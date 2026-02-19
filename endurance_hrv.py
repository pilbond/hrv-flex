#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ENDURANCE HRV — Procesador de medición (v2.1)
=============================================

Genera desde archivos RR crudos:
  - ENDURANCE_HRV_master_CORE.csv    (medición canónica, 12 columnas)
  - ENDURANCE_HRV_master_BETA_AUDIT.csv (beta/cRMSSD/colores V3 legacy, 13 columnas)

NO genera gate V4-lite ni decisiones operativas (eso lo hace endurance_v4lite.py, que produce FINAL/DASHBOARD).

Uso:
  python endurance_hrv.py                           # procesa RR_FILES definidos en código
  python endurance_hrv.py --rr-dir ./rr_downloads   # procesa todos los RR en directorio
  python endurance_hrv.py --rr-file archivo_RR.csv  # procesa un archivo específico

Variables de entorno:
  HRV_DATA_DIR       Directorio de datos (default: .)
  RR_DOWNLOAD_DIR    Directorio de archivos RR (default: ./rr_downloads)
  HRV_QUIET          Silenciar mensajes (1/true/yes)
  HRV_DISABLE_BACKUP Deshabilitar backups (1/true/yes)
"""

import os
import re
import sys
import time
import shutil
import argparse
from pathlib import Path
from typing import Dict, List, Tuple, Optional

import numpy as np
import pandas as pd


# ============================================================================
# CONFIGURACIÓN
# ============================================================================

QUIET = os.environ.get("HRV_QUIET", "").strip().lower() in {"1", "true", "yes", "on"}

def _qprint(*args, **kwargs):
    if not QUIET:
        print(*args, **kwargs)

# Directorios
DATA_DIR = Path((os.environ.get("HRV_DATA_DIR") or ".").strip() or ".")
_rr_env = (os.environ.get("RR_DOWNLOAD_DIR") or "").strip()
RR_BASE_DIR = Path(_rr_env) if _rr_env else (DATA_DIR / "rr_downloads")

# Archivos de salida (nombres canónicos, sin fechas)
OUT_CORE = DATA_DIR / "ENDURANCE_HRV_master_CORE.csv"
OUT_BETA_AUDIT = DATA_DIR / "ENDURANCE_HRV_master_BETA_AUDIT.csv"

# Constantes de procesamiento
CONSTANTS = {
    "TAIL_TRIM_S": 15.0,      # Segundos a recortar del final
    "LAT_WIN_S": 60.0,        # Ventana para detección de latencia
    "LAT_STEP_S": 30.0,       # Paso de ventana
    "LAT_REL_EPS": 0.08,      # Umbral de estabilidad (8%)
    "TAIL_S": 120.0,          # Segundos de cola para estabilidad
    "TAIL_MIN_S": 75.0,       # Mínimo de cola aceptable
    "TAIL_MIN_PAIRS": 60,     # Mínimo de pares en cola
    "RR_MIN_MS": 300.0,       # RR mínimo válido (ms)
    "RR_MAX_MS": 2000.0,      # RR máximo válido (ms)
    "DELTA_RR_MAX": 0.20,     # Máximo delta relativo entre RR consecutivos
    "BETA_CAP_MAX": 3.0,      # Tope máximo de beta
}

# Columnas de salida
COLS_CORE = [
    "Fecha",
    "Calidad",
    "HRV_Stability",
    "Artifact_pct",
    "Tiempo_Estabilizacion",
    "HR_stable",
    "RRbar_s",
    "RMSSD_stable",
    "RMSSD_stable_last2",
    "lnRMSSD",
    "Flags",
    "Notes",
]

COLS_BETA_AUDIT = [
    "Fecha",
    "HR_stable",
    "RRbar_s",
    "RMSSD_stable",
    "lnRMSSD",
    "cRMSSD",
    "beta_mode",
    "beta_est_90d",
    "beta_use_90d",
    "R2_winsor_90d",
    "Color_Agudo_Diario",
    "Color_Tendencia",
    "Color_Tiebreak",
]


# ============================================================================
# HELPERS MATEMÁTICOS
# ============================================================================

def qtype7(arr, q: float) -> float:
    """Percentil tipo 7 (Hyndman & Fan), default en numpy/R."""
    a = np.asarray(arr, dtype=float)
    a = a[~np.isnan(a)]
    n = a.size
    if n == 0:
        return np.nan
    a.sort()
    if n == 1:
        return float(a[0])
    h = 1 + (n - 1) * q
    j = int(np.floor(h))
    g = h - j
    if j <= 1:
        return float(a[0])
    if j >= n:
        return float(a[-1])
    return float((1 - g) * a[j - 1] + g * a[j])


def winsor(a, qlo: float = 0.10, qhi: float = 0.90):
    """Winsorización de extremos."""
    a = np.asarray(a, dtype=float)
    lo = qtype7(a, qlo)
    hi = qtype7(a, qhi)
    return np.clip(a, lo, hi)


def rmssd_ms(rr_s) -> float:
    """RMSSD en milisegundos desde RR en segundos."""
    rr_s = np.asarray(rr_s, dtype=float)
    if rr_s.size < 2:
        return np.nan
    d = np.diff(rr_s)
    return float(np.sqrt(np.mean(d * d)) * 1000.0)


def robust_z(value: float, series) -> Tuple[float, int]:
    """Z-score robusto usando MAD."""
    s = np.asarray(series, dtype=float)
    s = s[~np.isnan(s)]
    if s.size == 0 or np.isnan(value):
        return np.nan, 0
    med = np.median(s)
    mad = np.median(np.abs(s - med))
    sigma = 1.4826 * mad
    if sigma == 0 or np.isnan(sigma):
        return np.nan, int(s.size)
    z = (value - med) / sigma
    z = float(np.clip(z, -5, 5))
    return z, int(s.size)


def ols_beta(x, y) -> Tuple[float, float]:
    """OLS simple: y = a + b*x. Devuelve (beta, R²)."""
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    m = ~np.isnan(x) & ~np.isnan(y)
    x, y = x[m], y[m]
    if x.size < 2:
        return np.nan, np.nan
    X = np.column_stack([np.ones(x.size), x])
    coef, *_ = np.linalg.lstsq(X, y, rcond=None)
    a, b = coef
    yhat = a + b * x
    ss_res = np.sum((y - yhat) ** 2)
    ss_tot = np.sum((y - np.mean(y)) ** 2)
    r2 = 1 - ss_res / ss_tot if ss_tot > 0 else np.nan
    return float(b), float(r2)


def parse_date_from_name(name: str) -> str:
    """Extrae fecha YYYY-MM-DD del nombre de archivo."""
    m = re.search(r"(\d{4}-\d{2}-\d{2})", name)
    if not m:
        raise ValueError(f"No puedo extraer Fecha de: {name}")
    return m.group(1)


# ============================================================================
# PROCESAMIENTO DE UN DÍA
# ============================================================================

def compute_day_from_rr(rr_path: Path, history_df: pd.DataFrame, C: dict) -> Tuple[dict, dict]:
    """
    Procesa un archivo RR y devuelve:
      - core_row: dict para CORE (medición)
      - beta_row: dict para BETA_AUDIT (legacy)
    """
    # Lectura del RR
    rr = pd.read_csv(rr_path)
    if not {"duration", "offline"}.issubset(rr.columns):
        raise ValueError("Header inválida. Debe ser: duration,offline")

    rr_ms = pd.to_numeric(rr["duration"], errors="coerce").astype(float).to_numpy()
    offline = pd.to_numeric(rr["offline"], errors="coerce").fillna(0).astype(int).to_numpy()
    offline = (offline != 0).astype(int)

    rr_ms = rr_ms[~np.isnan(rr_ms)]
    offline = offline[:rr_ms.size]

    # Eje temporal
    N_total = int(rr_ms.size)
    t_end_raw = np.cumsum(rr_ms) / 1000.0
    dur_raw = float(t_end_raw[-1]) if N_total else np.nan

    # Filtros: offline, OOR, delta
    N_off = int(np.sum(offline == 1))
    oor = (offline == 0) & ((rr_ms < C["RR_MIN_MS"]) | (rr_ms > C["RR_MAX_MS"]))
    N_oor = int(np.sum(oor))

    base = (offline == 0) & (~oor)
    rr_base = rr_ms[base]
    t_base = t_end_raw[base]
    N_base = int(rr_base.size)

    keep = np.ones(N_base, dtype=bool)
    N_drr = 0
    if N_base > 1:
        d = np.abs(rr_base[1:] - rr_base[:-1]) / rr_base[:-1]
        mark = d > C["DELTA_RR_MAX"]
        keep[1:] = ~mark
        N_drr = int(np.sum(mark))

    rr_clean = rr_base[keep]
    t_clean = t_base[keep]
    N_clean = int(rr_clean.size)

    artifact_pct = 100.0 * (N_off + N_oor + N_drr) / N_total if N_total else np.nan

    # Tail-trim
    t_end_eff = dur_raw - C["TAIL_TRIM_S"] if not np.isnan(dur_raw) else np.nan
    eff = t_clean <= t_end_eff
    rr_eff = rr_clean[eff]
    t_eff = t_clean[eff]

    # Latencia (ventanas 60s, paso 30s)
    max_t = float(t_end_eff) if not np.isnan(t_end_eff) else (float(t_eff[-1]) if t_eff.size else 0.0)
    nwin = int(np.floor(max_t / C["LAT_STEP_S"])) + 1 if max_t > 0 else 1
    rmssd_w = np.full(nwin, np.nan, dtype=float)

    for k in range(nwin):
        a = C["LAT_STEP_S"] * k
        b = a + C["LAT_WIN_S"]
        m = (t_eff >= a) & (t_eff < b)
        rr_w = rr_eff[m] / 1000.0
        if rr_w.size - 1 >= 20:
            rmssd_w[k] = rmssd_ms(rr_w)

    lat = np.nan

    def rel(a, b):
        if np.isnan(a) or np.isnan(b) or a <= 0:
            return np.nan
        return abs(b - a) / a

    # Criterio primario (8% consecutivo)
    for k in range(1, nwin - 1):
        if rel(rmssd_w[k-1], rmssd_w[k]) < C["LAT_REL_EPS"] and rel(rmssd_w[k], rmssd_w[k+1]) < C["LAT_REL_EPS"]:
            lat = float(C["LAT_STEP_S"] * k)
            break

    # Fallback (target mediano)
    if np.isnan(lat):
        valid = rmssd_w[~np.isnan(rmssd_w)]
        if valid.size >= 4:
            target = float(np.median(valid[-4:]))
            for k in range(0, nwin - 2):
                a, b, c = rmssd_w[k], rmssd_w[k+1], rmssd_w[k+2]
                if np.isnan(a) or np.isnan(b) or np.isnan(c) or target <= 0:
                    continue
                if abs(a-target)/target < C["LAT_REL_EPS"] and abs(b-target)/target < C["LAT_REL_EPS"] and abs(c-target)/target < C["LAT_REL_EPS"]:
                    lat = float(C["LAT_STEP_S"] * k)
                    break

    t_start_eff = 45.0 if np.isnan(lat) else max(lat, 45.0)

    # Métricas tramo estabilizado
    tramo = t_eff >= t_start_eff
    rr_tramo = rr_eff[tramo] / 1000.0
    RRbar_s = float(np.mean(rr_tramo)) if rr_tramo.size else np.nan
    HR = float(60.0 / RRbar_s) if (not np.isnan(RRbar_s) and RRbar_s > 0) else np.nan
    RMSSD = rmssd_ms(rr_tramo) if rr_tramo.size >= 2 else np.nan
    lnRMSSD = float(np.log(RMSSD)) if (not np.isnan(RMSSD) and RMSSD > 0) else np.nan

    # Cola (últimos 120s)
    tail_start = t_end_eff - C["TAIL_S"]
    tail = (t_eff >= tail_start) & (t_eff <= t_end_eff)
    rr_tail = rr_eff[tail] / 1000.0
    dur_tail_eff = float(t_eff[tail][-1] - t_eff[tail][0]) if np.sum(tail) > 1 else 0.0
    n_pairs_tail = int(rr_tail.size - 1)
    RMSSD_last2 = rmssd_ms(rr_tail) if rr_tail.size >= 2 else np.nan
    CV_120 = float(np.std(rr_tail) / np.mean(rr_tail)) if rr_tail.size > 1 and np.mean(rr_tail) > 0 else np.nan

    # Gate: Estabilidad y Calidad
    HRV_Stability = "OK"
    stab_flag = ""
    if dur_tail_eff < C["TAIL_MIN_S"] or n_pairs_tail < C["TAIL_MIN_PAIRS"]:
        HRV_Stability = "Unstable"
        stab_flag = "STAB_TAIL_SHORT"
    elif (not np.isnan(CV_120)) and CV_120 > 0.20:
        HRV_Stability = "Unstable"
        stab_flag = "STAB_CV120_HIGH"
    elif np.isnan(RMSSD_last2):
        HRV_Stability = "Unstable"
        stab_flag = "STAB_LAST2_NAN"
    elif (not np.isnan(RMSSD) and RMSSD > 0) and abs(RMSSD_last2 - RMSSD) / RMSSD > 0.15:
        HRV_Stability = "Unstable"
        stab_flag = "STAB_LAST2_MISMATCH"

    invalid = False
    if (not np.isnan(artifact_pct)) and artifact_pct > 20.0:
        invalid = True
    if (not np.isnan(HR)) and (HR < 35.0 or HR > 100.0):
        invalid = True

    if invalid:
        Calidad = "INVALID"
    else:
        Lat_eff = 60.0 if np.isnan(lat) else max(lat, 60.0)
        if (not np.isnan(lat)) and artifact_pct <= 10.0 and 60.0 <= Lat_eff <= 600.0 and HRV_Stability == "OK":
            Calidad = "OK"
        else:
            Calidad = "FLAG_mecánico"
        if np.isnan(lat):
            Calidad = "FLAG_mecánico"

    # ========================================================================
    # BETA / cRMSSD (90d shift-1) - Para BETA_AUDIT legacy
    # ========================================================================
    fecha_str = parse_date_from_name(rr_path.name)
    d = pd.to_datetime(fecha_str)

    hist = history_df.copy()
    if not hist.empty and "Fecha" in hist.columns:
        hist["Fecha_dt"] = pd.to_datetime(hist["Fecha"])
        win90 = hist[(hist["Fecha_dt"] >= d - pd.Timedelta(days=90)) & (hist["Fecha_dt"] <= d - pd.Timedelta(days=1))]
        win90 = win90[win90["Calidad"] != "INVALID"]
    else:
        win90 = pd.DataFrame()

    N90 = int(len(win90))
    rr90 = win90["RRbar_s"].to_numpy(dtype=float) if not win90.empty and "RRbar_s" in win90.columns else np.array([])
    IQR = qtype7(rr90, 0.75) - qtype7(rr90, 0.25) if rr90.size else np.nan
    RR_ref = float(np.median(rr90[~np.isnan(rr90)])) if np.sum(~np.isnan(rr90)) else np.nan

    prev_beta_use = np.nan
    if not hist.empty and "beta_use_90d" in hist.columns:
        prev = hist[hist["Fecha_dt"] < d].sort_values("Fecha_dt").tail(1)
        if len(prev) and not pd.isna(prev["beta_use_90d"].iloc[0]):
            prev_beta_use = float(prev["beta_use_90d"].iloc[0])

    prev_has = not np.isnan(prev_beta_use)

    beta_est = np.nan
    r2 = np.nan
    beta_use = np.nan
    beta_mode = "none"

    can_est = (N90 >= 60) and (not np.isnan(IQR)) and (IQR >= 0.03)
    if can_est and "RMSSD_stable" in win90.columns:
        x = np.log(win90["RRbar_s"].to_numpy(dtype=float))
        y = np.log(win90["RMSSD_stable"].to_numpy(dtype=float))
        xw = winsor(x)
        yw = winsor(y)
        beta_est, r2 = ols_beta(xw, yw)
        unstable = np.isnan(beta_est) or np.isnan(r2) or (r2 < 0.10) or (prev_has and abs(beta_est - prev_beta_use) > 0.15)
        if unstable:
            if prev_has:
                beta_use = prev_beta_use
                beta_mode = "frozen"
            else:
                beta_mode = "none"
        else:
            beta_use = float(np.clip(beta_est, 0.1, C["BETA_CAP_MAX"]))
            beta_mode = "clipped" if (beta_est > C["BETA_CAP_MAX"] or beta_est < 0.1) else "active"
    else:
        if prev_has:
            beta_use = prev_beta_use
            beta_mode = "frozen"

    if beta_mode in {"active", "clipped", "frozen"} and (not np.isnan(beta_use)) and (not np.isnan(RR_ref)) and (not np.isnan(RRbar_s)) and RR_ref > 0 and RRbar_s > 0 and (not np.isnan(RMSSD)):
        cRMSSD = float(RMSSD * (RRbar_s / RR_ref) ** (-beta_use))
    else:
        cRMSSD = float(RMSSD) if not np.isnan(RMSSD) else np.nan

    # ========================================================================
    # COLORES V3 (legacy, para BETA_AUDIT)
    # ========================================================================
    if not hist.empty and "Fecha_dt" in hist.columns:
        valid = hist[hist["Calidad"] != "INVALID"]
        win14 = valid[(pd.to_datetime(valid["Fecha"]) >= d - pd.Timedelta(days=14)) & (pd.to_datetime(valid["Fecha"]) <= d - pd.Timedelta(days=1))]
        win30 = valid[(pd.to_datetime(valid["Fecha"]) >= d - pd.Timedelta(days=30)) & (pd.to_datetime(valid["Fecha"]) <= d - pd.Timedelta(days=1))]
        win28 = valid[(pd.to_datetime(valid["Fecha"]) >= d - pd.Timedelta(days=28)) & (pd.to_datetime(valid["Fecha"]) <= d - pd.Timedelta(days=1))]
    else:
        win14 = win30 = win28 = pd.DataFrame()

    HR_z14 = np.nan
    if not win14.empty and "HR_stable" in win14.columns:
        HR_z14, _ = robust_z(HR, win14["HR_stable"].to_numpy(dtype=float))
        HR_z14 = float(np.round(HR_z14, 2)) if not np.isnan(HR_z14) else np.nan

    cprev = win30["cRMSSD"].to_numpy(dtype=float) if not win30.empty and "cRMSSD" in win30.columns else np.array([])
    Nprev30 = int(np.sum(~np.isnan(cprev)))
    P15 = qtype7(cprev, 0.15) if Nprev30 else np.nan
    P30 = qtype7(cprev, 0.30) if Nprev30 else np.nan

    lnprev = win28["lnRMSSD"].to_numpy(dtype=float) if not win28.empty and "lnRMSSD" in win28.columns else np.array([])
    z_HRV_28, n28 = robust_z(lnRMSSD, lnprev)

    lnc = float(np.log(cRMSSD)) if (not np.isnan(cRMSSD) and cRMSSD > 0) else np.nan
    lncprev = np.log(win28["cRMSSD"].to_numpy(dtype=float)) if not win28.empty and "cRMSSD" in win28.columns else np.array([])
    z_HRVc_28, _ = robust_z(lnc, lncprev)

    # Decisión de colores V3
    Color_Tendencia = "Indef"
    if Nprev30 >= 15 and not np.isnan(P15) and not np.isnan(P30) and not np.isnan(cRMSSD):
        if cRMSSD >= P30:
            Color_Tendencia = "Verde"
        elif cRMSSD >= P15:
            Color_Tendencia = "Ámbar"
        else:
            Color_Tendencia = "Rojo"
        if Color_Tendencia == "Verde" and not np.isnan(HR_z14) and (P30 > P15):
            if (cRMSSD - P30) < 0.10 * (P30 - P15) and HR_z14 >= 3.0:
                Color_Tendencia = "Ámbar"

    def p2(z):
        if np.isnan(z):
            return "Indef"
        if z >= -1.0:
            return "Verde"
        if z >= -2.0:
            return "Ámbar"
        return "Rojo"

    Color_Agudo = p2(z_HRV_28)
    Color_Tiebreak = p2(z_HRVc_28)

    if not np.isnan(HR_z14):
        if HR_z14 >= 3.8:
            Color_Agudo = "Rojo"
            Color_Tiebreak = "Rojo"
        elif HR_z14 >= 3.0:
            if Color_Agudo == "Verde":
                Color_Agudo = "Ámbar"
            if Color_Tiebreak == "Verde":
                Color_Tiebreak = "Ámbar"

    if Calidad == "INVALID":
        Color_Tendencia = Color_Agudo = Color_Tiebreak = "Indef"

    # ========================================================================
    # FLAGS & NOTES
    # ========================================================================
    flags = []
    if np.isnan(lat):
        flags.append("LAT_NAN")
    if artifact_pct > 10.0:
        flags.append("ART_GT10")
    if artifact_pct > 20.0:
        flags.append("ART_GT20")
    if stab_flag:
        flags.append(stab_flag)
    if beta_mode == "clipped":
        flags.append("BETA_CLIPPED")
    elif beta_mode == "frozen":
        flags.append("BETA_FROZEN")
    elif beta_mode == "none":
        flags.append("BETA_NONE")

    dur_tramo = (t_eff[tramo][-1] - t_start_eff) if np.sum(tramo) > 0 else 0.0
    n_tramo = int(np.sum(tramo))
    n_tail = int(np.sum(tail))

    notes = (
        f"src={rr_path.name}; "
        f"dur_raw={dur_raw:.1f}s; dur_eff={t_end_eff:.1f}s; "
        f"t_start_eff={t_start_eff:.1f}s; dur_tramo={dur_tramo:.1f}s; dur_tail={dur_tail_eff:.1f}s; "
        f"n_total={N_total}; n_base={N_base}; n_clean={N_clean}; n_tramo={n_tramo}; n_tail={n_tail}; "
        f"off={N_off}; oor={N_oor}; dRR={N_drr}; "
        f"lat_mode={'NUM' if not np.isnan(lat) else 'NAN'}; stab={HRV_Stability}"
    )

    # ========================================================================
    # CONSTRUIR ROWS
    # ========================================================================
    core_row = {
        "Fecha": fecha_str,
        "Calidad": Calidad,
        "HRV_Stability": HRV_Stability,
        "Artifact_pct": artifact_pct,
        "Tiempo_Estabilizacion": lat,
        "HR_stable": HR,
        "RRbar_s": RRbar_s,
        "RMSSD_stable": RMSSD,
        "RMSSD_stable_last2": RMSSD_last2,
        "lnRMSSD": lnRMSSD,
        "Flags": "|".join(flags),
        "Notes": notes,
    }

    beta_row = {
        "Fecha": fecha_str,
        "HR_stable": HR,
        "RRbar_s": RRbar_s,
        "RMSSD_stable": RMSSD,
        "lnRMSSD": lnRMSSD,
        "cRMSSD": cRMSSD,
        "beta_mode": beta_mode,
        "beta_est_90d": beta_est,
        "beta_use_90d": beta_use,
        "R2_winsor_90d": r2,
        "Color_Agudo_Diario": Color_Agudo,
        "Color_Tendencia": Color_Tendencia,
        "Color_Tiebreak": Color_Tiebreak,
    }

    return core_row, beta_row


def compute_day_from_rr_core_only(rr_path: Path, C: dict) -> Tuple[dict, None]:
    """
    Versión simplificada que solo calcula CORE (sin beta/cRMSSD).
    Usada como fallback cuando el procesamiento completo falla.
    """
    # Lectura del RR
    rr = pd.read_csv(rr_path)
    if not {"duration", "offline"}.issubset(rr.columns):
        raise ValueError("Header inválida. Debe ser: duration,offline")

    rr_ms = pd.to_numeric(rr["duration"], errors="coerce").astype(float).to_numpy()
    offline = pd.to_numeric(rr["offline"], errors="coerce").fillna(0).astype(int).to_numpy()
    offline = (offline != 0).astype(int)

    rr_ms = rr_ms[~np.isnan(rr_ms)]
    offline = offline[:rr_ms.size]

    N_total = int(rr_ms.size)
    t_end_raw = np.cumsum(rr_ms) / 1000.0
    dur_raw = float(t_end_raw[-1]) if N_total else np.nan

    # Filtros básicos
    N_off = int(np.sum(offline == 1))
    oor = (offline == 0) & ((rr_ms < C["RR_MIN_MS"]) | (rr_ms > C["RR_MAX_MS"]))
    N_oor = int(np.sum(oor))

    base = (offline == 0) & (~oor)
    rr_base = rr_ms[base]
    t_base = t_end_raw[base]
    N_base = int(rr_base.size)

    keep = np.ones(N_base, dtype=bool)
    N_drr = 0
    if N_base > 1:
        d = np.abs(rr_base[1:] - rr_base[:-1]) / rr_base[:-1]
        mark = d > C["DELTA_RR_MAX"]
        keep[1:] = ~mark
        N_drr = int(np.sum(mark))

    rr_clean = rr_base[keep]
    t_clean = t_base[keep]
    N_clean = int(rr_clean.size)

    artifact_pct = 100.0 * (N_off + N_oor + N_drr) / N_total if N_total else np.nan

    # Tail-trim y tramo
    t_end_eff = dur_raw - C["TAIL_TRIM_S"] if not np.isnan(dur_raw) else np.nan
    eff = t_clean <= t_end_eff
    rr_eff = rr_clean[eff]
    t_eff = t_clean[eff]

    # Latencia simplificada (usar 45s como fallback)
    t_start_eff = 45.0

    # Métricas tramo
    tramo = t_eff >= t_start_eff
    rr_tramo = rr_eff[tramo] / 1000.0
    RRbar_s = float(np.mean(rr_tramo)) if rr_tramo.size else np.nan
    HR = float(60.0 / RRbar_s) if (not np.isnan(RRbar_s) and RRbar_s > 0) else np.nan
    RMSSD = rmssd_ms(rr_tramo) if rr_tramo.size >= 2 else np.nan
    lnRMSSD = float(np.log(RMSSD)) if (not np.isnan(RMSSD) and RMSSD > 0) else np.nan

    # Cola
    tail_start = t_end_eff - C["TAIL_S"]
    tail = (t_eff >= tail_start) & (t_eff <= t_end_eff)
    rr_tail = rr_eff[tail] / 1000.0
    dur_tail_eff = float(t_eff[tail][-1] - t_eff[tail][0]) if np.sum(tail) > 1 else 0.0
    n_pairs_tail = int(rr_tail.size - 1)
    RMSSD_last2 = rmssd_ms(rr_tail) if rr_tail.size >= 2 else np.nan

    # Calidad simplificada
    HRV_Stability = "OK"
    if dur_tail_eff < C["TAIL_MIN_S"] or n_pairs_tail < C["TAIL_MIN_PAIRS"]:
        HRV_Stability = "Unstable"
    elif np.isnan(RMSSD_last2):
        HRV_Stability = "Unstable"

    invalid = (not np.isnan(artifact_pct) and artifact_pct > 20.0) or \
              (not np.isnan(HR) and (HR < 35.0 or HR > 100.0))
    
    Calidad = "INVALID" if invalid else "FLAG_mecánico"  # Siempre FLAG en modo rescate

    fecha_str = parse_date_from_name(rr_path.name)
    
    core_row = {
        "Fecha": fecha_str,
        "Calidad": Calidad,
        "HRV_Stability": HRV_Stability,
        "Artifact_pct": artifact_pct,
        "Tiempo_Estabilizacion": np.nan,  # No calculada en modo rescate
        "HR_stable": HR,
        "RRbar_s": RRbar_s,
        "RMSSD_stable": RMSSD,
        "RMSSD_stable_last2": RMSSD_last2,
        "lnRMSSD": lnRMSSD,
        "Flags": "RESCUE_MODE",
        "Notes": f"src={rr_path.name}; rescue_mode=True",
    }

    return core_row, None


# ============================================================================
# GESTIÓN DE DATAFRAMES
# ============================================================================

def get_or_create_df(path: Path, columns: List[str]) -> pd.DataFrame:
    """Carga CSV si existe, o crea DataFrame vacío."""
    if path.exists():
        try:
            df = pd.read_csv(path)
            if "Fecha" in df.columns:
                df["Fecha"] = df["Fecha"].astype(str)
            return df
        except Exception as e:
            print(f"Advertencia: No se pudo leer {path} ({e}). Creando nuevo.")
            return pd.DataFrame(columns=columns)
    else:
        _qprint(f"Info: {path} no existe. Creando archivo nuevo.")
        return pd.DataFrame(columns=columns)


def upsert_row(df: pd.DataFrame, row: dict, columns: List[str]) -> pd.DataFrame:
    """Inserta o actualiza fila por Fecha."""
    fecha = row["Fecha"]
    
    # Eliminar fila existente con misma fecha
    if not df.empty:
        df = df[df["Fecha"] != fecha].copy()
    
    # Crear nueva fila con todas las columnas
    new_row = {c: np.nan for c in columns}
    for k, v in row.items():
        if k in new_row:
            new_row[k] = v
    
    # Añadir y ordenar
    df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
    df = df.sort_values("Fecha").reset_index(drop=True)
    
    return df


# ============================================================================
# MAIN
# ============================================================================

def find_rr_files(rr_dir: Path) -> List[Path]:
    """Encuentra todos los archivos RR en un directorio."""
    patterns = ["*_RR.csv", "*_RR.CSV", "*_rr.csv"]
    files = []
    for pattern in patterns:
        files.extend(rr_dir.glob(pattern))
    return sorted(set(files), key=lambda p: parse_date_from_name(p.name))


def main():
    parser = argparse.ArgumentParser(description="ENDURANCE HRV - Procesador de medición")
    parser.add_argument("--rr-dir", type=str, help="Directorio con archivos RR")
    parser.add_argument("--rr-file", type=str, action="append", help="Archivo RR específico (puede repetirse)")
    parser.add_argument("--data-dir", type=str, help="Directorio de datos (override HRV_DATA_DIR)")
    args = parser.parse_args()

    global DATA_DIR, OUT_CORE, OUT_BETA_AUDIT

    if args.data_dir:
        DATA_DIR = Path(args.data_dir)
        OUT_CORE = DATA_DIR / "ENDURANCE_HRV_master_CORE.csv"
        OUT_BETA_AUDIT = DATA_DIR / "ENDURANCE_HRV_master_BETA_AUDIT.csv"

    DATA_DIR.mkdir(parents=True, exist_ok=True)

    # Determinar archivos a procesar
    rr_files = []
    if args.rr_file:
        rr_files = [Path(f) for f in args.rr_file]
    elif args.rr_dir:
        rr_files = find_rr_files(Path(args.rr_dir))
    else:
        # Buscar en directorio por defecto
        if RR_BASE_DIR.exists():
            rr_files = find_rr_files(RR_BASE_DIR)

    if not rr_files:
        print("No se encontraron archivos RR para procesar.")
        print(f"Usa --rr-dir o --rr-file, o coloca archivos en {RR_BASE_DIR}")
        sys.exit(1)

    _qprint(f"\n📂 Procesando {len(rr_files)} archivo(s) RR...")

    # Cargar DataFrames existentes
    core_df = get_or_create_df(OUT_CORE, COLS_CORE)
    beta_df = get_or_create_df(OUT_BETA_AUDIT, COLS_BETA_AUDIT)

    # Para el cálculo de beta, necesitamos un historial combinado
    # Usamos CORE + BETA_AUDIT combinados
    if not core_df.empty and not beta_df.empty:
        history_df = core_df.merge(
            beta_df[["Fecha", "cRMSSD", "beta_use_90d"]],
            on="Fecha",
            how="left"
        )
    else:
        history_df = core_df.copy()

    # Procesar cada archivo
    processed = []
    for rr_path in rr_files:
        if not rr_path.exists():
            print(f"⚠️  Archivo no encontrado: {rr_path}")
            continue

        # CORE: siempre se intenta escribir si el RR es parseable
        # BETA_AUDIT: best-effort, nunca bloquea CORE
        core_row = None
        beta_row = None
        
        try:
            core_row, beta_row = compute_day_from_rr(rr_path, history_df, CONSTANTS)
        except Exception as e:
            # Si falla el procesamiento completo, intentar al menos CORE básico
            print(f"⚠️  Error en procesamiento completo de {rr_path.name}: {e}")
            try:
                core_row, _ = compute_day_from_rr_core_only(rr_path, CONSTANTS)
                print(f"   → CORE rescatado (sin BETA_AUDIT)")
            except Exception as e2:
                print(f"❌ Error irrecuperable en {rr_path.name}: {e2}")
                continue
        
        # Escribir CORE (siempre si tenemos core_row)
        if core_row is not None:
            core_df = upsert_row(core_df, core_row, COLS_CORE)
            processed.append({
                "Fecha": core_row["Fecha"],
                "Calidad": core_row["Calidad"],
                "HR": core_row["HR_stable"],
                "RMSSD": core_row["RMSSD_stable"],
            })
            _qprint(f"  ✓ {core_row['Fecha']}: Calidad={core_row['Calidad']}, HR={core_row['HR_stable']:.1f}, RMSSD={core_row['RMSSD_stable']:.1f}")
        
        # Escribir BETA_AUDIT (best-effort)
        if beta_row is not None:
            beta_df = upsert_row(beta_df, beta_row, COLS_BETA_AUDIT)
        elif core_row is not None:
            # Si no hay beta_row pero sí core_row, crear beta_row vacío
            beta_row = {
                "Fecha": core_row["Fecha"],
                "HR_stable": core_row["HR_stable"],
                "RRbar_s": core_row["RRbar_s"],
                "RMSSD_stable": core_row["RMSSD_stable"],
                "lnRMSSD": core_row["lnRMSSD"],
                "cRMSSD": np.nan,
                "beta_mode": "none",
                "beta_est_90d": np.nan,
                "beta_use_90d": np.nan,
                "R2_winsor_90d": np.nan,
                "Color_Agudo_Diario": "Indef",
                "Color_Tendencia": "Indef",
                "Color_Tiebreak": "Indef",
            }
            beta_df = upsert_row(beta_df, beta_row, COLS_BETA_AUDIT)
            _qprint(f"   → BETA_AUDIT: NaN (sin historial)")
        
        # Actualizar historial para siguientes archivos
        if not core_df.empty and not beta_df.empty:
            history_df = core_df.merge(
                beta_df[["Fecha", "cRMSSD", "beta_use_90d"]],
                on="Fecha",
                how="left"
            )

    if not processed:
        print("No se procesó ningún archivo.")
        sys.exit(1)

    # Backup y guardar
    ts = time.strftime("%Y%m%d_%H%M%S")
    disable_backup = os.environ.get("HRV_DISABLE_BACKUP", "").strip().lower() in {"1", "true", "yes", "on"}

    if not disable_backup:
        backup_dir = DATA_DIR / "backup"
        backup_dir.mkdir(exist_ok=True)
        
        if OUT_CORE.exists():
            shutil.copy2(OUT_CORE, backup_dir / f"CORE_backup_{ts}.csv")
        if OUT_BETA_AUDIT.exists():
            shutil.copy2(OUT_BETA_AUDIT, backup_dir / f"BETA_AUDIT_backup_{ts}.csv")
        _qprint(f"\n📦 Backups en {backup_dir}/")

    # Guardar
    core_df.to_csv(OUT_CORE, index=False)
    beta_df.to_csv(OUT_BETA_AUDIT, index=False)

    print(f"\n{'='*50}")
    print("✅ ENDURANCE HRV - Procesamiento completado")
    print(f"{'='*50}")
    print(f"📄 CORE:       {OUT_CORE} ({len(core_df)} filas)")
    print(f"📄 BETA_AUDIT: {OUT_BETA_AUDIT} ({len(beta_df)} filas)")
    print(f"\nÚltimas fechas procesadas:")
    for p in processed[-5:]:
        print(f"   {p['Fecha']}: HR={p['HR']:.1f} lpm, RMSSD={p['RMSSD']:.1f} ms")
    print(f"\n➡️  Ejecuta 'python endurance_v4lite.py' para generar FINAL y DASHBOARD")


if __name__ == "__main__":
    main()
