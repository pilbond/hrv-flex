import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import build_hrv_core as core_builder


class BuildHrvCoreContractTests(unittest.TestCase):
    _GLOBAL_ATTRS = ("DATA_DIR", "OUT_CORE", "OUT_BETA_AUDIT", "OUT_CORE_MANIFEST")

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

        saved = {attr: getattr(core_builder, attr) for attr in self._GLOBAL_ATTRS}
        try:
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
        finally:
            for attr, value in saved.items():
                setattr(core_builder, attr, value)


class GetOrCreateDfFailClosedTests(unittest.TestCase):
    def test_corrupt_existing_file_raises_and_quarantines(self):
        with TemporaryDirectory() as tmpdir:
            corrupt = Path(tmpdir) / "CORE.csv"
            corrupt.write_bytes(b"\xff\xfe corrupt bytes \x00\x01")
            original_bytes = corrupt.read_bytes()

            with self.assertRaises(RuntimeError) as ctx:
                core_builder.get_or_create_df(corrupt, ["Fecha", "col"])

            self.assertIn("FAIL-CLOSED", str(ctx.exception))
            # original bytes preserved
            self.assertEqual(corrupt.read_bytes(), original_bytes)
            # quarantine created with original content
            quarantine_files = list(Path(tmpdir).glob("CORE.csv.corrupt.*"))
            self.assertEqual(len(quarantine_files), 1)
            self.assertEqual(quarantine_files[0].read_bytes(), original_bytes)

    def test_invalid_schema_raises_and_quarantines(self):
        """Un CSV legible por pandas pero sin columnas canónicas debe fallar con cuarentena."""
        with TemporaryDirectory() as tmpdir:
            wrong = Path(tmpdir) / "CORE.csv"
            wrong.write_text("garbage\nfoo\n", encoding="utf-8")
            original_bytes = wrong.read_bytes()

            with self.assertRaises(RuntimeError) as ctx:
                core_builder.get_or_create_df(wrong, ["Fecha", "RMSSD"])

            self.assertIn("FAIL-CLOSED", str(ctx.exception))
            self.assertEqual(wrong.read_bytes(), original_bytes)
            quarantine_files = list(Path(tmpdir).glob("CORE.csv.corrupt.*"))
            self.assertEqual(len(quarantine_files), 1)

    def test_truncated_file_only_fecha_raises_and_quarantines(self):
        """Un archivo con solo 'Fecha' (truncado) debe fallar, no rellenarse con NaN."""
        with TemporaryDirectory() as tmpdir:
            truncated = Path(tmpdir) / "CORE.csv"
            truncated.write_text("Fecha\n2026-07-14\n", encoding="utf-8")
            original_bytes = truncated.read_bytes()

            with self.assertRaises(RuntimeError) as ctx:
                core_builder.get_or_create_df(truncated, ["Fecha", "RMSSD", "lnRMSSD"])

            self.assertIn("FAIL-CLOSED", str(ctx.exception))
            self.assertIn("RMSSD", str(ctx.exception))
            self.assertEqual(truncated.read_bytes(), original_bytes)
            quarantine_files = list(Path(tmpdir).glob("CORE.csv.corrupt.*"))
            self.assertEqual(len(quarantine_files), 1)

    def test_unexpected_column_raises_and_quarantines(self):
        """Un canónico con columnas ajenas al contrato debe fallar sin reescribirse."""
        with TemporaryDirectory() as tmpdir:
            wrong = Path(tmpdir) / "CORE.csv"
            wrong.write_text("Fecha,RMSSD,extra\n2026-07-14,45,valor\n", encoding="utf-8")
            original_bytes = wrong.read_bytes()

            with self.assertRaises(RuntimeError) as ctx:
                core_builder.get_or_create_df(wrong, ["Fecha", "RMSSD"])

            self.assertIn("columnas no canónicas", str(ctx.exception))
            self.assertEqual(wrong.read_bytes(), original_bytes)
            quarantine_files = list(Path(tmpdir).glob("CORE.csv.corrupt.*"))
            self.assertEqual(len(quarantine_files), 1)

    def test_header_only_file_raises_and_quarantines(self):
        """Cabecera completa pero sin filas debe fallar con cuarentena."""
        with TemporaryDirectory() as tmpdir:
            header_only = Path(tmpdir) / "CORE.csv"
            header_only.write_text("Fecha,RMSSD,lnRMSSD\n", encoding="utf-8")
            original_bytes = header_only.read_bytes()

            with self.assertRaises(RuntimeError) as ctx:
                core_builder.get_or_create_df(header_only, ["Fecha", "RMSSD", "lnRMSSD"])

            self.assertIn("FAIL-CLOSED", str(ctx.exception))
            self.assertEqual(header_only.read_bytes(), original_bytes)
            quarantine_files = list(Path(tmpdir).glob("CORE.csv.corrupt.*"))
            self.assertEqual(len(quarantine_files), 1)

    def test_all_nan_row_raises_and_quarantines(self):
        """Una fila con cabecera correcta pero solo valores vacíos debe fallar, no publicarse."""
        with TemporaryDirectory() as tmpdir:
            blank_row = Path(tmpdir) / "CORE.csv"
            blank_row.write_text("Fecha,RMSSD\n,\n", encoding="utf-8")
            original_bytes = blank_row.read_bytes()

            with self.assertRaises(RuntimeError) as ctx:
                core_builder.get_or_create_df(blank_row, ["Fecha", "RMSSD"])

            self.assertIn("FAIL-CLOSED", str(ctx.exception))
            self.assertEqual(blank_row.read_bytes(), original_bytes)
            quarantine_files = list(Path(tmpdir).glob("CORE.csv.corrupt.*"))
            self.assertEqual(len(quarantine_files), 1)

    def test_missing_file_returns_empty_df(self):
        with TemporaryDirectory() as tmpdir:
            missing = Path(tmpdir) / "CORE.csv"
            df = core_builder.get_or_create_df(missing, ["Fecha", "col"])
            self.assertTrue(df.empty)
            self.assertListEqual(list(df.columns), ["Fecha", "col"])


