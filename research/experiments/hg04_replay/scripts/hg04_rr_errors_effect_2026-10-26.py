"""HG-04: efecto de los errores verificados y sensibilidad del indicador (2026-10-26). FASE 2.

Protocolo: research/reports/hg04_protocolo_errores_rr_2026-10-26.md
  sha256 e2edbbd7fe061bceb2dc61060b9bfe0865bc3726eb065f4589c952876ce026f3
Veredicto ciego (sellado antes de desenmascarar):
  out/hg04_errores_rr_2026-10-26/veredicto_ciego.json

Exploratorio. No modifica produccion, contratos ni datos originales.

A) Localiza cada error verificado del conversor respecto a la geometria del CORE
   (tramo [90, t_end_eff], cola [t_end_eff-120, t_end_eff], corte 375 s, TAIL_TRIM_S 15).
B) Aplica la correccion trazable y recalcula RMSSD_tramo, RMSSD_cola y tail_mismatch_pct.
C) Prueba de SENSIBILIDAD, separada: inserta errores plausibles en una rejilla de posiciones
   sobre las series RR de los 29 dias recuperados y mide la respuesta de tail_mismatch_pct.
   Una simulacion muestra sensibilidad; no demuestra que el error existiera.
"""
from __future__ import annotations
import csv, glob, hashlib, json, math, os, re
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parents[4]
RESP = Path(os.path.expanduser("~")) / "hg04_resp_work"
WORK = Path(os.environ.get("HG04_REPLAY_WORK", Path.home() / "hg04_replay_work")) / "rr_src"
OUT = ROOT / "out/hg04_errores_rr_2026-10-26"
RES = ROOT / "research/experiments/hg04_replay/results/hg04_rr_errors_2026-10-26.json"
SEED = 20261026
CUT, T0, TAIL_TRIM, TAIL_S = 375.0, 90.0, 15.0, 120.0
REF = Path(os.path.expanduser("~")) / "hg04_replay_work/H3S90T375/data/ENDURANCE_HRV_master_CORE.csv"
DELTA_RR_MAX, RR_MIN_MS, RR_MAX_MS = 0.20, 300.0, 2000.0
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()


def rmssd_ms(rr_s, idx=None):
    """HG-03: RMSSD (ms) SOLO entre pares originalmente consecutivos.

    Replica build_hrv_core_H3S90T375.rr_pair_diffs: un par cuenta si original_idx
    avanza exactamente 1. Sin `idx` se asume que todos lo son.
    """
    r = np.asarray(rr_s, float)
    if r.size < 2: return float("nan")
    d = np.diff(r) * 1000.0
    if idx is not None:
        idx = np.asarray(idx)
        if idx.size != r.size: return float("nan")
        d = d[np.diff(idx) == 1]
    if d.size == 0: return float("nan")
    return float(np.sqrt(np.mean(d ** 2)))


def geometria(rr_s, idx=None, dur_raw=None, tiempos=None):
    """Replica la geometria de la copia H3S90T375 (HG-03 + inicio 90 s + corte 375 s).

    `idx` son los indices originales (para los pares consecutivos de HG-03);
    `dur_raw` la duracion ANTES de limpiar, que es la que fija t_end_eff en el CORE.
    """
    rr = np.asarray(rr_s, float)
    if rr.size < 3: return dict(RMSSD=float("nan"), RMSSD_cola=float("nan"), tmm=float("nan"))
    # El eje de tiempos es el ORIGINAL (t_end_raw filtrado), no un cumsum de la serie limpia:
    # al quitar latidos, recalcular el cumsum desplazaria la ventana. La copia conserva t_end_raw.
    t = np.asarray(tiempos, float) if tiempos is not None else np.cumsum(rr)
    dur = float(dur_raw) if dur_raw is not None else float(t[-1])
    t_end = dur - TAIL_TRIM
    tramo = (t >= T0) & (t <= t_end)
    tail = (t >= t_end - TAIL_S) & (t <= t_end)
    ix = None if idx is None else np.asarray(idx)
    R = rmssd_ms(rr[tramo], None if ix is None else ix[tramo])
    Rc = rmssd_ms(rr[tail], None if ix is None else ix[tail])
    tmm = float(abs(Rc - R) / R * 100.0) if (R == R and Rc == Rc and R > 0) else float("nan")
    return dict(RMSSD=R, RMSSD_cola=Rc, tmm=tmm, n_tramo=int(tramo.sum()), n_cola=int(tail.sum()),
                t_end=t_end, dur=dur)


