from __future__ import annotations

"""Gateway de sleep/nightly Polar usando v4 como único transporte (AYO-22)."""

from threading import RLock
import logging
from typing import Optional

from . import config
from . import polar_auth_v4 as auth_v4
from .polar_adapters_v4 import (
    NIGHTLY_FEATURES,
    SLEEP_FEATURES,
    index_by_date,
    next_day_iso,
    v4_nightly_to_internal,
    v4_sleep_to_internal,
)
from .polar_client_v4 import PolarV4Error, V4Client

log = logging.getLogger(__name__)

_shared_v4_client: Optional[V4Client] = None
_missing_bundle_warned = False
_gateway_lock = RLock()
def _v4_client() -> Optional[V4Client]:
    global _shared_v4_client, _missing_bundle_warned
    if auth_v4.load_bundle_v4(config.TOKEN_FILE_V4) is None:
        with _gateway_lock:
            _shared_v4_client = None
        return None
    with _gateway_lock:
        if _shared_v4_client is None or _shared_v4_client.bundle_path != config.TOKEN_FILE_V4:
            _shared_v4_client = V4Client(bundle_path=config.TOKEN_FILE_V4)
        _missing_bundle_warned = False
        return _shared_v4_client


def _warn_missing_bundle(date_str: str, kind: str) -> None:
    global _missing_bundle_warned
    with _gateway_lock:
        if _missing_bundle_warned:
            return
        _missing_bundle_warned = True
    log.warning(
        f"⚠️ Sin bundle v4 utilizable: se omiten lecturas {kind} v4. "
        f"Autoriza vía /auth (primer día afectado: {date_str})."
    )


def fetch_polar_sleep_result(token: str, user_id: Optional[str], date_str: str) -> dict:
    """Sleep v4 adaptado, con el resultado de transporte en la propia llamada."""
    client = _v4_client()
    if client is None:
        _warn_missing_bundle(date_str, "sleep")
        return {"outcome": "request_error", "data": None}
    try:
        items = client.fetch_sleeps(date_str, next_day_iso(date_str), features=SLEEP_FEATURES)
    except PolarV4Error as exc:
        log.warning("Sleep v4 fetch failed for %s: %s", date_str, exc)
        return {"outcome": "request_error", "data": None}
    result = v4_sleep_to_internal(index_by_date(items).get(date_str))
    return {"outcome": "data_found" if result else "no_data_yet", "data": result}


def fetch_polar_nightly_recharge_result(token: str, user_id: Optional[str], date_str: str) -> dict:
    """Nightly recharge v4 adaptado, con el resultado de transporte propio."""
    client = _v4_client()
    if client is None:
        _warn_missing_bundle(date_str, "sleep/nightly")
        return {"outcome": "request_error", "data": None}
    try:
        items = client.fetch_nightly_recharges(date_str, next_day_iso(date_str), features=NIGHTLY_FEATURES)
    except PolarV4Error as exc:
        log.warning("Nightly v4 fetch failed for %s: %s", date_str, exc)
        return {"outcome": "request_error", "data": None}
    result = v4_nightly_to_internal(index_by_date(items).get(date_str))
    return {"outcome": "data_found" if result else "no_data_yet", "data": result}
