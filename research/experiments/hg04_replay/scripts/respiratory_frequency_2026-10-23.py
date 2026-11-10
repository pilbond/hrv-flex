"""HG-04: ¿la caída de lnRMSSD dentro del registro acompaña a un cambio de frecuencia respiratoria? (2026-10-23)

Exploratorio. No modifica CORE/FINAL ni contrato. En research/ solo se escriben agregados; la tabla por
grabación del acelerómetro se escribe en out/ (gitignored).

Parte A (RR, todos los días no INVALID de H3S90T375): RR truncados a 375 s, mismos filtros que
build_hrv_core.py y HG-03. Mitades [90,225) y [225,t_end_eff]. Frecuencia respiratoria = pico de
Lomb-Scargle del tacograma (RR destendenciado) en 0,10-0,50 Hz (sensibilidad 0,15-0,50 Hz).
Regularidad = fracción de potencia de la banda a ±0,03 Hz del pico. lnRMSSD y FC de cada mitad.
Parte B (14 grabaciones de auditoría con ECG.jsonl + ACC.jsonl de la H10): el RR de CADA grabación
se obtiene de su propio ECG con egc_to_rr.py (salida previa en $HG04_RESP_WORK/<grabacion>/), sin
emparejar por duración. Respiración por acelerómetro (primera componente principal de x,y,z, paso alto
por resta de media móvil de 10 s, paso bajo de 1 s; pico FFT en 0,10-0,50 Hz) y amplitud respiratoria
(SD de esa señal; indicador relativo de profundidad dentro de la grabación) en las mismas mitades.
Se excluyen grabaciones con artefactos >20% (regla INVALID). En mañanas con dos grabaciones se
describe la repetibilidad del lnRMSSD de [90,360] truncado.
"""
from __future__ import annotations
import csv, glob, hashlib, json, math, os, re
from pathlib import Path
import numpy as np, pandas as pd

ROOT = Path(__file__).resolve().parents[4]
WORK = Path(os.environ.get("HG04_REPLAY_WORK", Path.home() / "hg04_replay_work"))
OUT = ROOT / "out" / "hg04_copias_paralelas_2026-10-22"
RES = ROOT / "research/experiments/hg04_replay/results/respiratory_frequency_2026-10-23.json"
OUT_TABLE = ROOT / "out" / "hg04_respiracion_2026-10-23"
ECG_START = "2026-03-06"
FGRID = np.arange(0.08, 0.5001, 0.0025)

def lomb(t, y, f=FGRID):
    t = np.asarray(t, float); y = np.asarray(y, float); y = y - np.polyval(np.polyfit(t, y, 1), t)
    w = 2 * np.pi * f[:, None]
    tau = np.arctan2(np.sin(2 * w * t).sum(1), np.cos(2 * w * t).sum(1))[:, None] / (2 * w)
    c = np.cos(w * (t - tau)); s = np.sin(w * (t - tau))
    return ((y * c).sum(1) ** 2 / (c * c).sum(1) + (y * s).sum(1) ** 2 / (s * s).sum(1)) / 2

def peak(f, p, lo, hi):
    m = (f >= lo) & (f <= hi)
    if not m.any() or p[m].sum() <= 0: return np.nan, np.nan
    fm, pm = f[m], p[m]; k = int(np.argmax(pm)); fp = fm[k]
    return float(fp), float(pm[np.abs(fm - fp) <= 0.03].sum() / pm.sum())

def selftest():
    rng = np.random.default_rng(7); errs = []
    for fr in (0.15, 0.22, 0.30, 0.40):
        rr = []; t = 0.0
        while t < 135:
            v = 1.15 + 0.05 * math.sin(2 * math.pi * fr * t) + rng.normal(0, 0.02); rr.append(v); t += v
        tt = np.cumsum(rr); errs.append(abs(peak(FGRID, lomb(tt, rr), 0.10, 0.50)[0] - fr))
    assert max(errs) <= 0.005, errs
    return max(errs)

def tonum(x):
    try: return float(x)
    except (TypeError, ValueError): return 1.0 if str(x).strip().lower() == "true" else 0.0

def load_rr(path, cut=375.0):
    rr, off = [], []
    with open(path, newline="") as fh:
        for r in csv.DictReader(fh):
            try: v = float(r["duration"])
            except (TypeError, ValueError): continue
            if math.isnan(v): continue
            rr.append(v); off.append(tonum(r["offline"]) != 0)
    rr = np.array(rr); off = np.array(off, bool); idx = np.arange(rr.size)
    dur_full = float(np.sum(rr) / 1000)
    if cut: k = np.cumsum(rr) / 1000 <= cut; rr, off, idx = rr[k], off[k], idx[k]
    t = np.cumsum(rr) / 1000; te = t[-1] - 15.0
    b = (~off) & (rr >= 300) & (rr <= 2000); rb, tb, ib = rr[b], t[b], idx[b]
    keep = np.ones(rb.size, bool); keep[1:] = ~(np.abs(np.diff(rb)) / rb[:-1] > 0.20)
    rc, tc, ic = rb[keep], tb[keep], ib[keep]; e = tc <= te
    return rc[e], tc[e], ic[e], te, dur_full

