import json
import unittest
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import build_hrv_core as core_builder


class BuildHrvCoreContractTests(unittest.TestCase):
    _GLOBAL_ATTRS = ("DATA_DIR", "OUT_CORE", "OUT_BETA_AUDIT", "OUT_CORE_MANIFEST")

    def test_backup_retention_defaults_to_thirty_and_accepts_zero(self):
        with patch.dict("os.environ", {}, clear=True):
            self.assertEqual(core_builder.core_backup_retention(), 30)
        with patch.dict("os.environ", {"HRV_CORE_BACKUP_RETENTION": "0"}, clear=True):
            self.assertEqual(core_builder.core_backup_retention(), 0)

    def test_invalid_backup_retention_warns_and_uses_default(self):
        with (
            patch.dict("os.environ", {"HRV_CORE_BACKUP_RETENTION": "abc"}),
            patch("sys.stderr", new_callable=StringIO) as stderr,
        ):
            self.assertEqual(core_builder.core_backup_retention(), 30)
            self.assertIn("[WARN] HRV_CORE_BACKUP_RETENTION", stderr.getvalue())

    def test_prune_core_backups_keeps_latest_n_per_type(self):
        with TemporaryDirectory() as tmpdir:
            backup_dir = Path(tmpdir)
            for prefix in ("CORE", "BETA_AUDIT"):
                for stamp in ("20260101_000000", "20260102_000000", "20260103_000000"):
                    (backup_dir / f"{prefix}_backup_{stamp}.csv").write_text("x", encoding="utf-8")

            core_builder.prune_core_backups(backup_dir, 2)

            self.assertEqual(len(list(backup_dir.glob("CORE_backup_*.csv"))), 2)
            self.assertEqual(len(list(backup_dir.glob("BETA_AUDIT_backup_*.csv"))), 2)
            self.assertFalse((backup_dir / "CORE_backup_20260101_000000.csv").exists())
            self.assertTrue((backup_dir / "CORE_backup_20260103_000000.csv").exists())

    def test_prune_failure_does_not_raise(self):
        with TemporaryDirectory() as tmpdir:
            backup_dir = Path(tmpdir)
            old_path = backup_dir / "CORE_backup_20260101_000000.csv"
            old_path.write_text("x", encoding="utf-8")
            (backup_dir / "CORE_backup_20260102_000000.csv").write_text("x", encoding="utf-8")
            with patch.object(Path, "unlink", side_effect=OSError("locked")):
                core_builder.prune_core_backups(backup_dir, 1)

    def test_prune_skips_only_the_type_with_a_listing_error(self):
        with TemporaryDirectory() as tmpdir:
            backup_dir = Path(tmpdir)
            core_old, core_new, beta_old, beta_new = (
                backup_dir / f"{prefix}_backup_20260101_{stamp}.csv"
                for prefix in ("CORE", "BETA_AUDIT")
                for stamp in ("110000", "120000")
            )
            for path in (core_old, core_new, beta_old, beta_new):
                path.touch()

            glob = Path.glob
            def listing_error(path, pattern):
                if path == backup_dir and pattern.startswith("CORE_"):
                    raise PermissionError("listing denied")
                return glob(path, pattern)
            with (
                patch.object(Path, "glob", listing_error),
                patch("sys.stderr", new_callable=StringIO) as stderr,
            ):
                core_builder.prune_core_backups(backup_dir, 1)

            self.assertEqual(set(backup_dir.iterdir()), {core_old, core_new, beta_new})
            self.assertIn("[WARN] No se pudo inspeccionar los backups de CORE", stderr.getvalue())

    def test_prune_protects_current_copy_after_clock_rollback_and_ignores_manual_copies(self):
        with TemporaryDirectory() as tmpdir:
            backup_dir = Path(tmpdir)
            current_copies = tuple(
                backup_dir / f"{prefix}_backup_20260101_110000.csv"
                for prefix in ("CORE", "BETA_AUDIT")
            )
            manual_copy = backup_dir / "CORE_backup_manual.csv"
            prior_copies = tuple(
                backup_dir / f"{prefix}_backup_20260101_120000.csv"
                for prefix in ("CORE", "BETA_AUDIT")
            )
            for path in (*current_copies, *prior_copies, manual_copy):
                path.touch()

            core_builder.prune_core_backups(backup_dir, 1, current_copies=current_copies)

            self.assertEqual(set(backup_dir.iterdir()), {*current_copies, manual_copy})

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
            "Notes": f"geom={core_builder.CONSTANTS['GEOMETRY_VERSION']}",
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

                backup_dir = data_dir / "backup"
                with (
                    patch.dict("os.environ", {"HRV_CORE_BACKUP_RETENTION": "3"}),
                    patch.object(core_builder.sys, "argv", [
                        "build_hrv_core.py", "--data-dir", str(data_dir), "--rr-file", str(rr_path)
                    ]),
                    patch.object(core_builder, "compute_day_from_rr", return_value=(core_row, beta_row)),
                    patch.object(core_builder, "prune_core_backups", wraps=core_builder.prune_core_backups) as prune,
                ):
                    self.assertEqual(core_builder.main(), 0)
                self.assertEqual(len(list(backup_dir.glob("CORE_backup_*.csv"))), 1)
                self.assertEqual(len(list(backup_dir.glob("BETA_AUDIT_backup_*.csv"))), 1)
                kwargs = prune.call_args.kwargs
                self.assertEqual(len(kwargs["current_copies"]), 2)

                for env in (
                    {"HRV_CORE_BACKUP_RETENTION": "0"},
                    {"HRV_DISABLE_BACKUP": "1"},
                ):
                    with (
                        patch.dict("os.environ", env, clear=True),
                        patch.object(core_builder.sys, "argv", [
                            "build_hrv_core.py", "--data-dir", str(data_dir), "--rr-file", str(rr_path)
                        ]),
                        patch.object(core_builder, "compute_day_from_rr", return_value=(core_row, beta_row)),
                    ):
                        self.assertEqual(core_builder.main(), 0)
                    self.assertEqual(len(list(backup_dir.glob("CORE_backup_*.csv"))), 1)
                    self.assertEqual(len(list(backup_dir.glob("BETA_AUDIT_backup_*.csv"))), 1)
        finally:
            for attr, value in saved.items():
                setattr(core_builder, attr, value)

    def test_main_rejects_legacy_core_before_processing_or_writing(self):
        saved = {attr: getattr(core_builder, attr) for attr in self._GLOBAL_ATTRS}
        try:
            with TemporaryDirectory() as tmpdir:
                data_dir = Path(tmpdir)
                core = data_dir / "ENDURANCE_HRV_master_CORE.csv"
                beta = data_dir / "ENDURANCE_HRV_master_BETA_AUDIT.csv"
                rr = data_dir / "2026-02-09_RR.csv"
                core.write_text("Fecha,Notes\n2026-02-08,legacy\n", encoding="utf-8")
                beta.write_text("Fecha\n2026-02-08\n", encoding="utf-8")
                rr.write_text("duration,offline\n1000,0\n", encoding="utf-8")
                before = (core.read_bytes(), beta.read_bytes())
                argv = ["build_hrv_core.py", "--data-dir", str(data_dir), "--rr-file", str(rr)]
                with patch.object(core_builder.sys, "argv", argv), patch.object(
                    core_builder, "compute_day_from_rr"
                ) as compute, patch.object(core_builder, "get_or_create_df", return_value=None):
                    with self.assertRaises(SystemExit) as caught:
                        core_builder.main()
                self.assertEqual(caught.exception.code, 2)
                compute.assert_not_called()
                self.assertEqual((core.read_bytes(), beta.read_bytes()), before)
        finally:
            for attr, value in saved.items():
                setattr(core_builder, attr, value)

    def test_canonical_geometry_check_requires_matching_manifest_and_hashes(self):
        with TemporaryDirectory() as tmpdir:
            data_dir = Path(tmpdir)
            core = data_dir / "ENDURANCE_HRV_master_CORE.csv"
            beta = data_dir / "ENDURANCE_HRV_master_BETA_AUDIT.csv"
            manifest = data_dir / "ENDURANCE_HRV_master_CORE_manifest.json"
            self.assertIsNone(core_builder.canonical_geometry_issue(core, beta, manifest))
            core.write_text("Fecha,Notes\n2026-02-08,geom=hg10_s90_t375_trim15\n", encoding="utf-8")
            beta.write_text("beta", encoding="utf-8")
            payload = {
                "effective_config": {"constants": {"GEOMETRY_VERSION": "old"}},
                "outputs": [
                    {"role": "core", "sha256": core_builder.file_digest(core)},
                    {"role": "beta_audit", "sha256": core_builder.file_digest(beta)},
                ],
            }
            manifest.write_text(json.dumps(payload), encoding="utf-8")
            self.assertIn("geometría existente", core_builder.canonical_geometry_issue(core, beta, manifest))
            payload["effective_config"]["constants"]["GEOMETRY_VERSION"] = core_builder.CONSTANTS["GEOMETRY_VERSION"]
            manifest.write_text(json.dumps(payload), encoding="utf-8")
            self.assertIn("política de Calidad", core_builder.canonical_geometry_issue(core, beta, manifest))
            payload["effective_config"]["constants"]["QUALITY_POLICY_VERSION"] = core_builder.CONSTANTS["QUALITY_POLICY_VERSION"]
            manifest.write_text(json.dumps(payload), encoding="utf-8")
            self.assertIsNone(core_builder.canonical_geometry_issue(core, beta, manifest))
            core.write_text("Fecha,Notes\n2026-02-08,legacy\n", encoding="utf-8")
            self.assertIn("huella de core", core_builder.canonical_geometry_issue(core, beta, manifest))
            payload["outputs"][0]["sha256"] = core_builder.file_digest(core)
            manifest.write_text(json.dumps(payload), encoding="utf-8")
            self.assertIn("fila(s) CORE", core_builder.canonical_geometry_issue(core, beta, manifest))
            core.write_text(
                "Fecha,Notes\n"
                "2026-02-08,geom=hg10_s90_t375_trim15\n"
                "2026-02-26,legacy sin RR\n"
                "2026-02-27,legacy sin RR\n"
                "2026-03-03,legacy sin RR\n",
                encoding="utf-8",
            )
            payload["outputs"][0]["sha256"] = core_builder.file_digest(core)
            manifest.write_text(json.dumps(payload), encoding="utf-8")
            self.assertIsNone(core_builder.canonical_geometry_issue(core, beta, manifest))

    def test_migration_override_requires_a_separate_data_dir(self):
        with patch.object(
            core_builder.sys, "argv", ["build_hrv_core.py", "--allow-hg10-migration"]
        ), self.assertRaises(SystemExit) as caught:
            core_builder.main()
        self.assertEqual(caught.exception.code, 2)


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
