#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
ECG.jsonl + ACC.jsonl -> RR compatible with Endurance pipeline.

Supported modes:
1) Single local pair:
   python egc_to_rr.py --ecg C:\\path\\ECG.jsonl --acc C:\\path\\ACC.jsonl --outdir data/rr_downloads

2) Batch local folder (auto-pair ECG/ACC by name):
   python egc_to_rr.py --input-dir C:\\path\\jsonl_folder --outdir data/rr_downloads

3) Google Drive folder (OAuth user auth + download + convert):
   python egc_to_rr.py --drive-folder-id <FOLDER_ID> --outdir data/rr_downloads --drive-client-secret credentials.json

4) Google Drive using predefined folder id:
   python egc_to_rr.py --outdir data/rr_downloads --dry-run

5) Web/server runtime (non-interactive, e.g. Railway):
   python egc_to_rr.py --drive-runtime web --outdir data/rr_downloads --dry-run

Outputs per session:
- <prefix>_<YYYY-MM-DD>_from_jsonl_RR.CSV                  (duration,offline)
- Aux files in <outdir>/_aux_jsonl by default:
  - <prefix>_<YYYY-MM-DD>_from_jsonl_RR_events.csv
  - <prefix>_<YYYY-MM-DD>_from_jsonl_resp_rate.csv
  - <prefix>_<YYYY-MM-DD>_from_jsonl_acc_motion_windows.csv

Main requirements:
- numpy, pandas, scipy
- Optional for Google Drive mode:
  google-auth, google-auth-oauthlib, google-api-python-client
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

import numpy as np
import pandas as pd

try:
    from scipy.signal import butter, filtfilt, find_peaks, welch
except Exception:
    SCIPY_AVAILABLE = False
    butter = filtfilt = find_peaks = welch = None
else:
    SCIPY_AVAILABLE = True

try:
    from google.oauth2.credentials import Credentials
    from google.oauth2 import service_account
    from google.auth.transport.requests import Request
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaIoBaseDownload
except Exception as exc:
    GOOGLE_DRIVE_AVAILABLE = False
    GOOGLE_DRIVE_IMPORT_ERROR = exc
    Credentials = service_account = Request = InstalledAppFlow = build = MediaIoBaseDownload = None
else:
    GOOGLE_DRIVE_AVAILABLE = True
    GOOGLE_DRIVE_IMPORT_ERROR = None


DRIVE_SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]
RR_MIN_MS = 300.0
RR_MAX_MS = 2000.0
DELTA_RR_MAX = 0.20
PREDEFINED_DRIVE_FOLDER_ID = "1ROd4GmALeNVQzwaMC48PWBH0zrAAlR-U"


@dataclass
class FileEntry:
    source: str
    name: str
    parent: str
    sort_key: float
    path: Optional[Path] = None
    drive_id: Optional[str] = None
    modified_time: str = ""


@dataclass
class PairEntry:
    key: str
    ecg: FileEntry
    acc: FileEntry


def require_scipy() -> None:
    if SCIPY_AVAILABLE:
        return
    raise RuntimeError(
        "Missing dependency: scipy. Install it before conversion.\n"
        "Suggested command: pip install scipy"
    )


def require_drive_libs() -> None:
    if GOOGLE_DRIVE_AVAILABLE:
        return
    raise RuntimeError(
        "Google Drive mode needs extra deps. Install:\n"
        "  pip install google-auth google-auth-oauthlib google-api-python-client\n"
        f"Import error detail: {GOOGLE_DRIVE_IMPORT_ERROR}"
    )


def get_default_drive_folder_id() -> str:
    env_override = (os.environ.get("ECG_RR_DRIVE_FOLDER_ID") or "").strip()
    if env_override:
        return env_override
    return PREDEFINED_DRIVE_FOLDER_ID


def iter_jsonl(path: Path) -> Iterable[dict]:
    with path.open("r", encoding="utf-8", errors="ignore") as handle:
        for line in handle:
            s = line.strip()
            if not s:
                continue
            yield json.loads(s)


def extract_ecg(ecg_jsonl: Path) -> Tuple[np.ndarray, np.ndarray, List[float], Optional[str]]:
    ts, v, phone_ts = [], [], []
    rec_name: Optional[str] = None

    for obj in iter_jsonl(ecg_jsonl):
        rec_name = rec_name or obj.get("recordingName")
        if "phoneTimestamp" in obj:
            try:
                phone_ts.append(float(obj["phoneTimestamp"]))
            except Exception:
                pass
        for row in obj.get("data", []):
            if isinstance(row, dict) and "timeStamp" in row and "voltage" in row:
                try:
                    ts.append(float(row["timeStamp"]))
                    v.append(float(row["voltage"]))
                except Exception:
                    pass

    if len(ts) < 200:
        raise ValueError(f"ECG has too few samples: {len(ts)}")
    return np.asarray(ts, float), np.asarray(v, float), phone_ts, rec_name


