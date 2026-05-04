## Objetivo

Reducir el acoplamiento operativo de `polar_hrv_automation.py` separando responsabilidades en modulos pequenos y casos de uso explicitos, sin romper el contrato actual del repositorio:

- mismo entrypoint CLI,
- mismos outputs canonicos,
- mismas rutas base,
- mismo flujo Dropbox primero y Polar como fallback,
- misma compatibilidad con Python `3.11`.

La tarea no busca rehacer la logica HRV ni cambiar `build_hrv_core.py` o `build_hrv_final_dashboard.py`. Busca ordenar la capa operativa que hoy orquesta OAuth, red, sleep, RR, subprocess, reporting CLI e integracion Intervals en un unico fichero.

## Estado documental

Esta nota mezcla dos capas:

- el diagnostico y la evidencia usados para justificar la refactorizacion;
- y un cierre de estado con el resultado ejecutado.

Regla de lectura:

- las secciones de inventario, lineas y responsabilidades del entrypoint describen el estado previo al refactor y se conservan como evidencia historica;
- el estado operativo vigente del repo debe leerse en `AGENTS.MD` y `docs/contracts/`.

## Estado tras ejecucion de AYO-01

La refactorizacion se ejecuto manteniendo el contrato operativo:

- `polar_hrv_automation.py` queda como entrypoint fino;
- `hrv_sync_flow.py` concentra el caso de uso principal;
- `config.py` centraliza runtime y constantes;
- `dropbox_rr.py` concentra la cobertura RR desde Dropbox;
- `polar_client.py` concentra el acceso HTTP a Polar;
- `polar_oauth_local.py` concentra el flujo OAuth local `dev-only`;
- `sleep_store.py` concentra la persistencia y recalculo de `ENDURANCE_HRV_sleep.csv`;
- `intervals_sync.py` concentra la sync opcional con Intervals;
- `cli_reporting.py` concentra el reporting CLI;
- `pipeline_runner.py` concentra la ejecucion de builders.

El contrato no cambia:

- mismo entrypoint CLI,
- mismos outputs canonicos,
- Dropbox sigue siendo la fuente principal esperada de RR y Polar el fallback,
- mismo alcance N=1,
- misma compatibilidad con Python `3.11`.

## Tesis central

La critica de que `polar_hrv_automation.py` es demasiado grande y mezcla responsabilidades es correcta.

No es solo un problema estetico de longitud. Es un problema real de acoplamiento entre:

- infraestructura y runtime,
- cliente Polar,
- importacion Dropbox RR,
- persistencia de sleep,
- sync a Intervals,
- reporting CLI,
- y orquestacion del pipeline.

Cuando todas esas capas viven en el mismo modulo, cada cambio pequeno tiene demasiada superficie de riesgo y el testing aislado se vuelve innecesariamente dificil.

## Evidencia observada en el repo

### Tamano

En el baseline previo al refactor, `polar_hrv_automation.py` tenia unas `2307` lineas.

Eso por si solo no condena el archivo, pero el reparto interno confirma el problema.

### Mezcla de responsabilidades

En [polar_hrv_automation.py](/C:/Pilbond/polar-hrv-automation/polar_hrv_automation.py) conviven bloques de naturaleza distinta:

- OAuth local interactivo:
  - `OAuthCallbackHandler`
  - `start_callback_server`
  - `do_oauth_flow`
- cliente Polar:
  - `api_request`
  - `list_exercises`
  - `get_exercise_with_samples`
  - `fetch_polar_sleep`
  - `fetch_polar_nightly_recharge`
- importacion Dropbox RR:
  - `_scan_rr_files_by_date`
  - `_compute_target_missing_dates`
  - `_run_dropbox_rr_import_for_dates`
- almacenamiento y recalculo de `sleep.csv`:
  - `_ensure_sleep_schema`
  - `_recalculate_sleep_derived`
  - `upsert_sleep_row`
  - `_update_sleep_for_dates`
- sync con Intervals:
  - `_build_intervals_payload`
  - `_send_intervals_wellness_from_master`
  - `fetch_intervals_activities`
- presentacion CLI:
  - `_print_header`
  - `_print_sync_completed`
  - `show_last_daily_summary`
  - `show_last_7_days_summary`
- orquestacion end-to-end:
  - `main()`

Ademas, el propio repo ya apunta en esa direccion:

- [oauth_utils.py](/C:/Pilbond/polar-hrv-automation/oauth_utils.py) ya extrae parte del flujo OAuth y persistencia de tokens.
- [polar_utils.py](/C:/Pilbond/polar-hrv-automation/polar_utils.py) ya extrae helpers reutilizables.
- [polar_sessions.py](/C:/Pilbond/polar-hrv-automation/polar_sessions.py) ya es un precedente claro de extraccion de logica Polar a un modulo dedicado, con cliente/utilidades y procesamiento mecanico reutilizable.

La separacion ya empezo, pero se quedo a medio camino.

**Alcance respecto a `web_ui.py`:** `web_ui.py` no se refactoriza en AYO-01 y no se esperan cambios funcionales en sus endpoints ni en su contrato HTTP. Pero no esta completamente aislado:

