#!/usr/bin/env python3
from __future__ import annotations

import csv
import gzip
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from build_sessions import IntervalsClient
try:
    from fitparse import FitFile
except Exception:  # pragma: no cover - optional import at runtime
    FitFile = None

_ANALYSIS_DIR = Path(__file__).resolve().parent
if str(_ANALYSIS_DIR) not in sys.path:
    sys.path.insert(0, str(_ANALYSIS_DIR))
from fit_speed_utils import compute_speed_metrics as _compute_speed_metrics
from fit_terrain_utils import analyze_fit_climbs, parse_fit_terrain_data

from hrv_app.hrv_sync_flow import extract_rr_ms, write_rr_csv
from hrv_app.polar_client import get_exercise_with_samples, list_exercises
from hrv_app.polar_oauth_local import load_tokens
from hrv_app.polar_sessions import match_polar_exercise
from hrv_app.polar_utils import parse_float, weighted_mean as _weighted_mean
from training_audit_utils import (
    session_report_evidence,
    summary_training_audit,
    training_audit_dataset_limits,
    training_audit_metric_state,
    training_audit_session_affected,
    training_audit_session_flags,
)


ANALYSIS_DIR = ROOT / "analysis"
DEFAULT_SESSIONS_CSV = ROOT / "data" / "ENDURANCE_HRV_sessions.csv"
DEFAULT_REPORTS_DIR = ANALYSIS_DIR / "reports"
DEFAULT_BUNDLE_ROOT = ANALYSIS_DIR / ".cache" / "session_bundles"
ANALYZER_SCRIPT = ANALYSIS_DIR / "endurance_rr_session_v4.py"
EXPECTED_CONTRACT_VERSIONS = {
    "SESSION_ANALYSIS_METHOD.md": "1.3",
    "ENDURANCE_AGENT_DOMAIN.md": "1.3",
}
ANALYST_PROMPT_RULES_PATH = ANALYSIS_DIR / "analyst_prompt_rules.md"

def style_reference_paths(limit: int = 3) -> list[str]:
    candidates = [
        ANALYSIS_DIR / "delete",
        ROOT / "delete",
    ]
    paths: list[str] = []
    for base in candidates:
        if not base.exists():
            continue
        for path in sorted(base.glob("session_report_*.md"), reverse=True):
            paths.append(str(path))
            if len(paths) >= limit:
                return paths
    return paths


def infer_sport_family(summary: dict[str, Any]) -> str | None:
    direct = summary.get("session_meta", {}).get("sport_family") or summary.get("session_row", {}).get("sport_family")
    if direct:
        return str(direct)
    session_row = summary.get("session_row") or {}
    if isinstance(session_row, dict) and session_row.get("sport"):
        return analyzer_sport_from_session(session_row)
    return None


def rr_sections_visible(summary: dict[str, Any]) -> bool:
    if summary.get("rr_unavailable", False):
        return False
    modifier = (summary.get("rr_context") or {}).get("modifier")
    if modifier in {"unavailable", "no_rr"}:
        return False
    return True


def summarize_runtime_error(error: Any) -> str:
    text = str(error or "").strip()
    if not text:
        return "error no especificado"
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("<"):
            continue
        return line
    return text.splitlines()[0].strip()


def read_contract_version(path: Path) -> str | None:
    if not path.exists():
        return None
    try:
        head = path.read_text(encoding="utf-8").splitlines()[:5]
    except Exception:
        return None
    pattern = re.compile(r"contract_version:\s*([0-9]+\.[0-9]+)")
    for line in head:
        match = pattern.search(line)
        if match:
            return match.group(1)
    return None


def contract_version_status() -> dict[str, Any]:
    contracts = {
        "SESSION_ANALYSIS_METHOD.md": ANALYSIS_DIR / "SESSION_ANALYSIS_METHOD.md",
        "ENDURANCE_AGENT_DOMAIN.md": ANALYSIS_DIR / "ENDURANCE_AGENT_DOMAIN.md",
    }
    warnings: list[str] = []
    details: dict[str, Any] = {}
    for name, path in contracts.items():
        expected = EXPECTED_CONTRACT_VERSIONS.get(name)
        actual = read_contract_version(path)
        status = "ok"
        if actual is None:
            status = "missing_version"
            warnings.append(f"{name} sin contract_version; expected {expected}")
        elif expected != actual:
            status = "mismatch"
            warnings.append(f"{name} contract_version={actual}; expected {expected}")
        details[name] = {
            "path": str(path),
            "expected": expected,
            "actual": actual,
            "status": status,
        }
    return {
        "status": "ok" if not warnings else "warning",
        "warnings": warnings,
        "contracts": details,
    }


def load_sessions_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def select_session_row(rows: list[dict[str, str]], session_id: str | None = None) -> dict[str, str]:
    if session_id:
        for row in rows:
            if row.get("session_id") == session_id:
                return row
        raise ValueError(f"session_id not found: {session_id}")

    candidates = [row for row in rows if (row.get("Fecha") or "").strip()]
    if not candidates:
        raise ValueError("sessions.csv has no dated rows")
    candidates.sort(key=lambda row: (row.get("Fecha", ""), row.get("start_time", ""), row.get("session_id", "")))
    return candidates[-1]


def build_session_slug(row: dict[str, str]) -> str:
    date = (row.get("Fecha") or "unknown-date").strip()
    time_str = (row.get("start_time") or "unknown-time").strip().replace(":", "-")
    sport = (row.get("sport") or "unknown").strip()
    session_id = (row.get("session_id") or "unknown").strip()
    return f"{date}_{time_str}_{sport}_{session_id}"


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def write_terrain_intervals_csv(path: Path, rows: list[dict[str, Any]]) -> Path | None:
    if not rows:
        return None
    fieldnames = [
        "session_id",
        "split_source",
        "split_type",
        "split_index",
        "terrain_class",
        "vam_eligible",
        "distance_km",
        "elapsed_time_s",
        "start_time_s",
        "end_time_s",
        "moving_time_s",
        "average_speed_kmh",
        "gap_kmh",
        "average_gradient",
        "average_gradient_pct",
        "elev_gain_m",
        "average_cadence",
        "average_heartrate",
        "intensity",
        "zone",
        "power_mean",
        "power_source",
        "vam_mh",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field) for field in fieldnames})
    return path


def write_terrain_climbs_csv(path: Path, rows: list[dict[str, Any]]) -> Path | None:
    if not rows:
        return None
    fieldnames = [
        "climb_index",
        "start_sec",
        "end_sec",
        "duration_s",
        "distance_km",
        "elev_gain_m",
        "grade_mean_pct",
        "vam_mh",
        "hr_mean",
        "hr_max",
        "cadence_mean",
        "power_mean",
        "power_max",
        "hr_available",
        "cadence_available",
        "power_available",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field) for field in fieldnames})
    return path


def load_optional_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def row_by_date(path: Path, date_str: str) -> dict[str, str] | None:
    rows = load_optional_rows(path)
    for row in reversed(rows):
        if row.get("Fecha") == date_str:
            return row
    return None


def compact_row(row: dict[str, str] | None, keys: list[str]) -> dict[str, Any] | None:
    if not row:
        return None
    return {key: row.get(key) for key in keys}


def load_optional_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _get_intervals_client() -> IntervalsClient:
    from build_sessions import API_KEY, ATHLETE_ID

    if not API_KEY or not ATHLETE_ID:
        raise RuntimeError("faltan INTERVALS_API_KEY o INTERVALS_ATHLETE_ID")
    return IntervalsClient(API_KEY, ATHLETE_ID)


