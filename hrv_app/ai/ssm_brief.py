from __future__ import annotations

import hashlib
import json
import math
import re
from json import JSONDecodeError
from datetime import date, datetime
from pathlib import Path
from typing import Any

import pandas as pd
import requests

from hrv_app.ai.config import (
    AI_SSM_BRIEF_LATEST_PATH,
    FINAL_PATH,
    HRV_AI_API_KEY,
    HRV_AI_ENABLED,
    HRV_AI_LANGUAGE,
    HRV_AI_MAX_TOKENS,
    HRV_AI_MODEL,
    HRV_AI_PROVIDER,
    HRV_AI_SSM_ENABLED,
    HRV_AI_SSM_PROMPT_VERSION,
    HRV_AI_TEMPERATURE,
    HRV_AI_THINKING,
    HRV_AI_TIMEOUT_SEC,
    HRV_AI_TOP_P,
    SSM_SHADOW_PATH,
    ai_chat_completions_url,
    ai_ssm_brief_history_path,
)
from hrv_app.io_utils import write_json_atomic
from hrv_app.ssm_brief import SSM_INNOVATION_THRESHOLD, build_minimal_ssm_brief

# Prompt validado en research/reports/iu16_ssm_brief_eval/prompt.md (v4).
# Cambios aqui deben reflejarse tambien en ese artefacto de evaluacion.
PROMPT_TEXT = """Eres el redactor del brief SSM diario para un unico atleta.

Recibes un payload JSON ya calculado y validado por Python. Tu trabajo es
SOLO redactar; todos los juicios (que senal importa, su magnitud, su
relacion con el gate, si se publica o no) ya estan decididos en los campos
del payload. Tu no calculas nada.

## Reglas duras

1. El `summary` (1 frase) debe abrir con la senal indicada en
   `publication.trigger`. Si el trigger es `ssm_innovation`, habla de la
   sorpresa matinal. Si es `sleep_innovation`, habla de la senal nocturna.
   Si es `state_vs_rolling`, habla del estado filtrado frente al rolling.
   El summary debe integrar la relacion con el gate cuando sea relevante
   (especialmente en `discordant_or_noteworthy` y `adds_caution`), no
   limitarse solo al trigger aislado.
2. Usa `signals.morning_surprise.magnitude_label` para calibrar la
   intensidad del lenguaje: `small` = matiz leve, `moderate` = senal
   apreciable, `clear` = senal clara, `large` = senal muy marcada.
   Usa exactamente un nivel de intensidad por senal. No combines niveles
   (ej: no digas "clara y muy marcada" si el label es `clear`).
   Cuando otras senales materiales acompanan al trigger (ej: night_signal
   material, state_vs_rolling material), mencionalas brevemente en el
   summary o al inicio del detail para dar contexto.
3. Los campos marcados `authoritative: true` son verdad; no los
   reinterpretes ni los contradigas.
4. Los unicos numeros permitidos en tu salida son los que aparecen en
   campos `*_display` del payload (como `fatigue_penalty.pct_display`).
   No calcules, no conviertas, no inventes porcentajes ni comparaciones.
5. No contradigas `gate_anchor`. El gate y la accion son decisiones ya
   tomadas; tu brief es un comentario secundario, no una correccion.
   - Si `relation_to_gate` es `reinforces_gate`, el SSM refuerza la
     cautela del gate.
   - Si es `adds_caution`, el SSM anade prudencia a un gate verde.
   - Si es `discordant_or_noteworthy`, presentalo como matiz no resuelto,
     nunca como correccion del gate.
   - Si es `aligned`, el SSM acompana sin sustituir.
6. Si `night_signal.material` es true y `night_signal.sleep_quality`
   es `degraded`:
   - Si `night_signal.direction` es `above_expected`: menciona que la
     calidad degradada limita la lectura positiva y que no debe leerse
     como firme senal de recuperacion.
   - Si `night_signal.direction` es `below_expected`: menciona que la
     calidad degradada limita el peso de esta lectura.
   Si `night_signal.material` es true y `sleep_quality` no es `degraded`,
   mencionala brevemente indicando su direccion (ej: "la senal nocturna
   tambien apunta por debajo de lo esperado").
7. Si `fatigue_penalty.label` no es `minimal`, menciona la penalizacion
   de fatiga usando `fatigue_penalty.label_display` (texto en idioma de
   salida) y `fatigue_penalty.pct_display`. No copies el campo `label`
   (enum interno en ingles) al texto de salida.
8. Si `fatigue_penalty.trend_vs_yesterday` esta presente, mencionalo
   brevemente (ej: "la fatiga va a menos respecto a ayer").
9. Si el payload incluye `caveats`, incorporalos como cierre. Si un
   caveat menciona discordancia matinal/nocturna, presentala como dato
   observado sin intentar resolverla ni explicar su causa.
10. No diagnostiques enfermedad, sobreentrenamiento ni fatiga sistemica.
11. No inventes causalidad que el payload no soporte.
12. Maximo `expected_output.max_words` palabras en total (summary + detail).
13. Escribe en el idioma indicado en `expected_output.language`.

## Sobre senales no materiales

Si una senal tiene `material: false`, no la menciones como protagonista.
Puedes omitirla o mencionarla de pasada ("la senal nocturna no anade
informacion material hoy"). No le des peso narrativo a algo que Python
ya descarto. En particular, nunca uses expresiones como "con peso
material" o "significativo" para describir una senal cuyo campo
`material` sea `false`.

## Formato de salida

Solo JSON, sin texto fuera del JSON:

{
  "date": "YYYY-MM-DD",
  "summary": "una frase corta",
  "detail": "2-4 frases de contexto",
  "relation_to_gate_echo": "copiar el valor de gate_anchor.relation_to_gate",
  "trigger_echo": "copiar el valor de publication.trigger"
}

Los campos `*_echo` deben repetir exactamente los valores del payload.
Si no coinciden, la salida se descarta automaticamente.
"""

