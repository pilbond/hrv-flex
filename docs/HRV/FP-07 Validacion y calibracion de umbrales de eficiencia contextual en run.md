> Tarjeta Kanvas: `FP-07` - grupo `Terreno / Perfomance`, estado `purple` (propuesta).
> Documento precedente: [FP-06 Eficiencia contextual en run.md](FP-06%20Eficiencia%20contextual%20en%20run.md)

## Texto propuesto para la tarjeta

Objetivo: auditar con historico real como se reparten hoy los casos de `efficiency_context` en run, identificar por que `mixed_signal` absorbe combinaciones heterogeneas, y decidir despues si procede completar la logica de clasificacion, ajustar thresholds o mantener la heuristica actual.

Esta tarea no extiende el contrato global ni canoniza la metrica. Revisa la capa local de `analysis/` abierta por `FP-06`.

---

## Analisis tecnico 2026-05-18

### Motivo de reapertura

La formulacion original de `FP-07` asumia que la principal duda pendiente tras `FP-06` era si los thresholds provisionales de:

- `vam_ratio`: `0.93` / `0.90`
- `hr_per_vam_ratio`: `1.04` / `1.07`

separaban bien los patrones utiles.

La revision del estado real en `analysis/reports/` apunta a un problema mas concreto y previo:

- el bucket `mixed_signal` esta absorbiendo sesiones con combinaciones distintas entre `vam_ratio`, `hr_drift_bpm` y `hr_per_vam_ratio`
- parte de esas sesiones no parecen "mixtas" en sentido fuerte, sino no resueltas por la logica actual
- por tanto, antes de mover thresholds conviene auditar la taxonomia efectiva que hoy produce `analysis/fit_terrain_utils.py`

### Hallazgo clave en implementacion

La clasificacion actual de `efficiency_context` vive en [analysis/fit_terrain_utils.py](../../analysis/fit_terrain_utils.py) y usa estas reglas:

- `vam_ok = vam_ratio >= 0.93`
- `vam_drop = vam_ratio < 0.90`
- `hr_stable = hr_drift_bpm is None or abs(hr_drift_bpm) <= 5.0`
- `hr_elevated = hr_drift_bpm is not None and hr_drift_bpm > 8.0`
- `cost_ok = hr_per_vam_ratio is None or hr_per_vam_ratio <= 1.04`
- `cost_elevated = hr_per_vam_ratio is not None and hr_per_vam_ratio > 1.07`

Y despues:

- `vam_ok and hr_stable and cost_ok` -> `stable_contextual_efficiency`
- `vam_drop and hr_elevated and cost_elevated` -> `repeatability_loss_in_climbs`
- `cost_elevated and not vam_drop` -> `cardiovascular_efficiency_drop`
- `vam_drop and hr_stable and not cost_elevated` -> `mechanical_efficiency_drop`
- resto -> `mixed_signal`

Esto deja varias zonas no explicitadas:

- `5 < hr_drift_bpm <= 8`
- `vam_ok + hr_elevated + cost_ok`
- `vam_drop + hr_stable + cost_elevated`
- `hr_drift_bpm < -5`
- combinaciones en bandas grises de coste

La implicacion es importante: hoy `mixed_signal` mezcla incertidumbre real con huecos de taxonomia.

### Estado real del dataset observado

Con los artefactos actuales del repo:

- existen `25` `matched_climbs.csv`
- los `25` tienen `efficiency_context.applicable = true` en `summary.json`
- reparto observado por patron:
  - `mixed_signal`: `13`
  - `stable_contextual_efficiency`: `5`
  - `cardiovascular_efficiency_drop`: `5`
  - `repeatability_loss_in_climbs`: `2`
  - `mechanical_efficiency_drop`: `0`

Reparto por deporte/familia:

- `road_run`: `3` sesiones (`2 mixed`, `1 stable`)
- `trail_run`: `22` sesiones (`11 mixed`, `4 stable`, `5 cardiovascular`, `2 repeatability`)

Ademas:

- no hay casos en la banda gris de `vam_ratio` (`0.90-0.93`)
- hay pocos casos en banda gris de `hr_per_vam_ratio` (`1.04-1.07`)
- una parte relevante de `mixed_signal` no cae en las bandas grises, sino en combinaciones validas no tipificadas

### Reformulacion del problema

La pregunta operativa correcta para `FP-07` ya no es:

- "debemos mover `0.93`, `0.90`, `1.04` o `1.07`?"

Sino:

- "que subtipos reales estan entrando hoy en `mixed_signal`?"
- "cuales son incertidumbre genuina y cuales son huecos de reglas?"
- "solo despues de vaciar ese bucket, los thresholds actuales siguen teniendo sentido?"

Por eso `FP-07` debe cambiar de foco:

1. primero auditar el comportamiento real de la clasificacion
2. despues decidir si hace falta una rama nueva, una prioridad distinta o thresholds nuevos

### Alcance propuesto

La tarea debe cubrir cinco piezas:

1. Extraccion reproducible del dataset desde `analysis/reports/`
2. Construccion de una tabla de validacion usando `summary.json` como fuente primaria de `efficiency_pattern`
3. Auditoria de todos los casos que hoy caen en `mixed_signal`
4. Propuesta documentada de taxonomia revisada o de nuevas ramas de decision
5. Revision secundaria de thresholds solo si la auditoria muestra que siguen siendo el cuello real

### Dataset minimo obligatorio

Cada fila debe representar una sesion con `matched_climbs.csv` y enlazarse con su `summary.json`. El dataset no puede construirse solo con `matched_climbs.csv`, porque `efficiency_pattern` vive en `summary.json`.

Campos minimos:

- `slug`
- `sport_family`
- `climb_count`
- `matched_groups_count`
- `aggregate.vam_ratio`
- `aggregate.hr_drift_bpm`
- `aggregate.hr_per_vam_ratio`
- `aggregate.power_per_hr_ratio`
- `efficiency_pattern`
- `interpretation_confidence`
- presencia de potencia medida o estimada

Campos derivados recomendados:

- bucket de `vam_ratio` (`ok`, `gray`, `drop`)
- bucket de `hr_drift_bpm` (`stable`, `gray`, `elevated`, `drop`)
- bucket de `hr_per_vam_ratio` (`ok`, `gray`, `elevated`)
- combinacion logica resultante

### Preguntas que FP-07 debe responder

1. Que porcentaje de `mixed_signal` viene de un hueco logico y no de ambiguedad fisiologica real.
2. Si `mixed_signal` debe seguir existiendo como bucket prudente, pero acotado a contradicciones reales.
3. Si hace falta introducir una rama adicional para algun subcaso estable, cardiovascular leve o drift desacoplado.
4. Si `mechanical_efficiency_drop` no aparece porque es raro o porque su regla actual es demasiado estricta.
5. Si `repeatability_loss_in_climbs` aparece poco por rareza real o por conjuncion excesivamente dura.
6. Solo despues de lo anterior, si `0.93/0.90/1.04/1.07` deben mantenerse, moverse o seguir como heuristica local.

### Metodo de validacion recomendado

Orden de trabajo:

1. Extraer el historico reproducible.
2. Clasificar cada `mixed_signal` por combinacion de buckets.
3. Separar:
   - hueco de logica
   - contradiccion real entre señales
   - zona gris de thresholds
4. Etiquetar manualmente una muestra pequena, solo como contraste cualitativo.
5. Probar cambios de taxonomia antes de probar rejillas amplias de thresholds.
6. Hacer un backtest simple y descriptivo si aun quedan dudas de corte.

Con el tamano actual de muestra, el output esperable es:

- una decision tecnica defendible
- no una conclusion estadistica fuerte por precision/recall o ROC

### Criterios de aceptacion propuestos

1. Existe un dataset reproducible enlazando `matched_climbs.csv` con `summary.json`.
2. Existe un inventario claro de combinaciones que hoy terminan en `mixed_signal`.
3. Existe una decision escrita sobre si `mixed_signal` necesita ramas nuevas, reglas reordenadas o puede mantenerse igual.
4. Si se propone cambiar la taxonomia o thresholds, hay una justificacion apoyada en casos reales del historico.
5. La documentacion de `analysis/` deja explicito que parte es hueco logico, que parte es ambiguedad real y que parte depende de thresholds.

### Fuera de alcance

- cambiar `FINAL`, `DASHBOARD`, `sessions.csv` o el gate HRV
- convertir `efficiency_context` en output canonico global
- hacer inferencia estadistica fuerte por deporte con muestra pequena
- mover thresholds por intuicion sin antes auditar el contenido real de `mixed_signal`

### Texto corto recomendado para actualizar la tarjeta Kanvas

`Auditar con historico real por que mixed_signal absorbe combinaciones heterogeneas en efficiency_context de run, decidir si faltan ramas de clasificacion y revisar thresholds solo despues de esa auditoria.`

### Conclusion

`FP-07` sigue teniendo valor y encaja bien como continuacion de `FP-06`, pero su scope correcto no es "calibrar thresholds" sin mas.

La secuencia correcta es:

- `FP-06` implementa la heuristica local
- `FP-07` audita la taxonomia efectiva y el bucket `mixed_signal`
- solo despues se decide si los thresholds merecen ajustarse o mantenerse

Asi la tarea deja de perseguir un ajuste numerico prematuro y pasa a resolver el problema estructural real de la clasificacion.
