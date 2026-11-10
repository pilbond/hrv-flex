"""HG-04: tabla auditable por dia para las dos propuestas (2026-10-25).

Exploratorio. No recalcula CORE ni repite el replay de RR. Lee:
  - out/hg04_calidad_semaforo_incremental_2026-10-23/comparacion_incremental.csv (4 politicas)
  - out/hg04_evidencia_mismatch_veto_2026-10-25/recuperados_29_diagnostico.csv (diagnostico tecnico)
  - data/ENDURANCE_HRV_{sessions_day,sleep,wellness_subjective}.csv (informacion independiente)
Criterios fijados en research/reports/hg04_protocolo_mismatch_veto_2026-10-25.md (escrito antes).
Escribe out/hg04_evidencia_mismatch_veto_2026-10-25/evidencia_por_dia.xlsx y los agregados.
"""
from __future__ import annotations
import hashlib, json
from pathlib import Path
import numpy as np, pandas as pd

ROOT = Path(__file__).resolve().parents[4]
INC = ROOT / "out/hg04_calidad_semaforo_incremental_2026-10-23/comparacion_incremental.csv"
OUT = ROOT / "out/hg04_evidencia_mismatch_veto_2026-10-25"
RES = ROOT / "research/experiments/hg04_replay/results/mismatch_veto_tables_2026-10-25.json"
PROT = ROOT / "research/reports/hg04_protocolo_mismatch_veto_2026-10-25.md"
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
bo = lambda s: s.astype(str).str.strip().str.lower().isin(["true", "1", "1.0"])


