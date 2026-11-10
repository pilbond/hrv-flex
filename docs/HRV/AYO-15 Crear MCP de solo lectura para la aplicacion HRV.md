## Estado

Propuesta. Revisada el 2026-11-09 contra el estado actual del repositorio.
Plan de ejecución: [[Plan AYO-15 — MCP solo lectura HRV (plan de desarrollo)]].

## Decisión

Crear un servidor MCP **local**, por `stdio` y de **solo lectura**, sobre los
artefactos ya generados en `data/`. Su función es dar a los agentes locales
(Claude Code, Codex u otro host MCP) consultas tipadas y acotadas sobre el
estado HRV, en lugar de que cada agente lea y reinterprete varios CSV y JSON.

No ejecuta sincronizaciones, no modifica outputs canónicos, no llama a Polar,
Dropbox ni Intervals, no necesita credenciales y no se despliega en Railway.

## Qué aporta y qué no

En local un agente ya puede leer los ficheros, así que el MCP **no da acceso
nuevo**. Su valor está en:

- **Consulta por fecha ya resuelta.** `ENDURANCE_HRV_master_FINAL_reason_items.json`
  ocupa ~765 KB y FINAL tiene 66 columnas; la pregunta habitual ("¿cuál era el
  estado en esta fecha y con qué confianza?") solo necesita una fila y sus
  items.
- **Semántica fijada en un único sitio.** Precedencia de fuentes, separación
  entre gate y contexto, sueño de la noche correcta y carga con desfase
  explícito se resuelven una vez en Python, no en el prompt de cada cliente.
- **Respuestas con calidad y procedencia.** Cada respuesta declara fuentes,
  frescura y estado (`complete`, `partial`, `not_found`, `stale`).
- **Privacidad por elección de fuente.** El MVP solo usa artefactos sin RR,
  GPS, streams ni texto libre.

Si en la práctica casi no se consulta el estado HRV desde un agente, el
beneficio es pequeño. La tarea debe mantenerse pequeña para que el coste sea
proporcional.

## Estado del repositorio que condiciona el diseño

1. **La procedencia ya existe.** `ENDURANCE_HRV_master_CORE_manifest.json` y
   `ENDURANCE_HRV_master_FINAL_manifest.json` traen `generated_at`, hashes
   `sha256`, conteos y `effective_config_hash`. El MCP solo los lee.
2. **La explicación del gate ya está estructurada.** `reason_items.json`
   (`schema_version` 1.0, `items_by_date`) tipa cada item por `type`, `layer`,
   `source`, `metric`, `value`, `threshold` y `gate_scope`.
3. **El payload del estado diario ya existe.** `hrv_app/ai/daily_brief.py`
   (`_build_payload` y auxiliares) monta un payload con `decision`,
   `reason_items`, `morning_hrv`, `sleep_context` (solo si el sueño es de la
   noche correcta) y `recent_load_summary` (con fecha y desfase de la carga).
   Es casi entero el futuro `hrv_get_daily_status`. **No debe reimplementarse:**
   hay que extraer la parte determinista a un módulo compartido que usen tanto
   el brief como el MCP.
4. **Ese payload no se puede reenviar tal cual.** `meta.data_sources` contiene
   rutas absolutas (`/app/data/...` en Railway) y `interpretation_contract` /
   `expected_output` son instrucciones para el LLM del brief, no datos.
5. **`hrv_app/config.py` tiene efectos laterales al importarse**
   (`_load_local_env()`, `mkdir` y prueba de escritura). La capa compartida
   debe recibir rutas como parámetros y no importar `hrv_app.config` ni
   `hrv_app.ai.config`.
6. **El `data/` local es una copia.** La fuente de verdad es el volumen `/data`
   de Railway; el `data/` local refleja el último restore o sync local. La
   frescura (última fecha de FINAL y su antigüedad) es parte obligatoria de
   cada respuesta.
7. **Los artefactos de sesión no son aptos todavía.** Los
   `analysis/reports/**/artifacts/session_payload.json` contienen rutas
   absolutas (`fit_path`, `hr_stream_csv`), algunas del repositorio anterior.
   Exponerlos exige allowlist de campos y redacción.

## Alcance del MVP

Cuatro herramientas, todas de solo lectura:

| Herramienta | Fuente | Qué devuelve |
|---|---|---|
| `hrv_get_daily_status(date)` | payload compartido (FINAL, reason_items, sleep, sessions_day) + manifest | decisión, HRV matinal, sueño de esa noche, carga previa con desfase, frescura |
| `hrv_explain_gate(date)` | reason_items + columnas de gate de FINAL | items del día agrupados por capa, con valores y umbrales |
| `hrv_get_date_range(from, to, fields, limit)` | DASHBOARD y allowlist de FINAL | serie acotada, nunca posterior a `to`, con `truncated` |
| `hrv_get_data_quality(from, to)` | CORE, FINAL, sleep, sessions_day + manifests | cobertura por fecha, `Calidad`, huecos, frescura y procedencia |

`hrv_get_capabilities` y `hrv_get_runtime_status` se pliegan en un recurso
`hrv://capabilities` (herramientas, versión de esquema, artefactos disponibles
y frescura). No hay prompts MCP en el MVP.

### Fuera del MVP

| Elemento | Condición para incorporarlo |
|---|---|
| Sesiones (`list_sessions`, `get_session_context`) | allowlist de campos y redacción de rutas sobre `session_payload.json` y `summary.json` |
| Contexto semanal | contrato estable del manifest semanal de `analysis/` (existen `weekly_prep_manifest.json`, pero sin contrato versionado) |
| Prompts MCP versionados | uso real que lo justifique |
| Transporte HTTP / acceso remoto | tarea separada: extensión privada para ChatGPT |
| Mutaciones (sync, restore, borrados) | nunca en este servidor |

## Reglas de respuesta

- Sobre común versionado: `schema_version`, `as_of`, `status`, `measured`,
  `derived`, `context`, `quality`, `sources`, `provenance`.
- `as_of` es la fecha consultada, no "hoy"; ninguna fila posterior a `as_of`
  o a `to`.
- `null` en vez de `NaN`; la ausencia se explica en `quality.warnings`.
- Sin rutas absolutas, tokens, RR, GPS, streams ni `notes_raw`; `sources` usa
  nombres lógicos de artefacto.
- Límites de filas y días explícitos y declarados.

## Relación con otras tareas

- **IU-13** (done): aporta los manifests que el MCP consume.
- **SYA-18** (propuesta): condiciona las herramientas semanales.
- **IU-04** (propuesta): el MCP no reutiliza el payload de `/api/status`.
- **AYO-27** (propuesta): fase remota para ChatGPT; parte del contrato y de la
  capa de consulta de esta tarea.
- **AYO-14** (descartada): el MCP de Polar no se construye; esta tarea no
  necesita componer con él.

## Criterios de aceptación

1. Funciona localmente por `stdio`; no está en la imagen de Railway.
2. Las cuatro herramientas son de solo lectura y no importan entrypoints ni
   módulos con efectos laterales al importarse.
3. El estado diario sale de la misma capa que alimenta el brief diario; el
   brief sigue pasando sus tests de contrato tras la extracción.
4. Toda respuesta usa el sobre versionado y declara fuentes, frescura y calidad.
5. Las consultas respetan causalidad temporal (test explícito).
6. Ninguna respuesta contiene rutas absolutas, tokens, RR, GPS ni streams
   (test negativo).
7. La ausencia de un artefacto produce `partial` o `not_found`, nunca una
   conclusión inventada.
8. Existe documentación de instalación, activación y desactivación.
