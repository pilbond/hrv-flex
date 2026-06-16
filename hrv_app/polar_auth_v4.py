from __future__ import annotations

"""
OAuth para Polar Dynamic API v4 (AYO-13).

v4 usa endpoints OAuth propios (auth.polar.com), access token de ~12h y
refresh token obligatorio. El bundle v4 se persiste en un archivo separado
del bundle v3 (TOKEN_FILE_V4) para que el rollback sea un flip de env var
sin migración de datos.

Reglas:
- Un access token expirado NO es inválido: se renueva con el refresh token.
- access y refresh token se rotan y guardan juntos de forma atómica.
- Los tokens nunca se incluyen en logs, errores ni payloads HTTP (usar
  redact() para diagnósticos).
"""

import json
import os
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urlencode

import requests

from .oauth_utils import build_basic_auth_header, save_json_atomic

AUTH_URL_V4 = "https://auth.polar.com/oauth/authorize"
TOKEN_URL_V4 = "https://auth.polar.com/oauth/token"

# Margen antes de la expiración a partir del cual se refresca proactivamente.
# Con TTL ~12h y sync diario, el refresh es el camino caliente, no la excepción.
REFRESH_SKEW_SEC = 120.0

# Serializa refresh dentro del proceso. Entre procesos se usa además un
# lockfile O_CREAT|O_EXCL (ver `_file_lock`) porque los refresh tokens rotan
# y un segundo proceso podría usar uno ya invalidado.
_REFRESH_LOCK = threading.Lock()

_FILE_LOCK_TIMEOUT_SEC = 30.0
_FILE_LOCK_STALE_SEC = 60.0


@contextmanager
def _file_lock(bundle_path: Path, timeout: Optional[float] = None):
    """Lock entre procesos basado en lockfile O_CREAT|O_EXCL portable.

    No requiere fcntl/msvcrt: el create-exclusivo es atómico en POSIX y NTFS.
    Si el lock es más viejo que `_FILE_LOCK_STALE_SEC` se considera huérfano
    de un proceso caído y se rompe. Si no se adquiere en `timeout` segundos,
    se cede (el caller degrada a None)."""
    lock_path = Path(str(bundle_path) + ".lock")
    # Resuelto en runtime (no como default de la firma) para que los tests
    # puedan parchear la constante del módulo.
    if timeout is None:
        timeout = _FILE_LOCK_TIMEOUT_SEC
    deadline = time.time() + timeout
    acquired = False
    while True:
        try:
            fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            try:
                os.write(fd, str(time.time()).encode("ascii"))
            finally:
                os.close(fd)
            acquired = True
            break
        except FileExistsError:
            try:
                age = time.time() - lock_path.stat().st_mtime
            except FileNotFoundError:
                continue
            if age > _FILE_LOCK_STALE_SEC:
                try:
                    lock_path.unlink()
                except FileNotFoundError:
                    pass
                continue
            if time.time() >= deadline:
                break
            time.sleep(0.1)
    try:
        yield acquired
    finally:
        if acquired:
            try:
                lock_path.unlink()
            except FileNotFoundError:
                pass


class PolarAuthV4Error(RuntimeError):
    """Error OAuth v4. El mensaje nunca contiene tokens."""


def build_auth_url_v4(client_id: str, redirect_uri: str, scopes: str, state: Optional[str] = None) -> str:
    params = {
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "scope": scopes,
    }
    if state:
        params["state"] = state
    return f"{AUTH_URL_V4}?{urlencode(params)}"


def _token_request(data: dict, client_id: str, client_secret: str, timeout: int) -> dict[str, Any]:
    headers = {
        "Authorization": build_basic_auth_header(client_id, client_secret),
        "Content-Type": "application/x-www-form-urlencoded",
        "Accept": "application/json;charset=UTF-8",
    }
    r = requests.post(TOKEN_URL_V4, headers=headers, data=data, timeout=timeout)
    if r.status_code >= 400:
        # No se incluye el body bruto: un proxy o error inesperado podría
        # reflejar credenciales. Solo los campos de error OAuth estándar.
        detail = ""
        try:
            err = r.json()
            if isinstance(err, dict):
                detail = " | " + " ".join(
                    str(err[k]) for k in ("error", "error_description") if err.get(k)
                )
        except ValueError:
            pass
        raise PolarAuthV4Error(
            f"Token request v4 falló ({data.get('grant_type')}): {r.status_code} {r.reason}{detail}"
        )
    try:
        payload = r.json()
    except ValueError as exc:
        raise PolarAuthV4Error(
            f"Token request v4 ({data.get('grant_type')}): respuesta 2xx con JSON inválido"
        ) from exc
    # Un 2xx sin access_token no es un grant: persistirlo dejaría un bundle
    # vacío y el callback reportaría éxito sin credenciales.
    if not isinstance(payload, dict) or not payload.get("access_token"):
        raise PolarAuthV4Error(
            f"Token request v4 ({data.get('grant_type')}): respuesta 2xx sin access_token"
        )
    # En authorization_code el refresh_token es obligatorio en v4: sin él el
    # bundle moriría en silencio al expirar el access token (~12h) y el
    # callback habría reportado éxito. Mejor fallar tipado aquí y que el
    # usuario reintente /auth. En refresh la omisión es legítima (rotación
    # que conserva el refresh token previo).
    if data.get("grant_type") == "authorization_code" and not payload.get("refresh_token"):
        raise PolarAuthV4Error(
            "Token request v4 (authorization_code): respuesta sin refresh_token; "
            "v4 lo exige para renovar sin re-auth. Bundle no persistido, reintenta /auth."
        )
    return payload