_FATIGUE_LABEL_ES = {
    "minimal": "leve",
    "moderate": "moderada",
    "high": "alta",
    "very_high": "muy alta",
    "unknown": "desconocida",
}


def _to_py(value: Any) -> Any:
    if pd.isna(value):
        return None
    if isinstance(value, (pd.Timestamp, datetime, date)):
        return value.isoformat()
    if isinstance(value, (bool, int, float, str)):
        return value
    if hasattr(value, "item"):
        try:
            return value.item()
        except Exception:
            return value
    return value


def _hash_json(payload: Any) -> str:
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _payload_for_hash(payload: dict[str, Any]) -> dict[str, Any]:
    payload_copy = json.loads(json.dumps(payload))
    meta = payload_copy.get("meta")
    if isinstance(meta, dict):
        meta.pop("generated_at", None)
    return payload_copy


def _innovation_magnitude_label(innovation: float) -> str:
    if not math.isfinite(innovation):
        return "unknown"
    abs_val = abs(innovation)
    if abs_val < SSM_INNOVATION_THRESHOLD:
        return "small"
    ratio = abs_val / SSM_INNOVATION_THRESHOLD
    if ratio < 1.5:
        return "moderate"
    if ratio < 2.5:
        return "clear"
    return "large"


def _fatigue_penalty_pct(baseline_state: float, fatigue_state: float) -> float | None:
    if not (math.isfinite(baseline_state) and math.isfinite(fatigue_state)):
        return None
    if baseline_state <= 0:
        return None
    state = baseline_state - fatigue_state
    rmssd_baseline = math.exp(baseline_state)
    rmssd_state = math.exp(state)
    return round((rmssd_baseline - rmssd_state) / rmssd_baseline * 100, 0)


def _fatigue_label(pct: float | None) -> str:
    if pct is None:
        return "unknown"
    if pct < 5:
        return "minimal"
    if pct < 15:
        return "moderate"
    if pct < 30:
        return "high"
    return "very_high"


