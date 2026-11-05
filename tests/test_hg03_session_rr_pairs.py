"""Local session RMSSD keeps the physical RR CSV row numbers."""

import numpy as np
import pandas as pd
import pytest

from analysis.endurance_rr_session_v4 import build_rmssd_windows_v4, load_rr_csv, rmssd_ms


def test_session_rmssd_excludes_bridge_across_discarded_row():
    rr = np.array([1000.0, 1020.0, 1030.0, 1060.0])
    lines = np.array([2, 3, 5, 6])
    assert rmssd_ms(rr, lines) == pytest.approx(np.sqrt((20**2 + 30**2) / 2))
    assert rmssd_ms(rr, np.array([2, 3, 4, 5])) != rmssd_ms(rr, lines)
    assert np.isnan(rmssd_ms(rr[:2], lines[:2]))


def test_session_window_uses_original_lines_for_pairs():
    rr_df = pd.DataFrame(
        {
            "end_s": [1.0, 2.0, 3.0, 4.0, 5.0],
            "duration_ms": [1000.0, 1020.0, 900.0, 1030.0, 1060.0],
            "line_no": [2, 3, 4, 5, 6],
            "accepted_core": [True, True, False, True, True],
            "accepted_strict": [True, True, False, True, True],
        }
    )
    windows, _, _ = build_rmssd_windows_v4(rr_df, 60, 0.5, 3, 1)
    assert windows.loc[0, "rmssd_ms"] == pytest.approx(25.495098)
    assert bool(windows.loc[0, "usable"])


@pytest.mark.parametrize("bad", ["", "nan", "inf", "-inf"])
def test_bad_duration_breaks_provenance_and_compromises_time_axis(tmp_path, bad):
    path = tmp_path / "session_rr.csv"
    path.write_text(
        "duration,offline\n1000,0\n1020,0\n"
        f"{bad},0\n1030,0\n1060,0\n",
        encoding="utf-8",
    )
    rr_df, qa = load_rr_csv(path)
    assert rr_df["line_no"].tolist() == [2, 3, 5, 6]
    assert qa.bad_duration_rows == 1
    assert qa.time_axis_trust == "COMPROMISED_BAD_DURATION_ROWS"
    assert rmssd_ms(rr_df["duration_ms"].to_numpy(), rr_df["line_no"].to_numpy()) == pytest.approx(
        np.sqrt((20**2 + 30**2) / 2)
    )
    rr_df["end_s"] = np.cumsum(rr_df["duration_ms"]) / 1000.0
    rr_df["accepted_core"] = True
    rr_df["accepted_strict"] = True
    windows, _, _ = build_rmssd_windows_v4(rr_df, 60, 0.5, 3, 1, time_axis_trusted=False)
    assert not bool(windows.loc[0, "usable"])
    assert windows.loc[0, "reason"] == "time_axis_compromised"
