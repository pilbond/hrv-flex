import json
import unittest
from pathlib import Path
from uuid import uuid4
from unittest.mock import patch

import pandas as pd
from polar_sessions import extract_mechanical_metrics, match_polar_exercise

from build_sessions import (
    build_training_audit,
    build_sessions_day,
    build_session_row,
    classify_session_group,
    compute_effort_anchor,
    compute_effort_recent,
    merge_sessions_incremental,
    resolve_update_oldest,
    warn_if_stream_sampling_suspicious,
    write_metadata,
)


EXPECTED_SESSIONS_DAY_COLUMNS = [
    "Fecha",
    "n_sessions",
    "total_duration_min",
    "has_aerobic",
    "has_strength",
    "has_mobility",
    "load_day",
    "intensity_cat_day",
    "intense_day",
    "work_total_min_day",
    "work_n_blocks_day",
    "z3_min_day",
    "hr_max_day",
    "hr_p95_max_day",
    "late_intensity_day",
    "cardiac_drift_worst",
    "elev_gain_day",
    "elev_loss_day",
    "strength_min_day",
    "mobility_min_day",
    "rpe_max_day",
    "effort_above_typical_aerobic",
    "effort_above_typical_strength",
    "effort_above_anchor_aerobic",
    "n_with_rpe",
    "n_with_notes",
    "elev_density_day",
    "intense_days_prev_3d",
    "intense_days_prev_5d",
    "intensity_clustering_flag",
    "intensity_clustering_level",
    "z3_7d_sum",
    "z3_7d_nobs",
    "work_7d_sum",
    "work_7d_nobs",
    "finish_strong_7d_count",
    "load_3d",
    "load_3d_nobs",
    "load_7d",
    "load_7d_nobs",
    "load_14d",
    "load_14d_nobs",
    "load_28d",
    "load_28d_nobs",
    "acwr_simple_prev",
    "monotony_7d_prev",
    "strain_7d_prev",
    "load_ctx_ready",
    "elev_loss_7d_sum",
]

EXPECTED_SESSIONS_COLUMNS = [
    "session_id",
    "Fecha",
    "start_time",
    "sport",
    "sport_raw",
    "source",
    "vt1_used",
    "vt2_used",
    "zones_source",
    "duration_min",
    "moving_min",
    "distance_km",
    "elev_gain_m",
    "elev_loss_m",
    "elev_density",
    "hr_mean",
    "hr_max",
    "hr_p95",
    "z1_pct",
    "z2_pct",
    "z3_pct",
    "z2_total_min",
    "z3_total_min",
    "work_n_blocks",
    "work_total_min",
    "work_longest_min",
    "work_avg_z3_pct",
    "work_blocks_min",
    "work_blocks_z3pct",
    "late_intensity",
    "cardiac_drift_pct",
    "mechanics_source",
    "polar_sport_raw",
    "polar_start_delta_min",
    "polar_duration_gap_min",
    "run_power_available",
    "run_power_mean",
    "run_power_max",
    "run_power_p95",
    "speed_first_half",
    "speed_second_half",
    "cadence_first_half",
    "cadence_second_half",
    "polar_speed_available",
    "polar_cadence_available",
    "load",
    "rpe",
    "feel",
    "intensity_category",
    "effort_vs_recent",
    "effort_vs_anchor",
    "session_group",
    "notes_raw",
    "rpe_present",
    "notes_present",
    "pipeline_version",
    "stream_dt_est",
]


