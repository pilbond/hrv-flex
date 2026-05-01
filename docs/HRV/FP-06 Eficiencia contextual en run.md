# FP-06 Eficiencia contextual en run con segmentos comparables

> Tarjeta Kanvas: `FP-06` — grupo `Terreno / Perfomance`, estado `green`.
> Documento canonico de referencia: [FP-05 Eficiencia contextual en run con segmentos comparables.md](FP-05%20Eficiencia%20contextual%20en%20run%20con%20segmentos%20comparables.md)
> Continuacion de validacion: [FP-07 Validacion y calibracion de umbrales de eficiencia contextual en run.md](FP-07%20Validacion%20y%20calibracion%20de%20umbrales%20de%20eficiencia%20contextual%20en%20run.md)

## Objetivo

Dejar una capa reproducible de eficiencia contextual para sesiones de `road_run` y `trail_run`, comparando subidas tempranas y tardias de pendiente comparable dentro de la misma sesion, sin promover esa capa a contrato canonico global.

## Estado actual

`FP-06` esta implementada en `analysis/` como V1 exploratoria basada en `matched_climbs`.

Hoy ya existen:

- `compute_matched_climbs_context()` en `analysis/fit_terrain_utils.py`
- `efficiency_context` dentro de `summary.json` y `session_payload.json`
- `matched_climbs.csv` dentro de `analysis/reports/<slug>/artifacts/` cuando la sesion es aplicable
- integracion de ese artefacto en `analyst_prompt.md` y `ai_handoff.md`
- tests de regresion para ausencia de `vam_ratio`, agregacion ponderada y exposicion del artefacto

No es una propuesta vacia ni una nota de intencion: la capa ya forma parte del flujo local de `analysis`.

## Implementacion actual

### Fuente y modo de comparacion

La V1 usa:

- `terrain_fit_context`
- `terrain_climbs.csv`
- `comparison_mode = matched_climbs`

La comparacion se construye asi:

1. detectar climbs desde `FIT` record-level
2. agruparlos por bins de pendiente
3. partirlos en `early` y `late` usando el `midpoint_sec` de la sesion
4. comparar medias de `HR`, `VAM` y, cuando exista, `power`
5. agregar el resultado por tamano real de muestra (`early_count + late_count`)

### Salida local

La capa produce:

- `efficiency_context`
- `matched_climbs.csv`
- taxonomia local:
  - `stable_contextual_efficiency`
  - `cardiovascular_efficiency_drop`
  - `mechanical_efficiency_drop`
  - `repeatability_loss_in_climbs`
  - `mixed_signal`
  - `not_applicable`

Estos outputs viven solo en `analysis/`. No modifican:

- `sessions.csv`
- `ENDURANCE_HRV_master_FINAL.csv`
- `ENDURANCE_HRV_master_DASHBOARD.csv`
- el gate HRV

## Valor real aportado

Antes de `FP-06`, `analysis` ya disponia de:

- `terrain_context`
- `terrain_fit_context`
- `power_ratio`
- `speed_ratio`
- `decoupling`
- `terrain_climbs.csv`

Pero faltaba una capa intermedia para sesiones de `run` y `trail` donde:

- la comparacion global de mitades era demasiado tosca por culpa del perfil
- el terreno hacia ambigua la lectura clasica de `durability`
- hacia falta distinguir mejor entre "sube la FC" y "cae el output util"

`FP-06` aporta sobre ese estado previo:

- comparacion reproducible early vs late entre subidas comparables
- sintesis estructurada en `efficiency_context`
- sidecar auditable `matched_climbs.csv`
- una taxonomia local para describir estabilidad, caida mecanica, caida cardiovascular o senal mixta

En terminos practicos:

- mejora la explicacion de sesiones ambiguas de `run` y `trail`
- reduce dependencia de intuicion manual al redactar el informe
- deja evidencia reproducible en artefactos, no solo en texto libre
- complementa `FP-01` sin mezclarla con la lectura clasica de `durability`

## Limites y riesgos

La capa sigue siendo exploratoria. Sus limites actuales son claros:

- depende de que existan climbs comparables dentro de la sesion
- el corte `early` vs `late` por `midpoint_sec` es una heuristica, no una verdad fisiologica
- los thresholds actuales de clasificacion no estan validados con historico amplio
- la banda gris de `vam_ratio` entre `0.90` y `0.93` cae deliberadamente en `mixed_signal`

Por ese motivo:

- no debe tratarse como contrato canonico
- no debe contradecir por si sola `sessions.csv` ni la capa RR
- debe leerse como apoyo analitico local y trazable

## Cobertura y validacion actual

La implementacion actual ya cubre los fallos funcionales que aparecieron durante la revision:

- `matched_climbs.csv` se propaga a payload y prompts
- ausencia de `vam_ratio` no promociona patrones fuertes
- la agregacion esta ponderada por tamano de muestra
- el flujo no rompe cuando `efficiency_context` no aplica

La validacion que falta ya no es de implementacion, sino de calibracion. Esa continuacion queda abierta en `FP-07`.

## Conclusion

`FP-06` puede darse por completada como capa exploratoria de `analysis`:

- implementacion reproducible: si
- integracion en artefactos y prompts: si
- trazabilidad local: si
- validacion fisiologica cerrada: no

La lectura correcta hoy es:

`FP-06` resuelve implementacion y utilidad analitica local; `FP-07` resuelve si sus thresholds y patrones merecen endurecerse o recalibrarse.
