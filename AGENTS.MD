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
- documentacion historica en `docs/legacy/`,
- modulo analitico local en `analysis/`.

## 6. Snapshot actual (2026-03-17)
Estado actual de implementacion observado:

- la UI expone `/api/sync`, `/api/sync-sessions`, `/api/status` y endpoints OAuth,
- `build_sessions.py` genera `ENDURANCE_HRV_sessions.csv`, `ENDURANCE_HRV_sessions_day.csv` y `ENDURANCE_HRV_sessions_metadata.json`,
- el flujo recomendado de cobertura RR es Dropbox primero y Polar como fallback,
- `ENDURANCE_HRV_sleep.csv` es el unico archivo canonico de sueno,
- la UI no debe permitir ejecutar `sync` HRV y `sync-sessions` al mismo tiempo,
- la UI actual prioriza `Detalle tecnico` o `raw output` como bloque principal visible.

Si este bloque queda desactualizado, debe actualizarse o reducirse.

## 7. Arquitectura actual
- `web_ui.py`
  Flask + UI movil.
  Endpoints: `/`, `/auth`, `/auth/callback`, `/oauth/callback`, `/api/sync`, `/api/sync-sessions`, `/api/status`, `/health`.
  `POST /api/sync` ejecuta `polar_hrv_automation.py --process` en thread.
  `POST /api/sync-sessions` ejecuta `build_sessions.py --update` en thread.
  Ambos jobs comparten estado operativo y no deben ejecutarse en paralelo.

- `polar_hrv_automation.py`
  Orquesta el flujo principal.
  Intenta cubrir RR faltantes desde Dropbox.
  Si no es posible, usa Polar como fallback.
  Actualiza `ENDURANCE_HRV_sleep.csv`.
  Ejecuta `build_hrv_core.py` y `build_hrv_final_dashboard.py` cuando corresponde.
  Puede sincronizar wellness a Intervals.icu.

- `egc_to_rr.py`
  Convierte pares `ECG.jsonl + ACC.jsonl` a RR compatibles con la app.
  El uso recomendado actual es local o Dropbox.

- `build_hrv_core.py`
  RR -> `ENDURANCE_HRV_master_CORE.csv` y `ENDURANCE_HRV_master_BETA_AUDIT.csv`.

- `build_hrv_final_dashboard.py`
  `CORE + sleep + sessions_day` -> `ENDURANCE_HRV_master_FINAL.csv` y `ENDURANCE_HRV_master_DASHBOARD.csv`.
  La carga de entrenamiento se lee desde `ENDURANCE_HRV_sessions_day.csv`.

- `build_sessions.py`
  Pipeline de sesiones desde Intervals.icu.
  Genera `ENDURANCE_HRV_sessions.csv`, `ENDURANCE_HRV_sessions_day.csv` y `ENDURANCE_HRV_sessions_metadata.json`.
  Soporta `--backfill`, `--daily`, `--update` y `--date`.

- `Dockerfile`
  Imagen base Python 3.11-slim.

- `requirements_web.txt`
  Dependencias de la app web y del pipeline.
  Incluye `scipy`.

- `analysis/`
  Modulo local para analisis de sesiones.
  Su operativa interna esta gobernada por `analysis/AGENTS.md`.

## 8. Outputs operativos canonicos
Canonicos:

- `ENDURANCE_HRV_master_CORE.csv` (18 columnas)
- `ENDURANCE_HRV_master_BETA_AUDIT.csv` (13 columnas)
- `ENDURANCE_HRV_master_FINAL.csv` (58 columnas)
- `ENDURANCE_HRV_master_DASHBOARD.csv` (10 columnas)
- `ENDURANCE_HRV_sleep.csv` (17 columnas)

Complementarios:

- `ENDURANCE_HRV_sessions.csv`
- `ENDURANCE_HRV_sessions_day.csv`
- `ENDURANCE_HRV_sessions_metadata.json`

## 9. Defaults runtime
Defaults actuales si no hay variables:

- `HRV_DATA_DIR = data`
- `RR_DOWNLOAD_DIR = data/rr_downloads`
- `POLAR_TOKEN_PATH = .polar_tokens.json`

Por tanto, en local:

- RR nuevos y reprocesables van a `data/rr_downloads/`,
- CSV maestros, `sleep` y `sessions` se leen y escriben en `data/`.

## 10. Variables de entorno
Requeridas:

- `POLAR_CLIENT_SECRET`
- `PORT`

Requerida una de estas:

- `POLAR_CLIENT_ID`
- `POLAR_CLIENT_ID2`

Nota:

- el codigo actual da precedencia a `POLAR_CLIENT_ID2` si ambas existen.

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

Dropbox RR:

- `HRV_DROPBOX_RR_ENABLED=1`
- `HRV_DROPBOX_RR_SCRIPT=egc_to_rr.py`
- `HRV_DROPBOX_NO_AUX=1`
- `HRV_DROPBOX_PAIR_LIMIT=<N>`
- `HRV_DROPBOX_FOLDER_PATH=<dropbox_path>`
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
- `GET /health`

Regla operativa:

- `/api/sync` y `/api/sync-sessions` comparten estado de ejecucion en memoria,
- no deben ejecutarse en paralelo,
- si un job esta corriendo, el otro debe rechazarse.

## 13. Seguridad
- no commitear `.env`, `.polar_tokens.json`, RR ni CSV personales,
- no loguear tokens ni `client_secret`,
- rotar secretos si se exponen,
- no exponer tokens ni artefactos sensibles por HTTP,
- tratar `docs/legacy/` como material historico sensible.

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

## 15. Comandos operativos
Windows:

- `scripts\\run-web-ui.bat`
- `scripts\\run-python.bat`

Pipeline de sesiones:

- `python build_sessions.py --update`

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

