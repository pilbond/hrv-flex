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
    python polar_hrv_automation.py --process      # + ejecutar endurance_hrv.py
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
from pathlib import Path
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse, parse_qs, urlencode
from datetime import datetime, timedelta

from typing import Optional
import requests
import base64

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

_data_dir = (os.environ.get("HRV_DATA_DIR") or "").strip()
_rr_dir = (os.environ.get("RR_DOWNLOAD_DIR") or "").strip()
if _rr_dir:
    OUTDIR = Path(_rr_dir)
elif _data_dir:
    OUTDIR = Path(_data_dir) / "rr_downloads"
else:
    OUTDIR = Path("rr_downloads")

DATA_DIR = Path(_data_dir) if _data_dir else Path(".")
MASTER_PATH = DATA_DIR / "ENDURANCE_HRV_master_ALL.csv"

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

# Nombres de columnas del Master CSV (ENDURANCE_HRV_master_ALL.csv)
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

# Límites de visualización y procesamiento
DEBUG_PREVIEW_LIMIT = 10      # Sesiones a mostrar en modo debug
MAX_AUTO_DAYS = 30            # Días máximo en modo --auto
DATE_STRING_LENGTH = 10       # Longitud de "YYYY-MM-DD"
UNKNOWN_SESSION_ID = "unknown"  # ID para sesiones sin fecha

DEBUG_JSON = False  # True = guarda JSON debug de sesiones sin RR

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


def _print_header(title: str, width: int = 25, leading_blank: bool = True, trailing_blank: bool = False):
    line = "=" * width
    if leading_blank:
        print("\n" + line)
    else:
        print(line)
    print(title)
    if trailing_blank:
        print(line + "\n")
    else:
        print(line)


def _print_divider(width: int = 30, leading_blank: bool = False, trailing_blank: bool = False):
    line = "=" * width
    if leading_blank:
        print("\n" + line)
    else:
        print(line)
    if trailing_blank:
        print("")


def _print_sync_completed(updated_date=None, checkmark=False):
    print("\n✅ SINCRONIZACIÓN COMPLETADA")
    print("=" * 25)
    if updated_date:
        print(f"📊 Master CSV actualizado hasta hoy ({updated_date})")
    else:
        print("📊 Master CSV actualizado hasta hoy")
    print("💡 No nuevas sesiones")
    tail = " ✅" if checkmark else "."
    # print(f"   • Todo al día{tail}")


def _print_no_rr_files():
    print("\n⚠️  No hay archivos RR para procesar")
    print("Causas típicas:")
    print("   - Sesiones sin RR en el periodo")
    print("   - Sesiones aún no sincronizadas con Polar Flow")


def _print_master_already_updated():
    print("\n✅ Master CSV ya está actualizado con todas las sesiones")
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
    """Lee última fecha registrada en ENDURANCE_HRV_master_ALL.csv"""
    master_file = MASTER_PATH
    
    if not master_file.exists():
        return None
    
    if not PANDAS_AVAILABLE:
        print("⚠️  pandas no instalado, usa --days para especificar rango")
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
        print(f"⚠️  Error leyendo master CSV: {e}")
        return None


def get_existing_dates_from_master():
    """Obtiene set de fechas ya existentes en master CSV"""
    master_file = MASTER_PATH
    
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
        print(f"⚠️  Error leyendo fechas del master: {e}")
        return set()


