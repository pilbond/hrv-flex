from __future__ import annotations

import json
import threading
import time
import webbrowser
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlencode, urlparse

# Legado v3 — solo rollback temporal hasta AYO-22 (F6).
# El runtime principal usa v4 (AYO-23). No importar desde código nuevo.
from .config import AUTH_URL, CLIENT_ID, CLIENT_SECRET, REDIRECT_URI, SCOPE, TOKEN_FILE, TOKEN_URL
from .oauth_utils import exchange_code_for_token, save_json_atomic


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


def load_tokens():
    """Carga tokens guardados."""
    if not TOKEN_FILE.exists():
        return None, None

    try:
        tokens = json.loads(TOKEN_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError, ValueError, UnicodeDecodeError):
        return None, None

    obtained_at = float(tokens.get("obtained_at", 0) or 0)
    expires_in = float(tokens.get("expires_in", 0) or 0)

    if expires_in > 0 and (time.time() - obtained_at) > expires_in:
        return None, None

    return tokens.get("access_token"), tokens.get("x_user_id")


def do_oauth_flow():
    """Flujo OAuth local/dev-only. En producción se usa la Web UI."""
    if not CLIENT_ID or not CLIENT_SECRET:
        print("❌ Faltan credenciales en .env", file=sys.stderr)
        sys.exit(2)

    cb_state = _CallbackState()
    server_thread = threading.Thread(
        target=start_callback_server,
        args=(REDIRECT_URI, cb_state, 180),
        daemon=True,
    )
    server_thread.start()

    auth_url = build_auth_url(CLIENT_ID, REDIRECT_URI, SCOPE)
    print("🔐 Abriendo navegador para autorizar...")
    webbrowser.open(auth_url)

    server_thread.join(timeout=190)

    if cb_state.error:
        raise RuntimeError(f"OAuth error: {cb_state.error}")
    if not cb_state.code:
        raise RuntimeError("No se recibió código de autorización")

    print("✅ Código recibido. Intercambiando por token...")

    token_json = exchange_code_for_token(cb_state.code, CLIENT_ID, CLIENT_SECRET, TOKEN_URL, REDIRECT_URI)
    access_token = token_json.get("access_token")
    x_user_id = token_json.get("x_user_id")

    if not access_token:
        raise RuntimeError(f"No vino access_token:\n{json.dumps(token_json, indent=2)}")

    print(f"✅ Token OK. user_id: {x_user_id}")

    token_json["obtained_at"] = time.time()
    save_json_atomic(TOKEN_FILE, token_json)

    return access_token, x_user_id
