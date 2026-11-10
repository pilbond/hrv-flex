"""HG-04 / HG-03: comparacion de las copias paralelas (2026-10-22).

Lee C, H3, H3S90, H3S120, H3S90T375 de $HOME/hg04_replay_work (run_parallel.py) y escribe:
  - out/hg04_copias_paralelas_2026-10-22/<copia>/ CORE y FINAL completos
  - out/hg04_copias_paralelas_2026-10-22/comparacion_dia_a_dia.xlsx
    (fuera de research/: research/AGENTS.md prohibe copias completas de datos personales)
  - research/experiments/hg04_replay/results/parallel_2026-10-22_summary.json (solo agregados)
Era: Polar < 2026-03-06 <= ECG (fecha del primer RR from_jsonl).
"""
from __future__ import annotations
import json, os, shutil
from pathlib import Path
import numpy as np, pandas as pd

ROOT = Path(__file__).resolve().parents[4]
WORK = Path(os.environ.get("HG04_REPLAY_WORK", Path.home() / "hg04_replay_work"))
OUT = ROOT / "out" / "hg04_copias_paralelas_2026-10-22"
RES = ROOT / "research/experiments/hg04_replay/results"
COPIES = ["C", "H3", "H3S90", "H3S120", "H3S90T375"]
LAB = {"C": "Actual", "H3": "HG-03", "H3S90": "HG-03 + 90s", "H3S120": "HG-03 + 120s",
       "H3S90T375": "HG-03 + 90s corte 375s"}
NEW = ["H3", "H3S90", "H3S120", "H3S90T375"]
ECG_START = "2026-03-06"

def load(a):
    c = pd.read_csv(WORK / a / "data/ENDURANCE_HRV_master_CORE.csv").set_index("Fecha")
    f = pd.read_csv(WORK / a / "data/ENDURANCE_HRV_master_FINAL.csv").set_index("Fecha")
    n = c.Notes.astype(str)
    c["t_start"] = n.str.extract(r"t_start_eff=([\d.]+)")[0].astype(float)
    c["dur_tramo"] = n.str.extract(r"dur_tramo=([\d.]+)")[0].astype(float)
    c["dur_eff"] = n.str.extract(r"dur_eff=([\d.]+)")[0].astype(float)
    c["mismatch"] = c.Flags.astype(str).str.contains("STAB_LAST2_MISMATCH")
    return c, f

D = {a: load(a) for a in COPIES}
idx = D["C"][0].index
era = pd.Series(np.where(idx >= ECG_START, "ECG", "Polar"), index=idx)
rsd = lambda x: float(1.4826 * np.median(np.abs(x - np.median(x)))) if len(x) else float("nan")

def ba(x, y):
    d = (y - x).dropna()
    if d.size < 3: return None
    x, y = x[d.index], y[d.index]; m, s = d.mean(), d.std(ddof=1)
    pooled = np.sqrt((x.var(ddof=1) + y.var(ddof=1)) / 2)
    return {"n": int(d.size), "sesgo": round(float(m), 4), "LoA": [round(float(m - 1.96 * s), 4), round(float(m + 1.96 * s), 4)],
            "d_cohen": round(float(m / pooled), 3), "d_z": round(float(m / s), 3) if s > 0 else None,
            "r": round(float(np.corrcoef(x, y)[0, 1]), 4), "p95_abs": round(float(d.abs().quantile(.95)), 4),
            "max_abs": round(float(d.abs().max()), 4)}

def sd_dad(core, mask):
    s = core.loc[mask & (core.Calidad != "INVALID"), "lnRMSSD"].dropna()
    t = pd.to_datetime(s.index.to_series())
    dd = s.diff()[t.diff().dt.days.eq(1).to_numpy()].dropna()
    return round(rsd(dd.to_numpy()) / np.sqrt(2), 4), int(dd.size)

