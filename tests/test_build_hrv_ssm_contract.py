import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

import numpy as np
import pandas as pd

import build_hrv_ssm as ssm_builder


def _core_frame() -> pd.DataFrame:
    dates = pd.date_range("2026-01-01", periods=55, freq="D")
    rows = []
    for idx, fecha in enumerate(dates):
        rows.append(
            {
                "Fecha": fecha.strftime("%Y-%m-%d"),
                "Calidad": "OK" if idx != 7 else "FLAG_mecánico",
                "HRV_Stability": "OK" if idx % 11 else "WARN",
                "Artifact_pct": 0.0 if idx != 10 else 8.0,
                "lnRMSSD": 3.85 + (0.04 * np.sin(idx / 6.0)) if idx != 14 else np.nan,
                "Flags": "" if idx != 20 else "BETA_FROZEN",
            }
        )
    return pd.DataFrame(rows)


def _sessions_day_frame() -> pd.DataFrame:
    dates = pd.date_range("2026-01-01", periods=55, freq="D")
    rows = []
    for idx, fecha in enumerate(dates):
        if idx in {5, 6, 7, 30}:
            continue
        rows.append(
            {
                "Fecha": fecha.strftime("%Y-%m-%d"),
                "load_day": float(60 + (idx % 5) * 10) if idx != 18 else np.nan,
                "load_7d": float(300 + idx),
                "cardiac_drift_worst": 0.05 + (idx * 0.001),
                "effort_above_anchor_aerobic": 0.10 + (idx * 0.002),
                "effort_above_typical_aerobic": 0.08 + (idx * 0.001),
                "rpe_max_day": float(4 + (idx % 4)),
            }
        )
    return pd.DataFrame(rows)


def _wellness_frame() -> pd.DataFrame:
    dates = pd.date_range("2026-01-01", periods=55, freq="D")
    return pd.DataFrame(
        {
            "Fecha": [fecha.strftime("%Y-%m-%d") for fecha in dates],
            "well_fatigue_raw": [2 + (idx % 3) for idx in range(len(dates))],
            "well_comment_raw": [""] * len(dates),
        }
    )


def _sleep_frame() -> pd.DataFrame:
    dates = pd.date_range("2026-01-01", periods=55, freq="D")
    rows = []
    for idx, fecha in enumerate(dates):
        rows.append(
            {
                "Fecha": fecha.strftime("%Y-%m-%d"),
                "polar_sleep_duration_min": 420.0 + (idx % 5) * 4,
                "polar_sleep_span_min": 445.0 + (idx % 5) * 4,
                "polar_efficiency_pct": 93.0 + (idx % 3) * 0.3,
                "polar_continuity_index": 2.6 + (idx % 4) * 0.1,
                "polar_interruptions_long": float(2 + (idx % 3)),
                "polar_interruptions_total": float(18 + (idx % 6)),
                "polar_sleep_score": float(72 + (idx % 6)),
                "polar_night_rmssd": 42.0 + (idx % 7) * 1.5,
                "sleep_dur_p10": 365.0,
                "sleep_dur_p90": 495.0,
                "sleep_int_p90": 8.0,
            }
        )
    return pd.DataFrame(rows)


