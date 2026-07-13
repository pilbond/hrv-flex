import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import MagicMock, patch

from hrv_app import backup_dropbox


def _response(status_code=200, payload=None):
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = payload if payload is not None else {}
    return resp


class BackupDropboxContractTests(unittest.TestCase):
    def test_disabled_is_noop_without_network(self):
        with patch.dict("os.environ", {"HRV_BACKUP_DROPBOX_ENABLED": "0"}, clear=False), \
                patch.object(backup_dropbox.requests, "post") as post_mock:
            result = backup_dropbox.run_backup()

        self.assertEqual(result["status"], "disabled")
        post_mock.assert_not_called()

    def test_enabled_without_credentials_skips_gracefully(self):
        env = {
            "HRV_BACKUP_DROPBOX_ENABLED": "1",
            "DROPBOX_ACCESS_TOKEN": "",
            "DROPBOX_REFRESH_TOKEN": "",
            "DROPBOX_APP_KEY": "",
            "DROPBOX_APP_SECRET": "",
        }
        with patch.dict("os.environ", env, clear=False), \
                patch.object(backup_dropbox.requests, "post") as post_mock:
            result = backup_dropbox.run_backup()

        self.assertEqual(result["status"], "no_credentials")
        post_mock.assert_not_called()

    def test_uploads_canonical_files_and_ai_brief_history(self):
        env = {
            "HRV_BACKUP_DROPBOX_ENABLED": "1",
            "DROPBOX_ACCESS_TOKEN": "tok",
            "DROPBOX_REFRESH_TOKEN": "",
            "HRV_BACKUP_DROPBOX_PATH": "/hrv_backups",
        }

        def fake_post(url, **kwargs):
            return _response(200, {})

        with TemporaryDirectory() as tmpdir:
            data_dir = Path(tmpdir)
            (data_dir / "ENDURANCE_HRV_master_FINAL.csv").write_text("Fecha\n2026-06-12\n", encoding="utf-8")
            (data_dir / "ENDURANCE_HRV_weekly_coach.json").write_text("{}", encoding="utf-8")
            ai_history = data_dir / "ai_briefs" / "daily" / "ENDURANCE_HRV_ai_daily_brief_2026-07-10.json"
            ai_history.parent.mkdir(parents=True)
            ai_history.write_text("{}", encoding="utf-8")
            (data_dir / "otro_archivo.csv").write_text("x\n", encoding="utf-8")

            with patch.dict("os.environ", env, clear=False), \
                    patch.object(backup_dropbox, "DATA_DIR", data_dir), \
                    patch.object(backup_dropbox.requests, "post", side_effect=fake_post) as post_mock:
                result = backup_dropbox.run_backup()

        self.assertEqual(result["status"], "ok")
        # Solo los ENDURANCE_HRV_* cubiertos, no "otro_archivo.csv".
        self.assertEqual(result["uploaded"], 3)
        self.assertEqual(result["folder"], "/hrv_backups")

        upload_calls = [
            c for c in post_mock.call_args_list if c.args[0] == backup_dropbox._UPLOAD_URL
        ]
        self.assertEqual(len(upload_calls), 3)
        folder_calls = [
            c for c in post_mock.call_args_list if c.args[0] == backup_dropbox._CREATE_FOLDER_URL
        ]
        self.assertEqual(
            [c.kwargs["json"]["path"] for c in folder_calls],
            ["/hrv_backups", "/hrv_backups/ai_briefs", "/hrv_backups/ai_briefs/daily"],
        )
        uploaded_paths = {
            __import__("json").loads(c.kwargs["headers"]["Dropbox-API-Arg"])["path"]
            for c in upload_calls
        }
        self.assertEqual(
            uploaded_paths,
            {
                "/hrv_backups/ENDURANCE_HRV_master_FINAL.csv",
                "/hrv_backups/ENDURANCE_HRV_weekly_coach.json",
                "/hrv_backups/ai_briefs/daily/ENDURANCE_HRV_ai_daily_brief_2026-07-10.json",
            },
        )

    def test_upload_failure_reports_partial_and_never_raises(self):
        env = {
            "HRV_BACKUP_DROPBOX_ENABLED": "1",
            "DROPBOX_ACCESS_TOKEN": "tok",
            "DROPBOX_REFRESH_TOKEN": "",
        }

        def fake_post(url, **kwargs):
            if url == backup_dropbox._UPLOAD_URL:
                return _response(500, {})
            return _response(200, {"entries": []})

        with TemporaryDirectory() as tmpdir:
            data_dir = Path(tmpdir)
            (data_dir / "ENDURANCE_HRV_master_FINAL.csv").write_text("Fecha\n", encoding="utf-8")

            with patch.dict("os.environ", env, clear=False), \
                    patch.object(backup_dropbox, "DATA_DIR", data_dir), \
                    patch.object(backup_dropbox.requests, "post", side_effect=fake_post):
                result = backup_dropbox.run_backup()

        self.assertEqual(result["status"], "partial")
        self.assertEqual(result["failed"], 1)

    def test_folder_successes_are_cached_when_a_later_folder_fails(self):
        env = {
            "HRV_BACKUP_DROPBOX_ENABLED": "1",
            "DROPBOX_ACCESS_TOKEN": "tok",
            "HRV_BACKUP_DROPBOX_PATH": "/hrv_backups",
        }

        def fake_post(url, **kwargs):
            if url == backup_dropbox._CREATE_FOLDER_URL:
                if kwargs["json"]["path"] == "/hrv_backups/ai_briefs":
                    return _response(500, {})
                return _response(200, {})
            return _response(200, {})

        with TemporaryDirectory() as tmpdir:
            data_dir = Path(tmpdir)
            (data_dir / "ENDURANCE_HRV_master_FINAL.csv").write_text("Fecha\n", encoding="utf-8")
            ai_dir = data_dir / "ai_briefs" / "daily"
            ai_dir.mkdir(parents=True)
            for date_str in ("2026-07-10", "2026-07-11"):
                (ai_dir / f"ENDURANCE_HRV_ai_daily_brief_{date_str}.json").write_text("{}", encoding="utf-8")

            with patch.dict("os.environ", env, clear=False), \
                    patch.object(backup_dropbox, "DATA_DIR", data_dir), \
                    patch.object(backup_dropbox.requests, "post", side_effect=fake_post) as post_mock:
                result = backup_dropbox.run_backup()

        self.assertEqual(result["status"], "partial")
        self.assertEqual(result["uploaded"], 1)
        self.assertEqual(result["failed"], 2)
        folder_paths = [
            c.kwargs["json"]["path"]
            for c in post_mock.call_args_list
            if c.args[0] == backup_dropbox._CREATE_FOLDER_URL
        ]
        self.assertEqual(folder_paths.count("/hrv_backups"), 1)
        self.assertEqual(folder_paths.count("/hrv_backups/ai_briefs"), 2)

    def test_list_available_backups_includes_nested_ai_history(self):
        env = {
            "DROPBOX_ACCESS_TOKEN": "tok",
            "DROPBOX_REFRESH_TOKEN": "",
            "DROPBOX_APP_KEY": "",
            "DROPBOX_APP_SECRET": "",
            "HRV_BACKUP_DROPBOX_PATH": "/hrv_backups",
        }
        entries = {
            "entries": [
                {
                    ".tag": "file",
                    "name": "ENDURANCE_HRV_ai_daily_brief_2026-07-11.json",
                    "path_display": "/hrv_backups/ai_briefs/daily/ENDURANCE_HRV_ai_daily_brief_2026-07-11.json",
                },
            ],
            "has_more": False,
        }

        def fake_post(url, **kwargs):
            self.assertEqual(url, backup_dropbox._LIST_FOLDER_URL)
            self.assertEqual(kwargs["json"], {"path": "/hrv_backups", "recursive": True})
            return _response(200, entries)

        with patch.dict("os.environ", env, clear=False), \
                patch.object(backup_dropbox.requests, "post", side_effect=fake_post):
            result = backup_dropbox.list_available_backups()

        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["files"], ["ai_briefs/daily/ENDURANCE_HRV_ai_daily_brief_2026-07-11.json"])

    def test_unexpected_exception_is_swallowed(self):
        env = {"HRV_BACKUP_DROPBOX_ENABLED": "1", "DROPBOX_ACCESS_TOKEN": "tok"}
        with patch.dict("os.environ", env, clear=False), \
                patch.object(backup_dropbox, "_canonical_files", side_effect=RuntimeError("boom")):
            result = backup_dropbox.run_backup()
        self.assertEqual(result["status"], "error")


