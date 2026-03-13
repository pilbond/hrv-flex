# ENDURANCE HRV — Diccionario de Columnas (V4-lite)

**Revisión:** r2026-03-01 v4.1 (context simplificado + sessions pipeline)  
**Estado:** Producción

**Documentos relacionados:**
- `ENDURANCE_HRV_Spec_Tecnica.md` — especificación técnica (fórmulas y reglas)
- `ENDURANCE_HRV_Estructura.md` — contrato de datos (columnas y orden exacto)

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
| 10-20% | Límite (FLAG_mecánico) |
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

Generado por `endurance_hrv.py`. Contiene la señal fisiológica **sin decisiones**.

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
| `SI_baevsky` | Índice de estrés de Baevsky. Resume la compactación del histograma RR y suele aumentar cuando la señal apunta a mayor rigidez o carga simpática. En este pipeline queda como señal complementaria, útil para auditoría o análisis futuro. | Informativo; no afecta al gate V4-lite |
| `SD1` | SD1 del diagrama de Poincare. Captura la variabilidad de corto plazo, muy relacionada con la misma dinámica que refleja RMSSD. Sirve como métrica adicional para leer la forma de la nube RR. | Informativo |
| `SD2` | SD2 del diagrama de Poincare. Captura la variabilidad de más largo plazo dentro de la serie RR estable. Ayuda a distinguir si la señal cambia solo beat-to-beat o también en una escala algo más lenta. | Informativo |
| `SD1_SD2_ratio` | Relación entre la variabilidad rápida (`SD1`) y la más lenta (`SD2`). Útil para interpretar la "geometría" del Poincare y detectar patrones menos visibles si solo miras RMSSD. | Informativo |

### Trazabilidad

| Columna | Qué es |
|---------|--------|
| `Flags` | Lista de incidencias detectadas durante el procesamiento, separadas por `\|`. Cada flag indica un problema o condición específica: estabilidad, artefactos, latencia, modo beta, etc. Ejemplo: `LAT_NAN\|ART_GT10` significa que no se detectó estabilización y además los artefactos superaron el 10%. Si está vacío, no se detectaron incidencias relevantes. |
| `Notes` | Metadatos técnicos del procesamiento en formato `clave=valor`. Incluye el fichero fuente, duraciones de cada fase, conteos de latidos en cada etapa y desglose de artefactos por tipo. Está pensado para auditoría y depuración, no para lectura diaria. |

---

## 3. FINAL (gate + auditoría extendida) — 58 columnas

Generado por `endurance_v4lite.py`. Contiene:

- suavizado ROLL3 (solo días clean)
- baseline BASE60 + SWC
- **veto agudo** (bypass ROLL3 ante caídas bruscas)
- gate BASE60 (decisor)
- sombras BASE42 y BASE28 (informativas)
- override opcional (modo O3)
- residual (BASE60) + sufijo (`+/-`)
- acción + acumulación + warnings
- **reason_text** (contexto de sueño + carga)

### Lo mínimo que debes mirar a diario

- `gate_badge` (semáforo final + matiz)
- `Action` y `Action_detail`
- `reason_text` (contexto: sueño, carga, veto agudo)
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
| `SWC_ln` | El cambio mínimo significativo para lnRMSSD: `0.5 × SD robusta`. Si tu delta (d_ln) no supera este umbral, se considera ruido y el gate no se enciende por esa vía. Cuanto más estable hayas sido históricamente, más estrecho es este umbral (más sensible). |
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

