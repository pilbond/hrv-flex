

## Vinculo con la tarea

Este documento complementa la tarea:

- [FP-05 Eficiencia contextual en run con segmentos comparables](C:/Pilbond/polar-hrv-automation/docs/HRV/FP-05%20Eficiencia%20contextual%20en%20run%20con%20segmentos%20comparables.md)

Nota de trazabilidad:

- este documento fija definiciones operativas de apoyo para FP-05
- la tarea de implementacion principal vive en el documento enlazado arriba

## Objetivo de este documento

Fijar en un solo sitio:

- definiciones operativas recientes sobre `durability` en `road_run` y `trail_run`
- contexto relevante del desarrollo ya realizado
- nuevas reglas de lectura para evitar errores narrativos al interpretar sesiones con terreno variable o estructura por bloques

Este documento no cambia contratos canonicos globales por si solo.

Su alcance es:

- diseno analitico
- semantica local de `analysis/`
- criterios para futuras implementaciones o refactors

## Desarrollo ya realizado relevante

### 1. `FP-01` ya abrio una capa local de durability en `analysis`

Estado actual ya implementado:

- `sessions.csv` mantiene primitivas:
  - `run_power_first_half`
  - `run_power_second_half`
  - `speed_first_half`
  - `speed_second_half`
  - `cadence_first_half`
  - `cadence_second_half`
  - `durability_applicable`
  - `speed_ratio`
  - `power_ratio`
- `analysis/` ya expone:
  - `analysis_only_context.durability_context`
  - alias plano `session_payload.json.durability_context`

Taxonomia local ya usada:

- `not_applicable`
- `cardiovascular_drift_only`
- `mechanical_drop_with_drift`
- `mechanical_drop_without_drift`
- `ambiguous_due_to_terrain`
- `ambiguous_due_to_structure`
- `stable_output`
- `mixed_signal`

### 2. `FP-02` ya abrio la capa de terreno

Estado ya implementado:

- `terrain_context`
- `terrain_fit_context`
- `terrain_intervals.csv`
- `terrain_climbs.csv`
- `GAP`
- `VAM`

Esto ya permite leer:

- pendiente
- tipo de tramo
- climbs
- y parte del coste por relieve

### 3. `SYA-12` ya extendio climbs FIT a trail y road con potencia medida

Estado ya implementado:

- climbs FIT para `trail_run` y `road_run`
- `power_mean` por climb cuando existe potencia medida
- `hr_mean`, `cadence`, `grade_mean_pct`, `climb_time_min`, `climb_gain_m`

Esto es clave porque reduce la dependencia de medias globales de sesion para leer output y coste en terreno.

### 4. Ya existe una mejora local de lectura de bloques en `analysis`

Estado ya implementado:

- `analysis_only_context.work_block_context`
- alias plano `session_payload.json.work_block_context`

Campos ya derivados:

- `hard_work_blocks`
- `very_hard_work_blocks`
- `hard_work_min`
- `hard_work_share`
- `dominant_work_block_index`
- `dominant_work_block_min`
- `dominant_work_block_z3_pct`
- `dominant_work_block_share`
- `work_block_pattern`

Objetivo de esa capa:

- evitar leer `work_n_blocks` como si todos los bloques fueran igual de duros
- distinguir entre:
  - muchos bloques utiles
  - un bloque duro dominante
  - dureza repartida

## Definicion operativa actual de durability

### Principio base

`Durability` no debe confundirse con:

- `decoupling`
- `speed_ratio`
- `power_ratio`
- ni con cualquier media global simple de sesion

La definicion operativa correcta es:

> capacidad de sostener output util en condiciones comparables a medida que avanza la sesion

Eso implica dos familias de lectura:

1. `durability clasica`
2. `durability contextual`

## Durability clasica

### Definicion

Lectura de sostenimiento global de sesion, util cuando la comparacion entre primera mitad y segunda mitad tiene semantica aceptable.

### Cuando tiene sentido

Principalmente en:

- `road_run`
- algunos `trail_run`

Condiciones deseables:

- sesion relativamente continua
- baja fragmentacion estructural
- perfil no muy asimetrico
- si existe, potencia de carrera util

### Señales principales

Prioridad:

1. `power_ratio`
2. `speed_ratio` como fallback
3. `decoupling` solo como señal paralela, no como sustituto

### Lo que puede decir

- `cardiovascular_drift_only`
- `mechanical_drop_with_drift`
- `mechanical_drop_without_drift`
- `stable_output`

## Durability contextual

### Definicion

Lectura de sostenimiento no sobre la sesion completa, sino sobre tramos comparables dentro de la sesion.

### Cuándo hace falta

Especialmente en:

- `trail_run`
- sesiones con subidas y bajadas marcadas
- sesiones con bloques o repeticiones
- casos donde `power_ratio` y `speed_ratio` divergen

### Principio

En trail clasico si puede haber durability real.

Lo que muchas veces no existe es una forma limpia de medirla con:

- `speed_first_half`
- `speed_second_half`
- o con promedios simples globales

Por tanto:

- `trail_run` si puede tener deterioro de durability
- pero muchas veces debe leerse como `durability contextual`, no como `durability clasica`

## Regla propuesta por deporte

### `road_run`

Puede admitir `durability clasica` antes que otros deportes de pie.

Regla orientativa:

- `classic_applicable` si:
  - `moving_min >= 60`
  - `work_n_blocks <= 2`
  - comparacion global razonablemente limpia
  - mejor aun si `run_power_available = 1`

### `trail_run`

Debe separarse en tres estados:

1. `classic_applicable`
2. `contextual_only`
3. `not_applicable`

#### `classic_applicable`

Solo cuando:

- `moving_min >= 75`
- `work_n_blocks <= 2`
- perfil no demasiado asimetrico
- preferentemente `run_power_available = 1`
- la lectura por mitades no este claramente contaminada por descenso o terreno favorable

#### `contextual_only`

Cuando:

- `moving_min >= 60`
- existe capa de terreno usable
- y hay base para comparar:
  - climbs
  - bins de pendiente
  - o bloques comparables

pero falla la lectura global por:

- demasiados bloques
- terreno muy asimetrico
- contraste entre `power_ratio` y `speed_ratio`
- o alta sensibilidad al relieve

#### `not_applicable`

Cuando:

- la sesion no vale para lectura global
- y tampoco ofrece suficiente base contextual comparable

### `hike`

Debe seguir siendo el caso mas conservador.

Regla orientativa:

- no promover `speed_ratio` a lectura fuerte de durability sin mucho contexto adicional
- umbral de entrada mas alto
- alta penalizacion por asimetria de perfil

## Regla conceptual clave

No debe existir una unica puerta binaria para todos los deportes de pie.

La puerta actual `durability_applicable` mezcla demasiado:

- duracion
- continuidad
- deporte
- y tipo de señal mecanica

La evolucion deseable es distinguir:

- `durability_mode = classic`
- `durability_mode = contextual`
- `durability_mode = none`

Y mantener:

- `durability_applicable = 1` solo para el modo `classic`

## Regla sobre decoupling

`Decoupling` no debe leerse como prueba cerrada de agotamiento ni como sustituto de durability.

Su semantica correcta es:

- señal de relacion `output / FC`
- útil para detectar deriva cardiovascular relativa
- no suficiente por si sola para afirmar:
  - fatiga periferica
  - ineficiencia mecanica
  - agotamiento

Especialmente en trail o sesiones por bloques:

- `decoupling` alto puede convivir con:
  - `cardiac_drift_pct` no compatible con deriva lineal simple
  - `speed_ratio` estable
  - `power_ratio` bajo
  - y estructura muy fragmentada

Eso obliga a declarar ambigüedad en vez de cerrar una conclusion demasiado fuerte.

## Regla sobre bloques en run

`work_n_blocks` debe seguir leyendose como estructura util.