class RestoreBackupContractTests(unittest.TestCase):
    def test_restore_downloads_files_atomically_to_data_dir(self):
        env = {"DROPBOX_ACCESS_TOKEN": "tok", "HRV_BACKUP_DROPBOX_PATH": "/hrv_backups"}
        file_entries = {
            "entries": [
                {".tag": "file", "name": "ENDURANCE_HRV_sleep.csv"},
                {".tag": "file", "name": "ENDURANCE_HRV_master_FINAL.csv"},
            ]
        }

        def fake_post(url, **kwargs):
            if url == backup_dropbox._LIST_FOLDER_URL:
                return _response(200, file_entries)
            if url == backup_dropbox._DOWNLOAD_URL:
                resp = _response(200)
                resp.content = b"Fecha\n2026-06-11\n"
                return resp
            return _response(200, {})

        with TemporaryDirectory() as tmpdir:
            data_dir = Path(tmpdir)
            (data_dir / "ENDURANCE_HRV_sleep.csv").write_text("old\n", encoding="utf-8")

            with patch.dict("os.environ", env, clear=False), \
                    patch.object(backup_dropbox, "DATA_DIR", data_dir), \
                    patch.object(backup_dropbox.requests, "post", side_effect=fake_post):
                result = backup_dropbox.restore_backup()

            self.assertEqual(result["status"], "ok")
            self.assertEqual(len(result["restored"]), 2)
            self.assertIn("ENDURANCE_HRV_sleep.csv", result["backed_up"])
            self.assertEqual(result["source_folder"], "/hrv_backups")
            self.assertEqual(
                (data_dir / "ENDURANCE_HRV_sleep.csv").read_text(encoding="utf-8"),
                "Fecha\n2026-06-11\n",
            )
            backup_dir = data_dir / "backup" / "pre_restore"
            self.assertTrue((backup_dir / "ENDURANCE_HRV_sleep.csv").exists())
            self.assertEqual(
                (backup_dir / "ENDURANCE_HRV_sleep.csv").read_text(encoding="utf-8"),
                "old\n",
            )

    def test_restore_recreates_ai_brief_history_subdirectories(self):
        env = {"DROPBOX_ACCESS_TOKEN": "tok", "HRV_BACKUP_DROPBOX_PATH": "/hrv_backups"}
        file_entries = {
            "entries": [
                {
                    ".tag": "file",
                    "name": "ENDURANCE_HRV_ai_daily_brief_2026-07-10.json",
                    "path_display": "/hrv_backups/ai_briefs/daily/ENDURANCE_HRV_ai_daily_brief_2026-07-10.json",
                },
            ]
        }

        def fake_post(url, **kwargs):
            if url == backup_dropbox._LIST_FOLDER_URL:
                self.assertTrue(kwargs["json"]["recursive"])
                return _response(200, file_entries)
            if url == backup_dropbox._DOWNLOAD_URL:
                resp = _response(200)
                resp.content = b'{"summary":"ok"}'
                return resp
            return _response(200, {})

        with TemporaryDirectory() as tmpdir:
            data_dir = Path(tmpdir)

            with patch.dict("os.environ", env, clear=False), \
                    patch.object(backup_dropbox, "DATA_DIR", data_dir), \
                    patch.object(backup_dropbox.requests, "post", side_effect=fake_post):
                result = backup_dropbox.restore_backup()

            restored_path = data_dir / "ai_briefs" / "daily" / "ENDURANCE_HRV_ai_daily_brief_2026-07-10.json"
            self.assertEqual(result["status"], "ok")
            self.assertEqual(result["restored"], ["ai_briefs/daily/ENDURANCE_HRV_ai_daily_brief_2026-07-10.json"])
            self.assertTrue(restored_path.exists())
            self.assertEqual(restored_path.read_text(encoding="utf-8"), '{"summary":"ok"}')

    def test_restore_lists_recursive_backup_with_pagination(self):
        env = {"DROPBOX_ACCESS_TOKEN": "tok", "HRV_BACKUP_DROPBOX_PATH": "/hrv_backups"}
        first_page = {
            "entries": [
                {
                    ".tag": "file",
                    "name": "ENDURANCE_HRV_master_FINAL.csv",
                    "path_display": "/hrv_backups/ENDURANCE_HRV_master_FINAL.csv",
                },
            ],
            "has_more": True,
            "cursor": "cursor-1",
        }
        second_page = {
            "entries": [
                {
                    ".tag": "file",
                    "name": "ENDURANCE_HRV_ai_ssm_brief_2026-07-10.json",
                    "path_display": "/hrv_backups/ai_briefs/ssm/ENDURANCE_HRV_ai_ssm_brief_2026-07-10.json",
                },
            ],
            "has_more": False,
        }

        def fake_post(url, **kwargs):
            if url == backup_dropbox._LIST_FOLDER_URL:
                self.assertEqual(kwargs["json"], {"path": "/hrv_backups", "recursive": True})
                return _response(200, first_page)
            if url == backup_dropbox._LIST_FOLDER_CONTINUE_URL:
                self.assertEqual(kwargs["json"], {"cursor": "cursor-1"})
                return _response(200, second_page)
            if url == backup_dropbox._DOWNLOAD_URL:
                resp = _response(200)
                resp.content = b"payload"
                return resp
            return _response(200, {})

        with TemporaryDirectory() as tmpdir:
            data_dir = Path(tmpdir)
            with patch.dict("os.environ", env, clear=False), \
                    patch.object(backup_dropbox, "DATA_DIR", data_dir), \
                    patch.object(backup_dropbox.requests, "post", side_effect=fake_post):
                result = backup_dropbox.restore_backup()

            self.assertEqual(result["status"], "ok")
            self.assertEqual(
                result["restored"],
                [
                    "ENDURANCE_HRV_master_FINAL.csv",
                    "ai_briefs/ssm/ENDURANCE_HRV_ai_ssm_brief_2026-07-10.json",
                ],
            )

    def test_restore_without_credentials_raises(self):
        env = {"DROPBOX_ACCESS_TOKEN": "", "DROPBOX_REFRESH_TOKEN": ""}
        with patch.dict("os.environ", env, clear=False):
            with self.assertRaises(RuntimeError):
                backup_dropbox.restore_backup()

    def test_restore_with_no_backups_raises(self):
        env = {"DROPBOX_ACCESS_TOKEN": "tok"}

        def fake_post(url, **kwargs):
            return _response(200, {"entries": []})

        with patch.dict("os.environ", env, clear=False), \
                patch.object(backup_dropbox.requests, "post", side_effect=fake_post):
            with self.assertRaises(FileNotFoundError):
                backup_dropbox.restore_backup()

    def test_restore_partial_download_failure(self):
        env = {"DROPBOX_ACCESS_TOKEN": "tok", "HRV_BACKUP_DROPBOX_PATH": "/hrv_backups"}
        file_entries = {
            "entries": [
                {".tag": "file", "name": "ENDURANCE_HRV_sleep.csv"},
                {".tag": "file", "name": "ENDURANCE_HRV_master_FINAL.csv"},
            ]
        }
        call_count = {"download": 0}

        def fake_post(url, **kwargs):
            if url == backup_dropbox._LIST_FOLDER_URL:
                return _response(200, file_entries)
            if url == backup_dropbox._DOWNLOAD_URL:
                call_count["download"] += 1
                if call_count["download"] == 1:
                    resp = _response(200)
                    resp.content = b"ok\n"
                    return resp
                return _response(500)
            return _response(200, {})

        with TemporaryDirectory() as tmpdir:
            data_dir = Path(tmpdir)
            with patch.dict("os.environ", env, clear=False), \
                    patch.object(backup_dropbox, "DATA_DIR", data_dir), \
                    patch.object(backup_dropbox.requests, "post", side_effect=fake_post):
                result = backup_dropbox.restore_backup()

        self.assertEqual(result["status"], "partial")
        self.assertEqual(len(result["restored"]), 1)
        self.assertEqual(len(result["failed"]), 1)


