import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import web_ui


class WebUiStatusTests(unittest.TestCase):
    def test_weekly_coach_diagnostics_exposes_planning_note(self):
        with TemporaryDirectory() as tmpdir:
            data_dir = Path(tmpdir)
            weekly_coach_path = data_dir / "ENDURANCE_HRV_weekly_coach.json"
            weekly_coach_path.write_text(
                json.dumps(
                    {
                        "iso_week": "2026-W10",
                        "window_start": "2026-03-02",
                        "window_end": "2026-03-08",
                        "data_quality": "limited",
                        "planning_note": (
                            "Semana con cobertura parcial: si la HRV matinal abre "
                            "estable y Action/reason_text acompanan, puedes arrancar "
                            "con progresion normal; si no, mueve 24h el primer pico "
                            "de carga."
                        ),
                        "z3_budget_summary": "Z3 alto en bike (p87.5) y road run (p81.0).",
                    }
                ),
                encoding="utf-8",
            )

            with patch.object(web_ui, "DATA_DIR", data_dir):
                diagnostics = web_ui._weekly_coach_diagnostics()

        self.assertTrue(diagnostics["weekly_coach_exists"])
        self.assertEqual(diagnostics["weekly_coach_iso_week"], "2026-W10")
        self.assertEqual(diagnostics["weekly_coach_window_end"], "2026-03-08")
        self.assertEqual(diagnostics["weekly_coach_data_quality"], "limited")
        self.assertIn("puedes arrancar con progresion normal", diagnostics["weekly_coach_planning_note"])
        self.assertEqual(
            diagnostics["weekly_coach_z3_budget_summary"],
            "Z3 alto en bike (p87.5) y road run (p81.0).",
        )

    def test_index_exposes_hrv_dashboard_shell(self):
        with web_ui.app.test_client() as client:
            response = client.get("/")

        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn('id="hrvSummaryCard"', html)
        self.assertIn("Lectura HRV de hoy", html)
        self.assertNotIn('id="weeklyCoachCard"', html)
        self.assertNotIn("Coach semanal", html)
        self.assertNotIn("weeklyCoachUnavailable", html)
        self.assertNotIn('onclick="syncPolar()"', html)
        self.assertNotIn('data-start-message=', html)
        self.assertNotIn('data-endpoint=', html)
        self.assertIn('/static/ui.css', html)
        self.assertIn('/static/ui.js', html)
        self.assertIn('id="ui-runtime-config"', html)
        self.assertNotIn("window.UI_TEXT", html)
        self.assertNotIn("window.UI_TEMPLATES", html)
        self.assertNotIn("window.SYNC_TIMEOUT_SEC", html)


if __name__ == "__main__":
    unittest.main()
