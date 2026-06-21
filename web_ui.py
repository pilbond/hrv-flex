#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Web UI para Polar HRV Automation
Accesible desde cualquier dispositivo (móvil, tablet, PC)
"""

from flask import Flask, render_template_string, jsonify, request, redirect
from flask_cors import CORS
from markupsafe import escape
from werkzeug.middleware.proxy_fix import ProxyFix
import subprocess
import sys
import time
import os
import csv
import math
import re
import shutil
from pathlib import Path
from datetime import datetime
import threading
import json
from urllib.parse import urlencode
import secrets
import uuid
import pandas as pd
from hrv_app.config import (
    DATA_DIR,
    OUTDIR as RR_DOWNLOAD_DIR,
    POLAR_V4_SCOPES,
    TOKEN_FILE_V4 as TOKEN_PATH_V4,
)
from hrv_app.io_utils import write_csv_atomic, write_json_atomic
from hrv_app.polar_utils import env_flag, response_excerpt
from hrv_app.oauth_utils import save_json_atomic
from hrv_app.polar_auth_v4 import (
    _safe_float as _v4_safe_float,
    build_auth_url_v4,
    exchange_code_for_token_v4,
    load_bundle_v4,
    persist_authorized_bundle,
    redact as redact_v4_bundle,
)

app = Flask(__name__)
CORS(app)
# Respeta headers X-Forwarded-* cuando corre detrás de Railway/Proxy
app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)
app.config["PREFERRED_URL_SCHEME"] = "https"

SEED_UPLOAD_DIR = Path((os.environ.get("HRV_SEED_UPLOAD_DIR") or "seed_upload").strip() or "seed_upload")
ALLOWED_IMPORT_FILES = [
    "ENDURANCE_HRV_master_CORE.csv",
    "ENDURANCE_HRV_master_BETA_AUDIT.csv",
    "ENDURANCE_HRV_master_FINAL.csv",
    "ENDURANCE_HRV_master_DASHBOARD.csv",
    "ENDURANCE_HRV_sleep.csv",
    "ENDURANCE_HRV_sessions.csv",
    "ENDURANCE_HRV_sessions_day.csv",
]

_RR_DELETE_DERIVED_CSVS = (
    "ENDURANCE_HRV_master_CORE.csv",
    "ENDURANCE_HRV_master_BETA_AUDIT.csv",
    "ENDURANCE_HRV_master_FINAL.csv",
    "ENDURANCE_HRV_master_DASHBOARD.csv",
    "ENDURANCE_HRV_ssm_shadow.csv",
)
_RR_DELETE_DERIVED_JSONS = (
    "ENDURANCE_HRV_master_FINAL_reason_items.json",
    "ENDURANCE_HRV_master_CORE_manifest.json",
    "ENDURANCE_HRV_master_FINAL_manifest.json",
    "ENDURANCE_HRV_ssm_shadow_metadata.json",
)



def _public_url() -> str:
    """URL pública base.

    En producción se usa https. En local se respeta http://localhost.
    """
    # Prioridad: PUBLIC_URL explícita → Railway domain → request host
    pu = (
        os.environ.get("PUBLIC_URL")
        or os.environ.get("RAILWAY_PUBLIC_URL")
        or os.environ.get("RAILWAY_PUBLIC_DOMAIN")
        or ""
    ).strip()
    if pu:
        if pu.startswith("http://") or pu.startswith("https://"):
            host = pu.split("://", 1)[1]
            if host.startswith(("localhost", "127.0.0.1", "[::1]")):
                return f"http://{host}".rstrip("/")
            return pu.rstrip("/")
        if pu.startswith(("localhost", "127.0.0.1", "[::1]")):
            return f"http://{pu}".rstrip("/")
        return f"https://{pu}".rstrip("/")
    # Fallback razonable: usar Host del request (puede ser http sin ProxyFix)
    return (request.host_url or "").rstrip("/")


def _redirect_uri() -> str:
    return f"{_public_url()}/auth/callback"


# Estado global de ejecución
execution_state = {
    'running': False,
    'last_run': None,
    'last_output': '',
    'last_error': '',
    'success': None,
    'job_type': None,
    'message': None,
}
execution_state_lock = threading.Lock()

# Clave compartida opcional para proteger /api/*. Si HRV_UI_KEY no está
# definida, el comportamiento es el histórico (sin autenticación).
UI_KEY = (os.environ.get("HRV_UI_KEY") or "").strip()

# Estados OAuth emitidos pendientes de callback (anti-CSRF). Proceso único,
# memoria local suficiente.
_OAUTH_STATE_TTL_SEC = 600
_oauth_states: dict[str, float] = {}
_oauth_states_lock = threading.Lock()


def _issue_oauth_state() -> str:
    state = secrets.token_urlsafe(24)
    now = time.time()
    with _oauth_states_lock:
        expired = [s for s, t in _oauth_states.items() if now - t > _OAUTH_STATE_TTL_SEC]
        for s in expired:
            _oauth_states.pop(s, None)
        _oauth_states[state] = now
    return state


def _consume_oauth_state(state: str) -> bool:
    """Valida y consume el state (uso único). Devuelve True si válido."""
    if not state:
        return False
    with _oauth_states_lock:
        issued_at = _oauth_states.pop(state, None)
    if issued_at is None:
        return False
    return (time.time() - issued_at) <= _OAUTH_STATE_TTL_SEC


@app.before_request
def _require_ui_key():
    if not UI_KEY or not request.path.startswith("/api/"):
        return None
    provided = (request.headers.get("X-HRV-KEY") or request.args.get("key") or "").strip()
    if provided and secrets.compare_digest(provided, UI_KEY):
        return None
    return jsonify({
        "success": False,
        "error": "No autorizado: falta la clave HRV_UI_KEY (header X-HRV-KEY o ?key=).",
    }), 401


JOB_LABELS = {
    'hrv': 'sincronización HRV',
    'sessions': 'sincronización de sesiones',
    'seed_import': 'importación CSV seed',
    'delete_rr': 'borrado del último RR',
    'restore_backup': 'restauración desde Dropbox',
}


def _job_label(job_type: str | None) -> str:
    return JOB_LABELS.get(job_type or '', 'proceso')


def _execution_snapshot() -> dict:
    with execution_state_lock:
        return dict(execution_state)


def _execution_running() -> bool:
    with execution_state_lock:
        return bool(execution_state['running'])


def _try_begin_execution(job_type: str) -> bool:
    with execution_state_lock:
        if execution_state['running']:
            return False
        execution_state['running'] = True
        execution_state['success'] = None
        execution_state['last_output'] = ''
        execution_state['last_error'] = ''
        execution_state['job_type'] = job_type
        execution_state['message'] = None
        return True


def _set_execution_start(job_type: str) -> None:
    with execution_state_lock:
        execution_state['running'] = True
        execution_state['success'] = None
        execution_state['last_output'] = ''
        execution_state['last_error'] = ''
        execution_state['job_type'] = job_type
        execution_state['message'] = None


def _set_execution_result(job_type: str, success: bool, output: str = '', error: str = '', message: str | None = None) -> None:
    with execution_state_lock:
        execution_state['running'] = False
        execution_state['success'] = success
        execution_state['last_output'] = output or ''
        execution_state['last_error'] = error or ''
        execution_state['job_type'] = job_type
        execution_state['message'] = message
        execution_state['last_run'] = datetime.now().isoformat()


def _run_subprocess_job(command: list[str], job_type: str, success_message: str, env_extra: dict | None = None) -> None:
    _set_execution_start(job_type)
    timeout_sec = _sync_timeout_seconds()
    command_path = Path(command[1]) if len(command) > 1 else None

    try:
        if command_path is not None and not command_path.exists():
            raise FileNotFoundError(f'{command_path.name} no encontrado')

        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='replace',
            timeout=timeout_sec,
            env={
                **os.environ,
                'PYTHONIOENCODING': 'utf-8',
                **(env_extra or {}),
            },
        )

        success = (result.returncode == 0)
        message = success_message if success else f'Error en {_job_label(job_type)}'
        _set_execution_result(job_type, success, result.stdout or '', result.stderr or '', message)
    except subprocess.TimeoutExpired as exc:
        stdout = exc.stdout if isinstance(exc.stdout, str) else (exc.stdout.decode('utf-8', errors='replace') if exc.stdout else '')
        stderr = exc.stderr if isinstance(exc.stderr, str) else (exc.stderr.decode('utf-8', errors='replace') if exc.stderr else '')
        _set_execution_result(
            job_type,
            False,
            stdout or '',
            (
                f'Timeout ejecutando {_job_label(job_type)} (>{timeout_sec}s). '
                f'Ajusta HRV_SYNC_TIMEOUT_SEC si hace falta.\n{stderr or ""}'
            ).strip(),
            f'Timeout en {_job_label(job_type)}',
        )
    except Exception as exc:
        _set_execution_result(job_type, False, '', str(exc), f'Error en {_job_label(job_type)}')

def _parse_iso_date(value: str):
    try:
        return datetime.fromisoformat((value or "").strip()).date()
    except Exception:
        return None


def _sync_timeout_seconds(default: int = 1200) -> int:
    raw = (os.environ.get("HRV_SYNC_TIMEOUT_SEC") or "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
        if value < 60:
            return 60
        return value
    except ValueError:
        return default


def _token_diagnostics_v4() -> dict:
    # Describe el bundle v4 (único runtime desde AYO-22).
    info = {
        "api_version": "v4",
        "token_path": str(TOKEN_PATH_V4),
        "token_exists": TOKEN_PATH_V4.exists(),
        "token_reason": "missing",
        "token_expired": None,
    }
    if not info["token_exists"]:
        return info

    bundle = load_bundle_v4(TOKEN_PATH_V4)
    if bundle is None:
        info["token_reason"] = "invalid_json"
        return info

    # redact(): nunca exponer access ni refresh token por /api/status.
    safe = redact_v4_bundle(bundle)
    info["token_scopes"] = safe.get("scopes")
    if not safe.get("has_access_token"):
        # Sin access_token pero con refresh_token, get_valid_access_token()
        # lo renueva en el siguiente uso: es "refreshable", no un caso que
        # exija re-auth como "missing_access_token".
        if safe.get("has_refresh_token"):
            info["token_reason"] = "refreshable"
            info["token_expired"] = True
        else:
            info["token_reason"] = "missing_access_token"
        return info

    if safe.get("needs_refresh"):
        # needs_refresh se activa también dentro del margen de refresco
        # proactivo (REFRESH_SKEW_SEC), antes de la expiración real.
        # _safe_float: un bundle con obtained_at/expires_in corruptos debe
        # diagnosticarse, no tumbar /api/status con ValueError.
        obtained_at = _v4_safe_float(bundle.get("obtained_at"))
        expires_in = _v4_safe_float(bundle.get("expires_in"))
        actually_expired = expires_in <= 0 or (time.time() - obtained_at) >= expires_in
        if safe.get("has_refresh_token"):
            info["token_reason"] = "refreshable"
            info["token_expired"] = actually_expired
        else:
            info["token_reason"] = "expired"
            info["token_expired"] = True
        return info

    info["token_reason"] = "ok"
    info["token_expired"] = False
    return info


_token_diagnostics = _token_diagnostics_v4


def _seed_upload_diagnostics() -> dict:
    files = []
    for name in ALLOWED_IMPORT_FILES:
        path = SEED_UPLOAD_DIR / name
        if path.exists():
            try:
                size = path.stat().st_size
            except OSError:
                size = None
            files.append({
                "name": name,
                "size": size,
            })

    return {
        "seed_upload_dir": str(SEED_UPLOAD_DIR),
        "seed_upload_exists": SEED_UPLOAD_DIR.exists(),
        "seed_upload_files": files,
        "seed_upload_file_count": len(files),
    }


def _import_seed_csvs() -> dict:
    if not SEED_UPLOAD_DIR.exists():
        raise FileNotFoundError(f"No existe la carpeta de carga: {SEED_UPLOAD_DIR}")

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    backup_dir = DATA_DIR / "backup" / datetime.now().strftime("seed_import_%Y%m%d_%H%M%S")

    imported = []
    missing = []
    backed_up = []

    for name in ALLOWED_IMPORT_FILES:
        source = SEED_UPLOAD_DIR / name
        if not source.exists():
            missing.append(name)
            continue

        dest = DATA_DIR / name
        if dest.exists():
            backup_dir.mkdir(parents=True, exist_ok=True)
            backup_target = backup_dir / name
            shutil.copy2(dest, backup_target)
            backed_up.append(name)

        shutil.copy2(source, dest)
        imported.append(name)

    if not imported:
        raise FileNotFoundError(
            f"No se encontraron CSV permitidos en {SEED_UPLOAD_DIR}"
        )

    return {
        "imported": imported,
        "missing": missing,
        "backed_up": backed_up,
        "backup_dir": str(backup_dir) if backed_up else None,
        "data_dir": str(DATA_DIR),
    }


def _rr_download_dir() -> Path:
    # Misma resolución (con fallback a directorio escribible) que usa el
    # pipeline: una única fuente de verdad en hrv_app.config.
    return RR_DOWNLOAD_DIR


def _list_rr_csv_files(rr_dir: Path) -> list[Path]:
    files = []
    for pattern in ("*_RR.csv", "*_RR.CSV", "*_rr.csv"):
        files.extend(path for path in rr_dir.glob(pattern) if path.is_file())
    unique_files = {path.resolve(): path for path in files}
    return sorted(unique_files.values(), key=_rr_sort_key)


def _rr_sort_key(path: Path) -> tuple[str, float, str]:
    try:
        rr_date = _extract_rr_date(path.name)
    except ValueError:
        rr_date = ""
    try:
        mtime = path.stat().st_mtime
    except OSError:
        mtime = 0.0
    return (rr_date, mtime, path.name)


def _latest_core_rr_reference() -> tuple[str, str] | None:
    core_path = DATA_DIR / "ENDURANCE_HRV_master_CORE.csv"
    if not core_path.exists():
        return None
    try:
        df = pd.read_csv(core_path)
    except (FileNotFoundError, pd.errors.EmptyDataError, OSError, ValueError):
        return None
    if df.empty or "Fecha" not in df.columns:
        return None
    last = df.tail(1).iloc[0]
    date_str = str(last.get("Fecha") or "").strip()
    notes = str(last.get("Notes") or "")
    match = re.search(r"(?:^|;\s*)src=([^;]+)", notes)
    source_name = match.group(1).strip() if match else ""
    if not date_str:
        return None
    return date_str, source_name


def _find_rr_path_by_name(rr_dir: Path, source_name: str) -> Path | None:
    if not source_name:
        return None
    direct = rr_dir / source_name
    if direct.is_file():
        return direct
    matches = [path for path in rr_dir.rglob(source_name) if path.is_file()]
    if not matches:
        return None
    return sorted(matches, key=_rr_sort_key)[-1]


def _select_latest_rr_for_delete(rr_dir: Path) -> tuple[Path, str]:
    core_ref = _latest_core_rr_reference()
    if core_ref:
        core_date, source_name = core_ref
        source_path = _find_rr_path_by_name(rr_dir, source_name)
        if source_path:
            return source_path, core_date

    files = _list_rr_csv_files(rr_dir)
    if not files:
        raise FileNotFoundError(f"No hay archivos RR CSV en {rr_dir}")
    latest = files[-1]
    return latest, _extract_rr_date(latest.name)


def _latest_rr_diagnostics() -> dict:
    rr_dir = _rr_download_dir()
    try:
        files = _list_rr_csv_files(rr_dir) if rr_dir.exists() else []
    except Exception:
        files = []
    try:
        latest, latest_date = _select_latest_rr_for_delete(rr_dir) if rr_dir.exists() else (None, None)
    except Exception:
        latest = files[-1] if files else None
        latest_date = _extract_rr_date(latest.name) if latest else None
    latest_mtime = None
    if latest:
        try:
            latest_mtime = datetime.fromtimestamp(latest.stat().st_mtime).isoformat()
        except Exception:
            latest_mtime = None
    return {
        "rr_download_dir": str(rr_dir),
        "rr_download_exists": rr_dir.exists(),
        "rr_csv_count": len(files),
        "latest_rr_file": latest.name if latest else None,
        "latest_rr_path": str(latest) if latest else None,
        "latest_rr_date": latest_date,
        "latest_rr_mtime": latest_mtime,
    }


def _delete_latest_rr() -> dict:
    rr_dir = _rr_download_dir()
    if not rr_dir.exists():
        raise FileNotFoundError(f"No existe el directorio RR: {rr_dir}")

    latest, latest_date = _select_latest_rr_for_delete(rr_dir)
    snapshot_dir, snapshot_manifest = _snapshot_rr_delete_state(latest)
    target = snapshot_dir / latest.name

    try:
        shutil.move(str(latest), str(target))

        purged_csvs = []
        for name in _RR_DELETE_DERIVED_CSVS:
            path = DATA_DIR / name
            if _drop_csv_rows_for_date(path, latest_date):
                purged_csvs.append(name)

        purged_jsons = []
        reason_items_path = DATA_DIR / "ENDURANCE_HRV_master_FINAL_reason_items.json"
        if _drop_reason_items_for_date(reason_items_path, latest_date):
            purged_jsons.append(reason_items_path.name)

        for name in (
            "ENDURANCE_HRV_master_CORE_manifest.json",
            "ENDURANCE_HRV_master_FINAL_manifest.json",
            "ENDURANCE_HRV_ssm_shadow_metadata.json",
        ):
            path = DATA_DIR / name
            if path.exists():
                path.unlink()
                purged_jsons.append(name)
    except Exception as exc:
        try:
            _restore_rr_delete_snapshot(snapshot_manifest)
        except Exception as rollback_exc:
            raise RuntimeError(
                f"Borrado del último RR falló y el rollback también falló: {rollback_exc}"
            ) from exc
        raise

    remaining_files = _list_rr_csv_files(rr_dir)

    return {
        "deleted_rr_date": latest_date,
        "deleted_rr_name": latest.name,
        "deleted_rr_source": str(latest),
        "deleted_rr_backup": str(target),
        "delete_snapshot_dir": str(snapshot_dir),
        "delete_snapshot_manifest": str(snapshot_manifest),
        "rr_download_dir": str(rr_dir),
        "remaining_rr_csv_count": len(remaining_files),
        "purged_csvs": purged_csvs,
        "purged_jsons": purged_jsons,
        "rollback_available": True,
        "rebuild_status": "not_requested",
    }


def _extract_rr_date(filename: str) -> str:
    match = re.search(r"(\d{4}-\d{2}-\d{2})", filename)
    if not match:
        raise ValueError(f"No puedo extraer la fecha del RR: {filename}")
    return match.group(1)


def _drop_csv_rows_for_date(path: Path, date_str: str) -> bool:
    if not path.exists():
        return False
    try:
        df = pd.read_csv(path)
    except (FileNotFoundError, pd.errors.EmptyDataError, OSError, ValueError):
        return False
    if "Fecha" not in df.columns:
        return False
    filtered = df[df["Fecha"].astype(str) != date_str].copy()
    if len(filtered) == len(df):
        return False
    write_csv_atomic(filtered.reindex(columns=df.columns), path)
    return True


def _drop_reason_items_for_date(path: Path, date_str: str) -> bool:
    if not path.exists():
        return False
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return False
    if not isinstance(payload, dict):
        return False
    items_by_date = payload.get("items_by_date")
    if not isinstance(items_by_date, dict) or date_str not in items_by_date:
        return False
    items_by_date.pop(date_str, None)
    write_json_atomic(payload, path)
    return True


def _rr_delete_snapshot_manifest_path(snapshot_dir: Path) -> Path:
    return snapshot_dir / "restore_manifest.json"


def _build_rr_delete_snapshot_dir() -> Path:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    return DATA_DIR / "backup" / "deleted_rr" / f"{stamp}_{uuid.uuid4().hex[:8]}"


def _snapshot_rr_delete_state(latest_rr_path: Path) -> tuple[Path, Path]:
    snapshot_dir = _build_rr_delete_snapshot_dir()
    snapshot_dir.mkdir(parents=True, exist_ok=True)

    artifacts = [{"path": str(latest_rr_path), "snapshot_name": latest_rr_path.name, "required": True}]
    artifacts.extend(
        {"path": str(DATA_DIR / name), "snapshot_name": name, "required": False}
        for name in (*_RR_DELETE_DERIVED_CSVS, *_RR_DELETE_DERIVED_JSONS)
    )

    manifest_artifacts = []
    for item in artifacts:
        original_path = Path(item["path"])
        entry = {
            "path": str(original_path),
            "snapshot_name": item["snapshot_name"],
            "required": bool(item["required"]),
            "existed": original_path.exists(),
        }
        if original_path.exists():
            shutil.copy2(original_path, snapshot_dir / item["snapshot_name"])
        manifest_artifacts.append(entry)

    manifest = {
        "created_at": datetime.now().isoformat(),
        "snapshot_dir": str(snapshot_dir),
        "artifacts": manifest_artifacts,
    }
    manifest_path = _rr_delete_snapshot_manifest_path(snapshot_dir)
    write_json_atomic(manifest, manifest_path)
    return snapshot_dir, manifest_path


def _restore_rr_delete_snapshot(manifest_path: Path) -> dict:
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    snapshot_dir = Path(payload["snapshot_dir"])
    restored = []
    removed = []
    for item in payload.get("artifacts", []):
        original_path = Path(item["path"])
        snapshot_path = snapshot_dir / str(item["snapshot_name"])
        if item.get("existed"):
            if not snapshot_path.exists():
                raise FileNotFoundError(f"Falta snapshot para restaurar: {snapshot_path}")
            _restore_file_atomic(snapshot_path, original_path)
            restored.append(original_path.name)
        elif original_path.exists():
            original_path.unlink()
            removed.append(original_path.name)
    return {
        "snapshot_dir": str(snapshot_dir),
        "restored": restored,
        "removed": removed,
    }


def _restore_file_atomic(snapshot_path: Path, target_path: Path) -> None:
    target_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = target_path.parent / f".{target_path.name}.{uuid.uuid4().hex}.tmp"
    try:
        shutil.copy2(snapshot_path, tmp_path)
        os.replace(tmp_path, target_path)
    finally:
        if tmp_path.exists():
            try:
                tmp_path.unlink()
            except OSError:
                pass


def _csv_runtime_diagnostics() -> dict:
    # DATA_DIR resuelto por hrv_app.config (mismo fallback que el pipeline);
    # evita que /api/status mire un directorio distinto del que se escribe.
    data_dir = DATA_DIR
    core_path = data_dir / "ENDURANCE_HRV_master_CORE.csv"
    final_path = data_dir / "ENDURANCE_HRV_master_FINAL.csv"

    quality_counts = {}
    rows = 0
    min_date = None
    max_date = None

    if core_path.exists():
        try:
            with core_path.open("r", encoding="utf-8", newline="") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    rows += 1
                    calidad = (row.get("Calidad") or "").strip()
                    if calidad:
                        quality_counts[calidad] = quality_counts.get(calidad, 0) + 1

                    d = _parse_iso_date(row.get("Fecha", ""))
                    if d is None:
                        continue
                    if min_date is None or d < min_date:
                        min_date = d
                    if max_date is None or d > max_date:
                        max_date = d
        except Exception:
            # Si falla lectura/parsing, devolvemos métricas por defecto.
            pass

    last_final_row = {}
    if final_path.exists():
        try:
            with final_path.open("r", encoding="utf-8", newline="") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    last_final_row = row
        except Exception:
            last_final_row = {}

    return {
        "hrv_data_dir": str(data_dir),
        "core_path": str(core_path),
        "core_exists": core_path.exists(),
        "core_rows": rows,
        "core_min_date": min_date.isoformat() if min_date else None,
        "core_max_date": max_date.isoformat() if max_date else None,
        "core_quality_counts": quality_counts,
        "final_path": str(final_path),
        "final_exists": final_path.exists(),
        "final_last_fecha": last_final_row.get("Fecha") if last_final_row else None,
        "final_last_hr_today": last_final_row.get("HR_today") if last_final_row else None,
        "final_last_rmssd_stable": last_final_row.get("RMSSD_stable") if last_final_row else None,
        "final_last_lnrmssd_today": last_final_row.get("lnRMSSD_today") if last_final_row else None,
        "final_last_lnrmssd_used": last_final_row.get("lnRMSSD_used") if last_final_row else None,
        "final_last_ln_base60": last_final_row.get("ln_base60") if last_final_row else None,
        "final_last_swc_ln": last_final_row.get("SWC_ln") if last_final_row else None,
        "final_last_gate_badge": last_final_row.get("gate_badge") if last_final_row else None,
        "final_last_n_base60": last_final_row.get("n_base60") if last_final_row else None,
        "final_last_gate_razon_base60": last_final_row.get("gate_razon_base60") if last_final_row else None,
        "final_last_reason_text": last_final_row.get("reason_text") if last_final_row else None,
        "final_last_decision_path": last_final_row.get("decision_path") if last_final_row else None,
        "final_last_action_detail": last_final_row.get("Action_detail") if last_final_row else None,
        "final_last_recovery_support_class": last_final_row.get("recovery_support_class") if last_final_row else None,
    }


def _weekly_coach_diagnostics() -> dict:
    weekly_coach_path = DATA_DIR / "ENDURANCE_HRV_weekly_coach.json"
    payload = {
        "weekly_coach_exists": weekly_coach_path.exists(),
        "weekly_coach_iso_week": None,
        "weekly_coach_window_end": None,
        "weekly_coach_data_quality": None,
        "weekly_coach_planning_note": None,
        "weekly_coach_z3_budget_summary": None,
    }
    if not weekly_coach_path.exists():
        return payload

    try:
        weekly_coach = json.loads(weekly_coach_path.read_text(encoding="utf-8"))
    except Exception:
        return payload

    payload["weekly_coach_iso_week"] = weekly_coach.get("iso_week")
    payload["weekly_coach_window_end"] = weekly_coach.get("window_end")
    payload["weekly_coach_data_quality"] = weekly_coach.get("data_quality")
    payload["weekly_coach_planning_note"] = weekly_coach.get("planning_note")
    payload["weekly_coach_z3_budget_summary"] = weekly_coach.get("z3_budget_summary")
    return payload


def _dropbox_runtime_diagnostics() -> dict:
    dropbox_script = Path((os.environ.get("HRV_DROPBOX_RR_SCRIPT") or "egc_to_rr.py").strip() or "egc_to_rr.py")
    dropbox_folder_path = (
        os.environ.get("HRV_DROPBOX_FOLDER_PATH")
        or os.environ.get("DROPBOX_FOLDER_PATH")
        or ""
    ).strip()

    return {
        "dropbox_rr_enabled": env_flag("HRV_DROPBOX_RR_ENABLED", True),
        "dropbox_rr_script": str(dropbox_script),
        "dropbox_rr_script_exists": dropbox_script.exists(),
        "dropbox_rr_no_aux": env_flag("HRV_DROPBOX_NO_AUX", True),
        "dropbox_rr_pair_limit": (os.environ.get("HRV_DROPBOX_PAIR_LIMIT") or "").strip() or None,
        "dropbox_folder_path_set": bool(dropbox_folder_path),
        "dropbox_recursive": env_flag("HRV_DROPBOX_RECURSIVE", True),
        "dropbox_access_token_set": bool((os.environ.get("DROPBOX_ACCESS_TOKEN") or "").strip()),
        "dropbox_refresh_token_set": bool((os.environ.get("DROPBOX_REFRESH_TOKEN") or "").strip()),
        "dropbox_app_key_set": bool((os.environ.get("DROPBOX_APP_KEY") or "").strip()),
        "dropbox_app_secret_set": bool((os.environ.get("DROPBOX_APP_SECRET") or "").strip()),
    }


def _build_status_payload() -> dict:
    token_info = _token_diagnostics()
    csv_info = _csv_runtime_diagnostics()
    weekly_coach_info = _weekly_coach_diagnostics()
    dropbox_info = _dropbox_runtime_diagnostics()
    seed_info = _seed_upload_diagnostics()
    rr_info = _latest_rr_diagnostics()

    payload = _execution_snapshot()
    payload["diagnostics"] = {
        "authorized": token_info.get("token_reason") == "ok",
        **token_info,
        **csv_info,
        **weekly_coach_info,
        **dropbox_info,
        **seed_info,
        **rr_info,
    }
    return payload


def _hrv_summary_title_from_payload(payload: dict) -> str:
    diagnostics = payload.get("diagnostics", {}) if isinstance(payload, dict) else {}
    fecha = str(diagnostics.get("final_last_fecha") or "").strip()
    return f"Lectura HRV de hoy ({fecha})" if fecha else "Lectura HRV de hoy"


def _technical_summary_from_payload(payload: dict) -> str:
    diagnostics = payload.get("diagnostics", {}) if isinstance(payload, dict) else {}

    def _fmt_float(raw: object, decimals: int = 1) -> str:
        try:
            value = float(raw)
        except (TypeError, ValueError):
            return "-"
        return f"{value:.{decimals}f}"

    def _exp_from_log(raw: object) -> str:
        try:
            value = float(raw)
        except (TypeError, ValueError):
            return "-"
        try:
            return f"{math.exp(value):.1f}"
        except OverflowError:
            return "-"

    lines = [
        "Estado actual visible en UI",
        f"Fecha FINAL: {str(diagnostics.get('final_last_fecha') or 'N/A')}",
        f"RMSSD bruto: {_fmt_float(diagnostics.get('final_last_rmssd_stable'))} ms",
        f"HR hoy: {_fmt_float(diagnostics.get('final_last_hr_today'))} lpm",
        f"lnRMSSD bruto: {_fmt_float(diagnostics.get('final_last_lnrmssd_today'), 3)}",
        f"RMSSD usado: {_exp_from_log(diagnostics.get('final_last_lnrmssd_used'))} ms",
        f"lnRMSSD usado: {_fmt_float(diagnostics.get('final_last_lnrmssd_used'), 3)}",
        f"Baseline 60d: {_exp_from_log(diagnostics.get('final_last_ln_base60'))} ms",
        f"SWC_ln: {_fmt_float(diagnostics.get('final_last_swc_ln'), 3)}",
        f"Gate: {str(diagnostics.get('final_last_gate_badge') or 'N/A')} - {str(diagnostics.get('final_last_gate_razon_base60') or 'N/A')}",
        f"Acción: {str(diagnostics.get('final_last_action_detail') or 'N/A')}",
        f"Último RR en disco: {str(diagnostics.get('latest_rr_file') or 'N/A')}",
    ]

    raw_text = str(payload.get("last_output") or payload.get("output") or payload.get("last_error") or "").strip()
    if raw_text:
        lines.extend(["", "Log de la última ejecución", raw_text])
    return "\n".join(lines)


# HTML Template (UI móvil-first)
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Polar HRV Sync v4</title>
    <style>
        :root {
            --bg: #f5f0e6;
            --surface: rgba(255, 252, 247, 0.92);
            --text: #16353a;
            --muted: #5f7478;
            --brand: #0f766e;
            --brand-strong: #0a4b54;
            --accent: #ea6a2a;
            --ok-bg: #e3f3ea;
            --ok-text: #1d6b3f;
            --info-bg: #e3eff8;
            --info-text: #215b79;
            --warn-bg: #fff1dc;
            --warn-text: #9a5a00;
            --error-bg: #fde8e5;
            --error-text: #9f2f2f;
            --shadow: 0 18px 40px rgba(20, 48, 52, 0.12);
            --radius-xl: 8px;
            --radius-md: 4px;
        }
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: "Segoe UI", "Helvetica Neue", Arial, sans-serif;
            color: var(--text);
            min-height: 100vh;
            padding: 14px;
            background:
                radial-gradient(circle at top left, rgba(234, 106, 42, 0.18), transparent 28%),
                radial-gradient(circle at top right, rgba(15, 118, 110, 0.16), transparent 34%),
                linear-gradient(180deg, var(--bg) 0%, #fbf7ef 100%);
        }
        .container { max-width: 720px; margin: 0 auto; display: grid; gap: 14px; }
        .card {
            background: var(--surface);
            backdrop-filter: blur(14px);
            border: 1px solid rgba(255, 255, 255, 0.7);
            border-radius: var(--radius-xl);
            box-shadow: var(--shadow);
            padding: 18px;
        }
        h1 { font-size: 30px; line-height: 1; letter-spacing: -0.04em; margin-bottom: 14px; }
        .subtitle { color: var(--muted); font-size: 14px; line-height: 1.4; margin-bottom: 18px; }
        .button-stack { display: grid; gap: 10px; }
        button {
            appearance: none; width: 100%; min-height: 46px; padding: 8px 10px; border-radius: 8px;
            border: none; font-size: 16px; font-weight: 700; display: inline-flex; align-items: center;
            justify-content: center; gap: 10px; cursor: pointer; transition: transform 0.2s ease, box-shadow 0.2s ease, opacity 0.2s ease;
        }
        button:hover:not(:disabled) { transform: translateY(-1px); }
        button:disabled { opacity: 0.62; cursor: not-allowed; }
        .sync-button { color: #fffdf9; background: linear-gradient(135deg, var(--brand-strong), var(--brand)); xxxbox-shadow: 0 14px 28px rgba(15,118,110,0.22); }
        .sync-button.running, .sessions-button.running { background: linear-gradient(135deg, #215b79, #0f766e); color: #fffdf9; animation: pulse 1.8s ease-in-out infinite; }
        .sync-button.success, .sessions-button.success { background: linear-gradient(135deg, #1d6b3f, #2a9d5b); color: #fffdf9; }
        .sessions-button { color: var(--brand-strong); background: rgba(15,118,110,0.08); border: 1px solid rgba(15,118,110,0.14); }
        .ghost-button { color: var(--accent); background: rgba(234,106,42,0.10); border: 1px solid rgba(234,106,42,0.14); }
        .danger-button { color: #9f2f2f; background: rgba(159,47,47,0.10); border: 1px solid rgba(159,47,47,0.18); }
        .is-hidden { display: none; }
        .status { display: none; margin-top: 12px; padding: 8px 16px; border-radius: 0; font-size: 14px; line-height: 1.45; }
        .status.show { display: block; }
        .status.info { background: var(--info-bg); color: var(--info-text); }
        .status.success { background: var(--ok-bg); color: var(--ok-text); }
        .status.error { background: var(--error-bg); color: var(--error-text); }
        .section-title { font-size: 16px; font-weight: 800; letter-spacing: -0.03em; color: var(--brand-strong); margin-bottom: 12px; }
        .coach-card {
            border: 1px solid rgba(15, 118, 110, 0.14);
            background:
                linear-gradient(180deg, rgba(227, 243, 234, 0.98), rgba(255, 252, 247, 0.96));
        }
        .coach-header {
            display: flex;
            flex-wrap: wrap;
            gap: 8px 10px;
            align-items: center;
            justify-content: space-between;
            margin-bottom: 10px;
        }
        .coach-title {
            font-size: 18px;
            font-weight: 800;
            letter-spacing: -0.03em;
            color: var(--brand-strong);
        }
        .coach-meta {
            display: flex;
            flex-wrap: wrap;
            gap: 8px;
            margin-bottom: 12px;
        }
        .coach-pill {
            display: inline-flex;
            align-items: center;
            gap: 6px;
            padding: 4px 10px;
            border-radius: 999px;
            background: rgba(15, 118, 110, 0.09);
            color: var(--brand-strong);
            font-size: 12px;
            font-weight: 700;
            letter-spacing: 0.01em;
        }
        .coach-label {
            color: var(--muted);
            font-weight: 700;
            margin-right: 4px;
        }
        .coach-note {
            font-size: 15px;
            line-height: 1.55;
            color: var(--text);
            white-space: pre-wrap;
        }
        .coach-z3 {
            margin-top: 10px;
            font-size: 13px;
            line-height: 1.45;
            color: var(--brand-strong);
            background: rgba(15, 118, 110, 0.08);
            border: 1px solid rgba(15, 118, 110, 0.12);
            padding: 8px 10px;
        }
        .hrv-summary-card {
            border: 1px solid rgba(234, 106, 42, 0.18);
            background:
                linear-gradient(180deg, rgba(255, 241, 220, 0.96), rgba(255, 252, 247, 0.97));
        }
        .hrv-summary-title {
            font-size: 18px;
            font-weight: 800;
            letter-spacing: -0.03em;
            color: var(--brand-strong);
            margin-bottom: 10px;
        }
        .hrv-summary-grid {
            display: grid;
            grid-template-columns: repeat(2, minmax(0, 1fr));
            gap: 10px;
            margin-bottom: 12px;
        }
        .hrv-summary-item {
            padding: 10px 12px;
            border-radius: 8px;
            background: rgba(255, 255, 255, 0.78);
            border: 1px solid rgba(234, 106, 42, 0.10);
        }
        .hrv-summary-label {
            font-size: 11px;
            font-weight: 800;
            letter-spacing: 0.08em;
            text-transform: uppercase;
            color: var(--muted);
            margin-bottom: 4px;
        }
        .hrv-summary-value {
            font-size: 15px;
            font-weight: 750;
            line-height: 1.35;
            color: var(--text);
        }
        .hrv-summary-note {
            font-size: 13px;
            line-height: 1.45;
            color: var(--brand-strong);
            background: rgba(234, 106, 42, 0.08);
            border: 1px solid rgba(234, 106, 42, 0.12);
            padding: 8px 10px;
        }
        .coach-source {
            margin-top: 12px;
            font-size: 12px;
            line-height: 1.4;
            color: var(--muted);
        }
        .raw-output {
            padding: 14px; border-radius: 4px; background: #16353a; color: #eef6f5; font-family: Consolas, "Courier New", monospace;
            font-size: 12px; line-height: 1.5; min-height: 320px; max-height: 60vh; overflow-x: hidden; overflow-y: auto; white-space: pre-wrap; word-wrap: break-word;
        }
        .spinner { display: inline-block; width: 16px; height: 16px; border: 2px solid rgba(255,255,255,0.32); border-radius: 50%; border-top-color: #fff; animation: spin 1s linear infinite; }
        @keyframes pulse { 0%, 100% { transform: scale(1); } 50% { transform: scale(0.99); } }
        @keyframes spin { to { transform: rotate(360deg); } }
        @media (min-width: 640px) { body { padding: 20px; } .card { padding: 22px; } }
        @media (max-width: 420px) { body { padding: 10px; } .card { padding: 12px; border-radius: 12px; } h1 { font-size: 28px; } }
    </style>
</head>
<body>
    <div class="container">
        <section class="card">
            <h1>⚡ HRV Sync</h1>
            <!--<p class="subtitle">Sincronización automática de datos HRV</p>-->
            <div class="button-stack">
                <button id="syncBtn" class="sync-button" onclick="syncPolar()"><span id="syncBtnText">Sincronizar HRV</span></button>
                <button id="sessionsBtn" class="sessions-button" onclick="syncSessions()"><span id="sessionsBtnText">Sincronizar sesiones</span></button>
            </div>
            <div id="status" class="status"></div>
        </section>
        <section id="hrvSummaryCard" class="card hrv-summary-card" hidden>
            <div id="hrvSummaryTitle" class="hrv-summary-title">{{ hrv_summary_title }}</div>
            <div class="hrv-summary-grid">
                <div class="hrv-summary-item">
                    <div class="hrv-summary-label">Dato bruto</div>
                    <div id="hrvSummaryRaw" class="hrv-summary-value">-</div>
                </div>
                <div class="hrv-summary-item">
                    <div class="hrv-summary-label">Dato usado por el gate</div>
                    <div id="hrvSummaryUsed" class="hrv-summary-value">-</div>
                </div>
                <div class="hrv-summary-item">
                    <div class="hrv-summary-label">Baseline 60d</div>
                    <div id="hrvSummaryBase" class="hrv-summary-value">-</div>
                </div>
                <div class="hrv-summary-item">
                    <div class="hrv-summary-label">Gate</div>
                    <div id="hrvSummaryGate" class="hrv-summary-value">-</div>
                </div>
            </div>
            <div id="hrvSummaryNote" class="hrv-summary-note">Esperando disponibilidad del resumen HRV...</div>
        </section>
        <section id="weeklyCoachCard" class="card coach-card" hidden>
            <div class="coach-header">
                <div class="coach-title">Coach semanal</div>
            </div>
            <div class="coach-meta">
                <span class="coach-pill"><span class="coach-label">Semana</span><span id="weeklyCoachWeek">-</span></span>
                <span class="coach-pill"><span class="coach-label">Cierre</span><span id="weeklyCoachWindowEnd">-</span></span>
                <span class="coach-pill"><span class="coach-label">Calidad</span><span id="weeklyCoachQuality">-</span></span>
            </div>
            <div id="weeklyCoachNote" class="coach-note">Esperando disponibilidad del resumen semanal...</div>
            <div id="weeklyCoachZ3" class="coach-z3" hidden title="Lectura retrospectiva de Z3 respecto al historico comparable por deporte. No es una prescripcion automatica."></div>
            <div class="coach-source">Fuente visible en UI: <code>ENDURANCE_HRV_weekly_coach.json</code> vía <code>/api/status</code>. Fuentes primarias del método semanal: <code>sessions_day</code>, <code>sessions</code>, <code>FINAL</code>, <code>DASHBOARD</code> y <code>sleep</code>.</div>
        </section>
        <section class="card">
            <div class="section-title">Detalle técnico</div>
            <pre id="rawOutput" class="raw-output">{{ initial_technical_output }}</pre>
            <div class="button-stack" style="margin-top: 14px;">
                <button id="importBtn" class="ghost-button{% if not show_seed_import %} is-hidden{% endif %}" onclick="importSeedCsvs()" {% if not show_seed_import %}hidden{% endif %}><span id="importBtnText">Importar CSV seed</span></button>
                <button id="restoreBackupBtn" class="ghost-button{% if not show_restore_backup %} is-hidden{% endif %}" onclick="restoreFromDropbox()" {% if not show_restore_backup %}hidden{% endif %}><span id="restoreBackupBtnText">Restaurar backup Dropbox</span></button>
                <button id="deleteLastRrBtn" class="danger-button" onclick="deleteLastRr()"><span id="deleteLastRrBtnText">Borrar último RR</span></button>
            </div>
        </section>
    </div>
    <script>
        const UI_KEY = new URLSearchParams(window.location.search).get('key');
        function apiFetch(url, options = {}) {
            const headers = Object.assign({}, options.headers || {});
            if (UI_KEY) headers['X-HRV-KEY'] = UI_KEY;
            return fetch(url, Object.assign({}, options, { headers }));
        }
        function showBanner(kind, message) {
            const status = document.getElementById('status');
            status.className = `status ${kind} show`;
            status.textContent = message;
        }
        function renderTechnicalOutput(rawText) {
            const rawOutput = document.getElementById('rawOutput');
            rawOutput.textContent = rawText || 'Esperando ejecución...';
        }
        function buildTechnicalSummary(data) {
            const diagnostics = data?.diagnostics || {};
            const lines = [];
            lines.push('Estado actual visible en UI');
            lines.push(`Fecha FINAL: ${String(diagnostics.final_last_fecha || 'N/A')}`);
            lines.push(`RMSSD bruto: ${fmtNumber(diagnostics.final_last_rmssd_stable)} ms`);
            lines.push(`HR hoy: ${fmtNumber(diagnostics.final_last_hr_today)} lpm`);
            lines.push(`lnRMSSD bruto: ${fmtNumber(diagnostics.final_last_lnrmssd_today, 3)}`);
            lines.push(`RMSSD usado: ${fmtNumber(expFromLog(diagnostics.final_last_lnrmssd_used))} ms`);
            lines.push(`lnRMSSD usado: ${fmtNumber(diagnostics.final_last_lnrmssd_used, 3)}`);
            lines.push(`Baseline 60d: ${fmtNumber(expFromLog(diagnostics.final_last_ln_base60))} ms`);
            lines.push(`SWC_ln: ${fmtNumber(diagnostics.final_last_swc_ln, 3)}`);
            lines.push(`Gate: ${String(diagnostics.final_last_gate_badge || 'N/A')} - ${String(diagnostics.final_last_gate_razon_base60 || 'N/A')}`);
            lines.push(`Acción: ${String(diagnostics.final_last_action_detail || 'N/A')}`);
            lines.push(`Último RR en disco: ${String(diagnostics.latest_rr_file || 'N/A')}`);
            return lines.join('\\n');
        }
        function renderWeeklyCoachPanel(data) {
            const card = document.getElementById('weeklyCoachCard');
            const week = document.getElementById('weeklyCoachWeek');
            const windowEnd = document.getElementById('weeklyCoachWindowEnd');
            const quality = document.getElementById('weeklyCoachQuality');
            const note = document.getElementById('weeklyCoachNote');
            const z3 = document.getElementById('weeklyCoachZ3');
            const diagnostics = data?.diagnostics || {};
            const exists = Boolean(diagnostics.weekly_coach_exists);
            card.hidden = !exists;
            if (!exists) {
                week.textContent = '-';
                windowEnd.textContent = '-';
                quality.textContent = '-';
                note.textContent = 'Todavía no hay resumen semanal disponible.';
                z3.hidden = true;
                z3.textContent = '';
                return;
            }
            week.textContent = diagnostics.weekly_coach_iso_week || 'Semana no declarada';
            windowEnd.textContent = diagnostics.weekly_coach_window_end || 'Sin cierre';
            quality.textContent = diagnostics.weekly_coach_data_quality || 'sin dato';
            note.textContent = diagnostics.weekly_coach_planning_note || 'Sin planning note disponible.';
            const z3Summary = diagnostics.weekly_coach_z3_budget_summary || '';
            z3.hidden = !z3Summary;
            z3.textContent = z3Summary ? `Contexto Z3 semanal: ${z3Summary}` : '';
        }
        function renderHrvSummaryPanel(data) {
            const card = document.getElementById('hrvSummaryCard');
            const title = document.getElementById('hrvSummaryTitle');
            const raw = document.getElementById('hrvSummaryRaw');
            const used = document.getElementById('hrvSummaryUsed');
            const base = document.getElementById('hrvSummaryBase');
            const gate = document.getElementById('hrvSummaryGate');
            const note = document.getElementById('hrvSummaryNote');
            const diagnostics = data?.diagnostics || {};
            const exists = Boolean(diagnostics.final_exists);
            const summaryDate = String(diagnostics.final_last_fecha || '').trim();
            card.hidden = !exists;
            title.textContent = summaryDate ? `Lectura HRV de hoy (${summaryDate})` : 'Lectura HRV de hoy';
            if (!exists) {
                raw.textContent = '-';
                used.textContent = '-';
                base.textContent = '-';
                gate.textContent = '-';
                note.textContent = 'Todavía no hay salida FINAL disponible.';
                return;
            }

            const rmssdRaw = diagnostics.final_last_rmssd_stable;
            const hrToday = diagnostics.final_last_hr_today;
            const lnToday = diagnostics.final_last_lnrmssd_today;
            const lnUsed = diagnostics.final_last_lnrmssd_used;
            const lnBase = diagnostics.final_last_ln_base60;
            const swcLn = diagnostics.final_last_swc_ln;
            const gateBadge = diagnostics.final_last_gate_badge || 'N/A';
            const gateReason = diagnostics.final_last_gate_razon_base60 || 'N/A';
            const action = diagnostics.final_last_action_detail || 'N/A';

            raw.textContent = `${fmtNumber(rmssdRaw)} ms · HR ${fmtNumber(hrToday)} lpm · lnRMSSD bruto ${fmtNumber(lnToday, 3)}`;
            used.textContent = `${fmtNumber(expFromLog(lnUsed))} ms · lnRMSSD usado ${fmtNumber(lnUsed, 3)}`;
            base.textContent = `${fmtNumber(expFromLog(lnBase))} ms · SWC_ln ${fmtNumber(swcLn, 3)}`;
            gate.textContent = `${gateBadge} · ${gateReason}`;
            note.textContent = `El gate compara el valor usado por la decisión con BASE60. Hoy la acción es ${action}.`;
        }
        function fmtNumber(value, decimals = 1) {
            const n = Number(value);
            return Number.isFinite(n) ? n.toFixed(decimals) : '-';
        }
        function expFromLog(value) {
            const n = Number(value);
            return Number.isFinite(n) ? Math.exp(n) : NaN;
        }
        function fmtDateFromRrName(value) {
            const raw = String(value || '').trim();
            const match = raw.match(/(\\d{4})-(\\d{2})-(\\d{2})/);
            if (!match) return '';
            return `${match[3]}/${match[2]}/${match[1]}`;
        }
        function setButtonState(jobType, state) {
            const mapping = { hrv: ['syncBtn', 'syncBtnText', 'Sincronizar HRV'], sessions: ['sessionsBtn', 'sessionsBtnText', 'Sincronizar sesiones'] };
            const target = mapping[jobType];
            if (!target) return;
            const [btnId, textId, idleText] = target;
            const btn = document.getElementById(btnId);
            const text = document.getElementById(textId);
            btn.classList.remove('running', 'success');
            if (state === 'running') {
                btn.classList.add('running');
                text.innerHTML = '<span class="spinner"></span> ' + (jobType === 'hrv' ? 'Sincronizando HRV...' : 'Sincronizando sesiones...');
            } else if (state === 'success') {
                btn.classList.add('success');
                text.textContent = jobType === 'hrv' ? 'Sincronización HRV ok' : 'Sincronización sesiones ok';
            } else {
                text.textContent = idleText;
            }
        }
        function applyUiState(data) {
            const syncBtn = document.getElementById('syncBtn');
            const sessionsBtn = document.getElementById('sessionsBtn');
            const importBtn = document.getElementById('importBtn');
            const deleteLastRrBtn = document.getElementById('deleteLastRrBtn');
            const rawText = data.last_output || data.output || data.last_error || '';
            const summaryText = buildTechnicalSummary(data);
            setButtonState('hrv', 'idle');
            setButtonState('sessions', 'idle');
            if (data.running && data.job_type === 'hrv') setButtonState('hrv', 'running');
            else if (data.running && data.job_type === 'sessions') setButtonState('sessions', 'running');
            syncBtn.disabled = Boolean(data.running);
            sessionsBtn.disabled = Boolean(data.running);
            if (importBtn) importBtn.disabled = Boolean(data.running);
            if (deleteLastRrBtn) {
                const latestRrPath = data?.diagnostics?.latest_rr_path;
                deleteLastRrBtn.disabled = Boolean(data.running || !latestRrPath);
            }
            renderHrvSummaryPanel(data);
            renderWeeklyCoachPanel(data);
            renderTechnicalOutput(rawText ? `${summaryText}\\n\\nLog de la última ejecución\\n${rawText}` : summaryText);
        }
        async function refreshDashboard() {
            try {
                const response = await apiFetch('/api/status');
                const data = await response.json();
                applyUiState(data);
                if (data.running) showBanner('info', data.job_type === 'sessions' ? 'Procesando sincronización de sesiones...' : 'Procesando sincronización HRV...');
                else if (data.success === true) showBanner('success', data.message || 'Última operación completada correctamente.');
                else if (data.success === false) showBanner('error', data.last_error || data.message || 'La última operación terminó con error.');
            } catch (error) {
                console.error('Error actualizando status:', error);
            }
        }
        async function syncPolar() { await startJob('/api/sync', 'hrv', 'Iniciando sincronización HRV...'); }
        async function syncSessions() { await startJob('/api/sync-sessions', 'sessions', 'Iniciando sincronización de sesiones...'); }
        async function startJob(url, jobType, startMessage) {
            const stateTextId = jobType === 'hrv' ? 'syncBtnText' : 'sessionsBtnText';
            const btn = document.getElementById(jobType === 'hrv' ? 'syncBtn' : 'sessionsBtn');
            const btnText = document.getElementById(stateTextId);
            document.getElementById('syncBtn').disabled = true;
            document.getElementById('sessionsBtn').disabled = true;
            btn.classList.add('running');
            btnText.innerHTML = '<span class="spinner"></span> ' + (jobType === 'hrv' ? 'Sincronizando HRV...' : 'Sincronizando sesiones...');
            showBanner('info', startMessage);
            try {
                const response = await apiFetch(url, { method: 'POST' });
                const data = await response.json();
                if (!response.ok) { showSyncError(data, jobType); return; }
                if (data.message && /iniciada/i.test(data.message)) await pollSyncStatus();
                else if (data.success) showSyncSuccess(data, jobType);
                else showSyncError(data, jobType);
            } catch (error) {
                btn.classList.remove('running');
                btnText.textContent = jobType === 'hrv' ? 'Sincronizar HRV' : 'Sincronizar sesiones';
                document.getElementById('syncBtn').disabled = false;
                document.getElementById('sessionsBtn').disabled = false;
                showBanner('error', 'Error de conexión: ' + error.message);
            }
        }
        async function importSeedCsvs() {
            const btn = document.getElementById('importBtn');
            const btnText = document.getElementById('importBtnText');
            btn.disabled = true;
            btnText.innerHTML = '<span class="spinner"></span> Importando...';
            showBanner('info', 'Importando CSV seed a /data...');
            try {
                const response = await apiFetch('/api/import-seed', { method: 'POST' });
                const data = await response.json();
                if (!response.ok || !data.success) throw new Error(data.error || 'Error importando CSV seed');
                renderTechnicalOutput(JSON.stringify(data, null, 2));
                showBanner('success', 'CSV seed importados a /data');
                await refreshDashboard();
            } catch (error) {
                showBanner('error', error.message);
            } finally {
                btn.disabled = false;
                btnText.textContent = 'Importar CSV seed';
            }
        }
        async function restoreFromDropbox() {
            const btn = document.getElementById('restoreBackupBtn');
            const btnText = document.getElementById('restoreBackupBtnText');
            const confirmed = window.confirm('Se restaurarán los CSV del último backup en Dropbox. Los archivos actuales se guardarán en data/backup/. ¿Continuar?');
            if (!confirmed) return;
            btn.disabled = true;
            btnText.innerHTML = '<span class="spinner"></span> Restaurando...';
            showBanner('info', 'Descargando backup desde Dropbox...');
            try {
                const response = await apiFetch('/api/restore-backup', { method: 'POST' });
                const data = await response.json();
                if (!response.ok || !data.success) throw new Error(data.error || 'Error restaurando backup');
                renderTechnicalOutput(JSON.stringify(data, null, 2));
                showBanner('success', `Backup restaurado: ${data.restored?.length || 0} archivos desde ${data.source_folder || 'Dropbox'}`);
                await refreshDashboard();
            } catch (error) {
                showBanner('error', error.message);
            } finally {
                btn.disabled = false;
                btnText.textContent = 'Restaurar backup Dropbox';
            }
        }
        async function deleteLastRr() {
            const btn = document.getElementById('deleteLastRrBtn');
            const btnText = document.getElementById('deleteLastRrBtnText');
            const statusResponse = await apiFetch('/api/status');
            const statusData = await statusResponse.json();
            const latest = statusData?.diagnostics?.latest_rr_file;
            if (!latest) {
                showBanner('error', 'No hay ningún RR reciente para borrar.');
                return;
            }
            const latestDate = fmtDateFromRrName(latest);
            const latestLabel = latestDate ? `${latest} (${latestDate})` : latest;
            const confirmed = window.confirm(`Se moverá a backup el último RR: ${latestLabel}. Después tendrás que repetir la medición y volver a sincronizar. ¿Continuar?`);
            if (!confirmed) return;
            btn.disabled = true;
            btnText.innerHTML = '<span class="spinner"></span> Borrando...';
            showBanner('info', `Moviendo ${latestLabel} a backup...`);
            try {
                const response = await apiFetch('/api/delete-latest-rr', { method: 'POST' });
                const data = await response.json();
                if (!response.ok || !data.success) throw new Error(data.error || 'Error borrando el último RR');
                renderTechnicalOutput(JSON.stringify(data, null, 2));
                showBanner('success', `Último RR movido a backup: ${data.deleted_rr_name}`);
                await refreshDashboard();
            } catch (error) {
                showBanner('error', error.message);
            } finally {
                btn.disabled = false;
                btnText.textContent = 'Borrar último RR';
            }
        }
        async function pollSyncStatus() {
            let attempts = 0;
            const syncTimeoutSec = Number('{{ sync_timeout_sec }}') || 1200;
            const pollIntervalSec = 2;
            const maxAttempts = Math.ceil(syncTimeoutSec / pollIntervalSec);
            while (attempts < maxAttempts) {
                await new Promise(resolve => setTimeout(resolve, 2000));
                try {
                    const response = await apiFetch('/api/status');
                    const data = await response.json();
                    applyUiState(data);
                    if (!data.running) {
                        if (data.success) showSyncSuccess(data, data.job_type);
                        else if (data.success === false) showSyncError(data, data.job_type);
                        return;
                    }
                    showBanner('info', 'Procesando ' + (data.job_type === 'sessions' ? 'sincronización de sesiones' : 'sincronización HRV') + '... ' + Math.floor(attempts * pollIntervalSec / 60) + 'm ' + (attempts * pollIntervalSec % 60) + 's');
                    attempts++;
                } catch (error) {
                    console.error('Error polling status:', error);
                    attempts++;
                }
            }
            document.getElementById('syncBtn').disabled = false;
            document.getElementById('sessionsBtn').disabled = false;
            setButtonState('hrv', 'idle');
            setButtonState('sessions', 'idle');
            showBanner('error', 'Timeout en UI: la sincronización tardó más de lo esperado');
        }
        function showSyncSuccess(data, jobType) {
            document.getElementById('syncBtn').disabled = false;
            document.getElementById('sessionsBtn').disabled = false;
            setButtonState('hrv', 'idle');
            setButtonState('sessions', 'idle');
            if (jobType) setButtonState(jobType, 'success');
            renderTechnicalOutput(data.last_output || data.output || '');
            showBanner('success', data.message || 'Proceso completado');
            setTimeout(() => { setButtonState('hrv', 'idle'); setButtonState('sessions', 'idle'); }, 3000);
        }
        function showSyncError(data, jobType) {
            document.getElementById('syncBtn').disabled = false;
            document.getElementById('sessionsBtn').disabled = false;
            setButtonState('hrv', 'idle');
            setButtonState('sessions', 'idle');
            renderTechnicalOutput(data.last_output || data.output || data.error || data.last_error || 'Error desconocido');
            showBanner('error', data.error || data.last_error || data.message || 'Error desconocido');
        }
        setInterval(refreshDashboard, 30000);
        refreshDashboard();
    </script>
</body>
</html>
"""

