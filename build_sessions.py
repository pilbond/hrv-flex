#!/usr/bin/env python3
"""
ENDURANCE HRV — Session Extraction Pipeline v3
================================================
Extrae datos de sesiones desde Intervals.icu API y genera:
  - sessions.csv       (1 fila por sesión)
  - sessions_day.csv   (1 fila por día, agregado + rolling)
  - ENDURANCE_HRV_sessions_metadata.json (trazabilidad de la corrida)

Modos:
  --backfill           Histórico completo desde --oldest (default 2025-05-12)
  --daily              Últimas 48h (para cron diario)
  --update             Desde el último día con datos hasta hoy (revisando ese último día)
  --date YYYY-MM-DD    Un día concreto

Config: .env con INTERVALS_API_KEY + INTERVALS_ATHLETE_ID

v3 changes:
  - Work blocks with merge_blocks_z2plus (gap≤60s AND drop≤10lpm)
  - Moving mask on stream analysis (velocity>0.3 m/s)
  - HR/vel alignment before drift
  - Fallback VT1/VT2 by sport + zones_source field
  - effort_vs_typical: dual mode (recent rolling 60d + anchor)
  - effort_above_typical split aerobic/strength
  - Rolling with _nobs (no blind missing→0)
  - Work block aggregates + string as forensic
  - ENDURANCE_HRV_sessions_metadata.json per run
  - CSV: QUOTE_ALL, notes sanitized
"""

import os
import sys
import time
import json
import hashlib
import argparse
import logging
from datetime import datetime, timedelta, date
from pathlib import Path
from typing import Optional

import requests
import numpy as np
import pandas as pd

# ─── Version & params ─────────────────────────────────────────────────────────

PIPELINE_VERSION = "v3.2"

PARAMS = {
    "gap_max_s": 60,
    "hr_drop_max_bpm": 10,
    "hr_exit_win_s": 30,
    "hr_min_win_s": 10,
    "min_block_s": 180,
    "late_intensity_threshold_lpm": 8,
    "late_intensity_min_duration_s": 2400,
    "drift_min_duration_s": 1800,
    "drift_min_speed_ms": 0.5,
    "moving_min_speed_ms": 0.3,
    "effort_recent_window_days": 60,
    "effort_min_prev_sessions": 5,
    "effort_anchor_start": "2025-06-01",
    "effort_anchor_end": "2025-08-31",
}


def params_hash() -> str:
    s = json.dumps(PARAMS, sort_keys=True)
    return hashlib.md5(s.encode()).hexdigest()[:8]


# ─── Config ───────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("build_sessions")

ENV_FILE = Path(__file__).parent / ".env"
if ENV_FILE.exists():
    for line in ENV_FILE.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())

API_KEY = os.environ.get("INTERVALS_API_KEY", "")
ATHLETE_ID = os.environ.get("INTERVALS_ATHLETE_ID", "")
BASE_URL = "https://intervals.icu/api/v1"
REQUEST_DELAY = 0.4

# ─── Sport config ─────────────────────────────────────────────────────────────

SPORT_MAP = {
    "TrailRun": "trail_run", "Hike": "trail_run",
    "Run": "road_run", "VirtualRun": "road_run",
    "Ride": "bike", "VirtualRide": "bike",
    "Swim": "swim",
    "Elliptical": "elliptical",
    "WeightTraining": "strength",
    "Workout": "mobility",
    "Other": "other",
}

AEROBIC_SPORTS = {"trail_run", "road_run", "bike", "swim", "elliptical"}

# Fix C: fallback VT1/VT2 by sport
VT_FALLBACK = {
    "trail_run": (143, 161),
    "road_run":  (143, 161),
    "bike":      (139, 156),
    "swim":      (134, 149),
    "elliptical": (139, 156),
    "strength":  (142, 163),
    "mobility":  (142, 163),
    "other":     (143, 161),
}

# ─── API Client ───────────────────────────────────────────────────────────────


class IntervalsClient:
    def __init__(self, api_key: str, athlete_id: str):
        self.session = requests.Session()
        self.session.auth = ("API_KEY", api_key)
        self.athlete_id = athlete_id
        self._last_request = 0.0

    def _rate_limit(self):
        elapsed = time.time() - self._last_request
        if elapsed < REQUEST_DELAY:
            time.sleep(REQUEST_DELAY - elapsed)
        self._last_request = time.time()

    def get(self, path: str, params: dict = None) -> requests.Response:
        self._rate_limit()
        url = f"{BASE_URL}{path}"
        r = self.session.get(url, params=params, timeout=30)
        r.raise_for_status()
        return r

    def get_activities(self, oldest: str, newest: str) -> list[dict]:
        return self.get(
            f"/athlete/{self.athlete_id}/activities",
            {"oldest": oldest, "newest": newest},
        ).json()

    def get_streams(self, activity_id: str,
                    types: str = "heartrate,velocity_smooth") -> dict:
        r = self.get(f"/activity/{activity_id}/streams", {"types": types})
        result = {}
        data = r.json()
        if isinstance(data, list):
            for s in data:
                result[s["type"]] = np.array(s.get("data", []), dtype=float)
        return result

    def get_activity_messages(self, activity_id: str) -> list[dict]:
        try:
            return self.get(f"/activity/{activity_id}/messages").json()
        except requests.HTTPError:
            return []


# ─── Smart block merge ────────────────────────────────────────────────────────


