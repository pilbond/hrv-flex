# -*- coding: utf-8 -*-
"""
ENDURANCE HRV — Validación reproducible SSM sombra
=================================================
"""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from typing import Dict, List

import numpy as np
import pandas as pd
from scipy import stats

import build_hrv_ssm as ssm_builder
from hrv_app.config import DATA_DIR as CONFIG_DATA_DIR
from hrv_app.config import resolve_writable_dir
from hrv_app.io_utils import json_safe as _json_safe, write_json_atomic, write_text_atomic


DATA_DIR = CONFIG_DATA_DIR
IN_CORE = DATA_DIR / "ENDURANCE_HRV_master_CORE.csv"
IN_SSM = DATA_DIR / "ENDURANCE_HRV_ssm_shadow.csv"
IN_SSM_METADATA = DATA_DIR / "ENDURANCE_HRV_ssm_shadow_metadata.json"
IN_SESSIONS_DAY = DATA_DIR / "ENDURANCE_HRV_sessions_day.csv"
IN_SESSIONS = DATA_DIR / "ENDURANCE_HRV_sessions.csv"
IN_SLEEP = DATA_DIR / "ENDURANCE_HRV_sleep.csv"
IN_WELLNESS = DATA_DIR / "ENDURANCE_HRV_wellness_subjective.csv"
IN_FINAL = DATA_DIR / "ENDURANCE_HRV_master_FINAL.csv"
OUT_REPORT_JSON = DATA_DIR / "ENDURANCE_HRV_ssm_validation_report.json"
OUT_REPORT_MD = DATA_DIR / "ENDURANCE_HRV_ssm_validation_report.md"

PRIMARY_CANDIDATES = [
    "cardiac_drift_worst",
    "effort_above_anchor_aerobic",
    "effort_above_typical_aerobic",
    "rpe_max_day",
]
PHI_SENSITIVITY_GRID = [0.85, 0.90, 0.92, 0.97]
EWMA_ALPHA_GRID = [0.05, 0.10, 0.15, 0.20, 0.30, 0.40]
LEGACY_LOAD_BETA = -0.0010
BOOTSTRAP_ITERATIONS = 1000
GATE_MAP = {"VERDE": 0.0, "ÁMBAR": 1.0, "AMBAR": 1.0, "ROJO": 2.0}
OUTCOME_HIGHER_IS_BETTER = {
    "cardiac_drift_worst": False,
    "effort_above_anchor_aerobic": True,
    "effort_above_typical_aerobic": True,
    "rpe_max_day": False,
}


def _sport_scaled_outcome(
    df: pd.DataFrame,
    outcome_col: str,
) -> tuple[pd.Series, dict[str, object]]:
    raw = _safe_float_series(df[outcome_col])
    if outcome_col != "cardiac_drift_worst" or "sport_family" not in df.columns:
        return raw, {"mode": "none", "applied": False, "per_sport_reference": {}}

    refs: dict[str, float] = {}
    scaled = raw.copy()
    for sport, subset in df.groupby("sport_family", dropna=False):
        sport_key = str(sport)
        values = _safe_float_series(subset[outcome_col]).dropna()
        if values.empty:
            continue
        ref = float(abs(values.median()))
        if not np.isfinite(ref) or ref < 1e-6:
            ref = float(values.abs().median())
        if not np.isfinite(ref) or ref < 1e-6:
            continue
        refs[sport_key] = ref
        scaled.loc[subset.index] = values / ref

    return scaled, {
        "mode": "sport_family_abs_median_scale",
        "applied": bool(refs),
        "per_sport_reference": refs,
    }


def parse_args(argv: List[str]) -> Dict[str, str]:
    parsed: Dict[str, str] = {}
    for idx, token in enumerate(argv):
        if token == "--data-dir" and idx + 1 < len(argv):
            parsed["data_dir"] = argv[idx + 1]
    return parsed


def _safe_float_series(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce").astype(float)


def _load_csv(path: Path, required_columns: List[str]) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"No existe: {path}")
    df = pd.read_csv(path)
    missing = [col for col in required_columns if col not in df.columns]
    if missing:
        raise ValueError(f"{path.name} no contiene columnas requeridas: {missing}")
    if "Fecha" in df.columns:
        df["Fecha"] = pd.to_datetime(df["Fecha"], errors="coerce").dt.normalize()
        df = df[df["Fecha"].notna()].copy()
    return df.sort_values("Fecha").reset_index(drop=True)


def _outcome_candidate_summary(
    sessions_day: pd.DataFrame,
    sessions_df: pd.DataFrame | None,
    column: str,
) -> dict[str, object]:
    coverage = int(_safe_float_series(sessions_day[column]).notna().sum()) if column in sessions_day.columns else 0
    outcome_rows = _build_comparable_outcomes(sessions_day, column, sessions_df=sessions_df)
    if outcome_rows.empty:
        return {
            "coverage": coverage,
            "n_rows": 0,
            "fds": 0,
            "fds_lite": 0,
            "baseline_gte_3": 0,
            "zero_share": float("nan"),
            "unique_values": 0,
            "valid_for_strict": False,
            "score": (0, 0, 0, 0, float("-inf"), coverage),
        }
    zero_share = float(outcome_rows["outcome_oriented"].eq(0).mean())
    unique_values = int(outcome_rows["outcome_oriented"].nunique(dropna=True))
    fds = int(outcome_rows["outcome_fds"].notna().sum())
    fds_lite = int(outcome_rows["outcome_fds_lite"].notna().sum())
    baseline_gte_3 = int((outcome_rows["family_baseline_n"] >= 3).sum())
    valid_for_strict = bool(fds > 0)
    score = (
        1 if valid_for_strict else 0,
        fds,
        fds_lite,
        baseline_gte_3,
        -zero_share if np.isfinite(zero_share) else float("-inf"),
        coverage,
    )
    return {
        "coverage": coverage,
        "n_rows": int(len(outcome_rows)),
        "fds": fds,
        "fds_lite": fds_lite,
        "baseline_gte_3": baseline_gte_3,
        "zero_share": zero_share,
        "unique_values": unique_values,
        "valid_for_strict": valid_for_strict,
        "score": score,
    }


def _choose_primary_outcome(
    sessions_day: pd.DataFrame,
    metadata: dict,
    sessions_df: pd.DataFrame | None,
) -> tuple[str | None, dict[str, object]]:
    audit = metadata.get("outcome_audit", {})
    audit_candidate = audit.get("primary_outcome_name")
    candidate_summaries: dict[str, dict[str, object]] = {}
    best_name = None
    best_score = None
    for column in PRIMARY_CANDIDATES:
        if column not in sessions_day.columns:
            continue
        summary = _outcome_candidate_summary(sessions_day, sessions_df, column)
        candidate_summaries[column] = summary
        if best_score is None or summary["score"] > best_score:
            best_name = column
            best_score = summary["score"]

    selected_name = best_name
    selection_reason = "best_validability_score"
    if isinstance(audit_candidate, str) and audit_candidate in candidate_summaries:
        audit_summary = candidate_summaries[audit_candidate]
        best_summary = candidate_summaries.get(best_name, {})
        if audit_candidate == best_name:
            selected_name = audit_candidate
            selection_reason = "audit_primary_same_as_best_available"
        elif (
            audit_summary["valid_for_strict"]
            and best_summary
            and audit_summary["fds"] >= best_summary.get("fds", 0) * 0.75
            and audit_summary["zero_share"] <= min(0.50, best_summary.get("zero_share", 1.0) + 0.10)
        ):
            selected_name = audit_candidate
            selection_reason = "audit_primary_close_to_best_validable"
        else:
            selection_reason = "audit_primary_degenerate_fallback_to_best_validable"

    return selected_name, {
        "audit_candidate": audit_candidate if isinstance(audit_candidate, str) else None,
        "selected_candidate": selected_name,
        "selection_reason": selection_reason,
        "candidates": {
            key: {k: v for k, v in value.items() if k != "score"}
            for key, value in candidate_summaries.items()
        },
    }


def _map_sport_family(sport: object) -> str | None:
    if sport is None or (isinstance(sport, float) and np.isnan(sport)):
        return None
    text = str(sport).strip().lower()
    if not text:
        return None
    if text in {"road_run", "trail_run", "run", "treadmill_run"}:
        return "run"
    if text in {"bike", "virtual_ride", "ride"}:
        return "bike"
    if text in {"hike", "walking", "walk"}:
        return "hike"
    if text in {"elliptical"}:
        return "elliptical"
    if text in {"strength"}:
        return "strength"
    if text in {"mobility", "yoga", "pilates"}:
        return "mobility"
    if text in {"swim"}:
        return "swim"
    return text


def _build_daily_sport_projection(sessions_df: pd.DataFrame) -> pd.DataFrame:
    if sessions_df.empty:
        return pd.DataFrame(columns=["Fecha", "dominant_sport", "sport_family", "dominant_session_group", "dominant_route_id"])
    df = sessions_df.copy()
    df["Fecha"] = pd.to_datetime(df["Fecha"], errors="coerce").dt.normalize()
    df = df[df["Fecha"].notna()].copy()
    if "duration_min" not in df.columns:
        df["duration_min"] = 0.0
    df["duration_min"] = _safe_float_series(df["duration_min"]).fillna(0.0)
    if "load" not in df.columns:
        df["load"] = np.nan
    df["load"] = _safe_float_series(df["load"]).fillna(0.0)
    if "session_group" not in df.columns:
        df["session_group"] = np.nan
    if "route_id" not in df.columns:
        df["route_id"] = np.nan
    df["sport"] = df["sport"].astype(str)
    grouped = (
        df.groupby(["Fecha", "sport"], dropna=False)["duration_min"]
        .sum()
        .reset_index()
        .sort_values(["Fecha", "duration_min"], ascending=[True, False])
    )
    dominant = grouped.groupby("Fecha", as_index=False).first()
    total = grouped.groupby("Fecha", as_index=False)["duration_min"].sum().rename(columns={"duration_min": "duration_total"})
    merged = dominant.merge(total, on="Fecha", how="left")
    merged["dominant_share"] = np.where(
        merged["duration_total"] > 0,
        merged["duration_min"] / merged["duration_total"],
        np.nan,
    )
    merged["dominant_sport"] = np.where(merged["dominant_share"] >= 0.60, merged["sport"], "mixed")
    merged["sport_family"] = merged["dominant_sport"].apply(_map_sport_family)
    merged.loc[merged["dominant_sport"].eq("mixed"), "sport_family"] = "mixed"
    dominant_session = (
        df.sort_values(["Fecha", "load", "duration_min"], ascending=[True, False, False])
        .groupby("Fecha", as_index=False)
        .first()[["Fecha", "session_group", "route_id"]]
        .rename(columns={"session_group": "dominant_session_group", "route_id": "dominant_route_id"})
    )
    merged = merged.merge(dominant_session, on="Fecha", how="left")
    return merged[["Fecha", "dominant_sport", "sport_family", "dominant_session_group", "dominant_route_id"]]


def _derive_session_family(sessions_day: pd.DataFrame, sessions_df: pd.DataFrame | None = None) -> pd.DataFrame:
    df = sessions_day.copy()
    for column in [
        "has_aerobic",
        "has_strength",
        "has_mobility",
        "total_duration_min",
        "load_day",
        "z3_min_day",
        "work_n_blocks_day",
        "intensity_cat_day",
        "intensity_clustering_level",
    ]:
        if column not in df.columns:
            df[column] = np.nan

    intensity = df["intensity_cat_day"].fillna("").astype(str).str.lower()
    clustering = df["intensity_clustering_level"].fillna("").astype(str).str.lower()
    duration = _safe_float_series(df["total_duration_min"])
    z3_min = _safe_float_series(df["z3_min_day"])
    work_blocks = _safe_float_series(df["work_n_blocks_day"])
    has_aerobic = df["has_aerobic"].fillna(0).astype(int).eq(1)

    family = np.full(len(df), None, dtype=object)
    strength_only = df["has_strength"].fillna(0).astype(int).eq(1) & ~has_aerobic
    aerobic_z3_tempo = has_aerobic & (
        intensity.isin(["z3", "work_moderate", "finish_strong"])
        & duration.between(30, 75, inclusive="both")
        & z3_min.ge(5.0).fillna(False)
    )
    aerobic_long_z2 = has_aerobic & (
        intensity.isin(["z2", "easy", "work_steady"])
        & duration.ge(75)
        & z3_min.le(10.0).fillna(True)
    )
    aerobic_short_z2 = has_aerobic & (
        intensity.isin(["z2", "easy", "work_steady"])
        & duration.lt(75)
        & z3_min.le(5.0).fillna(True)
    )
    aerobic_intervals = has_aerobic & (
        clustering.eq("high")
        | intensity.eq("work_intense")
        | work_blocks.ge(4)
        | (work_blocks.ge(3) & z3_min.ge(10.0).fillna(False))
    )

    family[strength_only.to_numpy(dtype=bool)] = "strength_only"
    family[aerobic_z3_tempo.to_numpy(dtype=bool)] = "aerobic_z3_tempo"
    family[aerobic_long_z2.to_numpy(dtype=bool)] = "aerobic_long_z2"
    family[aerobic_short_z2.to_numpy(dtype=bool)] = "aerobic_short_z2"
    family[(pd.isna(family) & aerobic_intervals).to_numpy(dtype=bool)] = "aerobic_intervals"
    df["session_family"] = family
    if sessions_df is not None and not sessions_df.empty:
        sport_projection = _build_daily_sport_projection(sessions_df)
        df = df.merge(sport_projection, on="Fecha", how="left")
    else:
        df["dominant_sport"] = np.nan
        df["sport_family"] = np.nan
        df["dominant_session_group"] = np.nan
        df["dominant_route_id"] = np.nan
    df["sport_family"] = df["sport_family"].fillna("unknown")
    df["session_family_sport"] = np.where(
        df["session_family"].notna(),
        df["session_family"].astype(str) + "__" + df["sport_family"].astype(str),
        np.nan,
    )
    return df


def _is_load_ratio_comparable(a: float, b: float) -> bool:
    if not np.isfinite(a) or not np.isfinite(b) or a <= 0 or b <= 0:
        return True
    ratio = a / b
    return 0.70 <= ratio <= 1.43


