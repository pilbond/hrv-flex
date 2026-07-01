"""Traducción humana del gate HRV (qué pasó / qué hacer).

Convierte el código interno de razón del gate (``gate_razon_base60``) en dos
strings independientes pensados para mostrar al usuario: descripción de lo
que ocurrió y sugerencia de acción.

La lógica vivía como funciones privadas en ``hrv_app/cli_reporting.py`` y
solo la consumía la CLI. Se promueve a módulo neutro para que la UI web
(``hrv_app/ui_view.py``) consuma el mismo texto sin duplicar el mapping.
"""

from __future__ import annotations

from typing import Any

try:
    import pandas as pd
except ImportError:  # pragma: no cover
    pd = None


def _row_value(row: Any, key: str):
    if row is None:
        return None
    if hasattr(row, "get"):
        return row.get(key)
    try:
        return row[key]
    except (KeyError, TypeError, IndexError):
        return None


def _maybe_float(value: Any):
    if value is None:
        return None
    if pd is not None and pd.isna(value):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


_REASON_MAPPING = {
    "CAL/STAB/ART/NaN": (
        "La toma de hoy no fue lo bastante fiable para usarla. "
        "Suele pasar por artefactos, señal inestable o una medición "
        "incompleta."
    ),
    "ROLL3_INSUF": (
        "Aún faltan días limpios seguidos para construir una referencia "
        "fiable."
    ),
    "BASE60_INSUF": (
        "Todavía no hay suficientes datos limpios en la ventana de 60 días "
        "para comparar con confianza."
    ),
    "SWC_NAN/0": (
        "La referencia estadística de hoy salió vacía o demasiado plana, "
        "así que no conviene sacar conclusiones."
    ),
    "RAW_NAN/0": (
        "La señal bruta llegó vacía o inválida, por eso hoy no se pudo "
        "evaluar."
    ),
    "2D_OK": (
        "La señal quedó dentro de tu rango reciente; si el resto del "
        "contexto también acompaña, puedes seguir con el plan previsto."
    ),
    "2D_LN": (
        "La señal suavizada bajó respecto a tu base reciente; conviene "
        "no apretar más de la cuenta y vigilar recuperación y carga."
    ),
    "2D_HR": (
        "La frecuencia cardiaca suavizada subió respecto a tu base reciente; "
        "mejor mantener prudencia hoy y evitar subir demasiado la intensidad."
    ),
    "2D_AMBOS": (
        "La señal suavizada bajó y la frecuencia cardiaca suavizada subió "
        "respecto a tu base reciente; trata hoy como un día más delicado: "
        "baja un punto la exigencia."
    ),
}


_NEXT_STEP_MAPPING = {
    "CAL/STAB/ART/NaN": "Repite la toma en un momento más tranquilo, sin moverte y con el sensor bien colocado.",
    "ROLL3_INSUF": "Sigue midiendo de forma constante hasta reunir más días limpios.",
    "BASE60_INSUF": "Mantén la rutina: aún falta base para comparar con seguridad.",
    "SWC_NAN/0": "No tomes decisiones fuertes solo con este dato; espera una lectura con referencia estable.",
    "RAW_NAN/0": "Repite la medición o revisa si la señal llegó bien al sistema.",
    "2D_OK": "Puedes seguir con el plan previsto si el resto del contexto también acompaña.",
    "2D_LN": "Conviene no apretar más de la cuenta y vigilar recuperación y carga.",
    "2D_HR": "Mejor mantener prudencia hoy y evitar subir demasiado la intensidad.",
    "2D_AMBOS": "Trata hoy como un día más delicado: baja un punto la exigencia.",
}


def format_gate_reason(value: Any, row: Any = None) -> str:
    """Traduce ``gate_razon_base60`` al texto "qué pasó".

    Si el código es ``CAL/STAB/ART/NaN`` y se pasa una fila FINAL, anexa
    pistas extraídas de ``Artifact_pct``, ``HRV_Stability``,
    ``Stability_Subtype`` y ``Tiempo_Estabilizacion``.
    """
    raw = str(value or "").strip()
    if not raw or raw == "N/A":
        return "N/A"

    if raw in _REASON_MAPPING:
        text = _REASON_MAPPING[raw]
        if raw == "CAL/STAB/ART/NaN":
            clues: list[str] = []
            artifact_pct = _maybe_float(_row_value(row, "Artifact_pct"))
            if artifact_pct is not None:
                if artifact_pct >= 15:
                    clues.append(f"artefactos altos ({artifact_pct:.1f}%)")
                else:
                    clues.append(f"artefactos presentes ({artifact_pct:.1f}%)")

            stability = str(_row_value(row, "HRV_Stability") or "").strip()
            if stability and stability.upper() not in {"OK", "ALTA", "HIGH", "GOOD"}:
                clues.append(f"estabilidad de señal {stability}")

            subtype = str(_row_value(row, "Stability_Subtype") or "").strip()
            if subtype and subtype.upper() not in {"OK", "N/A", "NONE", "NAN"}:
                clues.append(f"subtipo de estabilidad {subtype}")

            tiemp_est = _maybe_float(_row_value(row, "Tiempo_Estabilizacion"))
            if tiemp_est is not None:
                clues.append(f"estabilización de {tiemp_est:.0f}s")

            if clues:
                return text + " Pistas del registro: " + "; ".join(clues) + "."
            return text + " Causas típicas: artefactos, estabilidad insuficiente o medición incompleta."
        return text

    if raw.startswith("CAL/"):
        return (
            "La toma de hoy no fue lo bastante fiable para usarla (calidad, "
            "estabilidad o artefactos)."
        )
    if raw.endswith("_INSUF"):
        return (
            "Aún no hay suficientes datos limpios para hacer una comparación "
            "fiable."
        )
    if raw.endswith("/0") or "NAN" in raw:
        return (
            "La referencia o la señal no tienen suficiente información válida "
            "para comparar hoy."
        )

    return f"{raw} (motivo interno no traducido)"


def format_gate_next_step(value: Any) -> str:
    """Traduce ``gate_razon_base60`` al texto "qué hacer"."""
    raw = str(value or "").strip()
    if not raw or raw == "N/A":
        return "N/A"

    if raw in _NEXT_STEP_MAPPING:
        return _NEXT_STEP_MAPPING[raw]
    if raw.startswith("CAL/"):
        return "Repite la toma en un momento más tranquilo y con el sensor bien colocado."
    if raw.endswith("_INSUF"):
        return "Sigue midiendo de forma constante hasta reunir más datos limpios."
    if raw.endswith("/0") or "NAN" in raw:
        return "No tomes decisiones fuertes con este dato; primero necesitas una lectura más fiable."
    return "Consulta el motivo interno si quieres más detalle técnico."
