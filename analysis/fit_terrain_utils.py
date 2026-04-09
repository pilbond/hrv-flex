#!/usr/bin/env python3
from __future__ import annotations

import bisect
import sys
from itertools import pairwise
from pathlib import Path
from statistics import median
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from polar_utils import parse_float, weighted_mean as _weighted_mean

try:
    from fitparse import FitFile
except Exception:  # pragma: no cover - optional import at runtime
    FitFile = None


ALTITUDE_MEDIAN_WINDOW = 11
GRADE_WINDOW_SEC = 10.0
VERTICAL_DEADBAND_M = 0.5
CLIMB_MIN_GRADE = 0.03
CLIMB_MIN_DURATION_S = 60.0
CLIMB_MIN_DISTANCE_M = 150.0
CLIMB_MIN_GAIN_M = 10.0
MERGE_MAX_GAP_S = 30.0
MERGE_MAX_ELEV_LOSS_M = 5.0
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


def _summarize_climb_rows(climb_index: int, rows: list[dict[str, Any]]) -> dict[str, Any]:
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
        "hr_available": bool(hr_values),
        "cadence_available": bool(cadence_values),
        "power_available": bool(power_values),
    }


def _detect_climb_rows(active_records: list[dict[str, Any]]) -> list[dict[str, Any]]:
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
        if gap_duration_s <= MERGE_MAX_GAP_S and gap_elev_loss_m <= MERGE_MAX_ELEV_LOSS_M:
            merged_segments[-1] = (prev_start, seg_end)
        else:
            merged_segments.append((seg_start, seg_end))

    climbs: list[dict[str, Any]] = []
    for seg_start, seg_end in merged_segments:
        climb_rows = active_records[seg_start : seg_end + 1]
        climb = _summarize_climb_rows(len(climbs) + 1, climb_rows)
        if (
            parse_float(climb.get("duration_s")) is not None
            and float(climb["duration_s"]) >= CLIMB_MIN_DURATION_S
            and parse_float(climb.get("distance_km")) is not None
            and float(climb["distance_km"]) * 1000.0 >= CLIMB_MIN_DISTANCE_M
            and parse_float(climb.get("elev_gain_m")) is not None
            and float(climb["elev_gain_m"]) >= CLIMB_MIN_GAIN_M
        ):
            climbs.append(climb)
    return climbs


def _signals_available(rows: list[dict[str, Any]]) -> dict[str, bool]:
    return {
        "hr": any(parse_float(row.get("hr")) is not None for row in rows),
        "cadence": any(parse_float(row.get("cadence")) is not None for row in rows),
        "power": any(parse_float(row.get("power")) is not None for row in rows),
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
) -> dict[str, Any]:
    active_records = _prepare_active_records(records)
    if len(active_records) < 2:
        raise RuntimeError("fit terrain analysis requires at least 2 active records with distance and altitude")

    climb_rows = _detect_climb_rows(active_records)
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
    climb_power_max = max((parse_float(row.get("power_max")) or 0.0 for row in climb_rows), default=0.0)
    if not any(parse_float(row.get("power_max")) is not None for row in climb_rows):
        climb_power_max = None

    context = {
        "climbs_source": "fit_record_level",
        "climb_count": len(climb_rows),
        "climb_time_min": climb_time_min,
        "climb_distance_km": climb_distance_km,
        "climb_gain_m": climb_gain_m,
        "climb_gain_coverage_pct": round(climb_gain_coverage_pct, 1) if climb_gain_coverage_pct is not None else None,
        "climb_hr_mean": round(climb_hr_mean, 1) if climb_hr_mean is not None else None,
        "climb_cadence_mean": round(climb_cadence_mean, 1) if climb_cadence_mean is not None else None,
        "climb_power_mean": round(climb_power_mean, 1) if climb_power_mean is not None else None,
        "climb_power_max": round(climb_power_max, 1) if climb_power_max is not None else None,
        "cadence_unit": "strides_per_min",
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
    )
