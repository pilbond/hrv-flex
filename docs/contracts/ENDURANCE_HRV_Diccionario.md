# ENDURANCE HRV — Diccionario de Columnas (FINAL/DASHBOARD)

**Revisión:** r2026-04-28 v4.12 (jargon fixes + coverage: intensity_category, effort_vs_*, session_group, late_intensity, decoupling, load_ctx_ready, zones_source fallback, DFA α1, reason_items layers)
**Estado:** Producción

**Documentos relacionados:**
- `ENDURANCE_HRV_Spec_Tecnica.md` — especificación técnica (fórmulas y reglas)
- `ENDURANCE_HRV_Estructura.md` — contrato de datos (columnas y orden exacto)
- `ENDURANCE_HRV_Sessions_Schema.md` — contrato del pipeline de sesiones (`sessions.csv`, `sessions_day.csv`, `ENDURANCE_HRV_sessions_metadata.json`), revisión `r2026-04-20 v3.12`

**Límite de alcance de este diccionario:**
- documenta `CORE`, `FINAL`, `DASHBOARD`, `BETA_AUDIT`, `sleep`, `sessions_day`, `intensity_distribution_weekly`, `wellness_subjective` y la metadata de sesiones,
- para el detalle columna-a-columna de `sessions.csv` (73 cols), la fuente canónica es `ENDURANCE_HRV_Sessions_Schema.md`; aquí sólo se ofrece el mapa,
- no documenta artefactos locales de `analysis/` como `terrain_context`, `terrain_fit_context`, `terrain_intervals.csv` o `terrain_climbs.csv`,
- cuando haga falta esa capa de análisis de terreno, la fuente correcta es `analysis/SESSION_ANALYSIS_METHOD.md` y `analysis/ANALYSIS_DICTIONARY.md`.

---

## Índice

- §0. Cómo leer el CSV (operativo)
- §1. Valores típicos (orientación inicial)
- §2. CORE (medición canónica) — 18 columnas
- §3. FINAL (gate + auditoría extendida) — 62 columnas
- §4. DASHBOARD (vista operativa) — 10 columnas
- §5. BETA_AUDIT (forense V3) — 13 columnas
- §5bis. CONTEXT / sleep.csv (sidecar externo) — 17 columnas
- §5ter. SESSIONS_DAY (carga diaria y clustering) — sidecar CSV
- §5quater. SESSIONS METADATA / TRAINING_AUDIT (sidecar JSON)
- §5quinquies. INTENSITY_DISTRIBUTION_WEEKLY (sidecar CSV) — 21 columnas
- §5sexies. WELLNESS_SUBJECTIVE (sidecar retrospectivo) — 17 columnas
- §5septies. SESSIONS (histórico de sesiones) — 73 columnas (mapa)
- §6. Valores de gate_razon_base60 (y sombras)
- §7. Valores de Flags (CORE)
- §8. decision_path (auditoría de "quién mandó")
- §9. Diagrama de flujo (cómo se decide cada mañana)
- §10. Glosario de términos técnicos
- §11. Notas sobre latencia alta
- §12. Casos de ejemplo
- §13. "Para tontos" (muy llano)

---

## 0. Cómo leer el CSV (operativo)

### Paso 1 — ¿El dato es utilizable hoy?

1) Mira `Calidad`:
- `INVALID` → no uses HRV hoy (día perdido)
- `FLAG_mecánico` → dato usable pero con **menos fiabilidad**
- `OK` → normal

2) Mira `quality_flag` (en FINAL):
- `True` → aunque el color salga VERDE/ÁMBAR, la **acción se fuerza a SUAVE** (`Action_detail = SUAVE_QUALITY`)

### Paso 2 — ¿Qué hago hoy?

3) Mira `gate_badge`:
- Es el **semáforo final** (VERDE/ÁMBAR/ROJO/NO) + un matiz (`+ / -`) del residual.

4) Mira `Action` y `Action_detail`:
- Eso es lo que manda (no "lo que te apetece hacer").

### Paso 3 — ¿Por qué salió así?

5) `gate_razon_base60` → explica el color base (2D_OK / 2D_LN / 2D_HR / 2D_AMBOS…)
6) `decision_path` y `override_reason` → si hubo override por sombras (siempre auditado)
7) Si gate es ROJO/NO: mira `bad_streak` y `bad_7d` (acumulación)

### Lo que NO debes hacer

- ❌ Ignorar el gate cuando el RMSSD "parece bueno"
- ❌ Comparar RMSSD absoluto entre días sin contexto
- ❌ Tomar decisiones de carga con día NO/INVALID
- ❌ Entrenar intensidad con `quality_flag=True` aunque el gate sea VERDE

---

## 1. Valores típicos (orientación inicial)

**IMPORTANTE:** Estos valores son orientativos para la primera semana. Después de 30-60 días, el sistema se calibra con TUS baselines.

### HR supino matinal (HR_stable / HR_today)

| Perfil | Rango típico |
|--------|--------------|
| Deportista resistencia bien entrenado | 40-55 lpm |
| Deportista recreativo | 50-65 lpm |
| Sedentario | 60-80 lpm |
| **Alarma** | >80 lpm o <35 lpm → INVALID |

### RMSSD supino matinal (RMSSD_stable)

| Perfil | Rango típico |
|--------|--------------|
| Muy entrenado | 60-100 ms |
| Entrenado | 40-70 ms |
| Recreativo | 25-50 ms |

**Lo importante NO es el número absoluto**, sino TU tendencia vs baseline.

### Artifact_pct

| Rango | Calidad |
|-------|---------|
| <5% | Excelente |
| 5-10% | Bueno |
| 10-15% | Aceptable con vigilancia |
| 15-20% | Límite (FLAG_mecánico) |
| >20% | Malo (INVALID) |

### Tiempo_Estabilizacion

| Rango | Interpretación |
|-------|----------------|
| 60-120 s | Ideal |
| 120-300 s | Aceptable |
| >300 s | Sospechoso (revisar protocolo) |
| >600 s | Problema (no puede ser Calidad=OK) |
| NaN | No se detectó estabilización → FLAG_mecánico |

---

## 2. CORE (medición canónica) — 18 columnas

Generado por `build_hrv_core.py`. Contiene la señal fisiológica **sin decisiones**.

### Identificación

| Columna | Qué es | Para qué sirve |
|---------|--------|----------------|
| `Fecha` | Día en que te hiciste la medición matinal (YYYY-MM-DD) | Clave primaria de todo el sistema. Cada día solo puede tener una fila. |

### Gate de fiabilidad (medición)

| Columna | Qué es | Valores |
|---------|--------|---------|
| `Calidad` | Veredicto final sobre si la medición de hoy es usable. Resume en una palabra si los artefactos, la latencia y la estabilidad permiten confiar en el dato. No dice si "estás bien o mal"; dice si la medición merece confianza. | OK (fiable) / FLAG_mecánico (existe pero dudoso) / INVALID (descartado) |
| `HRV_Stability` | ¿El tramo final de la grabación fue estable? Se evalúa comparando los últimos 120 s con el tramo completo. Si la cola oscila mucho, cambia de régimen o no tiene suficientes datos, marca `Unstable`. | OK / Unstable |
| `Stability_Subtype` | Subtipo explícito del chequeo de estabilidad. Hace visible el motivo principal del `Unstable` sin obligarte a parsear `Flags`. Es útil para distinguir una simple discrepancia de cola (`STAB_LAST2_MISMATCH`) de una medición realmente rota (`STAB_TAIL_SHORT`, `STAB_LAST2_NAN`). | OK / STAB_LAST2_MISMATCH / STAB_TAIL_SHORT / STAB_CV120_HIGH / STAB_LAST2_NAN |
| `Artifact_pct` | Porcentaje del registro total que se ha descartado por artefactos del sensor, intervalos fuera de rango fisiológico y saltos bruscos entre latidos. Cuanto más bajo, más limpia la señal. Un valor alto no implica necesariamente fatiga: muchas veces es solo mala calidad de adquisición. | 0-100 (ver §1 para rangos de calidad) |
| `Tiempo_Estabilizacion` | Cuántos segundos tardó tu sistema nervioso, y la propia señal del sensor, en estabilizarse desde que empezaste la medición. Si no se detecta ese punto, queda `NaN` y fuerza `FLAG_mecánico`, porque probablemente estás midiendo una transición y no un estado estable. | segundos (ideal 60-120) o NaN |

### Señal fisiológica (del tramo estable)

| Columna | Qué es | Unidades |
|---------|--------|----------|
| `HR_stable` | Tu frecuencia cardiaca media durante el tramo estabilizado. Es tu pulso "real" de reposo matinal, una vez descartada la fase de ajuste inicial y los últimos segundos problemáticos. | lpm |
| `RRbar_s` | Intervalo RR medio en el tramo estable, es decir, el tiempo medio entre latidos. Es la inversa del pulso: `RRbar_s = 60 / HR_stable`. Sirve como control cruzado y como entrada para modelos auxiliares. | segundos |
| `RMSSD_stable` | Tu variabilidad cardiaca principal: la raíz cuadrada de la media de las diferencias al cuadrado entre latidos consecutivos, calculada sobre todo el tramo estable. Es el indicador central del tono vagal o parasimpático. Más alto, en general, implica más recuperación. | ms |
| `RMSSD_stable_last2` | Igual que `RMSSD_stable`, pero calculado solo con los últimos 120 segundos de la grabación útil. Se compara con el tramo estable completo para verificar si la señal seguía estable al final o estaba cambiando. | ms |
| `tail_mismatch_pct` | Diferencia relativa entre `RMSSD_stable` y `RMSSD_stable_last2`. Es una métrica diagnóstica pensada para entender mejor los `Unstable` de tipo discrepancia de cola. No decide el color por sí sola, pero ayuda a ver si el final de la medición se apartó mucho del resto. | % |
| `lnRMSSD` | Logaritmo natural de `RMSSD_stable`. Se usa en vez del RMSSD bruto porque la distribución de RMSSD es muy asimétrica: los días buenos generan dispersión mayor que los malos. El logaritmo la "normaliza" mejor y hace que medias, medianas y umbrales tengan más sentido estadístico. Es la señal que realmente entra en el gate. | adimensional |

### Métricas informativas Tier 2

| Columna | Qué es | Uso |
|---------|--------|-----|
| `SI_baevsky` | Índice de estrés de Baevsky. Resume la compactación del histograma RR y suele aumentar cuando la señal apunta a mayor rigidez o carga simpática. En este pipeline queda como señal complementaria, útil para auditoría o análisis futuro. | Informativo; no afecta al decisor FINAL/DASHBOARD |
| `SD1` | SD1 del diagrama de Poincare. Captura la variabilidad de corto plazo, muy relacionada con la misma dinámica que refleja RMSSD. Sirve como métrica adicional para leer la forma de la nube RR. | Informativo |
| `SD2` | SD2 del diagrama de Poincare. Captura la variabilidad de más largo plazo dentro de la serie RR estable. Ayuda a distinguir si la señal cambia solo beat-to-beat o también en una escala algo más lenta. | Informativo |
| `SD1_SD2_ratio` | Relación entre la variabilidad rápida (`SD1`) y la más lenta (`SD2`). Útil para interpretar la "geometría" del Poincare y detectar patrones menos visibles si solo miras RMSSD. | Informativo |

### Trazabilidad

| Columna | Qué es |
|---------|--------|
| `Flags` | Lista de incidencias detectadas durante el procesamiento, separadas por `\|`. Cada flag indica un problema o condición específica: estabilidad, artefactos, latencia, modo beta, etc. Ejemplo: `LAT_NAN\|ART_GT15` significa que no se detectó estabilización y además los artefactos superaron el 15%. Si está vacío, no se detectaron incidencias relevantes. |
| `Notes` | Metadatos técnicos del procesamiento en formato `clave=valor`. Incluye el fichero fuente, duraciones de cada fase, conteos de latidos en cada etapa y desglose de artefactos por tipo. Está pensado para auditoría y depuración, no para lectura diaria. |

---

## 3. FINAL (gate + auditoría extendida) — 62 columnas

Generado por `build_hrv_final_dashboard.py`. Contiene:

- suavizado ROLL3 (solo días clean; → §10)
- baseline BASE60 + SWC (→ §10)
- **veto agudo** (bypass ROLL3 ante caídas bruscas; → §10)
- gate BASE60 (decisor)
- sombras BASE42 y BASE28 (informativas; → §10)
- override opcional (modo O3)
- residual (BASE60) + sufijo (`+/-`)
- acción + acumulación + warnings
- **reason_text** (contexto de sueño + carga)
- **recovery_context_quality / recovery_support_class** (capa de análisis de recuperación: soporte sueño/carga vs gate)

### Lo mínimo que debes mirar a diario

- `gate_badge` (semáforo final + matiz)
- `Action` y `Action_detail`
- `reason_text` (contexto: sueño, carga, veto agudo)
- `recovery_support_class` si quieres saber rápido si ese color viene apoyado, frágil o en conflicto con sueño/carga
- `quality_flag`
- `gate_razon_base60`
- `decision_path` (para ver si hubo override)

### Bloques importantes

#### A) Identidad / medición base (copiado de CORE)

Las 10 primeras columnas de FINAL replican la medición de CORE, pero ahora arrastran también el subtipo explícito de estabilidad y el mismatch de cola. Siguen existiendo **2 cambios de nombre** respecto a CORE:

