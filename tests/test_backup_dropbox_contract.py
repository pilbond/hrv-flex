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
    def _canonical_entries(self):
        return [{".tag": "file", "name": name} for name in backup_dropbox._RESTORE_REQUIRED_CSVS]

    def _canonical_content(self, name):
        if name == "ENDURANCE_HRV_master_CORE.csv":
            return b"Fecha,Calidad,HR_stable,RMSSD_stable,lnRMSSD\n2026-06-11,OK,52,42,3.74\n"
        return b"Fecha,valor\n2026-06-11,1\n"

    def test_restore_rejects_missing_required_files_without_touching_data_dir(self):
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
                with self.assertRaisesRegex(RuntimeError, "faltan"):
                    backup_dropbox.restore_backup()
            self.assertEqual(
                (data_dir / "ENDURANCE_HRV_sleep.csv").read_text(encoding="utf-8"),
                "old\n",
            )

    def test_restore_validates_then_publishes_complete_set(self):
        env = {"DROPBOX_ACCESS_TOKEN": "tok", "HRV_BACKUP_DROPBOX_PATH": "/hrv_backups"}
        file_entries = {"entries": self._canonical_entries()}

        def fake_post(url, **kwargs):
            if url == backup_dropbox._LIST_FOLDER_URL:
                return _response(200, file_entries)
            if url == backup_dropbox._DOWNLOAD_URL:
                name = __import__("json").loads(kwargs["headers"]["Dropbox-API-Arg"])["path"].removeprefix("/hrv_backups/")
                resp = _response(200)
                resp.content = self._canonical_content(name)
                return resp
            return _response(200, {})

        with TemporaryDirectory() as tmpdir:
            data_dir = Path(tmpdir) / "data"
            data_dir.mkdir()
            (data_dir / "ENDURANCE_HRV_sleep.csv").write_text("old\n", encoding="utf-8")
            with patch.dict("os.environ", env, clear=False), \
                    patch.object(backup_dropbox, "DATA_DIR", data_dir), \
                    patch.object(backup_dropbox.requests, "post", side_effect=fake_post), \
                    patch.object(backup_dropbox, "_validate_restore_set", wraps=backup_dropbox._validate_restore_set) as validate_mock:
                result = backup_dropbox.restore_backup()
            self.assertEqual(validate_mock.call_args.args[0].parent, data_dir)
            self.assertFalse(validate_mock.call_args.args[0].exists())
            self.assertEqual(result["status"], "ok")
            self.assertEqual(set(result["restored"]), set(backup_dropbox._RESTORE_REQUIRED_CSVS))
            self.assertIn("ENDURANCE_HRV_sleep.csv", result["backed_up"])
            self.assertEqual((data_dir / "ENDURANCE_HRV_sleep.csv").read_text(encoding="utf-8"),
                             "Fecha,valor\n2026-06-11,1\n")
            self.assertEqual((data_dir / "backup/pre_restore/ENDURANCE_HRV_sleep.csv").read_text(encoding="utf-8"), "old\n")

    def test_restore_rolls_back_files_when_publication_fails(self):
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            target = root / "data"
            staging = root / "staging"
            target.mkdir()
            staging.mkdir()
            names = ["ENDURANCE_HRV_master_CORE.csv", "ENDURANCE_HRV_master_FINAL.csv"]
            for name in names:
                (target / name).write_text(f"old {name}\n", encoding="utf-8")
                (staging / name).write_text(f"new {name}\n", encoding="utf-8")

            import hrv_app.io_utils as io_utils
            original_replace = io_utils._replace_atomic
            calls = {"count": 0}

            def fail_second_replace(src, dst):
                calls["count"] += 1
                if calls["count"] == 2:
                    raise OSError("publication failure")
                return original_replace(src, dst)

            with patch.object(io_utils, "_replace_atomic", side_effect=fail_second_replace):
                with self.assertRaisesRegex(RuntimeError, "Falló la publicación"):
                    backup_dropbox._publish_restore_set(staging, target, names)
            for name in names:
                self.assertEqual((target / name).read_text(encoding="utf-8"), f"old {name}\n")

    def test_restore_rejects_invalid_csv_without_touching_existing_files(self):
        env = {"DROPBOX_ACCESS_TOKEN": "tok", "HRV_BACKUP_DROPBOX_PATH": "/hrv_backups"}
        entries = {"entries": self._canonical_entries()}

        def fake_post(url, **kwargs):
            if url == backup_dropbox._LIST_FOLDER_URL:
                return _response(200, entries)
            if url == backup_dropbox._DOWNLOAD_URL:
                path = __import__("json").loads(kwargs["headers"]["Dropbox-API-Arg"])["path"]
                name = path.removeprefix("/hrv_backups/")
                resp = _response(200)
                resp.content = b'"unterminated' if name == "ENDURANCE_HRV_master_FINAL.csv" else self._canonical_content(name)
                return resp
            return _response(200, {})

        with TemporaryDirectory() as tmpdir:
            data_dir = Path(tmpdir) / "data"
            data_dir.mkdir()
            previous = data_dir / "ENDURANCE_HRV_master_CORE.csv"
            previous.write_text("previous core\n", encoding="utf-8")
            with patch.dict("os.environ", env, clear=False), \
                    patch.object(backup_dropbox, "DATA_DIR", data_dir), \
                    patch.object(backup_dropbox.requests, "post", side_effect=fake_post):
                with self.assertRaisesRegex(RuntimeError, "ilegible o inválido"):
                    backup_dropbox.restore_backup()
            self.assertEqual(previous.read_text(encoding="utf-8"), "previous core\n")
            self.assertFalse((data_dir / "ENDURANCE_HRV_master_FINAL.csv").exists())

    def test_restore_rejects_core_without_required_columns_or_valid_date(self):
        env = {"DROPBOX_ACCESS_TOKEN": "tok", "HRV_BACKUP_DROPBOX_PATH": "/hrv_backups"}
        invalid_cores = (
            b"dato\nbasura\n",
            b"Fecha,Calidad,HR_stable,RMSSD_stable,lnRMSSD\nnot-a-date,OK,52,42,3.74\n",
        )
        for invalid_core in invalid_cores:
            with self.subTest(core=invalid_core), TemporaryDirectory() as tmpdir:
                data_dir = Path(tmpdir) / "data"
                data_dir.mkdir()
                previous = data_dir / "ENDURANCE_HRV_master_CORE.csv"
                previous.write_bytes(self._canonical_content(previous.name))

                def fake_post(url, **kwargs):
                    if url == backup_dropbox._LIST_FOLDER_URL:
                        return _response(200, {"entries": self._canonical_entries()})
                    if url == backup_dropbox._DOWNLOAD_URL:
                        name = __import__("json").loads(kwargs["headers"]["Dropbox-API-Arg"])["path"].removeprefix("/hrv_backups/")
                        resp = _response(200)
                        resp.content = invalid_core if name == previous.name else self._canonical_content(name)
                        return resp
                    return _response(200, {})

                with patch.dict("os.environ", env, clear=False), \
                        patch.object(backup_dropbox, "DATA_DIR", data_dir), \
                        patch.object(backup_dropbox.requests, "post", side_effect=fake_post):
                    with self.assertRaisesRegex(RuntimeError, "CORE"):
                        backup_dropbox.restore_backup()
                self.assertEqual(previous.read_bytes(), self._canonical_content(previous.name))
                self.assertFalse((data_dir / "ENDURANCE_HRV_master_FINAL.csv").exists())

    def test_restore_validation_tolerates_blank_lines_and_earlier_invalid_core_date(self):
        with TemporaryDirectory() as tmpdir:
            directory = Path(tmpdir)
            for name in backup_dropbox._RESTORE_REQUIRED_CSVS:
                content = self._canonical_content(name)
                if name == "ENDURANCE_HRV_master_CORE.csv":
                    content = content.replace(
                        b"2026-06-11,OK,52,42,3.74\n",
                        b"not-a-date,OK,52,42,3.74\n2026-06-11,OK,52,42,3.74\n",
                    )
                (directory / name).write_bytes(content + b"\n")
            backup_dropbox._validate_restore_set(directory)

    def test_short_row_in_derived_csv_does_not_block_recovery(self):
        with TemporaryDirectory() as tmpdir:
            directory = Path(tmpdir)
            for name in backup_dropbox._RESTORE_REQUIRED_CSVS:
                (directory / name).write_bytes(self._canonical_content(name))
            (directory / "ENDURANCE_HRV_master_FINAL.csv").write_bytes(
                b"Fecha,valor\n2026-06-11\n"
            )
            backup_dropbox._validate_restore_set(directory)
            with patch.object(backup_dropbox, "restore_backup") as restore_mock:
                result = backup_dropbox.auto_restore_if_empty(data_dir=directory, enabled=True)
            self.assertEqual(result["status"], "skipped")
            restore_mock.assert_not_called()

    def test_restore_recreates_ai_brief_history_subdirectories(self):
        env = {"DROPBOX_ACCESS_TOKEN": "tok", "HRV_BACKUP_DROPBOX_PATH": "/hrv_backups"}
        file_entries = {
            "entries": [
                *self._canonical_entries(),
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
                path = __import__("json").loads(kwargs["headers"]["Dropbox-API-Arg"])["path"]
                if "ai_daily" in path:
                    resp.content = b'{"summary":"ok"}'
                else:
                    name = next(n for n in backup_dropbox._RESTORE_REQUIRED_CSVS if n in path)
                    resp.content = self._canonical_content(name)
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
            self.assertIn("ai_briefs/daily/ENDURANCE_HRV_ai_daily_brief_2026-07-10.json", result["restored"])
            self.assertTrue(restored_path.exists())
            self.assertEqual(restored_path.read_text(encoding="utf-8"), '{"summary":"ok"}')

    def test_restore_lists_recursive_backup_with_pagination(self):
        env = {"DROPBOX_ACCESS_TOKEN": "tok", "HRV_BACKUP_DROPBOX_PATH": "/hrv_backups"}
        first_page = {
            "entries": [
                *self._canonical_entries(),
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
                arg = __import__("json").loads(kwargs["headers"]["Dropbox-API-Arg"])["path"]
                name = next((n for n in backup_dropbox._RESTORE_REQUIRED_CSVS if n in arg), None)
                resp.content = self._canonical_content(name) if name else b"payload"
                return resp
            return _response(200, {})

        with TemporaryDirectory() as tmpdir:
            data_dir = Path(tmpdir)
            with patch.dict("os.environ", env, clear=False), \
                    patch.object(backup_dropbox, "DATA_DIR", data_dir), \
                    patch.object(backup_dropbox.requests, "post", side_effect=fake_post):
                result = backup_dropbox.restore_backup()

            self.assertEqual(result["status"], "ok")
            self.assertIn("ENDURANCE_HRV_master_FINAL.csv", result["restored"])
            self.assertIn("ai_briefs/ssm/ENDURANCE_HRV_ai_ssm_brief_2026-07-10.json", result["restored"])

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
                with self.assertRaisesRegex(RuntimeError, "Descarga incompleta"):
                    backup_dropbox.restore_backup()
            self.assertFalse((data_dir / "ENDURANCE_HRV_sleep.csv").exists())


class AutoRestoreIfEmptyContractTests(unittest.TestCase):
    def test_auto_restore_skips_when_core_has_rows(self):
        env = {"HRV_AUTO_RESTORE_ON_EMPTY_DATA": "1"}

        with TemporaryDirectory() as tmpdir:
            data_dir = Path(tmpdir)
            for name in backup_dropbox._RESTORE_REQUIRED_CSVS:
                content = ("Fecha,Calidad,HR_stable,RMSSD_stable,lnRMSSD\n2026-06-11,OK,52,42,3.74\n"
                           if name == "ENDURANCE_HRV_master_CORE.csv" else "Fecha,Valor\n2026-06-11,1\n")
                (data_dir / name).write_text(content, encoding="utf-8")

            with patch.dict("os.environ", env, clear=False), \
                    patch.object(backup_dropbox, "DATA_DIR", data_dir), \
                    patch.object(backup_dropbox, "restore_backup") as restore_mock:
                result = backup_dropbox.auto_restore_if_empty()

        self.assertEqual(result["status"], "skipped")
        self.assertFalse(result["data_empty"])
        restore_mock.assert_not_called()

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
            "backed_up": [],
            "backup_dir": None,
        }

        with TemporaryDirectory() as tmpdir:
            data_dir = Path(tmpdir)

            with patch.dict("os.environ", env, clear=False), \
                    patch.object(backup_dropbox, "DATA_DIR", data_dir), \
                    patch.object(backup_dropbox, "_core_row_count", side_effect=[0, 1]), \
                    patch.object(backup_dropbox, "_validate_restore_set", side_effect=[RuntimeError("missing"), None]), \
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
                    patch.object(backup_dropbox, "_validate_restore_set", side_effect=[RuntimeError("missing"), None]), \
                    patch.object(backup_dropbox, "restore_backup", return_value=dict(restore_result)) as restore_mock:
                result = backup_dropbox.auto_restore_if_empty()

        self.assertEqual(result["status"], "restored")
        self.assertFalse(result["data_empty"])
        restore_mock.assert_called_once()

    def test_auto_restore_blocks_on_restore_failure(self):
        env = {"HRV_AUTO_RESTORE_ON_EMPTY_DATA": "1"}
        with TemporaryDirectory() as tmpdir:
            data_dir = Path(tmpdir)

            with patch.dict("os.environ", env, clear=False), \
                    patch.object(backup_dropbox, "DATA_DIR", data_dir), \
                    patch.object(backup_dropbox, "restore_backup", side_effect=RuntimeError("Descarga incompleta")):
                with self.assertRaisesRegex(RuntimeError, "Auto-restore falló: Descarga incompleta"):
                    backup_dropbox.auto_restore_if_empty()

    def test_auto_restore_repairs_missing_canonical_even_when_core_has_rows(self):
        env = {"HRV_AUTO_RESTORE_ON_EMPTY_DATA": "1"}
        restore_result = {"status": "ok", "restored": list(backup_dropbox._RESTORE_REQUIRED_CSVS)}
        with TemporaryDirectory() as tmpdir:
            data_dir = Path(tmpdir)
            with patch.dict("os.environ", env, clear=False), \
                    patch.object(backup_dropbox, "DATA_DIR", data_dir), \
                    patch.object(backup_dropbox, "_core_row_count", side_effect=[1, 1]), \
                    patch.object(backup_dropbox, "_validate_restore_set", side_effect=[RuntimeError("missing"), None]), \
                    patch.object(backup_dropbox, "restore_backup", return_value=restore_result) as restore_mock:
                result = backup_dropbox.auto_restore_if_empty()
        self.assertEqual(result["status"], "restored")
        restore_mock.assert_called_once()

    def test_auto_restore_blocks_when_restore_does_not_make_core_usable(self):
        env = {"HRV_AUTO_RESTORE_ON_EMPTY_DATA": "1"}
        restore_result = {
            "status": "ok",
            "source_folder": "/hrv_backups",
            "restored": ["ENDURANCE_HRV_master_CORE.csv"],
            "backed_up": [],
            "backup_dir": None,
        }

        with TemporaryDirectory() as tmpdir:
            data_dir = Path(tmpdir)

            with patch.dict("os.environ", env, clear=False), \
                    patch.object(backup_dropbox, "DATA_DIR", data_dir), \
                    patch.object(backup_dropbox, "_core_row_count", side_effect=[0, 0]), \
                    patch.object(backup_dropbox, "restore_backup", return_value=dict(restore_result)):
                with self.assertRaisesRegex(RuntimeError, "Auto-restore no dejó el conjunto obligatorio utilizable"):
                    backup_dropbox.auto_restore_if_empty()


if __name__ == "__main__":
    unittest.main()
