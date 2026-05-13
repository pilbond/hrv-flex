# ENDURANCE HRV — Sessions Schema

**Revisión:** r2026-05-13 v3.13 (params_hash: c1c78a78)
**Estado:** Producción

**Documentos relacionados:**
- `ENDURANCE_HRV_Estructura.md` — contrato de datos del sistema completo (CORE, FINAL, DASHBOARD, SLEEP)
- `ENDURANCE_HRV_Spec_Tecnica.md` — fórmulas y algoritmos del gate HRV
- `ENDURANCE_HRV_Diccionario.md` — diccionario de columnas del gate HRV y sidecars

**Convención de versión:** esta cabecera identifica la revisión del pipeline de sesiones (`r2026-05-13 v3.13`), no la versión global del sistema HRV. La versión de sistema vigente se declara en `ENDURANCE_HRV_Spec_Tecnica.md`.

---

## 0. Para qué sirve este pipeline

El gate HRV (CORE → FINAL → DASHBOARD) responde a la pregunta "¿cómo estás hoy?". Pero no sabe **qué hiciste ayer**: no ve si corriste 90 minutos con intervalos en Z3, si hiciste fuerza, o si fue un día de descanso. Esa pieza la aporta el pipeline de sesiones.

Sessions extrae de Intervals.icu el detalle de cada entrenamiento — stream de HR segundo a segundo, velocidad, desnivel — y lo transforma en métricas que describen **la estructura real del trabajo**: cuántos minutos pasaste por encima de VT1 en bloques sostenidos, cuánto de ese trabajo fue en Z3, si terminaste la sesión con el corazón más alto que al principio (drift), y cómo se compara esa sesión con tu histórico reciente.

El resultado alimenta el `reason_text` del gate HRV con avisos de carga ("ACWR alto", "Monotonía alta", "Volumen semanal alto"), pero **nunca modifica el gate ni la acción** — es contexto informativo para tu decisión.

### Alcance

Este pipeline está diseñado para **un único atleta** y consume la cuenta personal de Intervals.icu asociada a ese atleta.

- No pretende agregar ni comparar sesiones entre varios atletas.
- No define particionado por usuario, equipos, coaches ni tenants.
- El uso del endpoint `/athlete/{id}` es una fuente externa concreta, no una señal de que el sistema deba generalizarse a múltiples atletas dentro de la misma instalación.

### Lo que NO hace este pipeline

- ❌ No cambia el semáforo (gate_final sigue dependiendo solo de HRV + pulso)
- ❌ No sustituye a Intervals.icu (que sigue siendo la fuente de carga/TSS/ATL/CTL)
- ❌ No sustituye a Intervals.icu como fuente principal; Polar solo aporta una capa mecánica opcional en deportes de pie cuando hay match fiable
- ❌ No calcula zonas por potencia (solo HR)
- ❌ No genera la capa analítica de terreno `FP-02` (`terrain_context`, `terrain_fit_context`, `terrain_intervals.csv`, `terrain_climbs.csv`); esa capa vive solo en `analysis/` y no modifica este schema

---

## 1. Arquitectura

| Archivo | Granularidad | Para qué sirve |
|---------|-------------|-----------------|
| `sessions.csv` | 1 fila por sesión | Detalle completo de cada entrenamiento: zonas, work blocks, drift, clasificación y minutos primarios por zona (`z1/z2/z3_total_min`). Lo que miras cuando quieres entender una sesión concreta. |
| `sessions_day.csv` | 1 fila por día | Agregados diarios + rolling 3d/7d/14d/28d con cobertura, más la capa canónica de contexto de carga (`ACWR`, `monotony`, `strain`), una señal corta de clustering reciente de intensidad y la señal rolling `DO-02` de polarización por familia con resumen de episodio. Lo que lee `build_hrv_final_dashboard.py` para generar avisos de carga en reason_text. |
| `ENDURANCE_HRV_intensity_distribution_weekly.csv` | 1 fila por semana y deporte | Resumen canónico `sport x week` de distribución observada de intensidad: minutos ponderados por zona, `work_*`, patrón descriptivo (`polarized`, `pyramidal`, `threshold`, `mixed`) y confianza explícita. Pensado para análisis semanal y comparativa intra-deporte; no alimenta el gate. |
| `ENDURANCE_HRV_weekly_coach.json` | 1 por corrida | Sidecar semanal estructurado: `iso_week`, ventana, marcas de corte (`as_of_date`, `generated_at`, `anchor_source`), cobertura (`week_expected_days`, `week_data_coverage_pct`), tipo semanal, carga, riesgo de progresión, tendencia HRV y calidad de datos. No alimenta el gate. |
| `ENDURANCE_HRV_sessions_metadata.json` | 1 por corrida | Trazabilidad: versión del pipeline, parámetros usados, hash de configuración, sampling rate del stream y una auditoría ligera por capas (`dataset/signal/metric`) para coaching y carga. |
| `ENDURANCE_HRV_wellness_subjective.csv` | 1 fila por día | Wellness subjetivo diario desde Intervals (`fatigue`, `stress`, `mood`, `motivation`, `soreness`, `injury`, comentario), con labels y cobertura 7d para análisis retrospectivo o capas separadas. |

### Fuente de datos

El pipeline consume la API de Intervals.icu:
- `/api/v1/athlete/{id}/activities` — lista de actividades con metadatos (load, duration, type, RPE...)
- `/api/v1/activity/{id}/streams` — stream de HR y velocidad segundo a segundo
- `/api/v1/athlete/{id}/wellness` — wellness diario subjetivo y campos de recuperación

De forma **opcional y no bloqueante**, el pipeline puede enriquecer sesiones de `road_run`, `trail_run` y `hike` con muestras mecánicas. La prioridad actual es:
- `FIT` descargado desde Intervals (`/activity/{id}/fit-file`)
- Polar AccessLink como fallback cuando el FIT no está disponible o no trae señal útil

Como fallback secundario, el pipeline puede enriquecer con muestras mecánicas de Polar AccessLink:
- `GET /v3/exercises`
- `GET /v3/exercises/{id}?samples=true`

El stream HR de Intervals es idéntico al TCX del sensor (verificado empíricamente: 4844 vs 4843 puntos, Δ=0). No se necesita descargar TCX.

**Sampling rate:** Intervals re-muestrea todos los streams a 1 Hz. El pipeline verifica esto con `stream_dt_est` (canary). Si alguna sesión se desvía significativamente de 1.0, las conversiones de muestras a minutos serían incorrectas.

### Relación con `analysis/`

El pipeline de sesiones y el módulo `analysis/` se conectan, pero no comparten contrato de salida:

- `build_sessions.py` sigue siendo la fuente canónica de `sessions.csv`, `sessions_day.csv`, `ENDURANCE_HRV_weekly_coach.json`, `ENDURANCE_HRV_sessions_metadata.json` y sidecars operativos.
- `analysis/` puede reutilizar:
  - `run_power_*`
  - `speed_first_half/second_half`
  - `cadence_first_half/second_half`
  - `training_audit`
- `analysis/` puede además construir artefactos locales de terreno (`FP-02`) a partir de Intervals/FIT:
  - `terrain_context`
  - `terrain_fit_context`
  - `terrain_intervals.csv`
  - `terrain_climbs.csv`
- Esos artefactos no forman parte del contrato de `build_sessions.py` y no deben documentarse como columnas de `sessions.csv`.

---

## 2. SESSIONS.CSV — columnas y significado

73 columnas organizadas en bloques funcionales. Cada bloque agrupa campos relacionados.

### Bloque A — Identidad

Quién eres, cuándo entrenaste, y qué zonas se usaron para clasificar el esfuerzo.

| Campo | Tipo | Qué es | Ejemplo |
|-------|------|--------|---------|
| `session_id` | string | Identificador único de la actividad en Intervals.icu. Empieza con "i" seguido de un número. Sirve para rastrear cualquier sesión hasta su fuente original. | i127783816 |
| `route_id` | int? | Identificador de la ruta de Intervals.icu cuando la actividad viene asociada a un recorrido repetible. Permite comparar la sesión con la última vez que se hizo el mismo route_id, sin inventar comparadores por parecido visual. | 42 |
| `Fecha` | date | Día en que se realizó la sesión (YYYY-MM-DD). Si entrenas dos veces un día, habrá dos filas con la misma Fecha pero distinto session_id. | 2026-02-25 |
| `start_time` | HH:MM | Hora de inicio de la sesión. Útil para distinguir sesiones dobles y para análisis de distribución horaria del entrenamiento. | 15:16 |
| `sport` | enum | Tipo de deporte normalizado (minúsculas, guiones bajos). El pipeline lo usa para asignar umbrales de zonas, decidir si hay velocidad disponible, y clasificar la sesión. | trail_run, bike, strength, swim |
| `sport_raw` | string | Tipo de deporte tal como viene de Intervals.icu, sin normalizar. Lo conservamos por trazabilidad: si algún día cambia la normalización, puedes volver al original. | TrailRun, VirtualRide |
| `source` | const | Siempre "intervals". Reservado por si en el futuro se integran otras fuentes (Garmin directo, Polar Flow, etc.). | intervals |
| `vt1_used` | int lpm | Umbral ventilatorio 1 (primer umbral) usado para esta sesión. Es el límite entre Z1 y Z2. Todo lo que está por debajo es aeróbico cómodo; por encima, empieza el "trabajo". | 143 |
| `vt2_used` | int lpm | Umbral ventilatorio 2 (segundo umbral) usado para esta sesión. Es el límite entre Z2 y Z3. Por encima de VT2 estás en zona de alta intensidad, acumulando fatiga rápidamente. | 161 |
| `zones_source` | enum | De dónde salieron los umbrales VT1/VT2 para esta sesión. **"icu"** = de las zonas HR configuradas en Intervals.icu para ese deporte (lo ideal). **"fallback"** = umbrales genéricos por deporte porque Intervals no tenía zonas configuradas. | icu / fallback |

