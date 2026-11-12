# Core Audit Fix 07 — Retención del backup local de CORE y BETA_AUDIT

> **Reencuadre (2026-11-12).** El volumen de Railway en `/data` existe (500 MB) y,
> con `RAILWAY_RUN_UID=0`, persiste entre redeploys (comprobado por el atleta el
> 2026-11-11). La premisa del reencuadre de julio («`/data` se borra en cada
> redeploy») era un síntoma: la app no podía escribir en el volumen y usaba
> `/app/data`. Con el volumen operativo, las copias locales se acumulan sin límite.
> Se descarta retirarlas: son la única copia de versiones anteriores, porque el
> backup de Dropbox sobrescribe. El objetivo pasa a ser **conservar solo las
> últimas N copias**. Prioridad media: al ritmo actual el volumen tardaría años en
> llenarse.

> **Reencuadre (2026-07-17), superado.** Proponía retirar el backup local por
> considerar efímero el volumen. Esa premisa resultó falsa (ver arriba).

## Objetivo

Acotar el espacio que ocupan las copias locales sin perder la vuelta atrás
manual de las últimas ejecuciones.

## Contexto

- `build_hrv_core.py:1217-1234` copia `CORE_backup_{ts}.csv` y
  `BETA_AUDIT_backup_{ts}.csv` a `DATA_DIR/backup/` justo antes de sobrescribir
  los canónicos. Guardan el estado anterior a cada ejecución. Activo por
  defecto; `HRV_DISABLE_BACKUP` lo desactiva.
- La medición inicial encontró 111 copias de cada tipo y 57 MB. En la inspección
  del 2026-11-12 había 6 copias de cada tipo y unos 2 MB en CSV (20 MB contando
  las subcarpetas). Cada par ronda 360 KB; con un sync diario son unos 130 MB al
  año en un volumen de 500 MB.
- El backup de Dropbox (`hrv_app/backup_dropbox.py`) sobrescribe cada fichero:
  conserva una sola versión. Si una ejecución publica un CORE que pasa las
  comprobaciones pero es incorrecto, se sube y pisa el anterior. Las copias
  locales son entonces el único sitio con la versión previa. El historial de
  versiones propio de Dropbox no se ha verificado para el plan del atleta y no
  se cuenta con él.
- Limitaciones conocidas de las copias locales: están en el mismo volumen que
  los originales, solo cubren CORE y BETA_AUDIT (no una generación completa con
  manifests) y la recuperación es manual.

## Alcance

- `build_hrv_core.py`: tras crear las copias, borrar las más antiguas y conservar
  las últimas N de cada tipo.
- Una variable de configuración para N con valor por defecto (p. ej. 10).
- Documentación operativa que describa el backup local.

## Fuera de alcance

- El backup y restore a Dropbox, y el auto-restore.
- `DATA_DIR/backup/pre_restore/` que crea `restore_backup()`.
- `DATA_DIR/backup/deleted_rr/` del borrado del último RR.
- Convertir las copias locales en generaciones completas restaurables.

## Implementación esperada

1. Reservar una plaza por tipo para la copia recién creada. Las plazas
   restantes se asignan a las copias con nombre fechado (`YYYYMMDD_HHMMSS`)
   más recientes por nombre. Las copias con otros nombres quedan fuera de la poda.
2. `HRV_CORE_BACKUP_RETENTION` vale 30 por defecto. Los valores inválidos,
   incluidos los negativos, se avisan y usan 30. `0` o `HRV_DISABLE_BACKUP=1`
   desactivan la copia y la poda.
3. Si falla la inspección de las copias, se avisa y se omite la poda de ese
   tipo. Si falla el borrado de una copia antigua, se avisa y se sigue con
   las demás. En ambos casos el core continúa.
4. Documentar el comportamiento y la variable en `AGENTS.MD`, `CLAUDE.md` y la
   guía de scripts.

## Aceptación

- Tras varias ejecuciones quedan como máximo N copias de cada tipo, las más
  recientes.
- Con más de N copias previas (caso actual), la primera ejecución poda las
  sobrantes.
- La copia previa a la ejecución en curso siempre se conserva.
- El resto del pipeline (escritura atómica, manifests, backup Dropbox,
  auto-restore) no cambia.
- Tests de la poda (orden, límite, fallos al inspeccionar o borrar) y documentación coherente.

## Notas / seguimiento

- **Resuelto (2026-11-11):** el riesgo de perder el token tras cada redeploy no
  se debía a la falta de volumen, sino a los permisos de escritura sobre él y a
  que faltaba `POLAR_TOKEN_PATH_V4`. Corregido por configuración.
