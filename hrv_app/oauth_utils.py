from __future__ import annotations

import base64
import json
import os
from pathlib import Path
from uuid import uuid4
from typing import Any, Optional

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
    tmp_path = path.with_suffix(path.suffix + f".{os.getpid()}.{uuid4().hex[:8]}.tmp")
    tmp_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    tmp_path.replace(path)
    if chmod_mode is None:
        return
    try:
        os.chmod(path, chmod_mode)
    except OSError:
        pass