| Columna FINAL | Equivale a (CORE) | Qué es | Unidades |
|---------------|--------------------|--------|----------|
| `Fecha` | `Fecha` | Día de la medición matinal | YYYY-MM-DD |
| `Calidad` | `Calidad` | ¿Se puede confiar en la medición? Resume artefactos, latencia y estabilidad. Ojo: es una etiqueta de fiabilidad, no un juicio sobre tu estado fisiológico. | OK / FLAG_mecánico / INVALID |
| `HRV_Stability` | `HRV_Stability` | ¿El tramo final de la grabación fue estable o estaba oscilando? Si aquí sale `Unstable`, el raw del día existe, pero el sistema lo trata con desconfianza. | OK / Unstable |
| `Artifact_pct` | `Artifact_pct` | Porcentaje del registro descartado por ruido, artefactos y saltos entre latidos. Es una forma rápida de medir la limpieza de la señal. | 0-100 |
| `Tiempo_Estabilizacion` | `Tiempo_Estabilizacion` | Cuántos segundos tardó la señal en estabilizarse tras iniciar la medición. Si es muy alto o `NaN`, conviene sospechar de protocolo, postura o transición fisiológica. | número o NaN |
| `Stability_Subtype` | `Stability_Subtype` | Subtipo explícito de estabilidad. Hace visible el motivo principal del `Unstable` sin parsear `Flags`, y permite distinguir una discrepancia de cola de un tramo final demasiado corto o directamente no calculable. | texto |
| `tail_mismatch_pct` | `tail_mismatch_pct` | Diferencia relativa entre `RMSSD_stable` y `RMSSD_stable_last2`. Es una métrica diagnóstica para entender cuánto se apartó el final de la medición del resto del tramo estable. No es el color oficial. | % |
| `HR_today` | **`HR_stable`** | Tu pulso de reposo matinal, media del tramo estable. Es exactamente el mismo valor que `HR_stable` de CORE, solo que en FINAL cambia el nombre para alinearse con el resto del lenguaje del gate. | lpm |
| `RMSSD_stable` | `RMSSD_stable` | Tu variabilidad cardiaca del tramo estable completo. Se mantiene con el mismo nombre porque sigue siendo la métrica fisiológica de referencia del día. | ms |
| `lnRMSSD_today` | **`lnRMSSD`** | Logaritmo natural de `RMSSD_stable`. Es el valor que entra en el suavizado y el gate. Es el mismo dato que `lnRMSSD` de CORE, con nombre distinto para dejar claro que aquí representa el valor bruto de hoy. | adimensional |

**Atención — cambios de nombre CORE → FINAL:**
- `HR_stable` → `HR_today` (mismo valor, distinto nombre)
- `lnRMSSD` → `lnRMSSD_today` (mismo valor, distinto nombre)

Si haces merge CORE↔FINAL por nombre de columna, estos dos campos no casarán automáticamente. Usa `Fecha` como clave y renombra explícitamente.

**Nota:** `RRbar_s`, `SI_baevsky`, `SD1`, `SD2` y `SD1_SD2_ratio` de CORE **no se copian** a FINAL. `Stability_Subtype` y `tail_mismatch_pct` sí se copian porque añaden contexto útil para auditar discrepancias entre el raw del día y la decisión final.

#### B) Suavizado (ROLL3)

| Columna | Qué es |
|---------|--------|
| `lnRMSSD_used` | Tu lnRMSSD suavizado: la media de los últimos 3 días clean. Es el valor que realmente se compara contra el baseline para decidir el gate. Suavizar con 3 días filtra oscilaciones puntuales sin perder sensibilidad ante tendencias reales. |
| `HR_used` | Tu pulso suavizado: la media de HR de los últimos 3 días clean. Se usa junto con lnRMSSD_used en la comparación 2D del gate. |
| `n_roll3` | Cuántos días clean se usaron para el suavizado. Debe ser 3. Si es menor (por falta de días clean recientes), el gate queda NO con razón ROLL3_INSUF. |

Reduce ruido: se calcula solo con días **clean**.

#### C) Auditoría raw del día

| Columna | Qué es |
|---------|--------|
| `gate_raw_today` | Semáforo 2D contrafactual calculado con el raw del día (`lnRMSSD_today`, `HR_today`) frente a la misma baseline que usa el gate oficial. No cambia `gate_final`. Existe para responder a una pregunta muy concreta: "si me creyera el dato bruto de hoy, ¿qué color habría dado?". |
| `gate_raw_reason` | Motivo del semáforo raw (`2D_OK`, `2D_LN`, `2D_HR`, `2D_AMBOS`). Es la explicación del color contrafactual, igual que `gate_razon_base60` lo es del color oficial. |
| `unstable_note` | Resumen corto `raw vs ref` cuando `quality_flag=True`. Ejemplo: `Raw=VERDE(2D_OK) vs ref=ÁMBAR(2D_LN)`. Está pensado para que, al abrir el CSV, se vea de un vistazo si el día dudoso apuntaba en una dirección distinta a la decisión conservadora. |

Estas columnas son de auditoría, no de decisión: ayudan a interpretar los `Unstable`, pero no promocionan ni empeoran el gate por sí mismas.

#### D) Baseline BASE60 y SWC

| Columna | Qué es |
|---------|--------|
| `ln_base60` | Tu "normal" de lnRMSSD: la mediana de los últimos 60 días (solo clean, sin contar hoy). Es la referencia contra la que se compara tu valor suavizado de hoy. Se usa mediana (no media) para que días atípicos puntuales no desplacen tu referencia. |
| `HR_base60` | Tu "normal" de pulso en reposo: la mediana de HR en los últimos 60 días clean. Funciona igual que ln_base60 pero para el eje de frecuencia cardíaca. |
| `n_base60` | Cuántos días clean hay en la ventana de 60 días. Necesitas al menos 30 para que el baseline sea fiable. Si no llegas, el gate queda NO con razón BASE60_INSUF. |
| `SWC_ln` | El cambio mínimo significativo para lnRMSSD: `0.5 × SD robusta` (→ §10). Si tu delta (d_ln) no supera este umbral, se considera ruido y el gate no se enciende por esa vía. Cuanto más estable hayas sido históricamente, más estrecho es este umbral (más sensible). |
| `SWC_HR` | Igual que SWC_ln pero para el pulso. Define cuánto tiene que subir tu HR respecto a tu normal para que cuente como señal real y no como fluctuación aleatoria. |

Deltas (la distancia entre tu valor suavizado de hoy y tu baseline):

| Columna | Qué es |
|---------|--------|
| `d_ln` | Diferencia `lnRMSSD_used - ln_base60`. Negativo = tu HRV está por debajo de tu normal. Si supera -SWC_ln, contribuye al gate (ámbar o rojo). |
| `d_HR` | Diferencia `HR_used - HR_base60`. Positivo = tu pulso está por encima de tu normal. Si supera +SWC_HR, contribuye al gate (ámbar o rojo). |

#### E) Gates (BASE60 + sombras + final)

| Columna | Qué es | Valores |
|---------|--------|---------|
| `gate_base60` | El semáforo calculado con tu baseline principal (60 días). Es el punto de partida de la decisión: compara tus deltas (d_ln, d_HR) contra los umbrales SWC. | VERDE / ÁMBAR / ROJO / NO |
| `gate_razon_base60` | Explica **por qué** salió ese color. Si es 2D_OK, ambos deltas están dentro de SWC. Si es 2D_LN, tu HRV está baja. Si es 2D_AMBOS, ambas señales están fuera → convergencia de fatiga. | 2D_OK, 2D_LN, 2D_HR, 2D_AMBOS, ROLL3_INSUF, BASE60_INSUF, etc. |
| `gate_shadow42` | Semáforo calculado con el baseline de 42 días. Representa tu "normal" de las últimas ~6 semanas. Si discrepa de gate_base60, puede indicar que tu estado está cambiando y BASE60 aún no lo ve. | VERDE / ÁMBAR / ROJO / NO |
| `gate_razon_shadow42` | Motivo del semáforo de la sombra de 42 días (misma lógica 2D). | ídem gate_razon_base60 |
| `n_base42` | Días clean en la ventana de 42 días. Necesita ≥21 para operar. | entero |
| `gate_shadow28` | Semáforo con baseline de 28 días (tu "normal" del último mes). Es la sombra más reactiva: detecta cambios de régimen antes que BASE42 y BASE60. | VERDE / ÁMBAR / ROJO / NO |
| `gate_razon_shadow28` | Motivo del semáforo de la sombra de 28 días. | ídem gate_razon_base60 |
| `n_base28` | Días clean en la ventana de 28 días. Necesita ≥14 para operar. | entero |
| `decision_mode` | Qué modo de decisión está activo. O2 = las sombras solo informan, BASE60 manda. O3 = las sombras pueden ajustar el gate final si insisten varios días. | O2_SHADOW / O3_OVERRIDE_PERSIST_2of3 |
| `gate_final` | El semáforo definitivo que gobierna la acción. En modo O2, es idéntico a gate_base60. En modo O3, puede ser ±1 nivel respecto a gate_base60 si las sombras insistieron. | VERDE / ÁMBAR / ROJO / NO |
| `gate_final_delta` | Si hubo override, cuánto se movió: +1 (subida, la sombra veía mejor), -1 (bajada, la sombra veía peor), 0 (sin cambio). | -1 / 0 / +1 |
| `decision_path` | Auditoría de quién tomó la decisión final. Si es BASE60_ONLY, no hubo override. Si contiene OVERRIDE, indica qué sombra (28 o 42) forzó el ajuste y en qué dirección. | BASE60_ONLY / OVERRIDE_DOWN_28_2of3 / OVERRIDE_UP_28_2of3 / etc. |
| `override_reason` | Texto corto que explica por qué se aplicó el override (ej: "shadow28 peor 2/3"). Vacío si no hubo override. | texto o vacío |

#### F) Residual (matiz)

| Columna | Qué es | Valores |
|---------|--------|---------|
| `residual_ln` | La diferencia entre tu lnRMSSD real y el que predice un modelo lineal basado en tu pulso (RR). Si es positivo, tu HRV es más alta de lo que "debería" dado tu pulso — buena señal parasimpática. Si es negativo, tu HRV es más baja de lo esperable — posible fatiga o estrés que no se explica solo por el pulso. El modelo se entrena con tus últimos 60 días clean. | adimensional (float, típicamente -0.3 a +0.3) |
| `residual_z` | El residual normalizado: cuántas "unidades SWC del residual" te has alejado de lo esperable. Permite interpretar la magnitud: un residual_z de -1.5 es más preocupante que -0.3. Se calcula con escala robusta (MAD; → §10) para no distorsionarse por días atípicos. | z-score robusto (float, típicamente -3 a +3) |
| `residual_tag` | Sufijo visual que resume residual_z en categorías. `+` (≥0.5), `++` (≥1.0), `+++` (≥2.0) para residual positivo. `-` (≤-0.5), `--` (≤-1.0), `---` (≤-2.0) para negativo. Sin sufijo si está entre -0.5 y +0.5. | `+` / `++` / `+++` / `-` / `--` / `---` / vacío |
| `gate_badge` | El semáforo final con el matiz del residual pegado. Ejemplo: `VERDE+` (todo bien y además tu HRV es mejor de lo esperable), `ÁMBAR--` (gate ámbar y además el residual es bastante negativo). Es la columna más informativa para echar un vistazo rápido al estado completo del día. | `<COLOR><TAG>` (ej. `VERDE+`, `ÁMBAR--`, `ROJO`, `NO`) |

Interpretación del residual:
- `residual_z > 0` → HRV **mejor** de lo esperable dado RR
- `residual_z < 0` → HRV **peor** de lo esperable dado RR

El residual **no recolorea** el gate; solo añade matiz.

Tags:
- `+` / `++` / `+++` si residual_z ≥ 0.5 / 1.0 / 2.0
- `-` / `--` / `---` si residual_z ≤ -0.5 / -1.0 / -2.0

#### G) Calidad y acción

| Columna | Qué es | Valores |
|---------|--------|---------|
| `quality_flag` | ¿El dato de hoy es sospechoso? True si la medición tiene algún problema de fiabilidad (FLAG_mecánico, Unstable, o artefactos >15%) pero no llega a ser INVALID. Cuando es True, la acción se fuerza a SUAVE aunque el gate pinte VERDE — no se confía en el dato para justificar intensidad. | True / False |
| `Color_operativo` | Duplicado explícito de gate_final, sin transformaciones ni capas intermedias. Existe para que no haya duda de qué color gobierna la acción. Si lees gate_final, es exactamente lo mismo. | VERDE / ÁMBAR / ROJO / NO |
| `Action` | La instrucción operativa del día: qué tipo de entrenamiento permite el gate. INTENSIDAD_OK = puedes ejecutar intervalos o sesiones duras. Z2_O_TEMPO_SUAVE = nada explosivo, pero puedes hacer volumen en zona aeróbica. SUAVE_O_DESCANSO = regenerativo o descanso total. | INTENSIDAD_OK / Z2_O_TEMPO_SUAVE / SUAVE_O_DESCANSO |
| `Action_detail` | Matiza la acción con contexto: EJECUTAR_PLAN (verde limpio, adelante con lo planificado), SIN_HIIT (ámbar, quita intensidad pero mantén volumen), SUAVE_QUALITY (el gate podría ser bueno pero el dato no es fiable), SUAVE (rojo puntual o NO sin señal suficiente), DESCARGA (acumulación de rojos → reducir carga semanal). | EJECUTAR_PLAN / SIN_HIIT / SUAVE_QUALITY / SUAVE / DESCARGA |

Mapping:
- VERDE → `INTENSIDAD_OK` (salvo quality_flag)
- ÁMBAR → `Z2_O_TEMPO_SUAVE` (salvo quality_flag)
- ROJO/NO → `SUAVE_O_DESCANSO`