def merge_blocks_z2plus(
    hr: np.ndarray,
    vt1: float,
    moving_mask: Optional[np.ndarray] = None,
    gap_max_s: float = PARAMS["gap_max_s"],
    hr_drop_max_bpm: float = PARAMS["hr_drop_max_bpm"],
    hr_exit_win_s: float = PARAMS["hr_exit_win_s"],
    hr_min_win_s: float = PARAMS["hr_min_win_s"],
) -> list[list[int]]:
    """
    Merge Z2+ blocks separated by short Z1 gaps that don't reset physiology.
    Fix A: applies moving_mask if provided.
    """
    hr = np.asarray(hr, dtype=float)
    n = hr.size

    # Fix A: if moving_mask, treat non-moving as NaN for classification
    hr_eff = hr.copy()
    if moving_mask is not None:
        hr_eff[~moving_mask] = np.nan

    is_z2plus = hr_eff >= vt1

    # Smoothed HR for robust min (using original HR for physics)
    win = max(1, int(round(hr_min_win_s)))
    kernel = np.ones(win) / win
    hr_smooth = np.convolve(hr, kernel, mode="same")

    # Find raw Z2+ segments (ignoring NaN as not-Z2+)
    blocks = []
    i = 0
    while i < n:
        if is_z2plus[i] == True:  # noqa — explicit True check for NaN safety
            s = i
            while i < n and is_z2plus[i] == True:  # noqa
                i += 1
            blocks.append([s, i - 1])
        else:
            i += 1

    if len(blocks) <= 1:
        return blocks

    merged = [blocks[0]]
    for b in blocks[1:]:
        prev = merged[-1]
        gs = prev[1] + 1
        ge = b[0] - 1

        if ge < gs:
            prev[1] = b[1]
            continue

        gap_duration = ge - gs + 1
        gap_is_z1 = bool(np.all(hr[gs:ge + 1] < vt1))

        ew = max(1, int(hr_exit_win_s))
        es = max(prev[0], prev[1] - ew + 1)
        hr_exit = float(np.mean(hr[es:prev[1] + 1]))
        hr_min_gap = float(np.min(hr_smooth[gs:ge + 1]))
        hr_drop = hr_exit - hr_min_gap

        if gap_is_z1 and gap_duration <= gap_max_s and hr_drop <= hr_drop_max_bpm:
            prev[1] = b[1]
        else:
            merged.append(b)

    return merged


# ─── Stream analysis ──────────────────────────────────────────────────────────


def compute_hr_derived(hr: np.ndarray, vt1: int, vt2: int,
                       duration_s: float,
                       velocity: Optional[np.ndarray] = None) -> dict:
    """
    Compute HR-derived metrics with moving mask (Fix A).
    """
    # Fix A: build moving mask from velocity
    moving_mask = None
    if velocity is not None and len(velocity) > 0:
        # Fix B: align lengths
        n = min(len(hr), len(velocity))
        hr = hr[:n]
        velocity = velocity[:n]
        moving_mask = velocity > PARAMS["moving_min_speed_ms"]

    valid = hr[~np.isnan(hr)]
    if len(valid) < 60:
        return {}

    result = {}

    # Zone distribution — Fix A: use moving samples only
    if moving_mask is not None:
        hr_z = hr[moving_mask & ~np.isnan(hr)]
    else:
        hr_z = valid

    if len(hr_z) < 60:
        hr_z = valid  # fallback to all if moving filter too aggressive

    # hr_p95 on same universe as zones (coherence fix)
    result["hr_p95"] = round(float(np.percentile(hr_z, 95)), 1)

    total = len(hr_z)
    z1_s = float((hr_z <= vt1).sum())
    z2_s = float(((hr_z > vt1) & (hr_z <= vt2)).sum())
    z3_s = float((hr_z > vt2).sum())

    result["z1_pct"] = round(100.0 * z1_s / total, 1)
    result["z2_pct"] = round(100.0 * z2_s / total, 1)
    result["z3_pct"] = round(100.0 * z3_s / total, 1)
    result["z2_total_min"] = round(z2_s / 60.0, 1)
    result["z3_total_min"] = round(z3_s / 60.0, 1)

    # ── Work blocks (smart merge with moving mask) ──
    merged = merge_blocks_z2plus(hr, vt1=vt1, moving_mask=moving_mask)
    min_block = PARAMS["min_block_s"]
    blocks_ge3 = [(s, e) for s, e in merged if (e - s + 1) >= min_block]

    if blocks_ge3:
        durations = []
        z3_pcts = []
        for s, e in blocks_ge3:
            d = e - s + 1
            seg = hr[s:e + 1]
            z3_in = (seg > vt2).sum()
            durations.append(round(d / 60.0, 1))
            z3_pcts.append(round(100.0 * z3_in / d))

        # String (forensic)
        result["work_blocks_min"] = ";".join(str(x) for x in durations)
        result["work_blocks_z3pct"] = ";".join(str(x) for x in z3_pcts)
        # Aggregates (analytic)
        result["work_n_blocks"] = len(blocks_ge3)
        result["work_total_min"] = round(sum(durations), 1)
        result["work_longest_min"] = round(max(durations), 1)
        total_work_s = sum(e - s + 1 for s, e in blocks_ge3)
        total_z3_s = sum((hr[s:e+1] > vt2).sum() for s, e in blocks_ge3)
        result["work_avg_z3_pct"] = round(100.0 * total_z3_s / total_work_s) if total_work_s > 0 else 0
    else:
        result["work_blocks_min"] = ""
        result["work_blocks_z3pct"] = ""
        result["work_n_blocks"] = 0
        result["work_total_min"] = 0.0
        result["work_longest_min"] = 0.0
        result["work_avg_z3_pct"] = 0

    # ── Late intensity (Fix A: use moving mask) ──
    result["late_intensity"] = _compute_late_intensity(
        hr, duration_s, moving_mask)

    return result