def _fatigue_trend(fatigue_today: float, fatigue_yesterday: float | None) -> str | None:
    if fatigue_yesterday is None or not math.isfinite(fatigue_yesterday):
        return None
    if not math.isfinite(fatigue_today):
        return None
    diff = fatigue_today - fatigue_yesterday
    if abs(diff) < 0.02:
        return "stable"
    return "decreasing" if diff < 0 else "increasing"


def _determine_trigger(rule_hits: dict[str, bool]) -> str:
    if rule_hits.get("abs_ssm_innovation_ge_0_12"):
        return "ssm_innovation"
    if rule_hits.get("abs_sleep_innovation_ge_0_12_and_usable"):
        return "sleep_innovation"
    if rule_hits.get("state_delta_vs_rolling_ge_0_08"):
        return "state_vs_rolling"
    return "none"


def _sleep_quality_label(quality: str) -> str:
    q = str(quality or "").strip().lower()
    if q == "clean":
        return "clean"
    if q == "degraded":
        return "degraded"
    if q == "suppressed":
        return "suppressed"
    return "unknown"


def _build_payload(
    ssm_row: pd.Series,
    final_row: pd.Series,
    brief: dict[str, Any],
    fatigue_yesterday: float | None,
) -> dict[str, Any]:
    fecha = ssm_row["Fecha"]
    date_str = fecha.date().isoformat() if isinstance(fecha, pd.Timestamp) else str(fecha)

    gate_final = str(final_row.get("gate_final", ""))
    action_detail = str(final_row.get("Action_detail") or final_row.get("Action") or "").strip()

    ssm_innovation = float(ssm_row.get("ssm_innovation", float("nan")))
    sleep_innovation = float(ssm_row.get("sleep_innovation", float("nan")))
    baseline_state = float(ssm_row.get("ssm_baseline_state", float("nan")))
    fatigue_state = float(ssm_row.get("ssm_fatigue_state", float("nan")))
    state = float(ssm_row.get("ssm_recovery_state", float("nan")))
    rolling = float(ssm_row.get("control_rolling_hrv_7d", float("nan")))
    sleep_quality = str(ssm_row.get("sleep_input_quality", ""))

    state_delta = state - rolling if math.isfinite(state) and math.isfinite(rolling) else float("nan")

    rule_hits = brief["rule_hits"]
    trigger = _determine_trigger(rule_hits)
    relation_to_gate = brief["relation_to_gate"]

    morning_mag_label = _innovation_magnitude_label(ssm_innovation)
    morning_direction = "above_expected" if ssm_innovation > 0 else "below_expected" if ssm_innovation < 0 else "neutral"
    morning_ratio = f"{abs(ssm_innovation) / SSM_INNOVATION_THRESHOLD:.1f}x" if math.isfinite(ssm_innovation) else None
    morning_material = abs(ssm_innovation) >= SSM_INNOVATION_THRESHOLD if math.isfinite(ssm_innovation) else False

    night_material = (
        abs(sleep_innovation) >= SSM_INNOVATION_THRESHOLD
        and _sleep_quality_label(sleep_quality) != "suppressed"
    ) if math.isfinite(sleep_innovation) else False
    night_direction = "above_expected" if sleep_innovation > 0 else "below_expected" if sleep_innovation < 0 else "neutral"

    fatigue_pct = _fatigue_penalty_pct(baseline_state, fatigue_state)
    fatigue_pct_display = f"≈{int(fatigue_pct)}%" if fatigue_pct is not None else None
    fatigue_lbl = _fatigue_label(fatigue_pct)
    fatigue_trend = _fatigue_trend(fatigue_state, fatigue_yesterday)

    state_vs_rolling_direction = "above" if state_delta > 0 else "below" if state_delta < 0 else "equal"
    state_vs_rolling_material = abs(state_delta) >= 0.08 if math.isfinite(state_delta) else False

    caveats: list[str] = []
    if _to_py(final_row.get("veto_agudo")):
        caveats.append("Hay un veto agudo activo que refuerza la restricción.")
    if morning_material and night_material and (ssm_innovation > 0) != (sleep_innovation > 0):
        caveats.append("Existe discordancia entre la señal matinal y la nocturna.")

    payload: dict[str, Any] = {
        "meta": {
            "date": date_str,
            "generated_at": datetime.now().replace(microsecond=0).isoformat(),
            "source": "ssm_shadow",
        },
        "publication": {
            "published_by_python": brief["published"],
            "trigger": trigger,
            "rule_hits": rule_hits,
        },
        "gate_anchor": {
            "gate_final": gate_final,
            "action_detail": action_detail,
            "relation_to_gate": relation_to_gate,
        },
        "signals": {
            "morning_surprise": {
                "direction": morning_direction,
                "magnitude_label": morning_mag_label,
                "magnitude_vs_threshold_display": morning_ratio,
                "material": morning_material,
                "authoritative": True,
            },
            "state_vs_rolling": {
                "direction": state_vs_rolling_direction,
                "material": state_vs_rolling_material,
                "authoritative": True,
            },
            "night_signal": {
                "direction": night_direction if night_material else None,
                "material": night_material,
                "sleep_quality": _sleep_quality_label(sleep_quality),
                "authoritative": True,
            },
            "fatigue_penalty": {
                "label": fatigue_lbl,
                "label_display": _FATIGUE_LABEL_ES.get(fatigue_lbl, fatigue_lbl),
                "pct_display": fatigue_pct_display,
                "trend_vs_yesterday": fatigue_trend,
                "authoritative": True,
            },
        },
        "caveats": caveats,
        "expected_output": {
            "language": HRV_AI_LANGUAGE,
            "max_words": 150,
            "format": "json",
        },
    }

    payload["meta"]["payload_hash"] = _hash_json(_payload_for_hash(payload))
    return payload


