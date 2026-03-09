# ENDURANCE HRV — Propuestas de Mejora Consolidadas

**Versión 4** — Filtradas por viabilidad para N=1 (atleta individual)

Febrero 2026 | 7 revisores independientes + 3 iteraciones con implementador

---

## SECCIÓN 0 — ARQUITECTURA DEL SISTEMA

### 0.1 Capas

El sistema se organiza en 4 capas conceptuales. Las 3 primeras se ejecutan en un solo pipeline y producen un solo output (FINAL). La 4ª es gobernanza offline.

| Capa | Responsabilidad | Qué contiene | Dónde vive |
|------|----------------|--------------|------------|
| **CORE** | Medición y métricas base | RR → RMSSD, HR, calidad, latencia, Tier 2 (SI, SD1/SD2), datos Polar sueño, datos Intervals carga | Columnas en CORE.csv |
| **V4-lite** | Estado fisiológico | gate_final, sombras, residual, warnings, quality_flag, veto_agudo, SWC floor | Lógica decisora en pipeline |
| **ACTION** | Recomendación de acción | recommended_action, reason_text, action_override_reason. Consume gate + confusores + contexto | Bloque final integrado en pipeline |
| **QA/REPORT** | Gobernanza y evaluación | labels.csv, reporte mensual, canary A/B, model cards | Archivos y scripts auxiliares |

**Principio crítico:** CORE y V4-lite son fisiología/medición. ACTION es operativa. QA es auditoría. No se mezclan.

### 0.2 Regla fundamental: "Sugiere = Decide conductual"

En un sistema N=1, donde el mismo individuo desarrolla, usa y es sujeto, una "sugerencia" tiene el mismo efecto conductual que una "orden". Si el sistema dice "no HIIT hoy", el usuario va a hacer caso o va a ignorarlo. En ambos casos, el sistema ha influido en la decisión.

**Implicación:** La capa ACTION se versiona, se testea y se somete a canary con el mismo rigor que el gate. No es "soft". Es un decisor conductual.

**Matiz:** "Sugiere" sigue siendo útil porque permite desviarse sin romper el contrato. Ignorar una sugerencia es una decisión legítima que se puede registrar y analizar. Ignorar una orden genera culpa y datos contaminados.

### 0.3 Outputs del sistema

| Archivo | Contenido | Tier 2 visible | Quién lo ve |
|---------|-----------|----------------|-------------|
| **CORE.csv** | Todo: métricas base + Tier 2 + datos Polar/Intervals | Sí | QA y análisis |
| **FINAL.csv** | CORE + gate + ACTION + contexto | Sí | Auditoría |
| **DASHBOARD.csv** | Subconjunto compacto para decisión diaria | **No** | Vista diaria |

**Regla:** Tier 2 (SI, SD1/SD2, ANS charge) se calcula siempre y se guarda en CORE, pero **no aparece en DASHBOARD**. El riesgo cognitivo de ver más números cada mañana es mayor que el beneficio de tenerlos a la vista. Se consultan en el reporte mensual.

**Sobre FINAL.csv:** FINAL contiene Tier 2 porque es el archivo de auditoría completo. Si en la práctica abres FINAL para tomar decisiones diarias (en vez de DASHBOARD), el Tier 2 estará visible y el riesgo cognitivo se materializa. Opciones:

- **Disciplina:** Solo abrir DASHBOARD por la mañana. FINAL solo para auditorías puntuales.
- **Técnica:** Crear un FINAL_AUDIT que incluya Tier 2 y un FINAL_DAILY que no lo incluya. Más archivos, pero elimina la tentación.
- **Pragmática:** Aceptar que verás Tier 2 y confiar en que no recolorearás mentalmente. Esto es honesto pero frágil.

La decisión depende de tu flujo real. Si consultas un solo archivo cada mañana, debe ser DASHBOARD.

### 0.4 Un pipeline, un script, un output

No hay RECOMMENDER separado. No hay `morning_complexity.csv` aparte. No hay 4 archivos nuevos. El pipeline es:

```
Archivo RR (H10) + Polar sleep API + Intervals API + labels.csv
    → endurance_v4lite.py
    → CORE.csv + FINAL.csv + DASHBOARD.csv + metadata.json
```

---

## SECCIÓN 1 — FUENTES DE DATOS

### 1.1 Polar H10 — Medición matutina (fuente primaria)

Archivo RR exportado. Grabación de ~8min 30s en supino al despertar, respiración libre.

Produce: intervalos RR → RMSSD, HR, lnRMSSD, calidad, latencia, Artifact_pct, HRV_Stability, n_pairs, y todas las métricas Tier 2 (SI, SD1, SD2, ratio SD1/SD2).

### 1.2 Polar Vantage M3 vía Accesslink API — Sueño

Datos extraídos automáticamente cada mañana. Reemplazan el toggle manual `sueno_malo`.

| Campo Polar | Columna CORE | Uso |
|-------------|-------------|-----|
| sleep_score (0-100) | polar_sleep_score | Confusor automático |
| duration (min) | polar_sleep_duration_min | Confusor automático |
| deep_sleep % | polar_deep_pct | Informativo |
| interruptions (count) | polar_interruptions | Confusor automático |
| sleep_end (datetime) | hora_despertar | Informativo (P2.7) |
| ANS charge | polar_ans_charge | Informativo (no decisor) |

**Prohibiciones explícitas sobre ANS charge (score propietario Polar):**

ANS charge es un score propietario cuyo algoritmo interno no es público. Por tanto, NUNCA puede:

- Recolorear gate (no puede cambiar VERDE→ÁMBAR ni ÁMBAR→ROJO)
- Activar veto agudo
- Generar ROJO por sí solo
- Sustituir la medición matutina H10

Solo puede: contextualizar en reason_text ("posible confusor") y aparecer en el reporte mensual como dato correlativo.

**Regla de `sleep_bad_auto`:**

```python
sleep_bad_auto = (
    polar_sleep_score < 60
    OR polar_sleep_duration_min < 360   # < 6 horas
    OR polar_deep_pct < 15
    OR polar_interruptions > 3
)
# Umbrales iniciales. Personalizar con percentiles propios tras 60 noches.
```

### 1.3 Intervals.icu API — Carga y sesiones

Datos extraídos automáticamente. Reemplazan el input manual de `carga_ayer`.

| Campo Intervals | Columna CORE | Uso |
|----------------|-------------|-----|
| icu_training_load (ayer) | intervals_load_ayer | Contexto en ACTION |
| type + sub_type (ayer) | intervals_tipo_ayer | Derivar risk_real_auto |
| icu_intensity (ayer) | intervals_intensity_ayer | Derivar risk_real_auto |
| icu_atl | intervals_atl | Contexto: fatiga aguda |
| icu_ctl | intervals_ctl | Contexto: fitness |
| icu_tsb | intervals_tsb | Contexto: freshness |

