from __future__ import annotations

import hashlib
import json
from json import JSONDecodeError
from datetime import date, datetime
from pathlib import Path
from typing import Any

import pandas as pd
import requests

from hrv_app.ai.config import (
    AI_DAILY_BRIEF_LATEST_PATH,
    FINAL_PATH,
    FINAL_REASON_ITEMS_PATH,
    HRV_AI_API_KEY,
    HRV_AI_DAILY_ENABLED,
    HRV_AI_ENABLED,
    HRV_AI_LANGUAGE,
    HRV_AI_MAX_TOKENS,
    HRV_AI_MODEL,
    HRV_AI_PROMPT_VERSION,
    HRV_AI_PROVIDER,
    HRV_AI_TEMPERATURE,
    HRV_AI_THINKING,
    HRV_AI_TIMEOUT_SEC,
    HRV_AI_TOP_P,
    SESSIONS_DAY_PATH,
    SLEEP_PATH,
    ai_chat_completions_url,
    ai_daily_brief_history_path,
)
from hrv_app.io_utils import write_json_atomic

PROMPT_TEXT = """You are a daily HRV renderer for one athlete.

Use only the JSON payload provided below. Do not use external memory or any
baseline text file. Do not contradict `gate_badge`, `gate_final`, `Action`,
`Action_detail`, or `reason_items`.

Rules:
- Follow the language and `max_words` specified in `expected_output`.
- If `reason_items` is non-empty, treat it as the primary explanation layer.
- When `reason_items` or `reason_items_meta.renderable_metrics` provide metric,
  value, and threshold fields, you may cite those values in the rendered text
  when they help the athlete gauge severity.
- If `reason_items` is empty, base the answer on `decision` and
  `morning_hrv`, and set `source_mode` to `reason_text_fallback`.
- Treat `classification` and `interpretation` fields as authoritative. Do not
  reclassify the day by re-reading raw numbers.
- Do not compute derived statistics, percentages, or comparisons from raw
  fields inside `morning_hrv`, `sleep_context`, or `recent_load_summary`.
- If `reason_items` contains `raw_today_rebound`, mention it as an incipient
  improvement signal that does not override the final gate or action.
- If multiple `reason_items` express the same practical caution, mention that
  caution once. Do not amplify tone by repeating overlapping items.
- Use `gate_badge` and `residual_tag` as narrative nuance only. They can add
  color to the explanation, but they never override `gate_final`.
- If `gate_final` is `VERDE`, `tone` must be `green`.
- If `gate_final` is `AMBAR`, `tone` must be `amber`.
- If `gate_final` is `ROJO`, `tone` must be `red`.
- If `gate_final` is `NO`, `tone` must be `not_applicable` and the brief should
  state that there is not enough baseline or signal quality to interpret the day.
- Mention reduced confidence when `quality_flag` is true.
- If `recovery_discordance_flag` is true, acknowledge the mixed signal between
  morning HRV and overnight recovery without resolving the contradiction. The
  gate still stands.
- Use `recovery_support_class` only as contextual wording support. Do not let
  it override the main decision.
- If `veto_agudo` is true, mention that there is an acute protective signal
  reinforcing the day's caution or restriction.
- If `sleep_context.sleep_duration_anomaly.flag` is true, treat that as a data
  anomaly note, not as proof of exceptional recovery.
- Do not diagnose illness, overtraining, or systemic fatigue.
- Do not invent causal links that the payload does not support.
- Do not add illustrative examples, likely causes, or factor lists unless they
  are explicitly present in the payload.
- Keep the answer operational.

Output JSON only with this schema:
{
  "date": "YYYY-MM-DD",
  "summary": "short text",
  "detail": "short text",
  "tone": "green|amber|red|not_applicable",
  "source_mode": "reason_items|reason_text_fallback"
}

Rewrite the cautions in clearer, more natural language. Do not add
information. Do not remove cautions. Preserve the decision, explain the main
constraint or tension, and state the practical implication in cleaner
language than a plain deterministic render.
"""


