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
- cubre nuevos RR matinales desde `ECG.jsonl + ACC.jsonl` en Dropbox, su unica fuente: si una fecha nueva no esta en Dropbox, esa fecha no entra al pipeline en ese ciclo; no hay fallback Polar para RR nuevos,
- el historico de `CORE` generado anteriormente con RR de Polar se conserva sin migracion retroactiva,
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
- implementacion interna del pipeline en `hrv_app/` (paquete Python interno).

## 6. Snapshot actual (2026-06-17)
Estado actual de implementacion observado:

- la UI expone `/api/sync`, `/api/sync-sessions`, `/api/status`, `/api/restore-backup`, `/api/delete-latest-rr` y endpoints OAuth,
- `build_sessions.py` genera `ENDURANCE_HRV_sessions.csv`, `ENDURANCE_HRV_sessions_day.csv`, `ENDURANCE_HRV_intensity_distribution_weekly.csv`, `ENDURANCE_HRV_weekly_coach.json`, `ENDURANCE_HRV_sessions_metadata.json` y `ENDURANCE_HRV_wellness_subjective.csv`,
- `ENDURANCE_HRV_sessions_day.csv` ya incluye contexto canonico de carga (`acwr_simple_prev`, `monotony_7d_prev`, `strain_7d_prev`, `load_ctx_ready`), clustering reciente de intensidad (`intense_day`, `intense_days_prev_3d`, `intense_days_prev_5d`, `intensity_clustering_flag`, `intensity_clustering_level`) y la señal rolling de polarizacion por familia (`dominant_family_prev_7d`, `dominant_family_share_prev_7d`, `n_sessions_usable_prev_7d`, `z1/z2/z3_pct_weighted_prev_7d`, `distribution_signal_confidence_prev_7d`, `polarisation_index_prev_7d`, `intensity_blackhole_flag`, `intensity_blackhole_episode_id`, `intensity_blackhole_episode_len`),
- `ENDURANCE_HRV_intensity_distribution_weekly.csv` ya resume la distribucion observada por `sport x week` con ponderacion por minutos, patron (`polarized`, `pyramidal`, `threshold`, `mixed`) y confianza explicita,
- `ENDURANCE_HRV_sessions_metadata.json` ya incluye `training_audit` por capas (`dataset_level`, `signal_level`, `metric_level`) para gobernar confianza de coaching/carga sin tocar el gate HRV,
- `sessions.csv` ya incluye una capa mecanica minima opcional para deportes de pie con `run_power_*`, `speed_first_half`, `speed_second_half`, `cadence_first_half` y `cadence_second_half`,
- `sessions.csv` ya persiste `z1_total_min` junto a `z2_total_min` y `z3_total_min` para soportar agregacion canonica por deporte sin medias simples de porcentajes,
- `sessions.csv` ya persiste la extraccion minima canonica desde Intervals activity payload:
  - fijos: `calories`, `average_cadence`, `average_weather_temp`, `hrr_drop_bpm`, `trimp`
  - condicionales si `device_watts=true`: `icu_weighted_avg_watts`, `icu_joules_above_ftp`, `icu_max_wbal_depletion`, `decoupling`
