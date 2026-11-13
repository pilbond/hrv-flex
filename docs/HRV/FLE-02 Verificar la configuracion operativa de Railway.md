# FLE-02 — Verificar acceso, token y backup en Railway

## Descripción

La configuración efectiva del despliegue determina si los datos y las operaciones están expuestos, si el token Polar sobrevive a un redeploy y si local y Railway comparten destino de backup. La auditoría identifica el riesgo por código y por información del propietario. Falta verificar el entorno efectivo.

## Desarrollo

1. Comprobar el control de acceso efectivo y la protección de la API en Railway. Verificar el rechazo de peticiones sin credenciales mediante un endpoint de lectura. Coordinar la protección de portada y OAuth con CAF-04.
2. Comprobar el montaje y las rutas efectivas de datos, RR y token. Configurar `POLAR_TOKEN_PATH_V4` en el volumen y comprobar persistencia durante un redeploy autorizado. Documentar la variable vigente y alinear los scripts operativos que todavía usan la variable v3.
3. Asignar un destino Dropbox por entorno y decidir cuál será la fuente de recuperación de cada uno. Comprobar el destino mediante configuración y metadatos de la copia, sin usar una restauración sobre datos operativos.
4. Registrar qué configuración de build y arranque se aplica. Llevar a CAF-05 la comprobación de que los procesos descendientes terminan antes de liberar el candado tras un timeout. CAF-03, CAF-06 y CAF-07 cubren restauración, coherencia de generaciones y retención.

## Aceptación

- El despliegue rechaza el acceso anónimo a la API y quedan documentadas las rutas que cubre la protección instalada.
- El token y los datos persisten en el volumen. Cada entorno escribe en su destino Dropbox.
- Quedan registradas las comprobaciones pendientes del despliegue y sus tareas responsables, sin exponer credenciales ni rutas sensibles de acceso.

Referencias. Hallazgos 4, 7, 8 y 9. [[CORE_AUDIT_FIX_04_OWNER_AUTH|CAF-04]] · [[CORE_AUDIT_FIX_05_RAILWAY_WSGI|CAF-05]] · [[CORE_AUDIT_FIX_03_RESTORE_GENERATION|CAF-03]].

## Estado (2026-11-12)

Resuelto por configuración en Railway, comprobado por el atleta con un redeploy sin restaurar ni reautorizar:

- **Volumen.** Existía, montado en `/data` (500 MB). La app no podía escribir en él: el `Dockerfile` ejecuta con `USER app` y Railway monta el volumen como root. `hrv_app/config.py:78-82,160` pasaba sin aviso a `/app/data`, efímero; `/api/status` mostraba `core_path=/app/data/...`. Corregido con `RAILWAY_RUN_UID=0` ([documentación de Railway](https://docs.railway.com/volumes)).
- **Token.** Solo existía `POLAR_TOKEN_PATH` (variable v3, sin uso en el runtime). El token v4 iba a `.polar_tokens_v4.json` en el directorio de trabajo. Corregido con `POLAR_TOKEN_PATH_V4=/data/polar_tokens_v4.json`.
- **RR.** Sin hallazgo confirmado. Una nota anterior atribuía a `RR_DOWNLOAD_DIR` una comilla literal; el atleta indica que no modificó ninguna variable por ese motivo y no consta que se verificara en Railway: era una suposición, descartada como causa del fallo de persistencia (la causa fue `RAILWAY_RUN_UID`). Debe comprobarse el valor efectivo de `RR_DOWNLOAD_DIR` en Railway.
- **Documentación operativa** actualizada con estos requisitos (`AGENTS.MD`, `CLAUDE.md`, `README.md`, `PROCEDIMIENTO_RECOMENDADO.md`, `scripts/run-web-ui.bat`).

Pendiente:

1. **Acceso.** `HRV_UI_KEY` no está definida en Railway: `/api/*` es anónimo en la URL pública. Definirla y comprobar que `/api/status` sin clave devuelve 401. Punto 1 de Desarrollo; prioridad alta.
2. **Código.** Resuelto localmente: en producción, los datos, RR y token no pasan silenciosamente a una carpeta de fallback si no admiten escritura; el arranque falla de forma explícita. Railway exige configurar los tres destinos dentro del volumen `/data`. Con `HRV_UI_KEY`, la portada ya no inserta datos personales en el HTML previo al acceso; la UI deja de sondear la API mientras está bloqueada. Pendiente de confirmar el comportamiento en Railway tras desplegar.
3. **Build/arranque.** El repositorio declara Dockerfile y `railway.json` declara NIXPACKS, mientras que la nota de estado anterior afirma que Railway usa Dockerfile. Falta comprobar el builder efectivo en el servicio y alinear la configuración del repositorio con esa evidencia; no cambiarlo por suposición.
4. **Backup por entorno.** El atleta confirmó que `/hrv_backups` es el destino deseado; el valor por defecto lo selecciona sin definir `HRV_BACKUP_DROPBOX_PATH`. Sigue pendiente comprobar el destino efectivo y metadatos del backup de Railway, sin restaurar datos operativos.
5. **Aceptación.** El criterio «el token y los datos persisten en el volumen» se cumple según el redeploy confirmado por el atleta. Quedan las comprobaciones remotas indicadas arriba.

6. **Límite conocido del control de rutas.** El arranque en Railway comprueba que `HRV_DATA_DIR`, `RR_DOWNLOAD_DIR` y `POLAR_TOKEN_PATH_V4` apuntan léxicamente dentro de `/data` y que son escribibles, pero no que `/data` sea el volumen montado. `_dir_is_writable` crea el directorio si falta y, con `RAILWAY_RUN_UID=0`, un `/data` sin volumen se crea dentro del contenedor, es escribible y pasa las comprobaciones, con datos efímeros. Verificarlo exigiría `os.path.ismount('/data')` y una prueba en Railway; no se añade porque, si el volumen no figurara como punto de montaje, el servicio no arrancaría. La comprobación vigente es `/api/status`: `core_path`, `final_path`, `token_path` y `rr_download_dir` deben empezar por `/data/` y los datos deben sobrevivir a un redeploy.