**Sobre VT1/VT2:** Estos no son "zonas de Polar" ni "zonas de Garmin". Son TUS umbrales ventilatorios reales (o la mejor aproximación que tengas), configurados en Intervals.icu por deporte. Si cambias tus zonas en Intervals, el pipeline los recoge automáticamente. Si no están configurados, usa fallbacks conservadores.

### Bloque B — Duración y distancia

Lo básico de la sesión: cuánto duró, cuánto te moviste, cuánto subiste.

| Campo | Tipo | Qué es | Rango típico |
|-------|------|--------|-------------|
| `duration_min` | float | Duración total de la sesión en minutos, incluyendo pausas, paradas, y tiempo estacionario. Es el "cronómetro completo" desde que pulsas start hasta stop. | 30-120 |
| `moving_min` | float | Minutos en los que realmente te estabas moviendo (velocidad > 0.3 m/s). Es la duración "útil" — descuenta semáforos, paradas para beber, atar zapatillas, etc. **Las zonas y los work blocks se calculan solo sobre estos minutos.** | 25-100 |
| `distance_km` | float | Distancia total recorrida en kilómetros. Para fuerza/movilidad puede ser 0 o muy bajo. | 5-25 |
| `elev_gain_m` | float? | Metros de desnivel positivo acumulado (subida total). NaN en indoor y natación. | 100-1500 |
| `elev_loss_m` | float? | Metros de desnivel negativo acumulado (bajada total). NaN en indoor y natación. | 100-1500 |
| `elev_density` | float? | Metros de desnivel ganados por kilómetro recorrido (`elev_gain / distance`). Captura la "verticalidad" de la ruta: 20 m/km = plano, 60 m/km = montañoso, 100+ m/km = vertical puro. NaN si la distancia es menor a 0.5 km (para evitar divisiones ruidosas). | 20-120 |
| `calories` | int? | Gasto energético estimado por Intervals para la sesión. Es una señal descriptiva de coste metabólico; no alimenta ningún gate ni rolling actual. En el CSV puede verse como `372.0` por coerción numérica de pandas, aunque su semántica siga siendo entera. | 200-1500 |

**¿Por qué `moving_min` y no `duration_min`?** Porque una sesión de trail de 90 minutos con 15 minutos de pausas en fuentes y fotos tiene 75 minutos de trabajo real. Si calculas zonas sobre los 90, diluyes la intensidad con tiempo donde tu corazón estaba bajando en una parada. La moving mask (`vel > 0.3 m/s`) asegura que solo contamos los momentos donde realmente estabas esforzándote.

### Bloque C — Coste cardíaco global

Cómo respondió tu corazón durante el movimiento: frecuencia media, pico, y distribución por zonas.

| Campo | Tipo | Qué es | Rango típico |
|-------|------|--------|-------------|
| `hr_mean` | int lpm | Frecuencia cardíaca media de toda la sesión (con y sin movimiento). Viene directamente de Intervals.icu, no se recalcula. | 110-160 |
| `hr_max` | int lpm | Frecuencia cardíaca máxima registrada durante la sesión. Puede incluir picos de artefacto si el sensor tuvo problemas, pero Intervals ya filtra los más groseros. | 150-185 |
| `hr_p95` | float lpm | Percentil 95 de la FC **solo durante movimiento** (moving mask). Más robusto que hr_max porque ignora picos aislados de 1-2 segundos. Útil para saber "cuál fue tu intensidad máxima sostenible" en esa sesión. | 145-175 |
| `average_cadence` | float? | Cadencia media reportada por Intervals para la sesión cuando hay sensor o stream válido. Se conserva como primitiva transversal de sesión; no sustituye a `cadence_first_half/second_half`, que siguen siendo una capa mecánica separada. **La semántica depende del deporte**: en run/trail suele reflejar pasos por minuto, en bike pedaladas por minuto y en swim frecuencia de brazada. | 70-100 |
| `hrr_drop_bpm` | int? | Caída de FC en el primer minuto post-esfuerzo, extraída de `icu_hrr.hrr` cuando Intervals la expone en el listado de actividades. Es una señal parasimpática intra-sesión; queda vacía si no hubo pico recuperable. | 10-60 |
| `average_weather_temp` | float? | Temperatura ambiente media modelada por Intervals cuando `has_weather=true`. Sirve como contexto explicativo para FC anómalamente alta, deriva o coste percibido. | 0-35 |
| `z1_pct` | float % | Porcentaje del tiempo **en movimiento** que tu corazón estuvo en Z1 (≤VT1). Es tu zona aeróbica cómoda: puedes hablar, el esfuerzo es sostenible indefinidamente. En una sesión "easy" bien ejecutada, debería ser >80%. | 40-95 |
| `z2_pct` | float % | Porcentaje del tiempo en movimiento en Z2 (VT1 < HR ≤ VT2). Es tu zona "tempo": puedes hablar con frases cortas, el esfuerzo es mantenible 30-60 minutos. En subidas largas de trail, es donde pasas la mayor parte. | 5-50 |
| `z3_pct` | float % | Porcentaje del tiempo en movimiento en Z3 (> VT2). Zona de alta intensidad: no puedes hablar, acumulas fatiga rápidamente, la recuperación tarda. Incluso en sesiones duras, suele ser <15% del total — los intervalos de Z3 son cortos dentro de una sesión larga. | 0-15 |
| `z1_total_min` | float | Minutos totales en Z1. Completa la triada primaria de tiempo por zona y permite agregar semanas por deporte con ponderación correcta sin depender de medias de porcentajes por sesión. | 20-300 |
| `z2_total_min` | float | Minutos totales en Z2 (sin redondeo de porcentaje). Útil para contabilizar volumen de trabajo moderado. | 5-40 |
| `z3_total_min` | float | Minutos totales en Z3. **Este es el campo que alimenta `z3_7d_sum` en sessions_day** y que genera el aviso "Tiempo en alta intensidad acumulado esta semana (Xmin en Z3)" en `reason_text`. Incluso unos pocos minutos de Z3 tienen impacto real en la fatiga. | 0-15 |

**z1 + z2 + z3 = 100%** (siempre, verificado por QA). Esto es posible porque se calculan sobre el mismo universo de muestras (moving mask activa). Si sumas y no da 100%, hay un bug.

**¿Por qué zonas por HR y no por potencia?** Porque este pipeline se integra con el gate HRV, que opera sobre señal cardíaca. Las zonas HR son coherentes con todo el sistema. Para análisis por potencia, Intervals.icu ya tiene herramientas excelentes.

### Bloque D — Bloques de trabajo

**La pieza central del pipeline.** Los porcentajes de zona (Bloque C) te dicen "qué proporción del tiempo pasaste en cada zona". Pero no te dicen si ese Z2 fue un bloque continuo de 30 minutos de subida, o si fueron 60 picos de 30 segundos dispersos en una sesión de stop-and-go. Los bloques de trabajo capturan la **estructura** del esfuerzo.

Un "bloque de trabajo" es un periodo continuo donde tu corazón estuvo por encima de VT1 (es decir, en Z2 o Z3) durante al menos 3 minutos, con gaps ≤60s y caídas de HR ≤10 lpm entre tramos. Es la forma que tiene el pipeline de distinguir "esfuerzo sostenido" de "picos breves entre pausas".

#### Agregados (lo que miras para evaluar la sesión):

| Campo | Tipo | Qué es | Ejemplo |
|-------|------|--------|---------|
| `work_n_blocks` | int | Cuántos bloques de trabajo sostenido tuvo la sesión. Una sesión easy = 0 bloques. Trail con 4 subidas = 4 bloques. Intervalos en pista = tantos bloques como series (si cada serie dura >3 min) o un solo bloque si la recuperación es corta. | 4 |
| `work_total_min` | float | Minutos totales de trabajo sostenido (suma de todos los bloques). **Esta es la métrica que usa `classify_intensity` para decidir si la sesión fue "work_intense", "work_steady", etc.** Es distinta de z2+z3 minutes porque solo cuenta bloques ≥3min. | 43.4 |
| `work_longest_min` | float | Duración del bloque más largo. Distingue entre una sesión con muchos bloques cortos (intervalos) y una con una subida continua larga. | 11.8 |
| `work_avg_z3_pct` | int % | Porcentaje medio de Z3 **dentro de los bloques de trabajo**. Si es >15%, los bloques incluyen esfuerzo de alta intensidad (no solo tempo). Si es <15%, el trabajo fue predominantemente Z2 (tempo sostenido). **Esta es la segunda métrica que usa `classify_intensity`.** | 35 |

#### Detalle forense (para analizar la estructura bloque a bloque):

