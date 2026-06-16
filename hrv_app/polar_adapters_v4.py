from __future__ import annotations

"""
Adaptadores Polar v4 → modelo interno (AYO-13, Fase 1).

El "modelo interno" del proyecto es el shape v3 que ya consumen
`sleep_store` (claves snake_case tipo `sleep_start_time`, `deep_sleep`,
`heart_rate_variability_avg`) y `polar_sessions`/`hrv_sync_flow` (claves
kebab-case tipo `start-time`, `detailed-sport-info`, `samples` con
`sample-type`). v3 lo satisface con adaptador identidad; v4 se normaliza
aquí. Ningún consumidor canónico debe leer nombres de campos v4.

NOTA F0: los nombres de campos v4 marcados como candidatos son provisionales
(derivados de la doc pública). La matriz de paridad de Fase 0 con fixtures
reales cierra la lista; ajustar aquí si la captura real difiere.
"""

import re
from datetime import date as _date_type, timedelta
from typing import Any, Optional, TypedDict

# Duración estilo protobuf ("90s", "5460s", "28800.5s"): los ejemplos
# oficiales de /sleeps la usan aunque el swagger declare int64 ms.
_PROTO_DURATION_RE = re.compile(r"^(\d+(?:\.\d+)?)s$")

# Sin `features` las respuestas v4 solo traen fechas (ver polar_client_v4).
SLEEP_FEATURES = ["sleep-result", "sleep-score", "sleep-evaluation"]
NIGHTLY_FEATURES = ["samples"]


def next_day_iso(date_str: str) -> str:
    """Rango de query [day, day+1). Para training-sessions/list la promocion a
    datetime hace que from=to=mismo-dia sea una ventana de 0 segundos; para
    sleep/nightly es la unica forma validada en la captura F0. Los consumidores
    filtran por index_by_date/date_str, asi que un rango que devuelva dos dias
    es inocuo."""
    try:
        return (_date_type.fromisoformat(date_str) + timedelta(days=1)).isoformat()
    except ValueError:
        return date_str


class InternalSleep(TypedDict, total=False):
    """Subconjunto del shape v3 de /users/sleep/{date} que consume
    sleep_store._extract_sleep_fields (duraciones en segundos o ISO)."""

    date: str
    sleep_start_time: str
    sleep_end_time: str
    deep_sleep: Any
    rem_sleep: Any
    light_sleep: Any
    continuity: Any
    continuity_class: Any
    sleep_score: Any
    evaluation: Any


class InternalNightly(TypedDict, total=False):
    """Subconjunto del shape v3 de /users/nightly-recharge/{date} que
    consume sleep_store._extract_nightly_fields."""

    date: str
    heart_rate_variability_avg: Any
    heart_rate_avg: Any
    breathing_rate_avg: Any


class InternalExercise(TypedDict, total=False):
    """Subconjunto del shape v3 de /exercises que consumen
    polar_sessions.match_polar_exercise y hrv_sync_flow (kebab-case)."""

    id: Any
    # claves v3 reales: "start-time", "detailed-sport-info", "duration",
    # "samples" — se construyen como dict literal (kebab-case no es
    # identificador válido de TypedDict).


def _first(d: dict, *keys: str) -> Any:
    for key in keys:
        if key in d and d[key] is not None:
            return d[key]
    return None


def _get_path(d: Any, path: str) -> Any:
    """Acceso anidado tolerante: _get_path(item, "sleepResult.hypnogram.sleepStart")."""
    node = d
    for part in path.split("."):
        if not isinstance(node, dict):
            return None
        node = node.get(part)
    return node


def _first_path(d: dict, *paths: str) -> Any:
    """Como _first pero acepta rutas anidadas con puntos."""
    for path in paths:
        value = _get_path(d, path) if "." in path else (d.get(path) if isinstance(d, dict) else None)
        if value is not None:
            return value
    return None


def _phase_duration_value(value: Any) -> Any:
    """phaseDurations.{deep,rem,light} pueden venir como objeto
    `{"durationMillis": N}` (swagger) o como string protobuf `"90s"`
    (ejemplos oficiales de /sleeps). sleep_store espera un número
    (heurística ms/s/min) o una duración ISO PT...; un `"90s"` crudo no lo
    entiende, y convertirlo a número plano lo leería como minutos — por eso
    se normaliza a ISO `PT90S`."""
    if isinstance(value, dict):
        value = _first(value, "durationMillis", "duration_millis", "seconds", "minutes", "value")
    if isinstance(value, str):
        m = _PROTO_DURATION_RE.match(value.strip())
        if m:
            return f"PT{m.group(1)}S"
    return value