@app.route('/')
def index():
    """Interfaz web principal"""
    initial_payload = _build_status_payload()
    return render_template_string(
        HTML_TEMPLATE,
        sync_timeout_sec=_sync_timeout_seconds(),
        show_seed_import=env_flag('HRV_SHOW_SEED_IMPORT', SEED_UPLOAD_DIR.exists()),
        show_restore_backup=env_flag('HRV_BACKUP_DROPBOX_ENABLED', False),
        hrv_summary_title=_hrv_summary_title_from_payload(initial_payload),
        initial_technical_output=_technical_summary_from_payload(initial_payload),
    )


@app.route('/api/sync', methods=['POST'])
def sync():
    """Ejecutar sincronización Polar"""
    if not TOKEN_PATH_V4.exists():
        return jsonify({
            'success': False,
            'error': 'Falta autorización. Abre /auth para iniciar sesión en Polar y autorizar la app.'
        }), 400

    if not _try_begin_execution('hrv'):
        return jsonify({
            'success': False,
            'error': f'Ya hay un proceso en curso: {_job_label(_execution_snapshot().get("job_type"))}'
        }), 409

    thread = threading.Thread(target=run_sync, daemon=True)
    try:
        thread.start()
    except Exception as exc:
        _set_execution_result('hrv', False, '', str(exc), 'Error iniciando sincronización')
        return jsonify({
            'success': False,
            'error': str(exc),
            'job_type': 'hrv',
        }), 500
    thread.join(timeout=1)

    state = _execution_snapshot()
    if state['success'] is not None and state.get('job_type') == 'hrv':
        return jsonify({
            'success': state['success'],
            'message': 'Sincronización completada' if state['success'] else 'Error en sincronización',
            'output': state['last_output'],
            'error': state['last_error'],
            'job_type': 'hrv',
        })

    return jsonify({
        'success': True,
        'message': 'Sincronización iniciada',
        'output': 'Procesando...',
        'job_type': 'hrv',
    }), 202


