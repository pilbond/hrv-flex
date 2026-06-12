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

    def test_uploads_canonical_files_and_rotates_old_folders(self):
        env = {
            "HRV_BACKUP_DROPBOX_ENABLED": "1",
            "DROPBOX_ACCESS_TOKEN": "tok",
            "DROPBOX_REFRESH_TOKEN": "",
            "HRV_BACKUP_DROPBOX_PATH": "/hrv_backups",
            "HRV_BACKUP_KEEP": "2",
        }
        old_folders = {
            "entries": [
                {".tag": "folder", "name": "2026-01-01"},
                {".tag": "folder", "name": "2026-01-02"},
                {".tag": "folder", "name": "2026-01-03"},
                {".tag": "folder", "name": "no_es_fecha"},
            ]
        }

        def fake_post(url, **kwargs):
            if url == backup_dropbox._LIST_FOLDER_URL:
                return _response(200, old_folders)
            return _response(200, {})

        with TemporaryDirectory() as tmpdir:
            data_dir = Path(tmpdir)
            (data_dir / "ENDURANCE_HRV_master_FINAL.csv").write_text("Fecha\n2026-06-12\n", encoding="utf-8")
            (data_dir / "ENDURANCE_HRV_weekly_coach.json").write_text("{}", encoding="utf-8")
            (data_dir / "otro_archivo.csv").write_text("x\n", encoding="utf-8")

            with patch.dict("os.environ", env, clear=False), \
                    patch.object(backup_dropbox, "DATA_DIR", data_dir), \
                    patch.object(backup_dropbox.requests, "post", side_effect=fake_post) as post_mock:
                result = backup_dropbox.run_backup()

        self.assertEqual(result["status"], "ok")
        # Solo los 2 canónicos ENDURANCE_HRV_*, no "otro_archivo.csv".
        self.assertEqual(result["uploaded"], 2)
        # keep=2 sobre 3 carpetas-fecha → borra la más antigua (la no-fecha se ignora).
        self.assertEqual(result["deleted_old"], 1)

        delete_calls = [
            c for c in post_mock.call_args_list if c.args[0] == backup_dropbox._DELETE_URL
        ]
        self.assertEqual(len(delete_calls), 1)
        self.assertEqual(delete_calls[0].kwargs["json"]["path"], "/hrv_backups/2026-01-01")

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

    def test_unexpected_exception_is_swallowed(self):
        env = {"HRV_BACKUP_DROPBOX_ENABLED": "1", "DROPBOX_ACCESS_TOKEN": "tok"}
        with patch.dict("os.environ", env, clear=False), \
                patch.object(backup_dropbox, "_canonical_files", side_effect=RuntimeError("boom")):
            result = backup_dropbox.run_backup()
        self.assertEqual(result["status"], "error")


class RestoreBackupContractTests(unittest.TestCase):
    def test_restore_downloads_files_atomically_to_data_dir(self):
        env = {"DROPBOX_ACCESS_TOKEN": "tok", "HRV_BACKUP_DROPBOX_PATH": "/hrv_backups"}
        folder_entries = {
            "entries": [
                {".tag": "folder", "name": "2026-06-10"},
                {".tag": "folder", "name": "2026-06-11"},
            ]
        }
        file_entries = {
            "entries": [
                {".tag": "file", "name": "ENDURANCE_HRV_sleep.csv"},
                {".tag": "file", "name": "ENDURANCE_HRV_master_FINAL.csv"},
            ]
        }

        def fake_post(url, **kwargs):
            if url == backup_dropbox._LIST_FOLDER_URL:
                json_body = kwargs.get("json", {})
                if json_body.get("path", "").endswith("2026-06-11"):
                    return _response(200, file_entries)
                return _response(200, folder_entries)
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
            self.assertEqual(result["source_folder"], "/hrv_backups/2026-06-11")
            self.assertEqual(
                (data_dir / "ENDURANCE_HRV_sleep.csv").read_text(encoding="utf-8"),
                "Fecha\n2026-06-11\n",
            )
            backup_dir = data_dir / "backup" / "pre_restore_2026-06-11"
            self.assertTrue((backup_dir / "ENDURANCE_HRV_sleep.csv").exists())
            self.assertEqual(
                (backup_dir / "ENDURANCE_HRV_sleep.csv").read_text(encoding="utf-8"),
                "old\n",
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
        folder_entries = {"entries": [{".tag": "folder", "name": "2026-06-11"}]}
        file_entries = {
            "entries": [
                {".tag": "file", "name": "ENDURANCE_HRV_sleep.csv"},
                {".tag": "file", "name": "ENDURANCE_HRV_master_FINAL.csv"},
            ]
        }
        call_count = {"download": 0}

        def fake_post(url, **kwargs):
            if url == backup_dropbox._LIST_FOLDER_URL:
                json_body = kwargs.get("json", {})
                if json_body.get("path", "").endswith("2026-06-11"):
                    return _response(200, file_entries)
                return _response(200, folder_entries)
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


if __name__ == "__main__":
    unittest.main()
