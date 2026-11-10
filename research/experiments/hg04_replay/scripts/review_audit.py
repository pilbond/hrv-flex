"""Checks for HG-04 replay; saved change lists are not complete replay outputs."""
import json
from pathlib import Path

import numpy as np
import pandas as pd

PAIRS = [("H4", "H4w"), ("H4w", "H4v"), ("H4e", "H4e210"), ("H4e210", "H4e240")]
OUTPUTS = ("CORE", "BETA_AUDIT", "FINAL", "DASHBOARD")


def read_dated(path):
    frame = pd.read_csv(path).set_index("Fecha")
    if frame.index.has_duplicates or frame.index.isna().any():
        raise ValueError(f"Missing or duplicate Fecha: {path}")
    pd.to_datetime(frame.index, errors="raise")
    return frame.sort_index()


def compare_changes(a, b, name_a, name_b):
    """Reconstruct gates on the union; outside it both equal the control."""
    for frame, name in ((a, name_a), (b, name_b)):
        if frame.index.has_duplicates or frame.index.isna().any():
            raise ValueError("Missing or duplicate dates")
        if frame[["gate_C", f"gate_{name}"]].isna().any().any():
            raise ValueError("Missing gate")
        if (frame.gate_C == frame[f"gate_{name}"]).any():
            raise ValueError("Change list contains unchanged dates")
    shared = a.index.intersection(b.index)
    if not a.loc[shared, "gate_C"].equals(b.loc[shared, "gate_C"]):
        raise ValueError("Inconsistent control between arms")
    control = a.gate_C.combine_first(b.gate_C)
    ga = a[f"gate_{name_a}"].reindex(control.index).fillna(control)
    gb = b[f"gate_{name_b}"].reindex(control.index).fillna(control)
    changed = ga != gb
    return {"changed_days": int(changed.sum()),
            "dates": control.index[changed].tolist(),
            "union_days": len(control), "both_changed_vs_control": len(shared),
            "only_a_changed_vs_control": len(a.index.difference(b.index)),
            "only_b_changed_vs_control": len(b.index.difference(a.index))}


def compare_frames(control, production):
    """All fields, no exclusions; numeric tolerance is explicit, not bit parity."""
    for frame in (control, production):
        if frame.index.has_duplicates or frame.index.isna().any():
            raise ValueError("Missing or duplicate dates")
    dates = control.index.intersection(production.index)
    differences = {}
    for column in control.columns.intersection(production.columns):
        x, y = control.loc[dates, column], production.loc[dates, column]
        equal = (x.eq(y) | (x.isna() & y.isna())).to_numpy()
        if pd.api.types.is_numeric_dtype(x) and pd.api.types.is_numeric_dtype(y):
            equal = np.isclose(x.astype(float), y.astype(float), rtol=1e-9, atol=1e-12, equal_nan=True)
        if not equal.all():
            differences[column] = dates[~equal].tolist()
    result = {"only_control_dates": control.index.difference(production.index).tolist(),
              "only_production_dates": production.index.difference(control.index).tolist(),
              "only_control_columns": control.columns.difference(production.columns).tolist(),
              "only_production_columns": production.columns.difference(control.columns).tolist(),
              "column_order_equal": list(control.columns) == list(production.columns),
              "differing_dates_by_column": differences,
              "numeric_tolerance": {"rtol": 1e-9, "atol": 1e-12}}
    result["parity"] = (not differences and result["column_order_equal"] and
                        not any(result[k] for k in ("only_control_dates", "only_production_dates",
                                                   "only_control_columns", "only_production_columns")))
    return result


def control_parity(work, production):
    result = {}
    for output in OUTPUTS:
        filename = f"ENDURANCE_HRV_master_{output}.csv"
        result[output] = compare_frames(read_dated(Path(work) / "C/data" / filename),
                                        read_dated(Path(production) / filename))
    return result


def saved_audit(results):
    results = Path(results)
    comparisons = {}
    for a, b in PAIRS:
        comparisons[f"{a}_vs_{b}"] = compare_changes(
            read_dated(results / f"gate_changes_{a}.csv"),
            read_dated(results / f"gate_changes_{b}.csv"), a, b)
    report = {"scope": "Saved exhaustive gate-change lists; full control parity not assessed.",
              "assumption": "Each list enumerates every gate change against the same control.",
              "direct_comparisons": comparisons}
    (results / "review_audit.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    return report
