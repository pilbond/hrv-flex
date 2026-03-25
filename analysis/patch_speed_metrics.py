#!/usr/bin/env python3
"""Parchea los session_payload.json existentes con métricas de velocidad del FIT.

Uso:
    python analysis/patch_speed_metrics.py
    python analysis/patch_speed_metrics.py --slug 2026-03-14_11-55_road_run_i131932523

El script lee artifacts/session.fit de cada sesión, extrae velocidad media y
por bloque de trabajo (reconstruidos desde el stream HR + VT1), y añade el
campo speed_metrics al session_payload.json de forma atómica.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ANALYSIS_DIR = Path(__file__).resolve().parent
for _p in (str(ROOT), str(ANALYSIS_DIR)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from fit_speed_utils import compute_speed_metrics  # noqa: E402

REPORTS_DIR = ANALYSIS_DIR / "reports"

# Sesiones a parchear (en orden cronológico)
TARGET_SLUGS = [
    "2026-03-14_11-55_road_run_i131932523",
    "2026-03-15_16-38_bike_i132252950",
    "2026-03-17_14-09_trail_run_i132739221",
    "2026-03-18_13-45_bike_i133012203",
    "2026-03-19_14-25_trail_run_i133273117",
]


def _parse_float(value: str | None) -> float | None:
    if value is None:
        return None
    try:
        return float(str(value).strip())
    except (ValueError, TypeError):
        return None


def patch_session(slug: str, dry_run: bool = False) -> dict:
    """Parchea un session_payload.json con speed_metrics.

    Returns:
        Resumen del resultado (dict con status, avg_speed, etc.)
    """
    year, month = slug[:4], slug[5:7]
    artifacts = REPORTS_DIR / year / month / slug / "artifacts"
    payload_path = artifacts / "session_payload.json"
    fit_path = artifacts / "session.fit"

    if not payload_path.exists():
        return {"slug": slug, "status": "SKIP", "reason": "payload not found"}
    if not fit_path.exists():
        return {"slug": slug, "status": "SKIP", "reason": "session.fit not found"}

    payload = json.loads(payload_path.read_text(encoding="utf-8"))
    session_row = payload.get("session_row", {})
    sport_family = payload.get("meta", {}).get("sport_family", "road")

    vt1_bpm = _parse_float(session_row.get("vt1_used"))
    wbm = session_row.get("work_blocks_min") or ""
    work_blocks_n = len([x for x in wbm.split(";") if x.strip()]) if wbm else 0

    speed_metrics = compute_speed_metrics(fit_path, vt1_bpm, work_blocks_n, sport_family)

    if speed_metrics is None:
        return {"slug": slug, "status": "FAIL", "reason": "FIT parse failed or fitparse not installed"}

    if not dry_run:
        payload["speed_metrics"] = speed_metrics
        tmp = payload_path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        tmp.replace(payload_path)

    return {
        "slug": slug,
        "status": "OK" if not dry_run else "DRY_RUN",
        "avg_speed_kmh": speed_metrics.get("avg_speed_kmh"),
        "avg_pace_min_km": speed_metrics.get("avg_pace_min_km"),
        "blocks_matched": speed_metrics.get("blocks_matched"),
        "work_blocks_n": work_blocks_n,
        "work_blocks_speed_kmh": speed_metrics.get("work_blocks_speed_kmh"),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--slug", help="Parchear solo una sesión concreta")
    parser.add_argument("--dry-run", action="store_true", help="No escribir; solo mostrar resultados")
    args = parser.parse_args()

    slugs = [args.slug] if args.slug else TARGET_SLUGS

    print(f"{'DRY RUN — ' if args.dry_run else ''}Parcheando {len(slugs)} sesión(es)...\n")

    for slug in slugs:
        result = patch_session(slug, dry_run=args.dry_run)
        status = result["status"]
        if status in ("OK", "DRY_RUN"):
            spd = result["avg_speed_kmh"]
            pace = result.get("avg_pace_min_km")
            matched = result["blocks_matched"]
            wbn = result["work_blocks_n"]
            blk_speeds = result.get("work_blocks_speed_kmh")
            speed_str = f"{spd} km/h" + (f"  ({pace} min/km)" if pace else "")
            blocks_str = f"{wbn} bloques, matched={matched}, speeds={blk_speeds}"
            print(f"[{status}] {slug}")
            print(f"       velocidad media: {speed_str}")
            print(f"       bloques:         {blocks_str}")
        else:
            print(f"[{status}] {slug}  — {result.get('reason', '')}")
        print()


if __name__ == "__main__":
    main()
