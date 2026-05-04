
## Objetivo

Cerrar la fase 0 de `AYO-11` con una lista acotada de consumidores, el mapa de imports que se romperia al mover modulos, y una decision explicita entre `opcion A` y `opcion B`.

## Decision de fase 0

**Decision recomendada: opcion B.**

Motivo:

- la lista de consumidores esta cerrada y es ejecutable;
- la mayoria de dependencias afectadas son modulos internos reutilizables, no entrypoints canonicos;
- `config.py` tiene un contrato especifico de `importlib.reload()` que se puede resolver de forma directa moviendolo a `hrv_app.config` y actualizando su test;
- el coste es alto, pero la ganancia estructural justifica el paquete interno.

## Criterio de estilo para la opcion B

- dentro de `hrv_app/`, usar imports relativos;
- fuera del paquete, usar imports absolutos `hrv_app.*`;
- no introducir wrappers `import *` como solucion general;
- reservar wrappers solo para una compatibilidad transitoria documentada si aparece un bloqueo real.

## Orden recomendado de migracion

Secuencia segura sugerida para ejecutar la opcion B:

1. `polar_utils.py`
2. `oauth_utils.py`
3. `pipeline_runner.py`
4. `config.py`
5. `cli_reporting.py`
6. `polar_client.py`
7. `polar_sessions.py`
8. `dropbox_rr.py`
9. `polar_oauth_local.py`
10. `intervals_sync.py`
11. `sleep_store.py`
12. `hrv_sync_flow.py`
13. actualizar entrypoints raiz, `analysis/` y tests de contrato

Motivo:

- los helpers base deben moverse antes que los modulos que dependen de ellos;
- `config.py` depende de `polar_utils` y conviene resolverlo temprano para no dejar deuda abierta;
- `hrv_sync_flow.py` es el nodo mas conectado y debe ir al final de la cadena interna;
- `analysis/` y los tests deben actualizarse una vez que exista el paquete destino completo.

## Inventario de consumidores

### Entrypoints y consumidores de produccion

| consumidor | tipo | import actual | destino previsto | accion | riesgo |
| --- | --- | --- | --- | --- | --- |
| `web_ui.py` | `entrypoint` | `polar_utils`, `oauth_utils` | `hrv_app.polar_utils`, `hrv_app.oauth_utils` | migrar imports; mantener `subprocess` a entrypoints raiz | medio |
| `polar_hrv_automation.py` | `entrypoint` | `config`, `polar_client`, `polar_oauth_local`, `hrv_sync_flow` | `hrv_app.config`, `hrv_app.polar_client`, `hrv_app.polar_oauth_local`, `hrv_app.hrv_sync_flow` | migrar imports de produccion | alto |
| `build_sessions.py` | `entrypoint` | `polar_sessions` | `hrv_app.polar_sessions` | migrar import del builder | medio |
| `analysis/session_analysis_pipeline.py` | `analysis` | `build_sessions`, `hrv_sync_flow`, `polar_client`, `polar_oauth_local`, `polar_sessions`, `polar_utils` | `build_sessions` queda en raiz; resto a `hrv_app.*` | migrar imports de analisis y conservar el builder raiz | alto |
| `analysis/fit_terrain_utils.py` | `analysis` | `polar_utils` | `hrv_app.polar_utils` | migrar helper compartido | medio |
| `analysis/training_audit_utils.py` | `analysis` | `polar_utils` | `hrv_app.polar_utils` | migrar helper compartido | medio |

### Modulos internos candidatos al paquete

