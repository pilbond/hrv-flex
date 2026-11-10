# Core Audit Fix 06 — Gate de coherencia de manifest en consumidor

## Objetivo

Detectar y rechazar en la UI una combinación incoherente de
CORE/BETA_AUDIT/FINAL/DASHBOARD (p. ej. un CORE de la generación N+1 con un FINAL de la
generación N cuando un sync falla a mitad).

Detección en **lectura** con fallo cerrado, sin protocolo de publicación
transaccional. Alcance N=1: la opción más sencilla y eficaz.

El gate cubre la UI web (`/` y `/api/status`). Los consumidores que leen los
canónicos fuera de la UI —`hrv_app/cli_reporting.py`, `analysis/*`,
`build_hrv_ssm*`— siguen leyendo por ruta sin verificar; son herramientas de
lectura manual y quedan fuera de CAF-06.

## Contexto

La trazabilidad por etapa **ya existe** (IU-13):

- `build_hrv_core.py` escribe `ENDURANCE_HRV_master_CORE_manifest.json` con hashes
  de inputs (RR), outputs (CORE/BETA sha256), filas/columnas y `effective_config_hash`.
- `build_hrv_final_dashboard.py` escribe `ENDURANCE_HRV_master_FINAL_manifest.json`
  y ya enlaza con el manifest de CORE (`source_manifest_path`,
  `source_manifest_sha256`, `source_manifest_effective_config_hash`).
- Cada archivo se escribe atómicamente de forma individual (`hrv_app/run_manifest.py` + `io_utils`).

El builder ya escribe el manifest FINAL al final y registra los hashes de FINAL
y DASHBOARD (IU-13). Esta tarea hace que el consumidor **valide y rechace**
generaciones incoherentes.

## Alcance

Tres puntos acotados:

1. **Cierre existente en el builder.** `ENDURANCE_HRV_master_FINAL_manifest.json`
   ya se escribe después de CORE, BETA, FINAL, DASHBOARD y sidecars, y registra
   los `sha256` de `FINAL.csv` y `DASHBOARD.csv`. No requiere otro cambio.

2. **Gate de coherencia en el consumidor.** Helper `verify_generation_coherence()`
   usado al leer FINAL/DASHBOARD (`/api/status` y carga del gate) que comprueba:
   - existen, son JSON legible y tienen la estructura mínima necesaria
     `FINAL_manifest.json` y `CORE_manifest.json`;
   - el linaje coincide: `source_manifest_sha256` /
     `source_manifest_effective_config_hash` del FINAL manifest concuerdan con el
     CORE manifest actual en disco;
   - los `sha256` de `CORE.csv` y `BETA_AUDIT.csv` en disco coinciden con las
     firmas `role=core` y `role=beta_audit` del CORE manifest actual;
   - los `sha256` de `FINAL.csv` y `DASHBOARD.csv` en disco coinciden con los
     registrados en el FINAL manifest.
   - Si algo no cuadra → la verificación produce el código estable
     `generation_incoherent`; la carga del gate se detiene antes de leer CSV y
     no sirve datos silenciosamente.

   La verificación se ejecuta antes de construir los diagnósticos. Los builders
   publican cada archivo mediante rename atómico y el flujo web serializa sus
   jobs; no se conserva una copia de los CSV en memoria.

   Un directorio sin ninguno de los cuatro CSV ni los dos manifests de generación
   conserva el estado habitual de «sin datos». Un manifest huérfano ya cuenta
   como conjunto parcial. En la UI, `GET /api/status`
   comunica cualquier conjunto parcial o incoherente con HTTP `503`,
   `success=false` y diagnósticos `generation_coherent=false` y
   `generation_error.code=generation_incoherent`, con motivo registrado en el
   log y visible en el estado de ejecución. La vista se construye sin datos
   HRV/gate. La portada que carga
   ese mismo estado aplica el mismo gate. `GET /health` conserva su contrato
   actual de liveness/staleness y no pasa a formar parte de CAF-06.

3. **Restore coherente.** El backup de Dropbox incluye los manifests que haya
   en `DATA_DIR`. El restore valida en staging los CSV obligatorios y la
   generación completa antes de publicar; si el backup carece de manifests o
   mezcla archivos de distintas corridas, falla sin sustituir datos operativos.
   El auto-restore comprueba la coherencia del volumen existente solo para
   reportarla: si sus CSV están presentes y utilizables pero sus manifests
   faltan o no cuadran, **no** restaura nada (ver más abajo).

