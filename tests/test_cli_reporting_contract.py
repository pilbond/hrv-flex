import contextlib
import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd

import cli_reporting


class CliReportingContractTests(unittest.TestCase):
    def test_show_last_daily_summary_prefers_final(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            final_path = tmp_path / "ENDURANCE_HRV_master_FINAL.csv"
            core_path = tmp_path / "ENDURANCE_HRV_master_CORE.csv"

            pd.DataFrame(
                [
                    {
                        "Fecha": "2024-01-01",
                        "HR_today": 51.2,
                        "RMSSD_stable": 42.8,
                        "gate_badge": "VERDE",
                        "Action": "seguir",
                        "gate_razon_base60": "ok",
                        "Calidad": "A",
                        "HRV_Stability": "Alta",
                        "baseline60_degraded": False,
                    }
                ]
            ).to_csv(final_path, index=False)

            pd.DataFrame(
                [
                    {
                        "Fecha": "2024-01-01",
                        "HR_stable": 60.0,
                        "RMSSD_stable": 30.0,
                        "Calidad": "B",
                        "HRV_Stability": "Media",
                    }
                ]
            ).to_csv(core_path, index=False)

            buffer = io.StringIO()
            with (
                patch.object(cli_reporting, "FINAL_PATH", final_path),
                patch.object(cli_reporting, "CORE_PATH", core_path),
                patch.object(cli_reporting, "PANDAS_AVAILABLE", True),
                contextlib.redirect_stdout(buffer),
            ):
                cli_reporting.show_last_daily_summary()

            output = buffer.getvalue()
            self.assertIn("Última Medición HRV (V4)", output)
            self.assertIn("📅 Fecha:          2024-01-01", output)
            self.assertIn("💓 HR hoy:         51.2 bpm", output)
            self.assertIn("🚦 Gate:           🟢 VERDE", output)
            self.assertNotIn("HR promedio", output)

    def test_show_last_daily_summary_falls_back_to_core(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            final_path = tmp_path / "missing_final.csv"
            core_path = tmp_path / "ENDURANCE_HRV_master_CORE.csv"

            pd.DataFrame(
                [
                    {
                        "Fecha": "2024-01-02",
                        "HR_stable": 59.1,
                        "RMSSD_stable": 31.4,
                        "Calidad": "B",
                        "HRV_Stability": "Media",
                        "Flags": "test-flag",
                    }
                ]
            ).to_csv(core_path, index=False)

            buffer = io.StringIO()
            with (
                patch.object(cli_reporting, "FINAL_PATH", final_path),
                patch.object(cli_reporting, "CORE_PATH", core_path),
                patch.object(cli_reporting, "PANDAS_AVAILABLE", True),
                contextlib.redirect_stdout(buffer),
            ):
                cli_reporting.show_last_daily_summary()

            output = buffer.getvalue()
            self.assertIn("Última Medición HRV (CORE)", output)
            self.assertIn("💓 HR promedio:    59.1 bpm", output)
            self.assertIn("🚩 Flags:          test-flag", output)


if __name__ == "__main__":
    unittest.main()
