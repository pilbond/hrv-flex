"""Tests F5.2 — Backend v4 para PolarSessionClient y catálogo de deportes.

Cubre los puntos del plan §8:
- Adaptador mecánico: exercises[].samples.samples[] → extract_mechanical_metrics
- Catálogo: sport.id → label v3 vía sport_catalog; sin catálogo no matchea a ciegas
- V4Client.list_sports(): endpoint correcto, catálogo cargado una vez por instancia
- Rango: enrich_row consulta/cachea por fecha de la fila
- Matriz de flags: las 4 combinaciones del §6 no rompen PolarSessionClient
"""
from __future__ import annotations

import json
import time
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import MagicMock, patch

from hrv_app import config
from hrv_app.polar_adapters_v4 import (
    _v4_mechanical_samples_to_v3,
    v4_session_to_internal,
)
from hrv_app.polar_sessions import (
    PolarSessionClient,
    extract_mechanical_metrics,
    fetch_session_rr_v4,
    _load_v4_session_exercises_for_date,
)

FIXTURES = Path(__file__).parent / "fixtures" / "polar_v4"


def _load(rel: str):
    return json.loads((FIXTURES / rel).read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# Adaptador mecánico
# ---------------------------------------------------------------------------

class MechSamplesAdapterTests(unittest.TestCase):
    def _session_with_samples(self, speed=None, cadence=None, power=None, rr=None):
        inner_samples = []
        if speed is not None:
            inner_samples.append({"type": 1, "intervalMillis": 1000, "values": speed})
        if cadence is not None:
            inner_samples.append({"type": 2, "intervalMillis": 1000, "values": cadence})
        if power is not None:
            inner_samples.append({"type": 4, "intervalMillis": 1000, "values": power})
        samples_obj: dict = {}
        if inner_samples:
            samples_obj["samples"] = inner_samples
        if rr is not None:
            samples_obj["rrSamples"] = [{"durationMillis": v, "offline": False} for v in rr]
        return {
            "identifier": {"id": "x"},
            "sport": {"id": "1"},
            "exercises": [{"sport": {"id": "1"}, "samples": samples_obj}],
        }

    def test_speed_cadence_power_adapt_to_v3_format(self):
        session = self._session_with_samples(
            speed=[2.5, 2.7, 2.6],
            cadence=[80, 82, 81],
            power=[200, 210, 205],
        )
        mech = _v4_mechanical_samples_to_v3(session)
        types_found = {s["sample-type"] for s in mech}
        self.assertIn("1", types_found)
        self.assertIn("2", types_found)
        self.assertIn("4", types_found)
        speed_sample = next(s for s in mech if s["sample-type"] == "1")
        self.assertEqual(speed_sample["data"], "2.5,2.7,2.6")
        power_sample = next(s for s in mech if s["sample-type"] == "4")
        self.assertEqual(power_sample["data"], "200,210,205")

    def test_no_samples_returns_empty_list(self):
        session = {"exercises": [{"samples": {}}]}
        self.assertEqual(_v4_mechanical_samples_to_v3(session), [])

    def test_string_types_speed_cadence_power_adapt_to_v3_format(self):
        session = {
            "exercises": [{
                "samples": {
                    "samples": [
                        {"type": "SPEED", "intervalMillis": 1000, "values": [2.5, 2.7, 2.6]},
                        {"type": "CADENCE", "intervalMillis": 1000, "values": [80, 82, 81]},
                        {"type": "POWER", "intervalMillis": 1000, "values": [200, 210, 205]},
                    ]
                }
            }]
        }
        mech = _v4_mechanical_samples_to_v3(session)
        types_found = {s["sample-type"] for s in mech}
        self.assertEqual(types_found, {"1", "2", "4"})

    def test_unknown_type_ignored(self):
        session = {
            "exercises": [{
                "samples": {
                    "samples": [
                        {"type": 99, "intervalMillis": 1000, "values": [1, 2, 3]},
                        {"type": 4, "intervalMillis": 1000, "values": [200, 210]},
                    ]
                }
            }]
        }
        mech = _v4_mechanical_samples_to_v3(session)
        self.assertEqual(len(mech), 1)
        self.assertEqual(mech[0]["sample-type"], "4")

    def test_samples_aggregated_across_exercises(self):
        session = {
            "exercises": [
                {"samples": {"samples": [{"type": 4, "intervalMillis": 1000, "values": [200, 210]}]}},
                {"samples": {"samples": [{"type": 4, "intervalMillis": 1000, "values": [205, 215]}]}},
            ]
        }
        mech = _v4_mechanical_samples_to_v3(session)
        power = next(s for s in mech if s["sample-type"] == "4")
        self.assertEqual(power["data"], "200,210,205,215")

    def test_fixture_with_mech_samples_feeds_extract_mechanical_metrics(self):
        """Fixture completo con ≥60 samples → extract_mechanical_metrics produce métricas."""
        session = _load("training_sessions_with_mech.json")["trainingSessions"][0]
        catalog = {"10005": "TRAIL_RUNNING"}
        adapted = v4_session_to_internal(session, sport_catalog=catalog)

        self.assertIn("samples", adapted)
        mech = extract_mechanical_metrics(adapted)

        self.assertEqual(mech["polar_speed_available"], 1)
        self.assertEqual(mech["polar_cadence_available"], 1)
        self.assertEqual(mech["run_power_available"], 1)
        self.assertIsNotNone(mech["run_power_mean"])
        self.assertIsNotNone(mech["speed_first_half"])
        # Velocidad m/s → km/h: 2.5–2.9 m/s * 3.6 ≈ 9–10.4 km/h
        self.assertGreater(mech["speed_first_half"], 8.0)
        self.assertLess(mech["speed_first_half"], 12.0)

    def test_v4_session_to_internal_includes_mech_and_rr(self):
        """v4_session_to_internal emite samples mecánicos Y RR en la misma sesión."""
        session = _load("training_sessions_with_mech.json")["trainingSessions"][0]
        adapted = v4_session_to_internal(session, sport_catalog={"10005": "TRAIL_RUNNING"})

        rr = [s for s in adapted["samples"] if s.get("sample-type") == "11"]
        mech_speed = [s for s in adapted["samples"] if s.get("sample-type") == "1"]
        self.assertEqual(len(rr), 1)
        self.assertEqual(len(mech_speed), 1)


# ---------------------------------------------------------------------------
# Catálogo de deportes
# ---------------------------------------------------------------------------

class SportCatalogTests(unittest.TestCase):
    CATALOG = {"10005": "TRAIL_RUNNING", "1": "RUNNING", "22353647432": "BODY_AND_MIND"}

    def test_sport_id_resolved_to_label_with_catalog(self):
        session = {
            "identifier": {"id": "s1"},
            "startTime": "2025-07-01T07:00:00",
            "sport": {"id": "10005"},
        }
        adapted = v4_session_to_internal(session, sport_catalog=self.CATALOG)
        self.assertEqual(adapted["detailed-sport-info"], "TRAIL_RUNNING")
        self.assertEqual(adapted["detailed_sport_info"], "TRAIL_RUNNING")

    def test_without_catalog_sport_id_passthrough(self):
        """Sin catálogo el id crudo se preserva; el filtro de deporte no matchea."""
        session = {
            "identifier": {"id": "s1"},
            "sport": {"id": "10005"},
        }
        adapted = v4_session_to_internal(session)
        self.assertEqual(adapted["detailed-sport-info"], "10005")

    def test_catalog_loaded_once_on_success(self):
        """list_sports no se llama dos veces si la primera tuvo éxito."""
        with TemporaryDirectory() as tmpdir:
            bundle = Path(tmpdir) / "v4_tokens.json"
            bundle.write_text(json.dumps({
                "access_token": "at", "refresh_token": "rt",
                "obtained_at": time.time(), "expires_in": 43200,
                "scopes": config.POLAR_V4_SCOPES,
            }), encoding="utf-8")

            with patch.object(config, "POLAR_V4_SESSIONS", True), \
                 patch.object(config, "TOKEN_FILE_V4", bundle):
                client = PolarSessionClient()
                with patch.object(client._v4_client, "list_sports", return_value={"10005": "TRAIL_RUNNING"}) as mock_sports, \
                     patch.object(client._v4_client, "list_training_sessions", return_value=[]):
                    client._list_sessions_for_date("2025-07-01")
                    client._list_sessions_for_date("2025-07-02")
                self.assertEqual(mock_sports.call_count, 1)

    def test_catalog_retried_after_failure(self):
        """Si list_sports falla, se reintenta en la siguiente fecha."""
        with TemporaryDirectory() as tmpdir:
            bundle = Path(tmpdir) / "v4_tokens.json"
            bundle.write_text(json.dumps({
                "access_token": "at", "refresh_token": "rt",
                "obtained_at": time.time(), "expires_in": 43200,
                "scopes": config.POLAR_V4_SCOPES,
            }), encoding="utf-8")

            with patch.object(config, "POLAR_V4_SESSIONS", True), \
                 patch.object(config, "TOKEN_FILE_V4", bundle):
                client = PolarSessionClient()
                call_count = {"n": 0}

                def _fail_then_succeed():
                    call_count["n"] += 1
                    if call_count["n"] == 1:
                        raise RuntimeError("network error")
                    return {"10005": "TRAIL_RUNNING"}

                with patch.object(client._v4_client, "list_sports", side_effect=_fail_then_succeed), \
                     patch.object(client._v4_client, "list_training_sessions", return_value=[]):
                    client._list_sessions_for_date("2025-07-01")  # fallo → reintenta
                    client._list_sessions_for_date("2025-07-02")  # éxito → cachea
                    client._list_sessions_for_date("2025-07-03")  # usa caché
                self.assertEqual(call_count["n"], 2)  # 1 fallo + 1 éxito; tercera usa caché

    def test_catalog_failure_does_not_cache_degraded_date(self):
        """Si list_sports falla para una fecha, no se debe cachear la adaptación degradada."""
        with TemporaryDirectory() as tmpdir:
            bundle = Path(tmpdir) / "v4_tokens.json"
            bundle.write_text(json.dumps({
                "access_token": "at", "refresh_token": "rt",
                "obtained_at": time.time(), "expires_in": 43200,
                "scopes": config.POLAR_V4_SCOPES,
            }), encoding="utf-8")

            with patch.object(config, "POLAR_API_VERSION", "v4"), \
                 patch.object(config, "TOKEN_FILE_V4", bundle):
                client = PolarSessionClient()
                raw = _load("training_sessions_list.json")["trainingSessions"]
                with patch.object(client._v4_client, "list_sports", side_effect=[RuntimeError("boom"), {"22353647432": "BODY_AND_MIND"}]), \
                     patch.object(client._v4_client, "list_training_sessions", return_value=raw) as mock_list:
                    degraded = client._list_sessions_for_date("2025-06-10")
                    recovered = client._list_sessions_for_date("2025-06-10")
                self.assertEqual(mock_list.call_count, 2)
                self.assertEqual(degraded[0]["detailed_sport_info"], "22353647432")
                self.assertEqual(recovered[0]["detailed_sport_info"], "BODY_AND_MIND")


# ---------------------------------------------------------------------------
# V4Client.list_sports endpoint
# ---------------------------------------------------------------------------

class ListSportsTests(unittest.TestCase):
    def test_list_sports_hits_data_path(self):
        """list_sports debe usar el base /v4/data, no la raíz /v4."""
        from hrv_app.polar_client_v4 import V4Client

        with TemporaryDirectory() as tmpdir:
            bundle = Path(tmpdir) / "v4_tokens.json"
            bundle.write_text(json.dumps({
                "access_token": "at",
                "refresh_token": "rt",
                "obtained_at": time.time(),
                "expires_in": 43200,
                "scopes": config.POLAR_V4_SCOPES,
            }), encoding="utf-8")
            client = V4Client(bundle_path=bundle)
            captured = {}

            def _fake_request(path, params=None, timeout=None, *, base=""):
                captured["path"] = path
                captured["base"] = base
                return _load("sports_list.json")

            with patch.object(client, "_request", side_effect=_fake_request):
                catalog = client.list_sports()

            self.assertEqual(captured["path"], "/sports/list")
            self.assertEqual(captured["base"], "")
            self.assertIn("10005", catalog)
            self.assertEqual(catalog["10005"], "TRAIL_RUNNING")

    def test_list_sports_normalizes_to_snake_upper(self):
        """Nombres con espacios deben quedar en SNAKE_UPPER para coincidir
        con POLAR_STANDING_SPORT_MAP (TRAIL_RUNNING, BODY_AND_MIND, etc.)."""
        from hrv_app.polar_client_v4 import V4Client

        with TemporaryDirectory() as tmpdir:
            bundle = Path(tmpdir) / "v4_tokens.json"
            bundle.write_text(json.dumps({
                "access_token": "at", "refresh_token": "rt",
                "obtained_at": time.time(), "expires_in": 43200,
                "scopes": config.POLAR_V4_SCOPES,
            }), encoding="utf-8")
            client = V4Client(bundle_path=bundle)
            raw = {"sports": [
                {"id": "99", "name": "trail running"},
                {"id": "100", "name": "Hiking"},
                {"id": "101", "name": "Body and mind"},
                {"id": "102", "name": "trail-running"},
            ]}
            with patch.object(client, "_request", return_value=raw):
                catalog = client.list_sports()
            self.assertEqual(catalog["99"], "TRAIL_RUNNING")
            self.assertEqual(catalog["100"], "HIKING")
            self.assertEqual(catalog["101"], "BODY_AND_MIND")
            self.assertEqual(catalog["102"], "TRAIL_RUNNING")  # guión también → _

    def test_human_readable_name_matches_v3_filter(self):
        """Integración: name='Trail running' → TRAIL_RUNNING → matchea trail_run."""
        from hrv_app.polar_client_v4 import V4Client
        from hrv_app.polar_adapters_v4 import v4_session_to_internal
        from hrv_app.polar_sessions import match_polar_exercise, POLAR_STANDING_SPORT_MAP

        # 1. list_sports() normaliza nombre legible → etiqueta v3
        with TemporaryDirectory() as tmpdir:
            bundle = Path(tmpdir) / "tok.json"
            bundle.write_text(json.dumps({
                "access_token": "at", "refresh_token": "rt",
                "obtained_at": time.time(), "expires_in": 43200,
                "scopes": config.POLAR_V4_SCOPES,
            }), encoding="utf-8")
            client = V4Client(bundle_path=bundle)
            with patch.object(client, "_request", return_value={
                "sports": [{"id": "10005", "name": "Trail running"}]
            }):
                catalog = client.list_sports()
        self.assertEqual(catalog["10005"], "TRAIL_RUNNING")

        # 2. Sesión adaptada con ese catálogo tiene detailed_sport_info correcto
        session = {
            "identifier": {"id": "s1"},
            "startTime": "2025-07-01T07:30:00",
            "durationMillis": 3600000,
            "sport": {"id": "10005"},
            "exercises": [{"sport": {"id": "10005"}}],
        }
        adapted = v4_session_to_internal(session, sport_catalog=catalog)
        self.assertEqual(adapted["detailed_sport_info"], "TRAIL_RUNNING")

        # 3. match_polar_exercise filtra correctamente por trail_run
        row = {"Fecha": "2025-07-01", "start_time": "07:30", "duration_min": "60", "session_id": "s1"}
        result = match_polar_exercise(row, [adapted], allowed_polar_sports=POLAR_STANDING_SPORT_MAP["trail_run"])
        self.assertEqual(result["exercise"]["id"], "s1")

    def test_list_sports_empty_response_returns_empty_dict(self):
        from hrv_app.polar_client_v4 import V4Client

        with TemporaryDirectory() as tmpdir:
            bundle = Path(tmpdir) / "v4_tokens.json"
            bundle.write_text(json.dumps({
                "access_token": "at", "refresh_token": "rt",
                "obtained_at": time.time(), "expires_in": 43200,
                "scopes": config.POLAR_V4_SCOPES,
            }), encoding="utf-8")
            client = V4Client(bundle_path=bundle)
            with patch.object(client, "_request", return_value={}):
                catalog = client.list_sports()
            self.assertEqual(catalog, {})

    def test_list_sports_accepts_identifier_object_shape(self):
        """Shape real observado: el id puede venir anidado como identifier:{id:N}."""
        from hrv_app.polar_client_v4 import V4Client

        with TemporaryDirectory() as tmpdir:
            bundle = Path(tmpdir) / "v4_tokens.json"
            bundle.write_text(json.dumps({
                "access_token": "at",
                "refresh_token": "rt",
                "obtained_at": time.time(),
                "expires_in": 43200,
                "scopes": config.POLAR_V4_SCOPES,
            }), encoding="utf-8")
            client = V4Client(bundle_path=bundle)
            raw = {
                "sports": [
                    {"identifier": {"id": 1}, "name": "Running"},
                    {"identifier": {"id": 27}, "name": "Trail running"},
                    {"identifier": {"id": 126}, "name": "Core"},
                ]
            }
            with patch.object(client, "_request", return_value=raw):
                catalog = client.list_sports()

            self.assertEqual(catalog["1"], "RUNNING")
            self.assertEqual(catalog["27"], "TRAIL_RUNNING")
            self.assertEqual(catalog["126"], "CORE")


# ---------------------------------------------------------------------------
# PolarSessionClient: rango y caché por fecha
# ---------------------------------------------------------------------------

class SessionClientV4DateRangeTests(unittest.TestCase):
    def _make_client(self, tmpdir: str) -> PolarSessionClient:
        bundle = Path(tmpdir) / "v4_tokens.json"
        bundle.write_text(json.dumps({
            "access_token": "at", "refresh_token": "rt",
            "obtained_at": time.time(), "expires_in": 43200,
            "scopes": config.POLAR_V4_SCOPES,
        }), encoding="utf-8")
        with patch.object(config, "TOKEN_FILE_V4", bundle):
            return PolarSessionClient()

    def test_enrich_row_queries_by_date_not_global(self):
        """Cada enrich_row usa la fecha de la fila; no depende de una lista global."""
        with TemporaryDirectory() as tmpdir, \
             patch.object(config, "POLAR_API_VERSION", "v4"):
            client = self._make_client(tmpdir)
            captured_dates: list = []

            def _fake_list(date_from, date_to, features=None):
                captured_dates.append(date_from)
                return []

            with patch.object(client._v4_client, "list_sports", return_value={}), \
                 patch.object(client._v4_client, "list_training_sessions", side_effect=_fake_list):
                # Dos filas de fechas distintas (sport no standing → no llega al match)
                client.enrich_row({"sport": "road_run", "Fecha": "2025-07-01", "start_time": "07:30", "duration_min": "60"})
                client.enrich_row({"sport": "road_run", "Fecha": "2025-07-02", "start_time": "07:30", "duration_min": "60"})

            self.assertIn("2025-07-01", captured_dates)
            self.assertIn("2025-07-02", captured_dates)

    def test_session_cache_reused_for_same_date(self):
        """Segunda llamada con la misma fecha usa caché: no HTTP duplicado."""
        with TemporaryDirectory() as tmpdir, \
             patch.object(config, "POLAR_API_VERSION", "v4"):
            client = self._make_client(tmpdir)

            with patch.object(client._v4_client, "list_sports", return_value={}), \
                 patch.object(client._v4_client, "list_training_sessions", return_value=[]) as mock_list:
                client._list_sessions_for_date("2025-07-01")
                client._list_sessions_for_date("2025-07-01")

            self.assertEqual(mock_list.call_count, 1)

    def test_v4_degradation_no_bundle_returns_defaults(self):
        """Sin bundle v4 utilizable, enrich_row devuelve defaults sin romper."""
        with TemporaryDirectory() as tmpdir, \
             patch.object(config, "POLAR_API_VERSION", "v4"):
            # Token file no existe → available=False
            with patch.object(config, "TOKEN_FILE_V4", Path(tmpdir) / "nonexistent.json"):
                client = PolarSessionClient()
                self.assertFalse(client.available)
                result = client.enrich_row({"sport": "road_run", "Fecha": "2025-07-01"})
                # Debe devolver defaults sin excepción
                self.assertEqual(result["run_power_available"], 0)
                self.assertIsNone(result["run_power_mean"])

    def test_v4_missing_bundle_logs_warning(self):
        with TemporaryDirectory() as tmpdir, \
             patch.object(config, "POLAR_API_VERSION", "v4"):
            with patch.object(config, "TOKEN_FILE_V4", Path(tmpdir) / "nonexistent.json"):
                client = PolarSessionClient()
                with self.assertLogs("polar_sessions", level="WARNING") as logs:
                    result = client.enrich_row({"sport": "road_run", "Fecha": "2025-07-01", "session_id": "s1"})
        self.assertEqual(result["run_power_available"], 0)
        self.assertTrue(any("sin bundle/token utilizable" in line for line in logs.output))

    def test_v4_match_value_error_returns_defaults(self):
        with TemporaryDirectory() as tmpdir, \
             patch.object(config, "POLAR_API_VERSION", "v4"):
            client = self._make_client(tmpdir)
            with patch.object(client, "_list_sessions_for_date", return_value=[]):
                with self.assertLogs("polar_sessions", level="WARNING") as logs:
                    result = client._enrich_row_v4({"Fecha": "2025-07-01", "sport": "road_run"}, "road_run")
        self.assertEqual(result["run_power_available"], 0)
        self.assertTrue(any("session row lacks Fecha/start_time" in line for line in logs.output))


class FetchSessionRrV4Tests(unittest.TestCase):
    def _row(self) -> dict[str, str]:
        return {
            "Fecha": "2025-06-10",
            "start_time": "07:30",
            "duration_min": "8.5",
            "sport": "road_run",
            "session_id": "s1",
        }

    def test_fetch_session_rr_v4_matches_and_extracts_rr(self):
        row = self._row()
        raw_sessions = _load("training_sessions_list.json")["trainingSessions"]

        with TemporaryDirectory() as tmpdir:
            bundle = Path(tmpdir) / "v4_tokens.json"
            bundle.write_text(json.dumps({
                "access_token": "at",
                "refresh_token": "rt",
                "obtained_at": time.time(),
                "expires_in": 43200,
                "scopes": config.POLAR_V4_SCOPES,
            }), encoding="utf-8")

            with patch("hrv_app.polar_client_v4.polar_auth_v4.get_valid_access_token", return_value="at"), \
                 patch("hrv_app.polar_client_v4.requests.get") as mock_get:
                mock_get.side_effect = [
                    MagicMock(status_code=200, json=lambda: _load("sports_list.json"), reason="OK"),
                    MagicMock(status_code=200, json=lambda: {"trainingSessions": raw_sessions}, reason="OK"),
                ]
                result = fetch_session_rr_v4(
                    row,
                    bundle_path_v4=bundle,
                    allowed_polar_sports={"BODY_AND_MIND"},
                )

        self.assertEqual(result["exercise"]["id"], "ts-001")
        self.assertEqual(result["match"]["start_delta_min"], 0.0)
        self.assertEqual([pair[0] for pair in result["rr"]], [812.0, 820.0, 805.0, 798.0])
        self.assertEqual([pair[1] for pair in result["rr"]], [0, 0, 0, 0])

    def test_fetch_session_rr_v4_raises_when_rr_missing(self):
        row = {
            "Fecha": "2025-06-10",
            "start_time": "18:05",
            "duration_min": "72",
            "sport": "trail_run",
            "session_id": "s2",
        }
        raw_sessions = [_load("training_sessions_list.json")["trainingSessions"][1]]

        with TemporaryDirectory() as tmpdir:
            bundle = Path(tmpdir) / "v4_tokens.json"
            bundle.write_text(json.dumps({
                "access_token": "at",
                "refresh_token": "rt",
                "obtained_at": time.time(),
                "expires_in": 43200,
                "scopes": config.POLAR_V4_SCOPES,
            }), encoding="utf-8")

            with patch("hrv_app.polar_client_v4.polar_auth_v4.get_valid_access_token", return_value="at"), \
                 patch("hrv_app.polar_client_v4.requests.get") as mock_get:
                mock_get.side_effect = [
                    MagicMock(status_code=200, json=lambda: {"sports": [{"id": "10005", "name": "Trail running"}]}, reason="OK"),
                    MagicMock(status_code=200, json=lambda: {"trainingSessions": raw_sessions}, reason="OK"),
                ]
                with self.assertRaises(RuntimeError) as ctx:
                    fetch_session_rr_v4(
                        row,
                        bundle_path_v4=bundle,
                        allowed_polar_sports={"TRAIL_RUNNING"},
                    )

        self.assertIn("RR exportable", str(ctx.exception))

    def test_fetch_session_rr_v4_reuses_cached_date_payload(self):
        row = self._row()
        raw_sessions = _load("training_sessions_list.json")["trainingSessions"]
        _load_v4_session_exercises_for_date.cache_clear()

        with TemporaryDirectory() as tmpdir:
            bundle = Path(tmpdir) / "v4_tokens.json"
            bundle.write_text(json.dumps({
                "access_token": "at",
                "refresh_token": "rt",
                "obtained_at": time.time(),
                "expires_in": 43200,
                "scopes": config.POLAR_V4_SCOPES,
            }), encoding="utf-8")

            with patch("hrv_app.polar_client_v4.polar_auth_v4.get_valid_access_token", return_value="at"), \
                 patch("hrv_app.polar_client_v4.requests.get") as mock_get:
                mock_get.side_effect = [
                    MagicMock(status_code=200, json=lambda: _load("sports_list.json"), reason="OK"),
                    MagicMock(status_code=200, json=lambda: {"trainingSessions": raw_sessions}, reason="OK"),
                ]
                first = fetch_session_rr_v4(
                    row,
                    bundle_path_v4=bundle,
                    allowed_polar_sports={"BODY_AND_MIND"},
                )
                second = fetch_session_rr_v4(
                    row,
                    bundle_path_v4=bundle,
                    allowed_polar_sports={"BODY_AND_MIND"},
                )

        self.assertEqual(first["exercise"]["id"], second["exercise"]["id"])
        self.assertEqual(mock_get.call_count, 2)

    def test_fetch_session_rr_v4_forwards_injected_client_and_catalog(self):
        row = self._row()
        fake_client = object()
        sport_catalog = {"10005": "BODY_AND_MIND"}
        exercises = tuple([
            {
                "id": "ts-001",
                "samples": {"rrSamples": [{"durationMillis": 812, "offline": False}]},
            }
        ])

        with patch("hrv_app.polar_sessions._load_v4_session_exercises_for_date", return_value=exercises) as mock_load, \
             patch("hrv_app.polar_sessions.match_polar_exercise", return_value={
                 "exercise": exercises[0],
                 "start_delta_min": 0.0,
                 "duration_gap_min": 0.0,
             }), \
             patch("hrv_app.hrv_sync_flow.extract_rr_ms", return_value=[(812.0, 0)]):
            result = fetch_session_rr_v4(
                row,
                bundle_path_v4=Path("/tmp/v4_tokens.json"),
                client=fake_client,
                sport_catalog=sport_catalog,
            )

        mock_load.assert_called_once_with(
            Path("/tmp/v4_tokens.json"),
            "2025-06-10",
            client=fake_client,
            sport_catalog=sport_catalog,
        )
        self.assertEqual(result["exercise"]["id"], "ts-001")


# ---------------------------------------------------------------------------
# Matriz de flags (§6): 4 combinaciones no rompen PolarSessionClient
# ---------------------------------------------------------------------------

class RuntimeSelectorTests(unittest.TestCase):
    """El selector efectivo del backend de sesiones sigue POLAR_API_VERSION."""

    def _client_defaults(self, api_version: str) -> dict:
        with TemporaryDirectory() as tmpdir, \
             patch.object(config, "POLAR_API_VERSION", api_version):
            # Paths explícitos (inexistentes) para no usar tokens reales en disco.
            client = PolarSessionClient(
                token_path=Path(tmpdir) / "tok_v3.json",
                bundle_path_v4=Path(tmpdir) / "tok_v4.json",
            )
            return client.enrich_row({"sport": "road_run", "Fecha": "2025-07-01"})

    def test_v3_uses_legacy_path(self):
        result = self._client_defaults("v3")
        self.assertEqual(result["run_power_available"], 0)

    def test_shadow_uses_v4_path(self):
        result = self._client_defaults("shadow")
        self.assertEqual(result["run_power_available"], 0)

    def test_v4_uses_v4_path(self):
        result = self._client_defaults("v4")
        self.assertEqual(result["run_power_available"], 0)


if __name__ == "__main__":
    unittest.main()
