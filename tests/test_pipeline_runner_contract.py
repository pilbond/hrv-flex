import contextlib
import io
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pipeline_runner


class PipelineRunnerContractTests(unittest.TestCase):
    def test_build_hrv_core_cmd_keeps_rr_files_ordered(self):
        cmd = pipeline_runner.build_hrv_core_cmd([Path("one.csv"), "two.csv"])

        self.assertEqual(cmd[0], sys.executable)
        self.assertEqual(cmd[1], "build_hrv_core.py")
        self.assertEqual(
            cmd[2:],
            ["--rr-file", "one.csv", "--rr-file", "two.csv"],
        )

    def test_run_build_hrv_final_dashboard_only_uses_utf8_env(self):
        fake_result = SimpleNamespace(stdout="dashboard listo\n")
        buffer = io.StringIO()

        with (
            patch.object(pipeline_runner.Path, "exists", return_value=True),
            patch.object(pipeline_runner.subprocess, "run", return_value=fake_result) as run_mock,
            contextlib.redirect_stdout(buffer),
        ):
            ok = pipeline_runner.run_build_hrv_final_dashboard_only()

        self.assertTrue(ok)
        self.assertIn("dashboard listo", buffer.getvalue())
        run_mock.assert_called_once()

        args, kwargs = run_mock.call_args
        self.assertEqual(args[0][0], sys.executable)
        self.assertEqual(args[0][1], "build_hrv_final_dashboard.py")
        self.assertEqual(kwargs["encoding"], "utf-8")
        self.assertEqual(kwargs["errors"], "replace")
        self.assertTrue(kwargs["check"])
        self.assertEqual(kwargs["env"]["PYTHONIOENCODING"], "utf-8")


if __name__ == "__main__":
    unittest.main()
