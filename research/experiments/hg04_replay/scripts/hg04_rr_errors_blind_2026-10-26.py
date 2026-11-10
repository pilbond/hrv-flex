"""HG-04: errores RR residuales vs discordancia cola-tramo (2026-10-26). FASE 1: ciego.

Protocolo previo: research/reports/hg04_protocolo_errores_rr_2026-10-26.md
  sha256 e2edbbd7fe061bceb2dc61060b9bfe0865bc3726eb065f4589c952876ce026f3

Exploratorio. No modifica produccion, contratos ni datos originales. No reescribe ningun RR.

Compara, en las 14 grabaciones ECG de data/rr_downloads/_source_jsonl_recovered/_unzipped/,
los latidos de egc_to_rr.py
con la deteccion independiente de ecg_peak_timing_check_2026-10-25.py (mismos parametros), y
emite los casos de discrepancia ENMASCARADOS para revision manual:
  - sin fecha, hora, tail_mismatch_pct, Calidad ni Flags,
  - detectores etiquetados A/B con asignacion aleatoria e independiente por caso,
  - orden barajado con semilla fija.
La correspondencia caso -> (grabacion, detector) se guarda aparte y NO se lee en esta fase.

Salidas:
  out/hg04_errores_rr_2026-10-26/casos_ciegos.json        <- para revisar
  out/hg04_errores_rr_2026-10-26/mapa_desenmascarar.json  <- NO abrir hasta fijar el veredicto
  out/hg04_errores_rr_2026-10-26/emparejamiento.csv       <- metricas por grabacion
"""
from __future__ import annotations
import csv, glob, hashlib, json, math, os, re
from pathlib import Path
import numpy as np
from scipy.signal import butter, filtfilt, find_peaks

ROOT = Path(__file__).resolve().parents[4]
RESP = Path(os.path.expanduser("~")) / "hg04_resp_work"
OUT = ROOT / "out/hg04_errores_rr_2026-10-26"
SEED = 20261026
TOL_S = 0.060          # tolerancia de emparejamiento, heredada
OFFLINE_MAX = 0.10     # exclusion heredada
WIN_S = 3.0            # ventana de ECG por caso, +-3 s
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()


def load_ecg(p):
    ts, v = [], []
    for line in open(p):
        line = line.strip()
        if not line: continue
        o = json.loads(line)
        for s in o.get("data", []):
            ts.append(s["timeStamp"]); v.append(s["voltage"])
    ts = np.array(ts, dtype=np.float64); v = np.array(v, float); o = np.argsort(ts)
    return (ts[o] - ts[o][0]) / 1e9, v[o]


def detect(t, v):
    """Detector independiente. Parametros identicos a ecg_peak_timing_check_2026-10-25.py."""
    fs = 1 / np.median(np.diff(t))
    b, a = butter(2, [5 / (fs / 2), min(20 / (fs / 2), 0.99)], btype="band")
    f = filtfilt(b, a, v); e = f ** 2
    pk, _ = find_peaks(e, distance=int(0.33 * fs), height=np.percentile(e, 97) * 0.25)
    out = []
    for i in pk:
        if i < 1 or i >= len(e) - 1: out.append(t[i]); continue
        y0, y1, y2 = e[i - 1], e[i], e[i + 1]; d = (y0 - 2 * y1 + y2)
        dl = 0.5 * (y0 - y2) / d if d != 0 else 0.0
        out.append(t[i] + max(min(dl, 0.5), -0.5) / fs)
    return np.array(out), fs


