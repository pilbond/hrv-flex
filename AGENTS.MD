# AGENTS.md - Polar HRV Automation (Railway) V4

## 1. Alcance de este archivo
Este `AGENTS.MD` gobierna la capa operativa global del repositorio:

- estructura del proyecto,
- componentes principales,
- rutas y outputs canonicos,
- runtime y variables de entorno,
- OAuth, endpoints y despliegue,
- seguridad y politica de cambios operativos.

No gobierna:

- el analisis deportivo detallado,
- el tono del agente de analisis,
- el perfil fisiologico del atleta,
- el metodo paso a paso del analisis de sesiones.

Esos aspectos viven en el modulo local `analysis/`.

## 2. Regla de precedencia
La precedencia documental del repositorio es:

1. este `AGENTS.MD` para operacion, runtime, ficheros, endpoints y despliegue
2. `docs/contracts/` para logica HRV normativa, columnas, QA y gating
3. `analysis/AGENTS.md` para reglas locales del modulo analitico
4. `analysis/ENDURANCE_AGENT_DOMAIN.md` para rol, tono y baseline fisiologico
5. `analysis/SESSION_ANALYSIS_METHOD.md` para el metodo operativo del analisis

Regla:

- no mezclar capas,
- si hay conflicto, clasificar primero si es operativo, normativo HRV o analitico.

## 3. Objetivo del proyecto
Sistema automatizado HRV para un unico atleta que:

- autentica con Polar AccessLink mediante OAuth2 Authorization Code,
- intenta cubrir primero RR faltantes desde `ECG.jsonl + ACC.jsonl` en Dropbox,
- usa Polar como fallback cuando Dropbox no cubre las fechas necesarias o no esta disponible,
- procesa RR con `build_hrv_core.py` para generar `CORE` y `BETA_AUDIT`,
- genera `FINAL` y `DASHBOARD` con `build_hrv_final_dashboard.py`,
- expone una UI web Flask y endpoints de sincronizacion,
- puede sincronizar wellness a Intervals.icu de forma opcional,
- se despliega en Railway.

## 4. Alcance funcional del proyecto
Este proyecto es para uso personal de un unico atleta.

Reglas:

- no tratarlo como producto multiusuario,
- no introducir abstracciones multi-athlete o multi-tenant sin cambio de alcance explicito,
- no introducir soporte multi-cuenta o seleccion de atleta salvo cambio de alcance explicito,
- priorizar simplicidad operativa, trazabilidad y robustez para el caso N=1.

## 5. Estado estructural
Elementos estructurales estables del repo:

- datos operativos en `data/`,
- RR crudos y reprocesables en `data/rr_downloads/`,
- archivo canonico de sueno en `ENDURANCE_HRV_sleep.csv`,
- scripts operativos locales en `scripts/`,
- norma HRV activa en `docs/contracts/`,
- documentacion historica y material archivado en `research/archive/`,
- modulo analitico local en `analysis/`,
- investigacion exploratoria, auditorias e informes no operativos en `research/`,
- implementacion interna del pipeline en `hrv_app/` (paquete Python interno; ARQ-02).

## 6. Snapshot actual (2026-06-12)
Estado actual de implementacion observado:

- la UI expone `/api/sync`, `/api/sync-sessions`, `/api/status`, `/api/import-seed`, `/api/restore-backup`, `/api/delete-latest-rr` y endpoints OAuth,
- `build_sessions.py` genera `ENDURANCE_HRV_sessions.csv`, `ENDURANCE_HRV_sessions_day.csv`, `ENDURANCE_HRV_intensity_distribution_weekly.csv`, `ENDURANCE_HRV_weekly_coach.json`, `ENDURANCE_HRV_sessions_metadata.json` y `ENDURANCE_HRV_wellness_subjective.csv`,
- `ENDURANCE_HRV_sessions_day.csv` ya incluye contexto canonico de carga (`acwr_simple_prev`, `monotony_7d_prev`, `strain_7d_prev`, `load_ctx_ready`), clustering reciente de intensidad (`intense_day`, `intense_days_prev_3d`, `intense_days_prev_5d`, `intensity_clustering_flag`, `intensity_clustering_level`) y la señal rolling `DO-02` de polarizacion por familia (`dominant_family_prev_7d`, `dominant_family_share_prev_7d`, `n_sessions_usable_prev_7d`, `z1/z2/z3_pct_weighted_prev_7d`, `distribution_signal_confidence_prev_7d`, `polarisation_index_prev_7d`, `intensity_blackhole_flag`, `intensity_blackhole_episode_id`, `intensity_blackhole_episode_len`),
- `ENDURANCE_HRV_intensity_distribution_weekly.csv` ya resume la distribucion observada por `sport x week` con ponderacion por minutos, patron (`polarized`, `pyramidal`, `threshold`, `mixed`) y confianza explicita,
- `ENDURANCE_HRV_sessions_metadata.json` ya incluye `training_audit` por capas (`dataset_level`, `signal_level`, `metric_level`) para gobernar confianza de coaching/carga sin tocar el gate HRV,
- `sessions.csv` ya incluye una capa mecanica minima opcional para deportes de pie con `run_power_*`, `speed_first_half`, `speed_second_half`, `cadence_first_half` y `cadence_second_half`,
- `sessions.csv` ya persiste `z1_total_min` junto a `z2_total_min` y `z3_total_min` para soportar agregacion canonica por deporte sin medias simples de porcentajes,
- `sessions.csv` ya persiste la extraccion minima canonica de `SYA-04` desde Intervals activity payload:
  - fijos: `calories`, `average_cadence`, `average_weather_temp`, `hrr_drop_bpm`, `trimp`
  - condicionales si `device_watts=true`: `icu_weighted_avg_watts`, `icu_joules_above_ftp`, `icu_max_wbal_depletion`, `decoupling`
- el flujo recomendado de cobertura RR es Dropbox primero y Polar como fallback,
- `ENDURANCE_HRV_sleep.csv` es el unico archivo canonico de sueno,
- `build_hrv_ssm.py` ya se ejecuta en el sync diario para regenerar `ENDURANCE_HRV_ssm_shadow.csv`, mientras que `build_hrv_ssm_validation.py` y `build_hrv_ssm_outcome_battery.py` quedan como auditorias manuales bajo demanda,
- `build_hrv_core.py` y `build_hrv_final_dashboard.py` ya dejan sidecars atomicos de trazabilidad
  en `ENDURANCE_HRV_master_CORE_manifest.json` y
  `ENDURANCE_HRV_master_FINAL_manifest.json`,
- la UI no debe permitir ejecutar `sync` HRV y `sync-sessions` al mismo tiempo,
- `analysis/` ya consume `training_audit` y la capa mecanica minima como contexto reproducible del informe,
- `analysis/` ya expone una capa analitica de terreno para sesiones a pie:
  - `terrain_context` desde Intervals activity + intervals (`GAP`, `VAM`, potencia por split y `terrain_intervals.csv`)
  - `terrain_fit_context` desde `FIT` record-level (`terrain_climbs.csv`, HR/cadencia/potencia por climb)
  - estas salidas viven solo en `analysis` y no modifican `sessions.csv` ni el gate HRV.
- `analysis/` ya expone `composite_context` dentro de `session_payload.json` y `summary.json` para señales compuestas exploratorias (`subjective_coherence/load_mismatch`, `thermal_context`, `durability_context`) calculadas sobre `sessions.csv` y `session_stream.csv`; siguen siendo capa local de `analysis/` y no modifican `sessions.csv`.
- `analysis/` ya puede exponer una capa no canonica de coach/Intervals dentro de `analysis/reports/<slug>/artifacts/`:
  - `analysis_only_context` en `summary.json` y `session_payload.json`
  - `coach_metrics.json`, `coach_intervals.csv` y `coach_groups.csv` como sidecars locales reproducibles
  - esta capa no modifica `sessions.csv`, `sessions_day.csv`, `FINAL` ni `DASHBOARD`.
