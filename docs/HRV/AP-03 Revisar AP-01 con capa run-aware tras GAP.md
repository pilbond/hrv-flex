## AP-03 Revisar AP-01 con capa run-aware en sombra tras GAP y terrain_climbs

Nota de desarrollo: [[AP-03 Revisar AP-01 con capa run-aware en sombra tras GAP y terrain_climbs]]

## Objetivo

Evaluar si la v1 de `AP-01` gana valor en `trail_run` al enriquecer el clustering con la capa de terreno ya disponible (`FP-02` + `SYA-12`).

La tarea es de validacion retrospectiva y `forward-only`: no reescribe el historico, no toca el gate HRV y no sustituye la v1 salvo evidencia clara.

## Scope

- In scope: `trail_run`.
- Out of scope: `road_run` y `bike` hasta que exista cobertura suficiente y estable.
- Señales candidatas: `terrain_fit_context` / `terrain_context` primero; `run_power_mean` y `power_ratio` solo como apoyo si estan disponibles.

## Preguntas a resolver

1. La capa de terreno mejora la deteccion de clustering reciente en `trail_run` frente a `intensity_category` sola?
2. La mejora supera o solo replica la informacion ya capturada por `load_3d`, `ACWR`, `monotony` y `strain`?
3. Hay suficiente lift para justificar una capa paralela en sombra, o conviene dejar `AP-01` intacta?

## Entrega esperada

- Informe comparativo v1 vs candidata run-aware, separado por `trail_run`.
- Decision explicita: mantener v1, abrir capa paralela en sombra, o descartar.
- Si no hay evidencia suficiente, no tocar `reason_text`, `sessions_day.csv` ni el contrato operativo.

## Criterio de arranque

Empezar por construir la tabla de evaluacion retrospectiva sobre `trail_run` y medir paso `VERDE -> no-VERDE` a `24-48h`, lift vs baseline y solapamiento con el contexto de carga.

## Contexto historico

Esta tarea sustituyo la lectura inicial de AP-03, que contemplaba `road_run` como posible caso de estudio. El bloque de revision de estado de `2026-04-23` desplaza el foco hacia `trail_run`, porque:

- `FP-02 GAP-01` ya esta `green`.
- `SYA-12 TYM-03 FP-05` ya aporta `terrain_climbs.csv` y `terrain_intervals.csv` para `trail_run` y `road_run`.
- `DO-01` y `DO-02` ya cubren parte del hueco de contexto semanal de intensidad.
- `road_run` sigue con cobertura demasiado baja para `run_power` como base decisoria.

La conclusion operativa es mantener `AP-01` v1 intacta y estudiar una capa paralela en sombra solo si el backtest sobre `trail_run` muestra mejora real.

## Como se interpreta el resultado

La comparacion que produce AP-03 no busca decidir si la sesion fue dura o facil, porque esa lectura ya la cubre AP-01 v1. Lo que busca es responder a una pregunta mas concreta: `la capa run-aware esta contando la misma historia que la v1 o esta cambiando el umbral de activacion?`

- `v1_snapshot` representa la decision minima de AP-01 v1 para ese dia.
- `runaware_context` representa la propuesta en sombra.
- `runaware_context.strength_basis` explica por qué la sombra quedó en `strong` o en `exploratory`; no obliga a adivinarlo leyendo el código.
- `runaware_context.runaware_severity_basis` hace lo mismo para `runaware_severity_candidate`: deja claro qué umbral empuja a `high` o a `low`.
- `v1_shadow_comparison` dice si ambas capas coinciden o discrepan.
- `v1_shadow_history` muestra si esa coincidencia se mantiene en el tiempo o si la sombra se aparta sistematicamente.

En otras palabras: la concordancia historica no mide intensidad, mide alineacion de criterio. Si la sombra activa mas que la v1, puede estar capturando terreno real o puede estar abriendo demasiado el grifo. Esa diferencia solo se ve mirando acuerdo, no mirando una sola sesion.

## Valor aportado por AP-03

AP-03 no cambia el contrato HRV canonico, pero si aumenta de forma clara la calidad del analisis de sesiones a pie, sobre todo en `trail_run`.

1. Añade lectura especifica de terreno y subida que antes no estaba integrada de forma util en la interpretacion:
   - `terrain_context`
   - `terrain_fit_context`
   - coste cardiovascular por climb
   - ritmo vertical y potencia del tramo dominante cuando existen

2. Evita relatos erroneos en trail:
   - no toda sesion `trail_run` se interpreta ya como sesion de cuestas
   - una ruta llana o rodadora deja de narrarse como desnivel relevante
   - la durabilidad deja de leerse ingenuamente como drift cuando el terreno explica la forma de la curva

3. Introduce una capa `run-aware` auditable en sombra:
   - `runaware_intense_candidate`
   - `runaware_severity_candidate`
   - `runaware_candidate_basis`
   - `strength_basis`
   - `v1_snapshot`
   - `v1_shadow_history`

4. Mejora la explicacion del coste:
   - mejor separacion entre coste cardiometabolico y mecanico
   - mejor lectura de trail tecnico frente a trail llano
   - mejor tratamiento de sesiones mixtas o de bajo estimulo

5. Mejora la calidad narrativa del informe:
   - menos jerga interna de implementacion
   - menos texto criptico
   - mas trazabilidad sin obligar al lector a conocer el codigo

## Limites de AP-03

AP-03 sigue siendo una capa exploratoria y de validacion, no una norma nueva del sistema.

- no sustituye el gate HRV
- no modifica `sessions_day.csv` como contrato operativo
- no convierte la sombra en verdad canonica
- no demuestra por si sola precision predictiva si faltan outcomes del dia siguiente
- su lectura historica sigue siendo orientativa cuando `N` es bajo o el alcance de v1 y la sombra no es exactamente el mismo

## Siguiente fase recomendada

La siguiente fase no es anadir mas complejidad por defecto, sino validar si esta capa merece promotion parcial o si debe seguir solo como soporte analitico.

1. ampliar historico con mas `trail_run` comparables
2. contrastar la sombra con outcomes del dia siguiente cuando existan
3. revisar lift real, no solo divergencia o tasa de activacion
4. decidir si la capa `run-aware` debe:
   - seguir en sombra
   - informar el informe analitico sin tocar el gate
   - o escalar a una revision formal de AP-01
