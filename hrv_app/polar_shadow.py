from __future__ import annotations

"""
AYO-13 Fase 3: lecturas shadow Polar v4 + sidecar de auditoria (AYO-19).

Bajo `POLAR_API_VERSION=shadow`, al final de `--process` se hace una lectura
de solo-lectura contra la API v4 (sleeps, nightly-recharge, training-sessions)
para las mismas fechas que `_default_sleep_refresh_dates()` y se compara con
lo que v3 ya persistio en ENDURANCE_HRV_sleep.csv (sleep/nightly) y
ENDURANCE_HRV_master_CORE.csv (sessions).

No reconsulta v3, no escribe ningun CSV operativo y nunca bloquea
`--process`: cualquier fallo queda registrado como `status` en el sidecar
JSONL (`data/audit/polar_v4_shadow.jsonl`, append-only) y la excepcion se
captura en el punto de entrada `run_polar_v4_shadow`.
"""

import json
import time
from datetime import date as _date_type
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

from . import config
from . import polar_auth_v4 as auth_v4
from .hrv_sync_flow import extract_rr_ms
from .polar_adapters_v4 import (
    index_by_date,
    v4_nightly_to_internal,
    v4_session_to_internal,
    v4_sleep_to_internal,
)
from .polar_client_v4 import PolarV4Error, V4Client
from .sleep_store import SLEEP_COLUMNS, _extract_nightly_fields, _extract_sleep_fields

SHADOW_PATH = config.DATA_DIR / "audit" / "polar_v4_shadow.jsonl"

# Sentinel para distinguir "el caller no pasa v3_row" de "el caller pasa
# explicitamente None porque la fecha no tiene fila en el CSV". Sin esto,
# el cache por-fecha de run_shadow_for_dates es inutil para fechas sin v3.
_UNSET = object()

# Sin `features` las respuestas v4 solo traen fechas (ver polar_client_v4).
SLEEP_FEATURES = ["sleep-result", "sleep-score", "sleep-evaluation"]
NIGHTLY_FEATURES = ["samples"]
SESSION_FEATURES = ["samples"]


def _next_day_iso(date_str: str) -> str:
    """Rango de query [day, day+1). Para training-sessions/list la promocion a
    datetime hace que from=to=mismo-dia sea una ventana de 0 segundos; para
    sleep/nightly es la unica forma validada en la captura F0. Los consumidores
    filtran por index_by_date/date_str, asi que un rango que devuelva dos dias
    es inocuo."""
    try:
        return (_date_type.fromisoformat(date_str) + timedelta(days=1)).isoformat()
    except ValueError:
        return date_str


def _bundle_obtained_at(bundle_path: Path) -> Optional[Any]:
    bundle = auth_v4.load_bundle_v4(bundle_path)
    return bundle.get("obtained_at") if bundle else None


def _round(value: Any, ndigits: int = 2) -> Any:
    try:
        f = float(value)
    except (TypeError, ValueError):
        return value
    if f != f:  # NaN
        return None
    return round(f, ndigits)


def _diff_fields(v3_row: Optional[dict], v4_fields: dict, ndigits: int = 2) -> dict:
    diff: dict[str, dict] = {}
    for key, v4_val in v4_fields.items():
        v3_val = v3_row.get(key) if v3_row else None
        v3r = _round(v3_val, ndigits)
        v4r = _round(v4_val, ndigits)
        if v3r != v4r:
            diff[key] = {"v3": v3r, "v4": v4r}
    return diff


def _v3_sleep_row(date_str: str) -> Optional[dict]:
    if not config.PANDAS_AVAILABLE or not config.SLEEP_PATH.exists():
        return None
    import pandas as pd

    try:
        df = pd.read_csv(config.SLEEP_PATH)
    except (FileNotFoundError, pd.errors.EmptyDataError, OSError, ValueError):
        return None
    if "Fecha" not in df.columns:
        return None
    match = df[df["Fecha"].astype(str) == date_str]
    if match.empty:
        return None
    return match.iloc[0].to_dict()


def _v3_sleep_present(v3_row: Optional[dict]) -> bool:
    if not v3_row:
        return False
    return any(_round(v3_row.get(c)) is not None for c in SLEEP_COLUMNS if c != "Fecha")


def _v3_core_has_date(date_str: str) -> Optional[bool]:
    if not config.PANDAS_AVAILABLE or not config.CORE_PATH.exists():
        return None
    import pandas as pd

    try:
        df = pd.read_csv(config.CORE_PATH)
    except (FileNotFoundError, pd.errors.EmptyDataError, OSError, ValueError):
        return None
    if "Fecha" not in df.columns:
        return None
    return date_str in set(df["Fecha"].astype(str))


def _call_v4(bundle_path: Path, fn, *args, **kwargs) -> dict:
    """Ejecuta `fn` v4 midiendo latencia/refresh y devuelve un dict con
    `status` ("ok"|"error"), `payload`, `error`, `latency_ms`, `refreshed`."""
    before = _bundle_obtained_at(bundle_path)
    t0 = time.monotonic()
    try:
        payload = fn(*args, **kwargs)
        status, error = "ok", None
    except PolarV4Error as exc:
        payload, status, error = None, "error", str(exc)
    latency_ms = round((time.monotonic() - t0) * 1000.0, 1)
    after = _bundle_obtained_at(bundle_path)
    return {
        "status": status,
        "payload": payload,
        "error": error,
        "latency_ms": latency_ms,
        "refreshed": before != after,
    }


