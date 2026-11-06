# Procedimiento Recomendado (V4)

**Estado local (2026-11-05):** la generación de las versiones v4.18 y v4.19 de la Spec técnica (pares consecutivos y política de Calidad vigente) está publicada en `C:\Pilbond\hrv-flex\data` con CORE de 19 columnas y FINAL de 67. CORE, BETA_AUDIT, FINAL, DASHBOARD y SSM se regeneraron y verificaron por huellas; Railway no está cubierto por este corte. Las menciones posteriores a «candidata» y «pendiente de migración» describen el estado anterior al corte local.

**Artefactos del tramo (candidata v2, 03/11/2026).** CORE y FINAL añaden `rejected_rr_pct_window` junto a `Artifact_pct`. El primero es el porcentaje de RR rechazados entre todos los RR cuyo instante final está entre 90 s y el final útil inclusive. Se aplican los descartes del filtro original antes de seleccionar el tramo. Sin RR en el tramo, el porcentaje queda vacío. Calidad y los flags de artefactos usan el porcentaje local: más de 15 % impide OK y más de 20 % implica INVALID. El global sigue describiendo el registro truncado y ponderando la varianza de SSM. FINAL identifica la métrica local en el motivo de calidad cuando recibe el nuevo esquema.

**Latencia ausente en la versión candidata (03/11/2026), pendiente de migración.** CORE conserva `LAT_NAN` como diagnóstico y concede `OK` si se cumplen todos los demás requisitos. FINAL aplica su elegibilidad y acción ordinarias. SSM admite la observación con `LAT_NAN` si la fila es `OK` y mantiene ausentes los casos combinados. El manifiesto CORE registra `QUALITY_POLICY_VERSION=hg10_latnan_aviso_art_window_v2`. El sync exige que la versión coincida. Las referencias de este documento a `LAT_NAN` como causa de `FLAG_mecánico` corresponden a la política desplegada.

## Alcance operativo

Este procedimiento asume **uso personal para un único atleta**.

- La instalación, los tokens, los CSV y la sincronización pertenecen a una sola cuenta deportiva.
- No está pensado para alternar atletas, mantener varias cuentas ni ejecutar flujos paralelos por usuario.
- Si se quisiera dar soporte a varios atletas, habría que redefinir el procedimiento y la persistencia; no es un caso contemplado aquí.

## Uso diario (automático)
Ejecuta una sola vez al día:

python polar_hrv_automation.py --process

Esto hace:
- El entrypoint `polar_hrv_automation.py` coordina el caso de uso pero ya no concentra toda la logica operativa en un solo archivo; la implementacion interna vive en `hrv_app/`.
- Detecta fechas faltantes en CORE (desde `ultima_fecha_CORE + 1` hasta hoy).
- Intenta cubrir esos faltantes desde Dropbox (JSONL o ZIP -> RR) con `egc_to_rr.py` si está habilitado.
- Dropbox es la **única** fuente de nuevos RR matinales: no hay fallback Polar para fechas nuevas que Dropbox no cubra; si una fecha no está en Dropbox, esa fecha no entra al pipeline en este ciclo.
- El historico de CORE generado anteriormente con RR de Polar se conserva sin migracion retroactiva.
- Si CORE no existe y hay RR en `rr_downloads/`, reprocesa esos RR locales primero (sin Dropbox ni Polar); solo si tampoco hay RR locales recurre a Dropbox con la ventana por defecto.
- Si CORE existe pero esta vacio, es ilegible o no coincide con el esquema canonico vigente, el pipeline falla cerrado y no lo sustituye por un dataset nuevo.
- Si `HRV_AUTO_RESTORE_ON_EMPTY_DATA=1`, el flujo intenta restaurar `DATA_DIR` desde Dropbox antes de cualquier sync mutante cuando no hay un CORE usable; si el restore no deja un CORE valido, el sync se bloquea. Sin auto-restore, la recuperacion es manual.
- Actualiza `ENDURANCE_HRV_sleep.csv` mediante escritura atomica. Si el canonico existente esta vacio, es ilegible o tiene un esquema incompatible, la actualizacion se bloquea sin sobrescribirlo.
- Para el sueño Polar, el flujo prueba primero la fecha exacta y, si no hay datos, el dia anterior; el fallback existe para cubrir retrasos o desplazamientos alrededor de medianoche, no para inventar filas.
- Genera ENDURANCE_HRV_master_CORE.csv y ENDURANCE_HRV_master_BETA_AUDIT.csv.
- Genera ENDURANCE_HRV_master_FINAL.csv y ENDURANCE_HRV_master_DASHBOARD.csv.
- Regenera ENDURANCE_HRV_ssm_shadow.csv y su metadata.

