"""Read-only audit of the nine 90s/120s red-green disagreements (2026-10-22).

Inputs are isolated replay CORE/FINAL files, not production. Outputs contain
only nine diagnostic rows and aggregates. Counterfactual gates freeze each
arm's own baseline; they do not simulate a different historical pipeline.
"""
from pathlib import Path
import json

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[4]
SOURCE = ROOT / "out/hg04_copias_paralelas_2026-10-22"
OUTPUT = Path(__file__).resolve().parents[1] / "results/nine_disagreements_2026-10-22.json"
ARMS = ("H3S90", "H3S120")


def gate(ln, hr, row):
    low = ln < row.ln_base60 - row.SWC_ln
    high = hr > row.HR_base60 + row.SWC_HR
    return "ROJO" if low and high else "ÁMBAR" if low or high else "VERDE"


def main():
    cores = {a: pd.read_csv(SOURCE / a / "ENDURANCE_HRV_master_CORE.csv").set_index("Fecha") for a in ARMS}
    finals = {a: pd.read_csv(SOURCE / a / "ENDURANCE_HRV_master_FINAL.csv").set_index("Fecha") for a in ARMS}
    a, b = (finals[n] for n in ARMS)
    assert a.index.equals(b.index) and a.index.is_unique
    mask = (a.gate_final.eq("ROJO") & b.gate_final.eq("VERDE")) | (a.gate_final.eq("VERDE") & b.gate_final.eq("ROJO"))
    assert int(mask.sum()) == 9
    rows = []
    for date in a.index[mask]:
        result = {"date": date}
        for arm in ARMS:
            core, row = cores[arm], finals[arm].loc[date]
            valid = core.loc[:date].loc[lambda x: x.Calidad.eq("OK") & np.isfinite(x.lnRMSSD) & np.isfinite(x.HR_stable) & np.isfinite(x.RMSSD_stable)].tail(3)
            assert len(valid) == 3
            ln, hr = valid.lnRMSSD.mean(), valid.HR_stable.mean()
            threshold_ln = row.ln_base60 - 2 * max(row.SWC_ln, 0.04879)
            veto = bool(row.Calidad == "OK" and row.lnRMSSD_today < threshold_ln)
            assert veto == bool(row.veto_agudo)
            assert np.isclose(row.lnRMSSD_used, row.lnRMSSD_today if veto else ln, atol=1e-10, rtol=0)
            assert np.isclose(row.HR_used, row.HR_today if veto else hr, atol=1e-10, rtol=0)
            assert gate(row.lnRMSSD_used, row.HR_used, row) == row.gate_final
            result[arm] = {
                "rmssd_ms": float(row.RMSSD_stable),
                "quality": row.Calidad,
                "tail_mismatch_pct": float(row.tail_mismatch_pct),
                "raw_gate": row.gate_raw_today,
                "final_gate": row.gate_final,
                "veto": veto,
                "veto_threshold_ms": float(np.exp(threshold_ln)),
                "raw_minus_veto_threshold_ms": float(row.RMSSD_stable - np.exp(threshold_ln)),
                "roll_dates": list(valid.index),
                "roll_geometric_rmssd_ms": float(np.exp(ln)),
                "used_geometric_rmssd_ms": float(np.exp(row.lnRMSSD_used)),
                "local_gate_without_veto": gate(ln, hr, row),
                "hr_above_upper_threshold_bpm": float(row.HR_used - row.HR_base60 - row.SWC_HR),
                "ln_above_lower_threshold": float(row.lnRMSSD_used - row.ln_base60 + row.SWC_ln),
            }
        rows.append(result)
    pct = [100 * (r[ARMS[1]]["rmssd_ms"] / r[ARMS[0]]["rmssd_ms"] - 1) for r in rows]
    result = {
        "source": str(SOURCE),
        "scope": "Nine selected discordant days; not a random sample or physiological validation.",
        "n": len(rows),
        "raw_gate_equal": sum(r[ARMS[0]]["raw_gate"] == r[ARMS[1]]["raw_gate"] for r in rows),
        "veto_differs": sum(r[ARMS[0]]["veto"] != r[ARMS[1]]["veto"] for r in rows),
        "today_quality_differs": sum(r[ARMS[0]]["quality"] != r[ARMS[1]]["quality"] for r in rows),
        "median_absolute_rmssd_difference_pct": float(np.median(np.abs(pct))),
        "max_absolute_rmssd_difference_pct": float(np.max(np.abs(pct))),
        "days": rows,
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(result, indent=2, ensure_ascii=False, allow_nan=False), encoding="utf-8")
    print(json.dumps({k: v for k, v in result.items() if k != "days"}, ensure_ascii=False))
    for row in rows:
        print(row["date"], [(n, round(row[n]["rmssd_ms"], 3), row[n]["final_gate"], row[n]["veto"], row[n]["roll_dates"]) for n in ARMS])


if __name__ == "__main__":
    main()
