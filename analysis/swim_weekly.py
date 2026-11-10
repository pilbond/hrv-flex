"""Sidecar semanal local de natación para `analysis/`.

Agrega, para la semana ISO (lunes-domingo) del ancla:
- minutos de natación frente a carrera/trail desde `sessions.csv`
  (`duration_min` en ambos términos),
- `swim_share_of_swim_run = swim_min / (swim_min + run_trail_min)`,
- distancia por estilo y exposición a braza desde los `swim_context` de los
  informes de sesión ya generados, con cobertura explícita.

No escribe `ENDURANCE_HRV_weekly_coach.json` ni ningún output global. El
cociente no implica equivalencia de carga ni demuestra sustitución de impacto.
"""
from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Iterable

import pandas as pd

from analysis import swim_context

SIDECAR_NAME = "swim_weekly_context"
SCHEMA_VERSION = "swim_weekly_context_v1"
SWIM_SPORTS = ("swim",)
RUN_TRAIL_SPORTS = ("road_run", "trail_run")
HISTORY_WEEKS = 4


def _num(value: Any) -> float | None:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return None if out != out else out


def week_bounds(anchor: date) -> tuple[date, date]:
    start = anchor - timedelta(days=anchor.weekday())
    return start, start + timedelta(days=6)


def _week_minutes(sessions: pd.DataFrame, start: date, end: date) -> dict[str, Any]:
    dates = pd.to_datetime(sessions["Fecha"], errors="coerce").dt.date
    in_week = sessions[(dates >= start) & (dates <= end)]
    duration = pd.to_numeric(in_week["duration_min"], errors="coerce")
    sport = in_week["sport"].astype(str).str.strip().str.lower()
    swim_mask = sport.isin(SWIM_SPORTS)
    run_mask = sport.isin(RUN_TRAIL_SPORTS)
    swim_min = float(duration[swim_mask].fillna(0).sum())
    run_min = float(duration[run_mask].fillna(0).sum())
    denominator = swim_min + run_min
    return {
        "week_start": start.isoformat(),
        "week_end": end.isoformat(),
        "swim_sessions": int(swim_mask.sum()),
        "swim_min": round(swim_min, 1),
        "run_trail_sessions": int(run_mask.sum()),
        "run_trail_min": round(run_min, 1),
        "swim_share_of_swim_run": round(swim_min / denominator, 3) if denominator > 0 else None,
        "swim_duration_missing": int(duration[swim_mask].isna().sum()),
        "run_trail_duration_missing": int(duration[run_mask].isna().sum()),
    }


def load_swim_contexts(reports_root: Path) -> list[dict[str, Any]]:
    """`swim_context` de los informes de sesión existentes, con su fecha e id."""
    return swim_context.load_prior_swim_contexts(reports_root)


def _week_technique(contexts: Iterable[dict[str, Any]], session_ids: set[str], start: date, end: date) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    by_style: dict[str, float] = {}
    for context in contexts:
        day = str(context.get("session_date") or "")
        if not (start.isoformat() <= day <= end.isoformat()):
            continue
        # Solo sesiones de natación de esa semana en sessions.csv: un informe
        # huérfano (sesión borrada o renombrada) no aporta cobertura.
        if str(context.get("session_id")) not in session_ids:
            continue
        distribution = context.get("stroke_distribution") or {}
        if context.get("swim_source") == "polar_v4":
            for style, item in distribution.items():
                by_style[style] = by_style.get(style, 0.0) + (_num((item or {}).get("distance_m")) or 0.0)
        rows.append({
            "session_date": day,
            "session_id": context.get("session_id"),
            "swim_source": context.get("swim_source"),
            "distance_m": context.get("distance_m"),
            "primary_stroke": context.get("primary_stroke"),
            "breaststroke_pct": context.get("breaststroke_pct"),
            "swolf_by_stroke": context.get("swolf_by_stroke"),
            "srpe_load": context.get("srpe_load"),
            "status": context.get("status"),
        })
    rows.sort(key=lambda r: (r["session_date"], str(r["session_id"])))
    total = sum(by_style.values())
    distribution = {
        style: {"distance_m": round(value, 1), "pct": round(100.0 * value / total, 1) if total else None}
        for style, value in sorted(by_style.items())
    }
    return {
        "sessions_with_swim_context": len(rows),
        "sessions_with_polar": sum(1 for r in rows if r["swim_source"] == "polar_v4"),
        "stroke_distribution_basis": "distance_m" if distribution else None,
        "stroke_distribution": distribution or None,
        "breaststroke_pct": distribution.get("BREASTSTROKE", {}).get("pct", 0.0) if distribution else None,
        "srpe_load_total": round(sum(r["srpe_load"] for r in rows if r["srpe_load"] is not None), 1)
        if any(r["srpe_load"] is not None for r in rows) else None,
        "srpe_sessions": sum(1 for r in rows if r["srpe_load"] is not None),
        "sessions": rows,
    }


