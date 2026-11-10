"""Contexto local de natación para `analysis/`.

Fuente principal: Polar Dynamic API v4 (`/training-sessions/list` con las
features `samples`, `laps`, `statistics` y `pause-times`). La consulta y la
caché están separadas de las funciones puras de transformación, de modo que
el contexto se recalcula sin red desde `polar_swim_source.json`.

Reglas principales:
- el SWOLF solo procede de Polar (`swimmingStyles[].swolfAvg`); el SWOLF de
  vuelta de los FIT regenerados por Intervals nunca se expone como métrica,
- una fase Polar solo se trata como largo tras validar piscina, conteos,
  distancia y brazadas de la sesión,
- no se infiere estilo, no se mezcla SWOLF entre estilos y las ausencias se
  devuelven como `null` con motivo.
"""
from __future__ import annotations

import csv
import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable

SCHEMA_VERSION = "swim_context_v1"
EXTRACTOR_VERSION = "1.0"
POLAR_SWIM_FEATURES = ["samples", "laps", "statistics", "pause-times"]
SOURCE_FILENAME = "polar_swim_source.json"
PHASES_FILENAME = "swim_phases.csv"
LAPS_FILENAME = "swim_laps.csv"

# Estilos cuya fase se ha comprobado que equivale a un largo de piscina.
# Mariposa, viraje, drill y fases desconocidas no heredan esa regla.
LENGTH_VALIDATED_STYLES = {"FREESTYLE", "BREASTSTROKE", "BACKSTROKE"}
SUPPORTED_POOL_UNITS = {"POOL_UNIT_METERS", "METERS", "METER"}
MATCH_TOLERANCE_MIN = 20.0
# Intervals y Polar describen el mismo ejercicio: la duración debe coincidir.
DURATION_TOLERANCE_MIN = 5.0
DST_SHIFT_MIN = 60.0
DST_SHIFT_TOLERANCE_MIN = 2.0
DST_DURATION_TOLERANCE_MIN = 3.0
SWOLF_RECONSTRUCTION_TOLERANCE = 0.001
MIN_LENGTHS_PER_STYLE = 3
DISCORDANCE_MIN_RPE = 4

PHASE_COLUMNS = [
    "phase_index",
    "start_offset_s",
    "duration_s",
    "gap_before_s",
    "style",
    "strokes",
    "length_validated",
    "distance_m",
    "pace_s_per_100m",
    "swolf_derived",
    "exclusion_reason",
    "source",
]
LAP_COLUMNS = [
    "lap_index",
    "start_s",
    "duration_s",
    "distance_m",
    "pools_swum",
    "strokes",
    "avg_secs_per_pool",
    "pace_s_per_100m",
    "source",
]


# ---------------------------------------------------------------------------
# Utilidades
# ---------------------------------------------------------------------------