def extract_acc(acc_jsonl: Path) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, List[float], Optional[str]]:
    ts, x, y, z, phone_ts = [], [], [], [], []
    rec_name: Optional[str] = None

    for obj in iter_jsonl(acc_jsonl):
        rec_name = rec_name or obj.get("recordingName")
        if "phoneTimestamp" in obj:
            try:
                phone_ts.append(float(obj["phoneTimestamp"]))
            except Exception:
                pass
        for row in obj.get("data", []):
            if isinstance(row, dict) and all(k in row for k in ("timeStamp", "x", "y", "z")):
                try:
                    ts.append(float(row["timeStamp"]))
                    x.append(float(row["x"]))
                    y.append(float(row["y"]))
                    z.append(float(row["z"]))
                except Exception:
                    pass

    if len(ts) < 50:
        raise ValueError(f"ACC has too few samples: {len(ts)}")
    return (
        np.asarray(ts, float),
        np.asarray(x, float),
        np.asarray(y, float),
        np.asarray(z, float),
        phone_ts,
        rec_name,
    )


def normalize_ts_seconds(ts_raw: np.ndarray) -> Tuple[np.ndarray, str]:
    med = float(np.median(ts_raw))
    if med > 1e17:
        return ts_raw / 1e9, "ns"
    if med > 1e14:
        return ts_raw / 1e6, "us"
    if med > 1e11:
        return ts_raw / 1e3, "ms"
    return ts_raw, "s"


def sort_unique(ts_s: np.ndarray, *arrs: np.ndarray) -> Tuple[np.ndarray, ...]:
    order = np.argsort(ts_s)
    ts_s_sorted = ts_s[order]
    arrs_sorted = [arr[order] for arr in arrs]
    keep = np.insert(np.diff(ts_s_sorted) > 0, 0, True)
    ts_s_sorted = ts_s_sorted[keep]
    arrs_sorted = [arr[keep] for arr in arrs_sorted]
    return (ts_s_sorted, *arrs_sorted)


def fs_est(ts_s: np.ndarray) -> float:
    dt = np.diff(ts_s)
    if dt.size == 0:
        raise ValueError("Cannot estimate sampling frequency (no deltas).")
    return 1.0 / float(np.median(dt))


def integrate_area(y: np.ndarray, x: np.ndarray) -> float:
    if hasattr(np, "trapezoid"):
        return float(np.trapezoid(y, x))
    return float(np.trapz(y, x))


def bandpass(x: np.ndarray, fs: float, lo: float, hi: float, order: int = 2) -> np.ndarray:
    require_scipy()
    ny = fs / 2.0
    lo_n = max(lo / ny, 1e-6)
    hi_n = min(hi / ny, 0.99)
    b, a = butter(order, [lo_n, hi_n], btype="bandpass")
    return filtfilt(b, a, x)


def lowpass(x: np.ndarray, fs: float, hi: float, order: int = 2) -> np.ndarray:
    require_scipy()
    ny = fs / 2.0
    hi_n = min(hi / ny, 0.99)
    b, a = butter(order, hi_n, btype="lowpass")
    return filtfilt(b, a, x)


def detect_rpeaks(ts_s: np.ndarray, ecg: np.ndarray) -> Tuple[np.ndarray, float]:
    require_scipy()
    fs = fs_est(ts_s)
    ecg_f = bandpass(ecg, fs, 5.0, 20.0)

    diff_sig = np.diff(ecg_f, prepend=ecg_f[0])
    sq = diff_sig ** 2
    win = max(1, int(round(0.150 * fs)))
    mwi = np.convolve(sq, np.ones(win) / win, mode="same")

    med = np.median(mwi)
    mad = np.median(np.abs(mwi - med)) * 1.4826
    thr = med + 3.0 * mad

    min_dist = int(round(0.35 * fs))
    peaks, _ = find_peaks(mwi, height=thr, distance=min_dist)
    if len(peaks) < 20:
        raise ValueError("Too few R-peaks detected.")

    # Merge peaks too close (<450ms), keep strongest.
    final: List[int] = []
    i = 0
    while i < len(peaks):
        group = [int(peaks[i])]
        j = i
        while j + 1 < len(peaks) and (ts_s[peaks[j + 1]] - ts_s[peaks[j]]) < 0.45:
            group.append(int(peaks[j + 1]))
            j += 1
        best = max(group, key=lambda idx: mwi[idx])
        final.append(int(best))
        i = j + 1

    final_unique = np.asarray(sorted(set(final)), dtype=int)
    return final_unique, fs


