import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import numpy as np
import pandas as pd

import build_hrv_ssm_outcome_battery as battery


def _core(n: int = 60) -> pd.DataFrame:
    dates = pd.date_range("2026-01-01", periods=n, freq="D")
    rng = np.random.default_rng(42)
    lnrmssd = 3.8 + 0.1 * np.sin(np.arange(n) / 7.0) + rng.normal(0, 0.05, n)
    return pd.DataFrame({"Fecha": [d.strftime("%Y-%m-%d") for d in dates], "lnRMSSD": lnrmssd})


def _ssm(n: int = 60) -> pd.DataFrame:
    dates = pd.date_range("2026-01-01", periods=n, freq="D")
    rng = np.random.default_rng(7)
    state = 3.8 + 0.08 * np.sin(np.arange(n) / 7.0) + rng.normal(0, 0.04, n)
    rolling = pd.Series(state).rolling(7, min_periods=1).mean().to_numpy()
    return pd.DataFrame(
        {
            "Fecha": [d.strftime("%Y-%m-%d") for d in dates],
            "ssm_warmup_complete": [idx >= 10 for idx in range(n)],
            "ssm_recovery_state": [state[i] if i >= 10 else np.nan for i in range(n)],
            "control_rolling_hrv_7d": rolling,
            "control_load_7d": [200 + i for i in range(n)],
        }
    )


def _wellness(n: int = 40) -> pd.DataFrame:
    dates = pd.date_range("2026-01-10", periods=n, freq="D")
    rng = np.random.default_rng(3)
    return pd.DataFrame(
        {
            "Fecha": [d.strftime("%Y-%m-%d") for d in dates],
            "well_fatigue_raw": rng.integers(1, 6, n).astype(float),
        }
    )


class OutcomeBatteryContractTests(unittest.TestCase):
    def test_build_outcome_battery_emits_expected_structure(self):
        report = battery.build_outcome_battery(
            pd.DataFrame(_core()).assign(Fecha=lambda df: pd.to_datetime(df["Fecha"])),
            pd.DataFrame(_ssm()).assign(Fecha=lambda df: pd.to_datetime(df["Fecha"])),
            pd.DataFrame(_wellness()).assign(Fecha=lambda df: pd.to_datetime(df["Fecha"])),
        )
        self.assertIn("outcomes", report)
        self.assertIn("battery_conclusion", report)
        self.assertIn("lnrmssd_next_day", report["outcomes"])
        block = report["outcomes"]["lnrmssd_next_day"]
        self.assertGreater(block["n_pairs"], 10)
        self.assertIn(block["verdict"], {"ssm_wins", "rolling_wins", "tied", "insufficient_data"})
        self.assertIn("evaluations", block)
        self.assertIn("ssm_goodness", block["evaluations"])
        self.assertIn("rolling_hrv_goodness", block["evaluations"])
        self.assertIn("ar1_baseline", block["evaluations"])
        self.assertIn("ewma_grid", block)
        self.assertIn("bootstrap_ssm_vs_rolling", block)
        self.assertIn(report["battery_conclusion"]["status"], {
            "ssm_wins_at_least_one_outcome", "no_ssm_advantage_across_outcomes", "mixed",
        })

    def test_build_outcome_battery_markdown_contains_key_sections(self):
        report = battery.build_outcome_battery(
            pd.DataFrame(_core()).assign(Fecha=lambda df: pd.to_datetime(df["Fecha"])),
            pd.DataFrame(_ssm()).assign(Fecha=lambda df: pd.to_datetime(df["Fecha"])),
            pd.DataFrame(_wellness()).assign(Fecha=lambda df: pd.to_datetime(df["Fecha"])),
        )
        md = battery.build_outcome_battery_markdown(report)
        self.assertIn("# Batería de Outcomes Alternativos", md)
        self.assertIn("## Conclusión", md)
        self.assertIn("lnRMSSD", md)
        self.assertIn("| Predictor |", md)
        self.assertIn("AR(1)", md)

    def test_main_writes_json_and_markdown(self):
        with TemporaryDirectory() as tmpdir:
            data_dir = Path(tmpdir)
            _core().to_csv(data_dir / "ENDURANCE_HRV_master_CORE.csv", index=False)
            _ssm().to_csv(data_dir / "ENDURANCE_HRV_ssm_shadow.csv", index=False)
            _wellness().to_csv(data_dir / "ENDURANCE_HRV_wellness_subjective.csv", index=False)
            output_dir = data_dir / "reports"
            exit_code = battery.main(["--data-dir", str(data_dir), "--output-dir", str(output_dir)])
            self.assertEqual(exit_code, 0)
            self.assertTrue((output_dir / "ENDURANCE_HRV_ssm_outcome_battery.json").exists())
            report = json.loads(
                (output_dir / "ENDURANCE_HRV_ssm_outcome_battery.json").read_text(encoding="utf-8")
            )
            self.assertEqual(report["source"], "build_hrv_ssm_outcome_battery.py")


if __name__ == "__main__":
    unittest.main()
