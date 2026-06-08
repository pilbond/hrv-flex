
## Objetivo

Extender el detector de climbs de `fit_terrain_utils.py` (desarrollado en FP-02 V3) al deporte `bike`, de forma que sesiones de ciclismo con desnivel significativo dispongan de métricas de HR, cadencia y potencia por subida, y no solo de un resumen de sesión diluido por las bajadas.

El problema concreto que resuelve: el `session_cost_model` trabaja con métricas de sesión completa (`z2_pct`, `z3_pct`, `hr_p95`). En bicicleta con bajadas largas, la FC de sesión puede colapsar a valores de Z1 aunque las subidas hayan generado carga cardiovascular real en Z2-Z3. El sistema reporta `cardio_score=0` para sesiones de montaña de 2h con 800+ m D+ cuando la FC media es baja, aunque durante las subidas la FC estuvo consistentemente en Z2.

---

## Diagnóstico — el problema de la dilución de FC en bici

### Ejemplo observado: i138137906

Sesión de bici del 2026-04-08:

```
duration_min:  123 min
distance_km:   34.09 km
elev_gain_m:   879 m     ← ruta de montaña seria
D+/h:          439 m/h

avg_hr:        117 bpm
hr_p95:        138 bpm
vt1:           139 bpm   ← hr_p95 apenas toca el umbral Z1/Z2

z2_pct:        0.3%
z3_pct:        0.0%

cardio_score:  0          ← "sin señal cardiometabólica"
mecanico_score: 2         ← proxy D+/h, confidence_mecanico = medium
```

La lectura del sistema es `coste_dominante = mecanico` con `confidence_mecanico = medium` porque no hay potenciómetro. La señal cardiovascular de sesión es prácticamente invisible.

### Por qué ocurre

En una ruta de montaña con bici, la sesión alterna:
- **Subidas**: FC sube a 140-160 bpm (Z2-Z3), esfuerzo real sostenido
- **Bajadas**: FC cae a 90-110 bpm (Z1 profundo), manos en el manillar, esfuerzo mínimo

Si el recorrido tiene 50% de tiempo subiendo y 50% bajando, la FC media de sesión puede quedar en Z1 aunque el atleta haya estado en Z2 durante toda la hora que duró la subida principal.

El `z2_pct` de sesión no refleja el esfuerzo en subidas — lo **promedia** con las bajadas.

### Analogía con trail run

En trail run, el mismo fenómeno es menos severo porque los tiempos de bajada son menores en proporción, la FC no cae tan rápido y los splits de Intervals suelen capturar los tramos de subida. En bici de montaña, el efecto es sistemático y persistente.

---

## Solución propuesta

### Principio

FP-02 V3 ya resuelve el problema técnico para trail run: el detector FIT de climbs calcula `hr_mean`, `hr_max` por cada subida detectada. La infraestructura existe. El único bloqueo es que `_supports_terrain_context()` excluye `bike`.

La propuesta es **extender ese soporte a bike** con los ajustes mínimos necesarios para ese deporte.

### Lo que NO cambia

- El contrato de `session_cost_model` no se toca en esta iteración
- `sessions.csv` no añade columnas nuevas
- El gate HRV no recibe ninguna señal nueva
- `terrain_context` (V2, Intervals splits) sigue desactivado para bike (GAP y modelo `STRAVA_RUN` no aplican a ciclismo)

### Lo que SÍ cambia

- `terrain_fit_context` y `terrain_climbs.csv` se generan para sesiones de bike con GPS y altitud
- El report técnico incluye la sección "Terrain FIT Context" para bike
- `cadence_unit` para bike se expone como `rpm` en lugar de `strides_per_min`

---

## Alcance por iteraciones

### Iteración A — Activar V3 FIT en bike (mínima)

**Cambio en código:**

```python
# session_analysis_pipeline.py
def _supports_terrain_context(row: dict[str, str]) -> bool:
    return analyzer_sport_from_session(row) in {"road", "trail", "hike", "bike"}
    #                                                                     ^^^^^^ añadir
```

