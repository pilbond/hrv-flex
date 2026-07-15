import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

import pandas as pd

import hrv_app.sleep_store as sleep_store


class SleepStoreContractTests(unittest.TestCase):
    def test_ensure_sleep_schema_adds_missing_columns_in_canonical_order(self):
        df = pd.DataFrame([{"Fecha": "2026-03-01", "polar_sleep_duration_min": 360}])

        out = sleep_store._ensure_sleep_schema(df)

        self.assertEqual(list(out.columns), sleep_store.SLEEP_COLUMNS)
        self.assertEqual(out.loc[0, "Fecha"], "2026-03-01")
        self.assertTrue(pd.isna(out.loc[0, "sleep_dur_p10"]))

    def test_recalculate_sleep_derived_computes_percentiles_and_efficiency(self):
        df = pd.DataFrame(
            [
                {
                    "Fecha": "2026-03-02",
                    "polar_sleep_duration_min": 360,
                    "polar_sleep_span_min": 400,
                    "polar_night_resp": 6000,
                    "polar_interruptions_long": 3,
                }
            ]
        )

        out = sleep_store._recalculate_sleep_derived(df)

        self.assertAlmostEqual(out.loc[0, "polar_efficiency_pct"], 90.0)
        self.assertAlmostEqual(out.loc[0, "sleep_dur_p10"], 360.0)
        self.assertAlmostEqual(out.loc[0, "sleep_dur_p90"], 360.0)
        self.assertAlmostEqual(out.loc[0, "sleep_int_p90"], 3.0)
        self.assertAlmostEqual(out.loc[0, "polar_night_resp"], 10.0)

    def test_upsert_sleep_row_replaces_existing_date(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            sleep_path = Path(tmpdir) / "ENDURANCE_HRV_sleep.csv"
            with patch.object(sleep_store, "SLEEP_PATH", sleep_path):
                self.assertTrue(
                    sleep_store.upsert_sleep_row(
                        {
                            "Fecha": "2026-03-03",
                            "polar_sleep_duration_min": 300,
                            "polar_sleep_span_min": 330,
                        }
                    )
                )
                self.assertTrue(
                    sleep_store.upsert_sleep_row(
                        {
                            "Fecha": "2026-03-03",
                            "polar_sleep_duration_min": 360,
                            "polar_sleep_span_min": 400,
                        }
                    )
                )

                out = pd.read_csv(sleep_path)

        self.assertEqual(len(out), 1)
        self.assertEqual(out.loc[0, "Fecha"], "2026-03-03")
        self.assertAlmostEqual(out.loc[0, "polar_sleep_duration_min"], 360.0)
        self.assertAlmostEqual(out.loc[0, "polar_sleep_span_min"], 400.0)

    def test_fetch_and_upsert_sleep_uses_previous_day_fallback(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            sleep_path = Path(tmpdir) / "ENDURANCE_HRV_sleep.csv"

            def fake_sleep(_token, _user_id, candidate_date):
                if candidate_date == "2026-03-03":
                    return {}
                if candidate_date == "2026-03-02":
                    return {
                        "sleepDuration": "PT6H",
                        "sleepSpan": "PT6H30M",
                        "deepSleep": "PT1H",
                        "remSleep": "PT2H",
                        "lightSleep": "PT3H",
                    }
                return {}

            def fake_nightly(_token, _user_id, candidate_date):
                if candidate_date == "2026-03-03":
                    return {}
                if candidate_date == "2026-03-02":
                    return {
                        "heart_rate_variability_avg": 41,
                        "breathing_rate_avg": 6000,
                    }
                return {}

            with patch.object(sleep_store, "SLEEP_PATH", sleep_path), patch.object(
                sleep_store, "fetch_polar_sleep", side_effect=fake_sleep
            ) as sleep_mock, patch.object(
                sleep_store, "fetch_polar_nightly_recharge", side_effect=fake_nightly
            ) as nightly_mock:
                self.assertTrue(sleep_store.fetch_and_upsert_sleep("token", "user", date(2026, 3, 3)))

                out = pd.read_csv(sleep_path)

        self.assertGreaterEqual(sleep_mock.call_count, 2)
        self.assertGreaterEqual(nightly_mock.call_count, 2)
        self.assertEqual(len(out), 1)
        self.assertEqual(out.loc[0, "Fecha"], "2026-03-03")
        self.assertAlmostEqual(out.loc[0, "polar_sleep_duration_min"], 360.0)
        self.assertAlmostEqual(out.loc[0, "polar_sleep_span_min"], 390.0)
        self.assertAlmostEqual(out.loc[0, "polar_night_rmssd"], 41.0)
        self.assertAlmostEqual(out.loc[0, "polar_night_resp"], 10.0)

    def test_fetch_and_upsert_sleep_v4_queries_gateway_without_user_id(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            sleep_path = Path(tmpdir) / "ENDURANCE_HRV_sleep.csv"

            def fake_sleep(_token, _user_id, candidate_date):
                if candidate_date == "2026-03-03":
                    return {"sleep_duration": "PT6H"}
                return {}

            def fake_nightly(_token, _user_id, candidate_date):
                return {}

            with patch.object(sleep_store, "SLEEP_PATH", sleep_path), \
                    patch.object(sleep_store, "fetch_polar_sleep", side_effect=fake_sleep) as sleep_mock, \
                    patch.object(sleep_store, "fetch_polar_nightly_recharge", side_effect=fake_nightly) as nightly_mock:
                self.assertTrue(sleep_store.fetch_and_upsert_sleep("ignored", None, date(2026, 3, 3)))

        sleep_mock.assert_any_call("ignored", None, "2026-03-03")
        nightly_mock.assert_any_call("ignored", None, "2026-03-03")

    def test_update_sleep_for_dates_deduplicates_dates(self):
        calls = []

        def fake_fetch(token, user_id, processed_date):
            calls.append(processed_date)
            return True

        with patch.object(sleep_store, "fetch_and_upsert_sleep", side_effect=fake_fetch):
            done = sleep_store._update_sleep_for_dates(
                "token",
                "user",
                [date(2026, 3, 4), date(2026, 3, 4), date(2026, 3, 5), None],
            )

        self.assertEqual(done, 2)
        self.assertEqual(calls, [date(2026, 3, 4), date(2026, 3, 5)])


class SleepStoreFailClosedTests(unittest.TestCase):
    def test_corrupt_sleep_csv_raises_and_quarantines(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            sleep_path = Path(tmpdir) / "ENDURANCE_HRV_sleep.csv"
            sleep_path.write_bytes(b"\xff corrupt \x00")
            original_bytes = sleep_path.read_bytes()

            with patch.object(sleep_store, "SLEEP_PATH", sleep_path):
                with self.assertRaises(RuntimeError) as ctx:
                    sleep_store.upsert_sleep_row({"Fecha": "2026-07-14", "polar_sleep_duration_min": 360})

            self.assertIn("FAIL-CLOSED", str(ctx.exception))
            # original bytes preserved
            self.assertEqual(sleep_path.read_bytes(), original_bytes)
            # quarantine created with original content
            quarantine_files = list(Path(tmpdir).glob("ENDURANCE_HRV_sleep.csv.corrupt.*"))
            self.assertEqual(len(quarantine_files), 1)
            self.assertEqual(quarantine_files[0].read_bytes(), original_bytes)

    def test_empty_sleep_csv_raises_and_quarantines(self):
        """Un sleep.csv existente pero vacío debe fallar con cuarentena, no sobrescribirse."""
        with tempfile.TemporaryDirectory() as tmpdir:
            sleep_path = Path(tmpdir) / "ENDURANCE_HRV_sleep.csv"
            sleep_path.write_bytes(b"")
            original_bytes = sleep_path.read_bytes()

            with patch.object(sleep_store, "SLEEP_PATH", sleep_path):
                with self.assertRaises(RuntimeError) as ctx:
                    sleep_store.upsert_sleep_row({"Fecha": "2026-07-14", "polar_sleep_duration_min": 360})

            self.assertIn("FAIL-CLOSED", str(ctx.exception))
            self.assertEqual(sleep_path.read_bytes(), original_bytes)
            quarantine_files = list(Path(tmpdir).glob("ENDURANCE_HRV_sleep.csv.corrupt.*"))
            self.assertEqual(len(quarantine_files), 1)

    def test_invalid_schema_sleep_csv_raises_and_quarantines(self):
        """Un sleep.csv legible pero sin columnas canónicas debe fallar con cuarentena."""
        with tempfile.TemporaryDirectory() as tmpdir:
            sleep_path = Path(tmpdir) / "ENDURANCE_HRV_sleep.csv"
            sleep_path.write_text("garbage\nfoo\n", encoding="utf-8")
            original_bytes = sleep_path.read_bytes()

            with patch.object(sleep_store, "SLEEP_PATH", sleep_path):
                with self.assertRaises(RuntimeError) as ctx:
                    sleep_store.upsert_sleep_row({"Fecha": "2026-07-14", "polar_sleep_duration_min": 360})

            self.assertIn("FAIL-CLOSED", str(ctx.exception))
            self.assertEqual(sleep_path.read_bytes(), original_bytes)
            quarantine_files = list(Path(tmpdir).glob("ENDURANCE_HRV_sleep.csv.corrupt.*"))
            self.assertEqual(len(quarantine_files), 1)

    def test_truncated_sleep_csv_only_fecha_raises_and_quarantines(self):
        """Un sleep.csv con solo 'Fecha' (truncado) debe fallar, no rellenarse con NaN."""
        with tempfile.TemporaryDirectory() as tmpdir:
            sleep_path = Path(tmpdir) / "ENDURANCE_HRV_sleep.csv"
            sleep_path.write_text("Fecha\n2026-07-14\n", encoding="utf-8")
            original_bytes = sleep_path.read_bytes()

            with patch.object(sleep_store, "SLEEP_PATH", sleep_path):
                with self.assertRaises(RuntimeError) as ctx:
                    sleep_store.upsert_sleep_row({"Fecha": "2026-07-14", "polar_sleep_duration_min": 360})

            self.assertIn("FAIL-CLOSED", str(ctx.exception))
            self.assertIn("polar_sleep_duration_min", str(ctx.exception))
            self.assertEqual(sleep_path.read_bytes(), original_bytes)
            quarantine_files = list(Path(tmpdir).glob("ENDURANCE_HRV_sleep.csv.corrupt.*"))
            self.assertEqual(len(quarantine_files), 1)

    def test_unexpected_sleep_column_raises_and_quarantines(self):
        """Una columna ajena al contrato debe bloquear la actualización de sleep."""
        with tempfile.TemporaryDirectory() as tmpdir:
            sleep_path = Path(tmpdir) / "ENDURANCE_HRV_sleep.csv"
            header = ",".join(sleep_store.SLEEP_COLUMNS + ["extra"]) + "\n"
            row = ",".join(["2026-07-13"] + [""] * (len(sleep_store.SLEEP_COLUMNS) - 1) + ["valor"]) + "\n"
            sleep_path.write_text(header + row, encoding="utf-8")
            original_bytes = sleep_path.read_bytes()

            with patch.object(sleep_store, "SLEEP_PATH", sleep_path):
                with self.assertRaises(RuntimeError) as ctx:
                    sleep_store.upsert_sleep_row({"Fecha": "2026-07-14"})

            self.assertIn("columnas no canónicas", str(ctx.exception))
            self.assertEqual(sleep_path.read_bytes(), original_bytes)
            quarantine_files = list(Path(tmpdir).glob("ENDURANCE_HRV_sleep.csv.corrupt.*"))
            self.assertEqual(len(quarantine_files), 1)

    def test_header_only_sleep_csv_raises_and_quarantines(self):
        """Cabecera completa pero sin filas debe fallar con cuarentena."""
        with tempfile.TemporaryDirectory() as tmpdir:
            sleep_path = Path(tmpdir) / "ENDURANCE_HRV_sleep.csv"
            header = ",".join(sleep_store.SLEEP_COLUMNS) + "\n"
            sleep_path.write_text(header, encoding="utf-8")
            original_bytes = sleep_path.read_bytes()

            with patch.object(sleep_store, "SLEEP_PATH", sleep_path):
                with self.assertRaises(RuntimeError) as ctx:
                    sleep_store.upsert_sleep_row({"Fecha": "2026-07-14", "polar_sleep_duration_min": 360})

            self.assertIn("FAIL-CLOSED", str(ctx.exception))
            self.assertEqual(sleep_path.read_bytes(), original_bytes)
            quarantine_files = list(Path(tmpdir).glob("ENDURANCE_HRV_sleep.csv.corrupt.*"))
            self.assertEqual(len(quarantine_files), 1)

    def test_all_nan_row_sleep_csv_raises_and_quarantines(self):
        """Una fila con cabecera correcta pero solo valores vacíos debe fallar, no publicarse."""
        with tempfile.TemporaryDirectory() as tmpdir:
            sleep_path = Path(tmpdir) / "ENDURANCE_HRV_sleep.csv"
            header = ",".join(sleep_store.SLEEP_COLUMNS) + "\n"
            blank_row = "," * (len(sleep_store.SLEEP_COLUMNS) - 1) + "\n"
            sleep_path.write_text(header + blank_row, encoding="utf-8")
            original_bytes = sleep_path.read_bytes()

            with patch.object(sleep_store, "SLEEP_PATH", sleep_path):
                with self.assertRaises(RuntimeError) as ctx:
                    sleep_store.upsert_sleep_row({"Fecha": "2026-07-14", "polar_sleep_duration_min": 360})

            self.assertIn("FAIL-CLOSED", str(ctx.exception))
            self.assertEqual(sleep_path.read_bytes(), original_bytes)
            quarantine_files = list(Path(tmpdir).glob("ENDURANCE_HRV_sleep.csv.corrupt.*"))
            self.assertEqual(len(quarantine_files), 1)

    def test_upsert_sleep_row_calls_write_csv_atomic(self):
        """write_csv_atomic debe usarse en vez de una escritura directa."""
        with tempfile.TemporaryDirectory() as tmpdir:
            sleep_path = Path(tmpdir) / "ENDURANCE_HRV_sleep.csv"
            with patch.object(sleep_store, "SLEEP_PATH", sleep_path), \
                 patch("hrv_app.sleep_store.write_csv_atomic", wraps=sleep_store.write_csv_atomic) as mock_write:
                sleep_store.upsert_sleep_row({"Fecha": "2026-07-14", "polar_sleep_duration_min": 360})

            mock_write.assert_called_once()
            _, call_path = mock_write.call_args[0]
            self.assertEqual(call_path, sleep_path)


if __name__ == "__main__":
    unittest.main()
