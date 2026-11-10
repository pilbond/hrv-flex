# Plan AYO-15 — MCP de solo lectura HRV (plan de desarrollo)

> Documento de **ejecución**. El porqué, el alcance y los criterios de
> aceptación están en [[AYO-15 Crear MCP de solo lectura para la aplicacion HRV]].
> Revisado el 2026-11-09. Estado de la tarea: `proposed`.

---

## 1. Principios

1. **Reutilizar, no reimplementar.** El estado diario ya lo calcula
   `hrv_app/ai/daily_brief.py`; se extrae a un módulo compartido. Nada de
   recalcular gate, `training_audit` ni pipeline.
2. **Read-only de verdad.** Sin escrituras, sin `mkdir`, sin imports con
   efectos laterales, sin red.
3. **Privacidad por elección de fuente.** Solo artefactos sin RR, GPS,
   streams ni texto libre; rutas siempre como nombres lógicos.
4. **Su caída no afecta a nada.** Proceso aparte y dependencia opcional fuera
   de la imagen de Railway.

---

## 2. Arquitectura

```
Host MCP local (Claude Code / Codex)
      │  stdio
      ▼
hrv_app/mcp/server.py          ← adaptador fino (FastMCP): 4 tools + 1 resource
      │
      ▼
hrv_app/query/                 ← capa de lectura pura, testeable sin SDK MCP
      ├── paths.py             ← rutas read-only desde HRV_DATA_DIR (sin mkdir)
      ├── catalog.py           ← existencia, frescura y procedencia desde manifests
      ├── daily.py             ← payload diario extraído del brief + explain_gate
      ├── quality.py           ← cobertura y calidad por rango
      └── envelope.py          ← sobre de respuesta, límites y saneado
      ▲
      │  (importa la misma lógica)
hrv_app/ai/daily_brief.py      ← conserva prompt, interpretation_contract y validación
```

### 2.1 Extracción del payload diario

Mover a `hrv_app/query/daily.py` la parte determinista de `daily_brief.py`:

- `_to_py`, `_row_dict`, `_normalize_gate`;
- `_classify_morning`, `_classify_sleep`, `_sleep_context`, `_same_night`,
  `_polar_rating`, `_polar_nightly_recharge`, `_sleep_duration_anomaly`;
- `_load_reason_items_lookup`, `_reason_items_overlap`,
  `_renderable_reason_metrics`;
- el núcleo de `_build_payload`: `decision`, `reason_items`, `morning_hrv`,
  `sleep_context`, `recent_load_summary` y notas de desfase.

Se quedan en `daily_brief.py` lo específico del LLM: `interpretation_contract`,
`expected_output`, `reason_items_meta.rendering_note` y
`numeric_rendering_policy`, el prompt, la llamada al modelo, la validación y
los sidecars.

Reglas de la extracción:

- Las funciones reciben rutas o DataFrames como parámetros; `hrv_app/query/`
  no importa `hrv_app.config` ni `hrv_app.ai.config`.
- `meta.data_sources` pasa a nombres lógicos (`final`, `sleep`,
  `sessions_day`, `reason_items`). El brief puede seguir registrando rutas en
  su sidecar si lo necesita, pero la capa compartida no las produce.
- `generated_at` sale del payload base para que la salida sea determinista; el
  brief lo añade al construir el sidecar.
- `tests/test_ai_daily_brief_contract.py` y
  `tests/test_ai_brief_storage.py` deben seguir pasando sin cambios de
  comportamiento. El `payload_hash` puede cambiar si cambia `data_sources`;
  se acepta y se documenta en la misma entrega.

### 2.2 Rutas

`paths.py` resuelve `HRV_DATA_DIR` (default `data`) sin crear ni escribir
nada, con una allowlist de nombres de fichero:

- `ENDURANCE_HRV_master_CORE.csv`, `..._FINAL.csv`, `..._DASHBOARD.csv`;
- `ENDURANCE_HRV_master_FINAL_reason_items.json`;
- `ENDURANCE_HRV_master_CORE_manifest.json`, `..._FINAL_manifest.json`;
- `ENDURANCE_HRV_sleep.csv`, `ENDURANCE_HRV_sessions_day.csv`.

Cualquier otro fichero no es accesible desde el MCP.

### 2.3 Dependencia y arranque

```
requirements_mcp.txt          # opcional; no se instala en Railway
  mcp                         # SDK oficial Python (FastMCP), versión fijada al implementar

python -m hrv_app.mcp.server  # stdio
scripts/run-mcp.bat           # wrapper Windows
```

`Dockerfile` y `requirements_web.txt` no cambian.

---

