# Validación SSM Shadow

## Resumen
- Vista operativa primaria: `global_with_sport_context`
- Scope recomendado: `global`
- Estado go/no-go principal: `candidate_go`
- Outcome principal: `cardiac_drift_worst`
- Motivo de selección outcome: `audit_primary_degenerate_fallback_to_best_validable`
- Pares estrictos: `200`
- Pares lite diagnósticos: `212`
- Pares exploratorios: `342`
- Regla temporal: `next comparable session within t+1..t+7 using declared session families and within-family FDS`
- Regla temporal exploratoria: `aggregate comparable outcomes within t+1..t+3 using up to 3 sessions and within-family FDS`
- Escala outcome estricta: `{"fds": 200}`
- Escala outcome lite: `{"fds": 200, "fds_lite": 12}`
- Escala outcome exploratoria: `{"fds": 260, "oriented_raw_fallback": 64, "fds_lite": 18}`
- `WF MAE mean` usa walk-forward temporal con ventana expansiva.

## Cierre Fase 1
- Estado go/no-go enlazado: `candidate_go`
- Go/no-go por deporte: `{"bike": "no_go", "run": "candidate_go"}`
- Lectura primaria por deporte: `sport_specific_go`
- `Fase 1 completa. SSM sombra operativo como capa técnica auditada. Semántica confirmada como goodness. Tras normalizar `cardiac_drift_worst` por deporte, la estratificación por deporte muestra valor deporte-dependiente: en run el SSM empata aproximadamente con rolling HRV 7d; en bike pierde. El comparador estructural respalda mantener HRV-only como base, así que el término de carga no queda respaldado como mejora robusta. La observación nocturna de sueño sí añade algo de valor frente a la versión sin sueño. El benchmark EWMA empata prácticamente al SSM (alpha=0.40, MAE holdout=1.534, WF=1.457), lo que refuerza el riesgo de redundancia. La heterogeneidad cross-sport sigue siendo relevante incluso con el drift reescalado. Infraestructura de validación madura y reutilizable. No apto aún para gate ni reason_text (existe en `build_hrv_final_dashboard.py` un bloque latente de contexto SSM tras feature flag `HRV_SSM_REASON_TEXT_ENABLED`, default `0`; sin filtro por deporte, no se activa en Fase 1). Siguiente mejora natural: evaluar outcome específico por deporte en lugar de un target combinado.`

## Vista Operativa Primaria
- Modo: `global_with_sport_context`
- Scope recomendado: `global`
- Estado global: `candidate_go`
- Estados por deporte: `{"bike": "no_go", "run": "candidate_go"}`
- `La lectura principal puede seguir siendo global, usando la estratificación por deporte como contexto.`

## Calibración
- `{"status": "undercovered", "target_coverage": 0.9, "observed_coverage": 0.8118811881188119, "delta": -0.08811881188118809, "ci95": [0.7219221173952687, 0.8827724430175964], "coverage_n": 101}`

## Diagnóstico Outcome
- Modo de fallo principal: `fds_available`
- Normalización outcome: `{"mode": "sport_family_abs_median_scale", "applied": true, "per_sport_reference": {"bike": 6.0, "hike": 0.1, "mixed": 0.2, "mobility": 0.7, "run": 3.75, "strength": 5.5, "swim": 1.4}}`
- Outcomes comparables evaluados: `208`
- Filas con `FDS`: `152`
- Filas con `FDS-lite`: `11`
- Filas con `baseline_n >= 3`: `153`
- Filas con `baseline_n >= 3` bloqueadas por MAD=0: `1`
- Share de `outcome_oriented == 0`: `0.000`
- Valores más frecuentes del outcome orientado: `{"-0.88": 3, "1.0": 3, "-0.13333333333333333": 2, "-3.714285714285715": 2, "-1.4666666666666668": 2, "-2.8266666666666667": 2, "-3.2800000000000002": 2, "1.4166666666666667": 2}`

## Auditoría de Signo
- SSM como `goodness`: rho=`0.099`; soporte=`True`; semántica preferida=`goodness`
- Rolling 7d como `goodness`: rho=`0.121`; soporte=`True`; semántica preferida=`goodness`

## Comparador Estructural
- Estado comparador: `prefer_current_banister`
- Pares alineados actual vs alternativo: `200`
- Modelo actual (banister_2state) holdout MAE: `1.538`
- Modelo alternativo (banister_hrv_only) holdout MAE: `1.538`
- Load sobre innovaciones HRV-only: `{"status": "no_evidence_load_explains_innovations", "n_rows": 345, "coef": -1.8195950505725642e-05, "se": 0.00033846930993630025, "p_value": 0.9571580518412962, "r2": 8.425838339709557e-06}`