#### H) Acumulación

| Columna | Qué es |
|---------|--------|
| `bad_streak` | Cuántos días consecutivos llevas con gate ROJO. Una racha de 1 es un mal día puntual. Una racha ≥2 activa DESCARGA en Action_detail — la señal de que no es un evento aislado. Los días `NO` por falta de señal no cuentan como acumulación fisiológica. |
| `bad_7d` | Cuántos días ROJO has tenido en los últimos 7 días (no necesariamente consecutivos). Si llega a ≥3, también activa DESCARGA. Captura la situación donde alternas días malos y regulares pero la tendencia semanal es negativa. Los días `NO` no suman este contador. |

#### I) Warning + flags sistémicos (orden físico, cols 47–54)

Este bloque cubre el warning de baseline degradado y los flags sistémicos que lo acompañan, listados en el **orden físico** de las columnas en el CSV (47–54) para facilitar auditoría y merge.

| # | Columna | Qué es |
|---|---------|--------|
| 47 | `baseline60_degraded` | Alias legacy del warning de baseline. Mantiene compatibilidad hacia atrás y sigue el umbral seleccionado por `warning_mode`. En modo `adaptive90` (default) equivale a `degraded_vs_current_normal`. En modo `healthy85` equivale a `degraded_vs_best`. Se mantiene por compatibilidad con consumidores antiguos y con DASHBOARD. En consumidores nuevos, preferir `degraded_vs_best` y `degraded_vs_current_normal`. |
| 48 | `degraded_vs_best` | Señal canónica: True si tu baseline actual (mediana de los últimos 60 días) está por debajo de la referencia de mejor forma histórica (`healthy_rmssd × healthy_factor`). Responde “¿sigues lejos de tu mejor nivel conocido?”. |
| 49 | `degraded_vs_current_normal` | Señal canónica: True si tu baseline actual está por debajo de tu normal reciente adaptativa (`warning_threshold_current_normal`). Responde “¿estás en caída activa respecto a tu nivel reciente?”. |
| 50 | `healthy_rmssd` | Tu ancla histórica de RMSSD "sano": la mediana de RMSSD durante un periodo en el que estabas bien entrenado y sin problemas. Sirve como contexto de mejor forma conocida y como base de `degraded_vs_best`. |
| 51 | `healthy_hr` | Tu ancla histórica de pulso "sano": la mediana de HR en reposo durante el mismo periodo de referencia. |
| 52 | `healthy_period` | El rango de fechas usado para calcular las anclas healthy (ej: "2025-07-01 a 2025-09-30"). Identifica la referencia histórica de mejor forma. |
| 53 | `flag_sistemico` | Campo reservado para información externa al HRV que podría afectar la interpretación: calidad de sueño, viajes, enfermedad, etc. Actualmente no se alimenta automáticamente — está preparado para futuras integraciones. |
| 54 | `flag_razon` | Texto explicativo del flag sistémico (ej: "sueño <5h", "jet lag"). Vacío si no hay flag activo. |
| 55 | `warning_threshold` | Umbral efectivo usado por el warning legacy `baseline60_degraded`, según `warning_mode`. Se mantiene por compatibilidad y auditoría. |
| 56 | `warning_threshold_best` | Umbral fijo de mejor forma histórica usado por `degraded_vs_best` (`healthy_factor × healthy_rmssd`). |
| 57 | `warning_threshold_current_normal` | Umbral dinámico usado por `degraded_vs_current_normal` (`warning_factor × P75 rolling 90D` de `exp(ln_base60)`). |
| 58 | `warning_mode` | Qué método se usó para calcular el warning legacy `baseline60_degraded`. `adaptive90` = alias de `degraded_vs_current_normal` (default). `healthy85` = alias de la comparación contra mejor forma histórica. `p20` = percentil 20 del histórico completo. |

#### K) v4 Enhancement

| Columna | Qué es |
|---------|--------|
| `veto_agudo` | ¿Se activó el bypass de ROLL3 por caída aguda? True si tu lnRMSSD crudo de hoy cayó más de 2×SWC por debajo de tu baseline (una caída demasiado brusca para que ROLL3 la suavice sin peligro). Cuando se activa, `lnRMSSD_used` y `HR_used` se fuerzan al dato crudo del día en vez del promedio de 3 días. Esto hace que el gate refleje la caída inmediatamente. |
| `ln_pre_veto` | El valor de lnRMSSD_used (ROLL3) que tenías antes de que el veto lo sobrescribiera. Permite auditar cuánto habría enmascarado el suavizado: la diferencia `ln_pre_veto - lnRMSSD_used` muestra lo que ROLL3 estaba "ocultando". NaN si no hubo veto. |
| `swc_ln_floor` | El SWC efectivo que se usó para evaluar el veto: `max(SWC_ln, 0.04879)`. El floor de 0.04879 (= ln(1.05)) garantiza que el umbral del veto nunca sea trivialmente pequeño, evitando falsos positivos en periodos de variabilidad muy baja. NaN si no se calculó BASE60. |
| `recovery_context_quality` | Disponibilidad de datos de recuperación (sueño + carga). `none` = solo gate, sin contexto externo; `basic` = hay sueño básico y/o carga reciente; `rich` = además hay señal nocturna rich (`polar_sleep_score` y/o `polar_night_rmssd`). Sirve para no exagerar la precisión de interpretaciones sin soporte externo. |
| `recovery_support_class` | Lectura resumida de cómo encajan gate, sueño Polar y carga reciente. `supported` = el contexto externo acompaña la lectura; `neutral` = no añade gran cosa o está mezclado; `fragile` = el gate sale razonable pero sueño/carga meten cautela; `conflicted` = el gate sale mal pero sueño/carga no lo explican bien. No cambia la acción por sí mismo. |
| `recovery_discordance_flag` | True cuando el análisis de recuperación detecta una tensión entre el gate y el soporte externo (sueño/carga). Se activa en clases `fragile` (contexto débil) y `conflicted` (contexto contradictorio). |
| `recovery_discordance_reason` | Códigos estructurados que explican la discordancia. Ejemplos: `sleep_basic_poor`, `nightly_rmssd_low`, `load_context_high`, `sleep_score_good`, `recent_load_low`. Pensado para auditoría o análisis posterior. |
| `reason_text` | Texto explicativo contextual que combina información del gate con datos de sueño y carga. Múltiples razones separadas por ` \| `. Ver tabla de familias de mensajes a continuación. Internamente se renderiza a partir de `reason_items` estructurados (dato medido, proxy, inferencia, acción); no existe columna pública `reason_items_json` en `FINAL` ni en `DASHBOARD`, pero hay un sidecar estructurado `ENDURANCE_HRV_master_FINAL_reason_items.json` (descrito más abajo). El wellness subjetivo de Intervals queda fuera de `reason_text` y se reserva para capas retrospectivas. **No recolorea** el gate — es contexto para tu decisión. |

##### Familias de mensajes que pueden aparecer en `reason_text`

| Familia | Origen de datos | Ejemplos de mensaje |
|---------|------------------|----------------------|
| Caída aguda | `veto_agudo = True` | `RMSSD de hoy cayó bruscamente respecto a tu base reciente: superó el umbral de caída aguda` |
| HRV inusualmente alta | `lnRMSSD_used` fuera del rango habitual de la media móvil 3d | `RMSSD suavizado de 3 días por encima de tu base reciente: posible saturación parasimpática relativa al rango local` |
| Sueño (duración) | `sleep.csv` (percentiles personales `sleep_dur_p10/p90`) | `Sueño más corto de lo habitual (5h45 vs tu umbral habitual bajo de 6h02)` · `Noche larga atípica` |
| Sueño (fragmentación) | `sleep.csv` (`sleep_int_p90`) | `Sueño más fragmentado de lo habitual (8 interrupciones largas sobre tu P90)` |
| Carga aguda | `sessions_day.csv` (`acute_load_72h_rel`) | `Carga aguda 72h por encima de tu base crónica (acute_load_72h_rel=4.20x; load_3d=237)` |
| Carga canónica | `sessions_day.csv` (`acwr_simple_prev`, `monotony_7d_prev`, `strain_7d_prev`) | `ACWR muy alto: carga aguda muy por encima de la base crónica (1.69)` · `Monotonía alta` · `Strain semanal elevado` |
| Convergencia de carga | Convergencia `acute_load_72h_rel` + al menos una canónica | `VERDE con convergencia de carga (carga 72h + ACWR/monotonía/strain): conviene prudencia con la intensidad reforzada` |
| Clustering de intensidad | `sessions_day.csv` (`intensity_clustering_*`) | `VERDE pero con 2 días intensos en los últimos 3: conviene prudencia con la intensidad` · `Intensidad reciente muy agrupada: vigilar recuperación` |
| Resumen de recuperación | `recovery_support_class` | `VERDE con recuperación frágil...` · `ÁMBAR con soporte nocturno aceptable...` · `ROJO con discordancia objetiva...` |
| Nightly RMSSD discordante | `polar_night_rmssd` vs gate matinal | `Nightly RMSSD bajo pese a gate verde: vigilar` |

### Sidecar estructurado para analysis

Existe el sidecar `ENDURANCE_HRV_master_FINAL_reason_items.json`, que serializa por fecha los `reason_items` usados internamente para construir `reason_text`.

`analysis/` consume ese sidecar y deriva:
- `final_reason_items`: items normalizados listos para lectura semántica,
- `final_reason_flags`: flags agregados de cautela/tensión,
- `final_reason_items_contract`: disponibilidad, conformidad y fallback,
- `narrative_targets.final_reason_rendered`: capa narrativa local para informes de sesión.

### `narrative_targets.final_reason_rendered` (solo analysis)

No forma parte del contrato global de `FINAL`, pero sí del contrato local de `analysis/session_payload.json`.

Campos relevantes:
- `items[]`: lista renderizada por item, preservando el `message` cuantificado original.
- `items[].signal_kind`: naturaleza de la señal ya resuelta por Python.
  - `temporal_density`: densidad temporal de días duros, como `intensity_clustering`.
  - `accumulated_load`: carga acumulada reciente, como `green_load_caution`, `acwr`, `monotony` o `strain`.
  - `precision_modifier`: modulador de precisión interpretativa, como `baseline60_degraded`.
- `baseline_modifier`: lectura separada cuando `baseline60_degraded = true`; en `analysis/` debe leerse como rebaja de precisión, no como veto operativo por sí sola.

Artefacto complementario:
- `artifacts/report_sync_status.json`: estado de sincronización del `report.md` humano.
  - `status`: `missing`, `unmanaged_legacy`, `stale`, `up_to_date`.
  - `current_token`: token calculado desde `session_payload.json`, `summary.json` y `technical_report.md`.
  - `report_token`: token encontrado en `report.md`, si existe.

Regla de trazabilidad:
- si `final_reason_items_contract.fallback_to_reason_text = false`, los informes de `analysis/` deben tratar este sidecar como fuente estructurada activa y pueden declararlo explícitamente en `Fuentes`.
- si `report_sync_status.status != up_to_date`, el `report.md` debe considerarse no alineado con la regeneración técnica más reciente.

---

## 4. DASHBOARD (vista operativa) — 10 columnas

Subconjunto de FINAL para mirar en 10 segundos. Solo lo esencial para decidir qué hacer hoy.

| Columna | Qué mirar |
|---------|-----------|
| `Fecha` | Día de la medición. |
| `Calidad` | Primera parada: si es INVALID, ignora el resto. Si es FLAG_mecánico, prudencia. |
| `HR_today` | Tu pulso matinal de hoy. Útil para detectar de un vistazo si algo va raro (ej: 58 lpm cuando tu normal es 48). |
| `RMSSD_stable` | Tu variabilidad de hoy en ms. Sirve como referencia rápida, pero no tomes decisiones comparando este número entre días — para eso está el gate. |
| `gate_badge` | **Tu semáforo completo**: el color final (VERDE/ÁMBAR/ROJO/NO) + el sufijo del residual (+/-). Es lo primero que debes mirar después de descartar INVALID. Ejemplo: `VERDE+` = todo bien y HRV mejor de lo esperable. `ROJO--` = señal clara de estrés/fatiga. |
| `Action` | **Qué hacer hoy**: INTENSIDAD_OK (adelante), Z2_O_TEMPO_SUAVE (sin intervalos), SUAVE_O_DESCANSO (regenerativo o parar). |
| `gate_razon_base60` | Por qué salió ese color. 2D_OK = todo dentro de rango. 2D_LN = HRV baja. 2D_HR = pulso alto. 2D_AMBOS = las dos cosas → máxima confianza de fatiga. |
| `decision_path` | Si el gate fue ajustado por una sombra (BASE28 o BASE42) aparece aquí. Si dice BASE60_ONLY, no hubo override. |
| `baseline60_degraded` | Warning a medio plazo legacy. Para lectura nueva, distinguir `degraded_vs_best` (lejos de mejor forma) de `degraded_vs_current_normal` (caída activa reciente). |
| `reason_text` | Contexto textual del día: por qué el sistema tomó esa decisión y qué factores externos hay (sueño, carga, divergencias). El wellness subjetivo no entra en esta capa. Vacío si no hay nada que reportar. |

---

## 5. BETA_AUDIT (forense V3) — 13 columnas

Conservado para comparación histórica con el sistema anterior (V3). **No afecta al decisor FINAL/DASHBOARD.**

### Columnas compartidas con CORE (1–5)

Las 5 primeras columnas se copian tal cual de CORE. Ver §2 para el detalle completo.