**Clasificación automática de carga:**

```python
def clasificar_carga(load, historico_loads_90d):
    p33 = percentile(historico_loads_90d, 33)
    p66 = percentile(historico_loads_90d, 66)
    if load == 0: return 'DESCANSO'
    elif load < p33: return 'BAJA'
    elif load < p66: return 'MEDIA'
    else: return 'ALTA'
```

**Inferencia automática de risk_real_auto (post-hoc):**

```python
def inferir_risk_real(activities_hoy):
    if not activities_hoy:
        return None  # día sin actividad = no evaluable para FV/FR
    a = activities_hoy[0]  # sesión principal
    intensity = a.get('icu_intensity', 0)
    subtype = a.get('sub_type', '').lower()
    if intensity > 85 or 'interval' in subtype or 'race' in subtype:
        return 'A'   # alta intensidad / competición
    elif intensity > 65 or 'tempo' in subtype:
        return 'B'   # media
    else:
        return 'C'   # baja
```

### 1.4 Input manual residual

Solo 3 campos manuales obligatorios diarios (~10 segundos) + 2 opcionales post-sesión:

| Campo | Tipo | Cuándo |
|-------|------|--------|
| **outcome** | A / B / C / D / REST | Post-sesión (o al final del día si REST) |
| **alcohol** | 0 / 1 | Al rellenar labels por la mañana |
| **sintomas** | 0 / 1 | Al rellenar labels por la mañana |

Opcionalmente: `planned_session_risk_plan` (A/B/C) si se conoce el plan del día. Ver P0.1 para detalles.

### 1.5 data_missing_flag

Cuando falta un dato automático, el sistema NO inventa valores:

```python
# Si falta sleep de Polar:
if polar_sleep_score is None:
    sleep_bad_auto = None        # NO asumir "buena noche"
    reason_text += ' | Sleep data unavailable'

# Si falta actividad de Intervals:
if intervals_activities is None:
    risk_real_auto = None        # Día no entra en métricas FV/FR auto
    carga_ayer = None
```

**Regla:** `None` ≠ neutro. Ausencia de dato es ausencia de dato.

---

## PARTE I — PROPUESTAS APROBADAS

Organizadas por capas funcionales (A-F). Total: 29 propuestas + 1 nota operativa.

---

### A. GOBERNANZA Y GROUND TRUTH

---

#### P0.1 — Labels y Evaluación Post-Sesión

**[CONSENSO]** Revisor pragmático + Claude + implementador. Iterado en 3 rondas.

**Problema:** Sin ground truth no se puede medir si el sistema funciona. Sin etiquetas no hay MLOps, hay fe.

**Implementación:** Archivo `ENDURANCE_HRV_labels.csv` separado, join con FINAL en reporte.

**Campos:**

| Campo | Tipo | Manual/Auto | Cuándo rellenar |
|-------|------|-------------|-----------------|
| Fecha | YYYY-MM-DD | Auto | — |
| fill_before_viewing_gate | Boolean | Manual | Marcar True solo si no has mirado el gate |
| planned_session_risk_plan | A / B / C / null | Manual (opcional) | Antes de ver gate, si hay plan |
| outcome | A / B / C / D / REST | Manual | Post-sesión o al final del día |
| alcohol | 0 / 1 | Manual | Por la mañana |
| sintomas | 0 / 1 | Manual | Por la mañana |
| notes | Texto libre | Manual (opcional) | Cuando quieras |
| followed_reco | 0 / 1 / NA | Manual | Post-sesión. ¿Seguiste la recomendación del sistema? |
| trained_today | 0 / 1 | Manual | Override si Intervals falla o no sincroniza |

**Escala de outcome (4 niveles + REST):**

| Nivel | Nombre | Criterio |
|-------|--------|----------|
| A | Excelente | Sesión completada, RPE igual o mejor de lo esperado |
| B | OK | Completada según plan/intención, RPE normal |
| C | Justo | Completada pero RPE alto, piernas vacías, deriva cardíaca anormal |
| D | Mal | Abortada, síntomas durante sesión, claramente no tolerada |
| REST | Descanso | No hubo sesión (por agenda, no por sistema) |

**planned_session_risk: dos modos**

- **Modo Plan:** Se rellena por semana (batch) antes de ver el gate. Ideal, bajo sesgo. Es el dato que permite al sistema "blindar" sesiones de riesgo A.
- **Modo Auto:** Se infiere post-hoc de `risk_real_auto` vía Intervals. Sirve para métricas retrospectivas pero no para protección previa.

**Limitación explícita:** Si no hay plan previo, el sistema no puede "blindar A" antes de la sesión. Solo puede evaluar retrospectivamente.

**Métricas se reportan separadas:**

- **FV_grave_plan** y **FR_repetido_plan**: solo días con `fill_before_viewing_gate=True` y `planned_session_risk_plan` rellenado. Son la métrica de calidad del sistema como protector.
- **FV_grave_auto** y **FR_repetido_auto**: todos los días con `risk_real_auto` disponible. Son la métrica de oportunidad retrospectiva.
- **Nunca mezclar Plan y Auto en el mismo denominador.**

**Contrato de colores (definición explícita):**

| Gate | Significado | Sesiones permitidas |
|------|------------|-------------------|
| VERDE | Recuperación adecuada | Cualquiera según plan (A/B/C) |
| ÁMBAR | Precaución | Solo B/C (no intensidad alta) |
| ROJO/NO | Alerta / dato insuficiente | Solo C o descanso |

**Clasificación de aciertos/fallos:**

```python
if gate == 'VERDE':
    if outcome in ['C', 'D']:
        resultado = 'FALSO_VERDE'  # siempre, cualquier tipo sesión
    elif outcome in ['A', 'B'] and risk in ['A']:
        resultado = 'VERDE_CONFIRMADO'
    elif outcome in ['A', 'B'] and risk in ['B', 'C']:
        resultado = 'VERDE_PARCIAL'
    elif outcome == 'REST':
        resultado = 'NO_TESTEABLE'

if gate == 'AMBAR':
    if outcome in ['A', 'B'] and risk == 'A':
        resultado = 'AMBAR_CONSERVADOR'  # quizá podía haber ido VERDE
    elif outcome in ['A', 'B'] and risk in ['B', 'C']:
        resultado = 'AMBAR_CONFIRMADO'   # precaución adecuada, sesión OK
    elif outcome in ['C', 'D']:
        resultado = 'AMBAR_INSUFICIENTE' # debería haber sido ROJO
    elif outcome == 'REST':
        resultado = 'NO_TESTEABLE'

if gate in ['ROJO', 'NO']:
    if outcome in ['A', 'B'] and risk != None:
        resultado = 'FALSO_ROJO'
    elif outcome in ['C', 'D', 'REST']:
        resultado = 'ROJO_CONFIRMADO'
```

