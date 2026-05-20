# Validación SSM Shadow

## Resumen
- Vista operativa primaria: `sport_first`
- Scope recomendado: `by_sport`
- Estado go/no-go principal: `no_go`
- Outcome principal: `cardiac_drift_worst`
- Motivo de selección outcome: `audit_primary_degenerate_fallback_to_best_validable`
- Pares estrictos: `189`
- Pares lite diagnósticos: `201`
- Pares exploratorios: `327`
- Regla temporal: `next comparable session within t+1..t+7 using declared session families and within-family FDS`
- Regla temporal exploratoria: `aggregate comparable outcomes within t+1..t+3 using up to 3 sessions and within-family FDS`
- Escala outcome estricta: `{"fds": 189}`
- Escala outcome lite: `{"fds": 189, "fds_lite": 12}`
- Escala outcome exploratoria: `{"fds": 245, "oriented_raw_fallback": 64, "fds_lite": 18}`
- `WF MAE mean` usa walk-forward temporal con ventana expansiva.

## Cierre Fase 1
- Estado go/no-go enlazado: `no_go`
- Go/no-go por deporte: `{"bike": "no_go", "run": "no_go"}`
- Lectura primaria por deporte: `no_sport_go`
- `Fase 1 completa. SSM sombra operativo como capa técnica auditada. Semántica confirmada como goodness. Tras normalizar `cardiac_drift_worst` por deporte, la estratificación por deporte muestra valor deporte-dependiente: en run el SSM empata aproximadamente con rolling HRV 7d; en bike pierde. El comparador estructural respalda mantener HRV-only como base, así que el término de carga no queda respaldado como mejora robusta. La observación nocturna de sueño tampoco mejora de forma robusta frente a la versión sin sueño. El benchmark EWMA empata prácticamente al SSM (alpha=0.05, MAE holdout=2.260, WF=1.852), lo que refuerza el riesgo de redundancia. El resultado global cae a no-go, así que la normalización por deporte no rescata una ventaja robusta del modelo. La heterogeneidad cross-sport sigue siendo relevante incluso con el drift reescalado. Infraestructura de validación madura y reutilizable. No apto aún para gate ni reason_text (existe en `build_hrv_final_dashboard.py` un bloque latente de contexto SSM tras feature flag `HRV_SSM_REASON_TEXT_ENABLED`, default `0`; sin filtro por deporte, no se activa en Fase 1). Siguiente mejora natural: evaluar outcome específico por deporte en lugar de un target combinado.`

## Vista Operativa Primaria
- Modo: `sport_first`
- Scope recomendado: `by_sport`
- Estado global: `no_go`
- Estados por deporte: `{"bike": "no_go", "run": "no_go"}`
- `Priorizar la lectura por deporte: el agregado global es secundario porque ningún deporte viable sostiene candidate_go.`

## Calibración
- `{"status": "undercovered", "target_coverage": 0.9, "observed_coverage": 0.8229166666666666, "delta": -0.07708333333333339, "ci95": [0.7316814537399138, 0.8933229640980848], "coverage_n": 96}`

## Diagnóstico Outcome
- Modo de fallo principal: `fds_available`
- Normalización outcome: `{"mode": "sport_family_abs_median_scale", "applied": true, "per_sport_reference": {"bike": 6.550000000000001, "hike": 0.1, "mixed": 0.7, "mobility": 0.7, "run": 3.75, "strength": 5.5, "swim": 1.7}}`
- Outcomes comparables evaluados: `197`
- Filas con `FDS`: `141`
- Filas con `FDS-lite`: `11`
- Filas con `baseline_n >= 3`: `142`
- Filas con `baseline_n >= 3` bloqueadas por MAD=0: `1`
- Share de `outcome_oriented == 0`: `0.000`
- Valores más frecuentes del outcome orientado: `{"-0.88": 3, "1.0": 3, "-0.13333333333333333": 2, "-3.058823529411765": 2, "-2.8266666666666667": 2, "-3.2800000000000002": 2, "1.297709923664122": 2, "0.29333333333333333": 2}`

## Auditoría de Signo
- SSM como `goodness`: rho=`0.124`; soporte=`True`; semántica preferida=`goodness`
- Rolling 7d como `goodness`: rho=`0.154`; soporte=`True`; semántica preferida=`goodness`

## Comparador Estructural
- Estado comparador: `prefer_banister_hrv_only`
- Pares alineados actual vs alternativo: `189`
- Modelo actual (banister_2state) holdout MAE: `2.264`
- Modelo alternativo (banister_hrv_only) holdout MAE: `2.263`
- Load sobre innovaciones HRV-only: `{"status": "no_evidence_load_explains_innovations", "n_rows": 332, "coef": -2.0664359706820354e-05, "se": 0.00034471532278035447, "p_value": 0.9522348020740513, "r2": 1.0889402733749165e-05}`