- consume `oauth_utils.py` y `polar_utils.py`;
- depende de que el entrypoint CLI siga siendo invocable por subprocess;
- y por tanto puede verse afectado indirectamente si cambian modulos compartidos.

Regla operativa:

- AYO-01 no debe abrir trabajo de refactor dentro de `web_ui.py`;
- pero cualquier cambio en modulos compartidos debe pasar al menos un smoke test de import y un smoke test basico del flujo OAuth web o del arranque de la app.

### Inventario de extraccion actual

Estado a 2026-04-12 (`polar_hrv_automation.py`: 2307 lineas).

#### Ya correctamente extraido

**`oauth_utils.py` — 127 lineas**

| Funcion | Proposito |
|---------|-----------|
| `build_basic_auth_header` | Header Basic Auth para token exchange |
| `exchange_code_for_token` | Intercambio de code → token |
| `save_json_atomic` | Escritura atomica de tokens a disco |
| `register_polar_user` | Registro de usuario con retry 5xx |

`register_user_if_needed` (linea 740 del entrypoint) es un thin wrapper sobre `register_polar_user`. Debe moverse a `polar_client.py`.

**`polar_utils.py` — 99 lineas**

| Funcion | Proposito |
|---------|-----------|
| `get_field_variant` | Lookup con variantes de clave en dicts |
| `parse_float` | Parser float robusto |
| `parse_duration_to_minutes` | Parser ISO duration → minutos |
| `weighted_mean` | Media ponderada |
| `env_flag` | Env var → bool |
| `response_excerpt` | Truncar texto de respuesta HTTP |

**`polar_sessions.py` — 391 lineas**

| Componente | Proposito |
|-----------|-----------|
| `PolarSessionClient` | Cliente de sesiones para session matching y mecanica |
| `match_polar_exercise` | Empareja ejercicio Polar con sesion Intervals |
| `extract_mechanical_metrics` | Metricas mecanicas desde JSON ejercicio |
| `extract_mechanical_metrics_from_fit_file` | Metricas desde FIT |
| `parse_polar_local_datetime` | Parser datetime Polar |

No importado por `polar_hrv_automation.py`. Usado por `build_sessions.py` y `analysis/`.

Solapamiento funcional activo con el entrypoint: `PolarSessionClient.list_exercises()` (linea 344) y `.get_exercise_with_samples()` (linea 350) duplican las funciones del mismo nombre en el entrypoint (lineas 760 y 764). `_load_access_token()` (linea 306) duplica `load_tokens` (linea 1528). Ver decision de alcance 2 y AYO-06.

#### Parcialmente extraido — candidatos a completar

- `load_tokens` (linea 1528): contraparte parcial de `save_json_atomic`; mover a `oauth_utils.py` en AYO-06.
- `build_auth_url` (linea 692): utilidad OAuth generica; mover a `oauth_utils.py` en AYO-06.
- `_parse_yyyy_mm_dd` (linea 276): helper de fecha puro usado por `dropbox_rr`, `sleep_store` e `intervals_sync`; mover a `polar_utils.py` en AYO-02.
- `_iso_to_dt` (linea 258): convierte ISO string a datetime local; usada por `passes_filters` (se queda en entrypoint) pero puede necesitarse en `polar_client`; mover a `polar_utils.py` en AYO-02.

Matiz:

- `_load_access_token()` en `polar_sessions.py` no es un duplicado exacto de `load_tokens`;
- el solapamiento es parcial: ambos resuelven expiracion y lectura de token, pero `load_tokens` devuelve tambien `x_user_id`;
- por tanto, la extraccion debe decidir si converge en un loader comun parametrizable o si se mantienen dos helpers con contratos distintos y documentados.

#### Lo que sigue en el entrypoint por modulo propuesto

**`cli_reporting.py` — AYO-03**

| Funcion | Linea | Notas |
|---------|-------|-------|
| `_get_color_emoji` | 434 | Depende de `COLOR_EMOJI` |
| `_get_gate_emoji` | 439 | Depende de `GATE_EMOJI` |
| `_format_metric` | 458 | Depende de `PANDAS_AVAILABLE` |
| `_print_header` | 588 | Depende de `QUIET` via `_qprint` |
| `_print_divider` | 603 | |
| `_print_sync_completed` | 615 | |
| `_print_no_rr_files` | 629 | |
| `_print_master_already_updated` | 639 | |
| `show_last_daily_summary` | 1599 | Lee `FINAL_PATH` y `CORE_PATH` |
| `show_last_7_days_summary` | 1679 | |
| `show_latest_hrv_summaries` | 1733 | Wrapper de las dos anteriores |

**`dropbox_rr.py` — AYO-05**

| Funcion | Linea | Notas |
|---------|-------|-------|
| `_extract_date_from_rr_filename` | 285 | |
| `_scan_rr_files_by_date` | 293 | |
| `_iter_dates` | 339 | Helper generico de fechas |
| `_compute_target_missing_dates` | 348 | |
| `_run_dropbox_rr_import_for_dates` | 358 | Lanza subprocess a `egc_to_rr.py` |

