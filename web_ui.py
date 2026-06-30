#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Web UI para Polar HRV Automation
Accesible desde cualquier dispositivo (móvil, tablet, PC)
"""

from flask import Flask, render_template, jsonify, request, redirect
from flask_cors import CORS
from jinja2 import TemplateNotFound
from werkzeug.middleware.proxy_fix import ProxyFix
import subprocess
import sys
import time
import os
import csv
import html
import re
import shutil
from pathlib import Path
from datetime import datetime
import threading
import json
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
from hrv_app.messages import API as MSG, OAUTH as OAUTH_MSG, CONSOLE as CONSOLE_MSG
from hrv_app.polar_utils import env_flag
from hrv_app import ui_view
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


DEFAULT_UI_COPY = {
    "dashboard_title": "HRV Sync",
    "sync_hrv": "Sincronizar HRV",
    "sync_sessions": "Sincronizar sesiones",
    "hrv_summary_title_base": "Lectura HRV de hoy",
    "hrv_summary_raw": "Dato bruto",
    "hrv_summary_used": "Dato usado por el gate",
    "hrv_summary_base": "Baseline 60d",
    "hrv_summary_gate": "Gate",
    "hrv_summary_waiting": "Esperando disponibilidad del resumen HRV...",
    "technical_title": "Detalle técnico",
    "restore_backup": "Restaurar backup Dropbox",
    "delete_last_rr": "Borrar último RR",
}

DEFAULT_UI_RUNTIME_CONFIG = {
    "text": {
        "technicalOutputPlaceholder": "Esperando ejecución...",
        "hrvSummaryUnavailable": "Todavía no hay salida FINAL disponible.",
        "syncRunningHrv": "Sincronizando HRV...",
        "syncRunningSessions": "Sincronizando sesiones...",
        "syncSuccessHrv": "Sincronización HRV ok",
        "syncSuccessSessions": "Sincronización sesiones ok",
        "bannerRunningHrv": "Procesando sincronización HRV...",
        "bannerRunningSessions": "Procesando sincronización de sesiones...",
        "bannerLastSuccess": "Última operación completada correctamente.",
        "bannerLastError": "La última operación terminó con error.",
        "bannerStartHrv": "Iniciando sincronización HRV...",
        "bannerStartSessions": "Iniciando sincronización de sesiones...",
        "bannerConnectionErrorPrefix": "Error de conexión: ",
        "importStart": "Importando CSV seed a /data...",
        "importSuccess": "CSV seed importados a /data",
        "importButtonRunning": "Importando...",
        "restoreConfirm": "Se restaurarán los CSV del último backup en Dropbox. Los archivos actuales se guardarán en data/backup/. ¿Continuar?",
        "restoreStart": "Descargando backup desde Dropbox...",
        "restoreSuccessFallbackSource": "Dropbox",
        "restoreButtonRunning": "Restaurando...",
        "deleteNoLatest": "No hay ningún RR reciente para borrar.",
        "deleteButtonRunning": "Borrando...",
        "pollStatusSessions": "sincronización de sesiones",
        "pollStatusHrv": "sincronización HRV",
        "pollTimeout": "Timeout en UI: la sincronización tardó más de lo esperado",
        "processCompleted": "Proceso completado",
        "unknownError": "Error desconocido",
    },
    "templates": {
        "restoreSuccess": "Backup restaurado: {count} archivos desde {source}",
        "deleteConfirm": "Se moverá a backup el último RR: {label}. Después tendrás que repetir la medición y volver a sincronizar. ¿Continuar?",
        "deleteStart": "Moviendo {label} a backup...",
        "deleteSuccess": "Último RR movido a backup: {name}",
        "pollStatus": "Procesando {jobLabel}... {minutes}m {seconds}s",
    },
}


# Helpers de formato y composición del resumen HRV viven en hrv_app.ui_view.


def _ai_daily_brief_diagnostics(final_date: str | None) -> dict:
    brief_path = DATA_DIR / "ENDURANCE_HRV_ai_daily_brief_latest.json"
    payload = {
        "ai_daily_brief_path": str(brief_path),
        "ai_daily_brief_exists": brief_path.exists(),
        "ai_daily_brief_status": None,
        "ai_daily_brief_date": None,
        "ai_daily_brief_published": False,
        "ai_daily_brief_summary": None,
        "ai_daily_brief_detail": None,
        "ai_daily_brief_tone": None,
        "ai_daily_brief_source_mode": None,
        "ai_daily_brief_reason": None,
        "ai_daily_brief_matches_final": False,
    }
    if not brief_path.exists():
        return payload

    try:
        brief = json.loads(brief_path.read_text(encoding="utf-8"))
    except Exception:
        return payload

    brief_date = ui_view.normalize_summary_text(brief.get("date")) or None
    payload.update(
        {
            "ai_daily_brief_status": brief.get("status"),
            "ai_daily_brief_date": brief_date,
            "ai_daily_brief_published": bool(brief.get("published")),
            "ai_daily_brief_summary": brief.get("summary"),
            "ai_daily_brief_detail": brief.get("detail"),
            "ai_daily_brief_tone": brief.get("tone"),
            "ai_daily_brief_source_mode": brief.get("source_mode"),
            "ai_daily_brief_reason": brief.get("reason"),
            "ai_daily_brief_matches_final": bool(brief_date and final_date and brief_date == final_date),
        }
    )
    return payload


def _compose_hrv_summary_diagnostics(diagnostics: dict) -> dict:
    unavailable_text = UI_RUNTIME_CONFIG.get("text", {}).get(
        "hrvSummaryUnavailable",
        ui_view.DEFAULT_UNAVAILABLE_TEXT,
    )
    return ui_view.compose_hrv_summary(diagnostics, unavailable_text=unavailable_text)


def _merge_template_json(fallback: dict, payload: dict) -> dict:
    merged = json.loads(json.dumps(fallback))
    for key, value in payload.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _merge_template_json(merged[key], value)
        else:
            merged[key] = value
    return merged


def _load_template_json(template_name: str, fallback: dict) -> dict:
    try:
        template = app.jinja_env.get_template(template_name)
        payload = json.loads(template.render())
    except (TemplateNotFound, json.JSONDecodeError, TypeError, ValueError) as exc:
        app.logger.warning("Template JSON via Jinja fallback for %s: %s", template_name, exc)
        template_path = Path(app.root_path) / "templates" / template_name
        try:
            payload = json.loads(template_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, TypeError, ValueError) as raw_exc:
            app.logger.warning("Template JSON file fallback for %s: %s", template_name, raw_exc)
            return json.loads(json.dumps(fallback))
    if not isinstance(payload, dict):
        app.logger.warning("Template JSON fallback for %s: expected object", template_name)
        return json.loads(json.dumps(fallback))
    return _merge_template_json(fallback, payload)


UI_COPY = _load_template_json("data/ui_copy.json.j2", DEFAULT_UI_COPY)
UI_RUNTIME_CONFIG = _load_template_json("data/ui_runtime_config.json.j2", DEFAULT_UI_RUNTIME_CONFIG)


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
    return _api_error(MSG["ui_key_missing"], 401)


JOB_LABELS = {
    'hrv': 'sincronización HRV',
    'sessions': 'sincronización de sesiones',
    'seed_import': 'importación CSV seed',
    'delete_rr': 'borrado del último RR',
    'restore_backup': 'restauración desde Dropbox',
}


def _job_label(job_type: str | None) -> str:
    return JOB_LABELS.get(job_type or '', 'proceso')


def _api_error(error_message: str, status_code: int = 400, **payload):
    if payload:
        payload = {k: v for k, v in payload.items() if k not in {"success", "message", "error"}}
    body = {"success": False, "error": error_message, **payload}
    return jsonify(body), status_code


def _api_success(message: str, status_code: int = 200, **payload):
    if payload:
        payload = {k: v for k, v in payload.items() if k not in {"success", "message", "error"}}
    body = {"success": True, "message": message, **payload}
    return jsonify(body), status_code


def _in_progress_error(job_type: str | None, suffix: str = ""):
    base = f"{MSG['sync_in_progress_prefix']}{_job_label(job_type)}"
    return f"{base}.{suffix}" if suffix else base


def _oauth_error_context(variant: str, strong_message: str | None = None, error_detail: str | None = None) -> dict:
    error_copy = OAUTH_MSG["error"]
    if variant == "oauth_provider_error":
        return {
            "title": error_copy["provider_title"],
            "pill": error_copy["provider_pill"],
            "heading": error_copy["provider_heading"],
            "strong_message": strong_message,
            "detail_message": error_detail or error_copy["provider_detail_fallback"],
            "button": error_copy["default_button"],
            "button_href": "/",
        }
    if variant == "oauth_missing_code":
        return {
            "title": error_copy["missing_code_title"],
            "pill": error_copy["missing_code_pill"],
            "heading": error_copy["missing_code_heading"],
            "strong_message": None,
            "detail_message": error_copy["missing_code_message"],
            "button": error_copy["default_button"],
            "button_href": "/",
        }
    if variant == "oauth_state_error":
        return {
            "title": error_copy["state_title"],
            "pill": error_copy["state_pill"],
            "heading": error_copy["state_heading"],
            "strong_message": None,
            "detail_message": error_copy["state_message"],
            "button": error_copy["state_button"],
            "button_href": "/auth",
        }
    if variant == "oauth_persist_error":
        return {
            "title": error_copy["missing_code_title"],
            "pill": error_copy["missing_code_pill"],
            "heading": error_copy["persist_heading"],
            "strong_message": None,
            "detail_message": f"{error_copy['persist_message_prefix']}{error_detail}" if error_detail else error_copy["provider_detail_fallback"],
            "button": error_copy["default_button"],
            "button_href": "/",
        }
    return {
        "title": error_copy["missing_code_title"],
        "pill": error_copy["missing_code_pill"],
        "heading": error_copy["persist_heading"],
        "strong_message": None,
        "detail_message": error_detail or error_copy["provider_detail_fallback"],
        "button": error_copy["default_button"],
        "button_href": "/",
    }


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

    diagnostics = {
        "authorized": token_info.get("token_reason") == "ok",
        **token_info,
        **csv_info,
        **_ai_daily_brief_diagnostics(csv_info.get("final_last_fecha")),
        **weekly_coach_info,
        **dropbox_info,
        **seed_info,
        **rr_info,
    }
    diagnostics.update(_compose_hrv_summary_diagnostics(diagnostics))
    payload = _execution_snapshot()
    payload["diagnostics"] = diagnostics
    payload["view"] = ui_view.build_view(diagnostics)
    return payload


def _technical_summary_from_payload(payload: dict) -> str:
    return str(payload.get("last_output") or payload.get("output") or payload.get("last_error") or "").strip()


def _render_index_fallback(initial_payload: dict):
    view = initial_payload.get("view") or ui_view.build_view({})
    hrv = view.get("hrv_today", {}) or {}
    final_exists = bool(hrv.get("exists"))
    final_fecha = html.escape(str(hrv.get("date") or "sin datos"))
    technical_output = html.escape(_technical_summary_from_payload(initial_payload) or "Esperando ejecución...")
    dashboard_title = html.escape(UI_COPY.get("dashboard_title", "HRV Sync"))
    summary_title = html.escape(UI_COPY.get("hrv_summary_title_base", "Lectura HRV de hoy"))
    ai_brief_text = html.escape(str(hrv.get("ai_text") or ""))
    reason_text = html.escape(str(hrv.get("reason_text") or ""))
    fallback_text = html.escape(str(hrv.get("fallback_text") or ""))
    technical_title = html.escape(UI_COPY.get("technical_title", "Detalle técnico"))
    raw_text = html.escape(str(hrv.get("raw_text") or "-"))
    used_text = html.escape(str(hrv.get("used_text") or "-"))
    base_text = html.escape(str(hrv.get("base_text") or "-"))
    gate_text = html.escape(str(hrv.get("gate_text") or "-"))
    hidden_attr = "" if final_exists else " hidden"
    return f"""<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Polar HRV Sync v4</title>