def load_conv(folder):
    """Instantes del conversor por suma acumulada de RR, con marca offline."""
    g = sorted(glob.glob(str(folder / "ENDURANCE_*_RR.CSV")))
    if not g: return None
    rr, off = [], []
    for x in csv.DictReader(open(g[0], newline="")):
        try: w = float(x["duration"])
        except (TypeError, ValueError, KeyError): continue
        if math.isnan(w): continue
        rr.append(w)
        o = str(x.get("offline", "")).strip().lower()
        off.append(o in ("true", "1", "1.0"))
    rr = np.array(rr, float); off = np.array(off, bool)
    if rr.size == 0: return None
    if np.median(rr) > 10: rr = rr / 1000.0          # ms -> s si procede
    return np.cumsum(rr), rr, off, Path(g[0])


def align(a, b):
    """Desplazamiento global que minimiza el residuo mediano (busqueda gruesa + fina)."""
    best, bshift = None, 0.0
    for coarse in np.arange(-5.0, 5.0, 0.05):
        d = [abs(x - b[np.argmin(np.abs(b - x))]) for x in (a[:200] + coarse)]
        m = np.median(d) if d else np.inf
        if best is None or m < best: best, bshift = m, coarse
    for fine in np.arange(bshift - 0.05, bshift + 0.05, 0.001):
        d = [abs(x - b[np.argmin(np.abs(b - x))]) for x in (a[:200] + fine)]
        m = np.median(d) if d else np.inf
        if m < best: best, bshift = m, fine
    return bshift