**Versión publicada en este checkout local desde 2026-11-05:** `build_hrv_core.py` comprueba antes de procesar que CORE, BETA_AUDIT y su manifiesto correspondan a la geometría candidata, conserven las huellas registradas y que cada fila CORE declare esa geometría. El código actual permite conservar sin recálculo las filas de `2026-02-26`, `2026-02-27` y `2026-03-03`. Dos tienen un RR y una ninguno; ninguna tiene RMSSD utilizable. La migración acordada omite estas tres fechas. Si encuentra otras filas del histórico anterior, el sync falla cerrado para evitar mezclar definiciones en un mismo CORE. `--allow-hg10-migration` exige `--data-dir` distinto del directorio operativo y se reserva para preparar una copia aislada; no lo usa el sync web. La migración necesita además fijar un único RR por fecha y contrastarlo con el replay; la ruta automática rechaza duplicados en modo migración. Este bloqueo protegía el histórico anterior y sigue impidiendo mezclar generaciones incompatibles. Con el CORE desplegado de 18 columnas, el builder se detiene ya al leerlo (falta `rejected_rr_pct_window`) y deja una copia `.corrupt.<timestamp>`; esto también ocurre con `--allow-hg10-migration`, así que la copia de migración debe partir sin CORE previo.

Si usas la Web UI, basta con presionar "Sincronizar".

### Flags disponibles de `polar_hrv_automation.py`

| Flag | Qué hace |
|------|----------|
| `--process` | Flujo completo: cubrir fechas faltantes + CORE + FINAL + DASHBOARD + SSM |
| `--auth` | Forzar re-autenticación Polar |
| `--auto` | Detectar automáticamente días faltantes desde último registro |
| `--all` | Reprocesa RR ya existentes en `rr_downloads/` sin descargar nada nuevo |
| `--days N` | Limita la ventana de fechas a buscar a los últimos N días |
| `--ssm-audit` | Ejecuta SSM shadow + validación + outcome battery (manual, no combina con `--process`) |
| `--debug-sports` | Muestra deportes de todas las sesiones Polar de los últimos 7 días (diagnóstico) |
| `--verbose` | Muestra detalles de cada archivo procesado |

### Endpoints Web UI

| Método | Ruta | Qué hace |
|--------|------|----------|
| `GET` | `/` | Página de inicio |
| `GET` | `/auth` | Redirige a Polar OAuth |
| `GET` | `/auth/callback`, `/oauth/callback` | Intercambio code → tokens |
| `POST` | `/api/sync` | Ejecuta `polar_hrv_automation.py --process` en background |
| `POST` | `/api/sync-sessions` | Ejecuta `build_sessions.py --update` en background |
| `GET` | `/api/status` | Estado actual del job, último output e info de weekly coach |
| `POST` | `/api/import-seed` | Importa seed/artefactos auxiliares |
| `POST` | `/api/restore-backup` | Restaura archivos HRV desde el último backup en Dropbox |
| `POST` | `/api/delete-latest-rr` | Elimina el último RR ingerido |
| `GET` | `/health` | Health check (`?strict=1` para validar frescura de FINAL) |

Todos los endpoints POST comparten estado y no deben ejecutarse en paralelo. Si `HRV_UI_KEY` está definida, los `/api/*` exigen la clave vía header `X-HRV-KEY` o `?key=`.

## Variables recomendadas
Local:
- `HRV_DATA_DIR=data`
- `RR_DOWNLOAD_DIR=data/rr_downloads`

