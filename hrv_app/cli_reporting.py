from __future__ import annotations
import json
import math
from pathlib import Path

try:
    import pandas as pd
except ImportError:  # pragma: no cover - exercised implicitly when pandas is absent
    pd = None

from jinja2 import Environment, FileSystemLoader, TemplateNotFound

from .config import (
    COLOR_EMOJI,
    CORE_PATH,
    DATE_STRING_LENGTH,
    FINAL_PATH,
    GATE_EMOJI,
    PANDAS_AVAILABLE,
    QUIET,
    SSM_SHADOW_METADATA_PATH,
    _qprint,
)


CLI_TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates" / "cli"
CLI_TEMPLATE_ENV = Environment(
    loader=FileSystemLoader(str(CLI_TEMPLATES_DIR)),
    autoescape=False,
    trim_blocks=False,
    lstrip_blocks=False,
)


def _get_color_emoji(color_value, default="⚪"):
    """Convierte valor de color a emoji."""
    return COLOR_EMOJI.get(color_value, default)


def _get_gate_emoji(gate_value, default="⚪"):
    """Convierte gate_badge a emoji."""
    if gate_value is None:
        return default
    value = str(gate_value).strip().upper()
    if value.startswith("VERDE"):
        key = "VERDE"
    elif value.startswith("ÁMBAR") or value.startswith("AMBAR"):
        key = "ÁMBAR"
    elif value.startswith("ROJO"):
        key = "ROJO"
    elif value.startswith("NO"):
        key = "NO"
    else:
        key = value.replace("Á", "A")
    return GATE_EMOJI.get(key, default)


def _format_metric(value, decimals=1):
    """Formatea métrica numérica o devuelve N/A."""
    if PANDAS_AVAILABLE:
        is_valid = pd.notna(value) and value != "N/A"
    else:
        is_valid = value is not None and value != "N/A"
    if is_valid:
        try:
            return f"{float(value):.{decimals}f}"
        except (ValueError, TypeError):
            return "N/A"
    return "N/A"


def _has_value(value):
    if PANDAS_AVAILABLE:
        return value is not None and pd.notna(value) and str(value).strip() != "" and str(value) != "N/A"
    return value is not None and str(value).strip() != "" and str(value) != "N/A"


def _format_recovery_quality(value):
    mapping = {
        "rich": "contexto completo",
        "basic": "contexto parcial",
        "none": "sin contexto",
    }
    return mapping.get(str(value or "").strip().lower(), str(value or "N/A"))


def _format_recovery_class(value):
    mapping = {
        "supported": "senales alineadas",
        "fragile": "senales fragiles",
        "conflicted": "senales mixtas",
        "neutral": "sin senal clara",
    }
    return mapping.get(str(value or "").strip().lower(), str(value or "N/A"))


def _row_value(row, key):
    if row is None:
        return None
    if hasattr(row, "get"):
        return row.get(key)
    try:
        return row[key]
    except (KeyError, TypeError, IndexError):
        return None


