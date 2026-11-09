import json
import unittest
from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory

import pandas as pd

from analysis import run_weekly_analysis_prep
from analysis import swim_context as swim
from analysis import swim_weekly
from analysis import sya15_continuity


def sessions_frame(rows):
    return pd.DataFrame(rows, columns=["session_id", "Fecha", "sport", "duration_min"])


def ctx(session_id, day, *, styles, pool=25.0, source="polar_v4", validation="passed", srpe=None):
    total = sum(s[1] for s in styles)
    return {
        "session_id": session_id,
        "session_date": day,
        "swim_source": source,
        "length_validation_status": validation,
        "pool_length_m": pool,
        "distance_m": total,
        "primary_stroke": max(styles, key=lambda s: s[1])[0],
        "breaststroke_pct": None,
        "srpe_load": srpe,
        "status": "available",
        "swolf_by_stroke": {s[0]: s[2] for s in styles},
        "stroke_distribution": {s[0]: {"distance_m": s[1], "pct": round(100 * s[1] / total, 1)} for s in styles},
        "styles": [
            {
                "style": name,
                "distance_m": dist,
                "swolf_polar": swolf,
                "pace_s_per_100m": 180.0,
                "n_lengths_validated": int(dist / pool),
                "too_few_lengths": False,
                "swolf_validation_status": "validated_against_phases",
            }
            for name, dist, swolf in styles
        ],
    }


class SwimWeeklyContextTest(unittest.TestCase):
    def test_share_uses_duration_min_and_excludes_other_sports(self):
        sessions = sessions_frame([
            ("s1", "2026-11-02", "swim", 60),
            ("s2", "2026-11-03", "trail_run", 90),
            ("s3", "2026-11-04", "road_run", 30),
            ("s4", "2026-11-05", "bike", 120),
            ("s5", "2026-10-27", "swim", 45),
        ])
        payload = swim_weekly.build_swim_weekly_context(sessions, [], date(2026, 11, 6))
        week = payload["current_week"]
        self.assertEqual(payload["week_start"], "2026-11-02")
        self.assertEqual(payload["week_end"], "2026-11-08")
        self.assertEqual(week["swim_min"], 60.0)
        self.assertEqual(week["run_trail_min"], 120.0)
        self.assertAlmostEqual(week["swim_share_of_swim_run"], 0.333, places=3)
        self.assertEqual(len(payload["previous_weeks"]), swim_weekly.HISTORY_WEEKS)
        self.assertEqual(payload["previous_weeks"][-1]["swim_min"], 45.0)
        self.assertIn("swim_context_incomplete", payload["quality_reasons"])

    def test_zero_denominator_is_null(self):
        sessions = sessions_frame([("s1", "2026-11-03", "bike", 60)])
        payload = swim_weekly.build_swim_weekly_context(sessions, [], date(2026, 11, 3))
        self.assertIsNone(payload["current_week"]["swim_share_of_swim_run"])
        self.assertIn("no_swim_or_run_minutes", payload["quality_reasons"])

    def test_technique_aggregates_polar_distance_by_style(self):
        sessions = sessions_frame([
            ("s1", "2026-11-02", "swim", 60),
            ("s2", "2026-11-04", "swim", 60),
        ])
        contexts = [
            ctx("s1", "2026-11-02", styles=[("BREASTSTROKE", 500.0, 57.0), ("BACKSTROKE", 500.0, 88.0)], srpe=240),
            ctx("s2", "2026-11-04", styles=[("FREESTYLE", 1000.0, 72.0)]),
            ctx("s9", "2026-10-20", styles=[("BREASTSTROKE", 800.0, 57.0)]),
        ]
        payload = swim_weekly.build_swim_weekly_context(sessions, contexts, date(2026, 11, 5))
        tech = payload["technique"]
        self.assertEqual(tech["sessions_with_polar"], 2)
        self.assertEqual(tech["stroke_distribution"]["BREASTSTROKE"]["distance_m"], 500.0)
        self.assertEqual(tech["breaststroke_pct"], 25.0)
        self.assertEqual(tech["srpe_load_total"], 240.0)
        self.assertEqual(tech["srpe_sessions"], 1)
        self.assertNotIn("swim_context_incomplete", payload["quality_reasons"])

    def test_orphan_contexts_do_not_count(self):
        sessions = sessions_frame([
            ("x", "2026-11-03", "bike", 60),
            ("s1", "2026-11-04", "swim", 60),
        ])
        contexts = [
            ctx("orphan", "2026-11-03", styles=[("BREASTSTROKE", 500.0, 57.0)]),
            ctx("x", "2026-11-03", styles=[("BREASTSTROKE", 500.0, 57.0)]),
        ]
        payload = swim_weekly.build_swim_weekly_context(sessions, contexts, date(2026, 11, 4))
        self.assertEqual(payload["technique_coverage"], {"swim_sessions": 1, "with_polar_swim_context": 0})
        self.assertIsNone(payload["technique"]["stroke_distribution"])
        empty = swim_weekly.build_swim_weekly_context(sessions_frame([("x", "2026-11-03", "bike", 60)]), contexts, date(2026, 11, 4))
        self.assertEqual(empty["technique_coverage"], {"swim_sessions": 0, "with_polar_swim_context": 0})

    def test_sidecar_files_and_manifest_entry(self):
        with TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            csv_path = tmp_path / "sessions.csv"
            sessions_frame([("s1", "2026-11-02", "swim", 60)]).to_csv(csv_path, index=False)
            entry = swim_weekly.build_swim_weekly_sidecar(
                today="2026-11-06", out_dir=tmp_path / "artifacts", sessions_csv=csv_path, reports_root=tmp_path / "none"
            )
            self.assertEqual(entry["sidecar"], swim_weekly.SIDECAR_NAME)
            payload = json.loads(Path(entry["report_json"]).read_text(encoding="utf-8"))
            self.assertEqual(payload["schema_version"], swim_weekly.SCHEMA_VERSION)
            markdown = Path(entry["report_md"]).read_text(encoding="utf-8")
            self.assertIn("no equivalencia de carga", markdown)

    def test_weekly_prep_declares_swim_sidecar_when_sessions_given(self):
        with TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            weekly_csv = tmp_path / "weekly.csv"
            pd.DataFrame([{
                "window_start": "2026-10-26", "sport": "trail_run", "distribution_confidence": "high",
                "n_sessions_usable": 2, "total_duration_min": 120, "z1_pct_weighted": 80,
                "distribution_pattern": "pyramidal",
            }]).to_csv(weekly_csv, index=False)
            sessions_csv = tmp_path / "sessions.csv"
            sessions_frame([("s1", "2026-11-02", "swim", 60)]).to_csv(sessions_csv, index=False)
            manifest = run_weekly_analysis_prep.build_weekly_prep(
                today=sya15_continuity.resolve_today("2026-11-06"),
                weekly_dir=tmp_path / "weekly",
                input_path=weekly_csv,
                focus_sport=None,
                window_size=4,
                min_positive=None,
                sessions_csv=sessions_csv,
                session_reports_dir=tmp_path / "reports",
            )
            sidecar = run_weekly_analysis_prep.get_sidecar(manifest, swim_weekly.SIDECAR_NAME)
            self.assertTrue(Path(sidecar["report_json"]).exists())
            self.assertFalse((tmp_path / "weekly" / "artifacts" / "ENDURANCE_HRV_weekly_coach.json").exists())


