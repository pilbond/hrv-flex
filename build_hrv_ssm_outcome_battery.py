# -*- coding: utf-8 -*-
"""
ENDURANCE HRV — Batería de outcomes alternativos SSM Fase 1
============================================================

Prueba el predictor SSM sombra contra outcomes distintos de cardiac_drift_worst:
  - lnrmssd_next_day : predicción directa del HRV del día siguiente (AR)
  - wellness_next_day: predicción del bienestar subjetivo del día siguiente

No modifica FINAL ni el gate operativo.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from hrv_app.config import DATA_DIR as CONFIG_DATA_DIR
from hrv_app.config import SSM_RESEARCH_REPORT_DIR
from hrv_app.config import resolve_writable_dir
from hrv_app.eval_utils import bootstrap_delta_mae, evaluate_predictor, ols_predict
from hrv_app.io_utils import json_safe as _json_safe, write_json_atomic, write_text_atomic

DATA_DIR = CONFIG_DATA_DIR
IN_CORE = DATA_DIR / "ENDURANCE_HRV_master_CORE.csv"
IN_SSM = DATA_DIR / "ENDURANCE_HRV_ssm_shadow.csv"
IN_WELLNESS = DATA_DIR / "ENDURANCE_HRV_wellness_subjective.csv"
OUT_BATTERY_JSON = SSM_RESEARCH_REPORT_DIR / "ENDURANCE_HRV_ssm_outcome_battery.json"
OUT_BATTERY_MD = SSM_RESEARCH_REPORT_DIR / "ENDURANCE_HRV_ssm_outcome_battery.md"

EWMA_ALPHA_GRID = [0.05, 0.10, 0.15, 0.20, 0.30, 0.40]
VERDICT_MARGIN = 0.005


def parse_args(argv: List[str]) -> Dict[str, str]:
    parsed: Dict[str, str] = {}
    for idx, token in enumerate(argv):
        if token == "--data-dir" and idx + 1 < len(argv):
            parsed["data_dir"] = argv[idx + 1]
        if token == "--output-dir" and idx + 1 < len(argv):
            parsed["output_dir"] = argv[idx + 1]
    return parsed


def _safe_float(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce").astype(float)


def _load_csv(path: Path, required: List[str]) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"No existe: {path}")
    df = pd.read_csv(path)
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f"{path.name} faltan columnas: {missing}")
    df["Fecha"] = pd.to_datetime(df["Fecha"], errors="coerce").dt.normalize()
    return df[df["Fecha"].notna()].sort_values("Fecha").reset_index(drop=True)


def _build_lnrmssd_next_pairs(ssm_df: pd.DataFrame, core_df: pd.DataFrame) -> pd.DataFrame:
    ssm = ssm_df.copy()
    ssm = ssm[ssm["ssm_warmup_complete"].astype(bool) & ssm["ssm_recovery_state"].notna()].copy()

    core = core_df.copy()
    core["lnRMSSD_f"] = _safe_float(core["lnRMSSD"])

    # EWMA columns computed causally on available CORE rows
    for alpha in EWMA_ALPHA_GRID:
        core[f"ewma_{alpha}"] = (
            core["lnRMSSD_f"].ewm(alpha=alpha, adjust=False, ignore_na=True).mean()
        )

    # next_hrv: shift date -1 day so Fecha==t maps to lnRMSSD measured at t+1
    next_hrv = (
        core[["Fecha", "lnRMSSD_f"]]
        .copy()
        .rename(columns={"lnRMSSD_f": "lnrmssd_next"})
    )
    next_hrv["Fecha"] = next_hrv["Fecha"] - pd.Timedelta(days=1)

    # current lnRMSSD (AR1 baseline) and EWMA at date t
    ewma_cols = [f"ewma_{a}" for a in EWMA_ALPHA_GRID]
    current = core[["Fecha", "lnRMSSD_f"] + ewma_cols].rename(
        columns={"lnRMSSD_f": "lnrmssd_current"}
    )

    pairs = ssm.merge(next_hrv, on="Fecha", how="inner")
    pairs = pairs.merge(current, on="Fecha", how="left")
    return pairs[pairs["lnrmssd_next"].notna()].sort_values("Fecha").reset_index(drop=True)


def _build_wellness_pairs(
    ssm_df: pd.DataFrame,
    wellness_df: pd.DataFrame,
    lag_days: int = 1,
) -> Tuple[pd.DataFrame, Optional[str]]:
    if wellness_df.empty:
        return pd.DataFrame(), None

    ssm = ssm_df.copy()
    ssm = ssm[ssm["ssm_warmup_complete"].astype(bool) & ssm["ssm_recovery_state"].notna()].copy()

    well = wellness_df.copy()
    raw_cols = [c for c in well.columns if c.endswith("_raw") and c != "well_comment_raw"]
    if not raw_cols:
        return pd.DataFrame(), None

    # Choose column with most non-NaN values
    best_col = max(raw_cols, key=lambda c: _safe_float(well[c]).notna().sum())
    if int(_safe_float(well[best_col]).notna().sum()) < 12:
        return pd.DataFrame(), None

    well = well[["Fecha", best_col]].copy()
    well[best_col] = _safe_float(well[best_col])
    # Shift so Fecha==t maps to wellness measured at t+lag
    well["Fecha"] = well["Fecha"] - pd.Timedelta(days=lag_days)
    well = well.rename(columns={best_col: "wellness_outcome"})

    pairs = ssm.merge(well, on="Fecha", how="inner")
    pairs = pairs[pairs["wellness_outcome"].notna()].copy()
    return pairs.sort_values("Fecha").reset_index(drop=True), best_col


def _build_outcome_block(
    outcome_name: str,
    pairs: pd.DataFrame,
    outcome_col: str,
    ar1_col: Optional[str] = None,
) -> Dict[str, object]:
    y = _safe_float(pairs[outcome_col]).to_numpy(dtype=float)

    def _get(col: str) -> Optional[np.ndarray]:
        if col not in pairs.columns:
            return None
        return _safe_float(pairs[col]).to_numpy(dtype=float)

    def _eval_masked(x: Optional[np.ndarray]) -> Dict[str, object]:
        if x is None:
            return {}
        mask = np.isfinite(x) & np.isfinite(y)
        if mask.sum() < 12:
            return {"n": int(mask.sum())}
        return evaluate_predictor(x[mask], y[mask])

    ssm_x = _get("ssm_recovery_state")
    rolling_x = _get("control_rolling_hrv_7d")
    ar1_x = _get(ar1_col) if ar1_col else None
    load_x = _get("control_load_7d")
    innovation_x = _get("ssm_innovation")

    ssm_eval = _eval_masked(ssm_x)
    rolling_eval = _eval_masked(rolling_x)
    ar1_eval = _eval_masked(ar1_x)
    load_eval = _eval_masked(load_x)
    innovation_eval = _eval_masked(innovation_x)

    # Bootstrap CI: innovation vs rolling (independent channel test)
    bci_innovation: Dict[str, object] = {}
    if innovation_x is not None and rolling_x is not None:
        mask = np.isfinite(innovation_x) & np.isfinite(rolling_x) & np.isfinite(y)
        if mask.sum() >= 16:
            bci_innovation = bootstrap_delta_mae(innovation_x[mask], rolling_x[mask], y[mask])

    # Bootstrap CI: SSM vs rolling
    bci: Dict[str, object] = {}
    if ssm_x is not None and rolling_x is not None:
        mask = np.isfinite(ssm_x) & np.isfinite(rolling_x) & np.isfinite(y)
        if mask.sum() >= 16:
            bci = bootstrap_delta_mae(ssm_x[mask], rolling_x[mask], y[mask])

    # EWMA grid
    ewma_results: List[Dict[str, object]] = []
    for alpha in EWMA_ALPHA_GRID:
        ewma_x = _get(f"ewma_{alpha}")
        if ewma_x is None:
            continue
        mask = np.isfinite(ewma_x) & np.isfinite(y)
        if mask.sum() < 12:
            continue
        ev = evaluate_predictor(ewma_x[mask], y[mask])
        ewma_results.append({"alpha": alpha, **ev})

    ssm_mae = ssm_eval.get("holdout_mae", float("nan"))
    rolling_mae = rolling_eval.get("holdout_mae", float("nan"))
    ar1_mae = ar1_eval.get("holdout_mae", float("nan"))

    if not np.isfinite(ssm_mae) or not np.isfinite(rolling_mae):
        verdict = "insufficient_data"
    elif ssm_mae < rolling_mae - VERDICT_MARGIN:
        verdict = "ssm_wins"
    elif rolling_mae < ssm_mae - VERDICT_MARGIN:
        verdict = "rolling_wins"
    else:
        verdict = "tied"

    best_ewma = min(ewma_results, key=lambda r: r.get("holdout_mae", float("inf"))) if ewma_results else {}
    ewma_verdict: Dict[str, object] = {}
    if best_ewma:
        ewma_verdict = {
            "best_alpha": best_ewma.get("alpha"),
            "best_holdout_mae": best_ewma.get("holdout_mae"),
            "ssm_vs_ewma_best_delta": (ssm_mae - float(best_ewma.get("holdout_mae", float("nan")))),
            "ewma_wins_holdout": bool(
                np.isfinite(ssm_mae)
                and np.isfinite(float(best_ewma.get("holdout_mae", float("nan"))))
                and float(best_ewma.get("holdout_mae", float("nan"))) < ssm_mae
            ),
        }

    innovation_mae = innovation_eval.get("holdout_mae", float("nan"))
    innovation_verdict = (
        "innovation_wins"
        if np.isfinite(innovation_mae) and np.isfinite(rolling_mae) and innovation_mae < rolling_mae - VERDICT_MARGIN
        else "innovation_tied_or_loses"
        if np.isfinite(innovation_mae)
        else "insufficient_data"
    )

    return {
        "outcome_name": outcome_name,
        "outcome_col": outcome_col,
        "n_pairs": int(np.isfinite(y).sum()),
        "evaluations": {
            "ssm_goodness": ssm_eval,
            "rolling_hrv_goodness": rolling_eval,
            "ar1_baseline": ar1_eval,
            "load_7d": load_eval,
            "ssm_innovation": innovation_eval,
        },
        "innovation_verdict": innovation_verdict,
        "bootstrap_innovation_vs_rolling": bci_innovation,
        "ewma_grid": ewma_results,
        "ewma_verdict": ewma_verdict,
        "bootstrap_ssm_vs_rolling": bci,
        "verdict": verdict,
        "ssm_beats_ar1": (
            bool(ssm_mae < ar1_mae)
            if np.isfinite(ssm_mae) and np.isfinite(ar1_mae)
            else None
        ),
    }


def build_outcome_battery(
    core_df: pd.DataFrame,
    ssm_df: pd.DataFrame,
    wellness_df: pd.DataFrame,
) -> Dict[str, object]:
    lnrmssd_pairs = _build_lnrmssd_next_pairs(ssm_df, core_df)
    wellness_pairs, wellness_col = _build_wellness_pairs(ssm_df, wellness_df, lag_days=1)

    outcomes: Dict[str, object] = {}

    if not lnrmssd_pairs.empty:
        outcomes["lnrmssd_next_day"] = _build_outcome_block(
            outcome_name="lnRMSSD día siguiente",
            pairs=lnrmssd_pairs,
            outcome_col="lnrmssd_next",
            ar1_col="lnrmssd_current",
        )

    if not wellness_pairs.empty and wellness_col:
        outcomes[f"wellness_next_day"] = _build_outcome_block(
            outcome_name=f"Bienestar subjetivo día siguiente ({wellness_col})",
            pairs=wellness_pairs,
            outcome_col="wellness_outcome",
        )

    all_verdicts = {k: v.get("verdict") for k, v in outcomes.items()}  # type: ignore[union-attr]
    any_ssm_wins = any(v == "ssm_wins" for v in all_verdicts.values())

    if any_ssm_wins:
        battery_status = "ssm_wins_at_least_one_outcome"
        summary = (
            "El SSM muestra ventaja predictiva en al menos un outcome alternativo. "
            "Ver detalles por outcome para evaluar si justifica revisión de Fase 2."
        )
    elif all_verdicts and all(v in ("tied", "rolling_wins", "insufficient_data") for v in all_verdicts.values()):
        battery_status = "no_ssm_advantage_across_outcomes"
        summary = (
            "El SSM no muestra ventaja sobre rolling HRV 7d en ningún outcome evaluado. "
            "La señal autonómica disponible (lnRMSSD matinal) parece capturarse igualmente bien "
            "por un suavizado simple. El bottleneck es el dataset, no la arquitectura del modelo."
        )
    else:
        battery_status = "mixed"
        summary = "Resultados mixtos. Ver detalles por outcome."

    return {
        "source": "build_hrv_ssm_outcome_battery.py",
        "generated_at": pd.Timestamp.now("UTC").isoformat(),
        "ewma_alpha_grid": EWMA_ALPHA_GRID,
        "outcomes": outcomes,
        "battery_conclusion": {
            "status": battery_status,
            "all_verdicts": all_verdicts,
            "summary": summary,
        },
    }


def build_outcome_battery_markdown(report: Dict[str, object]) -> str:
    conclusion = report["battery_conclusion"]  # type: ignore[index]
    lines = [
        "# Batería de Outcomes Alternativos — SSM Fase 1",
        "",
        "## Conclusión",
        f"- Estado: `{conclusion['status']}`",
        f"- Veredictos: `{json.dumps(conclusion['all_verdicts'], ensure_ascii=False)}`",
        f"- {conclusion['summary']}",
        "",
    ]

    def _fmt(v: object, d: int = 3) -> str:
        if v is None or (isinstance(v, float) and not np.isfinite(v)):
            return "—"
        return f"{float(v):.{d}f}" if d else str(int(float(v)))  # type: ignore[arg-type]

    for block in report["outcomes"].values():  # type: ignore[union-attr]
        evals = block.get("evaluations", {})
        lines += [
            f"## Outcome: `{block['outcome_name']}`",
            f"- Pares disponibles: `{block['n_pairs']}`",
            f"- Veredicto: `{block['verdict']}`",
            f"- SSM supera AR(1): `{block.get('ssm_beats_ar1')}`",
            "",
            "| Predictor | n | Spearman rho | p-value | Holdout MAE | WF MAE | WF folds |",
            "| --- | --- | --- | --- | --- | --- | --- |",
        ]
        labels = {
            "ssm_goodness": "SSM shadow",
            "rolling_hrv_goodness": "Rolling HRV 7d",
            "ar1_baseline": "AR(1) lnRMSSD[t]",
            "ssm_innovation": "Innovación SSM[t]",
            "load_7d": "Load 7d",
        }
        for key, label in labels.items():
            ev = evals.get(key, {})
            if not ev:
                continue
            lines.append(
                f"| {label} | {_fmt(ev.get('n'), 0)} | {_fmt(ev.get('spearman_rho'))} | "
                f"{_fmt(ev.get('spearman_p'))} | {_fmt(ev.get('holdout_mae'))} | "
                f"{_fmt(ev.get('wf_mae_mean'))} | {_fmt(ev.get('wf_n_folds'), 0)} |"
            )

        inno_verdict = block.get("innovation_verdict")
        if inno_verdict:
            lines.append(f"- Veredicto innovación: `{inno_verdict}`")

        bci_inno = block.get("bootstrap_innovation_vs_rolling", {})
        if bci_inno.get("status") == "ok":
            lines += [
                "",
                f"- Bootstrap CI90 (MAE innovación − MAE rolling): `{bci_inno.get('delta_mae_ci90')}`",
                f"- prob(innovación_MAE > rolling_MAE): `{_fmt(bci_inno.get('prob_delta_gt_0'))}`",
            ]

        ewma_v = block.get("ewma_verdict", {})
        if ewma_v:
            lines += [
                "",
                f"- Mejor EWMA holdout: alpha=`{ewma_v.get('best_alpha')}` "
                f"→ MAE=`{_fmt(ewma_v.get('best_holdout_mae'))}`",
                f"- Delta MAE (SSM − EWMA_best): `{_fmt(ewma_v.get('ssm_vs_ewma_best_delta'))}`",
            ]

        bci = block.get("bootstrap_ssm_vs_rolling", {})
        if bci.get("status") == "ok":
            lines += [
                "",
                f"- Bootstrap CI90 (MAE SSM − MAE rolling): `{bci.get('delta_mae_ci90')}`",
                f"- prob(SSM_MAE > rolling_MAE): `{_fmt(bci.get('prob_delta_gt_0'))}`",
            ]

        lines.append("")

    lines += [
        "## Nota",
        "- Esta batería es exploratoria y no modifica el go/no-go principal de `build_hrv_ssm_validation.py`.",
        "- AR(1) (lnRMSSD[t] como predictor de lnRMSSD[t+1]) es el baseline más difícil para HRV.",
        "- Un SSM que no supera AR(1) no añade información sobre la dinámica temporal.",
        "- La EWMA con alpha óptimo actúa como test de degeneración adicional.",
    ]
    return "\n".join(lines) + "\n"


def main(argv: List[str]) -> int:
    args = parse_args(argv)

    global DATA_DIR, IN_CORE, IN_SSM, IN_WELLNESS, OUT_BATTERY_JSON, OUT_BATTERY_MD
    if "data_dir" in args:
        DATA_DIR = resolve_writable_dir(Path(args["data_dir"]), CONFIG_DATA_DIR)
        IN_CORE = DATA_DIR / "ENDURANCE_HRV_master_CORE.csv"
        IN_SSM = DATA_DIR / "ENDURANCE_HRV_ssm_shadow.csv"
        IN_WELLNESS = DATA_DIR / "ENDURANCE_HRV_wellness_subjective.csv"
    if "output_dir" in args:
        output_dir = resolve_writable_dir(Path(args["output_dir"]), SSM_RESEARCH_REPORT_DIR)
        OUT_BATTERY_JSON = output_dir / "ENDURANCE_HRV_ssm_outcome_battery.json"
        OUT_BATTERY_MD = output_dir / "ENDURANCE_HRV_ssm_outcome_battery.md"

    try:
        core_df = _load_csv(IN_CORE, ["Fecha", "lnRMSSD"])
        ssm_df = _load_csv(
            IN_SSM,
            ["Fecha", "ssm_warmup_complete", "ssm_recovery_state", "control_rolling_hrv_7d"],
        )
        wellness_df = (
            _load_csv(IN_WELLNESS, ["Fecha"]) if IN_WELLNESS.exists()
            else pd.DataFrame(columns=["Fecha"])
        )
    except (FileNotFoundError, ValueError) as exc:
        print(f"[ERROR] {exc}")
        return 2

    report = build_outcome_battery(core_df, ssm_df, wellness_df)
    write_json_atomic(report, OUT_BATTERY_JSON)
    write_text_atomic(build_outcome_battery_markdown(report), OUT_BATTERY_MD)
    print(f"[OK] Batería de outcomes actualizada: {OUT_BATTERY_JSON.name}")
    return 0


if __name__ == "__main__":
    import sys

    raise SystemExit(main(sys.argv[1:]))