| Columna | Qué es |
|---------|--------|
| `residual_ln` | La diferencia entre tu lnRMSSD real y el que predice un modelo lineal basado en tu pulso (RR). Si es positivo, tu HRV es más alta de lo que "debería" dado tu pulso — buena señal parasimpática. Si es negativo, tu HRV es más baja de lo esperable — posible fatiga o estrés que no se explica solo por el pulso. El modelo se entrena con tus últimos 60 días clean. |
| `residual_z` | El residual normalizado: cuántas "unidades SWC del residual" te has alejado de lo esperable. Permite interpretar la magnitud: un residual_z de -1.5 es más preocupante que -0.3. Se calcula con escala robusta (MAD) para no distorsionarse por días atípicos. |
| `residual_tag` | Sufijo visual que resume residual_z en categorías. `+` (≥0.5), `++` (≥1.0), `+++` (≥2.0) para residual positivo. `-` (≤-0.5), `--` (≤-1.0), `---` (≤-2.0) para negativo. Sin sufijo si está entre -0.5 y +0.5. |
| `gate_badge` | El semáforo final con el matiz del residual pegado. Ejemplo: `VERDE+` (todo bien y además tu HRV es mejor de lo esperable), `ÁMBAR--` (gate ámbar y además el residual es bastante negativo). Es la columna más informativa para echar un vistazo rápido al estado completo del día. |

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
| `quality_flag` | ¿El dato de hoy es sospechoso? True si la medición tiene algún problema de fiabilidad (FLAG_mecánico, Unstable, o artefactos >10%) pero no llega a ser INVALID. Cuando es True, la acción se fuerza a SUAVE aunque el gate pinte VERDE — no se confía en el dato para justificar intensidad. | True / False |
| `Color_operativo` | Duplicado explícito de gate_final, sin transformaciones ni capas intermedias. Existe para que no haya duda de qué color gobierna la acción. Si lees gate_final, es exactamente lo mismo. | VERDE / ÁMBAR / ROJO / NO |
| `Action` | La instrucción operativa del día: qué tipo de entrenamiento permite el gate. INTENSIDAD_OK = puedes ejecutar intervalos o sesiones duras. Z2_O_TEMPO_SUAVE = nada explosivo, pero puedes hacer volumen en zona aeróbica. SUAVE_O_DESCANSO = regenerativo o descanso total. | INTENSIDAD_OK / Z2_O_TEMPO_SUAVE / SUAVE_O_DESCANSO |
| `Action_detail` | Matiza la acción con contexto: EJECUTAR_PLAN (verde limpio, adelante con lo planificado), SIN_HIIT (ámbar, quita intensidad pero mantén volumen), SUAVE_QUALITY (el gate podría ser bueno pero el dato no es fiable), SUAVE (rojo puntual), DESCARGA (acumulación de rojos → reducir carga semanal). | EJECUTAR_PLAN / SIN_HIIT / SUAVE_QUALITY / SUAVE / DESCARGA |

Mapping:
- VERDE → `INTENSIDAD_OK` (salvo quality_flag)
- ÁMBAR → `Z2_O_TEMPO_SUAVE` (salvo quality_flag)
- ROJO/NO → `SUAVE_O_DESCANSO`

#### H) Acumulación

| Columna | Qué es |
|---------|--------|
| `bad_streak` | Cuántos días consecutivos llevas con gate ROJO o NO (sin un VERDE o ÁMBAR de por medio). Una racha de 1 es un mal día puntual. Una racha ≥2 activa DESCARGA en Action_detail — la señal de que no es un evento aislado. |
| `bad_7d` | Cuántos días ROJO o NO has tenido en los últimos 7 días (no necesariamente consecutivos). Si llega a ≥3, también activa DESCARGA. Captura la situación donde alternas días malos y regulares pero la tendencia semanal es negativa. |

#### I) Warning

| Columna | Qué es |
|---------|--------|
| `baseline60_degraded` | ¿Tu capacidad de absorción está reducida respecto a tu mejor momento? True si tu baseline actual (mediana de los últimos 60 días) está por debajo de un umbral de referencia. Es un aviso a medio plazo — no cambia el gate del día, pero sugiere que las decisiones de progresión semanal deberían ser conservadoras. |
| `healthy_rmssd` | Tu ancla de RMSSD "sano": la mediana de RMSSD durante un periodo en el que estabas bien entrenado y sin problemas. Sirve como referencia de lo que tu cuerpo puede dar en condiciones óptimas. Se define una vez y se mantiene fija. | 
| `healthy_hr` | Tu ancla de pulso "sano": la mediana de HR en reposo durante el mismo periodo de referencia. |
| `healthy_period` | El rango de fechas usado para calcular las anclas healthy (ej: "2025-07-01 a 2025-09-30"). |
| `warning_threshold` | El umbral concreto (en ms de RMSSD) por debajo del cual se activa el warning. En modo healthy85 es el 85% de tu healthy_rmssd. En modo p20 es el percentil 20 de tu histórico. |
| `warning_mode` | Qué método se usó para calcular el umbral de warning. healthy85 = basado en tu mejor periodo × 0.85. p20 = basado en el percentil 20 de tu histórico completo. | 

