"""HG-03: los huecos del archivo RR no se convierten en pares vecinos."""

from pathlib import Path

import numpy as np
import pytest

import build_hrv_core as core


def test_pair_diffs_ignore_a_discarded_rr_between_survivors():
    rr = np.array([1000.0, 1020.0, 1030.0, 1060.0])
    source_rows = np.array([0, 1, 3, 4])

    np.testing.assert_array_equal(core.rr_pair_diffs(rr, source_rows), [20.0, 30.0])
    assert np.sqrt(np.mean(core.rr_pair_diffs(rr, source_rows) ** 2)) == pytest.approx(25.49509757)
    np.testing.assert_array_equal(core.rr_pair_diffs(rr, np.arange(4)), [20.0, 10.0, 30.0])


def test_source_rows_survive_nan_offline_and_range_filters(tmp_path: Path):
    rr_path = tmp_path / "2026-01-01_RR.csv"
    rr_path.write_text(
        "duration,offline\n"
        "1000,0\n"
        ",0\n"
        "1000,0\n"
        "1000,1\n"
        "1000,0\n"
        "2500,0\n"
        "1000,0\n"
        "1000,0\n",
        encoding="utf-8",
    )
    constants = {**core.CONSTANTS, "TAIL_TRIM_S": 0.0}

    context = core._parse_and_filter_rr(rr_path, constants)

    np.testing.assert_array_equal(context.original_idx_eff, [0, 2, 4, 6, 7])
    assert not context.time_axis_reliable
    np.testing.assert_array_equal(
        core.rr_pair_diffs(context.rr_eff, context.original_idx_eff), [0.0]
    )
    assert context.N_off == 1
    assert context.N_oor == 1


def test_pair_diffs_reject_ambiguous_provenance():
    with pytest.raises(ValueError, match="crecientes"):
        core.rr_pair_diffs([1000, 1010], [3, 3])
    with pytest.raises(ValueError, match="igual longitud"):
        core.rr_pair_diffs([1000, 1010], [3])


def test_nonfinite_duration_marks_core_time_axis_unreliable(tmp_path: Path):
    rr_path = tmp_path / "2026-01-02_RR.csv"
    rr_path.write_text("duration,offline\n1000,0\ninf,0\n1020,0\n", encoding="utf-8")
    context = core._parse_and_filter_rr(rr_path, {**core.CONSTANTS, "TAIL_TRIM_S": 0.0})
    assert not context.time_axis_reliable
