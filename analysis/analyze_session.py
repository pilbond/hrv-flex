#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SESSIONS_CSV = ROOT / "data" / "ENDURANCE_HRV_sessions.csv"
DEFAULT_REPORTS_DIR = ROOT / "analysis" / "reports"
DEFAULT_BUNDLE_ROOT = ROOT / "analysis" / ".cache" / "session_bundles"


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
            lines = [
                "Falta la dependencia 'requests' en el Python con el que estás ejecutando el script.",
                f"Python actual: {python_path}",
            ]
            if venv_python.exists():
                lines.extend(
                    [
                        f"Este repo ya tiene entorno virtual: {venv_python}",
                        "No se pudo relanzar automaticamente el script con .venv.",
                        "Ejecuta:",
                        rf"  .\.venv\Scripts\python.exe analysis\analyze_session.py",
                    ]
                )
            else:
                lines.extend(
                    [
                        "Instala dependencias con:",
                        r"  pip install -r requirements_web.txt",
                    ]
                )
            raise SystemExit("\n".join(lines)) from exc
        raise
    return cleanup_bundle, prepare_bundle, run_analysis


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Prepare and run a full session analysis.")
    p.add_argument("--sessions-csv", default=str(DEFAULT_SESSIONS_CSV))
    p.add_argument("--bundle-root", default=str(DEFAULT_BUNDLE_ROOT))
    p.add_argument("--reports-dir", default=str(DEFAULT_REPORTS_DIR))
    p.add_argument("--session-id", default=None)
    p.add_argument("--keep-bundle", action="store_true", help="Keep raw session files after analysis")
    p.add_argument("--keep-debug-artifacts", action="store_true", help="Keep low-level CSV and stdout artifacts in reports")
    return p.parse_args()


def main() -> int:
    cleanup_bundle, prepare_bundle, run_analysis = _load_pipeline()
    args = parse_args()
    manifest = prepare_bundle(
        sessions_csv=Path(args.sessions_csv),
        bundle_root=Path(args.bundle_root),
        session_id=args.session_id,
    )
    result = run_analysis(
        Path(manifest["manifest_path"]),
        Path(args.reports_dir),
        keep_debug_artifacts=args.keep_debug_artifacts,
    )
    if not args.keep_bundle:
        cleanup_bundle(Path(manifest["bundle_dir"]))
        result["bundle_cleaned"] = True
    else:
        result["bundle_cleaned"] = False
        result["bundle_dir"] = manifest["bundle_dir"]
        result["bundle_manifest"] = manifest["manifest_path"]
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
