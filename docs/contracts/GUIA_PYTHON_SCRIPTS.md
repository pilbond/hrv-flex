# Guia didactica de scripts Python

Este documento explica, en lenguaje simple, que hace cada `.py` del proyecto, en que flujo participa y como encaja la conversion `ECG.jsonl + ACC.jsonl -> RR`.

## 1) Mapa rapido del flujo principal

Flujo operativo normal (Railway o UI local):

1. `web_ui.py` levanta la web.
2. Al llamar `POST /api/sync`, la web ejecuta `python polar_hrv_automation.py --process`.
3. `polar_hrv_automation.py` valida entorno, tokens y argumentos, y delega el flujo operativo a `hrv_app.hrv_sync_flow`.
4. `hrv_app.hrv_sync_flow` calcula las fechas objetivo (desde `ultima_fecha_CORE + 1` hasta hoy) y usa `hrv_app.dropbox_rr` para intentar cubrirlas desde JSONL/ZIP con `egc_to_rr.py`. Si `CORE` esta vacio, primero intenta reconstruir desde RR ya presentes en `data/rr_downloads/`; solo si no hay RR locales cae al bootstrap corto desde Dropbox. Dropbox es la **unica** fuente de nuevos RR matinales (AYO-13-F4): si una fecha no esta en Dropbox, esa fecha no entra al pipeline en este ciclo (sin fallback Polar).
5. `hrv_app.sleep_store` actualiza `ENDURANCE_HRV_sleep.csv`, `hrv_app.intervals_sync` resuelve la parte de wellness/Intervals y `hrv_app.pipeline_runner` llama:
   - `build_hrv_core.py`
   - `build_hrv_final_dashboard.py`
   - cada builder deja además su sidecar de trazabilidad atómico (`ENDURANCE_HRV_master_CORE_manifest.json` y `ENDURANCE_HRV_master_FINAL_manifest.json`)

Importante:
- El comando principal no cambia: `python polar_hrv_automation.py --process`.
- `polar_hrv_automation.py` ya no concentra toda la logica operativa; hoy actua como entrypoint fino.
- `build_sessions.py` no se ejecuta automaticamente en ese flujo.
- `build_hrv_final_dashboard.py` usa `ENDURANCE_HRV_sessions_day.csv` solo si ya existe.
- Si `sessions_day.csv` y `sessions_metadata.json` estan al dia, `FINAL` puede incorporar contexto de carga canonico (`ACWR`, `monotony`, `strain`, clustering de intensidad) y capas de recuperacion multisenal sin tocar el gate.
- La capa de terreno no nace aqui: se genera despues dentro de `analysis/` al correr `analysis\\run_session_analysis.py` o `analysis\\analyze_session.py`.
- Esa capa sigue siendo local a `analysis/`: hoy puede exponer `terrain_fit_context` tambien en `bike`, y en sesiones `trail`/`road` puede mostrar `climb_power_mean` cuando la fuente FIT lo declara como potencia medida; `terrain_climbs.csv` sigue siendo el detalle reproducible por climb y no cambia ningun contrato canonico global.
- Esa misma capa local de `analysis/` ya puede enriquecer el bundle de sesion con `composite_context` (`subjective_coherence`, `thermal_context`, `durability_context`) sin tocar `sessions.csv`, `sessions_day.csv` ni otros contratos canonicos.
- `analysis/hrv_rebound_profile.py` genera una lectura retrospectiva de rebote HRV D+1/D+3 como sidecar local (`analysis/reports/hrv_rebound_profile/`); sirve para analisis semanal de absorcion, no para el gate diario.
- `analysis/` deja tambien `artifacts/report_sync_status.json` para explicitar si el `report.md` o `report.ia.md` humano esta alineado con `session_payload.json`, `summary.json` y `technical_report.md`. El prompt/handoff incluyen un `report_sync_token` que debe copiarse al inicio del informe narrativo final.
- En el semanal local, `analysis/analyze_weekly.py` reutiliza `weekly_prep_manifest.json`, genera `report.auto.md`, `report.ia.md`, `analyst_prompt.md`, `ai_handoff.md` y `artifacts/report_sync_status.json` bajo `analysis/reports/weekly/<week_start>_<week_end>/`. Esta capa sigue siendo local de `analysis/` y no modifica ningún contrato canónico del pipeline principal.
- Desde esta misma fase, `analysis/run_analysis()` genera `report.md` directamente como artefacto final gobernado por pipeline. Si encuentra un `report.md` legacy sin token, crea antes un backup `report.legacy.md` y luego toma posesion del informe principal.

