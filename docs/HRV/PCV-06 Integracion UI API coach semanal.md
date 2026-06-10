# PCV-06 Integracion UI API coach semanal

Estado: implementada

## Resultado adoptado

La UI muestra una tarjeta de coach semanal a partir de
`ENDURANCE_HRV_weekly_coach.json`. El recurso se incorpora a la respuesta de
`GET /api/status`; no se creo un endpoint adicional.

La vista expone el periodo semanal, calidad de datos, `planning_note` y el
resumen retrospectivo de Z3 disponible. Esta integracion es informativa y no
modifica `FINAL`, `DASHBOARD` ni el gate diario.

## Trazabilidad

- `web_ui.py`
- `build_sessions.py`
- `docs/contracts/ENDURANCE_HRV_Estructura.md`
- `docs/contracts/ENDURANCE_HRV_Diccionario.md`
- `tests/test_web_ui_status.py`

