import math
import unittest

from hrv_app import ui_view


class ComposeHrvSummaryTests(unittest.TestCase):
    def test_returns_dashes_when_pipeline_metrics_absent(self):
        out = ui_view.compose_hrv_summary({})
        self.assertEqual(out["hrv_summary_title_date"], None)
        self.assertEqual(
            out["hrv_summary_raw_text"],
            "- ms · HR - · ln -",
        )
        self.assertEqual(out["hrv_summary_gate_text"], "N/A · N/A")
        self.assertIsNone(out["hrv_summary_ai_text"])
        self.assertIsNone(out["hrv_summary_reason_text"])
        self.assertEqual(
            out["hrv_summary_fallback_text"],
            ui_view.DEFAULT_UNAVAILABLE_TEXT,
        )
        self.assertTrue(out["hrv_summary_reason_is_fallback"])
        self.assertFalse(out["hrv_summary_has_reason_text"])

    def test_uses_custom_unavailable_text_when_provided(self):
        out = ui_view.compose_hrv_summary({}, unavailable_text="Sin datos.")
        self.assertEqual(out["hrv_summary_fallback_text"], "Sin datos.")

    def test_formats_numeric_pipeline_values(self):
        ln_used = 3.70
        ln_base = 3.68
        diagnostics = {
            "final_last_fecha": "2026-06-30",
            "final_last_rmssd_stable": 42.0,
            "final_last_hr_today": 51,
            "final_last_lnrmssd_today": 3.73,
            "final_last_lnrmssd_used": ln_used,
            "final_last_ln_base60": ln_base,
            "final_last_swc_ln": 0.12,
            "final_last_gate_badge": "VERDE",
            "final_last_gate_razon_base60": "BASE60_OK",
        }
        out = ui_view.compose_hrv_summary(diagnostics)

        self.assertEqual(out["hrv_summary_title_date"], "2026-06-30")
        self.assertIn("42.0 ms", out["hrv_summary_raw_text"])
        self.assertIn("HR 51.0", out["hrv_summary_raw_text"])
        self.assertIn("ln 3.730", out["hrv_summary_raw_text"])
        self.assertIn(f"{math.exp(ln_used):.1f} ms", out["hrv_summary_used_text"])
        self.assertIn(f"{math.exp(ln_base):.1f} ms", out["hrv_summary_base_text"])
        self.assertEqual(out["hrv_summary_gate_text"], "VERDE · BASE60_OK")

    def test_prefers_ai_brief_when_published_and_matches_final(self):
        diagnostics = {
            "ai_daily_brief_status": "ok",
            "ai_daily_brief_published": True,
            "ai_daily_brief_matches_final": True,
            "ai_daily_brief_summary": "Dia verde.",
            "ai_daily_brief_detail": "Monotonia 2.88.",
            "final_last_reason_text": "Reason canonico",
        }
        out = ui_view.compose_hrv_summary(diagnostics)
        self.assertIn("Dia verde.", out["hrv_summary_ai_text"])
        self.assertIn("Monotonia 2.88.", out["hrv_summary_ai_text"])
        self.assertEqual(out["hrv_summary_reason_text"], "Reason canonico")
        self.assertIsNone(out["hrv_summary_fallback_text"])

    def test_ai_brief_ignored_when_status_not_ok(self):
        diagnostics = {
            "ai_daily_brief_status": "error",
            "ai_daily_brief_published": True,
            "ai_daily_brief_matches_final": True,
            "ai_daily_brief_summary": "Texto",
            "final_last_reason_text": "Reason",
        }
        out = ui_view.compose_hrv_summary(diagnostics)
        self.assertIsNone(out["hrv_summary_ai_text"])
        self.assertEqual(out["hrv_summary_reason_text"], "Reason")


class FmtHelpersTests(unittest.TestCase):
    def test_fmt_number_returns_dash_on_invalid(self):
        self.assertEqual(ui_view.fmt_number(None), "-")
        self.assertEqual(ui_view.fmt_number("abc"), "-")
        self.assertEqual(ui_view.fmt_number(1.234, decimals=2), "1.23")

    def test_fmt_exp_from_log_uses_one_decimal(self):
        self.assertEqual(ui_view.fmt_exp_from_log(None), "-")
        self.assertEqual(ui_view.fmt_exp_from_log(0), "1.0")

    def test_fmt_rr_date_label_parses_iso_date_inside_filename(self):
        self.assertEqual(ui_view.fmt_rr_date_label("rr_2026-06-30_xyz.csv"), "30/06/2026")
        self.assertEqual(ui_view.fmt_rr_date_label("no_date_here.csv"), "")
        self.assertEqual(ui_view.fmt_rr_date_label(None), "")


