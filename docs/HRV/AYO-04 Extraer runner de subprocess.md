## Objetivo

Concentrar la ejecucion de scripts externos del pipeline HRV en un modulo pequeno y testeable.

## Alcance

- mover `build_hrv_core_cmd`
- mover `run_build_hrv_final_dashboard_only`
- encapsular manejo comun de subprocess, `env`, `encoding` y errores para `build_hrv_core.py` y `build_hrv_final_dashboard.py`

## Criterios de aceptacion

1. El entrypoint deja de construir y ejecutar directamente esos subprocess principales.
2. El manejo de errores y salida queda unificado.
3. No se mueve aqui la ejecucion de `egc_to_rr.py`, que sigue perteneciendo a Dropbox RR.

## Regression Gate

- `python -m py_compile` sobre `pipeline_runner.py` y `polar_hrv_automation.py`
- smoke test de construccion de comandos
- smoke test de error de subprocess con mocks