#### J) Flags sistémicos

| Columna | Qué es |
|---------|--------|
| `flag_sistemico` | Campo reservado para información externa al HRV que podría afectar la interpretación: calidad de sueño, viajes, enfermedad, etc. Actualmente no se alimenta automáticamente — está preparado para futuras integraciones. |
| `flag_razon` | Texto explicativo del flag sistémico (ej: "sueño <5h", "jet lag"). Vacío si no hay flag activo. |

#### K) v4 Enhancement

| Columna | Qué es |
|---------|--------|
| `veto_agudo` | ¿Se activó el bypass de ROLL3 por caída aguda? True si tu lnRMSSD crudo de hoy cayó más de 2×SWC por debajo de tu baseline (una caída demasiado brusca para que ROLL3 la suavice sin peligro). Cuando se activa, `lnRMSSD_used` y `HR_used` se fuerzan al dato crudo del día en vez del promedio de 3 días. Esto hace que el gate refleje la caída inmediatamente. |
| `ln_pre_veto` | El valor de lnRMSSD_used (ROLL3) que tenías antes de que el veto lo sobrescribiera. Permite auditar cuánto habría enmascarado el suavizado: la diferencia `ln_pre_veto - lnRMSSD_used` muestra lo que ROLL3 estaba "ocultando". NaN si no hubo veto. |
| `swc_ln_floor` | El SWC efectivo que se usó para evaluar el veto: `max(SWC_ln, 0.04879)`. El floor de 0.04879 (= ln(1.05)) garantiza que el umbral del veto nunca sea trivialmente pequeño, evitando falsos positivos en periodos de variabilidad muy baja. NaN si no se calculó BASE60. |
| `reason_text` | Texto explicativo contextual que combina información del gate con datos de sueño y carga. Múltiples razones separadas por ` \| `. Puede incluir: caída aguda HRV, noche corta/fragmentada (basado en tus percentiles, no en umbrales fijos), carga acumulada alta, fatiga profunda (TSB), saturación parasimpática, divergencias gate↔contexto. Vacío si no hay nada que reportar. **No recolorea** el gate — es contexto para tu decisión. |

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
| `baseline60_degraded` | Warning a medio plazo: True si tu baseline de los últimos 2 meses está por debajo de tu referencia "sano". No cambia el gate de hoy, pero avisa de que tu capacidad de absorción está reducida. |
| `reason_text` | Contexto textual del día: por qué el sistema tomó esa decisión y qué factores externos hay (sueño, carga, divergencias). Vacío si no hay nada que reportar. |

---

## 5. BETA_AUDIT (forense V3) — 13 columnas

Conservado para comparación histórica con el sistema anterior (V3). **No afecta al gate V4-lite.** Las primeras 5 columnas (`Fecha`, `HR_stable`, `RRbar_s`, `RMSSD_stable`, `lnRMSSD`) son idénticas a CORE y no se repiten aquí.

