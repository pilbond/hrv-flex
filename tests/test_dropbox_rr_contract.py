import contextlib
import io
import tempfile
import unittest
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import subprocess

import hrv_app.dropbox_rr as dropbox_rr


class DropboxRrContractTests(unittest.TestCase):
    def test_extract_date_from_rr_filename_handles_polar_and_dropbox_patterns(self):
        self.assertEqual(
            dropbox_rr._extract_date_from_rr_filename("User_2026-03-01_from_jsonl_RR.CSV"),
            date(2026, 3, 1),
        )
        self.assertEqual(
            dropbox_rr._extract_date_from_rr_filename("Polar_User_2026-03-02_07-15-00_RR.CSV"),
            date(2026, 3, 2),
        )

    def test_scan_rr_files_by_date_and_compute_missing_dates(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            old_rr = root / "old_2026-03-01_from_jsonl_RR.CSV"
            new_rr = root / "new_2026-03-03_from_jsonl_RR.CSV"
            aux = root / "old_2026-03-01_from_jsonl_RR_events.csv"
            polar_rr = root / "polar_2026-03-02_RR.CSV"

            old_rr.write_text("duration,offline\n100,0\n", encoding="utf-8")
            new_rr.write_text("duration,offline\n120,0\n", encoding="utf-8")
            aux.write_text("ignored\n", encoding="utf-8")
            polar_rr.write_text("duration,offline\n130,0\n", encoding="utf-8")

            indexed = dropbox_rr._scan_rr_files_by_date(root, source_tag="from_jsonl")
            missing = dropbox_rr._compute_target_missing_dates(
                date(2026, 3, 1),
                date(2026, 3, 3),
                {date(2026, 3, 1)},
            )

            self.assertEqual(indexed[date(2026, 3, 1)], old_rr)
            self.assertEqual(indexed[date(2026, 3, 3)], new_rr)
            self.assertEqual(missing, [date(2026, 3, 2), date(2026, 3, 3)])
            self.assertNotIn(date(2026, 3, 2), indexed)

    def test_scan_rr_files_by_date_without_source_tag_includes_all_rr_files(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            dropbox_rr_path = root / "dropbox_2026-03-01_from_jsonl_RR.CSV"
            polar_rr_path = root / "polar_2026-03-02_RR.CSV"

            dropbox_rr_path.write_text("duration,offline\n100,0\n", encoding="utf-8")
            polar_rr_path.write_text("duration,offline\n120,0\n", encoding="utf-8")

            indexed = dropbox_rr._scan_rr_files_by_date(root)

            self.assertEqual(indexed[date(2026, 3, 1)], dropbox_rr_path)
            self.assertEqual(indexed[date(2026, 3, 2)], polar_rr_path)

    def test_run_dropbox_rr_import_for_dates_updates_index_from_subprocess(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            preexisting = root / "existing_2026-03-01_from_jsonl_RR.CSV"
            preexisting.write_text("duration,offline\n90,0\n", encoding="utf-8")

            fake_result = SimpleNamespace(stdout="dropbox ok\n", stderr="", returncode=0)
            buffer = io.StringIO()

            def fake_run(cmd, **kwargs):
                new_file = root / "fresh_2026-03-02_from_jsonl_RR.CSV"
                new_file.write_text("duration,offline\n100,0\n", encoding="utf-8")
                return fake_result

            with (
                patch.object(dropbox_rr, "DROPBOX_RR_ENABLED", True),
                patch.object(dropbox_rr, "DROPBOX_FOLDER_PATH", "/HRV/raw_jsonl"),
                patch.object(dropbox_rr.subprocess, "run", side_effect=fake_run) as run_mock,
                contextlib.redirect_stdout(buffer),
            ):
                result, new_count = dropbox_rr._run_dropbox_rr_import_for_dates(
                    [date(2026, 3, 1), date(2026, 3, 2)],
                    root,
                    verbose=True,
                )

            self.assertEqual(new_count, 1)
            self.assertEqual(result[date(2026, 3, 1)], preexisting)
            self.assertEqual(result[date(2026, 3, 2)], root / "fresh_2026-03-02_from_jsonl_RR.CSV")
            run_mock.assert_called_once()
            self.assertIn("--dropbox-folder", run_mock.call_args.args[0])
            self.assertIn("--outdir", run_mock.call_args.args[0])

    def test_run_dropbox_rr_import_for_dates_passes_timeout_and_survives_timeout(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            preexisting = root / "existing_2026-03-01_from_jsonl_RR.CSV"
            preexisting.write_text("duration,offline\n90,0\n", encoding="utf-8")

            buffer = io.StringIO()

            def fake_run(cmd, **kwargs):
                raise subprocess.TimeoutExpired(cmd=cmd, timeout=kwargs.get("timeout"))

            with (
                patch.object(dropbox_rr, "DROPBOX_RR_ENABLED", True),
                patch.object(dropbox_rr, "DROPBOX_FOLDER_PATH", "/HRV/raw_jsonl"),
                patch.object(dropbox_rr, "DROPBOX_RR_TIMEOUT_SEC", 17),
                patch.object(dropbox_rr.subprocess, "run", side_effect=fake_run) as run_mock,
                contextlib.redirect_stdout(buffer),
            ):
                result, new_count = dropbox_rr._run_dropbox_rr_import_for_dates(
                    [date(2026, 3, 1), date(2026, 3, 2)],
                    root,
                    verbose=False,
                )

            self.assertEqual(new_count, 0)
            self.assertEqual(result[date(2026, 3, 1)], preexisting)
            self.assertIn("Timeout ejecutando importación Dropbox RR", buffer.getvalue())
            run_mock.assert_called_once()
            self.assertEqual(run_mock.call_args.kwargs["timeout"], 17)

    def test_run_dropbox_rr_import_warns_to_stderr_when_folder_missing_even_if_quiet(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            preexisting = root / "existing_2026-03-01_from_jsonl_RR.CSV"
            preexisting.write_text("duration,offline\n90,0\n", encoding="utf-8")

            stdout_buffer = io.StringIO()
            stderr_buffer = io.StringIO()

            with (
                patch.object(dropbox_rr, "DROPBOX_RR_ENABLED", True),
                patch.object(dropbox_rr, "DROPBOX_FOLDER_PATH", ""),
                patch.object(dropbox_rr, "DROPBOX_RR_TIMEOUT_SEC", 17),
                patch.object(dropbox_rr, "_qprint") as qprint_mock,
                contextlib.redirect_stdout(stdout_buffer),
                contextlib.redirect_stderr(stderr_buffer),
            ):
                result, new_count = dropbox_rr._run_dropbox_rr_import_for_dates(
                    [date(2026, 3, 1), date(2026, 3, 2)],
                    root,
                    verbose=False,
                )

            self.assertEqual(new_count, 0)
            self.assertEqual(result[date(2026, 3, 1)], preexisting)
            self.assertIn("falta HRV_DROPBOX_FOLDER_PATH/DROPBOX_FOLDER_PATH", stderr_buffer.getvalue())
            qprint_mock.assert_not_called()
            self.assertEqual(stdout_buffer.getvalue(), "")


if __name__ == "__main__":
    unittest.main()