Con ese cambio, el pipeline ya genera `terrain_climbs.csv` y `terrain_fit_context` para sesiones de bike que tengan GPS + altitud en el FIT.

**Ajuste de `cadence_unit`:**

```python
# fit_terrain_utils.py o session_analysis_pipeline.py
cadence_unit = "rpm" if sport_family == "bike" else "strides_per_min"
```

**Salida esperada para i138137906:**

```
terrain_climbs.csv:
  climb 1: 15 min, 180m D+, grade 5.2%, hr_mean=148, hr_max=158, power_mean=195 (si potenciómetro)
  climb 2: 22 min, 240m D+, grade 6.1%, hr_mean=153, hr_max=162
  ...
terrain_fit_context:
  climb_count:        4
  climb_time_min:     62.0   ← 52% de los 120 min de sesión
  climb_gain_m:       830.0  ← 94% del D+ total
  climb_hr_mean:      149.5  ← vs session avg_hr=117
  climb_power_mean:   null   ← sin potenciómetro
  signals_available:  {hr: true, cadence: true, power: false}
  cadence_unit:       rpm
```

El analista puede leer: "el sistema reporta `cardio_score=0` porque la sesión completa está en Z1, pero durante 62 min de subidas (52% del tiempo) la FC media fue 149 bpm, por encima de vt1=139". Eso es coste cardiovascular real.

**Validación:** misma lógica que trail run — comparar `climb_time_min` y `climb_gain_m` contra los splits de V2 si estuvieran disponibles. Como V2 está desactivado para bike, la validación se hace contra `session_elev_gain_m` con `climb_gain_coverage_pct`.

---

### Iteración B — Distribución de zonas por subida (valor analítico alto)

Una vez activada la iteración A, los registros FIT por climb ya están disponibles en memoria durante el análisis. Con los umbrales `vt1`/`vt2` del `session_row`, es posible calcular la distribución de zonas **dentro de cada subida**:

```python
for sample in climb_records:
    if sample["hr"] >= vt2:    z3 += 1
    elif sample["hr"] >= vt1:  z2 += 1
    else:                       z1 += 1

climb["z1_pct"] = z1 / total * 100
climb["z2_pct"] = z2 / total * 100
climb["z3_pct"] = z3 / total * 100
climb["z2_min"] = z2 / sample_rate / 60.0
climb["z3_min"] = z3 / sample_rate / 60.0
```

Y en `terrain_fit_context`:
```
total_climb_z2_min: 38.4
total_climb_z3_min: 12.1
climb_cardio_signal: "z2_dominant"   # clasificación derivada
```

**Extensión opcional al cost model (futura, no en esta tarea):**

Si en iteraciones posteriores se decide mejorar el cost model para bike, la señal `total_climb_z2_min` sería la evidencia adicional:

```
cardio_evidence: [
    "climb_z2_min = 38.4 (terrain_fit_context)"  ← nuevo, alternativo al z2_pct de sesión
]
```

Esto requeriría un cambio de contrato en `session_cost_model`. Queda **explícitamente fuera del alcance de FP-03**; se documenta aquí como vía natural de evolución.

---

## Decisiones de diseño

1. **V2 (Intervals splits / GAP) permanece desactivado para bike.** `GAP` con modelo `STRAVA_RUN` no tiene semántica para ciclismo. Activar V2 para bike requeriría un modelo de corrección de velocidad por pendiente para ciclismo, que no existe en los datos actuales.

2. **`cadence_unit = "rpm"` para bike.** La cadencia en ciclismo es pedaleo por minuto (RPM), no zancadas. El campo `cadence_unit` ya existe en `terrain_fit_context`; solo hay que asignar el valor correcto según deporte.

3. **Thresholds de detección de climbs sin cambio en iteración A.** Los parámetros actuales (`grade >= 3%`, `duration >= 60s`, `distance >= 150m`, `elev_gain >= 10m`) son razonables para ciclismo de montaña. En ciclismo de carretera o pistas, algunas subidas cortas y empinadas podrían perderse. Se revisa con datos reales en iteración A antes de tocar los parámetros.

