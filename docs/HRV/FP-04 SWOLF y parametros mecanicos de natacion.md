# FP-04 SWOLF y parámetros mecánicos de natación

## Objetivo

Incorporar señal mecánica real para sesiones de natación en piscina mediante la extracción de datos específicos del FIT de swim (`length`, `lap`, `session`), con SWOLF por estilo como métrica central de eficiencia técnica. El objetivo es hacer que el pipeline deje de reportar `coste_dominante = bajo_estimulo` para todas las sesiones de natación — independientemente del esfuerzo real — por no tener señal mecánica.

---

## Diagnóstico — el agujero estructural de swim

### Estado actual para i138090502

```
distance_km:       1.2   (48 largos de 25m)
duration_min:      41.8
hr_mean:           114   (Z1 completo — HR de muñeca bajo agua)
hr_p95:            125   < vt1=134
z2_pct:            0%

cardio_score:      0
mecanico_score:    0    ← confidence: low
coste:             bajo_estimulo
session_meta:      { "sport_family": "swim" }   ← vacío
```

El atleta anota: *"Sensación costosa, como siempre en natación."* El sistema dice `bajo_estimulo`. Esta discrepancia no es ruido — es estructural. El problema tiene dos causas:

**1. HR de muñeca en agua es poco fiable**
Los sensores ópticos de muñeca tienen baja fiabilidad en piscina. El agua actúa como barrera, el movimiento del brazo genera artefactos, y la FC real puede ser 10-20 bpm más alta que la registrada. Los datos de zona (z2_pct=0%) no reflejan el esfuerzo cardiovascular real.

**2. El parser FIT actual ignora los mensajes de swim**
El pipeline lee mensajes `record` (stream segundo a segundo). En natación en piscina, `record` solo contiene timestamp y HR de muñeca — no hay velocidad, no hay datos técnicos. El dato de técnica y eficiencia está en los mensajes `length` (por largo) y `lap` (por serie), que el sistema no lee.

---

## El problema de los estilos — por qué SWOLF no es comparable entre ellos

Este es el punto crítico que determina toda la arquitectura de la solución.

### SWOLF = tiempo (s) + brazadas por largo

Para un largo de 25m:
```
SWOLF = elapsed_time_25m + total_strokes_25m
```

Cuanto menor, mayor eficiencia. Pero los valores **no son comparables entre estilos**.

### Rangos típicos de SWOLF por estilo (25m)

| Estilo | Rango nadador recreational | Rango nadador entrenado | Por qué difiere |
|---|---|---|---|
| **Freestyle (crol)** | 40–60 | 28–42 | Estilo más eficiente; brazada y patada continuas |
| **Backstroke (espalda)** | 45–65 | 32–48 | Similar mecánica a crol pero posición invertida |
| **Breaststroke (braza)** | 55–80 | 40–60 | Glide largo post-patada → menos brazadas pero más tiempo; SWOLF naturalmente alto |
| **Butterfly (mariposa)** | 50–75 | 35–52 | Alta potencia por ciclo; sets cortos; SWOLF variable |
| **Drill** | n/a | n/a | Sin brazadas completas (tabla de patada) o sin patada (pull buoy); SWOLF sin semántica |

**Consecuencia directa:** un SWOLF de 48 en crol es mediocre. El mismo SWOLF de 48 en braza es muy bueno. Un SWOLF global de sesión que mezcla estilos es un número sin significado interpretable.

### Casos concretos que el sistema debe manejar

**Caso A — Sesión típica de entrenamiento técnico:**
```
1000m crol (series 4×100m) + 200m braza (recuperación) + 200m drill (paletas)
```
- El SWOLF de crol es el indicador de rendimiento
- La braza tiene SWOLF naturalmente alto — no es "peor" que el crol, es otro estilo
- Los largos de drill deben excluirse del análisis de eficiencia (no hay brazada completa)
- Un `avg_swolf` global de sesión mezclaría los tres y daría un número inútil

**Caso B — Sesión de mariposa en intervalos cortos:**
```
10×50m mariposa con 30s descanso
```
- SWOLF de mariposa alto es esperado; la señal de esfuerzo está en los bloques de trabajo
- La cadencia de brazada (cycles/min) es más relevante aquí que el SWOLF absoluto
- El tiempo de descanso (30s×10 = 5 min) es información sobre el tipo de entreno