def _compute_late_intensity(hr: np.ndarray, duration_s: float,
                            moving_mask: Optional[np.ndarray] = None) -> int:
    threshold = PARAMS["late_intensity_threshold_lpm"]
    min_dur = PARAMS["late_intensity_min_duration_s"]
    if duration_s < min_dur:
        return 0
    start_cut = 600 if duration_s >= 3600 else 0
    if start_cut >= len(hr):
        return 0

    hr_eff = hr[start_cut:]
    if moving_mask is not None:
        mm = moving_mask[start_cut:] if start_cut < len(moving_mask) else None
        if mm is not None and mm.sum() > 120:
            hr_eff = hr_eff[mm]

    valid = hr_eff[~np.isnan(hr_eff)]
    if len(valid) < 120:
        return 0
    mid = len(valid) // 2
    return 1 if (np.mean(valid[mid:]) - np.mean(valid[:mid])) >= threshold else 0


def compute_cardiac_drift(hr: np.ndarray, velocity: np.ndarray,
                          duration_s: float) -> Optional[float]:
    """Fix B: align lengths before processing."""
    min_dur = PARAMS["drift_min_duration_s"]
    min_speed = PARAMS["drift_min_speed_ms"]
    if duration_s < min_dur or velocity is None or len(velocity) == 0:
        return None

    # Fix B: align
    n = min(len(hr), len(velocity))
    hr = hr[:n]
    velocity = velocity[:n]

    start_cut = 600
    if start_cut >= n:
        return None
    hr_eff = hr[start_cut:]
    vel_eff = velocity[start_cut:]

    valid = (~np.isnan(hr_eff) & ~np.isnan(vel_eff)
             & (vel_eff > min_speed) & (hr_eff > 60))
    if valid.sum() < 120:
        return None

    hr_v = hr_eff[valid]
    vel_v = vel_eff[valid]
    mid = len(hr_v) // 2
    s1, s2 = vel_v[:mid].mean(), vel_v[mid:].mean()
    if s1 < min_speed or s2 < min_speed:
        return None
    eff1 = hr_v[:mid].mean() / s1
    eff2 = hr_v[mid:].mean() / s2
    return round(((eff2 - eff1) / eff1) * 100.0, 1)


# ─── Intensity classification ────────────────────────────────────────────────


def classify_intensity(sport: str, late_intensity: int,
                       work_total_min: float, work_avg_z3_pct: float) -> str:
    """
    Classify session intensity by WORK STRUCTURE (sustained blocks >VT1),
    not by raw Z3 exposure. Z3 exposure is captured separately by
    z3_total_min and z3_7d_sum for auditing.
    """
    if sport not in AEROBIC_SPORTS:
        return "NA"
    if work_total_min >= 10 and work_avg_z3_pct >= 15:
        return "work_intense"
    if work_total_min >= 20 and work_avg_z3_pct < 15:
        return "work_steady"
    if work_total_min >= 5:
        return "work_moderate"
    if late_intensity == 1:
        return "finish_strong"
    return "easy"


def classify_session_group(sport: str, intensity_cat: str) -> str:
    if sport == "strength":
        return "strength_unknown"
    if sport == "mobility":
        return "mobility"
    if sport not in AEROBIC_SPORTS:
        return "other"
    if intensity_cat == "work_intense":
        return "endurance_hard"
    if intensity_cat in ("work_steady", "work_moderate"):
        return "endurance_moderate"
    return "endurance_easy"


# ─── Notes ────────────────────────────────────────────────────────────────────


def extract_user_note(messages: list[dict]) -> str:
    user_msgs = []
    for m in messages:
        if m.get("type") != "TEXT":
            continue
        content = m.get("content", "")
        if len(content) > 500 and ("##" in content or "---" in content):
            continue
        user_msgs.append(content)
    if not user_msgs:
        return ""
    note = " | ".join(user_msgs)
    note = note.replace("\r\n", " | ").replace("\n", " | ").replace("\r", " | ")
    while " |  | " in note:
        note = note.replace(" |  | ", " | ")
    return note.strip()


# ─── Effort vs typical (dual mode) ───────────────────────────────────────────


def _elev_bin(ed):
    if pd.isna(ed):
        return "no_gps"
    if ed < 10:
        return "flat"
    if ed < 25:
        return "rolling"
    if ed < 50:
        return "mountain"
    return "steep_mountain"


