"""Aggregate the preregistered early-start HG-04 replay without saving raw RR.

Requires the isolated arms C, H3, E0/60/90/120/180,
H3E0/60/90/120/180, H4w, H3H4w, H4, H34, and the corresponding
QA-frozen arms from freeze_qa.py. Writes aggregate results in results/ only.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd

from review_audit import read_dated

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))
from build_hrv_core import CONSTANTS, _parse_and_filter_rr  # noqa: E402

EARLY = [f"E{s}" for s in (0, 60, 90, 120)]
COMBINED = [f"H3E{s}" for s in (0, 60, 90, 120)]
SENSITIVITY = ["E180", "H3E180"]
ARMS = ["C", "H3", *EARLY, *COMBINED, *SENSITIVITY, "H4w", "H3H4w", "H4", "H34"]


def arm_frames(work: Path, arm: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    base = work / arm / "data"
    return (
        read_dated(base / "ENDURANCE_HRV_master_CORE.csv"),
        read_dated(base / "ENDURANCE_HRV_master_FINAL.csv"),
    )


def paired_log_stats(x: pd.Series, y: pd.Series, mask: pd.Series) -> dict:
    valid = mask & x.notna() & y.notna() & np.isfinite(x) & np.isfinite(y)
    a, b = x[valid].astype(float).to_numpy(), y[valid].astype(float).to_numpy()
    if len(a) < 3:
        return {"n": len(a), "bias": None, "loa": None, "cohen_d": None, "r": None}
    diff = b - a
    sd = float(np.std(diff, ddof=1))
    pooled = float(np.sqrt((np.var(a, ddof=1) + np.var(b, ddof=1)) / 2))
    return {
        "n": len(a),
        "bias": float(np.mean(diff)),
        "loa": [float(np.mean(diff) - 1.96 * sd), float(np.mean(diff) + 1.96 * sd)],
        "cohen_d": float(np.mean(diff) / pooled) if pooled else None,
        "r": float(np.corrcoef(a, b)[0, 1]) if np.std(a) and np.std(b) else None,
        "p95_abs": float(np.quantile(np.abs(diff), 0.95)),
        "max_abs": float(np.max(np.abs(diff))),
        "higher": int(np.sum(diff > 0)),
        "lower": int(np.sum(diff < 0)),
    }


def transition_counts(before: pd.Series, after: pd.Series) -> dict[str, int]:
    return dict(sorted(Counter(f"{a}->{b}" for a, b in zip(before, after) if a != b).items()))


def changed_numeric(a: pd.Series, b: pd.Series) -> int:
    x, y = pd.to_numeric(a, errors="coerce"), pd.to_numeric(b, errors="coerce")
    return int((~np.isclose(x.to_numpy(), y.to_numpy(), rtol=1e-9, atol=1e-12, equal_nan=True)).sum())


def window_qc(work: Path, inventory: dict) -> dict:
    windows = {str(s): (s, None) for s in (0, 60, 90, 120, 180)}
    windows["180_to_360"] = (180, 360.0)
    rows = {label: [] for label in windows}
    for day, item in inventory.items():
        path = work / "rr_src" / item["file"]
        raw = pd.read_csv(path)
        duration = pd.to_numeric(raw["duration"], errors="coerce").to_numpy(dtype=float)
        if not np.isfinite(duration).all():
            raise ValueError(f"Unreliable time axis in {day}")
        raw_end = np.cumsum(duration) / 1000.0
        ctx = _parse_and_filter_rr(path, CONSTANTS)
        if not ctx.time_axis_reliable:
            raise ValueError(f"Unreliable parsed time axis in {day}")
        for label, (start, fixed_end) in windows.items():
            end = fixed_end if fixed_end is not None else ctx.t_end_eff
            raw_mask = (raw_end >= start) & (raw_end <= end)
            eff_mask = (ctx.t_eff >= start) & (ctx.t_eff <= end)
            idx = ctx.original_idx_eff[eff_mask]
            n_raw, n_eff = int(raw_mask.sum()), int(eff_mask.sum())
            rows[label].append({
                "day": day,
                "seconds": max(0.0, min(end, ctx.t_end_eff) - start),
                "n_raw": n_raw,
                "n_eff": n_eff,
                "valid_frac": n_eff / n_raw if n_raw else 0.0,
                "n_pairs": int(np.sum(np.diff(idx) == 1)),
            })
    result = {}
    for label, values in rows.items():
        f = pd.DataFrame(values)
        result[label] = {
            "n": len(f),
            "median_seconds": float(f.seconds.median()),
            "p05_seconds": float(f.seconds.quantile(0.05)),
            "median_valid_rr": float(f.n_eff.median()),
            "p05_valid_pairs": float(f.n_pairs.quantile(0.05)),
            "n_under_20_pairs": int((f.n_pairs < 20).sum()),
            "under_20_pairs_dates": f.loc[f.n_pairs < 20, "day"].tolist(),
            "n_under_180_seconds": int((f.seconds < 180).sum()),
            "under_180_seconds_dates": f.loc[f.seconds < 180, "day"].tolist(),
            "n_valid_frac_below_85pct": int((f.valid_frac < 0.85).sum()),
        }
    return result


def analyze(work: Path) -> dict:
    inventory = json.loads((work / "rr_src" / "_index.json").read_text(encoding="utf-8"))
    source_dates = pd.Index(sorted(inventory))
    frames = {name: arm_frames(work, name) for name in ARMS}
    c, cf = frames["C"]
    for name, (x, xf) in frames.items():
        if not x.index.equals(c.index) or not xf.index.equals(cf.index):
            raise ValueError(f"Date coverage differs: {name}")
        if list(x.columns) != list(c.columns) or list(xf.columns) != list(cf.columns):
            raise ValueError(f"Column schema differs: {name}")
    if len(source_dates) != 501 or len(c) != 504 or not source_dates.isin(c.index).all():
        raise ValueError("Unexpected source/control cohort")
    common = pd.Series(c.index.isin(source_dates), index=c.index)
    for name in ["C", *EARLY, *COMBINED]:
        x = frames[name][0]
        common &= x.Calidad.eq("OK") & np.isfinite(pd.to_numeric(x.lnRMSSD, errors="coerce"))
    def source_label(item: dict) -> str:
        name = item["source"].lower()
        for marker in ("from_jsonl", "from_ecg", "from_elite"):
            if marker in name:
                return marker
        return "other_filename"

    source_kind = {day: source_label(item) for day, item in inventory.items()}
    output = {
        "cohort": {
            "control_days": len(c),
            "source_days": len(source_dates),
            "missing_rr_days": c.index.difference(source_dates).tolist(),
            "common_ok_early_and_combined_days": int(common.sum()),
            "source_kind_counts": dict(Counter(source_kind.values())),
        },
        "window_qc": window_qc(work, inventory),
        "arms": {},
        "direct_effects": {},
        "qa_frozen": {},
    }
    source_mask = pd.Series(c.index.isin(source_dates), index=c.index)
    for name in ARMS[1:]:
        x, xf = frames[name]
        both_ok = source_mask & c.Calidad.eq("OK") & x.Calidad.eq("OK")
        g0, g1 = cf.gate_final.astype(str), xf.gate_final.astype(str)
        changed = source_mask & g0.ne(g1)
        mismatch0 = c.Flags.fillna("").str.contains("STAB_LAST2_MISMATCH")
        mismatch1 = x.Flags.fillna("").str.contains("STAB_LAST2_MISMATCH")
        output["arms"][name] = {
            "log_common_ok": paired_log_stats(c.lnRMSSD, x.lnRMSSD, common),
            "log_both_ok": paired_log_stats(c.lnRMSSD, x.lnRMSSD, both_ok),
            "quality_transitions": transition_counts(c.loc[source_mask, "Calidad"], x.loc[source_mask, "Calidad"]),
            "mismatch_count": int(mismatch1.loc[source_mask].sum()),
            "mismatch_discordant_vs_C": int((mismatch0[source_mask] != mismatch1[source_mask]).sum()),
            "gate_changes": int(changed.sum()),
            "gate_transitions": transition_counts(g0[changed], g1[changed]),
            "gate_changes_by_source": dict(Counter(source_kind[d] for d in c.index[changed])),
            "action_changes": int((cf.Action[source_mask].astype(str) != xf.Action[source_mask].astype(str)).sum()),
            "ln_base60_changed": changed_numeric(cf.loc[source_mask, "ln_base60"], xf.loc[source_mask, "ln_base60"]),
            "healthy_rmssd_changed": changed_numeric(cf.loc[source_mask, "healthy_rmssd"], xf.loc[source_mask, "healthy_rmssd"]),
        }
    for start in (0, 60, 90, 120, 180):
        a, b = f"E{start}", f"H3E{start}"
        xa, fa = frames[a]
        xb, fb = frames[b]
        output["direct_effects"][f"{b}_vs_{a}"] = {
            "gate_different": int((fa.gate_final[source_mask].astype(str) != fb.gate_final[source_mask].astype(str)).sum()),
            "quality_different": int((xa.Calidad[source_mask] != xb.Calidad[source_mask]).sum()),
            "log_common_ok": paired_log_stats(xa.lnRMSSD, xb.lnRMSSD, common),
        }
    for a, b in (("H4w", "H3H4w"), ("H4w", "H4"), ("H3H4w", "H34")):
        xa, fa = frames[a]
        xb, fb = frames[b]
        output["direct_effects"][f"{b}_vs_{a}"] = {
            "gate_different": int((fa.gate_final[source_mask].astype(str) != fb.gate_final[source_mask].astype(str)).sum()),
            "quality_different": int((xa.Calidad[source_mask] != xb.Calidad[source_mask]).sum()),
        }
    for name in [*EARLY, *COMBINED, *SENSITIVITY]:
        frozen_core, frozen_final = arm_frames(work, f"{name}q")
        original_core, original_final = frames[name]
        if not frozen_final.index.equals(cf.index):
            raise ValueError(f"QA-frozen dates differ: {name}")
        if changed_numeric(frozen_core.RMSSD_stable, original_core.RMSSD_stable):
            raise ValueError(f"QA-frozen candidate values changed: {name}")
        frozen_gate = frozen_final.gate_final[source_mask].astype(str)
        control_gate = cf.gate_final[source_mask].astype(str)
        original_gate = original_final.gate_final[source_mask].astype(str)
        output["qa_frozen"][name] = {
            "gate_changes_vs_C": int(frozen_gate.ne(control_gate).sum()),
            "gate_changes_vs_unfrozen": int(frozen_gate.ne(original_gate).sum()),
            "gate_transitions_vs_C": transition_counts(control_gate, frozen_gate),
            "action_changes_vs_C": int((cf.Action[source_mask].astype(str) != frozen_final.Action[source_mask].astype(str)).sum()),
            "ln_base60_changed_vs_C": changed_numeric(cf.loc[source_mask, "ln_base60"], frozen_final.loc[source_mask, "ln_base60"]),
        }
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work", type=Path, default=Path(os.environ.get("HG04_REPLAY_WORK", Path.home() / "hg04_replay_work")))
    args = parser.parse_args()
    output = analyze(args.work.resolve())
    path = ROOT / "research/experiments/hg04_replay/results/early_window_2026-10-21.json"
    path.write_text(json.dumps(output, indent=2, ensure_ascii=False), encoding="utf-8")
    print("cohort", output["cohort"])
    print("window_qc", output["window_qc"])
    for name, value in output["arms"].items():
        print(name, "n_common", value["log_common_ok"]["n"], "bias", value["log_common_ok"]["bias"],
              "gate", value["gate_changes"], "action", value["action_changes"],
              "mismatch", value["mismatch_count"])
    print("direct_effects", {k: v["gate_different"] for k, v in output["direct_effects"].items()})
    print("qa_frozen", {k: v["gate_changes_vs_C"] for k, v in output["qa_frozen"].items()})
    print("report", path)


if __name__ == "__main__":
    main()
