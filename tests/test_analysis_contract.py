import unittest
from unittest.mock import patch

from analysis.session_analysis_pipeline import (
    _build_no_rr_summary,
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


if __name__ == "__main__":
    unittest.main()