- Dropbox es la unica fuente de nuevos RR matinales; no hay fallback Polar para fechas nuevas no cubiertas por Dropbox,
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
- `hrv_app/backup_dropbox.py`: backup opcional de `ENDURANCE_HRV_*` de la raiz de `DATA_DIR` y del historial IA en `data/ai_briefs/` a Dropbox (`HRV_BACKUP_DROPBOX_ENABLED`, sobrescribe en cada sync); la restauracion descarga primero a staging dentro de `DATA_DIR`, valida CORE, BETA_AUDIT, FINAL, DASHBOARD, sleep y la coherencia de ambos manifests antes de publicar, y revierte los sustituidos si falla la publicacion, conservando su copia previa en `data/backup/pre_restore/`. Un backup sin manifests se rechaza antes de publicar. El auto-restore solo se dispara cuando el conjunto obligatorio no es utilizable: unos manifests incoherentes sobre un dataset completo se avisan por log (`generation_coherent=false`) y no provocan restauracion, para no sobrescribir un historico utilizable. El backup tampoco sube una generacion incoherente: devuelve `incoherent_generation`, deja el remoto intacto y degrada el sync,
- `/health?strict=1` devuelve 503 si el FINAL falta o su ultima fecha supera `HRV_STALE_MAX_DAYS` (default 3); sin `strict` sigue siendo 200 (liveness),
- si `HRV_UI_KEY` esta definida, todos los `/api/*` exigen la clave via header `X-HRV-KEY` o `?key=`; el `state` de OAuth se valida con TTL y uso unico,
- `build_hrv_core.py`, `build_hrv_final_dashboard.py` y `build_sessions.py` usan `hrv_app.io_utils` para escrituras atomicas (eliminadas las implementaciones locales duplicadas),
- CI en `.github/workflows/tests.yml`: pytest en push/PR sobre Python 3.11.
- v3 completamente retirado; v4 es el único runtime Polar; `polar_client.py`, `polar_oauth_local.py` y `polar_shadow.py` eliminados; `POLAR_API_VERSION` y `POLAR_V4_SESSIONS` suprimidos.

Si este bloque queda desactualizado, debe actualizarse o reducirse.

## 7. Arquitectura actual
- `web_ui.py`
  Flask + UI movil.
  Endpoints: `/`, `/auth`, `/auth/callback`, `/oauth/callback`, `/api/sync`, `/api/sync-sessions`, `/api/status`, `/api/restore-backup`, `/api/delete-latest-rr`, `/health`.
  `POST /api/sync` ejecuta `polar_hrv_automation.py --process` en thread.
  `POST /api/sync-sessions` ejecuta `build_sessions.py --update` en thread.
  `POST /api/restore-backup` descarga el último backup de Dropbox a `DATA_DIR` (requiere `HRV_BACKUP_DROPBOX_ENABLED`).
  Los jobs HRV, sesiones, restore backup y borrado del ultimo RR comparten estado operativo y no deben ejecutarse en paralelo.

- `polar_hrv_automation.py`
  Orquesta el flujo principal.
  Delega la logica operativa a `hrv_app.hrv_sync_flow` y modulos internos del paquete.
  Intenta cubrir RR nuevos faltantes desde Dropbox (unica fuente); si Dropbox no cubre una fecha nueva, esa fecha no entra al pipeline en este ciclo (sin fallback Polar).
  `--all` reprocesa solo RR ya presentes en disco, sin descargar nada nuevo.
  Runtime único: v4. No hay rollback flag ni modo v3.
  Actualiza `ENDURANCE_HRV_sleep.csv`.
  Ejecuta `build_hrv_core.py`, `build_hrv_final_dashboard.py` y `build_hrv_ssm.py` cuando corresponde.
  Al final del sync exitoso, ejecuta `hrv_app.backup_dropbox.run_backup()` (opt-in via `HRV_BACKUP_DROPBOX_ENABLED`; nunca rompe el sync).
  La validacion SSM y la battery de outcomes quedan fuera del sync diario y se lanzan solo bajo demanda.
  Puede sincronizar wellness a Intervals.icu.

- `egc_to_rr.py`
  Convierte pares `ECG.jsonl + ACC.jsonl` a RR compatibles con la app.
  El uso recomendado actual es local o Dropbox.
  Conserva prospectivamente el motivo por índice RR y un manifiesto de huellas/versiones en `RR_DOWNLOAD_DIR/_rr_diagnostics/`, también con `--no-aux`. Al incorporar el RR desde Dropbox, se verifican los nombres y las huellas SHA-256 del RR y de sus motivos de descarte contra el manifiesto. Si falta un diagnóstico o falla la verificación, la importación de ese ciclo falla (`diagnostic_error`) y no se promueve ningún RR nuevo. Estos sidecars no son canónicos ni cambian `duration,offline`.

