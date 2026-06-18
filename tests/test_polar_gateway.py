import json
import time
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from hrv_app import config
from hrv_app import polar_gateway as gateway
from hrv_app.polar_client_v4 import PolarV4Error

# Mismos fixtures oficiales v4 que test_polar_shadow_contract.
V4_SLEEP_ITEM = {
    "date": "2026-06-10",
    "sleepResult": {"hypnogram": {"sleepStart": "2026-06-10T22:00:00", "sleepEnd": "2026-06-11T06:00:00"}},
    "sleepEvaluation": {
        "asleepDuration": "24000s",
        "analysis": {"efficiencyPercent": 90},
    },
    "sleepScore": {"sleepScore": 75},
}

V4_NIGHTLY_ITEM = {
    "sleepResultDate": "2026-06-10",
    "meanNightlyRecoveryRmssd": 55,
}


class _Env(unittest.TestCase):
    def setUp(self):
        self._tmp = TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.data_dir = Path(self._tmp.name) / "data"
        self.data_dir.mkdir(parents=True, exist_ok=True)

        self._patches = [
            patch.object(config, "TOKEN_FILE_V4", self.data_dir / "polar_tokens_v4.json"),
            patch.object(gateway, "_shared_v4_client", None),
            patch.object(gateway, "_missing_bundle_warned", False),
        ]
        for p in self._patches:
            p.start()
            self.addCleanup(p.stop)

    def _write_valid_bundle(self):
        config.TOKEN_FILE_V4.write_text(json.dumps({
            "access_token": "at",
            "refresh_token": "rt",
            "obtained_at": time.time(),
            "expires_in": 43199,
            "scopes": config.POLAR_V4_SCOPES,
        }), encoding="utf-8")


class V3AndShadowDelegationTests(_Env):
    def test_v3_delegates_to_polar_client(self):
        with patch.object(config, "POLAR_API_VERSION", "v3"), \
                patch.object(gateway.polar_client, "fetch_polar_sleep", return_value={"ok": True}) as sleep_mock, \
                patch.object(gateway.polar_client, "fetch_polar_nightly_recharge", return_value={"ok": True}) as nightly_mock:
            sleep = gateway.fetch_polar_sleep("tok", "user", "2026-06-10")
            nightly = gateway.fetch_polar_nightly_recharge("tok", "user", "2026-06-10")

        sleep_mock.assert_called_once_with("tok", "user", "2026-06-10")
        nightly_mock.assert_called_once_with("tok", "user", "2026-06-10")
        self.assertEqual(sleep, {"ok": True})
        self.assertEqual(nightly, {"ok": True})

    def test_shadow_behaves_as_v3(self):
        with patch.object(config, "POLAR_API_VERSION", "shadow"), \
                patch.object(gateway.polar_client, "fetch_polar_sleep", return_value={"ok": True}) as sleep_mock:
            gateway.fetch_polar_sleep("tok", "user", "2026-06-10")

        sleep_mock.assert_called_once_with("tok", "user", "2026-06-10")


class V4NoTokenTests(_Env):
    def test_no_bundle_returns_none(self):
        with patch.object(config, "POLAR_API_VERSION", "v4"):
            self.assertIsNone(gateway.fetch_polar_sleep("ignored", None, "2026-06-10"))
            self.assertIsNone(gateway.fetch_polar_nightly_recharge("ignored", None, "2026-06-10"))

    def test_no_bundle_logs_a_single_warning(self):
        with patch.object(config, "POLAR_API_VERSION", "v4"), \
                self.assertLogs("hrv_app.polar_gateway", level="WARNING") as logs:
            gateway.fetch_polar_sleep("ignored", None, "2026-06-10")
            gateway.fetch_polar_nightly_recharge("ignored", None, "2026-06-10")
            gateway.fetch_polar_sleep("ignored", None, "2026-06-11")

        warning_messages = [msg for msg in logs.output if "bundle v4 utilizable" in msg]
        self.assertEqual(len(warning_messages), 1)
        self.assertIn("sleep", warning_messages[0])
        self.assertTrue(any("/auth" in msg for msg in logs.output))


class V4FetchTests(_Env):
    def setUp(self):
        super().setUp()
        self._write_valid_bundle()

    def test_sleep_uses_day_window_with_features_and_adapts(self):
        captured = {}

        def _fake_fetch_sleeps(date_from, date_to, features=None):
            captured["args"] = (date_from, date_to, features)
            return [V4_SLEEP_ITEM]

        with patch.object(config, "POLAR_API_VERSION", "v4"), \
                patch.object(gateway.V4Client, "fetch_sleeps", side_effect=_fake_fetch_sleeps):
            result = gateway.fetch_polar_sleep("ignored-token", None, "2026-06-10")

        self.assertEqual(captured["args"][0], "2026-06-10")
        self.assertEqual(captured["args"][1], "2026-06-11")
        self.assertTrue(captured["args"][2])  # features no vacios
        self.assertIsNotNone(result)
        # shape interno v3: asleepDuration "24000s" -> PT24000S
        self.assertEqual(result["asleep_duration"], "PT24000S")
        self.assertEqual(result["sleep_score"], 75)

    def test_nightly_uses_day_window_with_features_and_adapts(self):
        with patch.object(config, "POLAR_API_VERSION", "v4"), \
                patch.object(gateway.V4Client, "fetch_nightly_recharges", return_value=[V4_NIGHTLY_ITEM]):
            result = gateway.fetch_polar_nightly_recharge("ignored-token", None, "2026-06-10")

        self.assertIsNotNone(result)
        self.assertEqual(result["heart_rate_variability_avg"], 55)

    def test_missing_date_in_response_returns_none(self):
        with patch.object(config, "POLAR_API_VERSION", "v4"), \
                patch.object(gateway.V4Client, "fetch_sleeps", return_value=[]):
            self.assertIsNone(gateway.fetch_polar_sleep("ignored", None, "2026-06-10"))

    def test_v4_error_returns_none(self):
        with patch.object(config, "POLAR_API_VERSION", "v4"), \
                patch.object(gateway.V4Client, "fetch_sleeps", side_effect=PolarV4Error("boom")):
            self.assertIsNone(gateway.fetch_polar_sleep("ignored", None, "2026-06-10"))

    def test_client_instance_is_reused_across_calls_for_throttle(self):
        with patch.object(config, "POLAR_API_VERSION", "v4"), \
                patch.object(gateway.V4Client, "fetch_sleeps", return_value=[]), \
                patch.object(gateway.V4Client, "fetch_nightly_recharges", return_value=[]):
            gateway.fetch_polar_sleep("ignored", None, "2026-06-10")
            client_after_sleep = gateway._shared_v4_client
            gateway.fetch_polar_nightly_recharge("ignored", None, "2026-06-10")
            client_after_nightly = gateway._shared_v4_client

        self.assertIsNotNone(client_after_sleep)
        self.assertIs(client_after_sleep, client_after_nightly)


if __name__ == "__main__":
    unittest.main()
