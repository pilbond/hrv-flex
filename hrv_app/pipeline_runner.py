from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Iterable, Sequence


def _build_subprocess_env() -> dict[str, str]:
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    return env


def _build_hrv_core_args(rr_files: Iterable[Path | str]) -> list[str]:
    args: list[str] = []
    for rr_file in rr_files:
        args.extend(["--rr-file", str(rr_file)])
    return args


def build_hrv_core_cmd(rr_files: Iterable[Path | str]) -> list[str]:
    """Construye el comando completo para build_hrv_core.py."""
    return [sys.executable, "build_hrv_core.py", *_build_hrv_core_args(rr_files)]


def _run_python_script(script_name: str, args: Sequence[str] = ()) -> subprocess.CompletedProcess[str] | None:
    if not Path(script_name).exists():
        print(f"❌ {script_name} no encontrado")
        return None
    try:
        return subprocess.run(
            [sys.executable, script_name, *args],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=True,
            env=_build_subprocess_env(),
        )
    except subprocess.CalledProcessError as exc:
        print(f"⚠️  Error ejecutando {script_name} (código {exc.returncode})")
        if exc.stdout:
            print(exc.stdout)
        if exc.stderr:
            print(exc.stderr)
        return None


def run_build_hrv_core(rr_files: Iterable[Path | str]) -> subprocess.CompletedProcess[str] | None:
    """Ejecuta build_hrv_core.py con una lista de archivos RR."""
    return _run_python_script("build_hrv_core.py", _build_hrv_core_args(rr_files))


def run_build_hrv_final_dashboard_only() -> bool:
    """Ejecuta build_hrv_final_dashboard.py sin reprocesar RR/CORE."""
    result = _run_python_script("build_hrv_final_dashboard.py")
    if result is None:
        return False
    if result.stdout:
        print(result.stdout)
    return True