## Sensibilidad Phi
- Estado sensibilidad: `current_phi_best_or_tied`
- Phi actual: `0.985`
- Mejor phi en grid: `0.85`
- MAE holdout actual: `2.264`
- MAE holdout mejor phi: `2.263`
- Grid: `[{"phi": 0.85, "aligned_pairs_n": 189, "spearman_rho": 0.12382411432412202, "spearman_p_value": 0.08959344081643514, "holdout_mae": 2.262640751052557, "holdout_rmse": 3.725646800913046, "direction_ok": true}, {"phi": 0.9, "aligned_pairs_n": 189, "spearman_rho": 0.12416276428613088, "spearman_p_value": 0.0887131787110059, "holdout_mae": 2.2626464578393213, "holdout_rmse": 3.7254449075969633, "direction_ok": true}, {"phi": 0.92, "aligned_pairs_n": 189, "spearman_rho": 0.1229379358146133, "spearman_p_value": 0.091929946376958, "holdout_mae": 2.262755750953383, "holdout_rmse": 3.7251995037365417, "direction_ok": true}, {"phi": 0.97, "aligned_pairs_n": 189, "spearman_rho": 0.12114157997939051, "spearman_p_value": 0.09681510113304166, "holdout_mae": 2.2634310844588463, "holdout_rmse": 3.723342571909278, "direction_ok": true}]`

## Días Discordantes
- Estado discordancia: `ok`
- Flags: `{"ssm_good_vs_load_high": 22, "ssm_bad_vs_hrv_normal": 1, "ssm_vs_gate_disagree": 32, "discordant_any": 50, "concordant_any": 139}`
- SSM MAE discordantes: `1.906` vs rolling `1.955`
- SSM MAE concordantes: `1.629` vs rolling `1.621`

## Estratificación Deporte
- Estado estratificación: `ok`
- Deportes viables: `["bike", "run"]`
- Resumen por deporte: `{"bike": {"n_pairs": 82, "ssm_holdout_mae": 2.1765635021945036, "rolling_holdout_mae": 2.018989505547742}, "run": {"n_pairs": 107, "ssm_holdout_mae": 2.0054168494546367, "rolling_holdout_mae": 1.99669995387272}}`

## Walk-Forward Por Deporte
| Deporte | n | Go/no-go | SSM holdout MAE | SSM WF MAE | Rolling holdout MAE | Rolling WF MAE |
| --- | --- | --- | --- | --- | --- | --- |
| bike | 82 | no_go | 2.177 | 1.371 | 2.019 | 1.378 |
| run | 107 | no_go | 2.005 | 1.639 | 1.997 | 1.587 |

## Principal Estricto Por Deporte
- `{"bike": {"n_pairs": 82, "go_no_go": "no_go"}, "run": {"n_pairs": 107, "go_no_go": "no_go"}}`

## Funnel Estricto
- `{"all_pairs": 327, "fds_only": 245, "no_strength": 245, "aerobic_sports_only": 189, "valid_comparison_level": 189, "baseline_n_gte_3": 189}`

## Principal Estricto
| Predictor | n | Spearman rho | p-value | Holdout MAE | WF MAE mean | WF folds | Holdout RMSE |
| --- | --- | --- | --- | --- | --- | --- | --- |
| SSM shadow | 189 | 0.124 | 0.090 | 2.264 | 1.862 | 4 | 3.722 |
| Rolling HRV 7d | 189 | 0.154 | 0.035 | 2.262 | 1.855 | 4 | 3.723 |
| Load 7d | 164 | 0.138 | 0.079 | 2.070 | 1.451 | 4 | 3.452 |
| Gate final | 178 | -0.022 | 0.767 | 2.172 | 1.627 | 4 | 3.564 |

## Comparador Sueño
- Estado comparador: `prefer_sleep_free`
- Pares alineados actual vs sin sueño: `189`
- Modelo con sueño holdout MAE: `2.264`
- Modelo sin sueño holdout MAE: `2.263`
- Delta MAE sin sueño - con sueño: `-0.001`

