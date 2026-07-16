from __future__ import annotations

import shutil
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

try:
    import pandas as pd
except ImportError:  # pragma: no cover - pandas is expected in runtime requirements
    pd = None

from . import config
from .config import PANDAS_AVAILABLE, SLEEP_PATH
from .io_utils import write_csv_atomic
from .polar_gateway import fetch_polar_nightly_recharge_result, fetch_polar_sleep_result
from .polar_utils import _parse_yyyy_mm_dd, parse_duration_to_minutes, parse_float


SLEEP_COLUMNS = [
    "Fecha",
    "polar_sleep_duration_min",
    "polar_sleep_span_min",
    "polar_deep_pct",
    "polar_rem_pct",
    "polar_efficiency_pct",
    "polar_continuity",
    "polar_continuity_index",
    "polar_interruptions_long",
    "polar_interruptions_total",
    "polar_sleep_score",
    "polar_night_rmssd",
    "polar_night_rri",
    "polar_night_resp",
    "sleep_dur_p10",
    "sleep_dur_p90",
    "sleep_int_p90",
]

SLEEP_SIGNAL_COLUMNS = [col for col in SLEEP_COLUMNS if col not in {"Fecha", "sleep_dur_p10", "sleep_dur_p90", "sleep_int_p90"}]
SLEEP_PENDING_WINDOW_DAYS = 7


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
    if minutes > 1440:
        if minutes <= 172800:
            return minutes / 60.0
        if minutes <= 172800000:
            return minutes / 60000.0
    return minutes


def _normalize_resp_rate(value) -> Optional[float]:
    """Normalize nightly respiration to breaths/min."""
    v = parse_float(value)
    if v is None or v <= 0:
        return None
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


def _extract_interruptions_counts(sleep_json: dict) -> tuple[Optional[float], Optional[float]]:
    if not isinstance(sleep_json, dict):
        return None, None

    evaluation = _find_first_value(sleep_json, ["evaluation", "sleep-evaluation", "sleep_evaluation"], as_float=False)
    interruptions = None
    if isinstance(evaluation, dict):
        interruptions = _find_first_value(
            evaluation,
            ["interruptions", "sleep-interruptions", "sleep_interruptions"],
            as_float=False,
        )

    long_count = None
    total_count = None
    if isinstance(interruptions, dict):
        long_count = parse_float(_find_first_value(interruptions, ["longCount", "long_count", "long-count"], as_float=True))
        total_count = parse_float(_find_first_value(interruptions, ["totalCount", "total_count", "total-count", "count"], as_float=True))
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

    dur = out["polar_sleep_duration_min"].dropna()
    out["sleep_dur_p10"] = float(dur.quantile(0.10)) if len(dur) > 0 else float("nan")
    out["sleep_dur_p90"] = float(dur.quantile(0.90)) if len(dur) > 0 else float("nan")

    ints = out["polar_interruptions_long"].dropna()
    out["sleep_int_p90"] = float(ints.quantile(0.90)) if len(ints) > 0 else float("nan")

    return out


def upsert_sleep_row(sleep_row: Dict[str, Any]) -> bool:
    if not PANDAS_AVAILABLE or pd is None:
        print("⚠️  Pandas no disponible: se omite actualización de sleep.csv")
        return False

    fecha = str(sleep_row.get("Fecha", "")).strip()
    if not fecha:
        return False

    if SLEEP_PATH.exists():
        try:
            sleep_df = pd.read_csv(SLEEP_PATH)
            missing = [c for c in SLEEP_COLUMNS if c not in sleep_df.columns]
            if missing:
                raise ValueError(
                    f"columnas canónicas ausentes en {SLEEP_PATH.name}: {missing!r} — "
                    f"archivo truncado o de generación incompatible"
                )
            extras = [c for c in sleep_df.columns if c not in set(SLEEP_COLUMNS)]
            if extras:
                raise ValueError(
                    f"columnas no canónicas en {SLEEP_PATH.name}: {extras!r} — "
                    f"esquema incompatible"
                )
            if sleep_df.empty or sleep_df.dropna(how="all").empty:
                raise ValueError(
                    f"archivo existente sin registros en {SLEEP_PATH.name} — "
                    f"posible truncado; eliminar el archivo para iniciar desde cero"
                )
        except Exception as e:
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            quarantine = None
            for _attempt in range(100):
                suffix = f"_{_attempt}" if _attempt else ""
                candidate = SLEEP_PATH.with_name(SLEEP_PATH.name + f".corrupt.{ts}{suffix}")
                try:
                    candidate.open("x").close()
                    quarantine = candidate
                    break
                except FileExistsError:
                    continue
                except OSError:
                    break
            copied = False
            if quarantine is not None:
                try:
                    shutil.copy2(SLEEP_PATH, quarantine)
                    copied = True
                except OSError:
                    try:
                        quarantine.unlink(missing_ok=True)
                    except OSError:
                        pass
                    quarantine = None
            copy_msg = quarantine.name if copied else "(copia fallida)"
            raise RuntimeError(
                f"[FAIL-CLOSED] {SLEEP_PATH.name} existe pero no se puede leer ({e}). "
                f"Copia en: {copy_msg}. Reparar o restaurar antes de continuar."
            ) from e
    else:
        sleep_df = pd.DataFrame(columns=SLEEP_COLUMNS)

    sleep_df = _ensure_sleep_schema(sleep_df)
    sleep_df = sleep_df[sleep_df["Fecha"].astype(str) != fecha]

    row = {col: sleep_row.get(col, float("nan")) for col in SLEEP_COLUMNS}
    row["Fecha"] = fecha

    sleep_df = pd.concat([sleep_df, pd.DataFrame([row])], ignore_index=True)
    sleep_df = _recalculate_sleep_derived(sleep_df)
    sleep_df = sleep_df[SLEEP_COLUMNS]

    write_csv_atomic(sleep_df, SLEEP_PATH)
    return True


