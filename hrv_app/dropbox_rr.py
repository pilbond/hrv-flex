from __future__ import annotations

import os
import re
import subprocess
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Dict, Iterable, Optional
from dataclasses import dataclass

from .config import DROPBOX_FOLDER_PATH, DROPBOX_RECURSIVE, DROPBOX_RR_ENABLED, DROPBOX_RR_NO_AUX, DROPBOX_RR_PAIR_LIMIT, DROPBOX_RR_SCRIPT, DROPBOX_RR_TIMEOUT_SEC, OUTDIR, _qprint

_RR_DATE_RE = re.compile(r"(?P<date>\d{4}-\d{2}-\d{2})")


@dataclass
class DropboxRRResult:
    """Cobertura y estado de una importación Dropbox RR."""

    files: Dict[date, Path]
    new_count: int
    status: str = "ok"
    outcome: str = "data_found"
    error: dict | None = None


def _extract_date_from_rr_filename(rr_filename: str) -> Optional[date]:
    """Extrae la fecha YYYY-MM-DD de un nombre de RR."""
    name = Path(rr_filename).name
    match = _RR_DATE_RE.search(name)
    if not match:
        return None
    try:
        return datetime.strptime(match.group("date"), "%Y-%m-%d").date()
    except ValueError:
        return None


def _is_excluded_rr_path(path: Path, root: Path) -> bool:
    try:
        rel_parts = path.relative_to(root).parts[:-1]
    except ValueError:
        rel_parts = path.parts[:-1]
    return any(part.startswith("_audit_") or part == "_incoming_dropbox_rr" for part in rel_parts)


def _dropbox_stage_dir(rr_dir: Path | str = OUTDIR) -> Path:
    return Path(rr_dir) / "_incoming_dropbox_rr"


def _clear_dropbox_stage_dir(stage_dir: Path) -> None:
    if stage_dir.exists():
        for path in sorted(stage_dir.rglob("*"), reverse=True):
            if path.is_file():
                path.unlink()
            elif path.is_dir():
                try:
                    path.rmdir()
                except OSError:
                    pass
    stage_dir.mkdir(parents=True, exist_ok=True)


def _scan_rr_files_by_date(rr_dir: Path | str = OUTDIR, source_tag: Optional[str] = None) -> Dict[date, Path]:
    """Indexa RR.CSV por fecha, usando el fichero más reciente si hay colisiones.

    Si source_tag se proporciona, solo se consideran ficheros cuyo nombre lo contenga.
    """
    root = Path(rr_dir)
    if not root.exists():
        return {}

    source_tag_norm = (source_tag or "").strip().lower()
    indexed: Dict[date, tuple[float, Path]] = {}
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if _is_excluded_rr_path(path, root):
            continue
        if not path.name.upper().endswith("_RR.CSV"):
            continue
        if source_tag_norm and source_tag_norm not in path.name.lower():
            continue
        rr_date = _extract_date_from_rr_filename(path.name)
        if rr_date is None:
            continue
        mtime = path.stat().st_mtime
        current = indexed.get(rr_date)
        if current is None or mtime >= current[0]:
            indexed[rr_date] = (mtime, path)

    return {d: item[1] for d, item in sorted(indexed.items(), key=lambda item: item[0])}


def _iter_dates(date_from: date, date_to: date) -> Iterable[date]:
    """Itera fechas inclusivas entre date_from y date_to."""
    if date_from > date_to:
        return
    current = date_from
    while current <= date_to:
        yield current
        current += timedelta(days=1)


def _compute_target_missing_dates(
    date_from: Optional[date],
    date_to: Optional[date],
    existing_dates: Iterable[date],
) -> list[date]:
    """Devuelve las fechas del rango que todavía no están en CORE."""
    if date_from is None or date_to is None:
        return []

    existing = set(existing_dates)
    return [d for d in _iter_dates(date_from, date_to) if d not in existing]


def _build_dropbox_rr_cmd(outdir: Path, target_dates: Iterable[date] = ()) -> list[str]:
    cmd = [sys.executable, DROPBOX_RR_SCRIPT, "--dropbox-folder", DROPBOX_FOLDER_PATH, "--outdir", str(outdir)]
    if DROPBOX_RECURSIVE:
        cmd.append("--dropbox-recursive")
    if DROPBOX_RR_NO_AUX:
        cmd.append("--no-aux")
    if DROPBOX_RR_PAIR_LIMIT:
        cmd.extend(["--pair-limit", str(DROPBOX_RR_PAIR_LIMIT)])
    for target_date in sorted({d for d in target_dates if d is not None}):
        cmd.extend(["--target-date", target_date.isoformat()])
    return cmd


