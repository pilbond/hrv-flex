# FP-02 GAP-01 Incorporar GAP y VAM como capa analitica de terreno

## Objetivo

Incorporar `GAP` y `VAM` como capa analitica contextual para sesiones a pie dentro de `analysis`, sin convertirlos de entrada en parte estructural del contrato base de `sessions.csv`.

La idea no es inflar la tabla canonica con columnas repetitivas por km ni tratar `VAM` como una metrica universal plana, sino abrir una capa de lectura de terreno que permita interpretar mejor fatiga periferica, coste de subida y sostenimiento mecanico en carrera y hike.

## Por que en analysis y no en sessions.csv

- `sessions.csv` esta orientado a una fila estable por sesion.
- `GAP` por km o por intervalo tiene estructura interna variable.
- `VAM` solo tiene semantica fuerte en tramos de subida; como resumen bruto de sesion puede inducir ruido.
- `analysis` ya admite una lectura contextual de pendiente/terreno y es el sitio natural para explotar estas senales.

## Fuente de datos preferida

Fuente primaria: Intervals API.

Rutas validadas:

- `GET /activity/{id}` expone `gap` y `gap_model`
- `GET /activity/{id}/intervals` expone filas con:
  - `gap`
  - `average_gradient`
  - `average_speed`
  - `distance`
  - `elapsed_time`
  - `moving_time`
  - `total_elevation_gain`
  - `average_cadence`
  - `intensity`
  - `zone`

Hallazgo clave:

- `GAP` sale nativo en Intervals
- `VAM` no aparece nativo en la API probada, pero puede derivarse de forma limpia:
  - `vam_mh = total_elevation_gain / (elapsed_time / 3600)`

## Estado actual de implementacion

La tarea ya esta implementada en `analysis/` como tres capas incrementales:

- **V1** — contexto de sesion desde `GET /activity/{id}`
  - `gap_mean`
  - `gap_unit = km/h`
  - `gap_model`
- **V2** — capa Intervals por split/km desde `GET /activity/{id}/intervals`
  - `terrain_context`
  - `terrain_intervals.csv`
  - `GAP` por clase de terreno (`uphill`, `rolling`, `downhill`)
  - `VAM` solo en uphill filtrado
  - potencia por split cuando Intervals o el FIT permiten derivarla
- **V3** — capa FIT record-level paralela
  - `terrain_fit_context`
  - `terrain_climbs.csv`
  - climbs reales con `HR`, `cadence`, `power`, `grade_mean_pct` neto y validacion frente a V2

Outputs reales en `analysis/reports/<slug>/artifacts/`:

- `summary.json`
- `session_payload.json`
- `terrain_intervals.csv`
- `terrain_climbs.csv`

## Alcance propuesto

### V1 minima

Objetivo: habilitar lectura analitica util sin tocar aun `sessions.csv`.

Salida implementada en `analysis`:

- `gap_mean`
- `gap_unit`
- `gap_model`

Reglas:

- `GAP` se resume a nivel sesion, con unidad explicita
- `VAM` todavia no arbitra la V1; queda para la capa por intervalos/climbs

Filtro conservador para tramos uphill:

- `elapsed_time >= 60 s`
- `total_elevation_gain >= 10 m`
- `average_gradient >= 0.02`

### V2

Abrir una salida estructurada por intervalos o por km, separada del contrato base.

Salida implementada:

- `analysis/reports/<slug>/artifacts/terrain_intervals.csv`
- `terrain_context` dentro de `summary.json` y `session_payload.json`

Campos ya materializados o equivalentes:

- `distance_km`
- `elapsed_time_s`
- `pace_kmh`
- `gap_kmh` o `gap_mean`
- `average_gradient`
- `elev_gain_m`
- `vam_mh`
- `cadence`
- `power_mean`

Reglas activas:

- `GAP` se usa en `uphill`, `rolling` y `downhill`
- `VAM` se usa solo en `uphill`
- `power_mean` por split usa Intervals nativo si existe y, si no, fallback a ventana temporal del `FIT`

### V3

Salida implementada:

- `analysis/reports/<slug>/artifacts/terrain_climbs.csv`
- `terrain_fit_context` dentro de `summary.json` y `session_payload.json`

Contrato actual:

- no recalcula `GAP`
- detecta climbs desde `FIT` record-level
- prioriza `enhanced_altitude` sobre `altitude`
- usa validacion direccional contra V2
- expone `signals_available`, `cadence_unit = strides_per_min` y `validation_vs_v2`

## Decisiones de diseno

1. No canonizar `gap_km_1`, `gap_km_2`, etc. en `sessions.csv`.
2. No tratar `VAM` como metrica universal plana de sesion.
3. Usar `Intervals` como fuente primaria para esta capa, no Polar.
4. Mantener `GAP` y `VAM` como contexto analitico, no como base de gating HRV.
5. Separar `terrain_context` (Intervals) y `terrain_fit_context` (FIT) para no mezclar fuentes ni segmentaciones distintas.
6. No aplicar la capa a deportes no-a-pie ni a sesiones indoor/virtual/treadmill.

## Riesgos

- `GAP` en Intervals depende del `gap_model`; hay que conservarlo para trazabilidad.
- `VAM` puede contaminarse con intervalos mixtos si no se filtran bien las subidas.
- Una particion ciega por km sirve para `GAP`, pero no siempre para `VAM`.

## Relacion con otras tareas

- Depende funcionalmente de `AP-02`, porque reutiliza la apertura de la capa mecanica y el trabajo reciente con fuentes de Intervals/FIT.
- Tiene afinidad directa con `FP-01`, porque puede enriquecer la lectura de fatiga periferica en terreno variable.

## Criterio de aceptacion propuesto

1. Existe una extraccion reproducible de `GAP` desde Intervals para sesiones a pie.
2. Existe un calculo reproducible de `VAM` sobre tramos uphill filtrados.
3. La salida vive en `analysis` o en un artefacto analitico separado, no en columnas repetidas de `sessions.csv`.
4. La documentacion deja claro que `GAP` y `VAM` son contexto analitico y no arbitros del gate HRV.
5. `terrain_context` y `terrain_fit_context` quedan separados para preservar trazabilidad de fuente.
6. La capa no afecta negativamente a bike, swim ni indoor run; en esos casos queda `null` o no aplicable.