| # | Columna | Qué es (resumen) |
|---|---------|------------------|
| 1 | `Fecha` | Día de la medición matinal (YYYY-MM-DD). Clave primaria. |
| 2 | `HR_stable` | Pulso medio en el tramo estabilizado (lpm). |
| 3 | `RRbar_s` | Intervalo RR medio en el tramo estable (segundos). |
| 4 | `RMSSD_stable` | Variabilidad cardiaca principal (ms). |
| 5 | `lnRMSSD` | Logaritmo natural de `RMSSD_stable` (adimensional). |

### Columnas específicas de BETA_AUDIT (6–13)

| # | Columna | Qué es |
|---|---------|--------|
| 6 | `cRMSSD` | RMSSD "corregido" por la relación natural entre pulso y variabilidad. Descuenta el efecto de que si tu pulso sube, tu RMSSD baja naturalmente (sin que haya fatiga). En V3 era el indicador principal; en el decisor FINAL/DASHBOARD lo sustituye el Gate 2D, que compara ambas señales simultáneamente en lugar de corregir una por la otra. |
| 7 | `beta_mode` | Estado del modelo alométrico (→ §10) que calcula la corrección. `active` = funcionando normal. `clipped` = el coeficiente beta salió fuera del rango plausible [0.1, 3.0] y se recortó. `frozen` = el modelo era inestable (R² bajo o salto grande), se usó el valor del día anterior. `none` = no había suficiente historial para estimar beta. |
| 8 | `beta_est_90d` | El coeficiente beta estimado con los últimos 90 días. Indica cuánto cambia tu HRV por cada cambio unitario en tu pulso (en escala logarítmica). Típicamente entre 0.5 y 2.0. |
| 9 | `beta_use_90d` | El beta realmente usado para la corrección. Puede diferir de beta_est si hubo clipping o freezing. |
| 10 | `R2_winsor_90d` | Calidad del ajuste del modelo alométrico (R² de la regresión winsorizada; → §10). Valores >0.30 indican buena relación lineal entre ln(RR) y ln(RMSSD). Valores bajos sugieren que el modelo beta no captura bien tu fisiología en ese periodo. |
| 11 | `Color_Agudo_Diario` | El color del sistema V3 para el día (equivalente al gate diario, pero basado en cRMSSD en vez de gate 2D). Solo para comparación histórica. |
| 12 | `Color_Tendencia` | El color de tendencia del V3 (basado en media móvil de cRMSSD). Indicaba si la dirección a medio plazo era buena o mala. |
| 13 | `Color_Tiebreak` | El color de desempate del V3: cuando agudo y tendencia discrepaban, este decidía. |

---

## 5bis. CONTEXT (sidecar externo) — 17 columnas

Actualizado en el flujo diario coordinado por `polar_hrv_automation.py`, con persistencia en `hrv_app.sleep_store`. Contiene datos de sueño y recuperación nocturna de Polar. Alimenta el `reason_text` pero **NO afecta al gate ni a la acción**. La ingestión prueba primero la fecha exacta y, si Polar no devuelve datos para ese día, consulta el día anterior como fallback operativo para no perder cobertura por desplazamientos de medianoche o latencia de sincronización.

**La carga de entrenamiento ya NO está en sleep.csv.** Está en `sessions_day.csv` (generado por `build_sessions.py`), que tiene datos más ricos: work blocks, zonas con moving mask, rolling con cobertura real (_nobs). El `reason_text` lee carga de sessions_day.csv y sueño de sleep.csv.

### ¿Para qué sirve?

El gate 2D solo ve HRV y pulso. Pero a menudo quieres saber *por qué* tu HRV bajó: ¿dormiste mal? ¿acumulaste mucha carga? ¿o no hay explicación obvia? Sleep.csv aporta la pieza del sueño. Sessions_day.csv aporta la pieza de carga. Ninguna interfiere en la decisión automática.

### Polar Sleep (lo que pasó durante la noche)

| Columna | Qué es | Valores típicos |
|---------|--------|----------------|
| `polar_sleep_duration_min` | Minutos de sueño real (sin despertares) | 360-480 (6-8h) |
| `polar_sleep_span_min` | Minutos totales en cama (con despertares) | 400-510 |
| `polar_deep_pct` | % de sueño profundo (N3). Solo con Sleep Plus Stages (~18% cobertura) | 15-25% |
| `polar_rem_pct` | % de sueño REM. Solo con Sleep Plus Stages (~18% cobertura) | 18-25% |
| `polar_efficiency_pct` | Eficiencia: tiempo dormido / tiempo en cama × 100 | 85-95% |
| `polar_continuity` | Clase cualitativa de continuidad del sueño Polar (1 = más fragmentado/discontinuo, 5 = más continuo). Categoría textual que Polar asigna al tramo nocturno. | 1-5 |
| `polar_continuity_index` | Índice numérico de continuidad del sueño Polar. Equivalente numérico de `polar_continuity`. | 1-5 |
| `polar_interruptions_long` | **Conteo** de interrupciones largas (⚠️ NO es duración). P90 personal ≈ 8 | 0-15 |
| `polar_interruptions_total` | Conteo total de interrupciones (largas + cortas) | 10-40 |
| `polar_sleep_score` | Score Polar (0-100). Solo con Nightly Recharge (~18% cobertura) | 60-90 |
| `polar_night_rmssd` | RMSSD nocturno medio (ms). Complementa el RMSSD matinal — si el nocturno es alto pero el matinal bajo, hay un confusor post-despertar | 20-60 |
| `polar_night_rri` | RR intervalo medio durante la noche (ms). Informativo; útil como referencia cruzada con `polar_night_rmssd`. | 900-1300 |
| `polar_night_resp` | Frecuencia respiratoria media durante la noche (rpm). Informativo; elevaciones sostenidas pueden acompañar a estrés o enfermedad. | 12-18 |

### Percentiles propios (tus umbrales personalizados)

| Columna | Qué es |
|---------|--------|
| `sleep_dur_p10` | Debajo de este valor = sueño más corto de lo habitual para ti. Se calibra con todo tu histórico |
| `sleep_dur_p90` | Encima = noche excepcionalmente larga |
| `sleep_int_p90` | Encima = noche fragmentada para TI |

**Si el sleep.csv no existe o Polar API falla:** El gate y la acción no se ven afectados. Solo se pierden los avisos de sueño en reason_text. Los avisos de carga (de sessions_day.csv) siguen funcionando independientemente. Si la fecha exacta no devuelve datos, `sleep_store` intenta el día anterior antes de rendirse; si tampoco hay datos, entonces el sidecar queda vacío.

---

## 5ter. SESSIONS_DAY (carga diaria y clustering) — sidecar CSV

Generado por `build_sessions.py` como `ENDURANCE_HRV_sessions_day.csv`. No decide el color del día, pero aporta contexto estructurado para interpretar el gate y enriquecer `reason_text`.

### ¿Para qué sirve?

`sessions_day.csv` responde a preguntas que el gate HRV no puede responder por sí solo:

- ¿has acumulado mucha carga en pocos días?
- ¿la intensidad reciente está mal distribuida?
- ¿vienes de una semana monótona o muy exigente?
- ¿el verde de hoy llega con contexto de prudencia?

### Capa de clustering de intensidad

Estas columnas viven en `sessions_day.csv` y alimentan directamente el aviso proactivo de concentración temporal de sesiones intensas:

| Columna | Qué es | Cómo leerla |
|---------|--------|-------------|
| `intense_day` | Flag binario diario. Vale `1` si ese día hubo al menos una sesión con `intensity_category = work_intense`; `0` si no. | Es la semilla mínima de la capa proactiva. No mide cuánta intensidad hubo, solo si existió una sesión intensa. |
| `intense_days_prev_3d` | Conteo de `intense_day` en los 3 días previos, sobre calendario continuo y excluyendo el día actual. | Detecta apilamiento muy corto. Un valor `2` significa que en 2 de los últimos 3 días hubo sesión intensa. |
| `intense_days_prev_5d` | Conteo de `intense_day` en los 5 días previos, también excluyendo hoy. | Es la ventana principal del flag de clustering en la v1 actual. |
| `intensity_clustering_flag` | Flag binario de clustering reciente. Vale `1` si `intense_days_prev_5d >= 2`. | Señala que la intensidad reciente ya está lo bastante concentrada como para merecer contexto preventivo. |
| `intensity_clustering_level` | Severidad del clustering. `high` si `intense_days_prev_3d >= 2` o `intense_days_prev_5d >= 3`; `low` si solo activa el flag suave; vacío si no hay clustering. | `low` = aviso suave; `high` = apilamiento claro de intensidad. |

### Análisis enriquecido local (capas opcionales de `analysis/`)

Además del clustering básico, cuando el módulo `analysis/` procesa una sesión puede enriquecer el análisis con datos adicionales (terreno, potencia de carrera) y generar capas paralelas. Estos campos viven en `summary.json` (para auditoría) y en `session_payload.json` (para informes de sesión). **Para el significado semántico completo de estas capas experimentales, ver `analysis/ANALYSIS_DICTIONARY.md`:**

| Campo | Qué es | Cómo leerlo |
|-------|--------|-------------|
| `v1_snapshot` | Resumen del análisis de clustering básico para ese día, derivado de `sessions_day.csv`. | Sirve como línea base estable. Ver `analysis/ANALYSIS_DICTIONARY.md` para el detalle semántico. |
| `runaware_context` | Análisis enriquecido cuando hay datos de terreno/potencia (principalmente en trail run). | Experimental: no cambia el gate HRV ni reemplaza el clustering. Ver `analysis/ANALYSIS_DICTIONARY.md`. |
| `v1_shadow_comparison` | Comparación entre el clustering básico y el análisis enriquecido (si existe). | Resume convergencia, divergencia o falta de señal. Ver `analysis/ANALYSIS_DICTIONARY.md`. |
| `v1_shadow_history` | Histórico de concordancia entre análisis básico y enriquecido en sesiones previas del mismo tipo. | Herramienta de calibración, no de puntuación. Ver `analysis/ANALYSIS_DICTIONARY.md`. |
| `terrain_climb_hr_mean` | FC media en tramos de subida (cuando hay análisis de terreno). | Contexto cardiovascular del tramo dominante. Ver `analysis/ANALYSIS_DICTIONARY.md`. |
| `terrain_climb_vam_mean` | VAM (velocidad ascensional media) en subidas, cuando hay datos de terreno. | Contexto de ritmo vertical. Ver `analysis/ANALYSIS_DICTIONARY.md`. |
| `terrain_climb_power_mean` | Potencia media en subidas (cuando hay potencia de carrera disponible). | Contexto mecánico del tramo dominante. Ver `analysis/ANALYSIS_DICTIONARY.md`. |
| `strength_basis` | Condiciones observadas que justifican la confianza del análisis enriquecido. | Auditoría de por qué el análisis se marcó como "strong" o "exploratory". Ver `analysis/ANALYSIS_DICTIONARY.md`. |
| `runaware_severity_basis` | Umbrales y señales que explican la severidad del análisis enriquecido. | Auditoría de severidad: por qué es `high`, `low`, o `n/d`. Ver `analysis/ANALYSIS_DICTIONARY.md`. |

### Cómo leer la concordancia en `v1_shadow_comparison`

- `aligned` significa que el análisis básico y el enriquecido convergen en la misma conclusión.
- `divergent` significa que el análisis enriquecido propone algo distinto al básico; no implica automáticamente error, pero sí merece revisión si el contexto lo justifica.
- `insufficient` significa que no había señal comparable suficiente para cerrar la comparación.
- El histórico de concordancia es una herramienta de calibración, no una medida de intensidad ni de carga. Ver `analysis/ANALYSIS_DICTIONARY.md`.

### Semántica operativa de esta capa

- Es una **aproximación basada en el calendario de sesiones** (días intensos y su espaciado temporal), no un índice de carga basado en potencia.
- Usa calendario continuo: los días sin sesión cuentan como `0` para esta capa concreta.
- Siempre mira **días previos**, nunca incluye el día actual.
- En `FINAL`, el clustering se propaga con `ffill(limit=2)` (relleno hacia adelante de máximo 2 días sin sesión) para poder avisar en días HRV sin sesión si el apilamiento ocurrió ayer o anteayer.
- No recolorea el gate: solo añade contexto textual.

### Relación con `reason_text`

Cuando el clustering está activo, `reason_text` puede mostrar mensajes como:

- `VERDE pero con 2 días intensos en los últimos 3: conviene prudencia con la intensidad`
- `VERDE pero con 3 días intensos en los últimos 5: conviene prudencia con la intensidad`
- `Intensidad reciente agrupada: vigilar recuperación`
- `Intensidad reciente muy agrupada: vigilar recuperación`

La formulación exacta depende de:

- si el gate final salió `VERDE` o no,
- y de si el nivel es `low` o `high`.

### Capa canónica de carga

Además del clustering, `sessions_day.csv` sigue siendo la fuente de:

- `load_3d`
- `work_7d_sum`
- `z3_7d_sum`
- `acwr_simple_prev`
- `acute_load_72h_rel`
- `monotony_7d_prev`
- `strain_7d_prev`
- `load_ctx_ready` — `True` si hay ≥14 días con datos de carga en la ventana de 28 días; indica que `acwr_simple_prev`, `acute_load_72h_rel`, `monotony_7d_prev` y `strain_7d_prev` tienen historial suficiente para ser interpretables y entrar en `reason_text`.

Estas métricas explican *cuánta* carga hay. La capa de clustering explica si la intensidad reciente está **mal espaciada**.

### Capa de distribución rolling por familia (DO-02)

