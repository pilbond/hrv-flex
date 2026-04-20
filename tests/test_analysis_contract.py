import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from analysis.fit_terrain_utils import (
    _build_validation_vs_v2,
    _select_altitude_value,
    analyze_terrain_records,
)
from analysis.session_analysis_pipeline import (
    _build_best_block_comparator,
    _build_same_day_sessions,
    _build_route_history_comparator,
    _build_weekly_intensity_distribution,
    _compute_sport_percentiles,
    _build_no_rr_summary,
    _normalize_terrain_interval_rows,
    _supports_terrain_context,
    _summarize_terrain_context_from_intervals,
    build_ai_handoff_markdown,
    build_analyst_prompt_markdown,
    build_conversational_payload,
    build_final_reason_rendered,
    build_final_report_markdown,
    build_report_sync_status,
    build_report_sync_token,
    extract_report_sync_token,
    enrich_summary_with_manifest_context,
    enrich_summary_with_sessions_metadata,
    infer_sport_family,
    resolve_final_reason_semantics,
    render_report_markdown,
    rr_sections_visible,
    write_managed_final_report,
)
from analysis.session_cost_model import normalize_sport
from analysis.training_audit_utils import (
    session_report_evidence,
    summary_training_audit,
    training_audit_dataset_limits,
    training_audit_metric_state,
    training_audit_session_affected,
)


def _session_row(**overrides):
    row = {
        "session_id": "i1",
        "Fecha": "2026-03-25",
        "start_time": "09:00",
        "sport": "road_run",
        "vt1_used": "143",
        "vt2_used": "161",
        "zones_source": "icu",
        "moving_min": "50.0",
        "elev_gain_m": "",
        "elev_loss_m": "",
        "elev_density": "",
        "hr_p95": "165",
        "z2_pct": "20.0",
        "z3_pct": "10.0",
        "z2_total_min": "10.0",
        "z3_total_min": "5.0",
        "work_n_blocks": "3",
        "work_total_min": "18.0",
        "work_longest_min": "7.0",
        "work_avg_z3_pct": "20.0",
    }
    row.update(overrides)
    return row


