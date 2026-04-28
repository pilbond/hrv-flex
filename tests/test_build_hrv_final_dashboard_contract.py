import inspect
import json
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

    def test_emit_reason_builds_structured_item_and_render_text(self):
        reason_items = [[]]
        reason_parts = [[]]

        final_builder._emit_reason(
            reason_items,
            reason_parts,
            0,
            type="acwr",
            layer="inference",
            source="sessions_day",
            variant="high",
            severity="high",
            metric="acwr_simple_prev",
            value=1.4,
            threshold=1.3,
            gate_scope="green",
            codes=["load_context_high"],
            evidence=["acwr_simple_prev=1.4"],
            message="Carga reciente por encima de tu base habitual (ACWR=1.40)",
        )

        self.assertEqual(reason_parts[0], ["Carga reciente por encima de tu base habitual (ACWR=1.40)"])
        self.assertEqual(reason_items[0][0]["type"], "acwr")
        self.assertEqual(reason_items[0][0]["layer"], "inference")
        self.assertEqual(reason_items[0][0]["source"], "sessions_day")
        self.assertEqual(reason_items[0][0]["metric"], "acwr_simple_prev")
        self.assertEqual(reason_items[0][0]["codes"], ["load_context_high"])
        self.assertEqual(reason_items[0][0]["evidence"], ["acwr_simple_prev=1.4"])

        final_builder._emit_reason(
            reason_items,
            reason_parts,
            0,
            type="data_quality",
            layer="measured",
            source="hrv_pipeline",
            gate_scope="green_or_amber",
            metric="Artifact_pct",
            value=12.5,
            threshold=15.0,
            evidence=["Tiempo_Estabilizacion=75s"],
            message="Dato dudoso: limitar a Z1-Z2 máx 90min",
        )

        final_builder._emit_reason(
            reason_items,
            reason_parts,
            0,
            type="action_constraint",
            layer="action",
            source="gate_final",
            variant="fragile",
            message="contener la intensidad",
        )

        self.assertEqual(
            reason_parts[0],
            [
                "Carga reciente por encima de tu base habitual (ACWR=1.40)",
                "Dato dudoso: limitar a Z1-Z2 máx 90min",
                "contener la intensidad",
            ],
        )
        self.assertEqual(reason_items[0][1]["type"], "data_quality")
        self.assertEqual(reason_items[0][1]["layer"], "measured")
        self.assertEqual(reason_items[0][1]["metric"], "Artifact_pct")
        self.assertEqual(reason_items[0][1]["value"], 12.5)
        self.assertEqual(reason_items[0][1]["threshold"], 15.0)
        self.assertEqual(reason_items[0][1]["evidence"], ["Tiempo_Estabilizacion=75s"])
        self.assertEqual(reason_items[0][2]["type"], "action_constraint")
        self.assertEqual(reason_items[0][2]["layer"], "action")

    def test_emit_reason_rejects_invalid_layer(self):
        with self.assertRaises(AssertionError):
            final_builder._emit_reason(
                [[]],
                [[]],
                0,
                type="bad",
                layer="context",
                source="test",
                message="nope",
            )

    def test_emit_reason_rejects_invalid_severity(self):
        with self.assertRaises(AssertionError):
            final_builder._emit_reason(
                [[]],
                [[]],
                0,
                type="bad",
                layer="inference",
                source="test",
                severity="critical",
                message="nope",
            )

    def test_emit_reason_omits_none_optional_fields(self):
        reason_items = [[]]
        reason_parts = [[]]

        final_builder._emit_reason(
            reason_items,
            reason_parts,
            0,
            type="acwr",
            layer="inference",
            source="sessions_day",
            message="Carga reciente baja frente a tu base habitual (ACWR=0.80)",
        )

        item = reason_items[0][0]
        self.assertEqual(item["type"], "acwr")
        self.assertEqual(item["layer"], "inference")
        self.assertEqual(item["source"], "sessions_day")
        self.assertEqual(item["message"], "Carga reciente baja frente a tu base habitual (ACWR=0.80)")
        self.assertNotIn("variant", item)
        self.assertNotIn("severity", item)
        self.assertNotIn("metric", item)

    def test_parasympathetic_reason_uses_local_base_language(self):
        reason_items = [[]]
        reason_parts = [[]]

        final_builder._emit_reason(
            reason_items,
            reason_parts,
            0,
            type="parasympathetic_saturation",
            layer="inference",
            source="hrv_pipeline",
            metric="d_ln",
            value=0.08,
            threshold=0.04,
            message="RMSSD suavizado de 3 días por encima de tu base reciente: posible saturación parasimpática relativa al rango local",
        )

        self.assertEqual(
            reason_parts[0],
            ["RMSSD suavizado de 3 días por encima de tu base reciente: posible saturación parasimpática relativa al rango local"],
        )
        self.assertEqual(reason_items[0][0]["type"], "parasympathetic_saturation")

    def test_reason_parts_append_is_only_used_inside_helper(self):
        source = inspect.getsource(final_builder)
        append_lines = [
            line.strip()
            for line in source.splitlines()
            if "reason_parts[" in line and ".append(" in line
        ]
        self.assertEqual(append_lines, ["reason_parts[idx].append(message)"])

    def test_build_emits_only_allowed_reason_layers(self):
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
                    },
                    {
                        "Fecha": "2026-02-08",
                        "load_day": 15,
                        "load_3d": 75,
                        "load_3d_nobs": 3,
                    },
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

            captured_layers: list[str] = []
            original_emit_reason = final_builder._emit_reason

            def capture_emit_reason(*args, **kwargs):
                captured_layers.append(kwargs["layer"])
                return original_emit_reason(*args, **kwargs)

            with patch.object(final_builder, "DATA_DIR", data_dir), patch.object(
                final_builder, "_emit_reason", side_effect=capture_emit_reason
            ):
                final, _ = final_builder.build_final_and_dashboard(core, final_builder.Config())

        self.assertFalse(final.empty)
        self.assertTrue(set(captured_layers).issubset(final_builder._VALID_LAYERS))
        self.assertIn("inference", captured_layers)
        self.assertIn("action", captured_layers)

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
        self.assertIn(
            "ROJO sin carga previa reciente: revisar factores externos al entrenamiento",
            row_no_sleep["reason_text"],
        )
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
        self.assertIn(
            "ROJO sin carga previa ni sueño malo: revisar factores externos al entrenamiento",
            row_with_sleep["reason_text"],
        )

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
        self.assertIn("VERDE con carga acumulada (load_3d=210): precaución con la intensidad", row["reason_text"])
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
            "VERDE pero con 2 días intensos en los últimos 3 (y 3 en los últimos 5): conviene prudencia con la intensidad",
            row["reason_text"],
        )
        self.assertIn("VERDE, pero sueño y carga reciente piden prudencia", row["reason_text"])
        sidecar = final.attrs["reason_items_sidecar"]
        reason_items = sidecar["items_by_date"]["2026-02-08"]
        reason_types = {item["type"] for item in reason_items}
        self.assertEqual(sidecar["schema_version"], "1.0")
        self.assertEqual(sidecar["source"], "build_hrv_final_dashboard.py")
        self.assertIn("recovery_discordance", reason_types)
        self.assertIn("action_constraint", reason_types)

    def test_recovery_discordance_message_falls_back_with_context_when_summary_is_empty(self):
        message = final_builder._recovery_discordance_message("VERDE", "fragile", "basic", "")
        self.assertIn("Discordancia de recuperación", message)
        self.assertIn("VERDE", message)
        self.assertIn("fragile", message)
        self.assertIn("cobertura=basic", message)

    def test_main_writes_reason_items_sidecar_json(self):
        core = _core_frame()

        with TemporaryDirectory() as tmpdir:
            data_dir = Path(tmpdir)
            core.to_csv(data_dir / "ENDURANCE_HRV_master_CORE.csv", index=False)
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

            exit_code = final_builder.main(["--data-dir", str(data_dir)])

            self.assertEqual(exit_code, 0)
            sidecar_path = data_dir / "ENDURANCE_HRV_master_FINAL_reason_items.json"
            self.assertTrue(sidecar_path.exists())
            payload = json.loads(sidecar_path.read_text(encoding="utf-8"))
            self.assertEqual(payload["schema_version"], "1.0")
            self.assertEqual(payload["source"], "build_hrv_final_dashboard.py")
            self.assertIn("2026-02-08", payload["items_by_date"])
            self.assertTrue(payload["items_by_date"]["2026-02-08"])

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
        self.assertIn("ÁMBAR con señales nocturnas favorables", row["reason_text"])

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
        self.assertIn(
            "ROJO, pero el HRV de sueño salió alto (50ms): la recuperación nocturna fue mejor de lo esperado",
            row["reason_text"],
        )
        self.assertIn("ROJO, pero sueño y carga reciente no encajan con un rojo claro", row["reason_text"])

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
        self.assertIn("ROJO respaldado por mala recuperación y carga reciente", row["reason_text"])
        self.assertNotIn("ROJO, pero el HRV de sueño salió alto", row["reason_text"])

    def test_build_clustering_window_suffix_is_compact_for_non_green_messages(self):
        self.assertEqual(
            final_builder._build_clustering_window_suffix(2, 4),
            "2 intensos en últimos 3d; 4 en últimos 5d",
        )
        self.assertEqual(
            final_builder._build_clustering_window_suffix(2, None),
            "2 intensos en últimos 3d",
        )
        self.assertEqual(
            final_builder._build_clustering_window_suffix(None, 4),
            "4 en últimos 5d",
        )

    def test_build_clustering_window_clause_handles_singular_and_plural(self):
        self.assertEqual(
            final_builder._build_clustering_window_clause(1, None),
            "1 día intenso en los últimos 3",
        )
        self.assertEqual(
            final_builder._build_clustering_window_clause(None, 1),
            "1 día intenso en los últimos 5",
        )
        self.assertEqual(
            final_builder._build_clustering_window_clause(1, 2),
            "1 día intenso en los últimos 3 (y 2 en los últimos 5)",
        )
        self.assertEqual(
            final_builder._build_clustering_window_clause(2, None),
            "2 días intensos en los últimos 3",
        )


if __name__ == "__main__":
    unittest.main()
