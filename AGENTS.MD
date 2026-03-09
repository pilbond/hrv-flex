# AGENTS.md — Polar HRV Automation (Railway) V4

## Objetivo del proyecto
Sistema automatizado de monitoreo HRV que:
- Autentica con Polar AccessLink (OAuth2 Authorization Code).
- Descarga RR de sesiones Body&Mind.
- Opcionalmente genera RR válidos desde `ECG.jsonl + ACC.jsonl` en Google Drive.
- Procesa RR con Endurance V4 (`endurance_hrv.py`) para generar CORE/BETA_AUDIT.
- Calcula gate V4-lite (`endurance_v4lite.py`) para FINAL/DASHBOARD.
- Expone UI web (Flask) y endpoints de sincronización.
- Puede sincronizar wellness a Intervals.icu (opcional).
- Despliega en Railway.

## Estado actual (2026-03)
Cambios estructurales ya aplicados:
- Datos operativos en `data/` (no en raíz).
- RR crudos en `data/rr_downloads/`.
- Archivo de contexto renombrado a `ENDURANCE_HRV_sleep.csv`.
- Compatibilidad backward: el código todavía puede leer `ENDURANCE_HRV_context.csv` legacy si existe.
- Scripts `.bat` movidos a `scripts/`.
- Documentación en `docs/contracts/`.
- Documentación legacy en `docs/legacy/` (ignorada y tratada como sensible).

## Arquitectura (actual)
- `web_ui.py`:
  - Flask + UI móvil.
  - Endpoints: `/`, `/auth`, `/auth/callback`, `/oauth/callback`, `/api/sync`, `/api/status`, `/health`.
  - `POST /api/sync` ejecuta `polar_hrv_automation.py --process` en thread.
- `polar_hrv_automation.py`:
  - Descarga/sync RR desde Polar.
  - Para fechas faltantes de CORE, intenta primero importar RR desde Drive vía `egc_to_rr.py`.
  - Actualiza sueño/recharge en `ENDURANCE_HRV_sleep.csv`.
  - Ejecuta pipeline V4 (`endurance_hrv.py` + `endurance_v4lite.py`) cuando corresponde.
  - Sync opcional de wellness a Intervals.icu (PUT del último día).
- `egc_to_rr.py`:
  - Lee pares `ECG.jsonl + ACC.jsonl` (local o Google Drive).
  - Convierte a RR en formato compatible con la app (`ENDURANCE_YYYY-MM-DD_from_jsonl_RR.CSV`).
  - Puede guardar artefactos auxiliares en subcarpeta (`_aux_jsonl`).
- `endurance_hrv.py`:
  - RR -> `ENDURANCE_HRV_master_CORE.csv` y `ENDURANCE_HRV_master_BETA_AUDIT.csv`.
- `endurance_v4lite.py`:
  - CORE + sleep + `sessions_day` -> `ENDURANCE_HRV_master_FINAL.csv` y `ENDURANCE_HRV_master_DASHBOARD.csv`.
  - La carga de entrenamiento se lee desde `ENDURANCE_HRV_sessions_day.csv` (no desde sleep).
- `build_sessions.py`:
  - Pipeline de sesiones desde Intervals.icu.
  - Genera `ENDURANCE_HRV_sessions.csv`, `ENDURANCE_HRV_sessions_day.csv`, `metadata.json`.
- `Dockerfile`: Python 3.11-slim.
- `requirements_web.txt`: dependencias.
  - Incluye `scipy` y librerías Google Drive (`google-auth*`, `google-api-python-client`).

## Estructura de carpetas
- `data/`:
  - CSV operativos actuales (CORE/BETA_AUDIT/FINAL/DASHBOARD/sleep/sessions*).
  - `rr_downloads/` para RR crudos.
  - `backup/` para backups automáticos.
- `scripts/`:
  - `run-python.bat` (ejecuta sync + process).
  - `run-web-ui.bat` (levanta la UI).
- `docs/contracts/`:
  - Especificación funcional y técnica activa.
- `docs/legacy/`:
  - Documentación histórica/legacy (potencialmente sensible).

## Archivos de salida operativos
Canónicos:
- `ENDURANCE_HRV_master_CORE.csv` (12 cols).
- `ENDURANCE_HRV_master_BETA_AUDIT.csv` (13 cols, legacy V3).
- `ENDURANCE_HRV_master_FINAL.csv` (53 cols).
- `ENDURANCE_HRV_master_DASHBOARD.csv` (10 cols).
- `ENDURANCE_HRV_sleep.csv` (17 cols: sueño/recharge + percentiles derivados).

Complementarios:
- `ENDURANCE_HRV_sessions.csv` (detalle por sesión, Intervals).
- `ENDURANCE_HRV_sessions_day.csv` (agregado diario de carga/sesiones).
- `metadata.json` (pipeline de sesiones).

## Directorios y defaults runtime
Defaults actuales si no hay variables:
- `HRV_DATA_DIR = data`
- `RR_DOWNLOAD_DIR = data/rr_downloads`
- `POLAR_TOKEN_PATH = .polar_tokens.json`

