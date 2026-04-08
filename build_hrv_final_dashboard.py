#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ENDURANCE HRV — Decisor FINAL/DASHBOARD
======================================

Revisión de módulo: r2026-04-08
Contrato esperado: FINAL 62 cols, DASHBOARD 10 cols
Sistema vigente: ENDURANCE HRV V4.6

Lee:
  - ENDURANCE_HRV_master_CORE.csv

Genera:
  - ENDURANCE_HRV_master_FINAL.csv     (62 cols, gate + sombras + residual + auditoría raw-vs-ref + RE-01)
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

import os
import sys
import logging
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Dict, Optional, Tuple, List

import numpy as np
import pandas as pd


# =============================================================================
# Configuración
# =============================================================================

VERDE = "VERDE"
AMBAR = "ÁMBAR"
ROJO  = "ROJO"
NO    = "NO"

GATE_ORDER = {VERDE: 0, AMBAR: 1, ROJO: 2}

DATA_DIR = Path((os.environ.get("HRV_DATA_DIR") or "data").strip() or "data")

IN_CORE = DATA_DIR / "ENDURANCE_HRV_master_CORE.csv"
OUT_FINAL = DATA_DIR / "ENDURANCE_HRV_master_FINAL.csv"
OUT_DASHBOARD = DATA_DIR / "ENDURANCE_HRV_master_DASHBOARD.csv"


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
    warning_mode: str = "healthy85"  # healthy85 | p20
    healthy_start: str = os.environ.get("HRV_HEALTHY_START", "2025-07-01")
    healthy_end: str   = os.environ.get("HRV_HEALTHY_END",   "2025-09-30")
    healthy_factor: float = 0.85
    p20_q: float = 0.20


CFG = Config()
SWC_FLOOR = 0.04879  # ln(1.05), floor mínimo para SWC
VETO_MULT = 2.0      # veto si raw cae > 2xSWC bajo base60
LOAD_3D_HIGH = 250
LOAD_3D_CAUTION = 200
WORK_7D_HIGH = 200
Z3_7D_HIGH = 60

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
    "baseline60_degraded","healthy_rmssd","healthy_hr","healthy_period",
    "flag_sistemico","flag_razon",
    "warning_threshold","warning_mode",
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


def compute_healthy_anchors(core: pd.DataFrame, cfg: Config) -> Tuple[float, float, str]:
    """
    Anclas "healthy" para warning baseline60_degraded.
    - Se calculan sobre días clean (Calidad == OK) usando mediana móvil 7d.
    """
    df = core.copy()
    df["Fecha_dt"] = pd.to_datetime(df["Fecha"], errors="coerce")
    is_clean = (df["Calidad"] == "OK") & df["lnRMSSD"].notna() & df["HR_stable"].notna() & df["RMSSD_stable"].notna()
    sub = df.loc[is_clean, ["Fecha_dt", "RMSSD_stable", "HR_stable"]].sort_values("Fecha_dt").copy()
    if sub.empty:
        return (float("nan"), float("nan"), f"{cfg.healthy_start}..{cfg.healthy_end}")

    sub["RMSSD_med7"] = sub["RMSSD_stable"].rolling(7, min_periods=3).median()
    sub["HR_med7"] = sub["HR_stable"].rolling(7, min_periods=3).median()

    hs = pd.to_datetime(cfg.healthy_start, errors="coerce")
    he = pd.to_datetime(cfg.healthy_end, errors="coerce")
    if pd.isna(hs) or pd.isna(he):
        return (float(np.nanmedian(sub["RMSSD_med7"])), float(np.nanmedian(sub["HR_med7"])), "invalid_period(fallback)")

    in_period = (sub["Fecha_dt"] >= hs) & (sub["Fecha_dt"] <= he)
    s2 = sub.loc[in_period]
    if s2.empty:
        return (float(np.nanmedian(sub["RMSSD_med7"])), float(np.nanmedian(sub["HR_med7"])), f"{cfg.healthy_start}..{cfg.healthy_end}(fallback)")
    return (float(np.nanmedian(s2["RMSSD_med7"])), float(np.nanmedian(s2["HR_med7"])), f"{cfg.healthy_start}..{cfg.healthy_end}")


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


