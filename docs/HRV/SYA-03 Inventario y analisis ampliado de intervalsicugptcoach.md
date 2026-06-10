
## Objetivo

Crear una tarea separada para inventariar, recuperar y comparar en detalle las metricas que aparecen en los JSON de `intervalsicugptcoach` y que hoy no forman parte del contrato canonico del repo.

La tarea no busca cambiar el gate HRV ni introducir de golpe nuevas columnas en `sessions.csv`. El objetivo es:

1. entender que parte del JSON es dato bruto de Intervals,
2. que parte proviene de FIT / streams / intervalos,
3. que parte es inferencia del coach,
4. y decidir despues que vale la pena canonizar, dejar solo en `analysis/`, o ignorar.

## Resumen ejecutivo del roadmap formal

Este documento contiene dos secuencias distintas de fases y no deben confundirse:

1. **Fases de investigacion de la propia tarea**
   Sirven para ordenar el trabajo exploratorio del informe.
2. **Roadmap formal de implementacion**
   Sirve para decidir como se incorporan, validan o descartan las metricas en el repo.

El roadmap formal completo tiene **5 fases**:

1. **Fase 1 — Extraccion minima canonica**
2. **Fase 2 — Validacion semantica y backtest de campos ambiguos**
3. **Fase 3 — Enriquecimiento analitico no canonico**
4. **Fase 4 — Senales compuestas validadas**
5. **Fase 5 — Consolidacion longitudinal y especializacion por deporte**

La seccion normativa y operativa que debe leerse como referencia principal es:

- `6.b Roadmap formal por fases`

## Estado de cierre 2026-04-29

Fases cerradas y ya materializadas en codigo:
- `SYA-04 / Fase 1`: extraccion minima canonica en `build_sessions.py`
- `SYA-05 / Fase 2`: validacion semantica y backtest de campos ambiguos
- `SYA-06 / Fase 3`: enriquecimiento analitico no canonico en `analysis/`
- `SYA-07 / Fase 4`: senales compuestas validadas en `analysis_only_context`
- `SYA-08 / Fase 5`: consolidacion longitudinal y especializacion por deporte en `analysis/`

Estado operativo final por capa:
- `sessions.csv` ya canoniza primitivas de sesion y la capa mecanica minima, pero no introduce ninguna columna longitudinal nueva por `SYA-08`
- `sessions_day.csv` sigue siendo capa de carga y distribucion semanal; no absorbe baseline longitudinal subjetivo/termico ni benchmark de ruta
- `analysis/session_analysis_pipeline.py` es la capa destino final de `SYA-08`

Verificacion funcional de `SYA-08`:
- historial mixto de deportes verificado: `build_longitudinal_context(...)` filtra por deporte y no mezcla sesiones ajenas
- render del reporte verificado con `sport_baseline.highlight` presente y ausente; el bloque longitudinal se dibuja una sola vez y el anclaje propio solo aparece cuando existe highlight
- cobertura mixta verificada: `route_benchmark` puede activarse sin datos de `climb`, y `climb_economy_trend` queda `None` sin romper el payload ni el reporte

Modelo longitudinal final aprobado para `SYA-08`:
- `sport_baseline`: comparativa contra baseline propio por deporte
- `subjective_chronic_context`: lectura cronica de coherencia subjetiva/objetiva
- `thermal_sensitivity_context`: lectura longitudinal de coste termico individual
- `route_history`: comparativa tactica con la sesion previa de la misma ruta
- `route_benchmark` y `climb_economy_trend`: solo cuando la repeticion de ruta alcanza cobertura suficiente

Limites reales de cobertura observados en la auditoria `2026-04-29`:
- `trail_run`: baseline y lectura cronica si; benchmark por ruta no
- `road_run`: baseline y lectura cronica si; benchmark por ruta no
- `bike`: baseline y lectura cronica si; benchmark por ruta solo de forma puntual
- resto de deportes: fuera del objetivo fuerte de especializacion o sin cobertura suficiente

Decision de contrato:
- `SYA-08` queda cerrado como capa `analysis-only`
- no se toca `build_sessions.py` por esta fase
- no se actualiza `docs/contracts/` porque no cambia el contrato operativo ni el gate HRV

## Inventario maestro cerrado 2026-04-30

Este documento queda cerrado como inventario maestro de `SYA-03`.

Regla de lectura:

- si una seccion exploratoria antigua contradice este bloque, manda este bloque
- si sigue habiendo duda, mandan `6.b Roadmap formal por fases` y el contrato activo de `sessions.csv`

Estado final por capa y familia:

| Familia / campo | Estado final | Capa destino al cierre |
| --- | --- | --- |
| `trimp`, `calories`, `average_cadence`, `hrr_drop_bpm`, `average_weather_temp` | implementado | `sessions.csv` |
| `icu_weighted_avg_watts`, `icu_joules_above_ftp`, `icu_max_wbal_depletion`, `decoupling` | implementado con gate `device_watts` | `sessions.csv` |
| `session_rpe`, `icu_intensity`, `polarization_index`, `average_stride` | validados o reevaluados, pero no promovidos a contrato | `analysis/` |
| `icu_intervals`, `icu_groups`, `icu_achievements`, `coach_metrics`, `coach_intervals.csv`, `coach_groups.csv` | implementado como enriquecimiento local reproducible | `analysis/` |
| `subjective coherence`, `load mismatch`, `thermal_context`, primitivas de durabilidad por tercios | implementado como senal compuesta local | `analysis/` |
| `sport_baseline`, `subjective_chronic_context`, `thermal_sensitivity_context`, `route_history`, `route_benchmark`, `climb_economy_trend` | implementado como consolidacion longitudinal por deporte | `analysis/` |
| `icu_atl`, `icu_ctl`, `icu_ftp`, `icu_resting_hr`, `hr_load`, `route_id` | no canonizar como dato de sesion | fuera de `sessions.csv`; uso local o contextual |
| `icu_zone_times`, `icu_pm_*`, `icu_rolling_*`, `RunningIndex`, `GAPOverAvgHR` | no canonizar | `analysis/` o descarte |

Estado final del roadmap:

- `SYA-04` cerro la extraccion minima canonica y ya esta reflejada en `build_sessions.py` y `docs/contracts/`
- `SYA-05` cerro que `session_rpe`, `icu_intensity` y `polarization_index` no debian pasar a contrato canonico por ahora
- `SYA-06` cerro la capa `analysis_only_context` y sidecars coach como destino natural de estructuras ricas
- `SYA-07` cerro las senales compuestas locales sin invadir `sessions.csv`
- `SYA-08` cerro la consolidacion longitudinal y especializacion por deporte como capa `analysis-only`
- `SYA-09` queda como dependiente natural para decidir el impacto semanal; no reabre decisiones de inventario maestro
- `SYA-10` queda como backlog diferido de ideas retrospectivas o HRV longitudinal no absorbidas por `SYA-07/08`

## Por que esta tarea debe existir aparte

Los JSON de `intervalsicugptcoach` mezclan varias capas:

- actividad base de Intervals,
- agregados de intervalos y grupos,
- streams de FIT / sensores,
- y metricas derivadas del motor de coaching.

Eso hace que no sea seguro tratarlos como una unica fuente canonica. Si se mezclan demasiado pronto con `build_sessions.py`, el riesgo es introducir metricas opacas en la capa operativa antes de saber si son:

- reproducibles,
- consistentes entre deportes,
- o utiles de verdad para decisions de carga / recuperacion.

Por tanto, esta tarea debe quedarse en una capa de semantica y analisis.

## Fuentes observadas

### Trail run

En el ejemplo de `TrailRun` aparecen estas familias de datos:

- actividad base: `icu_training_load`, `icu_atl`, `icu_ctl`, `icu_ftp`, `icu_weight`, `distance`, `moving_time`, `average_heartrate`, `average_cadence`, `calories`, `gap`, `gap_model`, `route_id`, `external_id`
- potencia y dinamica: `icu_weighted_avg_watts`, `icu_average_watts`, `icu_variability_index`, `icu_efficiency_factor`, `icu_power_hr`, `icu_power_hr_z2`, `icu_power_hr_z2_mins`, `icu_cadence_z2`, `fractional_utilizationusing6mPower`
- modelos de potencia: `icu_pm_cp`, `icu_pm_w_prime`, `icu_pm_p_max`, `icu_pm_ftp`, `icu_pm_ftp_secs`, `icu_pm_ftp_watts`, `icu_rolling_w_prime`, `icu_rolling_p_max`, `icu_rolling_ftp`, `icu_rolling_ftp_delta`, `icu_w_prime`, `p_max`
- carga y sensacion: `trimp`, `icu_intensity`, `session_rpe`, `feel`, `strain_score`, `power_load`, `hr_load`, `hr_load_type`
- contexto fisiologico y tecnico: `decoupling`, `icu_hrr`, `polarization_index`, `icu_hr_zone_times`, `icu_zone_times`, `average_stride`, `RunningIndex`, `GAPOverAvgHR`
- segmentos: `icu_intervals`, `icu_groups`, `icu_achievements`
- contexto externo: temperatura, viento, nubosidad, lluvia, nieve

### Ride

En el ejemplo de ciclismo aparecen estas familias:

- actividad base: `icu_training_load`, `icu_atl`, `icu_ctl`, `icu_ftp`, `distance`, `moving_time`, `average_speed`, `average_heartrate`, `average_cadence`, `calories`
- carga y percepcion: `trimp`, `icu_intensity`, `session_rpe`, `feel`, `hr_load`, `hr_load_type`, `polarization_index`
- recuperacion / contexto: `icu_hrr`, `icu_hr_zones`, `icu_median_time_delta`, `average_weather_temp`, viento, nubes
- segmentacion: `interval_summary`, `icu_intervals`, `icu_groups`
- clasificacion de sesion: `session_classification`, `key_blocks_analysis`, `durability_assessment`, `coaching_readout`
- contexto de atleta: `weight_kg`, `resting_hr_bpm`, `lthr_bpm`, `max_hr_bpm`, `power_zones_pct`, `sweet_spot_pct`

## Lo que el repo ya recupera hoy

El repo actual ya absorbe estas capas de forma explicita:

- contrato canonico de sesion en `sessions.csv`, incluyendo `load`, `rpe`, `feel`, FC, zonas HR, mecanica minima y la extraccion minima canonica cerrada por `SYA-04`
- contexto rolling en `sessions_day.csv`, incluyendo carga, clustering e intensidad/distribucion por familia
- capa local `analysis/`, donde viven `analysis_only_context`, sidecars coach, senales compuestas y consolidacion longitudinal

Archivos clave:

- `build_sessions.py`
- `analysis/session_analysis_pipeline.py`
- `analysis/training_audit_utils.py`
- `docs/contracts/ENDURANCE_HRV_Sessions_Schema.md`

Punto importante:

- `build_sessions.py` es la pieza canonica para extraer y persistir campos de Intervals en el pipeline de sesiones
- `analysis/session_analysis_pipeline.py` es la pieza canonica para consumir datos coach/Intervals ricos sin convertirlos en contrato operativo global

## Lo que no estamos canonizando hoy

Al cierre de `SYA-03`, estos grupos siguen fuera del contrato operativo canonico de `sessions.csv`:

- `session_rpe`
- `icu_intensity`
- `polarization_index`
- `average_stride`
- `icu_average_watts`, `icu_variability_index`, `icu_efficiency_factor`
- `icu_power_hr`, `icu_power_hr_z2`, `icu_power_hr_z2_mins`
- `icu_pm_cp`, `icu_pm_w_prime`, `icu_pm_p_max`
- `icu_rolling_w_prime`, `icu_rolling_p_max`, `icu_rolling_ftp`, `icu_rolling_ftp_delta`
- `icu_w_prime`, `p_max`
- `RunningIndex`
- `GAPOverAvgHR`
- `fractional_utilizationusing6mPower`
- `icu_intervals`, `icu_groups`, `icu_achievements` como estructuras permanentes
- contexto ambiental detallado mas alla de `average_weather_temp`, si no se usa despues para analisis especifico

Nota de cierre:

- `trimp`, `decoupling`, `icu_weighted_avg_watts`, `icu_joules_above_ftp`, `icu_max_wbal_depletion`, `calories`, `average_cadence`, `hrr_drop_bpm` y `average_weather_temp` ya no pertenecen a esta lista porque quedaron cerrados en Fase 1 y estan implementados en `sessions.csv`

## Lectura tecnica preliminar

### 1. Algunas metricas parecen derivadas directas

En el trail run, varios ratios encajan matematicamente con los numeros del JSON:

- `icu_variability_index` parece ser `weighted_avg_watts / average_watts`
- `icu_efficiency_factor` parece ser `weighted_avg_watts / average_hr`
- `icu_power_hr` parece ser `average_watts / average_hr`

Eso sugiere que parte del bloque coach no es un dato independiente, sino una composicion sobre potencia media, potencia ponderada y FC media.

### 2. Otras metricas parecen modeladas

El bloque:

- `icu_pm_cp`
- `icu_pm_w_prime`
- `icu_rolling_w_prime`
- `icu_rolling_p_max`
- `icu_pm_ftp`
- `icu_pm_ftp_watts`
- `p_max`
- `W'bal`

parece venir de un modelo de potencia-duracion / critical power interno del coach.

Es probable que sea util, pero no deberia canonizarse sin antes responder:

- como se calcula exactamente,
- si es estable entre deportes,
- si cambia con la cobertura de potencia,
- y si aporta algo por encima de los derivados que ya tenemos.

### 3. Parte de la salida es estructura, no solo metricas

`icu_intervals` y `icu_groups` no son solo una lista:

- llevan potencia,
- cadencia,
- stride,
- torque,
- distancia,
- elevacion,
- y `wbal` en el caso de carrera.

Eso los convierte en una fuente de analisis de bloque muy rica, pero tambien en un riesgo de sobrecanonizar estructuras demasiado detalladas sin un caso de uso claro.

## Comparacion por deporte

### Trail run

Lo mas interesante del trail run es:

- `decoupling`
- `average_stride`
- `average_cadence`
- `trimp`
- `session_rpe`
- `icu_weighted_avg_watts`
- `icu_efficiency_factor`
- `icu_variability_index`
- `icu_power_hr`

Lectura:

- aqui hay una mezcla buena entre carga interna, coste mecanico y estructura de intensidad;
- es el caso mas prometedor para estudiar si `GAP + run_power + coach analytics` aportan mas que los proxies actuales.

### Ride

Lo mas interesante del ride es:

- `trimp`
- `session_rpe`
- `polarization_index`
- `average_cadence`
- `icu_hrr`
- `icu_intensity`
- `key_blocks_analysis`
- `durability_assessment`

Lectura:

- en bici, el valor no parece estar tanto en potencia pura sino en la combinacion de carga, polarizacion y durabilidad de bloques;
- `average_stride` y `GAPOverAvgHR` parecen mucho menos prioritarios aqui.

## Hipotesis de trabajo iniciales

Estas hipotesis sirvieron para abrir `SYA-03` y ya no sustituyen el estado final cerrado arriba:

1. `load`, `rpe`, `feel`, `trimp`, `session_rpe` y `polarization_index` son candidatos mas razonables para analisis que `W'bal` o `RunningIndex`.
2. `decoupling`, `average_cadence` y `average_stride` parecen muy prometedores en trail run.
3. `icu_weighted_avg_watts` era mas valioso que una media simple y acabaria cerrandose como columna canonica condicional en `sessions.csv`.
4. `icu_intervals` y `icu_groups` deben seguir siendo una capa de analisis, salvo que se encuentre una forma estable de resumirlas.
5. La decision de canonizar debe hacerse por deporte y por utilidad real, no por abundancia de campos.

## Fases de investigacion de esta tarea

Estas fases son metodologicas y sirvieron para estructurar el analisis del informe.
No son el roadmap formal de implementacion del repo.

### Fase 1. Inventario y normalizacion

Crear un inventario estructurado de campos por:

- deporte,
- fuente probable,
- tipo de dato,
- y nivel de confianza.

Clasificacion minima:

- dato directo de actividad,
- dato derivado de stream / FIT,
- dato derivado de intervalos,
- dato derivado del coach,
- dato de analisis retrospectivo.

### Fase 2. Recuperacion reproducible

Definir donde guardar la version raw o semi-raw del payload sin tocar el contrato canonico.

La salida deberia permitir responder:

- que campos llegan siempre,
- cuales son dependientes del deporte,
- cuales dependen de tener FIT,
- y cuales dependen de un motor coach interno.

### Fase 3. Backtest semantico

Comparar las metricas nuevas con lo que ya existe en:

- `sessions.csv`
- `sessions_day.csv`
- `analysis/` terrain outputs

Preguntas:

- `trimp` o `session_rpe` explican mejor la carga que `load`?
- `polarization_index` aporta algo por encima de nuestra distribucion de intensidad?
- `decoupling` y `efficiency_factor` mejoran la lectura de trail run?
- `icu_groups` ayuda a describir bloques utiles o solo añade ruido?

### Fase 4. Decision de canonizacion

Salida posible por campo:

1. canonico en `sessions.csv`
2. solo en `analysis/`
3. solo como investigacion
4. descartar

## Criterios de aceptacion

1. Existe un inventario claro de campos de `intervalsicugptcoach` por deporte.
2. Se distinguen con claridad los campos directos, derivados y coach-only.
3. Se documenta que campos valen como candidatos serios para futura canonizacion.
4. Se mantiene fuera de `sessions.csv` todo lo que aun no tenga justificacion operativa suficiente.
5. La comparacion deja claro que no se esta mezclando esta tarea con `AP-03`.

## Riesgos

- Sobrecargar la capa operativa con metricas opacas.
- Confundir derivaciones del coach con datos primarios.
- Introducir duplicados semanticos de carga o intensidad.
- Asumir que una metrica util en trail run lo sera tambien en bike.

---

## Analisis Gap Detallado — v2 (2026-04-16, corregido tras revision externa)

> Esta seccion reemplaza la version inicial. Se corrigen 5 errores facticos identificados por revision externa: clasificacion de `icu_hrr`, formula de `session_rpe`, tipado de `icu_intensity` y `polarization_index`, relacion entre `decoupling` y `cardiac_drift_pct`, e impacto contractual de canonizar en `sessions.csv`.

### 1. Lo que ya capturamos bien (sin gaps)

El sistema actual en `build_sessions.py` + `analysis/` cubre solidamente:

- **Zonas HR** (Z1/Z2/Z3 sobre moving_time) — 3-zona fisiologica propia, sin equivalente directo en ICU
- **Work blocks** con merge inteligente — mas sofisticado que interval grouping de Intervals
- **Cardiac drift** (`cardiac_drift_pct`) — HR vs velocidad; complementario, NO equivalente a `decoupling` de ICU (ver seccion 3)
- **Late intensity** — sin equivalente directo en intervalsicugptcoach
- **Clasificacion de sesion** (intensity_category, session_group) — comparable
- **Esfuerzo relativo** (effort_vs_recent, effort_vs_anchor) — propio, no existe en coach externo
- **RR/HRV per-session** (RMSSD, DFA-alpha1) — nuestro sistema lo tiene, coach no
- **Terrain layers** (FP-02) — tenemos climb detection desde FIT
- **Contexto rolling** (sessions_day.csv) — ACWR, monotony, strain, clustering

### 2. Clasificacion en 4 categorias semanticas

Antes de decidir que canonizar, cada campo se clasifica segun su naturaleza:

| Categoria | Criterio | Destino natural |
|------|----------|-----------------|
| **session-level** | Dato propio de esta sesion, no derivable de campos existentes | Candidato a `sessions.csv` |
| **athlete-day context** | Estado del atleta ese dia; no es de la sesion sino del atleta | Consultable pero no canonizar en sessions |
| **derived-duplicate** | Calculable desde campos que ya tenemos, o semantica solapada; requiere verificacion | Evaluar si aporta sobre lo existente |
| **analysis-only** | Rico pero dependiente de potenciometro, modelado coach, o estructura opaca | Queda en `analysis/`, no en sessions |

### 3. Campos del payload por categoria semantica — datos del dump real

> Dump: `GET /athlete/{id}/activities?oldest=2026-04-14&newest=2026-04-16` — 3 actividades, 175 campos por actividad. Ver `research/archive/new/intervals_activities_dump.json`.

#### Categoria session-level — candidatos a sessions.csv

Campos que describen esta sesion especifica, con semantica clara y no duplicada:

| Campo API | Escala real (dump) | Qué aporta | Condicional |
|-----------|-------------------|------------|-------------|
| `trimp` | float (ej: 97.93, 168.81) | Carga TRIMP (Banister): duracion × intensidad HR. Tercera senal de carga independiente de HRSS y session_rpe. | No |
| `calories` | int (ej: 969) | Gasto calorico. Presente siempre. | No |
| `average_weather_temp` | float (ej: ~18°C) | Temperatura ambiente media. Contexto para anomalias de FC. Solo si `has_weather=true`. | Si (`has_weather`) |
| `icu_hrr` → `hrr_drop_bpm` | dict nested `{hrr: 48, start_bpm: 167, end_bpm: 119}` | Caida FC en ~60s post-pico. Marcador parasimpatico intra-sesion. **Llega en el listado cuando hay dato**; null si no hay pico medible. | Si (condicional) |
| `average_cadence` | float (ej: 88.16 rpm) | Ya parcial via FIT. La API lo da siempre que hay sensor. | Si (consolidar con FIT) |
| `icu_weighted_avg_watts` | float (null si sin potenciometro) | Potencia normalizada (NP). Solo util con `device_watts=true`. | Si (`device_watts`) |
| `icu_joules_above_ftp` | float (null si sin potenciometro) | Trabajo anaerobico en julios. | Si (`device_watts`) |
| `icu_max_wbal_depletion` | float (null si sin potenciometro) | Pico de vaciado W'. | Si (`device_watts`) |
| `decoupling` | float (null si sin potenciometro; ej: 15.76 en trail con potencia) | **Deriva HR/potencia** (no HR/velocidad). Complementa `cardiac_drift_pct`, no lo reemplaza. Solo util con `device_watts=true`. | Si (`device_watts`) |

#### Categoria athlete-day context — NO canonizar en sessions.csv