- `hrv_app/backup_dropbox.py`: backup opcional de `ENDURANCE_HRV_*` a Dropbox tras sync exitoso (`HRV_BACKUP_DROPBOX_ENABLED`); restauracion via `POST /api/restore-backup` con escritura atomica y backup previo de los archivos existentes en `data/backup/pre_restore_<fecha>/`,
- `/health?strict=1` devuelve 503 si el FINAL falta o su ultima fecha supera `HRV_STALE_MAX_DAYS` (default 3); sin `strict` sigue siendo 200 (liveness),
- si `HRV_UI_KEY` esta definida, todos los `/api/*` exigen la clave via header `X-HRV-KEY` o `?key=`; el `state` de OAuth se valida con TTL y uso unico,
- `build_hrv_core.py`, `build_hrv_final_dashboard.py` y `build_sessions.py` usan `hrv_app.io_utils` para escrituras atomicas (eliminadas las implementaciones locales duplicadas),
- CI en `.github/workflows/tests.yml`: pytest en push/PR sobre Python 3.11.

Si este bloque queda desactualizado, debe actualizarse o reducirse.

## 7. Arquitectura actual
- `web_ui.py`
  Flask + UI movil.
  Endpoints: `/`, `/auth`, `/auth/callback`, `/oauth/callback`, `/api/sync`, `/api/sync-sessions`, `/api/status`, `/api/import-seed`, `/api/restore-backup`, `/api/delete-latest-rr`, `/health`.
  `POST /api/sync` ejecuta `polar_hrv_automation.py --process` en thread.
  `POST /api/sync-sessions` ejecuta `build_sessions.py --update` en thread.
  `POST /api/restore-backup` descarga el último backup de Dropbox a `DATA_DIR` (requiere `HRV_BACKUP_DROPBOX_ENABLED`).
  Los jobs HRV, sesiones, import seed, restore backup y borrado del ultimo RR comparten estado operativo y no deben ejecutarse en paralelo.

- `polar_hrv_automation.py`
  Orquesta el flujo principal.
  Delega la logica operativa a `hrv_app.hrv_sync_flow` y modulos internos del paquete.
  Intenta cubrir RR faltantes desde Dropbox.
  Si no es posible, usa Polar como fallback.
  Actualiza `ENDURANCE_HRV_sleep.csv`.
  Ejecuta `build_hrv_core.py`, `build_hrv_final_dashboard.py` y `build_hrv_ssm.py` cuando corresponde.
  Al final del sync exitoso, ejecuta `hrv_app.backup_dropbox.run_backup()` (opt-in via `HRV_BACKUP_DROPBOX_ENABLED`; nunca rompe el sync).
  La validacion SSM y la battery de outcomes quedan fuera del sync diario y se lanzan solo bajo demanda.
  Puede sincronizar wellness a Intervals.icu.

- `egc_to_rr.py`
  Convierte pares `ECG.jsonl + ACC.jsonl` a RR compatibles con la app.
  El uso recomendado actual es local o Dropbox.

- `build_hrv_core.py`
  RR -> `ENDURANCE_HRV_master_CORE.csv` y `ENDURANCE_HRV_master_BETA_AUDIT.csv`.
  Tambien deja `ENDURANCE_HRV_master_CORE_manifest.json` como sidecar atomico de corrida.

- `build_hrv_final_dashboard.py`
  `CORE + sleep + sessions_day` -> `ENDURANCE_HRV_master_FINAL.csv` y `ENDURANCE_HRV_master_DASHBOARD.csv`.
  La carga de entrenamiento se lee desde `ENDURANCE_HRV_sessions_day.csv`.
  Consume `load_3d`, la capa canonica `ACWR/monotony/strain` y el clustering reciente de intensidad solo como contexto de `reason_text`.
  Tambien deja `ENDURANCE_HRV_master_FINAL_manifest.json` como sidecar atomico de corrida.