def rr_events(
    ts_s: np.ndarray,
    peaks: np.ndarray,
    rr_min_ms: float = RR_MIN_MS,
    rr_max_ms: float = RR_MAX_MS,
    delta_rel_max: float = DELTA_RR_MAX,
) -> pd.DataFrame:
    r = ts_s[peaks]
    rr = np.diff(r) * 1000.0
    t_center = ((r[:-1] + r[1:]) / 2.0) - r[0]

    offline = np.zeros(rr.shape, dtype=int)
    reason = np.array(["OK"] * len(rr), dtype=object)

    bad_range = (rr < rr_min_ms) | (rr > rr_max_ms)
    offline[bad_range] = 1
    reason[bad_range] = "RR_OUT_OF_RANGE"

    if len(rr) >= 2:
        rel = np.abs(np.diff(rr)) / np.maximum(rr[:-1], 1e-9)
        bad_delta = np.zeros_like(rr, dtype=bool)
        bad_delta[1:] = rel > delta_rel_max
        mark = bad_delta & (offline == 0)
        offline[mark] = 1
        reason[mark] = "DELTA_RR_GT_20P"

    return pd.DataFrame(
        {
            "t_center_s": np.round(t_center, 3),
            "duration_ms": np.round(rr, 3),
            "offline": offline.astype(int),
            "reason": reason,
        }
    )


def acc_high_motion_windows(
    ts_s: np.ndarray,
    x: np.ndarray,
    y: np.ndarray,
    z: np.ndarray,
    win_s: float = 5.0,
    step_s: float = 1.0,
    k_mad: float = 3.0,
    posture_lp_hz: float = 0.30,
) -> Tuple[pd.DataFrame, float]:
    fs = fs_est(ts_s)
    gx = lowpass(x, fs, posture_lp_hz)
    gy = lowpass(y, fs, posture_lp_hz)
    gz = lowpass(z, fs, posture_lp_hz)

    dx, dy, dz = x - gx, y - gy, z - gz
    dyn = np.sqrt(dx * dx + dy * dy + dz * dz)

    t0 = ts_s[0]
    rows = []
    cur = ts_s[0]
    end = ts_s[-1]
    while cur + win_s <= end:
        m = (ts_s >= cur) & (ts_s < cur + win_s)
        seg = dyn[m]
        if seg.size:
            rows.append(
                {
                    "t_start_s": float(cur - t0),
                    "t_end_s": float(cur + win_s - t0),
                    "rms_dyn": float(np.sqrt(np.mean(seg ** 2))),
                }
            )
        cur += step_s

    df = pd.DataFrame(rows)
    if df.empty:
        return df, float("nan")

    med = float(df["rms_dyn"].median())
    mad = float(np.median(np.abs(df["rms_dyn"].to_numpy() - med)) * 1.4826)
    thr = med + k_mad * mad
    df["high_motion_flag"] = (df["rms_dyn"] > thr).astype(int)
    return df, float(thr)


def gate_rr_by_acc(rr_ev: pd.DataFrame, acc_win: pd.DataFrame) -> pd.DataFrame:
    if rr_ev.empty or acc_win.empty:
        return rr_ev
    high = acc_win.loc[acc_win["high_motion_flag"] == 1, ["t_start_s", "t_end_s"]].to_numpy(float)
    if high.size == 0:
        return rr_ev

    t = rr_ev["t_center_s"].to_numpy(float)
    gate = np.zeros_like(t, dtype=bool)
    for start, end in high:
        gate |= (t >= start) & (t <= end)

    out = rr_ev.copy()
    m = gate & (out["offline"].to_numpy() == 0)
    out.loc[m, "offline"] = 1
    out.loc[m, "reason"] = "ACC_HIGH_MOTION"
    return out


def resp_rate_from_acc(
    ts_s: np.ndarray,
    x: np.ndarray,
    y: np.ndarray,
    z: np.ndarray,
    win_s: float = 30.0,
    step_s: float = 5.0,
    lo: float = 0.08,
    hi: float = 0.60,
) -> pd.DataFrame:
    require_scipy()
    fs = fs_est(ts_s)
    t0 = ts_s[0]
    mag = np.sqrt(x * x + y * y + z * z)
    sigs = {"x": x, "y": y, "z": z, "mag": mag}

    rows = []
    cur = ts_s[0]
    end = ts_s[-1]
    while cur + win_s <= end:
        m = (ts_s >= cur) & (ts_s < cur + win_s)
        if np.sum(m) < int(0.7 * win_s * fs):
            cur += step_s
            continue

        best = None
        for axis, sig in sigs.items():
            seg = sig[m]
            seg_f = bandpass(seg, fs, lo, hi)
            nper = min(len(seg_f), max(64, int(fs * 20)))
            f, p = welch(seg_f, fs=fs, nperseg=nper)
            band = (f >= lo) & (f <= hi)
            fb, pb = f[band], p[band]
            if pb.size == 0:
                continue
            pk = int(np.argmax(pb))
            peak_hz = float(fb[pk])
            conf = float(pb[pk] / (np.median(pb) + 1e-12))
            band_power = integrate_area(pb, fb)
            cand = (band_power, axis, peak_hz, conf)
            if best is None or cand[0] > best[0]:
                best = cand

        if best:
            _, axis, peak_hz, conf = best
            rows.append(
                {
                    "t_center_s": float(cur + win_s / 2 - t0),
                    "resp_rate_bpm": float(peak_hz * 60.0),
                    "confidence": float(conf),
                    "axis": axis,
                }
            )
        cur += step_s

    return pd.DataFrame(rows)


