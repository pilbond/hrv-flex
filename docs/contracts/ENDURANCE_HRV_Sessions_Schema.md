# ENDURANCE HRV — Sessions Schema

**Revisión:** r2026-03-19 v3.2 (params_hash: c1c78a78)  
**Estado:** Producción

**Documentos relacionados:**
- `ENDURANCE_HRV_Estructura.md` — contrato de datos del sistema completo (CORE, FINAL, DASHBOARD, SLEEP)
- `ENDURANCE_HRV_Spec_Tecnica.md` — fórmulas y algoritmos del gate HRV
- `ENDURANCE_HRV_Diccionario.md` — diccionario de columnas del gate HRV

**Convención de versión:** esta cabecera identifica la revisión del pipeline de sesiones (`r2026-03-19 v3.2`), no la versión global del sistema HRV. La versión de sistema vigente se declara en `ENDURANCE_HRV_Spec_Tecnica.md`.

---

## 0. Para qué sirve este pipeline

El gate HRV (CORE → FINAL → DASHBOARD) responde a la pregunta "¿cómo estás hoy?". Pero no sabe **qué hiciste ayer**: no ve si corriste 90 minutos con intervalos en Z3, si hiciste fuerza, o si fue un día de descanso. Esa pieza la aporta el pipeline de sesiones.

Sessions extrae de Intervals.icu el detalle de cada entrenamiento — stream de HR segundo a segundo, velocidad, desnivel — y lo transforma en métricas que describen **la estructura real del trabajo**: cuántos minutos pasaste por encima de VT1 en bloques sostenidos, cuánto de ese trabajo fue en Z3, si terminaste la sesión con el corazón más alto que al principio (drift), y cómo se compara esa sesión con tu histórico reciente.

El resultado alimenta el `reason_text` del gate HRV con avisos de carga ("Volumen semanal alto", "Z3 acumulado alto"), pero **nunca modifica el gate ni la acción** — es contexto informativo para tu decisión.

### Alcance

Este pipeline está diseñado para **un único atleta** y consume la cuenta personal de Intervals.icu asociada a ese atleta.

- No pretende agregar ni comparar sesiones entre varios atletas.
- No define particionado por usuario, equipos, coaches ni tenants.
- El uso del endpoint `/athlete/{id}` es una fuente externa concreta, no una señal de que el sistema deba generalizarse a múltiples atletas dentro de la misma instalación.

### Lo que NO hace este pipeline

- ❌ No cambia el semáforo (gate_final sigue dependiendo solo de HRV + pulso)
- ❌ No sustituye a Intervals.icu (que sigue siendo la fuente de carga/TSS/ATL/CTL)
- ❌ No procesa datos Polar directos (el sueño está en sleep.csv)
- ❌ No calcula zonas por potencia (solo HR)

---

## 1. Arquitectura

| Archivo | Granularidad | Para qué sirve |
|---------|-------------|-----------------|
| `sessions.csv` | 1 fila por sesión | Detalle completo de cada entrenamiento: zonas, work blocks, drift, clasificación. Lo que miras cuando quieres entender una sesión concreta. |
| `sessions_day.csv` | 1 fila por día | Agregados diarios + rolling 3d/7d/14d/28d con cobertura. Lo que lee `build_hrv_final_dashboard.py` para generar avisos de carga en reason_text. |
| `ENDURANCE_HRV_sessions_metadata.json` | 1 por corrida | Trazabilidad: versión del pipeline, parámetros usados, hash de configuración, sampling rate del stream. Para auditoría y depuración. |

### Fuente de datos

El pipeline consume la API de Intervals.icu:
- `/api/v1/athlete/{id}/activities` — lista de actividades con metadatos (load, duration, type, RPE...)
- `/api/v1/activity/{id}/streams` — stream de HR y velocidad segundo a segundo

El stream HR de Intervals es idéntico al TCX del sensor (verificado empíricamente: 4844 vs 4843 puntos, Δ=0). No se necesita descargar TCX.

