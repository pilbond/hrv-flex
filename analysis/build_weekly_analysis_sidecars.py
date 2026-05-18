from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from analysis import sya15_continuity


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_WEEKLY_REPORTS_DIR = ROOT / "analysis" / "reports" / "weekly"


def weekly_bounds(today) -> tuple:
    week_start = sya15_continuity.current_week_start(today)
    week_end = week_start + pd.Timedelta(days=6)
    return week_start, week_end


def default_out_dir(today) -> Path:
    week_start, week_end = weekly_bounds(today)
    return DEFAULT_WEEKLY_REPORTS_DIR / f"{week_start.date()}_{week_end.date()}" / "artifacts"


def _slugify_part(value: str) -> str:
    return "".join(char if char.isalnum() else "_" for char in value.strip().lower()).strip("_")


def build_sya15_artifact_stem(*, focus_sport: str, window_size: int, min_positive: int) -> str:
    sport_slug = _slugify_part(focus_sport)
    return f"sya15_continuity_{sport_slug}_{min_positive}of{window_size}w"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build local weekly-analysis sidecars under analysis/reports/weekly/."
    )
    parser.add_argument("--today", type=str, default=None, help="Optional YYYY-MM-DD anchor date.")
    parser.add_argument("--out-dir", type=Path, default=None, help="Optional output directory for weekly sidecars.")
    parser.add_argument(
        "--input",
        type=Path,
        default=sya15_continuity.DEFAULT_INPUT,
        help="Path to ENDURANCE_HRV_intensity_distribution_weekly.csv for SYA-15.",
    )
    parser.add_argument(
        "--focus-sport",
        type=str,
        default=None,
        help="Optional sport to focus the SYA-15 weekly sidecar on.",
    )
    parser.add_argument(
        "--window-size",
        type=int,
        default=sya15_continuity.WINDOW_SIZE,
        help="Rolling window size for SYA-15. Must be at least 2.",
    )
    parser.add_argument(
        "--min-positive",
        type=int,
        default=None,
        help="Optional minimum number of positive weeks required inside the rolling window.",
    )
    return parser


def build_sya15_weekly_sidecar(
    *,
    today,
    out_dir: Path,
    input_path: Path,
    focus_sport: str | None,
    window_size: int,
    min_positive: int | None,
) -> dict[str, object]:
    sya15_continuity.validate_report_window_size(window_size)
    weekly = sya15_continuity.load_weekly(input_path)
    resolved_min_positive = sya15_continuity._resolve_min_positive_unchecked(window_size, min_positive)
    summary, details = sya15_continuity._summarize_by_sport_validated(
        weekly,
        today,
        window_size,
        resolved_min_positive,
    )
    report_focus_sport = sya15_continuity.resolve_report_focus_sport(summary, focus_sport)
    artifact_stem = build_sya15_artifact_stem(
        focus_sport=report_focus_sport,
        window_size=window_size,
        min_positive=resolved_min_positive,
    )

    out_dir.mkdir(parents=True, exist_ok=True)
    report_md_path = out_dir / f"{artifact_stem}.md"
    report_json_path = out_dir / f"{artifact_stem}.json"

    report_md = sya15_continuity._build_sport_report_validated(
        report_focus_sport,
        summary,
        details,
        today,
        input_path,
        window_size,
        resolved_min_positive,
    )
    report_payload = sya15_continuity._build_report_payload_validated(
        report_focus_sport,
        summary,
        details,
        today,
        input_path,
        window_size,
        resolved_min_positive,
    )

    report_md_path.write_text(report_md, encoding="utf-8")
    report_json_path.write_text(
        json.dumps(report_payload, indent=2, ensure_ascii=False, allow_nan=False),
        encoding="utf-8",
    )

    week_start, week_end = weekly_bounds(today)
    return {
        "week_start": week_start.date().isoformat(),
        "week_end": week_end.date().isoformat(),
        "anchor_date": today.date().isoformat(),
        "sidecar": "sya15_continuity",
        "focus_sport": report_focus_sport,
        "window_size": window_size,
        "min_positive": resolved_min_positive,
        "artifact_stem": artifact_stem,
        "report_md": str(report_md_path),
        "report_json": str(report_json_path),
    }


def main() -> int:
    args = build_parser().parse_args()
    today = sya15_continuity.resolve_today(args.today)
    out_dir = args.out_dir if args.out_dir is not None else default_out_dir(today)

    payload = build_sya15_weekly_sidecar(
        today=today,
        out_dir=out_dir,
        input_path=args.input,
        focus_sport=args.focus_sport,
        window_size=args.window_size,
        min_positive=args.min_positive,
    )
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
