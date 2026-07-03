from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
from typing import Any

import math
import pandas as pd


SSM_INNOVATION_THRESHOLD = 0.12
SSM_DISCREPANCY_THRESHOLD = 0.08


def _is_missing(value: Any) -> bool:
    try:
        return bool(pd.isna(value))
    except (TypeError, ValueError):
        return value is None


def _to_float(value: Any) -> float:
    if _is_missing(value):
        return float("nan")
    try:
        return float(value)
    except (TypeError, ValueError):
        return float("nan")


def _to_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if _is_missing(value):
        return False
    return str(value).strip().lower() in {"1", "true", "yes", "si", "sí"}


def _to_date_text(value: Any) -> str | None:
    if _is_missing(value):
        return None
    if isinstance(value, pd.Timestamp):
        return value.date().isoformat()
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    text = str(value).strip()
    if not text:
        return None
    try:
        return pd.to_datetime(text).date().isoformat()
    except (TypeError, ValueError):
        return text


def _gate(final_row: pd.Series | None) -> str:
    if final_row is None:
        return ""
    return str(final_row.get("gate_final") or "").strip().upper()


def _action(final_row: pd.Series | None) -> str:
    if final_row is None:
        return ""
    return str(final_row.get("Action_detail") or final_row.get("Action") or "").strip()


def _empty_sidecar(
    *,
    status: str,
    date_str: str | None,
    reason: str,
    relation_to_gate: str = "no_extra_signal",
) -> dict[str, Any]:
    return {
        "status": status,
        "date": date_str,
        "published": False,
        "summary": "",
        "detail": "",
        "relation_to_gate": relation_to_gate,
        "reason": reason,
        "source_mode": "deterministic_ssm_v1",
        "rule_hits": {},
    }


def _relation_to_gate(
    *,
    gate_final: str,
    ssm_innovation: float,
    sleep_innovation: float,
    sleep_usable: bool,
    state_delta: float,
) -> str:
    has_negative_caution = (
        (math.isfinite(ssm_innovation) and ssm_innovation <= -SSM_INNOVATION_THRESHOLD)
        or (
            sleep_usable
            and math.isfinite(sleep_innovation)
            and sleep_innovation <= -SSM_INNOVATION_THRESHOLD
        )
    )
    has_positive_signal = (
        (math.isfinite(ssm_innovation) and ssm_innovation >= SSM_INNOVATION_THRESHOLD)
        or (
            sleep_usable
            and math.isfinite(sleep_innovation)
            and sleep_innovation >= SSM_INNOVATION_THRESHOLD
        )
    )
    state_high_vs_rolling = math.isfinite(state_delta) and state_delta >= SSM_DISCREPANCY_THRESHOLD
    state_low_vs_rolling = math.isfinite(state_delta) and state_delta <= -SSM_DISCREPANCY_THRESHOLD

    if has_negative_caution or state_low_vs_rolling:
        return "adds_caution" if gate_final == "VERDE" else "reinforces_gate"
    if has_positive_signal or state_high_vs_rolling:
        return "aligned" if gate_final == "VERDE" else "discordant_or_noteworthy"
    return "no_extra_signal"


def _main_observation(
    *,
    relation_to_gate: str,
    ssm_innovation: float,
    sleep_innovation: float,
    sleep_usable: bool,
    state_delta: float,
) -> str:
    if math.isfinite(ssm_innovation) and abs(ssm_innovation) >= SSM_INNOVATION_THRESHOLD:
        magnitude = _innovation_magnitude_text(ssm_innovation)
        if ssm_innovation < 0:
            return f"SSM shadow: la observación matinal quedó {magnitude} por debajo de lo que esperaba el modelo."
        return f"SSM shadow: la observación matinal quedó {magnitude} por encima de lo que esperaba el modelo."

    if sleep_usable and math.isfinite(sleep_innovation) and abs(sleep_innovation) >= SSM_INNOVATION_THRESHOLD:
        if sleep_innovation < 0:
            return "SSM shadow: la observación nocturna queda por debajo de lo esperado y añade prudencia experimental."
        return "SSM shadow: la observación nocturna queda por encima de lo esperado, pero no cambia la lectura principal."

    if math.isfinite(state_delta) and abs(state_delta) >= SSM_DISCREPANCY_THRESHOLD:
        if state_delta < 0:
            return "SSM shadow: el estado filtrado queda por debajo de tu rolling reciente."
        return "SSM shadow: el estado filtrado queda por encima de tu rolling reciente."

    if math.isfinite(ssm_innovation):
        if math.isfinite(state_delta) and abs(state_delta) < SSM_DISCREPANCY_THRESHOLD:
            return "SSM shadow: lectura compatible con continuidad reciente, no con cambio claro de estado."
        return "SSM shadow: hoy no hay una sorpresa matinal relevante."

    if relation_to_gate == "reinforces_gate":
        return "SSM shadow: acompaña la cautela marcada por el gate."
    if relation_to_gate == "adds_caution":
        return "SSM shadow: añade una cautela experimental al gate de hoy."
    if relation_to_gate == "discordant_or_noteworthy":
        return "SSM shadow: añade un matiz experimental que conviene leer aparte del gate."
    return "SSM shadow: no añade una señal material por encima del gate."