def infer_session_date(
    phone_ts_ecg: List[float],
    phone_ts_acc: List[float],
    rec_name: Optional[str],
) -> Tuple[str, Optional[datetime]]:
    pts = None
    if phone_ts_ecg:
        pts = min(phone_ts_ecg)
    elif phone_ts_acc:
        pts = min(phone_ts_acc)

    if pts is not None:
        dt = datetime.fromtimestamp(float(pts) / 1000.0, tz=timezone.utc)
        return dt.strftime("%Y-%m-%d"), dt

    if isinstance(rec_name, str):
        m = re.search(r"(\d{8})_(\d{6})", rec_name)
        if m:
            dt = datetime.strptime(m.group(1) + m.group(2), "%Y%m%d%H%M%S").replace(tzinfo=timezone.utc)
            return dt.strftime("%Y-%m-%d"), dt

    return "1970-01-01", None


def sanitize_fragment(text: str, max_len: int = 40) -> str:
    out = re.sub(r"[^A-Za-z0-9_\-]+", "_", str(text))
    out = re.sub(r"_+", "_", out).strip("_")
    if not out:
        out = "session"
    return out[:max_len]


def unique_output_stem(outdir: Path, stem: str) -> str:
    candidate = stem
    idx = 2
    while (outdir / f"{candidate}_RR.CSV").exists():
        candidate = f"{stem}_v{idx}"
        idx += 1
    return candidate


def validate_rr_df(rr_csv: pd.DataFrame) -> Dict[str, object]:
    issues: List[str] = []

    expected_cols = ["duration", "offline"]
    if list(rr_csv.columns) != expected_cols:
        issues.append(f"Invalid columns. Expected {expected_cols}, got {list(rr_csv.columns)}")

    if rr_csv.empty:
        issues.append("RR is empty")

    duration = pd.to_numeric(rr_csv.get("duration"), errors="coerce")
    offline = pd.to_numeric(rr_csv.get("offline"), errors="coerce")

    if duration.isna().any():
        issues.append("duration has NaN/non-numeric values")
    if offline.isna().any():
        issues.append("offline has NaN/non-numeric values")
    if (duration <= 0).any():
        issues.append("duration has non-positive values")
    if (~offline.isin([0, 1])).any():
        issues.append("offline must be 0/1")

    offline_pct = float((offline == 1).mean() * 100.0) if len(offline) else float("nan")
    out_of_range_count = int(((duration < RR_MIN_MS) | (duration > RR_MAX_MS)).sum())

    return {
        "ok": len(issues) == 0,
        "issues": issues,
        "rows": int(len(rr_csv)),
        "offline_pct": offline_pct,
        "out_of_range_count": out_of_range_count,
    }


def process_pair(
    ecg_path: Path,
    acc_path: Path,
    outdir: Path,
    aux_dir: Optional[Path] = None,
    prefix: str = "ENDURANCE",
    use_acc_gate: bool = False,
    write_aux: bool = True,
    session_tag: str = "",
) -> Dict[str, object]:
    ts_ecg_raw, ecg, phone_ecg, rec_ecg = extract_ecg(ecg_path)
    ts_acc_raw, ax, ay, az, phone_acc, rec_acc = extract_acc(acc_path)

    ts_ecg, _ = normalize_ts_seconds(ts_ecg_raw)
    ts_acc, _ = normalize_ts_seconds(ts_acc_raw)

    ts_ecg, ecg = sort_unique(ts_ecg, ecg)
    ts_acc, ax, ay, az = sort_unique(ts_acc, ax, ay, az)

    rec = rec_ecg or rec_acc
    date_str, dt = infer_session_date(phone_ecg, phone_acc, rec)

    peaks, fs_ecg = detect_rpeaks(ts_ecg, ecg)
    rr_ev = rr_events(ts_ecg, peaks)

    acc_win, motion_thr = acc_high_motion_windows(ts_acc, ax, ay, az)
    if use_acc_gate:
        rr_ev = gate_rr_by_acc(rr_ev, acc_win)

    rr_csv = pd.DataFrame({"duration": rr_ev["duration_ms"], "offline": rr_ev["offline"]}).round(3)
    rr_check = validate_rr_df(rr_csv)
    if not rr_check["ok"]:
        raise ValueError(f"RR validation failed: {rr_check['issues']}")

    resp = resp_rate_from_acc(ts_acc, ax, ay, az)

    stem_base = f"{sanitize_fragment(prefix, 18)}_{date_str}_from_jsonl"
    stem = unique_output_stem(outdir, stem_base)

    rr_path = outdir / f"{stem}_RR.CSV"
    aux_base = aux_dir if aux_dir is not None else outdir
    rr_events_path = aux_base / f"{stem}_RR_events.csv"
    acc_motion_path = aux_base / f"{stem}_acc_motion_windows.csv"
    resp_path = aux_base / f"{stem}_resp_rate.csv"

    rr_csv.to_csv(rr_path, index=False)
    if write_aux:
        rr_ev.to_csv(rr_events_path, index=False)
        acc_win.to_csv(acc_motion_path, index=False)
        resp.to_csv(resp_path, index=False)

    return {
        "rr_path": rr_path,
        "rr_events_path": rr_events_path if write_aux else None,
        "acc_motion_path": acc_motion_path if write_aux else None,
        "resp_path": resp_path if write_aux else None,
        "date_str": date_str,
        "dt": dt.isoformat() if dt else None,
        "offline_count": int((rr_csv["offline"] == 1).sum()),
        "rr_count": int(len(rr_csv)),
        "fs_ecg": float(fs_ecg),
        "fs_acc": float(fs_est(ts_acc)),
        "motion_thr": float(motion_thr) if np.isfinite(motion_thr) else float("nan"),
    }