| Columna | Qué es |
|---------|--------|
| `cRMSSD` | RMSSD "corregido" por la relación natural entre pulso y variabilidad. Descuenta el efecto de que si tu pulso sube, tu RMSSD baja naturalmente (sin que haya fatiga). En V3 era el indicador principal; en V4-lite lo sustituye el Gate 2D, que compara ambas señales simultáneamente en lugar de corregir una por la otra. |
| `beta_mode` | Estado del modelo alométrico que calcula la corrección. `active` = funcionando normal. `clipped` = el coeficiente beta salió fuera del rango plausible [0.1, 3.0] y se recortó. `frozen` = el modelo era inestable (R² bajo o salto grande), se usó el valor del día anterior. `none` = no había suficiente historial para estimar beta. |
| `beta_est_90d` | El coeficiente beta estimado con los últimos 90 días. Indica cuánto cambia tu HRV por cada cambio unitario en tu pulso (en escala logarítmica). Típicamente entre 0.5 y 2.0. |
| `beta_use_90d` | El beta realmente usado para la corrección. Puede diferir de beta_est si hubo clipping o freezing. |
| `R2_winsor_90d` | Calidad del ajuste del modelo alométrico (R² de la regresión winsorizada). Valores >0.30 indican buena relación lineal entre ln(RR) y ln(RMSSD). Valores bajos sugieren que el modelo beta no captura bien tu fisiología en ese periodo. |
| `Color_Agudo_Diario` | El color del sistema V3 para el día (equivalente al gate diario, pero basado en cRMSSD en vez de gate 2D). Solo para comparación histórica. |
| `Color_Tendencia` | El color de tendencia del V3 (basado en media móvil de cRMSSD). Indicaba si la dirección a medio plazo era buena o mala. |
| `Color_Tiebreak` | El color de desempate del V3: cuando agudo y tendencia discrepaban, este decidía. |

---

## 5bis. CONTEXT (sidecar externo) — 17 columnas

Generado por `polar_hrv_automation.py` (fetch diario). Contiene datos de sueño y recuperación nocturna de Polar. Alimenta el `reason_text` pero **NO afecta al gate ni a la acción**.

**La carga de entrenamiento ya NO está en sleep.csv.** Está en `sessions_day.csv` (generado por `build_sessions.py`), que tiene datos más ricos: work blocks, zonas con moving mask, rolling con cobertura real (_nobs). El `reason_text` lee carga de sessions_day.csv y sueño de sleep.csv.

### ¿Para qué sirve?

El gate 2D solo ve HRV y pulso. Pero a menudo quieres saber *por qué* tu HRV bajó: ¿dormiste mal? ¿acumulaste mucha carga? ¿o no hay explicación obvia? Context.csv aporta la pieza del sueño. Sessions_day.csv aporta la pieza de carga. Ninguna interfiere en la decisión automática.

### Polar Sleep (lo que pasó durante la noche)

| Columna | Qué es | Valores típicos |
|---------|--------|----------------|
| `polar_sleep_duration_min` | Minutos de sueño real (sin despertares) | 360-480 (6-8h) |
| `polar_sleep_span_min` | Minutos totales en cama (con despertares) | 400-510 |
| `polar_deep_pct` | % de sueño profundo (N3). Solo con Sleep Plus Stages (~18% cobertura) | 15-25% |
| `polar_rem_pct` | % de sueño REM. Solo con Sleep Plus Stages (~18% cobertura) | 18-25% |
| `polar_efficiency_pct` | Eficiencia: tiempo dormido / tiempo en cama × 100 | 85-95% |
| `polar_continuity` / `polar_continuity_index` | Clase e índice de continuidad Polar | 1-5 |
| `polar_interruptions_long` | **Conteo** de interrupciones largas (⚠️ NO es duración). P90 personal ≈ 8 | 0-15 |
| `polar_interruptions_total` | Conteo total de interrupciones (largas + cortas) | 10-40 |
| `polar_sleep_score` | Score Polar (0-100). Solo con Nightly Recharge (~18% cobertura) | 60-90 |
| `polar_night_rmssd` | RMSSD nocturno medio (ms). Complementa el RMSSD matinal — si el nocturno es alto pero el matinal bajo, hay un confusor post-despertar | 20-60 |
| `polar_night_rri` / `polar_night_resp` | RRI y respiración nocturna (ms). Informativos | — |

### Percentiles propios (tus umbrales personalizados)

| Columna | Qué es |
|---------|--------|
| `sleep_dur_p10` | Debajo de este valor = noche corta para TI. Se calibra con todo tu histórico |
| `sleep_dur_p90` | Encima = noche excepcionalmente larga |
| `sleep_int_p90` | Encima = noche fragmentada para TI |

