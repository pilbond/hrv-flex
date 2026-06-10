# PCV-02 Baseline adaptativo largo plazo

Estado: implementada
Fecha de cierre operativo: 2026-05-13

## Resultado adoptado

La necesidad original quedo resuelta en la capa de warning longitudinal:

- `FINAL` expone `degraded_vs_best` y `degraded_vs_current_normal`.
- `warning_mode=adaptive90` es el default operativo.
- `baseline60_degraded` se conserva como alias legacy.
- contratos y tests reflejan la semantica adoptada.

El gate diario no cambia. La separacion entre `historical_best` y
`current_normal` evita tratar como referencia unica un periodo historico que
pueda haber dejado de representar el estado normal reciente del atleta.

## Relacion con HG-01

`HG-01` es una hipotesis complementaria sobre una posible metrica longitudinal
adicional. No sustituye ni reabre `PCV-02` mientras no demuestre valor
incremental frente a `degraded_vs_best` y `degraded_vs_current_normal`.

## Trazabilidad

- `build_hrv_final_dashboard.py`
- `docs/contracts/ENDURANCE_HRV_Spec_Tecnica.md`
- `docs/contracts/ENDURANCE_HRV_Diccionario.md`
- `docs/contracts/ENDURANCE_HRV_Estructura.md`