| Campo | Tipo | Qué es | Ejemplo |
|-------|------|--------|---------|
| `work_blocks_min` | string (;) | Duración de cada bloque de trabajo, separados por `;`. Permite reconstruir la sesión: "subida 1 de 11.8 min, subida 2 de 10.4 min, etc.". | 11.8;10.4;9.4;11.8 |
| `work_blocks_z3pct` | string (;) | Porcentaje de Z3 dentro de cada bloque, mismo orden que `work_blocks_min`. Permite identificar cuál de las subidas fue la más intensa. | 17;75;39;14 |

**Algoritmo de merge:** Dos tramos consecutivos de HR≥VT1 se fusionan en un solo bloque si el gap entre ellos cumple AMBAS condiciones: gap ≤ 60 segundos **Y** la caída de HR durante el gap ≤ 10 lpm. Esto evita fragmentar una subida continua donde bajaste 5 segundos para cruzar un río, pero mantiene separados dos intervalos con 2 minutos de recuperación entre ellos.

**Ejemplo práctico:** Un trail de 80 minutos con 4 subidas largas separadas por bajadas. Cada subida es un bloque (11-12 min), con Z3 variable según la pendiente. `work_total_min = 43.4` = casi la mitad de la sesión fue esfuerzo sostenido por encima de VT1.

### Bloque E — Indicadores de fatiga intra-sesión

¿Cómo fue evolucionando tu esfuerzo a lo largo de la sesión? Si terminaste con el corazón más alto que al principio a la misma velocidad, es drift cardíaco — señal de fatiga o deshidratación.

| Campo | Tipo | Qué es | Valores típicos |
|-------|------|--------|----------------|
| `late_intensity` | 0 o 1 | ¿La segunda mitad de la sesión fue significativamente más intensa que la primera? Se calcula comparando la HR media de la 1ª mitad vs la 2ª mitad (solo muestras con movimiento). Si la 2ª mitad supera a la 1ª en ≥8 lpm → 1 (sí). Solo se calcula en sesiones de ≥40 minutos de movimiento; en sesiones cortas → 0. **Diseño "mitades":** deliberadamente simple y robusto. No detecta sprints finales de 5 minutos, sino cambios sostenidos de intensidad. | 0 (mayoría) o 1 |
| `cardiac_drift_pct` | float? | Porcentaje de aumento de HR por unidad de velocidad a lo largo de la sesión. Si corres a la misma velocidad pero tu HR va subiendo, hay drift. Valores >5% sugieren fatiga, calor, o deshidratación. Solo se calcula en sesiones de ≥30 minutos con datos de velocidad; NaN si no hay velocidad (indoor) o sesión corta. HR y velocidad se alinean a la misma longitud para evitar errores de desfase. | 0-15% (normal: 3-7%) |

**¿Por qué "mitades" y no "últimos 20 minutos"?** El diseño por mitades es más robusto para sesiones de distinta duración: en una sesión de 45 min, "últimos 20 min" es casi la mitad; en una de 120 min, es solo el último sexto. Las mitades se adaptan automáticamente a la duración.

### Capa opcional — Señal mecánica (16 campos)

Cuando existe señal utilizable, `sessions.csv` añade una capa mecánica mínima para deportes de pie (`road_run`, `trail_run`, `hike`). La prioridad es `Intervals FIT` y el fallback es `Polar AccessLink`. Si ninguna fuente está disponible, las columnas quedan vacías o en `0` y el pipeline sigue funcionando igual.

| Campo | Tipo | Qué es |
|-------|------|--------|
| `mechanics_source` | enum | `intervals_fit` si la señal salió del FIT de Intervals, `polar` si salió de AccessLink; vacío en caso contrario. |
| `polar_sport_raw` | string | Deporte crudo de la fuente mecánica usada. Si la fuente fue Polar, suele venir como `RUNNING`, `TRAIL_RUNNING`, `HIKING`, `TREADMILL_RUNNING`; si la fuente fue `Intervals FIT`, conserva el `sport/sub_sport` del FIT. |
| `polar_start_delta_min` | float? | Diferencia absoluta en minutos entre la sesión de Intervals y el ejercicio de Polar usado para el match. Solo aplica cuando `mechanics_source = polar`; en `intervals_fit` queda vacío. |
| `polar_duration_gap_min` | float? | Diferencia absoluta en minutos entre `duration_min` y la duración declarada por Polar. Solo aplica cuando `mechanics_source = polar`; en `intervals_fit` queda vacío. |
| `run_power_available` | 0/1 | 1 solo si la fuente mecánica tiene cobertura útil de potencia y valores >0; evita tratar un stream todo a cero como potencia real. |
| `run_power_mean` | float? | Potencia media útil en vatios de la fuente mecánica seleccionada. |
| `run_power_max` | float? | Potencia máxima útil en vatios de la fuente mecánica seleccionada. |
| `run_power_p95` | float? | Percentil 95 de potencia útil en vatios de la fuente mecánica seleccionada. |
| `run_power_first_half` | float? | Potencia media de la primera mitad útil en vatios. Solo presente cuando `run_power_available=1`. |
| `run_power_second_half` | float? | Potencia media de la segunda mitad útil en vatios. Solo presente cuando `run_power_available=1`. |
| `speed_first_half` | float? | Velocidad media de la primera mitad útil de la sesión, en km/h, usando la fuente mecánica seleccionada. |
| `speed_second_half` | float? | Velocidad media de la segunda mitad útil de la sesión, en km/h, usando la fuente mecánica seleccionada. |
| `cadence_first_half` | float? | Cadencia media de la primera mitad útil usando la fuente mecánica seleccionada. |
| `cadence_second_half` | float? | Cadencia media de la segunda mitad útil usando la fuente mecánica seleccionada. |
| `polar_speed_available` | 0/1 | 1 si la fuente mecánica tiene cobertura útil de velocidad. |
| `polar_cadence_available` | 0/1 | 1 si la fuente mecánica tiene cobertura útil de cadencia. |

**Límites de la v1:** esta capa no introduce GAP, zonas por potencia ni métricas derivadas nuevas. Su objetivo es canonizar una base mecánica mínima para futuras tareas (`AP-01`, `FP-01`, etc.) sin romper compatibilidad.

**Relación con `FP-02`:** la capa mecánica mínima sí puede ser reutilizada por `analysis/` para enriquecer terreno, pero `build_sessions.py` no persiste `GAP`, `VAM`, `terrain_context` ni artefactos por split/climb dentro de `sessions.csv`.

**Semántica temporal (FP-01):** `speed_first_half`, `speed_second_half`, `cadence_first_half`, `cadence_second_half`, `run_power_first_half` y `run_power_second_half` se calculan sobre **tiempo en movimiento**: primero se filtran las muestras válidas (velocidad > umbral mínimo, cadencia > 0, potencia > 0) y luego se parte el array resultante por su mitad. Las pausas no computan ni desplazan el punto de corte. Esto es relevante en `hike`, donde el tiempo de pausa puede superar el 30% del tiempo total. El sampling rate es 1 Hz en todas las sesiones conocidas, por lo que la frontera equivale exactamente a la mitad del tiempo en movimiento.

**Cobertura Polar:** cuando `mechanics_source = polar`, la cobertura depende de la ventana reciente realmente expuesta por Polar AccessLink en `/v3/exercises`. No debe asumirse como fuente de backfill histórico completo.

### Capa derivada — Durabilidad mecánica (3 campos)

Señales derivadas de FP-01 para detectar fatiga periférica en sesiones largas de deportes de pie. Solo se calculan en `build_sessions.py` como post-proceso; no dependen de ninguna fuente externa adicional.

| Campo | Tipo | Qué es |
|-------|------|--------|
| `durability_applicable` | 0/1 | 1 si la sesión cumple los criterios mínimos para calcular una lectura clásica de durabilidad: `sport` en `{road_run, trail_run, hike}`, `work_n_blocks <= 2`, `speed_first_half` disponible y duración mínima dependiente de deporte/señal. Reglas v1 run-aware: `road_run >= 60 min` con potencia útil o `>= 75 min` sin ella; `trail_run >= 75 min` con potencia útil o `>= 90 min` sin ella; `hike >= 90 min`. Las sesiones de intervalos o demasiado cortas quedan en 0. |
| `speed_ratio` | float? | `speed_second_half / speed_first_half`. Ratio de velocidad entre segunda y primera mitad. Valores <1 indican caída de velocidad; por debajo de ~0.93 y con `cardiac_drift_pct > 5` la combinación sugiere fatiga mecánica periférica. En `hike`, ratio > 1.10 con elevación alta es ambiguo (posible descenso en segunda mitad). |
| `power_ratio` | float? | `run_power_second_half / run_power_first_half`. **NaN cuando `run_power_available=0`**, incluso si las mitades existen en el CSV. La gate es explícita en el pipeline: el cálculo usa `run_power_available` como condición necesaria, no se infiere de la presencia de los valores. Señal preferida sobre `speed_ratio` cuando está disponible: la potencia es output directo del motor muscular, independiente de la variabilidad de terreno. |

**Nota de interpretación:** `power_ratio` es la señal preferida cuando está disponible. `speed_ratio` es el fallback. Ambas pueden coexistir en la misma sesión. Para `hike`, `speed_ratio < 0.90` con `cardiac_drift_pct > 5` es la combinación más fiable; el ratio positivo alto es menos interpretable sin conocer el perfil de elevación.