def compare(a, ref):
    ca, fa = D[a]; cr, fr = D[ref]
    out = {}
    for e in ("total", "Polar", "ECG"):
        m = pd.Series(True, index=idx) if e == "total" else (era == e)
        okb = m & (cr.Calidad == "OK") & (ca.Calidad == "OK")
        gr, ga = fr.gate_final.reindex(idx).astype(str), fa.gate_final.reindex(idx).astype(str)
        out[e] = {
            "lnRMSSD_OK_ambos": ba(cr.lnRMSSD[okb], ca.lnRMSSD[okb]),
            "FC_OK_ambos": ba(cr.HR_stable[okb], ca.HR_stable[okb]),
            "cambios_semaforo": int(((gr != ga) & m).sum()),
            "cambios_accion": int(((fr.Action.reindex(idx).astype(str) != fa.Action.reindex(idx).astype(str)) & m).sum()),
            "cambios_calidad": int(((cr.Calidad != ca.Calidad) & m).sum()),
            "ROJO": [int(((gr == "ROJO") & m).sum()), int(((ga == "ROJO") & m).sum())],
            "STAB_LAST2_MISMATCH": [int((cr.mismatch & m).sum()), int((ca.mismatch & m).sum())],
            "Unstable": [int(((cr.HRV_Stability == "Unstable") & m).sum()), int(((ca.HRV_Stability == "Unstable") & m).sum())],
        }
    last90 = idx[-90:]
    out["cambios_semaforo_ultimos_90"] = int((fr.gate_final.reindex(last90).astype(str) != fa.gate_final.reindex(last90).astype(str)).sum())
    out["transiciones_semaforo"] = pd.crosstab(fr.gate_final.reindex(idx).astype(str).rename(ref), fa.gate_final.reindex(idx).astype(str).rename(a)).to_dict()
    out["transiciones_calidad"] = pd.crosstab(cr.Calidad.rename(ref), ca.Calidad.rename(a)).to_dict()
    return out

summary = {"fecha": "2026-10-22", "filas": int(len(idx)), "con_RR": int(D["C"][0].dur_eff.notna().sum()),
           "por_copia": {}, "vs_C": {}, "vs_H3": {}, "vs_H3S90": {}}
for a in COPIES:
    c, f = D[a]; r = {}
    for e in ("Polar", "ECG"):
        m = era == e; v = (c.Calidad != "INVALID") & m
        sd, n = sd_dad(c, m)
        r[e] = {"tramo_mediano_s": round(float(c.dur_tramo[v].median()), 1), "tramo_p5_s": round(float(c.dur_tramo[v].quantile(.05)), 1),
                "SD_dia_a_dia": sd, "n_pares_dias": n, "SWC_ln_mediano": round(float(f.SWC_ln.reindex(idx)[m].median()), 4),
                "lnRMSSD_mediano_OK": round(float(c.lnRMSSD[m & (c.Calidad == "OK")].median()), 4)}
    r["semaforo"] = f.gate_final.value_counts().to_dict()
    summary["por_copia"][a] = r
for a in NEW: summary["vs_C"][a] = compare(a, "C")
for a in ["H3S90", "H3S120", "H3S90T375"]: summary["vs_H3"][a] = compare(a, "H3")
summary["vs_H3S90"]["H3S90T375"] = compare("H3S90T375", "H3S90")
# descomposicion de H3: mismo inicio vs inicio distinto
c0, h3 = D["C"][0], D["H3"][0]
same = (c0.t_start == h3.t_start) | (c0.t_start.isna() & h3.t_start.isna())
dl = (h3.lnRMSSD - c0.lnRMSSD).abs()
g0, g3 = D["C"][1].gate_final.reindex(idx).astype(str), D["H3"][1].gate_final.reindex(idx).astype(str)
summary["H3_descomposicion"] = {k: {"dias": int(m.sum()), "dias_con_cambio_ln>0.001": int((dl[m] > 0.001).sum()),
                                     "abs_dln_mediana": round(float(dl[m].median()), 4), "abs_dln_p95": round(float(dl[m].quantile(.95)), 4),
                                     "abs_dln_max": round(float(dl[m].max()), 4), "cambios_semaforo": int(((g0 != g3) & m).sum())}
                                 for k, m in {"mismo_inicio": same, "inicio_distinto": ~same}.items()}

