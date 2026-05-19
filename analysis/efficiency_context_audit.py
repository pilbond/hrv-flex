#!/usr/bin/env python3
"""Regenerate the local efficiency-context audit from `analysis/reports`.

The emitted CSV stores `summary_path` and `matched_climbs_path` relative to the
`reports_root` passed on the command line. The `threshold_gap_flags` column is
pipe-delimited (`|`) so it can be round-tripped without embedding JSON.
Use `strict=False` only when you want to keep rows with missing
`matched_climbs.csv` sidecars and inspect the gap separately; the default
`strict=True` mode fails fast on missing sidecars.
"""
from __future__ import annotations

import argparse
import csv
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from analysis.fit_terrain_utils import _build_efficiency_audit

REPORTS_ROOT = ROOT / "analysis" / "reports"


def _read_json(path: Path) -> dict[str, Any] | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _sport_label(summary: dict[str, Any], fallback_slug: str) -> str:
    session_meta = summary.get("session_meta") or {}
    sport = session_meta.get("sport")
    family = session_meta.get("sport_family") or (summary.get("efficiency_context") or {}).get("sport_family")
    if sport == "running":
        return "trail_run" if family == "trail" else "road_run" if family == "road" else "running"
    if sport:
        return str(sport)
    if family:
        return str(family)
    return fallback_slug


def _build_audit_from_summary(summary: dict[str, Any]) -> dict[str, Any]:
    efficiency_context = summary.get("efficiency_context") or {}
    aggregate = efficiency_context.get("aggregate") or {}
    vam = aggregate.get("vam_ratio")
    hr = aggregate.get("hr_drift_bpm")
    cost = aggregate.get("hr_per_vam_ratio")
    audit = efficiency_context.get("efficiency_audit") or _build_efficiency_audit(
        vam if isinstance(vam, (int, float)) else None,
        hr if isinstance(hr, (int, float)) else None,
        cost if isinstance(cost, (int, float)) else None,
        efficiency_context.get("efficiency_pattern"),
    )
    return audit


def collect_rows(reports_root: Path = REPORTS_ROOT, *, strict: bool = True) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    missing_sidecars: list[Path] = []
    for summary_path in sorted(reports_root.rglob("summary.json")):
        summary = _read_json(summary_path)
        if not summary:
            continue
        efficiency_context = summary.get("efficiency_context") or {}
        if not efficiency_context.get("applicable"):
            continue
        aggregate = efficiency_context.get("aggregate") or {}
        vam = aggregate.get("vam_ratio")
        hr = aggregate.get("hr_drift_bpm")
        cost = aggregate.get("hr_per_vam_ratio")
        audit = _build_audit_from_summary(summary)
        pattern = efficiency_context.get("efficiency_pattern")
        threshold_gap_flags = audit.get("threshold_gap_flags") or []
        mixed_signal_type = audit.get("mixed_signal_type")
        matched_climbs_path = summary_path.parent / "matched_climbs.csv"
        if not matched_climbs_path.exists():
            missing_sidecars.append(matched_climbs_path)
        rows.append(
            {
                "slug": summary_path.parent.parent.name,
                "sport_family": _sport_label(summary, summary_path.parent.parent.name),
                "summary_path": summary_path.relative_to(reports_root).as_posix(),
                "matched_climbs_path": matched_climbs_path.relative_to(reports_root).as_posix(),
                "matched_climbs_exists": matched_climbs_path.exists(),
                "pattern": pattern,
                "interpretation_confidence": efficiency_context.get("interpretation_confidence"),
                "vam_ratio": vam,
                "hr_drift_bpm": hr,
                "hr_per_vam_ratio": cost,
                "vam_bucket": audit["buckets"]["vam_ratio"],
                "hr_bucket": audit["buckets"]["hr_drift_bpm"],
                "cost_bucket": audit["buckets"]["hr_per_vam_ratio"],
                "signal_profile": audit.get("signal_profile"),
                "mixed_signal_type": mixed_signal_type,
                "threshold_gap_flags": threshold_gap_flags,
                "threshold_gap_count": len(threshold_gap_flags),
            }
        )
    if strict and missing_sidecars:
        missing_text = "\n".join(str(path) for path in missing_sidecars)
        raise FileNotFoundError(f"missing matched_climbs.csv sidecars:\n{missing_text}")
    return rows


def build_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    pattern_counts = Counter(row["pattern"] for row in rows)
    mixed_rows = [row for row in rows if row["pattern"] == "mixed_signal"]
    mixed_type_counts = Counter(row["mixed_signal_type"] for row in mixed_rows)
    profile_counts = Counter(row["signal_profile"] for row in mixed_rows)
    by_sport = defaultdict(Counter)
    for row in mixed_rows:
        by_sport[row["sport_family"]][row["mixed_signal_type"]] += 1
    return {
        "total_applicable": len(rows),
        "pattern_counts": dict(pattern_counts),
        "mixed_signal_counts": {
            "by_type": dict(mixed_type_counts),
            "by_profile": dict(profile_counts),
            "by_sport_family": {sport: dict(counts) for sport, counts in by_sport.items()},
        },
    }


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "slug",
        "sport_family",
        "summary_path",
        "matched_climbs_path",
        "matched_climbs_exists",
        "pattern",
        "interpretation_confidence",
        "vam_ratio",
        "hr_drift_bpm",
        "hr_per_vam_ratio",
        "vam_bucket",
        "hr_bucket",
        "cost_bucket",
        "signal_profile",
        "mixed_signal_type",
        "threshold_gap_flags",
        "threshold_gap_count",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            payload = dict(row)
            payload["threshold_gap_flags"] = "|".join(payload.get("threshold_gap_flags") or [])
            writer.writerow(payload)


def main() -> int:
    parser = argparse.ArgumentParser(description="Regenerate the efficiency-context audit from analysis/reports")
    parser.add_argument("--reports-root", type=Path, default=REPORTS_ROOT)
    parser.add_argument("--json-output", type=Path, default=None)
    parser.add_argument("--csv-output", type=Path, default=None)
    args = parser.parse_args()

    rows = collect_rows(args.reports_root, strict=True)
    summary = build_summary(rows)
    payload = {"summary": summary, "rows": rows}

    if args.json_output:
        args.json_output.parent.mkdir(parents=True, exist_ok=True)
        args.json_output.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    if args.csv_output:
        write_csv(args.csv_output, rows)

    print(json.dumps(payload["summary"], indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
