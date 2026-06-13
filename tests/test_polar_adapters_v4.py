import json
import unittest
from pathlib import Path

from hrv_app.polar_adapters_v4 import (
    index_by_date,
    v4_nightly_to_internal,
    v4_session_to_internal,
    v4_sleep_to_internal,
)
from hrv_app.sleep_store import _extract_nightly_fields, _extract_sleep_fields

FIXTURES = Path(__file__).parent / "fixtures"


def _load(rel: str):
    return json.loads((FIXTURES / rel).read_text(encoding="utf-8"))


class SleepAdapterTests(unittest.TestCase):
    def test_v4_sleep_produces_same_extraction_as_v3(self):
        v4_item = _load("polar_v4/sleeps.json")["nightSleeps"][0]
        v3_payload = _load("polar_v3/sleep.json")

        adapted = v4_sleep_to_internal(v4_item)
        fields_v4 = _extract_sleep_fields(adapted)
        fields_v3 = _extract_sleep_fields(v3_payload)

        # Métricas comunes a ambos shapes: el adaptador debe alimentar
        # sleep_store igual que el JSON v3 nativo.
        for key in ("polar_sleep_duration_min", "polar_sleep_span_min", "polar_deep_pct",
                    "polar_rem_pct", "polar_sleep_score", "polar_continuity"):
            self.assertIn(key, fields_v4, key)
            self.assertAlmostEqual(fields_v4[key], fields_v3[key], places=3, msg=key)

    def test_v4_sleep_interruptions_via_evaluation(self):
        v4_item = _load("polar_v4/sleeps.json")["nightSleeps"][0]
        fields = _extract_sleep_fields(v4_sleep_to_internal(v4_item))
        # Fixture real F0: sleepEvaluation.interruptions {longCount: 1, totalCount: 26}.
        self.assertEqual(fields.get("polar_interruptions_long"), 1.0)
        self.assertEqual(fields.get("polar_interruptions_total"), 26.0)

    def test_adapter_handles_invalid_input(self):
        self.assertIsNone(v4_sleep_to_internal(None))
        self.assertIsNone(v4_sleep_to_internal({}))
        self.assertIsNone(v4_sleep_to_internal("not-a-dict"))

    def test_phase_durations_as_protobuf_second_strings(self):
        # Ejemplos oficiales de /sleeps: "90s", "5460s" (protobuf Duration),
        # aunque el swagger declare int64 ms. Un "5460s" crudo no lo entiende
        # sleep_store y 5460 plano se leería como minutos.
        v4_item = _load("polar_v4/sleeps.json")["nightSleeps"][0]
        v4_item = json.loads(json.dumps(v4_item))
        phases = v4_item["sleepEvaluation"]["phaseDurations"]
        phases["deep"] = "5460s"
        phases["rem"] = "5940s"
        phases["light"] = "14400s"
        # Sin asleepDuration/sleepSpan autoritativos la duración se recalcula
        # desde la suma de fases (es lo que este test ejercita: el parseo de
        # los strings protobuf "Ns"). El fixture real los trae y ganarían.
        v4_item["sleepEvaluation"].pop("asleepDuration", None)
        v4_item["sleepEvaluation"].pop("sleepSpan", None)

        fields = _extract_sleep_fields(v4_sleep_to_internal(v4_item))
        # 5460+5940+14400 s = 430 min de sueño total.
        self.assertAlmostEqual(fields["polar_sleep_duration_min"], 430.0, places=1)
        self.assertAlmostEqual(fields["polar_deep_pct"], 100.0 * 91.0 / 430.0, places=1)
        self.assertAlmostEqual(fields["polar_rem_pct"], 100.0 * 99.0 / 430.0, places=1)

    def test_authoritative_duration_span_and_efficiency_win_over_recalc(self):
        # Polar publica asleepDuration/sleepSpan/efficiencyPercent: deben
        # usarse tal cual, no recalcularse desde fases y horas de inicio/fin.
        v4_item = _load("polar_v4/sleeps.json")["nightSleeps"][0]
        v4_item = json.loads(json.dumps(v4_item))
        ev = v4_item["sleepEvaluation"]
        ev["asleepDuration"] = "25200s"      # 420 min
        ev["sleepSpan"] = "36000s"           # 600 min
        ev["analysis"]["efficiencyPercent"] = 70.0

        fields = _extract_sleep_fields(v4_sleep_to_internal(v4_item))
        self.assertAlmostEqual(fields["polar_sleep_duration_min"], 420.0, places=1)
        self.assertAlmostEqual(fields["polar_sleep_span_min"], 600.0, places=1)
        self.assertAlmostEqual(fields["polar_efficiency_pct"], 70.0, places=1)

    def test_phase_durations_as_objects_with_duration_millis(self):
        # Variante del esquema oficial: phaseDurations.{deep,rem,light} como
        # objeto {"durationMillis": N} en lugar de número plano de segundos.
        v4_item = _load("polar_v4/sleeps.json")["nightSleeps"][0]
        v4_item = json.loads(json.dumps(v4_item))  # copia profunda
        phases = v4_item["sleepEvaluation"]["phaseDurations"]
        phases["deep"] = {"durationMillis": 5460000}
        phases["rem"] = {"durationMillis": 5940000}
        phases["light"] = {"durationMillis": 14400000}

        fields = _extract_sleep_fields(v4_sleep_to_internal(v4_item))
        self.assertIn("polar_sleep_duration_min", fields)
        self.assertIn("polar_deep_pct", fields)
        self.assertIn("polar_rem_pct", fields)
        self.assertGreater(fields["polar_sleep_duration_min"], 0)