# ---- salidas ----
OUT.mkdir(parents=True, exist_ok=True)
for a in COPIES:
    (OUT / a).mkdir(exist_ok=True)
    for f in ("CORE", "FINAL"):
        shutil.copy2(WORK / a / "data" / f"ENDURANCE_HRV_master_{f}.csv", OUT / a / f"ENDURANCE_HRV_master_{f}.csv")
(RES / "parallel_2026-10-22_summary.json").write_text(json.dumps(summary, indent=1, ensure_ascii=False, default=str))

T = pd.DataFrame(index=idx); T.index.name = "Fecha"
T["Era"] = era; T["Duracion efectiva (s)"] = c0.dur_eff.round(0)
T["Inicio Actual (s)"] = c0.t_start; T["Inicio HG-03 (s)"] = h3.t_start; T["Mismo inicio Actual/HG-03"] = np.where(same, "si", "NO")
for a in COPIES: T[f"Tramo {LAB[a]} (s)"] = D[a][0].dur_tramo.round(0)
for a in COPIES: T[f"RMSSD {LAB[a]} (ms)"] = D[a][0].RMSSD_stable.round(1)
for a in COPIES: T[f"lnRMSSD {LAB[a]}"] = D[a][0].lnRMSSD.round(3)
for a in NEW: T[f"Δln {LAB[a]} − Actual"] = (D[a][0].lnRMSSD - c0.lnRMSSD).round(3)
for a in ["H3S90", "H3S120", "H3S90T375"]: T[f"Δln {LAB[a]} − HG-03"] = (D[a][0].lnRMSSD - h3.lnRMSSD).round(3)
T["Δln corte 375s − HG-03 + 90s"] = (D["H3S90T375"][0].lnRMSSD - D["H3S90"][0].lnRMSSD).round(3)
T["ΔFC corte 375s − HG-03 + 90s"] = (D["H3S90T375"][0].HR_stable - D["H3S90"][0].HR_stable).round(2)
for a in COPIES: T[f"FC {LAB[a]}"] = D[a][0].HR_stable.round(1)
for a in COPIES: T[f"Calidad {LAB[a]}"] = D[a][0].Calidad
for a in COPIES: T[f"Semáforo {LAB[a]}"] = D[a][1].gate_final.reindex(idx)
for a in COPIES: T[f"Acción {LAB[a]}"] = D[a][1].Action.reindex(idx)
gates = pd.concat([D[a][1].gate_final.reindex(idx).astype(str) for a in COPIES], axis=1)
cals = pd.concat([D[a][0].Calidad.astype(str) for a in COPIES], axis=1)
T["Cambia semáforo"] = np.where(gates.nunique(axis=1) > 1, "SI", "")
T["Cambia Calidad"] = np.where(cals.nunique(axis=1) > 1, "SI", "")
T = T.reset_index()

