#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Web UI para Polar HRV Automation
Accesible desde cualquier dispositivo (móvil, tablet, PC)
"""

from flask import Flask, render_template_string, jsonify, request, redirect
from flask_cors import CORS
from werkzeug.middleware.proxy_fix import ProxyFix
import subprocess
import sys
import os
import csv
import shutil
from pathlib import Path
from datetime import datetime
import threading
import json
from urllib.parse import urlencode
import secrets
import time
import requests
import base64

app = Flask(__name__)
CORS(app)
# Respeta headers X-Forwarded-* cuando corre detrás de Railway/Proxy
app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)
app.config["PREFERRED_URL_SCHEME"] = "https"

# =========================
# Polar OAuth (web flow)
# =========================
SCOPE = "accesslink.read_all"
TOKEN_PATH = Path(os.environ.get("POLAR_TOKEN_PATH", ".polar_tokens.json"))
DATA_DIR = Path((os.environ.get("HRV_DATA_DIR") or "data").strip() or "data")
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



def _public_url() -> str:
    """URL pública base (https://<dominio>)"""
    # Prioridad: PUBLIC_URL explícita → Railway domain → request host
    pu = (
        os.environ.get("PUBLIC_URL")
        or os.environ.get("RAILWAY_PUBLIC_URL")
        or os.environ.get("RAILWAY_PUBLIC_DOMAIN")
        or ""
    ).strip()
    if pu:
        if not pu.startswith("http"):
            pu = f"https://{pu}"
        return pu.rstrip("/")
    # Fallback razonable: usar Host del request (puede ser http sin ProxyFix)
    host = (request.host_url or "").rstrip("/")
    if host.startswith("http://"):
        # Railway sirve https fuera; forzamos https
        host = host.replace("http://", "https://", 1)
    return host


def _redirect_uri() -> str:
    return f"{_public_url()}/auth/callback"


def _basic_auth_header(client_id: str, client_secret: str) -> str:
    token = base64.b64encode(f"{client_id}:{client_secret}".encode("utf-8")).decode("ascii")
    return f"Basic {token}"

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

JOB_LABELS = {
    'hrv': 'sincronización HRV',
    'sessions': 'sincronización de sesiones',
    'seed_import': 'importación CSV seed',
}


def _job_label(job_type: str | None) -> str:
    return JOB_LABELS.get(job_type or '', 'proceso')


def _set_execution_start(job_type: str) -> None:
    execution_state['running'] = True
    execution_state['success'] = None
    execution_state['last_output'] = ''
    execution_state['last_error'] = ''
    execution_state['job_type'] = job_type
    execution_state['message'] = None


def _set_execution_result(job_type: str, success: bool, output: str = '', error: str = '', message: str | None = None) -> None:
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


def _env_flag(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    value = raw.strip().lower()
    if value == "":
        return default
    return value in {"1", "true", "yes", "on"}


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


def _token_diagnostics() -> dict:
    info = {
        "token_path": str(TOKEN_PATH),
        "token_exists": TOKEN_PATH.exists(),
        "token_reason": "missing",
        "token_expired": None,
    }

    if not info["token_exists"]:
        return info

    try:
        token_json = json.loads(TOKEN_PATH.read_text(encoding="utf-8"))
    except Exception:
        info["token_reason"] = "invalid_json"
        return info

    access_token = token_json.get("access_token")
    if not access_token:
        info["token_reason"] = "missing_access_token"
        return info

    obtained_at = float(token_json.get("obtained_at", 0) or 0)
    expires_in = float(token_json.get("expires_in", 0) or 0)
    if expires_in > 0 and (time.time() - obtained_at) > expires_in:
        info["token_reason"] = "expired"
        info["token_expired"] = True
        return info

    info["token_reason"] = "ok"
    info["token_expired"] = False if expires_in > 0 else None
    return info


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


def _csv_runtime_diagnostics() -> dict:
    data_dir = Path((os.environ.get("HRV_DATA_DIR") or "data").strip() or "data")
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
        "final_last_n_base60": last_final_row.get("n_base60") if last_final_row else None,
        "final_last_gate_razon_base60": last_final_row.get("gate_razon_base60") if last_final_row else None,
    }


def _drive_runtime_diagnostics() -> dict:
    drive_script = Path((os.environ.get("HRV_DRIVE_RR_SCRIPT") or "egc_to_rr.py").strip() or "egc_to_rr.py")
    drive_runtime = (os.environ.get("HRV_DRIVE_RUNTIME") or "auto").strip() or "auto"
    drive_folder_id_set = bool((os.environ.get("HRV_DRIVE_FOLDER_ID") or "").strip())
    rr_cloud_source = (os.environ.get("HRV_RR_CLOUD_SOURCE") or "drive").strip().lower() or "drive"
    if rr_cloud_source not in {"drive", "dropbox"}:
        rr_cloud_source = "drive"
    dropbox_folder_path = (
        os.environ.get("HRV_DROPBOX_FOLDER_PATH")
        or os.environ.get("DROPBOX_FOLDER_PATH")
        or ""
    ).strip()

    google_application_credentials = (os.environ.get("GOOGLE_APPLICATION_CREDENTIALS") or "").strip()
    google_application_credentials_exists = False
    if google_application_credentials:
        try:
            google_application_credentials_exists = Path(google_application_credentials).exists()
        except Exception:
            google_application_credentials_exists = False

    service_account_file = Path("service_account.json")
    tokens_file = Path("tokens.json")

    return {
        "drive_rr_enabled": _env_flag("HRV_DRIVE_RR_ENABLED", True),
        "drive_rr_script": str(drive_script),
        "drive_rr_script_exists": drive_script.exists(),
        "drive_rr_runtime": drive_runtime,
        "rr_cloud_source": rr_cloud_source,
        "drive_rr_recursive": _env_flag("HRV_DRIVE_RECURSIVE", True),
        "drive_rr_no_aux": _env_flag("HRV_DRIVE_NO_AUX", True),
        "drive_rr_folder_id_set": drive_folder_id_set,
        "drive_rr_pair_limit": (os.environ.get("HRV_DRIVE_PAIR_LIMIT") or "").strip() or None,
        "dropbox_folder_path_set": bool(dropbox_folder_path),
        "dropbox_recursive": _env_flag("HRV_DROPBOX_RECURSIVE", True),
        "dropbox_access_token_set": bool((os.environ.get("DROPBOX_ACCESS_TOKEN") or "").strip()),
        "dropbox_refresh_token_set": bool((os.environ.get("DROPBOX_REFRESH_TOKEN") or "").strip()),
        "dropbox_app_key_set": bool((os.environ.get("DROPBOX_APP_KEY") or "").strip()),
        "dropbox_app_secret_set": bool((os.environ.get("DROPBOX_APP_SECRET") or "").strip()),
        "google_oauth_token_json_set": bool((os.environ.get("GOOGLE_OAUTH_TOKEN_JSON") or "").strip()),
        "google_service_account_json_set": bool((os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON") or "").strip()),
        "google_application_credentials_set": bool(google_application_credentials),
        "google_application_credentials_exists": google_application_credentials_exists,
        "service_account_file_exists": service_account_file.exists(),
        "tokens_file_exists": tokens_file.exists(),
        "credentials_file_exists": Path("credentials.json").exists(),
    }


def _build_status_payload() -> dict:
    token_info = _token_diagnostics()
    csv_info = _csv_runtime_diagnostics()
    drive_info = _drive_runtime_diagnostics()
    seed_info = _seed_upload_diagnostics()

    payload = dict(execution_state)
    payload["diagnostics"] = {
        "authorized": token_info.get("token_reason") == "ok",
        **token_info,
        **csv_info,
        **drive_info,
        **seed_info,
    }
    return payload


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
        h1 { font-size: 30px; line-height: 1; letter-spacing: -0.04em; margin-bottom: 10px; }
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
        .is-hidden { display: none; }
        .status { display: none; margin-top: 12px; padding: 8px 16px; border-radius: 0; font-size: 14px; line-height: 1.45; }
        .status.show { display: block; }
        .status.info { background: var(--info-bg); color: var(--info-text); }
        .status.success { background: var(--ok-bg); color: var(--ok-text); }
        .status.error { background: var(--error-bg); color: var(--error-text); }
        .section-title { font-size: 16px; font-weight: 800; letter-spacing: -0.03em; color: var(--brand-strong); margin-bottom: 12px; }
        .raw-output {
            padding: 14px; border-radius: 4px; background: #16353a; color: #eef6f5; font-family: Consolas, "Courier New", monospace;
            font-size: 12px; line-height: 1.5; min-height: 320px; max-height: 60vh; overflow: auto; white-space: pre-wrap; word-wrap: break-word;
            letter-spacing: -.125px;
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
            <h1>⚡ HRV Sync v4</h1>
            <p class="subtitle">Sincronización automática de datos HRV</p>
            <div class="button-stack">
                <button id="syncBtn" class="sync-button" onclick="syncPolar()"><span id="syncBtnText">Sincronizar HRV</span></button>
                <button id="sessionsBtn" class="sessions-button" onclick="syncSessions()"><span id="sessionsBtnText">Sincronizar sesiones</span></button>
                <button id="importBtn" class="ghost-button{% if not show_seed_import %} is-hidden{% endif %}" onclick="importSeedCsvs()" {% if not show_seed_import %}hidden{% endif %}><span id="importBtnText">Importar CSV seed</span></button>
            </div>
            <div id="status" class="status"></div>
        </section>
        <section class="card">
            <div class="section-title">Detalle técnico</div>
            <pre id="rawOutput" class="raw-output">Esperando ejecución...</pre>
        </section>
    </div>
    <script>
        function showBanner(kind, message) {
            const status = document.getElementById('status');
            status.className = `status ${kind} show`;
            status.textContent = message;
        }
        function renderTechnicalOutput(rawText) {
            const rawOutput = document.getElementById('rawOutput');
            rawOutput.textContent = rawText || 'Esperando ejecución...';
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
            const rawText = data.last_output || data.output || data.last_error || '';
            setButtonState('hrv', 'idle');
            setButtonState('sessions', 'idle');
            if (data.running && data.job_type === 'hrv') setButtonState('hrv', 'running');
            else if (data.running && data.job_type === 'sessions') setButtonState('sessions', 'running');
            syncBtn.disabled = Boolean(data.running);
            sessionsBtn.disabled = Boolean(data.running);
            if (importBtn) importBtn.disabled = Boolean(data.running);
            renderTechnicalOutput(rawText);
        }
        async function refreshDashboard() {
            try {
                const response = await fetch('/api/status');
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
                const response = await fetch(url, { method: 'POST' });
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
                const response = await fetch('/api/import-seed', { method: 'POST' });
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
        async function pollSyncStatus() {
            let attempts = 0;
            const syncTimeoutSec = Number('{{ sync_timeout_sec }}') || 1200;
            const pollIntervalSec = 2;
            const maxAttempts = Math.ceil(syncTimeoutSec / pollIntervalSec);
            while (attempts < maxAttempts) {
                await new Promise(resolve => setTimeout(resolve, 2000));
                try {
                    const response = await fetch('/api/status');
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
    return render_template_string(
        HTML_TEMPLATE,
        sync_timeout_sec=_sync_timeout_seconds(),
        show_seed_import=_env_flag('HRV_SHOW_SEED_IMPORT', False),
    )


@app.route('/api/sync', methods=['POST'])
def sync():
    """Ejecutar sincronización Polar"""
    global execution_state

    if not TOKEN_PATH.exists():
        return jsonify({
            'success': False,
            'error': 'Falta autorización. Abre /auth para iniciar sesión en Polar y autorizar la app.'
        }), 400

    if execution_state['running']:
        return jsonify({
            'success': False,
            'error': f'Ya hay un proceso en curso: {_job_label(execution_state.get("job_type"))}'
        }), 409

    thread = threading.Thread(target=run_sync)
    thread.start()
    thread.join(timeout=1)

    if execution_state['success'] is not None and execution_state.get('job_type') == 'hrv':
        return jsonify({
            'success': execution_state['success'],
            'message': 'Sincronización completada' if execution_state['success'] else 'Error en sincronización',
            'output': execution_state['last_output'],
            'error': execution_state['last_error'],
            'job_type': 'hrv',
        })

    return jsonify({
        'success': True,
        'message': 'Sincronización iniciada',
        'output': 'Procesando...',
        'job_type': 'hrv',
    })


def run_sync():
    """Ejecutar polar_hrv_automation.py"""
    global execution_state

    execution_state['running'] = True
    execution_state['success'] = None
    execution_state['last_output'] = ''
    execution_state['last_error'] = ''
    execution_state['job_type'] = 'hrv'
    execution_state['message'] = None

    try:
        script_path = Path('polar_hrv_automation.py')
        timeout_sec = _sync_timeout_seconds()

        if not script_path.exists():
            raise FileNotFoundError('polar_hrv_automation.py no encontrado')

        result = subprocess.run(
            [sys.executable, str(script_path), '--process'],
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='replace',
            timeout=timeout_sec,
            env={
                **os.environ,
                'PYTHONIOENCODING': 'utf-8',
                'PYTHONUTF8': '1',
                'HRV_DISABLE_BACKUP': '1',
                'HRV_QUIET': '1',
            }
        )

        execution_state['last_output'] = result.stdout or ''
        execution_state['last_error'] = result.stderr or ''
        execution_state['success'] = (result.returncode == 0)
        execution_state['message'] = 'Sincronización completada' if execution_state['success'] else 'Error en sincronización'
    except subprocess.TimeoutExpired as e:
        timeout_sec = _sync_timeout_seconds()
        stdout = e.stdout if isinstance(e.stdout, str) else (e.stdout.decode('utf-8', errors='replace') if e.stdout else '')
        stderr = e.stderr if isinstance(e.stderr, str) else (e.stderr.decode('utf-8', errors='replace') if e.stderr else '')
        execution_state['last_output'] = stdout or ''
        execution_state['last_error'] = (
            f"Timeout ejecutando sync (>{timeout_sec}s). Ajusta HRV_SYNC_TIMEOUT_SEC si hace falta.\n{stderr or ''}"
        ).strip()
        execution_state['success'] = False
        execution_state['message'] = 'Error en sincronización'
    except Exception as e:
        execution_state['last_error'] = str(e)
        execution_state['success'] = False
        execution_state['message'] = 'Error en sincronización'
    finally:
        execution_state['last_run'] = datetime.now().isoformat()
        execution_state['running'] = False


@app.route('/api/sync-sessions', methods=['POST'])
def sync_sessions():
    """Ejecutar sincronización de sesiones desde Intervals."""
    global execution_state

    if execution_state['running']:
        return jsonify({
            'success': False,
            'error': f'Ya hay un proceso en curso: {_job_label(execution_state.get("job_type"))}'
        }), 409

    thread = threading.Thread(target=run_sessions_sync, daemon=True)
    thread.start()
    thread.join(timeout=1)

    if execution_state['success'] is not None and execution_state.get('job_type') == 'sessions':
        return jsonify({
            'success': execution_state['success'],
            'message': execution_state.get('message') or ('Sincronización de sesiones completada' if execution_state['success'] else 'Error en sincronización de sesiones'),
            'output': execution_state['last_output'],
            'error': execution_state['last_error'],
            'job_type': 'sessions',
        })

    return jsonify({
        'success': True,
        'message': 'Sincronización de sesiones iniciada',
        'output': 'Procesando...',
        'job_type': 'sessions',
    })


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
    return jsonify(_build_status_payload())


@app.route('/api/import-seed', methods=['POST'])
def import_seed():
    """Importar CSV canónicos desde seed_upload hacia HRV_DATA_DIR."""
    global execution_state

    if execution_state['running']:
        return jsonify({
            'success': False,
            'error': f'Hay un proceso en curso: {_job_label(execution_state.get("job_type"))}. Espera a que termine antes de importar.'
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
    state = secrets.token_urlsafe(24)

    # Polar AccessLink espera scope (en muchos casos es obligatorio)
    params = {
        'response_type': 'code',
        'client_id': client_id,
        'redirect_uri': redirect_uri,
        'scope': SCOPE,
        'state': state,
    }

    authorization_url = f"https://flow.polar.com/oauth2/authorization?{urlencode(params)}"

#    print("🔐 OAuth /auth")
#    print(f"   client_id_source: {client_id_source}")
#    print(f"   client_id_len: {len(client_id)}")
#    print(f"   client_id_tail: {client_id[-4:] if len(client_id) >= 4 else client_id}")
#    print(f"   redirect_uri: {redirect_uri}")

    return redirect(authorization_url)


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
            <p><strong>{error}</strong></p>
            <p>{error_description or 'Error desconocido'}</p>
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

    try:
        client_id = (os.environ.get("POLAR_CLIENT_ID2") or os.environ.get("POLAR_CLIENT_ID") or "").strip()
        client_secret = (os.environ.get("POLAR_CLIENT_SECRET") or "").strip()
        if not client_id or not client_secret:
            raise RuntimeError("Credenciales POLAR_CLIENT_ID / POLAR_CLIENT_SECRET no configuradas")

        redirect_uri = _redirect_uri()

        headers = {
            'Authorization': _basic_auth_header(client_id, client_secret),
            'Content-Type': 'application/x-www-form-urlencoded',
            'Accept': 'application/json;charset=UTF-8',
        }
        data = {
            'grant_type': 'authorization_code',
            'code': code,
            'redirect_uri': redirect_uri,
        }
        token_url = "https://polarremote.com/v2/oauth2/token"
        r = requests.post(token_url, headers=headers, data=data, timeout=30)
        if r.status_code >= 400:
            raise RuntimeError(f"Token exchange falló: {r.status_code} {r.reason} | {r.text}")

        token_json = r.json()
        token_json['obtained_at'] = time.time()

        access_token = token_json.get('access_token')
        x_user_id = token_json.get('x_user_id')
        if access_token:
            member_id = f"local_{x_user_id or 'user'}"
            xml = f"<register><member-id>{member_id}</member-id></register>"
            reg_url = "https://www.polaraccesslink.com/v3/users"
            reg = requests.post(
                reg_url,
                headers={
                    'Authorization': f'Bearer {access_token}',
                    'Accept': 'application/json',
                    'Content-Type': 'application/xml',
                },
                data=xml.encode('utf-8'),
                timeout=30,
            )
            if reg.status_code not in (200, 201, 409):
                raise RuntimeError(f"Registro usuario falló: {reg.status_code} {reg.reason} | {reg.text}")
        TOKEN_PATH.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = TOKEN_PATH.with_suffix(TOKEN_PATH.suffix + '.tmp')
        tmp_path.write_text(json.dumps(token_json, indent=2), encoding='utf-8')
        tmp_path.replace(TOKEN_PATH)
        try:
            os.chmod(TOKEN_PATH, 0o600)
        except Exception:
            pass

        return """
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

    except Exception as e:
        return f"""
        <html>
        <body style="font-family: Arial; text-align: center; padding: 50px;">
            <h1>⚠️ Error</h1>
            <p>No se pudo guardar el código de autorización: {str(e)}</p>
            <br>
            <a href="/" style="color: #667eea; text-decoration: none;">← Volver a la app</a>
        </body>
        </html>
        """, 500

@app.route('/health', methods=['GET'])
def health():
    """Health check para Railway/Render"""
    return jsonify({
        'status': 'healthy',
        'timestamp': datetime.now().isoformat()
    })


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    
    print("\n" + "="*60)
    print("  POLAR HRV - WEB UI")
    print("="*20)
    print(f"\n🌐 Servidor iniciado en puerto {port}")
    print(f"\n📱 Accede desde:")
    print(f"   - Local: http://localhost:{port}")
    print(f"   - Railway: https://tu-app.up.railway.app")
    print("\n💡 Abre desde cualquier dispositivo (móvil, tablet, PC)")
    print("="*20 + "\n")
    
    app.run(host='0.0.0.0', port=port, debug=False)








