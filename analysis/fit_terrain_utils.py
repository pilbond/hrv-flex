#!/usr/bin/env python3
from __future__ import annotations

import bisect
import math
import sys
from itertools import pairwise
from pathlib import Path
from statistics import mean, median
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from hrv_app.polar_utils import parse_float, weighted_mean as _weighted_mean

try:
    from fitparse import FitFile
except Exception:  # pragma: no cover - optional import at runtime
    FitFile = None


# Empirical defaults for the local road-cycling proxy model.
# They stay local to this module because they are tuning constants, not canonically measured session fields.
_ROAD_CRR  = 0.004
_ROAD_CDA  = 0.35
_AIR_RHO   = 1.2
_DRIVE_ETA = 0.97
_G         = 9.81

ALTITUDE_MEDIAN_WINDOW = 11
GRADE_WINDOW_SEC = 10.0
VERTICAL_DEADBAND_M = 0.5
CLIMB_MIN_GRADE = 0.03
CLIMB_MIN_DURATION_S = 60.0
# Umbrales de detección de subidas por familia de deporte.
# bike: criterios basados en Strava (300 m, producto 800, merge 60 s).
# road/run/trail/hike: más permisivos — subidas cortas y empinadas son
#   fisiológicamente relevantes en deportes de pie.
# Nota: "road" es el valor que devuelve analyzer_sport_from_session para
#   road_run; se mapea explícitamente para no caer en el default bike.
_CLIMB_THRESHOLDS: dict[str, dict[str, float]] = {
    "bike": {
        "min_distance_m":    300.0,
        "min_gain_m":         10.0,
        "min_product":       800.0,   # dist_m × grade_pct
        "merge_gap_s":        60.0,
        "merge_elev_loss_m":   5.0,
    },
    "trail": {
        "min_distance_m":    150.0,
        "min_gain_m":         10.0,
        "min_product":       300.0,
        "merge_gap_s":        30.0,
        "merge_elev_loss_m":   5.0,
    },
    "run": {
        "min_distance_m":    150.0,
        "min_gain_m":         10.0,
        "min_product":       300.0,
        "merge_gap_s":        30.0,
        "merge_elev_loss_m":   5.0,
    },
    "hike": {
        "min_distance_m":    150.0,
        "min_gain_m":         10.0,
        "min_product":       200.0,
        "merge_gap_s":        60.0,
        "merge_elev_loss_m":   8.0,
    },
}
# "road" (road_run via analyzer_sport_from_session) usa los mismos umbrales que "run".
# Copia explícita para evitar aliasing mutable: ajustar "road" o "run" en el futuro
# no afectará al otro.
_CLIMB_THRESHOLDS["road"] = _CLIMB_THRESHOLDS["run"].copy()
_CLIMB_THRESHOLDS_DEFAULT = _CLIMB_THRESHOLDS["bike"]

_CLIMB_GROUP_THRESHOLDS: dict[str, dict[str, float]] = {
    "bike": {
        "merge_gap_s": 75.0,
    },
    "trail": {
        "merge_gap_s": 120.0,
    },
    "run": {
        "merge_gap_s": 120.0,
    },
    "road": {
        "merge_gap_s": 120.0,
    },
    "hike": {
        "merge_gap_s": 150.0,
    },
}
_CLIMB_GROUP_THRESHOLDS_DEFAULT = _CLIMB_GROUP_THRESHOLDS["bike"]


def _climb_thresholds(sport_family: str | None) -> dict[str, float]:
    return _CLIMB_THRESHOLDS.get(sport_family or "", _CLIMB_THRESHOLDS_DEFAULT)


def _climb_group_thresholds(sport_family: str | None) -> dict[str, float]:
    return _CLIMB_GROUP_THRESHOLDS.get(sport_family or "", _CLIMB_GROUP_THRESHOLDS_DEFAULT)


PAUSE_SPEED_THRESHOLD_MPS = 0.2
PAUSE_DISTANCE_STALL_M = 0.5
LOW_SESSION_GAIN_NOT_APPLICABLE_M = 50.0
MIN_GAIN_COVERAGE_PCT = 30.0
HIGH_COVERAGE_INFORMATIVE_PCT = 80.0


def _select_altitude_value(values: dict[str, Any]) -> float | None:
    enhanced = parse_float(values.get("enhanced_altitude"))
    if enhanced is not None:
        return enhanced
    return parse_float(values.get("altitude"))