**Caso C — Sesión IM (Individual Medley) o mixed:**
```
400m IM: 100m mariposa + 100m espalda + 100m braza + 100m crol
```
- Cada estilo tiene su propia señal técnica
- Comparar con sesiones de crol puro no tiene sentido
- El valor está en la distribución de estilos y el SWOLF por segmento

### Regla fundamental de diseño

> **SWOLF solo es interpretable para comparación histórica dentro del mismo estilo.**
> Cualquier `avg_swolf` de sesión que mezcle estilos debe ir acompañado de la distribución de estilos, o marcarse como `not_comparable`.

---

## Fuente de datos — mensajes FIT de swim

### Mensajes relevantes (distintos de running/cycling)

**`session` message** — resumen de la sesión completa:
- `pool_length` — longitud del carril (25m o 50m); ausente en aguas abiertas
- `total_lengths` — número total de largos
- `total_strokes` — brazadas totales
- `avg_swolf` — SWOLF medio (sin separar estilos — no usar directamente)
- `avg_stroke_distance` — DPS medio (metros/brazada)
- `total_timer_time` — tiempo activo
- `sport` = `swimming`

**`lap` message** — por serie/bloque:
- `num_lengths` — largos en esta serie
- `avg_swolf` — SWOLF medio de la serie
- `total_strokes` — brazadas en la serie
- `stroke_type` — estilo dominante de la serie
- `total_elapsed_time` — duración total incluyendo descansos
- `total_timer_time` — tiempo activo (sin descansos)

**`length` message** — por largo individual (granularidad máxima):
- `total_strokes` — brazadas en este largo
- `total_elapsed_time` — tiempo de este largo
- `avg_speed` — velocidad media (m/s)
- `stroke_type` — estilo exacto de este largo
- `length_type` — `active` (largo nadado) o `idle` (descanso en la pared)

### Cómo identificar aguas abiertas vs piscina

```python
pool_length = parse_float(session_values.get("pool_length"))
is_pool = pool_length is not None and pool_length > 0
```

Si `is_pool = False`, no hay mensajes `length` útiles y el análisis no puede ejecutarse.

---

## Alcance propuesto

### Iteración A — Parser FIT swim + SWOLF por estilo

**Nuevo módulo `fit_swim_utils.py`:**

```
parse_fit_swim_data(fit_path)
  → lee session, lap, length messages
  → identifica pool vs open water
  → filtra largos idle (descansos en la pared)
  → separa largos drill de largos de estilo completo
  → agrupa por stroke_type

summarize_swim_context(lengths, laps, session_meta)
  → SWOLF por estilo (solo comparables internamente)
  → stroke_distribution (% largos por estilo)
  → DPS por estilo
  → rest_time_total (sum de largos idle)
  → SWOLF degradation (primera vs segunda mitad, solo estilo principal)
```

**Salida — `swim_context` en `summary.json`:**

```json
"swim_context": {
    "pool_length_m": 25,
    "total_lengths": 48,
    "active_lengths": 44,
    "drill_lengths": 4,
    "rest_time_min": 8.3,
    "primary_stroke": "freestyle",
    "stroke_distribution": {
        "freestyle": { "lengths": 38, "pct": 79.2 },
        "breaststroke": { "lengths": 6, "pct": 12.5 },
        "drill": { "lengths": 4, "pct": 8.3 }
    },
    "swolf_by_stroke": {
        "freestyle": { "mean": 44.2, "min": 41.0, "max": 48.0, "cv_pct": 4.1 },
        "breaststroke": { "mean": 61.5, "min": 58.0, "max": 65.0, "cv_pct": 4.8 }
    },
    "dps_by_stroke": {
        "freestyle": 1.62,
        "breaststroke": 1.91
    },
    "swolf_degradation_pct": 6.5,
    "swolf_degradation_stroke": "freestyle",
    "signals_available": {
        "pool_lengths": true,
        "stroke_type": true,
        "drill_detected": true
    },
    "swim_source": "fit_length_messages"
}
```

**Archivo opcional — `artifacts/swim_lengths.csv`:**

```
length_index, length_type, stroke_type, elapsed_time_s, total_strokes, swolf, speed_mps, dps_m
1, active, freestyle, 22.4, 18, 40.4, 1.116, 1.39
2, active, freestyle, 23.1, 17, 40.1, 1.082, 1.47
3, idle, null, 15.0, 0, null, null, null
...
```

---

### Iteración B — Integración en cost model (futura)