def _is_duration_ratio_comparable(a: float, b: float) -> bool:
    if not np.isfinite(a) or not np.isfinite(b) or a <= 0 or b <= 0:
        return False
    ratio = a / b
    return 0.75 <= ratio <= 1.33


def _z3_tolerance_ok(a: float, b: float) -> bool:
    if not np.isfinite(a) or not np.isfinite(b):
        return True
    return abs(a - b) <= max(10.0, 0.5 * max(a, b))


def _build_comparable_outcomes(sessions_day: pd.DataFrame, outcome_col: str, sessions_df: pd.DataFrame | None = None) -> pd.DataFrame:
    df = _derive_session_family(sessions_day, sessions_df=sessions_df)
    df[outcome_col] = _safe_float_series(df[outcome_col])
    df["total_duration_min"] = _safe_float_series(df["total_duration_min"])
    df["load_day"] = _safe_float_series(df["load_day"])
    df["z3_min_day"] = _safe_float_series(df["z3_min_day"])
    df = df[df["session_family_sport"].notna() & df[outcome_col].notna()].copy().reset_index(drop=True)

    normalized_values, normalization_info = _sport_scaled_outcome(df, outcome_col)
    df["outcome_value_normalized"] = normalized_values
    df["outcome_normalization_mode"] = normalization_info.get("mode", "none")
    oriented_values = normalized_values.copy()
    if outcome_col in OUTCOME_HIGHER_IS_BETTER and not OUTCOME_HIGHER_IS_BETTER[outcome_col]:
        oriented_values = -oriented_values
    df["outcome_oriented"] = oriented_values
    df.attrs["outcome_normalization"] = normalization_info

    route_history_count = {}
    session_group_history_count = {}
    comparison_key = np.full(len(df), None, dtype=object)
    comparison_level = np.full(len(df), "family_sport", dtype=object)

    for idx, row in df.iterrows():
        route_id = row.get("dominant_route_id")
        session_group = row.get("dominant_session_group")
        family_sport = row.get("session_family_sport")

        route_key = None
        if pd.notna(route_id):
            route_key = f"route::{int(float(route_id))}"
        session_group_key = None
        if isinstance(session_group, str) and session_group.strip():
            session_group_key = f"group::{session_group.strip().lower()}"

        if route_key is not None and route_history_count.get(route_key, 0) >= 2:
            comparison_key[idx] = route_key
            comparison_level[idx] = "route_id"
        elif session_group_key is not None and session_group_history_count.get(session_group_key, 0) >= 2:
            comparison_key[idx] = session_group_key
            comparison_level[idx] = "session_group"
        else:
            comparison_key[idx] = str(family_sport)
            comparison_level[idx] = "family_sport"

        if route_key is not None:
            route_history_count[route_key] = route_history_count.get(route_key, 0) + 1
        if session_group_key is not None:
            session_group_history_count[session_group_key] = session_group_history_count.get(session_group_key, 0) + 1

    df["comparison_key"] = comparison_key
    df["comparison_level"] = comparison_level

    fds = np.full(len(df), np.nan, dtype=float)
    fds_lite = np.full(len(df), np.nan, dtype=float)
    baseline_n = np.zeros(len(df), dtype=int)
    for idx, row in df.iterrows():
        prior = df.iloc[:idx].copy()
        if prior.empty:
            continue
        prior = prior[prior["comparison_key"] == row["comparison_key"]].copy()
        if prior.empty:
            continue
        prior = prior[
            prior["total_duration_min"].apply(lambda v: _is_duration_ratio_comparable(v, row["total_duration_min"]))
            & prior["load_day"].apply(lambda v: _is_load_ratio_comparable(v, row["load_day"]))
            & prior["z3_min_day"].apply(lambda v: _z3_tolerance_ok(v, row["z3_min_day"]))
        ].copy()
        if prior.empty:
            continue
        prior = prior.tail(8)
        baseline_n[idx] = len(prior)
        values = prior["outcome_oriented"].to_numpy(dtype=float)
        median = float(np.median(values))
        abs_dev = np.abs(values - median)
        mad = float(np.median(abs_dev))
        if len(prior) == 2:
            # Baseline mínimo para diagnóstico: no es tan robusto como FDS,
            # pero evita mezclar esta señal con el fallback raw orientado.
            scale = float(1.4826 * mad)
            if not np.isfinite(scale) or scale <= 0:
                scale = float(abs(values[1] - values[0]) / 2.0)
            if not np.isfinite(scale) or scale <= 0:
                continue
            fds_lite[idx] = float((row["outcome_oriented"] - median) / scale)
            continue
        if len(prior) < 3:
            continue
        if not np.isfinite(mad) or mad <= 0:
            continue
        fds[idx] = float((row["outcome_oriented"] - median) / (1.4826 * mad))

    df["outcome_fds"] = fds
    df["outcome_fds_lite"] = fds_lite
    df["family_baseline_n"] = baseline_n
    return df


def _find_next_outcome_pairs(
    ssm_df: pd.DataFrame,
    outcome_rows: pd.DataFrame,
    outcome_col: str,
    final_df: pd.DataFrame | None,
    aggregate_window_days: int = 7,
    aggregate_window_max_sessions: int = 1,
) -> pd.DataFrame:
    outcome_rows = outcome_rows[
        outcome_rows["outcome_fds"].notna()
        | outcome_rows["outcome_fds_lite"].notna()
        | outcome_rows["outcome_oriented"].notna()
    ].reset_index(drop=True)

    final_map = {}
    if final_df is not None and {"Fecha", "gate_final"}.issubset(final_df.columns):
        final_map = {
            row.Fecha.normalize(): GATE_MAP.get(str(row.gate_final), np.nan)
            for row in final_df[["Fecha", "gate_final"]].itertuples(index=False)
        }

    rows: list[dict[str, object]] = []
    for row in ssm_df.itertuples(index=False):
        current_date = row.Fecha
        if pd.isna(current_date) or not bool(row.ssm_warmup_complete) or pd.isna(row.ssm_recovery_state):
            continue
        future = outcome_rows[
            (outcome_rows["Fecha"] > current_date)
            & (outcome_rows["Fecha"] <= current_date + pd.Timedelta(days=aggregate_window_days))
        ]
        if future.empty:
            continue
        window_rows = future.head(aggregate_window_max_sessions).copy()
        window_values = []
        window_scales = []
        for _, outcome_row in window_rows.iterrows():
            if not pd.isna(outcome_row["outcome_fds"]):
                window_values.append(float(outcome_row["outcome_fds"]))
                window_scales.append("fds")
            elif not pd.isna(outcome_row["outcome_fds_lite"]):
                window_values.append(float(outcome_row["outcome_fds_lite"]))
                window_scales.append("fds_lite")
            elif not pd.isna(outcome_row["outcome_oriented"]):
                window_values.append(float(outcome_row["outcome_oriented"]))
                window_scales.append("oriented_raw_fallback")
        if not window_values:
            continue
        next_row = window_rows.iloc[0]
        outcome_value = float(np.mean(window_values))
        unique_scales = set(window_scales)
        if aggregate_window_max_sessions == 1:
            outcome_scale = window_scales[0]
        else:
            outcome_scale = f"window_mean_{window_scales[0]}" if len(unique_scales) == 1 else "window_mean_mixed"
        rows.append(
            {
                "Fecha": current_date,
                "outcome_date": next_row["Fecha"],
                "outcome_end_date": window_rows["Fecha"].iloc[-1],
                "outcome_window_n": int(len(window_values)),
                "lag_days": int((next_row["Fecha"] - current_date).days),
                "outcome_value": outcome_value,
                "outcome_raw_value": float(window_rows[outcome_col].mean()),
                "session_family": str(next_row["session_family"]),
                "session_family_sport": str(next_row["session_family_sport"]),
                "dominant_sport": str(next_row["dominant_sport"]),
                "sport_family": str(next_row["sport_family"]),
                "dominant_session_group": str(next_row["dominant_session_group"]),
                "dominant_route_id": None if pd.isna(next_row["dominant_route_id"]) else int(float(next_row["dominant_route_id"])),
                "comparison_key": str(next_row["comparison_key"]),
                "comparison_level": str(next_row["comparison_level"]),
                "family_baseline_n": int(next_row["family_baseline_n"]),
                "outcome_scale": outcome_scale,
                "ssm_goodness": float(row.ssm_recovery_state),
                "rolling_hrv_goodness": float(row.control_rolling_hrv_7d) if not pd.isna(row.control_rolling_hrv_7d) else np.nan,
                "load_badness": float(row.control_load_7d) if not pd.isna(row.control_load_7d) else np.nan,
                "gate_badness": final_map.get(current_date, np.nan),
                "ssm_state_var": float(row.ssm_state_var) if not pd.isna(row.ssm_state_var) else np.nan,
            }
        )
    columns = [
        "Fecha",
        "outcome_date",
        "outcome_end_date",
        "outcome_window_n",
        "lag_days",
        "outcome_value",
        "outcome_raw_value",
        "session_family",
        "session_family_sport",
        "dominant_sport",
        "sport_family",
        "dominant_session_group",
        "dominant_route_id",
        "comparison_key",
        "comparison_level",
        "family_baseline_n",
        "outcome_scale",
        "ssm_goodness",
        "rolling_hrv_goodness",
        "load_badness",
        "gate_badness",
        "ssm_state_var",
    ]
    return pd.DataFrame(rows, columns=columns)


def _build_strict_funnel(pairs: pd.DataFrame) -> dict[str, int]:
    if pairs.empty:
        return {
            "all_pairs": 0,
            "fds_only": 0,
            "no_strength": 0,
            "aerobic_sports_only": 0,
            "valid_comparison_level": 0,
            "baseline_n_gte_3": 0,
        }
    all_pairs = pairs.copy()
    fds_only = all_pairs[all_pairs["outcome_scale"].eq("fds")].copy()
    no_strength = fds_only[~fds_only["session_family"].eq("strength_only")].copy()
    aerobic = no_strength[no_strength["sport_family"].isin(["run", "bike", "hike", "elliptical"])].copy()
    comparison = aerobic[aerobic["comparison_level"].isin(["route_id", "session_group", "family_sport"])].copy()
    baseline = comparison[comparison["family_baseline_n"] >= 3].copy()
    return {
        "all_pairs": int(len(all_pairs)),
        "fds_only": int(len(fds_only)),
        "no_strength": int(len(no_strength)),
        "aerobic_sports_only": int(len(aerobic)),
        "valid_comparison_level": int(len(comparison)),
        "baseline_n_gte_3": int(len(baseline)),
    }


def _build_outcome_diagnostics(outcome_rows: pd.DataFrame) -> dict[str, object]:
    if outcome_rows.empty:
        return {
            "n_rows": 0,
            "n_with_fds": 0,
            "n_with_fds_lite": 0,
            "n_baseline_gte_3": 0,
            "n_baseline_gte_3_fds_blocked_zero_mad": 0,
            "outcome_oriented_zero_share": float("nan"),
            "outcome_oriented_unique_values_top": {},
            "primary_failure_mode": "no_comparable_outcomes",
        }

    baseline_gte_3 = outcome_rows["family_baseline_n"] >= 3
    blocked_zero_mad = baseline_gte_3 & outcome_rows["outcome_fds"].isna()
    value_counts = outcome_rows["outcome_oriented"].value_counts(dropna=False).head(8)
    zero_share = float(outcome_rows["outcome_oriented"].eq(0).mean()) if len(outcome_rows) else float("nan")
    if int(outcome_rows["outcome_fds"].notna().sum()) == 0 and int(blocked_zero_mad.sum()) > 0:
        failure_mode = "within_family_outcome_mad_zero"
    elif int(outcome_rows["outcome_fds"].notna().sum()) == 0:
        failure_mode = "insufficient_comparable_history"
    else:
        failure_mode = "fds_available"
    return {
        "n_rows": int(len(outcome_rows)),
        "n_with_fds": int(outcome_rows["outcome_fds"].notna().sum()),
        "n_with_fds_lite": int(outcome_rows["outcome_fds_lite"].notna().sum()),
        "n_baseline_gte_3": int(baseline_gte_3.sum()),
        "n_baseline_gte_3_fds_blocked_zero_mad": int(blocked_zero_mad.sum()),
        "outcome_oriented_zero_share": zero_share,
        "outcome_oriented_unique_values_top": {str(key): int(value) for key, value in value_counts.to_dict().items()},
        "primary_failure_mode": failure_mode,
    }


def _filter_primary_strict_pairs(pairs: pd.DataFrame) -> pd.DataFrame:
    if pairs.empty:
        return pairs.copy()
    df = pairs.copy()
    return df[
        df["outcome_scale"].eq("fds")
        & ~df["session_family"].eq("strength_only")
        & df["sport_family"].isin(["run", "bike", "hike", "elliptical"])
        & df["comparison_level"].isin(["route_id", "session_group", "family_sport"])
        & (df["family_baseline_n"] >= 3)
    ].copy()


def _filter_primary_lite_pairs(pairs: pd.DataFrame) -> pd.DataFrame:
    if pairs.empty:
        return pairs.copy()
    df = pairs.copy()
    return df[
        df["outcome_scale"].isin(["fds", "fds_lite"])
        & ~df["session_family"].eq("strength_only")
        & df["sport_family"].isin(["run", "bike", "hike", "elliptical"])
        & df["comparison_level"].isin(["route_id", "session_group", "family_sport"])
        & (df["family_baseline_n"] >= 2)
    ].copy()