def _drive_modified_ts(value: str) -> float:
    if not value:
        return 0.0
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
    except Exception:
        return 0.0


def resolve_drive_runtime(runtime: str) -> str:
    if runtime in {"local", "web"}:
        return runtime
    web_markers = [
        "RAILWAY_ENVIRONMENT",
        "RAILWAY_PROJECT_ID",
        "K_SERVICE",
        "CI",
        "GITHUB_ACTIONS",
    ]
    return "web" if any((os.environ.get(k) or "").strip() for k in web_markers) else "local"


def _load_service_account_credentials(service_account_path: Path):
    env_json = (os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON") or "").strip()
    if env_json:
        try:
            info = json.loads(env_json)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid GOOGLE_SERVICE_ACCOUNT_JSON: {exc}") from exc
        creds = service_account.Credentials.from_service_account_info(info, scopes=DRIVE_SCOPES)
        return creds, "env:GOOGLE_SERVICE_ACCOUNT_JSON"

    env_file = (os.environ.get("GOOGLE_APPLICATION_CREDENTIALS") or "").strip()
    if env_file:
        p = Path(env_file)
        if p.exists():
            creds = service_account.Credentials.from_service_account_file(str(p), scopes=DRIVE_SCOPES)
            return creds, f"file:{p}"

    if service_account_path.exists():
        creds = service_account.Credentials.from_service_account_file(str(service_account_path), scopes=DRIVE_SCOPES)
        return creds, f"file:{service_account_path}"

    return None, ""


def _load_oauth_token_credentials(token_path: Path):
    env_token_json = (os.environ.get("GOOGLE_OAUTH_TOKEN_JSON") or "").strip()
    if env_token_json:
        try:
            token_info = json.loads(env_token_json)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid GOOGLE_OAUTH_TOKEN_JSON: {exc}") from exc
        creds = Credentials.from_authorized_user_info(token_info, DRIVE_SCOPES)
        return creds, "env:GOOGLE_OAUTH_TOKEN_JSON", False

    if token_path.exists():
        creds = Credentials.from_authorized_user_file(str(token_path), DRIVE_SCOPES)
        return creds, f"file:{token_path}", True

    return None, "", False


def _build_oauth_flow(client_secret: Path):
    env_client_json = (os.environ.get("GOOGLE_OAUTH_CLIENT_SECRET_JSON") or "").strip()
    if env_client_json:
        try:
            client_config = json.loads(env_client_json)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid GOOGLE_OAUTH_CLIENT_SECRET_JSON: {exc}") from exc
        return InstalledAppFlow.from_client_config(client_config, DRIVE_SCOPES), "env:GOOGLE_OAUTH_CLIENT_SECRET_JSON"

    if not client_secret.exists():
        raise FileNotFoundError(f"Google OAuth client secret not found: {client_secret}")
    return InstalledAppFlow.from_client_secrets_file(str(client_secret), DRIVE_SCOPES), f"file:{client_secret}"


def get_drive_service(
    client_secret: Path,
    token_path: Path,
    auth_mode: str = "local_server",
    runtime: str = "auto",
    service_account_path: Optional[Path] = None,
):
    require_drive_libs()
    resolved_runtime = resolve_drive_runtime(runtime)
    service_account_path = service_account_path or Path("service_account.json")

    # Web mode: prefer non-interactive auth (service account first).
    if resolved_runtime == "web":
        sa_creds, sa_source = _load_service_account_credentials(service_account_path)
        if sa_creds is not None:
            print(f"[INFO] Drive auth=service_account source={sa_source}")
            return build("drive", "v3", credentials=sa_creds, cache_discovery=False)

    creds, token_source, can_persist_token = _load_oauth_token_credentials(token_path)
    if creds and creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
            if can_persist_token:
                token_path.parent.mkdir(parents=True, exist_ok=True)
                token_path.write_text(creds.to_json(), encoding="utf-8")
        except Exception as exc:
            if resolved_runtime == "web":
                raise RuntimeError(
                    "Web runtime cannot refresh OAuth token automatically. "
                    "Provide valid token or service account credentials."
                ) from exc

    if creds and creds.valid:
        print(f"[INFO] Drive auth=oauth_token source={token_source}")
        return build("drive", "v3", credentials=creds, cache_discovery=False)

    # Local mode fallback: allow service account if available.
    if resolved_runtime == "local":
        sa_creds, sa_source = _load_service_account_credentials(service_account_path)
        if sa_creds is not None:
            print(f"[INFO] Drive auth=service_account source={sa_source}")
            return build("drive", "v3", credentials=sa_creds, cache_discovery=False)

    # Local mode: interactive OAuth.
    if resolved_runtime == "local":
        flow, flow_source = _build_oauth_flow(client_secret)
        if auth_mode == "console":
            creds = flow.run_console()
        else:
            creds = flow.run_local_server(port=0)
        token_path.parent.mkdir(parents=True, exist_ok=True)
        token_path.write_text(creds.to_json(), encoding="utf-8")
        print(f"[INFO] Drive auth=oauth_interactive source={flow_source}")
        return build("drive", "v3", credentials=creds, cache_discovery=False)

    raise RuntimeError(
        "Web runtime requires non-interactive credentials. "
        "Use one of: GOOGLE_SERVICE_ACCOUNT_JSON, "
        "GOOGLE_APPLICATION_CREDENTIALS/service_account.json, or GOOGLE_OAUTH_TOKEN_JSON/tokens.json."
    )


def list_drive_jsonl_files(service, folder_id: str, recursive: bool = True) -> List[FileEntry]:
    files: List[FileEntry] = []
    queue: List[Tuple[str, str]] = [(folder_id, ".")]
    visited: set = set()

    while queue:
        current_id, display_parent = queue.pop(0)
        if current_id in visited:
            continue
        visited.add(current_id)

        page_token = None
        while True:
            query = f"'{current_id}' in parents and trashed = false"
            resp = (
                service.files()
                .list(
                    q=query,
                    fields="nextPageToken, files(id,name,mimeType,modifiedTime,parents)",
                    pageToken=page_token,
                    pageSize=1000,
                    supportsAllDrives=True,
                    includeItemsFromAllDrives=True,
                )
                .execute()
            )
            for item in resp.get("files", []):
                name = item.get("name", "")
                mime = item.get("mimeType", "")
                file_id = item.get("id", "")
                mtime = item.get("modifiedTime", "")

                if mime == "application/vnd.google-apps.folder":
                    if recursive:
                        sub_parent = f"{display_parent}/{name}" if display_parent != "." else name
                        queue.append((file_id, sub_parent))
                    continue

                if not name.lower().endswith(".jsonl"):
                    continue

                files.append(
                    FileEntry(
                        source="drive",
                        name=name,
                        parent=display_parent,
                        sort_key=_drive_modified_ts(mtime),
                        path=None,
                        drive_id=file_id,
                        modified_time=mtime,
                    )
                )

            page_token = resp.get("nextPageToken")
            if not page_token:
                break

    return files


def download_drive_file(service, file_entry: FileEntry, download_dir: Path) -> Path:
    if not file_entry.drive_id:
        raise ValueError("Drive file entry missing drive_id.")

    safe_name = sanitize_fragment(file_entry.name, 80)
    local_name = f"{file_entry.drive_id[:10]}_{safe_name}.jsonl"
    dest = download_dir / local_name

    request = service.files().get_media(fileId=file_entry.drive_id, supportsAllDrives=True)
    with dest.open("wb") as fh:
        downloader = MediaIoBaseDownload(fh, request)
        done = False
        while not done:
            _, done = downloader.next_chunk()
    return dest


def collect_local_jsonl_files(input_dir: Path, recursive: bool = True) -> List[FileEntry]:
    pattern = "**/*.jsonl" if recursive else "*.jsonl"
    files: List[FileEntry] = []
    for path in sorted(input_dir.glob(pattern)):
        if not path.is_file():
            continue
        parent = "."
        try:
            rel_parent = path.parent.relative_to(input_dir)
            parent = "." if str(rel_parent) == "." else str(rel_parent).replace("\\", "/")
        except Exception:
            parent = str(path.parent).replace("\\", "/")
        files.append(
            FileEntry(
                source="local",
                name=path.name,
                parent=parent,
                sort_key=path.stat().st_mtime,
                path=path,
            )
        )
    return files


def detect_sensor_and_key(file_name: str) -> Tuple[Optional[str], Optional[str]]:
    stem = Path(file_name).stem.lower()
    has_ecg = "ecg" in stem
    has_acc = "acc" in stem
    if has_ecg and not has_acc:
        sensor = "ecg"
    elif has_acc and not has_ecg:
        sensor = "acc"
    elif has_ecg and has_acc:
        return None, None
    else:
        return None, None

    key = re.sub(r"(ecg|acc)", "", stem, flags=re.IGNORECASE)
    key = re.sub(r"[^a-z0-9]+", "", key)
    if not key:
        key = "default"
    return sensor, key


def build_pairs(files: List[FileEntry]) -> List[PairEntry]:
    grouped: Dict[Tuple[str, str], Dict[str, List[FileEntry]]] = defaultdict(lambda: {"ecg": [], "acc": []})

    for file_entry in files:
        sensor, key = detect_sensor_and_key(file_entry.name)
        if sensor is None or key is None:
            continue
        grouped[(file_entry.parent, key)][sensor].append(file_entry)

    pairs: List[PairEntry] = []
    for (parent, key), bucket in grouped.items():
        ecg_list = sorted(bucket["ecg"], key=lambda x: (x.sort_key, x.name))
        acc_list = sorted(bucket["acc"], key=lambda x: (x.sort_key, x.name))
        if not ecg_list or not acc_list:
            continue

        n = min(len(ecg_list), len(acc_list))
        for idx in range(n):
            pair_key = f"{parent}::{key}" if n == 1 else f"{parent}::{key}#{idx+1}"
            pairs.append(PairEntry(key=pair_key, ecg=ecg_list[idx], acc=acc_list[idx]))

        if len(ecg_list) != len(acc_list):
            print(
                f"[WARN] Unbalanced files for pair {parent}::{key} "
                f"(ECG={len(ecg_list)}, ACC={len(acc_list)}). Using first {n}."
            )

    return sorted(pairs, key=lambda p: p.key)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Convert ECG/ACC JSONL to RR CSV compatible with Endurance."
    )
    parser.add_argument("--ecg", help="Single ECG.jsonl local path")
    parser.add_argument("--acc", help="Single ACC.jsonl local path")
    parser.add_argument("--input-dir", help="Local folder with JSONL files to pair and process")
    parser.add_argument("--input-recursive", action="store_true", help="Scan local input-dir recursively")

    parser.add_argument(
        "--drive-folder-id",
        default="",
        help=(
            "Google Drive folder id containing ECG/ACC JSONL files. "
            "If omitted and no local mode is selected, predefined folder id is used."
        ),
    )
    parser.add_argument(
        "--drive-runtime",
        choices=["auto", "local", "web"],
        default="auto",
        help=(
            "Runtime profile for Drive auth. "
            "'local' allows interactive OAuth login, "
            "'web' disables interactive login (Railway/server), "
            "'auto' detects environment."
        ),
    )
    parser.add_argument("--drive-client-secret", default="credentials.json")
    parser.add_argument("--drive-token-path", default="tokens.json")
    parser.add_argument(
        "--drive-service-account",
        default="service_account.json",
        help="Service account JSON file (used mainly in web runtime).",
    )
    parser.add_argument(
        "--drive-auth-mode",
        choices=["local_server", "console"],
        default="local_server",
        help="Interactive OAuth flow mode for local runtime.",
    )
    parser.add_argument("--drive-download-dir", default="", help="Keep downloaded drive JSONL files in this folder")
    parser.add_argument("--drive-recursive", action="store_true", help="Traverse subfolders in Drive input folder")

    parser.add_argument("--outdir", required=True, help="Output folder for RR files")
    parser.add_argument(
        "--aux-subdir",
        default="_aux_jsonl",
        help="Subfolder inside outdir for auxiliary files (RR_events/resp/acc_motion).",
    )
    parser.add_argument("--prefix", default="ENDURANCE", help="Output filename prefix")
    parser.add_argument("--pair-limit", type=int, default=0, help="Max number of pairs to process (0 = all)")
    parser.add_argument("--use-acc-gate", action="store_true", help="Mark RR as offline on ACC high-motion windows")
    parser.add_argument("--no-aux", action="store_true", help="Do not write RR_events/resp/acc_motion side files")
    parser.add_argument("--dry-run", action="store_true", help="Only list pairs; do not convert")
    return parser.parse_args()