def compute_effort_recent(df: pd.DataFrame) -> pd.Series:
    """
    Online/causal: rolling 60d percentiles by session_group, shift(1).
    Only uses past sessions in the same group.
    """
    min_prev = PARAMS["effort_min_prev_sessions"]
    window_days = PARAMS["effort_recent_window_days"]
    out = pd.Series("unknown", index=df.index, dtype="object")

    w = df.copy()
    w["_Fecha"] = pd.to_datetime(w["Fecha"])
    w = w.sort_values("_Fecha")

    for session_group, g in w.groupby("session_group", sort=False):
        if not isinstance(session_group, str) or not session_group.strip():
            continue
        indices = g.index.tolist()
        load_vals = pd.to_numeric(g["load"], errors="coerce").values
        fechas = g["_Fecha"].values

        for pos in range(len(indices)):
            idx = indices[pos]
            load = load_vals[pos]
            if np.isnan(load):
                continue

            # Get past sessions within window
            current_date = fechas[pos]
            cutoff = current_date - np.timedelta64(window_days, 'D')
            past_mask = (fechas[:pos] >= cutoff)
            past_load = load_vals[:pos][past_mask]

            if len(past_load) < min_prev:
                continue

            p25 = np.percentile(past_load, 25)
            p75 = np.percentile(past_load, 75)

            if load > p75:
                out.loc[idx] = "above"
            elif load < p25:
                out.loc[idx] = "below"
            else:
                out.loc[idx] = "typical"

    return out


def compute_effort_anchor(df: pd.DataFrame) -> pd.Series:
    """
    Anchor mode: percentiles fixed from a 'healthy' reference period
    in the same session_group.
    """
    anchor_start = PARAMS["effort_anchor_start"]
    anchor_end = PARAMS["effort_anchor_end"]
    min_n = PARAMS["effort_min_prev_sessions"]
    out = pd.Series("unknown", index=df.index, dtype="object")

    w = df.copy()
    w["_Fecha"] = pd.to_datetime(w["Fecha"])

    anchor_mask = (w["_Fecha"] >= anchor_start) & (w["_Fecha"] <= anchor_end)
    anchor_data = w[anchor_mask]

    for session_group, ref_group in anchor_data.groupby("session_group"):
        if not isinstance(session_group, str) or not session_group.strip():
            continue
        load_ref = pd.to_numeric(ref_group["load"], errors="coerce").dropna()
        if len(load_ref) < min_n:
            continue

        p25 = load_ref.quantile(0.25)
        p75 = load_ref.quantile(0.75)

        # Apply to all sessions in the same functional group
        all_in_group = w[w["session_group"] == session_group]
        for idx in all_in_group.index:
            load = pd.to_numeric(all_in_group.loc[idx, "load"], errors="coerce")
            if pd.isna(load):
                continue
            if load > p75:
                out.loc[idx] = "above"
            elif load < p25:
                out.loc[idx] = "below"
            else:
                out.loc[idx] = "typical"

    return out


# ─── Session builder ──────────────────────────────────────────────────────────


def build_session_row(activity: dict, client: IntervalsClient,
                      fetch_streams: bool = True,
                      fetch_notes: bool = True) -> dict:
    aid = activity["id"]
    sport_raw = activity.get("type", "Other")
    sport = SPORT_MAP.get(sport_raw, "other")
    is_aerobic = sport in AEROBIC_SPORTS

    # Fix C: VT zones with sport fallback
    hr_zones = activity.get("icu_hr_zones") or []
    fallback = VT_FALLBACK.get(sport, (143, 161))
    if len(hr_zones) >= 2:
        vt1, vt2 = hr_zones[0], hr_zones[1]
        zones_source = "icu"
    else:
        vt1, vt2 = fallback
        zones_source = "fallback"

    elapsed = activity.get("elapsed_time", 0)
    moving = activity.get("moving_time", elapsed)

    row = {
        "session_id": aid,
        "Fecha": activity["start_date_local"][:10],
        "start_time": activity["start_date_local"][11:16],
        "sport": sport,
        "sport_raw": sport_raw,
        "source": "intervals",
        "vt1_used": vt1,
        "vt2_used": vt2,
        "zones_source": zones_source,

        "duration_min": round(elapsed / 60.0, 1),
        "moving_min": round(moving / 60.0, 1),
        "distance_km": round((activity.get("distance") or 0) / 1000.0, 2),
        "elev_gain_m": activity.get("total_elevation_gain"),
        "elev_loss_m": activity.get("total_elevation_loss"),

        "hr_mean": activity.get("average_heartrate"),
        "hr_max": activity.get("max_heartrate"),

        "load": activity.get("icu_training_load"),
        "rpe": activity.get("icu_rpe") if (activity.get("icu_rpe") or 0) > 0 else None,
        "feel": activity.get("feel"),
    }

    # Elevation density
    gain, dist = row["elev_gain_m"], row["distance_km"]
    if gain is not None and dist and dist > 0.5:
        row["elev_density"] = round(gain / dist, 1)
    else:
        row["elev_density"] = None

    # Stream-derived
    if fetch_streams and is_aerobic:
        try:
            streams = client.get_streams(aid, "heartrate,velocity_smooth")
            hr_stream = streams.get("heartrate")
            vel_stream = streams.get("velocity_smooth")

            if hr_stream is not None and len(hr_stream) > 60:
                hr_derived = compute_hr_derived(
                    hr_stream, vt1, vt2, moving, velocity=vel_stream)
                row.update(hr_derived)

                # Fix 4: sampling rate canary
                if moving > 0:
                    row["stream_dt_est"] = round(moving / len(hr_stream), 3)

                if vel_stream is not None and len(vel_stream) > 0:
                    row["cardiac_drift_pct"] = compute_cardiac_drift(
                        hr_stream, vel_stream, moving)

        except Exception as e:
            log.warning(f"Stream error for {aid}: {e}")

    # Non-aerobic fallback zones from Intervals
    if not is_aerobic or "z1_pct" not in row:
        zone_times = activity.get("icu_hr_zone_times") or []
        if zone_times and sum(zone_times) > 0:
            total_zt = sum(zone_times)
            if len(zone_times) >= 3:
                row.setdefault("z1_pct", round(100.0 * zone_times[0] / total_zt, 1))
                row.setdefault("z2_pct", round(100.0 * zone_times[1] / total_zt, 1))
                row.setdefault("z3_pct", round(100.0 * zone_times[2] / total_zt, 1))
                row.setdefault("z2_total_min", round(zone_times[1] / 60.0, 1))
                row.setdefault("z3_total_min", round(zone_times[2] / 60.0, 1))

    # QA
    row["rpe_present"] = 1 if row.get("rpe") else 0
    row["notes_present"] = 0

    # Defaults
    for f in ["work_blocks_min", "work_blocks_z3pct"]:
        row.setdefault(f, "")
    for f in ["work_n_blocks", "work_total_min", "work_longest_min", "work_avg_z3_pct"]:
        row.setdefault(f, 0)

    # Intensity
    row["intensity_category"] = classify_intensity(
        sport,
        row.get("late_intensity", 0) or 0,
        row.get("work_total_min", 0) or 0,
        row.get("work_avg_z3_pct", 0) or 0,
    )
    row["session_group"] = classify_session_group(sport, row["intensity_category"])

    # Notes
    if fetch_notes:
        try:
            messages = client.get_activity_messages(aid)
            note = extract_user_note(messages)
            if note:
                row["notes_raw"] = note
                row["notes_present"] = 1
        except Exception as e:
            log.warning(f"Notes error for {aid}: {e}")

    # Pipeline version
    row["pipeline_version"] = PIPELINE_VERSION

    return row


