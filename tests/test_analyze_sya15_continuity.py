import json
import importlib.util
import sys
import unittest
from unittest import mock
from pathlib import Path
from tempfile import TemporaryDirectory

import pandas as pd


MODULE_PATH = Path(__file__).resolve().parents[1] / "analysis" / "sya15_continuity.py"
SPEC = importlib.util.spec_from_file_location("analyze_sya15_continuity", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)

# Algunos tests consumen los CSV personales reales de data/ (no versionados);
# en CI no existen y se omiten con razón explícita.
_REAL_DATA_AVAILABLE = Path("data/ENDURANCE_HRV_intensity_distribution_weekly.csv").exists()
requires_real_data = unittest.skipUnless(
    _REAL_DATA_AVAILABLE, "requiere los CSV personales de data/ (no disponibles en CI)"
)


class AnalyzeSya15ContinuityTests(unittest.TestCase):
    def _write_weekly_csv(self, rows):
        tmpdir = TemporaryDirectory()
        self.addCleanup(tmpdir.cleanup)
        path = Path(tmpdir.name) / "weekly.csv"
        pd.DataFrame(rows).to_csv(path, index=False)
        return path

    def test_load_weekly_rejects_non_monday_window_start(self):
        path = self._write_weekly_csv(
            [
                {
                    "window_start": "2026-05-05",
                    "sport": "bike",
                    "distribution_confidence": "high",
                    "n_sessions_usable": 2,
                    "total_duration_min": 120,
                    "z1_pct_weighted": 80,
                    "distribution_pattern": "pyramidal",
                }
            ]
        )
        with self.assertRaisesRegex(ValueError, "Monday-aligned ISO weeks"):
            MODULE.load_weekly(path)

    def test_load_weekly_rejects_duplicate_sport_window_start_rows(self):
        path = self._write_weekly_csv(
            [
                {
                    "window_start": "2026-04-06",
                    "sport": "bike",
                    "distribution_confidence": "high",
                    "n_sessions_usable": 2,
                    "total_duration_min": 120,
                    "z1_pct_weighted": 80,
                    "distribution_pattern": "pyramidal",
                },
                {
                    "window_start": "2026-04-06",
                    "sport": "bike",
                    "distribution_confidence": "high",
                    "n_sessions_usable": 2,
                    "total_duration_min": 120,
                    "z1_pct_weighted": 80,
                    "distribution_pattern": "pyramidal",
                },
            ]
        )

        with self.assertRaisesRegex(
            ValueError,
            "Duplicate sport/window_start rows are not supported; sample duplicates:",
        ):
            MODULE.load_weekly(path)

    def test_expand_calendar_marks_missing_weeks_as_not_observed(self):
        path = self._write_weekly_csv(
            [
                {
                    "window_start": "2026-04-20",
                    "sport": "bike",
                    "distribution_confidence": "high",
                    "n_sessions_usable": 2,
                    "total_duration_min": 120,
                    "z1_pct_weighted": 80,
                    "distribution_pattern": "pyramidal",
                },
                {
                    "window_start": "2026-05-04",
                    "sport": "bike",
                    "distribution_confidence": "high",
                    "n_sessions_usable": 2,
                    "total_duration_min": 130,
                    "z1_pct_weighted": 82,
                    "distribution_pattern": "pyramidal",
                },
            ]
        )
        weekly = MODULE.load_weekly(path)
        bike = weekly[weekly["sport"] == "bike"].copy()
        calendar = MODULE.expand_calendar(bike, MODULE.resolve_today("2026-05-07"))

        gap_row = calendar.loc[calendar["window_start"] == pd.Timestamp("2026-04-27")].iloc[0]
        self.assertFalse(bool(gap_row["row_observed"]))
        self.assertFalse(bool(gap_row["usable_week"]))
        self.assertFalse(bool(gap_row["z1_dominant"]))

    def test_current_week_is_forced_to_not_z1_dominant_even_if_partial_row_exists(self):
        path = self._write_weekly_csv(
            [
                {
                    "window_start": "2026-04-13",
                    "sport": "bike",
                    "distribution_confidence": "high",
                    "n_sessions_usable": 2,
                    "total_duration_min": 120,
                    "z1_pct_weighted": 80,
                    "distribution_pattern": "pyramidal",
                },
                {
                    "window_start": "2026-04-20",
                    "sport": "bike",
                    "distribution_confidence": "high",
                    "n_sessions_usable": 2,
                    "total_duration_min": 120,
                    "z1_pct_weighted": 80,
                    "distribution_pattern": "pyramidal",
                },
                {
                    "window_start": "2026-04-27",
                    "sport": "bike",
                    "distribution_confidence": "high",
                    "n_sessions_usable": 2,
                    "total_duration_min": 120,
                    "z1_pct_weighted": 80,
                    "distribution_pattern": "pyramidal",
                },
                {
                    "window_start": "2026-05-04",
                    "sport": "bike",
                    "distribution_confidence": "high",
                    "n_sessions_usable": 2,
                    "total_duration_min": 120,
                    "z1_pct_weighted": 80,
                    "distribution_pattern": "pyramidal",
                },
            ]
        )
        weekly = MODULE.load_weekly(path)
        bike = weekly[weekly["sport"] == "bike"].copy()
        calendar = MODULE.expand_calendar(bike, MODULE.resolve_today("2026-05-07"))

        current_row = calendar.loc[calendar["window_start"] == pd.Timestamp("2026-05-04")].iloc[0]
        self.assertTrue(bool(current_row["row_observed"]))
        self.assertFalse(bool(current_row["z1_dominant"]))

    def test_summary_reports_positive_rate_and_evaluable_windows(self):
        path = self._write_weekly_csv(
            [
                {
                    "window_start": "2026-04-06",
                    "sport": "bike",
                    "distribution_confidence": "high",
                    "n_sessions_usable": 2,
                    "total_duration_min": 120,
                    "z1_pct_weighted": 80,
                    "distribution_pattern": "pyramidal",
                },
                {
                    "window_start": "2026-04-13",
                    "sport": "bike",
                    "distribution_confidence": "high",
                    "n_sessions_usable": 2,
                    "total_duration_min": 120,
                    "z1_pct_weighted": 80,
                    "distribution_pattern": "pyramidal",
                },
                {
                    "window_start": "2026-04-20",
                    "sport": "bike",
                    "distribution_confidence": "high",
                    "n_sessions_usable": 2,
                    "total_duration_min": 120,
                    "z1_pct_weighted": 80,
                    "distribution_pattern": "pyramidal",
                },
                {
                    "window_start": "2026-04-27",
                    "sport": "bike",
                    "distribution_confidence": "low",
                    "n_sessions_usable": 1,
                    "total_duration_min": 40,
                    "z1_pct_weighted": 80,
                    "distribution_pattern": "pyramidal",
                },
            ]
        )
        weekly = MODULE.load_weekly(path)
        summary, _details = MODULE.summarize_by_sport(weekly, MODULE.resolve_today("2026-04-30"))
        bike = summary.loc[summary["sport"] == "bike"].iloc[0]
        evaluable_col = f"{MODULE.CONTINUITY_PREFIX}_evaluable_weeks"
        positive_col = f"{MODULE.CONTINUITY_PREFIX}_positive_weeks"
        rate_col = f"{MODULE.CONTINUITY_PREFIX}_positive_rate"

        self.assertEqual(int(bike[evaluable_col]), 1)
        self.assertEqual(int(bike[positive_col]), 1)
        self.assertAlmostEqual(float(bike[rate_col]), 1.0, places=6)

    def test_continuity_depends_on_min_positive_threshold(self):
        def make_calendar(z1_dominant):
            return pd.DataFrame(
                {
                    "window_start": pd.to_datetime(
                        [
                            "2026-04-06",
                            "2026-04-13",
                            "2026-04-20",
                            "2026-04-27",
                        ]
                    ),
                    "sport": ["bike"] * 4,
                    "row_observed": [True] * 4,
                    "usable_week": [True] * 4,
                    "z1_dominant": z1_dominant,
                }
            )
        positive_col = f"{MODULE.CONTINUITY_PREFIX}_positive"

        positive_patterns = [
            [True, True, True, True],
            [False, True, True, True],
            [True, False, True, True],
            [True, True, False, True],
            [True, True, True, False],
        ]
        for seq in positive_patterns:
            out = MODULE.compute_continuity(make_calendar(seq), min_positive=3)
            self.assertTrue(bool(out.iloc[-1][positive_col]), msg=str(seq))

        for seq in ([False, False, True, True], [True, False, True, False], [False, True, False, True]):
            out = MODULE.compute_continuity(make_calendar(seq), min_positive=3)
            self.assertFalse(bool(out.iloc[-1][positive_col]), msg=str(seq))

        out = MODULE.compute_continuity(make_calendar([True, True, False, False]), min_positive=2)
        self.assertTrue(bool(out.iloc[-1][positive_col]))
        out = MODULE.compute_continuity(make_calendar([True, False, True, False]), min_positive=2)
        self.assertTrue(bool(out.iloc[-1][positive_col]))
        out = MODULE.compute_continuity(make_calendar([False, True, False, True]), min_positive=2)
        self.assertTrue(bool(out.iloc[-1][positive_col]))
        out = MODULE.compute_continuity(make_calendar([False, True, False, True]), min_positive=3)
        self.assertFalse(bool(out.iloc[-1][positive_col]))
        out = MODULE.compute_continuity(make_calendar([False, True, False, True]), min_positive=4)
        self.assertFalse(bool(out.iloc[-1][positive_col]))

    def test_compute_continuity_rejects_out_of_range_min_positive(self):
        calendar = pd.DataFrame(
            {
                "window_start": pd.to_datetime(
                    [
                        "2026-04-06",
                        "2026-04-13",
                        "2026-04-20",
                        "2026-04-27",
                    ]
                ),
                "sport": ["bike"] * 4,
                "row_observed": [True] * 4,
                "usable_week": [True] * 4,
                "z1_dominant": [True] * 4,
            }
        )
        with self.assertRaisesRegex(
            ValueError, rf"between 1 and {MODULE.WINDOW_SIZE}"
        ):
            MODULE.compute_continuity(calendar, min_positive=0)
        with self.assertRaisesRegex(
            ValueError, rf"between 1 and {MODULE.WINDOW_SIZE}"
        ):
            MODULE.compute_continuity(calendar, min_positive=5)

    def test_summarize_by_sport_keeps_sports_isolated(self):
        path = self._write_weekly_csv(
            [
                {
                    "window_start": "2026-04-06",
                    "sport": "bike",
                    "distribution_confidence": "high",
                    "n_sessions_usable": 2,
                    "total_duration_min": 120,
                    "z1_pct_weighted": 80,
                    "distribution_pattern": "pyramidal",
                },
                {
                    "window_start": "2026-04-13",
                    "sport": "bike",
                    "distribution_confidence": "high",
                    "n_sessions_usable": 2,
                    "total_duration_min": 120,
                    "z1_pct_weighted": 80,
                    "distribution_pattern": "pyramidal",
                },
                {
                    "window_start": "2026-04-20",
                    "sport": "bike",
                    "distribution_confidence": "high",
                    "n_sessions_usable": 2,
                    "total_duration_min": 120,
                    "z1_pct_weighted": 80,
                    "distribution_pattern": "pyramidal",
                },
                {
                    "window_start": "2026-04-27",
                    "sport": "bike",
                    "distribution_confidence": "high",
                    "n_sessions_usable": 2,
                    "total_duration_min": 120,
                    "z1_pct_weighted": 80,
                    "distribution_pattern": "pyramidal",
                },
                {
                    "window_start": "2026-04-06",
                    "sport": "trail_run",
                    "distribution_confidence": "low",
                    "n_sessions_usable": 1,
                    "total_duration_min": 50,
                    "z1_pct_weighted": 90,
                    "distribution_pattern": "pyramidal",
                },
                {
                    "window_start": "2026-04-13",
                    "sport": "trail_run",
                    "distribution_confidence": "low",
                    "n_sessions_usable": 1,
                    "total_duration_min": 50,
                    "z1_pct_weighted": 90,
                    "distribution_pattern": "pyramidal",
                },
                {
                    "window_start": "2026-04-20",
                    "sport": "trail_run",
                    "distribution_confidence": "low",
                    "n_sessions_usable": 1,
                    "total_duration_min": 50,
                    "z1_pct_weighted": 90,
                    "distribution_pattern": "pyramidal",
                },
                {
                    "window_start": "2026-04-27",
                    "sport": "trail_run",
                    "distribution_confidence": "low",
                    "n_sessions_usable": 1,
                    "total_duration_min": 50,
                    "z1_pct_weighted": 90,
                    "distribution_pattern": "pyramidal",
                },
            ]
        )
        weekly = MODULE.load_weekly(path)
        summary, details = MODULE.summarize_by_sport(weekly, MODULE.resolve_today("2026-04-30"))

        bike = summary.loc[summary["sport"] == "bike"].iloc[0]
        trail = summary.loc[summary["sport"] == "trail_run"].iloc[0]
        positive_col = f"{MODULE.CONTINUITY_PREFIX}_positive"
        positive_weeks_col = f"{MODULE.CONTINUITY_PREFIX}_positive_weeks"

        self.assertEqual(int(bike["usable_weeks"]), 4)
        self.assertEqual(int(bike["z1_dominant_weeks"]), 3)
        self.assertEqual(int(trail["usable_weeks"]), 0)
        self.assertEqual(int(trail["z1_dominant_weeks"]), 0)
        self.assertEqual(int(trail[positive_weeks_col]), 0)
        self.assertEqual(int(details["bike"][positive_col].sum()), 1)
        self.assertEqual(int(details["trail_run"][positive_col].sum()), 0)

    def test_detect_positive_episodes_groups_consecutive_positive_windows(self):
        detail = pd.DataFrame(
            {
                "window_start": pd.to_datetime(
                    [
                        "2026-04-06",
                        "2026-04-13",
                        "2026-04-20",
                        "2026-04-27",
                        "2026-05-04",
                        "2026-05-11",
                    ]
                ),
                f"{MODULE.CONTINUITY_PREFIX}_positive": [False, True, True, False, True, True],
            }
        )

        episodes = MODULE.detect_positive_episodes(detail)

        self.assertEqual(len(episodes), 2)
        self.assertEqual(episodes.iloc[0]["episode_start"], pd.Timestamp("2026-04-13"))
        self.assertEqual(episodes.iloc[0]["episode_end"], pd.Timestamp("2026-04-20"))
        self.assertEqual(int(episodes.iloc[0]["positive_weeks"]), 2)
        self.assertEqual(episodes.iloc[1]["episode_start"], pd.Timestamp("2026-05-04"))
        self.assertEqual(episodes.iloc[1]["episode_end"], pd.Timestamp("2026-05-11"))
        self.assertEqual(int(episodes.iloc[1]["positive_weeks"]), 2)

    def test_detect_positive_episodes_requires_window_start(self):
        detail = pd.DataFrame({f"{MODULE.CONTINUITY_PREFIX}_positive": [True, False]})

        with self.assertRaisesRegex(ValueError, "Missing required column: window_start"):
            MODULE.detect_positive_episodes(detail)

    def test_detect_positive_episodes_returns_stable_empty_schema(self):
        detail = pd.DataFrame(
            {
                "window_start": pd.to_datetime(["2026-04-06", "2026-04-13"]),
                f"{MODULE.CONTINUITY_PREFIX}_positive": [False, False],
            }
        )

        episodes = MODULE.detect_positive_episodes(detail)

        self.assertEqual(list(episodes.columns), ["episode_start", "episode_end", "positive_weeks"])
        self.assertTrue(episodes.empty)

    def test_positive_threshold_scales_by_window_size(self):
        self.assertEqual(MODULE.positive_threshold(1), 1)
        self.assertEqual(MODULE.positive_threshold(2), 1)
        self.assertEqual(MODULE.positive_threshold(3), 2)
        self.assertEqual(MODULE.positive_threshold(4), 3)
        self.assertEqual(MODULE.positive_threshold(5), 4)

    def test_build_parser_help_formats_without_argparse_percent_error(self):
        parser = MODULE.build_parser()
        help_text = parser.format_help()
        self.assertIn("75%", help_text)
        self.assertIn("100%", help_text)
        self.assertIn("Must be at least 2", help_text)

    def test_json_safe_value_leaves_non_scalar_values_untouched(self):
        payload = [1, 2, 3]
        self.assertEqual(MODULE._json_safe_value(payload), payload)

    def test_positive_threshold_rejects_non_positive_window_size(self):
        with self.assertRaisesRegex(ValueError, "window_size must be at least 1"):
            MODULE.positive_threshold(0)
        with self.assertRaisesRegex(ValueError, "window_size must be at least 1"):
            MODULE.positive_threshold(-1)

    def test_resolve_min_positive_rejects_out_of_range_value(self):
        with self.assertRaisesRegex(ValueError, "min_positive must be between 1 and 4 for a 4-week window"):
            MODULE.resolve_min_positive(4, 0)
        with self.assertRaisesRegex(ValueError, "min_positive must be between 1 and 4 for a 4-week window"):
            MODULE.resolve_min_positive(4, 5)

    def test_compute_continuity_rejects_window_size_one(self):
        calendar = pd.DataFrame(
            {
                "window_start": pd.to_datetime(["2026-04-06", "2026-04-13"]),
                "z1_dominant": [True, False],
            }
        )

        with self.assertRaisesRegex(ValueError, "window_size must be at least 2"):
            MODULE.compute_continuity(calendar, window_size=1)

    def test_summarize_by_sport_rejects_window_size_one(self):
        path = self._write_weekly_csv(
            [
                {
                    "window_start": "2026-04-06",
                    "sport": "bike",
                    "distribution_confidence": "high",
                    "n_sessions_usable": 2,
                    "total_duration_min": 120,
                    "z1_pct_weighted": 80,
                    "distribution_pattern": "pyramidal",
                }
            ]
        )
        weekly = MODULE.load_weekly(path)

        with self.assertRaisesRegex(ValueError, "window_size must be at least 2"):
            MODULE.summarize_by_sport(weekly, MODULE.resolve_today("2026-05-07"), window_size=1)

    def test_build_sport_report_includes_episodes(self):
        path = self._write_weekly_csv(
            [
                {
                    "window_start": "2026-04-06",
                    "sport": "bike",
                    "distribution_confidence": "high",
                    "n_sessions_usable": 2,
                    "total_duration_min": 120,
                    "z1_pct_weighted": 80,
                    "distribution_pattern": "pyramidal",
                },
                {
                    "window_start": "2026-04-13",
                    "sport": "bike",
                    "distribution_confidence": "high",
                    "n_sessions_usable": 2,
                    "total_duration_min": 120,
                    "z1_pct_weighted": 80,
                    "distribution_pattern": "pyramidal",
                },
                {
                    "window_start": "2026-04-20",
                    "sport": "bike",
                    "distribution_confidence": "high",
                    "n_sessions_usable": 2,
                    "total_duration_min": 120,
                    "z1_pct_weighted": 80,
                    "distribution_pattern": "pyramidal",
                },
                {
                    "window_start": "2026-04-27",
                    "sport": "bike",
                    "distribution_confidence": "high",
                    "n_sessions_usable": 2,
                    "total_duration_min": 120,
                    "z1_pct_weighted": 80,
                    "distribution_pattern": "pyramidal",
                },
            ]
        )
        weekly = MODULE.load_weekly(path)
        summary, details = MODULE.summarize_by_sport(weekly, MODULE.resolve_today("2026-05-07"))

        report = MODULE.build_sport_report("bike", summary, details, MODULE.resolve_today("2026-05-07"))

        self.assertIn("# SYA-15 Bike Continuity Review", report)
        self.assertIn("`2026-04-27` a `2026-05-04`", report)
        self.assertIn("Nota: estas fechas corresponden a las semanas de evaluacion de la ventana", report)
        self.assertIn("`4/4` semanas `usable` son `Z1-dominantes`", report)
        self.assertIn("Sensibilidad de ventana en `bike`", report)
        self.assertIn("`3w` con umbral `2/3`", report)
        self.assertIn("`4w` con umbral `3/4`", report)
        self.assertIn("`5w` con umbral `4/5`", report)

    def test_build_sport_report_uses_custom_input_path(self):
        path = self._write_weekly_csv(
            [
                {
                    "window_start": "2026-04-06",
                    "sport": "bike",
                    "distribution_confidence": "high",
                    "n_sessions_usable": 2,
                    "total_duration_min": 120,
                    "z1_pct_weighted": 80,
                    "distribution_pattern": "pyramidal",
                },
                {
                    "window_start": "2026-04-13",
                    "sport": "bike",
                    "distribution_confidence": "high",
                    "n_sessions_usable": 2,
                    "total_duration_min": 120,
                    "z1_pct_weighted": 80,
                    "distribution_pattern": "pyramidal",
                },
                {
                    "window_start": "2026-04-20",
                    "sport": "bike",
                    "distribution_confidence": "high",
                    "n_sessions_usable": 2,
                    "total_duration_min": 120,
                    "z1_pct_weighted": 80,
                    "distribution_pattern": "pyramidal",
                },
                {
                    "window_start": "2026-04-27",
                    "sport": "bike",
                    "distribution_confidence": "high",
                    "n_sessions_usable": 2,
                    "total_duration_min": 120,
                    "z1_pct_weighted": 80,
                    "distribution_pattern": "pyramidal",
                },
            ]
        )
        weekly = MODULE.load_weekly(path)
        summary, details = MODULE.summarize_by_sport(weekly, MODULE.resolve_today("2026-05-07"))
        custom_input = Path("data/custom_weekly.csv")

        report = MODULE.build_sport_report(
            "bike",
            summary,
            details,
            MODULE.resolve_today("2026-05-07"),
            input_path=custom_input,
        )

        self.assertIn("`data/custom_weekly.csv`", report)

    def test_build_sport_report_uses_requested_min_positive_in_text(self):
        path = self._write_weekly_csv(
            [
                {
                    "window_start": "2026-04-06",
                    "sport": "bike",
                    "distribution_confidence": "high",
                    "n_sessions_usable": 2,
                    "total_duration_min": 120,
                    "z1_pct_weighted": 80,
                    "distribution_pattern": "pyramidal",
                },
                {
                    "window_start": "2026-04-13",
                    "sport": "bike",
                    "distribution_confidence": "high",
                    "n_sessions_usable": 2,
                    "total_duration_min": 120,
                    "z1_pct_weighted": 80,
                    "distribution_pattern": "pyramidal",
                },
                {
                    "window_start": "2026-04-20",
                    "sport": "bike",
                    "distribution_confidence": "high",
                    "n_sessions_usable": 2,
                    "total_duration_min": 120,
                    "z1_pct_weighted": 80,
                    "distribution_pattern": "pyramidal",
                },
                {
                    "window_start": "2026-04-27",
                    "sport": "bike",
                    "distribution_confidence": "high",
                    "n_sessions_usable": 2,
                    "total_duration_min": 120,
                    "z1_pct_weighted": 80,
                    "distribution_pattern": "pyramidal",
                },
            ]
        )
        weekly = MODULE.load_weekly(path)
        summary, details = MODULE.summarize_by_sport(weekly, MODULE.resolve_today("2026-05-07"))

        report = MODULE.build_sport_report(
            "bike",
            summary,
            details,
            MODULE.resolve_today("2026-05-07"),
            min_positive=2,
        )

        self.assertIn("`4w` con `2/4` sigue siendo la configuracion de referencia de esta ejecucion:", report)
        self.assertIn("umbral solicitado en esta ejecucion: `2/4`", report)

    def test_build_report_payload_serializes_focus_section(self):
        path = self._write_weekly_csv(
            [
                {
                    "window_start": "2026-04-06",
                    "sport": "bike",
                    "distribution_confidence": "high",
                    "n_sessions_usable": 2,
                    "total_duration_min": 120,
                    "z1_pct_weighted": 80,
                    "distribution_pattern": "pyramidal",
                },
                {
                    "window_start": "2026-04-13",
                    "sport": "bike",
                    "distribution_confidence": "high",
                    "n_sessions_usable": 2,
                    "total_duration_min": 120,
                    "z1_pct_weighted": 80,
                    "distribution_pattern": "pyramidal",
                },
                {
                    "window_start": "2026-04-20",
                    "sport": "bike",
                    "distribution_confidence": "high",
                    "n_sessions_usable": 2,
                    "total_duration_min": 120,
                    "z1_pct_weighted": 80,
                    "distribution_pattern": "pyramidal",
                },
                {
                    "window_start": "2026-04-27",
                    "sport": "bike",
                    "distribution_confidence": "high",
                    "n_sessions_usable": 2,
                    "total_duration_min": 120,
                    "z1_pct_weighted": 80,
                    "distribution_pattern": "pyramidal",
                },
            ]
        )
        weekly = MODULE.load_weekly(path)
        summary, details = MODULE.summarize_by_sport(weekly, MODULE.resolve_today("2026-05-07"))
        payload = MODULE.build_report_payload(
            "bike",
            summary,
            details,
            MODULE.resolve_today("2026-05-07"),
            input_path=Path("data/custom_weekly.csv"),
            window_size=4,
        )

        self.assertEqual(payload["window_size"], 4)
        self.assertEqual(payload["min_positive"], 3)
        self.assertEqual(payload["focus"]["sport"], "bike")
        self.assertTrue(payload["focus"]["episodes"])
        self.assertEqual(payload["focus"]["detail"][0]["window_start"], "2026-04-06")
        self.assertEqual(payload["input"], "data/custom_weekly.csv")
        json.dumps(payload, allow_nan=False)

    def test_build_report_payload_serializes_missing_weeks_without_nan(self):
        path = self._write_weekly_csv(
            [
                {
                    "window_start": "2026-04-06",
                    "sport": "bike",
                    "distribution_confidence": "high",
                    "n_sessions_usable": 2,
                    "total_duration_min": 120,
                    "z1_pct_weighted": 80,
                    "distribution_pattern": "pyramidal",
                },
                {
                    "window_start": "2026-04-20",
                    "sport": "bike",
                    "distribution_confidence": "high",
                    "n_sessions_usable": 2,
                    "total_duration_min": 120,
                    "z1_pct_weighted": 80,
                    "distribution_pattern": "pyramidal",
                },
            ]
        )
        weekly = MODULE.load_weekly(path)
        summary, details = MODULE.summarize_by_sport(weekly, MODULE.resolve_today("2026-05-07"))
        payload = MODULE.build_report_payload(
            "bike",
            summary,
            details,
            MODULE.resolve_today("2026-05-07"),
            input_path=Path("data/custom_weekly.csv"),
        )

        self.assertIsNone(payload["focus"]["detail"][1]["distribution_confidence"])
        self.assertIsNone(payload["focus"]["detail"][1]["n_sessions_usable"])
        json.dumps(payload, allow_nan=False)

    def test_main_rejects_missing_sport_in_requested_details(self):
        path = self._write_weekly_csv(
            [
                {
                    "window_start": "2026-04-06",
                    "sport": "bike",
                    "distribution_confidence": "high",
                    "n_sessions_usable": 2,
                    "total_duration_min": 120,
                    "z1_pct_weighted": 80,
                    "distribution_pattern": "pyramidal",
                },
                {
                    "window_start": "2026-04-13",
                    "sport": "bike",
                    "distribution_confidence": "high",
                    "n_sessions_usable": 2,
                    "total_duration_min": 120,
                    "z1_pct_weighted": 80,
                    "distribution_pattern": "pyramidal",
                },
                {
                    "window_start": "2026-04-20",
                    "sport": "bike",
                    "distribution_confidence": "high",
                    "n_sessions_usable": 2,
                    "total_duration_min": 120,
                    "z1_pct_weighted": 80,
                    "distribution_pattern": "pyramidal",
                },
                {
                    "window_start": "2026-04-27",
                    "sport": "bike",
                    "distribution_confidence": "high",
                    "n_sessions_usable": 2,
                    "total_duration_min": 120,
                    "z1_pct_weighted": 80,
                    "distribution_pattern": "pyramidal",
                },
            ]
        )
        argv = [
            "analyze_sya15_continuity.py",
            "--input",
            str(path),
            "--sports",
            "trail_run",
        ]

        with self.assertRaisesRegex(ValueError, "Sport not found in input: trail_run"):
            with mock.patch.object(sys, "argv", argv):
                MODULE.main()

    def test_main_prefers_requested_sport_for_report(self):
        path = self._write_weekly_csv(
            [
                {
                    "window_start": "2026-04-06",
                    "sport": "bike",
                    "distribution_confidence": "high",
                    "n_sessions_usable": 2,
                    "total_duration_min": 120,
                    "z1_pct_weighted": 80,
                    "distribution_pattern": "pyramidal",
                },
                {
                    "window_start": "2026-04-13",
                    "sport": "bike",
                    "distribution_confidence": "high",
                    "n_sessions_usable": 2,
                    "total_duration_min": 120,
                    "z1_pct_weighted": 80,
                    "distribution_pattern": "pyramidal",
                },
                {
                    "window_start": "2026-04-20",
                    "sport": "bike",
                    "distribution_confidence": "high",
                    "n_sessions_usable": 2,
                    "total_duration_min": 120,
                    "z1_pct_weighted": 80,
                    "distribution_pattern": "pyramidal",
                },
                {
                    "window_start": "2026-04-27",
                    "sport": "bike",
                    "distribution_confidence": "high",
                    "n_sessions_usable": 2,
                    "total_duration_min": 120,
                    "z1_pct_weighted": 80,
                    "distribution_pattern": "pyramidal",
                },
                {
                    "window_start": "2026-04-06",
                    "sport": "trail_run",
                    "distribution_confidence": "high",
                    "n_sessions_usable": 2,
                    "total_duration_min": 120,
                    "z1_pct_weighted": 80,
                    "distribution_pattern": "pyramidal",
                },
                {
                    "window_start": "2026-04-13",
                    "sport": "trail_run",
                    "distribution_confidence": "high",
                    "n_sessions_usable": 2,
                    "total_duration_min": 120,
                    "z1_pct_weighted": 80,
                    "distribution_pattern": "pyramidal",
                },
                {
                    "window_start": "2026-04-20",
                    "sport": "trail_run",
                    "distribution_confidence": "high",
                    "n_sessions_usable": 2,
                    "total_duration_min": 120,
                    "z1_pct_weighted": 80,
                    "distribution_pattern": "pyramidal",
                },
                {
                    "window_start": "2026-04-27",
                    "sport": "trail_run",
                    "distribution_confidence": "high",
                    "n_sessions_usable": 2,
                    "total_duration_min": 120,
                    "z1_pct_weighted": 80,
                    "distribution_pattern": "pyramidal",
                },
            ]
        )
        report_path = Path(self._write_weekly_csv([]).parent) / "report.md"
        argv = [
            "analyze_sya15_continuity.py",
            "--input",
            str(path),
            "--focus-sport",
            "trail_run",
            "--report-md",
            str(report_path),
        ]

        with mock.patch.object(sys, "argv", argv):
            MODULE.main()

        report = report_path.read_text(encoding="utf-8")
        self.assertIn("# SYA-15 Trail Run Continuity Review", report)
        self.assertNotIn("# SYA-15 Bike Continuity Review", report)

    def test_resolve_report_focus_sport_defaults_to_first_summary_sport(self):
        path = self._write_weekly_csv(
            [
                {
                    "window_start": "2026-04-06",
                    "sport": "bike",
                    "distribution_confidence": "high",
                    "n_sessions_usable": 2,
                    "total_duration_min": 120,
                    "z1_pct_weighted": 80,
                    "distribution_pattern": "pyramidal",
                },
                {
                    "window_start": "2026-04-13",
                    "sport": "bike",
                    "distribution_confidence": "high",
                    "n_sessions_usable": 2,
                    "total_duration_min": 120,
                    "z1_pct_weighted": 80,
                    "distribution_pattern": "pyramidal",
                },
            ]
        )
        weekly = MODULE.load_weekly(path)
        summary, _details = MODULE.summarize_by_sport(weekly, MODULE.resolve_today("2026-05-07"))

        self.assertEqual(MODULE.resolve_report_focus_sport(summary, None), "bike")

    def test_main_report_focus_ignores_requested_details(self):
        path = self._write_weekly_csv(
            [
                {
                    "window_start": "2026-04-06",
                    "sport": "bike",
                    "distribution_confidence": "high",
                    "n_sessions_usable": 2,
                    "total_duration_min": 120,
                    "z1_pct_weighted": 80,
                    "distribution_pattern": "pyramidal",
                },
                {
                    "window_start": "2026-04-13",
                    "sport": "bike",
                    "distribution_confidence": "high",
                    "n_sessions_usable": 2,
                    "total_duration_min": 120,
                    "z1_pct_weighted": 80,
                    "distribution_pattern": "pyramidal",
                },
                {
                    "window_start": "2026-04-20",
                    "sport": "bike",
                    "distribution_confidence": "high",
                    "n_sessions_usable": 2,
                    "total_duration_min": 120,
                    "z1_pct_weighted": 80,
                    "distribution_pattern": "pyramidal",
                },
                {
                    "window_start": "2026-04-27",
                    "sport": "bike",
                    "distribution_confidence": "high",
                    "n_sessions_usable": 2,
                    "total_duration_min": 120,
                    "z1_pct_weighted": 80,
                    "distribution_pattern": "pyramidal",
                },
                {
                    "window_start": "2026-04-06",
                    "sport": "trail_run",
                    "distribution_confidence": "high",
                    "n_sessions_usable": 2,
                    "total_duration_min": 120,
                    "z1_pct_weighted": 80,
                    "distribution_pattern": "pyramidal",
                },
                {
                    "window_start": "2026-04-13",
                    "sport": "trail_run",
                    "distribution_confidence": "high",
                    "n_sessions_usable": 2,
                    "total_duration_min": 120,
                    "z1_pct_weighted": 80,
                    "distribution_pattern": "pyramidal",
                },
                {
                    "window_start": "2026-04-20",
                    "sport": "trail_run",
                    "distribution_confidence": "high",
                    "n_sessions_usable": 2,
                    "total_duration_min": 120,
                    "z1_pct_weighted": 80,
                    "distribution_pattern": "pyramidal",
                },
                {
                    "window_start": "2026-04-27",
                    "sport": "trail_run",
                    "distribution_confidence": "high",
                    "n_sessions_usable": 2,
                    "total_duration_min": 120,
                    "z1_pct_weighted": 80,
                    "distribution_pattern": "pyramidal",
                },
            ]
        )
        report_path = Path(self._write_weekly_csv([]).parent) / "report.md"
        argv = [
            "analyze_sya15_continuity.py",
            "--input",
            str(path),
            "--sports",
            "trail_run",
            "--report-md",
            str(report_path),
        ]

        with mock.patch.object(sys, "argv", argv):
            MODULE.main()

        report = report_path.read_text(encoding="utf-8")
        self.assertIn("# SYA-15 Bike Continuity Review", report)
        self.assertNotIn("# SYA-15 Trail Run Continuity Review", report)

    @requires_real_data
    def test_main_rejects_non_positive_window_size(self):
        argv = [
            "analyze_sya15_continuity.py",
            "--window-size",
            "0",
        ]

        with self.assertRaisesRegex(ValueError, "window_size must be at least 1"):
            with mock.patch.object(sys, "argv", argv):
                MODULE.main()

    @requires_real_data
    def test_main_rejects_invalid_min_positive(self):
        argv = [
            "analyze_sya15_continuity.py",
            "--min-positive",
            "0",
        ]

        with self.assertRaisesRegex(ValueError, "min_positive must be between 1 and 4 for a 4-week window"):
            with mock.patch.object(sys, "argv", argv):
                MODULE.main()

    def test_build_sport_report_works_with_window_size_three(self):
        path = self._write_weekly_csv(
            [
                {
                    "window_start": "2026-04-06",
                    "sport": "bike",
                    "distribution_confidence": "high",
                    "n_sessions_usable": 2,
                    "total_duration_min": 120,
                    "z1_pct_weighted": 80,
                    "distribution_pattern": "pyramidal",
                },
                {
                    "window_start": "2026-04-13",
                    "sport": "bike",
                    "distribution_confidence": "high",
                    "n_sessions_usable": 2,
                    "total_duration_min": 120,
                    "z1_pct_weighted": 80,
                    "distribution_pattern": "pyramidal",
                },
                {
                    "window_start": "2026-04-20",
                    "sport": "bike",
                    "distribution_confidence": "high",
                    "n_sessions_usable": 2,
                    "total_duration_min": 120,
                    "z1_pct_weighted": 80,
                    "distribution_pattern": "pyramidal",
                },
                {
                    "window_start": "2026-04-27",
                    "sport": "bike",
                    "distribution_confidence": "high",
                    "n_sessions_usable": 2,
                    "total_duration_min": 120,
                    "z1_pct_weighted": 80,
                    "distribution_pattern": "pyramidal",
                },
            ]
        )
        weekly = MODULE.load_weekly(path)
        summary, details = MODULE.summarize_by_sport(
            weekly,
            MODULE.resolve_today("2026-05-07"),
            window_size=3,
        )

        report = MODULE.build_sport_report(
            "bike",
            summary,
            details,
            MODULE.resolve_today("2026-05-07"),
            window_size=3,
        )

        self.assertIn("`3w` con `2/3` sigue siendo la configuracion de referencia de esta ejecucion:", report)
        self.assertIn("Sensibilidad de ventana en `bike` con umbral relativo `75%`:", report)
        self.assertIn("`1/3`", report)
        self.assertIn("`2w`", report)
        self.assertIn("`3w`", report)
        self.assertIn("`4w`", report)

    def test_build_sport_report_rejects_window_size_one(self):
        path = self._write_weekly_csv(
            [
                {
                    "window_start": "2026-04-06",
                    "sport": "bike",
                    "distribution_confidence": "high",
                    "n_sessions_usable": 2,
                    "total_duration_min": 120,
                    "z1_pct_weighted": 80,
                    "distribution_pattern": "pyramidal",
                },
                {
                    "window_start": "2026-04-13",
                    "sport": "bike",
                    "distribution_confidence": "high",
                    "n_sessions_usable": 2,
                    "total_duration_min": 120,
                    "z1_pct_weighted": 80,
                    "distribution_pattern": "pyramidal",
                },
            ]
        )
        weekly = MODULE.load_weekly(path)
        summary, details = MODULE.summarize_by_sport(weekly, MODULE.resolve_today("2026-05-07"), window_size=2)

        with self.assertRaisesRegex(ValueError, "window_size must be at least 2"):
            MODULE.build_sport_report(
                "bike",
                summary,
                details,
                MODULE.resolve_today("2026-05-07"),
                window_size=1,
            )

    def test_build_report_payload_rejects_window_size_one(self):
        path = self._write_weekly_csv(
            [
                {
                    "window_start": "2026-04-06",
                    "sport": "bike",
                    "distribution_confidence": "high",
                    "n_sessions_usable": 2,
                    "total_duration_min": 120,
                    "z1_pct_weighted": 80,
                    "distribution_pattern": "pyramidal",
                },
                {
                    "window_start": "2026-04-13",
                    "sport": "bike",
                    "distribution_confidence": "high",
                    "n_sessions_usable": 2,
                    "total_duration_min": 120,
                    "z1_pct_weighted": 80,
                    "distribution_pattern": "pyramidal",
                },
            ]
        )
        weekly = MODULE.load_weekly(path)
        summary, details = MODULE.summarize_by_sport(weekly, MODULE.resolve_today("2026-05-07"), window_size=2)

        with self.assertRaisesRegex(ValueError, "window_size must be at least 2"):
            MODULE.build_report_payload(
                "bike",
                summary,
                details,
                MODULE.resolve_today("2026-05-07"),
                input_path=Path("data/custom_weekly.csv"),
                window_size=1,
            )

    def test_build_sport_report_rejects_invalid_min_positive(self):
        path = self._write_weekly_csv(
            [
                {
                    "window_start": "2026-04-06",
                    "sport": "bike",
                    "distribution_confidence": "high",
                    "n_sessions_usable": 2,
                    "total_duration_min": 120,
                    "z1_pct_weighted": 80,
                    "distribution_pattern": "pyramidal",
                },
                {
                    "window_start": "2026-04-13",
                    "sport": "bike",
                    "distribution_confidence": "high",
                    "n_sessions_usable": 2,
                    "total_duration_min": 120,
                    "z1_pct_weighted": 80,
                    "distribution_pattern": "pyramidal",
                },
            ]
        )
        weekly = MODULE.load_weekly(path)
        summary, details = MODULE.summarize_by_sport(weekly, MODULE.resolve_today("2026-05-07"), window_size=2)

        with self.assertRaisesRegex(ValueError, "min_positive must be between 1 and 2 for a 2-week window"):
            MODULE.build_sport_report(
                "bike",
                summary,
                details,
                MODULE.resolve_today("2026-05-07"),
                window_size=2,
                min_positive=0,
            )

    def test_build_report_payload_rejects_invalid_min_positive(self):
        path = self._write_weekly_csv(
            [
                {
                    "window_start": "2026-04-06",
                    "sport": "bike",
                    "distribution_confidence": "high",
                    "n_sessions_usable": 2,
                    "total_duration_min": 120,
                    "z1_pct_weighted": 80,
                    "distribution_pattern": "pyramidal",
                },
                {
                    "window_start": "2026-04-13",
                    "sport": "bike",
                    "distribution_confidence": "high",
                    "n_sessions_usable": 2,
                    "total_duration_min": 120,
                    "z1_pct_weighted": 80,
                    "distribution_pattern": "pyramidal",
                },
            ]
        )
        weekly = MODULE.load_weekly(path)
        summary, details = MODULE.summarize_by_sport(weekly, MODULE.resolve_today("2026-05-07"), window_size=2)

        with self.assertRaisesRegex(ValueError, "min_positive must be between 1 and 2 for a 2-week window"):
            MODULE.build_report_payload(
                "bike",
                summary,
                details,
                MODULE.resolve_today("2026-05-07"),
                input_path=Path("data/custom_weekly.csv"),
                window_size=2,
                min_positive=0,
            )

    def test_build_report_rejects_mismatched_summary_window_size(self):
        path = self._write_weekly_csv(
            [
                {
                    "window_start": "2026-04-06",
                    "sport": "bike",
                    "distribution_confidence": "high",
                    "n_sessions_usable": 2,
                    "total_duration_min": 120,
                    "z1_pct_weighted": 80,
                    "distribution_pattern": "pyramidal",
                },
                {
                    "window_start": "2026-04-13",
                    "sport": "bike",
                    "distribution_confidence": "high",
                    "n_sessions_usable": 2,
                    "total_duration_min": 120,
                    "z1_pct_weighted": 80,
                    "distribution_pattern": "pyramidal",
                },
                {
                    "window_start": "2026-04-20",
                    "sport": "bike",
                    "distribution_confidence": "high",
                    "n_sessions_usable": 2,
                    "total_duration_min": 120,
                    "z1_pct_weighted": 80,
                    "distribution_pattern": "pyramidal",
                },
                {
                    "window_start": "2026-04-27",
                    "sport": "bike",
                    "distribution_confidence": "high",
                    "n_sessions_usable": 2,
                    "total_duration_min": 120,
                    "z1_pct_weighted": 80,
                    "distribution_pattern": "pyramidal",
                },
            ]
        )
        weekly = MODULE.load_weekly(path)
        summary4, details4 = MODULE.summarize_by_sport(weekly, MODULE.resolve_today("2026-05-07"), window_size=4)
        _, details3 = MODULE.summarize_by_sport(weekly, MODULE.resolve_today("2026-05-07"), window_size=3)

        with self.assertRaisesRegex(
            ValueError,
            "Summary columns do not match the requested window_size 3: missing cont3_evaluable_weeks, cont3_positive_rate, cont3_positive_weeks",
        ):
            MODULE.build_sport_report(
                "bike",
                summary4,
                details3,
                MODULE.resolve_today("2026-05-07"),
                window_size=3,
            )

        with self.assertRaisesRegex(
            ValueError,
            "Summary columns do not match the requested window_size 3: missing cont3_evaluable_weeks, cont3_positive_rate, cont3_positive_weeks",
        ):
            MODULE.build_report_payload(
                "bike",
                summary4,
                details4,
                MODULE.resolve_today("2026-05-07"),
                input_path=Path("data/custom_weekly.csv"),
                window_size=3,
            )

    def test_format_detail_rejects_mismatched_window_size(self):
        path = self._write_weekly_csv(
            [
                {
                    "window_start": "2026-04-06",
                    "sport": "bike",
                    "distribution_confidence": "high",
                    "n_sessions_usable": 2,
                    "total_duration_min": 120,
                    "z1_pct_weighted": 80,
                    "distribution_pattern": "pyramidal",
                },
                {
                    "window_start": "2026-04-13",
                    "sport": "bike",
                    "distribution_confidence": "high",
                    "n_sessions_usable": 2,
                    "total_duration_min": 120,
                    "z1_pct_weighted": 80,
                    "distribution_pattern": "pyramidal",
                },
                {
                    "window_start": "2026-04-20",
                    "sport": "bike",
                    "distribution_confidence": "high",
                    "n_sessions_usable": 2,
                    "total_duration_min": 120,
                    "z1_pct_weighted": 80,
                    "distribution_pattern": "pyramidal",
                },
                {
                    "window_start": "2026-04-27",
                    "sport": "bike",
                    "distribution_confidence": "high",
                    "n_sessions_usable": 2,
                    "total_duration_min": 120,
                    "z1_pct_weighted": 80,
                    "distribution_pattern": "pyramidal",
                },
            ]
        )
        weekly = MODULE.load_weekly(path)
        _, details = MODULE.summarize_by_sport(weekly, MODULE.resolve_today("2026-05-07"), window_size=4)

        with self.assertRaisesRegex(
            ValueError,
            "Detail columns do not match the requested window_size 3: missing cont3_evaluable, cont3_positive",
        ):
            MODULE.format_detail(details["bike"], window_size=3)

    def test_window_size_uses_relative_default_threshold(self):
        path = self._write_weekly_csv(
            [
                {
                    "window_start": "2026-04-06",
                    "sport": "bike",
                    "distribution_confidence": "high",
                    "n_sessions_usable": 2,
                    "total_duration_min": 120,
                    "z1_pct_weighted": 80,
                    "distribution_pattern": "pyramidal",
                },
                {
                    "window_start": "2026-04-13",
                    "sport": "bike",
                    "distribution_confidence": "high",
                    "n_sessions_usable": 2,
                    "total_duration_min": 120,
                    "z1_pct_weighted": 80,
                    "distribution_pattern": "pyramidal",
                },
                {
                    "window_start": "2026-04-20",
                    "sport": "bike",
                    "distribution_confidence": "high",
                    "n_sessions_usable": 2,
                    "total_duration_min": 120,
                    "z1_pct_weighted": 80,
                    "distribution_pattern": "pyramidal",
                },
                {
                    "window_start": "2026-04-27",
                    "sport": "bike",
                    "distribution_confidence": "high",
                    "n_sessions_usable": 2,
                    "total_duration_min": 120,
                    "z1_pct_weighted": 80,
                    "distribution_pattern": "pyramidal",
                },
                {
                    "window_start": "2026-05-04",
                    "sport": "bike",
                    "distribution_confidence": "high",
                    "n_sessions_usable": 2,
                    "total_duration_min": 120,
                    "z1_pct_weighted": 80,
                    "distribution_pattern": "pyramidal",
                },
            ]
        )

        argv = [
            "analyze_sya15_continuity.py",
            "--input",
            str(path),
            "--today",
            "2026-05-15",
            "--window-size",
            "5",
            "--focus-sport",
            "bike",
        ]
        with mock.patch.object(sys, "argv", argv):
            with mock.patch("builtins.print") as mocked_print:
                MODULE.main()

        rendered = "\n".join(" ".join(str(arg) for arg in call.args) for call in mocked_print.call_args_list)
        self.assertIn("Minimum positives in 5w window: 4", rendered)


if __name__ == "__main__":
    unittest.main()
