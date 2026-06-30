import json
import unittest
from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from jinja2 import TemplateNotFound

import web_ui


class WebUiStatusTests(unittest.TestCase):
    def _write_final_csv(self, data_dir: Path, fecha: str, reason_text: str = "Reason text base") -> None:
        (data_dir / "ENDURANCE_HRV_master_FINAL.csv").write_text(
            (
                "Fecha,HR_today,RMSSD_stable,lnRMSSD_today,lnRMSSD_used,ln_base60,SWC_ln,"
                "gate_badge,gate_razon_base60,reason_text,decision_path,Action_detail,recovery_support_class\n"
                f"{fecha},51,42.0,3.73,3.70,3.68,0.12,VERDE,BASE60_OK,{reason_text},path,EJECUTAR_PLAN,supported\n"
            ),
            encoding="utf-8",
        )

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

    def test_status_prefers_ai_daily_brief_when_published_for_latest_final(self):
        with TemporaryDirectory() as tmpdir:
            data_dir = Path(tmpdir)
            fecha = date.today().isoformat()
            self._write_final_csv(data_dir, fecha, reason_text="Texto determinista")
            (data_dir / "ENDURANCE_HRV_ai_daily_brief_latest.json").write_text(
                json.dumps(
                    {
                        "status": "ok",
                        "date": fecha,
                        "published": True,
                        "summary": "Dia verde con carga alta.",
                        "detail": "Monotonia 2.88 y strain 971, pero el gate sigue verde.",
                        "tone": "green",
                        "source_mode": "reason_items",
                    }
                ),
                encoding="utf-8",
            )

            with patch.object(web_ui, "DATA_DIR", data_dir):
                payload = web_ui._build_status_payload()

        diagnostics = payload["diagnostics"]
        self.assertTrue(diagnostics["ai_daily_brief_exists"])
        self.assertTrue(diagnostics["ai_daily_brief_matches_final"])
        self.assertIn("Dia verde con carga alta.", diagnostics["hrv_summary_ai_text"])
        self.assertIn("Monotonia 2.88 y strain 971", diagnostics["hrv_summary_ai_text"])
        self.assertEqual(diagnostics["hrv_summary_reason_text"], "Texto determinista")
        self.assertIsNone(diagnostics["hrv_summary_fallback_text"])
        self.assertTrue(diagnostics["hrv_summary_has_reason_text"])
        self.assertFalse(diagnostics["hrv_summary_reason_is_fallback"])

    def test_index_fallback_renders_ai_daily_brief_when_template_missing(self):
        with TemporaryDirectory() as tmpdir:
            data_dir = Path(tmpdir)
            fecha = date.today().isoformat()
            self._write_final_csv(data_dir, fecha, reason_text="Texto determinista")
            (data_dir / "ENDURANCE_HRV_ai_daily_brief_latest.json").write_text(
                json.dumps(
                    {
                        "status": "ok",
                        "date": fecha,
                        "published": True,
                        "summary": "Dia rojo por caida aguda.",
                        "detail": "La restriccion viene del gate rojo y se mantiene publicada.",
                        "tone": "red",
                        "source_mode": "reason_items",
                    }
                ),
                encoding="utf-8",
            )

            with patch.object(web_ui, "DATA_DIR", data_dir), \
                    patch.object(web_ui, "render_template", side_effect=TemplateNotFound("index.html")):
                with web_ui.app.test_client() as client:
                    response = client.get("/")

        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn("Dia rojo por caida aguda.", html)
        self.assertIn("La restriccion viene del gate rojo", html)
        self.assertIn("Texto determinista", html)
        self.assertIn("VERDE", html)

    def test_index_exposes_hrv_dashboard_shell(self):
        with web_ui.app.test_client() as client:
            response = client.get("/")

        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn('id="hrvSummaryCard"', html)
        self.assertIn('id="hrvSummaryAiBlock"', html)
        self.assertIn('id="hrvSummaryReasonBlock"', html)
        self.assertIn('id="hrvSummaryFallbackBlock"', html)
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

    def test_index_falls_back_when_template_missing(self):
        with patch.object(web_ui, "render_template", side_effect=TemplateNotFound("index.html")):
            with web_ui.app.test_client() as client:
                response = client.get("/")

        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn('id="hrvSummaryCard"', html)
        self.assertIn("Lectura HRV de hoy", html)
        self.assertIn("Detalle técnico", html)

    def test_status_uses_unavailable_fallback_when_ai_and_reason_are_missing(self):
        with TemporaryDirectory() as tmpdir:
            data_dir = Path(tmpdir)
            self._write_final_csv(data_dir, date.today().isoformat(), reason_text="")

            with patch.object(web_ui, "DATA_DIR", data_dir):
                payload = web_ui._build_status_payload()

        diagnostics = payload["diagnostics"]
        self.assertIsNone(diagnostics["hrv_summary_ai_text"])
        self.assertIsNone(diagnostics["hrv_summary_reason_text"])
        self.assertEqual(diagnostics["hrv_summary_fallback_text"], "Todavía no hay salida FINAL disponible.")
        self.assertFalse(diagnostics["hrv_summary_has_reason_text"])
        self.assertTrue(diagnostics["hrv_summary_reason_is_fallback"])

    def test_template_json_loader_uses_fallback_when_template_missing(self):
        fallback = {"text": {"example": "ok"}}
        with patch.object(web_ui.app.jinja_env, "get_template", side_effect=TemplateNotFound("missing.json.j2")):
            payload = web_ui._load_template_json("missing.json.j2", fallback)

        self.assertEqual(payload, fallback)
        self.assertIsNot(payload, fallback)

    def test_template_json_loader_reads_file_when_jinja_lookup_fails(self):
        fallback = {"dashboard_title": "fallback"}
        with patch.object(web_ui.app.jinja_env, "get_template", side_effect=TemplateNotFound("data/ui_copy.json.j2")):
            payload = web_ui._load_template_json("data/ui_copy.json.j2", fallback)

        self.assertEqual(payload["dashboard_title"], "⚡ HRV Sync")
        self.assertNotEqual(payload, fallback)


if __name__ == "__main__":
    unittest.main()