**Thresholds candidatos (backtesting FP-01, N=30, 2025-05 a 2026-04):**
- Fatiga mecánica: `speed_ratio < 0.93` AND `cardiac_drift_pct > 5` → 1 caso claro (hike 0.773/+31.7). Sin falsos positivos con este criterio dual.
- Decoupling cardíaco sin caída mecánica: `cardiac_drift_pct > 10` AND `speed_ratio >= 0.93` → 3 sesiones (patrón diferente: el corazón trabaja más pero la velocidad aguanta).
- N insuficiente para producción: solo 1 caso positivo inequívoco. Revisión prevista a N≥50 sesiones aplicables.
- Las constantes están en `build_sessions.py` (`_DURABILITY_SPEED_RATIO_THRESHOLD`, `_DURABILITY_DRIFT_THRESHOLD`) para ajuste sin cambio de lógica.

**Alcance FP-01:** estas columnas son solo de `sessions.csv`. No alimentan `reason_text`, `FINAL` ni ningún gate HRV hasta que los thresholds se validen con N≥50.

### Bloque F — Carga, percepción y métricas coach de sesión

Cómo se clasifica la sesión y cómo se compara con tu histórico.

| Campo | Tipo | Qué es |
|-------|------|--------|
| `load` | int | Carga de entrenamiento asignada por Intervals.icu (su modelo HRSS/TSS). No lo calcula este pipeline — viene tal cual de la fuente. Es el valor que alimenta `load_day` y, por arrastre, `load_3d` y `acute_load_72h_rel` en sessions_day.csv. |
| `trimp` | float? | Carga TRIMP tipo Banister calculada por Intervals a partir de duración e intensidad cardíaca. Es una segunda señal fisiológica de carga, complementaria a `load` y separada de la percepción subjetiva. |
| `rpe` | int? (1-10) | Rate of Perceived Exertion. Percepción subjetiva del esfuerzo que tú registraste después de entrenar. 1=muy fácil, 10=máximo. NaN si no lo registraste. El pipeline lo conserva pero no lo usa para clasificar — es informativo. |
| `feel` | int? | Cómo te sentiste durante la sesión (escala Intervals). NaN si no lo registraste. Informativo. |
| `icu_weighted_avg_watts` | float? | Potencia ponderada / normalizada reportada por Intervals cuando `device_watts=true`. Es una primitiva coach útil de sesión, pero no introduce zonas por potencia ni cambia ninguna clasificación base. |
| `icu_joules_above_ftp` | float? | Trabajo acumulado por encima de FTP, en julios, cuando hay potencia válida. Sirve como lectura de coste anaeróbico puntual. |
| `icu_max_wbal_depletion` | float? | Máximo vaciado de W' reportado por Intervals cuando hay potencia válida. Es una señal de coste pico; queda vacía sin potenciómetro. |
| `decoupling` | float? | Deriva HR/potencia calculada por Intervals cuando `device_watts=true`. **No es equivalente** a `cardiac_drift_pct` (HR/velocidad); ambas se deben interpretar como señales complementarias. Su escala tampoco es directamente comparable entre deportes: trail con desnivel, cambios de terreno y pacing variable puede mostrar valores estructuralmente más altos que road o bike. |
| `intensity_category` | enum | **Clasificación de la estructura de trabajo de la sesión.** Ver §3 para la taxonomía completa. Es la respuesta a "¿qué tipo de sesión fue?" basada en los work blocks, no en el porcentaje bruto de zonas. |
| `effort_vs_recent` | enum | ¿Esta sesión fue más dura, normal, o más fácil que tus últimas 60 sesiones del mismo `session_group`? Se calcula con P25/P75 de `load` **solo sobre sesiones anteriores** (sin look-ahead), para mantener la causalidad. Valores: "above" / "typical" / "below". |
| `effort_vs_anchor` | enum | ¿Esta sesión fue más dura que cuando estabas en tu mejor forma? Compara `load` contra percentiles fijos de un periodo de referencia sano (jun-ago 2025, configurable), siempre dentro del mismo `session_group`. Detecta desentrenamiento sostenido: si tu "typical" actual está por debajo del "typical" de tu mejor periodo, algo ha cambiado. Valores: "above" / "typical" / "below". |
| `session_group` | enum | Grupo funcional de la sesión para separar estadísticas. Ver §4 para valores. |

### Bloque G — QA y trazabilidad

Campos técnicos para depuración y auditoría. No los necesitas para el uso diario.

| Campo | Tipo | Qué es |
|-------|------|--------|
| `notes_raw` | string? | Notas que dejaste en Intervals.icu para esa sesión. Los saltos de línea se convierten a `\|` para que no rompan el CSV. NaN si no dejaste notas. |
| `rpe_present` | 0/1 | 1 si registraste RPE, 0 si no. Permite calcular "% de sesiones con RPE" como métrica de adherencia. |
| `notes_present` | 0/1 | 1 si dejaste notas, 0 si no. Mismo propósito. |
| `stream_dt_est` | float? | Intervalo medio entre muestras del stream de HR, estimado como `elapsed_time / len(stream)`. Si el stream es 1 Hz, este valor debería ser ~1.000. Si se desvía mucho (ej: 0.5 o 2.0), significa que Intervals re-muestreó a otra frecuencia y todas las conversiones de "muestras → minutos" serán incorrectas. **Canary**: si ves un valor ≠1.0, investiga antes de confiar en las métricas de esa sesión. NaN si la sesión no tiene stream. |
| `pipeline_version` | string | Versión del pipeline que generó esta fila. Para auditar si una sesión fue procesada con una versión anterior (y si necesita reprocesarse). |

---

## 3. Enumeraciones

### intensity_category — taxonomía de estructura de trabajo

**Principio fundamental:** Esta clasificación mira la ESTRUCTURA del trabajo (bloques sostenidos por encima de VT1), NO la exposición bruta a Z3. ¿Por qué? Porque 5 minutos de Z3 repartidos en 50 picos de 6 segundos (stop-and-go urbano) no tienen el mismo impacto fisiológico que 5 minutos de Z3 dentro de un bloque continuo de 20 minutos de subida.

Para exposición Z3 acumulada (que sí tiene impacto independiente de la estructura), usar `z3_total_min` en la sesión y `z3_7d_sum` en sessions_day.

| Valor | Condición | Qué significa en la práctica |
|-------|-----------|------------------------------|
| `work_intense` | work_total ≥ 10min AND work_avg_z3% ≥ 15 | Sesión con trabajo duro sostenido: intervalos largos, subidas a ritmo, tempo con tramos al límite. Los bloques de trabajo no solo son largos, sino que incluyen una proporción significativa por encima de VT2. **Impacto alto en fatiga.** |
| `work_steady` | work_total ≥ 20min AND work_avg_z3% < 15 | Sesión con trabajo sostenido predominantemente en Z2: tempo largo, subida constante a ritmo moderado. El esfuerzo es real pero no llega a alta intensidad. Típica sesión de "base aeróbica con carga". **Impacto moderado-alto en fatiga.** |
| `work_moderate` | work_total ≥ 5min (no cumple los anteriores) | Algo de trabajo por encima de VT1, pero poco: unas cuestas, un tramo a ritmo, una subida breve. No lo suficiente para llamarlo "steady" ni "intense". **Impacto moderado.** |
| `finish_strong` | late_intensity=1 sin bloques relevantes | La sesión terminó significativamente más intensa que como empezó, pero sin bloques de trabajo formales. Patrón típico: empezar suave y apretar en la segunda mitad sin llegar a un esfuerzo sostenido largo. **Impacto variable.** |
| `easy` | Resto de sesiones aeróbicas | Todo el esfuerzo estuvo en Z1 (o Z2 tan breve que no formó bloques de ≥3 min). Sesión regenerativa, paseo activo, rodaje fácil. **Impacto bajo en fatiga.** |
| `NA` | Fuerza, movilidad, other | La sesión no es aeróbica y el análisis de zonas/work blocks no aplica. La carga se contabiliza (load existe), pero las métricas de zonas no tienen sentido. |

### effort_vs_recent — esfuerzo relativo al historial reciente

Compara el `load` de esta sesión contra el P25 y P75 de las últimas 60 sesiones del mismo `session_group`. **Crucial: sin look-ahead** — solo usa sesiones anteriores para calcular los percentiles, nunca futuras. Esto mantiene la causalidad: el effort de una sesión de enero se evalúa contra lo que habías hecho hasta enero, no contra lo que harás en marzo.

| Valor | Significado |
|-------|-------------|
| `above` | Load por encima del P75 de tu historial reciente para ese tipo de sesión. Sesión inusualmente dura para ti. |
| `typical` | Load entre P25 y P75. Normal para ti. |
| `below` | Load por debajo del P25. Sesión más suave de lo habitual. |

### effort_vs_anchor — esfuerzo relativo a tu mejor periodo

Misma lógica que effort_vs_recent, pero los percentiles se calculan sobre un periodo de referencia fijo: tu "mejor momento" conocido (configurable, por defecto jun-ago 2025), siempre dentro del mismo `session_group`. No cambian con el tiempo.

**¿Para qué sirve?** Si tu effort_vs_recent dice "typical" pero tu effort_vs_anchor dice "below", significa que tu nivel actual de esfuerzo se ha normalizado a la baja sin que te des cuenta. Detecta desentrenamiento progresivo: lo que hoy te parece normal era "below" en tu mejor momento.

### session_group — agrupación funcional

