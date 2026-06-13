#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AYO-13 Fase 3: reporte de solo lectura del sidecar shadow Polar v4 (AYO-19).

Lee `data/audit/polar_v4_shadow.jsonl` (escrito por
`hrv_app.polar_shadow.run_polar_v4_shadow` cuando `POLAR_API_VERSION=shadow`)
y resume presencia, diffs, latencia y refreshes por dominio.

No escribe nada; uso exclusivamente diagnostico durante la ventana de
observacion de 7-14 dias.

Uso:
    python scripts/shadow_report.py
    python scripts/shadow_report.py --last 7
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from hrv_app.polar_shadow import SHADOW_PATH  # noqa: E402

DOMAINS = ("sleep", "nightly", "sessions")


def _load_records(path: Path) -> list[dict]:
    if not path.exists():
        return []
    records = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return records


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--last", type=int, default=14, help="Numero de registros recientes a incluir (default 14)")
    parser.add_argument("--path", default=str(SHADOW_PATH), help="Ruta al sidecar JSONL")
    args = parser.parse_args()

    path = Path(args.path)
    records = _load_records(path)
    if not records:
        print(f"Sin datos en {path}")
        return 0

    records = records[-args.last:] if args.last > 0 else records
    print(f"Shadow Polar v4 — {len(records)} registro(s) de {path}")
    print()

    status_counts = {d: defaultdict(int) for d in DOMAINS}
    latencies = {d: [] for d in DOMAINS}
    diff_dates = {d: [] for d in DOMAINS}
    refresh_count = 0

    for rec in records:
        date_str = rec.get("date", "?")
        doms = rec.get("domains", {})
        parts = [date_str]
        for d in DOMAINS:
            info = doms.get(d, {})
            status = info.get("status", "?")
            v3p = info.get("v3_present")
            v4p = info.get("v4_present")
            diff = info.get("diff") or {}
            status_counts[d][status] += 1
            if isinstance(info.get("latency_ms"), (int, float)):
                latencies[d].append(info["latency_ms"])
            if info.get("refreshed"):
                refresh_count += 1
            if diff:
                diff_dates[d].append(date_str)
            parts.append(f"{d}: {status} v3={v3p} v4={v4p} diff={len(diff)}")
        print(" | ".join(parts))

    print()
    print("Resumen:")
    for d in DOMAINS:
        total = sum(status_counts[d].values())
        ok = status_counts[d].get("ok", 0)
        other = {k: v for k, v in status_counts[d].items() if k != "ok"}
        line = f"  {d}: {ok}/{total} ok"
        if other:
            line += " (" + ", ".join(f"{k}={v}" for k, v in sorted(other.items())) + ")"
        if latencies[d]:
            avg = sum(latencies[d]) / len(latencies[d])
            line += f", latencia media {avg:.0f} ms"
        if diff_dates[d]:
            line += f", diffs en {len(diff_dates[d])} fecha(s): {', '.join(diff_dates[d])}"
        print(line)

    print(f"  refreshes detectados: {refresh_count}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
