import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import numpy as np
import pandas as pd

import build_hrv_final_dashboard as final_builder


def _core_frame() -> pd.DataFrame:
    dates = pd.date_range("2026-01-01", periods=40, freq="D")
    rows = []
    for idx, fecha in enumerate(dates):
        lnrmssd = 3.70 + (0.03 if idx % 2 == 0 else -0.03)
        hr_stable = 50.0 + [0.0, 0.7, -0.6][idx % 3]
        rrbar_s = 1.10 + [0.00, 0.01, -0.01, 0.02][idx % 4]
        rows.append(
            {
                "Fecha": fecha.strftime("%Y-%m-%d"),
                "Calidad": "OK",
                "HRV_Stability": "OK",
                "Artifact_pct": 0.0,
                "Tiempo_Estabilizacion": 60.0,
                "lnRMSSD": lnrmssd,
                "HR_stable": hr_stable,
                "RMSSD_stable": float(np.exp(lnrmssd)),
                "RRbar_s": rrbar_s,
            }
        )
    return pd.DataFrame(rows)


def _write_sleep(data_dir: Path, rows: list[dict[str, object]]) -> None:
    pd.DataFrame(rows).to_csv(data_dir / "ENDURANCE_HRV_sleep.csv", index=False)


def _write_sessions_day(data_dir: Path, rows: list[dict[str, object]]) -> None:
    pd.DataFrame(rows).to_csv(data_dir / "ENDURANCE_HRV_sessions_day.csv", index=False)