def load_rr_csv(path, cut=CUT):
    """Replica _parse_and_filter_rr de la copia H3S90T375, en el mismo orden.

    Orden exacto: NaN -> corte 375 s -> dur_raw -> offline y fuera de rango -> delta-RR.
    Devuelve (rr_s, original_idx, dur_raw) para poder aplicar HG-03 y la geometria.
    """
    rr, off = [], []
    for x in csv.DictReader(open(path, newline="")):
        try: w = float(x["duration"])
        except (TypeError, ValueError, KeyError): w = float("nan")
        o = str(x.get("offline", "")).strip().lower()
        rr.append(w); off.append(1 if o in ("true", "1", "1.0") else 0)
    rr_ms = np.array(rr, float); offline = np.array(off, int)
    valid = ~np.isnan(rr_ms)
    rr_ms, offline = rr_ms[valid], offline[valid]
    if rr_ms.size and np.median(rr_ms) < 10: rr_ms = rr_ms * 1000.0     # s -> ms si procede
    original_idx = np.arange(rr_ms.size, dtype=np.int64)
    if cut:                                                             # corte 375 s
        k = (np.cumsum(rr_ms) / 1000.0) <= cut
        rr_ms, offline, original_idx = rr_ms[k], offline[k], original_idx[k]
    dur_raw = float(np.sum(rr_ms) / 1000.0)
    t_end_raw = np.cumsum(rr_ms) / 1000.0          # eje original, antes de filtrar
    oor = (offline == 0) & ((rr_ms < RR_MIN_MS) | (rr_ms > RR_MAX_MS))
    base = (offline == 0) & (~oor)
    rr_b, idx_b, t_b = rr_ms[base], original_idx[base], t_end_raw[base]
    keep = np.ones(rr_b.size, dtype=bool)
    if rr_b.size > 1:
        keep[1:] = ~(np.abs(rr_b[1:] - rr_b[:-1]) / rr_b[:-1] > DELTA_RR_MAX)
    return rr_b[keep] / 1000.0, idx_b[keep], dur_raw, t_b[keep]



def simula(rr, t, idx, i, tipo):
    """Inserta UN error de deteccion y devuelve (rr, t, idx) coherentes.

    El eje de tiempos se edita igual que lo haria el error real: una omision borra el
    instante del latido perdido; un extra inserta uno nuevo. Los indices se renumeran
    porque el conversor habria emitido esa serie como consecutiva.
    """
    rr, t = rr.copy(), np.asarray(t, float).copy()
    if tipo == "omision":
        rr = np.concatenate([rr[:i], [rr[i] + rr[i + 1]], rr[i + 2:]])
        t = np.concatenate([t[:i], t[i + 1:]])
    elif tipo == "extra":
        h = rr[i] / 2.0
        rr = np.concatenate([rr[:i], [h, h], rr[i + 1:]])
        t = np.concatenate([t[:i], [t[i] - h], t[i:]])
    else:
        k = 0.15 if tipo == "ectopico15" else 0.25
        d = rr[i] * k
        rr[i] -= d; rr[i + 1] += d
        t[i] -= d
    return rr, t, np.arange(rr.size, dtype=np.int64)


