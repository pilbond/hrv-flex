
## Objetivo

Diseñar una capa analitica para evaluar **eficiencia contextual** en `road_run` y `trail_run` comparando `potencia`, `GAP`, `pendiente` y `FC` sobre tramos homogeneos o climbs comparables.

La idea no es introducir una metrica global ingenua de "eficiencia" a nivel sesion completa, sino abrir una lectura contextual que permita distinguir mejor entre:

- deterioro mecanico real,
- deriva cardiovascular,
- terreno mas favorable en la segunda mitad,
- y fatiga de repeticion en sesiones estructuradas.

## Por que esta tarea tiene sentido

Hoy ya existen en `analysis` varias piezas que apuntan al problema, pero no una senal explicita que lo resuelva:

- `power_ratio`
- `speed_ratio`
- `decoupling`
- `terrain_context`
- `terrain_fit_context`
- `terrain_intervals.csv`
- `terrain_climbs.csv`

El problema es que esas piezas, leidas de forma agregada, no bastan para afirmar "eficiencia mejor/peor" en trail o run con relieve variable.

Ejemplo tipico:

- `power_ratio` bajo
- `speed_ratio` estable o incluso > 1

Eso puede significar:

- perdida de output bajo fatiga,
- tramo final mas favorable,
- mejor ejecucion tactica,
- o mezcla de subidas y bajadas que invalida la comparacion global.

Por tanto, hablar de eficiencia exige una comparacion mas estable entre:

- `potencia`
- `velocidad` o mejor `GAP`
- `pendiente`
- `FC`

y, cuando sea posible, tambien:

- `cadencia`

## Problema que esta tarea debe resolver

En sesiones de `road_run` y sobre todo `trail_run`, una media de sesion o una simple particion por mitades no distingue bien entre:

1. producir menos potencia porque hay fatiga periferica real,
2. producir menos potencia porque el terreno permite sostener la velocidad con menos coste,
3. mostrar `decoupling` alto por distribucion de bloques o de relieve y no por deriva lineal continua,
4. perder repeatability en subidas o repeticiones sin que eso sea exactamente "durability" clasica.

La tarea debe responder a esta pregunta:

> Se puede construir en `analysis` una lectura reproducible de eficiencia contextual en carrera usando comparaciones entre tramos equivalentes, sin promoverla todavia a contrato canonico?

## Por que en analysis y no en sessions.csv

- `sessions.csv` esta pensado para una fila estable por sesion.
- La eficiencia contextual requiere comparaciones entre tramos, climbs o bins de pendiente.
- La segmentacion relevante cambia mucho entre `road_run`, `trail_run` y sesiones por bloques.
- El riesgo de colapsar demasiada semantica en una sola columna es alto.

Por eso, esta tarea debe vivir primero en `analysis/` como:

- artefacto reproducible,
- contexto local de sesion,
- y apoyo narrativo para el informe,

sin tocar de entrada:

- `sessions.csv`
- `FINAL`
- `DASHBOARD`
- `reason_text`

## Base tecnica ya disponible

La tarea no parte de cero. El repo ya expone:

- `FP-02`: `GAP`, `VAM`, `terrain_context`, `terrain_intervals.csv`
- `SYA-12`: climbs FIT para `trail_run` y `road_run` con potencia medida Polar cuando existe
- `FP-01`: mitades mecanicas y contexto local de `durability_context`

Eso permite construir una capa nueva basada en comparaciones contextuales en lugar de comparaciones ciegas de sesion completa.

## Fuentes de datos preferidas

### Fuente primaria por split/intervalo

`Intervals`

Campos ya disponibles o derivables:

- `gap`
- `average_gradient`
- `average_speed`
- `distance`
- `elapsed_time`
- `moving_time`
- `total_elevation_gain`
- `average_cadence`
- `average_watts` cuando exista
- `decoupling`

### Fuente primaria por climb

`FIT` record-level

Campos ya disponibles o derivables:

- `hr`
- `cadence`
- `power`
- `distance`
- `altitude`
- `grade_mean_pct`
- `climb_time_min`
- `climb_gain_m`

## Enfoque recomendado

### Opcion A. Comparacion por climbs comparables

Es la opcion mas robusta para `trail_run`.

Idea:

- detectar climbs comparables por rango de pendiente, duracion y distancia,
- comparar primera mitad vs segunda mitad solo dentro de esos climbs,
- observar conjuntamente:
  - `power`
  - `GAP`
  - `FC`
  - `cadencia`

Preguntas que responder:

- a igual tipo de subida, hace falta mas FC para sostener menos output?
- la potencia cae aunque `GAP` se mantenga por perfil ligeramente favorable?
- cae tambien la cadencia o solo el output bruto?

### Opcion B. Comparacion por bins de pendiente

Mas flexible, especialmente para `road_run`.

Idea:

- agrupar tramos por bins de pendiente, por ejemplo:
  - `flat`
  - `rolling`
  - `moderate_uphill`
  - `steep_uphill`
