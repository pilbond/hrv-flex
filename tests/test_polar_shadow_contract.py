import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from hrv_app import config
from hrv_app import polar_shadow as shadow


# Sesion v4 con shape oficial (igual que test_polar_v4_end_to_end): un RR
# offline marcado por el sensor.
V4_SESSION = {
    "id": "ts-1",
    "startTime": "2026-06-10T07:00:00",
    "durationMillis": 300000,
    "exercises": [
        {"samples": {"rrSamples": [
            {"durationMillis": 812, "offline": False},
            {"durationMillis": 815, "offline": True},
        ]}}
    ],
}

# Sleep v4 oficial: 400 min asleep, sleepScore 75.
V4_SLEEP_ITEM = {
    "date": "2026-06-10",
    "sleepResult": {"hypnogram": {"sleepStart": "2026-06-10T22:00:00", "sleepEnd": "2026-06-11T06:00:00"}},
    "sleepEvaluation": {
        "asleepDuration": "24000s",
        "analysis": {"efficiencyPercent": 90},
    },
    "sleepScore": {"sleepScore": 75},
}

# Nightly v4 oficial: rmssd 55.
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
            patch.object(config, "DATA_DIR", self.data_dir),
            patch.object(config, "SLEEP_PATH", self.data_dir / "ENDURANCE_HRV_sleep.csv"),
            patch.object(config, "CORE_PATH", self.data_dir / "ENDURANCE_HRV_master_CORE.csv"),
            patch.object(config, "TOKEN_FILE_V4", self.data_dir / "polar_tokens_v4.json"),
            patch.object(shadow, "SHADOW_PATH", self.data_dir / "audit" / "polar_v4_shadow.jsonl"),
        ]
        for p in self._patches:
            p.start()
            self.addCleanup(p.stop)


class NotShadowModeTests(_Env):
    def test_noop_when_not_shadow(self):
        with patch.object(config, "POLAR_API_VERSION", "v3"):
            result = shadow.run_polar_v4_shadow(dates=["2026-06-10"])

        self.assertEqual(result, [])
        self.assertFalse(shadow.SHADOW_PATH.exists())


class NoTokenTests(_Env):
    def test_no_token_marks_all_domains(self):
        with patch.object(config, "POLAR_API_VERSION", "shadow"):
            records = shadow.run_polar_v4_shadow(dates=["2026-06-10"])

        self.assertEqual(len(records), 1)
        rec = records[0]
        self.assertEqual(rec["date"], "2026-06-10")
        for domain in ("sleep", "nightly", "sessions"):
            self.assertEqual(rec["domains"][domain]["status"], "no_token")
            self.assertFalse(rec["domains"][domain]["v3_present"])

        # Sidecar persistido.
        lines = shadow.SHADOW_PATH.read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(lines), 1)
        self.assertEqual(json.loads(lines[0])["date"], "2026-06-10")