_NUMBER_TOKEN_RE = re.compile(r"\d+(?:[.,]\d+)?\s*(?:%|x|X)?")


def _extract_number_tokens(text: str) -> set[str]:
    """Extrae porcentajes y ratios (`\\d+%`, `\\d+x`, `≈\\d+%`, etc.) del texto.

    Ignora numeros sueltos sin sufijo (fechas, anos, etc. no aparecen en briefs
    validos, pero si estan y no llevan `%`/`x` se ignoran para evitar falsos
    positivos con posibles fechas ISO parciales).
    """
    tokens: set[str] = set()
    for match in _NUMBER_TOKEN_RE.finditer(text or ""):
        raw = match.group(0)
        # Solo consideramos violacion los que llevan sufijo `%` o `x`; asi los
        # numeros sin sufijo (poco probables aqui) no bloquean el brief.
        stripped = raw.strip().lower()
        if not (stripped.endswith("%") or stripped.endswith("x")):
            continue
        # Normaliza: quita espacios internos, unifica coma decimal.
        normalized = stripped.replace(" ", "").replace(",", ".")
        tokens.add(normalized)
    return tokens


def _allowed_number_tokens(payload: dict[str, Any]) -> set[str]:
    """Union de todos los `*_display` numericos del payload, normalizados.

    Todo campo citable en el texto tiene sufijo `_display` por convencion
    (`pct_display`, `label_display`, `magnitude_vs_threshold_display`). Cada
    `_display` puede aparecer en el texto con o sin el prefijo `≈`, por eso
    el matching descarta ese caracter antes de comparar.
    """
    allowed: set[str] = set()
    for signal in payload.get("signals", {}).values():
        if not isinstance(signal, dict):
            continue
        for key, value in signal.items():
            if not isinstance(value, str) or not key.endswith("_display"):
                continue
            normalized = value.strip().lower().replace("≈", "").replace(" ", "").replace(",", ".")
            if normalized:
                allowed.add(normalized)
    return allowed


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
        + f"Escribe `summary` y `detail` en el idioma indicado por `expected_output.language` (`{language}`).\n"
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
    summary: str,
    detail: str,
    relation_to_gate: str | None,
    trigger: str | None,
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
        "prompt_version": HRV_AI_SSM_PROMPT_VERSION,
        "published": published,
        "summary": summary,
        "detail": detail,
        "relation_to_gate": relation_to_gate,
        "trigger": trigger,
        "source_mode": "ai_ssm_brief",
        "reason": reason,
        "validation_errors": validation_errors or [],
        "model_output_preview": model_output_preview or "",
        "created_at": datetime.now().replace(microsecond=0).isoformat(),
    }