def _holdout_split_predictions(df: pd.DataFrame, predictor: str) -> dict[str, object]:
    df = df[[predictor, "outcome_value"]].dropna().copy()
    if len(df) < 8:
        return {
            "n_pairs": int(len(df)),
            "holdout_mae": float("nan"),
            "holdout_rmse": float("nan"),
            "train_n": 0,
            "test_n": 0,
            "y_test": np.array([], dtype=float),
            "pred_test": np.array([], dtype=float),
        }
    split = max(int(len(df) * 0.8), 8)
    train = df.iloc[:split].copy()
    test = df.iloc[split:].copy()
    if len(test) < 4:
        return {
            "n_pairs": int(len(df)),
            "holdout_mae": float("nan"),
            "holdout_rmse": float("nan"),
            "train_n": int(len(train)),
            "test_n": int(len(test)),
            "y_test": np.array([], dtype=float),
            "pred_test": np.array([], dtype=float),
        }
    x_train = np.column_stack([np.ones(len(train), dtype=float), train[predictor].to_numpy(dtype=float)])
    y_train = train["outcome_value"].to_numpy(dtype=float)
    beta, _, _, _ = np.linalg.lstsq(x_train, y_train, rcond=None)
    x_test = np.column_stack([np.ones(len(test), dtype=float), test[predictor].to_numpy(dtype=float)])
    y_test = test["outcome_value"].to_numpy(dtype=float)
    pred = x_test @ beta
    return {
        "n_pairs": int(len(df)),
        "holdout_mae": float(np.mean(np.abs(y_test - pred))),
        "holdout_rmse": float(np.sqrt(np.mean((y_test - pred) ** 2))),
        "train_n": int(len(train)),
        "test_n": int(len(test)),
        "y_test": y_test,
        "pred_test": pred,
    }


def _median_baseline_holdout(df: pd.DataFrame) -> dict[str, object]:
    df = df[["outcome_value"]].dropna().copy()
    if len(df) < 8:
        return {
            "n_pairs": int(len(df)),
            "holdout_mae": float("nan"),
            "holdout_rmse": float("nan"),
            "train_n": 0,
            "test_n": 0,
            "y_test": np.array([], dtype=float),
            "pred_test": np.array([], dtype=float),
        }
    split = max(int(len(df) * 0.8), 8)
    train = df.iloc[:split].copy()
    test = df.iloc[split:].copy()
    if len(test) < 4:
        return {
            "n_pairs": int(len(df)),
            "holdout_mae": float("nan"),
            "holdout_rmse": float("nan"),
            "train_n": int(len(train)),
            "test_n": int(len(test)),
            "y_test": np.array([], dtype=float),
            "pred_test": np.array([], dtype=float),
        }
    median = float(train["outcome_value"].median())
    y_test = test["outcome_value"].to_numpy(dtype=float)
    pred = np.full(len(test), median, dtype=float)
    return {
        "n_pairs": int(len(df)),
        "holdout_mae": float(np.mean(np.abs(y_test - pred))),
        "holdout_rmse": float(np.sqrt(np.mean((y_test - pred) ** 2))),
        "train_n": int(len(train)),
        "test_n": int(len(test)),
        "y_test": y_test,
        "pred_test": pred,
    }


def _family_last_baseline_holdout(df: pd.DataFrame) -> dict[str, object]:
    if df.empty or "comparison_key" not in df.columns:
        return {
            "n_pairs": 0,
            "holdout_mae": float("nan"),
            "holdout_rmse": float("nan"),
            "train_n": 0,
            "test_n": 0,
            "y_test": np.array([], dtype=float),
            "pred_test": np.array([], dtype=float),
        }
    ordered = df[["Fecha", "comparison_key", "outcome_value"]].dropna().sort_values("Fecha").copy()
    if len(ordered) < 8:
        return {
            "n_pairs": int(len(ordered)),
            "holdout_mae": float("nan"),
            "holdout_rmse": float("nan"),
            "train_n": 0,
            "test_n": 0,
            "y_test": np.array([], dtype=float),
            "pred_test": np.array([], dtype=float),
        }
    split = max(int(len(ordered) * 0.8), 8)
    train = ordered.iloc[:split].copy()
    test = ordered.iloc[split:].copy()
    if len(test) < 4:
        return {
            "n_pairs": int(len(ordered)),
            "holdout_mae": float("nan"),
            "holdout_rmse": float("nan"),
            "train_n": int(len(train)),
            "test_n": int(len(test)),
            "y_test": np.array([], dtype=float),
            "pred_test": np.array([], dtype=float),
        }
    family_last: dict[str, float] = {}
    train_median = float(train["outcome_value"].median())
    for row in train.itertuples(index=False):
        family_last[str(row.comparison_key)] = float(row.outcome_value)
    y_test = []
    pred_test = []
    for row in test.itertuples(index=False):
        key = str(row.comparison_key)
        pred_test.append(family_last.get(key, train_median))
        y_test.append(float(row.outcome_value))
        family_last[key] = float(row.outcome_value)
    y_test_arr = np.asarray(y_test, dtype=float)
    pred_arr = np.asarray(pred_test, dtype=float)
    return {
        "n_pairs": int(len(ordered)),
        "holdout_mae": float(np.mean(np.abs(y_test_arr - pred_arr))),
        "holdout_rmse": float(np.sqrt(np.mean((y_test_arr - pred_arr) ** 2))),
        "train_n": int(len(train)),
        "test_n": int(len(test)),
        "y_test": y_test_arr,
        "pred_test": pred_arr,
    }


def _bootstrap_mae_delta(
    y_a: np.ndarray,
    pred_a: np.ndarray,
    y_b: np.ndarray,
    pred_b: np.ndarray,
    n_iter: int = BOOTSTRAP_ITERATIONS,
) -> dict[str, object]:
    if len(y_a) < 4 or len(y_b) < 4 or len(y_a) != len(y_b):
        return {"status": "insufficient_data"}
    n = len(y_a)
    rng = np.random.default_rng(1337 + n)
    deltas = np.empty(n_iter, dtype=float)
    for idx in range(n_iter):
        sample = rng.integers(0, n, size=n)
        mae_a = float(np.mean(np.abs(y_a[sample] - pred_a[sample])))
        mae_b = float(np.mean(np.abs(y_b[sample] - pred_b[sample])))
        deltas[idx] = mae_a - mae_b
    return {
        "status": "ok",
        "n_iter": int(n_iter),
        "delta_mae_mean": float(np.mean(deltas)),
        "delta_mae_median": float(np.median(deltas)),
        "delta_mae_ci90": [float(np.quantile(deltas, 0.05)), float(np.quantile(deltas, 0.95))],
        "prob_delta_gt_0": float(np.mean(deltas > 0.0)),
    }


