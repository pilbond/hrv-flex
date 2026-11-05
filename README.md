# Polar HRV Automation

Aplicación personal para procesar la variabilidad de la frecuencia cardiaca (HRV) de un atleta. Combina RR matinales, sueño y sesiones de entrenamiento para generar un histórico diario, una vista de decisión y una interfaz web. Se puede ejecutar en local o en un servidor.

## Cómo funciona

1. Busca fechas nuevas que aún no figuran en el histórico HRV.
2. Obtiene pares `ECG.jsonl` y `ACC.jsonl` de Dropbox y los convierte a RR. Dropbox es la única fuente de RR matinales nuevos: si falta una fecha allí, se espera a otro ciclo. El histórico existente se conserva.
3. Actualiza el sueño mediante Polar AccessLink y procesa los RR con `build_hrv_core.py`.
4. Combina CORE, sueño y contexto de entrenamiento en `build_hrv_final_dashboard.py`.
5. Regenera la estimación SSM en sombra. La validación ampliada de SSM se ejecuta aparte, bajo demanda.
6. Puede sincronizar wellness con Intervals.icu y guardar una copia de los resultados en Dropbox.

El sistema es para un solo atleta. Los contratos de cálculo, calidad y decisión están en [docs/contracts/](docs/contracts/); el README describe la operación general.

## Componentes

| Ruta | Función |
| --- | --- |
| `web_ui.py` | Interfaz Flask, OAuth web, estado y acciones de sincronización. |
| `polar_hrv_automation.py` y `hrv_app/` | Orquestación, integraciones y lógica operativa del sync HRV. |
| `egc_to_rr.py` | Conversión de ECG y ACC a RR, con diagnósticos de procedencia. |
| `build_hrv_core.py` | Generación de CORE y BETA_AUDIT a partir de RR. |
| `build_hrv_final_dashboard.py` | Generación de FINAL y DASHBOARD. |
| `build_hrv_ssm.py` | Estimación SSM en sombra. |
| `build_sessions.py` | Sesiones y contexto de carga desde Intervals.icu. |
| `analysis/` | Informes locales de sesiones y semanas; no modifica los canónicos HRV. |
| `research/` | Experimentos y auditorías que no forman parte del runtime. |
| `scripts/` | Lanzadores y herramientas operativas locales. |

Los datos operativos están en `data/` por defecto. Los RR reprocesables se guardan en `data/rr_downloads/`; sus motivos de descarte y manifiestos viven en `data/rr_downloads/_rr_diagnostics/`. Los briefs IA fechados, cuando se generan, se guardan en `data/ai_briefs/`.

## Preparación local