- `build_hrv_core.py`
  RR -> `ENDURANCE_HRV_master_CORE.csv` y `ENDURANCE_HRV_master_BETA_AUDIT.csv`.
  Tambien deja `ENDURANCE_HRV_master_CORE_manifest.json` como sidecar atomico de corrida.
  En este checkout local, el pipeline falla cerrado si CORE, BETA_AUDIT y su manifiesto no corresponden a `GEOMETRY_VERSION=hg10_s90_t375_trim15` y `QUALITY_POLICY_VERSION=hg10_latnan_aviso_art_window_v2`. El histórico anterior de 18 columnas fue respaldado antes del corte local del 2026-11-05. `--allow-hg10-migration` solo se admite con un `--data-dir` aislado.

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
En este checkout local, la generación actual (pares consecutivos y política de Calidad vigente) se publicó el 2026-11-05: CORE tiene 19 columnas y FINAL 67, incluida `rejected_rr_pct_window`. Los manifiestos y las huellas corresponden a esta generación. El estado del volumen Railway se verifica por separado.

Canonicos:

- `ENDURANCE_HRV_master_CORE.csv` (19 columnas)
- `ENDURANCE_HRV_master_BETA_AUDIT.csv` (13 columnas)
- `ENDURANCE_HRV_master_FINAL.csv` (67 columnas)
- `ENDURANCE_HRV_master_DASHBOARD.csv` (10 columnas)
- `ENDURANCE_HRV_sleep.csv` (26 columnas: 17 históricas + 9 valoraciones de Polar Nightly Recharge)

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
- `POLAR_TOKEN_PATH_V4 = .polar_tokens_v4.json` (relativo al directorio de trabajo)

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
- `POLAR_TOKEN_PATH_V4` (ej. `/data/polar_tokens_v4.json`; `POLAR_TOKEN_PATH` es la variable v3 y el runtime no la usa)
- `HRV_DATA_DIR` (ej. `/data`)
- `RR_DOWNLOAD_DIR` (ej. `/data/rr_downloads`)
- `INTERVALS_API_KEY`
- `INTERVALS_ATHLETE_ID`

Operativas:

- `HRV_QUIET=1`
- `HRV_DISABLE_BACKUP=1`
- `HRV_CORE_BACKUP_RETENTION=30` (copias locales fechadas de CORE y BETA_AUDIT a conservar por tipo; `0` las desactiva. `HRV_DISABLE_BACKUP=1` sigue siendo el interruptor global)
- `HRV_SYNC_TIMEOUT_SEC`
- `HRV_DROPBOX_RR_TIMEOUT_SEC`
- `HRV_UI_KEY` (si está definida, todos los `/api/*` exigen la clave vía header `X-HRV-KEY` o query `?key=`; sin definir, `/api/*` queda sin autenticación. Recomendada en Railway y **pendiente de configurar** en el despliegue actual: ver sección 13)
- `HRV_STALE_MAX_DAYS` (umbral de `/health?strict=1`: devuelve 503 si el FINAL falta o su última fecha supera el umbral; default 3. `/health` sin `strict` sigue siendo 200 liveness)
- `HRV_BACKUP_DROPBOX_ENABLED` (opcional: tras cada sync exitoso sube los `ENDURANCE_HRV_*.csv/.json` de la raiz de `DATA_DIR` y el historial `DATA_DIR/ai_briefs/**/ENDURANCE_HRV_*.json` a Dropbox, sobrescribiendo; usa las credenciales Dropbox ya configuradas; nunca rompe el sync)
- `HRV_BACKUP_DROPBOX_PATH` (carpeta del backup; default `/hrv_backups`)

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

IA briefs (opt-in, con fallback determinista garantizado):