**`intervals_sync.py` — AYO-08**

| Funcion | Linea | Notas |
|---------|-------|-------|
| `_intervals_api_root` | 228 | |
| `_normalize_color_value` | 483 | |
| `_read_latest_master_row` | 509 | |
| `_build_intervals_payload` | 533 | |
| `_send_intervals_wellness_from_master` | 547 | |
| `_normalize_intervals_activities_payload` | 1100 | |
| `fetch_intervals_activities` | 1111 | |
| `_extract_activity_datetime` | 1128 | |
| `_aggregate_intervals_activity_fields` | 1137 | |

**`sleep_store.py` — AYO-07**

| Funcion | Linea | Notas |
|---------|-------|-------|
| `_normalize_sleep_minutes` | 832 | |
| `_normalize_resp_rate` | 853 | |
| `_normalize_pct` | 866 | |
| `_find_first_value` | 875 | |
| `_extract_interruptions_counts` | 899 | |
| `_extract_sleep_fields` | 967 | |
| `_extract_nightly_fields` | 1035 | |
| `_ensure_sleep_schema` | 1214 | |
| `_recalculate_sleep_derived` | 1224 | Requiere pandas |
| `upsert_sleep_row` | 1263 | |
| `_polar_sleep_date_candidates` | 1297 | |
| `fetch_and_upsert_sleep` | 1305 | Llama a `polar_client`; AYO-07 despues de AYO-06 |
| `_update_sleep_for_dates` | 1353 | |
| `_today_date` | 1375 | |
| `_default_sleep_refresh_dates` | 1379 | |

**`polar_client.py` — AYO-06**

| Funcion | Linea | Notas |
|---------|-------|-------|
| `api_request` | 716 | HTTP wrapper |
| `register_user_if_needed` | 740 | Thin wrapper sobre `register_polar_user` |
| `list_exercises` | 760 | |
| `get_exercise_with_samples` | 764 | |
| `fetch_polar_sleep` | 1074 | |
| `fetch_polar_nightly_recharge` | 1087 | |
| `_normalize_key` | 774 | Helper interno |
| `_parse_iso_datetime` | 778 | Se queda en `polar_client`: es especifica de respuestas Polar (formato y timezone); `_iso_to_dt` (→ `polar_utils`) es el helper generico de conversion |
| `_minutes_between` | 792 | |
| `_iso_duration_to_minutes` | 803 | **Duplicado** de `parse_duration_to_minutes`; eliminar al extraer |

**`pipeline_runner.py` — AYO-04**

| Funcion | Linea | Notas |
|---------|-------|-------|
| `build_hrv_core_cmd` | 1757 | |
| `run_build_hrv_final_dashboard_only` | 1765 | |

**Se quedan en el entrypoint o requieren decision explicita**

| Funcion | Linea | Decision recomendada |
|---------|-------|---------------------|
| `_CallbackState` | 646 | Dev-only; anotar o mover a `oauth_utils.py` |
| `OAuthCallbackHandler` | 653 | Dev-only; igual |
| `start_callback_server` | 675 | Dev-only; igual |
| `get_production_url` | 703 | Mover a `config.py` |
| `do_oauth_flow` | 1482 | Dev-only; NO en produccion |
| `get_last_date_from_master` | 1548 | Quedarse en entrypoint |
| `get_existing_dates_from_master` | 1571 | Candidato a `dropbox_rr.py` |
| `calculate_missing_days` | 1738 | Orquestacion; quedarse |
| `extract_rr_ms` | 1384 | Quedarse |
| `write_rr_csv` | 1407 | Quedarse |
| `passes_filters` | 1416 | Quedarse |
| `_refresh_sleep_and_outputs` | 1794 | Caso de uso; quedarse en entrypoint |
| `main()` | 1801 | Objetivo de AYO-09 |

#### Resumen de volumen estimado

| Modulo | Lineas aproximadas |
|--------|-------------------|
| `config.py` | ~200 |
| `cli_reporting.py` | ~250 |
| `pipeline_runner.py` | ~50 |
| `dropbox_rr.py` | ~150 |
| `intervals_sync.py` | ~250 |
| `polar_client.py` | ~250 |
| `sleep_store.py` | ~350 |
| `oauth_utils.py` (ampliacion) | ~150 |
| Entrypoint residual | ~500–600 |

Total liberado del entrypoint actual: ~1650 lineas. Objetivo: entrypoint residual de ~500–600 lineas.

Nota: la suma de modulos extraidos (~1650) mas el entrypoint residual (~550) da ~2200, unas ~107 lineas menos que las 2307 actuales. El descuadre se explica por imports, bloques de comentarios, lineas en blanco y constantes de dominio que se redistribuyen sin contabilizar individualmente. Es una estimacion orientativa, no un presupuesto exacto.

#### Bugs detectados durante el inventario

**Bug 1 — `NameError` en bloque de credenciales (lineas 236–255)**

