from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
from pathlib import Path

import pandas as pd

from analysis import run_weekly_analysis_prep
from analysis import sya15_continuity


ROOT = Path(__file__).resolve().parents[1]
ANALYSIS_DIR = ROOT / "analysis"
DATA_DIR = ROOT / "data"
DEFAULT_SESSIONS_DAY = DATA_DIR / "ENDURANCE_HRV_sessions_day.csv"
DEFAULT_SESSIONS = DATA_DIR / "ENDURANCE_HRV_sessions.csv"
DEFAULT_DASHBOARD = DATA_DIR / "ENDURANCE_HRV_master_DASHBOARD.csv"
DEFAULT_CORE = DATA_DIR / "ENDURANCE_HRV_master_CORE.csv"
DEFAULT_SLEEP = DATA_DIR / "ENDURANCE_HRV_sleep.csv"
DEFAULT_WEEKLY_DISTRIBUTION = DATA_DIR / "ENDURANCE_HRV_intensity_distribution_weekly.csv"
DEFAULT_WEEKLY_COACH = DATA_DIR / "ENDURANCE_HRV_weekly_coach.json"
REPORT_SYNC_TOKEN_PATTERN = re.compile(r"<!--\s*report_sync_token:\s*([a-f0-9]{12,64})\s*-->")
REPORT_SYNC_SCHEMA_VERSION = "weekly-v1"
LOAD_RATIO_HIGH = 1.3
LOAD_RATIO_LOW = 0.7


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build a reproducible weekly auto-report under analysis/reports/weekly/."
    )
    parser.add_argument("--today", type=str, default=None, help="Optional YYYY-MM-DD anchor date.")
    parser.add_argument(
        "--weekly-dir",
        type=Path,
        default=None,
        help="Optional weekly directory. Defaults to analysis/reports/weekly/<week_start>_<week_end>/.",
    )
    parser.add_argument(
        "--skip-prep",
        action="store_true",
        help="Use an existing weekly_prep_manifest.json instead of regenerating weekly prep.",
    )
    parser.add_argument("--input", type=Path, default=DEFAULT_WEEKLY_DISTRIBUTION)
    parser.add_argument("--focus-sport", type=str, default=None)
    parser.add_argument("--window-size", type=int, default=sya15_continuity.WINDOW_SIZE)
    parser.add_argument("--min-positive", type=int, default=None)
    return parser


