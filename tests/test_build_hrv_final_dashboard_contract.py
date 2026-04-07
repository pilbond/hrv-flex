import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import numpy as np
import pandas as pd

import build_hrv_final_dashboard as final_builder


def _core_frame() -> pd.DataFrame:
    dates = pd.date_range("2026-01-01", periods=40, freq="D")
    rows = []
    for idx, fecha in enumerate(dates):
        lnrmssd = 3.70 + (0.03 if idx % 2 == 0 else -0.03)
        hr_stable = 50.0 + [0.0, 0.7, -0.6][idx % 3]
        rrbar_s = 1.10 + [0.00, 0.01, -0.01, 0.02][idx % 4]
        rows.append(
            {
                "Fecha": fecha.strftime("%Y-%m-%d"),
                "Calidad": "OK",
                "HRV_Stability": "OK",
                "Artifact_pct": 0.0,
                "Tiempo_Estabilizacion": 60.0,
                "lnRMSSD": lnrmssd,
                "HR_stable": hr_stable,
                "RMSSD_stable": float(np.exp(lnrmssd)),
                "RRbar_s": rrbar_s,
            }
        )
    return pd.DataFrame(rows)


class BuildFinalDashboardContractTests(unittest.TestCase):
    def test_reason_text_adds_clustering_warning_on_ffill_window(self):
        core = _core_frame()

        with TemporaryDirectory() as tmpdir:
            data_dir = Path(tmpdir)
            pd.DataFrame(
                [
                    {
                        "Fecha": "2026-02-07",
                        "intense_days_prev_3d": 2,
                        "intense_days_prev_5d": 3,
                        "intensity_clustering_flag": 1,
                        "intensity_clustering_level": "high",
                    }
                ]
            ).to_csv(data_dir / "ENDURANCE_HRV_sessions_day.csv", index=False)

            with patch.object(final_builder, "DATA_DIR", data_dir):
                final, _ = final_builder.build_final_and_dashboard(core, final_builder.Config())

        row = final.loc[final["Fecha"] == "2026-02-08"].iloc[0]
        self.assertEqual(row["gate_final"], "VERDE")
        self.assertIn(
            "VERDE pero clustering alto de intensidad reciente: considera Z1 mañana (2/3d · 3/5d)",
            row["reason_text"],
        )


if __name__ == "__main__":
    unittest.main()
