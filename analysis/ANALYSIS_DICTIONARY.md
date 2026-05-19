<!-- dict_version: 1.2 — SYA-13 + jargon cleanup -->
# ANALYSIS_DICTIONARY.md — Diccionario local de `analysis/`

> **Propósito:** centralizar el significado de artefactos, contextos JSON, labels y taxonomías
> que viven exclusivamente en el módulo `analysis/`. NO amplía ni modifica el diccionario
> canónico HRV (`docs/contracts/`). La distinción entre semántica canónica y semántica local
> es explícita en cada entrada.

---

## Índice

1. [Artefactos de sesión](#1-artefactos-de-sesión)
2. [Contextos JSON de sesión](#2-contextos-json-de-sesión)
   - [analysis_only_context](#analysis_only_context)
   - [narrative_targets](#narrative_targets)
   - [composite_context](#composite_context)
   - [composite_context.subjective_coherence](#composite_contextsubjective_coherence)
   - [composite_context.thermal_context](#composite_contextthermal_context)
   - [composite_context.durability_context](#composite_contextdurability_context)
   - [terrain_context](#terrain_context)
   - [terrain_fit_context](#terrain_fit_context)
   - [runaware_context](#runaware_context)
   - [durability_context (análisis de durabilidad)](#durability_context-análisis-de-durabilidad)
   - [efficiency_context (análisis de eficiencia)](#efficiency_context-análisis-de-eficiencia-en-subidas)
   - [rr_context](#rr_context)
   - [subjective_context](#subjective_context)
   - [session_cost_model](#session_cost_model)
   - [v1_snapshot](#v1_snapshot)
   - [v1_shadow_comparison](#v1_shadow_comparison)
3. [Labels de clasificación](#3-labels-de-clasificación)
   - [durability_pattern](#durability_pattern)
   - [durability_hint y durability_hint_detail](#durability_hint-y-durability_hint_detail)
   - [efficiency_pattern](#efficiency_pattern-patrón-de-eficiencia-en-subidas)
   - [coste_dominante](#coste_dominante)
   - [intensity_category](#intensity_category)
   - [terrain_class](#terrain_class)
   - [power_source](#power_source)
   - [strength_grade](#strength_grade)
   - [runaware_severity_candidate](#runaware_severity_candidate)
   - [thermal_band](#thermal_band)
   - [subjective_coherence_state](#subjective_coherence_state)
4. [Señales exploratorias](#4-señales-exploratorias)
5. [Notas de alcance](#5-notas-de-alcance)

---

## Glosario de siglas internas

Antes de entrar en el detalle, estas siglas aparecen frecuentemente:

| Sigla | Qué es | Dónde aparece |
|-------|--------|---------------|
| **AP-01** | Clustering de intensidad (v1): algoritmo que clasifica sesiones como `work_intense` o no basándose en bloques de trabajo y zonas. | En `v1_snapshot`, `v1_shadow_comparison`, `intensity_category`. |
| **AP-03** | Clustering validado en sombra: variante experimental que enriquece AP-01 con datos de terreno y potencia para trail run. | En `runaware_context`, generalmente con nota "solo análisis, no reemplaza v1". |
| **FP-01** | Análisis de durabilidad: evalúa si la potencia/velocidad cae o la FC sube de la primera a la última mitad de la sesión (fatiga). | En `durability_context`, `durability_pattern`, `durability_hint`. |
| **FP-06** | Análisis de eficiencia en subidas: compara subidas early vs late del mismo rango de pendiente para detectar pérdida de eficiencia. | En `efficiency_context`, `efficiency_pattern`, `matched_climbs.csv`. |
| **FP-07** | Auditoría reproducible de la clasificación de eficiencia contextual: separa `mixed_signal` en huecos de umbral vs combinaciones no taxonomizadas y regenera el barrido histórico. | En `efficiency_audit`, `analysis/efficiency_context_audit.py`. |
| **v1** | Primera generación de algoritmos (ej. AP-01 v1). Implica algo estable y probado. | En `v1_snapshot`, `v1_shadow_comparison`, `v1_shadow_history`. |
| **Sombra (shadow)** | Análisis experimental que se ejecuta en paralelo pero no reemplaza la decisión oficial. Permite compara sin modificar. | En `runaware_context` (sombra para AP-01), `v1_shadow_comparison` (resultado de la comparación). |

---

## 1. Artefactos de sesión

Cada sesión analizada genera un directorio bajo `analysis/reports/<año>/<mes>/<fecha>_<deporte>_<id>/`.
Los archivos de contexto viven en `artifacts/`; los informes y prompts en la raíz del directorio de sesión.

| Artefacto | Ruta relativa | Descripción |
|---|---|---|
| `session_payload.json` | `artifacts/session_payload.json` | Fuente principal de la sesión: contiene el contexto enriquecido completo (`analysis_only_context`, `composite_context`, `terrain_context`, `terrain_fit_context`, `runaware_context`, `durability_context`, señales de recuperación). Es "humana" porque concentra datos curados y contexto coach que el analista necesita para narrar, a diferencia de `summary.json` que es reproducible pero más árido. |
| `summary.json` | `artifacts/summary.json` | Salida técnica reproducible del pipeline: contiene `session_cost_model`, el flag `rr_unavailable` y métricas calculadas. Se puede regenerar siempre que existan las fuentes; no depende de datos manuales ni de decisiones de curation. |
| `session_row.json` | `artifacts/session_row.json` | Copia de la fila de `sessions.csv` correspondiente a esta sesión. Permite acceder a los valores canónicos de la sesión sin leer el CSV completo. |
| `technical_report.md` | `technical_report.md` | Resumen estructurado generado automáticamente por `session_analysis_pipeline.py`; útil para navegación rápida pero no es fuente primaria. No citar como evidencia del caso en el informe. |
| `analyst_prompt.md` | `analyst_prompt.md` | Contrato operativo de la sesión para el agente LLM: incluye instrucciones de lectura, jerarquía de fuentes y narrativa estructurada. Se genera una sola vez por sesión y no se sobreescribe. |
| `ai_handoff.md` | `ai_handoff.md` | Documento de traspaso al agente LLM: lista qué archivos leer, en qué orden y qué declarar si alguno falta. Complementa `analyst_prompt.md`. |
| `report.ia.md` | `report.ia.md` | Informe final redactado por el agente LLM a partir del `analyst_prompt.md`. Es la salida de análisis narrativo de la sesión. |
| `session_stream.csv` | `artifacts/session_stream.csv` | Señal temporal de FC, cadencia y velocidad/potencia muestreada a ~1Hz. Es la base del análisis de durabilidad por tercios: al dividir la sesión en tres segmentos iguales de tiempo, se puede ver si el rendimiento aguanta o se degrada. |
| `session_rr.csv` | `artifacts/session_rr.csv` | Intervalos RR brutos exportados desde Polar. Solo existe cuando hay datos RR válidos para la sesión. Si está ausente, `summary.json` registra `rr_unavailable = true`. |
| `terrain_intervals.csv` | `artifacts/terrain_intervals.csv` | Splits de terreno desde Intervals.icu: cada fila es un segmento de la sesión clasificado por tipo (`uphill`, `downhill`, `rolling`, `unknown`), con métricas de distancia, tiempo, FC, VAM, potencia y zona. Es la base del `terrain_context` agregado. |
| `terrain_climbs.csv` | `artifacts/terrain_climbs.csv` | Subidas individuales detectadas desde el archivo FIT: cada fila es una subida con su desnivel, pendiente media, VAM, FC, potencia y distribución de zonas. Es la base del `terrain_fit_context`. Distinto de `matched_climbs.csv`, que agrupa subidas por bin de pendiente para FP-06. |
| `matched_climbs.csv` | `artifacts/matched_climbs.csv` | Tabla FP-06: subidas agrupadas por bin de pendiente (`low_grade` 3–7%, `mid_grade` 7–12%, `high_grade` 12%+). Comparar una subida del 4% con una del 15% no tiene sentido fisiológico, por eso se agrupan: solo se comparan subidas del mismo rango para detectar si la eficiencia cae entre las primeras y las últimas. Solo existe cuando FP-06 es aplicable; `FP-07` puede regenerar su barrido histórico desde `summary.json` + este sidecar. |
| `coach_intervals.csv` | `artifacts/coach_intervals.csv` | Intervalos de entrenamiento exportados de Intervals.icu. Capa local de apoyo: útil para identificar bloques o repeticiones con valor táctico, pero no es contrato canónico. |
| `coach_groups.csv` | `artifacts/coach_groups.csv` | Grupos de intervalos agrupados por bloque; complementa `coach_intervals.csv` para sesiones con estructura repetida (p.ej. series). |
| `coach_metrics.json` | `artifacts/coach_metrics.json` | Versión fichero independiente de `analysis_only_context.coach_metrics`. Permite cargar solo las métricas coach sin leer el payload completo. |
| `v1_shadow_history.json` | `artifacts/v1_shadow_history.json` | Histórico de concordancia entre el clustering estable (AP-01 v1) y el análisis enriquecido con terreno (AP-03, "sombra") en sesiones de trail previas. Muestra si ambos análisis convergen o divergen típicamente, útil como contexto de calibración. Solo existe en trail. |

> **Artefactos de depuración:** si `keep_debug_artifacts=True`, se generan bajo `debug/`: `rr_beats.csv`, `dfa_alpha1.csv`, `rmssd_1min.csv`, `rmssd_5min.csv`. No usar como fuentes analíticas primarias.

**Regla de lectura:** Usar `session_payload.json` como fuente principal para la narrativa; `summary.json` para verificar métricas técnicas. No citar `technical_report.md` ni informes anteriores como evidencia del caso actual.

---

## 2. Contextos JSON de sesión

### `analysis_only_context`

**Aparece en:** `session_payload.json.analysis_only_context`, generado por `session_analysis_pipeline.py`.

**Qué es:** Objeto JSON que agrupa métricas subjetivas/coach, estructura de sesión y señales locales que el módulo `analysis/` obtiene de Intervals.icu pero que no forman parte del pipeline HRV canónico ni de `sessions.csv`. Existe porque hay información útil para el análisis (percepción de esfuerzo, distribución de zonas, estructura del workout) que no tiene un hogar en los CSVs canónicos y que tampoco debe elevarse a contrato global.

**Subobjetos:**

| Clave | Descripción |
|---|---|
| `coach_metrics` | Métricas de carga y percepción de Intervals.icu: `session_rpe`, `icu_rpe`, `feel`, `icu_intensity_pct`, `hr_load`, `hr_load_type`, `power_load`, `pace_load`, `decoupling_pct`, `cardiac_drift_pct`, `average_stride`, `strain_score`, `polarization_index`. |
| `structured_workout` | Descripción del workout estructurado si existe: `intervals_count`, `groups_count`, `interval_types`, `labels_preview`, `lap_count`, `intervals_edited`. Da acceso a `coach_intervals.csv` y `coach_groups.csv`. |
| `route_context` | Contexto de ruta: `route_id`, `gap_raw`, `gap_unit`, `gap_model`; no es fuente de terreno (para eso, usar `terrain_fit_context`). |
| `zone_context` | Distribución de zonas: `hr_zone_times`, `power_zone_times`; complementaria, no canónica. |
| `achievements` | Logros registrados en Intervals.icu: `count`, `preview`; contexto informativo, sin impacto analítico. |
| `composite_context` | Ver sección independiente; incluye `subjective_coherence`, `thermal_context`, `durability_context`. |

**Cuándo aplica:** Siempre que exista la clave en `session_payload.json`. Si no existe, declararlo como limitación.

**Qué NO significa:** No es contrato canónico. `coach_metrics` no reemplaza ni contradice `sessions.csv`, `training_audit` ni la capa RR. `session_rpe` e `icu_rpe` son capas subjetivas/coach locales, no equivalentes directos de `load` o `trimp`.

**Canon:** ❌ Local de `analysis/`.

---

### `narrative_targets`

**Aparece en:** `session_payload.json.narrative_targets`, generado por `session_analysis_pipeline.py`.

**Qué es:** Contenedor de anclajes narrativos para el informe de sesión. Separa la capa de render final de `reason_text` de los anclajes estructurados que explican el error, el encaje en el bloque y la lectura operativa final. No es un contrato canónico global; su función es estabilizar la narrativa local de `analysis/`.

**Subobjetos:**

| Clave | Descripción |
|---|---|
| `final_reason_rendered` | Render estructurado de `reason_text` y de las cautelas tipificadas. Incluye `gate_readout`, `reason_items`, `action_readout`, `baseline_readout` e `instructions`. |
| `error_context` | Ancla para `Donde Estuvo el Error`: resume `gate_mode`, `gate_badge`, `gate_vs_execution_delta`, `execution_coherence`, `cost_vs_gate_mismatch`, `positive_count`, `negative_cost_count`, `thermal_penalty` y `durability_hint`. Se usa para distinguir error de decisión, de dosificación o de encaje. |
| `exit_context` | Ancla para `Como Habria Encajado Mejor`, `Que Construye vs Que Consume` y `Que Repetir / Que No Repetir`: resume `execution_quality`, `block_role_signals` y `adaptation_signals`. `load_rank_in_sport_7d` se calcula sobre una ventana real de 7 días por deporte, no sobre un recorte visual de sesiones recientes. |

**Cuándo aplica:** Siempre que exista `session_payload.json`. Los anclajes pueden construirse aunque `rr_unavailable = true`, porque dependen de la sesión, del bloque y del contexto local de `analysis/`, no de la capa RR fina.

**Qué NO significa:** No es contrato canónico. No debe leerse como sustituto de `analysis_only_context`, `composite_context` ni `final_reason_items`; es una capa de orquestación narrativa sobre esas señales.

**Canon:** ❌ Local de `analysis/`.

---

### `composite_context`

**Aparece en:** `session_payload.json.composite_context` y dentro de `analysis_only_context.composite_context`.

**Qué es:** Contenedor exploratorio que agrupa tres capas de contexto que no están en el pipeline canónico pero que enriquecen la lectura de la sesión: si el atleta percibió el esfuerzo de forma coherente con lo que dicen los datos objetivos, cuánto pudo haber pesado el calor, y si el rendimiento aguantó a lo largo de la sesión. Se construye con `build_composite_context()` en `session_analysis_pipeline.py`. Las tres capas son independientes entre sí: pueden existir en cualquier combinación.

**Subobjetos:** `subjective_coherence`, `thermal_context`, `durability_context`.

**Qué NO significa:** No es contrato canónico. Ninguna de las tres capas puede contradecir `sessions.csv`, `training_audit` ni la capa RR sin declarar explícitamente la discrepancia. Son apoyo narrativo, no fuente de decisión.

**Canon:** ❌ Local de `analysis/`.

---

### `composite_context.subjective_coherence`

**Aparece en:** `composite_context.subjective_coherence`, generado por `build_load_mismatch_context()`.

**Qué es:** Comparación lineal normalizada entre `session_rpe_load_equiv` (carga subjetiva Foster) y métricas objetivas de carga (`hr_load`, `trimp`). Indica si la percepción de esfuerzo del atleta es coherente con las señales objetivas.

**Campos clave:**

| Campo | Tipo | Descripción |
|---|---|---|
| `subjective_coherence_state` | string | Ver [subjective_coherence_state](#subjective_coherence_state). |
| `subjective_objective_gap_pct` | float | Diferencia porcentual entre `session_rpe_load_equiv` y el ancla objetiva. Mide cuánto se aleja la percepción del atleta de lo que marcan los datos. |
| `objective_spread_pct` | float | Dispersión entre los propios indicadores objetivos (`hr_load` vs `trimp`). Si los objetivos ya se contradicen entre sí, el gap subjetivo/objetivo tiene menos peso. |
| `session_rpe_load_equiv` | float | Equivalente de carga subjetiva derivado de `session_rpe` y reescalado al rango histórico de `load`. Si existe una referencia histórica (`session_rpe_load_ratio_ref`), el pipeline divide `session_rpe` por esa ratio; si no existe, usa un fallback simple (`session_rpe / 10`). La idea no es reconstruir Foster al detalle, sino poner la percepción en una escala comparable con las cargas objetivas. |
| `trimp_load_equiv` | float | TRIMP normalizado al rango habitual del atleta, usado como ancla objetiva de referencia. |
| `subjective_coherence_score` | float | Score 0-100 que resume el nivel de coherencia: 100 = percepción exactamente alineada con el ancla objetiva; decrece con el gap subjetivo/objetivo. |

**Cuándo aplica:** Cuando existe `session_rpe` y el pipeline puede reunir al menos dos señales objetivas comparables entre `load`, `trimp_load_equiv` y `hr_load`. Si solo hay una señal objetiva, la capa no se genera porque el contraste sería demasiado débil.

**Qué NO significa:** `session_rpe_load_equiv` y `trimp_load_equiv` no son conversiones fisiológicas exactas; son comparaciones lineales para detectar discrepancias relativas. No presentar como diagnóstico de sobreentrenamiento.

**Canon:** ❌ Local de `analysis/`.

---

### `composite_context.thermal_context`

**Aparece en:** `composite_context.thermal_context`, generado por `build_thermal_context()`.

**Qué es:** Estimación simple del costo térmico de la sesión basada en `average_weather_temp` de Intervals.icu.

**Campos clave:**

| Campo | Tipo | Descripción |
|---|---|---|
| `temperature_c` | float | Temperatura media durante la sesión (°C). |
| `thermal_band` | string | Ver [thermal_band](#thermal_band). |
| `thermal_cost_score` | float | Puntuación de costo térmico estimado. |
| `threshold_c` | float | Umbral de temperatura usado para clasificar la banda (fijo en 20.0 °C base, ajustado por deporte/duración). |
| `excess_c` | float | Grados por encima del umbral; input principal del `thermal_cost_score`. |
| `duration_min` | float | Duración de la sesión (min), segundo input del modelo térmico. |

**Cuándo aplica:** Cuando existe `average_weather_temp` en los datos de Intervals.icu.

**Qué NO significa:** No es WBGT ni diagnóstico cerrado de estrés por calor. `thermal_band = low` o `marginal` sirve para descartar que el calor explique una deriva; no merece protagonismo propio.

**Canon:** ❌ Local de `analysis/`.

---

### `composite_context.durability_context`

**Aparece en:** `composite_context.durability_context`, generado por `build_durability_thirds_context()`.

**Qué es:** Lectura exploratoria de durabilidad que divide la sesión en tres segmentos iguales de tiempo a partir de `session_stream.csv`, y compara el primer tercio con el último en potencia/velocidad y FC. La idea es simple: si en el último tercio la potencia baja o la FC sube respecto al primero, puede haber señal de fatiga. Es más exploratoria que la capa FP-01 porque depende de la calidad del stream y del terreno.

**Campos clave:**

| Campo | Tipo | Descripción |
|---|---|---|
| `basis` | string | Siempre `stream_elapsed_sec_equal_thirds`; confirma el método de división. |
| `thirds` | list[dict] | Lista de 3 elementos, uno por tercio. Cada uno incluye: `third` (1/2/3), `start_sec`, `end_sec`, `duration_sec`, `n_samples`, `hr_mean`, `speed_mean_kmh`, `cadence_mean` y coberturas (`hr_coverage_pct`, `speed_coverage_pct`, `cadence_coverage_pct`). |
| `delta_first_last_pct` | dict | Variación porcentual del último tercio respecto al primero para `hr`, `speed_kmh` y `cadence`. Es la señal principal de si hubo deriva o caída. |
| `cadence_change_abs_pct` | float | Cambio absoluto de cadencia entre primer y último tercio (pct). Señal de fatiga neuromuscular en running. |
| `durability_hint` | string | Ver [durability_hint y durability_hint_detail](#durability_hint-y-durability_hint_detail). |
| `durability_hint_detail` | string | Subtipo del hint cuando el valor principal es ambiguo (p.ej. `terrain_confounded_hr_peak`). |
| `interpretation_confidence` | string | `low`, `medium` o `high`; depende de la cobertura del stream y del terreno. |
| `rolling_only_context` | dict | Variante de control para trail/hike: repite el análisis de tercios excluyendo los segmentos de subida. Suele ser más interpretable que los tercios brutos en terreno accidentado. Mismos campos que el objeto raíz. |
| `n_samples` | int | Total de muestras del stream usadas; indica si el stream era denso o fragmentado. |
| `method` | string | Descripción del método aplicado. |
| `notes` | list[string] | Advertencias del pipeline (p.ej. cobertura baja, terreno irregular). |

**Cuándo aplica:** Cuando existe `session_stream.csv` en los artefactos de la sesión.

**Qué NO significa:** No es la capa FP-01 (esa lee desde primitivas de `sessions.csv`). No convertir en taxonomía fuerte por deporte. En trail, si `power_ratio` aparece sin perfil de terreno por mitades, tratar como señal ambigua.

**Canon:** ❌ Local de `analysis/`.

---

### `terrain_context`

**Aparece en:** `session_payload.json.terrain_context`, generado por `fetch_intervals_activity_terrain_context()` o construido desde datos FIT.

**Qué es:** Resumen agregado de terreno de la sesión obtenido de Intervals.icu o del archivo FIT: desnivel global, VAM media uphill y cuenta de splits por tipo de terreno. A diferencia de `terrain_fit_context`, no desciende al nivel de subida individual; da una visión panorámica del perfil de la sesión.

**Campos clave:**

| Campo | Tipo | Descripción |
|---|---|---|
| `source` | string | Origen del dato: `intervals_activity` (desde Intervals.icu) o indicador de FIT. |
| `gap_mean` | float | GAP medio (Gradient-Adjusted Pace) para la sesión (min/km o km/h según `gap_unit`): el ritmo equivalente en llano considerando el desnivel total. |
| `gap_unit` | string | Unidad del GAP: `km/h` o `min/km`. |
| `gap_model` | string | Modelo usado para calcular el GAP (p.ej. `minetti`); `None` si no se aplicó modelo. |
| `vam_uphill_mean` | float | VAM medio en tramos de subida (m/h): metros verticales ganados por hora, indicador de eficiencia de subida agregada. |
| `uphill_split_count` | int | Número de segmentos clasificados como subida en el perfil de la sesión. |
| `rolling_split_count` | int | Número de segmentos clasificados como terreno ondulado. |

**Cuándo aplica:** Deportes compatibles con terreno (`trail_run`, `road_run`, `hike`, `bike`) cuando hay datos de desnivel.

**Diferencia clave con `terrain_fit_context`:** `terrain_context` es el resumen global (viene de Intervals.icu o de los datos GPS agregados); `terrain_fit_context` es el análisis granular subida a subida desde el archivo FIT. Si existe FIT, preferir `terrain_fit_context` para leer el coste de subida con detalle.

**Canon:** ❌ Local de `analysis/`.

---

### `terrain_fit_context`

**Aparece en:** `session_payload.json.terrain_fit_context`, generado por `analyze_fit_climbs()` en `fit_terrain_utils.py`.

**Qué es:** Análisis granular de subidas individuales extraído del archivo FIT. A diferencia de `terrain_context` (que da un resumen global), aquí cada subida detectada tiene sus propias métricas: FC, VAM, potencia, tiempo y pendiente. El objeto también incluye resúmenes agregados con los promedios de todas las subidas.

**Campos clave:**

| Campo | Tipo | Descripción |
|---|---|---|
| `climb_count` | int | Número de subidas detectadas. |
| `climb_gain_m` | float | Desnivel total acumulado en subidas (m). |
| `climb_distance_km` | float | Distancia total recorrida en subidas (km). |
| `climb_gain_coverage_pct` | float | Porcentaje del desnivel total de la sesión que está cubierto por las subidas detectadas; indica si el FIT capturó bien el perfil. |
| `climb_time_min` | float | Tiempo total en subidas (min). |
| `climb_hr_mean` | float | FC media global en subidas (lpm). |
| `climb_cadence_mean` | float | Cadencia media en subidas; en running = pasos/min, en bike = rpm. |
| `climb_z3_pct_mean` | float | Porcentaje medio de tiempo en Z3 durante subidas. Señal de intensidad cardiovascular en el tramo dominante. |
| `climb_vam_mean` | float | VAM media en subidas (m/h). |
| `climb_power_mean` | float | Potencia media en subidas (W); ver `climb_power_source`. |
| `climb_power_max` | float | Potencia máxima registrada en subidas (W). |
| `climb_power_source` | string | Ver [power_source](#power_source); indica si la potencia es medida o estimada. |
| `signals_available` | dict | Booleanos `{ hr, cadence, power }` que indican qué señales tenía el FIT. Útil para saber de antemano la completitud del análisis. |
| `cadence_unit` | string | `strides_per_min` (running) o `rpm` (ciclismo). |
| `pause_filter_mode` | string | Modo de filtro de pausas: `fit_event` (pausa detectada por evento FIT) o `heuristic_stationary` (pausas inferidas por velocidad cero). Afecta a la limpieza del stream. |
| `validation_vs_v2` | dict | Resultado de validación interna: `status`, lista de `warnings` e `infos`, y `checks` realizados. Si `warnings` no está vacío, la cobertura o calidad del FIT puede ser parcial. |

**Cuándo aplica:** Cuando existe archivo FIT con datos de GPS y desnivel.

**Qué NO significa:** `climb_power_mean` de bike con `climb_power_source = estimated` proviene de un modelo físico (gravedad + rodadura + aerodinámica), no de potenciómetro; no comparar con FTP ni usar para validar umbrales de potencia.

**Canon:** ❌ Local de `analysis/`.

---

### `runaware_context`

**Aparece en:** `session_payload.json.runaware_context`, generado por `build_runaware_context()`.

**Qué es:** Análisis enriquecido para trail run que usa datos de terreno, FC y potencia para evaluar intensidad. El clustering estable (AP-01 v1) da la decisión oficial; `runaware_context` explora, en paralelo y sin modificarla, si el terreno podría justificar una clasificación diferente. Es una candidatura alternativa para comparar, nunca une reemplazo.

**Campos clave:**

| Campo | Tipo | Descripción |
|---|---|---|
| `applicable` | bool | `true` si la sesión es un deporte de running con terreno suficiente para evaluar. |
| `shadow_only` | bool | Siempre `true`; confirma que este contexto no reemplaza la decisión AP-01 v1. |
| `source` | string | Origen de la señal de intensidad: `terrain` (solo terreno), `power` (solo potencia), `combined` (ambos). |
| `strength` | string | `strong` (señales sólidas) o `exploratory` (evidencia parcial o ambigua). Distinto de `strength_grade`, que describe el subtipo específico. |
| `strength_grade` | string | Ver [strength_grade](#strength_grade); subtipo específico de la señal. |
| `terrain_ready` | bool | `true` si los datos de terreno son suficientes para evaluar; `false` si solo hay potencia. |
| `runaware_intense_candidate` | int (0/1) | 1 si la sesión es candidata a `work_intense` por señales de terreno+FC. |
| `runaware_severity_candidate` | string | Ver [runaware_severity_candidate](#runaware_severity_candidate). |
| `intensity_category` | string | Valor de `intensity_category` de `sessions.csv` para esta sesión; contexto de partida para la evaluación. |
| `run_power_available` | int (0/1) | 1 si existe potencia medida en running para la sesión. |
| `power_ratio` | float | Ratio de potencia media segunda mitad / primera mitad; señal de durabilidad mecánica desde potencia. |
| `terrain_climb_hr_mean` | float | Alias directo de `terrain_fit_context.climb_hr_mean`; FC media en subida. |
| `terrain_climb_vam_mean` | float | Alias de `terrain_fit_context.climb_vam_mean`; VAM media en subida. |
| `terrain_climb_power_mean` | float | Alias de `terrain_fit_context.climb_power_mean`; potencia media en subida. |
| `v1_snapshot` | dict | Copia del `v1_snapshot` (ver [v1_snapshot](#v1_snapshot)) embebida en este contexto para facilitar la comparación. |
| `v1_shadow_comparison` | dict | Resultado de la comparación directa entre la decisión v1 y la candidatura sombra (ver [v1_shadow_comparison](#v1_shadow_comparison)). |
| `notes` | list[string] | Advertencias del pipeline sobre la calidad o limitaciones de la evaluación. |

**Cuándo aplica:** Sesiones de `trail_run`, `road_run` o similares con datos de terreno suficientes.

**Qué NO significa:** No es contrato HRV canónico. No reemplaza la decisión AP-01 v1; es una candidatura en sombra para comparar.

**Canon:** ❌ Local de `analysis/`.

---

### `durability_context` (análisis de durabilidad)

**Aparece en:** `session_payload.json.durability_context` (clave raíz, distinta de `composite_context.durability_context`).

**Qué es:** Lectura de durabilidad FP-01 calculada desde primitivas de `sessions.csv` (`decoupling`, `power_ratio`, `speed_ratio`, `durability_applicable`). Es la capa preferente para la narrativa del informe porque lee métricas ya calculadas y fiables.

**Diferencia clave con `composite_context.durability_context`:** Esta capa FP-01 usa métricas de `sessions.csv` — valores ya procesados y confiables (decoupling, power_ratio). La capa de `composite_context` en cambio divide el `session_stream.csv` en tres tercios iguales de tiempo y compara el primero con el último — más exploratoria, más sensible al terreno irregular. Cuando ambas existen, priorizar la capa FP-01 para la narrativa principal.

**Campos clave:**

| Campo | Tipo | Descripción |
|---|---|---|
| `applicable` | bool | `true` si hay datos suficientes en `sessions.csv` para calcular durabilidad. |
| `applicability_reason` | string | Razón de no aplicabilidad si `applicable = false` (p.ej. `no_decoupling_data`). |
| `preferred_signal` | string | `power_ratio` (bike o running con potencia), `speed_ratio` (trail/hike sin potencia), `none` (sin señal mecánica). |
| `decoupling_pct` | float | Decoupling aeróbico de la sesión (de `sessions.csv`). |
| `cardiac_drift_pct` | float | Deriva cardíaca de la sesión (de `sessions.csv`). |
| `power_ratio` | float | Ratio potencia segunda mitad / primera mitad. |
| `speed_ratio` | float | Ratio velocidad segunda mitad / primera mitad. |
| `mechanics_source` | string | Fuente de la señal mecánica: `power`, `speed` o `None`. |
| `run_power_available` | int (0/1) | 1 si hay potencia medida en running. |
| `terrain_sensitivity` | string | `low` (potencia medida, poca sensibilidad al terreno), `medium` o `high` (velocidad en trail, muy sensible). Indica cuánto puede confundir el terreno la lectura. |
| `interpretation_confidence` | string | `low`, `medium` o `high`; depende de la señal preferente y la calidad de los datos. |
| `durability_pattern` | string | Ver [durability_pattern](#durability_pattern). |
| `notes` | list[string] | Advertencias específicas del pipeline (p.ej. terreno irregular, cobertura parcial). |

**Cuándo aplica:** Cuando existen `decoupling` y/o `power_ratio`/`speed_ratio` en `sessions.csv` para la sesión.

**Canon:** ❌ Local de `analysis/`.

---

### `efficiency_context` (análisis de eficiencia en subidas)

**Aparece en:** `session_payload.json.efficiency_context` y reflejado en `matched_climbs.csv`, generado por `compute_matched_climbs_context()` en `fit_terrain_utils.py`. El barrido reproducible asociado se regenera con `analysis/efficiency_context_audit.py`.

**Qué es:** Análisis FP-06 de eficiencia contextual en subidas: compara subidas early vs late de pendiente similar para detectar pérdida de eficiencia a lo largo de la sesión. FP-07 usa el mismo contexto para auditar qué parte de `mixed_signal` es hueco de umbral y qué parte es combinación no taxonomizada.

**Campos clave:**

| Campo | Tipo | Descripción |
|---|---|---|
| `applicable` | bool | `true` si hay ≥2 subidas y al menos un par comparable por bin de pendiente. |
| `applicability_reason` | string | Razón de no aplicabilidad: `fewer_than_2_climbs`, `sport_not_applicable`, `no_timing_data`, `no_comparable_climb_pairs`. |
| `comparison_mode` | string | Siempre `matched_climbs`. |
| `sport_family` | string | Deporte de la sesión; solo aplica a deportes de running. |
| `climb_count` | int | Total de subidas detectadas en la sesión. |
| `matched_groups_count` | int | Número de bins de pendiente con al menos una subida early y una late comparables. |
| `midpoint_sec` | float | Segundo de la sesión usado como frontera entre "early" y "late". |
| `aggregate` | dict | Métricas agregadas de la comparación: `vam_ratio`, `hr_drift_bpm`, `hr_per_vam_ratio`, `power_per_hr_ratio` (floats o None). |
| `efficiency_pattern` | string | Ver [efficiency_pattern](#efficiency_pattern-fp-06). |
| `interpretation_confidence` | string | `low` o `moderate`; depende de cuántas señales usa realmente el clasificador (`vam_ratio`, `hr_drift_bpm`, `hr_per_vam_ratio`). `moderate` aparece cuando las tres están disponibles; `low`, cuando falta alguna. La potencia puede enriquecer la lectura a través de `power_per_hr_ratio`, pero no decide esta confianza. |
| `matched_groups` | list[dict] | Un elemento por bin de pendiente con: `grade_bin`, `grade_range_pct`, `early_count`, `late_count`, métricas medias early/late (hr, vam, power), y ratios de eficiencia. |
| `vam_ratio` | float | VAM late / VAM early (campo en `aggregate`): < 1.0 indica pérdida de capacidad de subida. |
| `hr_drift_bpm` | float | Diferencia FC late − FC early (lpm, en `aggregate`): cuánto sube el coste cardiovascular hacia el final. |
| `hr_per_vam_ratio` | float | Coste cardiovascular relativo por unidad de VAM (en `aggregate`): > 1.0 = las subidas tardías cuestan más FC por metro vertical ganado. |
| `power_per_hr_ratio` | float | Potencia producida por latido late / early (en `aggregate`): < 1.0 indica menor eficiencia mecánica relativa al coste cardíaco. Solo disponible si hay potencia medida. |

**Cuándo aplica:** Deportes de running (`trail_run`, `road_run`, `run`, `hike`) con ≥2 subidas y timing disponible.

**Qué NO significa:** No aplica a bike. No es contrato canónico.

**Canon:** ❌ Local de `analysis/` (FP-06 + FP-07).

---

### `rr_context`

**Aparece en:** `session_payload.json.rr_context` y `summary.json.rr_context`, generado por `build_rr_context()`.

**Qué es:** Objeto que describe la disponibilidad y calidad de los datos RR para la sesión. Es la primera señal que el analista debe revisar: si los RR no están disponibles, varias secciones del informe quedan degradadas o ausentes.

**Campos clave:**

| Campo | Tipo | Descripción |
|---|---|---|
| `modifier` | string | Estado de los RR: `no_rr` (no hay datos), `unavailable` (existen pero no son utilizables), `available` (datos RR válidos). |
| `interpretation` | string | Texto descriptivo del estado para incluir en el informe. |
| `evidence` | list[string] | Lista de razones o evidencias que explican el estado (p.ej. causa de la no disponibilidad). |

**Cuándo aplica:** Siempre; si no existe la clave, asumir `rr_unavailable = true` y declarar la limitación.

**Qué NO significa:** `modifier = no_rr` no invalida el análisis de sesión: el coste cardiovascular/mecánico y la narrativa siguen siendo válidos sin RR. Solo limita las secciones de HRV (RMSSD, DFA α1).

**Canon:** ❌ Local de `analysis/`.

---

### `subjective_context`

**Aparece en:** `session_payload.json.subjective_context`, generado por `build_subjective_context()`.

**Qué es:** Contexto subjetivo del atleta para la sesión: notas manuales escritas en Intervals.icu y un subconjunto compacto de la fila de `sessions.csv`.

**Campos clave:**

| Campo | Tipo | Descripción |
|---|---|---|
| `notes_raw` | string o None | Nota libre escrita por el atleta en Intervals.icu. Si existe, es la voz directa del atleta sobre la sesión y debe incluirse en `Contexto subjetivo` del informe. No mezclar con `session_rpe`, `feel` ni con `load`/`trimp`. |
| `session_row_subset` | dict | Subconjunto de campos de `sessions.csv` para referencia rápida sin abrir el CSV completo. |

**Cuándo aplica:** Cuando existe `notes_raw` o datos de sesión relevantes. Si `notes_raw = None`, la sección de contexto subjetivo del informe puede omitirse o declarar ausencia.

**Canon:** ❌ Local de `analysis/`.

---

### `session_cost_model`

**Aparece en:** `session_payload.json.session_cost_model` y `summary.json.session_cost_model`, generado por `session_cost_model.py`.

**Qué es:** Modelo de coste de sesión que clasifica el esfuerzo dominante como cardiovascular, mecánico o mixto, basándose en FC, potencia, desnivel y zonas. Permite al analista entender qué tipo de estrés predominó sin depender de los RR.

**Campos clave:**

| Campo | Tipo | Descripción |
|---|---|---|
| `coste_dominante` | string | Ver [coste_dominante](#coste_dominante). |
| `cardio_score` | int | Score 0–100 del componente cardiovascular. |
| `mecanico_score` | int | Score 0–100 del componente mecánico (potencia, desnivel, velocidad). |
| `confidence_cardio` | string | `high`, `medium` o `low`; calidad de la señal cardiovascular disponible. |
| `confidence_mecanico` | string | `high`, `medium` o `low`; calidad de la señal mecánica disponible. |
| `cardio_basis` | list[string] | Lista de indicadores que fundamentan el score cardiovascular (p.ej. `z3_pct`, `hr_p95`). |
| `mecanico_basis` | list[string] | Lista de indicadores que fundamentan el score mecánico (p.ej. `elev_gain_m`, `power_watts`). |
| `cardio_evidence` | list[string] | Evidencias detalladas del componente cardio con valores. |
| `mecanico_evidence` | list[string] | Evidencias detalladas del componente mecánico con valores. |
| `inputs_used` | dict | Valores de entrada usados: `vt1_used`, `vt2_used`, `zones_source`, `moving_min`, `elev_gain_m`, `hr_p95`, `z2_pct`, `z3_pct`, `work_n_blocks`, `work_avg_z3_pct`. |

**Cuándo aplica:** Siempre; si `usable = false` (campo que puede aparecer en `summary.json`), declarar que el modelo no es interpretable para esta sesión.

**Qué NO significa:** No es contrato HRV canónico. No reemplaza la lectura de FC temporal ni el análisis de RR. El `coste_dominante` es una clasificación de apoyo para estructurar la narrativa, no un diagnóstico fisiológico cerrado.

**Canon:** ❌ Local de `analysis/`.

---

### `v1_snapshot`

**Aparece en:** `session_payload.json.v1_snapshot` y embebido en `runaware_context.v1_snapshot`.

**Qué es:** Resumen congelado de la decisión de clustering (AP-01 v1) para el día de la sesión. Se preserva así el análisis estable puede compararse con análisis enriquecidos (como `runaware_context` con terreno) sin ser modificado.

**Campos clave:**

| Campo | Tipo | Descripción |
|---|---|---|
| `intensity_clustering_flag` | int o None | 0/1 según AP-01 v1 clasifica la sesión como intensa. |
| `intensity_clustering_severity` | string o None | `low` o `high`; severidad según v1. |

**Cuándo aplica:** Sesiones de trail_run con datos de `sessions.csv` suficientes para AP-01 v1.

**Qué NO significa:** Es la decisión mínima histórica de v1, no la evaluación actual. Comparar con `runaware_context` para ver si la capa sombra sugiere algo diferente, sin presentar ambas como equivalentes.

**Canon:** ❌ Local de `analysis/`.

---

### `v1_shadow_comparison`

**Aparece en:** `session_payload.json.v1_shadow_comparison` y embebido en `runaware_context.v1_shadow_comparison`, generado por `build_v1_shadow_comparison()`.

**Qué es:** Resultado de comparar el clustering estable (`v1_snapshot`) con el análisis enriquecido (`runaware_context`). Muestra si convergen (aligned), divergen (divergent) o si falta señal (insufficient) — útil para saber si el terreno proporciona información adicional relevante.

**Campos clave:**

| Campo | Tipo | Descripción |
|---|---|---|
| `alignment` | string | `aligned` (ambas capas coinciden), `divergent` (señalan cosas distintas), `insufficient` (una o ambas sin datos suficientes). |
| `flag_alignment` | string | `match` o `mismatch`; compara solo el flag binario (0/1). |
| `severity_alignment` | string | `match`, `mismatch` o `None`; compara la severidad (si ambas tienen dato). |
| `v1_snapshot` | dict | Copia del snapshot de v1 para referencia directa. |
| `shadow_candidate` | dict | Resumen de la candidatura sombra: `runaware_intense_candidate`, `runaware_severity_candidate`, `source`. |
| `notes` | list[string] | Observaciones del pipeline sobre la comparación. |

**Cuándo aplica:** Cuando existen tanto `v1_snapshot` como `runaware_context` con datos.

**Qué NO significa:** `divergent` no significa que v1 esté equivocado. Indica que la capa de terreno aporta información adicional que v1 no tenía disponible; el analista decide qué peso darle.

**Canon:** ❌ Local de `analysis/`.

---

## 3. Labels de clasificación

### `durability_pattern`

**Aparece en:** `durability_context.durability_pattern` (FP-01); también en `composite_context.durability_context.durability_pattern` (tercios).

**Valores y significado:**

| Valor | Significado |
|---|---|
| `stable_output` | Potencia/velocidad y FC estables entre tercios; sin señal de fatiga dominante. |
| `cardiovascular_drift_only` | FC sube al final pero la potencia/velocidad se mantiene; solo deriva cardiovascular sin caída mecánica. |
| `mechanical_drop_with_drift` | Baja potencia/velocidad Y sube FC; señal doble de fatiga periférica + cardiovascular. |
| `mechanical_drop_without_drift` | Baja potencia/velocidad sin subida de FC; fatiga periférica sin respuesta cardiovascular. |
| `mixed_signal` | Señales contradictorias; hay indicios de sostenimiento y de cambio, pero no una forma única de fatiga. Leer con prudencia. |
| `not_applicable` | Datos insuficientes para clasificar. |
| `ambiguous_due_to_terrain` | Trail/hike: el terreno en la segunda mitad confunde la lectura; no es señal fisiológica cerrada. |
| `ambiguous_due_to_structure` | Sesión estructurada: los bloques explican la variación mejor que la fatiga. |
| `terrain_confounded` | El terreno explica la variación; no es señal fisiológica cerrada. Ver `durability_hint_detail` para el subtipo. |
| `steady_easy` | Sesión fácil y uniforme; no hay señal de fatiga útil para interpretar. |
| `drift_like` | Patrón similar a deriva cardiovascular, pero sin certeza suficiente para clasificar como `cardiovascular_drift_only`. |
| `fade_like` | Patrón similar a fade mecánico, pero sin certeza suficiente. |
| `negative_split_like` | Aceleración en la segunda mitad; puede reflejar progresión táctica o recuperación tardía. |

**Señal preferente:** `preferred_signal` = `power_ratio` (bike, road_run con potencia), `speed_ratio` (trail/hike, sin potencia) o `none`.

**Confianza:** `interpretation_confidence` = `low`, `medium` o `high`. Afecta al peso narrativo que se le debe dar al patrón.

**`terrain_sensitivity`:** `low` (potencia medida, poco ruido de terreno), `medium`, `high` (velocidad en trail, muy sensible). A mayor sensibilidad, más probable que el patrón sea ruido de perfil y no señal fisiológica.

**Qué NO significa:** No es diagnóstico canónico de fatiga. En trail, si `power_ratio` aparece sin perfil de terreno por mitades, es ambiguo. `mixed_signal` no es señal de problema; es señal de incertidumbre.

**Canon:** ❌ Local de `analysis/`.

---

### `durability_hint` y `durability_hint_detail`

**Aparece en:** `composite_context.durability_context.durability_hint` y `.durability_hint_detail`, generado por `build_durability_thirds_context()`.

**Qué son:** Labels de nivel intermedio que clasifican el patrón detectado en los tercios del stream antes de ser promovido (o no) a `durability_pattern`. Son más granulares que `durability_pattern` y aportan el subtipo cuando el contexto es ambiguo.

**Valores de `durability_hint`:**

| Valor | Significado |
|---|---|
| `steady_easy` | Sesión uniforme y fácil; sin señal de fatiga. Traducir al texto en lugar de omitir. |
| `terrain_confounded` | El perfil de terreno explica la variación; no es señal fisiológica. Ver `durability_hint_detail` para el subtipo. |
| `negative_split_like` | Aceleración en la segunda mitad. |
| `fade_like` | Caída de rendimiento gradual. |
| `stable` | Output estable a lo largo de la sesión. |
| `drift_like` | Deriva cardiovascular con sostenimiento mecánico. |
| `mixed` | Señales contradictorias sin patrón claro. |

**Valores de `durability_hint_detail`** (subtipos de `terrain_confounded`):

| Valor | Significado |
|---|---|
| `terrain_confounded_hr_peak` | La FC sube por una subida concentrada al final, no por fatiga. |
| `terrain_confounded_speed_drop` | La velocidad baja por desnivel positivo acumulado, no por caída muscular. |
| `terrain_confounded_mixed` | Ambas señales (FC y velocidad) están confundidas por el terreno simultáneamente. |

**Regla narrativa:** `terrain_confounded` y `steady_easy` deben traducirse al texto (explicar qué los causó) en lugar de omitirse como "solo exploratorio".

**Canon:** ❌ Local de `analysis/` (exploratorio).

---

### `efficiency_pattern` (patrón de eficiencia en subidas)

**Aparece en:** `efficiency_context.efficiency_pattern`, calculado por `_classify_efficiency_pattern()` en `fit_terrain_utils.py`.

**Valores y significado:**

| Valor | Significado |
|---|---|
| `stable_contextual_efficiency` | VAM ≥ 0.93, FC estable (±5 lpm), costo FC/VAM ≤ 1.04; sin pérdida de eficiencia detectable entre subidas tempranas y tardías. |
| `cardiovascular_efficiency_drop` | Costo FC/VAM elevado (>1.07) sin caída de VAM; mayor coste cardiovascular sin pérdida mecánica visible. |
| `mechanical_efficiency_drop` | VAM cae (<0.90) pero FC estable y costo FC/VAM normal; pérdida mecánica sin deriva cardiovascular. |
| `repeatability_loss_in_climbs` | VAM cae, FC sube y costo FC/VAM sube; pérdida combinada — el atleta produce menos VAM y además le cuesta más FC hacerlo. |
| `mixed_signal` | VAM no disponible o señales contradictorias; confianza baja. Puede venir de `threshold_gap`, `taxonomy_gap` o `data_insufficient` en `efficiency_audit`. |

**Umbrales de clasificación:**
- `vam_ok`: ratio ≥ 0.93; `vam_drop`: ratio < 0.90
- `hr_stable`: |drift| ≤ 5 lpm; `hr_elevated`: drift > 8 lpm
- `cost_ok`: hr_per_vam_ratio ≤ 1.04; `cost_elevated`: > 1.07

**`efficiency_audit`:**

**Aparece en:** `efficiency_context.efficiency_audit`.

**Qué es:** Desglose local de la clasificación de `efficiency_pattern`. No cambia el label canónico local, pero deja trazabilidad de por qué una sesión acabó en `mixed_signal` o en un label más específico.

**Campos principales:**

| Campo | Significado |
|---|---|
| `signals.vam_ratio` | Valor bruto de VAM ratio usado por la clasificación. |
| `signals.hr_drift_bpm` | Valor bruto de deriva HR usado por la clasificación. |
| `signals.hr_per_vam_ratio` | Valor bruto de coste HR/VAM usado por la clasificación. |
| `buckets.vam_ratio` | `ok`, `gray`, `drop` o `missing`. |
| `buckets.hr_drift_bpm` | `stable`, `gray`, `elevated`, `drop` o `missing`. |
| `buckets.hr_per_vam_ratio` | `ok`, `gray`, `elevated` o `missing`. |
| `signal_profile` | Resumen compacto `vam|hr|cost`, por ejemplo `ok|gray|ok`. |
| `threshold_gap_flags` | Lista de huecos de umbral detectados; en CSV se serializa como cadena separada por `|`, por ejemplo `hr_drift_gray_band|hr_per_vam_ratio_gray_band`. |
| `mixed_signal_type` | Para `mixed_signal`, distingue `threshold_gap`, `taxonomy_gap` y `data_insufficient`. |

**Bins de pendiente:**
- `low_grade`: 3–7%
- `mid_grade`: 7–12%
- `high_grade`: 12–100%

**Canon:** ❌ Local de `analysis/` (FP-06).

---

### `coste_dominante`

**Aparece en:** `session_cost_model.coste_dominante`.

**Qué es:** Clasificación del tipo de estrés predominante en la sesión según el balance entre señales cardiovasculares (FC, zonas) y mecánicas (potencia, desnivel, velocidad).

| Valor | Significado |
|---|---|
| `bajo_estimulo` | Sesión de baja intensidad: scores cardiovascular y mecánico ambos bajos. Sin coste dominante útil para interpretar. |
| `cardiometabolico` | El coste cardiovascular domina; la sesión fue exigente para el sistema aeróbico pero no necesariamente para el neuromuscular. |
| `mecanico` | El coste mecánico domina; la sesión fue exigente para la potencia/desnivel/velocidad pero el sistema cardíaco aguantó bien. |
| `mixto` | Ambos scores son altos; la sesión fue exigente en las dos dimensiones. |
| `no_clasificable` | Datos insuficientes para determinar el coste dominante. Declarar la limitación. |

**Canon:** ❌ Local de `analysis/`.

---

### `intensity_category`

**Aparece en:** `sessions.csv.intensity_category` y como input en `runaware_context.intensity_category`.

**Qué es:** Clasificación AP-01 de intensidad de la sesión basada en clustering de carga y zonas. Es el punto de partida para `runaware_context`.

| Valor | Significado |
|---|---|
| `work_intense` | Sesión clasificada como trabajo intenso por AP-01. Umbral de base para `runaware_context`. |
| `work_threshold` | Trabajo en umbral; intensidad elevada pero inferior a `work_intense`. |
| `work_tempo` | Trabajo en tempo; intensidad moderada-alta. |
| `endurance` | Sesión de resistencia aeróbica base. |
| `easy` | Sesión fácil o de recuperación activa. |
| `None` | Sin clasificación disponible. |

**Canon:** ❌ Local de `analysis/` (output de AP-01, no contrato HRV canónico global).

---

### `terrain_class`

**Aparece en:** `terrain_intervals.csv.terrain_class`; cada split de terreno tiene asignado un tipo.

**Qué es:** Clasificación del tipo de terreno de cada segmento de la sesión, usada para construir `terrain_context` y separar señales de subida, bajada y llano.

| Valor | Significado |
|---|---|
| `uphill` | Segmento de subida; desnivel positivo dominante. Fuente de VAM, coste cardiovascular de subida y detección de coste mecánico. |
| `downhill` | Segmento de bajada; desnivel negativo dominante. En running aporta coste excéntrico; en bike, recuperación. |
| `rolling` | Terreno ondulado; combinación de subida y bajada sin dominancia clara. |
| `unknown` | No se pudo clasificar el segmento. Excluir de análisis específicos de tipo de terreno. |

**Canon:** ❌ Local de `analysis/`.

---

### `power_source`

**Aparece en:** `terrain_fit_context.climb_power_source` y `terrain_climbs.csv.power_source`.

**Qué es:** Indica si la potencia registrada en una subida proviene de un sensor real o de una estimación física.

| Valor | Significado |
|---|---|
| `measured` | Potencia medida por potenciómetro real. Fiable para comparar con FTP y umbrales de potencia. |
| `estimated` | Potencia estimada por modelo físico (`road_climb_simple_v1`: gravedad + rodadura + aerodinámica). Solo útil como orden de magnitud; no comparar con FTP ni usar para validar umbrales. |
| `mixed` | Algunas subidas tienen potencia medida y otras estimada. Indicar al narrar qué subidas son fiables. |
| `None` | Sin datos de potencia para la subida. |

**Canon:** ❌ Local de `analysis/`.

---

### `strength_grade`

**Aparece en:** `runaware_context.strength_grade`.

**Qué es:** Subtipo específico de la solidez de la señal de intensidad en `runaware_context`. Complementa `strength` (que solo distingue `strong` / `exploratory`) con más detalle sobre la fuente de la evidencia.

| Valor | Significado |
|---|---|
| `terrain_robust` | Terreno con señal fuerte: `climb_z3_pct` elevado, VAM uphill claro, FC media en subida sobre VT1/VT2. |
| `terrain_moderate` | Terreno con señal moderada: al menos una de las señales es marginal. |
| `terrain_sparse` | Terreno presente pero señal débil; solo hay una subida o las métricas son parciales. |
| `power_only` | La señal de intensidad viene solo de potencia, sin datos de terreno. |
| `combined` | Señal de terreno + potencia; mayor confianza. |
| `exploratory` | No se pudo asignar ninguna de las categorías anteriores. Que sea "exploratory" describe la limitación de clasificación, no la intensidad de la sesión — la evidencia de terreno puede ser robusta aunque el sistema no logre categorizar la fuente de la señal. |

**Canon:** ❌ Local de `analysis/`.

---

### `runaware_severity_candidate`

**Aparece en:** `runaware_context.runaware_severity_candidate`.

| Valor | Significado |
|---|---|
| `high` | La sesión cumple ≥2 umbrales fuertes (p.ej. `climb_z3_pct_mean` ≥ 40% y/o VAM > VT2). Candidatura a `work_intense` con evidencia robusta. |
| `low` | Solo cumple el criterio base (`intensity_category = work_intense`) sin señales de terreno adicionales. |
| `None` | No es candidata a intensidad elevada. |

**Canon:** ❌ Local de `analysis/`.

---

### `thermal_band`

**Aparece en:** `composite_context.thermal_context.thermal_band`.

| Valor | Temperatura orientativa | Uso narrativo |
|---|---|---|
| `low` | `thermal_cost_score <= 0` | El calor no añade coste apreciable en el modelo. Suele ocurrir cuando la temperatura media no supera el umbral base de 20 °C. |
| `marginal` | `0 < thermal_cost_score < 3` | Coste térmico menor. Puede servir para descartar que el calor explique por sí solo una deriva ligera. |
| `moderate` | `3 <= thermal_cost_score < 8` | Coste térmico significativo en este modelo exploratorio. Suele aparecer cuando coinciden calor por encima del umbral y suficiente duración. |
| `high` | `thermal_cost_score >= 8` | Coste térmico alto. Aquí el calor ya merece entrar como factor de contexto en la lectura de deriva o fatiga. |

**Nota:** El modelo actual no ajusta el umbral por deporte: usa `threshold_c = 20.0` para todas las sesiones y luego pondera el exceso térmico por la duración (`moving_min`). Por eso una sesión larga a calor moderado puede acabar con más coste que una sesión corta a más temperatura. La tabla debe leerse como traducción didáctica del `thermal_cost_score`, no como rangos térmicos absolutos tipo WBGT.

**Qué NO significa:** No es WBGT. No reemplaza señales de FC ni de RR. `thermal_band = low/marginal` sirve para descartar; no construir narrativa sobre ello.

**Canon:** ❌ Local de `analysis/`.

---

### `subjective_coherence_state`

**Aparece en:** `composite_context.subjective_coherence.subjective_coherence_state`.

| Valor | Significado |
|---|---|
| `coherent` | `subjective_objective_gap_pct` ≤ 15% y `objective_spread_pct` ≤ 15%; percepción alineada con señal objetiva. |
| `mismatched` | Gap subjetivo-objetivo > 30% o spread objetivo > 30%; discrepancia clara. |
| *(valor intermedio)* | Zona gris (gap 15–30%); usar con cautela y sin protagonismo. |

**Cuándo mencionarlo:** Una vez cuando `coherent` o `mismatched` sea claro y ayude a contextualizar la sesión. No repetir si no cambia la lectura.

**Qué NO significa:** No indica deshonestidad del atleta. No es diagnóstico de sobreestimación ni de subestimación sistemática; es una comparación lineal de escalas normalizadas para el atleta.

**Canon:** ❌ Local de `analysis/`.

---

## 4. Señales exploratorias

Las siguientes señales están presentes en el código y tienen uso narrativo activo, pero no son taxonomías estabilizadas: sus valores, nombres o lógica pueden cambiar sin requerir actualización del diccionario canónico. Tratar como pistas analíticas, no como contratos.

| Señal | Origen | Nota de uso |
|---|---|---|
| `rolling_only_context` | `composite_context.durability_context` | Control para trail/hike que excluye subidas de los tercios; suele ser más interpretable que los tercios brutos en terreno accidentado. Misma estructura que `composite_context.durability_context`. |
| `zones_source` | `analysis_only_context.zone_context` | Si `= fallback`, reducir el peso del bonus técnico trail basado en `work_avg_z3_pct`; la fiabilidad de las zonas es insuficiente para ese uso. |
| `polarization_index` | `analysis_only_context.coach_metrics` | Índice de polarización de la sesión según Intervals.icu; exploratorio, no estabilizado como señal analítica. |
| `v1_shadow_history` | `artifacts/v1_shadow_history.json` | Historial longitudinal de comparaciones v1 vs sombra; útil como contexto de patrón histórico, no como fuente de decisión por sesión. |
| `hrv_rebound_profile` | `analysis/reports/hrv_rebound_profile/*` | Sidecar retrospectivo de rebote HRV D+1/D+3: resume eventos origen, baseline previa, clase de recuperación y lectura semanal. Sirve para absorción de carga y arrastre autonómico, no para el gate diario ni como señal canónica. |
| `weekly_prep_manifest` | `analysis/reports/weekly/<week_start>_<week_end>/weekly_prep_manifest.json` | Manifest local del arranque semanal de `analysis`. Enumera semana, fecha ancla, carpeta base y sidecars generados. Debe actuar como punto único de descubrimiento para que el semanal local consuma sidecars por rutas declaradas y no por convención implícita de nombres. |
| `weekly_analysis_context` | `analysis/reports/weekly/<week_start>_<week_end>/weekly_analysis_context.json` | Sidecar mínimo del borrador semanal automático. Resume semana, manifest consumido y cobertura básica para que `report.auto.md` sea trazable sin reescanear el árbol. |
| `report.auto.md` | `analysis/reports/weekly/<week_start>_<week_end>/report.auto.md` | Borrador semanal reproducible generado por `analyze_weekly.py` desde fuentes canónicas y sidecars descubiertos a través de `weekly_prep_manifest.json`. Es útil como base de trabajo, pero no sustituye una redacción semanal interpretativa completa cuando haga falta juicio fino. |
| `report.ia.md` | `analysis/reports/weekly/<week_start>_<week_end>/report.ia.md` | Informe semanal narrativo final del módulo `analysis/`. Se gobierna por `report_sync_token` y debe leerse junto a `artifacts/report_sync_status.json` para saber si sigue alineado con el semanal técnico actual. |
| `weekly_analyst_prompt` | `analysis/reports/weekly/<week_start>_<week_end>/analyst_prompt.md` | Contrato operativo semanal para el agente LLM. Fija el orden de lectura, obliga a usar `weekly_prep_manifest.json` como punto único de descubrimiento y define cómo tratar `report.auto.md` frente a las fuentes canónicas. |
| `weekly_ai_handoff` | `analysis/reports/weekly/<week_start>_<week_end>/ai_handoff.md` | Resumen ejecutable de archivos a pasar a la IA para redactar el semanal. Repite la jerarquía: manifest primero, fuentes canónicas después, sidecars locales solo como apoyo. |
| `weekly_report_sync_status` | `analysis/reports/weekly/<week_start>_<week_end>/artifacts/report_sync_status.json` | Estado de sincronización del `report.ia.md` semanal respecto al análisis actual. Usa estados `missing`, `unmanaged_legacy`, `stale`, `up_to_date` y expone `current_token` / `report_token` para trazabilidad. |
| `sya15_continuity_report` | `analysis/reports/weekly/<week_start>_<week_end>/artifacts/sya15_continuity_<sport>_<min>of<window>w.(md\|json)` o ruta local indicada por `--report-md/--report-json` | Artefacto local retrospectivo por deporte que resume semanas `usable`, semanas `Z1-dominantes`, continuidad rolling y episodios positivos de SYA-15. El nombre codifica deporte y parametros principales para evitar sobreescritura entre variantes semanales. El JSON asociado usa serialización estricta (`null` en huecos de calendario) y no forma parte del contrato global ni del sidecar canónico. |

---

## 5. Notas de alcance

### Qué ES este diccionario

- Fuente semántica primaria para artefactos, contextos JSON y labels del módulo `analysis/`.
- Documento de referencia para `SESSION_ANALYSIS_METHOD.md`, `AGENTS.md` y `analyst_prompt_rules.md` cuando necesiten enlazar definiciones.
- Base para handoffs y revisiones que involucren la capa analítica local.

### Qué NO ES este diccionario

- No amplía ni modifica `docs/contracts/ENDURANCE_HRV_Diccionario.md` (diccionario canónico HRV).
- No promueve señales exploratorias a contrato global.
- No recalibra thresholds ni rediseña taxonomías.
- No define la lógica HRV canónica del pipeline (gate, semáforos, RMSSD, SWC).

### Política de actualización

Cuando se añada un nuevo contexto, artefacto o label en `analysis/`, actualizar este diccionario en la misma tarea o PR. Si el cambio afecta a semántica canónica, actualizar también `docs/contracts/`.