class BuildHRVSSMContractTests(unittest.TestCase):
    def test_beta_frozen_alone_does_not_degrade_observation_weight(self):
        base = ssm_builder._prepare_daily_frame(_core_frame(), _sessions_day_frame())
        base["Calidad"] = "OK"
        base["HRV_Stability"] = "OK"
        base["Artifact_pct"] = 0.0
        base["Flags"] = ""
        base.loc[10, "Flags"] = "BETA_FROZEN"

        quality = ssm_builder._derive_obs_quality(base, ssm_builder.CFG)

        self.assertEqual(float(quality.loc[10, "ssm_obs_var_multiplier"]), 1.0)
        self.assertEqual(str(quality.loc[10, "ssm_input_quality"]), "clean")

    def test_build_ssm_shadow_emits_contract_columns_and_warmup_state(self):
        sidecar, metadata = ssm_builder.build_ssm_shadow(_core_frame(), _sessions_day_frame(), _wellness_frame(), sleep_df=_sleep_frame())

        self.assertEqual(list(sidecar.columns), ssm_builder.SIDE_CAR_COLUMNS)
        self.assertEqual(len(sidecar), 55)
        self.assertTrue(sidecar["ssm_warmup_complete"].astype(bool).any())
        self.assertTrue(sidecar["ssm_recovery_state"].notna().any())
        self.assertIn("ssm_baseline_state", sidecar.columns)
        self.assertIn("ssm_fatigue_state", sidecar.columns)
        self.assertIn("sleep_recovery_index", sidecar.columns)
        self.assertTrue(sidecar["sleep_recovery_index"].notna().any())
        self.assertIn("calendar_gap_no_session", set(sidecar["ssm_load_context_mode"]))
        self.assertIn(metadata["outcome_audit"]["outcome_audit_status"], {"pass", "no_validatable_current_data"})
        state_mean = sidecar["ssm_recovery_state"].dropna().mean()
        rolling_mean = sidecar["control_rolling_hrv_7d"].dropna().mean()
        self.assertLess(abs(state_mean - rolling_mean), 0.75)
        self.assertIn("state_anchor_mu", metadata["kalman_diagnostics"])
        self.assertIn("sleep_observation_coverage_n", metadata["kalman_diagnostics"])
        self.assertIn("sleep_nightly_rmssd_fit", metadata["kalman_diagnostics"])
        self.assertIn("innovation_mean", metadata["kalman_diagnostics"])
        self.assertIn("innovation_abs_p90", metadata["kalman_diagnostics"])
        self.assertIn("interval_scale_factor", metadata["kalman_diagnostics"])
        self.assertIn("interval_coverage_90pct", metadata["kalman_diagnostics"])
        self.assertIn("interval_coverage_ci95", metadata["kalman_diagnostics"])
        self.assertIn("daily_user_summary", metadata)
        self.assertEqual(metadata["daily_user_summary"]["status"], "ok")
        self.assertIn("interpretive_text", metadata["daily_user_summary"])
        self.assertIn("ssm_baseline_state", metadata["daily_user_summary"])
        self.assertIn("ssm_fatigue_state", metadata["daily_user_summary"])
        self.assertIn("histórico del SSM", metadata["daily_user_summary"]["interpretive_text"])
        self.assertIn("rolling HRV 7d", metadata["daily_user_summary"]["interpretive_text"])
        self.assertIn("innovation", metadata["daily_user_summary"])
        self.assertIn("sleep_recovery_index", metadata["daily_user_summary"])

    def test_main_writes_sidecar_and_metadata_files(self):
        with TemporaryDirectory() as tmpdir:
            data_dir = Path(tmpdir)
            _core_frame().to_csv(data_dir / "ENDURANCE_HRV_master_CORE.csv", index=False)
            _sessions_day_frame().to_csv(data_dir / "ENDURANCE_HRV_sessions_day.csv", index=False)
            _sleep_frame().to_csv(data_dir / "ENDURANCE_HRV_sleep.csv", index=False)
            _wellness_frame().to_csv(data_dir / "ENDURANCE_HRV_wellness_subjective.csv", index=False)

            with mock.patch.object(ssm_builder, "_kalman_shadow", wraps=ssm_builder._kalman_shadow) as kalman_spy:
                exit_code = ssm_builder.main(["--data-dir", str(data_dir)])

            self.assertEqual(exit_code, 0)
            self.assertEqual(kalman_spy.call_count, 1)
            sidecar_path = data_dir / "ENDURANCE_HRV_ssm_shadow.csv"
            metadata_path = data_dir / "ENDURANCE_HRV_ssm_shadow_metadata.json"
            self.assertTrue(sidecar_path.exists())
            self.assertTrue(metadata_path.exists())

            sidecar = pd.read_csv(sidecar_path)
            self.assertEqual(list(sidecar.columns), ssm_builder.SIDE_CAR_COLUMNS)

            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            self.assertEqual(metadata["source"], "build_hrv_ssm.py")
            self.assertIn("core_input", metadata)
            self.assertIn("sessions_day_input", metadata)
            self.assertIn("sleep_input", metadata)
            self.assertIn("load_signal_pretest", metadata)
            self.assertIn("daily_user_summary", metadata)
            self.assertIn("innovation", metadata["daily_user_summary"])


    # --- Unit tests sobre helpers de la lectura SSM (UX-01 follow-up) ---

    def test_innovation_text_negative_expresses_percentage_hrv(self):
        text = ssm_builder._innovation_text(-0.26)
        self.assertIn("sorpresa", text.lower())
        self.assertRegex(text, r"-\d+%")
        self.assertIn("-0.26", text)

    def test_innovation_text_positive_expresses_percentage_hrv(self):
        text = ssm_builder._innovation_text(0.20)
        self.assertIn("sorpresa", text.lower())
        self.assertIn("positiva", text)
        self.assertRegex(text, r"\+\d+%")

    def test_innovation_text_small_falls_back_to_close_fit(self):
        text = ssm_builder._innovation_text(0.05)
        self.assertIn("encaja", text)
        self.assertIn("pequeña", text)

    def test_innovation_text_nan_is_safe(self):
        self.assertIn("no es interpretable", ssm_builder._innovation_text(float("nan")))

    def test_relation_text_includes_ms_equivalents(self):
        text = ssm_builder._relation_text(3.70, 3.65, 0.05)
        self.assertIn("rolling HRV 7d", text)
        self.assertRegex(text, r"≈\s?\d+\s?ms")
        self.assertIn("continuidad", text)

    def test_relation_text_negative_delta_marks_below(self):
        text = ssm_builder._relation_text(3.50, 3.70, -0.20)
        self.assertIn("por debajo", text)

    def test_relation_text_nan_delta_is_safe(self):
        self.assertIn("No puedo compararlo", ssm_builder._relation_text(3.70, float("nan"), float("nan")))

    def test_sleep_obs_text_renders_ms_when_present(self):
        text = ssm_builder._sleep_obs_text(3.71, 0.0)
        self.assertRegex(text, r"≈\s?\d+\s?ms")
        self.assertIn("apoyo", text)

    def test_sleep_obs_text_handles_missing_observation(self):
        text = ssm_builder._sleep_obs_text(float("nan"), float("nan"))
        self.assertIn("no hay observación nocturna", text)

    def test_ms_from_log_roundtrip(self):
        self.assertAlmostEqual(ssm_builder._ms_from_log(3.98), 53.51, places=1)
        self.assertTrue(np.isnan(ssm_builder._ms_from_log(float("nan"))))

    def test_fatigue_label_from_history_percentiles(self):
        series = pd.Series([0.05, 0.10, 0.15, 0.20, 0.25, 0.30, 0.35, 0.40, 0.45, 0.50])
        self.assertEqual(ssm_builder._fatigue_label_from_history(0.45, series), "alta")
        self.assertEqual(ssm_builder._fatigue_label_from_history(0.08, series), "baja")
        self.assertEqual(ssm_builder._fatigue_label_from_history(0.25, series), "media")

    def test_fatigue_label_indeterminada_with_short_series(self):
        short = pd.Series([0.1, 0.2])
        self.assertEqual(ssm_builder._fatigue_label_from_history(0.15, short), "indeterminada")

    def test_load_context_text_rest_day_after_positive_prev_load(self):
        valid = pd.DataFrame(
            [
                {"ssm_load_context_mode": "session_recorded", "load_day": 75.0},
                {"ssm_load_context_mode": "rest_day_no_session", "load_day": np.nan},
            ]
        )
        text = ssm_builder._load_context_text(valid.iloc[-1], valid)
        self.assertIn("contexto reciente venía de una sesión registrada", text)

    def test_load_context_text_rest_day_after_session_recorded_without_load_value(self):
        valid = pd.DataFrame(
            [
                {"ssm_load_context_mode": "session_recorded", "load_day": np.nan},
                {"ssm_load_context_mode": "rest_day_no_session", "load_day": np.nan},
            ]
        )
        text = ssm_builder._load_context_text(valid.iloc[-1], valid)
        self.assertIn("carga previa ya consolidada", text)

    def test_load_context_text_rest_day_after_calendar_gap(self):
        valid = pd.DataFrame(
            [
                {"ssm_load_context_mode": "calendar_gap_no_session", "load_day": 0.0},
                {"ssm_load_context_mode": "rest_day_no_session", "load_day": np.nan},
            ]
        )
        text = ssm_builder._load_context_text(valid.iloc[-1], valid)
        self.assertIn("varios días sin sesiones consolidadas", text)

    def test_load_context_text_rest_day_after_missing_session_value(self):
        valid = pd.DataFrame(
            [
                {"ssm_load_context_mode": "missing_session_value", "load_day": np.nan},
                {"ssm_load_context_mode": "rest_day_no_session", "load_day": np.nan},
            ]
        )
        text = ssm_builder._load_context_text(valid.iloc[-1], valid)
        self.assertIn("no era plenamente utilizable", text)

    def test_load_context_text_falls_back_for_first_rest_day(self):
        valid = pd.DataFrame(
            [
                {"ssm_load_context_mode": "rest_day_no_session", "load_day": np.nan},
            ]
        )
        text = ssm_builder._load_context_text(valid.iloc[-1], valid)
        self.assertIn("carga previa disponible", text)

    def test_load_context_text_falls_back_for_unknown_previous_mode(self):
        valid = pd.DataFrame(
            [
                {"ssm_load_context_mode": "unknown_mode", "load_day": 0.0},
                {"ssm_load_context_mode": "rest_day_no_session", "load_day": np.nan},
            ]
        )
        text = ssm_builder._load_context_text(valid.iloc[-1], valid)
        self.assertIn("carga previa disponible", text)

    def test_component_text_positive_fatigue_renders_discount(self):
        valid = pd.DataFrame({"ssm_fatigue_state": [0.05, 0.10, 0.15, 0.20, 0.25, 0.30]})
        text = ssm_builder._component_text(3.98, 0.29, valid)
        self.assertIn("descuenta", text)
        self.assertRegex(text, r"≈\d+%")
        self.assertIn("0.29", text)

    def test_component_text_negative_fatigue_uses_boost_language(self):
        valid = pd.DataFrame({"ssm_fatigue_state": [-0.20, -0.10, 0.0, 0.10, 0.20]})
        text = ssm_builder._component_text(3.98, -0.15, valid)
        self.assertIn("compensa", text)
        self.assertNotIn("descuenta", text)
        self.assertRegex(text, r"≈\+\d+%")

    def test_component_text_near_zero_fatigue_uses_neutral_language(self):
        valid = pd.DataFrame({"ssm_fatigue_state": [0.0, 0.01, -0.01]})
        text = ssm_builder._component_text(3.98, 0.01, valid)
        self.assertIn("prácticamente nula", text)
        self.assertNotIn("descuenta", text)


if __name__ == "__main__":
    unittest.main()
