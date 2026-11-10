"""HG-09B §4.4-§7.1: corrección de errores confirmados del conversor y efecto en lnRMSSD.

Entrada: out/hg09b_casos_2026-10-27/veredicto_desenmascarado.csv (veredicto ciego sellado y luego
desenmascarado) y mapa_desenmascarar.json. Corrige SOLO errores del conversor confirmados
(EXTRA -> fusiona los dos intervalos; FALTA -> divide el intervalo en el instante del latido
confirmado). Sensibilidad: INDETERMINADO atribuido al conversor -> desplaza su marca al instante
del detector independiente (cota). Recalcula con el motor de la geometría candidata (mismo
filtro, misma semántica de pares). Salidas: results/hg09b_efecto_2026-10-27.json (agregados)
y out/hg09b_casos_2026-10-27/efecto_por_dia.csv.
"""
from __future__ import annotations

import hashlib
import importlib.util
import io
import json
import math
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import hg09b_motor as motor  # noqa: E402

ROOT = motor.ROOT
OUTC = ROOT / "out/hg09b_casos_2026-10-27"
VER = OUTC / "veredicto_ciego.json"
VD = OUTC / "veredicto_desenmascarado.csv"
MAPA = OUTC / "mapa_desenmascarar.json"
SEL = HERE.parent / "results/hg09b_seleccion_2026-10-27.json"
CASOS_RES = HERE.parent / "results/hg09b_casos_resumen.json"
A0 = ROOT / "out/hg04_copias_paralelas_2026-10-22/H3S90T375/ENDURANCE_HRV_master_CORE.csv"
HG05 = ROOT / "research/experiments/hg05/scripts/hg05_ventana_vs_global_375.py"
RES = HERE.parent / "results/hg09b_efecto_2026-10-27.json"
TMP = Path(os.path.expanduser("~")) / "hg09b_tmp/efecto"
SWC_MED = 0.1148449437374518  # mediana SWC_ln era ECG en A0 (protocolo §5)
REL = 0.5 * SWC_MED
sha = lambda b: hashlib.sha256(b).hexdigest()


def wilson(k, n, z=1.96):
    if n == 0:
        return (float("nan"), float("nan"))
    p = k / n; d = 1 + z * z / n; c = p + z * z / (2 * n); h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return ((c - h) / d, (c + h) / d)


def newcombe(k1, n1, k2, n2):
    p1, p2 = k1 / n1, k2 / n2
    l1, u1 = wilson(k1, n1); l2, u2 = wilson(k2, n2)
    d = p1 - p2
    return (d - math.sqrt((p1 - l1) ** 2 + (u2 - p2) ** 2), d + math.sqrt((u1 - p1) ** 2 + (p2 - l2) ** 2))


def metrics(df: pd.DataFrame, name: str) -> dict:
    TMP.mkdir(parents=True, exist_ok=True)
    p = TMP / f"ENDURANCE_{name}_RR.CSV"
    df.to_csv(p, index=False)
    r = motor.day_metrics(p)
    return {k: r.get(k) for k in ("RMSSD_stable", "lnRMSSD", "tail_mismatch_pct", "HR_stable", "Calidad", "Stability_Subtype", "Artifact_pct")}


def correct(rr: pd.DataFrame, ops: list[dict], clear_offline: bool = False) -> pd.DataFrame:
    """ops sobre el eje del conversor (t final de cada RR, s). Devuelve RR corregido."""
    dur = pd.to_numeric(rr.duration, errors="coerce").to_numpy(float).copy()
    off = rr.offline.astype(str).str.lower().isin(["1", "true", "1.0"]).to_numpy().astype(int)
    keep = ~np.isnan(dur)
    dur, off = dur[keep], off[keep]
    for op in sorted(ops, key=lambda o: -o["t"]):  # de atrás hacia delante: índices estables
        t_end = np.cumsum(dur) / 1000.0
        if op["tipo"] == "EXTRA":
            i = int(np.argmin(np.abs(t_end - op["t"])))
            assert abs(t_end[i] - op["t"]) < 0.005 and i + 1 < dur.size
            dur[i] = dur[i] + dur[i + 1]; off[i] = 0 if clear_offline else max(off[i], off[i + 1])
            dur = np.delete(dur, i + 1); off = np.delete(off, i + 1)
        elif op["tipo"] == "FALTA":
            i = int(np.searchsorted(t_end, op["t"]))
            start = t_end[i] - dur[i] / 1000.0
            a = (op["t"] - start) * 1000.0
            assert 0 < a < dur[i]
            dur = np.insert(dur, i, a); dur[i + 1] = dur[i + 1] - a
            off = np.insert(off, i, off[i])
            if clear_offline:
                off[i] = 0; off[i + 1] = 0
        elif op["tipo"] == "DESPLAZA":
            i = int(np.argmin(np.abs(t_end - op["t"])))
            delta = (op["t_nuevo"] - op["t"]) * 1000.0
            dur[i] += delta
            if i + 1 < dur.size:
                dur[i + 1] -= delta
    return pd.DataFrame({"duration": np.round(dur, 6), "offline": off})


