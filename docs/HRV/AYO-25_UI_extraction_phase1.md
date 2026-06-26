# AYO-25: Extraer UI a archivos estáticos (Fase 1 desacople frontend)

**Estado:** Hecho
**Grupo:** Plataforma  
**Fecha creación:** 2026-06-23  
**Análisis de viabilidad:** [`Evaluacion viabilidad migracion UI a Vue.md`](Evaluacion%20viabilidad%20migracion%20UI%20a%20Vue.md)

**Nota:** este documento conserva también la revisión previa a la extracción; la implementación ya está aplicada en el runtime actual.

---

## Objetivo

Extraer la UI embebida de `web_ui.py` (plantilla principal + HTML inline OAuth) a `templates/` y `static/`. Esto desacopla frontend de backend, mejora mantenibilidad, y prepara decisiones futuras sobre frontend sin cambiar el runtime ni el comportamiento operativo observado.

---

## Alcance

### Qué se hace

1. **Crear estructura de directorios:**
   ```
   templates/
     index.html          ← shell principal actual
     oauth_success.html  ← Callback OAuth exitoso (hereda ui.css)
     oauth_error.html    ← Callback OAuth error (hereda ui.css)
     partials/ui_runtime_config.html ← puente JSON mínimo para ui.js
   
   static/
     ui.css              ← Todos los estilos (consolidados)
     ui.js               ← Toda la lógica cliente (consolidada)
   ```

2. **Consolidar CSS:**
   - Mover estilos `:root` (variables, colores, tipografía)
   - Mover definiciones de componentes (`.card`, `.button-stack`, `.hrv-summary-*`, etc.)
   - Mover media queries
   - Eliminar redundancias (`border-radius: 8px` hardcodeado + `var(--radius-xl)`)

3. **Consolidar JS:**
   - Mover todos los `document.getElementById` a `static/ui.js`
   - Agrupar state y render en funciones coherentes
   - Mantener `fetch` nativo, sin dependencias externas
   - Mantener un puente mínimo para valores Jinja que el JS necesita en runtime (`templates/partials/ui_runtime_config.html` expone `UI_RUNTIME.sync_timeout_sec`)

4. **Unificar páginas OAuth:**
   - `oauth_success.html` y `oauth_error.html` heredan `ui.css` compartido
   - Consistencia visual con la UI principal (mismos colores, tipografía, radio)

5. **Reemplazar en `web_ui.py`:**
   - Cambiar `render_template_string(HTML_TEMPLATE, ...)` por `render_template('index.html', ...)`
   - Convertir los **f-strings + `.replace()`** de los endpoints OAuth (no son `render_template_string`; ver hallazgo H3) a `render_template('oauth_success.html', ...)` / `oauth_error.html`
   - Borrar `HTML_TEMPLATE`
   - `web_ui.py` delega todo el renderizado HTML a plantillas y conserva solo la lógica backend

### Qué NO se toca

- Lógica backend (estado, OAuth, diagnostics, endpoints)
- Docker, Railway, variables de entorno, configuración
- Build steps, npm, node_modules — **cero cambios de despliegue**
- Framework JS (sigue siendo vanilla fetch)
- Funcionalidad operativa observada
- La UI activa ya no incluye `weeklyCoachCard`; `importBtn` sigue comentado y cualquier limpieza funcional va en tarea aparte

---

## Criterios de aceptación

- [x] Directorios `templates/` y `static/` creados
- [x] `templates/index.html` es equivalente visual/funcional a `HTML_TEMPLATE`
- [x] `static/ui.css` consolida todos los estilos sin duplicación
- [x] `static/ui.js` consolida toda la lógica cliente de forma legible
- [x] `templates/oauth_success.html` y `oauth_error.html` usan `ui.css`
- [x] `web_ui.py` migrado a `render_template()` en todos los endpoints
- [x] `HTML_TEMPLATE` borrado de `web_ui.py`
- [x] `index.html` expone el puente mínimo para `sync_timeout_sec` antes de cargar `ui.js`
- [x] Suite pytest verde con `python -m pytest tests/test_web_ui_status.py tests/test_web_ui_security.py` y tests actualizados al nuevo reparto HTML/JS
- [x] Verificación en navegador: UI funciona igual que antes (todos los botones, polling, estados)
- [x] Diff limpio: cambios solo en archivos nuevos/modificados, no en lógica backend
- [x] Revert simple por commit, sin tocar datos ni runtime

---

## Razón