El bloque llama a `_print_header` durante el import del modulo, antes de que esa funcion este definida (linea 588). Si las credenciales estan ausentes, Python lanza `NameError: name '_print_header' is not defined`, no un `sys.exit(1)` limpio. Es un bug activo, no una fragilidad teorica. Resolver en AYO-02 antes de cualquier otra extraccion: inlinar el mensaje de error directamente sin llamar a `_print_header`.

**Duplicado — `_iso_duration_to_minutes` vs `parse_duration_to_minutes`**

`_iso_duration_to_minutes` (linea 803) es funcionalmente equivalente a `parse_duration_to_minutes` en `polar_utils.py`. No es un bug de ejecucion pero si un riesgo de mantenimiento: si se mueven ambas a modulos distintos sin consolidar, el duplicado queda distribuido. Ver Riesgo 5 y la tabla de `polar_client.py`.

**Ambiguedad — `do_oauth_flow` y clases OAuth locales**

`CLAUDE.md` prohibe HTTPServer local y apertura de navegador en produccion. El codigo existe y `main()` lo guarda con `IS_PRODUCTION`, pero sin anotacion clara. Decidir en AYO-06:
- Opcion A (minima): dejar en entrypoint con bloque `# DEV-ONLY`.
- Opcion B (limpia): mover a `oauth_utils.py` con docstring explicito.

## Por que esto importa de verdad

### 1. El testing queda mal aislado

Hoy es dificil probar por separado:

- que el cliente Polar responde bien,
- que el upsert de sleep recalcula percentiles como toca,
- que Dropbox RR cubre fechas faltantes correctamente,
- o que el CLI solo muestra el resumen correcto.

La razon es simple:

- el modulo mezcla filesystem,
- red,
- subprocess,
- pandas,
- y reglas de orquestacion.

### 2. La superficie de regresion es demasiado grande

Un cambio en:

- OAuth,
- manejo de tokens,
- sleep,
- o Intervals,

obliga a tocar el mismo archivo que decide el flujo principal de RR y procesamiento.

Eso eleva el riesgo de romper rutas que conceptualmente no deberian estar conectadas.

### 3. Hay duplicacion conceptual con la Web UI

[web_ui.py](/C:/Pilbond/polar-hrv-automation/web_ui.py) ya contiene una capa web de ejecucion y OAuth web.

Mientras tanto, `polar_hrv_automation.py` mantiene:

- OAuth local con navegador,
- callback server local,
- y parte del manejo de tokens y registro de usuario.

No siempre es duplicacion literal, pero si hay dos fronteras de ejecucion con logica relacionada y poco desacoplada.

### 4. `main()` acumula demasiadas decisiones

`main()` hoy hace a la vez:

- parseo CLI,
- decision de autenticacion,
- registro de usuario,
- seleccion de rango de fechas,
- filtros de sesiones,
- cobertura Dropbox,
- descarga Polar,
- export RR,
- disparo de builds,
- refresh de sleep,
- sync a Intervals,
- reporting final.

Eso dificulta:

- leer el flujo real,
- reutilizar partes,
- y testear casos intermedios sin ejecutar todo.

## Lo que no conviene hacer

No conviene responder a esta tarea con:

- un rewrite completo,
- mover funciones sin redisenar fronteras,
- o introducir una arquitectura grande con clases y abstracciones innecesarias.

Este repo es N=1, operativo y pragmatico. La solucion debe bajar acoplamiento sin introducir ceremonial.

## Propuesta recomendada

La mejor salida es una refactorizacion incremental por modulos y casos de uso.

Antes del corte por modulos, hay dos decisiones de alcance que deben quedar fijadas:

### Decision de alcance 1. Estatus de `do_oauth_flow`

El repo ya documenta de forma explicita que en produccion:

- no se debe abrir navegador desde backend;
- no se debe usar `HTTPServer` local para callback;
- y el flujo oficial es el web OAuth servido por `web_ui.py`.

Por tanto, `do_oauth_flow` no puede seguir tratado como parte indistinta del flujo operativo principal.

La decision recomendada es esta:

- en produccion, `do_oauth_flow` queda fuera de alcance operativo y no debe usarse;
- en local/dev, puede sobrevivir solo como utilidad dev-only explicita;
- si no tiene uso real mantenido, debe retirarse.

Matiz importante:

- esto no obliga a borrar `do_oauth_flow` de inmediato;
- lo que si obliga es a sacarlo del flujo operativo normal y a dejar su estatus no ambiguo;
- mientras exista, debe quedar documentado y encapsulado como utilidad local/dev-only, no como parte del camino recomendado del sistema.

Eso debe resolverse antes o al principio de la extraccion del cliente Polar. No conviene posponerlo hasta el final.

### Decision de alcance 2. Reutilizar precedentes ya existentes

`AYO-01` no debe introducir `polar_client.py` como si el repo no tuviera ya un modelo parcial de esa frontera.

La referencia obligatoria es [polar_sessions.py](/C:/Pilbond/polar-hrv-automation/polar_sessions.py):

