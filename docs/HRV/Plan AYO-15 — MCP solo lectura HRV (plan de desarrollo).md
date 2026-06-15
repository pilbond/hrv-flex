# Plan AYO-15 — MCP de solo lectura HRV (plan de desarrollo)

> Documento de **ejecución**. Complementa la nota conceptual
> [[AYO-15 Crear MCP de solo lectura para la aplicacion HRV]] (el "porqué").
> Aquí va el "cómo": alcance recortado, módulos, contratos, pruebas y fases.
> Fecha: 2026-06-14. Estado tarea: `purple` (propuesta).

---

## 1. Veredicto de la evaluación

**La tarea tiene valor y es viable a bajo coste si se mantiene pequeña.**

Tres hechos del repositorio actual sostienen esta conclusión:

1. **La columna de procedencia ya existe (IU-13, hecho).** `data/` contiene
   `ENDURANCE_HRV_master_CORE_manifest.json` y
   `ENDURANCE_HRV_master_FINAL_manifest.json` con `generated_at`, hashes
   `sha256`, `row_count`/`column_count` y `effective_config_hash`. No hay que
   construir hashing ni frescura: solo leerlos.
2. **La explicación del gate ya está estructurada.**
   `ENDURANCE_HRV_master_FINAL_reason_items.json` ya trae `schema_version` e
   `items_by_date`, con cada item tipado por capa
   (`type`, `layer`, `source`, `message`, `metric`, `value`, `threshold`,
   `severity`, `variant`). `hrv_explain_gate` es casi gratis.
3. **Los artefactos del MVP no contienen datos sensibles.** `DASHBOARD`,
   `FINAL`, `reason_items` y los manifests **no** llevan RR, GPS, streams ni
   rutas absolutas. La redacción solo es un problema en `analysis/` (los
   `session_payload.json` sí contienen rutas absolutas), por eso esa capa se
   difiere.

**Riesgo principal: sobreingeniería.** La nota conceptual propone 11
herramientas, 6 recursos, 4 prompts, 5 fases y un `HRVQueryService` con seis
lectores. Para un proyecto N=1 eso es excesivo de entrada. Este plan recorta el
MVP a **6 herramientas + 3 recursos**, todas sobre artefactos ya estables y sin
datos sensibles, y **difiere** explícitamente sesiones, semana, prompts y HTTP.

---

## 2. Principios de diseño (orden de prioridad)

1. **Simpleza primero.** Capa de lectura fina + adaptador MCP fino. Nada de
   reimplementar el gate, el `training_audit` ni el pipeline.
2. **Read-only de verdad.** El servidor no importa `web_ui.py`, builders ni
   nada con efectos laterales. No abre puertos en V1 (`stdio`). No toca `/data`.
3. **Reutilizar lo que ya está calculado.** Manifests para procedencia,
   `reason_items.json` para el gate, `DASHBOARD`/`FINAL` para el estado.
4. **Privacidad por construcción, no por filtro.** El MVP solo expone
   artefactos que de origen no contienen datos sensibles. La seguridad se gana
   eligiendo bien las fuentes, no añadiendo redactores complejos.
5. **Su caída no afecta a nada.** Proceso aparte, dependencia opcional, fuera
   de la imagen Railway.

---

## 3. Alcance recortado del MVP

### 3.1 Herramientas V1 (6)

| Herramienta | Fuente(s) | Coste | Sensibilidad |
|---|---|---|---|
| `hrv_get_capabilities()` | estático + manifests | trivial | nula |
| `hrv_get_daily_status(date)` | DASHBOARD + subset FINAL + reason_items + manifest | bajo | nula |
| `hrv_explain_gate(date)` | reason_items.json + columnas gate de FINAL | trivial | nula |
| `hrv_get_date_range(from, to, fields, limit)` | DASHBOARD/FINAL (slice acotado) | bajo | nula |
| `hrv_get_data_quality(from, to)` | CORE/FINAL/sleep (presencia) + `Calidad` + manifest | bajo | nula |
| `hrv_get_runtime_status()` | manifests CORE/FINAL (saneado) | trivial | nula (saneado) |