def _moving_median(values: list[float], window_size: int) -> list[float]:
    if not values:
        return []
    radius = max(0, window_size // 2)
    smoothed: list[float] = []
    for idx in range(len(values)):
        start = max(0, idx - radius)
        end = min(len(values), idx + radius + 1)
        smoothed.append(float(median(values[start:end])))
    return smoothed


def _mark_heuristic_pauses(records: list[dict[str, Any]]) -> None:
    prev_distance = None
    for row in records:
        distance = parse_float(row.get("distance_m"))
        speed = parse_float(row.get("speed_mps"))
        delta_distance = None
        if distance is not None and prev_distance is not None:
            delta_distance = max(0.0, distance - prev_distance)
        is_paused = bool(
            speed is not None
            and speed < PAUSE_SPEED_THRESHOLD_MPS
            and delta_distance is not None
            and delta_distance <= PAUSE_DISTANCE_STALL_M
        )
        row["paused"] = is_paused
        prev_distance = distance if distance is not None else prev_distance


def _extract_pause_intervals(fit: Any, start_ts: Any) -> list[tuple[float, float]]:
    if start_ts is None:
        return []
    intervals: list[tuple[float, float]] = []
    pause_start = None
    for msg in fit.get_messages("event"):
        values = {field.name: field.value for field in msg}
        if str(values.get("event") or "").strip().lower() != "timer":
            continue
        timestamp = values.get("timestamp")
        if timestamp is None:
            continue
        event_type = str(values.get("event_type") or "").strip().lower()
        sec = (timestamp - start_ts).total_seconds()
        if event_type in {"stop", "stop_all"}:
            pause_start = sec
        elif event_type in {"start", "start_all"} and pause_start is not None and sec > pause_start:
            intervals.append((pause_start, sec))
            pause_start = None
    return intervals


def parse_fit_terrain_data(fit_path: str | Path) -> dict[str, Any]:
    if FitFile is None:
        raise RuntimeError("fitparse is not installed")

    fit = FitFile(str(fit_path))
    session_msg = next(iter(fit.get_messages("session")), None)
    session_meta = {}
    if session_msg is not None:
        session_values = {field.name: field.value for field in session_msg}
        session_meta = {
            "total_timer_time_s": parse_float(session_values.get("total_timer_time")),
            "total_elapsed_time_s": parse_float(session_values.get("total_elapsed_time")),
            "total_distance_m": parse_float(session_values.get("total_distance")),
            "total_ascent_m": parse_float(session_values.get("total_ascent")),
            "total_descent_m": parse_float(session_values.get("total_descent")),
            "avg_hr": parse_float(session_values.get("avg_heart_rate")),
            "max_hr": parse_float(session_values.get("max_heart_rate")),
            "avg_running_cadence": parse_float(session_values.get("avg_running_cadence")),
        }

    raw_rows: list[dict[str, Any]] = []
    start_ts = None
    for msg in fit.get_messages("record"):
        values = {field.name: field.value for field in msg}
        timestamp = values.get("timestamp")
        if timestamp is None:
            continue
        if start_ts is None:
            start_ts = timestamp
        sec = (timestamp - start_ts).total_seconds()
        speed_mps = parse_float(values.get("enhanced_speed"))
        if speed_mps is None:
            speed_mps = parse_float(values.get("speed"))
        raw_rows.append(
            {
                "sec": float(sec),
                "distance_m": parse_float(values.get("distance")),
                "altitude_m": _select_altitude_value(values),
                "speed_mps": speed_mps,
                "speed_kmh": round(speed_mps * 3.6, 3) if speed_mps is not None else None,
                "hr": parse_float(values.get("heart_rate")),
                "cadence": parse_float(values.get("cadence")),
                "power": parse_float(values.get("power")),
                "paused": False,
            }
        )

    if not raw_rows:
        raise RuntimeError("FIT file contains no record messages")

    pause_intervals = _extract_pause_intervals(fit, start_ts)
    if pause_intervals:
        for row in raw_rows:
            sec = row["sec"]
            row["paused"] = any(start <= sec <= end for start, end in pause_intervals)
        pause_filter_mode = "fit_event"
    else:
        _mark_heuristic_pauses(raw_rows)
        pause_filter_mode = "heuristic_stationary"

    return {
        "records": raw_rows,
        "session_meta": session_meta,
        "pause_filter_mode": pause_filter_mode,
    }


def _prepare_active_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    active = [
        dict(row)
        for row in records
        if not row.get("paused")
        and parse_float(row.get("distance_m")) is not None
        and parse_float(row.get("altitude_m")) is not None
    ]
    if len(active) < 2:
        return []

    smoothed = _moving_median([float(row["altitude_m"]) for row in active], ALTITUDE_MEDIAN_WINDOW)
    secs = [float(row["sec"]) for row in active]
    half_window = GRADE_WINDOW_SEC / 2.0
    for idx, row in enumerate(active):
        row["altitude_smooth_m"] = smoothed[idx]
        left_idx = bisect.bisect_left(secs, secs[idx] - half_window)
        right_idx = bisect.bisect_right(secs, secs[idx] + half_window) - 1
        if right_idx <= left_idx:
            row["grade"] = None
            continue
        distance_span = float(active[right_idx]["distance_m"]) - float(active[left_idx]["distance_m"])
        if distance_span <= 0:
            row["grade"] = None
            continue
        altitude_span = smoothed[right_idx] - smoothed[left_idx]
        if abs(altitude_span) < VERTICAL_DEADBAND_M:
            altitude_span = 0.0
        row["grade"] = altitude_span / distance_span
    return active


def _segment_elev_loss(records: list[dict[str, Any]]) -> float:
    loss = 0.0
    for prev_row, row in pairwise(records):
        delta = float(row["altitude_smooth_m"]) - float(prev_row["altitude_smooth_m"])
        if delta < 0:
            loss += -delta
    return loss


def _estimate_climb_power_w(
    distance_m: float,
    duration_s: float,
    elev_gain_m: float,
    system_bike_weight_kg: float,
) -> float | None:
    """Estima la potencia mecánica total necesaria para mover el sistema completo
    (atleta + bicicleta + equipamiento) por la subida descrita.

    Retorna vatios en la rueda (tras pérdidas de transmisión ETA).

    Convención de display: cuando se expresa como W/kg, el denominador es SIEMPRE
    la masa corporal del atleta (ATHLETE_WEIGHT_KG), no la masa del sistema. Esto
    sigue el estándar del sector (Strava, TrainingPeaks, WKO). Los vatios reflejan
    el esfuerzo real para mover el sistema completo; el W/kg atleta es el índice
    de rendimiento relativo a la masa corporal, que es independiente del equipo.
    """
    if duration_s <= 0 or distance_m <= 0:
        return None
    speed_mps = distance_m / duration_s
    grade_pct = elev_gain_m / distance_m * 100.0
    theta     = math.atan(grade_pct / 100.0)
    p_grav    = system_bike_weight_kg * _G * math.sin(theta) * speed_mps
    p_roll    = _ROAD_CRR * system_bike_weight_kg * _G * math.cos(theta) * speed_mps
    p_aero    = 0.5 * _AIR_RHO * _ROAD_CDA * speed_mps ** 3
    return (p_grav + p_roll + p_aero) / _DRIVE_ETA


def _summarize_climb_rows(
    climb_index: int,
    rows: list[dict[str, Any]],
    system_bike_weight_kg: float | None = None,
    vt1: float | None = None,
    vt2: float | None = None,
) -> dict[str, Any]:
    start = rows[0]
    end = rows[-1]
    duration_s = max(0.0, float(end["sec"]) - float(start["sec"]))
    distance_m = max(0.0, float(end["distance_m"]) - float(start["distance_m"]))
    elev_gain_m = max(0.0, float(end["altitude_smooth_m"]) - float(start["altitude_smooth_m"]))
    # Net grade of the detected climb segment; not the arithmetic mean of sample grades.
    grade_mean_pct = (elev_gain_m / distance_m * 100.0) if distance_m > 0 else None
    vam_mh = (elev_gain_m / (duration_s / 3600.0)) if duration_s > 0 and elev_gain_m > 0 else None

    hr_values = [float(row["hr"]) for row in rows if parse_float(row.get("hr")) is not None]
    cadence_values = [float(row["cadence"]) for row in rows if parse_float(row.get("cadence")) is not None]
    power_values = [float(row["power"]) for row in rows if parse_float(row.get("power")) is not None]

    power_estimated = None
    if not power_values and system_bike_weight_kg is not None:
        power_estimated = _estimate_climb_power_w(distance_m, duration_s, elev_gain_m, system_bike_weight_kg)

    z1_pct: float | None = None
    z2_pct: float | None = None
    z3_pct: float | None = None
    if vt1 is not None and vt2 is not None and len(rows) >= 2:
        z1_s = z2_s = z3_s = 0.0
        for prev, curr in zip(rows, rows[1:]):
            interval_s = float(curr["sec"]) - float(prev["sec"])
            hr = parse_float(curr.get("hr"))
            if hr is None or interval_s <= 0:
                continue
            if hr < vt1:
                z1_s += interval_s
            elif hr < vt2:
                z2_s += interval_s
            else:
                z3_s += interval_s
        total_zone_s = z1_s + z2_s + z3_s
        if total_zone_s > 0:
            z1_pct = round(z1_s / total_zone_s * 100.0, 1)
            z2_pct = round(z2_s / total_zone_s * 100.0, 1)
            z3_pct = round(z3_s / total_zone_s * 100.0, 1)

    return {
        "climb_index": climb_index,
        "start_sec": round(float(start["sec"]), 1),
        "end_sec": round(float(end["sec"]), 1),
        "duration_s": round(duration_s, 1),
        "distance_km": round(distance_m / 1000.0, 3),
        "elev_gain_m": round(elev_gain_m, 1),
        "grade_mean_pct": round(grade_mean_pct, 1) if grade_mean_pct is not None else None,
        "vam_mh": round(vam_mh, 1) if vam_mh is not None else None,
        "hr_mean": round(sum(hr_values) / len(hr_values), 1) if hr_values else None,
        "hr_max": round(max(hr_values), 1) if hr_values else None,
        "cadence_mean": round(sum(cadence_values) / len(cadence_values), 1) if cadence_values else None,
        "power_mean": round(sum(power_values) / len(power_values), 1) if power_values else None,
        "power_max": round(max(power_values), 1) if power_values else None,
        "power_estimated_mean": round(power_estimated, 1) if power_estimated is not None else None,
        "power_source": "measured" if power_values else ("estimated" if power_estimated is not None else None),
        "z1_pct": z1_pct,
        "z2_pct": z2_pct,
        "z3_pct": z3_pct,
        "hr_available": bool(hr_values),
        "cadence_available": bool(cadence_values),
        "power_available": bool(power_values),
    }


def _detect_climb_rows(
    active_records: list[dict[str, Any]],
    system_bike_weight_kg: float | None = None,
    vt1: float | None = None,
    vt2: float | None = None,
    sport_family: str | None = None,
) -> list[dict[str, Any]]:
    thr = _climb_thresholds(sport_family)
    raw_segments: list[tuple[int, int]] = []
    start_idx = None
    for idx, row in enumerate(active_records):
        is_climb = parse_float(row.get("grade")) is not None and float(row["grade"]) >= CLIMB_MIN_GRADE
        if is_climb and start_idx is None:
            start_idx = idx
        elif not is_climb and start_idx is not None:
            raw_segments.append((start_idx, idx - 1))
            start_idx = None
    if start_idx is not None:
        raw_segments.append((start_idx, len(active_records) - 1))
    if not raw_segments:
        return []

    merged_segments: list[tuple[int, int]] = [raw_segments[0]]
    for seg_start, seg_end in raw_segments[1:]:
        prev_start, prev_end = merged_segments[-1]
        gap_rows = active_records[prev_end : seg_start + 1]
        gap_duration_s = float(active_records[seg_start]["sec"]) - float(active_records[prev_end]["sec"])
        gap_elev_loss_m = _segment_elev_loss(gap_rows)
        if gap_duration_s <= thr["merge_gap_s"] and gap_elev_loss_m <= thr["merge_elev_loss_m"]:
            merged_segments[-1] = (prev_start, seg_end)
        else:
            merged_segments.append((seg_start, seg_end))

    climbs: list[dict[str, Any]] = []
    for seg_start, seg_end in merged_segments:
        climb_rows = active_records[seg_start : seg_end + 1]
        climb = _summarize_climb_rows(len(climbs) + 1, climb_rows, system_bike_weight_kg, vt1, vt2)
        dist_m = (parse_float(climb.get("distance_km")) or 0.0) * 1000.0
        grade_pct = parse_float(climb.get("grade_mean_pct")) or 0.0
        if (
            parse_float(climb.get("duration_s")) is not None
            and float(climb["duration_s"]) >= CLIMB_MIN_DURATION_S
            and dist_m >= thr["min_distance_m"]
            and parse_float(climb.get("elev_gain_m")) is not None
            and float(climb["elev_gain_m"]) >= thr["min_gain_m"]
            and dist_m * grade_pct >= thr["min_product"]
        ):
            climbs.append(climb)
    return climbs


def _climb_power_value(row: dict[str, Any]) -> float | None:
    measured = parse_float(row.get("power_mean"))
    if measured is not None:
        return measured
    return parse_float(row.get("power_estimated_mean"))


def _summarize_climb_group(
    group_index: int,
    climbs: list[dict[str, Any]],
    sport_family: str | None = None,
) -> dict[str, Any]:
    start = climbs[0]
    end = climbs[-1]
    duration_s = sum(parse_float(row.get("duration_s")) or 0.0 for row in climbs)
    distance_km = sum(parse_float(row.get("distance_km")) or 0.0 for row in climbs)
    elev_gain_m = sum(parse_float(row.get("elev_gain_m")) or 0.0 for row in climbs)
    grade_mean_pct = (elev_gain_m / distance_km * 100.0) if distance_km > 0 else None
    vam_mh = (elev_gain_m / (duration_s / 3600.0)) if duration_s > 0 and elev_gain_m > 0 else None

    hr_mean = _weighted_mean(climbs, "hr_mean", "duration_s")
    cadence_mean = _weighted_mean(climbs, "cadence_mean", "duration_s")
    z1_pct = _weighted_mean(climbs, "z1_pct", "duration_s")
    z2_pct = _weighted_mean(climbs, "z2_pct", "duration_s")
    z3_pct = _weighted_mean(climbs, "z3_pct", "duration_s")
    hr_max_values = [
        parse_float(row.get("hr_max"))
        for row in climbs
        if parse_float(row.get("hr_max")) is not None
    ]

    power_rows = []
    measured_count = 0
    estimated_count = 0
    for row in climbs:
        power_value = _climb_power_value(row)
        if power_value is None:
            continue
        power_rows.append({**row, "_group_power_value": power_value})
        if row.get("power_source") == "measured":
            measured_count += 1
        elif row.get("power_source") == "estimated":
            estimated_count += 1

    power_mean = _weighted_mean(power_rows, "_group_power_value", "duration_s")
    power_max_values = [
        parse_float(row.get("power_max"))
        for row in climbs
        if parse_float(row.get("power_max")) is not None
    ]
    power_max = max(power_max_values) if power_max_values else None
    power_estimated_mean_values = [
        parse_float(row.get("power_estimated_mean"))
        for row in climbs
        if parse_float(row.get("power_estimated_mean")) is not None
    ]
    power_estimated_mean = (
        round(sum(power_estimated_mean_values) / len(power_estimated_mean_values), 1)
        if power_estimated_mean_values
        else None
    )
    if measured_count > 0 and estimated_count > 0:
        power_source = "mixed"
    elif measured_count > 0:
        power_source = "measured"
    elif estimated_count > 0:
        power_source = "estimated"
    else:
        power_source = None

    member_indices = [
        int(parse_float(row.get("climb_index")) or idx + 1)
        for idx, row in enumerate(climbs)
    ]

    return {
        "group_index": group_index,
        "climb_count": len(climbs),
        "member_climb_indices": member_indices,
        "start_sec": round(float(start["start_sec"]), 1) if start.get("start_sec") is not None else None,
        "end_sec": round(float(end["end_sec"]), 1) if end.get("end_sec") is not None else None,
        "duration_s": round(duration_s, 1),
        "distance_km": round(distance_km, 3),
        "elev_gain_m": round(elev_gain_m, 1),
        "grade_mean_pct": round(grade_mean_pct, 1) if grade_mean_pct is not None else None,
        "vam_mh": round(vam_mh, 1) if vam_mh is not None else None,
        "hr_mean": round(hr_mean, 1) if hr_mean is not None else None,
        "hr_max": max(hr_max_values) if hr_max_values else None,
        "cadence_mean": round(cadence_mean, 1) if cadence_mean is not None else None,
        "power_mean": round(power_mean, 1) if power_mean is not None else None,
        "power_max": round(power_max, 1) if power_max is not None else None,
        "power_estimated_mean": power_estimated_mean,
        "power_source": power_source,
        "z1_pct": round(z1_pct, 1) if z1_pct is not None else None,
        "z2_pct": round(z2_pct, 1) if z2_pct is not None else None,
        "z3_pct": round(z3_pct, 1) if z3_pct is not None else None,
        "sport_family": sport_family,
        "merge_gap_s": _climb_group_thresholds(sport_family)["merge_gap_s"],
    }


def group_terrain_climbs(
    terrain_climbs: list[dict[str, Any]],
    sport_family: str | None = None,
) -> list[dict[str, Any]]:
    if len(terrain_climbs) < 2:
        return [
            _summarize_climb_group(1, terrain_climbs, sport_family=sport_family)
        ] if terrain_climbs else []

    thresholds = _climb_group_thresholds(sport_family)
    sorted_climbs = sorted(
        terrain_climbs,
        key=lambda row: (
            parse_float(row.get("start_sec")) if parse_float(row.get("start_sec")) is not None else float("inf"),
            parse_float(row.get("end_sec")) if parse_float(row.get("end_sec")) is not None else float("inf"),
        ),
    )

    groups: list[list[dict[str, Any]]] = [[sorted_climbs[0]]]
    for climb in sorted_climbs[1:]:
        prev = groups[-1][-1]
        prev_end = parse_float(prev.get("end_sec"))
        cur_start = parse_float(climb.get("start_sec"))
        gap_s = None
        if prev_end is not None and cur_start is not None:
            gap_s = cur_start - prev_end
        if gap_s is not None and gap_s <= thresholds["merge_gap_s"]:
            groups[-1].append(climb)
        else:
            groups.append([climb])

    return [
        _summarize_climb_group(idx + 1, climbs, sport_family=sport_family)
        for idx, climbs in enumerate(groups)
    ]


def _signals_available(rows: list[dict[str, Any]]) -> dict[str, bool]:
    return {
        "hr": any(parse_float(row.get("hr")) is not None for row in rows),
        "cadence": any(parse_float(row.get("cadence")) is not None for row in rows),
        "power": any(parse_float(row.get("power")) is not None for row in rows),
    }


def _session_altitude_context(rows: list[dict[str, Any]]) -> dict[str, Any]:
    altitude_rows = [row for row in rows if parse_float(row.get("altitude_m")) is not None]
    if not altitude_rows:
        return {}

    altitude_values = [float(parse_float(row.get("altitude_m")) or 0.0) for row in altitude_rows]
    start_altitude_m = float(altitude_values[0])
    end_altitude_m = float(altitude_values[-1])
    return {
        "session_altitude_m": round(mean(altitude_values), 1),
        "session_altitude_start_m": round(start_altitude_m, 1),
        "session_altitude_end_m": round(end_altitude_m, 1),
        "session_altitude_min_m": round(min(altitude_values), 1),
        "session_altitude_max_m": round(max(altitude_values), 1),
        "session_altitude_range_m": round(max(altitude_values) - min(altitude_values), 1),
        "session_altitude_samples": len(altitude_values),
    }


def _power_mean_from_fit_records(
    fit_records: list[dict[str, Any]] | None,
    start_sec: float | None,
    end_sec: float | None,
) -> float | None:
    if not fit_records or start_sec is None or end_sec is None:
        return None

    values: list[float] = []
    for row in fit_records:
        sec = parse_float(row.get("sec"))
        power = parse_float(row.get("power"))
        if sec is None or power is None:
            continue
        if start_sec <= sec < end_sec:
            values.append(power)
    if not values:
        return None
    return sum(values) / len(values)


def _build_validation_vs_v2(
    terrain_context: dict[str, Any] | None,
    terrain_intervals: list[dict[str, Any]] | None,
    session_gain_m: float | None,
    climb_time_min: float,
    climb_gain_m: float,
    climb_distance_km: float,
    climb_gain_coverage_pct: float | None,
) -> dict[str, Any]:
    checks: dict[str, Any] = {}
    warnings: list[str] = []
    infos: list[str] = []
    terrain_context = terrain_context if isinstance(terrain_context, dict) else {}
    terrain_intervals = terrain_intervals if isinstance(terrain_intervals, list) else []
    uphill_rows = [row for row in terrain_intervals if row.get("terrain_class") == "uphill"]
    reference_time_min = parse_float(terrain_context.get("vam_uphill_time_min"))
    reference_gain_m = sum(
        parse_float(row.get("elev_gain_m")) or 0.0
        for row in terrain_intervals
        if (parse_float(row.get("elev_gain_m")) or 0.0) > 0.0
    )
    reference_distance_km = sum(parse_float(row.get("distance_km")) or 0.0 for row in uphill_rows)

    high_coverage = climb_gain_coverage_pct is not None and climb_gain_coverage_pct >= HIGH_COVERAGE_INFORMATIVE_PCT

    if reference_time_min is not None:
        exceeds = climb_time_min > reference_time_min + 1.0
        if exceeds and high_coverage:
            checks["time_upper_bound"] = {
                "passed": True,
                "direction": "<=",
                "observed": round(climb_time_min, 1),
                "reference": round(reference_time_min, 1),
                "tolerance": 1.0,
                "comparison": "v3_exceeds_v2_high_coverage",
            }
            infos.append("info_v3_time_exceeds_v2_high_coverage")
        else:
            passed = not exceeds
            checks["time_upper_bound"] = {
                "passed": passed,
                "direction": "<=",
                "observed": round(climb_time_min, 1),
                "reference": round(reference_time_min, 1),
                "tolerance": 1.0,
            }
            if not passed:
                warnings.append("warn_climb_time_exceeds_v2")
    else:
        checks["time_upper_bound"] = {"passed": None, "reference": None}

    if reference_gain_m > 0:
        exceeds = climb_gain_m > reference_gain_m + 10.0
        if exceeds and high_coverage:
            checks["gain_upper_bound"] = {
                "passed": True,
                "direction": "<=",
                "observed": round(climb_gain_m, 1),
                "reference": round(reference_gain_m, 1),
                "tolerance": 10.0,
                "reference_scope": "all_positive_split_gain",
                "comparison": "v3_exceeds_v2_high_coverage",
            }
            infos.append("info_v3_gain_exceeds_v2_high_coverage")
        else:
            passed = not exceeds
            checks["gain_upper_bound"] = {
                "passed": passed,
                "direction": "<=",
                "observed": round(climb_gain_m, 1),
                "reference": round(reference_gain_m, 1),
                "tolerance": 10.0,
                "reference_scope": "all_positive_split_gain",
            }
            if not passed:
                warnings.append("warn_climb_gain_exceeds_v2")
    else:
        checks["gain_upper_bound"] = {"passed": None, "reference": None, "reference_scope": "all_positive_split_gain"}

    if uphill_rows:
        exceeds = climb_distance_km > reference_distance_km + 0.2
        if exceeds and high_coverage:
            checks["distance_upper_bound"] = {
                "passed": True,
                "direction": "<=",
                "observed": round(climb_distance_km, 3),
                "reference": round(reference_distance_km, 3),
                "tolerance": 0.2,
                "reference_scope": "uphill_split_distance",
                "comparison": "v3_exceeds_v2_high_coverage",
            }
            infos.append("info_v3_distance_exceeds_v2_high_coverage")
        else:
            passed = not exceeds
            checks["distance_upper_bound"] = {
                "passed": passed,
                "direction": "<=",
                "observed": round(climb_distance_km, 3),
                "reference": round(reference_distance_km, 3),
                "tolerance": 0.2,
                "reference_scope": "uphill_split_distance",
            }
            if not passed:
                warnings.append("warn_climb_distance_exceeds_v2")
    else:
        checks["distance_upper_bound"] = {"passed": None, "reference": None, "reference_scope": "uphill_split_distance"}

    if climb_gain_coverage_pct is not None:
        if session_gain_m is not None and session_gain_m < LOW_SESSION_GAIN_NOT_APPLICABLE_M:
            checks["coverage_lower_bound"] = {
                "passed": None,
                "applicable": False,
                "minimum": MIN_GAIN_COVERAGE_PCT,
                "reason": "low_session_gain",
            }
        else:
            coverage_passed = climb_gain_coverage_pct >= MIN_GAIN_COVERAGE_PCT
            checks["coverage_lower_bound"] = {
                "passed": coverage_passed,
                "applicable": True,
                "direction": ">=",
                "observed": round(climb_gain_coverage_pct, 1),
                "minimum": MIN_GAIN_COVERAGE_PCT,
            }
            if not coverage_passed:
                warnings.append("warn_low_climb_coverage")
    else:
        checks["coverage_lower_bound"] = {"passed": None, "applicable": False, "minimum": MIN_GAIN_COVERAGE_PCT}

    available = any(check.get("passed") is not None for check in checks.values())
    if not available:
        status = "not_available"
    elif warnings:
        status = "warn"
    else:
        status = "pass"
    return {
        "status": status,
        "warnings": warnings,
        "infos": infos,
        "climb_gain_coverage_pct": round(climb_gain_coverage_pct, 1) if climb_gain_coverage_pct is not None else None,
        "checks": checks,
    }


def analyze_terrain_records(
    records: list[dict[str, Any]],
    pause_filter_mode: str,
    session_elev_gain_m: float | None,
    terrain_context: dict[str, Any] | None = None,
    terrain_intervals: list[dict[str, Any]] | None = None,
    cadence_unit: str = "strides_per_min",
    system_bike_weight_kg: float | None = None,
    vt1: float | None = None,
    vt2: float | None = None,
    sport_family: str | None = None,
) -> dict[str, Any]:
    active_records = _prepare_active_records(records)
    if len(active_records) < 2:
        raise RuntimeError("fit terrain analysis requires at least 2 active records with distance and altitude")

    climb_rows = _detect_climb_rows(active_records, system_bike_weight_kg, vt1, vt2, sport_family)
    climb_time_min = round(sum(parse_float(row.get("duration_s")) or 0.0 for row in climb_rows) / 60.0, 1)
    climb_distance_km = float(round(sum((parse_float(row.get("distance_km")) or 0.0) for row in climb_rows), 3))
    climb_gain_m = float(round(sum((parse_float(row.get("elev_gain_m")) or 0.0) for row in climb_rows), 1))
    session_gain = session_elev_gain_m if session_elev_gain_m and session_elev_gain_m > 0 else None
    climb_gain_coverage_pct = None
    if session_gain:
        climb_gain_coverage_pct = (climb_gain_m / session_gain) * 100.0

    climb_hr_mean = _weighted_mean(climb_rows, "hr_mean", "duration_s")
    climb_cadence_mean = _weighted_mean(climb_rows, "cadence_mean", "duration_s")
    climb_power_mean = _weighted_mean(climb_rows, "power_mean", "duration_s")
    climb_z3_pct_mean = _weighted_mean(climb_rows, "z3_pct", "duration_s")
    climb_power_max = max((parse_float(row.get("power_max")) or 0.0 for row in climb_rows), default=0.0)
    if not any(parse_float(row.get("power_max")) is not None for row in climb_rows):
        climb_power_max = None

    n_measured = sum(1 for r in climb_rows if r.get("power_source") == "measured")
    n_estimated = sum(1 for r in climb_rows if r.get("power_source") == "estimated")
    if n_measured > 0 and n_estimated > 0:
        _power_source_agg = "mixed"
    elif n_measured > 0:
        _power_source_agg = "measured"
    elif n_estimated > 0:
        _power_source_agg = "estimated"
    else:
        _power_source_agg = None

    climb_power_est_mean: float | None = None
    climb_power_est_max: float | None = None
    if climb_rows:
        est_values = [(r["power_estimated_mean"], r["duration_s"]) for r in climb_rows if r.get("power_estimated_mean") is not None]
        if est_values:
            total_dur = sum(d for _, d in est_values)
            if total_dur > 0:
                climb_power_est_mean = round(sum(v * d for v, d in est_values) / total_dur, 1)
            climb_power_est_max = round(max(v for v, _ in est_values), 1)

    context = {
        "climbs_source": "fit_record_level",
        "climb_count": len(climb_rows),
        "climb_time_min": climb_time_min,
        "climb_distance_km": climb_distance_km,
        "climb_gain_m": climb_gain_m,
        **_session_altitude_context(active_records),
        "climb_gain_coverage_pct": round(climb_gain_coverage_pct, 1) if climb_gain_coverage_pct is not None else None,
        "climb_hr_mean": round(climb_hr_mean, 1) if climb_hr_mean is not None else None,
        "climb_cadence_mean": round(climb_cadence_mean, 1) if climb_cadence_mean is not None else None,
        "climb_power_mean": round(climb_power_mean, 1) if climb_power_mean is not None else None,
        "climb_power_max": round(climb_power_max, 1) if climb_power_max is not None else None,
        "climb_power_estimated_mean": climb_power_est_mean,
        "climb_power_estimated_max": climb_power_est_max,
        "climb_power_source": _power_source_agg,
        "climb_power_estimation_model": "road_climb_simple_v1",
        "climb_power_measured_count": n_measured,
        "climb_power_estimated_count": n_estimated,
        "climb_z3_pct_mean": round(climb_z3_pct_mean, 1) if climb_z3_pct_mean is not None else None,
        "cadence_unit": cadence_unit,
        "signals_available": _signals_available(active_records),
        "pause_filter_mode": pause_filter_mode,
    }
    context["validation_vs_v2"] = _build_validation_vs_v2(
        terrain_context=terrain_context,
        terrain_intervals=terrain_intervals,
        session_gain_m=session_elev_gain_m,
        climb_time_min=climb_time_min,
        climb_gain_m=climb_gain_m,
        climb_distance_km=climb_distance_km,
        climb_gain_coverage_pct=climb_gain_coverage_pct,
    )
    return {
        "terrain_fit_context": context,
        "terrain_climbs": climb_rows,
    }


def analyze_fit_climbs(
    fit_path: str | Path,
    session_row: dict[str, Any] | None = None,
    terrain_context: dict[str, Any] | None = None,
    terrain_intervals: list[dict[str, Any]] | None = None,
    cadence_unit: str = "strides_per_min",
    system_bike_weight_kg: float | None = None,
    vt1: float | None = None,
    vt2: float | None = None,
    sport_family: str | None = None,
) -> dict[str, Any]:
    parsed = parse_fit_terrain_data(fit_path)
    session_row = session_row if isinstance(session_row, dict) else {}
    session_elev_gain_m = parse_float(session_row.get("elev_gain_m"))
    if session_elev_gain_m is None:
        session_elev_gain_m = parse_float((parsed.get("session_meta") or {}).get("total_ascent_m"))
    return analyze_terrain_records(
        records=parsed["records"],
        pause_filter_mode=parsed["pause_filter_mode"],
        session_elev_gain_m=session_elev_gain_m,
        terrain_context=terrain_context,
        terrain_intervals=terrain_intervals,
        cadence_unit=cadence_unit,
        system_bike_weight_kg=system_bike_weight_kg,
        vt1=vt1,
        vt2=vt2,
        sport_family=sport_family,
    )


# ---------------------------------------------------------------------------
# FP-06 — Eficiencia contextual: matched_climbs early vs late
# ---------------------------------------------------------------------------

_GRADE_BINS: list[tuple[str, float, float]] = [
    ("low_grade",  3.0,  7.0),
    ("mid_grade",  7.0, 12.0),
    ("high_grade", 12.0, 100.0),
]

_RUN_SPORTS: frozenset[str] = frozenset({"trail_run", "road_run", "run", "trail", "road"})


def _classify_efficiency_pattern(
    vam_ratio: float | None,
    hr_drift_bpm: float | None,
    hr_per_vam_ratio: float | None,
) -> tuple[str, str]:
    if vam_ratio is None:
        return "mixed_signal", "low"

    vam_ok = vam_ratio >= 0.93
    vam_drop = vam_ratio < 0.90
    hr_stable = hr_drift_bpm is None or abs(hr_drift_bpm) <= 5.0
    hr_elevated = hr_drift_bpm is not None and hr_drift_bpm > 8.0
    cost_ok = hr_per_vam_ratio is None or hr_per_vam_ratio <= 1.04
    cost_elevated = hr_per_vam_ratio is not None and hr_per_vam_ratio > 1.07

    available = sum(x is not None for x in [vam_ratio, hr_drift_bpm, hr_per_vam_ratio])
    confidence = "moderate" if available >= 3 else "low"

    if vam_ok and hr_stable and cost_ok:
        return "stable_contextual_efficiency", confidence
    if vam_drop and hr_elevated and cost_elevated:
        return "repeatability_loss_in_climbs", confidence
    if cost_elevated and not vam_drop:
        return "cardiovascular_efficiency_drop", confidence
    if vam_drop and hr_stable and not cost_elevated:
        return "mechanical_efficiency_drop", confidence
    return "mixed_signal", "low"


def compute_matched_climbs_context(
    terrain_climbs: list[dict[str, Any]],
    sport_family: str | None = None,
) -> dict[str, Any]:
    """
    FP-06: compare early vs late climbs of similar grade to detect contextual efficiency drop.
    Only applicable for run sports with ≥2 climbs and at least one matched grade-bin pair.
    """

    def _not_applicable(reason: str, **extra: Any) -> dict[str, Any]:
        return {"applicable": False, "applicability_reason": reason, "comparison_mode": "matched_climbs", **extra}

    if len(terrain_climbs) < 2:
        return _not_applicable("fewer_than_2_climbs")

    if sport_family and sport_family not in _RUN_SPORTS:
        return _not_applicable("sport_not_applicable")

    start_secs = [s for c in terrain_climbs if (s := parse_float(c.get("start_sec"))) is not None]
    end_secs   = [s for c in terrain_climbs if (s := parse_float(c.get("end_sec")))   is not None]

    if not start_secs:
        return _not_applicable("no_timing_data")

    midpoint_sec = (min(start_secs) + (max(end_secs) if end_secs else max(start_secs))) / 2.0

    def _mean(climbs: list[dict[str, Any]], field: str) -> float | None:
        vals = [v for c in climbs if (v := parse_float(c.get(field))) is not None]
        return round(sum(vals) / len(vals), 2) if vals else None

    matched_groups: list[dict[str, Any]] = []

    for bin_name, grade_lo, grade_hi in _GRADE_BINS:
        bin_climbs = [
            c for c in terrain_climbs
            if c.get("hr_available")
            and parse_float(c.get("grade_mean_pct")) is not None
            and grade_lo <= float(c["grade_mean_pct"]) < grade_hi
        ]
        if len(bin_climbs) < 2:
            continue

        early = [c for c in bin_climbs if (parse_float(c.get("start_sec")) or 0.0) < midpoint_sec]
        late  = [c for c in bin_climbs if (parse_float(c.get("start_sec")) or 0.0) >= midpoint_sec]

        if not early or not late:
            continue

        early_hr    = _mean(early, "hr_mean")
        late_hr     = _mean(late,  "hr_mean")
        early_vam   = _mean(early, "vam_mh")
        late_vam    = _mean(late,  "vam_mh")
        early_power = _mean(early, "power_mean")
        late_power  = _mean(late,  "power_mean")

        hr_drift_bpm = (
            round(late_hr - early_hr, 1)
            if late_hr is not None and early_hr is not None else None
        )
        vam_ratio = (
            round(late_vam / early_vam, 3)
            if late_vam and early_vam else None
        )

        hr_per_vam_ratio = None
        if early_hr and early_vam and late_hr and late_vam:
            early_cost = early_hr / early_vam
            hr_per_vam_ratio = round((late_hr / late_vam) / early_cost, 3)

        power_per_hr_ratio = None
        if early_power and early_hr and late_power and late_hr:
            power_per_hr_ratio = round(
                (late_power / late_hr) / (early_power / early_hr), 3
            )

        matched_groups.append({
            "grade_bin": bin_name,
            "grade_range_pct": [grade_lo, grade_hi],
            "early_count": len(early),
            "late_count": len(late),
            "early_hr_mean": early_hr,
            "late_hr_mean": late_hr,
            "early_vam_mean": early_vam,
            "late_vam_mean": late_vam,
            "early_power_mean": early_power,
            "late_power_mean": late_power,
            "hr_drift_bpm": hr_drift_bpm,
            "vam_ratio": vam_ratio,
            "hr_per_vam_ratio": hr_per_vam_ratio,
            "power_per_hr_ratio": power_per_hr_ratio,
        })

    if not matched_groups:
        return _not_applicable("no_comparable_climb_pairs", climb_count=len(terrain_climbs))

    def _weighted_agg(key: str) -> float | None:
        weighted_total = 0.0
        weight_total = 0.0
        for g in matched_groups:
            value = g.get(key)
            if value is None:
                continue
            weight = float((g.get("early_count") or 0) + (g.get("late_count") or 0))
            if weight <= 0:
                continue
            weighted_total += float(value) * weight
            weight_total += weight
        return round(weighted_total / weight_total, 3) if weight_total else None

    agg_vam_ratio    = _weighted_agg("vam_ratio")
    agg_hr_drift     = _weighted_agg("hr_drift_bpm")
    agg_hr_per_vam   = _weighted_agg("hr_per_vam_ratio")
    agg_power_per_hr = _weighted_agg("power_per_hr_ratio")

    efficiency_pattern, interpretation_confidence = _classify_efficiency_pattern(
        agg_vam_ratio, agg_hr_drift, agg_hr_per_vam
    )

    return {
        "applicable": True,
        "applicability_reason": "matched_climb_pairs_found",
        "comparison_mode": "matched_climbs",
        "sport_family": sport_family,
        "climb_count": len(terrain_climbs),
        "matched_groups_count": len(matched_groups),
        "midpoint_sec": round(midpoint_sec, 1),
        "aggregate": {
            "vam_ratio": agg_vam_ratio,
            "hr_drift_bpm": round(agg_hr_drift, 1) if agg_hr_drift is not None else None,
            "hr_per_vam_ratio": agg_hr_per_vam,
            "power_per_hr_ratio": agg_power_per_hr,
        },
        "efficiency_pattern": efficiency_pattern,
        "interpretation_confidence": interpretation_confidence,
        "matched_groups": matched_groups,
    }