## 2) Script por script

## `web_ui.py`
- Que hace:
  - Levanta Flask (UI + API).
  - Expone endpoints: `/`, `/auth`, `/auth/callback`, `/oauth/callback`, `/api/sync`, `/api/sync-sessions`, `/api/status`, `/api/import-seed`, `/api/restore-backup`, `/api/delete-latest-rr`, `/health`.
  - En `/api/sync` dispara `polar_hrv_automation.py --process`.
  - En `/api/sync-sessions` dispara `build_sessions.py --update`.
  - La UI prioriza los controles operativos, una tarjeta dedicada de `Coach semanal` cuando existe `ENDURANCE_HRV_weekly_coach.json`, y despues `Detalle tecnico` / `raw output`.
- Cuando usarlo:
  - Siempre que quieras usar OAuth web y lanzar sync desde navegador.
  - Es el entrypoint de Railway.
- Entradas:
  - Variables de entorno (`PORT`, `POLAR_CLIENT_ID`, `POLAR_CLIENT_SECRET`, `PUBLIC_URL`, etc.).
- Salidas:
  - Respuestas HTTP y logs.
  - `GET /api/status` devuelve estado actual del job, `job_type` y ultimo `output/error` relevante.
  - `GET /api/status` incluye tambien el resumen semanal de `ENDURANCE_HRV_weekly_coach.json` para que la UI pinte `planning_note`, `iso_week`, `window_end`, `data_quality` y `weekly_coach_z3_budget_summary` sin crear un endpoint nuevo.
  - `POST /api/sync` y `POST /api/sync-sessions` devuelven `202 Accepted` cuando el job queda corriendo en background; si terminan practicamente al instante, pueden devolver el resultado final en la propia respuesta.
  - No genera CSV por si solo; delega al pipeline.
- Automatico o manual:
  - Automatico en Railway (start command).
  - `POST /api/sync`, `POST /api/sync-sessions`, `POST /api/import-seed`, `POST /api/restore-backup` y `POST /api/delete-latest-rr` comparten estado y no deben ejecutarse en paralelo.
  - Si `HRV_UI_KEY` está definida, todos los `/api/*` exigen la clave vía header `X-HRV-KEY` o query `?key=`; sin definir, comportamiento histórico sin autenticación.

## `canvas-tool.py`
- Que hace:
  - Gestiona `Project.canvas` mediante comandos de lectura, propuesta, inicio, pausa, cierre y dependencias.
- Cuando usarlo:
  - Solo para el workflow Kanvas documentado en `AGENTS.MD`.
- Comando base:
  - `python canvas-tool.py Project.canvas <command>`
- Importante:
  - No editar `Project.canvas` manualmente.

## `polar_hrv_automation.py`
- Que hace:
  - Es el entrypoint CLI del flujo HRV.
  - Valida configuracion, tokens y argumentos.
  - Orquesta el registro Polar cuando hace falta y delega el trabajo operativo en modulos extraidos.
  - Mantiene el contrato CLI historico del repo sin reabrir el alcance funcional.
- Cuando usarlo:
  - Sync operativo principal (CLI o disparado desde web).
- Entradas:
  - Tokens, credenciales Polar, RR ya existentes, configuracion de `HRV_DATA_DIR`.
- Salidas:
  - RR descargados + actualizacion de sleep + (si `--process`) archivos CORE/BETA/FINAL/DASHBOARD.
- Automatico o manual:
  - Manual por CLI o automatico via `web_ui.py` en `/api/sync`.

## `hrv_app.hrv_sync_flow`
- Que hace:
  - Implementa el caso de uso principal del sync HRV.
  - Si `CORE` esta vacio, primero intenta reprocesar RR locales de `data/rr_downloads/`; si no existen, hace bootstrap corto desde Dropbox.
  - Resuelve rango de fechas y cubre `target_missing_dates` desde Dropbox (AYO-13-F4); si Dropbox no cubre una fecha nueva, esa fecha no entra al pipeline (sin fallback Polar).
  - Coordina escritura de RR, ejecucion de `build_hrv_core.py`, refresco de `sleep`, sync opcional con Intervals y reporting final.
- Cuando usarlo:
  - Indirectamente desde `polar_hrv_automation.py`.
  - Tambien como referencia cuando quieras entender el flujo operativo real sin leer el entrypoint.
- Entradas:
  - Argumentos CLI ya normalizados, cliente Polar, configuracion runtime y rutas base.
- Salidas:
  - Misma salida operativa del comando principal.
