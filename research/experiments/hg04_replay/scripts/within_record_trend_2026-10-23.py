"""HG-04: tendencia de lnRMSSD y FC dentro del registro, ruido por bloque y estructura del veto (2026-10-23).

Exploratorio. No modifica CORE/FINAL ni contrato. Solo escribe agregados (sin tabla por fecha).
Entradas:
  - RR originales en $HG04_REPLAY_WORK/rr_src (los mismos que usa run_parallel.py)
  - out/hg04_copias_paralelas_2026-10-22/{C,H3S90,H3S90T375}/ENDURANCE_HRV_master_{CORE,FINAL}.csv
Método (bloques de 30 s disjuntos desde 90 s hasta t_end_eff, HG-03, mismos filtros que build_hrv_core.py):
  pendiente = regresión lineal de ln(RMSSD_bloque) y de FC_bloque frente al centro del bloque, por día;
  ruido = SD residual de esa regresión (por bloque de 30 s). Variantes: registro truncado a 375 s y completo.
  Modelo de contraste para el informe de bloques 60/90/120 s: diferencia último−primero ~ N(-pendiente*distancia, (ruido30*sqrt(30/L))*sqrt(2)).
Salida: results/within_record_trend_2026-10-23.json
"""
from __future__ import annotations
import csv, glob, hashlib, json, math, os, re
from pathlib import Path
import numpy as np, pandas as pd

ROOT = Path(__file__).resolve().parents[4]
WORK = Path(os.environ.get("HG04_REPLAY_WORK", Path.home() / "hg04_replay_work"))
OUT = ROOT / "out" / "hg04_copias_paralelas_2026-10-22"
RES = ROOT / "research/experiments/hg04_replay/results/within_record_trend_2026-10-23.json"
ECG_START = "2026-03-06"

def tonum(x):
    try: return float(x)
    except (TypeError, ValueError): return 1.0 if str(x).strip().lower() == "true" else 0.0  # igual que pandas (bool)

def load_rr(path, cut):
    rr, off = [], []
    with open(path, newline="") as fh:
        for r in csv.DictReader(fh):
            try: v = float(r["duration"])
            except (TypeError, ValueError): continue
            if math.isnan(v): continue
            rr.append(v); off.append(tonum(r["offline"]) != 0)
    rr = np.array(rr); off = np.array(off, bool); idx = np.arange(rr.size)
    if cut:
        k = np.cumsum(rr) / 1000 <= cut; rr, off, idx = rr[k], off[k], idx[k]
    t = np.cumsum(rr) / 1000; te = t[-1] - 15.0
    b = (~off) & (rr >= 300) & (rr <= 2000); rb, tb, ib = rr[b], t[b], idx[b]
    keep = np.ones(rb.size, bool); keep[1:] = ~(np.abs(np.diff(rb)) / rb[:-1] > 0.20)
    rc, tc, ic = rb[keep], tb[keep], ib[keep]; e = tc <= te
    return rc[e], tc[e], ic[e], te

def day_trend(path, cut):
    rc, tc, ic, te = load_rr(path, cut)
    xs, ln, hr = [], [], []
    s = 90.0
    while s + 30 <= te + 1e-9:
        m = (tc >= s) & (tc < s + 30); r = rc[m]; d = np.diff(r)[np.diff(ic[m]) == 1]
        if d.size >= 15:
            xs.append(s + 15); ln.append(math.log(math.sqrt(np.mean(d * d)))); hr.append(60000 / np.mean(r))
        s += 30
    if len(xs) < 6: return None
    x = np.array(xs); y = np.array(ln); p = np.polyfit(x, y, 1)
    half = x < (90 + te) / 2
    s1 = np.polyfit(x[half], y[half], 1)[0] * 60 if half.sum() >= 3 else np.nan
    s2 = np.polyfit(x[~half], y[~half], 1)[0] * 60 if (~half).sum() >= 3 else np.nan
    return dict(slope_ln=p[0] * 60, slope_hr=np.polyfit(x, hr, 1)[0] * 60,
                resid_sd=float(np.std(y - np.polyval(p, x), ddof=2)), s1=s1, s2=s2, te=te, nb=int(x.size))

def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def summ(g):
    if len(g) == 0: return None
    n = len(g); neg = int((g.slope_ln < 0).sum())
    return {"n": n, "pend_ln_mediana_por_min": round(float(g.slope_ln.median()), 4),
            "pend_ln_IQR": [round(float(g.slope_ln.quantile(.25)), 4), round(float(g.slope_ln.quantile(.75)), 4)],
            "pend_ln_negativa": neg, "pend_ln_negativa_pct": round(100 * neg / n, 1),
            "pend_ln_1a_mitad": round(float(g.s1.median()), 4), "pend_ln_2a_mitad": round(float(g.s2.median()), 4),
            "pend_FC_mediana_lpm_por_min": round(float(g.slope_hr.median()), 3),
            "pend_FC_positiva_pct": round(100 * float((g.slope_hr > 0).mean()), 1),
            "ruido_residual_bloque30_mediana": round(float(g.resid_sd.median()), 3),
            "t_end_eff_mediano_s": round(float(g.te.median()), 0)}

