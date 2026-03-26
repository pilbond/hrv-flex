import unittest

from analysis.session_analysis_pipeline import (
    _build_no_rr_summary,
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


if __name__ == "__main__":
    unittest.main()