Datos del atleta ese dia; no son de la sesion. Ya los tenemos en parte via wellness o son redundantes con sessions_day.csv:

| Campo API | Por que no canonizar |
|-----------|---------------------|
| `icu_atl` | ATL (fatiga aguda ICU). Equivalente conceptual a nuestro rolling de carga en sessions_day. Poner en sessions multiplicaria el contexto sin justificacion. |
| `icu_ctl` | CTL (fitness cronica ICU). Misma razon. |
| `icu_ftp` | FTP vigente ese dia segun ICU. Util como referencia, pero es configuracion del atleta, no resultado de la sesion. |
| `icu_resting_hr` | FC reposo del dia. Ya viene de wellness si se captura ahi. |
| `hr_load` | HRSS de ICU. Semanticamente equivalente a `icu_training_load` que ya capturamos como `load`. |
| `route_id` | Identificador de ruta. Util para analisis de ruta repetida, pero requiere sistema de lookup; no aporta solo. |

#### Categoria derived-duplicate — verificar antes de decidir

Campos cuya semantica o formula solapan con lo que ya tenemos, o requieren validacion:

| Campo API | Escala real (dump) | Problema semantico | Estado |
|-----------|-------------------|-------------------|--------|
| `icu_intensity` | **float 0-100** (ej: 53.0, 73.47, 31.87) — escala porcentual, **NO [0,1]** | IF% (intensidad relativa a FTP/LTHR). Util, pero requiere entender que 53 = 53%, no 0.53. Si se canoniza, documentar escala. | Verificar si aporta sobre `intensity_category` |
| `polarization_index` | **float sin tope superior claro; en backtest real puede ser negativo** (ej: 0.0, 1.94, -1.17) | Indice de polarizacion ICU. Logica no documentada publicamente. En el historico real se observa fuerte masa en `0`, algunos valores >1 y casos negativos, por lo que no debe asumirse dominio `>= 0`. | Verificar formula antes de canonizar |
| `session_rpe` | int (ej: 356, 655, 159) | **Formula real: `moving_time_min × icu_rpe`** (no `load × RPE`). Verificado: 7137/60×3=356.85, 5622/60×7=655.9, 3190/60×3=159.5. Modelo Foster de carga percibida basada en duracion. **No es trivial**: es una tercera senal de carga (junto a HRSS y TRIMP) desde la percepcion del atleta. | Reevaluar; puede complementar `trimp` |
| `icu_variability_index` | float (null sin potenciometro) | NP/AP ratio. Derivable de `icu_weighted_avg_watts / icu_average_watts` si tenemos ambos. | Solo con `device_watts`; por defecto queda en `analysis/` salvo caso fuerte a favor |
| `icu_efficiency_factor` | float (null sin potenciometro) | NP/HR. Derivable de `icu_weighted_avg_watts / average_heartrate`. | Solo con `device_watts`; por defecto queda en `analysis/` salvo caso fuerte a favor |

#### Categoria analysis-only — NO canonizar en sessions.csv

Campos ricos pero que violan el contrato v1 de sessions.csv, dependen de potencia, o requieren modelado coach:

| Campo | Por que analysis-only |
|-------|-----------------------|
| `icu_zone_times` (7 zonas de potencia) | El contrato v1 de sessions.csv dice explicitamente: "no introduce zonas por potencia". Queda en `analysis/`. |
| `icu_pm_cp`, `icu_pm_w_prime`, `icu_pm_ftp` | Modelos de potencia-duracion. Requieren historial de potencia. Null en sesiones sin potenciometro. Solo para analisis macro. |
| `icu_rolling_ftp`, `icu_rolling_w_prime` | Idem. Modelos rolling dependientes de historial. |
| `icu_intervals`, `icu_groups` | Estructuras ricas por bloque. Opacas sin normalizacion. Solo para analysis/. |
| `icu_average_watts` | Potencia media. Solo util si hay potenciometro. Si se captura `icu_weighted_avg_watts`, esta es redundante. |
| `RunningIndex`, `GAPOverAvgHR` | Indices propietarios Polar/Garmin. Baja prevalencia y formula no documentada. |
| `icu_power_hr`, `icu_power_hr_z2` | Ratios potencia/FC por zona. Analisis especifico, no canonico. |
| Power curves / ESPE | Endpoint separado. Analisis macro, no por sesion. |
| Coaching readout, session_classification | Output de IA del coach externo. Nuestro analysis/ ya lo cubre. |

### 4. Nota critica: decoupling ≠ cardiac_drift_pct

Estos dos campos miden fenomenos distintos con la misma logica subyacente (deriva de FC) pero sobre variables de referencia diferentes:

| | `cardiac_drift_pct` (nuestro) | `decoupling` (ICU) |
|--|------------------------------|-------------------|
| **Formula** | Aumento de HR por unidad de velocidad | Deriva HR/potencia |
| **Requiere** | Velocidad (outdoor) | Potenciómetro (`device_watts=true`) |
| **Dump** | Calculado siempre que hay velocidad | null en Ride sin potencia; 15.76 en Trail con potencia |
| **Cobertura** | Amplia (todo outdoor) | Solo con sensor de potencia |
| **Relacion** | Complementarios | Complementarios |

Son **complementarios**, no equivalentes. Con potenciometro se pueden comparar; sin potenciometro solo existe el nuestro.

### 5. Nota critica: session_rpe no es trivial

La formula real confirmada con los datos del dump es:

```
session_rpe = moving_time_min × icu_rpe
```

Esto corresponde al **modelo Foster de carga percibida** (Session-RPE × duracion). No es lo mismo que `load` (HRSS fisiologico) ni que `trimp` (TRIMP de Banister). Es una tercera señal de carga desde la percepcion subjetiva del atleta, independiente de FC.

La correlacion entre las tres señales (`load`, `trimp`, `session_rpe`) a lo largo del tiempo puede ser un indicador util de alineacion entre esfuerzo fisiologico y percibido.

### 6. Propuesta de implementacion revisada

#### **FASE 1 — Extraccion directa, solo campos defensibles**

Implementacion en `build_sessions.py` (no en `intervals_sync.py`). Los campos ya llegan en el payload actual; no se necesita cambiar la llamada API.

**Candidatos disponibles para Fase 1, con defensa razonable pero no cerrada:**

```
trimp                 → sessions.csv (siempre; carga Banister)
calories              → sessions.csv (siempre; coste energetico)
average_weather_temp  → sessions.csv (si has_weather; contexto ambiental)
hrr_drop_bpm          → sessions.csv (de icu_hrr.hrr; si presente; condicional)
average_cadence       → sessions.csv (consolidar con FIT existente; si sensor)
```

**Candidatos que requieren decision previa sobre semantica:**

```
icu_intensity         → verificar si aporta sobre intensity_category; escala 0-100
polarization_index    → verificar formula ICU antes de canonizar; escala opaca y no garantizada `>= 0`
session_rpe           → evaluar si complementa trimp; formula moving_time_min × rpe
```

**Si device_watts (condicional, sujetos a utilidad real en backtest):**

```
icu_weighted_avg_watts   → sessions.csv (potencia normalizada)
icu_joules_above_ftp     → sessions.csv (coste anaerobico)
icu_max_wbal_depletion   → sessions.csv (pico de vaciado W')
decoupling               → sessions.csv (complemento a cardiac_drift_pct)
```

**NO en sessions.csv (mover a analysis/ o descartar):**

```
icu_zone_times        → viola contrato v1
icu_variability_index → derivado; evaluar en analysis/
icu_efficiency_factor → derivado; evaluar en analysis/
icu_pm_*, icu_rolling_* → modelos coach; solo analisis macro
icu_atl, icu_ctl      → athlete-day context, no sesion
icu_ftp, icu_resting_hr → athlete-day context
hr_load               → duplicado semantico de load
```

#### **FASE 2 — Semantica verificada (tras validacion)**

Solo tras verificar que `icu_intensity`, `polarization_index` y `session_rpe` no solapan con lo existente:
- Decidir si entran en sessions.csv o quedan como campos consultables en analysis/
- Documentar escala y formula en el contrato si se canoniza

#### **FASE 3 — analysis/ (sin tocar sessions.csv)**

- Potencia estimada sin sensor (modelo grade/speed/weight)
- Durability assessment formal usando `decoupling` + `late_intensity`
- Key blocks analysis con potencia si disponible
- Comparativa `cardiac_drift_pct` vs `decoupling` cuando ambos existen

### 7. Tabla final campo → categoria semantica → destino recomendado

| Campo | Categoria | Destino |
|-------|------|---------|
| `trimp` | session-level | `sessions.csv` (Fase 1) |
| `calories` | session-level | `sessions.csv` (Fase 1) |
| `average_weather_temp` | session-level | `sessions.csv` (Fase 1, si `has_weather`) |
| `icu_hrr` → `hrr_drop_bpm` | session-level | `sessions.csv` (Fase 1, condicional) |
| `average_cadence` | session-level | `sessions.csv` (Fase 1, consolidar FIT) |
| `icu_weighted_avg_watts` | session-level | `sessions.csv` (Fase 1, si `device_watts`) |
| `icu_joules_above_ftp` | session-level | `sessions.csv` (Fase 1, si `device_watts`) |
| `icu_max_wbal_depletion` | session-level | `sessions.csv` (Fase 1, si `device_watts`) |
| `decoupling` | session-level | `sessions.csv` (Fase 1, si `device_watts`) |
| `icu_intensity` | derived-duplicate | Verificar antes de decidir (Fase 2) |
| `polarization_index` | derived-duplicate | Verificar formula antes de decidir (Fase 2) |
| `session_rpe` | derived-duplicate | Evaluar complementariedad con trimp (Fase 2) |
| `icu_variability_index` | derived-duplicate | `analysis/` por defecto; no canonizar en Fase 1 |
| `icu_efficiency_factor` | derived-duplicate | `analysis/` por defecto; no canonizar en Fase 1 |
| `icu_atl`, `icu_ctl` | athlete-day context | No canonizar |
| `icu_ftp`, `icu_resting_hr` | athlete-day context | No canonizar |
| `hr_load` | athlete-day context | No canonizar (duplicado de `load`) |
| `route_id` | athlete-day context | No canonizar (requiere lookup) |
| `icu_zone_times` | analysis-only | `analysis/` (viola contrato v1) |
| `icu_pm_*`, `icu_rolling_*` | analysis-only | `analysis/` (modelos coach) |
| `icu_intervals`, `icu_groups` | analysis-only | `analysis/` |
| `RunningIndex`, `GAPOverAvgHR` | analysis-only | Descartar |
| `icu_power_hr`, `icu_power_hr_z2` | analysis-only | `analysis/` |

### 8. Resumen Ejecutivo (corregido)