- `HRV_AI_ENABLED=0` (prerequisito comun)
- `HRV_AI_DAILY_ENABLED=0` (brief diario HRV, capa `reason_items`)
- `HRV_AI_SSM_ENABLED=0` (brief SSM shadow, payload validado v4 en `research/reports/iu16_ssm_brief_eval/`)
- `HRV_AI_PROVIDER`, `HRV_AI_MODEL`, `HRV_AI_API_KEY`, `HRV_AI_BASE_URL` (OpenAI-compatible)
- `HRV_AI_LANGUAGE=es`, `HRV_AI_PROMPT_VERSION=daily_brief_v1`, `HRV_AI_SSM_PROMPT_VERSION=ssm_brief_v5`
- `HRV_AI_TEMPERATURE`, `HRV_AI_TOP_P`, `HRV_AI_MAX_TOKENS`, `HRV_AI_TIMEOUT_SEC`, `HRV_AI_THINKING`
- Los sidecars `*_latest.json` viven en `DATA_DIR`; el historial fechado vive en `DATA_DIR/ai_briefs/{daily,ssm}/`. No son contratos canonicos.
- La UI (`hrv_app.ui_view.build_view`) solo muestra el texto IA si supera la validacion de contrato; el brief SSM ademas exige que `relation_to_gate` coincida con el calculado por Python. Cualquier discrepancia cae al texto determinista.

## 11. Persistencia, OAuth y despliegue
Principio no negociable de produccion:

- en Railway debe existir un unico flujo OAuth web,
- esta prohibido abrir navegador desde backend,
- esta prohibido usar HTTPServer local para callback en produccion.

Persistencia Railway requerida:

- volumen montado en `/data`
- `RAILWAY_RUN_UID=0`: la imagen del `Dockerfile` se ejecuta con un usuario sin privilegios y Railway monta el volumen como root. Sin esta variable la app no puede escribir en `/data` y pasa sin aviso a `./data` dentro del contenedor, que se pierde en cada redeploy. Se comprueba en `/api/status`: `core_path`, `final_path`, `token_path` y `rr_download_dir` deben empezar por `/data/`
- `POLAR_TOKEN_PATH_V4=/data/polar_tokens_v4.json` (sin ella el token se guarda en el directorio de trabajo del contenedor y hay que reautorizar Polar tras cada redeploy)
- `HRV_DATA_DIR=/data`
- `RR_DOWNLOAD_DIR=/data/rr_downloads`
- los valores de las rutas se escriben sin comillas literales: el codigo no las elimina y una ruta que empieza por `"` se interpreta como relativa al contenedor

Reglas:

- escribir tokens de forma atomica,
- no exponer tokens por HTTP.

Flujo esperado:

1. usuario abre `GET /auth`
2. backend redirige a Polar
3. callback en `/auth/callback` o `/oauth/callback`
4. intercambio de `code` por tokens
5. persistencia en `POLAR_TOKEN_PATH_V4`

## 12. Endpoints y jobs
Contrato:

- `GET /`
- `GET /auth`
- `GET /auth/callback`
- `GET /oauth/callback`
- `POST /api/sync`
- `POST /api/sync-sessions`
- `GET /api/status`
- `POST /api/restore-backup`
- `POST /api/delete-latest-rr`
- `GET /health`

Regla operativa:

- los cuatro endpoints POST operativos comparten estado de ejecucion en memoria,
- no deben ejecutarse en paralelo,
- si un job esta corriendo, cualquier otro debe rechazarse.

## 13. Seguridad
- no commitear `.env`, `.polar_tokens.json`, RR ni CSV personales,
- no loguear tokens ni `client_secret`,
- rotar secretos si se exponen,
- no exponer tokens ni artefactos sensibles por HTTP,
- tratar `research/archive/` como material historico sensible,
- **pendiente:** `HRV_UI_KEY` aun no esta definida en Railway. Se recomienda definirla con una cadena aleatoria larga (p. ej. `python -c "import secrets; print(secrets.token_urlsafe(32))"`): sin ella cualquiera que alcance la URL publica puede leer `/api/status` y lanzar sync, restore o borrado del ultimo RR. La UI lee la clave de `?key=` en la URL de la pagina; `/` y `/auth` no quedan cubiertos.

