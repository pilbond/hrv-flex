"""Valoraciones personales de Polar Nightly Recharge: adaptador, persistencia
en sleep.csv, contexto de recuperación en FINAL y payload del brief diario."""

import importlib.util
import json
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pandas as pd

import build_hrv_final_dashboard as final_builder
import hrv_app.sleep_store as sleep_store
from hrv_app.ai import daily_brief
from hrv_app.polar_adapters_v4 import v4_nightly_to_internal, v4_sleep_to_internal

FIXTURES = Path(__file__).parent / "fixtures" / "polar_v4"


class AdapterTests(unittest.TestCase):
    def test_nightly_adapter_keeps_polar_ratings_and_baselines(self):
        item = json.loads((FIXTURES / "nightly_recharge_results.json").read_text(encoding="utf-8"))[
            "nightlyRechargeResults"
        ][0]
        out = v4_nightly_to_internal(item)
        self.assertEqual(out["nightly_recharge_status"], 4)
        self.assertEqual(out["nightly_recharge_sublevel"], 58)
        self.assertEqual(out["ans_charge_status"], 2)
        self.assertAlmostEqual(out["ans_charge"], -5.9062, places=3)
        self.assertEqual(out["nightly_rmssd_baseline_sd"], 5)
        self.assertIn("nightly_rri_baseline_mean", out)

    def test_sleep_adapter_keeps_score_rate(self):
        items = json.loads((FIXTURES / "sleeps.json").read_text(encoding="utf-8"))
        night = next(
            it for it in (items.get("nightSleeps") or items.get("sleeps") or [])
            if isinstance(it.get("sleepScore"), dict) and "scoreRate" in it["sleepScore"]
        )
        out = v4_sleep_to_internal(night)
        self.assertEqual(out["sleep_charge_status"], night["sleepScore"]["scoreRate"])

    def test_missing_ratings_are_omitted(self):
        out = v4_nightly_to_internal({"sleepResultDate": "2026-11-06", "meanNightlyRecoveryRmssd": 32})
        self.assertNotIn("nightly_recharge_status", out)
        self.assertNotIn("ans_charge_status", out)