def build_swim_weekly_context(
    sessions: pd.DataFrame,
    contexts: Iterable[dict[str, Any]],
    anchor: date,
    *,
    history_weeks: int = HISTORY_WEEKS,
) -> dict[str, Any]:
    start, end = week_bounds(anchor)
    current = _week_minutes(sessions, start, end)
    history = [
        _week_minutes(sessions, start - timedelta(days=7 * k), end - timedelta(days=7 * k))
        for k in range(history_weeks, 0, -1)
    ]
    dates = pd.to_datetime(sessions["Fecha"], errors="coerce").dt.date
    sport = sessions["sport"].astype(str).str.strip().str.lower()
    week_swim_ids = {
        str(value)
        for value in sessions.loc[(dates >= start) & (dates <= end) & sport.isin(SWIM_SPORTS), "session_id"]
    } if "session_id" in sessions.columns else set()
    technique = _week_technique(contexts, week_swim_ids, start, end)
    reasons: list[str] = []
    if current["swim_sessions"] and technique["sessions_with_polar"] < current["swim_sessions"]:
        reasons.append("swim_context_incomplete")
    if current["swim_share_of_swim_run"] is None:
        reasons.append("no_swim_or_run_minutes")
    return {
        "schema_version": SCHEMA_VERSION,
        "sidecar": SIDECAR_NAME,
        "anchor_date": anchor.isoformat(),
        "week_start": start.isoformat(),
        "week_end": end.isoformat(),
        "categories": {"swim": list(SWIM_SPORTS), "run_trail": list(RUN_TRAIL_SPORTS)},
        "duration_basis": "sessions.duration_min",
        "share_definition": "swim_min / (swim_min + run_trail_min); otros deportes no entran",
        "current_week": current,
        "previous_weeks": history,
        "technique": technique,
        "technique_coverage": {
            "swim_sessions": current["swim_sessions"],
            "with_polar_swim_context": technique["sessions_with_polar"],
        },
        "quality_reasons": reasons,
        "notes": [
            "el cociente describe reparto de minutos, no equivalencia de carga ni sustitucion de impacto",
            "breaststroke_pct describe exposicion a braza, no riesgo",
            "la distancia por estilo solo cubre sesiones con swim_context de Polar en sus informes",
        ],
    }


def _fmt(value: Any, suffix: str = "") -> str:
    return "n/d" if value is None else f"{value}{suffix}"


def render_swim_weekly_markdown(payload: dict[str, Any]) -> str:
    current = payload["current_week"]
    technique = payload["technique"]
    share = current["swim_share_of_swim_run"]
    lines = [
        f"# Natación semanal {payload['week_start']} a {payload['week_end']}",
        "",
        "Capa local de `analysis/`; no es contrato canónico ni prescripción.",
        "",
        "## Reparto natación / carrera-trail",
        "",
        f"- Natación: `{current['swim_sessions']}` sesiones, `{current['swim_min']}` min.",
        f"- Carrera y trail: `{current['run_trail_sessions']}` sesiones, `{current['run_trail_min']}` min.",
        f"- `swim_share_of_swim_run`: `{_fmt(None if share is None else round(100 * share, 1), '%')}` "
        "(reparto de minutos, no equivalencia de carga).",
        "",
        "| Semana | Natación (min) | Carrera/trail (min) | Proporción natación |",
        "|---|---:|---:|---:|",
    ]
    for week in [*payload["previous_weeks"], current]:
        week_share = week["swim_share_of_swim_run"]
        lines.append(
            f"| {week['week_start']} | {week['swim_min']} | {week['run_trail_min']} | "
            f"{_fmt(None if week_share is None else round(100 * week_share, 1), '%')} |"
        )
    lines.extend([
        "",
        "## Estilos (Polar)",
        "",
        f"- Cobertura: `{technique['sessions_with_polar']}` de `{current['swim_sessions']}` sesiones con `swim_context` de Polar.",
    ])
    distribution = technique.get("stroke_distribution") or {}
    for style, item in distribution.items():
        lines.append(f"- {style}: `{item['distance_m']} m` (`{_fmt(item['pct'], '%')}`).")
    if technique.get("breaststroke_pct") is not None:
        lines.append(f"- Braza: `{technique['breaststroke_pct']}%` de la distancia con estilo (exposición, no riesgo).")
    if technique.get("srpe_load_total") is not None:
        lines.append(
            f"- sRPE acumulado: `{technique['srpe_load_total']} AU` en `{technique['srpe_sessions']}` sesiones con RPE."
        )
    if payload["quality_reasons"]:
        lines.extend(["", f"Motivos de calidad: `{', '.join(payload['quality_reasons'])}`."])
    return "\n".join(lines) + "\n"


def build_swim_weekly_sidecar(
    *,
    today,
    out_dir: Path,
    sessions_csv: Path,
    reports_root: Path,
) -> dict[str, Any]:
    anchor = pd.Timestamp(today).date()
    sessions = pd.read_csv(sessions_csv)
    payload = build_swim_weekly_context(sessions, load_swim_contexts(reports_root), anchor)
    payload["inputs"] = {"sessions_csv": str(sessions_csv), "reports_root": str(reports_root)}
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / f"{SIDECAR_NAME}.json"
    md_path = out_dir / f"{SIDECAR_NAME}.md"
    json_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, allow_nan=False), encoding="utf-8")
    md_path.write_text(render_swim_weekly_markdown(payload), encoding="utf-8")
    return {
        "week_start": payload["week_start"],
        "week_end": payload["week_end"],
        "anchor_date": payload["anchor_date"],
        "sidecar": SIDECAR_NAME,
        "artifact_stem": SIDECAR_NAME,
        "report_md": str(md_path),
        "report_json": str(json_path),
    }