def _is_indoor_session(row: dict[str, str]) -> bool:
    tokens = [
        row.get("sport_raw"),
        row.get("polar_sport_raw"),
        row.get("sub_sport"),
        row.get("sport"),
    ]
    text = " ".join(str(token or "").lower() for token in tokens)
    return any(marker in text for marker in ("indoor", "treadmill", "virtualrun", "virtual_run"))


def _supports_terrain_context(row: dict[str, str]) -> bool:
    if _is_indoor_session(row):
        return False
    return analyzer_sport_from_session(row) in {"road", "trail", "hike"}


def fetch_intervals_activity_terrain_context(row: dict[str, str]) -> dict[str, Any]:
    session_id = row.get("session_id")
    if not session_id:
        raise ValueError("session row has no session_id")

    client = _get_intervals_client()
    activity = client.get(f"/activity/{session_id}").json()

    gap_mean = parse_float(activity.get("gap"))
    gap_model_raw = activity.get("gap_model")
    gap_model = str(gap_model_raw).strip() if gap_model_raw is not None else None
    if gap_model == "":
        gap_model = None

    return {
        "source": "intervals_activity",
        "gap_mean": round(gap_mean * 3.6, 1) if gap_mean is not None else None,
        "gap_unit": "km/h",
        "gap_model": gap_model,
        "vam_uphill_mean": None,
        "vam_source": None,
    }


def _extract_intervals_payload_rows(payload: Any) -> tuple[list[dict[str, Any]], str | None]:
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)], "root_list"
    if isinstance(payload, dict):
        for key in ("icu_intervals", "intervals", "laps", "splits", "items", "data"):
            value = payload.get(key)
            if isinstance(value, list):
                return [row for row in value if isinstance(row, dict)], key
        return [], "unrecognized_dict_payload"
    return [], f"unsupported_payload_type:{type(payload).__name__}"


def _terrain_class_from_gradient(average_gradient: float | None) -> str:
    if average_gradient is None:
        return "unknown"
    if average_gradient >= 0.02:
        return "uphill"
    if average_gradient <= -0.01:
        return "downhill"
    return "rolling"


def _normalize_terrain_interval_rows(
    session_id: str,
    payload: Any,
    fit_records: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    extracted_rows, _source_key = _extract_intervals_payload_rows(payload)
    for split_index, row in enumerate(extracted_rows, start=1):
        distance_m = parse_float(row.get("distance"))
        elapsed_time_s = parse_float(row.get("elapsed_time"))
        start_time_s = parse_float(row.get("start_time"))
        end_time_s = parse_float(row.get("end_time"))
        moving_time_s = parse_float(row.get("moving_time"))
        average_speed = parse_float(row.get("average_speed"))
        gap = parse_float(row.get("gap"))
        average_gradient = parse_float(row.get("average_gradient"))
        elev_gain_m = parse_float(row.get("total_elevation_gain"))
        average_cadence = parse_float(row.get("average_cadence"))
        average_heartrate = parse_float(row.get("average_heartrate"))
        intensity = parse_float(row.get("intensity"))
        zone = parse_float(row.get("zone"))
        power_mean = None
        power_source = None
        for source_name, field_name in (
            ("intervals_native_average_watts", "average_watts"),
            ("intervals_native_weighted_average_watts", "weighted_average_watts"),
            ("intervals_native_average_watts_alt", "average_watts_alt"),
            ("intervals_native_average_watts_alt_acc", "average_watts_alt_acc"),
        ):
            native_power = parse_float(row.get(field_name))
            if native_power is not None:
                power_mean = native_power
                power_source = source_name
                break
        if power_mean is None and fit_records is not None and start_time_s is not None and end_time_s is not None:
            power_values = []
            for fit_row in fit_records:
                fit_sec = parse_float(fit_row.get("sec"))
                fit_power = parse_float(fit_row.get("power"))
                if fit_sec is None or fit_power is None:
                    continue
                if start_time_s <= fit_sec < end_time_s:
                    power_values.append(fit_power)
            if power_values:
                power_mean = sum(power_values) / len(power_values)
                power_source = "fit_record_window"

        distance_km = None if distance_m is None else distance_m / 1000.0
        if (distance_km is None or distance_km < 0.1) and (elapsed_time_s is None or elapsed_time_s < 30.0):
            continue

        terrain_class = _terrain_class_from_gradient(average_gradient)
        vam_eligible = bool(
            elapsed_time_s is not None
            and elapsed_time_s >= 60.0
            and elev_gain_m is not None
            and elev_gain_m >= 10.0
            and average_gradient is not None
            and average_gradient >= 0.02
        )
        vam_mh = None
        if vam_eligible and elapsed_time_s and elapsed_time_s > 0:
            vam_mh = elev_gain_m / (elapsed_time_s / 3600.0)

        normalized.append(
            {
                "session_id": session_id,
                "split_source": "icu_intervals",
                "split_type": "interval",
                "split_index": split_index,
                "terrain_class": terrain_class,
                "vam_eligible": 1 if vam_eligible else 0,
                "distance_km": round(distance_km, 3) if distance_km is not None else None,
                "elapsed_time_s": round(elapsed_time_s, 1) if elapsed_time_s is not None else None,
                "start_time_s": round(start_time_s, 1) if start_time_s is not None else None,
                "end_time_s": round(end_time_s, 1) if end_time_s is not None else None,
                "moving_time_s": round(moving_time_s, 1) if moving_time_s is not None else None,
                "average_speed_kmh": round(average_speed * 3.6, 2) if average_speed is not None else None,
                "gap_kmh": round(gap * 3.6, 2) if gap is not None else None,
                "average_gradient": round(average_gradient, 4) if average_gradient is not None else None,
                "average_gradient_pct": round(average_gradient * 100.0, 1) if average_gradient is not None else None,
                "elev_gain_m": round(elev_gain_m, 1) if elev_gain_m is not None else None,
                "average_cadence": round(average_cadence, 1) if average_cadence is not None else None,
                "average_heartrate": round(average_heartrate, 1) if average_heartrate is not None else None,
                "intensity": round(intensity, 1) if intensity is not None else None,
                "zone": int(zone) if zone is not None else None,
                "power_mean": round(power_mean, 1) if power_mean is not None else None,
                "power_source": power_source,
                "vam_mh": round(vam_mh, 1) if vam_mh is not None else None,
            }
        )
    return normalized


def _summarize_terrain_context_from_intervals(
    base_context: dict[str, Any],
    interval_rows: list[dict[str, Any]],
    session_row: dict[str, str] | None = None,
) -> dict[str, Any]:
    context = dict(base_context)
    split_distance_km_total = round(sum(parse_float(row.get("distance_km")) or 0.0 for row in interval_rows), 2)
    session_distance_km = parse_float((session_row or {}).get("distance_km")) if isinstance(session_row, dict) else None
    context.update(
        {
            "source": "intervals_activity+icu_intervals",
            "split_source": "icu_intervals",
            "split_count": len(interval_rows),
            "split_distance_km_total": split_distance_km_total,
            "gap_split_weighting": "distance_km",
            "split_coverage_pct": round((split_distance_km_total / session_distance_km) * 100.0, 1)
            if session_distance_km and session_distance_km > 0
            else None,
        }
    )

    for terrain_class in ("uphill", "rolling", "downhill", "unknown"):
        class_rows = [row for row in interval_rows if row.get("terrain_class") == terrain_class]
        context[f"{terrain_class}_split_count"] = len(class_rows)
        gap_mean = _weighted_mean(class_rows, "gap_kmh", "distance_km")
        context[f"gap_{terrain_class}_mean"] = round(gap_mean, 1) if gap_mean is not None else None
        power_mean = _weighted_mean(class_rows, "power_mean", "elapsed_time_s")
        context[f"power_{terrain_class}_mean"] = round(power_mean, 1) if power_mean is not None else None

    vam_rows = [row for row in interval_rows if row.get("vam_eligible") == 1 and parse_float(row.get("vam_mh")) is not None]
    if vam_rows:
        vam_mean = _weighted_mean(vam_rows, "vam_mh", "elapsed_time_s")
        context["vam_uphill_mean"] = round(vam_mean, 1) if vam_mean is not None else None
        context["vam_uphill_max"] = round(max(parse_float(row.get("vam_mh")) or 0.0 for row in vam_rows), 1)
        context["vam_uphill_time_min"] = round(
            sum(parse_float(row.get("elapsed_time_s")) or 0.0 for row in vam_rows) / 60.0,
            1,
        )
        context["vam_uphill_split_count"] = len(vam_rows)
        context["vam_source"] = "icu_intervals_uphill_filtered"
    else:
        context["vam_uphill_mean"] = None
        context["vam_uphill_max"] = None
        context["vam_uphill_time_min"] = None
        context["vam_uphill_split_count"] = 0
        context["vam_source"] = "icu_intervals_uphill_filtered_no_matches"
    return context


def fetch_intervals_terrain_interval_rows(row: dict[str, str], fit_path: Path | None = None) -> list[dict[str, Any]]:
    session_id = row.get("session_id")
    if not session_id:
        raise ValueError("session row has no session_id")

    client = _get_intervals_client()
    payload = client.get(f"/activity/{session_id}/intervals").json()
    rows, source_key = _extract_intervals_payload_rows(payload)
    if source_key in {"unrecognized_dict_payload"} or (source_key or "").startswith("unsupported_payload_type:"):
        raise RuntimeError(f"intervals payload shape not recognized: {source_key}")
    fit_records = None
    if fit_path is not None and fit_path.exists():
        fit_records = parse_fit_terrain_data(fit_path)["records"]
    return _normalize_terrain_interval_rows(session_id, payload, fit_records=fit_records)


def fetch_intervals_stream_csv(row: dict[str, str], target_csv: Path) -> dict[str, Any]:
    session_id = row.get("session_id")
    if not session_id:
        raise ValueError("session row has no session_id")

    client = _get_intervals_client()
    streams = client.get_streams(session_id, "heartrate,velocity_smooth,cadence")

    hr = streams.get("heartrate")
    vel = streams.get("velocity_smooth")
    cad = streams.get("cadence")
    if hr is None or len(hr) == 0:
        raise RuntimeError(f"Intervals streams sin heartrate para {session_id}")

    max_len = max(len(arr) for arr in [hr, vel, cad] if arr is not None and len(arr) > 0)

    def value_at(arr, idx):
        if arr is None or idx >= len(arr):
            return None
        val = arr[idx]
        try:
            f = float(val)
        except (TypeError, ValueError):
            return None
        if f != f:
            return None
        return f

    rows: list[dict[str, Any]] = []
    for idx in range(max_len):
        hr_v = value_at(hr, idx)
        vel_v = value_at(vel, idx)
        cad_v = value_at(cad, idx)
        rows.append(
            {
                "sec": float(idx),
                "hr": hr_v,
                "speed_kmh": None if vel_v is None else round(vel_v * 3.6, 6),
                "cadence": cad_v,
            }
        )

    target_csv.parent.mkdir(parents=True, exist_ok=True)
    with target_csv.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["sec", "hr", "speed_kmh", "cadence"])
        writer.writeheader()
        writer.writerows(rows)

    return {
        "rows": len(rows),
        "hr_points": len(hr) if hr is not None else 0,
        "velocity_points": len(vel) if vel is not None else 0,
        "cadence_points": len(cad) if cad is not None else 0,
    }