def run_sync():
    """Ejecutar polar_hrv_automation.py --process."""
    _run_subprocess_job(
        [sys.executable, 'polar_hrv_automation.py', '--process'],
        'hrv',
        'Sincronización completada',
        env_extra={
            'PYTHONUTF8': '1',
            'HRV_QUIET': '1',
        },
    )


@app.route('/api/sync-sessions', methods=['POST'])
def sync_sessions():
    """Ejecutar sincronización de sesiones desde Intervals."""
    if not _try_begin_execution('sessions'):
        return jsonify({
            'success': False,
            'error': f'Ya hay un proceso en curso: {_job_label(_execution_snapshot().get("job_type"))}'
        }), 409

    thread = threading.Thread(target=run_sessions_sync, daemon=True)
    try:
        thread.start()
    except Exception as exc:
        _set_execution_result('sessions', False, '', str(exc), 'Error iniciando sincronización de sesiones')
        return jsonify({
            'success': False,
            'error': str(exc),
            'job_type': 'sessions',
        }), 500
    thread.join(timeout=1)

    state = _execution_snapshot()
    if state['success'] is not None and state.get('job_type') == 'sessions':
        return jsonify({
            'success': state['success'],
            'message': state.get('message') or ('Sincronización de sesiones completada' if state['success'] else 'Error en sincronización de sesiones'),
            'output': state['last_output'],
            'error': state['last_error'],
            'job_type': 'sessions',
        })

    return jsonify({
        'success': True,
        'message': 'Sincronización de sesiones iniciada',
        'output': 'Procesando...',
        'job_type': 'sessions',
    }), 202


