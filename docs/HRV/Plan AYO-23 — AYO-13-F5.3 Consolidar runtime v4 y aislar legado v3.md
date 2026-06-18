# AYO-23 — AYO-13-F5.3 Consolidar runtime v4 y aislar legado v3

Estado: implementada; consolidacion pendiente de cierre fino de alcance (2026-06-17)  
Objetivo padre: `AYO-13 Migrar Polar AccessLink de v3 a v4`  
Bloquea: `AYO-22 AYO-13-F6 Retirada v3 y limpieza`

---

## 1. Resumen ejecutivo

Hace falta una fase intermedia entre `AYO-21 (F5 corte controlado)` y
`AYO-22 (F6 retirada v3)`.

Motivo: hoy el repo ya tiene partes operativas validadas en v4
(`sleep/nightly` por gateway, sesiones mecánicas vía `PolarSessionClient`
bajo flag), pero el runtime general sigue conservando demasiada lógica v3
como comportamiento normal:

- `POLAR_API_VERSION` sigue default a `v3`
- `web_ui.py` sigue dual `v3|v4`
- el registro de usuario v3 sigue vivo
- `polar_oauth_local.py` sigue anclado a v3
- `shadow` sigue siendo modo soportado
- `analysis/session_analysis_pipeline.py` sigue consumiendo `polar_client`
  y `polar_oauth_local` legacy

Eso significa que `AYO-22` mezcla dos tipos de trabajo:

1. cambio operativo real de comportamiento
2. limpieza/borrado de legado

Separarlos reduce riesgo y simplifica rollback.

La prioridad de esta tarea es:

- simpleza del runtime
- utilidad inmediata
- buen funcionamiento

por encima de reordenamientos cosméticos o sobreingeniería.

Actualizacion de alcance (2026-06-17):

- AYO-23 ya deja `v4` como runtime principal y aísla el legado `v3`.
- Lo que sigue encajando en esta tarea son ajustes de consolidacion:
  - mensajes UX/documentacion interna coherentes con `v4` como camino normal
  - tests explicitos de degradacion controlada en `analysis`
  - pequenos refactors para reducir acoplamiento al legado
- No debe absorber trabajo de capacidad nueva. En particular:
- recuperar RR de sesiones de entrenamiento en `analysis` usando `v4`
  no pertenece ya a AYO-23; queda movido a `AYO-24`.

---

## 2. Qué problema resuelve

`F5.2` ya demostró que v4 funciona en integración real para:

- catálogo deportivo (`/v4/data/sports/list`, `sports:read`)
- matching por fecha/deporte
- samples RR
- capa mecánica mínima en deportes de pie con tipos reales (`SPEED`,
  `CADENCE`)

Pero todavía no existe una fase explícita que diga:

- v4 pasa a ser el camino operativo principal
- v3 queda aislado como legado temporal, no como comportamiento normal
- `shadow` deja de formar parte del runtime ordinario
- la UI y los entrypoints ya no “piensan en v3” como default

Sin eso, `F6` sería demasiado grande y con demasiado riesgo.

---

## 3. Objetivo concreto

Dejar el sistema en este estado:

- `v4` es el runtime efectivo por defecto para Polar
- sesiones mecánicas usan v4 cuando la capa está activada
- `web_ui.py` deja de ofrecer un flujo normal dual `v3|v4`
- el registro de usuario v3 sale del camino operativo
- `polar_oauth_local.py` queda explicitamente como legado temporal y fuera del
  camino normal
- `analysis/session_analysis_pipeline.py` deja de depender por imports
  top-level de `polar_client` y `polar_oauth_local` v3
- el código legacy v3 sigue existiendo solo como red de seguridad temporal
  hasta `F6`

No es una tarea para borrar v3. Es una tarea para dejarlo fuera del camino
normal.

Nota de alcance:

- `POLAR_V4_SESSIONS` sigue como opt-in en esta fase. `AYO-23` consolida el
  runtime general en v4 y aísla el legado v3, pero no obliga todavía a que la
  capa de sesiones mecánicas v4 pase a activarse por defecto.
- `AYO-23` no obliga a preservar en `analysis` la antigua capacidad de sacar
  RR de sesiones de entrenamiento desde Polar. Si esa capacidad se considera
  necesaria en el estado final, debe planificarse como trabajo nuevo y no
  mezclarse con esta fase de consolidacion.

---

## 4. Fuera de alcance

Esta tarea NO debe:

- borrar `hrv_app/polar_client.py`
- borrar tests/fixtures v3
- eliminar definitivamente `shadow` del repo
- renombrar bundles/token paths v4
- cambiar outputs canónicos (`CORE`, `FINAL`, `DASHBOARD`, `sleep`,
  `sessions`)
- introducir nueva arquitectura o abstracciones extra
- reimplementar RR de sesiones de entrenamiento sobre Polar v4
- convertir `POLAR_V4_SESSIONS` en el unico backend soportado para sesiones

Eso pertenece a `AYO-22`.

---

## 5. Evidencia actual que justifica la tarea

### 5.1 Situacion residual que justificaba la tarea

