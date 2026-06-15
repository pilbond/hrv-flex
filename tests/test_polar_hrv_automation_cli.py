import unittest
from io import StringIO
from unittest.mock import ANY, patch

import polar_hrv_automation


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
            polar_hrv_automation, "load_tokens"
        ) as load_tokens_mock, patch.object(
            polar_hrv_automation, "list_exercises"
        ) as list_mock, patch.object(
            polar_hrv_automation, "sync_hrv_range"
        ) as sync_mock:
            exit_code = polar_hrv_automation.main()

        self.assertEqual(exit_code, 0)
        shadow_mock.assert_called_once()
        validation_mock.assert_called_once()
        battery_mock.assert_called_once()
        load_tokens_mock.assert_not_called()
        list_mock.assert_not_called()
        sync_mock.assert_not_called()
        self.assertIn("[RUN] Ejecutando build_hrv_ssm.py...", stdout.getvalue())
        self.assertIn("[OK] Auditoria SSM completada", stdout.getvalue())

    def test_ssm_audit_rejects_sync_flags(self):
        with patch("sys.argv", ["polar_hrv_automation.py", "--ssm-audit", "--process"]):
            with self.assertRaises(SystemExit) as ctx:
                polar_hrv_automation.main()

        self.assertEqual(ctx.exception.code, 2)

    def test_normal_run_does_not_fetch_polar_exercises(self):
        with patch("sys.argv", ["polar_hrv_automation.py"]), patch.object(
            polar_hrv_automation, "load_tokens", return_value=("token", "user")
        ), patch.object(
            polar_hrv_automation, "register_user_if_needed", return_value={"status": "ok"}
        ), patch.object(polar_hrv_automation, "list_exercises") as list_mock, patch.object(
            polar_hrv_automation, "sync_hrv_range"
        ) as sync_mock, patch.object(polar_hrv_automation, "run_dropbox_backup"):
            exit_code = polar_hrv_automation.main()

        self.assertEqual(exit_code, 0)
        list_mock.assert_not_called()
        sync_mock.assert_called_once_with(ANY, "token", "user", [])

    def test_debug_sports_fetches_polar_exercises(self):
        exercises = [{"id": "abc123"}]
        with patch("sys.argv", ["polar_hrv_automation.py", "--debug-sports"]), patch.object(
            polar_hrv_automation, "load_tokens", return_value=("token", "user")
        ), patch.object(
            polar_hrv_automation, "register_user_if_needed", return_value={"status": "ok"}
        ), patch.object(
            polar_hrv_automation, "list_exercises", return_value=exercises
        ) as list_mock, patch.object(polar_hrv_automation, "sync_hrv_range") as sync_mock, patch.object(
            polar_hrv_automation, "run_dropbox_backup"
        ):
            exit_code = polar_hrv_automation.main()

        self.assertEqual(exit_code, 0)
        list_mock.assert_called_once_with("token")
        sync_mock.assert_called_once_with(ANY, "token", "user", exercises)


if __name__ == "__main__":
    unittest.main()