def _shadow_sleep(client: V4Client, bundle_path: Path, date_str: str,
                   v3_row: Any = _UNSET) -> dict:
    if v3_row is _UNSET:
        v3_row = _v3_sleep_row(date_str)
    v3_present = _v3_sleep_present(v3_row)

    if auth_v4.load_bundle_v4(bundle_path) is None:
        return {"status": "no_token", "v3_present": v3_present}

    # [day, day+1): unica forma de query validada en la captura F0 (pasada con
    # features). from=to=mismo-dia es no probada y devolveria vacio si la API
    # trata `to` como exclusivo. index_by_date().get(date_str) selecciona el
    # dia correcto aunque el rango devuelva dos.
    result = _call_v4(bundle_path, client.fetch_sleeps, date_str, _next_day_iso(date_str),
                      features=SLEEP_FEATURES)
    out = {
        "status": result["status"],
        "latency_ms": result["latency_ms"],
        "refreshed": result["refreshed"],
        "v3_present": v3_present,
    }
    if result["status"] != "ok":
        out["error"] = result["error"]
        return out

    item = index_by_date(result["payload"] or []).get(date_str)
    internal = v4_sleep_to_internal(item)
    v4_fields = _extract_sleep_fields(internal) if internal else {}
    out["v4_present"] = bool(v4_fields)
    out["diff"] = _diff_fields(v3_row, v4_fields)
    return out


def _shadow_nightly(client: V4Client, bundle_path: Path, date_str: str,
                     v3_row: Any = _UNSET) -> dict:
    if v3_row is _UNSET:
        v3_row = _v3_sleep_row(date_str)
    v3_present = v3_row is not None and any(
        _round(v3_row.get(c)) is not None
        for c in ("polar_night_rmssd", "polar_night_rri", "polar_night_resp")
    )

    if auth_v4.load_bundle_v4(bundle_path) is None:
        return {"status": "no_token", "v3_present": v3_present}

    # [day, day+1) como sleep: forma validada en F0; index_by_date selecciona
    # el dia correcto.
    result = _call_v4(bundle_path, client.fetch_nightly_recharges, date_str, _next_day_iso(date_str),
                      features=NIGHTLY_FEATURES)
    out = {
        "status": result["status"],
        "latency_ms": result["latency_ms"],
        "refreshed": result["refreshed"],
        "v3_present": v3_present,
    }
    if result["status"] != "ok":
        out["error"] = result["error"]
        return out

    item = index_by_date(result["payload"] or []).get(date_str)
    internal = v4_nightly_to_internal(item)
    v4_fields = _extract_nightly_fields(internal) if internal else {}
    out["v4_present"] = bool(v4_fields)
    out["diff"] = _diff_fields(v3_row, v4_fields)
    return out


def _shadow_sessions(client: V4Client, bundle_path: Path, date_str: str) -> dict:
    v3_present = _v3_core_has_date(date_str)

    if auth_v4.load_bundle_v4(bundle_path) is None:
        return {"status": "no_token", "v3_present": v3_present}

    result = _call_v4(
        bundle_path, client.list_training_sessions, date_str, _next_day_iso(date_str),
        features=SESSION_FEATURES,
    )
    out = {
        "status": result["status"],
        "latency_ms": result["latency_ms"],
        "refreshed": result["refreshed"],
        "v3_present": v3_present,
    }
    if result["status"] != "ok":
        out["error"] = result["error"]
        return out

    items = result["payload"] or []
    rr_counts = []
    for item in items:
        internal = v4_session_to_internal(item)
        if not internal:
            continue
        rr = extract_rr_ms(internal)
        if rr:
            rr_counts.append(len(rr))
    out["v4_present"] = bool(rr_counts)
    out["v4_session_count"] = len(items)
    out["v4_rr_counts"] = rr_counts
    return out


def _append_jsonl(records: list[dict]) -> None:
    if not records:
        return
    SHADOW_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(SHADOW_PATH, "a", encoding="utf-8") as f:
        for rec in records:
            f.write(json.dumps(rec, ensure_ascii=False, default=str))
            f.write("\n")


def run_shadow_for_dates(dates: list, bundle_path: Optional[Path] = None) -> list[dict]:
    bundle_path = Path(bundle_path) if bundle_path is not None else config.TOKEN_FILE_V4
    client = V4Client(bundle_path=bundle_path)

    # Persistencia por-fecha: si una iteracion lanza una excepcion no-PolarV4Error
    # (red en auth.refresh, pandas con el CSV corrupto, etc.) el catchall de
    # run_polar_v4_shadow la come pero los registros ya completados deben quedar
    # en disco — perderlos eliminaria la utilidad del shadow.
    records = []
    for d in dates:
        date_str = d.isoformat() if hasattr(d, "isoformat") else str(d)
        v3_row = _v3_sleep_row(date_str)
        record = {
            "date": date_str,
            "captured_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "domains": {
                "sleep": _shadow_sleep(client, bundle_path, date_str, v3_row=v3_row),
                "nightly": _shadow_nightly(client, bundle_path, date_str, v3_row=v3_row),
                "sessions": _shadow_sessions(client, bundle_path, date_str),
            },
        }
        records.append(record)
        _append_jsonl([record])

    return records


def run_polar_v4_shadow(dates: Optional[list] = None) -> list[dict]:
    """Punto de entrada del hook `--process`. No-op si `POLAR_API_VERSION`
    no es `shadow`. Cualquier excepcion se captura: el shadow nunca debe
    romper el sync principal."""
    if config.POLAR_API_VERSION != "shadow":
        return []

    if dates is None:
        from .sleep_store import _default_sleep_refresh_dates

        dates = _default_sleep_refresh_dates()

    try:
        return run_shadow_for_dates(dates)
    except Exception as exc:  # noqa: BLE001 - shadow nunca bloquea --process
        print(f"⚠️  Shadow Polar v4 falló: {exc}")
        return []