class BuildFinalDashboardContractTests(unittest.TestCase):
    def test_parse_args_ignores_flags_without_value(self):
        self.assertEqual(final_builder.parse_args(["--decision-mode"]), {})
        self.assertEqual(final_builder.parse_args(["--data-dir"]), {})
        self.assertEqual(
            final_builder.parse_args(["--data-dir", "data", "--decision-mode", "O2_SHADOW"]),
            {"data_dir": "data", "decision_mode": "O2_SHADOW"},
        )

    def test_red_without_recent_load_uses_sleep_specific_wording_only_when_sleep_exists(self):
        core = _core_frame()
        for idx in (-4, -3, -2):
            core.loc[len(core) + idx, "lnRMSSD"] = 3.45
            core.loc[len(core) + idx, "RMSSD_stable"] = float(np.exp(3.45))
            core.loc[len(core) + idx, "HR_stable"] = 54.5

        with TemporaryDirectory() as tmpdir:
            data_dir = Path(tmpdir)
            _write_sessions_day(
                data_dir,
                [
                    {
                        "Fecha": "2026-02-08",
                        "load_day": 15,
                        "load_3d": 75,
                        "load_3d_nobs": 3,
                    }
                ],
            )
            with patch.object(final_builder, "DATA_DIR", data_dir):
                final_no_sleep, _ = final_builder.build_final_and_dashboard(core, final_builder.Config())

        row_no_sleep = final_no_sleep.loc[final_no_sleep["Fecha"] == "2026-02-08"].iloc[0]
        self.assertIn("ROJO sin carga previa reciente: revisar otros factores", row_no_sleep["reason_text"])
        self.assertNotIn("ni sueño malo", row_no_sleep["reason_text"])

        with TemporaryDirectory() as tmpdir:
            data_dir = Path(tmpdir)
            _write_sessions_day(
                data_dir,
                [
                    {
                        "Fecha": "2026-02-08",
                        "load_day": 15,
                        "load_3d": 75,
                        "load_3d_nobs": 3,
                    }
                ],
            )
            _write_sleep(
                data_dir,
                [
                    {
                        "Fecha": "2026-02-08",
                        "polar_sleep_duration_min": 420,
                        "polar_interruptions_long": 2,
                        "sleep_dur_p10": 360,
                        "sleep_int_p90": 8,
                    }
                ],
            )
            with patch.object(final_builder, "DATA_DIR", data_dir):
                final_with_sleep, _ = final_builder.build_final_and_dashboard(core, final_builder.Config())

        row_with_sleep = final_with_sleep.loc[final_with_sleep["Fecha"] == "2026-02-08"].iloc[0]
        self.assertIn("ROJO sin carga previa ni sueño malo: revisar otros factores", row_with_sleep["reason_text"])

    def test_single_load_caution_on_green_does_not_emit_recovery_fragile_closure(self):
        core = _core_frame()

        with TemporaryDirectory() as tmpdir:
            data_dir = Path(tmpdir)
            _write_sessions_day(
                data_dir,
                [
                    {
                        "Fecha": "2026-02-08",
                        "load_day": 70,
                        "load_3d": 210,
                        "load_3d_nobs": 3,
                    }
                ],
            )

            with patch.object(final_builder, "DATA_DIR", data_dir):
                final, _ = final_builder.build_final_and_dashboard(core, final_builder.Config())

        row = final.loc[final["Fecha"] == "2026-02-08"].iloc[0]
        self.assertEqual(row["gate_final"], "VERDE")
        self.assertEqual(row["recovery_support_class"], "neutral")
        self.assertFalse(row["recovery_discordance_flag"])
        self.assertIn("VERDE con carga acumulada (load_3d=210): precaución intensidad", row["reason_text"])
        self.assertNotIn("VERDE con recuperación frágil", row["reason_text"])

    def test_reason_text_adds_fragile_recovery_warning_on_ffill_clustering_window(self):
        core = _core_frame()

        with TemporaryDirectory() as tmpdir:
            data_dir = Path(tmpdir)
            _write_sessions_day(
                data_dir,
                [
                    {
                        "Fecha": "2026-02-07",
                        "intense_days_prev_3d": 2,
                        "intense_days_prev_5d": 3,
                        "intensity_clustering_flag": 1,
                        "intensity_clustering_level": "high",
                    }
                ],
            )
            _write_sleep(
                data_dir,
                [
                    {
                        "Fecha": "2026-02-08",
                        "polar_sleep_duration_min": 330,
                        "polar_interruptions_long": 4,
                        "sleep_dur_p10": 360,
                        "sleep_int_p90": 8,
                    }
                ],
            )

            with patch.object(final_builder, "DATA_DIR", data_dir):
                final, _ = final_builder.build_final_and_dashboard(core, final_builder.Config())

        row = final.loc[final["Fecha"] == "2026-02-08"].iloc[0]
        self.assertEqual(row["gate_final"], "VERDE")
        self.assertEqual(row["recovery_context_quality"], "basic")
        self.assertEqual(row["recovery_support_class"], "fragile")
        self.assertTrue(row["recovery_discordance_flag"])
        self.assertIn("sleep_basic_poor", row["recovery_discordance_reason"])
        self.assertIn(
            "VERDE pero clustering alto de intensidad reciente: considera Z1 mañana (2/3d · 3/5d)",
            row["reason_text"],
        )
        self.assertIn("VERDE con recuperación frágil", row["reason_text"])

    def test_recovery_context_marks_amber_as_supported_when_night_and_load_are_favorable(self):
        core = _core_frame()
        for idx in (-4, -3, -2):
            core.loc[len(core) + idx, "lnRMSSD"] = 3.52
            core.loc[len(core) + idx, "RMSSD_stable"] = float(np.exp(3.52))

        with TemporaryDirectory() as tmpdir:
            data_dir = Path(tmpdir)
            _write_sleep(
                data_dir,
                [
                    {
                        "Fecha": "2026-02-08",
                        "polar_sleep_duration_min": 425,
                        "polar_interruptions_long": 2,
                        "sleep_dur_p10": 360,
                        "sleep_int_p90": 8,
                        "polar_sleep_score": 82,
                        "polar_night_rmssd": 48,
                    }
                ],
            )
            _write_sessions_day(
                data_dir,
                [
                    {
                        "Fecha": "2026-02-08",
                        "load_day": 20,
                        "load_3d": 80,
                        "load_3d_nobs": 3,
                    }
                ],
            )

            with patch.object(final_builder, "DATA_DIR", data_dir):
                final, _ = final_builder.build_final_and_dashboard(core, final_builder.Config())

        row = final.loc[final["Fecha"] == "2026-02-08"].iloc[0]
        self.assertEqual(row["gate_final"], "ÁMBAR")
        self.assertEqual(row["recovery_context_quality"], "rich")
        self.assertEqual(row["recovery_support_class"], "supported")
        self.assertFalse(row["recovery_discordance_flag"])
        self.assertEqual(row["recovery_discordance_reason"], "")
        self.assertIn("ÁMBAR con soporte nocturno aceptable", row["reason_text"])

    def test_recovery_context_marks_rojo_as_conflicted_when_support_signals_are_good(self):
        core = _core_frame()
        for idx in (-4, -3, -2):
            core.loc[len(core) + idx, "lnRMSSD"] = 3.45
            core.loc[len(core) + idx, "RMSSD_stable"] = float(np.exp(3.45))
            core.loc[len(core) + idx, "HR_stable"] = 54.5

        with TemporaryDirectory() as tmpdir:
            data_dir = Path(tmpdir)
            _write_sleep(
                data_dir,
                [
                    {
                        "Fecha": "2026-02-08",
                        "polar_sleep_duration_min": 430,
                        "polar_interruptions_long": 2,
                        "sleep_dur_p10": 360,
                        "sleep_int_p90": 8,
                        "polar_sleep_score": 84,
                        "polar_night_rmssd": 50,
                    }
                ],
            )
            _write_sessions_day(
                data_dir,
                [
                    {
                        "Fecha": "2026-02-08",
                        "load_day": 15,
                        "load_3d": 75,
                        "load_3d_nobs": 3,
                    }
                ],
            )

            with patch.object(final_builder, "DATA_DIR", data_dir):
                final, _ = final_builder.build_final_and_dashboard(core, final_builder.Config())

        row = final.loc[final["Fecha"] == "2026-02-08"].iloc[0]
        self.assertEqual(row["gate_final"], "ROJO")
        self.assertEqual(row["recovery_context_quality"], "rich")
        self.assertEqual(row["recovery_support_class"], "conflicted")
        self.assertTrue(row["recovery_discordance_flag"])
        self.assertIn("sleep_score_good", row["recovery_discordance_reason"])
        self.assertIn("ROJO con nightly_rmssd alto (50ms): posible confusor", row["reason_text"])
        self.assertIn("ROJO con discordancia objetiva", row["reason_text"])

    def test_rojo_supported_omits_legacy_nightly_confusor_message(self):
        core = _core_frame()
        for idx in (-4, -3, -2):
            core.loc[len(core) + idx, "lnRMSSD"] = 3.45
            core.loc[len(core) + idx, "RMSSD_stable"] = float(np.exp(3.45))
            core.loc[len(core) + idx, "HR_stable"] = 54.5

        with TemporaryDirectory() as tmpdir:
            data_dir = Path(tmpdir)
            _write_sleep(
                data_dir,
                [
                    {
                        "Fecha": "2026-02-08",
                        "polar_sleep_duration_min": 330,
                        "polar_interruptions_long": 12,
                        "sleep_dur_p10": 360,
                        "sleep_int_p90": 8,
                        "polar_night_rmssd": 58,
                    }
                ],
            )
            _write_sessions_day(
                data_dir,
                [
                    {
                        "Fecha": "2026-02-08",
                        "load_day": 120,
                        "load_3d": 260,
                        "load_3d_nobs": 3,
                        "intense_days_prev_3d": 2,
                        "intense_days_prev_5d": 3,
                        "intensity_clustering_flag": 1,
                        "intensity_clustering_level": "high",
                    }
                ],
            )

            with patch.object(final_builder, "DATA_DIR", data_dir):
                final, _ = final_builder.build_final_and_dashboard(core, final_builder.Config())

        row = final.loc[final["Fecha"] == "2026-02-08"].iloc[0]
        self.assertEqual(row["gate_final"], "ROJO")
        self.assertEqual(row["recovery_support_class"], "supported")
        self.assertFalse(row["recovery_discordance_flag"])
        self.assertIn("ROJO respaldado por mala recuperación o carga reciente", row["reason_text"])
        self.assertNotIn("ROJO con nightly_rmssd alto", row["reason_text"])


if __name__ == "__main__":
    unittest.main()