**Tabla de contingencia:**

| | Toleró intensidad (A/B, risk A) | Toleró aeróbico (A/B, risk B/C) | No toleró (C/D) | REST |
|---|---|---|---|---|
| VERDE | ✓ Confirmado | Parcial | ✗ FALSO VERDE | No testeable |
| ÁMBAR | Conservador? | ✓ Confirmado | ✗ Insuficiente (debía ser ROJO) | No testeable |
| ROJO/NO | ✗ FALSO ROJO | Falso rojo? | ✓ Confirmado | ✓ Confirmado |

**Criterio de aceptación:** ≥80% de días etiquetados en 30 días. ≥50% con `fill_before_viewing_gate=True` (objetivo realista inicial).

**SOP operativa para `fill_before_viewing_gate`:**

1. Al despertar, ANTES de ejecutar el pipeline o mirar cualquier resultado:
   - Abrir labels.csv (o formulario equivalente)
   - Rellenar: alcohol, síntomas, planned_session_risk_plan (si hay plan)
   - Marcar `fill_before_viewing_gate = True`
2. Ejecutar el pipeline (medición H10 + procesado)
3. Post-sesión (o al final del día): rellenar outcome

Si por cualquier razón ya has visto el gate antes de rellenar labels, marcar `fill_before_viewing_gate = False`. Esos días cuentan para métricas Auto pero no para métricas Plan. Sin trampas: si dudas, marca False.

**`followed_reco`: separar fallo del sistema vs fallo de adherencia**

Si el sistema dijo ÁMBAR pero hiciste una sesión risk A (ignoraste la recomendación) y salió C/D, eso no es fallo del sistema — es fallo de adherencia. `followed_reco` permite distinguir:

- `followed_reco=1` + outcome C/D → fallo del sistema (FV o AMBAR_INSUFICIENTE)
- `followed_reco=0` + outcome C/D → fallo de adherencia (el sistema acertó, tú lo ignoraste)

Las métricas primarias FV_grave y FR_repetido deben calcularse solo sobre días con `followed_reco=1` o `followed_reco=NA` (días REST). Sin esto, FV/FR mezclan "sistema mal" con "yo hice otra cosa".

**KPIs de gobernanza (reporte mensual):**

```
%fill_true_30d = count(fill_before_viewing_gate=True) / N_measured
  Objetivo: ≥50% al inicio, ≥70% a 3 meses

# FV/FR Plan no se reportan si N_plan_evaluable < 10
# (muestra insuficiente para cualquier conclusión)
```

**Confianza: 95**

---

#### P0.2 — Contexto Automatizado (Polar Sueño + Intervals Carga)

**[CONSENSO]** Revisor pragmático + Kimi + DeepSeek + implementador.

**Problema:** HRV es inespecífico. Sin contexto, falsos verdes y falsos rojos sin explicación.

**Solución:** Automatizar todo lo posible vía APIs. Solo 3 inputs manuales residuales.

**Inputs automáticos (ya detallados en Sección 1):**

- Polar: sleep_score, duración, deep%, interrupciones, ANS charge, hora_despertar
- Intervals: carga_ayer, tipo_ayer, intensity, ATL, CTL, TSB

**Inputs manuales:**

```
alcohol    = 0|1
sintomas   = 0|1   # garganta, mialgia, fiebre, GI
outcome    = A|B|C|D|REST
```

**Reglas de override y contextualización:**

```python
# Override duro:
if sintomas == 1:
    recommended_action = 'SUAVE_O_DESCANSO'
    action_override_reason = 'SINTOMAS'
    reason_text += ' | Síntomas reportados: no intensidad'

# Confusor automático:
if sleep_bad_auto:
    reason_text += ' | Mala noche (Polar): precaución'
if alcohol == 1:
    reason_text += ' | Alcohol: confusor presente'

# Contextualización causal con carga (TSB):
if intervals_tsb < -25 and gate_final == 'ROJO':
    reason_text += f' | Fatiga acumulada (TSB={intervals_tsb}). Esperable.'
if intervals_tsb > 15 and gate_final == 'ROJO':
    reason_text += ' | ROJO sin fatiga acumulada. Posible enfermedad/estrés.'
if intervals_tsb < -30 and gate_final == 'VERDE':
    reason_text += ' | VERDE con fatiga alta. Precaución: posible rebote.'

# Carga de ayer:
carga_cat = clasificar_carga(intervals_load_ayer, historico)
if carga_cat == 'ALTA' and gate_final == 'ROJO':
    reason_text += ' | Fatiga post-carga alta. Recuperación, no alarma.'
if carga_cat == 'BAJA' and gate_final == 'ROJO':
    reason_text += ' | ROJO sin carga previa: revisar otros factores.'

# ANS charge nocturno (Polar) como señal complementaria:
if polar_ans_charge is not None:
    if polar_ans_charge < 30 and gate_final == 'VERDE':
        reason_text += ' | ANS charge nocturno bajo. Precaución pese a VERDE.'
    if polar_ans_charge > 70 and gate_final == 'ROJO':
        reason_text += ' | Buena recuperación nocturna (ANS). Posible confusor matutino.'
# Nota: umbrales ANS charge (30/70) son orientativos.
# Calibrar con percentiles propios tras 60 noches (p.ej. p20/p80).
# La escala depende de lo que devuelva Polar Accesslink para tu dispositivo.
```

**Confianza: 90**

---

#### Métricas Primarias de Evaluación (NUEVO)

**[CONVERGENCIA]** Claude + implementador. Iterado en 2 rondas.

**Principio:** Conteos simples, sin ponderar. Pre-registrar definiciones antes de comparar versiones. Reportar siempre con denominador.

**Métrica de seguridad:**

```
FV_grave = count(
    gate_final == 'VERDE'
    AND outcome in ['C', 'D']
    AND followed_reco in [1, NA]   # excluir días donde ignoraste la recomendación
)
Denominador: N_evaluable (plan o auto según contexto)
```

**Métrica de oportunidad:**

```
FR_repetido = count(
    gate_final in ['ROJO', 'NO']
    AND outcome == 'A'
    AND followed_reco in [1, NA]
)
Denominador: N_evaluable
Umbral de alarma: ≥3 en 30 días
```

**Loss ponderada:** Solo exploratoria. No para decidir si un cambio es bueno o malo.

**Disclaimer de potencia estadística:**

