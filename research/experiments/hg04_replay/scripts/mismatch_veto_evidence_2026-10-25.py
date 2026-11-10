"""HG-04: evidencia para las dos propuestas (quitar STAB_LAST2_MISMATCH / veto ambar). 2026-10-25.

Exploratorio. NO recalcula CORE ni repite el replay de RR: lee los RR solo para diagnostico tecnico
(rachas offline, huecos, recuentos) y lee los resultados ya calculados de las cuatro politicas.
Criterios de defecto tecnico fijados de antemano en research/reports/hg04_protocolo_mismatch_veto_2026-10-25.md §5.

Base: HG-03 + inicio 90 s + corte 375 s. Tramo [90, dur-15], cola [dur-135, dur-15].
Salidas: out/hg04_evidencia_mismatch_veto_2026-10-25/ y results/mismatch_veto_evidence_2026-10-25.json
"""
from __future__ import annotations
import csv, glob, hashlib, json, math, os, re
from pathlib import Path
import numpy as np, pandas as pd

ROOT = Path(__file__).resolve().parents[4]
WORK = Path(os.environ.get("HG04_REPLAY_WORK", Path.home() / "hg04_replay_work")) / "rr_src"
INC = ROOT / "out/hg04_calidad_semaforo_incremental_2026-10-23/comparacion_incremental.csv"
OUT = ROOT / "out/hg04_evidencia_mismatch_veto_2026-10-25"
RES = ROOT / "research/experiments/hg04_replay/results/mismatch_veto_evidence_2026-10-25.json"
CUT, TRIM, START, TAIL = 375.0, 15.0, 90.0, 120.0
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
bo = lambda s: s.astype(str).str.strip().str.lower().isin(["true", "1", "1.0"])


def tonum(x):
    try: return float(x)
    except (TypeError, ValueError): return 1.0 if str(x).strip().lower() == "true" else 0.0


def rr_files():
    out = {}
    for f in glob.glob(str(WORK / "*")):
        m = re.search(r"(\d{4}-\d{2}-\d{2})", f)
        if m: out[m.group(1)] = f
    return out


def diagnose(path):
    """Diagnostico tecnico del registro truncado a 375 s. No recalcula metricas del CORE."""
    rr, off = [], []
    for r in csv.DictReader(open(path, newline="")):
        try: v = float(r["duration"])
        except (TypeError, ValueError): continue
        if math.isnan(v): continue
        rr.append(v); off.append(tonum(r["offline"]) != 0)
    rr = np.array(rr); off = np.array(off, bool)
    k = np.cumsum(rr) / 1000.0 <= CUT
    rr, off = rr[k], off[k]
    t = np.cumsum(rr) / 1000.0
    te = float(t[-1] - TRIM)
    oor = (~off) & ((rr < 300) | (rr > 2000))
    base = (~off) & (~oor)
    rb, tb = rr[base], t[base]
    keep = np.ones(rb.size, bool)
    if rb.size > 1: keep[1:] = ~(np.abs(np.diff(rb)) / rb[:-1] > 0.20)
    rc, tc = rb[keep], tb[keep]
    e = tc <= te
    rc, tc = rc[e], tc[e]
    tramo = tc >= START
    cola = (tc >= te - TAIL) & (tc <= te)
    # rachas offline dentro del tramo
    in_tr = (t >= START) & (t <= te)
    o = off[in_tr].astype(int)
    run = mx = 0
    for x in o:
        run = run + 1 if x else 0; mx = max(mx, run)
    # huecos dentro del tramo
    tt = tc[tramo]
    gap = float(np.max(np.diff(tt))) if tt.size > 1 else np.nan
    # latidos retirados por delta dentro de la cola
    tdel = tb[1:][~keep[1:]] if rb.size > 1 else np.array([])
    del_cola = int(np.sum((tdel >= te - TAIL) & (tdel <= te)))
    return {"dur_375": round(float(t[-1]), 1), "t_end_eff": round(te, 1),
            "artefactos_pct": round(100.0 * (int(off.sum()) + int(oor.sum()) + int((~keep).sum())) / max(rr.size, 1), 2),
            "n_offline": int(off.sum()), "n_fuera_rango": int(oor.sum()), "n_delta": int((~keep).sum()),
            "racha_offline_max_tramo": int(mx), "hueco_max_tramo_s": None if np.isnan(gap) else round(gap, 2),
            "n_validos_tramo": int(tramo.sum()), "n_pares_cola": max(int(cola.sum()) - 1, 0),
            "n_delta_en_cola": del_cola}


