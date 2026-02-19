# AGENTS.md — Polar HRV Automation (Railway) V4

## Objetivo del proyecto
Sistema automatizado de monitoreo HRV que:
- Autentica con Polar AccessLink (OAuth2 Authorization Code).
- Descarga RR de sesiones Body&Mind.
- Procesa RR con Endurance V4 (endurance_hrv.py) para generar CORE/BETA_AUDIT.
- Calcula gate V4-lite (endurance_v4lite.py) para FINAL/DASHBOARD.
- Expone UI web (Flask) y endpoints de sincronización.
- Despliega en Railway.

## Arquitectura (actual)
- web_ui.py: Flask + UI móvil + endpoints /auth, /auth/callback, /api/sync, /api/status.
- polar_hrv_automation.py: descarga/sync + ejecución de pipeline V4.
- endurance_hrv.py: RR -> ENDURANCE_HRV_master_CORE.csv y ENDURANCE_HRV_master_BETA_AUDIT.csv.
- endurance_v4lite.py: CORE -> ENDURANCE_HRV_master_FINAL.csv y ENDURANCE_HRV_master_DASHBOARD.csv.
- __endurance_migrate.py: migración V3 -> V4-lite (opcional).
- Dockerfile: Python 3.11-slim.
- requirements_web.txt: dependencias.

## Archivos de salida
- ENDURANCE_HRV_master_CORE.csv (canónico, 12 cols).
- ENDURANCE_HRV_master_BETA_AUDIT.csv (legacy V3, 13 cols).
- ENDURANCE_HRV_master_FINAL.csv (gate V4-lite + auditoría, 34 cols).
- ENDURANCE_HRV_master_DASHBOARD.csv (vista operativa, 9 cols).

## Principio clave (producción)
Debe existir un único flujo OAuth web en Railway.
Está prohibido en producción:
- abrir navegador desde backend
- usar HTTPServer local para callback

## Variables de entorno
Requeridas:
- POLAR_CLIENT_ID
- POLAR_CLIENT_SECRET
- PUBLIC_URL
- PORT

Recomendadas:
- POLAR_TOKEN_PATH (ej. /data/polar_tokens.json)
- HRV_DATA_DIR
- RR_DOWNLOAD_DIR
- INTERVALS_API_KEY, INTERVALS_ATHLETE_ID (si se usa sync a intervals.icu)

## Persistencia: Railway Volume
- Montar volumen en /data
- POLAR_TOKEN_PATH=/data/polar_tokens.json
- Escribir tokens de forma atómica y nunca exponerlos por HTTP

## OAuth (flujo esperado)
1) Usuario abre GET /auth
2) Backend redirige a Polar con redirect_uri=${PUBLIC_URL}/auth/callback
3) Polar redirige a /auth/callback?code=...
4) Backend intercambia code por tokens y registra usuario
5) Tokens se guardan en POLAR_TOKEN_PATH

## Endpoints (contrato)
- GET / -> UI
- GET /auth -> inicia OAuth
- GET /auth/callback -> completa OAuth
- POST /api/sync -> descarga RR + ejecuta V4 (CORE/BETA_AUDIT/FINAL/DASHBOARD)
- GET /api/status -> estado
- GET /health -> healthcheck

## Seguridad (no negociable)
- No commitear .env, .polar_tokens.json, RR ni CSV personales.
- No loguear tokens ni client_secret.
- Si un secreto se filtra, rotarlo.

## Criterios de aceptación
1) /auth devuelve 302 a Polar con redirect_uri correcto.
2) /auth/callback guarda tokens en POLAR_TOKEN_PATH.
3) POST /api/sync genera CORE/BETA_AUDIT/FINAL/DASHBOARD.
4) Tras redeploy, /api/sync sigue funcionando (si hay Volume).
5) Logs útiles sin secretos.

## Estilo de cambios
- Cambios mínimos, compatibilidad Python 3.11.
- Evitar dependencias nuevas si no aportan valor claro.