def _session(**overrides):
    base = {
        "session_id": "i1",
        "Fecha": "2026-03-01",
        "start_time": "07:30",
        "sport": "trail_run",
        "sport_raw": "TrailRun",
        "source": "intervals",
        "vt1_used": 143,
        "vt2_used": 161,
        "zones_source": "icu",
        "duration_min": 60.0,
        "moving_min": 58.0,
        "distance_km": 10.0,
        "elev_gain_m": 500.0,
        "elev_loss_m": 500.0,
        "elev_density": 50.0,
        "hr_mean": 145.0,
        "hr_max": 170.0,
        "hr_p95": 165.0,
        "z1_pct": 40.0,
        "z2_pct": 50.0,
        "z3_pct": 10.0,
        "z2_total_min": 29.0,
        "z3_total_min": 5.0,
        "work_n_blocks": 2,
        "work_total_min": 20.0,
        "work_longest_min": 12.0,
        "work_avg_z3_pct": 18.0,
        "work_blocks_min": "10.0;10.0",
        "work_blocks_z3pct": "20;16",
        "late_intensity": 1,
        "cardiac_drift_pct": 4.0,
        "mechanics_source": "",
        "polar_sport_raw": "",
        "polar_start_delta_min": None,
        "polar_duration_gap_min": None,
        "run_power_available": 0,
        "run_power_mean": None,
        "run_power_max": None,
        "run_power_p95": None,
        "speed_first_half": None,
        "speed_second_half": None,
        "cadence_first_half": None,
        "cadence_second_half": None,
        "polar_speed_available": 0,
        "polar_cadence_available": 0,
        "load": 80.0,
        "rpe": 7.0,
        "feel": 3.0,
        "intensity_category": "work_intense",
        "effort_vs_recent": "above",
        "effort_vs_anchor": "typical",
        "session_group": "endurance_hard",
        "notes_raw": "ok",
        "rpe_present": 1,
        "notes_present": 1,
        "pipeline_version": "v3.2",
        "stream_dt_est": 1.0,
    }
    base.update(overrides)
    return base


