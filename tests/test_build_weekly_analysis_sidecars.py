import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

import pandas as pd

from analysis import build_weekly_analysis_sidecars as MODULE
from analysis import sya15_continuity


class BuildWeeklyAnalysisSidecarsTests(unittest.TestCase):
    def _write_weekly_csv(self, rows):
        tmpdir = TemporaryDirectory()
        self.addCleanup(tmpdir.cleanup)
        path = Path(tmpdir.name) / "weekly.csv"
        pd.DataFrame(rows).to_csv(path, index=False)
        return path

    def test_default_out_dir_uses_week_bounds(self):
        today = sya15_continuity.resolve_today("2026-05-15")
        out_dir = MODULE.default_out_dir(today)
        self.assertTrue(str(out_dir).endswith(r"analysis\reports\weekly\2026-05-11_2026-05-17\artifacts"))

    def test_build_sya15_weekly_sidecar_writes_report_files(self):
        path = self._write_weekly_csv(
            [
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
        with TemporaryDirectory() as tmpdir:
            out_dir = Path(tmpdir) / "artifacts"
            payload = MODULE.build_sya15_weekly_sidecar(
                today=sya15_continuity.resolve_today("2026-05-15"),
                out_dir=out_dir,
                input_path=path,
                focus_sport=None,
                window_size=4,
                min_positive=None,
            )

            report_md = Path(payload["report_md"])
            report_json = Path(payload["report_json"])
            self.assertEqual(payload["focus_sport"], "trail_run")
            self.assertEqual(payload["artifact_stem"], "sya15_continuity_trail_run_3of4w")
            self.assertTrue(report_md.exists())
            self.assertTrue(report_json.exists())
            self.assertIn("# SYA-15 Trail Run Continuity Review", report_md.read_text(encoding="utf-8"))
            json.loads(report_json.read_text(encoding="utf-8"))

    def test_build_sya15_weekly_sidecar_keeps_parameterized_variants(self):
        path = self._write_weekly_csv(
            [
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
        with TemporaryDirectory() as tmpdir:
            out_dir = Path(tmpdir) / "artifacts"
            payload_4w = MODULE.build_sya15_weekly_sidecar(
                today=sya15_continuity.resolve_today("2026-05-15"),
                out_dir=out_dir,
                input_path=path,
                focus_sport=None,
                window_size=4,
                min_positive=None,
            )
            payload_3w = MODULE.build_sya15_weekly_sidecar(
                today=sya15_continuity.resolve_today("2026-05-15"),
                out_dir=out_dir,
                input_path=path,
                focus_sport=None,
                window_size=3,
                min_positive=None,
            )

            self.assertNotEqual(payload_4w["report_md"], payload_3w["report_md"])
            self.assertNotEqual(payload_4w["report_json"], payload_3w["report_json"])
            self.assertTrue(Path(payload_4w["report_md"]).exists())
            self.assertTrue(Path(payload_3w["report_md"]).exists())

    def test_build_sya15_weekly_sidecar_validates_window_size_once(self):
        path = self._write_weekly_csv(
            [
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
        original = sya15_continuity.validate_report_window_size
        with TemporaryDirectory() as tmpdir, mock.patch.object(
            sya15_continuity,
            "validate_report_window_size",
            wraps=original,
        ) as validate_mock:
            MODULE.build_sya15_weekly_sidecar(
                today=sya15_continuity.resolve_today("2026-05-15"),
                out_dir=Path(tmpdir) / "artifacts",
                input_path=path,
                focus_sport=None,
                window_size=4,
                min_positive=None,
            )
            self.assertEqual(validate_mock.call_count, 1)


if __name__ == "__main__":
    unittest.main()
