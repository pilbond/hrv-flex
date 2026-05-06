

**Tipo:** Propuesta de nueva capa analítica (shadow/sombra)
**Alcance:** N=1, pipeline HRV operativo
**Estado:** Propuesta — pendiente de aprobación

---

## Motivación

El pipeline actual estima readiness con rolling baselines fijos (`ROLL3`, `baseline_ln`) y un gate binario con veto agudo. Esto funciona bien operativamente pero tiene limitaciones:

- Los τ de decaimiento (fitness, fatiga) son genéricos, no calibrados al atleta
- El gate es determinista — no expresa cuánta incertidumbre hay en la decisión
- Los días con datos faltantes (RR gaps) no propagan incertidumbre explícita
- No hay estimación de estados latentes (fitness, fatiga) separados

Un **Bayesian State-Space Model** añade estas capacidades sin tocar el gate actual, en modo sombra.

---

## Distinción fundamental: modelo fisiológico vs. marco de inferencia

Son dos capas distintas que se combinan:

| Capa | Qué hace | Ejemplos |
|---|---|---|
| **Modelo fisiológico** | Define qué significa fitness, fatiga, recuperación | Banister, Busso, Critical Power |
| **Marco de inferencia Bayesiano** | Estima parámetros con incertidumbre, maneja ruido | Kalman, GP, HMM, MCMC |

El significado fisiológico viene del modelo estructural. La incertidumbre y calibración personal vienen del marco Bayesiano. Se necesitan ambos.

---

## Modelos fisiológicos considerados

### Banister Fitness-Fatigue (1975) — base recomendada

```
fitness(t)   = fitness(t-1)  · exp(-1/τ₁) + carga(t)   # τ₁ ≈ 45 días
fatiga(t)    = fatiga(t-1)   · exp(-1/τ₂) + carga(t)   # τ₂ ≈ 15 días
readiness(t) = k₁·fitness(t) - k₂·fatiga(t)
```

- Bien documentado, inputs directos desde `sessions_day.csv`
- Limitación: τ₁, τ₂, k₁, k₂ son fijos — en realidad varían por atleta y fase

### Coggan ATL/CTL/TSB

```
CTL(t) = CTL(t-1) + (TSS - CTL(t-1)) / 42
ATL(t) = ATL(t-1) + (TSS - ATL(t-1)) / 7
TSB(t) = CTL(t) - ATL(t)
```

Banister simplificado con τ genéricos. Ya está implícito en `sessions_day.csv`. Sin incertidumbre.

### Busso (2003) — parámetros variables

Extiende Banister permitiendo que k₁ varíe con la fatiga acumulada:

```
k₁(t) = k₁₀ · exp(-fatiga(t) / θ)
```

Captura que el mismo entrenamiento tiene efecto diferente cuando estás fresco vs. acumulado. Más realista para bloques de carga alta. Buena opción Bayesiana porque los parámetros variables son exactamente lo que MCMC puede inferir.

### Modelo de 3 componentes (Morton 1990)

Añade supercompensación:

```
fitness(t) + fatigue(t) + recovery(t)
```

Captura el rebote post-tapering. Relevante para bloques de descarga.

### Critical Power / W' (Monod-Scherrer)

```
Potencia(t) = CP + W' / duración(t)
```

Modela curva potencia-duración. Requiere datos de potencia. La recarga de W' tiene dinámica exponencial similar a Banister.

### Modelo HRV-específico (Chalencon / Schmitt)

Usa HRV directamente como señal de estado:

```
HRV_obs(t) = HRV_baseline · f(fitness_t, fatigue_t) + ruido
```

Más natural para este pipeline — `ln_rmssd` es la observación principal.

---

## Marcos de inferencia Bayesiana considerados

### Dynamic Linear Models (DLM) — recomendado para implementación inicial

Generalización del Kalman Filter en marco Bayesiano completo:

```
estado(t) = F · estado(t-1) + ruido_proceso
observación(t) = H · estado(t) + ruido_obs
```

- Sin dependencias nuevas (numpy/scipy suficiente)
- Actualización online (diaria)
- Manejo natural de gaps
- **Fit para pipeline:** ★★★★★

### Gaussian Process (GP) Regression

```
readiness(t) ~ GP(μ, k(t, t'))
```

El kernel k(t,t') captura correlación entre días cercanos. Funciona excepcionalmente bien con pocos datos (N=1 ideal). No descompone fitness/fatiga por sí solo.

- **Fit para pipeline:** ★★★★☆

### Hidden Markov Model (HMM) Bayesiano

Estados latentes discretos:

```
Estados: {fresco, cargado, acumulado, sobreentrenado}
P(estado_t | estado_{t-1}) = matriz de transición
P(HRV_obs | estado_t) = emisión gaussiana por estado
```

Output directamente interpretable como estado operativo. `ssm_gate_shadow` sería la etiqueta del estado.

- **Fit para pipeline:** ★★★★☆

### Bayesian Structural Time Series (BSTS)

Descompone la señal:

```
HRV(t) = tendencia(t) + estacionalidad(t) + efecto_carga(t) + ruido
```

Permite separar tendencia a largo plazo de efectos de carga reciente.

- **Fit para pipeline:** ★★★☆☆

### Bayesian Change Point Detection (BOCPD)

Detecta cuándo cambia el régimen:

```
P(cambio en t | datos) → detecta transiciones de bloque
```

Útil para detectar automáticamente entrada en sobreentrenamiento o cambio de bloque.

- **Fit para pipeline:** ★★★☆☆

### GP-SSM (Gaussian Process State-Space)

La función de transición entre estados es un GP, no una ecuación paramétrica. Más flexible, menos interpretable.

- **Fit para pipeline:** ★★☆☆☆

---

## Combinación recomendada

```
Estructura fisiológica:   Banister (fase 1) → Busso variable (fase 2)
                                   +
Marco de inferencia:      MCMC con PyMC (calibración offline de τ personales)
                          Kalman Extendido (actualización diaria online)
                                   +
Clasificación de estado:  HMM Bayesiano → ssm_gate_shadow discreto
```

---

## Diseño de integración en el pipeline

### Nuevo script: `build_hrv_ssm.py`

Posición en el pipeline:

```
build_hrv_core.py             →  CORE.csv
build_hrv_ssm.py              →  SSM.csv          ← nuevo (opcional)
build_hrv_final_dashboard.py  →  FINAL.csv + DASHBOARD.csv
```

`build_hrv_final_dashboard.py` consume `SSM.csv` como input opcional. Si no existe, funciona igual que hoy.

### Campos nuevos en FINAL.csv (bloque `ssm_*`)

| Campo | Descripción |
|---|---|
| `ssm_fitness` | Estado de fitness latente estimado |
| `ssm_fatigue` | Estado de fatiga latente estimado |
| `ssm_readiness` | k₁·fitness - k₂·fatiga normalizado |
| `ssm_readiness_lo` | Límite inferior intervalo 90% |
| `ssm_readiness_hi` | Límite superior intervalo 90% |
| `ssm_overreach_prob` | P(fatiga > umbral) — señal de alerta temprana |
| `ssm_gate_shadow` | green/amber/red según SSM, sin efecto en gate real |

El gate HRV actual no se toca. Los campos `ssm_*` van al final del bloque, igual que `recovery_*` de RE-01.

### En `reason_text` (solo informativo)

```
[SSM-shadow: fatiga estimada alta, ssm_gate=amber vs gate=green]
```

Sin cambiar la decisión operativa.

---

## Fases de implementación

### Fase 1 — Sombra con parámetros de literatura
- Kalman Extendido con τ₁=45, τ₂=15 (valores Banister estándar)
- Emite campos `ssm_*` en FINAL.csv
- Acumula historial para comparación con gate actual
- Sin nuevas dependencias (numpy/scipy)

### Fase 2 — Calibración personal
- MCMC offline con PyMC sobre historial acumulado
- Estima τ₁, τ₂, k₁, k₂ personales
- Actualiza priors del Kalman con valores calibrados
- Dependencia: `pymc` (opcional, solo calibración)

### Fase 3 — Promoción al gate (condicional a validación)
- `ssm_overreach_prob` influye en `reason_text` real
- `ssm_gate_shadow` puede modular umbrales adaptativamente
- Solo si Fase 1 y 2 muestran mejora clara sobre gate actual

---

## Inputs requeridos del pipeline actual

| Dato | Fuente | Uso en SSM |
|---|---|---|
| `trimp` / `load_score` | `sessions_day.csv` | Input de carga → genera fitness y fatiga |
| `ln_rmssd` | `CORE.csv` | Observación ruidosa de readiness |
| `sleep_score` | `sleep.csv` | Modulador de τ₂ (opcional) |
| `wellness_score` | `wellness_subjective.csv` | Segunda observación (opcional) |

---

## Referencias clave

- Banister EW (1975) — modelo impulse-response original
- Busso T (2003) — parámetros variables con fatiga acumulada
- Chalencon S et al. (2012) — SSM para detección de overreaching con HRV en triatletas
- Schmitt L et al. (2015) — modelos de estado para respuesta al entrenamiento en corredores
- Turner JD et al. (2017) — extensión Bayesiana del modelo Banister para endurance
- Hellard P et al. (2006) — SSM para optimización de carga en nadadores olímpicos
- Pfeiffer M & Hohmann A (2012) — SSM con partículas para seguimiento individual

---

## Notas operativas

- Este módulo es **complementario**, no sustituto del gate actual
- Los campos `ssm_*` no modifican `ENDURANCE_HRV_Spec_Tecnica.md` hasta Fase 3
- Si `build_hrv_ssm.py` falla, el pipeline continúa sin interrupciones
- Compatibilidad: Python 3.11, sin dependencias nuevas en Fase 1
  
---

**Revision Crítica**

## 1. Síntesis de la tesis original

El documento propone añadir un Bayesian State-Space Model (Banister + Kalman Extendido) como capa sombra en el pipeline HRV, emitiendo campos `ssm_*` en FINAL.csv sin tocar el gate actual. La justificación central es que el pipeline actual usa τ genéricos y gates deterministas, y que un SSM Bayesiano añadiría incertidumbre explícita y calibración personal. Se plantea en 3 fases: sombra → MCMC offline → promoción al gate.

---

## 2. Contraargumentos más fuertes

**1. El documento no cuantifica cuántos datos reales hay ni justifica que sean suficientes para el Kalman.** Se menciona N=1 como ventaja pero no se analiza si el histórico real (¿6 meses? ¿18 meses?) tiene suficiente variabilidad de carga para que el modelo aprenda algo distinto a ruido. Si hay períodos largos sin variación de carga (lesión, vacaciones), el Kalman diverge o colapsa hacia los priors sin actualización útil.

**2. El pipeline ya calcula algo equivalente a ATL/CTL — el valor añadido real no está cuantificado.** El documento descarta Coggan como "sin incertidumbre" pero no demuestra que la incertidumbre del Kalman sea operativamente útil. Un intervalo de confianza en `ssm_readiness` solo es valioso si el operador sabe qué hacer con él. Ninguna sección explica cómo un `ssm_readiness_lo/hi` cambia una decisión de entrenamiento concreta.

**3. La Fase 2 (MCMC con PyMC) asume que ln_rmssd es una observación fiable de readiness — esto no está justificado.** La observación del modelo (`ln_rmssd`) es a la vez la señal de readiness actual. Si usas la misma señal para calibrar los parámetros del modelo que para validarlo, el modelo aprende a reproducir ln_rmssd, no a estimar readiness real. Hay circularidad implícita.

**4. La combinación Banister + HMM en la misma implementación es arquitecturalmente inconsistente.** El documento propone DLM para estado continuo y HMM para estado discreto como si fueran complementarios, pero no explica cómo se articulan. ¿El HMM consume el output del Kalman? ¿Corren en paralelo? ¿Comparten parámetros? Sin esta aclaración, el diseño es aspiracional, no implementable.

---

## 3. Confianza por afirmación principal

- **"El Kalman maneja gaps naturalmente"**
    
    - Tipo: factual
    - Confianza: 85/100
    - Estado: razonable — cierto, pero requiere que la covarianza de proceso esté bien especificada; con priors mal calibrados los gaps producen estimaciones con varianza inflada inútil
- **"Banister es la base recomendada para este caso"**
    
    - Tipo: recomendación
    - Confianza: 65/100
    - Estado: especulativo — es la opción más citada en literatura, pero para HRV como observación el modelo HRV-específico (Chalencon) tiene más base empírica directa; la recomendación no justifica por qué Banister sobre HRV-específico
- **"τ₁≈45, τ₂≈15 son valores adecuados como priors"**
    
    - Tipo: factual
    - Confianza: 50/100
    - Estado: especulativo — estos valores vienen de estudios con atletas de rendimiento alto y TSS basado en potencia; para un atleta recreacional-avanzado con TRIMP como métrica de carga, los τ pueden diferir sustancialmente
- **"Sin nuevas dependencias en Fase 1 (numpy/scipy suficiente)"**
    
    - Tipo: factual
    - Confianza: 70/100
    - Estado: razonable — implementable, pero subvalorado en complejidad; un Kalman Extendido correcto con Banister no lineal requiere jacobians y estimación de ruido de proceso, que en numpy es ~200 líneas no triviales
- **"La Fase 3 es condicional a validación"**
    
    - Tipo: recomendación
    - Confianza: 90/100
    - Estado: razonable — el único criterio de cautela sólido del documento

---

## 4. Fallos potenciales y verificación

- **Fallo: Los campos `ssm_*` amplían el esquema de FINAL.csv sin actualizar `docs/contracts/`**
    
    - Plausibilidad: alta
    - Estado: confirmado — el propio CLAUDE.md exige actualizar `docs/contracts/` cuando cambia el esquema de columnas; el documento no lo menciona
    - Justificación: CLAUDE.md §"Política de Cambios" es explícito en esto
- **Fallo: No hay criterio de éxito definido para promover de Fase 1 a Fase 2**
    
    - Plausibilidad: alta
    - Estado: no confirmado
    - Justificación: "acumula historial para comparación con gate actual" no define qué métrica, umbral o período de observación activa la Fase 2; sin esto la sombra puede quedarse en sombra indefinidamente
- **Fallo: Las referencias bibliográficas no están verificadas independientemente**
    
    - Plausibilidad: media
    - Estado: indeterminado
    - Justificación: Busso (2003), Turner et al. (2017), Chalencon et al. (2012) son reales como autores del área, pero los años y títulos exactos no fueron verificados en esta sesión; citarlos como base del diseño sin verificación es riesgo de credibilidad
- **Fallo: `build_hrv_ssm.py` falla silenciosamente si no hay datos de carga suficientes**
    
    - Plausibilidad: media
    - Estado: no confirmado
    - Justificación: el documento dice "si falla, el pipeline continúa" pero no especifica qué constituye fallo, ni cómo se propagan NaN en los campos `ssm_*` a `reason_text`

---

## 5. Cambios y conclusiones

- **Qué se mantiene:** la distinción modelo fisiológico vs. marco Bayesiano es correcta y útil; la arquitectura de sombra es el enfoque adecuado; DLM/Kalman como primera implementación es razonable
- **Qué se debilita:** la recomendación de Banister sobre HRV-específico no está bien justificada; los priors τ₁=45/τ₂=15 son cuestionables para este atleta concreto; el valor operativo del intervalo de confianza no está argumentado
- **Qué se corrige:** falta obligación de actualizar `docs/contracts/`; falta criterio de éxito para avanzar de fase; la combinación Banister+HMM necesita aclarar arquitectura
- **Incertidumbres abiertas:** volumen real de datos históricos disponibles; fiabilidad de las referencias exactas; si `ln_rmssd` es observación válida para calibrar Banister o hay circularidad

---

## 6. Respuesta revisada

El documento es una propuesta válida y bien estructurada, pero tiene tres correcciones necesarias antes de usarlo como spec de implementación:

**Corrección 1 — Criterio de avance entre fases** Añadir en cada fase una condición de éxito medible. Ejemplo mínimo:

> Fase 1 → Fase 2: tras 90 días de sombra, correlación `ssm_gate_shadow` vs `gate_actual` > 0.6 en días sin gap de datos

**Corrección 2 — Obligación de actualizar contracts** Añadir en "Notas operativas":

> Los campos `ssm_*` requieren actualizar `docs/contracts/ENDURANCE_HRV_Estructura.md` y `ENDURANCE_HRV_Diccionario.md` antes de Fase 3

**Corrección 3 — Justificar Banister vs. HRV-específico** El modelo HRV-específico (Chalencon) usa `ln_rmssd` como observación directa, que es exactamente lo que tienes. Banister requiere que la carga (TRIMP) sea un buen proxy de estrés fisiológico — asunción más débil. El documento debería reconocer esto explícitamente o invertir la recomendación.

**Lo que no cae:** la propuesta de implementación en 3 fases con modo sombra sigue siendo el enfoque correcto. El riesgo técnico real está en la Fase 2, no en la Fase 1.

---

## 7. Adenda de reevaluacion (2026-05-05)

Esta adenda actualiza la lectura de la tarea despues de contrastarla con el pipeline real del repo, el contrato actual de `FINAL.csv` y el historico disponible.

### 7.1 Juicio actualizado

La tarea sigue siendo valida, pero esta demasiado ancha para ejecutarla tal como esta escrita. Ahora mismo mezcla:

- Banister fijo
- Busso variable
- Kalman Extendido / DLM
- MCMC con PyMC
- HMM para clasificacion discreta
- ampliacion directa de `FINAL.csv`

Eso no es una implementacion unica; es un roadmap de investigacion. Para este proyecto conviene reducir la primera entrega a una sola pregunta operativa:

> Puede una capa sombra de estado latente aportar informacion util por encima del gate actual y del contexto de carga ya disponible, sin romper contratos ni tocar el decisor productivo?

### 7.2 Lo que cambia con la lectura actual del repo

El pipeline real ya tiene un contrato duro sobre `FINAL.csv`:

- `build_hrv_final_dashboard.py` declara una lista fija de 62 columnas
- `docs/contracts/ENDURANCE_HRV_Estructura.md` documenta ese contrato exacto
- `analysis/` ya consume `reason_text` y sidecars asociados como parte del flujo reproducible

Por tanto, aunque la propuesta dice "sin tocar el gate actual", anadir `ssm_*` directamente a `FINAL.csv` si toca el contrato operativo del sistema. No rompe la logica del gate, pero si rompe el esquema canonico salvo actualizacion explicita de contratos, tests y consumidores.

### 7.3 Relectura de Busso

Busso no cae como idea. De hecho, fisiologicamente es de las partes mas interesantes de la propuesta porque modela que la misma carga no produce el mismo efecto cuando vienes fresco que cuando vienes acumulado.

El problema es de identificacion, no de intuicion:

- en este repo la carga diaria viene de `sessions_day.csv`
- la observacion principal seria `lnRMSSD_used` o `lnRMSSD_today`
- esa misma senal ya participa en el gate actual y tiende a mezclar fitness, fatiga, ruido y contexto no modelado

Con esa estructura, Busso sube mucho el riesgo de sobreajuste si entra demasiado pronto. Puede producir parametros elegantes pero poco creibles si no se valida fuera de muestra.

Conclusion actual:

- `Banister fijo` sigue siendo mejor opcion para la primera sombra
- `Busso` debe tratarse como extension avanzada de Fase 2
- no debe ser requisito de la primera implementacion

### 7.4 Historico minimo razonable

Regla operativa propuesta para esta tarea:

- menos de 3 meses: insuficiente incluso para una sombra seria
- 3-6 meses: suficiente para un Banister fijo muy exploratorio
- 6-9 meses: minimo razonable para empezar a probar estabilidad de la sombra
- 9-12 meses: umbral razonable para plantear calibracion personal
- 12+ meses: ventana buena para valorar Busso con mas confianza

Lectura del historico actual del proyecto en esta revision:

- `CORE/FINAL` cubren aproximadamente 2025-05-12 a 2026-05-04
- hay alrededor de 12 meses de HRV canónico
- el solape util con `sessions_day.csv` ronda 292 dias

Eso es suficiente para:

- una Fase 1 sombra seria
- un prototipo controlado de calibracion posterior

No es suficiente para fiarse ciegamente de un Busso promovido a decision operativa.

### 7.5 Redefinicion recomendada de las fases

#### Fase 1 - sombra minima implementable

Objetivo:

- crear `build_hrv_ssm.py`
- generar `ENDURANCE_HRV_ssm_shadow.csv`
- no tocar `FINAL.csv` en la primera entrega

Modelo minimo recomendado:

- estado continuo simple: `fitness`, `fatigue`, `baseline`
- input de carga desde `load_day` o `trimp` derivado en `sessions_day.csv`
- observacion principal desde `lnRMSSD_used`
- dias sin HRV -> prediccion sin update
- dias sin sesion -> carga 0 sobre calendario continuo

Salida recomendada del sidecar:

- `Fecha`
- `ssm_input_ready`
- `ssm_input_quality`
- `ssm_fitness`
- `ssm_fatigue`
- `ssm_readiness`
- `ssm_readiness_lo`
- `ssm_readiness_hi`
- `ssm_overreach_prob`
- `ssm_shadow_state`

#### Fase 2 - calibracion personal

Solo se habilita si Fase 1 demuestra valor y si hay al menos 9-12 meses de historico util.

Objetivo:

- recalibrar taus y pesos
- comparar Banister fijo contra variante Busso
- validar fuera de muestra

En esta fase Busso entra como candidato, no como obligacion.

#### Fase 3 - integracion informativa

Antes de tocar columnas canonicas, la integracion recomendada es informativa:

- sidecar consumible por `analysis/`
- opcionalmente item estructurado adicional en `reason_items`
- no promocionar a `gate_final` hasta demostrar valor claro

Solo despues tendria sentido debatir si `ssm_*` entra en `FINAL.csv`.

### 7.6 Valor real esperado

El valor de la tarea no deberia formularse como "crear un gate nuevo". El valor real esperado es:

- detectar verde con fatiga latente alta no evidente aun en el gate
- detectar rojo poco explicable por la carga reciente
- separar mejor carga alta bien absorbida de carga alta cada vez peor absorbida
- ofrecer una lectura longitudinal mas estable que la mezcla actual de umbrales y contexto

Si no entrega eso, el modelo anade complejidad estadistica pero no valor operativo.

### 7.7 Veredicto actualizado

La tarea merece seguir viva, pero reformulada.

Propuesta de reformulacion corta:

> Implementar una capa sombra de estado latente para HRV/carga con sidecar propio y validacion temporal, dejando Busso como extension avanzada y evitando tocar `FINAL.csv` en la primera entrega.

En ese formato, la tarea encaja con el proyecto actual. En su forma original, corre el riesgo de convertirse en una iniciativa de investigacion demasiado ambiciosa para el valor operativo inicial que puede aportar.