def run_sessions_sync():
    """Ejecutar build_sessions.py --update."""
    _run_subprocess_job(
        [sys.executable, 'build_sessions.py', '--update'],
        'sessions',
        'Sincronización de sesiones completada',
    )


@app.route('/api/status', methods=['GET'])
def get_status():
    """Obtener estado actual"""
    try:
        return jsonify(_build_status_payload())
    except Exception as exc:
        app.logger.exception("/api/status failed")
        payload = _execution_snapshot()
        payload["success"] = False
        payload["error"] = str(exc)
        payload["diagnostics"] = {
            "authorized": False,
            "status_error": str(exc),
        }
        return jsonify(payload), 500


@app.route('/api/import-seed', methods=['POST'])
def import_seed():
    """Importar CSV canónicos desde seed_upload hacia HRV_DATA_DIR."""
    if not _try_begin_execution('seed_import'):
        return jsonify({
            'success': False,
            'error': f'Hay un proceso en curso: {_job_label(_execution_snapshot().get("job_type"))}. Espera a que termine antes de importar.'
        }), 409

    try:
        result = _import_seed_csvs()
        _set_execution_result(
            'seed_import',
            True,
            json.dumps(result, ensure_ascii=False, indent=2),
            '',
            'CSV seed importados',
        )
        return jsonify({
            'success': True,
            'message': 'CSV seed importados',
            'job_type': 'seed_import',
            **result,
        })
    except Exception as exc:
        _set_execution_result('seed_import', False, '', str(exc), 'Error importando CSV seed')
        return jsonify({
            'success': False,
            'error': str(exc),
            'job_type': 'seed_import',
        }), 400