class AnalysisContractTests(unittest.TestCase):
    def test_resolve_final_reason_semantics_derives_structured_flags(self):
        items = [
            {
                "type": "data_quality",
                "layer": "measured",
                "source": "hrv_pipeline",
                "message": "Dato dudoso",
                "metric": "Artifact_pct",
                "value": 12.5,
            },
            {
                "type": "acwr",
                "layer": "inference",
                "source": "sessions_day",
                "message": "Carga reciente alta",
            },
            {
                "type": "action_constraint",
                "layer": "action",
                "source": "gate_final",
                "message": "contener la intensidad",
            },
            {
                "type": "recovery_discordance",
                "layer": "inference",
                "source": "sleep+sessions_day",
                "message": "Discordancia",
            },
        ]
        normalized, flags, contract = resolve_final_reason_semantics(items)
        self.assertEqual(len(normalized), 4)
        self.assertTrue(flags["has_measured_quality_caution"])
        self.assertTrue(flags["has_load_inference_caution"])
        self.assertTrue(flags["has_action_constraint"])
        self.assertTrue(flags["has_recovery_discordance"])
        self.assertTrue(flags["has_explicit_tension"])
        self.assertTrue(contract["available"])
        self.assertTrue(contract["conformant"])
        self.assertEqual(contract["received_items"], 4)
        self.assertEqual(contract["normalized_items"], 4)
        self.assertEqual(contract["recognized_items"], 4)
        self.assertFalse(contract["fallback_to_reason_text"])

    def test_resolve_final_reason_semantics_keeps_unknown_layers_but_marks_contract_nonconformant(self):
        normalized, flags, contract = resolve_final_reason_semantics(
            [
                {
                    "type": "acwr",
                    "layer": "inference",
                    "source": "sessions_day",
                    "message": "Carga reciente alta",
                },
                {
                    "type": "mystery",
                    "layer": "context",
                    "source": "unknown",
                    "message": "Capa no soportada",
                },
            ]
        )
        self.assertEqual(len(normalized), 2)
        self.assertFalse(contract["conformant"])
        self.assertEqual(contract["unknown_layers"], ["context"])
        self.assertEqual(contract["received_items"], 2)
        self.assertEqual(contract["normalized_items"], 2)
        self.assertEqual(contract["recognized_items"], 1)
        self.assertEqual(contract["invalid_items"], 1)
        self.assertTrue(flags["has_load_inference_caution"])

    def test_build_conversational_payload_exposes_reason_items_and_flags(self):
        session_row = _session_row()
        manifest = {
            "session_id": "i1",
            "slug": "2026-03-25_09-00_road_run_i1",
            "date": "2026-03-25",
            "start_time": "09:00",
            "sport": "road_run",
        }

        def fake_row_by_date(path, date_str):
            if path.name == "ENDURANCE_HRV_master_FINAL.csv":
                return {
                    "Fecha": date_str,
                    "Calidad": "OK",
                    "RMSSD_stable": "40.2",
                    "lnRMSSD_used": "3.69",
                    "HR_used": "49.8",
                    "d_ln": "0.03",
                    "d_HR": "-1.2",
                    "residual_z": "0.4",
                    "gate_badge": "VERDE",
                    "Action": "Normal con prudencia",
                    "baseline60_degraded": "False",
                    "recovery_context_quality": "rich",
                    "recovery_support_class": "fragile",
                    "recovery_discordance_flag": "True",
                    "recovery_discordance_reason": "sleep_basic_poor",
                    "reason_text": "VERDE, pero sueño y carga reciente piden prudencia",
                }
            if path.name == "ENDURANCE_HRV_master_DASHBOARD.csv":
                return {
                    "Fecha": date_str,
                    "Calidad": "OK",
                    "HR_today": "50.0",
                    "RMSSD_stable": "40.2",
                    "gate_badge": "VERDE",
                    "Action": "Normal con prudencia",
                    "baseline60_degraded": "False",
                    "reason_text": "VERDE, pero sueño y carga reciente piden prudencia",
                }
            return None

        reason_lookup = {
            "2026-03-25": [
                {
                    "type": "data_quality",
                    "layer": "measured",
                    "source": "hrv_pipeline",
                    "message": "Dato dudoso",
                },
                {
                    "type": "acwr",
                    "layer": "inference",
                    "source": "sessions_day",
                    "message": "Carga reciente alta",
                },
                {
                    "type": "action_constraint",
                    "layer": "action",
                    "source": "gate_final",
                    "message": "contener la intensidad",
                },
                {
                    "type": "recovery_discordance",
                    "layer": "inference",
                    "source": "sleep+sessions_day",
                    "message": "Discordancia",
                },
            ]
        }

        with patch("analysis.session_analysis_pipeline.row_by_date", side_effect=fake_row_by_date), patch(
            "analysis.session_analysis_pipeline.load_optional_json", return_value=None
        ), patch(
            "analysis.session_analysis_pipeline.load_final_reason_items_lookup", return_value=reason_lookup
        ), patch(
            "analysis.session_analysis_pipeline._compute_speed_metrics", return_value=None
        ):
            payload = build_conversational_payload({}, manifest, session_row)

        self.assertEqual(len(payload["final_reason_items"]), 4)
        self.assertTrue(payload["final_reason_flags"]["has_measured_quality_caution"])
        self.assertTrue(payload["final_reason_flags"]["has_load_inference_caution"])
        self.assertTrue(payload["final_reason_flags"]["has_action_constraint"])
        self.assertTrue(payload["final_reason_flags"]["has_recovery_discordance"])
        self.assertTrue(payload["final_reason_flags"]["has_explicit_tension"])
        self.assertTrue(payload["final_reason_items_contract"]["conformant"])
        self.assertEqual(payload["final_reason_items_contract"]["normalized_items"], 4)
        rendered = payload["narrative_targets"]["final_reason_rendered"]
        self.assertTrue(rendered["enabled"])
        self.assertEqual(rendered["source"], "final_reason_items")
        self.assertEqual(rendered["reporting_mode"], "caution_first")
        self.assertIsNone(rendered["action_readout"])
        self.assertTrue(any("`acwr`" in line for line in rendered["lines"]))
        self.assertEqual(rendered["items"][0]["signal_kind"], "measured_quality")
        self.assertEqual(rendered["items"][1]["signal_kind"], "accumulated_load")

    def test_build_conversational_payload_falls_back_cleanly_when_reason_items_missing(self):
        session_row = _session_row()
        manifest = {
            "session_id": "i1",
            "slug": "2026-03-25_09-00_road_run_i1",
            "date": "2026-03-25",
            "start_time": "09:00",
            "sport": "road_run",
        }

        def fake_row_by_date(path, date_str):
            if path.name == "ENDURANCE_HRV_master_FINAL.csv":
                return {
                    "Fecha": date_str,
                    "Calidad": "OK",
                    "RMSSD_stable": "40.2",
                    "lnRMSSD_used": "3.69",
                    "HR_used": "49.8",
                    "d_ln": "0.03",
                    "d_HR": "-1.2",
                    "residual_z": "0.4",
                    "gate_badge": "VERDE",
                    "Action": "Normal con prudencia",
                    "baseline60_degraded": "False",
                    "recovery_context_quality": "rich",
                    "recovery_support_class": "fragile",
                    "recovery_discordance_flag": "False",
                    "recovery_discordance_reason": "",
                    "reason_text": "VERDE, pero sueño y carga reciente piden prudencia",
                }
            if path.name == "ENDURANCE_HRV_master_DASHBOARD.csv":
                return {
                    "Fecha": date_str,
                    "Calidad": "OK",
                    "HR_today": "50.0",
                    "RMSSD_stable": "40.2",
                    "gate_badge": "VERDE",
                    "Action": "Normal con prudencia",
                    "baseline60_degraded": "False",
                    "reason_text": "VERDE, pero sueño y carga reciente piden prudencia",
                }
            return None

        with patch("analysis.session_analysis_pipeline.row_by_date", side_effect=fake_row_by_date), patch(
            "analysis.session_analysis_pipeline.load_optional_json", return_value=None
        ), patch(
            "analysis.session_analysis_pipeline.load_final_reason_items_lookup", return_value={}
        ), patch(
            "analysis.session_analysis_pipeline._compute_speed_metrics", return_value=None
        ):
            payload = build_conversational_payload({}, manifest, session_row)

        self.assertEqual(payload["final_reason_items"], [])
        self.assertTrue(payload["final_reason_items_contract"]["fallback_to_reason_text"])
        self.assertEqual(
            payload["context"]["final"]["reason_text"],
            "VERDE, pero sueño y carga reciente piden prudencia",
        )
        self.assertFalse(payload["final_reason_flags"]["has_explicit_tension"])
        rendered = payload["narrative_targets"]["final_reason_rendered"]
        self.assertFalse(rendered["enabled"])
        self.assertEqual(rendered["source"], "reason_text_fallback")

    def test_build_final_reason_rendered_preserves_temporal_density_and_precision_modifier(self):
        rendered = build_final_reason_rendered(
            final_reason_items=[
                {
                    "type": "intensity_clustering",
                    "layer": "inference",
                    "metric": "intensity_clustering_flag",
                    "value": 1,
                    "message": "VERDE pero con 1 día intenso en los últimos 3 (y 2 en los últimos 5): prudencia con la intensidad",
                },
                {
                    "type": "green_load_caution",
                    "layer": "inference",
                    "metric": "load_3d",
                    "value": 221.0,
                    "threshold": 200.0,
                    "message": "VERDE con carga acumulada (load_3d=221): precaución con la intensidad",
                },
            ],
            final_reason_flags={
                "has_measured_quality_caution": False,
                "has_load_inference_caution": True,
                "has_action_constraint": False,
                "has_recovery_discordance": False,
                "has_explicit_tension": True,
            },
            final_reason_items_contract={
                "conformant": True,
                "fallback_to_reason_text": False,
            },
            final_row={"baseline60_degraded": "True", "gate_badge": "VERDE+++", "Action": "INTENSIDAD_OK"},
        )
        self.assertEqual(rendered["reporting_mode"], "caution_first")
        self.assertEqual(rendered["items"][0]["signal_kind"], "temporal_density")
        self.assertEqual(rendered["items"][1]["signal_kind"], "accumulated_load")
        self.assertIn("1 día intenso en los últimos 3 (y 2 en los últimos 5)", rendered["items"][0]["message"])
        self.assertEqual(rendered["baseline_modifier"]["signal_kind"], "precision_modifier")
        self.assertIn("baseline60_degraded = true", rendered["baseline_readout"])
        self.assertEqual(rendered["gate_readout"], "`gate_badge = VERDE+++` y `Action = INTENSIDAD_OK`")
        self.assertIn("Si el gate sigue en `VERDE`", rendered["instructions"][3])

    def test_build_final_reason_rendered_switches_to_gate_first_for_amber(self):
        rendered = build_final_reason_rendered(
            final_reason_items=[
                {
                    "type": "intensity_clustering",
                    "layer": "inference",
                    "metric": "intensity_clustering_flag",
                    "value": 1,
                    "message": "Clustering reciente de intensidad: vigilar recuperación (1 intensos en últimos 3d; 2 en últimos 5d)",
                }
            ],
            final_reason_flags={
                "has_measured_quality_caution": False,
                "has_load_inference_caution": True,
                "has_action_constraint": False,
                "has_recovery_discordance": False,
                "has_explicit_tension": True,
            },
            final_reason_items_contract={
                "conformant": True,
                "fallback_to_reason_text": False,
            },
            final_row={"baseline60_degraded": "True", "gate_badge": "ÁMBAR+++", "Action": "Z2_O_TEMPO_SUAVE"},
        )
        self.assertEqual(rendered["reporting_mode"], "gate_first")
        self.assertEqual(rendered["gate_readout"], "`gate_badge = ÁMBAR+++` y `Action = Z2_O_TEMPO_SUAVE`")
        self.assertTrue(rendered["lines"][0].startswith("- `gate_badge = ÁMBAR+++`"))
        self.assertIn("Si el gate ya es `ÁMBAR` o `ROJO`", rendered["instructions"][3])

    def test_build_analyst_prompt_markdown_injects_pre_rendered_final_reason_block(self):
        prompt = build_analyst_prompt_markdown(
            report_dir=Path("analysis/reports/example"),
            payload_path=Path("analysis/reports/example/artifacts/session_payload.json"),
            summary_path=Path("analysis/reports/example/artifacts/summary.json"),
            blocks_path=None,
            terrain_intervals_path=None,
            terrain_climbs_path=None,
            coach_metrics_path=None,
            coach_intervals_path=None,
            coach_groups_path=None,
            report_sync_token="abc123def4567890",
            final_reason_rendered={
                "enabled": True,
                "title": "Tension explicita pre-resuelta",
                "gate_readout": "`gate_badge = ÁMBAR+++` y `Action = Z2_O_TEMPO_SUAVE`",
                "reason_items": [
                    {
                        "line": "- `intensity_clustering` (`intensity_clustering_flag=1`): 1 dia intenso en los ultimos 3"
                    },
                    {
                        "line": "- `green_load_caution` (`load_3d=221`, umbral `200`): carga acumulada alta"
                    },
                ],
                "action_readout": "`has_action_constraint = false` -> no hay restriccion de accion activa; la cautela existe, pero no hay veto adicional.",
                "baseline_readout": "`baseline60_degraded = true` -> usar como rebaja de precision del contexto, no como veto operativo por si solo.",
                "instructions": [
                    "Deriva `Tension explicita` de estos items ya renderizados.",
                    "No cites `reason_text` como fuente primaria cuando este bloque este activo.",
                ],
            },
        )
        self.assertIn("## Tension explicita pre-resuelta", prompt)
        self.assertIn("### Gate", prompt)
        self.assertIn("### Cautelas tipificadas", prompt)
        self.assertIn("### Lectura operativa", prompt)
        self.assertIn("### Precision del contexto", prompt)
        self.assertIn("NO usar `session_payload.json.context.final.reason_text`", prompt)
        self.assertIn("HR estimada en α1=0.75", prompt)
        self.assertIn("<!-- report_sync_token: abc123def4567890 -->", prompt)
        self.assertIn("`intensity_clustering` (`intensity_clustering_flag=1`)", prompt)
        self.assertIn("no hay restriccion de accion activa", prompt)

    def test_build_ai_handoff_markdown_includes_report_sync_token_instruction(self):
        with TemporaryDirectory() as tmp:
            tmpdir = Path(tmp)
            summary_path = tmpdir / "summary.json"
            summary_path.write_text(
                json.dumps({"hr_at_075_crossing": {"hr_at_075_crossing": 158.5, "confidence": "low"}}),
                encoding="utf-8",
            )
            handoff = build_ai_handoff_markdown(
                report_dir=Path("analysis/reports/example"),
                artifacts_dir=Path("analysis/reports/example/artifacts"),
                payload_path=Path("analysis/reports/example/artifacts/session_payload.json"),
                summary_path=summary_path,
                blocks_path=None,
                terrain_intervals_path=None,
                terrain_climbs_path=None,
                coach_metrics_path=None,
                coach_intervals_path=None,
                coach_groups_path=None,
                debug_dir=None,
                report_sync_token="abc123def4567890",
            )
            self.assertIn("## Sincronizacion de report.md", handoff)
            self.assertIn("<!-- report_sync_token: abc123def4567890 -->", handoff)
            self.assertIn("## RR orientativa", handoff)

    def test_build_report_sync_status_detects_missing_legacy_stale_and_up_to_date(self):
        with TemporaryDirectory() as tmp:
            tmpdir = Path(tmp)
            payload_path = tmpdir / "session_payload.json"
            summary_path = tmpdir / "summary.json"
            technical_report_path = tmpdir / "technical_report.md"
            report_path = tmpdir / "report.md"
            payload_path.write_text('{"a": 1}', encoding="utf-8")
            summary_path.write_text('{"b": 2}', encoding="utf-8")
            technical_report_path.write_text("# Technical report\n", encoding="utf-8")

            current_token = build_report_sync_token(
                payload_path=payload_path,
                summary_path=summary_path,
                technical_report_path=technical_report_path,
                rules_version="1.8",
            )

            missing = build_report_sync_status(
                report_path=report_path,
                current_token=current_token,
                payload_path=payload_path,
                summary_path=summary_path,
                technical_report_path=technical_report_path,
            )
            self.assertEqual(missing["status"], "missing")

            report_path.write_text("# Legacy report\n", encoding="utf-8")
            legacy = build_report_sync_status(
                report_path=report_path,
                current_token=current_token,
                payload_path=payload_path,
                summary_path=summary_path,
                technical_report_path=technical_report_path,
            )
            self.assertEqual(legacy["status"], "unmanaged_legacy")

            report_path.write_text(
                "<!-- report_sync_token: deadbeefdeadbeef -->\n# Report\n",
                encoding="utf-8",
            )
            stale = build_report_sync_status(
                report_path=report_path,
                current_token=current_token,
                payload_path=payload_path,
                summary_path=summary_path,
                technical_report_path=technical_report_path,
            )
            self.assertEqual(stale["status"], "stale")
            self.assertEqual(extract_report_sync_token(report_path), "deadbeefdeadbeef")

            report_path.write_text(
                f"<!-- report_sync_token: {current_token} -->\n# Report\n",
                encoding="utf-8",
            )
            fresh = build_report_sync_status(
                report_path=report_path,
                current_token=current_token,
                payload_path=payload_path,
                summary_path=summary_path,
                technical_report_path=technical_report_path,
            )
            self.assertEqual(fresh["status"], "up_to_date")

    def test_build_final_report_markdown_includes_token_and_required_sections(self):
        payload = {
            "meta": {
                "session_id": "i1",
                "date": "2026-04-11",
                "start_time": "09:36",
                "sport": "bike",
            },
            "session_row": {
                "session_id": "i1",
                "Fecha": "2026-04-11",
                "start_time": "09:36",
                "sport": "bike",
                "moving_min": "195.6",
                "duration_min": "207.8",
                "distance_km": "74.36",
                "elev_gain_m": "659",
                "elev_loss_m": "664",
                "hr_mean": "132",
                "hr_max": "176",
                "vt1_used": "139",
                "vt2_used": "156",
                "zones_source": "icu",
                "z1_pct": "71.8",
                "z2_pct": "13.2",
                "z3_pct": "15.0",
                "hr_p95": "167",
                "load": "157",
                "trimp": "253.7",
                "work_n_blocks": "2",
                "work_total_min": "36.8",
                "work_longest_min": "25.5",
                "work_blocks_min": "25.5;11.3",
                "work_avg_z3_pct": "80",
                "late_intensity": "0.0",
                "cardiac_drift_pct": "-2.7",
                "session_group": "endurance_hard",
            },
            "subjective_context": {"rpe": 6, "feel": 2, "notes_raw": "Salida larga con dos subidas duras"},
            "composite_context": {
                "subjective_coherence": {"subjective_coherence_state": "coherent", "subjective_coherence_score": 91.3},
                "durability_context": {"durability_hint": "fade_like", "confidence": "high"},
                "thermal_context": {"thermal_band": "high", "temperature_c": 22.5},
            },
            "terrain_fit_context": {"climb_count": 2, "climb_gain_m": 420, "climb_time_min": 31.2},
            "analysis_only_context": {"coach_metrics": {"session_rpe": 1173, "icu_intensity_pct": 67.3}},
            "context": {
                "sleep": {
                    "polar_sleep_duration_min": "425",
                    "polar_sleep_score": "78",
                    "polar_efficiency_pct": "93.4",
                    "polar_night_rmssd": "46",
                },
                "final": {
                    "RMSSD_stable": "42.35",
                    "residual_z": "2.62",
                    "gate_badge": "ÁMBAR+++",
                    "Action": "Z2_O_TEMPO_SUAVE",
                    "baseline60_degraded": "True",
                },
                "sessions_day": {
                    "load_day": "157",
                    "load_3d": "144",
                    "load_7d": "331",
                    "work_7d_sum": "69.8",
                    "z3_7d_sum": "12.6",
                },
                "sessions_metadata": {"training_audit": {}},
            },
            "narrative_targets": {
                "final_reason_rendered": {
                    "enabled": True,
                    "reporting_mode": "gate_first",
                    "gate_readout": "`gate_badge = ÁMBAR+++` y `Action = Z2_O_TEMPO_SUAVE`",
                    "reason_items": [
                        {"line": "- `intensity_clustering` (`intensity_clustering_flag=1`): 1 día intenso en los últimos 3"}
                    ],
                    "action_readout": "`has_action_constraint = false` -> no hay restriccion de accion activa; la cautela existe, pero no hay veto adicional.",
                    "baseline_readout": "`baseline60_degraded = true` -> usar como rebaja de precision del contexto, no como veto operativo por si solo.",
                }
            },
            "rr_analysis_summary": {},
        }
        summary = {
            "session_cost_model": {"usable": True, "coste_dominante": "cardiometabolico"},
            "duration_consistency": "OK",
            "hr_source": "FIT",
            "dfa_gate": {"state": "DFA_OK"},
            "hr_at_075": {"usable": False},
            "hr_at_075_crossing": {"hr_at_075_crossing": 158.5, "confidence": "low"},
            "dfa_alpha1": {"median": 1.471, "pct_below_075": 15.6},
            "alpha1_median_by_hr_zone": {
                "alpha1_med_z1_hr": 1.082,
                "alpha1_med_z2_hr": 0.913,
                "alpha1_med_z3_hr": 0.478,
            },
            "rmssd_1min": {"p50": 2.7},
            "rmssd_5min": {"p50": 3.12},
            "rr_unavailable": False,
        }
        report = build_final_report_markdown(payload, summary, "abc123def4567890")
        self.assertIn("<!-- report_sync_token: abc123def4567890 -->", report)
        self.assertIn("## Fuentes", report)
        self.assertIn("## Contexto de recuperación y carga", report)
        self.assertIn("## Qué Puede Aportar", report)
        self.assertIn("## Qué Puede Restar", report)
        self.assertIn("## Balance Neto", report)
        self.assertIn("## RR", report)
        self.assertIn("## Alpha1 por zona de FC", report)
        self.assertIn("RMSSD 1 min p50", report)
        self.assertIn("DFA-alpha1 mediana", report)
        self.assertEqual(report.count("HR estimada en `α1=0.75`"), 0)
        self.assertIn("| Z3 | `0.478` | `sí` |", report)
        self.assertIn("work_blocks_min = 25.5 ; 11.3", report)
        self.assertIn("asimetría clara entre bloques", report)
        self.assertIn("## Advertencias", report)
        self.assertIn("## Conclusión", report)
        self.assertIn("`intensity_clustering`", report)
        self.assertIn("| RR fina | Media |", report)
        self.assertLess(report.index("## Conclusión"), report.index("## Advertencias"))

    def test_build_final_report_markdown_uses_dynamic_climb_phrase_for_bike(self):
        payload = {
            "meta": {
                "session_id": "i_bike_three_climbs",
                "date": "2026-04-11",
                "start_time": "09:36",
                "sport": "bike",
            },
            "session_row": {
                "session_id": "i_bike_three_climbs",
                "Fecha": "2026-04-11",
                "start_time": "09:36",
                "sport": "bike",
                "moving_min": "195.6",
                "duration_min": "207.8",
                "distance_km": "74.36",
                "elev_gain_m": "659",
                "elev_loss_m": "664",
                "hr_mean": "132",
                "hr_max": "176",
                "vt1_used": "139",
                "vt2_used": "156",
                "zones_source": "icu",
                "z1_pct": "71.8",
                "z2_pct": "13.2",
                "z3_pct": "15.0",
                "hr_p95": "167",
                "load": "157",
                "trimp": "253.7",
                "work_n_blocks": "3",
                "work_total_min": "36.8",
                "work_longest_min": "25.5",
                "work_blocks_min": "25.5;11.3",
                "work_avg_z3_pct": "80",
                "late_intensity": "0.0",
                "cardiac_drift_pct": "-2.7",
                "session_group": "endurance_hard",
            },
            "subjective_context": {"rpe": 6, "feel": 2, "notes_raw": "Salida larga con tres subidas duras"},
            "composite_context": {
                "subjective_coherence": {"subjective_coherence_state": "coherent", "subjective_coherence_score": 91.3},
                "durability_context": {"durability_hint": "fade_like", "confidence": "high"},
                "thermal_context": {"thermal_band": "high", "temperature_c": 22.5},
            },
            "terrain_fit_context": {"climb_count": 3, "climb_gain_m": 420, "climb_time_min": 31.2},
            "analysis_only_context": {"coach_metrics": {"session_rpe": 1173, "icu_intensity_pct": 67.3}},
            "context": {
                "sleep": {
                    "polar_sleep_duration_min": "425",
                    "polar_sleep_score": "78",
                    "polar_efficiency_pct": "93.4",
                    "polar_night_rmssd": "46",
                },
                "final": {
                    "RMSSD_stable": "42.35",
                    "residual_z": "2.62",
                    "gate_badge": "ÁMBAR+++",
                    "Action": "Z2_O_TEMPO_SUAVE",
                    "baseline60_degraded": "True",
                },
                "sessions_day": {
                    "load_day": "157",
                    "load_3d": "144",
                    "load_7d": "331",
                    "work_7d_sum": "69.8",
                    "z3_7d_sum": "12.6",
                },
                "sessions_metadata": {"training_audit": {}},
            },
            "narrative_targets": {
                "final_reason_rendered": {
                    "enabled": True,
                    "reporting_mode": "gate_first",
                    "gate_readout": "`gate_badge = ÁMBAR+++` y `Action = Z2_O_TEMPO_SUAVE`",
                    "reason_items": [
                        {"line": "- `intensity_clustering` (`intensity_clustering_flag=1`): 1 día intenso en los últimos 3"}
                    ],
                    "action_readout": "`has_action_constraint = false` -> no hay restriccion de accion activa; la cautela existe, pero no hay veto adicional.",
                    "baseline_readout": "`baseline60_degraded = true` -> usar como rebaja de precision del contexto, no como veto operativo por si solo.",
                }
            },
            "rr_analysis_summary": {},
        }
        summary = {
            "session_cost_model": {"usable": True, "coste_dominante": "cardiometabolico"},
            "duration_consistency": "OK",
            "hr_source": "FIT",
            "dfa_gate": {"state": "DFA_OK"},
            "hr_at_075": {"usable": False},
            "hr_at_075_crossing": {"hr_at_075_crossing": 158.5, "confidence": "low"},
            "dfa_alpha1": {"median": 1.471, "pct_below_075": 15.6},
            "alpha1_median_by_hr_zone": {
                "alpha1_med_z1_hr": 1.082,
                "alpha1_med_z2_hr": 0.913,
                "alpha1_med_z3_hr": 0.478,
            },
            "rmssd_1min": {"p50": 2.7},
            "rmssd_5min": {"p50": 3.12},
            "rr_unavailable": False,
        }
        report = build_final_report_markdown(payload, summary, "abc123def4567890")
        self.assertIn("3 subidas", report)
        self.assertNotIn("dos subidas", report)

    def test_build_final_report_markdown_includes_same_day_sessions_context(self):
        payload = {
            "meta": {
                "session_id": "i_same_day_current",
                "date": "2026-04-14",
                "start_time": "14:08",
                "sport": "trail_run",
            },
            "session_row": {
                "session_id": "i_same_day_current",
                "Fecha": "2026-04-14",
                "start_time": "14:08",
                "sport": "trail_run",
                "moving_min": "93.7",
                "duration_min": "99.2",
                "distance_km": "15.1",
                "elev_gain_m": "800",
                "hr_mean": "148",
                "vt1_used": "140",
                "vt2_used": "158",
                "zones_source": "icu",
                "z2_pct": "42.0",
                "z3_pct": "34.0",
                "hr_p95": "170",
                "load": "100",
                "trimp": "187.4",
                "work_n_blocks": "5",
                "work_total_min": "47.7",
                "work_longest_min": "13.8",
                "work_blocks_min": "10.8;9.6;4.3;13.8;6.2",
                "work_avg_z3_pct": "66.0",
                "late_intensity": "5.0",
                "cardiac_drift_pct": "2.1",
                "speed_first_half": "6.03",
                "speed_second_half": "5.72",
                "session_group": "endurance_hard",
            },
            "subjective_context": {"rpe": 7, "feel": 3, "notes_raw": "Trail con movilidad previa"},
            "composite_context": {},
            "terrain_fit_context": {"climb_count": 3, "climb_gain_m": 800, "climb_time_min": 45.0},
            "analysis_only_context": {"coach_metrics": {"session_rpe": 655, "icu_intensity_pct": 54.2}},
            "context": {
                "sleep": {
                    "polar_sleep_duration_min": "425",
                    "polar_sleep_score": "78",
                    "polar_efficiency_pct": "93.4",
                    "polar_night_rmssd": "46",
                },
                "final": {
                    "RMSSD_stable": "42.35",
                    "residual_z": "2.62",
                    "gate_badge": "VERDE+++",
                    "Action": "INTENSIDAD_OK",
                    "baseline60_degraded": "False",
                    "reason_text": "VERDE, pero carga reciente pide prudencia",
                },
                "sessions_day": {
                    "load_day": "100",
                    "load_3d": "221",
                    "load_7d": "383",
                    "work_7d_sum": "50.3",
                    "z3_7d_sum": "34.7",
                },
                "sessions_metadata": {"training_audit": {}},
            },
            "narrative_targets": {
                "final_reason_rendered": {
                    "enabled": True,
                    "reporting_mode": "caution_first",
                    "gate_readout": "`gate_badge = VERDE+++` y `Action = INTENSIDAD_OK`",
                    "reason_items": [
                        {"line": "- `intensity_clustering` (`intensity_clustering_flag=1`): 1 día intenso en los últimos 3"}
                    ],
                    "action_readout": "`has_action_constraint = false` -> no hay restriccion de accion activa; la cautela existe, pero no hay veto adicional.",
                    "baseline_readout": "`baseline60_degraded = false` -> no rebaja adicional de precision del contexto.",
                }
            },
            "rr_analysis_summary": {},
        }
        summary = {
            "session_cost_model": {"usable": True, "coste_dominante": "cardiometabolico"},
            "duration_consistency": "OK",
            "hr_source": "FIT",
            "dfa_gate": {"state": "DFA_OK"},
            "hr_at_075": {"usable": False},
            "hr_at_075_crossing": {"hr_at_075_crossing": None, "confidence": None},
            "dfa_alpha1": {"median": 1.215, "pct_below_075": 12.3},
            "alpha1_median_by_hr_zone": {
                "alpha1_med_z1_hr": 1.215,
                "alpha1_med_z2_hr": 0.955,
                "alpha1_med_z3_hr": 0.495,
            },
            "rmssd_1min": {"p50": 3.1},
            "rmssd_5min": {"p50": 3.7},
            "rr_unavailable": False,
        }
        with TemporaryDirectory() as tmp:
            tmpdir = Path(tmp)
            sessions_csv = tmpdir / "ENDURANCE_HRV_sessions.csv"
            sessions_csv.write_text(
                "\n".join(
                    [
                        "session_id,Fecha,start_time,sport,moving_min,session_group,load,work_total_min,elev_gain_m",
                        "i_same_day_early,2026-04-14,09:33,mobility,53.2,mobility,9,0,0",
                        "i_same_day_current,2026-04-14,14:08,trail_run,93.7,endurance_hard,100,47.7,800",
                        "i_same_day_late,2026-04-14,17:40,walk,25.0,recovery,5,0,0",
                    ]
                ),
                encoding="utf-8",
            )
            with patch("analysis.session_analysis_pipeline.DEFAULT_SESSIONS_CSV", sessions_csv):
                report = build_final_report_markdown(payload, summary, "abc123def4567890")

        self.assertIn("## Sesiones del mismo dia", report)
        self.assertIn("| 09:33 | mobility | 53.2 min | antes | mobility |", report)
        self.assertIn("| 17:40 | walk | 25.0 min | despues | recovery |", report)

    def test_build_final_report_markdown_omits_same_day_header_when_empty(self):
        payload = {
            "meta": {
                "session_id": "i_no_same_day",
                "date": "2026-04-15",
                "start_time": "14:08",
                "sport": "trail_run",
            },
            "session_row": {
                "session_id": "i_no_same_day",
                "Fecha": "2026-04-15",
                "start_time": "14:08",
                "sport": "trail_run",
                "moving_min": "93.7",
                "duration_min": "99.2",
                "distance_km": "15.1",
                "elev_gain_m": "800",
                "hr_mean": "148",
                "vt1_used": "140",
                "vt2_used": "158",
                "zones_source": "icu",
                "z2_pct": "42.0",
                "z3_pct": "34.0",
                "hr_p95": "170",
                "load": "100",
                "trimp": "187.4",
                "work_total_min": "47.7",
                "work_longest_min": "13.8",
                "work_blocks_min": "13.1 ; 10.3 ; 4.3 ; 13.8 ; 6.2",
                "speed_first_half": "6.03",
                "speed_second_half": "5.72",
                "route_id": "5857059",
            },
            "final": {
                "RMSSD_stable": "42.35",
                "residual_z": "2.62",
                "gate_badge": "VERDE+++",
                "Action": "INTENSIDAD_OK",
                "baseline60_degraded": "False",
            },
            "sessions_day": {
                "load_day": "157",
                "load_3d": "144",
                "load_7d": "331",
                "work_7d_sum": "69.8",
                "z3_7d_sum": "12.6",
            },
            "narrative_targets": {
                "final_reason_rendered": {
                    "enabled": True,
                    "reporting_mode": "caution_first",
                    "gate_readout": "`gate_badge = VERDE+++` y `Action = INTENSIDAD_OK`",
                    "reason_items": [],
                    "action_readout": "`has_action_constraint = false` -> no hay veto adicional.",
                    "baseline_readout": "`baseline60_degraded = false` -> sin rebaja de precision del contexto.",
                }
            },
            "rr_analysis_summary": {},
        }
        summary = {
            "session_cost_model": {"usable": True, "coste_dominante": "cardiometabolico"},
            "duration_consistency": "OK",
            "hr_source": "FIT",
            "dfa_gate": {"state": "DFA_OK"},
            "hr_at_075": {"usable": False},
            "hr_at_075_crossing": {"hr_at_075_crossing": None, "confidence": None},
            "dfa_alpha1": {"median": 1.471, "pct_below_075": 15.6},
            "alpha1_median_by_hr_zone": {
                "alpha1_med_z1_hr": 1.082,
                "alpha1_med_z2_hr": 0.913,
                "alpha1_med_z3_hr": 0.478,
            },
            "rmssd_1min": {"p50": 2.7},
            "rmssd_5min": {"p50": 3.12},
            "rr_unavailable": False,
        }
        with TemporaryDirectory() as tmp:
            tmpdir = Path(tmp)
            sessions_csv = tmpdir / "ENDURANCE_HRV_sessions.csv"
            sessions_csv.write_text(
                "\n".join(
                    [
                        "session_id,Fecha,start_time,sport,moving_min,session_group,load,work_total_min,elev_gain_m",
                        "i_no_same_day_prev,2026-04-14,09:33,mobility,53.2,mobility,9,0,0",
                    ]
                ),
                encoding="utf-8",
            )
            with patch("analysis.session_analysis_pipeline.DEFAULT_SESSIONS_CSV", sessions_csv):
                report = build_final_report_markdown(payload, summary, "abc123def4567890")

        self.assertNotIn("## Sesiones del mismo dia", report)
        self.assertNotIn("| Hora | Deporte | Duración | Relación | Grupo |", report)

    def test_build_final_report_markdown_includes_weekly_distribution_context(self):
        payload = {
            "meta": {
                "session_id": "i_same_day_current",
                "date": "2026-04-14",
                "start_time": "14:08",
                "sport": "trail_run",
            },
            "session_row": {
                "session_id": "i_same_day_current",
                "Fecha": "2026-04-14",
                "start_time": "14:08",
                "sport": "trail_run",
                "moving_min": "93.7",
                "duration_min": "99.2",
                "distance_km": "15.1",
                "elev_gain_m": "800",
                "hr_mean": "148",
                "vt1_used": "140",
                "vt2_used": "158",
                "zones_source": "icu",
                "z2_pct": "42.0",
                "z3_pct": "34.0",
                "hr_p95": "170",
                "load": "100",
                "trimp": "187.4",
                "work_n_blocks": "5",
                "work_total_min": "47.7",
                "work_longest_min": "13.8",
                "work_blocks_min": "10.8;9.6;4.3;13.8;6.2",
                "work_avg_z3_pct": "66.0",
                "late_intensity": "5.0",
                "cardiac_drift_pct": "2.1",
                "speed_first_half": "6.03",
                "speed_second_half": "5.72",
                "session_group": "endurance_hard",
            },
            "subjective_context": {"rpe": 7, "feel": 3, "notes_raw": "Trail con movilidad previa"},
            "composite_context": {},
            "terrain_fit_context": {"climb_count": 3, "climb_gain_m": 800, "climb_time_min": 45.0},
            "analysis_only_context": {"coach_metrics": {"session_rpe": 655, "icu_intensity_pct": 54.2}},
            "context": {
                "sleep": {
                    "polar_sleep_duration_min": "425",
                    "polar_sleep_score": "78",
                    "polar_efficiency_pct": "93.4",
                    "polar_night_rmssd": "46",
                },
                "final": {
                    "RMSSD_stable": "42.35",
                    "residual_z": "2.62",
                    "gate_badge": "VERDE+++",
                    "Action": "INTENSIDAD_OK",
                    "baseline60_degraded": "False",
                    "reason_text": "VERDE, pero carga reciente pide prudencia",
                },
                "sessions_day": {
                    "load_day": "100",
                    "load_3d": "221",
                    "load_7d": "383",
                    "work_7d_sum": "50.3",
                    "z3_7d_sum": "34.7",
                },
                "sessions_metadata": {"training_audit": {}},
            },
            "narrative_targets": {
                "final_reason_rendered": {
                    "enabled": True,
                    "reporting_mode": "caution_first",
                    "gate_readout": "`gate_badge = VERDE+++` y `Action = INTENSIDAD_OK`",
                    "reason_items": [
                        {"line": "- `intensity_clustering` (`intensity_clustering_flag=1`): 1 día intenso en los últimos 3"}
                    ],
                    "action_readout": "`has_action_constraint = false` -> no hay restriccion de accion activa; la cautela existe, pero no hay veto adicional.",
                    "baseline_readout": "`baseline60_degraded = false` -> no rebaja adicional de precision del contexto.",
                }
            },
            "rr_analysis_summary": {},
        }
        summary = {
            "session_cost_model": {"usable": True, "coste_dominante": "cardiometabolico"},
            "duration_consistency": "OK",
            "hr_source": "FIT",
            "dfa_gate": {"state": "DFA_OK"},
            "hr_at_075": {"usable": False},
            "hr_at_075_crossing": {"hr_at_075_crossing": None, "confidence": None},
            "dfa_alpha1": {"median": 1.215, "pct_below_075": 12.3},
            "alpha1_median_by_hr_zone": {
                "alpha1_med_z1_hr": 1.215,
                "alpha1_med_z2_hr": 0.955,
                "alpha1_med_z3_hr": 0.495,
            },
            "rmssd_1min": {"p50": 3.1},
            "rmssd_5min": {"p50": 3.7},
            "rr_unavailable": False,
        }
        with TemporaryDirectory() as tmp:
            tmpdir = Path(tmp)
            sessions_csv = tmpdir / "ENDURANCE_HRV_sessions.csv"
            sessions_csv.write_text(
                "\n".join(
                    [
                        "session_id,Fecha,start_time,sport,moving_min,session_group,load,work_total_min,elev_gain_m",
                        "i_same_day_early,2026-04-14,09:33,mobility,53.2,mobility,9,0,0",
                        "i_same_day_current,2026-04-14,14:08,trail_run,93.7,endurance_hard,100,47.7,800",
                    ]
                ),
                encoding="utf-8",
            )
            weekly_csv = tmpdir / "ENDURANCE_HRV_intensity_distribution_weekly.csv"
            weekly_csv.write_text(
                "\n".join(
                    [
                        "window_start,window_end,sport,n_sessions_total,n_sessions_usable,total_duration_min,z1_total_min,z2_total_min,z3_total_min,z1_pct_weighted,z2_pct_weighted,z3_pct_weighted,work_total_min,work_n_blocks,work_longest_min,work_avg_z3_pct_weighted,zones_source_mix,intensity_category_mix,distribution_pattern,distribution_confidence,distribution_notes",
                        "2026-04-14,2026-04-20,trail_run,2,2,177.5,130.9,42.9,3.4,73.9,24.2,1.9,43.8,4,15.7,5.0,icu=2,easy=1;work_steady=1,pyramidal,moderate,minimum_weekly_support",
                    ]
                ),
                encoding="utf-8",
            )
            with patch("analysis.session_analysis_pipeline.DEFAULT_SESSIONS_CSV", sessions_csv), patch(
                "analysis.session_analysis_pipeline.DEFAULT_INTENSITY_DISTRIBUTION_WEEKLY_CSV", weekly_csv
            ):
                report = build_final_report_markdown(payload, summary, "abc123def4567890")

        self.assertIn("### Distribución semanal", report)
        self.assertIn("`pyramidal`", report)
        self.assertIn("Z1 `73.9%`", report)
        self.assertIn("Z3 `1.9%`", report)
        self.assertIn("La velocidad cayó de 6.03 km/h a 5.72 km/h", report)

    def test_build_final_report_markdown_includes_road_fade_context(self):
        payload = {
            "meta": {
                "session_id": "i_road_current",
                "date": "2026-04-13",
                "start_time": "08:10",
                "sport": "road_run",
            },
            "session_row": {
                "session_id": "i_road_current",
                "Fecha": "2026-04-13",
                "start_time": "08:10",
                "sport": "road_run",
                "moving_min": "72.0",
                "duration_min": "75.5",
                "distance_km": "13.4",
                "elev_gain_m": "82",
                "hr_mean": "146",
                "vt1_used": "140",
                "vt2_used": "158",
                "zones_source": "icu",
                "z2_pct": "44.0",
                "z3_pct": "19.0",
                "hr_p95": "164",
                "load": "87",
                "trimp": "128.4",
                "work_n_blocks": "3",
                "work_total_min": "28.6",
                "work_longest_min": "12.2",
                "work_blocks_min": "12.2;9.1;7.3",
                "speed_first_half": "9.42",
                "speed_second_half": "8.88",
                "session_group": "tempo",
            },
            "subjective_context": {"rpe": 6, "feel": 3, "notes_raw": "Road con fade claro"},
            "composite_context": {},
            "terrain_fit_context": {},
            "analysis_only_context": {},
            "context": {
                "sleep": {
                    "polar_sleep_duration_min": "410",
                    "polar_sleep_score": "80",
                    "polar_efficiency_pct": "92.0",
                    "polar_night_rmssd": "44",
                },
                "final": {
                    "RMSSD_stable": "40.20",
                    "residual_z": "1.90",
                    "gate_badge": "VERDE+++",
                    "Action": "INTENSIDAD_OK",
                    "baseline60_degraded": "False",
                    "reason_text": "VERDE con margen",
                },
                "sessions_day": {
                    "load_day": "87",
                    "load_3d": "190",
                    "load_7d": "315",
                    "work_7d_sum": "61.5",
                    "z3_7d_sum": "21.2",
                },
                "sessions_metadata": {"training_audit": {}},
            },
            "narrative_targets": {
                "final_reason_rendered": {
                    "enabled": True,
                    "reporting_mode": "caution_first",
                    "gate_readout": "`gate_badge = VERDE+++` y `Action = INTENSIDAD_OK`",
                    "reason_items": [],
                    "action_readout": "`has_action_constraint = false` -> no hay veto adicional.",
                    "baseline_readout": "`baseline60_degraded = false` -> sin rebaja adicional de precisión del contexto.",
                }
            },
            "rr_analysis_summary": {},
        }
        summary = {
            "session_cost_model": {"usable": True, "coste_dominante": "cardiometabolico"},
            "duration_consistency": "OK",
            "hr_source": "FIT",
            "dfa_gate": {"state": "DFA_OK"},
            "hr_at_075": {"usable": False},
            "hr_at_075_crossing": {"hr_at_075_crossing": None, "confidence": None},
            "dfa_alpha1": {"median": 1.102, "pct_below_075": 18.7},
            "alpha1_median_by_hr_zone": {
                "alpha1_med_z1_hr": 1.101,
                "alpha1_med_z2_hr": 0.884,
                "alpha1_med_z3_hr": 0.531,
            },
            "rmssd_1min": {"p50": 2.9},
            "rmssd_5min": {"p50": 3.4},
            "rr_unavailable": False,
        }
        report = build_final_report_markdown(payload, summary, "abc123def4567890")
        self.assertIn("En carretera eso suele significar que el pacing", report)
        self.assertIn("La velocidad cayó de 9.42 km/h a 8.88 km/h", report)

    def test_build_final_report_markdown_includes_hike_fade_context(self):
        payload = {
            "meta": {
                "session_id": "i_hike_current",
                "date": "2025-09-21",
                "start_time": "10:41",
                "sport": "hike",
            },
            "session_row": {
                "session_id": "i_hike_current",
                "Fecha": "2025-09-21",
                "start_time": "10:41",
                "sport": "hike",
                "moving_min": "82.0",
                "duration_min": "85.5",
                "distance_km": "9.8",
                "elev_gain_m": "380",
                "hr_mean": "131",
                "vt1_used": "135",
                "vt2_used": "150",
                "zones_source": "icu",
                "z2_pct": "41.0",
                "z3_pct": "12.0",
                "hr_p95": "148",
                "load": "64",
                "trimp": "110.3",
                "work_n_blocks": "2",
                "work_total_min": "21.7",
                "work_longest_min": "12.6",
                "work_blocks_min": "12.6;9.1",
                "speed_first_half": "3.97",
                "speed_second_half": "3.07",
                "session_group": "endurance",
            },
            "subjective_context": {"rpe": 4, "feel": 3, "notes_raw": "Marcha con bajada de ritmo"},
            "composite_context": {},
            "terrain_fit_context": {},
            "analysis_only_context": {},
            "context": {
                "sleep": {
                    "polar_sleep_duration_min": "440",
                    "polar_sleep_score": "82",
                    "polar_efficiency_pct": "94.0",
                    "polar_night_rmssd": "48",
                },
                "final": {
                    "RMSSD_stable": "43.10",
                    "residual_z": "1.25",
                    "gate_badge": "VERDE+++",
                    "Action": "RECOVERY_OK",
                    "baseline60_degraded": "False",
                    "reason_text": "VERDE",
                },
                "sessions_day": {
                    "load_day": "64",
                    "load_3d": "120",
                    "load_7d": "280",
                    "work_7d_sum": "38.9",
                    "z3_7d_sum": "10.1",
                },
                "sessions_metadata": {"training_audit": {}},
            },
            "narrative_targets": {
                "final_reason_rendered": {
                    "enabled": True,
                    "reporting_mode": "caution_first",
                    "gate_readout": "`gate_badge = VERDE+++` y `Action = RECOVERY_OK`",
                    "reason_items": [],
                    "action_readout": "`has_action_constraint = false` -> no hay veto adicional.",
                    "baseline_readout": "`baseline60_degraded = false` -> sin rebaja adicional de precisión del contexto.",
                }
            },
            "rr_analysis_summary": {},
        }
        summary = {
            "session_cost_model": {"usable": True, "coste_dominante": "cardiometabolico"},
            "duration_consistency": "OK",
            "hr_source": "FIT",
            "dfa_gate": {"state": "DFA_OK"},
            "hr_at_075": {"usable": False},
            "hr_at_075_crossing": {"hr_at_075_crossing": None, "confidence": None},
            "dfa_alpha1": {"median": 1.021, "pct_below_075": 11.4},
            "alpha1_median_by_hr_zone": {
                "alpha1_med_z1_hr": 1.120,
                "alpha1_med_z2_hr": 0.942,
                "alpha1_med_z3_hr": 0.560,
            },
            "rmssd_1min": {"p50": 3.0},
            "rmssd_5min": {"p50": 3.5},
            "rr_unavailable": False,
        }
        report = build_final_report_markdown(payload, summary, "abc123def4567890")
        self.assertIn("En marcha eso suele significar que la continuidad de paso", report)
        self.assertIn("La velocidad cayó de 3.97 km/h a 3.07 km/h", report)

    def test_build_final_report_markdown_includes_route_history_comparator(self):
        payload = {
            "meta": {
                "session_id": "i_route_current",
                "date": "2026-04-14",
                "start_time": "14:08",
                "sport": "trail_run",
            },
            "session_row": {
                "session_id": "i_route_current",
                "Fecha": "2026-04-14",
                "start_time": "14:08",
                "sport": "trail_run",
                "moving_min": "93.7",
                "duration_min": "99.2",
                "distance_km": "15.1",
                "elev_gain_m": "800",
                "hr_mean": "148",
                "vt1_used": "140",
                "vt2_used": "158",
                "zones_source": "icu",
                "z2_pct": "42.0",
                "z3_pct": "34.0",
                "hr_p95": "170",
                "load": "100",
                "trimp": "187.4",
                "work_n_blocks": "5",
                "work_total_min": "47.7",
                "work_longest_min": "13.8",
                "work_blocks_min": "10.8;9.6;4.3;13.8;6.2",
                "work_avg_z3_pct": "66.0",
                "late_intensity": "5.0",
                "cardiac_drift_pct": "2.1",
                "session_group": "endurance_hard",
            },
            "subjective_context": {"rpe": 7, "feel": 3, "notes_raw": "Trail de ruta repetida"},
            "composite_context": {},
            "terrain_fit_context": {"climb_count": 3, "climb_gain_m": 800, "climb_time_min": 45.0},
            "analysis_only_context": {
                "coach_metrics": {"session_rpe": 655, "icu_intensity_pct": 54.2},
                "route_context": {"route_id": 42},
                "terrain_fit_context": {"climb_gain_m": 800, "climb_time_min": 45.0},
            },
            "context": {
                "sleep": {
                    "polar_sleep_duration_min": "425",
                    "polar_sleep_score": "78",
                    "polar_efficiency_pct": "93.4",
                    "polar_night_rmssd": "46",
                },
                "final": {
                    "RMSSD_stable": "42.35",
                    "residual_z": "2.62",
                    "gate_badge": "VERDE+++",
                    "Action": "INTENSIDAD_OK",
                    "baseline60_degraded": "False",
                    "reason_text": "VERDE, pero carga reciente pide prudencia",
                },
                "sessions_day": {
                    "load_day": "100",
                    "load_3d": "221",
                    "load_7d": "383",
                    "work_7d_sum": "50.3",
                    "z3_7d_sum": "34.7",
                },
                "sessions_metadata": {"training_audit": {}},
            },
            "narrative_targets": {
                "final_reason_rendered": {
                    "enabled": True,
                    "reporting_mode": "caution_first",
                    "gate_readout": "`gate_badge = VERDE+++` y `Action = INTENSIDAD_OK`",
                    "reason_items": [
                        {"line": "- `intensity_clustering` (`intensity_clustering_flag=1`): 1 día intenso en los últimos 3"}
                    ],
                    "action_readout": "`has_action_constraint = false` -> no hay restriccion de accion activa; la cautela existe, pero no hay veto adicional.",
                    "baseline_readout": "`baseline60_degraded = false` -> no rebaja adicional de precision del contexto.",
                }
            },
            "rr_analysis_summary": {},
        }
        summary = {
            "session_cost_model": {"usable": True, "coste_dominante": "cardiometabolico"},
            "duration_consistency": "OK",
            "hr_source": "FIT",
            "dfa_gate": {"state": "DFA_OK"},
            "hr_at_075": {"usable": False},
            "hr_at_075_crossing": {"hr_at_075_crossing": None, "confidence": None},
            "dfa_alpha1": {"median": 1.215, "pct_below_075": 12.3},
            "alpha1_median_by_hr_zone": {
                "alpha1_med_z1_hr": 1.215,
                "alpha1_med_z2_hr": 0.955,
                "alpha1_med_z3_hr": 0.495,
            },
            "rmssd_1min": {"p50": 3.1},
            "rmssd_5min": {"p50": 3.7},
            "rr_unavailable": False,
        }
        with TemporaryDirectory() as tmp:
            tmpdir = Path(tmp)
            reports_root = tmpdir / "reports"
            previous_payload_path = (
                reports_root
                / "2026"
                / "04"
                / "2026-04-10_14-00_trail_run_i_route_prev"
                / "artifacts"
                / "session_payload.json"
            )
            previous_payload_path.parent.mkdir(parents=True, exist_ok=True)
            previous_payload_path.write_text(
                json.dumps(
                    {
                        "meta": {
                            "session_id": "i_route_prev",
                            "date": "2026-04-10",
                            "start_time": "14:00",
                            "sport": "trail_run",
                        },
                        "session_row": {
                            "session_id": "i_route_prev",
                            "Fecha": "2026-04-10",
                            "start_time": "14:00",
                            "sport": "trail_run",
                            "work_total_min": "41.2",
                            "load": "92",
                            "cardiac_drift_pct": "0.5",
                        },
                        "analysis_only_context": {"route_context": {"route_id": 42}},
                        "terrain_fit_context": {"climb_gain_m": 790, "climb_time_min": 44.0},
                    }
                ),
                encoding="utf-8",
            )
            with patch("analysis.session_analysis_pipeline.DEFAULT_REPORTS_DIR", reports_root):
                report = build_final_report_markdown(payload, summary, "abc123def4567890")

        self.assertIn("### Comparación de ruta", report)
        self.assertIn("route_id=42", report)
        self.assertIn("i_route_prev", report)
        self.assertIn("work_total_min", report)

    def test_build_best_block_comparator_prefers_same_family_and_work_shape(self):
        current = _session_row(
            sport="bike",
            session_group="endurance_hard",
            load="157",
            work_total_min="36.8",
        )
        recent_rows = [
            _session_row(
                session_id="i_old_bike_easy",
                Fecha="2026-04-08",
                sport="bike",
                session_group="endurance_hard",
                load="61",
                work_total_min="0",
            ),
            _session_row(
                session_id="i_trail_hard",
                Fecha="2026-04-09",
                sport="trail_run",
                session_group="endurance_hard",
                load="150",
                work_total_min="40",
            ),
            _session_row(
                session_id="i_bike_hard",
                Fecha="2026-04-06",
                sport="bike",
                session_group="endurance_hard",
                load="145",
                work_total_min="34",
            ),
        ]

        comparator = _build_best_block_comparator("bike", current, recent_rows)

        self.assertIsNotNone(comparator)
        self.assertIn("`i_bike_hard`", comparator)
        self.assertIn("misma familia de deporte", comparator)

    def test_build_best_block_comparator_refuses_noncomparable_same_family_gap(self):
        current = _session_row(
            sport="bike",
            session_group="endurance_hard",
            load="157",
            work_total_min="36.8",
        )
        recent_rows = [
            _session_row(
                session_id="i_trail_hard",
                Fecha="2026-04-09",
                sport="trail_run",
                session_group="endurance_hard",
                load="150",
                work_total_min="40",
            ),
        ]

        comparator = _build_best_block_comparator("bike", current, recent_rows)

        self.assertIsNotNone(comparator)
        self.assertIn("No hay un comparador de la misma familia", comparator)

    def test_build_same_day_sessions_lists_other_sessions_with_order(self):
        with TemporaryDirectory() as tmp:
            tmpdir = Path(tmp)
            sessions_csv = tmpdir / "ENDURANCE_HRV_sessions.csv"
            sessions_csv.write_text(
                "\n".join(
                    [
                        "session_id,Fecha,start_time,sport,moving_min,session_group",
                        "i_same_day_early,2026-04-14,09:33,mobility,53.2,mobility",
                        "i_same_day_current,2026-04-14,14:08,trail_run,93.7,endurance_hard",
                        "i_same_day_late,2026-04-14,17:40,walk,25.0,recovery",
                        "i_other_day,2026-04-13,10:00,bike,90.0,endurance_hard",
                    ]
                ),
                encoding="utf-8",
            )
            with patch("analysis.session_analysis_pipeline.DEFAULT_SESSIONS_CSV", sessions_csv):
                rows = _build_same_day_sessions(
                    {
                        "session_id": "i_same_day_current",
                        "Fecha": "2026-04-14",
                        "start_time": "14:08",
                    }
                )

        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["start_time"], "09:33")
        self.assertEqual(rows[0]["relation"], "antes")
        self.assertEqual(rows[1]["start_time"], "17:40")
        self.assertEqual(rows[1]["relation"], "despues")

    def test_compute_sport_percentiles_highlights_most_informative_metric(self):
        with TemporaryDirectory() as tmp:
            tmpdir = Path(tmp)
            sessions_csv = tmpdir / "ENDURANCE_HRV_sessions.csv"
            sessions_csv.write_text(
                "\n".join(
                    [
                        "session_id,Fecha,start_time,sport,work_total_min,load,z3_total_min,z3_pct",
                        "i1,2026-04-01,09:00,trail_run,10,20,3,5",
                        "i2,2026-04-02,09:00,trail_run,12,25,4,6",
                        "i3,2026-04-03,09:00,trail_run,14,30,5,7",
                        "i4,2026-04-04,09:00,trail_run,16,35,6,8",
                        "i5,2026-04-05,09:00,trail_run,18,40,7,9",
                        "i_current,2026-04-14,14:08,trail_run,47.7,100,34.7,34.0",
                    ]
                ),
                encoding="utf-8",
            )
            with patch("analysis.session_analysis_pipeline.DEFAULT_SESSIONS_CSV", sessions_csv):
                result = _compute_sport_percentiles(
                    {
                        "session_id": "i_current",
                        "sport": "trail_run",
                        "work_total_min": "47.7",
                        "load": "100",
                        "z3_total_min": "34.7",
                        "z3_pct": "34.0",
                    }
                )

        self.assertIsNotNone(result)
        self.assertEqual(result["highlight"]["label"], "work_total_min")
        self.assertEqual(result["highlight"]["percentile"], 100.0)
        self.assertEqual(result["highlight"]["count"], 5)

    def test_compute_sport_percentiles_prefers_work_total_when_close_but_switches_when_gap_is_clear(self):
        with TemporaryDirectory() as tmp:
            tmpdir = Path(tmp)
            sessions_csv = tmpdir / "ENDURANCE_HRV_sessions.csv"
            sessions_csv.write_text(
                "\n".join(
                    [
                        "session_id,Fecha,start_time,sport,work_total_min,load,z3_total_min,z3_pct",
                        "t1,2026-04-01,09:00,trail_run,10,20,3,5",
                        "t2,2026-04-02,09:00,trail_run,12,25,4,6",
                        "t3,2026-04-03,09:00,trail_run,14,30,5,7",
                        "t4,2026-04-04,09:00,trail_run,16,35,6,8",
                        "t5,2026-04-05,09:00,trail_run,18,40,7,9",
                        "t_current,2026-04-14,14:08,trail_run,47.7,100,34.7,34.0",
                        "b1,2026-04-01,09:00,bike,30,20,3,5",
                        "b2,2026-04-02,09:00,bike,34,22,4,6",
                        "b3,2026-04-03,09:00,bike,36,24,5,7",
                        "b4,2026-04-04,09:00,bike,38,26,6,8",
                        "b5,2026-04-05,09:00,bike,40,28,7,9",
                        "b_current,2026-04-11,09:36,bike,36.8,157,29.3,15.0",
                    ]
                ),
                encoding="utf-8",
            )
            with patch("analysis.session_analysis_pipeline.DEFAULT_SESSIONS_CSV", sessions_csv):
                trail = _compute_sport_percentiles(
                    {
                        "session_id": "t_current",
                        "sport": "trail_run",
                        "work_total_min": "47.7",
                        "load": "100",
                        "z3_total_min": "34.7",
                        "z3_pct": "34.0",
                    }
                )
                bike = _compute_sport_percentiles(
                    {
                        "session_id": "b_current",
                        "sport": "bike",
                        "work_total_min": "36.8",
                        "load": "157",
                        "z3_total_min": "29.3",
                        "z3_pct": "15.0",
                    }
                )

        self.assertEqual(trail["highlight"]["label"], "work_total_min")
        self.assertEqual(bike["highlight"]["label"], "load")

    def test_build_weekly_intensity_distribution_matches_session_week(self):
        with TemporaryDirectory() as tmp:
            tmpdir = Path(tmp)
            weekly_csv = tmpdir / "ENDURANCE_HRV_intensity_distribution_weekly.csv"
            weekly_csv.write_text(
                "\n".join(
                    [
                        "window_start,window_end,sport,n_sessions_total,n_sessions_usable,total_duration_min,z1_total_min,z2_total_min,z3_total_min,z1_pct_weighted,z2_pct_weighted,z3_pct_weighted,work_total_min,work_n_blocks,work_longest_min,work_avg_z3_pct_weighted,zones_source_mix,intensity_category_mix,distribution_pattern,distribution_confidence,distribution_notes",
                        "2026-04-14,2026-04-20,trail_run,2,2,177.5,130.9,42.9,3.4,73.9,24.2,1.9,43.8,4,15.7,5.0,icu=2,easy=1;work_steady=1,pyramidal,moderate,minimum_weekly_support",
                    ]
                ),
                encoding="utf-8",
            )
            with patch("analysis.session_analysis_pipeline.DEFAULT_INTENSITY_DISTRIBUTION_WEEKLY_CSV", weekly_csv):
                result = _build_weekly_intensity_distribution(
                    {
                        "sport": "trail_run",
                        "Fecha": "2026-04-14",
                    }
                )

        self.assertIsNotNone(result)
        self.assertTrue(result["show"])
        self.assertEqual(result["row"]["distribution_pattern"], "pyramidal")
        self.assertEqual(result["row"]["distribution_confidence"], "moderate")

    def test_build_route_history_comparator_uses_previous_same_route_payload(self):
        with TemporaryDirectory() as tmp:
            tmpdir = Path(tmp)
            reports_root = tmpdir / "reports"
            previous_payload_path = (
                reports_root
                / "2026"
                / "04"
                / "2026-04-10_14-00_trail_run_i_route_prev"
                / "artifacts"
                / "session_payload.json"
            )
            previous_payload_path.parent.mkdir(parents=True, exist_ok=True)
            previous_payload_path.write_text(
                json.dumps(
                    {
                        "meta": {
                            "session_id": "i_route_prev",
                            "date": "2026-04-10",
                            "start_time": "14:00",
                            "sport": "trail_run",
                        },
                        "session_row": {
                            "session_id": "i_route_prev",
                            "Fecha": "2026-04-10",
                            "start_time": "14:00",
                            "sport": "trail_run",
                            "work_total_min": "41.2",
                            "load": "92",
                            "cardiac_drift_pct": "0.5",
                        },
                        "analysis_only_context": {"route_context": {"route_id": 42}},
                        "terrain_fit_context": {"climb_gain_m": 790, "climb_time_min": 44.0},
                    }
                ),
                encoding="utf-8",
            )
            with patch("analysis.session_analysis_pipeline.DEFAULT_REPORTS_DIR", reports_root):
                result = _build_route_history_comparator(
                    {
                        "session_id": "i_route_current",
                        "Fecha": "2026-04-14",
                        "start_time": "14:08",
                        "sport": "trail_run",
                        "work_total_min": "47.7",
                        "load": "100",
                        "cardiac_drift_pct": "2.1",
                    },
                    {
                        "route_context": {"route_id": 42},
                        "terrain_fit_context": {"climb_gain_m": 800, "climb_time_min": 45.0},
                    },
                )

        self.assertIsNotNone(result)
        self.assertEqual(result["previous_session_id"], "i_route_prev")
        self.assertEqual(result["work_total_min_delta_pct"], "+15.8%")
        self.assertEqual(result["load_delta_pct"], "+8.7%")

    def test_build_route_history_comparator_falls_back_to_session_row_route_id(self):
        with TemporaryDirectory() as tmp:
            tmpdir = Path(tmp)
            reports_root = tmpdir / "reports"
            previous_payload_path = (
                reports_root
                / "2026"
                / "04"
                / "2026-04-10_14-00_trail_run_i_route_prev"
                / "artifacts"
                / "session_payload.json"
            )
            previous_payload_path.parent.mkdir(parents=True, exist_ok=True)
            previous_payload_path.write_text(
                json.dumps(
                    {
                        "meta": {
                            "session_id": "i_route_prev",
                            "date": "2026-04-10",
                            "start_time": "14:00",
                            "sport": "trail_run",
                        },
                        "session_row": {
                            "session_id": "i_route_prev",
                            "route_id": 42,
                            "Fecha": "2026-04-10",
                            "start_time": "14:00",
                            "sport": "trail_run",
                            "work_total_min": "41.2",
                            "load": "92",
                            "cardiac_drift_pct": "0.5",
                        },
                        "analysis_only_context": {"route_context": {}},
                        "terrain_fit_context": {"climb_gain_m": 790, "climb_time_min": 44.0},
                    }
                ),
                encoding="utf-8",
            )
            with patch("analysis.session_analysis_pipeline.DEFAULT_REPORTS_DIR", reports_root):
                result = _build_route_history_comparator(
                    {
                        "session_id": "i_route_current",
                        "Fecha": "2026-04-14",
                        "start_time": "14:08",
                        "sport": "trail_run",
                        "route_id": "42",
                        "work_total_min": "47.7",
                        "load": "100",
                        "cardiac_drift_pct": "2.1",
                    },
                    {
                        "route_context": {},
                        "terrain_fit_context": {"climb_gain_m": 800, "climb_time_min": 45.0},
                    },
                )

        self.assertIsNotNone(result)
        self.assertEqual(result["route_id"], 42)
        self.assertEqual(result["previous_session_id"], "i_route_prev")

    def test_write_managed_final_report_preserves_legacy_once(self):
        with TemporaryDirectory() as tmp:
            tmpdir = Path(tmp)
            report_path = tmpdir / "report.md"
            report_path.write_text("# Legacy report\n", encoding="utf-8")
            backup = write_managed_final_report(
                report_path,
                "<!-- report_sync_token: abc123def4567890 -->\n# New report\n",
            )
            self.assertEqual(backup, tmpdir / "report.legacy.md")
            self.assertTrue((tmpdir / "report.legacy.md").exists())
            self.assertIn("Legacy report", (tmpdir / "report.legacy.md").read_text(encoding="utf-8"))
            self.assertIn("abc123def4567890", report_path.read_text(encoding="utf-8"))

    def test_normalize_sport_keeps_road_family_separate_from_trail(self):
        self.assertEqual(normalize_sport("road_run"), "road")
        self.assertEqual(normalize_sport("virtual_run"), "road")

    def test_infer_sport_family_falls_back_to_session_row(self):
        summary = {
            "session_meta": {},
            "session_row": {"sport": "road_run"},
        }
        self.assertEqual(infer_sport_family(summary), "road")

    def test_rr_sections_hidden_when_rr_context_is_unavailable(self):
        summary = {
            "session_cost_model": {"session_id": "i1", "usable": True},
            "session_row": {"sport": "trail_run"},
            "rr_context": {"modifier": "unavailable", "interpretation": "RR no interpretable", "evidence": []},
            "final_cost_interpretation": {"note": "Sessions sugiere `mixto`; RR no fue interpretable"},
            "rr_unavailable": False,
        }
        self.assertFalse(rr_sections_visible(summary))
        report = render_report_markdown(summary)
        self.assertNotIn("## Key Metrics", report)
        self.assertNotIn("## RMSSD", report)

    def test_no_rr_summary_marks_cost_usable_and_builds_final_note(self):
        summary = _build_no_rr_summary(
            _session_row(sport="bike"),
            {"rr_error": "sin RR exportable"},
        )
        self.assertTrue(summary["rr_unavailable"])
        self.assertTrue(summary["session_cost_model"]["usable"])
        self.assertEqual(summary["rr_context"]["modifier"], "no_rr")
        self.assertIn("RR no disponible", summary["final_cost_interpretation"]["note"])

    def test_render_report_includes_structural_audit_sections(self):
        summary = {
            "session_cost_model": {"session_id": "i1", "usable": True},
            "session_row": {
                "sport": "road_run",
                "zones_source": "fallback",
                "session_group": "endurance_hard",
                "stream_dt_est": "",
                "cardiac_drift_pct": "",
            },
            "rr_context": {"modifier": "available", "interpretation": "RR usable", "evidence": []},
            "final_cost_interpretation": {"note": "Lectura base"},
            "sessions_metadata": {
                "training_audit": {
                    "signal_level": {
                        "sampling_ok": False,
                        "interpretability_limits": [
                            "stream_sampling_not_1hz",
                            "partial_aerobic_stream_coverage",
                        ],
                    },
                    "metric_level": {
                        "coaching_load": {"state": "contextual", "reasons": ["stream_sampling_not_1hz"]},
                        "zone_intensity": {"state": "contextual", "reasons": ["partial_aerobic_stream_coverage"]},
                        "cardiac_drift": {"state": "informational", "reasons": ["partial_aerobic_drift_coverage"]},
                    },
                },
            },
        }
        report = render_report_markdown(summary)
        self.assertIn("## Training Audit", report)
        self.assertIn("coaching_load_state: `contextual`", report)
        self.assertIn("## Dataset Audit Limits", report)
        self.assertIn("- session_affected: `True`", report)
        self.assertIn("## Session Audit Flags", report)
        self.assertIn("session_zones_fallback", report)
        self.assertIn("session_without_stream", report)

    def test_training_audit_helpers_support_nested_summary_layout(self):
        summary = {
            "sessions_metadata": {
                "training_audit": {
                    "signal_level": {
                        "sampling_ok": False,
                        "interpretability_limits": ["partial_aerobic_stream_coverage"],
                    },
                    "metric_level": {
                        "zone_intensity": {"state": "contextual", "reasons": ["partial_aerobic_stream_coverage"]},
                    },
                }
            },
            "session_row": {
                "sport": "road_run",
                "zones_source": "fallback",
                "stream_dt_est": "",
                "cardiac_drift_pct": "",
            },
        }
        self.assertEqual(summary_training_audit(summary)["metric_level"]["zone_intensity"]["state"], "contextual")
        self.assertEqual(training_audit_metric_state(summary, "zone_intensity"), "contextual")
        self.assertEqual(training_audit_dataset_limits(summary), ["partial_aerobic_stream_coverage"])
        self.assertTrue(training_audit_session_affected(summary))

    def test_session_report_evidence_uses_shared_helper_signals(self):
        summary = {
            "session_cost_model": {
                "session_id": "i2",
                "usable": True,
                "confidence_cardio": "medium",
                "confidence_mecanico": "medium",
            },
            "session_row": {
                "sport": "bike",
                "cardiac_drift_pct": "-30.3",
                "mechanics_source": "",
            },
        }
        evidence = session_report_evidence(summary)
        self.assertIn(("session", "cardiac_drift_pct = -30.3% (perfil descendente de FC; revisar pacing/perfil)"), evidence)
        self.assertIn(("confidence", "confidence_cardio = medium (base cardiometabolica parcial)"), evidence)
        self.assertIn(("confidence", "confidence_mecanico = medium (sin señal mecánica directa; proxy por relieve/bloques)"), evidence)

    def test_render_report_sanitizes_rr_error_and_keeps_dataset_limits_structural(self):
        summary = {
            "rr_unavailable": True,
            "rr_error": "GET https://x.test -> 503 Service Temporarily Unavailable\n<html>\n<body>down</body>\n</html>",
            "session_cost_model": {"session_id": "i1", "usable": True},
            "session_row": {
                "sport": "road_run",
                "zones_source": "icu",
                "session_group": "endurance_hard",
                "stream_dt_est": "1.0",
                "cardiac_drift_pct": "4.2",
            },
            "rr_context": {
                "modifier": "no_rr",
                "interpretation": "RR no disponible",
                "evidence": ["GET https://x.test -> 503 Service Temporarily Unavailable\n<html>\n<body>down</body>\n</html>"],
            },
            "final_cost_interpretation": {"note": "Lectura base"},
            "sessions_metadata": {
                "training_audit": {
                    "signal_level": {
                        "sampling_ok": True,
                        "interpretability_limits": ["partial_aerobic_stream_coverage"],
                    },
                    "metric_level": {
                        "coaching_load": {"state": "high", "reasons": []},
                        "zone_intensity": {"state": "high", "reasons": []},
                        "cardiac_drift": {"state": "high", "reasons": []},
                    },
                }
            },
        }
        report = render_report_markdown(summary)
        self.assertIn("- motivo: GET https://x.test -> 503 Service Temporarily Unavailable", report)
        self.assertNotIn("<html>", report)
        self.assertIn("## Dataset Audit Limits", report)
        self.assertIn("partial_aerobic_stream_coverage", report)
        self.assertIn("- session_affected: `False`", report)
        self.assertNotIn("## Session Audit Flags", report)

    def test_render_report_exposes_negative_drift_and_medium_mechanical_confidence_reason(self):
        summary = {
            "session_cost_model": {
                "session_id": "i2",
                "usable": True,
                "confidence_cardio": "high",
                "confidence_mecanico": "medium",
                "cardio_evidence": [],
                "mecanico_evidence": ["D+/h = 327", "bloques exigentes: total 36.0 min, max 14.0 min"],
            },
            "session_row": {
                "sport": "bike",
                "zones_source": "icu",
                "mechanics_source": "",
                "cardiac_drift_pct": "-30.3",
            },
            "rr_context": {"modifier": "no_rr", "interpretation": "RR no disponible", "evidence": []},
            "final_cost_interpretation": {"note": "Lectura base"},
        }
        report = render_report_markdown(summary)
        self.assertIn("cardiac_drift_pct = -30.3% (perfil descendente de FC; revisar pacing/perfil)", report)
        self.assertIn("confidence_mecanico = medium (sin señal mecánica directa; proxy por relieve/bloques)", report)

    def test_render_report_includes_ap02_mechanical_evidence_for_running(self):
        summary = {
            "session_cost_model": {
                "session_id": "i3",
                "usable": True,
                "confidence_cardio": "high",
                "confidence_mecanico": "high",
                "cardio_evidence": [],
                "mecanico_evidence": ["D+/h = 110", "D-/h = 110"],
            },
            "session_row": {
                "sport": "road_run",
                "zones_source": "icu",
                "run_power_available": "1",
                "run_power_mean": "228.9",
                "speed_first_half": "9.18",
                "speed_second_half": "9.39",
                "cadence_first_half": "84.1",
                "cadence_second_half": "86.1",
            },
            "rr_context": {"modifier": "no_rr", "interpretation": "RR no disponible", "evidence": []},
            "final_cost_interpretation": {"note": "Lectura base"},
        }
        report = render_report_markdown(summary)
        self.assertIn("run_power_mean = 228.9 W", report)
        self.assertIn("speed_first_half = 9.18 km/h, speed_second_half = 9.39 km/h (negative split)", report)
        self.assertIn("cadence_first_half = 84.1, cadence_second_half = 86.1 (↑)", report)

    def test_render_report_includes_terrain_context_when_available(self):
        summary = {
            "session_cost_model": {"session_id": "i4", "usable": True},
            "session_row": {
                "sport": "trail_run",
                "speed_first_half": "6.03",
                "speed_second_half": "5.72",
            },
            "rr_context": {"modifier": "no_rr", "interpretation": "RR no disponible", "evidence": []},
            "final_cost_interpretation": {"note": "Lectura base"},
            "terrain_context": {
                "source": "intervals_activity+icu_intervals",
                "gap_mean": 8.7,
                "gap_unit": "km/h",
                "gap_model": "STRAVA_RUN",
                "split_source": "icu_intervals",
                "split_count": 3,
                "split_coverage_pct": 100.0,
                "uphill_split_count": 1,
                "rolling_split_count": 1,
                "downhill_split_count": 1,
                "gap_uphill_mean": 8.5,
                "gap_rolling_mean": 8.7,
                "gap_downhill_mean": 9.1,
                "vam_uphill_mean": 450.0,
                "vam_uphill_max": 450.0,
                "vam_uphill_time_min": 7.0,
                "vam_uphill_split_count": 1,
                "vam_source": "icu_intervals_uphill_filtered",
            },
        }
        report = render_report_markdown(summary)
        self.assertIn("## Terrain Context", report)
        self.assertIn("gap_mean: `8.7` km/h", report)
        self.assertIn("gap_model: `STRAVA_RUN`", report)
        self.assertIn("split_source: `icu_intervals`", report)
        self.assertIn("vam_uphill_split_count: `1`", report)
        self.assertIn("vam_source: `icu_intervals_uphill_filtered`", report)
        self.assertIn("contexto analitico de terreno; no arbitra el gate HRV", report)

    def test_render_report_includes_terrain_fit_context_when_available(self):
        summary = {
            "session_cost_model": {"session_id": "i4", "usable": True},
            "session_row": {"sport": "trail_run"},
            "rr_context": {"modifier": "no_rr", "interpretation": "RR no disponible", "evidence": []},
            "final_cost_interpretation": {"note": "Lectura base"},
            "terrain_fit_context": {
                "climbs_source": "fit_record_level",
                "climb_count": 2,
                "climb_time_min": 18.4,
                "climb_distance_km": 2.1,
                "climb_gain_m": 92.0,
                "climb_gain_coverage_pct": 35.0,
                "climb_hr_mean": 152.4,
                "climb_cadence_mean": 81.1,
                "cadence_unit": "strides_per_min",
                "climb_power_mean": 287.4,
                "climb_power_max": 405.0,
                "signals_available": {"hr": True, "cadence": True, "power": True},
                "pause_filter_mode": "heuristic_stationary",
                "validation_vs_v2": {"status": "warn", "warnings": ["warn_low_climb_coverage"]},
            },
        }
        report = render_report_markdown(summary)
        self.assertIn("## Terrain FIT Context", report)
        self.assertIn("climbs_source: `fit_record_level`", report)
        self.assertIn("climb_gain_coverage_pct: `35.0`", report)
        self.assertIn("cadence_unit: `strides_per_min`", report)
        self.assertIn("signals_available: `hr=True, cadence=True, power=True`", report)
        self.assertIn("validation_warnings: `warn_low_climb_coverage`", report)
        self.assertIn("capa FIT paralela a V2; no recalcula GAP", report)

    def test_enrich_summary_with_sessions_metadata_nests_training_audit_under_sessions_metadata(self):
        summary = {
            "session_cost_model": {"session_id": "i1"},
            "rr_error": "GET https://x.test -> 503 Service Temporarily Unavailable\n<html>down</html>",
        }
        sessions_metadata = {
            "pipeline_version": "v3.5",
            "build_time": "2026-04-07T15:00:00",
            "stream_sampling": {"assumed_1hz": True},
            "training_audit": {
                "metric_level": {
                    "coaching_load": {"state": "high", "reasons": []},
                }
            },
        }
        with patch("analysis.session_analysis_pipeline.load_optional_json", return_value=sessions_metadata):
            enriched = enrich_summary_with_sessions_metadata(summary)
        self.assertEqual(enriched["sessions_metadata"]["pipeline_version"], "v3.5")
        self.assertEqual(
            enriched["sessions_metadata"]["training_audit"]["metric_level"]["coaching_load"]["state"],
            "high",
        )
        self.assertEqual(enriched["rr_error_summary"], "GET https://x.test -> 503 Service Temporarily Unavailable")
        self.assertNotIn("training_audit", enriched)

    def test_enrich_summary_with_manifest_context_injects_terrain_context(self):
        summary = {"session_cost_model": {"session_id": "i5"}}
        manifest = {
            "terrain_context": {
                "source": "intervals_activity+icu_intervals",
                "gap_mean": 7.6,
                "gap_unit": "km/h",
                "gap_model": "STRAVA_RUN",
                "vam_uphill_mean": None,
                "vam_source": None,
            }
        }
        enriched = enrich_summary_with_manifest_context(summary, manifest)
        self.assertEqual(enriched["terrain_context"]["gap_mean"], 7.6)
        self.assertEqual(enriched["terrain_context"]["gap_model"], "STRAVA_RUN")

    def test_enrich_summary_with_manifest_context_backfills_session_row_fields(self):
        with patch("analysis.session_analysis_pipeline.load_optional_json", return_value={"stream_dt_est": "1.0", "sport": "trail_run"}):
            enriched = enrich_summary_with_manifest_context(
                {"session_row": {"sport": "trail_run", "stream_dt_est": ""}},
                {"session_row_path": "dummy.json"},
            )
        self.assertEqual(enriched["session_row"]["stream_dt_est"], "1.0")

    def test_v2_terrain_intervals_normalize_and_summarize(self):
        payload = {
            "icu_intervals": [
                {
                    "distance": 1000.0,
                    "elapsed_time": 400.0,
                    "moving_time": 398.0,
                    "average_speed": 2.5,
                    "gap": 2.4,
                    "average_gradient": 0.03,
                    "total_elevation_gain": 30.0,
                    "average_cadence": 82,
                    "average_heartrate": 145,
                    "average_watts": 250,
                    "intensity": 80,
                    "zone": 2,
                },
                {
                    "distance": 1000.0,
                    "elapsed_time": 360.0,
                    "moving_time": 360.0,
                    "average_speed": 2.9,
                    "gap": 2.6,
                    "average_gradient": 0.0,
                    "total_elevation_gain": 5.0,
                    "average_cadence": 84,
                    "average_heartrate": 150,
                    "average_watts": 180,
                    "intensity": 88,
                    "zone": 3,
                },
                {
                    "distance": 1000.0,
                    "elapsed_time": 330.0,
                    "moving_time": 330.0,
                    "average_speed": 3.0,
                    "gap": 2.8,
                    "average_gradient": -0.03,
                    "total_elevation_gain": 0.0,
                    "average_cadence": 83,
                    "average_heartrate": 140,
                    "average_watts": 160,
                    "intensity": 72,
                    "zone": 1,
                },
            ]
        }
        rows = _normalize_terrain_interval_rows("i9", payload)
        self.assertEqual(len(rows), 3)
        self.assertEqual(rows[0]["terrain_class"], "uphill")
        self.assertEqual(rows[1]["terrain_class"], "rolling")
        self.assertEqual(rows[2]["terrain_class"], "downhill")
        self.assertEqual(rows[0]["vam_eligible"], 1)
        self.assertEqual(rows[0]["power_mean"], 250.0)
        base = {
            "source": "intervals_activity",
            "gap_mean": 9.0,
            "gap_unit": "km/h",
            "gap_model": "STRAVA_RUN",
            "vam_uphill_mean": None,
            "vam_source": None,
        }
        summary = _summarize_terrain_context_from_intervals(base, rows, session_row={"distance_km": "3.0"})
        self.assertEqual(summary["source"], "intervals_activity+icu_intervals")
        self.assertEqual(summary["split_count"], 3)
        self.assertEqual(summary["split_coverage_pct"], 100.0)
        self.assertEqual(summary["uphill_split_count"], 1)
        self.assertEqual(summary["rolling_split_count"], 1)
        self.assertEqual(summary["downhill_split_count"], 1)
        self.assertEqual(summary["gap_uphill_mean"], 8.6)
        self.assertEqual(summary["gap_rolling_mean"], 9.4)
        self.assertEqual(summary["gap_downhill_mean"], 10.1)
        self.assertEqual(summary["power_uphill_mean"], 250.0)
        self.assertEqual(summary["vam_source"], "icu_intervals_uphill_filtered")
        self.assertIsNotNone(summary["vam_uphill_mean"])

    def test_v2_terrain_summary_uses_none_when_no_vam_rows(self):
        rows = [
            {
                "terrain_class": "rolling",
                "distance_km": 1.0,
                "gap_kmh": 8.8,
                "elapsed_time_s": 360.0,
                "vam_eligible": 0,
                "vam_mh": None,
            }
        ]
        summary = _summarize_terrain_context_from_intervals(
            {
                "source": "intervals_activity",
                "gap_mean": 8.8,
                "gap_unit": "km/h",
                "gap_model": "STRAVA_RUN",
                "vam_uphill_mean": None,
                "vam_source": None,
            },
            rows,
            session_row={"distance_km": "1.0"},
        )
        self.assertIsNone(summary["vam_uphill_time_min"])
        self.assertEqual(summary["vam_uphill_split_count"], 0)
        self.assertEqual(summary["vam_source"], "icu_intervals_uphill_filtered_no_matches")

    def test_fit_terrain_prefers_enhanced_altitude(self):
        self.assertEqual(
            _select_altitude_value({"altitude": 101.0, "enhanced_altitude": 103.5}),
            103.5,
        )
        self.assertEqual(_select_altitude_value({"altitude": 101.0}), 101.0)

    def test_fit_terrain_detects_and_merges_climbs_with_directional_validation(self):
        records = []
        distance = 0.0
        altitude = 100.0
        for sec in range(0, 250):
            speed_mps = 2.0
            distance += speed_mps
            if 20 <= sec <= 110:
                altitude += 0.10
            elif 111 <= sec <= 125:
                altitude -= 0.12
            elif 126 <= sec <= 220:
                altitude += 0.11
            records.append(
                {
                    "sec": float(sec),
                    "distance_m": round(distance, 2),
                    "altitude_m": round(altitude, 2),
                    "speed_mps": speed_mps,
                    "hr": 145.0 + (sec % 10),
                    "cadence": 82.0,
                    "power": 280.0,
                    "paused": False,
                }
            )

        terrain_intervals = [
            {"terrain_class": "uphill", "distance_km": 1.0, "elev_gain_m": 40.0},
            {"terrain_class": "uphill", "distance_km": 1.0, "elev_gain_m": 38.0},
        ]
        result = analyze_terrain_records(
            records=records,
            pause_filter_mode="heuristic_stationary",
            session_elev_gain_m=260.0,
            terrain_context={"vam_uphill_time_min": 23.0},
            terrain_intervals=terrain_intervals,
        )

        climbs = result["terrain_climbs"]
        context = result["terrain_fit_context"]
        self.assertEqual(len(climbs), 1)
        self.assertGreaterEqual(climbs[0]["elev_gain_m"], 15.0)
        self.assertEqual(context["climbs_source"], "fit_record_level")
        self.assertEqual(context["climb_count"], 1)
        self.assertEqual(context["pause_filter_mode"], "heuristic_stationary")
        self.assertEqual(context["cadence_unit"], "strides_per_min")
        self.assertEqual(context["signals_available"], {"hr": True, "cadence": True, "power": True})
        self.assertEqual(context["validation_vs_v2"]["status"], "warn")
        self.assertIn("warn_low_climb_coverage", context["validation_vs_v2"]["warnings"])
        self.assertTrue(context["validation_vs_v2"]["checks"]["time_upper_bound"]["passed"])

    def test_fit_terrain_marks_low_gain_splits_as_not_applicable_for_coverage(self):
        records = []
        distance = 0.0
        altitude = 100.0
        for sec in range(0, 120):
            distance += 2.0
            records.append(
                {
                    "sec": float(sec),
                    "distance_m": round(distance, 2),
                    "altitude_m": altitude,
                    "speed_mps": 2.0,
                    "hr": 140.0,
                    "cadence": 80.0,
                    "power": 200.0,
                    "paused": False,
                }
            )

        result = analyze_terrain_records(
            records=records,
            pause_filter_mode="heuristic_stationary",
            session_elev_gain_m=33.0,
            terrain_context={"vam_uphill_time_min": None},
            terrain_intervals=[],
        )
        validation = result["terrain_fit_context"]["validation_vs_v2"]
        self.assertEqual(validation["status"], "not_available")
        self.assertFalse(validation["checks"]["coverage_lower_bound"]["applicable"])
        self.assertNotIn("warn_low_climb_coverage", validation["warnings"])

    def test_fit_validation_treats_high_coverage_v3_excess_as_info(self):
        validation = _build_validation_vs_v2(
            terrain_context={"vam_uphill_time_min": 13.6},
            terrain_intervals=[
                {"terrain_class": "uphill", "distance_km": 1.999, "elev_gain_m": 146.0},
            ],
            session_gain_m=147.8,
            climb_time_min=18.1,
            climb_gain_m=146.8,
            climb_distance_km=2.481,
            climb_gain_coverage_pct=99.3,
        )
        self.assertEqual(validation["status"], "pass")
        self.assertEqual(validation["warnings"], [])
        self.assertIn("info_v3_time_exceeds_v2_high_coverage", validation["infos"])
        self.assertIn("info_v3_distance_exceeds_v2_high_coverage", validation["infos"])
        self.assertTrue(validation["checks"]["time_upper_bound"]["passed"])
        self.assertEqual(validation["checks"]["time_upper_bound"]["comparison"], "v3_exceeds_v2_high_coverage")

    def test_supports_terrain_context_rejects_indoor_virtual_runs(self):
        self.assertFalse(
            _supports_terrain_context(
                {
                    "sport": "road_run",
                    "sport_raw": "VirtualRun",
                    "polar_sport_raw": "running indoor_running",
                }
            )
        )

    def test_fit_validation_gain_upper_bound_uses_all_positive_split_gain(self):
        records = []
        distance = 0.0
        altitude = 100.0
        for sec in range(0, 220):
            speed_mps = 2.0
            distance += speed_mps
            if 20 <= sec <= 140:
                altitude += 0.12
            records.append(
                {
                    "sec": float(sec),
                    "distance_m": round(distance, 2),
                    "altitude_m": round(altitude, 2),
                    "speed_mps": speed_mps,
                    "hr": 150.0,
                    "cadence": 82.0,
                    "power": 280.0,
                    "paused": False,
                }
            )

        result = analyze_terrain_records(
            records=records,
            pause_filter_mode="heuristic_stationary",
            session_elev_gain_m=200.0,
            terrain_context={"vam_uphill_time_min": 20.0},
            terrain_intervals=[
                {"terrain_class": "uphill", "distance_km": 0.6, "elev_gain_m": 20.0},
                {"terrain_class": "rolling", "distance_km": 0.4, "elev_gain_m": 12.0},
            ],
        )
        checks = result["terrain_fit_context"]["validation_vs_v2"]["checks"]
        self.assertEqual(checks["gain_upper_bound"]["reference_scope"], "all_positive_split_gain")
        self.assertTrue(checks["gain_upper_bound"]["passed"])


if __name__ == "__main__":
    unittest.main()