def exchange_code_for_token_v4(
    code: str,
    client_id: str,
    client_secret: str,
    redirect_uri: Optional[str] = None,
    timeout: int = 30,
) -> dict[str, Any]:
    data = {"grant_type": "authorization_code", "code": code}
    if redirect_uri:
        data["redirect_uri"] = redirect_uri
    return _token_request(data, client_id, client_secret, timeout)


def refresh_access_token_v4(
    refresh_token: str,
    client_id: str,
    client_secret: str,
    timeout: int = 30,
) -> dict[str, Any]:
    data = {"grant_type": "refresh_token", "refresh_token": refresh_token}
    return _token_request(data, client_id, client_secret, timeout)


def make_bundle(
    token_json: dict[str, Any],
    scopes: str,
    previous: Optional[dict] = None,
    *,
    refresh: bool = False,
) -> dict[str, Any]:
    """Construye el bundle v4 persistible a partir de la respuesta de token.

    Conserva x_user_id previo si la respuesta no lo trae; el refresh_token
    previo solo se conserva en rotaciones (`refresh=True`), donde algunas
    respuestas devuelven solo el access token nuevo.

    `refresh` distingue la semántica RFC 6749 cuando la respuesta omite
    `scope`: en un refresh el grant no cambió (se conservan los scopes ya
    persistidos), pero en un exchange (authorization_code) la omisión
    significa "idéntico a lo solicitado" — usar los previos ahí dejaría un
    bundle con scopes viejos tras re-autorizar con scopes ampliados.
    """
    bundle = dict(token_json)
    bundle["provider_version"] = "v4"
    bundle["obtained_at"] = time.time()
    if refresh:
        fallback_scopes = (previous or {}).get("scopes") or scopes
    else:
        fallback_scopes = scopes
    bundle["scopes"] = (bundle.get("scope") or fallback_scopes or "").strip()
    if previous:
        # refresh_token solo se hereda en rotaciones (refresh): en un
        # exchange es un grant NUEVO y el refresh antiguo pertenece al grant
        # anterior (posiblemente revocado) — heredarlo crearía un bundle
        # híbrido access-nuevo/refresh-viejo.
        if refresh and not bundle.get("refresh_token") and previous.get("refresh_token"):
            bundle["refresh_token"] = previous["refresh_token"]
        if not bundle.get("x_user_id") and previous.get("x_user_id"):
            bundle["x_user_id"] = previous["x_user_id"]
    return bundle


def save_bundle_v4(path: Path, bundle: dict[str, Any]) -> None:
    save_json_atomic(Path(path), bundle)


def persist_authorized_bundle(path: Path, token_json: dict[str, Any], scopes: str) -> dict[str, Any]:
    """Persiste el bundle de un exchange (authorization_code) bajo los mismos
    locks que el refresh. Sin esto, una re-autorización que coincida con un
    refresh en vuelo puede ser sobrescrita por el resultado del refresh
    basado en el grant antiguo.

    El timeout supera el TTL de lock huérfano: un refresh vivo libera el
    lock en segundos y uno muerto se rompe a los 60s, así que la
    adquisición está garantizada salvo patología. Si aun así no se obtiene,
    se lanza error tipado en vez de escribir sin lock (escribir a ciegas
    podría dejar que un refresh en vuelo restaure credenciales antiguas o
    colisionar sobre el mismo .tmp); el usuario reintenta /auth."""
    bundle_path = Path(path)
    exchange_timeout = _FILE_LOCK_STALE_SEC + 15.0
    with _REFRESH_LOCK, _file_lock(bundle_path, timeout=exchange_timeout) as got_file_lock:
        if not got_file_lock:
            raise PolarAuthV4Error(
                "Exchange v4: lockfile de rotación ocupado más allá del timeout; "
                "reintenta la autorización."
            )
        previous = load_bundle_v4(bundle_path)
        bundle = make_bundle(token_json, scopes=scopes, previous=previous)
        save_bundle_v4(bundle_path, bundle)
    return bundle


def load_bundle_v4(path: Path) -> Optional[dict[str, Any]]:
    """Carga el bundle v4. Un access token expirado sigue siendo un bundle
    válido mientras exista refresh_token (expirado != inválido en v4)."""
    path = Path(path)
    if not path.exists():
        return None
    try:
        bundle = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError, ValueError, UnicodeDecodeError):
        return None
    if not isinstance(bundle, dict):
        return None
    if not bundle.get("access_token") and not bundle.get("refresh_token"):
        return None
    return bundle


