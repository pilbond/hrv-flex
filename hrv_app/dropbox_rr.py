from __future__ import annotations

import os
import re
import subprocess
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Dict, Iterable, Optional

from .config import DROPBOX_FOLDER_PATH, DROPBOX_RECURSIVE, DROPBOX_RR_ENABLED, DROPBOX_RR_NO_AUX, DROPBOX_RR_PAIR_LIMIT, DROPBOX_RR_SCRIPT, DROPBOX_RR_TIMEOUT_SEC, OUTDIR, _qprint

_RR_DATE_RE = re.compile(r"(?P<date>\d{4}-\d{2}-\d{2})")


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


def _build_dropbox_rr_cmd(outdir: Path) -> list[str]:
    cmd = [sys.executable, DROPBOX_RR_SCRIPT, "--dropbox-folder", DROPBOX_FOLDER_PATH, "--outdir", str(outdir)]
    if DROPBOX_RECURSIVE:
        cmd.append("--dropbox-recursive")
    if DROPBOX_RR_NO_AUX:
        cmd.append("--no-aux")
    if DROPBOX_RR_PAIR_LIMIT:
        cmd.extend(["--pair-limit", str(DROPBOX_RR_PAIR_LIMIT)])
    return cmd


def _run_dropbox_rr_import_for_dates(
    target_dates: Iterable[date],
    rr_dir: Path | str = OUTDIR,
    verbose: bool = False,
) -> tuple[Dict[date, Path], int]:
    """Asegura cobertura RR vía Dropbox para un conjunto de fechas."""
    target_set = {d for d in target_dates if d is not None}
    if not target_set:
        return {}, 0

    outdir = Path(rr_dir)
    pre_map = _scan_rr_files_by_date(outdir, source_tag="from_jsonl")

    if not DROPBOX_RR_ENABLED:
        result = {d: pre_map[d] for d in target_set if d in pre_map}
        return result, 0

    if not DROPBOX_FOLDER_PATH:
        print(
            "⚠️  Dropbox RR habilitado, pero falta HRV_DROPBOX_FOLDER_PATH/DROPBOX_FOLDER_PATH. "
            "Se continuará solo con RR ya existentes.",
            file=sys.stderr,
        )
        result = {d: pre_map[d] for d in target_set if d in pre_map}
        return result, 0

    script_path = Path(DROPBOX_RR_SCRIPT)
    if not script_path.exists():
        _qprint(f"⚠️  No existe el script Dropbox RR: {script_path}")
        result = {d: pre_map[d] for d in target_set if d in pre_map}
        return result, 0

    cmd = _build_dropbox_rr_cmd(outdir)
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"

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
    except subprocess.CalledProcessError as exc:
        print(f"⚠️  Error ejecutando importación Dropbox RR (código {exc.returncode})")
        if exc.stdout:
            print(exc.stdout)
        if exc.stderr:
            print(exc.stderr)

    post_map = _scan_rr_files_by_date(outdir, source_tag="from_jsonl")
    merged_map: Dict[date, Path] = dict(pre_map)
    merged_map.update(post_map)

    result = {d: merged_map[d] for d in target_set if d in merged_map}
    new_count = sum(1 for d in result if d not in pre_map and d in post_map)
    return result, new_count
