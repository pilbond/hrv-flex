from __future__ import annotations

import os
import tempfile
from pathlib import Path

from .polar_utils import env_flag


def _load_local_env() -> None:
    if IS_PRODUCTION:
        return
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    load_dotenv()


def _env_int(name: str, default: int) -> int:
    raw = (os.environ.get(name) or "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _dir_is_writable(path: Path) -> bool:
    try:
        path.mkdir(parents=True, exist_ok=True)
    except OSError:
        return False
    try:
        with tempfile.NamedTemporaryFile(dir=str(path), prefix=".hrv-write-probe-", delete=True):
            pass
        return True
    except OSError:
        return False


def _resolve_writable_dir(primary: Path, fallback: Path) -> Path:
    for candidate in (primary, fallback):
        if _dir_is_writable(candidate):
            return candidate
    return primary


def _resolve_writable_file(primary: Path, fallback_dir: Path) -> Path:
    candidates = [primary]
    fallback_file = fallback_dir / primary.name
    if fallback_file != primary:
        candidates.append(fallback_file)

    for candidate in candidates:
        if _dir_is_writable(candidate.parent):
            return candidate
    return primary


def resolve_writable_dir(primary: Path, fallback: Path) -> Path:
    return _resolve_writable_dir(primary, fallback)


def resolve_writable_file(primary: Path, fallback_dir: Path) -> Path:
    return _resolve_writable_file(primary, fallback_dir)


IS_RAILWAY = os.environ.get("RAILWAY_ENVIRONMENT") is not None
IS_RENDER = os.environ.get("RENDER") is not None
IS_HEROKU = os.environ.get("DYNO") is not None
IS_PRODUCTION = IS_RAILWAY or IS_RENDER or IS_HEROKU

_load_local_env()

PANDAS_AVAILABLE = False
try:
    import pandas as pd  # noqa: F401
except ImportError:
    pass
else:
    PANDAS_AVAILABLE = True

QUIET = env_flag("HRV_QUIET", False)


def _qprint(*args, **kwargs):
    if not QUIET:
        print(*args, **kwargs)


CLIENT_ID = (
    os.environ.get("POLAR_CLIENT_ID2")
    or os.environ.get("POLAR_CLIENT_ID")
)
CLIENT_SECRET = os.environ.get("POLAR_CLIENT_SECRET")
POLAR_USER_NAME = os.environ.get("POLAR_USER_NAME") or "Polar_User"

SCOPE = "accesslink.read_all"
API_BASE = "https://www.polaraccesslink.com/v3"
AUTH_URL = "https://flow.polar.com/oauth2/authorization"
TOKEN_URL = "https://polarremote.com/v2/oauth2/token"


def get_production_url():
    public_url = os.environ.get("PUBLIC_URL") or os.environ.get("RAILWAY_PUBLIC_DOMAIN") or ""
    if public_url and not str(public_url).startswith("http"):
        return f"https://{public_url}"
    return public_url


PUBLIC_URL = get_production_url()


def _build_redirect_uri() -> str:
    if IS_PRODUCTION:
        if PUBLIC_URL:
            return f"{PUBLIC_URL}/auth/callback"
        if IS_RAILWAY:
            service_name = os.environ.get("RAILWAY_SERVICE_NAME", "app")
            return f"https://{service_name}.up.railway.app/auth/callback"
    return "http://localhost:5050/oauth2/callback"


REDIRECT_URI = _build_redirect_uri()

_data_dir = (os.environ.get("HRV_DATA_DIR") or "data").strip() or "data"
_data_dir_path = Path(_data_dir)
DATA_DIR = _resolve_writable_dir(_data_dir_path, Path.cwd() / _data_dir_path.name)
_rr_dir = (os.environ.get("RR_DOWNLOAD_DIR") or "").strip()
if _rr_dir:
    OUTDIR = _resolve_writable_dir(Path(_rr_dir), DATA_DIR / "rr_downloads")
else:
    OUTDIR = DATA_DIR / "rr_downloads"

TOKEN_FILE = _resolve_writable_file(
    Path(os.environ.get("POLAR_TOKEN_PATH", ".polar_tokens.json")),
    DATA_DIR,
)

# --- Polar Dynamic API v4 (AYO-13): dual stack bajo feature flag ---
# v3: runtime actual (default). v4: lecturas Polar vía Dynamic API v4.
# shadow: v3 efectivo + lectura paralela v4 solo para auditoría.
_raw_polar_api_version = (os.environ.get("POLAR_API_VERSION") or "v3").strip().lower()
if _raw_polar_api_version not in ("v3", "v4", "shadow"):
    _qprint(f"AVISO: POLAR_API_VERSION invalida ({_raw_polar_api_version!r}); se usa v3")
    _raw_polar_api_version = "v3"
POLAR_API_VERSION = _raw_polar_api_version

POLAR_V4_SCOPES = (
    os.environ.get("POLAR_V4_SCOPES")
    or "sleep:read nightly_recharge:read training_sessions:read sports:read"
).strip()

# Bundle v4 en archivo separado del v3: rollback = flip de env var sin
# migración de datos. Misma app/credenciales que v3 (admin.polaraccesslink.com).
TOKEN_FILE_V4 = _resolve_writable_file(
    Path(os.environ.get("POLAR_TOKEN_PATH_V4", ".polar_tokens_v4.json")),
    DATA_DIR,
)
CORE_PATH = DATA_DIR / "ENDURANCE_HRV_master_CORE.csv"
BETA_AUDIT_PATH = DATA_DIR / "ENDURANCE_HRV_master_BETA_AUDIT.csv"
FINAL_PATH = DATA_DIR / "ENDURANCE_HRV_master_FINAL.csv"
DASHBOARD_PATH = DATA_DIR / "ENDURANCE_HRV_master_DASHBOARD.csv"
SSM_SHADOW_PATH = DATA_DIR / "ENDURANCE_HRV_ssm_shadow.csv"
SSM_SHADOW_METADATA_PATH = DATA_DIR / "ENDURANCE_HRV_ssm_shadow_metadata.json"
SSM_VALIDATION_REPORT_JSON_PATH = DATA_DIR / "ENDURANCE_HRV_ssm_validation_report.json"
SSM_VALIDATION_REPORT_MD_PATH = DATA_DIR / "ENDURANCE_HRV_ssm_validation_report.md"
SSM_OUTCOME_BATTERY_JSON_PATH = DATA_DIR / "ENDURANCE_HRV_ssm_outcome_battery.json"
SSM_OUTCOME_BATTERY_MD_PATH = DATA_DIR / "ENDURANCE_HRV_ssm_outcome_battery.md"
SLEEP_PATH = DATA_DIR / "ENDURANCE_HRV_sleep.csv"

INTERVALS_SOURCE_PATH = BETA_AUDIT_PATH
INTERVALS_BASE_URL = (os.environ.get("INTERVALS_BASE_URL") or "https://intervals.icu").strip()

# Dos masas distintas con roles distintos:
# - SYSTEM_BIKE_WEIGHT_KG: masa total para el modelo físico de potencia
#   (atleta + bicicleta + bidón + ropa/calzado). Determina los vatios estimados.
# - ATHLETE_WEIGHT_KG: masa corporal del atleta, denominador de W/kg.
#   Convención estándar del sector (Strava, TrainingPeaks, WKO): W/kg usa
#   solo la masa corporal, independientemente del equipo. Los vatios reflejan
#   el esfuerzo para mover el sistema completo; W/kg atleta es el índice de
#   rendimiento relativo a la masa corporal.
ATHLETE_WEIGHT_KG     = float(os.environ.get("ATHLETE_WEIGHT_KG",     "68.0"))
SYSTEM_BIKE_WEIGHT_KG = float(os.environ.get("SYSTEM_BIKE_WEIGHT_KG", "80.0"))

SPORTS_FILTER = ["BODY_AND_MIND"]
MAX_DURATION_MINUTES = 10
MAX_EXERCISES = 50

RR_MIN_MS = 300.0
RR_MAX_MS = 2000.0

FIELD_START_TIME = ("start-time", "start_time", "startTime")
FIELD_SPORT = ("detailed-sport-info", "detailed_sport_info", "sport")
FIELD_SAMPLE_TYPE = ("sample-type", "sample_type")

MASTER_CSV_COLS = {
    "fecha": "Fecha",
    "hr": "HR_stable",
    "rmssd": "RMSSD_stable",
    "crmssd": "cRMSSD",
    "color_agudo": "Color_Agudo_Diario",
    "color_tendencia": "Color_Tendencia",
    "color_tiebreak": "Color_Tiebreak",
    "calidad": "Calidad",
    "estabilidad": "HRV_Stability",
    "flags": "Flags",
}

INTERVALS_FIELD_MAP = {
    "CRMSSD": "cRMSSD",
    "HRPolar": "HR_stable",
    "HRVScore": "RMSSD_stable",
    "ColorDiario": "Color_Agudo_Diario",
    "ColorTiebreak": "Color_Tiebreak",
    "ColorTendencia": "Color_Tendencia",
}

COLOR_EMOJI = {
    "Verde": "🟢",
    "Amarillo": "🟡",
    "Ámbar": "🟡",
    "Rojo": "🔴",
    "N/A": "⚪",
}

GATE_EMOJI = {
    "VERDE": "🟢",
    "ÁMBAR": "🟡",
    "AMBAR": "🟡",
    "ROJO": "🔴",
    "NO": "⚪",
}

DEBUG_PREVIEW_LIMIT = 10
MAX_AUTO_DAYS = 30
DATE_STRING_LENGTH = 10
UNKNOWN_SESSION_ID = "unknown"
DEBUG_JSON = False

# Sesiones Polar via Dynamic API v4 (F5.2); requiere POLAR_API_VERSION=v4.
# Default off: el backend v3 de PolarSessionClient es el activo hasta que se valide.
# Rollback = POLAR_V4_SESSIONS=0 (o unset).
POLAR_V4_SESSIONS = env_flag("POLAR_V4_SESSIONS", False)

DROPBOX_RR_ENABLED = env_flag("HRV_DROPBOX_RR_ENABLED", True)
DROPBOX_RR_SCRIPT = (os.environ.get("HRV_DROPBOX_RR_SCRIPT") or "egc_to_rr.py").strip() or "egc_to_rr.py"
DROPBOX_RR_NO_AUX = env_flag("HRV_DROPBOX_NO_AUX", True)
DROPBOX_RR_PAIR_LIMIT = (os.environ.get("HRV_DROPBOX_PAIR_LIMIT") or "").strip()
DROPBOX_RR_TIMEOUT_SEC = _env_int("HRV_DROPBOX_RR_TIMEOUT_SEC", 900)
DROPBOX_FOLDER_PATH = (
    os.environ.get("HRV_DROPBOX_FOLDER_PATH")
    or os.environ.get("DROPBOX_FOLDER_PATH")
    or ""
).strip()
DROPBOX_RECURSIVE = env_flag("HRV_DROPBOX_RECURSIVE", True)
