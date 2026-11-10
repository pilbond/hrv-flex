# FLE-01 — Aislar las pruebas de restauración

## Descripción

La prueba de autorización de `/api/restore-backup` puede llegar a Dropbox y publicar datos sobre el directorio operativo si el entorno local tiene credenciales. La auditoría documenta dos restauraciones accidentales durante la suite. Prioridad inmediata.

## Desarrollo

1. Sustituir `hrv_app.backup_dropbox.restore_backup` en la prueba de autorización. Comprobar que la petición denegada no lo invoca y que la autorizada lo invoca una vez y devuelve el resultado esperado.
2. Comprobar las demás pruebas de restauración y auto-restore. Usar directorios temporales y respuestas simuladas en la frontera externa.
3. Verificar la prueba aislada antes de repetir la suite en un entorno con configuración local. CAF-03 lleva el snapshot previo y la restauración íntegra del runtime.

## Aceptación

- La autorización devuelve 401 sin invocar el restore y 200 con el resultado simulado para una clave válida.
- Las pruebas afectadas funcionan con o sin configuración Dropbox y dejan intactos los datos operativos.

Referencia. `tests/test_web_ui_security.py:372` y hallazgo 1 de la auditoría.
