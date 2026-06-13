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


class WebUiOauthV4Tests(unittest.TestCase):
    def test_auth_provider_v4_redirects_to_auth_polar_with_scopes_and_state(self):
        with patch.dict("os.environ", {"POLAR_CLIENT_ID": "cid", "POLAR_CLIENT_SECRET": "sec"}):
            with web_ui.app.test_client() as client:
                response = client.get("/auth", query_string={"provider": "v4"})

        self.assertEqual(response.status_code, 302)
        location = response.headers["Location"]
        self.assertTrue(location.startswith("https://auth.polar.com/oauth/authorize"))
        self.assertIn("sleep%3Aread", location)
        self.assertIn("state=", location)

    def test_auth_default_remains_v3(self):
        with patch.dict("os.environ", {"POLAR_CLIENT_ID": "cid", "POLAR_CLIENT_SECRET": "sec"}):
            with web_ui.app.test_client() as client:
                response = client.get("/auth")

        self.assertEqual(response.status_code, 302)
        self.assertTrue(
            response.headers["Location"].startswith("https://flow.polar.com/oauth2/authorization")
        )

    def test_callback_v4_persists_bundle_without_leaking_refresh_token(self):
        from hrv_app import polar_auth_v4 as auth_v4

        state = web_ui._issue_oauth_state("v4")
        token_json = {"access_token": "at-v4", "refresh_token": "rt-secreto", "expires_in": 43199}
        saved = {}

        def fake_persist(path, tj, scopes):
            saved["path"] = path
            saved["bundle"] = auth_v4.make_bundle(tj, scopes=scopes)
            return saved["bundle"]

        with patch.object(web_ui, "exchange_code_for_token_v4", return_value=dict(token_json)), \
                patch.object(web_ui, "persist_authorized_bundle", side_effect=fake_persist), \
                patch.dict("os.environ", {"POLAR_CLIENT_ID": "cid", "POLAR_CLIENT_SECRET": "sec"}):
            with web_ui.app.test_client() as client:
                response = client.get("/auth/callback", query_string={"code": "abc", "state": state})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(saved["path"], web_ui.TOKEN_PATH_V4)
        self.assertEqual(saved["bundle"]["provider_version"], "v4")
        self.assertEqual(saved["bundle"]["refresh_token"], "rt-secreto")
        self.assertIn("scopes", saved["bundle"])
        # El HTML de respuesta jamás contiene tokens.
        html = response.get_data(as_text=True)
        self.assertNotIn("rt-secreto", html)
        self.assertNotIn("at-v4", html)

    def test_callback_v4_state_is_single_use(self):
        state = web_ui._issue_oauth_state("v4")
        with patch.object(web_ui, "exchange_code_for_token_v4", return_value={"access_token": "at"}), \
                patch.object(web_ui, "persist_authorized_bundle", return_value={"access_token": "at"}), \
                patch.dict("os.environ", {"POLAR_CLIENT_ID": "cid", "POLAR_CLIENT_SECRET": "sec"}):
            with web_ui.app.test_client() as client:
                first = client.get("/auth/callback", query_string={"code": "abc", "state": state})
                replay = client.get("/auth/callback", query_string={"code": "abc", "state": state})

        self.assertEqual(first.status_code, 200)
        self.assertEqual(replay.status_code, 400)

    def test_expired_v4_state_retry_link_preserves_provider(self):
        # Un state v4 caducado no debe reenviar al flujo v3 por defecto.
        state = web_ui._issue_oauth_state("v4")
        with web_ui._oauth_states_lock:
            issued_at, version = web_ui._oauth_states[state]
            web_ui._oauth_states[state] = (issued_at - 9999, version)

        with web_ui.app.test_client() as client:
            response = client.get("/auth/callback", query_string={"code": "abc", "state": state})

        self.assertEqual(response.status_code, 400)
        self.assertIn("/auth?provider=v4", response.get_data(as_text=True))

    def test_unknown_state_retry_mentions_v4_path(self):
        with web_ui.app.test_client() as client:
            response = client.get("/auth/callback", query_string={"code": "abc", "state": "forged"})
        self.assertEqual(response.status_code, 400)
        self.assertIn("/auth?provider=v4", response.get_data(as_text=True))

    def test_api_status_never_contains_refresh_token_in_v4_mode(self):
        import json as _json
        import time as _time
        from pathlib import Path
        from tempfile import TemporaryDirectory

        with TemporaryDirectory() as tmpdir:
            bundle_path = Path(tmpdir) / "polar_tokens_v4.json"
            bundle_path.write_text(_json.dumps({
                "access_token": "at-secreto",
                "refresh_token": "rt-secreto",
                "expires_in": 43199,
                "obtained_at": _time.time(),
                "scopes": "sleep:read",
                "provider_version": "v4",
            }), encoding="utf-8")
            with patch.object(web_ui, "POLAR_API_VERSION", "v4"), \
                    patch.object(web_ui, "TOKEN_PATH_V4", bundle_path):
                with web_ui.app.test_client() as client:
                    response = client.get("/api/status")

        self.assertEqual(response.status_code, 200)
        raw = response.get_data(as_text=True)
        self.assertNotIn("rt-secreto", raw)
        self.assertNotIn("at-secreto", raw)
        diagnostics = response.get_json().get("diagnostics", {})
        self.assertEqual(diagnostics.get("token_reason"), "ok")

    def test_token_diagnostics_v4_refreshable_when_expired_with_refresh_token(self):
        import json as _json
        import time as _time
        from pathlib import Path
        from tempfile import TemporaryDirectory

        with TemporaryDirectory() as tmpdir:
            bundle_path = Path(tmpdir) / "polar_tokens_v4.json"
            bundle_path.write_text(_json.dumps({
                "access_token": "at",
                "refresh_token": "rt",
                "expires_in": 10,
                "obtained_at": _time.time() - 99999,
                "scopes": "sleep:read",
            }), encoding="utf-8")
            with patch.object(web_ui, "POLAR_API_VERSION", "v4"), \
                    patch.object(web_ui, "TOKEN_PATH_V4", bundle_path):
                info = web_ui._token_diagnostics()

        # Expirado con refresh_token != requiere re-auth: se renueva solo.
        self.assertEqual(info["token_reason"], "refreshable")
        self.assertTrue(info["token_expired"])

    def test_token_diagnostics_v4_refreshable_without_access_token(self):
        import json as _json
        import time as _time
        from pathlib import Path
        from tempfile import TemporaryDirectory

        # Bundle "refresh-only" (sin access_token, con refresh_token):
        # get_valid_access_token() lo renueva en el siguiente uso, no exige
        # re-auth como un "missing_access_token".
        with TemporaryDirectory() as tmpdir:
            bundle_path = Path(tmpdir) / "polar_tokens_v4.json"
            bundle_path.write_text(_json.dumps({
                "refresh_token": "rt",
                "obtained_at": _time.time(),
                "scopes": "sleep:read",
            }), encoding="utf-8")
            with patch.object(web_ui, "POLAR_API_VERSION", "v4"), \
                    patch.object(web_ui, "TOKEN_PATH_V4", bundle_path):
                info = web_ui._token_diagnostics()

        self.assertEqual(info["token_reason"], "refreshable")
        self.assertTrue(info["token_expired"])

    def test_token_diagnostics_v4_within_skew_is_not_expired(self):
        import json as _json
        import time as _time
        from pathlib import Path
        from tempfile import TemporaryDirectory

        # needs_refresh se activa también dentro del margen de refresco
        # proactivo (REFRESH_SKEW_SEC=120s), antes de que el token expire
        # de verdad: token_expired debe reflejar la expiración real.
        with TemporaryDirectory() as tmpdir:
            bundle_path = Path(tmpdir) / "polar_tokens_v4.json"
            bundle_path.write_text(_json.dumps({
                "access_token": "at",
                "refresh_token": "rt",
                "expires_in": 43199,
                "obtained_at": _time.time() - (43199 - 60),
                "scopes": "sleep:read",
            }), encoding="utf-8")
            with patch.object(web_ui, "POLAR_API_VERSION", "v4"), \
                    patch.object(web_ui, "TOKEN_PATH_V4", bundle_path):
                info = web_ui._token_diagnostics()

        self.assertEqual(info["token_reason"], "refreshable")
        self.assertFalse(info["token_expired"])

    def test_callback_exception_message_is_html_escaped(self):
        # Un error_description del token endpoint puede contener markup; la
        # página de error no debe insertarlo sin escapar (XSS).
        state = web_ui._issue_oauth_state("v4")
        with patch.object(web_ui, "exchange_code_for_token_v4",
                          side_effect=RuntimeError("<script>alert(1)</script>")):
            with web_ui.app.test_client() as client:
                response = client.get("/auth/callback", query_string={"code": "abc", "state": state})

        self.assertEqual(response.status_code, 500)
        body = response.get_data(as_text=True)
        self.assertNotIn("<script>alert(1)</script>", body)
        self.assertIn("&lt;script&gt;", body)

    def test_token_diagnostics_v4_corrupt_numbers_do_not_raise(self):
        import json as _json
        import time as _time
        from pathlib import Path
        from tempfile import TemporaryDirectory

        # expires_in/obtained_at no numéricos: diagnóstico degradado, no 500.
        with TemporaryDirectory() as tmpdir:
            bundle_path = Path(tmpdir) / "polar_tokens_v4.json"
            bundle_path.write_text(_json.dumps({
                "access_token": "at",
                "refresh_token": "rt",
                "expires_in": "abc",
                "obtained_at": _time.time(),
                "scopes": "sleep:read",
            }), encoding="utf-8")
            with patch.object(web_ui, "POLAR_API_VERSION", "v4"), \
                    patch.object(web_ui, "TOKEN_PATH_V4", bundle_path):
                info = web_ui._token_diagnostics()

        self.assertEqual(info["token_reason"], "refreshable")
        self.assertTrue(info["token_expired"])

    def test_api_status_shadow_mode_exposes_v4_bundle(self):
        import json as _json
        import time as _time
        from pathlib import Path
        from tempfile import TemporaryDirectory

        # En shadow el runtime efectivo sigue siendo v3, pero el bundle v4
        # (autorizado via /auth?provider=v4) debe seguir siendo visible.
        with TemporaryDirectory() as tmpdir:
            bundle_path = Path(tmpdir) / "polar_tokens_v4.json"
            bundle_path.write_text(_json.dumps({
                "access_token": "at-secreto",
                "refresh_token": "rt-secreto",
                "expires_in": 43199,
                "obtained_at": _time.time(),
                "scopes": "sleep:read",
                "provider_version": "v4",
            }), encoding="utf-8")
            with patch.object(web_ui, "POLAR_API_VERSION", "shadow"), \
                    patch.object(web_ui, "TOKEN_PATH_V4", bundle_path):
                with web_ui.app.test_client() as client:
                    response = client.get("/api/status")

        self.assertEqual(response.status_code, 200)
        raw = response.get_data(as_text=True)
        self.assertNotIn("rt-secreto", raw)
        self.assertNotIn("at-secreto", raw)
        diagnostics = response.get_json().get("diagnostics", {})
        self.assertEqual(diagnostics.get("api_version"), "shadow")
        self.assertEqual(diagnostics.get("token_v4", {}).get("token_reason"), "ok")


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