| consumidor | tipo | import actual | destino previsto | accion | riesgo |
| --- | --- | --- | --- | --- | --- |
| `config.py` | `modulo interno` | `polar_utils` | `hrv_app.polar_utils` | mover a `hrv_app/config.py` | alto |
| `cli_reporting.py` | `modulo interno` | `config` | `hrv_app.config` | mover a `hrv_app/` | medio |
| `dropbox_rr.py` | `modulo interno` | `config` | `hrv_app.config` | mover a `hrv_app/` | medio |
| `hrv_sync_flow.py` | `modulo interno` | `cli_reporting`, `config`, `dropbox_rr`, `intervals_sync`, `pipeline_runner`, `polar_client`, `polar_utils`, `sleep_store` | `hrv_app.cli_reporting`, `hrv_app.config`, `hrv_app.dropbox_rr`, `hrv_app.intervals_sync`, `hrv_app.pipeline_runner`, `hrv_app.polar_client`, `hrv_app.polar_utils`, `hrv_app.sleep_store` | mover y actualizar imports cruzados | alto |
| `intervals_sync.py` | `modulo interno` | `cli_reporting`, `config`, `oauth_utils`, `polar_utils` | `hrv_app.cli_reporting`, `hrv_app.config`, `hrv_app.oauth_utils`, `hrv_app.polar_utils` | mover a `hrv_app/` | medio |
| `oauth_utils.py` | `modulo interno` | ninguno de los candidatos | ninguno | puede moverse sin dependencias internas | bajo |
| `pipeline_runner.py` | `modulo interno` | ninguno de los candidatos | ninguno | puede moverse sin dependencias internas | bajo |
| `polar_client.py` | `modulo interno` | `config`, `oauth_utils`, `polar_utils` | `hrv_app.config`, `hrv_app.oauth_utils`, `hrv_app.polar_utils` | mover a `hrv_app/` | medio |
| `polar_oauth_local.py` | `modulo interno` | `config`, `oauth_utils` | `hrv_app.config`, `hrv_app.oauth_utils` | mover a `hrv_app/` | medio-alto |
| `polar_sessions.py` | `modulo interno` | `polar_utils` | `hrv_app.polar_utils` | mover a `hrv_app/` | medio |
| `polar_utils.py` | `modulo interno` | ninguno de los candidatos | ninguno | mover a `hrv_app/` como helper base | bajo |
| `sleep_store.py` | `modulo interno` | `config`, `polar_client`, `polar_utils` | `hrv_app.config`, `hrv_app.polar_client`, `hrv_app.polar_utils` | mover a `hrv_app/` | medio-alto |

### Tests de contrato afectados

| consumidor | tipo | import actual | destino previsto | accion | riesgo |
| --- | --- | --- | --- | --- | --- |
| `tests/test_config_contract.py` | `test` | `import config` + `importlib.reload(config)` | `import hrv_app.config as config` | actualizar el contrato de recarga | alto |
| `tests/test_analysis_contract.py` | `test` | `analysis.session_analysis_pipeline`, `analysis.fit_terrain_utils`, `analysis.training_audit_utils`, `analysis.session_cost_model` | `analysis.*` con dependencia indirecta sobre `hrv_app.*` | verificar tras migrar los modulos internos | medio |
| `tests/test_build_sessions_contract.py` | `test` | `polar_sessions` | `hrv_app.polar_sessions` | migrar import directo | medio |
| `tests/test_cli_reporting_contract.py` | `test` | `cli_reporting` | `hrv_app.cli_reporting` | migrar import directo | medio |
| `tests/test_dropbox_rr_contract.py` | `test` | `dropbox_rr` | `hrv_app.dropbox_rr` | migrar import directo | medio |
| `tests/test_hrv_sync_flow_contract.py` | `test` | `hrv_sync_flow` | `hrv_app.hrv_sync_flow` | migrar import directo | alto |
| `tests/test_intervals_sync_contract.py` | `test` | `intervals_sync` | `hrv_app.intervals_sync` | migrar import directo | medio |
| `tests/test_pipeline_runner_contract.py` | `test` | `pipeline_runner` | `hrv_app.pipeline_runner` | migrar import directo | bajo |
| `tests/test_polar_client_contract.py` | `test` | `polar_client` | `hrv_app.polar_client` | migrar import directo | medio |
| `tests/test_polar_oauth_local_contract.py` | `test` | `polar_oauth_local` | `hrv_app.polar_oauth_local` | migrar import directo | medio-alto |
| `tests/test_sleep_store_contract.py` | `test` | `sleep_store` | `hrv_app.sleep_store` | migrar import directo | medio-alto |
| `tests/test_polar_hrv_automation_import.py` | `test` | `importlib.import_module("polar_hrv_automation")`, `importlib.import_module("web_ui")`, `importlib.import_module("build_sessions")` | entrypoints raiz que importan `hrv_app.*` | smoke de import para validar que el arranque sigue limpio tras la migracion | medio |

## Mapa de imports cruzados

### Antes del movimiento

- `config.py` -> `polar_utils`
- `cli_reporting.py` -> `config`
- `dropbox_rr.py` -> `config`
- `hrv_sync_flow.py` -> `cli_reporting`, `config`, `dropbox_rr`, `intervals_sync`, `pipeline_runner`, `polar_client`, `polar_utils`, `sleep_store`
- `intervals_sync.py` -> `cli_reporting`, `config`, `oauth_utils`, `polar_utils`
- `polar_client.py` -> `config`, `oauth_utils`, `polar_utils`
- `polar_oauth_local.py` -> `config`, `oauth_utils`
- `polar_sessions.py` -> `polar_utils`
- `sleep_store.py` -> `config`, `polar_client`, `polar_utils`
- `analysis/session_analysis_pipeline.py` -> `build_sessions`, `hrv_sync_flow`, `polar_client`, `polar_oauth_local`, `polar_sessions`, `polar_utils`
- `analysis/fit_terrain_utils.py` -> `polar_utils`
- `analysis/training_audit_utils.py` -> `polar_utils`

