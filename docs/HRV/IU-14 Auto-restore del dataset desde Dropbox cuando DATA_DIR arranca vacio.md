## Objetivo

Evitar la perdida operativa del historico cuando Railway arranca con `DATA_DIR` vacio tras un redeploy o recreacion del volumen.

---

## Diagnostico

Hoy el backup existe, pero la restauracion es manual.

Si el volumen arranca vacio y se lanza antes un sync HRV o de sesiones:

- el pipeline puede regenerar solo una parte del dataset,
- al final puede subir ese estado incompleto a Dropbox,
- y el backup sano queda pisado por un historico parcial.

El problema principal no es la falta de reauth en Polar. Es permitir un sync mutante cuando falta la base de datos operativa.

---

## Abordaje mas simple

- detectar dataset vacio antes de lanzar jobs mutantes (`/api/sync`, `/api/sync-sessions` y ruta CLI principal),
- si `HRV_BACKUP_DROPBOX_ENABLED=1`, intentar `restore_backup()` automaticamente,
- si la restauracion funciona, continuar,
- si la restauracion falla, abortar el job con error claro,
- no restaurar si ya existe dataset util,
- no introducir daemons, hooks de arranque, cron ni snapshots extra.

Regla operativa recomendada:

- considerar "dataset vacio" como ausencia de `ENDURANCE_HRV_master_CORE.csv` util o `core_rows == 0`,
- usar `FINAL` solo como senal secundaria de diagnostico, no como unica condicion.

---

## Alcance propuesto

- helper pequeno reutilizable para detectar dataset vacio,
- auto-restore opt-in via flag explicita, por ejemplo `HRV_AUTO_RESTORE_ON_EMPTY_DATA=1`,
- bloqueo del sync si el restore automatico no consigue recuperar datos,
- mensaje visible en UI/logs indicando si hubo restore automatico o aborto preventivo.

---

## Limites

- no tocar logica HRV ni contratos de `docs/contracts/`,
- no cambiar el formato del backup Dropbox,
- no anadir nuevos providers de persistencia,
- no convertir esto en una orquestacion compleja de bootstrap.

---

## Criterios de aceptacion

1. Si `DATA_DIR` arranca vacio y hay backup valido en Dropbox, el sistema puede restaurarlo antes del primer sync mutante.
2. Si `DATA_DIR` arranca vacio y la restauracion automatica falla, el sync se bloquea y no pisa el backup remoto.
3. Si el dataset local ya existe, el comportamiento actual no cambia.
4. La solucion queda acotada y compatible con Railway y Python 3.11.
5. Tras un auto-restore exitoso, `/api/status` o los logs reportan que se hizo la restauracion automatica.
