# Guia didactica de scripts Python

Este documento explica, en lenguaje simple, que hace cada `.py` del proyecto, en que flujo participa y como encaja la conversion `ECG.jsonl + ACC.jsonl -> RR`.

## 1) Mapa rapido del flujo principal

Flujo operativo normal (Railway o UI local):

1. `web_ui.py` levanta la web.
2. Al llamar `POST /api/sync`, la web ejecuta `python polar_hrv_automation.py --process`.
3. `polar_hrv_automation.py` valida entorno, tokens y argumentos, y delega el flujo operativo a `hrv_app.hrv_sync_flow`.
4. `hrv_app.hrv_sync_flow` calcula las fechas objetivo y trata Dropbox como fuente principal de cobertura RR, usando `hrv_app.dropbox_rr` para intentar cubrirlas desde JSONL/ZIP con `egc_to_rr.py`.
5. Solo para fechas que sigan sin cobertura RR, usa `hrv_app.polar_client` como fallback contra Polar.
6. `hrv_app.sleep_store` actualiza `ENDURANCE_HRV_sleep.csv`, `hrv_app.intervals_sync` resuelve la parte de wellness/Intervals y `hrv_app.pipeline_runner` llama:
   - `build_hrv_core.py`
   - `build_hrv_final_dashboard.py`

Importante:
- El comando principal no cambia: `python polar_hrv_automation.py --process`.
- `polar_hrv_automation.py` ya no concentra toda la logica operativa; hoy actua como entrypoint fino.
- `build_sessions.py` no se ejecuta automaticamente en ese flujo.
- `build_hrv_final_dashboard.py` usa `ENDURANCE_HRV_sessions_day.csv` solo si ya existe.
- Si `sessions_day.csv` y `sessions_metadata.json` estan al dia, `FINAL` puede incorporar contexto de carga canonico (`ACWR`, `monotony`, `strain`, clustering de intensidad) y capas de recuperacion multisenal sin tocar el gate.
- La capa de terreno `FP-02` no nace aqui: se genera despues dentro de `analysis/` al correr `analysis\\run_session_analysis.py` o `analysis\\analyze_session.py`.
- Esa capa sigue siendo local a `analysis/`: hoy puede exponer `terrain_fit_context` tambien en `bike`, y en sesiones `trail`/`road` puede mostrar `climb_power_mean` cuando la fuente FIT lo declara como potencia medida; `terrain_climbs.csv` sigue siendo el detalle reproducible por climb y no cambia ningun contrato canonico global.
- Esa misma capa local de `analysis/` ya puede enriquecer el bundle de sesion con `composite_context` (`subjective_coherence`, `thermal_context`, `durability_context`) sin tocar `sessions.csv`, `sessions_day.csv` ni otros contratos canonicos.
- Desde `SYA-01`, `analysis/` deja tambien `artifacts/report_sync_status.json` para explicitar si el `report.md` humano esta alineado con `session_payload.json`, `summary.json` y `technical_report.md`. El prompt/handoff incluyen un `report_sync_token` que debe copiarse al inicio del `report.md`.
- Desde esta misma fase, `analysis/run_analysis()` genera `report.md` directamente como artefacto final gobernado por pipeline. Si encuentra un `report.md` legacy sin token, crea antes un backup `report.legacy.md` y luego toma posesion del informe principal.

## 2) Script por script

## `web_ui.py`
- Que hace:
  - Levanta Flask (UI + API).
  - Expone endpoints: `/`, `/auth`, `/auth/callback`, `/oauth/callback`, `/api/sync`, `/api/sync-sessions`, `/api/status`, `/api/import-seed`, `/api/delete-latest-rr`, `/health`.
  - En `/api/sync` dispara `polar_hrv_automation.py --process`.
  - En `/api/sync-sessions` dispara `build_sessions.py --update`.
  - La UI actual prioriza `Detalle tecnico` / `raw output` como bloque principal visible.
- Cuando usarlo:
  - Siempre que quieras usar OAuth web y lanzar sync desde navegador.
  - Es el entrypoint de Railway.
- Entradas:
  - Variables de entorno (`PORT`, `POLAR_CLIENT_ID`, `POLAR_CLIENT_SECRET`, `PUBLIC_URL`, etc.).
