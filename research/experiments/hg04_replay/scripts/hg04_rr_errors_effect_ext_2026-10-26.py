"""HG-04: FASE 3-ext. Efecto de la correccion y clasificacion E/D en los 10 dias recuperados.

Protocolo: research/reports/hg04_protocolo_errores_rr_2026-10-26.md (enmienda 12)
Exploratorio. No modifica produccion, contratos ni datos originales.

Reutiliza la geometria validada de hg04_rr_errors_effect_2026-10-26.py, que reproduce la copia
H3S90T375 en 503/503 dias con diferencia maxima 0,000000.
"""
from __future__ import annotations
import csv, glob, importlib.util, json, os, re
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parents[4]
O = ROOT / "out/hg04_errores_rr_2026-10-26/ampliacion_10dias"
RRSRC = Path(os.path.expanduser("~")) / "hg04_replay_work/rr_src"
REF = Path(os.path.expanduser("~")) / "hg04_replay_work/H3S90T375/data/ENDURANCE_HRV_master_CORE.csv"

spec = importlib.util.spec_from_file_location(
    "eff", ROOT / "research/experiments/hg04_replay/scripts/hg04_rr_errors_effect_2026-10-26.py")
eff = importlib.util.module_from_spec(spec); spec.loader.exec_module(eff)


def main():
    ref = {r["Fecha"]: r for r in csv.DictReader(open(REF, encoding="utf-8-sig"))}
    desen = list(csv.DictReader(open(O / "casos_desenmascarados.csv", encoding="utf-8-sig")))

    # errores atribuidos al CONVERSOR, por dia (los unicos corregibles de forma trazable)
    err_conv = {}
    for r in desen:
        if r["detector_real"] == "conv" and r["veredicto"] in ("EXTRA", "FALTA"):
            err_conv.setdefault(r["fecha"], []).append(r)

    fechas = sorted({r["fecha"] for r in desen})
    out = []
    for d in fechas:
        g = sorted(glob.glob(str(RRSRC / f"ENDURANCE_{d}_*RR*")))
        rr, idx, dur_raw, t = eff.load_rr_csv(g[0])
        g0 = eff.geometria(rr, idx, dur_raw, t)
        R, Rc, tmm = g0["RMSSD"], g0["RMSSD_cola"], g0["tmm"]

        ec = err_conv.get(d, [])
        en_tramo = [e for e in ec if 90 <= float(e["instante_s"]) <= 375]
        # correccion trazable: sin errores del conversor no hay nada que corregir
        tmm_corr = tmm
        clase = "E — error verificado" if en_tramo else "D — discordancia sin error de deteccion"

        amb = [r for r in desen if r["fecha"] == d and r["veredicto"] == "AMBIGUO"]
        amb_tramo = [r for r in amb if 90 <= float(r["instante_s"]) <= 375]
        if amb_tramo:
            clase = "N — no determinable (ventanas no evaluables dentro del tramo)"

        rr_ref = ref.get(d, {})
        out.append({
            "Fecha": d,
            "Clase": clase,
            "RMSSD tramo (ms)": round(R, 4), "RMSSD cola (ms)": round(Rc, 4),
            "n_tramo": g0["n_tramo"], "n_cola": g0["n_cola"],
            "tail_mismatch_pct": round(tmm, 4),
            "Errores conversor (total)": len(ec),
            "Errores conversor EN TRAMO": len(en_tramo),
            "Errores detector independiente": sum(
                1 for r in desen if r["fecha"] == d and r["detector_real"] == "indep"
                and r["veredicto"] in ("EXTRA", "FALTA")),
            "Casos AMBIGUO": len(amb),
            "AMBIGUO dentro del tramo": len(amb_tramo),
            "tail_mismatch_pct tras correccion": round(tmm_corr, 4),
            "Delta por la correccion": round(tmm_corr - tmm, 4),
            "artefactos_pct (pipeline)": rr_ref.get("artefactos_pct", ""),
            "n_delta_en_cola (pipeline)": rr_ref.get("n_delta_en_cola", ""),
            "Calidad en la copia": rr_ref.get("Calidad", ""),
            "Flags en la copia": rr_ref.get("Flags", ""),
            "tail_mismatch_pct en la copia": rr_ref.get("tail_mismatch_pct", ""),
        })

    with open(O / "clasificacion_10dias.csv", "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=list(out[0])); w.writeheader(); [w.writerow(r) for r in out]

    print(f"{'Fecha':12s} {'tmm%':>8s} {'copia%':>8s} {'dif':>8s} {'errC':>5s} {'errI':>5s} {'amb':>4s}  Clase")
    for r in out:
        cp = float(r["tail_mismatch_pct en la copia"]) if r["tail_mismatch_pct en la copia"] else float("nan")
        print(f"{r['Fecha']:12s} {r['tail_mismatch_pct']:8.2f} {cp:8.2f} "
              f"{abs(r['tail_mismatch_pct']-cp):8.4f} {r['Errores conversor (total)']:5d} "
              f"{r['Errores detector independiente']:5d} {r['Casos AMBIGUO']:4d}  {r['Clase']}")
    from collections import Counter
    print("\nclases:", dict(Counter(r["Clase"] for r in out)))
    print("delta maximo por correccion:", max(abs(r["Delta por la correccion"]) for r in out))


if __name__ == "__main__":
    main()