**Problema actual:** 560 líneas de HTML+CSS+JS dentro de un string Python.

**Síntomas:**
- Sin syntax highlighting ni autocomplete en el IDE
- Tocar UI requiere abrir `web_ui.py` y navegar un string gigante
- CSS sin linting, sin separación clara
- JS sin formateo, sin debugging sencillo
- Diffs confusos cuando cambio frontend

**Solución:** Extraer a archivos reales.

**Ganancia:**
- IDE soporte completo (syntax, autocomplete, linting)
- Edición directa sin tocar backend
- Diffs claros por archivo
- Base limpia para evaluar después si Vue/framework hace falta
- Riesgo operacional bajo (Flask sigue siendo 1 contenedor; requiere actualizar tests CI, ver H0)

**Costo:** ~2-3 horas de extracción + testing.

---

## Notas

- Esta es **Fase 1 (desacople estructural)**. Fases siguientes solo si hace falta:
  - **Fase 2a** — Limpiar JS imperativo si el render manual sigue molestando: agrupar los `getElementById` sueltos, centralizar state/render en funciones coherentes. Sin framework, sin dependencias.
  - **Fase 2b (alternativa a evaluar, fuera de AYO-25)** — HTMX (~14 KB CDN, sin build step): Flask renderiza parciales HTML por panel (`hx-get="/ui/partials/hrv-summary"`), HTMX los inyecta en el DOM. Puede reducir bastante el JS de render, pero añade una dependencia y nuevos parciales/endpoints. Solo evaluarlo si el JS actual vuelve a ser el dolor real. Propuesta separada: [`AYO-25_Fase2_HTMX.md`](AYO-25_Fase2_HTMX.md)
  - **Fase 3** (solo si de verdad hace falta): Vue 3 via CDN.
- No introducir toolchain adicional. `Flask` sirve `templates/` y `static/` de serie.
- Las páginas OAuth quedan visualmente consistentes con `ui.css` compartido (hoy tienen estilos inline sueltos).
- AYO-25 ya no tiene `weeklyCoachCard` en runtime; `importBtn` sigue comentado y no se reactiva dentro de esta tarea.

---

## Referencias

- Análisis de viabilidad completo: [`Evaluacion viabilidad migracion UI a Vue.md`](Evaluacion%20viabilidad%20migracion%20UI%20a%20Vue.md)
- Entrada actual: `web_ui.py`, `templates/data/ui_copy.json.j2`, `templates/data/ui_runtime_config.json.j2`
- Salida: `templates/index.html`, `templates/oauth_success.html`, `templates/oauth_error.html`, `templates/partials/ui_runtime_config.html`, `static/ui.css`, `static/ui.js`

---

## Revisión de la tarea (histórica, validada con código — 2026-06-23)

Revisión sobre `web_ui.py` previa a la extracción. Cada hallazgo está justificado con la línea exacta. El veredicto del alcance se mantiene; lo que sigue son **trampas técnicas** que la tarea original no contemplaba y **correcciones factuales** que se mantuvieron como referencia histórica.

### Bloqueante: CI

**H0 — La extracción rompe `test_index_exposes_weekly_coach_panel_shell`. ALTO.**
`tests/test_web_ui_status.py:55,58` assertan que el HTML de `GET /` contiene los nombres de funciones JS `renderHrvSummaryPanel` y `renderWeeklyCoachPanel`. En cuanto el JS se mueve a `static/ui.js`, esos strings dejan de aparecer en el HTML → el test falla.
Además, `tests/test_web_ui_security.py` exige substrings concretos en las páginas OAuth: `"Estado OAuth"` (l.60), enlace `"/auth"` (l.144,152), ausencia de `"provider="` (l.145,153), ausencia de tokens (l.119-120). Las plantillas Jinja deben conservar esos literales.
**Acción:** actualizar los asserts del test de index (reapuntar a estructura HTML o verificar que `ui.js` se carga con `<script src=>`), y validar que las plantillas OAuth conservan los literales que los tests de seguridad exigen.

### Trampas técnicas