- Salidas:
  - Respuestas HTTP y logs.
  - `GET /api/status` devuelve estado actual del job, `job_type` y ultimo `output/error` relevante.
  - `POST /api/sync` y `POST /api/sync-sessions` devuelven `202 Accepted` cuando el job queda corriendo en background; si terminan practicamente al instante, pueden devolver el resultado final en la propia respuesta.
  - No genera CSV por si solo; delega al pipeline.
- Automatico o manual:
  - Automatico en Railway (start command).
  - `POST /api/sync`, `POST /api/sync-sessions`, `POST /api/import-seed` y `POST /api/delete-latest-rr` comparten estado y no deben ejecutarse en paralelo.

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
  - Resuelve rango de fechas y decide si la cobertura RR viene de Dropbox o, en fallback, de Polar.
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

## `hrv_app.dropbox_rr`
- Que hace:
  - Escanea `RR.CSV` existentes por fecha.
  - Calcula fechas objetivo faltantes.
  - Lanza `egc_to_rr.py` para cubrir fechas desde Dropbox cuando esta habilitado.
  - Respeta `HRV_DROPBOX_RR_TIMEOUT_SEC` para evitar bloqueos indefinidos en el subprocess.
- Cuando usarlo:
  - Como capa operativa de cobertura RR principal.
- Importante:
  - Dropbox es hoy la fuente principal esperada de RR matinales.
  - Polar no compite con Dropbox como fuente primaria; se usa como fallback cuando Dropbox no cubre.

## `hrv_app.polar_client`
- Que hace:
  - Encapsula las llamadas HTTP a Polar AccessLink.
  - Lista ejercicios, descarga detalle con samples y fetch de sleep/nightly recharge.
  - Resuelve el registro del usuario Polar contra AccessLink.
- Cuando usarlo:
  - Como capa de red/fallback Polar, no como entrypoint.

## `hrv_app.polar_oauth_local`
- Que hace:
  - Mantiene el flujo OAuth local con callback HTTP local para uso `dev-only`.
  - Carga tokens y soporta el flujo interactivo local cuando no se usa la UI web.
- Importante:
  - No es el flujo productivo de Railway.
  - En produccion el OAuth canonico sigue siendo el web de `web_ui.py`.

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
  - Encapsula el lanzamiento de `build_hrv_core.py` y `build_hrv_final_dashboard.py`.
  - Centraliza el entorno de subprocess y la construccion de comandos.
- Cuando usarlo:
  - Siempre que el flujo principal necesite ejecutar builders sin mantener ese detalle en el entrypoint.

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
- Automatico o manual:
  - Automatico dentro de `polar_hrv_automation.py --process`.
  - Tambien se puede correr manual.

## `build_hrv_final_dashboard.py`
- Que hace:
  - Lee CORE + sleep.
- Aplica la logica del decisor FINAL/DASHBOARD (decision operativa diaria).
  - Enriquce `reason_text` con contexto de sueno y carga.
  - Desde SS-01, construye internamente `reason_items` estructurados y despues renderiza `reason_text` desde esa capa.
  - Desde SS-02, publica ademas `ENDURANCE_HRV_master_FINAL_reason_items.json` como sidecar estable para consumo de `analysis/`.
  - Valida semanticamente cada motivo con enums cerrados de `layer` (`measured/proxy/inference/action`) y `severity` (`low/medium/high/very_high`).
  - Consume la capa CDC-01 de contexto canonico de carga desde `ENDURANCE_HRV_sessions_day.csv`:
    - `acwr_simple_prev`
    - `monotony_7d_prev`
    - `strain_7d_prev`
    - `load_ctx_ready`
  - Consume la capa AP-01 de clustering reciente de intensidad:
    - `intense_day`
    - `intense_days_prev_3d`
    - `intense_days_prev_5d`
    - `intensity_clustering_flag`
    - `intensity_clustering_level`
  - Construye la capa RE-01 de contexto de recuperacion multisenal sin tocar el gate:
    - `recovery_context_quality`
    - `recovery_support_class`
    - `recovery_discordance_flag`
    - `recovery_discordance_reason`
  - Si existe `ENDURANCE_HRV_sessions_day.csv`, usa sus campos de carga.
  - Genera:
    - `ENDURANCE_HRV_master_FINAL.csv` (62 columnas)
    - `ENDURANCE_HRV_master_DASHBOARD.csv`