**Sampling rate:** Intervals re-muestrea todos los streams a 1 Hz. El pipeline verifica esto con `stream_dt_est` (canary). Si alguna sesión se desvía significativamente de 1.0, las conversiones de muestras a minutos serían incorrectas.

---

## 2. SESSIONS.CSV — columnas y significado

43 columnas organizadas en 7 bloques. Cada bloque agrupa campos relacionados.

### Bloque A — Identidad (9 campos)

Quién eres, cuándo entrenaste, y qué zonas se usaron para clasificar el esfuerzo.

| Campo | Tipo | Qué es | Ejemplo |
|-------|------|--------|---------|
| `session_id` | string | Identificador único de la actividad en Intervals.icu. Empieza con "i" seguido de un número. Sirve para rastrear cualquier sesión hasta su fuente original. | i127783816 |
| `Fecha` | date | Día en que se realizó la sesión (YYYY-MM-DD). Si entrenas dos veces un día, habrá dos filas con la misma Fecha pero distinto session_id. | 2026-02-25 |
| `start_time` | HH:MM | Hora de inicio de la sesión. Útil para distinguir sesiones dobles y para análisis de distribución horaria del entrenamiento. | 15:16 |
| `sport` | enum | Tipo de deporte normalizado (minúsculas, guiones bajos). El pipeline lo usa para asignar umbrales de zonas, decidir si hay velocidad disponible, y clasificar la sesión. | trail_run, bike, strength, swim |
| `sport_raw` | string | Tipo de deporte tal como viene de Intervals.icu, sin normalizar. Lo conservamos por trazabilidad: si algún día cambia la normalización, puedes volver al original. | TrailRun, VirtualRide |
| `source` | const | Siempre "intervals". Reservado por si en el futuro se integran otras fuentes (Garmin directo, Polar Flow, etc.). | intervals |
| `vt1_used` | int lpm | Umbral ventilatorio 1 (primer umbral) usado para esta sesión. Es el límite entre Z1 y Z2. Todo lo que está por debajo es aeróbico cómodo; por encima, empieza el "trabajo". | 143 |
| `vt2_used` | int lpm | Umbral ventilatorio 2 (segundo umbral) usado para esta sesión. Es el límite entre Z2 y Z3. Por encima de VT2 estás en zona de alta intensidad, acumulando fatiga rápidamente. | 161 |
| `zones_source` | enum | De dónde salieron los umbrales VT1/VT2 para esta sesión. **"icu"** = de las zonas HR configuradas en Intervals.icu para ese deporte (lo ideal). **"fallback"** = umbrales genéricos por deporte porque Intervals no tenía zonas configuradas. | icu / fallback |

**Sobre VT1/VT2:** Estos no son "zonas de Polar" ni "zonas de Garmin". Son TUS umbrales ventilatorios reales (o la mejor aproximación que tengas), configurados en Intervals.icu por deporte. Si cambias tus zonas en Intervals, el pipeline los recoge automáticamente. Si no están configurados, usa fallbacks conservadores.

### Bloque B — Duración y distancia (6 campos)

Lo básico de la sesión: cuánto duró, cuánto te moviste, cuánto subiste.

| Campo | Tipo | Qué es | Rango típico |
|-------|------|--------|-------------|
| `duration_min` | float | Duración total de la sesión en minutos, incluyendo pausas, paradas, y tiempo estacionario. Es el "cronómetro completo" desde que pulsas start hasta stop. | 30-120 |
| `moving_min` | float | Minutos en los que realmente te estabas moviendo (velocidad > 0.3 m/s). Es la duración "útil" — descuenta semáforos, paradas para beber, atar zapatillas, etc. **Las zonas y los work blocks se calculan solo sobre estos minutos.** | 25-100 |
| `distance_km` | float | Distancia total recorrida en kilómetros. Para fuerza/movilidad puede ser 0 o muy bajo. | 5-25 |
| `elev_gain_m` | float? | Metros de desnivel positivo acumulado (subida total). NaN en indoor y natación. | 100-1500 |
| `elev_loss_m` | float? | Metros de desnivel negativo acumulado (bajada total). NaN en indoor y natación. | 100-1500 |
| `elev_density` | float? | Metros de desnivel ganados por kilómetro recorrido (`elev_gain / distance`). Captura la "verticalidad" de la ruta: 20 m/km = plano, 60 m/km = montañoso, 100+ m/km = vertical puro. NaN si la distancia es menor a 0.5 km (para evitar divisiones ruidosas). | 20-120 |

