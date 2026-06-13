import unittest

from hrv_app.hrv_sync_flow import extract_rr_ms


class ExtractRrMsTests(unittest.TestCase):
    def test_v3_samples_without_mask_keep_range_behaviour(self):
        exercise = {"samples": [{"sample-type": "11", "data": "812,5000,820"}]}
        rr = extract_rr_ms(exercise)
        self.assertEqual(rr, [(812.0, 0), (5000.0, 1), (820.0, 0)])

    def test_offline_mask_overrides_range_check(self):
        # RR en rango fisiológico pero marcado offline=true por Polar: debe
        # quedar como artefacto (primera capa de descarte del contrato HRV).
        exercise = {"samples": [{
            "sample-type": "11",
            "data": "812,815,820",
            "offline": "0,1,0",
        }]}
        rr = extract_rr_ms(exercise)
        self.assertEqual(rr, [(812.0, 0), (815.0, 1), (820.0, 0)])

    def test_mask_and_range_combine_with_or(self):
        exercise = {"samples": [{
            "sample-type": "11",
            "data": "100,815",
            "offline": "0,0",
        }]}
        rr = extract_rr_ms(exercise)
        # 100ms fuera de rango → offline aunque la máscara diga 0.
        self.assertEqual(rr, [(100.0, 1), (815.0, 0)])

    def test_short_mask_does_not_crash(self):
        exercise = {"samples": [{
            "sample-type": "11",
            "data": "812,815,820",
            "offline": "1",
        }]}
        rr = extract_rr_ms(exercise)
        self.assertEqual(rr, [(812.0, 1), (815.0, 0), (820.0, 0)])


if __name__ == "__main__":
    unittest.main()
