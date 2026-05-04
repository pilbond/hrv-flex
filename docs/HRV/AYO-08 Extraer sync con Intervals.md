## Objetivo

Separar en un modulo dedicado la integracion opcional con Intervals para evitar que cada cambio de payload o red toque el flujo principal.

## Alcance

- mover `_read_latest_master_row`
- mover `_build_intervals_payload`
- mover `_send_intervals_wellness_from_master`
- mover `fetch_intervals_activities`
- mover `_normalize_intervals_activities_payload`
- mover `_extract_activity_datetime`
- mover `_aggregate_intervals_activity_fields`
- mover `MASTER_CSV_COLS` e `INTERVALS_FIELD_MAP`

## Criterios de aceptacion

1. La integracion con Intervals queda aislada.
2. El payload wellness y los agregados de actividades siguen siendo equivalentes.
3. El entrypoint solo coordina la llamada, no implementa el detalle.

## Regression Gate

- `python -m py_compile` sobre `intervals_sync.py` y `polar_hrv_automation.py`
- test de construccion de payload
- test de lectura de ultima fila util
- smoke test de push con `requests` mockeado
