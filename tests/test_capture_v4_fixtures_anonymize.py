import importlib.util
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

_SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "capture_v4_fixtures.py"
sys.path.insert(0, str(_SCRIPT.parent.parent))
_spec = importlib.util.spec_from_file_location("capture_v4_fixtures", _SCRIPT)
capture = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(capture)


class AnonymizeTests(unittest.TestCase):
    def test_strips_camelcase_token_keys(self):
        payload = {
            "accessToken": "at-secreto",
            "refreshToken": "rt-secreto",
            "idToken": "id-secreto",
            "access_token": "at2",
            "jti": "x",
            "sleepScore": 82,
        }
        out = capture._anonymize(payload, 0)
        self.assertEqual(set(out.keys()), {"sleepScore"})

    def test_anonymizes_camelcase_user_and_device_ids(self):
        payload = {"xUserId": 123, "userId": 456, "polarUserId": 789, "deviceId": "ABC", "x_user_id": 1}
        out = capture._anonymize(payload, 0)
        self.assertEqual(out["xUserId"], "ANON_USER")
        self.assertEqual(out["userId"], "ANON_USER")
        self.assertEqual(out["polarUserId"], "ANON_USER")
        self.assertEqual(out["x_user_id"], "ANON_USER")
        self.assertEqual(out["deviceId"], "ANON_DEVICE")

    def test_drops_coordinates_and_routes(self):
        payload = {
            "latitude": 42.88, "longitude": -8.54, "lat": 1, "lon": 2,
            "route": [{"latitude": 42.0, "longitude": -8.0}],
            "location": {"city": "x"},
            "distance": 12000,
        }
        out = capture._anonymize(payload, 0)
        self.assertEqual(out, {"distance": 12000})

    def test_drops_prefixed_coordinate_keys(self):
        payload = {
            "startLatitude": 42.88, "endLongitude": -8.54, "maxAltitude": 1200,
            "ascent": 350,
        }
        out = capture._anonymize(payload, 0)
        self.assertEqual(out, {"ascent": 350})

    def test_replaces_identifiers_and_uuids(self):
        payload = {
            "identifier": {"id": "abc-123"},
            "recordingDevice": {"uuid": "9f8b6c1e-2222-4444-8888-aaaaaaaaaaaa"},
        }
        out = capture._anonymize(payload, 0)
        self.assertEqual(out["identifier"], "ANON_ID")
        self.assertEqual(out["recordingDevice"]["uuid"], "ANON_ID")

    def test_anonymizes_id_and_id_suffix_keys(self):
        payload = {
            "id": "abc",
            "sportId": "22353647432",
            "exerciseId": "ex1",
            "routeId": "r1",
            "favoriteId": "f1",
            "organizationId": "o1",
            "sport": {"id": "22353647432"},
            "trainingTarget": {"id": "tt1"},
            "favoriteTarget": {"id": "ft1"},
            "valid": True,
            "paid": False,
            "duration": 510000,
        }
        out = capture._anonymize(payload, 0)
        self.assertEqual(out["id"], "ANON_ID")
        self.assertEqual(out["sportId"], "ANON_ID")
        self.assertEqual(out["exerciseId"], "ANON_ID")
        self.assertEqual(out["routeId"], "ANON_ID")
        self.assertEqual(out["favoriteId"], "ANON_ID")
        self.assertEqual(out["organizationId"], "ANON_ID")
        # Objetos sport/trainingTarget/favoriteTarget se reemplazan enteros.
        self.assertEqual(out["sport"], {"id": "ANON_ID"})
        self.assertEqual(out["trainingTarget"], {"id": "ANON_ID"})
        self.assertEqual(out["favoriteTarget"], {"id": "ANON_ID"})
        # Falsos positivos del sufijo "id": deben preservarse.
        self.assertTrue(out["valid"])
        self.assertFalse(out["paid"])
        self.assertEqual(out["duration"], 510000)

    def test_drops_free_text_fields(self):
        payload = {"name": "Morning ride", "note": "felt sick", "description": "x", "duration": 10}
        out = capture._anonymize(payload, 0)
        self.assertEqual(out, {"duration": 10})

    def test_scrubs_nested_structures(self):
        payload = {"items": [{"refreshToken": "rt", "date": "2026-06-01", "ok": 1}]}
        out = capture._anonymize(payload, -365)
        item = out["items"][0]
        self.assertNotIn("refreshToken", item)
        self.assertEqual(item["date"], "2025-06-01")
        self.assertEqual(item["ok"], 1)


class _FakeResponse:
    def __init__(self, status_code=200, json_payload=None, json_error=False, content_type="application/json"):
        self.status_code = status_code
        self._json_payload = json_payload
        self._json_error = json_error
        self.text = "not json" if json_error else "{}"
        self.reason = "OK"
        self.headers = {"Content-Type": content_type}

    def json(self):
        if self._json_error:
            raise ValueError("invalid json")
        return self._json_payload


class PayloadHasItemsTests(unittest.TestCase):
    def test_empty_wrapper_has_no_items(self):
        self.assertFalse(capture._payload_has_items({"trainingSessions": []}))
        self.assertFalse(capture._payload_has_items({"nightlyRechargeResults": {"nightlyRechargeResults": []}}))
        self.assertFalse(capture._payload_has_items({}))

    def test_nested_non_empty_list_is_detected(self):
        self.assertTrue(capture._payload_has_items({"trainingSessions": [{"id": "x"}]}))
        self.assertTrue(capture._payload_has_items(
            {"nightlyRechargeResults": {"nightlyRechargeResults": [{"a": 1}]}}
        ))


