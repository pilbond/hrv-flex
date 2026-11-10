"""HG-04: sensibilidad del diagnóstico intrarregistro a bloques de 60/90/120 s.

Solo lectura de RR y copias CORE; escribe agregados, nunca RR ni filas diarias.
El inicio de cálculo permanece en 90 s. Los bloques de diagnóstico son
[90, 90+L) y [t_end_eff-L, t_end_eff], completos y sin solape.
"""
from __future__ import annotations

import json
import math
import hashlib
from pathlib import Path
import os
import sys

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))
SOURCE = ROOT / "out/hg04_copias_paralelas_2026-10-22"
RR_DIR = Path(os.environ.get("HG04_REPLAY_WORK", Path.home() / "hg04_replay_work")) / "rr_src"
OUT = Path(__file__).resolve().parents[1] / "results/stability_window_sensitivity_2026-10-23.json"
LENGTHS = (60, 90, 120)
THRESHOLDS = (0.10, 0.15, 0.20)  # exploratorios, no umbrales aprobados


def pairs_rmssd(rr_ms: np.ndarray, idx: np.ndarray) -> tuple[float, int]:
    diffs = np.diff(rr_ms)[np.diff(idx) == 1]
    return (float(np.sqrt(np.mean(diffs**2))) if diffs.size else math.nan, int(diffs.size))


def parse_truncated(path: Path) -> tuple[np.ndarray, np.ndarray, np.ndarray, float]:
    raw = pd.read_csv(path)
    rr = pd.to_numeric(raw.duration, errors="coerce").to_numpy(float)
    offline = pd.to_numeric(raw.offline, errors="coerce").fillna(0).to_numpy(int)
    idx = np.arange(len(rr))
    valid = ~np.isnan(rr)
    rr, offline, idx = rr[valid], offline[valid], idx[valid]
    keep = np.cumsum(rr) / 1000 <= 375
    rr, offline, idx = rr[keep], offline[keep], idx[keep]
    if not rr.size:
        return rr, rr, idx, math.nan
    times = np.cumsum(rr) / 1000
    end = float(times[-1] - 15)
    base = (offline == 0) & (rr >= 300) & (rr <= 2000)
    rr, times, idx = rr[base], times[base], idx[base]
    keep = np.ones(len(rr), dtype=bool)
    if len(rr) > 1:
        keep[1:] = abs(np.diff(rr)) / rr[:-1] <= 0.20
    keep &= times <= end
    return rr[keep], times[keep], idx[keep], end


def segment(rr: np.ndarray, times: np.ndarray, idx: np.ndarray, a: float, b: float, closed_right: bool) -> tuple[float, int]:
    mask = (times >= a) & ((times <= b) if closed_right else (times < b))
    return pairs_rmssd(rr[mask], idx[mask])


def summarize(frame: pd.DataFrame) -> dict:
    out = {"n": int(len(frame))}
    for length in LENGTHS:
        z = frame.loc[frame[f"valid_{length}"], f"delta_ln_{length}"].dropna()
        p = frame.loc[frame[f"valid_{length}"], f"min_pairs_{length}"].dropna()
        out[str(length)] = {
            "valid": int(len(z)),
            "missing": int(len(frame) - len(z)),
            "median_delta_ln_late_minus_early": float(z.median()) if len(z) else None,
            "median_abs_delta_ln": float(z.abs().median()) if len(z) else None,
            "p90_abs_delta_ln": float(z.abs().quantile(.9)) if len(z) else None,
            "median_min_pairs": float(p.median()) if len(p) else None,
            "late_lower": int((z < 0).sum()),
            "late_higher": int((z > 0).sum()),
            "abs_change_over": {str(round(100*t)): int((z.abs() > math.log1p(t)).sum()) for t in THRESHOLDS},
        }
    return out