def v4_sleep_to_internal(item: Optional[dict]) -> Optional[dict]:
    """Esquema oficial v4: el item de nightSleeps anida sleepResult.hypnogram
    (sleepStart/sleepEnd), sleepScore (objeto con sleepScore) y
    sleepEvaluation (analysis con continuityIndex/continuityClass,
    phaseDurations con deep/rem/light). Se aceptan también los shapes planos
    provisionales como fallback hasta cerrar F0 con captura real."""
    if not isinstance(item, dict):
        return None
    out: dict[str, Any] = {}

    date = _first(item, "date", "sleepDate", "sleep_date")
    if date is not None:
        out["date"] = str(date)

    mapping = [
        ("sleep_start_time", ("sleepResult.hypnogram.sleepStart", "sleepStartTime", "sleep_start_time", "startTime")),
        ("sleep_end_time", ("sleepResult.hypnogram.sleepEnd", "sleepEndTime", "sleep_end_time", "endTime")),
        ("deep_sleep", ("sleepEvaluation.phaseDurations.deep", "deepSleep", "deep_sleep")),
        ("rem_sleep", ("sleepEvaluation.phaseDurations.rem", "remSleep", "rem_sleep")),
        ("light_sleep", ("sleepEvaluation.phaseDurations.light", "lightSleep", "light_sleep")),
        # Métricas autoritativas de Polar: si están, sleep_store las usa en
        # vez de recalcular duración/eficiencia desde fases y horas.
        ("asleep_duration", ("sleepEvaluation.asleepDuration",)),
        ("sleep_span", ("sleepEvaluation.sleepSpan",)),
        ("efficiency", ("sleepEvaluation.analysis.efficiencyPercent",)),
        ("continuity", ("sleepEvaluation.analysis.continuityIndex", "continuity")),
        ("continuity_class", ("sleepEvaluation.analysis.continuityClass", "continuityClass", "continuity_class")),
        ("evaluation", ("sleepEvaluation", "evaluation")),
    ]
    _duration_keys = ("deep_sleep", "rem_sleep", "light_sleep", "asleep_duration", "sleep_span")
    for internal_key, candidates in mapping:
        value = _first_path(item, *candidates)
        if value is not None:
            if internal_key in _duration_keys:
                value = _phase_duration_value(value)
                if value is None:
                    continue
            out[internal_key] = value

    # sleepScore es objeto en el esquema oficial ({"sleepScore": 82, ...}) y
    # número plano en el shape provisional.
    score = item.get("sleepScore")
    if isinstance(score, dict):
        score = _first(score, "sleepScore", "score")
    if score is None:
        score = item.get("sleep_score")
    if score is not None and not isinstance(score, dict):
        out["sleep_score"] = score

    return out or None


def v4_nightly_to_internal(item: Optional[dict]) -> Optional[dict]:
    """Esquema oficial v4: sleepResultDate, meanNightlyRecoveryRmssd,
    meanNightlyRecoveryRri, meanNightlyRecoveryRespirationInterval. Se
    mantienen los nombres planos provisionales como fallback."""
    if not isinstance(item, dict):
        return None
    out: dict[str, Any] = {}

    date = _first(item, "sleepResultDate", "date", "nightlyRechargeDate", "nightly_recharge_date")
    if date is not None:
        out["date"] = str(date)

    rmssd = _first(item, "meanNightlyRecoveryRmssd", "heartRateVariabilityAvg", "heart_rate_variability_avg", "hrvAvg")
    if rmssd is not None:
        out["heart_rate_variability_avg"] = rmssd

    # RRI medio: directo en v4 oficial; sleep_store lo lee como nightly_rri.
    rri = _first(item, "meanNightlyRecoveryRri")
    if rri is not None:
        out["nightly_rri"] = rri

    hr = _first(item, "heartRateAvg", "heart_rate_avg", "hrAvg")
    if hr is not None:
        out["heart_rate_avg"] = hr

    resp = _first(item, "breathingRateAvg", "breathing_rate_avg")
    if resp is None:
        # Oficial v4: intervalo respiratorio medio, no frecuencia. Se
        # convierte a respiraciones/min (ms si >60, segundos si no).
        interval = _first(item, "meanNightlyRecoveryRespirationInterval")
        if isinstance(interval, (int, float)) and interval > 0:
            resp = 60000.0 / interval if interval > 60 else 60.0 / interval
    if resp is not None:
        out["breathing_rate_avg"] = resp

    return out or None