def fetch_intervals_fit_file(row: dict[str, str], target_fit: Path) -> dict[str, Any]:
    session_id = row.get("session_id")
    if not session_id:
        raise ValueError("session row has no session_id")

    client = _get_intervals_client()
    response = client.get(f"/activity/{session_id}/fit-file")
    payload = response.content
    if not payload:
        raise RuntimeError(f"Intervals devolvio un FIT vacio para {session_id}")

    try:
        fit_bytes = gzip.decompress(payload)
        compressed = True
    except (OSError, EOFError):
        fit_bytes = payload
        compressed = False

    target_fit.parent.mkdir(parents=True, exist_ok=True)
    target_fit.write_bytes(fit_bytes)

    if FitFile is None:
        raise RuntimeError("fitparse is not installed; no se puede validar el FIT descargado")
    try:
        fit = FitFile(str(target_fit))
        session_msg = next(iter(fit.get_messages("session")), None)
        record_msg = next(iter(fit.get_messages("record")), None)
        if session_msg is None and record_msg is None:
            raise RuntimeError("FIT descargado sin mensajes session ni record")
    except Exception as exc:
        try:
            target_fit.unlink()
        except OSError:
            pass
        raise RuntimeError(f"FIT descargado invalido para {session_id}: {exc}") from exc

    return {
        "bytes": len(fit_bytes),
        "compressed_source": compressed,
        "source": "intervals_fit_file",
    }


def _target_session_datetime(row: dict[str, str]) -> datetime:
    date_str = (row.get("Fecha") or "").strip()
    time_str = (row.get("start_time") or "").strip()
    if not date_str or not time_str:
        raise ValueError("session row lacks Fecha/start_time")
    return datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M")

def _match_polar_exercise(row: dict[str, str], exercises: list[dict[str, Any]]) -> dict[str, Any]:
    return match_polar_exercise(
        row,
        exercises,
        tz_offset_min=int(os.environ.get("POLAR_TZ_OFFSET_MIN", "0")),
    )


def fetch_session_rr_csv(row: dict[str, str], target_csv: Path) -> dict[str, Any]:
    token, _user = load_tokens()
    if not token:
        raise RuntimeError("token Polar ausente o expirado")

    exercises = list_exercises(token)
    match = _match_polar_exercise(row, exercises)
    ex = get_exercise_with_samples(token, match["exercise"]["id"])
    rr = extract_rr_ms(ex)
    if not rr:
        raise RuntimeError("el ejercicio Polar no contiene RR exportable")

    target_csv.parent.mkdir(parents=True, exist_ok=True)
    write_rr_csv(rr, str(target_csv))
    offline_pct = 100.0 * sum(1 for _, off in rr if off == 1) / max(1, len(rr))
    return {
        "polar_exercise_id": match["exercise"]["id"],
        "polar_start_delta_min": match["start_delta_min"],
        "polar_duration_gap_min": match["duration_gap_min"],
        "rr_count": len(rr),
        "offline_pct": round(offline_pct, 3),
    }


