import unittest
from unittest.mock import patch

from analysis.fit_terrain_utils import (
    _build_validation_vs_v2,
    _select_altitude_value,
    analyze_terrain_records,
)
from analysis.session_analysis_pipeline import (
    _build_no_rr_summary,
    _normalize_terrain_interval_rows,
    _supports_terrain_context,
    _summarize_terrain_context_from_intervals,
    enrich_summary_with_manifest_context,
    enrich_summary_with_sessions_metadata,
    infer_sport_family,
    render_report_markdown,
    rr_sections_visible,
)
from analysis.session_cost_model import normalize_sport


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
            "session_row": {"sport": "trail_run"},
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