## Sensibilidad Phi
- Estado sensibilidad: `current_phi_best_or_tied`
- Phi actual: `0.985`
- Mejor phi en grid: `0.9`
- MAE holdout actual: `1.538`
- MAE holdout mejor phi: `1.537`
- Grid: `[{"phi": 0.85, "aligned_pairs_n": 200, "spearman_rho": 0.08934999474223322, "spearman_p_value": 0.20832032570501072, "holdout_mae": 1.5371618327649934, "holdout_rmse": 2.672239790169227, "direction_ok": true}, {"phi": 0.9, "aligned_pairs_n": 200, "spearman_rho": 0.0893874992523207, "spearman_p_value": 0.20812867113952255, "holdout_mae": 1.5369749072537715, "holdout_rmse": 2.67211816925233, "direction_ok": true}, {"phi": 0.92, "aligned_pairs_n": 200, "spearman_rho": 0.09034086389874468, "spearman_p_value": 0.20329934350410656, "holdout_mae": 1.5370091380402193, "holdout_rmse": 2.6720510444240757, "direction_ok": true}, {"phi": 0.97, "aligned_pairs_n": 200, "spearman_rho": 0.0956094974758352, "spearman_p_value": 0.1780657488254262, "holdout_mae": 1.5375001449857013, "holdout_rmse": 2.6717142260936715, "direction_ok": true}]`

## Días Discordantes
- Estado discordancia: `ok`
- Flags: `{"ssm_good_vs_load_high": 20, "ssm_bad_vs_hrv_normal": 1, "ssm_vs_gate_disagree": 32, "discordant_any": 50, "concordant_any": 150}`
- SSM MAE discordantes: `2.112` vs rolling `2.138`
- SSM MAE concordantes: `1.438` vs rolling `1.443`

## Estratificación Deporte
- Estado estratificación: `ok`
- Deportes viables: `["bike", "run"]`
- Resumen por deporte: `{"bike": {"n_pairs": 90, "ssm_holdout_mae": 0.8143237738410419, "rolling_holdout_mae": 0.7788730407216197}, "run": {"n_pairs": 110, "ssm_holdout_mae": 2.246827866612099, "rolling_holdout_mae": 2.278850337081546}}`

## Walk-Forward Por Deporte
| Deporte | n | Go/no-go | SSM holdout MAE | SSM WF MAE | Rolling holdout MAE | Rolling WF MAE |
| --- | --- | --- | --- | --- | --- | --- |
| bike | 90 | no_go | 0.814 | 1.215 | 0.779 | 1.212 |
| run | 110 | candidate_go | 2.247 | 1.528 | 2.279 | 1.446 |

## Principal Estricto Por Deporte
- `{"bike": {"n_pairs": 90, "go_no_go": "no_go"}, "run": {"n_pairs": 110, "go_no_go": "candidate_go"}}`

## Funnel Estricto
- `{"all_pairs": 342, "fds_only": 260, "no_strength": 260, "aerobic_sports_only": 200, "valid_comparison_level": 200, "baseline_n_gte_3": 200}`

## Principal Estricto
| Predictor | n | Spearman rho | p-value | Holdout MAE | WF MAE mean | WF folds | Holdout RMSE |
| --- | --- | --- | --- | --- | --- | --- | --- |
| SSM shadow | 200 | 0.099 | 0.162 | 1.538 | 1.447 | 4 | 2.672 |
| Rolling HRV 7d | 200 | 0.121 | 0.089 | 1.547 | 1.383 | 4 | 2.680 |
| Load 7d | 175 | 0.140 | 0.065 | 1.664 | 1.345 | 4 | 2.859 |
| Gate final | 188 | -0.002 | 0.980 | 1.591 | 1.375 | 4 | 2.745 |

## Comparador Sueño
- Estado comparador: `prefer_sleep_augmented`
- Pares alineados actual vs sin sueño: `200`
- Modelo con sueño holdout MAE: `1.538`
- Modelo sin sueño holdout MAE: `1.539`
- Delta MAE sin sueño - con sueño: `0.002`

