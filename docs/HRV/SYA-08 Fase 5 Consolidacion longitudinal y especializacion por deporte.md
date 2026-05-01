## SYA-08 SYA-03E Fase 5 Consolidacion longitudinal y especializacion por deporte

Consolidar las senales ya validadas como capa madura de contexto del atleta por deporte y horizonte temporal. Prioridad real tras la revision externa: benchmarks por ruta o climb cuando exista repeticion suficiente; climb economy trend y sensibilidad termica individual como lecturas longitudinales; y divergencia cronica entre carga objetiva y subjetiva solo cuando ya exista una version validada en Fase 4.

Documento maestro: [[docs/HRV/SYA-03 Inventario y analisis ampliado de intervalsicugptcoach.md]]
Secciones aplicables: resumen ejecutivo; 6.b Roadmap formal por fases; tabla priorizada; anexo exhaustivo; 8.1 Priorizacion refinada tras revision externa.
Marco obligatorio: tratar esta fase como objetivo ideal posterior, dependiente de resultados validos de las fases 1-4.
Esta subtarea SI puede decidir: consolidacion longitudinal, especializacion por deporte y benchmarks cuando exista cobertura suficiente.
Esta subtarea NO puede decidir: saltarse validaciones previas o invadir el gate HRV con senales todavia experimentales; ni absorber tareas semanales o de baseline HRV global que pertenecen a otra capa.
Cierre obligatorio: actualizar SYA-03 con el modelo longitudinal final, criterios por deporte y limites reales de cobertura.

## Estado de cierre 2026-04-29

### Implementacion cerrada
- La capa longitudinal ya existe en `analysis/session_analysis_pipeline.py` como `build_longitudinal_context(...)`.
- La salida queda confinada a `analysis/`:
  - `summary.json`
  - `session_payload.json`
  - markdown del reporte final
- La implementacion actual consolida:
  - baseline propio por deporte sobre `sessions.csv`
  - comparativa por `route_id` cuando existe historico previo
  - benchmark de ruta solo cuando hay repeticion suficiente
  - coherencia subjetiva cronica
  - sensibilidad termica longitudinal
- La tarea sigue sin tocar `build_sessions.py`, `sessions_day.csv`, `FINAL` ni el gate HRV.

### Auditoria real de cobertura

Base auditada el `2026-04-29`:
- `data/ENDURANCE_HRV_sessions.csv`: `378` sesiones
- `analysis/reports/**/session_payload.json`: `90` reportes locales

Cobertura relevante en `sessions.csv` por deporte:
- `trail_run`: `67` sesiones; `route_id` 100%, `average_weather_temp` 100%, `cardiac_drift_pct` 100%, `decoupling` 40.3%
- `road_run`: `43` sesiones; `route_id` 20.9%, `average_weather_temp` 20.9%, `cardiac_drift_pct` 83.7%, `decoupling` 7.0%
- `bike`: `80` sesiones; `route_id` 100%, `average_weather_temp` 100%, `cardiac_drift_pct` 98.8%, `decoupling` 0.0%

Repeticion real de rutas en `sessions.csv`:
- `trail_run`: `66` rutas distintas para `67` sesiones; ninguna ruta llega a `n >= 3`
- `road_run`: `9` sesiones con `route_id`; ninguna ruta llega a `n >= 3`
- `bike`: `72` rutas distintas para `80` sesiones; solo `1` ruta llega a `n = 5`

Cobertura real en reportes `analysis/`:
- `trail_run`: `29` reportes; `subjective_coherence` 89.7%, `thermal_context` 17.2%, `terrain_fit_context` 100%
- `road_run`: `17` reportes; `subjective_coherence` 88.2%, `thermal_context` 0.0%, `terrain_fit_context` 35.3%
- `bike`: `29` reportes; `subjective_coherence` 86.2%, `thermal_context` 31.0%, `terrain_fit_context` 100%

Potencial real del algoritmo longitudinal actual sobre reportes ya generados:
- `trail_run`: `28/29` reportes pueden construir `longitudinal_context`, pero `0/29` activan `route_benchmark`
- `road_run`: `16/17` reportes pueden construir `longitudinal_context`, pero `0/17` activan `route_benchmark`
- `bike`: `28/29` reportes pueden construir `longitudinal_context`; `2/29` activan `route_benchmark`

### Decision final de capa
- `subjective_chronic_context` y `thermal_sensitivity_context` quedan aceptadas como capa madura de `analysis/`.
- `route_benchmark` y `climb_economy_trend` quedan aceptados tambien en `analysis/`, pero con activacion muy restringida por cobertura; hoy solo bici muestra repeticion util y no debe venderse como patron general de `trail_run` o `road_run`.
- `longitudinal_confidence` no exige esperar al umbral alto para reconocer señal util: pasa a `moderate` en cuanto hay `route_benchmark` con cobertura minima o al menos 6 sesiones historicas; solo sube a `high` cuando hay `>=12` sesiones historicas y ademas una senal longitudinal madura.
- Los umbrales de `chronic_state` y `longitudinal_confidence` estan centralizados como constantes en `analysis/session_analysis_pipeline.py` para reducir drift entre codigo, tests y documentacion.
- No se canoniza ninguna columna nueva en `sessions.csv` ni en `sessions_day.csv`.
- No se modifica `docs/contracts/` porque no cambia ningun contrato operativo ni de gating.
- Los artefactos historicos existentes no traen todavia `longitudinal_context.json`; ese sidecar aparecera al reanalizar sesiones con la nueva version del pipeline.

