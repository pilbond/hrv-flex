from __future__ import annotations

from typing import Optional

import requests

from config import API_BASE, _qprint
from oauth_utils import register_polar_user
from polar_utils import response_excerpt


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


def register_user_if_needed(token: str, member_id: str, allow_transient_failure: bool = False):
    """Paso obligatorio: registrar usuario. Reintenta fallos 5xx temporales."""
    result = register_polar_user(
        access_token=token,
        member_id=member_id,
        user_url=f"{API_BASE}/users",
        allow_transient_failure=allow_transient_failure,
        log_fn=_qprint,
        response_excerpt_fn=response_excerpt,
        network_error_label="register_user network error",
        transient_error_label="register_user fallo temporal",
    )
    if result.get("status") == "temporary_failure" and allow_transient_failure:
        _qprint(
            "⚠️  register_user sigue devolviendo un error temporal. "
            "Se continúa y se reintentará en futuras syncs."
        )
    return result


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