@app.route('/api/restore-backup', methods=['POST'])
def restore_backup_endpoint():
    """Restaurar CSV canónicos desde el último backup en Dropbox."""
    if not _try_begin_execution('restore_backup'):
        return jsonify({
            'success': False,
            'error': f'Hay un proceso en curso: {_job_label(_execution_snapshot().get("job_type"))}. Espera a que termine antes de restaurar.'
        }), 409

    try:
        from hrv_app.backup_dropbox import restore_backup
        result = restore_backup()
        _set_execution_result(
            'restore_backup',
            True,
            json.dumps(result, ensure_ascii=False, indent=2),
            '',
            'Backup restaurado desde Dropbox',
        )
        return jsonify({
            'success': True,
            'message': 'Backup restaurado desde Dropbox',
            'job_type': 'restore_backup',
            **result,
        })
    except Exception as exc:
        _set_execution_result('restore_backup', False, '', str(exc), 'Error restaurando backup')
        return jsonify({
            'success': False,
            'error': str(exc),
            'job_type': 'restore_backup',
        }), 400


@app.route('/api/delete-latest-rr', methods=['POST'])
def delete_latest_rr():
    """Mover a backup el último RR CSV del directorio operativo."""
    if not _try_begin_execution('delete_rr'):
        return jsonify({
            'success': False,
            'error': f'Hay un proceso en curso: {_job_label(_execution_snapshot().get("job_type"))}. Espera a que termine antes de borrar el último RR.'
        }), 409

    try:
        result = _delete_latest_rr()
        _set_execution_result(
            'delete_rr',
            True,
            json.dumps(result, ensure_ascii=False, indent=2),
            '',
            'Último RR movido a backup',
        )
        return jsonify({
            'success': True,
            'message': 'Último RR movido a backup',
            'job_type': 'delete_rr',
            **result,
        })
    except Exception as exc:
        _set_execution_result('delete_rr', False, '', str(exc), 'Error borrando el último RR')
        return jsonify({
            'success': False,
            'error': str(exc),
            'job_type': 'delete_rr',
        }), 400