class DiffAndPresenceTests(_Env):
    def setUp(self):
        super().setUp()
        # Bundle v4 valido y fresco (no requiere refresh).
        self.data_dir.mkdir(parents=True, exist_ok=True)
        config.TOKEN_FILE_V4.write_text(json.dumps({
            "access_token": "at",
            "refresh_token": "rt",
            "obtained_at": __import__("time").time(),
            "expires_in": 43199,
            "scopes": config.POLAR_V4_SCOPES,
        }), encoding="utf-8")

        # v3 ya persistio sleep/nightly para 2026-06-10 con valores distintos
        # a los que devolvera v4 (genera diff esperado).
        config.SLEEP_PATH.write_text(
            "Fecha,polar_sleep_duration_min,polar_efficiency_pct,polar_sleep_score,"
            "polar_night_rmssd\n"
            "2026-06-10,380,80,60,50\n",
            encoding="utf-8",
        )
        # CORE no tiene esta fecha -> v3_present False para sessions.
        config.CORE_PATH.write_text("Fecha,HR_stable\n2026-06-01,60\n", encoding="utf-8")

    def test_diffs_presence_and_sidecar(self):
        captured_calls = {}

        def _capture_sleeps(date_from, date_to, features=None):
            captured_calls["sleeps"] = {"from": date_from, "to": date_to, "features": features}
            return [V4_SLEEP_ITEM]

        def _capture_nightly(date_from, date_to, features=None):
            captured_calls["nightly"] = {"from": date_from, "to": date_to, "features": features}
            return [V4_NIGHTLY_ITEM]

        def _capture_sessions(date_from, date_to, features=None, **kw):
            captured_calls["sessions"] = {"from": date_from, "to": date_to, "features": features}
            return [V4_SESSION]

        with patch.object(config, "POLAR_API_VERSION", "shadow"), \
                patch.object(shadow.V4Client, "fetch_sleeps", side_effect=_capture_sleeps), \
                patch.object(shadow.V4Client, "fetch_nightly_recharges", side_effect=_capture_nightly), \
                patch.object(shadow.V4Client, "list_training_sessions", side_effect=_capture_sessions):
            records = shadow.run_polar_v4_shadow(dates=["2026-06-10"])

        # Nightly debe pasar features (sin features v4 solo devuelve fechas).
        self.assertIsNotNone(captured_calls["nightly"]["features"])
        # Los tres dominios usan [day, day+1): forma validada en la captura F0
        # (sessions ademas lo necesita por la promocion a datetime).
        for dom in ("sleeps", "nightly", "sessions"):
            self.assertEqual(captured_calls[dom]["from"], "2026-06-10", dom)
            self.assertEqual(captured_calls[dom]["to"], "2026-06-11", dom)

        self.assertEqual(len(records), 1)
        domains = records[0]["domains"]

        sleep = domains["sleep"]
        self.assertEqual(sleep["status"], "ok")
        self.assertFalse(sleep["refreshed"])
        self.assertTrue(sleep["v3_present"])
        self.assertTrue(sleep["v4_present"])
        # v4 asleepDuration=400min (24000s), v3=380 -> diff.
        self.assertIn("polar_sleep_duration_min", sleep["diff"])
        self.assertEqual(sleep["diff"]["polar_sleep_duration_min"]["v3"], 380)
        self.assertEqual(sleep["diff"]["polar_sleep_duration_min"]["v4"], 400)
        # v4 efficiency=90, v3=80 -> diff.
        self.assertIn("polar_efficiency_pct", sleep["diff"])
        # v4 sleepScore=75, v3=60 -> diff.
        self.assertIn("polar_sleep_score", sleep["diff"])

        nightly = domains["nightly"]
        self.assertEqual(nightly["status"], "ok")
        self.assertTrue(nightly["v3_present"])
        self.assertTrue(nightly["v4_present"])
        self.assertIn("polar_night_rmssd", nightly["diff"])
        self.assertEqual(nightly["diff"]["polar_night_rmssd"]["v3"], 50)
        self.assertEqual(nightly["diff"]["polar_night_rmssd"]["v4"], 55)

        sessions = domains["sessions"]
        self.assertEqual(sessions["status"], "ok")
        self.assertFalse(sessions["v3_present"])
        self.assertTrue(sessions["v4_present"])
        self.assertEqual(sessions["v4_session_count"], 1)
        self.assertEqual(sessions["v4_rr_counts"], [2])

        # Sidecar append-only con un registro.
        lines = shadow.SHADOW_PATH.read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(lines), 1)


class ErrorHandlingTests(_Env):
    def test_unexpected_exception_does_not_propagate(self):
        with patch.object(config, "POLAR_API_VERSION", "shadow"), \
                patch.object(shadow, "run_shadow_for_dates", side_effect=RuntimeError("boom")):
            result = shadow.run_polar_v4_shadow(dates=["2026-06-10"])

        self.assertEqual(result, [])

    def test_partial_batch_persists_completed_dates(self):
        # Fecha 1 se procesa normal (sin bundle => no_token). En fecha 2,
        # _v3_sleep_row falla (CSV corrupto): el catchall externo come la
        # excepcion, pero la fecha 1 ya debe estar en disco.
        with patch.object(config, "POLAR_API_VERSION", "shadow"), \
                patch.object(shadow, "_v3_sleep_row",
                             side_effect=[None, RuntimeError("csv corrupto")]):
            result = shadow.run_polar_v4_shadow(dates=["2026-06-10", "2026-06-11"])

        self.assertEqual(result, [])  # catchall devuelve [] en run_polar_v4_shadow
        lines = shadow.SHADOW_PATH.read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(lines), 1)
        self.assertEqual(json.loads(lines[0])["date"], "2026-06-10")


if __name__ == "__main__":
    unittest.main()