## Comparador EWMA
- Estado comparador: `equivalent_holdout`
- Modelo base: `banister_2state`
- Baseline: `ewma_lnrmssd`
- Mejor alpha holdout: `0.400`
- Mejor MAE holdout EWMA: `1.534`
- Mejor MAE walk-forward EWMA: `1.457`
- Delta MAE SSM - EWMA holdout: `0.003`
- Delta MAE SSM - EWMA walk-forward: `-0.009`
- Grid: `[{"alpha": 0.05, "aligned_pairs_n": 197, "spearman_rho": 0.1254555292788709, "spearman_p_value": 0.07898715106125345, "holdout_mae": 1.5666418718970647, "holdout_rmse": 2.684709191187366, "walk_forward_status": "ok", "walk_forward_n_folds": 4, "walk_forward_mae_mean": 1.5917579246093276, "walk_forward_mae_median": 1.5619365915190042, "direction_ok": true}, {"alpha": 0.1, "aligned_pairs_n": 197, "spearman_rho": 0.13849093009008398, "spearman_p_value": 0.05228188001391928, "holdout_mae": 1.5639100459766329, "holdout_rmse": 2.6867393839946927, "walk_forward_status": "ok", "walk_forward_n_folds": 4, "walk_forward_mae_mean": 1.4884640388735049, "walk_forward_mae_median": 1.5142846048732768, "direction_ok": true}, {"alpha": 0.15, "aligned_pairs_n": 197, "spearman_rho": 0.12511253372525216, "spearman_p_value": 0.07981635008020894, "holdout_mae": 1.5578227059609002, "holdout_rmse": 2.683092749972068, "walk_forward_status": "ok", "walk_forward_n_folds": 4, "walk_forward_mae_mean": 1.463139753769932, "walk_forward_mae_median": 1.4872990892907612, "direction_ok": true}, {"alpha": 0.2, "aligned_pairs_n": 197, "spearman_rho": 0.12044638139970654, "spearman_p_value": 0.09180918069594113, "holdout_mae": 1.551302915670299, "holdout_rmse": 2.6793879604727144, "walk_forward_status": "ok", "walk_forward_n_folds": 4, "walk_forward_mae_mean": 1.4614926559095742, "walk_forward_mae_median": 1.4855230420522105, "direction_ok": true}, {"alpha": 0.3, "aligned_pairs_n": 197, "spearman_rho": 0.11279765904269355, "spearman_p_value": 0.11452971930518274, "holdout_mae": 1.5397146479306125, "holdout_rmse": 2.6750194125025892, "walk_forward_status": "ok", "walk_forward_n_folds": 4, "walk_forward_mae_mean": 1.4625640415491783, "walk_forward_mae_median": 1.4939002756139035, "direction_ok": true}, {"alpha": 0.4, "aligned_pairs_n": 197, "spearman_rho": 0.09902132504471596, "spearman_p_value": 0.16623885237513084, "holdout_mae": 1.5342627418267445, "holdout_rmse": 2.673217460777812, "walk_forward_status": "ok", "walk_forward_n_folds": 4, "walk_forward_mae_mean": 1.4565106331649866, "walk_forward_mae_median": 1.4881864543664212, "direction_ok": true}]`

## Diagnósticos Estrictos
- Redundancia vs `rolling_hrv_7d + load_7d`: `distinct_enough` (R²=0.772)
- Lag medio al outcome: `1.745` días
- Lag mediano al outcome: `1.000` días
- Nivel de comparabilidad: `{"session_group": 200}`
- Familias por deporte: `{"aerobic_long_z2__bike": 82, "aerobic_long_z2__run": 49, "aerobic_intervals__run": 37, "aerobic_short_z2__run": 24, "aerobic_intervals__bike": 8}`
- Cuartil alto de varianza: n=50 · outcome medio=0.165
- Cuartil bajo de varianza: n=50 · outcome medio=-0.081

## Baseline Trivial
- `{"median_baseline": {"n_pairs": 200, "holdout_mae": 1.4998090373644828, "holdout_rmse": 2.660047657134352}, "family_last_baseline": {"n_pairs": 200, "holdout_mae": 1.9635066824573837, "holdout_rmse": 3.365462864510324}, "bootstrap_ci": {"ssm_vs_rolling_holdout_mae": {"status": "ok", "n_iter": 1000, "delta_mae_mean": -0.010733167403599246, "delta_mae_median": -0.010879594372839585, "delta_mae_ci90": [-0.03835241975773225, 0.01631050883533641], "prob_delta_gt_0": 0.26}, "ssm_vs_median_baseline_holdout_mae": {"status": "ok", "n_iter": 1000, "delta_mae_mean": 0.03972401840221707, "delta_mae_median": 0.03994429211137157, "delta_mae_ci90": [-0.021448530466292692, 0.10098017945526282], "prob_delta_gt_0": 0.862}, "ssm_vs_family_last_baseline_holdout_mae": {"status": "ok", "n_iter": 1000, "delta_mae_mean": -0.440078292652162, "delta_mae_median": -0.4058301996350796, "delta_mae_ci90": [-1.1395648692099827, 0.17362152810270567], "prob_delta_gt_0": 0.129}, "rolling_vs_median_baseline_holdout_mae": {"status": "ok", "n_iter": 1000, "delta_mae_mean": 0.05045718580581632, "delta_mae_median": 0.0510677176532186, "delta_mae_ci90": [-0.033191460526663746, 0.13181840833500125], "prob_delta_gt_0": 0.845}, "load_vs_median_baseline_holdout_mae": {"status": "insufficient_data"}}}`