Estas columnas viven también en `sessions_day.csv` y describen **cómo** se repartió la intensidad en los `7` días previos (qué tan polarizada, qué tan concentrada en Z2), no cuánta carga hubo:

| Columna | Qué es | Cómo leerla |
|---------|--------|-------------|
| `dominant_family_prev_7d` | Familia deportiva dominante de la ventana `D-7..D-1` (`run_family`, `bike_family`, `hike_family`, `elliptical_family`). | Vacío si la ventana no tiene una dominancia clara. |
| `dominant_family_share_prev_7d` | Fracción de `moving_min` que aporta la familia dominante sobre el total elegible de la ventana. | Umbral operativo `>= 0.60` (≥60% del volumen). Si queda por debajo, la señal no se considera interpretable. |
| `n_sessions_usable_prev_7d` | Número de sesiones de esa familia con cobertura válida de zonas. | `0` significa que no hay señal utilizable aunque haya habido entrenamiento. |
| `distribution_signal_confidence_prev_7d` | Confianza de la señal rolling: `low`, `moderate`, `high`. | `low` = no usar para flag; `moderate/high` = la estructura ya es interpretable. |
| `polarisation_index_prev_7d` | Índice de polarización: `(Z1 + Z3) / max(Z2, 1.0)` usando porcentajes ponderados de la familia dominante. Cuanto más bajo, más concentración en Z2 (agujero negro de intensidad). | Es una señal contextual informativa, no afecta el gate. Alto = polarizada; bajo = dominada por Z2. |
| `intensity_blackhole_flag` | Flag operativo que marca una ventana con Z2 excesiva y poco soporte de Z1/Z3. | Solo puede ser `True` con confianza suficiente, al menos `2` sesiones usables, `dominant_family_share >= 0.60`, `dominant_family_duration >= 90` y `polarisation_index_prev_7d < 2.2`. |
| `intensity_blackhole_episode_id` | Identificador del episodio actual del flag. | Sirve para no contar cada día repetido como un evento nuevo. |
| `intensity_blackhole_episode_len` | Longitud total del episodio actual. | Cuenta filas consecutivas emitidas en `sessions_day.csv`, no días calendario consecutivos. |

### Semántica operativa de DO-02

- Usa ventana rolling causal `D-7..D-1`; nunca incluye el día actual.
- Se calcula desde `sessions.csv`, no proyectando directamente el sidecar semanal.
- La guarda de volumen `>= 90 min` se aplica a la familia dominante, no al total mezclado.
- La frecuencia útil se lee por episodios (`episode_id`), no por días activos.
- Si esta señal entra en `reason_text`, el mensaje no debe repetirse en todos los días del mismo episodio.

### Cómo leer la convergencia de carga en `reason_text`

Cuando el día sale `VERDE`, la capa de carga puede cerrar de tres formas:

- `VERDE con carga aguda 72h (acute_load_72h_rel=Xx; load_3d=Y): precaución con la intensidad`
  Uso: solo la señal aguda relativa de 72h dispara cautela.
- `VERDE con contexto de carga exigente: precaución con la intensidad`
  Uso: dispara la capa canónica (`ACWR`, `monotony` o `strain`) sin apoyo de `acute_load_72h_rel`.
- `VERDE con convergencia de carga (carga 72h + ACWR/monotonía/strain): precaución con la intensidad reforzada`
  Uso: convergen la señal aguda relativa y al menos una señal canónica. La conclusión no se repite dos veces; se sintetiza y se refuerza.

---

## 5quater. SESSIONS METADATA / TRAINING_AUDIT (sidecar JSON)

Generado por `build_sessions.py` como `ENDURANCE_HRV_sessions_metadata.json`. No afecta al gate HRV ni a `Action`, pero documenta **si la capa de sesiones es interpretable** antes de sacar conclusiones de carga, zonas o drift.

### ¿Para qué sirve?

Hay una diferencia importante entre:

- dato disponible,
- dato interpretable,
- y dato accionable.

`training_audit` existe para hacer esa separación explícita. Si faltan streams, hay zonas en `fallback`, o la cobertura de drift es parcial, la capa de sesiones puede seguir existiendo pero ya no merece el mismo grado de confianza para coaching o análisis fino.

### Bloques principales

| Campo | Qué es |
|-------|--------|
| `stream_sampling` | Canary técnico del sampling del stream HR. Si `assumed_1hz = false`, conviene desconfiar de métricas derivadas de conversiones `muestras -> minutos`. |
| `zones_source_dist` | Distribución global de origen de zonas. Si aparece `fallback > 0`, hay deportes o sesiones sin zonas de Intervals bien configuradas. |
| `training_audit.dataset_level` | Cobertura gruesa del dataset: cuántos deportes hay, cuántos días con sesión, cuántas sesiones aeróbicas y cuántos días tienen `load_ctx_ready`. |
| `training_audit.signal_level` | Calidad de señal de la capa de sesiones: cobertura de stream aeróbico, cobertura de drift, fallback de zonas y límites globales de interpretabilidad. |
| `training_audit.metric_level` | Estado operativo mínimo por métrica/capa: `load_context`, `zone_intensity`, `cardiac_drift`, `coaching_load`. No es texto narrativo; es una etiqueta estructural de confianza. |

### `training_audit.signal_level`

| Campo | Qué mirar |
|-------|-----------|
| `sampling_ok` | `true` si el dataset parece ~1 Hz y las conversiones de stream son razonables. `false` = warning técnico fuerte. |
| `aerobic_stream_coverage_pct` | Qué porcentaje de sesiones aeróbicas tiene stream utilizable. Si baja mucho, zonas/work blocks/drift pierden fuerza interpretativa. |
| `aerobic_drift_coverage_pct` | Qué porcentaje de sesiones aeróbicas tiene drift calculable. Si es parcial, el drift reciente existe pero no representa a toda la capa. |
| `zones_fallback_pct` | Qué porcentaje total de sesiones usa `zones_source = fallback`. Ayuda a distinguir una incidencia puntual de un problema estructural de configuración. |
| `fallback_sports` | Qué deportes están afectados por fallback de zonas. |
| `interpretability_limits` | Lista corta de límites globales del dataset, por ejemplo `stream_sampling_not_1hz`, `partial_aerobic_stream_coverage`, `partial_aerobic_drift_coverage`, `zones_fallback_present`. |

### `training_audit.metric_level.*.state`

| Valor | Significado |
|------|-------------|
| `high` | La capa tiene señal suficiente y la lectura puede tomarse como apoyo fuerte. |
| `contextual` | La métrica existe, pero debe leerse con prudencia. Sirve como contexto, no como apoyo fuerte. |
| `informational` | El dato existe más como traza técnica que como señal utilizable para interpretación fina. |
| `not_applicable` | Esa métrica/capa no aplica al dataset actual o a ese tipo de sesiones. |

### `training_audit.metric_level.*.reasons`

Lista de causas concretas de degradación. Ejemplos frecuentes:

- `load_context_not_ready`
- `limited_ready_days`
- `zones_fallback_present`
- `partial_aerobic_stream_coverage`
- `partial_aerobic_drift_coverage`
- `no_valid_drift_sessions`
- `stream_sampling_not_1hz`

### Qué NO debes hacer

- ❌ Usar `training_audit` para recolorear el gate HRV
- ❌ Interpretar `contextual` como "malo"; significa "usable con prudencia"
- ❌ Confundir un límite global del dataset con un problema de la sesión concreta

### Qué sí debes hacer

- ✅ Usar `training_audit` para decidir cuánta fuerza dar a zonas, drift, clustering y contexto de carga
- ✅ Tratar `interpretability_limits` como límites estructurales del dataset, no como un diagnóstico de una sesión concreta
- ✅ Dejar que el informe conversacional module el lenguaje usando estas etiquetas, en vez de reconstruir limitaciones a mano

---

## 5quinquies. INTENSITY_DISTRIBUTION_WEEKLY (sidecar CSV) — 21 columnas

Generado por `build_sessions.py` como `ENDURANCE_HRV_intensity_distribution_weekly.csv`. Una fila por combinación `(semana ISO lunes-domingo, deporte)`. **No afecta al gate HRV ni a `reason_text`** — es una capa de análisis retrospectivo o coaching externo.

### ¿Para qué sirve?

Responde preguntas que ni el gate HRV ni `sessions_day.csv` pueden responder por sí solos:

- ¿Fue esta semana realmente polarizada (mucho Z1 + algo de Z3) o en realidad todo fue Z2?
- ¿El ciclismo y el trail run tienen perfiles de distribución distintos en mi histórico?
- ¿Hay semanas dominadas por el "agujero negro" de intensidad (threshold), que sabotean adaptaciones sin generar fatiga HRV aparente?

### Columnas de identificación

| Columna | Qué es |
|---------|--------|
| `window_start` | Lunes de la semana ISO (YYYY-MM-DD). Punto de inicio de la ventana. |
| `window_end` | Domingo de la semana ISO (YYYY-MM-DD). Siempre `window_start + 6 días`. |
| `sport` | Deporte canónico: `bike`, `road_run`, `trail_run`, `elliptical`, `hike`. Otros deportes (fuerza, movilidad) no aparecen en este sidecar. |

### Volumen y cobertura

| Columna | Qué es |
|---------|--------|
| `n_sessions_total` | Número total de sesiones del deporte en esa semana. |
| `n_sessions_usable` | Sesiones con datos de zona (z1/z2/z3) completos y positivos. Las restantes existen pero no aportaron distribución. |
| `total_duration_min` | Minutos totales de las sesiones usables (`moving_min`). Si no hay `moving_min`, se usa la suma de zonas como proxy. |

### Zonas ponderadas por duración

| Columna | Qué es |
|---------|--------|
| `z1_total_min` | Minutos en Z1 (≤VT1) sumados en todas las sesiones usables de la semana. |
| `z2_total_min` | Minutos en Z2 (VT1–VT2). |
| `z3_total_min` | Minutos en Z3 (≥VT2). |
| `z1_pct_weighted` | Z1 como % del total de zonas (z1+z2+z3). Ponderación por minutos, no por conteo de sesiones. Suma exactamente 100% junto con z2 y z3. |
| `z2_pct_weighted` | Z2 como % del total de zonas. Un valor alto (≥50%) con z1 bajo indica "agujero negro" de intensidad. |
| `z3_pct_weighted` | Z3 como % del total de zonas. |

### Bloques de trabajo intenso

| Columna | Qué es |
|---------|--------|
| `work_total_min` | Minutos en bloques de trabajo estructurado (≥VT1 continuo) sumados en la semana. |
| `work_n_blocks` | Número total de bloques de trabajo en la semana. |
| `work_longest_min` | Bloque de trabajo más largo de la semana (minutos). |
| `work_avg_z3_pct_weighted` | Intensidad media de los bloques de trabajo: % Z3 promediado ponderando por duración de cada bloque. Indica si el trabajo fue sostenido cerca de VT2 o claramente por encima. |

### Mezcla de fuentes y categorías

| Columna | Qué es |
|---------|--------|
| `zones_source_mix` | Distribución de fuentes de zona en la semana. Formato `icu=N;fallback=N`. `fallback` indica sesiones sin zonas configuradas en Intervals.icu. |
| `intensity_category_mix` | Distribución de categorías de intensidad asignadas a cada sesión. Formato `easy=N;work_intense=N;work_steady=N`. |

### Clasificación de patrón

| Columna | Qué es |
|---------|--------|
| `distribution_pattern` | Etiqueta descriptiva de la semana: `polarized` (Z1 alto + Z3 real, Z2 mínimo), `pyramidal` (Z1 > Z2 > Z3 con diferencia ≥10%), `threshold` (Z2 domina — el agujero negro), `mixed` (sin patrón claro). Vacío si no hay sesiones usables. |
| `distribution_confidence` | Fiabilidad de la clasificación: `high` (≥3 sesiones usables, duración suficiente, zonas reales), `moderate` (2 sesiones o ligera degradación), `low` (1 sesión, duración < 90min, o zonas en fallback). Se degrada acumulativamente. |
| `distribution_notes` | Causas de degradación o limitación, separadas por `;`. Posibles valores: `too_few_sessions`, `minimum_weekly_support`, `partial_zone_coverage`, `too_few_usable_sessions`, `low_total_duration`, `zones_fallback_present`, `no_usable_zone_sessions`. |

### Lo que NO debes hacer

- ❌ Usar `distribution_pattern` para recolorear el gate HRV de ningún día de esa semana
- ❌ Interpretar `confidence=low` como "dato erróneo"; significa "insuficiente para una conclusión firme"
- ❌ Comparar patrones entre semanas de `confidence=low` como si fueran equivalentes a semanas de `confidence=high`
- ❌ Esperar que `z1_pct_weighted + z2_pct_weighted + z3_pct_weighted` sumen 100% con `total_duration_min` (las zonas se normalizan sobre su propia suma, no sobre el tiempo total de sesión)

### Lo que sí debes hacer

- ✅ Usar `distribution_confidence` para decidir cuánta fuerza dar a la etiqueta de patrón
- ✅ Priorizar semanas de `confidence=high` para comparar distribuciones entre deportes
- ✅ Detectar rachas de semanas `threshold` como señal de que estás entrenando demasiado en la zona "cómoda pero ineficiente"
- ✅ Revisar `zones_source_mix` si el patrón parece anómalo: puede que el deporte no tenga zonas bien configuradas en Intervals.icu

---

## 5sexies. WELLNESS_SUBJECTIVE (sidecar retrospectivo) — 17 columnas