# ─── Sessions day ─────────────────────────────────────────────────────────────


def build_sessions_day(sessions_df: pd.DataFrame) -> pd.DataFrame:
    df = sessions_df.copy()
    df["Fecha"] = pd.to_datetime(df["Fecha"])

    rows = []
    for fecha, group in df.groupby("Fecha"):
        aerobic = group[group["sport"].isin(AEROBIC_SPORTS)]
        strength = group[group["sport"] == "strength"]
        mobility = group[group["sport"] == "mobility"]
        has_aerobic_sessions = len(aerobic) > 0
        primary_session = group.copy()
        primary_session["_load_sort"] = pd.to_numeric(primary_session.get("load"), errors="coerce")
        primary_session["_duration_sort"] = pd.to_numeric(primary_session.get("duration_min"), errors="coerce")
        primary_session = primary_session.sort_values(
            ["_load_sort", "_duration_sort"],
            ascending=[False, False],
            na_position="last",
            kind="stable",
        )
        primary_intensity_cat = (
            primary_session.iloc[0]["intensity_category"]
            if len(primary_session) > 0 and "intensity_category" in primary_session.columns
            else None
        )

        # Aggregate work from pre-computed session aggregates (not string parsing)
        work_total_day = (
            round(aerobic["work_total_min"].sum(), 1)
            if has_aerobic_sessions and "work_total_min" in aerobic.columns and aerobic["work_total_min"].notna().any()
            else None
        )
        work_n_blocks_day = (
            int(aerobic["work_n_blocks"].sum())
            if has_aerobic_sessions and "work_n_blocks" in aerobic.columns and aerobic["work_n_blocks"].notna().any()
            else None
        )
        z3_min_day = (
            round(aerobic["z3_total_min"].sum(), 1)
            if has_aerobic_sessions and "z3_total_min" in aerobic.columns and aerobic["z3_total_min"].notna().any()
            else None
        )
        late_intensity_day = (
            1 if has_aerobic_sessions and "late_intensity" in aerobic.columns and (aerobic["late_intensity"] == 1).any()
            else (0 if has_aerobic_sessions else None)
        )

        row = {
            "Fecha": fecha.strftime("%Y-%m-%d"),
            "n_sessions": len(group),
            "total_duration_min": round(group["duration_min"].sum(), 1),
            "has_aerobic": 1 if has_aerobic_sessions else 0,
            "has_strength": 1 if len(strength) > 0 else 0,
            "has_mobility": 1 if len(mobility) > 0 else 0,

            "load_day": round(group["load"].sum(), 1) if group["load"].notna().any() else None,
            "intensity_cat_day": primary_intensity_cat if pd.notna(primary_intensity_cat) else None,
            "work_total_min_day": work_total_day,
            "work_n_blocks_day": work_n_blocks_day,
            "z3_min_day": z3_min_day,
            "hr_max_day": aerobic["hr_max"].max() if has_aerobic_sessions and aerobic["hr_max"].notna().any() else None,
            "hr_p95_max_day": aerobic["hr_p95"].max() if has_aerobic_sessions and "hr_p95" in aerobic.columns and aerobic["hr_p95"].notna().any() else None,
            "late_intensity_day": late_intensity_day,
            "cardiac_drift_worst": aerobic["cardiac_drift_pct"].max() if has_aerobic_sessions and "cardiac_drift_pct" in aerobic.columns and aerobic["cardiac_drift_pct"].notna().any() else None,

            "elev_gain_day": round(group["elev_gain_m"].sum(), 0) if group["elev_gain_m"].notna().any() else None,
            "elev_loss_day": round(group["elev_loss_m"].sum(), 0) if group["elev_loss_m"].notna().any() else None,
            "strength_min_day": round(strength["duration_min"].sum(), 1) if len(strength) > 0 else 0,
            "mobility_min_day": round(mobility["duration_min"].sum(), 1) if len(mobility) > 0 else 0,

            "rpe_max_day": int(aerobic["rpe"].max()) if has_aerobic_sessions and aerobic["rpe"].notna().any() else None,

            # Fix F: split effort aerobic/strength
            "effort_above_typical_aerobic": 1 if has_aerobic_sessions and (aerobic.get("effort_vs_recent", pd.Series(dtype=str)) == "above").any() else 0,
            "effort_above_typical_strength": 1 if len(strength) > 0 and (strength.get("effort_vs_recent", pd.Series(dtype=str)) == "above").any() else 0,
            "effort_above_anchor_aerobic": 1 if has_aerobic_sessions and (aerobic.get("effort_vs_anchor", pd.Series(dtype=str)) == "above").any() else 0,

            "n_with_rpe": int(group["rpe_present"].sum()),
            "n_with_notes": int(group["notes_present"].sum()),
        }

        # Elevation density day
        aero_ed = aerobic.dropna(subset=["elev_density", "distance_km"])
        if len(aero_ed) > 0 and aero_ed["distance_km"].sum() > 0:
            row["elev_density_day"] = round(
                (aero_ed["elev_density"] * aero_ed["distance_km"]).sum()
                / aero_ed["distance_km"].sum(), 1)
        else:
            row["elev_density_day"] = None

        rows.append(row)

    day_df = pd.DataFrame(rows)
    if day_df.empty:
        return day_df

    day_df["Fecha"] = pd.to_datetime(day_df["Fecha"])
    day_df = day_df.sort_values("Fecha").reset_index(drop=True)

    # ── Rolling with nobs (Fix E) ──
    day_df = day_df.set_index("Fecha")
    full_range = pd.date_range(day_df.index.min(), day_df.index.max(), freq="D")
    day_df = day_df.reindex(full_range)
    day_df.index.name = "Fecha"

    # Mark which days have real data
    has_data = day_df["n_sessions"].notna()

    # For rolling: use actual values where we have data, NaN otherwise
    # (NOT fillna(0) blindly — Fix E)
    def safe_rolling(series, window, shift_n=1):
        """
        Rolling sum with real metric coverage tracking.
        _nobs = days where this specific metric had a real value
                (NOT "days with any session" — that would mask missing streams).
        Fill NaN→0 only on days WITH sessions AFTER computing nobs.
        """
        # Step 1: nobs on raw data (before any fill)
        raw_shifted = series.shift(shift_n)
        roll_nobs = raw_shifted.notna().rolling(window, min_periods=1).sum()

        # Step 2: fill NaN→0 for days with sessions (for the sum)
        filled = series.copy()
        filled.loc[has_data & filled.isna()] = 0
        shifted = filled.shift(shift_n)
        roll_sum = shifted.rolling(window, min_periods=1).sum()

        return roll_sum.round(1), roll_nobs.astype("Int64")

    day_df["z3_7d_sum"], day_df["z3_7d_nobs"] = safe_rolling(day_df["z3_min_day"], 7)
    day_df["work_7d_sum"], day_df["work_7d_nobs"] = safe_rolling(day_df["work_total_min_day"], 7)
    day_df["finish_strong_7d_count"], _ = safe_rolling(day_df["late_intensity_day"], 7)
    day_df["load_3d"], day_df["load_3d_nobs"] = safe_rolling(day_df["load_day"], 3)
    day_df["load_7d"], day_df["load_7d_nobs"] = safe_rolling(day_df["load_day"], 7)
    day_df["load_14d"], day_df["load_14d_nobs"] = safe_rolling(day_df["load_day"], 14)
    day_df["load_28d"], day_df["load_28d_nobs"] = safe_rolling(day_df["load_day"], 28)

    if "elev_loss_day" in day_df:
        day_df["elev_loss_7d_sum"], _ = safe_rolling(day_df["elev_loss_day"], 7)

    # Drop filler days
    day_df = day_df.dropna(subset=["n_sessions"])
    day_df = day_df.reset_index()
    day_df["Fecha"] = day_df["Fecha"].dt.strftime("%Y-%m-%d")

    return day_df