- `hrv_app/config.py` mantenia `POLAR_API_VERSION=v3|v4|shadow` con default `v3`
- `web_ui.py` mantenia callback dual y registro de usuario v3
- `polar_hrv_automation.py` arrastraba ramas v3 explicitas
- `analysis/session_analysis_pipeline.py` consumia imports top-level del stack
  v3

Estado tras AYO-23:

- `POLAR_API_VERSION` ya defaulta a `v4`
- `/auth` ya entra en v4 como camino normal
- el legado v3 sigue presente, pero ya no como flujo principal
- `analysis` ya no importa top-level el cliente/oauth v3

### 5.2 Residuo principal detectado en `analysis`

Antes de AYO-23, `analysis/session_analysis_pipeline.py` importaba
`list_exercises`, `get_exercise_with_samples` y `load_tokens` desde módulos
legacy v3.

Tras AYO-23, ese acoplamiento estructural se reduce, pero queda una decision
de producto/alcance pendiente:

- en `v4`, el fetch de RR de sesion degrada de forma controlada
- si se quiere volver a soportar RR de sesiones de entrenamiento sobre `v4`,
  eso ya no es consolidacion: es capacidad nueva y requiere tarea separada

También existen consumidores auxiliares de `polar_oauth_local.py` fuera del
runtime principal:

- `scripts/capture_v4_fixtures.py`
- utilidades en `research/` como `compare_session_streams.py`

No bloquean la tarea, pero cualquier decisión sobre `polar_oauth_local.py`
debe verificar estos scripts de apoyo.

### 5.3 F5 ya validó valor suficiente para cortar runtime

Ya se verificó en real:

- `sports:read` requerido
- `/v4/data/sports/list`
- ids reales resueltos
- shape real del catálogo (`identifier.id`)
- shape real de samples mecánicos (`SPEED`, `CADENCE`)
- extracción mecánica real en sesiones de `road_run` y `trail_run`

Eso da base suficiente para pasar a un runtime “v4 primero”.

---

## 6. Estrategia de abordaje

La estrategia correcta es:

1. **migrar consumidores**
2. **colapsar el default del runtime**
3. **aislar v3**
4. **dejar rollback simple**

No al revés.

Regla práctica:

- primero se elimina a v3 del camino normal
- luego, en `F6`, se borra el código muerto

---

## 7. Plan detallado por pasos

### Paso 0 — Precondición explícita

No arrancar esta tarea hasta que `AYO-21` esté aceptada funcionalmente como
corte v4 válido.

Mínimos:

- catálogo real validado
- sesión mecánica real validada
- flujo `POLAR_API_VERSION=v4` estable

### Paso 1 — Colapsar el runtime normal a v4

Objetivo: dejar de tratar v3 como comportamiento implícito.

Cambios esperados:

- `hrv_app/config.py`
  - cambiar el comportamiento default de `POLAR_API_VERSION` a `v4`
  - conservar temporalmente `v3|shadow` solo como rollback técnico
- `polar_hrv_automation.py`
  - revisar ramas de arranque para que el camino feliz sea v4
  - eliminar del camino normal cualquier exigencia v3 innecesaria
  - revisar explícitamente la dependencia de `do_oauth_flow` y `load_tokens`
    desde `polar_oauth_local`

Criterio de aceptación:

- un sync normal sin flags especiales usa v4
- rollback sigue siendo posible poniendo explícitamente `POLAR_API_VERSION=v3`

### Paso 2 — Simplificar `web_ui.py`

Objetivo: la UI ya no debe presentar v3 como ruta normal.

Cambios esperados:

- `/auth` orientado a v4 por defecto
- mantener `provider=v3` solo como escape temporal si hace falta rollback
- revisar si `_register_polar_user()` sigue siendo necesario en el camino vivo
- limpiar mensajes/status para que el usuario vea v4 como comportamiento estándar

Criterio de aceptación:

- la autorización normal desde UI crea/usa bundle v4
- no hay UX ambigua que sugiera que v3 es el camino recomendado

### Paso 3 — Resolver `polar_oauth_local.py`

Objetivo: decidirlo, no dejarlo ambiguo.

Opciones válidas:

1. migrarlo mínimamente a v4
2. retirarlo del camino normal si ya no se usa

Decisión recomendada por simpleza:

- si todavía se usa en local, migración mínima a v4
- si no se usa, retirarlo en `F6`; en esta tarea basta con dejar claro que no
  bloquea runtime
- revisar también consumidores auxiliares (`scripts/capture_v4_fixtures.py`,
  utilidades en `research/`) antes de tocar su frontera

No merece un rediseño.

### Paso 4 — Aislar `analysis/session_analysis_pipeline.py` del legado v3

Objetivo: que `analysis` deje de depender estructuralmente de imports legacy
v3 en el camino normal.

Cambios esperados:

- dejar de importar `list_exercises`, `get_exercise_with_samples`,
  `load_tokens` desde módulos v3
- si el runtime esta en `v4`, degradar de forma controlada el fetch de RR de
  sesion sin romper el informe
- mantener el comportamiento global del análisis fuera de esa capacidad puntual

Criterio de aceptación:

- analysis sigue funcionando
- ya no depende por imports top-level de `polar_client.py` ni de
  `polar_oauth_local.py` legacy
- existe test explicito del caso `v4 -> no RR de sesion -> informe usable`

### Paso 5 — Sacar `shadow` del runtime ordinario

Objetivo: `shadow` deja de ser modo operativo normal y pasa a ser solo
instrumentación temporal o residual.

Cambios esperados:

- dejar de promocionar `shadow` como estado normal del sistema
- si sigue siendo útil, tratarlo como herramienta diagnóstica excepcional
- evitar que la lógica principal siga condicionada por esa tercera rama

Criterio de aceptación:

- el camino feliz del runtime es binario: v4 normal, v3 solo para rollback
- `POLAR_V4_SESSIONS` puede seguir separado como opt-in temporal sin impedir
  que el runtime general ya sea v4-first

### Paso 6 — Documentación de consolidación

Actualizar:

- `AGENTS.md`
- `docs/contracts/GUIA_PYTHON_SCRIPTS.md`
- `docs/contracts/ENDURANCE_HRV_Sessions_Schema.md`
- docs HRV operativas afectadas

Objetivo:

- reflejar que v4 es el runtime principal
- dejar v3 como legado temporal pre-F6

---

## 8. Criterios de aceptación de la tarea

La tarea se considera cerrada si se cumple todo esto:

1. `v4` es el comportamiento por defecto del runtime Polar.
2. La UI web autoriza y opera en v4 como camino normal.
3. `analysis/session_analysis_pipeline.py` deja de depender de módulos legacy v3.
4. `shadow` ya no forma parte del flujo operativo normal.
5. Sigue existiendo rollback simple a v3 durante un ciclo.
6. No cambian outputs canónicos ni semántica de producto.
7. La solución es más simple de operar que antes.

---

## 9. Riesgos y mitigación

### Riesgo 1 — Romper rollback demasiado pronto

Mitigación:

- no borrar v3 aquí
- mantener flag explícito de vuelta temporal
- documentar rollback de un ciclo

### Riesgo 2 — Cambiar demasiado `web_ui.py`

Mitigación:

- tocar solo routing OAuth y mensajes
- no rediseñar UI
- no mezclar endurecimientos ajenos

### Riesgo 3 — Analysis introduce dependencia escondida

Mitigación:

- migrar `analysis/session_analysis_pipeline.py` en esta fase
- validar explícitamente ese flujo

### Riesgo 4 — Expandir alcance por bike/swim/etc.

Mitigación:

- no ampliar contrato de la capa mecánica
- mantener foco en consolidar v4, no en nuevos deportes

### Riesgo 5 — Reintento persistente del catálogo

Si `list_sports()` falla de forma continua, `_v4_sport_catalog` permanece
`None` y el cliente vuelve a intentarlo por cada fecha nueva procesada. En uso
normal el coste es pequeño, pero en `--all` sobre históricos largos puede
generar una serie lineal de intentos contra un endpoint caído.

Mitigación propuesta, si llega a ser relevante:

- añadir un `cooldown` o timestamp de último fallo por instancia
- evitar backoff complejo salvo evidencia operativa
- conservar el comportamiento simple por defecto para N=1

### Riesgo 6 — Aplanado de samples mecánicos en sesiones multibloque

`_v4_mechanical_samples_to_v3()` concatena las muestras de todos los ejercicios
del item en una sola serie. Para las sesiones reales validadas en este repo
eso es suficiente, pero en un futuro con sesiones multibloque (brick,
transiciones) se perdería separación entre ejercicios.

Mitigación propuesta:

- documentarlo como límite actual
- no tocarlo mientras el alcance siga siendo N=1 y sesiones simples
- si aparece un caso real multibloque, reevaluar antes de refactorizar

---

## 10. Relación con F6

Cuando esta tarea termine, `AYO-22` queda reducido a lo que debería ser:

- borrar código legacy v3
- borrar tests/fixtures v3
- retirar `shadow`
- limpiar variables/constantes/documentación residual
- decidir y ejecutar el corte final del doble stack en OAuth/status/sesiones

Y queda fuera de `F6`, salvo decision explicita en contra, esta pregunta:

- `AYO-24` debe cerrar la paridad funcional de RR de sesion en `analysis`
  antes de `F6`.

Si se quiere conservar esa capacidad, debe abrirse una tarea nueva y cerrarse
antes o en paralelo a `F6`, pero no mezclarse dentro de la propia retirada.

Es decir:

- `AYO-23` = consolidar runtime v4
- `AYO-22` = retirar legado v3
- `AYO-24` = paridad funcional de `analysis` y RR de sesion en v4

Esa separación es la forma más simple y segura de terminar la migración.

---

## 11. Recomendación final

La fase ya ha cumplido su objetivo principal: dejar `v4` como runtime normal y
aislar `v3` como legado temporal.

Lo unico que merece seguimiento dentro de AYO-23 es:

- cerrar incoherencias menores de mensajes/documentacion interna
- dejar tests explicitos del comportamiento degradado en `analysis`

Cualquier trabajo para recuperar RR de sesion en `v4` debe abrirse aparte.
