#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
POLAR HRV AUTOMATION - Railway/Render Compatible
=================================================
Funciona con .env (local) O variables de entorno (Railway/Render)

Uso:
    python polar_hrv_automation.py --auth         # Primera vez
    python polar_hrv_automation.py                # Después (últimos 7 días)
    python polar_hrv_automation.py --days 30      # Últimos 30 días
    python polar_hrv_automation.py --all          # Todas las sesiones
    python polar_hrv_automation.py --process      # + ejecutar endurance_hrv.py + endurance_v4lite.py
"""

import os
import sys
import re
import threading
import time
import json
import argparse
import subprocess
import webbrowser
import csv
from pathlib import Path
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse, parse_qs, urlencode
from datetime import datetime, timedelta

from typing import Optional, Dict, Any, List, Tuple
import requests
import base64
from requests.auth import _basic_auth_str

# pandas es opcional, solo para --auto
try:
    import pandas as pd
    PANDAS_AVAILABLE = True
except ImportError:
    PANDAS_AVAILABLE = False

# =========================
# DETECCIÓN DE ENTORNO
# =========================
IS_RAILWAY = os.environ.get('RAILWAY_ENVIRONMENT') is not None
IS_RENDER = os.environ.get('RENDER') is not None
IS_HEROKU = os.environ.get('DYNO') is not None
IS_PRODUCTION = IS_RAILWAY or IS_RENDER or IS_HEROKU

# Cargar .env solo en local
if not IS_PRODUCTION:
    try:
        from dotenv import load_dotenv
        load_dotenv()
        # print("📝 Modo LOCAL: cargando credenciales desde .env")
    except ImportError:
        print("⚠️  python-dotenv no instalado, usando variables de entorno del sistema")
else:
    env_name = 'Railway' if IS_RAILWAY else 'Render' if IS_RENDER else 'Heroku'
    # print(f"🌐 Modo PRODUCCIÓN: {env_name}")
    # print("📝 Cargando credenciales desde variables de entorno")

# =========================
# CONFIG
# =========================
def _env_flag(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    value = raw.strip().lower()
    if value == "":
        return default
    return value in {"1", "true", "yes", "on"}


QUIET = _env_flag("HRV_QUIET", False)


def _qprint(*args, **kwargs):
    if not QUIET:
        print(*args, **kwargs)

CLIENT_ID = (
    os.environ.get("POLAR_CLIENT_ID2")
    or os.environ.get("POLAR_CLIENT_ID")
    or os.getenv("POLAR_CLIENT_ID")
)
CLIENT_SECRET = os.environ.get("POLAR_CLIENT_SECRET") or os.getenv("POLAR_CLIENT_SECRET")

# REDIRECT_URI adaptativo (local vs producción)
if IS_PRODUCTION:
    # En producción, construir URL pública
    PUBLIC_URL = os.environ.get('PUBLIC_URL') or os.environ.get('RAILWAY_PUBLIC_DOMAIN')
    if PUBLIC_URL:
        if not PUBLIC_URL.startswith('http'):
            PUBLIC_URL = f"https://{PUBLIC_URL}"
        REDIRECT_URI = f"{PUBLIC_URL}/auth/callback"
    else:
        # Fallback: intentar construir desde variables Railway
        if IS_RAILWAY:
            service_name = os.environ.get('RAILWAY_SERVICE_NAME', 'app')
            project_name = os.environ.get('RAILWAY_PROJECT_NAME', 'polar-hrv')
            REDIRECT_URI = f"https://{service_name}.up.railway.app/auth/callback"
        else:
            REDIRECT_URI = "http://localhost:5050/oauth2/callback"
            print("⚠️  PUBLIC_URL no configurado, usando localhost")
else:
    # En local, usar localhost
    REDIRECT_URI = "http://localhost:5050/oauth2/callback"

#print(f"🔗 OAuth Redirect URI: {REDIRECT_URI}")
#if CLIENT_ID:
#   print(f"🔑 client_id_len: {len(CLIENT_ID)} | client_id_tail: {CLIENT_ID[-4:]}")

SCOPE = "accesslink.read_all"

API_BASE = "https://www.polaraccesslink.com/v3"
AUTH_URL = "https://flow.polar.com/oauth2/authorization"
TOKEN_URL = "https://polarremote.com/v2/oauth2/token"

# Configuración nombres archivo
POLAR_USER_NAME = os.environ.get("POLAR_USER_NAME") or os.getenv("POLAR_USER_NAME", "Polar_User")

# Permite persistir tokens en un volumen (Railway) con POLAR_TOKEN_PATH=/data/polar_tokens.json
TOKEN_FILE = Path(os.environ.get("POLAR_TOKEN_PATH", ".polar_tokens.json"))

_data_dir = (os.environ.get("HRV_DATA_DIR") or "data").strip() or "data"
_rr_dir = (os.environ.get("RR_DOWNLOAD_DIR") or "").strip()
if _rr_dir:
    OUTDIR = Path(_rr_dir)
else:
    OUTDIR = Path(_data_dir) / "rr_downloads"

DATA_DIR = Path(_data_dir)
CORE_PATH = DATA_DIR / "ENDURANCE_HRV_master_CORE.csv"
BETA_AUDIT_PATH = DATA_DIR / "ENDURANCE_HRV_master_BETA_AUDIT.csv"
FINAL_PATH = DATA_DIR / "ENDURANCE_HRV_master_FINAL.csv"
DASHBOARD_PATH = DATA_DIR / "ENDURANCE_HRV_master_DASHBOARD.csv"
SLEEP_PATH = DATA_DIR / "ENDURANCE_HRV_sleep.csv"
LEGACY_SLEEP_PATH = DATA_DIR / "ENDURANCE_HRV_context.csv"

INTERVALS_SOURCE_PATH = BETA_AUDIT_PATH

SLEEP_COLUMNS = [
    "Fecha",
    # Polar sleep
    "polar_sleep_duration_min", "polar_sleep_span_min",
    "polar_deep_pct", "polar_rem_pct",
    "polar_efficiency_pct", "polar_continuity", "polar_continuity_index",
    "polar_interruptions_long", "polar_interruptions_total", "polar_sleep_score",
    # Polar nightly recharge
    "polar_night_rmssd", "polar_night_rri", "polar_night_resp",
    # Derived percentiles (recalculated on each upsert)
    "sleep_dur_p10", "sleep_dur_p90", "sleep_int_p90",
]

# Filtros
SPORTS_FILTER = ["BODY_AND_MIND"]  # Comparación EXACTA
MAX_DURATION_MINUTES = 10
MAX_EXERCISES = 50

# Rangos fisiológicos válidos para RR intervals (ms)
# Basado en rango de FC humano: 30-200 bpm
RR_MIN_MS = 300.0   # ~200 bpm (máximo fisiológico)
RR_MAX_MS = 2000.0  # ~30 bpm (mínimo fisiológico)

# Nombres de campos API Polar (variantes inconsistentes)
FIELD_START_TIME = ("start-time", "start_time", "startTime")
FIELD_SPORT = ("detailed-sport-info", "detailed_sport_info", "sport")
FIELD_SAMPLE_TYPE = ("sample-type", "sample_type")

# Nombres de columnas del BETA_AUDIT (para Intervals)
MASTER_CSV_COLS = {
    'fecha': 'Fecha',
    'hr': 'HR_stable',
    'rmssd': 'RMSSD_stable',
    'crmssd': 'cRMSSD',
    'color_agudo': 'Color_Agudo_Diario',
    'color_tendencia': 'Color_Tendencia',
    'color_tiebreak': 'Color_Tiebreak',
    'calidad': 'Calidad',
    'estabilidad': 'HRV_Stability',
    'flags': 'Flags',
}

# Mapeo de colores de estado a emojis
COLOR_EMOJI = {
    'Verde': '🟢',
    'Amarillo': '🟡',
    'Ámbar': '🟡',  # Alias para Amarillo
    'Rojo': '🔴',
    'N/A': '⚪',
}

GATE_EMOJI = {
    'VERDE': '🟢',
    'ÁMBAR': '🟡',
    'AMBAR': '🟡',
    'ROJO': '🔴',
    'NO': '⚪',
}

# Límites de visualización y procesamiento
DEBUG_PREVIEW_LIMIT = 10      # Sesiones a mostrar en modo debug
MAX_AUTO_DAYS = 30            # Días máximo en modo --auto
DATE_STRING_LENGTH = 10       # Longitud de "YYYY-MM-DD"
UNKNOWN_SESSION_ID = "unknown"  # ID para sesiones sin fecha

DEBUG_JSON = False  # True = guarda JSON debug de sesiones sin RR

# Integración Drive RR (ECG/ACC JSONL -> RR) con fallback a Polar.
DRIVE_RR_ENABLED = _env_flag("HRV_DRIVE_RR_ENABLED", True)
DRIVE_RR_SCRIPT = (os.environ.get("HRV_DRIVE_RR_SCRIPT") or "egc_to_rr.py").strip() or "egc_to_rr.py"
DRIVE_RR_RUNTIME = (os.environ.get("HRV_DRIVE_RUNTIME") or "auto").strip() or "auto"
DRIVE_RR_RECURSIVE = _env_flag("HRV_DRIVE_RECURSIVE", True)
DRIVE_RR_NO_AUX = _env_flag("HRV_DRIVE_NO_AUX", True)
DRIVE_RR_FOLDER_ID = (os.environ.get("HRV_DRIVE_FOLDER_ID") or "").strip()
DRIVE_RR_PAIR_LIMIT = (os.environ.get("HRV_DRIVE_PAIR_LIMIT") or "").strip()
RR_CLOUD_SOURCE = (os.environ.get("HRV_RR_CLOUD_SOURCE") or "drive").strip().lower()
if RR_CLOUD_SOURCE not in {"drive", "dropbox"}:
    RR_CLOUD_SOURCE = "drive"
DROPBOX_FOLDER_PATH = (
    os.environ.get("HRV_DROPBOX_FOLDER_PATH")
    or os.environ.get("DROPBOX_FOLDER_PATH")
    or ""
).strip()
DROPBOX_RECURSIVE = _env_flag("HRV_DROPBOX_RECURSIVE", True)

# =========================
# Intervals.icu wellness sync
# =========================
INTERVALS_BASE_URL = (os.environ.get("INTERVALS_BASE_URL") or "https://intervals.icu").strip()
INTERVALS_FIELD_MAP = {
    "CRMSSD": "cRMSSD",
    "HRPolar": "HR_stable",
    "HRVScore": "RMSSD_stable",
    "ColorDiario": "Color_Agudo_Diario",
    "ColorTiebreak": "Color_Tiebreak",
    "ColorTendencia": "Color_Tendencia",
}


def _intervals_api_root() -> str:
    base = (INTERVALS_BASE_URL or "https://intervals.icu").strip().rstrip("/")
    if not base:
        base = "https://intervals.icu"
    base = re.sub(r"/api/v1/?$", "", base, flags=re.IGNORECASE)
    return f"{base}/api/v1"

# Verificar credenciales al inicio
if not CLIENT_ID or not CLIENT_SECRET:
    _print_header("❌ ERROR: Credenciales Polar no configuradas", trailing_blank=True)
    
    if IS_PRODUCTION:
        print("En Railway/Render, configura variables de entorno:")
        print("  1. Ir a dashboard del servicio")
        print("  2. Variables → Add Variable")
        print("  3. Agregar:")
        print("     • POLAR_CLIENT_ID = tu_client_id")
        print("     • POLAR_CLIENT_SECRET = tu_client_secret")
        print("     • POLAR_USER_NAME = Tu_Nombre")
        print("     • PUBLIC_URL = https://tu-app.up.railway.app (opcional)")
    else:
        print("En local, crea archivo .env:")
        print("  1. cp .env.example .env")
        print("  2. Editar .env con tus credenciales")
        print("  3. Obtener credenciales en: https://admin.polaraccesslink.com/")
    
    print("\n")
    sys.exit(1)


def _iso_to_dt(s: str):
    """Convierte ISO string a datetime en hora LOCAL"""
    if not s:
        return None
    try:
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        dt_utc = datetime.fromisoformat(s)

        # Convertir a hora local del sistema
        utc_timestamp = dt_utc.timestamp()
        local_dt = datetime.fromtimestamp(utc_timestamp)

        return local_dt
    except (ValueError, TypeError, OverflowError, OSError):
        return None


def _parse_yyyy_mm_dd(s: str):
    if not s:
        return None
    try:
        return datetime.strptime(s, "%Y-%m-%d").date()
    except ValueError:
        return None


def _extract_date_from_rr_filename(file_name: str):
    """Extrae fecha YYYY-MM-DD desde nombre de archivo RR."""
    m = re.search(r"(\d{4}-\d{2}-\d{2})", file_name)
    if not m:
        return None
    return _parse_yyyy_mm_dd(m.group(1))


def _scan_rr_files_by_date(rr_dir: Path, source_tag: Optional[str] = None) -> Dict:
    """
    Devuelve {date: best_rr_path} para archivos *_RR.csv en rr_dir.
    Si source_tag existe, filtra por nombre que contenga ese tag (case-insensitive).
    """
    out: Dict = {}
    if not rr_dir.exists():
        return out

    tag = source_tag.lower() if source_tag else ""
    candidates = list(rr_dir.glob("*_RR.[Cc][Ss][Vv]"))
    for path in candidates:
        name_lower = path.name.lower()
        if tag and tag not in name_lower:
            continue

        day = _extract_date_from_rr_filename(path.name)
        if day is None:
            continue

        prev = out.get(day)
        if prev is None:
            out[day] = path
            continue

        prev_name = prev.name.lower()
        cur_is_jsonl = "from_jsonl" in name_lower
        prev_is_jsonl = "from_jsonl" in prev_name
        if cur_is_jsonl and not prev_is_jsonl:
            out[day] = path
            continue

        try:
            cur_mtime = path.stat().st_mtime
        except OSError:
            cur_mtime = 0
        try:
            prev_mtime = prev.stat().st_mtime
        except OSError:
            prev_mtime = 0
        if cur_mtime >= prev_mtime:
            out[day] = path

    return out


def _iter_dates(start_date, end_date):
    if start_date is None or end_date is None:
        return
    day = start_date
    while day <= end_date:
        yield day
        day += timedelta(days=1)


def _compute_target_missing_dates(from_d, to_d, existing_dates: set) -> set:
    """
    Fechas objetivo del rango [from_d, to_d] que aún no están en CORE.
    Solo aplica cuando existe un rango de fechas explícito.
    """
    if from_d is None or to_d is None:
        return set()
    return {d for d in _iter_dates(from_d, to_d) if d not in existing_dates}


def _run_drive_rr_import_for_dates(target_dates: set, outdir: Path, verbose: bool = False) -> Tuple[Dict, int]:
    """
    Ejecuta egc_to_rr.py para intentar cubrir fechas faltantes desde cloud (Drive/Dropbox).
    Devuelve:
      - {date: rr_path} para fechas cubiertas con RR from_jsonl.
      - número de fechas nuevas creadas en esta ejecución.
    """
    if not target_dates:
        return {}, 0

    source_label = "Dropbox" if RR_CLOUD_SOURCE == "dropbox" else "Drive"
    existing_before = _scan_rr_files_by_date(outdir, source_tag="from_jsonl")
    missing_dates = sorted(d for d in target_dates if d not in existing_before)

    if missing_dates:
        script_path = Path(DRIVE_RR_SCRIPT)
        if not script_path.exists():
            print(f"⚠️  {source_label} RR habilitado, pero no existe {script_path}. Se usa fallback Polar.")
        else:
            cmd = [
                sys.executable,
                str(script_path),
                "--outdir",
                str(outdir),
            ]

            if RR_CLOUD_SOURCE == "dropbox":
                if not DROPBOX_FOLDER_PATH:
                    print(
                        "⚠️  Dropbox RR habilitado pero falta HRV_DROPBOX_FOLDER_PATH/DROPBOX_FOLDER_PATH. "
                        "Se usa fallback Polar."
                    )
                    return {}, 0
                cmd.extend(["--dropbox-folder", DROPBOX_FOLDER_PATH])
                if DROPBOX_RECURSIVE:
                    cmd.append("--dropbox-recursive")
            else:
                cmd.extend(["--drive-runtime", DRIVE_RR_RUNTIME])
                if DRIVE_RR_RECURSIVE:
                    cmd.append("--drive-recursive")
                if DRIVE_RR_FOLDER_ID:
                    cmd.extend(["--drive-folder-id", DRIVE_RR_FOLDER_ID])

            if DRIVE_RR_NO_AUX:
                cmd.append("--no-aux")
            if DRIVE_RR_PAIR_LIMIT:
                cmd.extend(["--pair-limit", DRIVE_RR_PAIR_LIMIT])

            _qprint(f"☁️  {source_label} RR: intentando cubrir {len(missing_dates)} fecha(s) faltante(s)...")
            try:
                env = os.environ.copy()
                env["PYTHONIOENCODING"] = "utf-8"
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    check=False,
                    env=env,
                )
                if verbose and result.stdout:
                    print(result.stdout)
                if result.returncode != 0:
                    print(
                        f"⚠️  {source_label} RR devolvió código {result.returncode}. "
                        "Se continúa con fallback Polar."
                    )
                    if result.stderr:
                        print(result.stderr)
            except Exception as exc:
                print(f"⚠️  Error ejecutando {source_label} RR: {exc}. Se continúa con fallback Polar.")

    existing_after = _scan_rr_files_by_date(outdir, source_tag="from_jsonl")
    covered = {d: p for d, p in existing_after.items() if d in target_dates}

    new_created = 0
    for d, p in covered.items():
        prev = existing_before.get(d)
        if prev is None or str(prev) != str(p):
            new_created += 1

    return covered, new_created


def _get_field_variant(data: dict, *keys, default=None):
    """Obtiene el primer valor no-None de múltiples variantes de clave."""
    for key in keys:
        val = data.get(key)
        if val is not None:
            return val
    return default


def _get_color_emoji(color_value, default='⚪'):
    """Convierte valor de color ('Verde', 'Amarillo', 'Rojo') a emoji."""
    return COLOR_EMOJI.get(color_value, default)


def _get_gate_emoji(gate_value, default='⚪'):
    """Convierte gate_badge (p.ej. 'ÁMBAR--') a emoji."""
    if gate_value is None:
        return default
    value = str(gate_value).strip().upper()
    # Quitar sufijos +/- y normalizar
    if value.startswith("VERDE"):
        key = "VERDE"
    elif value.startswith("ÁMBAR") or value.startswith("AMBAR"):
        key = "ÁMBAR"
    elif value.startswith("ROJO"):
        key = "ROJO"
    elif value.startswith("NO"):
        key = "NO"
    else:
        key = value.replace('Á', 'A')
    return GATE_EMOJI.get(key, default)


def _format_metric(value, decimals=1):
    """
    Formatea métrica numérica o devuelve 'N/A'.

    Args:
        value: Valor a formatear
        decimals: Número de decimales (default: 1)

    Returns:
        String formateado o 'N/A'
    """
    # Si pandas no está disponible, verificar None directamente
    if PANDAS_AVAILABLE:
        is_valid = pd.notna(value) and value != 'N/A'
    else:
        is_valid = value is not None and value != 'N/A'

    if is_valid:
        try:
            return f"{float(value):.{decimals}f}"
        except (ValueError, TypeError):
            return 'N/A'
    return 'N/A'


def _normalize_color_value(raw_value: str) -> Optional[int]:
    if raw_value is None:
        return None
    value = str(raw_value).strip().lower()
    if not value or value in {"nan", "none", "n/a"}:
        return None
    value = (
        value.replace("á", "a")
        .replace("é", "e")
        .replace("í", "i")
        .replace("ó", "o")
        .replace("ú", "u")
    )
    if value in {"verde", "green"}:
        return 3
    if value in {"ambar", "amber", "amarillo", "yellow"}:
        return 2
    if value in {"rojo", "red"}:
        return 1
    if value in {"indef", "indefinido", "na", "n/a"}:
        return 0
    try:
        return int(float(value))
    except ValueError:
        return None


def _parse_float(value: str) -> Optional[float]:
    if value is None:
        return None
    value_str = str(value).strip()
    if not value_str or value_str.lower() in {"nan", "none", "n/a"}:
        return None
    try:
        return float(value_str)
    except ValueError:
        return None


def _read_latest_master_row(master_path: Path) -> Optional[Dict[str, Any]]:
    if not master_path.exists():
        print(f"⚠️  Intervals: no se encontró {master_path}")
        return None

    latest_row: Optional[Dict[str, Any]] = None
    latest_date = None
    with master_path.open("r", encoding="utf-8", newline="") as csvfile:
        reader = csv.DictReader(csvfile)
        for row in reader:
            raw_date = (row.get(MASTER_CSV_COLS["fecha"]) or "").strip()
            parsed = _parse_yyyy_mm_dd(raw_date)
            if parsed is None:
                continue
            if latest_date is None or parsed > latest_date:
                latest_date = parsed
                latest_row = row
    if not latest_row or not latest_date:
        print("⚠️  Intervals: no se pudo determinar la última fecha del CORE")
        return None
    latest_row["_date"] = latest_date.isoformat()
    return latest_row


def _build_intervals_payload(row: Dict[str, Any]) -> Dict[str, Any]:
    payload: Dict[str, Any] = {}
    for field_id, source_key in INTERVALS_FIELD_MAP.items():
        master_key = MASTER_CSV_COLS.get(source_key, source_key)
        raw_value = row.get(master_key)
        if source_key.startswith("Color_"):
            mapped = _normalize_color_value(raw_value)
        else:
            mapped = _parse_float(raw_value)
        if mapped is not None:
            payload[field_id] = mapped
    return payload


def _send_intervals_wellness_from_master(master_path: Path) -> None:
    _print_header("🌐 INTERVALS SYNC")
    api_key = (os.environ.get("INTERVALS_API_KEY") or "").strip()
    athlete_id = (os.environ.get("INTERVALS_ATHLETE_ID") or "").strip()
    if not api_key or not athlete_id:
        print("⏭️  Intervals: faltan INTERVALS_API_KEY o INTERVALS_ATHLETE_ID, se omite sync")
        return

    row = _read_latest_master_row(master_path)
    if not row:
        return

    payload = _build_intervals_payload(row)
    if not payload:
        print("⚠️  Intervals: no hay datos válidos para enviar")
        return

    date_value = row.get("_date")
    url = f"{_intervals_api_root()}/athlete/{athlete_id}/wellness/{date_value}"
    headers = {
        "Authorization": _basic_auth_str("API_KEY", api_key),
        "Content-Type": "application/json",
    }

    try:
        response = requests.put(url, headers=headers, json=payload, timeout=30)
    except requests.RequestException as exc:
        print(f"❌ Intervals: error de red: {exc}")
        return

    if response.ok:
        print(f"✅ Intervals: wellness actualizado para {date_value}")
        return

    print(f"⚠️  Intervals: error {response.status_code}")
    try:
        print(response.json())
    except ValueError:
        print(response.text)


def _print_header(title: str, width: int = 25, leading_blank: bool = True, trailing_blank: bool = False):
    if QUIET:
        return
    line = "=" * width
    if leading_blank:
        _qprint("\n" + line)
    else:
        _qprint(line)
    _qprint(title)
    if trailing_blank:
        _qprint(line + "\n")
    else:
        _qprint(line)


def _print_divider(width: int = 30, leading_blank: bool = False, trailing_blank: bool = False):
    if QUIET:
        return
    line = "=" * width
    if leading_blank:
        _qprint("\n" + line)
    else:
        _qprint(line)
    if trailing_blank:
        _qprint("")


def _print_sync_completed(updated_date=None, checkmark=False):
    if QUIET:
        return
    print("\n✅ SINCRONIZACIÓN COMPLETADA")
    #print("=" * 25)
    if updated_date:
        print(f"📊 CORE actualizado hasta hoy ({updated_date})")
    else:
        print("📊 CORE actualizado hasta hoy")
    print("💡 No nuevas sesiones")
    tail = " ✅" if checkmark else "."
    # print(f"   • Todo al día{tail}")


def _print_no_rr_files():
    if QUIET:
        print("⚠️  No hay RR para procesar")
        return
    print("\n⚠️  No hay archivos RR para procesar")
    print("Causas típicas:")
    print("   - Sesiones sin RR en el periodo")
    print("   - Archivos aún no disponibles en cloud (Dropbox/Drive) ni en Polar")


def _print_master_already_updated():
    if QUIET:
        return
    print("\n✅ CORE ya está actualizado con todas las sesiones")
    print("   No hay nada nuevo que procesar")


class _CallbackState:
    def __init__(self):
        self.code = None
        self.error = None
        self.raw_query = None


class OAuthCallbackHandler(BaseHTTPRequestHandler):
    state: _CallbackState = None

    def do_GET(self):
        parsed = urlparse(self.path)
        qs = parse_qs(parsed.query)
        OAuthCallbackHandler.state.raw_query = parsed.query

        if "error" in qs:
            OAuthCallbackHandler.state.error = qs.get("error", ["unknown"])[0]
        if "code" in qs:
            OAuthCallbackHandler.state.code = qs["code"][0]

        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(b"<h3>OK. Ya puedes cerrar esta ventana.</h3>")

    def log_message(self, fmt, *args):
        return


def start_callback_server(redirect_uri: str, state_obj: _CallbackState, timeout_s: int = 180):
    u = urlparse(redirect_uri)
    host = u.hostname or "localhost"
    port = u.port or 80

    OAuthCallbackHandler.state = state_obj

    httpd = HTTPServer((host, port), OAuthCallbackHandler)
    httpd.timeout = 1.0

    t0 = time.time()
    while time.time() - t0 < timeout_s:
        httpd.handle_request()
        if state_obj.code or state_obj.error:
            break


def build_auth_url(client_id: str, redirect_uri: str, scope: str):
    params = {
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": redirect_uri,
    }
    if scope:
        params["scope"] = scope
    return f"{AUTH_URL}?{urlencode(params)}"


def get_production_url():
    """
    Obtiene y normaliza la URL pública en producción.

    Returns:
        URL normalizada con https:// o string vacío si no existe
    """
    public_url = os.environ.get('PUBLIC_URL') or os.environ.get('RAILWAY_PUBLIC_DOMAIN') or ''
    if public_url and not str(public_url).startswith('http'):
        return f"https://{public_url}"
    return public_url


def exchange_code_for_token(code: str, client_id: str, client_secret: str, redirect_uri: Optional[str] = None) -> dict:
    basic = base64.b64encode(f"{client_id}:{client_secret}".encode("utf-8")).decode("ascii")
    headers = {
        "Authorization": f"Basic {basic}",
        "Content-Type": "application/x-www-form-urlencoded",
        "Accept": "application/json;charset=UTF-8",
    }
    data = {
        "grant_type": "authorization_code",
        "code": code,
    }
    if redirect_uri:
        data["redirect_uri"] = redirect_uri

    r = requests.post(TOKEN_URL, headers=headers, data=data, timeout=30)

    if r.status_code >= 400:
        raise RuntimeError(f"Token exchange fallo: {r.status_code} {r.reason}\n{r.text}")

    return r.json()


def api_request(method: str, path: str, token: str, params=None, headers=None, data=None, json_body=None, timeout=60):
    h = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
    if headers:
        h.update(headers)

    url = f"{API_BASE}{path}"
    r = requests.request(
        method=method,
        url=url,
        params=params or {},
        headers=h,
        data=data,
        json=json_body,
        timeout=timeout,
    )
    if r.status_code >= 400:
        raise RuntimeError(f"{method} {url} -> {r.status_code} {r.reason}\n{r.text}")

    ct = (r.headers.get("Content-Type") or "").lower()
    if "application/json" in ct:
        return r.json()
    return r.text


def register_user_if_needed(token: str, member_id: str):
    """Paso obligatorio: registrar usuario"""
    xml = f"<register><member-id>{member_id}</member-id></register>"
    url = f"{API_BASE}/users"

    r = requests.post(
        url,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
            "Content-Type": "application/xml",
        },
        data=xml.encode("utf-8"),
        timeout=30,
    )

    if r.status_code == 409:
        return {"status": "already_registered"}

    if r.status_code == 403:
        raise RuntimeError(f"register_user 403 (no autorizado / consents):\n{r.text}")

    if r.status_code >= 400:
        raise RuntimeError(f"register_user fallo: {r.status_code} {r.reason}\n{r.text}")

    return {"status": "registered"}


def list_exercises(token: str):
    return api_request("GET", "/exercises", token, timeout=60)


def get_exercise_with_samples(token: str, exercise_id: str):
    return api_request(
        "GET",
        f"/exercises/{exercise_id}",
        token,
        params={"samples": "true"},
        timeout=90,
    )


def _normalize_key(key: str) -> str:
    return str(key).strip().lower().replace("-", "_")


def _to_float(value) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        try:
            return float(value)
        except (TypeError, ValueError):
            return None
    value_str = str(value).strip()
    if not value_str or value_str.lower() in {"nan", "none", "null", "n/a"}:
        return None
    value_str = value_str.replace(",", ".")
    try:
        return float(value_str)
    except ValueError:
        return None


def _parse_iso_datetime(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    s = str(value).strip()
    if not s:
        return None
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(s)
    except ValueError:
        return None


def _minutes_between(start_iso: Optional[str], end_iso: Optional[str]) -> Optional[float]:
    start_dt = _parse_iso_datetime(start_iso)
    end_dt = _parse_iso_datetime(end_iso)
    if not start_dt or not end_dt:
        return None
    delta = (end_dt - start_dt).total_seconds() / 60.0
    if delta <= 0:
        return None
    return float(delta)


def _iso_duration_to_minutes(value) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    text = str(value).strip()
    if not text:
        return None

    if text.startswith("PT"):
        hours = re.search(r"([\d.]+)H", text)
        minutes = re.search(r"([\d.]+)M", text)
        seconds = re.search(r"([\d.]+)S", text)
        total = 0.0
        if hours:
            total += float(hours.group(1)) * 60.0
        if minutes:
            total += float(minutes.group(1))
        if seconds:
            total += float(seconds.group(1)) / 60.0
        return total

    return _to_float(text)


def _normalize_sleep_minutes(value) -> Optional[float]:
    """
    Normalize duration-like values to minutes.
    Accepts ISO duration, minutes, seconds, or milliseconds (heuristic).
    """
    minutes = _iso_duration_to_minutes(value)
    if minutes is None:
        return None
    if minutes <= 0:
        return None
    # If value is implausibly large for minutes, infer source unit.
    if minutes > 1440:
        # Looks like seconds.
        if minutes <= 172800:
            return minutes / 60.0
        # Looks like milliseconds.
        if minutes <= 172800000:
            return minutes / 60000.0
    return minutes


def _normalize_resp_rate(value) -> Optional[float]:
    """Normalize nightly respiration to breaths/min."""
    v = _to_float(value)
    if v is None or v <= 0:
        return None
    # If value seems to be respiration interval in ms, convert to brpm.
    if v > 100:
        brpm = 60000.0 / v
        if 4.0 <= brpm <= 40.0:
            return brpm
    return v


def _normalize_pct(value) -> Optional[float]:
    v = _to_float(value)
    if v is None:
        return None
    if v <= 1.0:
        return v * 100.0
    return v


def _find_first_value(payload, candidate_keys: List[str], as_float: bool = False):
    keys = {_normalize_key(k) for k in candidate_keys}
    stack = [payload]
    while stack:
        current = stack.pop()
        if isinstance(current, dict):
            for raw_key, raw_value in current.items():
                if _normalize_key(raw_key) in keys:
                    if as_float:
                        f = _to_float(raw_value)
                        if f is not None:
                            return f
                    else:
                        if raw_value is not None and str(raw_value).strip() != "":
                            return raw_value
                if isinstance(raw_value, (dict, list)):
                    stack.append(raw_value)
        elif isinstance(current, list):
            for item in current:
                if isinstance(item, (dict, list)):
                    stack.append(item)
    return None


def _extract_interruptions_counts(sleep_json: dict) -> Tuple[Optional[float], Optional[float]]:
    if not isinstance(sleep_json, dict):
        return None, None

    evaluation = _get_field_variant(sleep_json, "evaluation", "sleep-evaluation", "sleep_evaluation", default=None)
    interruptions = None
    if isinstance(evaluation, dict):
        interruptions = _get_field_variant(
            evaluation,
            "interruptions",
            "sleep-interruptions",
            "sleep_interruptions",
            default=None,
        )

    long_count = None
    total_count = None
    if isinstance(interruptions, dict):
        long_count = _to_float(_get_field_variant(interruptions, "longCount", "long_count", "long-count", default=None))
        total_count = _to_float(_get_field_variant(interruptions, "totalCount", "total_count", "total-count", "count", default=None))
    elif isinstance(interruptions, list):
        total_items = 0
        long_items = 0
        for item in interruptions:
            if not isinstance(item, dict):
                continue
            total_items += 1
            kind = str(_find_first_value(item, ["type", "kind", "interruption_type"]) or "").strip().lower()
            if "long" in kind:
                long_items += 1
                continue
            dur_min = _normalize_sleep_minutes(_find_first_value(item, ["duration", "interruption_duration"]))
            if dur_min is not None and dur_min >= 5.0:
                long_items += 1
        if total_items > 0:
            total_count = float(total_items)
            long_count = float(long_items)

    if long_count is None:
        long_count = _find_first_value(
            sleep_json,
            [
                "longCount",
                "long_count",
                "long-count",
                "sleep_long_interruptions",
                "interruptions_long",
            ],
            as_float=True,
        )
    if total_count is None:
        total_count = _find_first_value(
            sleep_json,
            [
                "totalCount",
                "total_count",
                "total-count",
                "interruptions_total",
                "sleep_interruptions_total",
                "interruptions_count",
                "number_of_interruptions",
            ],
            as_float=True,
        )

    return long_count, total_count


def _extract_sleep_fields(sleep_json: Optional[dict]) -> Dict[str, Any]:
    if not isinstance(sleep_json, dict):
        return {}

    sleep_start = _find_first_value(sleep_json, ["sleep_start_time", "sleep-start-time", "sleepStartTime"])
    sleep_end = _find_first_value(sleep_json, ["sleep_end_time", "sleep-end-time", "sleepEndTime"])

    asleep_duration_min = _normalize_sleep_minutes(
        _find_first_value(
            sleep_json,
            ["asleep_duration", "asleep-duration", "sleep_duration", "sleep-duration", "sleepDuration"],
        )
    )
    span_min = _normalize_sleep_minutes(
        _find_first_value(sleep_json, ["sleep_span", "sleep-span", "sleepSpan", "time_in_bed"])
    )
    if span_min is None:
        span_min = _minutes_between(sleep_start, sleep_end)

    deep_min = _normalize_sleep_minutes(_find_first_value(sleep_json, ["deep_sleep", "deep-sleep", "deepSleep", "sleep_n3"]))
    rem_min = _normalize_sleep_minutes(_find_first_value(sleep_json, ["rem_sleep", "rem-sleep", "remSleep", "sleep_rem"]))
    light_min = _normalize_sleep_minutes(_find_first_value(sleep_json, ["light_sleep", "light-sleep", "lightSleep"]))

    if asleep_duration_min is None:
        parts = [x for x in (deep_min, rem_min, light_min) if x is not None]
        if parts:
            asleep_duration_min = float(sum(parts))

    deep_pct = _to_float(_find_first_value(sleep_json, ["polar_deep_pct", "deep_pct", "deep_percentage"]))
    rem_pct = _to_float(_find_first_value(sleep_json, ["polar_rem_pct", "rem_pct", "rem_percentage"]))
    if asleep_duration_min and asleep_duration_min > 0:
        if deep_pct is None and deep_min is not None:
            deep_pct = 100.0 * deep_min / asleep_duration_min
        if rem_pct is None and rem_min is not None:
            rem_pct = 100.0 * rem_min / asleep_duration_min

    continuity = _to_float(_find_first_value(sleep_json, ["continuity", "sleep_continuity"]))
    continuity_index = _to_float(_find_first_value(sleep_json, ["continuity_index", "continuity-class", "continuity_class"]))
    efficiency_pct = _normalize_pct(_find_first_value(sleep_json, ["efficiency_pct", "sleep_efficiency", "efficiency"]))
    if efficiency_pct is None and asleep_duration_min is not None and span_min is not None and span_min > 0:
        efficiency_pct = 100.0 * asleep_duration_min / span_min
    sleep_score = _to_float(_find_first_value(sleep_json, ["sleep_score", "sleep-score"]))
    long_count, total_count = _extract_interruptions_counts(sleep_json)

    out: Dict[str, Any] = {}
    if asleep_duration_min is not None:
        out["polar_sleep_duration_min"] = asleep_duration_min
    if span_min is not None:
        out["polar_sleep_span_min"] = span_min
    if deep_pct is not None:
        out["polar_deep_pct"] = deep_pct
    if rem_pct is not None:
        out["polar_rem_pct"] = rem_pct
    if efficiency_pct is not None:
        out["polar_efficiency_pct"] = efficiency_pct
    if continuity is not None:
        out["polar_continuity"] = continuity
    if continuity_index is not None:
        out["polar_continuity_index"] = continuity_index
    if long_count is not None:
        out["polar_interruptions_long"] = long_count
    if total_count is not None:
        out["polar_interruptions_total"] = total_count
    if sleep_score is not None:
        out["polar_sleep_score"] = sleep_score
    return out


def _extract_nightly_fields(nightly_json: Optional[dict]) -> Dict[str, Any]:
    if not isinstance(nightly_json, dict):
        return {}

    night_rmssd = _to_float(
        _find_first_value(
            nightly_json,
            ["heart_rate_variability_avg", "heart-rate-variability-avg", "nightly_rmssd"],
            as_float=True,
        )
    )
    night_rri = _to_float(
        _find_first_value(
            nightly_json,
            ["nightly_rri", "rri_avg", "heart_rate_rri_avg", "heart-rate-rri-avg"],
            as_float=True,
        )
    )
    hr_avg = _to_float(_find_first_value(nightly_json, ["heart_rate_avg", "heart-rate-avg", "hr_avg"], as_float=True))
    if night_rri is None and hr_avg is not None and hr_avg > 0:
        night_rri = 60000.0 / hr_avg

    night_resp_raw = _find_first_value(
        nightly_json,
        ["breathing_rate_avg", "breathing-rate-avg", "nightly_resp", "nightly_resp_int"],
        as_float=True,
    )
    night_resp = _normalize_resp_rate(night_resp_raw)

    out: Dict[str, Any] = {}
    if night_rmssd is not None:
        out["polar_night_rmssd"] = night_rmssd
    if night_rri is not None:
        out["polar_night_rri"] = night_rri
    if night_resp is not None:
        out["polar_night_resp"] = night_resp
    return out


def fetch_polar_sleep(token: str, user_id: str, date_str: str) -> Optional[dict]:
    """Fetch sleep data for a date. Returns None if not available."""
    if not token or not user_id or not date_str:
        return None
    try:
        # AccessLink sleep endpoint is scoped to authorized user (no user_id in path).
        resp = api_request("GET", f"/users/sleep/{date_str}", token, timeout=30)
        return resp if isinstance(resp, dict) else None
    except Exception as exc:
        print(f"⚠️ Sleep fetch failed for {date_str}: {exc}")
        return None


def fetch_polar_nightly_recharge(token: str, user_id: str, date_str: str) -> Optional[dict]:
    """Fetch nightly recharge data for a date. Returns None if not available."""
    if not token or not user_id or not date_str:
        return None
    try:
        # AccessLink nightly endpoint is scoped to authorized user (no user_id in path).
        resp = api_request("GET", f"/users/nightly-recharge/{date_str}", token, timeout=30)
        return resp if isinstance(resp, dict) else None
    except Exception as exc:
        print(f"⚠️ Nightly-recharge fetch failed for {date_str}: {exc}")
        return None


def _normalize_intervals_activities_payload(data: Any) -> list:
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]
    if isinstance(data, dict):
        for key in ("activities", "data", "results", "items"):
            value = data.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
    return []


def fetch_intervals_activities(api_key: str, athlete_id: str, date_str: str) -> list:
    """Fetch activities for a date from Intervals.icu."""
    if not api_key or not athlete_id or not date_str:
        return []
    url = f"{_intervals_api_root()}/athlete/{athlete_id}/activities"
    headers = {"Authorization": _basic_auth_str("API_KEY", api_key)}
    params = {"oldest": date_str, "newest": date_str}
    try:
        resp = requests.get(url, headers=headers, params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        return _normalize_intervals_activities_payload(data)
    except Exception as exc:
        print(f"⚠️ Intervals fetch failed for {date_str}: {exc}")
        return []


def _extract_activity_datetime(activity: dict) -> Optional[datetime]:
    for key in ("start_date_local", "start_date", "startDateLocal", "startDate", "start_time", "startTime"):
        raw = _find_first_value(activity, [key])
        parsed = _parse_iso_datetime(raw) if raw is not None else None
        if parsed is not None:
            return parsed
    return None


def _aggregate_intervals_activity_fields(activities: list) -> Dict[str, Any]:
    if not activities:
        return {"intervals_n_acts": 0}

    rows = []
    for act in activities:
        if not isinstance(act, dict):
            continue
        row = {
            "activity": act,
            "load": _find_first_value(act, ["icu_training_load", "training_load", "load"], as_float=True),
            "intensity": _find_first_value(act, ["icu_intensity", "intensity"], as_float=True),
            "moving_time_s": _find_first_value(act, ["moving_time", "movingTime", "moving time"], as_float=True),
            "avg_hr": _find_first_value(act, ["average_heartrate", "avg_hr", "average_heart_rate"], as_float=True),
            "max_hr": _find_first_value(act, ["max_heartrate", "max_hr", "max_heart_rate"], as_float=True),
            "atl": _find_first_value(act, ["icu_atl", "atl"], as_float=True),
            "ctl": _find_first_value(act, ["icu_ctl", "ctl"], as_float=True),
            "tsb": _find_first_value(act, ["icu_tsb", "tsb"], as_float=True),
            "rpe": _find_first_value(act, ["icu_rpe", "rpe"], as_float=True),
            "resting_hr": _find_first_value(act, ["resting_heartrate", "resting_hr"], as_float=True),
            "type": _find_first_value(act, ["type", "activity_type", "sport"]),
            "dt": _extract_activity_datetime(act),
        }
        rows.append(row)

    if not rows:
        return {"intervals_n_acts": 0}

    load_vals = [r["load"] for r in rows if r["load"] is not None]
    intensity_vals = [r["intensity"] for r in rows if r["intensity"] is not None]
    duration_vals = [r["moving_time_s"] for r in rows if r["moving_time_s"] is not None]
    avg_hr_vals = [r["avg_hr"] for r in rows if r["avg_hr"] is not None]
    max_hr_vals = [r["max_hr"] for r in rows if r["max_hr"] is not None]

    main_row = max(rows, key=lambda r: r["load"] if r["load"] is not None else float("-inf"))
    def _dt_key(row):
        dt = row.get("dt")
        if dt is None:
            return float("-inf")
        try:
            return float(dt.timestamp())
        except (AttributeError, OSError, OverflowError, ValueError):
            return float("-inf")

    latest_row = max(rows, key=_dt_key)

    out: Dict[str, Any] = {"intervals_n_acts": len(rows)}
    if load_vals:
        out["intervals_load"] = float(sum(load_vals))
        out["intervals_load_max"] = float(max(load_vals))
    if intensity_vals:
        out["intervals_intensity_max"] = float(max(intensity_vals))
    if duration_vals:
        out["intervals_duration_min"] = float(sum(duration_vals) / 60.0)
    if avg_hr_vals:
        out["intervals_avg_hr"] = float(sum(avg_hr_vals) / len(avg_hr_vals))
    if max_hr_vals:
        out["intervals_max_hr"] = float(max(max_hr_vals))

    main_type = main_row.get("type")
    if main_type is not None:
        out["intervals_type_main"] = str(main_type)

    for dst_key, src_key in (
        ("intervals_atl", "atl"),
        ("intervals_ctl", "ctl"),
        ("intervals_tsb", "tsb"),
        ("intervals_rpe", "rpe"),
        ("intervals_resting_hr", "resting_hr"),
    ):
        value = latest_row.get(src_key)
        if value is not None:
            out[dst_key] = float(value)

    return out


def _ensure_sleep_schema(df):
    out = df.copy()
    for col in SLEEP_COLUMNS:
        if col not in out.columns:
            out[col] = float("nan")
    out = out[SLEEP_COLUMNS].copy()
    out["Fecha"] = out["Fecha"].astype(str)
    return out


def _recalculate_sleep_derived(df):
    out = _ensure_sleep_schema(df)
    out["_fecha_dt"] = pd.to_datetime(out["Fecha"], errors="coerce")
    out = out.sort_values("_fecha_dt").drop(columns=["_fecha_dt"]).reset_index(drop=True)

    numeric_cols = [c for c in SLEEP_COLUMNS if c != "Fecha"]
    for col in numeric_cols:
        out[col] = pd.to_numeric(out[col], errors="coerce")

    # Normalize sleep minutes and nightly respiration for legacy rows too.
    if "polar_sleep_duration_min" in out.columns:
        out["polar_sleep_duration_min"] = out["polar_sleep_duration_min"].apply(_normalize_sleep_minutes)
    if "polar_sleep_span_min" in out.columns:
        out["polar_sleep_span_min"] = out["polar_sleep_span_min"].apply(_normalize_sleep_minutes)
    if "polar_night_resp" in out.columns:
        out["polar_night_resp"] = out["polar_night_resp"].apply(_normalize_resp_rate)
    if "polar_efficiency_pct" in out.columns:
        missing_eff = out["polar_efficiency_pct"].isna()
        can_derive = (
            out["polar_sleep_duration_min"].notna()
            & out["polar_sleep_span_min"].notna()
            & (out["polar_sleep_span_min"] > 0)
        )
        idx = missing_eff & can_derive
        out.loc[idx, "polar_efficiency_pct"] = (
            100.0 * out.loc[idx, "polar_sleep_duration_min"] / out.loc[idx, "polar_sleep_span_min"]
        )

    # Sleep-only percentiles
    dur = out["polar_sleep_duration_min"].dropna()
    out["sleep_dur_p10"] = float(dur.quantile(0.10)) if len(dur) > 0 else float("nan")
    out["sleep_dur_p90"] = float(dur.quantile(0.90)) if len(dur) > 0 else float("nan")

    ints = out["polar_interruptions_long"].dropna()
    out["sleep_int_p90"] = float(ints.quantile(0.90)) if len(ints) > 0 else float("nan")

    return out


def upsert_sleep_row(sleep_row: Dict[str, Any]) -> bool:
    if not PANDAS_AVAILABLE:
        print("⚠️  Pandas no disponible: se omite actualización de sleep.csv")
        return False

    fecha = str(sleep_row.get("Fecha", "")).strip()
    if not fecha:
        return False

    source_path = None
    if SLEEP_PATH.exists():
        source_path = SLEEP_PATH
    elif LEGACY_SLEEP_PATH.exists():
        source_path = LEGACY_SLEEP_PATH

    if source_path is not None:
        try:
            sleep_df = pd.read_csv(source_path)
        except (FileNotFoundError, pd.errors.EmptyDataError, OSError, ValueError):
            sleep_df = pd.DataFrame(columns=SLEEP_COLUMNS)
    else:
        sleep_df = pd.DataFrame(columns=SLEEP_COLUMNS)

    sleep_df = _ensure_sleep_schema(sleep_df)
    sleep_df = sleep_df[sleep_df["Fecha"].astype(str) != fecha]

    row = {col: sleep_row.get(col, float("nan")) for col in SLEEP_COLUMNS}
    row["Fecha"] = fecha
    if row.get("intervals_type_main") is None:
        row["intervals_type_main"] = ""

    sleep_df = pd.concat([sleep_df, pd.DataFrame([row])], ignore_index=True)
    sleep_df = _recalculate_sleep_derived(sleep_df)
    sleep_df = sleep_df[SLEEP_COLUMNS]

    SLEEP_PATH.parent.mkdir(parents=True, exist_ok=True)
    sleep_df.to_csv(SLEEP_PATH, index=False)
    return True


def _polar_sleep_date_candidates(date_str: str) -> List[str]:
    d = _parse_yyyy_mm_dd(date_str)
    if d is None:
        return [date_str]
    prev = (d - timedelta(days=1)).isoformat()
    return [date_str, prev]


def fetch_and_upsert_sleep(token: str, user_id: Optional[str], processed_date) -> bool:
    if processed_date is None:
        return False

    date_str = processed_date.isoformat() if hasattr(processed_date, "isoformat") else str(processed_date)
    if not date_str:
        return False

    sleep_row: Dict[str, Any] = {col: float("nan") for col in SLEEP_COLUMNS}
    sleep_row["Fecha"] = date_str

    if user_id:
        sleep_json = None
        sleep_used_date = None
        nightly_json = None
        nightly_used_date = None
        for candidate_date in _polar_sleep_date_candidates(date_str):
            if sleep_json is None:
                resp = fetch_polar_sleep(token, user_id, candidate_date)
                if isinstance(resp, dict) and len(resp) > 0:
                    sleep_json = resp
                    sleep_used_date = candidate_date
            if nightly_json is None:
                resp2 = fetch_polar_nightly_recharge(token, user_id, candidate_date)
                if isinstance(resp2, dict) and len(resp2) > 0:
                    nightly_json = resp2
                    nightly_used_date = candidate_date
            if sleep_json is not None and nightly_json is not None:
                break

        if sleep_json:
            sleep_row.update(_extract_sleep_fields(sleep_json))
            if sleep_used_date and sleep_used_date != date_str:
                print(f"ℹ️  Sleep tomado desde {sleep_used_date} para fecha {date_str}")
        if nightly_json:
            sleep_row.update(_extract_nightly_fields(nightly_json))
            if nightly_used_date and nightly_used_date != date_str:
                print(f"ℹ️  Nightly tomado desde {nightly_used_date} para fecha {date_str}")
    else:
        print("⚠️  x_user_id ausente: se omite fetch Polar sleep/nightly")

    # Training load now lives in sessions_day.csv (generated by build_sessions.py)
    # — no longer fetched here.

    saved = upsert_sleep_row(sleep_row)
    return saved


def _update_sleep_for_dates(token: str, user_id: Optional[str], dates_to_sync: List) -> int:
    """Fetch+upsert sleep rows for a list of dates. Returns successful upserts."""
    if not dates_to_sync:
        return 0

    done = 0
    seen = set()
    for d in dates_to_sync:
        if d is None:
            continue
        key = d.isoformat() if hasattr(d, "isoformat") else str(d)
        if key in seen:
            continue
        seen.add(key)
        try:
            if fetch_and_upsert_sleep(token, user_id, d):
                done += 1
        except Exception as exc:
            print(f"⚠️  Sleep fetch/upsert falló para {key}: {exc}")
    return done


def _today_date():
    return datetime.now().date()


def _default_sleep_refresh_dates() -> List:
    today = _today_date()
    return [today, today - timedelta(days=1)]


def extract_rr_ms(exercise_json: dict):
    """Extrae RR intervals (sample-type 11)"""
    rr = []
    samples = exercise_json.get("samples") or []
    for s in samples:
        st = _get_field_variant(s, *FIELD_SAMPLE_TYPE)
        if str(st) != "11":
            continue

        data = str(s.get("data", ""))
        for tok in data.split(","):
            tok = tok.strip()
            if not tok or tok.upper() == "NULL":
                continue
            try:
                v = float(tok)  # ms
            except ValueError:
                continue
            offline = 0 if RR_MIN_MS <= v <= RR_MAX_MS else 1
            rr.append((v, offline))
    return rr


def write_rr_csv(rr, out_path: str):
    """Escribe CSV formato endurance_hrv.py"""
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("duration,offline\n")
        for v, off in rr:
            f.write(f"{v:.3f},{off}\n")


def passes_filters(ex_item: dict, from_d, to_d, sports_set, max_duration_min, debug=False):
    """Filtra ejercicios por fecha, deporte y duración"""
    
    if debug:
        print(f"\n  🔍 Evaluando: {ex_item.get('id', 'N/A')}")
    
    # Filtro fecha
    st = _get_field_variant(ex_item, *FIELD_START_TIME)
    dt = _iso_to_dt(st)
    if dt:
        d = dt.date()
        if debug:
            print(f"     Fecha: {d} | Rango: {from_d} a {to_d}")
        
        if from_d and d < from_d:
            if debug:
                print(f"     ❌ Fecha < from_d ({d} < {from_d})")
            return False
        if to_d and d > to_d:
            if debug:
                print(f"     ❌ Fecha > to_d ({d} > {to_d})")
            return False
        
        if debug:
            print(f"     ✅ Fecha OK")
    else:
        if debug:
            print(f"     ⚠️  Sin fecha parseable: {st}")

    # Filtro deporte (comparación EXACTA)
    if sports_set:
        sp = _get_field_variant(ex_item, *FIELD_SPORT, default="")

        if debug:
            print(f"     Sport: '{sp}' | Buscando: {sports_set}")
        
        if sp not in sports_set:
            if debug:
                print(f"     ❌ Sport no coincide")
            return False
        
        if debug:
            print(f"     ✅ Sport OK")

    # Filtro duración
    if max_duration_min:
        duration_str = ex_item.get("duration", "")
        if duration_str:
            duration_min = parse_duration_to_minutes(duration_str)
            
            if debug:
                print(f"     Duración: {duration_str} = {duration_min:.2f} min | Max: {max_duration_min}")
            
            if duration_min > max_duration_min:
                if debug:
                    print(f"     ❌ Duración excedida ({duration_min:.2f} > {max_duration_min})")
                return False
            
            if debug:
                print(f"     ✅ Duración OK")

    if debug:
        print(f"     ✅✅ PASA TODOS LOS FILTROS")
    
    return True


def parse_duration_to_minutes(duration_str):
    """
    PT10M30S -> 10.5
    PT506.615S -> 8.44
    PT1H30M -> 90
    """
    # Soportar decimales en cada componente
    hours = re.search(r'([\d.]+)H', duration_str)
    minutes = re.search(r'([\d.]+)M', duration_str)
    seconds = re.search(r'([\d.]+)S', duration_str)
    
    total_minutes = 0.0
    if hours:
        total_minutes += float(hours.group(1)) * 60
    if minutes:
        total_minutes += float(minutes.group(1))
    if seconds:
        total_minutes += float(seconds.group(1)) / 60
    
    return total_minutes


def do_oauth_flow():
    """Ejecuta flujo OAuth completo"""
    if not CLIENT_ID or not CLIENT_SECRET:
        print("❌ Faltan credenciales en .env", file=sys.stderr)
        sys.exit(2)

    # 1) Callback server en thread
    cb_state = _CallbackState()
    server_thread = threading.Thread(
        target=start_callback_server,
        args=(REDIRECT_URI, cb_state, 180),
        daemon=True,
    )
    server_thread.start()

    # 2) OAuth
    auth_url = build_auth_url(CLIENT_ID, REDIRECT_URI, SCOPE)
    print("🔐 Abriendo navegador para autorizar...")
    webbrowser.open(auth_url)

    server_thread.join(timeout=190)
    
    if cb_state.error:
        raise RuntimeError(f"OAuth error: {cb_state.error}")
    if not cb_state.code:
        raise RuntimeError("No se recibió código de autorización")

    print("✅ Código recibido. Intercambiando por token...")

    # 3) Token exchange
    token_json = exchange_code_for_token(cb_state.code, CLIENT_ID, CLIENT_SECRET, REDIRECT_URI)
    access_token = token_json.get("access_token")
    x_user_id = token_json.get("x_user_id")

    if not access_token:
        raise RuntimeError(f"No vino access_token:\n{json.dumps(token_json, indent=2)}")

    print(f"✅ Token OK. user_id: {x_user_id}")

    # Guardar tokens
    token_json['obtained_at'] = time.time()
    # Guardar tokens (soporta Railway Volume via POLAR_TOKEN_PATH=/data/polar_tokens.json)
    TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = TOKEN_FILE.with_suffix(TOKEN_FILE.suffix + '.tmp')
    tmp_path.write_text(json.dumps(token_json, indent=2), encoding='utf-8')
    tmp_path.replace(TOKEN_FILE)
    try:
        os.chmod(TOKEN_FILE, 0o600)
    except OSError:
        pass  # chmod may not be supported on Windows

    return access_token, x_user_id


def load_tokens():
    """Carga tokens guardados"""
    if not TOKEN_FILE.exists():
        return None, None

    try:
        tokens = json.loads(TOKEN_FILE.read_text(encoding='utf-8'))
    except (json.JSONDecodeError, OSError, ValueError, UnicodeDecodeError):
        return None, None

    obtained_at = float(tokens.get('obtained_at', 0) or 0)
    expires_in = float(tokens.get('expires_in', 0) or 0)

    # Si no tenemos expires_in, devolvemos el token igualmente (Polar puede no informarlo en algunos casos)
    if expires_in > 0 and (time.time() - obtained_at) > expires_in:
        return None, None

    return tokens.get('access_token'), tokens.get('x_user_id')


def get_last_date_from_master():
    """Lee última fecha registrada en ENDURANCE_HRV_master_CORE.csv"""
    master_file = CORE_PATH

    if not master_file.exists() or not PANDAS_AVAILABLE:
        return None

    try:
        df = pd.read_csv(master_file)

        if 'Fecha' not in df.columns or df.empty:
            return None

        # Obtener última fecha (asumiendo formato YYYY-MM-DD)
        last_date_str = df['Fecha'].max()
        last_date = datetime.strptime(last_date_str, '%Y-%m-%d').date()

        return last_date

    except (FileNotFoundError, pd.errors.EmptyDataError, ValueError, KeyError) as e:
        print(f"⚠️  Error leyendo CORE: {e}")
        return None

def get_existing_dates_from_master():
    """Obtiene set de fechas ya existentes en CORE (ENDURANCE_HRV_master_CORE.csv)"""
    master_file = CORE_PATH

    if not master_file.exists() or not PANDAS_AVAILABLE:
        return set()

    try:
        df = pd.read_csv(master_file)

        if 'Fecha' not in df.columns or df.empty:
            return set()

        # Convertir todas las fechas a date objects
        dates = set()
        for date_str in df['Fecha']:
            try:
                date_obj = datetime.strptime(str(date_str), '%Y-%m-%d').date()
                dates.add(date_obj)
            except (ValueError, TypeError):
                pass  # Skip invalid date formats

        return dates

    except (FileNotFoundError, pd.errors.EmptyDataError, KeyError) as e:
        print(f"⚠️  Error leyendo fechas del CORE: {e}")
        return set()

def show_last_daily_summary():
    """Muestra el último daily summary (FINAL si existe, si no CORE)."""
    if not PANDAS_AVAILABLE:
        return

    if FINAL_PATH.exists():
        try:
            df = pd.read_csv(FINAL_PATH)

            if df.empty or 'Fecha' not in df.columns:
                return

            # Obtener última medición
            last_row = df.sort_values('Fecha').iloc[-1]

            _print_header("💓 Última Medición HRV (V4)")
            print("")

            fecha = last_row.get("Fecha", "N/A")
            hr = last_row.get("HR_today", "N/A")
            rmssd = last_row.get("RMSSD_stable", "N/A")
            gate = last_row.get("gate_badge", "N/A")
            action = last_row.get("Action", "N/A")
            reason = last_row.get("gate_razon_base60", "N/A")
            calidad = last_row.get("Calidad", "N/A")
            stab = last_row.get("HRV_Stability", "N/A")
            degraded = str(last_row.get("baseline60_degraded", False)).strip().lower() in {"true", "1", "yes"}

            gate_emoji = _get_gate_emoji(gate)

            print(f"📅 Fecha:          {fecha}")
            print(f"💓 HR hoy:         {_format_metric(hr)} bpm")
            print(f"📊 RMSSD:          {_format_metric(rmssd)} ms")
            print(f"🚦 Gate:           {gate_emoji} {gate}")
            print(f"🧭 Acción:         {action}")
            print(f"🧾 Razón gate:     {reason}")
            print(f"✅ Calidad:        {calidad}")
            print(f"📈 Estabilidad:    {stab}")
            if bool(degraded):
                print("⚠️  Warning base:  baseline60_degraded=True")
            return

        except (FileNotFoundError, pd.errors.EmptyDataError, KeyError, IndexError) as e:
            print(f"⚠️  Error mostrando summary FINAL: {e}")

    # Fallback: CORE
    if not CORE_PATH.exists():
        return

    try:
        df = pd.read_csv(CORE_PATH)

        if df.empty or 'Fecha' not in df.columns:
            return

        # Obtener última medición
        last_row = df.sort_values('Fecha').iloc[-1]

        _print_header("💓 Última Medición HRV (CORE)")
        print("")

        fecha = last_row.get("Fecha", "N/A")
        hr = last_row.get("HR_stable", "N/A")
        rmssd = last_row.get("RMSSD_stable", "N/A")
        calidad = last_row.get("Calidad", "N/A")
        stab = last_row.get("HRV_Stability", "N/A")

        print(f"📅 Fecha:          {fecha}")
        print(f"💓 HR promedio:    {_format_metric(hr)} bpm")
        print(f"📊 RMSSD:          {_format_metric(rmssd)} ms")
        print(f"✅ Calidad:        {calidad}")
        print(f"📈 Estabilidad:    {stab}")

        flags = last_row.get("Flags", "")
        if pd.notna(flags) and flags:
            print(f"🚩 Flags:          {flags}")

    except (FileNotFoundError, pd.errors.EmptyDataError, KeyError, IndexError) as e:
        print(f"⚠️  Error mostrando summary CORE: {e}")

def show_last_7_days_summary():
    """Muestra resumen compacto de los últimos 7 días (FINAL si existe, si no CORE)."""
    if not PANDAS_AVAILABLE:
        return

    use_final = FINAL_PATH.exists()
    src_path = FINAL_PATH if use_final else CORE_PATH

    if not src_path.exists():
        return

    try:
        df = pd.read_csv(src_path)

        if df.empty or 'Fecha' not in df.columns:
            return

        # Obtener últimos 7 días
        df_sorted = df.sort_values('Fecha')
        last_7 = df_sorted.tail(7)

        if len(last_7) == 0:
            return

        print("")
        title = "📊 RESUMEN ÚLTIMOS 7 DÍAS (V4)" if use_final else "📊 RESUMEN ÚLTIMOS 7 DÍAS (CORE)"
        _print_header(title)

        for _, row in last_7.iterrows():
            fecha = row.get("Fecha", "N/A")

            # Formatear fecha a YY-MM-DD
            fecha_str = fecha
            if isinstance(fecha, str) and len(fecha) == DATE_STRING_LENGTH:  # YYYY-MM-DD
                fecha_str = fecha[2:]  # Quitar "20" del año → YY-MM-DD

            hr = row.get("HR_today", "N/A") if use_final else row.get("HR_stable", "N/A")
            rmssd = row.get("RMSSD_stable", "N/A")

            # Formatear métricas (sin unidad)
            hr_str = _format_metric(hr)
            rmssd_str = _format_metric(rmssd)

            if use_final:
                gate = row.get("gate_badge", "N/A")
                action = row.get("Action", "N/A")
                gate_emoji = _get_gate_emoji(gate)
                print(f"{fecha_str}  💓{hr_str:>5}  📊{rmssd_str:>5}  {gate_emoji} {gate}  → {action}")
            else:
                print(f"{fecha_str}  💓{hr_str:>5}  📊{rmssd_str:>5}")

    except (FileNotFoundError, pd.errors.EmptyDataError, KeyError, IndexError) as e:
        print(f"⚠️  Error mostrando resumen 7 días: {e}")

def show_latest_hrv_summaries():
    """Muestra el resumen diario y el histórico corto más recientes."""
    show_last_daily_summary()
    show_last_7_days_summary()

def calculate_missing_days():
    """Calcula cuántos días faltan desde última medición hasta hoy"""
    last_date = get_last_date_from_master()
    today = datetime.now().date()
    
    if last_date is None:
        # Sin CORE o sin datos, usar 7 días por defecto
        return 7, None
    
    # Calcular días faltantes
    days_missing = (today - last_date).days
    
    # Si última fecha es hoy, no hay nada que descargar
    if days_missing <= 0:
        return 0, last_date
    
    return days_missing, last_date


def build_endurance_hrv_cmd(rr_files):
    """Construye comando para endurance_hrv.py usando --rr-file."""
    cmd = [sys.executable, "endurance_hrv.py"]
    for f in rr_files:
        cmd.extend(["--rr-file", str(f)])
    return cmd


def run_endurance_v4lite_only() -> bool:
    """Ejecuta endurance_v4lite.py sin reprocesar RR/CORE."""
    if not Path("endurance_v4lite.py").exists():
        print("❌ endurance_v4lite.py no encontrado")
        return False
    try:
        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"
        result = subprocess.run(
            [sys.executable, "endurance_v4lite.py"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=True,
            env=env,
        )
        if result.stdout:
            print(result.stdout)
        return True
    except subprocess.CalledProcessError as exc:
        print(f"⚠️  Error ejecutando endurance_v4lite.py (código {exc.returncode})")
        if exc.stdout:
            print(exc.stdout)
        if exc.stderr:
            print(exc.stderr)
        return False


def _refresh_sleep_and_outputs(access_token: str, x_user_id: Optional[str], run_v4lite: bool = False, dates: Optional[List] = None) -> None:
    target_dates = dates if dates is not None else _default_sleep_refresh_dates()
    _update_sleep_for_dates(access_token, x_user_id, target_dates)
    if run_v4lite:
        _qprint("▶️  Regenerando FINAL/DASHBOARD con sleep actualizado...")
        run_endurance_v4lite_only()

def main():
    parser = argparse.ArgumentParser(description='Polar HRV Automation')
    parser.add_argument('--auth', action='store_true', help='Forzar re-autenticación')
    parser.add_argument('--days', type=int, help='Días hacia atrás (ignora --auto)')
    parser.add_argument('--all', action='store_true', help='Todas las sesiones (ignora --days y --auto)')
    parser.add_argument('--auto', action='store_true', help='Detectar automáticamente días faltantes desde último registro')
    parser.add_argument('--process', action='store_true', help='Ejecutar endurance_hrv.py + endurance_v4lite.py después')
    parser.add_argument('--debug-sports', action='store_true', help='Mostrar deportes de todas las sesiones encontradas')
    parser.add_argument('--verbose', action='store_true', help='Mostrar detalles de cada archivo procesado')
    args = parser.parse_args()

    # _print_header("  POLAR HRV AUTOMATION")

    # Autenticación
    # En PRODUCCIÓN (Railway/Render/Heroku) NO se puede abrir navegador ni levantar callback server local.
    # La autorización debe hacerse vía Web UI: /auth -> /auth/callback, que guarda TOKEN_FILE.
    if args.auth:
        if IS_PRODUCTION:
            public_url = get_production_url()
            hint = f"{public_url.rstrip('/')}/auth" if public_url else "/auth"
            print(f"❌ En producción no se admite --auth interactivo. Abre {hint} para autorizar.", file=sys.stderr)
            sys.exit(3)
        access_token, x_user_id = do_oauth_flow()
    else:
        access_token, x_user_id = load_tokens()
        if not access_token:
            if IS_PRODUCTION:
                public_url = get_production_url()
                hint = f"{public_url.rstrip('/')}/auth" if public_url else "/auth"
                print(f"❌ Falta autorización. Abre {hint} para iniciar sesión en Polar y autorizar la app.", file=sys.stderr)
                sys.exit(3)
            print("⚠️  Token ausente/expirado, iniciando OAuth local...")
            access_token, x_user_id = do_oauth_flow()

    # Registrar usuario (obligatorio)
    member_id = f"local_{x_user_id or 'user'}"
    reg = register_user_if_needed(access_token, member_id)
    # print(f"📝 Usuario: {reg.get('status')}")

    # Listar ejercicios
    # print("\n🔍 Obteniendo ejercicios...")
    exercises = list_exercises(access_token)

    if not isinstance(exercises, list):
        raise RuntimeError(f"Respuesta inesperada: {type(exercises)}")

    # print(f"📋 {len(exercises)} ejercicios totales")

    # Determinar rango fechas
    if args.all:
        from_d = None
        to_d = None
        _qprint("📅 Procesando TODAS las sesiones")
    elif args.auto:
        days_missing, last_date = calculate_missing_days()
        
        if days_missing == 0:
            if args.process:
                _qprint("▶️  Sin RR nuevos: actualizando sleep.csv (hoy)...")
                _refresh_sleep_and_outputs(access_token, x_user_id, run_v4lite=True)
            _print_sync_completed(updated_date=datetime.now().date(), checkmark=False)
            
            # Mostrar último daily summary
            show_latest_hrv_summaries()
            
            #print(f"\n💡 Para re-procesar: python {sys.argv[0]} --days 1 --process")
            #print("="*25 + "\n")
            return
        
        to_d = datetime.now().date()
        
        if last_date:
            # Descargar desde el día SIGUIENTE a la última medición
            from_d = last_date + timedelta(days=1)
            _qprint(f"📅 Última medición: {last_date}")
            _qprint(f"   Descargando desde {from_d} hasta {to_d}")
        else:
            # Sin CORE, descargar últimos N días
            from_d = (datetime.now() - timedelta(days=days_missing)).date()
            _qprint(f"📅 Master sin datos, descargando últimos {days_missing} días")
    elif args.days:
        to_d = datetime.now().date()
        from_d = (datetime.now() - timedelta(days=args.days)).date()
        _qprint(f"📅 Últimos {args.days} días: {from_d} → {to_d}")
    else:
        # Default: modo auto
        days_missing, last_date = calculate_missing_days()
        
        if days_missing == 0:
            if args.process:
                _qprint("▶️  Sin RR nuevos: actualizando sleep.csv (hoy)...")
                _refresh_sleep_and_outputs(access_token, x_user_id, run_v4lite=True)
            _print_sync_completed(updated_date=None, checkmark=True)
            
            # Mostrar último daily summary
            show_latest_hrv_summaries()
            
            # print(f"\n💡 Para re-procesar: python {sys.argv[0]} --days 1 --process")
            _print_divider(trailing_blank=True)
            return
        
        # Limitar a 30 días en modo auto para evitar descargas masivas
        if days_missing > MAX_AUTO_DAYS:
            print(f"⚠️  Faltan {days_missing} días (>30)")
            print(f"   Limitando a últimos 30 días")
            print(f"   Usa --all para descargar todo")
            days_missing = 30
        
        to_d = datetime.now().date()
        
        if last_date:
            # Descargar desde el día SIGUIENTE a la última medición
            from_d = last_date + timedelta(days=1)
            _qprint(f"📅 Última medición: {last_date}")
            _qprint(f"   Descargando desde {from_d} hasta {to_d} ({days_missing} días)")
        else:
            # Sin CORE, descargar últimos N días
            from_d = (datetime.now() - timedelta(days=days_missing)).date()
            _qprint(f"📅 Descargando últimos {days_missing} días (default)")

    # Debug: Mostrar deportes si --debug-sports
    if args.debug_sports:
        _print_header("🔍 DEBUG: TODAS LAS SESIONES ENCONTRADAS")
        for i, e in enumerate(exercises):
            st = _get_field_variant(e, *FIELD_START_TIME, default="N/A")
            sport = _get_field_variant(e, *FIELD_SPORT, default="N/A")
            duration = e.get("duration", "N/A")
            dt = _iso_to_dt(st)
            date_str = dt.strftime("%Y-%m-%d") if dt else "N/A"
            
            print(f"  [{i}] {date_str} | Sport: '{sport}' | Duration: {duration}")
        _print_divider(trailing_blank=True)
    
    # Aplicar filtros
    sports_set = set(SPORTS_FILTER) if SPORTS_FILTER else None
    
    filtered = []
    for e in exercises:
        if passes_filters(e, from_d, to_d, sports_set, MAX_DURATION_MINUTES):
            filtered.append(e)
        if len(filtered) >= MAX_EXERCISES:
            break

    _qprint(f"✅ {len(filtered)} sesiones tras filtros (max {MAX_EXERCISES})")

    if not filtered:
        drive_only_map: Dict = {}
        if DRIVE_RR_ENABLED:
            existing_for_drive = get_existing_dates_from_master()
            target_for_drive = _compute_target_missing_dates(from_d, to_d, existing_for_drive)
            drive_only_map, _ = _run_drive_rr_import_for_dates(
                target_for_drive,
                OUTDIR,
                verbose=args.verbose,
            )

        if drive_only_map:
            _qprint(
                f"☁️  Sin sesiones Polar filtradas, pero "
                f"{('Dropbox' if RR_CLOUD_SOURCE == 'dropbox' else 'Drive')} cubrió "
                f"{len(drive_only_map)} fecha(s). Continuando con procesamiento HRV."
            )
        else:
            if QUIET:
                print("⚠️  No hay sesiones Body&Mind en el periodo")
                _refresh_sleep_and_outputs(access_token, x_user_id, run_v4lite=args.process)
                show_latest_hrv_summaries()
                _send_intervals_wellness_from_master(INTERVALS_SOURCE_PATH)
                return
            print("\n⚠️  No hay sesiones Body&Mind en el periodo")
            
            # Mostrar debug automáticamente
            if not args.debug_sports and exercises:
                print("\n🔍 Mostrando TODAS las sesiones encontradas para debug:")
                _print_divider()
                for i, e in enumerate(exercises[:DEBUG_PREVIEW_LIMIT]):
                    st = _get_field_variant(e, *FIELD_START_TIME, default="N/A")
                    sport = _get_field_variant(e, *FIELD_SPORT, default="N/A")
                    duration = e.get("duration", "N/A")
                    dt = _iso_to_dt(st)
                    date_str = dt.strftime("%Y-%m-%d") if dt else "N/A"
                    
                    # Mostrar si pasa filtro de fecha
                    in_range = "✓" if from_d and to_d and dt and from_d <= dt.date() <= to_d else "✗"
                    
                    print(f"  [{i}] {date_str} {in_range} | Sport: '{sport}' | Duration: {duration}")
                
                if len(exercises) > 10:
                    print(f"  ... y {len(exercises) - DEBUG_PREVIEW_LIMIT} más")
                _print_divider()
                print(f"\n💡 Buscando: Sport EXACTO = '{SPORTS_FILTER[0] if SPORTS_FILTER else 'N/A'}'")
                print(f"   En rango: {from_d} a {to_d}")
                
                # DEBUG DETALLADO: Re-evaluar con debug activado
                _print_header("🔍 DEBUG DETALLADO de cada sesión en rango:", leading_blank=True)
                for i, e in enumerate(exercises[:10]):
                    st = _get_field_variant(e, *FIELD_START_TIME, default="N/A")
                    dt = _iso_to_dt(st)
                    if dt and from_d and to_d and from_d <= dt.date() <= to_d:
                        print(f"\n  Sesión [{i}] - {dt.date()}:")
                        passes_filters(e, from_d, to_d, sports_set, MAX_DURATION_MINUTES, debug=True)
                _print_divider()
            
            print(f"\n💡 No se encontraron sesiones '{SPORTS_FILTER[0] if SPORTS_FILTER else 'N/A'}' en el periodo.")
            print(f"   Usa --days N para más días o --debug-sports para ver todas las sesiones.")
            
            _refresh_sleep_and_outputs(access_token, x_user_id, run_v4lite=args.process)

            # Mostrar último daily summary disponible aunque no haya nuevos datos
            _print_header("📊 Aunque no hay nuevos datos, aquí está tu última medición:")
            show_latest_hrv_summaries()
            
            _send_intervals_wellness_from_master(INTERVALS_SOURCE_PATH)
            return

    # Export RR
    _qprint("\n📥 Descargando datos RR...")
    OUTDIR.mkdir(exist_ok=True)
    rr_cloud_label = "Dropbox" if RR_CLOUD_SOURCE == "dropbox" else "Drive"
    
    # Obtener fechas ya existentes en CORE
    existing_dates = get_existing_dates_from_master()
    pre_process_dates = set(existing_dates)
    if existing_dates and args.verbose:
        print(f"📋 {len(existing_dates)} fechas ya en CORE")
    
    exported = 0
    skipped_in_master = 0
    skipped_covered_by_drive = 0
    skipped_no_date = 0
    rr_files = []
    pending_rr_dates = set()

    target_missing_dates = _compute_target_missing_dates(from_d, to_d, existing_dates)
    drive_rr_map: Dict = {}
    drive_rr_new = 0
    if DRIVE_RR_ENABLED and target_missing_dates:
        drive_rr_map, drive_rr_new = _run_drive_rr_import_for_dates(
            target_missing_dates,
            OUTDIR,
            verbose=args.verbose,
        )
        for day, rr_path in sorted(drive_rr_map.items(), key=lambda x: x[0]):
            rr_files.append(rr_path)
            pending_rr_dates.add(day)
        if drive_rr_map:
            reused = max(len(drive_rr_map) - drive_rr_new, 0)
            _qprint(
                f"☁️  {rr_cloud_label} RR: {len(drive_rr_map)} fecha(s) cubierta(s) "
                f"({drive_rr_new} nuevas, {reused} ya existentes)"
            )

    for idx, e in enumerate(filtered):
        ex_id = e.get("id")
        if not ex_id:
            continue

        # Si ya tenemos RR (CORE o cloud JSONL) para la fecha del índice, evitar descarga de detalle.
        st_hint = _get_field_variant(e, *FIELD_START_TIME, default="")
        st_hint_dt = _iso_to_dt(st_hint)
        session_date_hint = st_hint_dt.date() if st_hint_dt else None
        if session_date_hint and session_date_hint in existing_dates:
            if args.verbose:
                print(f"  [{idx}] ⏭️  {session_date_hint} ya en CORE, omitiendo")
            skipped_in_master += 1
            continue
        if session_date_hint and session_date_hint in pending_rr_dates:
            if args.verbose:
                print(
                    f"  [{idx}] ⏭️  {session_date_hint} ya cubierto por RR {rr_cloud_label}, "
                    "omitiendo descarga Polar"
                )
            skipped_covered_by_drive += 1
            continue

        try:
            # Descargar ejercicio completo con samples
            ex_full = get_exercise_with_samples(access_token, ex_id)
        except (requests.RequestException, RuntimeError) as ex:
            print(f"  [{idx}] ❌ Error descargando: {ex}")
            continue

        # Obtener start-time del ejercicio completo
        st = _get_field_variant(ex_full, *FIELD_START_TIME, default="")
        
        if not st:
            print(f"  [{idx}] ⚠️ Sin start-time, usando del índice previo")
            # Intentar con el del listado original
            st = _get_field_variant(e, "start-time", "start_time", "startTime", default="")
        
        if not st:
            print(f"  [{idx}] ⚠️ No se puede determinar fecha/hora, usando ID")
            out_name = f"{POLAR_USER_NAME}_{UNKNOWN_SESSION_ID}_{ex_id}_RR.CSV"
            session_date = None
        else:
            st_dt = _iso_to_dt(st)
            
            if not st_dt:
                print(f"  [{idx}] ⚠️ Error parseando fecha, usando ID")
                out_name = f"{POLAR_USER_NAME}_{UNKNOWN_SESSION_ID}_{ex_id}_RR.CSV"
                session_date = None
            else:
                # Usar hora LOCAL de la sesión
                date_part = st_dt.strftime("%Y-%m-%d")
                time_part = st_dt.strftime("%H-%M-%S")
                out_name = f"{POLAR_USER_NAME}_{date_part}_{time_part}_RR.CSV"
                session_date = st_dt.date()
        
        
        if session_date is None:
            out_path = OUTDIR / out_name
            if out_path.exists():
                if args.verbose:
                    print(f"  [{idx}] ⏭️  {out_name} sin fecha, se omite procesamiento")
            else:
                rr = extract_rr_ms(ex_full)
                write_rr_csv(rr, str(out_path))
            skipped_no_date += 1
            continue

        # Verificar si fecha ya existe en CORE
        if session_date and session_date in existing_dates:
            if args.verbose:
                print(f"  [{idx}] ⏭️  {date_part} ya en CORE, omitiendo")
            skipped_in_master += 1
            continue
        if session_date and session_date in pending_rr_dates:
            if args.verbose:
                print(f"  [{idx}] ⏭️  {date_part} ya cubierto por RR {rr_cloud_label}, omitiendo Polar")
            skipped_covered_by_drive += 1
            continue

        out_path = OUTDIR / out_name

        # Si archivo existe pero fecha NO está en master, procesarlo
        if out_path.exists():
            if args.verbose:
                print(f"  [{idx}] ♻️  {out_name} existe, se procesará (no en master)")
            rr_files.append(out_path)
            pending_rr_dates.add(session_date)
            continue

        # Extraer RR
        rr = extract_rr_ms(ex_full)

        write_rr_csv(rr, str(out_path))
        rr_files.append(out_path)
        pending_rr_dates.add(session_date)
        exported += 1

        offline_pct = 100.0 * sum(1 for _, off in rr if off == 1) / max(1, len(rr))
        if args.verbose:
            print(f"  [{idx}] ✅ {out_name} | {len(rr)} RR | offline: {offline_pct:.1f}%")

    # Resumen
    _print_header("✅ EXPORT COMPLETADO")
    
    total_to_process = len(rr_files)
    existing = max(total_to_process - exported - drive_rr_new, 0)
    
    if exported > 0:
        _qprint(f"\n📥 {exported} archivos nuevos descargados")
    if drive_rr_new > 0:
        _qprint(f"☁️  {drive_rr_new} RR nuevos generados desde {rr_cloud_label}")
    
    if skipped_in_master > 0:
        _qprint(f"⏭️  {skipped_in_master} sesiones omitidas (ya en CORE)")
    if skipped_covered_by_drive > 0:
        _qprint(f"☁️  ⏭️  {skipped_covered_by_drive} sesiones omitidas (cubiertas por {rr_cloud_label})")
    if skipped_no_date > 0:
        _qprint(f"⚠️  {skipped_no_date} sesiones sin fecha (no se procesan)")
    
    if total_to_process > exported:
        _qprint(f"♻️  {existing} archivos existentes para reprocesar")
    
    _qprint(f"\n📊 {total_to_process} archivos totales para procesar en {OUTDIR}/")

    if total_to_process == 0 and skipped_in_master == 0:
        if skipped_no_date > 0:
            print("⚠️  No hay RR con fecha válida para procesar")
        else:
            _print_no_rr_files()
        _refresh_sleep_and_outputs(access_token, x_user_id, run_v4lite=args.process)
        _send_intervals_wellness_from_master(INTERVALS_SOURCE_PATH)
        show_latest_hrv_summaries()
        return
    
    if total_to_process == 0 and skipped_in_master > 0:
        _print_master_already_updated()
        _refresh_sleep_and_outputs(access_token, x_user_id, run_v4lite=args.process)
        _send_intervals_wellness_from_master(INTERVALS_SOURCE_PATH)
        show_latest_hrv_summaries()
        return

    # Procesar con endurance_hrv.py
    if args.process:
        _print_header("🔧 PROCESANDO CON ENDURANCE_HRV (V4)")

        if not Path("endurance_hrv.py").exists():
            print("")
            print("❌ endurance_hrv.py no encontrado")
            print("   Copia endurance_hrv.py al directorio actual para usar --process")
            return
        if not Path("endurance_v4lite.py").exists():
            print("")
            print("❌ endurance_v4lite.py no encontrado")
            print("   Copia endurance_v4lite.py al directorio actual para usar --process")
            return

        cmd = build_endurance_hrv_cmd(rr_files)
        if len(cmd) <= 2:
            print("")
            print("⚠️  No hay archivos RR con fecha válida para procesar")
            _refresh_sleep_and_outputs(access_token, x_user_id, run_v4lite=True)
            _send_intervals_wellness_from_master(INTERVALS_SOURCE_PATH)
            show_latest_hrv_summaries()
            return

        _qprint("")
        _qprint("▶️  Ejecutando endurance_hrv.py...")
        _qprint("")
        try:
            # Configurar environment para UTF-8
            env = os.environ.copy()
            env['PYTHONIOENCODING'] = 'utf-8'

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                encoding='utf-8',
                errors='replace',
                check=True,
                env=env
            )

            if result.stdout:
                print(result.stdout)

            post_process_dates = get_existing_dates_from_master() if PANDAS_AVAILABLE else set()
            new_dates = sorted(post_process_dates - pre_process_dates) if PANDAS_AVAILABLE else []
            if new_dates:
                merged_dates = set(new_dates)
                merged_dates.update(_default_sleep_refresh_dates())
                target_dates = sorted(merged_dates)
            else:
                target_dates = _default_sleep_refresh_dates()
            _qprint("")
            _qprint(f"▶️  Actualizando sleep.csv ({len(target_dates)} fecha(s))...")
            _update_sleep_for_dates(access_token, x_user_id, target_dates)

            _qprint("")
            _qprint("▶️  Ejecutando endurance_v4lite.py...")
            _qprint("")
            result2 = subprocess.run(
                [sys.executable, "endurance_v4lite.py"],
                capture_output=True,
                text=True,
                encoding='utf-8',
                errors='replace',
                check=True,
                env=env
            )
            if result2.stdout:
                print(result2.stdout)

            if not QUIET:
                print("")
                print("✅ Procesamiento HRV completado")
                print("")
                print("📄 Archivos actualizados:")
                print("   - ENDURANCE_HRV_master_CORE.csv")
                print("   - ENDURANCE_HRV_master_BETA_AUDIT.csv")
                print("   - ENDURANCE_HRV_master_FINAL.csv")
                print("   - ENDURANCE_HRV_master_DASHBOARD.csv")
            _send_intervals_wellness_from_master(INTERVALS_SOURCE_PATH)
            show_latest_hrv_summaries()

        except subprocess.CalledProcessError as e:
            print("")
            print(f"❌ Error ejecutando procesamiento HRV (código: {e.returncode})")
            if e.stdout:
                print("")
                print("Output:")
                print(e.stdout)
            if e.stderr:
                print("")
                print("Error:")
                print(e.stderr)
        except (FileNotFoundError, PermissionError, OSError) as e:
            print("")
            print(f"❌ Error inesperado ejecutando script: {e}")
    else:
        _send_intervals_wellness_from_master(INTERVALS_SOURCE_PATH)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nInterrumpido por el usuario.")
    except Exception as e:
        print(f"\n❌ ERROR INESPERADO: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)