- Automatico o manual:
  - Automatico dentro del entrypoint.

## `hrv_app.config`
- Que hace:
  - Centraliza constantes operativas, rutas base, flags de runtime y mappings compartidos.
  - Evita que el entrypoint tenga estado global disperso.
- Cuando usarlo:
  - Siempre que un modulo operativo necesite paths, columnas canonicas o toggles runtime.

## `hrv_app.polar_utils`
- Que hace:
  - Reune parsers y helpers compartidos para variantes de campos Polar, duraciones, numericos, flags de entorno y extractos seguros de respuestas.
- Cuando usarlo:
  - Como soporte interno de clientes y UI; no es un entrypoint.

## `hrv_app.oauth_utils`
- Que hace:
  - Implementa el intercambio OAuth `code -> token`, registro de usuario y persistencia JSON atomica reutilizada por la UI web.
- Cuando usarlo:
  - Desde los flujos OAuth; no se ejecuta directamente.

## `hrv_app.polar_sessions`
- Que hace:
  - Resuelve matching de sesiones Intervals con ejercicios Polar y extrae la capa mecanica minima, incluyendo fallback FIT cuando aplica.
- Cuando usarlo:
  - Indirectamente desde `build_sessions.py` y el modulo `analysis/`; no es un entrypoint.

## `hrv_app.dropbox_rr`
- Que hace:
  - Escanea `RR.CSV` existentes por fecha.
  - Calcula fechas objetivo faltantes.
  - Lanza `egc_to_rr.py` para cubrir fechas desde Dropbox cuando esta habilitado.
  - Respeta `HRV_DROPBOX_RR_TIMEOUT_SEC` para evitar bloqueos indefinidos en el subprocess.
- Cuando usarlo:
  - Como capa operativa de cobertura RR principal.
- Importante:
  - Dropbox es la unica fuente de nuevos RR matinales (AYO-13-F4). Si una fecha nueva no esta cubierta en Dropbox, esa fecha no entra al pipeline en este ciclo; no hay fallback Polar para RR nuevos.
  - Correcciones de fechas ya existentes en CORE quedan fuera de alcance de F4 (requieren reprocesado manual del periodo, fuera de este flujo automatico).

## `hrv_app.polar_auth_v4`, `hrv_app.polar_client_v4`, `hrv_app.polar_adapters_v4`
- Que hacen:
  - `polar_auth_v4`: OAuth contra `auth.polar.com` con refresh token obligatorio, bundle separado (`polar_tokens_v4.json`) y rotacion atomica bajo lock.
  - `polar_client_v4`: cliente HTTP de la Dynamic API v4; lo consumen el gateway de sleep/nightly y `PolarSessionClient`.
  - `polar_adapters_v4`: convierte respuestas v4 al shape interno que consumen `sleep_store`, `hrv_sync_flow` y `polar_sessions`.
- Mascara `offline` en RR:
  - El adaptador añade `"offline": "0,1,0,..."` (mismo orden que `data`).
  - `hrv_app.hrv_sync_flow.extract_rr_ms` la consume: un RR en rango fisiologico pero marcado `offline=true` queda como artefacto.
  - No cambia el contrato del CSV RR ni los CSVs canonicos.
- Importante:
  - El catalogo de deportes usa `GET /v4/data/sports/list` y requiere el scope `sports:read`.
  - Los samples mecanicos en sesiones reales usan tipos string (`SPEED`, `CADENCE`, `POWER`/`LEFT_CRANK_CURRENT_POWER`).

## `hrv_app.sleep_store`
- Que hace:
  - Persiste y recalcula `ENDURANCE_HRV_sleep.csv`.
  - Normaliza campos de sleep y nightly recharge, hace upsert por fecha y recalcula derivados.
- Cuando usarlo:
  - Siempre que el flujo HRV necesite actualizar sueno/capas de recuperacion.

## `hrv_app.intervals_sync`
- Que hace:
  - Construye payloads wellness y resuelve el sync opcional con Intervals.icu.
  - Lee el ultimo master y agrega contexto de activities cuando hace falta.
- Cuando usarlo:
  - Solo como sidecar operativo del sync HRV.

## `hrv_app.cli_reporting`
- Que hace:
  - Genera el reporting textual del CLI y los resumenes diarios/7d.
- Cuando usarlo:
  - Cuando necesites presentation/output humano del flujo sin mezclarlo con la logica operativa.

