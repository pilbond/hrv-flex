# PCV-04 Coach semanal estructurado en producto

Estado: implementada

## Resultado adoptado

`build_sessions.py` genera `ENDURANCE_HRV_weekly_coach.json` como sidecar
semanal canonico, determinista y reproducible. Resume la semana calculable y
expone, entre otros, periodo, cobertura, tipo de semana, carga, riesgo de
progresion, tendencia HRV, calidad de datos y contexto retrospectivo de Z3.

El sidecar consume las capas existentes de sesiones, distribucion semanal,
HRV y auditoria. No modifica `FINAL`, `DASHBOARD` ni el gate diario.

`PCV-05` anadio `planning_note` y `PCV-06` expuso el resultado en la UI a
traves de `/api/status`.

## Trazabilidad

- `build_sessions.py`
- `ENDURANCE_HRV_weekly_coach.json`
- `docs/contracts/ENDURANCE_HRV_Diccionario.md`
- `docs/contracts/ENDURANCE_HRV_Estructura.md`
- `tests/test_build_sessions_contract.py`