class SleepStoreTests(unittest.TestCase):
    def test_extract_fields_map_ratings_to_sleep_columns(self):
        sleep = sleep_store._extract_sleep_fields({"sleep_score": 68.6, "sleep_charge_status": 2})
        nightly = sleep_store._extract_nightly_fields(
            {"heart_rate_variability_avg": 32, "nightly_recharge_status": 2, "ans_charge_status": 1, "ans_charge": -7.5}
        )
        self.assertEqual(sleep["polar_sleep_charge_status"], 2.0)
        self.assertEqual(nightly["polar_recharge_status"], 2.0)
        self.assertEqual(nightly["polar_ans_charge_status"], 1.0)
        self.assertEqual(nightly["polar_ans_charge"], -7.5)
        self.assertEqual(nightly["polar_night_rmssd"], 32.0)

    def test_legacy_17_column_csv_is_accepted_and_extended(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            sleep_path = Path(tmpdir) / "ENDURANCE_HRV_sleep.csv"
            legacy = pd.DataFrame(
                [{col: np.nan for col in sleep_store.SLEEP_LEGACY_COLUMNS} | {"Fecha": "2026-11-05", "polar_sleep_duration_min": 400}]
            )[sleep_store.SLEEP_LEGACY_COLUMNS]
            self.assertEqual(len(legacy.columns), 17)
            legacy.to_csv(sleep_path, index=False)
            with patch.object(sleep_store, "SLEEP_PATH", sleep_path):
                self.assertTrue(
                    sleep_store.upsert_sleep_row(
                        {"Fecha": "2026-11-06", "polar_sleep_duration_min": 449.5, "polar_recharge_status": 2}
                    )
                )
            out = pd.read_csv(sleep_path)
        self.assertEqual(list(out.columns), sleep_store.SLEEP_COLUMNS)
        self.assertEqual(len(out), 2)
        old = out.loc[out["Fecha"] == "2026-11-05"].iloc[0]
        new = out.loc[out["Fecha"] == "2026-11-06"].iloc[0]
        self.assertTrue(pd.isna(old["polar_recharge_status"]))
        self.assertEqual(new["polar_recharge_status"], 2)

    def test_partial_response_keeps_previous_valid_values(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            sleep_path = Path(tmpdir) / "ENDURANCE_HRV_sleep.csv"
            with patch.object(sleep_store, "SLEEP_PATH", sleep_path):
                sleep_store.upsert_sleep_row(
                    {"Fecha": "2026-11-06", "polar_sleep_duration_min": 449.5, "polar_ans_charge_status": 1}
                )
                # Reintento: Polar devuelve sueño pero el nightly aún no está.
                sleep_store.upsert_sleep_row({"Fecha": "2026-11-06", "polar_sleep_duration_min": 450.0})
                out = pd.read_csv(sleep_path)
        self.assertEqual(len(out), 1)
        self.assertAlmostEqual(out.loc[0, "polar_sleep_duration_min"], 450.0)
        self.assertEqual(out.loc[0, "polar_ans_charge_status"], 1)

    def test_fetch_and_upsert_persists_ratings_from_both_endpoints(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            sleep_path = Path(tmpdir) / "ENDURANCE_HRV_sleep.csv"
            sleep_resp = {"outcome": "data_found", "data": {"sleep_duration": "PT7H", "sleep_charge_status": 2}}
            nightly_resp = {
                "outcome": "data_found",
                "data": {"heart_rate_variability_avg": 32, "nightly_recharge_status": 2, "ans_charge_status": 1},
            }
            with patch.object(sleep_store, "SLEEP_PATH", sleep_path), \
                    patch.object(sleep_store, "fetch_polar_sleep_result", return_value=sleep_resp), \
                    patch.object(sleep_store, "fetch_polar_nightly_recharge_result", return_value=nightly_resp):
                result = sleep_store.fetch_and_upsert_sleep_result("t", None, date(2026, 11, 6))
                out = pd.read_csv(sleep_path)
        self.assertEqual(result["status"], "ok")
        row = out.iloc[0]
        self.assertEqual(row["polar_sleep_charge_status"], 2)
        self.assertEqual(row["polar_recharge_status"], 2)
        self.assertEqual(row["polar_ans_charge_status"], 1)


class RecoveryClassificationTests(unittest.TestCase):
    def test_polar_codes_one_per_domain_and_recharge_only_as_fallback(self):
        row = pd.Series({"polar_ans_charge_status": 1, "polar_sleep_charge_status": 3, "polar_recharge_status": 2})
        support, caution, covered = final_builder._polar_recovery_codes(row)
        self.assertEqual(caution, ["polar_ans_low"])
        self.assertEqual(support, [])
        self.assertEqual(covered, {"autonomic": True, "sleep": True})

        only_recharge = pd.Series({"polar_recharge_status": 2})
        support, caution, covered = final_builder._polar_recovery_codes(only_recharge)
        self.assertEqual(caution, ["polar_recharge_poor"])
        self.assertTrue(covered["autonomic"] and covered["sleep"])

    def test_recharge_fills_partial_response_only_when_present_component_is_neutral(self):
        neutral_partial = pd.Series({"polar_ans_charge_status": 3, "polar_recharge_status": 1})
        support, caution, covered = final_builder._polar_recovery_codes(neutral_partial)
        self.assertEqual((support, caution), ([], ["polar_recharge_poor"]))
        self.assertEqual(covered, {"autonomic": True, "sleep": True})

        coded_partial = pd.Series({"polar_ans_charge_status": 1, "polar_recharge_status": 1})
        support, caution, covered = final_builder._polar_recovery_codes(coded_partial)
        self.assertEqual(caution, ["polar_ans_low"])  # sin doble conteo
        self.assertEqual(covered, {"autonomic": True, "sleep": False})

        both_neutral = pd.Series({"polar_ans_charge_status": 3, "polar_sleep_charge_status": 3, "polar_recharge_status": 1})
        self.assertEqual(final_builder._polar_recovery_codes(both_neutral)[:2], ([], []))

    def test_unknown_codes_are_not_interpreted(self):
        row = pd.Series({"polar_ans_charge_status": 9, "polar_sleep_charge_status": 2.5, "polar_recharge_status": 0})
        support, caution, covered = final_builder._polar_recovery_codes(row)
        self.assertEqual((support, caution), ([], []))
        self.assertEqual(covered, {"autonomic": False, "sleep": False})

    def test_absence_of_basic_alert_is_not_favorable_evidence(self):
        cls, discordant = final_builder._classify_recovery_support(
            gate=final_builder.ROJO, coverage="basic", support_codes=["sleep_basic_ok"], caution_codes=[]
        )
        self.assertEqual((cls, discordant), ("neutral", False))
        cls, _ = final_builder._classify_recovery_support(
            gate=final_builder.AMBAR, coverage="basic", support_codes=["sleep_basic_ok"], caution_codes=[]
        )
        self.assertEqual(cls, "neutral")

    def test_favorable_polar_night_with_red_is_mixed_and_names_component(self):
        cls, discordant = final_builder._classify_recovery_support(
            gate=final_builder.ROJO, coverage="rich",
            support_codes=["sleep_basic_ok", "polar_sleep_charge_high"], caution_codes=[],
        )
        self.assertEqual((cls, discordant), ("conflicted", True))
        msg = final_builder._recovery_summary_message(
            final_builder.ROJO, cls, ["sleep_basic_ok", "polar_sleep_charge_high"], []
        )
        self.assertEqual(msg, "ROJO, pero señal mixta: carga de sueño de Polar por encima de lo habitual")


def _core_with_red_tail() -> pd.DataFrame:
    dates = pd.date_range("2026-01-01", periods=40, freq="D")
    rows = []
    for idx, fecha in enumerate(dates):
        lnrmssd = 3.70 + (0.03 if idx % 2 == 0 else -0.03)
        rows.append(
            {
                "Fecha": fecha.strftime("%Y-%m-%d"),
                "Calidad": "OK",
                "HRV_Stability": "OK",
                "Artifact_pct": 0.0,
                "Tiempo_Estabilizacion": 60.0,
                "lnRMSSD": lnrmssd,
                "HR_stable": 50.0 + [0.0, 0.7, -0.6][idx % 3],
                "RMSSD_stable": float(np.exp(lnrmssd)),
                "RRbar_s": 1.10,
            }
        )
    core = pd.DataFrame(rows)
    for idx in (-4, -3, -2):
        core.loc[len(core) + idx, "lnRMSSD"] = 3.45
        core.loc[len(core) + idx, "RMSSD_stable"] = float(np.exp(3.45))
        core.loc[len(core) + idx, "HR_stable"] = 54.5
    return core


class FinalEndToEndTests(unittest.TestCase):
    TARGET = "2026-02-08"
    BASE_SLEEP = {
        "Fecha": "2026-02-08",
        "polar_sleep_duration_min": 449.5,
        "polar_interruptions_long": 7,
        "polar_sleep_score": 68.6,
        "polar_night_rmssd": 32.0,
        "sleep_dur_p10": 356.15,
        "sleep_int_p90": 7.6,
    }

    def _build(self, sleep_row):
        with tempfile.TemporaryDirectory() as tmpdir:
            data_dir = Path(tmpdir)
            pd.DataFrame([sleep_row]).to_csv(data_dir / "ENDURANCE_HRV_sleep.csv", index=False)
            pd.DataFrame(
                [{"Fecha": self.TARGET, "load_day": 80, "load_3d": 150, "load_3d_nobs": 3}]
            ).to_csv(data_dir / "ENDURANCE_HRV_sessions_day.csv", index=False)
            with patch.object(final_builder, "DATA_DIR", data_dir):
                final, _ = final_builder.build_final_and_dashboard(_core_with_red_tail(), final_builder.Config())
        return final.loc[final["Fecha"] == self.TARGET].iloc[0]

    def test_red_without_ratings_no_longer_reports_favorable_discordance(self):
        row = self._build(self.BASE_SLEEP)
        self.assertEqual(row["gate_final"], final_builder.ROJO)
        self.assertNotEqual(row["recovery_support_class"], "conflicted")
        self.assertFalse(bool(row["recovery_discordance_flag"]))
        self.assertNotIn("sleep_basic_ok", str(row["recovery_discordance_reason"]))

    def test_red_with_unfavorable_polar_ratings_is_coherent(self):
        row = self._build(
            self.BASE_SLEEP | {"polar_recharge_status": 2, "polar_ans_charge_status": 1, "polar_sleep_charge_status": 2}
        )
        self.assertEqual(row["gate_final"], final_builder.ROJO)
        self.assertEqual(row["recovery_support_class"], "supported")
        self.assertFalse(bool(row["recovery_discordance_flag"]))
        self.assertEqual(row["recovery_context_quality"], "rich")
        self.assertIn("estado del SNA nocturno de Polar por debajo de lo habitual", row["reason_text"])
        self.assertIn("carga de sueño de Polar por debajo de lo habitual", row["reason_text"])

    def test_gate_is_unchanged_by_polar_ratings(self):
        base = self._build(self.BASE_SLEEP)
        rated = self._build(self.BASE_SLEEP | {"polar_ans_charge_status": 5, "polar_sleep_charge_status": 5})
        for col in ("gate_final", "gate_raw_today", "Action", "Action_detail"):
            if col in base.index:
                self.assertEqual(base[col], rated[col], col)
        self.assertEqual(rated["recovery_support_class"], "conflicted")
        self.assertIn("ROJO, pero señal mixta", rated["reason_text"])


class DailyBriefPayloadTests(unittest.TestCase):
    def test_payload_exposes_polar_ratings_with_labels_and_date(self):
        sleep_row = pd.Series(
            {
                "Fecha": date(2026, 11, 6),
                "polar_recharge_status": 2.0,
                "polar_ans_charge_status": 1.0,
                "polar_sleep_charge_status": 7.0,
                "polar_ans_charge": -7.5,
            }
        )
        block = daily_brief._polar_nightly_recharge(sleep_row, date(2026, 11, 6))
        self.assertTrue(block["available"])
        self.assertEqual(block["sleep_date"], "2026-11-06")
        self.assertEqual(block["recharge_status"]["label"], "mala")
        self.assertEqual(block["ans_charge_status"]["label"], "muy por debajo de lo habitual")
        self.assertEqual(block["sleep_charge_status"]["label"], "codigo_desconocido")
        self.assertEqual(block["polar_ans_charge"], -7.5)

    def test_payload_marks_ratings_unavailable_for_legacy_rows(self):
        block = daily_brief._polar_nightly_recharge(
            pd.Series({"Fecha": date(2026, 11, 5), "polar_sleep_score": 70.0}), date(2026, 11, 5)
        )
        self.assertFalse(block["available"])
        self.assertEqual(block["unavailable_reason"], "no_polar_ratings")
        self.assertNotIn("recharge_status", block)

    def test_payload_hides_ratings_from_a_previous_night(self):
        # Hoy falta sueño; la última fila es de ayer y trae valoraciones.
        yesterday = pd.Series(
            {
                "Fecha": date(2026, 11, 5),
                "polar_recharge_status": 5.0,
                "polar_ans_charge_status": 4.0,
                "polar_sleep_charge_status": 4.0,
            }
        )
        block = daily_brief._polar_nightly_recharge(yesterday, date(2026, 11, 6))
        self.assertFalse(block["available"])
        self.assertEqual(block["unavailable_reason"], "no_sleep_row_for_target_date")
        self.assertEqual(block["sleep_date"], "2026-11-05")
        for key in ("recharge_status", "ans_charge_status", "sleep_charge_status"):
            self.assertNotIn(key, block)

    def test_build_payload_does_not_present_previous_night_sleep_as_current(self):
        final_row = pd.Series({"Fecha": date(2026, 11, 6), "gate_final": "ROJO"})
        yesterday = pd.Series(
            {
                "Fecha": date(2026, 11, 5),
                "polar_sleep_charge_status": 1.0,
                "polar_sleep_score": 50.0,
                "polar_sleep_duration_min": 300.0,
            }
        )
        payload = daily_brief._build_payload(final_row, yesterday, None, [])
        sleep = payload["sleep_context"]
        self.assertFalse(sleep["sleep_for_target_date"])
        self.assertEqual(sleep["sleep_date"], "2026-11-05")
        self.assertEqual(sleep["classification"], "not_available")
        self.assertNotIn("polar_sleep_score", sleep)
        self.assertNotIn("polar_sleep_duration_min", sleep)
        self.assertFalse(sleep["sleep_duration_anomaly"]["flag"])
        self.assertFalse(sleep["polar_nightly_recharge"]["available"])

    def test_build_payload_same_night_keeps_sleep_fields(self):
        final_row = pd.Series({"Fecha": date(2026, 11, 6), "gate_final": "ROJO"})
        tonight = pd.Series({"Fecha": date(2026, 11, 6), "polar_sleep_score": 50.0})
        sleep = daily_brief._build_payload(final_row, tonight, None, [])["sleep_context"]
        self.assertTrue(sleep["sleep_for_target_date"])
        self.assertEqual(sleep["polar_sleep_score"], 50.0)
        self.assertEqual(sleep["classification"], "red")

    def test_only_unknown_codes_are_not_available(self):
        row = pd.Series(
            {
                "Fecha": date(2026, 11, 6),
                "polar_recharge_status": 9.0,
                "polar_ans_charge_status": 0.0,
                "polar_sleep_charge_status": 2.5,
            }
        )
        block = daily_brief._polar_nightly_recharge(row, date(2026, 11, 6))
        self.assertFalse(block["available"])
        self.assertEqual(block["unavailable_reason"], "only_unknown_codes")
        self.assertEqual(block["recharge_status"]["label"], "codigo_desconocido")

    def test_low_sleep_charge_classifies_sleep_as_amber(self):
        cls, text = daily_brief._classify_sleep(pd.Series({"polar_sleep_charge_status": 2.0, "polar_sleep_score": 70.0}), [])
        self.assertEqual(cls, "amber")
        self.assertIn("por debajo de lo habitual", text)

    def test_very_low_sleep_charge_with_poor_score_is_red(self):
        cls, text = daily_brief._classify_sleep(pd.Series({"polar_sleep_charge_status": 1.0, "polar_sleep_score": 50.0}), [])
        self.assertEqual(cls, "red")
        self.assertIn("muy por debajo de lo habitual", text)

    def test_favourable_sleep_charge_replaces_absolute_score_threshold(self):
        # Igual que en FINAL: la valoración relativa manda sobre el umbral de 65.
        cls, _ = daily_brief._classify_sleep(pd.Series({"polar_sleep_charge_status": 4.0, "polar_sleep_score": 60.0}), [])
        self.assertEqual(cls, "green")

    def test_without_rating_absolute_score_threshold_still_applies(self):
        cls, _ = daily_brief._classify_sleep(pd.Series({"polar_sleep_score": 60.0}), [])
        self.assertEqual(cls, "red")
        cls, _ = daily_brief._classify_sleep(pd.Series({"polar_sleep_charge_status": 7.0, "polar_sleep_score": 60.0}), [])
        self.assertEqual(cls, "red")  # código fuera de escala: se usa el umbral

    def test_favourable_sleep_charge_keeps_duration_caution(self):
        row = pd.Series({"polar_sleep_charge_status": 4.0, "polar_sleep_duration_min": 300.0, "sleep_dur_p10": 360.0})
        cls, _ = daily_brief._classify_sleep(row, [])
        self.assertEqual(cls, "amber")


def _load_backfill_script():
    path = Path(__file__).resolve().parent.parent / "scripts" / "backfill_polar_nightly_ratings.py"
    spec = importlib.util.spec_from_file_location("backfill_polar_nightly_ratings", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _FakeV4Client:
    calls: list = []

    def __init__(self, bundle_path=None):
        pass

    def fetch_nightly_recharges(self, start, end, features=None):
        _FakeV4Client.calls.append(("nightly", start, end))
        return {"nightlyRechargeResults": [
            {"sleepResultDate": start, "recoveryIndicator": 1, "recoveryIndicatorSubLevel": 38,
             "ansStatus": -8.56, "ansRate": 1, "meanNightlyRecoveryRmssd": 32}
        ]}

    def fetch_sleeps(self, start, end, features=None):
        _FakeV4Client.calls.append(("sleep", start, end))
        return {"nightSleeps": [{"sleepDate": start, "sleepScore": {"sleepScore": 68.6, "scoreRate": 1}}]}


class BackfillScriptTests(unittest.TestCase):
    def test_candidates_include_partial_ratings(self):
        script = _load_backfill_script()
        df = pd.DataFrame(
            [
                {"Fecha": "2026-03-14", "polar_sleep_score": 80.0, "polar_recharge_status": 4,
                 "polar_ans_charge_status": 3, "polar_sleep_charge_status": 3},
                {"Fecha": "2026-03-15", "polar_sleep_score": 80.0, "polar_sleep_charge_status": 3},
                {"Fecha": "2026-03-16", "polar_night_rmssd": 30.0},
                {"Fecha": "2026-03-17"},
            ]
        ).reindex(columns=sleep_store.SLEEP_COLUMNS)
        self.assertEqual(script.candidate_dates(df, None, False), ["2026-03-15", "2026-03-16"])
        self.assertEqual(len(script.candidate_dates(df, None, True)), 3)

    def test_backfill_fills_only_rating_columns_and_is_idempotent(self):
        script = _load_backfill_script()
        legacy = pd.DataFrame(
            [
                {"Fecha": "2026-11-05", "polar_sleep_duration_min": 400.0},
                {"Fecha": "2026-11-06", "polar_sleep_duration_min": 420.0, "polar_night_rmssd": 32.0,
                 "polar_sleep_score": 68.6},
            ]
        ).reindex(columns=sleep_store.SLEEP_LEGACY_COLUMNS)
        with tempfile.TemporaryDirectory() as tmpdir:
            sleep_path = Path(tmpdir) / "ENDURANCE_HRV_sleep.csv"
            legacy.to_csv(sleep_path, index=False)
            _FakeV4Client.calls = []
            with patch.object(sleep_store, "SLEEP_PATH", sleep_path),                     patch.object(script, "V4Client", _FakeV4Client),                     patch.object(script, "index_by_date", side_effect=_index_fake):
                self.assertEqual(script.main(["--dry-run"]), 0)
                self.assertEqual(_FakeV4Client.calls, [])
                self.assertEqual(script.main([]), 0)
                out = pd.read_csv(sleep_path)
                first_calls = list(_FakeV4Client.calls)
                self.assertEqual(script.main([]), 0)  # nada pendiente: no consulta
                self.assertEqual(_FakeV4Client.calls, first_calls)
            backups = list((Path(tmpdir) / "backup" / "pre_nightly_ratings").glob("*.csv"))
        self.assertEqual(list(out.columns), sleep_store.SLEEP_COLUMNS)
        self.assertEqual(len(out), 2)
        self.assertEqual({c[1] for c in first_calls}, {"2026-11-06"})
        row = out.set_index("Fecha").loc["2026-11-06"]
        self.assertEqual(row["polar_recharge_status"], 1)
        self.assertEqual(row["polar_ans_charge_status"], 1)
        self.assertEqual(row["polar_sleep_charge_status"], 1)
        self.assertAlmostEqual(row["polar_sleep_duration_min"], 420.0)
        self.assertTrue(out.set_index("Fecha").loc["2026-11-05", sleep_store.SLEEP_COLUMNS[17:]].isna().all())
        self.assertEqual(len(backups), 1)


def _index_fake(payload):
    items = payload.get("nightlyRechargeResults") or payload.get("nightSleeps") or []
    return {it.get("sleepResultDate") or it.get("sleepDate"): it for it in items}


if __name__ == "__main__":
    unittest.main()
