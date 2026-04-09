from __future__ import annotations

from typing import Any

from polar_utils import parse_float


RUN_SPORTS = {"road_run", "trail_run", "run", "running", "virtual_run", "virtualrun"}


def summary_sessions_metadata(summary: dict[str, Any]) -> dict[str, Any]:
    sessions_metadata = summary.get("sessions_metadata")
    return sessions_metadata if isinstance(sessions_metadata, dict) else {}


def summary_training_audit(summary: dict[str, Any]) -> dict[str, Any]:
    sessions_metadata = summary_sessions_metadata(summary)
    nested = sessions_metadata.get("training_audit")
    if isinstance(nested, dict):
        return nested
    legacy = summary.get("training_audit")
    return legacy if isinstance(legacy, dict) else {}


def _training_audit_source(source: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(source, dict):
        return {}
    if "signal_level" in source or "metric_level" in source:
        return source
    return summary_training_audit(source)


def training_audit_metric_state(source: dict[str, Any], metric_name: str) -> str | None:
    audit = _training_audit_source(source)
    metric_level = audit.get("metric_level") if isinstance(audit, dict) else {}
    metric = metric_level.get(metric_name) if isinstance(metric_level, dict) else {}
    state = metric.get("state") if isinstance(metric, dict) else None
    return str(state) if state else None


def training_audit_dataset_limits(source: dict[str, Any]) -> list[str]:
    audit = _training_audit_source(source)
    signal_level = audit.get("signal_level") if isinstance(audit, dict) else {}
    limits = signal_level.get("interpretability_limits") if isinstance(signal_level, dict) else []
    return [str(item) for item in limits if str(item).strip()]


def training_audit_session_flags(summary: dict[str, Any]) -> list[str]:
    row = summary.get("session_row") or {}
    if not isinstance(row, dict):
        return []

    flags: list[str] = []
    zones_source = str(row.get("zones_source") or "").strip().lower()
    if zones_source == "fallback":
        flags.append("session_zones_fallback")

    stream_dt = str(row.get("stream_dt_est") or "").strip()
    if not stream_dt:
        flags.append("session_without_stream")

    session_group = str(row.get("session_group") or "").strip().lower()
    cardiac_drift = str(row.get("cardiac_drift_pct") or "").strip()
    if session_group.startswith("endurance") and stream_dt and not cardiac_drift:
        flags.append("session_without_drift")

    return flags


def training_audit_session_affected(summary: dict[str, Any]) -> bool:
    return bool(training_audit_session_flags(summary))


def session_report_evidence(summary: dict[str, Any]) -> list[tuple[str, str]]:
    row = summary.get("session_row") or {}
    session_cost = summary.get("session_cost_model") or {}
    evidence: list[tuple[str, str]] = []

    if isinstance(row, dict):
        drift_raw = str(row.get("cardiac_drift_pct") or "").strip()
        try:
            drift = float(drift_raw) if drift_raw else None
        except ValueError:
            drift = None

        sport = str(row.get("sport") or "").strip().lower()
        if drift is not None:
            if drift >= 8.0:
                evidence.append(("session", f"cardiac_drift_pct = {drift:.1f}% (alto)"))
            elif drift <= -10.0:
                label = "perfil descendente de FC"
                if sport == "bike":
                    label = "perfil descendente de FC; revisar pacing/perfil"
                evidence.append(("session", f"cardiac_drift_pct = {drift:.1f}% ({label})"))

        is_run = sport in RUN_SPORTS
        run_power_available = parse_float(row.get("run_power_available"))
        polar_speed_available = parse_float(row.get("polar_speed_available"))
        polar_cadence_available = parse_float(row.get("polar_cadence_available"))
        if is_run and (
            (run_power_available is not None and run_power_available >= 0.5)
            or (polar_speed_available is not None and polar_speed_available >= 0.5)
            or (polar_cadence_available is not None and polar_cadence_available >= 0.5)
        ):
            run_power_mean = parse_float(row.get("run_power_mean"))
            speed_first_half = parse_float(row.get("speed_first_half"))
            speed_second_half = parse_float(row.get("speed_second_half"))
            cadence_first_half = parse_float(row.get("cadence_first_half"))
            cadence_second_half = parse_float(row.get("cadence_second_half"))

            if run_power_mean is not None:
                evidence.append(("mechanics", f"run_power_mean = {run_power_mean:.1f} W"))

            if speed_first_half is not None and speed_second_half is not None:
                speed_delta = speed_second_half - speed_first_half
                if abs(speed_delta) >= 0.1:
                    split_label = "negative split" if speed_delta > 0 else "fade"
                    evidence.append(
                        (
                            "mechanics",
                            f"speed_first_half = {speed_first_half:.2f} km/h, "
                            f"speed_second_half = {speed_second_half:.2f} km/h ({split_label})",
                        )
                    )
                else:
                    evidence.append(
                        (
                            "mechanics",
                            f"speed_first_half = {speed_first_half:.2f} km/h, "
                            f"speed_second_half = {speed_second_half:.2f} km/h",
                        )
                    )

            if cadence_first_half is not None and cadence_second_half is not None:
                cadence_delta = cadence_second_half - cadence_first_half
                if abs(cadence_delta) >= 1.0:
                    trend = "↑" if cadence_delta > 0 else "↓"
                    evidence.append(
                        (
                            "mechanics",
                            f"cadence_first_half = {cadence_first_half:.1f}, "
                            f"cadence_second_half = {cadence_second_half:.1f} ({trend})",
                        )
                    )
                else:
                    evidence.append(
                        (
                            "mechanics",
                            f"cadence_first_half = {cadence_first_half:.1f}, "
                            f"cadence_second_half = {cadence_second_half:.1f}",
                        )
                    )

    cardio_conf = str(session_cost.get("confidence_cardio") or "").strip().lower()
    mech_conf = str(session_cost.get("confidence_mecanico") or "").strip().lower()
    zones_source = str(row.get("zones_source") or "").strip().lower() if isinstance(row, dict) else ""
    mechanics_source = str(row.get("mechanics_source") or "").strip() if isinstance(row, dict) else ""

    if cardio_conf and cardio_conf != "high":
        reason = "zonas no ICU" if zones_source == "fallback" else "base cardiometabolica parcial"
        evidence.append(("confidence", f"confidence_cardio = {cardio_conf} ({reason})"))

    if mech_conf and mech_conf != "high":
        reason = "sin señal mecánica directa; proxy por relieve/bloques"
        if mechanics_source:
            reason = f"señal mecánica parcial desde {mechanics_source}"
        evidence.append(("confidence", f"confidence_mecanico = {mech_conf} ({reason})"))

    return evidence