class SwimStyleHistoryTest(unittest.TestCase):
    def current(self):
        return ctx("now", "2026-11-06", styles=[("BREASTSTROKE", 500.0, 58.0), ("BACKSTROKE", 500.0, 88.0)])

    def test_too_few_sessions_has_no_summary(self):
        priors = [ctx("p1", "2026-11-01", styles=[("BREASTSTROKE", 500.0, 57.0)])]
        history = swim.build_style_history(self.current(), priors)
        entry = history["by_stroke"]["BREASTSTROKE"]
        self.assertTrue(entry["too_few_sessions"])
        self.assertIsNone(entry["prior_swolf_median"])
        self.assertEqual(history["by_stroke"]["BACKSTROKE"]["n_prior_eligible"], 0)

    def test_filters_and_limits_eligible_priors(self):
        priors = [
            ctx(f"p{i}", f"2026-10-{10 + i:02d}", styles=[("BREASTSTROKE", 500.0, 50.0 + i)])
            for i in range(7)
        ]
        priors += [
            ctx("pool50", "2026-10-30", styles=[("BREASTSTROKE", 500.0, 40.0)], pool=50.0),
            ctx("fit", "2026-10-31", styles=[("BREASTSTROKE", 500.0, 40.0)], source="intervals_fit_laps"),
            ctx("failed", "2026-11-01", styles=[("BREASTSTROKE", 500.0, 40.0)], validation="failed"),
            ctx("future", "2026-11-07", styles=[("BREASTSTROKE", 500.0, 40.0)]),
        ]
        few = ctx("few", "2026-11-02", styles=[("BREASTSTROKE", 50.0, 40.0)])
        few["styles"][0]["too_few_lengths"] = True
        priors.append(few)
        entry = swim.build_style_history(self.current(), priors)["by_stroke"]["BREASTSTROKE"]
        self.assertEqual(entry["n_prior_eligible"], 5)
        self.assertEqual([r["session_id"] for r in entry["prior_sessions"]], ["p6", "p5", "p4", "p3", "p2"])
        self.assertFalse(entry["too_few_sessions"])
        self.assertEqual(entry["prior_swolf_median"], 54.0)
        self.assertEqual(entry["pool_length_m"], 25.0)

    def test_no_history_without_validated_polar_lengths(self):
        current = self.current()
        current["length_validation_status"] = "failed"
        self.assertIsNone(swim.build_style_history(current, []))

    def test_load_prior_contexts_excludes_current_session(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            for sid in ("a", "b"):
                path = root / "2026" / "11" / f"x_{sid}" / "artifacts"
                path.mkdir(parents=True)
                (path / "summary.json").write_text(
                    json.dumps({"swim_context": {"session_id": sid, "session_date": "2026-11-01"}}), encoding="utf-8"
                )
            loaded = swim.load_prior_swim_contexts(root, exclude_session_id="a")
            self.assertEqual([c["session_id"] for c in loaded], ["b"])


if __name__ == "__main__":
    unittest.main()
