import contextlib
import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd

import hrv_app.cli_reporting as cli_reporting


class CliReportingContractTests(unittest.TestCase):
    def test_format_gate_reason_translates_known_codes(self):
        cases = {
            "CAL/STAB/ART/NaN": "La toma de hoy no fue lo bastante fiable para usarla.",
            "ROLL3_INSUF": "Aún faltan días limpios seguidos para construir una referencia fiable",
            "BASE60_INSUF": "Todavía no hay suficientes datos limpios en la ventana de 60 días",
            "SWC_NAN/0": "La referencia estadística de hoy salió vacía o demasiado plana",
            "RAW_NAN/0": "La señal bruta llegó vacía o inválida",
            "2D_OK": "La medición de hoy quedó dentro de tu rango reciente",
            "2D_LN": "La variabilidad de hoy bajó respecto a tu base reciente",
            "2D_HR": "La frecuencia cardiaca de hoy subió respecto a tu base reciente",
            "2D_AMBOS": "La variabilidad bajó y la frecuencia cardiaca subió respecto a tu base reciente",
        }

        for code, expected_snippet in cases.items():
            with self.subTest(code=code):
                text = cli_reporting._format_gate_reason(code)
                self.assertIn(expected_snippet, text)

        self.assertEqual(cli_reporting._format_gate_reason(""), "N/A")
        self.assertIn("no traducido", cli_reporting._format_gate_reason("XYZ_UNKNOWN"))

        self.assertEqual(cli_reporting._format_gate_next_step(""), "N/A")
        self.assertIn("sensor bien colocado", cli_reporting._format_gate_next_step("CAL/STAB/ART/NaN"))

    def test_show_last_daily_summary_prefers_final(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            final_path = tmp_path / "ENDURANCE_HRV_master_FINAL.csv"
            core_path = tmp_path / "ENDURANCE_HRV_master_CORE.csv"

            pd.DataFrame(
                [
                    {
                        "Fecha": "2024-01-01",
                        "HR_today": 51.2,
                        "RMSSD_stable": 42.8,
                        "gate_badge": "VERDE",
                        "Action": "seguir",
                        "Action_detail": "EJECUTAR_PLAN",
                        "gate_razon_base60": "CAL/STAB/ART/NaN",
                        "decision_path": "BASE60_ONLY",
                        "recovery_support_class": "supported",
                        "recovery_context_quality": "rich",
                        "recovery_discordance_reason": "",
                        "reason_text": "VERDE con carga aguda 72h (acute_load_72h_rel=4.20x; load_3d=210): precaución con la intensidad",
                        "Artifact_pct": 18.4,
                        "Tiempo_Estabilizacion": 72,
                        "HRV_Stability": "Media",
                        "Stability_Subtype": "Inestable",
                        "ln_base60": 3.75,
                        "n_base60": 41,
                        "Calidad": "A",
                        "healthy_rmssd": 54.2,
                        "warning_threshold": 46.1,
                        "baseline60_degraded": False,
                    }
                ]
            ).to_csv(final_path, index=False)

            pd.DataFrame(
                [
                    {
                        "Fecha": "2024-01-01",
                        "HR_stable": 60.0,
                        "RMSSD_stable": 30.0,
                        "Calidad": "B",
                        "HRV_Stability": "Media",
                    }
                ]
            ).to_csv(core_path, index=False)

            buffer = io.StringIO()
            with (
                patch.object(cli_reporting, "FINAL_PATH", final_path),
                patch.object(cli_reporting, "CORE_PATH", core_path),
                patch.object(cli_reporting, "PANDAS_AVAILABLE", True),
                contextlib.redirect_stdout(buffer),
            ):
                cli_reporting.show_last_daily_summary()

            output = buffer.getvalue()
            self.assertIn("Última Medición HRV (V4)", output)
            self.assertIn("📅 Fecha:           2024-01-01", output)
            self.assertIn("💓 HR hoy:          51.2 bpm", output)
            self.assertIn("🚦 Gate:            🟢 VERDE", output)
            self.assertIn(
                "🧾 Qué pasó:        La toma de hoy no fue lo bastante fiable para usarla.",
                output,
            )
            self.assertIn(
                "🧾 Qué hacer:       Repite la toma en un momento más tranquilo, sin moverte y con el sensor bien colocado.",
                output,
            )
            self.assertIn("Pistas del registro:", output)
            self.assertIn("artefactos altos (18.4%)", output)
            self.assertIn("estabilización de 72s", output)
            self.assertIn("estabilidad de señal Media", output)
            self.assertIn("🧠 Reason text:     VERDE con carga aguda 72h (acute_load_72h_rel=4.20x; load_3d=210): precaución con la intensidad", output)
            self.assertIn("🧪 Contexto recuperación: contexto completo / senales alineadas", output)
            self.assertIn("📐 Base 60d:        42.5 ms (n=41)", output)
            self.assertIn("⚠️  Límite inferior de referencia: 46.1 ms", output)
            self.assertGreater(
                output.index("🧠 Reason text:"),
                output.index("⚠️  Límite inferior de referencia: 46.1 ms"),
            )
            self.assertNotIn("🧩 Decision path:", output)
            self.assertNotIn("Base 60d por debajo de tu referencia habitual", output)
            self.assertNotIn("\n\n📅 Fecha:", output)
            self.assertNotIn("Healthy period", output)
            self.assertNotIn("HR promedio", output)

    def test_show_last_daily_summary_falls_back_to_core(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            final_path = tmp_path / "missing_final.csv"
            core_path = tmp_path / "ENDURANCE_HRV_master_CORE.csv"

            pd.DataFrame(
                [
                    {
                        "Fecha": "2024-01-02",
                        "HR_stable": 59.1,
                        "RMSSD_stable": 31.4,
                        "Calidad": "B",
                        "HRV_Stability": "Media",
                        "Flags": "test-flag",
                    }
                ]
            ).to_csv(core_path, index=False)

            buffer = io.StringIO()
            with (
                patch.object(cli_reporting, "FINAL_PATH", final_path),
                patch.object(cli_reporting, "CORE_PATH", core_path),
                patch.object(cli_reporting, "PANDAS_AVAILABLE", True),
                contextlib.redirect_stdout(buffer),
            ):
                cli_reporting.show_last_daily_summary()

            output = buffer.getvalue()
            self.assertIn("Última Medición HRV (CORE)", output)
            self.assertIn("💓 HR promedio:    59.1 bpm", output)
            self.assertIn("🚩 Flags:          test-flag", output)


if __name__ == "__main__":
    unittest.main()