def prepare_bundle(
    sessions_csv: Path,
    bundle_root: Path,
    session_id: str | None = None,
) -> dict[str, Any]:
    rows = load_sessions_rows(sessions_csv)
    row = select_session_row(rows, session_id=session_id)
    slug = build_session_slug(row)
    bundle_dir = bundle_root / slug
    bundle_dir.mkdir(parents=True, exist_ok=True)

    session_json = bundle_dir / "session_row.json"
    stream_csv = bundle_dir / "session_stream.csv"
    fit_file = bundle_dir / "session.fit"
    rr_csv = bundle_dir / "session_rr.csv"
    manifest_path = bundle_dir / "bundle_manifest.json"

    write_json(session_json, row)
    stream_info = fetch_intervals_stream_csv(row, stream_csv)
    terrain_context = None
    terrain_error = None
    terrain_intervals = None
    terrain_intervals_error = None
    if _supports_terrain_context(row):
        try:
            terrain_context = fetch_intervals_activity_terrain_context(row)
        except Exception as exc:
            terrain_error = str(exc)
    fit_info = None
    fit_error = None
    try:
        fit_info = fetch_intervals_fit_file(row, fit_file)
    except Exception as exc:
        fit_error = str(exc)
    if terrain_context is not None:
        try:
            terrain_intervals = fetch_intervals_terrain_interval_rows(row, fit_path=fit_file if fit_file.exists() else None)
            terrain_context = _summarize_terrain_context_from_intervals(terrain_context, terrain_intervals, session_row=row)
        except Exception as exc:
            terrain_intervals_error = str(exc)
    rr_info = None
    rr_error = None
    try:
        rr_info = fetch_session_rr_csv(row, rr_csv)
    except Exception as exc:
        rr_error = str(exc)

    manifest = {
        "slug": slug,
        "bundle_dir": str(bundle_dir),
        "session_row_path": str(session_json),
        "session_id": row.get("session_id"),
        "sport": row.get("sport"),
        "date": row.get("Fecha"),
        "start_time": row.get("start_time"),
        "sessions_csv": str(sessions_csv),
        "hr_stream_csv": str(stream_csv),
        "fit_path": str(fit_file) if fit_info else None,
        "rr_csv": str(rr_csv) if rr_info else None,
        "stream_info": stream_info,
        "terrain_context": terrain_context,
        "terrain_error": terrain_error,
        "terrain_intervals": terrain_intervals,
        "terrain_intervals_error": terrain_intervals_error,
        "fit_info": fit_info,
        "fit_error": fit_error,
        "rr_info": rr_info,
        "rr_error": rr_error,
    }
    write_json(manifest_path, manifest)
    manifest["manifest_path"] = str(manifest_path)
    return manifest


def render_report_markdown(summary: dict[str, Any]) -> str:
    session_cost = summary.get("session_cost_model") or {}
    rr_context = summary.get("rr_context") or {}
    final_cost = summary.get("final_cost_interpretation") or {}
    terrain_context = summary.get("terrain_context") or {}
    terrain_fit_context = summary.get("terrain_fit_context") or {}
    rmssd_1m = summary.get("rmssd_1min") or {}
    rmssd_5m = summary.get("rmssd_5min") or {}
    training_audit = summary_training_audit(summary)
    signal_level = training_audit.get("signal_level") or {}
    sport_family = infer_sport_family(summary)
    rr_unavailable = summary.get("rr_unavailable", False)
    show_rr = rr_sections_visible(summary)

    lines = [
        f"# Session Analysis - {summary.get('session_cost_model', {}).get('session_id') or 'unknown'}",
        "",
        "## Sources",
        f"- rr_path: `{summary.get('rr_path')}`",
        f"- hr_source: `{summary.get('hr_source')}`",
        f"- sport_family: `{sport_family}`",
        f"- sessions_cost_usable: `{session_cost.get('usable')}`",
        "",
    ]

    audit_limitations = training_audit_dataset_limits(summary)
    coaching_state = training_audit_metric_state(summary, "coaching_load")
    zone_state = training_audit_metric_state(summary, "zone_intensity")
    drift_state = training_audit_metric_state(summary, "cardiac_drift")
    session_flags = training_audit_session_flags(summary)
    session_affected = training_audit_session_affected(summary)
    rr_error_summary = summarize_runtime_error(summary.get("rr_error"))
    terrain_intervals_error = summarize_runtime_error(summary.get("terrain_intervals_error"))
    terrain_fit_error = summarize_runtime_error(summary.get("terrain_fit_error"))

    if rr_unavailable:
        lines.extend([
            "## ⚠️ RR No Disponible",
            f"- motivo: {rr_error_summary}",
            "- impacto: no hay metricas de variabilidad (RMSSD, DFA, HR@0.75)",
            "- cobertura: analisis de coste y contexto intacto",
            "",
        ])

    lines.extend([
        "## Cost Model",
        f"- cardio_score: `{session_cost.get('cardio_score')}`",
        f"- mecanico_score: `{session_cost.get('mecanico_score')}`",
        f"- coste_dominante: `{session_cost.get('coste_dominante')}`",
        f"- confidence_cardio: `{session_cost.get('confidence_cardio')}`",
        f"- confidence_mecanico: `{session_cost.get('confidence_mecanico')}`",
        "",
        "## RR Context",
        f"- modifier: `{rr_context.get('modifier')}`",
        f"- interpretation: {rr_context.get('interpretation')}",
        f"- final_note: {final_cost.get('note')}",
        "",
    ])

    if terrain_context:
        lines.extend([
            "## Terrain Context",
            f"- source: `{terrain_context.get('source')}`",
            f"- gap_mean: `{terrain_context.get('gap_mean')}` {terrain_context.get('gap_unit') or ''}".rstrip(),
            f"- gap_model: `{terrain_context.get('gap_model')}`",
            f"- split_source: `{terrain_context.get('split_source')}`",
            f"- split_count: `{terrain_context.get('split_count')}`",
            f"- split_coverage_pct: `{terrain_context.get('split_coverage_pct')}`",
            f"- uphill_split_count: `{terrain_context.get('uphill_split_count')}`",
            f"- rolling_split_count: `{terrain_context.get('rolling_split_count')}`",
            f"- downhill_split_count: `{terrain_context.get('downhill_split_count')}`",
            f"- gap_uphill_mean: `{terrain_context.get('gap_uphill_mean')}`",
            f"- gap_rolling_mean: `{terrain_context.get('gap_rolling_mean')}`",
            f"- gap_downhill_mean: `{terrain_context.get('gap_downhill_mean')}`",
            f"- power_uphill_mean: `{terrain_context.get('power_uphill_mean')}`",
            f"- power_rolling_mean: `{terrain_context.get('power_rolling_mean')}`",
            f"- power_downhill_mean: `{terrain_context.get('power_downhill_mean')}`",
            f"- vam_uphill_mean: `{terrain_context.get('vam_uphill_mean')}`",
            f"- vam_uphill_max: `{terrain_context.get('vam_uphill_max')}`",
            f"- vam_uphill_time_min: `{terrain_context.get('vam_uphill_time_min')}`",
            f"- vam_uphill_split_count: `{terrain_context.get('vam_uphill_split_count')}`",
            f"- vam_source: `{terrain_context.get('vam_source')}`",
            "- note: contexto analitico de terreno; no arbitra el gate HRV",
            "",
        ])
    if summary.get("terrain_intervals_error"):
        lines.extend([
            "## Terrain Warnings",
            f"- intervals_error: {terrain_intervals_error}",
            "",
        ])

    if terrain_fit_context:
        validation_vs_v2 = terrain_fit_context.get("validation_vs_v2") or {}
        signals_available = terrain_fit_context.get("signals_available") or {}
        warnings = validation_vs_v2.get("warnings") or []
        infos = validation_vs_v2.get("infos") or []
        lines.extend([
            "## Terrain FIT Context",
            f"- climbs_source: `{terrain_fit_context.get('climbs_source')}`",
            f"- climb_count: `{terrain_fit_context.get('climb_count')}`",
            f"- climb_time_min: `{terrain_fit_context.get('climb_time_min')}`",
            f"- climb_distance_km: `{terrain_fit_context.get('climb_distance_km')}`",
            f"- climb_gain_m: `{terrain_fit_context.get('climb_gain_m')}`",
            f"- climb_gain_coverage_pct: `{terrain_fit_context.get('climb_gain_coverage_pct')}`",
            f"- climb_hr_mean: `{terrain_fit_context.get('climb_hr_mean')}`",
            f"- climb_cadence_mean: `{terrain_fit_context.get('climb_cadence_mean')}`",
            f"- cadence_unit: `{terrain_fit_context.get('cadence_unit')}`",
            f"- climb_power_mean: `{terrain_fit_context.get('climb_power_mean')}`",
            f"- climb_power_max: `{terrain_fit_context.get('climb_power_max')}`",
            f"- signals_available: `hr={signals_available.get('hr')}, cadence={signals_available.get('cadence')}, power={signals_available.get('power')}`",
            f"- pause_filter_mode: `{terrain_fit_context.get('pause_filter_mode')}`",
            f"- validation_status: `{validation_vs_v2.get('status')}`",
            f"- validation_warnings: `{', '.join(warnings) if warnings else 'none'}`",
            f"- validation_infos: `{', '.join(infos) if infos else 'none'}`",
            "- note: capa FIT paralela a V2; no recalcula GAP",
            "",
        ])
    if summary.get("terrain_fit_error"):
        lines.extend([
            "## Terrain FIT Warnings",
            f"- fit_error: {terrain_fit_error}",
            "",
        ])

    if training_audit:
        lines.extend([
            "## Training Audit",
            f"- coaching_load_state: `{coaching_state}`",
            f"- zone_intensity_state: `{zone_state}`",
            f"- cardiac_drift_state: `{drift_state}`",
            f"- sampling_ok: `{signal_level.get('sampling_ok')}`",
            "",
        ])
        if audit_limitations:
            lines.extend([
                "## Dataset Audit Limits",
                f"- interpretability_limits: `{', '.join(audit_limitations)}`",
                f"- session_affected: `{session_affected}`",
                "",
            ])
        if session_flags:
            lines.extend([
                "## Session Audit Flags",
                f"- flags: `{', '.join(session_flags)}`",
                "",
            ])

    if show_rr:
        lines.extend([
            "## Key Metrics",
            f"- dfa_gate: `{summary.get('dfa_gate', {}).get('state')}`",
            f"- hr_at_075_usable: `{summary.get('hr_at_075', {}).get('usable')}`",
            f"- hr_at_075: `{summary.get('hr_at_075', {}).get('hr_at_075')}`",
            f"- hr_at_075_crossing: `{summary.get('hr_at_075_crossing', {}).get('hr_at_075_crossing')}` (confidence: `{summary.get('hr_at_075_crossing', {}).get('confidence')}`)",
            f"- rmssd_1min_p50: `{summary.get('rmssd_1min', {}).get('p50')}`",
            f"- rmssd_5min_p50: `{summary.get('rmssd_5min', {}).get('p50')}`",
            f"- dfa_median: `{summary.get('dfa_alpha1', {}).get('median')}`",
            "",
            "## RMSSD",
            "",
            "| Window | P10 | P50 | P90 | Usable Windows | Total Windows |",
            "|---|---:|---:|---:|---:|---:|",
            f"| 1 min | {rmssd_1m.get('p10')} | {rmssd_1m.get('p50')} | {rmssd_1m.get('p90')} | {rmssd_1m.get('n_windows_usable')} | {rmssd_1m.get('n_windows_total')} |",
            f"| 5 min | {rmssd_5m.get('p10')} | {rmssd_5m.get('p50')} | {rmssd_5m.get('p90')} | {rmssd_5m.get('n_windows_usable')} | {rmssd_5m.get('n_windows_total')} |",
            "",
        ])

    lines.append("## Evidence")
    for item in session_cost.get("cardio_evidence") or []:
        lines.append(f"- cardio: {item}")
    for item in session_cost.get("mecanico_evidence") or []:
        lines.append(f"- mecanico: {item}")
    for category, item in session_report_evidence(summary):
        lines.append(f"- {category}: {item}")
    for item in rr_context.get("evidence") or []:
        lines.append(f"- rr: {summarize_runtime_error(item)}")
    return "\n".join(lines) + "\n"