# ─── Metadata ─────────────────────────────────────────────────────────────────


def write_metadata(output_dir: Path, oldest: str, newest: str,
                   n_sessions: int, n_days: int,
                   n_streams: int, n_notes: int,
                   dt_stats: Optional[dict] = None,
                   zones_dist: Optional[dict] = None):
    meta = {
        "pipeline_version": PIPELINE_VERSION,
        "params": PARAMS,
        "params_hash": params_hash(),
        "build_time": datetime.now().isoformat(),
        "input_range": {"oldest": oldest, "newest": newest},
        "counts": {
            "sessions": n_sessions,
            "days": n_days,
            "with_streams": n_streams,
            "with_notes": n_notes,
        },
    }
    if dt_stats:
        meta["stream_sampling"] = dt_stats
    if zones_dist:
        meta["zones_source_dist"] = zones_dist
    path = output_dir / "ENDURANCE_HRV_sessions_metadata.json"
    path.write_text(json.dumps(meta, indent=2, ensure_ascii=False))
    log.info(f"Metadata → {path}")


def warn_if_stream_sampling_suspicious(dt_stats: Optional[dict]) -> None:
    if not dt_stats:
        return
    if dt_stats.get("assumed_1hz", True):
        return
    log.warning(
        "Stream sampling canary outside ~1Hz; review stream_dt_est before "
        f"trusting stream-derived metrics (dt_mean={dt_stats['dt_mean']}, "
        f"dt_min={dt_stats['dt_min']}, dt_max={dt_stats['dt_max']})"
    )


