"""Integración de corte AYO-13: callback v4 -> bundle persistido ->
get_valid_access_token -> V4Client -> adaptador -> RR CSV.

Las piezas tienen tests unitarios propios; aquí se valida que el circuito
completo encaja sin gateway (F5) de por medio: el mismo bundle que persiste
el callback alimenta al cliente, los samples v4 atraviesan el adaptador con
su máscara offline y terminan en un CSV `duration,offline` válido según el
contrato (docs/contracts/ENDURANCE_HRV_Spec_Tecnica.md).
"""

import json
import time
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from hrv_app import config
from hrv_app import polar_auth_v4 as auth
from hrv_app import polar_client_v4 as client_mod
from hrv_app.hrv_sync_flow import extract_rr_ms, write_rr_csv
from hrv_app.polar_adapters_v4 import v4_session_to_internal
from hrv_app.polar_client_v4 import V4Client

# Mismo origen que web_ui al persistir el bundle del callback: el cliente
# valida los scopes del bundle contra config.POLAR_V4_SCOPES.
SCOPES = config.POLAR_V4_SCOPES

# Payload tal y como lo devolvería /oauth/token en el callback.
TOKEN_RESPONSE = {
    "access_token": "at-e2e",
    "refresh_token": "rt-e2e",
    "expires_in": 43199,
    "token_type": "Bearer",
    "x_user_id": "u1",
}

# Sesión v4 con shape oficial: exercises[].samples.rrSamples[{durationMillis,
# offline}]. El segundo RR viene marcado offline=true por el sensor y el
# tercero está fuera de rango fisiológico: ambos deben salir offline=1.
V4_SESSION = {
    "id": "ts-1",
    "startTime": "2026-06-10T07:00:00",
    "durationMillis": 300000,
    "exercises": [
        {
            "samples": {
                "rrSamples": [
                    {"durationMillis": 812, "offline": False},
                    {"durationMillis": 815, "offline": True},
                    {"durationMillis": 2500, "offline": False},
                    {"durationMillis": 820, "offline": False},
                ]
            }
        }
    ],
}


class _FakeHttpResponse:
    def __init__(self, payload, status_code=200):
        self.status_code = status_code
        self._payload = payload
        self.reason = "OK"
        self.text = json.dumps(payload)

    def json(self):
        return self._payload


class PolarV4EndToEndTests(unittest.TestCase):
    def test_callback_to_rr_csv(self):
        with TemporaryDirectory() as tmp:
            bundle_path = Path(tmp) / "polar_tokens_v4.json"

            # 1. Callback: persiste el bundle bajo lock, como hace web_ui.
            bundle = auth.persist_authorized_bundle(bundle_path, dict(TOKEN_RESPONSE), scopes=SCOPES)
            self.assertEqual(bundle["scopes"], SCOPES)

            # 2. El cliente resuelve el token desde ese mismo bundle (fresco:
            #    no debe hablar con el endpoint de token).
            captured = {}

            def fake_get(url, params=None, headers=None, timeout=None):
                captured.update({"url": url, "params": params, "headers": headers})
                return _FakeHttpResponse({"trainingSessions": [dict(V4_SESSION)]})

            client = V4Client(bundle_path=bundle_path, request_delay=0)
            with patch.object(client_mod.requests, "get", side_effect=fake_get), \
                    patch.object(auth, "refresh_access_token_v4",
                                 side_effect=AssertionError("token fresco: no debe refrescar")):
                sessions = client.list_training_sessions("2026-06-10", "2026-06-10")

            self.assertEqual(captured["headers"]["Authorization"], "Bearer at-e2e")
            self.assertTrue(captured["url"].endswith("/training-sessions/list"))
            # training-sessions/list exige datetime ISO (promovido por el cliente).
            self.assertEqual(captured["params"]["from"], "2026-06-10T00:00:00")
            self.assertEqual(len(sessions), 1)

            # 3. Adaptador v4 -> shape v3 con máscara offline.
            internal = v4_session_to_internal(sessions[0])
            self.assertIsNotNone(internal)

            # 4. Consumidor canónico: extract_rr_ms respeta la máscara y el
            #    rango fisiológico, write_rr_csv produce el contrato exacto.
            rr = extract_rr_ms(internal)
            self.assertEqual([(v, off) for v, off in rr],
                             [(812.0, 0), (815.0, 1), (2500.0, 1), (820.0, 0)])

            out_csv = Path(tmp) / "rr_downloads" / "e2e.csv"
            self.assertTrue(write_rr_csv(rr, str(out_csv)))
            lines = out_csv.read_text(encoding="utf-8").splitlines()
            self.assertEqual(lines[0], "duration,offline")
            self.assertEqual(lines[1], "812.000,0")
            self.assertEqual(lines[2], "815.000,1")
            self.assertEqual(lines[3], "2500.000,1")

    def test_expired_bundle_refreshes_then_serves_client(self):
        # Variante: el bundle persistido por el callback ya expiró cuando el
        # cliente lo usa -> refresh transparente, rotación persistida y la
        # petición sale con el access token nuevo.
        with TemporaryDirectory() as tmp:
            bundle_path = Path(tmp) / "polar_tokens_v4.json"
            auth.persist_authorized_bundle(bundle_path, dict(TOKEN_RESPONSE), scopes=SCOPES)
            stale = json.loads(bundle_path.read_text(encoding="utf-8"))
            stale["obtained_at"] = time.time() - 99999
            bundle_path.write_text(json.dumps(stale), encoding="utf-8")

            captured = {}

            def fake_get(url, params=None, headers=None, timeout=None):
                captured["headers"] = headers
                return _FakeHttpResponse({"trainingSessions": []})

            client = V4Client(bundle_path=bundle_path, request_delay=0)
            with patch.object(client_mod.requests, "get", side_effect=fake_get), \
                    patch.object(config, "CLIENT_ID", "cid"), \
                    patch.object(config, "CLIENT_SECRET", "sec"), \
                    patch.object(auth, "refresh_access_token_v4",
                                 return_value={"access_token": "at-rotado", "refresh_token": "rt-rotado",
                                               "expires_in": 43199}):
                sessions = client.list_training_sessions("2026-06-10", "2026-06-10")

            self.assertEqual(sessions, [])
            self.assertEqual(captured["headers"]["Authorization"], "Bearer at-rotado")
            persisted = json.loads(bundle_path.read_text(encoding="utf-8"))
            self.assertEqual(persisted["refresh_token"], "rt-rotado")
            self.assertEqual(persisted["x_user_id"], "u1")


if __name__ == "__main__":
    unittest.main()
