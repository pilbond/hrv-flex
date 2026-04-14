import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd

import hrv_app.intervals_sync as intervals_sync


class IntervalsSyncContractTests(unittest.TestCase):
    def test_read_latest_master_row_picks_latest_date(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            master_path = Path(tmpdir) / "ENDURANCE_HRV_master_FINAL.csv"
            pd.DataFrame(
                [
                    {"Fecha": "2026-03-01", "HR_stable": 45},
                    {"Fecha": "2026-03-03", "HR_stable": 48},
                    {"Fecha": "2026-03-02", "HR_stable": 46},
                ]
            ).to_csv(master_path, index=False)

            row = intervals_sync._read_latest_master_row(master_path)

        self.assertIsNotNone(row)
        self.assertEqual(row["Fecha"], "2026-03-03")
        self.assertEqual(row["_date"], "2026-03-03")

    def test_build_intervals_payload_maps_colors_and_numbers(self):
        row = {
            "Fecha": "2026-03-03",
            "HR_stable": "48",
            "RMSSD_stable": "61.5",
            "cRMSSD": "70.2",
            "Color_Agudo_Diario": "Verde",
            "Color_Tendencia": "Amarillo",
            "Color_Tiebreak": "Rojo",
            "Calidad": "82",
            "HRV_Stability": "4",
        }

        payload = intervals_sync._build_intervals_payload(row)

        self.assertEqual(payload["CRMSSD"], 70.2)
        self.assertEqual(payload["HRPolar"], 48.0)
        self.assertEqual(payload["HRVScore"], 61.5)
        self.assertEqual(payload["ColorDiario"], 3)
        self.assertEqual(payload["ColorTendencia"], 2)
        self.assertEqual(payload["ColorTiebreak"], 1)

    def test_normalize_color_value_maps_na_to_indefinite_code(self):
        self.assertEqual(intervals_sync._normalize_color_value("n/a"), 0)

    def test_fetch_intervals_activities_uses_public_basic_auth_helper(self):
        class _Resp:
            def raise_for_status(self):
                return None

            def json(self):
                return {"activities": []}

        with patch.object(intervals_sync.requests, "get", return_value=_Resp()) as get_mock:
            self.assertEqual(intervals_sync.fetch_intervals_activities("secret", "athlete", "2026-03-01"), [])

        headers = get_mock.call_args.kwargs["headers"]
        self.assertEqual(headers["Authorization"], "Basic QVBJX0tFWTpzZWNyZXQ=")

    def test_activity_aggregation_extracts_numeric_context(self):
        payload = [
            {
                "icu_training_load": 42,
                "moving_time": 3600,
                "startDateLocal": "2026-03-01T07:30:00",
                "type": "Run",
            }
        ]

        out = intervals_sync._aggregate_intervals_activity_fields(payload)

        self.assertEqual(out["intervals_n_acts"], 1)
        self.assertEqual(out["intervals_load"], 42.0)
        self.assertEqual(out["intervals_duration_min"], 60.0)
        self.assertEqual(out["intervals_type_main"], "Run")

    def test_send_intervals_wellness_posts_latest_row(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            master_path = Path(tmpdir) / "ENDURANCE_HRV_master_FINAL.csv"
            pd.DataFrame(
                [
                    {
                        "Fecha": "2026-03-02",
                        "HR_stable": 45,
                        "RMSSD_stable": 61,
                        "cRMSSD": 70,
                        "Color_Agudo_Diario": "Verde",
                        "Color_Tendencia": "Amarillo",
                        "Color_Tiebreak": "Rojo",
                    }
                ]
            ).to_csv(master_path, index=False)

            class _Resp:
                ok = True
                status_code = 200

                def json(self):
                    return {"ok": True}

                @property
                def text(self):
                    return "ok"

            with patch.dict(
                "os.environ",
                {"INTERVALS_API_KEY": "secret", "INTERVALS_ATHLETE_ID": "athlete"},
                clear=False,
            ), patch.object(intervals_sync.requests, "put", return_value=_Resp()) as put_mock:
                intervals_sync._send_intervals_wellness_from_master(master_path)

        self.assertEqual(put_mock.call_args.args[0], "https://intervals.icu/api/v1/athlete/athlete/wellness/2026-03-02")
        self.assertEqual(put_mock.call_args.kwargs["json"]["CRMSSD"], 70.0)
        self.assertEqual(put_mock.call_args.kwargs["json"]["HRPolar"], 45.0)
        self.assertEqual(put_mock.call_args.kwargs["headers"]["Authorization"], "Basic QVBJX0tFWTpzZWNyZXQ=")


if __name__ == "__main__":
    unittest.main()
