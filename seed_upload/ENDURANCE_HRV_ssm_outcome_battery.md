# Batería de Outcomes Alternativos — SSM Fase 1

## Conclusión
- Estado: `ssm_wins_at_least_one_outcome`
- Veredictos: `{"lnrmssd_next_day": "ssm_wins", "wellness_next_day": "ssm_wins"}`
- El SSM muestra ventaja predictiva en al menos un outcome alternativo. Ver detalles por outcome para evaluar si justifica revisión de Fase 2.

## Outcome: `lnRMSSD día siguiente`
- Pares disponibles: `319`
- Veredicto: `ssm_wins`
- SSM supera AR(1): `True`

| Predictor | n | Spearman rho | p-value | Holdout MAE | WF MAE | WF folds |
| --- | --- | --- | --- | --- | --- | --- |
| SSM shadow | 319 | 0.541 | 0.000 | 0.305 | 0.347 | 4 |
| Rolling HRV 7d | 319 | 0.546 | 0.000 | 0.314 | 0.281 | 4 |
| AR(1) lnRMSSD[t] | 308 | 0.511 | 0.000 | 0.325 | 0.308 | 4 |
| Innovación SSM[t] | 291 | 0.255 | 0.000 | 0.304 | 0.322 | 4 |
| Load 7d | 265 | 0.378 | 0.000 | 0.313 | 0.327 | 4 |
- Veredicto innovación: `innovation_wins`

- Bootstrap CI90 (MAE innovación − MAE rolling): `[-0.038821839352842794, 0.02035561294918723]`
- prob(innovación_MAE > rolling_MAE): `0.312`

- Mejor EWMA holdout: alpha=`0.05` → MAE=`0.295`
- Delta MAE (SSM − EWMA_best): `0.010`

- Bootstrap CI90 (MAE SSM − MAE rolling): `[-0.03274881264534613, 0.015308888532133705]`
- prob(SSM_MAE > rolling_MAE): `0.282`

## Outcome: `Bienestar subjetivo día siguiente (well_fatigue_raw)`
- Pares disponibles: `73`
- Veredicto: `ssm_wins`
- SSM supera AR(1): `None`

| Predictor | n | Spearman rho | p-value | Holdout MAE | WF MAE | WF folds |
| --- | --- | --- | --- | --- | --- | --- |
| SSM shadow | 73 | -0.127 | 0.283 | 0.610 | 0.399 | 3 |
| Rolling HRV 7d | 73 | 0.035 | 0.766 | 0.658 | 0.405 | 3 |
| Innovación SSM[t] | 65 | -0.024 | 0.849 | 0.640 | 0.430 | 3 |
| Load 7d | 63 | 0.020 | 0.874 | 0.558 | 0.378 | 3 |
- Veredicto innovación: `innovation_wins`

- Bootstrap CI90 (MAE innovación − MAE rolling): `[-0.11163514747961255, 0.002808186589020589]`
- prob(innovación_MAE > rolling_MAE): `0.062`

- Bootstrap CI90 (MAE SSM − MAE rolling): `[-0.09061515200063695, -0.002566503400981218]`
- prob(SSM_MAE > rolling_MAE): `0.043`

## Nota
- Esta batería es exploratoria y no modifica el go/no-go principal de `build_hrv_ssm_validation.py`.
- AR(1) (lnRMSSD[t] como predictor de lnRMSSD[t+1]) es el baseline más difícil para HRV.
- Un SSM que no supera AR(1) no añade información sobre la dinámica temporal.
- La EWMA con alpha óptimo actúa como test de degeneración adicional.