def build_conversational_payload(
    summary: dict[str, Any],
    manifest: dict[str, Any],
    session_row: dict[str, str],
    artifacts_dir: Path | None = None,
) -> dict[str, Any]:
    sport_family = analyzer_sport_from_session(session_row)
    session_date = session_row.get("Fecha") or manifest.get("date")
    terrain_context = summary.get("terrain_context")
    terrain_fit_context = summary.get("terrain_fit_context")
    terrain_intervals_csv = None
    terrain_climbs_csv = None
    if artifacts_dir is not None:
        terrain_intervals_path = artifacts_dir / "terrain_intervals.csv"
        if terrain_intervals_path.exists():
            terrain_intervals_csv = str(terrain_intervals_path)
        terrain_climbs_path = artifacts_dir / "terrain_climbs.csv"
        if terrain_climbs_path.exists():
            terrain_climbs_csv = str(terrain_climbs_path)
    sessions_day = compact_row(
        row_by_date(ROOT / "data" / "ENDURANCE_HRV_sessions_day.csv", session_date),
        [
            "Fecha",
            "n_sessions",
            "load_day",
            "intensity_cat_day",
            "work_total_min_day",
            "work_n_blocks_day",
            "z3_min_day",
            "load_3d",
            "load_7d",
            "work_7d_sum",
            "z3_7d_sum",
            "elev_gain_day",
            "elev_loss_day",
            "elev_density_day",
        ],
    )
    sleep_row = compact_row(
        row_by_date(ROOT / "data" / "ENDURANCE_HRV_sleep.csv", session_date),
        [
            "Fecha",
            "polar_sleep_duration_min",
            "polar_sleep_score",
            "polar_efficiency_pct",
            "polar_night_rmssd",
            "polar_night_rri",
            "polar_night_resp",
        ],
    )
    final_row = compact_row(
        row_by_date(ROOT / "data" / "ENDURANCE_HRV_master_FINAL.csv", session_date),
        [
            "Fecha",
            "Calidad",
            "RMSSD_stable",
            "lnRMSSD_used",
            "HR_used",
            "d_ln",
            "d_HR",
            "residual_z",
            "gate_badge",
            "Action",
            "baseline60_degraded",
            "recovery_context_quality",
            "recovery_support_class",
            "recovery_discordance_flag",
            "recovery_discordance_reason",
            "reason_text",
        ],
    )
    dashboard_row = compact_row(
        row_by_date(ROOT / "data" / "ENDURANCE_HRV_master_DASHBOARD.csv", session_date),
        [
            "Fecha",
            "Calidad",
            "HR_today",
            "RMSSD_stable",
            "gate_badge",
            "Action",
            "baseline60_degraded",
            "reason_text",
        ],
    )
    sessions_metadata = load_optional_json(ROOT / "data" / "ENDURANCE_HRV_sessions_metadata.json")
    stream_sampling = None
    training_audit = None
    if sessions_metadata:
        stream_sampling = sessions_metadata.get("stream_sampling")
        training_audit = sessions_metadata.get("training_audit")
    versions = contract_version_status()

    # --- Vector velocidad desde FIT artifact ---
    speed_metrics: dict | None = None
    if artifacts_dir is not None:
        fit_artifact = artifacts_dir / "session.fit"
        vt1 = parse_float(session_row.get("vt1_used"))
        wbm = session_row.get("work_blocks_min") or ""
        wbn = len([x for x in wbm.split(";") if x.strip()]) if wbm else 0
        speed_metrics = _compute_speed_metrics(fit_artifact, vt1, wbn, sport_family)

    return {
        "meta": {
            "session_id": manifest.get("session_id"),
            "slug": manifest.get("slug"),
            "date": manifest.get("date"),
            "start_time": manifest.get("start_time"),
            "sport": manifest.get("sport"),
            "sport_family": sport_family,
        },
        "bundle_sources": {
            "fit_path": manifest.get("fit_path"),
            "fit_info": manifest.get("fit_info"),
            "fit_error": manifest.get("fit_error"),
            "hr_stream_csv": manifest.get("hr_stream_csv"),
            "rr_csv": manifest.get("rr_csv"),
            "terrain_error": manifest.get("terrain_error"),
            "terrain_intervals_error": manifest.get("terrain_intervals_error"),
            "terrain_fit_error": summary.get("terrain_fit_error"),
        },
        "session_row": session_row,
        "rr_analysis_summary": summary,
        "terrain_context": terrain_context,
        "terrain_fit_context": terrain_fit_context,
        "terrain_intervals_csv": terrain_intervals_csv,
        "terrain_climbs_csv": terrain_climbs_csv,
        "context": {
            "sessions_day": sessions_day,
            "sleep": sleep_row,
            "final": final_row,
            "dashboard": dashboard_row,
            "sessions_metadata": {
                "pipeline_version": sessions_metadata.get("pipeline_version") if sessions_metadata else None,
                "build_time": sessions_metadata.get("build_time") if sessions_metadata else None,
                "stream_sampling": stream_sampling,
                "training_audit": training_audit,
            }
            if sessions_metadata
            else None,
            "contract_versions": versions,
        },
        "narrative_targets": {
            "required_sections": [
                "Fuentes",
                "Calidad del dato",
                "Datos",
                "Estructura externa",
                "Respuesta interna",
                "Capa RR",
                "Contexto de recuperacion y carga",
                "Encaje en el bloque",
                "Conclusion",
                "Interpretacion fisiologica",
                "Implicacion practica",
                "Confianza",
                "Advertencias",
            ],
            "method_path": str(ANALYSIS_DIR / "SESSION_ANALYSIS_METHOD.md"),
            "domain_path": str(ANALYSIS_DIR / "ENDURANCE_AGENT_DOMAIN.md"),
            "style_reference_paths": style_reference_paths(),
            "sport_family": sport_family,
            "sport_family_notes": session_family_notes(sport_family),
        },
        "speed_metrics": speed_metrics,
    }