</head>
<body>
    <main>
        <h1>{dashboard_title}</h1>
        <section id="hrvSummaryCard"{hidden_attr}>
            <h2>{summary_title} ({final_fecha})</h2>
            <div>
                <p>{raw_text}</p>
                <p>{used_text}</p>
                <p>{base_text}</p>
                <p>{gate_text}</p>
            </div>
            <p>{ai_brief_text}</p>
            <p>{reason_text}</p>
            <p>{fallback_text}</p>
        </section>
        <section>
            <h2>{technical_title}</h2>
            <pre>{technical_output}</pre>
        </section>
    </main>
</body>
</html>"""


def _render_oauth_success_fallback():
    success = OAUTH_MSG["success"]
    return f"""<!DOCTYPE html>
<html lang="es">
<head><meta charset="UTF-8"><title>{html.escape(success['title'])}</title></head>
<body>
    <main>
        <h1>{html.escape(success['heading'])}</h1>
        <p>{html.escape(success['message_1'])}</p>
        <p>{html.escape(success['message_2'])}</p>
        <a href="/">{html.escape(success['button'])}</a>
    </main>
</body>
</html>"""


def _render_oauth_error_fallback(context: dict):
    title = html.escape(str(context["title"]))
    heading = html.escape(str(context["heading"]))
    strong_message = html.escape(str(context.get("strong_message") or ""))
    detail_message = html.escape(str(context["detail_message"]))
    button_href = html.escape(str(context["button_href"]), quote=True)
    button = html.escape(str(context["button"]))
    return f"""<!DOCTYPE html>
