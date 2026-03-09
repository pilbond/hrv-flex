# Guia didactica de scripts Python

Este documento explica, en lenguaje simple, que hace cada `.py` del proyecto, en que flujo participa y como encaja la conversion `ECG.jsonl + ACC.jsonl -> RR`.

## 1) Mapa rapido del flujo principal

Flujo operativo normal (Railway o UI local):

1. `web_ui.py` levanta la web.
2. Al llamar `POST /api/sync`, la web ejecuta `python polar_hrv_automation.py --process`.
3. `polar_hrv_automation.py` detecta fechas faltantes en CORE.
4. Si hay faltantes y Drive esta habilitado, intenta generar RR desde JSONL con `egc_to_rr.py`.
5. Para lo que siga faltando, usa el flujo normal de descarga RR desde Polar.
6. `polar_hrv_automation.py` actualiza sleep y luego llama:
   - `endurance_hrv.py`
   - `endurance_v4lite.py`

Importante:
- El comando principal no cambia: `python polar_hrv_automation.py --process`.
- `build_sessions.py` no se ejecuta automaticamente en ese flujo.
- `endurance_v4lite.py` usa `ENDURANCE_HRV_sessions_day.csv` solo si ya existe.

## 2) Script por script

## `web_ui.py`
- Que hace:
  - Levanta Flask (UI + API).
  - Expone endpoints: `/`, `/auth`, `/auth/callback`, `/oauth/callback`, `/api/sync`, `/api/status`, `/health`.
  - En `/api/sync` dispara `polar_hrv_automation.py --process`.
- Cuando usarlo:
  - Siempre que quieras usar OAuth web y lanzar sync desde navegador.
  - Es el entrypoint de Railway.
- Entradas:
  - Variables de entorno (`PORT`, `POLAR_CLIENT_ID`, `POLAR_CLIENT_SECRET`, `PUBLIC_URL`, etc.).
- Salidas:
  - Respuestas HTTP y logs.
  - No genera CSV por si solo; delega al pipeline.
- Automatico o manual:
  - Automatico en Railway (start command).

## `polar_hrv_automation.py`
- Que hace:
  - Autenticacion/token con Polar AccessLink.
  - Calcula fechas faltantes en CORE dentro del rango objetivo.
  - Si esta habilitado, llama `egc_to_rr.py` para cubrir faltantes desde Drive (`from_jsonl`).
  - Descarga sesiones Body&Mind y extrae RR desde Polar para los faltantes restantes.
  - Guarda RR validos en `data/rr_downloads`.
  - Actualiza `ENDURANCE_HRV_sleep.csv` (y compat legacy con `ENDURANCE_HRV_context.csv`).
  - Si se usa `--process`, ejecuta `endurance_hrv.py` y `endurance_v4lite.py`.
  - Sync opcional de wellness a Intervals.
- Cuando usarlo:
  - Sync operativo principal (CLI o disparado desde web).
- Entradas:
  - Tokens, credenciales Polar, RR ya existentes, configuracion de `HRV_DATA_DIR`.
- Salidas:
  - RR descargados + actualizacion de sleep + (si `--process`) archivos CORE/BETA/FINAL/DASHBOARD.
- Automatico o manual:
  - Manual por CLI o automatico via `web_ui.py` en `/api/sync`.

## `egc_to_rr.py`
- Que hace:
  - Busca pares `ECG.jsonl` + `ACC.jsonl` en carpeta local o en Google Drive.
  - Convierte cada par a un RR compatible con la app.
  - Guarda RR con nomenclatura tipo `ENDURANCE_YYYY-MM-DD_from_jsonl_RR.CSV`.
  - Puede guardar ficheros auxiliares en subcarpeta (por defecto `_aux_jsonl`).
- Cuando usarlo:
  - Manualmente para validar conversiones.
  - Automaticamente cuando lo invoca `polar_hrv_automation.py` para cubrir fechas faltantes.
- Entradas:
  - Local: `--input-dir` o `--ecg` + `--acc`.
  - Drive: `--drive-folder-id` (si no se pasa, usa folder predefinido del script).
  - Credenciales Drive segun runtime (`local` con OAuth interactivo, `web` con credenciales no interactivas).
- Salidas:
  - RR en `data/rr_downloads`.
  - Opcional: artefactos de apoyo en `_aux_jsonl`.
- Automatico o manual:
  - Ambos.

## `endurance_hrv.py`
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

## `endurance_v4lite.py`
- Que hace:
  - Lee CORE + sleep.
  - Aplica logica de gate V4-lite (decision operativa diaria).
  - Enriquce `reason_text` con contexto de sueno y carga.
  - Si existe `ENDURANCE_HRV_sessions_day.csv`, usa sus campos de carga.
  - Genera:
    - `ENDURANCE_HRV_master_FINAL.csv`
    - `ENDURANCE_HRV_master_DASHBOARD.csv`
- Cuando usarlo:
  - Siempre que quieras pasar de CORE a salida operativa FINAL/DASHBOARD.
- Entradas:
  - `ENDURANCE_HRV_master_CORE.csv`
  - `ENDURANCE_HRV_sleep.csv` (o fallback legacy `ENDURANCE_HRV_context.csv`)
  - Opcional: `ENDURANCE_HRV_sessions_day.csv`
- Salidas:
  - FINAL y DASHBOARD.
- Automatico o manual:
  - Automatico dentro de `polar_hrv_automation.py --process`.
  - Tambien se puede correr manual.

## `build_sessions.py`
- Que hace:
  - Extrae sesiones de entrenamiento desde Intervals API.
  - Construye:
    - `ENDURANCE_HRV_sessions.csv` (detalle por sesion)
    - `ENDURANCE_HRV_sessions_day.csv` (agregado diario + rolling)
    - `metadata.json`
- Cuando usarlo:
  - Cuando quieras actualizar la capa de carga de entrenamiento.
  - Recomendado en cron separado (diario/backfill), no dentro del sync Polar.
- Entradas:
  - `INTERVALS_API_KEY`, `INTERVALS_ATHLETE_ID` y parametros (`--daily`, `--backfill`, `--date`).
- Salidas:
  - CSVs de sesiones y metadata.
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

## `build_v4_context_historical.py`
- Que hace:
  - Script historico/one-off para reconstruir contexto y salidas v4 sobre datasets antiguos.
  - Genera archivos tipo:
    - `ENDURANCE_HRV_master_FINAL_v4.csv`
    - `ENDURANCE_HRV_master_DASHBOARD_v4.csv`
    - `ENDURANCE_HRV_context.csv`
- Cuando usarlo:
  - Analisis historico, validaciones, comparativas de version.
- Entradas:
  - Fuentes historicas con rutas hardcodeadas (no pensado para Railway runtime actual).
- Salidas:
  - CSVs v4 historicos.
- Automatico o manual:
  - Manual, fuera del flujo operativo.

## 3) Resumen practico

Si tu pregunta es "que scripts importan para operar dia a dia":

1. `web_ui.py` (servidor web)
2. `polar_hrv_automation.py` (sync y orquestacion)
3. `egc_to_rr.py` (Drive/local JSONL -> RR, cuando faltan fechas o para validacion manual)
4. `endurance_hrv.py` (RR -> CORE/BETA)
5. `endurance_v4lite.py` (CORE -> FINAL/DASHBOARD)

Y aparte, opcional recomendado:

1. `build_sessions.py` para mantener al dia `sessions_day.csv` y enriquecer `reason_text` de carga.
