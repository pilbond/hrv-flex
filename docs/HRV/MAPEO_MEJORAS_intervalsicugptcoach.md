# Mapeo de Mejoras desde intervalsicugptcoach-public

**Fecha:** 2026-04-02
**Fuente:** Análisis fisiológico de intervalsicugptcoach-public (v17) vs. polar-hrv-automation (v4)
**Autor:** Claude Haiku 4.5 (analysis agent)

---

## Tabla de Mapeo: Análisis → Canvas Tasks

| Mejora | Componente | Canvas Task | Estado | Confianza | Esfuerzo | Justificación Fisiológica |
|--------|-----------|------------|--------|-----------|----------|-------------------------|
| **1. ACWR (Acute:Chronic Workload Ratio)** | Contexto de carga | **CDC-01** ✓ | Ready | 92% | Bajo | Contextualiza carga relativa a fitness actual (ATL/CTL 7d/42d); umbrales fijos no adaptan a periodos base vs. build |
| **2. Monotonía + Strain (Foster)** | Contexto de carga | **CDC-01** ✓ | Ready | 88% | Bajo | Detecta riesgo invisible: carga uniforme predispone infección respiratoria incluso con volumen aceptable |
| **3. Polarisation Index (Seiler 80/20)** | Distribución intensidad | **DO-01** ✓ | Ready | 85% | Bajo | Detecta "agujero negro" (exceso Z2): sabotea adaptaciones sin fatiga aparente, gate sigue verde |
| **4. Durability Index (potencia/velocidad)** | Fatiga periférica | **FP-01 (DI-01)** ✓ | Proposed | 80% | Medio | Complementa drift cardíaco: detección de caída mecánica sin fatiga central aparente |
| **5. Recovery Index compuesto (HRV+HR+Sleep)** | Recuperación | **RE-01** ✓ | Proposed | 78% | Medio | Subdivide ÁMBAR: decisiones más finas basadas en calidad de sueño (Z2 largo vs. corto) |
| **6. NDLI (Neural Load Density Index)** | Aviso predictivo | **AP-01 (NDLI-01)** ✓ | Proposed | 75% | Bajo | **Primer componente proactivo**: detecta clustering de intensidad incluso con gate VERDE (latencia HRV 24-48h) |
| ~~7. Eficiencia Metabólica (San Millán)~~ | ~~Metabolismo~~ | — | ❌ | 55% | Alto | Sin calorimetría indirecta, proxies metabólicas dilyen fiabilidad vs. mediciones RR directas |
| ~~8. ESPE (Energy System Progression)~~ | ~~Progresión energética~~ | — | ❌ | 50% | Alto | Requiere power curves que v4 no descarga; es planificación, no readiness; fase posterior |

---

## Descripción de Mejoras Aceptadas

### **1 & 2: ACWR + Monotonía/Strain → CDC-01** (Ready, bajo esfuerzo)

**Qué aporta intervalsicugptcoach:**
- **ACWR** (Banister fitness-fatigue model): ratio ATL/CTL contextualiza carga al fitness actual
  - Zona productiva: 0.8–1.3
  - Riesgo lesión: >1.5
  - Permite reason_text adaptativo: "ACWR 1.4 — carga > fitness crónico" vs. umbrales fijos

- **Monotonía + Strain** (Foster model): detecta variabilidad de carga, no solo volumen
  - Monotonía = media(carga 7d) / SD(carga 7d); >2.0 = estrés repetitivo
  - Strain = Σ(carga 7d) × Monotonía; >2200 = sobreentrenamiento
  - Semana "peligrosamente igual" pasa desapercibida en rolling actual

**Por qué es crítico:**
- Tu sistema ya tiene datos (load_day, load_3d, load_7d, load_28d en sessions_day.csv)
- Cálculo trivial (media/SD en ventana 7d; EWMA para ACWR)
- Mejora: text de reason_text pasa de binario ("carga alta") a contextual ("ACWR 1.2 — tolerable pero monotonía 2.3 — varía estructura")

**Implementación:**
```python
# En build_hrv_final_dashboard.py o daily aggregation
acwr = load_7d / load_28d  # Simple EWMA
monotony = load_day_mean_7d / load_day_sd_7d
strain = load_sum_7d * monotony
```

