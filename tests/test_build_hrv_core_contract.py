import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import build_hrv_core as core_builder


class BuildHrvCoreContractTests(unittest.TestCase):
    def test_main_writes_core_manifest_json(self):
        rr_row = "duration,offline\n1000,0\n1010,0\n"
        core_row = {
            "Fecha": "2026-02-08",
            "Calidad": "OK",
            "HRV_Stability": "OK",
            "Artifact_pct": 0.0,
            "Tiempo_Estabilizacion": 60.0,
            "Stability_Subtype": "OK",
            "tail_mismatch_pct": 0.0,
            "HR_stable": 52.0,
            "RRbar_s": 1.05,
            "RMSSD_stable": 45.0,
            "lnRMSSD": 3.81,
            "Flags": "",
            "SI_baevsky": 12.0,
            "SD1": 10.0,
            "SD2": 20.0,
            "SD1_SD2_ratio": 0.5,
            "Notes": "",
        }
        beta_row = {
            "Fecha": "2026-02-08",
            "HR_stable": 52.0,
            "RRbar_s": 1.05,
            "RMSSD_stable": 45.0,
            "lnRMSSD": 3.81,
            "cRMSSD": 44.0,
            "beta_mode": "test",
            "beta_est_90d": 1.0,
            "beta_use_90d": 1.0,
            "R2_winsor_90d": 0.9,
            "Color_Agudo_Diario": "Verde",
            "Color_Tendencia": "Verde",
            "Color_Tiebreak": "Verde",
        }

        with TemporaryDirectory() as tmpdir:
            data_dir = Path(tmpdir)
            rr_path = data_dir / "2026-02-08_RR.csv"
            rr_path.write_text(rr_row, encoding="utf-8")

            with (
                patch.object(core_builder, "compute_day_from_rr", return_value=(core_row, beta_row)),
                patch.object(
                    core_builder.sys,
                    "argv",
                    [
                        "build_hrv_core.py",
                        "--data-dir",
                        str(data_dir),
                        "--rr-file",
                        str(rr_path),
                    ],
                )
            ):
                exit_code = core_builder.main()

            self.assertEqual(exit_code, 0)
            self.assertTrue((data_dir / "ENDURANCE_HRV_master_CORE.csv").exists())
            self.assertTrue((data_dir / "ENDURANCE_HRV_master_BETA_AUDIT.csv").exists())

            manifest_path = data_dir / "ENDURANCE_HRV_master_CORE_manifest.json"
            self.assertTrue(manifest_path.exists())
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(manifest["schema_version"], "1.0")
            self.assertEqual(manifest["manifest_kind"], "hrv_run_manifest")
            self.assertEqual(manifest["stage"], "core")
            self.assertEqual(manifest["builder"], "build_hrv_core.py")
            self.assertEqual(manifest["inputs"][0]["role"], "rr_input")
            self.assertTrue(manifest["inputs"][0]["exists"])
            self.assertEqual(manifest["outputs"][0]["role"], "core")
            self.assertEqual(manifest["outputs"][1]["role"], "beta_audit")
            self.assertIn("effective_config_hash", manifest)
            self.assertEqual(manifest["effective_config"]["constants"]["TAIL_TRIM_S"], 15.0)


if __name__ == "__main__":
    unittest.main()
