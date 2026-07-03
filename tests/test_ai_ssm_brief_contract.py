import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock, patch

import pandas as pd
import requests

from hrv_app.ai import ssm_brief


class AiSsmBriefContractTests(unittest.TestCase):
    def _write_minimal_inputs(
        self,
        root: Path,
        *,
        gate_final: str = "ROJO",
        ssm_innovation: float = -0.25,
        sleep_innovation: float = -0.15,
        sleep_input_quality: str = "clean",
        veto_agudo: bool = False,
    ) -> tuple[Path, Path]:
        ssm_path = root / "ENDURANCE_HRV_ssm_shadow.csv"
        final_path = root / "ENDURANCE_HRV_master_FINAL.csv"

        pd.DataFrame(
            [
                {
                    "Fecha": "2026-06-26",
                    "ssm_warmup_complete": True,
                    "ssm_recovery_state": 3.70,
                    "ssm_baseline_state": 4.00,
                    "ssm_fatigue_state": 0.24,
                    "ssm_innovation": ssm_innovation,
                    "sleep_innovation": sleep_innovation,
                    "sleep_input_quality": sleep_input_quality,
                    "control_rolling_hrv_7d": 3.72,
                }
            ]
        ).to_csv(ssm_path, index=False)

        pd.DataFrame(
            [
                {
                    "Fecha": "2026-06-26",
                    "gate_final": gate_final,
                    "Action": "SUAVE_O_DESCANSO",
                    "Action_detail": "SUAVE",
                    "veto_agudo": veto_agudo,
                }
            ]
        ).to_csv(final_path, index=False)

        return ssm_path, final_path

    def test_disabled_returns_status_without_touching_disk(self):
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            ssm_path, final_path = self._write_minimal_inputs(root)
            with patch.object(ssm_brief, "SSM_SHADOW_PATH", ssm_path), \
                    patch.object(ssm_brief, "FINAL_PATH", final_path), \
                    patch.object(ssm_brief, "HRV_AI_ENABLED", False), \
                    patch.object(ssm_brief, "HRV_AI_SSM_ENABLED", True), \
                    patch.object(ssm_brief.requests, "post") as post_mock:
                result = ssm_brief.run_ai_ssm_brief_for_latest_date()

        self.assertEqual(result["status"], "disabled")
        post_mock.assert_not_called()

    def test_not_applicable_when_no_material_ssm_signal_skips_model_call(self):
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            ssm_path, final_path = self._write_minimal_inputs(
                root, ssm_innovation=0.02, sleep_innovation=0.01,
            )
            latest_path = root / "ENDURANCE_HRV_ai_ssm_brief_latest.json"

            with patch.object(ssm_brief, "SSM_SHADOW_PATH", ssm_path), \
                    patch.object(ssm_brief, "FINAL_PATH", final_path), \
                    patch.object(ssm_brief, "AI_SSM_BRIEF_LATEST_PATH", latest_path), \
                    patch.object(ssm_brief, "ai_ssm_brief_history_path", return_value=root / "ENDURANCE_HRV_ai_ssm_brief_2026-06-26.json"), \
                    patch.object(ssm_brief, "HRV_AI_ENABLED", True), \
                    patch.object(ssm_brief, "HRV_AI_SSM_ENABLED", True), \
                    patch.object(ssm_brief.requests, "post") as post_mock:
                result = ssm_brief.run_ai_ssm_brief_for_latest_date()
                self.assertTrue(latest_path.exists())

        self.assertEqual(result["status"], "not_applicable")
        self.assertFalse(result["published"])
        post_mock.assert_not_called()

    def test_successful_generation_is_idempotent_by_payload_hash(self):
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            ssm_path, final_path = self._write_minimal_inputs(root, gate_final="ROJO", veto_agudo=True)
            latest_path = root / "ENDURANCE_HRV_ai_ssm_brief_latest.json"
            history_path = root / "ENDURANCE_HRV_ai_ssm_brief_2026-06-26.json"

            response = Mock()
            response.raise_for_status.return_value = None
            response.json.return_value = {
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "date": "2026-06-26",
                                    "summary": "Sorpresa matinal clara por debajo de lo esperado refuerza la cautela del gate rojo.",
                                    "detail": "La penalizacion de fatiga es alta (≈21%). Hay un veto agudo activo que refuerza la restriccion.",
                                    "relation_to_gate_echo": "reinforces_gate",
                                    "trigger_echo": "ssm_innovation",
                                }
                            )
                        }
                    }
                ]
            }

            with patch.object(ssm_brief, "SSM_SHADOW_PATH", ssm_path), \
                    patch.object(ssm_brief, "FINAL_PATH", final_path), \
                    patch.object(ssm_brief, "AI_SSM_BRIEF_LATEST_PATH", latest_path), \
                    patch.object(ssm_brief, "ai_ssm_brief_history_path", return_value=history_path), \
                    patch.object(ssm_brief, "HRV_AI_ENABLED", True), \
                    patch.object(ssm_brief, "HRV_AI_SSM_ENABLED", True), \
                    patch.object(ssm_brief, "HRV_AI_PROVIDER", "test-provider"), \
                    patch.object(ssm_brief, "HRV_AI_MODEL", "test-model"), \
                    patch.object(ssm_brief, "HRV_AI_API_KEY", "secret"), \
                    patch.object(ssm_brief, "ai_chat_completions_url", return_value="https://example.test/chat/completions"), \
                    patch.object(ssm_brief.requests, "post", return_value=response) as post_mock:
                first = ssm_brief.run_ai_ssm_brief_for_latest_date()
                second = ssm_brief.run_ai_ssm_brief_for_latest_date()
                self.assertTrue(history_path.exists())
                self.assertTrue(latest_path.exists())

        self.assertEqual(first["status"], "ok")
        self.assertTrue(first["published"])
        self.assertEqual(first["relation_to_gate"], "reinforces_gate")
        self.assertEqual(first["trigger"], "ssm_innovation")
        self.assertEqual(second["status"], "skipped_unchanged")
        post_mock.assert_called_once()
        user_payload = json.loads(post_mock.call_args.kwargs["json"]["messages"][1]["content"])
        self.assertEqual(user_payload["gate_anchor"]["gate_final"], "ROJO")
        self.assertEqual(user_payload["publication"]["trigger"], "ssm_innovation")
        self.assertIn("Hay un veto agudo activo", user_payload["caveats"][0])

    def test_relation_to_gate_echo_mismatch_writes_validation_failed_sidecar(self):
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            ssm_path, final_path = self._write_minimal_inputs(root, gate_final="ROJO")
            latest_path = root / "ENDURANCE_HRV_ai_ssm_brief_latest.json"
            history_path = root / "ENDURANCE_HRV_ai_ssm_brief_2026-06-26.json"

            response = Mock()
            response.raise_for_status.return_value = None
            response.json.return_value = {
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "date": "2026-06-26",
                                    "summary": "Texto con relation_to_gate_echo incorrecto.",
                                    "detail": "Detalle de prueba.",
                                    "relation_to_gate_echo": "aligned",
                                    "trigger_echo": "ssm_innovation",
                                }
                            )
                        }
                    }
                ]
            }

            with patch.object(ssm_brief, "SSM_SHADOW_PATH", ssm_path), \
                    patch.object(ssm_brief, "FINAL_PATH", final_path), \
                    patch.object(ssm_brief, "AI_SSM_BRIEF_LATEST_PATH", latest_path), \
                    patch.object(ssm_brief, "ai_ssm_brief_history_path", return_value=history_path), \
                    patch.object(ssm_brief, "HRV_AI_ENABLED", True), \
                    patch.object(ssm_brief, "HRV_AI_SSM_ENABLED", True), \
                    patch.object(ssm_brief, "HRV_AI_PROVIDER", "test-provider"), \
                    patch.object(ssm_brief, "HRV_AI_MODEL", "test-model"), \
                    patch.object(ssm_brief, "HRV_AI_API_KEY", "secret"), \
                    patch.object(ssm_brief, "ai_chat_completions_url", return_value="https://example.test/chat/completions"), \
                    patch.object(ssm_brief.requests, "post", return_value=response):
                result = ssm_brief.run_ai_ssm_brief_for_latest_date()

        self.assertEqual(result["status"], "validation_failed")
        self.assertFalse(result["published"])
        self.assertIn("relation_to_gate_echo_mismatch", result["validation_errors"])

    def test_trigger_echo_mismatch_writes_validation_failed_sidecar(self):
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            ssm_path, final_path = self._write_minimal_inputs(root, gate_final="ROJO")
            latest_path = root / "ENDURANCE_HRV_ai_ssm_brief_latest.json"
            history_path = root / "ENDURANCE_HRV_ai_ssm_brief_2026-06-26.json"

            response = Mock()
            response.raise_for_status.return_value = None
            response.json.return_value = {
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "date": "2026-06-26",
                                    "summary": "Texto con trigger_echo incorrecto.",
                                    "detail": "Detalle de prueba.",
                                    "relation_to_gate_echo": "reinforces_gate",
                                    "trigger_echo": "sleep_innovation",
                                }
                            )
                        }
                    }
                ]
            }

            with patch.object(ssm_brief, "SSM_SHADOW_PATH", ssm_path), \
                    patch.object(ssm_brief, "FINAL_PATH", final_path), \
                    patch.object(ssm_brief, "AI_SSM_BRIEF_LATEST_PATH", latest_path), \
                    patch.object(ssm_brief, "ai_ssm_brief_history_path", return_value=history_path), \
                    patch.object(ssm_brief, "HRV_AI_ENABLED", True), \
                    patch.object(ssm_brief, "HRV_AI_SSM_ENABLED", True), \
                    patch.object(ssm_brief, "HRV_AI_PROVIDER", "test-provider"), \
                    patch.object(ssm_brief, "HRV_AI_MODEL", "test-model"), \
                    patch.object(ssm_brief, "HRV_AI_API_KEY", "secret"), \
                    patch.object(ssm_brief, "ai_chat_completions_url", return_value="https://example.test/chat/completions"), \
                    patch.object(ssm_brief.requests, "post", return_value=response):
                result = ssm_brief.run_ai_ssm_brief_for_latest_date()

        self.assertEqual(result["status"], "validation_failed")
        self.assertIn("trigger_echo_mismatch", result["validation_errors"])

    def test_numeric_contract_violation_writes_validation_failed_sidecar(self):
        # El payload de este fixture corresponde a fatigue_penalty ≈21%. Si el
        # modelo mete otro porcentaje (aqui ≈24%) el sidecar debe quedarse en
        # validation_failed en vez de status="ok".
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            ssm_path, final_path = self._write_minimal_inputs(root, gate_final="ROJO", veto_agudo=True)
            latest_path = root / "ENDURANCE_HRV_ai_ssm_brief_latest.json"
            history_path = root / "ENDURANCE_HRV_ai_ssm_brief_2026-06-26.json"

            response = Mock()
            response.raise_for_status.return_value = None
            response.json.return_value = {
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "date": "2026-06-26",
                                    "summary": "Sorpresa matinal clara por debajo de lo esperado refuerza la cautela del gate rojo.",
                                    "detail": "La penalizacion de fatiga es alta (≈24%). Hay un veto agudo activo.",
                                    "relation_to_gate_echo": "reinforces_gate",
                                    "trigger_echo": "ssm_innovation",
                                }
                            )
                        }
                    }
                ]
            }

            with patch.object(ssm_brief, "SSM_SHADOW_PATH", ssm_path), \
                    patch.object(ssm_brief, "FINAL_PATH", final_path), \
                    patch.object(ssm_brief, "AI_SSM_BRIEF_LATEST_PATH", latest_path), \
                    patch.object(ssm_brief, "ai_ssm_brief_history_path", return_value=history_path), \
                    patch.object(ssm_brief, "HRV_AI_ENABLED", True), \
                    patch.object(ssm_brief, "HRV_AI_SSM_ENABLED", True), \
                    patch.object(ssm_brief, "HRV_AI_PROVIDER", "test-provider"), \
                    patch.object(ssm_brief, "HRV_AI_MODEL", "test-model"), \
                    patch.object(ssm_brief, "HRV_AI_API_KEY", "secret"), \
                    patch.object(ssm_brief, "ai_chat_completions_url", return_value="https://example.test/chat/completions"), \
                    patch.object(ssm_brief.requests, "post", return_value=response):
                result = ssm_brief.run_ai_ssm_brief_for_latest_date()

        self.assertEqual(result["status"], "validation_failed")
        self.assertFalse(result["published"])
        self.assertIn("numeric_contract_violation", result["validation_errors"])

    def test_numeric_helper_accepts_display_tokens_and_rejects_others(self):
        payload = {
            "signals": {
                "morning_surprise": {"magnitude_vs_threshold_display": "2.4x"},
                "fatigue_penalty": {"pct_display": "≈21%"},
            }
        }
        allowed = ssm_brief._allowed_number_tokens(payload)
        self.assertIn("21%", allowed)
        self.assertIn("2.4x", allowed)

        # Texto que solo usa tokens permitidos: sin violacion.
        text_ok = "Sorpresa 2.4x por debajo. Fatiga alta (≈21%)."
        self.assertFalse(ssm_brief._extract_number_tokens(text_ok) - allowed)

        # Texto con porcentaje inventado: violacion.
        text_bad = "Fatiga alta (≈24%)."
        self.assertEqual(ssm_brief._extract_number_tokens(text_bad) - allowed, {"24%"})

    def test_missing_final_row_writes_error_sidecar(self):
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            ssm_path, final_path = self._write_minimal_inputs(root)
            # FINAL only has a different date than the SSM row.
            pd.DataFrame([{"Fecha": "2026-06-20", "gate_final": "ROJO", "Action_detail": "SUAVE", "veto_agudo": False}]).to_csv(
                final_path, index=False
            )
            latest_path = root / "ENDURANCE_HRV_ai_ssm_brief_latest.json"

            with patch.object(ssm_brief, "SSM_SHADOW_PATH", ssm_path), \
                    patch.object(ssm_brief, "FINAL_PATH", final_path), \
                    patch.object(ssm_brief, "AI_SSM_BRIEF_LATEST_PATH", latest_path), \
                    patch.object(ssm_brief, "ai_ssm_brief_history_path", return_value=root / "ENDURANCE_HRV_ai_ssm_brief_2026-06-26.json"), \
                    patch.object(ssm_brief, "HRV_AI_ENABLED", True), \
                    patch.object(ssm_brief, "HRV_AI_SSM_ENABLED", True), \
                    patch.object(ssm_brief.requests, "post") as post_mock:
                result = ssm_brief.run_ai_ssm_brief_for_latest_date()

        self.assertEqual(result["status"], "error")
        self.assertEqual(result["reason"], "missing_final_row")
        post_mock.assert_not_called()

    def test_fatigue_penalty_pct_matches_natural_units_percentage(self):
        pct = ssm_brief._fatigue_penalty_pct(4.00, 0.24)
        self.assertAlmostEqual(pct, 21.0, delta=1.0)
        self.assertEqual(ssm_brief._fatigue_label(pct), "high")
        self.assertEqual(ssm_brief._FATIGUE_LABEL_ES[ssm_brief._fatigue_label(pct)], "alta")

    def test_http_error_writes_response_preview_to_reason(self):
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            ssm_path, final_path = self._write_minimal_inputs(root, gate_final="ROJO")
            latest_path = root / "ENDURANCE_HRV_ai_ssm_brief_latest.json"
            history_path = root / "ENDURANCE_HRV_ai_ssm_brief_2026-06-26.json"

            response = Mock()
            response.text = '{"error":"unsupported thinking.type"}'
            response.raise_for_status.side_effect = requests.HTTPError(
                "400 Client Error: Bad Request for url: https://example.test/chat/completions",
                response=response,
            )

            with patch.object(ssm_brief, "SSM_SHADOW_PATH", ssm_path), \
                    patch.object(ssm_brief, "FINAL_PATH", final_path), \
                    patch.object(ssm_brief, "AI_SSM_BRIEF_LATEST_PATH", latest_path), \
                    patch.object(ssm_brief, "ai_ssm_brief_history_path", return_value=history_path), \
                    patch.object(ssm_brief, "HRV_AI_ENABLED", True), \
                    patch.object(ssm_brief, "HRV_AI_SSM_ENABLED", True), \
                    patch.object(ssm_brief, "HRV_AI_PROVIDER", "test-provider"), \
                    patch.object(ssm_brief, "HRV_AI_MODEL", "test-model"), \
                    patch.object(ssm_brief, "HRV_AI_API_KEY", "secret"), \
                    patch.object(ssm_brief, "ai_chat_completions_url", return_value="https://example.test/chat/completions"), \
                    patch.object(ssm_brief.requests, "post", return_value=response):
                result = ssm_brief.run_ai_ssm_brief_for_latest_date()

        self.assertEqual(result["status"], "error")
        self.assertIn("response_preview=", result["reason"])
        self.assertIn("unsupported thinking.type", result["reason"])

    def test_payload_hash_ignores_generated_at_timestamp(self):
        payload_a = {
            "meta": {"date": "2026-06-26", "generated_at": "2026-06-30T10:00:00"},
            "gate_anchor": {"gate_final": "ROJO"},
        }
        payload_b = {
            "meta": {"date": "2026-06-26", "generated_at": "2026-06-30T10:00:01"},
            "gate_anchor": {"gate_final": "ROJO"},
        }

        self.assertEqual(
            ssm_brief._hash_json(ssm_brief._payload_for_hash(payload_a)),
            ssm_brief._hash_json(ssm_brief._payload_for_hash(payload_b)),
        )


if __name__ == "__main__":
    unittest.main()
