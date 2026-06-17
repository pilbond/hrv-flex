import importlib
import tempfile
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch


class ConfigContractTests(unittest.TestCase):
    def test_client_id_prefers_client_id2_and_normalizes_production_url(self):
        with patch.dict(
            "os.environ",
            {
                "POLAR_CLIENT_ID2": "client-2",
                "POLAR_CLIENT_ID": "client-1",
                "PUBLIC_URL": "example.up.railway.app",
            },
            clear=False,
        ):
            import hrv_app.config as config

            config = importlib.reload(config)
            self.assertEqual(config.CLIENT_ID, "client-2")
            self.assertEqual(config.get_production_url(), "https://example.up.railway.app")

    def test_client_id_falls_back_to_client_id(self):
        with patch.dict(
            "os.environ",
            {
                "POLAR_CLIENT_ID": "client-1",
                "PUBLIC_URL": "",
            },
            clear=False,
        ):
            import hrv_app.config as config

            config = importlib.reload(config)
            self.assertEqual(config.CLIENT_ID, "client-1")

    def test_path_contract_uses_data_dir_and_rr_download_dir(self):
        with TemporaryDirectory() as tmpdir:
            data_dir = Path(tmpdir) / "hrv-data"
            rr_dir = Path(tmpdir) / "rr-downloads"
            with patch.dict(
                "os.environ",
                {
                    "HRV_DATA_DIR": str(data_dir),
                    "RR_DOWNLOAD_DIR": str(rr_dir),
                    "HRV_DROPBOX_RR_TIMEOUT_SEC": "321",
                    "POLAR_CLIENT_ID": "client-1",
                    "POLAR_CLIENT_SECRET": "secret",
                    "PUBLIC_URL": "",
                },
                clear=False,
            ):
                import hrv_app.config as config

                config = importlib.reload(config)
                self.assertEqual(config.DATA_DIR, data_dir)
                self.assertEqual(config.OUTDIR, rr_dir)
                self.assertEqual(config.CORE_PATH, data_dir / "ENDURANCE_HRV_master_CORE.csv")
                self.assertEqual(config.SLEEP_PATH, data_dir / "ENDURANCE_HRV_sleep.csv")
                self.assertEqual(config.FINAL_PATH, data_dir / "ENDURANCE_HRV_master_FINAL.csv")
                self.assertEqual(config.DASHBOARD_PATH, data_dir / "ENDURANCE_HRV_master_DASHBOARD.csv")
                self.assertEqual(config.SSM_SHADOW_PATH, data_dir / "ENDURANCE_HRV_ssm_shadow.csv")
                self.assertEqual(config.SSM_SHADOW_METADATA_PATH, data_dir / "ENDURANCE_HRV_ssm_shadow_metadata.json")
                self.assertEqual(config.SSM_VALIDATION_REPORT_JSON_PATH, data_dir / "ENDURANCE_HRV_ssm_validation_report.json")
                self.assertEqual(config.SSM_VALIDATION_REPORT_MD_PATH, data_dir / "ENDURANCE_HRV_ssm_validation_report.md")
                self.assertEqual(config.DROPBOX_RR_TIMEOUT_SEC, 321)

    def test_polar_api_version_defaults_to_v4(self):
        env = {k: v for k, v in __import__("os").environ.items() if k != "POLAR_API_VERSION"}
        with patch.dict("os.environ", env, clear=True):
            import hrv_app.config as config
            config = importlib.reload(config)
        self.assertEqual(config.POLAR_API_VERSION, "v4")

    def test_polar_api_version_v3_rollback_explicit(self):
        with patch.dict("os.environ", {"POLAR_API_VERSION": "v3"}, clear=False):
            import hrv_app.config as config
            config = importlib.reload(config)
        self.assertEqual(config.POLAR_API_VERSION, "v3")

    def test_path_resolution_falls_back_to_a_writable_storage_root(self):
        class _ProbeContext:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

        with TemporaryDirectory() as tmpdir:
            primary_data_dir = Path(tmpdir) / "blocked" / "hrv-data"
            fallback_data_dir = Path(tmpdir) / "hrv-data"

            def _named_tempfile(*args, **kwargs):
                dir_arg = kwargs.get("dir")
                if dir_arg and str(dir_arg).startswith(str(primary_data_dir.parent)):
                    raise OSError("permission denied")
                return _ProbeContext()

            with patch.dict(
                "os.environ",
                {
                    "HRV_DATA_DIR": str(primary_data_dir),
                    "RR_DOWNLOAD_DIR": str(primary_data_dir / "rr-downloads"),
                    "POLAR_TOKEN_PATH": str(primary_data_dir / "polar_tokens.json"),
                    "POLAR_CLIENT_ID": "client-1",
                    "POLAR_CLIENT_SECRET": "secret",
                    "PUBLIC_URL": "",
                },
                clear=False,
            ), patch.object(tempfile, "NamedTemporaryFile", side_effect=_named_tempfile), patch.object(
                Path, "cwd", return_value=Path(tmpdir)
            ):
                import hrv_app.config as config

                config = importlib.reload(config)

            self.assertEqual(config.DATA_DIR, fallback_data_dir)
            self.assertEqual(config.OUTDIR, fallback_data_dir / "rr_downloads")
            self.assertEqual(config.TOKEN_FILE, fallback_data_dir / "polar_tokens.json")
