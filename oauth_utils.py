from __future__ import annotations

import base64
import json
import os
import time
from pathlib import Path
from typing import Any, Callable, Optional

import requests


def build_basic_auth_header(client_id: str, client_secret: str) -> str:
    token = base64.b64encode(f"{client_id}:{client_secret}".encode("utf-8")).decode("ascii")
    return f"Basic {token}"


def exchange_code_for_token(
    code: str,
    client_id: str,
    client_secret: str,
    token_url: str,
    redirect_uri: Optional[str] = None,
    timeout: int = 30,
) -> dict[str, Any]:
    headers = {
        "Authorization": build_basic_auth_header(client_id, client_secret),
        "Content-Type": "application/x-www-form-urlencoded",
        "Accept": "application/json;charset=UTF-8",
    }
    data = {
        "grant_type": "authorization_code",
        "code": code,
    }
    if redirect_uri:
        data["redirect_uri"] = redirect_uri

    r = requests.post(token_url, headers=headers, data=data, timeout=timeout)
    if r.status_code >= 400:
        raise RuntimeError(f"Token exchange falló: {r.status_code} {r.reason}\n{r.text}")
    return r.json()


def save_json_atomic(path: Path, payload: dict[str, Any], chmod_mode: int = 0o600) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    tmp_path.replace(path)
    if chmod_mode is None:
        return
    try:
        os.chmod(path, chmod_mode)
    except OSError:
        pass


def register_polar_user(
    access_token: str,
    member_id: str,
    user_url: str,
    allow_transient_failure: bool = False,
    *,
    log_fn: Optional[Callable[[str], None]] = None,
    response_excerpt_fn: Optional[Callable[[requests.Response], str]] = None,
    timeout: int = 30,
    retry_attempts: int = 4,
    network_error_label: str = "register_user network error",
    transient_error_label: str = "register_user fallo temporal",
    transient_codes: tuple[int, ...] = (502, 503, 504),
) -> dict[str, Any]:
    xml = f"<register><member-id>{member_id}</member-id></register>"
    last_error: Optional[str] = None

    def _log(message: str) -> None:
        if log_fn is not None:
            log_fn(message)

    for attempt in range(1, retry_attempts + 1):
        try:
            r = requests.post(
                user_url,
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Accept": "application/json",
                    "Content-Type": "application/xml",
                },
                data=xml.encode("utf-8"),
                timeout=timeout,
            )
        except requests.RequestException as exc:
            last_error = f"{network_error_label}: {exc}"
            if attempt < retry_attempts:
                wait_s = 2 ** (attempt - 1)
                _log(f"register_user intento {attempt}/{retry_attempts} con error de red. Reintentando en {wait_s}s...")
                time.sleep(wait_s)
                continue
            if allow_transient_failure:
                return {"status": "temporary_failure", "detail": str(exc)}
            raise RuntimeError(last_error) from exc

        if r.status_code in (200, 201, 409):
            return {"status": "registered" if r.status_code != 409 else "already_registered"}

        if r.status_code in transient_codes:
            excerpt = response_excerpt_fn(r) if response_excerpt_fn is not None else r.text
            last_error = f"{transient_error_label}: {r.status_code} {r.reason} | {excerpt}"
            if attempt < retry_attempts:
                wait_s = 2 ** (attempt - 1)
                _log(
                    f"register_user devolvió {r.status_code} en intento {attempt}/{retry_attempts}. "
                    f"Reintentando en {wait_s}s..."
                )
                time.sleep(wait_s)
                continue
            if allow_transient_failure:
                return {"status": "temporary_failure", "detail": last_error}
            raise RuntimeError(last_error)

        if r.status_code >= 400:
            raise RuntimeError(f"register_user fallo: {r.status_code} {r.reason}\n{r.text}")

        return {"status": "registered"}

    if allow_transient_failure:
        return {"status": "temporary_failure", "detail": last_error or "unknown transient error"}
    raise RuntimeError(last_error or "register_user fallo sin detalle")