Railway (con Volume en `/data`):
- `HRV_DATA_DIR=/data`
- `RR_DOWNLOAD_DIR=/data/rr_downloads`
- `POLAR_TOKEN_PATH=/data/polar_tokens.json`
- `HRV_DROPBOX_RR_ENABLED=1`
- `HRV_DROPBOX_NO_AUX=1`
- `HRV_DROPBOX_FOLDER_PATH=/ruta/carpeta`
  - `HRV_DROPBOX_RECURSIVE=1`
  - `HRV_DROPBOX_RR_TIMEOUT_SEC=900`

## Uso manual (si necesitas rehacer o depurar)
1) Procesar RR a CORE/BETA_AUDIT:

python build_hrv_core.py --rr-dir data/rr_downloads --data-dir data

2) Generar FINAL/DASHBOARD:

python build_hrv_final_dashboard.py --data-dir data

3) (Opcional) Convertir cloud JSONL/ZIP -> RR manualmente:

python egc_to_rr.py --dropbox-folder /ruta/carpeta --dropbox-recursive --outdir data/rr_downloads

4) (Opcional) Actualizar carga de entrenamiento:

python build_sessions.py --update          # desde último día con datos hasta hoy
python build_sessions.py --backfill        # histórico completo
python build_sessions.py --daily           # últimas 48h
python build_sessions.py --date 2026-06-15 # un día concreto

5) (Opcional) Usar utilidades manuales movidas a `scripts/python/`:

- `python scripts/python/intervals_wellness_test.py ...`
- `python scripts/python/intervals_resting_hr_from_core.py ...`
- `python scripts/python/add_ans_balance_to_core.py --dry-run` (deprecated: no escribe CORE)
- `python scripts/python/build_historical_hrv_compare.py`

## Días sin sesión
Si no hay sesión en un día, el CSV simplemente no incluye esa fecha. Es normal.

## Notas operativas
- El comando principal sigue siendo: `python polar_hrv_automation.py --process`.
- Internamente, el flujo operativo vive hoy en modulos separados dentro de `hrv_app/` (`hrv_app.hrv_sync_flow`, `hrv_app.dropbox_rr`, `hrv_app.polar_client_v4`, `hrv_app.sleep_store`, `hrv_app.intervals_sync`, `hrv_app.pipeline_runner`), pero el contrato CLI no cambia.
- Para mantener la capa de carga al dia, usa `python build_sessions.py --update`.
- Para evitar guardar artefactos JSONL auxiliares en entornos web, usa `HRV_DROPBOX_NO_AUX=1`.
- Variables operativas adicionales (ver `CLAUDE.md` para lista completa):
  - `HRV_QUIET=1` — logs mínimos
  - `HRV_DISABLE_BACKUP=1` — no respaldar CSVs
  - `HRV_UI_KEY=<clave>` — protege `/api/*` con header `X-HRV-KEY` o `?key=`
  - `HRV_WARNING_MODE=adaptive90` — estrategia de warning (`adaptive90` | `healthy85` | `p20`)
- `HRV_BACKUP_DROPBOX_ENABLED=1` — backup de artefactos a Dropbox tras sync exitoso
- `HRV_AUTO_RESTORE_ON_EMPTY_DATA=1` — intenta restaurar `DATA_DIR` desde Dropbox cuando CORE falta, esta vacio o es ilegible; un restore que no deje un CORE valido bloquea el sync
- `HRV_STALE_MAX_DAYS=3` — umbral de `/health?strict=1`
- `HRV_BACKUP_DROPBOX_PATH=/hrv_backups` — carpeta de backup en Dropbox; conserva subrutas como `ai_briefs/`
- No subir a Git: `.env`, `.polar_tokens.json` ni datos personales.

## Migración desde V3 (solo histórico)

El migrador V3 ya no forma parte de este repositorio. Conserva cualquier
`ENDURANCE_HRV_master_ALL.csv` fuera del repositorio como backup privado y
reconstruye los outputs vigentes desde los RR originales.

