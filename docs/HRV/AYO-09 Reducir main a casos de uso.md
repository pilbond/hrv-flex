## Objetivo

Reducir `main()` a un coordinador fino de casos de uso, eliminando ramas repetidas y concentracion excesiva de decisiones.

## Alcance

- introducir funciones de coordinacion tipo:
  - `resolve_date_range_from_args(...)`
  - `sync_hrv_range(...)`
  - `sync_sleep_only(...)`
  - `process_rr_files(...)`
  - `sync_intervals_wellness(...)`
  - `refresh_sleep_and_outputs(...)`
- reorganizar salidas tempranas repetidas
- dejar el entrypoint claramente por debajo del tamaño actual

## Ownership

- `refresh_sleep_and_outputs(...)` debe quedar como helper de caso de uso
- no debe hundirse en `sleep_store.py` ni en `pipeline_runner.py`

## Criterios de aceptacion

1. `main()` pasa a coordinar en vez de implementar detalles de red, persistencia y reporting.
2. El CLI mantiene su contrato actual.
3. El flujo sigue siendo entendible y testeable por ramas.

## Regression Gate

- `python -m py_compile` sobre `polar_hrv_automation.py`
- smoke tests con mocks para:
  - caso sin RR nuevos
  - caso con RR nuevos y `--process`
- smoke test de import de `web_ui.py`