Generado como `ENDURANCE_HRV_wellness_subjective.csv` a partir del wellness subjetivo reportado en Intervals.icu (capa retrospectiva de análisis). **NO alimenta `reason_text`** ni modifica el gate: es información complementaria reservada para revisiones semanales u offline.

### ¿Para qué sirve?

Guarda lo que tú mismo reportaste cada día (fatiga, estrés, ánimo, etc.) junto a su versión etiquetada categórica. Permite:

- cruzar el gate HRV con percepción subjetiva a posteriori,
- detectar divergencias (ej. VERDE con fatiga subjetiva alta durante varios días),
- habilitar futuras capas sin contaminar la decisión diaria.

### Columnas

| # | Columna | Qué es |
|---|---------|--------|
| 1 | `Fecha` | Día del reporte subjetivo (YYYY-MM-DD). Clave primaria. |
| 2 | `well_fatigue_raw` | Valor crudo de fatiga reportado en Intervals.icu. Escala original del campo. |
| 3 | `well_fatigue_label` | Etiqueta categórica derivada (ej. `low`, `moderate`, `high`). |
| 4 | `well_stress_raw` | Valor crudo de estrés reportado. |
| 5 | `well_stress_label` | Etiqueta categórica derivada. |
| 6 | `well_mood_raw` | Valor crudo de estado de ánimo. |
| 7 | `well_mood_label` | Etiqueta categórica derivada. |
| 8 | `well_motivation_raw` | Valor crudo de motivación. |
| 9 | `well_motivation_label` | Etiqueta categórica derivada. |
| 10 | `well_soreness_raw` | Valor crudo de agujetas / dolor muscular. |
| 11 | `well_soreness_label` | Etiqueta categórica derivada. |
| 12 | `well_injury_raw` | Valor crudo de lesión reportada. |
| 13 | `well_injury_label` | Etiqueta categórica derivada. |
| 14 | `well_comment_raw` | Comentario libre del día, tal cual lo escribiste. |
| 15 | `wellness_subjective_n_fields` | Cuántos campos subjetivos (de los 7 anteriores) tienen valor ese día. |
| 16 | `wellness_subjective_available` | `True` si ese día hay al menos un campo reportado con valor utilizable. |
| 17 | `wellness_subjective_coverage_7d` | Fracción de los últimos 7 días con wellness subjetivo disponible. Sirve como indicador de adherencia al reporte. |

### Lo que NO debes hacer

- ❌ Usar estas columnas para recolorear el gate HRV
- ❌ Inferir causalidad de un solo día (un mal día subjetivo no justifica decisiones sin contexto HRV)
- ❌ Mezclar estas etiquetas con `reason_text` — permanecen separadas intencionalmente

---

## 5septies. SESSIONS (histórico de sesiones) — 73 columnas (mapa)

Generado por `build_sessions.py` como `ENDURANCE_HRV_sessions.csv`. Es el **histórico canónico** de sesiones de Intervals.icu con zonas, bloques de trabajo, drift y métricas derivadas. No afecta al gate HRV, pero es la fuente a partir de la cual se construye `sessions_day.csv` (§5ter) y el sidecar semanal (§5quinque).

### Fuente canónica del detalle columna-a-columna

La especificación completa columna-a-columna vive en **`ENDURANCE_HRV_Sessions_Schema.md`** (revisión `r2026-04-20 v3.12`). Este diccionario no la duplica para evitar desincronizaciones.

### Mapa de bloques (73 columnas)

| Bloque | Rango aprox. | Columnas representativas |
|--------|--------------|--------------------------|
| Identificación | 1–7 | `session_id`, `route_id`, `Fecha`, `start_time`, `sport`, `sport_raw`, `source` |
| Zonas de referencia | 8–10 | `vt1_used`, `vt2_used`, `zones_source` |
| Volumen y geografía | 11–17 | `duration_min`, `moving_min`, `distance_km`, `elev_gain_m`, `elev_loss_m`, `elev_density`, `calories` |
| Cardiaco | 18–22 | `hr_mean`, `hr_max`, `hr_p95`, `average_cadence`, `hrr_drop_bpm` |
| Clima | 23 | `average_weather_temp` |
| Distribución por zonas | 24–29 | `z1_pct`, `z2_pct`, `z3_pct`, `z1_total_min`, `z2_total_min`, `z3_total_min` |
| Bloques de trabajo | 30–35 | `work_n_blocks`, `work_total_min`, `work_longest_min`, `work_avg_z3_pct`, `work_blocks_min`, `work_blocks_z3pct` |
| Late intensity + drift | 36–37 | `late_intensity`, `cardiac_drift_pct` |
| Mecánica y crosscheck Polar | 38–41 | `mechanics_source`, `polar_sport_raw`, `polar_start_delta_min`, `polar_duration_gap_min` |
| Potencia (run) | 42–45 | `run_power_available`, `run_power_mean`, `run_power_max`, `run_power_p95` |
| Durabilidad (mitades) | 46–56 | `speed_first_half`, `speed_second_half`, `cadence_first_half`, `cadence_second_half`, `polar_speed_available`, `polar_cadence_available`, `run_power_first_half`, `run_power_second_half`, `durability_applicable`, `speed_ratio`, `power_ratio` |
| Carga | 57–59 | `load`, `trimp`, `rpe` |

### Coste de sesión (`mecanico_score` y `coste_dominante`) — capa local de `analysis/`

Estos campos viven en `summary.json` dentro de cada report de `analysis/`. No forman parte de los CSV canónicos, pero alimentan la clasificación de coste que aparece en los informes de sesión.

| Campo | Valores | Qué significa |
|-------|---------|---------------|
| `cardio_score` | `0..3` | Coste cardiovascular/metabólico estimado. `3` = sesión con exposición cardíaca alta y sostenida (Z2+Z3 > 50%, hr_p95 > VT2). |
| `mecanico_score` | `0..3` | Coste musculoesquelético/locomotor. Calculado por deporte con lógica diferenciada. |
| `coste_dominante` | `cardiometabolico`, `mecanico`, `mixto`, `bajo_estimulo` | Clasificación final de la sesión. `cardio_score > mecanico_score` → cardiometabólico; iguales o ambos altos → mixto. |

**Lógica de `mecanico_score` por deporte:**

- **Trail/road run:** Se toma el máximo entre `mecanico_terreno_score` (basado en D+/h) y `mecanico_locomocion_score` (basado en bloques corribles sostenidos). Si ambos son `>= 2`, se suma `+1` (tope 3). Para trail existe además un **bonus técnico** (`+1`) si hay clustering de bloques con Z3 suficiente (`work_n_blocks >= 4` y `work_avg_z3_pct >= 25`, o `>= 3` bloques con `>= 20%` Z3 y `>= 20 min` de trabajo). El umbral de D+/h para activar el score de terreno es **220 para trail** y **400 para road** — diferencia explícita porque el coste mecánico real por metro de desnivel en trail es mayor. El bonus técnico no se aplica si `zones_source = fallback`.
- **Bike:** Máximo entre score de terreno (D+/h) y score de pedaleo (bloques sostenidos). Sin bonus técnico de trail.
- **Natación:** Basado en coste propulsivo y técnico; sin terreno.

**Cómo leer `mecanico_score` en trail:**
- `0–1`: coste mecánico bajo o terreno plano con poco trabajo sostenido.
- `2`: desnivel relevante (D+/h ≥ 220) o bloque corrible largo con continuidad.
- `3`: combinación de desnivel alto + continuidad + clustering de bloques duros en Z3; indica peaje mecánico real.

---

### `durability_hint` y `durability_hint_detail` — capa local de `analysis/`

Campo en `summary.json → composite_context.durability_context`. Clasifica cómo evolucionó la sesión dividida en tres tercios iguales de tiempo.

| Valor de `durability_hint` | Qué describe |
|---------------------------|--------------|
| `steady_easy` | Sesión subumbral con variaciones pequeñas en los tres tercios. Sin señal de fatiga ni degradación. |
| `terrain_confounded` | Trail o hike donde el perfil de terreno domina la lectura. No interpretar como fatiga lineal: el pico de FC o la caída de velocidad reflejan el trazado, no degradación fisiológica. |
| `negative_split_like` | Velocidad mejora del primer al último tercio. |
| `fade_like` | Velocidad cae y FC sube del primero al último tercio. Patrón compatible con fatiga acumulada. |
| `drift_like` | FC sube sin caída de velocidad equivalente. Patrón compatible con deriva cardíaca sostenida. |
| `stable` | Cambios menores en los tres tercios. Sesión sin patrón marcado de degradación ni mejora. |
| `mixed` | Patrón no clasificable claramente en ninguna categoría anterior. |

Cuando `durability_hint = terrain_confounded`, el campo `durability_hint_detail` añade la causa específica:

| Valor de `durability_hint_detail` | Causa |
|----------------------------------|-------|
| `terrain_confounded_hr_peak` | FC media más alta en el tercio central (típico de terreno con subida principal en la parte media de la sesión). |
| `terrain_confounded_speed_drop` | Caída de velocidad ≥ 10% sin subida equivalente de FC (típico de ascensos donde se corre más lento pero el esfuerzo cardíaco no sube proporcionalmente). |
| `terrain_confounded_mixed` | Combinación de las anteriores o patrón de terreno no encuadrable en las dos causas anteriores. |

**Regla operativa:** en `trail_run` y `hike`, si el perfil por tercios muestra un pico intermedio de FC o caída de velocidad que coincide con la sección de subida principal, preferir `terrain_confounded` sobre `drift_like`. Los tercios iguales en tiempo no equivalen a secciones fisiológicamente homogéneas cuando el trazado tiene desnivel concentrado.
| Percepción y derivados | 60–64 | `feel`, `icu_weighted_avg_watts`, `icu_joules_above_ftp`, `icu_max_wbal_depletion`, `decoupling` |
| Categorización e identidad de sesión | 65–68 | `intensity_category`, `effort_vs_recent`, `effort_vs_anchor`, `session_group` |
| Notas y contrato | 69–73 | `notes_raw`, `rpe_present`, `notes_present`, `pipeline_version`, `stream_dt_est` |

### `late_intensity` y `cardiac_drift_pct` — cols 36–37

| Campo | Qué es |
|-------|--------|
| `late_intensity` | `1` si la FC media de la segunda mitad de la sesión supera en ≥8 lpm a la primera mitad, solo en sesiones ≥40 min. Detecta sesiones donde el esfuerzo escala hacia el final (finish strong). `0` en el resto. No aplica a sesiones demasiado cortas. |
| `cardiac_drift_pct` | Porcentaje de deriva cardíaca calculada desde el stream HR: cuánto sube la FC media en la segunda mitad respecto a la primera, con la velocidad controlada. Requiere sesión ≥30 min. `None` si no hay suficientes datos. |

### `intensity_category` — col 65

Clasifica la sesión por la **estructura del trabajo sostenido** (bloques >VT1), no por la exposición bruta a Z3:

| Valor | Cuándo se asigna |
|-------|-----------------|
| `work_intense` | Hay ≥10 min de bloques de trabajo Y ≥15% de esos minutos en Z3. Indica sesión con esfuerzo estructurado de alta intensidad. |
| `work_steady` | Hay ≥20 min de bloques de trabajo Y <15% Z3. Trabajo aeróbico sostenido sin picos de alta intensidad. |
| `work_moderate` | Hay ≥5 min de bloques de trabajo, pero sin alcanzar los umbrales anteriores. Trabajo suave o corto. |
| `finish_strong` | No hay bloques de trabajo pero `late_intensity = 1`: la FC subió al final. Sesión que escala al cierre. |
| `easy` | Ninguna de las anteriores. Sesión aeróbica suave sin estructura de trabajo detectable. |
| `NA` | Deporte no aeróbico (fuerza, movilidad, etc.). |

### `effort_vs_recent` y `effort_vs_anchor` — cols 66–67

Comparan la carga (`load`) de esta sesión con el historial del mismo `session_group`:

| Campo | Valores | Qué mide |
|-------|---------|----------|
| `effort_vs_recent` | `above` / `typical` / `below` / `unknown` | Carga vs percentiles 25–75 de las sesiones del mismo grupo en los últimos 60 días (causal, shift-1). `unknown` si hay <5 sesiones previas. |
| `effort_vs_anchor` | `above` / `typical` / `below` / `unknown` | Carga vs percentiles 25–75 del **período de referencia fijo** (verano entrenamiento base). Permite comparar siempre con el mismo punto de referencia histórico. |

### `session_group` — col 68

Agrupa sesiones en familias funcionales para los cálculos de `effort_vs_recent` y `effort_vs_anchor`:

| Valor | Quién cae aquí |
|-------|----------------|
| `endurance_hard` | Sesiones aeróbicas con `intensity_category = work_intense`. |
| `endurance_moderate` | Sesiones aeróbicas con `work_steady` o `work_moderate`. |
| `endurance_easy` | Sesiones aeróbicas `finish_strong` o `easy`. |
| `strength_unknown` | Fuerza (sin clasificación de intensidad aeróbica). |
| `mobility` | Movilidad. |
| `other` | Otros deportes no clasificables. |

### `decoupling` — col 64

Valor de desacoplamiento aeróbico tomado directamente de Intervals.icu. Solo está presente cuando hay datos de potencia del dispositivo (`device_watts`); en el resto de sesiones queda `None`. Mide la divergencia progresiva entre esfuerzo (potencia/ritmo) y FC a lo largo de la sesión: valores altos indican que el sistema cardiovascular trabajó cada vez más para mantener el mismo output mecánico.

### `zones_source`