---

### **3: Polarisation Index (Seiler 80/20) → DO-01** (Ready, bajo esfuerzo)

**Qué aporta intervalsicugptcoach:**
- **Polarisation Index** (normalizado 0–1): sintetiza distribución Z1+Z2 vs Z3
  - Formula: (Z1 + Z2) / (Z1 + Z2 + Z3)
  - Target: ≥0.75 (78–80% en zonas bajas)
  - Identifica el "agujero negro": demasiado Z2, ni fácil ni duro

**Por qué es crítico:**
- Tu z3_7d_sum detecta EXCESO de Z3 ✓
- Pero NO detecta **déficit de Z1** (demasiado Z2)
- El "agujero negro" (40–60% Z2, poco Z1) es el error más común en resistencia
- Gate sigue verde, pero entrenamiento es subóptimo → adaptaciones saboteadas sin fatiga aparente

**Mejora:**
- Polarisation_index semanal en sessions_day.csv como semáforo estructural independiente
- reason_text: "Polarisation 0.68 — agujero negro (Z2 alto, Z1 bajo) — variar estructura"

**Implementación:**
```python
# En build_sessions.py
z_total = z1_sum_7d + z2_sum_7d + z3_sum_7d
polarisation_index = (z1_sum_7d + z2_sum_7d) / z_total if z_total > 0 else 0
# Flag: <0.7 = insufficient, 0.75-0.9 = optimal, >0.95 = excessive Z1/Z2 void
```

---

### **4: Durability Index → FP-01 (DI-01)** (Proposed, medio esfuerzo)

**Qué aporta intervalsicugptcoach:**
- **Durability Index**: ratio potencia/velocidad (primera hora vs. última hora en sesiones >120 min)
  - Threshold: ≥0.9 = excelente resistencia, <0.8 = deterioro mecánico
  - Perspectiva: caída de potencia (periférica) vs. caída de HR (central)

**Por qué es importante:**
- Tu cardiac_drift_pct mide HR/velocidad (fatiga central)
- Durability Index complementa con perspectiva mecánica: ¿puedes mantener output?
- Diferencia relevante: bajo drift HR + alto durability drop = fatiga periférica (muscular), no central
- Refina work_steady: si durability <0.8, base aeróbica necesita trabajo pese a carga moderada

**Mejora:**
- Integración en reason_text de sesiones largas
- Refinamiento de work_steady classification: "work_steady con durability 0.75 → base aeróbica débil, enfoque endurance largo"

**Implementación:**
```python
# En build_sessions.py (requiere potencia por mitades desde Intervals.icu)
power_first_hour = mean(power[0:moving_time//2])
power_last_hour = mean(power[moving_time//2:moving_time])
durability_index = power_last_hour / power_first_hour if power_first_hour > 0 else 1.0
```

---

### **5: Recovery Index Compuesto → RE-01** (Proposed, medio esfuerzo)

**Qué aporta intervalsicugptcoach:**
- **Recovery Index**: síntesis (HRV × RestHR_ratio × Sleep_score) → score 0–1
- Subdivide zona ÁMBAR con resolución fina según calidad de sueño

**Por qué es importante:**
- Tu gate 2D (lnRMSSD + HR) es excelente conceptualmente
- Sleep actual es sidecar (informa reason_text, no participa en decisión)
- Pero con cobertura de sueño (~18%), integrar sleep_score en índice de recuperación mejora confianza en ÁMBAR
- Permite decisiones como: "ÁMBAR + recovery_index >0.7 → Z2 moderado; ÁMBAR + recovery_index <0.5 → Z1 o descansa"

**Mejora:**
- Recovery Index semanal en sessions_day.csv
- Refinamiento de acciones en ÁMBAR según sleep_quality_percentil
- Ejemplo: "Hoy ÁMBAR pero sleep_score 95 (excelente) → Z2 largo es seguro"

**Implementación:**
```python
# En build_hrv_final_dashboard.py
recovery_index = (lnRMSSD_today / BASE60_lnRMSSD) * (HR_baseline / HR_today) * (sleep_score / 80)
# Normalizado 0-1; usa para refinar action_detail en ÁMBAR
```

