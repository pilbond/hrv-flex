import unittest
from unittest.mock import patch

import web_ui


class WebUiOauthCallbackSecurityTests(unittest.TestCase):
    def test_error_params_are_html_escaped(self):
        with web_ui.app.test_client() as client:
            response = client.get(
                "/auth/callback",
                query_string={
                    "error": "<script>alert(1)</script>",
                    "error_description": "<img src=x onerror=alert(2)>",
                },
            )

        self.assertEqual(response.status_code, 400)
        html = response.get_data(as_text=True)
        self.assertNotIn("<script>alert(1)</script>", html)
        self.assertNotIn("<img src=x", html)
        self.assertIn("&lt;script&gt;", html)

    def test_callback_rejects_missing_or_unknown_state(self):
        with web_ui.app.test_client() as client:
            no_state = client.get("/auth/callback", query_string={"code": "abc"})
            bad_state = client.get(
                "/auth/callback", query_string={"code": "abc", "state": "forged"}
            )

        self.assertEqual(no_state.status_code, 400)
        self.assertIn("Estado OAuth", no_state.get_data(as_text=True))
        self.assertEqual(bad_state.status_code, 400)
        self.assertIn("Estado OAuth", bad_state.get_data(as_text=True))

    def test_callback_accepts_issued_state_once(self):
        state = web_ui._issue_oauth_state()
        fake_token = {"access_token": "", "x_user_id": None}

        with patch.object(web_ui, "exchange_code_for_token", return_value=dict(fake_token)), \
                patch.object(web_ui, "save_json_atomic") as save_mock, \
                patch.dict("os.environ", {"POLAR_CLIENT_ID": "cid", "POLAR_CLIENT_SECRET": "sec"}):
            with web_ui.app.test_client() as client:
                first = client.get(
                    "/auth/callback", query_string={"code": "abc", "state": state}
                )
                replay = client.get(
                    "/auth/callback", query_string={"code": "abc", "state": state}
                )

        self.assertEqual(first.status_code, 200)
        save_mock.assert_called_once()
        # El state es de un solo uso: el replay debe rechazarse.
        self.assertEqual(replay.status_code, 400)
        self.assertIn("Estado OAuth", replay.get_data(as_text=True))


class WebUiApiKeyTests(unittest.TestCase):
    def test_api_open_when_key_not_configured(self):
        with patch.object(web_ui, "UI_KEY", ""):
            with web_ui.app.test_client() as client:
                response = client.get("/api/status")
        self.assertEqual(response.status_code, 200)

    def test_api_requires_key_when_configured(self):
        with patch.object(web_ui, "UI_KEY", "secreto"):
            with web_ui.app.test_client() as client:
                denied = client.get("/api/status")
                wrong = client.get("/api/status", headers={"X-HRV-KEY": "otra"})
                via_header = client.get("/api/status", headers={"X-HRV-KEY": "secreto"})
                via_query = client.get("/api/status", query_string={"key": "secreto"})
                index_open = client.get("/")
                health_open = client.get("/health")

        self.assertEqual(denied.status_code, 401)
        self.assertEqual(wrong.status_code, 401)
        self.assertEqual(via_header.status_code, 200)
        self.assertEqual(via_query.status_code, 200)
        self.assertEqual(index_open.status_code, 200)
        self.assertEqual(health_open.status_code, 200)

    def test_mutable_endpoint_denied_without_key(self):
        with patch.object(web_ui, "UI_KEY", "secreto"):
            with web_ui.app.test_client() as client:
                response = client.post("/api/sync")
        self.assertEqual(response.status_code, 401)


class WebUiHealthStalenessTests(unittest.TestCase):
    def _write_final(self, data_dir, fecha):
        final_path = data_dir / "ENDURANCE_HRV_master_FINAL.csv"
        final_path.write_text(f"Fecha,RMSSD_stable\n{fecha},45.0\n", encoding="utf-8")

    def test_health_without_strict_always_200(self):
        from pathlib import Path
        from tempfile import TemporaryDirectory

        with TemporaryDirectory() as tmpdir:
            with patch.object(web_ui, "DATA_DIR", Path(tmpdir)):
                with web_ui.app.test_client() as client:
                    response = client.get("/health")
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.get_json()["days_stale"])

    def test_health_strict_fresh_final_is_200(self):
        from datetime import date
        from pathlib import Path
        from tempfile import TemporaryDirectory

        with TemporaryDirectory() as tmpdir:
            data_dir = Path(tmpdir)
            self._write_final(data_dir, date.today().isoformat())
            with patch.object(web_ui, "DATA_DIR", data_dir):
                with web_ui.app.test_client() as client:
                    response = client.get("/health", query_string={"strict": "1"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["days_stale"], 0)

    def test_health_strict_stale_or_missing_final_is_503(self):
        from datetime import date, timedelta
        from pathlib import Path
        from tempfile import TemporaryDirectory

        with TemporaryDirectory() as tmpdir:
            data_dir = Path(tmpdir)
            old = (date.today() - timedelta(days=10)).isoformat()
            self._write_final(data_dir, old)
            with patch.object(web_ui, "DATA_DIR", data_dir):
                with web_ui.app.test_client() as client:
                    stale = client.get("/health", query_string={"strict": "1"})

        with TemporaryDirectory() as tmpdir:
            with patch.object(web_ui, "DATA_DIR", Path(tmpdir)):
                with web_ui.app.test_client() as client:
                    missing = client.get("/health", query_string={"strict": "1"})

        self.assertEqual(stale.status_code, 503)
        self.assertEqual(stale.get_json()["status"], "stale")
        self.assertEqual(missing.status_code, 503)


class WebUiRestoreBackupTests(unittest.TestCase):
    def test_restore_backup_requires_ui_key(self):
        with patch.dict("os.environ", {"HRV_UI_KEY": "s3cret"}, clear=False):
            import importlib
            importlib.reload(web_ui)
            with web_ui.app.test_client() as client:
                denied = client.post("/api/restore-backup")
                allowed = client.post(
                    "/api/restore-backup",
                    headers={"X-HRV-KEY": "s3cret"},
                )
        importlib.reload(web_ui)
        self.assertEqual(denied.status_code, 401)
        self.assertIn(allowed.status_code, (200, 400))

    def test_restore_backup_returns_result(self):
        fake_result = {
            "status": "ok",
            "source_folder": "/hrv_backups/2026-06-11",
            "restored": ["ENDURANCE_HRV_sleep.csv"],
            "failed": [],
            "backed_up": [],
            "backup_dir": None,
        }
        with patch("hrv_app.backup_dropbox.restore_backup", return_value=fake_result):
            with web_ui.app.test_client() as client:
                resp = client.post("/api/restore-backup")
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data["success"])
        self.assertEqual(data["restored"], ["ENDURANCE_HRV_sleep.csv"])

    def test_restore_backup_error_returns_400(self):
        with patch("hrv_app.backup_dropbox.restore_backup", side_effect=RuntimeError("no creds")):
            with web_ui.app.test_client() as client:
                resp = client.post("/api/restore-backup")
        self.assertEqual(resp.status_code, 400)
        data = resp.get_json()
        self.assertFalse(data["success"])
        self.assertIn("no creds", data["error"])


if __name__ == "__main__":
    unittest.main()
