import importlib
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
            import config

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
            import config

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
                    "POLAR_CLIENT_ID": "client-1",
                    "POLAR_CLIENT_SECRET": "secret",
                    "PUBLIC_URL": "",
                },
                clear=False,
            ):
                import config

                config = importlib.reload(config)
                self.assertEqual(config.DATA_DIR, data_dir)
                self.assertEqual(config.OUTDIR, rr_dir)
                self.assertEqual(config.CORE_PATH, data_dir / "ENDURANCE_HRV_master_CORE.csv")
                self.assertEqual(config.SLEEP_PATH, data_dir / "ENDURANCE_HRV_sleep.csv")
                self.assertEqual(config.FINAL_PATH, data_dir / "ENDURANCE_HRV_master_FINAL.csv")
                self.assertEqual(config.DASHBOARD_PATH, data_dir / "ENDURANCE_HRV_master_DASHBOARD.csv")
