#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from session_analysis_pipeline import DEFAULT_BUNDLE_ROOT, DEFAULT_SESSIONS_CSV, prepare_bundle


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Prepare local bundle for a session analysis.")
    p.add_argument("--sessions-csv", default=str(DEFAULT_SESSIONS_CSV))
    p.add_argument("--bundle-root", default=str(DEFAULT_BUNDLE_ROOT))
    p.add_argument("--session-id", default=None)
    return p.parse_args()


def main() -> int:
    args = parse_args()
    manifest = prepare_bundle(
        sessions_csv=Path(args.sessions_csv),
        bundle_root=Path(args.bundle_root),
        session_id=args.session_id,
    )
    print(json.dumps(manifest, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
