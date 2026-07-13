import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from hrv_app.ai import config as ai_config


class AiBriefStorageTests(unittest.TestCase):
    def test_history_paths_are_isolated_by_brief_type(self):
        with TemporaryDirectory() as tmpdir, patch.object(ai_config, "DATA_DIR", Path(tmpdir)):
            self.assertEqual(
                ai_config.ai_daily_brief_history_path("2026-07-10"),
                Path(tmpdir) / "ai_briefs" / "daily" / "ENDURANCE_HRV_ai_daily_brief_2026-07-10.json",
            )
            self.assertEqual(
                ai_config.ai_ssm_brief_history_path("2026-07-10"),
                Path(tmpdir) / "ai_briefs" / "ssm" / "ENDURANCE_HRV_ai_ssm_brief_2026-07-10.json",
            )

    def test_migrates_legacy_history_without_touching_latest(self):
        with TemporaryDirectory() as tmpdir, patch.object(ai_config, "DATA_DIR", Path(tmpdir)):
            root = Path(tmpdir)
            daily = root / "ENDURANCE_HRV_ai_daily_brief_2026-07-10.json"
            ssm = root / "ENDURANCE_HRV_ai_ssm_brief_2026-07-10.json"
            latest = root / "ENDURANCE_HRV_ai_daily_brief_latest.json"
            daily.write_text('{"kind":"daily"}', encoding="utf-8")
            ssm.write_text('{"kind":"ssm"}', encoding="utf-8")
            latest.write_text('{"kind":"latest"}', encoding="utf-8")

            self.assertEqual(ai_config.migrate_legacy_ai_brief_history(), {"moved": 2, "conflicts": 0, "errors": 0})
            self.assertFalse(daily.exists())
            self.assertFalse(ssm.exists())
            self.assertTrue(latest.exists())
            self.assertTrue(ai_config.ai_daily_brief_history_path("2026-07-10").exists())
            self.assertTrue(ai_config.ai_ssm_brief_history_path("2026-07-10").exists())
            self.assertEqual(ai_config.migrate_legacy_ai_brief_history(), {"moved": 0, "conflicts": 0, "errors": 0})

    def test_keeps_conflicting_legacy_file_for_manual_resolution(self):
        with TemporaryDirectory() as tmpdir, patch.object(ai_config, "DATA_DIR", Path(tmpdir)):
            root = Path(tmpdir)
            source = root / "ENDURANCE_HRV_ai_daily_brief_2026-07-10.json"
            destination = ai_config.ai_daily_brief_history_path("2026-07-10")
            source.write_text('{"version":"legacy"}', encoding="utf-8")
            destination.parent.mkdir(parents=True)
            destination.write_text('{"version":"new"}', encoding="utf-8")

            self.assertEqual(ai_config.migrate_legacy_ai_brief_history(), {"moved": 0, "conflicts": 1, "errors": 0})
            self.assertTrue(source.exists())
            self.assertEqual(destination.read_text(encoding="utf-8"), '{"version":"new"}')