## Comparador EWMA
- Estado comparador: `equivalent_holdout`
- Modelo base: `banister_2state`
- Baseline: `ewma_lnrmssd`
- Mejor alpha holdout: `0.050`
- Mejor MAE holdout EWMA: `2.260`
- Mejor MAE walk-forward EWMA: `1.852`
- Delta MAE SSM - EWMA holdout: `0.004`
- Delta MAE SSM - EWMA walk-forward: `0.010`
- Grid: `[{"alpha": 0.05, "aligned_pairs_n": 186, "spearman_rho": 0.1517979009174566, "spearman_p_value": 0.03861253765292107, "holdout_mae": 2.2599976965772357, "holdout_rmse": 3.708631297826218, "walk_forward_status": "ok", "walk_forward_n_folds": 4, "walk_forward_mae_mean": 2.0246060098541983, "walk_forward_mae_median": 1.931260431878703, "direction_ok": true}, {"alpha": 0.1, "aligned_pairs_n": 186, "spearman_rho": 0.17065140611999394, "spearman_p_value": 0.01986997677056949, "holdout_mae": 2.264362322932585, "holdout_rmse": 3.722978681451172, "walk_forward_status": "ok", "walk_forward_n_folds": 4, "walk_forward_mae_mean": 1.8939802526355183, "walk_forward_mae_median": 1.8326789400248464, "direction_ok": true}, {"alpha": 0.15, "aligned_pairs_n": 186, "spearman_rho": 0.1593133779134129, "spearman_p_value": 0.02985649010226102, "holdout_mae": 2.2672973178887514, "holdout_rmse": 3.72886986454911, "walk_forward_status": "ok", "walk_forward_n_folds": 4, "walk_forward_mae_mean": 1.86174863654479, "walk_forward_mae_median": 1.8336109217059802, "direction_ok": true}, {"alpha": 0.2, "aligned_pairs_n": 186, "spearman_rho": 0.1576543589810632, "spearman_p_value": 0.03162788658201333, "holdout_mae": 2.267319749028065, "holdout_rmse": 3.7310588311824704, "walk_forward_status": "ok", "walk_forward_n_folds": 4, "walk_forward_mae_mean": 1.8612040350660135, "walk_forward_mae_median": 1.850286903127906, "direction_ok": true}, {"alpha": 0.3, "aligned_pairs_n": 186, "spearman_rho": 0.14958307800327417, "spearman_p_value": 0.041573146348510344, "holdout_mae": 2.264629790742474, "holdout_rmse": 3.7313116217665088, "walk_forward_status": "ok", "walk_forward_n_folds": 4, "walk_forward_mae_mean": 1.86357083661711, "walk_forward_mae_median": 1.862542718928492, "direction_ok": true}, {"alpha": 0.4, "aligned_pairs_n": 186, "spearman_rho": 0.1333537882451618, "spearman_p_value": 0.06959219656026529, "holdout_mae": 2.2607143690847926, "holdout_rmse": 3.729084771222002, "walk_forward_status": "ok", "walk_forward_n_folds": 4, "walk_forward_mae_mean": 1.852466490608324, "walk_forward_mae_median": 1.849403307891424, "direction_ok": true}]`

## Diagnósticos Estrictos
- Redundancia vs `rolling_hrv_7d + load_7d`: `distinct_enough` (R²=0.771)
- Lag medio al outcome: `1.767` días
- Lag mediano al outcome: `1.000` días
- Nivel de comparabilidad: `{"session_group": 189}`
- Familias por deporte: `{"aerobic_long_z2__bike": 74, "aerobic_long_z2__run": 48, "aerobic_intervals__run": 35, "aerobic_short_z2__run": 24, "aerobic_intervals__bike": 8}`
- Cuartil alto de varianza: n=48 · outcome medio=0.131
- Cuartil bajo de varianza: n=48 · outcome medio=0.076

## Baseline Trivial
- `{"median_baseline": {"n_pairs": 189, "holdout_mae": 2.2725422609429287, "holdout_rmse": 3.6834009640749983}, "family_last_baseline": {"n_pairs": 189, "holdout_mae": 2.0472315041912, "holdout_rmse": 3.5788518406594423}, "bootstrap_ci": {"ssm_vs_rolling_holdout_mae": {"status": "ok", "n_iter": 1000, "delta_mae_mean": 0.0019389737626904187, "delta_mae_median": 0.0023046696238949727, "delta_mae_ci90": [-0.01593330337083657, 0.01869231758725496], "prob_delta_gt_0": 0.581}, "ssm_vs_median_baseline_holdout_mae": {"status": "ok", "n_iter": 1000, "delta_mae_mean": -0.00849621240639264, "delta_mae_median": -0.009451537193930104, "delta_mae_ci90": [-0.06502821706581063, 0.05070834027427866], "prob_delta_gt_0": 0.395}, "ssm_vs_family_last_baseline_holdout_mae": {"status": "ok", "n_iter": 1000, "delta_mae_mean": 0.2089123271565161, "delta_mae_median": 0.22356072747588696, "delta_mae_ci90": [-0.6530726224789357, 1.128167530082046], "prob_delta_gt_0": 0.653}, "rolling_vs_median_baseline_holdout_mae": {"status": "ok", "n_iter": 1000, "delta_mae_mean": -0.010435186169083059, "delta_mae_median": -0.011962507173439274, "delta_mae_ci90": [-0.07841768458011968, 0.062441947134470654], "prob_delta_gt_0": 0.394}, "load_vs_median_baseline_holdout_mae": {"status": "insufficient_data"}}}`

