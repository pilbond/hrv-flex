"""HG-04: dias decisivos para Calidad y semaforo entre las cuatro politicas ya ensayadas (2026-10-25).

Exploratorio. NO recalcula CORE ni repite el replay de RR: lee solo resultados ya guardados.
Base fija: HG-03 + inicio 90 s + corte 375 s (copia H3S90T375 / H3S90T375NL).

Entradas (solo lectura):
  out/hg04_calidad_semaforo_incremental_2026-10-23/comparacion_incremental.csv
  out/hg04_calidad_semaforo_incremental_2026-10-23/dias_afectados.csv
  out/hg04_copias_paralelas_2026-10-22/H3S90T375/ENDURANCE_HRV_master_CORE.csv
  out/hg04_copias_paralelas_2026-10-22/H3S90T375NL/ENDURANCE_HRV_master_{CORE,FINAL}.csv

Politicas comparadas (columnas ya presentes en el CSV incremental):
  NL_actual              sin la penalizacion LAT_NAN; MISMATCH y veto vigentes
  NL_sin_mismatch        + sin la regla STAB_LAST2_MISMATCH en Calidad
  NL_ambar               + el veto emite ÁMBAR cuando el gate del roll-3 no seria ROJO
  NL_sin_mismatch_ambar  combinada

Dia decisivo = alguna de las cuatro politicas difiere de otra en Calidad o en gate_final.

Atribucion (corregida 2026-10-25 tras revision del usuario): en las comparaciones de UNA sola regla
(NL sin MISMATCH, NL veto ambar) la etiqueta A/B/C es causal, porque solo hay una regla en juego. En la
comparacion combinada NO lo es: las referencias historicas varian casi siempre, de modo que una etiqueta
basada en "detecto una diferencia numerica" atribuia a las referencias cambios de color producidos por el
veto. La combinada se atribuye ahora con un diseno 2x2: se comprueba que regla por si sola reproduce el
color combinado (veto ambar, quitar MISMATCH, ambas, o interaccion si ninguna lo logra sola). La columna
"Que varia" se conserva como descripcion, no como causa.

Verificaciones que ejecuta y que abortan el script si fallan:
  1. la base del CSV incremental coincide con el CORE de H3S90T375
  2. la politica NL_actual coincide con el CORE/FINAL de H3S90T375NL
  3. la composicion reconstruida del roll-3 reproduce lnRMSSD_used (o ln_pre_veto con veto)
  4. el conjunto de dias decisivos coincide con dias_afectados.csv
  5. la regla del veto ambar reproduce el color en los dias con veto

Salidas: out/hg04_dias_decisivos_2026-10-25/ (tabla filtrable) y
         research/experiments/hg04_replay/results/decisive_days_2026-10-25.json (agregados + huellas).
"""
from __future__ import annotations
import hashlib, json
from pathlib import Path
import numpy as np, pandas as pd

ROOT = Path(__file__).resolve().parents[4]
INC = ROOT / "out/hg04_calidad_semaforo_incremental_2026-10-23"
COP = ROOT / "out/hg04_copias_paralelas_2026-10-22"
OUT = ROOT / "out/hg04_dias_decisivos_2026-10-25"
RES = ROOT / "research/experiments/hg04_replay/results/decisive_days_2026-10-25.json"
POL = ["NL_actual", "NL_sin_mismatch", "NL_ambar", "NL_sin_mismatch_ambar"]
LAB = {"NL_actual": "NL", "NL_sin_mismatch": "NL sin MISMATCH",
       "NL_ambar": "NL veto ámbar", "NL_sin_mismatch_ambar": "combinada"}
ECG_START = "2026-03-06"
SWC_FLOOR = 0.04879
VETO_MULT = 2.0
# flags que penalizan Calidad en cada politica (LAT_NAN nunca penaliza: todas son NL)
PEN = {"NL_actual": ["STAB_LAST2_MISMATCH", "ART_GT15", "STAB_TAIL_SHORT"],
       "NL_sin_mismatch": ["ART_GT15", "STAB_TAIL_SHORT"]}
