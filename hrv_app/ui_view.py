"""Capa de presentación para la UI web (viewmodel).

Centraliza el formato de strings y la composición del viewmodel que consumen
las plantillas Jinja y el JavaScript del dashboard. Antes vivía repartido
entre ``web_ui.py`` (composición) y ``static/ui.js`` (reconstrucción), con
dos fuentes de verdad para los mismos textos.

Contrato público:
    - ``compose_hrv_summary(diagnostics, *, unavailable_text)``: produce las
      claves ``hrv_summary_*`` que ya formaban parte de ``/api/status.diagnostics``.
      Se mantiene la forma original para no romper tests ni consumidores.
    - ``build_view(diagnostics)``: produce un viewmodel estructurado y versionado
      pensado para que la UI no conozca nombres internos del pipeline.

El viewmodel se expone en ``/api/status.view`` como capa nueva; ``diagnostics``
se conserva intacto para compatibilidad con tests y debugging.
"""

from __future__ import annotations

import math
import re
from typing import Any


VIEW_VERSION = 1

DEFAULT_UNAVAILABLE_TEXT = "Todavía no hay salida FINAL disponible."

_RR_DATE_RE = re.compile(r"(\d{4})-(\d{2})-(\d{2})")


def fmt_number(value: Any, decimals: int = 1) -> str:
    try:
        n = float(value)
    except (TypeError, ValueError):
        return "-"
    return f"{n:.{decimals}f}"


def fmt_exp_from_log(value: Any) -> str:
    try:
        n = float(value)
    except (TypeError, ValueError):
        return "-"
    return f"{math.exp(n):.1f}"


def normalize_summary_text(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()


def render_ai_brief_text(summary: Any, detail: Any) -> str:
    summary_text = normalize_summary_text(summary)
    detail_text = normalize_summary_text(detail)
    if not summary_text:
        return detail_text
    if not detail_text:
        return summary_text
    if detail_text.startswith(summary_text):
        return detail_text
    return f"{summary_text} {detail_text}"


def fmt_rr_date_label(rr_filename: Any) -> str:
    raw = str(rr_filename or "").strip()
    match = _RR_DATE_RE.search(raw)
    if not match:
        return ""
    return f"{match.group(3)}/{match.group(2)}/{match.group(1)}"


def compose_hrv_summary(diagnostics: dict, *, unavailable_text: str | None = None) -> dict:
    """Compone los textos canónicos del resumen HRV.

    Mantiene la forma histórica de claves ``hrv_summary_*`` para que cualquier
    consumidor existente (tests, fallback SSR) siga funcionando sin cambios.
    """
    fallback = unavailable_text or DEFAULT_UNAVAILABLE_TEXT
    final_date = normalize_summary_text(diagnostics.get("final_last_fecha")) or None
    ai_ready = (
        diagnostics.get("ai_daily_brief_status") == "ok"
        and bool(diagnostics.get("ai_daily_brief_published"))
        and bool(diagnostics.get("ai_daily_brief_matches_final"))
    )

    ai_brief_text = None
    if ai_ready:
        ai_brief_text = render_ai_brief_text(
            diagnostics.get("ai_daily_brief_summary"),
            diagnostics.get("ai_daily_brief_detail"),
        )
    reason_text = normalize_summary_text(diagnostics.get("final_last_reason_text")) or None
    fallback_text = None
    if not ai_brief_text and not reason_text:
        fallback_text = fallback

    return {
        "hrv_summary_title_date": final_date,
        "hrv_summary_raw_text": (
            f"{fmt_number(diagnostics.get('final_last_rmssd_stable'))} ms "
            f"· HR {fmt_number(diagnostics.get('final_last_hr_today'))} lpm "
            f"· lnRMSSD bruto {fmt_number(diagnostics.get('final_last_lnrmssd_today'), 3)}"
        ),
        "hrv_summary_used_text": (
            f"{fmt_exp_from_log(diagnostics.get('final_last_lnrmssd_used'))} ms "
            f"· lnRMSSD usado {fmt_number(diagnostics.get('final_last_lnrmssd_used'), 3)}"
        ),
        "hrv_summary_base_text": (
            f"{fmt_exp_from_log(diagnostics.get('final_last_ln_base60'))} ms "
            f"· SWC_ln {fmt_number(diagnostics.get('final_last_swc_ln'), 3)}"
        ),
        "hrv_summary_gate_text": (
            f"{normalize_summary_text(diagnostics.get('final_last_gate_badge')) or 'N/A'} "
            f"· {normalize_summary_text(diagnostics.get('final_last_gate_razon_base60')) or 'N/A'}"
        ),
        "hrv_summary_ai_text": ai_brief_text,
        "hrv_summary_reason_text": reason_text,
        "hrv_summary_fallback_text": fallback_text,
        "hrv_summary_has_reason_text": bool(reason_text),
        "hrv_summary_reason_is_fallback": bool(fallback_text),
    }


def build_view(diagnostics: dict) -> dict:
    """Construye el viewmodel estructurado para la UI.

    La UI consume sólo este árbol; no debe conocer las claves crudas del
    pipeline. Si una nueva métrica entra en el dashboard, se añade aquí.

    Acepta diagnostics crudos o ya enriquecidos. Si los campos ``hrv_summary_*``
    están ausentes los compone internamente; si ya están presentes los reutiliza.
    """
    if "hrv_summary_raw_text" not in diagnostics:
        diagnostics = {**diagnostics, **compose_hrv_summary(diagnostics)}
    exists = bool(diagnostics.get("final_exists"))
    title_date = diagnostics.get("hrv_summary_title_date") or None
    ai_text = diagnostics.get("hrv_summary_ai_text") or None
    reason_text = diagnostics.get("hrv_summary_reason_text") or None
    fallback_text = diagnostics.get("hrv_summary_fallback_text") or None

    latest_rr_file = diagnostics.get("latest_rr_file") or None
    latest_rr_path = diagnostics.get("latest_rr_path") or None
    latest_rr_label = ""
    if latest_rr_file:
        rr_date = fmt_rr_date_label(latest_rr_file)
        latest_rr_label = f"{latest_rr_file} ({rr_date})" if rr_date else str(latest_rr_file)

    return {
        "version": VIEW_VERSION,
        "hrv_today": {
            "exists": exists,
            "date": title_date,
            "raw_text": diagnostics.get("hrv_summary_raw_text", "-"),
            "used_text": diagnostics.get("hrv_summary_used_text", "-"),
            "base_text": diagnostics.get("hrv_summary_base_text", "-"),
            "gate_text": diagnostics.get("hrv_summary_gate_text", "-"),
            "ai_text": ai_text,
            "reason_text": reason_text,
            "fallback_text": fallback_text,
        },
        "system": {
            "authorized": bool(diagnostics.get("authorized")),
            "latest_rr_file": latest_rr_file,
            "latest_rr_path": latest_rr_path,
            "latest_rr_label": latest_rr_label,
        },
    }