| Valor | Qué significa |
|-------|---------------|
| `icu` | Zonas configuradas en Intervals.icu para ese deporte. Son las zonas de referencia preferidas. |
| `fallback` | Intervals.icu no devolvió zonas configuradas para ese deporte o sesión. Se usaron los umbrales VT1/VT2 de algún deporte alternativo disponible, o valores por defecto. Las métricas de zona (z1/z2/z3, work blocks) existen pero son menos precisas. Señal de que conviene configurar las zonas en Intervals.icu para ese deporte. |

Para interpretación, reglas de cobertura y el contrato de cada columna, consultar `ENDURANCE_HRV_Sessions_Schema.md`.

---

## 6. Valores de gate_razon_base60 (y sombras)

| Valor | Significado | Resultado |
|------|-------------|-----------|
| `2D_OK` | Ambos deltas (HRV y HR) dentro de SWC: tu variabilidad y tu pulso están en tu rango normal. | VERDE |
| `2D_LN` | Solo lnRMSSD por debajo de SWC: tu variabilidad ha bajado pero tu pulso sigue normal. Señal parcial — puede ser ruido o inicio de fatiga. | ÁMBAR |
| `2D_HR` | Solo HR por encima de SWC: tu pulso está más alto de lo normal pero tu variabilidad se mantiene. Puede indicar sueño malo, estrés puntual, o deshidratación. | ÁMBAR |
| `2D_AMBOS` | Las dos señales fuera de SWC simultáneamente: HRV baja **y** pulso alto. Esta convergencia da alta confianza de estrés fisiológico real (fatiga, enfermedad, mala recuperación). | ROJO |
| `ROLL3_INSUF` | No hay 3 días clean recientes para calcular el suavizado. Suele ocurrir al inicio del histórico o tras rachas de días INVALID/FLAG. | NO |
| `BASE60_INSUF` | No hay al menos 30 días clean en la ventana de 60 días. El sistema no tiene suficiente referencia para calibrar tu "normal". | NO |
| `BASE42_INSUF` / `BASE28_INSUF` | La sombra correspondiente no tiene suficientes días clean (21 para BASE42, 14 para BASE28). La sombra no puede operar. | gate_shadowXX = NO |
| `SWC_NAN/0` | No se pudo calcular el umbral SWC (dispersión nula o datos insuficientes). Sin SWC no hay forma de decidir si un delta es ruido o señal. | NO |
| `CAL/STAB/ART/NaN` | Día descartado por problema de calidad: INVALID, Unstable severo, artefactos excesivos, o valores faltantes. | NO |

---

## 7. Valores de Flags (CORE)

| Flag | Qué ha pasado | Consecuencia |
|------|---------------|--------------|
| `LAT_NAN` | No se detectó ningún punto de estabilización en toda la grabación. La señal nunca dejó de moverse. Puede ser mecánico (banda suelta, movimiento) o fisiológico (activación simpática fuerte). | Fuerza `Calidad = FLAG_mecánico`. El día no será clean. |
| `ART_GT15` | Los artefactos (latidos marcados como offline, fuera de rango, o con saltos bruscos) superan el 15% del registro total. Hay suficiente señal para calcular métricas, pero con ruido significativo. | Impide `Calidad = OK`. El día será FLAG_mecánico como mínimo. |
| `ART_GT20` | Artefactos por encima del 20%. Demasiado ruido para confiar en cualquier métrica. | Fuerza `Calidad = INVALID`. Día perdido. |
| `STAB_TAIL_SHORT` | La cola de la grabación (últimos 120 s) tiene menos de 75 s de material utilizable o menos de 60 pares de latidos. No hay suficientes datos al final para verificar la estabilidad. | Fuerza `HRV_Stability = Unstable`. |
| `STAB_CV120_HIGH` | El coeficiente de variación de la cola (últimos 120 s) supera el 20%. Los intervalos RR al final de la grabación oscilan demasiado — la señal no se había estabilizado realmente. | Fuerza `HRV_Stability = Unstable`. |
| `STAB_LAST2_NAN` | No se pudo calcular RMSSD_stable_last2 (la variabilidad de la cola). Normalmente porque hay muy pocos pares de latidos válidos en los últimos 120 s. | Fuerza `HRV_Stability = Unstable`. |
| `STAB_LAST2_MISMATCH` | La variabilidad de la cola (RMSSD_stable_last2) discrepa más de un 15% con la del tramo completo (RMSSD_stable). Indica que la señal estaba cambiando significativamente al final de la grabación. | Fuerza `HRV_Stability = Unstable`. |
| `BETA_CLIPPED` | El coeficiente beta estimado cayó fuera del rango plausible [0.1, 3.0] y se recortó al límite más cercano. | Solo informativo (afecta a BETA_AUDIT, no al decisor FINAL/DASHBOARD). |
| `BETA_FROZEN` | El modelo beta era inestable (R² < 0.10 o salto respecto al día anterior > 0.15). Se usó el beta del día anterior en lugar del nuevo. | Solo informativo (afecta a BETA_AUDIT, no al decisor FINAL/DASHBOARD). |
| `BETA_NONE` | No había suficiente historial (< 60 días válidos en ventana de 90d, o variación de RR insuficiente) para estimar beta. | Solo informativo (afecta a BETA_AUDIT, no al decisor FINAL/DASHBOARD). |
| `RESCUE_MODE` | El procesamiento normal falló en algún punto, pero se consiguió rescatar las métricas básicas de CORE. El dato existe pero se generó sin el pipeline completo. | Solo informativo. Revisar Notes para detalles del fallo. |

---

## 8. decision_path (auditoría de "quién mandó")

| Valor | Qué pasó |
|------|----------|
| `BASE60_ONLY` | La decisión la tomó BASE60 solo, sin interferencia de las sombras. Es el caso habitual (modo O2) y el más frecuente. |
| `OVERRIDE_DOWN_28_2of3` | La sombra de 28 días llevaba al menos 2 de los últimos 3 días diciendo que el gate debería ser **peor** que lo que dice BASE60. El gate final se bajó 1 nivel (ej: de VERDE a ÁMBAR). |
| `OVERRIDE_UP_28_2of3` | La sombra de 28 días insistió 2 de 3 días en que el gate debería ser **mejor**. El gate final se subió 1 nivel (ej: de ÁMBAR a VERDE). |
| `OVERRIDE_DOWN_42_2of3` | Igual que el override de 28 pero usando la sombra de 42 días (se usa cuando BASE28 no está disponible). Gate bajado 1 nivel. |
| `OVERRIDE_UP_42_2of3` | Sombra de 42 días insiste en mejorar. Gate subido 1 nivel. |

Si no hay override, `override_reason` queda vacío.

---

## 9. Diagrama de flujo (cómo se decide cada mañana)

```
┌─────────────────────────────────────────┐
│  Abres DASHBOARD del día                │
└─────────────────┬───────────────────────┘
                  │
                  ▼
       ┌──────────────────────┐
       │ ¿Calidad = INVALID?  │
       └──────────┬───────────┘
                  │
         ┌────────┴────────┐
         │ SÍ              │ NO
         ▼                 ▼
    ┌─────────┐      ┌──────────────────────────┐
    │ No usar │      │ ¿quality_flag = True?     │
    │ HRV hoy │      └──────────┬───────────────┘
    └─────────┘                 │
                       ┌────────┴────────┐
                       │ SÍ              │ NO
                       ▼                 ▼
                  ┌──────────┐     ┌───────────────────────┐
                  │ SUAVE    │     │ Ver gate_badge        │
                  │ sin HIIT │     │ + Action              │
                  └──────────┘     └───────┬───────────────┘
                                           │
                                           ▼
                              ┌───────────────────────────┐
                              │ VERDE → INTENSIDAD_OK     │
                              │ ÁMBAR → Z2/TEMPO SUAVE    │
                              │ ROJO  → SUAVE/DESCANSO    │
                              │ NO    → SUAVE/DESCANSO    │
                              └───────────┬───────────────┘
                                          │
                                          ▼
                              ┌───────────────────────────┐
                              │ ¿decision_path ≠          │
                              │  BASE60_ONLY?             │
                              │ Si override → revisar     │
                              │ override_reason           │
                              └───────────┬───────────────┘
                                          │
                                          ▼
                              ┌───────────────────────────┐
                              │ ¿baseline60_degraded?     │
                              │ Si True → Warning         │
                              │ (no cambia Action)        │
                              └───────────┬───────────────┘
                                          │
                                          ▼
                              ┌───────────────────────────┐
                              │ ¿reason_text no vacío?    │
                              │ Si tiene texto → Leer     │
                              │ contexto (sueño, carga,   │
                              │ veto agudo, divergencias)  │
                              └───────────────────────────┘
```

Nota: `baseline60_degraded` es la señal legacy de lectura rápida. La lectura canónica nueva distingue `degraded_vs_best` (distancia a mejor forma histórica) y `degraded_vs_current_normal` (caída activa respecto a tu normal reciente).

---

## 10. Glosario de términos técnicos

### MAD (Median Absolute Deviation)
Medida de dispersión robusta: en vez de calcular la media y ver cuánto se alejan los datos (como hace la SD clásica), la MAD calcula la **mediana** y mide las desviaciones respecto a ella. ¿Ventaja? Un solo día con RMSSD disparado (por ejemplo, un artefacto no detectado) apenas mueve la MAD, mientras que la SD se distorsiona mucho. Por eso la usamos para calcular SWC y z-scores: necesitamos que una mala noche puntual no descalibre tus umbrales.

### SWC (Smallest Worthwhile Change)
El cambio mínimo que merece atención. Se calcula como `0.5 × SD robusta` (donde la SD robusta viene de MAD × 1.4826). Si tu lnRMSSD de hoy está a -0.03 de tu baseline y el SWC es 0.05, esa diferencia es **ruido** — no justifica cambiar el entrenamiento. Solo cuando el delta supera el SWC en la dirección negativa (HRV baja o HR alto) se enciende el ámbar o rojo. Cuanto más estable es tu histórico, más estrecho es el SWC y más sensible se vuelve el sistema.

### Shift-1 (ventanas históricas)
Regla fundamental: el día de hoy **nunca** entra en su propia ventana de comparación. Si hoy es 10 de febrero, BASE60 usa datos del 12 de diciembre al 9 de febrero. ¿Por qué? Porque si incluyeras el día que estás evaluando en la referencia, estarías contaminando la comparación: un día muy malo bajaría su propio baseline y parecería "menos malo" de lo que realmente es.

### Día clean (para ventanas)
No todos los días con medición entran en los cálculos de ROLL3 y baselines. Solo los **clean**: aquellos donde la medición fue fiable en todos los sentidos. Requisitos simultáneos:
- `Calidad = OK` (no FLAG_mecánico ni INVALID)
- `HRV_Stability = OK` (tramo final estable)
- `Artifact_pct ≤ 10%` (ruido bajo)
- `lnRMSSD` y `HR_stable` no NaN (señal completa)

Un día FLAG_mecánico **sí** genera gate y acción (con quality_flag=True), pero **no** contamina las ventanas de referencia. Así protegemos la calidad del baseline.

### quality_flag
"El dato existe, pero no me fío lo suficiente como para meter intensidad." Salta cuando el día es `FLAG_mecánico`, `Unstable`, o tiene `Artifact_pct > 15%`, pero no llega a ser INVALID. El sistema calcula el gate 2D igualmente (porque perder la señal de tendencia es peor que no tenerla), pero la acción se **fuerza a SUAVE** (`Action_detail = SUAVE_QUALITY`) independientemente del color. En la práctica: si el gate sale VERDE pero tienes quality_flag, no te lances a hacer intervalos — el dato que lo justifica no es fiable.

### ROLL3
Media móvil de los **últimos 3 días clean**. En vez de comparar contra el baseline con el dato crudo de hoy (que puede fluctuar mucho día a día), se suaviza promediando los 3 últimos días fiables. Esto filtra el ruido diario sin perder sensibilidad ante cambios reales: si llevas 2 días con HRV bajando y hoy también baja, ROLL3 lo refleja. Pero si ayer tuviste un pico raro y hoy estás normal, ROLL3 lo amortigua. Si no hay 3 días clean recientes, el gate queda como NO (`ROLL3_INSUF`).

### Veto agudo (bypass de ROLL3)
Mecanismo de seguridad que detecta cuando ROLL3 está **enmascarando una caída brusca**. Si ayer y anteayer estaban bien y hoy tu HRV se desploma, ROLL3 aún muestra un valor cercano al normal (promedia 2 buenos + 1 malo). El veto compara tu dato crudo de hoy directamente contra el baseline: si cae más de 2×SWC por debajo, fuerza `lnRMSSD_used = lnRMSSD_today` (dato crudo) y `HR_used = HR_today`, saltándose el suavizado. El gate se calcula entonces con tu estado real de hoy, no con el promedio.

### SWC_FLOOR
Mínimo garantizado para SWC_ln: `ln(1.05) ≈ 0.04879`. ¿Por qué? En periodos de variabilidad muy estable (todos los días casi iguales), SWC puede ser minúsculo, lo que haría que cualquier fluctuación trivial active gates o vetos. El floor asegura que el "cambio mínimo significativo" nunca sea menor que un ~5% de variación en RMSSD.

### Reason_text
Texto explicativo que combina información del gate con datos contextuales (sueño, carga). No modifica el gate — es un "comentario" que acompaña a la decisión automática. Puede decir cosas como "sueño más corto de lo habitual", "carga acumulada reciente alta", o "VERDE con fatiga acumulada: conviene prudencia". Si el sleep.csv no existe, solo se generan avisos basados en datos HRV (caída brusca de RMSSD de hoy respecto a la base reciente o RMSSD suavizado de 3 días por encima de la base reciente).