## 14. Criterios de aceptacion
1. `/auth` devuelve 302 a Polar con `redirect_uri` correcto.
2. `/auth/callback` guarda tokens en `POLAR_TOKEN_PATH_V4`.
3. `POST /api/sync` genera o actualiza `CORE`, `BETA_AUDIT`, `sleep`, `FINAL` y `DASHBOARD`.
4. Tras redeploy, `/api/sync` sigue funcionando sin restaurar ni reautorizar (volumen en `/data` con escritura y token en el volumen).
5. Logs utiles sin secretos.
6. RR se almacenan y leen desde `data/rr_downloads/`.
7. Si faltan fechas nuevas en `CORE`, se intentan cubrir desde Dropbox (unica fuente); si Dropbox no las cubre, esas fechas no entran al pipeline (sin fallback Polar).
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
- no colocar experimentos en la raiz, `analysis/`, `docs/contracts/` ni `data/`,
- no importar codigo de `research/` desde la aplicacion,
- una investigacion solo pasa a la aplicacion mediante implementacion
  explicita, tests y actualizacion contractual cuando corresponda.

Regla de decision:

- si el archivo sirve para operar o generar el producto analitico habitual,
  pertenece a `analysis/`,
- si sirve para decidir si algo deberia adoptarse en el futuro, pertenece a
  `research/`.


## Workflow Kanvas

Plan and track work on the Kanvas board; follow .agents/skills/kanvas/SKILL.md.

Tablero canonico: `kanvas.json` en la raiz (Kanvas 0.4, migrado desde `Project.canvas` el 2026-11-05).

Reglas:
- Nunca editar `kanvas.json` a mano; todo cambio pasa por el CLI:
  `python .agents/skills/kanvas/kanvas.py <command>`
- Al inicio de cada sesion: `python .agents/skills/kanvas/kanvas.py status`
- Validar el tablero: `python .agents/skills/kanvas/kanvas.py check`
- El humano lo ve en el navegador con `python .agents/skills/kanvas/kanvas.py serve`
- Parche local: los `[[...]]` de las tareas abren el `.md` de `docs/` en el navegador (`scripts/kanvas_docs_patch.py`; reaplicar tras `kanvas-board init` o una actualizacion; no funciona con `uvx kanvas-board serve`)
- Firmar notas y propuestas con `--as <herramienta>` (`claude-code`, `codex`, `gemini`, ...)

Estados: `proposed -> todo -> doing -> review -> done`. `blocked` ya no se marca a mano: se deriva de dependencias sin terminar.
- `proposed`: propuesta del agente (`propose`, `batch`)
- `todo`: aprobada por el humano
- `doing`: en curso (`start`)
- `review`: terminada por el agente, pendiente de revision humana (`finish`)
- `done`: solo el humano la marca

Permisos del agente:
- Leer: `status`, `ready`, `show`, `list`, `blocked`, `check`
- Proponer: `propose`, `add-group`, `batch`; revisar propuestas no aprobadas con `edit`, `withdraw`, `undepend`
- Trabajar: `start`, `note`, `ask`, `pause`, `finish`
- Anadir dependencias con `depend`
- No aprueba propuestas, no cambia tareas aprobadas, no marca `done`, no activa YOLO

Legacy (solo historico, no usar): `Project.canvas`, `canvas-tool.py` y `RULES.md` se conservan en `research/archive/kanvas_legacy/`; el plugin `.obsidian/plugins/canvas-watcher` tambien esta retirado. La lista de prioridades libre del canvas antiguo se conserva en `docs/HRV/KANVAS prioridades legacy.md`.

Integracion con este repositorio:
- Las reglas operativas de `polar-hrv-automation` siguen teniendo prioridad
- Kanvas solo organiza planificacion, dependencias y estado del trabajo
- Si hay conflicto entre Kanvas y las reglas del dominio HRV, manda `AGENTS.MD` del proyecto y la documentacion de `docs/contracts/`
