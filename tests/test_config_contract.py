import importlib
import unittest
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
