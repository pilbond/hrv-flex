# SYA-02 Capa swim lite: sRPE, ritmo por vuelta, estilo y SWOLF

> Reescrita el 2026-11-06 tras evaluar la version anterior contra datos reales.
> Sustituye al alcance previo (parser por largo con fallback FIT/TCX y `swim_lengths.csv`).
> Sigue absorbiendo `TYM-02`: su semantica de `SWOLF` se conserva.

## Por que se reescribe

### Paso 0 parcial ya ejecutado (2026-11-06)

Se inspeccionaron los 8 FIT swim cacheados en `analysis/reports/**/swim_*/artifacts/session.fit`:

- todos son FIT **regenerados por Intervals.icu** (`file_id.product_name = Intervals.icu`), no el original de Polar,
- **ningun** FIT tiene mensajes `length`, ni `swim_stroke`, ni `length_type`,
- los `record` solo traen `heart_rate`, `temperature`, `timestamp` (sin distancia por segundo),
- todos declaran `sub_sport = open_water` aunque son sesiones de piscina,
- si hay `lap` (1-7 por sesion) con `total_distance`, `total_timer_time`, FC media/max/min y `SWOLF` (campo developer calculado por Intervals),
- `session` trae `SWOLF` global, `avg_cadence` y `avg_speed`.

Consecuencia: el fallback `fit_length_messages` del diseño anterior **no existe** con la fuente actual. La granularidad real disponible hoy es **por vuelta**, no por largo.

Ademas, la version anterior citaba `hrv_app/polar_client.py` y `/v3/exercises`, retirados en AYO-22.

### Perfil real de la natacion de este atleta

Datos de `ENDURANCE_HRV_sessions.csv` (2025-05-15 → 2026-11-05):

- 78 sesiones swim (13 % de sesiones, 6 % de la carga total),
- 71 `easy`, 5 `work_moderate`, 2 `finish_strong`; FC media ~115 bpm; ~1.5 km en ~47 min,
- RPE solo en 19/78 sesiones (media 4.2),
- las notas describen natacion de descarga / cross-training: "volumen suave sin cargar articulaciones", "evitar el calor", "no hacer crol me hace llevar mejor la sesion", "en los giros notaba las rodillas", y sensacion repetida de sesion "costosa",
- octubre 2026: 16 sesiones (bloque de sustitucion de impacto).

Lectura: `bajo_estimulo` cardio es mayoritariamente correcto. El hueco no es la eficiencia tecnica fina, sino:

1. la carga **percibida** (sesiones "costosas" con `cardio_score = 0`, FC de muneca debil en agua),
2. el **estilo** como contexto articular (patada de braza y rodilla),
3. la evolucion de **ritmo y SWOLF** como lectura de readaptacion,
4. el **papel de la natacion** como sustituto de impacto en la semana.

## Objetivo

Exponer en `analysis` un `swim_context` reproducible y prudente usando primero lo que ya existe (FIT por vuelta de Intervals + `sessions.csv`), y enriquecerlo con estilo solo si una fuente lo trae de verdad.

La integracion en `analysis/session_cost_model.py` (`swim_mechanical_score`) sigue **fuera de alcance**.

## Fases

### Fase A — Spike de fuentes (timebox 1-2 h)

Dump exploratorio de una sesion swim de referencia desde:

1. Polar AccessLink v4 `/training-sessions/list` (+ detalle/samples si existe) con el cliente `hrv_app/polar_client_v4.py`,
2. Intervals.icu `/activity/{id}/file` (archivo original subido, no el FIT regenerado),
3. campos de actividad de Intervals relacionados con natacion (`pool_length`, largos, brazadas, si existen).

Verificar en cada uno: `length` / largos, `swim_stroke`, `pool_length`, pausas, brazadas, y **como calcula Intervals su `SWOLF`** (de donde salen brazadas y longitud de piscina).

Salida: informe corto en `research/audits/swim_sources/` con la decision de fuente. Sin codigo de aplicacion.

### Fase B — Swim lite (no depende de A)

Desde el FIT por vuelta ya disponible y `sessions.csv`:

- `srpe_load` = RPE × duracion (min) cuando hay RPE; ancla de carga principal en swim dada la FC de muneca debil,
- `pace_per_100m` de sesion y por vuelta (con `total_timer_time` de vuelta),
- `pace_drift_pct`: primera vs ultima vuelta activa,
- `swolf_by_lap` (SWOLF de vuelta de Intervals) y `swolf_drift_pct` primera vs ultima vuelta,
- `hr_by_lap` solo como contexto, `hr_confidence = "low_wrist_in_water"`,
- `rpe_vs_cardio_discordance`: RPE ≥ 4 con `cardio_score = 0` → flag explicativo, no reclasificacion.