## `hrv_app.pipeline_runner`
- Que hace:
  - Encapsula el lanzamiento de los scripts de pipeline como subprocesos: `build_hrv_core.py`, `build_hrv_final_dashboard.py`, `build_hrv_ssm.py`, `build_hrv_ssm_validation.py` y `build_hrv_ssm_outcome_battery.py`.
  - Centraliza el entorno de subprocess (UTF-8), la construccion de comandos y el manejo de errores.
  - Expone funciones `run_build_hrv_*_only()` que devuelven bool segun exito.
- Cuando usarlo:
  - Siempre que el flujo principal necesite ejecutar builders sin mantener ese detalle en el entrypoint.

## `hrv_app.io_utils`
- Que hace:
  - Proporciona `write_csv_atomic`, `write_json_atomic`, `write_text_atomic` y `json_safe` compartidos por todos los módulos que escriben artefactos canónicos.
  - Todas las escrituras usan `tempfile + os.replace` con retry ante `PermissionError`.
- Cuando usarlo:
  - Lo importan `build_hrv_core.py`, `build_hrv_final_dashboard.py`, `build_sessions.py`, `build_hrv_ssm.py` y `hrv_app/backup_dropbox.py`. No se llama directamente desde el flujo operativo.

## `hrv_app.backup_dropbox`
- Que hace:
  - Backup opcional de los `ENDURANCE_HRV_*.csv/.json` a Dropbox tras un sync exitoso.
  - Sube los artefactos canónicos a una carpeta plana (`/hrv_backups/`), sobrescribiendo cada archivo (Dropbox conserva versiones anteriores por su cuenta).
  - Restaura archivos desde Dropbox a `DATA_DIR` con escritura atómica y backup previo de los archivos existentes en `data/backup/pre_restore/`.
  - Reutiliza las credenciales Dropbox ya configuradas para la ingesta RR.
- Cuando usarlo:
  - El backup se ejecuta automáticamente al final de cada sync si `HRV_BACKUP_DROPBOX_ENABLED=1`.
  - La restauración se invoca desde `POST /api/restore-backup` en la UI web.
  - NUNCA lanza excepciones en el backup (el sync continua); la restauración sí lanza si falta credencial o no hay archivos en `/hrv_backups/`.
- Entradas:
  - Variables de entorno Dropbox (`DROPBOX_ACCESS_TOKEN` o refresh trio), `HRV_BACKUP_DROPBOX_PATH`.
- Salidas:
  - Archivos subidos/descargados a/desde Dropbox, dict de resultado con status.

## `hrv_app.eval_utils`
- Que hace:
  - Proporciona `ols_predict`, `evaluate_predictor` y `bootstrap_delta_mae` compartidos por los modulos SSM.
  - `evaluate_predictor` calcula Spearman, holdout MAE/RMSE (80/20 OLS) y walk-forward MAE.
  - `bootstrap_delta_mae` da CI90 sobre la diferencia de MAE entre dos predictores (1000 iteraciones).
- Cuando usarlo:
  - Lo importa `build_hrv_ssm_outcome_battery.py`. No se llama directamente desde el flujo operativo.

## `egc_to_rr.py`
- Que hace:
  - Busca pares `ECG.jsonl` + `ACC.jsonl` en carpeta local o Dropbox.
  - Convierte cada par a un RR compatible con la app.
  - Guarda RR con nomenclatura tipo `ENDURANCE_YYYY-MM-DD_from_jsonl_RR.CSV`.
  - Puede guardar ficheros auxiliares en subcarpeta (por defecto `_aux_jsonl`).
- Cuando usarlo:
  - Manualmente para validar conversiones.
  - Automaticamente cuando lo invoca `polar_hrv_automation.py` para cubrir fechas faltantes.
- Entradas:
  - Local: `--input-dir` o `--ecg` + `--acc`.
  - Dropbox: `--dropbox-folder` + credenciales Dropbox.
  - Credenciales Dropbox segun fuente configurada.
- Salidas:
  - RR en `data/rr_downloads`.
  - Opcional: artefactos de apoyo en `_aux_jsonl`.
- Automatico o manual:
  - Ambos.

## `build_hrv_core.py`
- Que hace:
  - Procesa RR crudos.
  - Calcula metrica HRV estable por dia.
  - Genera:
    - `ENDURANCE_HRV_master_CORE.csv`
    - `ENDURANCE_HRV_master_BETA_AUDIT.csv`
- Cuando usarlo:
  - Siempre que quieras transformar RR en dataset CORE/AUDIT.
- Entradas:
  - RR (`--rr-file` o `--rr-dir`, normalmente `data/rr_downloads`).