Con `swim_context` disponible, el cost model podría mejorar para swim:

**Señal de coste mecánico:**
```
mecanico_score = 1  si SWOLF freestyle < baseline_personal × 0.9  (intensidad alta)
mecanico_score = 1  si swolf_degradation_pct > 8%  (fatiga técnica)
confidence_mecanico = "medium"  (señal SWOLF disponible, no directa como potencia)
```

**Señal de coste cardiovascular (con HR de muñeca como contexto débil):**
```
cardio_score puede basarse en rest_ratio:
  si rest_time / total_time < 0.15  →  sesión continua → cardio aerobo
  si work_blocks definidos con descansos cortos  →  más anaeróbico
```

**Esta iteración queda explícitamente fuera de FP-04.** Requiere cambio de contrato del cost model y validación histórica.

---

## Decisiones de diseño

**1. SWOLF separado por estilo, no global de sesión**
El `avg_swolf` global del `session` FIT message no se expone directamente en `swim_context`. Solo se calculan SWOLF por `stroke_type`. Si el sistema necesita "un número" para comparación histórica, usa el SWOLF del estilo primario (`primary_stroke`).

**2. Drill excluido del análisis de eficiencia**
Largos con `stroke_type = drill` se contabilizan (para conocer el volumen de trabajo técnico) pero se excluyen del cálculo de SWOLF, DPS y degradation. El `drill` engloba tabla de patada, pull buoy, paletas — ninguno representa una brazada completa.

**3. `primary_stroke` = estilo con más largos activos (no drill)**
Si la sesión tiene 70% crol + 20% braza + 10% drill:
- `primary_stroke = freestyle`
- SWOLF degradation se calcula solo sobre los largos de freestyle
- La braza aparece en `swolf_by_stroke` pero no en la señal de degradación

**4. Open water sin soporte en iteración A**
Si `pool_length` es None o 0, `swim_context_error = "open_water_no_pool_length"`. Sin crash. No hay largos definidos → no hay SWOLF → análisis no aplicable. La sesión sigue procesándose con el resto del pipeline.

**5. HR de muñeca como señal de contexto muy débil, no primaria**
HR en swim se reporta pero con flag explícito `hr_confidence = "low_wrist_in_water"`. No se usa para cardio_score en iteración A. La señal cardio de swim sigue siendo ciega hasta tener banda de HR para natación (banda de pecho con transmisión en agua).

**6. SWOLF en 50m no es directamente comparable con SWOLF en 25m**
Si `pool_length = 50m`, SWOLF dobla aproximadamente vs 25m. El campo `pool_length_m` se expone siempre para que el consumer pueda normalizar. No se normaliza automáticamente para evitar confusión.

---

## Riesgos

| Riesgo | Probabilidad | Mitigación |
|---|---|---|
| FIT de Polar swim no tiene mensajes `length` (solo `lap` o `session`) | Media | Verificar con i138090502 antes de cerrar diseño; fallback a lap-level si no hay length |
| Sesión open water sin `pool_length` — común en triatlón | Alta | `swim_context_error: open_water_no_pool_length` + análisis continúa sin swim_context |
| SWOLF de un solo largo de estilo diferente contamina `swolf_by_stroke` | Baja | Requerir mínimo 4 largos del mismo estilo para calcular SWOLF de ese estilo; si no, marcar `too_few_lengths` |
| `drill` mal etiquetado en algunos dispositivos (registrado como `freestyle`) | Media | Sin solución automática; el flag `drill_detected` indica si al menos se identificó algún drill |
| Sesión IM — cada estilo tiene solo 4 largos (100m IM en 25m) | Media | Calcular SWOLF por estilo pero con `too_few_lengths` si < 4; `primary_stroke = mixed` |
| HR de muñeca corrupta da FC artificialmente baja → z2_pct=0% aunque hubo esfuerzo real | Certeza conocida | `hr_confidence: low_wrist_in_water` explícito; swim_context no depende de HR |

---

## Relación con otras tareas

- **No depende de FP-02 ni FP-03**: parser diferente, mensajes FIT distintos, sport diferente. La única infraestructura compartida es `parse_float` de `polar_utils` y el patrón de módulo separado (`fit_swim_utils.py` paralelo a `fit_terrain_utils.py`).
- **Complementa FP-03**: juntas cubren los tres deportes principales del pipeline con señal mecánica propia (trail/road run → FP-02 V3, bike → FP-03, swim → FP-04).
- **Tiene afinidad con SS-01** (separar dato, proxy, inferencia): el SWOLF es dato directo, el DPS es dato, el SWOLF vs baseline personal es una inferencia. La jerarquía debe ser explícita en el output.