`reason_text` debe leerse como un render humano compacto del contexto operativo, no como el origen semántico primario. Internamente se construye desde `reason_items` que separan cuatro capas epistémicas:

- **dato medido**: valor directo de un sensor o CSV (ej. `sleep_dur_min`, `load_3d`).
- **proxy**: valor derivado que aproxima algo no medido directamente (ej. `acwr_simple_prev` como proxy de carga crónica).
- **inferencia**: conclusión obtenida combinando uno o más datos/proxies (ej. "carga convergente" cuando coinciden `load_3d` y `acwr`).
- **acción**: recomendación operativa que emerge de la inferencia (ej. "conviene prudencia con la intensidad").

Esa mejora es interna y de trazabilidad. El builder también publica un sidecar `ENDURANCE_HRV_master_FINAL_reason_items.json` con los `reason_items` estructurados por fecha para consumo de `analysis/`. El contrato público del CSV no cambia:

- `FINAL` sigue teniendo 62 columnas,
- `DASHBOARD` sigue teniendo 10 columnas,
- no existe `reason_items_json` público como columna en `FINAL` ni en `DASHBOARD`;
- el sidecar `ENDURANCE_HRV_master_FINAL_reason_items.json` sí existe y se usa como entrada estructurada de `analysis/`.

### Baseline 60d (BASE60)
Tu "normal reciente": la **mediana** de lnRMSSD y HR en los últimos 60 días (solo clean, shift-1). ¿Por qué mediana y no media? Porque la mediana ignora valores extremos puntuales: si en 60 días tuviste 2 días con HRV muy bajo por una gripe, la mediana apenas se mueve. La ventana de 60 días es un compromiso: lo bastante larga para ser estable, lo bastante corta para seguir adaptaciones reales (si mejoras por entrenamiento sostenido, el baseline sube). Necesita al menos 30 días clean para operar.

### Sombras (BASE42, BASE28)
Baselines de ventana más corta (42 y 28 días) que actúan como **vigías**: observan y alertan de cambios de régimen antes de que los detecte BASE60, pero no toman el mando (en modo O2). El término "sombra" es un calco del inglés *shadow* (como en *shadow system*: sistema paralelo que monitoriza sin gobernar).

¿Para qué sirven? BASE60 es intencionadamente lenta — si tu HRV lleva 3 semanas bajando progresivamente, BASE60 todavía "recuerda" los buenos días de hace 2 meses y puede pintarte VERDE cuando ya deberías estar en ÁMBAR. BASE28 detectaría esa tendencia antes. En modo O2 (default), solo informan. En modo O3, si la sombra insiste durante varios días consecutivos en que el gate debería ser peor (o mejor), puede ajustar el gate final ±1 nivel.

### Gate 2D
La regla de decisión que combina **dos señales**: lnRMSSD (variabilidad cardíaca) y HR (frecuencia cardíaca en reposo). ¿Por qué dos y no solo HRV? Porque a veces la HRV baja por razones mecánicas o posturales sin que haya fatiga real — pero si **además** el pulso sube, la convergencia de ambas señales da mucha más confianza. La lógica:
- Ninguna fuera de SWC → VERDE (todo normal)
- Solo HRV baja → ÁMBAR (señal parcial, prudencia)
- Solo HR alto → ÁMBAR (señal parcial, prudencia)
- Ambas fuera → ROJO (convergencia, señal fuerte de estrés/fatiga)

### Residual
Responde a la pregunta: "dado mi pulso de hoy, ¿mi HRV es mejor o peor de lo esperable?" Existe una relación natural entre pulso y HRV — cuando el pulso sube, la HRV tiende a bajar, y viceversa. El residual es lo que **sobra** después de descontar esa relación (mediante un modelo lineal entrenado con tus últimos 60 días clean). Si el residual es positivo, tu HRV está por encima de lo que predice tu pulso (buena señal). Si es negativo, por debajo (posible fatiga o estrés que no se explica solo por el pulso). Se expresa como sufijo (+/-) en `gate_badge` y **no recolorea** el gate — es un matiz para interpretar, no para decidir.

### Winsorización
Técnica para "domesticar" valores extremos sin eliminarlos: los datos por debajo del percentil 10 se igualan al P10, y los de arriba del P90 se igualan al P90. Es como decir "no te creo que tu RR de esa mañana fue 2.1 s, vamos a tratarlo como si fuera 1.5 s que es tu P90". Se usa en el cálculo de beta (BETA_AUDIT) y del residual para evitar que un par de días anómalos distorsionen toda la regresión.

### Z-score robusto
"¿Cuántas desviaciones estoy de mi normal?" Pero usando estadísticos robustos: mediana en vez de media, y MAD×1.4826 en vez de SD. El z-score clásico (con media y SD) es muy sensible a outliers — un solo día extremo cambia la referencia y las unidades. El z-score robusto da una medida más estable de "cuánto me he movido respecto a lo habitual".

### Beta (modelo alométrico)
Coeficiente que captura la relación natural entre tu pulso y tu HRV: cuando tu RR sube (pulso más lento), ¿cuánto sube tu RMSSD? Beta responde a eso. Se estima por regresión en espacio logarítmico (`ln(RMSSD) = a + beta × ln(RR)`) con datos de los últimos 90 días. Valores típicos: 0.5–2.0. Beta alto significa que tu HRV es muy sensible a cambios de pulso; beta bajo, que es relativamente estable. **Usado solo en BETA_AUDIT** como referencia forense del sistema V3 — no afecta al decisor FINAL/DASHBOARD.

### cRMSSD ("c" = corrected)
RMSSD "limpio" de la influencia del pulso: si tu pulso de hoy está más alto de lo normal, tu RMSSD bajará naturalmente (sin que haya fatiga real). cRMSSD usa beta para descontar ese efecto y quedarse solo con la variabilidad "genuina". **Usado solo en BETA_AUDIT** — el decisor FINAL/DASHBOARD usa el Gate 2D (que compara ambas señales simultáneamente) en lugar de corregir una por la otra.

### DFA α1 (análisis de fluctuaciones sin tendencia)
Métrica no lineal de la señal RR. Mide las correlaciones de escala corta en la serie de latidos: si α1 ≈ 1.0, la señal tiene correlaciones de largo alcance típicas de reposo; si α1 < 0.75, sugiere pérdida de complejidad asociada a estrés o fatiga; si α1 > 1.5, la señal tiende a comportarse como ruido browniano. DFA α1 no forma parte de los CSV canónicos (`CORE`, `FINAL`, `DASHBOARD`) pero aparece en `summary.json` de `analysis/` como métrica complementaria cuando hay suficientes latidos en la sesión.

### `zones_source = fallback`
Ver la sección "SESSIONS — `zones_source`" en §5septies. En resumen: indica que para esa sesión o deporte no había zonas VT1/VT2 configuradas en Intervals.icu y se usaron valores de respaldo. Las distribuciones z1/z2/z3 y los bloques de trabajo siguen existiendo pero son menos precisos. Visible también en `zones_source_dist` del metadata JSON (§5quater) y en `zones_source_mix` del sidecar semanal (§5quinquies).

---

## 11. Notas sobre latencia alta

### Causas mecánicas (más frecuentes)

- Movimiento, ajuste de postura, tensar piernas/abdomen
- Banda pierde contacto o hay micro-artefactos
- Frío, incomodidad, respiración irregular

### Causas fisiológicas reales

- Activación simpática al despertar (estrés, anticipación)
- Respiración muy variable (suspiros, apnea breve)
- Microdespertares o sueño fragmentado
- Estado inflamatorio / recuperación mala

### Por qué baja la confiabilidad

1. **Estás midiendo una transición, no un estado**: El inicio de la mañana es un periodo de ajuste
2. **Queda poco material estable**: Con 60-90s estables, el RMSSD es muy sensible al azar

### Procedimiento cuando la latencia sale alta

1. Mira si también sube `Artifact_pct` o aparece `STAB_*` en Flags
   - Si sí → más probable que sea mecánico
2. Repite la medición 10-15 min después (si puedes)
   - Si mejora → era transición/mecánico
   - Si sigue igual → probablemente fisiológico
3. No tomes decisiones de carga basadas solo en ese RMSSD
   - Usa el gate: si está flaggeado, interpretar con prudencia

---

## 12. Casos de ejemplo

### Caso 1: Día normal (VERDE)

```
Fecha: 2026-02-08
Calidad: OK
HR_today: 48.5
RMSSD_stable: 55.2
gate_badge: VERDE+
Action: INTENSIDAD_OK
Action_detail: EJECUTAR_PLAN
gate_razon_base60: 2D_OK
decision_path: BASE60_ONLY
baseline60_degraded: False
degraded_vs_best: False
degraded_vs_current_normal: False
```

**Interpretación:** Gate OK, ambos deltas dentro de SWC, residual ligeramente positivo. Ejecutar plan previsto.

### Caso 2: Fatiga real (ROJO)

```
Fecha: 2026-01-15
Calidad: OK
HR_today: 58.3
RMSSD_stable: 28.4
gate_badge: ROJO--
Action: SUAVE_O_DESCANSO
Action_detail: DESCARGA
gate_razon_base60: 2D_AMBOS
decision_path: BASE60_ONLY
bad_streak: 2
bad_7d: 3
baseline60_degraded: True
degraded_vs_best: True
degraded_vs_current_normal: True
```

**Interpretación:** HR alto + HRV bajo simultáneamente, residual muy negativo, racha de 2 días malos, 3 en 7 días, baseline degradado. Señales claras de fatiga acumulada → descarga.

### Caso 3: Solo HR alto (ÁMBAR)

```
Fecha: 2026-02-01
Calidad: OK
HR_today: 56.2
RMSSD_stable: 48.5
gate_badge: ÁMBAR
Action: Z2_O_TEMPO_SUAVE
Action_detail: SIN_HIIT
gate_razon_base60: 2D_HR
decision_path: BASE60_ONLY
baseline60_degraded: False
degraded_vs_best: False
degraded_vs_current_normal: False
```

**Interpretación:** HR por encima de lo normal pero HRV dentro de rango. Posible sueño malo o estrés puntual. Sin HIIT, pero Z2 permitido.

### Caso 4: Dato con quality_flag (VERDE forzado a SUAVE)

```
Fecha: 2026-02-05
Calidad: FLAG_mecánico
HR_today: 47.8
RMSSD_stable: 58.1
gate_badge: VERDE
Action: SUAVE_O_DESCANSO
Action_detail: SUAVE_QUALITY
quality_flag: True
gate_razon_base60: 2D_OK
decision_path: BASE60_ONLY
```

**Interpretación:** Gate pintaría VERDE, pero quality_flag=True (FLAG_mecánico) fuerza acción a SUAVE. No se confía en el dato para justificar intensidad.

### Caso 5: Veto agudo + contexto (ROJO con explicación)

```
Fecha: 2026-02-07
Calidad: OK
HR_today: 55.1
RMSSD_stable: 30.2
gate_badge: ROJO
Action: SUAVE_O_DESCANSO
Action_detail: SUAVE
gate_razon_base60: 2D_AMBOS
decision_path: BASE60_ONLY
veto_agudo: True
reason_text: RMSSD de hoy cayó bruscamente respecto a tu base reciente: superó el umbral de caída aguda | Sueño más corto de lo habitual (5h45 vs tu umbral habitual bajo de 6h02) | Carga aguda 72h por encima de tu base crónica (acute_load_72h_rel=4.20x; load_3d=237)
```

**Interpretación:** El veto agudo detectó una caída brusca que ROLL3 habría suavizado. El `reason_text` explica tres factores convergentes: la caída fue real, dormiste poco, y acumulaste mucha carga. Alta confianza de que el ROJO es legítimo.

### Caso 6: VERDE con convergencia de carga

```
Fecha: 2026-02-10
Calidad: OK
HR_today: 47.2
RMSSD_stable: 52.8
gate_badge: VERDE+
Action: INTENSIDAD_OK
Action_detail: EJECUTAR_PLAN
gate_razon_base60: 2D_OK
decision_path: BASE60_ONLY
veto_agudo: False
reason_text: ACWR muy alto: carga aguda muy por encima de la base crónica (1.69) | VERDE con convergencia de carga (carga 72h + ACWR): precaución con la intensidad reforzada
```

**Interpretación:** Tu HRV y pulso están bien (VERDE), pero la lectura operativa no es un verde limpio. La carga aguda de 3 días y el ACWR apuntan en la misma dirección, así que el cierre de `reason_text` escala la cautela: el gate permite intensidad, pero no justifica exprimirla.

---

## 13. "Para tontos" (muy llano)

- **BASE60** = tu "normal" de los últimos ~2 meses (sin contar hoy).
- **Gate** = compara tu HRV (lnRMSSD) y tu pulso (HR) contra ese normal.
- **ROLL3** = suavizado de los últimos 3 días buenos, para filtrar ruido.
- **Veto agudo** = si hoy tu HRV se desploma pero ROLL3 lo enmascara, el veto salta y usa el dato crudo.
- **Sombras (28/42)** = miran si tu normal "reciente" está cambiando antes de que lo vea BASE60.
- **Residual** = "¿para este pulso, tu HRV está mejor o peor de lo esperable?"
- **quality_flag** = "el dato de hoy es sospechoso": aunque pinte bonito, **no toca apretar**.
- **reason_text** = "te explico por qué": sueño malo (de Polar), carga alta o convergente (de `sessions_day`), caída aguda de HRV, clustering reciente, etc. **No cambia el gate**, solo informa.

---

Fin del documento.


