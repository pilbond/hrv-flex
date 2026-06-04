# -*- coding: utf-8 -*-
"""
ENDURANCE HRV — SSM sombra Fase 1
=================================

Genera una capa sombra reproducible de estado latente HRV+carga. No toca
FINAL ni el gate operativo.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import asdict, dataclass
from datetime import timedelta
from pathlib import Path
from typing import Dict, List, Tuple

import numpy as np
import pandas as pd
from scipy import stats

from hrv_app.config import DATA_DIR as CONFIG_DATA_DIR
from hrv_app.config import resolve_writable_dir
from hrv_app.io_utils import write_csv_atomic, write_json_atomic


DATA_DIR = CONFIG_DATA_DIR
IN_CORE = DATA_DIR / "ENDURANCE_HRV_master_CORE.csv"
IN_SESSIONS_DAY = DATA_DIR / "ENDURANCE_HRV_sessions_day.csv"
IN_SLEEP = DATA_DIR / "ENDURANCE_HRV_sleep.csv"
IN_WELLNESS = DATA_DIR / "ENDURANCE_HRV_wellness_subjective.csv"
OUT_SSM_SHADOW = DATA_DIR / "ENDURANCE_HRV_ssm_shadow.csv"
OUT_SSM_METADATA = DATA_DIR / "ENDURANCE_HRV_ssm_shadow_metadata.json"

SLEEP_OBS_COLUMNS = [
    "Fecha",
    "polar_sleep_duration_min",
    "polar_sleep_span_min",
    "polar_efficiency_pct",
    "polar_continuity_index",
    "polar_interruptions_long",
    "polar_interruptions_total",
    "polar_sleep_score",
    "polar_night_rmssd",
    "sleep_dur_p10",
    "sleep_dur_p90",
    "sleep_int_p90",
]

SIDE_CAR_COLUMNS = [
    "Fecha",
    "ssm_input_ready",
    "ssm_warmup_complete",
    "ssm_recovery_state",
    "ssm_baseline_state",
    "ssm_fatigue_state",
    "sleep_recovery_index",
    "sleep_recovery_index_var",
    "sleep_recovery_index_sd",
    "sleep_obs_missing",
    "sleep_input_quality",
    "sleep_obs_var_multiplier",
    "sleep_innovation",
    "ssm_state_lo",
    "ssm_state_hi",
    "ssm_state_var",
    "ssm_state_sd",
    "ssm_baseline_state_var",
    "ssm_fatigue_state_var",
    "ssm_baseline_state_sd",
    "ssm_fatigue_state_sd",
    "ssm_obs_missing",
    "ssm_load_missing",
    "ssm_load_context_mode",
    "ssm_proc_var_multiplier",
    "ssm_input_quality",
    "ssm_obs_var_multiplier",
    "ssm_innovation",
    "control_rolling_hrv_7d",
    "control_load_7d",
]

Z_90 = 1.6448536269514722


@dataclass(frozen=True)
class SSMConfig:
    phi_slow: float = 0.985
    phi_fast: float = 0.85
    # El comparador estructural (Fase 1) muestra prefer_banister_hrv_only con delta MAE ~0.001.
    # Se mantienen no-zero para preservar la arquitectura ARX; la diferencia es dentro del ruido.
    beta_slow: float = 0.00008
    beta_fast: float = 0.00072
    sigma_obs_fallback: float = 0.12
    sigma_proc_slow: float = 0.025
    sigma_proc_fast: float = 0.06
    warmup_candidate_window_days: int = 90
    warmup_required_obs: int = 30
    warmup_obs_var_multiplier_threshold: float = 1.25
    slow_baseline_window_days: int = 60
    quality_artifact_threshold_pct: float = 5.0


CFG = SSMConfig()


def parse_args(argv: List[str]) -> Dict[str, str]:
    parsed: Dict[str, str] = {}
    for idx, token in enumerate(argv):
        if token == "--data-dir" and idx + 1 < len(argv):
            parsed["data_dir"] = argv[idx + 1]
    return parsed


def _read_csv_required(path: Path, required_columns: List[str]) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"No existe: {path}")
    df = pd.read_csv(path)
    missing = [col for col in required_columns if col not in df.columns]
    if missing:
        raise ValueError(f"{path.name} no contiene columnas requeridas: {missing}")
    if df.empty:
        raise ValueError(f"{path.name} está vacío")
    return df


def _normalize_date_column(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["Fecha"] = pd.to_datetime(out["Fecha"], errors="coerce")
    out = out[out["Fecha"].notna()].copy()
    out["Fecha"] = out["Fecha"].dt.normalize()
    return out.sort_values("Fecha").drop_duplicates(subset=["Fecha"], keep="last").reset_index(drop=True)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def _safe_float_series(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce").astype(float)


def _split_flags(raw_value: object) -> set[str]:
    if raw_value is None or (isinstance(raw_value, float) and np.isnan(raw_value)):
        return set()
    parts = [part.strip() for part in str(raw_value).split("|")]
    return {part for part in parts if part}


def _prepare_daily_frame(core_df: pd.DataFrame, sessions_day_df: pd.DataFrame, sleep_df: pd.DataFrame | None = None) -> pd.DataFrame:
    core = _normalize_date_column(core_df)
    sday = _normalize_date_column(sessions_day_df)
    sleep = _normalize_date_column(sleep_df) if sleep_df is not None and not sleep_df.empty else pd.DataFrame(columns=SLEEP_OBS_COLUMNS)

    start = min(core["Fecha"].min(), sday["Fecha"].min())
    end = max(core["Fecha"].max(), sday["Fecha"].max())
    if not sleep.empty and "Fecha" in sleep.columns and sleep["Fecha"].notna().any():
        start = min(start, sleep["Fecha"].min())
        end = max(end, sleep["Fecha"].max())
    calendar = pd.DataFrame({"Fecha": pd.date_range(start, end, freq="D")})

    base = calendar.merge(core, on="Fecha", how="left")
    sday_cols = ["Fecha", "load_day", "load_7d"]
    sday_merge = sday[[col for col in sday_cols if col in sday.columns]].copy()
    if "load_day" not in sday_merge.columns:
        sday_merge["load_day"] = np.nan
    if "load_7d" not in sday_merge.columns:
        sday_merge["load_7d"] = np.nan
    sday_merge["load_day_raw"] = sday_merge["load_day"]
    sday_merge["load_row_present"] = True
    base = base.merge(sday_merge, on="Fecha", how="left")

    sleep_cols = ["Fecha"] + [col for col in SLEEP_OBS_COLUMNS if col != "Fecha"]
    sleep_merge = sleep[[col for col in sleep_cols if col in sleep.columns]].copy() if not sleep.empty else pd.DataFrame(columns=sleep_cols)
    if "sleep_row_present" not in sleep_merge.columns:
        sleep_merge["sleep_row_present"] = True
    return base.merge(sleep_merge, on="Fecha", how="left")


def _derive_obs_quality(base: pd.DataFrame, cfg: SSMConfig) -> pd.DataFrame:
    out = base.copy()
    lnrmssd = _safe_float_series(out["lnRMSSD"]) if "lnRMSSD" in out.columns else pd.Series(np.nan, index=out.index)
    artifact = _safe_float_series(out["Artifact_pct"]) if "Artifact_pct" in out.columns else pd.Series(0.0, index=out.index)
    quality = out["Calidad"].fillna("").astype(str)
    stability = out["HRV_Stability"].fillna("").astype(str)
    flags = out["Flags"].apply(_split_flags) if "Flags" in out.columns else pd.Series([set()] * len(out))

    obs_missing = lnrmssd.isna() | quality.eq("INVALID") | flags.apply(lambda parts: "LAT_NAN" in parts)
    penalty = np.zeros(len(out), dtype=float)
    penalty += np.where(quality.eq("FLAG_mecánico"), 1.5, 0.0)
    penalty += np.where(~stability.eq("OK") & stability.ne(""), 1.0, 0.0)
    artifact_excess = np.maximum(artifact.to_numpy(dtype=float) - cfg.quality_artifact_threshold_pct, 0.0)
    artifact_penalty = np.where(
        artifact_excess > 0.0,
        np.minimum(2.0, np.log1p(artifact_excess / 5.0)),
        0.0,
    )
    penalty += artifact_penalty

    obs_var_multiplier = 1.0 + penalty
    quality_mode = np.where(
        obs_missing,
        "suppressed",
        np.where(obs_var_multiplier <= 1.25, "clean", "degraded"),
    )

    out["lnRMSSD"] = lnrmssd
    out["Artifact_pct"] = artifact
    out["ssm_obs_missing"] = obs_missing.astype(bool)
    out["ssm_obs_var_multiplier"] = obs_var_multiplier.astype(float)
    out["ssm_input_quality"] = quality_mode.astype(object)
    return out


def _derive_load_context(base: pd.DataFrame) -> pd.DataFrame:
    out = base.copy()
    load_raw = _safe_float_series(out["load_day_raw"]) if "load_day_raw" in out.columns else pd.Series(np.nan, index=out.index)
    row_present = out["load_row_present"].fillna(False).astype(bool)

    no_session = ~row_present
    missing_value = row_present & load_raw.isna()
    load_missing = missing_value.astype(bool)

    streak = np.zeros(len(out), dtype=int)
    current = 0
    for idx, is_gap in enumerate(no_session.to_numpy(dtype=bool)):
        current = current + 1 if is_gap else 0
        streak[idx] = current

    mode = np.full(len(out), "session_recorded", dtype=object)
    mode[no_session.to_numpy(dtype=bool)] = "rest_day_no_session"
    mode[(no_session & (pd.Series(streak, index=out.index) >= 3)).to_numpy(dtype=bool)] = "calendar_gap_no_session"
    mode[missing_value.to_numpy(dtype=bool)] = "missing_session_value"

    proc_multiplier = np.ones(len(out), dtype=float)
    proc_multiplier = np.where(mode == "rest_day_no_session", 1.15, proc_multiplier)
    proc_multiplier = np.where(mode == "calendar_gap_no_session", 1.35, proc_multiplier)
    proc_multiplier = np.where(mode == "missing_session_value", 1.75, proc_multiplier)

    out["load_day"] = load_raw.fillna(0.0).astype(float)
    out["ssm_load_missing"] = load_missing
    out["ssm_load_context_mode"] = mode
    out["ssm_proc_var_multiplier"] = proc_multiplier.astype(float)
    return out


def _derive_sleep_context(base: pd.DataFrame, cfg: SSMConfig) -> Tuple[pd.DataFrame, Dict[str, object]]:
    out = base.copy()
    if "sleep_row_present" not in out.columns:
        out["sleep_row_present"] = False

    sleep_row_present = out["sleep_row_present"].fillna(False).astype(bool)
    night_rmssd = _safe_float_series(out["polar_night_rmssd"]) if "polar_night_rmssd" in out.columns else pd.Series(np.nan, index=out.index)
    sleep_score = _safe_float_series(out["polar_sleep_score"]) if "polar_sleep_score" in out.columns else pd.Series(np.nan, index=out.index)
    sleep_duration = _safe_float_series(out["polar_sleep_duration_min"]) if "polar_sleep_duration_min" in out.columns else pd.Series(np.nan, index=out.index)
    sleep_efficiency = _safe_float_series(out["polar_efficiency_pct"]) if "polar_efficiency_pct" in out.columns else pd.Series(np.nan, index=out.index)
    sleep_continuity = _safe_float_series(out["polar_continuity_index"]) if "polar_continuity_index" in out.columns else pd.Series(np.nan, index=out.index)
    sleep_interruptions = _safe_float_series(out["polar_interruptions_long"]) if "polar_interruptions_long" in out.columns else pd.Series(np.nan, index=out.index)
    sleep_dur_p10 = _safe_float_series(out["sleep_dur_p10"]) if "sleep_dur_p10" in out.columns else pd.Series(np.nan, index=out.index)
    sleep_int_p90 = _safe_float_series(out["sleep_int_p90"]) if "sleep_int_p90" in out.columns else pd.Series(np.nan, index=out.index)
    lnrmssd = _safe_float_series(out["lnRMSSD"]) if "lnRMSSD" in out.columns else pd.Series(np.nan, index=out.index)

    def _fit_crosswalk(feature: pd.Series, min_points: int = 20) -> Dict[str, float | int | str]:
        mask = sleep_row_present & feature.notna() & lnrmssd.notna()
        x = feature[mask].to_numpy(dtype=float)
        y = lnrmssd[mask].to_numpy(dtype=float)
        if len(x) < min_points:
            return {"available": False, "n": int(len(x))}
        A = np.column_stack([np.ones(len(x)), x])
        coef, *_ = np.linalg.lstsq(A, y, rcond=None)
        pred = A @ coef
        resid = y - pred
        rmse = float(np.sqrt(np.mean(resid ** 2))) if len(resid) else float("nan")
        resid_sd = float(np.std(resid, ddof=1)) if len(resid) >= 2 else float("nan")
        if not np.isfinite(resid_sd) or resid_sd <= 0:
            resid_sd = cfg.sigma_obs_fallback
        return {
            "available": True,
            "n": int(len(x)),
            "intercept": float(coef[0]),
            "slope": float(coef[1]),
            "rmse": rmse,
            "resid_sd": resid_sd,
        }

    night_fit = _fit_crosswalk(night_rmssd)
    score_fit = _fit_crosswalk(sleep_score)

    night_pred = pd.Series(np.nan, index=out.index, dtype=float)
    night_sigma = pd.Series(np.nan, index=out.index, dtype=float)
    night_available = night_fit.get("available", False)
    if night_available:
        night_pred = night_fit["intercept"] + night_fit["slope"] * night_rmssd
        night_sigma = pd.Series(float(night_fit["resid_sd"]), index=out.index, dtype=float)

    score_pred = pd.Series(np.nan, index=out.index, dtype=float)
    score_sigma = pd.Series(np.nan, index=out.index, dtype=float)
    score_available = score_fit.get("available", False)
    if score_available:
        score_pred = score_fit["intercept"] + score_fit["slope"] * sleep_score
        score_sigma = pd.Series(float(score_fit["resid_sd"]), index=out.index, dtype=float)

    combined_index = np.full(len(out), np.nan, dtype=float)
    combined_sigma = np.full(len(out), np.nan, dtype=float)
    source = np.full(len(out), "unavailable", dtype=object)
    for idx in range(len(out)):
        candidates: list[tuple[str, float, float]] = []
        if np.isfinite(night_pred.iat[idx]):
            candidates.append(("nightly_rmssd", float(night_pred.iat[idx]), float(night_sigma.iat[idx])))
        if np.isfinite(score_pred.iat[idx]):
            candidates.append(("sleep_score", float(score_pred.iat[idx]), float(score_sigma.iat[idx])))
        if not candidates:
            continue
        if len(candidates) == 1:
            src, pred_val, sigma_val = candidates[0]
            combined_index[idx] = pred_val
            combined_sigma[idx] = sigma_val
            source[idx] = src
            continue
        weights = []
        preds = []
        for _, pred_val, sigma_val in candidates:
            sigma_val = float(sigma_val) if np.isfinite(sigma_val) and sigma_val > 0 else float(cfg.sigma_obs_fallback)
            weights.append(1.0 / max(sigma_val ** 2, 1e-9))
            preds.append(pred_val)
        weight_sum = float(np.sum(weights))
        if weight_sum > 0:
            combined_index[idx] = float(np.sum(np.array(weights) * np.array(preds)) / weight_sum)
            combined_sigma[idx] = math.sqrt(1.0 / weight_sum)
            source[idx] = "nightly_rmssd+sleep_score"

    has_observation = np.isfinite(combined_index)
    sleep_penalty = np.zeros(len(out), dtype=float)
    if "polar_sleep_score" in out.columns:
        sleep_penalty += np.where(sleep_score.notna() & (sleep_score <= 65.0), 0.35, 0.0)
        sleep_penalty += np.where(sleep_score.notna() & sleep_score.gt(65.0) & sleep_score.lt(75.0), 0.15, 0.0)
    if "polar_sleep_duration_min" in out.columns:
        sleep_penalty += np.where(sleep_duration.notna() & sleep_duration.lt(420.0), 0.15, 0.0)
    if "polar_efficiency_pct" in out.columns:
        sleep_penalty += np.where(sleep_efficiency.notna() & sleep_efficiency.lt(90.0), 0.10, 0.0)
    if "polar_continuity_index" in out.columns:
        sleep_penalty += np.where(sleep_continuity.notna() & sleep_continuity.gt(3.5), 0.10, 0.0)
    if "polar_interruptions_long" in out.columns and "sleep_int_p90" in out.columns:
        sleep_penalty += np.where(
            sleep_interruptions.notna()
            & sleep_int_p90.notna()
            & (sleep_interruptions > sleep_int_p90),
            0.20,
            0.0,
        )
    if "polar_sleep_duration_min" in out.columns and "sleep_dur_p10" in out.columns:
        sleep_penalty += np.where(
            sleep_duration.notna()
            & sleep_dur_p10.notna()
            & (sleep_duration < sleep_dur_p10),
            0.10,
            0.0,
        )

    obs_var_multiplier = 1.0 + sleep_penalty
    quality_mode = np.where(
        ~has_observation,
        "suppressed",
        np.where(obs_var_multiplier <= 1.25, "clean", "degraded"),
    )

    out["sleep_recovery_index"] = combined_index.astype(float)
    out["sleep_recovery_index_sd"] = combined_sigma.astype(float)
    out["sleep_recovery_index_var"] = np.square(combined_sigma).astype(float)
    out["sleep_obs_missing"] = (~has_observation).astype(bool)
    out["sleep_input_quality"] = quality_mode.astype(object)
    out["sleep_obs_var_multiplier"] = obs_var_multiplier.astype(float)

    diagnostics = {
        "sleep_recovery_index_source": "nightly_rmssd_crosswalk" if night_available else "sleep_score_crosswalk" if score_available else "unavailable",
        "sleep_nightly_rmssd_fit": night_fit,
        "sleep_score_fit": score_fit,
        "sleep_observation_coverage_n": int(has_observation.sum()),
        "sleep_observation_coverage_pct": float(has_observation.mean()) if len(out) else float("nan"),
    }
    return out, diagnostics


def _rolling_mean(series: pd.Series, window: int) -> pd.Series:
    return series.rolling(window=window, min_periods=1).mean()


def _rolling_median(series: pd.Series, window: int) -> pd.Series:
    return series.rolling(window=window, min_periods=max(3, min(window, 7))).median()


def _initial_state_from_warmup(base: pd.DataFrame, cfg: SSMConfig) -> Tuple[int | None, float, float, float, pd.Series]:
    first_date = base["Fecha"].min()
    warmup_end = first_date + timedelta(days=cfg.warmup_candidate_window_days - 1)
    candidate_mask = base["Fecha"].between(first_date, warmup_end)
    usable_mask = (
        candidate_mask
        & (~base["ssm_obs_missing"].astype(bool))
        & (base["ssm_obs_var_multiplier"].astype(float) <= cfg.warmup_obs_var_multiplier_threshold)
        & base["lnRMSSD"].notna()
    )
    usable_idx = base.index[usable_mask].tolist()

    rolling7 = _rolling_mean(base["lnRMSSD"], 7)
    sigma_obs = float(np.nanstd((base["lnRMSSD"] - rolling7)[usable_mask].to_numpy(dtype=float), ddof=1))
    if not np.isfinite(sigma_obs) or sigma_obs <= 0:
        sigma_obs = cfg.sigma_obs_fallback

    warmup_complete_idx = usable_idx[cfg.warmup_required_obs - 1] if len(usable_idx) >= cfg.warmup_required_obs else None
    init_state = float(np.nanmedian(base.loc[usable_mask, "lnRMSSD"].to_numpy(dtype=float)))
    if not np.isfinite(init_state):
        init_state = float(np.nanmedian(base["lnRMSSD"].to_numpy(dtype=float)))
    if not np.isfinite(init_state):
        init_state = 0.0

    slow30 = _rolling_median(base["lnRMSSD"], 30)
    residuals = (base["lnRMSSD"] - slow30)[usable_mask]
    p0 = float(np.nanvar(residuals.to_numpy(dtype=float), ddof=1))
    if not np.isfinite(p0) or p0 <= 0:
        warmup_values = base.loc[usable_mask, "lnRMSSD"].to_numpy(dtype=float)
        median = float(np.nanmedian(warmup_values)) if warmup_values.size else init_state
        mad = float(np.nanmedian(np.abs(warmup_values - median))) if warmup_values.size else cfg.sigma_obs_fallback
        robust_sd = 1.4826 * mad if np.isfinite(mad) and mad > 0 else cfg.sigma_obs_fallback
        p0 = float(robust_sd ** 2)

    return warmup_complete_idx, init_state, p0, sigma_obs, candidate_mask


def _kalman_shadow(base: pd.DataFrame, cfg: SSMConfig) -> Tuple[pd.DataFrame, Dict[str, object]]:
    out = base.copy()
    warmup_complete_idx, init_state, p0, sigma_obs, candidate_mask = _initial_state_from_warmup(out, cfg)
    anchor_mu = float(init_state)

    load_prev = out["load_day"].shift(1).fillna(0.0).astype(float).to_numpy(dtype=float)
    lnrmssd = out["lnRMSSD"].to_numpy(dtype=float)
    obs_missing = out["ssm_obs_missing"].astype(bool).to_numpy(dtype=bool)
    obs_mult = out["ssm_obs_var_multiplier"].astype(float).to_numpy(dtype=float)
    proc_mult = out["ssm_proc_var_multiplier"].astype(float).to_numpy(dtype=float)
    sleep_missing = out["sleep_obs_missing"].astype(bool).to_numpy(dtype=bool) if "sleep_obs_missing" in out.columns else np.ones(len(out), dtype=bool)
    sleep_obs = out["sleep_recovery_index"].to_numpy(dtype=float) if "sleep_recovery_index" in out.columns else np.full(len(out), np.nan, dtype=float)
    sleep_obs_mult = out["sleep_obs_var_multiplier"].astype(float).to_numpy(dtype=float) if "sleep_obs_var_multiplier" in out.columns else np.ones(len(out), dtype=float)
    sleep_obs_var = out["sleep_recovery_index_var"].astype(float).to_numpy(dtype=float) if "sleep_recovery_index_var" in out.columns else np.full(len(out), np.nan, dtype=float)

    x_prev = np.array([0.0, 0.0], dtype=float)
    p_prev = np.array([[p0, 0.0], [0.0, max(p0 * 0.75, 1e-6)]], dtype=float)
    state = np.full(len(out), np.nan, dtype=float)
    baseline_state = np.full(len(out), np.nan, dtype=float)
    fatigue_state = np.full(len(out), np.nan, dtype=float)
    state_var = np.full(len(out), np.nan, dtype=float)
    baseline_state_var = np.full(len(out), np.nan, dtype=float)
    fatigue_state_var = np.full(len(out), np.nan, dtype=float)
    state_lo = np.full(len(out), np.nan, dtype=float)
    state_hi = np.full(len(out), np.nan, dtype=float)
    sleep_innovation_series = np.full(len(out), np.nan, dtype=float)
    innovation_series = np.full(len(out), np.nan, dtype=float)

    h = np.array([1.0, -1.0], dtype=float)
    a = np.array([cfg.phi_slow, cfg.phi_fast], dtype=float)
    q = np.diag([cfg.sigma_proc_slow ** 2, cfg.sigma_proc_fast ** 2]).astype(float)
    sigma_obs_sq = sigma_obs ** 2

    for idx in range(len(out)):
        x_pred = np.array(
            [
                (cfg.phi_slow * x_prev[0]) + (cfg.beta_slow * load_prev[idx]),
                (cfg.phi_fast * x_prev[1]) + (cfg.beta_fast * load_prev[idx]),
            ],
            dtype=float,
        )
        p_pred = np.diag(a) @ p_prev @ np.diag(a) + (q * proc_mult[idx])
        y_pred = anchor_mu + x_pred[0] - x_pred[1]

        if not sleep_missing[idx] and np.isfinite(sleep_obs[idx]):
            sleep_innovation = sleep_obs[idx] - y_pred
            sleep_innovation_series[idx] = sleep_innovation
            r_sleep = sleep_obs_var[idx] if np.isfinite(sleep_obs_var[idx]) and sleep_obs_var[idx] > 0 else (sigma_obs_sq * max(sleep_obs_mult[idx], 1.0))
            r_sleep = max(float(r_sleep), 1e-9)
            s_sleep = float(h @ p_pred @ h.T + r_sleep)
            k_sleep = (p_pred @ h) / s_sleep if s_sleep > 0 else np.zeros(2, dtype=float)
            x_pred = x_pred + (k_sleep * sleep_innovation)
            p_pred = (np.eye(2) - np.outer(k_sleep, h)) @ p_pred
            p_pred = np.asarray((p_pred + p_pred.T) / 2.0, dtype=float)
            p_pred = np.where(np.isfinite(p_pred), p_pred, 0.0)
            p_pred = p_pred + np.eye(2) * 1e-9
            y_pred = anchor_mu + x_pred[0] - x_pred[1]

        if obs_missing[idx] or not np.isfinite(lnrmssd[idx]):
            x_post = x_pred
            p_post = p_pred
        else:
            r_t = sigma_obs_sq * max(obs_mult[idx], 1.0)
            innovation = lnrmssd[idx] - y_pred
            innovation_series[idx] = innovation
            s_t = float(h @ p_pred @ h.T + r_t)
            k_t = (p_pred @ h) / s_t if s_t > 0 else np.zeros(2, dtype=float)
            x_post = x_pred + (k_t * innovation)
            p_post = (np.eye(2) - np.outer(k_t, h)) @ p_pred
            p_post = np.asarray((p_post + p_post.T) / 2.0, dtype=float)
            p_post = np.where(np.isfinite(p_post), p_post, 0.0)
            p_post = p_post + np.eye(2) * 1e-9

        if warmup_complete_idx is not None and idx >= warmup_complete_idx:
            baseline_state[idx] = anchor_mu + x_post[0]
            fatigue_state[idx] = x_post[1]
            state[idx] = baseline_state[idx] - fatigue_state[idx]
            state_var[idx] = float(p_post[0, 0] + p_post[1, 1] - (2.0 * p_post[0, 1]))
            baseline_state_var[idx] = float(p_post[0, 0])
            fatigue_state_var[idx] = float(p_post[1, 1])
            state_sd = math.sqrt(max(state_var[idx], 0.0))
            state_lo[idx] = state[idx] - (Z_90 * state_sd)
            state_hi[idx] = state[idx] + (Z_90 * state_sd)

        x_prev = x_post
        p_prev = p_post

    out["ssm_input_ready"] = True
    out["ssm_warmup_complete"] = False if warmup_complete_idx is None else (out.index >= warmup_complete_idx)
    out["ssm_recovery_state"] = state
    out["ssm_baseline_state"] = baseline_state
    out["ssm_fatigue_state"] = fatigue_state
    out["ssm_state_var"] = state_var
    out["ssm_state_sd"] = np.sqrt(np.clip(state_var, a_min=0.0, a_max=None))
    out["ssm_baseline_state_var"] = baseline_state_var
    out["ssm_fatigue_state_var"] = fatigue_state_var
    out["ssm_baseline_state_sd"] = np.sqrt(np.clip(baseline_state_var, a_min=0.0, a_max=None))
    out["ssm_fatigue_state_sd"] = np.sqrt(np.clip(fatigue_state_var, a_min=0.0, a_max=None))
    out["sleep_innovation"] = sleep_innovation_series
    out["ssm_innovation"] = innovation_series
    out["control_rolling_hrv_7d"] = _rolling_mean(out["lnRMSSD"], 7)
    out["control_load_7d"] = _safe_float_series(out["load_7d"]) if "load_7d" in out.columns else out["load_day"].rolling(window=7, min_periods=1).sum()

    slow_baseline = _rolling_median(out["lnRMSSD"], cfg.slow_baseline_window_days)
    detrended = out["lnRMSSD"] - slow_baseline
    valid_corr = out["ssm_recovery_state"].notna() & slow_baseline.notna()
    slow_corr = float(out.loc[valid_corr, "ssm_recovery_state"].corr(slow_baseline[valid_corr])) if valid_corr.any() else float("nan")
    innovation_valid = pd.Series(innovation_series).dropna()
    innovation_mean = float(innovation_valid.mean()) if not innovation_valid.empty else float("nan")
    innovation_sd = float(innovation_valid.std(ddof=1)) if len(innovation_valid) >= 2 else float("nan")
    innovation_abs_p90 = float(np.nanpercentile(np.abs(innovation_valid.to_numpy(dtype=float)), 90)) if not innovation_valid.empty else float("nan")
    # --- Interval scaling: calibrate on first 70%, evaluate on last 30% ---
    warmup_valid_idx = out.index[
        out["ssm_warmup_complete"].astype(bool) & out["lnRMSSD"].notna() & out["ssm_state_sd"].notna()
    ].tolist()
    interval_scale_factor = 1.0
    interval_scale_source = "fallback_unit"
    calib_n = 0
    holdout_n = 0
    if len(warmup_valid_idx) >= 10:
        calib_n = max(int(len(warmup_valid_idx) * 0.70), 8)
        holdout_n = len(warmup_valid_idx) - calib_n
        calib_mask = pd.Series(False, index=out.index)
        calib_mask[warmup_valid_idx[:calib_n]] = True
        std_resid = np.abs(
            (out.loc[calib_mask, "lnRMSSD"] - out.loc[calib_mask, "ssm_recovery_state"])
            / np.clip(out.loc[calib_mask, "ssm_state_sd"], a_min=1e-9, a_max=None)
        )
        std_resid = std_resid[np.isfinite(std_resid)]
        if len(std_resid):
            q90 = float(np.nanpercentile(std_resid.to_numpy(dtype=float), 90))
            if np.isfinite(q90) and q90 > 0:
                interval_scale_factor = max(1.0, q90 / Z_90)
                interval_scale_source = "calib_70pct_abs_standardized_residual_q90"

    if len(out):
        state_sd_full = out["ssm_state_sd"].to_numpy(dtype=float)
        state_lo = out["ssm_recovery_state"].to_numpy(dtype=float) - (Z_90 * state_sd_full * interval_scale_factor)
        state_hi = out["ssm_recovery_state"].to_numpy(dtype=float) + (Z_90 * state_sd_full * interval_scale_factor)
        state_lo = np.where(np.isfinite(state_lo), state_lo, np.nan)
        state_hi = np.where(np.isfinite(state_hi), state_hi, np.nan)
        out["ssm_state_lo"] = state_lo
        out["ssm_state_hi"] = state_hi

    # Coverage evaluated on holdout only; fall back to all warmup-complete when holdout < 8
    if holdout_n >= 8:
        coverage_idx = warmup_valid_idx[calib_n:]
        coverage_source = "holdout_30pct"
    else:
        coverage_idx = warmup_valid_idx
        coverage_source = "all_warmup_complete_fallback"
    coverage_mask = pd.Series(False, index=out.index)
    if coverage_idx:
        coverage_mask[coverage_idx] = True
    coverage_mask = coverage_mask & out["lnRMSSD"].notna() & out["ssm_state_lo"].notna() & out["ssm_state_hi"].notna()
    if coverage_mask.any():
        inside = (
            (out.loc[coverage_mask, "lnRMSSD"] >= out.loc[coverage_mask, "ssm_state_lo"])
            & (out.loc[coverage_mask, "lnRMSSD"] <= out.loc[coverage_mask, "ssm_state_hi"])
        )
        interval_coverage_90pct = float(inside.mean())
        interval_coverage_n = int(len(inside))
        binom = stats.binomtest(int(inside.sum()), n=interval_coverage_n, p=0.90, alternative="two-sided")
        ci = binom.proportion_ci(confidence_level=0.95, method="exact")
        interval_coverage_ci95 = [float(ci.low), float(ci.high)]
    else:
        interval_coverage_90pct = float("nan")
        interval_coverage_n = 0
        interval_coverage_ci95 = [float("nan"), float("nan")]
        coverage_source = "no_data"
    interval_calibration_delta = float(interval_coverage_90pct - 0.90) if np.isfinite(interval_coverage_90pct) else float("nan")
    interval_calibration_status = (
        "well_calibrated"
        if np.isfinite(interval_coverage_90pct) and abs(interval_calibration_delta) <= 0.05
        else "undercovered"
        if np.isfinite(interval_coverage_90pct) and interval_coverage_90pct < 0.85
        else "overcovered"
        if np.isfinite(interval_coverage_90pct) and interval_coverage_90pct > 0.95
        else "uncertain"
    )

    diagnostics = {
        "warmup_candidate_window_days": cfg.warmup_candidate_window_days,
        "warmup_required_obs": cfg.warmup_required_obs,
        "warmup_obs_var_multiplier_threshold": cfg.warmup_obs_var_multiplier_threshold,
        "warmup_observations_usable": int(
            (
                candidate_mask
                & (~out["ssm_obs_missing"].astype(bool))
                & (out["ssm_obs_var_multiplier"].astype(float) <= cfg.warmup_obs_var_multiplier_threshold)
                & out["lnRMSSD"].notna()
            ).sum()
        ),
        "warmup_complete": bool(warmup_complete_idx is not None),
        "warmup_complete_date": None if warmup_complete_idx is None else str(out.loc[warmup_complete_idx, "Fecha"].date()),
        "p0_method": "rolling_median_30d_residual_or_mad_fallback",
        "state_anchor_mu": anchor_mu,
        "state_model": "banister_2state_baseline_minus_fatigue",
        "phi_slow": cfg.phi_slow,
        "phi_fast": cfg.phi_fast,
        "beta_slow": cfg.beta_slow,
        "beta_fast": cfg.beta_fast,
        "sigma_proc_slow": cfg.sigma_proc_slow,
        "sigma_proc_fast": cfg.sigma_proc_fast,
        "sigma_obs_base": sigma_obs,
        "sleep_observation_coverage_n": int((~sleep_missing & np.isfinite(sleep_obs)).sum()),
        "sleep_observation_coverage_pct": float((~sleep_missing & np.isfinite(sleep_obs)).mean()) if len(out) else float("nan"),
        "slow_baseline_window_days": cfg.slow_baseline_window_days,
        "slow_baseline_coverage": float(slow_baseline.notna().mean()) if len(slow_baseline) else 0.0,
        "slow_baseline_state_corr": slow_corr,
        "lnrmssd_detrended_mean": float(np.nanmean(detrended.to_numpy(dtype=float))) if detrended.notna().any() else float("nan"),
        "innovation_mean": innovation_mean,
        "innovation_sd": innovation_sd,
        "innovation_abs_p90": innovation_abs_p90,
        "interval_scale_factor": interval_scale_factor,
        "interval_scale_source": interval_scale_source,
        "interval_calib_n": calib_n,
        "interval_holdout_n": holdout_n,
        "interval_coverage_source": coverage_source,
        "interval_coverage_n": interval_coverage_n,
        "interval_coverage_90pct": interval_coverage_90pct,
        "interval_coverage_ci95": interval_coverage_ci95,
        "interval_calibration_delta": interval_calibration_delta,
        "interval_calibration_status": interval_calibration_status,
    }
    return out, diagnostics


def _ols_with_pvalue(y: np.ndarray, x_cols: List[np.ndarray]) -> Dict[str, float]:
    x = np.column_stack([np.ones(len(y), dtype=float), *x_cols])
    beta, _, _, _ = np.linalg.lstsq(x, y, rcond=None)
    resid = y - (x @ beta)
    dof = max(len(y) - x.shape[1], 1)
    sigma2 = float(np.sum(resid ** 2) / dof)
    xtx_inv = np.linalg.pinv(x.T @ x)
    se = np.sqrt(np.clip(np.diag(xtx_inv) * sigma2, a_min=0.0, a_max=None))
    target_idx = x.shape[1] - 1
    t_stat = float(beta[target_idx] / se[target_idx]) if se[target_idx] > 0 else float("nan")
    p_value = float(2 * stats.t.sf(abs(t_stat), df=dof)) if np.isfinite(t_stat) else float("nan")
    ss_tot = float(np.sum((y - np.mean(y)) ** 2))
    r2 = float(1.0 - (np.sum(resid ** 2) / ss_tot)) if ss_tot > 0 else float("nan")
    return {
        "coef": float(beta[target_idx]),
        "se": float(se[target_idx]) if target_idx < len(se) else float("nan"),
        "p_value": p_value,
        "r2": r2,
    }


def _temporal_fold_signs(df: pd.DataFrame) -> List[float]:
    out: List[float] = []
    if len(df) < 45:
        return out
    fold_size = max(len(df) // 3, 15)
    for fold_end in range(fold_size, len(df) + 1, fold_size):
        fold = df.iloc[:fold_end].copy()
        y = fold["y"].to_numpy(dtype=float)
        result = _ols_with_pvalue(
            y,
            [
                fold["lag1"].to_numpy(dtype=float),
                fold["lag3"].to_numpy(dtype=float),
                fold["lag7"].to_numpy(dtype=float),
                fold["load_prev"].to_numpy(dtype=float),
            ],
        )
        out.append(result["coef"])
    return out


def _load_signal_pretest(base: pd.DataFrame) -> Dict[str, object]:
    df = pd.DataFrame(
        {
            "y": base["lnRMSSD"],
            "lag1": base["lnRMSSD"].shift(1),
            "lag3": base["lnRMSSD"].shift(3),
            "lag7": base["lnRMSSD"].shift(7),
            "load_prev": base["load_day"].shift(1),
        }
    ).dropna()
    if len(df) < 20:
        return {
            "n_rows": int(len(df)),
            "coef": float("nan"),
            "se": float("nan"),
            "p_value": float("nan"),
            "r2_full": float("nan"),
            "r2_reduced": float("nan"),
            "holdout_mse_improvement": float("nan"),
            "sign_stability": [],
            "load_signal_status": "insufficient_data",
        }

    y = df["y"].to_numpy(dtype=float)
    full = _ols_with_pvalue(
        y,
        [
            df["lag1"].to_numpy(dtype=float),
            df["lag3"].to_numpy(dtype=float),
            df["lag7"].to_numpy(dtype=float),
            df["load_prev"].to_numpy(dtype=float),
        ],
    )
    reduced_x = np.column_stack(
        [
            np.ones(len(df), dtype=float),
            df["lag1"].to_numpy(dtype=float),
            df["lag3"].to_numpy(dtype=float),
            df["lag7"].to_numpy(dtype=float),
        ]
    )
    reduced_beta, _, _, _ = np.linalg.lstsq(reduced_x, y, rcond=None)
    reduced_pred = reduced_x @ reduced_beta
    ss_tot = float(np.sum((y - np.mean(y)) ** 2))
    reduced_r2 = float(1.0 - (np.sum((y - reduced_pred) ** 2) / ss_tot)) if ss_tot > 0 else float("nan")

    split = max(int(len(df) * 0.8), 16)
    train = df.iloc[:split].copy()
    test = df.iloc[split:].copy()
    mse_improvement = float("nan")
    if len(test) >= 4 and len(train) >= 16:
        train_y = train["y"].to_numpy(dtype=float)
        x_full_train = np.column_stack(
            [
                np.ones(len(train), dtype=float),
                train["lag1"].to_numpy(dtype=float),
                train["lag3"].to_numpy(dtype=float),
                train["lag7"].to_numpy(dtype=float),
                train["load_prev"].to_numpy(dtype=float),
            ]
        )
        x_red_train = x_full_train[:, :-1]
        beta_full, _, _, _ = np.linalg.lstsq(x_full_train, train_y, rcond=None)
        beta_red, _, _, _ = np.linalg.lstsq(x_red_train, train_y, rcond=None)
        x_full_test = np.column_stack(
            [
                np.ones(len(test), dtype=float),
                test["lag1"].to_numpy(dtype=float),
                test["lag3"].to_numpy(dtype=float),
                test["lag7"].to_numpy(dtype=float),
                test["load_prev"].to_numpy(dtype=float),
            ]
        )
        x_red_test = x_full_test[:, :-1]
        test_y = test["y"].to_numpy(dtype=float)
        mse_full = float(np.mean((test_y - (x_full_test @ beta_full)) ** 2))
        mse_red = float(np.mean((test_y - (x_red_test @ beta_red)) ** 2))
        if mse_red > 0:
            mse_improvement = float((mse_red - mse_full) / mse_red)

    signs = _temporal_fold_signs(df)
    stable_negative = bool(signs) and all(value < 0 for value in signs if np.isfinite(value))
    status = "exploratory"
    if np.isfinite(full["coef"]) and full["coef"] < 0 and stable_negative and np.isfinite(mse_improvement) and mse_improvement > 0:
        status = "candidate"

    return {
        "n_rows": int(len(df)),
        "coef": full["coef"],
        "se": full["se"],
        "p_value": full["p_value"],
        "r2_full": full["r2"],
        "r2_reduced": reduced_r2,
        "holdout_mse_improvement": mse_improvement,
        "sign_stability": signs,
        "load_signal_status": status,
    }


def _audit_outcomes(sessions_day_df: pd.DataFrame, wellness_df: pd.DataFrame) -> Dict[str, object]:
    sessions_day = _normalize_date_column(sessions_day_df)
    wellness = _normalize_date_column(wellness_df) if not wellness_df.empty and "Fecha" in wellness_df.columns else pd.DataFrame(columns=["Fecha"])

    candidates = [
        "cardiac_drift_worst",
        "effort_above_anchor_aerobic",
        "effort_above_typical_aerobic",
        "rpe_max_day",
    ]
    candidate_counts = {
        col: int(_safe_float_series(sessions_day[col]).notna().sum())
        for col in candidates
        if col in sessions_day.columns
    }
    primary_name = max(candidate_counts, key=candidate_counts.get) if candidate_counts else None
    primary_available = bool(primary_name and candidate_counts.get(primary_name, 0) >= 12)

    wellness_numeric_cols = [col for col in wellness.columns if col.endswith("_raw") and col != "well_comment_raw"]
    wellness_counts = {col: int(_safe_float_series(wellness[col]).notna().sum()) for col in wellness_numeric_cols}
    secondary_name = max(wellness_counts, key=wellness_counts.get) if wellness_counts else None
    secondary_available = bool(secondary_name and wellness_counts.get(secondary_name, 0) >= 12)

    folds = {}
    if primary_name and "Fecha" in sessions_day.columns and len(sessions_day) >= 12:
        sessions_day = sessions_day.sort_values("Fecha").reset_index(drop=True)
        fold_size = max(len(sessions_day) // 3, 1)
        for fold_idx in range(3):
            chunk = sessions_day.iloc[fold_idx * fold_size : (fold_idx + 1) * fold_size if fold_idx < 2 else len(sessions_day)]
            if not chunk.empty:
                folds[f"fold_{fold_idx + 1}"] = float(_safe_float_series(chunk[primary_name]).notna().mean())

    return {
        "primary_outcome_available": primary_available,
        "secondary_outcome_available": secondary_available,
        "primary_outcome_name": primary_name,
        "primary_outcome_lag_rule": "next comparable session within t+1..t+7",
        "secondary_outcome_name": secondary_name,
        "secondary_outcome_lag_rule": "same-date structured self-report; temporal semantics still require confirmation",
        "outcome_coverage_by_fold": folds,
        "outcome_temporal_semantics_status": "sessions_day_plausible_wellness_unverified",
        "outcome_audit_status": "pass" if primary_available else "no_validatable_current_data",
    }


def _build_metadata(
    shadow_df: pd.DataFrame,
    core_path: Path,
    sessions_day_path: Path,
    sleep_path: Path | None,
    cfg: SSMConfig,
    kalman_diag: Dict[str, object],
    load_signal: Dict[str, object],
    outcome_audit: Dict[str, object],
) -> Dict[str, object]:
    flags = shadow_df["Flags"].apply(_split_flags) if "Flags" in shadow_df.columns else pd.Series([set()] * len(shadow_df))
    beta_frozen_count = int(flags.apply(lambda parts: "BETA_FROZEN" in parts).sum())
    quality_counts = {
        "flag_mecanico": int(shadow_df["Calidad"].fillna("").eq("FLAG_mecánico").sum()) if "Calidad" in shadow_df.columns else 0,
        "stability_not_ok": int(shadow_df["HRV_Stability"].fillna("").ne("OK").sum()) if "HRV_Stability" in shadow_df.columns else 0,
        "beta_frozen": beta_frozen_count,
        "artifact_gt_5pct": int((_safe_float_series(shadow_df["Artifact_pct"]) > 5).sum()) if "Artifact_pct" in shadow_df.columns else 0,
    }
    load_mode_dist = {str(key): int(value) for key, value in shadow_df["ssm_load_context_mode"].value_counts(dropna=False).to_dict().items()}
    proc_var_dist = {str(key): int(value) for key, value in shadow_df["ssm_proc_var_multiplier"].round(3).value_counts(dropna=False).to_dict().items()}

    return {
        "source": "build_hrv_ssm.py",
        "generated_at": pd.Timestamp.now("UTC").isoformat(),
        "parameters": asdict(cfg),
        "parameter_origin": {
            "phi_slow": "default_fixed",
            "phi_fast": "default_fixed",
            "beta_slow": "default_fixed",
            "beta_fast": "default_fixed",
            "sigma_proc_slow": "default_fixed",
            "sigma_proc_fast": "default_fixed",
            "sigma_obs_base": "warmup_or_fallback",
        },
        "processed_date_range": {
            "start": str(shadow_df["Fecha"].iloc[0]) if not shadow_df.empty else None,
            "end": str(shadow_df["Fecha"].iloc[-1]) if not shadow_df.empty else None,
            "n_days": int(len(shadow_df)),
        },
        "core_input": {
            "path": str(core_path),
            "size_bytes": core_path.stat().st_size,
            "sha256": _sha256_file(core_path),
        },
        "sessions_day_input": {
            "path": str(sessions_day_path),
            "size_bytes": sessions_day_path.stat().st_size,
            "sha256": _sha256_file(sessions_day_path),
        },
        "sleep_input": (
            {
                "path": str(sleep_path),
                "size_bytes": sleep_path.stat().st_size,
                "sha256": _sha256_file(sleep_path),
            }
            if sleep_path is not None and sleep_path.exists()
            else {
                "path": None if sleep_path is None else str(sleep_path),
                "available": False,
            }
        ),
        "days_valid": int(shadow_df["ssm_recovery_state"].notna().sum()),
        "days_suppressed_by_quality": int(shadow_df["ssm_obs_missing"].astype(bool).sum()),
        "days_with_load_missing": int(shadow_df["ssm_load_missing"].astype(bool).sum()),
        "load_context_distribution": load_mode_dist,
        "proc_var_multiplier_distribution": proc_var_dist,
        "warmup_mean_obs_var_multiplier": float(shadow_df["ssm_obs_var_multiplier"].mean()) if len(shadow_df) else float("nan"),
        "beta_frozen_count": beta_frozen_count,
        "beta_frozen_pct": float(beta_frozen_count / len(shadow_df)) if len(shadow_df) else 0.0,
        "quality_penalty_counts": quality_counts,
        "kalman_diagnostics": kalman_diag,
        "load_signal_pretest": load_signal,
        "outcome_audit": outcome_audit,
        "daily_user_summary": _build_daily_user_summary(shadow_df),
        "go_no_go_criteria": {
            "incremental_value_fail": "shadow state does not beat rolling HRV or load_7d baselines",
            "degeneracy_test_fail": "simple EWMA-style baselines reproduce the state within tolerance",
            "calibration_fail": "predictive interval coverage for lnRMSSD is not yet audited in this build",
        },
    }


_QUALITY_TEXT: Dict[str, str] = {
    "clean": "La observación de hoy fue limpia y el modelo le da un peso normal.",
    "degraded": "La observación de hoy fue usable pero no completamente limpia, así que el modelo la suaviza y le da algo menos de peso.",
    "suppressed": "La observación de hoy quedó suprimida y el modelo se apoya más en la tendencia previa que en la medición del día.",
}
_SLEEP_QUALITY_TEXT: Dict[str, str] = {
    "clean": "La observación nocturna de sueño fue limpia y ayuda como refuerzo de la lectura.",
    "degraded": "La observación nocturna de sueño fue usable pero algo más frágil, así que entra como apoyo con menos peso.",
    "suppressed": "La observación nocturna de sueño no es utilizable hoy, así que el modelo no la usa como medida directa.",
}
_LOAD_TEXT: Dict[str, str] = {
    "session_recorded": "La carga reciente venía de una sesión registrada normal.",
    "rest_day_no_session": "El contexto reciente parece de descanso sin sesión registrada.",
    "calendar_gap_no_session": "Hay un pequeño hueco de calendario sin sesiones registradas, así que el modelo asume más incertidumbre de proceso.",
    "missing_session_value": "Había fila de sesión pero con carga no utilizable, así que el modelo añade prudencia.",
}
_CONFIDENCE_TEXT: Dict[str, str] = {
    "alta": "La confianza de la lectura SSM es alta.",
    "media-alta": "La confianza de la lectura SSM es razonablemente buena, aunque no perfecta.",
    "media": "La confianza de la lectura SSM es media: orienta, pero conviene no sobreinterpretarlo.",
    "baja": "La confianza de la lectura SSM es baja y hoy conviene leerlo con bastante prudencia.",
}


def _load_context_text(latest: pd.Series, valid_df: pd.DataFrame) -> str:
    load_mode = str(latest.get("ssm_load_context_mode", "unknown"))
    if load_mode != "rest_day_no_session":
        return _LOAD_TEXT.get(load_mode, "El contexto reciente de carga no añade una lectura fuerte.")

    if len(valid_df) < 2:
        return (
            "Hoy aún no hay sesión registrada y, para la lectura matinal, "
            "el modelo se apoya en la carga previa disponible."
        )

    prev = valid_df.iloc[-2]
    prev_mode = str(prev.get("ssm_load_context_mode", "unknown"))
    prev_load = prev.get("load_day", np.nan)
    prev_load_float = float(prev_load) if not pd.isna(prev_load) else float("nan")

    if np.isfinite(prev_load_float) and prev_load_float > 0:
        return (
            "Hoy aún no hay sesión registrada; para la lectura matinal, "
            "el contexto reciente venía de una sesión registrada."
        )
    if prev_mode == "session_recorded":
        return (
            "Hoy aún no hay sesión registrada; para la lectura matinal, "
            "el modelo se apoya en la carga previa ya consolidada."
        )
    if prev_mode == "calendar_gap_no_session":
        return (
            "Hoy aún no hay sesión registrada y además vienes de varios días sin sesiones "
            "consolidadas, así que el modelo asume algo más de incertidumbre."
        )
    if prev_mode == "missing_session_value":
        return (
            "Hoy aún no hay sesión registrada y la última carga disponible no era plenamente "
            "utilizable, así que el modelo añade prudencia."
        )
    return (
        "Hoy aún no hay sesión registrada; para la lectura matinal, "
        "el modelo se apoya en la carga previa disponible."
    )


def _state_label_from_history(state: float, valid_series: "pd.Series[float]") -> str:
    q33 = float(valid_series.quantile(0.33))
    q66 = float(valid_series.quantile(0.66))
    if state >= q66:
        return "alto"
    if state <= q33:
        return "bajo"
    return "medio"


def _confidence_label_from_obs(input_quality: str, state_sd: float, obs_mult: float) -> str:
    if input_quality == "suppressed":
        return "baja"
    if input_quality == "clean" and np.isfinite(state_sd) and state_sd <= 0.08 and np.isfinite(obs_mult) and obs_mult <= 1.25:
        return "alta"
    if input_quality == "degraded" or (np.isfinite(state_sd) and state_sd > 0.12) or (np.isfinite(obs_mult) and obs_mult > 1.75):
        return "media"
    return "media-alta"


def _component_text(baseline_state: float, fatigue_state: float, valid_df) -> str:
    """Renderiza el desglose tendencia lenta + fatiga aguda.

    Maneja fatigue_state negativo (boost) y muy pequeño sin sonar absurdo.
    """
    baseline_ms = _ms_from_log(baseline_state)
    fatigue_label = (
        _fatigue_label_from_history(fatigue_state, valid_df["ssm_fatigue_state"])
        if hasattr(valid_df, "columns") and "ssm_fatigue_state" in valid_df.columns
        else "indeterminada"
    )
    label_clause = (
        f", nivel {fatigue_label} en tu histórico"
        if fatigue_label not in ("indeterminada", "") else ""
    )
    base_clause = (
        f"Tu HRV de fondo (tendencia lenta) está en ≈{baseline_ms:.0f} ms "
        f"({baseline_state:.2f} en log)"
    )
    if fatigue_state > 0.02:
        fatigue_pct = (1.0 - float(np.exp(-fatigue_state))) * 100.0
        fatigue_ms_cost = baseline_ms - _ms_from_log(baseline_state - fatigue_state)
        return (
            f"{base_clause} y la fatiga reciente te descuenta "
            f"≈{fatigue_pct:.0f}% (≈{fatigue_ms_cost:.0f} ms, "
            f"{fatigue_state:.2f} en log{label_clause})."
        )
    if fatigue_state < -0.02:
        boost_pct = (float(np.exp(-fatigue_state)) - 1.0) * 100.0
        return (
            f"{base_clause} y el modelo no detecta fatiga neta — incluso compensa "
            f"≈+{boost_pct:.0f}% sobre tu base ({fatigue_state:+.2f} en log{label_clause})."
        )
    return (
        f"{base_clause} y la fatiga aguda hoy es prácticamente nula "
        f"({fatigue_state:+.2f} en log{label_clause})."
    )


def _fatigue_label_from_history(fatigue: float, valid_series: "pd.Series[float]") -> str:
    """Etiqueta personal (baja/media/alta) de fatiga aguda vs percentiles propios."""
    series = valid_series.dropna()
    if not np.isfinite(fatigue) or len(series) < 5:
        return "indeterminada"
    q33 = float(series.quantile(0.33))
    q66 = float(series.quantile(0.66))
    if fatigue >= q66:
        return "alta"
    if fatigue <= q33:
        return "baja"
    return "media"


def _ms_from_log(x: float) -> float:
    return float(np.exp(x)) if np.isfinite(x) else float("nan")


def _relation_text(state: float, rolling: float, delta: float) -> str:
    if not np.isfinite(delta):
        return "No puedo compararlo bien con tu rolling HRV de 7 días."
    state_ms = _ms_from_log(state)
    rolling_ms = _ms_from_log(rolling)
    pair = (
        f"tu rolling HRV 7d ({rolling:.2f} ≈ {rolling_ms:.0f} ms) "
        f"y el estado de hoy ({state:.2f} ≈ {state_ms:.0f} ms)"
    )
    if delta >= 0.08:
        return (
            f"Frente a {pair}, hoy queda por encima, "
            "lo que apunta a una recuperación algo mejor de lo habitual reciente."
        )
    if delta <= -0.08:
        return (
            f"Frente a {pair}, hoy queda por debajo, "
            "así que el modelo lo lee como bueno o normal, pero sin interpretarlo como una mejora clara."
        )
    return (
        f"Frente a {pair}, hoy está muy cerca, "
        "así que el modelo lo interpreta como continuidad de tu línea reciente."
    )


def _innovation_text(innovation: float) -> str:
    if not np.isfinite(innovation):
        return "La sorpresa del modelo no es interpretable hoy."
    pct = (float(np.exp(innovation)) - 1.0) * 100.0
    if innovation >= 0.12:
        return (
            f"La sorpresa del modelo es positiva: el HRV observado quedó +{pct:.0f}% "
            f"por encima de lo predicho por estado y carga (innovation={innovation:+.2f} en log)."
        )
    if innovation <= -0.12:
        return (
            f"La sorpresa del modelo es negativa: el HRV observado quedó {pct:+.0f}% "
            f"respecto a lo predicho por estado y carga (innovation={innovation:+.2f} en log)."
        )
    return (
        f"La sorpresa del modelo es pequeña ({pct:+.0f}%, innovation={innovation:+.2f} en log): "
        "el dato observado encaja bastante con lo que esperaba."
    )


def _sleep_obs_text(sleep_recovery_index: float, sleep_innovation: float) -> str:
    if not np.isfinite(sleep_recovery_index):
        return "Hoy no hay observación nocturna de sueño utilizable, así que el modelo se apoya más en el HRV matinal."
    sleep_ms = _ms_from_log(sleep_recovery_index)
    if np.isfinite(sleep_innovation) and sleep_innovation >= 0.12:
        return (
            f"La observación nocturna de sueño queda alta (≈{sleep_ms:.0f} ms, "
            f"{sleep_recovery_index:.2f} en log), así que también empuja la lectura hacia mejor recuperación."
        )
    if np.isfinite(sleep_innovation) and sleep_innovation <= -0.12:
        return (
            f"La observación nocturna de sueño queda baja (≈{sleep_ms:.0f} ms, "
            f"{sleep_recovery_index:.2f} en log), así que añade prudencia antes de tomar el día como un pico."
        )
    return (
        f"La observación nocturna de sueño aporta ≈{sleep_ms:.0f} ms "
        f"({sleep_recovery_index:.2f} en log) y se usa como apoyo al HRV matinal."
    )


def _build_daily_user_summary(shadow_df: pd.DataFrame) -> Dict[str, object]:
    valid = shadow_df[shadow_df["ssm_recovery_state"].notna()].copy()
    if valid.empty:
        return {
            "status": "unavailable",
            "interpretive_text": "El SSM todavía no tiene suficiente base para emitir una lectura diaria interpretable.",
        }

    latest = valid.iloc[-1]

    def _fval(col: str) -> float:
        v = latest.get(col, np.nan)
        return float(v) if not pd.isna(v) else float("nan")

    state = _fval("ssm_recovery_state")
    rolling = _fval("control_rolling_hrv_7d")
    state_sd = _fval("ssm_state_sd")
    state_lo = _fval("ssm_state_lo")
    state_hi = _fval("ssm_state_hi")
    baseline_state = _fval("ssm_baseline_state")
    fatigue_state = _fval("ssm_fatigue_state")
    sleep_recovery_index = _fval("sleep_recovery_index")
    sleep_recovery_sd = _fval("sleep_recovery_index_sd")
    sleep_recovery_var = _fval("sleep_recovery_index_var")
    sleep_input_quality = str(latest.get("sleep_input_quality", "unknown"))
    sleep_obs_mult = _fval("sleep_obs_var_multiplier")
    sleep_innovation = _fval("sleep_innovation")
    obs_mult = _fval("ssm_obs_var_multiplier")
    input_quality = str(latest.get("ssm_input_quality", "unknown"))
    load_mode = str(latest.get("ssm_load_context_mode", "unknown"))
    innovation = _fval("ssm_innovation")
    delta_vs_rolling = state - rolling if np.isfinite(rolling) else float("nan")

    state_label = _state_label_from_history(state, valid["ssm_recovery_state"])
    confidence = _confidence_label_from_obs(input_quality, state_sd, obs_mult)

    if np.isfinite(baseline_state) and np.isfinite(fatigue_state):
        component_text = _component_text(baseline_state, fatigue_state, valid)
    else:
        component_text = "No puedo desglosar bien los componentes lento y rápido de hoy."

    interpretive_text = " ".join([
        f"Respecto a tu histórico del SSM, hoy quedas en zona {state_label}.",
        component_text,
        _sleep_obs_text(sleep_recovery_index, sleep_innovation),
        f"Confianza de la lectura SSM: {confidence}.",
        _relation_text(state, rolling, delta_vs_rolling),
        _innovation_text(innovation),
        _QUALITY_TEXT.get(input_quality, "La calidad de observación de hoy no es plenamente clasificable."),
        _SLEEP_QUALITY_TEXT.get(sleep_input_quality, "La calidad de sueño de hoy no es plenamente clasificable."),
        _load_context_text(latest, valid),
        _CONFIDENCE_TEXT.get(confidence, ""),
    ])

    return {
        "status": "ok",
        "date": latest["Fecha"].strftime("%Y-%m-%d") if isinstance(latest["Fecha"], pd.Timestamp) else str(latest["Fecha"]),
        "state_label": state_label,
        "confidence_label": confidence,
        "ssm_recovery_state": state,
        "ssm_baseline_state": baseline_state,
        "ssm_fatigue_state": fatigue_state,
        "sleep_recovery_index": sleep_recovery_index,
        "sleep_recovery_index_sd": sleep_recovery_sd,
        "sleep_recovery_index_var": sleep_recovery_var,
        "state_interval_lo": state_lo,
        "state_interval_hi": state_hi,
        "state_sd": state_sd,
        "rolling_hrv_7d": rolling,
        "delta_vs_rolling_hrv_7d": delta_vs_rolling,
        "input_quality": input_quality,
        "obs_var_multiplier": obs_mult,
        "sleep_input_quality": sleep_input_quality,
        "sleep_obs_var_multiplier": sleep_obs_mult,
        "sleep_innovation": sleep_innovation,
        "load_context_mode": load_mode,
        "innovation": innovation,
        "interpretive_text": interpretive_text,
    }


def preprocess_base(
    core_df: pd.DataFrame,
    sessions_day_df: pd.DataFrame,
    sleep_df: pd.DataFrame | None = None,
    cfg: SSMConfig = CFG,
) -> pd.DataFrame:
    """Pre-procesa inputs hasta antes del Kalman. Reutilizable para variantes de cfg.

    El sleep_diag de la observación nocturna se guarda en base.attrs['_sleep_diag']
    para que run_ssm_from_base lo recupere sin recalcularlo.
    """
    base = _prepare_daily_frame(core_df, sessions_day_df, sleep_df)
    base = _derive_obs_quality(base, cfg)
    base = _derive_load_context(base)
    base, sleep_diag = _derive_sleep_context(base, cfg)
    base.attrs["_sleep_diag"] = sleep_diag
    return base


def run_ssm_from_base(
    base: pd.DataFrame,
    sessions_day_df: pd.DataFrame,
    wellness_df: pd.DataFrame,
    cfg: SSMConfig = CFG,
) -> Tuple[pd.DataFrame, Dict[str, object]]:
    """Ejecuta solo el Kalman sobre un base ya pre-procesado. Evita recalcular obs/load/sleep."""
    sleep_diag: Dict[str, object] = base.attrs.get("_sleep_diag", {})
    shadow, kalman_diag = _kalman_shadow(base, cfg)
    kalman_diag = {**kalman_diag, **sleep_diag}
    metadata = {
        "shadow_frame": shadow,
        "kalman_diagnostics": kalman_diag,
        "load_signal_pretest": _load_signal_pretest(shadow),
        "outcome_audit": _audit_outcomes(sessions_day_df, wellness_df),
        "daily_user_summary": _build_daily_user_summary(shadow),
    }
    sidecar = shadow[SIDE_CAR_COLUMNS].copy()
    sidecar["Fecha"] = sidecar["Fecha"].dt.strftime("%Y-%m-%d")
    return sidecar, metadata


def build_ssm_shadow(
    core_df: pd.DataFrame,
    sessions_day_df: pd.DataFrame,
    wellness_df: pd.DataFrame,
    sleep_df: pd.DataFrame | None = None,
    cfg: SSMConfig = CFG,
) -> Tuple[pd.DataFrame, Dict[str, object]]:
    base = preprocess_base(core_df, sessions_day_df, sleep_df, cfg)
    sidecar, metadata = run_ssm_from_base(base, sessions_day_df, wellness_df, cfg)
    sidecar.attrs["metadata"] = metadata
    return sidecar, metadata


def main(argv: List[str]) -> int:
    args = parse_args(argv)

    global DATA_DIR, IN_CORE, IN_SESSIONS_DAY, IN_SLEEP, IN_WELLNESS, OUT_SSM_SHADOW, OUT_SSM_METADATA
    if "data_dir" in args:
        DATA_DIR = resolve_writable_dir(Path(args["data_dir"]), CONFIG_DATA_DIR)
        IN_CORE = DATA_DIR / "ENDURANCE_HRV_master_CORE.csv"
        IN_SESSIONS_DAY = DATA_DIR / "ENDURANCE_HRV_sessions_day.csv"
        IN_SLEEP = DATA_DIR / "ENDURANCE_HRV_sleep.csv"
        IN_WELLNESS = DATA_DIR / "ENDURANCE_HRV_wellness_subjective.csv"
        OUT_SSM_SHADOW = DATA_DIR / "ENDURANCE_HRV_ssm_shadow.csv"
        OUT_SSM_METADATA = DATA_DIR / "ENDURANCE_HRV_ssm_shadow_metadata.json"

    try:
        core_df = _read_csv_required(IN_CORE, ["Fecha", "lnRMSSD", "Calidad", "HRV_Stability", "Artifact_pct", "Flags"])
        sessions_day_df = _read_csv_required(IN_SESSIONS_DAY, ["Fecha", "load_day"])
        sleep_df = pd.read_csv(IN_SLEEP) if IN_SLEEP.exists() else pd.DataFrame(columns=SLEEP_OBS_COLUMNS)
        wellness_df = pd.read_csv(IN_WELLNESS) if IN_WELLNESS.exists() else pd.DataFrame(columns=["Fecha"])
    except (FileNotFoundError, ValueError) as exc:
        print(f"[ERROR] {exc}")
        return 2

    sidecar, detail = build_ssm_shadow(core_df, sessions_day_df, wellness_df, sleep_df=sleep_df, cfg=CFG)
    metadata = _build_metadata(
        detail["shadow_frame"],
        IN_CORE,
        IN_SESSIONS_DAY,
        IN_SLEEP,
        CFG,
        detail["kalman_diagnostics"],
        detail["load_signal_pretest"],
        detail["outcome_audit"],
    )

    write_csv_atomic(sidecar.reindex(columns=SIDE_CAR_COLUMNS), OUT_SSM_SHADOW)
    write_json_atomic(metadata, OUT_SSM_METADATA)

    last_fecha = sidecar["Fecha"].iloc[-1] if not sidecar.empty else "N/A"
    print(f"[OK] SSM sombra actualizado hasta {last_fecha}")
    return 0


if __name__ == "__main__":
    import sys

    raise SystemExit(main(sys.argv[1:]))