def main() -> None:
    from build_hrv_core import CONSTANTS as c

    assert (c["RR_MIN_MS"], c["RR_MAX_MS"], c["DELTA_RR_MAX"], c["TAIL_TRIM_S"]) == (300, 2000, 0.20, 15)
    core = {
        arm: pd.read_csv(SOURCE / arm / "ENDURANCE_HRV_master_CORE.csv").set_index("Fecha")
        for arm in ("H3S90", "H3S90T375", "H3S90T375NL")
    }
    assert core["H3S90"].index.equals(core["H3S90T375"].index)
    assert core["H3S90"].index.equals(core["H3S90T375NL"].index)
    source_index = json.loads((RR_DIR / "_index.json").read_text(encoding="utf-8"))
    rows = []
    for day in core["H3S90T375"].index:
        if day not in source_index:
            continue
        rr, times, idx, end = parse_truncated(RR_DIR / source_index[day]["file"])
        if not np.isfinite(end):
            continue
        whole, _ = segment(rr, times, idx, 90, end, True)
        expected = core["H3S90T375"].at[day, "RMSSD_stable"]
        if np.isfinite(expected) and not np.isclose(whole, expected, rtol=1e-10, atol=1e-10):
            raise AssertionError(f"RMSSD replay differs on {day}: {whole} != {expected}")
        cut = core["H3S90T375"].loc[day]
        nl = core["H3S90T375NL"].loc[day]
        only_lat = cut.Calidad == "FLAG_mecánico" and nl.Calidad == "OK"
        row = {"day": day, "end": end,
               "quality_full": core["H3S90"].at[day, "Calidad"],
               "quality_cut": cut.Calidad, "quality_no_lat": nl.Calidad,
               "lat_only": only_lat,
               "new_lat_only": only_lat and core["H3S90"].at[day, "Calidad"] == "OK"}
        for length in LENGTHS:
            if end - 90 < 2 * length:
                row.update({f"valid_{length}": False, f"delta_ln_{length}": math.nan,
                            f"min_pairs_{length}": math.nan})
                continue
            early, ne = segment(rr, times, idx, 90, 90 + length, False)
            late, nl_pairs = segment(rr, times, idx, end - length, end, True)
            valid = ne >= 20 and nl_pairs >= 20 and early > 0 and late > 0
            row.update({f"valid_{length}": bool(valid),
                        f"delta_ln_{length}": math.log(late / early) if valid else math.nan,
                        f"min_pairs_{length}": min(ne, nl_pairs)})
        rows.append(row)
    df = pd.DataFrame(rows).set_index("day")
    groups = {
        "all_rr": df,
        "common_ok": df[df.quality_full.eq("OK") & df.quality_cut.eq("OK")],
        "new_lat_only": df[df.new_lat_only],
        "existing_lat_only": df[df.lat_only & ~df.new_lat_only],
        "cut_no_lat_ok": df[df.quality_no_lat.eq("OK")],
    }
    results = {
        "date": "2026-10-23",
        "source": "HG-03 + inicio 90 s + corte 375 s; RR originales; pares originalmente consecutivos",
        "window_definition": "primeros L segundos desde 90 s versus últimos L segundos antes de t_end_eff, sin solape; mínimo 20 pares por bloque",
        "threshold_definition": "|ln(RMSSD_late/RMSSD_early)| > ln(1+p), p=10/15/20%; sensibilidad descriptiva, no QA aprobada",
        "n_export_dates": int(len(core["H3S90T375"])),
        "n_rr_reconstructed": int(len(df)),
        "input_sha256": {
            f"{arm}_CORE": hashlib.sha256((SOURCE / arm / "ENDURANCE_HRV_master_CORE.csv").read_bytes()).hexdigest()
            for arm in core
        },
        "groups": {name: summarize(group) for name, group in groups.items()},
    }
    finals = {
        arm: pd.read_csv(SOURCE / arm / "ENDURANCE_HRV_master_FINAL.csv").set_index("Fecha")
        for arm in core
    }
    assert all(finals[arm].index.equals(core[arm].index) for arm in core)
    cut, no_lat, full = ("H3S90T375", "H3S90T375NL", "H3S90")
    assert np.allclose(core[cut].RMSSD_stable, core[no_lat].RMSSD_stable, equal_nan=True)
    results["existing_no_lat_replay"] = {
        "quality_changes_vs_cut": int(core[cut].Calidad.ne(core[no_lat].Calidad).sum()),
        "gate_changes_vs_cut": int(finals[cut].gate_final.ne(finals[no_lat].gate_final).sum()),
        "gate_changes_vs_full": int(finals[full].gate_final.ne(finals[no_lat].gate_final).sum()),
        "red_days": {arm: int(finals[arm].gate_final.eq("ROJO").sum()) for arm in (full, cut, no_lat)},
    }
    # Compare classifications on the identical subset valid under all three lengths.
    common = df[np.logical_and.reduce([df[f"valid_{length}"].to_numpy() for length in LENGTHS])]
    for pct in THRESHOLDS:
        threshold = math.log1p(pct)
        labels = pd.DataFrame({str(length): common[f"delta_ln_{length}"].abs() > threshold for length in LENGTHS})
        key = str(round(pct * 100))
        results.setdefault("same_days_classification", {})[key] = {
            "n": int(len(labels)), "positive": {col: int(labels[col].sum()) for col in labels},
            "disagree_60_90": int((labels["60"] != labels["90"]).sum()),
            "disagree_90_120": int((labels["90"] != labels["120"]).sum()),
            "disagree_any": int((labels.nunique(axis=1) > 1).sum()),
        }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(results, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
    print(json.dumps(results, ensure_ascii=False, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
