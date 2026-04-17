#!/usr/bin/env python3
from __future__ import annotations

import csv
import gzip
import json
import os
import re
import statistics
import shutil
import subprocess
import sys
from datetime import datetime, timedelta
from functools import lru_cache
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
    "SESSION_ANALYSIS_METHOD.md": "1.6",
    "ENDURANCE_AGENT_DOMAIN.md": "1.3",
}
ANALYST_PROMPT_RULES_PATH = ANALYSIS_DIR / "analyst_prompt_rules.md"
# Heuristica local de analysis/: si drift y decoupling difieren <=2.5 pp,
# se consideran aproximadamente alineados para narrativa, no equivalentes.
DRIFT_DECOUPLING_ALIGNMENT_DELTA_PCT = 2.5

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
    gap_model = _coerce_text_or_none_sentinel(activity.get("gap_model"), {"NONE", "NULL"})

    return {
        "source": "intervals_activity",
        "gap_mean": round(gap_mean * 3.6, 1) if gap_mean is not None else None,
        "gap_unit": "km/h",
        "gap_model": gap_model,
        "vam_uphill_mean": None,
        "vam_source": None,
    }


def fetch_intervals_activity_detail(row: dict[str, str]) -> dict[str, Any]:
    session_id = row.get("session_id")
    if not session_id:
        raise ValueError("session row has no session_id")

    client = _get_intervals_client()
    payload = client.get(f"/activity/{session_id}").json()
    if not isinstance(payload, dict):
        raise RuntimeError(f"Intervals activity payload invalido para {session_id}")
    return payload


def fetch_intervals_activity_intervals_payload(row: dict[str, str]) -> dict[str, Any]:
    session_id = row.get("session_id")
    if not session_id:
        raise ValueError("session row has no session_id")

    client = _get_intervals_client()
    payload = client.get(f"/activity/{session_id}/intervals").json()
    if not isinstance(payload, dict):
        raise RuntimeError(f"Intervals intervals payload invalido para {session_id}")
    return payload