- Salidas:
- CORE y BETA_AUDIT.
  - `ENDURANCE_HRV_master_CORE_manifest.json` como sidecar atómico de trazabilidad de la corrida.
- Automatico o manual:
  - Automatico dentro de `polar_hrv_automation.py --process`.
  - Tambien se puede correr manual.

## `build_hrv_final_dashboard.py`
- Que hace:
  - Lee CORE + sleep.
- Aplica la logica del decisor FINAL/DASHBOARD (decision operativa diaria).
  - Enriquce `reason_text` con contexto de sueno y carga.
  - Construye internamente `reason_items` estructurados y despues renderiza `reason_text` desde esa capa.
  - Publica ademas `ENDURANCE_HRV_master_FINAL_reason_items.json` como sidecar estable para consumo de `analysis/`.
  - Valida semanticamente cada motivo con enums cerrados de `layer` (`measured/proxy/inference/action`) y `severity` (`low/medium/high/very_high`).
  - Consume la capa de contexto canonico de carga desde `ENDURANCE_HRV_sessions_day.csv`:
    - `acwr_simple_prev`
    - `monotony_7d_prev`
    - `strain_7d_prev`
    - `load_ctx_ready`
  - Consume la capa de clustering reciente de intensidad:
    - `intense_day`
    - `intense_days_prev_3d`
    - `intense_days_prev_5d`
    - `intensity_clustering_flag`
    - `intensity_clustering_level`
  - Construye la capa de contexto de recuperacion multisenal sin tocar el gate:
    - `recovery_context_quality`
    - `recovery_support_class`
    - `recovery_discordance_flag`
    - `recovery_discordance_reason`
  - Si existe `ENDURANCE_HRV_sessions_day.csv`, usa sus campos de carga.
  - Genera:
    - `ENDURANCE_HRV_master_FINAL.csv` (66 columnas)
    - `ENDURANCE_HRV_master_DASHBOARD.csv`
- Cuando usarlo:
  - Siempre que quieras pasar de CORE a salida operativa FINAL/DASHBOARD.
- Entradas:
  - `ENDURANCE_HRV_master_CORE.csv`
- `ENDURANCE_HRV_sleep.csv`
  - Opcional: `ENDURANCE_HRV_sessions_day.csv`
- Salidas:
  - FINAL y DASHBOARD.
  - `ENDURANCE_HRV_master_FINAL_manifest.json` como sidecar atómico de trazabilidad de la corrida.
  - `reason_items` sigue sin exponerse como columna en `FINAL` ni en `DASHBOARD`, pero ahora tambien se serializa en `ENDURANCE_HRV_master_FINAL_reason_items.json`.
  - `FINAL` mantiene `gate_final`, `Action` y `Action_detail` como arbitros operativos.
  - La recuperación multiseñal solo aporta soporte o discordancia objetiva via columnas y `reason_text`.
  - El contexto de carga y el clustering solo aportan contexto en `reason_text`; no recolorean el gate.
  - El manifest de `FINAL/DASHBOARD` enlaza al manifest de `CORE` por ruta, hash de archivo y hash efectivo de configuración cuando está disponible.
  - `analysis/` puede tratar el sidecar como fuente estructurada primaria cuando `fallback_to_reason_text = false`, pero eso no cambia el contrato público de los CSV.
- Automatico o manual:
  - Automatico dentro de `polar_hrv_automation.py --process`.
  - Tambien se puede correr manual.

