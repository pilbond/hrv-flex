import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import build_sessions


class BuildSessionsCliTests(unittest.TestCase):
    def test_main_bootstraps_output_dir_before_pipeline(self):
        with TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)
            with patch("sys.argv", ["build_sessions.py", "--update", "--output", str(output_dir)]), \
                patch.object(build_sessions, "API_KEY", "api-key"), \
                patch.object(build_sessions, "ATHLETE_ID", "athlete-id"), \
                patch.object(build_sessions, "resolve_update_oldest", return_value="2026-06-01"), \
                patch.object(build_sessions, "resolve_writable_dir", return_value=output_dir), \
                patch.object(build_sessions, "auto_restore_if_empty") as restore_mock, \
                patch.object(build_sessions, "run_pipeline") as pipeline_mock:
                build_sessions.main()

        restore_mock.assert_called_once_with(data_dir=output_dir)
        pipeline_mock.assert_called_once()


if __name__ == "__main__":
    unittest.main()