def enrich_summary_with_sessions_metadata(summary: dict[str, Any]) -> dict[str, Any]:
    enriched = dict(summary)
    if "rr_error" in enriched:
        enriched["rr_error_summary"] = summarize_runtime_error(enriched.get("rr_error"))
    sessions_metadata = load_optional_json(ROOT / "data" / "ENDURANCE_HRV_sessions_metadata.json")
    if not sessions_metadata:
        return enriched

    enriched_sessions_metadata = {
        "pipeline_version": sessions_metadata.get("pipeline_version"),
        "build_time": sessions_metadata.get("build_time"),
        "stream_sampling": sessions_metadata.get("stream_sampling"),
    }
    training_audit = sessions_metadata.get("training_audit")
    if training_audit is not None:
        enriched_sessions_metadata["training_audit"] = training_audit
    enriched["sessions_metadata"] = enriched_sessions_metadata
    enriched.pop("training_audit", None)
    return enriched


def enrich_summary_with_manifest_context(summary: dict[str, Any], manifest: dict[str, Any]) -> dict[str, Any]:
    enriched = dict(summary)
    summary_row = enriched.get("session_row")
    manifest_row = None
    session_row_path = manifest.get("session_row_path")
    if session_row_path:
        manifest_row = load_optional_json(Path(session_row_path))
    if isinstance(summary_row, dict) and isinstance(manifest_row, dict):
        merged_row = dict(summary_row)
        for key, value in manifest_row.items():
            existing = merged_row.get(key)
            if existing in (None, ""):
                merged_row[key] = value
        enriched["session_row"] = merged_row
    elif isinstance(manifest_row, dict):
        enriched["session_row"] = manifest_row
    terrain_context = manifest.get("terrain_context")
    if isinstance(terrain_context, dict) and terrain_context:
        enriched["terrain_context"] = terrain_context
    return enriched


def build_ai_handoff_markdown(
    report_dir: Path,
    artifacts_dir: Path,
    payload_path: Path,
    summary_path: Path,
    blocks_path: Path | None,
    terrain_intervals_path: Path | None,
    terrain_climbs_path: Path | None,
    debug_dir: Path | None,
) -> str:
    style_refs = style_reference_paths()
    versions = contract_version_status()
    lines = [
        "# AI Handoff",
        "",
    ]
    if versions["warnings"]:
        lines.extend(["## Contract Warnings"])
        lines.extend([f"- {warning}" for warning in versions["warnings"]])
        lines.append("")
    lines.extend(
        [
            "## Archivos principales a pasar a la IA",
            f"1. `{payload_path}`",
            f"2. `{ANALYSIS_DIR / 'SESSION_ANALYSIS_METHOD.md'}`",
            f"3. `{ANALYSIS_DIR / 'ENDURANCE_AGENT_DOMAIN.md'}`",
            "",
            "## Archivos de apoyo recomendados",
            f"- `{summary_path}`",
        ]
    )
    if blocks_path:
        lines.append(f"- `{blocks_path}`")
    if terrain_intervals_path:
        lines.append(f"- `{terrain_intervals_path}`")
    if terrain_climbs_path:
        lines.append(f"- `{terrain_climbs_path}`")
    if style_refs:
        lines.extend(["", "## Referencias de estilo opcionales"])
        lines.extend([f"- `{path}`" for path in style_refs])
    lines.extend(
        [
            "",
            "## Regla de uso",
            "- usar `session_payload.json` como fuente compacta principal",
            "- usar `SESSION_ANALYSIS_METHOD.md` para secciones obligatorias y metodo",
            "- usar `ENDURANCE_AGENT_DOMAIN.md` para tono, confianza e interpretacion",
            "- abrir `blocks.csv` solo si hace falta granularidad de bloques",
        ]
    )
    if debug_dir and debug_dir.exists():
        lines.extend(
            [
                "",
                "## Debug opcional",
                f"- `{debug_dir}`",
            ]
        )
    return "\n".join(lines) + "\n"


