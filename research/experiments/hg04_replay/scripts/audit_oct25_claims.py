"""Reproduce agregados citados en la rectificación bibliográfica HG-04.

No reconstruye RR ni clasifica tipos de latido. Escribe solo agregados y
huellas de los dos CORE de entrada, sin filas personales por fecha.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def core_association(path: Path) -> dict:
    df = pd.read_csv(path)
    df = df.loc[
        df["Calidad"].eq("OK")
        & df["RRbar_s"].notna()
        & df["RMSSD_stable"].gt(0)
    ].copy()
    rr = df["RRbar_s"].to_numpy(dtype=float)
    rmssd = df["RMSSD_stable"].to_numpy(dtype=float)
    lnr = np.log(rmssd)
    hr = 60.0 / rr
    fit_linear = np.polyfit(rr, lnr, 1)
    fit_quadratic = np.polyfit(rr, lnr, 2)
    total_ss = np.sum((lnr - lnr.mean()) ** 2)
    linear_ss = np.sum((lnr - np.polyval(fit_linear, rr)) ** 2)
    quadratic_ss = np.sum((lnr - np.polyval(fit_quadratic, rr)) ** 2)
    f_value = ((linear_ss - quadratic_ss) / 1) / (quadratic_ss / (len(rr) - 3))
    sextile = pd.qcut(df["RRbar_s"], 6, labels=False)
    medians = [
        {"n": int((sextile == i).sum()),
         "hr_bpm": float(np.median(hr[sextile == i])),
         "rmssd_ms": float(np.median(rmssd[sextile == i]))}
        for i in range(6)
    ]
    return {
        "input_sha256": sha256(path),
        "n_ok": len(rr),
        "first_date": str(df["Fecha"].min()),
        "last_date": str(df["Fecha"].max()),
        "selection": "Calidad == OK; RRbar_s presente; RMSSD_stable > 0",
        "hr_median_bpm": float(np.median(hr)),
        "rr_median_ms": float(np.median(rr) * 1000),
        "hr_below_55_n": int((hr < 55).sum()),
        "hr_below_55_pct": float(100 * np.mean(hr < 55)),
        "r2_linear": float(1 - linear_ss / total_ss),
        "r2_quadratic": float(1 - quadratic_ss / total_ss),
        "f_quadratic_vs_linear": float(f_value),
        "quadratic_coefficient_rr_seconds": float(fit_quadratic[0]),
        "rr_sextiles": medians,
    }


def removed_intervals(path: Path) -> dict:
    df = pd.read_csv(path)
    df = df.loc[df["Calidad"].ne("INVALID")].copy()
    counts = df["Notes"].str.extract(
        r"n_total=(\d+); n_base=(\d+); n_clean=(\d+); .*off=(\d+); oor=(\d+); dRR=(\d+)"
    )
    if counts.isna().any().any():
        raise ValueError("Faltan contadores en Notes de alguna fila seleccionada")
    counts = counts.astype(int)
    off, oor, drr = (int(counts[i].sum()) for i in (3, 4, 5))
    return {
        "input_sha256": sha256(path),
        "n_non_invalid": len(df),
        "first_date": str(df["Fecha"].min()),
        "last_date": str(df["Fecha"].max()),
        "selection": "Calidad != INVALID",
        "removed_total": off + oor + drr,
        "removed_offline": off,
        "removed_out_of_range": oor,
        "removed_delta_rr": drr,
        "artifact_pct_median": float(df["Artifact_pct"].median()),
        "artifact_pct_p95": float(df["Artifact_pct"].quantile(0.95)),
        "artifact_pct_max": float(df["Artifact_pct"].max()),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--production-core", type=Path, default=Path("data/ENDURANCE_HRV_master_CORE.csv"))
    parser.add_argument(
        "--replay-core", type=Path,
        default=Path("out/hg04_copias_paralelas_2026-10-22/H3S90T375/ENDURANCE_HRV_master_CORE.csv"),
    )
    parser.add_argument(
        "--output", type=Path,
        default=Path("research/experiments/hg04_replay/results/audit_oct25_claims.json"),
    )
    args = parser.parse_args()
    result = {
        "scope": "agregados sobre CORE existentes; no clasifica picos ni compara RR simultaneos",
        "production": core_association(args.production_core),
        "replay_truncated": removed_intervals(args.replay_core),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