class BuildHrvCoreCliFailClosedTests(unittest.TestCase):
    _GLOBAL_ATTRS = ("DATA_DIR", "OUT_CORE", "OUT_BETA_AUDIT", "OUT_CORE_MANIFEST")

    def _run_main(self, data_dir, rr_path):
        saved = {attr: getattr(core_builder, attr) for attr in self._GLOBAL_ATTRS}
        try:
            with patch.object(
                core_builder.sys,
                "argv",
                ["build_hrv_core.py", "--data-dir", str(data_dir), "--rr-file", str(rr_path)],
            ):
                return core_builder.main()
        finally:
            for attr, value in saved.items():
                setattr(core_builder, attr, value)

    def test_corrupt_core_csv_exits_nonzero_no_manifest(self):
        """main() debe fallar con RuntimeError y sin manifest nuevo ante CORE.csv corrupto."""
        rr_row = "duration,offline\n1000,0\n1010,0\n"

        with TemporaryDirectory() as tmpdir:
            data_dir = Path(tmpdir)
            rr_path = data_dir / "2026-07-14_RR.csv"
            rr_path.write_text(rr_row, encoding="utf-8")

            core_path = data_dir / "ENDURANCE_HRV_master_CORE.csv"
            core_path.write_text(",".join(core_builder.COLS_CORE) + "\n", encoding="utf-8")
            core_bytes_before = core_path.read_bytes()

            manifest_path = data_dir / "ENDURANCE_HRV_master_CORE_manifest.json"

            with self.assertRaises(RuntimeError):
                self._run_main(data_dir, rr_path)

            self.assertEqual(core_path.read_bytes(), core_bytes_before)
            self.assertFalse(manifest_path.exists())
            quarantine_files = list(data_dir.glob("ENDURANCE_HRV_master_CORE.csv.corrupt.*"))
            self.assertEqual(len(quarantine_files), 1)

    def test_corrupt_beta_audit_csv_exits_nonzero_no_manifest(self):
        """main() debe fallar con RuntimeError y sin manifest nuevo ante BETA_AUDIT.csv corrupto."""
        rr_row = "duration,offline\n1000,0\n1010,0\n"

        with TemporaryDirectory() as tmpdir:
            data_dir = Path(tmpdir)
            rr_path = data_dir / "2026-07-14_RR.csv"
            rr_path.write_text(rr_row, encoding="utf-8")

            beta_path = data_dir / "ENDURANCE_HRV_master_BETA_AUDIT.csv"
            beta_path.write_text(",".join(core_builder.COLS_BETA_AUDIT) + "\n", encoding="utf-8")
            beta_bytes_before = beta_path.read_bytes()

            manifest_path = data_dir / "ENDURANCE_HRV_master_CORE_manifest.json"

            with self.assertRaises(RuntimeError):
                self._run_main(data_dir, rr_path)

            self.assertEqual(beta_path.read_bytes(), beta_bytes_before)
            self.assertFalse(manifest_path.exists())
            quarantine_files = list(data_dir.glob("ENDURANCE_HRV_master_BETA_AUDIT.csv.corrupt.*"))
            self.assertEqual(len(quarantine_files), 1)


if __name__ == "__main__":
    unittest.main()
