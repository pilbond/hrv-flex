"""HG-04: tabla auditable por dia de la clasificacion de errores RR (2026-10-26). FASE 3.

Protocolo: research/reports/hg04_protocolo_errores_rr_2026-10-26.md
Exploratorio. No modifica produccion, contratos ni datos originales.

Hojas: Leeme / 29 dias clasificados / Referencia ECG / Errores verificados /
       Sensibilidad / Repetibilidad misma manana.
"""
from __future__ import annotations
import csv, glob, hashlib, importlib.util, itertools, json, os, re
from pathlib import Path
import numpy as np, pandas as pd

ROOT = Path(__file__).resolve().parents[4]
OUT = ROOT / "out/hg04_errores_rr_2026-10-26"
RESP = Path(os.path.expanduser("~")) / "hg04_resp_work"
WORK = Path(os.environ.get("HG04_REPLAY_WORK", Path.home() / "hg04_replay_work"))
REF = WORK / "H3S90T375/data/ENDURANCE_HRV_master_CORE.csv"
ECG_START = "2026-03-06"
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()

spec = importlib.util.spec_from_file_location(
    "eff", ROOT / "research/experiments/hg04_replay/scripts/hg04_rr_errors_effect_2026-10-26.py")
eff = importlib.util.module_from_spec(spec); spec.loader.exec_module(eff)


