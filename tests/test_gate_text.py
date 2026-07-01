import unittest

from hrv_app import gate_text


class FormatGateReasonTests(unittest.TestCase):
    def test_returns_na_for_empty_or_na(self):
        self.assertEqual(gate_text.format_gate_reason(None), "N/A")
        self.assertEqual(gate_text.format_gate_reason(""), "N/A")
        self.assertEqual(gate_text.format_gate_reason("N/A"), "N/A")

    def test_translates_canonical_codes(self):
        cases = {
            "2D_OK": "dentro de tu rango",
            "2D_LN": "señal suavizada bajó",
            "2D_HR": "frecuencia cardiaca suavizada subió",
            "2D_AMBOS": "trata hoy como un día más delicado",
            "ROLL3_INSUF": "días limpios seguidos",
            "BASE60_INSUF": "ventana de 60 días",
            "SWC_NAN/0": "demasiado plana",
            "RAW_NAN/0": "señal bruta llegó vacía",
        }
        for code, fragment in cases.items():
            with self.subTest(code=code):
                self.assertIn(fragment, gate_text.format_gate_reason(code))

    def test_cal_stab_art_appends_default_causes_without_row(self):
        text = gate_text.format_gate_reason("CAL/STAB/ART/NaN")
        self.assertIn("no fue lo bastante fiable", text)
        self.assertIn("Causas típicas", text)

    def test_cal_stab_art_appends_row_clues(self):
        row = {
            "Artifact_pct": 20.5,
            "HRV_Stability": "BAJA",
            "Stability_Subtype": "DRIFT",
            "Tiempo_Estabilizacion": 240,
        }
        text = gate_text.format_gate_reason("CAL/STAB/ART/NaN", row)
        self.assertIn("artefactos altos", text)
        self.assertIn("estabilidad de señal BAJA", text)
        self.assertIn("subtipo de estabilidad DRIFT", text)
        self.assertIn("estabilización de 240s", text)

    def test_unknown_prefix_fallbacks(self):
        self.assertIn("calidad", gate_text.format_gate_reason("CAL/UNKNOWN"))
        self.assertIn("datos limpios", gate_text.format_gate_reason("WHATEVER_INSUF"))
        self.assertIn("comparar hoy", gate_text.format_gate_reason("X_NAN"))

    def test_truly_unknown_returns_internal_motive(self):
        self.assertIn("no traducido", gate_text.format_gate_reason("XYZ_UNKNOWN"))


class FormatGateNextStepTests(unittest.TestCase):
    def test_returns_na_for_empty(self):
        self.assertEqual(gate_text.format_gate_next_step(None), "N/A")
        self.assertEqual(gate_text.format_gate_next_step(""), "N/A")
        self.assertEqual(gate_text.format_gate_next_step("N/A"), "N/A")

    def test_translates_canonical_codes(self):
        cases = {
            "2D_OK": "plan previsto",
            "2D_LN": "vigilar recuperación",
            "2D_HR": "evitar subir demasiado",
            "2D_AMBOS": "baja un punto la exigencia",
            "CAL/STAB/ART/NaN": "sensor bien colocado",
            "ROLL3_INSUF": "días limpios",
            "BASE60_INSUF": "Mantén la rutina",
            "SWC_NAN/0": "referencia estable",
            "RAW_NAN/0": "Repite la medición",
        }
        for code, fragment in cases.items():
            with self.subTest(code=code):
                self.assertIn(fragment, gate_text.format_gate_next_step(code))

    def test_unknown_prefix_fallbacks(self):
        self.assertIn("sensor bien colocado", gate_text.format_gate_next_step("CAL/UNKNOWN"))
        self.assertIn("datos limpios", gate_text.format_gate_next_step("WHATEVER_INSUF"))
        self.assertIn("lectura más fiable", gate_text.format_gate_next_step("X_NAN"))


if __name__ == "__main__":
    unittest.main()