- `build_sessions.py`
  Pipeline de sesiones desde Intervals.icu.
  Genera `ENDURANCE_HRV_sessions.csv`, `ENDURANCE_HRV_sessions_day.csv`, `ENDURANCE_HRV_intensity_distribution_weekly.csv`, `ENDURANCE_HRV_weekly_coach.json`, `ENDURANCE_HRV_sessions_metadata.json` y `ENDURANCE_HRV_wellness_subjective.csv`.
  Canoniza la capa mecanica minima para deportes de pie, el contexto de carga `ACWR/monotony/strain`, `training_audit` y la distribucion observada semanal por deporte.
  Soporta `--backfill`, `--daily`, `--update` y `--date`.

- `Dockerfile`
  Imagen base Python 3.11-slim.

- `requirements_web.txt`
  Dependencias de la app web y del pipeline.
  Incluye `scipy`.

- `analysis/`
  Modulo local para analisis de sesiones.
  Su operativa interna esta gobernada por `analysis/AGENTS.md`.
  Puede generar artefactos locales de terreno (`terrain_intervals.csv`, `terrain_climbs.csv`) dentro de `analysis/reports/` sin convertirlos en outputs canonicos globales.

## 8. Outputs operativos canonicos
Canonicos:

- `ENDURANCE_HRV_master_CORE.csv` (18 columnas)
- `ENDURANCE_HRV_master_BETA_AUDIT.csv` (13 columnas)
- `ENDURANCE_HRV_master_FINAL.csv` (66 columnas)
- `ENDURANCE_HRV_master_DASHBOARD.csv` (10 columnas)
- `ENDURANCE_HRV_sleep.csv` (17 columnas)

Complementarios:

- `ENDURANCE_HRV_sessions.csv`
- `ENDURANCE_HRV_sessions_day.csv`
- `ENDURANCE_HRV_intensity_distribution_weekly.csv`
- `ENDURANCE_HRV_weekly_coach.json`
- `ENDURANCE_HRV_sessions_metadata.json`
- `ENDURANCE_HRV_wellness_subjective.csv`
- `ENDURANCE_HRV_master_CORE_manifest.json`
- `ENDURANCE_HRV_master_FINAL_manifest.json`

## 9. Defaults runtime
Defaults actuales si no hay variables:

- `HRV_DATA_DIR = data`
- `RR_DOWNLOAD_DIR = data/rr_downloads`
- `POLAR_TOKEN_PATH = .polar_tokens.json`

Por tanto, en local:

- RR nuevos y reprocesables van a `data/rr_downloads/`,
- CSV maestros, `sleep` y `sessions` se leen y escriben en `data/`.

## 10. Variables de entorno
Requeridas para OAuth:

- `POLAR_CLIENT_SECRET`

Requerida una de estas:

- `POLAR_CLIENT_ID`
- `POLAR_CLIENT_ID2`

Nota:

- el codigo actual da precedencia a `POLAR_CLIENT_ID2` si ambas existen.
- `PORT` lo proporciona Railway en produccion; en local es opcional y por defecto vale `8080`.

Muy recomendadas:

- `PUBLIC_URL` (ej. `https://tu-app.up.railway.app`)
- `POLAR_TOKEN_PATH` (ej. `/data/polar_tokens.json`)
- `HRV_DATA_DIR` (ej. `/data`)
- `RR_DOWNLOAD_DIR` (ej. `/data/rr_downloads`)
- `INTERVALS_API_KEY`
- `INTERVALS_ATHLETE_ID`

Operativas:

