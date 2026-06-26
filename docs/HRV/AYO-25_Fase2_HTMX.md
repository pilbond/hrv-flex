# AYO-25 Fase 2: Evaluacion e integracion opcional de HTMX

Fecha: 2026-06-24

## Veredicto preliminar

`Go` solo condicional.

HTMX tiene sentido en este repo solo si, tras la extraccion de AYO-25 Fase 1, el dolor principal sigue siendo el render manual en `static/ui.js`.

No tiene sentido introducirlo:

- para rehacer toda la UI por estetica,
- para tocar OAuth,
- para reemplazar una pantalla que ya es estable y pequena,
- ni para abrir una mini-SPA disfrazada.

La oportunidad real de HTMX aqui es reducir JS imperativo en la pantalla principal sin meter build step ni framework cliente pesado.

## Estado de partida

Tras AYO-25 Fase 1, la UI queda separada en:

- `templates/index.html`
- `templates/oauth_success.html`
- `templates/oauth_error.html`
- `static/ui.css`
- `static/ui.js`

El backend sigue en `web_ui.py` y la superficie principal sigue siendo:

- `GET /`
- `GET /api/status`
- `POST /api/sync`
- `POST /api/sync-sessions`
- `POST /api/restore-backup`
- `POST /api/delete-latest-rr`

El principal candidato a simplificacion es la pantalla `/`, no los callbacks OAuth.

Nota operativa: el panel de `weekly coach` ya no forma parte del runtime actual; solo deberia volver a entrar si se recupera de forma explicita.

## Objetivo de Fase 2

Reducir la logica de pintado manual del dashboard principal moviendo fragmentos visuales a parciales Jinja servidos por Flask y actualizados con HTMX.

Objetivo explicito:

- menos `document.getElementById(...)`,
- menos `render*Panel(...)`,
- menos concatenacion manual de strings HTML o texto tecnico,
- mantener `Flask + templates + static`,
- mantener un unico contenedor,
- no introducir Node, build ni frontend separado.

Objetivo no explicito:

- no convertir esto en app multi-vista,
- no reescribir todo el backend,
- no eliminar de golpe todos los endpoints JSON.

## Donde HTMX si encaja

HTMX encaja bien en paneles que cumplen estas condiciones:

- son visibles en la UI principal,
- dependen de `status` o de un subset del payload actual,
- pueden renderizarse como HTML server-side sin logica cliente compleja,
- se refrescan por polling o tras una accion.

En esta app, eso apunta a:

1. resumen HRV
2. detalle tecnico
3. banner o bloque de estado operativo

## Donde HTMX no aporta gran cosa

No lo usaria para:

- paginas OAuth (`oauth_success.html`, `oauth_error.html`)
- confirm dialogs de borrado/restauracion
- countdown de cierre de ventana OAuth
- reglas de bloqueo fino de botones si ya quedan simples en JS

Es decir: HTMX para paneles; JS minimo para interacciones locales.

## Propuesta de arquitectura

### 1. Mantener `index.html` como shell

`index.html` seguiria siendo el marco de la pagina:

- botones principales,
- contenedores vacios o shells,
- carga de `ui.css`,
- carga de HTMX,
- JS minimo solo para confirmaciones locales o algun caso residual.

### 2. Crear parciales HTML

Parciales propuestos:

- `templates/partials/hrv_summary.html`
- `templates/partials/technical_output.html`
- `templates/partials/status_banner.html`
- `templates/partials/weekly_coach.html` solo si se decide reintroducir ese bloque

Cada parcial recibiria un payload ya preparado desde Python.

### 3. Crear endpoints UI de parciales

Rutas candidatas:

- `GET /ui/partials/hrv-summary`
- `GET /ui/partials/technical-output`
- `GET /ui/partials/status-banner`
- `GET /ui/partials/weekly-coach` solo si vuelve a existir ese panel

No sustituyen obligatoriamente a `/api/status`. Pueden convivir con el JSON actual.

### 4. Mantener acciones operativas en POST

Las acciones seguirian siendo:

- `POST /api/sync`
- `POST /api/sync-sessions`
- `POST /api/restore-backup`
- `POST /api/delete-latest-rr`

HTMX dispararia estas acciones y luego refrescaria uno o varios parciales.

## Ejemplo de patron

Shell en `index.html`:

```html
<section
  id="hrv-summary-slot"
  hx-get="/ui/partials/hrv-summary"
  hx-trigger="load, every 30s"
  hx-swap="outerHTML"
>
  Cargando resumen HRV...
</section>
```