**Si el sleep.csv no existe o Polar API falla:** El gate y la acción no se ven afectados. Solo se pierden los avisos de sueño en reason_text. Los avisos de carga (de sessions_day.csv) siguen funcionando independientemente.

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
| `ART_GT10` | Los artefactos (latidos marcados como offline, fuera de rango, o con saltos bruscos) superan el 10% del registro total. Hay suficiente señal para calcular métricas, pero con ruido significativo. | Impide `Calidad = OK`. El día será FLAG_mecánico como mínimo. |
| `ART_GT20` | Artefactos por encima del 20%. Demasiado ruido para confiar en cualquier métrica. | Fuerza `Calidad = INVALID`. Día perdido. |
| `STAB_TAIL_SHORT` | La cola de la grabación (últimos 120 s) tiene menos de 75 s de material utilizable o menos de 60 pares de latidos. No hay suficientes datos al final para verificar la estabilidad. | Fuerza `HRV_Stability = Unstable`. |
| `STAB_CV120_HIGH` | El coeficiente de variación de la cola (últimos 120 s) supera el 20%. Los intervalos RR al final de la grabación oscilan demasiado — la señal no se había estabilizado realmente. | Fuerza `HRV_Stability = Unstable`. |
| `STAB_LAST2_NAN` | No se pudo calcular RMSSD_stable_last2 (la variabilidad de la cola). Normalmente porque hay muy pocos pares de latidos válidos en los últimos 120 s. | Fuerza `HRV_Stability = Unstable`. |
| `STAB_LAST2_MISMATCH` | La variabilidad de la cola (RMSSD_stable_last2) discrepa más de un 15% con la del tramo completo (RMSSD_stable). Indica que la señal estaba cambiando significativamente al final de la grabación. | Fuerza `HRV_Stability = Unstable`. |
| `BETA_CLIPPED` | El coeficiente beta estimado cayó fuera del rango plausible [0.1, 3.0] y se recortó al límite más cercano. | Solo informativo (afecta a BETA_AUDIT, no al gate V4-lite). |
| `BETA_FROZEN` | El modelo beta era inestable (R² < 0.10 o salto respecto al día anterior > 0.15). Se usó el beta del día anterior en lugar del nuevo. | Solo informativo (afecta a BETA_AUDIT, no al gate V4-lite). |
| `BETA_NONE` | No había suficiente historial (< 60 días válidos en ventana de 90d, o variación de RR insuficiente) para estimar beta. | Solo informativo (afecta a BETA_AUDIT, no al gate V4-lite). |
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
"El dato existe, pero no me fío lo suficiente como para meter intensidad." Salta cuando el día es `FLAG_mecánico`, `Unstable`, o tiene `Artifact_pct > 10%`, pero no llega a ser INVALID. El sistema calcula el gate 2D igualmente (porque perder la señal de tendencia es peor que no tenerla), pero la acción se **fuerza a SUAVE** (`Action_detail = SUAVE_QUALITY`) independientemente del color. En la práctica: si el gate sale VERDE pero tienes quality_flag, no te lances a hacer intervalos — el dato que lo justifica no es fiable.

### ROLL3
Media móvil de los **últimos 3 días clean**. En vez de comparar contra el baseline con el dato crudo de hoy (que puede fluctuar mucho día a día), se suaviza promediando los 3 últimos días fiables. Esto filtra el ruido diario sin perder sensibilidad ante cambios reales: si llevas 2 días con HRV bajando y hoy también baja, ROLL3 lo refleja. Pero si ayer tuviste un pico raro y hoy estás normal, ROLL3 lo amortigua. Si no hay 3 días clean recientes, el gate queda como NO (`ROLL3_INSUF`).