- `HRV_QUIET=1`
- `HRV_DISABLE_BACKUP=1`
- `HRV_SYNC_TIMEOUT_SEC`
- `HRV_DROPBOX_RR_TIMEOUT_SEC`
- `HRV_SEED_UPLOAD_DIR`
- `HRV_SHOW_SEED_IMPORT`
- `HRV_UI_KEY` (opcional: si está definida, todos los `/api/*` exigen la clave vía header `X-HRV-KEY` o query `?key=`; sin definir, comportamiento histórico sin autenticación)
- `HRV_STALE_MAX_DAYS` (umbral de `/health?strict=1`: devuelve 503 si el FINAL falta o su última fecha supera el umbral; default 3. `/health` sin `strict` sigue siendo 200 liveness)
- `HRV_BACKUP_DROPBOX_ENABLED` (opcional: tras cada sync exitoso sube los `ENDURANCE_HRV_*.csv/.json` de `DATA_DIR` a Dropbox en carpeta fechada; usa las credenciales Dropbox ya configuradas; nunca rompe el sync)
- `HRV_BACKUP_DROPBOX_PATH` (carpeta raíz del backup; default `/hrv_backups`)
- `HRV_BACKUP_KEEP` (copias diarias a conservar; default 14)

Especializadas:

- `POLAR_USER_NAME` (default `Polar_User`; prefijo de RR descargados)
- `POLAR_TZ_OFFSET_MIN` (default `0`; ajuste de matching de sesiones)
- `INTERVALS_BASE_URL` (default `https://intervals.icu`)
- `ATHLETE_WEIGHT_KG` (default `68.0`; denominador de W/kg)
- `SYSTEM_BIKE_WEIGHT_KG` (default `80.0`; masa total del modelo fisico)
- `HRV_WARNING_MODE` (`adaptive90` por defecto; tambien `healthy85` o `p20`)
- `HRV_HEALTHY_START` / `HRV_HEALTHY_END` (ancla historica y modo `healthy85`)
- `HRV_SSM_REASON_TEXT_ENABLED=0` (feature flag experimental; no activar sin validacion por deporte)

Dropbox RR:

- `HRV_DROPBOX_RR_ENABLED=1`
- `HRV_DROPBOX_RR_SCRIPT=egc_to_rr.py`
- `HRV_DROPBOX_NO_AUX=1`
- `HRV_DROPBOX_PAIR_LIMIT=<N>`
- `HRV_DROPBOX_FOLDER_PATH=<dropbox_path>`
- aliases legacy de carpeta: `DROPBOX_FOLDER_PATH` y `ECG_RR_DROPBOX_FOLDER`
- `HRV_DROPBOX_RECURSIVE=1`
- `DROPBOX_ACCESS_TOKEN`
- o `DROPBOX_REFRESH_TOKEN + DROPBOX_APP_KEY + DROPBOX_APP_SECRET`

## 11. Persistencia, OAuth y despliegue
Principio no negociable de produccion:

- en Railway debe existir un unico flujo OAuth web,
- esta prohibido abrir navegador desde backend,
- esta prohibido usar HTTPServer local para callback en produccion.

Persistencia Railway recomendada:

- volumen montado en `/data`
- `POLAR_TOKEN_PATH=/data/polar_tokens.json`
- `HRV_DATA_DIR=/data`
- `RR_DOWNLOAD_DIR=/data/rr_downloads`

Reglas:

- escribir tokens de forma atomica,
- no exponer tokens por HTTP.

Flujo esperado:

1. usuario abre `GET /auth`
2. backend redirige a Polar
3. callback en `/auth/callback` o `/oauth/callback`
4. intercambio de `code` por tokens
5. persistencia en `POLAR_TOKEN_PATH`

## 12. Endpoints y jobs
Contrato:

- `GET /`
- `GET /auth`
- `GET /auth/callback`
- `GET /oauth/callback`
- `POST /api/sync`
- `POST /api/sync-sessions`
- `GET /api/status`
- `POST /api/import-seed`
- `POST /api/restore-backup`
- `POST /api/delete-latest-rr`
- `GET /health`

Regla operativa:

- los cinco endpoints POST operativos comparten estado de ejecucion en memoria,
- no deben ejecutarse en paralelo,
- si un job esta corriendo, cualquier otro debe rechazarse.

## 13. Seguridad
- no commitear `.env`, `.polar_tokens.json`, RR ni CSV personales,
- no loguear tokens ni `client_secret`,
- rotar secretos si se exponen,
- no exponer tokens ni artefactos sensibles por HTTP,
- tratar `research/archive/` como material historico sensible.

