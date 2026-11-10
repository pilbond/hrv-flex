"""Incremental factorial QA/gate sensitivity, existing CORE through 2026-10-22.

No RR replay or canonical writes. All daily outputs go to out/. Aggregate
results go to research/results. These are decision sensitivities, not clinical
validation. Optional sleep/load context is excluded equally from all arms.
"""
from __future__ import annotations

import hashlib
import json
import sys
import types
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))
SOURCE = ROOT / "out/hg04_copias_paralelas_2026-10-22/H3S90T375NL"
OUT = ROOT / "out/hg04_calidad_semaforo_incremental_2026-10-23"
RESULT = Path(__file__).resolve().parents[1] / "results/quality_gate_incremental_2026-10-23.json"
CODE = ROOT / "build_hrv_final_dashboard.py"


def module(amber: bool):
    source = CODE.read_text(encoding="utf-8")
    anchor = '            if bool(quality_flag[i]) and gate_raw_today[i] in (VERDE, AMBAR, ROJO):'
    patch = '''            # EXPERIMENT: red caused by acute bypass without roll-3 red.
            if veto_agudo[i] and gate_base60[i] == ROJO:
                roll_ln, _ = last_n_valid_mean(ln_today, is_clean, cfg.roll_n, i)
                roll_hr, _ = last_n_valid_mean(hr_today, is_clean, cfg.roll_n, i)
                roll_gate, _ = eval_gate(roll_ln, roll_hr, b_ln, b_hr, sw_ln, sw_hr)
                if roll_gate != ROJO:
                    gate_base60[i] = AMBAR
                    razon_base60[i] = "EXP_VETO_AMBAR_SIN_ROJO_ROLL3"

'''
    if amber:
        assert source.count(anchor) == 1
        source = source.replace(anchor, patch + anchor)
    name = "hg04_gate_amber" if amber else "hg04_gate_control"
    mod = types.ModuleType(name)
    mod.__file__ = str(CODE)
    sys.modules[name] = mod
    exec(compile(source, str(CODE), "exec"), mod.__dict__)
    mod.DATA_DIR = SOURCE  # Only CORE/FINAL present; no external context consumed.
    return mod