def show_last_daily_summary():
    """Muestra el último daily summary del master CSV de forma destacada"""
    master_file = MASTER_PATH
    
    if not master_file.exists() or not PANDAS_AVAILABLE:
        return
    
    try:
        df = pd.read_csv(master_file)
        
        if df.empty or 'Fecha' not in df.columns:
            return
        
        # Obtener última medición
        last_row = df.sort_values('Fecha').iloc[-1]
        
        _print_header("💓 Última Medición HRV")
        
        # Formatear y mostrar - usando constantes
        fecha = last_row.get(MASTER_CSV_COLS['fecha'], 'N/A')
        hr = last_row.get(MASTER_CSV_COLS['hr'], 'N/A')
        rmssd = last_row.get(MASTER_CSV_COLS['rmssd'], 'N/A')
        crmssd = last_row.get(MASTER_CSV_COLS['crmssd'], 'N/A')
        p2 = last_row.get(MASTER_CSV_COLS['color_agudo'], 'N/A')
        calidad = last_row.get(MASTER_CSV_COLS['calidad'], 'N/A')
        stab = last_row.get(MASTER_CSV_COLS['estabilidad'], 'N/A')
        trend = last_row.get(MASTER_CSV_COLS['color_tendencia'], 'N/A')
        tiebreak = last_row.get(MASTER_CSV_COLS['color_tiebreak'], 'N/A')

        print(f"\n📅 Fecha:          {fecha}")
        print(f"💓 HR promedio:    {_format_metric(hr)} bpm")
        print(f"📊 RMSSD:          {_format_metric(rmssd)} ms")
        print(f"🎯 cRMSSD:         {_format_metric(crmssd)} ms")

        # Estado (Color_Agudo_Diario) - SOLO EMOJI DE COLOR
        p2_emoji = _get_color_emoji(p2)
        print(f"🚦 Estado:         {p2_emoji}")

        # Tendencia - SOLO EMOJI DE COLOR (NO FLECHA)
        trend_emoji = _get_color_emoji(trend)
        print(f"📈 Tendencia:      {trend_emoji}")

        # Tiebreak - SOLO EMOJI DE COLOR
        tiebreak_emoji = _get_color_emoji(tiebreak)
        print(f"🟢 Tiebreak:       {tiebreak_emoji}")

        print(f"✅ Calidad:        {calidad}")
        print(f"📈 Estabilidad:    {stab}")

        # Flags si existen
        flags = last_row.get(MASTER_CSV_COLS['flags'], '')
        if pd.notna(flags) and flags:
            print(f"🚩 Flags:          {flags}")
        
        # print("="*25)
        
    except (FileNotFoundError, pd.errors.EmptyDataError, KeyError, IndexError) as e:
        print(f"⚠️  Error mostrando último summary: {e}")


def show_last_3_days_summary():
    """Muestra resumen compacto de los últimos 3 días"""
    master_file = MASTER_PATH
    
    if not master_file.exists() or not PANDAS_AVAILABLE:
        return
    
    try:
        df = pd.read_csv(master_file)
        
        if df.empty or 'Fecha' not in df.columns:
            return
        
        # Obtener últimos 3 días
        df_sorted = df.sort_values('Fecha')
        last_3 = df_sorted.tail(3)
        
        if len(last_3) == 0:
            return
        
        _print_header("📊 RESUMEN ÚLTIMOS 3 DÍAS")
        
        for _, row in last_3.iterrows():
            fecha = row.get(MASTER_CSV_COLS['fecha'], 'N/A')
            hr = row.get(MASTER_CSV_COLS['hr'], 'N/A')
            rmssd = row.get(MASTER_CSV_COLS['rmssd'], 'N/A')
            crmssd = row.get(MASTER_CSV_COLS['crmssd'], 'N/A')
            p2 = row.get(MASTER_CSV_COLS['color_agudo'], 'N/A')
            trend = row.get(MASTER_CSV_COLS['color_tendencia'], 'N/A')
            tiebreak = row.get(MASTER_CSV_COLS['color_tiebreak'], 'N/A')

            # Formatear fecha a YY-MM-DD
            fecha_str = fecha
            if isinstance(fecha, str) and len(fecha) == DATE_STRING_LENGTH:  # YYYY-MM-DD
                fecha_str = fecha[2:]  # Quitar "20" del año → YY-MM-DD

            # Formatear métricas (sin unidad)
            hr_str = _format_metric(hr)
            rmssd_str = _format_metric(rmssd)
            crmssd_str = _format_metric(crmssd)

            # Emojis DE COLOR (no flechas)
            p2_emoji = _get_color_emoji(p2)
            trend_emoji = _get_color_emoji(trend)
            tiebreak_emoji = _get_color_emoji(tiebreak)

            # Una línea por día - SEMÁFORO + 3 COLORES
            print(f"{fecha_str} \n💓{hr_str:>5}  📊{rmssd_str:>5}  🎯{crmssd_str:>5}  {p2_emoji} {trend_emoji} {tiebreak_emoji}\n")
        
        # _print_divider()

    except (FileNotFoundError, pd.errors.EmptyDataError, KeyError, IndexError) as e:
        print(f"⚠️  Error mostrando resumen 3 días: {e}")