class BuildViewTests(unittest.TestCase):
    def _base_diagnostics(self) -> dict:
        diagnostics = {
            "final_exists": True,
            "final_last_fecha": "2026-06-30",
            "final_last_rmssd_stable": 42.0,
            "final_last_hr_today": 51,
            "final_last_lnrmssd_today": 3.73,
            "final_last_lnrmssd_used": 3.70,
            "final_last_ln_base60": 3.68,
            "final_last_swc_ln": 0.12,
            "final_last_gate_badge": "VERDE",
            "final_last_gate_razon_base60": "BASE60_OK",
            "ai_daily_brief_status": "ok",
            "ai_daily_brief_published": True,
            "ai_daily_brief_matches_final": True,
            "ai_daily_brief_summary": "Dia verde.",
            "ai_daily_brief_detail": "Monotonia 2.88.",
            "final_last_reason_text": "Reason canonico",
            "authorized": True,
            "latest_rr_file": "rr_2026-06-30_morning.csv",
            "latest_rr_path": "/data/rr_downloads/rr_2026-06-30_morning.csv",
        }
        diagnostics.update(ui_view.compose_hrv_summary(diagnostics))
        return diagnostics

    def test_view_contains_versioned_root_with_known_sections(self):
        view = ui_view.build_view(self._base_diagnostics())
        self.assertEqual(view["version"], ui_view.VIEW_VERSION)
        self.assertEqual(set(view.keys()), {"version", "hrv_today", "system"})

    def test_hrv_today_carries_preformatted_strings(self):
        view = ui_view.build_view(self._base_diagnostics())
        hrv = view["hrv_today"]
        self.assertTrue(hrv["exists"])
        self.assertEqual(hrv["date"], "2026-06-30")
        self.assertIn("42.0 ms", hrv["raw_text"])
        self.assertIn("ln 3.700", hrv["used_text"])
        self.assertIn("ln 3.680", hrv["base_text"])
        self.assertNotIn("SWC", hrv["base_text"])
        self.assertEqual(hrv["gate"]["badge"], "VERDE")
        self.assertIn("Dia verde.", hrv["ai_text"])
        self.assertEqual(hrv["reason_text"], "Reason canonico")
        self.assertIsNone(hrv["fallback_text"])

    def test_base_text_uses_precomputed_base60_ms_when_present(self):
        diagnostics = self._base_diagnostics()
        diagnostics["final_last_base60_ms"] = 999.9
        view = ui_view.build_view(diagnostics)
        self.assertIn("999.9 ms", view["hrv_today"]["base_text"])

    def test_base_text_falls_back_to_ln_base60_when_base60_ms_absent(self):
        diagnostics = self._base_diagnostics()
        diagnostics.pop("final_last_base60_ms", None)
        view = ui_view.build_view(diagnostics)
        self.assertIn(f"{math.exp(3.68):.1f} ms", view["hrv_today"]["base_text"])

    def test_hrv_today_exposes_quality_stability_and_gate_block(self):
        diagnostics = self._base_diagnostics()
        diagnostics.update({
            "final_last_calidad": "OK",
            "final_last_hrv_stability": "OK",
            "final_last_gate_badge": "ROJO---",
            "final_last_action_detail": "SUAVE_O_DESCANSO",
            "final_last_gate_what_happened": "La señal suavizada bajó...",
            "final_last_gate_what_to_do": "Trata hoy como un día más delicado...",
        })
        view = ui_view.build_view(diagnostics)
        hrv = view["hrv_today"]
        self.assertEqual(hrv["quality"], "OK")
        self.assertEqual(hrv["stability"], "OK")
        self.assertEqual(hrv["gate"]["badge"], "ROJO---")
        self.assertEqual(hrv["gate"]["action"], "SUAVE_O_DESCANSO")
        self.assertIn("La señal suavizada bajó", hrv["gate"]["what_happened"])
        self.assertIn("Trata hoy", hrv["gate"]["what_to_do"])

    def test_view_version_is_two(self):
        self.assertEqual(ui_view.VIEW_VERSION, 2)

    def test_hrv_today_when_final_missing(self):
        view = ui_view.build_view({"final_exists": False, **ui_view.compose_hrv_summary({})})
        hrv = view["hrv_today"]
        self.assertFalse(hrv["exists"])
        self.assertIsNone(hrv["date"])
        self.assertIsNone(hrv["ai_text"])
        self.assertEqual(hrv["fallback_text"], ui_view.DEFAULT_UNAVAILABLE_TEXT)

    def test_system_section_includes_latest_rr_label(self):
        view = ui_view.build_view(self._base_diagnostics())
        system = view["system"]
        self.assertTrue(system["authorized"])
        self.assertEqual(system["latest_rr_file"], "rr_2026-06-30_morning.csv")
        self.assertEqual(
            system["latest_rr_label"],
            "rr_2026-06-30_morning.csv (30/06/2026)",
        )

    def test_system_section_when_no_latest_rr(self):
        view = ui_view.build_view(
            {
                "final_exists": False,
                "authorized": False,
                **ui_view.compose_hrv_summary({}),
            }
        )
        system = view["system"]
        self.assertFalse(system["authorized"])
        self.assertIsNone(system["latest_rr_file"])
        self.assertEqual(system["latest_rr_label"], "")


if __name__ == "__main__":
    unittest.main()
