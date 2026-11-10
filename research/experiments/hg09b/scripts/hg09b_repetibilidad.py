"""HG-09B §5/§7.2: repetibilidad con grabaciones repetidas la misma mañana (geometría candidata).

Grabaciones: ZIP PolarRecording_* de data/rr_downloads/_audit/_audit_*/ y del
manifiesto HG09b en _source_jsonl_recovered/. ECG/ACC se leen de su _unzipped/.
Cada ECG se convierte con egc_to_rr.py (árbol de trabajo) en $HOME/hg09b_tmp y se calcula con el
motor de la geometría candidata. Pares = grabaciones consecutivas de la misma mañana.
Condiciones (postura, banda) NO documentadas: se infieren solo minutos entre grabaciones y ΔFC.
Salidas: results/hg09b_repetibilidad_2026-10-27.json; out/hg09b_casos_2026-10-27/repetibilidad_pares.csv
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import hg09b_motor as motor  # noqa: E402

ROOT = motor.ROOT
SOURCE_DIR = ROOT / "data/rr_downloads/_source_jsonl_recovered"
UNZ_DIR = SOURCE_DIR / "_unzipped"
MANIFEST = HERE.parent / "results/hg09b_descarga_manifest.json"
TMP = Path(os.path.expanduser("~")) / "hg09b_tmp/rep"
RES = HERE.parent / "results/hg09b_repetibilidad_2026-10-27.json"
OUTC = ROOT / "out/hg09b_casos_2026-10-27"
SWC = 0.1148449437374518
SEED = 20261027
sha = lambda b: hashlib.sha256(b).hexdigest()


def recordings():
    found = {}
    audit_zips = (p for b in (ROOT / "data/rr_downloads/_audit").glob("_audit_*") for p in b.rglob("*.zip"))
    selected = json.loads(MANIFEST.read_text(encoding="utf-8"))["ficheros"]
    source_zips = (SOURCE_DIR / item["fichero"] for item in selected)
    for p in (*audit_zips, *source_zips):
        m = re.search(r"PolarRecording_(\d{8})_(\d{6})", p.name, re.I)
        if not m:
            continue
        key = f"{m.group(1)}_{m.group(2)}"
        h = sha(p.read_bytes())
        found.setdefault(key, (p, h))
    return found


def convert(key, zp):
    d = TMP / key; d.mkdir(parents=True, exist_ok=True)
    out = d / "rr"; out.mkdir(exist_ok=True)
    if not list(out.glob("*.CSV")):
        ecg = next((p / "ECG.jsonl" for p in sorted(UNZ_DIR.glob(zp.stem + "_*")) if (p / "ECG.jsonl").exists()), None)
        if ecg is None:
            return None
        cmd = [sys.executable, "-B", str(ROOT / "egc_to_rr.py"), "--ecg", str(ecg), "--outdir", str(out), "--no-aux"]
        if (ecg.parent / "ACC.jsonl").exists():
            cmd[5:5] = ["--acc", str(ecg.parent / "ACC.jsonl")]
        subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
    g = sorted(out.glob("*.CSV"))
    return g[0] if g else None


def main():
    recs = recordings()
    rows = []
    for key, (zp, h) in sorted(recs.items()):
        rr = convert(key, zp)
        if rr is None:
            rows.append({"grabacion": key, "estado": "sin conversión"}); continue
        dur = pd.to_numeric(pd.read_csv(rr).duration, errors="coerce").sum() / 1000
        try:
            r = motor.day_metrics(rr)
        except Exception as e:  # noqa: BLE001
            rows.append({"grabacion": key, "estado": f"error {type(e).__name__}"}); continue
        lat = r.get("Tiempo_Estabilizacion")
        rows.append({"grabacion": key, "fecha": f"{key[:4]}-{key[4:6]}-{key[6:8]}", "hora": key[9:15], "zip_sha256": h, "estado": "ok",
                     "dur_s": round(float(dur), 1), "lnRMSSD": r["lnRMSSD"], "HR": r["HR_stable"], "tail_pct": r["tail_mismatch_pct"],
                     "Calidad": r["Calidad"], "subtipo": r["Stability_Subtype"], "lat_nan": lat is None or (isinstance(lat, float) and np.isnan(lat)),
                     "Artifact_pct": r["Artifact_pct"]})
    g = pd.DataFrame(rows)
    ok = g[g.estado.eq("ok") & (g.dur_s >= 375)].copy()
    ok["flag"] = np.where(ok.subtipo.eq("STAB_LAST2_MISMATCH"), "MISMATCH", np.where(ok.Calidad.eq("OK"), "OK", "OTRO"))
    pairs = []
    for f, s in ok.sort_values("hora").groupby("fecha"):
        s = s.sort_values("hora").reset_index(drop=True)
        for i in range(len(s) - 1):
            a, b = s.iloc[i], s.iloc[i + 1]
            ta = datetime.strptime(a.hora, "%H%M%S"); tb = datetime.strptime(b.hora, "%H%M%S")
            pairs.append({"fecha": f, "orden": i + 1, "min_entre": round((tb - ta).seconds / 60, 1),
                          "flag_a": a.flag, "flag_b": b.flag, "tail_a": a["tail_pct"], "tail_b": b["tail_pct"],
                          "dln": float(b.lnRMSSD - a.lnRMSSD), "abs_dln": abs(float(b.lnRMSSD - a.lnRMSSD)),
                          "dHR": float(b.HR - a.HR), "cambio_real_probable": abs(float(b.HR - a.HR)) > 3})
    P = pd.DataFrame(pairs)
    P["con_mismatch"] = P.flag_a.eq("MISMATCH") | P.flag_b.eq("MISMATCH")
    P["ok_ok"] = P.flag_a.eq("OK") & P.flag_b.eq("OK")
    nmm, nok = int(P.con_mismatch.sum()), int(P.ok_ok.sum())
    res = {"n_grabaciones": int(len(g)), "n_utilizables_375": int(len(ok)), "n_mananas": int(ok.fecha.nunique()), "n_pares": int(len(P)),
           "pares_con_mismatch": nmm, "pares_ok_ok": nok,
           "acuerdo_flag": {f"{a}->{b}": int(n) for (a, b), n in P.groupby(["flag_a", "flag_b"]).size().items()},
           "mediana_abs_dln_con_mismatch": float(P[P.con_mismatch].abs_dln.median()) if nmm else None,
           "mediana_abs_dln_ok_ok": float(P[P.ok_ok].abs_dln.median()) if nok else None,
           "mediana_abs_dtail": float((P.tail_b - P.tail_a).abs().median()),
           "pares_con_dHR_gt3": int(P.cambio_real_probable.sum()),
           "regla_7_2": "INSUFICIENTE (<4 pares con MISMATCH)" if nmm < 4 else "evaluar",
           "nota": "Grabaciones secuenciales: no separan error de medida de cambio real; condiciones no documentadas."}
    if nmm >= 4 and nok >= 2:
        rng = np.random.default_rng(SEED)
        a = P[P.con_mismatch].abs_dln.to_numpy(); b = P[P.ok_ok].abs_dln.to_numpy()
        bs = [np.median(rng.choice(a, a.size)) - np.median(rng.choice(b, b.size)) for _ in range(10000)]
        lo, hi = np.percentile(bs, [2.5, 97.5])
        exc = np.median(a) - np.median(b)
        res["exceso_mediana"] = float(exc); res["IC95"] = [float(lo), float(hi)]
        res["regla_7_2"] = ("FAVORABLE A MANTENER" if exc >= 0.5 * SWC and lo > 0 else
                            "FAVORABLE A INCLUIR" if hi < 0.5 * SWC else "INSUFICIENTE")
    RES.write_text(json.dumps({"fecha": "2026-10-27", "motor": motor.fingerprints(), **res}, ensure_ascii=False, indent=1), encoding="utf-8")
    OUTC.mkdir(parents=True, exist_ok=True)
    P.to_csv(OUTC / "repetibilidad_pares.csv", index=False, encoding="utf-8-sig")
    g.to_csv(OUTC / "repetibilidad_grabaciones.csv", index=False, encoding="utf-8-sig")
    print(json.dumps(res, ensure_ascii=False, indent=1))
    print(P.round(3).to_string(index=False))
    print(g[["grabacion", "estado", "dur_s", "subtipo", "tail_pct"]].to_string(index=False) if "dur_s" in g else g)


if __name__ == "__main__":
    main()
