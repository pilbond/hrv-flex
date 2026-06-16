from __future__ import annotations

"""
Cliente HTTP para Polar Dynamic API v4 (AYO-13, Fase 1).

Aislado del cliente v3 (`polar_client.py`): ningún consumidor canónico debe
importar este módulo directamente hasta la fase de corte (gateway). No
escribe CSVs.

- Bearer token gestionado por `polar_auth_v4.get_valid_access_token` (con
  refresh proactivo y rotación atómica).
- Retry único tras 401: fuerza refresh y reintenta una sola vez.
- Errores tipados (`PolarV4Error`) sin tokens en el mensaje.
- Rate limit local entre peticiones (mismo criterio que PolarSessionClient).
"""

import time
from datetime import date
from pathlib import Path
from typing import Any, Optional

import requests

from . import polar_auth_v4
from .polar_utils import response_excerpt

API_BASE_V4 = "https://www.polaraccesslink.com/v4/data"

REQUEST_DELAY_SEC = 0.4
DEFAULT_TIMEOUT_SEC = 60


class PolarV4Error(RuntimeError):
    """Error de la API v4. El mensaje nunca contiene tokens."""

    def __init__(self, message: str, status: Optional[int] = None):
        super().__init__(message)
        self.status = status


def _extract_items(payload: Any, candidate_keys: tuple[str, ...], _depth: int = 2) -> list:
    """Extrae la lista de items de una respuesta v4 tolerando variantes de
    envoltorio, incluido el doble wrapper oficial (p.ej. nightly-recharge:
    {"nightlyRechargeResults": {"nightlyRechargeResults": [...]}})."""
    if payload is None:
        return []
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        for key in candidate_keys:
            value = payload.get(key)
            if isinstance(value, list):
                return value
            if isinstance(value, dict) and _depth > 0:
                inner = _extract_items(value, candidate_keys, _depth - 1)
                if inner:
                    return inner
        # Envoltorio de una sola lista: se acepta aunque la clave no esté
        # entre las candidatas conocidas.
        lists = [v for v in payload.values() if isinstance(v, list)]
        if len(lists) == 1:
            return lists[0]
        # Envoltorio de un solo dict no reconocido: desciende un nivel.
        dicts = [v for v in payload.values() if isinstance(v, dict)]
        if len(dicts) == 1 and _depth > 0:
            return _extract_items(dicts[0], candidate_keys, _depth - 1)
    return []