<html lang="es">
<head><meta charset="UTF-8"><title>{title}</title></head>
<body>
    <main>
        <h1>{heading}</h1>
        <p>{strong_message}</p>
        <p>{detail_message}</p>
        <a href="{button_href}">{button}</a>
    </main>
</body>
</html>"""


# HTML Template (UI móvil-first)
@app.route('/')
def index():
    """Interfaz web principal"""
    initial_payload = _build_status_payload()
    initial_view = initial_payload.get("view") or ui_view.build_view({})
    try:
        return render_template(
            'index.html',
            ui_copy=UI_COPY,
            runtime_config={**UI_RUNTIME_CONFIG, "sync_timeout_sec": _sync_timeout_seconds()},
            show_seed_import=env_flag('HRV_SHOW_SEED_IMPORT', SEED_UPLOAD_DIR.exists()),
            show_restore_backup=env_flag('HRV_BACKUP_DROPBOX_ENABLED', False),
            view=initial_view,
            initial_technical_output=_technical_summary_from_payload(initial_payload),
        )
    except TemplateNotFound as exc:
        app.logger.warning("Index template fallback: %s", exc)
        return _render_index_fallback(initial_payload)


@app.route('/api/sync', methods=['POST'])
def sync():
    """Ejecutar sincronización Polar"""
    if not TOKEN_PATH_V4.exists():
        return _api_error(MSG["sync_missing_auth"])

    if not _try_begin_execution('hrv'):
        return _api_error(_in_progress_error(_execution_snapshot().get("job_type")), 409)

    thread = threading.Thread(target=run_sync, daemon=True)
    try:
        thread.start()
    except Exception as exc:
        _set_execution_result('hrv', False, '', str(exc), MSG["sync_start_error"])
        return _api_error(str(exc), 500, job_type='hrv')
    thread.join(timeout=1)

    state = _execution_snapshot()
    if state['success'] is not None and state.get('job_type') == 'hrv':
        body = {
            'success': state['success'],
            'message': MSG["sync_success"] if state['success'] else MSG["sync_error"],
            'output': state['last_output'],
            'error': state['last_error'],
            'job_type': 'hrv',
        }
        return jsonify(body)

    return _api_success(MSG["sync_started"], 202, output=MSG["sync_output_placeholder"], job_type='hrv')


def run_sync():
    """Ejecutar polar_hrv_automation.py --process."""
    _run_subprocess_job(
        [sys.executable, 'polar_hrv_automation.py', '--process'],
        'hrv',
        MSG["sync_success"],
        env_extra={
            'PYTHONUTF8': '1',
            'HRV_QUIET': '0',
        },
    )


@app.route('/api/sync-sessions', methods=['POST'])
def sync_sessions():
    """Ejecutar sincronización de sesiones desde Intervals."""
    if not _try_begin_execution('sessions'):
        return _api_error(_in_progress_error(_execution_snapshot().get("job_type")), 409)

    thread = threading.Thread(target=run_sessions_sync, daemon=True)
    try:
        thread.start()
    except Exception as exc:
        _set_execution_result('sessions', False, '', str(exc), MSG["sessions_start_error"])
        return _api_error(str(exc), 500, job_type='sessions')
    thread.join(timeout=1)

    state = _execution_snapshot()
    if state['success'] is not None and state.get('job_type') == 'sessions':
        body = {
            'success': state['success'],
            'message': state.get('message') or (MSG["sessions_success"] if state['success'] else MSG["sessions_error"]),
            'output': state['last_output'],
            'error': state['last_error'],
            'job_type': 'sessions',
        }
        return jsonify(body)

    return _api_success(MSG["sessions_started"], 202, output=MSG["sync_output_placeholder"], job_type='sessions')


def run_sessions_sync():
    """Ejecutar build_sessions.py --update."""
    _run_subprocess_job(
        [sys.executable, 'build_sessions.py', '--update'],
        'sessions',
        MSG["sessions_success"],
        env_extra={
            'HRV_QUIET': '0',
        },
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
        return _api_error(_in_progress_error(_execution_snapshot().get('job_type'), MSG['seed_import_in_progress_suffix']), 409)

    try:
        result = _import_seed_csvs()
        _set_execution_result(
            'seed_import',
            True,
            json.dumps(result, ensure_ascii=False, indent=2),
            '',
            MSG["seed_import_started"],
        )
        return _api_success(MSG["seed_import_started"], job_type='seed_import', **result)
    except Exception as exc:
        _set_execution_result('seed_import', False, '', str(exc), MSG["seed_import_error"])
        return _api_error(str(exc), job_type='seed_import')


@app.route('/api/restore-backup', methods=['POST'])
def restore_backup_endpoint():
    """Restaurar CSV canónicos desde el último backup en Dropbox."""
    if not _try_begin_execution('restore_backup'):
        return _api_error(_in_progress_error(_execution_snapshot().get('job_type'), MSG['restore_in_progress_suffix']), 409)

    try:
        from hrv_app.backup_dropbox import restore_backup
        result = restore_backup()
        _set_execution_result(
            'restore_backup',
            True,
            json.dumps(result, ensure_ascii=False, indent=2),
            '',
            MSG["restore_started"],
        )
        return _api_success(MSG["restore_started"], job_type='restore_backup', **result)
    except Exception as exc:
        _set_execution_result('restore_backup', False, '', str(exc), MSG["restore_error"])
        return _api_error(str(exc), job_type='restore_backup')


@app.route('/api/delete-latest-rr', methods=['POST'])
def delete_latest_rr():
    """Mover a backup el último RR CSV del directorio operativo."""
    if not _try_begin_execution('delete_rr'):
        return _api_error(_in_progress_error(_execution_snapshot().get('job_type'), MSG['delete_in_progress_suffix']), 409)

    try:
        result = _delete_latest_rr()
        _set_execution_result(
            'delete_rr',
            True,
            json.dumps(result, ensure_ascii=False, indent=2),
            '',
            MSG["delete_started"],
        )
        return _api_success(MSG["delete_started"], job_type='delete_rr', **result)
    except Exception as exc:
        _set_execution_result('delete_rr', False, '', str(exc), MSG["delete_error"])
        return _api_error(str(exc), job_type='delete_rr')


@app.route('/auth', strict_slashes=False)
def auth():
    """Iniciar flujo OAuth (web) con Polar"""
    raw_client_id2 = os.environ.get("POLAR_CLIENT_ID2")
    raw_client_id = os.environ.get("POLAR_CLIENT_ID")
    client_id = (raw_client_id2 or raw_client_id or "").strip()
    client_secret = (os.environ.get("POLAR_CLIENT_SECRET") or "").strip()
    if not client_id or not client_secret:
        return _api_error(MSG["auth_missing_credentials"], 500)

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
        context = _oauth_error_context('oauth_provider_error', error, error_description or 'Error desconocido')
        try:
            return render_template('oauth_error.html', **context), 400
        except TemplateNotFound as exc:
            app.logger.warning("OAuth error template fallback: %s", exc)
            return _render_oauth_error_fallback(context), 400

    if not code:
        context = _oauth_error_context('oauth_missing_code')
        try:
            return render_template('oauth_error.html', **context), 400
        except TemplateNotFound as exc:
            app.logger.warning("OAuth error template fallback: %s", exc)
            return _render_oauth_error_fallback(context), 400

    state_valid = _consume_oauth_state((request.args.get('state') or '').strip())
    if not state_valid:
        context = _oauth_error_context('oauth_state_error')
        try:
            return render_template('oauth_error.html', **context), 400
        except TemplateNotFound as exc:
            app.logger.warning("OAuth error template fallback: %s", exc)
            return _render_oauth_error_fallback(context), 400

    try:
        client_id = (os.environ.get("POLAR_CLIENT_ID2") or os.environ.get("POLAR_CLIENT_ID") or "").strip()
        client_secret = (os.environ.get("POLAR_CLIENT_SECRET") or "").strip()
        if not client_id or not client_secret:
            raise RuntimeError("Credenciales POLAR_CLIENT_ID / POLAR_CLIENT_SECRET no configuradas")

        redirect_uri = _redirect_uri()

        token_json = exchange_code_for_token_v4(code, client_id, client_secret, redirect_uri)
        persist_authorized_bundle(TOKEN_PATH_V4, token_json, scopes=POLAR_V4_SCOPES)

        try:
            return render_template('oauth_success.html', **OAUTH_MSG["success"])
        except TemplateNotFound as exc:
            app.logger.warning("OAuth success template fallback: %s", exc)
            return _render_oauth_success_fallback()

    except Exception as e:
        context = _oauth_error_context('oauth_persist_error', error_detail=str(e))
        try:
            return render_template('oauth_error.html', **context), 500
        except TemplateNotFound as exc:
            app.logger.warning("OAuth error template fallback: %s", exc)
            return _render_oauth_error_fallback(context), 500

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


def _print_console_banner(port: int) -> None:
    _safe_console_print("\n" + "=" * 60)
    _safe_console_print(CONSOLE_MSG["title"])
    _safe_console_print("=" * 20)
    _safe_console_print(f"\n🌐 {CONSOLE_MSG['server_started'].format(port=port)}")
    _safe_console_print(f"\n📱 {CONSOLE_MSG['access_from']}")
    _safe_console_print(f"   - {CONSOLE_MSG['local'].format(port=port)}")
    _safe_console_print(f"   - {CONSOLE_MSG['railway']}")
    _safe_console_print(f"\n💡 {CONSOLE_MSG['tip']}")
    _safe_console_print("=" * 20 + "\n")
 

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))

    _print_console_banner(port)
    app.run(host='0.0.0.0', port=port, debug=False)