@app.route('/auth', strict_slashes=False)
def auth():
    """Iniciar flujo OAuth (web) con Polar"""
    raw_client_id2 = os.environ.get("POLAR_CLIENT_ID2")
    raw_client_id = os.environ.get("POLAR_CLIENT_ID")
    client_id_source = "POLAR_CLIENT_ID2" if raw_client_id2 else "POLAR_CLIENT_ID"
    client_id = (raw_client_id2 or raw_client_id or "").strip()
    client_secret = (os.environ.get("POLAR_CLIENT_SECRET") or "").strip()
    if not client_id or not client_secret:
        return jsonify({'error': 'POLAR_CLIENT_ID o POLAR_CLIENT_SECRET no configurados'}), 500

    redirect_uri = _redirect_uri()
    state = _issue_oauth_state()
    return redirect(build_auth_url_v4(client_id, redirect_uri, POLAR_V4_SCOPES, state))


@app.route('/auth/callback', methods=['GET'], strict_slashes=False)
@app.route('/oauth/callback', methods=['GET'], strict_slashes=False)
def oauth_callback():
    """
    Manejar callback OAuth de Polar AccessLink
    Este endpoint recibe el código de autorización después de que
    el usuario autoriza la app en Polar Flow
    """
    code = request.args.get('code')
    error = request.args.get('error')
    error_description = request.args.get('error_description')

    if error:
        return f"""
        <html>
        <head>
            <meta charset="UTF-8">
            <title>Error de Autorización</title>
        </head>
        <body style="font-family: Arial; text-align: center; padding: 50px;">
            <h1>❌ Error de Autorización</h1>
            <p><strong>{escape(error)}</strong></p>
            <p>{escape(error_description or 'Error desconocido')}</p>
            <br>
            <a href="/" style="color: #667eea; text-decoration: none;">← Volver a la app</a>
        </body>
        </html>
        """, 400

    if not code:
        return """
        <html>
        <head>
            <meta charset="UTF-8">
            <title>Error</title>
        </head>
        <body style="font-family: Arial; text-align: center; padding: 50px;">
            <h1>⚠️ Error</h1>
            <p>No se recibió código de autorización</p>
            <br>
            <a href="/" style="color: #667eea; text-decoration: none;">← Volver a la app</a>
        </body>
        </html>
        """, 400

    state_valid = _consume_oauth_state((request.args.get('state') or '').strip())
    if not state_valid:
        return f"""
        <html>
        <head>
            <meta charset="UTF-8">
            <title>Error</title>
        </head>
        <body style="font-family: Arial; text-align: center; padding: 50px;">
            <h1>⚠️ Error</h1>
            <p>Estado OAuth inválido o caducado. Vuelve a iniciar la autorización desde <a href="/auth">/auth</a>.</p>
            <br>
            <a href="/auth" style="color: #667eea; text-decoration: none;">← Reintentar autorización</a>
        </body>
        </html>
        """, 400

    try:
        client_id = (os.environ.get("POLAR_CLIENT_ID2") or os.environ.get("POLAR_CLIENT_ID") or "").strip()
        client_secret = (os.environ.get("POLAR_CLIENT_SECRET") or "").strip()
        if not client_id or not client_secret:
            raise RuntimeError("Credenciales POLAR_CLIENT_ID / POLAR_CLIENT_SECRET no configuradas")

        redirect_uri = _redirect_uri()

        token_json = exchange_code_for_token_v4(code, client_id, client_secret, redirect_uri)
        persist_authorized_bundle(TOKEN_PATH_V4, token_json, scopes=POLAR_V4_SCOPES)

        token_notice = ""

        success_html = """
        <html>
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Autorización Exitosa</title>
            <style>
                body {
                    font-family: "Segoe UI", "Helvetica Neue", Arial, sans-serif;
                    background: linear-gradient(180deg, #f5f0e6 0%, #d8ebe6 100%);
                    min-height: 100vh;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    margin: 0;
                    padding: 20px;
                    color: #16353a;
                }
                .card {
                    width: min(100%, 420px);
                    background: rgba(255, 252, 247, 0.92);
                    border: 1px solid rgba(255,255,255,0.7);
                    border-radius: 24px;
                    box-shadow: 0 18px 40px rgba(20, 48, 52, 0.12);
                    padding: 30px 24px;
                    text-align: center;
                }
                .pill {
                    display: inline-flex;
                    padding: 7px 12px;
                    border-radius: 999px;
                    background: #e3f3ea;
                    color: #1d6b3f;
                    font-size: 12px;
                    font-weight: 700;
                    letter-spacing: 0.06em;
                    text-transform: uppercase;
                }
                h1 {
                    margin: 18px 0 10px;
                    font-size: 30px;
                    line-height: 1;
                    letter-spacing: -0.04em;
                }
                p {
                    margin: 0 0 12px;
                    color: #5f7478;
                    line-height: 1.45;
                }
                .btn {
                    display: inline-flex;
                    align-items: center;
                    justify-content: center;
                    width: 100%;
                    min-height: 52px;
                    margin-top: 10px;
                    border-radius: 16px;
                    text-decoration: none;
                    color: #fffdf9;
                    background: linear-gradient(135deg, #0a4b54, #0f766e);
                    font-weight: 700;
                }
                .countdown {
                    margin-top: 18px;
                    font-size: 13px;
                    color: #7a8a8d;
                }
            </style>
        </head>
        <body>
            <div class="card">
                <div class="pill">OAuth completado</div>
                <h1>Polar autorizado</h1>
                <p>Polar AccessLink ha sido autorizado correctamente.</p>
                <p>Ya puedes volver a la app y lanzar la sincronización.</p>
                __TOKEN_NOTICE__
                <a href="/" class="btn">Volver a la App</a>
                <p class="countdown">Esta ventana se cerrará en <span id="counter">5</span> segundos...</p>
            </div>
            <script>
                let count = 5;
                const counter = document.getElementById('counter');
                const interval = setInterval(() => {
                    count--;
                    counter.textContent = count;
                    if (count <= 0) {
                        clearInterval(interval);
                        window.close();
                        setTimeout(() => {
                            window.location.href = '/';
                        }, 500);
                    }
                }, 1000);
            </script>
        </body>
        </html>
        """

        return success_html.replace("__TOKEN_NOTICE__", token_notice)

    except Exception as e:
        return f"""
        <html>
        <body style="font-family: Arial; text-align: center; padding: 50px;">
            <h1>⚠️ Error</h1>
            <p>No se pudo guardar el código de autorización: {escape(str(e))}</p>
            <br>
            <a href="/" style="color: #667eea; text-decoration: none;">← Volver a la app</a>
        </body>
        </html>
        """, 500

