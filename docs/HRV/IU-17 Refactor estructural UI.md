
## Contexto

La UI web (`web_ui.py` + `templates/` + `static/`) mezcla capa de presentación y lógica de formato. El refactor busca separar el viewmodel del render para que cambios visuales o de copy no obliguen a tocar tres archivos. Auditoría inicial realizada el 2026-06-30.

**Alcance acordado:** solo refactor estructural (sin rediseño visual). El rediseño visual queda para una iteración posterior, sobre la base nueva.

**Política operativa:**
- Evitar sobre-ingeniería. Si aparece una abstracción no justificada por el problema actual, parar y preguntar antes de seguir.
- Antes y después de cada cambio, verificar que la UI no regresiona (tests de contrato + smoke manual del flujo /api/status, /, /api/sync).

---

## Estado actual (snapshot)

### Stack
- Flask SSR (Jinja) + `ui.js` vanilla (482 líneas, IIFE)
- `ui.css` 472 líneas, sin build, sin framework
- Tres cards apiladas: `dashboard_actions`, `hrv_summary_card`, `technical_output_card`
- `templates/data/ui_copy.json.j2` + `ui_runtime_config.json.j2` para textos/config

### Flujo de datos
```
GET /            → render_template('index.html', initial_*=...) — SSR con datos crudos
GET /api/status  → _build_status_payload() → diagnostics dict plano ~50 claves
JS               → applyUiState(data) → renderHrvSummaryPanel() reescribe encima
Fallback         → _render_index_fallback() (HTML inline en Python, sólo si template no encontrado)
```

---

## Problemas estructurales detectados

### P1 — Triple fuente de renderizado para la misma card
La "Lectura HRV de hoy" se construye en **tres sitios**:
- `templates/partials/hrv_summary_card.html` (SSR Jinja inicial)
- `static/ui.js` línea 109 `renderHrvSummaryPanel()` (rehidratación cliente)
- `web_ui.py` línea 1103 `_render_index_fallback()` (HTML inline si Jinja falla)

**Impacto:** cualquier cambio de copy o estructura obliga a tocar tres archivos. Divergen en sutilezas (el fallback usa `hrv_summary_raw_text` ya formateado; el JS reconstruye desde campos crudos).

### P2 — Lógica de formato vive en el frontend
`ui.js:142-145`:
```js
panel.raw.textContent = `${fmtNumber(rmssdRaw)} ms · HR ${fmtNumber(hrToday)} lpm · lnRMSSD bruto ${fmtNumber(lnToday, 3)}`;
panel.used.textContent = `${fmtNumber(expFromLog(lnUsed))} ms · lnRMSSD usado ${fmtNumber(lnUsed, 3)}`;
```
Pero `_compose_hrv_summary_diagnostics` en `web_ui.py` ya compone los mismos strings (`hrv_summary_raw_text`, `_used_text`, `_base_text`, `_gate_text`). El SSR los consume; el JS los ignora y los recompone.

**Impacto:** dos fuentes de verdad para el mismo string. Cambios en precisión decimal, unidades u orden deben replicarse en backend + frontend.

### P3 — `/api/status` devuelve diagnostics crudos, no un viewmodel
La UI conoce nombres internos del pipeline: `final_last_rmssd_stable`, `final_last_ln_base60`, `latest_rr_path`, `final_last_gate_razon_base60`. Cualquier rename en CSV/pipeline rompe el JS.

**Impacto:** acoplamiento alto entre estructura interna del pipeline y la UI. Sin contrato versionado.

### P4 — Datos calculados que la UI no consume
`_build_status_payload` expone pero la UI no muestra:
- `weekly_coach_planning_note`
- `weekly_coach_z3_budget_summary`
- `weekly_coach_data_quality` / `weekly_coach_iso_week`
- `dropbox_*` (estado credenciales/folder)
- `final_last_gate_razon_base60` (se concatena al gate sin separarlo)

**Impacto:** capa de carga semanal invisible aunque el JSON está listo. No es un problema de refactor en sí, pero sí justifica tener un viewmodel donde encajen sin tocar JS cada vez.