def main():
    ver_sha = sha(VER.read_bytes())
    vd = pd.read_csv(VD)
    mapa = json.loads(MAPA.read_text(encoding="utf-8"))
    sel = json.loads(SEL.read_text(encoding="utf-8"))
    casos_res = json.loads(CASOS_RES.read_text(encoding="utf-8"))
    a0 = pd.read_csv(A0).set_index("Fecha")
    core = pd.read_csv(ROOT / "data/ENDURANCE_HRV_master_CORE.csv")
    spec = importlib.util.spec_from_file_location("h5", HG05); h5 = importlib.util.module_from_spec(spec); spec.loader.exec_module(h5)
    rows = []
    for fecha, g in casos_res["grabaciones"].items():
        if g["estado"] != "ok":
            continue
        raw = h5.load_rr_bytes(core[core.Fecha == fecha])[fecha]
        rr = pd.read_csv(io.BytesIO(raw))
        sub = vd[vd.fecha == fecha]
        ops, ops_sens, seen = [], [], set()
        for _, r in sub.iterrows():
            if r.categoria in ("EXTRA", "FALTA") and r.detector_erroneo == "conv":
                t = float(mapa[r.caso].get("t_indep", np.nan)) - float(casos_res_shift(casos_res, fecha)) if r.categoria == "FALTA" else float(r.t_core_s)
                key = (r.categoria, round(t, 2))
                if key not in seen:
                    seen.add(key); ops.append({"tipo": r.categoria, "t": t})
            if r.categoria == "INDETERMINADO" and r.detector_erroneo == "conv":
                ops_sens.append(r)
        base = metrics(rr, f"{fecha}_orig")
        # paridad con A0 (protocolo §4.1.3)
        if fecha in a0.index:
            assert abs(base["RMSSD_stable"] - a0.at[fecha, "RMSSD_stable"]) < 1e-9, fecha
            assert abs(base["tail_mismatch_pct"] - a0.at[fecha, "tail_mismatch_pct"]) < 1e-9, fecha
        corr = metrics(correct(rr, ops), f"{fecha}_corr") if ops else base
        rows.append({"fecha": fecha, "rol": g["rol"], "caso_ref": g["caso_ref"], "n_err_confirmados": len(ops),
                     "tipos": "|".join(sorted({o["tipo"] for o in ops})), "n_indet_conv": len(ops_sens),
                     "RMSSD_orig": base["RMSSD_stable"], "RMSSD_corr": corr["RMSSD_stable"],
                     "dln": corr["lnRMSSD"] - base["lnRMSSD"], "tail_orig": base["tail_mismatch_pct"],
                     "tail_corr": corr["tail_mismatch_pct"], "Calidad_orig": base["Calidad"], "Calidad_corr": corr["Calidad"],
                     "subtipo_orig": base["Stability_Subtype"], "subtipo_corr": corr["Stability_Subtype"],
                     "n_discrepancias": g["n_discrepancias"], "n_concordantes": g["n_concordantes"], "n_intervalos": g["n_intervalos"],
                     "_ops": ops, "_sens": [{"caso": r.caso, "t": float(r.t_core_s)} for r in ops_sens]})
    df = pd.DataFrame(rows)
    df["relevante"] = df.dln.abs() >= REL
    # sensibilidad: marcas del conversor indeterminadas por temporización -> instante del detector independiente
    sens = {}
    for _, r in df[df.n_indet_conv > 0].iterrows():
        raw = h5.load_rr_bytes(core[core.Fecha == r.fecha])[r.fecha]
        rr = pd.read_csv(io.BytesIO(raw))
        extra = []
        for s in r._sens:
            ti = nearest_indep(mapa, vd, r.fecha, s["t"], casos_res)
            if ti is not None:
                extra.append({"tipo": "DESPLAZA", "t": s["t"], "t_nuevo": ti})
        m = metrics(correct(rr, r._ops + extra), f"{r.fecha}_sens")
        sens[r.fecha] = {"dln_con_desplazamiento": m["lnRMSSD"] - (np.log(r.RMSSD_orig)), "tail": m["tail_mismatch_pct"], "n": len(extra)}
    # sensibilidad: intervalos reconstruidos por la corrección pasan a offline=0 (el conversor los había marcado offline)
    sens_off = {}
    for _, r in df[df.n_err_confirmados > 0].iterrows():
        raw = h5.load_rr_bytes(core[core.Fecha == r.fecha])[r.fecha]
        m = metrics(correct(pd.read_csv(io.BytesIO(raw)), r._ops, clear_offline=True), f"{r.fecha}_offl")
        sens_off[r.fecha] = {"dln": m["lnRMSSD"] - float(np.log(r.RMSSD_orig)), "tail": m["tail_mismatch_pct"], "subtipo": m["Stability_Subtype"]}
    M = df[df.rol == "M"]; C = df[df.rol == "C"]
    kM, nM, kC, nC = int(M.relevante.sum()), len(M), int(C.relevante.sum()), len(C)
    lo, hi = newcombe(kM, nM, kC, nC)
    maxM = float(M.dln.abs().max())
    if lo > 0 and (kM / nM - kC / nC) >= 0.15:
        dec = "FAVORABLE A MANTENER LA EXCLUSIÓN"
    elif hi <= 0.15 and maxM < SWC_MED:
        dec = "FAVORABLE A INCLUIR"
    else:
        dec = "EVIDENCIA INSUFICIENTE"
    # concordantes: cota de errores compartidos
    conc = vd[vd.tipo == "concordante"]
    kconc = int((conc.categoria != "CORRECTO").sum())
    out = {"fecha": "2026-10-27", "veredicto_sha256": ver_sha, "motor": motor.fingerprints(),
           "umbral_relevante_dln": REL, "swc_mediana_ecg": SWC_MED,
           "M": {"n": nM, "con_error_relevante": kM, "con_error_confirmado": int((M.n_err_confirmados > 0).sum()),
                 "max_abs_dln": maxM},
           "C": {"n": nC, "con_error_relevante": kC, "con_error_confirmado": int((C.n_err_confirmados > 0).sum()),
                 "max_abs_dln": float(C.dln.abs().max())},
           "M2": {"n": int((df.rol == "M2").sum()), "con_error_confirmado": int((df[df.rol == "M2"].n_err_confirmados > 0).sum())},
           "diferencia_pM_menos_pC": kM / nM - kC / nC, "IC95_newcombe": [lo, hi], "decision_7_1": dec,
           "indeterminados_M_pct": 100.0 * int((M.n_indet_conv > 0).sum()) / nM,
           "concordantes": {"revisados": int(len(conc)), "no_correctos": kconc,
                            "IC95_wilson_tasa_error_compartido": list(wilson(kconc, len(conc)))},
           "intervalos_aceptados_sospechosos": {"revisados": int((vd.tipo == "intervalo_aceptado").sum()),
                                               "no_correctos": int(((vd.tipo == "intervalo_aceptado") & (vd.categoria != "CORRECTO")).sum())},
           "categorias_por_rol_tipo": {f"{a}|{b}|{c}": int(n) for (a, b, c), n in vd.groupby(["rol", "tipo", "categoria"]).size().items()},
           "sensibilidad_temporizacion": sens, "sensibilidad_offline_limpio": sens_off,
           "por_dia": df.drop(columns=["_ops", "_sens"]).round(5).to_dict(orient="records")}
    RES.write_text(json.dumps(out, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    df.drop(columns=["_ops", "_sens"]).to_csv(OUTC / "efecto_por_dia.csv", index=False, encoding="utf-8-sig")
    print(json.dumps({k: out[k] for k in ("M", "C", "M2", "diferencia_pM_menos_pC", "IC95_newcombe", "decision_7_1",
                                          "concordantes", "intervalos_aceptados_sospechosos", "sensibilidad_temporizacion", "sensibilidad_offline_limpio")},
                     ensure_ascii=False, indent=1, default=str))
    print(df[["fecha", "rol", "n_err_confirmados", "tipos", "RMSSD_orig", "RMSSD_corr", "dln", "tail_orig", "tail_corr", "subtipo_orig", "subtipo_corr"]].round(4).to_string(index=False))


def casos_res_shift(casos_res, fecha):
    return SHIFTS[fecha]


def nearest_indep(mapa, vd, fecha, t_core, casos_res):
    """Instante del detector independiente más próximo (eje del conversor) entre los casos del mismo día."""
    best = None
    for cid, m in mapa.items():
        if m["fecha"] == fecha and "t_indep" in m:
            tc = m["t_indep"] - SHIFTS[fecha]
            if abs(tc - t_core) < 0.12 and (best is None or abs(tc - t_core) < abs(best - t_core)):
                best = tc
    return best


SHIFTS = {}

if __name__ == "__main__":
    reg = pd.read_csv(OUTC / "registro.csv")
    SHIFTS.update({r.fecha: float(r.desplazamiento_s) for r in reg.itertuples() if r.estado == "ok"})
    main()