def _safe_float(value: Any) -> float:
    """0.0 para valores ausentes o no numéricos: un bundle corrupto debe
    clasificarse como refrescable, nunca lanzar ValueError hacia /api/status
    o el flujo de refresh."""
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def bundle_needs_refresh(bundle: dict[str, Any], skew_s: float = REFRESH_SKEW_SEC) -> bool:
    if not bundle.get("access_token"):
        return True
    obtained_at = _safe_float(bundle.get("obtained_at"))
    expires_in = _safe_float(bundle.get("expires_in"))
    if expires_in <= 0:
        # Bundle sin expiración conocida = malformado o parcial: no se puede
        # garantizar que el access token siga vivo, así que se fuerza refresh
        # en lugar de servirlo indefinidamente.
        return True
    return (time.time() - obtained_at) >= max(expires_in - skew_s, 0)


def _scope_set(scopes: Any) -> set[str]:
    return {s for s in str(scopes or "").replace(",", " ").split() if s}


def bundle_scopes_match(bundle: dict[str, Any], expected_scopes: str) -> bool:
    """Si los scopes concedidos no cubren los configurados, el bundle exige
    re-autorización explícita (criterio AYO-13)."""
    expected = _scope_set(expected_scopes)
    if not expected:
        return True
    granted = _scope_set(bundle.get("scopes") or bundle.get("scope"))
    if not granted:
        # Bundle antiguo sin scopes registrados: no se puede verificar; se
        # acepta para no forzar re-auth en caliente, F0/F2 los persisten.
        return True
    return expected.issubset(granted)


def redact(bundle: Optional[dict[str, Any]]) -> dict[str, Any]:
    """Vista segura del bundle para /api/status y logs: sin tokens."""
    if not isinstance(bundle, dict):
        return {"present": False}
    return {
        "present": True,
        "provider_version": bundle.get("provider_version") or "v4",
        "scopes": bundle.get("scopes") or bundle.get("scope"),
        "obtained_at": bundle.get("obtained_at"),
        "expires_in": bundle.get("expires_in"),
        "x_user_id": bundle.get("x_user_id"),
        "has_access_token": bool(bundle.get("access_token")),
        "has_refresh_token": bool(bundle.get("refresh_token")),
        "needs_refresh": bundle_needs_refresh(bundle),
    }


def get_valid_access_token(
    path: Optional[Path] = None,
    *,
    force_refresh: bool = False,
    client_id: Optional[str] = None,
    client_secret: Optional[str] = None,
    expected_scopes: Optional[str] = None,
    timeout: int = 30,
) -> Optional[str]:
    """Devuelve un access token v4 utilizable, refrescando si hace falta.

    Devuelve None si no hay bundle, si los scopes no casan (re-auth
    requerida) o si el refresh no es viable. Nunca lanza por red: el caller
    decide cómo degradar.
    """
    from . import config

    bundle_path = Path(path) if path is not None else config.TOKEN_FILE_V4
    client_id = client_id or config.CLIENT_ID
    client_secret = client_secret or config.CLIENT_SECRET
    expected = expected_scopes if expected_scopes is not None else config.POLAR_V4_SCOPES

    bundle = load_bundle_v4(bundle_path)
    if bundle is None:
        return None
    if not bundle_scopes_match(bundle, expected):
        # Distinguible en logs de Railway de un fallo de refresh: este caso
        # solo se resuelve re-autorizando con los scopes ampliados.
        print("AVISO: Bundle v4: scopes concedidos no cubren los configurados; re-auth requerida (/auth?provider=v4).")
        return None

    if not force_refresh and not bundle_needs_refresh(bundle):
        return bundle.get("access_token")

    seen_obtained_at = bundle.get("obtained_at")
    with _REFRESH_LOCK, _file_lock(bundle_path) as got_file_lock:
        # Relee el disco: otro hilo/proceso pudo refrescar mientras esperábamos.
        current = load_bundle_v4(bundle_path) or bundle
        if current.get("obtained_at") != seen_obtained_at and not bundle_needs_refresh(current):
            return current.get("access_token")
        if not force_refresh and not bundle_needs_refresh(current):
            return current.get("access_token")

        if not got_file_lock:
            # Otro proceso está refrescando. No corremos riesgo de quemar el
            # refresh token: el caller degradará (None → re-auth manual o
            # 401-retry en el siguiente uso).
            print("⚠️ Refresh v4: lockfile ocupado por otro proceso, se cede.")
            return None

        refresh_token = current.get("refresh_token")
        if not refresh_token or not client_id or not client_secret:
            missing = "refresh_token en bundle" if not refresh_token else "credenciales OAuth en entorno"
            print(f"⚠️ Refresh v4 no viable: falta {missing}.")
            return None
        try:
            token_json = refresh_access_token_v4(refresh_token, client_id, client_secret, timeout=timeout)
        except (PolarAuthV4Error, requests.RequestException) as exc:
            print(f"⚠️ Refresh token v4 falló: {exc}")
            return None

        new_bundle = make_bundle(token_json, scopes=current.get("scopes") or expected, previous=current, refresh=True)
        save_bundle_v4(bundle_path, new_bundle)
        return new_bundle.get("access_token")
