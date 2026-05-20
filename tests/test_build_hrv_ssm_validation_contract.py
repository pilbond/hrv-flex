import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import numpy as np
import pandas as pd

import build_hrv_ssm_validation as validation_builder


def _core() -> pd.DataFrame:
    dates = pd.date_range("2026-01-01", periods=40, freq="D")
    return pd.DataFrame(
        {
            "Fecha": [fecha.strftime("%Y-%m-%d") for fecha in dates],
            "lnRMSSD": [4.0 - (idx * 0.02) if idx >= 8 else 4.0 for idx in range(len(dates))],
            "Calidad": ["OK"] * len(dates),
            "HRV_Stability": ["OK"] * len(dates),
            "Artifact_pct": [0.0] * len(dates),
            "Flags": [""] * len(dates),
        }
    )


def _ssm_frame() -> pd.DataFrame:
    dates = pd.date_range("2026-01-01", periods=40, freq="D")
    rows = []
    for idx, fecha in enumerate(dates):
        rows.append(
            {
                "Fecha": fecha.strftime("%Y-%m-%d"),
                "ssm_input_ready": True,
                "ssm_warmup_complete": idx >= 8,
                "ssm_recovery_state": 4.0 - (idx * 0.02) if idx >= 8 else np.nan,
                "ssm_state_lo": 0.0,
                "ssm_state_hi": 0.0,
                "ssm_state_var": 0.02 + (idx % 5) * 0.01 if idx >= 8 else np.nan,
                "ssm_state_sd": 0.2,
                "ssm_obs_missing": False,
                "ssm_load_missing": False,
                "ssm_load_context_mode": "session_recorded",
                "ssm_proc_var_multiplier": 1.0,
                "ssm_input_quality": "clean",
                "ssm_obs_var_multiplier": 1.0,
                "control_rolling_hrv_7d": 3.9 - (idx * 0.015),
                "control_load_7d": 200 + idx * 3,
            }
        )
    return pd.DataFrame(rows)


def _metadata() -> dict:
    return {
        "source": "build_hrv_ssm.py",
        "outcome_audit": {
            "outcome_audit_status": "pass",
            "primary_outcome_name": "rpe_max_day",
        },
        "load_signal_pretest": {"load_signal_status": "candidate"},
        "go_no_go_criteria": {"incremental_value_fail": "x"},
    }


def _sessions_day() -> pd.DataFrame:
    dates = pd.date_range("2026-01-02", periods=40, freq="D")
    return pd.DataFrame(
        {
            "Fecha": [fecha.strftime("%Y-%m-%d") for fecha in dates],
            "rpe_max_day": [4.0 + (idx * 0.03) for idx in range(len(dates))],
            "load_day": [50 + idx for idx in range(len(dates))],
            "has_aerobic": [1] * len(dates),
            "has_strength": [0] * len(dates),
            "has_mobility": [0] * len(dates),
            "intensity_cat_day": ["Z2"] * len(dates),
            "total_duration_min": [80 + (idx % 3) * 5 for idx in range(len(dates))],
            "z3_min_day": [5 + (idx % 3) for idx in range(len(dates))],
            "work_n_blocks_day": [1] * len(dates),
            "intensity_clustering_level": ["low"] * len(dates),
        }
    )


def _sessions() -> pd.DataFrame:
    dates = pd.date_range("2026-01-02", periods=40, freq="D")
    return pd.DataFrame(
        {
            "Fecha": [fecha.strftime("%Y-%m-%d") for fecha in dates],
            "sport": ["road_run"] * 20 + ["bike"] * 20,
            "duration_min": [80 + (idx % 3) * 5 for idx in range(len(dates))],
            "load": [50 + idx for idx in range(len(dates))],
            "session_group": (["endurance_easy"] * 10) + (["endurance_moderate"] * 10) + (["endurance_easy"] * 10) + (["endurance_moderate"] * 10),
            "route_id": ([101] * 6) + ([np.nan] * 14) + ([202] * 6) + ([np.nan] * 14),
        }
    )


def _final() -> pd.DataFrame:
    dates = pd.date_range("2026-01-01", periods=40, freq="D")
    gates = ["VERDE", "ÁMBAR", "ROJO", "ÁMBAR"] * 10
    return pd.DataFrame({"Fecha": [fecha.strftime("%Y-%m-%d") for fecha in dates], "gate_final": gates})


