#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = Path(os.environ.get("HRV_DATA_DIR", ROOT / "data"))
DEFAULT_OUT_DIR = ROOT / "analysis" / "reports" / "hrv_rebound_profile"

F_FINAL = DATA_DIR / "ENDURANCE_HRV_master_FINAL.csv"
F_CORE = DATA_DIR / "ENDURANCE_HRV_master_CORE.csv"
F_SLEEP = DATA_DIR / "ENDURANCE_HRV_sleep.csv"
F_SESSIONS = DATA_DIR / "ENDURANCE_HRV_sessions.csv"
F_SESSIONS_DAY = DATA_DIR / "ENDURANCE_HRV_sessions_day.csv"


@dataclass(frozen=True)
class ReboundConfig:
    acwr_event_threshold: float = 1.25
    high_relative_min_load: float = 60.0
    baseline_days: int = 7
    baseline_min_ok_days: int = 5
    swc_multiplier: float = 0.5
    d1_floor_z: float = -0.5
    d3_floor_z: float = -0.5
    overshoot_z: float = 1.0
    soft_sleep_min_minutes: float = 420.0


def robust_sd(values: pd.Series | np.ndarray | list[float]) -> float:
    arr = pd.to_numeric(pd.Series(values), errors="coerce").dropna().to_numpy(dtype=float)
    if arr.size < 2:
        return float("nan")
    med = float(np.median(arr))
    mad = float(np.median(np.abs(arr - med)))
    return 1.4826 * mad


def classify_rebound(z_d1: float | None, z_d3: float | None, hard_invalid: bool, overshoot_z: float, floor_z_d1: float, floor_z_d3: float) -> str:
    if hard_invalid or z_d1 is None or z_d3 is None or not math.isfinite(z_d1) or not math.isfinite(z_d3):
        return "no_interpretable"
    if z_d3 > overshoot_z:
        return "sobrerrebote"
    if z_d1 >= floor_z_d1 and z_d3 >= floor_z_d3:
        return "rebote_rapido"
    if z_d1 < floor_z_d1 and z_d3 >= floor_z_d3:
        return "rebote_lento_absorbido"
    if z_d3 < floor_z_d3:
        return "rebote_incompleto_d3"
    return "no_interpretable"


def _load_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"Missing required file: {path}")
    return pd.read_csv(path)


def _normalize_date_column(df: pd.DataFrame, column: str = "Fecha") -> pd.DataFrame:
    out = df.copy()
    out[column] = pd.to_datetime(out[column], errors="coerce").dt.normalize()
    out = out.dropna(subset=[column]).sort_values(column, kind="stable").reset_index(drop=True)
    return out


def _bool_series(df: pd.DataFrame, column: str) -> pd.Series:
    if column not in df.columns:
        return pd.Series(False, index=df.index)
    return df[column].fillna(False).astype(str).str.strip().str.lower().isin({"1", "true", "yes"})


def _numeric_series(df: pd.DataFrame, column: str, default: float = 0.0) -> pd.Series:
    if column not in df.columns:
        return pd.Series(default, index=df.index, dtype=float)
    return pd.to_numeric(df[column], errors="coerce").fillna(default)


