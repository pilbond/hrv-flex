## Estado

Implementado (2026-06-14). Este documento es la fuente final y cerrada de
F4. Cambios:

- `hrv_app/hrv_sync_flow.py::sync_hrv_range` ya no descarga ni filtra
  ejercicios Polar como fuente de RR; auto/`--days N` cubren
  `target_missing_dates` solo via `_run_dropbox_rr_import_for_dates`, sin
  fallback Polar.
- `--all` reprocesa solo RR ya presentes en disco
  (`_scan_rr_files_by_date`), sin descargar nada nuevo ni cubrir huecos.
- `polar_hrv_automation.py` solo llama a `list_exercises` bajo
  `--debug-sports`; el flujo normal de RR no depende de Polar.
- Tests: `tests/test_hrv_sync_flow_contract.py`,
  `tests/test_polar_hrv_automation_cli.py`.
- Correcciones de fechas ya existentes en `CORE` quedan fuera de alcance
  (ver "Decisiones explicitas" del plan de implementacion).

## Objetivo

Cerrar `AYO-13-F4` con una definicion operativa simple: Dropbox pasa a ser la
unica fuente para incorporar nuevos RR matinales al pipeline HRV, sin borrar ni
reescribir el historico ya existente.

## Diagnostico

La formulacion inicial de F4 como "validacion PPI vs Dropbox RR" servia para
explorar si PPI v4 podia sustituir o complementar el RR matinal. Tras la
discusion y la evidencia disponible, la decision de producto queda mas simple:

- los nuevos RR matinales entran solo desde Dropbox;
- no hay fallback Polar para fechas nuevas que Dropbox no cubra;
- el historico previo de `CORE` generado con RR de Polar se conserva sin
  migracion retroactiva;
- el flujo automatico debe seguir siendo pequeno y predecible para un proyecto
  N=1.

## Alcance

- retirar Polar como fuente de nuevos RR matinales en el flujo HRV operativo;
- mantener `sleep` y `nightly recharge` via Polar como hasta ahora;
- documentar que la regla aplica solo a incorporaciones nuevas, no al historico
  ya persistido;
- dejar un comportamiento simple para `auto`, `--days` y `--all`;
- mantener fuera de `build_hrv_core.py` cualquier uso de PPI mientras no exista
  validacion especifica posterior.

## Comportamiento esperado

### 1. Sync automatico

- leer la ultima fecha ya presente en `CORE`;
- buscar desde `ultima_fecha_CORE + 1` hasta hoy;
- importar RR solo desde Dropbox;
- si una fecha no esta en Dropbox, esa fecha no entra al pipeline;
- no reabrir automaticamente fechas antiguas ni huecos intermedios.

Razon:
- es el comportamiento mas eficiente para el caso N=1;
- evita reintentos repetitivos y conversiones masivas innecesarias;
- mantiene un criterio facil de explicar y de operar.

### 2. Historico de CORE

- conservar todas las filas existentes, incluidas las construidas
  historicamente con RR de Polar;
- no borrar ni reprocesar ese historico durante un sync normal;
- la regla "Dropbox es la unica fuente" aplica a partir de F4 en adelante, no
  como migracion retroactiva.

### 3. `--days N`

- usar `--days N` para buscar fechas ausentes en un rango manual hacia atras;
- sirve como via de backfill o rescate manual;
- no debe convertirse en logica automatica de reintento continuo.

Interpretacion:
- `auto` cubre solo fechas nuevas;
- `--days N` cubre recuperacion manual de fechas ausentes o tardias.

### 4. `--all`

- reprocesar unicamente los RR ya descargados localmente;
- no descargar nada nuevo;
- no intentar cubrir huecos;
- servir solo para recalculo masivo sobre el material ya presente en disco.

### 5. Fechas nuevas para un dia ya existente

Si aparece un RR nuevo para una fecha que ya existe en `CORE`, no debe
esperarse que el modo automatico la detecte. Ese caso se trata como correccion
manual y se resuelve mediante un reprocesado explicito del periodo
correspondiente.

## No objetivos

- no introducir una ventana automatica de reintento de 7 dias;
- no crear manifests, ledgers ni gobernanza extra para importacion RR;
- no resolver en esta tarea la idempotencia historica completa de `egc_to_rr.py`;
- no usar PPI v4 como entrada de `build_hrv_core.py`;
- no cambiar el gate HRV, esquemas de columnas ni contratos fisiologicos;
- no tocar `research/` si su trabajo queda bien encapsulado y sin efecto sobre
  el codigo principal.

## Decisiones explicitas

1. Dropbox es la unica fuente de nuevos RR matinales.
2. Polar deja de ser fallback para fechas nuevas ausentes en Dropbox.
3. El historico Polar ya persistido en `CORE` se conserva.
4. `auto` sigue un criterio simple: desde la ultima fecha conocida hacia hoy.
5. `--days N` es la herramienta manual de recuperacion hacia atras.
6. `--all` reprocesa local, no descarga.

## Riesgos aceptados

- si una fecha ya existe en `CORE` y aparece despues un RR nuevo para esa misma
  fecha, el modo automatico no la sustituira por si solo;
- las correcciones tardias requeriran una accion manual sobre el periodo;
- la idempotencia del conversor Dropbox RR sigue siendo deuda tecnica previa,
  pero no debe resolverse aqui con mas logica automatica alrededor.

## Criterios de aceptacion

1. El modo automatico nunca solicita fechas anteriores a la ultima fila de
   `CORE`.
2. Los nuevos RR procesados por el flujo HRV vienen solo de Dropbox.
3. Si Dropbox no cubre una fecha nueva, esa fecha no entra en `CORE`.
4. Las filas historicas de `CORE` generadas con RR de Polar se conservan sin
   borrado ni migracion retroactiva.
5. `--days N` permite recuperar manualmente fechas ausentes hacia atras.
6. `--all` solo reprocesa RR ya presentes localmente y no descarga nada.
7. La eliminacion del fallback Polar no rompe `sleep`, `nightly recharge`,
   CLI, UI ni builders posteriores.

## Regression Gate

- test del modo automatico usando `ultima_fecha_CORE + 1` como inicio;
- test de ausencia de fallback Polar para nuevos RR;
- test de conservacion del historico ya existente en `CORE`;
- test de `--days N` como ruta manual de backfill;
- test de `--all` sin descarga nueva;
- smoke test del entrypoint `polar_hrv_automation.py` usado por la UI.

## Nota de desarrollo

Este documento sustituye la lectura anterior de `AYO-20` como posible
"validacion PPI para decidir fallback". La validacion PPI, si se quiere
mantener, queda como investigacion o auditoria separada. La tarea de producto
que se cierra aqui es la politica operativa de fuentes RR del pipeline HRV.
