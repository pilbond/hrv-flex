"""Read-only comparison of pre-HG-10 FINAL with the active generation."""
from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd


def load_final(path: Path) -> pd.DataFrame:
    frame = pd.read_csv(path, dtype=str, keep_default_na=False, encoding="utf-8-sig")
    if frame["Fecha"].duplicated().any():
        raise ValueError(f"Duplicate dates in {path}")
    return frame.set_index("Fecha")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--before", type=Path, required=True)
    parser.add_argument("--after", type=Path, required=True)
    args = parser.parse_args()
    before = load_final(args.before)
    after = load_final(args.after)
    common = before.index.intersection(after.index)
    old, new = before.loc[common], after.loc[common]
    print(f"old={len(before)} new={len(after)} common={len(common)}")
    print("added=" + ",".join(after.index.difference(before.index)))
    print("lost=" + ",".join(before.index.difference(after.index)))
    for column in ("Calidad", "gate_final", "Action"):
        changed = old[column] != new[column]
        print(f"{column}_changed={changed.sum()}")
        transitions = pd.crosstab(old.loc[changed, column], new.loc[changed, column])
        print(transitions.to_string())
    quality_changed = old["Calidad"] != new["Calidad"]
    gate_changed = old["gate_final"] != new["gate_final"]
    action_changed = old["Action"] != new["Action"]
    print(f"quality_and_gate={(quality_changed & gate_changed).sum()}")
    print(f"gate_without_quality={(gate_changed & ~quality_changed).sum()}")
    print(f"action_without_gate={(action_changed & ~gate_changed).sum()}")
    promoted = (old["Action"] != "INTENSIDAD_OK") & (new["Action"] == "INTENSIDAD_OK")
    demoted = (old["Action"] == "INTENSIDAD_OK") & (new["Action"] != "INTENSIDAD_OK")
    invalid_promotions = promoted & ((new["gate_final"] != "VERDE") | (new["Calidad"] != "OK"))
    print(f"intensity_promoted={promoted.sum()} demoted={demoted.sum()} unsafe_promotions={invalid_promotions.sum()}")
    for days in (30, 90):
        recent = common[pd.to_datetime(common) >= pd.Timestamp("2026-11-03") - pd.Timedelta(days=days)]
        print(f"last_{days}d_gate={(old.loc[recent, 'gate_final'] != new.loc[recent, 'gate_final']).sum()}")
        print(f"last_{days}d_action={(old.loc[recent, 'Action'] != new.loc[recent, 'Action']).sum()}")


if __name__ == "__main__":
    main()