class BuildHRVSSMValidationContractTests(unittest.TestCase):
    def test_find_next_outcome_pairs_uses_multi_day_window_mean(self):
        ssm_df = pd.DataFrame(
            {
                "Fecha": pd.to_datetime(["2026-01-01"]),
                "ssm_warmup_complete": [True],
                "ssm_recovery_state": [4.0],
                "control_rolling_hrv_7d": [3.9],
                "control_load_7d": [200.0],
                "ssm_state_var": [0.02],
            }
        )
        outcome_rows = pd.DataFrame(
            {
                "Fecha": pd.to_datetime(["2026-01-02", "2026-01-03", "2026-01-04", "2026-01-06"]),
                "outcome_fds": [1.0, 2.0, 3.0, 99.0],
                "outcome_fds_lite": [np.nan, np.nan, np.nan, np.nan],
                "outcome_oriented": [1.0, 2.0, 3.0, 99.0],
                "cardiac_drift_worst": [10.0, 20.0, 30.0, 990.0],
                "session_family": ["aerobic_long_z2"] * 4,
                "session_family_sport": ["aerobic_long_z2__run"] * 4,
                "dominant_sport": ["road_run"] * 4,
                "sport_family": ["run"] * 4,
                "dominant_session_group": ["endurance_easy"] * 4,
                "dominant_route_id": [101.0] * 4,
                "comparison_key": ["route::101"] * 4,
                "comparison_level": ["route_id"] * 4,
                "family_baseline_n": [3] * 4,
            }
        )

        pairs = validation_builder._find_next_outcome_pairs(
            ssm_df,
            outcome_rows,
            "cardiac_drift_worst",
            None,
            aggregate_window_days=3,
            aggregate_window_max_sessions=3,
        )

        self.assertEqual(int(pairs.iloc[0]["outcome_window_n"]), 3)
        self.assertEqual(str(pairs.iloc[0]["outcome_scale"]), "window_mean_fds")
        self.assertAlmostEqual(float(pairs.iloc[0]["outcome_value"]), 2.0)
        self.assertAlmostEqual(float(pairs.iloc[0]["outcome_raw_value"]), 20.0)

    def test_cardiac_drift_is_scaled_by_sport_family_before_orientation(self):
        sessions_day = pd.DataFrame(
            {
                "Fecha": pd.to_datetime(["2026-01-01", "2026-01-02", "2026-01-03", "2026-01-04"]),
                "cardiac_drift_worst": [-8.0, -4.0, 8.0, 4.0],
                "load_day": [50, 50, 50, 50],
                "has_aerobic": [1, 1, 1, 1],
                "has_strength": [0, 0, 0, 0],
                "has_mobility": [0, 0, 0, 0],
                "intensity_cat_day": ["Z2", "Z2", "Z2", "Z2"],
                "total_duration_min": [60, 60, 60, 60],
                "z3_min_day": [5, 5, 5, 5],
                "work_n_blocks_day": [1, 1, 1, 1],
                "intensity_clustering_level": ["low", "low", "low", "low"],
            }
        )
        sessions = pd.DataFrame(
            {
                "Fecha": pd.to_datetime(["2026-01-01", "2026-01-02", "2026-01-03", "2026-01-04"]),
                "sport": ["bike", "bike", "road_run", "road_run"],
                "duration_min": [60, 60, 60, 60],
                "load": [50, 50, 50, 50],
                "session_group": ["endurance_easy", "endurance_easy", "endurance_easy", "endurance_easy"],
                "route_id": [101, 101, 202, 202],
            }
        )

        outcome_rows = validation_builder._build_comparable_outcomes(sessions_day, "cardiac_drift_worst", sessions_df=sessions)

        bike_rows = outcome_rows[outcome_rows["sport_family"].eq("bike")].sort_values("Fecha")
        run_rows = outcome_rows[outcome_rows["sport_family"].eq("run")].sort_values("Fecha")
        self.assertAlmostEqual(float(bike_rows.iloc[0]["outcome_value_normalized"]), -8.0 / 6.0, places=6)
        self.assertAlmostEqual(float(run_rows.iloc[0]["outcome_value_normalized"]), 8.0 / 6.0, places=6)
        self.assertTrue(bool(outcome_rows.attrs["outcome_normalization"]["applied"]))

    def test_build_validation_report_emits_expected_sections(self):
        report = validation_builder.build_validation_report(
            pd.DataFrame(_core()).assign(Fecha=lambda df: pd.to_datetime(df["Fecha"])),
            pd.DataFrame(_ssm_frame()).assign(Fecha=lambda df: pd.to_datetime(df["Fecha"])),
            _metadata(),
            pd.DataFrame(_sessions_day()).assign(Fecha=lambda df: pd.to_datetime(df["Fecha"])),
            pd.DataFrame(_sessions()).assign(Fecha=lambda df: pd.to_datetime(df["Fecha"])),
            pd.DataFrame({"Fecha": []}),
            pd.DataFrame({"Fecha": []}),
            pd.DataFrame(_final()).assign(Fecha=lambda df: pd.to_datetime(df["Fecha"])),
        )

        self.assertEqual(report["primary_outcome_name"], "rpe_max_day")
        self.assertIn("primary_outcome_selection", report)
        self.assertIn("sign_semantics_audit", report)
        self.assertIn("phase1_conclusion", report)
        self.assertIn("go_no_go_status", report["phase1_conclusion"])
        self.assertIn("structural_comparator_status", report["phase1_conclusion"])
        self.assertIn("sleep_comparator_status", report["phase1_conclusion"])
        self.assertIn("ewma_comparator_status", report["phase1_conclusion"])
        self.assertIn("sport_go_statuses", report["phase1_conclusion"])
        self.assertIn("sport_primary_reading", report["phase1_conclusion"])
        self.assertIn("structural_comparator", report)
        self.assertIn("sleep_comparator", report)
        self.assertIn("ewma_comparator", report)
        self.assertIn("phi_sensitivity", report)
        self.assertIn("discordant_day_analysis", report)
        self.assertIn("sport_stratified_analysis", report)
        self.assertIn("primary_strict_by_sport", report)
        self.assertIn("walk_forward_by_sport", report)
        self.assertIn("calibration_check", report)
        self.assertIn("baseline_comparison", report)
        self.assertIn("bootstrap_ci", report["baseline_comparison"])
        self.assertIn("primary_operational_view", report)
        self.assertIn("mode", report["primary_operational_view"])
        self.assertIn("recommended_primary_scope", report["primary_operational_view"])
        self.assertGreater(report["n_pairs"], 10)
        self.assertIn("strict_funnel", report)
        self.assertIn("outcome_diagnostics", report)
        self.assertIn("outcome_normalization", report)
        self.assertIn("primary_strict", report)
        self.assertIn("primary_lite", report)
        self.assertIn("exploratory_broad", report)
        self.assertIn("exploratory_window_t1_t3", report)
        self.assertIn("exploratory_pairing_rule", report)
        self.assertIn("ssm_goodness", report["evaluations"])
        self.assertIn("rolling_hrv_goodness", report["evaluations"])
        self.assertIn("walk_forward_n_folds", report["evaluations"]["ssm_goodness"])
        self.assertIn("walk_forward_mae_mean", report["evaluations"]["ssm_goodness"])
        self.assertIn("status", report["go_no_go"])
        self.assertIn("beats_rolling_hrv_7d_holdout_mae", report["go_no_go"]["required_all"])
        self.assertEqual(report["go_no_go"], report["primary_strict"]["go_no_go"])
        self.assertIn("go_no_go", report["primary_lite"])
        self.assertIn("session_family_distribution", report)
        self.assertIn("comparison_level_distribution", report)
        self.assertIn("session_family_sport_distribution", report)
        self.assertIn("sport_family_distribution", report)
        md = validation_builder.build_validation_markdown(report)
        self.assertIn("# Validación SSM Shadow", md)
        self.assertIn("## Cierre Fase 1", md)
        self.assertIn("## Vista Operativa Primaria", md)
        self.assertIn("Motivo de selección outcome", md)
        self.assertIn("t+1..t+3", md)
        self.assertIn("## Diagnóstico Outcome", md)
        self.assertIn("Normalización outcome", md)
        self.assertIn("## Auditoría de Signo", md)
        self.assertIn("## Comparador Estructural", md)
        self.assertIn("## Comparador Sueño", md)
        self.assertIn("## Comparador EWMA", md)
        self.assertIn("## Sensibilidad Phi", md)
        self.assertIn("## Días Discordantes", md)
        self.assertIn("## Estratificación Deporte", md)
        self.assertIn("## Walk-Forward Por Deporte", md)
        self.assertIn("## Principal Estricto Por Deporte", md)
        self.assertIn("## Funnel Estricto", md)
        self.assertIn("## Principal Estricto", md)
        self.assertIn("## Calibración", md)
        self.assertIn("## Baseline Trivial", md)
        self.assertIn("## Principal Lite", md)
        self.assertIn("## Exploratorio Amplio", md)
        self.assertIn("## Exploratorio Ventana T1-T3", md)
        self.assertIn("## Bootstrap CI", md)
        self.assertIn("WF MAE mean", md)
        self.assertIn("| Predictor |", md)
        self.assertIn("Nivel de comparabilidad", md)

    def test_main_writes_json_and_markdown(self):
        with TemporaryDirectory() as tmpdir:
            data_dir = Path(tmpdir)
            _core().to_csv(data_dir / "ENDURANCE_HRV_master_CORE.csv", index=False)
            _ssm_frame().to_csv(data_dir / "ENDURANCE_HRV_ssm_shadow.csv", index=False)
            (data_dir / "ENDURANCE_HRV_ssm_shadow_metadata.json").write_text(
                json.dumps(_metadata(), ensure_ascii=False),
                encoding="utf-8",
            )
            _sessions_day().to_csv(data_dir / "ENDURANCE_HRV_sessions_day.csv", index=False)
            _sessions().to_csv(data_dir / "ENDURANCE_HRV_sessions.csv", index=False)
            pd.DataFrame({"Fecha": []}).to_csv(data_dir / "ENDURANCE_HRV_wellness_subjective.csv", index=False)
            _final().to_csv(data_dir / "ENDURANCE_HRV_master_FINAL.csv", index=False)

            exit_code = validation_builder.main(["--data-dir", str(data_dir)])

            self.assertEqual(exit_code, 0)
            self.assertTrue((data_dir / "ENDURANCE_HRV_ssm_validation_report.json").exists())
            self.assertTrue((data_dir / "ENDURANCE_HRV_ssm_validation_report.md").exists())


if __name__ == "__main__":
    unittest.main()