- ya encapsula parsing y matching ligados a Polar;
- ya separa logica de API/dataset del entrypoint principal;
- y es el precedente mas claro de extraccion util en este repo.

La nueva frontera `polar_client.py`, si se crea, debe revisarse contra `polar_sessions.py` para evitar duplicacion de parse helpers, nueva dispersion de clientes, o fronteras ambiguas entre ingest de sesiones y cliente Polar general.

**Decision recomendada: coexistencia (Opcion A).** `polar_client.py` expone las funciones del entrypoint actual (`api_request`, `list_exercises`, `get_exercise_with_samples`, sleep, nightly). `PolarSessionClient` permanece en `polar_sessions.py` para session matching con rate limiting. La duplicacion de `list_exercises` y `get_exercise_with_samples` es tolerable porque sirven contextos distintos. `api_request` puede convertirse en el helper HTTP compartido. No conviene introducir una dependencia nueva entre `polar_sessions.py` y `polar_client.py` en este refactor.

Precisar el end state:

- la coexistencia se acepta como estado final de AYO-01, no solo como apaño temporal;
- `polar_client.py` y `polar_sessions.py` pueden convivir si sus fronteras quedan claras;
- no se debe hacer que `polar_sessions.py` dependa de `polar_client.py` en esta refactorizacion;
- si se quiere compartir logica HTTP, la salida correcta no es acoplar ambos modulos directamente sino extraer un helper neutro posterior o aceptar duplicacion limitada donde el coste de unificar sea mayor que el beneficio.

Decision operativa para esta tarea:

- no convertir `api_request` en helper compartido dentro de AYO-01 salvo que aparezca una necesidad muy clara;
- tratar cualquier unificacion HTTP entre `polar_client.py` y `polar_sessions.py` como posible trabajo posterior.

### Corte minimo recomendado

#### `config.py` (AYO-02)

Responsable de:

- variables de entorno,
- paths,
- flags,
- constantes operativas,
- `_qprint` (helper de logging silenciable).

Objetivo:

- sacar del entrypoint la inicializacion global de runtime.

Decision de convivencia:

- `config.py` no debe duplicar helpers ya presentes en `polar_utils.py`;
- `env_flag` sigue en `polar_utils.py`; `config.py` lo importa desde ahi;
- `polar_utils.py` solo debe crecer con helpers puros y compartidos; no debe convertirse en un cajon de sastre operativo;
- `_qprint` vive en `config.py`, no en `cli_reporting.py`; es usado por modulos operativos (dropbox_rr, polar_client, main) que no deben depender del modulo de reporting solo para hacer prints silenciables; cualquier modulo que necesite logging silenciable importa `_qprint` desde `config`.

#### `polar_client.py` (AYO-06)

Responsable de:

- `api_request`
- `list_exercises`
- `get_exercise_with_samples`
- `fetch_polar_sleep`
- `fetch_polar_nightly_recharge`
- `register_user_if_needed`

Objetivo:

- separar la frontera de red hacia Polar.

#### `dropbox_rr.py` (AYO-05)

Responsable de:

- deteccion de RR existentes,
- calculo de fechas faltantes,
- llamada a `egc_to_rr.py`,
- y cobertura por fecha.

Objetivo:

- aislar la estrategia Dropbox primero.

#### `sleep_store.py` (AYO-07)

Responsable de:

- normalizacion de sleep/nightly,
- schema de `ENDURANCE_HRV_sleep.csv`,
- recalculo derivado,
- upsert por fecha,
- batch update de fechas.

Objetivo:

- aislar la persistencia local de sueno.

#### `intervals_sync.py` (AYO-08)

Responsable de:

- lectura de ultima fila util del master,
- construccion del payload,
- push wellness a Intervals,
- y helpers asociados.

Objetivo:

- separar una integracion opcional que hoy esta acoplada al flujo principal.

#### `cli_reporting.py` (AYO-03)

Responsable de:

- `_print_*`
- summaries diarios y de 7 dias,
- rendering textual para CLI.

Objetivo:

- sacar la presentacion del core operativo.

#### `pipeline_runner.py` (AYO-04)

Responsable de:

- construir comandos de `build_hrv_core.py`,
- lanzar `build_hrv_final_dashboard.py`,
- encapsular subprocess y errores asociados.

Objetivo:

- aislar la frontera con scripts externos.

Nota de ownership:

- `_refresh_sleep_and_outputs` no pertenece a `sleep_store.py` ni a `pipeline_runner.py` como helper de bajo nivel;
- es mejor tratarla como funcion de caso de uso/orquestacion;
- por tanto, debe quedarse temporalmente en el entrypoint o pasar mas adelante a una capa de casos de uso durante la reduccion de `main()`.

#### `polar_hrv_automation.py` (AYO-09)

Deberia quedarse como:

- entrypoint CLI,
- parseo de argumentos,
- y orquestador fino de casos de uso.

Objetivo razonable:

- dejarlo claramente por debajo del orden actual,
- idealmente en un rango de `500–600` lineas (ver tabla de volumen estimado en la seccion de inventario).

