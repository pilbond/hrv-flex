# Tarea: Capa de carga relativa del atleta

Estado: pendiente
Tipo de valor: valor explicativo, valor predictivo temprano y valor de personalizacion
Prioridad: alta

## Resumen
La capa de carga actual sigue apoyandose en umbrales absolutos en `reason_text` (`load_3d`, `work_7d_sum`, `z3_7d_sum`). Eso limita la lectura del contexto porque no distingue bien cantidad, calidad, densidad ni pico relativo de carga.

## Que falta exactamente
- sustituir o complementar reglas absolutas por metricas relativas del atleta;
- introducir al menos estas senales en `sessions_day` o en una capa derivada:
  - `acute_load_72h_rel`
  - `quality_stress_72h`
  - `hard_day_stack_4d`
  - `acute_chronic_ratio_7_28`
  - `monotony_7d`
- rehacer los avisos de `reason_text` para que expliquen mejor verdes fragiles y rojos sin causa aparente;
- absorber aqui la mejora de `load_3d`, evitando dejarla como warning aislado con un umbral fijo.

## Por que sigue teniendo valor
- mejora mucho la interpretacion de carga sin tocar el gate base;
- reduce avisos muertos o poco informativos;
- permite distinguir carga total, calidad reciente, apilado de dias duros y spikes de progresion.

## Archivos candidatos
- `build_sessions.py`
- `build_hrv_final_dashboard.py`
- `docs/contracts/ENDURANCE_HRV_Sessions_Schema.md`
- `docs/contracts/ENDURANCE_HRV_Spec_Tecnica.md`

## Criterio de cierre
Existe una capa de carga relativa del atleta, documentada en contratos, y `reason_text` usa esa capa con mensajes mas especificos que los umbrales absolutos actuales.