NUMERIC_SESSION_COLS = [
    "duration_min",
    "moving_min",
    "distance_km",
    "elev_gain_m",
    "elev_loss_m",
    "elev_density",
    "hr_mean",
    "hr_max",
    "hr_p95",
    "z1_pct",
    "z2_pct",
    "z3_pct",
    "z2_total_min",
    "z3_total_min",
    "work_n_blocks",
    "work_total_min",
    "work_longest_min",
    "work_avg_z3_pct",
    "late_intensity",
    "cardiac_drift_pct",
    "load",
    "rpe",
    "rpe_present",
    "notes_present",
]


def coerce_numeric_session_cols(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    for col in NUMERIC_SESSION_COLS:
        if col in out.columns:
            out[col] = pd.to_numeric(out[col], errors="coerce")
    return out


def merge_sessions_incremental(new_df: pd.DataFrame, sessions_path: Path) -> pd.DataFrame:
    if sessions_path.exists():
        try:
            # Preserve literal enums like "NA"; numeric columns are coerced explicitly later.
            existing_df = pd.read_csv(sessions_path, keep_default_na=False)
            log.info(f"Loaded {len(existing_df)} existing sessions ← {sessions_path}")
        except Exception as e:
            log.warning(f"Could not read existing sessions ({sessions_path}): {e}")
            existing_df = pd.DataFrame()
    else:
        existing_df = pd.DataFrame()

    if existing_df.empty:
        merged = new_df.copy()
    else:
        merged = pd.concat([existing_df, new_df], ignore_index=True, sort=False)

    if "session_id" in merged.columns:
        sid = merged["session_id"].astype(str).str.strip()
        sid = sid.replace({"nan": "", "None": ""})
        merged["session_id"] = sid
        merged = merged[merged["session_id"] != ""].copy()

        before = len(merged)
        merged = merged.drop_duplicates(subset=["session_id"], keep="last")
        replaced = before - len(merged)
        if replaced:
            log.info(f"Replaced {replaced} duplicated sessions by session_id (upsert)")
    else:
        log.warning("session_id missing; falling back to row-level de-duplication")
        merged = merged.drop_duplicates(keep="last")

    if "Fecha" in merged.columns:
        merged["Fecha"] = pd.to_datetime(merged["Fecha"], errors="coerce").dt.strftime("%Y-%m-%d")
        bad_dates = int(merged["Fecha"].isna().sum())
        if bad_dates:
            log.warning(f"Dropping {bad_dates} rows with invalid Fecha")
            merged = merged.dropna(subset=["Fecha"]).copy()

    sort_cols = [c for c in ["Fecha", "start_time", "session_id"] if c in merged.columns]
    if sort_cols:
        merged = merged.sort_values(sort_cols, kind="stable").reset_index(drop=True)

    return merged


def resolve_update_oldest(output_dir: Path, fallback_oldest: str) -> str:
    candidates = [
        output_dir / "ENDURANCE_HRV_sessions_day.csv",
        output_dir / "ENDURANCE_HRV_sessions.csv",
    ]

    for csv_path in candidates:
        if not csv_path.exists():
            continue
        try:
            df = pd.read_csv(csv_path, usecols=["Fecha"], keep_default_na=False)
        except ValueError:
            log.warning(f"Fecha column missing in {csv_path}; skipping update anchor")
            continue
        except Exception as exc:
            log.warning(f"Could not read {csv_path} for update anchor: {exc}")
            continue

        fechas = pd.to_datetime(df["Fecha"], errors="coerce").dropna()
        if fechas.empty:
            continue

        last_day = fechas.max().date().isoformat()
        log.info(f"Update mode anchor: {last_day} ← {csv_path.name}")
        return last_day

    log.info(f"Update mode anchor not found; falling back to --oldest={fallback_oldest}")
    return fallback_oldest


# ─── Main pipeline ────────────────────────────────────────────────────────────


def run_pipeline(oldest: str, newest: str, output_dir: Path,
                 fetch_streams: bool = True, fetch_notes: bool = True):
    log.info(f"Pipeline {PIPELINE_VERSION} [{params_hash()}]")
    log.info(f"Range: {oldest} → {newest}")

    client = IntervalsClient(API_KEY, ATHLETE_ID)

    log.info("Fetching activities...")
    activities = client.get_activities(oldest, newest)
    log.info(f"Found {len(activities)} activities")
    if not activities:
        log.warning("No activities found!")
        return

    # Build sessions
    sessions = []
    for i, act in enumerate(activities):
        sport = SPORT_MAP.get(act.get("type", "Other"), "other")
        is_aerobic = sport in AEROBIC_SPORTS
        log.info(
            f"  [{i+1}/{len(activities)}] {act['id']} "
            f"{act['type']} {act['start_date_local'][:10]}"
            f"{' (+stream)' if fetch_streams and is_aerobic else ''}")

        row = build_session_row(act, client, fetch_streams, fetch_notes)
        sessions.append(row)

    new_df = pd.DataFrame(sessions)

    # Save sessions (incremental upsert by session_id)
    output_dir.mkdir(parents=True, exist_ok=True)
    sessions_path = output_dir / "ENDURANCE_HRV_sessions.csv"
    df = merge_sessions_incremental(new_df, sessions_path)
    df = coerce_numeric_session_cols(df)

    # Effort: dual mode (on full history to keep daily mode causal)
    log.info("Computing effort_vs_recent (online 60d)...")
    df["effort_vs_recent"] = compute_effort_recent(df)
    log.info("Computing effort_vs_anchor...")
    df["effort_vs_anchor"] = compute_effort_anchor(df)

    col_order = [
        "session_id", "Fecha", "start_time", "sport", "sport_raw",
        "source", "vt1_used", "vt2_used", "zones_source",
        "duration_min", "moving_min", "distance_km",
        "elev_gain_m", "elev_loss_m", "elev_density",
        "hr_mean", "hr_max", "hr_p95",
        "z1_pct", "z2_pct", "z3_pct", "z2_total_min", "z3_total_min",
        "work_n_blocks", "work_total_min", "work_longest_min",
        "work_avg_z3_pct", "work_blocks_min", "work_blocks_z3pct",
        "late_intensity", "cardiac_drift_pct",
        "load", "rpe", "feel",
        "intensity_category", "effort_vs_recent", "effort_vs_anchor",
        "session_group",
        "notes_raw", "rpe_present", "notes_present",
        "pipeline_version",
    ]
    col_order = [c for c in col_order if c in df.columns]
    extra = [c for c in df.columns if c not in col_order]
    df = df[col_order + extra]
    df.to_csv(sessions_path, index=False, quoting=1)
    log.info(f"Saved {len(df)} sessions (fetched {len(new_df)} this run) → {sessions_path}")

    # Sessions day
    day_df = build_sessions_day(df)
    day_path = output_dir / "ENDURANCE_HRV_sessions_day.csv"
    day_df.to_csv(day_path, index=False)
    log.info(f"Saved {len(day_df)} days → {day_path}")

    # Metadata — with sampling rate canary (Fix 4)
    n_streams_total = int(df["hr_p95"].notna().sum()) if "hr_p95" in df.columns else 0
    if "notes_present" in df.columns:
        n_notes_total = int(pd.to_numeric(df["notes_present"], errors="coerce").fillna(0).sum())
    else:
        n_notes_total = 0

    dt_stats = None
    if "stream_dt_est" in df.columns:
        dt_vals = df["stream_dt_est"].dropna()
        if len(dt_vals) > 0:
            dt_stats = {
                "n_streams": int(len(dt_vals)),
                "dt_mean": round(float(dt_vals.mean()), 4),
                "dt_min": round(float(dt_vals.min()), 4),
                "dt_max": round(float(dt_vals.max()), 4),
                "assumed_1hz": bool(dt_vals.max() < 1.1 and dt_vals.min() > 0.9),
            }
            warn_if_stream_sampling_suspicious(dt_stats)
    zones_dist = df["zones_source"].value_counts().to_dict() if "zones_source" in df.columns else None

    write_metadata(output_dir, oldest, newest, len(df), len(day_df),
                   n_streams_total, n_notes_total, dt_stats, zones_dist)

    # Summary
    log.info("─── Summary ───")
    log.info(f"  Sessions: {len(df)}, Days: {len(day_df)}")
    log.info(f"  Streams: {n_streams_total}, Notes: {n_notes_total}")
    if "zones_source" in df.columns:
        log.info(f"  zones_source: {df['zones_source'].value_counts().to_dict()}")
    if "effort_vs_recent" in df.columns:
        log.info(f"  effort_recent: {df['effort_vs_recent'].value_counts().to_dict()}")
    if "effort_vs_anchor" in df.columns:
        log.info(f"  effort_anchor: {df['effort_vs_anchor'].value_counts().to_dict()}")

    return df, day_df


# ─── CLI ──────────────────────────────────────────────────────────────────────


def main():
    parser = argparse.ArgumentParser(
        description=f"ENDURANCE HRV — Session pipeline {PIPELINE_VERSION}")
    parser.add_argument("--backfill", action="store_true")
    parser.add_argument("--daily", action="store_true")
    parser.add_argument("--update", action="store_true")
    parser.add_argument("--date", type=str)
    parser.add_argument("--oldest", type=str, default="2025-05-12")
    parser.add_argument(
        "--output",
        type=str,
        default=(os.environ.get("HRV_DATA_DIR") or "./data").strip() or "./data",
    )
    parser.add_argument("--no-streams", action="store_true")
    parser.add_argument("--no-notes", action="store_true")
    args = parser.parse_args()

    if not API_KEY or not ATHLETE_ID:
        log.error("Set INTERVALS_API_KEY and INTERVALS_ATHLETE_ID")
        sys.exit(1)

    today = date.today()
    output_dir = Path(args.output)
    selected_modes = int(bool(args.backfill)) + int(bool(args.daily)) + int(bool(args.update)) + int(bool(args.date))
    if selected_modes > 1:
        parser.error("Use only one range mode: --backfill, --daily, --update, or --date")

    if args.daily:
        oldest = (today - timedelta(days=2)).isoformat()
        newest = (today + timedelta(days=1)).isoformat()
    elif args.update:
        oldest = resolve_update_oldest(output_dir, args.oldest)
        newest = (today + timedelta(days=1)).isoformat()
    elif args.date:
        oldest = args.date
        newest = (datetime.strptime(args.date, "%Y-%m-%d").date()
                  + timedelta(days=1)).isoformat()
    else:
        oldest = args.oldest
        newest = (today + timedelta(days=1)).isoformat()

    run_pipeline(oldest, newest, output_dir,
                 fetch_streams=not args.no_streams,
                 fetch_notes=not args.no_notes)


if __name__ == "__main__":
    main()