## Casos de uso que conviene explicitar

No basta con mover funciones. Conviene introducir funciones de caso de uso legibles, por ejemplo:

- `sync_hrv_range(...)`
- `sync_sleep_only(...)`
- `process_rr_files(...)`
- `sync_intervals_wellness(...)`
- `resolve_date_range_from_args(...)`
- `refresh_sleep_and_outputs(...)`

Eso permite que el entrypoint coordine sin absorber toda la logica.

## Propuesta de subtareas

`AYO-01` deberia mantenerse como tarea paraguas de arquitectura.

La ejecucion real conviene descomponerla en subtareas pequenas y verificables. No porque el trabajo sea enorme, sino porque aqui hay varias fronteras tecnicas distintas y no todas tienen el mismo riesgo.

La propuesta mas razonable es esta.

### AYO-02 Extraer config y constantes operativas

Alcance:

- partir del inventario de extraccion de esta misma nota (seccion "Inventario de extraccion actual");
- mover variables de entorno,
- `Path` canonicos,
- flags,
- constantes de runtime,
- `_qprint`,
- `get_production_url` (linea 703),
- y ampliar `polar_utils.py` con `_parse_yyyy_mm_dd` (linea 276) e `_iso_to_dt` (linea 258);
- corregir Bug 1: inlinar mensaje de error en el bloque de credenciales sin llamar a `_print_header`.

Resultado esperado:

- `polar_hrv_automation.py` deja de inicializar en linea la mayor parte del runtime global;
- la configuracion queda centralizada y reusable;
- no se duplica `env_flag`;
- el bloque de credenciales produce un mensaje de error limpio en lugar de `NameError`;
- el comportamiento actual no cambia.

Test minimo esperado:

- verificar que el modulo importa correctamente con credenciales presentes;
- verificar que el bloque de credenciales produce salida legible (no `NameError`) cuando faltan;
- smoke test de que los paths canonicos apuntan a las rutas correctas segun las variables de entorno.

Riesgo:

- bajo.

### AYO-03 Extraer reporting CLI

Precondicion: AYO-02 completado (`_qprint` ya vive en `config.py`; bug de credenciales ya resuelto).

Alcance:

- mover `_print_header`,
- `_print_divider`,
- `_print_sync_completed`,
- `_print_no_rr_files`,
- `_print_master_already_updated`,
- `_get_color_emoji`,
- `_get_gate_emoji`,
- `_format_metric`,
- `show_last_daily_summary`,
- `show_last_7_days_summary`,
- y `show_latest_hrv_summaries`;
- incluir las constantes `COLOR_EMOJI` y `GATE_EMOJI` que acompanan a las funciones de rendering.

Resultado esperado:

- separar presentacion de operacion;
- hacer mas legible el flujo principal;
- facilitar testing del rendering textual.

Test minimo esperado:

- test de `show_last_daily_summary` con CSV temporal de una fila;
- test de `_get_gate_emoji` con los valores canonicos (VERDE, AMBAR, ROJO, NO);
- smoke test de que importar `cli_reporting` no requiere credenciales Polar.

Riesgo:

- bajo.

### AYO-04 Extraer runner de subprocess

Alcance:

- encapsular `build_hrv_core_cmd`,
- `run_build_hrv_final_dashboard_only`,
- y la ejecucion de subprocess hacia `build_hrv_core.py` y `build_hrv_final_dashboard.py`.

Nota: el subprocess hacia `egc_to_rr.py` pertenece a `dropbox_rr.py` (AYO-05), no a este modulo; `_run_dropbox_rr_import_for_dates` es quien lo lanza.

Resultado esperado:

- concentrar en un solo modulo la frontera con scripts externos;
- unificar manejo de `env`, `encoding`, `stdout/stderr` y errores.

Test minimo esperado:

- smoke test de construccion de comandos;
- y smoke test de manejo de error de subprocess sin tocar red real.

Riesgo:

- bajo a medio.

### AYO-05 Extraer integracion Dropbox RR

Alcance:

- mover `_extract_date_from_rr_filename`,
- `_scan_rr_files_by_date`,
- `_iter_dates`,
- `_compute_target_missing_dates`,
- `_run_dropbox_rr_import_for_dates`.

Resultado esperado:

- aislar la estrategia Dropbox primero;
- dejar trazable la cobertura por fecha;
- evitar que `main()` mezcle estrategia de cobertura con descarga Polar.

Test minimo esperado:

- test de seleccion de RR por fecha;
- test de fechas faltantes;
- y smoke test del wrapper de importacion con subprocess mockeado.

Riesgo:

- medio.

### AYO-06 Extraer cliente Polar

Alcance:

- revisar el solapamiento real con `PolarSessionClient` en `polar_sessions.py` antes de disenar la frontera (ver inventario);
- la decision recomendada es coexistencia: `polar_client.py` expone las funciones del entrypoint actual, `PolarSessionClient` permanece en `polar_sessions.py` para session matching;
- mover `api_request`,
- `register_user_if_needed`,
- `list_exercises`,
- `get_exercise_with_samples`,
- `fetch_polar_sleep`,
- `fetch_polar_nightly_recharge`,
- y helpers de parseo estrechamente ligados a respuestas de Polar;
- consolidar `_iso_duration_to_minutes` con `polar_utils.parse_duration_to_minutes` y eliminar el duplicado.

