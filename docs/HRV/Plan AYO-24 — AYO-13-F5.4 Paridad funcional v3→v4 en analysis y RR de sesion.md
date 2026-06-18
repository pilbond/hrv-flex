
Estado: **EN CURSO / implementación mínima completada** — 2026-06-17  
Objetivo padre: `AYO-13 Migrar Polar AccessLink de v3 a v4`  
Depende de: `AYO-23 AYO-13-F5.3 Consolidar runtime v4 y aislar legado v3`  
Bloquea: `AYO-22 AYO-13-F6 Retirada v3 y limpieza`

### Avance 2026-06-17

Se completó el primer corte funcional mínimo de la tarea:

- `hrv_app/polar_sessions.py` ya expone un helper v4 reutilizable para RR de
  sesión (`fetch_session_rr_v4`) sobre el stack existente
  `V4Client + polar_adapters_v4 + match_polar_exercise`,
- `analysis/session_analysis_pipeline.py` ya dejó de degradar
  sistemáticamente en `POLAR_API_VERSION=v4|shadow` y ahora usa una ruta real
  para generar `session_rr.csv`,
- la rama legacy `v3` de `fetch_session_rr_csv()` se conserva intacta mientras
  siga existiendo F6,
- la cobertura mínima de contrato quedó añadida en tests para:
  - éxito v4 con RR exportable,
  - ausencia real de RR exportable,
  - compatibilidad de `shadow` con la misma ruta v4,
  - mantenimiento del error v3 cuando falta token.

Validación ejecutada en este corte:

- `python -m pytest tests/test_polar_sessions_v4.py tests/test_analysis_contract.py -q`
- resultado: `156 passed`

Validación operativa real adicional ejecutada:

- `prepare_bundle()` + `run_analysis()` en directorios temporales sobre
  sesiones reales del dataset:
  - `i154959530` → `2026-06-07_08-06_trail_run_i154959530`
  - `i154746574` → `2026-06-06_08-01_bike_i154746574`
- resultado en ambos casos:
  - `rr_csv` generado,
  - `rr_error = null`,
  - `rr_path` presente en `summary/session_payload`,
  - sin degradación a `rr_unavailable`.

Interpretación:

- la brecha principal de paridad funcional queda cerrada a nivel de código,
  contrato local y validación operativa básica con sesiones reales,
- con esta comprobación AYO-24 puede considerarse técnicamente cerrada y deja
  desbloqueado el gate funcional previo a F6.

---

## 1. Decisión de producto

Esta tarea nace de una decisión explícita:

- **RR no se abandona.**
- **Todo lo que funciona en v3 y sigue teniendo valor operativo debe seguir
  funcionando en v4.**
- Esta regla aplica a toda la app, no solo a `analysis/`.

En la práctica, el hueco funcional detectado y no resuelto por `AYO-23` es:

- `analysis/session_analysis_pipeline.py` ya no recupera RR de sesiones de
  entrenamiento cuando el runtime está en `v4`; hoy degrada a `rr_unavailable`
  de forma controlada.

Esa degradación fue útil para consolidar el runtime, pero no satisface el
objetivo final de paridad funcional.

---

## 2. Objetivo concreto

Restaurar en `v4` la capacidad que existía en `v3` para `analysis`:

- localizar la sesión Polar equivalente,
- obtener sus samples RR,
- generar el CSV RR de sesión,
- alimentar el análisis completo sin caer en `rr_unavailable` cuando en `v3`
  sí había RR exportables.

El objetivo no es "mejorar" `analysis`, sino cerrar la brecha de paridad
funcional antes de ejecutar `F6`.

---

## 3. Regla de alcance

### 3.1 Dentro de alcance

- `analysis/session_analysis_pipeline.py`
- frontera de sesiones Polar usada por `analysis`
- adaptadores v4 necesarios para RR de sesiones
- tests de paridad `v3`/`v4` para el flujo de análisis con RR
- documentación operativa de la migración Polar en lo relativo a esta
  capacidad

### 3.2 Fuera de alcance

- retirar `v3`
- rediseñar el método analítico
- cambiar outputs canónicos globales
- cambiar la política de RR matinales nuevos desde Dropbox
- introducir nuevas métricas v4 no existentes en `v3`

---

