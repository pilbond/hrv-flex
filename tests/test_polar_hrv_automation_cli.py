import unittest
from io import StringIO
from unittest.mock import ANY, patch

import polar_hrv_automation
from hrv_app.pipeline_status import PipelineResult, result_from_marker


class PolarHrvAutomationCliTests(unittest.TestCase):
    def test_ssm_audit_runs_manual_pipeline_without_oauth_or_sync(self):
        stdout = StringIO()
        with patch("sys.argv", ["polar_hrv_automation.py", "--ssm-audit"]), patch("sys.stdout", stdout), patch.object(
            polar_hrv_automation, "run_build_hrv_ssm_shadow_only", return_value=True
        ) as shadow_mock, patch.object(
            polar_hrv_automation, "run_build_hrv_ssm_validation_only", return_value=True
        ) as validation_mock, patch.object(
            polar_hrv_automation, "run_build_hrv_ssm_outcome_battery_only", return_value=True
        ) as battery_mock, patch.object(
            polar_hrv_automation, "sync_hrv_range"
        ) as sync_mock:
            exit_code = polar_hrv_automation.main()

        self.assertEqual(exit_code, 0)
        shadow_mock.assert_called_once()
        validation_mock.assert_called_once()
        battery_mock.assert_called_once()
        sync_mock.assert_not_called()
        self.assertIn("[RUN] Ejecutando build_hrv_ssm.py...", stdout.getvalue())
        self.assertIn("[OK] Auditoria SSM completada", stdout.getvalue())

    def test_ssm_audit_rejects_sync_flags(self):
        with patch("sys.argv", ["polar_hrv_automation.py", "--ssm-audit", "--process"]):
            with self.assertRaises(SystemExit) as ctx:
                polar_hrv_automation.main()

        self.assertEqual(ctx.exception.code, 2)

    def test_normal_run_calls_sync_with_structured_result(self):
        with patch("sys.argv", ["polar_hrv_automation.py"]), \
             patch.object(polar_hrv_automation, "auto_restore_if_empty") as restore_mock, \
             patch.object(polar_hrv_automation, "sync_hrv_range", return_value=PipelineResult()) as sync_mock, \
             patch.object(polar_hrv_automation, "run_dropbox_backup"):
            exit_code = polar_hrv_automation.main()

        self.assertEqual(exit_code, 0)
        restore_mock.assert_called_once()
        sync_mock.assert_called_once_with(ANY, None, None, [])

    def test_failed_pipeline_result_exits_nonzero_and_skips_backup(self):
        stdout = StringIO()
        failed = PipelineResult().fail("core", "builder_failed", "CORE falló")
        with patch("sys.argv", ["polar_hrv_automation.py", "--process"]), \
             patch("sys.stdout", stdout), \
             patch.object(polar_hrv_automation, "auto_restore_if_empty", return_value={"status": "skipped"}), \
             patch.object(polar_hrv_automation, "sync_hrv_range", return_value=failed), \
             patch.object(polar_hrv_automation, "run_dropbox_backup") as backup_mock:
            exit_code = polar_hrv_automation.main()

        self.assertEqual(exit_code, 1)
        backup_mock.assert_not_called()
        self.assertEqual(result_from_marker(stdout.getvalue())["error"]["code"], "builder_failed")

    def test_debug_sports_v4_runs_then_returns(self):
        with patch("sys.argv", ["polar_hrv_automation.py", "--debug-sports"]), \
             patch.object(polar_hrv_automation, "_debug_sports_v4") as debug_mock:
            exit_code = polar_hrv_automation.main()

        self.assertEqual(exit_code, 0)
        debug_mock.assert_called_once()

    def test_auth_flag_exits_with_hint(self):
        with patch("sys.argv", ["polar_hrv_automation.py", "--auth"]):
            with self.assertRaises(SystemExit) as ctx:
                polar_hrv_automation.main()

        self.assertEqual(ctx.exception.code, 3)


if __name__ == "__main__":
    unittest.main()