- dentro de cada bin, comparar:
  - `power / GAP`
  - `GAP / HR`
  - `power / HR`

Ventaja:

- evita comparar una subida dura con una bajada rapida.

### Opcion C. Comparacion por bloques estructurados

Util para sesiones de calidad o trail por repeticiones.

Idea:

- cuando `work_n_blocks > 0`, comparar bloques del mismo tipo entre si,
- medir si hay:
  - perdida de potencia por repeticion,
  - perdida de `GAP`,
  - aumento de FC para output similar,
  - o degradacion de cadencia.

Importante:

- esta via no debe mezclarse sin mas con `durability` clasica de sesion continua.

## Senales candidatas

Esta tarea no fija aun una metrica unica. Debe evaluar varias senales candidatas:

### 1. `gap_per_hr_matched`

Proxy de eficiencia cardiovascular contextual.

Lectura:

- menos `GAP` por la misma `FC` en tramos equivalentes puede sugerir deterioro funcional.

### 2. `power_per_gap_matched`

Proxy de coste mecanico por desplazamiento equivalente.

Lectura:

- mas potencia para el mismo `GAP` en tramos comparables puede sugerir peor economia mecanica o terreno mas tecnico.

### 3. `power_per_hr_matched`

Aproxima la lectura clasica de output cardiovascular, pero controlando mejor el contexto que un promedio global de sesion.

### 4. `matched_climb_repeatability`

Senal de repeatability en subidas:

- comparacion de primeras subidas vs ultimas subidas comparables en:
  - `power`
  - `GAP`
  - `FC`
  - `cadencia`

## Hipotesis de trabajo

La hipotesis mas razonable hoy es:

- `trail_run` es el deporte donde mas valor puede aportar esta capa;
- `road_run` puede beneficiarse en sesiones con desnivel o bloques;
- `hike` probablemente sera demasiado ambiguo para hablar de eficiencia en sentido estricto;
- no conviene calcular una "eficiencia de sesion" unica sobre todo el archivo sin segmentacion contextual.

## Salida recomendada

### V1 exploratoria

Solo en `analysis/`.

Artefactos posibles:

- `efficiency_context` dentro de `session_payload.json` y `summary.json`
- `matched_segments.csv` o `matched_climbs.csv` dentro de `analysis/reports/<slug>/artifacts/`

Campos candidatos:

- `applicable`
- `applicability_reason`
- `comparison_mode`: `matched_climbs`, `grade_bins`, `structured_blocks`
- `primary_signal`
- `terrain_sensitivity`
- `interpretation_confidence`
- `efficiency_pattern`
- `power_per_gap_ratio`
- `gap_per_hr_ratio`
- `power_per_hr_ratio`

### V2 analitica

Si la V1 resulta util, incorporar narrativa especifica en el informe:

- distinguir coste alto con terreno favorable de perdida funcional real,
- separar deriva cardiovascular de perdida de repeatability,
- y no reutilizar automaticamente la taxonomia de `FP-01`.

## Taxonomia tentativa

Solo para `analysis`, no para contrato canonico.

- `not_applicable`
- `terrain_masked_output_drop`
- `cardiovascular_efficiency_drop`
- `mechanical_efficiency_drop`
- `repeatability_loss_in_climbs`
- `stable_contextual_efficiency`
- `mixed_signal`

## Riesgos

- llamar "eficiencia" a una senal todavia muy contaminada por tecnicidad y perfil;
- sobreajustar la taxonomia a muy pocas sesiones de trail;
- mezclar esta capa con `durability` clasica cuando en realidad resuelven preguntas distintas;
- aumentar mucho la complejidad narrativa del informe sin una mejora real de interpretacion.

## Relacion con otras tareas

- depende funcionalmente de `FP-02`, porque necesita `GAP` y capa de terreno;
- depende funcionalmente de `SYA-12`, porque necesita climbs FIT y potencia medida en run cuando exista;
- complementa `FP-01`, porque explica casos donde `power_ratio` y `speed_ratio` divergen;
- no debe empujar cambios en `FINAL`, `DASHBOARD` ni en el gate HRV.

## Criterios de aceptacion propuestos

1. Existe una estrategia reproducible para comparar output y coste en tramos equivalentes de run.
2. La solucion distingue al menos entre comparacion por climbs, bins de pendiente o bloques estructurados.
3. La salida vive solo en `analysis` y deja trazabilidad de fuente y metodo.
4. El informe puede usar la capa para explicar casos donde `power_ratio` y `speed_ratio` cuentan historias distintas.
5. La documentacion deja claro que esta capa no equivale a una metrica canonica de eficiencia fisiologica global.

## Decision recomendada hoy

Abrir esta tarea como **analisis y prototipado**, no como cambio de contrato.

La prioridad no es fabricar una metrica nueva rapido, sino comprobar si una comparacion contextual entre `power + GAP + pendiente + FC` realmente resuelve casos ambiguos mejor que:

- `power_ratio`
- `speed_ratio`
- `decoupling`
- y la narrativa de terreno ya existente.