## 4. Estado actual y gap exacto

Hoy el stack v4 ya tiene piezas técnicas relevantes:

- `hrv_app/polar_client_v4.py` puede listar `training-sessions` con
  `features`
- `hrv_app/polar_adapters_v4.py` ya adapta RR samples a shape interno
  compatible con el consumidor legado
- `hrv_app/polar_sessions.py` ya tiene backend v4 por fecha para sesiones
  mecánicas

Pero `analysis` no consume aún esa frontera. En su lugar:

- si `POLAR_API_VERSION == "v3"`, sigue usando la ruta legacy de RR de sesión
- si `POLAR_API_VERSION != "v3"`, falla a propósito y degrada el informe

Eso significa que la limitación no es de producto Polar demostrada en el repo,
sino de cableado pendiente en la app.

---

## 5. Estrategia recomendada

La estrategia correcta es **reusar la frontera v4 ya creada para sesiones**,
no inventar un tercer cliente paralelo dentro de `analysis`.

Principios:

1. `analysis` no debe volver a hablar directamente con el stack OAuth/client
   legacy.
2. La resolución de sesiones y de RR debe pasar por una frontera v4 reutilizable.
3. La salida para `analysis` debe seguir siendo el shape/artefacto interno que
   el pipeline ya entiende hoy.
4. La validación debe ser de **paridad funcional**, no solo de "no crashea".
5. La autenticación y el refresh v4 deben seguir resueltos por
   `hrv_app/polar_auth_v4.py` y `hrv_app/polar_client_v4.py`; `analysis` no
   debe introducir una segunda vía de OAuth ni gestionar tokens por su cuenta.
6. Debe prevalecer la solución más simple y eficiente: sin nuevas capas
   genéricas, sin flags permanentes extra y sin dejar dependencias transitorias
   como condición del estado final.

---

## 6. Plan de ejecución

### Paso 1 — Exponer helper reutilizable de RR de sesión sobre la frontera v4 existente

El repo ya tiene la base técnica en:

- `hrv_app/polar_client_v4.py`
- `hrv_app/polar_adapters_v4.py`
- `hrv_app/polar_sessions.py`

Por tanto, el trabajo aquí no debería crear una frontera nueva, sino exponer
un helper de conveniencia reutilizable desde `hrv_app/` para:

- listar sesiones v4 por fecha con `features`
- matchear la sesión esperada
- obtener RR en shape interno compatible

La implementación debe vivir en `hrv_app/`, no dentro de `analysis/`, y debe
reusar explícitamente el stack de autenticación/token v4 ya existente.

Regla sobre flags:

- si hoy la ruta v4 reutilizable depende de `POLAR_V4_SESSIONS=1`, AYO-24 debe
  resolver esa dependencia de la forma más simple posible para que el resultado
  final no quede atado a un flag transitorio
- el estado objetivo no es "v4 funciona si además activo un flag especial",
  sino "v4 cubre por defecto lo que antes cubría v3"

### Paso 2 — Migrar `analysis` a esa frontera

Sustituir la rama legacy de `fetch_session_rr_csv()` por una ruta v4 real,
manteniendo el contrato actual:

- escribe `rr_csv` con el contrato actual (`duration,offline`)
- devuelve las mismas claves observables que hoy consume el pipeline:
  `polar_exercise_id`, `polar_start_delta_min`, `polar_duration_gap_min`,
  `rr_count`, `offline_pct`
- solo cae a error cuando realmente no haya RR exportables o el match falle

Paridad esperada:

- no hace falta exigir identidad binaria absoluta entre payloads v3 y v4
- sí hace falta preservar el mismo comportamiento operativo observable:
  recuperación de RR, artefacto consumible, informe completo y ausencia de
  `rr_unavailable` cuando en v3 el caso era resoluble

### Paso 3 — Mantener compatibilidad v3 mientras exista F6

Hasta que F6 retire v3:

- `v3` debe seguir funcionando como hoy
- `v4` debe alcanzar la misma capacidad funcional
- la comparación entre ambos debe ser posible en tests/fixtures

Restricción de implementación:

- no introducir dispatchers complejos, capas de estrategia ni abstracciones
  permanentes por esta transición
