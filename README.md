# Polar HRV Automation (Railway V4)

Automatiza el flujo diario de HRV con Polar AccessLink y pipeline ENDURANCE V4.

## Flujo principal

Comando operativo principal:

```bash
python polar_hrv_automation.py --process
```

Este comando:

1. Calcula fechas faltantes en CORE.
2. Intenta cubrir faltantes con `egc_to_rr.py` desde cloud (Dropbox/Drive, JSONL/ZIP -> RR), si está habilitado.
3. Para fechas restantes, descarga RR desde Polar (Body&Mind).
4. Actualiza `ENDURANCE_HRV_sleep.csv`.
5. Genera/actualiza:
   - `ENDURANCE_HRV_master_CORE.csv`
   - `ENDURANCE_HRV_master_BETA_AUDIT.csv`
   - `ENDURANCE_HRV_master_FINAL.csv`
   - `ENDURANCE_HRV_master_DASHBOARD.csv`

## Web UI

```bash
python web_ui.py
```

Endpoints principales:
- `GET /auth`
- `GET /auth/callback` (alias: `/oauth/callback`)
- `POST /api/sync`
- `GET /api/status`
- `GET /health`

## Estructura de datos

- Datos operativos: `data/`
- RR crudos: `data/rr_downloads/`
- Scripts auxiliares Windows: `scripts/`
- Contratos/documentación activa: `docs/contracts/`

## Variables recomendadas (Railway)

Con Volume montado en `/data`:

- `HRV_DATA_DIR=/data`
- `RR_DOWNLOAD_DIR=/data/rr_downloads`
- `POLAR_TOKEN_PATH=/data/polar_tokens.json`
- `PUBLIC_URL=<https://tu-app.railway.app>`
- `POLAR_CLIENT_SECRET=<secret>`
- `POLAR_CLIENT_ID2=<id>` (o `POLAR_CLIENT_ID`)
- `PORT` (inyectada por Railway)

Para flujo cloud->RR (normalmente Dropbox; Drive puede quedar como fallback):

- `HRV_DRIVE_RR_ENABLED=1`
- `HRV_DRIVE_NO_AUX=1`
- `HRV_RR_CLOUD_SOURCE=dropbox|drive`
- Si `drive`:
  - `HRV_DRIVE_RUNTIME=web`
  - `HRV_DRIVE_FOLDER_ID=1ROd4GmALeNVQzwaMC48PWBH0zrAAlR-U`
- Si `dropbox`:
  - `HRV_DROPBOX_FOLDER_PATH=/ruta/carpeta`
  - `HRV_DROPBOX_RECURSIVE=1`

## Ejecución local

```bash
scripts\run-python.bat
scripts\run-web-ui.bat
python build_sessions.py --update
```

## Seguridad

No subir a Git:
- `.env`
- `.polar_tokens.json`
- `credentials.json`
- `tokens.json`
- `data/` y CSV/RR personales
