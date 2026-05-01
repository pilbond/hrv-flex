## Objetivo

Aislar la persistencia y el recalculo de `ENDURANCE_HRV_sleep.csv` en un modulo propio, separado del cliente Polar y del entrypoint.

## Alcance

- mover normalizacion de sleep y nightly
- mover `_ensure_sleep_schema`
- mover `_recalculate_sleep_derived`
- mover `upsert_sleep_row`
- mover `fetch_and_upsert_sleep`
- mover `_update_sleep_for_dates`
- mover `SLEEP_COLUMNS`

## Dependencia

Debe ejecutarse despues de `AYO-06`, porque `fetch_and_upsert_sleep` depende de la frontera Polar ya extraida.

## Criterios de aceptacion

1. El schema y el upsert de `sleep.csv` quedan encapsulados.
2. El entrypoint deja de contener la mayor parte de la logica de sleep.
3. Se conservan los percentiles derivados y el comportamiento actual.
4. La obtencion de Polar sleep prueba primero la fecha solicitada y, si no hay datos, el dia anterior como fallback operativo.

## Regression Gate

- `python -m py_compile` sobre `sleep_store.py` y `polar_hrv_automation.py`
- test de upsert sobre CSV temporal
- test de schema minimo
- test de recalculo derivado
- test de fallback de sleep exacto + dia anterior