Por tanto, en local:
- RR nuevos y reprocesables van a `data/rr_downloads/`.
- CSV maestros/sleep/sessions se leen/escriben en `data/`.

## Principio clave (producción)
Debe existir un único flujo OAuth web en Railway.
Está prohibido en producción:
- abrir navegador desde backend
- usar HTTPServer local para callback

## Variables de entorno
Requeridas:
- `POLAR_CLIENT_SECRET`
- `PORT`

Requeridas (una de estas dos):
- `POLAR_CLIENT_ID2` o `POLAR_CLIENT_ID`

Muy recomendadas:
- `PUBLIC_URL` (evita redirects ambiguos en OAuth)
- `POLAR_TOKEN_PATH` (ej. `/data/polar_tokens.json`)
- `HRV_DATA_DIR` (ej. `/data`)
- `RR_DOWNLOAD_DIR` (ej. `/data/rr_downloads`)
- `INTERVALS_API_KEY`, `INTERVALS_ATHLETE_ID` (si se usa integración Intervals)

Opcionales operativas:
- `HRV_QUIET=1` para salida mínima.
- `HRV_DISABLE_BACKUP=1` para evitar backups en ejecuciones web.
- `HRV_SYNC_TIMEOUT_SEC` para timeout de `POST /api/sync`.

Opcionales Drive (flujo RR desde JSONL):
- `HRV_DRIVE_RR_ENABLED=1` (default true).
- `HRV_DRIVE_RR_SCRIPT=egc_to_rr.py`.
- `HRV_DRIVE_RUNTIME=auto|local|web`.
- `HRV_DRIVE_FOLDER_ID=<folder_id>`.
- `HRV_DRIVE_RECURSIVE=1`.
- `HRV_DRIVE_NO_AUX=1` para no guardar artefactos auxiliares.
- `HRV_DRIVE_PAIR_LIMIT=<N>` para pruebas.

Credenciales Google Drive:
- Local interactivo: `credentials.json` + `tokens.json`.
- Web/Railway recomendado: `GOOGLE_APPLICATION_CREDENTIALS` apuntando a Service Account JSON.

## Persistencia: Railway Volume
Configuración recomendada:
- Montar volumen en `/data`.
- `POLAR_TOKEN_PATH=/data/polar_tokens.json`
- `HRV_DATA_DIR=/data`
- `RR_DOWNLOAD_DIR=/data/rr_downloads`

Reglas:
- Escribir tokens de forma atómica.
- No exponer tokens por HTTP.

## OAuth (flujo esperado)
1) Usuario abre `GET /auth`.
2) Backend redirige a Polar con `redirect_uri=${PUBLIC_URL}/auth/callback`.
3) Polar redirige a `/auth/callback?code=...` (o alias `/oauth/callback`).
4) Backend intercambia code por tokens y registra usuario AccessLink.
5) Tokens se guardan en `POLAR_TOKEN_PATH`.

## Endpoints (contrato)
- `GET /` -> UI.
- `GET /auth` -> inicia OAuth.
- `GET /auth/callback` -> completa OAuth.
- `GET /oauth/callback` -> alias compatible.
- `POST /api/sync` -> descarga RR + actualiza sleep + ejecuta V4 (CORE/BETA_AUDIT/FINAL/DASHBOARD).
- `GET /api/status` -> estado + diagnósticos.
- `GET /health` -> healthcheck.

## Seguridad (no negociable)
- No commitear `.env`, `.polar_tokens.json`, RR ni CSV personales.
- No loguear tokens ni `client_secret`.
- Si un secreto se filtra, rotarlo.
- `docs/legacy/` se considera material sensible histórico (evitar publicación abierta).

## Criterios de aceptación
1) `/auth` devuelve 302 a Polar con `redirect_uri` correcto.
2) `/auth/callback` guarda tokens en `POLAR_TOKEN_PATH`.
3) `POST /api/sync` genera/actualiza CORE/BETA_AUDIT/sleep/FINAL/DASHBOARD.
4) Tras redeploy, `/api/sync` sigue funcionando si hay Volume.
5) Logs útiles sin secretos.
6) RR se almacenan y leen desde `data/rr_downloads/`.
7) Si faltan fechas en CORE y Drive está habilitado, se intenta `Drive -> RR from_jsonl` antes del fallback Polar.

## Comandos operativos
- Web UI local:
  - `scripts\run-web-ui.bat`
- Sync+process local:
  - `scripts\run-python.bat`
- Pipeline de sesiones Intervals:
  - `python build_sessions.py --output data`
- Conversión manual Drive -> RR (debug/local):
  - `python egc_to_rr.py --drive-runtime local --drive-recursive --outdir data/rr_downloads`

## Estilo de cambios
- Cambios mínimos, compatibilidad Python 3.11.
- Evitar dependencias nuevas si no aportan valor claro.
- Mantener compatibilidad con datos legacy cuando sea barato (ej. fallback de `ENDURANCE_HRV_context.csv`).