**H2 — Jinja embebido en el JS. ALTO.**
`web_ui.py:1382` → `const syncTimeoutSec = Number('{{ sync_timeout_sec }}') || 1200;`
Flask **no** procesa Jinja en archivos de `static/`. Si todo el JS se mueve a `static/ui.js`, ese `{{ sync_timeout_sec }}` queda literal → `Number('{{...}}')` = `NaN` → siempre cae al fallback `1200`, ignorando `HRV_SYNC_TIMEOUT_SEC`. No es catastrófico (hay fallback y el subprocess tiene su propio timeout) pero la config deja de tener efecto en el poll de la UI.
**Puente mínimo:** en `index.html`, antes de cargar `ui.js`, una línea inline:
`<script>window.SYNC_TIMEOUT_SEC = {{ sync_timeout_sec }};</script>` y que `ui.js` lea `window.SYNC_TIMEOUT_SEC`. Es el único `{{ }}` dentro de `<script>` (el resto de variables Jinja están en el `<body>` HTML y se quedan en `index.html` sin problema: `hrv_summary_title` 1073, `initial_technical_output` 1109, los `{% if %}` 1111-1112).

### Correcciones factuales (aplicadas arriba)

**H3 — Las páginas OAuth NO usan `render_template_string`.**
Usan **f-strings con `escape()`** (`web_ui.py:1700-1747`) y un string + `.replace()` para la de éxito (`success_html` en 1762, `success_html.replace("__TOKEN_NOTICE__", token_notice)` en 1860). Migrarlas a `render_template` implica:
- convertir `{escape(error)}` → `{{ error }}` (Jinja autoescapa solo),
- pasar variables al contexto en vez de interpolar f-string.

**H3b — `__TOKEN_NOTICE__` es código muerto.**
`web_ui.py:1760` fija `token_notice = ""` siempre, y 1837/1860 solo lo sustituyen por vacío. Toda la maquinaria `__TOKEN_NOTICE__` se puede **eliminar** al migrar (simplificación gratis, no añade alcance).

**H4 — La estimación "~870 líneas" de backend resultante era optimista.**
El HTML no es solo `HTML_TEMPLATE` (563 líneas, 870-1432); hay ~140 líneas más de HTML inline en los callbacks OAuth (~1700-1872). Total HTML a extraer ≈ 700 líneas → `web_ui.py` queda en **~1250 líneas**, no 870.

### Limpiezas oportunas (bajas, opcionales, justificadas)

**H5 — Hay UI muerta; la extracción es el momento de decidir keep/drop.**
- `renderWeeklyCoachPanel` está **definida** (1150-1176) pero su llamada está **comentada** (`web_ui.py:1266` → `/*renderWeeklyCoachPanel(data);*/`). Resultado: `weeklyCoachCard` (1094-1106) nace `hidden` y nunca se muestra. El backend sí computa `_weekly_coach_diagnostics()` y lo manda en el payload → trabajo que la UI descarta.
- El botón `importBtn` está **comentado** en el HTML (`web_ui.py:1111`) pero `importSeedCsvs()` (1307) y las referencias en `applyUiState` (1250, 1260) siguen vivas con guardas `if (importBtn)`.

**Decisión de scope para AYO-25:** H5 queda **fuera** de esta tarea. La extracción debe preservar el comportamiento actual y limitarse a mover archivos y adaptar tests. Si se quiere activar o eliminar esta UI inactiva, abrir tarea separada.

**H6 — Pequeñas suciedades CSS (triviales).**
- `static/ui.css:107` → ya no hay `xxxbox-shadow`; quedó resuelto y solo permanece `box-shadow` real en estilos activos.
- Estilos inline sueltos (`style="margin-top: 14px;"` en 1110) que pueden ir a `ui.css`.
- `border-radius: 8px` hardcodeado coincide con `--radius-xl: 8px` (896): unificar a la variable.

**H7 — Caché de estáticos tras deploy.**
Flask sirve `/static/` con cabeceras de caché propias; el JS/CSS inline actual nunca se cachea por separado. Tras un deploy podría servirse `ui.js`/`ui.css` viejo. Para N=1 es trivial (hard refresh), pero es un cambio de comportamiento a tener en cuenta. No requiere acción ahora; solo documentar que existe.

### Conclusión de la revisión

La tarea es correcta y de riesgo bajo. El único bloqueante real es **H0** (CI): la extracción rompe un test existente que hay que actualizar. **H2** (Jinja en JS) requiere un puente mínimo. H3/H4 corrigen la descripción para que el ejecutor no busque un `render_template_string` OAuth que no existe ni espere un recuento de líneas irreal. H5 se difiere deliberadamente para no mezclar refactor estructural con cambio funcional. H6/H7 son limpiezas menores. No se justifica nada más allá de esto: sin framework, sin build, sin abstracciones nuevas dentro de AYO-25.