Contexto longitudinal y semanal:

- tendencia de `pace_per_100m` y `swolf` en las ultimas N sesiones comparables,
- en `weekly_coach.json`: proporcion de volumen swim frente a volumen de impacto (carrera/trail) como contexto de sustitucion; retrospectivo, sin tocar gate ni `reason_text`.

### Fase C — Estilo (solo si la Fase A encuentra dato directo)

- `stroke_distribution`, `primary_stroke`, `drill_lengths`,
- `breaststroke_pct` como contexto articular de rodilla,
- `swolf_by_stroke` cuando haya estilo por largo o por vuelta,
- `pool_length_m` desde la fuente.

Si la Fase A no encuentra estilo: no inferirlo. Alternativa barata a valorar con el humano: registrar estilo dominante en las notas de la sesion.

### Diferido (backlog)

- `dps_by_stroke`, `stroke_rate_by_stroke`,
- artifact por largo (`swim_lengths.csv`),
- reconstruccion TCX por mesetas de distancia.

## Contrato `swim_context`

```json
"swim_context": {
  "swim_source": "intervals_fit_laps",
  "granularity": "lap",
  "pool_length_m": null,
  "n_laps": 6,
  "pace_per_100m_s": 192.0,
  "pace_drift_pct": 4.1,
  "swolf_by_lap": [45.8, 44.8, 51.1],
  "swolf_session_note": "solo comparacion intra-sesion; estilo desconocido",
  "swolf_drift_pct": 11.6,
  "swolf_by_stroke": null,
  "srpe_load": 240,
  "rpe_vs_cardio_discordance": true,
  "stroke_distribution": null,
  "primary_stroke": null,
  "hr_confidence": "low_wrist_in_water",
  "signals_available": {
    "lap_structure": true,
    "lap_swolf": true,
    "stroke_type": false,
    "pool_length": false,
    "rpe": true
  }
}
```

Valores de `swim_source`: `polar_v4`, `intervals_original_file`, `intervals_fit_laps`, `none`.

## Reglas semanticas (heredadas de TYM-02 y ajustadas)

1. `SWOLF` solo es comparable **dentro del mismo estilo**.
2. No exponer el `SWOLF` global de sesion como metrica interpretable.
3. Sin dato de estilo, `SWOLF` por vuelta solo se usa para **comparacion intra-sesion** (deriva) y como tendencia longitudinal con `confidence = low` y nota `stroke_unknown`.
4. Con dato de estilo: `swolf_by_stroke`; `drill` excluido; estilo con pocos largos → `too_few_lengths`.
5. Comparaciones longitudinales de `SWOLF` solo con la misma `pool_length_m`; si es desconocida, marcarlo. No normalizar 25 m ↔ 50 m.
6. `SWOLF` alto no significa por si solo mas coste; puede reflejar ritmo, tecnica o contexto de serie (`SESSION_ANALYSIS_METHOD.md`).
7. FC de muneca en agua = contexto debil, nunca ancla primaria.
8. `sub_sport = open_water` del FIT de Intervals no es fiable: no usarlo para clasificar piscina / aguas abiertas.
9. Sin fuente usable: `swim_source = "none"`, continuar el pipeline sin crash.

## Riesgos

1. El `SWOLF` de Intervals puede depender de supuestos (longitud de piscina, brazadas derivadas de cadencia) no verificados → Fase A debe aclararlo antes de usarlo longitudinalmente.
2. RPE escaso (19/78) limita `srpe_load`; requiere registrar RPE de forma sistematica.
3. Pocas vueltas por sesion (a veces 1) → deriva no calculable; marcarlo explicitamente.

## Criterios de aceptacion

1. Informe de Fase A en `research/audits/swim_sources/` con decision de fuente.
2. `analysis` expone `swim_context` con `swim_source` y `granularity` para toda sesion swim, sin crash si falta dato.
3. `srpe_load`, `pace_per_100m`, `pace_drift_pct`, `swolf_by_lap` y `swolf_drift_pct` disponibles con la fuente actual.
4. `SWOLF` nunca se presenta como media global de sesion ni se compara entre estilos.
5. Estilo solo aparece si hay dato directo; nunca inferido.
6. Contexto semanal de proporcion swim / impacto visible en `weekly_coach.json` sin tocar gate, `FINAL`, `DASHBOARD` ni `reason_text`.
7. Sin cambios en `session_cost_model.py` en esta iteracion.

## Nota lateral

En los informes swim aparece `durability_context.confidence = high` sin stream de velocidad. Revisar por separado si la confianza esta inflada.