| Valor | Qué incluye |
|-------|-------------|
| `endurance_hard` | Sesiones aeróbicas clasificadas como work_intense |
| `endurance_moderate` | work_steady o work_moderate |
| `endurance_easy` | easy o finish_strong |
| `strength_unknown` | Sesiones de fuerza (la carga se cuenta, pero no se analiza HR) |
| `mobility` | Movilidad, yoga, stretching |

El session_group se usa para separar las estadísticas de effort_vs_recent: no tiene sentido comparar el load de una sesión de fuerza contra tus trails, ni tu paseo regenerativo contra tus intervalos.

---

## 4. SESSIONS_DAY.CSV — agregados diarios y rolling

Sessions_day.csv tiene una fila por día-calendario (no por sesión). Si un día no entrenaste, no aparece. Si entrenaste dos veces, se agregan en una sola fila. **Este es el archivo que lee `build_hrv_final_dashboard.py` para generar avisos de carga en reason_text.**

### Campos del día (agregados directos)

| Campo | Tipo | Qué es |
|-------|------|--------|
| `Fecha` | date | Día-calendario (YYYY-MM-DD). Clave primaria. |
| `n_sessions` | int | Número de sesiones registradas ese día. |
| `total_duration_min` | float | Suma de `duration_min` de todas las sesiones del día. Es duración bruta total, útil como contexto descriptivo. |
| `has_aerobic` | 0/1 | 1 si el día incluye al menos una sesión aeróbica. |
| `has_strength` | 0/1 | 1 si el día incluye al menos una sesión de fuerza. |
| `has_mobility` | 0/1 | 1 si el día incluye al menos una sesión de movilidad. |
| `load_day` | float | Suma de `load` de todas las sesiones del día. Es tu carga total diaria. |
| `intensity_cat_day` | string | Categoría de intensidad de la sesión principal del día. La sesión principal se define por `load` más alto; si falta `load`, desempata por `duration_min`. |
| `intense_day` | 0/1 | 1 si ese día hubo al menos una sesión con `intensity_category = work_intense`; 0 en caso contrario. Es la semilla binaria de la capa de clustering corto de intensidad. |
| `work_total_min_day` | float | Suma de `work_total_min` de las sesiones aeróbicas del día. Minutos de trabajo sostenido ≥VT1. Viene de los agregados de sesión, no de parsear strings (fix v3.1). **NaN si ese día no hubo ninguna sesión aeróbica.** |
| `work_n_blocks_day` | int | Suma de `work_n_blocks` de las sesiones aeróbicas. **NaN si ese día no hubo ninguna sesión aeróbica.** |
| `z3_min_day` | float | Suma de `z3_total_min` de las sesiones aeróbicas. Minutos totales de Z3 del día. **NaN si ese día no hubo ninguna sesión aeróbica.** |
| `hr_max_day` | int? | Pico de FC más alto observado entre las sesiones aeróbicas del día. |
| `hr_p95_max_day` | float? | Mayor `hr_p95` observado entre las sesiones aeróbicas del día. |
| `late_intensity_day` | 0/1? | 1 si alguna sesión aeróbica terminó claramente más intensa; 0 si hubo sesión aeróbica pero no ocurrió; NaN si no hubo sesión aeróbica. |
| `cardiac_drift_worst` | float? | Peor drift cardíaco del día entre sesiones aeróbicas con datos válidos. |
| `elev_gain_day` | float? | Suma de desnivel positivo del día. |
| `elev_loss_day` | float? | Suma de desnivel negativo del día. |
| `strength_min_day` | float | Duración total de sesiones de fuerza del día. |
| `mobility_min_day` | float | Duración total de sesiones de movilidad del día. |
| `rpe_max_day` | int? | RPE máximo registrado entre las sesiones aeróbicas del día. |
| `effort_above_typical_aerobic` | 0/1 | ¿Alguna sesión aeróbica del día tuvo effort_vs_recent = "above"? |
| `effort_above_typical_strength` | 0/1 | ¿Alguna sesión de fuerza del día tuvo effort_vs_recent = "above"? |
| `effort_above_anchor_aerobic` | 0/1 | ¿Alguna sesión aeróbica del día tuvo effort_vs_anchor = "above"? |
| `n_with_rpe` | int | Número de sesiones del día con RPE informado. |
| `n_with_notes` | int | Número de sesiones del día con notas. |
| `elev_density_day` | float? | Densidad vertical media ponderada por distancia de las sesiones aeróbicas del día. |

### Campos rolling (ventana deslizante con cobertura)

Los campos rolling son sumas o medias de los últimos N días, con un campo `_nobs` que indica cuántos días de la ventana tenían datos reales.

| Campo | Ventana | Qué es |
|-------|---------|--------|
| `load_3d` / `load_3d_nobs` | 3 días | Carga total de los 3 días anteriores (d-1 + d-2 + d-3, NO incluye hoy). Con cobertura. |
| `intense_days_prev_3d` | 3 días | Conteo de `intense_day` en los 3 días previos sobre calendario continuo (los días sin sesión cuentan como 0). |
| `intense_days_prev_5d` | 5 días | Conteo de `intense_day` en los 5 días previos sobre calendario continuo. |
| `intensity_clustering_flag` | 0/1 | Flag proactivo simple: 1 si `intense_days_prev_5d >= 2`, 0 si no. No toca el gate; solo alimenta contexto. |
| `intensity_clustering_level` | enum | Severidad de clustering. `high` si `intense_days_prev_3d >= 2` o `intense_days_prev_5d >= 3`; `low` si no llega a high pero sí activa flag; vacío en ausencia de flag. |
| `load_7d` / `load_7d_nobs` | 7 días | Carga total de los 7 días anteriores. Con cobertura. |
| `work_7d_sum` / `work_7d_nobs` | 7 días | Minutos totales de trabajo sostenido ≥VT1 en los 7 días previos. |
| `z3_7d_sum` / `z3_7d_nobs` | 7 días | **Minutos totales de Z3 en los 7 días previos.** Este valor genera el aviso "Tiempo en alta intensidad acumulado esta semana (Xmin en Z3)" en `reason_text` cuando supera 60 minutos. |
| `load_14d` / `load_14d_nobs` | 14 días | Carga total de las 2 semanas anteriores. |
| `load_28d` / `load_28d_nobs` | 28 días | Carga total del mes anterior. |
| `acwr_simple_prev` | 7d / 28d | `((sum load d-1..d-7)/7) / ((sum load d-1..d-28)/28)`. Rolling simple, con `shift(1)`. Si la base crónica es 0, queda `NaN`. |
| `acute_load_72h_rel` | 3d / 28d | `load_3d / (load_28d / 28)`. Se calcula solo con `load_ctx_ready = True` y `load_28d_nobs >= 14`; fuera de ese contexto queda `NaN`. Los umbrales operativos se calibran preferentemente por percentiles locales (`P75/P90`) del histórico listo del atleta, usando todo el histórico disponible en `base_df` para el cálculo de esos percentiles, y si aún no hay suficiente histórico caen en umbrales provisionales bootstrap (`3.9/4.5`). |
| `monotony_7d_prev` | 7 días | `media(load_day previos 7d calendario) / sd(load_day previos 7d calendario)`. Se calcula sobre calendario continuo; los días sin sesión cuentan como `0`. Si `std == 0` o `load_7d_nobs < 3`, queda `NaN`. |
| `strain_7d_prev` | 7 días | `sum(load_day previos 7d) * monotony_7d_prev`. Hereda `NaN` si `monotony_7d_prev` no está disponible. |
| `load_ctx_ready` | bool | `True` cuando `load_28d_nobs >= 14`. Señala que la capa canónica de contexto de carga ya tiene suficiente soporte histórico para uso interpretativo estable y para calcular `acwr_simple_prev`, `acute_load_72h_rel`, `monotony_7d_prev` y `strain_7d_prev`. |
| `finish_strong_7d_count` | 7 días | Conteo rolling de días con `late_intensity_day = 1` en la semana previa. |
| `elev_loss_7d_sum` | 7 días | Suma rolling de desnivel negativo en la semana previa. Campo descriptivo; no lo usa el gate. |

### AP-03 y concordancia v1 vs sombra

`AP-03` es una capa local de validación sobre `trail_run`. No cambia `sessions_day.csv`, no cambia el gate y no sustituye `AP-01`.

- `v1_snapshot` cachea la decisión mínima de `AP-01` v1 para ese día.
- `runaware_context` cachea la propuesta experimental en sombra.
- `runaware_context.strength_basis` explicita qué cobertura o combinación de señales justifica `strength = strong` o `exploratory`.
- `runaware_context.terrain_climb_hr_mean` traslada la FC media en subida desde `terrain_fit_context` para contextualizar el peaje cardiovascular del tramo dominante.
- `runaware_context.terrain_climb_vam_mean` traslada la VAM media en subida desde `terrain_fit_context` para contextualizar el ritmo vertical del tramo dominante.
- `runaware_context.terrain_climb_power_mean` traslada la potencia media en subida desde `terrain_fit_context` para contextualizar el esfuerzo mecánico del tramo dominante.
- `runaware_context.runaware_severity_basis` explicita qué umbrales o señales empujan `runaware_severity_candidate` a `high`, `low` o `n/d`.
- `v1_shadow_comparison` resume si ambas capas coinciden o discrepan.
- `v1_shadow_history` agrega varias sesiones comparables para ver tendencia y deriva.

La concordancia aquí mide alineación de criterio, no dureza de la sesión:

- `aligned` = la sombra y v1 toman la misma decisión.
- `divergent` = la sombra propone algo distinto; no es un fallo por sí mismo, pero sí una señal para revisar umbrales.
- `insufficient` = no había señal suficiente para comparar.

Uso correcto: interpretar si la sombra está calibrada respecto a la v1. Uso incorrecto: leer esta concordancia como una métrica de carga o como una reclasificación del entrenamiento.

### Señal DO-02 — polarización rolling por familia

Esta capa se calcula directamente desde `sessions.csv` sobre la ventana causal `D-7..D-1`. Primero identifica la familia dominante de la ventana y después recalcula la distribución sobre las sesiones de esa familia.

| Campo | Ventana | Qué es |
|-------|---------|--------|
| `dominant_family_prev_7d` | 7 días | Familia deportiva dominante en la ventana previa (`run_family`, `bike_family`, `elliptical_family`, `hike_family`). Vacío si no hay dominancia clara. |
| `dominant_family_share_prev_7d` | 7 días | Fracción de `moving_min` que aporta la familia dominante sobre el total de la ventana previa. Umbral v1: `>= 0.60`. |
| `n_sessions_usable_prev_7d` | 7 días | Número de sesiones de la familia dominante con cobertura válida de zonas en la ventana previa. `0` si no hay señal usable. |
| `z1_pct_weighted_prev_7d` / `z2_pct_weighted_prev_7d` / `z3_pct_weighted_prev_7d` | 7 días | Porcentaje ponderado por tiempo de la familia dominante en la ventana previa, recalculado desde `sessions.csv`. |
| `distribution_signal_confidence_prev_7d` | 7 días | `low`, `moderate` o `high` según soporte de la ventana rolling y cobertura válida. Vacío si no hay familia dominante. |
| `polarisation_index_prev_7d` | 7 días | Ratio v1 de polarización calculado como `(z1_pct_weighted_prev_7d + z3_pct_weighted_prev_7d) / max(z2_pct_weighted_prev_7d, 1.0)`. `NaN` si no hay señal. |
| `intensity_blackhole_flag` | 7 días | `True` solo cuando la señal es suficientemente confiable y la ventana cumple los umbrales v1 cerrados. `False` en el resto de casos. El umbral de volumen `>= 90` se aplica a la familia dominante de la ventana, no al total mezclado. La salida es diaria, pero la lectura operativa debe colapsar días consecutivos en episodios/runs si se quiere medir frecuencia real de activacion. |
| `intensity_blackhole_episode_id` | 7 días | Identificador consecutivo del episodio actual de `intensity_blackhole_flag = True`. `NaN` si el día no pertenece a un episodio. |
| `intensity_blackhole_episode_len` | 7 días | Longitud total del episodio consecutivo de `intensity_blackhole_flag = True`, medida sobre las filas emitidas en `sessions_day.csv`. Repetida en todos los días del episodio. `NaN` si el día no pertenece a un episodio. |

> Nota de uso futuro: si esta señal entra en `reason_text`, la alerta textual debe emitirse solo en el primer día de cada `intensity_blackhole_episode_id`. Días consecutivos con la misma ventana rolling y el mismo índice no deben repetir el mensaje.
>
> Nota de semántica: los huecos de calendario sin fila en `sessions_day.csv` no rompen el episodio. Es decir, `episode_len` cuenta filas consecutivas con flag `True`, no días calendario consecutivos. Si se quiere una métrica de span calendario, debe añadirse una columna aparte.

> Nota operativa: esta señal puede aparecer varios dias seguidos porque la ventana rolling se solapa. Para analizar frecuencia, contar episodios consecutivos de `True`; para analizar cobertura diaria, contar dias individuales.

### Semántica de _nobs — por qué importa

`_nobs` responde a la pregunta: "de los N días de la ventana, ¿cuántos tenían un valor **real** para esta métrica concreta?"

**Ejemplo crítico:** Imagina una semana donde entrenaste lunes (trail), miércoles (fuerza), y viernes (trail). El día jueves quieres calcular `z3_7d_sum`:
- Lunes tuvo z3_total_min = 8.5 (trail con subidas)
- Miércoles fue fuerza → `z3_min_day = NaN` (no tiene sentido hablar de Z3 en fuerza)
- Martes no entrenaste → no hay fila

Si el pipeline rellenara NaN→0 **antes** de contar nobs, contaría miércoles como "0 minutos de Z3" — como si ese día hubieras confirmado que no hubo Z3. Pero la realidad es que el concepto ni siquiera aplica ese día. La métrica era **desconocida**, no cero.

**Fix v3.1:** `_nobs` se computa ANTES de rellenar NaN→0. Además, las métricas aeróbicas diarias (`work_total_min_day`, `work_n_blocks_day`, `z3_min_day`, `late_intensity_day`) quedan en `NaN` si ese día no hubo sesión aeróbica. Así:
- `z3_7d_nobs = 1` (solo lunes tenía un valor real de Z3)
- `z3_7d_sum = 8.5` (solo el valor real)

**Regla de interpretación:** Solo confía en un rolling si `_nobs >= 3` (o idealmente `_nobs == ventana`). Un `z3_7d_sum = 8.5` con `nobs = 1` significa "solo tengo un dato de los 7 días" — no es representativo.

---

## 5. INTENSITY_DISTRIBUTION_WEEKLY.CSV — distribución observada por deporte

Este sidecar resume la estructura real de intensidad por combinación `deporte x semana` usando `sessions.csv` como fuente primaria. La semana se define de lunes a domingo.

Principios:

- usa minutos por zona (`z1_total_min`, `z2_total_min`, `z3_total_min`) como dato primario,
- pondera por tiempo total, no por media aritmética simple de `%` por sesión,
- es descriptivo e intra-deporte,
- no alimenta `FINAL`, `DASHBOARD` ni recolorea el gate.

Columnas:

| Campo | Tipo | Qué es |
|-------|------|--------|
| `window_start` / `window_end` | date | Lunes y domingo de la ventana semanal. |
| `sport` | enum | Deporte normalizado (`bike`, `road_run`, `trail_run`, `elliptical`, `hike` en v1). |
| `n_sessions_total` | int | Sesiones del deporte observadas en esa semana. |
| `n_sessions_usable` | int | Sesiones con cobertura suficiente de zonas para agregar minutos de forma válida. |
| `total_duration_min` | float | Tiempo aeróbico total agregado de la ventana. |
| `z1_total_min` / `z2_total_min` / `z3_total_min` | float | Minutos agregados por zona. |
| `z1_pct_weighted` / `z2_pct_weighted` / `z3_pct_weighted` | float % | Porcentaje ponderado por tiempo: `sum(zN_total_min) / sum(z1+z2+z3) * 100`. |
| `work_total_min` / `work_n_blocks` / `work_longest_min` | float/int | Resumen estructural de trabajo sostenido en la ventana. |
| `work_avg_z3_pct_weighted` | float % | Intensidad media de Z3 dentro de los bloques, ponderada por `work_total_min`. |
| `zones_source_mix` | string | Recuento resumido de procedencia de zonas, por ejemplo `icu=2;fallback=1`. |
| `intensity_category_mix` | string | Mezcla resumida de categorías de sesión, por ejemplo `easy=2;work_steady=1`. |
| `distribution_pattern` | enum | Etiqueta descriptiva: `polarized`, `pyramidal`, `threshold` o `mixed`. |
| `distribution_confidence` | enum | `low`, `moderate` o `high` según soporte semanal real. |
| `distribution_notes` | string | Motivos estructurados de confianza o limitación (`too_few_sessions`, `partial_zone_coverage`, `zones_fallback_present`, `low_total_duration`). |

Reglas mínimas de confianza en v1:

- `low` si hay `<2` sesiones totales o `<2` sesiones utilizables,
- `moderate` con `2` sesiones utilizables,
- `high` con `>=3` sesiones utilizables y `>=90` minutos agregados,
- degradar un nivel si hay cobertura parcial de zonas o `zones_source = fallback`.

Reglas mínimas de patrón en v1:

- `threshold` si `Z2 >= Z1` y `Z2 > Z3`,
- `pyramidal` si `Z1 > Z2 > Z3` y `Z1 - Z2 >= 10`,
- `polarized` si `Z1 >= 70` y `Z3 >= Z2`,
- `mixed` en el resto.

---

## 6. METADATA.JSON — trazabilidad del pipeline

Cada corrida del pipeline genera un `ENDURANCE_HRV_sessions_metadata.json` que documenta exactamente qué se procesó, con qué parámetros, y si hay algo sospechoso.

