#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ENDURANCE HRV — Decisor FINAL/DASHBOARD
======================================

Revisión de módulo: r2026-04-08
Contrato esperado: FINAL 66 cols, DASHBOARD 10 cols
Sistema vigente: ENDURANCE HRV V4.10

Lee:
  - ENDURANCE_HRV_master_CORE.csv

Genera:
  - ENDURANCE_HRV_master_FINAL.csv     (66 cols, gate + sombras + residual + warning dual + auditoría raw-vs-ref + RE-01)
  - ENDURANCE_HRV_master_DASHBOARD.csv (10 cols, vista operativa compacta)

Normativa:
  - ENDURANCE_HRV_Spec_Tecnica.md
  - ENDURANCE_HRV_Estructura.md
  - ENDURANCE_HRV_Diccionario.md

Notas clave:
- ROLL3 y baselines usan solo días "clean" (Calidad == "OK") y datos numéricos.
- El gate base (decisor) es BASE60; sombras BASE42/BASE28 son informativas por defecto (modo O2_SHADOW).
- residual_tag (+/++/+++ o -/--/---) es informativo; NO recolorea el gate.
"""

from __future__ import annotations

import json
import os
import sys
import logging
import tempfile
import time
from dataclasses import dataclass, replace, asdict
from pathlib import Path
from typing import Dict, Optional, Tuple, List

import numpy as np
import pandas as pd
from hrv_app.io_utils import write_csv_atomic, write_json_atomic
from hrv_app.config import (
    DATA_DIR as CONFIG_DATA_DIR,
    SSM_SHADOW_PATH,
    resolve_writable_dir,
)
from hrv_app.run_manifest import (
    artifact_signature,
    build_run_manifest,
    file_digest,
    write_run_manifest_atomic,
)


# =============================================================================
# Configuración
# =============================================================================

VERDE = "VERDE"
AMBAR = "ÁMBAR"
ROJO  = "ROJO"
NO    = "NO"

GATE_ORDER = {VERDE: 0, AMBAR: 1, ROJO: 2}

DATA_DIR = CONFIG_DATA_DIR

IN_CORE = DATA_DIR / "ENDURANCE_HRV_master_CORE.csv"
OUT_FINAL = DATA_DIR / "ENDURANCE_HRV_master_FINAL.csv"
OUT_DASHBOARD = DATA_DIR / "ENDURANCE_HRV_master_DASHBOARD.csv"
OUT_FINAL_REASON_ITEMS = DATA_DIR / "ENDURANCE_HRV_master_FINAL_reason_items.json"
OUT_CORE_MANIFEST = DATA_DIR / "ENDURANCE_HRV_master_CORE_manifest.json"
OUT_FINAL_MANIFEST = DATA_DIR / "ENDURANCE_HRV_master_FINAL_manifest.json"
DATE_FORMAT = "%Y-%m-%d"


@dataclass(frozen=True)
class Config:
    # Gate
    roll_n: int = 3
    base60_days: int = 60
    base42_days: int = 42
    base28_days: int = 28

    min_roll3_clean: int = 3
    min_base60_clean: int = 30
    min_base42_clean: int = 21
    min_base28_clean: int = 14

    swc_mult: float = 0.5  # SWC = swc_mult * robust_sd (MAD*1.4826)

    # Decision mode
    decision_mode: str = "O2_SHADOW"  # O2_SHADOW (default) | O3_OVERRIDE_PERSIST_2of3

    # Residual tag thresholds (en unidades de SWC_res)
    tag_t1: float = 0.5
    tag_t2: float = 1.0
    tag_t3: float = 2.0

    # Warning baseline60_degraded
    warning_mode: str = (os.environ.get("HRV_WARNING_MODE", "adaptive90").strip() or "adaptive90")
    adaptive_window_days: int = 90
    adaptive_ref_quantile: float = 0.75
    warning_factor: float = 0.85
    healthy_start: str = os.environ.get("HRV_HEALTHY_START", "2025-07-01")
    healthy_end: str   = os.environ.get("HRV_HEALTHY_END",   "2025-09-30")
    healthy_factor: float = 0.85
    p20_q: float = 0.20


CFG = Config()
SWC_FLOOR = 0.04879  # ln(1.05), floor mínimo para SWC
VETO_MULT = 2.0      # veto si raw cae > 2xSWC bajo base60
ACUTE_LOAD_72H_REL_HIGH_FALLBACK = 3.9
ACUTE_LOAD_72H_REL_VERY_HIGH_FALLBACK = 4.5
WORK_7D_HIGH = 200
Z3_7D_HIGH = 60
_VALID_LAYERS = {"measured", "proxy", "inference", "action"}
_VALID_SEVERITIES = {"low", "medium", "high", "very_high"}

log = logging.getLogger("build_hrv_final_dashboard")


# =============================================================================
# Columnas (contrato)
# =============================================================================

COLS_FINAL = [
    "Fecha","Calidad","HRV_Stability","Artifact_pct","Tiempo_Estabilizacion",
    "Stability_Subtype","tail_mismatch_pct",
    "HR_today","RMSSD_stable","lnRMSSD_today",
    "lnRMSSD_used","HR_used","n_roll3",
    "gate_raw_today","gate_raw_reason","unstable_note",
    "ln_base60","HR_base60","n_base60","SWC_ln","SWC_HR","d_ln","d_HR",
    "gate_base60","gate_razon_base60",
    "gate_shadow42","gate_razon_shadow42","n_base42",
    "gate_shadow28","gate_razon_shadow28","n_base28",
    "decision_mode","gate_final","gate_final_delta","decision_path","override_reason",
    "residual_ln","residual_z","residual_tag","gate_badge",
    "quality_flag","Color_operativo",
    "Action","Action_detail","bad_streak","bad_7d",
    "baseline60_degraded","degraded_vs_best","degraded_vs_current_normal",
    "healthy_rmssd","healthy_hr","healthy_period",
    "flag_sistemico","flag_razon",
    "warning_threshold","warning_threshold_best","warning_threshold_current_normal","warning_mode",
    "veto_agudo","ln_pre_veto","swc_ln_floor",
    "recovery_context_quality","recovery_support_class",
    "recovery_discordance_flag","recovery_discordance_reason",
    "reason_text",
]

COLS_DASHBOARD = [
    "Fecha","Calidad","HR_today","RMSSD_stable","gate_badge","Action",
    "gate_razon_base60","decision_path","baseline60_degraded","reason_text"
]


# =============================================================================
# Utilidades
# =============================================================================

def robust_sd(x: np.ndarray) -> float:
    """SD robusta basada en MAD (1.4826*MAD)."""
    x = np.asarray(x, dtype=float)
    x = x[np.isfinite(x)]
    if x.size == 0:
        return float("nan")
    med = np.median(x)
    mad = np.median(np.abs(x - med))
    return float(1.4826 * mad)


def _rank_gate(g: str) -> Optional[int]:
    return GATE_ORDER.get(g)


def _downgrade(g: str, k: int = 1) -> str:
    if g == VERDE:
        return AMBAR if k >= 1 else VERDE
    if g == AMBAR:
        return ROJO if k >= 1 else AMBAR
    if g == ROJO:
        return ROJO
    return g


def _upgrade(g: str, k: int = 1) -> str:
    if g == ROJO:
        return AMBAR if k >= 1 else ROJO
    if g == AMBAR:
        return VERDE if k >= 1 else AMBAR
    if g == VERDE:
        return VERDE
    return g


def last_n_valid_mean(values: np.ndarray, valid: np.ndarray, n: int, i: int) -> Tuple[float, int]:
    """Media de los últimos n valores válidos hasta i (incluido)."""
    take: List[float] = []
    j = i
    while j >= 0 and len(take) < n:
        if bool(valid[j]) and np.isfinite(values[j]):
            take.append(float(values[j]))
        j -= 1
    if len(take) == 0:
        return (float("nan"), 0)
    return (float(np.mean(take)), len(take))


def window_mask(dates: np.ndarray, i: int, days: int) -> np.ndarray:
    """Máscara para ventana [t-days, t) (shift-1)."""
    t = dates[i]
    lo = t - np.timedelta64(days, "D")
    return (dates >= lo) & (dates < t)


def window_stats(values: np.ndarray, valid: np.ndarray, wmask: np.ndarray, swc_mult: float) -> Tuple[float, float, int]:
    """Mediana + SWC (robusta) en una ventana. Solo valores válidos."""
    m = wmask & valid & np.isfinite(values)
    x = values[m].astype(float)
    n = int(x.size)
    if n == 0:
        return (float("nan"), float("nan"), 0)
    base = float(np.median(x))
    sd = robust_sd(x)
    swc = float(swc_mult * sd) if np.isfinite(sd) else float("nan")
    return (base, swc, n)


def _window_start_indices(dates: np.ndarray, days: int) -> np.ndarray:
    """Start index for the left-closed, right-open rolling window [t-days, t)."""
    lower = dates - np.timedelta64(days, "D")
    return np.searchsorted(dates, lower, side="left")


def _window_stats_range(
    values: np.ndarray,
    valid: np.ndarray,
    start: int,
    end: int,
    swc_mult: float,
) -> Tuple[float, float, int]:
    """Mediana + SWC robusta sobre un slice ya delimitado."""
    if end <= start:
        return (float("nan"), float("nan"), 0)
    window = values[start:end]
    m = valid[start:end] & np.isfinite(window)
    x = window[m].astype(float)
    n = int(x.size)
    if n == 0:
        return (float("nan"), float("nan"), 0)
    base = float(np.median(x))
    sd = robust_sd(x)
    swc = float(swc_mult * sd) if np.isfinite(sd) else float("nan")
    return (base, swc, n)


def compute_healthy_anchors(core: pd.DataFrame, cfg: Config) -> Tuple[float, float, str]:
    """
    Anclas "healthy" para warning baseline60_degraded.
    - Se calculan sobre días clean (Calidad == OK) usando mediana móvil 7d.
    """
    df = core.copy()
    df["Fecha_dt"] = pd.to_datetime(df["Fecha"], format=DATE_FORMAT, errors="coerce")
    is_clean = (df["Calidad"] == "OK") & df["lnRMSSD"].notna() & df["HR_stable"].notna() & df["RMSSD_stable"].notna()
    sub = df.loc[is_clean, ["Fecha_dt", "RMSSD_stable", "HR_stable"]].sort_values("Fecha_dt").copy()
    if sub.empty:
        return (float("nan"), float("nan"), f"{cfg.healthy_start}..{cfg.healthy_end}")

    sub["RMSSD_med7"] = sub["RMSSD_stable"].rolling(7, min_periods=3).median()
    sub["HR_med7"] = sub["HR_stable"].rolling(7, min_periods=3).median()

    hs = pd.to_datetime(cfg.healthy_start, format=DATE_FORMAT, errors="coerce")
    he = pd.to_datetime(cfg.healthy_end, format=DATE_FORMAT, errors="coerce")
    if pd.isna(hs) or pd.isna(he):
        return (float(np.nanmedian(sub["RMSSD_med7"])), float(np.nanmedian(sub["HR_med7"])), "invalid_period(fallback)")

    in_period = (sub["Fecha_dt"] >= hs) & (sub["Fecha_dt"] <= he)
    s2 = sub.loc[in_period]
    if s2.empty:
        return (float(np.nanmedian(sub["RMSSD_med7"])), float(np.nanmedian(sub["HR_med7"])), f"{cfg.healthy_start}..{cfg.healthy_end}(fallback)")
    return (float(np.nanmedian(s2["RMSSD_med7"])), float(np.nanmedian(s2["HR_med7"])), f"{cfg.healthy_start}..{cfg.healthy_end}")


def compute_dual_baseline_signals(
    fechas: pd.Series,
    rmssd_base60_equiv: pd.Series,
    healthy_rmssd: float,
    cfg: Config,
) -> Dict[str, np.ndarray]:
    """Compute the two canonical long-term baseline warnings plus their thresholds."""
    fecha_index = pd.to_datetime(fechas, format=DATE_FORMAT, errors="coerce")
    values = rmssd_base60_equiv.astype(float)
    mask = np.isfinite(values.to_numpy(dtype=float))

    threshold_best = np.full(len(values), np.nan, dtype=float)
    degraded_best = np.array([False] * len(values), dtype=bool)
    if np.isfinite(healthy_rmssd):
        threshold_best[:] = float(cfg.healthy_factor * healthy_rmssd)
        degraded_best = mask & (values.to_numpy(dtype=float) < threshold_best)

    dated = pd.Series(values.to_numpy(dtype=float), index=fecha_index)
    rolling_ref = dated.rolling(f"{cfg.adaptive_window_days}D", min_periods=30).quantile(cfg.adaptive_ref_quantile)
    threshold_current = (rolling_ref * cfg.warning_factor).to_numpy(dtype=float)
    degraded_current = mask & np.isfinite(threshold_current) & (values.to_numpy(dtype=float) < threshold_current)

    return {
        "warning_threshold_best": threshold_best,
        "warning_threshold_current_normal": threshold_current,
        "degraded_vs_best": degraded_best,
        "degraded_vs_current_normal": degraded_current,
    }


def compute_warning_signal(
    fechas: pd.Series,
    rmssd_base60_equiv: pd.Series,
    healthy_rmssd: float,
    cfg: Config,
) -> Tuple[np.ndarray, np.ndarray]:
    """
    Build the medium-term legacy warning signal from the canonical dual outputs.

    Returns:
      - effective warning threshold(s), one per row
      - baseline60_degraded boolean mask
    """
    dual = compute_dual_baseline_signals(fechas, rmssd_base60_equiv, healthy_rmssd, cfg)

    if cfg.warning_mode == "adaptive90":
        return dual["warning_threshold_current_normal"], dual["degraded_vs_current_normal"]

    if cfg.warning_mode == "healthy85":
        return dual["warning_threshold_best"], dual["degraded_vs_best"]

    if cfg.warning_mode == "p20":
        values = rmssd_base60_equiv.astype(float)
        mask = np.isfinite(values.to_numpy(dtype=float))
        thresholds = np.full(len(values), np.nan, dtype=float)
        degraded = np.array([False] * len(values), dtype=bool)
        x = values.dropna().to_numpy(dtype=float)
        if x.size >= 10:
            thresholds[:] = float(np.quantile(x, cfg.p20_q))
            degraded = mask & (values.to_numpy(dtype=float) < thresholds)
        return thresholds, degraded

    raise ValueError("warning_mode inválido. Usa adaptive90, healthy85 o p20.")


def select_legacy_warning_signal(
    dual_baseline: Dict[str, np.ndarray],
    rmssd_base60_equiv: pd.Series,
    cfg: Config,
) -> Tuple[np.ndarray, np.ndarray]:
    """Select the legacy warning signal from canonical outputs plus p20 fallback."""
    if cfg.warning_mode == "adaptive90":
        return (
            dual_baseline["warning_threshold_current_normal"],
            dual_baseline["degraded_vs_current_normal"],
        )

    if cfg.warning_mode == "healthy85":
        return (
            dual_baseline["warning_threshold_best"],
            dual_baseline["degraded_vs_best"],
        )

    if cfg.warning_mode == "p20":
        values = rmssd_base60_equiv.astype(float)
        mask = np.isfinite(values.to_numpy(dtype=float))
        thresholds = np.full(len(values), np.nan, dtype=float)
        degraded = np.array([False] * len(values), dtype=bool)
        x = values.dropna().to_numpy(dtype=float)
        if x.size >= 10:
            thresholds[:] = float(np.quantile(x, cfg.p20_q))
            degraded = mask & (values.to_numpy(dtype=float) < thresholds)
        return thresholds, degraded

    raise ValueError("warning_mode inválido. Usa adaptive90, healthy85 o p20.")


def residual_tag(res_z: float, cfg: Config) -> str:
    if not np.isfinite(res_z):
        return ""
    if res_z >= cfg.tag_t3:
        return "+++"
    if res_z >= cfg.tag_t2:
        return "++"
    if res_z >= cfg.tag_t1:
        return "+"
    if res_z <= -cfg.tag_t3:
        return "---"
    if res_z <= -cfg.tag_t2:
        return "--"
    if res_z <= -cfg.tag_t1:
        return "-"
    return ""


def eval_gate(ln_val: float, hr_val: float, b_ln: float, b_hr: float, sw_ln: float, sw_hr: float) -> Tuple[str, str]:
    if not all(np.isfinite(v) for v in (ln_val, hr_val, b_ln, b_hr, sw_ln, sw_hr)) or sw_ln == 0.0 or sw_hr == 0.0:
        return NO, "RAW_NAN/0"

    dln = float(ln_val - b_ln)
    dhr = float(hr_val - b_hr)
    ln_bajo = dln < -sw_ln
    hr_alto = dhr > sw_hr

    if ln_bajo and hr_alto:
        return ROJO, "2D_AMBOS"
    if ln_bajo:
        return AMBAR, "2D_LN"
    if hr_alto:
        return AMBAR, "2D_HR"
    return VERDE, "2D_OK"


def _safe_float(row: pd.Series, col: str) -> Optional[float]:
    """Extract float from sleep row, return None if missing."""
    try:
        v = row[col]
        if pd.isna(v):
            return None
        return float(v)
    except (KeyError, TypeError, ValueError):
        return None


def _has_strict_previous_load(load_3d: Optional[float], load_3d_nobs: Optional[float], min_nobs: int = 3) -> bool:
    """Return True when the prior 3-day load window is fully covered."""
    if load_3d is None or load_3d_nobs is None:
        return False
    try:
        return np.isfinite(float(load_3d)) and float(load_3d_nobs) >= float(min_nobs)
    except (TypeError, ValueError):
        return False


def _build_sessions_day_lookups(
    sday_df: pd.DataFrame,
) -> Tuple[Optional[pd.DataFrame], Optional[pd.DataFrame], Optional[pd.DataFrame], Optional[pd.DataFrame]]:
    if "Fecha" not in sday_df.columns:
        return None, None, None, None

    base_df = sday_df.copy()
    base_df["Fecha"] = base_df["Fecha"].astype(str)
    base_df = base_df.drop_duplicates(subset=["Fecha"], keep="last")
    base_df["Fecha_dt"] = pd.to_datetime(base_df["Fecha"], format=DATE_FORMAT, errors="coerce")
    base_df = base_df.dropna(subset=["Fecha_dt"]).sort_values("Fecha_dt")
    exact_lookup = base_df.set_index("Fecha")

    ctx_cols = ["acwr_simple_prev", "monotony_7d_prev", "strain_7d_prev", "load_ctx_ready"]
    present_ctx_cols = [col for col in ctx_cols if col in base_df.columns]
    ctx_lookup: Optional[pd.DataFrame] = None

    if present_ctx_cols:
        ctx_df = base_df[["Fecha"] + present_ctx_cols].copy()
        if not ctx_df.empty:
            ctx_df["Fecha_dt"] = pd.to_datetime(ctx_df["Fecha"], format=DATE_FORMAT, errors="coerce")
            ctx_df = ctx_df.dropna(subset=["Fecha_dt"]).sort_values("Fecha_dt")
            ctx_lookup = ctx_df.set_index("Fecha_dt")[present_ctx_cols]
            full_range = pd.date_range(ctx_lookup.index.min(), ctx_lookup.index.max(), freq="D")
            ctx_lookup = ctx_lookup.reindex(full_range).ffill(limit=7)
            ctx_lookup.index = ctx_lookup.index.strftime("%Y-%m-%d")
            ctx_lookup.index.name = "Fecha"

    clustering_cols = [
        "intense_days_prev_3d",
        "intense_days_prev_5d",
        "intensity_clustering_flag",
        "intensity_clustering_level",
    ]
    present_clustering_cols = [col for col in clustering_cols if col in base_df.columns]
    clustering_lookup: Optional[pd.DataFrame] = None
    if present_clustering_cols:
        clustering_df = base_df[["Fecha"] + present_clustering_cols].copy()
        if not clustering_df.empty:
            clustering_df["Fecha_dt"] = pd.to_datetime(clustering_df["Fecha"], format=DATE_FORMAT, errors="coerce")
            clustering_df = clustering_df.dropna(subset=["Fecha_dt"]).sort_values("Fecha_dt")
            clustering_lookup = clustering_df.set_index("Fecha_dt")[present_clustering_cols]
            full_range = pd.date_range(
                clustering_lookup.index.min(),
                clustering_lookup.index.max() + pd.Timedelta(days=2),
                freq="D",
            )
            clustering_lookup = clustering_lookup.reindex(full_range).ffill(limit=2)
            clustering_lookup.index = clustering_lookup.index.strftime("%Y-%m-%d")
            clustering_lookup.index.name = "Fecha"

    threshold_lookup: Optional[pd.DataFrame] = None
    threshold_specs: Dict[str, Tuple[str, float]] = {
        "acute_load_72h_rel_p75": ("acute_load_72h_rel", 0.75),
        "acute_load_72h_rel_p90": ("acute_load_72h_rel", 0.90),
        "strain_p75": ("strain_7d_prev", 0.75),
        "strain_p90": ("strain_7d_prev", 0.90),
    }
    threshold_cols: Dict[str, np.ndarray] = {}

    ready_mask = None
    if "load_ctx_ready" in base_df.columns:
        ready_mask = base_df["load_ctx_ready"].astype(str).str.lower().isin({"true", "1"})

    for out_col, (source_col, quantile) in threshold_specs.items():
        if source_col not in base_df.columns:
            continue
        source = pd.to_numeric(base_df[source_col], errors="coerce")
        if ready_mask is not None:
            source = source.where(ready_mask)
        # Thresholds are causal: every day sees only the prior ready history.
        threshold_cols[out_col] = source.shift(1).expanding(min_periods=8).quantile(quantile).to_numpy(dtype=float)

    if threshold_cols:
        threshold_lookup = pd.DataFrame(
            threshold_cols,
            index=base_df["Fecha"].astype(str).to_list(),
        )
        threshold_lookup.index.name = "Fecha"

    return exact_lookup, ctx_lookup, clustering_lookup, threshold_lookup


def _append_unique(items: List[str], value: str) -> None:
    if value and value not in items:
        items.append(value)


def _format_minutes_human(value: float) -> str:
    total_min = int(round(float(value)))
    hours, minutes = divmod(total_min, 60)
    if hours and minutes:
        return f"{hours}h{minutes:02d}"
    if hours:
        return f"{hours}h"
    return f"{minutes}min"


def _build_clustering_window_clause(
    intense_days_prev_3d: Optional[float],
    intense_days_prev_5d: Optional[float],
) -> str:
    def _window_text(value: float, window: int) -> str:
        count = int(value)
        if count == 1:
            return f"1 día intenso en los últimos {window}"
        return f"{count} días intensos en los últimos {window}"

    has_3d = intense_days_prev_3d is not None
    has_5d = intense_days_prev_5d is not None
    if has_3d and has_5d:
        return (
            f"{_window_text(intense_days_prev_3d, 3)} "
            f"(y {int(intense_days_prev_5d)} en los últimos 5)"
        )
    if has_3d:
        return _window_text(intense_days_prev_3d, 3)
    if has_5d:
        return _window_text(intense_days_prev_5d, 5)
    return ""


def _build_clustering_window_suffix(
    intense_days_prev_3d: Optional[float],
    intense_days_prev_5d: Optional[float],
) -> str:
    bits: List[str] = []
    if intense_days_prev_3d is not None:
        bits.append(f"{int(intense_days_prev_3d)} intensos en últimos 3d")
    if intense_days_prev_5d is not None:
        bits.append(f"{int(intense_days_prev_5d)} en últimos 5d")
    return "; ".join(bits)


def _emit_reason(
    reason_items: List[List[dict]],
    reason_parts: List[List[str]],
    idx: int,
    *,
    type: str,
    layer: str,
    source: str,
    message: str,
    variant: Optional[str] = None,
    severity: Optional[str] = None,
    metric: Optional[str] = None,
    value: Optional[object] = None,
    threshold: Optional[object] = None,
    gate_scope: Optional[str] = None,
    codes: Optional[List[str]] = None,
    evidence: Optional[List[str]] = None,
) -> None:
    assert layer in _VALID_LAYERS, f"layer inválido: {layer!r}"
    if severity is not None:
        assert severity in _VALID_SEVERITIES, f"severity inválida: {severity!r}"

    item: Dict[str, object] = {
        "type": type,
        "layer": layer,
        "source": source,
        "message": message,
    }
    if variant is not None:
        item["variant"] = variant
    if severity is not None:
        item["severity"] = severity
    if metric is not None:
        item["metric"] = metric
    if value is not None:
        item["value"] = value
    if threshold is not None:
        item["threshold"] = threshold
    if gate_scope is not None:
        item["gate_scope"] = gate_scope
    if codes:
        item["codes"] = [code for code in codes if str(code).strip()]
    if evidence:
        item["evidence"] = [bit for bit in evidence if str(bit).strip()]

    reason_items[idx].append(item)
    reason_parts[idx].append(message)


def _normalize_reason_json_value(value: object) -> object:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, (np.integer, np.floating, np.bool_)):
        return value.item()
    if isinstance(value, dict):
        return {
            str(key): _normalize_reason_json_value(subvalue)
            for key, subvalue in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [_normalize_reason_json_value(item) for item in value]
    return str(value)


def _build_reason_items_sidecar(
    fechas: List[str],
    reason_items: List[List[dict]],
) -> Dict[str, object]:
    items_by_date: Dict[str, List[dict]] = {}
    for fecha, raw_items in zip(fechas, reason_items):
        items_by_date[str(fecha)] = [
            _normalize_reason_json_value(item)
            for item in raw_items
            if isinstance(item, dict)
        ]
    return {
        "schema_version": "1.0",
        "source": "build_hrv_final_dashboard.py",
        "items_by_date": items_by_date,
    }


def _split_recovery_codes(codes: List[str]) -> Tuple[List[str], List[str]]:
    sleep_codes = [
        code
        for code in codes
        if code in {"sleep_basic_poor", "sleep_score_low", "nightly_rmssd_low"}
    ]
    load_codes = [
        code
        for code in codes
        if code in {"load_context_high", "intensity_clustering", "recent_load_low"}
    ]
    return sleep_codes, load_codes


def _recovery_context_quality(
    has_basic_sleep: bool,
    has_load_signal: bool,
    has_rich_sleep: bool,
) -> str:
    if has_rich_sleep:
        return "rich"
    if has_basic_sleep or has_load_signal:
        return "basic"
    return "none"


def _classify_recovery_support(
    gate: str,
    coverage: str,
    support_codes: List[str],
    caution_codes: List[str],
) -> Tuple[str, bool]:
    has_support = bool(support_codes)
    has_caution = bool(caution_codes)
    sleep_caution_codes, load_caution_codes = _split_recovery_codes(caution_codes)

    if coverage == "none" or gate == NO:
        return "neutral", False
    if gate == VERDE:
        cross_domain_caution = bool(sleep_caution_codes) and bool(load_caution_codes)
        repeated_sleep_caution = len(sleep_caution_codes) >= 2
        if cross_domain_caution or repeated_sleep_caution:
            return "fragile", True
        if has_support:
            return "supported", False
        return "neutral", False
    if gate == AMBAR:
        if has_support and not has_caution:
            return "supported", False
        if has_caution and not has_support:
            return "fragile", True
        return "neutral", False
    if gate == ROJO:
        if has_support and not has_caution:
            return "conflicted", True
        if has_caution:
            return "supported", False
        return "neutral", False
    return "neutral", False


def _recovery_summary_message(gate: str, recovery_class: str, support_codes: List[str], caution_codes: List[str]) -> str:
    caution_set = set(caution_codes)
    support_set = set(support_codes)
    sleep_caution_set, load_caution_set = _split_recovery_codes(caution_codes)

    if gate == VERDE and recovery_class == "fragile":
        if sleep_caution_set and load_caution_set:
            return "VERDE, pero sueño y carga reciente piden prudencia"
        if sleep_caution_set:
            return "VERDE, pero el sueño no acompaña del todo"
        if load_caution_set:
            return "VERDE, pero la carga reciente pide prudencia"
        return "VERDE, pero alguna señal de recuperación pide prudencia"
    if gate == AMBAR and recovery_class == "supported":
        if {"sleep_score_good", "nightly_rmssd_good"} & support_set:
            return "ÁMBAR con señales nocturnas favorables"
        if "recent_load_low" in support_set:
            return "ÁMBAR con poca carga reciente"
        return "ÁMBAR con señales objetivas razonables"
    if gate == AMBAR and recovery_class == "fragile":
        return "ÁMBAR con señales de recuperación flojas"
    if gate == ROJO and recovery_class == "conflicted":
        if {"sleep_score_good", "nightly_rmssd_good"} & support_set and "recent_load_low" in support_set:
            return "ROJO, pero sueño y carga reciente no encajan con un rojo claro"
        if {"sleep_score_good", "nightly_rmssd_good"} & support_set:
            return "ROJO, pero la señal nocturna sale mejor de lo esperado"
        if "recent_load_low" in support_set:
            return "ROJO, pero la carga reciente no parece alta"
        return "ROJO, pero hay señales que no encajan del todo"
    if gate == ROJO and recovery_class == "supported":
        if sleep_caution_set and load_caution_set:
            return "ROJO respaldado por mala recuperación y carga reciente"
        if sleep_caution_set:
            return "ROJO respaldado por mala recuperación nocturna"
        if load_caution_set:
            return "ROJO respaldado por carga reciente exigente"
        return "ROJO respaldado por señales desfavorables de recuperación"
    return ""


def _recovery_action_message(gate: str, recovery_class: str, support_codes: List[str], caution_codes: List[str]) -> str:
    if gate == VERDE and recovery_class == "fragile":
        return "Acción: contener la intensidad"
    if gate == AMBAR and recovery_class == "supported":
        return "Acción: Z2 controlado es razonable si sensaciones normales"
    if gate == AMBAR and recovery_class == "fragile":
        return "Acción: mejor sesgo conservador hoy"
    if gate == ROJO and recovery_class == "conflicted":
        return "Acción: revisar factores externos"
    if gate == ROJO and recovery_class == "supported":
        return "Acción: suave o descanso"
    return ""


def _recovery_discordance_message(gate: str, recovery_class: str, coverage: str, fallback: str) -> str:
    if fallback:
        return fallback
    return f"Discordancia de recuperación ({gate}, {recovery_class}, cobertura={coverage})"


# =============================================================================
# reason_text composition (UX-01)
# =============================================================================

# Tipos cuya semántica es matizar el verdict del gate (no datos crudos).
_VERDICT_TYPES = frozenset({
    "contradiction",
    "green_load_caution",
    "green_load_convergence",
    "nightly_discordance",
    "recovery_discordance",
    "recovery_support",
    "ssm_context",
})
_ACTION_TYPES = frozenset({"action_constraint"})

# Tabla de redundancia: cuando recovery_support|recovery_discordance carga la
# frase clave Y otro emisor más específico está presente, suprimir el eco genérico.
# El matching por frase es frágil; cuando el emisor pase a estructura con `codes`
# o `variant` explícito, migrar a comparación estructurada.
_RECOVERY_SUPPORT_REDUNDANT = (
    ("señal nocturna sale mejor", frozenset({"nightly_discordance"})),
    ("el sueño no acompaña", frozenset({"sleep_duration", "sleep_fragmentation"})),
    (
        "la carga reciente pide prudencia",
        frozenset({
            "green_load_caution", "green_load_convergence",
            "acwr", "monotony", "strain", "work_7d", "acute_load_72h_rel",
        }),
    ),
    ("carga reciente no parece alta", frozenset({"acwr"})),
)
_RECOVERY_ECHO_TYPES = frozenset({"recovery_support", "recovery_discordance"})


def _empty_reason_text(gate: str) -> str:
    if gate == VERDE:
        return "VERDE: HRV en rango, sin señales que matizar"
    if gate == AMBAR:
        return f"{AMBAR}: sin señales individuales destacables"
    if gate == ROJO:
        return f"{ROJO}: sin señales individuales destacables"
    return "sin señales que añadir"


def _strip_action_prefix(msg: str) -> str:
    for prefix in (
        "Acción sugerida: ", "Acción recomendada: ",
        "Acción: ", "Acción:",
        "Accion sugerida: ", "Accion recomendada: ",
        "Accion: ", "Accion:",
    ):
        if msg.startswith(prefix):
            return msg[len(prefix):].lstrip()
    return msg


def _filter_redundant_recovery_support(items: List[dict]) -> List[dict]:
    """Filtra echo genéricos de recovery_support|recovery_discordance cuando
    un emisor específico (nightly_discordance, sleep_*, green_load_*, acwr...)
    ya cubre la misma información."""
    types_present = {str(it.get("type", "")) for it in items}
    out: List[dict] = []
    for it in items:
        if str(it.get("type", "")) in _RECOVERY_ECHO_TYPES:
            msg = str(it.get("message", "")).lower()
            if any(
                phrase in msg and (types_present & redundant_with)
                for phrase, redundant_with in _RECOVERY_SUPPORT_REDUNDANT
            ):
                continue
        out.append(it)
    return out


def _compose_reason_text(items: List[dict], gate: str) -> str:
    """Ensamble final del reason_text a partir de reason_items tipados.

    Estructura: `{verdicts " · "}. {whys "; "}. Acción: {actions "; "}`.
    Deduplica por igualdad exacta de mensaje y suprime recovery_support
    cuando un emisor más específico cubre la misma señal.
    """
    if not items:
        return _empty_reason_text(gate)
    items = _filter_redundant_recovery_support(items)
    verdicts: List[str] = []
    whys: List[str] = []
    actions: List[str] = []
    seen: set = set()
    for it in items:
        msg = str(it.get("message", "") or "").strip()
        if not msg or msg in seen:
            continue
        seen.add(msg)
        t = str(it.get("type", ""))
        if t in _ACTION_TYPES:
            actions.append(_strip_action_prefix(msg))
        elif t in _VERDICT_TYPES:
            verdicts.append(msg)
        else:
            whys.append(msg)
    segments: List[str] = []
    if verdicts:
        segments.append(" · ".join(verdicts))
    if whys:
        segments.append("; ".join(whys))
    if actions:
        segments.append("Acción: " + "; ".join(actions))
    if not segments:
        return _empty_reason_text(gate)
    return ". ".join(segments)


def parse_args(argv: List[str]) -> Dict[str, str]:
    out: Dict[str, str] = {}
    i = 0
    while i < len(argv):
        a = argv[i]
        if a in ("--decision-mode",) and i + 1 < len(argv):
            out["decision_mode"] = argv[i+1]
            i += 2
        elif a in ("--data-dir",) and i + 1 < len(argv):
            out["data_dir"] = argv[i+1]
            i += 2
        else:
            i += 1
    return out


# =============================================================================
# Core → Final/Dashboard
# =============================================================================

def build_final_and_dashboard(core: pd.DataFrame, cfg: Config) -> Tuple[pd.DataFrame, pd.DataFrame]:
    df = core.copy()

    # Orden y fechas
    df["Fecha_dt"] = pd.to_datetime(df["Fecha"], format=DATE_FORMAT, errors="coerce")
    df = df.sort_values("Fecha_dt").reset_index(drop=True)
    dates = df["Fecha_dt"].to_numpy(dtype="datetime64[ns]")
    window_start_60 = _window_start_indices(dates, cfg.base60_days)
    window_start_42 = _window_start_indices(dates, cfg.base42_days)
    window_start_28 = _window_start_indices(dates, cfg.base28_days)
    window_end_excl = np.searchsorted(dates, dates, side="left")

    # Señales del día
    ln_today = pd.to_numeric(df["lnRMSSD"], errors="coerce").to_numpy(dtype=float)
    hr_today = pd.to_numeric(df["HR_stable"], errors="coerce").to_numpy(dtype=float)
    rmssd_today = pd.to_numeric(df["RMSSD_stable"], errors="coerce").to_numpy(dtype=float)
    rrbar_s = pd.to_numeric(df["RRbar_s"], errors="coerce").to_numpy(dtype=float)
    ln_today_finite = np.isfinite(ln_today)
    hr_today_finite = np.isfinite(hr_today)
    stability_subtype = (
        df["Stability_Subtype"].astype(str).to_numpy(dtype=object)
        if "Stability_Subtype" in df.columns
        else np.where(df["HRV_Stability"].astype(str).to_numpy(dtype=object) == "OK", "OK", "")
    )
    tail_mismatch_pct = pd.to_numeric(df["tail_mismatch_pct"], errors="coerce").to_numpy(dtype=float) if "tail_mismatch_pct" in df.columns else np.full(len(df), np.nan, dtype=float)

    # Clean / invalid / quality_flag
    is_numeric = np.isfinite(ln_today) & np.isfinite(hr_today) & np.isfinite(rmssd_today)
    is_invalid = (df["Calidad"].astype(str) == "INVALID") | (~is_numeric) | df["Fecha_dt"].isna().to_numpy()
    is_clean = (df["Calidad"].astype(str) == "OK") & is_numeric & (~is_invalid)
    quality_flag = (~is_clean) & (~is_invalid)
    clean_ln_mask = is_clean & ln_today_finite
    clean_hr_mask = is_clean & hr_today_finite

    # ROLL3 (solo clean)
    ln_used = np.full(len(df), np.nan, dtype=float)
    hr_used = np.full(len(df), np.nan, dtype=float)
    n_roll3 = np.zeros(len(df), dtype=int)
    for i in range(len(df)):
        mu_ln, n_ln = last_n_valid_mean(ln_today, is_clean, cfg.roll_n, i)
        mu_hr, n_hr = last_n_valid_mean(hr_today, is_clean, cfg.roll_n, i)
        ln_used[i] = mu_ln
        hr_used[i] = mu_hr
        n_roll3[i] = int(min(n_ln, n_hr))

    # Baselines + SWC (solo clean; shift-1)
    ln_base60 = np.full(len(df), np.nan, dtype=float)
    hr_base60 = np.full(len(df), np.nan, dtype=float)
    n_base60  = np.zeros(len(df), dtype=int)
    swc_ln60  = np.full(len(df), np.nan, dtype=float)
    swc_hr60  = np.full(len(df), np.nan, dtype=float)

    # Sombras: solo n + gate; bases/SWC no se exportan
    n_base42 = np.zeros(len(df), dtype=int)
    n_base28 = np.zeros(len(df), dtype=int)

    # Gates
    gate_base60 = np.array([NO]*len(df), dtype=object)
    razon_base60 = np.array([""]*len(df), dtype=object)
    gate_shadow42 = np.array([NO]*len(df), dtype=object)
    razon_shadow42 = np.array([""]*len(df), dtype=object)
    gate_shadow28 = np.array([NO]*len(df), dtype=object)
    razon_shadow28 = np.array([""]*len(df), dtype=object)
    gate_raw_today = np.array([NO]*len(df), dtype=object)
    gate_raw_reason = np.array([""]*len(df), dtype=object)
    unstable_note = np.array([""]*len(df), dtype=object)

    d_ln = np.full(len(df), np.nan, dtype=float)
    d_hr = np.full(len(df), np.nan, dtype=float)

    # Para residual
    residual_ln = np.full(len(df), np.nan, dtype=float)
    residual_z  = np.full(len(df), np.nan, dtype=float)
    residual_tag_arr = np.array([""]*len(df), dtype=object)
    veto_agudo = np.array([False]*len(df), dtype=bool)
    ln_pre_veto = np.full(len(df), np.nan, dtype=float)
    swc_ln_floor_arr = np.full(len(df), np.nan, dtype=float)
    reason_items: List[List[dict]] = [[] for _ in range(len(df))]
    reason_parts: List[List[str]] = [[] for _ in range(len(df))]

    # Precompute lnRRbar
    ln_rr = np.full(len(df), np.nan, dtype=float)
    with np.errstate(divide="ignore", invalid="ignore"):
        ln_rr = np.log(rrbar_s)
    ln_rr_finite = np.isfinite(ln_rr)

    def _apply_shadow_gate(
        i: int,
        start_idx_arr: np.ndarray,
        min_clean: int,
        gate_arr: np.ndarray,
        reason_arr: np.ndarray,
        n_arr: np.ndarray,
        insufficient_reason: str,
    ) -> None:
        """Aplica la lógica 2D para una ventana sombra sin cambiar semántica."""
        end_idx = int(window_end_excl[i])
        start_idx = int(start_idx_arr[i])
        b_ln, sw_ln, n_ln = _window_stats_range(ln_today, clean_ln_mask, start_idx, end_idx, cfg.swc_mult)
        b_hr, sw_hr, n_hr = _window_stats_range(hr_today, clean_hr_mask, start_idx, end_idx, cfg.swc_mult)
        nb = int(min(n_ln, n_hr))
        n_arr[i] = nb

        if nb < min_clean:
            gate_arr[i] = NO
            reason_arr[i] = insufficient_reason
            return
        if (not np.isfinite(sw_ln)) or (not np.isfinite(sw_hr)) or sw_ln == 0.0 or sw_hr == 0.0:
            gate_arr[i] = NO
            reason_arr[i] = "SWC_NAN/0"
            return

        dln = float(ln_used[i] - b_ln)
        dhr = float(hr_used[i] - b_hr)
        ln_bajo = dln < -sw_ln
        hr_alto = dhr > sw_hr
        if ln_bajo and hr_alto:
            gate_arr[i] = ROJO
            reason_arr[i] = "2D_AMBOS"
        elif ln_bajo:
            gate_arr[i] = AMBAR
            reason_arr[i] = "2D_LN"
        elif hr_alto:
            gate_arr[i] = AMBAR
            reason_arr[i] = "2D_HR"
        else:
            gate_arr[i] = VERDE
            reason_arr[i] = "2D_OK"

    for i in range(len(df)):
        if is_invalid[i]:
            gate_base60[i] = NO
            razon_base60[i] = "CAL/STAB/ART/NaN"
            gate_shadow42[i] = NO; razon_shadow42[i] = "CAL/STAB/ART/NaN"
            gate_shadow28[i] = NO; razon_shadow28[i] = "CAL/STAB/ART/NaN"
            continue

        if n_roll3[i] < cfg.min_roll3_clean:
            gate_base60[i] = NO
            razon_base60[i] = "ROLL3_INSUF"
            gate_shadow42[i] = NO; razon_shadow42[i] = "ROLL3_INSUF"
            gate_shadow28[i] = NO; razon_shadow28[i] = "ROLL3_INSUF"
            continue

        # ===== BASE60 =====
        end60 = int(window_end_excl[i])
        start60 = int(window_start_60[i])
        b_ln, sw_ln, n_ln = _window_stats_range(ln_today, is_clean & ln_today_finite, start60, end60, cfg.swc_mult)
        b_hr, sw_hr, n_hr = _window_stats_range(hr_today, is_clean & hr_today_finite, start60, end60, cfg.swc_mult)
        n60 = int(min(n_ln, n_hr))

        ln_base60[i] = b_ln
        hr_base60[i] = b_hr
        n_base60[i]  = n60
        swc_ln60[i]  = sw_ln
        swc_hr60[i]  = sw_hr

        if n60 < cfg.min_base60_clean:
            gate_base60[i] = NO
            razon_base60[i] = "BASE60_INSUF"
            gate_raw_today[i] = NO
            gate_raw_reason[i] = "BASE60_INSUF"
        elif (not np.isfinite(sw_ln)) or (not np.isfinite(sw_hr)) or sw_ln == 0.0 or sw_hr == 0.0:
            gate_base60[i] = NO
            razon_base60[i] = "SWC_NAN/0"
            gate_raw_today[i] = NO
            gate_raw_reason[i] = "SWC_NAN/0"
        else:
            gate_raw_today[i], gate_raw_reason[i] = eval_gate(ln_today[i], hr_today[i], b_ln, b_hr, sw_ln, sw_hr)
            # ===== VETO AGUDO (v4): bypass ROLL3 si caída aguda =====
            swc_v4 = max(sw_ln, SWC_FLOOR)
            swc_ln_floor_arr[i] = swc_v4

            if (is_clean[i] and np.isfinite(ln_today[i]) and np.isfinite(b_ln)
                and ln_today[i] < (b_ln - VETO_MULT * swc_v4)):
                veto_agudo[i] = True
                ln_pre_veto[i] = ln_used[i]
                ln_used[i] = ln_today[i]
                hr_used[i] = hr_today[i]
                rmssd_today_val = float(np.exp(ln_today[i]))
                rmssd_base_val = float(np.exp(b_ln))
                drop_pct = (
                    (rmssd_today_val - rmssd_base_val) / rmssd_base_val * 100.0
                    if rmssd_base_val > 0 else float("nan")
                )
                drop_suffix = (
                    f" ({rmssd_today_val:.0f} ms vs base {rmssd_base_val:.0f} ms, {drop_pct:+.0f}%)"
                    if np.isfinite(drop_pct) else ""
                )
                _emit_reason(
                    reason_items,
                    reason_parts,
                    i,
                    type="acute_drop",
                    layer="inference",
                    source="hrv_pipeline",
                    metric="lnRMSSD",
                    value=float(ln_today[i]),
                    threshold=float(b_ln - VETO_MULT * swc_v4),
                    message=f"RMSSD de hoy cayó bruscamente respecto a tu base reciente{drop_suffix}: superó el umbral de caída aguda",
                )

            dln = float(ln_used[i] - b_ln)
            dhr = float(hr_used[i] - b_hr)
            d_ln[i] = dln
            d_hr[i] = dhr

            ln_bajo = dln < -sw_ln
            hr_alto = dhr >  sw_hr

            if ln_bajo and hr_alto:
                gate_base60[i] = ROJO
                razon_base60[i] = "2D_AMBOS"
            elif ln_bajo:
                gate_base60[i] = AMBAR
                razon_base60[i] = "2D_LN"
            elif hr_alto:
                gate_base60[i] = AMBAR
                razon_base60[i] = "2D_HR"
            else:
                gate_base60[i] = VERDE
                razon_base60[i] = "2D_OK"

            if bool(quality_flag[i]) and gate_raw_today[i] in (VERDE, AMBAR, ROJO):
                unstable_note[i] = f"Raw={gate_raw_today[i]}({gate_raw_reason[i]}) vs ref={gate_base60[i]}({razon_base60[i]})"

        # ===== SHADOW42 / SHADOW28 =====
        _apply_shadow_gate(i, window_start_42, cfg.min_base42_clean, gate_shadow42, razon_shadow42, n_base42, "BASE42_INSUF")
        _apply_shadow_gate(i, window_start_28, cfg.min_base28_clean, gate_shadow28, razon_shadow28, n_base28, "BASE28_INSUF")

        # ===== RESIDUAL (BASE60) =====
        # Fit OLS y = a + b*x en ventana BASE60 (shift-1) sobre días clean
        # x = ln(RRbar_s), y = lnRMSSD_today
        mfit = is_clean[start60:end60] & ln_rr_finite[start60:end60] & ln_today_finite[start60:end60]
        if np.sum(mfit) >= cfg.min_base60_clean and np.isfinite(ln_rr[i]) and np.isfinite(ln_today[i]):
            x = ln_rr[start60:end60][mfit].astype(float)
            y = ln_today[start60:end60][mfit].astype(float)
            X = np.column_stack([np.ones_like(x), x])
            try:
                coef, *_ = np.linalg.lstsq(X, y, rcond=None)
                a, b = float(coef[0]), float(coef[1])
                yhat_i = a + b * float(ln_rr[i])
                residual_ln[i] = float(ln_today[i] - yhat_i)

                # residual scale (robusta) usando residuales de entrenamiento
                resid_train = y - (a + b * x)
                sd_res = robust_sd(resid_train)
                swc_res = cfg.swc_mult * sd_res if np.isfinite(sd_res) else float("nan")
                if np.isfinite(swc_res) and swc_res != 0.0:
                    residual_z[i] = float(residual_ln[i] / swc_res)
                    residual_tag_arr[i] = residual_tag(residual_z[i], cfg)
            except Exception as exc:
                log.warning("Residual calculation failed for %s: %s", df.iloc[i]["Fecha"], exc)
        # else: residual NaN

    # =============================================================================
    # Decision mode (O2 vs O3)
    # =============================================================================

    decision_mode = cfg.decision_mode
    gate_final = gate_base60.copy()
    gate_final_delta = np.zeros(len(df), dtype=int)
    decision_path = np.array(["BASE60_ONLY"]*len(df), dtype=object)
    override_reason = np.array([""]*len(df), dtype=object)

    def shadow_pick(j: int) -> Tuple[Optional[str], Optional[int]]:
        """Devuelve (gate, src_window) donde src_window es 28 o 42."""
        g28 = gate_shadow28[j]
        if g28 in (VERDE, AMBAR, ROJO):
            return (g28, 28)
        g42 = gate_shadow42[j]
        if g42 in (VERDE, AMBAR, ROJO):
            return (g42, 42)
        return (None, None)

    if decision_mode == "O3_OVERRIDE_PERSIST_2of3":
        for i in range(len(df)):
            gb = gate_base60[i]
            if gb not in (VERDE, AMBAR, ROJO):
                continue  # NO no se sobreescribe
            if i < 2:
                continue

            # Ventana S = {i-2, i-1, i}
            S = [i-2, i-1, i]
            worse_days = []
            better_days = []
            for j in S:
                sp, src = shadow_pick(j)
                if sp is None:
                    continue
                r_sp = _rank_gate(sp)
                r_gb = _rank_gate(gate_base60[j])
                if r_sp is None or r_gb is None:
                    continue
                if r_sp > r_gb:
                    worse_days.append(src)
                elif r_sp < r_gb:
                    better_days.append(src)

            persist_down = (len(worse_days) >= 2)
            persist_up   = (len(better_days) >= 2)

            if persist_down and persist_up:
                continue  # conflicto: no override
            if persist_down:
                gate_final[i] = _downgrade(gb, 1)
                gate_final_delta[i] = -1
                src_pick = 28 if worse_days.count(28) >= worse_days.count(42) else 42
                decision_path[i] = f"OVERRIDE_DOWN_{src_pick}_2of3"
                override_reason[i] = f"shadow{src_pick} peor 2/3"
            elif persist_up:
                gate_final[i] = _upgrade(gb, 1)
                gate_final_delta[i] = +1
                src_pick = 28 if better_days.count(28) >= better_days.count(42) else 42
                decision_path[i] = f"OVERRIDE_UP_{src_pick}_2of3"
                override_reason[i] = f"shadow{src_pick} mejor 2/3"

    elif decision_mode == "O2_SHADOW":
        pass
    else:
        raise ValueError("decision_mode inválido. Usa O2_SHADOW u O3_OVERRIDE_PERSIST_2of3.")

    # =============================================================================
    # Badge (gate + residual_tag)
    # =============================================================================
    gate_badge = np.array([str(g) + str(t) for g, t in zip(gate_final, residual_tag_arr)], dtype=object)

    # =============================================================================
    # Acción operativa + acumulación
    # =============================================================================
    Color_operativo = gate_final.copy()

    Action = np.array(["SUAVE_O_DESCANSO"]*len(df), dtype=object)
    Action_detail = np.array(["SUAVE"]*len(df), dtype=object)

    for i in range(len(df)):
        gf = gate_final[i]
        qf = bool(quality_flag[i])
        if gf == VERDE and not qf:
            Action[i] = "INTENSIDAD_OK"
            Action_detail[i] = "EJECUTAR_PLAN"
        elif gf == AMBAR and not qf:
            Action[i] = "Z2_O_TEMPO_SUAVE"
            Action_detail[i] = "SIN_HIIT"
        else:
            Action[i] = "SUAVE_O_DESCANSO"
            if qf and (gf in (VERDE, AMBAR, ROJO)):
                Action_detail[i] = "SUAVE_QUALITY"
            else:
                Action_detail[i] = "SUAVE"

    # bad_streak / bad_7d solo sobre ROJO.
    # NO significa "sin datos suficientes para decidir" y no debe inflar acumulación.
    bad_streak = np.zeros(len(df), dtype=int)
    for i in range(len(df)):
        if gate_final[i] == ROJO:
            bad_streak[i] = (bad_streak[i-1] + 1) if i > 0 else 1
        else:
            bad_streak[i] = 0

    bad_7d = np.zeros(len(df), dtype=int)
    for i in range(len(df)):
        lo = max(0, i-6)
        bad_7d[i] = int(np.sum(gate_final[lo:i+1] == ROJO))

    # Ajuste Action_detail por acumulación (solo para ROJO y sin SUAVE_QUALITY)
    for i in range(len(df)):
        if Action_detail[i] == "SUAVE_QUALITY":
            continue
        if gate_final[i] == ROJO and (bad_streak[i] >= 2 or bad_7d[i] >= 3):
            Action_detail[i] = "DESCARGA"

    # =============================================================================
    # REASON_TEXT (contextual)
    # =============================================================================

    # --- Sleep context from sleep.csv (Polar sleep/nightly only) ---
    sleep_lookup: Optional[pd.DataFrame] = None
    sleep_path = DATA_DIR / "ENDURANCE_HRV_sleep.csv"
    if sleep_path.exists():
        try:
            sleep_df = pd.read_csv(sleep_path)
            if "Fecha" in sleep_df.columns:
                sleep_df["Fecha"] = sleep_df["Fecha"].astype(str)
                sleep_df = sleep_df.drop_duplicates(subset=["Fecha"], keep="last")
                sleep_lookup = sleep_df.set_index("Fecha")
        except (OSError, ValueError, KeyError) as exc:
            log.warning("Sleep context unavailable from %s: %s", sleep_path, exc)
            sleep_lookup = None

    # --- SSM shadow context (informative only) ---
    ssm_lookup: Optional[pd.DataFrame] = None
    if SSM_SHADOW_PATH.exists():
        try:
            ssm_df = pd.read_csv(SSM_SHADOW_PATH)
            if "Fecha" in ssm_df.columns:
                ssm_df["Fecha"] = ssm_df["Fecha"].astype(str)
                ssm_df = ssm_df.drop_duplicates(subset=["Fecha"], keep="last")
                ssm_lookup = ssm_df.set_index("Fecha")
        except (OSError, ValueError, KeyError) as exc:
            log.warning("SSM context unavailable from %s: %s", SSM_SHADOW_PATH, exc)
            ssm_lookup = None

    # --- Training load from sessions_day.csv (generated by build_sessions.py) ---
    sday_lookup: Optional[pd.DataFrame] = None
    load_ctx_lookup: Optional[pd.DataFrame] = None
    clustering_lookup: Optional[pd.DataFrame] = None
    load_ctx_threshold_lookup: Optional[pd.DataFrame] = None
    sday_path = DATA_DIR / "ENDURANCE_HRV_sessions_day.csv"
    if sday_path.exists():
        try:
            sday_df = pd.read_csv(sday_path)
            sday_lookup, load_ctx_lookup, clustering_lookup, load_ctx_threshold_lookup = _build_sessions_day_lookups(sday_df)
        except (OSError, ValueError, KeyError) as exc:
            log.warning("Sessions context unavailable from %s: %s", sday_path, exc)
            sday_lookup = None
            load_ctx_lookup = None
            clustering_lookup = None
            load_ctx_threshold_lookup = None

    recovery_context_quality = np.array(["none"] * len(df), dtype=object)
    recovery_support_class = np.array(["neutral"] * len(df), dtype=object)
    recovery_discordance_flag = np.array([False] * len(df), dtype=bool)
    recovery_discordance_reason = np.array([""] * len(df), dtype=object)

    for i in range(len(df)):
        fecha = str(df.iloc[i]["Fecha"])
        verde_load_72h_caution = False
        sleep_bad = False
        sleep_basic_signal = False
        sleep_score = None
        night_rmssd = None
        night_rmssd_low_text = ""
        night_rmssd_high_text = ""
        load_3d = None
        load_3d_nobs = None
        acute_load_72h_rel = None
        acute_load_72h_rel_p75 = ACUTE_LOAD_72H_REL_HIGH_FALLBACK
        acute_load_72h_rel_p90 = ACUTE_LOAD_72H_REL_VERY_HIGH_FALLBACK
        recent_load_available = False
        recent_load_low = False
        load_ctx_caution = False
        load_ctx_caution_sources: List[str] = []
        load_ctx_ready = False
        clustering_flag = False
        support_codes: List[str] = []
        caution_codes: List[str] = []

        # Saturación parasimpática
        if np.isfinite(d_ln[i]) and np.isfinite(swc_ln_floor_arr[i]):
            if d_ln[i] > 2 * swc_ln_floor_arr[i]:
                _emit_reason(
                    reason_items,
                    reason_parts,
                    i,
                    type="parasympathetic_saturation",
                    layer="inference",
                    source="hrv_pipeline",
                    metric="d_ln",
                    value=float(d_ln[i]),
                    threshold=float(2 * swc_ln_floor_arr[i]),
                    message="RMSSD suavizado de 3 días por encima de tu base reciente: posible saturación parasimpática relativa al rango local",
                )

        # Quality override
        if quality_flag[i] and gate_final[i] in (VERDE, AMBAR):
            artifact_pct = _safe_float(df.iloc[i], "Artifact_pct")
            tiemp_est = _safe_float(df.iloc[i], "Tiempo_Estabilizacion")
            data_quality_evidence = []
            if tiemp_est is not None:
                data_quality_evidence.append(f"Tiempo_Estabilizacion={tiemp_est:.0f}s")
            _emit_reason(
                reason_items,
                reason_parts,
                i,
                type="data_quality",
                layer="measured",
                source="hrv_pipeline",
                gate_scope="green_or_amber",
                metric="Artifact_pct",
                value=float(artifact_pct) if artifact_pct is not None else None,
                threshold=15.0,
                evidence=data_quality_evidence,
                message="Dato dudoso: limitar a Z1-Z2 máx 90min",
            )

        # ── Sleep checks (from sleep.csv) ──
        if sleep_lookup is not None and fecha in sleep_lookup.index:
            sleep_row = sleep_lookup.loc[fecha]
            if isinstance(sleep_row, pd.DataFrame):
                sleep_row = sleep_row.iloc[-1]

            sleep_dur = _safe_float(sleep_row, "polar_sleep_duration_min")
            sleep_int = _safe_float(sleep_row, "polar_interruptions_long")
            sleep_dur_p10 = _safe_float(sleep_row, "sleep_dur_p10")
            sleep_int_p90 = _safe_float(sleep_row, "sleep_int_p90")
            sleep_basic_signal = (
                (sleep_dur is not None and sleep_dur_p10 is not None)
                or (sleep_int is not None and sleep_int_p90 is not None)
            )

            if sleep_dur is not None and sleep_dur_p10 is not None and sleep_dur < sleep_dur_p10:
                _emit_reason(
                    reason_items,
                    reason_parts,
                    i,
                    type="sleep_duration",
                    layer="inference",
                    source="sleep",
                    metric="polar_sleep_duration_min",
                    value=float(sleep_dur),
                    threshold=float(sleep_dur_p10),
                    message=(
                        f"Sueño más corto de lo habitual ({_format_minutes_human(sleep_dur)} "
                        f"vs tu umbral habitual bajo de {_format_minutes_human(sleep_dur_p10)})"
                    ),
                )
                sleep_bad = True
                _append_unique(caution_codes, "sleep_basic_poor")
            if sleep_int is not None and sleep_int_p90 is not None and sleep_int > sleep_int_p90:
                _emit_reason(
                    reason_items,
                    reason_parts,
                    i,
                    type="sleep_fragmentation",
                    layer="inference",
                    source="sleep",
                    metric="polar_interruptions_long",
                    value=float(sleep_int),
                    threshold=float(sleep_int_p90),
                    message=(
                        f"Sueño más fragmentado de lo habitual ({sleep_int:.0f} interrupciones; "
                        f"habitualmente no pasas de {sleep_int_p90:.0f})"
                    ),
                )
                sleep_bad = True
                _append_unique(caution_codes, "sleep_basic_poor")
            if sleep_basic_signal and not sleep_bad:
                _append_unique(support_codes, "sleep_basic_ok")

            sleep_score = _safe_float(sleep_row, "polar_sleep_score")
            if sleep_score is not None:
                if sleep_score <= 65:
                    _append_unique(caution_codes, "sleep_score_low")
                elif sleep_score >= 75:
                    _append_unique(support_codes, "sleep_score_good")

            # Nightly RMSSD discordancia
            night_rmssd = _safe_float(sleep_row, "polar_night_rmssd")
            if night_rmssd is not None:
                if gate_final[i] == VERDE and night_rmssd < 25:
                    night_rmssd_low_text = (
                        f"VERDE, pero el HRV nocturno fue bajo ({night_rmssd:.0f}ms): "
                        "la recuperación durante el sueño no acompaña"
                    )
                elif gate_final[i] == ROJO and night_rmssd > 45:
                    night_rmssd_high_text = (
                        f"ROJO, pero el HRV de sueño salió alto ({night_rmssd:.0f}ms): "
                        "la recuperación nocturna fue mejor de lo esperado"
                    )
                if night_rmssd < 30:
                    _append_unique(caution_codes, "nightly_rmssd_low")
                elif night_rmssd >= 40:
                    _append_unique(support_codes, "nightly_rmssd_good")
        else:
            sleep_dur = None
            sleep_dur_p10 = None
            sleep_int = None
            sleep_int_p90 = None

        load_ctx_row = None
        clustering_row = None
        load_ctx_threshold_row = None
        if load_ctx_lookup is not None and fecha in load_ctx_lookup.index:
            load_ctx_row = load_ctx_lookup.loc[fecha]
            if isinstance(load_ctx_row, pd.DataFrame):
                load_ctx_row = load_ctx_row.iloc[-1]
            load_ctx_ready = str(load_ctx_row.get("load_ctx_ready", "")).lower() in {"true", "1"}
        if load_ctx_threshold_lookup is not None and fecha in load_ctx_threshold_lookup.index:
            load_ctx_threshold_row = load_ctx_threshold_lookup.loc[fecha]
            if isinstance(load_ctx_threshold_row, pd.DataFrame):
                load_ctx_threshold_row = load_ctx_threshold_row.iloc[-1]
        if clustering_lookup is not None and fecha in clustering_lookup.index:
            clustering_row = clustering_lookup.loc[fecha]
            if isinstance(clustering_row, pd.DataFrame):
                clustering_row = clustering_row.iloc[-1]

        # ── Training load checks (from sessions_day.csv) ──
        if sday_lookup is not None and fecha in sday_lookup.index:
            sday_row = sday_lookup.loc[fecha]
            if isinstance(sday_row, pd.DataFrame):
                sday_row = sday_row.iloc[-1]

            load_3d = _safe_float(sday_row, "load_3d")
            load_3d_nobs = _safe_float(sday_row, "load_3d_nobs")
            acute_load_72h_rel = _safe_float(sday_row, "acute_load_72h_rel")
            work_7d = _safe_float(sday_row, "work_7d_sum")
            z3_7d = _safe_float(sday_row, "z3_7d_sum")
            recent_load_available = _has_strict_previous_load(load_3d, load_3d_nobs)
            recent_load_low = recent_load_available and load_3d is not None and load_3d < 30

            if load_ctx_threshold_row is not None:
                acute_load_72h_rel_p75_row = _safe_float(load_ctx_threshold_row, "acute_load_72h_rel_p75")
                acute_load_72h_rel_p90_row = _safe_float(load_ctx_threshold_row, "acute_load_72h_rel_p90")
                if acute_load_72h_rel_p75_row is not None:
                    acute_load_72h_rel_p75 = acute_load_72h_rel_p75_row
                if acute_load_72h_rel_p90_row is not None:
                    acute_load_72h_rel_p90 = acute_load_72h_rel_p90_row

            # Relative acute-load warning; only interpret it when the chronic
            # context is ready enough to make the ratio meaningful.
            if load_ctx_ready and acute_load_72h_rel is not None:
                if acute_load_72h_rel >= acute_load_72h_rel_p90:
                    _emit_reason(
                        reason_items,
                        reason_parts,
                        i,
                        type="acute_load_72h_rel",
                        layer="inference",
                        source="sessions_day",
                        variant="high",
                        severity="very_high",
                        metric="acute_load_72h_rel",
                        value=float(acute_load_72h_rel),
                        threshold=float(acute_load_72h_rel_p90),
                        message=(
                            "Carga aguda 72h muy alta respecto a tu base crónica "
                            f"(acute_load_72h_rel={acute_load_72h_rel:.2f}x; load_3d={load_3d:.0f})"
                        ),
                    )
                    load_ctx_caution = True
                    load_ctx_caution_sources.append("carga 72h")
                    _append_unique(caution_codes, "load_context_high")
                elif acute_load_72h_rel >= acute_load_72h_rel_p75:
                    _emit_reason(
                        reason_items,
                        reason_parts,
                        i,
                        type="acute_load_72h_rel",
                        layer="inference",
                        source="sessions_day",
                        variant="high",
                        severity="high",
                        metric="acute_load_72h_rel",
                        value=float(acute_load_72h_rel),
                        threshold=float(acute_load_72h_rel_p75),
                        message=(
                            "Carga aguda 72h por encima de tu base crónica "
                            f"(acute_load_72h_rel={acute_load_72h_rel:.2f}x; load_3d={load_3d:.0f})"
                        ),
                    )
                    load_ctx_caution = True
                    load_ctx_caution_sources.append("carga 72h")
                    _append_unique(caution_codes, "load_context_high")

            if work_7d is not None and work_7d > WORK_7D_HIGH:
                _emit_reason(
                    reason_items,
                    reason_parts,
                    i,
                    type="work_7d",
                    layer="inference",
                    source="sessions_day",
                    variant="high",
                    metric="work_7d_sum",
                    value=float(work_7d),
                    threshold=float(WORK_7D_HIGH),
                    message=f"Volumen de trabajo semanal alto (work_7d={work_7d:.0f}min, alto)",
                )
            if z3_7d is not None and z3_7d > Z3_7D_HIGH:
                _emit_reason(
                    reason_items,
                    reason_parts,
                    i,
                    type="z3_7d",
                    layer="inference",
                    source="sessions_day",
                    variant="high",
                    metric="z3_7d_sum",
                    value=float(z3_7d),
                    threshold=float(Z3_7D_HIGH),
                    message=f"Tiempo acumulado en Z3 esta semana ({z3_7d:.0f}min en Z3)",
                )

            # ROJO sin carga previa
            if gate_final[i] == ROJO:
                if recent_load_low:
                    if sleep_basic_signal and not sleep_bad:
                        _emit_reason(
                            reason_items,
                            reason_parts,
                            i,
                            type="contradiction",
                            layer="inference",
                            source="sessions_day",
                            gate_scope="red",
                            message="ROJO sin carga previa reciente ni sueño malo: revisar factores externos al entrenamiento",
                        )
                    elif not sleep_basic_signal:
                        _emit_reason(
                            reason_items,
                            reason_parts,
                            i,
                            type="recent_load_absence",
                            layer="inference",
                            source="sessions_day",
                            gate_scope="red",
                            message="ROJO sin carga previa reciente: revisar factores externos al entrenamiento",
                        )
                elif not recent_load_available:
                    load_message = "ROJO con carga no disponible"
                    if sleep_basic_signal and not sleep_bad:
                        load_message = "ROJO con carga no disponible y sueño no malo"
                    _emit_reason(
                        reason_items,
                        reason_parts,
                        i,
                        type="recent_load_absence",
                        layer="inference",
                        source="sessions_day",
                        gate_scope="red",
                        message=f"{load_message}: revisar factores externos al entrenamiento",
                    )

            if (
                gate_final[i] == VERDE
                and load_ctx_ready
                and acute_load_72h_rel is not None
                and acute_load_72h_rel >= acute_load_72h_rel_p75
            ):
                verde_load_72h_caution = True

        if clustering_row is not None:
            clustering_flag_num = _safe_float(clustering_row, "intensity_clustering_flag")
            clustering_flag = (
                str(clustering_row.get("intensity_clustering_flag", "")).strip().lower() in {"1", "true"}
                or (clustering_flag_num is not None and clustering_flag_num >= 0.5)
            )
            clustering_level = str(clustering_row.get("intensity_clustering_level", "")).strip().lower()
            intense_days_prev_3d = _safe_float(clustering_row, "intense_days_prev_3d")
            intense_days_prev_5d = _safe_float(clustering_row, "intense_days_prev_5d")

            if clustering_flag:
                _append_unique(caution_codes, "intensity_clustering")
                clustering_window_clause = _build_clustering_window_clause(
                    intense_days_prev_3d,
                    intense_days_prev_5d,
                )
                clustering_window_suffix = _build_clustering_window_suffix(
                    intense_days_prev_3d,
                    intense_days_prev_5d,
                )

                if gate_final[i] == VERDE:
                    if (
                        intense_days_prev_3d is not None
                        and intense_days_prev_3d >= 2
                    ):
                        clustering_msg = (
                            f"VERDE pero con {clustering_window_clause}: conviene prudencia con la intensidad"
                        )
                    elif (
                        intense_days_prev_5d is not None
                        and intense_days_prev_5d >= 2
                    ):
                        clustering_msg = (
                            f"VERDE pero con {clustering_window_clause}: conviene prudencia con la intensidad"
                        )
                    elif clustering_level == "high":
                        clustering_msg = "VERDE pero con intensidad reciente muy agrupada: conviene prudencia con la intensidad"
                    else:
                        clustering_msg = "VERDE pero con intensidad reciente acumulada: conviene prudencia con la intensidad"
                else:
                    if clustering_level == "high":
                        clustering_msg = "Intensidad reciente muy agrupada: vigilar recuperación"
                    else:
                        clustering_msg = "Intensidad reciente agrupada: vigilar recuperación"

                if gate_final[i] != VERDE and clustering_window_suffix:
                    clustering_msg = f"{clustering_msg} ({clustering_window_suffix})"
                _emit_reason(
                    reason_items,
                    reason_parts,
                    i,
                    type="intensity_clustering",
                    layer="inference",
                    source="sessions_day",
                    variant="high" if clustering_level == "high" else "recent",
                    metric="intensity_clustering_flag",
                    value=int(bool(clustering_flag)),
                    message=clustering_msg,
                )

        if load_ctx_row is not None:
            acwr_simple_prev = _safe_float(load_ctx_row, "acwr_simple_prev")
            monotony_7d_prev = _safe_float(load_ctx_row, "monotony_7d_prev")
            strain_7d_prev = _safe_float(load_ctx_row, "strain_7d_prev")
            if load_ctx_ready and acwr_simple_prev is not None:
                if acwr_simple_prev >= 1.5:
                    _emit_reason(
                        reason_items,
                        reason_parts,
                        i,
                        type="acwr",
                        layer="inference",
                        source="sessions_day",
                        variant="high",
                        severity="very_high",
                        metric="acwr_simple_prev",
                        value=float(acwr_simple_prev),
                        threshold=1.5,
                        message=(
                            "Carga reciente muy por encima de tu base habitual "
                            f"(ACWR={acwr_simple_prev:.2f}, muy alta)"
                        ),
                    )
                    load_ctx_caution = True
                    load_ctx_caution_sources.append("ACWR")
                    _append_unique(caution_codes, "load_context_high")
                elif acwr_simple_prev >= 1.3:
                    _emit_reason(
                        reason_items,
                        reason_parts,
                        i,
                        type="acwr",
                        layer="inference",
                        source="sessions_day",
                        variant="high",
                        severity="high",
                        metric="acwr_simple_prev",
                        value=float(acwr_simple_prev),
                        threshold=1.3,
                        message=(
                            "Carga reciente por encima de tu base habitual "
                            f"(ACWR={acwr_simple_prev:.2f}, alta)"
                        ),
                    )
                    load_ctx_caution = True
                    load_ctx_caution_sources.append("ACWR")
                    _append_unique(caution_codes, "load_context_high")
                elif acwr_simple_prev <= 0.8:
                    _emit_reason(
                        reason_items,
                        reason_parts,
                        i,
                        type="acwr",
                        layer="inference",
                        source="sessions_day",
                        variant="low",
                        metric="acwr_simple_prev",
                        value=float(acwr_simple_prev),
                        threshold=0.8,
                        message=(
                            "Carga reciente baja frente a tu base habitual "
                            f"(ACWR={acwr_simple_prev:.2f}, baja)"
                        ),
                    )

            if load_ctx_ready and monotony_7d_prev is not None:
                if monotony_7d_prev >= 2.0:
                    _emit_reason(
                        reason_items,
                        reason_parts,
                        i,
                        type="monotony",
                        layer="inference",
                        source="sessions_day",
                        variant="high",
                        severity="high",
                        metric="monotony_7d_prev",
                        value=float(monotony_7d_prev),
                        threshold=2.0,
                        message=(
                            "Semana muy repetitiva, con poca variación de carga "
                            f"(monotonía={monotony_7d_prev:.2f}, alta)"
                        ),
                    )
                    load_ctx_caution = True
                    load_ctx_caution_sources.append("monotonía")
                    _append_unique(caution_codes, "load_context_high")
                elif monotony_7d_prev >= 1.8:
                    _emit_reason(
                        reason_items,
                        reason_parts,
                        i,
                        type="monotony",
                        layer="inference",
                        source="sessions_day",
                        variant="elevated",
                        severity="medium",
                        metric="monotony_7d_prev",
                        value=float(monotony_7d_prev),
                        threshold=1.8,
                        message=(
                            "Semana algo repetitiva; conviene variar más la carga "
                            f"(monotonía={monotony_7d_prev:.2f}, moderada)"
                        ),
                    )
                    load_ctx_caution = True
                    load_ctx_caution_sources.append("monotonía")
                    _append_unique(caution_codes, "load_context_high")

            if load_ctx_ready and strain_7d_prev is not None and load_ctx_threshold_row is not None:
                strain_p90 = _safe_float(load_ctx_threshold_row, "strain_p90")
                strain_p75 = _safe_float(load_ctx_threshold_row, "strain_p75")
                if strain_p90 is not None and strain_7d_prev >= strain_p90:
                    _emit_reason(
                        reason_items,
                        reason_parts,
                        i,
                        type="strain",
                        layer="inference",
                        source="sessions_day",
                        variant="high",
                        severity="very_high",
                        metric="strain_7d_prev",
                        value=float(strain_7d_prev),
                        threshold=float(strain_p90),
                        message=(
                            "Semana muy exigente y con poca descarga "
                            f"(strain={strain_7d_prev:.0f}, muy elevado)"
                        ),
                    )
                    load_ctx_caution = True
                    load_ctx_caution_sources.append("strain")
                    _append_unique(caution_codes, "load_context_high")
                elif strain_p75 is not None and strain_7d_prev >= strain_p75:
                    _emit_reason(
                        reason_items,
                        reason_parts,
                        i,
                        type="strain",
                        layer="inference",
                        source="sessions_day",
                        variant="high",
                        severity="high",
                        metric="strain_7d_prev",
                        value=float(strain_7d_prev),
                        threshold=float(strain_p75),
                        message=(
                            "Semana exigente y algo cargada "
                            f"(strain={strain_7d_prev:.0f}, elevado)"
                        ),
                    )
                    load_ctx_caution = True
                    load_ctx_caution_sources.append("strain")
                    _append_unique(caution_codes, "load_context_high")

            if gate_final[i] == VERDE:
                unique_sources = list(dict.fromkeys(load_ctx_caution_sources))
                if verde_load_72h_caution and load_ctx_caution and len(unique_sources) > 1:
                    convergence_sources = [source for source in unique_sources if source != "carga 72h"]
                    _emit_reason(
                        reason_items,
                        reason_parts,
                        i,
                        type="green_load_convergence",
                        layer="inference",
                        source="sessions_day",
                        gate_scope="green",
                        codes=unique_sources,
                        message=(
                            "VERDE con convergencia de carga "
                            f"(carga 72h + {' + '.join(convergence_sources)}): precaución con la intensidad reforzada"
                        ),
                    )
                elif verde_load_72h_caution:
                    _emit_reason(
                        reason_items,
                        reason_parts,
                        i,
                        type="green_load_caution",
                        layer="inference",
                        source="sessions_day",
                        gate_scope="green",
                        metric="acute_load_72h_rel",
                        value=float(acute_load_72h_rel),
                        threshold=float(acute_load_72h_rel_p75),
                        message=(
                            "VERDE con carga aguda 72h "
                            f"(acute_load_72h_rel={acute_load_72h_rel:.2f}x; load_3d={load_3d:.0f}): "
                            "precaución con la intensidad"
                        ),
                    )
                elif load_ctx_caution:
                    _emit_reason(
                        reason_items,
                        reason_parts,
                        i,
                        type="green_load_caution",
                        layer="inference",
                        source="sessions_day",
                        gate_scope="green",
                        codes=load_ctx_caution_sources,
                        message=(
                            "VERDE con contexto de carga exigente "
                            f"({' + '.join(load_ctx_caution_sources)}): conviene prudencia con la intensidad"
                        ),
                    )
        elif gate_final[i] == VERDE and verde_load_72h_caution:
            _emit_reason(
                reason_items,
                reason_parts,
                i,
                type="green_load_caution",
                layer="inference",
                source="sessions_day",
                gate_scope="green",
                metric="acute_load_72h_rel",
                value=float(acute_load_72h_rel),
                threshold=float(acute_load_72h_rel_p75),
                message=(
                    "VERDE con carga aguda 72h "
                    f"(acute_load_72h_rel={acute_load_72h_rel:.2f}x; load_3d={load_3d:.0f}): "
                    "precaución con la intensidad"
                ),
            )

        if (
            gate_final[i] in (AMBAR, ROJO)
            and recent_load_low
            and not load_ctx_caution
            and not clustering_flag
            and (acute_load_72h_rel is None or acute_load_72h_rel < acute_load_72h_rel_p75)
        ):
            _append_unique(support_codes, "recent_load_low")

        coverage = _recovery_context_quality(
            has_basic_sleep=sleep_basic_signal,
            has_load_signal=(sday_lookup is not None and fecha in sday_lookup.index) or load_ctx_row is not None or clustering_row is not None,
            has_rich_sleep=(sleep_score is not None or night_rmssd is not None),
        )
        recovery_class, recovery_is_discordant = _classify_recovery_support(
            gate=gate_final[i],
            coverage=coverage,
            support_codes=support_codes,
            caution_codes=caution_codes,
        )
        recovery_summary = _recovery_summary_message(
            gate=gate_final[i],
            recovery_class=recovery_class,
            support_codes=support_codes,
            caution_codes=caution_codes,
        )
        recovery_action = _recovery_action_message(
            gate=gate_final[i],
            recovery_class=recovery_class,
            support_codes=support_codes,
            caution_codes=caution_codes,
        )
        # SYA-17 Fase 1: bloque latente, disabled-by-design.
        # La validación concluyó no_go (rho ~0.10, EWMA empata, advantage no estable en walk-forward).
        # Además este bloque no respeta sport_family (bike y run tienen señales distintas).
        # Se preserva el código tras feature flag para Fase 2; activar solo cuando haya evidencia
        # validada por deporte. Default: deshabilitado.
        if (
            os.environ.get("HRV_SSM_REASON_TEXT_ENABLED", "0") == "1"
            and ssm_lookup is not None
            and fecha in ssm_lookup.index
        ):
            ssm_row = ssm_lookup.loc[fecha]
            if isinstance(ssm_row, pd.DataFrame):
                ssm_row = ssm_row.iloc[-1]
            ssm_state = _safe_float(ssm_row, "ssm_recovery_state")
            ssm_state_sd = _safe_float(ssm_row, "ssm_state_sd")
            ssm_input_quality = str(ssm_row.get("ssm_input_quality", "")).strip().lower()
            ssm_innovation = _safe_float(ssm_row, "ssm_innovation")
            ssm_rolling = _safe_float(ssm_row, "control_rolling_hrv_7d")
            ssm_confident = (
                ssm_state is not None
                and ssm_state_sd is not None
                and ssm_state_sd < 0.08
                and ssm_input_quality == "clean"
                and ssm_innovation is not None
                and abs(ssm_innovation) < 0.12
            )
            if ssm_confident and ssm_state is not None and ssm_rolling is not None and abs(ssm_state - ssm_rolling) >= 0.08:
                if ssm_state >= ssm_rolling:
                    ssm_message = (
                        f"SSM limpio y estable: ve más margen de recuperación ({ssm_state:.2f}) que el rolling "
                        f"({ssm_rolling:.2f}); el promedio reciente puede estar siendo conservador."
                    )
                else:
                    ssm_message = (
                        f"SSM limpio y estable: ve menos margen de recuperación ({ssm_state:.2f}) que el rolling "
                        f"({ssm_rolling:.2f}); el promedio reciente puede estar siendo algo optimista."
                    )
                _emit_reason(
                    reason_items,
                    reason_parts,
                    i,
                    type="ssm_context",
                    layer="inference",
                    source="ssm_shadow",
                    metric="ssm_recovery_state",
                    value=float(ssm_state),
                    threshold=float(ssm_rolling),
                    message=ssm_message,
                )
        # Un nightly_rmssd bajo aislado en un VERDE no abre mensaje por sí solo:
        # RE-01 exige convergencia real para no sobrerreaccionar a un sidecar nocturno único.
        if night_rmssd_low_text and recovery_class == "fragile":
            _emit_reason(
                reason_items,
                reason_parts,
                i,
                type="nightly_discordance",
                layer="inference",
                source="sleep",
                gate_scope="green",
                message=night_rmssd_low_text,
            )
        if night_rmssd_high_text and recovery_class == "conflicted":
            _emit_reason(
                reason_items,
                reason_parts,
                i,
                type="nightly_discordance",
                layer="inference",
                source="sleep",
                gate_scope="red",
                message=night_rmssd_high_text,
            )
        if recovery_summary:
            _emit_reason(
                reason_items,
                reason_parts,
                i,
                type="recovery_support",
                layer="inference",
                source="sleep+sessions_day",
                variant=recovery_class,
                gate_scope=str(gate_final[i]).lower(),
                codes=caution_codes if recovery_is_discordant else support_codes,
                message=recovery_summary,
            )
        if recovery_action:
            _emit_reason(
                reason_items,
                reason_parts,
                i,
                type="action_constraint",
                layer="action",
                source="gate_final",
                variant=recovery_class,
                gate_scope=str(gate_final[i]).lower(),
                codes=caution_codes if recovery_is_discordant else support_codes,
                message=recovery_action,
            )
        if recovery_is_discordant:
            discordance_codes = caution_codes if recovery_class == "fragile" else support_codes
            discordance_message = _recovery_discordance_message(
                str(gate_final[i]),
                recovery_class,
                coverage,
                recovery_summary,
            )
            _emit_reason(
                reason_items,
                reason_parts,
                i,
                type="recovery_discordance",
                layer="inference",
                source="sleep+sessions_day",
                variant=recovery_class,
                codes=discordance_codes,
                message=discordance_message,
            )

        discordance_codes = caution_codes if recovery_class == "fragile" else support_codes
        recovery_context_quality[i] = coverage
        recovery_support_class[i] = recovery_class
        recovery_discordance_flag[i] = recovery_is_discordant
        recovery_discordance_reason[i] = "|".join(discordance_codes if recovery_is_discordant else [])

    reason_text = np.array(
        [
            _compose_reason_text(reason_items[i], str(gate_final[i]))
            for i in range(len(reason_parts))
        ],
        dtype=object,
    )

    # =============================================================================
    # Warning baseline60_degraded (informativo)
    # =============================================================================
    healthy_rmssd, healthy_hr, healthy_period = compute_healthy_anchors(core, cfg)

    rmssd_base60_equiv = np.exp(ln_base60.astype(float))
    rmssd_base60_equiv = pd.Series(rmssd_base60_equiv)

    dual_baseline = compute_dual_baseline_signals(
        df["Fecha"],
        rmssd_base60_equiv,
        healthy_rmssd,
        cfg,
    )

    warning_threshold, baseline60_degraded = select_legacy_warning_signal(
        dual_baseline,
        rmssd_base60_equiv,
        cfg,
    )

    # =============================================================================
    # Placeholders sistémicos (no recolorean)
    # =============================================================================
    flag_sistemico = np.array([False]*len(df), dtype=bool)
    flag_razon = np.array([""]*len(df), dtype=object)

    # =============================================================================
    # Construcción DataFrame FINAL
    # =============================================================================
    final = pd.DataFrame({
        "Fecha": df["Fecha"].astype(str),
        "Calidad": df["Calidad"].astype(str),
        "HRV_Stability": df["HRV_Stability"].astype(str),
        "Artifact_pct": pd.to_numeric(df["Artifact_pct"], errors="coerce"),
        "Tiempo_Estabilizacion": pd.to_numeric(df["Tiempo_Estabilizacion"], errors="coerce"),
        "Stability_Subtype": stability_subtype,
        "tail_mismatch_pct": tail_mismatch_pct,

        "HR_today": hr_today,
        "RMSSD_stable": rmssd_today,
        "lnRMSSD_today": ln_today,

        "lnRMSSD_used": ln_used,
        "HR_used": hr_used,
        "n_roll3": n_roll3,
        "gate_raw_today": gate_raw_today,
        "gate_raw_reason": gate_raw_reason,
        "unstable_note": unstable_note,

        "ln_base60": ln_base60,
        "HR_base60": hr_base60,
        "n_base60": n_base60,
        "SWC_ln": swc_ln60,
        "SWC_HR": swc_hr60,
        "d_ln": d_ln,
        "d_HR": d_hr,

        "gate_base60": gate_base60,
        "gate_razon_base60": razon_base60,

        "gate_shadow42": gate_shadow42,
        "gate_razon_shadow42": razon_shadow42,
        "n_base42": n_base42,

        "gate_shadow28": gate_shadow28,
        "gate_razon_shadow28": razon_shadow28,
        "n_base28": n_base28,

        "decision_mode": decision_mode,
        "gate_final": gate_final,
        "gate_final_delta": gate_final_delta,
        "decision_path": decision_path,
        "override_reason": override_reason,

        "residual_ln": residual_ln,
        "residual_z": residual_z,
        "residual_tag": residual_tag_arr,
        "gate_badge": gate_badge,

        "quality_flag": quality_flag.astype(bool),
        "Color_operativo": Color_operativo,

        "Action": Action,
        "Action_detail": Action_detail,
        "bad_streak": bad_streak,
        "bad_7d": bad_7d,

        "baseline60_degraded": baseline60_degraded.astype(bool),
        "degraded_vs_best": dual_baseline["degraded_vs_best"].astype(bool),
        "degraded_vs_current_normal": dual_baseline["degraded_vs_current_normal"].astype(bool),
        "healthy_rmssd": healthy_rmssd,
        "healthy_hr": healthy_hr,
        "healthy_period": healthy_period,

        "flag_sistemico": flag_sistemico.astype(bool),
        "flag_razon": flag_razon,

        "warning_threshold": warning_threshold,
        "warning_threshold_best": dual_baseline["warning_threshold_best"],
        "warning_threshold_current_normal": dual_baseline["warning_threshold_current_normal"],
        "warning_mode": cfg.warning_mode,
        "veto_agudo": veto_agudo.astype(bool),
        "ln_pre_veto": ln_pre_veto,
        "swc_ln_floor": swc_ln_floor_arr,
        "recovery_context_quality": recovery_context_quality,
        "recovery_support_class": recovery_support_class,
        "recovery_discordance_flag": recovery_discordance_flag.astype(bool),
        "recovery_discordance_reason": recovery_discordance_reason,
        "reason_text": reason_text,
    })

    # Reordenar (contrato)
    final = final.reindex(columns=COLS_FINAL)
    final.attrs["reason_items_sidecar"] = _build_reason_items_sidecar(
        [str(fecha) for fecha in df["Fecha"].astype(str).tolist()],
        reason_items,
    )

    dashboard = final[COLS_DASHBOARD].copy()
    return final, dashboard


def main(argv: List[str]) -> int:
    args = parse_args(argv)

    global DATA_DIR, IN_CORE, OUT_FINAL, OUT_DASHBOARD, OUT_FINAL_REASON_ITEMS, OUT_CORE_MANIFEST, OUT_FINAL_MANIFEST
    if "data_dir" in args:
        DATA_DIR = resolve_writable_dir(Path(args["data_dir"]), CONFIG_DATA_DIR)
        IN_CORE = DATA_DIR / "ENDURANCE_HRV_master_CORE.csv"
        OUT_FINAL = DATA_DIR / "ENDURANCE_HRV_master_FINAL.csv"
        OUT_DASHBOARD = DATA_DIR / "ENDURANCE_HRV_master_DASHBOARD.csv"
        OUT_FINAL_REASON_ITEMS = DATA_DIR / "ENDURANCE_HRV_master_FINAL_reason_items.json"
        OUT_CORE_MANIFEST = DATA_DIR / "ENDURANCE_HRV_master_CORE_manifest.json"
        OUT_FINAL_MANIFEST = DATA_DIR / "ENDURANCE_HRV_master_FINAL_manifest.json"

    cfg = CFG
    if "decision_mode" in args:
        cfg = replace(CFG, decision_mode=args["decision_mode"])

    if not IN_CORE.exists():
        print(f"[ERROR] No existe: {IN_CORE}")
        return 2

    core = pd.read_csv(IN_CORE)
    if core.empty or "Fecha" not in core.columns:
        print("[ERROR] CORE vacío o inválido.")
        return 2

    final, dashboard = build_final_and_dashboard(core, cfg)
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    write_csv_atomic(final, OUT_FINAL)
    write_csv_atomic(dashboard, OUT_DASHBOARD)
    write_json_atomic(final.attrs.get("reason_items_sidecar", {}), OUT_FINAL_REASON_ITEMS)

    manifest_extra = {}
    if OUT_CORE_MANIFEST.exists():
        manifest_extra["source_manifest_path"] = str(OUT_CORE_MANIFEST)
        manifest_extra["source_manifest_sha256"] = file_digest(OUT_CORE_MANIFEST)
        try:
            source_manifest = json.loads(OUT_CORE_MANIFEST.read_text(encoding="utf-8"))
        except Exception:
            source_manifest = None
        if isinstance(source_manifest, dict) and "effective_config_hash" in source_manifest:
            manifest_extra["source_manifest_effective_config_hash"] = str(
                source_manifest["effective_config_hash"]
            )

    manifest = build_run_manifest(
        stage="final_dashboard",
        builder="build_hrv_final_dashboard.py",
        builder_revision=file_digest(Path(__file__)),
        data_dir=DATA_DIR,
        effective_config={
            "data_dir": str(DATA_DIR),
            "input_core": str(IN_CORE),
            "input_sleep": str(DATA_DIR / "ENDURANCE_HRV_sleep.csv"),
            "input_sessions_day": str(DATA_DIR / "ENDURANCE_HRV_sessions_day.csv"),
            "final_output": str(OUT_FINAL),
            "dashboard_output": str(OUT_DASHBOARD),
            "reason_items_output": str(OUT_FINAL_REASON_ITEMS),
            "config": asdict(cfg),
            "swc_floor": SWC_FLOOR,
            "veto_mult": VETO_MULT,
        },
        inputs=[
            artifact_signature(
                IN_CORE,
                role="core_input",
                row_count=len(core),
                column_count=len(core.columns),
            ),
            artifact_signature(
                DATA_DIR / "ENDURANCE_HRV_sleep.csv",
                role="sleep_input",
                required=False,
            ),
            artifact_signature(
                DATA_DIR / "ENDURANCE_HRV_sessions_day.csv",
                role="sessions_day_input",
                required=False,
            ),
        ],
        outputs=[
            artifact_signature(
                OUT_FINAL,
                role="final",
                row_count=len(final),
                column_count=len(final.columns),
            ),
            artifact_signature(
                OUT_DASHBOARD,
                role="dashboard",
                row_count=len(dashboard),
                column_count=len(dashboard.columns),
            ),
            artifact_signature(
                OUT_FINAL_REASON_ITEMS,
                role="reason_items_sidecar",
            ),
        ],
        extra=manifest_extra or None,
    )
    write_run_manifest_atomic(manifest, OUT_FINAL_MANIFEST)

    last_fecha = "N/A"
    if not final.empty and "Fecha" in final.columns:
        last_fecha = str(final["Fecha"].iloc[-1])
    print(f"[OK] Archivos actualizados hasta {last_fecha}")
    print(f"[OK] Manifest escrito en {OUT_FINAL_MANIFEST}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