def calculate_missing_days():
    """Calcula cuántos días faltan desde última medición hasta hoy"""
    last_date = get_last_date_from_master()
    today = datetime.now().date()
    
    if last_date is None:
        # Sin master o sin datos, usar 7 días por defecto
        return 7, None
    
    # Calcular días faltantes
    days_missing = (today - last_date).days
    
    # Si última fecha es hoy, no hay nada que descargar
    if days_missing <= 0:
        return 0, last_date
    
    return days_missing, last_date


def update_endurance_hrv_files(rr_files):
    """Actualiza lista RR_FILES en endurance_hrv.py con archivos descargados"""
    hrv_script = Path("endurance_hrv.py")
    
    if not hrv_script.exists():
        print("⚠️  endurance_hrv.py no encontrado")
        return False
    
    # Leer script con UTF-8
    try:
        content = hrv_script.read_text(encoding='utf-8')
    except UnicodeDecodeError:
        # Intentar con latin-1 como fallback
        content = hrv_script.read_text(encoding='latin-1')
    
    # Generar nueva lista de archivos con ruta completa
    files_str = ",\n    ".join([f'Path("rr_downloads/{f.name}")' for f in rr_files])
    new_rr_files = f"""RR_FILES = [
    {files_str},
]"""
    
    # Reemplazar RR_FILES usando regex
    pattern = r'RR_FILES\s*=\s*\[[\s\S]*?\]'
    
    if not re.search(pattern, content):
        print("⚠️  No se encontró RR_FILES en endurance_hrv.py")
        return False
    
    new_content = re.sub(pattern, new_rr_files, content)
    
    # Guardar con UTF-8
    hrv_script.write_text(new_content, encoding='utf-8')
    print(f"✅ Actualizado RR_FILES con {len(rr_files)} archivos")
    
    return True