def main():
    I = pd.read_csv(INC, encoding="utf-8-sig").set_index("Fecha")
    D = pd.read_csv(OUT / "recuperados_29_diagnostico.csv", encoding="utf-8-sig").set_index("Fecha")
    S = pd.read_csv(ROOT / "data/ENDURANCE_HRV_sessions_day.csv").set_index("Fecha")
    SL = pd.read_csv(ROOT / "data/ENDURANCE_HRV_sleep.csv").set_index("Fecha")
    W = pd.read_csv(ROOT / "data/ENDURANCE_HRV_wellness_subjective.csv").set_index("Fecha")
    num = lambda c: pd.to_numeric(I[c], errors="coerce")
    rm, hr = num("RMSSD_stable"), num("HR_stable")
    ln = np.log(rm.where(rm > 0))
    idx = list(I.index); pos = {d: i for i, d in enumerate(idx)}
    # CORREGIDO 2026-10-25 (revision critica): hay que distinguir dos "dia anterior".
    # prev_cal = vispera de calendario, para carga/minutos/RPE/deriva del dia previo.
    # prev_med = medicion anterior, unico sentido posible para "hubo veto" (solo existe
    # en dias con medicion). Antes se usaba prev_med para todo, lo que con huecos de
    # medicion tomaba un dia equivocado: el 2025-09-24 leia 82 (del 21) en vez de 184
    # (del 23), y el 2025-10-05 leia 56 (del 3) en vez de 74 (del 4).
    prev_med = lambda d: idx[pos[d] - 1] if pos[d] > 0 else None
    prev_cal = lambda d: (pd.Timestamp(d) - pd.Timedelta(days=1)).strftime("%Y-%m-%d")
    nxt = lambda d, k: idx[pos[d] + k] if pos[d] + k < len(idx) else None
    gv = lambda df, c, d: (pd.to_numeric(df[c], errors="coerce").get(d, np.nan) if d is not None and c in df.columns else np.nan)

    def roll3(p, d):
        cl = (I["Calidad_" + p] == "OK") & ln.notna() & hr.notna() & rm.notna()
        t, j = [], pos[d]
        while j >= 0 and len(t) < 3:
            if cl.iloc[j]: t.append(idx[j])
            j -= 1
        return t

    def indep(d):
        """Informacion independiente del semaforo. Se marca como ausente cuando falta.

        "dia anterior" = vispera de CALENDARIO (prev_cal), no la medicion anterior.
        """
        p = prev_cal(d)
        return {"Carga día anterior": gv(S, "load_day", p), "Minutos día anterior": gv(S, "total_duration_min", p),
                "RPE máx día anterior": gv(S, "rpe_max_day", p), "Días intensos previos 3d": gv(S, "intense_days_prev_3d", d),
                "Deriva cardiaca día anterior": gv(S, "cardiac_drift_worst", p),
                "Sueño (min)": gv(SL, "polar_sleep_duration_min", d), "Eficiencia sueño (%)": gv(SL, "polar_efficiency_pct", d),
                "Interrupciones largas": gv(SL, "polar_interruptions_long", d),
                "Fatiga declarada": W.well_fatigue_label.get(d, ""), "Estrés declarado": W.well_stress_label.get(d, ""),
                "Dolor muscular declarado": W.well_soreness_label.get(d, ""), "Ánimo declarado": W.well_mood_label.get(d, ""),
                "Comentario": str(W.well_comment_raw.get(d, "") or "")[:140],
                "Bienestar disponible": "si" if str(W.wellness_subjective_available.get(d, "")).strip().lower() == "true" else "NO"}

    # --- hoja 1: 29 recuperados ---
    rec = list(I.index[I.Calidad_NL_actual.ne(I.Calidad_NL_sin_mismatch)])
    r1 = []
    for d in rec:
        g0, g1 = I.gate_final_NL_actual[d], I.gate_final_NL_sin_mismatch[d]
        r1.append({"Fecha": d, "RMSSD (ms)": round(float(rm[d]), 2), "FC (lpm)": round(float(hr[d]), 2),
                   "Flags del CORE": I.Flags[d],
                   "Calidad NL": I.Calidad_NL_actual[d], "Calidad sin MISMATCH": I.Calidad_NL_sin_mismatch[d],
                   "Semáforo NL": g0, "Semáforo sin MISMATCH": g1, "Su propio color cambia": "SI" if g0 != g1 else "",
                   **{k: D[k].get(d) for k in ("artefactos_pct", "racha_offline_max_tramo", "hueco_max_tramo_s",
                                               "n_validos_tramo", "n_pares_cola", "n_delta_en_cola",
                                               "Defecto técnico", "Motivos", "desv. vs mediana local 7d (ln)") if k in D.columns},
                   **indep(d)})
    T1 = pd.DataFrame(r1)

    # --- hoja 2: 30 cambios de color por quitar MISMATCH ---
    r2 = []
    for d in idx:
        g0, g1 = I.gate_final_NL_actual[d], I.gate_final_NL_sin_mismatch[d]
        if g0 == g1: continue
        t0, t1 = roll3("NL_actual", d), roll3("NL_sin_mismatch", d)
        nuevos = [x for x in t1 if x not in t0]
        r2.append({"Fecha": d, "Semáforo NL": g0, "Semáforo sin MISMATCH": g1,
                   "Razón NL": I.gate_razon_base60_NL_actual[d], "Razón sin MISMATCH": I.gate_razon_base60_NL_sin_mismatch[d],
                   "Vía": "su propia Calidad" if I.Calidad_NL_actual[d] != I.Calidad_NL_sin_mismatch[d] else "trío o referencias",
                   "Trío NL": ", ".join(t0), "Trío sin MISMATCH": ", ".join(t1),
                   "Entra día recuperado en el trío": ", ".join(x for x in nuevos if x in rec),
                   "RMSSD (ms)": round(float(rm[d]), 2), "FC (lpm)": round(float(hr[d]), 2),
                   "ln usado NL": round(float(num("lnRMSSD_used_NL_actual")[d]), 4),
                   "ln usado sin MISMATCH": round(float(num("lnRMSSD_used_NL_sin_mismatch")[d]), 4),
                   "base60 NL": round(float(num("ln_base60_NL_actual")[d]), 4),
                   "base60 sin MISMATCH": round(float(num("ln_base60_NL_sin_mismatch")[d]), 4),
                   **indep(d)})
    T2 = pd.DataFrame(r2)

    # --- hoja 3: los 75 dias ROJO con veto ---
    v = bo(I.veto_agudo_NL_actual)
    r3 = []
    for d in idx:
        if not v[d] or I.gate_final_NL_actual[d] != "ROJO": continue
        grp = "rebajado a ÁMBAR" if I.gate_final_NL_ambar[d] == "ÁMBAR" else "se mantiene ROJO"
        tri = roll3("NL_ambar", d)
        pl = float(np.mean([ln[x] for x in tri])); ph = float(np.mean([hr[x] for x in tri]))
        lb, sw = float(num("ln_base60_NL_ambar")[d]), float(num("SWC_ln_NL_ambar")[d])
        hb, sh = float(num("HR_base60_NL_ambar")[d]), float(num("SWC_HR_NL_ambar")[d])
        sig = [I.gate_final_NL_actual[nxt(d, k)] for k in (1, 2, 3) if nxt(d, k)]
        r3.append({"Fecha": d, "Grupo": grp, "RMSSD (ms)": round(float(rm[d]), 2), "FC (lpm)": round(float(hr[d]), 2),
                   "Trío (fechas)": ", ".join(tri), "ln trío": round(pl, 4), "FC trío": round(ph, 2),
                   "d_ln trío": round(pl - lb, 4), "umbral ln": round(-sw, 4), "trío RMSSD bajo": "SI" if pl - lb < -sw else "no",
                   "d_FC trío": round(ph - hb, 2), "umbral FC": round(sh, 2), "trío FC alta": "SI" if ph - hb > sh else "no",
                   "Veto en la medición anterior": "SI" if prev_med(d) and bo(I.veto_agudo_NL_actual)[prev_med(d)] else "",
                   "Semáforo 3 días siguientes": " ".join(sig), "ROJO en los 3 siguientes": sum(1 for x in sig if x == "ROJO"),
                   **indep(d)})
    T3 = pd.DataFrame(r3)

    # --- hoja 4: interaccion 2025-12-18 ---
    d = "2025-12-18"; r4 = []
    for p in ("NL_actual", "NL_sin_mismatch", "NL_ambar", "NL_sin_mismatch_ambar"):
        tri = roll3(p, d); pl = float(np.mean([ln[x] for x in tri])); ph = float(np.mean([hr[x] for x in tri]))
        lb, sw = float(num("ln_base60_" + p)[d]), float(num("SWC_ln_" + p)[d])
        hb, sh = float(num("HR_base60_" + p)[d]), float(num("SWC_HR_" + p)[d])
        r4.append({"Política": p, "Calidad": I["Calidad_" + p][d], "Semáforo": I["gate_final_" + p][d],
                   "Razón": I["gate_razon_base60_" + p][d], "Veto": I["veto_agudo_" + p][d],
                   "Trío": ", ".join(tri), "ln trío": round(pl, 4), "FC trío": round(ph, 2),
                   "base60 ln": round(lb, 4), "SWC_ln": round(sw, 4), "d_ln trío": round(pl - lb, 4),
                   "trío RMSSD bajo": "SI" if pl - lb < -sw else "no",
                   "base60 FC": round(hb, 2), "SWC_HR": round(sh, 2), "d_FC trío": round(ph - hb, 2),
                   "trío FC alta": "SI" if ph - hb > sh else "no",
                   "gate del trío": "ROJO" if (pl - lb < -sw and ph - hb > sh) else "no ROJO"})
    T4 = pd.DataFrame(r4)

    leeme = pd.DataFrame([
        {"": "Qué es", " ": "Evidencia por día para dos propuestas evaluadas por separado: quitar STAB_LAST2_MISMATCH de Calidad, y que el veto agudo emita ÁMBAR cuando el gate del trío no sería ROJO. Base: HG-03 + 90 s + corte 375 s."},
        {"": "Protocolo", " ": f"Criterios de evidencia favorable, desfavorable e insuficiente fijados ANTES de ver resultados en research/reports/hg04_protocolo_mismatch_veto_2026-10-25.md (SHA-256 {sha(PROT)[:16]}…)."},
        {"": "Hoja 29 recuperados", " ": "Los 29 días que pasan de FLAG a OK al quitar MISMATCH, con diagnóstico técnico de su RR según los criterios §5 del protocolo, y con la información independiente del día."},
        {"": "Hoja 30 cambios color", " ": "Los 30 días cuyo semáforo cambia al quitar MISMATCH, con la vía (su propia Calidad o trío/referencias) y qué día recuperado entra en su trío."},
        {"": "Hoja 75 veto", " ": "Todos los días ROJO con veto: 30 que la regla ámbar rebaja y 45 que mantiene, con el gate del trío reconstruido y la información independiente."},
        {"": "Independencia", " ": "Carga, RPE, sueño y bienestar no dependen del semáforo. El RMSSD del día siguiente y el estado del modelo SSM sí comparten método con el HRV: se muestran como descripción, no como criterio."},
        {"": "Ausencias", " ": "Las celdas vacías son datos que no existen, no ausencia de hallazgo. El bienestar subjetivo solo existe entre 2026-02-13 y 2026-07-27."},
        {"": "Límite", " ": "La acción histórica fue una sola. Esta revisión retrospectiva no muestra qué habría ocurrido siguiendo otra recomendación."},
    ])
    OUT.mkdir(parents=True, exist_ok=True)
    xl = OUT / "evidencia_por_dia.xlsx"
    with pd.ExcelWriter(xl, engine="openpyxl") as w:
        leeme.to_excel(w, sheet_name="Leeme", index=False)
        T1.to_excel(w, sheet_name="29 recuperados", index=False)
        T2.to_excel(w, sheet_name="30 cambios de color", index=False)
        T3.to_excel(w, sheet_name="75 dias con veto", index=False)
        T4.to_excel(w, sheet_name="Interaccion 2025-12-18", index=False)
    from openpyxl import load_workbook
    from openpyxl.styles import PatternFill, Font, Alignment
    from openpyxl.formatting.rule import FormulaRule
    from openpyxl.utils import get_column_letter
    wb = load_workbook(xl); colors = {"ROJO": "F4CCCC", "ÁMBAR": "FCE5CD", "VERDE": "D9EAD3", "NO": "EFEFEF"}
    for ws in wb.worksheets:
        for c in ws[1]: c.font = Font(bold=True); c.alignment = Alignment(wrap_text=True, vertical="center")
        ws.row_dimensions[1].height = 42
        for col in ws.columns:
            L = max(len(str(c.value)) if c.value is not None else 0 for c in col)
            ws.column_dimensions[get_column_letter(col[0].column)].width = min(max(10, L + 2), 40)
        if ws.title != "Leeme": ws.freeze_panes = "B2"; ws.auto_filter.ref = ws.dimensions
        h = {c.value: c.column for c in ws[1]}
        for nm, ci in h.items():
            L = get_column_letter(ci)
            if "Semáforo" in str(nm) or str(nm) == "Semáforo":
                for g, rgb in colors.items():
                    ws.conditional_formatting.add(f"{L}2:{L}{ws.max_row}", FormulaRule(formula=[f'${L}2="{g}"'], fill=PatternFill("solid", fgColor=rgb)))
            if nm in ("Defecto técnico", "Su propio color cambia"):
                ws.conditional_formatting.add(f"{L}2:{L}{ws.max_row}", FormulaRule(formula=[f'${L}2="SI"'], fill=PatternFill("solid", fgColor="FFF2CC")))
    wb["Leeme"].column_dimensions["B"].width = 115
    wb.save(xl)
    agg = {"fecha": "2026-10-25", "protocolo_sha256": sha(PROT),
           "entradas_sha256": {str(p.relative_to(ROOT)): sha(p) for p in
                               [INC, OUT / "recuperados_29_diagnostico.csv",
                                ROOT / "data/ENDURANCE_HRV_sessions_day.csv", ROOT / "data/ENDURANCE_HRV_sleep.csv",
                                ROOT / "data/ENDURANCE_HRV_wellness_subjective.csv"]},
           "n": {"recuperados": len(T1), "cambios_color_mismatch": len(T2), "dias_veto_rojo": len(T3),
                 "rebajados": int((T3.Grupo == "rebajado a ÁMBAR").sum()), "mantenidos": int((T3.Grupo == "se mantiene ROJO").sum())},
           "cobertura_independiente": {
               "recuperados_con_bienestar": int((T1["Bienestar disponible"] == "si").sum()),
               "cambios_color_con_bienestar": int((T2["Bienestar disponible"] == "si").sum()),
               "veto_con_bienestar": int((T3["Bienestar disponible"] == "si").sum()),
               "veto_con_carga_dia_anterior": int(T3["Carga día anterior"].notna().sum())}}
    RES.write_text(json.dumps(agg, indent=1, ensure_ascii=False))
    print(json.dumps(agg, indent=1, ensure_ascii=False)); print("escrito", xl)
    return T1, T2, T3, T4


if __name__ == "__main__":
    main()
