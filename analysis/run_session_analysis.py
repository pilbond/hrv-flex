#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from session_analysis_pipeline import DEFAULT_REPORTS_DIR, run_analysis


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Run session analysis from a prepared bundle.")
    p.add_argument("--bundle-manifest", required=True)
    p.add_argument("--reports-dir", default=str(DEFAULT_REPORTS_DIR))
    p.add_argument("--keep-debug-artifacts", action="store_true")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    result = run_analysis(
        Path(args.bundle_manifest),
        Path(args.reports_dir),
        keep_debug_artifacts=args.keep_debug_artifacts,
    )
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
