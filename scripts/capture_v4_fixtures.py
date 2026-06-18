#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AYO-13 Fase 0: captura de fixtures reales de Polar Dynamic API v4 (dev-only).

Flujo:
1. OAuth authorization code local (HTTPServer en localhost:5050, navegador),
   contra auth.polar.com con scopes granulares v4.
2. Descarga respuestas crudas de sleeps, nightly-recharge-results,
   training-sessions (list; no existe endpoint de detalle en v4),
   ppi-samples y tests.
3. Vuelca cada respuesta a JSON. Con --anonymize sustituye ids, desplaza
   fechas y elimina cualquier token antes de escribir.
4. Además de los volcados `<nombre>_dates.json` / `<nombre>_features_<fecha>.json`,
   escribe una copia "canónica" `<nombre>.json` (primer payload con features
   y datos) para los nombres que leen los tests de adaptadores/cliente
   (`tests/fixtures/polar_v4/{sleeps,nightly_recharge_results,
   training_sessions_list,ppi_samples}.json`).

Uso (local, NUNCA en producción):
    python scripts/capture_v4_fixtures.py --days 14 --outdir research/reports/v4_capture
    python scripts/capture_v4_fixtures.py --days 14 --anonymize --outdir tests/fixtures/polar_v4

Requiere POLAR_CLIENT_ID/POLAR_CLIENT_ID2 y POLAR_CLIENT_SECRET (misma app
que v3; registrar http://localhost:5050/oauth2/callback como redirect URI
en admin.polaraccesslink.com).
"""
from __future__ import annotations

import argparse
import json
import re
import secrets
import sys
import threading
import time
import webbrowser
from datetime import date, timedelta
from pathlib import Path
from urllib.parse import parse_qs

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import requests  # noqa: E402

from hrv_app.config import CLIENT_ID, CLIENT_SECRET  # noqa: E402
from hrv_app.polar_auth_v4 import (  # noqa: E402
    build_auth_url_v4,
    exchange_code_for_token_v4,
    make_bundle,
)
from hrv_app.polar_client_v4 import API_BASE_V4  # noqa: E402


class _CallbackState:
    def __init__(self):
        self.code = None
        self.error = None
        self.raw_query = None


def start_callback_server(redirect_uri: str, state_obj: _CallbackState, timeout_s: int = 180):
    from http.server import BaseHTTPRequestHandler, HTTPServer
    from urllib.parse import urlparse

    class _Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            from urllib.parse import parse_qs, urlparse as _up
            parsed = _up(self.path)
            qs = parse_qs(parsed.query)
            state_obj.raw_query = parsed.query
            if "error" in qs:
                state_obj.error = qs.get("error", ["unknown"])[0]
            if "code" in qs:
                state_obj.code = qs["code"][0]
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(b"<h3>OK. Ya puedes cerrar esta ventana.</h3>")

        def log_message(self, fmt, *args):
            return

    u = urlparse(redirect_uri)
    httpd = HTTPServer((u.hostname or "localhost", u.port or 80), _Handler)
    httpd.timeout = 1.0
    t0 = time.time()
    while time.time() - t0 < timeout_s:
        httpd.handle_request()
        if state_obj.code or state_obj.error:
            break

LOCAL_REDIRECT_URI = "http://localhost:5050/oauth2/callback"
CAPTURE_SCOPES = "sleep:read nightly_recharge:read training_sessions:read ppi_data:read tests:read"

# (nombre de fixture, path, features por defecto)
# Según la doc oficial v4: sin `features` las respuestas solo contienen
# fechas; con `features` el rango se limita a UN día. Por eso el script hace
# dos pasadas: rango sin features (índice de fechas) + por-día con features
# (datos completos). Los nombres de features no confirmados se cierran con
# los errores 400 que el propio script registra.
ENDPOINTS = [
    # Nombres de features confirmados en el swagger oficial (kebab-case).
    # training-sessions/list enumera: samples, test-results,
    # training-load-report, laps, hill-splits, routes, statistics, zones,
    # pause-times, strength-training-results, comments, physical-info.
    # F0 solo necesita `samples` (RR); el resto queda documentado en la matriz.
    ("sleeps", "/sleeps", ["sleep-result", "sleep-score", "sleep-evaluation"]),
    ("nightly_recharge_results", "/nightly-recharge-results", ["samples"]),
    ("training_sessions_list", "/training-sessions/list", ["samples"]),
    ("ppi_samples", "/ppi-samples", ["samples"]),
    ("tests_list", "/tests/list", ["samples"]),
]

# Comparación sobre claves normalizadas (_norm_key): cubre snake_case y
# camelCase (accessToken, refreshToken, xUserId, deviceId...).
TOKEN_KEYS = ("accesstoken", "refreshtoken", "idtoken", "jti")
USER_KEYS = ("userid", "memberid", "polaruser")
DEVICE_KEYS = ("deviceid",)
DATE_RE = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})")


def _norm_key(key) -> str:
    """Normaliza una clave para matching: minúsculas y sin separadores."""
    return re.sub(r"[^a-z0-9]", "", str(key).lower())


def _range_params_for(path: str, from_iso: str, to_iso: str, features=None) -> dict:
    """from/to por endpoint. `training-sessions/list` exige datetime ISO
    (`YYYY-MM-DDTHH:MM:SS`): con fecha pura devuelve 400 "Value for key 'from'
    could not be parsed as datetime" (confirmado empíricamente en la captura
    F0 del 2026-06-13). El resto de endpoints v4 aceptan fecha pura."""
    def fmt(v: str) -> str:
        return f"{v}T00:00:00" if "training-sessions" in path else v

    params: dict[str, object] = {"from": fmt(from_iso), "to": fmt(to_iso)}
    if features:
        params["features"] = features
    return params


def _do_local_oauth() -> dict:
    if not CLIENT_ID or not CLIENT_SECRET:
        sys.exit("❌ Faltan POLAR_CLIENT_ID(/2) o POLAR_CLIENT_SECRET en el entorno")

    cb_state = _CallbackState()
    server_thread = threading.Thread(
        target=start_callback_server, args=(LOCAL_REDIRECT_URI, cb_state, 180), daemon=True
    )
    server_thread.start()

    # state anti-CSRF también en el flujo local: el HTTPServer acepta el
    # primer code que llegue, así que sin state cualquier navegación local
    # podría contaminar la captura con un código ajeno.
    oauth_state = secrets.token_urlsafe(24)
    auth_url = build_auth_url_v4(CLIENT_ID, LOCAL_REDIRECT_URI, CAPTURE_SCOPES, state=oauth_state)
    print("🔐 Abriendo navegador para autorizar (v4)...")
    webbrowser.open(auth_url)
    server_thread.join(timeout=190)

    if cb_state.error:
        sys.exit(f"❌ OAuth v4 error: {cb_state.error}")
    if not cb_state.code:
        sys.exit("❌ No se recibió código de autorización")
    returned_state = (parse_qs(cb_state.raw_query or "").get("state") or [""])[0]
    if returned_state != oauth_state:
        sys.exit("❌ state OAuth no coincide: posible callback ajeno; captura abortada")

    print("✅ Código recibido. Intercambiando por token v4...")
    token_json = exchange_code_for_token_v4(cb_state.code, CLIENT_ID, CLIENT_SECRET, LOCAL_REDIRECT_URI)
    return make_bundle(token_json, scopes=CAPTURE_SCOPES)


def _shift_dates(obj, delta_days: int):
    """Desplaza toda fecha YYYY-MM-DD encontrada en strings (anonimización)."""
    if isinstance(obj, dict):
        return {k: _shift_dates(v, delta_days) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_shift_dates(v, delta_days) for v in obj]
    if isinstance(obj, str):
        def repl(m):
            try:
                d = date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
                return (d + timedelta(days=delta_days)).isoformat()
            except ValueError:
                return m.group(0)
        return DATE_RE.sub(repl, obj)
    return obj


# Claves de localización: se ELIMINAN (coordenadas, rutas GPS).
# Exactas para términos genéricos (route, location); substring para los
# inequívocos (startLatitude, endLongitude, maxAltitude...).
LOCATION_KEYS = ("route", "location", "gpscoordinates", "coordinates")
LOCATION_KEYS_SUBSTR = ("latitude", "longitude", "altitude")
# Claves de identificador (exacto o substring sustancial).
ID_KEYS_SUBSTR = ("identifier", "uuid", "guid", "serialnumber")
# Claves a eliminar enteras: campos de texto libre que pueden contener PII.
FREE_TEXT_KEYS = ("name", "note", "notes", "description", "comment", "comments", "title")
UUID_RE = re.compile(r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b")


def _is_id_key(nk: str) -> bool:
    """True si la clave normalizada representa un identificador.

    Cubre: `id` exacto, claves que terminan en `id` (sportid, exerciseid,
    routeid, segmentid, favoriteid, organizationid, programid, eventid,
    trainingtargetid, etc.) salvo falsos positivos comunes (`paid`,
    `valid`, `android`, `void`, `unpaid`, `prepaid`)."""
    if nk == "id":
        return True
    if any(s in nk for s in ID_KEYS_SUBSTR):
        return True
    if nk.endswith("id") and len(nk) >= 3:
        if nk in {"paid", "valid", "void", "android", "unpaid", "prepaid", "rapid", "vivid", "did"}:
            return False
        return True
    return False


def _anonymize(obj, delta_days: int):
    obj = _shift_dates(obj, delta_days)

    def scrub(node):
        if isinstance(node, dict):
            out = {}
            for k, v in node.items():
                nk = _norm_key(k)
                if any(t in nk for t in TOKEN_KEYS):
                    continue
                # User/device se etiquetan antes del id-suffix genérico para
                # preservar el matiz semántico (xUserId → ANON_USER).
                if any(u in nk for u in USER_KEYS):
                    out[k] = "ANON_USER"
                    continue
                if any(d in nk for d in DEVICE_KEYS):
                    out[k] = "ANON_DEVICE"
                    continue
                # ID-keys: `routeId`, `segmentId`, `sportId`... son referencias,
                # no datos GPS — se anonimizan en vez de borrarse.
                if _is_id_key(nk):
                    out[k] = "ANON_ID"
                    continue
                if nk in LOCATION_KEYS or nk in ("lat", "lon", "lng") \
                        or any(s in nk for s in LOCATION_KEYS_SUBSTR):
                    continue
                if nk in FREE_TEXT_KEYS:
                    continue
                out[k] = scrub(v)
            return out
        if isinstance(node, list):
            return [scrub(v) for v in node]
        if isinstance(node, str):
            return UUID_RE.sub("ANON_UUID", node)
        return node

    return scrub(obj)


def _payload_has_items(payload, _depth: int = 3) -> bool:
    """True si `payload` contiene al menos una lista no vacía en algún nivel
    (hasta `_depth`). Los distintos dominios envuelven sus items con claves
    distintas (`nightSleeps`, `nightlyRechargeResults.nightlyRechargeResults`,
    `trainingSessions`, `dailyPpiSamples`...), así que se busca de forma
    genérica en vez de hardcodear cada wrapper."""
    if _depth < 0:
        return False
    if isinstance(payload, list):
        return len(payload) > 0
    if isinstance(payload, dict):
        return any(_payload_has_items(v, _depth - 1) for v in payload.values())
    return False


def _get(url: str, params: dict, headers: dict):
    try:
        return requests.get(url, params=params, headers=headers, timeout=90)
    except requests.RequestException as exc:
        print(f"  ⚠️ error de red: {exc}")
        return None


def _capture_one(name: str, path: str, params: dict, headers: dict, captured: dict) -> None:
    url = f"{API_BASE_V4}{path}"
    print(f"→ GET {url} {params}")
    r = _get(url, params, headers)
    # Throttle también en rutas de error: una ráfaga de 400s consecutivos no
    # debe golpear la API sin pausa.
    time.sleep(0.4)
    if r is None:
        return
    if r.status_code >= 400:
        # Se conserva el extracto: con features no confirmadas, el 400
        # documenta los nombres válidos que espera la API.
        print(f"  ⚠️ {r.status_code} {r.reason}: {(r.text or '')[:200]}")
        captured[name] = {
            "status": r.status_code, "url": path, "params": params,
            "error_excerpt": (r.text or "")[:300],
        }
        return
    if "json" in (r.headers.get("Content-Type") or "").lower():
        try:
            payload = r.json()
        except ValueError as exc:
            # 200 OK con JSON inválido: se documenta como error capturado en
            # vez de abortar toda la captura (F0 debe degradar, no tumbarse).
            print(f"  ⚠️ 200 con JSON inválido: {exc}")
            captured[name] = {
                "status": r.status_code, "url": path, "params": params,
                "error_excerpt": f"invalid JSON: {exc}", "body_excerpt": (r.text or "")[:300],
            }
            return
    else:
        payload = r.text
    captured[name] = payload
    print(f"  ✅ {r.status_code}")


def _persist_capture_errors(captured: dict, outdir: Path) -> list[str]:
    """Vuelca a `_capture_errors.json` los errores HTTP de la corrida.

    `_capture_one` deja cada error en `captured[name] = {status, url,
    params, error_excerpt}`. Sin sidecar, esos errores solo viven en
    stdout: rarezas recurrentes de la API real (p.ej. el 500 que Polar
    devolvió cada día de las tres corridas F0 en `/nightly-recharge-results`
    del 2026-06-11) se pierden tras cerrar la terminal y no son auditables
    contra Polar más tarde.

    Si no hubo errores, no se escribe nada (no se crea un sidecar vacío).
    Devuelve la lista de keys con error para que el caller informe."""
    import datetime as _dt

    error_keys = [
        k for k, v in captured.items()
        if isinstance(v, dict) and "status" in v and isinstance(v.get("status"), int)
    ]
    if not error_keys:
        return []
    payload = {
        "captured_at_utc": _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds"),
        "errors": [{"key": k, **captured[k]} for k in error_keys],
    }
    (outdir / "_capture_errors.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return error_keys


def _persist_canonicals(
    captured: dict, outdir: Path, canonical_names: list[str], anonymize: bool, date_shift: int
) -> list[str]:
    """Escribe los `<name>.json` canónicos respetando fixtures CURADOS.

    Fixtures curados: archivos que se mantienen a mano porque la captura
    real no sirve para tests deterministas (p.ej. training_sessions_list:
    los tests necesitan 2 deportes con `sport.id` legibles, pero la
    anonimización los reemplaza por `ANON_ID`; el real además es muy
    grande). Se marcan con un sidecar `<name>.json.curated` junto al
    canónico; si existe, este escritor NO lo sobreescribe.

    Devuelve la lista de nombres saltados para que el caller informe."""
    skipped_curated: list[str] = []
    for name in canonical_names:
        payload = captured.get(name)
        if payload is None:
            continue
        if (outdir / f"{name}.json.curated").exists():
            skipped_curated.append(name)
            continue
        if anonymize:
            payload = _anonymize(payload, date_shift)
        (outdir / f"{name}.json").write_text(
            json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8"
        )
    return skipped_curated


def main() -> None:
    parser = argparse.ArgumentParser(description="Captura fixtures Polar v4 (AYO-13 F0)")
    parser.add_argument("--days", type=int, default=14, help="Días hacia atrás del rango from/to (índice de fechas, sin features)")
    parser.add_argument("--feature-days", type=int, default=3,
                        help="Últimos N días a capturar por-día con features (datos completos; la API limita features a 1 día)")
    parser.add_argument("--outdir", default="research/reports/v4_capture", help="Directorio de salida")
    parser.add_argument("--anonymize", action="store_true", help="Anonimiza ids/coordenadas y desplaza fechas")
    parser.add_argument("--date-shift", type=int, default=-365, help="Días de desplazamiento al anonimizar")
    args = parser.parse_args()

    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    bundle = _do_local_oauth()
    token = bundle.get("access_token")
    print(f"✅ Token v4 OK. Scopes concedidos: {bundle.get('scopes')}")

    to_d = date.today()
    from_d = to_d - timedelta(days=max(args.days, 1))
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}

    captured: dict[str, object] = {}

    # Pasada 1: rango sin features → índice de fechas disponibles.
    for name, path, _features in ENDPOINTS:
        params = _range_params_for(path, from_d.isoformat(), to_d.isoformat())
        _capture_one(f"{name}_dates", path, params, headers, captured)

    # Pasada 2: por-día con features → payloads completos (la API limita
    # las consultas con features a un único día).
    for offset in range(max(args.feature_days, 1)):
        day = to_d - timedelta(days=offset)
        day_iso = day.isoformat()
        next_iso = (day + timedelta(days=1)).isoformat()
        for name, path, features in ENDPOINTS:
            if not features:
                continue
            params = _range_params_for(path, day_iso, next_iso, features=features)
            _capture_one(f"{name}_features_{day_iso}", path, params, headers, captured)

    # Copia "canónica" por dominio: el primer payload de la pasada con
    # features que NO sea un error capturado Y tenga al menos un item real
    # (no solo {"trainingSessions": []}). Es el archivo que leen los tests de
    # adaptadores/cliente (sleeps.json, nightly_recharge_results.json, etc.).
    # Si ningún día de la ventana tiene datos, NO se sobreescribe/borra un
    # canónico existente: se avisa por stdout y se escribe un marcador
    # `<name>.CAPTURE_STALE.txt` para que sea imposible pasarlo por alto.
    missing_canonical = []
    for name, _path, features in ENDPOINTS:
        if not features:
            continue
        for offset in range(max(args.feature_days, 1)):
            day = to_d - timedelta(days=offset)
            key = f"{name}_features_{day.isoformat()}"
            payload = captured.get(key)
            if isinstance(payload, dict) and "status" not in payload and _payload_has_items(payload):
                captured[name] = payload
                # Canónico fresco: el marcador de una ejecución anterior
                # fallida ya no aplica.
                (outdir / f"{name}.CAPTURE_STALE.txt").unlink(missing_ok=True)
                break
        else:
            missing_canonical.append(name)

    # Solo se persisten los canónicos por dominio (los que leen tests y la
    # matriz). Los intermedios `_dates`/`_features_<día>` se quedan en memoria:
    # volcarlos generaba decenas de MB de ruido en el directorio de fixtures
    # (un día de PPI son ~7 MB) y multiplicaba las escrituras, que en Windows
    # provocaban OSError 22 transitorios sobre los volcados grandes.
    skipped_curated = _persist_canonicals(
        captured, outdir, [name for name, _p, _f in ENDPOINTS], args.anonymize, args.date_shift
    )
    for name in skipped_curated:
        print(f"🔒 {name}.json marcado como curado (.curated sidecar); no se sobreescribe.")

    error_keys = _persist_capture_errors(captured, outdir)
    if error_keys:
        print(f"🧾 Errores HTTP de esta corrida persistidos en _capture_errors.json ({len(error_keys)} entradas).")

    for name in missing_canonical:
        canonical_path = outdir / f"{name}.json"
        existed = canonical_path.exists()
        msg = (
            f"Ningún día de la ventana ({args.feature_days} día(s)) devolvió items para "
            f"'{name}'. "
            + (f"Se conserva {canonical_path.name} de una ejecución anterior."
               if existed else f"No se escribió {canonical_path.name}.")
        )
        print(f"⚠️ {msg}")
        (outdir / f"{name}.CAPTURE_STALE.txt").write_text(msg + "\n", encoding="utf-8")

    # Token response al final y por el mismo camino que el resto: redacción
    # de tokens siempre + anonimización (ids/fechas) si procede.
    token_shape = {k: ("<redacted>" if any(t in _norm_key(k) for t in TOKEN_KEYS) else v) for k, v in bundle.items()}
    if args.anonymize:
        token_shape = _anonymize(token_shape, args.date_shift)
    (outdir / "token_response.json").write_text(json.dumps(token_shape, indent=2), encoding="utf-8")

    print(f"\n✅ Capturas escritas en {outdir}/")
    print("Siguiente paso: completar docs/HRV/AYO-13-matriz-paridad-v3-v4.md con los shapes reales.")


if __name__ == "__main__":
    main()