def _load_csv(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    if "Fecha" in df.columns:
        df["Fecha"] = pd.to_datetime(df["Fecha"])
    if "window_start" in df.columns:
        df["window_start"] = pd.to_datetime(df["window_start"])
    if "window_end" in df.columns:
        df["window_end"] = pd.to_datetime(df["window_end"])
    return df


def _load_required_csv(path: Path, label: str) -> pd.DataFrame:
    try:
        return _load_csv(path)
    except FileNotFoundError as exc:
        raise FileNotFoundError(
            f"Missing required weekly analysis input ({label}): {path}"
        ) from exc


def _display_path(path: Path) -> str:
    try:
        return path.resolve().relative_to(ROOT.resolve()).as_posix()
    except ValueError:
        return str(path)


def _format_number(value, digits: int = 1) -> str:
    if value is None or pd.isna(value):
        return "—"
    return f"{float(value):.{digits}f}"


def _format_int(value) -> str:
    if value is None or pd.isna(value):
        return "—"
    return str(int(round(float(value))))


def _format_duration_hours(minutes) -> str:
    if minutes is None or pd.isna(minutes):
        return "—"
    hours = float(minutes) / 60.0
    return f"{hours:.1f} h"


def _safe_str(value, fallback: str = "—") -> str:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return fallback
    text = str(value).strip()
    return text if text else fallback


def _markdown_table(df: pd.DataFrame) -> str:
    columns = [str(column) for column in df.columns]
    header = "| " + " | ".join(columns) + " |"
    separator = "| " + " | ".join(["---"] * len(columns)) + " |"
    rows = []
    for row in df.fillna("—").itertuples(index=False, name=None):
        rows.append("| " + " | ".join(str(cell) for cell in row) + " |")
    return "\n".join([header, separator] + rows)


def _build_calendar(today) -> pd.DataFrame:
    week_start, week_end = run_weekly_analysis_prep.build_weekly_analysis_sidecars.weekly_bounds(today)
    days = pd.date_range(start=week_start, end=week_end, freq="D")
    return pd.DataFrame({"Fecha": days})


def _load_weekly_context(today, weekly_dir: Path) -> dict[str, object]:
    sessions_day = _load_required_csv(DEFAULT_SESSIONS_DAY, "sessions_day")
    sessions = _load_required_csv(DEFAULT_SESSIONS, "sessions")
    dashboard = _load_required_csv(DEFAULT_DASHBOARD, "dashboard")
    core = _load_required_csv(DEFAULT_CORE, "core")
    sleep = _load_required_csv(DEFAULT_SLEEP, "sleep")
    weekly_distribution = _load_required_csv(DEFAULT_WEEKLY_DISTRIBUTION, "weekly_distribution")
    coach_data = None
    if DEFAULT_WEEKLY_COACH.exists():
        coach_data = json.loads(DEFAULT_WEEKLY_COACH.read_text(encoding="utf-8"))

    calendar = _build_calendar(today)
    week_start = calendar["Fecha"].min()
    week_end = calendar["Fecha"].max()
    week_mask = (sessions_day["Fecha"] >= week_start) & (sessions_day["Fecha"] <= week_end)
    sessions_day_week = sessions_day.loc[week_mask].copy()
    sessions_week = sessions.loc[(sessions["Fecha"] >= week_start) & (sessions["Fecha"] <= week_end)].copy()
    dashboard_week = dashboard.loc[(dashboard["Fecha"] >= week_start) & (dashboard["Fecha"] <= week_end)].copy()
    core_week = core.loc[(core["Fecha"] >= week_start) & (core["Fecha"] <= week_end)].copy()
    sleep_week = sleep.loc[(sleep["Fecha"] >= week_start) & (sleep["Fecha"] <= week_end)].copy()
    distribution_week = weekly_distribution.loc[weekly_distribution["window_start"] == week_start].copy()

    return {
        "calendar": calendar,
        "week_start": week_start,
        "week_end": week_end,
        "sessions_day": sessions_day,
        "sessions_day_week": sessions_day_week,
        "sessions_week": sessions_week,
        "dashboard_week": dashboard_week,
        "core": core,
        "core_week": core_week,
        "sleep_week": sleep_week,
        "distribution_week": distribution_week,
        "weekly_coach": coach_data,
        "weekly_dir": weekly_dir,
    }


def _build_profile_table(context: dict[str, object]) -> pd.DataFrame:
    calendar = context["calendar"].copy()
    sessions_day_week = context["sessions_day_week"].copy()
    dashboard_week = context["dashboard_week"].copy()
    sleep_week = context["sleep_week"].copy()
    sessions_week = context["sessions_week"].copy()
    for column in ["load_day", "work_total_min_day", "z3_min_day"]:
        if column not in sessions_day_week.columns:
            sessions_day_week[column] = pd.NA

    session_names = (
        sessions_week.groupby("Fecha")["sport"]
        .apply(lambda items: " + ".join(items.astype(str).tolist()))
        .rename("Sesion")
        .reset_index()
    )

    profile = calendar.merge(sleep_week[["Fecha", "polar_sleep_duration_min"]], on="Fecha", how="left")
    profile = profile.merge(dashboard_week[["Fecha", "gate_badge", "Action"]], on="Fecha", how="left")
    profile = profile.merge(
        sessions_day_week[["Fecha", "load_day", "work_total_min_day", "z3_min_day"]],
        on="Fecha",
        how="left",
    )
    profile = profile.merge(session_names, on="Fecha", how="left")

    profile["Dia"] = profile["Fecha"].dt.strftime("%a")
    profile["Fecha_txt"] = profile["Fecha"].dt.strftime("%Y-%m-%d")
    profile["Sueño"] = profile["polar_sleep_duration_min"].map(_format_duration_hours)
    profile["gate_badge"] = profile["gate_badge"].fillna("—")
    profile["Action"] = profile["Action"].fillna("—")
    profile["Sesion"] = profile["Sesion"].fillna("Descanso")
    profile["load_day"] = profile["load_day"].fillna(0).map(_format_int)
    profile["work_total_min_day"] = profile["work_total_min_day"].map(_format_number)
    profile["z3_min_day"] = profile["z3_min_day"].map(_format_number)
    return profile[
        ["Dia", "Fecha_txt", "Sueño", "gate_badge", "Action", "Sesion", "load_day", "work_total_min_day", "z3_min_day"]
    ].rename(columns={"Fecha_txt": "Fecha"})


def _build_load_comparison(context: dict[str, object]) -> tuple[pd.DataFrame, float | None]:
    sessions_day = context["sessions_day"].copy()
    week_start = context["week_start"]
    weeks = []
    for offset in range(3, -1, -1):
        start = week_start - pd.Timedelta(days=7 * offset)
        end = start + pd.Timedelta(days=6)
        rows = sessions_day.loc[(sessions_day["Fecha"] >= start) & (sessions_day["Fecha"] <= end)]
        weeks.append(
            {
                "Semana": f"{start.date()} / {end.date()}",
                "load_total": rows["load_day"].fillna(0).sum(),
                "work_total_min": rows["work_total_min_day"].fillna(0).sum(),
                "z3_min_total": rows["z3_min_day"].fillna(0).sum(),
                "D+": rows["elev_gain_day"].fillna(0).sum(),
                "D-": rows["elev_loss_day"].fillna(0).sum(),
                "Duración_total_min": rows["total_duration_min"].fillna(0).sum(),
            }
        )
    comparison = pd.DataFrame(weeks)
    previous_mean = comparison.iloc[:3]["load_total"].mean() if len(comparison) >= 4 else None
    return comparison, previous_mean


def _load_ratio_text(current_load: float, previous_mean: float | None) -> tuple[str, float | None]:
    if previous_mean is None or previous_mean == 0:
        return "Sin comparación suficiente con 3 semanas previas.", None
    ratio = current_load / previous_mean
    if ratio > LOAD_RATIO_HIGH:
        label = "pico de carga relativo"
    elif ratio < LOAD_RATIO_LOW:
        label = "descarga o reducción material"
    else:
        label = "mantenimiento o progresión moderada"
    return f"La carga semanal equivale al {ratio * 100:.1f}% de la media de las 3 semanas previas: {label}.", ratio


def _build_distribution_table(context: dict[str, object]) -> pd.DataFrame:
    distribution_week = context["distribution_week"].copy()
    if distribution_week.empty:
        return pd.DataFrame()
    table = distribution_week[
        [
            "sport",
            "total_duration_min",
            "z1_pct_weighted",
            "z2_pct_weighted",
            "z3_pct_weighted",
            "work_total_min",
            "work_n_blocks",
            "distribution_pattern",
            "distribution_confidence",
        ]
    ].copy()
    table.columns = [
        "Deporte",
        "Tiempo_aeróbico_min",
        "Z1 %",
        "Z2 %",
        "Z3 %",
        "work_total_min",
        "work_n_blocks",
        "Patrón",
        "Confianza",
    ]
    return table


def _build_hrv_weekly_trend(core: pd.DataFrame, week_start) -> pd.DataFrame:
    rows = []
    for offset in range(7, -1, -1):
        start = week_start - pd.Timedelta(days=7 * offset)
        end = start + pd.Timedelta(days=6)
        week_rows = core.loc[(core["Fecha"] >= start) & (core["Fecha"] <= end) & (core["Calidad"] == "OK")]
        rows.append(
            {
                "Semana": start.date().isoformat(),
                "RMSSD media (OK)": week_rows["RMSSD_stable"].mean(),
                "n días OK": int(len(week_rows)),
                "HR reposo media": week_rows["HR_stable"].mean(),
            }
        )
    return pd.DataFrame(rows)


def _build_sleep_table(sleep_week: pd.DataFrame) -> pd.DataFrame:
    table = sleep_week.copy()
    if table.empty:
        return pd.DataFrame()
    table["Noche"] = table["Fecha"].dt.strftime("%Y-%m-%d")
    return table[
        ["Noche", "polar_sleep_duration_min", "polar_deep_pct", "polar_sleep_score", "polar_efficiency_pct"]
    ].rename(
        columns={
            "polar_sleep_duration_min": "Duración_min",
            "polar_deep_pct": "Deep%",
            "polar_sleep_score": "Score",
            "polar_efficiency_pct": "Eficiencia%",
        }
    )


def _build_divergences(context: dict[str, object]) -> list[str]:
    dashboard_required = ["Fecha", "gate_badge", "Action"]
    sessions_required = ["Fecha", "load_day", "work_total_min_day", "z3_min_day"]
    dashboard_week = context["dashboard_week"].copy()
    sessions_day_week = context["sessions_day_week"].copy()

    missing_dashboard = [column for column in dashboard_required if column not in dashboard_week.columns]
    if missing_dashboard:
        return [f"Divergences check skipped: missing dashboard columns: {', '.join(missing_dashboard)}."]

    for column in sessions_required:
        if column not in sessions_day_week.columns:
            sessions_day_week[column] = pd.NA

    merged = dashboard_week[dashboard_required].merge(
        sessions_day_week[sessions_required],
        on="Fecha",
        how="left",
    )
    divergences = []
    for _, row in merged.iterrows():
        action = row.get("Action")
        load_day = row.get("load_day")
        work_day = row.get("work_total_min_day")
        z3_day = row.get("z3_min_day")
        if action == "SUAVE_O_DESCANSO" and ((pd.notna(work_day) and work_day > 0) or (pd.notna(z3_day) and z3_day > 0)):
            divergences.append(
                f"{row['Fecha'].date()}: Action={action} pero hubo carga estructurada "
                f"(load={_format_int(load_day)}, work={_format_number(work_day)}, z3={_format_number(z3_day)})."
            )
    return divergences


def _build_context_payload(context: dict[str, object], manifest: dict[str, object]) -> dict[str, object]:
    week_start = context["week_start"].date().isoformat()
    week_end = context["week_end"].date().isoformat()
    return {
        "week_start": week_start,
        "week_end": week_end,
        "manifest_path": manifest["manifest_path"],
        "sidecars": manifest["sidecars"],
        "profile_rows": len(context["calendar"]),
        "sessions_week_count": int(len(context["sessions_week"])),
        "distribution_week_count": int(len(context["distribution_week"])),
    }


def _resolve_week_bounds(manifest: dict[str, object], today) -> tuple[pd.Timestamp, pd.Timestamp]:
    manifest_week_start = pd.Timestamp(manifest["week_start"])
    manifest_week_end = pd.Timestamp(manifest["week_end"])
    today_week_start = run_weekly_analysis_prep.build_weekly_analysis_sidecars.weekly_bounds(today)[0]
    if manifest_week_start != today_week_start:
        raise ValueError(
            "Provided today does not match weekly_prep_manifest week_start: "
            f"{today_week_start.date()} != {manifest_week_start.date()}"
        )
    return manifest_week_start, manifest_week_end


def _weekly_report_sync_token(manifest: dict[str, object], week_start: str, week_end: str) -> str:
    sidecar_fingerprint = [
        {
            "sidecar": sidecar.get("sidecar"),
            "focus_sport": sidecar.get("focus_sport"),
            "window_size": sidecar.get("window_size"),
            "min_positive": sidecar.get("min_positive"),
            "report_md": sidecar.get("report_md"),
            "report_json": sidecar.get("report_json"),
        }
        for sidecar in manifest.get("sidecars", [])
    ]
    raw = json.dumps(
        {
            "week_start": week_start,
            "week_end": week_end,
            "manifest_path": manifest["manifest_path"],
            "sidecars": sidecar_fingerprint,
        },
        sort_keys=True,
        ensure_ascii=False,
    )
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def extract_report_sync_token(report_path: Path) -> str | None:
    if not report_path.exists():
        return None
    head = "\n".join(report_path.read_text(encoding="utf-8").splitlines()[:5])
    match = REPORT_SYNC_TOKEN_PATTERN.search(head)
    return match.group(1) if match else None


def build_report_sync_status(
    *,
    report_path: Path,
    current_token: str,
    manifest_path: Path,
    context_path: Path,
    report_auto_path: Path,
) -> dict[str, object]:
    exists = report_path.exists()
    report_token = extract_report_sync_token(report_path) if exists else None
    if not exists:
        status = "missing"
        reason = f"{report_path.name} does not exist"
    elif not report_token:
        status = "unmanaged_legacy"
        reason = f"{report_path.name} exists but has no report_sync_token"
    elif report_token == current_token:
        status = "up_to_date"
        reason = f"{report_path.name} token matches current weekly analysis artifacts"
    else:
        status = "stale"
        reason = f"{report_path.name} token differs from current weekly analysis artifacts"
    return {
        "schema_version": REPORT_SYNC_SCHEMA_VERSION,
        "status": status,
        "reason": reason,
        "current_token": current_token,
        "report_token": report_token,
        "report_exists": exists,
        "paths": {
            "report_ia_md": str(report_path),
            "weekly_prep_manifest_json": str(manifest_path),
            "weekly_analysis_context_json": str(context_path),
            "report_auto_md": str(report_auto_path),
        },
    }


def build_weekly_final_report_placeholder(
    *,
    week_start: str,
    week_end: str,
    report_sync_token: str,
) -> str:
    return "\n".join(
        [
            f"<!-- report_sync_token: {report_sync_token} -->",
            "",
            f"# Informe semanal · {week_start} / {week_end}",
            "",
            "> Pendiente de redacción interpretativa final.",
            "",
            "Usa `analyst_prompt.md` y `ai_handoff.md` como contrato de lectura.",
            "Si el token no coincide con el semanal actual, reescribe el informe completo.",
            "",
        ]
    )


def build_weekly_analyst_prompt_markdown(
    *,
    weekly_dir: Path,
    manifest_path: Path,
    context_path: Path,
    report_auto_path: Path,
    report_sync_token: str,
    sidecars: list[dict[str, object]],
) -> str:
    lines = [
        "# Weekly Analyst Prompt",
        "",
        "Usa Codex/GPT como analista conversacional para el informe semanal del atleta.",
        "",
        "## Carga obligatoria",
        "Antes de redactar `report.ia.md`, leer en este orden y no saltarse ningun paso:",
        f"1. `{_display_path(weekly_dir / 'analyst_prompt.md')}`",
        f"2. `{_display_path(weekly_dir / 'ai_handoff.md')}`",
        f"3. `{_display_path(ANALYSIS_DIR / 'AGENTS.md')}`",
        f"4. `{_display_path(ANALYSIS_DIR / 'analyst_prompt_rules.md')}`",
        f"5. `{_display_path(ANALYSIS_DIR / 'WEEKLY_ANALYSIS_METHOD.md')}`",
        f"6. `{_display_path(ANALYSIS_DIR / 'ENDURANCE_AGENT_DOMAIN.md')}`",
        f"7. `{_display_path(manifest_path)}`",
        f"8. `{_display_path(context_path)}`",
        f"9. `{_display_path(report_auto_path)}`",
        f"10. `{_display_path(DATA_DIR / 'ENDURANCE_HRV_sessions_day.csv')}`",
        f"11. `{_display_path(DATA_DIR / 'ENDURANCE_HRV_sessions.csv')}`",
        f"12. `{_display_path(DATA_DIR / 'ENDURANCE_HRV_master_DASHBOARD.csv')}`",
        f"13. `{_display_path(DATA_DIR / 'ENDURANCE_HRV_master_CORE.csv')}`",
        f"14. `{_display_path(DATA_DIR / 'ENDURANCE_HRV_sleep.csv')}`",
        f"15. `{_display_path(DATA_DIR / 'ENDURANCE_HRV_intensity_distribution_weekly.csv')}`",
    ]
    if DEFAULT_WEEKLY_COACH.exists():
        lines.append(f"16. `{_display_path(DEFAULT_WEEKLY_COACH)}`")
    if sidecars:
        lines.extend(["", "## Sidecars semanales declarados en el manifest"])
        lines.extend([f"- `{_display_path(Path(sidecar['report_md']))}`" for sidecar in sidecars])
        lines.extend([f"- `{_display_path(Path(sidecar['report_json']))}`" for sidecar in sidecars])
    lines.extend(
        [
            "",
            "## Archivos a usar",
            "- usar `weekly_prep_manifest.json` como fuente unica de descubrimiento de sidecars",
            "- usar `report.auto.md` como borrador reproducible de partida, no como evidencia primaria",
            "- usar `sessions_day`, `sessions`, `DASHBOARD`, `CORE`, `sleep` y distribucion semanal como evidencia canonica",
            "- usar los sidecars declarados en el manifest solo como apoyo local de `analysis/`",
            "",
            "## Sincronizacion de report.ia.md",
            f"- al principio de `report.ia.md`, insertar exactamente `<!-- report_sync_token: {report_sync_token} -->`",
            "- si ya existe un token distinto en `report.ia.md`, reescribe el informe completo para alinearlo con el semanal actual",
            "",
            "## Instruccion",
            "Redacta un informe semanal en espanol, tecnico y prudente, siguiendo `WEEKLY_ANALYSIS_METHOD.md`.",
            "- separa lo observado en fuentes canonicas de lo inferido",
            "- no descubras sidecars por nombre; usa solo las rutas declaradas en el manifest",
            "- usa `report.auto.md` para acelerar estructura y tablas, pero corrige o amplía solo con evidencia de fuentes primarias",
            "- si una conclusion depende de un sidecar local, declaralo explicitamente como capa local de `analysis/`",
        ]
    )
    return "\n".join(lines) + "\n"


def build_weekly_ai_handoff_markdown(
    *,
    weekly_dir: Path,
    manifest_path: Path,
    context_path: Path,
    report_auto_path: Path,
    report_sync_token: str,
    sidecars: list[dict[str, object]],
) -> str:
    lines = [
        "# Weekly AI Handoff",
        "",
        "## Archivos principales a pasar a la IA",
        f"1. `{_display_path(weekly_dir / 'analyst_prompt.md')}`",
        f"2. `{_display_path(manifest_path)}`",
        f"3. `{_display_path(context_path)}`",
        f"4. `{_display_path(report_auto_path)}`",
        f"5. `{_display_path(ANALYSIS_DIR / 'AGENTS.md')}`",
        f"6. `{_display_path(ANALYSIS_DIR / 'analyst_prompt_rules.md')}`",
        f"7. `{_display_path(ANALYSIS_DIR / 'WEEKLY_ANALYSIS_METHOD.md')}`",
        f"8. `{_display_path(ANALYSIS_DIR / 'ENDURANCE_AGENT_DOMAIN.md')}`",
        "",
        "## Fuentes canonicas recomendadas",
        f"- `{_display_path(DATA_DIR / 'ENDURANCE_HRV_sessions_day.csv')}`",
        f"- `{_display_path(DATA_DIR / 'ENDURANCE_HRV_sessions.csv')}`",
        f"- `{_display_path(DATA_DIR / 'ENDURANCE_HRV_master_DASHBOARD.csv')}`",
        f"- `{_display_path(DATA_DIR / 'ENDURANCE_HRV_master_CORE.csv')}`",
        f"- `{_display_path(DATA_DIR / 'ENDURANCE_HRV_sleep.csv')}`",
        f"- `{_display_path(DATA_DIR / 'ENDURANCE_HRV_intensity_distribution_weekly.csv')}`",
    ]
    if DEFAULT_WEEKLY_COACH.exists():
        lines.append(f"- `{_display_path(DEFAULT_WEEKLY_COACH)}`")
    if sidecars:
        lines.extend(["", "## Sidecars declarados en el manifest"])
        for sidecar in sidecars:
            lines.append(f"- `{_display_path(Path(sidecar['report_md']))}`")
            lines.append(f"- `{_display_path(Path(sidecar['report_json']))}`")
    lines.extend(
        [
            "",
            "## Regla de uso",
            "- el manifest manda sobre cualquier escaneo manual de `artifacts/`",
            "- las fuentes canonicas del pipeline semanal mandan sobre `report.auto.md` y sobre los sidecars locales",
            "- `report.auto.md` sirve como borrador reproducible, no como fuente de verdad",
            "",
            "## Sincronizacion de report.ia.md",
            f"- al crear o actualizar `report.ia.md`, poner al principio la linea `<!-- report_sync_token: {report_sync_token} -->`",
            "- si el token no coincide con el semanal actual, tratar `report.ia.md` como obsoleto hasta reescribirlo",
        ]
    )
    return "\n".join(lines) + "\n"


def render_weekly_report(today, manifest: dict[str, object], context: dict[str, object]) -> str:
    week_start = context["week_start"].date().isoformat()
    week_end = context["week_end"].date().isoformat()
    weekly_coach = context["weekly_coach"] or {}
    week_load = weekly_coach.get("week_load")
    profile_table = _build_profile_table(context)
    comparison_table, previous_mean = _build_load_comparison(context)
    current_load = comparison_table.iloc[-1]["load_total"] if not comparison_table.empty else 0.0
    load_ratio_text, ratio = _load_ratio_text(current_load, previous_mean)
    distribution_table = _build_distribution_table(context)
    hrv_table = _build_hrv_weekly_trend(context["core"], context["week_start"])
    sleep_table = _build_sleep_table(context["sleep_week"])
    divergences = _build_divergences(context)
    try:
        sya15_sidecar = run_weekly_analysis_prep.get_sidecar(manifest, "sya15_continuity")
    except (KeyError, ValueError):
        sya15_sidecar = None

    verdict = "Semana neutra."
    if ratio is not None:
        if ratio > LOAD_RATIO_HIGH:
            verdict = "Semana exigente con pico de carga relativo."
        elif ratio < LOAD_RATIO_LOW:
            verdict = "Semana reducida o de descarga relativa."
        else:
            verdict = "Semana productiva en rango de mantenimiento o progresión moderada."
    if sya15_sidecar is not None:
        sya15_guidance_line = (
            f"- Si se quiere reutilizar la lectura de continuidad por deporte, partir del sidecar declarado en el manifest: "
            f"`{Path(sya15_sidecar['report_md']).name}`."
        )
    else:
        sya15_guidance_line = (
            "- No hay sidecar SYA-15 declarado en este manifest; si hace falta esa capa, regenerar el prep semanal."
        )

    lines = [
        f"# Informe semanal · {week_start} / {week_end}",
        "",
        f"**Semana coach:** {_safe_str(weekly_coach.get('week_type'), '—')} · **Carga semanal:** {_safe_str(week_load, '—')}",
        "",
        "---",
        "",
        "## 0. Veredicto semanal",
        "",
        f"{verdict} {load_ratio_text}",
        f"El semanal local se apoya en `{Path(manifest['manifest_path']).name}` como punto único de descubrimiento de sidecars.",
    ]
    if sya15_sidecar is None:
        lines.append("SYA-15 no está presente en este manifest semanal; el informe continúa sin ese sidecar local.")
    else:
        lines.append(
            f"SYA-15 disponible: `{Path(sya15_sidecar['report_md']).name}` ({sya15_sidecar['focus_sport']}, umbral {sya15_sidecar['min_positive']}/{sya15_sidecar['window_size']}w)."
        )
    lines.extend(
        [
            "",
            "---",
            "",
            "## 1. Perfil del microciclo",
            "",
            _markdown_table(profile_table),
            "",
            "---",
            "",
            "## 2. Carga y estructura",
            "",
            _markdown_table(comparison_table),
            "",
            load_ratio_text,
            "",
            "---",
            "",
            "## 3. Distribución observada por deporte",
            "",
        ]
    )
    if distribution_table.empty:
        lines.extend(["No hay fila semanal disponible en `ENDURANCE_HRV_intensity_distribution_weekly.csv` para esta semana.", ""])
    else:
        lines.append(_markdown_table(distribution_table))
        lines.append("")
        if sya15_sidecar is not None:
            lines.append(f"Sidecar local citado desde manifest: `{Path(sya15_sidecar['report_md']).name}`.")
            lines.append("")

    lines.extend(
        [
            "---",
            "",
            "## 4. Recuperación y absorción",
            "",
            _markdown_table(hrv_table.rename(columns={"RMSSD media (OK)": "RMSSD media (OK)", "HR reposo media": "HR reposo media"})),
            "",
        ]
    )
    if not sleep_table.empty:
        lines.extend([_markdown_table(sleep_table), ""])

    load_values = context["sessions_day_week"]["load_day"].fillna(0).tolist()
    if load_values:
        mean_load = sum(load_values) / 7.0
        variance = sum((value - mean_load) ** 2 for value in load_values) / 7.0
        sd = math.sqrt(variance)
        monotony = mean_load / sd if sd else float("nan")
        strain = mean_load * 7.0 * monotony if pd.notna(monotony) else float("nan")
    else:
        monotony = float("nan")
        strain = float("nan")

    lines.extend(
        [
            "---",
            "",
            "## 5. Monotonía y strain",
            "",
            f"- Monotonía fija 7d: {_format_number(monotony, 2)}",
            f"- Strain fijo 7d: {_format_number(strain, 0)}",
            "",
            "---",
            "",
            "## 6. Divergencias relevantes con el sistema",
            "",
        ]
    )
    if divergences:
        lines.extend([f"- {item}" for item in divergences])
    else:
        lines.append("No se detectan divergencias materiales por regla simple entre `Action` y la carga ejecutada.")

    lines.extend(
        [
            "",
            "---",
            "",
            "## 7. Orientación para la semana siguiente",
            "",
            "- Revisar primero el cierre en `gate_badge` y `Action` del último día disponible en `ENDURANCE_HRV_master_DASHBOARD.csv`.",
            sya15_guidance_line,
            "- Mantener la jerarquía: fuentes canónicas primero; sidecars locales solo como apoyo.",
            "",
            "---",
            "",
            "## 8. Confianza y limitaciones",
            "",
            f"- Sidecars descubiertos desde manifest: {len(manifest['sidecars'])}",
            f"- Sesiones en la semana: {len(context['sessions_week'])}",
            f"- Filas de distribución semanal disponibles: {len(context['distribution_week'])}",
            "- Este `report.auto.md` es un borrador reproducible y prudente; no sustituye una redacción semanal interpretativa completa cuando haga falta juicio fino.",
            "",
        ]
    )
    return "\n".join(lines)


def analyze_weekly(
    *,
    today,
    weekly_dir: Path,
    input_path: Path,
    focus_sport: str | None,
    window_size: int,
    min_positive: int | None,
    skip_prep: bool,
) -> dict[str, object]:
    if skip_prep:
        manifest = run_weekly_analysis_prep.load_weekly_prep_manifest(weekly_dir / "weekly_prep_manifest.json")
        _resolve_week_bounds(manifest, today)
    else:
        manifest = run_weekly_analysis_prep.build_weekly_prep(
            today=today,
            weekly_dir=weekly_dir,
            input_path=input_path,
            focus_sport=focus_sport,
            window_size=window_size,
            min_positive=min_positive,
        )

    context = _load_weekly_context(today, weekly_dir)
    report = render_weekly_report(today, manifest, context)
    report_path = weekly_dir / "report.auto.md"
    context_path = weekly_dir / "weekly_analysis_context.json"
    analyst_prompt_path = weekly_dir / "analyst_prompt.md"
    ai_handoff_path = weekly_dir / "ai_handoff.md"
    final_report_path = weekly_dir / "report.ia.md"
    report_sync_status_path = weekly_dir / "artifacts" / "report_sync_status.json"
    report_path.write_text(report, encoding="utf-8")
    context_payload = _build_context_payload(context, manifest)
    context_path.write_text(json.dumps(context_payload, indent=2, ensure_ascii=False, allow_nan=False), encoding="utf-8")
    report_sync_token = _weekly_report_sync_token(
        manifest,
        context["week_start"].date().isoformat(),
        context["week_end"].date().isoformat(),
    )
    analyst_prompt_path.write_text(
        build_weekly_analyst_prompt_markdown(
            weekly_dir=weekly_dir,
            manifest_path=Path(manifest["manifest_path"]),
            context_path=context_path,
            report_auto_path=report_path,
            report_sync_token=report_sync_token,
            sidecars=manifest["sidecars"],
        ),
        encoding="utf-8",
    )
    ai_handoff_path.write_text(
        build_weekly_ai_handoff_markdown(
            weekly_dir=weekly_dir,
            manifest_path=Path(manifest["manifest_path"]),
            context_path=context_path,
            report_auto_path=report_path,
            report_sync_token=report_sync_token,
            sidecars=manifest["sidecars"],
        ),
        encoding="utf-8",
    )
    if not final_report_path.exists():
        final_report_path.write_text(
            build_weekly_final_report_placeholder(
                week_start=context["week_start"].date().isoformat(),
                week_end=context["week_end"].date().isoformat(),
                report_sync_token=report_sync_token,
            ),
            encoding="utf-8",
        )
    report_sync_status_path.parent.mkdir(parents=True, exist_ok=True)
    report_sync_status = build_report_sync_status(
        report_path=final_report_path,
        current_token=report_sync_token,
        manifest_path=Path(manifest["manifest_path"]),
        context_path=context_path,
        report_auto_path=report_path,
    )
    report_sync_status_path.write_text(
        json.dumps(report_sync_status, indent=2, ensure_ascii=False, allow_nan=False),
        encoding="utf-8",
    )
    return {
        "week_start": context["week_start"].date().isoformat(),
        "week_end": context["week_end"].date().isoformat(),
        "weekly_dir": str(weekly_dir),
        "manifest_path": manifest["manifest_path"],
        "report_auto_md": str(report_path),
        "report_ia_md": str(final_report_path),
        "weekly_analysis_context": str(context_path),
        "analyst_prompt": str(analyst_prompt_path),
        "ai_handoff": str(ai_handoff_path),
        "report_sync_status": str(report_sync_status_path),
    }


def main() -> int:
    args = build_parser().parse_args()
    today = sya15_continuity.resolve_today(args.today)
    weekly_dir = args.weekly_dir if args.weekly_dir is not None else run_weekly_analysis_prep.default_weekly_dir(today)
    payload = analyze_weekly(
        today=today,
        weekly_dir=weekly_dir,
        input_path=args.input,
        focus_sport=args.focus_sport,
        window_size=args.window_size,
        min_positive=args.min_positive,
        skip_prep=args.skip_prep,
    )
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