## Bootstrap CI
- `{"ssm_vs_rolling_holdout_mae": {"status": "ok", "n_iter": 1000, "delta_mae_mean": -0.010733167403599246, "delta_mae_median": -0.010879594372839585, "delta_mae_ci90": [-0.03835241975773225, 0.01631050883533641], "prob_delta_gt_0": 0.26}, "ssm_vs_median_baseline_holdout_mae": {"status": "ok", "n_iter": 1000, "delta_mae_mean": 0.03972401840221707, "delta_mae_median": 0.03994429211137157, "delta_mae_ci90": [-0.021448530466292692, 0.10098017945526282], "prob_delta_gt_0": 0.862}, "ssm_vs_family_last_baseline_holdout_mae": {"status": "ok", "n_iter": 1000, "delta_mae_mean": -0.440078292652162, "delta_mae_median": -0.4058301996350796, "delta_mae_ci90": [-1.1395648692099827, 0.17362152810270567], "prob_delta_gt_0": 0.129}, "rolling_vs_median_baseline_holdout_mae": {"status": "ok", "n_iter": 1000, "delta_mae_mean": 0.05045718580581632, "delta_mae_median": 0.0510677176532186, "delta_mae_ci90": [-0.033191460526663746, 0.13181840833500125], "prob_delta_gt_0": 0.845}, "load_vs_median_baseline_holdout_mae": {"status": "insufficient_data"}}`

## Principal Lite
- Diagnóstico intermedio: exige baseline comparable >=2 y escala `fds`/`fds_lite`, pero no gobierna promoción.
| Predictor | n | Spearman rho | p-value | Holdout MAE | WF MAE mean | WF folds | Holdout RMSE |
| --- | --- | --- | --- | --- | --- | --- | --- |
| SSM shadow | 212 | 0.120 | 0.082 | 1.533 | 1.505 | 4 | 2.647 |
| Rolling HRV 7d | 212 | 0.127 | 0.065 | 1.537 | 1.489 | 4 | 2.656 |
| Load 7d | 185 | 0.101 | 0.173 | 1.582 | 1.390 | 4 | 2.774 |
| Gate final | 198 | 0.014 | 0.842 | 1.710 | 1.403 | 4 | 2.817 |

## Exploratorio Amplio
| Predictor | n | Spearman rho | p-value | Holdout MAE | WF MAE mean | WF folds | Holdout RMSE |
| --- | --- | --- | --- | --- | --- | --- | --- |
| SSM shadow | 342 | 0.128 | 0.018 | 3.042 | 5.731 | 4 | 3.766 |
| Rolling HRV 7d | 342 | 0.191 | 0.000 | 3.520 | 5.500 | 4 | 4.101 |
| Load 7d | 290 | 0.079 | 0.182 | 1.726 | 4.920 | 4 | 2.957 |
| Gate final | 318 | -0.016 | 0.774 | 2.195 | 5.511 | 4 | 3.031 |

## Exploratorio Ventana T1-T3
- Diagnóstico exploratorio: agrega hasta 3 sesiones comparables en `t+1..t+3` para reducir ruido de un mal día puntual.
| Predictor | n | Spearman rho | p-value | Holdout MAE | WF MAE mean | WF folds | Holdout RMSE |
| --- | --- | --- | --- | --- | --- | --- | --- |
| SSM shadow | 309 | 0.046 | 0.425 | 1.654 | 4.623 | 4 | 2.094 |
| Rolling HRV 7d | 309 | 0.126 | 0.027 | 1.969 | 4.055 | 4 | 2.325 |
| Load 7d | 265 | 0.082 | 0.182 | 1.547 | 4.072 | 4 | 2.023 |
| Gate final | 289 | 0.030 | 0.616 | 1.671 | 4.574 | 4 | 2.131 |

## Go / No-Go Principal
- required_all: `{"outcome_audit_pass": true, "pairs_gte_30": true, "not_redundant_vs_simple_baselines": true, "beats_rolling_hrv_7d_holdout_mae": true}`
- required_at_least_one: `{"beats_load_7d_holdout_mae": true}`
- veto_conditions: `{"redundancy_detected": false, "too_few_pairs": false, "outcome_audit_not_pass": false, "does_not_beat_rolling_hrv_7d": false}`

## Nota
- El bloque principal estricto gobierna el go/no-go. El bloque lite ayuda a decidir si merece seguir acumulando datos, pero no justifica promoción.
- El bloque exploratorio conserva cobertura amplia, pero no justifica promoción.
- Este reporte es Fase 1 sombra. No recolorea el gate ni modifica `FINAL.csv`.