Con ~300 mediciones/año, ~180 días de entrenamiento, ~100 con etiqueta fiable, ~60 con fill_before_viewing_gate=True, y quizá ~15 sesiones risk A en día VERDE: un FV_A de 2/15 tiene un intervalo de confianza al 95% de 1.7% a 40%. Las métricas primarias tardarán 6-12 meses en ser estadísticamente informativas. Cualquier conclusión antes es anecdótica.

| N_evaluable | Puede detectar cambio de... | Con confianza... |
|-------------|---------------------------|-----------------|
| 15 | ±25% | Baja |
| 50 | ±14% | Media |
| 100 | ±10% | Razonable |
| 200 | ±7% | Buena |

**Definiciones formales de denominadores:**

```
N_measured     = días con medición HRV (válida o no)
N_valid        = N_measured - días INVALID
N_trained      = días con actividad registrada (Intervals o trained_today=1)
N_evaluable_plan = días con:
    outcome ∈ {A, B, C, D}
    AND fill_before_viewing_gate = True
    AND followed_reco ∈ {1, NA}
N_evaluable_auto = días con:
    outcome ∈ {A, B, C, D}
    AND risk_real_auto ≠ None
    AND followed_reco ∈ {1, NA}

# Reportar siempre: "FV_grave = k / N_evaluable (N_evaluable = X)"
# Nunca reportar solo "FV_grave = k"
# No reportar FV/FR Plan si N_evaluable_plan < 10
```

**Confianza: 85**

---

### B. TRAZABILIDAD Y CONTROL

---

#### P1.1 — Versionado y Trazabilidad

**[CONSENSO]** Todos los revisores + implementador.

**Implementación:** metadata.json por corrida (no columnas en CSV, porque se reprocesa todo).

```json
{
  "algo_version": "v4lite_2026-02-20",
  "schema_version": "core_v4.0",
  "git_commit": "a1b2c3d",
  "run_timestamp": "2026-02-20T10:30:00Z",
  "config_hash": "sha256:..."
}
```

**Por fila en CORE/FINAL:** solo `run_timestamp` (ISO 8601). Permite detectar si una fila es del procesado original o del reprocesado.

**Regla:** Si cambia cualquier umbral/filtro/lógica → incrementar `algo_version` + model card + reprocesar todo el histórico.

**Pre-registro:** Antes de comparar versiones, escribir qué métricas se usarán y qué resultado se espera. Impide redefinir a posteriori.

**Confianza: 92**

---

#### P3.1 — Canary A/B para Cambios de Algoritmo

**[ORIGINAL]** Revisor pragmático. Adaptado a reprocesado completo + secuenciación.

```python
# 1. Branch del histórico con version_B (nueva lógica)
# 2. Reprocesar todo con version_B
# 3. Comparar métricas pre-registradas:

FV_grave_B = count(gate_B == 'VERDE' and outcome in ['C','D'])
FV_grave_A = count(gate_A == 'VERDE' and outcome in ['C','D'])

if FV_grave_B <= FV_grave_A: adoptar(B)
else: rollback(A)
```

**Secuenciación obligatoria:** Un solo cambio de decisor por iteración. No 3 cambios a la vez. Cambios no-interferentes (labels, metadata, columnas informativas) sí pueden ir en paralelo.

**Confianza: 88**

---

#### P4.3 — Model Cards

**[ORIGINAL]** Revisor pragmático.

Una página por versión: changelog, supuestos del protocolo, limitaciones conocidas, métricas del último período, contrato de acciones.

Evita que tu yo del futuro reinterprete el sistema.

**Confianza: 85**

---

### C. ROBUSTEZ DEL DECISOR (cambios core de bajo coste)

---

#### P1.2 — Veto Agudo del ROLL3

**[ORIGINAL]** Segundo revisor. Validado por Claude + implementador.

**Problema:** ROLL3 diluye caídas agudas. Enfermedad viral + 2 días buenos = ÁMBAR cuando merece ROJO.

```python
if Calidad == 'OK' and lnRMSSD_today < (ln_base60 - 2 * SWC_ln):
    lnRMSSD_used = lnRMSSD_today    # dato crudo, bypass ROLL3
    veto_agudo = True
    reason_text += ' | Caída aguda: bypass ROLL3'
else:
    lnRMSSD_used = mean(last_3_clean)  # ROLL3 normal
    veto_agudo = False
```

**Condición clave:** Solo si `Calidad=OK`. Si hay artefactos, no aplicas veto (evitas falsos rojos por mala medición).

**Confianza: 88**

---

#### P1.3 — Suelo de SWC

**[ORIGINAL]** Segundo revisor.

```python
SWC_ln_final = max(SWC_ln_calculated, log(1.05))
# log(1.05) ≈ 0.0488. Cambio mínimo detectable >= 5% relativo.
```

Evita que el sistema se vuelva "histérico" por fluctuaciones minúsculas en períodos muy estables.

**Confianza: 90**

---

#### P1.4 — Detección de Saturación Parasimpática

**[ORIGINAL]** Segundo revisor. Observación única.

**Problema:** HRV↑↑ + HR↓↓ = vagotonia. Sistema dice VERDE. Atleta aletargado.

```python
if d_ln_60 > (2 * SWC_ln):
    saturacion_flag = True
    reason_text += ' | HRV excesivamente alto. Posible saturación parasimpática.'
    reason_text += ' Considerar activación neuromuscular (sprints cortos).'
```

**Confianza: 82**

---

#### P1.5 — Override O3 Filtrado por Calidad

**[ORIGINAL]** Revisor pragmático.

Persistencia 2-de-3 en modo O3 solo debe contar días sin quality_flag.

```python
dias_patron = last_3_days_for_shadow_eval
dias_validos = [d for d in dias_patron if not d.quality_flag]
if len(dias_validos) < 2:
    override_bloqueado = True
```

**Confianza: 78**

---

#### P2.1 — Umbrales HR por Percentiles Propios

**[CONSENSO]** Todos los revisores.

```python
HR_lower = max(percentile(HR_historico_clean, 2), 28)
HR_upper = min(percentile(HR_historico_clean, 98), 120)
if HR_stable < HR_lower or HR_stable > HR_upper:
    Calidad = 'INVALID'
```

**Confianza: 80**

---

#### P2.9 — Tail-Trim Dinámico

**[ORIGINAL]** DeepSeek R1.

```python
cv_last_30s = std(RR_last_30s) / mean(RR_last_30s)
if cv_last_30s > 0.25: trim_s = 30
elif cv_last_30s > 0.15: trim_s = 20
else: trim_s = 15
```

**Confianza: 75**

---

### D. UX Y OPERATIVA DIARIA

---

#### P2.2 — Razón Humana en Una Línea

**[CONSENSO]** Revisor pragmático + segundo revisor.

