import importlib
import unittest
from unittest.mock import patch

from oauth_utils import build_basic_auth_header
from polar_utils import parse_duration_to_minutes


class PolarHrvAutomationImportTests(unittest.TestCase):
    def test_module_imports_cleanly(self):
        module = importlib.import_module("polar_hrv_automation")
        self.assertTrue(callable(module.main))

    def test_normalize_sleep_minutes_uses_shared_duration_parser(self):
        module = importlib.import_module("polar_hrv_automation")
        self.assertEqual(module._normalize_sleep_minutes("PT1H30M"), parse_duration_to_minutes("PT1H30M"))
        self.assertEqual(module._normalize_sleep_minutes(45), parse_duration_to_minutes(45))

    def test_fetch_intervals_activities_uses_public_basic_auth_helper(self):
        module = importlib.import_module("polar_hrv_automation")

        class _Resp:
            def __init__(self):
                self.headers = {"Content-Type": "application/json"}

            def raise_for_status(self):
                return None

            def json(self):
                return {"activities": []}

        with patch.object(module.requests, "get", return_value=_Resp()) as get_mock:
            self.assertEqual(module.fetch_intervals_activities("secret", "athlete", "2026-03-01"), [])

        headers = get_mock.call_args.kwargs["headers"]
        self.assertEqual(headers["Authorization"], build_basic_auth_header("API_KEY", "secret"))


if __name__ == "__main__":
    unittest.main()