Se recomienda Python 3.11, la versión de la imagen de despliegue y de CI. En Windows, `scripts\setup-windows.bat` crea o reutiliza `.venv`, instala `requirements_web.txt`, crea `data/` y `data/rr_downloads/` y comprueba las dependencias mínimas. Manualmente, desde la raíz del repositorio en PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements_web.txt
Copy-Item env.example .env
```

Configura las variables de entorno necesarias antes de arrancar. El código carga automáticamente un `.env` en la raíz (vía `python-dotenv`); parte de `env.example` y no incorpores `.env` a Git. Para OAuth de Polar se necesitan `POLAR_CLIENT_SECRET` y `POLAR_CLIENT_ID` o `POLAR_CLIENT_ID2`. Si están definidos ambos identificadores, el código da prioridad a `POLAR_CLIENT_ID2`.

Para importar RR nuevos desde Dropbox configura:

- `HRV_DROPBOX_FOLDER_PATH`: carpeta que contiene los pares ECG/ACC.
- `DROPBOX_ACCESS_TOKEN`, o bien `DROPBOX_REFRESH_TOKEN`, `DROPBOX_APP_KEY` y `DROPBOX_APP_SECRET`.
- `HRV_DROPBOX_RR_ENABLED=1` si se había desactivado la importación.

`PUBLIC_URL` fija la URL pública utilizada en el callback OAuth. En local, la UI usa el puerto `8080` salvo que se defina `PORT`. Las rutas por defecto son `HRV_DATA_DIR=data`, `RR_DOWNLOAD_DIR=data/rr_downloads` y `POLAR_TOKEN_PATH=.polar_tokens.json`.

Para usar la integración de sesiones y wellness con Intervals.icu, configura `INTERVALS_API_KEY` e `INTERVALS_ATHLETE_ID`.

## Ejecución

En Windows, los lanzadores usan `.venv\Scripts\python.exe` si existe:

| Lanzador | Qué hace |
| --- | --- |
| `scripts\run-web-ui.bat` | Arranca la UI en `PORT` (8080 por defecto) con backup Dropbox activado. |
| `scripts\run-hrv.bat` | Ejecuta `polar_hrv_automation.py --process`. |
| `scripts\run-build-sessions.bat` | Ejecuta `build_sessions.py --update`, o los argumentos que se le pasen. |
| `scripts\run-ssm-audit.bat` | Ejecuta la auditoría SSM manual (`--ssm-audit`). |

También se pueden ejecutar los programas directamente:

```powershell
.\.venv\Scripts\python.exe web_ui.py
.\.venv\Scripts\python.exe polar_hrv_automation.py --process
.\.venv\Scripts\python.exe build_sessions.py --update
```

La UI estará en `http://localhost:8080` con el puerto por defecto. Registra en tu aplicación Polar la URL de retorno de la UI (`http://localhost:8080/auth/callback` con la configuración local por defecto) y abre `/auth` para conectar la cuenta. Acciones de la UI y sus endpoints:

| Acción | Endpoint | Disponibilidad |
| --- | --- | --- |
| Sync HRV | `POST /api/sync` | Siempre. |
| Sync de sesiones | `POST /api/sync-sessions` | Siempre; requiere credenciales de Intervals.icu. |
| Borrar el último RR ingerido | `POST /api/delete-latest-rr` | Si hay algún RR en disco; pide confirmación. |
| Importar CSV desde `seed_upload/` | `POST /api/import-seed` | Visible si existe la carpeta (`HRV_SEED_UPLOAD_DIR`) o con `HRV_SHOW_SEED_IMPORT=1`. |
| Restaurar backup | `POST /api/restore-backup` | Visible con `HRV_BACKUP_DROPBOX_ENABLED=1`. |

`GET /api/status` devuelve el estado actual. Las operaciones `POST` comparten un bloqueo: si una está en curso, las demás se rechazan con `409`. Ese bloqueo no cubre la línea de comandos, así que evita lanzar scripts sobre los mismos datos mientras la UI trabaja.

Opciones útiles de línea de comandos:

- `polar_hrv_automation.py --all --process`: reprocesa los RR ya presentes en disco sin descargar RR nuevos.
- `polar_hrv_automation.py --ssm-audit`: ejecuta la auditoría SSM ampliada (shadow, validación y batería de outcomes) bajo demanda; no se combina con otras opciones.
- `polar_hrv_automation.py --debug-sports`: diagnóstico de los deportes de las sesiones Polar.
- `build_sessions.py --backfill`, `--daily`, `--update` o `--date`: seleccionan el rango de sesiones.
- `build_hrv_final_dashboard.py`: recalcula FINAL y DASHBOARD a partir de las entradas existentes.

## Datos generados

Los archivos principales de `HRV_DATA_DIR` son:

| Archivo | Contenido |
| --- | --- |
| `ENDURANCE_HRV_master_CORE.csv` | Métricas HRV procesadas por fecha. |
| `ENDURANCE_HRV_master_BETA_AUDIT.csv` | Auditoría de la medición RR. |
| `ENDURANCE_HRV_sleep.csv` | Histórico canónico de sueño. |
| `ENDURANCE_HRV_master_FINAL.csv` | Métricas, calidad, contexto y decisión diaria. |
| `ENDURANCE_HRV_master_DASHBOARD.csv` | Vista resumida para la UI. |
| `ENDURANCE_HRV_ssm_shadow.csv` | Estimación SSM exploratoria. |

