# Core Audit Fix 03 — Restore íntegro y fail-closed

## Objetivo

Evitar que un restore incompleto publique archivos parciales en `DATA_DIR` y
que `/api/restore-backup` lo comunique como un éxito.

Este fix protege la restauración local. No introduce generación versionada,
manifests con hashes ni un sistema propio de retención en Dropbox: para el
caso N=1 esos mecanismos no compensan todavía su complejidad. La recuperación
histórica y la capacidad del backup remoto se evaluarán por separado en CAF-07.

## Alcance

- `hrv_app/backup_dropbox.py`.
- `/api/restore-backup`.
- Auto-restore al arrancar con `DATA_DIR` vacío o ilegible.

## Implementación esperada

1. Descargar todos los archivos candidatos a un directorio temporal de
   *staging*, sin modificar `DATA_DIR`.
2. Validar antes de publicar que están presentes los canónicos obligatorios:
   `CORE`, `BETA_AUDIT`, `FINAL`, `DASHBOARD` y `sleep`.
3. Validar que los CSV obligatorios son legibles y que `CORE` contiene al
   menos una fila utilizable.
4. Publicar en `DATA_DIR` solo tras completar todas las descargas y
   validaciones. Si la publicación local falla, restaurar el snapshot previo
   de los archivos que se hubieran sustituido.
5. Ante cualquier descarga, validación o publicación fallida, limpiar el
   staging, no devolver estado `partial` como éxito y lanzar un error claro.
6. El endpoint debe responder con `success=false` si el restore no termina
   íntegramente.
7. El auto-restore no debe omitir la restauración solo porque `CORE` tenga
   filas: debe comprobar que el conjunto obligatorio es utilizable.

## Fuera de alcance

- Generaciones remotas versionadas.
- Manifest remoto, hashes criptográficos y puntero `latest`.
- Retención, rotación y capacidad de backups.
- Resolver un backup remoto que haya quedado parcialmente actualizado por un
  fallo durante la subida. Un restore de ese estado debe fallar de forma
  segura; preservarlo como generación recuperable es una mejora futura.

## Aceptación

- Un fallo a mitad de descarga no modifica ningún archivo de `DATA_DIR`.
- Si falla la publicación local, se conserva o se restaura íntegramente el
  estado previo de los archivos afectados.
- Un backup sin cualquiera de los canónicos obligatorios no se publica.
- El endpoint devuelve `success=false` para todo restore incompleto o fallido.
- El auto-restore bloquea el pipeline si, tras restaurar, el conjunto
  obligatorio no es utilizable.
- Tests de descarga fallida, canónico obligatorio ausente, validación fallida
  y fallo durante la publicación local.