## Bootstrap CI
- `{"ssm_vs_rolling_holdout_mae": {"status": "ok", "n_iter": 1000, "delta_mae_mean": 0.0019389737626904187, "delta_mae_median": 0.0023046696238949727, "delta_mae_ci90": [-0.01593330337083657, 0.01869231758725496], "prob_delta_gt_0": 0.581}, "ssm_vs_median_baseline_holdout_mae": {"status": "ok", "n_iter": 1000, "delta_mae_mean": -0.00849621240639264, "delta_mae_median": -0.009451537193930104, "delta_mae_ci90": [-0.06502821706581063, 0.05070834027427866], "prob_delta_gt_0": 0.395}, "ssm_vs_family_last_baseline_holdout_mae": {"status": "ok", "n_iter": 1000, "delta_mae_mean": 0.2089123271565161, "delta_mae_median": 0.22356072747588696, "delta_mae_ci90": [-0.6530726224789357, 1.128167530082046], "prob_delta_gt_0": 0.653}, "rolling_vs_median_baseline_holdout_mae": {"status": "ok", "n_iter": 1000, "delta_mae_mean": -0.010435186169083059, "delta_mae_median": -0.011962507173439274, "delta_mae_ci90": [-0.07841768458011968, 0.062441947134470654], "prob_delta_gt_0": 0.394}, "load_vs_median_baseline_holdout_mae": {"status": "insufficient_data"}}`

## Principal Lite
- Diagnóstico intermedio: exige baseline comparable >=2 y escala `fds`/`fds_lite`, pero no gobierna promoción.
| Predictor | n | Spearman rho | p-value | Holdout MAE | WF MAE mean | WF folds | Holdout RMSE |
| --- | --- | --- | --- | --- | --- | --- | --- |
| SSM shadow | 201 | 0.141 | 0.046 | 2.152 | 1.797 | 4 | 3.574 |
| Rolling HRV 7d | 201 | 0.156 | 0.027 | 2.145 | 1.858 | 4 | 3.576 |
| Load 7d | 174 | 0.100 | 0.191 | 1.991 | 1.486 | 4 | 3.352 |
| Gate final | 188 | -0.004 | 0.961 | 2.141 | 1.636 | 4 | 3.489 |

## Exploratorio Amplio
| Predictor | n | Spearman rho | p-value | Holdout MAE | WF MAE mean | WF folds | Holdout RMSE |
| --- | --- | --- | --- | --- | --- | --- | --- |
| SSM shadow | 327 | 0.143 | 0.010 | 3.217 | 5.038 | 4 | 4.111 |
| Rolling HRV 7d | 327 | 0.200 | 0.000 | 4.015 | 4.222 | 4 | 4.751 |
| Load 7d | 275 | 0.070 | 0.248 | 2.051 | 3.037 | 4 | 3.083 |
| Gate final | 305 | -0.028 | 0.632 | 2.744 | 4.836 | 4 | 3.703 |

## Exploratorio Ventana T1-T3
- Diagnóstico exploratorio: agrega hasta 3 sesiones comparables en `t+1..t+3` para reducir ruido de un mal día puntual.
| Predictor | n | Spearman rho | p-value | Holdout MAE | WF MAE mean | WF folds | Holdout RMSE |
| --- | --- | --- | --- | --- | --- | --- | --- |
| SSM shadow | 294 | 0.051 | 0.385 | 2.007 | 4.193 | 4 | 2.666 |
| Rolling HRV 7d | 294 | 0.108 | 0.064 | 2.658 | 2.895 | 4 | 3.176 |
| Load 7d | 250 | 0.071 | 0.265 | 1.244 | 2.058 | 4 | 1.786 |
| Gate final | 276 | 0.033 | 0.586 | 1.816 | 3.306 | 4 | 2.644 |

## Go / No-Go Principal
- required_all: `{"outcome_audit_pass": true, "pairs_gte_30": true, "not_redundant_vs_simple_baselines": true, "beats_rolling_hrv_7d_holdout_mae": false}`
- required_at_least_one: `{"beats_load_7d_holdout_mae": false}`
- veto_conditions: `{"redundancy_detected": false, "too_few_pairs": false, "outcome_audit_not_pass": false, "does_not_beat_rolling_hrv_7d": true}`

## Nota
- El bloque principal estricto gobierna el go/no-go. El bloque lite ayuda a decidir si merece seguir acumulando datos, pero no justifica promoción.
- El bloque exploratorio conserva cobertura amplia, pero no justifica promoción.
- Este reporte es Fase 1 sombra. No recolorea el gate ni modifica `FINAL.csv`.
