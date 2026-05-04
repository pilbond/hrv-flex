## Objetivo

Cerrar la refactorizacion con una capa de tests de integracion y no regresion que verifique que el contrato operativo sigue intacto.

## Alcance

- tests de integracion del flujo principal refactorizado
- test de compatibilidad del entrypoint CLI
- comprobaciones basicas sobre outputs y paths esperados
- smoke tests finales sobre modulos compartidos con `web_ui.py`

## Criterios de aceptacion

1. La refactorizacion completa pasa la bateria minima de regresion.
2. El CLI sigue siendo invocable por la UI sin cambios de contrato.
3. No aparecen roturas basicas en imports, rutas o payloads compartidos.

## Regression Gate

- ejecucion de la suite final acordada
- import smoke de `polar_hrv_automation.py`, `web_ui.py`, `build_sessions.py`
- comprobacion de no regresion en outputs/path base