def _write_sidecars(sidecar: dict[str, Any], date_str: str) -> None:
    write_json_atomic(sidecar, ai_ssm_brief_history_path(date_str))
    write_json_atomic(sidecar, AI_SSM_BRIEF_LATEST_PATH)


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
) -> tuple[dict[str, Any] | None, list[str]]:
    errors: list[str] = []
    for field in ("date", "summary", "detail", "relation_to_gate_echo", "trigger_echo"):
        if field not in model_output:
            errors.append(f"missing_field:{field}")

    if errors:
        return None, errors

    output_date = str(model_output.get("date", "")).strip()
    if output_date != date_str:
        errors.append("date_mismatch")

    relation_echo = str(model_output.get("relation_to_gate_echo", "")).strip()
    expected_relation = str(payload["gate_anchor"]["relation_to_gate"])
    if relation_echo != expected_relation:
        errors.append("relation_to_gate_echo_mismatch")

    trigger_echo = str(model_output.get("trigger_echo", "")).strip()
    expected_trigger = str(payload["publication"]["trigger"])
    if trigger_echo != expected_trigger:
        errors.append("trigger_echo_mismatch")

    summary = str(model_output.get("summary", "")).strip()
    detail = str(model_output.get("detail", "")).strip()
    if not summary:
        errors.append("summary_empty")
    if not detail:
        errors.append("detail_empty")

    max_words = int(payload.get("expected_output", {}).get("max_words") or 150)
    if _count_words(summary, detail) > int(max_words * 1.2):
        errors.append("max_words_exceeded")

    # Contrato numerico: cualquier porcentaje o ratio en el texto debe existir
    # como campo `*_display` del payload. Numeros inventados por el LLM (aunque
    # coincidentes con el gate) invalidan el brief.
    text_tokens = _extract_number_tokens(summary) | _extract_number_tokens(detail)
    allowed_tokens = _allowed_number_tokens(payload)
    unauthorized = text_tokens - allowed_tokens
    if unauthorized:
        errors.append("numeric_contract_violation")

    if errors:
        return None, errors

    return {
        "date": output_date,
        "summary": summary,
        "detail": detail,
        "relation_to_gate": relation_echo,
        "trigger": trigger_echo,
    }, []