---

## Criterios de aceptación

### Iteración A

1. `swim_context` se genera para sesiones de natación en piscina con FIT que contiene mensajes `length`.
2. SWOLF se calcula **por estilo separado**, nunca como promedio global de la sesión.
3. Largos `drill` se identifican, contabilizan y excluyen del SWOLF de eficiencia.
4. Sesiones de aguas abiertas producen `swim_context_error` sin crash.
5. El report técnico incluye sección "Swim Context" para sesiones swim.
6. Si hay menos de 4 largos de un estilo, ese estilo no produce SWOLF y se marca `too_few_lengths`.
7. Validado con i138090502 y al menos 1 sesión adicional de diferente perfil de estilos.

### Iteración B (futura)

8. El cost model usa SWOLF del estilo primario y `swolf_degradation_pct` como evidencia mecánica.
9. `confidence_mecanico = medium` cuando `swim_context` está disponible y válido.
10. El cambio de contrato del cost model está documentado en `docs/contracts/`.

---

## Análisis técnico 2026-04-23

### Estado actual (código)

- No existe `fit_swim_utils.py` ni `swim_context` en el pipeline. El único parser FIT operativo es `analysis/fit_terrain_utils.py` (bike/run) y `analysis/fit_speed_utils.py`.
- Swim se procesa hoy **sin señal mecánica**: `analysis/session_cost_model.py:338-363` (`swim_mechanical_score`) decide por `work_total_min`, `work_longest_min` y `z3_pct`, con `confidence = "low"` explícito. Esto es lo que produce `bajo_estimulo` en i138090502.
- Referencias declarativas a SWOLF ya existen en el prompt analítico (`analysis/session_analysis_pipeline.py:906, 1232-1240, 5682-5685`), pero no hay datos aguas arriba que lo alimenten.
- `hrv_app/polar_client.py:56-67` solo expone `/exercises` y `/exercises/{id}?samples=true` de AccessLink. **No hay endpoint AccessLink para phases de natación**; la capa "fases" que muestra Polar Flow (estilo / descanso / SWOLF / brazadas / stroke rate) no está accesible vía AccessLink público.

### Valor (dado que SYA-02 lo replantea)

El alcance original de TYM-02 (parser FIT `length` messages) **sigue siendo válido como fallback B** de SYA-02 cuando no exista capa Polar Flow programática. Toda la arquitectura semántica de este MD — SWOLF por estilo no comparable entre estilos, `primary_stroke`, exclusión de drill, `too_few_lengths`, `pool_length_m` explícito, HR de muñeca como señal débil, open_water sin soporte — es reutilizable íntegra por SYA-02.

### Errores / supuestos frágiles

1. **Supuesto no verificado**: que el FIT de Polar swim contenga mensajes `length` con `stroke_type` y `length_type` diferenciados. El riesgo ya estaba listado pero no validado contra i138090502 (`analysis/reports/2026/04/2026-04-07_15-16_swim_i138090502/artifacts/session.fit`).
2. Evidencia nueva (tarjeta SYA-02) apunta a que el **FIT/TCX actual no preserva completa** la capa que sí ve Polar Flow → el parser FIT por sí solo puede quedarse corto (sin `stroke_type` o sin `rest_time` fiable).
3. El MD no contempla TCX como fuente (trackpoints + mesetas de distancia a múltiplos de 25m), que es la vía de fallback propuesta por SYA-02.

### Mejoras

- Marcar TYM-02 como **subsumido** por SYA-02: el flujo correcto es primero localizar la fuente programática Polar (iteración A de SYA-02) y solo caer al parser FIT/TCX si esa capa no es accesible.
- Antes de cerrar diseño, dump exploratorio del FIT de i138090502 para ver qué `length` messages y `stroke_type` trae realmente el dispositivo del atleta.

### Conclusión

TYM-02 **queda subsumido por SYA-02 como iteración B de fallback**. El MD no se invalida: su diseño de `swim_context`, separación SWOLF por estilo y criterios de aceptación se trasladan íntegros al nuevo alcance. No recomendable ejecutar TYM-02 de forma independiente; debe avanzar bajo la tarjeta SYA-02.