## `build_sessions.py`
- Que hace:
  - Extrae sesiones de entrenamiento desde Intervals API.
  - Construye:
    - `ENDURANCE_HRV_sessions.csv` (detalle por sesion)
    - `ENDURANCE_HRV_sessions_day.csv` (agregado diario + rolling)
    - `ENDURANCE_HRV_intensity_distribution_weekly.csv` (resumen semanal por deporte del patron de distribucion observada)
    - `ENDURANCE_HRV_weekly_coach.json` (resumen semanal estructurado con marcas de corte, cobertura y contexto retrospectivo de Z3)
    - `ENDURANCE_HRV_sessions_metadata.json`
    - `ENDURANCE_HRV_wellness_subjective.csv` (wellness subjetivo diario desde Intervals, si hay cobertura)
  - Canoniza la capa de señal mecanica minima en `sessions.csv` para deportes de pie:
    - `mechanics_source`
    - `run_power_*`
    - `speed_first_half`, `speed_second_half`
    - `cadence_first_half`, `cadence_second_half`
  - Canoniza la extracción mínima de coach metrics en `sessions.csv`:
    - `calories`
    - `average_cadence`
    - `average_weather_temp`
    - `hrr_drop_bpm`
    - `trimp`
    - y, si `device_watts=true`, `icu_weighted_avg_watts`, `icu_joules_above_ftp`, `icu_max_wbal_depletion`, `decoupling`
  - Canoniza la capa de contexto de carga en `sessions_day.csv`:
    - `acwr_simple_prev`
    - `monotony_7d_prev`
    - `strain_7d_prev`
    - `load_ctx_ready`
  - Canoniza la capa de clustering proactivo en `sessions_day.csv`:
    - `intense_day`
    - `intense_days_prev_3d`
    - `intense_days_prev_5d`
    - `intensity_clustering_flag`
    - `intensity_clustering_level`
  - Embebe la auditoria ligera por capas en `ENDURANCE_HRV_sessions_metadata.json`:
    - `training_audit.dataset_level`
    - `training_audit.signal_level`
    - `training_audit.metric_level`
  - No genera la capa local de terreno de `analysis`:
    - no persiste `terrain_context`
    - no persiste `terrain_fit_context`
    - no escribe `terrain_intervals.csv` ni `terrain_climbs.csv`
- Cuando usarlo:
  - Cuando quieras actualizar la capa de carga de entrenamiento.
  - Recomendado en cron separado (diario/backfill), no dentro del sync Polar.
- Entradas:
  - `INTERVALS_API_KEY`, `INTERVALS_ATHLETE_ID` y parametros (`--daily`, `--backfill`, `--update`, `--date`, `--oldest`, `--no-streams`, `--no-notes`).
- Modos utiles:
  - `--backfill`: historico completo desde `--oldest`.
  - `--daily`: ultimas 48h.
  - `--update`: desde el ultimo dia con datos hasta hoy, releyendo tambien ese ultimo dia.
  - `--date YYYY-MM-DD`: un dia concreto.
  - `--no-streams`: omite descarga y procesado de streams cuando quieres una corrida mas ligera.
  - `--no-notes`: omite notas/wellness textual cuando quieres minimizar dependencias de contenido libre.
- Salidas:
  - CSVs de sesiones, distribucion semanal, wellness subjetivo y metadata.
  - `sessions.csv` pasa a ser la fuente canonica de detalle por sesion, incluidos coste, zonas, drift, mecanica minima y la extracción mínima cerrada de coach metrics por sesión.
  - `sessions_day.csv` pasa a ser la fuente canonica de rolling de carga y clustering para `reason_text`.
  - `intensity_distribution_weekly.csv` pasa a ser la salida canonica de distribucion observada por `sport x week`.
  - `ENDURANCE_HRV_weekly_coach.json` pasa a ser el sidecar canonico de resumen semanal estructurado para consumo posterior.
  - Ese sidecar puede incluir:
    - `z3_budget_by_sport` como lectura retrospectiva estructurada de percentil historico de Z3 por deporte o familia
    - `z3_budget_summary` como resumen corto visible en UI (`Contexto Z3 semanal`), deliberadamente asimetrico y solo surfaceado para bandas `high/very_high`
  - Esta capa sigue siendo retrospectiva y no introduce prescripcion automatica ni modifica `sessions_day`, `FINAL`, `DASHBOARD` o `reason_text`.
  - `sessions_metadata.json` pasa a ser la fuente canonica de `training_audit` para rebajar confianza de coaching/carga sin bloquear pipeline.
- Automatico o manual:
  - Manual (no lo llama el flujo principal por defecto).

## `intervals_wellness_test.py`
- Que hace:
  - Script de prueba para hacer `PUT` de un campo wellness en Intervals.
  - Sirve para validar auth/payload/campo custom.
- Cuando usarlo:
  - Diagnostico tecnico puntual.
- Entradas:
  - API key, athlete id, fecha, field, value.
- Salidas:
  - Respuesta HTTP en consola.
- Automatico o manual:
  - Manual, no operativo.
- Ruta actual:
  - `scripts/python/intervals_wellness_test.py`

## `intervals_resting_hr_from_core.py`
- Que hace:
  - Lee `HR_stable` desde CORE y lo sube a wellness (`restingHR`) en Intervals.
  - Permite enviar un dia, rango, o todo el CSV.
- Cuando usarlo:
  - Backfill/correccion manual de `restingHR` en Intervals.
- Entradas:
  - `ENDURANCE_HRV_master_CORE.csv` + credenciales Intervals.
- Salidas:
  - Requests PUT a Intervals (sin generar CSV nuevo).
