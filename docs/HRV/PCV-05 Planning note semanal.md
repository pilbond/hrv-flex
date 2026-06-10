# PCV-05 Planning note semanal

Estado: implementada

## Resultado adoptado

La orientacion semanal se materializa como `planning_note` dentro de
`ENDURANCE_HRV_weekly_coach.json`. La nota es corta, determinista y trazable
a las senales semanales disponibles.

`/api/status` la expone para consumo operativo y la UI la muestra dentro de la
tarjeta del coach semanal. No sustituye el informe semanal completo ni
modifica el decisor HRV.

## Mantenimiento

Si cambia la semantica del sidecar deben mantenerse alineados:

- `build_sessions.py`
- `web_ui.py`
- `analysis/WEEKLY_ANALYSIS_METHOD.md`
- `docs/prompts/informe semanal de entrenamiento.md`
- `docs/contracts/ENDURANCE_HRV_Diccionario.md`