- Cuando usarlo:
  - Siempre que quieras pasar de CORE a salida operativa FINAL/DASHBOARD.
- Entradas:
  - `ENDURANCE_HRV_master_CORE.csv`
- `ENDURANCE_HRV_sleep.csv`
  - Opcional: `ENDURANCE_HRV_sessions_day.csv`
- Salidas:
  - FINAL y DASHBOARD.
  - `reason_items` sigue sin exponerse como columna en `FINAL` ni en `DASHBOARD`, pero ahora tambien se serializa en `ENDURANCE_HRV_master_FINAL_reason_items.json`.
  - `FINAL` mantiene `gate_final`, `Action` y `Action_detail` como arbitros operativos.
  - RE-01 solo aporta soporte o discordancia objetiva via columnas y `reason_text`.
  - CDC-01 y AP-01 solo aportan contexto de carga/clustering en `reason_text`; no recolorean el gate.
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
    - `ENDURANCE_HRV_sessions_metadata.json`
    - `ENDURANCE_HRV_wellness_subjective.csv` (wellness subjetivo diario desde Intervals, si hay cobertura)
  - Canoniza la capa AP-02 de señal mecanica minima en `sessions.csv` para deportes de pie:
    - `mechanics_source`
    - `run_power_*`
    - `speed_first_half`, `speed_second_half`
    - `cadence_first_half`, `cadence_second_half`
  - Canoniza la extracción mínima de `SYA-04` en `sessions.csv`:
    - `calories`
    - `average_cadence`
    - `average_weather_temp`
    - `hrr_drop_bpm`
    - `trimp`
    - y, si `device_watts=true`, `icu_weighted_avg_watts`, `icu_joules_above_ftp`, `icu_max_wbal_depletion`, `decoupling`
  - Canoniza la capa CDC-01 de contexto de carga en `sessions_day.csv`:
    - `acwr_simple_prev`
    - `monotony_7d_prev`
    - `strain_7d_prev`
    - `load_ctx_ready`
  - Canoniza la capa AP-01 de clustering proactivo en `sessions_day.csv`:
    - `intense_day`
    - `intense_days_prev_3d`
    - `intense_days_prev_5d`
    - `intensity_clustering_flag`
    - `intensity_clustering_level`
  - Embebe la capa ADC-01 de auditoria ligera por capas en `ENDURANCE_HRV_sessions_metadata.json`:
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

## 3) Resumen practico

Si tu pregunta es "que scripts importan para operar dia a dia":

1. `web_ui.py` (servidor web)
2. `polar_hrv_automation.py` (sync y orquestacion)
3. `egc_to_rr.py` (Dropbox/local JSONL -> RR, cuando faltan fechas o para validacion manual)
4. `build_hrv_core.py` (RR -> CORE/BETA)
5. `build_hrv_final_dashboard.py` (CORE -> FINAL/DASHBOARD + RE-01 recovery context)

Y aparte, opcional recomendado:

1. `build_sessions.py` para mantener al dia `sessions.csv`, `sessions_day.csv`, `sessions_metadata.json` y `wellness_subjective.csv`, y asi habilitar AP-01, AP-02, CDC-01, ADC-01 y RE-02 en el contexto del sistema.
2. `analysis\\analyze_session.py` o `analysis\\run_session_analysis.py` cuando quieras explotar la capa analitica local sin tocar contratos canonicos:
   - terreno (`GAP`, `VAM`, potencia por split y climbs FIT`; en `bike`, la capa FIT puede anadir potencia estimada local por subida)
   - `composite_context` de `SYA-07` (`subjective_coherence`, `thermal_context`, `durability_context`)
   - para sesiones `trail_run`: capa shadow AP-03 (`runaware_context`, `v1_shadow_history`) — validacion paralela del clustering AP-01 v1 con senal de terreno y potencia de carrera; shadow-only, no modifica ningun contrato canonico

