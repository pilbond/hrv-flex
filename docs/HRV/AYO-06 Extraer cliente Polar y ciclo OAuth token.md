## Objetivo

Separar la frontera de red hacia Polar y cerrar la ambiguedad restante del ciclo OAuth/token sin mezclarlo con el flujo productivo oficial de `web_ui.py`.

## Alcance

### Checkpoint A. Frontera Polar

- mover `api_request`
- mover `register_user_if_needed`
- mover `list_exercises`
- mover `get_exercise_with_samples`
- mover `fetch_polar_sleep`
- mover `fetch_polar_nightly_recharge`
- consolidar `_iso_duration_to_minutes` con `polar_utils.parse_duration_to_minutes`

### Checkpoint B. OAuth/token dev-only

- mover `load_tokens` a `oauth_utils.py`
- mover `build_auth_url` a `oauth_utils.py`
- decidir el destino final de `do_oauth_flow`
- dejar explicito que el flujo oficial de produccion sigue siendo el web OAuth

## Decision de arquitectura

- `polar_client.py` y `polar_sessions.py` coexisten
- no se introduce dependencia nueva entre ambos modulos en esta tarea
- cualquier unificacion HTTP adicional queda fuera de alcance salvo necesidad clara

## Criterios de aceptacion

1. La frontera Polar queda fuera del entrypoint.
2. `do_oauth_flow` queda marcado o movido como dev-only, no ambiguo.
3. El flujo productivo via `web_ui.py` no cambia.
4. El duplicado `_iso_duration_to_minutes` desaparece.

## Regression Gate

- `python -m py_compile` sobre `polar_client.py`, `oauth_utils.py`, `polar_hrv_automation.py`, `web_ui.py`
- tests unitarios con `requests` mockeado
- smoke test de registro de usuario
- smoke test de import de `web_ui.py`