def _promote_operational_rr_files(rr_files: Iterable[Path | str], rr_dir: Path | str = OUTDIR) -> int:
    root = Path(rr_dir)
    promoted = 0
    for rr_file in rr_files:
        path = Path(rr_file)
        if not path.exists():
            continue
        if path.parent == root:
            continue
        rr_date = _extract_date_from_rr_filename(path.name)
        if rr_date is None:
            continue
        canonical = root / f"ENDURANCE_{rr_date.isoformat()}_from_jsonl_RR.CSV"
        canonical.parent.mkdir(parents=True, exist_ok=True)
        os.replace(path, canonical)
        for duplicate in root.glob(f"ENDURANCE_{rr_date.isoformat()}_from_jsonl_v*_RR.CSV"):
            if duplicate != canonical and duplicate.is_file():
                duplicate.unlink()
        promoted += 1
    return promoted


def _run_dropbox_rr_import_for_dates(
    target_dates: Iterable[date],
    rr_dir: Path | str = OUTDIR,
    verbose: bool = False,
) -> DropboxRRResult:
    """Asegura cobertura RR vía Dropbox para un conjunto de fechas."""
    target_set = {d for d in target_dates if d is not None}
    if not target_set:
        return DropboxRRResult({}, 0, status="not_requested", outcome="not_applicable")

    outdir = Path(rr_dir)
    pre_map = _scan_rr_files_by_date(outdir, source_tag="from_jsonl")
    stage_dir = _dropbox_stage_dir(outdir)

    def local_coverage() -> Dict[date, Path]:
        return {d: pre_map[d] for d in target_set if d in pre_map}

    def local_coverage_is_complete(result: Dict[date, Path]) -> bool:
        return len(result) == len(target_set)

    if not DROPBOX_RR_ENABLED:
        result = local_coverage()
        if local_coverage_is_complete(result):
            return DropboxRRResult(result, 0, status="not_requested", outcome="local_coverage")
        return DropboxRRResult(result, 0, status="failed", outcome="disabled", error={
            "code": "dropbox_rr_disabled",
            "message": "Dropbox RR está deshabilitado para fechas no cubiertas",
        })

    if not DROPBOX_FOLDER_PATH:
        print(
            "⚠️  Dropbox RR habilitado, pero falta HRV_DROPBOX_FOLDER_PATH/DROPBOX_FOLDER_PATH. "
            "Se continuará solo con RR ya existentes.",
            file=sys.stderr,
        )
        result = local_coverage()
        if local_coverage_is_complete(result):
            return DropboxRRResult(result, 0, status="not_requested", outcome="local_coverage")
        return DropboxRRResult(result, 0, status="failed", outcome="configuration_error", error={
            "code": "dropbox_rr_folder_missing",
            "message": "Falta la carpeta Dropbox RR",
        })

    script_path = Path(DROPBOX_RR_SCRIPT)
    if not script_path.exists():
        _qprint(f"⚠️  No existe el script Dropbox RR: {script_path}")
        result = local_coverage()
        if local_coverage_is_complete(result):
            return DropboxRRResult(result, 0, status="not_requested", outcome="local_coverage")
        return DropboxRRResult(result, 0, status="failed", outcome="configuration_error", error={
            "code": "dropbox_rr_script_missing",
            "message": f"No existe el script Dropbox RR: {script_path.name}",
        })

    _clear_dropbox_stage_dir(stage_dir)

    cmd = _build_dropbox_rr_cmd(stage_dir, target_set)
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"

    process_error: dict | None = None
    process_outcome = "data_found"
    try:
        completed = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=True,
            timeout=DROPBOX_RR_TIMEOUT_SEC,
            env=env,
        )
        if verbose and completed.stdout:
            print(completed.stdout)
    except subprocess.TimeoutExpired as exc:
        print(f"⚠️  Timeout ejecutando importación Dropbox RR (>{DROPBOX_RR_TIMEOUT_SEC}s)")
        if exc.stdout:
            print(exc.stdout)
        if exc.stderr:
            print(exc.stderr)
        process_error = {"code": "dropbox_rr_timeout", "message": "Timeout ejecutando importación Dropbox RR"}
        process_outcome = "timeout"
    except subprocess.CalledProcessError as exc:
        print(f"⚠️  Error ejecutando importación Dropbox RR (código {exc.returncode})")
        if exc.stdout:
            print(exc.stdout)
        if exc.stderr:
            print(exc.stderr)
        process_error = {"code": "dropbox_rr_converter_failed", "message": "El conversor Dropbox RR terminó con error"}
        process_outcome = "converter_error"

    post_map = _scan_rr_files_by_date(stage_dir, source_tag="from_jsonl")
    merged_map: Dict[date, Path] = dict(pre_map)
    merged_map.update(post_map)

    result = {d: merged_map[d] for d in target_set if d in merged_map}
    new_count = sum(1 for d in result if d not in pre_map and d in post_map)
    if process_error:
        return DropboxRRResult(result, new_count, status="failed", outcome=process_outcome, error=process_error)
    if not result:
        return DropboxRRResult(result, new_count, status="ok", outcome="no_data")
    return DropboxRRResult(result, new_count, status="ok", outcome="data_found")