### P5 — Capa de acciones repartida
- Botones sync viven en `dashboard_actions.html`
- Botones restore/delete en `technical_output_card.html`
- Comparten lock mutuo en backend (`/api/sync*` no concurrentes) pero la UI no muestra esa relación

**Impacto:** organización HTML refleja layout, no semántica. Difícil añadir/mover botones sin entender el JS.

---

## Propuesta de refactor (mínima viable, sin sobre-ingeniería)

### Fase R1 — Viewmodel en backend
Nuevo módulo `hrv_app/ui_view.py`:

```python
def build_dashboard_viewmodel(payload: dict) -> dict:
    """Construye viewmodel versionado para la UI a partir del payload de /api/status.

    Retorna estructura plana por sección:
        {
          "version": 1,
          "hrv_today": {
            "exists": bool,
            "date": "2026-06-30",
            "raw":   {"label": "...", "value": "45.2 ms · HR 58 lpm · lnRMSSD bruto 3.812"},
            "used":  {"label": "...", "value": "..."},
            "base":  {"label": "...", "value": "..."},
            "gate":  {"label": "...", "value": "OK", "reason": "base60_ok"},
            "ai_text": "...",
            "reason_text": "...",
            "fallback_text": "...",
          },
          "system": {
            "authorized": bool,
            "latest_rr_name": str | None,
            ...
          },
          "actions": {
            "show_seed_import": bool,
            "show_restore_backup": bool,
            "delete_last_rr_enabled": bool,
          }
        }
    ```

**Regla clave:** todo formato de strings vive aquí. JS y Jinja sólo consumen `value` y `label` ya listos.

Mover/centralizar:
- `_compose_hrv_summary_diagnostics` → componer parte de `hrv_today`
- Formato de fechas RR (`fmtDateFromRrName` que hoy vive en JS) → backend
- Templates de mensajes que hoy renderiza `ui.js` (`renderTemplate`) → revisar si caben en viewmodel

**Lo que NO se toca en R1:**
- Diagnostics crudos siguen exponiéndose en `/api/status.diagnostics` (compatibilidad con tests existentes y debugging)
- Sólo se añade `/api/status.view` como capa nueva
- Pipeline (`build_hrv_core`, `build_hrv_final_dashboard`, `build_sessions`) NO se toca

### Fase R2 — Un solo path de render en frontend
- `index.html` consume `view.*` desde el viewmodel pasado por SSR (no `initial_*` sueltos)
- `ui.js` reducido: mapeo declarativo `{selector: viewPath}` o función `applyView(view)` que rellena DOM sin construir strings
- Eliminar `fmtNumber`, `expFromLog`, `fmtDateFromRrName` del cliente (delegar al viewmodel)
- Eliminar `_render_index_fallback` o reducir a un mensaje mínimo (la causa real de error sería `TemplateNotFound`, que ya logueamos)

### Fase R3 — Reorganizar partials por sección semántica
- `_hrv_today.html`, `_actions.html`, `_technical_log.html`, `_system_status.html`
- Cada partial recibe `view.hrv_today`, `view.actions`, etc.

**Lo que NO se toca en R3:**
- No introducir componentes JS reutilizables, ni Web Components, ni framework
- No cambiar la estética visual (CSS sin cambios salvo lo necesario por reordenar HTML)

---

## Validación antes/después

### Antes de empezar
1. Ejecutar tests actuales: `pytest tests/test_web_ui_status.py -v`
2. Smoke manual: arrancar `web_ui.py` local, validar render de `/`, llamada a `/api/status`, click en sync (sin RR nuevos basta para verificar UI)
3. Capturar `/api/status` response como baseline (guardar en `research/audits/system/` como referencia)

### Durante cada fase
- Tests de contrato siguen pasando
- `/api/status` mantiene shape original (sólo añade `view` como key nueva)
- Diff visual cero: render inicial y rehidratación deben mostrar exactamente lo mismo que antes

### Después de cada fase
- Pytest verde
- Smoke manual del flujo completo
- Si algún test no cubre algo que sí estaba funcionando, añadir test antes de cerrar fase