def main():
    files = {}
    for f in glob.glob(str(WORK / "rr_src" / "*")):
        m = re.search(r"(\d{4}-\d{2}-\d{2})", f)
        if m: files[m.group(1)] = f
    core = {a: pd.read_csv(OUT / a / "ENDURANCE_HRV_master_CORE.csv").set_index("Fecha") for a in ("C", "H3S90", "H3S90T375")}
    fin = {a: pd.read_csv(OUT / a / "ENDURANCE_HRV_master_FINAL.csv").set_index("Fecha") for a in ("C", "H3S90", "H3S90T375")}
    T, S = core["H3S90T375"], core["H3S90"]
    rows = []
    for day in sorted(files):
        if day not in T.index or T.loc[day, "Calidad"] == "INVALID": continue
        for tag, cut in (("corte375", 375.0), ("completo", None)):
            r = day_trend(files[day], cut)
            if r: rows.append(dict(Fecha=day, tag=tag, era="ECG" if day >= ECG_START else "Polar", **r))
    D = pd.DataFrame(rows)
    fl = T.Flags.astype(str)
    lat_new = T.index[T.Calidad.eq("FLAG_mecánico") & fl.str.contains("LAT_NAN")
                      & ~fl.str.contains("STAB_LAST2_MISMATCH|ART_GT15|STAB_TAIL_SHORT")
                      & T.HRV_Stability.eq("OK") & (T.Artifact_pct <= 15) & S.Calidad.eq("OK")]
    groups = {"no_INVALID": T.index[~T.Calidad.eq("INVALID")], "OK_corte": T.index[T.Calidad.eq("OK")],
              "nuevos_LAT_NAN_exclusivo": lat_new, "MISMATCH_corte": T.index[fl.str.contains("STAB_LAST2_MISMATCH") & ~T.Calidad.eq("INVALID")]}
    out = {"fecha": "2026-10-23", "estado": "exploratorio; no cambia CORE/FINAL/contrato",
           "entradas_sha256": {f"{a}/{k}": sha(OUT / a / f"ENDURANCE_HRV_master_{k}.csv") for a in ("C", "H3S90", "H3S90T375") for k in ("CORE", "FINAL")},
           "n_rr": len(files), "tendencia": {}, "grupos_corte375": {}, "modelo_bloques": {}, "veto": {}}
    for (tag, era), g in D.groupby(["tag", "era"]): out["tendencia"][f"{tag}_{era}"] = summ(g)
    for tag in ("corte375", "completo"):
        g = D[D.tag == tag]; n = len(g); k = int((g.slope_ln < 0).sum()); z = (k - n / 2) / math.sqrt(n / 4)
        out["tendencia"][f"{tag}_todos"] = summ(g)
        out["tendencia"][f"{tag}_signo"] = {"negativas": k, "n": n, "z": round(z, 1), "p_bilateral": float(f"{math.erfc(abs(z)/math.sqrt(2)):.1e}")}
        out["tendencia"][f"{tag}_spearman_pend_ln_vs_FC"] = round(float(g.slope_ln.rank().corr(g.slope_hr.rank())), 2)
    G = D[D.tag == "corte375"].set_index("Fecha")
    for k, ix in groups.items(): out["grupos_corte375"][k] = summ(G.reindex(ix).dropna(subset=["slope_ln"]))
    slope = abs(float(G.slope_ln.median())) / 60; sig30 = float(G.resid_sd.median()); thr = math.log(1.15)
    rng = np.random.default_rng(1)
    for L in (60, 90, 120):
        dist = (360 - L / 2) - (90 + L / 2); s = sig30 * math.sqrt(30 / L) * math.sqrt(2)
        x = rng.normal(-slope * dist, s, 200000)
        out["modelo_bloques"][str(L)] = {"distancia_centros_s": dist, "mediana_firmada": round(-slope * dist, 3),
                                          "mediana_abs": round(float(np.median(np.abs(x))), 3), "pct_abs_gt_ln1.15": round(100 * float((np.abs(x) > thr).mean()), 1)}
    for a in ("C", "H3S90", "H3S90T375"):
        f = fin[a]; c = core[a].reindex(f.index)
        v = f.veto_agudo.astype(str).str.lower().isin(["true", "1", "1.0"])
        ev = f.ln_base60.notna() & (f.SWC_ln > 0) & c.Calidad.eq("OK") & ~f.gate_razon_base60.astype(str).isin(["BASE60_INSUF", "SWC_NAN/0"])
        out["veto"][a] = {"veto": int(v.sum()), "evaluables_OK": int(ev.sum()), "pct": round(100 * float(v.sum() / ev.sum()), 1),
                          "suelo_SWC_activo": int(((f.SWC_ln < 0.04879) & ev).sum()),
                          "ROJO_pct_evaluables": round(100 * float((f.gate_final.astype(str)[ev] == "ROJO").mean()), 1)}
    out["veto"]["nota"] = "VETO_MULT=2 x SWC y SWC=0,5 x SD robusta: el veto equivale a caer >1 SD robusta bajo la base60 (normal: 15,9%)."
    RES.write_text(json.dumps(out, indent=1, ensure_ascii=False))
    print(json.dumps({k: out[k] for k in ("grupos_corte375", "modelo_bloques", "veto")}, indent=1, ensure_ascii=False))

if __name__ == "__main__":
    main()