```json
{
  "pipeline_version": "v3.11",
  "params": {
    "VT1_DEFAULT": 143,
    "VT2_DEFAULT": 161,
    "MOVING_VEL_THRESH": 0.3,
    "BLOCK_GAP_MAX_S": 60,
    "BLOCK_HR_DROP_MAX": 10,
    "BLOCK_MIN_DURATION_S": 180,
    "LATE_MIN_MOVING_MIN": 40,
    "LATE_HR_DELTA_THRESH": 8,
    "DRIFT_MIN_MOVING_MIN": 30
  },
  "params_hash": "c1c78a78",
  "build_time": "2026-02-28T16:45:00Z",
  "input_range": {"oldest": "2025-06-01", "newest": "2026-02-28"},
  "counts": {
    "sessions": 306,
    "days": 240,
    "with_streams": 204,
    "with_notes": 6,
    "with_subjective_wellness": 51
  },
  "stream_sampling": {
    "n_streams": 204,
    "dt_mean": 0.998,
    "dt_min": 0.950,
    "dt_max": 1.020,
    "assumed_1hz": true
  },
  "zones_source_dist": {"icu": 306, "fallback": 0},
  "training_audit": {
    "dataset_level": {
      "sports_seen": 3,
      "days_with_sessions": 240,
      "aerobic_sessions": 230,
      "load_days_ready": 180
    },
    "signal_level": {
      "sampling_ok": true,
      "aerobic_stream_coverage_pct": 99.6,
      "aerobic_drift_coverage_pct": 88.7,
      "zones_fallback_pct": 0.0,
      "fallback_sports": [],
      "interpretability_limits": []
    },
    "metric_level": {
      "load_context": {"state": "high", "reasons": []},
      "zone_intensity": {"state": "high", "reasons": []},
      "cardiac_drift": {"state": "high", "reasons": ["partial_aerobic_drift_coverage"]},
      "coaching_load": {"state": "high", "reasons": []}
    }
  }
}
```

### Campos clave

| Campo | Qué mirar |
|-------|-----------|
| `params_hash` | Si cambias cualquier parámetro, el hash cambia. Permite saber si dos corridas usaron la misma configuración. |
| `stream_sampling.assumed_1hz` | **Si es `false`, trátalo como warning fuerte.** Las conversiones de muestras a minutos pueden estar sesgadas. Hay que investigar qué sesiones tienen dt ≠ 1.0 (el campo `stream_dt_est` en sessions.csv te dice cuáles) antes de confiar plenamente en las métricas derivadas de stream. No implica por sí solo que el metadata esté mal: es un canario deliberado. |
| `stream_sampling.dt_mean` | Debería ser ~1.000. Si se aleja mucho (ej: 0.5 o 2.0), Intervals cambió su re-muestreo. |
| `zones_source_dist` | Si `fallback > 0`, hay deportes sin zonas configuradas en Intervals. Revisa tu configuración de zonas. |
| `counts.with_streams` | Sesiones con stream HR disponible. Si es mucho menor que `sessions`, hay sesiones sin stream (ej: fuerza sin HR, sesiones muy cortas). Las métricas de zonas serán NaN para esas sesiones. |
| `counts.with_subjective_wellness` | Días del output canónico de wellness subjetivo con al menos una señal subjetiva o comentario libre disponible. |
| `training_audit.dataset_level` | Cobertura gruesa del dataset que sí soporta lecturas de carga: deportes vistos, días con sesión, sesiones aeróbicas y días donde la capa canónica de carga (`load_ctx_ready`) ya es utilizable. |
| `training_audit.signal_level` | Calidad de señal para métricas de coaching/carga: sampling, cobertura de stream aeróbico, cobertura de drift, porcentaje de fallback de zonas y límites de interpretabilidad activos. |
| `training_audit.metric_level.*.state` | Estado operativo mínimo por métrica: `high`, `contextual`, `informational` o `not_applicable`. La salida no bloquea el pipeline; sirve para rebajar interpretación cuando la capa de sesiones es parcial. |
| `training_audit.metric_level.*.reasons` | Motivos concretos de degradación (`zones_fallback_present`, `partial_aerobic_stream_coverage`, `load_context_not_ready`, etc.). Pensado para trazabilidad y consumo aguas abajo en `analysis/`. |

---

## 7. Conexión con el gate HRV (reason_text)

`build_hrv_final_dashboard.py` lee `sessions_day.csv` y genera avisos contextuales en `reason_text`. La carga canónica sigue siendo informativa: no recolorea el gate.

| Condición | Aviso generado |
|-----------|----------------|
| `load_ctx_ready` + `acute_load_72h_rel >= P75/P90 local` | "Carga aguda 72h por encima de tu base crónica (acute_load_72h_rel=Xx; load_3d=Y)" |
| `load_ctx_ready` + `acwr_simple_prev >= 1.3` | "ACWR alto: carga aguda por encima de la base crónica" |
| `load_ctx_ready` + `monotony_7d_prev >= 1.8` | "Monotonía elevada/alta: patrón de carga poco variable" |
| `load_ctx_ready` + `strain_7d_prev >= P75/P90 local` | "Strain alto/muy alto: semana exigente y poco descargada" |
| `work_7d_sum > 200` | "Volumen semanal alto (work_7d=Xmin)" |
| `z3_7d_sum > 60` | "Tiempo en alta intensidad acumulado esta semana (Xmin en Z3)" |
| `intensity_clustering_flag = 1` + `level=low/high` | "VERDE pero con X días intensos..." o "Clustering ... reciente: vigilar recuperación" |
| ROJO + `load_day < 30` + sueño OK | "ROJO sin carga previa ni sueño malo: revisar factores externos al entrenamiento" |
| VERDE + `acute_load_72h_rel >= P75/P90 local` | "VERDE con carga aguda 72h (acute_load_72h_rel=Xx; load_3d=Y): precaución con la intensidad" |
| VERDE + contexto canónico exigente | "VERDE con contexto de carga exigente: precaución con la intensidad" |
| VERDE + `acute_load_72h_rel >= P75/P90 local` + señal canónica exigente | "VERDE con convergencia de carga (carga 72h + ACWR/monotonía/strain): precaución con la intensidad reforzada" |

**Principio:** Los avisos informan, nunca cambian el semáforo. El gate sigue dependiendo exclusivamente de HRV + pulso. `load_3d` sigue siendo la señal bruta de 3 días, pero el aviso interpretado principal pasa por `acute_load_72h_rel`; la capa canónica sigue siendo `ACWR` + `monotony` + `strain`; y el clustering de intensidad aporta una alerta proactiva de mala distribución reciente. Si varias capas convergen en un día VERDE, el cierre operativo se vuelve más prudente, pero el color no cambia.

**Calibración local de carga:** `acute_load_72h_rel` usa percentiles del histórico listo del atleta (`P75/P90`) cuando hay soporte suficiente; mientras tanto, el dashboard usa umbrales bootstrap provisionales (`3.9/4.5`) para no perder señal al arrancar.

---

## 8. Validación e integridad

Tests que deben pasar después de cada procesamiento:

### sessions.csv

```python
# Sin duplicados por session_id
assert df["session_id"].is_unique

# Zonas suman 100% (con tolerancia de redondeo)
aerobic = df[df["session_group"].str.startswith("endurance")]
z_sum = aerobic["z1_pct"] + aerobic["z2_pct"] + aerobic["z3_pct"]
assert ((z_sum - 100.0).abs() < 0.1).all()

# work_total ≤ moving_min (no puedes trabajar más de lo que te mueves)
assert (aerobic["work_total_min"] <= aerobic["moving_min"] + 0.1).all()

# work_longest ≤ work_total
assert (aerobic["work_longest_min"] <= aerobic["work_total_min"] + 0.1).all()
```

### sessions_day.csv

```python
# Sin duplicados por Fecha
assert day["Fecha"].is_unique

# load_3d_nobs <= 3 (no puede haber más días que la ventana)
assert (day["load_3d_nobs"] <= 3).all()

# z3_7d_nobs <= 7
assert (day["z3_7d_nobs"] <= 7).all()

# intensity_clustering_level solo puede ser high/low o estar vacío
assert set(day["intensity_clustering_level"].dropna().unique()) <= {"low", "high"}

# load_ctx_ready solo puede activarse si hay al menos 14 observaciones reales
assert (~day["load_ctx_ready"] | (day["load_28d_nobs"] >= 14)).all()
```

### intensity_distribution_weekly.csv

```python
weekly = pd.read_csv("ENDURANCE_HRV_intensity_distribution_weekly.csv")

# Porcentajes ponderados coherentes
valid = weekly.dropna(subset=["z1_pct_weighted", "z2_pct_weighted", "z3_pct_weighted"])
z_sum = valid["z1_pct_weighted"] + valid["z2_pct_weighted"] + valid["z3_pct_weighted"]
assert ((z_sum - 100.0).abs() < 0.2).all()

# Confianza en vocabulario cerrado
assert set(weekly["distribution_confidence"].dropna().unique()) <= {"low", "moderate", "high"}

# Patrón en vocabulario cerrado
assert set(weekly["distribution_pattern"].dropna().unique()) <= {"polarized", "pyramidal", "threshold", "mixed"}
```

### ENDURANCE_HRV_sessions_metadata.json

```python
import json
meta = json.load(open("ENDURANCE_HRV_sessions_metadata.json"))

# Sampling rate: si no parece 1 Hz, elevar warning y revisar sessions.csv
assert "assumed_1hz" in meta["stream_sampling"]

# Todas las sesiones tienen zonas de Intervals (no fallback)
assert meta["zones_source_dist"].get("fallback", 0) == 0
```

---

## 9. Conceptos clave (glosario)

### VT1 y VT2 (umbrales ventilatorios)

Los dos puntos de inflexión de tu capacidad aeróbica. **VT1** es el momento donde tu respiración empieza a acelerarse más de lo proporcional al esfuerzo — ya no puedes hablar cómodamente. **VT2** es el momento donde la acumulación de lactato se vuelve insostenible — no puedes hablar y la fatiga se dispara. La franja entre VT1 y VT2 (Z2) es donde ocurre la mayor parte del entrenamiento productivo de resistencia. Por encima de VT2 (Z3) es alta intensidad pura.

