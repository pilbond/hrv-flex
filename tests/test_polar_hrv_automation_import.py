import importlib
import unittest
from unittest.mock import patch

from oauth_utils import build_basic_auth_header


class PolarHrvAutomationImportTests(unittest.TestCase):
    def test_module_imports_cleanly(self):
        module = importlib.import_module("polar_hrv_automation")
        self.assertTrue(callable(module.main))

    def test_refresh_sleep_and_outputs_remains_callable(self):
        module = importlib.import_module("polar_hrv_automation")
        self.assertTrue(callable(module._refresh_sleep_and_outputs))

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

    def test_intervals_activity_aggregation_uses_shared_field_lookup(self):
        module = importlib.import_module("polar_hrv_automation")
        payload = [
            {
                "icu_training_load": 42,
                "moving_time": 3600,
                "startDateLocal": "2026-03-01T07:30:00",
                "type": "Run",
            }
        ]

        out = module._aggregate_intervals_activity_fields(payload)

        self.assertEqual(out["intervals_n_acts"], 1)
        self.assertEqual(out["intervals_load"], 42.0)
        self.assertEqual(out["intervals_duration_min"], 60.0)
        self.assertEqual(out["intervals_type_main"], "Run")


if __name__ == "__main__":
    unittest.main()