4. **Sesiones indoor / cicloergómetro excluidas de facto.** Si el FIT de una sesión indoor no tiene altitud GPS (caso habitual en Zwift o rodillo), `_prepare_active_records` filtrará los registros sin altitud y el análisis fallará con `terrain_fit_error = "fit terrain analysis requires at least 2 active records with distance and altitude"`. Comportamiento correcto y ya validado en i131932523 (indoor running).

5. **`terrain_fit_context` y `terrain_context` son capas independientes.** Para bike: `terrain_context` = absent, `terrain_fit_context` = present (si GPS OK). Para trail/road: ambas presentes.

---

## Riesgos

| Riesgo | Probabilidad | Mitigación |
|---|---|---|
| FIT de bici outdoor sin `enhanced_altitude` barométrica | Baja — Garmin y Wahoo lo incluyen siempre; Polar variable | Verificar en i138137906 antes de cerrar iteración A |
| Thresholds de climb inadecuados para ciclismo de carretera (subidas largas y suaves) | Media | Revisar con 3-4 sesiones de carretera; ajustar `CLIMB_MIN_GRADE` si procede |
| Rutas con bajadas muy largas: V3 detecta correctamente 0 climbs y dispara `warn_low_climb_coverage` | Alta si D+ < 30m | Ya corregido en los fixes post-análisis multi-sesión |
| Potenciómetro ausente: `power_available=false` en la mayoría de sesiones bike | Alta | `power_mean=null` en `terrain_climbs.csv`; `signals_available.power=false` en contexto; no es un error |
| VAM en ciclismo: semánticamente diferente de VAM en trail | Baja impacto | VAM se expone como dato, no se interpreta automáticamente en esta iteración |

---

## Relación con otras tareas

- **Depende de FP-02** (completada): la infraestructura de `fit_terrain_utils.py`, `terrain_climbs.csv` y `terrain_fit_context` existe y está validada. FP-03 es una extensión, no una reimplementación.
- **Complementa FP-01**: FP-01 busca señal de sostenimiento mecánico en sesiones largas. Para bike con potenciómetro, FP-03 aporta potencia por subida que FP-01 podría consumir como señal de durabilidad mecánica en tramos de subida (vía futura, no en esta tarea).
- **No bloquea ni depende de DO-02, SS-01 ni AP-03.**

---

## Criterios de aceptación

### Iteración A

1. `terrain_climbs.csv` se genera para sesiones de bike con GPS + altitud en el FIT.
2. `terrain_fit_context` aparece en `summary.json` y en `technical_report.md` para bike.
3. `cadence_unit = "rpm"` en `terrain_fit_context` para bike.
4. Sesiones indoor de bike (sin GPS/altitud) producen `terrain_fit_error` sin crash, igual que ya ocurre con indoor running.
5. Sesiones de swim y otros deportes no soportados no se ven afectadas.
6. Validado con al menos 3 sesiones de bici outdoor de perfil variado.

### Iteración B (alcance extendido, opcional)

7. `terrain_climbs.csv` incluye `z1_pct`, `z2_pct`, `z3_pct`, `z2_min`, `z3_min` por climb.
8. `terrain_fit_context` incluye `total_climb_z2_min`, `total_climb_z3_min`, `climb_cardio_signal`.
9. Los campos de zona por climb son `null` si `vt1`/`vt2` no están disponibles en el `session_row`.

---

## Nota sobre el cost model

FP-03 **no modifica `session_cost_model`**. La señal de `terrain_fit_context` queda disponible como contexto adicional para el analista (humano o agente). Si en el futuro se decide que `total_climb_z2_min` debe influir en `cardio_score` para bike, ese cambio requiere una tarea separada con revisión de contrato explícita.

El objetivo de FP-03 es hacer visible lo que ya está pasando fisiológicamente, no cambiar los gatings actuales.