def _coerce_text_or_none(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _coerce_text_or_none_sentinel(value: Any, sentinels: set[str] | None = None) -> str | None:
    text = _coerce_text_or_none(value)
    if text is None:
        return None
    if sentinels and text.upper() in sentinels:
        return None
    return text


def _coerce_int_like(value: Any) -> int | None:
    numeric = parse_float(value)
    if numeric is None:
        return None
    rounded = int(round(numeric))
    if abs(numeric - rounded) > 1e-6:
        return None
    return rounded


def _achievement_preview(values: Any, limit: int = 5) -> list[str]:
    if not isinstance(values, list):
        return []
    preview: list[str] = []
    for item in values:
        if isinstance(item, dict):
            label = _coerce_text_or_none(
                item.get("label")
                or item.get("name")
                or item.get("description")
                or item.get("type")
            )
        else:
            label = _coerce_text_or_none(item)
        if not label or label in preview:
            continue
        preview.append(label)
        if len(preview) >= limit:
            break
    return preview


def summarize_intervals_analysis_context(
    activity: dict[str, Any] | None,
    intervals_payload: dict[str, Any] | None,
    session_row: dict[str, str],
) -> dict[str, Any] | None:
    if not isinstance(activity, dict) and not isinstance(intervals_payload, dict):
        return None

    activity = activity or {}
    intervals_payload = intervals_payload or {}
    icu_intervals = intervals_payload.get("icu_intervals") or []
    icu_groups = intervals_payload.get("icu_groups") or []
    interval_types: list[str] = []
    labels_preview: list[str] = []
    for row in icu_intervals:
        if not isinstance(row, dict):
            continue
        interval_type = _coerce_text_or_none(row.get("type"))
        if interval_type and interval_type not in interval_types:
            interval_types.append(interval_type)
        label = _coerce_text_or_none(row.get("label"))
        if label and label not in labels_preview:
            labels_preview.append(label)
        if len(labels_preview) >= 6:
            break

    hr_zone_times = activity.get("icu_hr_zone_times")
    power_zone_times = activity.get("icu_zone_times")
    sport_family = analyzer_sport_from_session(session_row)
    average_stride_raw = parse_float(activity.get("average_stride"))
    average_stride = average_stride_raw if sport_family in {"road", "trail"} else None

    return {
        "source": "intervals_activity+/intervals",
        "coach_metrics": {
            "session_rpe": _coerce_int_like(activity.get("session_rpe")),
            "icu_rpe": _coerce_int_like(activity.get("icu_rpe")),
            "icu_intensity_pct": round(parse_float(activity.get("icu_intensity")), 1)
            if parse_float(activity.get("icu_intensity")) is not None
            else None,
            "polarization_index": round(parse_float(activity.get("polarization_index")), 2)
            if parse_float(activity.get("polarization_index")) is not None
            else None,
            "average_stride": round(average_stride, 3) if average_stride is not None else None,
            "average_stride_semantics": "sport_specific" if average_stride is not None else None,
            "decoupling_pct": round(parse_float(activity.get("decoupling")), 2)
            if parse_float(activity.get("decoupling")) is not None
            else None,
            "cardiac_drift_pct": round(parse_float(session_row.get("cardiac_drift_pct")), 2)
            if parse_float(session_row.get("cardiac_drift_pct")) is not None
            else None,
            "hr_load": _coerce_int_like(activity.get("hr_load")),
            "hr_load_type": _coerce_text_or_none(activity.get("hr_load_type")),
            "power_load": round(parse_float(activity.get("power_load")), 2)
            if parse_float(activity.get("power_load")) is not None
            else None,
            "pace_load": round(parse_float(activity.get("pace_load")), 2)
            if parse_float(activity.get("pace_load")) is not None
            else None,
            "strain_score": round(parse_float(activity.get("strain_score")), 2)
            if parse_float(activity.get("strain_score")) is not None
            else None,
            "feel": _coerce_int_like(activity.get("feel")),
        },
            "structured_workout": {
            "intervals_count": len([row for row in icu_intervals if isinstance(row, dict)]),
            "groups_count": len([row for row in icu_groups if isinstance(row, dict)]),
            "interval_types": interval_types,
            "labels_preview": labels_preview,
            "lap_count": _coerce_int_like(activity.get("icu_lap_count")),
            "intervals_edited": bool(activity.get("icu_intervals_edited")) if activity.get("icu_intervals_edited") is not None else None,
        },
        "route_context": {
            "route_id": _coerce_int_like(activity.get("route_id")),
            "gap_raw": round(parse_float(activity.get("gap")) * 3.6, 2)
            if parse_float(activity.get("gap")) is not None
            else None,
            "gap_unit": "km/h" if parse_float(activity.get("gap")) is not None else None,
            "gap_model": _coerce_text_or_none_sentinel(activity.get("gap_model"), {"NONE", "NULL"}),
        },
        "achievements": {
            "count": len(activity.get("icu_achievements") or []) if isinstance(activity.get("icu_achievements"), list) else 0,
            "preview": _achievement_preview(activity.get("icu_achievements")),
        },
        "zone_context": {
            "hr_zone_times": hr_zone_times if isinstance(hr_zone_times, list) else None,
            "power_zone_times": power_zone_times if isinstance(power_zone_times, list) else None,
        },
    }


def build_coach_usage_notes(sport_family: str) -> list[str]:
    notes = [
        "usar `analysis_only_context` como enriquecimiento local de `analysis/`, no como contrato canonico global",
        "tratar `session_rpe` como carga subjetiva tipo Foster (`moving_time_min x icu_rpe`); no compararla 1:1 contra `load` o `trimp`",
        "tratar `icu_intensity` y `polarization_index` como apoyo coach/Intervals, no como reemplazo automatico de `intensity_category` o de la lectura canonica de distribucion",
        "si existe `composite_context`, usarlo como capa exploratoria de coherencia de carga, costo termico y durabilidad por tercios; no convertirlo en contrato canonico ni en taxonomy final",
    ]
    if sport_family in {"road", "trail"}:
        notes.append("si existe `average_stride`, usarla solo con semantica deporte-especifica y nunca como metrica transversal")
    if sport_family == "bike":
        notes.append("en bike, leer `coach_intervals` y `coach_groups` como estructura de esfuerzo o bloques, no con semantica de zancada o impacto")
    if sport_family == "swim":
        notes.append("en swim, rebajar el peso interpretativo de `average_stride` y priorizar estructura de bloques o sensacion subjetiva si aporta valor")
    return notes


def _session_rpe_readout(session_rpe: int | None, duration_min: float | None, icu_rpe: int | None) -> str | None:
    if session_rpe is None:
        return None
    if icu_rpe is not None and duration_min is not None and duration_min > 0:
        duration_label = int(round(duration_min))
        return f"`session_rpe={session_rpe}` (Foster: ~`{icu_rpe}` RPE x `{duration_label}` min)"
    return f"`session_rpe={session_rpe}`"


def build_coach_narrative_hints(
    analysis_only_context: dict[str, Any] | None,
    session_row: dict[str, str],
) -> dict[str, list[str]]:
    hints: dict[str, list[str]] = {
        "datos": [],
        "estructura_externa": [],
        "respuesta_interna": [],
        "encaje_bloque": [],
        "advertencias": [],
    }
    if not isinstance(analysis_only_context, dict):
        return hints

    coach_metrics = analysis_only_context.get("coach_metrics") or {}
    structured = analysis_only_context.get("structured_workout") or {}
    route_context = analysis_only_context.get("route_context") or {}
    zone_context = analysis_only_context.get("zone_context") or {}
    composite_context = analysis_only_context.get("composite_context") or {}

    session_rpe = _coerce_int_like(coach_metrics.get("session_rpe"))
    icu_rpe = _coerce_int_like(coach_metrics.get("icu_rpe"))
    feel = _coerce_int_like(coach_metrics.get("feel"))
    icu_intensity = parse_float(coach_metrics.get("icu_intensity_pct"))
    hr_load = _coerce_int_like(coach_metrics.get("hr_load"))
    hr_load_type = _coerce_text_or_none(coach_metrics.get("hr_load_type"))
    load = parse_float(session_row.get("load"))
    trimp = parse_float(session_row.get("trimp"))
    stride = parse_float(coach_metrics.get("average_stride"))
    duration_min = parse_float(session_row.get("moving_min")) or parse_float(session_row.get("duration_min"))
    session_rpe_label = _session_rpe_readout(session_rpe, duration_min, icu_rpe)
    if session_rpe is not None or feel is not None or icu_intensity is not None:
        parts: list[str] = []
        if session_rpe_label is not None:
            parts.append(session_rpe_label)
        if feel is not None:
            parts.append(f"`feel={feel}`")
        if icu_intensity is not None:
            parts.append(f"`icu_intensity={round(icu_intensity, 1)}%`")
        hints["datos"].append(
            "capa subjetiva/coach disponible: "
            + ", ".join(parts)
            + "; usarla en `Contexto subjetivo` como apoyo local, no como sustituto del contrato canonico"
        )
    if stride is not None:
        hints["datos"].append(
            f"`average_stride={round(stride, 3)}` disponible; usar solo con semantica deporte-especifica en `{session_row.get('sport') or 'sport'}`"
        )

    intervals_count = _coerce_int_like(structured.get("intervals_count")) or 0
    groups_count = _coerce_int_like(structured.get("groups_count")) or 0
    lap_count = _coerce_int_like(structured.get("lap_count"))
    interval_types = structured.get("interval_types") or []
    intervals_edited = structured.get("intervals_edited")
    if intervals_count or groups_count or lap_count:
        structure_parts = [f"`icu_intervals={intervals_count}`", f"`icu_groups={groups_count}`"]
        if lap_count is not None:
            structure_parts.append(f"`icu_lap_count={lap_count}`")
        if interval_types:
            structure_parts.append(f"`interval_types={interval_types}`")
        if intervals_edited is not None:
            structure_parts.append(f"`intervals_edited={intervals_edited}`")
        hints["estructura_externa"].append(
            "estructura ICU disponible: "
            + ", ".join(structure_parts)
            + "; usar `coach_intervals.csv` y `coach_groups.csv` si ayudan a describir bloques o repeticiones con valor tactico"
        )

    decoupling = parse_float(coach_metrics.get("decoupling_pct"))
    cardiac_drift = parse_float(coach_metrics.get("cardiac_drift_pct"))
    if decoupling is not None and cardiac_drift is not None:
        drift_delta = abs(decoupling - cardiac_drift)
        relation = (
            f"aproximadamente alineadas (delta ~{round(drift_delta, 2)} pp)"
            if drift_delta <= DRIFT_DECOUPLING_ALIGNMENT_DELTA_PCT
            else f"no directamente alineadas (delta ~{round(drift_delta, 2)} pp)"
        )
        hints["respuesta_interna"].append(
            f"`cardiac_drift_pct={round(cardiac_drift, 2)}` y `decoupling_pct={round(decoupling, 2)}` disponibles; leerlas como señales relacionadas pero no equivalentes ({relation})"
        )
    elif cardiac_drift is not None:
        hints["respuesta_interna"].append(
            f"`cardiac_drift_pct={round(cardiac_drift, 2)}` disponible en `sessions.csv`; `decoupling` coach no disponible para contraste directo"
        )
    elif decoupling is not None:
        hints["respuesta_interna"].append(
            f"`decoupling_pct={round(decoupling, 2)}` disponible desde coach; usarlo como apoyo local y no como reemplazo directo de `cardiac_drift_pct`"
        )

    load_mismatch = composite_context.get("subjective_coherence") or {}
    if load_mismatch:
        mismatch_parts: list[str] = []
        if load_mismatch.get("subjective_coherence_state"):
            mismatch_parts.append(f"estado {load_mismatch.get('subjective_coherence_state')}")
        if load_mismatch.get("subjective_objective_gap_pct") is not None:
            mismatch_parts.append(f"gap subjetivo/objetivo ~{load_mismatch.get('subjective_objective_gap_pct')}%")
        if load_mismatch.get("objective_spread_pct") is not None:
            mismatch_parts.append(f"spread objetivo ~{load_mismatch.get('objective_spread_pct')}%")
        if load_mismatch.get("session_rpe_load_equiv") is not None:
            mismatch_parts.append(f"session_rpe_load_equiv={load_mismatch.get('session_rpe_load_equiv')}")
        if load_mismatch.get("trimp_load_equiv") is not None:
            mismatch_parts.append(f"trimp_load_equiv={load_mismatch.get('trimp_load_equiv')}")
        hints["respuesta_interna"].append(
            "coherencia subjetiva/carga disponible: "
            + ", ".join(mismatch_parts)
            + "; usarla como apoyo exploratorio entre `load`, `trimp`, `hr_load` y `session_rpe`, no como veto automatico"
        )

    thermal_context = composite_context.get("thermal_context") or {}
    if thermal_context:
        thermal_parts: list[str] = []
        if thermal_context.get("temperature_c") is not None:
            thermal_parts.append(f"temp_media={thermal_context.get('temperature_c')}C")
        if thermal_context.get("thermal_cost_score") is not None:
            thermal_parts.append(f"thermal_cost_score={thermal_context.get('thermal_cost_score')}")
        if thermal_context.get("thermal_band"):
            thermal_parts.append(f"banda={thermal_context.get('thermal_band')}")
        hints["respuesta_interna"].append(
            "costo termico simple disponible: "
            + ", ".join(thermal_parts)
            + "; usarlo para matizar drift o sensacion de coste, no como WBGT ni como prueba fisiologica cerrada"
        )

    durability_context = composite_context.get("durability_context") or {}
    if durability_context:
        durability_parts: list[str] = []
        if durability_context.get("durability_hint"):
            durability_parts.append(f"hint={durability_context.get('durability_hint')}")
        if durability_context.get("confidence"):
            durability_parts.append(f"confidence={durability_context.get('confidence')}")
        if durability_context.get("delta_first_last_pct"):
            delta = durability_context.get("delta_first_last_pct") or {}
            delta_parts = ", ".join(
                f"{key}={value}%" for key, value in delta.items() if value is not None
            )
            if delta_parts:
                durability_parts.append(delta_parts)
        hints["estructura_externa"].append(
            "durabilidad por tercios disponible: "
            + ", ".join(durability_parts)
            + "; leerla como primitiva exploratoria de sostenimiento, no como taxonomia final"
        )

    if hr_load is not None or trimp is not None or load is not None:
        load_parts: list[str] = []
        if load is not None:
            load_parts.append(f"`load={round(load, 1)}`")
        if trimp is not None:
            load_parts.append(f"`trimp={round(trimp, 1)}`")
        if hr_load is not None:
            label = f"{hr_load}"
            if hr_load_type:
                label += f" ({hr_load_type})"
            load_parts.append(f"`hr_load={label}`")
        if session_rpe is not None:
            load_parts.append(session_rpe_label or f"`session_rpe={session_rpe}`")
        hints["encaje_bloque"].append(
            "si comparas capas de carga, presentalas como señales paralelas y no como equivalentes directas: "
            + ", ".join(load_parts)
        )

    route_id = _coerce_int_like(route_context.get("route_id"))
    gap_model = _coerce_text_or_none(route_context.get("gap_model"))
    if route_id is not None or gap_model:
        route_parts: list[str] = []
        if route_id is not None:
            route_parts.append(f"`route_id={route_id}`")
        if gap_model:
            route_parts.append(f"`gap_model={gap_model}`")
        hints["estructura_externa"].append(
            "contexto de ruta/coach disponible: "
            + ", ".join(route_parts)
            + "; usarlo para reencuadrar terreno o repetibilidad, no como prueba central de intensidad interna"
        )

    if isinstance(zone_context.get("power_zone_times"), list):
        hints["advertencias"].append(
            "`icu_zone_times` de potencia existe solo como capa coach local; no convertirla en lectura canonica de zonas"
        )
    if parse_float(coach_metrics.get("polarization_index")) is not None:
        hints["advertencias"].append(
            "`polarization_index` puede orientar la narrativa, pero su formula ICU sigue siendo opaca; no usarlo como prueba fuerte aislada"
        )
    return hints


def build_coach_report_examples(
    sport_family: str,
    analysis_only_context: dict[str, Any] | None,
    session_row: dict[str, str],
) -> dict[str, list[str]]:
    examples: dict[str, list[str]] = {
        "datos": [],
        "estructura_externa": [],
        "respuesta_interna": [],
        "encaje_bloque": [],
        "advertencias": [],
    }
    if not isinstance(analysis_only_context, dict):
        return examples

    coach_metrics = analysis_only_context.get("coach_metrics") or {}
    structured = analysis_only_context.get("structured_workout") or {}
    route_context = analysis_only_context.get("route_context") or {}
    composite_context = analysis_only_context.get("composite_context") or {}
    session_rpe = _coerce_int_like(coach_metrics.get("session_rpe"))
    icu_rpe = _coerce_int_like(coach_metrics.get("icu_rpe"))
    feel = _coerce_int_like(coach_metrics.get("feel"))
    icu_intensity = parse_float(coach_metrics.get("icu_intensity_pct"))
    cardiac_drift = parse_float(coach_metrics.get("cardiac_drift_pct"))
    decoupling = parse_float(coach_metrics.get("decoupling_pct"))
    hr_load = _coerce_int_like(coach_metrics.get("hr_load"))
    hr_load_type = _coerce_text_or_none(coach_metrics.get("hr_load_type")) or "coach"
    intervals_count = _coerce_int_like(structured.get("intervals_count")) or 0
    groups_count = _coerce_int_like(structured.get("groups_count")) or 0
    route_id = _coerce_int_like(route_context.get("route_id"))
    gap_model = _coerce_text_or_none(route_context.get("gap_model"))
    load = parse_float(session_row.get("load"))
    trimp = parse_float(session_row.get("trimp"))
    duration_min = parse_float(session_row.get("moving_min")) or parse_float(session_row.get("duration_min"))
    session_rpe_label = _session_rpe_readout(session_rpe, duration_min, icu_rpe)

    load_mismatch = composite_context.get("subjective_coherence") or {}
    if load_mismatch:
        examples["respuesta_interna"].append(
            "Ejemplo: \"La coherencia subjetiva/carga sugiere una "
            + str(load_mismatch.get("subjective_coherence_state") or "lectura mixta")
            + " con gap subjetivo/objetivo de ~"
            + str(load_mismatch.get("subjective_objective_gap_pct"))
            + "%; conviene leer `load`, `trimp`, `hr_load` y `session_rpe` como señales relacionadas, no equivalentes.\""
        )
    thermal_context = composite_context.get("thermal_context") or {}
    if thermal_context:
        examples["respuesta_interna"].append(
            "Ejemplo: \"El costo térmico simple ("
            + (f"`thermal_cost_score={thermal_context.get('thermal_cost_score')}`" if thermal_context.get("thermal_cost_score") is not None else "`thermal_cost_score`")
            + ") ayuda a explicar parte de la deriva o del coste percibido, pero no sustituye a la lectura cardiometabólica.\""
        )
    durability_context = composite_context.get("durability_context") or {}
    if durability_context:
        examples["estructura_externa"].append(
            "Ejemplo: \"La durabilidad por tercios muestra la sesión como una secuencia de tres tramos sobre `session_stream.csv`; la comparación entre el primero y el último es una pista exploratoria de sostenimiento, no una taxonomía cerrada.\""
        )

    if sport_family == "trail":
        if session_rpe is not None or icu_intensity is not None:
            examples["datos"].append(
                f"Ejemplo: \"La capa coach deja una percepcion de esfuerzo media-alta ({session_rpe_label or f'`session_rpe={session_rpe}`'}"
                + (f", `icu_intensity={round(icu_intensity, 1)}%`" if icu_intensity is not None else "")
                + "), compatible con un trail que costó más por terreno y continuidad que por simple tiempo en Z3.\""
            )
        if intervals_count or groups_count or route_id is not None:
            examples["estructura_externa"].append(
                f"Ejemplo: \"Intervals describe la sesión como una estructura con `icu_intervals={intervals_count}` y `icu_groups={groups_count}`"
                + (f"; `route_id={route_id}`" if route_id is not None else "")
                + ", útil para explicar dónde estuvieron los bloques de subida o los tramos corribles sin convertir esa capa en contrato canónico.\""
            )
        if cardiac_drift is not None or decoupling is not None:
            parts: list[str] = []
            if cardiac_drift is not None:
                parts.append(f"`cardiac_drift_pct={round(cardiac_drift, 2)}`")
            if decoupling is not None:
                parts.append(f"`decoupling_pct={round(decoupling, 2)}`")
            examples["respuesta_interna"].append(
                "Ejemplo: \""
                + " / ".join(parts)
                + " apuntan a una lectura de deriva condicionada por el relieve; conviene tratarlas como capas relacionadas pero no idénticas.\""
            )
        if load is not None or trimp is not None or hr_load is not None:
            examples["encaje_bloque"].append(
                f"Ejemplo: \"Dentro del bloque, la combinación `load={round(load,1) if load is not None else None}`, `trimp={round(trimp,1) if trimp is not None else None}`"
                + (f", `hr_load={hr_load} ({hr_load_type})`" if hr_load is not None else "")
                + (f" y {session_rpe_label}" if session_rpe_label is not None else "")
                + " sugiere una sesión de trail cara de absorber, no solo larga por terreno.\""
            )
    elif sport_family == "road":
        if session_rpe is not None or feel is not None or icu_intensity is not None:
            examples["datos"].append(
                f"Ejemplo: \"En la capa subjetiva/coach, {session_rpe_label or f'`session_rpe={session_rpe}`'}"
                + (f", `feel={feel}`" if feel is not None else "")
                + (f" e `icu_intensity={round(icu_intensity, 1)}%`" if icu_intensity is not None else "")
                + " ayudan a describir cuánto costó la sesión, pero no sustituyen a `load` ni a `trimp`.\""
            )
        if intervals_count or groups_count:
            examples["estructura_externa"].append(
                f"Ejemplo: \"La sesión dejó `icu_intervals={intervals_count}` y `icu_groups={groups_count}`; esto permite describirla como estructurada por bloques si ese patrón también se sostiene en `work_blocks` o en la continuidad real del FIT.\""
            )
        if load is not None or trimp is not None or hr_load is not None:
            examples["encaje_bloque"].append(
                f"Ejemplo: \"Para situarla en el bloque, puede leerse la combinación `load={round(load,1) if load is not None else None}`, `trimp={round(trimp,1) if trimp is not None else None}`"
                + (f" y `hr_load={hr_load} ({hr_load_type})`" if hr_load is not None else "")
                + (f" y {session_rpe_label}" if session_rpe_label is not None else "")
                + " como señales paralelas de carga interna, no como métricas equivalentes de la misma escala.\""
            )
    elif sport_family == "bike":
        if session_rpe is not None or hr_load is not None:
            examples["datos"].append(
                f"Ejemplo: \"En bici, {session_rpe_label or f'`session_rpe={session_rpe}`'}"
                + (f" y `hr_load={hr_load} ({hr_load_type})`" if hr_load is not None else "")
                + " sirven para matizar la carga interna del pedaleo, pero deben presentarse junto a `load`/`trimp`, no por separado como si midieran lo mismo.\""
            )
        if intervals_count or groups_count:
            examples["estructura_externa"].append(
                f"Ejemplo: \"`coach_intervals.csv` y `coach_groups.csv` pueden ayudar a contar la sesión como una sucesión de tramos o repeticiones de pedaleo, siempre evitando lenguaje de zancada o impacto propio de carrera.\""
            )
        if load is not None or trimp is not None or hr_load is not None:
            examples["encaje_bloque"].append(
                f"Ejemplo: \"Dentro del bloque ciclista, `load={round(load,1) if load is not None else None}`, `trimp={round(trimp,1) if trimp is not None else None}`"
                + (f", `hr_load={hr_load} ({hr_load_type})`" if hr_load is not None else "")
                + (f" y {session_rpe_label}" if session_rpe_label is not None else "")
                + " apuntan a una carga fácil-larga; suman volumen, no trabajo útil sobre VT1.\""
            )
    elif sport_family == "swim":
        if session_rpe is not None or feel is not None:
            examples["datos"].append(
                f"Ejemplo: \"En natación, `session_rpe={session_rpe}`"
                + (f" y `feel={feel}`" if feel is not None else "")
                + " pueden enriquecer la lectura subjetiva, pero la técnica y la estructura de bloques siguen siendo más informativas que cualquier intento de equipararlo a la carga de carrera.\""
            )
        examples["advertencias"].append(
            "Ejemplo: \"Si aparece `average_stride` o métricas similares, no deben traducirse con semántica terrestre; en swim la prioridad es bloque, sensación y técnica.\""
        )
    else:
        if session_rpe is not None or hr_load is not None:
            examples["datos"].append(
                "Ejemplo: \"La capa coach aporta señales de carga subjetiva o interna útiles para matizar el relato, pero no para reescribir la clasificación canónica de la sesión.\""
            )

    if gap_model:
        examples["advertencias"].append(
            f"Ejemplo: \"`gap_model={gap_model}` puede reencuadrar el terreno o la ruta, pero no debe usarse como prueba central de intensidad fisiológica.\""
        )
    return examples


def _normalize_intervals_structure_rows(
    session_id: str,
    rows: list[dict[str, Any]],
    structure_type: str,
) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for index, row in enumerate(rows, start=1):
        if not isinstance(row, dict):
            continue
        distance_m = parse_float(row.get("distance"))
        average_speed = parse_float(row.get("average_speed"))
        gap = parse_float(row.get("gap"))
        average_gradient = parse_float(row.get("average_gradient"))
        normalized.append(
            {
                "session_id": session_id,
                "structure_type": structure_type,
                "row_index": index,
                "row_id": _coerce_int_like(row.get("id")),
                "group_id": _coerce_int_like(row.get("group_id")),
                "type": _coerce_text_or_none(row.get("type")),
                "label": _coerce_text_or_none(row.get("label")),
                "count": _coerce_int_like(row.get("count")),
                "distance_km": round(distance_m / 1000.0, 3) if distance_m is not None else None,
                "elapsed_time_s": round(parse_float(row.get("elapsed_time")), 1)
                if parse_float(row.get("elapsed_time")) is not None
                else None,
                "moving_time_s": round(parse_float(row.get("moving_time")), 1)
                if parse_float(row.get("moving_time")) is not None
                else None,
                "start_time_s": round(parse_float(row.get("start_time")), 1)
                if parse_float(row.get("start_time")) is not None
                else None,
                "end_time_s": round(parse_float(row.get("end_time")), 1)
                if parse_float(row.get("end_time")) is not None
                else None,
                "average_speed_kmh": round(average_speed * 3.6, 2) if average_speed is not None else None,
                "gap_kmh": round(gap * 3.6, 2) if gap is not None else None,
                "average_gradient_pct": round(average_gradient * 100.0, 1) if average_gradient is not None else None,
                "elev_gain_m": round(parse_float(row.get("total_elevation_gain")), 1)
                if parse_float(row.get("total_elevation_gain")) is not None
                else None,
                "average_heartrate": round(parse_float(row.get("average_heartrate")), 1)
                if parse_float(row.get("average_heartrate")) is not None
                else None,
                "max_heartrate": round(parse_float(row.get("max_heartrate")), 1)
                if parse_float(row.get("max_heartrate")) is not None
                else None,
                "average_cadence": round(parse_float(row.get("average_cadence")), 1)
                if parse_float(row.get("average_cadence")) is not None
                else None,
                "average_stride": round(parse_float(row.get("average_stride")), 3)
                if parse_float(row.get("average_stride")) is not None
                else None,
                "average_watts": round(parse_float(row.get("average_watts")), 1)
                if parse_float(row.get("average_watts")) is not None
                else None,
                "weighted_average_watts": round(parse_float(row.get("weighted_average_watts")), 1)
                if parse_float(row.get("weighted_average_watts")) is not None
                else None,
                "intensity_pct": round(parse_float(row.get("intensity")), 1)
                if parse_float(row.get("intensity")) is not None
                else None,
                "zone": _coerce_int_like(row.get("zone")),
                "decoupling_pct": round(parse_float(row.get("decoupling")), 2)
                if parse_float(row.get("decoupling")) is not None
                else None,
                "training_load": round(parse_float(row.get("training_load")), 2)
                if parse_float(row.get("training_load")) is not None
                else None,
                "strain_score": round(parse_float(row.get("strain_score")), 2)
                if parse_float(row.get("strain_score")) is not None
                else None,
                "wbal_start": round(parse_float(row.get("wbal_start")), 1)
                if parse_float(row.get("wbal_start")) is not None
                else None,
                "wbal_end": round(parse_float(row.get("wbal_end")), 1)
                if parse_float(row.get("wbal_end")) is not None
                else None,
            }
        )
    return normalized


def write_intervals_structure_csv(path: Path, rows: list[dict[str, Any]]) -> Path | None:
    if not rows:
        return None
    fieldnames = [
        "session_id",
        "structure_type",
        "row_index",
        "row_id",
        "group_id",
        "type",
        "label",
        "count",
        "distance_km",
        "elapsed_time_s",
        "moving_time_s",
        "start_time_s",
        "end_time_s",
        "average_speed_kmh",
        "gap_kmh",
        "average_gradient_pct",
        "elev_gain_m",
        "average_heartrate",
        "max_heartrate",
        "average_cadence",
        "average_stride",
        "average_watts",
        "weighted_average_watts",
        "intensity_pct",
        "zone",
        "decoupling_pct",
        "training_load",
        "strain_score",
        "wbal_start",
        "wbal_end",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field) for field in fieldnames})
    return path


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

    payload = fetch_intervals_activity_intervals_payload(row)
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