def _quality_text(value: str) -> str:
    value = str(value or "").strip().lower()
    if value == "clean":
        return "limpia"
    if value == "degraded":
        return "degradada"
    if value == "suppressed":
        return "suprimida"
    return value or "no clasificada"


def _innovation_magnitude_text(value: float) -> str:
    abs_value = abs(value)
    if abs_value >= 0.30:
        return "muy claramente"
    if abs_value >= 0.20:
        return "claramente"
    return "algo"


def _innovation_magnitude_label(value: float) -> str:
    abs_value = abs(value)
    if abs_value >= 0.30:
        return "muy clara"
    if abs_value >= 0.20:
        return "clara"
    return "material"


def _fatigue_component_text(fatigue_state: float) -> str:
    if not math.isfinite(fatigue_state):
        return ""
    if fatigue_state > 0.02:
        discount_pct = (1.0 - math.exp(-fatigue_state)) * 100.0
        if discount_pct >= 30:
            level = "muy alta"
        elif discount_pct >= 15:
            level = "alta"
        elif discount_pct >= 5:
            level = "moderada"
        else:
            level = "leve"
        return f"La penalización aguda de fatiga del modelo es {level} (≈{discount_pct:.0f}%)."
    if fatigue_state < -0.02:
        boost_pct = (math.exp(-fatigue_state) - 1.0) * 100.0
        return f"El componente agudo no penaliza la lectura; la compensa en ≈+{boost_pct:.0f}% dentro del modelo."
    return "El componente agudo de fatiga es prácticamente neutro dentro del modelo."


def _detail_text(
    *,
    gate_final: str,
    action_detail: str,
    relation_to_gate: str,
    state: float,
    rolling: float,
    baseline_state: float,
    fatigue_state: float,
    ssm_innovation: float,
    sleep_innovation: float,
    sleep_quality: str,
) -> str:
    gate_clause = f"El gate sigue en {gate_final}" if gate_final else "El gate operativo no cambia"
    action_clause = f" y la acción continúa siendo {action_detail}" if action_detail else ""

    parts: list[str] = []
    if math.isfinite(rolling) and math.isfinite(state):
        delta = state - rolling
        if abs(delta) < SSM_DISCREPANCY_THRESHOLD:
            parts.append(
                "El estado filtrado queda cerca de tu rolling HRV de 7 días, "
                "así que el modelo lo lee como continuidad reciente, no como cambio claro."
            )
        elif delta > 0:
            parts.append("El estado filtrado queda por encima de tu rolling HRV reciente.")
        else:
            parts.append("El estado filtrado queda por debajo de tu rolling HRV reciente.")

    if math.isfinite(ssm_innovation) and abs(ssm_innovation) >= SSM_INNOVATION_THRESHOLD:
        direction = "por encima" if ssm_innovation > 0 else "por debajo"
        magnitude = _innovation_magnitude_label(ssm_innovation)
        parts.append(
            f"La sorpresa matinal del modelo es {magnitude}: el dato observado quedó {direction} "
            "de lo que esperaba antes de ver la medición de hoy."
        )
    elif math.isfinite(ssm_innovation):
        parts.append("La sorpresa matinal del modelo es pequeña: el dato observado encaja bastante con lo esperado.")

    if math.isfinite(baseline_state) and math.isfinite(fatigue_state):
        fatigue_text = _fatigue_component_text(fatigue_state)
        if fatigue_text:
            parts.append(f"{fatigue_text} Ese desglose explica el estado shadow, pero no cambia la acción del día.")

    sleep_quality_text = _quality_text(sleep_quality)
    if math.isfinite(sleep_innovation) and abs(sleep_innovation) >= SSM_INNOVATION_THRESHOLD:
        if sleep_innovation > 0:
            parts.append(
                f"La observación nocturna que entra al SSM queda por encima de lo esperado, "
                f"pero su calidad está {sleep_quality_text}; no debe leerse como señal global de buena recuperación."
            )
        else:
            parts.append(
                f"La observación nocturna que entra al SSM queda por debajo de lo esperado "
                f"y su calidad está {sleep_quality_text}, así que añade prudencia como capa shadow."
            )

    if relation_to_gate == "reinforces_gate":
        parts.append(f"{gate_clause}{action_clause}; el SSM solo refuerza esa cautela como capa shadow.")
    if relation_to_gate == "adds_caution":
        parts.append(f"{gate_clause}{action_clause}; usa este matiz solo como prudencia adicional, no como decisión nueva.")
    if relation_to_gate == "discordant_or_noteworthy":
        parts.append(f"{gate_clause}{action_clause}; trata el SSM como contexto secundario, no como contradicción resuelta.")
    if relation_to_gate == "aligned":
        parts.append(f"{gate_clause}{action_clause}; el SSM acompaña la lectura, sin sustituirla.")
    if relation_to_gate == "no_extra_signal":
        parts.append(f"{gate_clause}{action_clause}; el SSM no cambia la lectura principal.")

    return " ".join(parts)


