# FP-07 Validacion y calibracion de umbrales de eficiencia contextual en run

> Tarjeta Kanvas: `FP-07` — grupo `Terreno / Perfomance`, estado `purple` (propuesta).
> Documento precedente: [FP-06 Eficiencia contextual en run.md](FP-06%20Eficiencia%20contextual%20en%20run.md)

## Texto de la tarjeta

Objetivo: validar con historico real si los thresholds provisionales de `FP-06` separan patrones utiles en sesiones de run con climbs comparables y decidir si deben mantenerse, ajustarse o parametrizarse.

Esta tarea no extiende la V1 funcional de `FP-06`; la evalua.

---

## Analisis tecnico 2026-04-28

### Motivo de apertura

`FP-06` ya deja una V1 reproducible en `analysis/` basada en `matched_climbs` early vs late, con:

- `efficiency_context` en `summary.json` y `session_payload.json`
- `matched_climbs.csv` como sidecar reproducible
- clasificacion local `stable_contextual_efficiency`, `cardiovascular_efficiency_drop`, `mechanical_efficiency_drop`, `repeatability_loss_in_climbs`, `mixed_signal`

El problema pendiente no es de implementacion, sino de validez:

- `0.93` y `0.90` heredan heuristicas proximas a `FP-01`, pero no estan validadas especificamente para `vam_ratio`
- `1.04` y `1.07` aparecen hoy como thresholds operativos locales para `hr_per_vam_ratio`, sin trazabilidad suficiente en documentacion ni backtest

Por tanto, la pregunta correcta ya no es "como implementar FP-06", sino "si esos umbrales separan de verdad patrones utiles".

### Alcance propuesto

La tarea debe cubrir cuatro piezas:

1. Extraccion de dataset de validacion desde `analysis/reports/`
2. Etiquetado manual de una muestra de sesiones aplicables
3. Backtest reproducible de thresholds candidatos
4. Decision documentada sobre mantener, mover o parametrizar los umbrales

### Dataset minimo deseable

Cada fila deberia representar una sesion con `efficiency_context` aplicable e incluir, como minimo:

- `slug`
- `sport_family`
- `matched_groups_count`
- `climb_count`
- `aggregate.vam_ratio`
- `aggregate.hr_drift_bpm`
- `aggregate.hr_per_vam_ratio`
- `aggregate.power_per_hr_ratio`
- `efficiency_pattern`
- presencia de potencia medida o estimada

Ademas, una etiqueta manual de referencia:

- `stable`
- `mechanical_drop`
- `cardiovascular_drop`
- `repeatability_loss`
- `ambiguous`

### Metodo de validacion

El backtest debe probar, al menos:

- thresholds alternativos para `vam_ratio`
- thresholds alternativos para `hr_per_vam_ratio`
- separacion por `road`, `trail` y `hike` si la muestra lo permite

Y medir:

- precision
- recall
- matriz de confusion
- tasa de `mixed_signal`
- estabilidad de clasificacion ante pequenos cambios de threshold

### Criterios de aceptacion propuestos

1. Existe un dataset reproducible de sesiones candidatas a FP-06.
2. Existe una muestra etiquetada manualmente con suficiente variedad de casos.
3. Existe un backtest reproducible de thresholds para `vam_ratio` y `hr_per_vam_ratio`.
4. Hay una decision escrita sobre si `0.93/0.90/1.04/1.07` se mantienen, se ajustan o se parametrizan por deporte.
5. La documentacion de `analysis/` refleja esa decision y deja clara la procedencia final de los umbrales.

### Fuera de alcance

- cambiar `FINAL`, `DASHBOARD`, `sessions.csv` o el gate HRV
- convertir automaticamente FP-06 en contrato canonico
- ampliar la taxonomia antes de validar la V1 actual

### Conclusion

FP-07 tiene sentido como tarea nueva y separada porque ataca una duda distinta a FP-06:

- `FP-06` resuelve implementacion y trazabilidad
- `FP-07` resuelve validez y calibracion

Sin esta tarea, FP-06 puede cerrarse como capa exploratoria util. Con esta tarea, puede decidirse si la heuristica merece endurecerse, ajustarse o quedarse como apoyo narrativo local.