class NightlyAdapterTests(unittest.TestCase):
    def test_v4_nightly_extracts_real_fixture_fields(self):
        # Shape real confirmado en F0 (2026-06-13): wrapper SIMPLE
        # {"nightlyRechargeResults": [ {...} ]}. El item trae
        # meanNightlyRecoveryRmssd y meanNightlyRecoveryRri directos; el
        # intervalo respiratorio medio viene a 0 en esta captura, así que no
        # se deriva polar_night_resp.
        v4_item = _load("polar_v4/nightly_recharge_results.json")["nightlyRechargeResults"][0]
        fields = _extract_nightly_fields(v4_nightly_to_internal(v4_item))

        self.assertEqual(fields["polar_night_rmssd"], 47.0)
        # RRI medio directo de v4 (no derivado de HR): meanNightlyRecoveryRri.
        self.assertEqual(fields["polar_night_rri"], 1190.0)
        # respirationInterval=0 en el fixture → sin frecuencia respiratoria.
        self.assertNotIn("polar_night_resp", fields)

    def test_adapter_handles_invalid_input(self):
        self.assertIsNone(v4_nightly_to_internal(None))
        self.assertIsNone(v4_nightly_to_internal({}))


class SessionAdapterTests(unittest.TestCase):
    SPORT_CATALOG = {"22353647432": "BODY_AND_MIND", "10005": "TRAIL_RUNNING"}

    def test_v4_session_maps_to_v3_exercise_shape(self):
        v4_item = _load("polar_v4/training_sessions_list.json")["trainingSessions"][0]
        v3_exercise = _load("polar_v3/exercise_with_samples.json")

        adapted = v4_session_to_internal(v4_item, sport_catalog=self.SPORT_CATALOG)
        self.assertEqual(adapted["id"], "ts-001")
        self.assertEqual(adapted["detailed-sport-info"], v3_exercise["detailed-sport-info"])
        # durationMillis (510000) → "PT8M30S"
        self.assertEqual(adapted["duration"], v3_exercise["duration"])
        self.assertIn("start-time", adapted)

        rr = [s for s in adapted["samples"] if s.get("sample-type") == "11"]
        self.assertEqual(len(rr), 1)
        self.assertEqual(rr[0]["data"], v3_exercise["samples"][0]["data"])

    def test_session_without_rr_has_no_samples(self):
        v4_item = _load("polar_v4/training_sessions_list.json")["trainingSessions"][1]
        adapted = v4_session_to_internal(v4_item, sport_catalog=self.SPORT_CATALOG)
        self.assertEqual(adapted["detailed-sport-info"], "TRAIL_RUNNING")
        self.assertNotIn("samples", adapted)

    def test_sport_id_passthrough_without_catalog(self):
        # Sin catálogo el id crudo se preserva: el gateway de F5 resolverá.
        v4_item = _load("polar_v4/training_sessions_list.json")["trainingSessions"][0]
        adapted = v4_session_to_internal(v4_item)
        self.assertEqual(adapted["detailed-sport-info"], "22353647432")

    def test_rr_samples_from_official_nested_path(self):
        # exercises[].samples.rrSamples[{durationMillis}] (swagger oficial).
        v4_item = {
            "identifier": {"id": "x"},
            "sport": {"id": "1"},
            "exercises": [{
                "samples": {
                    "rrSamples": [
                        {"durationMillis": 812, "offline": False},
                        {"durationMillis": 820, "offline": False},
                    ]
                }
            }]
        }
        adapted = v4_session_to_internal(v4_item)
        rr = [s for s in adapted["samples"] if s.get("sample-type") == "11"]
        self.assertEqual(rr[0]["data"], "812,820")


    def test_offline_flag_preserved_as_parallel_mask(self):
        # offline=true de Polar es la primera capa de descarte de artefactos
        # del contrato HRV: un RR 300–2000ms marcado offline no debe
        # convertirse en válido al perder el flag.
        v4_item = {
            "identifier": {"id": "x"},
            "exercises": [{
                "samples": {
                    "rrSamples": [
                        {"durationMillis": 812, "offline": False},
                        {"durationMillis": 815, "offline": True},
                        {"durationMillis": 820, "offline": False},
                    ]
                }
            }]
        }
        adapted = v4_session_to_internal(v4_item)
        rr = [s for s in adapted["samples"] if s.get("sample-type") == "11"][0]
        self.assertEqual(rr["data"], "812,815,820")
        self.assertEqual(rr["offline"], "0,1,0")

    def test_transition_rr_samples_included(self):
        # Multideporte: samples.transitionRrSamples (mismo schema) no deben
        # desaparecer silenciosamente.
        v4_item = {
            "identifier": {"id": "x"},
            "exercises": [{
                "samples": {
                    "rrSamples": [{"durationMillis": 800, "offline": False}],
                    "transitionRrSamples": [{"durationMillis": 900, "offline": True}],
                }
            }]
        }
        adapted = v4_session_to_internal(v4_item)
        rr = [s for s in adapted["samples"] if s.get("sample-type") == "11"][0]
        self.assertEqual(rr["data"], "800,900")
        self.assertEqual(rr["offline"], "0,1")

    def test_sport_emitted_in_kebab_and_snake_variants(self):
        # polar_sessions.match_polar_exercise lee "detailed_sport_info"
        # (snake); sin esa clave el filtro de deporte se salta en silencio.
        v4_item = _load("polar_v4/training_sessions_list.json")["trainingSessions"][0]
        adapted = v4_session_to_internal(v4_item, sport_catalog=self.SPORT_CATALOG)
        self.assertEqual(adapted["detailed-sport-info"], "BODY_AND_MIND")
        self.assertEqual(adapted["detailed_sport_info"], "BODY_AND_MIND")


class IndexByDateTests(unittest.TestCase):
    def test_indexes_range_response_by_iso_date(self):
        items = _load("polar_v4/sleeps.json")["nightSleeps"]
        indexed = index_by_date(items, date_keys=("sleepDate",))
        # Fixture real F0: una noche (2025-06-13).
        self.assertEqual(set(indexed.keys()), {"2025-06-13"})
        self.assertAlmostEqual(indexed["2025-06-13"]["sleepScore"]["sleepScore"], 88.1296, places=3)

    def test_truncates_datetime_to_date(self):
        indexed = index_by_date([{"date": "2025-06-10T07:00:00Z", "x": 1}])
        self.assertIn("2025-06-10", indexed)

    def test_skips_items_without_date(self):
        self.assertEqual(index_by_date([{"x": 1}, None, "str"]), {})


if __name__ == "__main__":
    unittest.main()
