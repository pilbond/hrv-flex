from __future__ import annotations

import csv
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

import requests

from .cli_reporting import _print_header
from .config import INTERVALS_BASE_URL, INTERVALS_FIELD_MAP, MASTER_CSV_COLS
from .oauth_utils import build_basic_auth_header
from .polar_utils import _parse_yyyy_mm_dd, parse_float


def _intervals_api_root() -> str:
    base = (INTERVALS_BASE_URL or "https://intervals.icu").strip().rstrip("/")
    if not base:
        base = "https://intervals.icu"
    base = re.sub(r"/api/v1/?$", "", base, flags=re.IGNORECASE)
    return f"{base}/api/v1"


def _normalize_color_value(raw_value: str) -> Optional[int]:
    if raw_value is None:
        return None
    value = str(raw_value).strip().lower()
    if not value or value in {"nan", "none"}:
        return None
    value = (
        value.replace("á", "a")
        .replace("é", "e")
        .replace("í", "i")
        .replace("ó", "o")
        .replace("ú", "u")
    )
    if value in {"verde", "green"}:
        return 3
    if value in {"ambar", "amber", "amarillo", "yellow"}:
        return 2
    if value in {"rojo", "red"}:
        return 1
    if value in {"indef", "indefinido", "na", "n/a"}:
        return 0
    try:
        return int(float(value))
    except ValueError:
        return None


def _normalize_key(key: str) -> str:
    return str(key).strip().lower().replace("-", "_")


def _find_first_value(payload, candidate_keys, as_float: bool = False):
    keys = {_normalize_key(k) for k in candidate_keys}
    stack = [payload]
    while stack:
        current = stack.pop()
        if isinstance(current, dict):
            for raw_key, raw_value in current.items():
                if _normalize_key(raw_key) in keys:
                    if as_float:
                        f = parse_float(raw_value)
                        if f is not None:
                            return f
                    else:
                        if raw_value is not None and str(raw_value).strip() != "":
                            return raw_value
                if isinstance(raw_value, (dict, list)):
                    stack.append(raw_value)
        elif isinstance(current, list):
            for item in current:
                if isinstance(item, (dict, list)):
                    stack.append(item)
    return None


def _parse_iso_datetime(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    s = str(value).strip()
    if not s:
        return None
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(s)
    except ValueError:
        return None


def _normalize_intervals_activities_payload(data: Any) -> list:
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]
    if isinstance(data, dict):
        for key in ("activities", "data", "results", "items"):
            value = data.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
    return []