**¿Por qué `moving_min` y no `duration_min`?** Porque una sesión de trail de 90 minutos con 15 minutos de pausas en fuentes y fotos tiene 75 minutos de trabajo real. Si calculas zonas sobre los 90, diluyes la intensidad con tiempo donde tu corazón estaba bajando en una parada. La moving mask (`vel > 0.3 m/s`) asegura que solo contamos los momentos donde realmente estabas esforzándote.

### Bloque C — Coste cardíaco global (8 campos)

Cómo respondió tu corazón durante el movimiento: frecuencia media, pico, y distribución por zonas.

| Campo | Tipo | Qué es | Rango típico |
|-------|------|--------|-------------|
| `hr_mean` | int lpm | Frecuencia cardíaca media de toda la sesión (con y sin movimiento). Viene directamente de Intervals.icu, no se recalcula. | 110-160 |
| `hr_max` | int lpm | Frecuencia cardíaca máxima registrada durante la sesión. Puede incluir picos de artefacto si el sensor tuvo problemas, pero Intervals ya filtra los más groseros. | 150-185 |
| `hr_p95` | float lpm | Percentil 95 de la FC **solo durante movimiento** (moving mask). Más robusto que hr_max porque ignora picos aislados de 1-2 segundos. Útil para saber "cuál fue tu intensidad máxima sostenible" en esa sesión. | 145-175 |
| `z1_pct` | float % | Porcentaje del tiempo **en movimiento** que tu corazón estuvo en Z1 (≤VT1). Es tu zona aeróbica cómoda: puedes hablar, el esfuerzo es sostenible indefinidamente. En una sesión "easy" bien ejecutada, debería ser >80%. | 40-95 |
| `z2_pct` | float % | Porcentaje del tiempo en movimiento en Z2 (VT1 < HR ≤ VT2). Es tu zona "tempo": puedes hablar con frases cortas, el esfuerzo es mantenible 30-60 minutos. En subidas largas de trail, es donde pasas la mayor parte. | 5-50 |
| `z3_pct` | float % | Porcentaje del tiempo en movimiento en Z3 (> VT2). Zona de alta intensidad: no puedes hablar, acumulas fatiga rápidamente, la recuperación tarda. Incluso en sesiones duras, suele ser <15% del total — los intervalos de Z3 son cortos dentro de una sesión larga. | 0-15 |
| `z2_total_min` | float | Minutos totales en Z2 (sin redondeo de porcentaje). Útil para contabilizar volumen de trabajo moderado. | 5-40 |
| `z3_total_min` | float | Minutos totales en Z3. **Este es el campo que alimenta `z3_7d_sum` en sessions_day** y que genera el aviso "Z3 acumulado alto" en reason_text. Incluso unos pocos minutos de Z3 tienen impacto real en la fatiga. | 0-15 |

**z1 + z2 + z3 = 100%** (siempre, verificado por QA). Esto es posible porque se calculan sobre el mismo universo de muestras (moving mask activa). Si sumas y no da 100%, hay un bug.

**¿Por qué zonas por HR y no por potencia?** Porque este pipeline se integra con el gate HRV, que opera sobre señal cardíaca. Las zonas HR son coherentes con todo el sistema. Para análisis por potencia, Intervals.icu ya tiene herramientas excelentes.

### Bloque D — Bloques de trabajo (8 campos)

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

### Bloque E — Indicadores de fatiga intra-sesión (2 campos)