def defecto(d):
    """Criterios §5 del protocolo, fijados antes de ver resultados."""
    m = []
    if d["artefactos_pct"] > 10.0: m.append("artefactos>10%")
    if d["racha_offline_max_tramo"] >= 3: m.append("racha offline>=3")
    if d["hueco_max_tramo_s"] is not None and d["hueco_max_tramo_s"] > 5.0: m.append("hueco>5s")
    if d["n_validos_tramo"] < 200: m.append("<200 latidos en tramo")
    if d["n_pares_cola"] < 60: m.append("<60 pares en cola")
    if d["n_delta_en_cola"] >= 3: m.append(">=3 retirados por delta en cola")
    return m


def main():
    I = pd.read_csv(INC, encoding="utf-8-sig").set_index("Fecha")
    num = lambda c: pd.to_numeric(I[c], errors="coerce")
    rm, hr = num("RMSSD_stable"), num("HR_stable")
    ln = np.log(rm.where(rm > 0))
    files = rr_files()
    rec = list(I.index[I.Calidad_NL_actual.ne(I.Calidad_NL_sin_mismatch)])
    OUT.mkdir(parents=True, exist_ok=True)
    loc = ln.rolling(7, center=True, min_periods=4).median()
    rows = []
    for d in rec:
        if d not in files:
            rows.append({"Fecha": d, "RR disponible": "NO"}); continue
        g = diagnose(files[d]); m = defecto(g)
        rows.append({"Fecha": d, "RR disponible": "si",
                     "RMSSD (ms)": round(float(rm[d]), 2), "FC (lpm)": round(float(hr[d]), 2),
                     "tail_mismatch (%)": round(float(num("Artifact_pct")[d]), 2) if False else None,
                     "Flags": I.Flags[d], **g,
                     "Defecto técnico": "SI" if m else "no", "Motivos": "|".join(m),
                     "desv. vs mediana local 7d (ln)": round(float(ln[d] - loc[d]), 4) if np.isfinite(loc[d]) else None})
    T = pd.DataFrame(rows)
    out = {"fecha": "2026-10-25", "protocolo": "research/reports/hg04_protocolo_mismatch_veto_2026-10-25.md",
           "protocolo_sha256": sha(ROOT / "research/reports/hg04_protocolo_mismatch_veto_2026-10-25.md"),
           "entrada_sha256": {str(INC.relative_to(ROOT)): sha(INC)},
           "n_recuperados": len(rec), "con_RR": int((T["RR disponible"] == "si").sum()),
           "sin_defecto_tecnico": int((T.get("Defecto técnico") == "no").sum()),
           "con_defecto_tecnico": int((T.get("Defecto técnico") == "SI").sum()),
           "motivos": {}}
    mot = T.get("Motivos")
    if mot is not None:
        from collections import Counter
        c = Counter(x for s in mot.dropna() for x in str(s).split("|") if x)
        out["motivos"] = dict(c)
    T.to_csv(OUT / "recuperados_29_diagnostico.csv", index=False, encoding="utf-8-sig")
    RES.write_text(json.dumps(out, indent=1, ensure_ascii=False))
    print(json.dumps(out, indent=1, ensure_ascii=False))
    cols = ["Fecha", "RMSSD (ms)", "FC (lpm)", "artefactos_pct", "racha_offline_max_tramo", "hueco_max_tramo_s",
            "n_validos_tramo", "n_pares_cola", "n_delta_en_cola", "Defecto técnico", "Motivos",
            "desv. vs mediana local 7d (ln)"]
    print("\n" + T[[c for c in cols if c in T.columns]].to_string(index=False))
    return T, out


if __name__ == "__main__":
    main()