Pero no debe interpretarse automaticamente como:

- numero de bloques duros equivalentes

Para evitar ese error de lectura, `analysis` ya dispone de `work_block_context`.

### Semantica actual de `work_block_context`

#### Regla local de bloque duro

- `hard_work_block` si:
  - `duracion >= 6 min`
  - `z3_pct >= 20`

#### Regla local de bloque muy duro

- `very_hard_work_block` si:
  - `duracion >= 8 min`
  - `z3_pct >= 40`

#### Regla de bloque dominante

- `dominant_work_block_share = max(work_blocks_min) / work_total_min`

### Uso narrativo correcto

Si una sesion tiene:

- muchos bloques utiles
- pero un solo bloque que concentra la dureza real

la narrativa correcta no es:

- "cinco bloques duros"

sino:

- "cinco bloques utiles, con un bloque duro dominante"

Esto cambia la lectura de:

- repeticion de dureza
- peaje del bloque principal
- fatiga de continuidad

sin cambiar por si solo la conclusion sobre `durability` clasica.

## Relacion entre durability y eficiencia contextual

Estas dos capas no deben mezclarse:

### `durability`

Pregunta:

- se sostuvo el output util a medida que avanzaba la sesion?

### `efficiency contextual`

Pregunta:

- a igualdad aproximada de contexto de terreno, pendiente y tipo de tramo, cambió la relación entre:
  - potencia
  - GAP
  - FC
  - y, si existe, cadencia?

Por tanto:

- una sesion puede ser `not_applicable` para `durability clasica`
- y aun asi ser muy buena candidata para `efficiency contextual`

## Taxonomia orientativa futura para eficiencia contextual

Solo para `analysis`.

- `not_applicable`
- `terrain_masked_output_drop`
- `cardiovascular_efficiency_drop`
- `mechanical_efficiency_drop`
- `repeatability_loss_in_climbs`
- `stable_contextual_efficiency`
- `mixed_signal`

## Implicacion sobre sesiones tipo trail clasico

Regla conceptual final:

> un trail clasico con subidas y bajadas si puede tener durability, pero muchas veces no admite una lectura global limpia de durability clasica

En esos casos, debe pasar a:

- `durability contextual`
- o a futura capa de `efficiency_context`

No debe degradarse automaticamente a:

- "no hay nada interpretable"

pero tampoco debe forzarse a:

- "hay agotamiento claro"

## Decision de diseño recomendada

1. Mantener `FP-01` como capa de `durability` clasica basada en primitivas de `sessions.csv`
2. Evolucionar `trail_run` hacia una puerta de tres estados:
   - `classic_applicable`
   - `contextual_only`
   - `not_applicable`
3. Desarrollar `FP-05` como capa separada de `efficiency_context`
4. Usar `work_block_context` para corregir errores de lectura estructural antes de sacar conclusiones fuertes

## Cambios futuros deseables

### En `analysis`

- introducir `durability_mode`
- incorporar `efficiency_context`
- comparar:
  - climbs comparables
  - bins de pendiente
  - bloques estructurados comparables

### En documentacion

Si estas reglas pasan de exploracion a contrato operativo reproducible:

- actualizar [FP-05 Eficiencia contextual en run con potencia GAP pendiente y FC](C:/Pilbond/polar-hrv-automation/docs/HRV/FP-05%20Eficiencia%20contextual%20en%20run%20con%20potencia%20GAP%20pendiente%20y%20FC.md)
- revisar [FP-01 DI-01 Durability Index fatiga periferica en sesiones largas.md](C:/Pilbond/polar-hrv-automation/docs/HRV/FP-01%20DI-01%20Durability%20Index%20fatiga%20periferica%20en%20sesiones%20largas.md)
- y, si algun campo nuevo sube a contrato canonico, actualizar `docs/contracts/`

## Estado del documento

Documento de definiciones operativas.

No equivale a:

- implementacion cerrada
- contrato HRV canonico
- ni criterio definitivo de gating
