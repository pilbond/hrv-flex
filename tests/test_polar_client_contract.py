import unittest
from unittest.mock import patch

import polar_client


class _FakeResponse:
    def __init__(self, payload, content_type="application/json"):
        self.payload = payload
        self.status_code = 200
        self.reason = "OK"
        self.text = "plain text"
        self.headers = {"Content-Type": content_type}

    def json(self):
        return self.payload


class PolarClientContractTests(unittest.TestCase):
    def test_api_request_and_helper_endpoints(self):
        calls = []

        def fake_request(**kwargs):
            calls.append(kwargs)
            return _FakeResponse({"ok": True})

        with patch.object(polar_client.requests, "request", side_effect=fake_request):
            self.assertEqual(polar_client.api_request("GET", "/ping", "token"), {"ok": True})
            self.assertEqual(polar_client.list_exercises("token"), {"ok": True})
            self.assertEqual(polar_client.get_exercise_with_samples("token", "ex1"), {"ok": True})
            self.assertEqual(polar_client.fetch_polar_sleep("token", "user", "2026-03-01"), {"ok": True})
            self.assertEqual(
                polar_client.fetch_polar_nightly_recharge("token", "user", "2026-03-01"),
                {"ok": True},
            )

        self.assertEqual(calls[0]["url"], "https://www.polaraccesslink.com/v3/ping")
        self.assertEqual(calls[1]["url"], "https://www.polaraccesslink.com/v3/exercises")
        self.assertEqual(calls[2]["params"], {"samples": "true"})
        self.assertEqual(calls[3]["url"], "https://www.polaraccesslink.com/v3/users/sleep/2026-03-01")
        self.assertEqual(calls[4]["url"], "https://www.polaraccesslink.com/v3/users/nightly-recharge/2026-03-01")

    def test_register_user_if_needed_forwards_arguments(self):
        with patch.object(polar_client, "register_polar_user", return_value={"status": "registered"}) as register_mock:
            result = polar_client.register_user_if_needed("token", "local_user", allow_transient_failure=True)

        self.assertEqual(result, {"status": "registered"})
        register_mock.assert_called_once()
        kwargs = register_mock.call_args.kwargs
        self.assertEqual(kwargs["member_id"], "local_user")
        self.assertEqual(kwargs["user_url"], "https://www.polaraccesslink.com/v3/users")
        self.assertTrue(kwargs["allow_transient_failure"])


if __name__ == "__main__":
    unittest.main()