## 3. Herramientas y recurso

| Nombre | Firma de la capa query | Límites |
|---|---|---|
| `hrv_get_daily_status` | `get_daily_status(date, *, catalog)` | una fecha |
| `hrv_explain_gate` | `explain_gate(date, *, catalog)` | una fecha |
| `hrv_get_date_range` | `get_date_range(date_from, date_to, fields, limit, *, catalog)` | máx. 90 días; `fields` sobre allowlist de DASHBOARD/FINAL |
| `hrv_get_data_quality` | `get_data_quality(date_from, date_to, *, catalog)` | máx. 90 días |
| recurso `hrv://capabilities` | `catalog.capabilities()` | herramientas, `schema_version`, artefactos presentes, frescura |

`catalog.freshness()` devuelve la última `Fecha` de FINAL, `age_days` respecto
a la fecha local y `stale` según `HRV_STALE_MAX_DAYS` (default 3), igual que
`/health?strict=1`.

---

## 4. Sobre de respuesta

```json
{
  "schema_version": "1.0",
  "as_of": "2026-11-08",
  "status": "complete",
  "measured": {},
  "derived": {},
  "context": {},
  "quality": { "state": "high", "warnings": [], "truncated": false },
  "sources": ["final", "reason_items", "sleep", "sessions_day"],
  "provenance": {
    "final_generated_at": null,
    "artifact_hashes": {},
    "freshness": { "last_date": null, "age_days": null, "stale": false }
  }
}
```

- `status` ∈ `complete | partial | not_found | not_applicable | stale`.
- `null` en vez de `NaN`.
- `sources` con nombres lógicos, nunca rutas.

---

## 5. Pruebas (pytest, Python 3.11, CI actual)

Fixtures mínimas (5–10 fechas) en `tests/fixtures/mcp/`: DASHBOARD, FINAL
(subconjunto de columnas), reason_items, manifests, sleep y sessions_day.

1. Forma del sobre en las cuatro herramientas y el recurso.
2. Fecha inválida → error tipado; fecha inexistente → `not_found`.
3. Límites: `get_date_range` respeta `limit` y 90 días y marca `truncated`.
4. Sin sueño de esa noche → `sleep_for_target_date: false` y `status: partial`.
5. FINAL antiguo → `stale` y `age_days` correcto.
6. Causalidad: ninguna fila posterior a `as_of` o `to`; carga con
   `as_of_date` ≤ fecha consultada.
7. Privacidad: ninguna respuesta contiene `C:\`, `/app/`, `/data/`, tokens,
   RR, GPS ni `notes_raw`.
8. Determinismo: misma entrada → misma salida byte a byte.
9. `explain_gate` agrupa por `layer` igual que `reason_items.json`.
10. Regresión del brief diario tras la extracción.

Prueba manual de humo: MCP Inspector y un host real (Claude Code).

---

## 6. Fases

### Fase A — Extracción y capa query (sin SDK MCP)

- Extraer el payload diario a `hrv_app/query/daily.py` y adaptar
  `daily_brief.py` para usarlo.
- `paths.py`, `catalog.py`, `quality.py`, `envelope.py`.
- Tests §5 contra la capa query.
- **Hito A:** las cuatro consultas funcionan desde pytest y el brief diario no
  cambia de comportamiento.

### Fase B — Adaptador MCP local

- `requirements_mcp.txt`, `hrv_app/mcp/server.py`, `scripts/run-mcp.bat`.
- Registro en `.mcp.json` local documentado como opcional.
- Documentación de instalar, activar y desactivar.
- **Hito B:** servidor `stdio` descubrible desde Claude Code.

### Fase C — Extensiones (solo bajo demanda)

- Sesiones con allowlist de campos y redacción de rutas.
- Contexto semanal cuando el manifest semanal tenga contrato versionado.
- Reutilización de la capa query por la extensión remota para ChatGPT.

Estimación relativa: Fase A ≈ 60 %, Fase B ≈ 25 %, documentación y QA ≈ 15 %.

---

## 7. Riesgos

| Riesgo | Mitigación |
|---|---|
| La extracción rompe el brief diario | tests de contrato existentes + test de regresión del payload |
| Datos locales desactualizados leídos como actuales | frescura obligatoria en cada respuesta; `stale` |
| Rutas o secretos en respuestas | allowlist de ficheros y campos, nombres lógicos, test negativo |
| Segunda superficie de contrato | `schema_version` propio y tests de forma |
| Sobreingeniería | 4 herramientas, 1 recurso, 0 prompts; Fase C opcional |
| Mutaciones añadidas más adelante | fuera de este servidor por diseño |