### Veto agudo (bypass de ROLL3)
Mecanismo de seguridad que detecta cuando ROLL3 está **enmascarando una caída brusca**. Si ayer y anteayer estaban bien y hoy tu HRV se desploma, ROLL3 aún muestra un valor cercano al normal (promedia 2 buenos + 1 malo). El veto compara tu dato crudo de hoy directamente contra el baseline: si cae más de 2×SWC por debajo, fuerza `lnRMSSD_used = lnRMSSD_today` (dato crudo) y `HR_used = HR_today`, saltándose el suavizado. El gate se calcula entonces con tu estado real de hoy, no con el promedio.

### SWC_FLOOR
Mínimo garantizado para SWC_ln: `ln(1.05) ≈ 0.04879`. ¿Por qué? En periodos de variabilidad muy estable (todos los días casi iguales), SWC puede ser minúsculo, lo que haría que cualquier fluctuación trivial active gates o vetos. El floor asegura que el "cambio mínimo significativo" nunca sea menor que un ~5% de variación en RMSSD.

### Reason_text
Texto explicativo que combina información del gate con datos contextuales (sueño, carga). No modifica el gate — es un "comentario" que acompaña a la decisión automática. Puede decir cosas como "noche corta", "carga acumulada alta", o "VERDE con fatiga acumulada: precaución". Si el sleep.csv no existe, solo se generan avisos basados en datos HRV (caída aguda, saturación parasimpática).

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
Coeficiente que captura la relación natural entre tu pulso y tu HRV: cuando tu RR sube (pulso más lento), ¿cuánto sube tu RMSSD? Beta responde a eso. Se estima por regresión en espacio logarítmico (`ln(RMSSD) = a + beta × ln(RR)`) con datos de los últimos 90 días. Valores típicos: 0.5–2.0. Beta alto significa que tu HRV es muy sensible a cambios de pulso; beta bajo, que es relativamente estable. **Usado solo en BETA_AUDIT** como referencia forense del sistema V3 — no afecta al gate V4-lite.

### cRMSSD ("c" = corrected)
RMSSD "limpio" de la influencia del pulso: si tu pulso de hoy está más alto de lo normal, tu RMSSD bajará naturalmente (sin que haya fatiga real). cRMSSD usa beta para descontar ese efecto y quedarse solo con la variabilidad "genuina". **Usado solo en BETA_AUDIT** — el gate V4-lite usa el Gate 2D (que compara ambas señales simultáneamente) en lugar de corregir una por la otra.

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
reason_text: Caída aguda HRV: raw=3.408 vs base=3.798 (drop=-0.390, umbral=-0.210) | Noche corta (345min < P10=362) | Carga acumulada alta (load_3d=237)
```

**Interpretación:** El veto agudo detectó una caída brusca que ROLL3 habría enmascarado. El reason_text explica tres factores convergentes: la caída fue real, dormiste poco, y acumulaste mucha carga. Alta confianza de que el ROJO es legítimo.

### Caso 6: VERDE con aviso de fatiga acumulada

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
reason_text: VERDE con carga acumulada (load_3d=210): precaución intensidad
```

**Interpretación:** Tu HRV y pulso están bien (VERDE), pero sessions_day muestra carga acumulada alta en los últimos 3 días. El gate permite intensidad, pero el reason_text sugiere no ir al máximo.

---

## 13. "Para tontos" (muy llano)

- **BASE60** = tu "normal" de los últimos ~2 meses (sin contar hoy).
- **Gate** = compara tu HRV (lnRMSSD) y tu pulso (HR) contra ese normal.
- **ROLL3** = suavizado de los últimos 3 días buenos, para filtrar ruido.
- **Veto agudo** = si hoy tu HRV se desploma pero ROLL3 lo enmascara, el veto salta y usa el dato crudo.
- **Sombras (28/42)** = miran si tu normal "reciente" está cambiando antes de que lo vea BASE60.
- **Residual** = "¿para este pulso, tu HRV está mejor o peor de lo esperable?"
- **quality_flag** = "el dato de hoy es sospechoso": aunque pinte bonito, **no toca apretar**.
- **reason_text** = "te explico por qué": sueño malo (de Polar), carga alta (de sessions_day), caída aguda de HRV, etc. **No cambia el gate**, solo informa.

---

Fin del documento.