def build_analyst_prompt_markdown(
    report_dir: Path,
    payload_path: Path,
    summary_path: Path,
    blocks_path: Path | None,
    terrain_intervals_path: Path | None,
    terrain_climbs_path: Path | None,
) -> str:
    style_refs = style_reference_paths()
    versions = contract_version_status()

    rules_version: str | None = None
    if ANALYST_PROMPT_RULES_PATH.exists():
        first_line = ANALYST_PROMPT_RULES_PATH.read_text(encoding="utf-8").splitlines()[0].strip()
        m = re.match(r"<!--\s*rules_version:\s*([0-9]+\.[0-9]+)\s*-->", first_line)
        if m:
            rules_version = m.group(1)

    version_comment = f"<!-- generated_with_rules_version: {rules_version} -->" if rules_version else ""
    lines = [
        *([version_comment, ""] if version_comment else []),
        "# Analyst Prompt",
        "",
        "Usa Codex/GPT como analista conversacional sobre esta sesion.",
        "",
    ]
    if versions["warnings"]:
        lines.extend(["## Contract Warnings"])
        lines.extend([f"- {warning}" for warning in versions["warnings"]])
        lines.append("")
    lines.extend(
        [
            "## Archivos a usar",
            f"- payload principal: `{payload_path}`",
            f"- resumen tecnico: `{summary_path}`",
            f"- metodo: `{ANALYSIS_DIR / 'SESSION_ANALYSIS_METHOD.md'}`",
            f"- dominio: `{ANALYSIS_DIR / 'ENDURANCE_AGENT_DOMAIN.md'}`",
        ]
    )
    if blocks_path:
        lines.append(f"- bloques: `{blocks_path}`")
    if terrain_intervals_path:
        lines.append(f"- terreno por split: `{terrain_intervals_path}`")
    if terrain_climbs_path:
        lines.append(f"- climbs FIT: `{terrain_climbs_path}`")
    if style_refs:
        lines.extend(["", "## Referencias de estilo opcionales"])
        lines.extend([f"- `{path}`" for path in style_refs])
    lines.extend(
        [
            "",
            "## Instruccion",
            "Redacta un informe rico de sesion en espanol, con tono tecnico y prudente, usando `session_payload.json` como fuente compacta principal y sin inventar metricas ni fuentes no presentes.",
            "",
            "## Sport Family",
            "- usa `session_payload.json.meta.sport_family` como guia primaria de lenguaje y semantica",
            "- aplica las notas de familia incluidas en `session_payload.json.narrative_targets.sport_family_notes`",
            "- no traslades semantica de trail a `hike`, `elliptical`, `bike` o `swim` si la familia declarada no lo permite",
            "",
            "## Secciones obligatorias",
            "- Fuentes",
            "- Calidad del dato",
            "- Datos",
            "- Estructura externa",
            "- Respuesta interna",
            "- Capa RR",
            "- Contexto de recuperacion y carga",
            "- Encaje en el bloque",
            "- Conclusion",
            "- Interpretacion fisiologica",
            "- Implicacion practica",
            "- Confianza",
            "- Advertencias",
        ]
    )
    # Rules from external file (single source of truth)
    if ANALYST_PROMPT_RULES_PATH.exists():
        rules_raw = ANALYST_PROMPT_RULES_PATH.read_text(encoding="utf-8")
        # Strip the version comment line, keep everything else
        rules_lines = [
            line for line in rules_raw.splitlines()
            if not line.strip().startswith("<!-- ") and not line.strip().endswith("-->")
        ]
        lines.extend([""] + rules_lines)
    else:
        lines.extend(["", "## Reglas", f"- ADVERTENCIA: no se encontro {ANALYST_PROMPT_RULES_PATH}; aplica SESSION_ANALYSIS_METHOD.md y ENDURANCE_AGENT_DOMAIN.md directamente"])
    lines.extend(
        [
            "",
            "## Output",
            f"Guarda el informe final en `{report_dir / 'report.md'}`.",
        ]
    )
    return "\n".join(lines) + "\n"


def analyzer_sport_from_session(row: dict[str, str]) -> str:
    sport = (row.get("sport") or "").strip().lower()
    if sport in {"trail_run", "trail"}:
        return "trail"
    if sport in {"road_run", "run", "running", "virtualrun", "virtual_run"}:
        return "road"
    if sport == "hike":
        return "hike"
    if sport == "bike":
        return "bike"
    if sport == "swim":
        return "swim"
    if sport == "elliptical":
        return "elliptical"
    return "trail"


def session_family_notes(sport_family: str) -> list[str]:
    if sport_family == "road":
        return [
            "familia road / indoor run: no usar semantica de terreno o desnivel",
            "si la sesion es cinta o virtual run, priorizar continuidad, intensidad y estabilidad sobre geografia",
            "evitar inferir coste mecanico de trail a partir de ritmo o FC sin contexto de terreno",
        ]
    if sport_family == "hike":
        return [
            "familia hike: tratar como marcha en terreno, no como carrera continua",
            "priorizar desnivel, continuidad caminando y duracion; rebajar lenguaje de tempo o bloque corrible",
            "no asumir el mismo coste locomotor que en trail running",
        ]
    if sport_family == "elliptical":
        return [
            "familia elliptical: cardio indoor de bajo impacto",
            "no usar semantica de terreno, impacto o descenso",
            "si faltan bloques, cadencia o señales de trabajo sostenido, la dimension mecanica debe quedar muy prudente o no clasificable",
        ]
    if sport_family == "bike":
        return [
            "familia bike: no usar lenguaje de carrera ni de terreno a pie",
            "interpretar la carga mecanica como demanda ciclista inferida, no como impacto o excentrico",
            "priorizar cadencia, velocidad y perfil si existen, pero mantener prudencia sin potencia directa",
        ]
    if sport_family == "swim":
        return [
            "familia swim: no usar semantica de locomocion terrestre",
            "tratar SWOLF, brazada y bloques como apoyo tecnico/propulsivo, no como coste mecanico de carrera",
            "si el dato es pobre, preferir no clasificable en la dimension mecanica",
        ]
    return [
        "familia trail: semantica de terreno, subida, bajada y locomocion corrible aplicable por defecto",
    ]


def _build_no_rr_summary(session_row: dict[str, str], manifest: dict[str, Any]) -> dict[str, Any]:
    """Summary parcial para sesiones sin RR valido. Calcula cost model; deja metricas RR en None."""
    try:
        from session_cost_model import build_cost_model_result
        cost = build_cost_model_result(session_row)
        if isinstance(cost, dict):
            cost["usable"] = True
    except Exception as exc:
        cost = {"error": str(exc), "usable": False}
    rr_error = manifest.get("rr_error") or "RR no disponible"
    rr_context = {
        "modifier": "no_rr",
        "interpretation": "RR no disponible para esta sesion. Solo se calculan metricas de coste desde sessions.csv.",
        "evidence": [rr_error],
    }
    final_cost = None
    if isinstance(cost, dict) and cost.get("usable", False):
        final_cost = {
            "label": str(cost.get("coste_dominante")),
            "rr_modifier": "no_rr",
            "note": f"Sessions sugiere `{cost.get('coste_dominante')}`; RR no disponible",
        }
    return {
        "rr_unavailable": True,
        "rr_error": rr_error,
        "rr_path": None,
        "hr_source": "stream",
        "session_cost_model": cost,
        "session_meta": {
            "sport_family": analyzer_sport_from_session(session_row),
        },
        "session_row": session_row,
        "rmssd_1min": None,
        "rmssd_5min": None,
        "dfa_alpha1": None,
        "dfa_gate": None,
        "hr_at_075": None,
        "hr_at_075_crossing": None,
        "rr_context": rr_context,
        "final_cost_interpretation": final_cost,
    }