### Archivos afectados

- `web_ui.py` (gate antes de las lecturas de CORE/FINAL/DASHBOARD que alimentan
  la UI y `/api/status`, respuesta 503 e importación seed con validación previa
  y posterior a la publicación, con rollback en caso de fallo).
- `hrv_app/run_manifest.py` (helper de verificación).
- `hrv_app/backup_dropbox.py` (verificación del backup en staging antes del
  restore; el backup omite subir una generación incoherente; el auto-restore
  reporta la coherencia del volumen existente pero no se dispara por ella).
- `polar_hrv_automation.py` (un backup omitido por incoherencia degrada el
  resultado del sync en vez de pasar por bueno).

### Qué no hace el gate en las rutas de escritura

`auto_restore_if_empty()` sigue decidiendo «vacío» por el conjunto obligatorio
(archivo ausente, ilegible o CORE sin filas con fecha válida). Un dataset
completo cuyos manifests no cuadran **no** dispara el restore: publicar el
backup encima sobrescribiría un histórico utilizable sin saber cuál de los dos
es más reciente. Ese estado se avisa por log y se devuelve en
`generation_coherent`; bloquearlo es tarea del gate de lectura (`/api/status`) y
de la puerta HG-10 de `build_hrv_core.py`, que ya fallan cerrado.

Lo que sí hace falta cerrar en escritura es el **backup**: un sync sin RR nuevos
regenera FINAL/DASHBOARD sin pasar por `build_hrv_core.py`, así que la huella de
CORE no se vuelve a comprobar y HG-10 no interviene. Si ese sync termina bien,
`run_backup()` subiría encima del backup remoto una generación que el propio
restore rechazaría. Por eso `run_backup()` verifica la coherencia antes de subir
y devuelve `status="incoherent_generation"` sin tocar el remoto, y el
orquestador degrada el resultado del sync.

## Fuera de alcance (explícito)

- Staging/swap transaccional todo-o-nada entre archivos.
- Puntero de generación, directorios versionados o ledger prospectivo.
- Migración retroactiva de generaciones históricas sin manifest.
- Cualquier otra ruta de escritura del dataset (`/api/delete-latest-rr`,
  builders). CAF-06 termina en el gate de lectura, la importación seed, la
  validación del restore y la del backup; ampliarlo a otra ruta es una tarea
  aparte.

Si en el futuro hace falta publicación transaccional, será una tarea aparte.

## Dependencias

- CAF-01, CAF-02 (completadas).
- **Coordinar con CAF-03** (en revisión): el restore exige los cinco CSV
  obligatorios y comprueba hashes y linaje en staging antes de publicar.
  Un backup sin ambos manifests o con archivos mezclados se rechaza sin tocar
  los datos operativos. La recuperación de backups históricos sin manifests
  requiere un procedimiento manual separado; el sync web no puede regenerarlos
  porque HG-10 exige el manifest CORE existente.

## Aceptación

1. Con generación coherente en disco, `/api/status` sirve con normalidad y la
   UI puede mostrar el gate.
2. Manifest ausente o ilegible, `sha256` de CORE/BETA_AUDIT/FINAL/DASHBOARD que no cuadra,
   o linaje CORE↔FINAL desalineado → `/api/status` responde `503`, informa el
   error de generación junto con el estado técnico previo y la UI no sirve el gate.
3. Tests unitarios del helper con fixtures para: coherente, manifest ausente e
   ilegible, conjunto parcial, hashes alterados y linaje CORE↔FINAL desalineado.
4. Tests de UI para el caso coherente y el incoherente: el primero conserva la
   respuesta normal; el segundo devuelve `503`, informa el motivo y no muestra
   el gate.
5. La importación seed exige los cuatro CSV de generación y ambos manifests,
   con hashes y linaje coherentes, antes de publicarlos. El restore exige los
   cinco CSV obligatorios (incluido sueño), ambos manifests y una generación
   coherente en staging; un backup antiguo sin manifests falla antes de publicar.
6. El auto-restore no sobrescribe un dataset utilizable por un desajuste de
   manifests: lo reporta y deja que fallen cerrado el gate de lectura y HG-10.
7. `run_backup()` no sube una generación incoherente: devuelve
   `incoherent_generation`, no toca el backup remoto y el sync queda degradado.
8. Ante el `503`, el panel técnico encabeza con el motivo de incoherencia y
   conserva debajo la salida de la última ejecución.