¿Cómo fue evolucionando tu esfuerzo a lo largo de la sesión? Si terminaste con el corazón más alto que al principio a la misma velocidad, es drift cardíaco — señal de fatiga o deshidratación.

| Campo | Tipo | Qué es | Valores típicos |
|-------|------|--------|----------------|
| `late_intensity` | 0 o 1 | ¿La segunda mitad de la sesión fue significativamente más intensa que la primera? Se calcula comparando la HR media de la 1ª mitad vs la 2ª mitad (solo muestras con movimiento). Si la 2ª mitad supera a la 1ª en ≥8 lpm → 1 (sí). Solo se calcula en sesiones de ≥40 minutos de movimiento; en sesiones cortas → 0. **Diseño "mitades":** deliberadamente simple y robusto. No detecta sprints finales de 5 minutos, sino cambios sostenidos de intensidad. | 0 (mayoría) o 1 |
| `cardiac_drift_pct` | float? | Porcentaje de aumento de HR por unidad de velocidad a lo largo de la sesión. Si corres a la misma velocidad pero tu HR va subiendo, hay drift. Valores >5% sugieren fatiga, calor, o deshidratación. Solo se calcula en sesiones de ≥30 minutos con datos de velocidad; NaN si no hay velocidad (indoor) o sesión corta. HR y velocidad se alinean a la misma longitud para evitar errores de desfase. | 0-15% (normal: 3-7%) |

**¿Por qué "mitades" y no "últimos 20 minutos"?** El diseño por mitades es más robusto para sesiones de distinta duración: en una sesión de 45 min, "últimos 20 min" es casi la mitad; en una de 120 min, es solo el último sexto. Las mitades se adaptan automáticamente a la duración.

### Bloque F — Clasificación y percepción (7 campos)

Cómo se clasifica la sesión y cómo se compara con tu histórico.

| Campo | Tipo | Qué es |
|-------|------|--------|
| `load` | int | Carga de entrenamiento asignada por Intervals.icu (su modelo HRSS/TSS). No lo calcula este pipeline — viene tal cual de la fuente. Es el valor que alimenta `load_day` y `load_3d` en sessions_day.csv. |
| `rpe` | int? (1-10) | Rate of Perceived Exertion. Percepción subjetiva del esfuerzo que tú registraste después de entrenar. 1=muy fácil, 10=máximo. NaN si no lo registraste. El pipeline lo conserva pero no lo usa para clasificar — es informativo. |
| `feel` | int? | Cómo te sentiste durante la sesión (escala Intervals). NaN si no lo registraste. Informativo. |
| `intensity_category` | enum | **Clasificación de la estructura de trabajo de la sesión.** Ver §3 para la taxonomía completa. Es la respuesta a "¿qué tipo de sesión fue?" basada en los work blocks, no en el porcentaje bruto de zonas. |
| `effort_vs_recent` | enum | ¿Esta sesión fue más dura, normal, o más fácil que tus últimas 60 sesiones del mismo `session_group`? Se calcula con P25/P75 de `load` **solo sobre sesiones anteriores** (sin look-ahead), para mantener la causalidad. Valores: "above" / "typical" / "below". |
| `effort_vs_anchor` | enum | ¿Esta sesión fue más dura que cuando estabas en tu mejor forma? Compara `load` contra percentiles fijos de un periodo de referencia sano (jun-ago 2025, configurable), siempre dentro del mismo `session_group`. Detecta desentrenamiento sostenido: si tu "typical" actual está por debajo del "typical" de tu mejor periodo, algo ha cambiado. Valores: "above" / "typical" / "below". |
| `session_group` | enum | Grupo funcional de la sesión para separar estadísticas. Ver §4 para valores. |

### Bloque G — QA y trazabilidad (5 campos)

Campos técnicos para depuración y auditoría. No los necesitas para el uso diario.

