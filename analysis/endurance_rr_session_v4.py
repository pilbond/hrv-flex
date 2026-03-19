#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Endurance session RR analyzer v4
--------------------------------
Session-focused RR analysis for the workflows used in this repo.

Key features:
- preserves raw session time from the RR stream
- uses a self-contained core RR cleaning path
- adds a conservative strict layer for DFA-oriented outputs
- separates QA for RMSSD, DFA-alpha1 and HR@0.75
- introduces `dfa_gate` for interpretability
- supports FIT-first, with TCX fallback or TCX HR injection over FIT timing
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass
from pathlib import Path
from statistics import mean, median
from typing import Optional

import numpy as np
import pandas as pd

try:
    from fitparse import FitFile
except Exception:  # pragma: no cover - optional import at runtime
    FitFile = None


RR_MIN_MS = 300.0
RR_MAX_MS = 2000.0
DELTA_RR_THRESHOLD = 0.20


@dataclass
class RRInputQA:
    total_rows_file: int
    parseable_rows: int
    bad_duration_rows: int
    unknown_offline_rows: int
    offline_true_rows: int
    out_of_range_rows: int
    delta_rr_removed: int
    accepted_rows: int
    accepted_fraction_of_parseable: float
    accepted_fraction_of_file: float
    raw_duration_min_parseable: float
    accepted_duration_min: float
    time_axis_trust: str


@dataclass
class SessionMeta:
    total_timer_time: float | None
    total_elapsed_time: float | None
    total_distance_m: float | None
    avg_hr: int | None
    max_hr: int | None
    avg_cadence: float | None
    sport: str | None
    sub_sport: str | None
    total_calories: int | None


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Analyze session RR with strict QA and DFA gate.")
    p.add_argument("--rr", required=True, help="Path to RR CSV (duration,offline)")
    p.add_argument("--fit", help="Optional FIT file (preferred for HR mapping / blocks)")
    p.add_argument("--tcx", help="Optional TCX file (fallback for HR mapping)")
    p.add_argument("--sport", default="trail", choices=["trail", "bike", "swim"])
    p.add_argument("--vt1", type=float, default=None)
    p.add_argument("--vt2", type=float, default=None)
    p.add_argument("--out-prefix", help="Optional prefix for CSV / JSON outputs")

    p.add_argument("--rmssd-1m-min-valid-frac", type=float, default=0.85)
    p.add_argument("--rmssd-5m-min-valid-frac", type=float, default=0.90)
    p.add_argument("--rmssd-1m-min-beats", type=int, default=20)
    p.add_argument("--rmssd-5m-min-beats", type=int, default=100)
    p.add_argument("--rmssd-min-usable-windows", type=int, default=3)

    p.add_argument("--dfa-win-beats", type=int, default=300)
    p.add_argument("--dfa-step-beats", type=int, default=60)
    p.add_argument("--dfa-min-valid-frac-core", type=float, default=0.90)
    p.add_argument("--dfa-min-valid-frac-strict", type=float, default=0.85)
    p.add_argument("--dfa-max-artifact-run", type=int, default=3)
    p.add_argument("--dfa-min-usable-windows", type=int, default=5)
    p.add_argument("--scale-min", type=int, default=4)
    p.add_argument("--scale-max", type=int, default=16)
    p.add_argument(
        "--dfa-method",
        default="forward_reverse",
        choices=["forward", "forward_reverse"],
        help="DFA fluctuation method used for the primary alpha1 output",
    )

    p.add_argument("--local-window-beats", type=int, default=5)
    p.add_argument("--local-rel-dev-threshold", type=float, default=0.18)

    p.add_argument("--dfa-gate-ok-strict-frac", type=float, default=0.97)
    p.add_argument("--dfa-gate-limited-strict-frac", type=float, default=0.94)
    p.add_argument("--dfa-gate-min-hr-coverage", type=float, default=0.80)

    p.add_argument("--hr075-min-bins", type=int, default=4)
    p.add_argument("--hr075-min-points-per-bin", type=int, default=3)
    p.add_argument("--hr075-min-r2", type=float, default=0.55)
    p.add_argument("--hr075-min-near-windows", type=int, default=6)

    p.add_argument("--block-sec", type=float, default=None)
    p.add_argument("--offset-sec", type=float, default=0.0)
    p.add_argument("--target-speeds-kmh", default=None)
    p.add_argument("--auto-offset-max-sec", type=int, default=180)
    return p.parse_args()


def safe_quantile(values: np.ndarray, q: float) -> Optional[float]:
    if values.size == 0:
        return None
    return float(np.quantile(values, q))


def rmssd_ms(rr_ms: np.ndarray) -> float:
    if rr_ms.size < 3:
        return float("nan")
    diffs = np.diff(rr_ms)
    return float(np.sqrt(np.mean(diffs * diffs)))


def dfa_alpha1(rr_ms: np.ndarray, scales: np.ndarray, method: str = "forward_reverse") -> float:
    x = np.asarray(rr_ms, dtype=float)
    if x.size < int(scales.max()) * 4:
        return float("nan")

    x = x - np.mean(x)
    y = np.cumsum(x)
    ns_used = []
    f_used = []
    for n in scales:
        n = int(n)
        k = y.size // n
        if k < 4:
            continue
        t = np.arange(n, dtype=float)
        rms_vals = []
        sources = (y, y[::-1]) if method == "forward_reverse" else (y,)
        for source in sources:
            yk = source[: k * n].reshape(k, n)
            for row in yk:
                p = np.polyfit(t, row, 1)
                trend = p[0] * t + p[1]
                resid = row - trend
                rms_vals.append(np.sqrt(np.mean(resid * resid)))
        f_n = float(np.sqrt(np.mean(np.square(rms_vals))))
        if np.isfinite(f_n) and f_n > 0:
            ns_used.append(n)
            f_used.append(f_n)

    if len(ns_used) < 5:
        return float("nan")

    slope, _ = np.polyfit(np.log(np.asarray(ns_used, dtype=float)), np.log(np.asarray(f_used, dtype=float)), 1)
    return float(slope)


def parse_offline_token(value: object) -> Optional[bool]:
    token = str(value).strip().lower()
    if token in {"1", "true", "t", "yes", "y"}:
        return True
    if token in {"0", "false", "f", "no", "n", ""}:
        return False
    return None