Estas seis cubren la pregunta más frecuente ("¿cuál era el estado y con qué
confianza?") y la trazabilidad, sin tocar ninguna fuente con datos personales.

### 3.2 Diferido a fase posterior (con motivo)

| Herramienta | Por qué se difiere |
|---|---|
| `hrv_list_sessions`, `hrv_get_session_context`, `hrv_compare_sessions` | `session_payload.json` contiene **rutas absolutas** (`fit_path`, `hr_stream_csv`, `.cache/...`) → exige capa de redacción + allowlist de campos. Mayor coste y mayor riesgo. |
| `hrv_get_weekly_context`, `hrv_get_training_distribution` | dependen de `weekly_coach.json`, cuyo manifest **no está estabilizado hasta SYA-18**. Hasta entonces solo cabría degradar con aviso; mejor no exponerla aún. |
| `hrv_get_artifact_manifest(stage)` | se solapa con `hrv_get_runtime_status`; se puede plegar dentro y separar solo si se demuestra necesidad. |
| `hrv_find_missing_rr`, `hrv_get_data_inventory` | útiles pero secundarias; `hrv_get_data_quality` ya da cobertura. Añadir solo si hay demanda real. |
| Prompts MCP (`hrv_daily_review`, ...) | no aportan en N=1 de entrada; la nota ya lo dice. |
| Transporte HTTP | solo si aparece necesidad de acceso remoto. |
| Mutaciones (`hrv_run_sync`, ...) | fuera de alcance permanente para este servidor; servidor separado si alguna vez. |

### 3.3 Recursos V1 (3)

```
hrv://capabilities                 # mismo contenido que hrv_get_capabilities()
hrv://contracts/source-precedence  # orden de fuentes (texto corto)
hrv://contracts/data-dictionary    # apunta a docs/contracts/ENDURANCE_HRV_Diccionario.md
```

No exponer CSV completos como recursos. El histórico personal se sirve solo por
herramientas con límites.

---

## 4. Contrato de respuesta

Sobre de respuesta común (idéntico para todas las herramientas analíticas),
alineado con la nota conceptual:

```json
{
  "schema_version": "1.0",
  "as_of": "2026-06-14",
  "status": "complete",
  "measured": {},
  "derived": {},
  "context": {},
  "quality": { "state": "high", "warnings": [] },
  "sources": [],
  "provenance": {
    "generated_at": null,
    "artifact_hashes": {},
    "contract_versions": {}
  }
}
```

Reglas duras:

- `status` ∈ `complete | partial | not_found | not_applicable | stale`.
- Nunca `NaN`; usar `null` y, si procede, razón en `quality.warnings`.
- Toda respuesta declara `sources` y `provenance` (tomados del manifest).
- Nunca rutas absolutas, tokens, RR, GPS ni streams.
- Límites de filas/bytes explícitos; si se trunca, marcarlo en
  `quality.warnings` y en un campo `truncated: true`.
- `as_of` y frescura siempre presentes (edad del FINAL respecto a hoy).

---

## 5. Arquitectura (mínima)

```
Host MCP (Claude / Codex)
      │  stdio
      ▼
hrv_app/mcp/server.py        ← adaptador fino (FastMCP); registra tools+resources
      │
      ▼
hrv_app/query/               ← capa de lectura PURA, sin efectos laterales
      ├── paths.py           ← resuelve rutas read-only desde env (sin mkdir)
      ├── catalog.py         ← ArtifactCatalog: existencia, frescura, hash desde manifest
      ├── daily.py           ← daily_status() + explain_gate()
      ├── quality.py         ← cobertura/calidad por fecha o rango
      └── schemas.py         ← sobre de respuesta + helpers de validación/límites
      │
      ▼
data/*.csv  ·  data/*.json (reason_items, manifests)
```

Decisiones para mantenerlo simple:

- **`paths.py` propio, read-only.** No reutilizar `hrv_app/config.py` en
  caliente: su import ejecuta `_load_local_env()` y `_resolve_writable_dir()`
  (hace `mkdir` y una prueba de escritura). Para un servidor read-only conviene
  un resolutor mínimo que lea `HRV_DATA_DIR` (default `data`) **sin** crear ni
  escribir nada. Replica solo las constantes de nombre de fichero. Mantiene la
  pureza read-only y el desacople. (Coste: ~20 líneas; beneficio: el MCP no
  toca el filesystem de datos jamás.)
- **`catalog.py` lee el manifest, no recalcula hashes.** Frescura =
  `today - last Fecha de FINAL`; procedencia = `generated_at` + `sha256` del
  manifest. Cero trabajo nuevo de hashing.
- **`daily.py` reutiliza `reason_items.json` tal cual** para `explain_gate`; el
  estado diario combina la fila de DASHBOARD con un subconjunto allowlisted de
  columnas de FINAL.
- **pandas ya es dependencia** del proyecto: la capa query puede usarlo. El
  adaptador MCP **no** necesita pandas.
- **Sin pydantic nuevo si el SDK no lo exige.** El sobre se construye con dicts
  + dataclasses ligeras. (FastMCP del SDK oficial ya trae validación de
  argumentos vía type hints; no añadir un segundo sistema.)

### 5.1 Dependencia y arranque

```
requirements_mcp.txt        # nueva, OPCIONAL y separada de requirements_web.txt
  mcp>=1.0                   # SDK oficial Python (FastMCP). NO se instala en Railway.

# Arranque local:
python -m hrv_app.mcp.server          # stdio
scripts/run-mcp.bat                   # wrapper Windows (opcional)
```

El `Dockerfile`/`requirements_web.txt` **no** cambian: producción no conoce el
MCP. Esto preserva el criterio "su caída no afecta a Railway".

---

## 6. Firmas de referencia (capa query, sin MCP)

```python
# hrv_app/query/daily.py
def get_daily_status(date: str, *, catalog: ArtifactCatalog) -> dict: ...
def explain_gate(date: str, *, catalog: ArtifactCatalog) -> dict: ...

# hrv_app/query/quality.py
def get_data_quality(date_from: str, date_to: str, *, catalog) -> dict: ...

# hrv_app/query/catalog.py
class ArtifactCatalog:
    def freshness(self) -> dict: ...           # last_date, age_days, stale_bool
    def provenance(self, stage: str) -> dict:  # generated_at, hashes, contract_versions
    def exists(self, role: str) -> bool: ...

# hrv_app/query/schemas.py
def envelope(status, measured=None, derived=None, context=None,
             quality=None, sources=None, provenance=None,
             as_of=None) -> dict: ...
def clamp_range(date_from, date_to, max_days=90) -> tuple[str, str, list[str]]: ...
```

La capa query es ejecutable y testeable **sin** el SDK MCP. El adaptador
`server.py` solo envuelve estas funciones en `@mcp.tool()`.

---

## 7. Causalidad temporal

- `get_daily_status(date)` / `explain_gate(date)`: seleccionan exactamente esa
  fila; si no existe → `status: not_found`.
- `get_date_range(from, to)`: filtra `Fecha <= to` y `>= from`; nunca devuelve
  filas posteriores a `to`.
- `as_of` por defecto = `to` (o `date`), no "hoy", para que el corte sea
  explícito y reproducible.
- El riesgo serio de *leakage* vive en sesiones/semana (comparadores futuros);
  como esa capa se difiere, el MVP queda con superficie temporal trivial. Aun
  así, **test explícito** de que `range` nunca filtra futuro.

---

## 8. Seguridad y privacidad (MVP)

- Transporte `stdio`: sin puerto, sin auth HTTP, lo lanza el host. Encaja N=1.
- Sin credenciales: el servidor **no** lee `.env`, `.polar_tokens*.json` ni
  toca Polar/Dropbox/Intervals.
- Allowlist de artefactos en `paths.py`: solo los ficheros del MVP. Cualquier
  ruta fuera de esa lista no es accesible.
- Allowlist de **campos** al serializar FINAL (66 cols → subconjunto útil); por
  defecto no se vuelca la fila entera.
- `notes_raw` y cualquier texto libre: tratados como dato no confiable, jamás
  como instrucción; no se incluyen en V1.
- Tests negativos obligatorios: "ninguna respuesta contiene `C:\\`, token,
  `sha256` de secretos, RR ni GPS".

---

## 9. Plan de pruebas (pytest, encaja con CI 3.11)

Fixtures: copias mínimas (5–10 filas) de `DASHBOARD`, `FINAL`, `reason_items`,
`CORE_manifest`, `FINAL_manifest`, `sleep` bajo `tests/fixtures/mcp/`.

Casos:

1. **Forma del sobre**: todas las herramientas devuelven las claves del §4.
2. **Validación de fecha**: formato inválido → error tipado; fecha inexistente
   → `not_found`.
3. **Límites y truncamiento**: `get_date_range` respeta `limit`/`max_days` y
   marca `truncated`.
4. **Datos ausentes/parciales**: sin sleep para una fecha → `partial`, no
   conclusión inventada.
5. **Frescura/stale**: FINAL viejo → `status: stale` y `age_days` correcto.
6. **Causalidad**: `range(from, to)` nunca devuelve `Fecha > to`.
7. **Privacidad**: ninguna respuesta contiene rutas absolutas, tokens, RR, GPS
   ni claves de secreto.
8. **Determinismo**: mismo input → mismo orden y mismos hashes de procedencia.
9. **explain_gate**: mapea correctamente `layer` (restricción / cautela /
   modificador / contexto) desde `reason_items.json`.

Todos contra la **capa query directa** (rápidos, sin SDK). Una sola prueba de
humo arranca `server.py` y lista herramientas con el MCP Inspector (manual).

---

## 10. Fases de ejecución

### Fase A — Contrato + capa de lectura (sin dependencia MCP)
*Entrega el grueso del valor y del riesgo; el wrapper MCP es trivial después.*

- Definir el sobre §4 y los esquemas de salida de las 6 herramientas.
- `paths.py` (resolutor read-only) + `catalog.py` (frescura/procedencia desde
  manifest).
- `daily.py` (`get_daily_status`, `explain_gate`) y `quality.py`.
- `get_date_range` + clamps.
- Suite de tests §9 (sin MCP).
- **Hito A**: las 6 consultas funcionan y se prueban desde pytest/CLI, sin SDK.

### Fase B — Adaptador MCP local read-only
- `requirements_mcp.txt` con `mcp` (opcional, fuera de Railway).
- `hrv_app/mcp/server.py` (FastMCP, `stdio`): registra 6 tools + 3 resources.
- `scripts/run-mcp.bat` y documentación de instalar/activar/desactivar.
- Validación con MCP Inspector + un host real (Claude Code o Codex).
- **Hito B**: servidor `stdio` funcional, descubrible, read-only.

### Fase C — Extensiones (NO en MVP; abrir solo bajo demanda)
- Sesiones (`list/get_session_context`) **con** capa de redacción de rutas y
  allowlist de campos sobre `session_payload.json`/`summary.json`.
- Semana (`weekly_context`, `training_distribution`) **tras SYA-18**.
- Prompts versionados; transporte HTTP privado; composición con MCP Polar
  (AYO-14) usando `provenance` para distinguir `app_canonical` vs `polar_raw`.

Estimación relativa: Fase A ≈ 60% del esfuerzo, Fase B ≈ 25%, docs/QA ≈ 15%.
El MVP (A+B) es entregable de forma independiente y deja Fase C como opcional.

---

## 11. Ventajas

- **Reutiliza IU-13**: procedencia y frescura ya resueltas; coste real del MVP
  bajo.
- **Interoperabilidad**: Claude, Codex u otros hosts consumen el mismo contrato;
  la semántica vive en la app, no en el prompt de cada cliente.
- **Menos contexto y menos errores**: el agente deja de releer varios CSV y de
  reinterpretar columnas/precedencia.
- **Privacidad por elección de fuente**: el MVP solo toca artefactos sin datos
  sensibles; la seguridad no depende de filtros frágiles.
- **Desacople total**: proceso aparte, dependencia opcional, sin impacto en
  sync/UI/Railway.
- **Base limpia para AYO-14**: `provenance` permite combinar después datos
  locales canónicos con datos Polar externos sin confundir capas.

## 12. Inconvenientes y costes

- **Nueva dependencia** (`mcp` SDK) y un entrypoint más que mantener (aunque
  opcional y fuera de producción).
- **Segunda superficie de contrato**: si cambian las 66 columnas de FINAL, el
  esquema de `reason_items` o los manifests, hay que versionar y actualizar el
  MCP. Mitigación: `schema_version` propio + tests de forma + leer del manifest
  en vez de fijar columnas.
- **Riesgo de duplicación semántica**: tentación de recalcular el gate o el
  audit. Mitigación dura: el MCP **solo consulta y presenta**; nada de lógica.
- **Sesiones/semana no entran en V1**: parte del valor descrito en la nota
  queda diferido (rutas a redactar; SYA-18 pendiente). Es una elección
  deliberada de simpleza, no una carencia.
- **Disciplina read-only**: hay que vigilar que nadie añada mutaciones a este
  servidor; deben ir, si acaso, a un servidor separado con confirmación humana.

## 13. Riesgos y mitigaciones (resumen)

| Riesgo | Mitigación |
|---|---|
| Datos obsoletos leídos como actuales | `generated_at`, `age_days`, `status: stale` en cada respuesta |
| Payload excesivo | límites de filas/bytes, allowlist de campos, `truncated` |
| Exposición de rutas/secretos | MVP solo sobre artefactos sin datos sensibles + tests negativos |
| Prompt injection desde texto libre | `notes_raw` fuera de V1; texto libre marcado como no confiable |
| Acoplamiento al layout de ficheros | `catalog.py` central + rutas por env, no hardcode disperso |
| Sobreingeniería | 6 tools, 3 resources, 0 prompts; Fase C explícitamente opcional |

---

## 14. Relación con otras tareas

- **IU-13 (en Review)**: ya entrega los manifests que el MCP consume. Sin
  bloqueo; es habilitador.
- **SYA-18 (propuesta)**: estabiliza el manifest semanal → **gate** de las
  herramientas de semana (Fase C).
- **IU-04 (propuesta)**: reduce `/api/status`; el MCP **no** debe reutilizar ese
  payload — usa los artefactos directamente.
- **AYO-14 (propuesta)**: MCP de Polar v4; **complementario**, no
  intercambiable. `provenance` separa `app_canonical` de `polar_raw`.
- **AYO-13 (en curso)**: aporta Polar v4 al pipeline, pero el MCP de la app se
  construye con los artefactos actuales; **no es dependencia**.

---

## 15. Criterios de aceptación (MVP)

1. El servidor funciona localmente por `stdio` (`python -m hrv_app.mcp.server`).
2. Las 6 herramientas V1 son de solo lectura y no importan entrypoints con
   efectos laterales.
3. No requiere credenciales de proveedores ni lee `.env`/token files.
4. Toda respuesta usa el sobre versionado del §4 y declara `sources`,
   frescura y `quality`.
5. Las consultas por fecha respetan causalidad temporal (test explícito).
6. Ninguna respuesta devuelve rutas absolutas, tokens, RR, GPS ni streams.
7. La ausencia de un artefacto produce `partial`/`not_found`, nunca una
   conclusión inventada.
8. Los payloads tienen límites y declaran truncamiento.
9. El MCP no modifica outputs canónicos ni contratos; su caída no afecta a
   sync/UI/Railway (no está en la imagen).
10. Existe documentación de instalación, versión y desactivación, y la suite
    incluye tests de privacidad y de forma del sobre.

---

## 16. Resumen de una línea

Construir una capa de consulta Python read-only sobre artefactos ya existentes
(DASHBOARD/FINAL/reason_items/manifests) y envolverla en un MCP `stdio` con
**6 herramientas de alto valor y sin datos sensibles**; diferir sesiones,
semana, prompts y HTTP hasta que aporten valor claro. Simpleza y utilidad por
encima de cobertura.