### Despues del movimiento

- dentro de `hrv_app/`, todos los imports entre modulos candidatos pasan a ser relativos;
- `analysis/` y los tests usan imports absolutos `hrv_app.*`;
- `build_sessions.py`, `web_ui.py`, `polar_hrv_automation.py` y los demas entrypoints canonicos quedan en raiz, pero importan `hrv_app.*` donde corresponda;
- `build_sessions.py` sigue siendo entrypoint raiz, no se convierte en modulo interno.

### Contrato preciso de `reload(config)`

Si `config.py` pasa a `hrv_app/config.py`, el test debe hacer:

```python
import importlib
with patch.dict(...):
    import hrv_app.config as config
    config = importlib.reload(config)
```

La idea es mantener el `import` dentro del cuerpo del test, despues de preparar `patch.dict`, y pasar a `reload()` el objeto modulo ya importado. No hace falta usar el nombre textual `hrv_app.config` como argumento.

## Criterio de reversibilidad

Si durante la migracion de la opcion B falla cualquiera de estos puntos:

- smoke de import de un entrypoint raiz,
- `tests/test_config_contract.py`,
- `tests/test_polar_hrv_automation_import.py`,
- `tests/test_analysis_contract.py`,

entonces la fase en curso debe detenerse y revertirse antes de continuar con el siguiente modulo. Basta con que falle uno solo de esos puntos.

## Resumen operativo

### Se puede ejecutar opcion B porque:

- el inventario de consumidores esta acotado;
- no hay dependencias ocultas fuera de los archivos listados;
- la compatibilidad con `reload()` de `config.py` se puede resolver de forma explicita;
- el arranque de produccion puede seguir usando `python web_ui.py` si el entrypoint pasa a importar desde `hrv_app.*`.

### No se recomienda mantener wrappers largos porque:

- el objetivo de `ARQ-02` es que la estructura represente la frontera real;
- los wrappers prolongarian la deuda y esconderian el cambio estructural;
- la lista de consumidores ya es lo bastante cerrada como para migrarlos de forma directa.

## Estado de migracion ejecutada

Modulos ya trasladados a `hrv_app/`:

- `polar_utils.py`
- `oauth_utils.py`
- `pipeline_runner.py`
- `dropbox_rr.py`
- `config.py`
- `cli_reporting.py`
- `polar_client.py`
- `sleep_store.py`
- `polar_oauth_local.py`
- `intervals_sync.py`
- `hrv_sync_flow.py`
- `polar_sessions.py`

Consumers actualizados:

- `web_ui.py`
- `polar_hrv_automation.py`
- `build_sessions.py`
- `analysis/session_analysis_pipeline.py`
- `analysis/fit_terrain_utils.py`
- `analysis/training_audit_utils.py`
- `tests/test_config_contract.py`
- `tests/test_build_sessions_contract.py`
- `tests/test_cli_reporting_contract.py`
- `tests/test_dropbox_rr_contract.py`
- `tests/test_polar_client_contract.py`
- `tests/test_polar_oauth_local_contract.py`
- `tests/test_intervals_sync_contract.py`
- `tests/test_sleep_store_contract.py`
- `tests/test_hrv_sync_flow_contract.py`

## Fuera de alcance de esta fase 0

- `canvas-tool.py` es tooling local y no forma parte del runtime HRV;
- los directorios de ruido o temporales de raiz no afectan a este inventario de imports;
- los scripts auxiliares manuales se trataran en la fase de limpieza o en una subtarea separada.

## Notas de completitud

- `analysis/session_analysis_pipeline.py` tambien importa `fit_speed_utils` y `fit_terrain_utils`, ambos ya residiendo en `analysis/`; se documentan aqui como dependencias locales sin accion de migracion.
- `tests/test_build_hrv_final_dashboard_contract.py` queda fuera de alcance de la migracion porque `build_hrv_final_dashboard.py` no depende de los modulos candidatos del paquete interno.
- `tests/test_analysis_contract.py` no importa directamente los modulos que se mueven, pero si depende de `analysis/session_analysis_pipeline.py`, por lo que su verificacion pertenece al gate posterior de la opcion B.
- `tests/test_polar_hrv_automation_import.py` no es consumidor de produccion; es un smoke de entrypoints que debe mantenerse en el inventario porque valida el arranque raiz tras la migracion.
