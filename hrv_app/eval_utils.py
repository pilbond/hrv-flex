# -*- coding: utf-8 -*-
"""Funciones de evaluación estadística compartidas por los módulos SSM."""

from __future__ import annotations

from typing import Dict, List

import numpy as np
from scipy import stats


def ols_predict(x_tr: np.ndarray, y_tr: np.ndarray, x_te: np.ndarray) -> np.ndarray:
    A = np.column_stack([np.ones(len(x_tr)), x_tr])
    beta, *_ = np.linalg.lstsq(A, y_tr, rcond=None)
    return np.column_stack([np.ones(len(x_te)), x_te]) @ beta


def evaluate_predictor(x: np.ndarray, y: np.ndarray) -> Dict[str, object]:
    """Spearman + holdout MAE (80/20 OLS) + walk-forward MAE."""
    n = len(x)
    if n < 12:
        return {
            "n": n,
            "spearman_rho": float("nan"),
            "spearman_p": float("nan"),
            "holdout_mae": float("nan"),
            "holdout_rmse": float("nan"),
            "direction_ok": None,
            "wf_mae_mean": float("nan"),
            "wf_n_folds": 0,
        }

    rho, p = stats.spearmanr(x, y)

    split = max(int(n * 0.80), 8)
    holdout_mae = float("nan")
    holdout_rmse = float("nan")
    if n - split >= 4:
        pred = ols_predict(x[:split], y[:split], x[split:])
        holdout_mae = float(np.mean(np.abs(y[split:] - pred)))
        holdout_rmse = float(np.sqrt(np.mean((y[split:] - pred) ** 2)))

    wf_maes: List[float] = []
    if n >= 48:
        n_folds = 4 if n >= 120 else 3
        test_size = max(n // (n_folds + 2), 12)
        train_min = max(24, test_size * 2)
        start = train_min
        while start + test_size <= n and len(wf_maes) < n_folds:
            pred_wf = ols_predict(x[:start], y[:start], x[start : start + test_size])
            wf_maes.append(float(np.mean(np.abs(y[start : start + test_size] - pred_wf))))
            start += test_size

    return {
        "n": n,
        "spearman_rho": float(rho) if np.isfinite(rho) else float("nan"),
        "spearman_p": float(p) if np.isfinite(p) else float("nan"),
        "holdout_mae": holdout_mae,
        "holdout_rmse": holdout_rmse,
        "direction_ok": bool(rho > 0) if np.isfinite(rho) else None,
        "wf_mae_mean": float(np.mean(wf_maes)) if wf_maes else float("nan"),
        "wf_n_folds": len(wf_maes),
    }


def bootstrap_delta_mae(
    x_a: np.ndarray,
    x_b: np.ndarray,
    y: np.ndarray,
    n_iter: int = 1000,
) -> Dict[str, object]:
    """Bootstrap CI on holdout MAE(x_a) − MAE(x_b). Positive = x_a worse."""
    n = len(y)
    if n < 16:
        return {"status": "insufficient_data"}
    split = max(int(n * 0.80), 8)
    if n - split < 4:
        return {"status": "insufficient_holdout"}
    pred_a = ols_predict(x_a[:split], y[:split], x_a[split:])
    pred_b = ols_predict(x_b[:split], y[:split], x_b[split:])
    y_te = y[split:]
    rng = np.random.default_rng(42)
    deltas = np.empty(n_iter, dtype=float)
    for i in range(n_iter):
        idx = rng.integers(0, len(y_te), size=len(y_te))
        deltas[i] = (
            float(np.mean(np.abs(y_te[idx] - pred_a[idx])))
            - float(np.mean(np.abs(y_te[idx] - pred_b[idx])))
        )
    return {
        "status": "ok",
        "n_iter": n_iter,
        "delta_mae_mean": float(np.mean(deltas)),
        "delta_mae_median": float(np.median(deltas)),
        "delta_mae_ci90": [float(np.percentile(deltas, 5)), float(np.percentile(deltas, 95))],
        "prob_delta_gt_0": float(np.mean(deltas > 0)),
    }
