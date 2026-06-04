# Batería de Outcomes Alternativos — SSM Fase 1

## Conclusión
- Estado: `ssm_wins_at_least_one_outcome`
- Veredictos: `{"lnrmssd_next_day": "ssm_wins", "wellness_next_day": "rolling_wins"}`
- El SSM muestra ventaja predictiva en al menos un outcome alternativo. Ver detalles por outcome para evaluar si justifica revisión de Fase 2.

## Outcome: `lnRMSSD día siguiente`
- Pares disponibles: `333`
- Veredicto: `ssm_wins`
- SSM supera AR(1): `True`

| Predictor | n | Spearman rho | p-value | Holdout MAE | WF MAE | WF folds |
| --- | --- | --- | --- | --- | --- | --- |
| SSM shadow | 333 | 0.538 | 0.000 | 0.305 | 0.341 | 4 |
| Rolling HRV 7d | 333 | 0.543 | 0.000 | 0.313 | 0.282 | 4 |
| AR(1) lnRMSSD[t] | 321 | 0.512 | 0.000 | 0.323 | 0.308 | 4 |
| Innovación SSM[t] | 304 | 0.274 | 0.000 | 0.314 | 0.324 | 4 |
| Load 7d | 279 | 0.376 | 0.000 | 0.316 | 0.330 | 4 |
- Veredicto innovación: `innovation_tied_or_loses`

- Bootstrap CI90 (MAE innovación − MAE rolling): `[-0.030484316931111394, 0.02884635171721116]`
- prob(innovación_MAE > rolling_MAE): `0.455`

- Mejor EWMA holdout: alpha=`0.05` → MAE=`0.298`
- Delta MAE (SSM − EWMA_best): `0.008`

- Bootstrap CI90 (MAE SSM − MAE rolling): `[-0.03285184599175415, 0.014853027255848701]`
- prob(SSM_MAE > rolling_MAE): `0.286`

## Outcome: `Bienestar subjetivo día siguiente (well_fatigue_raw)`
- Pares disponibles: `82`
- Veredicto: `rolling_wins`
- SSM supera AR(1): `None`

| Predictor | n | Spearman rho | p-value | Holdout MAE | WF MAE | WF folds |
| --- | --- | --- | --- | --- | --- | --- |
| SSM shadow | 82 | -0.146 | 0.192 | 0.535 | 0.450 | 3 |
| Rolling HRV 7d | 82 | -0.002 | 0.983 | 0.521 | 0.444 | 3 |
| Innovación SSM[t] | 74 | -0.080 | 0.498 | 0.520 | 0.465 | 3 |
| Load 7d | 72 | -0.048 | 0.689 | 0.498 | 0.432 | 3 |
- Veredicto innovación: `innovation_tied_or_loses`

- Bootstrap CI90 (MAE innovación − MAE rolling): `[-0.03253386241558091, 0.0406888073807299]`
- prob(innovación_MAE > rolling_MAE): `0.603`

- Bootstrap CI90 (MAE SSM − MAE rolling): `[-0.04403116089936002, 0.06384135119464672]`
- prob(SSM_MAE > rolling_MAE): `0.689`

## Nota
- Esta batería es exploratoria y no modifica el go/no-go principal de `build_hrv_ssm_validation.py`.
- AR(1) (lnRMSSD[t] como predictor de lnRMSSD[t+1]) es el baseline más difícil para HRV.
- Un SSM que no supera AR(1) no añade información sobre la dinámica temporal.
- La EWMA con alpha óptimo actúa como test de degeneración adicional.