def fetch_intervals_activities(api_key: str, athlete_id: str, date_str: str) -> list:
    """Fetch activities for a date from Intervals.icu."""
    if not api_key or not athlete_id or not date_str:
        return []
    url = f"{_intervals_api_root()}/athlete/{athlete_id}/activities"
    headers = {"Authorization": build_basic_auth_header("API_KEY", api_key)}
    params = {"oldest": date_str, "newest": date_str}
    try:
        resp = requests.get(url, headers=headers, params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        return _normalize_intervals_activities_payload(data)
    except (requests.RequestException, ValueError) as exc:
        print(f"⚠️ Intervals fetch failed for {date_str}: {exc}")
        return []


def _extract_activity_datetime(activity: dict) -> Optional[datetime]:
    for key in ("start_date_local", "start_date", "startDateLocal", "startDate", "start_time", "startTime"):
        raw = _find_first_value(activity, [key])
        parsed = _parse_iso_datetime(raw) if raw is not None else None
        if parsed is not None:
            return parsed
    return None


def _aggregate_intervals_activity_fields(activities: list) -> Dict[str, Any]:
    if not activities:
        return {"intervals_n_acts": 0}

    rows = []

    for act in activities:
        if not isinstance(act, dict):
            continue
        row = {
            "activity": act,
            "load": parse_float(_find_first_value(act, ["icu_training_load", "training_load", "load"], as_float=True)),
            "intensity": parse_float(_find_first_value(act, ["icu_intensity", "intensity"], as_float=True)),
            "moving_time_s": parse_float(_find_first_value(act, ["moving_time", "movingTime", "moving time"], as_float=True)),
            "avg_hr": parse_float(_find_first_value(act, ["average_heartrate", "avg_hr", "average_heart_rate"], as_float=True)),
            "max_hr": parse_float(_find_first_value(act, ["max_heartrate", "max_hr", "max_heart_rate"], as_float=True)),
            "atl": parse_float(_find_first_value(act, ["icu_atl", "atl"], as_float=True)),
            "ctl": parse_float(_find_first_value(act, ["icu_ctl", "ctl"], as_float=True)),
            "tsb": parse_float(_find_first_value(act, ["icu_tsb", "tsb"], as_float=True)),
            "rpe": parse_float(_find_first_value(act, ["icu_rpe", "rpe"], as_float=True)),
            "resting_hr": parse_float(_find_first_value(act, ["resting_heartrate", "resting_hr"], as_float=True)),
            "type": _find_first_value(act, ["type", "activity_type", "sport"]),
            "dt": _extract_activity_datetime(act),
        }
        rows.append(row)

    if not rows:
        return {"intervals_n_acts": 0}

    load_vals = [r["load"] for r in rows if r["load"] is not None]
    intensity_vals = [r["intensity"] for r in rows if r["intensity"] is not None]
    duration_vals = [r["moving_time_s"] for r in rows if r["moving_time_s"] is not None]
    avg_hr_vals = [r["avg_hr"] for r in rows if r["avg_hr"] is not None]
    max_hr_vals = [r["max_hr"] for r in rows if r["max_hr"] is not None]

    main_row = max(rows, key=lambda r: r["load"] if r["load"] is not None else float("-inf"))

    def _dt_key(row):
        dt = row.get("dt")
        if dt is None:
            return float("-inf")
        try:
            return float(dt.timestamp())
        except (AttributeError, OSError, OverflowError, ValueError):
            return float("-inf")

    latest_row = max(rows, key=_dt_key)

    out: Dict[str, Any] = {"intervals_n_acts": len(rows)}
    if load_vals:
        out["intervals_load"] = float(sum(load_vals))
        out["intervals_load_max"] = float(max(load_vals))
    if intensity_vals:
        out["intervals_intensity_max"] = float(max(intensity_vals))
    if duration_vals:
        out["intervals_duration_min"] = float(sum(duration_vals) / 60.0)
    if avg_hr_vals:
        out["intervals_avg_hr"] = float(sum(avg_hr_vals) / len(avg_hr_vals))
    if max_hr_vals:
        out["intervals_max_hr"] = float(max(max_hr_vals))

    main_type = main_row.get("type")
    if main_type is not None:
        out["intervals_type_main"] = str(main_type)

    for dst_key, src_key in (
        ("intervals_atl", "atl"),
        ("intervals_ctl", "ctl"),
        ("intervals_tsb", "tsb"),
        ("intervals_rpe", "rpe"),
        ("intervals_resting_hr", "resting_hr"),
    ):
        value = latest_row.get(src_key)
        if value is not None:
            out[dst_key] = float(value)

    return out


def _read_latest_master_row(master_path: Path) -> Optional[Dict[str, Any]]:
    if not master_path.exists():
        print(f"⚠️  Intervals: no se encontró {master_path}")
        return None

    latest_row: Optional[Dict[str, Any]] = None
    latest_date = None
    with master_path.open("r", encoding="utf-8", newline="") as csvfile:
        reader = csv.DictReader(csvfile)
        for row in reader:
            raw_date = (row.get(MASTER_CSV_COLS["fecha"]) or "").strip()
            parsed = _parse_yyyy_mm_dd(raw_date)
            if parsed is None:
                continue
            if latest_date is None or parsed > latest_date:
                latest_date = parsed
                latest_row = row
    if not latest_row or not latest_date:
        print("⚠️  Intervals: no se pudo determinar la última fecha del master CSV")
        return None
    latest_row["_date"] = latest_date.isoformat()
    return latest_row


def _build_intervals_payload(row: Dict[str, Any]) -> Dict[str, Any]:
    payload: Dict[str, Any] = {}
    for field_id, source_key in INTERVALS_FIELD_MAP.items():
        raw_value = row.get(source_key)
        if source_key.startswith("Color_"):
            mapped = _normalize_color_value(raw_value)
        else:
            mapped = parse_float(raw_value)
        if mapped is not None:
            payload[field_id] = mapped
    return payload


def _send_intervals_wellness_from_master(master_path: Path) -> dict[str, str]:
    """Sync wellness and return a sanitized status for the HRV pipeline."""
    _print_header("🌐 INTERVALS SYNC")
    api_key = (os.environ.get("INTERVALS_API_KEY") or "").strip()
    athlete_id = (os.environ.get("INTERVALS_ATHLETE_ID") or "").strip()
    if not api_key or not athlete_id:
        print("⏭️  Intervals: faltan INTERVALS_API_KEY o INTERVALS_ATHLETE_ID, se omite sync")
        return {"status": "disabled", "outcome": "not_configured"}

    try:
        row = _read_latest_master_row(master_path)
    except (OSError, UnicodeDecodeError, csv.Error) as exc:
        print(f"⚠️  Intervals: no se pudo leer el master ({exc})")
        return {"status": "error", "outcome": "master_read_error"}
    if not row:
        return {"status": "not_applicable", "outcome": "missing_master_row"}

    payload = _build_intervals_payload(row)
    if not payload:
        print("⚠️  Intervals: no hay datos válidos para enviar")
        return {"status": "not_applicable", "outcome": "no_payload"}

    date_value = row.get("_date")
    url = f"{_intervals_api_root()}/athlete/{athlete_id}/wellness/{date_value}"
    headers = {
        "Authorization": build_basic_auth_header("API_KEY", api_key),
        "Content-Type": "application/json",
    }

    try:
        response = requests.put(url, headers=headers, json=payload, timeout=30)
    except requests.RequestException as exc:
        print(f"❌ Intervals: error de red: {exc}")
        return {"status": "error", "outcome": "request_error"}

    if response.ok:
        print(f"✅ Intervals: wellness actualizado para {date_value}")
        return {"status": "ok", "outcome": "updated"}

    print(f"⚠️  Intervals: error {response.status_code}")
    try:
        print(response.json())
    except ValueError:
        print(response.text)
    return {"status": "error", "outcome": "http_error"}
