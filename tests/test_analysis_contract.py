import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from analysis.fit_terrain_utils import (
    _build_validation_vs_v2,
    _select_altitude_value,
    analyze_terrain_records,
    group_terrain_climbs,
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
    _terrain_fit_cadence_unit,
    _summarize_terrain_context_from_intervals,
    build_ai_handoff_markdown,
    build_analysis_durability_context,
    build_analysis_work_block_context,
    build_analyst_prompt_markdown,
    build_conversational_payload,
    build_final_reason_rendered,
    build_final_report_markdown,
    build_durability_thirds_context,
    build_longitudinal_context,
    build_runaware_context,
    build_v1_snapshot,
    build_v1_shadow_comparison,
    build_v1_shadow_history,
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
from analysis.session_cost_model import build_cost_model_result, normalize_sport
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


def _write_longitudinal_payload(
    reports_root: Path,
    *,
    sport: str,
    session_id: str,
    date: str,
    start_time: str,
    route_id: int,
    load: float,
    work_total_min: float,
    cardiac_drift_pct: float,
    subjective_score: float,
    subjective_state: str,
    thermal_score: float,
    climb_gain_m: float | None = None,
    climb_time_min: float | None = None,
) -> None:
    payload_dir = reports_root / date[:4] / date[5:7] / f"{date}_{start_time.replace(':', '-')}_{sport}_{session_id}" / "artifacts"
    payload_dir.mkdir(parents=True, exist_ok=True)
    analysis_only_context = {
        "route_context": {"route_id": route_id},
        "composite_context": {
            "subjective_coherence": {
                "subjective_coherence_score": subjective_score,
                "subjective_coherence_state": subjective_state,
                "subjective_objective_gap_pct": 14.0,
            },
            "thermal_context": {
                "thermal_cost_score": thermal_score,
                "thermal_band": "moderate",
            },
            "coach_metrics": {
                "session_rpe": 6,
            },
        },
    }
    if climb_gain_m is not None and climb_time_min is not None:
        terrain_fit = {
            "climb_gain_m": climb_gain_m,
            "climb_time_min": climb_time_min,
            "climb_hr_mean": 158.0,
        }
        analysis_only_context["terrain_fit_context"] = terrain_fit
    payload = {
        "meta": {
            "session_id": session_id,
            "date": date,
            "start_time": start_time,
        },
        "session_row": {
            "session_id": session_id,
            "Fecha": date,
            "start_time": start_time,
            "sport": sport,
            "route_id": str(route_id),
            "load": str(load),
            "work_total_min": str(work_total_min),
            "cardiac_drift_pct": str(cardiac_drift_pct),
        },
        "analysis_only_context": analysis_only_context,
    }
    if climb_gain_m is not None and climb_time_min is not None:
        payload["terrain_fit_context"] = {
            "climb_gain_m": climb_gain_m,
            "climb_time_min": climb_time_min,
            "climb_hr_mean": 158.0,
        }
    (payload_dir / "session_payload.json").write_text(json.dumps(payload), encoding="utf-8")


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

    def test_build_analysis_durability_context_detects_cardiovascular_drift_only(self):
        session_row = _session_row(
            sport="road_run",
            moving_min="124.0",
            work_n_blocks="1",
            durability_applicable="1",
            run_power_available="1",
            run_power_first_half="248.0",
            run_power_second_half="243.0",
            power_ratio="0.98",
            speed_first_half="12.1",
            speed_second_half="11.9",
            speed_ratio="0.983",
            cardiac_drift_pct="4.1",
            mechanics_source="intervals_fit",
        )
        analysis_only_context = {"coach_metrics": {"decoupling_pct": 12.8}}

        context = build_analysis_durability_context(analysis_only_context, session_row)

        self.assertTrue(context["applicable"])
        self.assertEqual(context["preferred_signal"], "power_ratio")
        self.assertEqual(context["durability_pattern"], "cardiovascular_drift_only")
        self.assertEqual(context["interpretation_confidence"], "high")
        self.assertEqual(context["terrain_sensitivity"], "low")
        self.assertAlmostEqual(context["power_ratio"], 0.98, places=3)

    def test_build_analysis_durability_context_marks_trail_speed_only_as_terrain_ambiguous(self):
        session_row = _session_row(
            sport="trail_run",
            moving_min="132.0",
            work_n_blocks="1",
            durability_applicable="1",
            run_power_available="0",
            speed_first_half="9.6",
            speed_second_half="8.7",
            speed_ratio="0.906",
            cardiac_drift_pct="3.2",
            mechanics_source="polar",
        )

        context = build_analysis_durability_context({}, session_row)

        self.assertTrue(context["applicable"])
        self.assertEqual(context["preferred_signal"], "speed_ratio")
        self.assertEqual(context["durability_pattern"], "ambiguous_due_to_terrain")
        self.assertEqual(context["terrain_sensitivity"], "high")
        self.assertEqual(context["interpretation_confidence"], "low")
        self.assertTrue(any("speed_ratio" in note for note in context["notes"]))

    def test_build_durability_thirds_context_uses_terrain_profile_in_trail(self):
        with TemporaryDirectory() as tmp:
            tmpdir = Path(tmp)
            stream_csv = tmpdir / "session_stream.csv"
            rows = ["sec,hr,speed_kmh,cadence"]
            for sec in range(90):
                if sec < 30:
                    hr = 137
                    speed = 8.6
                    cadence = 81
                elif sec < 60:
                    hr = 152
                    speed = 7.9
                    cadence = 79
                else:
                    hr = 145
                    speed = 9.0
                    cadence = 85
                rows.append(f"{sec},{hr},{speed},{cadence}")
            stream_csv.write_text("\n".join(rows), encoding="utf-8")

            context = build_durability_thirds_context(
                stream_csv,
                session_row={
                    "sport": "trail_run",
                    "elev_gain_m": "245.0",
                    "work_n_blocks": "5",
                    "work_total_min": "34.2",
                    "z2_pct": "35.7",
                    "z3_pct": "15.5",
                    "cardiac_drift_pct": "-14.0",
                },
            )

        self.assertIsNotNone(context)
        self.assertEqual(context["durability_hint"], "terrain_confounded")
        self.assertEqual(context["durability_hint_detail"], "terrain_confounded_hr_peak")
        self.assertIn("perfil de terreno", " ".join(context["notes"]))

    def test_build_durability_thirds_context_tags_speed_drop_confounded_case(self):
        with TemporaryDirectory() as tmp:
            tmpdir = Path(tmp)
            stream_csv = tmpdir / "session_stream.csv"
            rows = ["sec,hr,speed_kmh,cadence"]
            for sec in range(90):
                if sec < 30:
                    hr = 140
                    speed = 9.8
                    cadence = 82
                elif sec < 60:
                    hr = 139
                    speed = 9.2
                    cadence = 80
                else:
                    hr = 136
                    speed = 8.3
                    cadence = 79
                rows.append(f"{sec},{hr},{speed},{cadence}")
            stream_csv.write_text("\n".join(rows), encoding="utf-8")

            context = build_durability_thirds_context(
                stream_csv,
                session_row={
                    "sport": "trail_run",
                    "elev_gain_m": "180.0",
                    "work_n_blocks": "4",
                    "work_total_min": "28.0",
                    "z2_pct": "25.0",
                    "z3_pct": "10.0",
                    "cardiac_drift_pct": "-1.0",
                },
            )

        self.assertIsNotNone(context)
        self.assertEqual(context["durability_hint"], "terrain_confounded")
        self.assertEqual(context["durability_hint_detail"], "terrain_confounded_speed_drop")
        self.assertIn("subtipo=terrain_confounded_speed_drop", " ".join(context["notes"]))

    def test_build_analysis_durability_context_treats_nan_power_ratio_as_missing_signal(self):
        session_row = _session_row(
            sport="road_run",
            moving_min="92.0",
            work_n_blocks="1",
            durability_applicable="1",
            run_power_available="1",
            run_power_first_half="248.0",
            run_power_second_half="nan",
            speed_first_half="12.1",
            speed_second_half="11.9",
            speed_ratio="0.983",
            mechanics_source="intervals_fit",
        )

        context = build_analysis_durability_context({}, session_row)

        self.assertTrue(context["applicable"])
        self.assertEqual(context["preferred_signal"], "speed_ratio")
        self.assertIsNone(context["power_ratio"])
        self.assertTrue(any("power_ratio no disponible" in note for note in context["notes"]))

    def test_build_analysis_durability_context_not_applicable_when_session_structure_is_unsuitable(self):
        session_row = _session_row(
            sport="road_run",
            moving_min="82.0",
            work_n_blocks="4",
            durability_applicable="0",
            run_power_available="1",
            run_power_first_half="220.0",
            run_power_second_half="205.0",
            power_ratio="0.932",
            mechanics_source="intervals_fit",
        )

        context = build_analysis_durability_context({"coach_metrics": {"decoupling_pct": 11.2}}, session_row)

        self.assertFalse(context["applicable"])
        self.assertEqual(context["durability_pattern"], "not_applicable")
        self.assertTrue(context["applicability_reason"].startswith("sessions_csv_durability_applicable=0"))
        self.assertIn("too_many_work_blocks", context["applicability_reason"])
        self.assertIn("speed_halves_unavailable", context["applicability_reason"])

    def test_build_runaware_context_exposes_trail_shadow_context(self):
        session_row = _session_row(
            sport="trail_run",
            run_power_available="1",
            run_power_mean="223.7",
            power_ratio="0.805",
            intensity_category="work_intense",
            vt1_used="143.0",
            vt2_used="158.0",
        )
        summary = {
            "terrain_fit_context": {
                "climb_count": 4,
                "climb_gain_m": 209.0,
                "climb_time_min": 19.0,
                "climb_hr_mean": 155.9,
                "climb_z3_pct_mean": 47.1,
            },
            "terrain_context": {
                "gap_mean": 9.5,
                "vam_uphill_mean": 524.3,
            },
        }

        context = build_runaware_context(summary, session_row)

        self.assertIsNotNone(context)
        self.assertEqual(context["source"], "combined")
        self.assertEqual(context["strength"], "strong")
        self.assertEqual(context["strength_grade"], "combined")
        self.assertTrue(context["shadow_only"])
        self.assertIn("terrain_ready=true", context["strength_basis"])
        self.assertIn("power_ready=true", context["strength_basis"])
        self.assertIn("terrain_strength_grade=terrain_moderate", context["strength_basis"])
        self.assertIn("combined_evidence=terrain_plus_power", context["strength_basis"])
        self.assertIn("intensity_category=work_intense", context["runaware_severity_basis"])
        self.assertIn("threshold=climb_z3_pct_mean>=40", context["runaware_severity_basis"])
        self.assertIn("climb_hr_mean=155.9", context["runaware_candidate_basis"])
        self.assertIn("climb_hr_mean=155.9", context["runaware_severity_basis"])
        self.assertIn("vt1_used=143.0", context["runaware_severity_basis"])
        self.assertIn("threshold=climb_hr_mean>=vt1_used", context["runaware_severity_basis"])
        self.assertEqual(context["terrain_climb_count"], 4)
        self.assertEqual(context["runaware_intense_candidate"], 1)
        self.assertEqual(context["runaware_severity_candidate"], "high")
        self.assertEqual(
            context["runaware_candidate_basis"],
            [
                "intensity_category=work_intense",
                "climb_z3_pct_mean=47.1",
                "vam_uphill=524",
                "climb_hr_mean=155.9",
            ],
        )
        self.assertEqual(context["terrain_strength_grade"], "terrain_moderate")
        self.assertAlmostEqual(context["run_power_mean"], 223.7, places=1)
        self.assertAlmostEqual(context["power_ratio"], 0.805, places=3)
        self.assertIn("no alimentar reason_text", context["notes"][1])

    def test_build_v1_snapshot_uses_sessions_day_clustering_fields(self):
        snapshot = build_v1_snapshot(
            {
                "intensity_clustering_flag": "1",
                "intensity_clustering_level": "high",
            }
        )

        self.assertEqual(
            snapshot,
            {
                "intensity_clustering_flag": 1,
                "intensity_clustering_severity": "high",
            },
        )

    def test_build_v1_shadow_comparison_reports_divergence(self):
        comparison = build_v1_shadow_comparison(
            {
                "intensity_clustering_flag": 0,
                "intensity_clustering_severity": None,
            },
            {
                "runaware_intense_candidate": 1,
                "runaware_severity_candidate": "high",
            },
        )

        self.assertEqual(comparison["alignment"], "divergent")
        self.assertEqual(comparison["flag_alignment"], "mismatch")
        self.assertIsNone(comparison["severity_alignment"])
        self.assertIn("discrepan", comparison["notes"][0])

    def test_build_v1_shadow_history_orders_recent_sessions_first(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            reports_root = root / "analysis" / "reports"
            current_report_dir = reports_root / "2026" / "04" / "2026-04-21_14-56_trail_run_i141760231"
            other_report_dir = reports_root / "2026" / "04" / "2026-04-01_10-00_trail_run_i000000001"
            current_report_dir.joinpath("artifacts").mkdir(parents=True, exist_ok=True)
            other_report_dir.joinpath("artifacts").mkdir(parents=True, exist_ok=True)

            current_summary = {
                "meta": {"session_id": "i141760231", "date": "2026-04-21"},
                "session_row": {"Fecha": "2026-04-21", "sport": "trail_run"},
                "v1_snapshot": {"intensity_clustering_flag": 0, "intensity_clustering_severity": None},
                "runaware_context": {
                    "runaware_intense_candidate": 1,
                    "runaware_severity_candidate": "high",
                    "source": "combined",
                },
            }
            other_summary = {
                "meta": {"session_id": "i000000001", "date": "2026-04-01"},
                "session_row": {"Fecha": "2026-04-01", "sport": "trail_run"},
                "v1_snapshot": {"intensity_clustering_flag": 1, "intensity_clustering_severity": "high"},
                "runaware_context": {
                    "runaware_intense_candidate": 1,
                    "runaware_severity_candidate": "high",
                    "source": "terrain",
                },
            }
            (current_report_dir / "artifacts" / "summary.json").write_text(json.dumps(current_summary), encoding="utf-8")
            (other_report_dir / "artifacts" / "summary.json").write_text(json.dumps(other_summary), encoding="utf-8")

            def fake_row_by_date(path, date_str):
                path_str = str(path)
                if path_str.endswith("ENDURANCE_HRV_sessions_day.csv"):
                    if date_str == "2026-04-21":
                        return {"Fecha": "2026-04-21", "intensity_clustering_flag": "0", "intensity_clustering_level": "low"}
                    if date_str == "2026-04-01":
                        return {"Fecha": "2026-04-01", "intensity_clustering_flag": "1", "intensity_clustering_level": "high"}
                if path_str.endswith("ENDURANCE_HRV_master_FINAL.csv"):
                    if date_str == "2026-04-22":
                        return {"Fecha": "2026-04-22", "gate_badge": "VERDE--", "residual_z": "-1.3", "Action": "INTENSIDAD_OK", "residual_ln": "-0.05"}
                    if date_str == "2026-04-02":
                        return {"Fecha": "2026-04-02", "gate_badge": "AMBAR--", "residual_z": "0.4", "Action": "RECUPERACION", "residual_ln": "0.02"}
                return None

            with patch("analysis.session_analysis_pipeline.row_by_date", side_effect=fake_row_by_date):
                history = build_v1_shadow_history(
                    current_summary,
                    current_summary["session_row"],
                    reports_root=reports_root,
                    current_report_dir=current_report_dir,
                    limit=8,
                )

        self.assertIsNotNone(history)
        self.assertEqual(history["row_count"], 2)
        self.assertEqual(history["v1_scope"], "all_sports_daily_intensity_clustering")
        self.assertEqual(history["shadow_scope"], "trail_only_session_candidates_rolling_window")
        self.assertIn("alcance", history["scope_note"])
        self.assertEqual(history["comparable_count"], 2)
        self.assertEqual(history["aligned_count"], 1)
        self.assertEqual(history["divergent_count"], 1)
        self.assertAlmostEqual(history["aligned_rate"], 0.5, places=3)
        self.assertEqual(history["shadow_positive_count"], 0)
        self.assertEqual(history["v1_positive_count"], 1)
        self.assertIn(5, history["window_summaries"])
        self.assertIn(10, history["window_summaries"])
        self.assertEqual(history["window_summaries"][5]["row_count"], 2)
        self.assertEqual(history["current_session_id"], "i141760231")
        self.assertEqual(history["rows"][0]["session_id"], "i141760231")
        self.assertEqual(history["rows"][0]["alignment"], "aligned")
        self.assertEqual(history["rows"][0]["shadow_source"], "combined")
        self.assertEqual(history["rows"][0]["shadow_session_candidate"], 1)
        self.assertEqual(history["rows"][0]["shadow_candidate"], 0)
        self.assertEqual(history["rows"][0]["next_day_gate"], "VERDE--")
        self.assertEqual(history["rows"][0]["next_day_residual_z"], -1.3)
        self.assertEqual(history["rows"][0]["next_day_action"], "INTENSIDAD_OK")
        self.assertEqual(history["rows"][0]["next_day_hrv_delta"], -0.05)
        self.assertEqual(history["rows"][1]["alignment"], "divergent")
        self.assertEqual(history["rows"][1]["shadow_source"], "terrain")
        self.assertEqual(history["rows"][1]["shadow_session_candidate"], 1)
        self.assertEqual(history["rows"][1]["shadow_candidate"], 0)
        self.assertEqual(history["rows"][1]["next_day_gate"], "AMBAR--")
        self.assertIn("muestra pequena", history["sample_warning"])

    def test_build_v1_shadow_history_uses_session_row_id_when_meta_missing(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            reports_root = root / "analysis" / "reports"
            current_report_dir = reports_root / "2026" / "04" / "2026-04-21_14-56_trail_run_i141760231"
            current_report_dir.joinpath("artifacts").mkdir(parents=True, exist_ok=True)

            current_summary = {
                "meta": {"date": "2026-04-21"},
                "session_row": {"session_id": "i141760231", "Fecha": "2026-04-21", "sport": "trail_run"},
                "v1_snapshot": {"intensity_clustering_flag": 0, "intensity_clustering_severity": None},
                "runaware_context": {"runaware_intense_candidate": 1, "runaware_severity_candidate": "high"},
            }
            (current_report_dir / "artifacts" / "summary.json").write_text(json.dumps(current_summary), encoding="utf-8")

            history = build_v1_shadow_history(
                current_summary,
                current_summary["session_row"],
                reports_root=reports_root,
                current_report_dir=current_report_dir,
                limit=8,
            )

        self.assertIsNotNone(history)
        self.assertEqual(history["current_session_id"], "i141760231")
        self.assertEqual(history["current_date"], "2026-04-21")
        self.assertEqual(history["v1_scope"], "all_sports_daily_intensity_clustering")

    def test_build_runaware_context_skips_road_run(self):
        context = build_runaware_context(
            {
                "terrain_fit_context": {"climb_count": 4, "climb_gain_m": 780.0, "climb_time_min": 41.5},
                "terrain_context": {"gap_mean": 8.6, "vam_uphill_mean": 462.0},
            },
            _session_row(sport="road_run", run_power_available="1", run_power_mean="312.4", power_ratio="0.964"),
        )

        self.assertIsNone(context)

    def test_build_analysis_work_block_context_detects_one_dominant_hard_block(self):
        session_row = _session_row(
            sport="trail_run",
            work_n_blocks="5",
            work_total_min="34.2",
            work_longest_min="11.4",
            work_blocks_min="3.3;3.5;11.4;9.0;7.0",
            work_blocks_z3pct="0;0;75;0;14",
        )

        context = build_analysis_work_block_context(session_row)

        self.assertTrue(context["available"])
        self.assertEqual(context["block_count"], 5)
        self.assertEqual(context["hard_work_blocks"], 1)
        self.assertEqual(context["very_hard_work_blocks"], 1)
        self.assertEqual(context["dominant_work_block_index"], 3)
        self.assertAlmostEqual(context["dominant_work_block_min"], 11.4, places=1)
        self.assertAlmostEqual(context["dominant_work_block_share"], 0.333, places=3)
        self.assertEqual(context["work_block_pattern"], "one_dominant_hard_block")

    def test_build_conversational_payload_exposes_analysis_durability_context(self):
        session_row = _session_row(
            sport="road_run",
            moving_min="121.0",
            work_n_blocks="1",
            durability_applicable="1",
            run_power_available="1",
            run_power_first_half="250.0",
            run_power_second_half="235.0",
            power_ratio="0.94",
            speed_first_half="12.2",
            speed_second_half="11.8",
            speed_ratio="0.967",
            cardiac_drift_pct="6.0",
            mechanics_source="intervals_fit",
        )
        manifest = {
            "session_id": "i1",
            "slug": "2026-03-25_09-00_road_run_i1",
            "date": "2026-03-25",
            "start_time": "09:00",
            "sport": "road_run",
            "analysis_only_context": {"coach_metrics": {"decoupling_pct": 11.6}},
        }

        def fake_row_by_date(path, date_str):
            if path.name == "ENDURANCE_HRV_master_FINAL.csv":
                return {"Fecha": date_str, "reason_text": "ok"}
            if path.name == "ENDURANCE_HRV_master_DASHBOARD.csv":
                return {"Fecha": date_str, "reason_text": "ok"}
            return None

        with patch("analysis.session_analysis_pipeline.row_by_date", side_effect=fake_row_by_date), patch(
            "analysis.session_analysis_pipeline.load_optional_json", return_value=None
        ), patch(
            "analysis.session_analysis_pipeline.load_final_reason_items_lookup", return_value={}
        ), patch(
            "analysis.session_analysis_pipeline._compute_speed_metrics", return_value=None
        ):
            payload = build_conversational_payload({}, manifest, session_row)

        self.assertEqual(payload["durability_context"]["durability_pattern"], "mechanical_drop_with_drift")
        self.assertEqual(
            payload["analysis_only_context"]["durability_context"]["durability_pattern"],
            "mechanical_drop_with_drift",
        )
        self.assertEqual(payload["narrative_targets"]["durability_context"]["preferred_signal"], "power_ratio")

    def test_build_conversational_payload_exposes_work_block_context(self):
        session_row = _session_row(
            sport="trail_run",
            work_n_blocks="5",
            work_total_min="34.2",
            work_longest_min="11.4",
            work_blocks_min="3.3;3.5;11.4;9.0;7.0",
            work_blocks_z3pct="0;0;75;0;14",
        )
        manifest = {
            "session_id": "i1",
            "slug": "2026-03-25_09-00_trail_run_i1",
            "date": "2026-03-25",
            "start_time": "09:00",
            "sport": "trail_run",
            "analysis_only_context": {},
        }

        def fake_row_by_date(path, date_str):
            if path.name == "ENDURANCE_HRV_master_FINAL.csv":
                return {"Fecha": date_str, "reason_text": "ok"}
            if path.name == "ENDURANCE_HRV_master_DASHBOARD.csv":
                return {"Fecha": date_str, "reason_text": "ok"}
            return None

        with patch("analysis.session_analysis_pipeline.row_by_date", side_effect=fake_row_by_date), patch(
            "analysis.session_analysis_pipeline.load_optional_json", return_value=None
        ), patch(
            "analysis.session_analysis_pipeline.load_final_reason_items_lookup", return_value={}
        ), patch(
            "analysis.session_analysis_pipeline._compute_speed_metrics", return_value=None
        ):
            payload = build_conversational_payload({}, manifest, session_row)

        self.assertEqual(payload["work_block_context"]["work_block_pattern"], "one_dominant_hard_block")
        self.assertEqual(payload["analysis_only_context"]["work_block_context"]["hard_work_blocks"], 1)

    def test_build_conversational_payload_exposes_runaware_context(self):
        session_row = _session_row(
            sport="trail_run",
            run_power_available="1",
            run_power_mean="312.4",
            power_ratio="0.964",
            intensity_category="work_intense",
        )
        manifest = {
            "session_id": "i1",
            "slug": "2026-03-25_09-00_trail_run_i1",
            "date": "2026-03-25",
            "start_time": "09:00",
            "sport": "trail_run",
            "analysis_only_context": {},
        }

        def fake_row_by_date(path, date_str):
            if path.name == "ENDURANCE_HRV_master_FINAL.csv":
                return {"Fecha": date_str, "reason_text": "ok"}
            if path.name == "ENDURANCE_HRV_master_DASHBOARD.csv":
                return {"Fecha": date_str, "reason_text": "ok"}
            return None

        summary = {
            "terrain_fit_context": {
                "climb_count": 4,
                "climb_gain_m": 780.0,
                "climb_time_min": 41.5,
            },
            "terrain_context": {
                "gap_mean": 8.6,
                "vam_uphill_mean": 462.0,
            },
            "v1_snapshot": {
                "intensity_clustering_flag": 1,
                "intensity_clustering_severity": "high",
            },
            "v1_shadow_comparison": {
                "alignment": "aligned",
                "flag_alignment": "match",
                "severity_alignment": "match",
                "notes": ["v1 y sombra coinciden de forma consistente"],
            },
        }

        with patch("analysis.session_analysis_pipeline.row_by_date", side_effect=fake_row_by_date), patch(
            "analysis.session_analysis_pipeline.load_optional_json", return_value=None
        ), patch(
            "analysis.session_analysis_pipeline.load_final_reason_items_lookup", return_value={}
        ), patch(
            "analysis.session_analysis_pipeline._compute_speed_metrics", return_value=None
        ):
            payload = build_conversational_payload(summary, manifest, session_row)

        self.assertEqual(payload["runaware_context"]["source"], "combined")
        self.assertEqual(payload["analysis_only_context"]["runaware_context"]["strength"], "strong")
        self.assertEqual(payload["context"]["runaware_context"]["terrain_climb_count"], 4)
        self.assertEqual(payload["v1_snapshot"]["intensity_clustering_flag"], 1)
        self.assertEqual(payload["context"]["v1_snapshot"]["intensity_clustering_severity"], "high")
        self.assertEqual(payload["v1_shadow_comparison"]["alignment"], "aligned")
        self.assertEqual(payload["context"]["v1_shadow_comparison"]["flag_alignment"], "match")

    def test_build_conversational_payload_exposes_longitudinal_context(self):
        session_row = _session_row(
            session_id="current-session",
            Fecha="2026-04-14",
            start_time="14:08",
            sport="trail_run",
            route_id="42",
            moving_min="47.0",
            duration_min="47.0",
            load="90.0",
            work_total_min="47.0",
            work_n_blocks="2",
            work_longest_min="16.0",
            cardiac_drift_pct="6.0",
            z3_total_min="9.5",
            z3_pct="20.0",
        )
        manifest = {
            "session_id": "current-session",
            "slug": "2026-04-14_14-08_trail_run_current-session",
            "date": "2026-04-14",
            "start_time": "14:08",
            "sport": "trail_run",
            "analysis_only_context": {},
        }

        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            reports_root = root / "analysis" / "reports"
            sessions_csv = root / "data" / "ENDURANCE_HRV_sessions.csv"
            sessions_csv.parent.mkdir(parents=True, exist_ok=True)
            sessions_csv.write_text(
                "\n".join(
                    [
                        "session_id,sport,work_total_min,load,z3_total_min,z3_pct",
                        "h1,trail_run,38.0,74.0,7.0,18.0",
                        "h2,trail_run,41.0,81.0,8.0,19.0",
                        "h3,trail_run,44.0,88.0,9.0,21.0",
                        "h4,trail_run,46.0,92.0,10.0,23.0",
                    ]
                ),
                encoding="utf-8",
            )

            def write_historical_payload(
                session_id: str,
                date: str,
                start_time: str,
                load: float,
                work_total_min: float,
                cardiac_drift_pct: float,
                subjective_score: float,
                subjective_state: str,
                thermal_score: float,
                climb_gain_m: float,
                climb_time_min: float,
            ) -> None:
                payload_dir = reports_root / date[:4] / date[5:7] / f"{date}_{start_time.replace(':', '-')}_trail_run_{session_id}" / "artifacts"
                payload_dir.mkdir(parents=True, exist_ok=True)
                payload = {
                    "meta": {
                        "session_id": session_id,
                        "date": date,
                        "start_time": start_time,
                    },
                    "session_row": {
                        "session_id": session_id,
                        "Fecha": date,
                        "start_time": start_time,
                        "sport": "trail_run",
                        "route_id": "42",
                        "load": str(load),
                        "work_total_min": str(work_total_min),
                        "cardiac_drift_pct": str(cardiac_drift_pct),
                    },
                    "analysis_only_context": {
                        "route_context": {"route_id": 42},
                        "composite_context": {
                            "subjective_coherence": {
                                "subjective_coherence_score": subjective_score,
                                "subjective_coherence_state": subjective_state,
                                "subjective_objective_gap_pct": 14.0,
                            },
                            "thermal_context": {
                                "thermal_cost_score": thermal_score,
                                "thermal_band": "moderate",
                            },
                            "coach_metrics": {
                                "session_rpe": 6,
                            },
                        },
                        "terrain_fit_context": {
                            "climb_gain_m": climb_gain_m,
                            "climb_time_min": climb_time_min,
                            "climb_hr_mean": 158.0,
                        },
                    },
                    "terrain_fit_context": {
                        "climb_gain_m": climb_gain_m,
                        "climb_time_min": climb_time_min,
                        "climb_hr_mean": 158.0,
                    },
                }
                (payload_dir / "session_payload.json").write_text(json.dumps(payload), encoding="utf-8")

            write_historical_payload("h1", "2026-04-01", "08:10", 74.0, 38.0, 4.4, 68.0, "mismatched", 7.8, 820.0, 41.0)
            write_historical_payload("h2", "2026-04-07", "08:20", 81.0, 41.0, 5.1, 71.0, "aligned", 8.2, 835.0, 41.5)
            write_historical_payload("h3", "2026-04-10", "08:30", 88.0, 44.0, 5.8, 66.0, "mismatched", 8.6, 845.0, 42.0)

            summary = {
                "session_cost_model": {"usable": True, "coste_dominante": "mixto"},
                "terrain_fit_context": {
                    "climb_gain_m": 870.0,
                    "climb_time_min": 42.0,
                    "climb_hr_mean": 160.0,
                },
                "composite_context": {
                    "subjective_coherence": {
                        "subjective_coherence_score": 64.0,
                        "subjective_coherence_state": "mismatched",
                        "subjective_objective_gap_pct": 18.0,
                    },
                    "thermal_context": {
                        "thermal_cost_score": 8.0,
                        "thermal_band": "moderate",
                    },
                    "durability_context": {
                        "durability_hint": "fade_like",
                        "confidence": "medium",
                    },
                    "coach_metrics": {
                        "session_rpe": 6,
                    },
                },
                "analysis_only_context": {
                    "route_context": {"route_id": 42},
                    "composite_context": {
                        "subjective_coherence": {
                            "subjective_coherence_score": 64.0,
                            "subjective_coherence_state": "mismatched",
                            "subjective_objective_gap_pct": 18.0,
                        },
                        "thermal_context": {
                            "thermal_cost_score": 8.0,
                            "thermal_band": "moderate",
                        },
                        "durability_context": {
                            "durability_hint": "fade_like",
                            "confidence": "medium",
                        },
                        "coach_metrics": {
                            "session_rpe": 6,
                        },
                    },
                    "terrain_fit_context": {
                        "climb_gain_m": 870.0,
                        "climb_time_min": 42.0,
                        "climb_hr_mean": 160.0,
                    },
                    "durability_context": {
                        "durability_hint": "fade_like",
                        "confidence": "medium",
                    },
                },
            }

            def fake_row_by_date(path, date_str):
                if path.name == "ENDURANCE_HRV_master_FINAL.csv":
                    return {
                        "Fecha": date_str,
                        "Calidad": "OK",
                        "RMSSD_stable": "40.2",
                        "lnRMSSD_used": "3.69",
                        "HR_used": "49.8",
                        "gate_badge": "VERDE",
                        "Action": "Normal con prudencia",
                        "baseline60_degraded": "False",
                        "reason_text": "VERDE, pero carga y contexto longitudinal piden prudencia",
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
                        "reason_text": "VERDE, pero carga y contexto longitudinal piden prudencia",
                    }
                return None

            with patch("analysis.session_analysis_pipeline.DEFAULT_REPORTS_DIR", reports_root), patch(
                "analysis.session_analysis_pipeline.DEFAULT_SESSIONS_CSV", sessions_csv
            ), patch(
                "analysis.session_analysis_pipeline.DEFAULT_INTENSITY_DISTRIBUTION_WEEKLY_CSV", root / "data" / "missing_weekly.csv"
            ), patch(
                "analysis.session_analysis_pipeline.row_by_date", side_effect=fake_row_by_date
            ), patch(
                "analysis.session_analysis_pipeline.load_optional_json", return_value=None
            ), patch(
                "analysis.session_analysis_pipeline.load_final_reason_items_lookup", return_value={}
            ), patch(
                "analysis.session_analysis_pipeline._compute_speed_metrics", return_value=None
            ):
                payload = build_conversational_payload(summary, manifest, session_row)
                markdown = build_final_report_markdown(payload, summary, "sync-token-123")

        longitudinal_context = payload["longitudinal_context"]
        self.assertTrue(longitudinal_context["available"])
        self.assertEqual(longitudinal_context["version"], "sya08_longitudinal_v1")
        self.assertEqual(longitudinal_context["confidence"], "moderate")
        self.assertEqual(longitudinal_context["route_benchmark"]["same_route_count"], 3)
        self.assertTrue(longitudinal_context["route_benchmark"]["available"])
        self.assertIn("route_vam_delta_pct=", longitudinal_context["route_benchmark"]["climb_economy_basis"][-1])
        self.assertTrue(longitudinal_context["subjective_chronic_context"]["available"])
        self.assertIn(
            "chronic_state_thresholds: coherent>=80 & mismatch<0.25",
            longitudinal_context["subjective_chronic_context"]["basis"],
        )
        self.assertTrue(longitudinal_context["thermal_sensitivity_context"]["available"])
        self.assertIn("longitudinal_context", payload["narrative_targets"])
        self.assertIn("Consolidación longitudinal", markdown)
        self.assertIn("benchmark de ruta", markdown)
        self.assertIn("sensibilidad térmica longitudinal", markdown)

    def test_build_longitudinal_context_loads_history_once(self):
        session_row = _session_row(
            session_id="current-session",
            Fecha="2026-04-14",
            start_time="14:08",
            sport="trail_run",
            route_id="42",
            moving_min="47.0",
            duration_min="47.0",
            load="90.0",
            work_total_min="47.0",
            cardiac_drift_pct="6.0",
        )
        summary = {
            "terrain_fit_context": {
                "climb_gain_m": 870.0,
                "climb_time_min": 42.0,
                "climb_hr_mean": 160.0,
            },
            "composite_context": {
                "subjective_coherence": {
                    "subjective_coherence_score": 64.0,
                    "subjective_coherence_state": "mismatched",
                    "subjective_objective_gap_pct": 18.0,
                },
                "thermal_context": {
                    "thermal_cost_score": 8.0,
                    "thermal_band": "moderate",
                },
                "coach_metrics": {
                    "session_rpe": 6,
                },
            },
            "analysis_only_context": {
                "route_context": {"route_id": 42},
                "composite_context": {
                    "subjective_coherence": {
                        "subjective_coherence_score": 64.0,
                        "subjective_coherence_state": "mismatched",
                        "subjective_objective_gap_pct": 18.0,
                    },
                    "thermal_context": {
                        "thermal_cost_score": 8.0,
                        "thermal_band": "moderate",
                    },
                    "coach_metrics": {
                        "session_rpe": 6,
                    },
                },
                "terrain_fit_context": {
                    "climb_gain_m": 870.0,
                    "climb_time_min": 42.0,
                    "climb_hr_mean": 160.0,
                },
            },
        }
        payload = {
            "meta": {
                "session_id": "h1",
                "date": "2026-04-01",
                "start_time": "08:10",
            },
            "session_row": {
                "session_id": "h1",
                "Fecha": "2026-04-01",
                "start_time": "08:10",
                "sport": "trail_run",
                "route_id": "42",
                "load": "74.0",
                "work_total_min": "38.0",
                "cardiac_drift_pct": "4.4",
            },
            "analysis_only_context": {
                "route_context": {"route_id": 42},
                "composite_context": {
                    "subjective_coherence": {
                        "subjective_coherence_score": 68.0,
                        "subjective_coherence_state": "mismatched",
                        "subjective_objective_gap_pct": 14.0,
                    },
                    "thermal_context": {
                        "thermal_cost_score": 7.8,
                        "thermal_band": "moderate",
                    },
                    "coach_metrics": {
                        "session_rpe": 6,
                    },
                },
                "terrain_fit_context": {
                    "climb_gain_m": 820.0,
                    "climb_time_min": 41.0,
                    "climb_hr_mean": 158.0,
                },
            },
            "terrain_fit_context": {
                "climb_gain_m": 820.0,
                "climb_time_min": 41.0,
                "climb_hr_mean": 158.0,
            },
        }
        with patch(
            "analysis.session_analysis_pipeline._load_historical_session_payloads",
            return_value=[payload],
        ) as load_mock:
            result = build_longitudinal_context(
                session_row,
                summary,
                summary["analysis_only_context"],
                report_root=Path("/tmp"),
        )

        self.assertEqual(load_mock.call_count, 1)
        self.assertIsNotNone(result)
        self.assertEqual(result["history_count"], 1)
        self.assertEqual(result["version"], "sya08_longitudinal_v1")

    def test_build_longitudinal_context_reaches_high_confidence(self):
        session_row = _session_row(
            session_id="current-session",
            Fecha="2026-04-14",
            start_time="14:08",
            sport="trail_run",
            route_id="42",
            moving_min="47.0",
            duration_min="47.0",
            load="90.0",
            work_total_min="47.0",
            cardiac_drift_pct="6.0",
        )
        summary = {
            "terrain_fit_context": {
                "climb_gain_m": 845.0,
                "climb_time_min": 42.0,
                "climb_hr_mean": 157.0,
            },
            "composite_context": {
                "subjective_coherence": {
                    "subjective_coherence_score": 62.0,
                    "subjective_coherence_state": "mismatched",
                    "subjective_objective_gap_pct": 17.0,
                },
                "thermal_context": {
                    "thermal_cost_score": 8.0,
                    "thermal_band": "moderate",
                },
                "coach_metrics": {
                    "session_rpe": 6,
                },
            },
            "analysis_only_context": {
                "route_context": {"route_id": 42},
                "composite_context": {
                    "subjective_coherence": {
                        "subjective_coherence_score": 62.0,
                        "subjective_coherence_state": "mismatched",
                        "subjective_objective_gap_pct": 17.0,
                    },
                    "thermal_context": {
                        "thermal_cost_score": 8.0,
                        "thermal_band": "moderate",
                    },
                    "coach_metrics": {
                        "session_rpe": 6,
                    },
                },
                "terrain_fit_context": {
                    "climb_gain_m": 845.0,
                    "climb_time_min": 42.0,
                    "climb_hr_mean": 157.0,
                },
            },
        }

        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            reports_root = root / "analysis" / "reports"
            sessions_csv = root / "data" / "ENDURANCE_HRV_sessions.csv"
            sessions_csv.parent.mkdir(parents=True, exist_ok=True)
            sessions_csv.write_text(
                "\n".join(
                    [
                        "session_id,sport,work_total_min,load,z3_total_min,z3_pct",
                        *[
                            f"h{i},trail_run,{40.0 + i:.1f},{74.0 + i:.1f},{7.0 + (i / 10):.1f},{18.0 + (i / 10):.1f}"
                            for i in range(1, 14)
                        ],
                    ]
                ),
                encoding="utf-8",
            )

            for i in range(1, 13):
                _write_longitudinal_payload(
                    reports_root,
                    sport="trail_run",
                    session_id=f"h{i}",
                    date=f"2026-04-{i:02d}",
                    start_time="08:00",
                    route_id=42,
                    load=74.0 + i,
                    work_total_min=40.0 + i,
                    cardiac_drift_pct=4.0 + (i / 10.0),
                    subjective_score=70.0 + i,
                    subjective_state="mismatched" if i % 2 else "aligned",
                    thermal_score=7.0 + (i / 10.0),
                    climb_gain_m=820.0 + i,
                    climb_time_min=41.0,
                )

            with patch("analysis.session_analysis_pipeline.DEFAULT_REPORTS_DIR", reports_root), patch(
                "analysis.session_analysis_pipeline.DEFAULT_SESSIONS_CSV", sessions_csv
            ):
                result = build_longitudinal_context(
                    session_row,
                    summary,
                    summary["analysis_only_context"],
                    report_root=reports_root,
                )

        self.assertIsNotNone(result)
        self.assertEqual(result["version"], "sya08_longitudinal_v1")
        self.assertEqual(result["confidence"], "high")
        self.assertEqual(result["history_count"], 12)
        self.assertTrue(result["route_benchmark"]["available"])
        self.assertTrue(result["support"]["route_benchmark_ready"])

    def test_build_longitudinal_context_ignores_cross_sport_history(self):
        session_row = _session_row(
            session_id="road-current",
            Fecha="2026-04-14",
            start_time="14:08",
            sport="road_run",
            route_id="42",
            moving_min="56.0",
            duration_min="56.0",
            load="84.0",
            work_total_min="56.0",
            cardiac_drift_pct="4.2",
        )
        summary = {
            "terrain_fit_context": {
                "climb_gain_m": 830.0,
                "climb_time_min": 41.0,
                "climb_hr_mean": 156.0,
            },
            "composite_context": {
                "subjective_coherence": {
                    "subjective_coherence_score": 63.0,
                    "subjective_coherence_state": "mismatched",
                    "subjective_objective_gap_pct": 16.0,
                },
                "thermal_context": {
                    "thermal_cost_score": 7.8,
                    "thermal_band": "moderate",
                },
                "coach_metrics": {
                    "session_rpe": 6,
                },
            },
            "analysis_only_context": {
                "route_context": {"route_id": 42},
                "composite_context": {
                    "subjective_coherence": {
                        "subjective_coherence_score": 63.0,
                        "subjective_coherence_state": "mismatched",
                        "subjective_objective_gap_pct": 16.0,
                    },
                    "thermal_context": {
                        "thermal_cost_score": 7.8,
                        "thermal_band": "moderate",
                    },
                    "coach_metrics": {
                        "session_rpe": 6,
                    },
                },
                "terrain_fit_context": {
                    "climb_gain_m": 830.0,
                    "climb_time_min": 41.0,
                    "climb_hr_mean": 156.0,
                },
            },
        }

        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            reports_root = root / "analysis" / "reports"
            sessions_csv = root / "data" / "ENDURANCE_HRV_sessions.csv"
            sessions_csv.parent.mkdir(parents=True, exist_ok=True)
            sessions_csv.write_text(
                "\n".join(
                    [
                        "session_id,sport,work_total_min,load,z3_total_min,z3_pct",
                        "road-h1,road_run,44.0,78.0,8.0,18.0",
                        "road-h2,road_run,46.0,81.0,8.5,19.0",
                        "road-h3,road_run,48.0,84.0,9.0,20.0",
                        "trail-h1,trail_run,50.0,90.0,10.0,22.0",
                    ]
                ),
                encoding="utf-8",
            )

            _write_longitudinal_payload(
                reports_root,
                sport="road_run",
                session_id="road-h1",
                date="2026-04-01",
                start_time="08:10",
                route_id=42,
                load=78.0,
                work_total_min=44.0,
                cardiac_drift_pct=3.8,
                subjective_score=68.0,
                subjective_state="coherent",
                thermal_score=7.3,
                climb_gain_m=810.0,
                climb_time_min=41.0,
            )
            _write_longitudinal_payload(
                reports_root,
                sport="road_run",
                session_id="road-h2",
                date="2026-04-07",
                start_time="08:20",
                route_id=42,
                load=81.0,
                work_total_min=46.0,
                cardiac_drift_pct=4.0,
                subjective_score=66.0,
                subjective_state="mismatched",
                thermal_score=7.6,
                climb_gain_m=815.0,
                climb_time_min=41.5,
            )
            _write_longitudinal_payload(
                reports_root,
                sport="road_run",
                session_id="road-h3",
                date="2026-04-10",
                start_time="08:30",
                route_id=42,
                load=84.0,
                work_total_min=48.0,
                cardiac_drift_pct=4.3,
                subjective_score=64.0,
                subjective_state="mismatched",
                thermal_score=7.9,
                climb_gain_m=820.0,
                climb_time_min=42.0,
            )
            _write_longitudinal_payload(
                reports_root,
                sport="trail_run",
                session_id="trail-h1",
                date="2026-04-08",
                start_time="08:30",
                route_id=42,
                load=90.0,
                work_total_min=50.0,
                cardiac_drift_pct=5.3,
                subjective_score=72.0,
                subjective_state="coherent",
                thermal_score=8.1,
                climb_gain_m=900.0,
                climb_time_min=44.0,
            )

            ctx = build_longitudinal_context(
                session_row,
                summary,
                summary["analysis_only_context"],
                report_root=reports_root,
            )

        self.assertIsNotNone(ctx)
        self.assertEqual(ctx["sport_family"], "road")
        self.assertEqual(ctx["history_count"], 3)
        self.assertEqual(ctx["route_benchmark"]["same_route_count"], 3)
        self.assertEqual(ctx["route_history"]["previous_session_id"], "road-h3")
        self.assertEqual(ctx["support"]["route_context_count"], 3)

    def test_build_longitudinal_context_allows_route_benchmark_without_climb_data(self):
        session_row = _session_row(
            session_id="bike-current",
            Fecha="2026-04-14",
            start_time="10:08",
            sport="bike",
            route_id="77",
            moving_min="94.0",
            duration_min="94.0",
            load="115.0",
            work_total_min="94.0",
            cardiac_drift_pct="2.7",
        )
        summary = {
            "composite_context": {
                "subjective_coherence": {
                    "subjective_coherence_score": 71.0,
                    "subjective_coherence_state": "coherent",
                    "subjective_objective_gap_pct": 8.0,
                },
                "thermal_context": {
                    "thermal_cost_score": 6.9,
                    "thermal_band": "moderate",
                },
                "coach_metrics": {
                    "session_rpe": 6,
                },
            },
            "analysis_only_context": {
                "route_context": {"route_id": 77},
                "composite_context": {
                    "subjective_coherence": {
                        "subjective_coherence_score": 71.0,
                        "subjective_coherence_state": "coherent",
                        "subjective_objective_gap_pct": 8.0,
                    },
                    "thermal_context": {
                        "thermal_cost_score": 6.9,
                        "thermal_band": "moderate",
                    },
                    "coach_metrics": {
                        "session_rpe": 6,
                    },
                },
            },
        }

        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            reports_root = root / "analysis" / "reports"
            sessions_csv = root / "data" / "ENDURANCE_HRV_sessions.csv"
            sessions_csv.parent.mkdir(parents=True, exist_ok=True)
            sessions_csv.write_text(
                "\n".join(
                    [
                        "session_id,sport,work_total_min,load,z3_total_min,z3_pct",
                        "bike-h1,bike,88.0,109.0,12.0,18.0",
                        "bike-h2,bike,90.0,112.0,13.0,19.0",
                        "bike-h3,bike,92.0,114.0,14.0,20.0",
                    ]
                ),
                encoding="utf-8",
            )

            _write_longitudinal_payload(
                reports_root,
                sport="bike",
                session_id="bike-h1",
                date="2026-04-01",
                start_time="07:10",
                route_id=77,
                load=109.0,
                work_total_min=88.0,
                cardiac_drift_pct=2.4,
                subjective_score=69.0,
                subjective_state="coherent",
                thermal_score=6.7,
            )
            _write_longitudinal_payload(
                reports_root,
                sport="bike",
                session_id="bike-h2",
                date="2026-04-05",
                start_time="07:20",
                route_id=77,
                load=112.0,
                work_total_min=90.0,
                cardiac_drift_pct=2.5,
                subjective_score=70.0,
                subjective_state="coherent",
                thermal_score=6.8,
            )
            _write_longitudinal_payload(
                reports_root,
                sport="bike",
                session_id="bike-h3",
                date="2026-04-10",
                start_time="07:30",
                route_id=77,
                load=114.0,
                work_total_min=92.0,
                cardiac_drift_pct=2.6,
                subjective_score=72.0,
                subjective_state="mismatched",
                thermal_score=7.0,
            )

            ctx = build_longitudinal_context(
                session_row,
                summary,
                summary["analysis_only_context"],
                report_root=reports_root,
            )

        self.assertIsNotNone(ctx)
        self.assertTrue(ctx["route_benchmark"]["available"])
        self.assertEqual(ctx["route_benchmark"]["same_route_count"], 3)
        self.assertEqual(ctx["route_benchmark"]["same_route_climb_count"], 0)
        self.assertIsNone(ctx["route_benchmark"]["climb_economy_trend"])

    def test_build_final_report_markdown_uses_longitudinal_baseline_highlight_only_when_present(self):
        base_summary = {
            "session_cost_model": {"session_id": "i1", "usable": True, "coste_dominante": "mixto"},
            "session_row": {
                "session_id": "i1",
                "Fecha": "2026-04-14",
                "start_time": "14:08",
                "sport": "trail_run",
                "session_group": "endurance_hard",
                "moving_min": "47.0",
                "work_total_min": "47.0",
                "load": "90.0",
                "cardiac_drift_pct": "6.0",
                "vt1_used": "140",
                "vt2_used": "158",
                "zones_source": "icu",
                "z1_pct": "25.0",
                "z2_pct": "50.0",
                "z3_pct": "25.0",
                "hr_p95": "168",
                "trimp": "118.0",
                "work_n_blocks": "2",
                "work_longest_min": "16.0",
                "work_blocks_min": "16.0;14.0",
                "work_blocks_z3pct": "20;30",
                "work_avg_z3_pct": "24.0",
            },
            "subjective_context": {"rpe": 6, "feel": 3, "notes_raw": "trail"},
            "analysis_only_context": {"coach_metrics": {"session_rpe": 6}},
            "terrain_fit_context": {"climb_count": 2, "climb_gain_m": 420.0, "climb_time_min": 31.2},
            "rr_context": {"modifier": "no_rr", "interpretation": "RR no disponible", "evidence": []},
            "final_cost_interpretation": {"note": "Lectura base"},
            "rr_unavailable": False,
        }
        base_payload = {
            "meta": {
                "session_id": "i1",
                "date": "2026-04-14",
                "start_time": "14:08",
                "sport": "trail_run",
            },
            "session_row": base_summary["session_row"],
            "subjective_context": base_summary["subjective_context"],
            "analysis_only_context": base_summary["analysis_only_context"],
            "terrain_fit_context": base_summary["terrain_fit_context"],
            "context": {
                "final": {
                    "gate_badge": "VERDE",
                    "Action": "NORMAL",
                    "baseline60_degraded": "False",
                },
                "sleep": {},
                "sessions_day": {},
                "sessions_metadata": {},
            },
            "narrative_targets": {
                "final_reason_rendered": {
                    "enabled": False,
                    "reporting_mode": "caution_first",
                    "reason_items": [],
                    "action_readout": "",
                    "baseline_readout": "",
                }
            },
        }

        with_highlight = dict(base_summary)
        with_highlight["longitudinal_context"] = {
            "available": True,
            "history_count": 3,
            "history_span_days": 9,
            "sport_baseline": {
                "available": True,
                "highlight": {
                    "label": "work_total_min",
                    "percentile": 88.0,
                    "count": 4,
                },
            },
            "route_benchmark": {"available": True, "same_route_count": 3, "climb_economy_trend": "stable"},
            "subjective_chronic_context": {
                "available": True,
                "chronic_state": "watch",
                "historical_mean": 70.0,
                "mismatch_rate": 0.25,
            },
            "thermal_sensitivity_context": {
                "available": True,
                "thermal_state": "typical",
                "historical_mean": 8.2,
                "current_percentile": 55.0,
            },
        }
        payload_with_highlight = dict(base_payload)
        payload_with_highlight["longitudinal_context"] = with_highlight["longitudinal_context"]

        without_highlight = dict(base_summary)
        without_highlight["longitudinal_context"] = {
            "available": True,
            "history_count": 3,
            "history_span_days": 9,
            "sport_baseline": {
                "available": True,
                "highlight": None,
            },
            "route_benchmark": {"available": True, "same_route_count": 3, "climb_economy_trend": "stable"},
            "subjective_chronic_context": {
                "available": True,
                "chronic_state": "watch",
                "historical_mean": 70.0,
                "mismatch_rate": 0.25,
            },
            "thermal_sensitivity_context": {
                "available": True,
                "thermal_state": "typical",
                "historical_mean": 8.2,
                "current_percentile": 55.0,
            },
        }
        payload_without_highlight = dict(base_payload)
        payload_without_highlight["longitudinal_context"] = without_highlight["longitudinal_context"]

        report_with = build_final_report_markdown(payload_with_highlight, with_highlight, "sync-token-123")
        report_without = build_final_report_markdown(payload_without_highlight, without_highlight, "sync-token-123")

        self.assertIn("### Consolidación longitudinal", report_with)
        self.assertEqual(report_with.count("El mejor anclaje del baseline propio"), 1)
        self.assertNotIn("El mejor anclaje del baseline propio", report_without)
        self.assertIn("La muestra acumulada del mismo deporte suma `3` sesiones previas", report_with)

    def test_build_conversational_payload_exposes_matched_climbs_csv(self):
        session_row = _session_row(sport="road_run")
        manifest = {
            "session_id": "i1",
            "slug": "2026-03-25_09-00_road_run_i1",
            "date": "2026-03-25",
            "start_time": "09:00",
            "sport": "road_run",
            "analysis_only_context": {},
        }

        def fake_row_by_date(path, date_str):
            if path.name == "ENDURANCE_HRV_master_FINAL.csv":
                return {"Fecha": date_str, "reason_text": "ok"}
            if path.name == "ENDURANCE_HRV_master_DASHBOARD.csv":
                return {"Fecha": date_str, "reason_text": "ok"}
            return None

        with TemporaryDirectory() as tmp:
            tmpdir = Path(tmp)
            matched_climbs_path = tmpdir / "matched_climbs.csv"
            matched_climbs_path.write_text("grade_bin,early_count\nlow_grade,1\n", encoding="utf-8")
            with patch("analysis.session_analysis_pipeline.row_by_date", side_effect=fake_row_by_date), patch(
                "analysis.session_analysis_pipeline.load_optional_json", return_value=None
            ), patch(
                "analysis.session_analysis_pipeline.load_final_reason_items_lookup", return_value={}
            ), patch(
                "analysis.session_analysis_pipeline._compute_speed_metrics", return_value=None
            ):
                payload = build_conversational_payload(
                    {},
                    manifest,
                    session_row,
                    artifacts_dir=tmpdir,
                    matched_climbs_csv_path=matched_climbs_path,
                )

        self.assertEqual(payload["matched_climbs_csv"], str(matched_climbs_path))

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
                    "message": "VERDE con carga aguda 72h (acute_load_72h_rel=4.20x; load_3d=221): precaución con la intensidad",
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
                        "line": "- `green_load_caution` (`acute_load_72h_rel=4.20x`, umbral `3.9`): carga aguda 72h alta"
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
        self.assertIn("`durability_context` por tercios", prompt)
        self.assertIn("si existe `session_payload.json.durability_context`, priorizalo", prompt)

    def test_build_analyst_prompt_markdown_mentions_matched_climbs_csv(self):
        prompt = build_analyst_prompt_markdown(
            report_dir=Path("analysis/reports/example"),
            payload_path=Path("analysis/reports/example/artifacts/session_payload.json"),
            summary_path=Path("analysis/reports/example/artifacts/summary.json"),
            blocks_path=None,
            terrain_intervals_path=Path("analysis/reports/example/artifacts/terrain_intervals.csv"),
            terrain_climbs_path=Path("analysis/reports/example/artifacts/terrain_climbs.csv"),
            matched_climbs_path=Path("analysis/reports/example/artifacts/matched_climbs.csv"),
            coach_metrics_path=None,
            coach_intervals_path=None,
            coach_groups_path=None,
            report_sync_token="abc123def4567890",
        )
        self.assertIn("matched_climbs.csv", prompt)
        self.assertIn("FP-06", prompt)

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
                matched_climbs_path=Path("analysis/reports/example/artifacts/matched_climbs.csv"),
                coach_metrics_path=None,
                coach_intervals_path=None,
                coach_groups_path=None,
                debug_dir=None,
                report_sync_token="abc123def4567890",
            )
            self.assertIn("## Sincronizacion de report.auto.md", handoff)
            self.assertIn("<!-- report_sync_token: abc123def4567890 -->", handoff)
            self.assertIn("## RR orientativa", handoff)
            self.assertIn("matched_climbs.csv", handoff)

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
            "analysis_only_context": {"coach_metrics": {"session_rpe": 6, "icu_intensity_pct": 67.3}},
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
            "terrain_fit_context": {
                "climb_count": 9,
                "climb_gain_m": 843.8,
                "climb_time_min": 79.4,
                "climb_hr_mean": 160.2,
                "climb_power_estimated_mean": 215.0,
                "climb_power_source": "estimated",
                "climb_power_estimated_count": 9,
                "climb_power_measured_count": 0,
            },
            "analysis_only_context": {"coach_metrics": {"session_rpe": 6, "icu_intensity_pct": 67.3}},
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
        self.assertIn("9 subidas", report)
        self.assertIn("Aunque la sesión salió `71.8%` en Z1 global", report)
        self.assertIn("FC media en subida fue `160.2 lpm`", report)
        self.assertIn("especificidad de montaña", report)
        self.assertIn("peaje cardiovascular real", report)
        self.assertIn("proxy de `bike`", report)

    def test_build_final_report_markdown_omits_bike_power_proxy_disclaimer_when_power_is_measured(self):
        payload = {
            "meta": {
                "session_id": "i_bike_measured",
                "date": "2026-04-13",
                "start_time": "09:36",
                "sport": "bike",
            },
            "session_row": {
                "session_id": "i_bike_measured",
                "Fecha": "2026-04-13",
                "start_time": "09:36",
                "sport": "bike",
                "moving_min": "150.0",
                "duration_min": "158.0",
                "distance_km": "64.2",
                "elev_gain_m": "1120",
                "elev_loss_m": "1124",
                "hr_mean": "138",
                "hr_max": "181",
                "vt1_used": "140",
                "vt2_used": "160",
                "zones_source": "icu",
                "z1_pct": "64.0",
                "z2_pct": "20.0",
                "z3_pct": "16.0",
                "hr_p95": "170",
                "load": "165",
                "trimp": "240.0",
                "work_n_blocks": "3",
                "work_total_min": "40.5",
                "work_longest_min": "18.0",
                "work_blocks_min": "18.0;12.5;10.0",
                "work_avg_z3_pct": "72.0",
                "late_intensity": "1.0",
                "cardiac_drift_pct": "-1.5",
                "session_group": "endurance_hard",
            },
            "subjective_context": {"rpe": 6, "feel": 2, "notes_raw": "Bike con potencia medida"},
            "composite_context": {},
            "terrain_fit_context": {
                "climb_count": 5,
                "climb_gain_m": 910.0,
                "climb_time_min": 52.0,
                "climb_hr_mean": 154.0,
                "climb_power_mean": 242.0,
                "climb_power_source": "measured",
                "climb_z3_pct_mean": 18.0,
                "climb_power_measured_count": 5,
                "climb_power_estimated_count": 0,
            },
            "analysis_only_context": {},
            "context": {
                "sleep": {},
                "final": {"gate_badge": "VERDE", "Action": "NORMAL", "baseline60_degraded": "False"},
                "sessions_day": {},
                "sessions_metadata": {"training_audit": {}},
            },
            "narrative_targets": {"final_reason_rendered": {"enabled": False}},
            "rr_analysis_summary": {},
        }
        summary = {
            "session_cost_model": {"usable": True, "coste_dominante": "mecanico"},
            "duration_consistency": "OK",
            "hr_source": "FIT",
            "rr_unavailable": True,
        }
        report = build_final_report_markdown(payload, summary, "bike123")
        self.assertIn("potencia medida `242 W`", report)
        self.assertNotIn("proxy de `bike`", report)

    def test_build_final_report_markdown_includes_trail_measured_climb_power(self):
        payload = {
            "meta": {
                "session_id": "i_trail_power",
                "date": "2026-04-12",
                "start_time": "08:10",
                "sport": "trail_run",
            },
            "session_row": {
                "session_id": "i_trail_power",
                "Fecha": "2026-04-12",
                "start_time": "08:10",
                "sport": "trail_run",
                "moving_min": "82.0",
                "duration_min": "85.5",
                "distance_km": "12.4",
                "elev_gain_m": "560",
                "elev_loss_m": "548",
                "hr_mean": "149",
                "hr_max": "171",
                "vt1_used": "142",
                "vt2_used": "158",
                "zones_source": "icu",
                "z1_pct": "68.0",
                "z2_pct": "20.5",
                "z3_pct": "11.5",
                "hr_p95": "166",
                "load": "112",
                "trimp": "176.4",
                "work_n_blocks": "4",
                "work_total_min": "31.2",
                "work_longest_min": "14.4",
                "work_blocks_min": "14.4;8.6;5.8;2.4",
                "work_avg_z3_pct": "58.0",
                "late_intensity": "0.0",
                "cardiac_drift_pct": "1.8",
                "session_group": "endurance_hard",
            },
            "subjective_context": {"rpe": 6, "feel": 3, "notes_raw": "Trail con subidas sostenidas y potencia medida"},
            "composite_context": {
                "subjective_coherence": {"subjective_coherence_state": "coherent", "subjective_coherence_score": 88.4},
                "durability_context": {"durability_hint": "steady_easy", "confidence": "medium"},
                "thermal_context": {"thermal_band": "marginal", "temperature_c": 16.5},
            },
            "terrain_fit_context": {
                "climb_count": 6,
                "climb_gain_m": 472.6,
                "climb_time_min": 37.4,
                "climb_hr_mean": 160.0,
                "climb_power_mean": 266.0,
                "climb_power_source": "measured",
                "climb_z3_pct_mean": 34.2,
                "climb_power_measured_count": 6,
                "climb_power_estimated_count": 0,
            },
            "analysis_only_context": {"coach_metrics": {"session_rpe": 6, "icu_intensity_pct": 58.1}},
            "context": {
                "sleep": {
                    "polar_sleep_duration_min": "402",
                    "polar_sleep_score": "80",
                    "polar_efficiency_pct": "92.1",
                    "polar_night_rmssd": "45",
                },
                "final": {
                    "RMSSD_stable": "41.2",
                    "residual_z": "1.3",
                    "gate_badge": "VERDE",
                    "Action": "NORMAL",
                    "baseline60_degraded": "False",
                },
                "sessions_day": {
                    "load_day": "112",
                    "load_3d": "240",
                    "load_7d": "312",
                    "work_7d_sum": "58.2",
                    "z3_7d_sum": "10.2",
                },
                "sessions_metadata": {"training_audit": {}},
            },
            "narrative_targets": {
                "final_reason_rendered": {
                    "enabled": True,
                    "reporting_mode": "permission_conditional",
                    "gate_readout": "`gate_badge = VERDE` y `Action = NORMAL`",
                    "reason_items": [],
                    "action_readout": "`has_action_constraint = false` -> no hay restriccion de accion activa.",
                    "baseline_readout": "`baseline60_degraded = false` -> precision normal.",
                }
            },
            "rr_analysis_summary": {},
        }
        summary = {
            "session_cost_model": {"usable": True, "coste_dominante": "mecanico"},
            "duration_consistency": "OK",
            "hr_source": "FIT",
            "dfa_gate": {"state": "DFA_OK"},
            "hr_at_075": {"usable": False},
            "terrain_climbs": [
                {
                    "climb_index": 1,
                    "distance_km": 0.6,
                    "elev_gain_m": 120.0,
                    "duration_s": 300.0,
                    "grade_mean_pct": 20.0,
                    "hr_mean": 168.0,
                    "vam_mh": 1440.0,
                    "power_mean": 265.0,
                },
                {
                    "climb_index": 2,
                    "distance_km": 0.5,
                    "elev_gain_m": 95.0,
                    "duration_s": 250.0,
                    "grade_mean_pct": 19.0,
                    "hr_mean": 165.0,
                    "vam_mh": 1368.0,
                    "power_mean": 254.0,
                },
            ],
            "rr_unavailable": True,
        }
        report = build_final_report_markdown(payload, summary, "trail123")
        self.assertIn("potencia medida `266 W`", report)
        self.assertIn("W/kg atleta", report)
        self.assertIn("subidas concentraron `34.2%` en Z3", report)
        self.assertIn("Trail running", report)
        self.assertIn("| # | Km | D+ | Tiempo | Pend. | FC media | VAM | Ritmo |", report)
        self.assertNotIn("| # | Km | D+ | Tiempo | Pend. | FC media | VAM | Ritmo | Potencia |", report)
        self.assertIn("8:20", report)

        structure_section = report.split("## Respuesta interna", 1)[0]
        self.assertIn("En la capa FIT aparecen `6` climbs", structure_section)
        self.assertIn("potencia medida `266 W`", structure_section)

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
            "analysis_only_context": {"coach_metrics": {"session_rpe": 6, "icu_intensity_pct": 54.2}},
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

    def test_recent_block_rows_inserts_rest_day_for_calendar_gap(self):
        from analysis.session_analysis_pipeline import _build_recent_block_rows_with_rest_days

        session_row = {
            "session_id": "i144733291",
            "Fecha": "2026-05-02",
            "start_time": "08:01",
        }
        rows = [
            {"Fecha": "2026-05-01", "session_id": "i1", "start_time": "08:05", "sport": "bike", "moving_min": "148.8", "elev_gain_m": "1169", "work_total_min": "29.3", "load": "93"},
            {"Fecha": "2026-04-29", "session_id": "i2", "start_time": "07:10", "sport": "bike", "moving_min": "119.7", "elev_gain_m": "835", "work_total_min": "5.5", "load": "68"},
            {"Fecha": "2026-04-29", "session_id": "i3", "start_time": "18:30", "sport": "strength", "moving_min": "56.3", "elev_gain_m": "", "work_total_min": "0", "load": "7"},
            {"Fecha": "2026-04-28", "session_id": "i4", "start_time": "07:45", "sport": "elliptical", "moving_min": "79.9", "elev_gain_m": "", "work_total_min": "0", "load": "44"},
        ]

        with patch("analysis.session_analysis_pipeline.load_optional_rows", return_value=rows):
            enriched, had_rest_day = _build_recent_block_rows_with_rest_days(session_row)

        self.assertTrue(had_rest_day)
        self.assertEqual(enriched[1]["sport"], "descanso")
        self.assertEqual(enriched[1]["Fecha"], "2026-04-30")
        self.assertEqual(enriched[1]["load"], 0.0)
        self.assertEqual(enriched[1]["work_total_min"], 0.0)

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
            "analysis_only_context": {"coach_metrics": {"session_rpe": 6, "icu_intensity_pct": 54.2}},
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

    def test_build_final_report_markdown_includes_analysis_durability_mechanical_drop(self):
        payload = {
            "meta": {
                "session_id": "i_road_durability",
                "date": "2026-04-13",
                "start_time": "08:10",
                "sport": "road_run",
            },
            "session_row": {
                "session_id": "i_road_durability",
                "Fecha": "2026-04-13",
                "start_time": "08:10",
                "sport": "road_run",
                "moving_min": "121.0",
                "duration_min": "123.0",
                "distance_km": "21.2",
                "elev_gain_m": "95",
                "hr_mean": "149",
                "vt1_used": "140",
                "vt2_used": "158",
                "zones_source": "icu",
                "z2_pct": "47.0",
                "z3_pct": "18.0",
                "hr_p95": "166",
                "load": "102",
                "trimp": "152.4",
                "work_n_blocks": "1",
                "work_total_min": "24.0",
                "work_longest_min": "24.0",
                "work_blocks_min": "24.0",
                "speed_first_half": "12.2",
                "speed_second_half": "11.8",
                "session_group": "tempo",
            },
            "subjective_context": {"rpe": 6, "feel": 3, "notes_raw": "Rodaje sostenido con fatiga final"},
            "composite_context": {},
            "durability_context": {
                "durability_pattern": "mechanical_drop_with_drift",
                "preferred_signal": "power_ratio",
                "power_ratio": 0.94,
                "decoupling_pct": 11.6,
                "interpretation_confidence": "high",
            },
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
                    "load_day": "102",
                    "load_3d": "210",
                    "load_7d": "320",
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
            "rr_unavailable": False,
        }

        report = build_final_report_markdown(payload, summary, "durability123")
        self.assertIn("caída mecánica acompañada de deriva", report)
        self.assertIn("`power_ratio = 0.940`", report)
        self.assertIn("peaje periférico real", report)

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

    def test_build_final_report_markdown_includes_analysis_durability_terrain_ambiguity(self):
        payload = {
            "meta": {
                "session_id": "i_trail_durability",
                "date": "2026-04-14",
                "start_time": "14:08",
                "sport": "trail_run",
            },
            "session_row": {
                "session_id": "i_trail_durability",
                "Fecha": "2026-04-14",
                "start_time": "14:08",
                "sport": "trail_run",
                "moving_min": "132.0",
                "duration_min": "138.0",
                "distance_km": "17.1",
                "elev_gain_m": "920",
                "hr_mean": "147",
                "vt1_used": "140",
                "vt2_used": "158",
                "zones_source": "icu",
                "z2_pct": "42.0",
                "z3_pct": "21.0",
                "hr_p95": "169",
                "load": "118",
                "trimp": "165.2",
                "work_n_blocks": "1",
                "work_total_min": "26.0",
                "work_longest_min": "26.0",
                "work_blocks_min": "26.0",
                "speed_first_half": "9.60",
                "speed_second_half": "8.70",
                "session_group": "endurance",
            },
            "subjective_context": {"rpe": 5, "feel": 3, "notes_raw": "Trail largo con segunda mitad rota"},
            "composite_context": {},
            "durability_context": {
                "durability_pattern": "ambiguous_due_to_terrain",
                "preferred_signal": "speed_ratio",
                "speed_ratio": 0.906,
                "decoupling_pct": 7.4,
                "terrain_sensitivity": "high",
                "interpretation_confidence": "low",
            },
            "terrain_fit_context": {},
            "analysis_only_context": {},
            "context": {
                "sleep": {
                    "polar_sleep_duration_min": "430",
                    "polar_sleep_score": "81",
                    "polar_efficiency_pct": "93.0",
                    "polar_night_rmssd": "46",
                },
                "final": {
                    "RMSSD_stable": "41.70",
                    "residual_z": "1.20",
                    "gate_badge": "VERDE+++",
                    "Action": "INTENSIDAD_OK",
                    "baseline60_degraded": "False",
                    "reason_text": "VERDE",
                },
                "sessions_day": {
                    "load_day": "118",
                    "load_3d": "240",
                    "load_7d": "360",
                    "work_7d_sum": "66.0",
                    "z3_7d_sum": "22.5",
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
            "session_cost_model": {"usable": True, "coste_dominante": "mixto"},
            "duration_consistency": "OK",
            "hr_source": "FIT",
            "dfa_gate": {"state": "DFA_OK"},
            "hr_at_075": {"usable": False},
            "rr_unavailable": False,
        }

        report = build_final_report_markdown(payload, summary, "durabilityterrain123")
        self.assertIn("ambigua por terreno", report)
        self.assertIn("`speed_ratio = 0.906`", report)
        self.assertIn("no permite cerrar fatiga periférica limpia", report)

    def test_build_final_report_markdown_uses_power_ratio_first_in_simple_trail(self):
        payload = {
            "meta": {
                "session_id": "i_trail_simple",
                "date": "2026-04-14",
                "start_time": "10:30",
                "sport": "trail_run",
            },
            "session_row": {
                "session_id": "i_trail_simple",
                "Fecha": "2026-04-14",
                "start_time": "10:30",
                "sport": "trail_run",
                "moving_min": "108.0",
                "duration_min": "110.0",
                "distance_km": "14.8",
                "elev_gain_m": "640.0",
                "hr_mean": "144",
                "vt1_used": "140",
                "vt2_used": "158",
                "zones_source": "icu",
                "z2_pct": "41.0",
                "z3_pct": "16.0",
                "hr_p95": "162",
                "load": "98",
                "trimp": "138.8",
                "work_n_blocks": "1",
                "work_total_min": "24.0",
                "work_longest_min": "24.0",
                "work_blocks_min": "24.0",
                "speed_first_half": "9.10",
                "speed_second_half": "9.18",
                "session_group": "endurance",
            },
            "subjective_context": {"rpe": 5, "feel": 3, "notes_raw": "Trail continuo con subida estable"},
            "composite_context": {},
            "durability_context": {
                "durability_pattern": "stable_output",
                "preferred_signal": "power_ratio",
                "power_ratio": 1.01,
                "speed_ratio": 1.009,
                "decoupling_pct": 4.6,
                "interpretation_confidence": "medium",
            },
            "terrain_fit_context": {},
            "analysis_only_context": {},
            "context": {
                "sleep": {
                    "polar_sleep_duration_min": "435",
                    "polar_sleep_score": "83",
                    "polar_efficiency_pct": "94.0",
                    "polar_night_rmssd": "47",
                },
                "final": {
                    "RMSSD_stable": "42.10",
                    "residual_z": "1.10",
                    "gate_badge": "VERDE+++",
                    "Action": "INTENSIDAD_OK",
                    "baseline60_degraded": "False",
                    "reason_text": "VERDE",
                },
                "sessions_day": {
                    "load_day": "98",
                    "load_3d": "208",
                    "load_7d": "318",
                    "work_7d_sum": "58.0",
                    "z3_7d_sum": "20.4",
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
            "session_cost_model": {"usable": True, "coste_dominante": "mixto"},
            "duration_consistency": "OK",
            "hr_source": "FIT",
            "dfa_gate": {"state": "DFA_OK"},
            "hr_at_075": {"usable": False},
            "rr_unavailable": False,
        }

        report = build_final_report_markdown(payload, summary, "trailsimple123")
        self.assertIn("si la durabilidad es simple, `power_ratio` manda sobre `speed_ratio`", report)
        self.assertIn("En trail simple, la lectura limpia prioriza `power_ratio`", report)
        self.assertIn("`speed_ratio` solo acompaña y no debe mandar sobre el perfil del terreno", report)

    def test_build_final_report_markdown_reframes_many_blocks_into_one_dominant_hard_block(self):
        payload = {
            "meta": {
                "session_id": "i_trail_block_shape",
                "date": "2026-04-21",
                "start_time": "14:56",
                "sport": "trail_run",
            },
            "session_row": {
                "session_id": "i_trail_block_shape",
                "Fecha": "2026-04-21",
                "start_time": "14:56",
                "sport": "trail_run",
                "moving_min": "61.6",
                "duration_min": "62.5",
                "distance_km": "8.75",
                "elev_gain_m": "245.0",
                "hr_mean": "149",
                "vt1_used": "143",
                "vt2_used": "161",
                "zones_source": "icu",
                "z2_pct": "34.0",
                "z3_pct": "15.5",
                "hr_p95": "167",
                "load": "65",
                "trimp": "114.6",
                "work_n_blocks": "5",
                "work_total_min": "34.2",
                "work_longest_min": "11.4",
                "work_blocks_min": "3.3;3.5;11.4;9.0;7.0",
                "work_blocks_z3pct": "0;0;75;0;14",
                "work_avg_z3_pct": "28",
                "late_intensity": "0",
                "cardiac_drift_pct": "-14.0",
                "session_group": "endurance_hard",
            },
            "subjective_context": {"rpe": 6, "feel": 3, "notes_raw": "La subida larga se apretó conscientemente"},
            "composite_context": {},
            "durability_context": {
                "durability_pattern": "not_applicable",
                "applicability_reason": "sessions_csv_durability_applicable=0",
            },
            "work_block_context": {
                "available": True,
                "hard_work_blocks": 1,
                "very_hard_work_blocks": 1,
                "dominant_work_block_index": 3,
                "dominant_work_block_min": 11.4,
                "dominant_work_block_share": 0.333,
                "work_block_pattern": "one_dominant_hard_block",
            },
            "terrain_fit_context": {},
            "analysis_only_context": {},
            "context": {
                "sleep": {
                    "polar_sleep_duration_min": "430",
                    "polar_sleep_score": "81",
                    "polar_efficiency_pct": "93.0",
                    "polar_night_rmssd": "46",
                },
                "final": {
                    "RMSSD_stable": "41.70",
                    "residual_z": "1.20",
                    "gate_badge": "VERDE--",
                    "Action": "INTENSIDAD_OK",
                    "baseline60_degraded": "False",
                    "reason_text": "VERDE--",
                },
                "sessions_day": {
                    "load_day": "65",
                    "load_3d": "180",
                    "load_7d": "320",
                    "work_7d_sum": "52.0",
                    "z3_7d_sum": "19.4",
                },
                "sessions_metadata": {"training_audit": {}},
            },
            "narrative_targets": {
                "final_reason_rendered": {
                    "enabled": True,
                    "reporting_mode": "caution_first",
                    "gate_readout": "`gate_badge = VERDE--` y `Action = INTENSIDAD_OK`",
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
            "dfa_gate": {"state": "DFA_NO_INTERPRETABLE"},
            "hr_at_075": {"usable": False},
            "rr_unavailable": False,
        }

        report = build_final_report_markdown(payload, summary, "hardblock123")
        self.assertIn("la dureza real quedó concentrada en `1` bloque duro dominante de `11.4 min`", report)
        self.assertIn("La dureza real no equivale a todos los bloques útiles", report)

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
                "coach_metrics": {"session_rpe": 6, "icu_intensity_pct": 54.2},
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

    def test_build_best_block_comparator_prefers_foot_family_over_bike_for_trail(self):
        current = _session_row(
            sport="trail_run",
            session_group="endurance_easy",
            load="53",
            work_total_min="0",
        )
        recent_rows = [
            _session_row(
                session_id="i_bike_easy",
                Fecha="2026-04-24",
                sport="bike",
                session_group="endurance_easy",
                load="54",
                work_total_min="0",
            ),
            _session_row(
                session_id="i_road_easy",
                Fecha="2026-04-23",
                sport="road_run",
                session_group="endurance_easy",
                load="56",
                work_total_min="0",
            ),
        ]

        comparator = _build_best_block_comparator("trail", current, recent_rows)

        self.assertIsNotNone(comparator)
        self.assertIn("`i_road_easy`", comparator)
        self.assertNotIn("`i_bike_easy`", comparator)

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

    def test_build_conversational_payload_exposes_longitudinal_context_minimal(self):
        with TemporaryDirectory() as tmp:
            tmpdir = Path(tmp)
            reports_root = tmpdir / "reports"
            sessions_csv = tmpdir / "ENDURANCE_HRV_sessions.csv"
            sessions_csv.write_text(
                "\n".join(
                    [
                        "session_id,Fecha,start_time,sport,work_total_min,load,z3_total_min,z3_pct",
                        "s_prev_1,2026-04-10,14:00,trail_run,40.0,80,10.0,25.0",
                        "s_prev_2,2026-04-11,14:00,trail_run,42.0,82,11.0,26.0",
                        "s_prev_3,2026-04-12,14:00,trail_run,44.0,84,12.0,27.0",
                        "s_current,2026-04-14,14:08,trail_run,47.0,90,13.0,28.0",
                    ]
                ),
                encoding="utf-8",
            )

            def _write_payload(
                session_id: str,
                date: str,
                start_time: str,
                load: float,
                work_total_min: float,
                cardiac_drift_pct: float,
                subjective_score: float,
                thermal_cost_score: float,
                route_id: int,
                climb_gain_m: float,
                climb_time_min: float,
                climb_hr_mean: float,
            ) -> None:
                payload_path = (
                    reports_root
                    / date[:4]
                    / date[5:7]
                    / f"{date}_{start_time.replace(':', '-')}_trail_run_{session_id}"
                    / "artifacts"
                    / "session_payload.json"
                )
                payload_path.parent.mkdir(parents=True, exist_ok=True)
                payload_path.write_text(
                    json.dumps(
                        {
                            "meta": {
                                "session_id": session_id,
                                "date": date,
                                "start_time": start_time,
                                "sport": "trail_run",
                            },
                            "session_row": {
                                "session_id": session_id,
                                "Fecha": date,
                                "start_time": start_time,
                                "sport": "trail_run",
                                "route_id": route_id,
                                "load": load,
                                "work_total_min": work_total_min,
                                "cardiac_drift_pct": cardiac_drift_pct,
                            },
                            "analysis_only_context": {
                                "route_context": {"route_id": route_id},
                                "composite_context": {
                                    "subjective_coherence": {
                                        "subjective_coherence_state": "mixed",
                                        "subjective_coherence_score": subjective_score,
                                        "objective_anchor": 72.0,
                                        "objective_spread_pct": 8.0,
                                        "subjective_objective_gap_pct": 14.0,
                                    },
                                    "thermal_context": {
                                        "thermal_cost_score": thermal_cost_score,
                                        "thermal_band": "moderate",
                                    },
                                    "durability_context": {
                                        "durability_hint": "stable",
                                        "confidence": "medium",
                                    },
                                    "coach_metrics": {
                                        "session_rpe": 6,
                                    },
                                },
                            },
                            "terrain_fit_context": {
                                "climb_gain_m": climb_gain_m,
                                "climb_time_min": climb_time_min,
                                "climb_hr_mean": climb_hr_mean,
                            },
                        }
                    ),
                    encoding="utf-8",
                )

            _write_payload("s_prev_1", "2026-04-10", "14:00", 80.0, 40.0, 4.0, 78.0, 4.0, 42, 780.0, 39.0, 154.0)
            _write_payload("s_prev_2", "2026-04-11", "14:00", 82.0, 42.0, 5.0, 74.0, 5.5, 42, 790.0, 40.0, 155.0)
            _write_payload("s_prev_3", "2026-04-12", "14:00", 84.0, 44.0, 6.0, 70.0, 6.5, 42, 800.0, 41.0, 156.0)

            summary = {
                "session_cost_model": {"usable": True, "coste_dominante": "cardio"},
                "terrain_fit_context": {"climb_gain_m": 845.0, "climb_time_min": 42.0, "climb_hr_mean": 157.0},
                "composite_context": {
                    "subjective_coherence": {
                        "subjective_coherence_state": "mismatched",
                        "subjective_coherence_score": 62.0,
                        "objective_anchor": 75.0,
                        "objective_spread_pct": 10.0,
                        "subjective_objective_gap_pct": 17.0,
                    },
                    "thermal_context": {
                        "thermal_cost_score": 8.0,
                        "thermal_band": "moderate",
                    },
                    "durability_context": {
                        "durability_hint": "fade_like",
                        "confidence": "medium",
                    },
                    "coach_metrics": {
                        "session_rpe": 6,
                    },
                },
                "analysis_only_context": {
                    "route_context": {"route_id": 42},
                    "composite_context": {
                        "subjective_coherence": {
                            "subjective_coherence_state": "mismatched",
                            "subjective_coherence_score": 62.0,
                            "objective_anchor": 75.0,
                            "objective_spread_pct": 10.0,
                            "subjective_objective_gap_pct": 17.0,
                        },
                        "thermal_context": {
                            "thermal_cost_score": 8.0,
                            "thermal_band": "moderate",
                        },
                        "durability_context": {
                            "durability_hint": "fade_like",
                            "confidence": "medium",
                        },
                        "coach_metrics": {
                            "session_rpe": 6,
                        },
                    },
                },
                "subjective_context": {
                    "rpe": 6,
                    "feel": 3,
                    "notes_present": True,
                    "notes_raw": "test",
                },
                "rr_context": {},
                "final_cost_interpretation": {},
                "rr_analysis_summary": {},
            }
            manifest = {
                "session_id": "s_current",
                "slug": "2026-04-14_14-08_trail_run_s_current",
                "date": "2026-04-14",
                "start_time": "14:08",
                "sport": "trail_run",
                "fit_path": None,
                "fit_info": None,
                "fit_error": None,
                "hr_stream_csv": None,
                "rr_csv": None,
                "terrain_error": None,
                "terrain_intervals_error": None,
                "analysis_only_context": summary["analysis_only_context"],
                "terrain_intervals": [],
            }
            session_row = _session_row(
                session_id="s_current",
                Fecha="2026-04-14",
                start_time="14:08",
                sport="trail_run",
                route_id="42",
                moving_min="47.0",
                duration_min="47.0",
                load="90.0",
                trimp="102.0",
                cardiac_drift_pct="6.0",
                work_total_min="47.0",
                work_longest_min="16.0",
                work_n_blocks="3",
                work_avg_z3_pct="22.0",
                z2_pct="20.0",
                z3_pct="28.0",
                z2_total_min="10.0",
                z3_total_min="13.0",
                session_group="endurance",
            )

            with patch("analysis.session_analysis_pipeline.DEFAULT_REPORTS_DIR", reports_root), patch(
                "analysis.session_analysis_pipeline.DEFAULT_SESSIONS_CSV", sessions_csv
            ), patch("analysis.session_analysis_pipeline.ROOT", tmpdir):
                payload = build_conversational_payload(summary, manifest, session_row, artifacts_dir=tmpdir / "artifacts")
                longitudinal = payload.get("longitudinal_context") or {}
                self.assertTrue(longitudinal)
                self.assertTrue(longitudinal.get("route_benchmark", {}).get("available"))
                self.assertEqual(longitudinal.get("route_benchmark", {}).get("same_route_count"), 3)
                self.assertEqual(longitudinal.get("subjective_chronic_context", {}).get("available"), True)
                self.assertEqual(longitudinal.get("thermal_sensitivity_context", {}).get("available"), True)
                report = build_final_report_markdown(payload, summary, "sync-token")
                self.assertIn("Consolidación longitudinal", report)
                self.assertIn("benchmark de ruta", report)
                self.assertIn("sensibilidad térmica longitudinal", report)

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

    def test_build_cost_model_result_raises_trail_mechanical_score_for_steep_work_intense_session(self):
        result = build_cost_model_result(
            _session_row(
                sport="trail_run",
                moving_min="61.6",
                elev_gain_m="245.0",
                elev_loss_m="250.2",
                elev_density="28.0",
                z2_pct="35.7",
                z3_pct="15.5",
                hr_p95="167.0",
                work_n_blocks="5",
                work_total_min="34.2",
                work_longest_min="11.4",
                work_avg_z3_pct="28.0",
            )
        )
        self.assertEqual(result["mecanico_score"], 3)
        self.assertEqual(result["coste_dominante"], "mixto")
        self.assertIn("D+/h = 239", result["mecanico_evidence"])
        self.assertIn("umbral trail = D+/h>=220", result["mecanico_evidence"])
        self.assertIn("bloque tecnico trail: work_n_blocks = 5, work_avg_z3_pct = 28.0", result["mecanico_evidence"])
        self.assertEqual(result["mecanico_basis"], result["mecanico_evidence"])

    def test_build_cost_model_result_does_not_apply_trail_bonus_on_fallback_zones(self):
        result = build_cost_model_result(
            _session_row(
                sport="trail_run",
                moving_min="61.6",
                elev_gain_m="245.0",
                elev_loss_m="250.2",
                elev_density="28.0",
                z2_pct="35.7",
                z3_pct="15.5",
                hr_p95="167.0",
                work_n_blocks="5",
                work_total_min="34.2",
                work_longest_min="11.4",
                work_avg_z3_pct="28.0",
                zones_source="fallback",
            )
        )
        self.assertEqual(result["mecanico_score"], 2)
        self.assertIn("zones_source = fallback; bonus tecnico trail no aplicado", result["mecanico_evidence"])
        self.assertNotIn("bloque tecnico trail: work_n_blocks = 5, work_avg_z3_pct = 28.0", result["mecanico_evidence"])

    def test_render_report_includes_mechanical_basis_in_cost_model_section(self):
        summary = {
            "session_cost_model": {
                "session_id": "i1",
                "usable": True,
                "cardio_score": 3,
                "mecanico_score": 2,
                "coste_dominante": "cardiometabolico",
                "confidence_cardio": "high",
                "confidence_mecanico": "high",
                "mecanico_basis": ["D+/h = 239", "umbral trail = D+/h>=220"],
            },
            "session_row": {"sport": "trail_run"},
            "rr_context": {"modifier": "available", "interpretation": "RR usable", "evidence": []},
            "final_cost_interpretation": {"note": "Lectura base"},
            "rr_unavailable": False,
        }
        report = render_report_markdown(summary)
        self.assertIn("Base mecánica", report)
        self.assertIn("D+/h = 239; umbral trail = D+/h>=220", report)

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

    def test_build_final_report_markdown_omits_internal_shadow_context_from_human_report(self):
        summary = {
            "session_cost_model": {"session_id": "i4", "usable": True},
            "session_row": {"sport": "trail_run"},
            "rr_context": {"modifier": "no_rr", "interpretation": "RR no disponible", "evidence": []},
            "final_cost_interpretation": {"note": "Lectura base"},
            "terrain_context": {
                "split_count": 3,
                "split_coverage_pct": 81.2,
            },
            "terrain_fit_context": {
                "climb_count": 4,
                "climb_gain_m": 780.0,
                "climb_time_min": 41.5,
            },
            "runaware_context": {
                "source": "combined",
                "strength": "strong",
                "strength_basis": [
                    "terrain_ready=true",
                    "power_ready=true",
                    "run_power_available=1",
                    "combined_evidence=terrain_plus_power",
                ],
                "shadow_only": True,
                "terrain_ready": True,
                "run_power_available": 1,
                "power_ratio": 0.964,
                "terrain_climb_count": 4,
                "terrain_gap_mean": 8.6,
                "terrain_vam_uphill_mean": 462.0,
            },
            "v1_snapshot": {
                "intensity_clustering_flag": 0,
                "intensity_clustering_severity": None,
            },
            "v1_shadow_comparison": {
                "alignment": "divergent",
                "flag_alignment": "mismatch",
                "severity_alignment": None,
                "notes": ["v1 y sombra discrepan en activacion binaria"],
            },
            "v1_shadow_history": {
                "row_count": 2,
                "comparable_count": 2,
                "aligned_count": 1,
                "divergent_count": 1,
                "aligned_rate": 0.5,
                "shadow_positive_count": 0,
                "shadow_positive_rate": 0.0,
                "window_summaries": {
                    5: {
                        "row_count": 2,
                        "comparable_count": 2,
                        "aligned_count": 1,
                        "divergent_count": 1,
                        "aligned_rate": 0.5,
                        "shadow_positive_count": 0,
                        "shadow_positive_rate": 0.0,
                    }
                },
                "rows": [
                    {
                        "date": "2026-04-12",
                        "session_id": "i4",
                        "v1_flag": 0,
                        "v1_severity": None,
                        "shadow_session_candidate": 1,
                        "shadow_session_severity": "high",
                        "shadow_candidate": 0,
                        "shadow_severity": None,
                        "shadow_source": "combined",
                        "alignment": "aligned",
                    },
                    {
                        "date": "2026-04-10",
                        "session_id": "i3",
                        "v1_flag": 1,
                        "v1_severity": "low",
                        "shadow_session_candidate": 1,
                        "shadow_session_severity": "high",
                        "shadow_candidate": 0,
                        "shadow_severity": None,
                        "shadow_source": "terrain",
                        "alignment": "divergent",
                    },
                ],
            },
        }
        payload = {
            "meta": {"session_id": "i4", "slug": "s", "date": "2026-04-12", "start_time": "08:00", "sport": "trail_run", "sport_family": "trail"},
            "session_row": {"sport": "trail_run"},
            "subjective_context": {},
            "composite_context": {},
            "durability_context": {},
            "work_block_context": {},
            "rr_analysis_summary": {},
            "terrain_context": summary["terrain_context"],
            "terrain_fit_context": summary["terrain_fit_context"],
            "runaware_context": summary["runaware_context"],
            "analysis_only_context": {"runaware_context": summary["runaware_context"]},
            "final_reason_items": [],
            "final_reason_flags": {},
            "final_reason_items_contract": {"fallback_to_reason_text": True},
            "terrain_intervals_csv": None,
            "terrain_climbs_csv": None,
            "coach_metrics_json": None,
            "coach_intervals_csv": None,
            "coach_groups_csv": None,
            "context": {"sessions_day": {}, "sleep": {}, "final": {"gate_badge": "VERDE", "Action": "Normal", "reason_text": "ok"}, "dashboard": {}, "sessions_metadata": None, "runaware_context": summary["runaware_context"]},
            "narrative_targets": {"final_reason_rendered": {"enabled": False}},
        }
        report = build_final_report_markdown(payload, summary, "abc123def4567890")
        self.assertNotIn("Capa run-aware en sombra", report)
        self.assertNotIn("Comparación v1 vs sombra", report)
        self.assertNotIn("Concordancia histórica", report)
        self.assertIn("En la capa FIT aparecen `4` climbs", report)

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

    def test_supports_terrain_context_accepts_bike_outdoor_and_uses_rpm(self):
        self.assertTrue(
            _supports_terrain_context(
                {
                    "sport": "bike",
                    "sport_raw": "Cycling",
                    "polar_sport_raw": "cycling",
                }
            )
        )
        self.assertEqual(_terrain_fit_cadence_unit({"sport": "bike"}), "rpm")
        self.assertEqual(_terrain_fit_cadence_unit({"sport": "trail_run"}), "strides_per_min")

    def test_supports_terrain_context_accepts_hike_outdoor_and_uses_stride_cadence(self):
        self.assertTrue(
            _supports_terrain_context(
                {
                    "sport": "hike",
                    "sport_raw": "Hiking",
                    "polar_sport_raw": "hiking",
                }
            )
        )
        self.assertEqual(_terrain_fit_cadence_unit({"sport": "hike"}), "strides_per_min")

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


class TestBikePowerEstimation(unittest.TestCase):
    def _make_climb_records(self, n_seconds: int = 300, speed_mps: float = 4.0, grade_pct: float = 6.0) -> list[dict]:
        records = []
        distance = 0.0
        altitude = 100.0
        elev_per_sec = speed_mps * (grade_pct / 100.0)
        for sec in range(n_seconds):
            distance += speed_mps
            altitude += elev_per_sec
            records.append({
                "sec": float(sec),
                "distance_m": round(distance, 2),
                "altitude_m": round(altitude, 2),
                "hr": 155.0,
                "cadence": 80.0,
                "paused": False,
            })
        return records

    def test_estimate_climb_power_physics_reasonable(self):
        from analysis.fit_terrain_utils import _estimate_climb_power_w
        # 80kg sistema, 6% pendiente, 15 km/h (~4.17 m/s)
        p = _estimate_climb_power_w(
            distance_m=1250.0,
            duration_s=300.0,
            elev_gain_m=75.0,
            system_bike_weight_kg=80.0,
        )
        self.assertIsNotNone(p)
        # Rango fisiológico razonable para 80kg a 6% pendiente: 200-320W
        self.assertGreater(p, 200.0)
        self.assertLess(p, 320.0)

    def test_estimate_climb_power_returns_none_on_zero_distance(self):
        from analysis.fit_terrain_utils import _estimate_climb_power_w
        self.assertIsNone(_estimate_climb_power_w(0.0, 300.0, 60.0, 80.0))
        self.assertIsNone(_estimate_climb_power_w(1000.0, 0.0, 60.0, 80.0))

    def test_analyze_terrain_records_populates_estimated_power_when_no_fit_power(self):
        records = self._make_climb_records()
        result = analyze_terrain_records(
            records=records,
            pause_filter_mode="heuristic_stationary",
            session_elev_gain_m=300.0,
            system_bike_weight_kg=80.0,
        )
        ctx = result["terrain_fit_context"]
        self.assertIsNotNone(ctx.get("climb_power_estimated_mean"))
        self.assertIsNotNone(ctx.get("climb_power_estimated_max"))
        self.assertEqual(ctx.get("climb_power_source"), "estimated")
        self.assertIsNotNone(ctx.get("session_altitude_m"))
        self.assertEqual(ctx.get("session_altitude_samples"), len(records))
        self.assertGreater(ctx.get("session_altitude_m"), ctx.get("session_altitude_start_m"))
        climbs = result["terrain_climbs"]
        self.assertTrue(all(c.get("power_source") == "estimated" for c in climbs))
        self.assertTrue(all(c.get("power_estimated_mean") is not None for c in climbs))

    def test_analyze_terrain_records_skips_estimation_when_fit_power_present(self):
        records = self._make_climb_records()
        for r in records:
            r["power"] = 250.0
        result = analyze_terrain_records(
            records=records,
            pause_filter_mode="heuristic_stationary",
            session_elev_gain_m=300.0,
            system_bike_weight_kg=80.0,
        )
        ctx = result["terrain_fit_context"]
        self.assertIsNone(ctx.get("climb_power_estimated_mean"))
        self.assertEqual(ctx.get("climb_power_source"), "measured")

    def test_analyze_terrain_records_mixed_power_source(self):
        # First climb: measured power; second climb: no measured power → estimated
        # Build two separate climbs with a flat gap between them
        climb1 = self._make_climb_records(n_seconds=300)
        for r in climb1:
            r["power"] = 250.0  # measured

        flat_gap = []
        base_sec = float(climb1[-1]["sec"]) + 1.0
        base_dist = climb1[-1]["distance_m"]
        base_alt = climb1[-1]["altitude_m"]
        for i in range(120):
            base_dist += 6.0
            flat_gap.append({
                "sec": base_sec + i,
                "distance_m": round(base_dist, 2),
                "altitude_m": round(base_alt, 2),
                "hr": 130.0,
                "cadence": 80.0,
                "paused": False,
            })

        climb2 = []
        base_sec2 = flat_gap[-1]["sec"] + 1.0
        base_dist2 = flat_gap[-1]["distance_m"]
        base_alt2 = flat_gap[-1]["altitude_m"]
        for i in range(300):
            base_dist2 += 4.0
            base_alt2 += 0.24
            climb2.append({
                "sec": base_sec2 + i,
                "distance_m": round(base_dist2, 2),
                "altitude_m": round(base_alt2, 2),
                "hr": 155.0,
                "cadence": 75.0,
                "paused": False,
                # no power field → will trigger estimation if weight provided
            })

        records = climb1 + flat_gap + climb2
        result = analyze_terrain_records(
            records=records,
            pause_filter_mode="heuristic_stationary",
            session_elev_gain_m=150.0,
            system_bike_weight_kg=80.0,
        )
        ctx = result["terrain_fit_context"]
        self.assertEqual(ctx.get("climb_power_source"), "mixed")
        self.assertGreater(ctx.get("climb_power_measured_count", 0), 0)
        self.assertGreater(ctx.get("climb_power_estimated_count", 0), 0)
        # estimated mean must reflect only the estimated climbs (not None)
        self.assertIsNotNone(ctx.get("climb_power_estimated_mean"))

    def test_analyze_terrain_records_no_estimation_without_weight(self):
        records = self._make_climb_records()
        result = analyze_terrain_records(
            records=records,
            pause_filter_mode="heuristic_stationary",
            session_elev_gain_m=300.0,
        )
        ctx = result["terrain_fit_context"]
        self.assertIsNone(ctx.get("climb_power_estimated_mean"))
        self.assertIsNone(ctx.get("climb_power_source"))

    def test_climb_thresholds_bike_stricter_than_trail(self):
        """bike thresholds must be >= trail thresholds for distance and product."""
        from analysis.fit_terrain_utils import _climb_thresholds
        bike = _climb_thresholds("bike")
        trail = _climb_thresholds("trail")
        self.assertGreaterEqual(bike["min_distance_m"], trail["min_distance_m"])
        self.assertGreaterEqual(bike["min_product"], trail["min_product"])

    def test_trail_climb_passes_trail_thresholds_but_fails_bike(self):
        """A short steep trail climb (200 m, 10%) passes trail but not bike filters."""
        from analysis.fit_terrain_utils import _climb_thresholds
        dist_m = 200.0
        grade_pct = 10.0
        product = dist_m * grade_pct  # 2000 > 300 (trail ok), but dist < 300 (bike fails)
        bike = _climb_thresholds("bike")
        trail = _climb_thresholds("trail")
        self.assertLess(dist_m, bike["min_distance_m"])          # filtered out by bike
        self.assertGreaterEqual(dist_m, trail["min_distance_m"]) # passes trail
        self.assertGreaterEqual(product, trail["min_product"])   # passes trail product

    def test_sport_family_propagated_to_detect_climbs_trail(self):
        """trail sport_family uses permissive thresholds: a 200 m climb passes."""
        # Build a climb: 200 m at ~10% grade (20 m gain) over 60 s → passes trail, fails bike
        records = []
        for i in range(65):
            records.append({
                "sec": float(i),
                "distance_m": round(i * (200.0 / 60), 2),
                "altitude_m": round(100.0 + i * (20.0 / 60), 2),
                "hr": 150.0,
                "cadence": 75.0,
                "paused": False,
            })
        result_trail = analyze_terrain_records(
            records=records,
            pause_filter_mode="heuristic_stationary",
            session_elev_gain_m=20.0,
            sport_family="trail",
        )
        result_bike = analyze_terrain_records(
            records=records,
            pause_filter_mode="heuristic_stationary",
            session_elev_gain_m=20.0,
            sport_family="bike",
        )
        self.assertGreater(result_trail["terrain_fit_context"]["climb_count"], 0,
                           "trail should detect the short steep climb")
        self.assertEqual(result_bike["terrain_fit_context"]["climb_count"], 0,
                         "bike should filter out the short climb")

    def test_road_sport_family_uses_run_thresholds_not_bike(self):
        """road_run → sport_family='road' must use run thresholds (150 m), not bike (300 m)."""
        from analysis.fit_terrain_utils import _climb_thresholds
        road = _climb_thresholds("road")
        run  = _climb_thresholds("run")
        bike = _climb_thresholds("bike")
        # road must equal run
        self.assertEqual(road["min_distance_m"], run["min_distance_m"])
        self.assertEqual(road["min_product"],    run["min_product"])
        # and must be less restrictive than bike
        self.assertLess(road["min_distance_m"], bike["min_distance_m"])
        self.assertLess(road["min_product"],    bike["min_product"])

    def test_road_sport_family_detects_short_climb(self):
        """A 200 m climb passes road thresholds but not bike thresholds."""
        records = []
        for i in range(65):
            records.append({
                "sec": float(i),
                "distance_m": round(i * (200.0 / 60), 2),
                "altitude_m": round(100.0 + i * (20.0 / 60), 2),
                "hr": 150.0,
                "cadence": 75.0,
                "paused": False,
            })
        result_road = analyze_terrain_records(
            records=records,
            pause_filter_mode="heuristic_stationary",
            session_elev_gain_m=20.0,
            sport_family="road",
        )
        result_bike = analyze_terrain_records(
            records=records,
            pause_filter_mode="heuristic_stationary",
            session_elev_gain_m=20.0,
            sport_family="bike",
        )
        self.assertGreater(result_road["terrain_fit_context"]["climb_count"], 0,
                           "road should detect the short climb (same thresholds as run)")
        self.assertEqual(result_bike["terrain_fit_context"]["climb_count"], 0,
                         "bike should filter out the short climb")

    def test_write_terrain_climbs_csv_includes_power_estimated_fields(self):
        from analysis.session_analysis_pipeline import write_terrain_climbs_csv
        rows = [
            {
                "climb_index": 1,
                "start_sec": 0.0,
                "end_sec": 300.0,
                "duration_s": 300.0,
                "distance_km": 1.25,
                "elev_gain_m": 75.0,
                "grade_mean_pct": 6.0,
                "vam_mh": 900.0,
                "hr_mean": 155.0,
                "hr_max": 162.0,
                "cadence_mean": 80.0,
                "power_mean": None,
                "power_max": None,
                "power_estimated_mean": 245.0,
                "power_source": "estimated",
                "hr_available": True,
                "cadence_available": True,
                "power_available": False,
            }
        ]
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "terrain_climbs.csv"
            write_terrain_climbs_csv(path, rows)
            import csv as csv_mod
            with path.open() as f:
                reader = csv_mod.DictReader(f)
                row = next(reader)
            self.assertEqual(row["power_estimated_mean"], "245.0")
            self.assertEqual(row["power_source"], "estimated")

    def test_build_bike_climbs_table_with_estimated_power(self):
        from analysis.session_analysis_pipeline import _build_bike_climbs_table
        rows = [
            {"climb_index": 1, "distance_km": 2.1, "elev_gain_m": 142.0, "duration_s": 480.0,
             "grade_mean_pct": 6.8, "hr_mean": 154.0, "vam_mh": 1065.0, "power_estimated_mean": 218.0},
            {"climb_index": 2, "distance_km": 1.4, "elev_gain_m": 98.0, "duration_s": 310.0,
             "grade_mean_pct": 7.0, "hr_mean": 163.0, "vam_mh": 1138.0, "power_estimated_mean": 241.0},
        ]
        lines = _build_bike_climbs_table(rows, 68.0)
        full = "\n".join(lines)
        self.assertIn("Potencia", lines[0])
        self.assertIn("Km", lines[0])
        self.assertIn("D+", lines[0])
        self.assertIn("~220 W", full)
        self.assertIn("*(est.)*", full)
        self.assertIn("W/kg atleta)", full)
        self.assertEqual(len(lines), 4)  # header + sep + 2 rows

    def test_build_bike_climbs_table_with_measured_power_no_est_label(self):
        from analysis.session_analysis_pipeline import _build_bike_climbs_table
        rows = [
            {"climb_index": 1, "distance_km": 1.5, "elev_gain_m": 90.0, "duration_s": 300.0,
             "grade_mean_pct": 6.0, "hr_mean": 152.0, "vam_mh": 1080.0, "power_mean": 230.0},
            {"climb_index": 2, "distance_km": 1.2, "elev_gain_m": 75.0, "duration_s": 250.0,
             "grade_mean_pct": 6.3, "hr_mean": 158.0, "vam_mh": 1080.0, "power_mean": 245.0},
        ]
        lines = _build_bike_climbs_table(rows, 68.0)
        full = "\n".join(lines)
        self.assertNotIn("est.", full)
        self.assertIn("230", full)

    def test_build_bike_climbs_table_without_power_hides_column(self):
        from analysis.session_analysis_pipeline import _build_bike_climbs_table
        rows = [
            {"climb_index": 1, "distance_km": 1.0, "elev_gain_m": 60.0, "duration_s": 240.0,
             "grade_mean_pct": 6.0, "hr_mean": 150.0, "vam_mh": 900.0},
            {"climb_index": 2, "distance_km": 0.8, "elev_gain_m": 45.0, "duration_s": 180.0,
             "grade_mean_pct": 5.6, "hr_mean": 148.0, "vam_mh": 900.0},
        ]
        lines = _build_bike_climbs_table(rows, 68.0)
        self.assertNotIn("Potencia", lines[0])

    def test_build_bike_climbs_table_single_climb_not_rendered_in_report(self):
        # La tabla solo se renderiza con >= 2 climbs; verificamos que el umbral funciona
        # inspeccionando directamente la función (no el report completo)
        from analysis.session_analysis_pipeline import _build_bike_climbs_table
        rows = [
            {"climb_index": 1, "distance_km": 1.0, "elev_gain_m": 60.0, "duration_s": 240.0,
             "grade_mean_pct": 6.0, "hr_mean": 150.0, "vam_mh": 900.0, "power_estimated_mean": 200.0},
        ]
        lines = _build_bike_climbs_table(rows, 68.0)
        self.assertEqual(len(lines), 3)  # header + sep + 1 fila — la función siempre genera; el umbral está en quien la llama

    def test_summarize_climb_rows_computes_zones_when_vt1_vt2_provided(self):
        from analysis.fit_terrain_utils import _summarize_climb_rows
        rows = []
        distance = 0.0
        altitude = 100.0
        for sec in range(0, 300):
            distance += 4.0
            altitude += 0.24
            hr = 140.0 if sec < 100 else (158.0 if sec < 200 else 172.0)
            rows.append({"sec": float(sec), "distance_m": round(distance, 1),
                         "altitude_smooth_m": round(altitude, 2), "hr": hr})
        result = _summarize_climb_rows(1, rows, vt1=152.0, vt2=166.0)
        self.assertIsNotNone(result["z1_pct"])
        self.assertIsNotNone(result["z2_pct"])
        self.assertIsNotNone(result["z3_pct"])
        total = result["z1_pct"] + result["z2_pct"] + result["z3_pct"]
        self.assertAlmostEqual(total, 100.0, delta=0.5)
        self.assertGreater(result["z1_pct"], 0)
        self.assertGreater(result["z2_pct"], 0)
        self.assertGreater(result["z3_pct"], 0)

    def test_summarize_climb_rows_no_zones_without_thresholds(self):
        from analysis.fit_terrain_utils import _summarize_climb_rows
        rows = [
            {"sec": 0.0, "distance_m": 0.0, "altitude_smooth_m": 100.0, "hr": 155.0},
            {"sec": 60.0, "distance_m": 240.0, "altitude_smooth_m": 115.0, "hr": 160.0},
        ]
        result = _summarize_climb_rows(1, rows)
        self.assertIsNone(result["z1_pct"])
        self.assertIsNone(result["z2_pct"])
        self.assertIsNone(result["z3_pct"])

    def test_group_terrain_climbs_merges_short_gaps_for_trail(self):
        climbs = [
            {"climb_index": 1, "start_sec": 10.0, "end_sec": 110.0, "duration_s": 100.0, "distance_km": 0.30,
             "elev_gain_m": 18.0, "grade_mean_pct": 6.0, "vam_mh": 648.0, "hr_mean": 138.0, "hr_max": 145.0,
             "cadence_mean": 80.0, "power_mean": 210.0, "power_max": 225.0, "power_source": "measured",
             "z1_pct": 100.0, "z2_pct": 0.0, "z3_pct": 0.0},
            {"climb_index": 2, "start_sec": 160.0, "end_sec": 260.0, "duration_s": 100.0, "distance_km": 0.34,
             "elev_gain_m": 22.0, "grade_mean_pct": 6.5, "vam_mh": 792.0, "hr_mean": 142.0, "hr_max": 148.0,
             "cadence_mean": 79.0, "power_mean": 220.0, "power_max": 235.0, "power_source": "measured",
             "z1_pct": 60.0, "z2_pct": 40.0, "z3_pct": 0.0},
            {"climb_index": 3, "start_sec": 420.0, "end_sec": 520.0, "duration_s": 100.0, "distance_km": 0.28,
             "elev_gain_m": 20.0, "grade_mean_pct": 7.1, "vam_mh": 720.0, "hr_mean": 145.0, "hr_max": 150.0,
             "cadence_mean": 78.0, "power_mean": 225.0, "power_max": 238.0, "power_source": "measured",
             "z1_pct": 20.0, "z2_pct": 80.0, "z3_pct": 0.0},
        ]

        groups = group_terrain_climbs(climbs, sport_family="trail")
        self.assertEqual(len(groups), 2)
        self.assertEqual(groups[0]["climb_count"], 2)
        self.assertEqual(groups[0]["member_climb_indices"], [1, 2])
        self.assertEqual(groups[1]["climb_count"], 1)

    def test_analyze_terrain_records_propagates_zones(self):
        records = self._make_climb_records(n_seconds=300, speed_mps=4.0, grade_pct=6.0)
        for r in records:
            r["hr"] = 165.0
        result = analyze_terrain_records(
            records=records,
            pause_filter_mode="heuristic_stationary",
            session_elev_gain_m=300.0,
            vt1=152.0,
            vt2=166.0,
        )
        climbs = result["terrain_climbs"]
        self.assertTrue(all(c.get("z1_pct") is not None for c in climbs))

    def test_terrain_climb_summary_sentence_mentions_macro_groups(self):
        from analysis.session_analysis_pipeline import _terrain_climb_summary_sentence

        session_row = {"z1_pct": "70.8"}
        terrain_fit_context = {
            "climb_count": 13,
            "climb_group_count": 6,
            "climb_hr_mean": 144.8,
        }

        sentence = _terrain_climb_summary_sentence(session_row, terrain_fit_context)
        self.assertIsNotNone(sentence)
        self.assertIn("bloques macro", sentence)
        self.assertIn("climbs finos", sentence)
        self.assertIn("13", sentence)

    def test_build_bike_climbs_table_shows_zone_columns_when_available(self):
        from analysis.session_analysis_pipeline import _build_bike_climbs_table
        rows = [
            {"climb_index": 1, "distance_km": 2.1, "elev_gain_m": 142.0, "duration_s": 480.0,
             "grade_mean_pct": 6.8, "hr_mean": 154.0, "vam_mh": 1065.0,
             "z1_pct": 30.0, "z2_pct": 45.0, "z3_pct": 25.0},
            {"climb_index": 2, "distance_km": 1.4, "elev_gain_m": 98.0, "duration_s": 310.0,
             "grade_mean_pct": 7.0, "hr_mean": 163.0, "vam_mh": 1138.0,
             "z1_pct": 10.0, "z2_pct": 35.0, "z3_pct": 55.0},
        ]
        lines = _build_bike_climbs_table(rows, 68.0)
        header = lines[0]
        self.assertIn("Z1", header)
        self.assertIn("Z2", header)
        self.assertIn("Z3", header)
        full = "\n".join(lines)
        self.assertIn("55%", full)
        self.assertIn("30%", full)

    def test_write_terrain_climbs_csv_includes_zone_columns(self):
        from analysis.session_analysis_pipeline import write_terrain_climbs_csv
        rows = [{
            "climb_index": 1, "start_sec": 0.0, "end_sec": 300.0, "duration_s": 300.0,
            "distance_km": 1.25, "elev_gain_m": 75.0, "grade_mean_pct": 6.0, "vam_mh": 900.0,
            "hr_mean": 158.0, "hr_max": 168.0, "cadence_mean": 80.0,
            "power_mean": None, "power_max": None, "power_estimated_mean": 245.0,
            "power_source": "estimated", "z1_pct": 20.0, "z2_pct": 45.0, "z3_pct": 35.0,
            "hr_available": True, "cadence_available": True, "power_available": False,
        }]
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "terrain_climbs.csv"
            write_terrain_climbs_csv(path, rows)
            import csv as csv_mod
            with path.open() as f:
                row = next(csv_mod.DictReader(f))
            self.assertEqual(row["z1_pct"], "20.0")
            self.assertEqual(row["z3_pct"], "35.0")

    def test_compute_matched_climbs_context_requires_vam_ratio(self):
        from analysis.fit_terrain_utils import compute_matched_climbs_context

        terrain_climbs = [
            {
                "grade_mean_pct": 5.8,
                "start_sec": 10.0,
                "end_sec": 40.0,
                "hr_available": True,
                "hr_mean": 150.0,
                "vam_mh": None,
                "power_mean": 220.0,
            },
            {
                "grade_mean_pct": 5.9,
                "start_sec": 60.0,
                "end_sec": 90.0,
                "hr_available": True,
                "hr_mean": 151.0,
                "vam_mh": None,
                "power_mean": 222.0,
            },
        ]

        result = compute_matched_climbs_context(terrain_climbs, sport_family="road")
        self.assertTrue(result["applicable"])
        self.assertEqual(result["efficiency_pattern"], "mixed_signal")
        self.assertEqual(result["interpretation_confidence"], "low")
        self.assertIsNone(result["aggregate"]["vam_ratio"])

    def test_compute_matched_climbs_context_weights_larger_bins_more_heavily(self):
        from analysis.fit_terrain_utils import compute_matched_climbs_context

        terrain_climbs = [
            {
                "grade_mean_pct": 5.5,
                "start_sec": 10.0,
                "end_sec": 40.0,
                "hr_available": True,
                "hr_mean": 150.0,
                "vam_mh": 100.0,
                "power_mean": 220.0,
            },
            {
                "grade_mean_pct": 5.6,
                "start_sec": 60.0,
                "end_sec": 90.0,
                "hr_available": True,
                "hr_mean": 150.0,
                "vam_mh": 100.0,
                "power_mean": 220.0,
            },
            {
                "grade_mean_pct": 8.5,
                "start_sec": 12.0,
                "end_sec": 42.0,
                "hr_available": True,
                "hr_mean": 150.0,
                "vam_mh": 100.0,
                "power_mean": 220.0,
            },
            {
                "grade_mean_pct": 8.6,
                "start_sec": 18.0,
                "end_sec": 48.0,
                "hr_available": True,
                "hr_mean": 150.0,
                "vam_mh": 100.0,
                "power_mean": 220.0,
            },
            {
                "grade_mean_pct": 8.7,
                "start_sec": 62.0,
                "end_sec": 92.0,
                "hr_available": True,
                "hr_mean": 150.0,
                "vam_mh": 50.0,
                "power_mean": 220.0,
            },
            {
                "grade_mean_pct": 8.8,
                "start_sec": 70.0,
                "end_sec": 100.0,
                "hr_available": True,
                "hr_mean": 150.0,
                "vam_mh": 50.0,
                "power_mean": 220.0,
            },
        ]

        result = compute_matched_climbs_context(terrain_climbs, sport_family="road")
        self.assertTrue(result["applicable"])
        self.assertEqual(result["matched_groups_count"], 2)
        self.assertAlmostEqual(result["aggregate"]["vam_ratio"], 0.667, places=3)
        self.assertEqual(result["efficiency_pattern"], "mixed_signal")

    def test_bike_climb_dilation_sentence_includes_estimated_power(self):
        from analysis.session_analysis_pipeline import _bike_climb_dilation_sentence, _terrain_climb_dilation_sentence
        session_row = {"z1_pct": "72.0", "vt1_used": "148", "sport": "bike"}
        terrain_fit_context = {
            "climb_count": 6,
            "climb_hr_mean": 160.0,
            "climb_time_min": 37.4,
            "climb_gain_m": 472.6,
            "climb_power_estimated_mean": 215.0,
            "climb_power_source": "estimated",
        }
        sentence = _bike_climb_dilation_sentence(session_row, terrain_fit_context)
        terrain_sentence = _terrain_climb_dilation_sentence(session_row, terrain_fit_context)
        self.assertIsNotNone(sentence)
        self.assertEqual(sentence, terrain_sentence)
        self.assertIn("~215 W", sentence)
        self.assertIn("W/kg atleta", sentence)
        self.assertIn("estimada", sentence)
        self.assertIn("potencia estimada", sentence)

    def test_bike_climb_dilation_sentence_includes_measured_power_and_z3_dilution(self):
        from analysis.session_analysis_pipeline import _bike_climb_dilation_sentence

        session_row = {"z1_pct": "72.0", "z3_pct": "11.5", "vt1_used": "148", "sport": "trail_run"}
        terrain_fit_context = {
            "climb_count": 6,
            "climb_hr_mean": 160.0,
            "climb_time_min": 37.4,
            "climb_gain_m": 472.6,
            "climb_power_mean": 266.0,
            "climb_power_source": "measured",
            "climb_z3_pct_mean": 34.2,
        }
        sentence = _bike_climb_dilation_sentence(session_row, terrain_fit_context)
        self.assertIsNotNone(sentence)
        self.assertIn("potencia medida", sentence)
        self.assertIn("W/kg atleta", sentence)
        self.assertIn("subidas concentraron", sentence)
        self.assertIn("34.2%", sentence)

    def test_build_sport_climbs_table_bike_with_power(self):
        """Test that bike table shows power column and no ritmo."""
        from analysis.session_analysis_pipeline import _build_sport_climbs_table
        rows = [
            {"climb_index": 1, "distance_km": 2.1, "elev_gain_m": 142.0, "duration_s": 480.0,
             "grade_mean_pct": 6.8, "hr_mean": 154.0, "vam_mh": 1065.0, "power_mean": 230.0},
            {"climb_index": 2, "distance_km": 1.4, "elev_gain_m": 98.0, "duration_s": 310.0,
             "grade_mean_pct": 7.0, "hr_mean": 163.0, "vam_mh": 1138.0, "power_mean": 245.0},
        ]
        lines = _build_sport_climbs_table(rows, 68.0, sport_family="bike")
        header = lines[0]
        full = "\n".join(lines)
        self.assertIn("Potencia", header)
        self.assertNotIn("Ritmo", header)
        self.assertIn("230", full)
        self.assertIn("W/kg atleta", full)

    def test_build_sport_climbs_table_trail_with_measured_power(self):
        """Test that trail table shows ritmo column and power when available."""
        from analysis.session_analysis_pipeline import _build_sport_climbs_table
        rows = [
            {"climb_index": 1, "distance_km": 0.6, "elev_gain_m": 120.0, "duration_s": 300.0,
             "grade_mean_pct": 20.0, "hr_mean": 168.0, "vam_mh": 1440.0, "power_mean": 265.0},
            {"climb_index": 2, "distance_km": 0.5, "elev_gain_m": 95.0, "duration_s": 250.0,
             "grade_mean_pct": 19.0, "hr_mean": 165.0, "vam_mh": 1368.0, "power_mean": 254.0},
        ]
        lines = _build_sport_climbs_table(rows, 68.0, sport_family="trail")
        header = lines[0]
        full = "\n".join(lines)
        self.assertIn("Ritmo", header)
        # For trail with measured power, power column is still shown (bike-only gate removed)
        # but NOT as primary; ritmo is the running-specific metric
        self.assertIn("8:20", full)  # Pace: 300s / 0.6km = 500s/km = 8:20
        self.assertIn("8:20", full)  # Pace: 250s / 0.5km = 500s/km = 8:20

    def test_build_sport_climbs_table_road_without_power(self):
        """Test that road table shows ritmo and omits power column when absent."""
        from analysis.session_analysis_pipeline import _build_sport_climbs_table
        rows = [
            {"climb_index": 1, "distance_km": 1.2, "elev_gain_m": 75.0, "duration_s": 360.0,
             "grade_mean_pct": 6.3, "hr_mean": 152.0, "vam_mh": 750.0},
            {"climb_index": 2, "distance_km": 0.9, "elev_gain_m": 55.0, "duration_s": 270.0,
             "grade_mean_pct": 6.1, "hr_mean": 150.0, "vam_mh": 733.0},
        ]
        lines = _build_sport_climbs_table(rows, 68.0, sport_family="road")
        header = lines[0]
        full = "\n".join(lines)
        self.assertIn("Ritmo", header)
        self.assertNotIn("Potencia", header)
        self.assertIn("5:00", full)  # pace: 360s / 1.2km

    def test_build_sport_climbs_table_zones_works_for_all_sports(self):
        """Test that zone columns are shown for all sports when data available."""
        from analysis.session_analysis_pipeline import _build_sport_climbs_table
        rows = [
            {"climb_index": 1, "distance_km": 1.0, "elev_gain_m": 60.0, "duration_s": 300.0,
             "grade_mean_pct": 6.0, "hr_mean": 155.0, "vam_mh": 720.0,
             "z1_pct": 30.0, "z2_pct": 40.0, "z3_pct": 30.0},
            {"climb_index": 2, "distance_km": 0.8, "elev_gain_m": 50.0, "duration_s": 240.0,
             "grade_mean_pct": 6.3, "hr_mean": 158.0, "vam_mh": 750.0,
             "z1_pct": 25.0, "z2_pct": 45.0, "z3_pct": 30.0},
        ]
        lines = _build_sport_climbs_table(rows, 68.0, sport_family="trail")
        header = lines[0]
        full = "\n".join(lines)
        self.assertIn("Z1", header)
        self.assertIn("Z2", header)
        self.assertIn("Z3", header)
        self.assertIn("30%", full)
        self.assertIn("40%", full)

    def test_build_sport_climbs_table_hike_with_pace(self):
        """Test that hike sport gets pace column like other running-style sessions."""
        from analysis.session_analysis_pipeline import _build_sport_climbs_table
        rows = [
            {"climb_index": 1, "distance_km": 1.5, "elev_gain_m": 150.0, "duration_s": 600.0,
             "grade_mean_pct": 10.0, "hr_mean": 130.0, "vam_mh": 900.0},
        ]
        lines = _build_sport_climbs_table(rows, 68.0, sport_family="hike")
        header = lines[0]
        full = "\n".join(lines)
        self.assertIn("Ritmo", header)
        self.assertIn("VAM", header)
        self.assertIn("6:40", full)  # pace: 600s / 1.5km = 400s/km = 6:40


if __name__ == "__main__":
    unittest.main()
