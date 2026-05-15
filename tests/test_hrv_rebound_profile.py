import unittest
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

import pandas as pd

import analysis.hrv_rebound_profile as rebound_module
from analysis.hrv_rebound_profile import (
    ReboundConfig,
    build_rebound_events,
    build_weekly_summary,
    classify_rebound,
)


class HrvReboundProfileTests(unittest.TestCase):
    def test_classify_rebound_categories(self):
        self.assertEqual(classify_rebound(-0.2, -0.2, False, 1.0, -0.5, -0.5), "rebote_rapido")
        self.assertEqual(classify_rebound(-1.0, -0.1, False, 1.0, -0.5, -0.5), "rebote_lento_absorbido")
        self.assertEqual(classify_rebound(-0.1, -0.8, False, 1.0, -0.5, -0.5), "rebote_incompleto_d3")
        self.assertEqual(classify_rebound(0.1, 1.3, False, 1.0, -0.5, -0.5), "sobrerrebote")
        self.assertEqual(classify_rebound(0.1, 0.2, True, 1.0, -0.5, -0.5), "no_interpretable")

    def test_build_rebound_events_uses_last_seven_valid_days(self):
        final_df = pd.DataFrame(
            [
                {"Fecha": "2026-04-01", "Calidad": "OK", "lnRMSSD_today": 4.00, "ln_base60": 3.70, "SWC_ln": 0.20},
                {"Fecha": "2026-04-02", "Calidad": "OK", "lnRMSSD_today": 4.10, "ln_base60": 3.70, "SWC_ln": 0.20},
                {"Fecha": "2026-04-03", "Calidad": "OK", "lnRMSSD_today": 4.20, "ln_base60": 3.70, "SWC_ln": 0.20},
                {"Fecha": "2026-04-04", "Calidad": "BAD", "lnRMSSD_today": 3.10, "ln_base60": 3.70, "SWC_ln": 0.20},
                {"Fecha": "2026-04-05", "Calidad": "BAD", "lnRMSSD_today": 3.20, "ln_base60": 3.70, "SWC_ln": 0.20},
                {"Fecha": "2026-04-06", "Calidad": "BAD", "lnRMSSD_today": 3.30, "ln_base60": 3.70, "SWC_ln": 0.20},
                {"Fecha": "2026-04-07", "Calidad": "OK", "lnRMSSD_today": 4.30, "ln_base60": 3.90, "SWC_ln": 0.25},
                {"Fecha": "2026-04-08", "Calidad": "OK", "lnRMSSD_today": 4.40, "ln_base60": 3.90, "SWC_ln": 0.25},
                {"Fecha": "2026-04-09", "Calidad": "OK", "lnRMSSD_today": 4.50, "ln_base60": 3.90, "SWC_ln": 0.25},
                {"Fecha": "2026-04-10", "Calidad": "OK", "lnRMSSD_today": 4.60, "ln_base60": 3.90, "SWC_ln": 0.25},
                {"Fecha": "2026-04-11", "Calidad": "OK", "lnRMSSD_today": 4.70, "ln_base60": 3.90, "SWC_ln": 0.25},
                {"Fecha": "2026-04-12", "Calidad": "OK", "lnRMSSD_today": 4.80, "ln_base60": 3.90, "SWC_ln": 0.25},
                {"Fecha": "2026-04-13", "Calidad": "OK", "lnRMSSD_today": 4.90, "ln_base60": 3.90, "SWC_ln": 0.25},
                {"Fecha": "2026-04-14", "Calidad": "OK", "lnRMSSD_today": 5.00, "ln_base60": 3.90, "SWC_ln": 0.25},
            ]
        )
        core_df = final_df[["Fecha"]].copy()
        core_df["lnRMSSD"] = final_df["lnRMSSD_today"]
        core_df["Flags"] = ""
        sessions_day_df = pd.DataFrame(
            [
                {"Fecha": "2026-04-01", "n_sessions": 0, "has_aerobic": 0, "has_strength": 0, "load_day": 0, "intense_day": 0, "acwr_simple_prev": 0.8, "monotony_7d_prev": 1.0, "strain_7d_prev": 10.0, "load_ctx_ready": True},
                {"Fecha": "2026-04-02", "n_sessions": 0, "has_aerobic": 0, "has_strength": 0, "load_day": 0, "intense_day": 0, "acwr_simple_prev": 0.8, "monotony_7d_prev": 1.0, "strain_7d_prev": 10.0, "load_ctx_ready": True},
                {"Fecha": "2026-04-03", "n_sessions": 0, "has_aerobic": 0, "has_strength": 0, "load_day": 0, "intense_day": 0, "acwr_simple_prev": 0.8, "monotony_7d_prev": 1.0, "strain_7d_prev": 10.0, "load_ctx_ready": True},
                {"Fecha": "2026-04-04", "n_sessions": 0, "has_aerobic": 0, "has_strength": 0, "load_day": 0, "intense_day": 0, "acwr_simple_prev": 0.8, "monotony_7d_prev": 1.0, "strain_7d_prev": 10.0, "load_ctx_ready": True},
                {"Fecha": "2026-04-05", "n_sessions": 0, "has_aerobic": 0, "has_strength": 0, "load_day": 0, "intense_day": 0, "acwr_simple_prev": 0.8, "monotony_7d_prev": 1.0, "strain_7d_prev": 10.0, "load_ctx_ready": True},
                {"Fecha": "2026-04-06", "n_sessions": 0, "has_aerobic": 0, "has_strength": 0, "load_day": 0, "intense_day": 0, "acwr_simple_prev": 0.8, "monotony_7d_prev": 1.0, "strain_7d_prev": 10.0, "load_ctx_ready": True},
                {"Fecha": "2026-04-07", "n_sessions": 0, "has_aerobic": 0, "has_strength": 0, "load_day": 0, "intense_day": 0, "acwr_simple_prev": 0.8, "monotony_7d_prev": 1.0, "strain_7d_prev": 10.0, "load_ctx_ready": True},
                {"Fecha": "2026-04-08", "n_sessions": 0, "has_aerobic": 0, "has_strength": 0, "load_day": 0, "intense_day": 0, "acwr_simple_prev": 0.8, "monotony_7d_prev": 1.0, "strain_7d_prev": 10.0, "load_ctx_ready": True},
                {"Fecha": "2026-04-09", "n_sessions": 0, "has_aerobic": 0, "has_strength": 0, "load_day": 0, "intense_day": 0, "acwr_simple_prev": 0.8, "monotony_7d_prev": 1.0, "strain_7d_prev": 10.0, "load_ctx_ready": True},
                {"Fecha": "2026-04-10", "n_sessions": 0, "has_aerobic": 0, "has_strength": 0, "load_day": 0, "intense_day": 0, "acwr_simple_prev": 0.8, "monotony_7d_prev": 1.0, "strain_7d_prev": 10.0, "load_ctx_ready": True},
                {"Fecha": "2026-04-11", "n_sessions": 1, "has_aerobic": 1, "has_strength": 0, "load_day": 88, "intense_day": 1, "acwr_simple_prev": 1.2, "monotony_7d_prev": 1.1, "strain_7d_prev": 14.0, "load_ctx_ready": True},
                {"Fecha": "2026-04-12", "n_sessions": 0, "has_aerobic": 0, "has_strength": 0, "load_day": 0, "intense_day": 0, "acwr_simple_prev": 0.8, "monotony_7d_prev": 1.0, "strain_7d_prev": 10.0, "load_ctx_ready": True},
                {"Fecha": "2026-04-13", "n_sessions": 0, "has_aerobic": 0, "has_strength": 0, "load_day": 0, "intense_day": 0, "acwr_simple_prev": 0.8, "monotony_7d_prev": 1.0, "strain_7d_prev": 10.0, "load_ctx_ready": True},
                {"Fecha": "2026-04-14", "n_sessions": 0, "has_aerobic": 0, "has_strength": 0, "load_day": 0, "intense_day": 0, "acwr_simple_prev": 0.8, "monotony_7d_prev": 1.0, "strain_7d_prev": 10.0, "load_ctx_ready": True},
            ]
        )
        sessions_df = pd.DataFrame(
            [{"Fecha": "2026-04-11", "session_id": "s1", "sport": "bike", "load": 88, "work_total_min": 35}]
        )
        sleep_df = pd.DataFrame(
            [{"Fecha": row["Fecha"], "polar_sleep_duration_min": 450, "polar_sleep_score": 80} for _, row in final_df.iterrows()]
        )

        events = build_rebound_events(final_df, core_df, sessions_day_df, sessions_df, sleep_df, ReboundConfig())

        self.assertEqual(len(events), 1)
        event = events.iloc[0]
        self.assertEqual(event["baseline_source"], "pre7_ok")
        self.assertEqual(int(event["baseline_n_ok_days"]), 7)
        self.assertAlmostEqual(float(event["baseline_pre"]), 4.30, places=6)

    def test_build_rebound_events_falls_back_to_base60_when_baseline_is_short(self):
        final_df = pd.DataFrame(
            [
                {"Fecha": "2026-02-01", "Calidad": "OK", "lnRMSSD_today": 4.00, "ln_base60": 3.80, "SWC_ln": 0.25},
                {"Fecha": "2026-02-02", "Calidad": "OK", "lnRMSSD_today": 4.02, "ln_base60": 3.80, "SWC_ln": 0.25},
                {"Fecha": "2026-02-03", "Calidad": "OK", "lnRMSSD_today": 4.01, "ln_base60": 3.80, "SWC_ln": 0.25},
                {"Fecha": "2026-02-04", "Calidad": "OK", "lnRMSSD_today": 4.03, "ln_base60": 3.80, "SWC_ln": 0.25},
                {"Fecha": "2026-02-05", "Calidad": "OK", "lnRMSSD_today": 4.20, "ln_base60": 3.95, "SWC_ln": 0.30},
                {"Fecha": "2026-02-06", "Calidad": "OK", "lnRMSSD_today": 4.10, "ln_base60": 3.95, "SWC_ln": 0.30},
                {"Fecha": "2026-02-07", "Calidad": "OK", "lnRMSSD_today": 4.12, "ln_base60": 3.95, "SWC_ln": 0.30},
                {"Fecha": "2026-02-08", "Calidad": "OK", "lnRMSSD_today": 4.11, "ln_base60": 3.95, "SWC_ln": 0.30},
            ]
        )
        core_df = final_df[["Fecha"]].copy()
        core_df["lnRMSSD"] = final_df["lnRMSSD_today"]
        core_df["Flags"] = ""
        sessions_day_df = pd.DataFrame(
            [
                {"Fecha": "2026-02-01", "n_sessions": 0, "has_aerobic": 0, "has_strength": 0, "load_day": 0, "intense_day": 0, "acwr_simple_prev": 0.8, "monotony_7d_prev": 1.0, "strain_7d_prev": 10.0, "load_ctx_ready": True},
                {"Fecha": "2026-02-02", "n_sessions": 0, "has_aerobic": 0, "has_strength": 0, "load_day": 0, "intense_day": 0, "acwr_simple_prev": 0.8, "monotony_7d_prev": 1.0, "strain_7d_prev": 10.0, "load_ctx_ready": True},
                {"Fecha": "2026-02-03", "n_sessions": 0, "has_aerobic": 0, "has_strength": 0, "load_day": 0, "intense_day": 0, "acwr_simple_prev": 0.8, "monotony_7d_prev": 1.0, "strain_7d_prev": 10.0, "load_ctx_ready": True},
                {"Fecha": "2026-02-04", "n_sessions": 0, "has_aerobic": 0, "has_strength": 0, "load_day": 0, "intense_day": 0, "acwr_simple_prev": 0.8, "monotony_7d_prev": 1.0, "strain_7d_prev": 10.0, "load_ctx_ready": True},
                {"Fecha": "2026-02-05", "n_sessions": 1, "has_aerobic": 1, "has_strength": 0, "load_day": 92, "intense_day": 1, "acwr_simple_prev": 1.1, "monotony_7d_prev": 1.2, "strain_7d_prev": 15.0, "load_ctx_ready": True},
                {"Fecha": "2026-02-06", "n_sessions": 0, "has_aerobic": 0, "has_strength": 0, "load_day": 0, "intense_day": 0, "acwr_simple_prev": 0.8, "monotony_7d_prev": 1.0, "strain_7d_prev": 10.0, "load_ctx_ready": True},
                {"Fecha": "2026-02-07", "n_sessions": 0, "has_aerobic": 0, "has_strength": 0, "load_day": 0, "intense_day": 0, "acwr_simple_prev": 0.8, "monotony_7d_prev": 1.0, "strain_7d_prev": 10.0, "load_ctx_ready": True},
                {"Fecha": "2026-02-08", "n_sessions": 0, "has_aerobic": 0, "has_strength": 0, "load_day": 0, "intense_day": 0, "acwr_simple_prev": 0.8, "monotony_7d_prev": 1.0, "strain_7d_prev": 10.0, "load_ctx_ready": True},
            ]
        )
        sessions_df = pd.DataFrame(
            [{"Fecha": "2026-02-05", "session_id": "s1", "sport": "bike", "load": 92, "work_total_min": 40}]
        )
        sleep_df = pd.DataFrame(
            [{"Fecha": row["Fecha"], "polar_sleep_duration_min": 450, "polar_sleep_score": 80} for _, row in final_df.iterrows()]
        )

        events = build_rebound_events(final_df, core_df, sessions_day_df, sessions_df, sleep_df, ReboundConfig())

        self.assertEqual(len(events), 1)
        event = events.iloc[0]
        self.assertEqual(event["baseline_source"], "base60_fallback")
        self.assertAlmostEqual(float(event["baseline_pre"]), 3.95, places=6)
        self.assertAlmostEqual(float(event["swc_pre"]), 0.30, places=6)
        self.assertEqual(event["classification"], "rebote_rapido")

    def test_build_rebound_events_detects_sobrerrebote(self):
        final_df = pd.DataFrame(
            [
                {"Fecha": "2026-03-01", "Calidad": "OK", "lnRMSSD_today": 4.00, "ln_base60": 3.90, "SWC_ln": 0.20},
                {"Fecha": "2026-03-02", "Calidad": "OK", "lnRMSSD_today": 4.02, "ln_base60": 3.90, "SWC_ln": 0.20},
                {"Fecha": "2026-03-03", "Calidad": "OK", "lnRMSSD_today": 4.01, "ln_base60": 3.90, "SWC_ln": 0.20},
                {"Fecha": "2026-03-04", "Calidad": "OK", "lnRMSSD_today": 4.03, "ln_base60": 3.90, "SWC_ln": 0.20},
                {"Fecha": "2026-03-05", "Calidad": "OK", "lnRMSSD_today": 4.00, "ln_base60": 3.90, "SWC_ln": 0.20},
                {"Fecha": "2026-03-06", "Calidad": "OK", "lnRMSSD_today": 4.01, "ln_base60": 3.90, "SWC_ln": 0.20},
                {"Fecha": "2026-03-07", "Calidad": "OK", "lnRMSSD_today": 4.05, "ln_base60": 3.90, "SWC_ln": 0.20},
                {"Fecha": "2026-03-08", "Calidad": "OK", "lnRMSSD_today": 4.60, "ln_base60": 3.90, "SWC_ln": 0.20},
                {"Fecha": "2026-03-09", "Calidad": "OK", "lnRMSSD_today": 4.30, "ln_base60": 3.90, "SWC_ln": 0.20},
                {"Fecha": "2026-03-10", "Calidad": "OK", "lnRMSSD_today": 4.72, "ln_base60": 3.90, "SWC_ln": 0.20},
            ]
        )
        core_df = final_df[["Fecha"]].copy()
        core_df["lnRMSSD"] = final_df["lnRMSSD_today"]
        core_df["Flags"] = ""
        sessions_day_df = pd.DataFrame(
            [
                {"Fecha": "2026-03-01", "n_sessions": 0, "has_aerobic": 0, "has_strength": 0, "load_day": 0, "intense_day": 0, "acwr_simple_prev": 0.8, "monotony_7d_prev": 1.0, "strain_7d_prev": 10.0, "load_ctx_ready": True},
                {"Fecha": "2026-03-02", "n_sessions": 0, "has_aerobic": 0, "has_strength": 0, "load_day": 0, "intense_day": 0, "acwr_simple_prev": 0.8, "monotony_7d_prev": 1.0, "strain_7d_prev": 10.0, "load_ctx_ready": True},
                {"Fecha": "2026-03-03", "n_sessions": 0, "has_aerobic": 0, "has_strength": 0, "load_day": 0, "intense_day": 0, "acwr_simple_prev": 0.8, "monotony_7d_prev": 1.0, "strain_7d_prev": 10.0, "load_ctx_ready": True},
                {"Fecha": "2026-03-04", "n_sessions": 0, "has_aerobic": 0, "has_strength": 0, "load_day": 0, "intense_day": 0, "acwr_simple_prev": 0.8, "monotony_7d_prev": 1.0, "strain_7d_prev": 10.0, "load_ctx_ready": True},
                {"Fecha": "2026-03-05", "n_sessions": 1, "has_aerobic": 1, "has_strength": 0, "load_day": 94, "intense_day": 1, "acwr_simple_prev": 1.0, "monotony_7d_prev": 1.1, "strain_7d_prev": 14.0, "load_ctx_ready": True},
                {"Fecha": "2026-03-06", "n_sessions": 0, "has_aerobic": 0, "has_strength": 0, "load_day": 0, "intense_day": 0, "acwr_simple_prev": 0.8, "monotony_7d_prev": 1.0, "strain_7d_prev": 10.0, "load_ctx_ready": True},
                {"Fecha": "2026-03-07", "n_sessions": 0, "has_aerobic": 0, "has_strength": 0, "load_day": 0, "intense_day": 0, "acwr_simple_prev": 0.8, "monotony_7d_prev": 1.0, "strain_7d_prev": 10.0, "load_ctx_ready": True},
                {"Fecha": "2026-03-08", "n_sessions": 0, "has_aerobic": 0, "has_strength": 0, "load_day": 0, "intense_day": 0, "acwr_simple_prev": 0.8, "monotony_7d_prev": 1.0, "strain_7d_prev": 10.0, "load_ctx_ready": True},
                {"Fecha": "2026-03-09", "n_sessions": 0, "has_aerobic": 0, "has_strength": 0, "load_day": 0, "intense_day": 0, "acwr_simple_prev": 0.8, "monotony_7d_prev": 1.0, "strain_7d_prev": 10.0, "load_ctx_ready": True},
                {"Fecha": "2026-03-10", "n_sessions": 0, "has_aerobic": 0, "has_strength": 0, "load_day": 0, "intense_day": 0, "acwr_simple_prev": 0.8, "monotony_7d_prev": 1.0, "strain_7d_prev": 10.0, "load_ctx_ready": True},
            ]
        )
        sessions_df = pd.DataFrame(
            [{"Fecha": "2026-03-05", "session_id": "s1", "sport": "bike", "load": 94, "work_total_min": 40}]
        )
        sleep_df = pd.DataFrame(
            [{"Fecha": row["Fecha"], "polar_sleep_duration_min": 450, "polar_sleep_score": 80} for _, row in final_df.iterrows()]
        )

        events = build_rebound_events(final_df, core_df, sessions_day_df, sessions_df, sleep_df, ReboundConfig())

        self.assertEqual(len(events), 1)
        event = events.iloc[0]
        self.assertEqual(event["classification"], "sobrerrebote")
        self.assertGreater(float(event["z_d3"]), 1.0)

    def test_build_rebound_events_handles_clean_and_contaminated_cases(self):
        final_df = pd.DataFrame(
            [
                {"Fecha": "2026-01-01", "Calidad": "OK", "lnRMSSD_today": 4.0, "ln_base60": 3.9, "SWC_ln": 0.2},
                {"Fecha": "2026-01-02", "Calidad": "OK", "lnRMSSD_today": 4.1, "ln_base60": 3.9, "SWC_ln": 0.2},
                {"Fecha": "2026-01-03", "Calidad": "OK", "lnRMSSD_today": 4.2, "ln_base60": 3.9, "SWC_ln": 0.2},
                {"Fecha": "2026-01-04", "Calidad": "OK", "lnRMSSD_today": 4.1, "ln_base60": 3.9, "SWC_ln": 0.2},
                {"Fecha": "2026-01-05", "Calidad": "OK", "lnRMSSD_today": 4.0, "ln_base60": 3.9, "SWC_ln": 0.2},
                {"Fecha": "2026-01-06", "Calidad": "OK", "lnRMSSD_today": 4.0, "ln_base60": 3.9, "SWC_ln": 0.2},
                {"Fecha": "2026-01-07", "Calidad": "OK", "lnRMSSD_today": 4.02, "ln_base60": 3.9, "SWC_ln": 0.2},
                {"Fecha": "2026-01-08", "Calidad": "OK", "lnRMSSD_today": 4.03, "ln_base60": 3.9, "SWC_ln": 0.2},
                {"Fecha": "2026-01-09", "Calidad": "OK", "lnRMSSD_today": 4.02, "ln_base60": 3.9, "SWC_ln": 0.2},
                {"Fecha": "2026-01-10", "Calidad": "OK", "lnRMSSD_today": 4.05, "ln_base60": 3.9, "SWC_ln": 0.2},
                {"Fecha": "2026-01-11", "Calidad": "OK", "lnRMSSD_today": 4.10, "ln_base60": 3.9, "SWC_ln": 0.2},
                {"Fecha": "2026-01-12", "Calidad": "OK", "lnRMSSD_today": 4.20, "ln_base60": 3.9, "SWC_ln": 0.2},
                {"Fecha": "2026-01-13", "Calidad": "OK", "lnRMSSD_today": 4.05, "ln_base60": 3.9, "SWC_ln": 0.2},
            ]
        )
        core_df = final_df[["Fecha"]].copy()
        core_df["lnRMSSD"] = final_df["lnRMSSD_today"]
        core_df["Flags"] = ""
        sessions_day_df = pd.DataFrame(
            [
                {"Fecha": "2026-01-01", "n_sessions": 0, "load_day": 0, "intense_day": 0, "acwr_simple_prev": 1.0, "monotony_7d_prev": 1.0, "strain_7d_prev": 10.0, "load_ctx_ready": True},
                {"Fecha": "2026-01-02", "n_sessions": 0, "load_day": 0, "intense_day": 0, "acwr_simple_prev": 1.0, "monotony_7d_prev": 1.0, "strain_7d_prev": 10.0, "load_ctx_ready": True},
                {"Fecha": "2026-01-03", "n_sessions": 0, "load_day": 0, "intense_day": 0, "acwr_simple_prev": 1.0, "monotony_7d_prev": 1.0, "strain_7d_prev": 10.0, "load_ctx_ready": True},
                {"Fecha": "2026-01-04", "n_sessions": 0, "load_day": 0, "intense_day": 0, "acwr_simple_prev": 1.0, "monotony_7d_prev": 1.0, "strain_7d_prev": 10.0, "load_ctx_ready": True},
                {"Fecha": "2026-01-05", "n_sessions": 0, "load_day": 0, "intense_day": 0, "acwr_simple_prev": 1.0, "monotony_7d_prev": 1.0, "strain_7d_prev": 10.0, "load_ctx_ready": True},
                {"Fecha": "2026-01-06", "n_sessions": 0, "load_day": 0, "intense_day": 0, "acwr_simple_prev": 1.0, "monotony_7d_prev": 1.0, "strain_7d_prev": 10.0, "load_ctx_ready": True},
                {"Fecha": "2026-01-07", "n_sessions": 1, "load_day": 90, "intense_day": 1, "acwr_simple_prev": 1.3, "monotony_7d_prev": 1.2, "strain_7d_prev": 20.0, "load_ctx_ready": True},
                {"Fecha": "2026-01-08", "n_sessions": 0, "load_day": 0, "intense_day": 0, "acwr_simple_prev": 0.9, "monotony_7d_prev": 1.1, "strain_7d_prev": 15.0, "load_ctx_ready": True},
                {"Fecha": "2026-01-09", "n_sessions": 0, "load_day": 0, "intense_day": 0, "acwr_simple_prev": 0.9, "monotony_7d_prev": 1.1, "strain_7d_prev": 15.0, "load_ctx_ready": True},
                {"Fecha": "2026-01-10", "n_sessions": 1, "load_day": 75, "intense_day": 1, "acwr_simple_prev": 1.4, "monotony_7d_prev": 1.3, "strain_7d_prev": 18.0, "load_ctx_ready": True},
                {"Fecha": "2026-01-11", "n_sessions": 1, "load_day": 85, "intense_day": 1, "acwr_simple_prev": 1.5, "monotony_7d_prev": 1.4, "strain_7d_prev": 21.0, "load_ctx_ready": True},
                {"Fecha": "2026-01-12", "n_sessions": 0, "load_day": 0, "intense_day": 0, "acwr_simple_prev": 0.8, "monotony_7d_prev": 1.1, "strain_7d_prev": 12.0, "load_ctx_ready": True},
                {"Fecha": "2026-01-13", "n_sessions": 0, "load_day": 0, "intense_day": 0, "acwr_simple_prev": 0.8, "monotony_7d_prev": 1.1, "strain_7d_prev": 12.0, "load_ctx_ready": True},
            ]
        )
        sessions_df = pd.DataFrame(
            [
                {"Fecha": "2026-01-07", "session_id": "s1", "sport": "trail_run", "load": 90, "work_total_min": 30},
                {"Fecha": "2026-01-10", "session_id": "s2", "sport": "bike", "load": 75, "work_total_min": 20},
                {"Fecha": "2026-01-11", "session_id": "s3", "sport": "bike", "load": 85, "work_total_min": 25},
            ]
        )
        sleep_df = pd.DataFrame(
            [{"Fecha": row["Fecha"], "polar_sleep_duration_min": 450, "polar_sleep_score": 80} for _, row in final_df.iterrows()]
        )

        events = build_rebound_events(final_df, core_df, sessions_day_df, sessions_df, sleep_df, ReboundConfig())

        self.assertEqual(len(events), 3)
        first = events.iloc[0]
        self.assertEqual(first["origin_date"], "2026-01-07")
        self.assertEqual(first["classification"], "rebote_lento_absorbido")
        self.assertFalse(bool(first["hard_invalid"]))

        second = events.iloc[1]
        self.assertEqual(second["origin_date"], "2026-01-10")
        self.assertTrue(bool(second["hard_invalid"]))
        self.assertIn("2026-01-11", second["d3_contamination_dates"])

        third = events.iloc[2]
        self.assertEqual(third["origin_scope"], "short_block")

        weekly = build_weekly_summary(events)
        self.assertEqual(int(weekly.iloc[0]["n_events"]), 3)

    def test_main_writes_sobrerrebote_artifacts(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            data_dir = tmp_path / "data"
            out_dir = tmp_path / "out"
            data_dir.mkdir(parents=True, exist_ok=True)

            final_df = pd.DataFrame(
                [
                    {"Fecha": "2026-03-01", "Calidad": "OK", "lnRMSSD_today": 4.00, "ln_base60": 3.90, "SWC_ln": 0.20, "gate_badge": "green", "Action": "normal", "reason_text": ""},
                    {"Fecha": "2026-03-02", "Calidad": "OK", "lnRMSSD_today": 4.02, "ln_base60": 3.90, "SWC_ln": 0.20, "gate_badge": "green", "Action": "normal", "reason_text": ""},
                    {"Fecha": "2026-03-03", "Calidad": "OK", "lnRMSSD_today": 4.01, "ln_base60": 3.90, "SWC_ln": 0.20, "gate_badge": "green", "Action": "normal", "reason_text": ""},
                    {"Fecha": "2026-03-04", "Calidad": "OK", "lnRMSSD_today": 4.03, "ln_base60": 3.90, "SWC_ln": 0.20, "gate_badge": "green", "Action": "normal", "reason_text": ""},
                    {"Fecha": "2026-03-05", "Calidad": "OK", "lnRMSSD_today": 4.00, "ln_base60": 3.90, "SWC_ln": 0.20, "gate_badge": "green", "Action": "normal", "reason_text": ""},
                    {"Fecha": "2026-03-06", "Calidad": "OK", "lnRMSSD_today": 4.01, "ln_base60": 3.90, "SWC_ln": 0.20, "gate_badge": "green", "Action": "normal", "reason_text": ""},
                    {"Fecha": "2026-03-07", "Calidad": "OK", "lnRMSSD_today": 4.05, "ln_base60": 3.90, "SWC_ln": 0.20, "gate_badge": "green", "Action": "normal", "reason_text": ""},
                    {"Fecha": "2026-03-08", "Calidad": "OK", "lnRMSSD_today": 4.60, "ln_base60": 3.90, "SWC_ln": 0.20, "gate_badge": "green", "Action": "normal", "reason_text": ""},
                    {"Fecha": "2026-03-09", "Calidad": "OK", "lnRMSSD_today": 4.30, "ln_base60": 3.90, "SWC_ln": 0.20, "gate_badge": "green", "Action": "normal", "reason_text": ""},
                    {"Fecha": "2026-03-10", "Calidad": "OK", "lnRMSSD_today": 4.72, "ln_base60": 3.90, "SWC_ln": 0.20, "gate_badge": "green", "Action": "normal", "reason_text": ""},
                ]
            )
            core_df = final_df[["Fecha"]].copy()
            core_df["lnRMSSD"] = final_df["lnRMSSD_today"]
            core_df["Flags"] = ""
            sessions_day_df = pd.DataFrame(
                [
                    {"Fecha": "2026-03-01", "n_sessions": 0, "has_aerobic": 0, "has_strength": 0, "load_day": 0, "intense_day": 0, "acwr_simple_prev": 0.8, "monotony_7d_prev": 1.0, "strain_7d_prev": 10.0, "load_ctx_ready": True},
                    {"Fecha": "2026-03-02", "n_sessions": 0, "has_aerobic": 0, "has_strength": 0, "load_day": 0, "intense_day": 0, "acwr_simple_prev": 0.8, "monotony_7d_prev": 1.0, "strain_7d_prev": 10.0, "load_ctx_ready": True},
                    {"Fecha": "2026-03-03", "n_sessions": 0, "has_aerobic": 0, "has_strength": 0, "load_day": 0, "intense_day": 0, "acwr_simple_prev": 0.8, "monotony_7d_prev": 1.0, "strain_7d_prev": 10.0, "load_ctx_ready": True},
                    {"Fecha": "2026-03-04", "n_sessions": 0, "has_aerobic": 0, "has_strength": 0, "load_day": 0, "intense_day": 0, "acwr_simple_prev": 0.8, "monotony_7d_prev": 1.0, "strain_7d_prev": 10.0, "load_ctx_ready": True},
                    {"Fecha": "2026-03-05", "n_sessions": 0, "has_aerobic": 0, "has_strength": 0, "load_day": 0, "intense_day": 0, "acwr_simple_prev": 0.8, "monotony_7d_prev": 1.0, "strain_7d_prev": 10.0, "load_ctx_ready": True},
                    {"Fecha": "2026-03-06", "n_sessions": 0, "has_aerobic": 0, "has_strength": 0, "load_day": 0, "intense_day": 0, "acwr_simple_prev": 0.8, "monotony_7d_prev": 1.0, "strain_7d_prev": 10.0, "load_ctx_ready": True},
                    {"Fecha": "2026-03-07", "n_sessions": 1, "has_aerobic": 1, "has_strength": 0, "load_day": 94, "intense_day": 1, "acwr_simple_prev": 1.3, "monotony_7d_prev": 1.2, "strain_7d_prev": 20.0, "load_ctx_ready": True},
                    {"Fecha": "2026-03-08", "n_sessions": 0, "has_aerobic": 0, "has_strength": 0, "load_day": 0, "intense_day": 0, "acwr_simple_prev": 0.9, "monotony_7d_prev": 1.1, "strain_7d_prev": 15.0, "load_ctx_ready": True},
                    {"Fecha": "2026-03-09", "n_sessions": 0, "has_aerobic": 0, "has_strength": 0, "load_day": 0, "intense_day": 0, "acwr_simple_prev": 0.9, "monotony_7d_prev": 1.1, "strain_7d_prev": 15.0, "load_ctx_ready": True},
                    {"Fecha": "2026-03-10", "n_sessions": 0, "has_aerobic": 0, "has_strength": 0, "load_day": 0, "intense_day": 0, "acwr_simple_prev": 0.8, "monotony_7d_prev": 1.1, "strain_7d_prev": 12.0, "load_ctx_ready": True},
                ]
            )
            sessions_df = pd.DataFrame(
                [{"Fecha": "2026-03-07", "session_id": "s1", "sport": "bike", "load": 94, "work_total_min": 40}]
            )
            sleep_df = pd.DataFrame(
                [{"Fecha": row["Fecha"], "polar_sleep_duration_min": 450, "polar_sleep_score": 80} for _, row in final_df.iterrows()]
            )

            final_path = data_dir / "ENDURANCE_HRV_master_FINAL.csv"
            core_path = data_dir / "ENDURANCE_HRV_master_CORE.csv"
            sessions_day_path = data_dir / "ENDURANCE_HRV_sessions_day.csv"
            sessions_path = data_dir / "ENDURANCE_HRV_sessions.csv"
            sleep_path = data_dir / "ENDURANCE_HRV_sleep.csv"
            final_df.to_csv(final_path, index=False)
            core_df.to_csv(core_path, index=False)
            sessions_day_df.to_csv(sessions_day_path, index=False)
            sessions_df.to_csv(sessions_path, index=False)
            sleep_df.to_csv(sleep_path, index=False)

            with (
                patch.object(rebound_module, "F_FINAL", final_path),
                patch.object(rebound_module, "F_CORE", core_path),
                patch.object(rebound_module, "F_SESSIONS_DAY", sessions_day_path),
                patch.object(rebound_module, "F_SESSIONS", sessions_path),
                patch.object(rebound_module, "F_SLEEP", sleep_path),
                patch.object(sys, "argv", ["hrv_rebound_profile.py", "--out-dir", str(out_dir)]),
            ):
                exit_code = rebound_module.main()

            self.assertEqual(exit_code, 0)
            events_df = pd.read_csv(out_dir / "hrv_rebound_profile_events.csv")
            summary_df = pd.read_csv(out_dir / "hrv_rebound_profile_weekly.csv")
            self.assertEqual(len(events_df), 1)
            self.assertEqual(events_df.iloc[0]["classification"], "sobrerrebote")
            self.assertGreaterEqual(int(events_df.iloc[0]["baseline_n_ok_days"]), 5)
            self.assertEqual(int(summary_df.iloc[0]["n_sobrerrebote"]), 1)


if __name__ == "__main__":
    unittest.main()