def run_ai_ssm_brief_for_latest_date() -> dict[str, Any]:
    if not HRV_AI_ENABLED or not HRV_AI_SSM_ENABLED:
        return {"status": "disabled"}

    if not SSM_SHADOW_PATH.exists():
        return {"status": "missing_ssm_shadow"}

    ssm_df = pd.read_csv(SSM_SHADOW_PATH)
    if ssm_df.empty or "Fecha" not in ssm_df.columns:
        return {"status": "missing_ssm_shadow"}
    ssm_df["Fecha"] = pd.to_datetime(ssm_df["Fecha"], errors="coerce")
    ssm_df = ssm_df.sort_values("Fecha")
    valid = ssm_df[ssm_df["ssm_recovery_state"].notna()] if "ssm_recovery_state" in ssm_df.columns else ssm_df
    if valid.empty:
        return {"status": "missing_ssm_shadow"}
    ssm_row = valid.iloc[-1]
    latest_date = ssm_row["Fecha"].date()
    date_str = latest_date.isoformat()

    if not FINAL_PATH.exists():
        sidecar = _build_sidecar_base(
            status="error",
            date_str=date_str,
            payload_hash="",
            provider=HRV_AI_PROVIDER,
            model=HRV_AI_MODEL,
            published=False,
            summary="",
            detail="",
            relation_to_gate=None,
            trigger=None,
            reason="missing_final",
        )
        _write_sidecars(sidecar, date_str)
        return sidecar

    final_df = pd.read_csv(FINAL_PATH)
    if final_df.empty or "Fecha" not in final_df.columns:
        sidecar = _build_sidecar_base(
            status="error",
            date_str=date_str,
            payload_hash="",
            provider=HRV_AI_PROVIDER,
            model=HRV_AI_MODEL,
            published=False,
            summary="",
            detail="",
            relation_to_gate=None,
            trigger=None,
            reason="missing_final",
        )
        _write_sidecars(sidecar, date_str)
        return sidecar

    final_df["Fecha"] = pd.to_datetime(final_df["Fecha"], errors="coerce")
    final_slice = final_df[final_df["Fecha"].dt.date == latest_date]
    if final_slice.empty:
        sidecar = _build_sidecar_base(
            status="error",
            date_str=date_str,
            payload_hash="",
            provider=HRV_AI_PROVIDER,
            model=HRV_AI_MODEL,
            published=False,
            summary="",
            detail="",
            relation_to_gate=None,
            trigger=None,
            reason="missing_final_row",
        )
        _write_sidecars(sidecar, date_str)
        return sidecar
    final_row = final_slice.iloc[-1]

    brief = build_minimal_ssm_brief(ssm_row, final_row)
    if not brief["published"]:
        sidecar = _build_sidecar_base(
            status="not_applicable",
            date_str=date_str,
            payload_hash="",
            provider=HRV_AI_PROVIDER,
            model=HRV_AI_MODEL,
            published=False,
            summary="",
            detail="",
            relation_to_gate=brief.get("relation_to_gate"),
            trigger=None,
            reason=brief.get("reason") or "no_material_ssm_signal",
        )
        _write_sidecars(sidecar, date_str)
        return sidecar

    prior = valid[valid["Fecha"].dt.date < latest_date]
    fatigue_yesterday = None
    if not prior.empty:
        prior_val = prior.iloc[-1].get("ssm_fatigue_state")
        try:
            fatigue_yesterday = float(prior_val)
        except (TypeError, ValueError):
            fatigue_yesterday = None

    payload = _build_payload(ssm_row, final_row, brief, fatigue_yesterday)
    payload_hash = payload["meta"]["payload_hash"]

    existing = _read_json(ai_ssm_brief_history_path(date_str))
    if existing and existing.get("payload_hash") == payload_hash and existing.get("status") == "ok":
        write_json_atomic(existing, AI_SSM_BRIEF_LATEST_PATH)
        return {
            "status": "skipped_unchanged",
            "date": date_str,
            "payload_hash": payload_hash,
        }

    raw_text = ""
    response_preview = ""
    try:
        response_json = _call_model(payload)
        response_preview = _response_json_preview(response_json)
        raw_text = _extract_response_text(response_json)
        model_output = _parse_model_output(raw_text)
        validated, errors = _validate_output(model_output, payload=payload, date_str=date_str)
        if errors or validated is None:
            sidecar = _build_sidecar_base(
                status="validation_failed",
                date_str=date_str,
                payload_hash=payload_hash,
                provider=HRV_AI_PROVIDER,
                model=HRV_AI_MODEL,
                published=False,
                summary="",
                detail="",
                relation_to_gate=brief.get("relation_to_gate"),
                trigger=payload["publication"]["trigger"],
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
            summary=str(validated["summary"]),
            detail=str(validated["detail"]),
            relation_to_gate=str(validated["relation_to_gate"]),
            trigger=str(validated["trigger"]),
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
            summary="",
            detail="",
            relation_to_gate=brief.get("relation_to_gate"),
            trigger=payload["publication"]["trigger"],
            reason=str(exc),
            model_output_preview=_model_output_preview(raw_text) or response_preview,
        )
        _write_sidecars(sidecar, date_str)
        return sidecar