def half_metrics(rc, tc, ic, a, b):
    m = (tc >= a) & (tc < b); r, t, i = rc[m], tc[m], ic[m]
    d = np.diff(r)[np.diff(i) == 1]
    if d.size < 40: return None
    p = lomb(t, r)
    f1, reg1 = peak(FGRID, p, 0.10, 0.50); f2, _ = peak(FGRID, p, 0.15, 0.50)
    return dict(ln=math.log(math.sqrt(np.mean(d * d))), hr=60000 / np.mean(r), f=f1, f15=f2, reg=reg1)

def spearman(x, y):
    x = pd.Series(x).rank().to_numpy(); y = pd.Series(y).rank().to_numpy()
    return float(np.corrcoef(x, y)[0, 1])

def perm_p(x, y, n=5000, seed=3):
    rng = np.random.default_rng(seed); r0 = abs(spearman(x, y)); xr = pd.Series(x).rank().to_numpy(); yr = pd.Series(y).rank().to_numpy()
    c = sum(abs(np.corrcoef(xr, rng.permutation(yr))[0, 1]) >= r0 for _ in range(n))
    return (c + 1) / (n + 1)

def sign_z(v):
    v = np.asarray(v); v = v[v != 0]; n = v.size; k = int((v > 0).sum())
    z = (k - n / 2) / math.sqrt(n / 4) if n else float("nan")
    return k, n, round(z, 1)

def acc_breathing(path):
    ts, X = [], []
    with open(path) as fh:
        for line in fh:
            line = line.strip()
            if not line: continue
            o = json.loads(line)
            for s in o.get("data", []):
                ts.append(s["timeStamp"]); X.append((s["x"], s["y"], s["z"]))
    ts = np.array(ts, dtype=np.float64); X = np.array(X, float)
    o = np.argsort(ts); ts, X = ts[o], X[o]
    t = (ts - ts[0]) / 1e9; fs = 1 / np.median(np.diff(t))
    X = X - X.mean(0)
    def mov(v, n): k = np.ones(n) / n; return np.apply_along_axis(lambda c: np.convolve(c, k, mode="same"), 0, v)
    Xh = X - mov(X, int(10 * fs)); Xb = mov(Xh, max(1, int(1 * fs)))
    u, s, vt = np.linalg.svd(Xb - Xb.mean(0), full_matrices=False); sig = Xb @ vt[0]
    return t, sig, fs

def acc_peak(t, sig, fs, a, b):
    m = (t >= a) & (t < b); y = sig[m]
    if y.size < fs * 60: return np.nan, np.nan
    y = (y - y.mean()) * np.hanning(y.size); n = 1 << int(np.ceil(np.log2(y.size * 8)))
    P = np.abs(np.fft.rfft(y, n)) ** 2; f = np.fft.rfftfreq(n, 1 / fs)
    return peak(f, P, 0.10, 0.50)