## 14. Criterios de aceptacion
1. `/auth` devuelve 302 a Polar con `redirect_uri` correcto.
2. `/auth/callback` guarda tokens en `POLAR_TOKEN_PATH`.
3. `POST /api/sync` genera o actualiza `CORE`, `BETA_AUDIT`, `sleep`, `FINAL` y `DASHBOARD`.
4. Tras redeploy, `/api/sync` sigue funcionando si hay Volume.
5. Logs utiles sin secretos.
6. RR se almacenan y leen desde `data/rr_downloads/`.
7. Si faltan fechas en `CORE`, se intenta primero cubrirlas desde Dropbox antes del fallback Polar.
8. `POST /api/sync-sessions` ejecuta `build_sessions.py --update`.
9. La UI web no permite ejecutar `sync` HRV y `sync-sessions` al mismo tiempo.
10. `POST /api/restore-backup` descarga el ultimo backup de Dropbox a `DATA_DIR` con escritura atomica.

## 15. Comandos operativos
Windows:

- `scripts\\run-web-ui.bat`
- `scripts\\run-hrv.bat`
- `scripts\\run-build-sessions.bat`
- `scripts\\run-ssm-audit.bat`

Pipeline de sesiones:

- `python build_sessions.py --update`

Auditoria SSM manual:

- `python polar_hrv_automation.py --ssm-audit`

Conversion manual cloud -> RR:

- `python egc_to_rr.py --dropbox-folder /ruta/carpeta --dropbox-recursive --outdir data/rr_downloads`

## 16. Politica de cambios
- cambios minimos,
- compatibilidad con Python 3.11,
- evitar dependencias nuevas salvo valor claro,
- preservar nombres, rutas y outputs operativos salvo instruccion explicita,
- no reintroducir rutas, outputs o flujos ya retirados sin cambio de alcance explicito.

Si un cambio afecta a:

- logica HRV,
- esquema de columnas,
- criterios QA,
- gating o semaforos,
- significado operativo de metricas,

entonces tambien hay que actualizar `docs/contracts/`.

## 17. Enrutado de analisis, auditorias y experimentos

Antes de crear archivos nuevos, clasificar el trabajo:

- informe funcional de una sesion o semana, sidecar reproducible adoptado por
  el modulo o artefacto necesario para redactar esos informes -> `analysis/`
  segun `analysis/AGENTS.md`,
- hipotesis puntual, benchmark, exploracion estadistica, auditoria tecnica,
  revision por IA o experimento no adoptado -> `research/`,
- prueba automatizada de comportamiento estable -> `tests/`,
- contrato normativo vigente -> `docs/contracts/`,
- documento consolidado de una tarea o decision adoptada -> `docs/HRV/`.

Reglas para `research/`:

- leer `research/AGENTS.md` antes de crear o modificar contenido,
- codigo reproducible en `research/**/scripts/`,
- resultados generados en `research/**/results/` o `research/reports/`,
- trabajo descartable en `research/.scratch/`,
- no escribir resultados junto a scripts,
- no colocar experimentos en la raiz, `analysis/`, `docs/contracts/`,
  `seed_upload/` ni `data/`,
- no importar codigo de `research/` desde la aplicacion,
- una investigacion solo pasa a la aplicacion mediante implementacion
  explicita, tests y actualizacion contractual cuando corresponda.

Regla de decision:

- si el archivo sirve para operar o generar el producto analitico habitual,
  pertenece a `analysis/`,
- si sirve para decidir si algo deberia adoptarse en el futuro, pertenece a
  `research/`.


## Workflow Kanvas

Si existe `Project.canvas` en la raiz del proyecto, usar Kanvas como tablero visual de tareas.

Reglas:
- Nunca editar `Project.canvas` directamente.
- Todas las modificaciones del canvas deben hacerse con el CLI de Kanvas.
- CLI canonico desde la raiz del repositorio:
  `python canvas-tool.py Project.canvas <command>`