class AutoRestoreIfEmptyContractTests(unittest.TestCase):
    def test_auto_restore_skips_when_core_has_rows(self):
        env = {"HRV_AUTO_RESTORE_ON_EMPTY_DATA": "1"}

        with TemporaryDirectory() as tmpdir:
            data_dir = Path(tmpdir)
            (data_dir / "ENDURANCE_HRV_master_CORE.csv").write_text("Fecha\n2026-06-11\n", encoding="utf-8")

            with patch.dict("os.environ", env, clear=False), \
                    patch.object(backup_dropbox, "DATA_DIR", data_dir), \
                    patch.object(backup_dropbox, "restore_backup") as restore_mock:
                result = backup_dropbox.auto_restore_if_empty()

        self.assertEqual(result["status"], "skipped")
        self.assertFalse(result["data_empty"])
        restore_mock.assert_not_called()

    def test_data_dir_is_empty_treats_unreadable_core_as_empty(self):
        with patch.object(backup_dropbox, "_core_row_count", return_value=None):
            self.assertTrue(backup_dropbox.data_dir_is_empty(Path("/tmp/ignored")))

    def test_core_row_count_returns_none_on_decode_error(self):
        with TemporaryDirectory() as tmpdir:
            data_dir = Path(tmpdir)
            (data_dir / "ENDURANCE_HRV_master_CORE.csv").write_bytes(b"\xff\xfe\x00")

            self.assertIsNone(backup_dropbox._core_row_count(data_dir))

    def test_auto_restore_restores_when_core_missing(self):
        env = {"HRV_AUTO_RESTORE_ON_EMPTY_DATA": "1"}
        restore_result = {
            "status": "ok",
            "source_folder": "/hrv_backups",
            "restored": ["ENDURANCE_HRV_master_CORE.csv"],
            "failed": [],
            "backed_up": [],
            "backup_dir": None,
        }

        with TemporaryDirectory() as tmpdir:
            data_dir = Path(tmpdir)

            with patch.dict("os.environ", env, clear=False), \
                    patch.object(backup_dropbox, "DATA_DIR", data_dir), \
                    patch.object(backup_dropbox, "_core_row_count", side_effect=[0, 1]), \
                    patch.object(backup_dropbox, "restore_backup", return_value=dict(restore_result)) as restore_mock:
                result = backup_dropbox.auto_restore_if_empty()

        self.assertEqual(result["status"], "restored")
        self.assertFalse(result["data_empty"])
        self.assertEqual(result["source_folder"], "/hrv_backups")
        restore_mock.assert_called_once()

    def test_auto_restore_restores_when_core_is_unreadable(self):
        env = {"HRV_AUTO_RESTORE_ON_EMPTY_DATA": "1"}
        restore_result = {
            "status": "ok",
            "source_folder": "/hrv_backups",
            "restored": ["ENDURANCE_HRV_master_CORE.csv"],
            "failed": [],
            "backed_up": [],
            "backup_dir": None,
        }

        with TemporaryDirectory() as tmpdir:
            data_dir = Path(tmpdir)
            core_path = data_dir / "ENDURANCE_HRV_master_CORE.csv"
            core_path.write_text("corrupt", encoding="utf-8")

            with patch.dict("os.environ", env, clear=False), \
                    patch.object(backup_dropbox, "DATA_DIR", data_dir), \
                    patch.object(backup_dropbox, "_core_row_count", side_effect=[None, 1]), \
                    patch.object(backup_dropbox, "restore_backup", return_value=dict(restore_result)) as restore_mock:
                result = backup_dropbox.auto_restore_if_empty()

        self.assertEqual(result["status"], "restored")
        self.assertFalse(result["data_empty"])
        restore_mock.assert_called_once()

    def test_auto_restore_blocks_on_partial_restore(self):
        env = {"HRV_AUTO_RESTORE_ON_EMPTY_DATA": "1"}
        partial_result = {
            "status": "partial",
            "source_folder": "/hrv_backups",
            "restored": ["ENDURANCE_HRV_master_CORE.csv"],
            "failed": ["ENDURANCE_HRV_sleep.csv"],
        }

        with TemporaryDirectory() as tmpdir:
            data_dir = Path(tmpdir)

            with patch.dict("os.environ", env, clear=False), \
                    patch.object(backup_dropbox, "DATA_DIR", data_dir), \
                    patch.object(backup_dropbox, "restore_backup", return_value=dict(partial_result)):
                with self.assertRaises(RuntimeError):
                    backup_dropbox.auto_restore_if_empty()

    def test_auto_restore_blocks_when_restore_does_not_make_core_usable(self):
        env = {"HRV_AUTO_RESTORE_ON_EMPTY_DATA": "1"}
        restore_result = {
            "status": "ok",
            "source_folder": "/hrv_backups",
            "restored": ["ENDURANCE_HRV_master_CORE.csv"],
            "failed": [],
            "backed_up": [],
            "backup_dir": None,
        }

        with TemporaryDirectory() as tmpdir:
            data_dir = Path(tmpdir)

            with patch.dict("os.environ", env, clear=False), \
                    patch.object(backup_dropbox, "DATA_DIR", data_dir), \
                    patch.object(backup_dropbox, "_core_row_count", side_effect=[0, 0]), \
                    patch.object(backup_dropbox, "restore_backup", return_value=dict(restore_result)):
                with self.assertRaises(RuntimeError):
                    backup_dropbox.auto_restore_if_empty()


if __name__ == "__main__":
    unittest.main()