xl = OUT / "comparacion_dia_a_dia.xlsx"
with pd.ExcelWriter(xl, engine="openpyxl") as w:
    T.to_excel(w, sheet_name="Dia a dia", index=False)
    rows = []
    for ref, a in [("C", x) for x in NEW] + [("H3S90", "H3S90T375")]:
        for e in ("Polar", "ECG", "total"):
            s = summary["vs_C" if ref == "C" else "vs_H3S90"][a][e]; b = s["lnRMSSD_OK_ambos"] or {}; h = s["FC_OK_ambos"] or {}
            rows.append({"Copia": LAB[a], "Referencia": LAB[ref], "Era": e, "n OK ambos": b.get("n"), "Sesgo lnRMSSD": b.get("sesgo"),
                         "LoA inf": (b.get("LoA") or [None, None])[0], "LoA sup": (b.get("LoA") or [None, None])[1],
                         "d_z": b.get("d_z"), "Sesgo FC (lpm)": h.get("sesgo"), "LoA FC inf": (h.get("LoA") or [None, None])[0],
                         "LoA FC sup": (h.get("LoA") or [None, None])[1], "Cambios semáforo": s["cambios_semaforo"], "Cambios acción": s["cambios_accion"],
                         "Cambios Calidad": s["cambios_calidad"], "ROJO referencia": s["ROJO"][0], "ROJO copia": s["ROJO"][1],
                         "MISMATCH referencia": s["STAB_LAST2_MISMATCH"][0], "MISMATCH copia": s["STAB_LAST2_MISMATCH"][1]})
    pd.DataFrame(rows).to_excel(w, sheet_name="Resumen comparaciones", index=False)
    rows = []
    for a in COPIES:
        for e in ("Polar", "ECG"):
            r = summary["por_copia"][a][e]
            rows.append({"Copia": LAB[a], "Era": e, "Tramo mediano (s)": r["tramo_mediano_s"], "Tramo p5 (s)": r["tramo_p5_s"],
                         "SD día a día": r["SD_dia_a_dia"], "SWC_ln mediano": r["SWC_ln_mediano"], "lnRMSSD mediano (OK)": r["lnRMSSD_mediano_OK"]})
    pd.DataFrame(rows).to_excel(w, sheet_name="Por copia", index=False)
    for a in NEW:
        pd.DataFrame(summary["vs_C"][a]["transiciones_semaforo"]).fillna(0).astype(int).rename_axis("Actual \\ " + LAB[a]).to_excel(w, sheet_name=f"Semaforo {LAB[a]}"[:31])
    A, B = "H3S90", "H3S90T375"
    ca, fa = D[A]; cb, fb = D[B]
    P = pd.DataFrame(index=idx); P.index.name = "Fecha"
    P["Era"] = era
    P["Duracion efectiva sin corte (s)"] = ca.dur_eff.round(0)
    P["Duracion efectiva con corte (s)"] = cb.dur_eff.round(0)
    P["Tramo sin corte (s)"] = ca.dur_tramo.round(0)
    P["Tramo con corte (s)"] = cb.dur_tramo.round(0)
    P["RMSSD sin corte (ms)"] = ca.RMSSD_stable.round(1)
    P["RMSSD con corte (ms)"] = cb.RMSSD_stable.round(1)
    P["Δ RMSSD (ms)"] = (cb.RMSSD_stable - ca.RMSSD_stable).round(1)
    P["lnRMSSD sin corte"] = ca.lnRMSSD.round(3)
    P["lnRMSSD con corte"] = cb.lnRMSSD.round(3)
    P["Δ lnRMSSD"] = (cb.lnRMSSD - ca.lnRMSSD).round(3)
    P["FC sin corte"] = ca.HR_stable.round(1)
    P["FC con corte"] = cb.HR_stable.round(1)
    P["Δ FC (lpm)"] = (cb.HR_stable - ca.HR_stable).round(2)
    P["Calidad sin corte"] = ca.Calidad
    P["Calidad con corte"] = cb.Calidad
    P["Flags sin corte"] = ca.Flags.astype(str).replace("nan", "")
    P["Flags con corte"] = cb.Flags.astype(str).replace("nan", "")
    P["Semáforo sin corte"] = fa.gate_final.reindex(idx)
    P["Semáforo con corte"] = fb.gate_final.reindex(idx)
    P["Acción sin corte"] = fa.Action.reindex(idx)
    P["Acción con corte"] = fb.Action.reindex(idx)
    P["Cambia semáforo"] = np.where(fa.gate_final.reindex(idx).astype(str) != fb.gate_final.reindex(idx).astype(str), "SI", "")
    P["Cambia Calidad"] = np.where(ca.Calidad.astype(str) != cb.Calidad.astype(str), "SI", "")
    P.reset_index().to_excel(w, sheet_name="90s vs corte 375s", index=False)

    pd.DataFrame([{"": "Que es cada copia", " ": ""},
        {"": "Actual", " ": "Producción reprocesada con el código vigente (verificada contra el CORE real)."},
        {"": "HG-03", " ": "Solo pares RR originalmente consecutivos (rr_pair_diffs). Detector de estabilización y Calidad sin cambios."},
        {"": "HG-03 + 90s / 120s", " ": "HG-03 + tramo [90 s o 120 s, final del registro − 15 s]. El detector ya no decide el tramo; Calidad sigue la regla vigente."},
        {"": "HG-03 + 90s corte 375s", " ": "Como HG-03 + 90s, pero simulando grabaciones de 375 s: se descartan los latidos que terminan después de 375 s; con el recorte final de 15 s el tramo queda [90, 360] s. Los registros de ≤375 s no cambian."},
        {"": "90s vs corte 375s", " ": "Hoja aparte con solo esas dos copias, día a día: duración, tramo, RMSSD, lnRMSSD, FC, Calidad, Flags, semáforo y acción, más las diferencias. Aísla el efecto de acortar la grabación a 375 s."},
        {"": "Resumen comparaciones", " ": "Cada copia frente a Actual, y la copia con corte frente a HG-03 + 90s (aísla el efecto de acortar la grabación)."},
        {"": "Mismo inicio Actual/HG-03", " ": "NO = el detector eligió otro inicio al aplicar HG-03; el cambio de ese día mezcla corrección de pares y tramo distinto."},
        {"": "Era", " ": "Polar hasta 2026-03-05; ECG desde 2026-03-06."},
        {"": "Limitación", " ": "Muestra dónde y cuánto cambia; no indica qué versión es fisiológicamente correcta."},
        {"": "Sin RR", " ": "2026-02-26, 2026-02-27 y 2026-03-03 conservan su fila antigua en todas las copias."}]).to_excel(w, sheet_name="Leeme", index=False)

