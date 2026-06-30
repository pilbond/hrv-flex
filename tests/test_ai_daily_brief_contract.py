import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock, patch

import pandas as pd
import requests

from hrv_app.ai import daily_brief


class AiDailyBriefContractTests(unittest.TestCase):
    def _write_minimal_inputs(self, root: Path, gate_final: str = "VERDE") -> tuple[Path, Path, Path, Path]:
        final_path = root / "ENDURANCE_HRV_master_FINAL.csv"
        sleep_path = root / "ENDURANCE_HRV_sleep.csv"
        sessions_day_path = root / "ENDURANCE_HRV_sessions_day.csv"
        reason_items_path = root / "ENDURANCE_HRV_master_FINAL_reason_items.json"

        pd.DataFrame(
            [
                {
                    "Fecha": "2026-06-24",
                    "gate_badge": "VERDE++" if gate_final == "VERDE" else "NO",
                    "gate_final": gate_final,
                    "Action": "INTENSIDAD_OK",
                    "Action_detail": "EJECUTAR_PLAN",
                    "quality_flag": False,
                    "veto_agudo": False,
                    "baseline60_degraded": False,
                    "recovery_context_quality": "rich",
                    "recovery_support_class": "supported",
                    "recovery_discordance_flag": False,
                    "Calidad": "OK",
                    "HRV_Stability": "OK",
                    "Artifact_pct": 0.5,
                    "Tiempo_Estabilizacion": 60.0,
                    "HR_today": 45.1,
                    "RMSSD_stable": 65.7,
                    "lnRMSSD_today": 4.18,
                    "lnRMSSD_used": 3.91,
                    "HR_used": 47.5,
                    "gate_raw_today": "VERDE",
                    "gate_raw_reason": "2D_OK",
                    "ln_base60": 3.83,
                    "HR_base60": 48.8,
                    "d_ln": 0.08,
                    "d_HR": -1.2,
                    "residual_tag": "++",
                    "tail_mismatch_pct": 4.7,
                }
            ]
        ).to_csv(final_path, index=False)

        pd.DataFrame(
            [
                {
                    "Fecha": "2026-06-24",
                    "polar_sleep_duration_min": 425.5,
                    "polar_sleep_span_min": 441.0,
                    "polar_deep_pct": 23.5,
                    "polar_rem_pct": 21.0,
                    "polar_efficiency_pct": 96.4,
                    "polar_continuity": 4.0,
                    "polar_continuity_index": 4.0,
                    "polar_interruptions_long": 0.0,
                    "polar_interruptions_total": 21.0,
                    "polar_sleep_score": 83.6,
                    "polar_night_rmssd": 56.0,
                    "sleep_dur_p10": 358.75,
                    "sleep_dur_p90": 519.0,
                    "sleep_int_p90": 5.5,
                }
            ]
        ).to_csv(sleep_path, index=False)

        pd.DataFrame(
            [
                {
                    "Fecha": "2026-06-24",
                    "load_day": 76.0,
                    "load_3d": 152.0,
                    "load_7d": 337.0,
                    "load_14d": 561.0,
                    "acwr_simple_prev": 0.907,
                    "acute_load_72h_rel": 2.864,
                    "monotony_7d_prev": 2.881,
                    "strain_7d_prev": 970.9,
                    "intensity_clustering_flag": 0,
                    "load_ctx_ready": True,
                }
            ]
        ).to_csv(sessions_day_path, index=False)

        reason_items_path.write_text(
            json.dumps(
                {
                    "items_by_date": {
                        "2026-06-24": [
                            {
                                "type": "monotony",
                                "layer": "inference",
                                "source": "sessions_day",
                                "message": "Semana muy repetitiva, con poca variacion de carga (monotonia=2.88, alta)",
                                "metric": "monotony_7d_prev",
                                "value": 2.881,
                                "threshold": 2.0,
                            }
                        ]
                    }
                }
            ),
            encoding="utf-8",
        )
        return final_path, sleep_path, sessions_day_path, reason_items_path

    def test_gate_no_writes_not_applicable_sidecar_without_calling_model(self):
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            final_path, sleep_path, sessions_day_path, reason_items_path = self._write_minimal_inputs(root, gate_final="NO")
            latest_path = root / "ENDURANCE_HRV_ai_daily_brief_latest.json"

            with patch.object(daily_brief, "FINAL_PATH", final_path), \
                    patch.object(daily_brief, "SLEEP_PATH", sleep_path), \
                    patch.object(daily_brief, "SESSIONS_DAY_PATH", sessions_day_path), \
                    patch.object(daily_brief, "FINAL_REASON_ITEMS_PATH", reason_items_path), \
                    patch.object(daily_brief, "AI_DAILY_BRIEF_LATEST_PATH", latest_path), \
                    patch.object(daily_brief, "ai_daily_brief_history_path", return_value=root / "ENDURANCE_HRV_ai_daily_brief_2026-06-24.json"), \
                    patch.object(daily_brief, "HRV_AI_ENABLED", True), \
                    patch.object(daily_brief, "HRV_AI_DAILY_ENABLED", True), \
                    patch.object(daily_brief.requests, "post") as post_mock:
                result = daily_brief.run_ai_daily_brief_for_latest_date()
                self.assertTrue(latest_path.exists())

        self.assertEqual(result["status"], "not_applicable")
        self.assertFalse(result["published"])
        self.assertEqual(result["reason"], "gate_NO")
        post_mock.assert_not_called()

    def test_missing_sleep_writes_error_sidecar(self):
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            final_path, sleep_path, sessions_day_path, reason_items_path = self._write_minimal_inputs(root, gate_final="VERDE")
            latest_path = root / "ENDURANCE_HRV_ai_daily_brief_latest.json"
            sleep_path.unlink()

            with patch.object(daily_brief, "FINAL_PATH", final_path), \
                    patch.object(daily_brief, "SLEEP_PATH", sleep_path), \
                    patch.object(daily_brief, "SESSIONS_DAY_PATH", sessions_day_path), \
                    patch.object(daily_brief, "FINAL_REASON_ITEMS_PATH", reason_items_path), \
                    patch.object(daily_brief, "AI_DAILY_BRIEF_LATEST_PATH", latest_path), \
                    patch.object(daily_brief, "ai_daily_brief_history_path", return_value=root / "ENDURANCE_HRV_ai_daily_brief_2026-06-24.json"), \
                    patch.object(daily_brief, "HRV_AI_ENABLED", True), \
                    patch.object(daily_brief, "HRV_AI_DAILY_ENABLED", True):
                result = daily_brief.run_ai_daily_brief_for_latest_date()
                self.assertTrue(latest_path.exists())

        self.assertEqual(result["status"], "error")
        self.assertEqual(result["reason"], "missing_sleep")

    def test_successful_generation_is_idempotent_by_payload_hash(self):
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            final_path, sleep_path, sessions_day_path, reason_items_path = self._write_minimal_inputs(root, gate_final="VERDE")
            latest_path = root / "ENDURANCE_HRV_ai_daily_brief_latest.json"
            history_path = root / "ENDURANCE_HRV_ai_daily_brief_2026-06-24.json"

            response = Mock()
            response.raise_for_status.return_value = None
            response.json.return_value = {
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "date": "2026-06-24",
                                    "summary": "Dia verde con carga repetitiva.",
                                    "detail": "El gate es verde y conviene prudencia por monotonia alta (2.88 sobre 2.0).",
                                    "tone": "green",
                                    "source_mode": "reason_items",
                                }
                            )
                        }
                    }
                ]
            }

            with patch.object(daily_brief, "FINAL_PATH", final_path), \
                    patch.object(daily_brief, "SLEEP_PATH", sleep_path), \
                    patch.object(daily_brief, "SESSIONS_DAY_PATH", sessions_day_path), \
                    patch.object(daily_brief, "FINAL_REASON_ITEMS_PATH", reason_items_path), \
                    patch.object(daily_brief, "AI_DAILY_BRIEF_LATEST_PATH", latest_path), \
                    patch.object(daily_brief, "ai_daily_brief_history_path", return_value=history_path), \
                    patch.object(daily_brief, "HRV_AI_ENABLED", True), \
                    patch.object(daily_brief, "HRV_AI_DAILY_ENABLED", True), \
                    patch.object(daily_brief, "HRV_AI_PROVIDER", "test-provider"), \
                    patch.object(daily_brief, "HRV_AI_MODEL", "test-model"), \
                    patch.object(daily_brief, "HRV_AI_TEMPERATURE", 0.7), \
                    patch.object(daily_brief, "HRV_AI_TOP_P", 0.95), \
                    patch.object(daily_brief, "HRV_AI_THINKING", "disabled"), \
                    patch.object(daily_brief, "HRV_AI_MAX_TOKENS", 321), \
                    patch.object(daily_brief, "HRV_AI_API_KEY", "secret"), \
                    patch.object(daily_brief, "ai_chat_completions_url", return_value="https://example.test/chat/completions"), \
                    patch.object(daily_brief.requests, "post", return_value=response) as post_mock:
                first = daily_brief.run_ai_daily_brief_for_latest_date()
                second = daily_brief.run_ai_daily_brief_for_latest_date()
                self.assertTrue(history_path.exists())
                self.assertTrue(latest_path.exists())

        self.assertEqual(first["status"], "ok")
        self.assertTrue(first["published"])
        self.assertEqual(second["status"], "skipped_unchanged")
        post_mock.assert_called_once()
        self.assertEqual(post_mock.call_args.kwargs["json"]["temperature"], 0.7)
        self.assertEqual(post_mock.call_args.kwargs["json"]["top_p"], 0.95)
        self.assertEqual(post_mock.call_args.kwargs["json"]["max_tokens"], 321)
        user_payload = json.loads(post_mock.call_args.kwargs["json"]["messages"][1]["content"])
        self.assertEqual(user_payload["morning_hrv"]["gate_raw_today"], "VERDE")

    def test_payload_hash_ignores_generated_at_timestamp(self):
        payload_a = {
            "meta": {"date": "2026-06-24", "generated_at": "2026-06-30T10:00:00"},
            "decision": {"gate_final": "VERDE"},
        }
        payload_b = {
            "meta": {"date": "2026-06-24", "generated_at": "2026-06-30T10:00:01"},
            "decision": {"gate_final": "VERDE"},
        }

        self.assertEqual(
            daily_brief._hash_json(daily_brief._payload_for_hash(payload_a)),
            daily_brief._hash_json(daily_brief._payload_for_hash(payload_b)),
        )

    def test_reason_items_overlap_detects_semantic_families_not_only_literal_messages(self):
        overlap = daily_brief._reason_items_overlap(
            [
                {"type": "nightly_discordance", "message": "ROJO, pero el HRV de sueno salio alto"},
                {"type": "recovery_support", "message": "ROJO, pero la senal nocturna sale mejor de lo esperado"},
                {"type": "monotony", "message": "Semana muy repetitiva"},
                {"type": "strain", "message": "Semana muy exigente"},
            ]
        )

        self.assertFalse(overlap["contains_message_overlap"])
        self.assertTrue(overlap["contains_semantic_overlap"])
        self.assertIn(
            {"family": "recovery_signal", "types": ["nightly_discordance", "recovery_support"]},
            overlap["semantic_overlap_groups"],
        )
        self.assertIn(
            {"family": "load_caution", "types": ["monotony", "strain"]},
            overlap["semantic_overlap_groups"],
        )

    def test_tone_mismatch_writes_validation_failed_sidecar(self):
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            final_path, sleep_path, sessions_day_path, reason_items_path = self._write_minimal_inputs(root, gate_final="VERDE")
            latest_path = root / "ENDURANCE_HRV_ai_daily_brief_latest.json"
            history_path = root / "ENDURANCE_HRV_ai_daily_brief_2026-06-24.json"

            response = Mock()
            response.raise_for_status.return_value = None
            response.json.return_value = {
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "date": "2026-06-24",
                                    "summary": "Dia verde.",
                                    "detail": "Pero con tono incorrecto para la prueba.",
                                    "tone": "red",
                                    "source_mode": "reason_items",
                                }
                            )
                        }
                    }
                ]
            }

            with patch.object(daily_brief, "FINAL_PATH", final_path), \
                    patch.object(daily_brief, "SLEEP_PATH", sleep_path), \
                    patch.object(daily_brief, "SESSIONS_DAY_PATH", sessions_day_path), \
                    patch.object(daily_brief, "FINAL_REASON_ITEMS_PATH", reason_items_path), \
                    patch.object(daily_brief, "AI_DAILY_BRIEF_LATEST_PATH", latest_path), \
                    patch.object(daily_brief, "ai_daily_brief_history_path", return_value=history_path), \
                    patch.object(daily_brief, "HRV_AI_ENABLED", True), \
                    patch.object(daily_brief, "HRV_AI_DAILY_ENABLED", True), \
                    patch.object(daily_brief, "HRV_AI_PROVIDER", "test-provider"), \
                    patch.object(daily_brief, "HRV_AI_MODEL", "test-model"), \
                    patch.object(daily_brief, "HRV_AI_API_KEY", "secret"), \
                    patch.object(daily_brief, "ai_chat_completions_url", return_value="https://example.test/chat/completions"), \
                    patch.object(daily_brief.requests, "post", return_value=response):
                result = daily_brief.run_ai_daily_brief_for_latest_date()

        self.assertEqual(result["status"], "validation_failed")
        self.assertFalse(result["published"])
        self.assertIn("tone_mismatch", result["validation_errors"])

    def test_source_mode_mismatch_writes_validation_failed_sidecar(self):
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            final_path, sleep_path, sessions_day_path, reason_items_path = self._write_minimal_inputs(root, gate_final="VERDE")
            latest_path = root / "ENDURANCE_HRV_ai_daily_brief_latest.json"
            history_path = root / "ENDURANCE_HRV_ai_daily_brief_2026-06-24.json"

            response = Mock()
            response.raise_for_status.return_value = None
            response.json.return_value = {
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "date": "2026-06-24",
                                    "summary": "Dia verde.",
                                    "detail": "Pero con source_mode incorrecto para la prueba.",
                                    "tone": "green",
                                    "source_mode": "reason_text_fallback",
                                }
                            )
                        }
                    }
                ]
            }

            with patch.object(daily_brief, "FINAL_PATH", final_path), \
                    patch.object(daily_brief, "SLEEP_PATH", sleep_path), \
                    patch.object(daily_brief, "SESSIONS_DAY_PATH", sessions_day_path), \
                    patch.object(daily_brief, "FINAL_REASON_ITEMS_PATH", reason_items_path), \
                    patch.object(daily_brief, "AI_DAILY_BRIEF_LATEST_PATH", latest_path), \
                    patch.object(daily_brief, "ai_daily_brief_history_path", return_value=history_path), \
                    patch.object(daily_brief, "HRV_AI_ENABLED", True), \
                    patch.object(daily_brief, "HRV_AI_DAILY_ENABLED", True), \
                    patch.object(daily_brief, "HRV_AI_PROVIDER", "test-provider"), \
                    patch.object(daily_brief, "HRV_AI_MODEL", "test-model"), \
                    patch.object(daily_brief, "HRV_AI_API_KEY", "secret"), \
                    patch.object(daily_brief, "ai_chat_completions_url", return_value="https://example.test/chat/completions"), \
                    patch.object(daily_brief.requests, "post", return_value=response):
                result = daily_brief.run_ai_daily_brief_for_latest_date()

        self.assertEqual(result["status"], "validation_failed")
        self.assertFalse(result["published"])
        self.assertIn("source_mode_mismatch", result["validation_errors"])

    def test_thinking_disabled_is_only_sent_for_kimi_or_moonshot(self):
        with patch.object(daily_brief, "HRV_AI_THINKING", "disabled"), \
                patch.object(daily_brief, "HRV_AI_PROVIDER", "other"), \
                patch.object(daily_brief, "HRV_AI_MODEL", "some-model"):
            self.assertFalse(daily_brief._should_send_thinking_param())

        with patch.object(daily_brief, "HRV_AI_THINKING", "disabled"), \
                patch.object(daily_brief, "HRV_AI_PROVIDER", "moonshot"), \
                patch.object(daily_brief, "HRV_AI_MODEL", "kimi-k2.6"):
            self.assertTrue(daily_brief._should_send_thinking_param())

    def test_non_json_model_output_writes_preview_to_error_sidecar(self):
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            final_path, sleep_path, sessions_day_path, reason_items_path = self._write_minimal_inputs(root, gate_final="VERDE")
            latest_path = root / "ENDURANCE_HRV_ai_daily_brief_latest.json"
            history_path = root / "ENDURANCE_HRV_ai_daily_brief_2026-06-24.json"

            response = Mock()
            response.raise_for_status.return_value = None
            response.json.return_value = {
                "choices": [
                    {
                        "message": {
                            "content": "No puedo devolver JSON valido para esta prueba."
                        }
                    }
                ]
            }

            with patch.object(daily_brief, "FINAL_PATH", final_path), \
                    patch.object(daily_brief, "SLEEP_PATH", sleep_path), \
                    patch.object(daily_brief, "SESSIONS_DAY_PATH", sessions_day_path), \
                    patch.object(daily_brief, "FINAL_REASON_ITEMS_PATH", reason_items_path), \
                    patch.object(daily_brief, "AI_DAILY_BRIEF_LATEST_PATH", latest_path), \
                    patch.object(daily_brief, "ai_daily_brief_history_path", return_value=history_path), \
                    patch.object(daily_brief, "HRV_AI_ENABLED", True), \
                    patch.object(daily_brief, "HRV_AI_DAILY_ENABLED", True), \
                    patch.object(daily_brief, "HRV_AI_PROVIDER", "test-provider"), \
                    patch.object(daily_brief, "HRV_AI_MODEL", "test-model"), \
                    patch.object(daily_brief, "HRV_AI_API_KEY", "secret"), \
                    patch.object(daily_brief, "ai_chat_completions_url", return_value="https://example.test/chat/completions"), \
                    patch.object(daily_brief.requests, "post", return_value=response):
                result = daily_brief.run_ai_daily_brief_for_latest_date()

        self.assertEqual(result["status"], "error")
        self.assertIn("Expecting value", result["reason"])
        self.assertEqual(result["model_output_preview"], "No puedo devolver JSON valido para esta prueba.")

    def test_http_error_writes_response_preview_to_reason(self):
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            final_path, sleep_path, sessions_day_path, reason_items_path = self._write_minimal_inputs(root, gate_final="VERDE")
            latest_path = root / "ENDURANCE_HRV_ai_daily_brief_latest.json"
            history_path = root / "ENDURANCE_HRV_ai_daily_brief_2026-06-24.json"

            response = Mock()
            response.text = '{"error":"unsupported thinking.type"}'
            response.raise_for_status.side_effect = requests.HTTPError(
                "400 Client Error: Bad Request for url: https://example.test/chat/completions",
                response=response,
            )

            with patch.object(daily_brief, "FINAL_PATH", final_path), \
                    patch.object(daily_brief, "SLEEP_PATH", sleep_path), \
                    patch.object(daily_brief, "SESSIONS_DAY_PATH", sessions_day_path), \
                    patch.object(daily_brief, "FINAL_REASON_ITEMS_PATH", reason_items_path), \
                    patch.object(daily_brief, "AI_DAILY_BRIEF_LATEST_PATH", latest_path), \
                    patch.object(daily_brief, "ai_daily_brief_history_path", return_value=history_path), \
                    patch.object(daily_brief, "HRV_AI_ENABLED", True), \
                    patch.object(daily_brief, "HRV_AI_DAILY_ENABLED", True), \
                    patch.object(daily_brief, "HRV_AI_PROVIDER", "test-provider"), \
                    patch.object(daily_brief, "HRV_AI_MODEL", "test-model"), \
                    patch.object(daily_brief, "HRV_AI_API_KEY", "secret"), \
                    patch.object(daily_brief, "ai_chat_completions_url", return_value="https://example.test/chat/completions"), \
                    patch.object(daily_brief.requests, "post", return_value=response):
                result = daily_brief.run_ai_daily_brief_for_latest_date()

        self.assertEqual(result["status"], "error")
        self.assertIn("response_preview=", result["reason"])
        self.assertIn("unsupported thinking.type", result["reason"])

    def test_extract_failure_writes_response_json_preview_to_sidecar(self):
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            final_path, sleep_path, sessions_day_path, reason_items_path = self._write_minimal_inputs(root, gate_final="VERDE")
            latest_path = root / "ENDURANCE_HRV_ai_daily_brief_latest.json"
            history_path = root / "ENDURANCE_HRV_ai_daily_brief_2026-06-24.json"

            response = Mock()
            response.raise_for_status.return_value = None
            response.json.return_value = {"choices": [{"message": {"content": None}}]}

            with patch.object(daily_brief, "FINAL_PATH", final_path), \
                    patch.object(daily_brief, "SLEEP_PATH", sleep_path), \
                    patch.object(daily_brief, "SESSIONS_DAY_PATH", sessions_day_path), \
                    patch.object(daily_brief, "FINAL_REASON_ITEMS_PATH", reason_items_path), \
                    patch.object(daily_brief, "AI_DAILY_BRIEF_LATEST_PATH", latest_path), \
                    patch.object(daily_brief, "ai_daily_brief_history_path", return_value=history_path), \
                    patch.object(daily_brief, "HRV_AI_ENABLED", True), \
                    patch.object(daily_brief, "HRV_AI_DAILY_ENABLED", True), \
                    patch.object(daily_brief, "HRV_AI_PROVIDER", "test-provider"), \
                    patch.object(daily_brief, "HRV_AI_MODEL", "test-model"), \
                    patch.object(daily_brief, "HRV_AI_API_KEY", "secret"), \
                    patch.object(daily_brief, "ai_chat_completions_url", return_value="https://example.test/chat/completions"), \
                    patch.object(daily_brief.requests, "post", return_value=response):
                result = daily_brief.run_ai_daily_brief_for_latest_date()

        self.assertEqual(result["status"], "error")
        self.assertEqual(result["reason"], "response_without_text_content")
        self.assertIn('"content": null', result["model_output_preview"])

    def test_latest_sleep_and_sessions_rows_are_chosen_by_date_not_file_order(self):
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            final_path, sleep_path, sessions_day_path, reason_items_path = self._write_minimal_inputs(root, gate_final="VERDE")
            latest_path = root / "ENDURANCE_HRV_ai_daily_brief_latest.json"
            history_path = root / "ENDURANCE_HRV_ai_daily_brief_2026-06-24.json"

            pd.DataFrame(
                [
                    {
                        "Fecha": "2026-06-24",
                        "polar_sleep_duration_min": 425.5,
                        "polar_sleep_span_min": 441.0,
                        "polar_deep_pct": 23.5,
                        "polar_rem_pct": 21.0,
                        "polar_efficiency_pct": 96.4,
                        "polar_continuity": 4.0,
                        "polar_continuity_index": 4.0,
                        "polar_interruptions_long": 0.0,
                        "polar_interruptions_total": 21.0,
                        "polar_sleep_score": 83.6,
                        "polar_night_rmssd": 56.0,
                        "sleep_dur_p10": 358.75,
                        "sleep_dur_p90": 519.0,
                        "sleep_int_p90": 5.5,
                    },
                    {
                        "Fecha": "2026-06-23",
                        "polar_sleep_duration_min": 390.0,
                        "polar_sleep_span_min": 410.0,
                        "polar_deep_pct": 20.0,
                        "polar_rem_pct": 19.0,
                        "polar_efficiency_pct": 92.0,
                        "polar_continuity": 3.0,
                        "polar_continuity_index": 3.0,
                        "polar_interruptions_long": 2.0,
                        "polar_interruptions_total": 30.0,
                        "polar_sleep_score": 70.0,
                        "polar_night_rmssd": 45.0,
                        "sleep_dur_p10": 358.75,
                        "sleep_dur_p90": 519.0,
                        "sleep_int_p90": 5.5,
                    },
                ]
            ).iloc[[1, 0]].to_csv(sleep_path, index=False)

            pd.DataFrame(
                [
                    {
                        "Fecha": "2026-06-24",
                        "load_day": 76.0,
                        "load_3d": 152.0,
                        "load_7d": 337.0,
                        "load_14d": 561.0,
                        "acwr_simple_prev": 0.907,
                        "acute_load_72h_rel": 2.864,
                        "monotony_7d_prev": 2.881,
                        "strain_7d_prev": 970.9,
                        "intensity_clustering_flag": 0,
                        "load_ctx_ready": True,
                    },
                    {
                        "Fecha": "2026-06-23",
                        "load_day": 40.0,
                        "load_3d": 100.0,
                        "load_7d": 250.0,
                        "load_14d": 500.0,
                        "acwr_simple_prev": 0.8,
                        "acute_load_72h_rel": 2.2,
                        "monotony_7d_prev": 1.7,
                        "strain_7d_prev": 800.0,
                        "intensity_clustering_flag": 1,
                        "load_ctx_ready": True,
                    },
                ]
            ).iloc[[1, 0]].to_csv(sessions_day_path, index=False)

            response = Mock()
            response.raise_for_status.return_value = None
            response.json.return_value = {
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "date": "2026-06-24",
                                    "summary": "Dia verde con carga repetitiva.",
                                    "detail": "El gate es verde y conviene prudencia por monotonia alta (2.88 sobre 2.0).",
                                    "tone": "green",
                                    "source_mode": "reason_items",
                                }
                            )
                        }
                    }
                ]
            }

            with patch.object(daily_brief, "FINAL_PATH", final_path), \
                    patch.object(daily_brief, "SLEEP_PATH", sleep_path), \
                    patch.object(daily_brief, "SESSIONS_DAY_PATH", sessions_day_path), \
                    patch.object(daily_brief, "FINAL_REASON_ITEMS_PATH", reason_items_path), \
                    patch.object(daily_brief, "AI_DAILY_BRIEF_LATEST_PATH", latest_path), \
                    patch.object(daily_brief, "ai_daily_brief_history_path", return_value=history_path), \
                    patch.object(daily_brief, "HRV_AI_ENABLED", True), \
                    patch.object(daily_brief, "HRV_AI_DAILY_ENABLED", True), \
                    patch.object(daily_brief, "HRV_AI_PROVIDER", "test-provider"), \
                    patch.object(daily_brief, "HRV_AI_MODEL", "test-model"), \
                    patch.object(daily_brief, "HRV_AI_API_KEY", "secret"), \
                    patch.object(daily_brief, "ai_chat_completions_url", return_value="https://example.test/chat/completions"), \
                    patch.object(daily_brief.requests, "post", return_value=response) as post_mock:
                result = daily_brief.run_ai_daily_brief_for_latest_date()

        self.assertEqual(result["status"], "ok")
        user_payload = json.loads(post_mock.call_args.kwargs["json"]["messages"][1]["content"])
        self.assertEqual(user_payload["sleep_context"]["polar_sleep_score"], 83.6)
        self.assertEqual(user_payload["recent_load_summary"]["monotony_7d_prev"], 2.881)

    def test_empty_model_output_has_explicit_error_reason(self):
        with self.assertRaisesRegex(ValueError, "empty_model_output"):
            daily_brief._parse_model_output("")


if __name__ == "__main__":
    unittest.main()
