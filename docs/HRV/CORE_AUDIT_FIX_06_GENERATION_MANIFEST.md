# Core Audit Fix 06 — Gate de coherencia de manifest en consumidor

## Objetivo

Garantizar que la UI y los consumidores operativos nunca sirvan una combinación
incoherente de CORE/FINAL/DASHBOARD (p. ej. un CORE de la generación N+1 con un
FINAL de la generación N cuando un sync falla a mitad).

Detección en **lectura** con fallo cerrado, sin protocolo de publicación
transaccional. Alcance N=1: la opción más sencilla y eficaz.

## Contexto

La trazabilidad por etapa **ya existe** (IU-13):

- `build_hrv_core.py` escribe `ENDURANCE_HRV_master_CORE_manifest.json` con hashes
  de inputs (RR), outputs (CORE/BETA sha256), filas/columnas y `effective_config_hash`.
- `build_hrv_final_dashboard.py` escribe `ENDURANCE_HRV_master_FINAL_manifest.json`
  y ya enlaza con el manifest de CORE (`source_manifest_path`,
  `source_manifest_sha256`, `source_manifest_effective_config_hash`).
- Cada archivo se escribe atómicamente de forma individual (`hrv_app/run_manifest.py` + `io_utils`).

Lo que falta y cubre esta tarea: (a) sellar el cierre de generación y (b) que el
consumidor **valide y rechace** generaciones incoherentes.

## Alcance

Dos cambios acotados:

1. **Commit-marker en el builder.** `ENDURANCE_HRV_master_FINAL_manifest.json` se
   escribe el último de la generación (después de CORE, BETA, FINAL, DASHBOARD y
   sidecars) y registra los `sha256` de `FINAL.csv` **y** `DASHBOARD.csv`.

2. **Gate de coherencia en el consumidor.** Helper `verify_generation_coherence()`
   usado al leer FINAL/DASHBOARD (`/api/status` y carga del gate) que comprueba:
   - existen `FINAL_manifest.json` y `CORE_manifest.json`;
   - el linaje coincide: `source_manifest_sha256` /
     `source_manifest_effective_config_hash` del FINAL manifest concuerdan con el
     CORE manifest actual en disco;
   - los `sha256` de `FINAL.csv` y `DASHBOARD.csv` en disco coinciden con los
     registrados en el FINAL manifest.
   - Si algo no cuadra → estado de error explícito (coherente con CAF-01/CAF-02);
     no servir datos silenciosamente.

### Archivos afectados

- `build_hrv_final_dashboard.py` (orden de escritura + sha256 de DASHBOARD).
- `web_ui.py` (gate en lecturas de FINAL/DASHBOARD).
- `hrv_app/run_manifest.py` (helper de verificación, si procede ubicarlo aquí).

## Fuera de alcance (explícito)

- Staging/swap transaccional todo-o-nada entre archivos.
- Puntero de generación, directorios versionados o ledger prospectivo.
- Migración retroactiva de generaciones históricas sin manifest.

Si en el futuro hace falta publicación transaccional, será una tarea aparte.

## Dependencias

- CAF-01, CAF-02 (completadas).
- **Coordinar con CAF-03** (en curso): CAF-03 restaura "por generación completa"
  sin hashes; tras CAF-06 el restore debería dejar un conjunto que pase
  `verify_generation_coherence()`. Anotar como nota; no bloquea.

## Aceptación

1. Con generación coherente en disco, `/api/status` sirve con normalidad.
2. Manifest FINAL ausente, o `sha256` de FINAL/DASHBOARD/CORE que no cuadra, o
   linaje CORE↔FINAL desalineado → la UI reporta error y no sirve el gate.
3. Test unitario del helper con 4 fixtures: coherente, manifest ausente, hash de
   output alterado, linaje CORE↔FINAL desalineado.