---

## Riesgos y límites de alcance

| Riesgo | Mitigación |
|---|---|
| Romper compatibilidad con tests existentes que asumen forma de `/api/status` | Mantener `diagnostics` intacto, sólo añadir `view` |
| Romper SSR fallback (`_render_index_fallback`) que protege contra TemplateNotFound | Conservar fallback mínimo; o eliminar si los tests confirman que Jinja siempre encuentra el template |
| Introducir abstracciones innecesarias (clases, factories, builders) | Una sola función `build_dashboard_viewmodel`; si aparece la tentación de jerarquía, parar y preguntar |
| Reescribir el JS entero | Refactor incremental, función por función. No reescritura total |
| Cambiar contratos de `weekly_coach.json` o CSVs | Fuera de alcance. Sólo se lee lo que ya está expuesto |

---

## Criterios de aceptación

1. `hrv_app/ui_view.py` existe con `build_dashboard_viewmodel(payload) -> dict` y test unitario
2. `/api/status` retorna `{execution: {...}, diagnostics: {...}, view: {...}}` — `diagnostics` sin cambios
3. `index.html` y partials consumen sólo `view.*`
4. `ui.js` no construye strings de métricas (las lee del viewmodel)
5. Divergencia de render eliminada: las tres rutas (Jinja SSR, JS, fallback Python) consumen el mismo viewmodel, por lo que ya no pueden divergir en formato. Las tres rutas se conservan (el fallback es la red de seguridad ante `TemplateNotFound`)
6. Tests de `test_web_ui_status.py` siguen pasando
7. Smoke manual: render inicial y rehidratación visualmente idénticos al estado pre-refactor

---

## Resultado real (2026-06-30)

Implementado y verificado:
- `hrv_app/ui_view.py` con `compose_hrv_summary()` (formato canónico de strings) y `build_view()` (viewmodel versionado `version=1`, secciones `hrv_today` y `system`). 13 tests en `tests/test_ui_view.py`.
- `/api/status` añade `view`; `diagnostics` intacto. Nota: el payload aplana los campos de ejecución en la raíz (`running`, `success`, `job_type`, ...) + `diagnostics` + `view`, no usa una clave anidada `execution` (la propuesta original lo planteaba anidado; se mantuvo el shape histórico para no romper consumidores).
- Jinja (`hrv_summary_card.html`), JS (`ui.js`) y fallback (`_render_index_fallback`) consumen `view.*`. `ui.js` ya no construye strings ni accede a `diagnostics.*`; eliminados `fmtNumber`, `expFromLog`, `fmtDateFromRrName`.
- Limpieza post-refactor: eliminado `import math` muerto y 3 alias muertos (`_fmt_number`, `_fmt_exp_from_log`, `_render_ai_brief_text`) en `web_ui.py`.

Validación: 53 tests del scope UI (`test_ui_view` + `test_web_ui_status` + `test_web_ui_security`) en verde antes y después. El fallo de `test_analyze_weekly` observado es ajeno a IU-17: lo causa un CSV local malformado (`data/ENDURANCE_HRV_intensity_distribution_weekly.csv`, comilla sin cerrar) y ese módulo no importa nada del scope tocado.

Pendiente / no hecho (intencional):
- R3 (reorganizar partials por sección semántica) no ejecutado; los botones siguen repartidos entre `dashboard_actions.html` y `technical_output_card.html` (P5 sin resolver).
- `view.system` expone `latest_rr_*` pero ningún campo de `weekly_coach`/`dropbox` (P4 fuera de alcance).

---

## Fuera de alcance (explícito)

- Cambios visuales o de paleta
- Sparklines, gráficos, deltas vs baseline
- Mostrar `weekly_coach.*` u otros datos no expuestos hoy
- Cambios en endpoints API más allá de añadir `view` al payload existente
- Migración a framework JS, build tooling, TypeScript, etc.
- Cambios en pipeline o CSVs

Estos items se discutirán en una iteración posterior (probable IU-18 "Rediseño visual UI") una vez la base esté consolidada.
