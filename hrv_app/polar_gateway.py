from __future__ import annotations

"""
AYO-13 Fase 5.1: gateway minimo de sleep/nightly, dispatch por
POLAR_API_VERSION.

- "v3" y "shadow": delega 1:1 en polar_client (sin cambio de comportamiento;
  shadow sigue siendo "v3 efectivo + auditoria v4 en paralelo").
- "v4": resuelve el bearer token v4 via polar_auth_v4.get_valid_access_token,
  consulta V4Client.fetch_sleeps/fetch_nightly_recharges en la ventana
  [dia, dia+1) con features (misma forma validada por el shadow F3) y adapta
  al shape interno v3 que consumen sleep_store._extract_sleep_fields /
  _extract_nightly_fields.

En modo v4 el `token`/`user_id` recibidos por firma se ignoran: los
endpoints v4 estan asociados al bearer token, no a un user_id. Si no hay
bundle v4 utilizable o la consulta falla, se devuelve None (sleep_store ya
trata None como "no se escribe fila"; la ausencia de sleep no rompe
--process).
"""

from typing import Optional

from . import config
from . import polar_auth_v4 as auth_v4
from . import polar_client
from .polar_adapters_v4 import (
    NIGHTLY_FEATURES,
    SLEEP_FEATURES,
    index_by_date,
    next_day_iso,
    v4_nightly_to_internal,
    v4_sleep_to_internal,
)
from .polar_client_v4 import PolarV4Error, V4Client

# V4Client reutilizado entre llamadas dentro del proceso: su throttle local
# (self._last_request_ts) solo limita peticiones consecutivas si la instancia
# persiste entre fetch_polar_sleep/fetch_polar_nightly_recharge.
_shared_v4_client: Optional[V4Client] = None
_missing_bundle_warned = False


def _v4_client() -> Optional[V4Client]:
    global _shared_v4_client, _missing_bundle_warned
    if auth_v4.load_bundle_v4(config.TOKEN_FILE_V4) is None:
        _shared_v4_client = None
        return None
    if _shared_v4_client is None or _shared_v4_client.bundle_path != config.TOKEN_FILE_V4:
        _shared_v4_client = V4Client(bundle_path=config.TOKEN_FILE_V4)
    _missing_bundle_warned = False
    return _shared_v4_client


def _warn_missing_bundle(date_str: str, kind: str) -> None:
    global _missing_bundle_warned
    if _missing_bundle_warned:
        return
    _missing_bundle_warned = True
    print(
        f"⚠️ Sin bundle v4 utilizable: se omiten lecturas {kind} v4. "
        f"Autoriza vía /auth?provider=v4 (primer día afectado: {date_str})."
    )


def fetch_polar_sleep(token: str, user_id: Optional[str], date_str: str) -> Optional[dict]:
    """Sleep para `date_str` en el shape interno v3 (ver modulo)."""
    if config.POLAR_API_VERSION != "v4":
        return polar_client.fetch_polar_sleep(token, user_id, date_str)

    client = _v4_client()
    if client is None:
        _warn_missing_bundle(date_str, "sleep")
        return None
    try:
        items = client.fetch_sleeps(date_str, next_day_iso(date_str), features=SLEEP_FEATURES)
    except PolarV4Error as exc:
        print(f"⚠️ Sleep v4 fetch failed for {date_str}: {exc}")
        return None
    return v4_sleep_to_internal(index_by_date(items).get(date_str))


def fetch_polar_nightly_recharge(token: str, user_id: Optional[str], date_str: str) -> Optional[dict]:
    """Nightly recharge para `date_str` en el shape interno v3 (ver modulo)."""
    if config.POLAR_API_VERSION != "v4":
        return polar_client.fetch_polar_nightly_recharge(token, user_id, date_str)

    client = _v4_client()
    if client is None:
        _warn_missing_bundle(date_str, "sleep/nightly")
        return None
    try:
        items = client.fetch_nightly_recharges(date_str, next_day_iso(date_str), features=NIGHTLY_FEATURES)
    except PolarV4Error as exc:
        print(f"⚠️ Nightly v4 fetch failed for {date_str}: {exc}")
        return None
    return v4_nightly_to_internal(index_by_date(items).get(date_str))