def _rr_values_from_list(raw: Any) -> list[tuple[str, str]]:
    """Acepta entradas v4 oficiales (`{durationMillis, offline}`) y los
    shapes provisionales (`{value}`/`{rr}`/`{ppi}`/número plano).

    Devuelve pares (valor, offline) con offline "1"/"0". El flag de Polar es
    la primera capa de descarte de artefactos del contrato HRV: no puede
    perderse en el adaptador. Shapes sin flag → "0" (el chequeo fisiológico
    del consumidor sigue aplicando)."""
    if not isinstance(raw, list):
        return []
    values: list[tuple[str, str]] = []
    for entry in raw:
        if isinstance(entry, (int, float)):
            values.append((str(entry), "0"))
        elif isinstance(entry, dict):
            v = _first(entry, "durationMillis", "value", "rr", "rrMillis", "intervalMillis", "ppInterval", "ppi")
            if v is not None:
                values.append((str(v), "1" if entry.get("offline") else "0"))
    return values


def _v4_rr_samples_to_v3(item: dict) -> Optional[dict]:
    """Convierte samples RR v4 al formato v3 {"sample-type": "11",
    "data": "rr1,rr2,..."} más una máscara paralela "offline" ("0,1,...").

    Esquema oficial (swagger): exercise.samples.rrSamples[{durationMillis,
    offline}] y, en sesiones multideporte, samples.transitionRrSamples (los
    RR de las transiciones entre exercises; mismo schema). El shape v3 no
    tiene canal para el flag offline, así que viaja como extensión del
    adaptador: el gateway F5 debe fusionarla (OR) con el chequeo
    fisiológico de rango del consumidor.

    Se aceptan también shapes planos (`exercises[].rrSamples`, `rrSamples`
    en el nivel superior, `ppiSamples`) como fallback."""
    pairs: list[tuple[str, str]] = []

    # Shape oficial: exercises[].samples.{rrSamples,transitionRrSamples}
    exercises = item.get("exercises")
    if isinstance(exercises, list):
        for ex in exercises:
            if not isinstance(ex, dict):
                continue
            ex_pairs: list[tuple[str, str]] = []
            samples_obj = ex.get("samples")
            if isinstance(samples_obj, dict):
                ex_pairs = _rr_values_from_list(
                    _first(samples_obj, "rrSamples", "rr_samples", "trainingsessionRRSample")
                )
                # RR de transición (multideporte): se anexan tras los RR del
                # exercise; el orden fino intra-sesión es responsabilidad del
                # gateway si la captura real demuestra que importa.
                ex_pairs.extend(_rr_values_from_list(
                    _first(samples_obj, "transitionRrSamples", "transition_rr_samples")
                ))
            if not ex_pairs:
                # Fallback provisional: rrSamples directo en el exercise.
                # Solo si la ruta oficial no dio valores, para no duplicar.
                ex_pairs = _rr_values_from_list(
                    _first(ex, "rrSamples", "rr_samples", "trainingsessionRRSample")
                )
            pairs.extend(ex_pairs)

    # Fallback: rrSamples/ppiSamples en el nivel superior (shapes provisionales).
    if not pairs:
        pairs.extend(_rr_values_from_list(
            _first(item, "rrSamples", "rr_samples", "trainingsessionRRSample", "ppiSamples")
        ))

    if not pairs:
        return None
    return {
        "sample-type": "11",
        "data": ",".join(v for v, _off in pairs),
        "offline": ",".join(off for _v, off in pairs),
    }


def _duration_to_v3(duration: Any) -> Any:
    """v4 oficial expresa duration en milisegundos; v3 usa ISO 8601 (PT...).
    Si ya viene como string ISO se respeta."""
    if isinstance(duration, str):
        return duration
    if isinstance(duration, (int, float)) and duration >= 0:
        total_s = int(round(float(duration) / 1000.0))
        h, rem = divmod(total_s, 3600)
        m, s = divmod(rem, 60)
        parts = "PT"
        if h:
            parts += f"{h}H"
        if m:
            parts += f"{m}M"
        if s or parts == "PT":
            parts += f"{s}S"
        return parts
    return duration