class BuildSessionsContractTests(unittest.TestCase):
    def test_sessions_csv_contract_header_matches_expected(self):
        self.assertEqual(len(EXPECTED_SESSIONS_COLUMNS), 57)
        self.assertEqual(EXPECTED_SESSIONS_COLUMNS[-1], "stream_dt_est")

    def test_sessions_day_schema_matches_expected_columns(self):
        sessions = pd.DataFrame(
            [
                _session(),
                _session(
                    session_id="i2",
                    Fecha="2026-03-01",
                    sport="strength",
                    sport_raw="WeightTraining",
                    distance_km=0.0,
                    elev_gain_m=None,
                    elev_loss_m=None,
                    elev_density=None,
                    hr_mean=100.0,
                    hr_max=120.0,
                    hr_p95=None,
                    z1_pct=100.0,
                    z2_pct=0.0,
                    z3_pct=0.0,
                    z2_total_min=0.0,
                    z3_total_min=0.0,
                    work_n_blocks=0,
                    work_total_min=0.0,
                    work_longest_min=0.0,
                    work_avg_z3_pct=0.0,
                    work_blocks_min="",
                    work_blocks_z3pct="",
                    late_intensity=0,
                    cardiac_drift_pct=None,
                    load=30.0,
                    rpe=None,
                    feel=None,
                    intensity_category="NA",
                    effort_vs_recent="above",
                    effort_vs_anchor="below",
                    session_group="strength_unknown",
                    notes_raw="",
                    rpe_present=0,
                    notes_present=0,
                    stream_dt_est=None,
                ),
            ]
        )
        day = build_sessions_day(sessions)
        self.assertEqual(day.columns.tolist(), EXPECTED_SESSIONS_DAY_COLUMNS)
        self.assertEqual(len(day.columns), 49)

    def test_finish_strong_maps_to_endurance_easy(self):
        self.assertEqual(classify_session_group("trail_run", "finish_strong"), "endurance_easy")
        self.assertEqual(classify_session_group("trail_run", "work_moderate"), "endurance_moderate")

    def test_effort_recent_uses_load_and_session_group_with_canonical_enums(self):
        df = pd.DataFrame(
            [
                {"Fecha": "2025-06-01", "session_group": "strength_unknown", "load": 20},
                {"Fecha": "2025-06-02", "session_group": "strength_unknown", "load": 21},
                {"Fecha": "2025-06-03", "session_group": "strength_unknown", "load": 22},
                {"Fecha": "2025-06-04", "session_group": "strength_unknown", "load": 23},
                {"Fecha": "2025-06-05", "session_group": "strength_unknown", "load": 24},
                {"Fecha": "2025-06-06", "session_group": "strength_unknown", "load": 40},
            ]
        )
        out = compute_effort_recent(df)
        self.assertEqual(out.iloc[-1], "above")
        self.assertTrue(set(out.dropna().unique()).issubset({"unknown", "above", "typical", "below"}))

    def test_effort_anchor_uses_canonical_enums(self):
        df = pd.DataFrame(
            [
                {"Fecha": "2025-06-01", "session_group": "endurance_easy", "load": 10},
                {"Fecha": "2025-06-02", "session_group": "endurance_easy", "load": 12},
                {"Fecha": "2025-06-03", "session_group": "endurance_easy", "load": 14},
                {"Fecha": "2025-06-04", "session_group": "endurance_easy", "load": 16},
                {"Fecha": "2025-06-05", "session_group": "endurance_easy", "load": 18},
                {"Fecha": "2025-06-06", "session_group": "endurance_easy", "load": 30},
            ]
        )
        out = compute_effort_anchor(df)
        self.assertEqual(out.iloc[-1], "above")
        self.assertTrue(set(out.dropna().unique()).issubset({"unknown", "above", "typical", "below"}))

    def test_nobs_do_not_treat_strength_day_as_aerobic_observation(self):
        sessions = pd.DataFrame(
            [
                _session(Fecha="2026-03-01", session_id="i1"),
                _session(
                    Fecha="2026-03-02",
                    session_id="i2",
                    sport="strength",
                    sport_raw="WeightTraining",
                    distance_km=0.0,
                    elev_gain_m=None,
                    elev_loss_m=None,
                    elev_density=None,
                    hr_mean=100.0,
                    hr_max=120.0,
                    hr_p95=None,
                    z1_pct=100.0,
                    z2_pct=0.0,
                    z3_pct=0.0,
                    z2_total_min=0.0,
                    z3_total_min=0.0,
                    work_n_blocks=0,
                    work_total_min=0.0,
                    work_longest_min=0.0,
                    work_avg_z3_pct=0.0,
                    work_blocks_min="",
                    work_blocks_z3pct="",
                    late_intensity=0,
                    cardiac_drift_pct=None,
                    load=30.0,
                    rpe=None,
                    feel=None,
                    intensity_category="NA",
                    effort_vs_recent="above",
                    effort_vs_anchor="below",
                    session_group="strength_unknown",
                    notes_raw="",
                    rpe_present=0,
                    notes_present=0,
                    stream_dt_est=None,
                ),
                _session(
                    Fecha="2026-03-03",
                    session_id="i3",
                    load=60.0,
                    z3_total_min=2.0,
                    work_total_min=10.0,
                    work_n_blocks=1,
                    late_intensity=0,
                    intensity_category="work_moderate",
                    effort_vs_recent="typical",
                    effort_vs_anchor="above",
                    session_group="endurance_moderate",
                ),
            ]
        )
        day = build_sessions_day(sessions)
        strength_day = day.loc[day["Fecha"] == "2026-03-02"].iloc[0]
        later_day = day.loc[day["Fecha"] == "2026-03-03"].iloc[0]

        self.assertTrue(pd.isna(strength_day["z3_min_day"]))
        self.assertTrue(pd.isna(strength_day["work_total_min_day"]))
        self.assertTrue(pd.isna(strength_day["late_intensity_day"]))
        self.assertEqual(later_day["z3_7d_nobs"], 1)
        self.assertEqual(later_day["work_7d_nobs"], 1)

    def test_canonical_load_context_uses_continuous_calendar_and_shifted_windows(self):
        sessions = pd.DataFrame(
            [
                _session(session_id="i1", Fecha="2026-03-01", load=100.0),
                _session(session_id="i2", Fecha="2026-03-03", load=100.0),
                _session(session_id="i3", Fecha="2026-03-05", load=100.0),
                _session(session_id="i4", Fecha="2026-03-07", load=100.0),
                _session(session_id="i5", Fecha="2026-03-08", load=100.0),
            ]
        )

        day = build_sessions_day(sessions)
        row = day.loc[day["Fecha"] == "2026-03-08"].iloc[0]

        self.assertAlmostEqual(row["acwr_simple_prev"], 4.0, places=3)
        self.assertAlmostEqual(row["monotony_7d_prev"], 1.155, places=3)
        self.assertAlmostEqual(row["strain_7d_prev"], 461.9, places=1)
        self.assertFalse(bool(row["load_ctx_ready"]))

    def test_intensity_clustering_uses_calendar_days_and_severity_levels(self):
        high_sessions = pd.DataFrame(
            [
                _session(session_id="i1", Fecha="2026-03-01", intensity_category="work_intense"),
                _session(session_id="i2", Fecha="2026-03-03", intensity_category="work_intense"),
                _session(session_id="i3", Fecha="2026-03-04", intensity_category="work_intense"),
            ]
        )
        low_sessions = pd.DataFrame(
            [
                _session(session_id="i10", Fecha="2026-03-01", intensity_category="work_intense"),
                _session(session_id="i11", Fecha="2026-03-04", intensity_category="work_intense"),
                _session(
                    session_id="i12",
                    Fecha="2026-03-05",
                    intensity_category="easy",
                    session_group="endurance_easy",
                    work_total_min=0.0,
                    work_n_blocks=0,
                    work_longest_min=0.0,
                    work_avg_z3_pct=0.0,
                    work_blocks_min="",
                    work_blocks_z3pct="",
                    z3_total_min=0.0,
                    late_intensity=0,
                ),
            ]
        )

        high_day = build_sessions_day(high_sessions)
        low_day = build_sessions_day(low_sessions)
        high_row = high_day.loc[high_day["Fecha"] == "2026-03-04"].iloc[0]
        low_row = low_day.loc[low_day["Fecha"] == "2026-03-05"].iloc[0]

        self.assertEqual(high_row["intense_day"], 1)
        self.assertEqual(high_row["intense_days_prev_3d"], 2)
        self.assertEqual(high_row["intense_days_prev_5d"], 2)
        self.assertEqual(high_row["intensity_clustering_flag"], 1)
        self.assertEqual(high_row["intensity_clustering_level"], "high")

        self.assertEqual(low_row["intense_day"], 0)
        self.assertEqual(low_row["intense_days_prev_3d"], 1)
        self.assertEqual(low_row["intense_days_prev_5d"], 2)
        self.assertEqual(low_row["intensity_clustering_flag"], 1)
        self.assertEqual(low_row["intensity_clustering_level"], "low")

    def test_load_ctx_ready_requires_14_prior_load_observations(self):
        sessions = pd.DataFrame(
            [
                _session(session_id=f"i{idx}", Fecha=f"2026-03-{idx:02d}", load=50.0)
                for idx in range(1, 16)
            ]
        )

        day = build_sessions_day(sessions)
        row = day.loc[day["Fecha"] == "2026-03-15"].iloc[0]

        self.assertTrue(bool(row["load_ctx_ready"]))
        self.assertAlmostEqual(row["acwr_simple_prev"], 2.0, places=3)
        self.assertTrue(pd.isna(row["monotony_7d_prev"]))
        self.assertTrue(pd.isna(row["strain_7d_prev"]))

    def test_intensity_cat_day_uses_highest_load_session(self):
        sessions = pd.DataFrame(
            [
                _session(
                    session_id="i1",
                    Fecha="2026-03-01",
                    load=40.0,
                    intensity_category="work_moderate",
                    session_group="endurance_moderate",
                ),
                _session(
                    session_id="i2",
                    Fecha="2026-03-01",
                    load=90.0,
                    intensity_category="work_intense",
                    session_group="endurance_hard",
                ),
            ]
        )
        day = build_sessions_day(sessions)
        self.assertEqual(day.iloc[0]["intensity_cat_day"], "work_intense")

    def test_elev_density_represents_gain_per_km(self):
        class DummyClient:
            pass

        activity = {
            "id": "i100",
            "type": "TrailRun",
            "start_date_local": "2026-03-01T07:30:00",
            "elapsed_time": 3600,
            "moving_time": 3500,
            "distance": 10000,
            "total_elevation_gain": 600.0,
            "total_elevation_loss": 400.0,
            "average_heartrate": 145,
            "max_heartrate": 170,
            "icu_training_load": 80,
            "icu_hr_zones": [143, 161],
        }
        row = build_session_row(activity, DummyClient(), fetch_streams=False, fetch_notes=False)
        self.assertEqual(row["elev_density"], 60.0)

    def test_sampling_warning_is_emitted_but_metadata_is_still_written(self):
        dt_stats = {
            "n_streams": 2,
            "dt_mean": 0.9532,
            "dt_min": 0.213,
            "dt_max": 1.012,
            "assumed_1hz": False,
        }
        with self.assertLogs("build_sessions", level="WARNING") as captured:
            warn_if_stream_sampling_suspicious(dt_stats)
        self.assertTrue(any("outside ~1Hz" in line for line in captured.output))

        output_dir = Path("tests") / f"_tmp_metadata_{uuid4().hex}"
        output_dir.mkdir(parents=True, exist_ok=True)
        try:
            write_metadata(
                output_dir=output_dir,
                oldest="2026-03-01",
                newest="2026-03-02",
                n_sessions=2,
                n_days=1,
                n_streams=2,
                n_notes=0,
                dt_stats=dt_stats,
                zones_dist={"icu": 2},
            )
            meta = json.loads((output_dir / "ENDURANCE_HRV_sessions_metadata.json").read_text(encoding="utf-8"))
        finally:
            metadata_path = output_dir / "ENDURANCE_HRV_sessions_metadata.json"
            if metadata_path.exists():
                metadata_path.unlink()
            if output_dir.exists():
                output_dir.rmdir()
        self.assertFalse(meta["stream_sampling"]["assumed_1hz"])
        self.assertEqual(meta["stream_sampling"]["dt_mean"], 0.9532)

    def test_training_audit_is_embedded_in_metadata_and_degrades_confidence(self):
        sessions = pd.DataFrame(
            [
                _session(session_id="i1", Fecha="2026-03-01", zones_source="icu", stream_dt_est=1.0),
                _session(
                    session_id="i2",
                    Fecha="2026-03-02",
                    zones_source="fallback",
                    stream_dt_est=None,
                    cardiac_drift_pct=None,
                    notes_present=0,
                    intensity_category="easy",
                    session_group="endurance_easy",
                    work_total_min=0.0,
                    work_n_blocks=0,
                    work_longest_min=0.0,
                    work_avg_z3_pct=0.0,
                    work_blocks_min="",
                    work_blocks_z3pct="",
                    z3_total_min=0.0,
                    late_intensity=0,
                ),
            ],
            columns=EXPECTED_SESSIONS_COLUMNS,
        )
        day = build_sessions_day(sessions)
        dt_stats = {
            "n_streams": 1,
            "dt_mean": 1.2,
            "dt_min": 1.2,
            "dt_max": 1.2,
            "assumed_1hz": False,
        }
        training_audit = build_training_audit(
            sessions,
            day,
            dt_stats=dt_stats,
            zones_dist={"icu": 1, "fallback": 1},
        )

        output_dir = Path("tests") / f"_tmp_metadata_{uuid4().hex}"
        output_dir.mkdir(parents=True, exist_ok=True)
        try:
            write_metadata(
                output_dir=output_dir,
                oldest="2026-03-01",
                newest="2026-03-02",
                n_sessions=2,
                n_days=2,
                n_streams=1,
                n_notes=1,
                dt_stats=dt_stats,
                zones_dist={"icu": 1, "fallback": 1},
                training_audit=training_audit,
            )
            meta = json.loads((output_dir / "ENDURANCE_HRV_sessions_metadata.json").read_text(encoding="utf-8"))
        finally:
            metadata_path = output_dir / "ENDURANCE_HRV_sessions_metadata.json"
            if metadata_path.exists():
                metadata_path.unlink()
            if output_dir.exists():
                output_dir.rmdir()

        audit = meta["training_audit"]
        self.assertFalse(audit["signal_level"]["sampling_ok"])
        self.assertEqual(audit["signal_level"]["zones_fallback_pct"], 50.0)
        self.assertIn("zones_fallback_present", audit["signal_level"]["interpretability_limits"])
        self.assertIn("partial_aerobic_stream_coverage", audit["signal_level"]["interpretability_limits"])
        self.assertEqual(audit["metric_level"]["zone_intensity"]["state"], "contextual")
        self.assertEqual(audit["metric_level"]["load_context"]["state"], "informational")
        self.assertEqual(audit["metric_level"]["coaching_load"]["state"], "informational")

    def test_merge_sessions_incremental_preserves_literal_na_enum(self):
        output_dir = Path("tests") / f"_tmp_sessions_{uuid4().hex}"
        output_dir.mkdir(parents=True, exist_ok=True)
        sessions_path = output_dir / "ENDURANCE_HRV_sessions.csv"
        try:
            existing = pd.DataFrame(
                [
                    _session(
                        sport="strength",
                        sport_raw="WeightTraining",
                        distance_km=0.0,
                        elev_gain_m=None,
                        elev_loss_m=None,
                        elev_density=None,
                        hr_mean=100.0,
                        hr_max=120.0,
                        hr_p95=None,
                        z1_pct=100.0,
                        z2_pct=0.0,
                        z3_pct=0.0,
                        z2_total_min=0.0,
                        z3_total_min=0.0,
                        work_n_blocks=0,
                        work_total_min=0.0,
                        work_longest_min=0.0,
                        work_avg_z3_pct=0.0,
                        work_blocks_min="",
                        work_blocks_z3pct="",
                        late_intensity=0,
                        cardiac_drift_pct=None,
                        mechanics_source="",
                        polar_sport_raw="",
                        polar_start_delta_min=None,
                        polar_duration_gap_min=None,
                        run_power_available=0,
                        run_power_mean=None,
                        run_power_max=None,
                        run_power_p95=None,
                        speed_first_half=None,
                        speed_second_half=None,
                        cadence_first_half=None,
                        cadence_second_half=None,
                        polar_speed_available=0,
                        polar_cadence_available=0,
                        load=30.0,
                        rpe=None,
                        feel=None,
                        intensity_category="NA",
                        effort_vs_recent="above",
                        effort_vs_anchor="below",
                        session_group="strength_unknown",
                        notes_raw="",
                        rpe_present=0,
                        notes_present=0,
                        pipeline_version="v3.3",
                        stream_dt_est=None,
                    )
                ],
                columns=EXPECTED_SESSIONS_COLUMNS,
            )
            existing.to_csv(sessions_path, index=False)
            merged = merge_sessions_incremental(pd.DataFrame(), sessions_path)
        finally:
            if sessions_path.exists():
                sessions_path.unlink()
            if output_dir.exists():
                output_dir.rmdir()
        self.assertEqual(merged.iloc[0]["intensity_category"], "NA")

    def test_resolve_update_oldest_reads_fecha_without_default_na_coercion(self):
        output_dir = Path("tests") / f"_tmp_update_anchor_{uuid4().hex}"
        output_dir.mkdir(parents=True, exist_ok=True)
        day_path = output_dir / "ENDURANCE_HRV_sessions_day.csv"
        try:
            day_path.write_text(
                "Fecha,load_day\n2026-03-01,50\n2026-03-03,70\n",
                encoding="utf-8",
            )
            oldest = resolve_update_oldest(output_dir, "2025-05-12")
        finally:
            if day_path.exists():
                day_path.unlink()
            if output_dir.exists():
                output_dir.rmdir()
        self.assertEqual(oldest, "2026-03-03")

    def test_match_polar_exercise_accepts_single_dst_like_candidate(self):
        row = {
            "session_id": "i135863677",
            "Fecha": "2026-03-30",
            "start_time": "09:29",
            "duration_min": "77.6",
        }
        exercises = [
            {
                "id": "54lXrXxj",
                "start_time": "2026-03-30T08:29:12",
                "duration": "PT4658.866S",
                "sport": "RUNNING",
                "detailed_sport_info": "RUNNING",
            }
        ]
        with self.assertLogs("polar_sessions", level="WARNING") as captured:
            match = match_polar_exercise(row, exercises)
        self.assertEqual(match["exercise"]["id"], "54lXrXxj")
        self.assertAlmostEqual(match["duration_gap_min"], 0.048, places=2)
        self.assertAlmostEqual(match["start_delta_min"], 59.8, places=1)
        self.assertTrue(any("DST fallback activado" in line for line in captured.output))

    def test_extract_mechanical_metrics_ignores_zero_power_as_unavailable(self):
        exercise = {
            "sport": "TREADMILL_RUNNING",
            "samples": [
                {"sample_type": "1", "data": ",".join(["1.0"] * 80)},
                {"sample_type": "2", "data": ",".join(["80"] * 80)},
                {"sample_type": "4", "data": ",".join(["0"] * 80)},
            ],
        }
        metrics = extract_mechanical_metrics(exercise)
        self.assertEqual(metrics["run_power_available"], 0)
        self.assertIsNone(metrics["run_power_mean"])
        self.assertEqual(metrics["polar_speed_available"], 1)
        self.assertEqual(metrics["polar_cadence_available"], 1)
        self.assertEqual(metrics["mechanics_source"], "polar")

    def test_extract_mechanical_metrics_splits_halves_by_chronology_not_valid_sample_count(self):
        speed_series = ["0.0"] * 20 + ["1.0"] * 20 + ["2.0"] * 40
        exercise = {
            "sport": "TRAIL_RUNNING",
            "samples": [
                {"sample_type": "1", "data": ",".join(speed_series)},
            ],
        }
        metrics = extract_mechanical_metrics(exercise)
        self.assertEqual(metrics["mechanics_source"], "polar")
        self.assertEqual(metrics["polar_speed_available"], 1)
        self.assertAlmostEqual(metrics["speed_first_half"], 3.6, places=2)
        self.assertAlmostEqual(metrics["speed_second_half"], 7.2, places=2)

    def test_build_session_row_prefers_intervals_fit_mechanics_over_polar(self):
        class DummyClient:
            def get_fit_payload(self, activity_id):
                return b"fake-fit"

        class DummyPolar:
            def enrich_row(self, row):
                return {
                    "mechanics_source": "polar",
                    "run_power_available": 1,
                    "run_power_mean": 111.0,
                }

        activity = {
            "id": "i100",
            "type": "TrailRun",
            "start_date_local": "2026-03-01T07:30:00",
            "elapsed_time": 3600,
            "moving_time": 3500,
            "distance": 10000,
            "total_elevation_gain": 600.0,
            "total_elevation_loss": 400.0,
            "average_heartrate": 145,
            "max_heartrate": 170,
            "icu_training_load": 80,
            "icu_hr_zones": [143, 161],
        }
        fit_metrics = {
            "mechanics_source": "intervals_fit",
            "polar_sport_raw": "running trail",
            "polar_start_delta_min": None,
            "polar_duration_gap_min": None,
            "run_power_available": 1,
            "run_power_mean": 222.0,
            "run_power_max": 350.0,
            "run_power_p95": 300.0,
            "speed_first_half": 10.0,
            "speed_second_half": 9.0,
            "cadence_first_half": 85.0,
            "cadence_second_half": 82.0,
            "polar_speed_available": 1,
            "polar_cadence_available": 1,
        }
        with patch("build_sessions.extract_mechanical_metrics_from_fit_payload", return_value=fit_metrics):
            row = build_session_row(activity, DummyClient(), fetch_streams=False, fetch_notes=False, polar_client=DummyPolar())
        self.assertEqual(row["mechanics_source"], "intervals_fit")
        self.assertEqual(row["run_power_mean"], 222.0)
        self.assertEqual(row["speed_first_half"], 10.0)


if __name__ == "__main__":
    unittest.main()