def _final_staleness() -> dict:
    """Última Fecha del FINAL y días transcurridos, para el monitor externo."""
    final_path = DATA_DIR / "ENDURANCE_HRV_master_FINAL.csv"
    last_fecha = None
    if final_path.exists():
        try:
            with final_path.open("r", encoding="utf-8", newline="") as f:
                for row in csv.DictReader(f):
                    raw = (row.get("Fecha") or "").strip()
                    if raw:
                        last_fecha = raw
        except Exception:
            last_fecha = None

    days_stale = None
    if last_fecha:
        parsed = _parse_iso_date(last_fecha)
        if parsed is not None:
            days_stale = (datetime.now().date() - parsed).days
    return {"final_last_fecha": last_fecha, "days_stale": days_stale}


def _stale_max_days(default: int = 3) -> int:
    raw = (os.environ.get("HRV_STALE_MAX_DAYS") or "").strip()
    try:
        value = int(raw)
        return value if value >= 1 else default
    except ValueError:
        return default


@app.route('/health', methods=['GET'])
def health():
    """Health check para Railway/monitor externo.

    Sin parámetros siempre devuelve 200 (liveness; no rompe healthchecks de
    despliegue). Con ?strict=1 devuelve 503 si el FINAL falta o su última
    fecha supera HRV_STALE_MAX_DAYS — apunta ahí un monitor externo
    (UptimeRobot, healthchecks.io) para enterarte de syncs fallando en silencio.
    """
    staleness = _final_staleness()
    stale_max = _stale_max_days()
    payload = {
        'status': 'healthy',
        'timestamp': datetime.now().isoformat(),
        'stale_max_days': stale_max,
        **staleness,
    }
    strict = (request.args.get('strict') or '').strip().lower() in {'1', 'true', 'yes'}
    if strict:
        days = staleness.get('days_stale')
        if days is None or days > stale_max:
            payload['status'] = 'stale'
            return jsonify(payload), 503
    return jsonify(payload)


def _safe_console_print(text: str) -> None:
    """Evita que el banner local falle en consolas Windows con cp1252."""
    try:
        print(text)
    except UnicodeEncodeError:
        fallback = (
            text.replace("🌐", "[web]")
            .replace("📱", "[ui]")
            .replace("💡", "[tip]")
        )
        print(fallback.encode("ascii", errors="replace").decode("ascii"))
 

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    
    _safe_console_print("\n" + "="*60)
    _safe_console_print("  POLAR HRV - WEB UI")
    _safe_console_print("="*20)
    _safe_console_print(f"\n🌐 Servidor iniciado en puerto {port}")
    _safe_console_print(f"\n📱 Accede desde:")
    _safe_console_print(f"   - Local: http://localhost:{port}")
    _safe_console_print(f"   - Railway: https://tu-app.up.railway.app")
    _safe_console_print("\n💡 Abre desde cualquier dispositivo (móvil, tablet, PC)")
    _safe_console_print("="*20 + "\n")
    
    app.run(host='0.0.0.0', port=port, debug=False)