PEN["NL_ambar"] = PEN["NL_actual"]
PEN["NL_sin_mismatch_ambar"] = PEN["NL_sin_mismatch"]

sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
bo = lambda s: s.astype(str).str.strip().str.lower().isin(["true", "1", "1.0"])


def main():
    I = pd.read_csv(INC / "comparacion_incremental.csv", encoding="utf-8-sig").set_index("Fecha")
    A = pd.read_csv(INC / "dias_afectados.csv", encoding="utf-8-sig").set_index("Fecha")
    Tc = pd.read_csv(COP / "H3S90T375/ENDURANCE_HRV_master_CORE.csv").set_index("Fecha")
    Nc = pd.read_csv(COP / "H3S90T375NL/ENDURANCE_HRV_master_CORE.csv").set_index("Fecha")
    Nf = pd.read_csv(COP / "H3S90T375NL/ENDURANCE_HRV_master_FINAL.csv").set_index("Fecha")
    num = lambda c: pd.to_numeric(I[c], errors="coerce")
    rm, hr = num("RMSSD_stable"), num("HR_stable")
    ln = np.log(rm.where(rm > 0))
    idx = list(I.index)
    dt = pd.to_datetime(pd.Series(idx, index=idx))

    # --- verificacion 1 y 2 ---
    chk = {}
    for nm, a, b in [("RMSSD base vs CORE corte", rm, pd.to_numeric(Tc.RMSSD_stable, errors="coerce")),
                     ("HR base vs CORE corte", hr, pd.to_numeric(Tc.HR_stable, errors="coerce")),
                     ("ln_base60 NL vs FINAL NL", num("ln_base60_NL_actual"), pd.to_numeric(Nf.ln_base60, errors="coerce")),
                     ("lnRMSSD_used NL vs FINAL NL", num("lnRMSSD_used_NL_actual"), pd.to_numeric(Nf.lnRMSSD_used, errors="coerce")),
                     ("HR_used NL vs FINAL NL", num("HR_used_NL_actual"), pd.to_numeric(Nf.HR_used, errors="coerce")),
                     ("SWC_ln NL vs FINAL NL", num("SWC_ln_NL_actual"), pd.to_numeric(Nf.SWC_ln, errors="coerce"))]:
        d = (a - b.reindex(idx)).abs().max()
        chk[nm] = float(d); assert not (d > 1e-9), f"{nm}: maxdif {d}"
    for nm, a, b in [("Calidad NL vs CORE NL", I.Calidad_NL_actual, Nc.Calidad),
                     ("gate NL vs FINAL NL", I.gate_final_NL_actual, Nf.gate_final),
                     ("Flags base vs CORE corte", I.Flags, Tc.Flags)]:
        n = int((a.astype(str).str.strip() != b.reindex(idx).astype(str).str.strip()).sum())
        chk[nm] = n; assert n == 0, nm

    # --- roll-3 reconstruido por politica ---
    def roll3(p):
        clean = (I["Calidad_" + p] == "OK") & ln.notna() & hr.notna() & rm.notna()
        out = {}
        for i, d in enumerate(idx):
            t, j = [], i
            while j >= 0 and len(t) < 3:
                if clean.iloc[j]: t.append(idx[j])
                j -= 1
            out[d] = t
        return out
    R = {p: roll3(p) for p in POL}

    # --- verificacion 3: el trio reproduce la señal usada ---
    worst = 0.0
    for p in POL:
        v = bo(I["veto_agudo_" + p])
        tgt = np.where(v, num("ln_pre_veto_" + p), num("lnRMSSD_used_" + p))
        rec = np.array([np.mean([ln[x] for x in R[p][d]]) if R[p][d] else np.nan for d in idx])
        ok = np.isfinite(tgt)
        worst = max(worst, float(np.nanmax(np.abs(rec - tgt)[ok])))
    chk["roll3 reconstruido vs señal usada"] = worst; assert worst < 1e-9, worst

    # --- verificacion 5: regla del veto ambar ---
    exc = []
    for d in idx:
        if not bo(I["veto_agudo_NL_ambar"])[d] or I["gate_final_NL_actual"][d] != "ROJO": continue
        tri = R["NL_ambar"][d]
        pl, ph = float(np.mean([ln[x] for x in tri])), float(np.mean([hr[x] for x in tri]))
        rojo = (pl - num("ln_base60_NL_ambar")[d] < -num("SWC_ln_NL_ambar")[d]) and \
               (ph - num("HR_base60_NL_ambar")[d] > num("SWC_HR_NL_ambar")[d])
        if ("ROJO" if rojo else "ÁMBAR") != I["gate_final_NL_ambar"][d]: exc.append(d)
    chk["excepciones regla veto ambar"] = exc; assert not exc, exc

    # --- conjunto decisivo y verificacion 4 ---
    cal = pd.DataFrame({p: I["Calidad_" + p] for p in POL})
    gat = pd.DataFrame({p: I["gate_final_" + p] for p in POL})
    dec = (cal.nunique(axis=1) > 1) | (gat.nunique(axis=1) > 1)
    chk["conjunto decisivo == dias_afectados.csv"] = set(A.index) == set(I.index[dec])
    assert chk["conjunto decisivo == dias_afectados.csv"]

    def varia(d, q):
        """Descriptivo: QUE difiere entre las dos politicas ese dia. No es una atribucion causal."""
        out = []
        if I["Calidad_NL_actual"][d] != I["Calidad_" + q][d]: out.append("elegibilidad del dia")
        if tuple(R["NL_actual"][d]) != tuple(R[q][d]): out.append("lecturas del trio")
        if any(not np.isclose(num(c + "NL_actual")[d], num(c + q)[d], equal_nan=True)
               for c in ("ln_base60_", "SWC_ln_", "HR_base60_", "SWC_HR_", "lnRMSSD_used_", "HR_used_")):
            out.append("referencias historicas")
        if bool(bo(I["veto_agudo_NL_actual"])[d]) != bool(bo(I["veto_agudo_" + q])[d]): out.append("activacion del veto")
        # corregido 2026-10-25: la razon cambia por varias causas (p.ej. BASE60_INSUF -> 2D_AMBOS al
        # recuperar dias OK), no solo por la regla del veto; la causa esta en la columna 2x2.
        if I["gate_razon_base60_NL_actual"][d] != I["gate_razon_base60_" + q][d]: out.append("cambia la razon del semaforo")
        return " + ".join(out) if out else "nada"

    def mech(d, q):
        """Mecanismo causal. Solo valido para las comparaciones de una regla; la combinada usa regla()."""
        if I["Calidad_NL_actual"][d] != I["Calidad_" + q][d]: return "A elegibilidad del dia"
        if tuple(R["NL_actual"][d]) != tuple(R[q][d]): return "B lecturas del trio"
        for c in ("ln_base60_", "SWC_ln_", "HR_base60_", "SWC_HR_", "lnRMSSD_used_", "HR_used_"):
            if not np.isclose(num(c + "NL_actual")[d], num(c + q)[d], equal_nan=True): return "B referencias historicas"
        if bool(bo(I["veto_agudo_NL_actual"])[d]) != bool(bo(I["veto_agudo_" + q])[d]): return "B referencias historicas"
        return "C solo regla del veto"

    def regla(d):
        """Atribucion 2x2 del color en la politica combinada: que regla por si sola lo reproduce."""
        gc = I["gate_final_NL_sin_mismatch_ambar"][d]
        if I["gate_final_NL_actual"][d] == gc: return "sin cambio de color"
        sa = I["gate_final_NL_ambar"][d] == gc
        sm = I["gate_final_NL_sin_mismatch"][d] == gc
        if sa and sm: return "ambas reglas por separado"
        if sa: return "veto ambar"
        if sm: return "quitar MISMATCH"
        return "interaccion de las dos reglas"

    rows = []
    for d in I.index[dec]:
        fl = str(I.Flags[d]) if pd.notna(I.Flags[d]) else ""
        r = {"Fecha": d, "Era": "ECG" if d >= ECG_START else "Polar",
             "RMSSD diario (ms)": round(float(rm[d]), 2), "lnRMSSD diario": round(float(ln[d]), 4),
             "FC diaria (lpm)": round(float(hr[d]), 2), "Artefactos (%)": round(float(num("Artifact_pct")[d]), 2),
             "Flags del CORE": fl, "Stability_Subtype": I.Stability_Subtype[d],
             "Cambia Calidad": "SI" if cal.loc[d].nunique() > 1 else "",
             "Cambia semáforo": "SI" if gat.loc[d].nunique() > 1 else ""}
        for q in POL[1:2] + POL[2:3]:
            cambia = (I["Calidad_NL_actual"][d] != I["Calidad_" + q][d]
                      or I["gate_final_NL_actual"][d] != I["gate_final_" + q][d])
            r[f"Mecanismo {LAB[q]} vs NL"] = mech(d, q) if cambia else ""
        q = "NL_sin_mismatch_ambar"
        cambia = (I["Calidad_NL_actual"][d] != I["Calidad_" + q][d]
                  or I["gate_final_NL_actual"][d] != I["gate_final_" + q][d])
        r["Regla que cambia el color (combinada)"] = regla(d) if cambia else ""
        r["Qué varía (combinada, descriptivo)"] = varia(d, q) if cambia else ""
        for p in POL:
            L = LAB[p]; tri = R[p][d]; ages = [(dt[d] - dt[x]).days for x in tri]
            lb, sw = float(num("ln_base60_" + p)[d]), float(num("SWC_ln_" + p)[d])
            hb, sh = float(num("HR_base60_" + p)[d]), float(num("SWC_HR_" + p)[d])
            lu, hu = float(num("lnRMSSD_used_" + p)[d]), float(num("HR_used_" + p)[d])
            pen = "|".join(x for x in PEN[p] if x in fl)
            r.update({
                f"[{L}] Calidad": I["Calidad_" + p][d],
                f"[{L}] Motivo FLAG": pen,
                f"[{L}] Semáforo": I["gate_final_" + p][d],
                f"[{L}] Razón": I["gate_razon_base60_" + p][d],
                f"[{L}] Veto": "SI" if bo(I["veto_agudo_" + p])[d] else "",
                f"[{L}] Acción": f"{I['Action_' + p][d]} / {I['Action_detail_' + p][d]}",
                f"[{L}] Trío (fechas)": ", ".join(tri),
                f"[{L}] Trío antigüedad (d)": ", ".join(str(a) for a in ages),
                f"[{L}] Trío n": len(tri),
                f"[{L}] lnRMSSD usado": round(lu, 4),
                f"[{L}] lnRMSSD trío (pre-veto)": round(float(np.mean([ln[x] for x in tri])), 4) if tri else None,
                f"[{L}] FC usada (lpm)": round(hu, 2),
                f"[{L}] ln base60": round(lb, 4), f"[{L}] SWC_ln": round(sw, 4),
                f"[{L}] d_ln (usado − base)": round(lu - lb, 4), f"[{L}] umbral ln": round(-sw, 4),
                f"[{L}] FC base60": round(hb, 2), f"[{L}] SWC_HR": round(sh, 2),
                f"[{L}] d_FC (usada − base)": round(hu - hb, 2), f"[{L}] umbral FC": round(sh, 2),
                f"[{L}] umbral veto (ln)": round(lb - VETO_MULT * max(sw, SWC_FLOOR), 4),
            })
        rows.append(r)
    T = pd.DataFrame(rows)

    # --- agregados ---
    out = {"fecha": "2026-10-25", "estado": "exploratorio; no cambia produccion, contratos ni los ficheros del ensayo",
           "base": "HG-03 + inicio fijo 90 s + corte 375 s",
           "periodo": [idx[0], idx[-1]], "filas_base": len(I),
           "nota_2026_10_23": "ambas CSV incrementales terminan el 2026-10-22; la fila 2026-10-23 del Excel no existe aqui y queda fuera de todos los recuentos",
           "entradas_sha256": {str(p.relative_to(ROOT)): sha(p) for p in
                               [INC / "comparacion_incremental.csv", INC / "dias_afectados.csv",
                                COP / "H3S90T375/ENDURANCE_HRV_master_CORE.csv",
                                COP / "H3S90T375NL/ENDURANCE_HRV_master_CORE.csv",
                                COP / "H3S90T375NL/ENDURANCE_HRV_master_FINAL.csv"]},
           "verificaciones": chk,
           "dias_decisivos": int(dec.sum()),
           "cambia_calidad": int((cal.nunique(axis=1) > 1).sum()),
           "cambia_semaforo": int((gat.nunique(axis=1) > 1).sum()),
           "por_politica": {}, "vs_NL": {}}
    for p in POL:
        c = I["Calidad_" + p]; g = I["gate_final_" + p]
        out["por_politica"][p] = {"OK": int((c == "OK").sum()), "FLAG": int((c == "FLAG_mecánico").sum()),
                                  "INVALID": int((c == "INVALID").sum()),
                                  "semaforo": {k: int(v) for k, v in g.value_counts().items()},
                                  "veto": int(bo(I["veto_agudo_" + p]).sum())}
    for q in POL[1:]:
        c = I["Calidad_NL_actual"] != I["Calidad_" + q]; g = I["gate_final_NL_actual"] != I["gate_final_" + q]
        e = {"dias_cambian": int((c | g).sum()), "cambia_calidad": int(c.sum()), "cambia_semaforo": int(g.sum()),
             "transiciones": pd.crosstab(I.loc[g, "gate_final_NL_actual"], I.loc[g, "gate_final_" + q]).to_dict()}
        if q == "NL_sin_mismatch_ambar":
            lab = pd.Series({d: regla(d) for d in I.index[c | g]})
            e["regla_que_cambia_el_color"] = {k: int(v) for k, v in lab.value_counts().items()}
            r2a = I.index[(I.gate_final_NL_actual == "ROJO") & (I.gate_final_NL_sin_mismatch_ambar == "ÁMBAR")]
            e["ROJO_a_AMBAR"] = {"total": len(r2a),
                                 "por_regla": {k: int(v) for k, v in pd.Series({d: regla(d) for d in r2a}).value_counts().items()}}
            tr = I.index[(I.gate_final_NL_actual != "ROJO") & (I.gate_final_NL_sin_mismatch == "ROJO")]
            e["pasan_a_ROJO_al_quitar_MISMATCH"] = {"dias": list(tr),
                                                    "siguen_ROJO_en_combinada": int((I.gate_final_NL_sin_mismatch_ambar[tr] == "ROJO").sum())}
            e["nota"] = "atribucion 2x2; la etiqueta A/B/C no es causal en esta comparacion"
        else:
            lab = pd.Series({d: mech(d, q) for d in I.index[c | g]})
            e["mecanismos"] = {k: int(v) for k, v in lab.value_counts().items()}
        out["vs_NL"][q] = e
    OUT.mkdir(parents=True, exist_ok=True)
    T.to_csv(OUT / "dias_decisivos.csv", index=False, encoding="utf-8-sig")
    RES.write_text(json.dumps(out, indent=1, ensure_ascii=False))
    print(json.dumps({k: out[k] for k in ("verificaciones", "dias_decisivos", "cambia_calidad", "cambia_semaforo", "por_politica", "vs_NL")},
                     indent=1, ensure_ascii=False))
    print("\ncolumnas de la tabla:", len(T.columns), "| filas:", len(T))
    return T, out