def run_analysis(bundle_manifest: Path, reports_dir: Path, keep_debug_artifacts: bool = False) -> dict[str, Any]:
    manifest = json.loads(bundle_manifest.read_text(encoding="utf-8"))
    slug = manifest["slug"]
    year = slug[:4]
    month = slug[5:7]
    report_dir = reports_dir / year / month / slug
    artifacts_dir = report_dir / "artifacts"
    debug_dir = report_dir / "debug"
    report_dir.mkdir(parents=True, exist_ok=True)
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    out_prefix = artifacts_dir / slug

    session_row = json.loads(Path(manifest["session_row_path"]).read_text(encoding="utf-8"))
    rr_csv_path = manifest.get("rr_csv")
    rr_available = bool(rr_csv_path and Path(rr_csv_path).exists())

    summary_path = artifacts_dir / "summary.json"

    if rr_available:
        cmd = [
            sys.executable,
            str(ANALYZER_SCRIPT),
            "--rr",
            rr_csv_path,
            "--hr-stream-csv",
            manifest["hr_stream_csv"],
            "--sport",
            analyzer_sport_from_session(session_row),
            "--sessions-csv",
            manifest["sessions_csv"],
            "--session-id",
            manifest["session_id"],
            "--out-prefix",
            str(out_prefix),
        ]
        fit_path = manifest.get("fit_path")
        if fit_path:
            cmd.extend(["--fit", fit_path])
        if session_row.get("vt1_used"):
            cmd.extend(["--vt1", str(session_row["vt1_used"])])
        if session_row.get("vt2_used"):
            cmd.extend(["--vt2", str(session_row["vt2_used"])])

        stdout_path = debug_dir / "analysis_stdout.txt"
        stderr_path = debug_dir / "analysis_stderr.txt"
        debug_dir.mkdir(parents=True, exist_ok=True)
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=300,
            )
        except subprocess.TimeoutExpired as exc:
            stdout_path.write_text(exc.stdout or "", encoding="utf-8")
            stderr_path.write_text(exc.stderr or "", encoding="utf-8")
            raise RuntimeError(f"analysis timed out after 300s for session {manifest['session_id']}") from exc
        stdout_path.write_text(result.stdout or "", encoding="utf-8")
        stderr_path.write_text(result.stderr or "", encoding="utf-8")
        if result.returncode != 0:
            raise RuntimeError(f"analysis failed with exit code {result.returncode}")

        generated_summary_path = artifacts_dir / f"{slug}_summary.json"
        if generated_summary_path.exists():
            generated_summary_path.replace(summary_path)
        if not summary_path.exists():
            raise RuntimeError(f"expected summary file not found: {summary_path}")
    else:
        # RR no disponible: report parcial con solo cost model y metricas de sesion
        stdout_path = debug_dir / "analysis_stdout.txt"
        stderr_path = debug_dir / "analysis_stderr.txt"
        debug_dir.mkdir(parents=True, exist_ok=True)
        stdout_path.write_text("", encoding="utf-8")
        stderr_path.write_text(
            f"RR no disponible: {manifest.get('rr_error') or 'sin RR exportable'}. "
            "Generando report parcial sin metricas RR.\n",
            encoding="utf-8",
        )
        partial_summary = _build_no_rr_summary(session_row, manifest)
        write_json(summary_path, partial_summary)

    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    summary = enrich_summary_with_manifest_context(summary, manifest)
    summary = enrich_summary_with_sessions_metadata(summary)

    fit_artifact_path = None
    fit_path = manifest.get("fit_path")
    if fit_path:
        fit_src = Path(fit_path)
        if fit_src.exists():
            fit_artifact_path = artifacts_dir / "session.fit"
            shutil.copy2(fit_src, fit_artifact_path)

    terrain_climbs_csv_path = None
    if _supports_terrain_context(session_row):
        if fit_artifact_path and fit_artifact_path.exists():
            try:
                fit_terrain = analyze_fit_climbs(
                    fit_artifact_path,
                    session_row=session_row,
                    terrain_context=summary.get("terrain_context"),
                    terrain_intervals=manifest.get("terrain_intervals") or [],
                )
                summary["terrain_fit_context"] = fit_terrain.get("terrain_fit_context")
                terrain_climbs_csv_path = write_terrain_climbs_csv(
                    artifacts_dir / "terrain_climbs.csv",
                    fit_terrain.get("terrain_climbs") or [],
                )
            except Exception as exc:
                summary["terrain_fit_error"] = str(exc)
        else:
            summary["terrain_fit_error"] = "fit artifact unavailable"

    write_json(summary_path, summary)
    technical_report_md = report_dir / "technical_report.md"
    technical_report_md.write_text(render_report_markdown(summary), encoding="utf-8")
    write_json(artifacts_dir / "manifest.json", manifest)
    terrain_intervals_csv_path = write_terrain_intervals_csv(
        artifacts_dir / "terrain_intervals.csv",
        manifest.get("terrain_intervals") or [],
    )

    generated_blocks_path = artifacts_dir / f"{slug}_blocks.csv"
    blocks_path = artifacts_dir / "blocks.csv"
    if generated_blocks_path.exists():
        generated_blocks_path.replace(blocks_path)

    payload = build_conversational_payload(summary, manifest, session_row, artifacts_dir=artifacts_dir)
    payload_path = artifacts_dir / "session_payload.json"
    write_json(payload_path, payload)

    analyst_prompt_path = report_dir / "analyst_prompt.md"
    analyst_prompt_path.write_text(
        build_analyst_prompt_markdown(
            report_dir=report_dir,
            payload_path=payload_path,
            summary_path=summary_path,
            blocks_path=blocks_path if blocks_path.exists() else None,
            terrain_intervals_path=terrain_intervals_csv_path,
            terrain_climbs_path=terrain_climbs_csv_path,
        ),
        encoding="utf-8",
    )

    if not keep_debug_artifacts:
        debug_files = [
            artifacts_dir / f"{slug}_rr_beats.csv",
            artifacts_dir / f"{slug}_dfa_alpha1.csv",
            artifacts_dir / f"{slug}_rmssd_1min.csv",
            artifacts_dir / f"{slug}_rmssd_5min.csv",
            stdout_path,
        ]
        for path in debug_files:
            if path.exists():
                try:
                    path.unlink()
                except PermissionError:
                    pass
        if stderr_path.exists() and stderr_path.read_text(encoding="utf-8").strip() == "":
            try:
                stderr_path.unlink()
            except PermissionError:
                pass
        if debug_dir.exists() and not any(debug_dir.iterdir()):
            debug_dir.rmdir()
    else:
        rename_pairs = [
            (artifacts_dir / f"{slug}_rr_beats.csv", debug_dir / "rr_beats.csv"),
            (artifacts_dir / f"{slug}_dfa_alpha1.csv", debug_dir / "dfa_alpha1.csv"),
        ]
        for src, dst in rename_pairs:
            if src.exists():
                src.replace(dst)

    ai_handoff_path = report_dir / "ai_handoff.md"
    ai_handoff_path.write_text(
        build_ai_handoff_markdown(
            report_dir=report_dir,
            artifacts_dir=artifacts_dir,
            payload_path=payload_path,
            summary_path=summary_path,
            blocks_path=blocks_path if blocks_path.exists() else None,
            terrain_intervals_path=terrain_intervals_csv_path,
            terrain_climbs_path=terrain_climbs_csv_path,
            debug_dir=debug_dir if debug_dir.exists() else None,
        ),
        encoding="utf-8",
    )

    return {
        "report_dir": str(report_dir),
        "summary_path": str(summary_path),
        "technical_report_md": str(technical_report_md),
        "final_report_md": str(report_dir / "report.md"),
        "analyst_prompt": str(analyst_prompt_path),
        "blocks_csv": str(blocks_path) if blocks_path.exists() else None,
        "terrain_intervals_csv": str(terrain_intervals_csv_path) if terrain_intervals_csv_path else None,
        "terrain_climbs_csv": str(terrain_climbs_csv_path) if terrain_climbs_csv_path else None,
        "fit_artifact": str(fit_artifact_path) if fit_artifact_path else None,
        "session_payload": str(payload_path),
        "ai_handoff": str(ai_handoff_path),
        "stderr_path": str(stderr_path) if stderr_path.exists() else None,
        "artifacts_dir": str(artifacts_dir),
        "debug_dir": str(debug_dir) if debug_dir.exists() else None,
        "debug_artifacts_kept": keep_debug_artifacts,
    }


def cleanup_bundle(bundle_dir: Path) -> None:
    if bundle_dir.exists():
        shutil.rmtree(bundle_dir, ignore_errors=True)
