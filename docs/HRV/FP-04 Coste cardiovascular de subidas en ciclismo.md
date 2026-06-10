# FP-04 Coste cardiovascular de subidas en ciclismo

> Tarjeta Kanvas: `FP-04` — grupo `Terreno / Perfomance`, estado `purple` (propuesta).
> Documento base predecesor: [FP-03 Coste cardiovascular de subidas en ciclismo.md](FP-03%20Coste%20cardiovascular%20de%20subidas%20en%20ciclismo.md)

## Texto de la tarjeta

Objetivo: extender la capa FIT de terreno a bike para exponer coste cardiovascular por subida y hacer visible la FC real de las subidas, sin tocar `session_cost_model`, `sessions.csv` ni el gate HRV.

V1 ejecutable: `matched_climbs` sobre `terrain_fit_context` para bike. `grade_bins` queda como evolucion posterior si hace falta mas granularidad.

Relacion: no mezclar con la linea de run contextual; debe vivir en su propia tarjeta y su propio documento.

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
