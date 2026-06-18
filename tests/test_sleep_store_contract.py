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


if __name__ == "__main__":
    unittest.main()
