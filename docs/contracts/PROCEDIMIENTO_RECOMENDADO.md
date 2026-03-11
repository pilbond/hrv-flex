# Procedimiento Recomendado (V4)

## Uso diario (automático)
Ejecuta una sola vez al día:

python polar_hrv_automation.py --process

Esto hace:
- Detecta fechas faltantes en CORE.
- Intenta cubrir faltantes desde cloud (Dropbox/Drive, JSONL o ZIP -> RR) con `egc_to_rr.py` si está habilitado.
- Para faltantes restantes, descarga RR desde Polar.
- Actualiza `ENDURANCE_HRV_sleep.csv`.
- Genera ENDURANCE_HRV_master_CORE.csv y ENDURANCE_HRV_master_BETA_AUDIT.csv.
- Genera ENDURANCE_HRV_master_FINAL.csv y ENDURANCE_HRV_master_DASHBOARD.csv.

Si usas la Web UI, basta con presionar "Sincronizar".

## Variables recomendadas
Local:
- `HRV_DATA_DIR=data`
- `RR_DOWNLOAD_DIR=data/rr_downloads`

Railway (con Volume en `/data`):
- `HRV_DATA_DIR=/data`
- `RR_DOWNLOAD_DIR=/data/rr_downloads`
- `POLAR_TOKEN_PATH=/data/polar_tokens.json`
- `HRV_DRIVE_RR_ENABLED=1`
- `HRV_RR_CLOUD_SOURCE=dropbox|drive`
- Si `drive`:
  - `HRV_DRIVE_RUNTIME=web`
  - `HRV_DRIVE_FOLDER_ID=1ROd4GmALeNVQzwaMC48PWBH0zrAAlR-U`
- Si `dropbox`:
  - `HRV_DROPBOX_FOLDER_PATH=/ruta/carpeta`
  - `HRV_DROPBOX_RECURSIVE=1`

## Uso manual (si necesitas rehacer o depurar)
1) Procesar RR a CORE/BETA_AUDIT:

python endurance_hrv.py --rr-dir data/rr_downloads --data-dir data

2) Generar gate V4-lite:

python endurance_v4lite.py --data-dir data

3) (Opcional) Convertir cloud JSONL/ZIP -> RR manualmente:

python egc_to_rr.py --drive-runtime local --drive-recursive --outdir data/rr_downloads
python egc_to_rr.py --dropbox-folder /ruta/carpeta --dropbox-recursive --outdir data/rr_downloads

4) (Opcional) Actualizar carga de entrenamiento:

python build_sessions.py --update

## Días sin sesión
Si no hay sesión en un día, el CSV simplemente no incluye esa fecha. Es normal.

## Notas operativas
- El comando principal sigue siendo: `python polar_hrv_automation.py --process`.
- Para mantener la capa de carga al dia, usa `python build_sessions.py --update`.
- Para evitar guardar artefactos JSONL auxiliares en entornos web, usa `HRV_DRIVE_NO_AUX=1`.
- No subir a Git: `.env`, `credentials.json`, `tokens.json`, `.polar_tokens.json`, ni datos personales.

## Migración desde V3 (solo histórico)
python __endurance_migrate.py --master-all ENDURANCE_HRV_master_ALL.csv