`build_sessions.py` genera `ENDURANCE_HRV_sessions.csv`, `ENDURANCE_HRV_sessions_day.csv`, la distribución semanal de intensidad, el resumen semanal, los metadatos de auditoría y el wellness subjetivo. CORE y FINAL tienen manifiestos JSON que registran procedencia y huellas de sus resultados.

El procesamiento comprueba la compatibilidad del esquema y de la generación del histórico antes de escribir. Si los datos existentes pertenecen a una generación incompatible, se detiene para evitar mezclar definiciones. Consulta [docs/contracts/](docs/contracts/) antes de reconstruir o sustituir un histórico.

## Backup y restauración

Con `HRV_BACKUP_DROPBOX_ENABLED=1`, un sync HRV exitoso copia a Dropbox los archivos `ENDURANCE_HRV_*.csv` y `ENDURANCE_HRV_*.json` de la raíz de `HRV_DATA_DIR`, junto con los briefs fechados de `ai_briefs/`. La carpeta remota por defecto es `/hrv_backups`; puede cambiarse con `HRV_BACKUP_DROPBOX_PATH`. El lanzador `scripts\run-web-ui.bat` activa esta opción para su proceso.

Cada archivo remoto se sobrescribe conservando su ruta relativa. Este backup incluye resultados e historial IA, pero no los RR, sus diagnósticos ni los tokens OAuth; conserva esas entradas por separado si necesitas reconstruir el histórico.

La restauración se inicia desde la UI o `POST /api/restore-backup`. Antes de reemplazar archivos locales existentes, guarda una copia en `data/backup/pre_restore/` o la ruta equivalente bajo `HRV_DATA_DIR`. `HRV_AUTO_RESTORE_ON_EMPTY_DATA=1` permite restaurar al iniciar el sync cuando CORE falta, está vacío o no se puede leer. Comprueba que el backup remoto corresponde a la misma generación del código antes de restaurarlo.

## Ejecución en servidor

La aplicación arranca con `python web_ui.py`. El repositorio incluye un Dockerfile con Python 3.11. Para conservar datos y OAuth entre despliegues, monta un volumen en `/data` y configura:

```text
HRV_DATA_DIR=/data
RR_DOWNLOAD_DIR=/data/rr_downloads
POLAR_TOKEN_PATH=/data/polar_tokens.json
PUBLIC_URL=https://<dominio-publico>
```

Añade los secretos de Polar y Dropbox como variables del servicio. Configura `PORT` si necesitas un puerto distinto de `8080`. El flujo OAuth es web: `/auth` redirige a Polar y `/auth/callback` recibe la respuesta. `/health` comprueba que el proceso responde; `/health?strict=1` también comprueba la frescura de FINAL según `HRV_STALE_MAX_DAYS`.

Si defines `HRV_UI_KEY`, las rutas `/api/*` requieren la clave mediante el header `X-HRV-KEY` o el parámetro `key`. No expongas esa clave, los tokens ni los archivos personales.

## Briefs IA opcionales

La aplicación puede generar explicaciones diarias y de SSM mediante un proveedor compatible con OpenAI. Requieren `HRV_AI_ENABLED=1` y, respectivamente, `HRV_AI_DAILY_ENABLED=1` o `HRV_AI_SSM_ENABLED=1`, además de la configuración del proveedor. Si la generación falla o el texto no supera la validación, la UI utiliza su explicación determinista. Las métricas y decisiones se calculan en el pipeline; el texto IA es una capa de presentación.

## Pruebas y documentación

```powershell
.\.venv\Scripts\python.exe -m pip install pytest pytest-subtests
.\.venv\Scripts\python.exe -m pytest tests/ -q
```

- [AGENTS.MD](AGENTS.MD): reglas operativas, rutas, variables y despliegue.
- [docs/contracts/](docs/contracts/): contratos HRV vigentes.
- [analysis/AGENTS.md](analysis/AGENTS.md): reglas del módulo de análisis.
- [research/AGENTS.md](research/AGENTS.md): reglas de investigación.

No incorpores a Git `.env`, tokens, RR, CSV personales ni el contenido de `data/`.
