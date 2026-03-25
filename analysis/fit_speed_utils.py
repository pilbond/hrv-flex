#!/usr/bin/env python3
"""Extracción de métricas de velocidad desde archivos FIT.

Módulo standalone: solo depende de fitparse (opcional). Sin imports del proyecto.
Usado por session_analysis_pipeline.py y patch_speed_metrics.py.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

try:
    from fitparse import FitFile
except Exception:  # pragma: no cover
    FitFile = None


# ---------------------------------------------------------------------------
# Tipos internos
# ---------------------------------------------------------------------------

Record = dict[str, Any]  # {"sec": float, "hr": float|None, "speed_kmh": float}


# ---------------------------------------------------------------------------
# Parseo del FIT
# ---------------------------------------------------------------------------

def _parse_fit_records(fit_path: Path) -> list[Record]:
    """Devuelve lista de registros [{sec, hr, speed_kmh}] desde un FIT file."""
    if FitFile is None:
        raise RuntimeError("fitparse no está instalado")

    fit = FitFile(str(fit_path))
    rows: list[Record] = []
    start_ts = None
    for msg in fit.get_messages("record"):
        values = {field.name: field.value for field in msg}
        ts = values.get("timestamp")
        if ts is None:
            continue
        if start_ts is None:
            start_ts = ts
        sec = (ts - start_ts).total_seconds()
        speed_mps = values.get("enhanced_speed") or values.get("speed")
        rows.append(
            {
                "sec": float(sec),
                "hr": float(values["heart_rate"]) if values.get("heart_rate") is not None else None,
                "speed_kmh": float(speed_mps or 0.0) * 3.6,
            }
        )
    return rows


# ---------------------------------------------------------------------------
# Reconstrucción de bloques de trabajo por umbral VT1
# ---------------------------------------------------------------------------

def _reconstruct_block_speeds(
    records: list[Record],
    vt1_bpm: float,
    expected_n: int,
    merge_gap_sec: float = 60.0,
    merge_hr_drop_bpm: float = 10.0,
    min_block_sec: float = 30.0,
) -> tuple[list[float | None] | None, bool]:
    """Reconstruye bloques de trabajo (HR ≥ VT1) y calcula velocidad media por bloque.

    Algoritmo de merge: dos segmentos consecutivos se fusionan si el gap entre
    ellos cumple AMBAS condiciones: gap ≤ merge_gap_sec Y caída de HR ≤ merge_hr_drop_bpm.
    Esto replica el criterio operativo de Intervals.icu / AGENTS.md.

    Returns:
        (speeds_per_block, blocks_matched)
        - speeds_per_block: lista de velocidades medias (km/h) por bloque, o None si no pudo reconstruirse
        - blocks_matched: True si el número de bloques reconstruidos == expected_n
    """
    # Paso 1: segmentos crudos por encima de VT1
    in_block = False
    raw_segs: list[tuple[float, float]] = []
    current_start: float | None = None

    for rec in records:
        hr = rec["hr"]
        if hr is None:
            continue
        above = hr >= vt1_bpm
        if above and not in_block:
            current_start = rec["sec"]
            in_block = True
        elif not above and in_block:
            duration = rec["sec"] - (current_start or 0.0)
            if duration >= min_block_sec:
                raw_segs.append((current_start, rec["sec"]))  # type: ignore[arg-type]
            in_block = False

    if in_block and current_start is not None:
        duration = records[-1]["sec"] - current_start
        if duration >= min_block_sec:
            raw_segs.append((current_start, records[-1]["sec"]))

    if not raw_segs:
        return None, False

    # Paso 2: merge de segmentos adyacentes
    merged: list[tuple[float, float]] = [raw_segs[0]]
    for seg in raw_segs[1:]:
        prev_start, prev_end = merged[-1]
        gap_start, gap_end = prev_end, seg[0]
        gap_sec = gap_end - gap_start

        gap_hrs = [r["hr"] for r in records if gap_start <= r["sec"] <= gap_end and r["hr"] is not None]
        pre_gap_hrs = [r["hr"] for r in records if r["sec"] <= gap_start and r["hr"] is not None]
        hr_before_gap = pre_gap_hrs[-1] if pre_gap_hrs else vt1_bpm
        hr_min_in_gap = min(gap_hrs) if gap_hrs else hr_before_gap
        hr_drop = hr_before_gap - hr_min_in_gap

        if gap_sec <= merge_gap_sec and hr_drop <= merge_hr_drop_bpm:
            merged[-1] = (prev_start, seg[1])  # extender bloque previo
        else:
            merged.append(seg)

    # Paso 3: velocidad media por bloque
    speeds: list[float | None] = []
    for start, end in merged:
        block_spds = [
            r["speed_kmh"]
            for r in records
            if start <= r["sec"] <= end and r.get("speed_kmh") is not None and r["speed_kmh"] > 0.5
        ]
        speeds.append(round(sum(block_spds) / len(block_spds), 2) if block_spds else None)

    blocks_matched = len(merged) == expected_n
    return speeds, blocks_matched


# ---------------------------------------------------------------------------
# Función principal pública
# ---------------------------------------------------------------------------

def compute_speed_metrics(
    fit_path: Path | str,
    vt1_bpm: float | None,
    work_blocks_n: int,
    sport_family: str = "road",
) -> dict | None:
    """Extrae métricas de velocidad/ritmo desde un archivo FIT de artefacto.

    Args:
        fit_path:       Ruta al session.fit (artifacts/).
        vt1_bpm:        Umbral VT1 en lpm (de session_row.vt1_used). None = sin reconstrucción de bloques.
        work_blocks_n:  Número de bloques esperados (de work_blocks_min). 0 = sin reconstrucción.
        sport_family:   'road' | 'trail' | 'bike' | 'hike' | 'swim' | 'elliptical'

    Returns:
        Dict con métricas de velocidad o None si el FIT no está disponible/parseable::

            {
                "avg_speed_kmh": float | None,
                "avg_pace_min_km": str | None,     # ej. "6:34" — solo para running
                "work_blocks_speed_kmh": list[float|None] | None,
                "blocks_matched": bool | None,
                "source": "fit"
            }
    """
    fit_path = Path(fit_path)
    if FitFile is None or not fit_path.exists():
        return None

    try:
        records = _parse_fit_records(fit_path)
    except Exception:
        return None

    if not records:
        return None

    # Velocidad media global (solo registros con movimiento real)
    moving = [r for r in records if r["speed_kmh"] > 0.5]
    avg_spd = round(sum(r["speed_kmh"] for r in moving) / len(moving), 2) if moving else None

    # Ritmo en min/km para deportes de carrera
    is_running = sport_family in ("road", "trail")
    avg_pace: str | None = None
    if is_running and avg_spd and avg_spd > 0.0:
        pace_sec = 3600.0 / avg_spd  # segundos por km
        avg_pace = f"{int(pace_sec // 60)}:{int(pace_sec % 60):02d}"

    # Velocidad por bloque de trabajo
    block_speeds: list[float | None] | None = None
    blocks_matched: bool | None = None
    if vt1_bpm is not None and work_blocks_n > 0:
        hr_recs = [r for r in records if r["hr"] is not None]
        if hr_recs:
            block_speeds, blocks_matched = _reconstruct_block_speeds(
                hr_recs, float(vt1_bpm), work_blocks_n
            )

    return {
        "avg_speed_kmh": avg_spd,
        "avg_pace_min_km": avg_pace,
        "work_blocks_speed_kmh": block_speeds,
        "blocks_matched": blocks_matched,
        "source": "fit",
    }
