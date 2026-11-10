"""Reproduce las ventanas alternativas de 120 s de HG-04 en los 10 días ECG auditados.

Exploratorio: lee los RR de la copia H3S90T375 sin modificarlos. Los resultados
describen esta muestra seleccionada por tail_mismatch_pct >= 15%; no prueban
que la cola tenga ni deje de tener una propiedad fisiológica especial.
"""
from __future__ import annotations

import argparse
import csv
import glob
import hashlib
import importlib.util
import json
from pathlib import Path

import numpy as np


ROOT = Path(__file__).resolve().parents[4]
SCRIPT = Path(__file__).with_name("hg04_rr_errors_effect_2026-10-26.py")
DATES = ROOT / "out/hg04_errores_rr_2026-10-26/ampliacion_10dias/clasificacion_10dias.csv"
MATCHES = ROOT / "out/hg04_errores_rr_2026-10-26/ampliacion_10dias/emparejamiento.csv"
DEFAULT_RESULTS = ROOT / "research/experiments/hg04_replay/results"


def load_effect_module():
    spec = importlib.util.spec_from_file_location("hg04_rr_effect", SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"No se puede cargar {SCRIPT}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rr-src", type=Path, default=Path.home() / "hg04_replay_work/rr_src")
    parser.add_argument("--results", type=Path, default=DEFAULT_RESULTS)
    args = parser.parse_args()

    eff = load_effect_module()
    dates = [r["Fecha"] for r in csv.DictReader(DATES.open(encoding="utf-8-sig"))]
    expected_hash = {
        r["fecha"]: r["rr_sha256"]
        for r in csv.DictReader(MATCHES.open(encoding="utf-8-sig"))
    }
    if len(dates) != 10 or len(set(dates)) != 10:
        raise ValueError("Se esperaban exactamente diez fechas distintas")

    windows: list[dict] = []
    days: list[dict] = []
    for date in dates:
        paths = sorted(glob.glob(str(args.rr_src / f"ENDURANCE_{date}_*RR*")))
        if len(paths) != 1:
            raise ValueError(f"RR no único para {date}: {paths}")
        rr_path = Path(paths[0])
        rr_hash = hashlib.sha256(rr_path.read_bytes()).hexdigest()
        if rr_hash != expected_hash.get(date):
            raise ValueError(f"RR distinto del auditado para {date}")
        rr, idx, dur_raw, times = eff.load_rr_csv(rr_path)
        geom = eff.geometria(rr, idx, dur_raw, times)
        whole = geom["RMSSD"]
        tail = geom["tmm"]
        if not np.isfinite(whole) or not np.isfinite(tail) or geom["t_end"] < 355:
            raise ValueError(f"Geometría no evaluable para {date}")

        mismatch = []
        for k in range(30):
            start = 90 + 5 * k
            end = start + 120
            selected = (times >= start) & (times <= end)
            value = eff.rmssd_ms(rr[selected], idx[selected])
            diff_pct = abs(value - whole) / whole * 100
            mismatch.append(diff_pct)
            windows.append({
                "fecha": date,
                "inicio_s": start,
                "fin_s": end,
                "n_rr_filtrados": int(selected.sum()),
                "rmssd_ventana_ms": round(value, 6),
                "rmssd_tramo_ms": round(whole, 6),
                "discordancia_pct": round(diff_pct, 6),
            })

        percentile = float(np.mean(np.asarray(mismatch) <= tail) * 100)
        days.append({
            "fecha": date,
            "rr_sha256": rr_hash,
            "n_ventanas_alternativas": len(mismatch),
            "rmssd_tramo_ms": round(whole, 6),
            "discordancia_cola_pct": round(tail, 6),
            "mediana_alternativas_pct": round(float(np.median(mismatch)), 6),
            "min_alternativas_pct": round(float(np.min(mismatch)), 6),
            "max_alternativas_pct": round(float(np.max(mismatch)), 6),
            "percentil_cola_en_alternativas": round(percentile, 6),
            "cola_en_decil_superior": int(percentile >= 90),
        })

    args.results.mkdir(parents=True, exist_ok=True)
    for filename, rows in (
        ("hg04_rr_ventanas_10dias_detalle_2026-10-26.csv", windows),
        ("hg04_rr_ventanas_10dias_resumen_2026-10-26.csv", days),
    ):
        with (args.results / filename).open("w", newline="", encoding="utf-8-sig") as fh:
            writer = csv.DictWriter(fh, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)

    summary = {
        "n_dias": len(days),
        "n_ventanas_alternativas_por_dia": 30,
        "rango_medianas_pct": [
            round(min(d["mediana_alternativas_pct"] for d in days), 2),
            round(max(d["mediana_alternativas_pct"] for d in days), 2),
        ],
        "percentil_medio_cola": round(float(np.mean([d["percentil_cola_en_alternativas"] for d in days])), 1),
        "colas_en_decil_superior": sum(d["cola_en_decil_superior"] for d in days),
        "advertencia": "Muestra seleccionada por la discordancia de la cola; 7/10 no es un contraste independiente.",
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
