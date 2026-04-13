import importlib
import unittest


class PolarHrvAutomationImportTests(unittest.TestCase):
    def test_module_imports_cleanly(self):
        module = importlib.import_module("polar_hrv_automation")
        self.assertTrue(callable(module.main))

    def test_web_ui_imports_cleanly(self):
        module = importlib.import_module("web_ui")
        self.assertTrue(hasattr(module, "app"))


if __name__ == "__main__":
    unittest.main()