def resolve_mode(args: argparse.Namespace) -> str:
    single_mode = bool(args.ecg or args.acc)
    local_mode = bool(args.input_dir)
    drive_mode = bool((args.drive_folder_id or "").strip())
    selected = int(single_mode) + int(local_mode) + int(drive_mode)

    if selected == 0:
        default_drive_id = get_default_drive_folder_id()
        if default_drive_id:
            args.drive_folder_id = default_drive_id
            return "drive_batch"
        raise ValueError("Choose one source mode: --ecg/--acc, or --input-dir, or --drive-folder-id.")
    if selected > 1:
        raise ValueError("Use only one source mode at a time.")
    if single_mode and (not args.ecg or not args.acc):
        raise ValueError("Single mode requires both --ecg and --acc.")
    if single_mode:
        return "single"
    if local_mode:
        return "local_batch"
    return "drive_batch"


def print_pairs_preview(pairs: List[PairEntry]) -> None:
    print(f"[INFO] Candidate pairs: {len(pairs)}")
    for i, pair in enumerate(pairs, start=1):
        ecg_name = pair.ecg.name
        acc_name = pair.acc.name
        print(f"  [{i}] {pair.key}")
        print(f"      ECG: {ecg_name}")
        print(f"      ACC: {acc_name}")


def main() -> None:
    args = parse_args()
    drive_folder_cli = (args.drive_folder_id or "").strip()
    mode = resolve_mode(args)

    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    write_aux = not args.no_aux
    aux_dir: Optional[Path] = None
    if write_aux:
        aux_subdir = (args.aux_subdir or "").strip()
        if aux_subdir:
            aux_dir = outdir / aux_subdir
            aux_dir.mkdir(parents=True, exist_ok=True)
        else:
            aux_dir = outdir

    if not args.dry_run:
        require_scipy()

    pairs: List[PairEntry]
    drive_service = None
    download_dir: Optional[Path] = None
    temp_drive_download_dir: Optional[Path] = None

    if mode == "single":
        ecg_path = Path(args.ecg)
        acc_path = Path(args.acc)
        if not ecg_path.exists():
            raise FileNotFoundError(f"ECG file not found: {ecg_path}")
        if not acc_path.exists():
            raise FileNotFoundError(f"ACC file not found: {acc_path}")
        pairs = [
            PairEntry(
                key="single",
                ecg=FileEntry(source="local", name=ecg_path.name, parent=".", sort_key=0.0, path=ecg_path),
                acc=FileEntry(source="local", name=acc_path.name, parent=".", sort_key=0.0, path=acc_path),
            )
        ]
    elif mode == "local_batch":
        input_dir = Path(args.input_dir)
        if not input_dir.exists():
            raise FileNotFoundError(f"Input dir not found: {input_dir}")
        local_files = collect_local_jsonl_files(input_dir, recursive=args.input_recursive)
        pairs = build_pairs(local_files)
    else:
        if drive_folder_cli:
            print(f"[INFO] Using Drive folder id from CLI: {args.drive_folder_id}")
        else:
            print(f"[INFO] Using predefined Drive folder id: {args.drive_folder_id}")
        print(f"[INFO] Drive runtime requested: {args.drive_runtime}")
        client_secret = Path(args.drive_client_secret)
        token_path = Path(args.drive_token_path)
        service_account_path = Path(args.drive_service_account)
        drive_service = get_drive_service(
            client_secret=client_secret,
            token_path=token_path,
            auth_mode=args.drive_auth_mode,
            runtime=args.drive_runtime,
            service_account_path=service_account_path,
        )
        drive_files = list_drive_jsonl_files(drive_service, args.drive_folder_id, recursive=args.drive_recursive)
        pairs = build_pairs(drive_files)

        if not args.dry_run:
            if args.drive_download_dir:
                download_dir = Path(args.drive_download_dir)
                download_dir.mkdir(parents=True, exist_ok=True)
            else:
                # Avoid OS temp permission issues by keeping transient downloads in workspace.
                run_tag = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")
                download_dir = outdir / "_drive_tmp" / run_tag
                download_dir.mkdir(parents=True, exist_ok=True)
                temp_drive_download_dir = download_dir

    if not pairs:
        raise ValueError("No ECG/ACC pairs found.")

    if args.pair_limit > 0:
        pairs = pairs[: args.pair_limit]

    print_pairs_preview(pairs)
    if args.dry_run:
        print("[DRY-RUN] No files converted.")
        return

    ok = 0
    failed = 0
    try:
        for idx, pair in enumerate(pairs, start=1):
            try:
                if mode == "drive_batch":
                    assert drive_service is not None
                    assert download_dir is not None
                    ecg_local = download_drive_file(drive_service, pair.ecg, download_dir)
                    acc_local = download_drive_file(drive_service, pair.acc, download_dir)
                else:
                    assert pair.ecg.path is not None
                    assert pair.acc.path is not None
                    ecg_local = pair.ecg.path
                    acc_local = pair.acc.path

                result = process_pair(
                    ecg_path=ecg_local,
                    acc_path=acc_local,
                    outdir=outdir,
                    aux_dir=aux_dir,
                    prefix=args.prefix,
                    use_acc_gate=args.use_acc_gate,
                    write_aux=write_aux,
                    session_tag=pair.key,
                )
                ok += 1
                print(
                    f"[OK {idx}/{len(pairs)}] {result['rr_path'].name} "
                    f"(offline={result['offline_count']}/{result['rr_count']})"
                )
            except Exception as exc:
                failed += 1
                print(f"[FAIL {idx}/{len(pairs)}] {pair.key}: {exc}")
    finally:
        if temp_drive_download_dir is not None:
            try:
                shutil.rmtree(temp_drive_download_dir, ignore_errors=True)
                parent = temp_drive_download_dir.parent
                # Legacy cleanup: previous versions stored downloaded jsonl directly in _drive_tmp.
                if parent.exists():
                    for legacy_file in parent.glob("*.jsonl"):
                        try:
                            legacy_file.unlink()
                        except OSError:
                            pass
                if parent.exists() and not any(parent.iterdir()):
                    try:
                        parent.rmdir()
                    except OSError:
                        # Non-critical (e.g. OneDrive lock): files are already removed.
                        pass
            except Exception as exc:
                print(f"[WARN] Could not cleanup temporary drive files: {exc}")

    print(
        f"[SUMMARY] processed={len(pairs)} ok={ok} failed={failed} "
        f"outdir={outdir}"
    )
    if failed > 0:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