def build_minimal_ssm_brief(ssm_row: pd.Series, final_row: pd.Series | None = None) -> dict[str, Any]:
    """Construye el brief determinista mínimo del SSM shadow.

    Esta función no interpreta datos crudos desde cero: solo decide si la salida
    shadow tiene una señal material y, si la tiene, la expresa como matiz
    secundario compatible con el gate.
    """
    date_str = _to_date_text(ssm_row.get("Fecha"))
    if not _to_bool(ssm_row.get("ssm_warmup_complete")):
        return _empty_sidecar(status="not_applicable", date_str=date_str, reason="warmup_incomplete")

    state = _to_float(ssm_row.get("ssm_recovery_state"))
    if not math.isfinite(state):
        return _empty_sidecar(status="not_applicable", date_str=date_str, reason="missing_ssm_state")

    gate_final = _gate(final_row)
    action_detail = _action(final_row)
    ssm_innovation = _to_float(ssm_row.get("ssm_innovation"))
    sleep_innovation = _to_float(ssm_row.get("sleep_innovation"))
    baseline_state = _to_float(ssm_row.get("ssm_baseline_state"))
    fatigue_state = _to_float(ssm_row.get("ssm_fatigue_state"))
    sleep_quality = str(ssm_row.get("sleep_input_quality") or "").strip().lower()
    sleep_usable = sleep_quality != "suppressed"
    rolling = _to_float(ssm_row.get("control_rolling_hrv_7d"))
    state_delta = state - rolling if math.isfinite(rolling) else float("nan")

    rule_hits = {
        "abs_ssm_innovation_ge_0_12": bool(
            math.isfinite(ssm_innovation) and abs(ssm_innovation) >= SSM_INNOVATION_THRESHOLD
        ),
        "abs_sleep_innovation_ge_0_12_and_usable": bool(
            sleep_usable
            and math.isfinite(sleep_innovation)
            and abs(sleep_innovation) >= SSM_INNOVATION_THRESHOLD
        ),
        "state_delta_vs_rolling_ge_0_08": bool(
            math.isfinite(state_delta) and abs(state_delta) >= SSM_DISCREPANCY_THRESHOLD
        ),
    }
    relation_to_gate = _relation_to_gate(
        gate_final=gate_final,
        ssm_innovation=ssm_innovation,
        sleep_innovation=sleep_innovation,
        sleep_usable=sleep_usable,
        state_delta=state_delta,
    )

    if not any(rule_hits.values()) or relation_to_gate == "no_extra_signal":
        return _empty_sidecar(
            status="silent",
            date_str=date_str,
            reason="no_material_ssm_signal",
            relation_to_gate=relation_to_gate,
        ) | {"rule_hits": rule_hits}

    return {
        "status": "ok",
        "date": date_str,
        "published": True,
        "summary": _main_observation(
            relation_to_gate=relation_to_gate,
            ssm_innovation=ssm_innovation,
            sleep_innovation=sleep_innovation,
            sleep_usable=sleep_usable,
            state_delta=state_delta,
        ),
        "detail": _detail_text(
            gate_final=gate_final,
            action_detail=action_detail,
            relation_to_gate=relation_to_gate,
            state=state,
            rolling=rolling,
            baseline_state=baseline_state,
            fatigue_state=fatigue_state,
            ssm_innovation=ssm_innovation,
            sleep_innovation=sleep_innovation,
            sleep_quality=sleep_quality,
        ),
        "relation_to_gate": relation_to_gate,
        "reason": None,
        "source_mode": "deterministic_ssm_v1",
        "rule_hits": rule_hits,
    }


def build_latest_minimal_ssm_brief(
    *,
    ssm_path: Path,
    final_path: Path | None = None,
) -> dict[str, Any]:
    if not ssm_path.exists():
        return _empty_sidecar(status="missing", date_str=None, reason="missing_ssm_shadow")

    ssm_df = pd.read_csv(ssm_path)
    if ssm_df.empty or "Fecha" not in ssm_df.columns:
        return _empty_sidecar(status="missing", date_str=None, reason="empty_ssm_shadow")
    ssm_df["Fecha"] = pd.to_datetime(ssm_df["Fecha"], errors="coerce")
    ssm_df = ssm_df.sort_values("Fecha")
    valid = ssm_df[ssm_df["ssm_recovery_state"].notna()] if "ssm_recovery_state" in ssm_df.columns else ssm_df
    if valid.empty:
        return _empty_sidecar(status="not_applicable", date_str=None, reason="missing_ssm_state")
    latest = valid.iloc[-1]

    final_row = None
    if final_path is not None and final_path.exists():
        final_df = pd.read_csv(final_path)
        if not final_df.empty and "Fecha" in final_df.columns:
            final_df["Fecha"] = pd.to_datetime(final_df["Fecha"], errors="coerce")
            final_slice = final_df[final_df["Fecha"].dt.date == latest["Fecha"].date()]
            if not final_slice.empty:
                final_row = final_slice.iloc[-1]

    return build_minimal_ssm_brief(latest, final_row)
