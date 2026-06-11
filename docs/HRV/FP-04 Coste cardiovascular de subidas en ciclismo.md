# FP-04 Matched climbs en bike con potencia medida cuando exista

## Texto de la tarjeta

Contexto actual: la extension FIT a `bike` ya quedo resuelta por `TYM-01`. El gap pendiente no es exponer climbs, sino comparar subidas comparables dentro de la misma sesion (`matched_climbs`) para leer deriva cardiovascular y perdida mecanica en ciclismo, priorizando potencia medida cuando exista y usando estimada solo como fallback interpretativo.

Objetivo: habilitar `matched_climbs` para `bike` sobre `terrain_fit_context`, sin tocar `session_cost_model`, `sessions.csv`, `sessions_day.csv`, `FINAL`, `DASHBOARD` ni el gate HRV.

V1 ejecutable:
- permitir `bike` en `compute_matched_climbs_context()`
- emitir `efficiency_context` y `matched_climbs.csv` para sesiones bike con >=2 climbs comparables
- usar deltas early vs late de `hr_mean`, `power_mean`, `cadence_mean` y ratios agregados (`hr_drift_bpm`, `power_per_hr_ratio`, `hr_per_vam_ratio`)
- si `climb_power_source=measured`, tratar esa via como lectura preferente; si es `estimated`, mantener cautela explicita

Criterios de aceptacion:
1. una sesion bike outdoor con >=2 climbs comparables genera `efficiency_context.applicable=true`
2. `summary.json` y `session_payload.json` exponen `matched_groups_count`, agregados early/late y patron categorico interpretable
3. se escribe `analysis/reports/<slug>/artifacts/matched_climbs.csv` cuando aplique
4. la narrativa distingue potencia `measured` vs `estimated`
5. no se modifica ningun output canonico global
6. validacion minima con 3 sesiones bike recientes con climbs; priorizar casos con potencia medida

Relacion:
- no duplicar `TYM-01`; esa extension ya esta cerrada
- no mezclar con la linea de run contextual salvo reutilizacion interna de infraestructura
- la Iteracion B de FP-03 (zonas por climb) queda fuera salvo decision explicita

---

## Analisis tecnico 2026-04-23

### Estado actual del codigo

La Iteracion A de FP-03 (activar V3 FIT en bike + `cadence_unit=rpm`) esta **ya implementada** en el repositorio, cerrada por TYM-01:

- `analysis/session_analysis_pipeline.py:701-704` — `_supports_terrain_context()` incluye `bike` en el set `{"road", "trail", "hike", "bike"}`.
- `analysis/session_analysis_pipeline.py:707-708` — `_terrain_fit_cadence_unit()` devuelve `"rpm"` cuando `analyzer_sport_from_session(row) == "bike"`, `"strides_per_min"` en otro caso.
- `analysis/fit_terrain_utils.py:80-81` — `_climb_thresholds()` ya discrimina por `sport_family` (bike/trail/run/road/hike) vía `_CLIMB_THRESHOLDS`.
- `analysis/session_analysis_pipeline.py:3185-3190` — existen alias `_report_bike_climb_count`, `_bike_climb_metrics`, `_bike_climb_dilation_sentence`, etc., apuntando a funciones genericas `_terrain_*` parametrizadas por `sport_family`.
- SYA-12 (ver `research/reports/legacy_analysis/SYA-12_terrain_climbs_trail_road_run_analysis.md`) generalizo `_build_sport_climbs_table()` y removio el gate `sport_family == "bike"` en el render de tabla.

Resultado: para cualquier sesion bike outdoor con GPS + altitud, el pipeline ya emite `terrain_climbs.csv`, `terrain_fit_context` con `cadence_unit=rpm` y narrativa de potencia medida/estimada.

### Valor incremental de FP-04 sobre el estado actual

El criterio 1-6 de Iteracion A de FP-03 esta cubierto. Lo que **todavia no existe** y define valor real de FP-04 como tarjeta independiente:

1. **`matched_climbs` por sesion** — comparacion entre subidas comparables (pendiente, duracion, distancia) dentro de la misma sesion bike, con delta de `hr_mean`, `power_mean` (medida o estimada) y `cadence_mean` entre primeras y ultimas subidas.
2. **Iteracion B de FP-03 (zonas por climb)** — `z1_pct`, `z2_pct`, `z3_pct`, `z2_min`, `z3_min` por subida, y agregados `total_climb_z2_min`, `total_climb_z3_min`, `climb_cardio_signal` en `terrain_fit_context`. No existe en el codigo inspeccionado (`grep matched_climbs|efficiency_context|grade_bins` → 0 resultados en `analysis/`).
3. **Validacion end-to-end con 3+ sesiones bike outdoor** — el punto 6 de criterios de aceptacion de FP-03 esta implementado pero no documentado como evidencia cerrada; la sesion i138137906 citada como caso motivador no tiene reporte de validacion posterior.

### Errores / riesgos detectados

- El documento base FP-03 describe FP-04 como "extension FIT a bike" pero esa extension **ya ocurrio**. La tarjeta FP-04 como esta redactada hoy solapa con TYM-01 (done). Hay que reencuadrarla explicitamente como `matched_climbs` V1 + Iteracion B de FP-03, para que no sea duplicada.
- FP-03 deja la Iteracion B como "alcance extendido, opcional". Si FP-04 se aprueba como `matched_climbs`, ambas lineas (zonas por climb vs comparacion entre climbs) comparten infraestructura (muestras FIT por subida) y conviene decidir si se fusionan o se desacoplan en dos tarjetas.
- No hay documento propio para FP-04: la tarjeta referencia el MD de FP-03 directamente, lo que genera ambiguedad sobre alcance. Este MD (2026-04-23) es el delta operativo hasta que la tarjeta se acepte.

### Mejoras propuestas para la tarjeta

1. Reescribir el texto de la tarjeta para acotar a `matched_climbs` sobre bike (no a "extender capa FIT", que ya esta hecha).
2. Anadir criterios de aceptacion especificos: salida `matched_climbs` en `summary.json` con al menos 2 climbs comparables, delta de FC y potencia entre primeros y ultimos, y pattern categorico (`stable`, `cardio_drift`, `mechanical_drop`, `mixed`).
3. Declarar de forma explicita: `sessions.csv`, `FINAL`, `DASHBOARD` y `reason_text` NO se modifican. Salida vive solo en `analysis/reports/<slug>/artifacts/`.
4. Dejar `grade_bins` fuera de V1 (coincide con nota actual de tarjeta).
5. Opcional: incluir Iteracion B de FP-03 (zonas por climb) como sub-alcance de FP-04 o crear tarjeta hija.

### Conclusion

FP-04 sigue aportando valor **si y solo si** se reencuadra a `matched_climbs` V1 en bike. La capa FIT de terreno para bike ya esta implementada por TYM-01; insistir en ese alcance seria trabajo redundante. La decision operativa razonable es:

- Aprobar FP-04 con alcance `matched_climbs` V1 (bike).
- Separar Iteracion B de FP-03 (zonas por climb) en tarjeta independiente si se considera prioritaria.
- Mantener FP-04 fuera de `session_cost_model` y del gate HRV, coherente con el principio de FP-03.