def _maybe_float(value):
    if value is None or (PANDAS_AVAILABLE and pd.isna(value)):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _load_ssm_daily_summary(expected_date=None):
    if not SSM_SHADOW_METADATA_PATH.exists():
        return None
    try:
        payload = json.loads(SSM_SHADOW_METADATA_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    summary = payload.get("daily_user_summary")
    if not isinstance(summary, dict) or summary.get("status") != "ok":
        return None
    if expected_date is not None and str(summary.get("date")) != str(expected_date):
        return None
    return summary


from .gate_text import format_gate_reason as _format_gate_reason
from .gate_text import format_gate_next_step as _format_gate_next_step


def _print_header(title: str, width: int = 25, leading_blank: bool = True, trailing_blank: bool = False):
    if QUIET:
        return
    line = "=" * width
    if leading_blank:
        _qprint()
    _qprint(line)
    _qprint(title)
    _qprint(line)
    if trailing_blank:
        _qprint()


def _print_divider(width: int = 30, leading_blank: bool = False, trailing_blank: bool = False):
    if QUIET:
        return
    line = "=" * width
    if leading_blank:
        _qprint()
    else:
        _qprint(line)
    if trailing_blank:
        _qprint()


def _render_report(report: dict | None):
    if not report or QUIET:
        return
    if report.get("leading_blank"):
        _qprint()
    title = report.get("title")
    if title:
        _qprint(title)
    for line in report.get("lines", []):
        if line == "":
            _qprint()
        else:
            _qprint(line)
    if report.get("trailing_blank"):
        _qprint()


def _render_template_report(template_name: str, report: dict | None):
    if not report or QUIET:
        return
    try:
        template = CLI_TEMPLATE_ENV.get_template(template_name)
    except TemplateNotFound:
        _render_report(report)
        return
    context = dict(report)
    body_lines = []
    title = context.get("title")
    if title:
        body_lines.append(title)
    body_lines.extend(context.get("lines") or [])
    context["body"] = "\n".join(body_lines)
    rendered = template.render(**context).rstrip()
    if rendered:
        _qprint(rendered)


def _build_report(title: str | None, lines: list[str], leading_blank: bool = False, trailing_blank: bool = False) -> dict:
    return {
        "title": title,
        "leading_blank": leading_blank,
        "lines": lines,
        "trailing_blank": trailing_blank,
    }


def build_message_report(message: str, leading_blank: bool = False, trailing_blank: bool = False) -> dict:
    return _build_report(None, [message], leading_blank=leading_blank, trailing_blank=trailing_blank)


def build_lines_report(lines: list[str], leading_blank: bool = False, trailing_blank: bool = False) -> dict:
    return _build_report(None, lines, leading_blank=leading_blank, trailing_blank=trailing_blank)


def build_bulleted_report(title: str, items: list[str], leading_blank: bool = False, trailing_blank: bool = False) -> dict:
    return _build_report(
        None,
        [title, *[f"   - {item}" for item in items]],
        leading_blank=leading_blank,
        trailing_blank=trailing_blank,
    )


def build_sync_completed_report(updated_date=None) -> dict:
    lines = ["✅ SINCRONIZACIÓN COMPLETADA"]
    if updated_date:
        lines.append(f"📊 CORE actualizado hasta hoy ({updated_date})")
    else:
        lines.append("📊 CORE actualizado hasta hoy")
    lines.append("💡 No hay RR nuevos que procesar")
    return _build_report(None, lines, leading_blank=True)


def build_no_local_rr_files_report() -> dict:
    return _build_report(
        None,
        [
            "⚠️  No hay archivos RR locales para reprocesar",
            "   - rr_downloads/ está vacío",
            "   - --all no descarga nada nuevo; usa el modo automático o --days N para traer RR desde Dropbox",
        ],
        leading_blank=True,
    )


def build_master_already_updated_report() -> dict:
    return _build_report(
        None,
        [
            "✅ CORE ya está actualizado con todas las sesiones",
            "   No hay nada nuevo que procesar",
        ],
        leading_blank=True,
    )


def build_pipeline_stage_report(stage_label: str) -> dict:
    return _build_report(None, [f"▶️  {stage_label}"], leading_blank=True, trailing_blank=True)


def build_no_rr_matinales_report(from_d, to_d) -> dict:
    return _build_report(
        None,
        [
            "⚠️  No hay RR matinales disponibles para el periodo objetivo",
            f"   Rango objetivo: {from_d} a {to_d}",
            "   Dropbox no cubre estas fechas todavía; no hay fallback Polar.",
            "   Usa --days N para reintentar más adelante o revisa Dropbox.",
        ],
        leading_blank=True,
    )


def build_debug_session_report(i: int, date_str: str, sport: str, duration) -> dict:
    return _build_report(None, [f"  [{i}] {date_str} | Sport: '{sport}' | Duration: {duration}"])


def _print_sync_completed(updated_date=None):
    _render_report(build_sync_completed_report(updated_date=updated_date))


def _print_no_local_rr_files():
    _render_report(build_no_local_rr_files_report())


def _print_master_already_updated():
    _render_report(build_master_already_updated_report())


def build_last_daily_summary() -> dict | None:
    """Construye el resumen diario como datos, sin imprimir nada."""
    if not PANDAS_AVAILABLE:
        return None

    if FINAL_PATH.exists():
        try:
            df = pd.read_csv(FINAL_PATH)
            if df.empty or "Fecha" not in df.columns:
                return None
            last_row = df.sort_values("Fecha").iloc[-1]
        except (FileNotFoundError, pd.errors.EmptyDataError, KeyError, IndexError):
            return None

        fecha = last_row.get("Fecha", "N/A")
        hr = last_row.get("HR_today", "N/A")
        rmssd = last_row.get("RMSSD_stable", "N/A")
        gate = last_row.get("gate_badge", "N/A")
        action = last_row.get("Action", "N/A")
        action_detail = last_row.get("Action_detail", "N/A")
        reason = last_row.get("gate_razon_base60", "N/A")
        reason_text = last_row.get("reason_text", "N/A")
        decision_path = last_row.get("decision_path", "N/A")
        recovery_class = last_row.get("recovery_support_class", "N/A")
        recovery_quality = last_row.get("recovery_context_quality", "N/A")
        recovery_discordance_reason = last_row.get("recovery_discordance_reason", "N/A")
        calidad = last_row.get("Calidad", "N/A")
        stab = last_row.get("HRV_Stability", "N/A")
        degraded = str(last_row.get("baseline60_degraded", False)).strip().lower() in {"true", "1", "yes"}
        degraded_best = str(last_row.get("degraded_vs_best", False)).strip().lower() in {"true", "1", "yes"}
        degraded_current = str(last_row.get("degraded_vs_current_normal", False)).strip().lower() in {"true", "1", "yes"}
        ln_base60 = last_row.get("ln_base60", "N/A")
        n_base60 = last_row.get("n_base60", "N/A")
        healthy_rmssd = last_row.get("healthy_rmssd", "N/A")
        warning_threshold = last_row.get("warning_threshold", "N/A")
        warning_threshold_best = last_row.get("warning_threshold_best", "N/A")
        warning_threshold_current = last_row.get("warning_threshold_current_normal", "N/A")

        base60_rmssd = "N/A"
        if _has_value(ln_base60):
            try:
                base60_rmssd = f"{math.exp(float(ln_base60)):.1f}"
            except (ValueError, TypeError, OverflowError):
                base60_rmssd = "N/A"

        gate_emoji = _get_gate_emoji(gate)
        lines = [
            f"📅 Fecha:           {fecha}",
            f"💓 HR hoy:          {_format_metric(hr)} bpm",
            f"📊 RMSSD:           {_format_metric(rmssd)} ms",
            f"🚦 Gate:            {gate_emoji} {gate}",
            f"🧭 Acción:          {action} / {action_detail}",
            f"🧾 Qué pasó:        {_format_gate_reason(reason, last_row)}",
            f"🧾 Qué hacer:       {_format_gate_next_step(reason)}",
        ]
        if _has_value(decision_path) and str(decision_path).strip() != "BASE60_ONLY":
            lines.append(f"🧩 Decision path:   {decision_path}")
        lines.append(
            "🧪 Contexto recuperación: "
            f"{_format_recovery_quality(recovery_quality)} / {_format_recovery_class(recovery_class)}"
        )
        if _has_value(recovery_discordance_reason):
            lines.append(f"⚠️  Discordancia:   {recovery_discordance_reason}")
        lines.extend(
            [
                f"✅ Calidad:         {calidad}",
                f"📈 Estabilidad:     {stab}",
            ]
        )
        if base60_rmssd != "N/A":
            base60_suffix = f" (n={int(float(n_base60))})" if _has_value(n_base60) else ""
            lines.append(f"📐 Base 60d:        {base60_rmssd} ms{base60_suffix}")
        if _has_value(healthy_rmssd):
            lines.append(f"📏 Healthy RMSSD:   {_format_metric(healthy_rmssd)} ms")
        if _has_value(warning_threshold):
            lines.append(f"⚠️  Límite inferior de referencia: {_format_metric(warning_threshold)} ms")
        if bool(degraded):
            lines.append("⚠️  Base 60d por debajo de tu referencia habitual")
        if _has_value(warning_threshold_best) and _has_value(warning_threshold_current):
            lines.append(
                "🧭 Baseline largo: "
                f"best={'sí' if degraded_best else 'no'} / current={'sí' if degraded_current else 'no'}"
            )
        ln_rmssd_today = _maybe_float(last_row.get("lnRMSSD_today"))
        ln_rmssd_used = _maybe_float(last_row.get("lnRMSSD_used"))
        swc_ln = _maybe_float(last_row.get("SWC_ln"))
        if _has_value(ln_base60) and ln_rmssd_used is not None and swc_ln is not None:
            try:
                ln_base60_f = float(ln_base60)
                rmssd_base60 = math.exp(ln_base60_f)
                rmssd_used = math.exp(ln_rmssd_used)
                delta_ln = ln_rmssd_used - ln_base60_f
                delta_ms = rmssd_used - rmssd_base60
                raw_note = ""
                if ln_rmssd_today is not None and abs(ln_rmssd_today - ln_rmssd_used) > 1e-6:
                    raw_note = f"; bruto hoy {_format_metric(rmssd)} ms"
                lines.append(
                    "🔎 Gate 2D:        "
                    f"usado {_format_metric(rmssd_used)} ms vs base60 {_format_metric(rmssd_base60)} ms "
                    f"(Δln {delta_ln:+.3f}; Δ≈{delta_ms:+.1f} ms; SWC_ln {_format_metric(swc_ln)})"
                    f"{raw_note}"
                )
            except (ValueError, TypeError, OverflowError):
                pass
        lines.append(f"🧠 Reason text:     {reason_text}")
        ssm_summary = _load_ssm_daily_summary(expected_date=fecha)
        if ssm_summary:
            lines.append(
                "🧠 SSM estado:      "
                f"{ssm_summary.get('state_label', 'N/A')} / confianza {ssm_summary.get('confidence_label', 'N/A')}"
            )
            lines.append(f"🧠 SSM lectura:     {ssm_summary.get('interpretive_text', 'N/A')}")

        return {
            "title": "💓 Última Medición HRV (V4)",
            "leading_blank": False,
            "lines": lines,
            "trailing_blank": False,
        }

    if not CORE_PATH.exists():
        return None

    try:
        df = pd.read_csv(CORE_PATH)
        if df.empty or "Fecha" not in df.columns:
            return None
        last_row = df.sort_values("Fecha").iloc[-1]
    except (FileNotFoundError, pd.errors.EmptyDataError, KeyError, IndexError):
        return None

    lines = [
        "",
        f"📅 Fecha:          {last_row.get('Fecha', 'N/A')}",
        f"💓 HR promedio:    {_format_metric(last_row.get('HR_stable', 'N/A'))} bpm",
        f"📊 RMSSD:          {_format_metric(last_row.get('RMSSD_stable', 'N/A'))} ms",
        f"✅ Calidad:        {last_row.get('Calidad', 'N/A')}",
        f"📈 Estabilidad:    {last_row.get('HRV_Stability', 'N/A')}",
    ]
    flags = last_row.get("Flags", "")
    if pd.notna(flags) and flags:
        lines.append(f"🚩 Flags:          {flags}")
    return {
        "title": "💓 Última Medición HRV (CORE)",
        "leading_blank": False,
        "lines": lines,
        "trailing_blank": False,
    }


def build_last_7_days_summary() -> dict | None:
    """Construye el resumen compacto de 7 días como datos, sin imprimir nada."""
    if not PANDAS_AVAILABLE:
        return None

    use_final = FINAL_PATH.exists()
    src_path = FINAL_PATH if use_final else CORE_PATH
    if not src_path.exists():
        return None

    try:
        df = pd.read_csv(src_path)
        if df.empty or "Fecha" not in df.columns:
            return None
    except (FileNotFoundError, pd.errors.EmptyDataError, KeyError, IndexError):
        return None

    df_sorted = df.sort_values("Fecha")
    last_7 = df_sorted.tail(7)
    if len(last_7) == 0:
        return None

    title = "📊 RESUMEN ÚLTIMOS 7 DÍAS (V4)" if use_final else "📊 RESUMEN ÚLTIMOS 7 DÍAS (CORE)"
    lines = [""]
    for _, row in last_7.iterrows():
        fecha = row.get("Fecha", "N/A")
        fecha_str = fecha
        if isinstance(fecha, str) and len(fecha) == DATE_STRING_LENGTH:
            fecha_str = fecha[2:]

        hr = row.get("HR_today", "N/A") if use_final else row.get("HR_stable", "N/A")
        rmssd = row.get("RMSSD_stable", "N/A")
        hr_str = _format_metric(hr)
        rmssd_str = _format_metric(rmssd)

        if use_final:
            gate = row.get("gate_badge", "N/A")
            action = row.get("Action", "N/A")
            gate_emoji = _get_gate_emoji(gate)
            lines.append(f"{fecha_str}  💓{hr_str:>5}  📊{rmssd_str:>5}  {gate_emoji} {gate}  → {action}")
        else:
            lines.append(f"{fecha_str}  💓{hr_str:>5}  📊{rmssd_str:>5}")

    return {
        "title": title,
        "leading_blank": False,
        "lines": lines,
        "trailing_blank": False,
    }


def show_last_daily_summary():
    """Muestra el último daily summary (FINAL si existe, si no CORE)."""
    report = build_last_daily_summary()
    if report is None:
        return
    _render_template_report("text_report.txt.j2", report)


def show_last_7_days_summary():
    """Muestra resumen compacto de los últimos 7 días (FINAL si existe, si no CORE)."""
    report = build_last_7_days_summary()
    if report is None:
        return
    _render_template_report("text_report.txt.j2", report)


def show_latest_hrv_summaries():
    """Muestra el resumen diario y el histórico corto más recientes."""
    show_last_daily_summary()
    show_last_7_days_summary()