def build_subjective_context(session_row: dict[str, str]) -> dict[str, Any]:
    return {
        "rpe": _coerce_int_like(session_row.get("rpe")),
        "rpe_present": _coerce_int_like(session_row.get("rpe_present")),
        "feel": _coerce_int_like(session_row.get("feel")),
        "notes_raw": _coerce_text_or_none(session_row.get("notes_raw")),
        "notes_present": _coerce_int_like(session_row.get("notes_present")),
    }


def _mean_or_none(values: list[float]) -> float | None:
    if not values:
        return None
    return round(sum(values) / len(values), 2)


def _pct_change(current: float | None, baseline: float | None) -> float | None:
    if current is None or baseline is None or baseline == 0:
        return None
    return round((current - baseline) / baseline * 100.0, 1)


def _load_stream_rows(stream_csv_path: Path | None) -> list[dict[str, float | None]]:
    if stream_csv_path is None or not stream_csv_path.exists():
        return []
    rows: list[dict[str, float | None]] = []
    with stream_csv_path.open(encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for raw in reader:
            sec = parse_float(raw.get("sec"))
            if sec is None:
                continue
            rows.append(
                {
                    "sec": sec,
                    "hr": parse_float(raw.get("hr")),
                    "speed_kmh": parse_float(raw.get("speed_kmh")),
                    "cadence": parse_float(raw.get("cadence")),
                }
            )
    rows.sort(key=lambda row: row["sec"] or 0.0)
    return rows


@lru_cache(maxsize=1)
def _historical_trimp_to_load_ratio() -> float | None:
    if not DEFAULT_SESSIONS_CSV.exists():
        return None
    ratios: list[float] = []
    try:
        rows = load_sessions_rows(DEFAULT_SESSIONS_CSV)
    except Exception:
        return None
    for row in rows:
        load = parse_float(row.get("load"))
        trimp = parse_float(row.get("trimp"))
        if load is None or trimp is None or load <= 0:
            continue
        ratios.append(trimp / load)
    if not ratios:
        return None
    return round(statistics.median(ratios), 3)


@lru_cache(maxsize=1)
def _historical_session_rpe_to_load_ratio() -> float | None:
    if not DEFAULT_SESSIONS_CSV.exists():
        return None
    ratios: list[float] = []
    try:
        rows = load_sessions_rows(DEFAULT_SESSIONS_CSV)
    except Exception:
        return None
    for row in rows:
        load = parse_float(row.get("load"))
        rpe = parse_float(row.get("rpe"))
        moving_min = parse_float(row.get("moving_min")) or parse_float(row.get("duration_min"))
        if load is None or load <= 0 or rpe is None or moving_min is None or moving_min <= 0:
            continue
        session_rpe = moving_min * rpe
        ratios.append(session_rpe / load)
    if not ratios:
        return None
    return round(statistics.median(ratios), 3)


def build_load_mismatch_context(
    analysis_only_context: dict[str, Any] | None,
    session_row: dict[str, str],
) -> dict[str, Any] | None:
    if not isinstance(analysis_only_context, dict):
        return None

    coach_metrics = analysis_only_context.get("coach_metrics") or {}
    load = parse_float(session_row.get("load"))
    trimp = parse_float(session_row.get("trimp"))
    hr_load = _coerce_int_like(coach_metrics.get("hr_load"))
    session_rpe = _coerce_int_like(coach_metrics.get("session_rpe"))
    if session_rpe is None:
        return None

    objective_values: list[tuple[str, float]] = []
    if load is not None:
        objective_values.append(("load", load))
    if trimp is not None:
        trimp_ratio = _historical_trimp_to_load_ratio()
        if trimp_ratio and trimp_ratio > 0:
            objective_values.append(("trimp_load_equiv", trimp / trimp_ratio))
        else:
            objective_values.append(("trimp", trimp))
    if hr_load is not None:
        objective_values.append(("hr_load", float(hr_load)))
    if len(objective_values) < 2:
        return None

    objective_nums = [value for _, value in objective_values]
    objective_anchor = statistics.median(objective_nums)
    if objective_anchor == 0:
        return None

    session_rpe_ratio = _historical_session_rpe_to_load_ratio()
    if session_rpe_ratio and session_rpe_ratio > 0:
        session_rpe_load_equiv = round(session_rpe / session_rpe_ratio, 1)
        subjective_method = "session_rpe/session_rpe_load_ratio_ref"
    else:
        session_rpe_load_equiv = round(session_rpe / 10.0, 1)
        subjective_method = "session_rpe/10_fallback"
    objective_spread_pct = round((max(objective_nums) - min(objective_nums)) / objective_anchor * 100.0, 1)
    subjective_objective_gap_pct = round(abs(session_rpe_load_equiv - objective_anchor) / objective_anchor * 100.0, 1)
    coherence_score = round(max(0.0, 100.0 - subjective_objective_gap_pct), 1)
    if subjective_objective_gap_pct <= 15 and objective_spread_pct <= 15:
        coherence_state = "coherent"
    elif subjective_objective_gap_pct <= 30 or objective_spread_pct <= 30:
        coherence_state = "mixed"
    else:
        coherence_state = "mismatched"

    deviations = [(name, abs(value - objective_anchor)) for name, value in objective_values]
    deviations.append(("session_rpe", abs(session_rpe_load_equiv - objective_anchor)))
    driver = max(deviations, key=lambda item: item[1])[0]

    return {
        "method": f"objective_anchor=median(load,trimp_load_equiv,hr_load); subjective_anchor={subjective_method}",
        "load": round(load, 1) if load is not None else None,
        "trimp": round(trimp, 1) if trimp is not None else None,
        "trimp_load_equiv": round(trimp / trimp_ratio, 1) if trimp is not None and trimp_ratio and trimp_ratio > 0 else None,
        "trimp_load_ratio_ref": trimp_ratio,
        "hr_load": hr_load,
        "session_rpe": session_rpe,
        "session_rpe_load_equiv": session_rpe_load_equiv,
        "session_rpe_load_ratio_ref": session_rpe_ratio,
        "objective_values": {name: round(value, 1) for name, value in objective_values},
        "objective_anchor": round(objective_anchor, 1),
        "objective_spread_pct": objective_spread_pct,
        "subjective_objective_gap_pct": subjective_objective_gap_pct,
        "subjective_coherence_score": coherence_score,
        "subjective_coherence_state": coherence_state,
        "driver": driver,
    }


def build_thermal_context(session_row: dict[str, str]) -> dict[str, Any] | None:
    average_temp = parse_float(session_row.get("average_weather_temp"))
    moving_min = parse_float(session_row.get("moving_min")) or parse_float(session_row.get("duration_min"))
    if average_temp is None or moving_min is None:
        return None

    thermal_threshold_c = 20.0
    thermal_excess_c = max(0.0, average_temp - thermal_threshold_c)
    thermal_cost_score = round(thermal_excess_c * (moving_min / 60.0), 2)
    if thermal_cost_score <= 0:
        thermal_band = "low"
    elif thermal_cost_score < 3:
        thermal_band = "marginal"
    elif thermal_cost_score < 8:
        thermal_band = "moderate"
    else:
        thermal_band = "high"
    return {
        "temperature_c": round(average_temp, 1),
        "duration_min": round(moving_min, 1),
        "threshold_c": thermal_threshold_c,
        "excess_c": round(thermal_excess_c, 1),
        "thermal_cost_score": thermal_cost_score,
        "thermal_band": thermal_band,
        "method": "max(0, average_weather_temp - threshold_c) * moving_min_hours; exploratory thermal load, not WBGT",
    }


def build_durability_thirds_context(
    stream_csv_path: Path | None,
    session_row: dict[str, str] | None = None,
) -> dict[str, Any] | None:
    stream_rows = _load_stream_rows(stream_csv_path)
    if len(stream_rows) < 30:
        return None

    start_sec = stream_rows[0]["sec"] or 0.0
    end_sec = stream_rows[-1]["sec"] or 0.0
    span_sec = end_sec - start_sec
    if span_sec <= 0:
        return None

    first_boundary = start_sec + span_sec / 3.0
    second_boundary = start_sec + 2.0 * span_sec / 3.0
    thirds: list[list[dict[str, float | None]]] = [[], [], []]
    for row in stream_rows:
        sec = row["sec"] or 0.0
        index = 0 if sec <= first_boundary else 1 if sec <= second_boundary else 2
        thirds[index].append(row)

    if any(not third for third in thirds):
        return None

    third_profiles: list[dict[str, Any]] = []
    for index, rows in enumerate(thirds, start=1):
        hr_values = [row["hr"] for row in rows if row["hr"] is not None]
        speed_values = [row["speed_kmh"] for row in rows if row["speed_kmh"] is not None]
        cadence_values = [row["cadence"] for row in rows if row["cadence"] is not None]
        third_profiles.append(
            {
                "third": index,
                "start_sec": round(rows[0]["sec"] or 0.0, 1),
                "end_sec": round(rows[-1]["sec"] or 0.0, 1),
                "duration_sec": round((rows[-1]["sec"] or 0.0) - (rows[0]["sec"] or 0.0), 1),
                "n_samples": len(rows),
                "hr_mean": _mean_or_none([float(v) for v in hr_values if v is not None]),
                "speed_mean_kmh": _mean_or_none([float(v) for v in speed_values if v is not None]),
                "cadence_mean": _mean_or_none([float(v) for v in cadence_values if v is not None]),
                "hr_coverage_pct": round(100.0 * len(hr_values) / len(rows), 1) if rows else None,
                "speed_coverage_pct": round(100.0 * len(speed_values) / len(rows), 1) if rows else None,
                "cadence_coverage_pct": round(100.0 * len(cadence_values) / len(rows), 1) if rows else None,
            }
        )

    first_third = third_profiles[0]
    middle_third = third_profiles[1]
    last_third = third_profiles[2]
    hr_change_pct = _pct_change(last_third.get("hr_mean"), first_third.get("hr_mean"))
    speed_change_pct = _pct_change(last_third.get("speed_mean_kmh"), first_third.get("speed_mean_kmh"))
    cadence_change_pct = _pct_change(last_third.get("cadence_mean"), first_third.get("cadence_mean"))
    sport = (session_row or {}).get("sport") or ""
    z2_pct = parse_float((session_row or {}).get("z2_pct"))
    z3_pct = parse_float((session_row or {}).get("z3_pct"))
    work_total_min = parse_float((session_row or {}).get("work_total_min"))

    is_easy_subthreshold = (
        (z2_pct or 0.0) == 0.0
        and (z3_pct or 0.0) == 0.0
        and (work_total_min or 0.0) == 0.0
    )

    if (
        is_easy_subthreshold
        and speed_change_pct is not None
        and abs(speed_change_pct) <= 10
        and hr_change_pct is not None
        and abs(hr_change_pct) <= 3
        and cadence_change_pct is not None
        and abs(cadence_change_pct) <= 5
    ):
        durability_hint = "steady_easy"
    elif (
        sport in {"trail_run", "hike"}
        and speed_change_pct is not None
        and speed_change_pct <= -10
        and hr_change_pct is not None
        and hr_change_pct <= 0
    ):
        durability_hint = "terrain_confounded"
    elif speed_change_pct is not None and speed_change_pct >= 5:
        durability_hint = "negative_split_like"
    elif speed_change_pct is not None and speed_change_pct <= -8 and hr_change_pct is not None and hr_change_pct >= 5:
        durability_hint = "fade_like"
    elif speed_change_pct is not None and abs(speed_change_pct) <= 5 and hr_change_pct is not None and abs(hr_change_pct) <= 5:
        durability_hint = "stable"
    elif hr_change_pct is not None and hr_change_pct >= 5 and speed_change_pct is not None and speed_change_pct > -3:
        durability_hint = "drift_like"
    else:
        durability_hint = "mixed"

    cadence_change_abs_pct = abs(cadence_change_pct) if cadence_change_pct is not None else None
    if (
        len(stream_rows) >= 300
        and first_third.get("speed_mean_kmh") is not None
        and last_third.get("speed_mean_kmh") is not None
    ):
        confidence = "high"
    elif len(stream_rows) >= 120:
        confidence = "medium"
    else:
        confidence = "low"
    return {
        "basis": "stream_elapsed_sec_equal_thirds",
        "start_sec": round(start_sec, 1),
        "end_sec": round(end_sec, 1),
        "span_sec": round(span_sec, 1),
        "n_samples": len(stream_rows),
        "thirds": third_profiles,
        "delta_first_last_pct": {
            "hr": hr_change_pct,
            "speed_kmh": speed_change_pct,
            "cadence": cadence_change_pct,
        },
        "cadence_change_abs_pct": cadence_change_abs_pct,
        "durability_hint": durability_hint,
        "confidence": confidence,
        "method": "three equal elapsed thirds from session_stream.csv; exploratory primitive, not final taxonomy",
    }


def build_composite_context(
    analysis_only_context: dict[str, Any] | None,
    session_row: dict[str, str],
    stream_csv_path: Path | None,
) -> dict[str, Any] | None:
    composite_context: dict[str, Any] = {}
    load_mismatch = build_load_mismatch_context(analysis_only_context, session_row)
    if load_mismatch:
        composite_context["subjective_coherence"] = load_mismatch
    thermal_context = build_thermal_context(session_row)
    if thermal_context:
        composite_context["thermal_context"] = thermal_context
    durability_context = build_durability_thirds_context(stream_csv_path, session_row=session_row)
    if durability_context:
        composite_context["durability_context"] = durability_context
    return composite_context or None


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
    activity_detail = None
    activity_error = None
    try:
        activity_detail = fetch_intervals_activity_detail(row)
    except Exception as exc:
        activity_error = str(exc)
    intervals_payload = None
    intervals_payload_error = None
    try:
        intervals_payload = fetch_intervals_activity_intervals_payload(row)
    except Exception as exc:
        intervals_payload_error = str(exc)
    terrain_context = None
    terrain_error = None
    terrain_intervals = None
    terrain_intervals_error = None
    if _supports_terrain_context(row):
        try:
            if activity_detail is not None:
                gap_mean = parse_float(activity_detail.get("gap"))
                gap_model = _coerce_text_or_none_sentinel(activity_detail.get("gap_model"), {"NONE", "NULL"})
                terrain_context = {
                    "source": "intervals_activity",
                    "gap_mean": round(gap_mean * 3.6, 1) if gap_mean is not None else None,
                    "gap_unit": "km/h",
                    "gap_model": gap_model,
                    "vam_uphill_mean": None,
                    "vam_source": None,
                }
            else:
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
            if intervals_payload is None:
                raise RuntimeError(intervals_payload_error or "intervals payload unavailable")
            fit_records = None
            if fit_file.exists():
                fit_records = parse_fit_terrain_data(fit_file)["records"]
            terrain_intervals = _normalize_terrain_interval_rows(
                row["session_id"],
                intervals_payload,
                fit_records=fit_records,
            )
            terrain_context = _summarize_terrain_context_from_intervals(terrain_context, terrain_intervals, session_row=row)
        except Exception as exc:
            terrain_intervals_error = str(exc)
    analysis_only_context = summarize_intervals_analysis_context(activity_detail, intervals_payload, row)
    composite_context = build_composite_context(analysis_only_context, row, stream_csv)
    if composite_context:
        analysis_only_context = dict(analysis_only_context or {})
        analysis_only_context["composite_context"] = composite_context
    subjective_context = build_subjective_context(row)
    coach_interval_rows = []
    coach_group_rows = []
    if isinstance(intervals_payload, dict):
        coach_interval_rows = _normalize_intervals_structure_rows(
            row["session_id"],
            intervals_payload.get("icu_intervals") or [],
            "icu_interval",
        )
        coach_group_rows = _normalize_intervals_structure_rows(
            row["session_id"],
            intervals_payload.get("icu_groups") or [],
            "icu_group",
        )
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
        "activity_detail": activity_detail,
        "activity_error": activity_error,
        "intervals_payload_error": intervals_payload_error,
        "stream_info": stream_info,
        "terrain_context": terrain_context,
        "terrain_error": terrain_error,
        "terrain_intervals": terrain_intervals,
        "terrain_intervals_error": terrain_intervals_error,
        "analysis_only_context": analysis_only_context,
        "composite_context": composite_context,
        "subjective_context": subjective_context,
        "coach_interval_rows": coach_interval_rows,
        "coach_group_rows": coach_group_rows,
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
    analysis_only_context = summary.get("analysis_only_context") or {}
    subjective_context = summary.get("subjective_context") or {}
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

    if subjective_context:
        lines.extend([
            "## Subjective Context",
            f"- rpe: `{subjective_context.get('rpe')}`",
            f"- feel: `{subjective_context.get('feel')}`",
            f"- notes_present: `{subjective_context.get('notes_present')}`",
            f"- notes_raw: `{subjective_context.get('notes_raw')}`",
            "",
        ])

    composite_context = summary.get("composite_context")
    if not isinstance(composite_context, dict):
        analysis_composite_context = (analysis_only_context.get("composite_context") or {}) if isinstance(analysis_only_context, dict) else {}
        composite_context = analysis_composite_context if isinstance(analysis_composite_context, dict) else {}
    if composite_context:
        subjective_coherence = composite_context.get("subjective_coherence") or {}
        thermal_context = composite_context.get("thermal_context") or {}
        durability_context = composite_context.get("durability_context") or {}
        lines.append("## Composite Context")
        if subjective_coherence:
            lines.extend([
                "### Subjective Coherence",
                f"- state: `{subjective_coherence.get('subjective_coherence_state')}`",
                f"- score: `{subjective_coherence.get('subjective_coherence_score')}`",
                f"- objective_anchor: `{subjective_coherence.get('objective_anchor')}`",
                f"- objective_spread_pct: `{subjective_coherence.get('objective_spread_pct')}`",
                f"- subjective_objective_gap_pct: `{subjective_coherence.get('subjective_objective_gap_pct')}`",
                f"- session_rpe_load_equiv: `{subjective_coherence.get('session_rpe_load_equiv')}`",
                f"- trimp_load_equiv: `{subjective_coherence.get('trimp_load_equiv')}`",
                f"- trimp_load_ratio_ref: `{subjective_coherence.get('trimp_load_ratio_ref')}`",
                f"- driver: `{subjective_coherence.get('driver')}`",
                f"- method: `{subjective_coherence.get('method')}`",
                "",
            ])
        if thermal_context:
            lines.extend([
                "### Thermal Context",
                f"- temperature_c: `{thermal_context.get('temperature_c')}`",
                f"- duration_min: `{thermal_context.get('duration_min')}`",
                f"- threshold_c: `{thermal_context.get('threshold_c')}`",
                f"- excess_c: `{thermal_context.get('excess_c')}`",
                f"- thermal_cost_score: `{thermal_context.get('thermal_cost_score')}`",
                f"- thermal_band: `{thermal_context.get('thermal_band')}`",
                f"- method: `{thermal_context.get('method')}`",
                "",
            ])
        if durability_context:
            delta = durability_context.get("delta_first_last_pct") or {}
            delta_parts = ", ".join(
                f"{key}={value}" for key, value in delta.items() if value is not None
            )
            lines.extend([
                "### Durability Context",
                f"- basis: `{durability_context.get('basis')}`",
                f"- confidence: `{durability_context.get('confidence')}`",
                f"- durability_hint: `{durability_context.get('durability_hint')}`",
                f"- span_sec: `{durability_context.get('span_sec')}`",
                f"- n_samples: `{durability_context.get('n_samples')}`",
                f"- delta_first_last_pct: `{delta_parts or None}`",
                f"- method: `{durability_context.get('method')}`",
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

    if analysis_only_context:
        coach_metrics = analysis_only_context.get("coach_metrics") or {}
        structured = analysis_only_context.get("structured_workout") or {}
        route_context = analysis_only_context.get("route_context") or {}
        coach_lines = ["## Coach Analysis-Only Context"]
        for label, value in (
            ("session_rpe", coach_metrics.get("session_rpe")),
            ("icu_intensity_pct", coach_metrics.get("icu_intensity_pct")),
            ("polarization_index", coach_metrics.get("polarization_index")),
            ("average_stride", coach_metrics.get("average_stride")),
            ("decoupling_pct", coach_metrics.get("decoupling_pct")),
            ("cardiac_drift_pct", coach_metrics.get("cardiac_drift_pct")),
            ("hr_load", coach_metrics.get("hr_load")),
            ("hr_load_type", coach_metrics.get("hr_load_type")),
            ("intervals_count", structured.get("intervals_count")),
            ("groups_count", structured.get("groups_count")),
            ("lap_count", structured.get("lap_count")),
            ("interval_types", structured.get("interval_types")),
            ("intervals_edited", structured.get("intervals_edited")),
            ("route_id", route_context.get("route_id")),
            ("gap_model", route_context.get("gap_model")),
        ):
            if value in (None, "", [], {}):
                continue
            coach_lines.append(f"- {label}: `{value}`")
        coach_lines.extend([
            "- note: capa local de analysis; apoyo narrativo y tactico, no contrato canonico global",
            "",
        ])
        lines.extend(coach_lines)
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
    subjective_context = build_subjective_context(session_row)
    terrain_context = summary.get("terrain_context")
    terrain_fit_context = summary.get("terrain_fit_context")
    analysis_only_context = summary.get("analysis_only_context")
    composite_context = None
    if isinstance(analysis_only_context, dict):
        composite_context = analysis_only_context.get("composite_context")
    terrain_intervals_csv = None
    terrain_climbs_csv = None
    coach_metrics_json = None
    coach_intervals_csv = None
    coach_groups_csv = None
    if artifacts_dir is not None:
        terrain_intervals_path = artifacts_dir / "terrain_intervals.csv"
        if terrain_intervals_path.exists():
            terrain_intervals_csv = str(terrain_intervals_path)
        terrain_climbs_path = artifacts_dir / "terrain_climbs.csv"
        if terrain_climbs_path.exists():
            terrain_climbs_csv = str(terrain_climbs_path)
        coach_metrics_path = artifacts_dir / "coach_metrics.json"
        if coach_metrics_path.exists():
            coach_metrics_json = str(coach_metrics_path)
        coach_intervals_path = artifacts_dir / "coach_intervals.csv"
        if coach_intervals_path.exists():
            coach_intervals_csv = str(coach_intervals_path)
        coach_groups_path = artifacts_dir / "coach_groups.csv"
        if coach_groups_path.exists():
            coach_groups_csv = str(coach_groups_path)
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
    coach_usage_notes = build_coach_usage_notes(sport_family)
    coach_narrative_hints = build_coach_narrative_hints(analysis_only_context, session_row)
    coach_report_examples = build_coach_report_examples(sport_family, analysis_only_context, session_row)

    # --- Vector velocidad desde FIT artifact ---
    speed_metrics: dict | None = None
    if artifacts_dir is not None:
        fit_artifact = artifacts_dir / "session.fit"
        vt1 = parse_float(session_row.get("vt1_used"))
        wbm = session_row.get("work_blocks_min") or ""
        wbn = len([x for x in wbm.split(";") if x.strip()]) if wbm else 0
        speed_metrics = _compute_speed_metrics(fit_artifact, vt1, wbn, sport_family)

    rr_summary_payload = dict(summary)
    rr_summary_payload.pop("analysis_only_context", None)
    rr_summary_payload.pop("composite_context", None)

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
        "subjective_context": subjective_context,
        "composite_context": composite_context,
        "rr_analysis_summary": rr_summary_payload,
        "terrain_context": terrain_context,
        "terrain_fit_context": terrain_fit_context,
        "analysis_only_context": analysis_only_context,
        "terrain_intervals_csv": terrain_intervals_csv,
        "terrain_climbs_csv": terrain_climbs_csv,
        "coach_metrics_json": coach_metrics_json,
        "coach_intervals_csv": coach_intervals_csv,
        "coach_groups_csv": coach_groups_csv,
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
            "subjective_context": subjective_context,
            "composite_context": composite_context,
            "coach_usage_notes": coach_usage_notes,
            "coach_narrative_hints": coach_narrative_hints,
            "coach_report_examples": coach_report_examples,
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
    analysis_only_context = manifest.get("analysis_only_context")
    if isinstance(analysis_only_context, dict) and analysis_only_context:
        enriched["analysis_only_context"] = analysis_only_context
        composite_context = analysis_only_context.get("composite_context")
        if isinstance(composite_context, dict) and composite_context:
            enriched["composite_context"] = composite_context
    subjective_context = manifest.get("subjective_context")
    if isinstance(subjective_context, dict) and subjective_context:
        enriched["subjective_context"] = subjective_context
    return enriched


def build_ai_handoff_markdown(
    report_dir: Path,
    artifacts_dir: Path,
    payload_path: Path,
    summary_path: Path,
    blocks_path: Path | None,
    terrain_intervals_path: Path | None,
    terrain_climbs_path: Path | None,
    coach_metrics_path: Path | None,
    coach_intervals_path: Path | None,
    coach_groups_path: Path | None,
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
    if coach_metrics_path:
        lines.append(f"- `{coach_metrics_path}`")
    if coach_intervals_path:
        lines.append(f"- `{coach_intervals_path}`")
    if coach_groups_path:
        lines.append(f"- `{coach_groups_path}`")
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
            "- usar `coach_metrics.json`, `coach_intervals.csv` y `coach_groups.csv` solo como enriquecimiento local de `analysis/`, nunca como contrato canonico global",
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
    coach_metrics_path: Path | None,
    coach_intervals_path: Path | None,
    coach_groups_path: Path | None,
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
    if coach_metrics_path:
        lines.append(f"- coach metrics no canonicos: `{coach_metrics_path}`")
    if coach_intervals_path:
        lines.append(f"- estructura ICU por intervalo: `{coach_intervals_path}`")
    if coach_groups_path:
        lines.append(f"- estructura ICU por grupo: `{coach_groups_path}`")
    if style_refs:
        lines.extend(["", "## Referencias de estilo opcionales"])
        lines.extend([f"- `{path}`" for path in style_refs])
    lines.extend(
        [
            "",
            "## Instruccion",
            "Redacta un informe rico de sesion en espanol, con tono tecnico y prudente, usando `session_payload.json` como fuente compacta principal y sin inventar metricas ni fuentes no presentes.",
            "- trata `analysis_only_context` y sus sidecars coach como enriquecimiento local de `analysis/`; no los eleves a verdad canonica global si contradicen `sessions.csv` o los contratos HRV",
            "- si existe `session_payload.json.subjective_context.notes_raw`, usala como nota manual del atleta en `Contexto subjetivo`; no la mezcles con `session_rpe`, `feel` ni con `load`/`trimp`",
            "- si existe `session_payload.json.composite_context`, usalo como capa exploratoria para `subjective_coherence/load_mismatch`, `thermal_context` y `durability_context`; no lo conviertas en contrato canonico ni en taxonomia cerrada",
            "",
            "## Sport Family",
            "- usa `session_payload.json.meta.sport_family` como guia primaria de lenguaje y semantica",
            "- aplica las notas de familia incluidas en `session_payload.json.narrative_targets.sport_family_notes`",
            "- aplica tambien `session_payload.json.narrative_targets.coach_usage_notes` y `coach_narrative_hints` cuando exista `analysis_only_context`",
            "- si existe `session_payload.json.narrative_targets.coach_report_examples`, usalos como ejemplos de traduccion narrativa por seccion, adaptandolos al caso sin copiarlos literalmente",
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
            "",
            "## Regla de bloque",
            "- la carga de entrenamiento es un continuo: no silos por deporte si otra sesion de distinto deporte explica mejor la secuencia de fatiga o recuperacion",
            "- para `Encaje en el bloque`, prioriza sesiones comparables por etapa de bloque, proximidad temporal, intensidad y tipo de estimulo; el mismo deporte ayuda, pero no es un filtro duro",
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
    coach_metrics_path = None
    coach_intervals_csv_path = None
    coach_groups_csv_path = None
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

    analysis_only_context = manifest.get("analysis_only_context")
    if isinstance(analysis_only_context, dict) and analysis_only_context:
        summary["analysis_only_context"] = analysis_only_context
        coach_metrics_path = artifacts_dir / "coach_metrics.json"
        write_json(coach_metrics_path, analysis_only_context)
    coach_interval_rows = manifest.get("coach_interval_rows") or []
    if isinstance(coach_interval_rows, list) and coach_interval_rows:
        coach_intervals_csv_path = write_intervals_structure_csv(
            artifacts_dir / "coach_intervals.csv",
            coach_interval_rows,
        )
    coach_group_rows = manifest.get("coach_group_rows") or []
    if isinstance(coach_group_rows, list) and coach_group_rows:
        coach_groups_csv_path = write_intervals_structure_csv(
            artifacts_dir / "coach_groups.csv",
            coach_group_rows,
        )

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
            coach_metrics_path=coach_metrics_path,
            coach_intervals_path=coach_intervals_csv_path,
            coach_groups_path=coach_groups_csv_path,
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
            coach_metrics_path=coach_metrics_path,
            coach_intervals_path=coach_intervals_csv_path,
            coach_groups_path=coach_groups_csv_path,
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
        "coach_metrics_json": str(coach_metrics_path) if coach_metrics_path else None,
        "coach_intervals_csv": str(coach_intervals_csv_path) if coach_intervals_csv_path else None,
        "coach_groups_csv": str(coach_groups_csv_path) if coach_groups_csv_path else None,
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
