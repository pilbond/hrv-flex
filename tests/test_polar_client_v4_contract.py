import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from hrv_app import polar_client_v4 as client_mod
from hrv_app.polar_client_v4 import API_BASE_V4, PolarV4Error, V4Client, _extract_items


class _FakeResponse:
    def __init__(self, status_code=200, payload=None, text=None):
        self.status_code = status_code
        self._payload = payload if payload is not None else {}
        self.text = text if text is not None else json.dumps(self._payload)
        self.reason = {401: "Unauthorized", 404: "Not Found"}.get(status_code, "OK")
        self.headers = {"Content-Type": "application/json"}

    def json(self):
        return self._payload


def _make_client(tmp: str) -> V4Client:
    return V4Client(bundle_path=Path(tmp) / "b.json", request_delay=0.0)


class V4ClientUrlContractTests(unittest.TestCase):
    def _capture_get(self, calls, payload=None):
        def fake_get(url, params=None, headers=None, timeout=None):
            calls.append({"url": url, "params": params, "headers": headers, "timeout": timeout})
            return _FakeResponse(payload=payload or {})
        return fake_get

    def test_fetch_sleeps_url_params_and_bearer(self):
        calls = []
        with TemporaryDirectory() as tmp:
            c = _make_client(tmp)
            with patch.object(client_mod.polar_auth_v4, "get_valid_access_token", return_value="tok"), \
                    patch.object(client_mod.requests, "get", side_effect=self._capture_get(calls, {"nightSleeps": []})):
                result = c.fetch_sleeps("2026-06-01", "2026-06-12")

        self.assertEqual(result, [])
        self.assertEqual(calls[0]["url"], f"{API_BASE_V4}/sleeps")
        self.assertEqual(calls[0]["params"], {"from": "2026-06-01", "to": "2026-06-12"})
        self.assertEqual(calls[0]["headers"]["Authorization"], "Bearer tok")
        self.assertEqual(calls[0]["headers"]["Accept"], "application/json")

    def test_endpoint_paths(self):
        cases = [
            (lambda c: c.fetch_nightly_recharges("a", "b"), "/nightly-recharge-results"),
            (lambda c: c.list_training_sessions("a", "b"), "/training-sessions/list"),
            (lambda c: c.fetch_ppi_samples("a", "b"), "/ppi-samples"),
            (lambda c: c.fetch_tests("a", "b"), "/tests/list"),
        ]
        for call, expected_path in cases:
            calls = []
            with TemporaryDirectory() as tmp:
                c = _make_client(tmp)
                with patch.object(client_mod.polar_auth_v4, "get_valid_access_token", return_value="tok"), \
                        patch.object(client_mod.requests, "get", side_effect=self._capture_get(calls, {})):
                    call(c)
            self.assertEqual(calls[0]["url"], f"{API_BASE_V4}{expected_path}", expected_path)

    def test_training_sessions_promotes_date_to_datetime(self):
        # `/training-sessions/list` exige datetime ISO en from/to: con fecha
        # pura devuelve 400 "could not be parsed as datetime" (captura F0
        # 2026-06-13). El cliente promueve YYYY-MM-DD -> YYYY-MM-DDT00:00:00.
        calls = []
        with TemporaryDirectory() as tmp:
            c = _make_client(tmp)
            with patch.object(client_mod.polar_auth_v4, "get_valid_access_token", return_value="tok"), \
                    patch.object(client_mod.requests, "get", side_effect=self._capture_get(calls, {})):
                c.list_training_sessions("2026-06-12", "2026-06-13")
        self.assertEqual(calls[0]["params"]["from"], "2026-06-12T00:00:00")
        self.assertEqual(calls[0]["params"]["to"], "2026-06-13T00:00:00")

    def test_other_endpoints_keep_date_only(self):
        # El resto de endpoints v4 aceptan fecha pura: no deben recibir el
        # sufijo de hora (regresión: la promoción es solo de training-sessions).
        calls = []
        with TemporaryDirectory() as tmp:
            c = _make_client(tmp)
            with patch.object(client_mod.polar_auth_v4, "get_valid_access_token", return_value="tok"), \
                    patch.object(client_mod.requests, "get", side_effect=self._capture_get(calls, {})):
                c.fetch_sleeps("2026-06-12", "2026-06-13")
        self.assertEqual(calls[0]["params"]["from"], "2026-06-12")
        self.assertEqual(calls[0]["params"]["to"], "2026-06-13")

    def test_no_session_detail_endpoint(self):
        # v4 no publica /training-sessions/{id}: el enriquecimiento se pide
        # con features sobre /list. El cliente no debe exponer ese método.
        with TemporaryDirectory() as tmp:
            c = _make_client(tmp)
        self.assertFalse(hasattr(c, "get_training_session"))

    def test_features_param_is_passed_as_list(self):
        calls = []
        with TemporaryDirectory() as tmp:
            c = _make_client(tmp)
            with patch.object(client_mod.polar_auth_v4, "get_valid_access_token", return_value="tok"), \
                    patch.object(client_mod.requests, "get", side_effect=self._capture_get(calls, {"nightSleeps": []})):
                c.fetch_sleeps("2026-06-11", "2026-06-12", features=["sleepScore", "sleepEvaluation"])
                c.fetch_ppi_samples("2026-06-11", "2026-06-12", features="samples")

        self.assertEqual(calls[0]["params"]["features"], ["sleepScore", "sleepEvaluation"])
        self.assertEqual(calls[1]["params"]["features"], ["samples"])

    def test_network_errors_are_typed_as_polar_v4_error(self):
        import requests as _requests

        # Contrato del cliente: Timeout/ConnectionError no se propagan
        # crudos, salen como PolarV4Error.
        with TemporaryDirectory() as tmp:
            c = _make_client(tmp)
            with patch.object(client_mod.polar_auth_v4, "get_valid_access_token", return_value="tok"), \
                    patch.object(client_mod.requests, "get", side_effect=_requests.Timeout("timed out")):
                with self.assertRaises(PolarV4Error) as ctx:
                    c.fetch_sleeps("2026-06-11", "2026-06-12")
        self.assertIn("error de red", str(ctx.exception))

    def test_features_with_multiday_range_raises_before_request(self):
        # Doc oficial: con `features` el rango se limita a 1 día. Debe fallar
        # por contrato (sin red) en vez de devolver un 400 difícil de leer.
        with TemporaryDirectory() as tmp:
            c = _make_client(tmp)
            with patch.object(client_mod.polar_auth_v4, "get_valid_access_token", return_value="tok"), \
                    patch.object(client_mod.requests, "get") as mock_get:
                with self.assertRaises(PolarV4Error):
                    c.fetch_sleeps("2026-06-01", "2026-06-12", features=["sleepScore"])
        mock_get.assert_not_called()

    def test_features_with_single_day_range_is_allowed(self):
        with TemporaryDirectory() as tmp:
            c = _make_client(tmp)
            with patch.object(client_mod.polar_auth_v4, "get_valid_access_token", return_value="tok"), \
                    patch.object(client_mod.requests, "get", side_effect=self._capture_get([], {"nightSleeps": []})):
                c.fetch_sleeps("2026-06-11", "2026-06-12", features=["sleepScore"])

    def test_training_sessions_list_uses_longer_timeout(self):
        calls = []
        with TemporaryDirectory() as tmp:
            c = _make_client(tmp)
            with patch.object(client_mod.polar_auth_v4, "get_valid_access_token", return_value="tok"), \
                    patch.object(client_mod.requests, "get", side_effect=self._capture_get(calls, {"trainingSessions": []})):
                c.list_training_sessions("a", "b", features=["samples"])
        self.assertEqual(calls[0]["timeout"], 90)