### Moving mask

Filtro que descarta las muestras de HR donde no te estabas moviendo (velocidad ≤ 0.3 m/s). Sin este filtro, una parada de 5 minutos en un avituallamiento diluye tus porcentajes de zona: tu HR baja a 90 lpm, esos 300 segundos se cuentan como "Z1", y tu sesión parece más fácil de lo que fue. Con la mask, solo cuentan los momentos donde realmente estabas esforzándote.

### Work block (bloque de trabajo)

Periodo continuo donde tu HR estuvo por encima de VT1 (Z2 o Z3) durante al menos 3 minutos. El algoritmo fusiona tramos cercanos si el gap es ≤60 segundos y la caída de HR es ≤10 lpm (porque cruzar un arroyo en 30 segundos no interrumpe fisiológicamente tu esfuerzo). **Es la unidad básica de "trabajo de resistencia" en este pipeline.**

### Drift cardíaco

Aumento progresivo de la frecuencia cardíaca a la misma velocidad (o potencia) a lo largo de una sesión. Si al minuto 10 corrías a 5:30/km con HR 140 y al minuto 60 corrías al mismo ritmo con HR 155, hubo drift del ~10%. Causas: fatiga muscular, deshidratación, calor, vaciamiento de glucógeno. Es una señal de que la sesión te costó más de lo que sugiere el ritmo.

### Causalidad en effort_vs_recent

Los percentiles P25/P75 que definen "above / typical / below" se calculan **solo con sesiones anteriores** a la fecha de cada sesión. Una sesión de enero se compara contra lo que habías hecho hasta enero, no contra tu historial completo (que incluiría febrero-marzo). Esto es "causalidad online" — evita que información del futuro contamine la clasificación del pasado.

### _nobs (number of observations)

Cuántos días de la ventana rolling tenían un valor real (no NaN) para esa métrica. Es la diferencia entre "cero real" (entrenaste aeróbico y no hubo Z3) y "desconocido" (no entrenaste, o solo hiciste fuerza). Sin _nobs, no puedes saber si un z3_7d_sum = 0 significa "descansé toda la semana" o "solo tengo 1 dato de 7 días".

---

## 10. Historial de versiones y fixes

**Versión operativa actual:** `v3.12`

Lo siguiente es historial de cambios acumulados. No sustituye al estado vigente declarado al inicio del documento.

### v3.12 (FP-01 durabilidad mecánica — spike de validación)
1) `sessions.csv` bumped `68 -> 73` columnas (nota: 68 = 67 declaradas al cierre de v3.11 + `stream_dt_est` que ya existía desde v3.10 pero no figuraba en el conteo oficial de v3.11)
2) columnas nuevas en capa mecánica: `run_power_first_half`, `run_power_second_half` (antes se calculaban y se descartaban; ahora persisten cuando `run_power_available=1`)
3) columnas derivadas nuevas: `durability_applicable` (0/1), `speed_ratio`, `power_ratio`
4) alcance: `road_run`, `trail_run`, `hike`; bike excluido sin potenciómetro
5) `durability_applicable=1` usa puerta clásica run-aware: `road_run >= 60/75 min` según potencia útil, `trail_run >= 75/90 min`, `hike >= 90 min`, además de `work_n_blocks <= 2` y `speed_first_half` disponible
6) `power_ratio` es **NaN cuando `run_power_available=0`** — la gate es explícita en el pipeline, no inferida de la presencia de las mitades. `speed_ratio` es el fallback cuando `power_ratio` no está disponible.
7) estas columnas no alimentan `reason_text`, `FINAL` ni ningún gate HRV (spike de validación; thresholds pendientes de backtesting)

### v3.11 (SYA-04 extracción mínima canónica de coach metrics)
1) `sessions.csv` bumped `58 -> 67` columnas con la extracción mínima cerrada en `SYA-03A`
2) columnas nuevas: `calories`, `average_cadence`, `average_weather_temp`, `hrr_drop_bpm`, `trimp`
3) columnas condicionales nuevas si `device_watts=true`: `icu_weighted_avg_watts`, `icu_joules_above_ftp`, `icu_max_wbal_depletion`, `decoupling`
4) no se añaden llamadas API nuevas ni zonas por potencia; la extracción sale del payload ya presente en `/athlete/{id}/activities`

### v3.10 (DO-02 polarización rolling por familia)
1) `sessions_day.csv` bumped `49 -> 60` columnas con la señal `DO-02`
2) nuevo cálculo rolling `D-7..D-1` desde `sessions.csv`, no proyección del sidecar semanal
3) la dominancia se decide por `sport_family` y se recalcula la distribución sobre la familia dominante
4) la salida añade `dominant_family_prev_7d`, `polarisation_index_prev_7d`, `intensity_blackhole_flag` y resumen de episodio sin tocar el gate HRV

### v3.8 (DO-01 distribución observada por deporte)
1) `sessions.csv` bumped `57 -> 58` columnas con `z1_total_min`
2) nuevo sidecar `ENDURANCE_HRV_intensity_distribution_weekly.csv`
3) la agregación semanal por deporte usa minutos ponderados por zona, no medias simples de porcentajes
4) la salida añade patrón descriptivo y confianza explícita sin tocar el gate HRV

### v3.0 (fixes del revisor externo)
A) Moving mask en zonas/blocks/late_intensity  
B) HR/vel alineados en drift  
C) Fallback VT1/VT2 por sport + zones_source  
D) effort dual: recent + anchor  
E) Rolling con _nobs  
F) effort split aerobic/strength  

### v3.1 (fixes post-revisión)
1) hr_p95 sobre hr_z (mismo universo que zonas) — coherencia interna  
2) _nobs = cobertura real de métrica, computado ANTES de NaN→0 fill  
3) work_total_min_day desde agregados, no parseando string forense  
4) stream_dt_est en session + stream_sampling en metadata (canary 1Hz)  
5) classify_intensity: firma sin z3_pct, documentado como "estructura de trabajo"  

### v3.2 (alineación semántica y trazabilidad)
1) `elev_density` = `elev_gain / distance` (verticalidad ascendente, no relieve total)  
2) `PIPELINE_VERSION` bumped a `v3.2` en sessions + metadata  
3) `ENDURANCE_HRV_weekly_coach.json`  
4) metadata renombrado a `ENDURANCE_HRV_sessions_metadata.json`  

### v3.3 (capa mecánica mínima y prioridad de fuentes)
1) `sessions.csv` bumped `43 -> 57` columnas con capa mecánica opcional para deportes de pie  
2) fuente prioritaria de mecánica: `FIT` descargado desde Intervals (`/activity/{id}/fit-file`)  
3) Polar AccessLink queda como fallback cuando el FIT no está disponible o no trae señal útil  
4) columnas nuevas: `mechanics_source`, `polar_sport_raw`, `polar_start_delta_min`, `polar_duration_gap_min`, `run_power_*`, `speed_first_half`, `speed_second_half`, `cadence_first_half`, `cadence_second_half`, `polar_speed_available`, `polar_cadence_available`

### v3.4 (clustering proactivo de intensidad)
1) `sessions_day.csv` bumped `44 -> 49` columnas  
2) columnas nuevas: `intense_day`, `intense_days_prev_3d`, `intense_days_prev_5d`, `intensity_clustering_flag`, `intensity_clustering_level`  
3) cálculo sobre calendario continuo con `shift(1)`: los días sin sesión cuentan como `0` para esta capa concreta  
4) `build_hrv_final_dashboard.py` consume la señal como contexto y la propaga con `ffill(limit=2)` en días HRV sin sesión

### v3.5 (ADC-01 auditoría mínima por capas)
1) `ENDURANCE_HRV_sessions_metadata.json` añade `training_audit`  
2) la auditoría separa `dataset_level`, `signal_level` y `metric_level`  
3) `metric_level` expone estados mínimos por capa (`load_context`, `zone_intensity`, `cardiac_drift`, `coaching_load`)  
4) el objetivo es rebajar confianza de coaching/carga cuando falten streams, haya zonas en fallback o la cobertura sea parcial, sin bloquear el pipeline ni tocar el gate HRV

### v3.7 (alineación documental)
1) la cabecera del contrato y la versión operativa se alinean con la revisión documental posterior a RE-02
2) no hay cambios de esquema, columnas ni semántica respecto a v3.6

### v3.6 (RE-02 wellness subjetivo)
1) `build_sessions.py` añade lectura de `/athlete/{id}/wellness` desde Intervals  
2) nuevo sidecar `ENDURANCE_HRV_wellness_subjective.csv` con `fatigue`, `stress`, `mood`, `motivation`, `soreness`, `injury`, comentario, labels y cobertura 7d  
3) `ENDURANCE_HRV_sessions_metadata.json` añade `counts.with_subjective_wellness`  
4) la capa queda disponible para análisis retrospectivo o capas separadas; no entra en `reason_text`

---

## 10. Pipeline

```bash
# Reprocesar todo el histórico
python build_sessions.py --backfill

# Procesar solo sesiones nuevas (para automatización diaria)
python build_sessions.py --daily

# Procesar un día específico
python build_sessions.py --date 2026-02-25
```

Genera: `sessions.csv` + `sessions_day.csv` + `ENDURANCE_HRV_weekly_coach.json` + `ENDURANCE_HRV_sessions_metadata.json`