- Al inicio de cada sesion:
  `python canvas-tool.py Project.canvas status`
- Si hay inconsistencias visuales o tareas sin ID:
  `python canvas-tool.py Project.canvas normalize`

Politica de estados:
- `purple`: propuesta del agente
- `red`: tarea aprobada y lista
- `orange`: en curso
- `cyan`: terminada por el agente, pendiente de revision humana
- `green`: solo el humano puede marcarla como completada
- `gray`: bloqueada por dependencias

Permisos del agente:
- Puede leer el tablero con `status`, `show`, `list`, `ready`, `blocked`, `blocking`, `dump`
- Puede proponer tareas con `propose`, `batch`, `propose-group`
- Puede empezar y cerrar trabajo con `start`, `finish`, `pause`
- Puede editar solo tareas en `orange` con `edit`
- Puede anadir dependencias con `add-dep`
- No puede marcar tareas en `green`
- No puede borrar tarjetas ni editar el JSON del canvas a mano

Integracion con este repositorio:
- Las reglas operativas de `polar-hrv-automation` siguen teniendo prioridad
- Kanvas solo organiza planificacion, dependencias y estado del trabajo
- Si hay conflicto entre Kanvas y las reglas del dominio HRV, manda `AGENTS.MD` del proyecto y la documentacion de `docs/contracts/`


<!-- code-review-graph MCP tools -->
## MCP Tools: code-review-graph

**IMPORTANT: This project has a knowledge graph. ALWAYS use the
code-review-graph MCP tools BEFORE using Grep/Glob/Read to explore
the codebase.** The graph is faster, cheaper (fewer tokens), and gives
you structural context (callers, dependents, test coverage) that file
scanning cannot.

### When to use graph tools FIRST

- **Exploring code**: `semantic_search_nodes` or `query_graph` instead of Grep
- **Understanding impact**: `get_impact_radius` instead of manually tracing imports
- **Code review**: `detect_changes` + `get_review_context` instead of reading entire files
- **Finding relationships**: `query_graph` with callers_of/callees_of/imports_of/tests_for
- **Architecture questions**: `get_architecture_overview` + `list_communities`

Fall back to Grep/Glob/Read **only** when the graph doesn't cover what you need.

### Policy: code-review-graph first

Para cualquier tarea de review, exploracion o analisis de impacto, la IA debe consultar `code-review-graph` antes de leer archivos, salvo que el cambio sea claramente local y ya este identificado con precision.

Nunca hacer lectura amplia del repo a ciegas si `detect_changes`, `get_review_context` o `get_impact_radius` pueden resolver la duda.

### Policy: graph queries should be narrow

Preferir consultas especificas antes que consultas amplias.

- Usar `detect_changes` cuando exista diff o cambios recientes.
- Usar `get_review_context` cuando ya se conozcan los archivos o el area afectada.
- Usar `get_impact_radius` cuando la pregunta sea de alcance o dependencias.
- Usar `get_minimal_context_tool` solo como orientacion inicial muy breve cuando la tarea aun no este bien acotada.
- Si una consulta del grafo timeoutea repetidamente para la misma tarea, dejar de ampliar el alcance y pasar a lectura manual de archivos relevantes.

### Key Tools

| Tool | Use when |
|------|----------|
| `detect_changes` | Reviewing code changes — gives risk-scored analysis |
| `get_review_context` | Need source snippets for review — token-efficient |
| `get_impact_radius` | Understanding blast radius of a change |
| `get_affected_flows` | Finding which execution paths are impacted |
| `query_graph` | Tracing callers, callees, imports, tests, dependencies |
| `semantic_search_nodes` | Finding functions/classes by name or keyword |
| `get_architecture_overview` | Understanding high-level codebase structure |
| `refactor_tool` | Planning renames, finding dead code |

### Workflow

1. The graph auto-updates on file changes (via hooks).
2. Use `detect_changes` for code review.
3. Use `get_affected_flows` to understand impact.
4. Use `query_graph` pattern="tests_for" to check coverage.
