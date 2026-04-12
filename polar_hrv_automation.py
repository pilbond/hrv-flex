#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
POLAR HRV AUTOMATION - Railway/Render Compatible
=================================================
Funciona con .env (local) O variables de entorno (Railway/Render)

Uso:
    python polar_hrv_automation.py --auth         # Primera vez
    python polar_hrv_automation.py                # Después (últimos 7 días)
    python polar_hrv_automation.py --days 30      # Últimos 30 días
    python polar_hrv_automation.py --all          # Todas las sesiones
    python polar_hrv_automation.py --process      # + ejecutar build_hrv_core.py + build_hrv_final_dashboard.py
"""

import os
import sys
import re
import argparse
import csv
from pathlib import Path
from datetime import datetime, timedelta

from typing import Optional, Dict, Any, List, Tuple
import requests
import pandas as pd
from config import (
    BETA_AUDIT_PATH,
    CORE_PATH,
    DASHBOARD_PATH,
    DATA_DIR,
    DEBUG_JSON,
    DEBUG_PREVIEW_LIMIT,
    DROPBOX_RR_ENABLED,
    FIELD_SAMPLE_TYPE,
    FIELD_SPORT,
    FIELD_START_TIME,
    FINAL_PATH,
    INTERVALS_BASE_URL,
    INTERVALS_FIELD_MAP,
    INTERVALS_SOURCE_PATH,
    IS_HEROKU,
    IS_PRODUCTION,
    IS_RAILWAY,
    IS_RENDER,
    MAX_AUTO_DAYS,
    MAX_DURATION_MINUTES,
    MAX_EXERCISES,
    MASTER_CSV_COLS,
    OUTDIR,
    PANDAS_AVAILABLE,
    POLAR_USER_NAME,
    QUIET,
    RR_MAX_MS,
    RR_MIN_MS,
    SLEEP_COLUMNS,
    SLEEP_PATH,
    SPORTS_FILTER,
    UNKNOWN_SESSION_ID,
    _qprint,
    get_production_url,
)
from cli_reporting import (
    _format_metric,
    _get_color_emoji,
    _get_gate_emoji,
    _print_divider,
    _print_header,
    _print_master_already_updated,
    _print_no_rr_files,
    _print_sync_completed,
    show_last_7_days_summary,
    show_last_daily_summary,
    show_latest_hrv_summaries,
)
from polar_utils import (
    _iso_to_dt,
    _parse_yyyy_mm_dd,
    env_flag,
    get_field_variant,
    parse_duration_to_minutes,
    parse_float,
    response_excerpt,
)
from polar_client import (
    fetch_polar_nightly_recharge,
    fetch_polar_sleep,
    get_exercise_with_samples,
    list_exercises,
    register_user_if_needed,
)
from polar_oauth_local import do_oauth_flow, load_tokens
from dropbox_rr import _compute_target_missing_dates, _run_dropbox_rr_import_for_dates
from pipeline_runner import (
    build_hrv_core_cmd,
    run_build_hrv_core,
    run_build_hrv_final_dashboard_only,
)
from oauth_utils import build_basic_auth_header


def _intervals_api_root() -> str:
    base = (INTERVALS_BASE_URL or "https://intervals.icu").strip().rstrip("/")
    if not base:
        base = "https://intervals.icu"
    base = re.sub(r"/api/v1/?$", "", base, flags=re.IGNORECASE)
    return f"{base}/api/v1"


def _normalize_key(key: str) -> str:
    return str(key).strip().lower().replace("-", "_")


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


def _minutes_between(start_iso: Optional[str], end_iso: Optional[str]) -> Optional[float]:
    start_dt = _parse_iso_datetime(start_iso)
    end_dt = _parse_iso_datetime(end_iso)
    if not start_dt or not end_dt:
        return None
    delta = (end_dt - start_dt).total_seconds() / 60.0
    if delta <= 0:
        return None
    return float(delta)


def _normalize_sleep_minutes(value) -> Optional[float]:
    """
    Normalize duration-like values to minutes.
    Accepts ISO duration, minutes, seconds, or milliseconds (heuristic).
    """
    minutes = parse_duration_to_minutes(value)
    if minutes is None:
        return None
    if minutes <= 0:
        return None
    # If value is implausibly large for minutes, infer source unit.
    if minutes > 1440:
        # Looks like seconds.
        if minutes <= 172800:
            return minutes / 60.0
        # Looks like milliseconds.
        if minutes <= 172800000:
            return minutes / 60000.0
    return minutes


def _normalize_resp_rate(value) -> Optional[float]:
    """Normalize nightly respiration to breaths/min."""
    v = parse_float(value)
    if v is None or v <= 0:
        return None
    # If value seems to be respiration interval in ms, convert to brpm.
    if v > 100:
        brpm = 60000.0 / v
        if 4.0 <= brpm <= 40.0:
            return brpm
    return v


def _normalize_pct(value) -> Optional[float]:
    v = parse_float(value)
    if v is None:
        return None
    if v <= 1.0:
        return v * 100.0
    return v


def _find_first_value(payload, candidate_keys: List[str], as_float: bool = False):
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


def _extract_interruptions_counts(sleep_json: dict) -> Tuple[Optional[float], Optional[float]]:
    if not isinstance(sleep_json, dict):
        return None, None

    evaluation = get_field_variant(sleep_json, "evaluation", "sleep-evaluation", "sleep_evaluation", default=None)
    interruptions = None
    if isinstance(evaluation, dict):
        interruptions = get_field_variant(
            evaluation,
            "interruptions",
            "sleep-interruptions",
            "sleep_interruptions",
            default=None,
        )

    long_count = None
    total_count = None
    if isinstance(interruptions, dict):
        long_count = parse_float(get_field_variant(interruptions, "longCount", "long_count", "long-count", default=None))
        total_count = parse_float(get_field_variant(interruptions, "totalCount", "total_count", "total-count", "count", default=None))
    elif isinstance(interruptions, list):
        total_items = 0
        long_items = 0
        for item in interruptions:
            if not isinstance(item, dict):
                continue
            total_items += 1
            kind = str(_find_first_value(item, ["type", "kind", "interruption_type"]) or "").strip().lower()
            if "long" in kind:
                long_items += 1
                continue
            dur_min = _normalize_sleep_minutes(_find_first_value(item, ["duration", "interruption_duration"]))
            if dur_min is not None and dur_min >= 5.0:
                long_items += 1
        if total_items > 0:
            total_count = float(total_items)
            long_count = float(long_items)

    if long_count is None:
        long_count = _find_first_value(
            sleep_json,
            [
                "longCount",
                "long_count",
                "long-count",
                "sleep_long_interruptions",
                "interruptions_long",
            ],
            as_float=True,
        )
    if total_count is None:
        total_count = _find_first_value(
            sleep_json,
            [
                "totalCount",
                "total_count",
                "total-count",
                "interruptions_total",
                "sleep_interruptions_total",
                "interruptions_count",
                "number_of_interruptions",
            ],
            as_float=True,
        )

    return long_count, total_count


def _extract_sleep_fields(sleep_json: Optional[dict]) -> Dict[str, Any]:
    if not isinstance(sleep_json, dict):
        return {}

    sleep_start = _find_first_value(sleep_json, ["sleep_start_time", "sleep-start-time", "sleepStartTime"])
    sleep_end = _find_first_value(sleep_json, ["sleep_end_time", "sleep-end-time", "sleepEndTime"])

    asleep_duration_min = _normalize_sleep_minutes(
        _find_first_value(
            sleep_json,
            ["asleep_duration", "asleep-duration", "sleep_duration", "sleep-duration", "sleepDuration"],
        )
    )
    span_min = _normalize_sleep_minutes(
        _find_first_value(sleep_json, ["sleep_span", "sleep-span", "sleepSpan", "time_in_bed"])
    )
    if span_min is None:
        span_min = _minutes_between(sleep_start, sleep_end)

    deep_min = _normalize_sleep_minutes(_find_first_value(sleep_json, ["deep_sleep", "deep-sleep", "deepSleep", "sleep_n3"]))
    rem_min = _normalize_sleep_minutes(_find_first_value(sleep_json, ["rem_sleep", "rem-sleep", "remSleep", "sleep_rem"]))
    light_min = _normalize_sleep_minutes(_find_first_value(sleep_json, ["light_sleep", "light-sleep", "lightSleep"]))

    if asleep_duration_min is None:
        parts = [x for x in (deep_min, rem_min, light_min) if x is not None]
        if parts:
            asleep_duration_min = float(sum(parts))

    deep_pct = parse_float(_find_first_value(sleep_json, ["polar_deep_pct", "deep_pct", "deep_percentage"]))
    rem_pct = parse_float(_find_first_value(sleep_json, ["polar_rem_pct", "rem_pct", "rem_percentage"]))
    if asleep_duration_min and asleep_duration_min > 0:
        if deep_pct is None and deep_min is not None:
            deep_pct = 100.0 * deep_min / asleep_duration_min
        if rem_pct is None and rem_min is not None:
            rem_pct = 100.0 * rem_min / asleep_duration_min

    continuity = parse_float(_find_first_value(sleep_json, ["continuity", "sleep_continuity"]))
    continuity_index = parse_float(_find_first_value(sleep_json, ["continuity_index", "continuity-class", "continuity_class"]))
    efficiency_pct = _normalize_pct(_find_first_value(sleep_json, ["efficiency_pct", "sleep_efficiency", "efficiency"]))
    if efficiency_pct is None and asleep_duration_min is not None and span_min is not None and span_min > 0:
        efficiency_pct = 100.0 * asleep_duration_min / span_min
    sleep_score = parse_float(_find_first_value(sleep_json, ["sleep_score", "sleep-score"]))
    long_count, total_count = _extract_interruptions_counts(sleep_json)

    out: Dict[str, Any] = {}
    if asleep_duration_min is not None:
        out["polar_sleep_duration_min"] = asleep_duration_min
    if span_min is not None:
        out["polar_sleep_span_min"] = span_min
    if deep_pct is not None:
        out["polar_deep_pct"] = deep_pct
    if rem_pct is not None:
        out["polar_rem_pct"] = rem_pct
    if efficiency_pct is not None:
        out["polar_efficiency_pct"] = efficiency_pct
    if continuity is not None:
        out["polar_continuity"] = continuity
    if continuity_index is not None:
        out["polar_continuity_index"] = continuity_index
    if long_count is not None:
        out["polar_interruptions_long"] = long_count
    if total_count is not None:
        out["polar_interruptions_total"] = total_count
    if sleep_score is not None:
        out["polar_sleep_score"] = sleep_score
    return out


def _extract_nightly_fields(nightly_json: Optional[dict]) -> Dict[str, Any]:
    if not isinstance(nightly_json, dict):
        return {}

    night_rmssd = parse_float(
        _find_first_value(
            nightly_json,
            ["heart_rate_variability_avg", "heart-rate-variability-avg", "nightly_rmssd"],
            as_float=True,
        )
    )
    night_rri = parse_float(
        _find_first_value(
            nightly_json,
            ["nightly_rri", "rri_avg", "heart_rate_rri_avg", "heart-rate-rri-avg"],
            as_float=True,
        )
    )
    hr_avg = parse_float(_find_first_value(nightly_json, ["heart_rate_avg", "heart-rate-avg", "hr_avg"], as_float=True))
    if night_rri is None and hr_avg is not None and hr_avg > 0:
        night_rri = 60000.0 / hr_avg

    night_resp_raw = _find_first_value(
        nightly_json,
        ["breathing_rate_avg", "breathing-rate-avg", "nightly_resp", "nightly_resp_int"],
        as_float=True,
    )
    night_resp = _normalize_resp_rate(night_resp_raw)

    out: Dict[str, Any] = {}
    if night_rmssd is not None:
        out["polar_night_rmssd"] = night_rmssd
    if night_rri is not None:
        out["polar_night_rri"] = night_rri
    if night_resp is not None:
        out["polar_night_resp"] = night_resp
    return out


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
    except Exception as exc:
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
            "load": _find_first_value(act, ["icu_training_load", "training_load", "load"], as_float=True),
            "intensity": _find_first_value(act, ["icu_intensity", "intensity"], as_float=True),
            "moving_time_s": _find_first_value(act, ["moving_time", "movingTime", "moving time"], as_float=True),
            "avg_hr": _find_first_value(act, ["average_heartrate", "avg_hr", "average_heart_rate"], as_float=True),
            "max_hr": _find_first_value(act, ["max_heartrate", "max_hr", "max_heart_rate"], as_float=True),
            "atl": _find_first_value(act, ["icu_atl", "atl"], as_float=True),
            "ctl": _find_first_value(act, ["icu_ctl", "ctl"], as_float=True),
            "tsb": _find_first_value(act, ["icu_tsb", "tsb"], as_float=True),
            "rpe": _find_first_value(act, ["icu_rpe", "rpe"], as_float=True),
            "resting_hr": _find_first_value(act, ["resting_heartrate", "resting_hr"], as_float=True),
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


def _ensure_sleep_schema(df):
    out = df.copy()
    for col in SLEEP_COLUMNS:
        if col not in out.columns:
            out[col] = float("nan")
    out = out[SLEEP_COLUMNS].copy()
    out["Fecha"] = out["Fecha"].astype(str)
    return out


def _recalculate_sleep_derived(df):
    out = _ensure_sleep_schema(df)
    out["_fecha_dt"] = pd.to_datetime(out["Fecha"], errors="coerce")
    out = out.sort_values("_fecha_dt").drop(columns=["_fecha_dt"]).reset_index(drop=True)

    numeric_cols = [c for c in SLEEP_COLUMNS if c != "Fecha"]
    for col in numeric_cols:
        out[col] = pd.to_numeric(out[col], errors="coerce")

    # Normalize sleep minutes and nightly respiration for legacy rows too.
    if "polar_sleep_duration_min" in out.columns:
        out["polar_sleep_duration_min"] = out["polar_sleep_duration_min"].apply(_normalize_sleep_minutes)
    if "polar_sleep_span_min" in out.columns:
        out["polar_sleep_span_min"] = out["polar_sleep_span_min"].apply(_normalize_sleep_minutes)
    if "polar_night_resp" in out.columns:
        out["polar_night_resp"] = out["polar_night_resp"].apply(_normalize_resp_rate)
    if "polar_efficiency_pct" in out.columns:
        missing_eff = out["polar_efficiency_pct"].isna()
        can_derive = (
            out["polar_sleep_duration_min"].notna()
            & out["polar_sleep_span_min"].notna()
            & (out["polar_sleep_span_min"] > 0)
        )
        idx = missing_eff & can_derive
        out.loc[idx, "polar_efficiency_pct"] = (
            100.0 * out.loc[idx, "polar_sleep_duration_min"] / out.loc[idx, "polar_sleep_span_min"]
        )

    # Sleep-only percentiles
    dur = out["polar_sleep_duration_min"].dropna()
    out["sleep_dur_p10"] = float(dur.quantile(0.10)) if len(dur) > 0 else float("nan")
    out["sleep_dur_p90"] = float(dur.quantile(0.90)) if len(dur) > 0 else float("nan")

    ints = out["polar_interruptions_long"].dropna()
    out["sleep_int_p90"] = float(ints.quantile(0.90)) if len(ints) > 0 else float("nan")

    return out


def upsert_sleep_row(sleep_row: Dict[str, Any]) -> bool:
    if not PANDAS_AVAILABLE:
        print("⚠️  Pandas no disponible: se omite actualización de sleep.csv")
        return False

    fecha = str(sleep_row.get("Fecha", "")).strip()
    if not fecha:
        return False

    if SLEEP_PATH.exists():
        try:
            sleep_df = pd.read_csv(SLEEP_PATH)
        except (FileNotFoundError, pd.errors.EmptyDataError, OSError, ValueError):
            sleep_df = pd.DataFrame(columns=SLEEP_COLUMNS)
    else:
        sleep_df = pd.DataFrame(columns=SLEEP_COLUMNS)

    sleep_df = _ensure_sleep_schema(sleep_df)
    sleep_df = sleep_df[sleep_df["Fecha"].astype(str) != fecha]

    row = {col: sleep_row.get(col, float("nan")) for col in SLEEP_COLUMNS}
    row["Fecha"] = fecha
    if row.get("intervals_type_main") is None:
        row["intervals_type_main"] = ""

    sleep_df = pd.concat([sleep_df, pd.DataFrame([row])], ignore_index=True)
    sleep_df = _recalculate_sleep_derived(sleep_df)
    sleep_df = sleep_df[SLEEP_COLUMNS]

    SLEEP_PATH.parent.mkdir(parents=True, exist_ok=True)
    sleep_df.to_csv(SLEEP_PATH, index=False)
    return True


def _polar_sleep_date_candidates(date_str: str) -> List[str]:
    d = _parse_yyyy_mm_dd(date_str)
    if d is None:
        return [date_str]
    prev = (d - timedelta(days=1)).isoformat()
    return [date_str, prev]


def fetch_and_upsert_sleep(token: str, user_id: Optional[str], processed_date) -> bool:
    if processed_date is None:
        return False

    date_str = processed_date.isoformat() if hasattr(processed_date, "isoformat") else str(processed_date)
    if not date_str:
        return False

    sleep_row: Dict[str, Any] = {col: float("nan") for col in SLEEP_COLUMNS}
    sleep_row["Fecha"] = date_str

    if user_id:
        sleep_json = None
        sleep_used_date = None
        nightly_json = None
        nightly_used_date = None
        for candidate_date in _polar_sleep_date_candidates(date_str):
            if sleep_json is None:
                resp = fetch_polar_sleep(token, user_id, candidate_date)
                if isinstance(resp, dict) and len(resp) > 0:
                    sleep_json = resp
                    sleep_used_date = candidate_date
            if nightly_json is None:
                resp2 = fetch_polar_nightly_recharge(token, user_id, candidate_date)
                if isinstance(resp2, dict) and len(resp2) > 0:
                    nightly_json = resp2
                    nightly_used_date = candidate_date
            if sleep_json is not None and nightly_json is not None:
                break

        if sleep_json:
            sleep_row.update(_extract_sleep_fields(sleep_json))
            if sleep_used_date and sleep_used_date != date_str:
                print(f"ℹ️  Sleep tomado desde {sleep_used_date} para fecha {date_str}")
        if nightly_json:
            sleep_row.update(_extract_nightly_fields(nightly_json))
            if nightly_used_date and nightly_used_date != date_str:
                print(f"ℹ️  Nightly tomado desde {nightly_used_date} para fecha {date_str}")
    else:
        print("⚠️  x_user_id ausente: se omite fetch Polar sleep/nightly")

    # Training load now lives in sessions_day.csv (generated by build_sessions.py)
    # — no longer fetched here.

    saved = upsert_sleep_row(sleep_row)
    return saved


def _update_sleep_for_dates(token: str, user_id: Optional[str], dates_to_sync: List) -> int:
    """Fetch+upsert sleep rows for a list of dates. Returns successful upserts."""
    if not dates_to_sync:
        return 0

    done = 0
    seen = set()
    for d in dates_to_sync:
        if d is None:
            continue
        key = d.isoformat() if hasattr(d, "isoformat") else str(d)
        if key in seen:
            continue
        seen.add(key)
        try:
            if fetch_and_upsert_sleep(token, user_id, d):
                done += 1
        except Exception as exc:
            print(f"⚠️  Sleep fetch/upsert falló para {key}: {exc}")
    return done


def _today_date():
    return datetime.now().date()


def _default_sleep_refresh_dates() -> List:
    today = _today_date()
    return [today, today - timedelta(days=1)]


def extract_rr_ms(exercise_json: dict):
    """Extrae RR intervals (sample-type 11)"""
    rr = []
    samples = exercise_json.get("samples") or []
    for s in samples:
        st = get_field_variant(s, *FIELD_SAMPLE_TYPE)
        if str(st) != "11":
            continue

        data = str(s.get("data", ""))
        for tok in data.split(","):
            tok = tok.strip()
            if not tok or tok.upper() == "NULL":
                continue
            try:
                v = float(tok)  # ms
            except ValueError:
                continue
            offline = 0 if RR_MIN_MS <= v <= RR_MAX_MS else 1
            rr.append((v, offline))
    return rr


def write_rr_csv(rr, out_path: str):
    """Escribe CSV formato build_hrv_core.py"""
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("duration,offline\n")
        for v, off in rr:
            f.write(f"{v:.3f},{off}\n")


def passes_filters(ex_item: dict, from_d, to_d, sports_set, max_duration_min, debug=False):
    """Filtra ejercicios por fecha, deporte y duración"""
    
    if debug:
        print(f"\n  🔍 Evaluando: {ex_item.get('id', 'N/A')}")
    
    # Filtro fecha
    st = get_field_variant(ex_item, *FIELD_START_TIME)
    dt = _iso_to_dt(st)
    if dt:
        d = dt.date()
        if debug:
            print(f"     Fecha: {d} | Rango: {from_d} a {to_d}")
        
        if from_d and d < from_d:
            if debug:
                print(f"     ❌ Fecha < from_d ({d} < {from_d})")
            return False
        if to_d and d > to_d:
            if debug:
                print(f"     ❌ Fecha > to_d ({d} > {to_d})")
            return False
        
        if debug:
            print(f"     ✅ Fecha OK")
    else:
        if debug:
            print(f"     ⚠️  Sin fecha parseable: {st}")

    # Filtro deporte (comparación EXACTA)
    if sports_set:
        sp = get_field_variant(ex_item, *FIELD_SPORT, default="")

        if debug:
            print(f"     Sport: '{sp}' | Buscando: {sports_set}")
        
        if sp not in sports_set:
            if debug:
                print(f"     ❌ Sport no coincide")
            return False
        
        if debug:
            print(f"     ✅ Sport OK")

    # Filtro duración
    if max_duration_min:
        duration_str = ex_item.get("duration", "")
        if duration_str:
            duration_min = parse_duration_to_minutes(duration_str)
            
            if debug:
                print(f"     Duración: {duration_str} = {duration_min:.2f} min | Max: {max_duration_min}")
            
            if duration_min > max_duration_min:
                if debug:
                    print(f"     ❌ Duración excedida ({duration_min:.2f} > {max_duration_min})")
                return False
            
            if debug:
                print(f"     ✅ Duración OK")

    if debug:
        print(f"     ✅✅ PASA TODOS LOS FILTROS")
    
    return True

def get_last_date_from_master():
    """Lee última fecha registrada en ENDURANCE_HRV_master_CORE.csv"""
    master_file = CORE_PATH

    if not master_file.exists() or not PANDAS_AVAILABLE:
        return None

    try:
        df = pd.read_csv(master_file)

        if 'Fecha' not in df.columns or df.empty:
            return None

        # Obtener última fecha (asumiendo formato YYYY-MM-DD)
        last_date_str = df['Fecha'].max()
        last_date = datetime.strptime(last_date_str, '%Y-%m-%d').date()

        return last_date

    except (FileNotFoundError, pd.errors.EmptyDataError, ValueError, KeyError) as e:
        print(f"⚠️  Error leyendo CORE: {e}")
        return None

def get_existing_dates_from_master():
    """Obtiene set de fechas ya existentes en CORE (ENDURANCE_HRV_master_CORE.csv)"""
    master_file = CORE_PATH

    if not master_file.exists() or not PANDAS_AVAILABLE:
        return set()

    try:
        df = pd.read_csv(master_file)

        if 'Fecha' not in df.columns or df.empty:
            return set()

        # Convertir todas las fechas a date objects
        dates = set()
        for date_str in df['Fecha']:
            try:
                date_obj = datetime.strptime(str(date_str), '%Y-%m-%d').date()
                dates.add(date_obj)
            except (ValueError, TypeError):
                pass  # Skip invalid date formats

        return dates

    except (FileNotFoundError, pd.errors.EmptyDataError, KeyError) as e:
        print(f"⚠️  Error leyendo fechas del CORE: {e}")
        return set()

def calculate_missing_days():
    """Calcula cuántos días faltan desde última medición hasta hoy"""
    last_date = get_last_date_from_master()
    today = datetime.now().date()
    
    if last_date is None:
        # Sin CORE o sin datos, usar 7 días por defecto
        return 7, None
    
    # Calcular días faltantes
    days_missing = (today - last_date).days
    
    # Si última fecha es hoy, no hay nada que descargar
    if days_missing <= 0:
        return 0, last_date
    
    return days_missing, last_date


def _refresh_sleep_and_outputs(access_token: str, x_user_id: Optional[str], run_final_dashboard: bool = False, dates: Optional[List] = None) -> None:
    target_dates = dates if dates is not None else _default_sleep_refresh_dates()
    _update_sleep_for_dates(access_token, x_user_id, target_dates)
    if run_final_dashboard:
        _qprint("▶️  Regenerando FINAL/DASHBOARD con sleep actualizado...")
        run_build_hrv_final_dashboard_only()

def main():
    parser = argparse.ArgumentParser(description='Polar HRV Automation')
    parser.add_argument('--auth', action='store_true', help='Forzar re-autenticación')
    parser.add_argument('--days', type=int, help='Días hacia atrás (ignora --auto)')
    parser.add_argument('--all', action='store_true', help='Todas las sesiones (ignora --days y --auto)')
    parser.add_argument('--auto', action='store_true', help='Detectar automáticamente días faltantes desde último registro')
    parser.add_argument('--process', action='store_true', help='Ejecutar build_hrv_core.py + build_hrv_final_dashboard.py después')
    parser.add_argument('--debug-sports', action='store_true', help='Mostrar deportes de todas las sesiones encontradas')
    parser.add_argument('--verbose', action='store_true', help='Mostrar detalles de cada archivo procesado')
    args = parser.parse_args()

    # _print_header("  POLAR HRV AUTOMATION")

    # Autenticación
    # En PRODUCCIÓN (Railway/Render/Heroku) NO se puede abrir navegador ni levantar callback server local.
    # La autorización debe hacerse vía Web UI: /auth -> /auth/callback, que guarda TOKEN_FILE.
    if args.auth:
        if IS_PRODUCTION:
            public_url = get_production_url()
            hint = f"{public_url.rstrip('/')}/auth" if public_url else "/auth"
            print(f"❌ En producción no se admite --auth interactivo. Abre {hint} para autorizar.", file=sys.stderr)
            sys.exit(3)
        access_token, x_user_id = do_oauth_flow()
    else:
        access_token, x_user_id = load_tokens()
        if not access_token:
            if IS_PRODUCTION:
                public_url = get_production_url()
                hint = f"{public_url.rstrip('/')}/auth" if public_url else "/auth"
                print(f"❌ Falta autorización. Abre {hint} para iniciar sesión en Polar y autorizar la app.", file=sys.stderr)
                sys.exit(3)
            print("⚠️  Token ausente/expirado, iniciando OAuth local...")
            access_token, x_user_id = do_oauth_flow()

    # Registrar usuario (obligatorio)
    member_id = f"local_{x_user_id or 'user'}"
    reg = register_user_if_needed(access_token, member_id, allow_transient_failure=True)
    if reg.get("status") == "temporary_failure":
        _qprint("⚠️  Registro Polar no confirmado por error temporal del servicio. Continuando con la sync.")
    # print(f"📝 Usuario: {reg.get('status')}")

    # Listar ejercicios
    # print("\n🔍 Obteniendo ejercicios...")
    exercises = list_exercises(access_token)

    if not isinstance(exercises, list):
        raise RuntimeError(f"Respuesta inesperada: {type(exercises)}")

    # print(f"📋 {len(exercises)} ejercicios totales")

    # Determinar rango fechas
    if args.all:
        from_d = None
        to_d = None
        _qprint("📅 Procesando TODAS las sesiones")
    elif args.auto:
        days_missing, last_date = calculate_missing_days()
        
        if days_missing == 0:
            if args.process:
                _qprint("▶️  Sin RR nuevos: actualizando sleep.csv (hoy)...")
                _refresh_sleep_and_outputs(access_token, x_user_id, run_final_dashboard=True)
            _print_sync_completed(updated_date=datetime.now().date(), checkmark=False)
            
            # Mostrar último daily summary
            show_latest_hrv_summaries()
            
            #print(f"\n💡 Para re-procesar: python {sys.argv[0]} --days 1 --process")
            #print("="*25 + "\n")
            return
        
        to_d = datetime.now().date()
        
        if last_date:
            # Descargar desde el día SIGUIENTE a la última medición
            from_d = last_date + timedelta(days=1)
            _qprint(f"📅 Última medición: {last_date}")
            _qprint(f"   Descargando desde {from_d} hasta {to_d}")
        else:
            # Sin CORE, descargar últimos N días
            from_d = (datetime.now() - timedelta(days=days_missing)).date()
            _qprint(f"📅 Master sin datos, descargando últimos {days_missing} días")
    elif args.days:
        to_d = datetime.now().date()
        from_d = (datetime.now() - timedelta(days=args.days)).date()
        _qprint(f"📅 Últimos {args.days} días: {from_d} → {to_d}")
    else:
        # Default: modo auto
        days_missing, last_date = calculate_missing_days()
        
        if days_missing == 0:
            if args.process:
                _qprint("▶️  Sin RR nuevos: actualizando sleep.csv (hoy)...")
                _refresh_sleep_and_outputs(access_token, x_user_id, run_final_dashboard=True)
            _print_sync_completed(updated_date=None, checkmark=True)
            
            # Mostrar último daily summary
            show_latest_hrv_summaries()
            
            # print(f"\n💡 Para re-procesar: python {sys.argv[0]} --days 1 --process")
            _print_divider(trailing_blank=True)
            return
        
        # Limitar a 30 días en modo auto para evitar descargas masivas
        if days_missing > MAX_AUTO_DAYS:
            print(f"⚠️  Faltan {days_missing} días (>30)")
            print(f"   Limitando a últimos 30 días")
            print(f"   Usa --all para descargar todo")
            days_missing = 30
        
        to_d = datetime.now().date()
        
        if last_date:
            # Descargar desde el día SIGUIENTE a la última medición
            from_d = last_date + timedelta(days=1)
            _qprint(f"📅 Última medición: {last_date}")
            _qprint(f"   Descargando desde {from_d} hasta {to_d} ({days_missing} días)")
        else:
            # Sin CORE, descargar últimos N días
            from_d = (datetime.now() - timedelta(days=days_missing)).date()
            _qprint(f"📅 Descargando últimos {days_missing} días (default)")

    # Debug: Mostrar deportes si --debug-sports
    if args.debug_sports:
        _print_header("🔍 DEBUG: TODAS LAS SESIONES ENCONTRADAS")
        for i, e in enumerate(exercises):
            st = get_field_variant(e, *FIELD_START_TIME, default="N/A")
            sport = get_field_variant(e, *FIELD_SPORT, default="N/A")
            duration = e.get("duration", "N/A")
            dt = _iso_to_dt(st)
            date_str = dt.strftime("%Y-%m-%d") if dt else "N/A"
            
            print(f"  [{i}] {date_str} | Sport: '{sport}' | Duration: {duration}")
        _print_divider(trailing_blank=True)
    
    # Aplicar filtros
    sports_set = set(SPORTS_FILTER) if SPORTS_FILTER else None
    
    filtered = []
    for e in exercises:
        if passes_filters(e, from_d, to_d, sports_set, MAX_DURATION_MINUTES):
            filtered.append(e)
        if len(filtered) >= MAX_EXERCISES:
            break

    _qprint(f"✅ {len(filtered)} sesiones tras filtros (max {MAX_EXERCISES})")

    if not filtered:
        dropbox_only_map: Dict = {}
        if DROPBOX_RR_ENABLED:
            existing_for_dropbox = get_existing_dates_from_master()
            target_for_dropbox = _compute_target_missing_dates(from_d, to_d, existing_for_dropbox)
            dropbox_only_map, _ = _run_dropbox_rr_import_for_dates(
                target_for_dropbox,
                OUTDIR,
                verbose=args.verbose,
            )

        if dropbox_only_map:
            _qprint(
                f"☁️  Sin sesiones Polar filtradas, pero Dropbox cubrió "
                f"{len(dropbox_only_map)} fecha(s). Continuando con procesamiento HRV."
            )
        else:
            if QUIET:
                print("⚠️  No hay sesiones Body&Mind en el periodo")
                _refresh_sleep_and_outputs(access_token, x_user_id, run_final_dashboard=args.process)
                show_latest_hrv_summaries()
                _send_intervals_wellness_from_master(INTERVALS_SOURCE_PATH)
                return
            print("\n⚠️  No hay sesiones Body&Mind en el periodo")
            
            # Mostrar debug automáticamente
            if not args.debug_sports and exercises:
                print("\n🔍 Mostrando TODAS las sesiones encontradas para debug:")
                _print_divider()
                for i, e in enumerate(exercises[:DEBUG_PREVIEW_LIMIT]):
                    st = get_field_variant(e, *FIELD_START_TIME, default="N/A")
                    sport = get_field_variant(e, *FIELD_SPORT, default="N/A")
                    duration = e.get("duration", "N/A")
                    dt = _iso_to_dt(st)
                    date_str = dt.strftime("%Y-%m-%d") if dt else "N/A"
                    
                    # Mostrar si pasa filtro de fecha
                    in_range = "✓" if from_d and to_d and dt and from_d <= dt.date() <= to_d else "✗"
                    
                    print(f"  [{i}] {date_str} {in_range} | Sport: '{sport}' | Duration: {duration}")
                
                if len(exercises) > 10:
                    print(f"  ... y {len(exercises) - DEBUG_PREVIEW_LIMIT} más")
                _print_divider()
                print(f"\n💡 Buscando: Sport EXACTO = '{SPORTS_FILTER[0] if SPORTS_FILTER else 'N/A'}'")
                print(f"   En rango: {from_d} a {to_d}")
                
                # DEBUG DETALLADO: Re-evaluar con debug activado
                _print_header("🔍 DEBUG DETALLADO de cada sesión en rango:", leading_blank=True)
                for i, e in enumerate(exercises[:10]):
                    st = get_field_variant(e, *FIELD_START_TIME, default="N/A")
                    dt = _iso_to_dt(st)
                    if dt and from_d and to_d and from_d <= dt.date() <= to_d:
                        print(f"\n  Sesión [{i}] - {dt.date()}:")
                        passes_filters(e, from_d, to_d, sports_set, MAX_DURATION_MINUTES, debug=True)
                _print_divider()
            
            print(f"\n💡 No se encontraron sesiones '{SPORTS_FILTER[0] if SPORTS_FILTER else 'N/A'}' en el periodo.")
            print(f"   Usa --days N para más días o --debug-sports para ver todas las sesiones.")
            
            _refresh_sleep_and_outputs(access_token, x_user_id, run_final_dashboard=args.process)

            # Mostrar último daily summary disponible aunque no haya nuevos datos
            _print_header("📊 Aunque no hay nuevos datos, aquí está tu última medición:")
            show_latest_hrv_summaries()
            
            _send_intervals_wellness_from_master(INTERVALS_SOURCE_PATH)
            return

    # Export RR
    _qprint("\n📥 Descargando datos RR...")
    OUTDIR.mkdir(exist_ok=True)
    # Obtener fechas ya existentes en CORE
    existing_dates = get_existing_dates_from_master()
    pre_process_dates = set(existing_dates)
    if existing_dates and args.verbose:
        print(f"📋 {len(existing_dates)} fechas ya en CORE")
    
    exported = 0
    skipped_in_master = 0
    skipped_covered_by_dropbox = 0
    skipped_no_date = 0
    rr_files = []
    pending_rr_dates = set()

    target_missing_dates = _compute_target_missing_dates(from_d, to_d, existing_dates)
    dropbox_rr_map: Dict = {}
    dropbox_rr_new = 0
    if DROPBOX_RR_ENABLED and target_missing_dates:
        dropbox_rr_map, dropbox_rr_new = _run_dropbox_rr_import_for_dates(
            target_missing_dates,
            OUTDIR,
            verbose=args.verbose,
        )
        for day, rr_path in sorted(dropbox_rr_map.items(), key=lambda x: x[0]):
            rr_files.append(rr_path)
            pending_rr_dates.add(day)
        if dropbox_rr_map:
            reused = max(len(dropbox_rr_map) - dropbox_rr_new, 0)
            _qprint(
                f"☁️  Dropbox RR: {len(dropbox_rr_map)} fecha(s) cubierta(s) "
                f"({dropbox_rr_new} nuevas, {reused} ya existentes)"
            )

    for idx, e in enumerate(filtered):
        ex_id = e.get("id")
        if not ex_id:
            continue

        # Si ya tenemos RR (CORE o cloud JSONL) para la fecha del índice, evitar descarga de detalle.
        st_hint = get_field_variant(e, *FIELD_START_TIME, default="")
        st_hint_dt = _iso_to_dt(st_hint)
        session_date_hint = st_hint_dt.date() if st_hint_dt else None
        if session_date_hint and session_date_hint in existing_dates:
            if args.verbose:
                print(f"  [{idx}] ⏭️  {session_date_hint} ya en CORE, omitiendo")
            skipped_in_master += 1
            continue
        if session_date_hint and session_date_hint in pending_rr_dates:
            if args.verbose:
                print(
                    f"  [{idx}] ⏭️  {session_date_hint} ya cubierto por RR Dropbox, "
                    "omitiendo descarga Polar"
                )
            skipped_covered_by_dropbox += 1
            continue

        try:
            # Descargar ejercicio completo con samples
            ex_full = get_exercise_with_samples(access_token, ex_id)
        except (requests.RequestException, RuntimeError) as ex:
            print(f"  [{idx}] ❌ Error descargando: {ex}")
            continue

        # Obtener start-time del ejercicio completo
        st = get_field_variant(ex_full, *FIELD_START_TIME, default="")
        
        if not st:
            print(f"  [{idx}] ⚠️ Sin start-time, usando del índice previo")
            # Intentar con el del listado original
            st = get_field_variant(e, "start-time", "start_time", "startTime", default="")
        
        if not st:
            print(f"  [{idx}] ⚠️ No se puede determinar fecha/hora, usando ID")
            out_name = f"{POLAR_USER_NAME}_{UNKNOWN_SESSION_ID}_{ex_id}_RR.CSV"
            session_date = None
        else:
            st_dt = _iso_to_dt(st)
            
            if not st_dt:
                print(f"  [{idx}] ⚠️ Error parseando fecha, usando ID")
                out_name = f"{POLAR_USER_NAME}_{UNKNOWN_SESSION_ID}_{ex_id}_RR.CSV"
                session_date = None
            else:
                # Usar hora LOCAL de la sesión
                date_part = st_dt.strftime("%Y-%m-%d")
                time_part = st_dt.strftime("%H-%M-%S")
                out_name = f"{POLAR_USER_NAME}_{date_part}_{time_part}_RR.CSV"
                session_date = st_dt.date()
        
        
        if session_date is None:
            out_path = OUTDIR / out_name
            if out_path.exists():
                if args.verbose:
                    print(f"  [{idx}] ⏭️  {out_name} sin fecha, se omite procesamiento")
            else:
                rr = extract_rr_ms(ex_full)
                write_rr_csv(rr, str(out_path))
            skipped_no_date += 1
            continue

        # Verificar si fecha ya existe en CORE
        if session_date and session_date in existing_dates:
            if args.verbose:
                print(f"  [{idx}] ⏭️  {date_part} ya en CORE, omitiendo")
            skipped_in_master += 1
            continue
        if session_date and session_date in pending_rr_dates:
            if args.verbose:
                print(f"  [{idx}] ⏭️  {date_part} ya cubierto por RR Dropbox, omitiendo Polar")
            skipped_covered_by_dropbox += 1
            continue

        out_path = OUTDIR / out_name

        # Si archivo existe pero fecha NO está en master, procesarlo
        if out_path.exists():
            if args.verbose:
                print(f"  [{idx}] ♻️  {out_name} existe, se procesará (no en master)")
            rr_files.append(out_path)
            pending_rr_dates.add(session_date)
            continue

        # Extraer RR
        rr = extract_rr_ms(ex_full)

        write_rr_csv(rr, str(out_path))
        rr_files.append(out_path)
        pending_rr_dates.add(session_date)
        exported += 1

        offline_pct = 100.0 * sum(1 for _, off in rr if off == 1) / max(1, len(rr))
        if args.verbose:
            print(f"  [{idx}] ✅ {out_name} | {len(rr)} RR | offline: {offline_pct:.1f}%")

    # Resumen
    _print_header("✅ EXPORT COMPLETADO")
    
    total_to_process = len(rr_files)
    existing = max(total_to_process - exported - dropbox_rr_new, 0)
    
    if exported > 0:
        _qprint(f"\n📥 {exported} archivos nuevos descargados")
    if dropbox_rr_new > 0:
        _qprint(f"☁️  {dropbox_rr_new} RR nuevos generados desde Dropbox")
    
    if skipped_in_master > 0:
        _qprint(f"⏭️  {skipped_in_master} sesiones omitidas (ya en CORE)")
    if skipped_covered_by_dropbox > 0:
        _qprint(f"☁️  ⏭️  {skipped_covered_by_dropbox} sesiones omitidas (cubiertas por Dropbox)")
    if skipped_no_date > 0:
        _qprint(f"⚠️  {skipped_no_date} sesiones sin fecha (no se procesan)")
    
    if total_to_process > exported:
        _qprint(f"♻️  {existing} archivos existentes para reprocesar")
    
    _qprint(f"\n📊 {total_to_process} archivos totales para procesar en {OUTDIR}/")

    if total_to_process == 0 and skipped_in_master == 0:
        if skipped_no_date > 0:
            print("⚠️  No hay RR con fecha válida para procesar")
        else:
            _print_no_rr_files()
        _refresh_sleep_and_outputs(access_token, x_user_id, run_final_dashboard=args.process)
        _send_intervals_wellness_from_master(INTERVALS_SOURCE_PATH)
        show_latest_hrv_summaries()
        return
    
    if total_to_process == 0 and skipped_in_master > 0:
        _print_master_already_updated()
        _refresh_sleep_and_outputs(access_token, x_user_id, run_final_dashboard=args.process)
        _send_intervals_wellness_from_master(INTERVALS_SOURCE_PATH)
        show_latest_hrv_summaries()
        return

    # Procesar con build_hrv_core.py
    if args.process:
        _print_header("🔧 PROCESANDO PIPELINE HRV")

        cmd = build_hrv_core_cmd(rr_files)
        if len(cmd) <= 2:
            print("")
            print("⚠️  No hay archivos RR con fecha válida para procesar")
            _refresh_sleep_and_outputs(access_token, x_user_id, run_final_dashboard=True)
            _send_intervals_wellness_from_master(INTERVALS_SOURCE_PATH)
            show_latest_hrv_summaries()
            return

        _qprint("")
        _qprint("▶️  Ejecutando build_hrv_core.py...")
        _qprint("")
        result = run_build_hrv_core(rr_files)
        if result is None:
            return

        if result.stdout:
            print(result.stdout)

        post_process_dates = get_existing_dates_from_master() if PANDAS_AVAILABLE else set()
        new_dates = sorted(post_process_dates - pre_process_dates) if PANDAS_AVAILABLE else []
        if new_dates:
            merged_dates = set(new_dates)
            merged_dates.update(_default_sleep_refresh_dates())
            target_dates = sorted(merged_dates)
        else:
            target_dates = _default_sleep_refresh_dates()
        _qprint("")
        _qprint(f"▶️  Actualizando sleep.csv ({len(target_dates)} fecha(s))...")
        _update_sleep_for_dates(access_token, x_user_id, target_dates)

        _qprint("")
        _qprint("▶️  Ejecutando build_hrv_final_dashboard.py...")
        _qprint("")
        run_build_hrv_final_dashboard_only()

        if not QUIET:
            print("")
            print("✅ Procesamiento HRV completado")
            print("")
            print("📄 Archivos actualizados:")
            print("   - ENDURANCE_HRV_master_CORE.csv")
            print("   - ENDURANCE_HRV_master_BETA_AUDIT.csv")
            print("   - ENDURANCE_HRV_master_FINAL.csv")
            print("   - ENDURANCE_HRV_master_DASHBOARD.csv")
        _send_intervals_wellness_from_master(INTERVALS_SOURCE_PATH)
        show_latest_hrv_summaries()
    else:
        _send_intervals_wellness_from_master(INTERVALS_SOURCE_PATH)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nInterrumpido por el usuario.")
    except Exception as e:
        print(f"\n❌ ERROR INESPERADO: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)