class V4ClientAuthBehaviourTests(unittest.TestCase):
    def test_missing_token_raises_typed_error(self):
        with TemporaryDirectory() as tmp:
            c = _make_client(tmp)
            with patch.object(client_mod.polar_auth_v4, "get_valid_access_token", return_value=None):
                with self.assertRaises(PolarV4Error):
                    c.fetch_sleeps("a", "b")

    def test_401_triggers_single_forced_refresh_and_retry(self):
        token_calls = []
        responses = [_FakeResponse(401, text="expired"), _FakeResponse(payload={"nightSleeps": [{"sleepDate": "2026-06-10"}]})]

        def fake_token(path, **kwargs):
            token_calls.append(kwargs.get("force_refresh", False))
            return "tok2" if kwargs.get("force_refresh") else "tok1"

        with TemporaryDirectory() as tmp:
            c = _make_client(tmp)
            with patch.object(client_mod.polar_auth_v4, "get_valid_access_token", side_effect=fake_token), \
                    patch.object(client_mod.requests, "get", side_effect=responses):
                result = c.fetch_sleeps("a", "b")

        self.assertEqual(result, [{"sleepDate": "2026-06-10"}])
        self.assertEqual(token_calls, [False, True])

    def test_second_401_raises_with_status_and_without_token(self):
        responses = [_FakeResponse(401, text="expired"), _FakeResponse(401, text="expired again")]
        with TemporaryDirectory() as tmp:
            c = _make_client(tmp)
            with patch.object(client_mod.polar_auth_v4, "get_valid_access_token", return_value="tok-secreto"), \
                    patch.object(client_mod.requests, "get", side_effect=responses):
                with self.assertRaises(PolarV4Error) as ctx:
                    c.fetch_sleeps("a", "b")
        self.assertEqual(ctx.exception.status, 401)
        self.assertNotIn("tok-secreto", str(ctx.exception))

    def test_http_error_is_typed_with_status(self):
        with TemporaryDirectory() as tmp:
            c = _make_client(tmp)
            with patch.object(client_mod.polar_auth_v4, "get_valid_access_token", return_value="tok"), \
                    patch.object(client_mod.requests, "get", return_value=_FakeResponse(404, text="nope")):
                with self.assertRaises(PolarV4Error) as ctx:
                    c.fetch_ppi_samples("a", "b")
        self.assertEqual(ctx.exception.status, 404)