def _sport_to_v3(sport: Any, sport_catalog: Optional[dict] = None) -> Any:
    """Resuelve `sport`/`sportReference` v4 al label v3 (p.ej. BODY_AND_MIND).

    Esquema oficial: `sport: {id: "22353647432"}` — el nombre humano vive en
    `/v4/sports/list`. Sin catálogo no podemos producir un label v3 fiable,
    así que devolvemos el id crudo y dejamos que el gateway de la fase de
    corte resuelva el nombre antes de pasar el filtro de deportes."""
    if isinstance(sport, dict):
        sport_id = _first(sport, "id", "sportId", "identifier")
        if sport_catalog and sport_id is not None and str(sport_id) in sport_catalog:
            return sport_catalog[str(sport_id)]
        # Shapes provisionales: si el objeto trae name/detailedSportInfo, se
        # respeta — útil para tests y para shapes legacy.
        labelled = _first(sport, "detailedSportInfo", "name", "sport")
        if labelled is not None:
            return labelled
        return sport_id
    return sport


def v4_session_to_internal(item: Optional[dict], sport_catalog: Optional[dict] = None) -> Optional[dict]:
    """Training session v4 → shape v3 de /exercises (kebab-case).

    Esquema oficial (swagger): `identifier`, `sport: {id}`, `startTime`,
    `stopTime`, `durationMillis`, `exercises[].samples.rrSamples[].durationMillis`.
    Para que el filtro v3 de deporte (BODY_AND_MIND, TRAIL_RUNNING…) siga
    funcionando hay que resolver `sport.id` con `sport_catalog` (cacheable
    desde `/v4/sports/list` en el gateway de F5)."""
    if not isinstance(item, dict):
        return None
    out: dict[str, Any] = {}

    session_id = _first(item, "identifier", "id", "trainingSessionId", "training_session_id")
    if isinstance(session_id, dict):
        session_id = _first(session_id, "id", "identifier", "value")
    if session_id is not None:
        out["id"] = session_id

    start_time = _first(item, "startTime", "start_time", "start-time")
    if start_time is not None:
        out["start-time"] = start_time

    sport_raw = _first(item, "detailedSportInfo", "detailed_sport_info", "sport", "sportReference", "sportProfile")
    if sport_raw is None:
        # El deporte puede vivir en el primer exercise anidado.
        exercises = item.get("exercises")
        if isinstance(exercises, list) and exercises and isinstance(exercises[0], dict):
            sport_raw = _first(exercises[0], "detailedSportInfo", "sport", "sportReference")
    sport = _sport_to_v3(sport_raw, sport_catalog=sport_catalog)
    if sport is not None:
        # Ambas variantes: hrv_sync_flow lee vía FIELD_SPORT (kebab primero),
        # pero polar_sessions.match_polar_exercise y polar_sport_raw leen
        # "detailed_sport_info" snake directamente — sin esta clave el filtro
        # de deporte se salta (sport vacío) y cualquier sesión matchea.
        out["detailed-sport-info"] = sport
        out["detailed_sport_info"] = sport

    duration = _first(item, "durationMillis", "duration")
    if duration is not None:
        out["duration"] = _duration_to_v3(duration)

    samples: list[dict] = []
    raw_samples = _first(item, "samples")
    if isinstance(raw_samples, list):
        # Si v4 ya entrega una lista de samples tipados, se pasa tal cual y
        # F0 decide si requiere mapeo de tipos.
        samples.extend(s for s in raw_samples if isinstance(s, dict))
    rr_sample = _v4_rr_samples_to_v3(item)
    if rr_sample is not None:
        samples.append(rr_sample)
    if samples:
        out["samples"] = samples

    return out or None


def index_by_date(items: list, date_keys: tuple[str, ...] = ("date", "sleepDate", "sleepResultDate", "nightlyRechargeDate")) -> dict[str, dict]:
    """Indexa una respuesta de rango v4 por fecha ISO (YYYY-MM-DD) para
    emular los lookups por fecha del flujo v3."""
    out: dict[str, dict] = {}
    for item in items or []:
        if not isinstance(item, dict):
            continue
        raw = _first(item, *date_keys)
        if raw is None:
            continue
        date_str = str(raw).strip()[:10]
        if date_str:
            out[date_str] = item
    return out
