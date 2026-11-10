"""HG-09B: selección determinista de casos y controles (protocolo §3). Solo metadatos del CORE.

Casos M: era ECG, único motivo STAB_LAST2_MISMATCH con la geometría candidata.
M2: LAT_NAN + MISMATCH. Controles C: 3 días OK de la era ECG más próximos en calendario por caso
(desempate al más antiguo, sin reutilizar), excluyendo M, M2, LAT_NAN e INVALID; reservas: los 2
siguientes por caso. Fechas > 2026-10-22: flag calculado con hg09b_motor sobre el RR de data/.
No abre ningún ECG. Salida: results/hg09b_seleccion_2026-10-27.json
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import hg09b_motor as motor  # noqa: E402

ROOT = motor.ROOT
A0 = ROOT / "out/hg04_copias_paralelas_2026-10-22/H3S90T375/ENDURANCE_HRV_master_CORE.csv"
CANON = ROOT / "data/ENDURANCE_HRV_master_CORE.csv"
PROTO = ROOT / "research/reports/hg09b_protocolo_evidencia_mismatch_2026-10-27.md"
OUT = HERE.parent / "results/hg09b_seleccion_2026-10-27.json"
FREEZE = "2026-10-27"
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()


def classify(df: pd.DataFrame) -> pd.Series:
    num = lambda c: pd.to_numeric(df[c], errors="coerce")
    lat = num("Tiempo_Estabilizacion").isna()
    mm = df.Stability_Subtype.eq("STAB_LAST2_MISMATCH")
    elig = (df.Calidad.eq("FLAG_mecánico") & num("Artifact_pct").le(15) & num("HR_stable").between(35, 100)
            & np.isfinite(num("RMSSD_stable")) & num("RMSSD_stable").gt(0) & np.isfinite(num("lnRMSSD")))
    return pd.Series(np.select([df.Calidad.eq("OK"), elig & ~lat & mm, elig & lat & mm, lat],
                               ["OK", "M", "M2", "LAT"], "OTRO"), index=df.index)


def main():
    a0 = pd.read_csv(A0)
    canon = pd.read_csv(CANON)
    extra = canon[(canon.Fecha > a0.Fecha.max()) & (canon.Fecha <= FREEZE)]
    rows = []
    for _, r in extra.iterrows():
        m = re.search(r"src=([^;]+)", str(r.Notes))
        p = ROOT / "data/rr_downloads" / m.group(1).strip() if m else None
        if p is None or not p.exists():
            continue
        row = motor.day_metrics(p, pd.concat([a0, pd.DataFrame(rows)], ignore_index=True))
        rows.append(row)
    full = pd.concat([a0, pd.DataFrame(rows)], ignore_index=True)
    full["era"] = np.where(full.Notes.astype(str).str.contains("from_jsonl"), "ECG", "Polar")
    full["grupo"] = classify(full)
    ecg = full[full.era.eq("ECG")].copy()
    ecg["dt"] = pd.to_datetime(ecg.Fecha)
    M = list(ecg.Fecha[ecg.grupo.eq("M")])
    M2 = list(ecg.Fecha[ecg.grupo.eq("M2")])
    pool = ecg[ecg.grupo.eq("OK")]
    used, controls, reserves = set(), {}, {}
    for d in M:
        dd = pd.Timestamp(d)
        cand = pool.assign(dist=(pool.dt - dd).abs().dt.days).sort_values(["dist", "dt"])
        cand = [f for f in cand.Fecha if f not in used]
        controls[d] = cand[:3]
        reserves[d] = cand[3:5]
        used.update(cand[:5])
    out = {
        "fecha": FREEZE, "protocolo": str(PROTO.relative_to(ROOT)).replace("\\", "/"), "protocolo_sha256": sha(PROTO),
        "motor": motor.fingerprints(), "a0_sha256": sha(A0),
        "n_era_ECG": int(len(ecg)), "grupos_era_ECG": ecg.grupo.value_counts().to_dict(),
        "M": M, "M2": M2, "controles": controls, "reservas": reserves,
        "fechas_posteriores_recalculadas": [r["Fecha"] for r in rows],
        "flags_posteriores": {r["Fecha"]: [r["Calidad"], r.get("Stability_Subtype")] for r in rows},
    }
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(out, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