def _num(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    if out != out:  # NaN
        return None
    return out


def _round(value: float | None, digits: int = 2) -> float | None:
    return None if value is None else round(value, digits)


def normalize_style(value: Any) -> str:
    text = str(value or "").strip().upper()
    if text.startswith("SWIMMING_STYLE_"):
        text = text[len("SWIMMING_STYLE_"):]
    return text or "UNKNOWN"


def _add_reason(reasons: list[str], reason: str) -> None:
    if reason not in reasons:
        reasons.append(reason)


def is_swim_session(session_row: dict[str, Any]) -> bool:
    return str(session_row.get("sport") or "").strip().lower() == "swim"


def is_swim_exercise(exercise: dict[str, Any]) -> bool:
    stats = (exercise.get("statistics") or {}).get("swimmingStatistics")
    phases = (exercise.get("samples") or {}).get("swimmingPhases")
    return bool(stats) or bool(phases)


# ---------------------------------------------------------------------------
# Correspondencia de sesión
# ---------------------------------------------------------------------------

def exercise_local_start(exercise: dict[str, Any]) -> datetime | None:
    """Hora local de inicio del ejercicio Polar, sin zona horaria.

    Polar v4 entrega `startTime` en hora local junto a
    `timezoneOffsetMinutes`. Si llegara con zona explícita, se pasa a UTC y
    se aplica el offset declarado para volver a hora local.
    """
    raw = str(exercise.get("startTime") or "").strip()
    if not raw:
        return None
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed
    offset = _num(exercise.get("timezoneOffsetMinutes"))
    utc = parsed.astimezone(timezone.utc).replace(tzinfo=None)
    return utc + timedelta(minutes=offset or 0.0)


def session_local_start(session_row: dict[str, Any]) -> datetime | None:
    date_text = str(session_row.get("Fecha") or "").strip()
    time_text = str(session_row.get("start_time") or "").strip()
    if not date_text or not time_text:
        return None
    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(f"{date_text} {time_text}", fmt)
        except ValueError:
            continue
    return None


def match_swim_exercise(session_row: dict[str, Any], exercises: Iterable[dict[str, Any]]) -> dict[str, Any]:
    """Empareja la sesión de Intervals con un ejercicio swim de Polar.

    Devuelve `status` = `matched`, `ambiguous_match` o `no_match`. Solo se
    acepta un candidato inequívoco con hora dentro de la tolerancia y
    duración a menos de `DURATION_TOLERANCE_MIN`; un desfase de ~60 min con
    duración casi idéntica se acepta como cambio horario. Si falta alguna de
    las dos duraciones no hay correspondencia.
    """
    target = session_local_start(session_row)
    target_duration = _num(session_row.get("duration_min"))
    result: dict[str, Any] = {
        "status": "no_match",
        "exercise": None,
        "start_delta_min": None,
        "duration_gap_min": None,
        "dst_fallback": False,
        "candidate_count": 0,
    }
    if target is None:
        result["reason"] = "session_start_missing"
        return result

    candidates: list[tuple[float, float | None, dict[str, Any]]] = []
    for exercise in exercises:
        if not isinstance(exercise, dict) or not is_swim_exercise(exercise):
            continue
        start = exercise_local_start(exercise)
        if start is None:
            continue
        delta = abs((start - target).total_seconds()) / 60.0
        duration_ms = _num(exercise.get("durationMillis"))
        gap = (
            abs(duration_ms / 60000.0 - target_duration)
            if duration_ms is not None and target_duration is not None
            else None
        )
        candidates.append((delta, gap, exercise))
    result["candidate_count"] = len(candidates)

    in_time = [c for c in candidates if c[0] <= MATCH_TOLERANCE_MIN]
    within = [c for c in in_time if c[1] is not None and c[1] <= DURATION_TOLERANCE_MIN]
    if in_time and not within:
        result["reason"] = "duration_mismatch"
        return result
    dst_fallback = False
    if not within:
        within = [
            c for c in candidates
            if abs(c[0] - DST_SHIFT_MIN) <= DST_SHIFT_TOLERANCE_MIN
            and c[1] is not None
            and c[1] <= DST_DURATION_TOLERANCE_MIN
        ]
        dst_fallback = bool(within)
    if not within:
        return result
    if len(within) > 1:
        result["status"] = "ambiguous_match"
        return result

    delta, gap, exercise = within[0]
    result.update({
        "status": "matched",
        "exercise": exercise,
        "start_delta_min": round(delta, 3),
        "duration_gap_min": None if gap is None else round(gap, 3),
        "dst_fallback": dst_fallback,
    })
    return result


# ---------------------------------------------------------------------------
# Adquisición y caché (única parte con red)
# ---------------------------------------------------------------------------

def _next_day(date_text: str) -> str:
    return (date.fromisoformat(date_text) + timedelta(days=1)).isoformat()


def trim_exercise_for_cache(exercise: dict[str, Any]) -> dict[str, Any]:
    """Conserva solo lo necesario para recalcular `swim_context`.

    Se descartan las series por segundo (FC, velocidad, distancia, cadencia)
    y cualquier identificador; quedan inicio, duración, distancia,
    estadísticas swim, vueltas, fases y pausas.
    """
    samples = exercise.get("samples") or {}
    return {
        "startTime": exercise.get("startTime"),
        "timezoneOffsetMinutes": exercise.get("timezoneOffsetMinutes"),
        "durationMillis": exercise.get("durationMillis"),
        "distanceMeters": exercise.get("distanceMeters"),
        "statistics": {"swimmingStatistics": (exercise.get("statistics") or {}).get("swimmingStatistics")},
        "laps": exercise.get("laps"),
        "samples": {"swimmingPhases": samples.get("swimmingPhases")},
        "pauseTimes": exercise.get("pauseTimes"),
    }


def revalidate_source_match(polar_source: dict[str, Any], session_row: dict[str, Any]) -> dict[str, Any]:
    """Vuelve a emparejar el ejercicio guardado con la fila de sesión actual.

    Una caché o un artefacto pueden quedar desfasados (fila de Intervals
    corregida, sesión distinta con el mismo slug): el `match` guardado no se
    acepta sin repetir la comprobación de hora y duración.
    """
    exercise = polar_source.get("exercise")
    if not exercise:
        return dict(polar_source.get("match") or {"status": "no_match"})
    result = match_swim_exercise(session_row, [exercise])
    result.pop("exercise", None)
    if result["status"] != "matched":
        result.setdefault("reason", "cached_source_mismatch")
    return result


def cached_source_is_valid(polar_source: dict[str, Any], session_row: dict[str, Any]) -> bool:
    if polar_source.get("query_date") != str(session_row.get("Fecha") or "").strip():
        return False
    if list(polar_source.get("features") or []) != list(POLAR_SWIM_FEATURES):
        return False
    if not polar_source.get("exercise"):
        # Un "sin correspondencia" guardado puede deberse a una sincronización
        # tardía de Polar: se vuelve a consultar.
        return False
    return revalidate_source_match(polar_source, session_row)["status"] == "matched"


def fetch_polar_swim_source(
    session_row: dict[str, Any],
    cache_path: Path,
    *,
    client: Any | None = None,
    refresh: bool = False,
) -> dict[str, Any]:
    """Consulta Polar v4 para el día de la sesión y guarda el ejercicio swim.

    Reutiliza la caché si existe. El fichero guardado contiene el ejercicio
    recortado y el resultado de la correspondencia, nunca la respuesta
    completa ni tokens.
    """
    cache_path = Path(cache_path)
    if cache_path.exists() and not refresh:
        try:
            cached = json.loads(cache_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            cached = None
        if isinstance(cached, dict) and cached_source_is_valid(cached, session_row):
            return cached

    date_text = str(session_row.get("Fecha") or "").strip()
    if not date_text:
        raise ValueError("session row lacks Fecha")
    if client is None:
        from hrv_app.polar_client_v4 import V4Client

        client = V4Client()
    sessions = client.list_training_sessions(date_text, _next_day(date_text), features=POLAR_SWIM_FEATURES)
    exercises = [
        exercise
        for session in sessions or []
        if isinstance(session, dict)
        for exercise in (session.get("exercises") or [])
    ]
    match = match_swim_exercise(session_row, exercises)
    exercise = match.pop("exercise")
    payload = {
        "schema_version": 1,
        "extractor_version": EXTRACTOR_VERSION,
        "retrieved_at_utc": datetime.now(timezone.utc).isoformat(),
        "endpoint": "/v4/data/training-sessions/list",
        "features": list(POLAR_SWIM_FEATURES),
        "query_date": date_text,
        "match": match,
        "exercise": trim_exercise_for_cache(exercise) if exercise else None,
    }
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = cache_path.with_suffix(cache_path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")
    tmp.replace(cache_path)
    return payload


# ---------------------------------------------------------------------------
# Transformación pura
# ---------------------------------------------------------------------------

def _swim_stats(exercise: dict[str, Any]) -> dict[str, Any]:
    return (exercise.get("statistics") or {}).get("swimmingStatistics") or {}


def _raw_phases(exercise: dict[str, Any]) -> list[dict[str, Any]]:
    phases = ((exercise.get("samples") or {}).get("swimmingPhases") or {}).get("phases") or []
    return sorted(
        (p for p in phases if isinstance(p, dict)),
        key=lambda p: _num(p.get("startOffsetMillis")) or 0.0,
    )


def _pool(stats: dict[str, Any]) -> tuple[float | None, list[str]]:
    reasons: list[str] = []
    pool = _num(stats.get("poolLength"))
    units = str(stats.get("poolUnits") or "").strip().upper()
    if pool is None or pool <= 0:
        reasons.append("pool_unknown")
        return None, reasons
    if units and units not in SUPPORTED_POOL_UNITS:
        reasons.append("pool_unknown")
        return None, reasons
    return pool, reasons


def validate_lengths(exercise: dict[str, Any]) -> dict[str, Any]:
    """Decide si las fases Polar pueden leerse como largos de piscina."""
    stats = _swim_stats(exercise)
    phases = _raw_phases(exercise)
    pool, reasons = _pool(stats)
    checks: dict[str, Any] = {"pool_length_m": pool, "n_phases": len(phases)}
    if not phases:
        _add_reason(reasons, "phase_validation_failed")
        return {"status": "not_applicable" if not stats else "failed", "reasons": reasons, "checks": checks}

    styles = [normalize_style(p.get("style")) for p in phases]
    unsupported = sorted({s for s in styles if s not in LENGTH_VALIDATED_STYLES})
    if unsupported:
        _add_reason(reasons, "unsupported_phase_type")
        checks["unsupported_styles"] = unsupported

    # Sin inicio o duración no se puede ubicar la fase ni comprobar solapes.
    untimed = sum(
        1 for p in phases
        if _num(p.get("startOffsetMillis")) is None
        or _num(p.get("durationMillis")) is None
        or (_num(p.get("durationMillis")) or 0.0) <= 0
    )
    checks["phases_without_timing"] = untimed
    if untimed:
        _add_reason(reasons, "phase_validation_failed")

    overlaps = 0
    for previous, current in zip(phases, phases[1:]):
        end = (_num(previous.get("startOffsetMillis")) or 0.0) + (_num(previous.get("durationMillis")) or 0.0)
        if (_num(current.get("startOffsetMillis")) or 0.0) < end:
            overlaps += 1
    checks["overlaps"] = overlaps
    if overlaps:
        _add_reason(reasons, "phase_validation_failed")

    pools_swum = _num(stats.get("poolsSwum"))
    checks["pools_swum"] = pools_swum
    if pools_swum is None or int(pools_swum) != len(phases):
        _add_reason(reasons, "phase_validation_failed")

    # Conciliación por estilo: cada estilo validable presente en las fases
    # necesita su agregado oficial, con distancia, brazadas y SWOLF que cuadren.
    stats_styles = {
        normalize_style(style.get("style")): style
        for style in stats.get("swimmingStyles") or []
        if isinstance(style, dict)
    }
    phase_styles = {s for s in styles if s in LENGTH_VALIDATED_STYLES}
    if not stats_styles:
        _add_reason(reasons, "phase_validation_failed")
        checks["styles_missing"] = True
    missing = sorted(phase_styles - set(stats_styles))
    if missing:
        _add_reason(reasons, "phase_validation_failed")
        checks["styles_without_statistics"] = missing

    style_checks: dict[str, Any] = {}
    for key, style in stats_styles.items():
        group = [p for p, s in zip(phases, styles) if s == key]
        strokes_present = bool(group) and all(_num(p.get("strokes")) is not None for p in group)
        durations_present = bool(group) and all(_num(p.get("durationMillis")) is not None for p in group)
        strokes_sum = sum(_num(p.get("strokes")) or 0.0 for p in group)
        duration_sum_s = sum(_num(p.get("durationMillis")) or 0.0 for p in group) / 1000.0
        distance = _num(style.get("distanceMeters"))
        stroke_count = _num(style.get("strokeCount"))
        distance_ok = pool is not None and distance is not None and abs(len(group) * pool - distance) < 0.5
        strokes_ok = strokes_present and stroke_count is not None and abs(strokes_sum - stroke_count) < 0.5
        swolf_polar = _num(style.get("swolfAvg"))
        reconstructed = (duration_sum_s + strokes_sum) / len(group) if strokes_present and durations_present else None
        error = abs(reconstructed - swolf_polar) if reconstructed is not None and swolf_polar is not None else None
        if swolf_polar is None:
            swolf_check = "missing"
        elif error is None:
            swolf_check = "not_computable"
        elif error <= SWOLF_RECONSTRUCTION_TOLERANCE:
            swolf_check = "ok"
        else:
            swolf_check = "mismatch"
        style_checks[key] = {
            "n_phases": len(group),
            "distance_ok": distance_ok,
            "strokes_ok": strokes_ok,
            "swolf_reconstructed": _round(reconstructed, 4),
            "swolf_abs_error": _round(error, 6),
            "swolf_check": swolf_check,
        }
        if key not in LENGTH_VALIDATED_STYLES:
            continue
        if not (distance_ok and strokes_ok):
            _add_reason(reasons, "phase_validation_failed")
        if swolf_check == "mismatch":
            # Un SWOLF oficial que no se reproduce desde las fases indica
            # tiempos o brazadas incoherentes: bloquea los largos derivados.
            _add_reason(reasons, "source_mismatch")
            _add_reason(reasons, "phase_validation_failed")
    checks["styles"] = style_checks

    blocking = {"pool_unknown", "phase_validation_failed"}
    status = "failed" if blocking.intersection(reasons) else "passed"
    return {"status": status, "reasons": reasons, "checks": checks}


def build_phase_rows(exercise: dict[str, Any], validation: dict[str, Any]) -> list[dict[str, Any]]:
    pool = validation.get("checks", {}).get("pool_length_m")
    passed = validation.get("status") == "passed"
    style_checks = validation.get("checks", {}).get("styles") or {}
    # El SWOLF por largo solo se deriva en estilos cuyo SWOLF oficial se
    # reproduce desde las fases.
    swolf_validated = {key for key, item in style_checks.items() if item.get("swolf_check") == "ok"}
    rows: list[dict[str, Any]] = []
    previous_end: float | None = None
    for index, phase in enumerate(_raw_phases(exercise), start=1):
        start_ms = _num(phase.get("startOffsetMillis"))
        duration_ms = _num(phase.get("durationMillis"))
        style = normalize_style(phase.get("style"))
        strokes = _num(phase.get("strokes"))
        start_s = None if start_ms is None else start_ms / 1000.0
        duration_s = None if duration_ms is None else duration_ms / 1000.0
        gap_before = None
        if previous_end is not None and start_s is not None:
            gap_before = round(start_s - previous_end, 3)
        if start_s is not None and duration_s is not None:
            previous_end = start_s + duration_s

        validated = passed and style in LENGTH_VALIDATED_STYLES and duration_s is not None and duration_s > 0
        exclusion = None
        if not validated:
            if style not in LENGTH_VALIDATED_STYLES:
                exclusion = "unsupported_phase_type"
            elif not passed:
                exclusion = "phase_validation_failed"
            else:
                exclusion = "duration_missing"
        distance = pool if validated else None
        rows.append({
            "phase_index": index,
            "start_offset_s": _round(start_s, 3),
            "duration_s": _round(duration_s, 3),
            "gap_before_s": gap_before,
            "style": style,
            "strokes": None if strokes is None else int(strokes),
            "length_validated": validated,
            "distance_m": distance,
            "pace_s_per_100m": _round(100.0 * duration_s / distance, 2) if validated and distance else None,
            "swolf_derived": (
                _round(duration_s + strokes, 3)
                if validated and strokes is not None and style in swolf_validated
                else None
            ),
            "exclusion_reason": exclusion,
            "source": "polar_v4",
        })
    return rows


def build_lap_rows(exercise: dict[str, Any]) -> list[dict[str, Any]]:
    laps = (exercise.get("laps") or {}).get("laps") or []
    rows: list[dict[str, Any]] = []
    for index, lap in enumerate((lap for lap in laps if isinstance(lap, dict)), start=1):
        duration_ms = _num(lap.get("durationMillis"))
        split_ms = _num(lap.get("splitTimeMillis"))
        distance = _num(lap.get("distanceMeters"))
        swim = (lap.get("statistics") or {}).get("swimmingStatistics") or lap.get("swimmingStatistics") or {}
        duration_s = None if duration_ms is None else duration_ms / 1000.0
        start_s = None
        if split_ms is not None and duration_ms is not None:
            start_s = (split_ms - duration_ms) / 1000.0
        pools = _num(swim.get("poolsSwum"))
        strokes = _num(swim.get("strokes"))
        rows.append({
            "lap_index": index,
            "start_s": _round(start_s, 3),
            "duration_s": _round(duration_s, 3),
            "distance_m": distance,
            "pools_swum": None if pools is None else int(pools),
            "strokes": None if strokes is None else int(strokes),
            "avg_secs_per_pool": _round(_num(swim.get("avgSecsPerPool")), 4),
            "pace_s_per_100m": (
                _round(100.0 * duration_s / distance, 2)
                if duration_s and distance and distance > 0
                else None
            ),
            "source": "polar_v4",
        })
    return rows


def build_fit_lap_rows(fit_laps: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """Vueltas descriptivas del FIT de Intervals: solo tiempo y distancia.

    Se excluyen vueltas sin distancia o sin tiempo (p. ej. la vuelta terminal
    de 1 s) y se ignora deliberadamente su campo SWOLF.
    """
    rows: list[dict[str, Any]] = []
    elapsed = 0.0
    for lap in fit_laps:
        timer = _num(lap.get("total_timer_time"))
        distance = _num(lap.get("total_distance"))
        start = elapsed
        elapsed += timer or 0.0
        if not timer or timer <= 0 or not distance or distance <= 0:
            continue
        rows.append({
            "lap_index": len(rows) + 1,
            "start_s": round(start, 3),
            "duration_s": round(timer, 3),
            "distance_m": distance,
            "pools_swum": None,
            "strokes": None,
            "avg_secs_per_pool": None,
            "pace_s_per_100m": round(100.0 * timer / distance, 2),
            "source": "intervals_fit_laps",
        })
    return rows


def read_fit_laps(fit_path: Path | None) -> list[dict[str, Any]]:
    if not fit_path or not Path(fit_path).exists():
        return []
    try:
        from fitparse import FitFile
    except Exception:
        return []
    try:
        return [message.get_values() for message in FitFile(str(fit_path)).get_messages("lap")]
    except Exception:
        return []


def _style_summary(
    stats: dict[str, Any],
    phase_rows: list[dict[str, Any]],
    validation: dict[str, Any],
    reasons: list[str],
) -> list[dict[str, Any]]:
    passed = validation.get("status") == "passed"
    style_checks = validation.get("checks", {}).get("styles") or {}
    out: list[dict[str, Any]] = []
    for style in stats.get("swimmingStyles") or []:
        if not isinstance(style, dict):
            continue
        key = normalize_style(style.get("style"))
        distance = _num(style.get("distanceMeters"))
        swim_time_s = (_num(style.get("swimmingTimeTotalMillis")) or 0.0) / 1000.0 or None
        swolf_polar = _num(style.get("swolfAvg"))
        lengths = [r for r in phase_rows if r["style"] == key and r["length_validated"]]
        check = style_checks.get(key) or {}
        swolf_check = check.get("swolf_check")
        if swolf_polar is None:
            swolf_status = "missing"
        elif swolf_check == "mismatch":
            swolf_status = "mismatch"
            _add_reason(reasons, "source_mismatch")
        elif passed and swolf_check == "ok":
            swolf_status = "validated_against_phases"
        else:
            swolf_status = "not_validated"
        reconstructed = check.get("swolf_reconstructed")
        error = check.get("swolf_abs_error")
        n_lengths = len(lengths) if passed else None
        too_few = n_lengths is not None and n_lengths < MIN_LENGTHS_PER_STYLE
        if too_few:
            _add_reason(reasons, "too_few_lengths")
        out.append({
            "style": key,
            "distance_m": distance,
            "strokes": None if _num(style.get("strokeCount")) is None else int(_num(style.get("strokeCount"))),
            "swim_time_s": _round(swim_time_s, 3),
            "pace_s_per_100m": (
                _round(100.0 * swim_time_s / distance, 2) if swim_time_s and distance else None
            ),
            "hr_avg": _num(style.get("hrAvg")),
            "hr_max": _num(style.get("hrMax")),
            "n_lengths_validated": n_lengths,
            "too_few_lengths": too_few,
            "swolf_polar": swolf_polar,
            "swolf_reconstructed": reconstructed,
            "swolf_abs_error": error,
            "swolf_validation_status": swolf_status,
        })
    return out


def _pause_summary(exercise: dict[str, Any]) -> tuple[int | None, float | None]:
    pauses = exercise.get("pauseTimes")
    if pauses is None:
        return None, None
    if isinstance(pauses, dict):
        pauses = pauses.get("pauseTimes") or pauses.get("pauses") or []
    if not isinstance(pauses, list):
        return None, None
    total_ms = 0.0
    for pause in pauses:
        if not isinstance(pause, dict):
            return len(pauses), None
        duration = _num(pause.get("durationMillis"))
        if duration is None:
            try:
                start = datetime.fromisoformat(str(pause.get("startTime")))
                end = datetime.fromisoformat(str(pause.get("endTime")))
            except (TypeError, ValueError):
                return len(pauses), None
            duration = (end - start).total_seconds() * 1000.0
        if duration < 0:
            return len(pauses), None
        total_ms += duration
    return len(pauses), round(total_ms / 1000.0, 3)


def _valid_rpe(session_row: dict[str, Any]) -> float | None:
    rpe = _num(session_row.get("rpe"))
    if rpe is None or rpe < 1 or rpe > 10:
        return None
    return rpe


def build_load_fields(
    session_row: dict[str, Any],
    *,
    cardio_score: int | None,
    intervals_session_rpe: float | None,
    reasons: list[str],
) -> dict[str, Any]:
    rpe = _valid_rpe(session_row)
    duration = _num(session_row.get("duration_min"))
    if rpe is None:
        _add_reason(reasons, "rpe_missing")
    if duration is None or duration <= 0:
        _add_reason(reasons, "duration_missing")
        duration = None
    srpe = round(rpe * duration, 1) if rpe is not None and duration is not None else None
    if rpe is None or cardio_score is None:
        discordance = None
    else:
        discordance = rpe >= DISCORDANCE_MIN_RPE and cardio_score == 0
    intervals_srpe = _num(intervals_session_rpe)
    if intervals_srpe is not None and intervals_srpe <= 0:
        intervals_srpe = None
    return {
        "rpe": rpe,
        "rpe_source": "sessions.rpe",
        "srpe_load": srpe,
        "srpe_unit": "AU",
        "srpe_duration_basis": "sessions.duration_min",
        "intervals_session_rpe": intervals_srpe,
        "intervals_session_rpe_basis": "intervals moving_time x icu_rpe",
        "srpe_minus_intervals_session_rpe": (
            round(srpe - intervals_srpe, 1) if srpe is not None and intervals_srpe is not None else None
        ),
        "cardio_score": cardio_score,
        "rpe_vs_cardio_discordance": discordance,
    }


def build_swim_context(
    session_row: dict[str, Any],
    polar_source: dict[str, Any] | None,
    *,
    fit_laps: Iterable[dict[str, Any]] | None = None,
    cardio_score: int | None = None,
    intervals_session_rpe: float | None = None,
    polar_error: str | None = None,
) -> tuple[dict[str, Any] | None, list[dict[str, Any]], list[dict[str, Any]]]:
    """Construye `swim_context` y las filas de `swim_phases.csv` / `swim_laps.csv`.

    Devuelve `(None, [], [])` para sesiones que no son de natación.
    """
    if not is_swim_session(session_row):
        return None, [], []

    reasons: list[str] = []
    match = (polar_source or {}).get("match") or {}
    exercise = (polar_source or {}).get("exercise")
    if polar_source is not None and exercise:
        match = revalidate_source_match(polar_source, session_row)
        if match.get("status") != "matched":
            exercise = None
            _add_reason(reasons, "source_mismatch")
    if polar_source is None:
        _add_reason(reasons, "polar_unavailable")
    elif match.get("status") == "ambiguous_match":
        _add_reason(reasons, "ambiguous_match")
    elif not exercise:
        _add_reason(reasons, "polar_unavailable")
        if match.get("reason") == "duration_mismatch":
            _add_reason(reasons, "source_mismatch")

    phase_rows: list[dict[str, Any]] = []
    lap_rows: list[dict[str, Any]] = []
    styles: list[dict[str, Any]] = []
    stats: dict[str, Any] = {}
    validation: dict[str, Any] = {"status": "not_applicable", "reasons": [], "checks": {}}
    pause_count = pause_total_s = None
    session_duration_s = None

    if exercise:
        stats = _swim_stats(exercise)
        validation = validate_lengths(exercise)
        for reason in validation["reasons"]:
            _add_reason(reasons, reason)
        phase_rows = build_phase_rows(exercise, validation)
        lap_rows = build_lap_rows(exercise)
        styles = _style_summary(stats, phase_rows, validation, reasons)
        pause_count, pause_total_s = _pause_summary(exercise)
        duration_ms = _num(exercise.get("durationMillis"))
        session_duration_s = None if duration_ms is None else round(duration_ms / 1000.0, 3)
        swim_source = "polar_v4"
    else:
        lap_rows = build_fit_lap_rows(fit_laps or [])
        swim_source = "intervals_fit_laps" if lap_rows else "none"

    if validation.get("status") == "passed":
        granularity = "length"
    elif phase_rows:
        granularity = "phase"
    elif lap_rows:
        granularity = "lap"
    elif stats:
        granularity = "session"
    else:
        granularity = "none"

    if styles and not any(s["distance_m"] for s in styles):
        _add_reason(reasons, "stroke_unknown")
    elif exercise and not styles:
        _add_reason(reasons, "stroke_unknown")

    # SWOLF: solo Polar, por estilo, nunca mezclado.
    swolf_by_stroke = {s["style"]: s["swolf_polar"] for s in styles if s["swolf_polar"] is not None}
    statuses = {s["swolf_validation_status"] for s in styles if s["swolf_polar"] is not None}
    if not swolf_by_stroke:
        swolf_validation_status = None
    elif "mismatch" in statuses:
        swolf_validation_status = "mismatch"
    elif statuses == {"validated_against_phases"}:
        swolf_validation_status = "validated_against_phases"
    else:
        swolf_validation_status = "not_validated"

    distance_total = _num(stats.get("distanceMeters"))
    styled_distance = sum(s["distance_m"] or 0.0 for s in styles)
    distribution = {}
    for s in styles:
        if s["distance_m"]:
            distribution[s["style"]] = {
                "distance_m": s["distance_m"],
                "pct": _round(100.0 * s["distance_m"] / styled_distance, 1) if styled_distance else None,
            }
    unclassified = (
        round(max(0.0, distance_total - styled_distance), 1) if distance_total is not None and styles else None
    )
    supported = [s for s in styles if s["style"] in LENGTH_VALIDATED_STYLES and s["distance_m"]]
    primary = max(supported, key=lambda s: s["distance_m"])["style"] if supported else None
    breaststroke_pct = (
        distribution.get("BREASTSTROKE", {}).get("pct", 0.0) if distribution else None
    )

    # El ritmo agregado exige tiempo y distancia en todos los estilos con
    # distancia: sumar metros sin su tiempo daría un ritmo falsamente rápido.
    timed = [s for s in styles if s["distance_m"]]
    time_complete = bool(timed) and all(s["swim_time_s"] for s in timed)
    if timed and not time_complete:
        _add_reason(reasons, "duration_missing")
    swim_time_s = sum(s["swim_time_s"] for s in timed) if time_complete else None
    pace = _round(100.0 * swim_time_s / styled_distance, 2) if swim_time_s and styled_distance else None
    gaps = [r["gap_before_s"] for r in phase_rows if r["gap_before_s"] is not None and r["gap_before_s"] > 0]

    load = build_load_fields(
        session_row,
        cardio_score=cardio_score,
        intervals_session_rpe=intervals_session_rpe,
        reasons=reasons,
    )

    if swim_source == "none" and load["rpe"] is None:
        status = "unavailable"
    elif reasons:
        status = "partial"
    else:
        status = "available"

    context = {
        "schema_version": SCHEMA_VERSION,
        "extractor_version": EXTRACTOR_VERSION,
        "session_id": session_row.get("session_id"),
        "session_date": session_row.get("Fecha"),
        "status": status,
        "swim_source": swim_source,
        "granularity": granularity,
        "polar_match": {
            "status": match.get("status") if polar_source is not None else None,
            "reason": match.get("reason"),
            "start_delta_min": match.get("start_delta_min"),
            "duration_gap_min": match.get("duration_gap_min"),
            "dst_fallback": match.get("dst_fallback"),
            "retrieved_at_utc": (polar_source or {}).get("retrieved_at_utc"),
            "features": (polar_source or {}).get("features"),
            "error": polar_error,
        },
        "length_validation_status": validation.get("status") if exercise else None,
        "pool_length_m": validation.get("checks", {}).get("pool_length_m") if exercise else None,
        "pool_units": stats.get("poolUnits") if exercise else None,
        "distance_m": distance_total,
        "distance_unclassified_m": unclassified,
        "n_phases": len(phase_rows) if exercise else None,
        "n_lengths_validated": sum(1 for r in phase_rows if r["length_validated"]) if exercise else None,
        "n_laps": len(lap_rows),
        "laps_source": lap_rows[0]["source"] if lap_rows else None,
        "session_duration_s": session_duration_s,
        "swim_time_s": _round(swim_time_s, 3),
        "pace_s_per_100m": pace,
        "pace_basis": "100 x sum(swimmingTimeTotalMillis) / sum(style distance)" if pace is not None else None,
        "phase_gaps_count": len(gaps) if exercise else None,
        "phase_gaps_total_s": _round(sum(gaps), 3) if exercise else None,
        "pause_count": pause_count,
        "pause_total_s": pause_total_s,
        "total_strokes": None if _num(stats.get("totalStrokeCount")) is None else int(_num(stats.get("totalStrokeCount"))),
        "primary_stroke": primary,
        "stroke_distribution_basis": "distance_m" if distribution else None,
        "stroke_distribution": distribution or None,
        "breaststroke_pct": breaststroke_pct,
        "styles": styles or None,
        "swolf_source": "polar" if swolf_by_stroke else "none",
        "swolf_by_stroke": swolf_by_stroke or None,
        "swolf_validation_status": swolf_validation_status,
        "hr_confidence": "sensor_unknown",
        **load,
        "quality_reasons": reasons,
        "artifacts": {
            "phases": PHASES_FILENAME if phase_rows else None,
            "laps": LAPS_FILENAME if lap_rows else None,
            "source": SOURCE_FILENAME if exercise else None,
        },
    }
    return context, phase_rows, lap_rows


# ---------------------------------------------------------------------------
# Historial comparable por estilo
# ---------------------------------------------------------------------------

HISTORY_LIMIT = 5
HISTORY_MIN_SESSIONS = 3
HISTORY_TIME_BASIS = "swimmingTimeTotalMillis por estilo"


def load_prior_swim_contexts(reports_root: Path, *, exclude_session_id: Any = None) -> list[dict[str, Any]]:
    """`swim_context` guardados en `summary.json` de informes de sesión previos."""
    out: list[dict[str, Any]] = []
    root = Path(reports_root)
    if not root.exists():
        return out
    for summary_path in sorted(root.glob("*/*/*/artifacts/summary.json")):
        try:
            summary = json.loads(summary_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        context = summary.get("swim_context")
        if not isinstance(context, dict) or not context.get("session_date"):
            continue
        if exclude_session_id is not None and str(context.get("session_id")) == str(exclude_session_id):
            continue
        out.append(context)
    return out


def _eligible_style(context: dict[str, Any], style: str) -> dict[str, Any] | None:
    if context.get("swim_source") != "polar_v4" or context.get("length_validation_status") != "passed":
        return None
    for item in context.get("styles") or []:
        if item.get("style") != style:
            continue
        if item.get("too_few_lengths") or item.get("swolf_validation_status") != "validated_against_phases":
            return None
        return item
    return None


def build_style_history(
    context: dict[str, Any],
    prior_contexts: Iterable[dict[str, Any]],
    *,
    limit: int = HISTORY_LIMIT,
    min_sessions: int = HISTORY_MIN_SESSIONS,
) -> dict[str, Any] | None:
    """Últimas sesiones previas comparables por estilo.

    Comparable = misma fuente (`polar_v4`), largos validados, misma piscina,
    mismo estilo, SWOLF validado, sin `too_few_lengths` y misma base temporal.
    Con menos de `min_sessions` se marca `too_few_sessions` y no se resume.
    Los mínimos son de presentación, no umbrales fisiológicos.
    """
    if context.get("swim_source") != "polar_v4" or context.get("length_validation_status") != "passed":
        return None
    current_date = str(context.get("session_date") or "")
    pool = context.get("pool_length_m")
    priors = [
        c for c in prior_contexts
        if str(c.get("session_date") or "") < current_date
        and c.get("pool_length_m") == pool
        and str(c.get("session_id")) != str(context.get("session_id"))
    ]
    priors.sort(key=lambda c: (str(c.get("session_date")), str(c.get("session_id"))), reverse=True)
    out: dict[str, Any] = {}
    for current in context.get("styles") or []:
        style = current.get("style")
        if _eligible_style(context, style) is None:
            continue
        rows = []
        for prior in priors:
            item = _eligible_style(prior, style)
            if item is None:
                continue
            rows.append({
                "session_date": prior.get("session_date"),
                "session_id": prior.get("session_id"),
                "swolf_polar": item.get("swolf_polar"),
                "pace_s_per_100m": item.get("pace_s_per_100m"),
                "n_lengths_validated": item.get("n_lengths_validated"),
            })
            if len(rows) >= limit:
                break
        entry: dict[str, Any] = {
            "pool_length_m": pool,
            "time_basis": HISTORY_TIME_BASIS,
            "n_prior_eligible": len(rows),
            "prior_sessions": rows,
            "too_few_sessions": len(rows) < min_sessions,
            "prior_swolf_median": None,
            "prior_pace_median_s_per_100m": None,
        }
        if not entry["too_few_sessions"]:
            swolfs = sorted(r["swolf_polar"] for r in rows if r["swolf_polar"] is not None)
            paces = sorted(r["pace_s_per_100m"] for r in rows if r["pace_s_per_100m"] is not None)
            entry["prior_swolf_median"] = _round(_median(swolfs), 2)
            entry["prior_pace_median_s_per_100m"] = _round(_median(paces), 2)
        out[style] = entry
    return {
        "basis": "mismo estilo, piscina, fuente polar_v4 y base temporal; ultimas sesiones previas elegibles",
        "limit": limit,
        "min_sessions": min_sessions,
        "prior_contexts_considered": len(priors),
        "by_stroke": out or None,
    }


def _median(values: list[float]) -> float | None:
    if not values:
        return None
    mid = len(values) // 2
    return values[mid] if len(values) % 2 else (values[mid - 1] + values[mid]) / 2.0


# ---------------------------------------------------------------------------
# Escritura de artefactos
# ---------------------------------------------------------------------------

def _write_csv(path: Path, columns: list[str], rows: list[dict[str, Any]]) -> Path | None:
    if not rows:
        return None
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({key: ("" if row.get(key) is None else row.get(key)) for key in columns})
    tmp.replace(path)
    return path


def write_swim_phases_csv(path: Path, rows: list[dict[str, Any]]) -> Path | None:
    return _write_csv(path, PHASE_COLUMNS, rows)


def write_swim_laps_csv(path: Path, rows: list[dict[str, Any]]) -> Path | None:
    return _write_csv(path, LAP_COLUMNS, rows)