### Verificacion funcional
- Se verifico comportamiento con historial mixto de deportes: `build_longitudinal_context(...)` filtra por deporte y no mezcla sesiones ajenas.
- Se verifico el render del reporte con `sport_baseline.highlight` presente y ausente: el bloque longitudinal sale una sola vez y el anclaje propio solo aparece cuando existe highlight.
- Se verifico un caso de cobertura mixta con `route_benchmark` disponible pero sin datos de `climb`: el benchmark sigue activo y `climb_economy_trend` queda `None` sin romper el render ni el payload.

### Criterios por deporte
- `trail_run`: viable para baseline propio, coherencia subjetiva cronica y sensibilidad termica; no viable hoy para benchmark por ruta.
- `road_run`: viable para baseline propio y coherencia subjetiva cronica; sensibilidad termica limitada por cobertura actual; benchmark por ruta no viable.
- `bike`: viable para baseline propio y coherencia subjetiva cronica; sensibilidad termica usable de forma parcial; benchmark por ruta viable solo en una ruta repetida concreta.
- `swim`, `elliptical`, `strength`, `mobility`, `other`, `hike`: fuera del objetivo principal de especializacion de esta fase o sin cobertura suficiente para reglas longitudinales fuertes.

## Análisis técnico 2026-04-23

### Estado actual del código
- Fase 4 (SYA-07) cerrada: la capa compuesta vive en `analysis/session_analysis_pipeline.py` y ya no debe referenciarse por el rango antiguo `1787-1870`, que quedó obsoleto tras refactorizaciones posteriores. En el código actual:
  - `build_load_mismatch_context(...)` expone `subjective_coherence` en torno a `:2069-2141`
  - `build_thermal_context(...)` expone `thermal_cost_score` en torno a `:2144-2169`
  - `build_composite_context(...)` consolida estas piezas en `composite_context` en torno a `:3186-3206`
  - el bloque narrativo que las consume y las menciona explícitamente está hoy en `analysis/session_analysis_pipeline.py:1095`, `:1119` y `:1129`
- Todo ello sigue confinado a la capa `analysis/` sin tocar `sessions_day.csv`.
- No existe todavía capa longitudinal per-sport: `build_sessions.py:1644` ya produce `intensity_distribution_weekly.csv` pero no hay rolling de `subjective_coherence`, `thermal_cost_score` ni durability en `sessions_day.csv`.
- No hay lookup por `route_id` ni por climb; `route_id` aparece en sessions pero sin capa de benchmark (ver SYA-03 tabla priorizada `:1136`).
- Cobertura actual N=362 sesiones históricas (backtest 2025-05-12..2026-04-15), pero `session_rpe` solo en 74.9%, `decoupling` condicionado a `device_watts`.

### Valor actual
- Valor potencial alto pero **diferido**: la Fase 5 solo debería arrancarse cuando el sidecar `analysis/` acumule suficientes observaciones validadas por deporte (≥3 meses tras SYA-07).
- Sensibilidad térmica individual y divergencia crónica carga-objetivo/subjetiva son las dos señales más maduras; route/climb benchmark depende de repeticiones de ruta que hoy no están cuantificadas.

### Errores/riesgos
- Riesgo principal: arrancar la fase prematuramente y consolidar rolling sobre primitivas con cobertura irregular por deporte (`session_rpe` en 74.9%, `device_watts` solo en bike).
- Riesgo de contaminar `sessions_day.csv` con columnas de baja cobertura que luego haya que deprecar.
- Falta aún auditoría mínima de cuántas rutas o climbs tienen repetición real en el histórico (preguntarle al dato antes de diseñar el schema).

### Mejoras propuestas
1. Antes de implementar nada, ejecutar auditoría de cobertura: por deporte, ¿cuántas sesiones tienen `subjective_coherence` válida?, ¿cuántas rutas se repiten ≥3 veces? Incluir resultado en SYA-03.
2. Definir en esta tarea el schema del rolling per-sport (ventana, métrica, nulabilidad) antes de tocar código.
3. Mantener route/climb benchmark como capa `analysis/` con lookup por `route_id`, no columna en `sessions_day.csv`; solo pasar a sidecar canónico si el uso se demuestra.
4. Sensibilidad térmica individual: baseline propio del atleta (media `thermal_cost_score` trimestral), exponerla como columna analítica, no como gate.
5. No tocar weekly ni HRV global aquí (pertenecen a SYA-09 y tareas HRV separadas respectivamente).

### Conclusión
La auditoria ya esta hecha y cambia la naturaleza de la tarea:
- la capa longitudinal queda validada como salida madura de `analysis/`
- la cobertura no justifica hoy mover nada a `build_sessions.py`
- `route benchmark` no debe presentarse como feature general de run; su utilidad real actual queda acotada sobre todo a bici

Por tanto, `SYA-08` puede cerrarse como implementacion `analysis-only` con limites explicitados y sin reabrir contratos canonicos.
