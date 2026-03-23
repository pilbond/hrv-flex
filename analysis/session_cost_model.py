#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Derive local cardio/mechanical session cost scores from sessions.csv.")
    p.add_argument("--sessions-csv", default="data/ENDURANCE_HRV_sessions.csv")
    p.add_argument("--session-id", required=True, help="Session identifier from sessions.csv")
    return p.parse_args()


def parse_float(row: dict[str, str], key: str) -> float | None:
    val = (row.get(key) or "").strip()
    if not val:
        return None
    try:
        return float(val)
    except ValueError:
        return None


def parse_int(row: dict[str, str], key: str) -> int | None:
    val = parse_float(row, key)
    if val is None:
        return None
    return int(round(val))


def load_session(path: Path, session_id: str) -> dict[str, str]:
    with path.open(encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row.get("session_id") == session_id:
                return row
    raise ValueError(f"session_id not found: {session_id}")


def normalize_sport(raw: str | None) -> str:
    sport = (raw or "").strip().lower()
    aliases = {
        "trail_run": "trail",
        "road_run": "trail",
        "run": "trail",
        "running": "trail",
        "virtual_run": "trail",
        "virtualrun": "trail",
        "bike": "bike",
        "ride": "bike",
        "virtual_ride": "bike",
        "swim": "swim",
        "pool_swim": "swim",
        "open_water_swim": "swim",
        "hike": "hike",
        "elliptical": "elliptical",
    }
    return aliases.get(sport, sport)


def append_evidence(evidence: list[str], text: str) -> None:
    if text not in evidence:
        evidence.append(text)


def cardio_score(row: dict[str, str]) -> tuple[int | None, str, list[str]]:
    evidence: list[str] = []
    z2_pct = parse_float(row, "z2_pct")
    z3_pct = parse_float(row, "z3_pct")
    hr_p95 = parse_float(row, "hr_p95")
    vt2 = parse_float(row, "vt2_used")
    work_total = parse_float(row, "work_total_min")
    work_longest = parse_float(row, "work_longest_min")
    work_n = parse_int(row, "work_n_blocks")
    work_avg_z3 = parse_float(row, "work_avg_z3_pct")
    zones_source = (row.get("zones_source") or "").strip().lower()

    if z2_pct is None or z3_pct is None or work_total is None or work_longest is None:
        return None, "low", ["faltan metricas base de zonas o work blocks"]

    z2plus_pct = z2_pct + z3_pct
    if z2plus_pct >= 40:
        append_evidence(evidence, f"z2+z3 = {z2plus_pct:.1f}%")
    elif z2plus_pct >= 25:
        append_evidence(evidence, f"z2+z3 = {z2plus_pct:.1f}%")

    if z3_pct >= 12:
        append_evidence(evidence, f"z3_pct = {z3_pct:.1f}%")
    elif z3_pct >= 5:
        append_evidence(evidence, f"z3_pct = {z3_pct:.1f}%")

    if work_total >= 35:
        append_evidence(evidence, f"work_total_min = {work_total:.1f}")
    elif work_total >= 20:
        append_evidence(evidence, f"work_total_min = {work_total:.1f}")
    elif work_total >= 8:
        append_evidence(evidence, f"work_total_min = {work_total:.1f}")

    if work_longest >= 20:
        append_evidence(evidence, f"work_longest_min = {work_longest:.1f}")
    elif work_longest >= 8:
        append_evidence(evidence, f"work_longest_min = {work_longest:.1f}")

    if work_n is not None and work_n >= 3:
        append_evidence(evidence, f"work_n_blocks = {work_n}")

    if work_avg_z3 is not None and work_avg_z3 >= 15:
        append_evidence(evidence, f"work_avg_z3_pct = {work_avg_z3:.0f}")

    if hr_p95 is not None and vt2 is not None:
        if hr_p95 >= vt2 + 3:
            append_evidence(evidence, f"hr_p95 = {hr_p95:.1f} (por encima de VT2)")
        elif hr_p95 >= vt2 - 3:
            append_evidence(evidence, f"hr_p95 = {hr_p95:.1f} (cerca de VT2)")

    if z2plus_pct >= 40 or z3_pct >= 12 or work_total >= 35 or (work_longest >= 20 and work_avg_z3 is not None and work_avg_z3 >= 15):
        score = 3
    elif z2plus_pct >= 25 or z3_pct >= 5 or work_total >= 20 or work_longest >= 20:
        score = 2
    elif z2plus_pct >= 10 or z3_pct >= 2 or work_total >= 8 or work_longest >= 8:
        score = 1
    else:
        score = 0

    confidence = "high" if zones_source == "icu" else "medium"
    if zones_source == "fallback":
        append_evidence(evidence, "zones_source = fallback")
    if not evidence:
        evidence.append("sin senal cardiometabolica material en zonas o work blocks")
    return score, confidence, evidence


def trail_mechanical_score(row: dict[str, str]) -> tuple[int | None, str, list[str]]:
    evidence: list[str] = []
    moving = parse_float(row, "moving_min")
    gain = parse_float(row, "elev_gain_m")
    loss = parse_float(row, "elev_loss_m")
    density = parse_float(row, "elev_density")
    work_total = parse_float(row, "work_total_min")
    work_longest = parse_float(row, "work_longest_min")

    if moving is None or moving <= 0:
        return None, "low", ["faltan metricas de moving_min"]

    uphill_h = (gain / (moving / 60.0)) if gain is not None else None
    downhill_h = (loss / (moving / 60.0)) if loss is not None else None
    terrain_score = 0
    terrain_signal = max(v for v in [uphill_h, downhill_h] if v is not None) if any(v is not None for v in [uphill_h, downhill_h]) else None
    if terrain_signal is not None:
        if terrain_signal >= 800:
            terrain_score = 3
        elif terrain_signal >= 400:
            terrain_score = 2
        elif terrain_signal >= 150:
            terrain_score = 1
        if uphill_h is not None:
            append_evidence(evidence, f"D+/h = {uphill_h:.0f}")
        if downhill_h is not None:
            append_evidence(evidence, f"D-/h = {downhill_h:.0f}")
    elif density is not None:
        if density >= 100:
            terrain_score = 3
        elif density >= 60:
            terrain_score = 2
        elif density >= 20:
            terrain_score = 1
        append_evidence(evidence, f"elev_density = {density:.1f}")

    locomotion_score = 0
    if work_total is not None and work_longest is not None:
        if work_total >= 35 and work_longest >= 20 and terrain_score <= 1:
            locomotion_score = 3
        elif work_total >= 20 and work_longest >= 12 and terrain_score <= 1:
            locomotion_score = 2
        elif work_total >= 10 and work_longest >= 8 and terrain_score <= 1:
            locomotion_score = 1
        if locomotion_score >= 1:
            append_evidence(evidence, f"bloque corrible sostenido: total {work_total:.1f} min, max {work_longest:.1f} min")

    score = max(terrain_score, locomotion_score)
    if terrain_score >= 2 and locomotion_score >= 2:
        score = min(3, score + 1)

    confidence = "high" if terrain_signal is not None or density is not None else "medium"
    if not evidence:
        evidence.append("sin senal mecanica material de terreno o locomocion")
    return score, confidence, evidence


def hike_mechanical_score(row: dict[str, str]) -> tuple[int | None, str, list[str]]:
    evidence: list[str] = []
    moving = parse_float(row, "moving_min")
    gain = parse_float(row, "elev_gain_m")
    loss = parse_float(row, "elev_loss_m")
    density = parse_float(row, "elev_density")
    work_total = parse_float(row, "work_total_min")
    work_longest = parse_float(row, "work_longest_min")

    if moving is None or moving <= 0:
        return None, "low", ["faltan metricas de moving_min"]

    terrain_signal = None
    if gain is not None or loss is not None:
        uphill_h = (gain / (moving / 60.0)) if gain is not None else None
        downhill_h = (loss / (moving / 60.0)) if loss is not None else None
        if uphill_h is not None:
            append_evidence(evidence, f"D+/h = {uphill_h:.0f}")
        if downhill_h is not None:
            append_evidence(evidence, f"D-/h = {downhill_h:.0f}")
        terrain_signal = max(v for v in [uphill_h, downhill_h] if v is not None) if any(v is not None for v in [uphill_h, downhill_h]) else None
    elif density is not None:
        append_evidence(evidence, f"elev_density = {density:.1f}")
        terrain_signal = density

    if terrain_signal is None:
        return None, "low", ["faltan metricas de terreno para hike"]

    if terrain_signal >= 800:
        terrain_score = 3
    elif terrain_signal >= 400:
        terrain_score = 2
    elif terrain_signal >= 150:
        terrain_score = 1
    else:
        terrain_score = 0

    effort_score = 0
    if work_total is not None and work_longest is not None:
        if work_total >= 35 and work_longest >= 20 and terrain_score >= 2:
            effort_score = 3
        elif work_total >= 20 and work_longest >= 12 and terrain_score >= 1:
            effort_score = 2
        elif work_total >= 10 and work_longest >= 8:
            effort_score = 1
        if effort_score >= 1:
            append_evidence(evidence, f"bloque de esfuerzo en hike: total {work_total:.1f} min, max {work_longest:.1f} min")

    score = max(terrain_score, effort_score)
    if terrain_score >= 2 and effort_score >= 2:
        score = min(3, score + 1)

    confidence = "medium" if terrain_signal is not None else "low"
    if not evidence:
        evidence.append("sin senal mecanica material de terreno o esfuerzo en hike")
    return score, confidence, evidence


def elliptical_mechanical_score(row: dict[str, str]) -> tuple[int | None, str, list[str]]:
    evidence: list[str] = []
    work_total = parse_float(row, "work_total_min")
    work_longest = parse_float(row, "work_longest_min")
    avg_cadence = parse_float(row, "avg_cadence")
    hr_p95 = parse_float(row, "hr_p95")
    vt2 = parse_float(row, "vt2_used")

    if work_total is None or work_longest is None:
        return None, "low", ["faltan metricas de estructura para elliptical"]

    if work_total >= 35 and work_longest >= 15:
        score = 2
        append_evidence(evidence, f"bloques de trabajo sostenido: total {work_total:.1f} min, max {work_longest:.1f} min")
    elif work_total >= 15 and work_longest >= 8:
        score = 1
        append_evidence(evidence, f"bloques de trabajo sostenido: total {work_total:.1f} min, max {work_longest:.1f} min")
    else:
        score = 0

    if avg_cadence is not None and avg_cadence >= 60 and score >= 1:
        append_evidence(evidence, f"avg_cadence = {avg_cadence:.0f}")
        if work_total >= 20:
            score = max(score, 2)
    if hr_p95 is not None and vt2 is not None and hr_p95 >= vt2 - 3 and score >= 1:
        append_evidence(evidence, f"hr_p95 = {hr_p95:.1f} (cerca de VT2)")
        if work_total >= 35:
            score = 3

    confidence = "low" if avg_cadence is None else "medium"
    if not evidence:
        evidence.append("base limitada para coste propulsivo en elliptical")
    return score, confidence, evidence


def bike_mechanical_score(row: dict[str, str]) -> tuple[int | None, str, list[str]]:
    evidence: list[str] = []
    moving = parse_float(row, "moving_min")
    gain = parse_float(row, "elev_gain_m")
    density = parse_float(row, "elev_density")
    work_total = parse_float(row, "work_total_min")
    work_longest = parse_float(row, "work_longest_min")

    if moving is None or moving <= 0:
        return None, "low", ["faltan metricas de moving_min"]

    terrain_score = 0
    if gain is not None:
        gain_h = gain / (moving / 60.0)
        if gain_h >= 700:
            terrain_score = 3
        elif gain_h >= 350:
            terrain_score = 2
        elif gain_h >= 120:
            terrain_score = 1
        append_evidence(evidence, f"D+/h = {gain_h:.0f}")
    elif density is not None:
        if density >= 70:
            terrain_score = 3
        elif density >= 35:
            terrain_score = 2
        elif density >= 15:
            terrain_score = 1
        append_evidence(evidence, f"elev_density = {density:.1f}")

    pedaling_score = 0
    if work_total is not None and work_longest is not None:
        if work_total >= 50 and work_longest >= 18:
            pedaling_score = 3
        elif work_total >= 30 and work_longest >= 12:
            pedaling_score = 2
        elif work_total >= 15 and work_longest >= 8:
            pedaling_score = 1
        if pedaling_score >= 1:
            append_evidence(evidence, f"bloques exigentes: total {work_total:.1f} min, max {work_longest:.1f} min")

    score = max(terrain_score, pedaling_score)
    if terrain_score >= 2 and pedaling_score >= 2:
        score = min(3, score + 1)

    confidence = "medium"
    if not evidence:
        evidence.append("sin senal mecanica material de relieve o bloques exigentes")
    return score, confidence, evidence


def swim_mechanical_score(row: dict[str, str]) -> tuple[int | None, str, list[str]]:
    evidence: list[str] = []
    work_total = parse_float(row, "work_total_min")
    work_longest = parse_float(row, "work_longest_min")
    z3_pct = parse_float(row, "z3_pct")

    if work_total is None or work_longest is None:
        return None, "low", ["faltan metricas de estructura para coste propulsivo"]

    if work_total >= 35 and work_longest >= 15:
        score = 2
        append_evidence(evidence, f"bloques de nado sostenido: total {work_total:.1f} min, max {work_longest:.1f} min")
    elif work_total >= 15 and work_longest >= 8:
        score = 1
        append_evidence(evidence, f"bloques de nado sostenido: total {work_total:.1f} min, max {work_longest:.1f} min")
    else:
        score = 0

    if z3_pct is not None and z3_pct >= 12:
        score = min(3, score + 1)
        append_evidence(evidence, f"z3_pct = {z3_pct:.1f}%")

    confidence = "low"
    if not evidence:
        evidence.append("base limitada para coste propulsivo en swim")
    return score, confidence, evidence


def mechanical_score(row: dict[str, str]) -> tuple[int | None, str, list[str]]:
    sport = normalize_sport(row.get("sport"))
    if sport == "trail":
        return trail_mechanical_score(row)
    if sport == "hike":
        return hike_mechanical_score(row)
    if sport == "bike":
        return bike_mechanical_score(row)
    if sport == "swim":
        return swim_mechanical_score(row)
    if sport == "elliptical":
        return elliptical_mechanical_score(row)
    return None, "low", [f"deporte sin rubrica mecanica automatizada: {row.get('sport') or 'unknown'}"]


def dominant_cost(cardio: int | None, mech: int | None) -> str:
    if cardio is None or mech is None:
        return "no_clasificable"
    if cardio <= 1 and mech <= 1:
        return "bajo_estimulo"
    if cardio >= 2 and cardio > mech:
        return "cardiometabolico"
    if mech >= 2 and mech > cardio:
        return "mecanico"
    if cardio >= 2 and mech >= 2 and cardio == mech:
        return "mixto"
    return "mixto"


def build_cost_model_result(row: dict[str, str]) -> dict[str, Any]:
    cardio, cardio_conf, cardio_evidence = cardio_score(row)
    mech, mech_conf, mech_evidence = mechanical_score(row)
    return {
        "session_id": row.get("session_id"),
        "date": row.get("Fecha"),
        "sport": row.get("sport"),
        "cardio_score": cardio,
        "mecanico_score": mech,
        "coste_dominante": dominant_cost(cardio, mech),
        "confidence_cardio": cardio_conf,
        "confidence_mecanico": mech_conf,
        "cardio_evidence": cardio_evidence,
        "mecanico_evidence": mech_evidence,
        "inputs_used": {
            "vt1_used": parse_float(row, "vt1_used"),
            "vt2_used": parse_float(row, "vt2_used"),
            "zones_source": row.get("zones_source"),
            "moving_min": parse_float(row, "moving_min"),
            "elev_gain_m": parse_float(row, "elev_gain_m"),
            "elev_loss_m": parse_float(row, "elev_loss_m"),
            "elev_density": parse_float(row, "elev_density"),
            "hr_p95": parse_float(row, "hr_p95"),
            "z2_pct": parse_float(row, "z2_pct"),
            "z3_pct": parse_float(row, "z3_pct"),
            "z2_total_min": parse_float(row, "z2_total_min"),
            "z3_total_min": parse_float(row, "z3_total_min"),
            "work_n_blocks": parse_int(row, "work_n_blocks"),
            "work_total_min": parse_float(row, "work_total_min"),
            "work_longest_min": parse_float(row, "work_longest_min"),
            "work_avg_z3_pct": parse_float(row, "work_avg_z3_pct"),
        },
    }


def main() -> int:
    args = parse_args()
    row = load_session(Path(args.sessions_csv), args.session_id)
    result = build_cost_model_result(row)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
