import contextlib
import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import polar_oauth_local


class PolarOauthLocalContractTests(unittest.TestCase):
    def test_build_auth_url_includes_client_redirect_and_scope(self):
        url = polar_oauth_local.build_auth_url("client-id", "https://example/auth", "scope-a scope-b")
        self.assertIn("client_id=client-id", url)
        self.assertIn("redirect_uri=https%3A%2F%2Fexample%2Fauth", url)
        self.assertIn("scope=scope-a+scope-b", url)

    def test_load_tokens_handles_expiration(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            token_path = Path(tmpdir) / "tokens.json"
            token_path.write_text(
                '{"access_token": "tok", "x_user_id": "uid", "obtained_at": 0, "expires_in": 1}',
                encoding="utf-8",
            )

            with patch.object(polar_oauth_local, "TOKEN_FILE", token_path), patch.object(polar_oauth_local.time, "time", return_value=10):
                self.assertEqual(polar_oauth_local.load_tokens(), (None, None))

    def test_do_oauth_flow_smoke_with_mocks(self):
        fake_result = {"access_token": "tok", "x_user_id": "uid"}

        def fake_start_callback_server(redirect_uri, state_obj, timeout_s=180):
            state_obj.code = "auth-code"

        class FakeThread:
            def __init__(self, target, args, daemon):
                self.target = target
                self.args = args
                self.daemon = daemon

            def start(self):
                self.target(*self.args)

            def join(self, timeout=None):
                return None

        with tempfile.TemporaryDirectory() as tmpdir:
            token_path = Path(tmpdir) / "tokens.json"
            buffer = io.StringIO()
            with (
                patch.object(polar_oauth_local, "CLIENT_ID", "client"),
                patch.object(polar_oauth_local, "CLIENT_SECRET", "secret"),
                patch.object(polar_oauth_local, "REDIRECT_URI", "https://example/auth/callback"),
                patch.object(polar_oauth_local, "TOKEN_FILE", token_path),
                patch.object(polar_oauth_local, "start_callback_server", side_effect=fake_start_callback_server),
                patch.object(polar_oauth_local.threading, "Thread", FakeThread),
                patch.object(polar_oauth_local.webbrowser, "open", return_value=True),
                patch.object(polar_oauth_local, "exchange_code_for_token", return_value=fake_result) as token_mock,
                contextlib.redirect_stdout(buffer),
            ):
                access_token, x_user_id = polar_oauth_local.do_oauth_flow()

            self.assertEqual(access_token, "tok")
            self.assertEqual(x_user_id, "uid")
            self.assertTrue(token_path.exists())
            self.assertIn('"access_token": "tok"', token_path.read_text(encoding="utf-8"))
            self.assertEqual(token_mock.call_args.args[3], polar_oauth_local.TOKEN_URL)
            self.assertEqual(token_mock.call_args.args[4], "https://example/auth/callback")


if __name__ == "__main__":
    unittest.main()
