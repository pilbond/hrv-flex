#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
add_ans_balance_to_core.py — Calcula SI Baevsky + SD1/SD2 Poincaré desde archivos RR
================================================================================

Reprocesa todos los RR de rr_downloads/, extrae el tramo estable con la misma
lógica que build_hrv_core.py, calcula las 4 métricas ANS balance y las añade como
columnas nuevas al CORE.csv existente.

Uso:
  python add_ans_balance_to_core.py                          # default: ./rr_downloads + CORE.csv
  python add_ans_balance_to_core.py --rr-dir /path/to/rr     # RR en otra carpeta
  python add_ans_balance_to_core.py --dry-run                 # solo muestra, no escribe

Columnas añadidas a CORE:
  SI_baevsky     — Stress Index de Baevsky (activación simpática)
  SD1            — Variabilidad beat-to-beat (ms), ~parasimpático
  SD2            — Variabilidad largo plazo (ms), ~simpático+parasimpático
  SD1_SD2_ratio  — Balance autonómico (bajo = simpático dominante)
"""

import os
import re
import io
import sys
import zipfile
import argparse
import shutil
from pathlib import Path
from datetime import datetime

import numpy as np
import pandas as pd


# ============================================================================
# CONSTANTES (idénticas a build_hrv_core.py)
# ============================================================================

CONSTANTS = {
    "TAIL_TRIM_S": 15.0,
    "LAT_WIN_S": 60.0,
    "LAT_STEP_S": 30.0,
    "LAT_REL_EPS": 0.08,
    "RR_MIN_MS": 300.0,
    "RR_MAX_MS": 2000.0,
    "DELTA_RR_MAX": 0.20,
}


# ============================================================================
# TIER 2 FUNCTIONS
# ============================================================================

def baevsky_stress_index(rr_ms: np.ndarray, bin_width: int = 50) -> float:
    """
    SI de Baevsky: AMo / (2 × Mo × MxDMn).
    Input: RR del tramo estable en milisegundos.
    """
    rr = np.asarray(rr_ms, dtype=float)
    if len(rr) < 20:
        return np.nan
    bins = np.arange(rr.min(), rr.max() + bin_width, bin_width)
    if len(bins) < 2:
        return np.nan
    counts, edges = np.histogram(rr, bins=bins)
    AMo = counts.max() / len(rr) * 100                       # % en bin modal
    modal_idx = counts.argmax()
    Mo_s = (edges[modal_idx] + edges[modal_idx + 1]) / 2 / 1000.0  # centro en s
    MxDMn = (rr.max() - rr.min()) / 1000.0                   # rango en s
    if Mo_s == 0 or MxDMn == 0:
        return np.nan
    return round(AMo / (2 * Mo_s * MxDMn), 1)


def poincare_sd(rr_ms: np.ndarray):
    """
    SD1, SD2, ratio SD1/SD2 del Poincaré plot.
    Input: RR del tramo estable en milisegundos.
    Returns: (SD1, SD2, ratio) — todo en ms excepto ratio (adimensional).
    """
    rr = np.asarray(rr_ms, dtype=float)
    if len(rr) < 10:
        return np.nan, np.nan, np.nan
    diff = rr[1:] - rr[:-1]
    sd1 = float(np.std(diff, ddof=0) / np.sqrt(2))
    sd2_sq = 2 * float(np.var(rr, ddof=0)) - sd1 ** 2
    sd2 = float(np.sqrt(sd2_sq)) if sd2_sq > 0 else 0.0
    ratio = round(sd1 / sd2, 3) if sd2 > 0 else np.nan
    return round(sd1, 2), round(sd2, 2), ratio


# ============================================================================
# EXTRACCIÓN DEL TRAMO ESTABLE (replica build_hrv_core.py líneas 198-288)
# ============================================================================

def extract_stable_segment_ms(rr_source) -> np.ndarray:
    """
    Dado un archivo RR (Path o file-like), devuelve el array de RR del tramo estable en ms.
    Misma lógica que build_hrv_core.py: filtros → tail-trim → latencia → tramo.
    Devuelve array vacío si el archivo es inválido.
    """
    C = CONSTANTS

    try:
        rr = pd.read_csv(rr_source)
    except Exception:
        return np.array([])

    if not {"duration", "offline"}.issubset(rr.columns):
        return np.array([])

    rr_ms = pd.to_numeric(rr["duration"], errors="coerce").astype(float).to_numpy()
    offline = pd.to_numeric(rr["offline"], errors="coerce").fillna(0).astype(int).to_numpy()
    offline = (offline != 0).astype(int)

    # Alinear: eliminar posiciones donde duration es NaN en ambos arrays
    valid_mask = ~np.isnan(rr_ms)
    rr_ms = rr_ms[valid_mask]
    offline = offline[valid_mask]

    if rr_ms.size == 0:
        return np.array([])

    # Eje temporal (basado en array alineado, preserva tiempos reales)
    t_end_raw = np.cumsum(rr_ms) / 1000.0
    dur_raw = float(t_end_raw[-1])

    # Filtro 1: offline + fuera de rango
    oor = (offline == 0) & ((rr_ms < C["RR_MIN_MS"]) | (rr_ms > C["RR_MAX_MS"]))
    base = (offline == 0) & (~oor)
    rr_base = rr_ms[base]
    t_base = t_end_raw[base]

    if rr_base.size < 2:
        return np.array([])

    # Filtro 2: delta > 20%
    keep = np.ones(len(rr_base), dtype=bool)
    d = np.abs(rr_base[1:] - rr_base[:-1]) / rr_base[:-1]
    keep[1:] = d <= C["DELTA_RR_MAX"]
    rr_clean = rr_base[keep]
    t_clean = t_base[keep]

    if rr_clean.size < 2:
        return np.array([])

    # Tail-trim
    t_end_eff = dur_raw - C["TAIL_TRIM_S"]
    eff = t_clean <= t_end_eff
    rr_eff = rr_clean[eff]
    t_eff = t_clean[eff]

    if rr_eff.size < 2:
        return np.array([])

    # Latencia (ventanas 60s, paso 30s)
    max_t = float(t_end_eff)
    nwin = int(np.floor(max_t / C["LAT_STEP_S"])) + 1 if max_t > 0 else 1
    rmssd_w = np.full(nwin, np.nan, dtype=float)

    for k in range(nwin):
        a = C["LAT_STEP_S"] * k
        b = a + C["LAT_WIN_S"]
        m = (t_eff >= a) & (t_eff < b)
        rr_w = rr_eff[m] / 1000.0
        if rr_w.size - 1 >= 20:
            diff_w = np.diff(rr_w)
            rmssd_w[k] = float(np.sqrt(np.mean(diff_w * diff_w)) * 1000.0)

    lat = np.nan

    # Criterio primario (estabilización consecutiva <8%)
    for k in range(1, nwin - 1):
        a, b, c = rmssd_w[k - 1], rmssd_w[k], rmssd_w[k + 1]
        if np.isnan(a) or np.isnan(b) or np.isnan(c) or a <= 0 or b <= 0:
            continue
        if abs(b - a) / a < C["LAT_REL_EPS"] and abs(c - b) / b < C["LAT_REL_EPS"]:
            lat = float(C["LAT_STEP_S"] * k)
            break

    # Fallback (target mediano)
    if np.isnan(lat):
        valid = rmssd_w[~np.isnan(rmssd_w)]
        if valid.size >= 4:
            target = float(np.median(valid[-4:]))
            for k in range(0, nwin - 2):
                a, b, c = rmssd_w[k], rmssd_w[k + 1], rmssd_w[k + 2]
                if np.isnan(a) or np.isnan(b) or np.isnan(c) or target <= 0:
                    continue
                if (abs(a - target) / target < C["LAT_REL_EPS"]
                        and abs(b - target) / target < C["LAT_REL_EPS"]
                        and abs(c - target) / target < C["LAT_REL_EPS"]):
                    lat = float(C["LAT_STEP_S"] * k)
                    break

    t_start_eff = 45.0 if np.isnan(lat) else max(lat, 45.0)

    # Tramo estable
    tramo = t_eff >= t_start_eff
    rr_tramo_ms = rr_eff[tramo]  # ← en milisegundos, como lo usa build_hrv_core.py

    return rr_tramo_ms


# ============================================================================
# PROCESAMIENTO DE UN ARCHIVO RR
# ============================================================================

def parse_date(filename: str) -> str:
    """Extrae YYYY-MM-DD del nombre del archivo."""
    m = re.search(r"(\d{4}-\d{2}-\d{2})", filename)
    if not m:
        raise ValueError(f"No se puede extraer fecha de: {filename}")
    return m.group(1)


def compute_ans_balance(name: str, rr_source) -> dict:
    """Procesa un RR (Path o file-like) y devuelve dict con Fecha + 4 métricas ANS balance."""
    fecha = parse_date(name)
    rr_tramo_ms = extract_stable_segment_ms(rr_source)

    if rr_tramo_ms.size < 20:
        return {
            "Fecha": fecha,
            "SI_baevsky": np.nan,
            "SD1": np.nan,
            "SD2": np.nan,
            "SD1_SD2_ratio": np.nan,
        }

    si = baevsky_stress_index(rr_tramo_ms)
    sd1, sd2, ratio = poincare_sd(rr_tramo_ms)

    return {
        "Fecha": fecha,
        "SI_baevsky": si,
        "SD1": sd1,
        "SD2": sd2,
        "SD1_SD2_ratio": ratio,
    }


def discover_rr_files(rr_dir: Path):
    """
    Genera tuplas (nombre, source) desde:
      - CSVs sueltos: *_RR.CSV / *_RR.csv
      - CSVs dentro de ZIPs: *.zip que contengan *_RR.CSV
    source es Path para sueltos, io.BytesIO para los de dentro de zip.
    """
    # CSVs sueltos
    loose = sorted(rr_dir.glob("*_RR.[Cc][Ss][Vv]"))
    for f in loose:
        yield f.name, f

    # Dentro de ZIPs
    zips = sorted(rr_dir.glob("*.zip"))
    for zpath in zips:
        try:
            with zipfile.ZipFile(zpath, "r") as zf:
                csv_names = [n for n in zf.namelist()
                             if n.upper().endswith("_RR.CSV")
                             and not n.startswith("__MACOSX")]
                for csv_name in sorted(csv_names):
                    data = zf.read(csv_name)
                    yield Path(csv_name).name, io.BytesIO(data)
        except (zipfile.BadZipFile, Exception) as e:
            print(f"  WARNING: No se pudo abrir {zpath.name}: {e}")


# ============================================================================
# MAIN
# ============================================================================

def main():
    parser = argparse.ArgumentParser(description="Añade métricas de balance autonómico (SI, SD1/SD2) a CORE.csv")
    parser.add_argument("--rr-dir", type=str, default=None,
                        help="Directorio de archivos RR (default: ./rr_downloads)")
    parser.add_argument("--core-csv", type=str, default=None,
                        help="Ruta al CORE.csv (default: ./ENDURANCE_HRV_master_CORE.csv)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Solo muestra resultados, no modifica CORE.csv")
    args = parser.parse_args()

    # Resolver rutas
    data_dir = Path(os.environ.get("HRV_DATA_DIR", ".").strip() or ".")
    rr_dir = Path(args.rr_dir) if args.rr_dir else data_dir / "rr_downloads"
    core_path = Path(args.core_csv) if args.core_csv else data_dir / "ENDURANCE_HRV_master_CORE.csv"

    if not rr_dir.exists():
        print(f"ERROR: Directorio RR no encontrado: {rr_dir}")
        sys.exit(1)
    if not core_path.exists():
        print(f"ERROR: CORE.csv no encontrado: {core_path}")
        sys.exit(1)

    # Buscar archivos RR (sueltos + dentro de ZIPs)
    rr_entries = list(discover_rr_files(rr_dir))

    # Deduplicar por fecha (si un RR está suelto Y en un zip, queda el suelto)
    seen = set()
    unique_entries = []
    for name, source in rr_entries:
        try:
            fecha = parse_date(name)
        except ValueError:
            continue
        if fecha not in seen:
            seen.add(fecha)
            unique_entries.append((name, source))
    rr_entries = unique_entries

    if not rr_entries:
        print(f"No se encontraron archivos *_RR.CSV (sueltos ni en ZIPs) en {rr_dir}")
        sys.exit(1)

    n_zips = len(list(rr_dir.glob("*.zip")))
    n_loose = len(list(rr_dir.glob("*_RR.[Cc][Ss][Vv]")))
    print(f"Encontrados {len(rr_entries)} archivos RR en {rr_dir} ({n_loose} sueltos, {n_zips} ZIPs)")

    # Procesar todos los RR
    results = []
    errors = []
    for i, (name, source) in enumerate(rr_entries):
        try:
            row = compute_ans_balance(name, source)
            results.append(row)
            si = row["SI_baevsky"]
            ratio = row["SD1_SD2_ratio"]
            status = "OK" if not np.isnan(si) else "SKIP"
            if (i + 1) % 50 == 0 or i == 0 or i == len(rr_entries) - 1:
                print(f"  [{i+1:3d}/{len(rr_entries)}] {row['Fecha']}  SI={si}  ratio={ratio}  [{status}]")
        except Exception as e:
            errors.append((name, str(e)))
            print(f"  [{i+1:3d}/{len(rr_entries)}] {name}  ERROR: {e}")

    if not results:
        print("No se pudo procesar ningún archivo.")
        sys.exit(1)

    ans_balance_df = pd.DataFrame(results)
    ans_balance_df = ans_balance_df.drop_duplicates(subset="Fecha", keep="last")
    print(f"\nProcesados: {len(ans_balance_df)} fechas únicas ({len(errors)} errores)")

    # Leer CORE.csv
    core = pd.read_csv(core_path)
    print(f"CORE.csv: {len(core)} filas, {len(core.columns)} columnas")

    # Si ya existen las columnas ANS balance, eliminarlas antes de mergear
    ans_balance_cols = ["SI_baevsky", "SD1", "SD2", "SD1_SD2_ratio"]
    existing = [c for c in ans_balance_cols if c in core.columns]
    if existing:
        print(f"  Columnas ANS balance existentes serán reemplazadas: {existing}")
        core = core.drop(columns=existing)

    # Merge
    merged = core.merge(ans_balance_df, on="Fecha", how="left")

    # Reordenar para que ANS balance quede antes de Notes
    preferred_order = [
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
        "SI_baevsky",
        "SD1",
        "SD2",
        "SD1_SD2_ratio",
        "Notes",
    ]
    merged = merged[[c for c in preferred_order if c in merged.columns] + [c for c in merged.columns if c not in preferred_order]]

    # Estadísticas
    n_matched = merged["SI_baevsky"].notna().sum()
    n_core = len(merged)
    n_missing = n_core - n_matched
    print(f"\nResultado merge:")
    print(f"  Filas CORE:      {n_core}")
    print(f"  Con ANS balance:      {n_matched} ({100*n_matched/n_core:.0f}%)")
    print(f"  Sin match (NaN): {n_missing}")

    # Resumen estadístico
    print(f"\nEstadísticas ANS balance:")
    for col in ans_balance_cols:
        s = merged[col].dropna()
        if len(s) > 0:
            print(f"  {col:15s}  median={s.median():.1f}  P10={s.quantile(0.1):.1f}  P90={s.quantile(0.9):.1f}  n={len(s)}")

    if args.dry_run:
        print("\n[DRY-RUN] No se ha modificado CORE.csv")
        # Mostrar últimos 5 días
        print("\nÚltimos 5 días:")
        tail = merged[["Fecha", "HR_stable", "RMSSD_stable"] + ans_balance_cols].tail(5)
        print(tail.to_string(index=False))
        return

    # Backup
    backup_path = core_path.with_suffix(f".bak_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv")
    shutil.copy2(core_path, backup_path)
    print(f"\nBackup: {backup_path}")

    # Escribir
    merged.to_csv(core_path, index=False)
    print(f"CORE.csv actualizado: {len(merged)} filas × {len(merged.columns)} columnas")
    print(f"Columnas nuevas: {ans_balance_cols}")
    print("Done.")


if __name__ == "__main__":
    main()