def export_excel(T, out):
    """Tabla filtrable: resumen compacto, detalle completo, politicas y los dos casos paso a paso."""
    from openpyxl import load_workbook
    from openpyxl.styles import PatternFill, Font, Alignment
    from openpyxl.formatting.rule import FormulaRule
    from openpyxl.utils import get_column_letter
    I = pd.read_csv(INC / "comparacion_incremental.csv", encoding="utf-8-sig").set_index("Fecha")
    num = lambda c: pd.to_numeric(I[c], errors="coerce")
    rm = num("RMSSD_stable"); hr = num("HR_stable"); ln = np.log(rm.where(rm > 0))
    xl = OUT / "dias_decisivos.xlsx"
    comp = ["Fecha", "Era", "RMSSD diario (ms)", "FC diaria (lpm)", "Flags del CORE",
            "Cambia Calidad", "Cambia semáforo"] + \
           [f"[{LAB[p]}] Semáforo" for p in POL] + [f"[{LAB[p]}] Calidad" for p in POL] + \
           [f"Mecanismo {LAB[q]} vs NL" for q in POL[1:3]] + \
           ["Regla que cambia el color (combinada)", "Qué varía (combinada, descriptivo)"]
    casos = []
    for d in ("2026-06-27", "2026-04-17"):
        for p in POL:
            tri = [x.strip() for x in str(T.set_index("Fecha").loc[d, f"[{LAB[p]}] Trío (fechas)"]).split(",")] if d in set(T.Fecha) else None
            row = {"Caso": d, "Política": LAB[p]}
            if d in set(T.Fecha):
                r = T.set_index("Fecha").loc[d]
                for k in ("Calidad", "Motivo FLAG", "Semáforo", "Razón", "Veto", "Acción", "Trío (fechas)",
                          "Trío antigüedad (d)", "lnRMSSD usado", "lnRMSSD trío (pre-veto)", "FC usada (lpm)",
                          "ln base60", "SWC_ln", "d_ln (usado − base)", "umbral ln", "FC base60", "SWC_HR",
                          "d_FC (usada − base)", "umbral FC", "umbral veto (ln)"):
                    row[k] = r[f"[{LAB[p]}] {k}"]
                row["RMSSD diario (ms)"] = r["RMSSD diario (ms)"]; row["FC diaria (lpm)"] = r["FC diaria (lpm)"]
            else:
                # dia no decisivo: se calculan igualmente todos los derivados
                clean = (I["Calidad_" + p] == "OK") & ln.notna() & hr.notna() & rm.notna()
                ii = list(I.index).index(d); tri = []; j = ii
                while j >= 0 and len(tri) < 3:
                    if clean.iloc[j]: tri.append(I.index[j])
                    j -= 1
                dts = pd.to_datetime(pd.Series(list(I.index), index=list(I.index)))
                lb = float(num("ln_base60_" + p)[d]); sw = float(num("SWC_ln_" + p)[d])
                hb = float(num("HR_base60_" + p)[d]); sh = float(num("SWC_HR_" + p)[d])
                lu = float(num("lnRMSSD_used_" + p)[d]); hu = float(num("HR_used_" + p)[d])
                fl0 = str(I.Flags[d]) if pd.notna(I.Flags[d]) else ""
                row.update({"Calidad": I["Calidad_" + p][d],
                            "Motivo FLAG": "|".join(x for x in PEN[p] if x in fl0),
                            "Semáforo": I["gate_final_" + p][d],
                            "Razón": I["gate_razon_base60_" + p][d],
                            "Veto": "SI" if bo(I["veto_agudo_" + p])[d] else "",
                            "Acción": f"{I['Action_' + p][d]} / {I['Action_detail_' + p][d]}",
                            "Trío (fechas)": ", ".join(tri),
                            "Trío antigüedad (d)": ", ".join(str((dts[d] - dts[x]).days) for x in tri),
                            "lnRMSSD usado": round(lu, 4),
                            "lnRMSSD trío (pre-veto)": round(float(np.mean([ln[x] for x in tri])), 4) if tri else None,
                            "FC usada (lpm)": round(hu, 2),
                            "ln base60": round(lb, 4), "SWC_ln": round(sw, 4),
                            "d_ln (usado − base)": round(lu - lb, 4), "umbral ln": round(-sw, 4),
                            "FC base60": round(hb, 2), "SWC_HR": round(sh, 2),
                            "d_FC (usada − base)": round(hu - hb, 2), "umbral FC": round(sh, 2),
                            "umbral veto (ln)": round(lb - VETO_MULT * max(sw, SWC_FLOOR), 4),
                            "RMSSD diario (ms)": round(float(rm[d]), 2), "FC diaria (lpm)": round(float(hr[d]), 2),
                            "Nota": ("no es dia decisivo entre estas cuatro politicas, porque todas parten de haber quitado "
                                     "la penalizacion LAT_NAN; si lo es en la comparacion anterior: VERDE (2D_OK) con la Calidad "
                                     "del corte a 375 s y AMBAR (2D_HR) sin esa penalizacion, con Calidad OK en ambas")})
            casos.append(row)
    pol = pd.DataFrame([{"Política": LAB[p], "OK": out["por_politica"][p]["OK"], "FLAG": out["por_politica"][p]["FLAG"],
                         "INVALID": out["por_politica"][p]["INVALID"], "Veto": out["por_politica"][p]["veto"],
                         **{k: out["por_politica"][p]["semaforo"].get(k, 0) for k in ("VERDE", "ÁMBAR", "ROJO", "NO")}}
                        for p in POL])
    vs = pd.DataFrame([{"Comparación": f"{LAB[q]} vs NL", "Días que cambian": out["vs_NL"][q]["dias_cambian"],
                        "Cambia Calidad": out["vs_NL"][q]["cambia_calidad"],
                        "Cambia semáforo": out["vs_NL"][q]["cambia_semaforo"],
                        **out["vs_NL"][q].get("mecanismos", out["vs_NL"][q].get("regla_que_cambia_el_color", {}))}
                       for q in POL[1:]])
    leeme = pd.DataFrame([
        {"": "Qué es esta tabla", " ": "Los 82 días en que Calidad o semáforo cambia entre las cuatro políticas ensayadas. Base fija: HG-03 + inicio 90 s + corte 375 s. No hay recálculo de CORE ni replay de RR."},
        {"": "Período y denominador", " ": f"{out['periodo'][0]} a {out['periodo'][1]}; {out['filas_base']} días en la base, de los cuales {out['dias_decisivos']} son decisivos."},
        {"": "NL", " ": "Quita la penalización de Calidad por LAT_NAN. Es la política de referencia de esta tabla."},
        {"": "NL sin MISMATCH", " ": "Además quita STAB_LAST2_MISMATCH de la regla de Calidad."},
        {"": "NL veto ámbar", " ": "Igual que NL en Calidad. Cuando salta el veto agudo y el gate del promedio de tres lecturas NO sería ROJO, emite ÁMBAR (razón EXP_VETO_AMBAR_SIN_ROJO_ROLL3). Verificado en los 75 días ROJO con veto, sin excepciones."},
        {"": "combinada", " ": "NL sin MISMATCH + veto ámbar."},
        {"": "Mecanismo A / B / C", " ": "Solo para las comparaciones de UNA regla (NL sin MISMATCH, NL veto ámbar), donde la etiqueta sí es causal. A = su propia Calidad cambia. B = su Calidad no cambia, pero sí el trío o las referencias, porque cambió la elegibilidad de otros días. C = Calidad, trío y referencias idénticos; cambia solo el color que emite el veto."},
        {"": "Regla que cambia el color (combinada)", " ": "CORREGIDO 2026-10-25. En la combinada las referencias varían casi siempre, así que una etiqueta A/B/C no distingue la causa. Se atribuye con diseño 2x2: qué regla por sí sola reproduce el color combinado. Resultado: 30 días por quitar MISMATCH, 30 por el veto ámbar, 1 interacción (2025-12-18) y 21 en que solo cambia la Calidad sin cambiar el color."},
        {"": "Qué varía (combinada)", " ": "Descripción de qué difiere ese día entre NL y la combinada. NO es la causa del cambio de color: para eso está la columna anterior. «Cambia la razón del semáforo» incluye casos ajenos al veto, como pasar de BASE60_INSUF a 2D_AMBOS al recuperar días OK."},
        {"": "Trío", " ": "Las hasta tres últimas lecturas limpias hasta ese día incluido, reconstruidas y verificadas contra lnRMSSD_used (o ln_pre_veto si hay veto): diferencia máxima 1e-15."},
        {"": "Umbrales", " ": "El gate marca RMSSD bajo si d_ln < −SWC_ln y FC alta si d_FC > SWC_HR; ROJO exige ambos. El veto salta si el lnRMSSD del día cae por debajo de base60 − 2 × max(SWC_ln, 0,04879)."},
        {"": "2026-10-23", " ": "Excluido: las dos CSV incrementales terminan el 2026-10-22 y no existen CORE/FINAL exportados de esa fecha en estas copias."},
        {"": "2026-06-27", " ": "No es decisivo entre estas cuatro políticas porque todas parten de haber quitado la penalización LAT_NAN. Sí lo es en la comparación anterior: con la Calidad del corte a 375 s era VERDE (2D_OK) y sin esa penalización es ÁMBAR (2D_HR), con Calidad OK en ambas. Ver la hoja de casos."},
        {"": "Limitación", " ": "La tabla dice qué hace cada política y en qué días. No establece qué política decide mejor: menos ROJOS no significa mejor rendimiento."},
    ])
    with pd.ExcelWriter(xl, engine="openpyxl") as w:
        leeme.to_excel(w, sheet_name="Leeme", index=False)
        T[comp].to_excel(w, sheet_name="Resumen dia a dia", index=False)
        T.to_excel(w, sheet_name="Detalle completo", index=False)
        pol.to_excel(w, sheet_name="Por politica", index=False)
        vs.fillna(0).to_excel(w, sheet_name="Mecanismos vs NL", index=False)
        pd.DataFrame(casos).to_excel(w, sheet_name="Casos paso a paso", index=False)
    wb = load_workbook(xl)
    colors = {"ROJO": "F4CCCC", "ÁMBAR": "FCE5CD", "VERDE": "D9EAD3", "NO": "EFEFEF"}
    for ws in wb.worksheets:
        for c in ws[1]: c.font = Font(bold=True); c.alignment = Alignment(wrap_text=True, vertical="center")
        ws.row_dimensions[1].height = 42
        for col in ws.columns:
            L = max(len(str(c.value)) if c.value is not None else 0 for c in col)
            ws.column_dimensions[get_column_letter(col[0].column)].width = min(max(10, L + 2), 42)
        if ws.title in ("Resumen dia a dia", "Detalle completo", "Casos paso a paso"):
            ws.freeze_panes = "C2"; ws.auto_filter.ref = ws.dimensions
        h = {c.value: c.column for c in ws[1]}
        for nm, ci in h.items():
            if "Semáforo" in str(nm) or str(nm) == "Semáforo":
                L = get_column_letter(ci)
                for g, rgb in colors.items():
                    ws.conditional_formatting.add(f"{L}2:{L}{ws.max_row}",
                        FormulaRule(formula=[f'${L}2="{g}"'], fill=PatternFill("solid", fgColor=rgb)))
            if nm in ("Cambia Calidad", "Cambia semáforo"):
                L = get_column_letter(ci)
                ws.conditional_formatting.add(f"{L}2:{L}{ws.max_row}",
                    FormulaRule(formula=[f'${L}2="SI"'], fill=PatternFill("solid", fgColor="FFF2CC")))
    wb["Leeme"].column_dimensions["B"].width = 118
    wb.save(xl)
    print("escrito", xl)


if __name__ == "__main__":
    _T, _out = main()
    export_excel(_T, _out)   # corregido 2026-10-25: antes el script no generaba el Excel