def main():
    parser = argparse.ArgumentParser(description='Polar HRV Automation')
    parser.add_argument('--auth', action='store_true', help='Forzar re-autenticación')
    parser.add_argument('--days', type=int, help='Días hacia atrás (ignora --auto)')
    parser.add_argument('--all', action='store_true', help='Todas las sesiones (ignora --days y --auto)')
    parser.add_argument('--auto', action='store_true', help='Detectar automáticamente días faltantes desde último registro')
    parser.add_argument('--process', action='store_true', help='Ejecutar endurance_hrv.py después')
    parser.add_argument('--debug-sports', action='store_true', help='Mostrar deportes de todas las sesiones encontradas')
    parser.add_argument('--verbose', action='store_true', help='Mostrar detalles de cada archivo procesado')
    args = parser.parse_args()

    _print_header("  POLAR HRV AUTOMATION")

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
        print("📅 Procesando TODAS las sesiones")
    elif args.auto:
        days_missing, last_date = calculate_missing_days()
        
        if days_missing == 0:
            _print_sync_completed(updated_date=datetime.now().date(), checkmark=False)
            
            # Mostrar último daily summary
            show_last_daily_summary()
            
            # Mostrar resumen últimos 3 días
            show_last_3_days_summary()
            
            #print(f"\n💡 Para re-procesar: python {sys.argv[0]} --days 1 --process")
            #print("="*25 + "\n")
            return
        
        to_d = datetime.now().date()
        
        if last_date:
            # Descargar desde el día SIGUIENTE a la última medición
            from_d = last_date + timedelta(days=1)
            print(f"📅 Última medición: {last_date}")
            print(f"   Descargando desde {from_d} hasta {to_d}")
        else:
            # Sin master, descargar últimos N días
            from_d = (datetime.now() - timedelta(days=days_missing)).date()
            print(f"📅 Master sin datos, descargando últimos {days_missing} días")
    elif args.days:
        to_d = datetime.now().date()
        from_d = (datetime.now() - timedelta(days=args.days)).date()
        print(f"📅 Últimos {args.days} días: {from_d} → {to_d}")
    else:
        # Default: modo auto
        days_missing, last_date = calculate_missing_days()
        
        if days_missing == 0:
            _print_sync_completed(updated_date=None, checkmark=True)
            
            # Mostrar último daily summary
            show_last_daily_summary()
            
            # Mostrar resumen últimos 3 días
            show_last_3_days_summary()
            
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
            print(f"📅 Última medición: {last_date}")
            print(f"   Descargando desde {from_d} hasta {to_d} ({days_missing} días)")
        else:
            # Sin master, descargar últimos N días
            from_d = (datetime.now() - timedelta(days=days_missing)).date()
            print(f"📅 Descargando últimos {days_missing} días (default)")

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

    print(f"✅ {len(filtered)} sesiones tras filtros (max {MAX_EXERCISES})")

    if not filtered:
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
        
        # Mostrar último daily summary disponible aunque no haya nuevos datos
        _print_header("📊 Aunque no hay nuevos datos, aquí está tu última medición:")
        show_last_daily_summary()
        
        # Mostrar resumen últimos 3 días
        show_last_3_days_summary()
        
        return

    # Export RR
    print("\n📥 Descargando datos RR...")
    OUTDIR.mkdir(exist_ok=True)
    
    # Obtener fechas ya existentes en master CSV
    existing_dates = get_existing_dates_from_master()
    if existing_dates and args.verbose:
        print(f"📋 {len(existing_dates)} fechas ya en master CSV")
    
    exported = 0
    skipped_in_master = 0
    rr_files = []

    for idx, e in enumerate(filtered):
        ex_id = e.get("id")
        if not ex_id:
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
        
        # Verificar si fecha ya existe en master CSV
        if session_date and session_date in existing_dates:
            if args.verbose:
                print(f"  [{idx}] ⏭️  {date_part} ya en master CSV, omitiendo")
            skipped_in_master += 1
            continue

        out_path = OUTDIR / out_name

        # Si archivo existe pero fecha NO está en master, procesarlo
        if out_path.exists():
            if args.verbose:
                print(f"  [{idx}] ♻️  {out_name} existe, se procesará (no en master)")
            rr_files.append(out_path)
            continue

        # Extraer RR
        rr = extract_rr_ms(ex_full)

        write_rr_csv(rr, str(out_path))
        rr_files.append(out_path)
        exported += 1

        offline_pct = 100.0 * sum(1 for _, off in rr if off == 1) / max(1, len(rr))
        if args.verbose:
            print(f"  [{idx}] ✅ {out_name} | {len(rr)} RR | offline: {offline_pct:.1f}%")

    # Resumen
    _print_header("✅ EXPORT COMPLETADO")
    
    total_to_process = len(rr_files)
    
    if exported > 0:
        print(f"\n📥 {exported} archivos nuevos descargados")
    
    if skipped_in_master > 0:
        print(f"⏭️  {skipped_in_master} sesiones omitidas (ya en master CSV)")
    
    if total_to_process > exported:
        existing = total_to_process - exported
        print(f"♻️  {existing} archivos existentes para reprocesar")
    
    print(f"\n📊 {total_to_process} archivos totales para procesar en {OUTDIR}/")

    if total_to_process == 0 and skipped_in_master == 0:
        _print_no_rr_files()
        return
    
    if total_to_process == 0 and skipped_in_master > 0:
        _print_master_already_updated()
        return

    # Procesar con endurance_hrv.py
    if args.process:
        _print_header("🔧 PROCESANDO CON ENDURANCE_HRV.PY")
        
        if not Path("endurance_hrv.py").exists():
            print("\n❌ endurance_hrv.py no encontrado")
            print("   Cópialo al directorio actual para usar --process")
            return
        
        # Actualizar RR_FILES en endurance_hrv.py
        if not update_endurance_hrv_files(rr_files):
            print("❌ Error actualizando endurance_hrv.py")
            return
        
        # Ejecutar
        print("\n▶️  Ejecutando endurance_hrv.py...\n")
        try:
            # Configurar environment para UTF-8
            env = os.environ.copy()
            env['PYTHONIOENCODING'] = 'utf-8'
            
            result = subprocess.run(
                [sys.executable, "endurance_hrv.py"],
                capture_output=True,
                text=True,
                encoding='utf-8',
                errors='replace',
                check=True,
                env=env
            )
            
            # Mostrar output
            if result.stdout:
                print(result.stdout)
            
            print("\n✅ Procesamiento HRV completado")
            print("\n📄 Archivos actualizados:")
            print("   - ENDURANCE_HRV_master_ALL.csv")
            print("   - ENDURANCE_HRV_eval_P1P2_ALL.csv")
            
        except subprocess.CalledProcessError as e:
            print(f"\n❌ Error ejecutando endurance_hrv.py (código: {e.returncode})")
            if e.stdout:
                print("\nOutput:")
                print(e.stdout)
            if e.stderr:
                print("\nError:")
                print(e.stderr)
        except (FileNotFoundError, PermissionError, OSError) as e:
            print(f"\n❌ Error inesperado ejecutando script: {e}")


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