- Automatico o manual:
  - Manual, no parte del pipeline principal.
- Ruta actual:
  - `scripts/python/intervals_resting_hr_from_core.py`

## `add_ans_balance_to_core.py`
- Que hace:
  - Reprocesa RR y calcula metricas ANS:
    - `SI_baevsky`
    - `SD1`
    - `SD2`
    - `SD1_SD2_ratio`
  - Hace merge por `Fecha` dentro de `ENDURANCE_HRV_master_CORE.csv`.
- Cuando usarlo:
  - Analisis adicional o enriquecimiento de CORE.
- Entradas:
  - RR en `data/rr_downloads` (o `--rr-dir`) + CORE.
- Salidas:
  - CORE actualizado con columnas ANS.
- Automatico o manual:
  - Manual, fuera del flujo principal.
- Ruta actual:
  - `scripts/python/add_ans_balance_to_core.py`

## `build_historical_hrv_compare.py`
- Que hace:
  - Script historico/one-off para reconstruir contexto y comparar salidas sobre datasets antiguos.
  - Puede generar salidas temporales de comparativa con sufijos legacy, fuera del contrato canonico actual.
- Cuando usarlo:
  - Analisis historico, validaciones, comparativas de version.
- Entradas:
  - Fuentes historicas con rutas hardcodeadas (no pensado para Railway runtime actual).
- Salidas:
  - CSVs historicos de comparativa, no canónicos.
- Automatico o manual:
  - Manual, fuera del flujo operativo.
- Ruta actual:
  - `scripts/python/build_historical_hrv_compare.py`

## `build_hrv_ssm.py`
- Que hace:
  - Genera la capa sombra SSM de Fase 1: Banister de dos estados (lento/rapido) con observacion HRV matinal y observacion nocturna de sueno opcional como segunda fuente.
  - Escribe `ENDURANCE_HRV_ssm_shadow.csv` (30 cols) y `ENDURANCE_HRV_ssm_shadow_metadata.json`.
  - Expone `preprocess_base()` para precomputar la parte invariante (obs_quality, load_context, sleep_context) y `run_ssm_from_base()` para ejecutar solo el Kalman sobre un base ya procesado — util para validacion con multiples configuraciones sin recalcular lo costoso.
  - No modifica `FINAL.csv`, no toca el gate y no se expone en la UI operativa.
- Cuando usarlo:
  - Automaticamente tras `build_hrv_final_dashboard.py` en cada sync via `hrv_app.hrv_sync_flow`.
  - Manualmente: `python build_hrv_ssm.py [--data-dir <dir>]`.
  - Su parser es minimo: solo reconoce `--data-dir`; no ofrece `--help` y los argumentos desconocidos se ignoran.
- Entradas:
  - `ENDURANCE_HRV_master_CORE.csv`, `ENDURANCE_HRV_sessions_day.csv`, `ENDURANCE_HRV_sleep.csv` (opcional).
- Salidas:
  - `ENDURANCE_HRV_ssm_shadow.csv`, `ENDURANCE_HRV_ssm_shadow_metadata.json`.
- Automatico o manual:
  - Automatico en cada sync HRV. Manual disponible.

## `build_hrv_ssm_validation.py`
- Que hace:
  - Genera el reporte reproducible de validacion Fase 1 del modelo SSM: elige el outcome principal (FDS sobre `cardiac_drift_worst` normalizado por deporte), construye pares temporales, evalua SSM vs rolling vs load vs EWMA con walk-forward, bootstrap CI, estratificacion por deporte, comparador estructural (beta=0 vs ARX) y comparador de sueno.
  - Escribe `ENDURANCE_HRV_ssm_validation_report.json` y `.md`.
  - El resultado no forma parte del contrato estatico: debe leerse de `phase1_conclusion`, `go_no_go` y `primary_strict_by_sport` en el JSON regenerado.
  - No modifica el gate.
- Cuando usarlo:
  - Manualmente: `python build_hrv_ssm_validation.py [--data-dir <dir>]`.
  - Su parser es minimo: solo reconoce `--data-dir`; no ofrece `--help` y los argumentos desconocidos se ignoran.
  - Bajo demanda cuando se quiera reevaluar si el SSM aporta valor; no forma parte del sync HRV diario.
  - O de forma agrupada via `python polar_hrv_automation.py --ssm-audit`, que primero regenera `ssm_shadow`.
