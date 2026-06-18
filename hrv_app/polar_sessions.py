from __future__ import annotations

import json
import logging
import os
import time
import gzip
import tempfile
from datetime import datetime, timedelta
from functools import lru_cache
from pathlib import Path
from typing import Any

import requests
from .config import TOKEN_FILE, TOKEN_FILE_V4
from .polar_utils import get_field_variant, parse_duration_to_minutes, parse_float
try:
    from fitparse import FitFile
except Exception:  # pragma: no cover - optional import at runtime
    FitFile = None


API_BASE = "https://www.polaraccesslink.com/v3"
REQUEST_DELAY = 0.4
FIELD_START_TIME = ("start-time", "start_time", "startTime")

STANDING_SPORTS = {"road_run", "trail_run", "hike"}
POLAR_STANDING_SPORT_MAP = {
    "road_run": {"RUNNING", "TREADMILL_RUNNING"},
    "trail_run": {"TRAIL_RUNNING"},
    "hike": {"HIKING"},
}

log = logging.getLogger("polar_sessions")

def _target_session_datetime(row: dict[str, str]) -> datetime:
    date_str = (row.get("Fecha") or "").strip()
    time_str = (row.get("start_time") or "").strip()
    if not date_str or not time_str:
        raise ValueError("session row lacks Fecha/start_time")
    return datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M")


def parse_polar_local_datetime(value: str) -> datetime | None:
    if not value:
        return None
    text = str(value).strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return None
    if dt.tzinfo is not None:
        return dt.replace(tzinfo=None)
    return dt


def match_polar_exercise(
    row: dict[str, str],
    exercises: list[dict[str, Any]],
    tz_offset_min: int = 0,
    allowed_polar_sports: set[str] | None = None,
) -> dict[str, Any]:
    target_dt = _target_session_datetime(row)
    target_duration = parse_float(row.get("duration_min"))
    candidates: list[tuple[float, float, dict[str, Any]]] = []
    adjusted_target_dt = target_dt + timedelta(minutes=tz_offset_min)

    for ex in exercises:
        sport = str(ex.get("detailed_sport_info") or ex.get("sport") or "").strip().upper()
        if allowed_polar_sports and sport and sport not in allowed_polar_sports:
            continue

        start_raw = get_field_variant(ex, *FIELD_START_TIME, default="")
        start_dt = parse_polar_local_datetime(start_raw)
        if not start_dt or start_dt.date() != adjusted_target_dt.date():
            continue

        delta_min = abs((start_dt - adjusted_target_dt).total_seconds()) / 60.0
        duration_min = parse_duration_to_minutes(ex.get("duration"))
        duration_gap = (
            abs(duration_min - target_duration)
            if duration_min is not None and target_duration is not None
            else 999.0
        )
        candidates.append((delta_min, duration_gap, ex))

    if not candidates:
        raise RuntimeError(f"no se encontro ejercicio Polar para {row.get('session_id')} en {adjusted_target_dt.date()}")

    candidates.sort(key=lambda item: (item[0], item[1]))
    best_delta, best_duration_gap, best = candidates[0]
    matched_via_dst_fallback = False

    if best_delta > 20:
        dst_like = [
            (delta_min, duration_gap, ex)
            for delta_min, duration_gap, ex in candidates
            if abs(delta_min - 60.0) <= 2.0 and duration_gap <= 3.0
        ]
        if len(dst_like) == 1:
            best_delta, best_duration_gap, best = dst_like[0]
            matched_via_dst_fallback = True
            log.warning(
                "DST fallback activado para %s: ejercicio %s con start_delta_min=%.1f y duration_gap_min=%s",
                row.get("session_id"),
                best.get("id"),
                best_delta,
                "None" if best_duration_gap == 999.0 else f"{best_duration_gap:.3f}",
            )

    if best_delta > 20 and not matched_via_dst_fallback:
        raise RuntimeError(
            f"match Polar demasiado lejano: {best.get('id')} a {best_delta:.1f} min del inicio esperado"
        )

    return {
        "exercise": best,
        "start_delta_min": round(best_delta, 3),
        "duration_gap_min": None if best_duration_gap == 999.0 else round(best_duration_gap, 3),
    }


