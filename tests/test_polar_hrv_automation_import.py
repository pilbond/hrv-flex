import importlib
import unittest


class PolarHrvAutomationImportTests(unittest.TestCase):
    def test_module_imports_cleanly(self):
        module = importlib.import_module("polar_hrv_automation")
        self.assertTrue(callable(module.main))

    def test_refresh_sleep_and_outputs_remains_callable(self):
        module = importlib.import_module("polar_hrv_automation")
        self.assertTrue(callable(module._refresh_sleep_and_outputs))


if __name__ == "__main__":
    unittest.main()