- Entradas:
  - `ENDURANCE_HRV_ssm_shadow.csv`, `ENDURANCE_HRV_ssm_shadow_metadata.json`, `ENDURANCE_HRV_master_CORE.csv`, `ENDURANCE_HRV_sessions_day.csv`, `ENDURANCE_HRV_sessions.csv`, `ENDURANCE_HRV_sleep.csv`, `ENDURANCE_HRV_master_FINAL.csv`.
- Salidas:
  - `ENDURANCE_HRV_ssm_validation_report.json`, `ENDURANCE_HRV_ssm_validation_report.md`.
- Automatico o manual:
  - Manual bajo demanda.

## `build_hrv_ssm_outcome_battery.py`
- Que hace:
  - Prueba el predictor SSM contra outcomes alternativos a `cardiac_drift_worst`: `lnRMSSD_t+1` y `well_fatigue_raw_t+1`.
  - Incluye comparadores SSM, rolling HRV 7d, AR(1), EWMA grid y bootstrap CI.
  - Los hallazgos dependen del dataset: deben leerse en `outcomes` y `battery_conclusion` del JSON regenerado, no copiarse como una propiedad permanente del script.
  - No modifica el gate.
- Cuando usarlo:
  - Manualmente: `python build_hrv_ssm_outcome_battery.py [--data-dir <dir>]`.
  - Su parser es minimo: solo reconoce `--data-dir`; no ofrece `--help` y los argumentos desconocidos se ignoran.
  - Bajo demanda, normalmente despues de lanzar la validacion SSM manual.
  - O de forma agrupada via `python polar_hrv_automation.py --ssm-audit`.
- Entradas:
  - `ENDURANCE_HRV_master_CORE.csv`, `ENDURANCE_HRV_ssm_shadow.csv`, `ENDURANCE_HRV_wellness_subjective.csv`.
- Salidas:
  - `ENDURANCE_HRV_ssm_outcome_battery.json`, `ENDURANCE_HRV_ssm_outcome_battery.md`.
- Automatico o manual:
  - Manual bajo demanda.

## 3) Resumen practico

Si tu pregunta es "que scripts importan para operar dia a dia":

1. `web_ui.py` (servidor web)
2. `polar_hrv_automation.py` (sync y orquestacion)
3. `egc_to_rr.py` (Dropbox/local JSONL -> RR, cuando faltan fechas o para validacion manual)
4. `build_hrv_core.py` (RR -> CORE/BETA)
5. `build_hrv_final_dashboard.py` (CORE -> FINAL/DASHBOARD + contexto de recuperación multiseñal)

Y aparte, opcionales recomendados:

1. `build_sessions.py` para mantener al dia `sessions.csv`, `sessions_day.csv`, `ENDURANCE_HRV_weekly_coach.json`, `sessions_metadata.json` y `wellness_subjective.csv`, y asi habilitar el clustering, la señal mecánica mínima, el contexto de carga, la auditoría por capas, el wellness subjetivo y el resumen semanal.
2. `build_hrv_ssm.py` se ejecuta automaticamente tras cada sync HRV para regenerar `ENDURANCE_HRV_ssm_shadow.csv`. `build_hrv_ssm_validation.py` y `build_hrv_ssm_outcome_battery.py` quedan como herramientas manuales bajo demanda: son sombra pura, no tocan `FINAL`, no recoloran el gate y sirven para reevaluar si el SSM aporta valor. El veredicto vigente debe leerse de los JSON regenerados, porque cambia con el dataset.
   - Entry point recomendado: `python polar_hrv_automation.py --ssm-audit`
3. `analysis\\analyze_session.py` o `analysis\\run_session_analysis.py` cuando quieras explotar la capa analitica local sin tocar contratos canonicos:
   - terreno (`GAP`, `VAM`, potencia por split y climbs FIT`; en `bike`, la capa FIT puede anadir potencia estimada local por subida)
   - `composite_context` (`subjective_coherence`, `thermal_context`, `durability_context`)
   - `narrative_targets` (`error_context`, `exit_context`, `final_reason_rendered`); `exit_context.block_role_signals.load_rank_in_sport_7d` usa una ventana real de 7 dias por deporte, no un recorte visual de sesiones recientes
   - para sesiones `trail_run`: capa shadow (`runaware_context`, `v1_shadow_history`) — validacion paralela del clustering v1 con senal de terreno y potencia de carrera; shadow-only, no modifica ningun contrato canonico
4. `analysis\\hrv_rebound_profile.py` cuando quieras revisar la absorcion HRV de forma retrospectiva por semana o por bloque, sin mezclar esa lectura con el gate diario ni con `sessions_day`.