def _parse_sample_values(sample: dict[str, Any]) -> list[float]:
    values: list[float] = []
    for token in str(sample.get("data", "")).split(","):
        token = token.strip()
        if not token or token.upper() == "NULL":
            continue
        value = parse_float(token)
        if value is not None:
            values.append(value)
    return values


def _mean(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None


def _percentile(values: list[float], q: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    idx = (len(ordered) - 1) * q
    lo = int(idx)
    hi = min(lo + 1, len(ordered) - 1)
    frac = idx - lo
    return ordered[lo] + (ordered[hi] - ordered[lo]) * frac


def _split_halves(values: list[float], predicate) -> tuple[list[float], list[float]]:
    # Split by moving time: filter valid samples first, then split at midpoint.
    # Pauses (samples failing predicate) are excluded before the split so they
    # don't shift the boundary — relevant for hike sessions with >20% pause time.
    valid = [v for v in values if predicate(v)]
    if len(valid) < 2:
        return [], []
    mid = len(valid) // 2
    return valid[:mid], valid[mid:]


def _mechanics_defaults() -> dict[str, Any]:
    return {
        "mechanics_source": "",
        "polar_sport_raw": "",
        "polar_start_delta_min": None,
        "polar_duration_gap_min": None,
        "run_power_available": 0,
        "run_power_mean": None,
        "run_power_max": None,
        "run_power_p95": None,
        "run_power_first_half": None,
        "run_power_second_half": None,
        "speed_first_half": None,
        "speed_second_half": None,
        "cadence_first_half": None,
        "cadence_second_half": None,
        "polar_speed_available": 0,
        "polar_cadence_available": 0,
    }


def _build_mechanical_metrics(
    *,
    source: str,
    speed_kmh: list[float],
    cadence: list[float],
    power_w: list[float],
    sport_raw: str = "",
    start_delta_min: float | None = None,
    duration_gap_min: float | None = None,
) -> dict[str, Any]:
    speed_valid = [v for v in speed_kmh if v > 1.08]
    cadence_valid = [v for v in cadence if v > 0]
    power_valid = [v for v in power_w if v > 0]

    power_first, power_second = _split_halves(power_w, lambda v: v > 0)
    speed_first, speed_second = _split_halves(speed_kmh, lambda v: v > 1.08)
    cadence_first, cadence_second = _split_halves(cadence, lambda v: v > 0)

    power_available = 1 if len(power_valid) >= 60 else 0
    speed_available = 1 if len(speed_valid) >= 60 else 0
    cadence_available = 1 if len(cadence_valid) >= 60 else 0
    source_available = 1 if power_available or speed_available or cadence_available else 0

    defaults = _mechanics_defaults()
    if not source_available:
        return defaults

    defaults.update(
        {
            "mechanics_source": source,
            "polar_sport_raw": sport_raw,
            "polar_start_delta_min": start_delta_min,
            "polar_duration_gap_min": duration_gap_min,
            "run_power_available": power_available,
            "run_power_mean": round(_mean(power_valid), 1) if power_valid else None,
            "run_power_max": round(max(power_valid), 1) if power_valid else None,
            "run_power_p95": round(_percentile(power_valid, 0.95), 1) if power_valid else None,
            "run_power_first_half": round(_mean(power_first), 1) if power_first and power_available else None,
            "run_power_second_half": round(_mean(power_second), 1) if power_second and power_available else None,
            "speed_first_half": round(_mean(speed_first), 2) if speed_first else None,
            "speed_second_half": round(_mean(speed_second), 2) if speed_second else None,
            "cadence_first_half": round(_mean(cadence_first), 1) if cadence_first else None,
            "cadence_second_half": round(_mean(cadence_second), 1) if cadence_second else None,
            "polar_speed_available": speed_available,
            "polar_cadence_available": cadence_available,
        }
    )
    return defaults


def extract_mechanical_metrics(exercise_json: dict[str, Any]) -> dict[str, Any]:
    sample_map: dict[str, list[float]] = {}
    for sample in exercise_json.get("samples") or []:
        sample_type = str(get_field_variant(sample, "sample-type", "sample_type", default="")).strip()
        if not sample_type:
            continue
        sample_map[sample_type] = _parse_sample_values(sample)

    power_w = sample_map.get("4", [])
    speed_kmh = [v * 3.6 for v in sample_map.get("1", [])]
    cadence = sample_map.get("2", [])
    return _build_mechanical_metrics(
        source="polar",
        speed_kmh=speed_kmh,
        cadence=cadence,
        power_w=power_w,
        sport_raw=str(exercise_json.get("detailed_sport_info") or exercise_json.get("sport") or "").strip(),
    )


def extract_mechanical_metrics_from_fit_file(fit_path: Path, source: str = "intervals_fit") -> dict[str, Any]:
    if FitFile is None:
        raise RuntimeError("fitparse is not installed; FIT support is unavailable")

    fit = FitFile(str(fit_path))
    session_msg = next(iter(fit.get_messages("session")), None)
    sport_raw = ""
    if session_msg is not None:
        fields = {field.name: field.value for field in session_msg}
        sport_raw = " ".join(str(fields.get(k) or "").strip() for k in ("sport", "sub_sport")).strip()

    speed_kmh: list[float] = []
    cadence: list[float] = []
    power_w: list[float] = []
    for msg in fit.get_messages("record"):
        values = {field.name: field.value for field in msg}
        speed_mps = values.get("enhanced_speed")
        if speed_mps is None:
            speed_mps = values.get("speed")
        if speed_mps is not None:
            try:
                speed_val = float(speed_mps) * 3.6
                speed_kmh.append(speed_val)
            except (TypeError, ValueError):
                pass
        cad = values.get("cadence")
        if cad is not None:
            try:
                cad_val = float(cad)
                cadence.append(cad_val)
            except (TypeError, ValueError):
                pass
        power = values.get("power")
        if power is not None:
            try:
                power_val = float(power)
                power_w.append(power_val)
            except (TypeError, ValueError):
                pass

    return _build_mechanical_metrics(
        source=source,
        speed_kmh=speed_kmh,
        cadence=cadence,
        power_w=power_w,
        sport_raw=sport_raw,
    )


def fetch_session_rr_v4(
    row: dict[str, str],
    bundle_path_v4: Path | None = None,
    allowed_polar_sports: set[str] | None = None,
    client: Any | None = None,
    sport_catalog: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Recupera RR de una sesión v4 en el shape interno histórico.

    Reutiliza el stack v4 ya existente (auth, cliente, adaptador y matcher)
    sin depender del flag transitorio POLAR_V4_SESSIONS.
    """
    date_str = str(row.get("Fecha") or "").strip()
    if not date_str:
        raise ValueError("session row lacks Fecha")

    exercises = list(
        _load_v4_session_exercises_for_date(
            bundle_path_v4 or TOKEN_FILE_V4,
            date_str,
            client=client,
            sport_catalog=sport_catalog,
        )
    )
    match = match_polar_exercise(
        row,
        exercises,
        tz_offset_min=int(os.environ.get("POLAR_TZ_OFFSET_MIN", "0")),
        allowed_polar_sports=allowed_polar_sports,
    )
    exercise = match["exercise"]

    from .hrv_sync_flow import extract_rr_ms

    rr = extract_rr_ms(exercise)
    if not rr:
        raise RuntimeError("el ejercicio Polar no contiene RR exportable")

    return {
        "exercise": exercise,
        "match": match,
        "rr": rr,
    }


@lru_cache(maxsize=32)
def _load_v4_session_exercises_for_date_cached(bundle_path: Path, date_str: str) -> tuple[dict[str, Any], ...]:
    return _load_v4_session_exercises_for_date_uncached(bundle_path, date_str)


def _load_v4_session_exercises_for_date(
    bundle_path: Path,
    date_str: str,
    client: Any | None = None,
    sport_catalog: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], ...]:
    """Carga por fecha el catálogo y las sesiones v4 adaptadas.

    Cuando el caller pasa `client` o `sport_catalog`, se evita recrearlos para
    reutilizar el stack v4 entre sesiones del mismo día.
    """
    if client is not None or sport_catalog is not None:
        return _load_v4_session_exercises_for_date_uncached(
            bundle_path,
            date_str,
            client=client,
            sport_catalog=sport_catalog,
        )
    return _load_v4_session_exercises_for_date_cached(bundle_path, date_str)


_load_v4_session_exercises_for_date.cache_clear = _load_v4_session_exercises_for_date_cached.cache_clear  # type: ignore[attr-defined]
_load_v4_session_exercises_for_date.cache_info = _load_v4_session_exercises_for_date_cached.cache_info  # type: ignore[attr-defined]


def _load_v4_session_exercises_for_date_uncached(
    bundle_path: Path,
    date_str: str,
    client: Any | None = None,
    sport_catalog: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], ...]:
    """Carga el catálogo y las sesiones v4 adaptadas sin tocar la caché."""
    from .polar_adapters_v4 import next_day_iso, v4_session_to_internal
    from .polar_client_v4 import V4Client

    client = client or V4Client(bundle_path=bundle_path)
    if sport_catalog is None:
        sport_catalog = client.list_sports()
    raw_sessions = client.list_training_sessions(
        date_from=date_str,
        date_to=next_day_iso(date_str),
        features=["samples"],
    )
    return tuple(
        ex
        for session in raw_sessions
        if (ex := v4_session_to_internal(session, sport_catalog=sport_catalog))
    )


class PolarSessionClient:
    def __init__(self, token_path: Path | None = None, bundle_path_v4: Path | None = None):
        # El runtime Polar ya se decide por POLAR_API_VERSION. POLAR_V4_SESSIONS
        # queda como compatibilidad transitoria de config, no como selector real.
        from .config import POLAR_API_VERSION as _api_version, TOKEN_FILE_V4 as _token_v4
        self._v4_mode = _api_version != "v3"

        # Estado v3 (siempre inicializado para facilitar rollback)
        self.token_path = token_path or TOKEN_FILE
        self.session = requests.Session()
        self._last_request = 0.0
        self._access_token = self._load_access_token()
        self._exercises: list[dict[str, Any]] | None = None
        self._v4_available = False

        # Estado v4 (activo por defecto en runtime v4/shadow)
        if self._v4_mode:
            from .polar_client_v4 import V4Client
            from . import polar_auth_v4
            self._v4_client = V4Client(bundle_path=bundle_path_v4 or _token_v4)
            # Verificar disponibilidad una vez: el bundle no cambia durante el run.
            # V4Client refresca el token en cada petición si está próximo a expirar.
            try:
                self._v4_available = bool(polar_auth_v4.get_valid_access_token(self._v4_client.bundle_path))
            except Exception:
                self._v4_available = False
            self._v4_sport_catalog = None
            self._v4_session_cache = {}

    def _load_access_token(self) -> str | None:
        if not self.token_path.exists():
            return None
        try:
            payload = json.loads(self.token_path.read_text(encoding="utf-8"))
        except (OSError, ValueError, json.JSONDecodeError):
            return None

        obtained_at = float(payload.get("obtained_at", 0) or 0)
        expires_in = float(payload.get("expires_in", 0) or 0)
        if expires_in > 0 and (time.time() - obtained_at) > expires_in:
            log.warning("Polar token expired; mechanics enrichment skipped")
            return None
        return payload.get("access_token")

    @property
    def available(self) -> bool:
        return self._v4_available if self._v4_mode else bool(self._access_token)

    def _rate_limit(self):
        elapsed = time.time() - self._last_request
        if elapsed < REQUEST_DELAY:
            time.sleep(REQUEST_DELAY - elapsed)
        self._last_request = time.time()

    def _get(self, path: str, params: dict[str, Any] | None = None):
        if not self._access_token:
            raise RuntimeError("token Polar ausente o expirado")
        self._rate_limit()
        response = self.session.get(
            f"{API_BASE}{path}",
            params=params,
            headers={"Authorization": f"Bearer {self._access_token}"},
            timeout=60,
        )
        response.raise_for_status()
        return response.json()

    def list_exercises(self) -> list[dict[str, Any]]:
        if self._exercises is None:
            payload = self._get("/exercises")
            self._exercises = payload if isinstance(payload, list) else []
        return self._exercises

    def get_exercise_with_samples(self, exercise_id: str) -> dict[str, Any]:
        payload = self._get(f"/exercises/{exercise_id}", params={"samples": "true"})
        return payload if isinstance(payload, dict) else {}

    # ---- Backend v4 (F5.2) ----

    def _list_sessions_for_date(self, date_str: str) -> list[dict[str, Any]]:
        """Pide [day, day+1) con features=samples, adapta y cachea por fecha."""
        if date_str in self._v4_session_cache:
            return self._v4_session_cache[date_str]

        from .polar_adapters_v4 import v4_session_to_internal, next_day_iso
        cacheable = True
        if self._v4_sport_catalog is None:
            try:
                self._v4_sport_catalog = self._v4_client.list_sports()
            except Exception as exc:
                # No cacheamos el fallo: se reintenta en la siguiente fecha.
                log.warning("No se pudo cargar catálogo de deportes v4: %s", exc)
                cacheable = False
        try:
            raw_sessions = self._v4_client.list_training_sessions(
                date_from=date_str,
                date_to=next_day_iso(date_str),
                features=["samples"],
            )
        except Exception as exc:
            log.warning("No se pudo obtener sesiones v4 para %s: %s", date_str, exc)
            raw_sessions = []

        adapted = [ex for s in raw_sessions if (ex := v4_session_to_internal(s, sport_catalog=self._v4_sport_catalog or {}))]
        if cacheable:
            self._v4_session_cache[date_str] = adapted
        return adapted

    def _enrich_row_v4(self, row: dict[str, Any], sport: str) -> dict[str, Any]:
        defaults = _mechanics_defaults()
        date_str = str(row.get("Fecha") or "").strip()
        if not date_str:
            return defaults

        exercises = self._list_sessions_for_date(date_str)
        try:
            match = match_polar_exercise(
                {k: "" if v is None else str(v) for k, v in row.items()},
                exercises,
                tz_offset_min=int(os.environ.get("POLAR_TZ_OFFSET_MIN", "0")),
                allowed_polar_sports=POLAR_STANDING_SPORT_MAP.get(sport),
            )
        except (RuntimeError, ValueError) as exc:
            log.warning("v4 session match fallido para %s: %s", date_str, exc)
            return defaults

        # En v4, list_training_sessions con features ya incluye samples:
        # no se necesita una segunda petición HTTP.
        exercise = match["exercise"]
        metrics = extract_mechanical_metrics(exercise)
        metrics["polar_start_delta_min"] = match["start_delta_min"]
        metrics["polar_duration_gap_min"] = match["duration_gap_min"]
        return {**defaults, **metrics}

    # ---- Punto de entrada ----

    def enrich_row(self, row: dict[str, Any]) -> dict[str, Any]:
        defaults = _mechanics_defaults()
        sport = str(row.get("sport") or "").strip()
        if sport not in STANDING_SPORTS or not self.available:
            if sport in STANDING_SPORTS and self._v4_mode and not self.available:
                log.warning(
                    "PolarSessionClient v4 sin bundle/token utilizable; enrichment mecánico desactivado para %s %s",
                    row.get("Fecha"),
                    row.get("session_id") or sport,
                )
            return defaults

        if self._v4_mode:
            return self._enrich_row_v4(row, sport)

        # Backend v3 (sin cambios)
        match = match_polar_exercise(
            {k: "" if v is None else str(v) for k, v in row.items()},
            self.list_exercises(),
            tz_offset_min=int(os.environ.get("POLAR_TZ_OFFSET_MIN", "0")),
            allowed_polar_sports=POLAR_STANDING_SPORT_MAP.get(sport),
        )
        exercise = self.get_exercise_with_samples(match["exercise"]["id"])
        metrics = extract_mechanical_metrics(exercise)
        metrics["polar_start_delta_min"] = match["start_delta_min"]
        metrics["polar_duration_gap_min"] = match["duration_gap_min"]
        return {**defaults, **metrics}


def extract_mechanical_metrics_from_fit_payload(payload: bytes, source: str = "intervals_fit") -> dict[str, Any]:
    fit_bytes = payload
    try:
        fit_bytes = gzip.decompress(payload)
    except (OSError, EOFError):
        pass

    tmp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".fit") as tmp:
            tmp.write(fit_bytes)
            tmp_path = Path(tmp.name)
        return extract_mechanical_metrics_from_fit_file(tmp_path, source=source)
    finally:
        if tmp_path and tmp_path.exists():
            try:
                tmp_path.unlink()
            except OSError:
                pass