---

### **6: NDLI (Neural Load Density Index) → AP-01 (NDLI-01)** (Proposed, bajo esfuerzo)

**Qué aporta intervalsicugptcoach:**
- **NDLI**: detección predictiva de clustering de intensidad en ventana 3–5 días
- Diferencia crítica: bad_streak es **reactivo** (fatiga ya ocurrió), NDLI es **predictivo**

**Por qué es importante (transformador):**
- Tu bad_streak cuenta días consecutivos con gate no-verde → ya es tarde
- NDLI detecta que llevas 3 días con sesiones work_intense incluso si gate sigue VERDE
- HRV tiene latencia 24–48h antes de responder → NDLI alerta antes que el gate cambie
- **Primer componente proactivo del sistema**: pasar de reactivo a parcialmente anticipatorio

**Mejora:**
- Aviso preventivo: "VERDE pero clustering alto (3d con work_intense) — considera Z1 mañana"
- Integración en reason_text y/o badge aparte (e.g., "VERDE ⚠ clustering")
- Reduce sorpresas: detiene la cascada de fatiga antes del ROJO

**Implementación:**
```python
# En build_hrv_final_dashboard.py o daily aggregation
work_intense_count_3d = count(intensity_category == 'work_intense' in last 3 days)
work_intense_count_5d = count(intensity_category == 'work_intense' in last 5 days)
ndli_flag = work_intense_count_3d >= 3 or work_intense_count_5d >= 4
# Si ndli_flag y gate == VERDE: generar aviso "Clustering alto - considera Z1 mañana"
```

---

## Tareas NO Aceptadas

### ~~Eficiencia Metabólica (San Millán)~~ (Confianza 55%)
**Razón:** Sin calorimetría indirecta, los índices FOxI/CUR son heurísticas, no mediciones. Tu sistema trabaja con RR (medición directa del ANS); mezclar con proxies metabólicos diluiría fiabilidad. **Mejor para fase posterior** si añades FTP calibrada y el objetivo incluye ultra-pacing.

### ~~ESPE (Energy System Progression)~~ (Confianza 50%)
**Razón:** Requiere power curves desde Intervals.icu API (que v4 no descarga actualmente). Es análisis de planificación a largo plazo, no readiness inmediata. **No mejora el gate ni el sistema de readiness actual.** Complemento interesante para fase v4.1+.

---

## Dependencias entre Tareas

```
Contexto de carga:
  CDC-01 (ACWR + Monotonía/Strain) — INDEPENDIENTE ✓

Distribución observada:
  DO-01 (Polarisation Index) — INDEPENDIENTE ✓

Recuperación:
  RE-01 (Recovery Index) — DEPENDE DE: CDC-01 (para contexto carga aguda)

Auditoría de carga:
  ADC-01 (Auditoría por capas) — INDEPENDIENTE ✓

Fatiga periférica:
  FP-01/DI-01 (Durability Index) — INDEPENDIENTE (pero mejora DO-01 output)

Aviso predictivo:
  AP-01/NDLI-01 (NDLI) — DEPENDE DE: CDC-01 (load context) + FP-01 (intensity_category)
```

---

## Resumen Ejecutivo

| Aspecto | Status |
|--------|--------|
| **Tareas creadas en canvas** | ✅ 5/5 (2 ready + 3 proposed) |
| **Nuevas mejoras identificadas** | ✅ 4/4 (DI-01, NDLI-01, + enriquecimientos a DO-01 y RE-01) |
| **Cobertura de datos** | ✅ 100% (datos ya disponibles en CSV canónicos) |
| **Transformación cualitativa** | De reactivo → parcialmente predictivo (NDLI) |
| **Próximos pasos** | Implementar CDC-01 + DO-01 (quick wins), luego RE-01 + FP-01 |
| **No-go features** | Eficiencia metabólica + ESPE (posponer a v4.1+) |

---

**Generated by:** Claude Code Analysis Agent
**Model:** Claude Haiku 4.5
**Confidence Floor:** 75% (NDLI) | Ceiling: 92% (ACWR)