def main():
    st_err = selftest()
    files = {}
    for f in glob.glob(str(WORK / "rr_src" / "*")):
        mm = re.search(r"(\d{4}-\d{2}-\d{2})", f)
        if mm: files[mm.group(1)] = f
    T = pd.read_csv(OUT / "H3S90T375" / "ENDURANCE_HRV_master_CORE.csv").set_index("Fecha")
    S = pd.read_csv(OUT / "H3S90" / "ENDURANCE_HRV_master_CORE.csv").set_index("Fecha")
    rows = []
    for day in sorted(files):
        if day not in T.index or T.loc[day, "Calidad"] == "INVALID": continue
        rc, tc, ic, te, _ = load_rr(files[day])
        h1 = half_metrics(rc, tc, ic, 90.0, 225.0); h2 = half_metrics(rc, tc, ic, 225.0, te + 1e-9)
        if not (h1 and h2): continue
        rows.append(dict(Fecha=day, era="ECG" if day >= ECG_START else "Polar", calidad=T.loc[day, "Calidad"],
                         **{f"{k}1": v for k, v in h1.items()}, **{f"{k}2": v for k, v in h2.items()}))
    D = pd.DataFrame(rows)
    D["dln"] = D.ln2 - D.ln1; D["dhr"] = D.hr2 - D.hr1; D["df"] = (D.f2 - D.f1) * 60; D["df15"] = (D.f152 - D.f151) * 60
    D["br1"] = D.f1 * 60; D["br2"] = D.f2 * 60
    fl = T.Flags.astype(str)
    lat_new = set(T.index[T.Calidad.eq("FLAG_mecánico") & fl.str.contains("LAT_NAN") & ~fl.str.contains("STAB_LAST2_MISMATCH|ART_GT15|STAB_TAIL_SHORT")
                          & T.HRV_Stability.eq("OK") & (T.Artifact_pct <= 15) & S.Calidad.eq("OK")])
    mism = set(T.index[fl.str.contains("STAB_LAST2_MISMATCH")])
    def summ(g):
        k, n, z = sign_z(g.df)
        reg_ok = g[(g.reg1 >= 0.5) & (g.reg2 >= 0.5)]
        b = np.polyfit(g.df, g.dln, 1)[0] if len(g) > 5 else np.nan
        return {"n": int(len(g)),
                "resp_por_min_mitad1_mediana": round(float(g.br1.median()), 2), "resp_por_min_mitad2_mediana": round(float(g.br2.median()), 2),
                "delta_resp_por_min_mediana": round(float(g.df.median()), 2), "delta_resp_IQR": [round(float(g.df.quantile(.25)), 2), round(float(g.df.quantile(.75)), 2)],
                "delta_resp_positivo_sobre_no_nulos": [k, n], "z_signo": z,
                "delta_resp_banda_0.15_mediana": round(float(g.df15.median()), 2),
                "delta_ln_mediana": round(float(g.dln.median()), 4), "delta_FC_mediana": round(float(g.dhr.median()), 2),
                "spearman_dresp_dln": round(spearman(g.df, g.dln), 2), "spearman_dresp_dFC": round(spearman(g.df, g.dhr), 2),
                "pendiente_dln_por_resp_min": round(float(b), 4),
                "regularidad_mediana": [round(float(g.reg1.median()), 2), round(float(g.reg2.median()), 2)],
                "n_regulares_ambas_mitades": int(len(reg_ok)),
                "spearman_dresp_dln_regulares": round(spearman(reg_ok.df, reg_ok.dln), 2) if len(reg_ok) > 10 else None,
                "dln_mediana_con_dresp_0": round(float(g.dln[g.df.abs() <= 0.5].median()), 4) if (g.df.abs() <= 0.5).sum() > 10 else None,
                "n_dresp_0": int((g.df.abs() <= 0.5).sum())}
    out = {"fecha": "2026-10-23", "estado": "exploratorio; no cambia CORE/FINAL/contrato",
           "autotest_lomb_error_max_hz": round(st_err, 4),
           "entradas_sha256": {a: hashlib.sha256((OUT / a / "ENDURANCE_HRV_master_CORE.csv").read_bytes()).hexdigest() for a in ("H3S90", "H3S90T375")},
           "parteA": {"todos": summ(D), "Polar": summ(D[D.era == "Polar"]), "ECG": summ(D[D.era == "ECG"]),
                      "OK": summ(D[D.calidad == "OK"]), "nuevos_LAT_NAN": summ(D[D.Fecha.isin(lat_new)]) if D.Fecha.isin(lat_new).sum() > 5 else None,
                      "MISMATCH": summ(D[D.Fecha.isin(mism)]) if D.Fecha.isin(mism).sum() > 5 else None}}
    out["parteA"]["todos"]["p_perm_spearman_dresp_dln"] = round(perm_p(D.df, D.dln), 4)
    # Parte B: acelerómetro + RR de cada grabación desde su ECG
    RESP = Path(os.environ.get("HG04_RESP_WORK", Path.home() / "hg04_resp_work"))
    accs = sorted(glob.glob(str(ROOT / "data" / "rr_downloads" / "_source_jsonl_recovered" / "_unzipped" / "**" / "ACC.jsonl"), recursive=True))
    seen = {}; brow = []
    for p in accs:
        rec = re.search(r"PolarRecording_(\d{8})_(\d{6})", p)
        if not rec or rec.group(0) in seen: continue
        seen[rec.group(0)] = p
        t, sig, fs = acc_breathing(p)
        a1, g1 = acc_peak(t, sig, fs, 90, 225); a2, g2 = acc_peak(t, sig, fs, 225, 360)
        m1 = (t >= 90) & (t < 225); m2 = (t >= 225) & (t < 360)
        day = f"{rec.group(1)[:4]}-{rec.group(1)[4:6]}-{rec.group(1)[6:]}"
        row = dict(grabacion=rec.group(0), Fecha=day, hora=rec.group(2), dur_acc=round(float(t[-1]), 1),
                   acc_br1=a1 * 60, acc_br2=a2 * 60, acc_reg1=g1, acc_reg2=g2,
                   acc_dlog_amp=float(np.log(np.std(sig[m2]) / np.std(sig[m1]))))
        rrf = sorted(glob.glob(str(RESP / rec.group(0) / "ENDURANCE_*_RR.CSV")))
        if rrf:
            raw = pd.read_csv(rrf[0]); n_tot = int(raw["duration"].notna().sum())
            rc, tc, ic, te, durf = load_rr(rrf[0])
            k375 = np.cumsum(raw["duration"].dropna().to_numpy(float)) / 1000 <= 375
            n375 = int(k375.sum()); art = 100 * (1 - rc.size / max(n375, 1))
            row.update(dur_rr=round(durf, 1), artefactos_pct_aprox=round(art, 1), rr_igual_rr_src=False)
            src = WORK / "rr_src" / f"ENDURANCE_{day}_from_jsonl_RR.CSV"
            if src.exists():
                row["rr_igual_rr_src"] = Path(rrf[0]).read_bytes().replace(b"\r", b"") == src.read_bytes().replace(b"\r", b"")
            h1 = half_metrics(rc, tc, ic, 90.0, 225.0); h2 = half_metrics(rc, tc, ic, 225.0, te + 1e-9)
            m = (tc >= 90) & (tc <= te); d = np.diff(rc[m])[np.diff(ic[m]) == 1]
            if h1 and h2 and art <= 20:
                row.update(rr_br1=h1["f"] * 60, rr_br2=h2["f"] * 60, dln=h2["ln"] - h1["ln"], dhr=h2["hr"] - h1["hr"],
                           ln_tramo=float(math.log(math.sqrt(np.mean(d * d)))) if d.size else np.nan)
        brow.append(row)
    B = pd.DataFrame(brow)
    B["acc_dbr"] = B.acc_br2 - B.acc_br1
    V = B.dropna(subset=["rr_br1", "rr_br2"]) if "rr_br1" in B else B.iloc[0:0]
    k, n, z = sign_z(B.acc_dbr.dropna())
    pb = {"n_grabaciones": int(len(B)), "n_validas_RR_artefactos_le_20": int(len(V)),
          "acc_resp_mitad1_mediana": round(float(B.acc_br1.median()), 2), "acc_resp_mitad2_mediana": round(float(B.acc_br2.median()), 2),
          "acc_delta_resp_mediana": round(float(B.acc_dbr.median()), 2), "acc_delta_positivo_sobre_no_nulos": [k, n],
          "acc_regularidad_mediana": [round(float(B.acc_reg1.median()), 2), round(float(B.acc_reg2.median()), 2)]}
    if len(V):
        e = np.concatenate([V.rr_br1 - V.acc_br1, V.rr_br2 - V.acc_br2])
        pb["RR_menos_ACC_resp_por_min"] = {"mediana": round(float(np.median(e)), 2), "abs_mediana": round(float(np.median(np.abs(e))), 2),
                                            "abs_max": round(float(np.max(np.abs(e))), 2), "n_mitades": int(e.size), "dentro_1_resp_min": int((np.abs(e) <= 1).sum())}
        pb["validas"] = {"dln_mediana": round(float(V.dln.median()), 3), "dFC_mediana": round(float(V.dhr.median()), 2),
                         "acc_delta_resp_mediana": round(float(V.acc_dbr.median()), 2),
                         "acc_dlog_amplitud_mediana": round(float(V.acc_dlog_amp.median()), 3),
                         "acc_amplitud_baja_en_2a_mitad": [int((V.acc_dlog_amp < 0).sum()), int(len(V))],
                         "spearman_dlog_amp_vs_dln": round(spearman(V.acc_dlog_amp, V.dln), 2) if len(V) >= 6 else None,
                         "rr_identico_a_rr_src": int(V.rr_igual_rr_src.sum())}
        rep = []
        for day, g in V.groupby("Fecha"):
            if len(g) == 2:
                g = g.sort_values("hora"); rep.append(float(g.ln_tramo.iloc[1] - g.ln_tramo.iloc[0]))
        if rep:
            pb["repetibilidad_mismo_dia"] = {"n_pares": len(rep), "dif_ln_segunda_menos_primera": [round(x, 3) for x in rep],
                                            "abs_mediana": round(float(np.median(np.abs(rep))), 3),
                                            "nota": "segunda grabación tras la primera (12-24 min); no son mediciones independientes en sentido estricto"}
    out["parteB"] = pb
    RES.write_text(json.dumps(out, indent=1, ensure_ascii=False))
    OUT_TABLE.mkdir(parents=True, exist_ok=True)
    B.round(3).to_csv(OUT_TABLE / "acelerometro_por_grabacion.csv", index=False)
    D.round(4).to_csv(OUT_TABLE / "respiracion_por_dia.csv", index=False)
    print(json.dumps(out, indent=1, ensure_ascii=False))

if __name__ == "__main__":
    main()