Endpoint Flask:

```python
@app.get("/ui/partials/hrv-summary")
def ui_partial_hrv_summary():
    payload = _build_status_payload()
    return render_template("partials/hrv_summary.html", data=payload)
```

Parcial Jinja:

```html
<section id="hrv-summary-slot" class="card hrv-summary-card" {% if not data.diagnostics.final_exists %}hidden{% endif %}>
  {% if data.diagnostics.final_last_fecha %}
    <div class="hrv-summary-title">Lectura HRV de hoy ({{ data.diagnostics.final_last_fecha }})</div>
  {% else %}
    <div class="hrv-summary-title">Lectura HRV de hoy</div>
  {% endif %}
</section>
```

## Estrategia recomendada

No migrar toda la pantalla a la vez.

Orden sugerido:

1. `hrv_summary`
2. `technical_output`
3. `status_banner`
4. solo despues revisar si los botones merecen integracion HTMX o si es mejor dejarlos en JS minimo

`weekly_coach` solo volveria a entrar si se reintroduce ese panel de forma explicita.

Esto permite medir valor antes de tocar toda la superficie.

## JS que podria desaparecer

Si HTMX entra bien, los principales candidatos a simplificacion en `static/ui.js` son:

- `renderHrvSummaryPanel`
- parte de `renderTechnicalOutput`
- parte de `refreshDashboard`
- parte del polling manual ligado a `/api/status`

Lo que probablemente seguiria en JS:

- `confirm()` para borrado/restauracion
- countdown OAuth
- algun pegamento minimo para estados de botones

## Trade-offs frente al estado actual

### Ventajas

- menos JS imperativo manual
- mas presentacion en plantillas Jinja, donde ya vive el HTML
- cambios visuales mas faciles de leer y revisar
- mejor encaje con Flask que un framework cliente completo
- sin build step ni cambio de despliegue

### Inconvenientes

- nueva dependencia de frontend
- mas endpoints HTML o parciales a mantener
- riesgo de repartir demasiado la logica entre:
  - `index.html`
  - atributos `hx-*`
  - parciales Jinja
  - `web_ui.py`
- si se usa sin disciplina, la UI puede acabar mas dispersa que ahora

## Regla de uso para no pasarse

Si entra HTMX, debe entrar con estas restricciones:

- HTML de servidor para paneles, no para todo
- parciales pequenos y con una responsabilidad clara
- no duplicar logica de negocio entre JSON y HTML
- no abrir mas de 3-4 parciales inicialmente
- no tocar OAuth ni flujos fuera de `/`
- si una interaccion es mas simple en JS local, dejarla en JS local

## Contrato tecnico recomendado

### Mantener

- `GET /api/status` como diagnostico JSON util para tests y debugging
- los POST operativos actuales
- `static/ui.css`

### Anadir

- parciales bajo `templates/partials/`
- rutas `GET /ui/partials/*`

### Evitar

- devolver HTML desde endpoints pensados hoy como API JSON
- mezclar HTMX y demasiadas ramas personalizadas en `ui.js`
- crear componentes genericos o abstracciones de frontend innecesarias

## Criterio de decision

### Hacer Fase 2 HTMX si:

- `ui.js` sigue pareciendo el punto mas feo o fragil
- el render manual de paneles sigue creciendo
- tocar UI implica demasiada coordinacion entre HTML vacio + JS + texto manual

### No hacer Fase 2 HTMX si:

- tras Fase 1 la UI ya es suficientemente mantenible
- el JS restante es pequeno y estable
- el dolor ya no esta en el frontend

## Criterios de aceptacion si se ejecuta

- existe una primera migracion parcial, no un big bang
- al menos `hrv_summary` se sirve via parcial HTMX
- la UI sigue funcionando sin cambios de Docker o Railway
- los tests de `web_ui` siguen verdes
- no se toca la logica de negocio HRV
- el diff reduce JS manual en vez de multiplicar capas

## Recomendacion final

La mejor lectura hoy es:

1. cerrar y validar AYO-25 Fase 1
2. revisar si de verdad `static/ui.js` sigue siendo el dolor principal
3. si la respuesta es si, ejecutar una Fase 2 HTMX incremental empezando por `hrv_summary`

HTMX aqui no es mala idea. Solo deja de ser buena idea si se usa para resolver un problema que ya estaba suficientemente resuelto con `Jinja + static + JS minimo`.
