"""Read existing HG-04 copies only; no RR replay, writes or operational changes.

Print aggregate differences and a bounded list of counterexamples. No daily
personal table is persisted in research. Source snapshot dates are explicit.
"""
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[4]
SOURCE = ROOT / "out/hg04_copias_paralelas_2026-10-22"


def main():
    arms = ("C", "H3S90", "H3S90T375", "H3S90T375NL")
    core = {a: pd.read_csv(SOURCE / a / "ENDURANCE_HRV_master_CORE.csv").set_index("Fecha") for a in arms}
    cut = core["H3S90T375"]
    for arm, frame in core.items():
        assert frame.index.is_unique and frame.index.equals(cut.index)
        print("SOURCE", arm, len(frame), frame.index.min(), frame.index.max())
    for arm in ("C", "H3S90"):
        ref = core[arm]
        for cohort, mask in (
            ("both_OK", ref.Calidad.eq("OK") & cut.Calidad.eq("OK")),
            ("both_not_INVALID", ref.Calidad.ne("INVALID") & cut.Calidad.ne("INVALID")),
        ):
            t = pd.DataFrame({"reference_ms": ref.RMSSD_stable, "cut_ms": cut.RMSSD_stable,
                              "reference_hr": ref.HR_stable, "cut_hr": cut.HR_stable}).loc[mask].dropna()
            t["delta_ms"] = t.cut_ms - t.reference_ms
            t["delta_pct"] = 100 * t.delta_ms / t.reference_ms
            t["delta_hr"] = t.cut_hr - t.reference_hr
            print("COMPARISON", arm, cohort, len(t))
            print(t[["delta_ms", "delta_pct", "delta_hr"]].agg(["mean", "median", "min", "max"]).round(4))
            print("ABS_PERCENT_QUANTILES", t.delta_pct.abs().quantile([.5, .9, .95, .99]).round(4).to_dict())
            print("ABS_PERCENT_COUNTS", {k: int(t.delta_pct.abs().gt(k).sum()) for k in (5, 10, 15)})
            if cohort == "both_OK":
                print(t.loc[t.delta_pct.abs().nlargest(5).index].round(4).to_string())
    nl = core["H3S90T375NL"]
    for field in ("RMSSD_stable", "HR_stable"):
        assert np.allclose(cut[field], nl[field], equal_nan=True)
        print("PARITY", field, True)
    print("QUALITY_TRANSITIONS", pd.crosstab(cut.Calidad, nl.Calidad).to_string())
    finals = {}
    for arm in ("H3S90T375", "H3S90T375NL"):
        finals[arm] = pd.read_csv(SOURCE / arm / "ENDURANCE_HRV_master_FINAL.csv").set_index("Fecha")
        assert finals[arm].index.equals(cut.index)
        print("QUALITY", arm, core[arm].Calidad.value_counts().to_dict())
        print("GATE", arm, finals[arm].gate_final.value_counts().to_dict())
    print("GATE_CHANGES", int(finals["H3S90T375"].gate_final.ne(finals["H3S90T375NL"].gate_final).sum()))


if __name__ == "__main__":
    main()