def _build_daily_base(final_df: pd.DataFrame, core_df: pd.DataFrame, sessions_day_df: pd.DataFrame, sleep_df: pd.DataFrame) -> pd.DataFrame:
    final_df = _normalize_date_column(final_df)
    core_df = _normalize_date_column(core_df)
    sessions_day_df = _normalize_date_column(sessions_day_df)
    sleep_df = _normalize_date_column(sleep_df)

    final_cols = [
        "Fecha",
        "Calidad",
        "lnRMSSD_today",
        "ln_base60",
        "SWC_ln",
        "gate_badge",
        "Action",
        "reason_text",
    ]
    core_cols = ["Fecha", "lnRMSSD", "Flags"]
    day_cols = [
        "Fecha",
        "n_sessions",
        "has_aerobic",
        "has_strength",
        "load_day",
        "intense_day",
        "acwr_simple_prev",
        "monotony_7d_prev",
        "strain_7d_prev",
        "load_ctx_ready",
    ]
    sleep_cols = ["Fecha", "polar_sleep_duration_min", "polar_sleep_score"]

    merged = final_df[[c for c in final_cols if c in final_df.columns]].copy()
    merged = merged.merge(core_df[[c for c in core_cols if c in core_df.columns]], on="Fecha", how="left", suffixes=("", "_core"))
    merged = merged.merge(sessions_day_df[[c for c in day_cols if c in sessions_day_df.columns]], on="Fecha", how="left")
    merged = merged.merge(sleep_df[[c for c in sleep_cols if c in sleep_df.columns]], on="Fecha", how="left")

    merged["Calidad"] = merged.get("Calidad", pd.Series("", index=merged.index)).fillna("").astype(str)
    merged["quality_ok"] = merged["Calidad"].eq("OK")
    merged["load_ctx_ready_bool"] = _bool_series(merged, "load_ctx_ready")
    merged["intense_day_bool"] = _numeric_series(merged, "intense_day", default=0.0).astype(int).gt(0)
    merged["has_aerobic_bool"] = _numeric_series(merged, "has_aerobic", default=0.0).astype(int).gt(0)
    merged["has_strength_bool"] = _numeric_series(merged, "has_strength", default=0.0).astype(int).gt(0)
    return merged


def _build_session_lookup(sessions_df: pd.DataFrame) -> pd.DataFrame:
    sessions_df = _normalize_date_column(sessions_df)
    cols = ["Fecha", "session_id", "sport", "load", "work_total_min"]
    work = sessions_df[[c for c in cols if c in sessions_df.columns]].copy()
    if work.empty:
        return pd.DataFrame(columns=["Fecha", "session_ids", "sports", "session_count"])

    agg = (
        work.groupby("Fecha", dropna=False)
        .agg(
            session_ids=("session_id", lambda s: "|".join(sorted({str(v).strip() for v in s if str(v).strip()}))),
            sports=("sport", lambda s: "|".join(sorted({str(v).strip() for v in s if str(v).strip()}))),
            session_count=("session_id", "count"),
        )
        .reset_index()
    )
    return agg