| Campo | Tipo | Qué es |
|-------|------|--------|
| `notes_raw` | string? | Notas que dejaste en Intervals.icu para esa sesión. Los saltos de línea se convierten a `\|` para que no rompan el CSV. NaN si no dejaste notas. |
| `rpe_present` | 0/1 | 1 si registraste RPE, 0 si no. Permite calcular "% de sesiones con RPE" como métrica de adherencia. |
| `notes_present` | 0/1 | 1 si dejaste notas, 0 si no. Mismo propósito. |
| `stream_dt_est` | float? | Intervalo medio entre muestras del stream de HR, estimado como `moving_time / len(stream)`. Si el stream es 1 Hz, este valor debería ser ~1.000. Si se desvía mucho (ej: 0.5 o 2.0), significa que Intervals re-muestreó a otra frecuencia y todas las conversiones de "muestras → minutos" serán incorrectas. **Canary**: si ves un valor ≠1.0, investiga antes de confiar en las métricas de esa sesión. NaN si la sesión no tiene stream. |
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
| `load_7d` / `load_7d_nobs` | 7 días | Carga total de los 7 días anteriores. Con cobertura. |
| `work_7d_sum` / `work_7d_nobs` | 7 días | Minutos totales de trabajo sostenido ≥VT1 en los 7 días previos. |
| `z3_7d_sum` / `z3_7d_nobs` | 7 días | **Minutos totales de Z3 en los 7 días previos.** Este valor genera el aviso "Z3 acumulado alto" en reason_text cuando supera 60 minutos. |
| `load_14d` / `load_14d_nobs` | 14 días | Carga total de las 2 semanas anteriores. |
| `load_28d` / `load_28d_nobs` | 28 días | Carga total del mes anterior. |
| `finish_strong_7d_count` | 7 días | Conteo rolling de días con `late_intensity_day = 1` en la semana previa. |
| `elev_loss_7d_sum` | 7 días | Suma rolling de desnivel negativo en la semana previa. Campo descriptivo; no lo usa el gate. |

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

## 5. METADATA.JSON — trazabilidad del pipeline

Cada corrida del pipeline genera un `ENDURANCE_HRV_sessions_metadata.json` que documenta exactamente qué se procesó, con qué parámetros, y si hay algo sospechoso.

```json
{
  "pipeline_version": "v3.2",
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
    "with_notes": 6
  },
  "stream_sampling": {
    "n_streams": 204,
    "dt_mean": 0.998,
    "dt_min": 0.950,
    "dt_max": 1.020,
    "assumed_1hz": true
  },
  "zones_source_dist": {"icu": 306, "fallback": 0}
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

---

## 6. Conexión con el gate HRV (reason_text)

`build_hrv_final_dashboard.py` lee `sessions_day.csv` y genera avisos contextuales en `reason_text`. Los umbrales son absolutos (no percentiles):

| Condición | Aviso generado |
|-----------|----------------|
| `load_3d > 250` (con `load_3d_nobs >= 2`) | "Carga acumulada alta (load_3d=X)" |
| `work_7d_sum > 200` | "Volumen semanal alto (work_7d=Xmin)" |
| `z3_7d_sum > 60` | "Z3 acumulado alto (z3_7d=Xmin)" |
| ROJO + `load_day < 30` + sueño OK | "ROJO sin carga previa ni sueño malo: revisar otros factores" |
| VERDE + `load_3d > 200` | "VERDE con carga acumulada: precaución intensidad" |

**Principio:** Los avisos informan, nunca cambian el semáforo. El gate sigue dependiendo exclusivamente de HRV + pulso.

---

## 7. Validación e integridad

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

## 8. Conceptos clave (glosario)

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

## 9. Historial de versiones y fixes

**Versión operativa actual:** `v3.2`

Lo siguiente es historial de cambios acumulados. No sustituye al estado vigente declarado al inicio del documento.

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
3) metadata renombrado a `ENDURANCE_HRV_sessions_metadata.json`  

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

Genera: `sessions.csv` + `sessions_day.csv` + `ENDURANCE_HRV_sessions_metadata.json`