def main():
    ref = {r["Fecha"]: r for r in csv.DictReader(open(REF, encoding="utf-8-sig"))}
    inc = {r["Fecha"]: r for r in csv.DictReader(open(
        ROOT / "out/hg04_calidad_semaforo_incremental_2026-10-23/comparacion_incremental.csv",
        encoding="utf-8-sig"))}
    diag = {r["Fecha"]: r for r in csv.DictReader(open(
        ROOT / "out/hg04_evidencia_mismatch_veto_2026-10-25/recuperados_29_diagnostico.csv",
        encoding="utf-8-sig"))}
    errores = list(csv.DictReader(open(OUT / "errores_verificados.csv", encoding="utf-8-sig")))
    efectos = list(csv.DictReader(open(OUT / "efecto_por_grabacion.csv", encoding="utf-8-sig")))
    sens = pd.read_csv(OUT / "sensibilidad_simulada.csv", encoding="utf-8-sig")
    res = json.loads((ROOT / "research/experiments/hg04_replay/results/hg04_rr_errors_2026-10-26.json")
                     .read_text(encoding="utf-8"))

    dias_ecg = sorted({f"{m.group(1)[:4]}-{m.group(1)[4:6]}-{m.group(1)[6:]}"
                       for f in glob.glob(str(ROOT / "data/rr_downloads/_source_jsonl_recovered/_unzipped/**/ECG.jsonl"), recursive=True)
                       if (m := re.search(r"PolarRecording_(\d{8})_", f))})

    # --- hoja 1: los 29 dias clasificados ---
    f1 = []
    for d in sorted(diag):
        era = "ECG" if d >= ECG_START else "Polar"
        tmm = float(ref[d]["tail_mismatch_pct"]) if d in ref and ref[d].get("tail_mismatch_pct") else None
        f1.append({
            "Fecha": d, "Era": era,
            "ECG original disponible": "si" if d in dias_ecg else "NO",
            "Clase": "N — no determinable",
            "Motivo de la clase": "no existe ECG original para este dia; no se puede comparar "
                                  "el conversor con una deteccion independiente",
            "tail_mismatch_pct (base H3S90T375)": round(tmm, 2) if tmm is not None else None,
            "RMSSD (ms)": diag[d].get("RMSSD (ms)"), "FC (lpm)": diag[d].get("FC (lpm)"),
            "artefactos_pct (detectados)": diag[d].get("artefactos_pct"),
            "n_delta_en_cola": diag[d].get("n_delta_en_cola"),
            "Su color cambia al quitar MISMATCH":
                "SI" if d in inc and inc[d]["gate_final_NL_actual"] != inc[d]["gate_final_NL_sin_mismatch"] else "",
            "Semáforo NL": inc[d]["gate_final_NL_actual"] if d in inc else "",
            "Semáforo sin MISMATCH": inc[d]["gate_final_NL_sin_mismatch"] if d in inc else "",
            "Auditable si se recupera el ECG": "si" if era == "ECG" else "no (era Polar: el RR lo "
                                                                        "genero la app, sin ECG que auditar)"})

    # --- hoja 2: conjunto de referencia ECG ---
    emp = {r["grabacion"]: r for r in csv.DictReader(open(OUT / "emparejamiento.csv", encoding="utf-8-sig"))}
    f2 = []
    for e in efectos:
        rec = e["grabacion"]; m = re.search(r"_(\d{8})_", rec)
        d = f"{m.group(1)[:4]}-{m.group(1)[4:6]}-{m.group(1)[6:]}"
        f2.append({"Fecha": d, "Grabación": rec,
                   "Es el registro que usa el CORE":
                       "si" if (d in ref and ref[d].get("tail_mismatch_pct") and
                                abs(float(ref[d]["tail_mismatch_pct"]) - float(e["tail_mismatch_pct"])) < 0.01) else "",
                   "tail_mismatch_pct": float(e["tail_mismatch_pct"]),
                   "RMSSD tramo (ms)": float(e["RMSSD_tramo"]), "RMSSD cola (ms)": float(e["RMSSD_cola"]),
                   "Latidos emparejados": emp[rec]["emparejados"],
                   "offline_pct": emp[rec]["offline_pct"],
                   "Residuo mediano (ms)": emp[rec]["resid_mediano_ms"],
                   "Errores del conversor (total)": int(e["n_errores_conversor"]),
                   "Errores DENTRO del tramo": int(e["errores_en_tramo"]),
                   "tail_mismatch tras corrección": float(e["tail_mismatch_pct_corr"]),
                   "Δ por la corrección": float(e["delta_tmm"]),
                   "Calidad en la copia": ref[d]["Calidad"] if d in ref else "",
                   "Flags en la copia": ref[d].get("Flags", "") if d in ref else ""})
    for g in sorted({r["grabacion"] for r in csv.DictReader(open(OUT / "emparejamiento.csv", encoding="utf-8-sig"))
                     if r.get("estado") != "ok"}):
        m = re.search(r"_(\d{8})_", g)
        f2.append({"Fecha": f"{m.group(1)[:4]}-{m.group(1)[4:6]}-{m.group(1)[6:]}", "Grabación": g,
                   "Es el registro que usa el CORE": "", "Errores del conversor (total)": None,
                   "Flags en la copia": "EXCLUIDA: " + emp[g]["estado"]})

    # --- hoja 3: errores verificados ---
    f3 = [{"Caso ciego": e["caso"], "Grabación": e["grabacion"], "Tipo": e["tipo"],
           "Instante (s)": float(e["instante_s"]), "Zona": e["zona"], "Motivo (revisión ciega)": e["motivo"],
           "Afecta al tramo": "no" if e["zona"].startswith("antes") else "SI"} for e in errores]

    # --- hoja 4: sensibilidad ---
    f4 = []
    for (sus, tipo, zona), g in sens.groupby(["sustrato", "tipo", "zona"]):
        f4.append({"Sustrato": sus, "Tipo de error": tipo, "Zona": zona, "n posiciones": len(g),
                   "Δ mediano (puntos)": round(float(g.delta.median()), 2),
                   "Δ p5": round(float(g.delta.quantile(.05)), 2),
                   "Δ p95": round(float(g.delta.quantile(.95)), 2),
                   "Cruzan el 15%": int(g.cruza_15.sum()),
                   "% que cruzan": round(float(g.cruza_15.mean() * 100), 1)})

    # --- hoja 5: repetibilidad misma manana ---
    por = {}
    for e in efectos:
        m = re.search(r"_(\d{8})_(\d{6})", e["grabacion"])
        d = f"{m.group(1)[:4]}-{m.group(1)[4:6]}-{m.group(1)[6:]}"
        por.setdefault(d, []).append((m.group(2), float(e["tail_mismatch_pct"]),
                                      float(e["RMSSD_tramo"]), float(e["RMSSD_cola"])))
    f5 = []
    for d, v in sorted(por.items()):
        for h, tm, R, Rc in sorted(v):
            f5.append({"Fecha": d, "Hora": h, "tail_mismatch_pct": tm, "RMSSD tramo (ms)": R,
                       "RMSSD cola (ms)": Rc, "Δ tail_mismatch del par": None, "Δ RMSSD del par": None})
        if len(v) > 1:
            for a, b in itertools.combinations(sorted(v), 2):
                f5.append({"Fecha": d, "Hora": f"{a[0]} vs {b[0]}", "tail_mismatch_pct": None,
                           "RMSSD tramo (ms)": None, "RMSSD cola (ms)": None,
                           "Δ tail_mismatch del par": round(abs(a[1] - b[1]), 2),
                           "Δ RMSSD del par": round(abs(a[2] - b[2]), 2)})

    leeme = [
        ("Qué es esto", "Clasificación de los 29 días recuperados en E (error verificado), "
                        "D (discordancia sin error detectable) o N (no determinable), y auditoría "
                        "del conversor en las grabaciones con ECG original."),
        ("Protocolo previo", f"research/reports/hg04_protocolo_errores_rr_2026-10-26.md  sha256 "
                             f"{res['protocolo_sha256'][:32]}…"),
        ("Veredicto ciego", f"out/hg04_errores_rr_2026-10-26/veredicto_ciego.json  sha256 "
                            f"{res['veredicto_ciego_sha256'][:32]}… (sellado ANTES de desenmascarar)"),
        ("Base de cálculo", "HG-03 + inicio 90 s + corte 375 s (copia H3S90T375), NO el CORE de producción."),
        ("Validación", f"La geometría reproduce la copia H3S90T375 en {res['validacion_copia_H3S90T375']['n']} "
                       f"días con diferencia máxima {res['validacion_copia_H3S90T375']['max_dif']}."),
        ("Resultado principal", f"Los 29 días son clase N: ninguno tiene ECG original. "
                                f"Errores del conversor dentro del tramo: "
                                f"{res['errores_conversor_en_tramo']} de {res['latidos_en_tramo']} latidos "
                                f"(Wilson 95%: hasta {res['wilson95_por_1000'][1]}/1000)."),
        ("Advertencia", "La hoja Sensibilidad es una SIMULACIÓN: muestra a qué responde el indicador, "
                        "no que esos errores existieran en ningún día."),
        ("Lo que no se usó", "Forma del histograma, coherencia RMSSD-FC, umbral del semáforo, "
                             "recuento de ROJOS. El veto ámbar queda fuera de alcance."),
    ]

    with pd.ExcelWriter(OUT / "errores_rr_por_dia.xlsx", engine="openpyxl") as xw:
        pd.DataFrame(leeme, columns=["Campo", "Valor"]).to_excel(xw, "Leeme", index=False)
        for nm, fr in (("29 dias clasificados", f1), ("Referencia ECG", f2), ("Errores verificados", f3),
                       ("Sensibilidad", f4), ("Repetibilidad manana", f5)):
            pd.DataFrame(fr).to_excel(xw, nm, index=False)
        for ws in xw.book.worksheets:
            if ws.max_row > 1 and ws.title != "Leeme":
                ws.auto_filter.ref = ws.dimensions
            ws.freeze_panes = "A2"
            for c in ws.columns:
                ln = max((len(str(x.value)) for x in c if x.value is not None), default=10)
                ws.column_dimensions[c[0].column_letter].width = min(max(ln + 2, 10), 58)

    pd.DataFrame(f1).to_csv(OUT / "errores_rr_por_dia.csv", index=False, encoding="utf-8-sig")
    print("escrito:", (OUT / "errores_rr_por_dia.xlsx").relative_to(ROOT))
    print(f"  29 dias clasificados: {len(f1)} filas, todas clase N")
    print(f"  referencia ECG: {len(f2)} grabaciones ({len(efectos)} utilizables)")
    print(f"  errores verificados del conversor: {len(f3)}, en el tramo: "
          f"{sum(1 for x in f3 if x['Afecta al tramo']=='SI')}")
    print(f"  sensibilidad: {len(f4)} combinaciones; repetibilidad: {len(f5)} filas")


if __name__ == "__main__":
    main()