def main():
    ver = json.loads((OUT / "veredicto_ciego.json").read_text(encoding="utf-8"))["veredictos"]
    mapa = json.loads((OUT / "mapa_desenmascarar.json").read_text(encoding="utf-8"))
    ref = {r["Fecha"]: r for r in csv.DictReader(open(REF, encoding="utf-8-sig"))}

    # --- A) errores verificados del conversor, situados en la geometria ---
    errores = []
    for cid, v in sorted(ver.items()):
        m = mapa[cid]
        det = {lab: d for d, lab in m["etiquetas"].items()}[v["etiqueta_erronea"]]
        if det != "conv": continue
        inst = m["instante_s"]
        errores.append({"caso": cid, "grabacion": m["grabacion"], "tipo": v["cat"],
                        "instante_s": inst, "motivo": v["motivo"],
                        "zona": "antes del tramo (<90 s)" if inst < T0 else
                                ("en la cola" if inst >= CUT - TAIL_TRIM - TAIL_S
                                 else "en el tramo, fuera de la cola")})

    E = list(csv.DictReader(open(OUT / "emparejamiento.csv", encoding="utf-8-sig")))
    ok = [r for r in E if r.get("estado") == "ok"]

    # --- B) efecto por grabacion y denominador de latidos en el tramo ---
    efectos, n_tramo_tot = [], 0
    for r in ok:
        rec = r["grabacion"]
        g = sorted(glob.glob(str(RESP / rec / "ENDURANCE_*_RR.CSV")))
        if not g: continue
        rr, idx, dur, t = load_rr_csv(g[0])
        base = geometria(rr, idx, dur, t)
        n_tramo_tot += int(((t >= T0) & (t <= dur - TAIL_TRIM)).sum())
        mine = [e for e in errores if e["grabacion"] == rec]
        rr_c, t_c, idx_c = rr.copy(), t.copy(), idx.copy()
        for e in mine:
            if e["instante_s"] > CUT: continue
            i = int(np.searchsorted(t_c, e["instante_s"]))
            if i >= len(rr_c) - 1: continue
            rr_c, t_c, idx_c = simula(rr_c, t_c, idx_c, i,
                                      "omision" if e["tipo"] == "EXTRA" else "extra")
        corr = geometria(rr_c, idx_c, dur, t_c)
        efectos.append({"grabacion": rec, "n_errores_conversor": len(mine),
                        "errores_en_tramo": sum(1 for e in mine if e["zona"] != "antes del tramo (<90 s)"),
                        "RMSSD_tramo": round(base["RMSSD"], 3), "RMSSD_tramo_corr": round(corr["RMSSD"], 3),
                        "RMSSD_cola": round(base["RMSSD_cola"], 3), "RMSSD_cola_corr": round(corr["RMSSD_cola"], 3),
                        "tail_mismatch_pct": round(base["tmm"], 3),
                        "tail_mismatch_pct_corr": round(corr["tmm"], 3),
                        "delta_tmm": round(corr["tmm"] - base["tmm"], 3),
                        "n_tramo": base["n_tramo"], "n_cola": base["n_cola"]})

    err_tramo = [e for e in errores if e["zona"] != "antes del tramo (<90 s)"]

    def wilson(k, n, z=1.96):
        if n == 0: return (0.0, 1.0)
        p = k / n; d = 1 + z * z / n
        c = (p + z * z / (2 * n)) / d
        h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
        return (max(0.0, c - h), min(1.0, c + h))
    lo, hi = wilson(len(err_tramo), n_tramo_tot)

    # --- validacion: reproduccion exacta de la copia H3S90T375 ---
    rrf = {}
    for f in glob.glob(str(WORK / "*")):
        m2 = re.search(r"(\d{4}-\d{2}-\d{2})", f)
        if m2: rrf[m2.group(1)] = f
    difs = []
    for d, f in sorted(rrf.items()):
        if d not in ref: continue
        try: r0 = float(ref[d]["tail_mismatch_pct"])
        except (TypeError, ValueError): continue
        rr, idx, dur, t = load_rr_csv(f)
        g = geometria(rr, idx, dur, t)
        if g["tmm"] == g["tmm"]: difs.append(abs(g["tmm"] - r0))
    val = {"n": len(difs), "max_dif": round(float(np.max(difs)), 8) if difs else None,
           "exactos_pct": round(float(np.mean(np.array(difs) < 0.1) * 100), 2) if difs else None}

    # --- C) SENSIBILIDAD, separada. Dos sustratos declarados ---
    D = list(csv.DictReader(open(OUT.parent / "hg04_evidencia_mismatch_veto_2026-10-25/recuperados_29_diagnostico.csv",
                                 encoding="utf-8-sig")))
    recuperados = {d["Fecha"] for d in D}
    limpios = {d for d in rrf if d in ref and "STAB_LAST2_MISMATCH" not in (ref[d].get("Flags") or "")}

    sens = []
    for sustrato, dias in (("29 recuperados (ya >=15%)", recuperados), ("dias limpios (<15%)", limpios)):
        for dia in sorted(dias):
            if dia not in rrf: continue
            rr, idx, dur, t = load_rr_csv(rrf[dia])
            base = geometria(rr, idx, dur, t)
            if base["tmm"] != base["tmm"]: continue
            if sustrato.startswith("dias limpios") and base["tmm"] >= 15: continue
            t_end = dur - TAIL_TRIM; tail0 = t_end - TAIL_S
            sel = np.where((t >= T0) & (t <= t_end))[0]
            if sel.size < 20: continue
            for i in sel[np.linspace(0, sel.size - 1, 15).astype(int)]:
                if i >= len(rr) - 2: continue
                for tipo in ("omision", "extra", "ectopico15", "ectopico25"):
                    r2, t2, i2 = simula(rr, t, idx, int(i), tipo)
                    g = geometria(r2, i2, dur, t2)
                    if g["tmm"] != g["tmm"]: continue
                    sens.append({"sustrato": sustrato, "Fecha": dia, "tipo": tipo,
                                 "pos_s": round(float(t[i]), 1),
                                 "zona": "cola" if t[i] >= tail0 else "tramo fuera de cola",
                                 "tmm_base": round(base["tmm"], 3), "tmm_sim": round(g["tmm"], 3),
                                 "delta": round(g["tmm"] - base["tmm"], 3),
                                 "cruza_15": bool(base["tmm"] < 15 <= g["tmm"])})

    for nm, rows in (("errores_verificados.csv", errores), ("efecto_por_grabacion.csv", efectos),
                     ("sensibilidad_simulada.csv", sens)):
        with open(OUT / nm, "w", newline="", encoding="utf-8-sig") as fh:
            w = csv.DictWriter(fh, fieldnames=list(rows[0])); w.writeheader(); [w.writerow(x) for x in rows]

    res = {"fecha": "2026-10-26", "semilla": SEED,
           "protocolo_sha256": sha(ROOT / "research/reports/hg04_protocolo_errores_rr_2026-10-26.md"),
           "veredicto_ciego_sha256": sha(OUT / "veredicto_ciego.json"),
           "validacion_copia_H3S90T375": val,
           "grabaciones_utilizables": len(ok), "latidos_en_tramo": n_tramo_tot,
           "errores_conversor_total": len(errores), "errores_conversor_en_tramo": len(err_tramo),
           "tasa_en_tramo_por_1000": round(len(err_tramo) / n_tramo_tot * 1000, 4) if n_tramo_tot else None,
           "wilson95_por_1000": [round(lo * 1000, 4), round(hi * 1000, 4)],
           "errores": errores, "efectos": efectos, "sensibilidad_n": len(sens)}
    RES.parent.mkdir(parents=True, exist_ok=True)
    RES.write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")

    print(f"=== validacion contra copia H3S90T375: n={val['n']}  max dif {val['max_dif']}  "
          f"exactos {val['exactos_pct']}% ===")
    print("\n=== A) errores verificados del CONVERSOR ===")
    for e in errores:
        print(f"  {e['caso']} {e['tipo']:6s} t={e['instante_s']:7.2f}s  {e['zona']:32s} {e['grabacion']}")
    print(f"\n  dentro del tramo [90, {CUT-TAIL_TRIM:.0f}] s: {len(err_tramo)} de {len(errores)}")
    print(f"  latidos del conversor en el tramo: {n_tramo_tot}")
    print(f"  tasa: {len(err_tramo)/n_tramo_tot*1000:.3f}/1000  (Wilson 95%: {lo*1000:.3f} - {hi*1000:.3f})")
    print("\n=== B) efecto de la correccion trazable ===")
    print(f"{'grabacion':32s} {'err':>3s} {'tmm':>7s} {'corr':>7s} {'delta':>7s}")
    for e in efectos:
        print(f"{e['grabacion']:32s} {e['n_errores_conversor']:3d} {e['tail_mismatch_pct']:7.2f} "
              f"{e['tail_mismatch_pct_corr']:7.2f} {e['delta_tmm']:7.2f}")
    print("\n=== C) sensibilidad simulada ===")
    for sustrato in ("29 recuperados (ya >=15%)", "dias limpios (<15%)"):
        print(f"\n  [{sustrato}]")
        for tipo in ("omision", "extra", "ectopico15", "ectopico25"):
            for zona in ("tramo fuera de cola", "cola"):
                s = [x for x in sens if x["sustrato"] == sustrato and x["tipo"] == tipo and x["zona"] == zona]
                if not s: continue
                dl = np.array([x["delta"] for x in s]); cz = sum(x["cruza_15"] for x in s)
                print(f"   {tipo:11s} {zona:20s} n={len(s):4d}  delta mediano {np.median(dl):+7.2f}  "
                      f"cruzan 15%: {cz:4d} ({cz/len(s)*100:5.1f}%)")
    print("\nJSON:", RES.relative_to(ROOT))


if __name__ == "__main__":
    main()
