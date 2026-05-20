from __future__ import annotations

import argparse
import json
from pathlib import Path

from analysis import build_weekly_analysis_sidecars
from analysis import sya15_continuity


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_WEEKLY_REPORTS_DIR = ROOT / "analysis" / "reports" / "weekly"


def default_weekly_dir(today) -> Path:
    week_start, week_end = build_weekly_analysis_sidecars.weekly_bounds(today)
    return DEFAULT_WEEKLY_REPORTS_DIR / f"{week_start.date()}_{week_end.date()}"


def default_manifest_path(today) -> Path:
    return default_weekly_dir(today) / "weekly_prep_manifest.json"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Prepare reproducible local artifacts for weekly analysis under analysis/reports/weekly/."
    )
    parser.add_argument("--today", type=str, default=None, help="Optional YYYY-MM-DD anchor date.")
    parser.add_argument(
        "--weekly-dir",
        type=Path,
        default=None,
        help="Optional weekly directory. Defaults to analysis/reports/weekly/<week_start>_<week_end>/.",
    )
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


def load_weekly_prep_manifest(path: Path) -> dict[str, object]:
    manifest = json.loads(path.read_text(encoding="utf-8"))
    if manifest.get("prep_kind") != "weekly_analysis_prep":
        raise ValueError(f"Invalid weekly prep manifest: {path}")
    if not isinstance(manifest.get("sidecars"), list):
        raise ValueError(f"weekly_prep_manifest sidecars must be a list: {path}")
    manifest["manifest_path"] = str(path)
    return manifest


def load_default_weekly_prep_manifest(today) -> dict[str, object]:
    manifest_path = default_manifest_path(today)
    if not manifest_path.exists():
        raise FileNotFoundError(f"Weekly prep manifest not found: {manifest_path}")
    return load_weekly_prep_manifest(manifest_path)


def iter_sidecars(manifest: dict[str, object], *, sidecar_name: str | None = None) -> list[dict[str, object]]:
    sidecars = manifest["sidecars"]
    if sidecar_name is None:
        return list(sidecars)
    return [sidecar for sidecar in sidecars if sidecar.get("sidecar") == sidecar_name]


def get_sidecar(manifest: dict[str, object], sidecar_name: str) -> dict[str, object]:
    matches = iter_sidecars(manifest, sidecar_name=sidecar_name)
    if not matches:
        raise KeyError(f"Sidecar not found in weekly prep manifest: {sidecar_name}")
    if len(matches) > 1:
        raise ValueError(f"Expected a single sidecar in weekly prep manifest: {sidecar_name}")
    return matches[0]


def build_weekly_prep(
    *,
    today,
    weekly_dir: Path,
    input_path: Path,
    focus_sport: str | None,
    window_size: int,
    min_positive: int | None,
) -> dict[str, object]:
    weekly_dir.mkdir(parents=True, exist_ok=True)
    artifacts_dir = weekly_dir / "artifacts"
    sidecars: list[dict[str, object]] = []

    sya15_sidecar = build_weekly_analysis_sidecars.build_sya15_weekly_sidecar(
        today=today,
        out_dir=artifacts_dir,
        input_path=input_path,
        focus_sport=focus_sport,
        window_size=window_size,
        min_positive=min_positive,
    )
    sidecars.append(sya15_sidecar)

    week_start, week_end = build_weekly_analysis_sidecars.weekly_bounds(today)
    manifest = {
        "week_start": week_start.date().isoformat(),
        "week_end": week_end.date().isoformat(),
        "anchor_date": today.date().isoformat(),
        "weekly_dir": str(weekly_dir),
        "artifacts_dir": str(artifacts_dir),
        "prep_kind": "weekly_analysis_prep",
        "sidecars": sidecars,
    }
    manifest_path = weekly_dir / "weekly_prep_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False, allow_nan=False), encoding="utf-8")
    manifest["manifest_path"] = str(manifest_path)
    return manifest


def main() -> int:
    args = build_parser().parse_args()
    today = sya15_continuity.resolve_today(args.today)
    weekly_dir = args.weekly_dir if args.weekly_dir is not None else default_weekly_dir(today)
    manifest = build_weekly_prep(
        today=today,
        weekly_dir=weekly_dir,
        input_path=args.input,
        focus_sport=args.focus_sport,
        window_size=args.window_size,
        min_positive=args.min_positive,
    )
    print(json.dumps(manifest, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
