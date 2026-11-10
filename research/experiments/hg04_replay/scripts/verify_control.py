"""Verifica los cuatro outputs del control y resume el brazo HG-03 en copia aislada.

Uso: python verify_control.py --work <directorio_temporal_del_replay>
No escribe en data/ ni copia RR personales al repositorio.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from datetime import date
from pathlib import Path

from review_audit import OUTPUTS, compare_frames, read_dated


ROOT = Path(__file__).resolve().parents[4]


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def summarize_comparison(detail: dict, *, include_dates: bool) -> dict:
    summary = {
        "parity": detail["parity"],
        "column_order_equal": detail["column_order_equal"],
        "only_control_dates": detail["only_control_dates"],
        "only_comparison_dates": detail["only_production_dates"],
        "only_control_columns": detail["only_control_columns"],
        "only_comparison_columns": detail["only_production_columns"],
        "different_day_count_by_column": {
            column: len(dates) for column, dates in detail["differing_dates_by_column"].items()
        },
        "changed_days_total": len({d for days in detail["differing_dates_by_column"].values() for d in days}),
        "numeric_tolerance": detail["numeric_tolerance"],
    }
    if include_dates:
        summary["different_dates_by_column"] = detail["differing_dates_by_column"]
    else:
        summary["gate_final_changed_dates"] = detail["differing_dates_by_column"].get("gate_final", [])
    return summary


def verify(work: Path, production: Path) -> dict:
    report = {
        "date": date.today().isoformat(),
        "scope": "Full date/column comparison of control replay C with production, and H3 with C if present",
        "locations": "C and H3 in an isolated local work directory; production from data/ (not copied into this report)",
        "builder_sha256": digest(ROOT / "build_hrv_core.py"),
        "outputs": {},
    }
    for output in OUTPUTS:
        filename = f"ENDURANCE_HRV_master_{output}.csv"
        c_path = work / "C" / "data" / filename
        p_path = production / filename
        c, p = read_dated(c_path), read_dated(p_path)
        item = {
            "n_control_rows": len(c),
            "n_production_rows": len(p),
            "control_sha256": digest(c_path),
            "production_sha256": digest(p_path),
            "control_vs_production": summarize_comparison(compare_frames(c, p), include_dates=True),
        }
        h_path = work / "H3" / "data" / filename
        if h_path.exists():
            h = read_dated(h_path)
            item["h3_sha256"] = digest(h_path)
            item["h3_vs_control"] = summarize_comparison(compare_frames(c, h), include_dates=False)
        report["outputs"][output] = item
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work", type=Path, default=Path(os.environ.get("HG04_REPLAY_WORK", Path.home() / "hg04_replay_work")))
    parser.add_argument("--production", type=Path, default=ROOT / "data")
    parser.add_argument("--output", type=Path, default=ROOT / "research/experiments/hg04_replay/results/control_verification.json")
    args = parser.parse_args()
    report = verify(args.work.resolve(), args.production.resolve())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    for name, item in report["outputs"].items():
        cp = item["control_vs_production"]
        print(name, "C/production:", "parity" if cp["parity"] else "differences", cp["changed_days_total"], "days")
        if "h3_vs_control" in item:
            h3 = item["h3_vs_control"]
            print(name, "H3/C:", h3["changed_days_total"], "days; gate_final:", len(h3["gate_final_changed_dates"]))
    print("Report:", args.output)


if __name__ == "__main__":
    main()