def _to_py(value: Any) -> Any:
    if pd.isna(value):
        return None
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, (bool, int, float, str)):
        return value
    if hasattr(value, "item"):
        try:
            return value.item()
        except Exception:
            return value
    return value


def _row_dict(row: pd.Series, fields: list[str]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for field in fields:
        if field in row.index:
            out[field] = _to_py(row[field])
    return out


def _hash_json(payload: Any) -> str:
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _normalize_text(value: Any) -> str:
    if value is None:
        return ""
    return " ".join(str(value).strip().lower().split())


def _reason_item_overlap_family(item: dict[str, Any]) -> str:
    item_type = str(item.get("type") or "").strip().lower()
    if item_type in {"recovery_support", "recovery_discordance", "nightly_discordance"}:
        return "recovery_signal"
    if item_type in {"sleep_fragmentation", "sleep_duration", "sleep_disruption", "sleep_short"}:
        return "sleep_caution"
    if item_type in {"acwr", "acute_load_72h_rel", "monotony", "strain", "work_7d", "green_load_caution", "green_load_convergence", "intensity_clustering"}:
        return "load_caution"
    if item_type in {"action_constraint"}:
        return "action_constraint"
    if item_type in {"data_quality"}:
        return "data_quality"
    return item_type or "unknown"


def _reason_items_overlap(reason_items: list[dict[str, Any]]) -> dict[str, Any]:
    messages: dict[str, list[str]] = {}
    families: dict[str, list[str]] = {}
    for item in reason_items:
        norm = _normalize_text(item.get("message"))
        item_type = str(item.get("type", "unknown"))
        if not norm:
            norm = item_type.lower()
        messages.setdefault(norm, []).append(item_type)
        family = _reason_item_overlap_family(item)
        families.setdefault(family, []).append(item_type)

    repeated = [
        {"message": message, "types": types}
        for message, types in messages.items()
        if len(types) > 1
    ]
    semantic_overlap = [
        {"family": family, "types": types}
        for family, types in families.items()
        if len(types) > 1 and len(set(types)) > 1
    ]
    return {
        "contains_message_overlap": bool(repeated),
        "contains_semantic_overlap": bool(semantic_overlap),
        "overlap_groups": repeated,
        "semantic_overlap_groups": semantic_overlap,
    }


def _renderable_reason_metrics(reason_items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    metrics: list[dict[str, Any]] = []
    for item in reason_items:
        if item.get("metric") is None or item.get("value") is None:
            continue
        metrics.append(
            {
                "type": _to_py(item.get("type")),
                "metric": _to_py(item.get("metric")),
                "value": _to_py(item.get("value")),
                "threshold": _to_py(item.get("threshold")),
                "severity": _to_py(item.get("severity")),
                "message": _to_py(item.get("message")),
            }
        )
    return metrics


def _sleep_duration_anomaly(sleep_row: pd.Series) -> dict[str, Any]:
    # Defensive data-quality flag for clearly implausible nights:
    # - 14h+ total sleep duration
    # - >20% above the athlete's own p90 duration
    # - 15h+ time-in-bed span
    # This is only prompt context for the IA renderer and does not alter FINAL.
    duration = sleep_row.get("polar_sleep_duration_min")
    span = sleep_row.get("polar_sleep_span_min")
    duration_p90 = sleep_row.get("sleep_dur_p90")

    triggered = False
    reasons: list[str] = []
    if pd.notna(duration) and float(duration) >= 840.0:
        triggered = True
        reasons.append("duration_ge_14h")
    if pd.notna(duration) and pd.notna(duration_p90) and float(duration) > float(duration_p90) * 1.2:
        triggered = True
        reasons.append("duration_gt_p90_x1.2")
    if pd.notna(span) and float(span) >= 900.0:
        triggered = True
        reasons.append("sleep_span_ge_15h")

    return {"flag": triggered, "reasons": reasons}


def _classify_morning(final_row: pd.Series) -> tuple[str, str]:
    gate = str(final_row.get("gate_final", "")).strip().upper()
    quality_flag = bool(final_row.get("quality_flag", False))

    if gate == "ROJO":
        return ("red", "HRV matinal cae frente a la base y sostiene un gate rojo.")
    if gate == "AMBAR":
        return ("amber", "HRV matinal util pero con prudencia operativa.")
    if gate == "NO":
        return ("not_applicable", "No hay base suficiente para interpretar el dia.")
    if quality_flag:
        return ("amber", "HRV matinal favorable, pero con confianza reducida por calidad.")
    return ("green", "HRV matinal estable y compatible con gate favorable.")


def _classify_sleep(sleep_row: pd.Series, reason_items: list[dict[str, Any]]) -> tuple[str, str]:
    score = sleep_row.get("polar_sleep_score")
    duration = sleep_row.get("polar_sleep_duration_min")
    interruptions = sleep_row.get("polar_interruptions_long")
    threshold = sleep_row.get("sleep_int_p90")

    sleep_item_types = {
        "sleep_fragmentation",
        "sleep_duration",
        "sleep_disruption",
        "sleep_short",
    }
    has_sleep_caution = any(str(item.get("type", "")) in sleep_item_types for item in reason_items)

    if pd.notna(score) and float(score) < 65.0:
        return ("red", "Sueno claramente pobre frente a tu historico.")
    if pd.notna(duration) and pd.notna(sleep_row.get("sleep_dur_p10")) and float(duration) < float(sleep_row.get("sleep_dur_p10")):
        return ("amber", "Sueno mas corto de lo habitual, con cautela contextual.")
    if pd.notna(interruptions) and pd.notna(threshold) and float(interruptions) > float(threshold):
        return ("amber", "Sueno mas fragmentado de lo habitual, con cautela contextual.")
    if has_sleep_caution:
        return ("amber", "Sueno aporta una cautela contextual o de soporte.")
    return ("green", "Sueno no introduce una cautela material en el dia.")


def _load_reason_items_lookup(path: Path) -> dict[str, list[dict[str, Any]]]:
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        return {}
    items_by_date = payload.get("items_by_date")
    if not isinstance(items_by_date, dict):
        return {}
    return {
        str(key): value
        for key, value in items_by_date.items()
        if isinstance(value, list)
    }


def _build_payload(
    final_row: pd.Series,
    sleep_row: pd.Series,
    sessions_row: pd.Series | None,
    reason_items: list[dict[str, Any]],
) -> dict[str, Any]:
    morning_classification, morning_interpretation = _classify_morning(final_row)
    sleep_classification, sleep_interpretation = _classify_sleep(sleep_row, reason_items)
    reason_items_overlap = _reason_items_overlap(reason_items)
    renderable_reason_metrics = _renderable_reason_metrics(reason_items)
    sleep_duration_anomaly = _sleep_duration_anomaly(sleep_row)

    load_context_date = _to_py(sessions_row["Fecha"]) if sessions_row is not None else None
    load_lag_days = None
    if sessions_row is not None:
        load_lag_days = (
            pd.to_datetime(final_row["Fecha"]).date() - pd.to_datetime(sessions_row["Fecha"]).date()
        ).days

    source_lag_notes = [
        "Load context uses the latest available sessions_day row at or before the target date.",
    ]
    if load_lag_days is not None and load_lag_days > 0:
        source_lag_notes.append(f"Load context is lagged by {load_lag_days} day(s) relative to the target date.")

    return {
        "meta": {
            "date": _to_py(final_row["Fecha"]),
            "generated_at": datetime.now().replace(microsecond=0).isoformat(),
            "source_lag_notes": source_lag_notes,
            "data_sources": [
                str(FINAL_PATH),
                str(SLEEP_PATH),
                str(SESSIONS_DAY_PATH),
                str(FINAL_REASON_ITEMS_PATH),
            ],
        },
        "decision": _row_dict(
            final_row,
            [
                "gate_badge",
                "gate_final",
                "Action",
                "Action_detail",
                "quality_flag",
                "veto_agudo",
                "baseline60_degraded",
                "recovery_context_quality",
                "recovery_support_class",
                "recovery_discordance_flag",
            ],
        ),
        "reason_items": reason_items,
        "reason_items_meta": {
            **reason_items_overlap,
            "renderable_metrics": renderable_reason_metrics,
            "rendering_note": "If multiple reason_items express the same practical caution, mention it once.",
            "numeric_rendering_policy": (
                "You may cite metric values and thresholds already present in reason_items_meta.renderable_metrics "
                "or reason_items. Do not compute derived statistics from morning_hrv, sleep_context, or "
                "recent_load_summary raw fields."
            ),
        },
        "morning_hrv": {
            **_row_dict(
                final_row,
                [
                    "Calidad",
                    "HRV_Stability",
                    "Artifact_pct",
                    "Tiempo_Estabilizacion",
                    "HR_today",
                    "RMSSD_stable",
                    "lnRMSSD_today",
                    "lnRMSSD_used",
                    "HR_used",
                    "gate_raw_today",
                    "gate_raw_reason",
                    "ln_base60",
                    "HR_base60",
                    "d_ln",
                    "d_HR",
                    "residual_tag",
                    "tail_mismatch_pct",
                ],
            ),
            "classification_authoritative": True,
            "classification": morning_classification,
            "interpretation": morning_interpretation,
        },
        "sleep_context": {
            **_row_dict(
                sleep_row,
                [
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
                    "sleep_dur_p10",
                    "sleep_dur_p90",
                    "sleep_int_p90",
                ],
            ),
            "classification_authoritative": True,
            "classification": sleep_classification,
            "interpretation": sleep_interpretation,
            "sleep_duration_anomaly": sleep_duration_anomaly,
        },
        "recent_load_summary": {
            **_row_dict(
                sessions_row if sessions_row is not None else pd.Series(dtype=object),
                [
                    "Fecha",
                    "load_day",
                    "load_3d",
                    "load_7d",
                    "load_14d",
                    "acwr_simple_prev",
                    "acute_load_72h_rel",
                    "monotony_7d_prev",
                    "strain_7d_prev",
                    "intensity_clustering_flag",
                    "load_ctx_ready",
                ],
            ),
            "as_of_date": load_context_date,
        },
        "interpretation_contract": {
            "hard_rules": [
                "Do not contradict gate_badge, gate_final, Action, or Action_detail.",
                "Treat reason_items as the primary explanation layer for the day.",
                "If reason_items is empty, use decision and morning_hrv as primary context and set source_mode=reason_text_fallback.",
                "Treat classification and interpretation fields as authoritative; do not reclassify from raw numbers.",
                "If multiple reason_items overlap semantically, collapse them into one caution in the rendered text.",
                "You may cite metric values and thresholds already present in reason_items or reason_items_meta.renderable_metrics.",
                "Do not compute derived statistics from morning_hrv, sleep_context, or recent_load_summary raw fields.",
                "Do not diagnose illness, overtraining, or systemic fatigue.",
            ]
        },
        "expected_output": {
            "language": HRV_AI_LANGUAGE,
            "format": "json",
            "max_words": 220,
        },
    }


def _expected_tone(gate_final: str) -> str:
    gate = str(gate_final or "").strip().upper()
    if gate == "VERDE":
        return "green"
    if gate == "AMBAR":
        return "amber"
    if gate == "ROJO":
        return "red"
    return "not_applicable"


def _payload_for_hash(payload: dict[str, Any]) -> dict[str, Any]:
    payload_copy = json.loads(json.dumps(payload))
    meta = payload_copy.get("meta")
    if isinstance(meta, dict):
        meta.pop("generated_at", None)
    return payload_copy


def _count_words(*parts: str) -> int:
    text = " ".join(part.strip() for part in parts if part).strip()
    if not text:
        return 0
    return len(text.split())


def _read_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    if not isinstance(payload, dict):
        return None
    return payload


def _extract_response_text(response_json: dict[str, Any]) -> str:
    choices = response_json.get("choices")
    if isinstance(choices, list) and choices:
        message = choices[0].get("message", {})
        content = message.get("content")
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts: list[str] = []
            for item in content:
                if isinstance(item, dict) and item.get("type") == "text":
                    parts.append(str(item.get("text", "")))
            return "\n".join(parts).strip()
    output_text = response_json.get("output_text")
    if isinstance(output_text, str):
        return output_text
    raise ValueError("response_without_text_content")


def _strip_code_fences(text: str) -> str:
    stripped = text.strip()
    if stripped.startswith("```"):
        lines = stripped.splitlines()
        if lines:
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        stripped = "\n".join(lines).strip()
    return stripped


def _parse_model_output(raw_text: str) -> dict[str, Any]:
    stripped = _strip_code_fences(raw_text)
    if not stripped:
        raise ValueError("empty_model_output")
    try:
        payload = json.loads(stripped)
    except json.JSONDecodeError:
        start = stripped.find("{")
        end = stripped.rfind("}")
        if start == -1 or end == -1 or end <= start:
            raise
        payload = json.loads(stripped[start : end + 1])
    if not isinstance(payload, dict):
        raise ValueError("model_output_not_object")
    return payload


def _model_output_preview(raw_text: str, limit: int = 1000) -> str:
    preview = " ".join(str(raw_text or "").split()).strip()
    if len(preview) <= limit:
        return preview
    return preview[:limit] + "...<truncated>"


def _http_error_preview(response: requests.Response) -> str:
    try:
        return _model_output_preview(response.text)
    except Exception:
        return ""


def _response_json_preview(response_json: dict[str, Any]) -> str:
    try:
        return _model_output_preview(json.dumps(response_json, ensure_ascii=False))
    except Exception:
        return ""


def _prompt_text(payload: dict[str, Any]) -> str:
    language = str(payload.get("expected_output", {}).get("language") or "es").strip() or "es"
    return (
        PROMPT_TEXT
        + "\n"
        + f"- Write `summary` and `detail` in the language specified by `expected_output.language` (`{language}`).\n"
    )


def _should_send_thinking_param() -> bool:
    thinking = str(HRV_AI_THINKING or "").strip().lower()
    if thinking in {"", "0", "false", "no", "off"}:
        return False
    if thinking == "disabled":
        provider = str(HRV_AI_PROVIDER or "").strip().lower()
        model = str(HRV_AI_MODEL or "").strip().lower()
        return provider in {"moonshot", "kimi"} or "kimi" in model
    return True


def _build_sidecar_base(
    *,
    status: str,
    date_str: str,
    payload_hash: str,
    provider: str,
    model: str,
    published: bool,
    tone: str,
    source_mode: str,
    summary: str,
    detail: str,
    reason: str | None,
    validation_errors: list[str] | None = None,
    model_output_preview: str | None = None,
) -> dict[str, Any]:
    return {
        "status": status,
        "date": date_str,
        "payload_hash": payload_hash,
        "provider": provider,
        "model": model,
        "prompt_version": HRV_AI_PROMPT_VERSION,
        "published": published,
        "summary": summary,
        "detail": detail,
        "tone": tone,
        "source_mode": source_mode,
        "reason": reason,
        "validation_errors": validation_errors or [],
        "model_output_preview": model_output_preview or "",
        "created_at": datetime.now().replace(microsecond=0).isoformat(),
    }


def _write_sidecars(sidecar: dict[str, Any], date_str: str) -> None:
    write_json_atomic(sidecar, ai_daily_brief_history_path(date_str))
    write_json_atomic(sidecar, AI_DAILY_BRIEF_LATEST_PATH)


def _build_not_applicable_sidecar(date_str: str, payload_hash: str, reason_items: list[dict[str, Any]]) -> dict[str, Any]:
    return _build_sidecar_base(
        status="not_applicable",
        date_str=date_str,
        payload_hash=payload_hash,
        provider=HRV_AI_PROVIDER,
        model=HRV_AI_MODEL,
        published=False,
        tone="not_applicable",
        source_mode="reason_items" if reason_items else "reason_text_fallback",
        summary="",
        detail="",
        reason="gate_NO",
    )


def _call_model(payload: dict[str, Any]) -> dict[str, Any]:
    url = ai_chat_completions_url()
    if not HRV_AI_API_KEY:
        raise RuntimeError("missing_ai_api_key")
    if not url:
        raise RuntimeError("missing_ai_base_url")
    if not HRV_AI_MODEL:
        raise RuntimeError("missing_ai_model")

    request_payload: dict[str, Any] = {
        "model": HRV_AI_MODEL,
        "temperature": HRV_AI_TEMPERATURE,
        "max_tokens": HRV_AI_MAX_TOKENS,
        "messages": [
            {"role": "system", "content": _prompt_text(payload)},
            {"role": "user", "content": json.dumps(payload, ensure_ascii=False, indent=2)},
        ],
    }
    if HRV_AI_TOP_P is not None:
        request_payload["top_p"] = HRV_AI_TOP_P
    if _should_send_thinking_param():
        request_payload["thinking"] = {"type": HRV_AI_THINKING}

    response = requests.post(
        url,
        headers={
            "Authorization": f"Bearer {HRV_AI_API_KEY}",
            "Content-Type": "application/json",
        },
        json=request_payload,
        timeout=HRV_AI_TIMEOUT_SEC,
    )
    try:
        response.raise_for_status()
    except requests.HTTPError as exc:
        preview = _http_error_preview(response)
        if preview:
            raise requests.HTTPError(f"{exc} | response_preview={preview}", response=response) from exc
        raise
    return response.json()


def _validate_output(
    model_output: dict[str, Any],
    *,
    payload: dict[str, Any],
    date_str: str,
    gate_final: str,
    reason_items: list[dict[str, Any]],
) -> tuple[dict[str, Any] | None, list[str]]:
    errors: list[str] = []
    for field in ("date", "summary", "detail", "tone", "source_mode"):
        if field not in model_output:
            errors.append(f"missing_field:{field}")

    if errors:
        return None, errors

    output_date = str(model_output.get("date", "")).strip()
    if output_date != date_str:
        errors.append("date_mismatch")

    tone = str(model_output.get("tone", "")).strip()
    expected_tone = _expected_tone(gate_final)
    if tone != expected_tone:
        errors.append("tone_mismatch")

    source_mode = str(model_output.get("source_mode", "")).strip()
    expected_source_mode = "reason_items" if reason_items else "reason_text_fallback"
    if source_mode != expected_source_mode:
        errors.append("source_mode_mismatch")

    summary = str(model_output.get("summary", "")).strip()
    detail = str(model_output.get("detail", "")).strip()
    if not summary:
        errors.append("summary_empty")
    if not detail:
        errors.append("detail_empty")

    max_words = int(payload.get("expected_output", {}).get("max_words") or 220)
    if _count_words(summary, detail) > int(max_words * 1.2):
        errors.append("max_words_exceeded")

    if errors:
        return None, errors

    return {
        "date": output_date,
        "summary": summary,
        "detail": detail,
        "tone": tone,
        "source_mode": source_mode,
    }, []


def run_ai_daily_brief_for_latest_date() -> dict[str, Any]:
    if not HRV_AI_ENABLED or not HRV_AI_DAILY_ENABLED:
        return {"status": "disabled"}

    if not FINAL_PATH.exists():
        return {"status": "missing_final"}

    final_df = pd.read_csv(FINAL_PATH)
    if final_df.empty or "Fecha" not in final_df.columns:
        return {"status": "missing_final"}
    final_df["Fecha"] = pd.to_datetime(final_df["Fecha"]).dt.date
    latest_date = final_df["Fecha"].max()
    final_row = final_df[final_df["Fecha"] == latest_date].iloc[-1]
    date_str = latest_date.isoformat()

    if not SLEEP_PATH.exists():
        sidecar = _build_sidecar_base(
            status="error",
            date_str=date_str,
            payload_hash="",
            provider=HRV_AI_PROVIDER,
            model=HRV_AI_MODEL,
            published=False,
            tone="not_applicable",
            source_mode="reason_text_fallback",
            summary="",
            detail="",
            reason="missing_sleep",
        )
        _write_sidecars(sidecar, date_str)
        return sidecar

    sleep_df = pd.read_csv(SLEEP_PATH)
    sleep_df["Fecha"] = pd.to_datetime(sleep_df["Fecha"]).dt.date
    sleep_slice = sleep_df[sleep_df["Fecha"] <= latest_date].sort_values("Fecha")
    if sleep_slice.empty:
        sidecar = _build_sidecar_base(
            status="error",
            date_str=date_str,
            payload_hash="",
            provider=HRV_AI_PROVIDER,
            model=HRV_AI_MODEL,
            published=False,
            tone="not_applicable",
            source_mode="reason_text_fallback",
            summary="",
            detail="",
            reason="missing_sleep_row",
        )
        _write_sidecars(sidecar, date_str)
        return sidecar
    sleep_row = sleep_slice.iloc[-1]

    sessions_row = None
    if SESSIONS_DAY_PATH.exists():
        sessions_df = pd.read_csv(SESSIONS_DAY_PATH)
        if not sessions_df.empty and "Fecha" in sessions_df.columns:
            sessions_df["Fecha"] = pd.to_datetime(sessions_df["Fecha"]).dt.date
            sessions_slice = sessions_df[sessions_df["Fecha"] <= latest_date].sort_values("Fecha")
            if not sessions_slice.empty:
                sessions_row = sessions_slice.iloc[-1]

    reasons_lookup = _load_reason_items_lookup(FINAL_REASON_ITEMS_PATH)
    reason_items = reasons_lookup.get(date_str, [])
    payload = _build_payload(final_row, sleep_row, sessions_row, reason_items)
    payload_hash = _hash_json(_payload_for_hash(payload))

    existing = _read_json(ai_daily_brief_history_path(date_str))
    if existing and existing.get("payload_hash") == payload_hash and existing.get("status") == "ok":
        write_json_atomic(existing, AI_DAILY_BRIEF_LATEST_PATH)
        return {
            "status": "skipped_unchanged",
            "date": date_str,
            "payload_hash": payload_hash,
        }

    gate_final = str(final_row.get("gate_final", "")).strip().upper()
    if gate_final == "NO":
        sidecar = _build_not_applicable_sidecar(date_str, payload_hash, reason_items)
        _write_sidecars(sidecar, date_str)
        return sidecar

    raw_text = ""
    response_preview = ""
    try:
        response_json = _call_model(payload)
        response_preview = _response_json_preview(response_json)
        raw_text = _extract_response_text(response_json)
        model_output = _parse_model_output(raw_text)
        validated, errors = _validate_output(
            model_output,
            payload=payload,
            date_str=date_str,
            gate_final=gate_final,
            reason_items=reason_items,
        )
        if errors or validated is None:
            sidecar = _build_sidecar_base(
                status="validation_failed",
                date_str=date_str,
                payload_hash=payload_hash,
                provider=HRV_AI_PROVIDER,
                model=HRV_AI_MODEL,
                published=False,
                tone="not_applicable",
                source_mode="reason_items" if reason_items else "reason_text_fallback",
                summary="",
                detail="",
                reason="validation_failed",
                validation_errors=errors,
            )
            _write_sidecars(sidecar, date_str)
            return sidecar

        sidecar = _build_sidecar_base(
            status="ok",
            date_str=date_str,
            payload_hash=payload_hash,
            provider=HRV_AI_PROVIDER,
            model=HRV_AI_MODEL,
            published=True,
            tone=str(validated["tone"]),
            source_mode=str(validated["source_mode"]),
            summary=str(validated["summary"]),
            detail=str(validated["detail"]),
            reason=None,
        )
        _write_sidecars(sidecar, date_str)
        return sidecar
    except Exception as exc:
        if not raw_text and isinstance(exc, JSONDecodeError):
            raw_text = ""
        sidecar = _build_sidecar_base(
            status="error",
            date_str=date_str,
            payload_hash=payload_hash,
            provider=HRV_AI_PROVIDER,
            model=HRV_AI_MODEL,
            published=False,
            tone="not_applicable",
            source_mode="reason_items" if reason_items else "reason_text_fallback",
            summary="",
            detail="",
            reason=str(exc),
            model_output_preview=_model_output_preview(raw_text) or response_preview,
        )
        _write_sidecars(sidecar, date_str)
        return sidecar
