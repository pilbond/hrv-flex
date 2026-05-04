#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from collections.abc import Iterable
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SESSIONS_CSV = ROOT / "data" / "ENDURANCE_HRV_sessions.csv"
DEFAULT_REPORTS_DIR = ROOT / "analysis" / "reports"
DEFAULT_BUNDLE_ROOT = ROOT / "analysis" / ".cache" / "session_bundles"

# "Aeróbica" aquí se interpreta como trabajo de resistencia, no fuerza ni movilidad.
# Si el criterio operativo cambia, este set debe ajustarse y, si afecta a la norma,
# también documentarse en analysis/AGENTS.md o docs/contracts/.
DEFAULT_NON_AEROBIC_SPORTS = {"strength", "mobility"}


def _load_pipeline():
    try:
        from session_analysis_pipeline import cleanup_bundle, prepare_bundle, run_analysis
    except ModuleNotFoundError as exc:
        if exc.name == "requests":
            python_path = Path(sys.executable)
            venv_python = ROOT / ".venv" / "Scripts" / "python.exe"
            if venv_python.exists() and python_path.resolve() != venv_python.resolve():
                os.execv(
                    str(venv_python),
                    [str(venv_python), str(Path(__file__).resolve()), *sys.argv[1:]],
                )
            raise SystemExit(
                "\n".join(
                    [
                        "Falta la dependencia 'requests' en el Python con el que estás ejecutando el script.",
                        f"Python actual: {python_path}",
                        "Instala dependencias con:",
                        r"  pip install -r requirements_web.txt",
                    ]
                )
            ) from exc
        raise
    return cleanup_bundle, prepare_bundle, run_analysis


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Run session analysis in batch.")
    p.add_argument("--sessions-csv", default=str(DEFAULT_SESSIONS_CSV))
    p.add_argument("--bundle-root", default=str(DEFAULT_BUNDLE_ROOT))
    p.add_argument("--reports-dir", default=str(DEFAULT_REPORTS_DIR))
    p.add_argument("--year", type=int, default=2026)
    p.add_argument("--session-id", action="append", default=None, help="Limit to one or more explicit session IDs.")
    p.add_argument(
        "--sport",
        action="append",
        default=None,
        help="Limit to one or more sport values from sessions.csv.",
    )
    p.add_argument(
        "--aerobic-only",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Keep only endurance-style sessions; default on.",
    )
    p.add_argument(
        "--include-strength",
        action="store_true",
        help="Include strength sessions even when --aerobic-only is enabled.",
    )
    p.add_argument("--keep-bundle", action="store_true")
    p.add_argument("--keep-debug-artifacts", action="store_true")
    return p.parse_args()


def _read_sessions(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def _is_selected_sport(sport: str, *, aerobic_only: bool, include_strength: bool, sports: set[str] | None) -> bool:
    sport = sport.strip()
    if sports is not None and sport not in sports:
        return False
    if not aerobic_only:
        return True
    if sport in DEFAULT_NON_AEROBIC_SPORTS:
        return include_strength and sport == "strength"
    return True


def _selected_rows(rows: Iterable[dict[str, str]], *, year: int, aerobic_only: bool, include_strength: bool, sports: set[str] | None, session_ids: set[str] | None) -> list[dict[str, str]]:
    selected: list[dict[str, str]] = []
    for row in rows:
        date = (row.get("Fecha") or "").strip()
        if len(date) < 4 or not date.startswith(str(year)):
            continue
        session_id = (row.get("session_id") or "").strip()
        if session_ids is not None and session_id not in session_ids:
            continue
        sport = (row.get("sport") or "").strip()
        if not _is_selected_sport(sport, aerobic_only=aerobic_only, include_strength=include_strength, sports=sports):
            continue
        selected.append(row)
    selected.sort(key=lambda row: ((row.get("Fecha") or ""), (row.get("start_time") or ""), (row.get("session_id") or "")))
    return selected


def main() -> int:
    cleanup_bundle, prepare_bundle, run_analysis = _load_pipeline()
    args = parse_args()
    rows = _read_sessions(Path(args.sessions_csv))
    session_ids = set(args.session_id) if args.session_id else None
    sports = set(args.sport) if args.sport else None
    selected = _selected_rows(
        rows,
        year=args.year,
        aerobic_only=args.aerobic_only,
        include_strength=args.include_strength,
        sports=sports,
        session_ids=session_ids,
    )

    results: list[dict[str, object]] = []
    failures: list[dict[str, str]] = []
    for row in selected:
        session_id = (row.get("session_id") or "").strip()
        if not session_id:
            continue
        manifest: dict[str, object] | None = None
        try:
            manifest = prepare_bundle(
                sessions_csv=Path(args.sessions_csv),
                bundle_root=Path(args.bundle_root),
                session_id=session_id,
            )
            result = run_analysis(
                Path(manifest["manifest_path"]),
                Path(args.reports_dir),
                keep_debug_artifacts=args.keep_debug_artifacts,
            )
            result["session_id"] = session_id
            result["slug"] = manifest["slug"]
            results.append(result)
        except Exception as exc:  # noqa: BLE001
            failures.append({"session_id": session_id, "error": str(exc)})
        finally:
            if manifest is not None and not args.keep_bundle:
                cleanup_bundle(Path(manifest["bundle_dir"]))

    payload = {
        "year": args.year,
        "selected_count": len(selected),
        "generated_count": len(results),
        "failed_count": len(failures),
        "results": results,
        "failures": failures,
    }
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