def match(a, b, tol=TOL_S):
    """Empareja cada instante de a con el mas cercano de b. Devuelve pares y huerfanos."""
    pairs, used = [], set()
    for i, x in enumerate(a):
        j = int(np.argmin(np.abs(b - x)))
        if abs(b[j] - x) <= tol and j not in used:
            pairs.append((i, j, b[j] - x)); used.add(j)
    ua = [i for i in range(len(a)) if i not in {p[0] for p in pairs}]
    ub = [j for j in range(len(b)) if j not in used]
    return pairs, ua, ub


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(SEED)
    ecgs = {}
    for p in sorted(set(glob.glob(str(ROOT / "data/rr_downloads/_source_jsonl_recovered/_unzipped/**/ECG.jsonl"), recursive=True))):
        m = re.search(r"PolarRecording_(\d{8})_(\d{6})", p)
        if m: ecgs.setdefault(m.group(0), p)        # dedup: misma grabacion en dos carpetas

    filas, casos, mapa = [], [], {}
    for rec, ep in sorted(ecgs.items()):
        folder = RESP / rec
        conv = load_conv(folder)
        if conv is None:
            filas.append({"grabacion": rec, "estado": "sin RR del conversor"}); continue
        ct, rr, off, rrpath = conv
        if off.mean() > OFFLINE_MAX:
            filas.append({"grabacion": rec, "estado": f"excluida: offline {off.mean():.1%}"}); continue
        t, v = load_ecg(ep)
        mine, fs = detect(t, v)
        sh = align(ct, mine)
        ct_al = ct + sh
        pairs, solo_conv, solo_indep = match(ct_al, mine)
        resid = np.array([p[2] for p in pairs]) * 1000.0

        filas.append({"grabacion": rec, "estado": "ok", "fs_Hz": round(float(fs), 2),
                      "n_conversor": len(ct), "n_independiente": len(mine),
                      "emparejados": len(pairs), "solo_conversor": len(solo_conv),
                      "solo_independiente": len(solo_indep),
                      "offline_pct": round(float(off.mean() * 100), 2),
                      "desplazamiento_s": round(float(sh), 4),
                      "resid_mediano_ms": round(float(np.median(np.abs(resid))), 3) if len(resid) else None,
                      "resid_p95_ms": round(float(np.percentile(np.abs(resid), 95)), 3) if len(resid) else None,
                      "rr_file": rrpath.name, "rr_sha256": sha(rrpath), "ecg_sha256": sha(ep)})

        # --- casos de discrepancia, enmascarados ---
        for origen, idxs, serie in (("conv", solo_conv, ct_al), ("indep", solo_indep, mine)):
            for i in idxs:
                inst = float(serie[i])
                # Ventana recortada en los bordes en lugar de descartar el caso: asi TODAS las
                # discrepancias pasan por la revision ciega y ninguna se clasifica sin enmascarar.
                m = (t >= inst - WIN_S) & (t <= inst + WIN_S)
                if m.sum() < 50: continue
                borde = inst < WIN_S or inst > float(t[-1]) - WIN_S
                etiq = ["A", "B"]; rng.shuffle(etiq)
                lab = {"conv": etiq[0], "indep": etiq[1]}
                cid = f"C{len(casos) + 1:03d}"
                tw = t[m]; vw = v[m]
                marcas = {}
                for nm, s in (("conv", ct_al), ("indep", mine)):
                    sel = s[(s >= inst - WIN_S) & (s <= inst + WIN_S)]
                    marcas[lab[nm]] = [round(float(x - inst), 4) for x in sel]
                casos.append({
                    "caso": cid,
                    "ecg_t_rel_s": [round(float(x - inst), 4) for x in tw],
                    "ecg_uV": [round(float(x), 1) for x in vw],
                    "marcas_rel_s": marcas,
                    "rr_local_ms_entre_marcas": {k: [round((marcas[k][j + 1] - marcas[k][j]) * 1000, 1)
                                                     for j in range(len(marcas[k]) - 1)]
                                                 for k in marcas},
                    "ventana_recortada_por_borde": bool(borde),
                })
                mapa[cid] = {"grabacion": rec, "instante_s": round(inst, 4),
                             "detector_que_lo_marco": origen, "etiqueta_de_ese_detector": lab[origen],
                             "etiquetas": lab}

    rng.shuffle(casos)
    (OUT / "casos_ciegos.json").write_text(json.dumps(
        {"protocolo_sha256": sha(ROOT / "research/reports/hg04_protocolo_errores_rr_2026-10-26.md"),
         "semilla": SEED, "n_casos": len(casos),
         "instrucciones": "Clasificar cada caso en FALTA / EXTRA / DOBLE / AMBIGUO mirando solo el "
                          "ECG y las marcas A/B. No se indica fecha, flag ni que detector es cada una.",
         "casos": casos}, ensure_ascii=False, indent=1), encoding="utf-8")
    (OUT / "mapa_desenmascarar.json").write_text(json.dumps(mapa, ensure_ascii=False, indent=1),
                                                 encoding="utf-8")
    with open(OUT / "emparejamiento.csv", "w", newline="", encoding="utf-8-sig") as fh:
        cols = sorted({k for f in filas for k in f})
        w = csv.DictWriter(fh, fieldnames=["grabacion", "estado"] + [c for c in cols if c not in ("grabacion", "estado")])
        w.writeheader(); [w.writerow(f) for f in filas]

    print(f"{'grabacion':32s} {'empar':>6s} {'soloC':>6s} {'soloI':>6s} {'off%':>6s} {'|res|ms':>8s}")
    for f in filas:
        if f.get("estado") != "ok": print(f"{f['grabacion']:32s} {f['estado']}"); continue
        print(f"{f['grabacion']:32s} {f['emparejados']:6d} {f['solo_conversor']:6d} "
              f"{f['solo_independiente']:6d} {f['offline_pct']:6.2f} {f['resid_mediano_ms']:8.2f}")
    tot = [f for f in filas if f.get("estado") == "ok"]
    ne = sum(f["emparejados"] for f in tot)
    print(f"\ngrabaciones utilizables: {len(tot)} de {len(ecgs)}")
    print(f"latidos emparejados: {ne}")
    print(f"solo conversor: {sum(f['solo_conversor'] for f in tot)} | "
          f"solo independiente: {sum(f['solo_independiente'] for f in tot)}")
    print(f"casos ciegos generados: {len(casos)}")
    print(f"\n-> revisar {OUT.relative_to(ROOT)}/casos_ciegos.json SIN abrir mapa_desenmascarar.json")


if __name__ == "__main__":
    main()
