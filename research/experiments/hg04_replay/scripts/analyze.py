"""HG-04 replay, paso 3: comparar H3/H4/H34 contra el control C (no contra produccion).
Concordancia de lnRMSSD (correlacion, Bland-Altman, d de Cohen), transiciones de Calidad,
tasa de flags de estabilidad, y cambios de gate_final / Action en FINAL.
Escribe un resumen agregado y la lista de dias con cambio de gate en results/."""
import argparse, json, os
from pathlib import Path
import numpy as np, pandas as pd
from review_audit import control_parity, read_dated, saved_audit
ROOT = Path(__file__).resolve().parents[4]
WORK = Path(os.environ.get("HG04_REPLAY_WORK", Path.home() / "hg04_replay_work"))
RES = ROOT / "research/experiments/hg04_replay/results"
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--saved-only", action="store_true", help="Audit saved change lists without replay outputs")
args = parser.parse_args()
if args.saved_only:
    print(json.dumps(saved_audit(RES), indent=2, ensure_ascii=False))
    raise SystemExit(0)
parity = control_parity(WORK, ROOT / "data")
RES.mkdir(parents=True, exist_ok=True)
(RES / "control_parity.json").write_text(json.dumps(parity, indent=2, ensure_ascii=False), encoding="utf-8")
print("Control parity, all columns:", {k: v["parity"] for k, v in parity.items()})
ld = lambda a, f: read_dated(WORK / a / "data" / f"ENDURANCE_HRV_master_{f}.csv")
C, CF = ld("C", "CORE"), ld("C", "FINAL")
prod = pd.read_csv(ROOT / "data/ENDURANCE_HRV_master_CORE.csv").set_index("Fecha")
num = ["RMSSD_stable", "HR_stable", "SD1", "Calidad"]
diffp = [d for d in C.index if any(str(C.loc[d, k]) != str(prod.loc[d, k]) and not (pd.api.types.is_number(C.loc[d, k]) and np.isclose(C.loc[d, k], prod.loc[d, k], equal_nan=True)) for k in num)]
print("Control vs produccion, dias con valores distintos:", diffp)
out = {"control_vs_prod_days": diffp, "control_vs_prod_days_scope": num, "control_parity": parity}
def ba(x, y):
    d = y - x; m = d.mean(); s = d.std(ddof=1)
    pooled = np.sqrt((x.var(ddof=1) + y.var(ddof=1)) / 2)
    return dict(n=int(d.size), r=round(float(np.corrcoef(x, y)[0, 1]), 4), bias=round(float(m), 4),
                loa=[round(float(m - 1.96 * s), 4), round(float(m + 1.96 * s), 4)],
                cohen_d=round(float(m / pooled), 3), d_z=round(float(m / s), 3) if s > 0 else None,
                p95_abs=round(float(d.abs().quantile(.95)), 4), max_abs=round(float(d.abs().max()), 4))
for a in ["H3", "H4", "H34", "H4w", "H4v", "H4e", "H4e210", "H4e240"]:
    X, XF = ld(a, "CORE"), ld(a, "FINAL")
    if not X.index.equals(C.index) or not XF.index.equals(CF.index):
        raise ValueError(f"Date coverage differs in arm {a}")
    r = {}
    for lab, mask in [("todos_no_INVALID_ambos", (C.Calidad != "INVALID") & (X.Calidad != "INVALID")),
                      ("OK_en_ambos", (C.Calidad == "OK") & (X.Calidad == "OK"))]:
        x, y = C.loc[mask, "lnRMSSD"].astype(float), X.loc[mask, "lnRMSSD"].astype(float)
        k = x.notna() & y.notna(); r[lab] = ba(x[k], y[k])
    r["calidad_transiciones"] = pd.crosstab(C.Calidad, X.Calidad).to_dict()
    r["stability_unstable"] = {"C": int((C.HRV_Stability == "Unstable").sum()), a: int((X.HRV_Stability == "Unstable").sum())}
    r["stab_mismatch"] = {"C": int(C.Flags.astype(str).str.contains("STAB_LAST2_MISMATCH").sum()), a: int(X.Flags.astype(str).str.contains("STAB_LAST2_MISMATCH").sum())}
    g0, g1 = CF.gate_final.astype(str), XF.gate_final.reindex(CF.index).astype(str)
    ch = CF.index[g0 != g1]
    r["gate_cambios"] = int(len(ch)); r["gate_transiciones"] = pd.crosstab(g0, g1).to_dict()
    r["gate_cambios_2026"] = int(sum(str(d) >= "2026-01-01" for d in ch))
    r["gate_cambios_ultimos_90_registros"] = int(sum(d in set(CF.index[-90:]) for d in ch))
    cutoff = pd.to_datetime(CF.index).max().normalize() - pd.Timedelta(days=89)
    r["gate_cambios_ultimos_90_dias"] = int((pd.to_datetime(ch) >= cutoff).sum())
    r["action_cambios"] = int((CF.Action.astype(str) != XF.Action.reindex(CF.index).astype(str)).sum())
    r["baseline60_degraded_cambios"] = int((CF.baseline60_degraded.astype(str) != XF.baseline60_degraded.reindex(CF.index).astype(str)).sum())
    pd.DataFrame({"gate_C": g0[ch], f"gate_{a}": g1[ch], "Calidad_C": C.Calidad.reindex(ch), f"Calidad_{a}": X.Calidad.reindex(ch),
                  "lnRMSSD_C": C.lnRMSSD.reindex(ch).round(3), f"lnRMSSD_{a}": X.lnRMSSD.reindex(ch).round(3)}).to_csv(RES / f"gate_changes_{a}.csv")
    out[a] = r
(RES / "summary.json").write_text(json.dumps(out, indent=1, ensure_ascii=False, default=str))
saved_audit(RES)
for a in ["H3", "H4", "H34", "H4w", "H4v", "H4e", "H4e210", "H4e240"]:
    r = out[a]; print(f"\n== {a} ==")
    for k in ("todos_no_INVALID_ambos", "OK_en_ambos"): print(" ", k, r[k])
    print("  Unstable:", r["stability_unstable"], "| MISMATCH:", r["stab_mismatch"])
    print("  gate cambia:", r["gate_cambios"], "(2026:", r["gate_cambios_2026"], "| ultimos 90 registros:", r["gate_cambios_ultimos_90_registros"], "| ultimos 90 dias:", r["gate_cambios_ultimos_90_dias"], ") | Action cambia:", r["action_cambios"], "| baseline60_degraded cambia:", r["baseline60_degraded_cambios"])
    print("  Calidad C->"+a+":"); print(pd.DataFrame(r["calidad_transiciones"]).fillna(0).astype(int).to_string())
    print("  gate C->"+a+":"); print(pd.DataFrame(r["gate_transiciones"]).fillna(0).astype(int).to_string())