Decision obligatoria dentro de esta subtarea:

- fijar si `do_oauth_flow` se mueve a una utilidad dev-only separada o se elimina;
- no dejarlo ambiguo dentro del cliente Polar general.

Checkpoints internos recomendados:

1. **AYO-06A — frontera Polar**
   - extraer `api_request`, `list_exercises`, `get_exercise_with_samples`, sleep y nightly;
   - consolidar `_iso_duration_to_minutes`;
   - mantener estable el contrato con el entrypoint.

2. **AYO-06B — ciclo de vida OAuth/token**
   - mover `load_tokens` y `build_auth_url` a `oauth_utils.py`;
   - decidir el destino final de `do_oauth_flow` y de las utilidades OAuth dev-only;
   - dejar no ambiguo que el flujo oficial de produccion sigue siendo el web OAuth.

Resultado esperado:

- una frontera de red clara hacia Polar;
- menos acoplamiento entre parsing de API y orquestacion.

Test minimo esperado:

- tests unitarios del cliente con `requests` mockeado;
- y smoke test del wrapper de registro de usuario.

Riesgo:

- medio.

### AYO-07 Extraer sleep store

Alcance:

- mover normalizacion de campos de sleep y nightly,
- `_ensure_sleep_schema`,
- `_recalculate_sleep_derived`,
- `upsert_sleep_row`,
- `fetch_and_upsert_sleep`,
- `_update_sleep_for_dates`;
- incluir la constante `SLEEP_COLUMNS` que define el schema del CSV de sueno.

Resultado esperado:

- aislar la persistencia de `ENDURANCE_HRV_sleep.csv`;
- facilitar pruebas del upsert y de los percentiles derivados;
- reducir el ruido operativo del entrypoint.

Test minimo esperado:

- test de upsert sobre CSV temporal;
- test de schema minimo;
- y test de recalculo derivado.

Riesgo:

- medio.

### AYO-08 Extraer sync con Intervals

Alcance:

- mover `_read_latest_master_row`,
- `_build_intervals_payload`,
- `_send_intervals_wellness_from_master`,
- `fetch_intervals_activities`,
- y agregados auxiliares ligados a Intervals;
- incluir las constantes `MASTER_CSV_COLS` e `INTERVALS_FIELD_MAP` que definen el mapping de columnas hacia la API de Intervals.

Resultado esperado:

- dejar separada una integracion opcional;
- hacer visible su contrato propio;
- evitar que cada cambio en Intervals toque el flujo central.

Test minimo esperado:

- test de construccion de payload;
- test de lectura de ultima fila util;
- y smoke test de push con `requests` mockeado.

Riesgo:

- medio.

### AYO-09 Reducir `main()` a casos de uso

Alcance:

- introducir funciones de coordinacion tipo:
  - `resolve_date_range_from_args(...)`
  - `sync_hrv_range(...)`
  - `sync_sleep_only(...)`
  - `process_rr_files(...)`
  - `sync_intervals_wellness(...)`
  - `refresh_sleep_and_outputs(...)`
- eliminar ramas repetidas de salida temprana;
- dejar el entrypoint como coordinador fino.

Resultado esperado:

- lectura del flujo principal mucho mas clara;
- menor densidad de decisiones por bloque;
- mejor testabilidad de rutas parciales.

Ownership explicito:

- `refresh_sleep_and_outputs(...)` debe quedar aqui, como helper de caso de uso;
- no debe hundirse dentro de un modulo de persistencia ni dentro del runner de subprocess.

Test minimo esperado:

- smoke tests de las ramas principales con mocks de red, filesystem y subprocess;
- al menos un caso de "sin RR nuevos" y un caso de "RR nuevos + process".

Riesgo:

- medio a alto.

### AYO-10 Anadir tests minimos de regresion operativa

Alcance:

- cerrar con tests de integracion de regresion;
- no sustituir los tests minimos que cada subtarea de riesgo medio o alto debe aportar por separado;
- comprobar que el contrato operativo basico no cambia tras la refactorizacion completa.

Minimo recomendable:

- test de integracion del flujo principal refactorizado;
- test de compatibilidad del entrypoint CLI;
- y comprobaciones basicas de no regresion sobre outputs/paths esperados.

Resultado esperado:

- reducir riesgo de regresion durante la refactorizacion;
- permitir cambios posteriores con mas confianza.

Riesgo:

- medio.

## Orden recomendado de activacion de subtareas

Si esta tarea se convierte en trabajo real, el orden mas sensato es:

