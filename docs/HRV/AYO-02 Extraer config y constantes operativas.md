## Objetivo

Extraer del entrypoint la configuracion global, paths canonicos, flags y constantes operativas, dejando `polar_hrv_automation.py` menos cargado y eliminando el bug actual del bloque de credenciales.

## Alcance

- mover variables de entorno y flags de runtime a `config.py`
- mover `get_production_url`
- mover `_qprint`
- ampliar `polar_utils.py` con helpers puros compartidos de fecha si sigue teniendo sentido
- corregir el bloque de credenciales para que no llame a `_print_header` durante import

## Criterios de aceptacion

1. El bloque de credenciales deja de poder fallar con `NameError`.
2. Los paths y flags canonicos quedan centralizados.
3. `env_flag` no se duplica.
4. `web_ui.py`, `build_sessions.py` y el entrypoint siguen importando sin romperse.

## Regression Gate

- `python -m py_compile` sobre `config.py`, `polar_hrv_automation.py`, `web_ui.py`
- smoke test de import de `polar_hrv_automation.py`, `web_ui.py`, `build_sessions.py`
- comprobacion de salida legible cuando faltan credenciales
