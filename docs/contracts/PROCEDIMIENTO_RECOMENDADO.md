# Procedimiento Recomendado (V4)

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
- Detecta fechas faltantes en CORE.
- Intenta cubrir primero esos faltantes desde Dropbox (JSONL o ZIP -> RR) con `egc_to_rr.py` si está habilitado.
- Trata Dropbox como fuente principal esperada de RR matinales.
- Solo para faltantes restantes, usa Polar como fallback.
- Actualiza `ENDURANCE_HRV_sleep.csv`.
- Para el sueño Polar, el flujo prueba primero la fecha exacta y, si no hay datos, el dia anterior; el fallback existe para cubrir retrasos o desplazamientos alrededor de medianoche, no para inventar filas.
- Genera ENDURANCE_HRV_master_CORE.csv y ENDURANCE_HRV_master_BETA_AUDIT.csv.
- Genera ENDURANCE_HRV_master_FINAL.csv y ENDURANCE_HRV_master_DASHBOARD.csv.
- Regenera ENDURANCE_HRV_ssm_shadow.csv y su metadata.

Si usas la Web UI, basta con presionar "Sincronizar".

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

python build_sessions.py --update

5) (Opcional) Usar utilidades manuales movidas a `scripts/python/`:

- `python scripts/python/intervals_wellness_test.py ...`
- `python scripts/python/intervals_resting_hr_from_core.py ...`
- `python scripts/python/add_ans_balance_to_core.py ...`
- `python scripts/python/build_historical_hrv_compare.py`

## Días sin sesión
Si no hay sesión en un día, el CSV simplemente no incluye esa fecha. Es normal.

## Notas operativas
- El comando principal sigue siendo: `python polar_hrv_automation.py --process`.
- Internamente, el flujo operativo vive hoy en modulos separados dentro de `hrv_app/` (`hrv_app.hrv_sync_flow`, `hrv_app.dropbox_rr`, `hrv_app.polar_client`, `hrv_app.sleep_store`, `hrv_app.intervals_sync`, `hrv_app.pipeline_runner`), pero el contrato CLI no cambia.
- Para mantener la capa de carga al dia, usa `python build_sessions.py --update`.
- Para evitar guardar artefactos JSONL auxiliares en entornos web, usa `HRV_DROPBOX_NO_AUX=1`.
- No subir a Git: `.env`, `.polar_tokens.json` ni datos personales.

## Migración desde V3 (solo histórico)

El migrador V3 ya no forma parte de este repositorio. Conserva cualquier
`ENDURANCE_HRV_master_ALL.csv` fuera del repositorio como backup privado y
reconstruye los outputs vigentes desde los RR originales.