def load_rr_csv(rr_path: str) -> tuple[pd.DataFrame, RRInputQA]:
    rows: list[dict[str, object]] = []
    total_rows_file = 0
    bad_duration_rows = 0
    unknown_offline_rows = 0

    with open(rr_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        required = {"duration", "offline"}
        if reader.fieldnames is None or not required.issubset(set(reader.fieldnames)):
            raise ValueError(f"RR CSV must contain columns {sorted(required)}")

        for line_no, row in enumerate(reader, start=2):
            total_rows_file += 1
            raw_duration = row.get("duration")
            raw_offline = row.get("offline")

            try:
                duration_ms = float(raw_duration)
            except Exception:
                bad_duration_rows += 1
                continue

            offline_state = parse_offline_token(raw_offline)
            if offline_state is None:
                unknown_offline_rows += 1
                offline_state = True

            rows.append(
                {
                    "line_no": line_no,
                    "duration_ms": duration_ms,
                    "offline": bool(offline_state),
                }
            )

    if not rows:
        raise ValueError("RR CSV has no parseable rows")

    df = pd.DataFrame(rows)
    df["beat_index"] = np.arange(len(df), dtype=int)
    df["is_in_range"] = df["duration_ms"].between(RR_MIN_MS, RR_MAX_MS, inclusive="both")
    df["candidate_pre_delta"] = (~df["offline"]) & df["is_in_range"]
    df["accepted"] = False
    df["reject_reason"] = np.where(df["offline"], "offline", np.where(~df["is_in_range"], "out_of_range", ""))

    last_accepted: Optional[float] = None
    delta_rr_removed = 0
    for idx in df.index:
        if not bool(df.at[idx, "candidate_pre_delta"]):
            continue
        dur = float(df.at[idx, "duration_ms"])
        if last_accepted is None:
            df.at[idx, "accepted"] = True
            df.at[idx, "reject_reason"] = ""
            last_accepted = dur
            continue

        rel_jump = abs(dur - last_accepted) / max(last_accepted, 1e-9)
        if rel_jump > DELTA_RR_THRESHOLD:
            delta_rr_removed += 1
            df.at[idx, "accepted"] = False
            df.at[idx, "reject_reason"] = "delta_rr"
            continue

        df.at[idx, "accepted"] = True
        df.at[idx, "reject_reason"] = ""
        last_accepted = dur

    end_s = np.cumsum(df["duration_ms"].to_numpy(dtype=float)) / 1000.0
    start_s = np.concatenate(([0.0], end_s[:-1]))
    df["start_s"] = start_s
    df["end_s"] = end_s

    accepted_rows = int(df["accepted"].sum())
    parseable_rows = int(len(df))
    qa = RRInputQA(
        total_rows_file=total_rows_file,
        parseable_rows=parseable_rows,
        bad_duration_rows=bad_duration_rows,
        unknown_offline_rows=unknown_offline_rows,
        offline_true_rows=int(df["offline"].sum()),
        out_of_range_rows=int((~df["is_in_range"]).sum()),
        delta_rr_removed=delta_rr_removed,
        accepted_rows=accepted_rows,
        accepted_fraction_of_parseable=(accepted_rows / parseable_rows) if parseable_rows else 0.0,
        accepted_fraction_of_file=(accepted_rows / total_rows_file) if total_rows_file else 0.0,
        raw_duration_min_parseable=float(df["duration_ms"].sum() / 60000.0),
        accepted_duration_min=float(df.loc[df["accepted"], "duration_ms"].sum() / 60000.0),
        time_axis_trust="OK" if bad_duration_rows == 0 else "COMPROMISED_BAD_DURATION_ROWS",
    )
    return df, qa


def load_fit_records(fit_path: str) -> tuple[SessionMeta, pd.DataFrame]:
    if FitFile is None:
        raise RuntimeError("fitparse is not installed; FIT support is unavailable")

    fit = FitFile(str(fit_path))
    session_msg = next(iter(fit.get_messages("session")), None)
    meta = SessionMeta(None, None, None, None, None, None, None, None, None)
    if session_msg is not None:
        fields = {field.name: field.value for field in session_msg}
        meta = SessionMeta(
            total_timer_time=fields.get("total_timer_time"),
            total_elapsed_time=fields.get("total_elapsed_time"),
            total_distance_m=fields.get("total_distance"),
            avg_hr=fields.get("avg_heart_rate"),
            max_hr=fields.get("max_heart_rate"),
            avg_cadence=fields.get("avg_running_cadence") or fields.get("avg_cadence"),
            sport=fields.get("sport"),
            sub_sport=fields.get("sub_sport"),
            total_calories=fields.get("total_calories"),
        )

    fit = FitFile(str(fit_path))
    rows: list[dict[str, object]] = []
    start_ts = None
    for msg in fit.get_messages("record"):
        values = {field.name: field.value for field in msg}
        ts = values.get("timestamp")
        if ts is None:
            continue
        if start_ts is None:
            start_ts = ts
        sec = (ts - start_ts).total_seconds()
        speed_mps = values.get("enhanced_speed")
        if speed_mps is None:
            speed_mps = values.get("speed")
        rows.append(
            {
                "sec": float(sec),
                "hr": values.get("heart_rate"),
                "speed_kmh": float(speed_mps or 0.0) * 3.6,
                "cadence": values.get("cadence"),
            }
        )

    if not rows:
        raise ValueError("FIT file contains no record messages")
    return meta, pd.DataFrame(rows)


def parse_tcx_hr(tcx_path: str) -> pd.DataFrame:
    tree = ET.parse(tcx_path)
    root = tree.getroot()

    ns = {}
    if root.tag.startswith("{"):
        uri = root.tag.split("}")[0].strip("{")
        ns["tcx"] = uri
        tp_xpath = ".//tcx:Trackpoint"
    else:
        tp_xpath = ".//Trackpoint"

    rows = []
    for tp in root.findall(tp_xpath, ns):
        t_el = tp.find("tcx:Time" if ns else "Time", ns)
        hr_el = tp.find("tcx:HeartRateBpm/tcx:Value" if ns else "HeartRateBpm/Value", ns)
        if t_el is None or hr_el is None:
            continue
        try:
            t = pd.to_datetime(t_el.text, utc=True)
            hr = float(hr_el.text)
            rows.append((t, hr))
        except Exception:
            continue

    if not rows:
        return pd.DataFrame(columns=["sec", "hr", "speed_kmh", "cadence"])

    out = pd.DataFrame(rows, columns=["time", "hr"]).sort_values("time").reset_index(drop=True)
    out["sec"] = (out["time"] - out["time"].iloc[0]).dt.total_seconds().astype(float)
    out["speed_kmh"] = np.nan
    out["cadence"] = np.nan
    return out[["sec", "hr", "speed_kmh", "cadence"]]


def interpolate_hr_at_seconds(hr_df: pd.DataFrame, seconds: np.ndarray) -> np.ndarray:
    if hr_df.empty or seconds.size == 0 or hr_df["hr"].dropna().empty:
        return np.full(seconds.shape, np.nan, dtype=float)
    src = hr_df.dropna(subset=["sec", "hr"]).sort_values("sec")
    x = src["sec"].to_numpy(dtype=float)
    y = src["hr"].to_numpy(dtype=float)
    return np.interp(seconds, x, y, left=np.nan, right=np.nan)


def choose_hr_source(args: argparse.Namespace) -> tuple[SessionMeta, pd.DataFrame, Optional[str], Optional[str]]:
    notes: list[str] = []

    if args.fit:
        try:
            meta, fit_df = load_fit_records(args.fit)
            if not fit_df.empty:
                if fit_df["hr"].dropna().empty and args.tcx:
                    try:
                        tcx_df = parse_tcx_hr(args.tcx)
                        if not tcx_df.empty and not tcx_df["hr"].dropna().empty:
                            fit_df = fit_df.copy()
                            fit_df["hr"] = interpolate_hr_at_seconds(tcx_df, fit_df["sec"].to_numpy(dtype=float))
                            notes.append("FIT loaded; HR mapped from TCX because FIT HR was unavailable")
                            return meta, fit_df, "FIT+TCX_HR", " | ".join(notes)
                    except Exception as exc:
                        notes.append(f"TCX fallback after FIT HR gap failed: {exc}")
                return meta, fit_df, "FIT", " | ".join(notes) if notes else None
        except Exception as exc:
            notes.append(f"FIT load failed: {exc}")

    if args.tcx:
        try:
            df = parse_tcx_hr(args.tcx)
            if not df.empty:
                return SessionMeta(None, None, None, None, None, None, None, None, None), df, "TCX", " | ".join(notes) if notes else None
            notes.append("TCX parsed but produced no usable HR trackpoints")
        except Exception as exc:
            notes.append(f"TCX load failed: {exc}")

    empty = pd.DataFrame(columns=["sec", "hr", "speed_kmh", "cadence"])
    return SessionMeta(None, None, None, None, None, None, None, None, None), empty, None, " | ".join(notes) if notes else None


def time_axis_is_trusted(rr_input_qa: dict[str, object]) -> bool:
    return rr_input_qa.get("time_axis_trust") == "OK"


def max_consecutive_true(mask: np.ndarray) -> int:
    best = 0
    cur = 0
    for val in mask.astype(bool):
        if val:
            cur += 1
            if cur > best:
                best = cur
        else:
            cur = 0
    return int(best)


def add_strict_artifact_layer(rr_df: pd.DataFrame, args: argparse.Namespace) -> tuple[pd.DataFrame, dict[str, object]]:
    df = rr_df.copy()
    df["accepted_core"] = df["accepted"].astype(bool)
    df["accepted_strict"] = df["accepted_core"].astype(bool)
    df["local_artifact"] = False

    core_idx = df.index[df["accepted_core"]]
    core_rr = df.loc[core_idx, "duration_ms"].astype(float).reset_index(drop=True)
    min_periods = max(3, args.local_window_beats // 2 + 1)
    rolling_med = core_rr.rolling(window=args.local_window_beats, center=True, min_periods=min_periods).median()
    rel_dev = (core_rr - rolling_med).abs() / rolling_med
    suspects = rel_dev > args.local_rel_dev_threshold
    suspects = suspects.fillna(False)

    suspect_positions = np.flatnonzero(suspects.to_numpy(dtype=bool))
    if suspect_positions.size:
        suspect_idx = core_idx[suspect_positions]
        df.loc[suspect_idx, "local_artifact"] = True
        df.loc[suspect_idx, "accepted_strict"] = False

    artifact_layer = np.full(len(df), "accepted", dtype=object)
    artifact_layer[~df["accepted_core"].to_numpy(dtype=bool)] = df.loc[
        ~df["accepted_core"], "reject_reason"
    ].replace("", "rejected").to_numpy(dtype=object)
    artifact_layer[df["local_artifact"].to_numpy(dtype=bool)] = "local_artifact"
    df["artifact_layer"] = artifact_layer

    accepted_strict_rows = int(df["accepted_strict"].sum())
    summary = {
        "accepted_core_rows": int(df["accepted_core"].sum()),
        "accepted_strict_rows": accepted_strict_rows,
        "local_artifact_removed": int(df["local_artifact"].sum()),
        "accepted_strict_fraction_of_parseable": (accepted_strict_rows / len(df)) if len(df) else 0.0,
        "accepted_strict_duration_min": float(df.loc[df["accepted_strict"], "duration_ms"].sum() / 60000.0),
        "local_artifact_window_beats": args.local_window_beats,
        "local_artifact_rel_dev_threshold": args.local_rel_dev_threshold,
    }
    return df, summary


def build_rmssd_windows_v4(
    rr_df: pd.DataFrame,
    window_sec: int,
    min_valid_frac: float,
    min_beats: int,
    min_usable_windows: int,
) -> tuple[pd.DataFrame, dict[str, object], dict[str, object]]:
    total_end = float(rr_df["end_s"].iloc[-1])
    rows: list[dict[str, object]] = []
    start = 0.0

    while start < total_end - 1e-9:
        end = start + window_sec
        raw_mask = (rr_df["end_s"] > start) & (rr_df["end_s"] <= end)
        seg_raw = rr_df.loc[raw_mask]
        seg_core = seg_raw.loc[seg_raw["accepted_core"]]
        seg_strict = seg_raw.loc[seg_raw["accepted_strict"]]

        parseable_beats = int(len(seg_raw))
        core_beats = int(len(seg_core))
        strict_beats = int(len(seg_strict))
        valid_frac_core = (core_beats / parseable_beats) if parseable_beats else 0.0
        valid_frac_strict = (strict_beats / parseable_beats) if parseable_beats else 0.0

        val = float("nan")
        usable = False
        reason = "no_beats"
        if parseable_beats > 0:
            if core_beats < min_beats:
                reason = "insufficient_core_beats"
            elif valid_frac_core < min_valid_frac:
                reason = "low_valid_fraction_core"
            else:
                val = rmssd_ms(seg_core["duration_ms"].to_numpy(dtype=float))
                usable = bool(np.isfinite(val))
                reason = "ok" if usable else "rmssd_nan"

        rows.append(
            {
                "window_start_sec": round(start, 3),
                "window_end_sec": round(end, 3),
                "window_center_sec": round(start + window_sec / 2.0, 3),
                "parseable_beats": parseable_beats,
                "accepted_core_beats": core_beats,
                "accepted_strict_beats": strict_beats,
                "valid_frac_core": round(valid_frac_core, 6),
                "valid_frac_strict": round(valid_frac_strict, 6),
                "rmssd_ms": None if not np.isfinite(val) else round(float(val), 6),
                "usable": usable,
                "reason": reason,
            }
        )
        start = end

    df = pd.DataFrame(rows)
    usable_vals = df.loc[df["usable"], "rmssd_ms"].to_numpy(dtype=float)
    summary = {
        "window_sec": window_sec,
        "p10": safe_quantile(usable_vals, 0.10),
        "p50": safe_quantile(usable_vals, 0.50),
        "p90": safe_quantile(usable_vals, 0.90),
        "n_windows_total": int(len(df)),
        "n_windows_usable": int(df["usable"].sum()),
        "min_valid_frac_required": min_valid_frac,
        "min_beats_required": min_beats,
        "rr_layer_used": "core",
    }
    usability = {
        "usable": bool(summary["n_windows_usable"] >= min_usable_windows),
        "reason": (
            "ok"
            if summary["n_windows_usable"] >= min_usable_windows
            else f"too_few_usable_rmssd_windows_min_{min_usable_windows}"
        ),
    }
    return df, summary, usability


def rmssd_band_minutes(rmssd_1m_df: pd.DataFrame) -> dict[str, float]:
    out = {"<=7": 0.0, "8-11": 0.0, ">=12": 0.0}
    usable = rmssd_1m_df.loc[rmssd_1m_df["usable"]]
    for _, row in usable.iterrows():
        val = float(row["rmssd_ms"])
        if val <= 7:
            out["<=7"] += 1.0
        elif val <= 11:
            out["8-11"] += 1.0
        else:
            out[">=12"] += 1.0
    return {k: round(v, 2) for k, v in out.items()}


def build_dfa_windows_v4(
    rr_df: pd.DataFrame,
    hr_df: pd.DataFrame,
    hr_source: str | None,
    args: argparse.Namespace,
) -> tuple[pd.DataFrame, dict[str, object], dict[str, object], dict[str, object], dict[str, object]]:
    strict = rr_df.loc[rr_df["accepted_strict"]].reset_index(drop=True)
    if len(strict) < args.dfa_win_beats:
        empty = pd.DataFrame(
            columns=[
                "start_sec",
                "end_sec",
                "center_sec",
                "accepted_beats",
                "valid_frac_core_raw",
                "valid_frac_strict_raw",
                "artifact_run_max",
                "alpha1",
                "center_hr",
                "usable",
                "reason",
            ]
        )
        dfa_summary = {
            "n_windows_total": 0,
            "n_windows_usable": 0,
            "median": None,
            "q25": None,
            "q75": None,
            "iqr": None,
            "pct_lt_075": None,
            "min_valid_frac_core_required": args.dfa_min_valid_frac_core,
            "min_valid_frac_strict_required": args.dfa_min_valid_frac_strict,
            "win_beats": args.dfa_win_beats,
            "step_beats": args.dfa_step_beats,
            "max_artifact_run": args.dfa_max_artifact_run,
            "rr_layer_used": "strict",
            "dfa_method": args.dfa_method,
        }
        usability = {"usable": False, "reason": "not_enough_accepted_strict_beats_for_dfa"}
        hr_mapping = {"hr_source": hr_source, "dfa_windows_with_hr": 0, "dfa_windows_without_hr": 0, "coverage_frac": 0.0}
        comparison = {
            "primary_method": args.dfa_method,
            "secondary_method": "forward" if args.dfa_method == "forward_reverse" else "forward_reverse",
            "median_abs_diff": None,
            "mean_abs_diff": None,
            "max_abs_diff": None,
            "n_compared_windows": 0,
        }
        return empty, dfa_summary, usability, hr_mapping, comparison

    strict_raw_idx = rr_df.index[rr_df["accepted_strict"]].to_numpy(dtype=int)
    scales = np.arange(args.scale_min, args.scale_max + 1)
    rows: list[dict[str, object]] = []
    secondary_method = "forward" if args.dfa_method == "forward_reverse" else "forward_reverse"
    primary_vals: list[float] = []
    secondary_vals: list[float] = []

    for start_i in range(0, len(strict) - args.dfa_win_beats + 1, args.dfa_step_beats):
        end_i = start_i + args.dfa_win_beats - 1
        raw_idx_slice = strict_raw_idx[start_i : end_i + 1]
        raw_start = float(rr_df.loc[raw_idx_slice[0], "start_s"])
        raw_end = float(rr_df.loc[raw_idx_slice[-1], "end_s"])
        raw_mask = (rr_df["end_s"] > raw_start) & (rr_df["end_s"] <= raw_end)
        seg_raw = rr_df.loc[raw_mask]
        valid_frac_core = float(seg_raw["accepted_core"].mean()) if not seg_raw.empty else 0.0
        valid_frac_strict = float(seg_raw["accepted_strict"].mean()) if not seg_raw.empty else 0.0
        artifact_run_max = max_consecutive_true(seg_raw["local_artifact"].to_numpy(dtype=bool)) if not seg_raw.empty else 0

        alpha = float("nan")
        usable = False
        reason = "low_valid_fraction_core"
        if valid_frac_core >= args.dfa_min_valid_frac_core:
            if valid_frac_strict < args.dfa_min_valid_frac_strict:
                reason = "low_valid_fraction_strict"
            elif artifact_run_max > args.dfa_max_artifact_run:
                reason = "artifact_run_too_long"
            else:
                seg_rr = rr_df.loc[raw_idx_slice, "duration_ms"].to_numpy(dtype=float)
                alpha = dfa_alpha1(seg_rr, scales=scales, method=args.dfa_method)
                usable = bool(np.isfinite(alpha))
                reason = "ok" if usable else "alpha1_nan"
                if usable:
                    alt_alpha = dfa_alpha1(seg_rr, scales=scales, method=secondary_method)
                    if np.isfinite(alt_alpha):
                        primary_vals.append(float(alpha))
                        secondary_vals.append(float(alt_alpha))

        center_sec = (raw_start + raw_end) / 2.0
        rows.append(
            {
                "start_sec": round(raw_start, 3),
                "end_sec": round(raw_end, 3),
                "center_sec": round(center_sec, 3),
                "accepted_beats": int(len(raw_idx_slice)),
                "valid_frac_core_raw": round(valid_frac_core, 6),
                "valid_frac_strict_raw": round(valid_frac_strict, 6),
                "artifact_run_max": int(artifact_run_max),
                "alpha1": None if not np.isfinite(alpha) else round(float(alpha), 6),
                "usable": usable,
                "reason": reason,
            }
        )

    dfa_df = pd.DataFrame(rows)
    if not dfa_df.empty:
        hr_interp = interpolate_hr_at_seconds(hr_df, dfa_df["center_sec"].to_numpy(dtype=float))
        dfa_df["center_hr"] = np.where(np.isfinite(hr_interp), np.round(hr_interp, 6), np.nan)
    else:
        dfa_df["center_hr"] = np.nan

    usable_alpha = dfa_df.loc[dfa_df["usable"] & dfa_df["alpha1"].notna(), "alpha1"].to_numpy(dtype=float)
    q25 = safe_quantile(usable_alpha, 0.25)
    q75 = safe_quantile(usable_alpha, 0.75)
    dfa_summary = {
        "n_windows_total": int(len(dfa_df)),
        "n_windows_usable": int(dfa_df["usable"].sum()),
        "median": safe_quantile(usable_alpha, 0.50),
        "q25": q25,
        "q75": q75,
        "iqr": None if q25 is None or q75 is None else float(q75 - q25),
        "pct_lt_075": None if usable_alpha.size == 0 else float(100.0 * np.mean(usable_alpha < 0.75)),
        "min_valid_frac_core_required": args.dfa_min_valid_frac_core,
        "min_valid_frac_strict_required": args.dfa_min_valid_frac_strict,
        "win_beats": args.dfa_win_beats,
        "step_beats": args.dfa_step_beats,
        "max_artifact_run": args.dfa_max_artifact_run,
        "rr_layer_used": "strict",
        "dfa_method": args.dfa_method,
    }
    usability = {
        "usable": bool(dfa_summary["n_windows_usable"] >= args.dfa_min_usable_windows),
        "reason": (
            "ok"
            if dfa_summary["n_windows_usable"] >= args.dfa_min_usable_windows
            else f"too_few_usable_dfa_windows_min_{args.dfa_min_usable_windows}"
        ),
    }

    usable_hr = int(dfa_df.loc[dfa_df["usable"] & dfa_df["center_hr"].notna()].shape[0])
    unusable_hr = int(dfa_df.loc[dfa_df["usable"] & dfa_df["center_hr"].isna()].shape[0])
    denom = usable_hr + unusable_hr
    hr_mapping = {
        "hr_source": hr_source,
        "dfa_windows_with_hr": usable_hr,
        "dfa_windows_without_hr": unusable_hr,
        "coverage_frac": (usable_hr / denom) if denom else 0.0,
    }
    if primary_vals and secondary_vals:
        diffs = np.abs(np.asarray(primary_vals) - np.asarray(secondary_vals))
        comparison = {
            "primary_method": args.dfa_method,
            "secondary_method": secondary_method,
            "median_abs_diff": float(np.median(diffs)),
            "mean_abs_diff": float(np.mean(diffs)),
            "max_abs_diff": float(np.max(diffs)),
            "n_compared_windows": int(len(diffs)),
        }
    else:
        comparison = {
            "primary_method": args.dfa_method,
            "secondary_method": secondary_method,
            "median_abs_diff": None,
            "mean_abs_diff": None,
            "max_abs_diff": None,
            "n_compared_windows": 0,
        }
    return dfa_df, dfa_summary, usability, hr_mapping, comparison


def build_dfa_gate(
    rr_input_qa: dict[str, object],
    dfa_summary: dict[str, object],
    dfa_usable: dict[str, object],
    hr_mapping: dict[str, object],
    args: argparse.Namespace,
) -> dict[str, object]:
    strict_frac = float(rr_input_qa["accepted_strict_fraction_of_parseable"])
    hr_coverage = float(hr_mapping["coverage_frac"])
    n_usable = int(dfa_summary["n_windows_usable"])

    if not dfa_usable["usable"]:
        return {"state": "DFA_NO_INTERPRETABLE", "reason": dfa_usable["reason"]}
    if strict_frac >= args.dfa_gate_ok_strict_frac and (
        hr_mapping["hr_source"] is None or hr_coverage >= args.dfa_gate_min_hr_coverage
    ):
        return {"state": "DFA_OK", "reason": "strict_artifact_load_low_and_dfa_windows_sufficient"}
    if strict_frac >= args.dfa_gate_limited_strict_frac and n_usable >= args.dfa_min_usable_windows:
        return {"state": "DFA_LIMITED", "reason": "dfa_usable_but_artifact_load_or_hr_coverage_not_optimal"}
    return {"state": "DFA_NO_INTERPRETABLE", "reason": "strict_artifact_load_too_high_for_confident_dfa"}


def apply_time_axis_policy(
    rr_input_qa: dict[str, object],
    hr_df: pd.DataFrame,
    hr_source: str | None,
    dfa_gate: dict[str, object],
) -> tuple[pd.DataFrame, str | None, dict[str, object]]:
    if time_axis_is_trusted(rr_input_qa):
        return hr_df, hr_source, dfa_gate

    limited_gate = dict(dfa_gate)
    if limited_gate["state"] == "DFA_OK":
        limited_gate = {
            "state": "DFA_LIMITED",
            "reason": "time_axis_compromised_dfa_values_available_but_time_based_interpretation_limited",
        }
    return (
        pd.DataFrame(columns=["sec", "hr", "speed_kmh", "cadence"]),
        None,
        limited_gate,
    )


def estimate_hr_at_alpha075_v4(
    dfa_df: pd.DataFrame,
    dfa_gate: dict[str, object],
    args: argparse.Namespace,
) -> dict[str, object]:
    if dfa_gate["state"] != "DFA_OK":
        return {
            "hr_at_075": None,
            "usable": False,
            "reason": f"dfa_gate_{dfa_gate['state'].lower()}",
            "r2": None,
            "raw_r": None,
            "slope": None,
            "n_bins": 0,
            "method": "strict_binned_local",
        }

    df = dfa_df.loc[dfa_df["usable"] & dfa_df["alpha1"].notna() & dfa_df["center_hr"].notna()].copy()
    if len(df) < 20:
        return {
            "hr_at_075": None,
            "usable": False,
            "reason": "too_few_dfa_windows_with_hr",
            "r2": None,
            "raw_r": None,
            "slope": None,
            "n_bins": 0,
            "method": "strict_binned_local",
        }

    raw_x = df["center_hr"].to_numpy(dtype=float)
    raw_y = df["alpha1"].to_numpy(dtype=float)
    raw_r = float(np.corrcoef(raw_x, raw_y)[0, 1]) if len(df) >= 2 else float("nan")
    if not np.isfinite(raw_r):
        return {
            "hr_at_075": None,
            "usable": False,
            "reason": "non_finite_hr_alpha1_correlation",
            "r2": None,
            "raw_r": None,
            "slope": None,
            "n_bins": 0,
            "method": "strict_binned_local",
        }

    raw_slope, _ = np.polyfit(raw_x, raw_y, 1)
    raw_r2 = raw_r * raw_r
    if raw_slope >= 0:
        return {
            "hr_at_075": None,
            "usable": False,
            "reason": "alpha1_does_not_decrease_with_hr",
            "r2": float(raw_r2),
            "raw_r": float(raw_r),
            "slope": float(raw_slope),
            "n_bins": 0,
            "method": "strict_binned_local",
        }
    if raw_r2 < args.hr075_min_r2:
        return {
            "hr_at_075": None,
            "usable": False,
            "reason": f"weak_raw_hr_alpha1_relation_r2_{raw_r2:.2f}",
            "r2": float(raw_r2),
            "raw_r": float(raw_r),
            "slope": float(raw_slope),
            "n_bins": 0,
            "method": "strict_binned_local",
        }

    df["hr_bin"] = np.floor(df["center_hr"].astype(float) / 3.0) * 3.0
    grouped = (
        df.groupby("hr_bin", as_index=False)
        .agg(hr_med=("center_hr", "median"), a1_med=("alpha1", "median"), n=("alpha1", "size"))
        .sort_values("hr_med")
        .reset_index(drop=True)
    )
    grouped = grouped.loc[grouped["n"] >= args.hr075_min_points_per_bin].copy()
    n_bins = int(len(grouped))
    if n_bins < args.hr075_min_bins:
        return {
            "hr_at_075": None,
            "usable": False,
            "reason": "too_few_hr_bins",
            "r2": float(raw_r2),
            "raw_r": float(raw_r),
            "slope": float(raw_slope),
            "n_bins": n_bins,
            "method": "strict_binned_local",
        }

    x = grouped["hr_med"].to_numpy(dtype=float)
    y = grouped["a1_med"].to_numpy(dtype=float)
    if (np.nanmax(y) - np.nanmin(y)) < 0.15:
        return {
            "hr_at_075": None,
            "usable": False,
            "reason": "alpha1_too_flat_across_hr",
            "r2": float(raw_r2),
            "raw_r": float(raw_r),
            "slope": float(raw_slope),
            "n_bins": n_bins,
            "method": "strict_binned_local",
        }

    monotonic_steps = np.sum(np.diff(y) < 0)
    if monotonic_steps < max(1, len(y) - 2):
        return {
            "hr_at_075": None,
            "usable": False,
            "reason": "binned_alpha1_not_monotonic_enough",
            "r2": float(raw_r2),
            "raw_r": float(raw_r),
            "slope": float(raw_slope),
            "n_bins": n_bins,
            "method": "strict_binned_local",
        }

    crossings: list[tuple[float, int]] = []
    for i in range(len(grouped) - 1):
        y1 = float(y[i])
        y2 = float(y[i + 1])
        if (y1 - 0.75) == 0 or (y2 - 0.75) == 0 or ((y1 - 0.75) * (y2 - 0.75) < 0):
            crossings.append((abs(y1 - 0.75) + abs(y2 - 0.75), i))

    if not crossings:
        return {
            "hr_at_075": None,
            "usable": False,
            "reason": "no_local_alpha1_075_bracketing_bins",
            "r2": float(raw_r2),
            "raw_r": float(raw_r),
            "slope": float(raw_slope),
            "n_bins": n_bins,
            "method": "strict_binned_local",
        }

    _, best_i = min(crossings, key=lambda item: item[0])
    x1 = float(x[best_i])
    x2 = float(x[best_i + 1])
    y1 = float(y[best_i])
    y2 = float(y[best_i + 1])
    if x1 == x2 or y1 == y2:
        return {
            "hr_at_075": None,
            "usable": False,
            "reason": "degenerate_local_crossing_bins",
            "r2": float(raw_r2),
            "raw_r": float(raw_r),
            "slope": float(raw_slope),
            "n_bins": n_bins,
            "method": "strict_binned_local",
        }

    hr075 = x1 + (0.75 - y1) * (x2 - x1) / (y2 - y1)
    if not np.isfinite(hr075):
        return {
            "hr_at_075": None,
            "usable": False,
            "reason": "non_finite_hr075",
            "r2": float(raw_r2),
            "raw_r": float(raw_r),
            "slope": float(raw_slope),
            "n_bins": n_bins,
            "method": "strict_binned_local",
        }

    near_cross = df.loc[df["alpha1"].between(0.70, 0.80)]
    if len(near_cross) < args.hr075_min_near_windows:
        return {
            "hr_at_075": None,
            "usable": False,
            "reason": "too_few_raw_windows_near_075",
            "r2": float(raw_r2),
            "raw_r": float(raw_r),
            "slope": float(raw_slope),
            "n_bins": n_bins,
            "method": "strict_binned_local",
        }

    return {
        "hr_at_075": float(hr075),
        "usable": True,
        "reason": "ok",
        "r2": float(raw_r2),
        "raw_r": float(raw_r),
        "slope": float(raw_slope),
        "n_bins": n_bins,
        "method": "strict_binned_local",
    }


def alpha1_by_hr_zone(dfa_df: pd.DataFrame, sport: str, dfa_gate: dict[str, object]) -> dict[str, float | None]:
    if dfa_gate["state"] == "DFA_NO_INTERPRETABLE":
        return {
            "alpha1_med_z1_hr": None,
            "alpha1_med_z2_hr": None,
            "alpha1_med_z3_hr": None,
        }
    if dfa_df.empty or dfa_df["center_hr"].dropna().empty:
        return {}

    if sport.lower() == "trail":
        z1_max, z2_min, z2_max, z3_min = 144, 145, 161, 162
    elif sport.lower() == "bike":
        z1_max, z2_min, z2_max, z3_min = 139, 140, 156, 157
    elif sport.lower() == "swim":
        z1_max, z2_min, z2_max, z3_min = 134, 135, 149, 150
    else:
        return {}

    df = dfa_df.loc[dfa_df["usable"] & dfa_df["alpha1"].notna() & dfa_df["center_hr"].notna()].copy()
    if df.empty:
        return {}
    hr = df["center_hr"].to_numpy(dtype=float)
    a1 = df["alpha1"].to_numpy(dtype=float)
    masks = {
        "alpha1_med_z1_hr": hr <= z1_max,
        "alpha1_med_z2_hr": (hr >= z2_min) & (hr <= z2_max),
        "alpha1_med_z3_hr": hr >= z3_min,
    }
    out: dict[str, float | None] = {}
    for key, mask in masks.items():
        vals = a1[mask]
        out[key] = None if vals.size == 0 else float(np.median(vals))
    return out


def mean_speed_in_window(records: pd.DataFrame, start_sec: float, end_sec: float) -> float | None:
    vals = records.loc[(records["sec"] >= start_sec) & (records["sec"] < end_sec), "speed_kmh"].dropna().tolist()
    return mean(vals) if vals else None


def autodetect_offset(records: pd.DataFrame, target_speeds: list[float], block_sec: float, max_offset_sec: int) -> tuple[float, list[float]]:
    best_score = math.inf
    best_offset = 0.0
    best_obs: list[float] = []
    for offset in range(max_offset_sec + 1):
        obs: list[float] = []
        ok = True
        for i, _target in enumerate(target_speeds):
            start_sec = offset + i * block_sec
            end_sec = offset + (i + 1) * block_sec
            speed = mean_speed_in_window(records, start_sec, end_sec)
            if speed is None:
                ok = False
                break
            obs.append(speed)
        if not ok:
            continue
        score = sum((obs_i - tgt_i) ** 2 for obs_i, tgt_i in zip(obs, target_speeds))
        if score < best_score:
            best_score = score
            best_offset = float(offset)
            best_obs = obs
    return best_offset, best_obs


def summarize_blocks(
    dfa_df: pd.DataFrame,
    hr_df: pd.DataFrame,
    args: argparse.Namespace,
    offset_sec: float,
    block_labels: list[str] | None,
) -> list[dict[str, object]]:
    if args.block_sec is None or hr_df.empty:
        return []

    max_end = float(hr_df["sec"].max())
    if block_labels:
        block_count = len(block_labels)
    else:
        block_count = int(math.floor((max_end - offset_sec) / args.block_sec))

    blocks: list[dict[str, object]] = []
    for i in range(block_count):
        start_s = offset_sec + i * args.block_sec
        end_s = start_s + args.block_sec
        wr = dfa_df.loc[
            dfa_df["usable"]
            & dfa_df["alpha1"].notna()
            & (dfa_df["center_sec"] >= start_s)
            & (dfa_df["center_sec"] < end_s)
        ]
        fr = hr_df.loc[(hr_df["sec"] >= start_s) & (hr_df["sec"] < end_s)]
        hr_vals = fr["hr"].dropna().astype(float).tolist() if "hr" in fr else []
        cadence_vals = fr["cadence"].dropna().astype(float).tolist() if "cadence" in fr else []
        speed_vals = fr["speed_kmh"].dropna().astype(float).tolist() if "speed_kmh" in fr else []

        block: dict[str, object] = {
            "block_index": i + 1,
            "label": block_labels[i] if block_labels and i < len(block_labels) else None,
            "start_s": round(start_s, 3),
            "end_s": round(end_s, 3),
            "speed_kmh_mean": round(mean(speed_vals), 3) if speed_vals else None,
            "hr_mean": round(mean(hr_vals), 3) if hr_vals else None,
            "hr_max": round(max(hr_vals), 3) if hr_vals else None,
            "cadence_mean": round(mean(cadence_vals), 3) if cadence_vals else None,
            "alpha1_median": round(median(wr["alpha1"].astype(float).tolist()), 6) if not wr.empty else None,
            "alpha1_mean": round(mean(wr["alpha1"].astype(float).tolist()), 6) if not wr.empty else None,
            "alpha1_lt_075_pct": round(100.0 * np.mean(wr["alpha1"].astype(float) < 0.75), 3) if not wr.empty else None,
            "window_count": int(len(wr)),
        }
        if args.vt1 is not None and hr_vals:
            block["z1_min"] = round(sum(h <= args.vt1 for h in hr_vals) / 60.0, 3)
            if args.vt2 is not None:
                block["z2_min"] = round(sum(args.vt1 < h <= args.vt2 for h in hr_vals) / 60.0, 3)
                block["z3_min"] = round(sum(h > args.vt2 for h in hr_vals) / 60.0, 3)
        blocks.append(block)
    return blocks


def write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    if not rows:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(path, index=False)


def format_summary(summary: dict[str, object]) -> str:
    lines = [
        f"rr_path: {summary['rr_path']}",
        f"fit_path: {summary['fit_path']}",
        f"tcx_path: {summary['tcx_path']}",
        f"hr_source: {summary['hr_source']}",
        f"hr_source_note: {summary['hr_source_note']}",
        f"time_axis_trust: {summary['rr_input_qa']['time_axis_trust']}",
        f"accepted_core_fraction: {summary['rr_input_qa']['accepted_fraction_of_parseable']:.6f}",
        f"accepted_strict_fraction: {summary['rr_input_qa']['accepted_strict_fraction_of_parseable']:.6f}",
        f"dfa_gate: {summary['dfa_gate']['state']} ({summary['dfa_gate']['reason']})",
        f"rmssd_1min_usable: {summary['usability']['rmssd_1min']['usable']} ({summary['usability']['rmssd_1min']['reason']})",
        f"rmssd_5min_usable: {summary['usability']['rmssd_5min']['usable']} ({summary['usability']['rmssd_5min']['reason']})",
        f"dfa_usable: {summary['usability']['dfa_alpha1']['usable']} ({summary['usability']['dfa_alpha1']['reason']})",
        f"hr_at_075: {summary['hr_at_075']['hr_at_075']}",
        f"hr_at_075_usable: {summary['hr_at_075']['usable']} ({summary['hr_at_075']['reason']})",
    ]
    return "\n".join(lines)


def main() -> int:
    args = parse_args()
    rr_df_core, qa_base = load_rr_csv(args.rr)
    rr_df, strict_info = add_strict_artifact_layer(rr_df_core, args)
    session_meta, hr_df, hr_source, hr_source_note = choose_hr_source(args)

    rr_input_qa = asdict(qa_base)
    rr_input_qa.update(strict_info)

    rmssd_1m_df, rmssd_1m_summary, rmssd_1m_usable = build_rmssd_windows_v4(
        rr_df,
        60,
        args.rmssd_1m_min_valid_frac,
        args.rmssd_1m_min_beats,
        args.rmssd_min_usable_windows,
    )
    rmssd_5m_df, rmssd_5m_summary, rmssd_5m_usable = build_rmssd_windows_v4(
        rr_df,
        300,
        args.rmssd_5m_min_valid_frac,
        args.rmssd_5m_min_beats,
        args.rmssd_min_usable_windows,
    )
    dfa_df, dfa_summary, dfa_usable, hr_mapping, dfa_method_comparison = build_dfa_windows_v4(rr_df, hr_df, hr_source, args)
    dfa_gate = build_dfa_gate(rr_input_qa, dfa_summary, dfa_usable, hr_mapping, args)
    hr_df, hr_source, dfa_gate = apply_time_axis_policy(rr_input_qa, hr_df, hr_source, dfa_gate)
    if not time_axis_is_trusted(rr_input_qa):
        hr_source_note = (
            f"{hr_source_note} | " if hr_source_note else ""
        ) + "Time axis compromised: HR mapping, HR@0.75 and block outputs disabled"
        hr_mapping = {"hr_source": None, "dfa_windows_with_hr": 0, "dfa_windows_without_hr": 0, "coverage_frac": 0.0}
        if "center_hr" in dfa_df.columns:
            dfa_df = dfa_df.copy()
            dfa_df["center_hr"] = np.nan
    hr075_summary = estimate_hr_at_alpha075_v4(dfa_df, dfa_gate, args)
    alpha1_zone_medians = alpha1_by_hr_zone(dfa_df, args.sport, dfa_gate)

    offset_sec = float(args.offset_sec)
    target_speeds = None
    observed_speeds = None
    block_labels = None
    if args.target_speeds_kmh:
        if args.block_sec is None:
            raise ValueError("--target-speeds-kmh requires --block-sec")
        if args.fit is None:
            raise ValueError("--target-speeds-kmh requires --fit because auto-alignment uses FIT speed")
        target_speeds = [float(x) for x in args.target_speeds_kmh.split(",") if x.strip()]
        offset_sec, observed_speeds = autodetect_offset(hr_df, target_speeds, args.block_sec, args.auto_offset_max_sec)
        block_labels = [f"{speed:.1f} km/h" for speed in target_speeds]
    blocks = summarize_blocks(dfa_df, hr_df, args, offset_sec, block_labels)

    summary = {
        "rr_path": args.rr,
        "fit_path": args.fit,
        "tcx_path": args.tcx,
        "hr_source": hr_source,
        "hr_source_note": hr_source_note,
        "session_meta": asdict(session_meta),
        "rr_input_qa": rr_input_qa,
        "usability": {
            "rmssd_1min": rmssd_1m_usable,
            "rmssd_5min": rmssd_5m_usable,
            "dfa_alpha1": dfa_usable,
            "hr_at_075": {"usable": hr075_summary["usable"], "reason": hr075_summary["reason"]},
        },
        "rmssd_1min": rmssd_1m_summary,
        "rmssd_5min": rmssd_5m_summary,
        "rmssd_1min_band_minutes": rmssd_band_minutes(rmssd_1m_df),
        "dfa_alpha1": dfa_summary,
        "dfa_method_comparison": dfa_method_comparison,
        "dfa_gate": dfa_gate,
        "hr_mapping": hr_mapping,
        "hr_at_075": hr075_summary,
        "alpha1_median_by_hr_zone": alpha1_zone_medians,
        "blocks_count": len(blocks),
        "offset_sec": offset_sec,
        "target_speeds_kmh": target_speeds,
        "observed_speeds_kmh": [round(v, 3) for v in observed_speeds] if observed_speeds is not None else None,
    }

    print(json.dumps(summary, indent=2, ensure_ascii=False))

    if args.out_prefix:
        prefix = Path(args.out_prefix)
        out_dir = prefix.parent if prefix.parent != Path("") else Path(".")
        out_dir.mkdir(parents=True, exist_ok=True)
        beat_cols = [
            "beat_index",
            "line_no",
            "start_s",
            "end_s",
            "duration_ms",
            "offline",
            "is_in_range",
            "candidate_pre_delta",
            "accepted",
            "accepted_core",
            "accepted_strict",
            "local_artifact",
            "reject_reason",
            "artifact_layer",
        ]
        write_csv(out_dir / f"{prefix.name}_rr_beats.csv", rr_df[beat_cols].to_dict(orient="records"))
        write_csv(out_dir / f"{prefix.name}_rmssd_1min.csv", rmssd_1m_df.to_dict(orient="records"))
        write_csv(out_dir / f"{prefix.name}_rmssd_5min.csv", rmssd_5m_df.to_dict(orient="records"))
        write_csv(out_dir / f"{prefix.name}_dfa_alpha1.csv", dfa_df.to_dict(orient="records"))
        write_csv(out_dir / f"{prefix.name}_blocks.csv", blocks)
        with (out_dir / f"{prefix.name}_summary.json").open("w", encoding="utf-8") as f:
            json.dump(summary, f, indent=2, ensure_ascii=False)

    print("\n" + format_summary(summary))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