def _polar_sleep_date_candidates(date_str: str) -> List[str]:
    # Try the exact requested date first, then fall back to the previous day.
    # Polar sleep can be late or shifted around midnight, so the fallback
    # preserves coverage when the exact day is not available.
    try:
        requested = _parse_yyyy_mm_dd(date_str)
        previous_day = (requested - timedelta(days=1)).isoformat()
        return [date_str, previous_day]
    except Exception:
        return [date_str]


def fetch_and_upsert_sleep_result(token: str, user_id: Optional[str], processed_date) -> dict:
    """Fetch+upsert one date with an explicit pending/error distinction."""
    if processed_date is None:
        return {"status": "pending", "outcome": "invalid_date", "date": None}

    date_str = processed_date.isoformat() if hasattr(processed_date, "isoformat") else str(processed_date)
    if not date_str:
        return {"status": "pending", "outcome": "invalid_date", "date": None}

    sleep_row: Dict[str, Any] = {col: float("nan") for col in SLEEP_COLUMNS}
    sleep_row["Fecha"] = date_str
    sleep_json = None
    sleep_used_date = None
    nightly_json = None
    nightly_used_date = None
    request_error = False

    for candidate_date in _polar_sleep_date_candidates(date_str):
        if sleep_json is None:
            response = fetch_polar_sleep_result(token, user_id, candidate_date)
            resp = response.get("data")
            outcome = str(response.get("outcome") or "no_data_yet")
            if outcome == "request_error":
                request_error = True
            if isinstance(resp, dict) and resp:
                sleep_json = resp
                sleep_used_date = candidate_date
        if nightly_json is None:
            response2 = fetch_polar_nightly_recharge_result(token, user_id, candidate_date)
            resp2 = response2.get("data")
            outcome = str(response2.get("outcome") or "no_data_yet")
            if outcome == "request_error":
                request_error = True
            if isinstance(resp2, dict) and resp2:
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

    if not any(pd.notna(sleep_row.get(col)) for col in SLEEP_SIGNAL_COLUMNS):
        outcome = "request_error" if request_error else "no_data_yet"
        print(f"ℹ️  Sin datos de sueño para {date_str}; no se escribe fila ({outcome})")
        return {"status": "pending", "outcome": outcome, "date": date_str}

    try:
        saved = upsert_sleep_row(sleep_row)
    except Exception as exc:
        return {
            "status": "failed",
            "outcome": "integrity_error" if "FAIL-CLOSED" in str(exc) else "write_error",
            "date": date_str,
            "error": {"code": "sleep_write_failed", "message": "No se pudo escribir sleep.csv"},
        }
    return {"status": "ok" if saved else "pending", "outcome": "data_found" if saved else "no_data_yet", "date": date_str}


def _update_sleep_for_dates_result(token: str, user_id: Optional[str], dates_to_sync: List) -> dict:
    result = {"attempted": [], "updated": [], "pending": [], "failed": []}
    seen = set()
    for d in dates_to_sync or []:
        if d is None:
            continue
        key = d.isoformat() if hasattr(d, "isoformat") else str(d)
        if key in seen:
            continue
        seen.add(key)
        result["attempted"].append(key)
        try:
            item = fetch_and_upsert_sleep_result(token, user_id, d)
        except Exception as exc:
            item = {"status": "failed", "outcome": "request_error", "date": key, "error": {"code": "sleep_fetch_failed", "message": "No se pudo consultar Polar sleep"}}
        if item.get("status") == "ok":
            result["updated"].append(key)
        elif item.get("status") == "failed":
            result["failed"].append({"date": key, "outcome": item.get("outcome"), "error": item.get("error")})
        else:
            result["pending"].append({"date": key, "outcome": item.get("outcome")})
    return result


def pending_sleep_dates_for_core(core_dates: List, window_days: int = SLEEP_PENDING_WINDOW_DAYS) -> list[str]:
    """Find recent CORE dates without any usable sleep signal."""
    if not core_dates or not PANDAS_AVAILABLE or pd is None:
        return []
    today = datetime.now().date()
    lower = today - timedelta(days=max(window_days - 1, 0))
    sleep_by_date = {}
    if SLEEP_PATH.exists():
        try:
            sleep_df = pd.read_csv(SLEEP_PATH)
            for _, row in sleep_df.iterrows():
                key = str(row.get("Fecha") or "").strip()
                if key:
                    sleep_by_date[key] = any(pd.notna(row.get(col)) for col in SLEEP_SIGNAL_COLUMNS)
        except Exception:
            return []
    pending = []
    for raw in core_dates:
        key = raw.isoformat() if hasattr(raw, "isoformat") else str(raw)
        try:
            day = _parse_yyyy_mm_dd(key)
        except Exception:
            continue
        if lower <= day <= today and not sleep_by_date.get(key, False):
            pending.append(key)
    return sorted(set(pending))


def _today_date():
    return datetime.now().date()


def _default_sleep_refresh_dates() -> List:
    today = _today_date()
    return [today, today - timedelta(days=1)]