def build_rebound_events(
    final_df: pd.DataFrame,
    core_df: pd.DataFrame,
    sessions_day_df: pd.DataFrame,
    sessions_df: pd.DataFrame,
    sleep_df: pd.DataFrame,
    cfg: ReboundConfig,
) -> pd.DataFrame:
    daily = _build_daily_base(final_df, core_df, sessions_day_df, sleep_df)
    session_lookup = _build_session_lookup(sessions_df)
    daily = daily.merge(session_lookup, on="Fecha", how="left")

    acwr = pd.to_numeric(daily.get("acwr_simple_prev"), errors="coerce")
    load_day = pd.to_numeric(daily.get("load_day"), errors="coerce")
    sports_text = daily.get("sports", pd.Series("", index=daily.index)).fillna("").astype(str).str.strip().str.lower()
    strength_only_day = (daily["has_strength_bool"] & ~daily["has_aerobic_bool"]) | sports_text.eq("strength")
    high_relative_load = (
        daily["load_ctx_ready_bool"]
        & acwr.ge(cfg.acwr_event_threshold)
        & load_day.ge(cfg.high_relative_min_load)
        & ~strength_only_day
    )
    eligible_origin = daily["intense_day_bool"] | high_relative_load

    daily["eligible_origin"] = eligible_origin
    daily["origin_reason"] = np.select(
        [
            daily["intense_day_bool"] & high_relative_load,
            daily["intense_day_bool"],
            high_relative_load,
        ],
        [
            "intense_day+high_relative_load",
            "intense_day",
            "high_relative_load",
        ],
        default="",
    )

    eligible_positions = daily.index[daily["eligible_origin"]].tolist()
    records: list[dict[str, Any]] = []
    for pos in eligible_positions:
        row = daily.iloc[pos]
        current_date = row["Fecha"]
        prior_rows = daily.iloc[:pos] if pos > 0 else daily.iloc[0:0]
        baseline_ok = prior_rows.loc[prior_rows["quality_ok"], "lnRMSSD_today"].tail(cfg.baseline_days)
        baseline_pre = float(np.median(baseline_ok)) if len(baseline_ok) >= cfg.baseline_min_ok_days else float("nan")
        swc_pre = cfg.swc_multiplier * robust_sd(baseline_ok) if len(baseline_ok) >= cfg.baseline_min_ok_days else float("nan")

        baseline_source = "pre7_ok"
        if not (math.isfinite(baseline_pre) and math.isfinite(swc_pre) and swc_pre > 0):
            base60 = pd.to_numeric(pd.Series([row.get("ln_base60")]), errors="coerce").iloc[0]
            swc_ln = pd.to_numeric(pd.Series([row.get("SWC_ln")]), errors="coerce").iloc[0]
            if math.isfinite(base60) and math.isfinite(swc_ln) and swc_ln > 0:
                baseline_pre = float(base60)
                swc_pre = float(swc_ln)
                baseline_source = "base60_fallback"
            else:
                baseline_source = "insufficient"

        prev_relevant = bool(pos > 0 and bool(daily.iloc[pos - 1]["eligible_origin"]))
        origin_scope = "short_block" if prev_relevant else "session_day"

        d1_pos = pos + 1
        d3_pos = pos + 3
        d1_row = daily.iloc[d1_pos] if d1_pos < len(daily) else None
        d3_row = daily.iloc[d3_pos] if d3_pos < len(daily) else None

        d1_hard_invalid = d1_row is None or not bool(d1_row["quality_ok"]) or not math.isfinite(pd.to_numeric(pd.Series([d1_row.get("lnRMSSD_today")]), errors="coerce").iloc[0])
        contamination_future = False
        contamination_dates: list[str] = []
        for future_pos in (pos + 1, pos + 2):
            if future_pos < len(daily) and bool(daily.iloc[future_pos]["eligible_origin"]):
                contamination_future = True
                contamination_dates.append(daily.iloc[future_pos]["Fecha"].date().isoformat())
        d3_missing_or_bad = d3_row is None or not bool(d3_row["quality_ok"]) or not math.isfinite(pd.to_numeric(pd.Series([d3_row.get("lnRMSSD_today")]), errors="coerce").iloc[0])
        d3_hard_invalid = d3_missing_or_bad or contamination_future

        d1_ln = None if d1_row is None else pd.to_numeric(pd.Series([d1_row.get("lnRMSSD_today")]), errors="coerce").iloc[0]
        d3_ln = None if d3_row is None else pd.to_numeric(pd.Series([d3_row.get("lnRMSSD_today")]), errors="coerce").iloc[0]
        delta_d1 = float(d1_ln - baseline_pre) if math.isfinite(baseline_pre) and d1_ln is not None and math.isfinite(d1_ln) else None
        delta_d3 = float(d3_ln - baseline_pre) if math.isfinite(baseline_pre) and d3_ln is not None and math.isfinite(d3_ln) else None
        z_d1 = float(delta_d1 / swc_pre) if delta_d1 is not None and math.isfinite(swc_pre) and swc_pre > 0 else None
        z_d3 = float(delta_d3 / swc_pre) if delta_d3 is not None and math.isfinite(swc_pre) and swc_pre > 0 else None

        soft_flags: list[str] = []
        for target_row, prefix in ((d1_row, "d1"), (d3_row, "d3")):
            if target_row is None:
                continue
            sleep_min = pd.to_numeric(pd.Series([target_row.get("polar_sleep_duration_min")]), errors="coerce").iloc[0]
            if math.isfinite(sleep_min) and sleep_min < cfg.soft_sleep_min_minutes:
                soft_flags.append(f"{prefix}_short_sleep")
            sleep_score = pd.to_numeric(pd.Series([target_row.get("polar_sleep_score")]), errors="coerce").iloc[0]
            if math.isfinite(sleep_score) and sleep_score < 70:
                soft_flags.append(f"{prefix}_low_sleep_score")

        hard_invalid = d1_hard_invalid or d3_hard_invalid or baseline_source == "insufficient"
        classification = classify_rebound(
            z_d1=z_d1,
            z_d3=z_d3,
            hard_invalid=hard_invalid,
            overshoot_z=cfg.overshoot_z,
            floor_z_d1=cfg.d1_floor_z,
            floor_z_d3=cfg.d3_floor_z,
        )

        record = {
            "origin_date": current_date.date().isoformat(),
            "origin_scope": origin_scope,
            "origin_reason": row.get("origin_reason") or "",
            "session_ids": row.get("session_ids") or "",
            "sports": row.get("sports") or "",
            "session_count": int(pd.to_numeric(pd.Series([row.get("session_count")]), errors="coerce").fillna(0).iloc[0]),
            "n_sessions_day": int(pd.to_numeric(pd.Series([row.get("n_sessions")]), errors="coerce").fillna(0).iloc[0]),
            "load_day": pd.to_numeric(pd.Series([row.get("load_day")]), errors="coerce").iloc[0],
            "intense_day": bool(row.get("intense_day_bool")),
            "acwr_simple_prev": acwr.iloc[pos] if pos < len(acwr) else np.nan,
            "monotony_7d_prev": pd.to_numeric(pd.Series([row.get("monotony_7d_prev")]), errors="coerce").iloc[0],
            "strain_7d_prev": pd.to_numeric(pd.Series([row.get("strain_7d_prev")]), errors="coerce").iloc[0],
            "load_ctx_ready": bool(row.get("load_ctx_ready_bool")),
            "baseline_pre": baseline_pre,
            "swc_pre": swc_pre,
            "baseline_source": baseline_source,
            "baseline_n_ok_days": int(len(baseline_ok)),
            "baseline_window_start": prior_rows.loc[prior_rows["quality_ok"], "Fecha"].tail(cfg.baseline_days).min().date().isoformat() if not baseline_ok.empty else "",
            "baseline_window_end": prior_rows.loc[prior_rows["quality_ok"], "Fecha"].tail(cfg.baseline_days).max().date().isoformat() if not baseline_ok.empty else "",
            "d1_date": d1_row["Fecha"].date().isoformat() if d1_row is not None else "",
            "d1_quality_ok": False if d1_row is None else bool(d1_row["quality_ok"]),
            "d1_lnrmssd_today": d1_ln,
            "delta_d1": delta_d1,
            "z_d1": z_d1,
            "d3_date": d3_row["Fecha"].date().isoformat() if d3_row is not None else "",
            "d3_quality_ok": False if d3_row is None else bool(d3_row["quality_ok"]),
            "d3_lnrmssd_today": d3_ln,
            "delta_d3": delta_d3,
            "z_d3": z_d3,
            "d1_hard_invalid": bool(d1_hard_invalid),
            "d3_hard_invalid": bool(d3_hard_invalid),
            "d3_contamination_dates": "|".join(contamination_dates),
            "soft_flags": "|".join(soft_flags),
            "classification": classification,
            "hard_invalid": bool(hard_invalid),
            "interpretability": "soft_caution" if soft_flags and not hard_invalid else ("hard_invalid" if hard_invalid else "clean"),
        }
        records.append(record)

    out = pd.DataFrame.from_records(records)
    if out.empty:
        return out
    return out.sort_values("origin_date", kind="stable").reset_index(drop=True)