1. `AYO-02` — config.py. Resolver el bug de credenciales: `_print_header` se llama antes de estar definida; inlinar el mensaje sin llamar a `_print_header`. `_qprint` vive aqui, no en `cli_reporting.py`.
2. `AYO-03` — cli_reporting.py. Solo despues de AYO-02. `_qprint` ya importado desde `config.py`.
3. `AYO-04` — pipeline_runner.py. Sin dependencias criticas; bajo riesgo.
4. `AYO-05` — dropbox_rr.py. Smoke test minimo requerido como parte de la definicion de hecho.
5. `AYO-08` — intervals_sync.py. Smoke test minimo requerido.
6. `AYO-06` — polar_client.py. Decidir coexistencia vs base compartida con `PolarSessionClient` (recomendado: coexistencia). Consolidar `_iso_duration_to_minutes`. Ampliar `oauth_utils.py`. Smoke test minimo requerido.
7. `AYO-07` — sleep_store.py. Despues de AYO-06. Smoke test minimo requerido.
8. `AYO-09` — Reducir `main()`. Smoke test minimo requerido.
9. `AYO-10` — Tests de integracion de cierre. Complementa los smoke tests intermedios; no los sustituye.

Razon:

- primero sacar ruido y fronteras de bajo riesgo;
- resolver la forward reference (credenciales llama a `_print_header` antes de que exista) antes de mover reporting;
- aislar integraciones de red antes de tocar la orquestacion;
- respetar la dependencia sleep_store → polar_client;
- y cerrar con tests de integracion de todo el ciclo.

Matiz importante:

- `AYO-10` es cierre de integracion, no sustituto de tests intermedios;
- las subtareas `AYO-05` a `AYO-09` deben traer su propio smoke test minimo como parte de su definicion de hecho.

## Regression Gate por subtarea

Cada subtarea que toque codigo debe cerrar con una puerta minima de regresion. No hace falta esperar a `AYO-10` para descubrir roturas basicas.

Minimo transversal recomendado:

- `python -m py_compile` sobre los modulos tocados;
- smoke test de import de:
  - `polar_hrv_automation.py`
  - `web_ui.py`
  - `build_sessions.py`
- ejecucion de los tests minimos definidos para esa subtarea;
- confirmacion de que no cambia el contrato CLI del entrypoint si la subtarea toca su interfaz.

Minimo adicional cuando se toquen modulos compartidos con la UI:

- smoke test de arranque de `web_ui.py`;
- y, cuando aplique, comprobacion basica del flujo OAuth web o del diagnostico de credenciales.

## Riesgos de esta tarea

### 1. Refactor cosmetico

Mover funciones sin aclarar ownership entre modulos no arregla nada.

### 2. Deriva arquitectonica

No hace falta meter:

- contenedores de dependencias,
- jerarquias de clases,
- ni capas enterprise.

El repo necesita modularidad, no framework interno.

### 3. Mezclar esta tarea con logica HRV

Esta tarea es operativa y arquitectonica.

No debe aprovecharse para:

- cambiar gating,
- tocar columnas canonicas,
- redefinir metrica fisiologica,
- ni alterar contratos de `docs/contracts/` salvo que algun cambio de interfaz lo exija de verdad.

### 4. Romper el orden de extraccion

`sleep_store.py` llama a `polar_client.py`. Si se extrae sleep_store antes que polar_client, el modulo importara funciones que todavia no existen en su nuevo destino. Respetar el orden definido en la seccion anterior.

### 5. Dejar duplicados tras la extraccion

`_iso_duration_to_minutes` (linea 803) y `parse_duration_to_minutes` en `polar_utils.py` son funcionalmente equivalentes. Si se mueve `polar_client.py` sin consolidar, el duplicado queda distribuido entre dos modulos. AYO-06 debe incluir explicitamente el reemplazo de `_iso_duration_to_minutes` por `polar_utils.parse_duration_to_minutes` y la eliminacion del duplicado. Ver tambien "Bugs detectados" en la seccion de inventario.

## Criterio de aceptacion propuesto

1. `polar_hrv_automation.py` deja de concentrar OAuth, cliente Polar, Dropbox RR, sleep store, Intervals y reporting CLI en el mismo fichero.
2. El entrypoint mantiene el contrato actual de CLI y no rompe los outputs operativos del repo.
3. Los modulos extraidos tienen fronteras claras y testeables.
4. `main()` pasa a coordinar casos de uso pequenos en vez de absorber detalles de implementacion.
5. La Web UI sigue pudiendo invocar el flujo principal sin cambiar endpoints ni contrato operativo.
6. Si algun cambio toca contrato operativo documentado, se actualiza la documentacion correspondiente.

## Estado actual

La tarea esta abierta en el canvas como AYO-01 (estado: purple/propuesta).

Las subtareas AYO-02 a AYO-10 estan pendientes de activacion. El orden de activacion recomendado y los criterios de aceptacion por subtarea estan en las secciones anteriores.

La refactorizacion no es una urgencia operativa pero si una mejora de mantenibilidad justificada. Cada cambio futuro en OAuth, sleep, Intervals o despliegue Railway tiene coste proporcional al tamano y acoplamiento actual del entrypoint. El inventario documenta exactamente donde esta ese coste.