class CaptureOneTests(unittest.TestCase):
    def test_200_with_invalid_json_is_captured_as_error_not_raised(self):
        captured: dict = {}
        with patch.object(capture, "_get", return_value=_FakeResponse(200, json_error=True)):
            capture._capture_one("sleeps_dates", "/sleeps", {}, {}, captured)
        self.assertIn("sleeps_dates", captured)
        self.assertEqual(captured["sleeps_dates"]["status"], 200)
        self.assertIn("invalid JSON", captured["sleeps_dates"]["error_excerpt"])

    def test_200_with_valid_json_is_captured(self):
        captured: dict = {}
        with patch.object(capture, "_get", return_value=_FakeResponse(200, json_payload={"a": 1})):
            capture._capture_one("sleeps_dates", "/sleeps", {}, {}, captured)
        self.assertEqual(captured["sleeps_dates"], {"a": 1})


class PersistCanonicalsTests(unittest.TestCase):
    def test_curated_sidecar_blocks_overwrite(self):
        # `<name>.json.curated` señala un fixture mantenido a mano. La
        # captura real no debe sobreescribirlo (regresión: en la corrida F0
        # del 2026-06-13 una captura limpia sobreescribió el fixture curado
        # de training-sessions con la versión anonimizada que perdía
        # `sport.id`, rompiendo 4 tests de adaptador).
        import json
        from tempfile import TemporaryDirectory

        captured = {
            "training_sessions_list": {"trainingSessions": [{"identifier": "ANON_ID"}]},
            "sleeps": {"nightSleeps": [{"sleepDate": "2025-06-13"}]},
        }
        with TemporaryDirectory() as tmp:
            outdir = Path(tmp)
            (outdir / "training_sessions_list.json").write_text(
                json.dumps({"trainingSessions": [{"identifier": {"id": "ts-001"}}]}), encoding="utf-8"
            )
            (outdir / "training_sessions_list.json.curated").write_text("hand-maintained", encoding="utf-8")

            skipped = capture._persist_canonicals(
                captured, outdir,
                canonical_names=["training_sessions_list", "sleeps"],
                anonymize=False, date_shift=0,
            )

            curated = json.loads((outdir / "training_sessions_list.json").read_text(encoding="utf-8"))
            sleeps = json.loads((outdir / "sleeps.json").read_text(encoding="utf-8"))

        self.assertEqual(skipped, ["training_sessions_list"])
        self.assertEqual(curated["trainingSessions"][0]["identifier"], {"id": "ts-001"})  # intacto
        self.assertEqual(sleeps["nightSleeps"][0]["sleepDate"], "2025-06-13")  # sí sobreescrito

    def test_missing_payload_is_silently_skipped(self):
        # Si la captura no produjo nada para un dominio (p.ej. tests_list sin
        # items en la ventana), no se escribe canónico vacío: el aviso
        # `CAPTURE_STALE.txt` ya lo cubre en main().
        from tempfile import TemporaryDirectory

        with TemporaryDirectory() as tmp:
            outdir = Path(tmp)
            skipped = capture._persist_canonicals(
                {}, outdir, canonical_names=["tests_list"], anonymize=False, date_shift=0
            )
            self.assertEqual(skipped, [])
            self.assertFalse((outdir / "tests_list.json").exists())


class PersistCaptureErrorsTests(unittest.TestCase):
    def test_writes_sidecar_with_only_error_entries(self):
        # Rarezas recurrentes de la API real (p.ej. 500 diario en
        # /nightly-recharge-results del 2026-06-11) deben quedar persistidas
        # para auditoría posterior, no solo en stdout.
        import json
        from tempfile import TemporaryDirectory

        captured = {
            "sleeps": {"nightSleeps": [{"sleepDate": "2025-06-13"}]},  # OK
            "nightly_recharge_results_features_2026-06-11": {
                "status": 500, "url": "/nightly-recharge-results",
                "params": {"from": "2026-06-11", "to": "2026-06-12"},
                "error_excerpt": "Unexpected error occurred",
            },
            "training_sessions_list_dates": {  # otro error
                "status": 400, "url": "/training-sessions/list", "params": {},
                "error_excerpt": "datetime",
            },
        }
        with TemporaryDirectory() as tmp:
            outdir = Path(tmp)
            keys = capture._persist_capture_errors(captured, outdir)
            sidecar = json.loads((outdir / "_capture_errors.json").read_text(encoding="utf-8"))

        self.assertEqual(set(keys), {
            "nightly_recharge_results_features_2026-06-11",
            "training_sessions_list_dates",
        })
        self.assertIn("captured_at_utc", sidecar)
        self.assertEqual(len(sidecar["errors"]), 2)
        statuses = {e["status"] for e in sidecar["errors"]}
        self.assertEqual(statuses, {500, 400})

    def test_no_sidecar_when_no_errors(self):
        # Una corrida 100% limpia no debe dejar un sidecar vacío.
        from tempfile import TemporaryDirectory

        captured = {"sleeps": {"nightSleeps": [{"sleepDate": "2025-06-13"}]}}
        with TemporaryDirectory() as tmp:
            outdir = Path(tmp)
            keys = capture._persist_capture_errors(captured, outdir)
            self.assertEqual(keys, [])
            self.assertFalse((outdir / "_capture_errors.json").exists())


if __name__ == "__main__":
    unittest.main()