| Aspecto | Hallazgo |
|---------|---------|
| **Campos canonizables de forma segura (Fase 1)** | 5-9 campos dependiendo de `device_watts` y `has_weather`. No 15+. |
| **Coste tecnico de Fase 1** | Los datos ya llegan en el payload actual de `build_sessions.py`. Solo codigo de extraccion. Sin llamadas API adicionales. |
| **Archivo a modificar** | `build_sessions.py` (no `intervals_sync.py`). |
| **Riesgo contractual** | Zonas por potencia, efficiency_factor, variability_index violan el contrato v1 de sessions.csv. No entran en Fase 1. |
| **Campos que requieren validacion previa** | `icu_intensity` (escala 0-100), `polarization_index` (formula ICU opaca), `session_rpe` (modelo Foster; evaluar si complementa trimp). |
| **Lo que se descarta o mueve a analysis/** | icu_zone_times, modelos pm/rolling, icu_intervals/groups, athlete-day context, indices propietarios. |

---

## Viabilidad Tecnica de Captura (2026-04-16)

### Dump real de la API

Se ejecuto un dump de `GET /athlete/{id}/activities?oldest=2026-04-14&newest=2026-04-16` contra la API real. El payload completo esta en `research/archive/new/intervals_activities_dump.json`.

**Resultado:** 3 actividades devueltas, **175 campos por actividad**. La API devuelve el payload completo sin necesidad de parametro `fields`.

### Como funciona hoy el codigo

`build_sessions.py → IntervalsClient.get_activities()` hace exactamente esa llamada sin filtro de campos. El payload completo ya llega al pipeline, pero solo se extraen ~15 campos. El resto se descarta silenciosamente.

```python
# build_sessions.py, linea 457
def get_activities(self, oldest: str, newest: str) -> list[dict]:
    return self.get(
        f"/athlete/{self.athlete_id}/activities",
        {"oldest": oldest, "newest": newest},
    ).json()
```

### Clasificacion del dump: donde llegan realmente los datos

Tras el dump se confirma que casi todo llega en el endpoint `/athlete/{id}/activities` sin parámetro `fields`. Solo se clasifican por tipo de dato y condiciones:

#### Categoria A — Llegan en el listado, siempre

Confirmados como presentes en todas/la mayoría de actividades:

| Campo | Valor dump | Tipo | Uso Fase 1 |
|-------|-----------|------|-----------|
| `trimp` | 97.93 | float | ✅ → sessions.csv |
| `calories` | 969 | int | ✅ → sessions.csv |
| `average_cadence` | 88.16 | float | ✅ → sessions.csv (consolidar FIT) |
| `average_weather_temp` | ~18 | float | ✅ → sessions.csv (si `has_weather=true`) |

#### Categoria A-condicional — Llegan en el listado, presentes cuando hay dato

| Campo | Valor dump | Condición | Uso Fase 1 |
|-------|-----------|-----------|-----------|
| `icu_hrr` | `{hrr: 48, start_bpm: 167, end_bpm: 119}` | Presente en TrailRun; null en Ride/Ejercicio | ✅ → sessions.csv (si no null) |
| `icu_weighted_avg_watts` | null | Solo si `device_watts=true` | ✅ → sessions.csv (si `device_watts`) |
| `icu_joules_above_ftp` | null | Solo si `device_watts=true` | ✅ → sessions.csv (si `device_watts`) |
| `icu_max_wbal_depletion` | null | Solo si `device_watts=true` | ✅ → sessions.csv (si `device_watts`) |
| `decoupling` | 15.76 (trail) / null (ride) | Solo si `device_watts=true` | ✅ → sessions.csv (si `device_watts`) |

**CORRECCIÓN CRÍTICA:** `icu_hrr` **llega en el listado** cuando la actividad lo tiene (confirmado en TrailRun, línea 438 del dump). No requiere llamada individual. Pasa de "Categoria B" a "Categoria A-condicional". **Coste: cero llamadas API adicionales.**

#### Categoria A-descarta — Llegan pero NO canonizar en sessions.csv (Fase 1)

Según la revisión de la sección anterior, estos campos son athlete-day context o duplicados semánticos:

| Campo | Razón | Destino |
|-------|-------|---------|
| `icu_ftp` | athlete-day context (estado del atleta ese día, no sesión) | Consultable pero no canonizar |
| `icu_atl` | athlete-day context; duplicado semántico de rolling load en sessions_day | Consultable pero no canonizar |
| `icu_ctl` | athlete-day context; duplicado semántico de rolling load en sessions_day | Consultable pero no canonizar |
| `icu_resting_hr` | athlete-day context; llega de wellness | Consultable pero no canonizar |
| `hr_load` | derived-duplicate (HRSS ≈ load que ya tenemos) | Consultable pero no canonizar |
| `route_id` | athlete-day context; requiere lookup histórico | Consultable pero no canonizar |
| `average_stride` | session-level pero con semantica inestable cross-sport; evaluar Fase 2 | Fase 2 |
| `session_rpe` | derived-duplicate; requiere validar si complementa trimp | Fase 2 |
| `icu_intensity` | derived-duplicate; escala 0-100 (no [0,1]); requiere validar aporte | Fase 2 |
| `polarization_index` | derived-duplicate; formula ICU opaca; backtest real con valores `0`, `>1` y negativos | Fase 2 |

#### Categorias B/C — Analisis solamente

- `icu_zone_times` (7 zonas potencia) → analysis/ (viola contrato v1)
- `icu_pm_*`, `icu_rolling_*` → analysis/ (modelos coach macro)
- `icu_variability_index`, `icu_efficiency_factor` → analysis/ por defecto
- `icu_intervals`, `icu_groups` → analysis/ (estructura opaca)
- Streams, power curves → análisis macro

### Hallazgo clave (corregido)

El 90% de los campos del gap analysis ya llegan. **No hace falta cambiar la llamada API.** 

**Coste real de Fase 1 (solo candidatos sólidos):**
- ~8 campos sin condiciones (`trimp`, `calories`, `cadence`, `weather_temp`)
- +4 campos condicionales (`icu_hrr`, potencia si `device_watts`, `decoupling`)
- **Total: 0 llamadas API adicionales. Puro código de extracción.**

### Campos recomendados para Fase 1 (alineados con la clasificacion semantica)

**Defensa sólida, sin violación contractual:**

```
trimp                  → sessions.csv (Banister load)
calories               → sessions.csv (metabolic cost)
average_cadence        → sessions.csv (consolidar FIT)
average_weather_temp   → sessions.csv (si has_weather; contexto ambiental)
icu_hrr → hrr_drop_bpm → sessions.csv (si presente; parasympathetic recovery)
```

**Si device_watts (condicional):**

```
icu_weighted_avg_watts → sessions.csv
icu_joules_above_ftp   → sessions.csv
icu_max_wbal_depletion → sessions.csv
decoupling             → sessions.csv (complemento a cardiac_drift_pct)
```

**Diferidos a Fase 2 (requieren validación previa):**

```
icu_intensity          (escala 0-100; ¿aporta sobre intensity_category?)
polarization_index     (formula opaca; ¿reproducible?)
session_rpe            (modelo Foster; ¿complementa trimp?)
average_stride         (solo analysis; si se reabre, con semantica deporte-especifica)
```

**NO en sessions.csv:**

```
icu_ftp, icu_atl, icu_ctl, icu_resting_hr, hr_load, route_id
(athlete-day context; no sesión)

icu_zone_times, icu_pm_*, icu_rolling_*
(viola contrato v1; modelos coach)
```

---

## Relacion con otras tareas

- `AP-03` sigue siendo la revision de `AP-01` con capa `run-aware`.
- `FP-02` ya cubre la capa analitica de terreno.
- `RE-02` cubre contexto de recuperacion subjetiva.
- `CDC-01` y `DO-01` ya canonizan contexto de carga y distribucion.

Esta tarea debe quedarse como inventario y analisis de `intervalsicugptcoach`, no como refactor operativo.

---

## Informe final de sintesis y decision (2026-04-16)

### 1. Tesis final

El valor principal de `intervalsicugptcoach` no esta en anadir muchas columnas nuevas al contrato canonico, sino en mejorar la capacidad del sistema para explicar cuatro cosas que hoy aun estan solo parcialmente resueltas:

- **coste real** de la sesion,
- **tolerancia** del atleta a esa carga,
- **durabilidad** dentro de la sesion,
- y **contexto** en el que ocurrio.

La mejora correcta no es "capturar 15-20 campos porque ya llegan", sino:

1. extraer primero un pequeno conjunto de primitivas con buena semantica,
2. medir si aportan valor incremental por deporte,
3. y solo despues construir unas pocas senales compuestas defendibles.

### 2. Lo mas valioso que realmente anaden estos datos

De todo el payload revisado, lo que mas potencial tiene para mejorar el analisis no es uniforme; cambia por deporte y por tipo de lectura.

#### 2.1 Carga convergente/divergente

La combinacion de:

- `load` (HRSS/Training Load),
- `trimp`,
- `session_rpe`,

permite construir una lectura mucho mas rica de la carga.

Interpretacion:

- si las tres senales convergen, la lectura de coste es limpia;
- si divergen, aparece informacion adicional:
  - `session_rpe` alto con `trimp` o `load` normales sugiere coste muscular, tecnico, termico o mental;
  - `trimp` alto con `session_rpe` bajo sugiere buena tolerancia;
  - `load` alto con `session_rpe` alto y `decoupling` alto sugiere sesion cara en terminos de absorcion.

#### 2.2 Durabilidad de sesion

La sesion puede entenderse mucho mejor si se combinan:

- `cardiac_drift_pct`,
- `late_intensity`,
- `decoupling` cuando exista potencia,
- `icu_weighted_avg_watts`,
- cadencia y, en carrera, `average_stride`.

Eso permite distinguir mejor entre:

- sesion estable,
- sesion progresiva,
- sesion degradada,
- y sesion cerrada con fatiga.

#### 2.3 Coste anaerobico y estocasticidad

En sesiones con potencia, el bloque:

- `icu_weighted_avg_watts`,
- `icu_joules_above_ftp`,
- `icu_max_wbal_depletion`,

puede separar sesiones que parecen similares por HR pero no lo son por coste mecanico o neuromuscular.

#### 2.4 Contexto ambiental

`average_weather_temp` y, si algun dia interesa, el resto del weather block, no son solo decorativos. Pueden ayudar a explicar:

- FC mas alta de lo esperable,
- peor eficiencia,
- peor tolerancia percibida,
- y deriva mayor de la habitual.

#### 2.5 Contexto de ruta y terreno

`route_id`, `gap`, `terrain_intervals`, `icu_groups` y los climbs desde FIT pueden enriquecer mucho la comparacion del atleta contra si mismo, pero esa capa encaja mejor en `analysis/` que en `sessions.csv`.

### 3. Lo que NO esta demostrado aun

Hay que dejar explicitamente fuera de la conclusion fuerte varias ideas que son plausibles pero aun no estan suficientemente validadas:

- `polarization_index` como campo canonico de sesion
- `icu_intensity` como mejora clara sobre `intensity_category`
- `average_stride` como candidato robusto fuera de run/trail
- `route_id` como contexto operativo inmediato
- indices nuevos como `mismatch index`, `thermal cost score` o `technicality proxy`

Estas ideas son utiles como investigacion, pero todavia no como diseno operativo cerrado.

### 4. Mejora real para los analisis de sesion

#### 4.1 Trail run

El mayor salto no viene de una sola metrica, sino de combinar:

- `GAP`,
- `run_power` / `icu_weighted_avg_watts`,
- `decoupling`,
- `cardiac_drift_pct`,
- cadencia,
- stride.

Con eso se puede diferenciar mejor:

- duro por terreno,
- duro por motor,
- duro por tecnica,
- y duro por fatiga acumulada.

#### 4.2 Cycling

En bici, la mejora mas clara viene de combinar:

- `trimp`,
- `session_rpe`,
- `icu_weighted_avg_watts`,
- `icu_joules_above_ftp`,
- `icu_max_wbal_depletion`,
- `hrr_drop_bpm`,
- `average_cadence`.

Eso ayuda a separar:

- carga interna,
- coste mecanico,
- coste anaerobico,
- y cierre de sesion.

#### 4.3 Narrativa y clasificacion de bloques

`icu_intervals` e `icu_groups` no deben canonizarse, pero si pueden alimentar mejor el relato analitico si se resumen bien.

Aplicaciones potenciales:

- `steady aerobic`
- `tempo continuo`
- `hill repeats`
- `trail estocastico`
- `final duro con fatiga`

### 5. Mejora real para el contexto general del atleta

Estos datos pueden ayudar mucho a pasar de una lectura de "cuanta carga hubo" a una lectura de "como la esta absorbiendo el atleta".

Las mejoras potenciales mas utiles son:

- **alineacion subjetivo-fisiologica**: relacion entre `load`, `trimp` y `session_rpe`
- **tolerancia al calor**: efecto sistematico de `average_weather_temp` sobre FC, deriva y percepcion
- **durabilidad como tendencia**: no una sesion aislada, sino si el atleta empeora en estabilidad durante varias semanas
- **economia mecanica especifica por deporte**: separar `road_run`, `trail_run` y `ride`

### 6. Recomendacion final de implementacion

#### Paso 1 — validar primitivas con mejor ROI

Prioridad alta:

- `trimp`
- `hrr_drop_bpm`
- `icu_weighted_avg_watts`
- `decoupling`
- `session_rpe`

Prioridad media:

- `average_weather_temp`
- `average_cadence`
- `icu_joules_above_ftp`
- `icu_max_wbal_depletion`
- `average_stride` solo como lectura deporte-especifica en `analysis/`

#### Paso 2 — medir utilidad incremental por deporte

Comparar cada primitiva contra:

- lo ya disponible en `sessions.csv`
- lo ya resumido en `sessions_day.csv`
- y lo ya inferido en `analysis/`

Siempre separando:

- `road_run`
- `trail_run`
- `ride`

#### Paso 3 — construir solo 3 familias de senales compuestas

Solo si las primitivas demuestran valor:

1. **carga convergente/divergente**
2. **durabilidad de sesion**
3. **contexto mecanico/ambiental**

### 6.b Roadmap formal por fases

| Fase | Objetivo | Entregables clave | Riesgo principal | Criterio de cierre |
| --- | --- | --- | --- | --- |
| `Fase 1` | Extraer solo primitivas de sesion con semantica clara y bajo riesgo contractual. | Campos canonicos cerrados, nombres/unidades/nullabilidad, implementacion en `build_sessions.py`, actualizacion de `docs/contracts/` si procede. | Sobrecanonizar por disponibilidad y romper el contrato v1 de `sessions.csv`. | Campos persistidos con reglas de presencia claras y auditables, sin erosionar el contrato actual. |
| `Fase 2` | Validar si los campos ambiguos aportan valor real o solo duplican semantica existente. | Backtest por deporte, formula/escala/cobertura cerradas, decision de destino por campo. | Confundir disponibilidad con utilidad y canonizar duplicados semanticos. | Cada campo ambiguo queda clasificado como `canonizable`, `solo analysis` o `descartado`. |
| `Fase 3` | Explotar estructuras ricas y modelos coach solo en `analysis/`. | Uso util de `icu_intervals`, `icu_groups`, `icu_achievements`, bloques, ruta, terreno y comparativas tacticas. | Contaminar `sessions.csv` con estructuras opacas o demasiado ricas para contrato base. | Existe valor explicativo claro en `analysis/` sin introducir nuevas columnas canonicas por simple disponibilidad. |
| `Fase 4` | Construir pocas senales compuestas despues de validar las primitivas. | Formula matematica explicita, prueba retrospectiva por deporte, decision de capa destino. | Crear indices vistosos pero no robustos o sin mejora real frente a primitivas. | Cada senal compuesta demuestra valor incremental y queda definida de forma auditable. |
| `Fase 5` | Consolidar senales validadas como contexto longitudinal del atleta, especializado por deporte. | Reglas por `road_run`, `trail_run` y `ride`, tendencias longitudinales, benchmarks por ruta si la cobertura lo permite, integracion selectiva en la salida analitica. | Mezclar capas y convertir una exploracion analitica en un sistema sobredimensionado o poco estable. | Las senales mejoran de forma estable el contexto del atleta sin invadir el gate HRV ni romper la separacion de capas. |

#### Fase 1 — Extraccion minima canonica

Objetivo:

- incorporar solo primitivas de sesion con semantica clara, cobertura razonable y bajo riesgo contractual.

Entregables esperados:

- decision cerrada de campos que entran en `sessions.csv`
- nombres canonicos, unidades y nullabilidad documentadas
- implementacion en `build_sessions.py`
- actualizacion de `docs/contracts/` si cambia el esquema

Campos candidatos de esta fase:

- `trimp`
- `hrr_drop_bpm`
- `average_weather_temp`
- `icu_weighted_avg_watts` si `device_watts`
- `decoupling` si `device_watts`

Criterio de cierre:

- los campos quedan persistidos sin romper el contrato v1
- se conocen sus reglas de presencia y ausencia
- hay trazabilidad suficiente para auditarlos

#### Fase 2 — Validacion semantica y backtest de campos ambiguos

Objetivo:

- decidir si ciertos campos prometedores aportan valor real o solo duplican semantica existente.

Entregables esperados:

- comparativa retrospectiva por deporte
- definicion exacta de escala, formula y cobertura
- decision de destino: `sessions.csv`, `analysis/` o descarte

Campos principales de esta fase:

- `session_rpe`
- `icu_intensity`
- `polarization_index`
- `average_cadence`
- `average_stride`

Criterio de cierre:

- cada campo ambiguo queda clasificado como:
  1. canonizable
  2. solo analysis
  3. descartado

#### Resultados de backtest SYA-05 (historico real 2025-05-12 .. 2026-04-15; n=362)

Fuente:

- `research/archive/new/intervals_activities_backtest.json`
- cruce completo contra `data/ENDURANCE_HRV_sessions.csv` por `session_id`

Hallazgos cerrados por campo:

| Campo | Cobertura real | Hallazgo principal | Decision |
|-------|----------------|-------------------|----------|
| `session_rpe` | `271/362` (`74.9%`) | La formula queda validada como `moving_time_min x icu_rpe` con error medio `0.25` y maximo `<1`. No es duplicado directo de carga fisiologica: correlacion baja-moderada con `load` (`0.426`) y `trimp` (`0.442`). Sin embargo, mezcla `null` con muchos `0` reales/operativos y su interpretacion depende de adherencia subjetiva. | `analysis/` por ahora. No canonizar aun en `sessions.csv`. |
| `icu_intensity` | `358/362` (`98.9%`) | Escala `0-100` confirmada. Tiene relacion moderada con nuestra estructura (`corr` con `work_total_min` `0.614`, con `z3_pct` `0.424`), pero no sustituye `intensity_category`: incluso `easy` tiene mediana ~`55.9` y hay solapamiento fuerte entre categorias. | `analysis/` |
| `polarization_index` | `357/362` (`98.6%`) | La formula ICU sigue opaca. El historico real invalida la hipotesis `>=0`: aparecen valores negativos hasta `-1.17`. Ademas, `264/357` observaciones son exactamente `0` y la correlacion con `z3_pct` es alta (`0.814`), lo que sugiere redundancia parcial con nuestra lectura de intensidad. | `analysis/` |
| `average_cadence` | `208/362` (`57.5%`) | El valor raw coincide exactamente con lo ya persistido en `sessions.csv` (`208/208` matches exactos). La captura queda validada. La semantica es util, pero depende del deporte (`run/trail/bike/swim`). | Mantener en `sessions.csv` |
| `average_stride` | `208/362` (`57.5%`) | No llega solo en carrera/trail: aparece tambien en `Ride` y `Swim`, lo que rompe la hipotesis de semantica estable transversal. En run/trail puede tener valor, pero cross-sport introduce ruido fuerte. | `analysis/` y solo con lectura deporte-especifica |

Conclusiones operativas de Fase 2:

- `average_cadence` queda ratificado como columna canonica valida en `sessions.csv`
- `session_rpe` queda validado como señal subjetiva real y no trivial, pero todavia no con calidad contractual suficiente para canonizarlo
- `icu_intensity` y `polarization_index` no mejoran de forma clara el contrato base frente a lo ya disponible
- `average_stride` no debe plantearse como columna canonica transversal; si se usa, debe vivir en `analysis/` y con semantica por deporte
- el hallazgo adicional fuera del alcance estricto de la fase es que `trimp` y `load` muestran correlacion casi perfecta en este dataset (`0.996`), lo que rebaja la urgencia de introducir una tercera senal canonica de carga sin una justificacion muy clara

#### Fase 3 — Enriquecimiento analitico no canonico

Objetivo:

- explotar el valor alto de estructuras ricas y modelos coach sin contaminar `sessions.csv`.

Entregables esperados:

- consumo util de `icu_intervals`, `icu_groups`, `icu_achievements`
- analisis de bloques, ruta y terreno
- comparativas de `cardiac_drift_pct` vs `decoupling`
- exploracion de potencia estimada sin sensor y lecturas tacticas

Campos o familias centrales:

- `icu_intervals`
- `icu_groups`
- `icu_achievements`
- `icu_zone_times`
- `icu_pm_*`
- `icu_rolling_*`
- `route_id`

Criterio de cierre:

- existe valor narrativo o explicativo claro en `analysis/`
- no se introducen columnas canonicas nuevas por simple disponibilidad

Implementacion inicial `2026-04-16`:

- `analysis/session_analysis_pipeline.py` ya inyecta `analysis_only_context` en `summary.json` y `session_payload.json`
- el detalle reproducible se escribe en `analysis/reports/<slug>/artifacts/coach_metrics.json`, `coach_intervals.csv` y `coach_groups.csv` cuando existe
- esta capa queda limitada a `analysis/` y no modifica `sessions.csv`, `sessions_day.csv`, `FINAL` ni `DASHBOARD`

#### Fase 4 — Senales compuestas validadas

Objetivo:

- construir pocas senales compuestas, pero solo despues de que las primitivas hayan demostrado valor incremental.

Entregables esperados:

- definicion matematica de cada senal
- prueba retrospectiva por deporte
- decision de capa destino: `sessions_day.csv` o `analysis/`

Senales candidatas:

- `load mismatch`
- `durability score`
- `subjective coherence`
- `thermal cost score`

Definiciones operativas iniciales validadas en `SYA-07`:

- `subjective coherence` / `load mismatch`: usar `objective_anchor = median(load, trimp_load_equiv, hr_load)` y `subjective_anchor = session_rpe / 10` como comparacion lineal; `trimp_load_equiv` se normaliza con un ratio historico del propio atleta para hacer legible la comparacion; exponer `subjective_objective_gap_pct`, `objective_spread_pct` y `subjective_coherence_state`; la escala de `session_rpe` se usa aqui solo como carga-equivalente exploratoria, no como conversion fisiologica exacta.
- `thermal cost score`: version simple y auditable apoyada en `average_weather_temp`; formula base `max(0, average_weather_temp - 18C) * moving_min_h`; si no hay humedad o dew point, no inventar un WBGT ni una lectura termica cerrada.
- `durability score` como entrada exploratoria: partir `session_stream.csv` en tres tercios iguales por segundos transcurridos, exponer medias de `hr`, `speed_kmh` y `cadence` por tercio, y anotar el delta del primero al ultimo; esto queda como primitiva de sostenimiento, no como taxonomia fuerte por deporte.
- destino provisional de estas señales: `analysis/` y, si alguna demuestra utilidad longitudinal real, `sessions_day.csv`; no canonizar en `sessions.csv` por simple disponibilidad tecnica.

Criterio de cierre:

- cada senal compuesta demuestra utilidad por encima de usar solo primitivas
- la formula queda explicita y auditable

#### Fase 5 — Consolidacion longitudinal y especializacion por deporte

Objetivo:

- convertir las senales ya validadas en una capa madura de contexto del atleta, diferenciada por deporte y por horizonte temporal.

Entregables esperados:

- reglas especificas para `road_run`, `trail_run` y `ride`
- tendencias longitudinales en `sessions_day.csv` cuando proceda
- benchmarks por ruta o subida si la cobertura lo permite
- integracion selectiva en la salida analitica del atleta

Aplicaciones tipicas:

- sensibilidad termica individual
- durabilidad como tendencia de varias semanas
- divergencia cronica entre carga fisiologica y carga percibida
- benchmark por ruta, climb o tipo de sesion repetida

Criterio de cierre:

- las senales ya no son solo experimento analitico
- mejoran de forma estable la lectura del contexto general del atleta
- siguen sin invadir el gate HRV ni mezclar capas operativas

### 7. Destino recomendado por capa

#### `sessions.csv`

Solo primitivas de sesion con semantica clara y coste contractual razonable.

Candidatos mas defendibles:

- `trimp`
- `hrr_drop_bpm`
- `icu_weighted_avg_watts` si `device_watts`
- `decoupling` si `device_watts`

Candidatos secundarios:

- `average_weather_temp`
- `average_cadence`
- `icu_joules_above_ftp`
- `icu_max_wbal_depletion`

#### `sessions_day.csv`

Aqui deberian vivir, si se justifican, las senales rolling:

- divergencia entre `load`, `trimp` y `session_rpe`
- tendencia de durabilidad
- tendencia de eficiencia o coste anaerobico
- sensibilidad termica observada

#### `analysis/`

Debe seguir siendo la casa natural de:

- `icu_intervals`, `icu_groups`
- power models `icu_pm_*`, `icu_rolling_*`
- `polarization_index` mientras no se valide bien
- `icu_intensity` mientras no se demuestre su aporte
- comparativas de rutas, climbs y bloques
- potencia estimada sin sensor
- clasificaciones tacticas de sesion

### 8. Ideas nuevas que merecen investigacion, no canonizacion inmediata

- **load mismatch**: divergencia entre `load`, `trimp` y `session_rpe`
- **durability score**: combinacion de `decoupling`, `cardiac_drift_pct` y cierre de sesion
- **thermal cost score**: impacto del calor sobre FC y percepcion respecto al propio baseline
- **route benchmark**: comparacion contra el propio historico en rutas o subidas repetidas
- **subjective coherence**: cuanto "siente" el atleta frente a lo que dicen HR y potencia

Estas ideas son prometedoras, pero no deben entrar todavia ni en el contrato ni en la Fase 1.

#### 8.1 Priorizacion refinada tras revision externa (2026-04-17)

La revision fisiologica externa aporta valor, pero mezcla tres capas distintas:

- senales compuestas de sesion candidatas a `SYA-07`
- consolidacion longitudinal y por deporte propia de `SYA-08`
- contexto semanal o de baseline HRV que no debe colarse en `analysis_only_context` como si fuera una extension natural de `SYA-06`

Decision operativa:

- **prioridad alta para `SYA-07`**:
  - `subjective coherence` / `load mismatch` usando `load`, `trimp`, `session_rpe` y `hr_load`
  - `thermal cost score` en una version simple y auditable, apoyada primero en `average_weather_temp` y solo despues en humedad o dew point si algun dia pasan a cobertura reproducible
  - primitivas de **durabilidad por tercios** como apoyo a `durability score`, pero sin cerrar todavia una taxonomia fuerte (`durable`, `central_drift`, `peripheral_fade`) sin backtest real por deporte y aplicabilidad

- **prioridad para `SYA-08`**:
    - `route benchmark` y `climb economy trend`, solo si hay rutas/subidas repetidas y cobertura suficiente
    - divergencia cronica entre carga objetiva y subjetiva como tendencia longitudinal, no como lectura de una sola sesion
    - continuidad aeróbica sostenida si algun dia se redefine bien en el marco de 3 zonas del proyecto

Estado final `2026-04-29`:

- implementado en `analysis/` mediante `longitudinal_context`
- consolidado como salida local reproducible de reporte
- no promocionado a columna canonica por falta de cobertura homogénea por deporte
- `route benchmark` restringido por evidencia real: util en bici de forma puntual, no generalizable hoy a `trail_run` ni `road_run`

- **no tratar como ampliacion directa de `SYA-06`**:
  - `HRV rebound profile D+1/D+3`, porque es retrospectivo por naturaleza y encaja mejor en weekly o en enriquecimiento diferido
  - `z3 budget` semanal, porque depende de tolerancia historica y pertenece a capa agregada semanal
  - `baseline drift 60v180`, porque toca la logica HRV global y el baseline adaptativo; si se aborda, debe abrirse como tarea HRV separada y no como señal coach de sesion

- **baja prioridad / riesgo de redundancia**:
  - `TSB` o `form score` clasico, porque `SYA-03` ya considera `icu_atl/ctl/tsb` contexto athlete-day redundante con la capa canonica de carga en `sessions_day`

Regla de incorporacion:

1. si la idea ya cabe en `load mismatch`, `subjective coherence`, `durability score` o `thermal cost score`, debe entrar por `SYA-07`
2. si depende de horizonte longitudinal, benchmark o especializacion por deporte, debe entrar por `SYA-08`
3. si depende de retrospectiva semanal o de reabrir la semantica del baseline HRV, no debe camuflarse como enriquecimiento local de `analysis/`

#### 8.2 Backlog diferido SYA-10: cierre y trazabilidad (2026-05-05)

`SYA-10` no autoriza implementacion. Su funcion es contener y desambiguar ideas que:

- no encajan hoy como senal compuesta de sesion
- no deben entrar por la puerta de atras en `analysis_only_context`
- o reabren semantica weekly o HRV global antes de estar bien definidas

Regla operativa:

- toda idea del backlog diferido debe acabar en una tarjeta propia o quedar descartada de forma explicita
- `SYA-10` no ejecuta esas ideas; solo fija su destino natural y su criterio de reactivacion

Tabla activa de trazabilidad:

| idea | destino natural | por que no entra hoy | criterio de reactivacion | tarea destino |
|---|---|---|---|---|
| `HRV rebound profile D+1/D+3` | `weekly retrospectivo` | usa informacion posterior a la sesion y no debe confundirse con una lectura inmediata de coste | pasa a `red` solo si existe definicion operacional del rebote, regla de atribucion a sesion o bloque, politica para dias contaminados y destino final escrito | [SYA-16](SYA-16%20HRV%20rebound%20profile%20D%2B1%20D%2B3.md) |
| `baseline drift 60v180` | `HRV global / baseline` | toca baseline, flags y potencialmente gate; no pertenece a capa coach de sesion | pasa a `red` solo si existe definicion operacional `60v180`, decision documentada sobre impacto en `baseline/flags/gate` y relacion cerrada con el baseline adaptativo de largo plazo | [HG-01](HG-01%20Propuesta%20baseline%20drift%2060v180.md) |
| `continuidad aerobica Z1 alta` | `longitudinal per-sport no operativo` | la semantica de `Z1 alta` y de continuidad sigue siendo ambigua por deporte y horizonte | pasa a `red` solo si existe definicion operacional de `Z1 alta`, definicion de continuidad, decision de aplicabilidad por deporte y comparacion documentada con valor incremental frente a `SYA-08`, `DO-01` y `DO-02` | [SYA-15](SYA-15%20Continuidad%20aer%C3%B3bica%20Z1%20alta.md) |
| `z3 budget semanal` | `weekly retrospectivo` | depende de tolerancia historica y puede solaparse con carga, clustering e intensidad semanal ya disponibles | pasa a `red` solo si existe definicion operacional de `Z3` y del `budget`, comparacion documentada con la capa actual y conclusion explicita de valor incremental no redundante | [SYA-14](SYA-14%20Z3%20budget%20semanal.md) |
| `TSB / form score clasico` | `descartado por redundancia` | ya existe contexto suficiente en `icu_atl/ctl/tsb` y en la capa canonica de carga de `sessions_day` | solo reconsiderar si aparece evidencia clara de valor incremental no redundante | sin tarea nueva |

Estado de cierre de `SYA-10`:

- el backlog ya no queda como lista difusa dentro de `SYA-03`
- cada idea principal tiene destino natural y tarjeta hija propia, salvo `TSB / form score` que queda descartado
- cualquier reactivacion futura debe salir de su tarjeta hija, no de `SYA-10`

### 9. Decision final

La conclusion mas robusta tras integrar el analisis exploratorio y la revision critica es esta:

- **si** hay valor real adicional en los datos de `intervalsicugptcoach`
- **no** conviene traducir ese valor en una expansion amplia e inmediata de `sessions.csv`
- el siguiente salto de calidad vendra de **pocas primitivas bien elegidas** y de **senales compuestas validadas despues**, no de una lista larga de campos nuevos

En resumen:

1. capturar poco y bien,
2. validar por deporte,
3. y componer despues.

### 10. Tabla priorizada campo/senal → destino → ROI → riesgo contractual

| Campo o senal | Destino recomendado | ROI esperado | Riesgo contractual | Nota operativa |
|---------------|---------------------|--------------|--------------------|----------------|
| `trimp` | `sessions.csv` | Alto | Bajo | Primitiva de carga clara, interpretable y ortogonal a `load` y `session_rpe`. |
| `hrr_drop_bpm` | `sessions.csv` | Alto | Bajo | Buena senal intra-sesion si viene poblada; condicionarla a presencia real del dato. |
| `icu_weighted_avg_watts` | `sessions.csv` si `device_watts` | Alto | Medio | Potencia normalizada muy util en run/trail/bike con potencia; requiere cobertura suficiente. |
| `decoupling` | `sessions.csv` si `device_watts` | Alto | Medio | Complementa `cardiac_drift_pct`; no sustituirlo ni mezclar semanticas. |
| `session_rpe` | `analysis/` tras validacion | Alto | Medio | Senal Foster validada y no trivial, pero la cobertura subjetiva es parcial y mezcla `null` con muchos `0`; mejor mantenerla fuera del contrato canonico por ahora. |
| `average_weather_temp` | `sessions.csv` | Medio | Bajo | Buen contexto explicativo; no justifica por si solo una capa compleja. |
| `average_cadence` | `sessions.csv` | Medio | Bajo | Util si se consolida bien con FIT y se interpreta por deporte. |
| `icu_joules_above_ftp` | `sessions.csv` si `device_watts` | Medio | Medio | Puede mejorar la lectura de coste anaerobico, sobre todo en bike y trail duro. |
| `icu_max_wbal_depletion` | `sessions.csv` si `device_watts` | Medio | Medio | Potente para leer picos de coste, pero mas sensible a cobertura y calidad de potencia. |
| `average_stride` | `analysis/` | Medio | Medio | Puede aportar en carrera, pero el backtest real muestra presencia tambien en `Ride` y `Swim`; no tiene semantica transversal suficientemente estable para `sessions.csv`. |
| `icu_intensity` | `analysis/` en Fase 2 | Medio | Medio | Escala 0-100 clara, pero no esta demostrado aun que mejore `intensity_category`. |
| `polarization_index` | `analysis/` en Fase 2 | Medio | Alto | Prometedor, pero la formula ICU sigue siendo opaca; no canonizar antes de verificarla. |
| `icu_variability_index` | `analysis/` | Medio | Alto | Derivado de potencia; mejor calcular o validar antes de persistirlo. |
| `icu_efficiency_factor` | `analysis/` | Medio | Alto | Igual que `variability_index`; util, pero mejor fuera de `sessions.csv` en v1. |
| `load mismatch` | `sessions_day.csv` tras backtest | Alto | Medio | Buena senal compuesta para divergencia entre carga fisiologica y percibida. |
| `durability score` | `sessions_day.csv` o `analysis/` tras backtest | Alto | Medio | Tiene potencial real, pero solo despues de validar bien las primitivas. |
| `thermal cost score` | `analysis/` | Medio | Bajo | Buena idea de investigacion, todavia no como parte del contrato operativo. |
| `route benchmark` | `analysis/` | Medio | Bajo | Puede ser muy util si hay rutas repetidas, pero depende de historico y lookup. |
| `subjective coherence` | `sessions_day.csv` o `analysis/` tras backtest | Medio | Medio | Interesante para alinear `load`, `trimp`, `session_rpe` y percepcion. |
| `icu_zone_times` | `analysis/` | Bajo | Alto | Violan el contrato v1 de `sessions.csv`; no son prioridad para canonizacion. |
| `icu_pm_*`, `icu_rolling_*` | `analysis/` | Bajo | Alto | Modelos coach y rolling de potencia; demasiado opacos para Fase 1. |
| `icu_intervals`, `icu_groups` | `analysis/` exclusivamente | Alto | Alto | ROI alto solo para narrativa, deteccion de bloques y lectura tactica en `analysis/`; no como columnas canonicas ni como candidato a `sessions.csv`. |
| `icu_atl`, `icu_ctl`, `icu_ftp`, `icu_resting_hr` | No canonizar | Bajo | Medio | Son contexto del atleta/dia, no resultado de la sesion. |
| `hr_load` | No canonizar por ahora | Bajo | Bajo | En este dump coincide con `load`; no merece duplicacion inmediata. |
| `route_id` | `analysis/` o lookup futuro | Bajo | Bajo | Interesante solo si se construye una capa de comparacion por ruta. |

---

## 11. Plantilla obligatoria de trazabilidad para subtareas SYA-03A a SYA-03E

Estas subtareas no deben arrancarse como analisis independientes. Cada una debe tratarse como ejecucion parcial del documento maestro `SYA-03`.

Para backlog diferido y reactivaciones posteriores como `SYA-10`, la referencia ya no es esta plantilla cerrada de fases `A` a `E`, sino la tabla de `8.2 Backlog diferido SYA-10: cierre y trazabilidad`, que fija:

- destino natural de cada idea
- criterio binario de promocion a `red`
- y enlace obligatorio a su tarjeta hija propia o a su descarte explicito

Bloque obligatorio para cualquier subtarea derivada:

- `Documento maestro`: `docs/HRV/SYA-03 Inventario y analisis ampliado de intervalsicugptcoach.md`
- `Subtarea Fase 5 cerrada`: `docs/HRV/SYA-08 Fase 5 Consolidacion longitudinal y especializacion por deporte.md`
- `Secciones aplicables`: resumen ejecutivo, `6.b Roadmap formal por fases`, tabla priorizada y anexo exhaustivo
- `Marco obligatorio`: no reabrir decisiones ya cerradas en `SYA-03` sin actualizar antes el documento maestro
- `Decisiones que SI puede tomar`: solo las que correspondan a su fase
- `Decisiones que NO puede tomar`: cualquier cambio fuera de su fase o cualquier reinterpretacion global no documentada en `SYA-03`
- `Cierre obligatorio`: actualizar `SYA-03` si cambia cualquier conclusion, formula, naming, unidad, nullabilidad, cobertura o destino de capa

Aplicacion por subtarea:

- `SYA-03A / Fase 1`
  - puede cerrar primitivas canonicas de `sessions.csv`
  - no puede introducir senales compuestas ni redisenar el roadmap
- `SYA-03B / Fase 2`
  - puede validar o descartar campos ambiguos
  - no puede canonizar sin evidencia retrospectiva suficiente
- `SYA-03C / Fase 3`
  - puede definir usos `analysis-only`
  - no puede convertir estructuras ricas o modelos coach en contrato canonico
- `SYA-03D / Fase 4`
  - puede formalizar senales compuestas ya previstas
  - no puede crear indices nuevos fuera del marco maestro sin actualizar `SYA-03`
- `SYA-03E / Fase 5`
  - puede consolidar especializacion por deporte y tendencias longitudinales
  - no puede saltarse validaciones previas ni invadir el gate HRV

Nota operativa:

- mientras las tarjetas de Kanvas sigan en estado `purple`, el CLI no permite editarlas;
- por tanto, esta seccion actua como fuente de verdad inmediata para su futura edicion cuando pasen a `red` u `orange`.

## Anexo A. Inventario exhaustivo del dump actual (2026-04-16)

> Este anexo intenta cerrar la pregunta "que campos pueden haberse quedado fuera". No es una recomendacion de canonizacion masiva; es un inventario exhaustivo por familias de todos los campos observados en `research/archive/new/intervals_activities_dump.json`, incluyendo los que hoy parecen de bajo valor o solo contextuales.

### A.1 Identidad, origen e ingestión

Campos:

- `id`
- `name`
- `type`
- `source`
- `device_name`
- `external_id`
- `file_type`
- `file_sport_index`
- `icu_athlete_id`
- `created`
- `icu_sync_date`
- `analyzed`
- `group`
- `route_id`
- `paired_event_id`
- `strava_id`
- `oauth_client_id`
- `oauth_client_name`

Lectura:

- utiles para trazabilidad y matching;
- `route_id` puede tener valor analitico si se construye una capa de benchmark por ruta;
- el resto es sobre todo metadata tecnica.

Destino preliminar:

- `route_id` → `analysis/` o lookup futuro
- resto → no canonizar, salvo trazabilidad puntual

### A.2 Calendario y duracion

Campos:

- `start_date`
- `start_date_local`
- `elapsed_time`
- `moving_time`
- `coasting_time`
- `icu_recording_time`
- `icu_median_time_delta`
- `workout_shift_secs`
- `recording_stops`
- `timezone`

Lectura:

- `elapsed_time`, `moving_time` e `icu_recording_time` son basicos de sesion;
- `icu_median_time_delta` y `recording_stops` son mas utiles como QA o para interpretar calidad del stream que como señal deportiva directa.

Destino preliminar:

- los tiempos base ya se usan o se pueden derivar;
- `icu_median_time_delta` merece al menos quedar como campo revisado y no olvidado; puede ser util para QA de streams;
- resto → no canonizar por ahora

### A.3 Volumen, distancia y altimetria

Campos:

- `distance`
- `icu_distance`
- `average_speed`
- `max_speed`
- `average_altitude`
- `min_altitude`
- `max_altitude`
- `total_elevation_gain`
- `total_elevation_loss`
- `pace`
- `gap`
- `gap_model`
- `use_elevation_correction`
- `threshold_pace`
- `pace_zones`
- `pace_zone_times`
- `gap_zone_times`
- `use_gap_zone_times`

Lectura:

- `gap`, `gap_model` y la correccion por elevacion tienen valor claro en run/trail y ya conectan con `FP-02`;
- `pace` y `threshold_pace` pueden ser utiles si algun dia se estudia semantica de ritmo, pero hoy no cambian mucho la capa canonica;
- `pace_zones` y `gap_zone_times` no aparecen poblados en este dump, pero conviene dejarlos inventariados.

Destino preliminar:

- `gap`, `gap_model`, `use_elevation_correction` → `analysis/`
- resto → ya cubierto por pipeline base o pendiente de justificacion

### A.4 Frecuencia cardiaca, zonas y recuperacion

Campos:

- `has_heartrate`
- `average_heartrate`
- `max_heartrate`
- `athlete_max_hr`
- `lthr`
- `icu_resting_hr`
- `icu_hr_zones`
- `icu_hr_zone_times`
- `icu_hrr`

Lectura:

- aqui hay mezcla entre dato de sesion y configuracion del atleta;
- `icu_hrr` es el hallazgo nuevo mas defendible de esta familia;
- `icu_resting_hr`, `athlete_max_hr`, `lthr` y `icu_hr_zones` son mas bien contexto del atleta.

Destino preliminar:

- `icu_hrr` → candidato a `sessions.csv`
- `icu_hr_zone_times` y FC base ya estan cubiertos conceptualmente
- configuracion del atleta → no canonizar en `sessions.csv`

### A.5 Carga, intensidad y percepcion

Campos:

- `icu_training_load`
- `icu_training_load_data`
- `hr_load`
- `hr_load_type`
- `power_load`
- `pace_load`
- `pace_load_type`
- `trimp`
- `icu_intensity`
- `icu_rpe`
- `session_rpe`
- `feel`
- `perceived_exertion`
- `polarization_index`
- `tiz_order`
- `strain_score`
- `decoupling`

Lectura:

- esta es una de las familias mas importantes del payload;
- `trimp`, `session_rpe`, `icu_intensity` y `decoupling` siguen siendo los campos con mas potencial nuevo;
- `icu_training_load_data`, `hr_load_type` y `tiz_order` son mas metadata de como ICU construye su lectura;
- `power_load` y `pace_load` pueden ser interesantes, pero aun no estan suficientemente analizados.

Destino preliminar:

- `trimp` → candidato fuerte a `sessions.csv`
- `session_rpe`, `icu_intensity`, `decoupling` → validar antes
- `power_load`, `pace_load`, `strain_score` → `analysis/` o pendiente
- `icu_training_load_data`, `hr_load_type`, `tiz_order` → documentar y dejar fuera por ahora

### A.6 Potencia, W' y modelos coach

Campos:

- `device_watts`
- `icu_average_watts`
- `icu_weighted_avg_watts`
- `icu_variability_index`
- `icu_efficiency_factor`
- `icu_joules`
- `icu_joules_above_ftp`
- `icu_max_wbal_depletion`
- `icu_w_prime`
- `icu_pm_cp`
- `icu_pm_w_prime`
- `icu_pm_p_max`
- `icu_pm_ftp`
- `icu_pm_ftp_secs`
- `icu_pm_ftp_watts`
- `icu_rolling_cp`
- `icu_rolling_ftp`
- `icu_rolling_ftp_delta`
- `icu_rolling_p_max`
- `icu_rolling_w_prime`
- `p_max`
- `MaxPwr`
- `ss_cp`
- `ss_p_max`
- `ss_w_prime`
- `FractionalUtilizationusing6mPower`
- `icu_zone_times`
- `icu_power_zones`
- `icu_power_hr`
- `icu_power_hr_z2`
- `icu_power_hr_z2_mins`
- `icu_cadence_z2`
- `icu_power_spike_threshold`
- `power_field`
- `power_field_names`
- `power_meter`
- `power_meter_serial`
- `power_meter_battery`
- `avg_lr_balance`
- `crank_length`

Lectura:

- esta familia es la mas rica y tambien la mas peligrosa a nivel contractual;
- distingue bien entre:
  - potencia de sesion util (`icu_weighted_avg_watts`, `icu_joules_above_ftp`, `icu_max_wbal_depletion`)
  - derivados calculables (`icu_variability_index`, `icu_efficiency_factor`)
  - modelos coach (`icu_pm_*`, `icu_rolling_*`, `ss_*`, `p_max`, `MaxPwr`)
  - metadata de la senal (`device_watts`, `power_field*`, hardware)
- aqui es donde mas facil es sobrecanonizar cosas opacas.

Destino preliminar:

- `icu_weighted_avg_watts`, `icu_joules_above_ftp`, `icu_max_wbal_depletion` → candidatos condicionales
- `icu_variability_index`, `icu_efficiency_factor`, `icu_power_hr*` → `analysis/`
- `icu_pm_*`, `icu_rolling_*`, `ss_*`, `p_max`, `MaxPwr` → `analysis/` macro
- `icu_zone_times` e `icu_power_zones` → `analysis/`
- metadata hardware → no canonizar

### A.7 Cadencia, stride y dinamica de movimiento

Campos:

- `average_cadence`
- `average_stride`
- `icu_cadence_z2`
- `RunningIndex`
- `GAPOverAvgHR`

Lectura:

- `average_cadence` es la señal mas clara y transversal;
- `average_stride` puede ser util en run/trail, pero no debe generalizarse;
- `RunningIndex` y `GAPOverAvgHR` siguen pareciendo indices propietarios poco transparentes.

Destino preliminar:

- `average_cadence` → candidato secundario a `sessions.csv`
- `average_stride` → `analysis/` con semantica por deporte; no candidato canonico transversal
- `RunningIndex`, `GAPOverAvgHR` → descartar por ahora

### A.8 Segmentacion, bloques y logica del coach

Campos:

- `interval_summary`
- `icu_achievements`
- `icu_intervals_edited`
- `icu_lap_count`
- `lock_intervals`
- `skyline_chart_bytes`
- `coach_tick`
- `compliance`
- `icu_chat_id`

Lectura:

- `interval_summary` e `icu_achievements` pueden enriquecer mucho la narrativa;
- `icu_lap_count` e `icu_intervals_edited` pueden servir como contexto de si la sesion fue estructurada o manipulada;
- `skyline_chart_bytes`, `coach_tick`, `compliance`, `icu_chat_id` parecen mas artefactos de UI o del motor coach.

Destino preliminar:

- `interval_summary`, `icu_achievements`, `icu_lap_count`, `icu_intervals_edited` → `analysis/`
- resto → no canonizar

### A.9 Meteorologia y entorno

Campos:

- `has_weather`
- `average_temp`
- `min_temp`
- `max_temp`
- `average_weather_temp`
- `min_weather_temp`
- `max_weather_temp`
- `average_feels_like`
- `min_feels_like`
- `max_feels_like`
- `average_wind_speed`
- `average_wind_gust`
- `prevailing_wind_deg`
- `headwind_percent`
- `tailwind_percent`
- `average_clouds`
- `max_rain`
- `max_snow`

Lectura:

- `average_weather_temp` es el candidato mas util a corto plazo;
- `feels_like`, viento y nubes pueden ser muy valiosos si algun dia se construye una capa de coste ambiental;
- `average_temp` y `average_weather_temp` no son lo mismo: sensor vs weather model.

Destino preliminar:

- `average_weather_temp` → candidato a `sessions.csv`
- bloque restante → `analysis/` o investigacion

### A.10 Flags de control y calidad del dato

Campos:

- `icu_ignore_time`
- `icu_ignore_power`
- `icu_ignore_hr`
- `ignore_velocity`
- `ignore_pace`
- `ignore_parts`
- `has_segments`
- `stream_types`
- `source`

Lectura:

- estos campos son importantes para interpretar si una señal deberia usarse o no;
- no son rendimiento, pero si QA y trazabilidad;
- `stream_types` en particular puede ser muy util para saber si una ausencia es "dato faltante" o "dato inexistente".

Destino preliminar:

- no canonizar en `sessions.csv` de momento
- usarlos como QA o gating de consumo en `analysis/`

### A.11 Tipologia de actividad y contexto de entrenamiento

Campos:

- `commute`
- `race`
- `trainer`
- `sub_type`
- `tags`
- `gear`
- `custom_zones`

Lectura:

- estas banderas pueden mejorar mucho la interpretacion si alguna vez vienen pobladas;
- en este dump estan vacias o poco informativas, pero no conviene olvidarlas.

Destino preliminar:

- mantener en inventario
- no canonizar hasta ver cobertura real

### A.12 Campos presentes pero hoy de valor bajo o incierto

Campos:

- `icu_warmup_time`
- `icu_cooldown_time`
- `icu_training_load_data`
- `icu_weight`
- `icu_sweet_spot_min`
- `icu_sweet_spot_max`
- `icu_power_zones`
- `use_gap_zone_times`
- `group`

Lectura:

- varios son mas bien configuracion o contexto del motor coach;
- `icu_weight` podria ser util solo si algun dia se hace modelado mecanico especifico;
- `icu_sweet_spot_*` e `icu_power_zones` tienen mas sentido en analysis que en contrato canonico.

Destino preliminar:

- dejar inventariados
- no priorizar en Fase 1

### A.13 Campos observados como null en este dump

Campos:

- `attachments`
- `carbs_ingested`
- `carbs_used`
- `coach_tick`
- `compliance`
- `custom_zones`
- `description`
- `gear`
- `gap_zone_times`
- `ignore_parts`
- `kg_lifted`
- `lengths`
- `lock_intervals`
- `oauth_client_id`
- `oauth_client_name`
- `p30s_exponent`
- `pace_load`
- `pace_load_type`
- `pace_zone_times`
- `pace_zones`
- `paired_event_id`
- `perceived_exertion`
- `pool_length`
- `power_meter`
- `power_meter_battery`
- `power_meter_serial`
- `recording_stops`
- `strava_id`
- `sub_type`
- `tags`
- `threshold_pace`
- `timezone`
- `trainer`
- `workout_shift_secs`
- `avg_lr_balance`
- `crank_length`
- `icu_color`
- `icu_power_spike_threshold`
- `icu_rolling_cp`
- `icu_sync_error`

Lectura:

- no deben considerarse "inexistentes";
- solo se observan como null en este dump de 3 actividades;
- conviene revisar historico mayor antes de descartarlos del todo.

### A.14 Conclusion del anexo exhaustivo

Tras esta pasada exhaustiva, la conclusion operativa queda mejor fundada:

- no parece que haya quedado fuera ningun **bloque importante** del payload sin identificar;
- si habia varios **campos secundarios o de QA** que no estaban suficientemente explicitados en el informe principal;
- y el mayor riesgo ya no es "olvidar un campo", sino **sobrerreaccionar a su mera existencia** sin validar cobertura, semantica y utilidad real.

Regla final de este anexo:

1. **campo presente** no significa **campo util**
2. **campo util** no significa **campo canonico**
3. el filtro correcto sigue siendo:
   - cobertura
   - interpretabilidad
   - ortogonalidad
   - utilidad operacional

## Análisis técnico 2026-04-23

### Estado actual del código
- Fases 1-4 cerradas: `build_sessions.py:2142-2149` persiste `trimp`, `decoupling`, `icu_weighted_avg_watts`, `icu_joules_above_ftp`, `icu_max_wbal_depletion` en `sessions.csv` como primitivas condicionadas a `device_watts`.
- Capa `analysis_only_context` operativa en `analysis/session_analysis_pipeline.py:921-1050` con `subjective_coherence`, `thermal_cost_score` y `durability` por tercios. La referencia antigua a `build_load_mismatch_context :1787-1870` quedó obsoleta tras refactorización; en el código actual las piezas relevantes viven en `build_load_mismatch_context(...)` `:2069-2141`, `build_thermal_context(...)` `:2144-2169`, `build_composite_context(...)` `:3186-3206`, y su consumo narrativo aparece en `:1095`, `:1119` y `:1129`.
- Sidecars canónicos ya activos: `ENDURANCE_HRV_intensity_distribution_weekly.csv` (DO-01), `ENDURANCE_HRV_wellness_subjective.csv` (RE-02).
- `build_sessions.py:1644` genera `build_intensity_distribution_weekly()` con patrones (`polarized`, `pyramidal`, `threshold`, `mixed`).

### Valor actual
- SYA-03 sigue siendo la fuente de verdad doctrinal; evita sobrecanonización y disciplina el flujo de nuevas métricas. Ha validado empíricamente su enfoque (fases 1-4 cerradas sin romper contrato).
- El anexo exhaustivo A.1-A.14 conserva valor como inventario de fallback si aparecen nuevos dumps ampliados.

### Errores/riesgos
- Sección `8.1 Priorizacion refinada` introdujo decisiones que ya están asignadas a SYA-08/10 y debe leerse como guion inmutable; riesgo de reinterpretación si SYA-08 o SYA-10 la tocan sin actualizar aquí.
- El MD tiene 1626+ líneas y empieza a ser difícil de navegar; conviene considerar extraer el anexo A a un fichero aparte si crece más.
- Falta una sección explícita "estado actual de cierre" que enumere qué fases están cerradas y qué columnas finales quedaron canonizadas.

### Mejoras propuestas
1. Añadir al inicio un bloque "estado de cierre 2026-04-23" con columnas canonizadas efectivas y señales en `analysis_only_context`.
2. Extraer Anexo A a `docs/HRV/SYA-03 Anexo inventario exhaustivo.md` cuando se actualice, enlazando desde el maestro.
3. Tras cierre de SYA-08/09/10, incorporar los enlaces a sus MDs en el bloque "Plantilla obligatoria de trazabilidad" (`:1147`).

### Conclusión
SYA-03 sigue plenamente vigente como documento maestro. Su rol ha cambiado: de exploración a guion operativo de gobernanza para SYA-08/09/10. Mantenerlo como fuente única de verdad; los análisis siguientes deben referenciarlo y cerrar sus capítulos pendientes sin reabrir decisiones ya tomadas.
