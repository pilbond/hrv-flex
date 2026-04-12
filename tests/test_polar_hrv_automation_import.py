import importlib
import unittest


class PolarHrvAutomationImportTests(unittest.TestCase):
    def test_module_imports_and_exposes_callback_state(self):
        module = importlib.import_module("polar_hrv_automation")
        state = module._CallbackState()

        self.assertIsNone(state.code)
        self.assertIsNone(state.error)
        self.assertIsNone(state.raw_query)


if __name__ == "__main__":
    unittest.main()