class ExtractItemsTests(unittest.TestCase):
    def test_known_wrapper_key(self):
        payload = {"nightSleeps": [{"a": 1}]}
        self.assertEqual(_extract_items(payload, ("nightSleeps",)), [{"a": 1}])

    def test_bare_list(self):
        self.assertEqual(_extract_items([{"a": 1}], ("whatever",)), [{"a": 1}])

    def test_single_unknown_list_wrapper(self):
        payload = {"futureKey": [{"a": 1}], "meta": "x"}
        self.assertEqual(_extract_items(payload, ("nightSleeps",)), [{"a": 1}])

    def test_official_double_wrapper_nightly(self):
        # Shape oficial v4: {"nightlyRechargeResults": {"nightlyRechargeResults": [...]}}
        payload = {"nightlyRechargeResults": {"nightlyRechargeResults": [{"sleepResultDate": "2026-06-10"}]}}
        self.assertEqual(
            _extract_items(payload, ("nightlyRechargeResults",)),
            [{"sleepResultDate": "2026-06-10"}],
        )

    def test_single_unknown_dict_wrapper_descends(self):
        payload = {"someResponse": {"nightSleeps": [{"a": 1}]}}
        self.assertEqual(_extract_items(payload, ("nightSleeps",)), [{"a": 1}])

    def test_fetch_nightly_with_official_payload_end_to_end(self):
        fixtures = Path(__file__).parent / "fixtures" / "polar_v4" / "nightly_recharge_results.json"
        payload = json.loads(fixtures.read_text(encoding="utf-8"))
        with TemporaryDirectory() as tmp:
            c = _make_client(tmp)
            with patch.object(client_mod.polar_auth_v4, "get_valid_access_token", return_value="tok"), \
                    patch.object(client_mod.requests, "get", return_value=_FakeResponse(payload=payload)):
                items = c.fetch_nightly_recharges("2025-06-12", "2025-06-13")
        # Fixture real capturado en F0 (2026-06-13, anonimizado): un día.
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["sleepResultDate"], "2025-06-13")

    def test_none_and_empty(self):
        self.assertEqual(_extract_items(None, ("k",)), [])
        self.assertEqual(_extract_items({}, ("k",)), [])


if __name__ == "__main__":
    unittest.main()
