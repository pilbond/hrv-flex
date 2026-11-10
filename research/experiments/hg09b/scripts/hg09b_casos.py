"""HG-09B §4.1-4.3: correspondencia ECG<->RR, detección independiente y casos ciegos.

Protocolo: research/reports/hg09b_protocolo_evidencia_mismatch_2026-10-27.md (huella en salidas).
Grabaciones: ZIP en data/rr_downloads/_source_jsonl_recovered y ECG/ACC en su
_unzipped/. RR reconvertido solo en $HOME/hg09b_tmp
(fuera del repo). Salidas en out/hg09b_casos_2026-10-27/ (datos personales, no versionados):
  registro.csv         correspondencia y uso de cada grabación
  paneles/P###.png     6 casos por imagen, sin fecha, grupo, flag ni identidad del detector
  casos_ciegos.json    lista de casos (id, etiquetas A/B no reveladas)
  mapa_desenmascarar.json  NO abrir antes de sellar el veredicto
Agregados sin datos personales: research/experiments/hg09b/results/hg09b_casos_resumen.json
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import math
import os
import re
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import hg09b_motor as motor  # noqa: E402
import importlib.util  # noqa: E402
import matplotlib  # noqa: E402
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from scipy.signal import butter, filtfilt, find_peaks  # noqa: E402

ROOT = motor.ROOT
SEL = HERE.parent / "results/hg09b_seleccion_2026-10-27.json"
PROTO = ROOT / "research/reports/hg09b_protocolo_evidencia_mismatch_2026-10-27.md"
REC_DIR = ROOT / "data/rr_downloads/_source_jsonl_recovered"
UNZ_DIR = REC_DIR / "_unzipped"
TMP = Path(os.path.expanduser("~")) / "hg09b_tmp"
OUT = ROOT / "out/hg09b_casos_2026-10-27"
RES = HERE.parent / "results/hg09b_casos_resumen.json"
HG05 = ROOT / "research/experiments/hg05/scripts/hg05_ventana_vs_global_375.py"
SEED, TOL, WIN, OFF_MAX = 20261027, 0.060, 3.0, 0.10
N_CONC, N_SUSP_MAX, LO, CUT = 8, 15, 80.0, 375.0
sha = lambda b: hashlib.sha256(b).hexdigest()


# ------------------------------------------------------------------ ECG y detector (HG-04, sin cambios)
def load_ecg(p):
    ts, v = [], []
    for line in open(p):
        line = line.strip()
        if not line:
            continue
        o = json.loads(line)
        for s in o.get("data", []):
            ts.append(s["timeStamp"]); v.append(s["voltage"])
    ts = np.array(ts, dtype=np.float64); v = np.array(v, float); o = np.argsort(ts)
    return (ts[o] - ts[o][0]) / 1e9, v[o]


def detect(t, v):
    fs = 1 / np.median(np.diff(t))
    b, a = butter(2, [5 / (fs / 2), min(20 / (fs / 2), 0.99)], btype="band")
    f = filtfilt(b, a, v); e = f ** 2
    pk, _ = find_peaks(e, distance=int(0.33 * fs), height=np.percentile(e, 97) * 0.25)
    out = []
    for i in pk:
        if i < 1 or i >= len(e) - 1:
            out.append(t[i]); continue
        y0, y1, y2 = e[i - 1], e[i], e[i + 1]; d = (y0 - 2 * y1 + y2)
        dl = 0.5 * (y0 - y2) / d if d != 0 else 0.0
        out.append(t[i] + max(min(dl, 0.5), -0.5) / fs)
    return np.array(out), fs, f


def align(a, b):
    best, bshift = None, 0.0
    for coarse in np.arange(-5.0, 5.0, 0.05):
        d = [abs(x - b[np.argmin(np.abs(b - x))]) for x in (a[:200] + coarse)]
        m = np.median(d) if d else np.inf
        if best is None or m < best:
            best, bshift = m, coarse
    for fine in np.arange(bshift - 0.05, bshift + 0.05, 0.001):
        d = [abs(x - b[np.argmin(np.abs(b - x))]) for x in (a[:200] + fine)]
        m = np.median(d) if d else np.inf
        if m < best:
            best, bshift = m, fine
    return bshift, best


def match(a, b, tol=TOL):
    pairs, used = [], set()
    for i, x in enumerate(a):
        j = int(np.argmin(np.abs(b - x)))
        if abs(b[j] - x) <= tol and j not in used:
            pairs.append((i, j)); used.add(j)
    pa = {p[0] for p in pairs}
    return pairs, [i for i in range(len(a)) if i not in pa], [j for j in range(len(b)) if j not in used]


# ------------------------------------------------------------------ utilidades de RR
def rr_df(raw: bytes) -> pd.DataFrame:
    return pd.read_csv(io.BytesIO(raw))


def same_rr(a: pd.DataFrame, b: pd.DataFrame) -> dict:
    n = min(len(a), len(b))
    da = pd.to_numeric(a.duration, errors="coerce").to_numpy()[:n]
    db = pd.to_numeric(b.duration, errors="coerce").to_numpy()[:n]
    oa = a.offline.astype(str).str.lower().isin(["1", "true", "1.0"]).to_numpy()[:n]
    ob = b.offline.astype(str).str.lower().isin(["1", "true", "1.0"]).to_numpy()[:n]
    eq = np.isclose(da, db, atol=1e-9, equal_nan=True)
    return {"n_core": len(a), "n_reconv": len(b), "dur_iguales": float(eq.mean()) if n else 0.0,
            "offline_iguales": float((oa == ob).mean()) if n else 0.0,
            "identico": bool(len(a) == len(b) and eq.all() and (oa == ob).all())}


def extract_and_convert(zp: Path) -> tuple[Path, Path] | None:
    rec = zp.stem
    c = TMP / "conv" / rec
    c.mkdir(parents=True, exist_ok=True)
    ecg = next((d / "ECG.jsonl" for d in sorted(UNZ_DIR.glob(rec + "_*")) if (d / "ECG.jsonl").exists()), None)
    if ecg is None:
        return None
    if not list(c.glob("*.CSV")):
        cmd = [sys.executable, "-B", str(ROOT / "egc_to_rr.py"), "--ecg", str(ecg), "--outdir", str(c), "--no-aux"]
        if (ecg.parent / "ACC.jsonl").exists():
            cmd[5:5] = ["--acc", str(ecg.parent / "ACC.jsonl")]
        subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
    g = sorted(c.glob("*.CSV"))
    return (ecg, g[0]) if g else None


def zips_for(date: str) -> list[Path]:
    key = date.replace("-", "")
    out = []
    for base in (REC_DIR,):
        if base.exists():
            out += [p for p in base.glob("*.zip") if re.search(rf"PolarRecording_{key}_\d{{6}}", p.name, re.I)]
    return sorted(set(out), key=lambda p: p.name.lower())


# ------------------------------------------------------------------ main
def main():
    sel = json.loads(SEL.read_text(encoding="utf-8"))
    core = pd.read_csv(ROOT / "data/ENDURANCE_HRV_master_CORE.csv")
    spec = importlib.util.spec_from_file_location("hg05_loader", HG05)
    h5 = importlib.util.module_from_spec(spec); spec.loader.exec_module(h5)
    mod = motor.engine()
    C = mod.CONSTANTS

    roles = {d: "M" for d in sel["M"]} | {d: "M2" for d in sel["M2"]}
    plan = []  # (fecha, rol, caso_ref)
    for d in sel["M"] + sel["M2"]:
        plan.append((d, roles[d], d))
    for case, ctrls in sel["controles"].items():
        for d in ctrls:
            plan.append((d, "C", case))

    rng = np.random.default_rng(SEED)
    TMP.mkdir(parents=True, exist_ok=True)
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "paneles").mkdir(exist_ok=True)
    registro, casos, mapa = [], [], {}
    usados = set()

    def process(fecha, rol, ref):
        raw = h5.load_rr_bytes(core[core.Fecha == fecha]).get(fecha)
        base = {"fecha": fecha, "rol": rol, "caso_ref": ref}
        if raw is None:
            return {**base, "estado": "sin RR del CORE"}
        core_rr = rr_df(raw)
        zs = zips_for(fecha)
        if not zs:
            return {**base, "estado": "sin ECG"}
        best = None
        for zp in zs:
            r = extract_and_convert(zp)
            if r is None:
                continue
            cmp = same_rr(core_rr, pd.read_csv(r[1]))
            if best is None or (cmp["identico"], cmp["dur_iguales"]) > (best[2]["identico"], best[2]["dur_iguales"]):
                best = (zp, r, cmp)
        if best is None:
            return {**base, "estado": "ECG ilegible"}
        zp, (ecg_p, conv_p), cmp = best
        base |= {"grabacion": zp.stem, "zip_sha256": sha(zp.read_bytes()), "rr_core_sha256": sha(raw), **cmp}
        rr_tmp = TMP / "core_rr" / f"{fecha}.CSV"
        rr_tmp.parent.mkdir(parents=True, exist_ok=True)
        rr_tmp.write_bytes(raw)
        dur = pd.to_numeric(core_rr.duration, errors="coerce")
        off = core_rr.offline.astype(str).str.lower().isin(["1", "true", "1.0"]).to_numpy()
        keep = dur.notna().to_numpy()
        ct = np.cumsum(dur[keep].to_numpy()) / 1000.0
        offk = off[keep]
        if offk.mean() > OFF_MAX:
            return {**base, "estado": f"no utilizable: offline {offk.mean():.1%}"}
        t, v = load_ecg(ecg_p)
        mine, fs, filt = detect(t, v)
        sh, res = align(ct, mine)
        if res > 0.020:
            return {**base, "estado": f"no alineable: residuo {res*1000:.1f} ms"}
        cta = ct + sh
        if cta[np.searchsorted(ct, CUT, side="right") - 1] > t[-1] - WIN:
            return {**base, "estado": "ECG no cubre [0,375] s"}
        pairs, solo_c, solo_i = match(cta, mine)
        ctx = mod._parse_and_filter_rr(rr_tmp, C)
        t_end = float(ctx.t_end_eff)
        info = {**base, "estado": "ok", "fs": round(float(fs), 2), "desplazamiento_s": round(float(sh), 4),
                "residuo_mediano_ms": round(float(res) * 1000, 2), "t_end_eff": round(t_end, 2),
                "offline_pct": round(float(offk.mean()) * 100, 2)}
        events = []  # (tiempo_eje_core, tipo, extra)
        for i in solo_c:
            if LO <= ct[i] <= CUT:
                events.append((ct[i], "discrepancia_conv", {"i_conv": int(i)}))
        for j in solo_i:
            tc = mine[j] - sh
            if LO <= tc <= CUT:
                events.append((tc, "discrepancia_indep", {"t_indep": float(mine[j])}))
        # intervalos aceptados sospechosos (tramo [90, t_end])
        rr_e, t_e, idx_e = ctx.rr_eff, ctx.t_eff, ctx.original_idx_eff
        tram = np.where(t_e >= 90.0)[0]
        susp = []
        for k in tram:
            lo_, hi_ = max(0, k - 5), min(len(rr_e), k + 6)
            nb = np.r_[rr_e[lo_:k], rr_e[k + 1:hi_]]
            if nb.size < 4:
                continue
            med = np.median(nb)
            dev = abs(rr_e[k] / med - 1) > 0.12
            sl = (k + 1 < len(rr_e) and idx_e[k + 1] == idx_e[k] + 1 and rr_e[k] < 0.88 * med and rr_e[k + 1] > 1.10 * med)
            if dev or sl:
                susp.append(k)
        info["n_sospechosos"] = len(susp)
        if len(susp) > N_SUSP_MAX:
            susp = sorted(rng.choice(susp, N_SUSP_MAX, replace=False).tolist())
        info["n_sospechosos_revisados"] = len(susp)
        disc_t = np.array([e[0] for e in events]) if events else np.array([])
        for k in susp:
            tk = float(t_e[k])
            if disc_t.size and np.min(np.abs(disc_t - tk)) <= TOL:
                continue
            events.append((tk, "intervalo_aceptado", {"rr_ms": float(rr_e[k]), "orig_idx": int(idx_e[k])}))
        # concordantes al azar en el tramo
        conc = [i for i, _ in pairs if 90.0 <= ct[i] <= t_end]
        taken = np.array([e[0] for e in events]) if events else np.array([])
        conc = [i for i in conc if not (taken.size and np.min(np.abs(taken - ct[i])) <= TOL)]
        for i in sorted(rng.choice(conc, min(N_CONC, len(conc)), replace=False).tolist()):
            events.append((ct[i], "concordante", {"i_conv": int(i)}))
        info["n_discrepancias"] = sum(e[1].startswith("discrepancia") for e in events)
        info["n_concordantes"] = sum(e[1] == "concordante" for e in events)
        info["n_intervalos"] = sum(e[1] == "intervalo_aceptado" for e in events)
        for tcore, tipo, extra in events:
            inst = tcore + sh
            m = (t >= inst - WIN) & (t <= inst + WIN)
            if m.sum() < 50:
                continue
            lab = ["A", "B"]; rng.shuffle(lab)
            lab = {"conv": lab[0], "indep": lab[1]}
            marks = {lab["conv"]: [float(x - inst) for x in cta[(cta >= inst - WIN) & (cta <= inst + WIN)]],
                     lab["indep"]: [float(x - inst) for x in mine[(mine >= inst - WIN) & (mine <= inst + WIN)]]}
            cid = f"K{rng.integers(10**6):06d}"
            while cid in mapa:
                cid = f"K{rng.integers(10**6):06d}"
            casos.append({"caso": cid, "t": (t[m] - inst).tolist(), "v": v[m].tolist(), "f": filt[m].tolist(), "marcas": marks})
            mapa[cid] = {"fecha": fecha, "rol": rol, "caso_ref": ref, "grabacion": zp.stem, "tipo": tipo,
                         "t_core_s": round(float(tcore), 4), "etiquetas": lab, **extra}
        return info

    m_ok = set()
    for fecha, rol, ref in plan:
        if rol == "C" and ref not in m_ok:
            registro.append({"fecha": fecha, "rol": rol, "caso_ref": ref, "estado": "omitido: caso sin ECG utilizable"})
            continue
        info = process(fecha, rol, ref)
        if rol == "M" and info.get("estado") == "ok":
            m_ok.add(fecha)
        # sustitución de controles no utilizables por reservas (protocolo §3)
        if rol == "C" and info.get("estado") != "ok":
            registro.append(info)
            for alt in sel["reservas"].get(ref, []):
                if alt in usados:
                    continue
                usados.add(alt)
                info = process(alt, "C", ref)
                info["sustituye_a"] = fecha
                if info.get("estado") == "ok":
                    break
                registro.append(info)
        registro.append(info)

    # paneles: orden barajado, 6 por imagen
    order = rng.permutation(len(casos))
    casos = [casos[i] for i in order]
    for p in range(0, len(casos), 6):
        chunk = casos[p:p + 6]
        fig, axs = plt.subplots(3, 2, figsize=(16, 12), dpi=70)
        for ax, c in zip(axs.flat, chunk):
            tt, vv, ff = np.array(c["t"]), np.array(c["v"]), np.array(c["f"])
            vn = (vv - np.median(vv)) / (np.percentile(np.abs(vv - np.median(vv)), 99) or 1)
            fn = (ff) / (np.percentile(np.abs(ff), 99) or 1)
            ax.plot(tt, vn, color="black", lw=0.9)
            ax.plot(tt, fn * 0.5 - 2.2, color="0.6", lw=0.6)
            ax.axvline(0, color="green", ls="--", lw=1)
            for lbl, col, y, mk in (("A", "red", 1.6, "v"), ("B", "blue", -3.2, "^")):
                xs = np.array(sorted(c["marcas"].get(lbl, [])))
                ax.plot(xs, np.full(xs.size, y), mk, color=col, ms=9, label=lbl)
                for a_, b_ in zip(xs[:-1], xs[1:]):
                    ax.text((a_ + b_) / 2, y + (0.25 if lbl == "A" else -0.45), f"{(b_ - a_)*1000:.0f}", color=col, fontsize=8, ha="center")
            ax.set_xlim(-WIN, WIN); ax.set_ylim(-4, 2.4); ax.set_yticks([])
            ax.set_title(c["caso"], fontsize=11, loc="left")
            ax.grid(axis="x", alpha=0.3)
        for ax in list(axs.flat)[len(chunk):]:
            ax.axis("off")
        fig.tight_layout()
        fig.savefig(OUT / "paneles" / f"P{p // 6 + 1:03d}.png")
        plt.close(fig)

    (OUT / "casos_ciegos.json").write_text(json.dumps({"casos": [{"caso": c["caso"]} for c in casos],
        "instrucciones": "Juzgar el evento en t=0 (línea verde). Negro: ECG; gris: ECG filtrado. A (rojo, arriba) y B (azul, abajo) son dos detectores sin identificar; números = RR en ms."},
        ensure_ascii=False, indent=1), encoding="utf-8")
    (OUT / "mapa_desenmascarar.json").write_text(json.dumps(mapa, ensure_ascii=False, indent=1), encoding="utf-8")
    pd.DataFrame(registro).to_csv(OUT / "registro.csv", index=False, encoding="utf-8-sig")
    ok = [r for r in registro if r.get("estado") == "ok"]
    res = {"protocolo_sha256": sha(PROTO.read_bytes()), "seleccion_sha256": sha(SEL.read_bytes()),
           "motor": motor.fingerprints(), "egc_to_rr_sha256": sha((ROOT / "egc_to_rr.py").read_bytes()),
           "detector": "ecg_peak_timing_check_2026-10-25 (parámetros sin cambios)",
           "grabaciones": {r["fecha"]: {k: r.get(k) for k in ("rol", "caso_ref", "estado", "identico", "dur_iguales", "residuo_mediano_ms",
                                                         "n_discrepancias", "n_concordantes", "n_intervalos", "n_sospechosos", "sustituye_a")}
                           for r in registro},
           "n_utilizables_por_rol": pd.Series([r["rol"] for r in ok]).value_counts().to_dict(),
           "n_casos": len(casos), "n_paneles": math.ceil(len(casos) / 6),
           "casos_por_tipo": pd.Series([m["tipo"] for m in mapa.values()]).value_counts().to_dict(),
           "mapa_sha256": sha((OUT / "mapa_desenmascarar.json").read_bytes())}
    RES.write_text(json.dumps(res, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    print(json.dumps({k: res[k] for k in ("n_utilizables_por_rol", "n_casos", "n_paneles", "casos_por_tipo")}, ensure_ascii=False, indent=1))
    for r in registro:
        print(r["fecha"], r["rol"], r.get("estado"), r.get("identico"), r.get("sustituye_a", ""))


if __name__ == "__main__":
    main()