from openpyxl import load_workbook
from openpyxl.styles import PatternFill, Font
from openpyxl.formatting.rule import FormulaRule
from openpyxl.utils import get_column_letter
wb = load_workbook(xl)
for ws in wb.worksheets:
    for c in ws[1]: c.font = Font(bold=True)
    for col in ws.columns:
        L = max(len(str(c.value)) if c.value is not None else 0 for c in col)
        ws.column_dimensions[get_column_letter(col[0].column)].width = min(max(10, L + 2), 48)
ws = wb["Dia a dia"]
ws.freeze_panes = "C2"; ws.auto_filter.ref = ws.dimensions
hdr = {c.value: c.column for c in ws[1]}
amber = PatternFill("solid", fgColor="FFF2CC")
colors = {"ROJO": "F4CCCC", "ÁMBAR": "FCE5CD", "VERDE": "D9EAD3"}
def paint(sheet):
    h = {c.value: c.column for c in sheet[1]}
    for nm in ("Cambia semáforo", "Cambia Calidad", "Mismo inicio Actual/HG-03"):
        if nm not in h: continue
        col = get_column_letter(h[nm]); val = "NO" if nm.startswith("Mismo") else "SI"
        sheet.conditional_formatting.add(f"{col}2:{col}{sheet.max_row}", FormulaRule(formula=[f'${col}2="{val}"'], fill=amber))
    for nm, ci in h.items():
        if str(nm).startswith("Semáforo"):
            col = get_column_letter(ci)
            for g, rgb in colors.items():
                sheet.conditional_formatting.add(f"{col}2:{col}{sheet.max_row}", FormulaRule(formula=[f'${col}2="{g}"'], fill=PatternFill("solid", fgColor=rgb)))
paint(ws)
ws2 = wb["90s vs corte 375s"]
ws2.freeze_panes = "B2"; ws2.auto_filter.ref = ws2.dimensions
paint(ws2)
wb["Leeme"].column_dimensions["B"].width = 110
wb.move_sheet("Leeme", offset=-len(wb.sheetnames) + 1)
wb.save(xl)
print("ok", xl, T.shape)
print(json.dumps({k: summary[k] for k in ("filas", "con_RR", "H3_descomposicion")}, indent=1, ensure_ascii=False))