```python
reasons = []
if gate_final == 'ROJO':
    if d_ln_60 < -SWC_ln and d_hr_60 > SWC_hr:
        reasons.append('HRV baja y HR alta vs baseline')
if veto_agudo: reasons.append('Caída aguda (bypass ROLL3)')
if saturacion_flag: reasons.append('Posible saturación parasimpática')
if quality_flag: reasons.append('Confianza reducida por calidad')
if sleep_bad_auto: reasons.append('Mala noche (Polar)')
if sintomas: reasons.append('Síntomas reportados')
if intervals_tsb and intervals_tsb < -25:
    reasons.append(f'Fatiga acumulada (TSB={intervals_tsb})')
reason_text = ' | '.join(reasons) if reasons else 'Medición normal'
```

**Principio:** El texto es descriptivo, no diagnóstico. Correlación, no causalidad.

**Confianza: 90**

---

#### P2.3 — REPEAT_RECOMMENDED

**[ORIGINAL]** Revisor pragmático.

```python
if Artifact_pct > 15 and Artifact_pct <= 25:
    repeat_recommended = True
    reason_text += ' | Medición con ruido. Repetir si posible.'
if latencia == 'LAT_NAN' and duracion_grabacion < 480:
    repeat_recommended = True
    reason_text += ' | Estabilización no detectada. Alargar grabación.'
```

**Confianza: 82**

---

#### P2.4 — Reporte Mensual Automático

**[CONSENSO]** Revisor pragmático + segundo revisor + implementador.

Script que genera `ENDURANCE_HRV_report_YYYY-MM.md`:

```
# CALIDAD
dias_OK / dias_FLAG / dias_INVALID / dias_sin_medicion
media_Artifact_pct, media_Tiempo_Estabilizacion

# DISTRIBUCIÓN GATE
VERDE / ÁMBAR / ROJO / NO (con %)

# GROUND TRUTH (separado Plan vs Auto)
FV_grave_plan: k / N_plan_evaluable (OMITIR si N_plan_evaluable < 10)
FR_repetido_plan: k / N_plan_evaluable
FV_grave_auto: k / N_auto_evaluable
FR_repetido_auto: k / N_auto_evaluable

# GOBERNANZA
%fill_true_30d (objetivo ≥50% → ≥70%)
%followed_reco (adherencia al sistema)
días con action_override_reason ≠ null (P2.6, síntomas, etc.)

# CONTEXTO
días con sleep_bad_auto, días con síntomas
TSB medio, carga media
ANS charge medio (si disponible), correlación ANS charge vs gate

# DRIFT
delta_mediana_14d_vs_60d
artifact_trend

# ALERTAS
(automáticas si FV > umbral o INVALID > 15%)
```

**Confianza: 88**

---

#### P2.5 — Reglas Secuenciales Clínicas

**[ORIGINAL]** Revisor pragmático (médico).

```python
# R1: 2+ rojos en 3 días → 48h sin intensidad
# R2: ROJO + HR alta + sleep_bad_auto → sospecha sistémica
# R3: VERDE tras 2 días ROJO/ÁMBAR → confianza recortada al 65%
# R4: VERDE + síntomas → SUAVE_O_DESCANSO (override duro)
```

**Nota:** Implementar después de tener 6-8 semanas de P0.1, no antes.

**Confianza: 78**

---

#### P2.6 — Quality Flag con Tolerancia Z1-Z2

**[ORIGINAL]** Revisor pragmático (entrenador).

```python
if quality_flag and gate_final in ['VERDE', 'AMBAR']:
    recommended_action = 'Z1_Z2_CON_TOPE'
    duracion_max = 90  # minutos
    action_override_reason = 'QUALITY_FLAG'
    reason_text += ' | Dato dudoso: Z1-Z2 hasta 90min, no intensidad'
```

**P2.6 es un decisor conductual** (sugiere = decide). Aunque no cambia gate_final, cambia recommended_action, lo que en la práctica determina lo que haces. Por tanto:

- Cuenta como cambio de ACTION → entra en canary igual que el gate
- `action_override_reason` debe quedar trazado en FINAL para auditoría
- Sin este campo, atribuirás al gate resultados que realmente fueron determinados por ACTION

**Confianza: 85**

---

#### P2.7 — Hora de Despertar (Automática vía Polar)

**[REVISADO]** DeepSeek + Kimi. Automatizado vía Polar.

Ahora es automática: `hora_despertar = polar_sleep_end_time`. Columna informativa en CORE. Sin corrección circadiana activa si siempre se mide inmediatamente al despertar.

**Confianza: 80**

---

#### P2.8 — Score Continuo 2D con Bandas de Severidad

**[ORIGINAL]** Revisor pragmático.

```python
score_ln = d_ln_60 / SWC_ln
score_hr = d_hr_60 / SWC_hr
score_2d = sqrt(score_ln**2 + score_hr**2) * sign(score_ln)

if gate_final == 'AMBAR':
    severity = 'AMBAR_LEVE' if abs(score_2d) < 1.5 else 'AMBAR_FUERTE'
```

Granularidad sin cambiar colores.

**Confianza: 80**

---

#### P4.4 — Tabla de Patrones Fisiológicos (Playbook)

**[ORIGINAL]** Segundo revisor + pragmático.

| Patrón | Señales | Diagnóstico probable | Acción |
|--------|---------|---------------------|--------|
| Fatiga simpática | HR↑↑ + HRV↓ | Estrés agudo, infección, mala noche | Descanso total o Z1 corto |
| Fatiga parasimpática | HR↓↓ + HRV↓ | Fatiga crónica, agotamiento | Descanso largo 3-5 días |
| Saturación | HR↓ + HRV↑↑↑ | Tapering excesivo, bloqueo agudo | Activación neuromuscular |
| Normal | Estable + estable | Recuperación adecuada | Entrenar según plan/sensaciones |
| Confusor térmico | HR↑ + HRV↓ sin fatiga | Alcohol, sauna, calor | Aeróbico. No pánico. |
| Confusor respiratorio | HRV↑ sin cambio HR | Respiración más lenta/profunda | Interpretar HRV con cautela |
| Deshidratación | HR↑ + HRV↓ | Ingesta insuficiente | Hidratarse. Z2 posible si síntomas OK |

**Confianza: 80**

---

### E. MÉTRICAS COMPLEMENTARIAS — SISTEMA POR TIERS

---

**Principio:** La métrica base es RMSSD (tono parasimpático). Las complementarias cubren lo que RMSSD no detecta. Se organizan en Tiers por orden de implementación. Tier 2 desde el día 1 (coste ≈ 0), Tier 3 solo con evidencia.

