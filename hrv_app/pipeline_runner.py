from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Iterable, Sequence

from .pipeline_status import StageExecution


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


def _run_python_script(script_name: str, args: Sequence[str] = ()) -> StageExecution:
    if not Path(script_name).exists():
        print(f"❌ {script_name} no encontrado")
        return StageExecution(
            stage=Path(script_name).stem,
            status="failed",
            outcome="missing_script",
            returncode=2,
            error={"code": "script_missing", "message": f"{script_name} no encontrado"},
        )
    try:
        completed = subprocess.run(
            [sys.executable, script_name, *args],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=True,
            env=_build_subprocess_env(),
        )
        return StageExecution(
            stage=Path(script_name).stem,
            status="ok",
            outcome="completed",
            returncode=getattr(completed, "returncode", 0),
            stdout=getattr(completed, "stdout", "") or "",
            stderr=getattr(completed, "stderr", "") or "",
        )
    except subprocess.CalledProcessError as exc:
        print(f"⚠️  Error ejecutando {script_name} (código {exc.returncode})")
        if exc.stdout:
            print(exc.stdout)
        if exc.stderr:
            print(exc.stderr)
        return StageExecution(
            stage=Path(script_name).stem,
            status="failed",
            outcome="process_error",
            returncode=exc.returncode,
            stdout=exc.stdout or "",
            stderr=exc.stderr or "",
            error={
                "code": "builder_failed",
                "message": f"Error ejecutando {script_name}",
            },
        )
    except OSError as exc:
        return StageExecution(
            stage=Path(script_name).stem,
            status="failed",
            outcome="runner_error",
            returncode=1,
            error={"code": "runner_error", "message": str(exc)},
        )


def run_build_hrv_core(rr_files: Iterable[Path | str]) -> StageExecution:
    """Ejecuta build_hrv_core.py con una lista de archivos RR."""
    return _run_python_script("build_hrv_core.py", _build_hrv_core_args(rr_files))


def run_build_hrv_final_dashboard_only() -> StageExecution:
    """Ejecuta build_hrv_final_dashboard.py sin reprocesar RR/CORE."""
    result = _run_python_script("build_hrv_final_dashboard.py")
    if result.stdout:
        print(result.stdout)
    return result


def run_build_hrv_ssm_shadow_only() -> StageExecution:
    """Ejecuta build_hrv_ssm.py para regenerar el sidecar sombra SSM."""
    result = _run_python_script("build_hrv_ssm.py")
    if result.stdout:
        print(result.stdout)
    return result


def run_build_hrv_ssm_validation_only() -> StageExecution:
    """Ejecuta build_hrv_ssm_validation.py para regenerar el reporte SSM."""
    result = _run_python_script("build_hrv_ssm_validation.py")
    if result.stdout:
        print(result.stdout)
    return result


def run_build_hrv_ssm_outcome_battery_only() -> StageExecution:
    """Ejecuta build_hrv_ssm_outcome_battery.py para la batería de outcomes alternativos."""
    result = _run_python_script("build_hrv_ssm_outcome_battery.py")
    if result.stdout:
        print(result.stdout)
    return result
