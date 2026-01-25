#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ENDURANCE HRV — Batch processor (Spec-aligned) — inputs set in code

This script is designed to match the normative artifacts:
- ENDURANCE_HRV_Spec_Tecnica_Implementacion.md (calculation rules)
- ENDURANCE_HRV_Estructura_Datos_Master.md (data contract / columns)

What it does:
- Processes one or more RR CSV files (Polar) with header: duration,offline
- Upserts by Fecha (no duplicates) into:
  - ENDURANCE_HRV_master_ALL.csv
  - ENDURANCE_HRV_eval_P1P2_ALL.csv
- Emits QA rolling 30/90 markdown.

Important: This script will NOT add columns. It only fills columns already present
in the base master/eval files.

Run:
  python endurance_hrv.py

Edit the INPUTS block below to point to your files.
"""


# endurance_hrv_batch.py
# Requiere: python 3.10+ ; pip install pandas numpy

import re
import time
import shutil
from pathlib import Path
import numpy as np
import pandas as pd

# ----------------------------
# 1. INPUTS Y CONSTANTES (PUNTO 4.1 - ROBUSTEZ)
# ----------------------------
BASE_MASTER = Path("ENDURANCE_HRV_master_ALL.csv")
BASE_EVAL   = Path("ENDURANCE_HRV_eval_P1P2_ALL.csv")

# Lista de archivos a procesar (esto normalmente lo cargarías con glob)
RR_FILES = [
    Path("rr_downloads/Franz_Dunn_2026-01-25_08-42-27_RR.CSV"),
]

# Definición directa de constantes (Evita leer el MD)
CONSTANTS = {
    "TAIL_TRIM_S": 15.0,
    "LAT_WIN_S":   60.0,
    "LAT_STEP_S":  30.0,
    "LAT_REL_EPS": 0.08,
    "TAIL_S":      120.0,
    "TAIL_MIN_S":  75.0,
    "TAIL_MIN_PAIRS": 60,
    "RR_MIN_MS":   300.0,
    "RR_MAX_MS":   2000.0,
    "DELTA_RR_MAX": 0.20,
    "BETA_CAP_MAX": 3.0,
}

# ----------------------------
# 2. HELPERS MATEMÁTICOS
# ----------------------------
def qtype7(arr, q):
    """Percentil tipo 7 (Hyndman & Fan), default en numpy/S."""
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

def winsor(a, qlo=0.10, qhi=0.90):
    a = np.asarray(a, dtype=float)
    lo = qtype7(a, qlo)
    hi = qtype7(a, qhi)
    return np.clip(a, lo, hi)

def rmssd_ms(rr_s):
    rr_s = np.asarray(rr_s, dtype=float)
    if rr_s.size < 2:
        return np.nan
    d = np.diff(rr_s)
    return float(np.sqrt(np.mean(d * d)) * 1000.0)

def robust_z(value, series):
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

def ols_beta(x, y):
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    m = ~np.isnan(x) & ~np.isnan(y)
    x = x[m]; y = y[m]
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
    m = re.search(r"(\d{4}-\d{2}-\d{2})", name)
    if not m:
        raise ValueError(f"No puedo extraer Fecha de: {name}")
    return m.group(1)

# ----------------------------
# 3. HELPER DE INICIALIZACIÓN (PUNTO 4.2 - SEGURIDAD)
# ----------------------------
def get_or_create_df(path: Path, columns: list) -> pd.DataFrame:
    """Carga el CSV si existe, o crea uno vacío con las columnas correctas."""
    if path.exists():
        try:
            df = pd.read_csv(path)
            # Asegurar que Fecha sea string para evitar problemas de parseo
            if "Fecha" in df.columns:
                df["Fecha"] = df["Fecha"].astype(str)
            return df
        except Exception as e:
            print(f"Advertencia: No se pudo leer {path} ({e}). Creando nuevo.")
            return pd.DataFrame(columns=columns)
    else:
        print(f"Info: {path} no existe. Creando archivo nuevo.")
        return pd.DataFrame(columns=columns)

# ----------------------------
# 4. LÓGICA CORE: Procesar 1 día (RR -> Métricas)
# ----------------------------
def compute_day_from_rr(rr_path: Path, master_hist: pd.DataFrame, C: dict):
    # Lectura del RR RAW
    rr = pd.read_csv(rr_path)
    if not {"duration", "offline"}.issubset(rr.columns):
        raise ValueError("Header inválida. Debe ser: duration,offline")

    rr_ms = pd.to_numeric(rr["duration"], errors="coerce").astype(float).to_numpy()
    offline = pd.to_numeric(rr["offline"], errors="coerce").fillna(0).astype(int).to_numpy()
    offline = (offline != 0).astype(int)

    rr_ms = rr_ms[~np.isnan(rr_ms)]
    offline = offline[: rr_ms.size]

    # Eje temporal acumulado (NO comprimido)
    N_total = int(rr_ms.size)
    t_end_raw = np.cumsum(rr_ms) / 1000.0
    dur_raw = float(t_end_raw[-1]) if N_total else np.nan

    # Filtros básicos y Anti-cascada (Oor, offline, delta)
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
        # Delta relativo contra el ANTERIOR (aunque esté marcado)
        d = np.abs(rr_base[1:] - rr_base[:-1]) / rr_base[:-1]
        mark = d > C["DELTA_RR_MAX"]
        keep[1:] = ~mark
        N_drr = int(np.sum(mark))

    rr_clean = rr_base[keep]
    t_clean = t_base[keep]
    N_clean = int(rr_clean.size)

    artifact_pct = 100.0 * (N_off + N_oor + N_drr) / N_total if N_total else np.nan

    # Tail-trim (Recorte de cola)
    t_end_eff = dur_raw - C["TAIL_TRIM_S"] if not np.isnan(dur_raw) else np.nan
    eff = t_clean <= t_end_eff
    rr_eff = rr_clean[eff]
    t_eff = t_clean[eff]

    # --- Latencia (Ventanas 60s, paso 30s) ---
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
    
    # Fallback (Target mediano)
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

    # Inicio efectivo métricas
    t_start_eff = 45.0 if np.isnan(lat) else max(lat, 45.0)

    # --- Métricas Tramo Estabilizado ---
    tramo = t_eff >= t_start_eff
    rr_tramo = rr_eff[tramo] / 1000.0
    RRbar_s = float(np.mean(rr_tramo)) if rr_tramo.size else np.nan
    HR = float(60.0 / RRbar_s) if (not np.isnan(RRbar_s) and RRbar_s > 0) else np.nan
    RMSSD = rmssd_ms(rr_tramo) if rr_tramo.size >= 2 else np.nan
    lnRMSSD = float(np.log(RMSSD)) if (not np.isnan(RMSSD) and RMSSD > 0) else np.nan

    # Cola (últimos 120s para estabilidad)
    tail_start = t_end_eff - C["TAIL_S"]
    tail = (t_eff >= tail_start) & (t_eff <= t_end_eff)
    rr_tail = rr_eff[tail] / 1000.0
    dur_tail_eff = float(t_eff[tail][-1] - t_eff[tail][0]) if np.sum(tail) > 1 else 0.0
    n_pairs_tail = int(rr_tail.size - 1)
    RMSSD_last2 = rmssd_ms(rr_tail) if rr_tail.size >= 2 else np.nan
    CV_120 = float(np.std(rr_tail) / np.mean(rr_tail)) if rr_tail.size > 1 and np.mean(rr_tail) > 0 else np.nan

    # --- Gate: Estabilidad y Calidad ---
    HRV_Stability = "OK"
    stab_flag = ""
    if dur_tail_eff < C["TAIL_MIN_S"] or n_pairs_tail < C["TAIL_MIN_PAIRS"]:
        HRV_Stability = "Unstable"; stab_flag = "STAB_TAIL_SHORT"
    elif (not np.isnan(CV_120)) and CV_120 > 0.20:
        HRV_Stability = "Unstable"; stab_flag = "STAB_CV120_HIGH"
    elif np.isnan(RMSSD_last2):
        HRV_Stability = "Unstable"; stab_flag = "STAB_LAST2_NAN"
    elif (not np.isnan(RMSSD) and RMSSD > 0) and abs(RMSSD_last2 - RMSSD) / RMSSD > 0.15:
        HRV_Stability = "Unstable"; stab_flag = "STAB_LAST2_MISMATCH"

    invalid = False
    if (not np.isnan(artifact_pct)) and artifact_pct > 20.0:
        invalid = True
    if (not np.isnan(HR)) and (HR < 35.0 or HR > 100.0):
        invalid = True

    if invalid:
        Calidad = "INVALID"
    else:
        # Lat_eff para decisión interna (no se guarda)
        Lat_eff = 60.0 if np.isnan(lat) else max(lat, 60.0)
        # Regla: lat NaN fuerza FLAG
        if (not np.isnan(lat)) and artifact_pct <= 10.0 and 60.0 <= Lat_eff <= 600.0 and HRV_Stability == "OK":
            Calidad = "OK"
        else:
            Calidad = "FLAG_mecánico"
        if np.isnan(lat):
            Calidad = "FLAG_mecánico"

    # --- BETA / cRMSSD (90d shift-1) ---
    d = pd.to_datetime(parse_date_from_name(rr_path.name))
    
    # Preparar historia
    hist = master_hist.copy()
    if not hist.empty:
        hist["Fecha_dt"] = pd.to_datetime(hist["Fecha"])
        win90 = hist[(hist["Fecha_dt"] >= d - pd.Timedelta(days=90)) & (hist["Fecha_dt"] <= d - pd.Timedelta(days=1))]
        win90 = win90[win90["Calidad"] != "INVALID"]
    else:
        win90 = pd.DataFrame()

    N90 = int(len(win90))
    rr90 = win90["RRbar_s"].to_numpy(dtype=float) if not win90.empty else np.array([])
    IQR = qtype7(rr90, 0.75) - qtype7(rr90, 0.25) if rr90.size else np.nan
    RR_ref = float(np.median(rr90[~np.isnan(rr90)])) if np.sum(~np.isnan(rr90)) else np.nan

    prev_beta_use = np.nan
    if not hist.empty:
        prev = hist[hist["Fecha_dt"] < d].sort_values("Fecha_dt").tail(1)
        if len(prev) and not pd.isna(prev["beta_use_90d"].iloc[0]):
            prev_beta_use = float(prev["beta_use_90d"].iloc[0])
    
    prev_has = not np.isnan(prev_beta_use)

    beta_est = np.nan
    r2 = np.nan
    beta_use = np.nan
    beta_mode = "none"

    can_est = (N90 >= 60) and (not np.isnan(IQR)) and (IQR >= 0.03)
    if can_est:
        x = np.log(win90["RRbar_s"].to_numpy(dtype=float))
        y = np.log(win90["RMSSD_stable"].to_numpy(dtype=float))
        xw = winsor(x); yw = winsor(y)
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
        ln_corr = float(np.log(cRMSSD / RMSSD)) if RMSSD > 0 else np.nan
    else:
        cRMSSD = float(RMSSD) if not np.isnan(RMSSD) else np.nan
        ln_corr = 0.0 if not np.isnan(RMSSD) else np.nan

    # --- Windows 14/28/30 shift-1 + Colores ---
    if not hist.empty:
        valid = hist[hist["Calidad"] != "INVALID"]
        win14 = valid[(pd.to_datetime(valid["Fecha"]) >= d - pd.Timedelta(days=14)) & (pd.to_datetime(valid["Fecha"]) <= d - pd.Timedelta(days=1))]
        win30 = valid[(pd.to_datetime(valid["Fecha"]) >= d - pd.Timedelta(days=30)) & (pd.to_datetime(valid["Fecha"]) <= d - pd.Timedelta(days=1))]
        win28 = valid[(pd.to_datetime(valid["Fecha"]) >= d - pd.Timedelta(days=28)) & (pd.to_datetime(valid["Fecha"]) <= d - pd.Timedelta(days=1))]
    else:
        win14 = win30 = win28 = pd.DataFrame()

    HR_z14 = np.nan
    if not win14.empty:
        HR_z14, _ = robust_z(HR, win14["HR_stable"].to_numpy(dtype=float))
        HR_z14 = float(np.round(HR_z14, 2)) if not np.isnan(HR_z14) else np.nan

    cprev = win30["cRMSSD"].to_numpy(dtype=float) if not win30.empty else np.array([])
    Nprev30 = int(np.sum(~np.isnan(cprev)))
    P15 = qtype7(cprev, 0.15) if Nprev30 else np.nan
    P30 = qtype7(cprev, 0.30) if Nprev30 else np.nan

    lnprev = win28["lnRMSSD"].to_numpy(dtype=float) if not win28.empty else np.array([])
    z_HRV_28, n28 = robust_z(lnRMSSD, lnprev)

    lnc = float(np.log(cRMSSD)) if (not np.isnan(cRMSSD) and cRMSSD > 0) else np.nan
    lncprev = np.log(win28["cRMSSD"].to_numpy(dtype=float)) if not win28.empty else np.array([])
    z_HRVc_28, _ = robust_z(lnc, lncprev)

    # --- Decisión de Colores ---
    Color_Tendencia = "Indef"
    if Nprev30 >= 15 and not np.isnan(P15) and not np.isnan(P30) and not np.isnan(cRMSSD):
        if cRMSSD >= P30:
            Color_Tendencia = "Verde"
        elif cRMSSD >= P15:
            Color_Tendencia = "Ámbar"
        else:
            Color_Tendencia = "Rojo"
        # Modulación Verde falso
        if Color_Tendencia == "Verde" and not np.isnan(HR_z14) and (P30 > P15):
            if (cRMSSD - P30) < 0.10 * (P30 - P15) and HR_z14 >= 3.0:
                Color_Tendencia = "Ámbar"

    def p2(z):
        if np.isnan(z): return "Indef"
        if z >= -1.0: return "Verde"
        if z >= -2.0: return "Ámbar"
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

    # --- Flags & Notes ---
    flags = []
    if np.isnan(lat): flags.append("LAT_NAN")
    if artifact_pct > 10.0: flags.append("ART_GT10")
    if artifact_pct > 20.0: flags.append("ART_GT20")
    if stab_flag: flags.append(stab_flag)
    if beta_mode == "clipped": flags.append("BETA_CLIPPED")
    elif beta_mode == "frozen": flags.append("BETA_FROZEN")
    elif beta_mode == "none": flags.append("BETA_NONE")

    dur_tramo = (t_eff[tramo][-1] - t_start_eff) if np.sum(tramo) > 0 else 0.0
    n_tramo = int(np.sum(tramo))
    n_tail = int(np.sum(tail))

    notes = (
        f"src={rr_path.name}; "
        f"dur_raw={dur_raw:.1f}s; dur_eff={t_end_eff:.1f}s; "
        f"t_start_eff={t_start_eff:.1f}s; dur_tramo={dur_tramo:.1f}s; dur_tail={dur_tail_eff:.1f}s; "
        f"n_total={N_total}; n_base={N_base}; n_clean={N_clean}; n_tramo={n_tramo}; n_tail={n_tail}; "
        f"off={N_off}; oor={N_oor}; dRR={N_drr}; "
        f"lat_mode={'NUM' if not np.isnan(lat) else 'NAN'}; stab={HRV_Stability}; "
        f"note_free="
    )

    day = {
        "Fecha": parse_date_from_name(rr_path.name),
        "Calidad": Calidad,
        "HRV_Stability": HRV_Stability,
        "Artifact_pct": artifact_pct,
        "Tiempo_Estabilizacion": lat,
        "HR_stable": HR,
        "RRbar_s": RRbar_s,
        "RMSSD_stable": RMSSD,
        "RMSSD_stable_last2": RMSSD_last2,
        "lnRMSSD": lnRMSSD,
        "cRMSSD": cRMSSD,
        "beta_est_90d": beta_est,
        "beta_use_90d": beta_use,
        "beta_mode": beta_mode,
        "RR_ref_90d": RR_ref,
        "N90_valid": float(N90),
        "IQR_RRbar_90d": float(IQR) if not np.isnan(IQR) else np.nan,
        "R2_winsor_90d": r2,
        "ln_corr": ln_corr,
        "Nprev30": Nprev30,
        "P15_cRMSSD_30d": P15,
        "P30_cRMSSD_30d": P30,
        "HR_z14": HR_z14,
        "Color_Tendencia": Color_Tendencia,
        "Color_Agudo_Diario": Color_Agudo,
        "Color_Tiebreak": Color_Tiebreak,
        "Flags": "|".join(flags),
        "Notes": notes,
    }

    def p1(z):
        if np.isnan(z): return "Indef"
        if z >= -0.8: return "Verde"
        if z >= -1.6: return "Ámbar"
        return "Rojo"

    Color_P1 = p1(z_HRV_28)
    Color_P1_lnc = p1(z_HRVc_28)
    if not np.isnan(HR_z14) and HR_z14 >= 3.0:
        if Color_P1 != "Indef": Color_P1 = "Rojo"
        if Color_P1_lnc != "Indef": Color_P1_lnc = "Rojo"
    if Calidad == "INVALID":
        Color_P1 = Color_P1_lnc = "Indef"

    eval_row = {
        "Fecha": day["Fecha"],
        "Calidad": Calidad,
        "HRV_Stability": HRV_Stability,
        "lnRMSSD": lnRMSSD,
        "cRMSSD": cRMSSD,
        "RRbar_s": RRbar_s,
        "HR_stable": HR,
        "z_HRV_28": z_HRV_28,
        "z_HRVc_28": z_HRVc_28,
        "HR_z14": HR_z14,
        "Nprev28_lnRMSSD": float(n28),
        "Nprev28_lncRMSSD": float(np.sum(~np.isnan(lncprev))),
        "Nprev14_HR": float(len(win14)),
        "Color_P1": Color_P1,
        "Color_P1_lncRMSSD": Color_P1_lnc,
        "Color_Agudo_Diario": Color_Agudo,
        "Color_Tiebreak": Color_Tiebreak,
        "Color_Tendencia": Color_Tendencia,
    }

    summary = {
        "Fecha": day["Fecha"],
        "Calidad": Calidad,
        "Stab": HRV_Stability,
        "HR": HR,
        "RMSSD": RMSSD,
        "cRMSSD": cRMSSD,
        "P2": Color_Agudo,
        "Trend": Color_Tendencia,
        "Tiebreak": Color_Tiebreak,  # AGREGADO
        "Flags": day["Flags"],
        "Artifact_pct": artifact_pct,
        "Lat_s": lat,
    }

    return day, eval_row, summary

# ----------------------------
# 5. QA ROLLING
# ----------------------------
def qa_rolling_md(master: pd.DataFrame, asof: str) -> str:
    df = master.copy()
    if df.empty:
        return "# QA Report\n\nNo data available."
    
    df["Fecha_dt"] = pd.to_datetime(df["Fecha"])
    d = pd.to_datetime(asof)

    out = []
    out.append(f"# ENDURANCE_HRV_QA_rolling_30_90")
    out.append(f"- asof: {asof}")
    out.append("")

    for w in [30, 90]:
        a = d - pd.Timedelta(days=w)
        win = df[(df["Fecha_dt"] > a) & (df["Fecha_dt"] <= d)]
        n = len(win)
        ok = int(np.sum(win["Calidad"] == "OK"))
        flag = int(np.sum(win["Calidad"] == "FLAG_mecánico"))
        inv = int(np.sum(win["Calidad"] == "INVALID"))
        indef = int(np.sum(win["Color_Agudo_Diario"] == "Indef"))

        out.append(f"## Rolling {w}d")
        out.append(f"- filas: {n}")
        out.append(f"- Calidad: OK={ok} | FLAG={flag} | INVALID={inv}")
        out.append(f"- Indef: {indef}")
        if n > 0:
            out.append(f"- cRMSSD median: {np.nanmedian(win['cRMSSD']):.2f} ms")
            out.append(f"- HR_stable median: {np.nanmedian(win['HR_stable']):.2f} lpm")
        else:
            out.append("- Sin datos en ventana.")
        out.append("")

    return "\n".join(out)

# ----------------------------
# 6. MAIN EXECUTION
# ----------------------------
def main():
    # Estructuras de columnas explícitas para Inicialización Segura
    COLS_MASTER = [
        "Fecha", "Calidad", "HRV_Stability", "Artifact_pct", "Tiempo_Estabilizacion",
        "HR_stable", "RRbar_s", "RMSSD_stable", "RMSSD_stable_last2",
        "lnRMSSD", "cRMSSD", 
        "beta_est_90d", "beta_use_90d", "beta_mode", "RR_ref_90d", 
        "N90_valid", "IQR_RRbar_90d", "R2_winsor_90d", "ln_corr",
        "Nprev30", "P15_cRMSSD_30d", "P30_cRMSSD_30d", "HR_z14",
        "Color_Tendencia", "Color_Agudo_Diario", "Color_Tiebreak",
        "Flags", "Notes"
    ]
    
    COLS_EVAL = [
        "Fecha", "Calidad", "HRV_Stability", "lnRMSSD", "cRMSSD", 
        "RRbar_s", "HR_stable", "z_HRV_28", "z_HRVc_28", "HR_z14", 
        "Nprev28_lnRMSSD", "Nprev28_lncRMSSD", "Nprev14_HR", 
        "Color_P1", "Color_P1_lncRMSSD", "Color_Agudo_Diario", 
        "Color_Tiebreak", "Color_Tendencia"
    ]

    # Carga segura (Punto 4.2)
    master = get_or_create_df(BASE_MASTER, COLS_MASTER)
    evalp = get_or_create_df(BASE_EVAL, COLS_EVAL)

    # Procesar
    rr_sorted = sorted(RR_FILES, key=lambda p: parse_date_from_name(p.name))
    summaries = []

    for rr_path in rr_sorted:
        if not rr_path.exists():
            print(f"Skipping missing file: {rr_path}")
            continue

        try:
            # Pasamos CONSTANTS directamente (Punto 4.1)
            day, eval_row, summary = compute_day_from_rr(rr_path, master, CONSTANTS)

            # Upsert Master
            if not master.empty:
                master = master[master["Fecha"] != day["Fecha"]].copy()
            
            new_row = {c: np.nan for c in COLS_MASTER}
            for k, v in day.items():
                if k in new_row:
                    new_row[k] = v
            master = pd.concat([master, pd.DataFrame([new_row])], ignore_index=True)
            master = master.sort_values("Fecha").reset_index(drop=True)

            # Upsert Eval
            if not evalp.empty:
                evalp = evalp[evalp["Fecha"] != eval_row["Fecha"]].copy()
            
            new_eval = {c: np.nan for c in COLS_EVAL}
            for k, v in eval_row.items():
                if k in new_eval:
                    new_eval[k] = v
            evalp = pd.concat([evalp, pd.DataFrame([new_eval])], ignore_index=True)
            evalp = evalp.sort_values("Fecha").reset_index(drop=True)

            summaries.append(summary)

        except Exception as e:
            print(f"ERROR procesando {rr_path.name}: {e}")

    # Crear backups antes de sobrescribir
    ts = time.strftime("%Y%m%d_%H%M%S")
    
    if not master.empty:
        # Crear backups de archivos existentes
        if BASE_MASTER.exists():
            backup_master = Path(f"ENDURANCE_HRV_master_ALL_backup_{ts}.csv")
            shutil.copy2(BASE_MASTER, backup_master)
            print(f"\n📦 Backup creado: {backup_master}")
        
        if BASE_EVAL.exists():
            backup_eval = Path(f"ENDURANCE_HRV_eval_P1P2_ALL_backup_{ts}.csv")
            shutil.copy2(BASE_EVAL, backup_eval)
            print(f"📦 Backup creado: {backup_eval}")
        
        # Sobrescribir archivos originales
        master.to_csv(BASE_MASTER, index=False)
        evalp.to_csv(BASE_EVAL, index=False)
        
        # QA con timestamp (opcional, puedes cambiar a nombre fijo)
        out_qa = Path(f"ENDURANCE_HRV_QA_rolling_30_90_{ts}.md")
        out_qa.write_text(qa_rolling_md(master, asof=master["Fecha"].max()), encoding="utf-8")
        
        print("\n" + "="*70)
        print("💓 DAILY SUMMARIES - Resumen Diario HRV")
        print("="*70)
        for s in summaries:
            # Formatear el diccionario de manera más legible
            fecha = s.get('Fecha', 'N/A')
            hr = s.get('HR', 'N/A')
            rmssd = s.get('RMSSD', 'N/A')
            crmssd = s.get('cRMSSD', 'N/A')
            p2 = s.get('P2', 'N/A')
            trend = s.get('Trend', 'N/A')  # AGREGADO
            tiebreak = s.get('Tiebreak', 'N/A')  # CORREGIDO nombre
            calidad = s.get('Calidad', 'N/A')
            stab = s.get('Stab', 'N/A')
            
            print(f"\n📅 Fecha: {fecha}")
            print(f"   💓 HR promedio:  {hr:.1f} bpm" if isinstance(hr, (int, float)) else f"   💓 HR promedio:  {hr}")
            print(f"   📊 RMSSD:        {rmssd:.1f} ms" if isinstance(rmssd, (int, float)) else f"   📊 RMSSD:        {rmssd}")
            print(f"   🎯 cRMSSD:       {crmssd:.1f} ms" if isinstance(crmssd, (int, float)) else f"   🎯 cRMSSD:       {crmssd}")
            
            # P2 con emoji
            p2_emoji = "🟢" if p2 == "Verde" else "🟡" if p2 == "Amarillo" else "🔴" if p2 == "Rojo" else "⚪"
            print(f"   🚦 Estado P2:    {p2_emoji} {p2}")
            
            # Tendencia con emoji
            trend_emoji = "📈" if trend == "Verde" else "📊" if trend == "Amarillo" else "📉" if trend == "Rojo" else "⚪"
            print(f"   {trend_emoji} Tendencia:    {trend}")
            
            # Tiebreak con emoji
            tiebreak_emoji = "🟢" if tiebreak == "Verde" else "🟡" if tiebreak in ["Amarillo", "Ámbar"] else "🔴" if tiebreak == "Rojo" else "⚪"
            print(f"   {tiebreak_emoji} Tiebreak:     {tiebreak}")
            
            print(f"   ✅ Calidad:      {calidad}")
            print(f"   📈 Estabilidad:  {stab}")
        print("="*70)
        
        print("\n=== OUTPUTS GENERATED ===")
        print(f"✅ {BASE_MASTER} (actualizado)")
        print(f"✅ {BASE_EVAL} (actualizado)")
        print(f"📄 {out_qa}")
    else:
        print("\nNo data processed.")

if __name__ == "__main__":
    main()