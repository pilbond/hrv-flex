"""Regression checks for research integrity; no production imports of research."""
import importlib.util
from pathlib import Path

import pandas as pd
import pytest


def load_script(name):
    path = Path(__file__).resolve().parents[1] / "research/experiments/hg04_replay/scripts" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


audit = load_script("review_audit")
extract = load_script("extract_rr")


def test_equal_change_counts_can_hide_disjoint_effects():
    a = pd.DataFrame({"gate_C": ["ROJO"], "gate_A": ["VERDE"]}, index=["2026-01-01"])
    b = pd.DataFrame({"gate_C": ["ROJO"], "gate_B": ["VERDE"]}, index=["2026-01-02"])
    assert audit.compare_changes(a, b, "A", "B")["changed_days"] == 2


def test_inconsistent_controls_rejected():
    a = pd.DataFrame({"gate_C": ["ROJO"], "gate_A": ["VERDE"]}, index=["2026-01-01"])
    b = pd.DataFrame({"gate_C": ["AMARILLO"], "gate_B": ["VERDE"]}, index=a.index)
    with pytest.raises(ValueError, match="Inconsistent control"):
        audit.compare_changes(a, b, "A", "B")


def test_parity_catches_auxiliary_values_and_missing_dates_columns():
    c = pd.DataFrame({"RMSSD_stable": [50.0, 51.0], "SD1": [40.77, 41.59]}, index=["2025-10-07", "2025-10-14"])
    p = pd.DataFrame({"RMSSD_stable": [50.0], "SD1": [float("nan")], "Notes": ["old"]}, index=["2025-10-07"])
    result = audit.compare_frames(c, p)
    assert not result["parity"]
    assert result["differing_dates_by_column"] == {"SD1": ["2025-10-07"]}
    assert result["only_control_dates"] == ["2025-10-14"]
    assert result["only_production_columns"] == ["Notes"]
    assert audit.compare_frames(c, c.copy())["parity"]


def test_duplicate_dates_rejected():
    c = pd.DataFrame({"value": [1, 2]}, index=["2025-10-07", "2025-10-07"])
    with pytest.raises(ValueError, match="duplicate"):
        audit.compare_frames(c, c)


def test_normalized_replay_copy_preserves_bytes_and_rejects_collision(tmp_path):
    name = extract.write_copy(tmp_path, "athlete_RR (1).CSV", b"duration,offline\n900,0\n")
    assert name == "athlete_RR.CSV"
    assert (tmp_path / name).read_bytes() == b"duration,offline\n900,0\n"
    with pytest.raises(ValueError, match="collision"):
        extract.write_copy(tmp_path, "athlete_RR (2).CSV", b"different")