**Regla arquitectónica:** Tier 2 y 3 se calculan y guardan en CORE. No aparecen en DASHBOARD. No alimentan el gate salvo con evidencia de repetibilidad + predicción de falsos verdes.

| Métrica | Qué detecta | RMSSD no cubre | Tier | Coste |
|---------|------------|----------------|------|-------|
| RMSSD | Tono parasimpático | (base) | Base | Ya implementado |
| SI Baevsky | Activación simpática directa | Sobreentrenamiento simpático | 2 | Sin librerías, 10 líneas |
| SD1/SD2 | Balance autonómico | Rigidez sin retirada vagal | 2 | Sin librerías, 5 líneas |
| DFA-α1 | Complejidad fractal | Pérdida de regulación | 3 | Necesita nolds |
| SampEn | Predictibilidad | Rigidez con RMSSD normal | 3 | Necesita antropy |

---

#### P4.5 — Stress Index de Baevsky (Tier 2)

**[CONVERGENCIA]** Varios revisores + Claude.

**Qué mide:** Lo puntiaguda que es la distribución RR. Distribución estrecha = SI alto = simpático dominante.

**Por qué es clave:** RMSSD detecta retirada parasimpática. SI detecta activación simpática directa. Son complementarios. El escenario de sobreentrenamiento simpático (HR↑ + HRV↓ pero residual normal) se detecta directamente con SI.

**Fórmula:** `SI = AMo / (2 × Mo × MxDMn)`

```python
import numpy as np

def baevsky_stress_index(rr_ms, bin_width=50):
    rr_s = np.array(rr_ms) / 1000.0
    bins = np.arange(rr_s.min(), rr_s.max() + bin_width/1000, bin_width/1000)
    counts, edges = np.histogram(rr_s, bins=bins)
    AMo = counts.max() / len(rr_s) * 100
    modal_idx = counts.argmax()
    Mo = (edges[modal_idx] + edges[modal_idx + 1]) / 2
    MxDMn = rr_s.max() - rr_s.min()
    if Mo == 0 or MxDMn == 0: return np.nan
    return round(AMo / (2 * Mo * MxDMn), 1)
```

**Umbrales orientativos (ajustar con percentiles propios):**

| SI | Significado | Acción |
|----|-----------|--------|
| < 50 | Parasimpático dominante | Normal. Si combina con HRV↑↑↑ considerar saturación |
| 50-150 | Equilibrio normal | Entrenar según plan |
| 150-300 | Activación simpática moderada | Precaución: Z1-Z2 máximo |
| > 300 | Activación simpática fuerte | Descanso o muy suave |

**Ubicación:** Columna en CORE. No en DASHBOARD. No alimenta gate.

**Confianza: 82**

---

#### P4.6 — SD1/SD2 del Poincaré Plot (Tier 2)

**[CONVERGENCIA]** Varios revisores.

**Qué mide:** SD1 = variabilidad latido a latido (~RMSSD). SD2 = variabilidad largo plazo (~SDNN). Ratio SD1/SD2 = balance autonómico. Ratio bajo = simpático dominante con variabilidad total preservada.

```python
import numpy as np

def poincare_sd(rr_ms):
    rr = np.array(rr_ms, dtype=float)
    diff = rr[1:] - rr[:-1]
    sd1 = np.std(diff) / np.sqrt(2)
    sd2 = np.sqrt(2 * np.std(rr)**2 - sd1**2)
    ratio = sd1 / sd2 if sd2 > 0 else np.nan
    return round(sd1, 2), round(sd2, 2), round(ratio, 3)
```

```python
# Flag:
if sd1_sd2_ratio < percentile(ratio_historico_60d, 10):
    poincare_flag = True
    reason_text += ' | SD1/SD2 bajo: rigidez autonómica'
```

**Ubicación:** Columna en CORE. No en DASHBOARD.

**Confianza: 78**

---

#### P4.7 — DFA-α1 como Guardarraíl Unidireccional (Tier 3)

**[CONVERGENCIA]** DeepSeek + Kimi + Claude + implementador.

**Condiciones estrictas para activación:**

1. Calidad = OK
2. n_beats >= 300
3. ICC verificada ≥ 0.6 en protocolo de repetibilidad (ver más abajo)

**Solo unidireccional (protección, no restricción):**

```python
import nolds
alpha1 = nolds.dfa(RR_intervals, nvals=range(4, 17), fit_exp='poly')

if alpha1 < 0.75 and Calidad == 'OK' and n_beats >= 300:
    if gate_final == 'VERDE':
        gate_final = 'AMBAR'
        reason_text += ' | DFA-α1 < 0.75: desregulación. Degradado a ÁMBAR.'
    dfa_guard = True
```

**NO bidireccional:** No escalar ÁMBAR→ROJO automáticamente por α1 > 1.3. La estimación con 300-350 latidos tiene varianza alta en ese rango. Solo flag informativo hacia arriba.

**Requisito previo:** Pasar el protocolo de repetibilidad. Sin ICC ≥ 0.6, DFA-α1 se queda como columna informativa en CORE sin efecto en gate.

**Confianza: 65** ⚠️ ESPECULATIVO hasta verificar repetibilidad.

---

#### P4.8 — SampEn (Tier 3)

**[CONVERGENCIA]** DeepSeek + Kimi + Claude.

**Condición:** Solo si tras 6 meses de etiquetas, falso_verde_rate > 5% Y Tier 2 + DFA-α1 no cubren.

```python
import antropy
sampen = antropy.sample_entropy(RR_intervals, order=2)
# m=2, r=0.2*SD. Comparar con baseline propio.
if sampen < sampen_base60 - 0.3:
    sampen_flag = True
    reason_text += ' | SampEn bajo: pérdida complejidad'
```

**Confianza: 62** ⚠️ ESPECULATIVO.

---

#### Protocolo de Repetibilidad (NUEVO)

**[ORIGINAL]** Implementador.

**Objetivo:** Determinar empíricamente qué métricas son reproducibles en TU protocolo, con TU sensor, con TU fisiología. Convierte discusión teórica en evidencia personal.

**Protocolo:**

- 2 mediciones consecutivas, misma mañana
- 2 días por semana
- Durante 2 semanas
- Total: 8 pares de mediciones

**Calcular para cada métrica:**

| Métrica | Criterio mínimo | Si pasa → |
|---------|----------------|-----------|
| RMSSD | CV_intra ≤ 10% | Confirmado como base |
| SI Baevsky | CV_intra ≤ 15% | Tier 2 operativo |
| SD1/SD2 ratio | CV_intra ≤ 15% | Tier 2 operativo |
| DFA-α1 | ICC ≥ 0.6 | Guardarraíl activable |
| SampEn | ICC ≥ 0.6 | Flag activable |

