"""Replay FINAL for candidate CORE values with control Calidad/HRV_Stability.

This is an attribution check, not a proposed operational QA policy. Output
arms are named <source>q and stay inside the isolated replay directory.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[4]


def freeze(work: Path, source: str) -> None:
    if source not in {f"{prefix}{s}" for prefix in ("E", "H3E") for s in (0, 60, 90, 120, 180)}:
        raise ValueError(f"Unsupported source arm: {source}")
    destination = (work / f"{source}q").resolve()
    if destination.parent != work.resolve():
        raise ValueError("Output must remain directly inside replay work directory")
    if destination.exists():
        shutil.rmtree(destination)
    shutil.copytree(work / source / "data", destination / "data")
    path = destination / "data" / "ENDURANCE_HRV_master_CORE.csv"
    frame = pd.read_csv(path)
    control = pd.read_csv(work / "C/data/ENDURANCE_HRV_master_CORE.csv").set_index("Fecha")
    if frame.Fecha.duplicated().any() or not frame.Fecha.isin(control.index).all():
        raise ValueError("Candidate/control dates do not align")
    for column in ("Calidad", "HRV_Stability"):
        frame[column] = frame.Fecha.map(control[column])
    frame.to_csv(path, index=False)
    env = dict(os.environ, HRV_DATA_DIR=str(destination / "data"), HRV_DISABLE_BACKUP="1",
               HRV_QUIET="1", PYTHONPATH=str(ROOT))
    result = subprocess.run(
        [sys.executable, str(ROOT / "build_hrv_final_dashboard.py"), "--data-dir", str(destination / "data")],
        cwd=destination, env=env, capture_output=True, text=True,
    )
    (destination / "final.log").write_text(result.stdout + "\n--- stderr ---\n" + result.stderr, encoding="utf-8")
    print(source, "QA-frozen FINAL rc", result.returncode)
    if result.returncode:
        raise RuntimeError(result.stderr[-1000:])


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work", type=Path, required=True)
    parser.add_argument("arms", nargs="+")
    args = parser.parse_args()
    work = args.work.resolve()
    if not (work / "C/data/ENDURANCE_HRV_master_CORE.csv").exists():
        raise ValueError("Missing isolated replay control")
    for arm in args.arms:
        freeze(work, arm)


if __name__ == "__main__":
    main()
