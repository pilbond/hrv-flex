import unittest

import pandas as pd

from hrv_app.ssm_brief import build_minimal_ssm_brief


class MinimalSsmBriefTests(unittest.TestCase):
    def _ssm_row(self, **overrides):
        row = {
            "Fecha": "2026-07-01",
            "ssm_warmup_complete": True,
            "ssm_recovery_state": 3.75,
            "ssm_baseline_state": 4.04,
            "ssm_fatigue_state": 0.29,
            "ssm_innovation": 0.02,
            "sleep_innovation": 0.03,
            "sleep_input_quality": "clean",
            "control_rolling_hrv_7d": 3.72,
        }
        row.update(overrides)
        return pd.Series(row)

    def _final_row(self, **overrides):
        row = {
            "Fecha": "2026-07-01",
            "gate_final": "ROJO",
            "Action": "SUAVE_O_DESCANSO",
            "Action_detail": "DESCARGA",
        }
        row.update(overrides)
        return pd.Series(row)

    def test_silent_when_ssm_has_no_material_signal(self):
        brief = build_minimal_ssm_brief(self._ssm_row(), self._final_row())

        self.assertEqual(brief["status"], "silent")
        self.assertFalse(brief["published"])
        self.assertEqual(brief["summary"], "")
        self.assertEqual(brief["reason"], "no_material_ssm_signal")

    def test_publishes_when_usable_sleep_innovation_is_material(self):
        brief = build_minimal_ssm_brief(
            self._ssm_row(sleep_innovation=0.16, sleep_input_quality="degraded"),
            self._final_row(gate_final="ROJO", Action_detail="DESCARGA"),
        )

        self.assertEqual(brief["status"], "ok")
        self.assertTrue(brief["published"])
        self.assertEqual(brief["relation_to_gate"], "discordant_or_noteworthy")
        self.assertIn("SSM shadow", brief["summary"])
        self.assertIn("observación nocturna", brief["summary"])
        self.assertIn("por encima de lo esperado", brief["summary"])
        self.assertIn("sorpresa matinal del modelo es pequeña", brief["detail"])
        self.assertIn("por encima de lo esperado", brief["detail"])
        self.assertIn("no debe leerse como señal global de buena recuperación", brief["detail"])
        self.assertIn("gate sigue en ROJO", brief["detail"])
        self.assertTrue(brief["rule_hits"]["abs_sleep_innovation_ge_0_12_and_usable"])

    def test_not_applicable_when_warmup_is_incomplete(self):
        brief = build_minimal_ssm_brief(
            self._ssm_row(ssm_warmup_complete=False),
            self._final_row(),
        )

        self.assertEqual(brief["status"], "not_applicable")
        self.assertFalse(brief["published"])
        self.assertEqual(brief["reason"], "warmup_incomplete")

    def test_suppressed_sleep_innovation_does_not_publish_by_itself(self):
        brief = build_minimal_ssm_brief(
            self._ssm_row(sleep_innovation=0.20, sleep_input_quality="suppressed"),
            self._final_row(),
        )

        self.assertEqual(brief["status"], "silent")
        self.assertFalse(brief["rule_hits"]["abs_sleep_innovation_ge_0_12_and_usable"])

    def test_state_vs_rolling_only_trigger_opens_summary_with_state_delta(self):
        # ssm_innovation sub-threshold pero state_delta material: el trigger real
        # es state_vs_rolling, el summary no debe caer en la rama generica de
        # "no hay una sorpresa matinal relevante".
        brief = build_minimal_ssm_brief(
            self._ssm_row(
                ssm_innovation=0.02,
                sleep_innovation=0.03,
                ssm_recovery_state=3.55,
                control_rolling_hrv_7d=3.72,
            ),
            self._final_row(gate_final="ROJO", Action_detail="DESCARGA"),
        )

        self.assertEqual(brief["status"], "ok")
        self.assertTrue(brief["rule_hits"]["state_delta_vs_rolling_ge_0_08"])
        self.assertFalse(brief["rule_hits"]["abs_ssm_innovation_ge_0_12"])
        self.assertIn("estado filtrado", brief["summary"])
        self.assertIn("por debajo", brief["summary"])
        self.assertNotIn("sorpresa matinal relevante", brief["summary"])

    def test_large_morning_innovation_is_labeled_by_magnitude(self):
        brief = build_minimal_ssm_brief(
            self._ssm_row(ssm_innovation=0.37, control_rolling_hrv_7d=3.61),
            self._final_row(gate_final="VERDE", Action_detail="EJECUTAR_PLAN"),
        )

        self.assertEqual(brief["status"], "ok")
        self.assertEqual(brief["relation_to_gate"], "aligned")
        self.assertIn("muy claramente por encima", brief["summary"])
        self.assertIn("sorpresa matinal del modelo es muy clara", brief["detail"])
        self.assertIn("penalización aguda de fatiga", brief["detail"])


if __name__ == "__main__":
    unittest.main()
