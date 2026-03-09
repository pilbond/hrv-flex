#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ENDURANCE HRV — Decisor V4-lite (r2026-02-12)
============================================

Lee:
  - ENDURANCE_HRV_master_CORE.csv

Genera:
  - ENDURANCE_HRV_master_FINAL.csv     (53 cols, gate + sombras + residual + auditoría)
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
from dataclasses import dataclass
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


# =============================================================================
# Columnas (contrato)
# =============================================================================

COLS_FINAL = [
    "Fecha","Calidad","HRV_Stability","Artifact_pct","Tiempo_Estabilizacion",
    "HR_today","RMSSD_stable","lnRMSSD_today",
    "lnRMSSD_used","HR_used","n_roll3",
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
    "veto_agudo","ln_pre_veto","swc_ln_floor","reason_text",
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


def _safe_float(row: pd.Series, col: str) -> Optional[float]:
    """Extract float from sleep row, return None if missing."""
    try:
        v = row[col]
        if pd.isna(v):
            return None
        return float(v)
    except (KeyError, TypeError, ValueError):
        return None


def parse_args(argv: List[str]) -> Dict[str, str]:
    out: Dict[str, str] = {}
    i = 0
    while i < len(argv):
        a = argv[i]
        if a in ("--decision-mode",):
            out["decision_mode"] = argv[i+1]
            i += 2
        elif a in ("--data-dir",):
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
        elif (not np.isfinite(sw_ln)) or (not np.isfinite(sw_hr)) or sw_ln == 0.0 or sw_hr == 0.0:
            gate_base60[i] = NO
            razon_base60[i] = "SWC_NAN/0"
        else:
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
            except Exception:
                pass  # residual queda NaN
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

    # bad_streak / bad_7d sobre (ROJO o NO)
    bad_streak = np.zeros(len(df), dtype=int)
    for i in range(len(df)):
        if gate_final[i] in (ROJO, NO):
            bad_streak[i] = (bad_streak[i-1] + 1) if i > 0 else 1
        else:
            bad_streak[i] = 0

    bad_7d = np.zeros(len(df), dtype=int)
    for i in range(len(df)):
        lo = max(0, i-6)
        bad_7d[i] = int(np.sum(np.isin(gate_final[lo:i+1], [ROJO, NO])))

    # Ajuste Action_detail por acumulación (solo para ROJO/NO y sin SUAVE_QUALITY)
    for i in range(len(df)):
        if Action_detail[i] == "SUAVE_QUALITY":
            continue
        if gate_final[i] in (ROJO, NO) and (bad_streak[i] >= 2 or bad_7d[i] >= 3):
            Action_detail[i] = "DESCARGA"

    # =============================================================================
    # REASON_TEXT (contextual)
    # =============================================================================

    # --- Sleep context from sleep.csv (Polar sleep/nightly only) ---
    sleep_lookup: Optional[pd.DataFrame] = None
    sleep_path = DATA_DIR / "ENDURANCE_HRV_sleep.csv"
    legacy_sleep_path = DATA_DIR / "ENDURANCE_HRV_context.csv"
    if not sleep_path.exists() and legacy_sleep_path.exists():
        sleep_path = legacy_sleep_path
    if sleep_path.exists():
        try:
            sleep_df = pd.read_csv(sleep_path)
            if "Fecha" in sleep_df.columns:
                sleep_df["Fecha"] = sleep_df["Fecha"].astype(str)
                sleep_df = sleep_df.drop_duplicates(subset=["Fecha"], keep="last")
                sleep_lookup = sleep_df.set_index("Fecha")
        except (OSError, ValueError, KeyError):
            sleep_lookup = None

    # --- Training load from sessions_day.csv (generated by build_sessions.py) ---
    sday_lookup: Optional[pd.DataFrame] = None
    sday_path = DATA_DIR / "ENDURANCE_HRV_sessions_day.csv"
    if sday_path.exists():
        try:
            sday_df = pd.read_csv(sday_path)
            if "Fecha" in sday_df.columns:
                sday_df["Fecha"] = sday_df["Fecha"].astype(str)
                sday_df = sday_df.drop_duplicates(subset=["Fecha"], keep="last")
                sday_lookup = sday_df.set_index("Fecha")
        except (OSError, ValueError, KeyError):
            sday_lookup = None

    for i in range(len(df)):
        fecha = str(df.iloc[i]["Fecha"])

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
            sleep_bad = False

            if sleep_dur is not None and sleep_dur_p10 is not None and sleep_dur < sleep_dur_p10:
                reason_parts[i].append(f"Noche corta ({sleep_dur:.0f}min < P10={sleep_dur_p10:.0f})")
                sleep_bad = True
            if sleep_int is not None and sleep_int_p90 is not None and sleep_int > sleep_int_p90:
                reason_parts[i].append(f"Noche fragmentada ({sleep_int:.0f} interr > P90={sleep_int_p90:.0f})")
                sleep_bad = True

            # Nightly RMSSD discordancia
            night_rmssd = _safe_float(sleep_row, "polar_night_rmssd")
            if night_rmssd is not None:
                if gate_final[i] == VERDE and night_rmssd < 25:
                    reason_parts[i].append(f"VERDE pero nightly_rmssd bajo ({night_rmssd:.0f}ms)")
                elif gate_final[i] == ROJO and night_rmssd > 45:
                    reason_parts[i].append(f"ROJO con nightly_rmssd alto ({night_rmssd:.0f}ms): posible confusor")
        else:
            sleep_dur = None
            sleep_dur_p10 = None
            sleep_bad = False

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

            # Only use load_3d if we have real coverage
            if load_3d is not None and load_3d_nobs is not None and load_3d_nobs >= 2:
                if load_3d > 250:
                    reason_parts[i].append(f"Carga acumulada alta (load_3d={load_3d:.0f})")
            if work_7d is not None and work_7d > 200:
                reason_parts[i].append(f"Volumen semanal alto (work_7d={work_7d:.0f}min)")
            if z3_7d is not None and z3_7d > 60:
                reason_parts[i].append(f"Z3 acumulado alto (z3_7d={z3_7d:.0f}min)")

            # ROJO sin carga previa
            if gate_final[i] == ROJO and load_day is not None and load_day < 30:
                if not sleep_bad:
                    reason_parts[i].append("ROJO sin carga previa ni sueño malo: revisar otros factores")

            # VERDE con carga acumulada alta
            if gate_final[i] == VERDE and load_3d is not None and load_3d > 200:
                reason_parts[i].append(f"VERDE con carga acumulada (load_3d={load_3d:.0f}): precaución intensidad")

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

        "HR_today": hr_today,
        "RMSSD_stable": rmssd_today,
        "lnRMSSD_today": ln_today,

        "lnRMSSD_used": ln_used,
        "HR_used": hr_used,
        "n_roll3": n_roll3,

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
        cfg = Config(**{**CFG.__dict__, "decision_mode": args["decision_mode"]})

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

    print(f"[OK] FINAL -> {OUT_FINAL} ({len(final)} filas)")
    print(f"[OK] DASHBOARD -> {OUT_DASHBOARD} ({len(dashboard)} filas)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