- un branching simple `if version == "v3": ... else: ...` es suficiente
- `shadow`, mientras exista, debe comportarse como rama v4 a efectos de esta
  capacidad; no debe abrir una tercera implementación independiente

### Paso 4 — Cerrar tests de paridad

Prerequisito explícito:

- capturar o validar una sesión de referencia con RR disponibles y fixtures
  comparables entre `v3` y `v4`
- fijar ese artefacto como base estable de los tests de paridad

Añadir tests que prueben, como mínimo:

- `v4` genera RR de sesión cuando los samples existen
- `v4` produce un artefacto consumible por el pipeline analítico actual
- el informe resultante no cae en `rr_unavailable` en casos donde `v3` sí tenía
  RR
- `v3` y `v4` mantienen mismo comportamiento observable para una sesión de
  referencia

### Paso 5 — Actualizar documentación de migración

Actualizar:

- este plan
- `Plan AYO-22`
- `Plan AYO-23`
- `AYO-13 Migrar Polar AccessLink de v3 a v4`
- matriz de paridad si se amplía el gate para incluir RR de sesión en analysis

---

## 7. Criterios de aceptación

La tarea se considera cerrada si se cumple todo esto:

1. En `POLAR_API_VERSION=v4`, `analysis` puede recuperar RR de sesión cuando
   esa sesión los expone y el mismo caso funcionaba en `v3`.
2. `rr_unavailable=True` deja de aparecer como consecuencia sistemática del
   cambio `v3 -> v4`; solo aparece en ausencias reales de RR o errores reales
   de match/datos.
3. El pipeline analítico produce el mismo tipo de informe en `v3` y en `v4`
   para sesiones equivalentes.
4. La implementación no introduce un nuevo stack ad hoc dentro de `analysis`;
   reutiliza la frontera v4 existente en `hrv_app/`.
5. La funcionalidad queda testada con casos explícitos de paridad.
6. `AYO-22` puede asumir que retirar `v3` no deja a `analysis` con menos
   capacidad funcional.
7. La capacidad final en `v4` no depende de un flag transitorio adicional para
   reproducir lo que antes hacía `v3`.

---

## 8. Riesgos y mitigación

### Riesgo 1 — Que el shape RR v4 real no coincida con fixtures

Mitigación:

- capturar o validar primero una sesión de referencia comparable entre `v3` y
  `v4`
- validar contra esos fixtures antes de cerrar la tarea
- si hace falta, ampliar captura real antes de escribir o cerrar los tests de
  paridad

### Riesgo 2 — Duplicar lógica de match entre `analysis` y `polar_sessions`

Mitigación:

- mover la lógica reutilizable a `hrv_app/`
- no copiar/pegar clientes ni adaptadores

### Riesgo 3 — Considerar “paridad” algo solo local de `analysis`

Mitigación:

- dejar explícito que esta tarea nace de una regla general de migración:
  ninguna capacidad operativa útil puede perderse por pasar a `v4`

### Riesgo 4 — Cerrar la tarea con una solución válida solo bajo flags de transición

Mitigación:

- tratar cualquier flag auxiliar actual como mecanismo temporal de cableado, no
  como parte del contrato final
- validar la aceptación contra el estado objetivo: `v3` desaparece y `v4`
  conserva la capacidad útil previa

---

## 9. Relación con F6

`AYO-24` debe cerrarse antes de ejecutar `AYO-22` si se mantiene la decisión
de producto de no perder funcionalidad RR.

Separación correcta:

- `AYO-23` consolidó runtime y aisló legado
- `AYO-24` recupera la paridad funcional faltante en `analysis`
- `AYO-22` retira `v3` cuando ya no existe pérdida funcional pendiente

F6 no debe mezclar paridad nueva con borrado final.

---

## 10. Recomendación final

Esta tarea debe tratarse como **bloqueadora funcional de F6**.

No es cosmética ni opcional:

- si el sistema final en `v4` debe conservar lo que `v3` hacía,
- y `analysis` con RR de sesión es una de esas capacidades,
- entonces esta tarea cierra una brecha real de migración.

En términos prácticos, la interpretación correcta de este plan es:

- hacer la migración con el menor número de piezas nuevas posible
- no aceptar una paridad condicionada a flags transitorios
- dejar a `v4` listo para sustituir a `v3` sin pérdida funcional cuando F6 lo retire
