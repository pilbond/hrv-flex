# SYA-18 Endurecer API local y manifest del semanal de analysis

## Objetivo

Cerrar la deuda de diseño que ha quedado tras la integración local de `SYA-15` en el semanal de `analysis`, sin promover nada al pipeline HRV global.

El foco de esta tarea no es crear una señal nueva, sino endurecer la capa local ya existente para que el semanal tenga:

- una API pública limpia para construir sidecars sin depender de helpers internos de `sya15_continuity.py`
- un `weekly_prep_manifest.json` con contrato más explícito y versionado
- una política clara de inputs obligatorios, opcionales y sidecars degradables
- una sincronización de `report.ia.md` basada en huella suficientemente fuerte del semanal

## Contexto

Tras `SYA-15`, el semanal local de `analysis` ya dispone de:

- `build_weekly_analysis_sidecars.py`
- `run_weekly_analysis_prep.py`
- `analyze_weekly.py`
- `weekly_prep_manifest.json`
- sidecars locales `sya15_continuity_<sport>_<min>of<window>w.(md|json)`

Eso aporta valor real, pero deja varias deudas:

1. `build_weekly_analysis_sidecars.py` llama a helpers internos de `analysis/sya15_continuity.py` (`_summarize_by_sport_validated`, `_build_sport_report_validated`, `_build_report_payload_validated`), lo que convierte una optimización de validación en acoplamiento de módulo.
2. `weekly_prep_manifest.json` todavía es un manifest mínimo: no declara `schema_version`, no resume política de inputs, no identifica claramente versión del builder ni huellas de artefactos.
3. La política de degradación del semanal existe en código, pero no está formalizada como contrato corto:
   - fuentes canónicas obligatorias
   - sidecars opcionales
   - sidecars duplicados o ausentes
   - cuándo abortar y cuándo degradar
4. `report_sync_token` ya no es trivial, pero sigue siendo una huella lógica de parámetros y rutas; puede convenir decidir si debe seguir así o pasar a una huella de contenido.

## Alcance propuesto

### 1. API pública del sidecar semanal

Definir una API pública única en `analysis/sya15_continuity.py` o módulo adyacente para construir el sidecar de `SYA-15`, por ejemplo:

- `build_weekly_sidecar(...)`
- o `build_sya15_package(...)`

La meta es que `build_weekly_analysis_sidecars.py` deje de depender de helpers internos con `_`.

### 2. Contrato del manifest semanal

Endurecer `weekly_prep_manifest.json` con, como mínimo:

- `schema_version`
- `generated_at`
- `builder`
- `inputs`
- `sidecars`
- política explícita o implícita de obligatoriedad/degradación

No hace falta convertirlo en contrato global del sistema; sigue siendo contrato local de `analysis`.

### 3. Política explícita de inputs

Documentar y, si hace falta, codificar una tabla clara:

- inputs canónicos obligatorios
- inputs canónicos opcionales
- sidecars opcionales
- sidecars que degradan con aviso
- sidecars cuya ausencia obliga a regenerar prep

### 4. Sincronización del informe semanal

Revisar si `report_sync_token` debe quedarse como huella de:

- semana
- manifest
- parámetros y rutas de sidecars

o si merece pasar a una huella más fuerte basada en contenido real.

La tarea no obliga a hashear todos los artefactos si el coste no compensa, pero sí a dejar una decisión explícita y defendible.

## Fuera de alcance

- tocar `sessions.csv`, `sessions_day.csv`, `FINAL` o `DASHBOARD`
- incorporar `SYA-15` al gate HRV o a `reason_text`
- promover `SYA-15` a contrato global o sidecar operativo canónico
- rehacer la narrativa del semanal como producto final interpretativo

## Criterios de aceptación

1. `build_weekly_analysis_sidecars.py` deja de depender de helpers internos con prefijo `_` de `sya15_continuity.py`, o queda documentada y encapsulada una excepción explícita si no se puede evitar con coste razonable.
2. `weekly_prep_manifest.json` tiene `schema_version` y contrato local documentado.
3. Existe documentación corta y clara de inputs obligatorios/opcionales y reglas de degradación del semanal.
4. El contrato de sincronización de `report.ia.md` queda explicitado y alineado con el token realmente generado.
5. La suite cubre al menos:
   - manifest versionado
   - API pública del sidecar
   - política de degradación o aborto para inputs ausentes

## Destino natural

Tarea local de `analysis`.

No debe cambiar:

- contratos HRV de `docs/contracts/`
- outputs canónicos del pipeline
- despliegue Railway

Su salida natural es dejar el semanal local más estable, más legible y menos acoplado internamente.
