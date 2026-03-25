#!/usr/bin/env python3
from __future__ import annotations

import csv
import gzip
import json
import re
import shutil
import subprocess
import sys
from datetime import datetime
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

from polar_hrv_automation import (
    FIELD_START_TIME,
    _get_field_variant,
    _iso_to_dt,
    extract_rr_ms,
    get_exercise_with_samples,
    list_exercises,
    load_tokens,
    parse_duration_to_minutes,
    write_rr_csv,
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


def _parse_float(value: str | None) -> float | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


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


def fetch_intervals_stream_csv(row: dict[str, str], target_csv: Path) -> dict[str, Any]:
    from build_sessions import API_KEY, ATHLETE_ID

    if not API_KEY or not ATHLETE_ID:
        raise RuntimeError("faltan INTERVALS_API_KEY o INTERVALS_ATHLETE_ID")

    session_id = row.get("session_id")
    if not session_id:
        raise ValueError("session row has no session_id")

    client = IntervalsClient(API_KEY, ATHLETE_ID)
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
    from build_sessions import API_KEY, ATHLETE_ID

    if not API_KEY or not ATHLETE_ID:
        raise RuntimeError("faltan INTERVALS_API_KEY o INTERVALS_ATHLETE_ID")

    session_id = row.get("session_id")
    if not session_id:
        raise ValueError("session row has no session_id")

    client = IntervalsClient(API_KEY, ATHLETE_ID)
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
    target_dt = _target_session_datetime(row)
    target_date = target_dt.date()
    target_duration = _parse_float(row.get("duration_min"))
    candidates: list[tuple[float, float, dict[str, Any]]] = []

    for ex in exercises:
        start_raw = _get_field_variant(ex, *FIELD_START_TIME, default="")
        start_dt = _iso_to_dt(start_raw)
        if not start_dt or start_dt.date() != target_date:
            continue
        delta_min = abs((start_dt - target_dt).total_seconds()) / 60.0
        dur_raw = ex.get("duration", "")
        duration_min = parse_duration_to_minutes(dur_raw) if dur_raw else None
        duration_gap = abs(duration_min - target_duration) if duration_min is not None and target_duration is not None else 999.0
        candidates.append((delta_min, duration_gap, ex))

    if not candidates:
        raise RuntimeError(f"no se encontro ejercicio Polar para {row.get('session_id')} en {target_date}")

    candidates.sort(key=lambda item: (item[0], item[1]))
    best_delta, best_duration_gap, best = candidates[0]
    if best_delta > 20:
        raise RuntimeError(
            f"match Polar demasiado lejano: {best.get('id')} a {best_delta:.1f} min del inicio esperado"
        )
    return {
        "exercise": best,
        "start_delta_min": round(best_delta, 3),
        "duration_gap_min": None if best_duration_gap == 999.0 else round(best_duration_gap, 3),
    }


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
    fit_info = None
    fit_error = None
    try:
        fit_info = fetch_intervals_fit_file(row, fit_file)
    except Exception as exc:
        fit_error = str(exc)
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
    rmssd_1m = summary.get("rmssd_1min") or {}
    rmssd_5m = summary.get("rmssd_5min") or {}
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

    if rr_unavailable:
        lines.extend([
            "## ⚠️ RR No Disponible",
            f"- motivo: {summary.get('rr_error')}",
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
    for item in rr_context.get("evidence") or []:
        lines.append(f"- rr: {item}")
    return "\n".join(lines) + "\n"


def build_conversational_payload(
    summary: dict[str, Any],
    manifest: dict[str, Any],
    session_row: dict[str, str],
    artifacts_dir: Path | None = None,
) -> dict[str, Any]:
    sport_family = analyzer_sport_from_session(session_row)
    session_date = session_row.get("Fecha") or manifest.get("date")
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
    if sessions_metadata:
        stream_sampling = sessions_metadata.get("stream_sampling")
    versions = contract_version_status()

    # --- Vector velocidad desde FIT artifact ---
    speed_metrics: dict | None = None
    if artifacts_dir is not None:
        fit_artifact = artifacts_dir / "session.fit"
        vt1 = _parse_float(session_row.get("vt1_used"))
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
        },
        "session_row": session_row,
        "rr_analysis_summary": summary,
        "context": {
            "sessions_day": sessions_day,
            "sleep": sleep_row,
            "final": final_row,
            "dashboard": dashboard_row,
            "sessions_metadata": {
                "pipeline_version": sessions_metadata.get("pipeline_version") if sessions_metadata else None,
                "build_time": sessions_metadata.get("build_time") if sessions_metadata else None,
                "stream_sampling": stream_sampling,
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


def build_ai_handoff_markdown(
    report_dir: Path,
    artifacts_dir: Path,
    payload_path: Path,
    summary_path: Path,
    blocks_path: Path | None,
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
    technical_report_md = report_dir / "technical_report.md"
    technical_report_md.write_text(render_report_markdown(summary), encoding="utf-8")
    write_json(artifacts_dir / "manifest.json", manifest)

    generated_blocks_path = artifacts_dir / f"{slug}_blocks.csv"
    blocks_path = artifacts_dir / "blocks.csv"
    if generated_blocks_path.exists():
        generated_blocks_path.replace(blocks_path)

    fit_artifact_path = None
    fit_path = manifest.get("fit_path")
    if fit_path:
        fit_src = Path(fit_path)
        if fit_src.exists():
            fit_artifact_path = artifacts_dir / "session.fit"
            shutil.copy2(fit_src, fit_artifact_path)

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
                path.unlink()
        if stderr_path.exists() and stderr_path.read_text(encoding="utf-8").strip() == "":
            stderr_path.unlink()
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
        shutil.rmtree(bundle_dir)