def build_weekly_summary(events_df: pd.DataFrame) -> pd.DataFrame:
    if events_df.empty:
        return pd.DataFrame(
            columns=[
                "week_start",
                "week_end",
                "n_events",
                "n_interpretable",
                "n_clean",
                "n_rebote_rapido",
                "n_rebote_lento_absorbido",
                "n_rebote_incompleto_d3",
                "n_sobrerrebote",
                "median_z_d1",
                "median_z_d3",
            ]
        )

    work = events_df.copy()
    work["origin_date_dt"] = pd.to_datetime(work["origin_date"], errors="coerce")
    work["week_start_dt"] = work["origin_date_dt"] - pd.to_timedelta(work["origin_date_dt"].dt.weekday, unit="D")
    work["week_end_dt"] = work["week_start_dt"] + pd.Timedelta(days=6)
    grouped = work.groupby("week_start_dt", dropna=False)

    rows: list[dict[str, Any]] = []
    for week_start, group in grouped:
        rows.append(
            {
                "week_start": week_start.date().isoformat(),
                "week_end": (week_start + pd.Timedelta(days=6)).date().isoformat(),
                "n_events": int(len(group)),
                "n_interpretable": int((~group["hard_invalid"]).sum()),
                "n_clean": int(group["interpretability"].eq("clean").sum()),
                "n_rebote_rapido": int(group["classification"].eq("rebote_rapido").sum()),
                "n_rebote_lento_absorbido": int(group["classification"].eq("rebote_lento_absorbido").sum()),
                "n_rebote_incompleto_d3": int(group["classification"].eq("rebote_incompleto_d3").sum()),
                "n_sobrerrebote": int(group["classification"].eq("sobrerrebote").sum()),
                "median_z_d1": pd.to_numeric(group["z_d1"], errors="coerce").median(),
                "median_z_d3": pd.to_numeric(group["z_d3"], errors="coerce").median(),
            }
        )
    return pd.DataFrame(rows).sort_values("week_start", kind="stable").reset_index(drop=True)