**Limitación honesta:** La segunda medición no es independiente (8.5 min más tumbado = más estabilizado). El ICC refleja repetibilidad intra-sesión, no sensibilidad al estado real. Es mejor que nada, pero no es validación completa.

**Confianza: 82**

---

#### P4.9 — Índices PNS/SNS Personalizados (Dashboard)

**[DERIVADO]** Concepto Kubios (Tarvainen 2014). Adaptado a N=1 con baseline propio.

Normalización contra tu propio baseline de 60 días, no poblacional.

```python
def pns_personal(mean_RR, RMSSD, SD1, base):
    z_rr = (mean_RR - base['mean_RR_60']) / base['sd_RR_60']
    z_rmssd = (RMSSD - base['RMSSD_60']) / base['sd_RMSSD_60']
    z_sd1 = (SD1 - base['SD1_60']) / base['sd_SD1_60']
    return round((z_rr + z_rmssd + z_sd1) / 3, 2)

def sns_personal(mean_HR, SI, SD2, base):
    z_hr = (mean_HR - base['mean_HR_60']) / base['sd_HR_60']
    z_si = (SI - base['SI_60']) / base['sd_SI_60']
    z_sd2 = -(SD2 - base['SD2_60']) / base['sd_SD2_60']
    return round((z_hr + z_si + z_sd2) / 3, 2)
```

**Visualización: plano PNS×SNS:**

```
           SNS alto (+)
               |
 ESTRESADO     |     ACTIVADO
 PNS-, SNS+    |     PNS+, SNS+
               |
 ------------- + ------------- +PNS
               |
 DEPRIMIDO     |     RECUPERADO
 PNS-, SNS-    |     PNS+, SNS-
               |     (zona ideal)
           SNS bajo (-)
```

**Categoría:** Dashboard/visualización pura. No alimenta gate. Requiere P4.5 + P4.6 implementados.

**Confianza: 72**

---

### F. ANÁLISIS Y TUNING (al iterar)

---

#### P3.2 — SWC Asimétrico

```python
mediana = percentile(lnRMSSD_base60, 50)
SWC_inferior = max(mediana - percentile(lnRMSSD_base60, 25), log(1.05))
SWC_superior = max(percentile(lnRMSSD_base60, 75) - mediana, log(1.05))
```

**Confianza: 72**

---

#### P3.3 — Baseline Ponderado por Calidad

**Caveat:** Implementar con cautela. Si los FLAG no son realmente "buenos con ruido" sino "malos", metes sesgo.

```python
peso = {'OK': 1.0, 'FLAG_mecanico': 0.3, 'INVALID': 0.0}
# Peso conservador (0.3, no 0.5) hasta verificar
```

**Confianza: 55** ⚠️ ESPECULATIVO.

---

#### P3.4 — Score de Confianza de la Medición

```python
s1 = 1.0 - min(Artifact_pct / 25.0, 1.0)
s2 = 1.0 if Tiempo_Estabilizacion else 0.5
s3 = 1.0 if HRV_Stability == 'Stable' else 0.4
s4 = min(n_pairs_stable / 300, 1.0)
confianza = round(0.4*s1 + 0.2*s2 + 0.2*s3 + 0.2*s4, 2)
```

**Confianza: 78**

---

#### P3.5 — Features Informativas en Dashboard

```python
slope_3d = linregress(range(3), lnRMSSD_last_3).slope
recovery_debt = count_consecutivo(gate != 'VERDE', hacia_atras)
strain_accum = intervals_atl  # ya disponible vía Intervals
```

**Confianza: 75**

---

#### P4.1 — Detección de Drift (Regime Shift)

```python
delta_mediana = median(lnRMSSD_last14) - median(lnRMSSD_base60)
if abs(delta_mediana) > 2 * SWC_ln or artifact_trend > 5:
    regime_shift = True
```

**Categoría:** Flag informativo, no cambio de gate.

**Confianza: 72**

---

#### P4.2 — Flecha de Tendencia

```python
slope_7d = linregress(range(7), lnRMSSD_last_7).slope
trend = 'UP' if slope_7d > 0.02 else 'DOWN' if slope_7d < -0.02 else 'FLAT'
```

**Confianza: 78**

---

### NOTA OPERATIVA — Sesgos del Desarrollador-Usuario-Atleta

**[ORIGINAL]** Claude. Exclusivo N=1. Ampliado con implementador.

**1. Sesgo de confirmación:** Atribuir mejora a cambio de umbral cuando puede ser sueño diferente. Mitigar con canary A/B.

**2. Sesgo de anclaje:** Ver VERDE y ajustar RPE inconscientemente. Mitigar: etiquetar `fill_before_viewing_gate`. Solo esos días cuentan para métricas Plan.

**3. Sesgo de optimización:** Ajustar umbral para "arreglar" un falso rojo recordado crea falsos verdes no notados. Priorizar SIEMPRE minimizar falsos verdes.

**4. "Sugiere = decide":** En N=1 no hay separación de roles. La recomendación condiciona la acción igual que una orden. Tratar la capa ACTION con el mismo rigor que el gate.

**5. N pequeño:** Con ~50-100 eventos evaluables al año, cualquier métrica es ruidosa. No sobrerreaccionar a 1-2 eventos. Esperar 6-12 meses para conclusiones robustas.

---

## PLAN DE IMPLEMENTACIÓN

Secuenciado para atribución causal. Gobernanza en paralelo, cambios de decisor uno a uno.

### Iteración 0 — Gobernanza (días 1-3)

**Cambios:** labels.csv con SOP + metadata.json + Tier 2 como columnas en CORE (SI, SD1, SD2, ratio). Separar DASHBOARD sin Tier 2.

**No toca el decisor.** Todo es aditivo.

**Criterio de aceptación:** ≥80% días etiquetados en 30 días.

### Iteración 1a — SWC Floor (semana 1)

**Cambio único de decisor:** `SWC_ln = max(SWC_ln, log(1.05))`

Reprocesar. Canary A/B. Comparar FV_grave.

### Iteración 1b — Veto Agudo (semana 2)

**Cambio único de decisor:** Bypass ROLL3 si caída > 2×SWC y Calidad=OK.

Reprocesar. Canary A/B.

### Iteración 2 — Automatización APIs (semana 2-3, en paralelo con 1b)

**Cambio:** Integrar Polar sleep + Intervals carga/TSB como columnas en CORE. Derivar sleep_bad_auto, carga_cat, risk_real_auto. Incluir ANS charge como columna informativa.

**No toca el decisor.** Solo añade datos. Puede ejecutarse en paralelo con 1b porque no interfiere con la lógica del gate.