def transitions(a, b):
    return {f"{x} -> {y}": int(n) for (x, y), n in pd.DataFrame({"a": a, "b": b}).value_counts().items() if x != y}


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    base = pd.read_csv(SOURCE / "ENDURANCE_HRV_master_CORE.csv")
    saved = pd.read_csv(SOURCE / "ENDURANCE_HRV_master_FINAL.csv")
    assert base.Fecha.is_unique and base.Fecha.equals(saved.Fecha)
    # Only promote rows whose sole remaining QA reason is mismatch.
    relaxed = base.copy(deep=True)
    promote = (base.Calidad.eq("FLAG_mecánico")
               & base.Stability_Subtype.eq("STAB_LAST2_MISMATCH")
               & base.Artifact_pct.le(15)
               & base.HR_stable.between(35, 100)
               & np.isfinite(base.RMSSD_stable) & base.RMSSD_stable.gt(0)
               & np.isfinite(base.lnRMSSD))
    relaxed.loc[promote, "Calidad"] = "OK"
    # Keep measured instability, flags and every numerical CORE value unchanged.
    pd.testing.assert_frame_equal(base.drop(columns="Calidad"), relaxed.drop(columns="Calidad"))
    control, amber = module(False), module(True)
    variants = {
        "NL_actual": (base, control),
        "NL_sin_mismatch": (relaxed, control),
        "NL_ambar": (base, amber),
        "NL_sin_mismatch_ambar": (relaxed, amber),
    }
    finals = {}
    for name, (core, engine) in variants.items():
        final, _ = engine.build_final_and_dashboard(core, engine.CFG)
        finals[name] = final
    # Verification only: reproduce the existing gate before adding any policy.
    baseline = finals["NL_actual"]
    for col in ("gate_final", "gate_base60", "veto_agudo", "Action", "Action_detail"):
        assert baseline[col].fillna("").equals(saved[col].fillna("")), f"Control mismatch: {col}"
    for col in ("ln_base60", "HR_base60", "SWC_ln", "SWC_HR", "lnRMSSD_today", "HR_today"):
        if col in saved.columns:
            assert np.allclose(baseline[col], saved[col], equal_nan=True), col
    summary = {
        "scope": "Existing 506-day CORE snapshot; gate sensitivity, no outcome validation; no RR replay",
        "start": str(base.Fecha.min()), "end": str(base.Fecha.max()), "n": len(base),
        "hashes": {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
                   for p in (SOURCE / "ENDURANCE_HRV_master_CORE.csv", SOURCE / "ENDURANCE_HRV_master_FINAL.csv", CODE)},
        "control_matches_saved_gate_and_actions": True,
        "qa_promoted": int(promote.sum()),
        "amber_definition": "Only veto days with current ROJO and non-ROJO roll3 become AMBAR; keep same thresholds and daily bypass values; not a temporal persistence criterion",
        "arms": {}, "comparisons": {},
    }
    daily = base[["Fecha", "RMSSD_stable", "HR_stable", "Artifact_pct", "Stability_Subtype", "Flags"]].copy()
    daily["calidad_recuperada"] = promote
    for name, (core, _) in variants.items():
        f = finals[name]
        summary["arms"][name] = {"quality": core.Calidad.value_counts().to_dict(),
            "gate": f.gate_final.value_counts().to_dict(), "veto": int(f.veto_agudo.sum())}
        daily[f"Calidad_{name}"] = core.Calidad
        for col in ("gate_final", "Action", "Action_detail", "veto_agudo", "gate_razon_base60",
                    "ln_base60", "HR_base60", "SWC_ln", "SWC_HR", "ln_pre_veto", "lnRMSSD_used", "HR_used"):
            daily[f"{col}_{name}"] = f[col]
    for a, b in (("NL_actual", "NL_sin_mismatch"), ("NL_actual", "NL_ambar"),
                 ("NL_sin_mismatch", "NL_sin_mismatch_ambar"), ("NL_actual", "NL_sin_mismatch_ambar")):
        fa, fb = finals[a], finals[b]
        changed = fa.gate_final.ne(fb.gate_final)
        summary["comparisons"][f"{a} / {b}"] = {
            "changed_gates": int(changed.sum()), "transitions": transitions(fa.gate_final, fb.gate_final),
            "changed_actions": int(fa.Action.ne(fb.Action).sum()),
            "changed_action_detail": int(fa.Action_detail.ne(fb.Action_detail).sum()),
            "changed_gates_on_promoted_days": int((changed & promote).sum()),
        }
        if a.endswith("actual") and b.endswith("ambar") and "mismatch" not in b:
            assert (changed <= fa.veto_agudo).all()
            assert fa.loc[changed, "gate_final"].eq("ROJO").all()
            assert fb.loc[changed, "gate_final"].eq("ÁMBAR").all()
        for field in ("lnRMSSD_today", "HR_today"):
            if field in fa:
                assert np.allclose(fa[field], fb[field], equal_nan=True)
    amber_changed = baseline.gate_final.ne(finals["NL_ambar"].gate_final)
    consecutive = pd.to_datetime(base.Fecha).diff().dt.days.eq(1)
    summary["checks"] = {
        "promoted_artifact_median_pct": float(base.loc[promote, "Artifact_pct"].median()),
        "promoted_artifact_max_pct": float(base.loc[promote, "Artifact_pct"].max()),
        "amber_changed_with_veto_previous_calendar_day": int((amber_changed & consecutive & baseline.veto_agudo.shift(1, fill_value=False)).sum()),
    }
    daily.to_csv(OUT / "comparacion_incremental.csv", index=False, encoding="utf-8-sig")
    changed_any = daily.filter(like="gate_final_").nunique(axis=1).gt(1) | promote
    daily.loc[changed_any].to_csv(OUT / "dias_afectados.csv", index=False, encoding="utf-8-sig")
    RESULT.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print("EXAMPLES_CHANGED_GATE")
    print(daily.loc[changed_any, ["Fecha", "RMSSD_stable", "HR_stable", "calidad_recuperada"]
                    + [f"gate_final_{x}" for x in variants]].head(12).to_string(index=False))


if __name__ == "__main__":
    main()