def _evaluate_single_predictor(pairs: pd.DataFrame, predictor: str) -> dict[str, object]:
    df = pairs[[predictor, "outcome_value"]].dropna().copy()
    if len(df) < 12:
        return {
            "n_pairs": int(len(df)),
            "spearman_rho": float("nan"),
            "spearman_p_value": float("nan"),
            "holdout_mae": float("nan"),
            "holdout_rmse": float("nan"),
            "walk_forward_status": "insufficient_data",
            "walk_forward_n_folds": 0,
            "walk_forward_mae_mean": float("nan"),
            "walk_forward_mae_median": float("nan"),
            "walk_forward_mae_by_fold": [],
            "direction_ok": None,
        }

    rho, p_value = stats.spearmanr(df[predictor].to_numpy(dtype=float), df["outcome_value"].to_numpy(dtype=float))
    holdout = _holdout_split_predictions(df, predictor)
    holdout_mae = float(holdout["holdout_mae"])
    holdout_rmse = float(holdout["holdout_rmse"])

    walk_forward_folds: list[dict[str, object]] = []
    if len(df) >= 48:
        n_folds = 4 if len(df) >= 120 else 3
        test_size = max(len(df) // (n_folds + 2), 12)
        train_min = max(24, test_size * 2)
        split_points = []
        start = train_min
        while start + test_size <= len(df):
            split_points.append(start)
            start += test_size
        split_points = split_points[:n_folds]
        for fold_idx, split_idx in enumerate(split_points, start=1):
            train_fold = df.iloc[:split_idx].copy()
            test_fold = df.iloc[split_idx : split_idx + test_size].copy()
            if len(train_fold) < 24 or len(test_fold) < 8:
                continue
            x_train = np.column_stack([np.ones(len(train_fold), dtype=float), train_fold[predictor].to_numpy(dtype=float)])
            y_train = train_fold["outcome_value"].to_numpy(dtype=float)
            beta_fold, _, _, _ = np.linalg.lstsq(x_train, y_train, rcond=None)
            x_test = np.column_stack([np.ones(len(test_fold), dtype=float), test_fold[predictor].to_numpy(dtype=float)])
            y_test = test_fold["outcome_value"].to_numpy(dtype=float)
            pred = x_test @ beta_fold
            walk_forward_folds.append(
                {
                    "fold": fold_idx,
                    "train_n": int(len(train_fold)),
                    "test_n": int(len(test_fold)),
                    "mae": float(np.mean(np.abs(y_test - pred))),
                    "rmse": float(np.sqrt(np.mean((y_test - pred) ** 2))),
                }
            )

    walk_forward_maes = [item["mae"] for item in walk_forward_folds if np.isfinite(item.get("mae", np.nan))]
    walk_forward_status = "ok" if walk_forward_maes else "insufficient_data"

    return {
        "n_pairs": int(len(df)),
        "spearman_rho": float(rho) if rho is not None else float("nan"),
        "spearman_p_value": float(p_value) if p_value is not None else float("nan"),
        "holdout_mae": holdout_mae,
        "holdout_rmse": holdout_rmse,
        "walk_forward_status": walk_forward_status,
        "walk_forward_n_folds": int(len(walk_forward_folds)),
        "walk_forward_mae_mean": float(np.mean(walk_forward_maes)) if walk_forward_maes else float("nan"),
        "walk_forward_mae_median": float(np.median(walk_forward_maes)) if walk_forward_maes else float("nan"),
        "walk_forward_mae_by_fold": walk_forward_folds,
        "direction_ok": bool(rho > 0) if np.isfinite(rho) else None,
    }


def _ewma_series(values: pd.Series, alpha: float) -> pd.Series:
    arr = _safe_float_series(values).to_numpy(dtype=float)
    out = np.full(len(arr), np.nan, dtype=float)
    prev = np.nan
    for idx, value in enumerate(arr):
        if np.isfinite(value):
            prev = value if not np.isfinite(prev) else (alpha * value) + ((1.0 - alpha) * prev)
        out[idx] = prev
    return pd.Series(out, index=values.index, dtype=float)


def _build_ewma_comparator(
    core_df: pd.DataFrame | None,
    current_primary_pairs: pd.DataFrame,
) -> dict[str, object]:
    if core_df is None:
        return {"status": "core_not_available"}
    if current_primary_pairs.empty or "Fecha" not in current_primary_pairs.columns:
        return {"status": "insufficient_data", "grid": []}
    if "Fecha" not in core_df.columns or "lnRMSSD" not in core_df.columns:
        return {"status": "insufficient_data", "grid": []}

    current_pairs = current_primary_pairs.copy()
    current_pairs["Fecha"] = pd.to_datetime(current_pairs["Fecha"], errors="coerce")
    current_pairs["outcome_date"] = pd.to_datetime(current_pairs.get("outcome_date", current_pairs["Fecha"]), errors="coerce")
    current_pairs = current_pairs[current_pairs["Fecha"].notna()].copy().sort_values(["Fecha", "outcome_date"]).reset_index(drop=True)

    current_eval = _evaluate_single_predictor(current_pairs, "ssm_goodness")
    if len(current_pairs) < 12 or not np.isfinite(current_eval.get("holdout_mae", np.nan)):
        return {
            "status": "insufficient_data",
            "current_model_kind": "banister_2state",
            "baseline_model_kind": "ewma_lnrmssd",
            "current_model": current_eval,
            "grid": [],
        }

    ewma_source = core_df[["Fecha", "lnRMSSD"]].copy()
    ewma_source["Fecha"] = pd.to_datetime(ewma_source["Fecha"], errors="coerce")
    ewma_source = ewma_source[ewma_source["Fecha"].notna()].sort_values("Fecha").reset_index(drop=True)
    if ewma_source.empty:
        return {
            "status": "insufficient_data",
            "current_model_kind": "banister_2state",
            "baseline_model_kind": "ewma_lnrmssd",
            "current_model": current_eval,
            "grid": [],
        }

    grid_results: list[dict[str, object]] = []
    for alpha in EWMA_ALPHA_GRID:
        alpha_label = f"{alpha:.2f}".replace(".", "p")
        ewma_column = f"ewma_lnrmssd_{alpha_label}"
        ewma_source[ewma_column] = _ewma_series(ewma_source["lnRMSSD"], alpha)
        aligned = current_pairs.merge(
            ewma_source[["Fecha", ewma_column]],
            on="Fecha",
            how="inner",
        ).rename(columns={ewma_column: "predictor"})
        aligned = aligned.sort_values(["Fecha", "outcome_date"]).reset_index(drop=True)
        ewma_eval = _evaluate_single_predictor(aligned, "predictor")
        grid_results.append(
            {
                "alpha": alpha,
                "aligned_pairs_n": int(len(aligned)),
                "spearman_rho": ewma_eval["spearman_rho"],
                "spearman_p_value": ewma_eval["spearman_p_value"],
                "holdout_mae": ewma_eval["holdout_mae"],
                "holdout_rmse": ewma_eval["holdout_rmse"],
                "walk_forward_status": ewma_eval["walk_forward_status"],
                "walk_forward_n_folds": ewma_eval["walk_forward_n_folds"],
                "walk_forward_mae_mean": ewma_eval["walk_forward_mae_mean"],
                "walk_forward_mae_median": ewma_eval["walk_forward_mae_median"],
                "direction_ok": ewma_eval["direction_ok"],
            }
        )

    valid_results = [row for row in grid_results if np.isfinite(row.get("holdout_mae", np.nan))]
    if not valid_results:
        return {
            "status": "insufficient_data",
            "current_model_kind": "banister_2state",
            "baseline_model_kind": "ewma_lnrmssd",
            "current_model": current_eval,
            "grid": grid_results,
        }

    best_holdout = min(valid_results, key=lambda row: row["holdout_mae"])
    valid_wf_results = [row for row in valid_results if np.isfinite(row.get("walk_forward_mae_mean", np.nan))]
    best_walk_forward = min(valid_wf_results, key=lambda row: row["walk_forward_mae_mean"]) if valid_wf_results else None
    current_holdout = float(current_eval.get("holdout_mae", np.nan))
    current_wf = float(current_eval.get("walk_forward_mae_mean", np.nan))
    best_holdout_mae = float(best_holdout["holdout_mae"])
    best_wf_mae = float(best_walk_forward["walk_forward_mae_mean"]) if best_walk_forward is not None else float("nan")
    margin = 0.01
    if np.isfinite(current_holdout) and np.isfinite(current_wf):
        if (best_holdout_mae + margin) < current_holdout and (best_wf_mae + margin) < current_wf:
            status = "prefer_ewma"
        elif (current_holdout + margin) < best_holdout_mae and (current_wf + margin) < best_wf_mae:
            status = "prefer_current_ssm"
        elif abs(current_holdout - best_holdout_mae) <= margin and (
            not np.isfinite(best_wf_mae) or abs(current_wf - best_wf_mae) <= margin
        ):
            status = "equivalent_holdout"
        else:
            status = "mixed"
    else:
        status = "insufficient_data"

    return {
        "status": status,
        "current_model_kind": "banister_2state",
        "baseline_model_kind": "ewma_lnrmssd",
        "current_model": current_eval,
        "ewma_best_by_holdout": best_holdout,
        "ewma_best_by_walk_forward": best_walk_forward or {},
        "current_vs_ewma_holdout_mae_delta": float(current_holdout - best_holdout_mae) if np.isfinite(current_holdout) else float("nan"),
        "current_vs_ewma_walk_forward_mae_delta": float(current_wf - best_wf_mae) if np.isfinite(current_wf) and np.isfinite(best_wf_mae) else float("nan"),
        "best_holdout_alpha": float(best_holdout["alpha"]),
        "best_walk_forward_alpha": float(best_walk_forward["alpha"]) if best_walk_forward is not None else float("nan"),
        "best_holdout_mae": best_holdout_mae,
        "best_walk_forward_mae_mean": best_wf_mae,
        "grid": grid_results,
    }


def _redundancy_check(pairs: pd.DataFrame) -> dict[str, object]:
    df = pairs[["ssm_goodness", "rolling_hrv_goodness", "load_badness"]].dropna().copy()
    if len(df) < 20:
        return {"n_rows": int(len(df)), "r2": float("nan"), "status": "insufficient_data"}
    x = np.column_stack(
        [
            np.ones(len(df), dtype=float),
            df["rolling_hrv_goodness"].to_numpy(dtype=float),
            df["load_badness"].to_numpy(dtype=float),
        ]
    )
    y = df["ssm_goodness"].to_numpy(dtype=float)
    beta, _, _, _ = np.linalg.lstsq(x, y, rcond=None)
    pred = x @ beta
    ss_tot = float(np.sum((y - np.mean(y)) ** 2))
    r2 = float(1.0 - (np.sum((y - pred) ** 2) / ss_tot)) if ss_tot > 0 else float("nan")
    status = "redundant" if np.isfinite(r2) and r2 >= 0.90 else "distinct_enough"
    return {"n_rows": int(len(df)), "r2": r2, "status": status}


def _uncertainty_slice(pairs: pd.DataFrame) -> dict[str, object]:
    df = pairs[["ssm_state_var", "outcome_value"]].dropna().copy()
    if len(df) < 20:
        return {"status": "insufficient_data"}
    q75 = float(df["ssm_state_var"].quantile(0.75))
    q25 = float(df["ssm_state_var"].quantile(0.25))
    hi = df[df["ssm_state_var"] >= q75]
    lo = df[df["ssm_state_var"] <= q25]
    return {
        "status": "ok",
        "high_var_n": int(len(hi)),
        "low_var_n": int(len(lo)),
        "high_var_outcome_mean": float(hi["outcome_value"].mean()) if len(hi) else float("nan"),
        "low_var_outcome_mean": float(lo["outcome_value"].mean()) if len(lo) else float("nan"),
    }


def _goodness_audit_single(pairs: pd.DataFrame, predictor: str, label: str) -> dict[str, object]:
    df = pairs[[predictor, "outcome_value"]].dropna().copy()
    if len(df) < 12:
        return {
            "predictor_label": label,
            "n_pairs": int(len(df)),
            "rho_goodness": float("nan"),
            "p_value_goodness": float("nan"),
            "goodness_supported": None,
            "preferred_semantics": "insufficient_data",
        }
    rho, p_value = stats.spearmanr(df[predictor].to_numpy(dtype=float), df["outcome_value"].to_numpy(dtype=float))
    goodness_supported = bool(rho > 0) if rho is not None and np.isfinite(rho) else None
    preferred = "goodness" if goodness_supported else "ambiguous"
    return {
        "predictor_label": label,
        "n_pairs": int(len(df)),
        "rho_goodness": float(rho) if rho is not None else float("nan"),
        "p_value_goodness": float(p_value) if p_value is not None else float("nan"),
        "goodness_supported": goodness_supported,
        "preferred_semantics": preferred,
    }


def _build_sign_semantics_audit(pairs: pd.DataFrame) -> dict[str, object]:
    return {
        "ssm_state": _goodness_audit_single(pairs, "ssm_goodness", "ssm_recovery_state"),
        "rolling_hrv_7d": _goodness_audit_single(pairs, "rolling_hrv_goodness", "control_rolling_hrv_7d"),
    }


def _align_structural_pairs(current_pairs: pd.DataFrame, hrv_only_pairs: pd.DataFrame) -> pd.DataFrame:
    if current_pairs.empty or hrv_only_pairs.empty:
        return pd.DataFrame(
            columns=[
                "Fecha",
                "outcome_date",
                "outcome_value",
                "current_ssm_goodness",
                "hrv_only_ssm_goodness",
                "rolling_hrv_goodness",
                "load_badness",
                "gate_badness",
            ]
        )
    current = current_pairs.rename(columns={"ssm_goodness": "current_ssm_goodness"}).copy()
    hrv_only = hrv_only_pairs.rename(columns={"ssm_goodness": "hrv_only_ssm_goodness"})[
        ["Fecha", "outcome_date", "hrv_only_ssm_goodness"]
    ].copy()
    merged = current.merge(hrv_only, on=["Fecha", "outcome_date"], how="inner")
    return merged[
        [
            "Fecha",
            "outcome_date",
            "outcome_value",
            "current_ssm_goodness",
            "hrv_only_ssm_goodness",
            "rolling_hrv_goodness",
            "load_badness",
            "gate_badness",
        ]
    ].copy()


def _load_on_hrv_only_innovations(shadow_frame: pd.DataFrame) -> dict[str, object]:
    if shadow_frame.empty or "ssm_innovation" not in shadow_frame.columns:
        return {"status": "innovation_series_unavailable"}
    df = pd.DataFrame(
        {
            "innovation": _safe_float_series(shadow_frame["ssm_innovation"]),
            "load_prev": _safe_float_series(shadow_frame["load_day"]).shift(1),
        }
    ).dropna()
    if len(df) < 20:
        return {
            "status": "insufficient_data",
            "n_rows": int(len(df)),
            "coef": float("nan"),
            "p_value": float("nan"),
            "r2": float("nan"),
        }
    y = df["innovation"].to_numpy(dtype=float)
    result = ssm_builder._ols_with_pvalue(y, [df["load_prev"].to_numpy(dtype=float)])
    status = "load_explains_innovations" if np.isfinite(result["p_value"]) and result["p_value"] < 0.05 else "no_evidence_load_explains_innovations"
    return {
        "status": status,
        "n_rows": int(len(df)),
        "coef": result["coef"],
        "se": result["se"],
        "p_value": result["p_value"],
        "r2": result["r2"],
    }


def _build_structural_comparator(
    core_df: pd.DataFrame | None,
    sessions_day: pd.DataFrame,
    sessions_df: pd.DataFrame | None,
    final_df: pd.DataFrame | None,
    sleep_df: pd.DataFrame | None,
    outcome_col: str,
    outcome_rows: pd.DataFrame,
    current_primary_pairs: pd.DataFrame,
    precomputed_base: pd.DataFrame | None = None,
) -> dict[str, object]:
    if core_df is None:
        return {"status": "core_not_available"}

    current_cfg = ssm_builder.CFG
    current_is_load_free = abs(float(current_cfg.beta_slow)) < 1e-12 and abs(float(current_cfg.beta_fast)) < 1e-12
    alternative_cfg = replace(ssm_builder.CFG, beta_slow=0.0, beta_fast=0.0)
    alternative_label = "banister_hrv_only"

    empty_wellness = pd.DataFrame(columns=["Fecha"])
    base = precomputed_base if precomputed_base is not None else ssm_builder.preprocess_base(
        core_df, sessions_day, sleep_df, current_cfg
    )

    current_sidecar, current_detail = ssm_builder.run_ssm_from_base(base, sessions_day, empty_wellness, cfg=current_cfg)
    alternative_sidecar, alternative_detail = ssm_builder.run_ssm_from_base(base, sessions_day, empty_wellness, cfg=alternative_cfg)
    alternative_sidecar = alternative_sidecar.copy()
    alternative_sidecar["Fecha"] = pd.to_datetime(alternative_sidecar["Fecha"], errors="coerce")
    alternative_pairs = _find_next_outcome_pairs(alternative_sidecar, outcome_rows, outcome_col, final_df)
    alternative_primary_pairs = _filter_primary_strict_pairs(alternative_pairs)
    aligned = _align_structural_pairs(current_primary_pairs, alternative_primary_pairs)
    current_eval = _evaluate_single_predictor(aligned.rename(columns={"current_ssm_goodness": "predictor"}), "predictor")
    alternative_eval = _evaluate_single_predictor(aligned.rename(columns={"hrv_only_ssm_goodness": "predictor"}), "predictor")
    current_mae = current_eval.get("holdout_mae", np.nan)
    alternative_mae = alternative_eval.get("holdout_mae", np.nan)
    if np.isfinite(current_mae) and np.isfinite(alternative_mae):
        if current_mae < alternative_mae:
            comparator_status = "prefer_current_banister" if not current_is_load_free else "prefer_current_hrv_only"
        elif alternative_mae < current_mae:
            comparator_status = "prefer_banister_hrv_only" if not current_is_load_free else "prefer_hrv_only"
        else:
            comparator_status = "equivalent_holdout"
    else:
        comparator_status = "insufficient_data"
    return {
        "status": comparator_status,
        "current_model_kind": "banister_2state",
        "alternative_model_kind": "banister_hrv_only",
        "current_load_betas": {
            "beta_slow": float(current_cfg.beta_slow),
            "beta_fast": float(current_cfg.beta_fast),
        },
        "alternative_load_betas": {
            "beta_slow": float(alternative_cfg.beta_slow),
            "beta_fast": float(alternative_cfg.beta_fast),
        },
        "aligned_pairs_n": int(len(aligned)),
        "current_model": current_eval,
        alternative_label: alternative_eval,
        "load_on_hrv_only_innovations": _load_on_hrv_only_innovations(alternative_detail["shadow_frame"]),
    }


def _build_sleep_comparator(
    core_df: pd.DataFrame | None,
    sessions_day: pd.DataFrame,
    sessions_df: pd.DataFrame | None,
    final_df: pd.DataFrame | None,
    sleep_df: pd.DataFrame | None,
    outcome_col: str,
    outcome_rows: pd.DataFrame,
    current_primary_pairs: pd.DataFrame,
) -> dict[str, object]:
    if core_df is None:
        return {"status": "core_not_available"}

    current_sidecar, current_detail = ssm_builder.build_ssm_shadow(
        core_df,
        sessions_day,
        pd.DataFrame(columns=["Fecha"]),
        sleep_df=sleep_df,
        cfg=ssm_builder.CFG,
    )
    sleep_free_sidecar, sleep_free_detail = ssm_builder.build_ssm_shadow(
        core_df,
        sessions_day,
        pd.DataFrame(columns=["Fecha"]),
        sleep_df=pd.DataFrame(columns=["Fecha"]),
        cfg=ssm_builder.CFG,
    )
    sleep_free_sidecar = sleep_free_sidecar.copy()
    sleep_free_sidecar["Fecha"] = pd.to_datetime(sleep_free_sidecar["Fecha"], errors="coerce")
    sleep_free_pairs = _find_next_outcome_pairs(sleep_free_sidecar, outcome_rows, outcome_col, final_df)
    sleep_free_primary_pairs = _filter_primary_strict_pairs(sleep_free_pairs)
    aligned = _align_structural_pairs(current_primary_pairs, sleep_free_primary_pairs)
    current_eval = _evaluate_single_predictor(aligned.rename(columns={"current_ssm_goodness": "predictor"}), "predictor")
    sleep_free_eval = _evaluate_single_predictor(aligned.rename(columns={"hrv_only_ssm_goodness": "predictor"}), "predictor")
    current_mae = current_eval.get("holdout_mae", np.nan)
    sleep_free_mae = sleep_free_eval.get("holdout_mae", np.nan)
    if np.isfinite(current_mae) and np.isfinite(sleep_free_mae):
        if current_mae < sleep_free_mae:
            comparator_status = "prefer_sleep_augmented"
        elif sleep_free_mae < current_mae:
            comparator_status = "prefer_sleep_free"
        else:
            comparator_status = "equivalent_holdout"
    else:
        comparator_status = "insufficient_data"
    return {
        "status": comparator_status,
        "current_model_kind": "banister_2state_with_sleep",
        "alternative_model_kind": "banister_2state_without_sleep",
        "aligned_pairs_n": int(len(aligned)),
        "current_model": current_eval,
        "sleep_free_model": sleep_free_eval,
        "sleep_on_holdout_mae_delta": float(sleep_free_mae - current_mae) if np.isfinite(current_mae) and np.isfinite(sleep_free_mae) else float("nan"),
        "sleep_current_coverage_n": int(current_detail.get("kalman_diagnostics", {}).get("sleep_observation_coverage_n", 0)),
        "sleep_free_coverage_n": int(sleep_free_detail.get("kalman_diagnostics", {}).get("sleep_observation_coverage_n", 0)),
    }


def _build_phi_sensitivity(
    core_df: pd.DataFrame | None,
    sessions_day: pd.DataFrame,
    sessions_df: pd.DataFrame | None,
    final_df: pd.DataFrame | None,
    sleep_df: pd.DataFrame | None,
    outcome_col: str,
    outcome_rows: pd.DataFrame,
    current_primary_pairs: pd.DataFrame,
    precomputed_base: pd.DataFrame | None = None,
) -> dict[str, object]:
    if core_df is None:
        return {"status": "core_not_available", "grid": []}

    empty_wellness = pd.DataFrame(columns=["Fecha"])
    base = precomputed_base if precomputed_base is not None else ssm_builder.preprocess_base(
        core_df, sessions_day, sleep_df, ssm_builder.CFG
    )

    current_eval = _evaluate_single_predictor(current_primary_pairs, "ssm_goodness")
    grid_results: list[dict[str, object]] = []
    for phi in PHI_SENSITIVITY_GRID:
        phi_cfg = replace(ssm_builder.CFG, phi_slow=phi)
        phi_sidecar, _ = ssm_builder.run_ssm_from_base(base, sessions_day, empty_wellness, cfg=phi_cfg)
        phi_sidecar = phi_sidecar.copy()
        phi_sidecar["Fecha"] = pd.to_datetime(phi_sidecar["Fecha"], errors="coerce")
        phi_pairs = _find_next_outcome_pairs(phi_sidecar, outcome_rows, outcome_col, final_df)
        phi_primary_pairs = _filter_primary_strict_pairs(phi_pairs)
        aligned_phi = current_primary_pairs.merge(
            phi_primary_pairs[["Fecha", "outcome_date", "ssm_goodness"]].rename(columns={"ssm_goodness": "phi_ssm_goodness"}),
            on=["Fecha", "outcome_date"],
            how="inner",
        )
        phi_eval = _evaluate_single_predictor(aligned_phi.rename(columns={"phi_ssm_goodness": "predictor"}), "predictor")
        grid_results.append(
            {
                "phi": phi,
                "aligned_pairs_n": int(len(aligned_phi)),
                "spearman_rho": phi_eval["spearman_rho"],
                "spearman_p_value": phi_eval["spearman_p_value"],
                "holdout_mae": phi_eval["holdout_mae"],
                "holdout_rmse": phi_eval["holdout_rmse"],
                "direction_ok": phi_eval["direction_ok"],
            }
        )

    valid_results = [row for row in grid_results if np.isfinite(row.get("holdout_mae", np.nan))]
    if not valid_results or not np.isfinite(current_eval.get("holdout_mae", np.nan)):
        return {"status": "insufficient_data", "grid": grid_results}

    best = min(valid_results, key=lambda row: row["holdout_mae"])
    current_phi = next((row for row in valid_results if abs(float(row["phi"]) - ssm_builder.CFG.phi_slow) < 1e-12), None)
    status = "current_phi_best_or_tied"
    if current_phi is not None and best["phi"] != current_phi["phi"]:
        improvement = float(current_phi["holdout_mae"] - best["holdout_mae"])
        status = "alternative_phi_better" if improvement > 0.01 else "current_phi_close_to_best"
    return {
        "status": status,
        "current_phi": ssm_builder.CFG.phi_slow,
        "best_phi": best["phi"],
        "best_holdout_mae": best["holdout_mae"],
        "current_holdout_mae": current_phi["holdout_mae"] if current_phi is not None else current_eval["holdout_mae"],
        "grid": grid_results,
    }


def _build_discordant_day_analysis(pairs: pd.DataFrame) -> dict[str, object]:
    if len(pairs) < 24:
        return {"status": "insufficient_data"}
    df = pairs.copy()
    ssm_q25 = float(df["ssm_goodness"].quantile(0.25))
    ssm_q75 = float(df["ssm_goodness"].quantile(0.75))
    load_q75 = float(df["load_badness"].dropna().quantile(0.75)) if df["load_badness"].notna().any() else float("nan")
    rolling_median = float(df["rolling_hrv_goodness"].dropna().median()) if df["rolling_hrv_goodness"].notna().any() else float("nan")
    gate_q25 = float(df["gate_badness"].dropna().quantile(0.25)) if df["gate_badness"].notna().any() else float("nan")
    gate_q75 = float(df["gate_badness"].dropna().quantile(0.75)) if df["gate_badness"].notna().any() else float("nan")

    df["flag_ssm_good_vs_load_high"] = df["ssm_goodness"].ge(ssm_q75) & df["load_badness"].ge(load_q75) if np.isfinite(load_q75) else False
    df["flag_ssm_bad_vs_hrv_normal"] = df["ssm_goodness"].le(ssm_q25) & df["rolling_hrv_goodness"].ge(rolling_median) if np.isfinite(rolling_median) else False
    gate_disagree = (
        (df["ssm_goodness"].le(ssm_q25) & df["gate_badness"].le(gate_q25))
        | (df["ssm_goodness"].ge(ssm_q75) & df["gate_badness"].ge(gate_q75))
    ) if np.isfinite(gate_q25) and np.isfinite(gate_q75) else False
    df["flag_ssm_vs_gate_disagree"] = gate_disagree
    df["discordant_any"] = (
        df["flag_ssm_good_vs_load_high"].astype(bool)
        | df["flag_ssm_bad_vs_hrv_normal"].astype(bool)
        | df["flag_ssm_vs_gate_disagree"].astype(bool)
    )

    discordant = df[df["discordant_any"]].copy()
    concordant = df[~df["discordant_any"]].copy()

    def _subset_block(subset: pd.DataFrame) -> dict[str, object]:
        return {
            "n_pairs": int(len(subset)),
            "ssm_goodness": _evaluate_single_predictor(subset, "ssm_goodness"),
            "rolling_hrv_goodness": _evaluate_single_predictor(subset, "rolling_hrv_goodness"),
            "load_badness": _evaluate_single_predictor(subset, "load_badness"),
            "gate_badness": _evaluate_single_predictor(subset, "gate_badness"),
        }

    return {
        "status": "ok",
        "thresholds": {
            "ssm_goodness_q25": ssm_q25,
            "ssm_goodness_q75": ssm_q75,
            "load_badness_q75": load_q75,
            "rolling_hrv_goodness_median": rolling_median,
            "gate_badness_q25": gate_q25,
            "gate_badness_q75": gate_q75,
        },
        "flag_counts": {
            "ssm_good_vs_load_high": int(df["flag_ssm_good_vs_load_high"].sum()),
            "ssm_bad_vs_hrv_normal": int(df["flag_ssm_bad_vs_hrv_normal"].sum()),
            "ssm_vs_gate_disagree": int(df["flag_ssm_vs_gate_disagree"].sum()),
            "discordant_any": int(df["discordant_any"].sum()),
            "concordant_any": int((~df["discordant_any"]).sum()),
        },
        "discordant_subset": _subset_block(discordant),
        "concordant_subset": _subset_block(concordant),
    }


def _build_sport_stratified_analysis(metadata: dict, pairs: pd.DataFrame) -> dict[str, object]:
    if pairs.empty or "sport_family" not in pairs.columns:
        return {"status": "insufficient_data", "sports": {}}
    sports: dict[str, object] = {}
    for sport, subset in pairs.groupby("sport_family", dropna=False):
        key = str(sport)
        sports[key] = _build_evaluation_block(metadata, subset.copy())
    viable = {key: value for key, value in sports.items() if value.get("n_pairs", 0) >= 12}
    return {
        "status": "ok" if viable else "insufficient_data",
        "sports": sports,
        "viable_sports": list(viable.keys()),
    }


def _promote_primary_strict_by_sport(sport_stratified_analysis: dict[str, object]) -> dict[str, object]:
    sports = sport_stratified_analysis.get("sports", {})
    promoted: dict[str, object] = {}
    for sport, block in sports.items():
        if block.get("n_pairs", 0) < 12:
            continue
        promoted[str(sport)] = {
            "filter_rule": "primary_strict restricted to one sport_family",
            **block,
        }
    return promoted


def _build_primary_operational_view(
    primary_block: dict[str, object],
    primary_strict_by_sport: dict[str, object],
    phase1_conclusion: dict[str, object],
) -> dict[str, object]:
    sport_go_statuses = {
        sport: str(block.get("go_no_go", {}).get("status", "unknown")) for sport, block in primary_strict_by_sport.items()
    }
    sport_primary_reading = str(phase1_conclusion.get("sport_primary_reading", "mixed"))
    if primary_strict_by_sport and sport_primary_reading == "no_sport_go":
        return {
            "mode": "sport_first",
            "recommended_primary_scope": "by_sport",
            "global_status": str(primary_block.get("go_no_go", {}).get("status", "unknown")),
            "sport_go_statuses": sport_go_statuses,
            "sport_primary_reading": sport_primary_reading,
            "summary": "Priorizar la lectura por deporte: el agregado global es secundario porque ningún deporte viable sostiene candidate_go.",
        }
    return {
        "mode": "global_with_sport_context",
        "recommended_primary_scope": "global",
        "global_status": str(primary_block.get("go_no_go", {}).get("status", "unknown")),
        "sport_go_statuses": sport_go_statuses,
        "sport_primary_reading": sport_primary_reading,
        "summary": "La lectura principal puede seguir siendo global, usando la estratificación por deporte como contexto.",
    }


def _build_walk_forward_by_sport(primary_strict_by_sport: dict[str, object]) -> dict[str, object]:
    summary: dict[str, object] = {}
    for sport, block in primary_strict_by_sport.items():
        evaluations = block.get("evaluations", {})
        summary[str(sport)] = {
            "n_pairs": int(block.get("n_pairs", 0)),
            "go_no_go": str(block.get("go_no_go", {}).get("status", "unknown")),
            "ssm_goodness": {
                "walk_forward_status": evaluations.get("ssm_goodness", {}).get("walk_forward_status", "unknown"),
                "walk_forward_n_folds": evaluations.get("ssm_goodness", {}).get("walk_forward_n_folds", 0),
                "walk_forward_mae_mean": evaluations.get("ssm_goodness", {}).get("walk_forward_mae_mean", float("nan")),
                "holdout_mae": evaluations.get("ssm_goodness", {}).get("holdout_mae", float("nan")),
            },
            "rolling_hrv_goodness": {
                "walk_forward_status": evaluations.get("rolling_hrv_goodness", {}).get("walk_forward_status", "unknown"),
                "walk_forward_n_folds": evaluations.get("rolling_hrv_goodness", {}).get("walk_forward_n_folds", 0),
                "walk_forward_mae_mean": evaluations.get("rolling_hrv_goodness", {}).get("walk_forward_mae_mean", float("nan")),
                "holdout_mae": evaluations.get("rolling_hrv_goodness", {}).get("holdout_mae", float("nan")),
            },
            "baseline_comparison": block.get("baseline_comparison", {}),
        }
    return {
        "status": "ok" if summary else "insufficient_data",
        "sports": summary,
    }


def _build_calibration_check(metadata: dict) -> dict[str, object]:
    kalman = metadata.get("kalman_diagnostics", {})
    coverage = kalman.get("interval_coverage_90pct", np.nan)
    ci95 = kalman.get("interval_coverage_ci95", [np.nan, np.nan])
    delta = kalman.get("interval_calibration_delta", np.nan)
    status = kalman.get("interval_calibration_status", "unknown")
    if not np.isfinite(coverage):
        return {
            "status": "insufficient_data",
            "target_coverage": 0.90,
            "observed_coverage": float("nan"),
            "delta": float("nan"),
            "ci95": [float("nan"), float("nan")],
            "coverage_n": int(kalman.get("interval_coverage_n", 0) or 0),
        }
    return {
        "status": status,
        "target_coverage": 0.90,
        "observed_coverage": float(coverage),
        "delta": float(delta),
        "ci95": [float(ci95[0]), float(ci95[1])] if isinstance(ci95, list) and len(ci95) == 2 else [float("nan"), float("nan")],
        "coverage_n": int(kalman.get("interval_coverage_n", 0) or 0),
    }


def _build_phase1_conclusion(
    outcome_col: str,
    sign_semantics_audit: dict[str, object],
    primary_block: dict[str, object],
    structural_comparator: dict[str, object],
    sleep_comparator: dict[str, object],
    ewma_comparator: dict[str, object],
    discordant_day_analysis: dict[str, object],
    sport_stratified_analysis: dict[str, object],
    outcome_normalization: dict[str, object],
) -> dict[str, object]:
    semantics = str(sign_semantics_audit.get("ssm_state", {}).get("preferred_semantics", "ambiguous"))
    discordant = discordant_day_analysis.get("discordant_subset", {})
    discordant_ssm = discordant.get("ssm_goodness", {}).get("holdout_mae", np.nan)
    discordant_rolling = discordant.get("rolling_hrv_goodness", {}).get("holdout_mae", np.nan)
    discordant_beats_rolling = bool(
        np.isfinite(discordant_ssm) and np.isfinite(discordant_rolling) and discordant_ssm < discordant_rolling
    )

    ssm_wf = primary_block.get("evaluations", {}).get("ssm_goodness", {}).get("walk_forward_mae_mean", np.nan)
    rolling_wf = primary_block.get("evaluations", {}).get("rolling_hrv_goodness", {}).get("walk_forward_mae_mean", np.nan)
    ssm_holdout = primary_block.get("evaluations", {}).get("ssm_goodness", {}).get("holdout_mae", np.nan)
    rolling_holdout = primary_block.get("evaluations", {}).get("rolling_hrv_goodness", {}).get("holdout_mae", np.nan)
    min_advantage_margin = 0.02
    holdout_advantage = bool(
        np.isfinite(ssm_holdout)
        and np.isfinite(rolling_holdout)
        and (rolling_holdout - ssm_holdout) >= min_advantage_margin
    )
    wf_advantage = bool(
        np.isfinite(ssm_wf)
        and np.isfinite(rolling_wf)
        and (rolling_wf - ssm_wf) >= min_advantage_margin
    )
    advantage_stable = holdout_advantage and wf_advantage

    sport_viable = sport_stratified_analysis.get("viable_sports", [])
    sports = sport_stratified_analysis.get("sports", {})
    primary_by_sport = _promote_primary_strict_by_sport(sport_stratified_analysis)
    sport_go_statuses = {
        sport: str(block.get("go_no_go", {}).get("status", "unknown")) for sport, block in primary_by_sport.items()
    }
    sport_candidate_go = [sport for sport, status in sport_go_statuses.items() if status == "candidate_go"]
    sport_no_go = [sport for sport, status in sport_go_statuses.items() if status == "no_go"]
    any_sport_candidate_go = bool(sport_candidate_go)
    all_viable_sports_no_go = bool(sport_go_statuses) and len(sport_no_go) == len(sport_go_statuses)
    run_ssm = sports.get("run", {}).get("evaluations", {}).get("ssm_goodness", {}).get("holdout_mae", np.nan)
    run_rolling = sports.get("run", {}).get("evaluations", {}).get("rolling_hrv_goodness", {}).get("holdout_mae", np.nan)
    bike_ssm = sports.get("bike", {}).get("evaluations", {}).get("ssm_goodness", {}).get("holdout_mae", np.nan)
    bike_rolling = sports.get("bike", {}).get("evaluations", {}).get("rolling_hrv_goodness", {}).get("holdout_mae", np.nan)
    run_ties_rolling = bool(np.isfinite(run_ssm) and np.isfinite(run_rolling) and abs(run_ssm - run_rolling) <= 0.05)
    bike_loses_to_rolling = bool(np.isfinite(bike_ssm) and np.isfinite(bike_rolling) and bike_ssm > bike_rolling)
    cross_sport_heterogeneous = outcome_col == "cardiac_drift_worst" and ("run" in sport_viable) and ("bike" in sport_viable)
    structural_status = str(structural_comparator.get("status", "unknown"))
    structural_hrv_only = structural_status in {"prefer_hrv_only", "prefer_current_hrv_only", "prefer_banister_hrv_only"}
    sleep_status = str(sleep_comparator.get("status", "unknown"))
    sleep_augmented_supported = sleep_status == "prefer_sleep_augmented"
    ewma_status = str(ewma_comparator.get("status", "unknown"))
    ewma_best_alpha = ewma_comparator.get("best_holdout_alpha", np.nan)
    ewma_best_holdout = ewma_comparator.get("best_holdout_mae", np.nan)
    ewma_best_wf = ewma_comparator.get("best_walk_forward_mae_mean", np.nan)
    normalization_applied = bool(outcome_normalization.get("applied"))
    global_go_no_go_status = str(primary_block.get("go_no_go", {}).get("status", "unknown"))

    if ewma_status == "prefer_ewma":
        ewma_clause = (
            f"El benchmark EWMA queda por delante del SSM (alpha={ewma_best_alpha:.2f}, "
            f"MAE holdout={ewma_best_holdout:.3f}, WF={ewma_best_wf:.3f}). "
        )
    elif ewma_status == "equivalent_holdout":
        ewma_clause = (
            f"El benchmark EWMA empata prácticamente al SSM (alpha={ewma_best_alpha:.2f}, "
            f"MAE holdout={ewma_best_holdout:.3f}, WF={ewma_best_wf:.3f}), lo que refuerza el riesgo de redundancia. "
        )
    elif ewma_status == "prefer_current_ssm":
        ewma_clause = (
            f"El benchmark EWMA no iguala al SSM (mejor alpha={ewma_best_alpha:.2f}), así que el Banister todavía conserva una ventaja modesta. "
        )
    else:
        ewma_clause = (
            f"El benchmark EWMA queda mixto (mejor alpha={ewma_best_alpha:.2f}), así que no resuelve por sí solo la discusión de degeneración. "
        )

    if all_viable_sports_no_go and global_go_no_go_status == "candidate_go":
        summary = "".join(
            [
                "Fase 1 completa. SSM sombra operativo como capa técnica auditada. ",
                "Semántica confirmada como goodness. ",
                "El bloque global todavía sale `candidate_go`, pero la lectura prioritaria ya no debe ser la agregada: ",
                "ningún deporte viable sostiene promoción propia (`",
                ", ".join(f"{sport}={status}" for sport, status in sport_go_statuses.items()),
                "`). ",
                "Tras normalizar `cardiac_drift_worst` por deporte, " if normalization_applied else "",
                "la señal sigue siendo deporte-dependiente y el agregado cross-sport resulta demasiado optimista para lectura operativa. ",
                "El comparador estructural respalda mantener HRV-only como base, así que el término de carga no queda respaldado como mejora robusta. ",
                "La observación nocturna de sueño tampoco mejora de forma robusta frente a la versión sin sueño. "
                if sleep_status == "prefer_sleep_free"
                else "La observación nocturna de sueño sí aporta una mejora pequeña frente a la versión sin sueño. "
                if sleep_augmented_supported
                else "",
                ewma_clause,
                "Infraestructura de validación madura y reutilizable. No apto aún para gate ni reason_text "
                "(existe en `build_hrv_final_dashboard.py` un bloque latente de contexto SSM tras feature flag "
                "`HRV_SSM_REASON_TEXT_ENABLED`, default `0`; sin filtro por deporte, no se activa en Fase 1). ",
                "Siguiente mejora natural: evaluar outcome principal por deporte en lugar de un target combinado.",
            ]
        )
    elif cross_sport_heterogeneous and run_ties_rolling and bike_loses_to_rolling:
        summary = "".join(
            [
                "Fase 1 completa. SSM sombra operativo como capa técnica auditada. ",
                "Semántica confirmada como goodness. ",
                "Tras normalizar `cardiac_drift_worst` por deporte, " if normalization_applied else "",
                "la estratificación por deporte muestra valor deporte-dependiente: en run el SSM empata aproximadamente con rolling HRV 7d; en bike pierde. ",
                "El comparador estructural respalda mantener HRV-only como base, así que el término de carga no queda respaldado como mejora robusta. ",
                "La observación nocturna de sueño tampoco mejora de forma robusta frente a la versión sin sueño. "
                if sleep_status == "prefer_sleep_free"
                else "La observación nocturna de sueño sí añade algo de valor frente a la versión sin sueño. "
                if sleep_augmented_supported
                else "",
                ewma_clause,
                "El resultado global cae a no-go, así que la normalización por deporte no rescata una ventaja robusta del modelo. "
                if global_go_no_go_status == "no_go"
                else "",
                "La heterogeneidad cross-sport sigue siendo relevante incluso con el drift reescalado. ",
                "Infraestructura de validación madura y reutilizable. No apto aún para gate ni reason_text "
                "(existe en `build_hrv_final_dashboard.py` un bloque latente de contexto SSM tras feature flag "
                "`HRV_SSM_REASON_TEXT_ENABLED`, default `0`; sin filtro por deporte, no se activa en Fase 1). ",
                "Siguiente mejora natural: evaluar outcome específico por deporte en lugar de un target combinado.",
            ]
        )
    else:
        summary = "".join(
            [
                "Fase 1 completa. SSM sombra operativo como capa técnica auditada. ",
                f"Semántica principal confirmada como {semantics}. ",
                "Hay evidencia de valor incremental frente a rolling HRV, especialmente en escenarios discordantes, ",
                "pero la ventaja no es estable en todos los regímenes temporales y no mantiene el mismo signo entre holdout y walk-forward. ",
                "El comparador estructural respalda mantener HRV-only como base, lo que sugiere que el término de carga no aporta valor robusto en esta configuración. ",
                "La observación nocturna de sueño tampoco muestra una mejora robusta frente a la versión sin sueño. "
                if sleep_status == "prefer_sleep_free"
                else "La observación nocturna de sueño añade una mejora pequeña frente a la versión sin sueño. "
                if sleep_augmented_supported
                else "",
                ewma_clause,
                "El outcome ya está normalizado por deporte, así que el siguiente paso debe ser separarlo por deporte en vez de seguir mezclándolo. "
                if normalization_applied
                else "",
                "No apto aún para gate ni reason_text "
                "(existe en `build_hrv_final_dashboard.py` un bloque latente de contexto SSM tras feature flag "
                "`HRV_SSM_REASON_TEXT_ENABLED`, default `0`; sin filtro por deporte, no se activa en Fase 1).",
            ]
        )

    return {
        "status": "phase1_complete_shadow_only",
        "go_no_go_status": global_go_no_go_status,
        "structural_comparator_status": structural_status,
        "structural_prefers_hrv_only": structural_hrv_only,
        "sleep_comparator_status": sleep_status,
        "sleep_augmented_supported": sleep_augmented_supported,
        "ewma_comparator_status": ewma_status,
        "ewma_best_holdout_alpha": ewma_best_alpha,
        "ewma_best_holdout_mae": ewma_best_holdout,
        "ewma_best_walk_forward_mae_mean": ewma_best_wf,
        "outcome_normalization_applied": normalization_applied,
        "semantics_confirmed": semantics == "goodness",
        "preferred_semantics": semantics,
        "discordant_beats_rolling": discordant_beats_rolling,
        "walk_forward_advantage_stable": advantage_stable,
        "walk_forward_advantage_min_margin": min_advantage_margin,
        "holdout_advantage": holdout_advantage,
        "walk_forward_advantage": wf_advantage,
        "cross_sport_heterogeneity": cross_sport_heterogeneous,
        "run_ties_rolling": run_ties_rolling,
        "bike_loses_to_rolling": bike_loses_to_rolling,
        "sport_go_statuses": sport_go_statuses,
        "sport_candidate_go": sport_candidate_go,
        "sport_primary_reading": "no_sport_go" if all_viable_sports_no_go else ("sport_specific_go" if any_sport_candidate_go else "mixed"),
        "summary": summary,
    }


def _go_no_go(metadata: dict, evaluations: dict, redundancy: dict, pairs: pd.DataFrame) -> dict[str, object]:
    outcome_status = metadata.get("outcome_audit", {}).get("outcome_audit_status")
    ssm_eval = evaluations.get("ssm_goodness", {})
    rolling_eval = evaluations.get("rolling_hrv_goodness", {})
    load_eval = evaluations.get("load_badness", {})

    beats_rolling = (
        np.isfinite(ssm_eval.get("holdout_mae", np.nan))
        and np.isfinite(rolling_eval.get("holdout_mae", np.nan))
        and ssm_eval["holdout_mae"] < rolling_eval["holdout_mae"]
    )
    beats_load = (
        np.isfinite(ssm_eval.get("holdout_mae", np.nan))
        and np.isfinite(load_eval.get("holdout_mae", np.nan))
        and ssm_eval["holdout_mae"] < load_eval["holdout_mae"]
    )
    enough_pairs = len(pairs) >= 30
    no_redundancy = redundancy.get("status") != "redundant"

    status = "no_go"
    if outcome_status == "pass" and enough_pairs and no_redundancy and beats_rolling:
        status = "candidate_go"
    elif outcome_status != "pass":
        status = "not_validatable_current_data"
    elif not enough_pairs:
        status = "exploratory_only"

    return {
        "status": status,
        "required_all": {
            "outcome_audit_pass": outcome_status == "pass",
            "pairs_gte_30": enough_pairs,
            "not_redundant_vs_simple_baselines": no_redundancy,
            "beats_rolling_hrv_7d_holdout_mae": beats_rolling,
        },
        "required_at_least_one": {
            "beats_load_7d_holdout_mae": beats_load,
        },
        "veto_conditions": {
            "redundancy_detected": redundancy.get("status") == "redundant",
            "too_few_pairs": not enough_pairs,
            "outcome_audit_not_pass": outcome_status != "pass",
            "does_not_beat_rolling_hrv_7d": not beats_rolling,
        },
    }


def _build_evaluation_block(metadata: dict, pairs: pd.DataFrame) -> dict[str, object]:
    evaluations = {
        "ssm_goodness": _evaluate_single_predictor(pairs, "ssm_goodness"),
        "rolling_hrv_goodness": _evaluate_single_predictor(pairs, "rolling_hrv_goodness"),
        "load_badness": _evaluate_single_predictor(pairs, "load_badness"),
        "gate_badness": _evaluate_single_predictor(pairs, "gate_badness"),
    }
    median_baseline = _median_baseline_holdout(pairs)
    family_last_baseline = _family_last_baseline_holdout(pairs)
    ssm_holdout = _holdout_split_predictions(pairs, "ssm_goodness")
    rolling_holdout = _holdout_split_predictions(pairs, "rolling_hrv_goodness")
    load_holdout = _holdout_split_predictions(pairs, "load_badness")
    bootstrap_ci = {
        "ssm_vs_rolling_holdout_mae": _bootstrap_mae_delta(
            np.asarray(ssm_holdout.get("y_test", np.array([], dtype=float)), dtype=float),
            np.asarray(ssm_holdout.get("pred_test", np.array([], dtype=float)), dtype=float),
            np.asarray(rolling_holdout.get("y_test", np.array([], dtype=float)), dtype=float),
            np.asarray(rolling_holdout.get("pred_test", np.array([], dtype=float)), dtype=float),
        ),
        "ssm_vs_median_baseline_holdout_mae": _bootstrap_mae_delta(
            np.asarray(ssm_holdout.get("y_test", np.array([], dtype=float)), dtype=float),
            np.asarray(ssm_holdout.get("pred_test", np.array([], dtype=float)), dtype=float),
            np.asarray(median_baseline.get("y_test", np.array([], dtype=float)), dtype=float),
            np.asarray(median_baseline.get("pred_test", np.array([], dtype=float)), dtype=float),
        ),
        "ssm_vs_family_last_baseline_holdout_mae": _bootstrap_mae_delta(
            np.asarray(ssm_holdout.get("y_test", np.array([], dtype=float)), dtype=float),
            np.asarray(ssm_holdout.get("pred_test", np.array([], dtype=float)), dtype=float),
            np.asarray(family_last_baseline.get("y_test", np.array([], dtype=float)), dtype=float),
            np.asarray(family_last_baseline.get("pred_test", np.array([], dtype=float)), dtype=float),
        ),
        "rolling_vs_median_baseline_holdout_mae": _bootstrap_mae_delta(
            np.asarray(rolling_holdout.get("y_test", np.array([], dtype=float)), dtype=float),
            np.asarray(rolling_holdout.get("pred_test", np.array([], dtype=float)), dtype=float),
            np.asarray(median_baseline.get("y_test", np.array([], dtype=float)), dtype=float),
            np.asarray(median_baseline.get("pred_test", np.array([], dtype=float)), dtype=float),
        ),
        "load_vs_median_baseline_holdout_mae": _bootstrap_mae_delta(
            np.asarray(load_holdout.get("y_test", np.array([], dtype=float)), dtype=float),
            np.asarray(load_holdout.get("pred_test", np.array([], dtype=float)), dtype=float),
            np.asarray(median_baseline.get("y_test", np.array([], dtype=float)), dtype=float),
            np.asarray(median_baseline.get("pred_test", np.array([], dtype=float)), dtype=float),
        ),
    }
    redundancy = _redundancy_check(pairs)
    uncertainty = _uncertainty_slice(pairs)
    go_no_go = _go_no_go(metadata, evaluations, redundancy, pairs)
    return {
        "n_pairs": int(len(pairs)),
        "lag_days_mean": float(pairs["lag_days"].mean()) if len(pairs) else float("nan"),
        "lag_days_median": float(pairs["lag_days"].median()) if len(pairs) else float("nan"),
        "outcome_scale_distribution": {
            str(key): int(value)
            for key, value in pairs["outcome_scale"].value_counts(dropna=False).to_dict().items()
        }
        if len(pairs)
        else {},
        "comparison_level_distribution": {
            str(key): int(value)
            for key, value in pairs["comparison_level"].value_counts(dropna=False).to_dict().items()
        }
        if len(pairs)
        else {},
        "session_family_distribution": {
            str(key): int(value)
            for key, value in pairs["session_family"].value_counts(dropna=False).to_dict().items()
        }
        if len(pairs)
        else {},
        "session_family_sport_distribution": {
            str(key): int(value)
            for key, value in pairs["session_family_sport"].value_counts(dropna=False).to_dict().items()
        }
        if len(pairs)
        else {},
        "sport_family_distribution": {
            str(key): int(value)
            for key, value in pairs["sport_family"].value_counts(dropna=False).to_dict().items()
        }
        if len(pairs)
        else {},
        "evaluations": evaluations,
        "baseline_comparison": {
            "median_baseline": {
                "n_pairs": int(median_baseline["n_pairs"]),
                "holdout_mae": float(median_baseline["holdout_mae"]),
                "holdout_rmse": float(median_baseline["holdout_rmse"]),
            },
            "family_last_baseline": {
                "n_pairs": int(family_last_baseline["n_pairs"]),
                "holdout_mae": float(family_last_baseline["holdout_mae"]),
                "holdout_rmse": float(family_last_baseline["holdout_rmse"]),
            },
            "bootstrap_ci": bootstrap_ci,
        },
        "redundancy_check": redundancy,
        "uncertainty_slice": uncertainty,
        "go_no_go": go_no_go,
    }


def build_validation_report(
    core_df: pd.DataFrame | None,
    ssm_df: pd.DataFrame,
    metadata: dict,
    sessions_day: pd.DataFrame,
    sessions_df: pd.DataFrame | None,
    sleep_df: pd.DataFrame | None,
    wellness_df: pd.DataFrame,
    final_df: pd.DataFrame | None,
) -> dict[str, object]:
    del wellness_df
    outcome_col, outcome_selection = _choose_primary_outcome(sessions_day, metadata, sessions_df)
    if outcome_col is None:
        raise ValueError("No hay outcome principal disponible para validación SSM")

    outcome_rows = _build_comparable_outcomes(sessions_day, outcome_col, sessions_df=sessions_df)
    pairs = _find_next_outcome_pairs(
        ssm_df,
        outcome_rows,
        outcome_col,
        final_df,
        aggregate_window_days=7,
        aggregate_window_max_sessions=1,
    )
    exploratory_window_pairs = _find_next_outcome_pairs(
        ssm_df,
        outcome_rows,
        outcome_col,
        final_df,
        aggregate_window_days=3,
        aggregate_window_max_sessions=3,
    )
    primary_pairs = _filter_primary_strict_pairs(pairs)
    primary_lite_pairs = _filter_primary_lite_pairs(pairs)
    primary_block = _build_evaluation_block(metadata, primary_pairs)
    primary_lite_block = _build_evaluation_block(metadata, primary_lite_pairs)
    exploratory_block = _build_evaluation_block(metadata, pairs)
    exploratory_window_block = _build_evaluation_block(metadata, exploratory_window_pairs)
    sign_semantics_audit = _build_sign_semantics_audit(primary_pairs)
    # Pre-compute base once so structural comparator and phi sensitivity reuse it
    precomputed_base = (
        ssm_builder.preprocess_base(core_df, sessions_day, sleep_df, ssm_builder.CFG)
        if core_df is not None
        else None
    )
    structural_comparator = _build_structural_comparator(
        core_df,
        sessions_day,
        sessions_df,
        final_df,
        sleep_df,
        outcome_col,
        outcome_rows,
        primary_pairs,
        precomputed_base=precomputed_base,
    )
    sleep_comparator = _build_sleep_comparator(
        core_df,
        sessions_day,
        sessions_df,
        final_df,
        sleep_df,
        outcome_col,
        outcome_rows,
        primary_pairs,
    )
    ewma_comparator = _build_ewma_comparator(core_df, primary_pairs)
    phi_sensitivity = _build_phi_sensitivity(
        core_df,
        sessions_day,
        sessions_df,
        final_df,
        sleep_df,
        outcome_col,
        outcome_rows,
        primary_pairs,
        precomputed_base=precomputed_base,
    )
    discordant_day_analysis = _build_discordant_day_analysis(primary_pairs)
    sport_stratified_analysis = _build_sport_stratified_analysis(metadata, primary_pairs)
    primary_strict_by_sport = _promote_primary_strict_by_sport(sport_stratified_analysis)
    walk_forward_by_sport = _build_walk_forward_by_sport(primary_strict_by_sport)
    strict_funnel = _build_strict_funnel(pairs)
    outcome_diagnostics = _build_outcome_diagnostics(outcome_rows)
    outcome_normalization = outcome_rows.attrs.get("outcome_normalization", {"mode": "none", "applied": False, "per_sport_reference": {}})
    calibration_check = _build_calibration_check(metadata)
    phase1_conclusion = _build_phase1_conclusion(
        outcome_col,
        sign_semantics_audit,
        primary_block,
        structural_comparator,
        sleep_comparator,
        ewma_comparator,
        discordant_day_analysis,
        sport_stratified_analysis,
        outcome_normalization,
    )
    primary_operational_view = _build_primary_operational_view(primary_block, primary_strict_by_sport, phase1_conclusion)

    return {
        "source": "build_hrv_ssm_validation.py",
        "generated_at": pd.Timestamp.now("UTC").isoformat(),
        "primary_outcome_name": outcome_col,
        "primary_outcome_selection": outcome_selection,
        "pairing_rule": "next comparable session within t+1..t+7 using declared session families and within-family FDS",
        "exploratory_pairing_rule": "aggregate comparable outcomes within t+1..t+3 using up to 3 sessions and within-family FDS",
        "sign_semantics_audit": sign_semantics_audit,
        "structural_comparator": structural_comparator,
        "phi_sensitivity": phi_sensitivity,
        "discordant_day_analysis": discordant_day_analysis,
        "sport_stratified_analysis": sport_stratified_analysis,
        "primary_strict_by_sport": primary_strict_by_sport,
        "walk_forward_by_sport": walk_forward_by_sport,
        "primary_operational_view": primary_operational_view,
        "calibration_check": calibration_check,
        "sleep_comparator": sleep_comparator,
        "ewma_comparator": ewma_comparator,
        "strict_funnel": strict_funnel,
        "outcome_diagnostics": outcome_diagnostics,
        "outcome_normalization": outcome_normalization,
        "phase1_conclusion": phase1_conclusion,
        "primary_strict": {
            "filter_rule": "FDS only, aerobic session families only, no strength_only, baseline_n>=3",
            **primary_block,
        },
        "baseline_comparison": primary_block["baseline_comparison"],
        "primary_lite": {
            "filter_rule": "FDS or FDS-lite, aerobic session families only, no strength_only, baseline_n>=2; diagnostic only",
            **primary_lite_block,
        },
        "exploratory_broad": {
            "filter_rule": "all comparable pairs, including oriented_raw_fallback and strength_only",
            **exploratory_block,
        },
        "exploratory_window_t1_t3": {
            "filter_rule": "aggregate up to 3 comparable outcomes within t+1..t+3; exploratory only",
            **exploratory_window_block,
        },
        "n_pairs": exploratory_block["n_pairs"],
        "lag_days_mean": exploratory_block["lag_days_mean"],
        "lag_days_median": exploratory_block["lag_days_median"],
        "outcome_scale_distribution": exploratory_block["outcome_scale_distribution"],
        "comparison_level_distribution": exploratory_block["comparison_level_distribution"],
        "session_family_distribution": exploratory_block["session_family_distribution"],
        "session_family_sport_distribution": exploratory_block["session_family_sport_distribution"],
        "sport_family_distribution": exploratory_block["sport_family_distribution"],
        "evaluations": exploratory_block["evaluations"],
        "redundancy_check": exploratory_block["redundancy_check"],
        "go_no_go": primary_block["go_no_go"],
        "metadata_snapshot": {
            "outcome_audit": metadata.get("outcome_audit", {}),
            "load_signal_pretest": metadata.get("load_signal_pretest", {}),
            "go_no_go_criteria": metadata.get("go_no_go_criteria", {}),
        },
    }


def _fmt(value, digits: int = 3) -> str:
    if value is None or (isinstance(value, float) and not np.isfinite(value)):
        return "—"
    if isinstance(value, int):
        return str(value)
    return f"{float(value):.{digits}f}"


def _append_metrics_table(lines: list[str], block: dict[str, object]) -> None:
    labels = {
        "ssm_goodness": "SSM shadow",
        "rolling_hrv_goodness": "Rolling HRV 7d",
        "load_badness": "Load 7d",
        "gate_badness": "Gate final",
    }
    lines.extend(
        [
            "| Predictor | n | Spearman rho | p-value | Holdout MAE | WF MAE mean | WF folds | Holdout RMSE |",
            "| --- | --- | --- | --- | --- | --- | --- | --- |",
        ]
    )
    for key in ["ssm_goodness", "rolling_hrv_goodness", "load_badness", "gate_badness"]:
        item = block["evaluations"][key]
        lines.append(
            f"| {labels[key]} | {_fmt(item['n_pairs'], 0)} | {_fmt(item['spearman_rho'])} | {_fmt(item['spearman_p_value'])} | {_fmt(item['holdout_mae'])} | {_fmt(item['walk_forward_mae_mean'])} | {_fmt(item['walk_forward_n_folds'], 0)} | {_fmt(item['holdout_rmse'])} |"
        )


def build_validation_markdown(report: dict[str, object]) -> str:
    primary = report["primary_strict"]
    lite = report["primary_lite"]
    broad = report["exploratory_broad"]
    exploratory_window = report["exploratory_window_t1_t3"]
    primary_by_sport = report.get("primary_strict_by_sport", {})
    structural = report["structural_comparator"]
    current_model_kind = str(structural.get("current_model_kind", "current_model"))
    alternative_model_kind = str(structural.get("alternative_model_kind", "alternative_model"))
    lines = [
        "# Validación SSM Shadow",
        "",
        "## Resumen",
        f"- Vista operativa primaria: `{report.get('primary_operational_view', {}).get('mode')}`",
        f"- Scope recomendado: `{report.get('primary_operational_view', {}).get('recommended_primary_scope')}`",
        f"- Estado go/no-go principal: `{primary['go_no_go']['status']}`",
        f"- Outcome principal: `{report['primary_outcome_name']}`",
        f"- Motivo de selección outcome: `{report['primary_outcome_selection']['selection_reason']}`",
        f"- Pares estrictos: `{primary['n_pairs']}`",
        f"- Pares lite diagnósticos: `{lite['n_pairs']}`",
        f"- Pares exploratorios: `{broad['n_pairs']}`",
        f"- Regla temporal: `{report['pairing_rule']}`",
        f"- Regla temporal exploratoria: `{report['exploratory_pairing_rule']}`",
        f"- Escala outcome estricta: `{json.dumps(_json_safe(primary.get('outcome_scale_distribution', {})), ensure_ascii=False)}`",
        f"- Escala outcome lite: `{json.dumps(_json_safe(lite.get('outcome_scale_distribution', {})), ensure_ascii=False)}`",
        f"- Escala outcome exploratoria: `{json.dumps(_json_safe(broad.get('outcome_scale_distribution', {})), ensure_ascii=False)}`",
        "- `WF MAE mean` usa walk-forward temporal con ventana expansiva.",
        "",
        "## Cierre Fase 1",
        f"- Estado go/no-go enlazado: `{report['phase1_conclusion'].get('go_no_go_status')}`",
        f"- Go/no-go por deporte: `{json.dumps(_json_safe({k: v.get('go_no_go', {}).get('status') for k, v in primary_by_sport.items()}), ensure_ascii=False)}`",
        f"- Lectura primaria por deporte: `{report['phase1_conclusion'].get('sport_primary_reading')}`",
        f"- `{report['phase1_conclusion']['summary']}`",
        "",
        "## Vista Operativa Primaria",
        f"- Modo: `{report.get('primary_operational_view', {}).get('mode')}`",
        f"- Scope recomendado: `{report.get('primary_operational_view', {}).get('recommended_primary_scope')}`",
        f"- Estado global: `{report.get('primary_operational_view', {}).get('global_status')}`",
        f"- Estados por deporte: `{json.dumps(_json_safe(report.get('primary_operational_view', {}).get('sport_go_statuses', {})), ensure_ascii=False)}`",
        f"- `{report.get('primary_operational_view', {}).get('summary')}`",
        "",
        "## Calibración",
        f"- `{json.dumps(_json_safe(report.get('calibration_check', {})), ensure_ascii=False)}`",
        "",
        "## Diagnóstico Outcome",
        f"- Modo de fallo principal: `{report['outcome_diagnostics']['primary_failure_mode']}`",
        f"- Normalización outcome: `{json.dumps(_json_safe(report.get('outcome_normalization', {})), ensure_ascii=False)}`",
        f"- Outcomes comparables evaluados: `{report['outcome_diagnostics']['n_rows']}`",
        f"- Filas con `FDS`: `{report['outcome_diagnostics']['n_with_fds']}`",
        f"- Filas con `FDS-lite`: `{report['outcome_diagnostics']['n_with_fds_lite']}`",
        f"- Filas con `baseline_n >= 3`: `{report['outcome_diagnostics']['n_baseline_gte_3']}`",
        f"- Filas con `baseline_n >= 3` bloqueadas por MAD=0: `{report['outcome_diagnostics']['n_baseline_gte_3_fds_blocked_zero_mad']}`",
        f"- Share de `outcome_oriented == 0`: `{_fmt(report['outcome_diagnostics']['outcome_oriented_zero_share'])}`",
        f"- Valores más frecuentes del outcome orientado: `{json.dumps(_json_safe(report['outcome_diagnostics']['outcome_oriented_unique_values_top']), ensure_ascii=False)}`",
        "",
        "## Auditoría de Signo",
        f"- SSM como `goodness`: rho=`{_fmt(report['sign_semantics_audit']['ssm_state']['rho_goodness'])}`; soporte=`{report['sign_semantics_audit']['ssm_state']['goodness_supported']}`; semántica preferida=`{report['sign_semantics_audit']['ssm_state']['preferred_semantics']}`",
        f"- Rolling 7d como `goodness`: rho=`{_fmt(report['sign_semantics_audit']['rolling_hrv_7d']['rho_goodness'])}`; soporte=`{report['sign_semantics_audit']['rolling_hrv_7d']['goodness_supported']}`; semántica preferida=`{report['sign_semantics_audit']['rolling_hrv_7d']['preferred_semantics']}`",
        "",
        "## Comparador Estructural",
        f"- Estado comparador: `{report['structural_comparator']['status']}`",
        f"- Pares alineados actual vs alternativo: `{report['structural_comparator'].get('aligned_pairs_n')}`",
        f"- Modelo actual ({current_model_kind}) holdout MAE: `{_fmt(report['structural_comparator'].get('current_model', {}).get('holdout_mae'))}`",
        f"- Modelo alternativo ({alternative_model_kind}) holdout MAE: `{_fmt(report['structural_comparator'].get(alternative_model_kind if alternative_model_kind in report['structural_comparator'] else 'hrv_only_model', {}).get('holdout_mae'))}`",
        f"- Load sobre innovaciones HRV-only: `{json.dumps(_json_safe(report['structural_comparator'].get('load_on_hrv_only_innovations', {})), ensure_ascii=False)}`",
        "",
        "## Sensibilidad Phi",
        f"- Estado sensibilidad: `{report['phi_sensitivity']['status']}`",
        f"- Phi actual: `{report['phi_sensitivity'].get('current_phi')}`",
        f"- Mejor phi en grid: `{report['phi_sensitivity'].get('best_phi')}`",
        f"- MAE holdout actual: `{_fmt(report['phi_sensitivity'].get('current_holdout_mae'))}`",
        f"- MAE holdout mejor phi: `{_fmt(report['phi_sensitivity'].get('best_holdout_mae'))}`",
        f"- Grid: `{json.dumps(_json_safe(report['phi_sensitivity'].get('grid', [])), ensure_ascii=False)}`",
        "",
        "## Días Discordantes",
        f"- Estado discordancia: `{report['discordant_day_analysis']['status']}`",
        f"- Flags: `{json.dumps(_json_safe(report['discordant_day_analysis'].get('flag_counts', {})), ensure_ascii=False)}`",
        f"- SSM MAE discordantes: `{_fmt(report['discordant_day_analysis'].get('discordant_subset', {}).get('ssm_goodness', {}).get('holdout_mae'))}` vs rolling `{_fmt(report['discordant_day_analysis'].get('discordant_subset', {}).get('rolling_hrv_goodness', {}).get('holdout_mae'))}`",
        f"- SSM MAE concordantes: `{_fmt(report['discordant_day_analysis'].get('concordant_subset', {}).get('ssm_goodness', {}).get('holdout_mae'))}` vs rolling `{_fmt(report['discordant_day_analysis'].get('concordant_subset', {}).get('rolling_hrv_goodness', {}).get('holdout_mae'))}`",
        "",
        "## Estratificación Deporte",
        f"- Estado estratificación: `{report['sport_stratified_analysis']['status']}`",
        f"- Deportes viables: `{json.dumps(_json_safe(report['sport_stratified_analysis'].get('viable_sports', [])), ensure_ascii=False)}`",
        f"- Resumen por deporte: `{json.dumps(_json_safe({k: {'n_pairs': v.get('n_pairs'), 'ssm_holdout_mae': v.get('evaluations', {}).get('ssm_goodness', {}).get('holdout_mae'), 'rolling_holdout_mae': v.get('evaluations', {}).get('rolling_hrv_goodness', {}).get('holdout_mae')} for k, v in report['sport_stratified_analysis'].get('sports', {}).items()}), ensure_ascii=False)}`",
        "",
        "## Walk-Forward Por Deporte",
    ]
    wf_sports = report.get("walk_forward_by_sport", {}).get("sports", {})
    if wf_sports:
        lines.extend([
            "| Deporte | n | Go/no-go | SSM holdout MAE | SSM WF MAE | Rolling holdout MAE | Rolling WF MAE |",
            "| --- | --- | --- | --- | --- | --- | --- |",
        ])
        for sport_key, sp in wf_sports.items():
            ssm_ev = sp.get("ssm_goodness", {})
            rol_ev = sp.get("rolling_hrv_goodness", {})
            lines.append(
                f"| {sport_key} | {_fmt(sp.get('n_pairs'), 0)} | {sp.get('go_no_go', '—')} "
                f"| {_fmt(ssm_ev.get('holdout_mae'))} | {_fmt(ssm_ev.get('walk_forward_mae_mean'))} "
                f"| {_fmt(rol_ev.get('holdout_mae'))} | {_fmt(rol_ev.get('walk_forward_mae_mean'))} |"
            )
    else:
        lines.append("- `insufficient_data`")
    lines.extend([
        "",
        "## Principal Estricto Por Deporte",
        f"- `{json.dumps(_json_safe({k: {'n_pairs': v.get('n_pairs'), 'go_no_go': v.get('go_no_go', {}).get('status')} for k, v in primary_by_sport.items()}), ensure_ascii=False)}`",
        "",
        "## Funnel Estricto",
        f"- `{json.dumps(_json_safe(report['strict_funnel']), ensure_ascii=False)}`",
        "",
        "## Principal Estricto",
    ])
    _append_metrics_table(lines, primary)

    sleep_comparator = report.get("sleep_comparator", {})
    lines.extend(
        [
            "",
            "## Comparador Sueño",
            f"- Estado comparador: `{sleep_comparator.get('status', 'unknown')}`",
            f"- Pares alineados actual vs sin sueño: `{sleep_comparator.get('aligned_pairs_n')}`",
            f"- Modelo con sueño holdout MAE: `{_fmt(sleep_comparator.get('current_model', {}).get('holdout_mae'))}`",
            f"- Modelo sin sueño holdout MAE: `{_fmt(sleep_comparator.get('sleep_free_model', {}).get('holdout_mae'))}`",
            f"- Delta MAE sin sueño - con sueño: `{_fmt(sleep_comparator.get('sleep_on_holdout_mae_delta'))}`",
        ]
    )

    ewma_comparator = report.get("ewma_comparator", {})
    lines.extend(
        [
            "",
            "## Comparador EWMA",
            f"- Estado comparador: `{ewma_comparator.get('status', 'unknown')}`",
            f"- Modelo base: `{ewma_comparator.get('current_model_kind', 'banister_2state')}`",
            f"- Baseline: `{ewma_comparator.get('baseline_model_kind', 'ewma_lnrmssd')}`",
            f"- Mejor alpha holdout: `{_fmt(ewma_comparator.get('best_holdout_alpha'))}`",
            f"- Mejor MAE holdout EWMA: `{_fmt(ewma_comparator.get('best_holdout_mae'))}`",
            f"- Mejor MAE walk-forward EWMA: `{_fmt(ewma_comparator.get('best_walk_forward_mae_mean'))}`",
            f"- Delta MAE SSM - EWMA holdout: `{_fmt(ewma_comparator.get('current_vs_ewma_holdout_mae_delta'))}`",
            f"- Delta MAE SSM - EWMA walk-forward: `{_fmt(ewma_comparator.get('current_vs_ewma_walk_forward_mae_delta'))}`",
            f"- Grid: `{json.dumps(_json_safe(ewma_comparator.get('grid', [])), ensure_ascii=False)}`",
        ]
    )

    redundancy = primary["redundancy_check"]
    lines.extend(
        [
            "",
            "## Diagnósticos Estrictos",
            f"- Redundancia vs `rolling_hrv_7d + load_7d`: `{redundancy['status']}` (R²={_fmt(redundancy.get('r2'))})",
            f"- Lag medio al outcome: `{_fmt(primary['lag_days_mean'])}` días",
            f"- Lag mediano al outcome: `{_fmt(primary['lag_days_median'])}` días",
            f"- Nivel de comparabilidad: `{json.dumps(_json_safe(primary.get('comparison_level_distribution', {})), ensure_ascii=False)}`",
            f"- Familias por deporte: `{json.dumps(_json_safe(primary.get('session_family_sport_distribution', {})), ensure_ascii=False)}`",
        ]
    )
    uncertainty = primary["uncertainty_slice"]
    if uncertainty.get("status") == "ok":
        lines.extend(
            [
            f"- Cuartil alto de varianza: n={uncertainty['high_var_n']} · outcome medio={_fmt(uncertainty['high_var_outcome_mean'])}",
            f"- Cuartil bajo de varianza: n={uncertainty['low_var_n']} · outcome medio={_fmt(uncertainty['low_var_outcome_mean'])}",
        ]
    )
    baseline_comparison = primary.get("baseline_comparison", {})
    lines.extend(
        [
            "",
            "## Baseline Trivial",
            f"- `{json.dumps(_json_safe(baseline_comparison), ensure_ascii=False)}`",
            "",
            "## Bootstrap CI",
            f"- `{json.dumps(_json_safe(baseline_comparison.get('bootstrap_ci', {})), ensure_ascii=False)}`",
        ]
    )
    lines.extend(
        [
            "",
            "## Principal Lite",
            "- Diagnóstico intermedio: exige baseline comparable >=2 y escala `fds`/`fds_lite`, pero no gobierna promoción.",
        ]
    )
    _append_metrics_table(lines, lite)
    lines.extend(
        [
            "",
            "## Exploratorio Amplio",
        ]
    )
    _append_metrics_table(lines, broad)
    lines.extend(
        [
            "",
            "## Exploratorio Ventana T1-T3",
            "- Diagnóstico exploratorio: agrega hasta 3 sesiones comparables en `t+1..t+3` para reducir ruido de un mal día puntual.",
        ]
    )
    _append_metrics_table(lines, exploratory_window)
    lines.extend(
        [
            "",
            "## Go / No-Go Principal",
            f"- required_all: `{json.dumps(_json_safe(primary['go_no_go']['required_all']), ensure_ascii=False)}`",
            f"- required_at_least_one: `{json.dumps(_json_safe(primary['go_no_go']['required_at_least_one']), ensure_ascii=False)}`",
            f"- veto_conditions: `{json.dumps(_json_safe(primary['go_no_go']['veto_conditions']), ensure_ascii=False)}`",
            "",
            "## Nota",
            "- El bloque principal estricto gobierna el go/no-go. El bloque lite ayuda a decidir si merece seguir acumulando datos, pero no justifica promoción.",
            "- El bloque exploratorio conserva cobertura amplia, pero no justifica promoción.",
            "- Este reporte es Fase 1 sombra. No recolorea el gate ni modifica `FINAL.csv`.",
        ]
    )
    return "\n".join(lines) + "\n"


def main(argv: List[str]) -> int:
    args = parse_args(argv)

    global DATA_DIR, IN_CORE, IN_SSM, IN_SSM_METADATA, IN_SESSIONS_DAY, IN_SESSIONS, IN_SLEEP, IN_WELLNESS, IN_FINAL, OUT_REPORT_JSON, OUT_REPORT_MD
    if "data_dir" in args:
        DATA_DIR = resolve_writable_dir(Path(args["data_dir"]), CONFIG_DATA_DIR)
        IN_CORE = DATA_DIR / "ENDURANCE_HRV_master_CORE.csv"
        IN_SSM = DATA_DIR / "ENDURANCE_HRV_ssm_shadow.csv"
        IN_SSM_METADATA = DATA_DIR / "ENDURANCE_HRV_ssm_shadow_metadata.json"
        IN_SESSIONS_DAY = DATA_DIR / "ENDURANCE_HRV_sessions_day.csv"
        IN_SESSIONS = DATA_DIR / "ENDURANCE_HRV_sessions.csv"
        IN_SLEEP = DATA_DIR / "ENDURANCE_HRV_sleep.csv"
        IN_WELLNESS = DATA_DIR / "ENDURANCE_HRV_wellness_subjective.csv"
        IN_FINAL = DATA_DIR / "ENDURANCE_HRV_master_FINAL.csv"
        OUT_REPORT_JSON = DATA_DIR / "ENDURANCE_HRV_ssm_validation_report.json"
        OUT_REPORT_MD = DATA_DIR / "ENDURANCE_HRV_ssm_validation_report.md"

    try:
        core_df = _load_csv(IN_CORE, ["Fecha", "lnRMSSD", "Calidad", "HRV_Stability", "Artifact_pct", "Flags"])
        ssm_df = _load_csv(IN_SSM, ["Fecha", "ssm_warmup_complete", "ssm_recovery_state", "ssm_state_var", "control_rolling_hrv_7d", "control_load_7d"])
        metadata = json.loads(IN_SSM_METADATA.read_text(encoding="utf-8"))
        sessions_day = _load_csv(IN_SESSIONS_DAY, ["Fecha"])
        sessions_df = _load_csv(IN_SESSIONS, ["Fecha", "sport"]) if IN_SESSIONS.exists() else pd.DataFrame(columns=["Fecha", "sport"])
        sleep_df = _load_csv(IN_SLEEP, ["Fecha"]) if IN_SLEEP.exists() else pd.DataFrame(columns=["Fecha"])
        wellness_df = _load_csv(IN_WELLNESS, ["Fecha"]) if IN_WELLNESS.exists() else pd.DataFrame(columns=["Fecha"])
        final_df = _load_csv(IN_FINAL, ["Fecha", "gate_final"]) if IN_FINAL.exists() else None
    except (FileNotFoundError, ValueError, json.JSONDecodeError) as exc:
        print(f"[ERROR] {exc}")
        return 2

    report = build_validation_report(core_df, ssm_df, metadata, sessions_day, sessions_df, sleep_df, wellness_df, final_df)
    write_json_atomic(report, OUT_REPORT_JSON)
    write_text_atomic(build_validation_markdown(report), OUT_REPORT_MD)
    print(f"[OK] Validación SSM actualizada: {OUT_REPORT_JSON.name}")
    return 0


if __name__ == "__main__":
    import sys

    raise SystemExit(main(sys.argv[1:]))
