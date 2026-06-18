# Evaluación de viabilidad: migrar la UI a Vue

Fecha: 2026-06-17

## Veredicto

`No-Go` por ahora.

La UI actual no justifica una migración a Vue como primera jugada. El problema principal no parece ser de framework, sino de empaquetado: hoy la UI vive embebida en `web_ui.py` dentro de `HTML_TEMPLATE`, mezclando HTML, CSS y JS en un único string. Eso penaliza mantenimiento, pero no implica que falte capacidad técnica en el frontend.

Con el estado actual del repo, Vue sería razonable solo si aparece alguna de estas señales:

- crecimiento claro de la UI a varias vistas o flujos,
- más componentes con estado local reutilizable,
- formularios más complejos,
- necesidad real de composición y no solo de separación de archivos.

Ahora mismo la superficie es pequeña:

- un único entrypoint,
- 6-7 endpoints REST,
- polling simple de `/api/status`,
- bloqueo de acciones concurrentes,
- unas pocas tarjetas visuales y botones de acción,
- cero necesidad aparente de routing, SSR o estado global.

Conclusión directa: migrar a Vue hoy tiene más coste estructural que retorno funcional.

## Qué haría en su lugar

La alternativa correcta y más simple es:

1. extraer el HTML a `templates/index.html`,
2. extraer CSS a `static/ui.css`,
3. extraer JS a `static/ui.js`,
4. mantener `Flask` sirviendo la misma UI y los mismos endpoints,
5. seguir usando `fetch` nativo y estado local en memoria del navegador.

Eso resuelve casi todo el dolor real:

- deja de haber un string Python de ~500 líneas,
- mejora legibilidad y edición,
- separa responsabilidades sin tocar backend,
- no añade pipeline JS,
- no cambia Docker ni Railway,
- mantiene un único contenedor,
- reduce el coste de futuros cambios.

Mi recomendación honesta es: haz eso y para.

## Go / No-Go

### `No-Go` ahora

Razones:

- el frontend no tiene suficiente complejidad para justificar framework,
- no hay evidencia de problemas de reactividad, routing o composición,
- introducir Vue desde cero también introduce decisiones de estructura, build y serving,
- el proyecto es `N=1`, sin presión de equipo frontend, escalado de UI ni producto multiusuario,
- el backend actual ya encaja bien con una UI estática servida por Flask.

### `Go` solo condicional

Vue tendría sentido si, después de extraer a archivos, la UI sigue degradándose y aparecen síntomas concretos:

- duplicación fuerte de lógica DOM,
- crecimiento a múltiples paneles con ciclos de vida propios,
- demasiados `document.getElementById(...)`,
- lógica de estado difícil de seguir,
- widgets reutilizables con variaciones.

Si no aparecen esas señales, Vue sigue siendo sobrecoste.

## Plan mínimo viable por fases

## Fase 1. Separar archivos sin cambiar paradigma

Qué se hace:

- mover la plantilla a `templates/index.html`,
- mover estilos a `static/ui.css`,
- mover JS a `static/ui.js`,
- sustituir `render_template_string(...)` por `render_template(...)`,
- mantener los mismos IDs, `fetch`, polling y comportamiento.

Qué se gana:

- mantenimiento mucho más sencillo,
- diff más limpio,
- edición mejor soportada por el IDE,
- posibilidad de tocar frontend sin entrar en un string Python,
- cero coste extra de despliegue.

Criterio de stop:

`Ya está` si el objetivo era hacer la UI mantenible sin cambiar arquitectura.

## Fase 2. Limpiar JS imperativo si sigue molestando

Qué se hace:

- agrupar el código en un pequeño módulo de UI,
- centralizar un `state` local mínimo,
- encapsular renderizado en funciones puras pequeñas,
- mantener `fetch` nativo y sin framework.

Qué se gana:

- menos acoplamiento entre polling, botones y render,
- lógica más fácil de leer,
- base limpia para decidir después si Vue hace falta.

Criterio de stop:

`Ya está` si la UI queda clara y estable sin necesidad de reactividad declarativa.

## Fase 3. Solo si de verdad hace falta: Vue mínimo

Qué se hace:

- montar Vue 3 en cliente sobre un único `#app`,
- mover el estado local de botones, banners, resumen HRV y coach semanal a reactividad Vue,
- mantener llamadas REST exactamente igual,
- seguir sirviendo todo desde Flask.

Qué se gana:

- template declarativo,
- menos manipulación manual de DOM,
- componentes simples para paneles concretos,
- mejor legibilidad si la UI ya creció.

Criterio de stop:

`Ya está` cuando la UI tenga 2-4 componentes claros y el código sea más simple que antes. Si empiezan a aparecer stores, composables genéricos, router o capas extras, ya te pasaste.

## Stack mínimo recomendado

Si no migras: `Flask + templates/static + fetch nativo`.

Si migras a Vue:

- `Vue 3 via CDN`, no `Pinia`, no `Vue Router`, no SSR, no TypeScript obligatorio,
- un único archivo `static/ui.js`,
- componentes mínimos solo si mejoran claridad,
- build step solo si aparece una necesidad concreta, no por estética.

## Qué no recomiendo

No recomiendo empezar por:

- `Vue SFC + Vite` como primera fase,
- frontend separado en otro servicio,
- SPA completa,
- store global,
- testing frontend dedicado,
- toolchain Node solo para una pantalla simple.

Para este repo, `Vue via CDN` es más coherente que `Vite + SFC` si insistes en Vue, porque:

- evita añadir una cadena de build nueva,
- mantiene Docker simple,
- elimina menos riesgo operacional en Railway,
- encaja mejor con una sola página y un usuario.

`Vite + SFC` solo tendría sentido si decides que el frontend ya es un subproyecto real y va a seguir creciendo.

## Despliegue

La opción correcta es seguir con un solo contenedor.

Modelo recomendado:

- Flask sirve `templates/` y `static/`,
- Docker sigue arrancando `python web_ui.py`,
- Railway sigue desplegando exactamente igual,
- no separar frontend y backend en servicios distintos.

Si hubiera Vue CDN:

- el HTML se sirve desde Flask,
- el script Vue también se carga en esa página,
- todo sigue en el mismo contenedor.

Si en el futuro hubiera `Vite`:

- compilar a una carpeta estática,
- Flask sirve el build generado,
- seguir en un solo contenedor.

Pero ese paso no está justificado hoy.

## Riesgos reales

Si metes Vue antes de tiempo:

- añades complejidad de proyecto sin resolver el problema principal,
- introduces una toolchain JS que hoy no existe,
- mezclas Jinja y Vue si no delimitas bien responsabilidades,
- haces más frágil el deploy para una app que hoy es operativamente simple,
- acabas reescribiendo código estable por una mejora cosmética.

Si haces la extracción simple:

- el riesgo es bajo,
- el backend no cambia,
- el comportamiento observable debería permanecer igual,
- el rollback es trivial.

## Qué no hacer

- no separar backend y frontend en dos despliegues,
- no meter `Pinia`, `Vue Router` o SSR,
- no convertir esto en una SPA si sigue siendo una sola pantalla operativa,
- no introducir Node en producción solo por “hacerlo moderno”,
- no reescribir toda la UI de una vez sin pasar antes por extracción a archivos.

## Recomendación final

La decisión pragmática es:

1. extraer la UI del string Python a archivos reales,
2. mantener `fetch` nativo,
3. revaluar después.

Si tras esa limpieza sigues notando dolor de mantenimiento, entonces sí: `Vue 3 via CDN` como segunda fase, no antes.

En este estado del proyecto, Vue no es una mala tecnología; simplemente no es la primera palanca que más valor da.