class V4Client:
    def __init__(
        self,
        bundle_path: Optional[Path] = None,
        request_delay: float = REQUEST_DELAY_SEC,
        default_timeout: int = DEFAULT_TIMEOUT_SEC,
    ):
        from . import config

        self.bundle_path = Path(bundle_path) if bundle_path is not None else config.TOKEN_FILE_V4
        self.request_delay = request_delay
        self.default_timeout = default_timeout
        self._last_request_ts = 0.0

    def _throttle(self) -> None:
        wait_s = self.request_delay - (time.time() - self._last_request_ts)
        if wait_s > 0:
            time.sleep(wait_s)
        self._last_request_ts = time.time()

    def _do_get(self, path: str, params: Optional[dict], token: str, timeout: int, *, base: Optional[str] = None) -> requests.Response:
        self._throttle()
        url = f"{base or API_BASE_V4}{path}"
        try:
            return requests.get(
                url,
                params=params or {},
                headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
                timeout=timeout,
            )
        except requests.RequestException as exc:
            # Contrato del cliente: todo error sale tipado como PolarV4Error
            # (y sin tokens — exc de requests no incluye headers enviados).
            raise PolarV4Error(f"GET {path} -> error de red: {type(exc).__name__}: {exc}") from exc

    def _request(self, path: str, params: Optional[dict] = None, timeout: Optional[int] = None, *, base: Optional[str] = None) -> Any:
        timeout = timeout or self.default_timeout
        effective_base = base or API_BASE_V4
        token = polar_auth_v4.get_valid_access_token(self.bundle_path)
        if not token:
            raise PolarV4Error(
                "Sin token v4 utilizable (bundle ausente, scopes insuficientes o refresh fallido). "
                "Autoriza vía /auth?provider=v4."
            )

        r = self._do_get(path, params, token, timeout, base=effective_base)
        if r.status_code == 401:
            # Retry único: fuerza refresh y reintenta una sola vez.
            token = polar_auth_v4.get_valid_access_token(self.bundle_path, force_refresh=True)
            if not token:
                raise PolarV4Error(f"GET {path} -> 401 y refresh no disponible", status=401)
            r = self._do_get(path, params, token, timeout, base=effective_base)

        if r.status_code == 204:
            return None
        if r.status_code >= 400:
            raise PolarV4Error(
                f"GET {path} -> {r.status_code} {r.reason} | {response_excerpt(r)}",
                status=r.status_code,
            )
        try:
            return r.json()
        except ValueError as exc:
            raise PolarV4Error(f"GET {path} -> respuesta 2xx con JSON inválido: {exc}") from exc

    # ---- Endpoints v4 ----
    # Según doc oficial: sin `features` las respuestas solo contienen fechas;
    # con `features` el rango se limita a 1 día. No existe endpoint de detalle
    # de training session: el enriquecimiento se pide con features sobre /list.

    @staticmethod
    def _range_params(date_from: Optional[str], date_to: Optional[str], features) -> dict:
        params: dict[str, Any] = {}
        if date_from:
            params["from"] = date_from
        if date_to:
            params["to"] = date_to
        if features:
            # Doc oficial: con `features` el rango se limita a 1 día. Se hace
            # cumplir aquí para fallar por contrato (antes de la petición),
            # no con un 400 de red difícil de diagnosticar.
            if date_from and date_to:
                try:
                    span_days = (date.fromisoformat(date_to) - date.fromisoformat(date_from)).days
                except ValueError:
                    span_days = None
                if span_days is not None and span_days > 1:
                    raise PolarV4Error(
                        f"features requiere rango <= 1 dia (from={date_from}, to={date_to}, "
                        f"{span_days} dias): la API v4 devuelve 400 fuera de ese rango."
                    )
            params["features"] = list(features) if not isinstance(features, str) else [features]
        return params

    def fetch_sleeps(self, date_from: str, date_to: str, features=None) -> list[dict]:
        payload = self._request("/sleeps", params=self._range_params(date_from, date_to, features))
        return _extract_items(payload, ("nightSleeps", "night_sleeps", "sleeps"))

    def fetch_nightly_recharges(self, date_from: str, date_to: str, features=None) -> list[dict]:
        payload = self._request(
            "/nightly-recharge-results", params=self._range_params(date_from, date_to, features)
        )
        return _extract_items(
            payload,
            ("nightlyRechargeResults", "nightly_recharge_results", "nightlyRecharges"),
        )

    @staticmethod
    def _as_datetime_bound(value: Any) -> Any:
        """`/training-sessions/list` exige datetime ISO en from/to: con fecha
        pura (`YYYY-MM-DD`) devuelve 400 "Value for key 'from' could not be
        parsed as datetime" (confirmado en captura F0 2026-06-13). El resto de
        endpoints v4 aceptan fecha pura, por eso solo se normaliza aquí."""
        if isinstance(value, str) and len(value) == 10 and value.count("-") == 2:
            return f"{value}T00:00:00"
        return value

    def list_training_sessions(
        self, date_from: Optional[str] = None, date_to: Optional[str] = None, features=None, **params
    ) -> list[dict]:
        query = dict(params)
        # El span-check de features de _range_params opera sobre fecha pura
        # (date.fromisoformat), así que se construye con fechas y se promueve
        # a datetime después, solo en las claves del rango.
        query.update(self._range_params(date_from, date_to, features))
        for bound in ("from", "to"):
            if bound in query:
                query[bound] = self._as_datetime_bound(query[bound])
        payload = self._request("/training-sessions/list", params=query, timeout=90)
        return _extract_items(payload, ("trainingSessions", "training_sessions", "sessions"))

    def fetch_ppi_samples(self, date_from: str, date_to: str, features=None) -> list[dict]:
        payload = self._request("/ppi-samples", params=self._range_params(date_from, date_to, features))
        return _extract_items(payload, ("dailyPpiSamples", "ppiSamples", "ppi_samples", "samples"))

    def fetch_tests(self, date_from: str, date_to: str, features=None) -> list[dict]:
        payload = self._request("/tests/list", params=self._range_params(date_from, date_to, features))
        return _extract_items(payload, ("tests", "testResults", "test_results"))

    def list_sports(self) -> dict[str, str]:
        """Carga /v4/data/sports/list y devuelve {str(id): LABEL} para resolver
        sport.id numérico a etiqueta compatible con el filtro v3 (RUNNING,
        TRAIL_RUNNING…). Se llama una vez por instancia; el consumidor cachea."""
        payload = self._request("/sports/list")
        items = _extract_items(payload, ("sports", "sportList", "sport_list", "exerciseTypes"))
        catalog: dict[str, str] = {}
        for item in items:
            if not isinstance(item, dict):
                continue
            sport_id = None
            for key in ("id", "sportId", "identifier"):
                sport_id = item.get(key)
                if sport_id is not None:
                    break
            if isinstance(sport_id, dict):
                for nested_key in ("id", "sportId", "identifier", "value"):
                    nested_value = sport_id.get(nested_key)
                    if nested_value is not None:
                        sport_id = nested_value
                        break
            name = None
            for key in ("detailedSportInfo", "name", "technicalName", "label"):
                name = item.get(key)
                if name:
                    break
            if sport_id is not None and name:
                # Normaliza a SNAKE_UPPER_CASE para coincidir con las etiquetas
                # v3 que usa POLAR_STANDING_SPORT_MAP (TRAIL_RUNNING, etc.).
                label = str(name).strip().upper().replace(" ", "_").replace("-", "_")
                catalog[str(sport_id)] = label
        return catalog
