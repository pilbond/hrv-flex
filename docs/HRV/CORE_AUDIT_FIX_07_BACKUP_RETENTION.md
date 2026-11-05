# Core Audit Fix 07 — Retirar backup local redundante

> **Reencuadre (2026-07-17).** La definición original asumía un volumen `/data`
> persistente y finito que el backup local podía llegar a llenar. La realidad
> operativa es otra: `/data` **se borra en cada redeploy** y el histórico se
> reconstruye desde Dropbox (auto-restore IU-14). Por tanto los snapshots
> locales `data/backup/CORE_backup_*` **no aportan durabilidad** (se pierden con
> el volumen) y **no pueden causar crecimiento indefinido** (el volumen se
> resetea en cada redeploy). El objetivo pasa de "retención/pruning" a
> "eliminar un mecanismo redundante".

## Objetivo

Retirar el backup local dated de `build_hrv_core.py` por ser redundante: no
protege contra la pérdida real (el volumen efímero) y añade escrituras y código
sin valor operativo. La protección durable ya es Dropbox + auto-restore.

## Contexto

- Único mecanismo de crecimiento local: `build_hrv_core.py:940-948` copia
  `CORE_backup_{ts}.csv` y `BETA_AUDIT_backup_{ts}.csv` a `data/backup/` en cada
  ejecución del core (activo por defecto; `HRV_DISABLE_BACKUP` es opt-out).
- `build_hrv_final_dashboard.py` **no** genera backups (las entradas
  `FINAL_backup_*` / `DASHBOARD_backup_*` del `.gitignore` son legacy).
- El backup a Dropbox (`hrv_app/backup_dropbox.py`) es **overwrite** y vive
  fuera del volumen; no tiene problema de crecimiento y queda fuera de alcance.
- La protección contra "una generación nueva mala pisa un CORE bueno" ya está
  cubierta por CAF-01 (fail-closed de canónicos), CAF-02 (propagación de estado
  del pipeline) y CAF-03 (restore/backup por generación completa).

## Alcance

- `build_hrv_core.py`: bloque de backup local (`data/backup/CORE_backup_*`,
  `BETA_AUDIT_backup_*`).
- Documentación asociada (`AGENTS.md`, `CLAUDE.md`, contratos) si mencionan el
  backup local como garantía.

## Fuera de alcance

- El backup/restore a Dropbox y el auto-restore (se mantienen; son la
  durabilidad real).
- `data/backup/pre_restore/` que crea `restore_backup()` (snapshot transitorio
  previo a una restauración; no crece de forma no acotada).
- La política de re-autenticación tras redeploy y la posible falta de un Volume
  persistente en Railway → **problema separado**, mayor que CAF-07 (ver Notas).

## Implementación esperada

1. Eliminar el bloque de backup local dated de `build_hrv_core.py`.
2. Retirar o neutralizar `HRV_DISABLE_BACKUP` si queda sin uso (o documentar que
   ya no aplica).
3. Ajustar la documentación que describa el backup local como salvaguarda.

## Aceptación

- El core deja de escribir `data/backup/CORE_backup_*` / `BETA_AUDIT_backup_*`.
- El resto del pipeline (escritura atómica canónica, manifests, Dropbox backup,
  auto-restore) sigue funcionando sin cambios.
- Tests actualizados si alguno dependía del backup local.
- Documentación coherente: la durabilidad se describe apoyada en Dropbox +
  auto-restore, no en copias same-volume.

## Notas / seguimiento

- **Riesgo mayor detectado, fuera de esta tarjeta:** si `/data` se borra en cada
  redeploy, `polar_tokens.json` (que vive en `/data` y **no** se respalda en
  Dropbox — `backup_dropbox.py` solo sube `ENDURANCE_HRV_*`) también se pierde,
  lo que implicaría re-autenticar OAuth Polar tras cada despliegue. Conviene una
  tarjeta aparte para: (a) confirmar si debería existir un Railway Volume
  persistente en `/data`, y (b) si no, incluir los tokens en el
  backup/restore Dropbox. No abordar dentro de CAF-07.
