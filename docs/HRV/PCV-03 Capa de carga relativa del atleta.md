# PCV-03 Capa de carga relativa del atleta

Estado: implementada

## Resultado adoptado

`sessions_day` incorpora contexto causal de carga del propio atleta:

- `acwr_simple_prev`
- `acute_load_72h_rel`
- `monotony_7d_prev`
- `strain_7d_prev`
- `load_ctx_ready`
- `load_28d_nobs`
- `intense_days_prev_3d`
- `intense_days_prev_5d`
- `intensity_clustering_flag`
- `intensity_clustering_level`

`acute_load_72h_rel` compara `load_3d` con la media diaria de `load_28d` y
solo se calcula cuando existe contexto suficiente. `build_hrv_final_dashboard.py`
lo interpreta preferentemente con percentiles locales P75/P90 y conserva
`load_3d` como dato bruto de trazabilidad, no como unica lectura de carga.

Los mensajes de `reason_text` usan la senal relativa para los avisos de carga
aguda y mantienen ACWR, monotonia, strain y clustering como contexto
explicativo. Esta capa no modifica por si misma el gate HRV.

## Trazabilidad

- `build_sessions.py`
- `build_hrv_final_dashboard.py`
- `docs/contracts/ENDURANCE_HRV_Sessions_Schema.md`
- `docs/contracts/ENDURANCE_HRV_Spec_Tecnica.md`
- `tests/test_build_sessions_contract.py`
- `tests/test_build_hrv_final_dashboard_contract.py`