def build_summary_payload(events_df: pd.DataFrame, weekly_df: pd.DataFrame, cfg: ReboundConfig) -> dict[str, Any]:
    classification_counts = {}
    if not events_df.empty:
        classification_counts = {
            str(k): int(v)
            for k, v in events_df["classification"].value_counts(dropna=False).to_dict().items()
        }
    return {
        "generated_at": datetime.now().isoformat(),
        "config": {
            "acwr_event_threshold": cfg.acwr_event_threshold,
            "high_relative_min_load": cfg.high_relative_min_load,
            "baseline_days": cfg.baseline_days,
            "baseline_min_ok_days": cfg.baseline_min_ok_days,
            "swc_multiplier": cfg.swc_multiplier,
            "d1_floor_z": cfg.d1_floor_z,
            "d3_floor_z": cfg.d3_floor_z,
            "overshoot_z": cfg.overshoot_z,
            "soft_sleep_min_minutes": cfg.soft_sleep_min_minutes,
        },
        "counts": {
            "n_events": int(len(events_df)),
            "n_weeks": int(len(weekly_df)),
            "n_interpretable": int((~events_df["hard_invalid"]).sum()) if not events_df.empty else 0,
            "n_clean": int(events_df["interpretability"].eq("clean").sum()) if not events_df.empty else 0,
            "n_soft_caution": int(events_df["interpretability"].eq("soft_caution").sum()) if not events_df.empty else 0,
        },
        "classification_counts": classification_counts,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build SYA-16 HRV rebound sidecar artifacts.")
    parser.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR))
    parser.add_argument("--acwr-event-threshold", type=float, default=1.25)
    parser.add_argument("--high-relative-min-load", type=float, default=60.0)
    parser.add_argument("--baseline-days", type=int, default=7)
    parser.add_argument("--baseline-min-ok-days", type=int, default=5)
    parser.add_argument("--swc-multiplier", type=float, default=0.5)
    parser.add_argument("--d1-floor-z", type=float, default=-0.5)
    parser.add_argument("--d3-floor-z", type=float, default=-0.5)
    parser.add_argument("--overshoot-z", type=float, default=1.0)
    parser.add_argument("--soft-sleep-min-minutes", type=float, default=420.0)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    cfg = ReboundConfig(
        acwr_event_threshold=args.acwr_event_threshold,
        high_relative_min_load=args.high_relative_min_load,
        baseline_days=args.baseline_days,
        baseline_min_ok_days=args.baseline_min_ok_days,
        swc_multiplier=args.swc_multiplier,
        d1_floor_z=args.d1_floor_z,
        d3_floor_z=args.d3_floor_z,
        overshoot_z=args.overshoot_z,
        soft_sleep_min_minutes=args.soft_sleep_min_minutes,
    )

    events_df = build_rebound_events(
        final_df=_load_csv(F_FINAL),
        core_df=_load_csv(F_CORE),
        sessions_day_df=_load_csv(F_SESSIONS_DAY),
        sessions_df=_load_csv(F_SESSIONS),
        sleep_df=_load_csv(F_SLEEP),
        cfg=cfg,
    )
    weekly_df = build_weekly_summary(events_df)
    summary = build_summary_payload(events_df, weekly_df, cfg)

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    events_path = out_dir / "hrv_rebound_profile_events.csv"
    weekly_path = out_dir / "hrv_rebound_profile_weekly.csv"
    summary_path = out_dir / "hrv_rebound_profile_summary.json"

    events_df.to_csv(events_path, index=False)
    weekly_df.to_csv(weekly_path, index=False)
    summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")

    print(json.dumps({"events_csv": str(events_path), "weekly_csv": str(weekly_path), "summary_json": str(summary_path)}, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