def _build_sessions_day_lookups(
    sday_df: pd.DataFrame,
) -> Tuple[Optional[pd.DataFrame], Optional[pd.DataFrame], Optional[pd.DataFrame], Dict[str, float]]:
    if "Fecha" not in sday_df.columns:
        return None, None, None, {}

    base_df = sday_df.copy()
    base_df["Fecha"] = base_df["Fecha"].astype(str)
    base_df = base_df.drop_duplicates(subset=["Fecha"], keep="last")
    exact_lookup = base_df.set_index("Fecha")

    ctx_cols = ["acwr_simple_prev", "monotony_7d_prev", "strain_7d_prev", "load_ctx_ready"]
    present_ctx_cols = [col for col in ctx_cols if col in base_df.columns]
    ctx_lookup: Optional[pd.DataFrame] = None

    if present_ctx_cols:
        ctx_df = base_df[["Fecha"] + present_ctx_cols].copy()
        ctx_df["Fecha_dt"] = pd.to_datetime(ctx_df["Fecha"], errors="coerce")
        ctx_df = ctx_df.dropna(subset=["Fecha_dt"]).sort_values("Fecha_dt")
        if not ctx_df.empty:
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
        clustering_df["Fecha_dt"] = pd.to_datetime(clustering_df["Fecha"], errors="coerce")
        clustering_df = clustering_df.dropna(subset=["Fecha_dt"]).sort_values("Fecha_dt")
        if not clustering_df.empty:
            clustering_lookup = clustering_df.set_index("Fecha_dt")[present_clustering_cols]
            full_range = pd.date_range(
                clustering_lookup.index.min(),
                clustering_lookup.index.max() + pd.Timedelta(days=2),
                freq="D",
            )
            clustering_lookup = clustering_lookup.reindex(full_range).ffill(limit=2)
            clustering_lookup.index = clustering_lookup.index.strftime("%Y-%m-%d")
            clustering_lookup.index.name = "Fecha"

    thresholds: Dict[str, float] = {}
    if "strain_7d_prev" in base_df.columns:
        strain_hist = pd.to_numeric(base_df["strain_7d_prev"], errors="coerce")
        if "load_ctx_ready" in base_df.columns:
            ready_mask = base_df["load_ctx_ready"].astype(str).str.lower().isin({"true", "1"})
            strain_hist = strain_hist.loc[ready_mask]
        strain_hist = strain_hist[np.isfinite(strain_hist.to_numpy(dtype=float))]
        if strain_hist.size >= 8:
            strain_values = strain_hist.to_numpy(dtype=float)
            thresholds["strain_p75"] = float(np.quantile(strain_values, 0.75))
            thresholds["strain_p90"] = float(np.quantile(strain_values, 0.90))

    return exact_lookup, ctx_lookup, clustering_lookup, thresholds


def _append_unique(items: List[str], value: str) -> None:
    if value and value not in items:
        items.append(value)