**Regla de "logging-only" (30 días):** Durante los primeros 30 días con APIs activas, todos los datos nuevos (sleep_bad_auto, TSB, ANS charge, carga_cat) se recogen y guardan pero NO activan ningún umbral en ACTION ni en reason_text. Esto permite:

- Acumular datos para calibrar percentiles propios (60 noches para sueño)
- Verificar que la sincronización funciona (% días con datos)
- Evitar que "umbrales inventados" contaminen reason_text y, por tanto, conducta

A partir del día 31: activar reglas de contextualización con umbrales calibrados.

### Iteración 3 — ACTION Block (semana 3-4)

**Cambio:** Añadir bloque final en pipeline que produce `recommended_action` + `reason_text`. Incluye P2.6 (quality flag → tolerancia Z1-Z2) y contextualización con TSB/ANS charge/sleep/carga.

Usa gate + confusores + contexto. Integrado, no script separado.

### Iteración 4 — Protocolo Repetibilidad (semana 4-5)

Doble medición 2×/semana × 2 semanas. Calcular ICC/CV. Decidir qué métricas pasan.

### Iteración 5 — Reporte Mensual (semana 6+)

Con suficientes etiquetas. Primer reporte real. Incluye métricas Plan vs Auto separadas.

### Iteración 6 — Reglas Secuenciales P2.5 (semana 8+)

Requiere ≥6-8 semanas de labels para tener contexto. Cada regla (R1-R4) se añade y evalúa por separado.

### Condicional — DFA-α1 guardarraíl

Solo si pasa repetibilidad (ICC ≥ 0.6). Solo unidireccional.

---

## PARTE II — PROPUESTAS RECHAZADAS

Total: 15 propuestas descartadas.

| ID | Propuesta | Motivo |
|----|-----------|--------|
| R1 | ML Supervisado (LSTM, XGBoost, RF, Autoencoders) | ~300 mediciones/año. Sobreajuste. |
| R2 | Isolation Forest | Gate 2D + residual ya cubre. Sin ground truth. |
| R3 | Facebook Prophet | Asume microciclo fijo. Caja negra. |
| R4 | Análisis Frecuencial LF/HF | Grabación insuficiente. Ratio cuestionado. |
| R5 | Arquitectura Cloud/Microservicios | Sobreingeniería para N=1. |
| R6 | Biomarcadores Sanguíneos | Impractico. Toggles matutinos cubren lo esencial. |
| R7 | Transfer Learning Poblacional | No existe población base. |
| R8 | EWMA Reemplazo ROLL3 | Con veto agudo, redundante. |
| R9 | Bootstrap Poblacional | Falsa confianza con valores genéricos. |
| R10 | NLP Cuestionarios | Toggle 0/1 es más práctico. |
| R11 | LOESS/Polinómica Residual | ~300 puntos: overfitting en extremos. |
| R12 | Genómico/Multi-Ómico | Sin relación operativa con HRV matutino. |
| R13 | Modo Ciego Pre-Competición | Problema no desaparece por no verlo. |
| R14 | HMM 2 Estados | ~300 muestras/año: matrices inestables. |
| R15 | Métricas HRV redundantes | SDNN, pNN50, SDSD (redundantes con RMSSD). HRV TI, TINN (redundantes con SI). ApEn (superado por SampEn). D2, Lyapunov (series cortas). |

**También rechazado como métrica principal:** Loss ponderada. Los pesos son arbitrarios y manipulables con n pequeño. Queda como herramienta exploratoria, no para decidir.

---

## ANEXO A — Ranking de Revisores

| # | Revisor | Nota | Comentario |
|---|---------|------|-----------|
| 1 | Revisor pragmático | ★★★★★ | El más útil. Entiende N=1. Bucle A/B/C, canary, model cards. |
| 2 | Segundo revisor | ★★★★ | Saturación parasimpática, residual oculta fatiga, suelo SWC. |
| 3 | Kimi 2.5 | ★★★★ | El más profundo técnicamente. Necesita filtrado. |
| 4 | DeepSeek R1 | ★★★ | Sólido. SampEn, modelo endocrino, UX progresiva. |
| 5 | Grok 4 | ★★ | Correcto pero genérico. |
| 6 | Mistral | ★★ | Tutorial ML genérico. Perfil 50 años rescatable. |
| 7 | Qwen 3 32b | ★ | Errores factuales, terminología inventada. |

**Implementador (3 iteraciones):** ★★★★ — Empezó con sobrediseño, terminó pragmático. Mejor contribución: protocolo de repetibilidad y SOP de labels. Punto ciego persistente: planned_session_risk.

---

## ANEXO B — Tabla de Confianzas

| Propuesta | Confianza | Estado |
|-----------|-----------|--------|
| P0.1 Labels con SOP | 95 | Firme |
| P0.2 Contexto automatizado Polar+Intervals | 90 | Firme |
| Métricas primarias (conteos simples) | 85 | Firme |
| P1.1 Versionado + metadata.json | 92 | Firme |
| P1.2 Veto agudo | 88 | Firme |
| P1.3 Suelo SWC | 90 | Firme |
| P1.4 Saturación parasimpática | 82 | Firme |
| P1.5 Override O3 filtrado | 78 | Firme |
| P2.1 Umbrales HR percentiles | 80 | Firme |
| P2.2 reason_text | 90 | Firme |
| P2.3 REPEAT_RECOMMENDED | 82 | Firme |
| P2.4 Reporte mensual | 88 | Firme |
| P2.5 Reglas secuenciales | 78 | Firme |
| P2.6 Quality flag tolerancia | 85 | Firme |
| P2.7 Hora despertar (auto) | 80 | Firme |
| P2.8 Score 2D severidad | 80 | Firme |
| P2.9 Tail-trim dinámico | 75 | Firme |
| P3.1 Canary A/B | 88 | Firme |
| P3.2 SWC asimétrico | 72 | Límite |
| P3.3 Baseline ponderado | 55 | ⚠️ Especulativo |
| P3.4 Score confianza | 78 | Firme |
| P3.5 Features informativas | 75 | Firme |
| P4.1 Drift detection | 72 | Límite |
| P4.2 Flecha tendencia | 78 | Firme |
| P4.3 Model cards | 85 | Firme |
| P4.4 Tabla patrones | 80 | Firme |
| P4.5 SI Baevsky (Tier 2) | 82 | Firme |
| P4.6 SD1/SD2 Poincaré (Tier 2) | 78 | Firme |
| P4.7 DFA-α1 guardarraíl (Tier 3) | 65 | ⚠️ Especulativo |
| P4.8 SampEn (Tier 3) | 62 | ⚠️ Especulativo |
| Protocolo repetibilidad | 82 | Firme |
| P4.9 PNS/SNS dashboard | 72 | Límite |
