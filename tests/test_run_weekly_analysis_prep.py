import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import pandas as pd

from analysis import run_weekly_analysis_prep as MODULE
from analysis import sya15_continuity


class RunWeeklyAnalysisPrepTests(unittest.TestCase):
    def _write_weekly_csv(self, rows):
        tmpdir = TemporaryDirectory()
        self.addCleanup(tmpdir.cleanup)
        path = Path(tmpdir.name) / "weekly.csv"
        pd.DataFrame(rows).to_csv(path, index=False)
        return path

    def test_default_weekly_dir_uses_week_bounds(self):
        today = sya15_continuity.resolve_today("2026-05-15")
        weekly_dir = MODULE.default_weekly_dir(today)
        self.assertTrue(str(weekly_dir).endswith(r"analysis\reports\weekly\2026-05-11_2026-05-17"))

    def test_default_manifest_path_uses_week_bounds(self):
        today = sya15_continuity.resolve_today("2026-05-15")
        manifest_path = MODULE.default_manifest_path(today)
        self.assertTrue(str(manifest_path).endswith(r"analysis\reports\weekly\2026-05-11_2026-05-17\weekly_prep_manifest.json"))

    def test_build_weekly_prep_writes_manifest_and_sidecars(self):
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
            weekly_dir = Path(tmpdir) / "weekly"
            payload = MODULE.build_weekly_prep(
                today=sya15_continuity.resolve_today("2026-05-15"),
                weekly_dir=weekly_dir,
                input_path=path,
                focus_sport=None,
                window_size=4,
                min_positive=None,
            )

            manifest_path = Path(payload["manifest_path"])
            self.assertTrue(manifest_path.exists())
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(manifest["prep_kind"], "weekly_analysis_prep")
            self.assertEqual(manifest["week_start"], "2026-05-11")
            self.assertEqual(manifest["week_end"], "2026-05-17")
            self.assertEqual(len(manifest["sidecars"]), 1)
            sidecar = manifest["sidecars"][0]
            self.assertEqual(sidecar["sidecar"], "sya15_continuity")
            self.assertTrue(Path(sidecar["report_md"]).exists())
            self.assertTrue(Path(sidecar["report_json"]).exists())

    def test_load_weekly_prep_manifest_and_get_sidecar(self):
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
            weekly_dir = Path(tmpdir) / "weekly"
            payload = MODULE.build_weekly_prep(
                today=sya15_continuity.resolve_today("2026-05-15"),
                weekly_dir=weekly_dir,
                input_path=path,
                focus_sport=None,
                window_size=4,
                min_positive=None,
            )

            manifest = MODULE.load_weekly_prep_manifest(Path(payload["manifest_path"]))
            sidecar = MODULE.get_sidecar(manifest, "sya15_continuity")
            self.assertEqual(sidecar["artifact_stem"], "sya15_continuity_trail_run_3of4w")
            self.assertEqual(MODULE.iter_sidecars(manifest, sidecar_name="sya15_continuity"), [sidecar])

    def test_load_weekly_prep_manifest_rejects_invalid_prep_kind(self):
        with TemporaryDirectory() as tmpdir:
            manifest_path = Path(tmpdir) / "weekly_prep_manifest.json"
            manifest_path.write_text(json.dumps({"prep_kind": "wrong", "sidecars": []}), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "Invalid weekly prep manifest"):
                MODULE.load_weekly_prep_manifest(manifest_path)

    def test_build_weekly_prep_rejects_window_size_below_2_early(self):
        path = self._write_weekly_csv(
            [
                {
                    "window_start": "2026-04-27",
                    "sport": "trail_run",
                    "distribution_confidence": "high",
                    "n_sessions_usable": 2,
                    "total_duration_min": 120,
                    "z1_pct_weighted": 80,
                    "distribution_pattern": "pyramidal",
                }
            ]
        )
        with TemporaryDirectory() as tmpdir:
            weekly_dir = Path(tmpdir) / "weekly"
            with self.assertRaisesRegex(ValueError, "window_size must be at least 2"):
                MODULE.build_weekly_prep(
                    today=sya15_continuity.resolve_today("2026-05-15"),
                    weekly_dir=weekly_dir,
                    input_path=path,
                    focus_sport=None,
                    window_size=1,
                    min_positive=None,
                )


if __name__ == "__main__":
    unittest.main()