def _split_recovery_codes(codes: List[str]) -> Tuple[List[str], List[str]]:
    sleep_codes = [
        code
        for code in codes
        if code in {"sleep_basic_poor", "sleep_score_low", "nightly_rmssd_low"}
    ]
    load_codes = [
        code
        for code in codes
        if code in {"load_3d_high", "load_context_high", "intensity_clustering", "recent_load_low"}
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


def _recovery_message(gate: str, recovery_class: str, support_codes: List[str], caution_codes: List[str]) -> str:
    caution_set = set(caution_codes)
    support_set = set(support_codes)

    if gate == VERDE and recovery_class == "fragile":
        if (
            {"sleep_basic_poor", "sleep_score_low", "nightly_rmssd_low"} & caution_set
            and {"load_3d_high", "load_context_high", "intensity_clustering"} & caution_set
        ):
            return "VERDE con recuperación frágil: mala noche + carga reciente piden contener la intensidad"
        if {"sleep_basic_poor", "sleep_score_low", "nightly_rmssd_low"} & caution_set:
            return "VERDE con recuperación nocturna frágil: contener la intensidad"
        return "VERDE con recuperación frágil por carga reciente: contener la intensidad"
    if gate == AMBAR and recovery_class == "supported":
        if {"sleep_score_good", "nightly_rmssd_good"} & support_set:
            return "ÁMBAR con soporte nocturno aceptable: Z2 controlado es razonable si sensaciones normales"
        if "recent_load_low" in support_set:
            return "ÁMBAR con poca carga reciente: Z2 controlado es razonable si sensaciones normales"
        return "ÁMBAR con soporte objetivo aceptable: Z2 controlado es razonable si sensaciones normales"
    if gate == AMBAR and recovery_class == "fragile":
        return "ÁMBAR con recuperación frágil: mejor sesgo conservador hoy"
    if gate == ROJO and recovery_class == "conflicted":
        return "ROJO con discordancia objetiva: sueño y carga no explican del todo la señal"
    if gate == ROJO and recovery_class == "supported":
        return "ROJO respaldado por mala recuperación o carga reciente"
    return ""


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
    df["Fecha_dt"] = pd.to_datetime(df["Fecha"], errors="coerce")
    df = df.sort_values("Fecha_dt").reset_index(drop=True)
    dates = df["Fecha_dt"].to_numpy(dtype="datetime64[ns]")

    # Señales del día
    ln_today = pd.to_numeric(df["lnRMSSD"], errors="coerce").to_numpy(dtype=float)
    hr_today = pd.to_numeric(df["HR_stable"], errors="coerce").to_numpy(dtype=float)
    rmssd_today = pd.to_numeric(df["RMSSD_stable"], errors="coerce").to_numpy(dtype=float)
    rrbar_s = pd.to_numeric(df["RRbar_s"], errors="coerce").to_numpy(dtype=float)
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
    reason_parts: List[List[str]] = [[] for _ in range(len(df))]

    # Precompute lnRRbar
    ln_rr = np.full(len(df), np.nan, dtype=float)
    with np.errstate(divide="ignore", invalid="ignore"):
        ln_rr = np.log(rrbar_s)

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
        w60 = window_mask(dates, i, cfg.base60_days)
        b_ln, sw_ln, n_ln = window_stats(ln_today, is_clean, w60, cfg.swc_mult)
        b_hr, sw_hr, n_hr = window_stats(hr_today, is_clean, w60, cfg.swc_mult)
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
                reason_parts[i].append(
                    f"Caída aguda HRV: raw={ln_today[i]:.3f} vs base={b_ln:.3f} "
                    f"(drop={ln_today[i]-b_ln:.3f}, umbral=-{VETO_MULT*swc_v4:.3f})"
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

        # ===== SHADOW42 =====
        w42 = window_mask(dates, i, cfg.base42_days)
        b_ln42, sw_ln42, n_ln42 = window_stats(ln_today, is_clean, w42, cfg.swc_mult)
        b_hr42, sw_hr42, n_hr42 = window_stats(hr_today, is_clean, w42, cfg.swc_mult)
        nb42 = int(min(n_ln42, n_hr42))
        n_base42[i] = nb42

        if nb42 < cfg.min_base42_clean:
            gate_shadow42[i] = NO
            razon_shadow42[i] = "BASE42_INSUF"
        elif (not np.isfinite(sw_ln42)) or (not np.isfinite(sw_hr42)) or sw_ln42 == 0.0 or sw_hr42 == 0.0:
            gate_shadow42[i] = NO
            razon_shadow42[i] = "SWC_NAN/0"
        else:
            dln42 = float(ln_used[i] - b_ln42)
            dhr42 = float(hr_used[i] - b_hr42)
            ln_bajo42 = dln42 < -sw_ln42
            hr_alto42 = dhr42 >  sw_hr42
            if ln_bajo42 and hr_alto42:
                gate_shadow42[i] = ROJO; razon_shadow42[i] = "2D_AMBOS"
            elif ln_bajo42:
                gate_shadow42[i] = AMBAR; razon_shadow42[i] = "2D_LN"
            elif hr_alto42:
                gate_shadow42[i] = AMBAR; razon_shadow42[i] = "2D_HR"
            else:
                gate_shadow42[i] = VERDE; razon_shadow42[i] = "2D_OK"

        # ===== SHADOW28 =====
        w28 = window_mask(dates, i, cfg.base28_days)
        b_ln28, sw_ln28, n_ln28 = window_stats(ln_today, is_clean, w28, cfg.swc_mult)
        b_hr28, sw_hr28, n_hr28 = window_stats(hr_today, is_clean, w28, cfg.swc_mult)
        nb28 = int(min(n_ln28, n_hr28))
        n_base28[i] = nb28

        if nb28 < cfg.min_base28_clean:
            gate_shadow28[i] = NO
            razon_shadow28[i] = "BASE28_INSUF"
        elif (not np.isfinite(sw_ln28)) or (not np.isfinite(sw_hr28)) or sw_ln28 == 0.0 or sw_hr28 == 0.0:
            gate_shadow28[i] = NO
            razon_shadow28[i] = "SWC_NAN/0"
        else:
            dln28 = float(ln_used[i] - b_ln28)
            dhr28 = float(hr_used[i] - b_hr28)
            ln_bajo28 = dln28 < -sw_ln28
            hr_alto28 = dhr28 >  sw_hr28
            if ln_bajo28 and hr_alto28:
                gate_shadow28[i] = ROJO; razon_shadow28[i] = "2D_AMBOS"
            elif ln_bajo28:
                gate_shadow28[i] = AMBAR; razon_shadow28[i] = "2D_LN"
            elif hr_alto28:
                gate_shadow28[i] = AMBAR; razon_shadow28[i] = "2D_HR"
            else:
                gate_shadow28[i] = VERDE; razon_shadow28[i] = "2D_OK"

        # ===== RESIDUAL (BASE60) =====
        # Fit OLS y = a + b*x en ventana BASE60 (shift-1) sobre días clean
        # x = ln(RRbar_s), y = lnRMSSD_today
        mfit = w60 & is_clean & np.isfinite(ln_rr) & np.isfinite(ln_today)
        if np.sum(mfit) >= cfg.min_base60_clean and np.isfinite(ln_rr[i]) and np.isfinite(ln_today[i]):
            x = ln_rr[mfit].astype(float)
            y = ln_today[mfit].astype(float)
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

    # --- Training load from sessions_day.csv (generated by build_sessions.py) ---
    sday_lookup: Optional[pd.DataFrame] = None
    load_ctx_lookup: Optional[pd.DataFrame] = None
    clustering_lookup: Optional[pd.DataFrame] = None
    load_ctx_thresholds: Dict[str, float] = {}
    sday_path = DATA_DIR / "ENDURANCE_HRV_sessions_day.csv"
    if sday_path.exists():
        try:
            sday_df = pd.read_csv(sday_path)
            sday_lookup, load_ctx_lookup, clustering_lookup, load_ctx_thresholds = _build_sessions_day_lookups(sday_df)
        except (OSError, ValueError, KeyError) as exc:
            log.warning("Sessions context unavailable from %s: %s", sday_path, exc)
            sday_lookup = None
            load_ctx_lookup = None
            clustering_lookup = None
            load_ctx_thresholds = {}

    recovery_context_quality = np.array(["none"] * len(df), dtype=object)
    recovery_support_class = np.array(["neutral"] * len(df), dtype=object)
    recovery_discordance_flag = np.array([False] * len(df), dtype=bool)
    recovery_discordance_reason = np.array([""] * len(df), dtype=object)

    for i in range(len(df)):
        fecha = str(df.iloc[i]["Fecha"])
        verde_load_3d_caution = False
        sleep_bad = False
        sleep_basic_signal = False
        sleep_score = None
        night_rmssd = None
        night_rmssd_low_text = ""
        night_rmssd_high_text = ""
        load_3d = None
        load_3d_nobs = None
        load_day = None
        load_ctx_caution = False
        clustering_flag = False
        support_codes: List[str] = []
        caution_codes: List[str] = []

        # Saturación parasimpática
        if np.isfinite(d_ln[i]) and np.isfinite(swc_ln_floor_arr[i]):
            if d_ln[i] > 2 * swc_ln_floor_arr[i]:
                reason_parts[i].append("HRV excesivamente alto: posible saturación parasimpática")

        # Quality override
        if quality_flag[i] and gate_final[i] in (VERDE, AMBAR):
            reason_parts[i].append("Dato dudoso: limitar a Z1-Z2 máx 90min")

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
                reason_parts[i].append(f"Noche corta ({sleep_dur:.0f}min < P10={sleep_dur_p10:.0f})")
                sleep_bad = True
                _append_unique(caution_codes, "sleep_basic_poor")
            if sleep_int is not None and sleep_int_p90 is not None and sleep_int > sleep_int_p90:
                reason_parts[i].append(f"Noche fragmentada ({sleep_int:.0f} interr > P90={sleep_int_p90:.0f})")
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
                    night_rmssd_low_text = f"VERDE pero nightly_rmssd bajo ({night_rmssd:.0f}ms)"
                elif gate_final[i] == ROJO and night_rmssd > 45:
                    night_rmssd_high_text = f"ROJO con nightly_rmssd alto ({night_rmssd:.0f}ms): posible confusor"
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
        if load_ctx_lookup is not None and fecha in load_ctx_lookup.index:
            load_ctx_row = load_ctx_lookup.loc[fecha]
            if isinstance(load_ctx_row, pd.DataFrame):
                load_ctx_row = load_ctx_row.iloc[-1]
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
            load_day = _safe_float(sday_row, "load_day")
            work_7d = _safe_float(sday_row, "work_7d_sum")
            z3_7d = _safe_float(sday_row, "z3_7d_sum")

            # Sidecar acute-load warning retained for short-term accumulation that
            # may matter even when canonical 7d/28d context stays below threshold.
            if load_3d is not None and load_3d_nobs is not None and load_3d_nobs >= 2:
                if load_3d > LOAD_3D_HIGH:
                    reason_parts[i].append(f"Carga acumulada alta (load_3d={load_3d:.0f})")
                if load_3d > LOAD_3D_CAUTION:
                    _append_unique(caution_codes, "load_3d_high")

            if work_7d is not None and work_7d > WORK_7D_HIGH:
                reason_parts[i].append(f"Volumen semanal alto (work_7d={work_7d:.0f}min)")
            if z3_7d is not None and z3_7d > Z3_7D_HIGH:
                reason_parts[i].append(f"Z3 acumulado alto (z3_7d={z3_7d:.0f}min)")

            # ROJO sin carga previa
            if gate_final[i] == ROJO and load_day is not None and load_day < 30:
                if sleep_basic_signal and not sleep_bad:
                    reason_parts[i].append("ROJO sin carga previa ni sueño malo: revisar otros factores")
                elif not sleep_basic_signal:
                    reason_parts[i].append("ROJO sin carga previa reciente: revisar otros factores")

            if (
                gate_final[i] == VERDE
                and load_3d is not None
                and load_3d_nobs is not None
                and load_3d_nobs >= 2
                and load_3d > LOAD_3D_CAUTION
            ):
                verde_load_3d_caution = True

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
                clustering_window_bits = []
                if intense_days_prev_3d is not None:
                    clustering_window_bits.append(f"{intense_days_prev_3d:.0f}/3d")
                if intense_days_prev_5d is not None:
                    clustering_window_bits.append(f"{intense_days_prev_5d:.0f}/5d")
                clustering_window_text = " · ".join(clustering_window_bits)

                if gate_final[i] == VERDE:
                    if clustering_level == "high":
                        clustering_msg = "VERDE pero clustering alto de intensidad reciente: considera Z1 mañana"
                    else:
                        clustering_msg = "VERDE pero clustering reciente de intensidad: considera Z1 mañana"
                else:
                    if clustering_level == "high":
                        clustering_msg = "Clustering alto de intensidad reciente: vigilar recuperación"
                    else:
                        clustering_msg = "Clustering reciente de intensidad: vigilar recuperación"

                if clustering_window_text:
                    clustering_msg = f"{clustering_msg} ({clustering_window_text})"
                reason_parts[i].append(clustering_msg)

        if load_ctx_row is not None:
            acwr_simple_prev = _safe_float(load_ctx_row, "acwr_simple_prev")
            monotony_7d_prev = _safe_float(load_ctx_row, "monotony_7d_prev")
            strain_7d_prev = _safe_float(load_ctx_row, "strain_7d_prev")
            load_ctx_ready = str(load_ctx_row.get("load_ctx_ready", "")).lower() in {"true", "1"}

            load_ctx_caution = False
            load_ctx_caution_sources: List[str] = []

            if load_ctx_ready and acwr_simple_prev is not None:
                if acwr_simple_prev >= 1.5:
                    reason_parts[i].append(
                        f"ACWR muy alto: carga aguda muy por encima de la base crónica ({acwr_simple_prev:.2f})"
                    )
                    load_ctx_caution = True
                    load_ctx_caution_sources.append("ACWR")
                    _append_unique(caution_codes, "load_context_high")
                elif acwr_simple_prev >= 1.3:
                    reason_parts[i].append(
                        f"ACWR alto: carga aguda por encima de la base crónica ({acwr_simple_prev:.2f})"
                    )
                    load_ctx_caution = True
                    load_ctx_caution_sources.append("ACWR")
                    _append_unique(caution_codes, "load_context_high")
                elif acwr_simple_prev <= 0.8:
                    reason_parts[i].append(
                        f"ACWR bajo: descarga o infraexposición reciente ({acwr_simple_prev:.2f})"
                    )

            if load_ctx_ready and monotony_7d_prev is not None:
                if monotony_7d_prev >= 2.0:
                    reason_parts[i].append(
                        f"Monotonía alta: patrón de carga poco variable ({monotony_7d_prev:.2f})"
                    )
                    load_ctx_caution = True
                    load_ctx_caution_sources.append("monotonía")
                    _append_unique(caution_codes, "load_context_high")
                elif monotony_7d_prev >= 1.8:
                    reason_parts[i].append(
                        f"Monotonía elevada: conviene variar la estructura de carga ({monotony_7d_prev:.2f})"
                    )
                    load_ctx_caution = True
                    load_ctx_caution_sources.append("monotonía")
                    _append_unique(caution_codes, "load_context_high")

            if load_ctx_ready and strain_7d_prev is not None and load_ctx_thresholds:
                strain_p90 = load_ctx_thresholds.get("strain_p90")
                strain_p75 = load_ctx_thresholds.get("strain_p75")
                if strain_p90 is not None and strain_7d_prev >= strain_p90:
                    reason_parts[i].append(
                        f"Strain muy alto: semana exigente y poco descargada ({strain_7d_prev:.0f})"
                    )
                    load_ctx_caution = True
                    load_ctx_caution_sources.append("strain")
                    _append_unique(caution_codes, "load_context_high")
                elif strain_p75 is not None and strain_7d_prev >= strain_p75:
                    reason_parts[i].append(
                        f"Strain alto: semana exigente y poco descargada ({strain_7d_prev:.0f})"
                    )
                    load_ctx_caution = True
                    load_ctx_caution_sources.append("strain")
                    _append_unique(caution_codes, "load_context_high")

            if gate_final[i] == VERDE:
                unique_sources = list(dict.fromkeys(load_ctx_caution_sources))
                if verde_load_3d_caution and load_ctx_caution:
                    reason_parts[i].append(
                        "VERDE con convergencia de carga "
                        f"(load_3d + {' + '.join(unique_sources)}): precaución intensidad reforzada"
                    )
                elif verde_load_3d_caution:
                    reason_parts[i].append(
                        f"VERDE con carga acumulada (load_3d={load_3d:.0f}): precaución intensidad"
                    )
                elif load_ctx_caution:
                    reason_parts[i].append("VERDE con contexto de carga exigente: precaución intensidad")
        elif gate_final[i] == VERDE and verde_load_3d_caution:
            reason_parts[i].append(
                f"VERDE con carga acumulada (load_3d={load_3d:.0f}): precaución intensidad"
            )

        if (
            gate_final[i] in (AMBAR, ROJO)
            and load_day is not None
            and load_day < 30
            and not load_ctx_caution
            and not clustering_flag
            and (load_3d is None or load_3d <= LOAD_3D_CAUTION)
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
        recovery_msg = _recovery_message(
            gate=gate_final[i],
            recovery_class=recovery_class,
            support_codes=support_codes,
            caution_codes=caution_codes,
        )
        # Un nightly_rmssd bajo aislado en un VERDE no abre mensaje por sí solo:
        # RE-01 exige convergencia real para no sobrerreaccionar a un sidecar nocturno único.
        if night_rmssd_low_text and recovery_class == "fragile":
            reason_parts[i].append(night_rmssd_low_text)
        if night_rmssd_high_text and recovery_class == "conflicted":
            reason_parts[i].append(night_rmssd_high_text)
        if recovery_msg:
            reason_parts[i].append(recovery_msg)

        discordance_codes = caution_codes if recovery_class == "fragile" else support_codes
        recovery_context_quality[i] = coverage
        recovery_support_class[i] = recovery_class
        recovery_discordance_flag[i] = recovery_is_discordant
        recovery_discordance_reason[i] = "|".join(discordance_codes if recovery_is_discordant else [])

    reason_text = np.array([" | ".join(p) if p else "" for p in reason_parts], dtype=object)

    # =============================================================================
    # Warning baseline60_degraded (informativo)
    # =============================================================================
    healthy_rmssd, healthy_hr, healthy_period = compute_healthy_anchors(core, cfg)

    rmssd_base60_equiv = np.exp(ln_base60.astype(float))
    rmssd_base60_equiv = pd.Series(rmssd_base60_equiv)

    warning_threshold = np.nan
    baseline60_degraded = np.array([False]*len(df), dtype=bool)

    if cfg.warning_mode == "healthy85":
        if np.isfinite(healthy_rmssd):
            warning_threshold = float(cfg.healthy_factor * healthy_rmssd)
            baseline60_degraded = (rmssd_base60_equiv.to_numpy(dtype=float) < warning_threshold) & np.isfinite(rmssd_base60_equiv.to_numpy(dtype=float))
        else:
            warning_threshold = np.nan
            baseline60_degraded = np.array([False]*len(df), dtype=bool)
    elif cfg.warning_mode == "p20":
        x = rmssd_base60_equiv.dropna().to_numpy(dtype=float)
        if x.size >= 10:
            warning_threshold = float(np.quantile(x, cfg.p20_q))
            baseline60_degraded = (rmssd_base60_equiv.to_numpy(dtype=float) < warning_threshold) & np.isfinite(rmssd_base60_equiv.to_numpy(dtype=float))
        else:
            warning_threshold = np.nan
            baseline60_degraded = np.array([False]*len(df), dtype=bool)
    else:
        raise ValueError("warning_mode inválido. Usa healthy85 o p20.")

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
        "healthy_rmssd": healthy_rmssd,
        "healthy_hr": healthy_hr,
        "healthy_period": healthy_period,

        "flag_sistemico": flag_sistemico.astype(bool),
        "flag_razon": flag_razon,

        "warning_threshold": warning_threshold,
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

    dashboard = final[COLS_DASHBOARD].copy()
    return final, dashboard


def main(argv: List[str]) -> int:
    args = parse_args(argv)

    global DATA_DIR, IN_CORE, OUT_FINAL, OUT_DASHBOARD
    if "data_dir" in args:
        DATA_DIR = Path(args["data_dir"])
        IN_CORE = DATA_DIR / "ENDURANCE_HRV_master_CORE.csv"
        OUT_FINAL = DATA_DIR / "ENDURANCE_HRV_master_FINAL.csv"
        OUT_DASHBOARD = DATA_DIR / "ENDURANCE_HRV_master_DASHBOARD.csv"

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
    final.to_csv(OUT_FINAL, index=False)
    dashboard.to_csv(OUT_DASHBOARD, index=False)

    last_fecha = "N/A"
    if not final.empty and "Fecha" in final.columns:
        last_fecha = str(final["Fecha"].iloc[-1])
    print(f"[OK] Archivos actualizados hasta {last_fecha}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

