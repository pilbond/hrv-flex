

**Tipo:** Propuesta de nueva capa analítica (shadow/sombra)
**Alcance:** N=1, pipeline HRV operativo
**Estado:** Documento de trabajo — tesis original, reevaluacion critica y posicion vigente consolidada

---

## Lectura recomendada y estatus actual

Este documento ya no debe leerse como una propuesta lineal unica, sino como la evolucion de una idea inicial hacia una especificacion mucho mas acotada.

La lectura correcta hoy es esta:

- las secciones iniciales hasta `6. Respuesta revisada` conservan la tesis original y la primera ronda de critica
- las secciones `7` a `12` contienen la reevaluacion metodologica y la posicion operativa consolidada
- la seccion `13` contiene el plan de implementacion vigente
- para decisiones de implementacion, las secciones que mandan son `10` a `13`

En consecuencia, ya no debe entenderse como vigente la idea original de:

- ampliar `FINAL.csv` en Fase 1
- introducir de entrada `fitness/fatigue` duales como salida canonica
- usar `Busso`, `MCMC`, `HMM` o promocion al gate como parte del primer corte implementable

La posicion consolidada del documento es esta:

- Fase 1 = capa sombra minima, separada del pipeline canonico
- observacion principal = `lnRMSSD` desde `CORE`
- input exogeno = `load_day[t-1]` desde `sessions_day`
- validacion = prospectiva, contra outcomes externos y baselines simples
- integracion = sidecar y gobernanza conservadora antes de cualquier visibilidad o influencia

---

## Estado de las secciones historicas

Las secciones `1` a `6` se conservan por trazabilidad intelectual, pero ya no deben leerse como especificacion vigente. Su valor actual es historico:

- documentan la tesis original
- conservan argumentos y contraargumentos iniciales
- explican por que se descarto una Fase 1 mas ambiciosa

Del mismo modo, dentro de la seccion `7`, el apartado `7.5` debe interpretarse como una reformulacion intermedia ya superada por las secciones `10` y `13`. Cuando exista conflicto entre:

- `7.5`
- `10. Sintesis critica del Bloque 3`
- `13. Plan de implementacion`

mandan `10` y `13`.

---

## Motivación de la tesis original (archivo)

El pipeline actual estima readiness con rolling baselines fijos (`ROLL3`, `baseline_ln`) y un gate binario con veto agudo. Esto funciona bien operativamente pero tiene limitaciones:

- Los τ de decaimiento (fitness, fatiga) son genéricos, no calibrados al atleta
- El gate es determinista — no expresa cuánta incertidumbre hay en la decisión
- Los días con datos faltantes (RR gaps) no propagan incertidumbre explícita
- No hay estimación de estados latentes (fitness, fatiga) separados

Un **Bayesian State-Space Model** añade estas capacidades sin tocar el gate actual, en modo sombra.

---

## Distinción fundamental de la tesis original (archivo)

Son dos capas distintas que se combinan:

| Capa | Qué hace | Ejemplos |
|---|---|---|
| **Modelo fisiológico** | Define qué significa fitness, fatiga, recuperación | Banister, Busso, Critical Power |
| **Marco de inferencia Bayesiano** | Estima parámetros con incertidumbre, maneja ruido | Kalman, GP, HMM, MCMC |

El significado fisiológico viene del modelo estructural. La incertidumbre y calibración personal vienen del marco Bayesiano. Se necesitan ambos.

---

## Modelos fisiológicos considerados en la tesis original (archivo)

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

## Marcos de inferencia Bayesiana considerados en la tesis original (archivo)

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

## Combinación recomendada en la tesis original (archivo)

```
Estructura fisiológica:   Banister (fase 1) → Busso variable (fase 2)
                                   +
Marco de inferencia:      MCMC con PyMC (calibración offline de τ personales)
                          Kalman Extendido (actualización diaria online)
                                   +
Clasificación de estado:  HMM Bayesiano → ssm_gate_shadow discreto
```

---

## Diseño de integración en el pipeline propuesto originalmente (archivo)

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

## Fases de implementación propuestas originalmente (archivo)

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

## Inputs requeridos en la tesis original (archivo)

| Dato | Fuente | Uso en SSM |
|---|---|---|
| `trimp` / `load_score` | `sessions_day.csv` | Input de carga → genera fitness y fatiga |
| `ln_rmssd` | `CORE.csv` | Observación ruidosa de readiness |
| `sleep_score` | `sleep.csv` | Modulador de τ₂ (opcional) |
| `wellness_score` | `wellness_subjective.csv` | Segunda observación (opcional) |

---

## Referencias clave de la tesis original (pendientes de verificacion independiente)

- Banister EW (1975) — modelo impulse-response original
- Busso T (2003) — parámetros variables con fatiga acumulada
- Chalencon S et al. (2012) — SSM para detección de overreaching con HRV en triatletas
- Schmitt L et al. (2015) — modelos de estado para respuesta al entrenamiento en corredores
- Turner JD et al. (2017) — extensión Bayesiana del modelo Banister para endurance
- Hellard P et al. (2006) — SSM para optimización de carga en nadadores olímpicos
- Pfeiffer M & Hohmann A (2012) — SSM con partículas para seguimiento individual

---

## Notas operativas de la tesis original (archivo)

- Este módulo es **complementario**, no sustituto del gate actual
- Los campos `ssm_*` no modifican `ENDURANCE_HRV_Spec_Tecnica.md` hasta Fase 3
- Si `build_hrv_ssm.py` falla, el pipeline continúa sin interrupciones
- Compatibilidad: Python 3.11, sin dependencias nuevas en Fase 1
  
---

**Primera revision critica (archivo)**

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

Este apartado se conserva solo como marca de transicion entre la tesis original y la especificacion vigente. Su utilidad actual es historica: muestra el momento en que la propuesta dejo de hablar de ampliacion directa de `FINAL.csv` y empezo a orientarse hacia una capa sombra separada.

Sin embargo, los detalles aqui sugeridos ya no deben usarse para implementacion porque mezclan decisiones despues descartadas, por ejemplo:

- estados `fitness/fatigue/baseline` como salida de Fase 1
- uso de `lnRMSSD_used` como observacion principal
- sidecar con `ssm_fitness`, `ssm_fatigue` y `ssm_overreach_prob` como schema base

La reformulacion vigente de fases es la siguiente:

- **Fase 1**: sidecar sombra minimo con un unico estado de recuperacion/autonomia, `lnRMSSD` desde `CORE`, `load_day[t-1]` y validacion prospectiva
- **Fase 2**: calibracion personal o complejizacion solo si Fase 1 demuestra valor incremental claro
- **Fase 3**: integracion informativa o visible solo con salvaguardas, auditoria y rollback

La especificacion que manda para estas fases ya no esta aqui, sino en:

- `10. Sintesis critica del Bloque 3`
- `11. Sintesis critica del Bloque 4`
- `12. Sintesis critica del Bloque 5`
- `13. Plan de implementacion`

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

---

## 8. Sintesis critica del Bloque 1

Esta sintesis consolida la literatura revisada sobre modelos `fitness-fatigue`, sistemas de espacio de estados, filtrado de Kalman y uso de HRV como senal observacional, con un criterio deliberadamente conservador. El objetivo no es maximizar ambicion metodologica, sino identificar que parte del diseno esta razonablemente respaldada y que parte sigue siendo una extrapolacion de investigacion.

### 8.1 Que soporte parece solido

La literatura si respalda la viabilidad matematica de reformular el modelo `fitness-fatigue` dentro de una arquitectura de espacio de estados. En este punto, `Kolossa et al. (2017)` es la referencia mas directa: demuestra que un modelo tipo Banister/Busso puede expresarse como un sistema dinamico y corregirse recursivamente mediante filtro de Kalman usando mediciones ruidosas de rendimiento. Esto no valida por si solo una implementacion concreta para HRV, pero si justifica la eleccion de un marco `SSM + Kalman` como linea metodologica defendible.

Tambien existe soporte suficiente para afirmar que la HRV en reposo es una senal longitudinal util en monitorizacion del entrenamiento. En particular, `lnRMSSD` tiene una base empirica fuerte como marcador reproducible y sensible a cambios recientes de carga y recuperacion. Sin embargo, esa evidencia respalda mejor su uso como marcador practico de estado autonomico que como observacion completa de un estado latente de `fitness` en sentido mecanico o estructural.

La literatura reciente tambien refuerza una advertencia importante: los modelos clasicos de dos componentes son fragiles desde el punto de vista estadistico. Diversos trabajos criticos sobre el modelo `fitness-fatigue` muestran problemas de identificabilidad, alta correlacion entre parametros y riesgo de que el componente de `fatigue` capture ruido mas que un proceso fisiologico estable. Esto no invalida la familia de modelos, pero si obliga a priorizar parsimonia y validacion predictiva real.

### 8.2 Que soporte sigue siendo parcial

No se ha encontrado precedente fuerte de `lnRMSSD` usado como observacion recursiva dentro de un filtro de Kalman acoplado a un modelo Banister/Busso para corregir en tiempo real los estados latentes. El precedente mas cercano es `Chalencon et al. (2015)`, donde una senal de HRV nocturna se modela dinamicamente como salida del sistema entrenamiento-respuesta, junto con el rendimiento. Eso demuestra que la HRV puede integrarse en una logica de impulso-respuesta, pero no prueba todavia que `lnRMSSD` sea una observacion suficiente o estable para actualizar un estado latente mediante filtrado recursivo.

Tampoco hay soporte fuerte para asumir que la dinamica temporal de la HRV y la del rendimiento mecanico compartan las mismas constantes de tiempo. Es plausible que la recuperacion autonómica y la recuperacion estructural operen en escalas distintas. Por tanto, usar la HRV como si observara directamente el mismo `fitness` que luego se expresa en vatios, ritmo o rendimiento competitivo seria una simplificacion excesiva.

La extension tipo `Busso` o modelos no lineales derivados tiene atractivo fisiologico, especialmente para representar acumulacion de fatiga, saturacion o respuesta dependiente del contexto previo. Sin embargo, esa ganancia de realismo viene acompanada de una perdida clara de robustez estadistica. En un contexto N=1 con observaciones ruidosas y sin tests frecuentes de rendimiento, la no linealidad aumenta el riesgo de sobreajuste y de parametros poco identificables. Por eso su uso en una primera fase debe considerarse exploratorio, no central.

### 8.3 Implicacion para la tarea SSM-01

La lectura mas prudente del Bloque 1 es que la tarea sigue teniendo sentido, pero debe acotarse. Lo que esta razonablemente respaldado no es un modelo Bayesiano completo con `Busso + MCMC + HMM`, sino una primera capa sombra de estado latente simple, estable y validable.

Para una Fase 1 robusta, la opcion con mejor equilibrio entre soporte metodologico y riesgo tecnico es un modelo de espacio de estados lineal de un solo estado latente, actualizado con filtro de Kalman y alimentado por una observacion diaria de HRV. Ese estado no deberia llamarse `fitness`, sino algo mas honesto con la senal disponible, por ejemplo `autonomic_recovery_state`, `autonomic_readiness` o `recovery_state`. La razon es que `lnRMSSD` informa sobre regulacion vagal y recuperacion autonómica, no sobre toda la capacidad mecanica del atleta.

En esta primera fase, `Busso` deberia quedar explicitamente relegado a una extension de Fase 2. Del mismo modo, la integracion inicial no deberia tocar `FINAL.csv` ni el `gate` operativo. La forma coherente de introducir esta capa es como `sidecar` sombra reproducible, con validacion temporal y comparacion contra outcomes posteriores, no contra la propia HRV del mismo dia.

### 8.4 Diseno minimo recomendado para Fase 1

La configuracion mas conservadora y defendible es la siguiente:

- arquitectura: `state-space model` lineal
- estado latente: un solo estado de recuperacion/autonomia, no `fitness` mecanico
- observacion principal: `lnRMSSD` diario
- observacion secundaria opcional: `HR_today`
- input de carga: `load_day` o `trimp` desde `sessions_day.csv`
- estimacion: filtro de Kalman lineal
- parametros: fijados o fuertemente restringidos en Fase 1
- salida: `ENDURANCE_HRV_ssm_shadow.csv`
- integracion: fuera de `FINAL.csv` en la primera entrega
- validacion: temporal y fuera de muestra, con enfasis en outcomes posteriores

### 8.5 Conclusion operativa

El Bloque 1 no justifica todavia una promocion ambiciosa del modelo al pipeline canonico, pero si aporta base suficiente para una primera implementacion sombra, siempre que se mantengan cuatro principios:

- parsimonia estructural
- separacion estricta entre evidencia metodologica y evidencia fisiologica
- cautela con la interpretacion de `lnRMSSD`
- validacion prospectiva o fuera de muestra antes de cualquier promocion operativa

Bajo estos limites, `SSM-01` sigue siendo una tarea valida. Lo que cambia no es su interes, sino la ambicion que conviene darle en su primera implementacion.

---

## 9. Sintesis critica del Bloque 2

Esta sintesis consolida el trabajo del Bloque 2 sobre circularidad, outcomes independientes, validacion temporal y criterios de paso entre fases. El objetivo no es definir un protocolo estadistico maximalista, sino fijar una estrategia de validacion razonablemente robusta para un modelo N=1 donde `lnRMSSD` actua como observacion principal de una capa sombra de estado latente.

### 9.1 Principio rector: evitar la validacion tautologica

El problema central no es solo construir un modelo que ajuste bien la serie de HRV, sino demostrar que ese modelo aporta valor operativo mas alla de la propia HRV. Por tanto, la regla metodologica basica debe ser esta:

> la HRV puede usarse como observacion imperfecta del estado latente, pero el modelo no debe validarse contra la misma senal que lo construye

Esto implica dos consecuencias practicas:

- el outcome principal debe ser externo a la HRV
- la evaluacion debe ser prospectiva y fuera de muestra

Bajo este marco, el exito del modelo no consiste en reproducir mejor `lnRMSSD`, sino en anticipar un resultado funcional o de recuperacion que no forme parte del mismo calculo.

En terminos operativos, esto equivale a trabajar en `shadow mode`: la capa sombra puede generar predicciones y scores, pero durante la validacion no debe gobernar la carga ni contaminar el outcome que luego se usara para evaluarla.

### 9.2 Outcomes independientes: jerarquia recomendada

La eleccion del outcome es la decision metodologica mas importante del Bloque 2. A efectos de este proyecto, la jerarquia mas defendible es la siguiente.

Antes de implementar el modelo como evaluacion formal, debe hacerse una auditoria previa de viabilidad del outcome. Las columnas de `sessions_day.csv` como `effort_above_typical_aerobic`, `cardiac_drift_worst` o `effort_above_anchor_aerobic` son metricas de la sesion en la que se calculan; solo son outcomes validos si se alinean como resultado posterior a una estimacion previa del estado, por ejemplo estado matinal en `t` frente a la siguiente sesion comparable en `t+1...t+7`. No pueden usarse como outcome del mismo dia si eso introduce ambiguedad temporal.

Del mismo modo, `ENDURANCE_HRV_wellness_subjective.csv` debe auditarse antes de tratar `wellness` o `PRS` como outcome secundario. Si la semantica temporal no esta documentada de forma consistente -por ejemplo, si el registro de una fecha refleja "como me siento hoy", "como fue ayer" o un comentario libre sin escala numerica-, no debe usarse como criterio formal de validacion. En ese caso puede conservarse como contexto cualitativo, pero no como outcome cuantitativo de Fase 1.

Regla de parada: si la auditoria no encuentra al menos un outcome posterior, externo y reproducible con cobertura suficiente, la Fase 1 puede generar un sidecar tecnico, pero no puede reclamar validacion predictiva ni pasar a Fase 2.

#### Outcome principal

El outcome principal recomendado es una metrica objetiva de rendimiento posterior o de tolerancia/eficiencia en una sesion comparable. La forma mas realista de operacionalizarlo en un proyecto N=1 no tiene por que ser un test maximo formal, sino una sesion suficientemente estandarizada y repetible en la que pueda medirse una respuesta funcional comparable entre dias o semanas.

La idea clave no es perseguir un "rendimiento absoluto" diario, sino medir la calidad funcional de la siguiente sesion comparable dentro de una familia de sesiones predefinidas. Esa familia deberia compartir, al menos de forma aproximada:

- tipo de estimulo
- objetivo fisiologico
- rango de intensidad
- duracion o volumen comparables
- posicion similar dentro del microciclo

Esto permite construir un outcome funcional util sin exigir un test formal semanal ni un protocolo maximalista de laboratorio.

Ejemplos razonables:

- distancia o velocidad mantenida a una carga interna fija
- potencia a frecuencia cardiaca objetivo
- eficiencia de una sesion comparable repetida regularmente
- respuesta en una tarea submaxima establecida por el propio atleta

La razon para priorizar este outcome es que combina tres ventajas:

- baja circularidad
- relevancia operativa directa
- posibilidad de comparacion longitudinal

#### Outcome secundario

El outcome secundario recomendado es `PRS`, `wellness` o una medida comparable de recuperacion en `D+1` o `D+2`. Esta familia de outcomes es mas blanda que una medida de rendimiento, pero tiene dos ventajas claras:

- alta factibilidad en seguimiento diario
- capacidad de capturar deterioro o fragilidad no visible aun en un test funcional

Debe tratarse como outcome secundario o de apoyo, no como criterio unico de validacion fuerte.

#### Outcomes terciarios o exploratorios

Pueden conservarse como outcomes terciarios:

- illness
- dias perdidos
- mala adaptacion tras bloques de carga
- eventos adversos de recuperacion

Estos outcomes son muy relevantes, pero su baja frecuencia o su etiologia heterogenea los hace menos adecuados como eje principal de una Fase 1.

### 9.3 Diseno temporal de validacion

Para una serie diaria N=1 con aproximadamente 12 meses de historico, el diseno de validacion mas defendible es de tipo `walk-forward` o `rolling origin`. La justificacion no es solo metodologica, sino operativa: este esquema se parece a como el modelo se usaria realmente en produccion.

La logica debe ser siempre la misma:

- entrenar con informacion pasada
- predecir un tramo futuro
- avanzar la ventana
- repetir el proceso sobre varios segmentos temporales

La forma exacta puede variar:

- `expanding window` si interesa acumular toda la historia disponible
- `rolling window` si se sospecha no estacionariedad fuerte

Lo importante no es fijar hoy un corte exacto, sino mantener tres principios:

- no usar particiones aleatorias
- no permitir fuga temporal
- obtener multiples evaluaciones fuera de muestra, no un unico holdout

Cuando sea posible, el horizonte de evaluacion deberia estar desplazado al menos `D+1` respecto a la HRV observada, para reducir al minimo el riesgo de evaluar el modelo contra una consecuencia demasiado inmediata o parcialmente compartida con la propia medicion.

### 9.4 Baselines minimos que el modelo debe batir

El modelo sombra no se justifica por ser mas sofisticado, sino por superar de manera consistente referencias simples y transparentes. Para este proyecto, los baselines minimos recomendados son tres.

#### Baseline 1: HRV simple

Un baseline basado en `rolling lnRMSSD`, media movil o suavizado exponencial es obligatorio. Si el modelo no supera una version simple y estable de la propia HRV, no hay razon para mantener una capa latente adicional.

#### Baseline 2: carga reciente

Debe incluirse una referencia basada en carga reciente, por ejemplo:

- `load_3d`
- `load_7d`
- una EWMA de carga
- `ATL/CTL` en una implementacion simple

La razon es que el repo ya dispone de contexto de carga canonico, y el modelo debe demostrar que aporta algo mas que leer bien la carga acumulada.

#### Baseline 3: referencia historica comparativa

`ACWR` puede conservarse como baseline historico o de referencia comparativa, pero no deberia ocupar un papel conceptual central. Su utilidad aqui es contextual, no doctrinal.

### 9.5 Valor incremental: que significa de verdad

El valor incremental del modelo no debe definirse como mejor ajuste interno ni como correlacion mas alta con `lnRMSSD`. Debe definirse como mejora prospectiva y repetible sobre baselines simples en la prediccion de outcomes independientes.

Las formas mas utiles de evidenciar ese valor son:

- menor error fuera de muestra para outcomes continuos
- mejor capacidad de acertar la direccion del cambio
- mejor capacidad de anticipar deterioro o fragilidad
- mejor lectura de casos discordantes entre HRV, carga y sensacion subjetiva

En otras palabras, el modelo debe demostrar que ayuda precisamente cuando las reglas simples o las senales aisladas dejan mas ambiguedad.

La prueba mas util no es que el modelo funcione cuando todas las senales ya apuntan en la misma direccion, sino que mantenga valor en escenarios discordantes, por ejemplo:

- HRV aparentemente favorable pero sensacion subjetiva o carga reciente desfavorables
- HRV deprimida sin un contexto de carga claro
- recuperacion subjetiva aceptable con senales fisiologicas ambiguas

Por eso conviene evaluar el modelo en dos cortes distintos:

- rendimiento global sobre todos los dias validos
- rendimiento especifico sobre el subconjunto de dias discordantes

Si el modelo mejora solo en el agregado total pero no en los dias discordantes, es posible que este aprendiendo sobre todo la tendencia media del sistema. Si en cambio conserva o amplifica la mejora precisamente en los dias ambiguos, entonces la capa sombra esta aportando desambiguacion real y no solo un suavizado mas elaborado.

### 9.6 Riesgos de usar lnRMSSD como unica observacion

Usar `lnRMSSD` como unica observacion no invalida una Fase 1, pero si introduce limitaciones claras que deben reconocerse explicitamente.

#### Ruido biologico

La HRV responde no solo a carga y recuperacion, sino tambien a sueno, hidratacion, alimentacion, estres, enfermedad incipiente y otras condiciones de contexto.

#### Ruido de medicion

Pequenas variaciones de protocolo, postura, dispositivo, hora o calidad del registro pueden modificar la senal.

#### Ambiguedad fisiologica

Una caida de `lnRMSSD` no discrimina con precision entre tipos de fatiga ni entre adaptacion funcional y mal estado no funcional. Por eso, como unica observacion, puede resultar insuficiente para una capa latente rica o muy interpretable.

La conclusion operativa de este apartado no es prohibir HRV sola, sino asumir que una Fase 1 basada principalmente en HRV debe ser parsimoniosa y mantenerse en modo sombra.

### 9.7 Observaciones multiples: cuando y para que

La literatura y el razonamiento metodologico convergen en que fusionar multiples observaciones reduce fragilidad y ayuda a romper parcialmente la circularidad. Si el proyecto avanza mas alla de una Fase 1 minima, las observaciones mas valiosas a priorizar son:

- `lnRMSSD` diario
- `HR_today` o resting HR
- sueno objetivo o subjetivo
- `wellness` o `PRS`
- outcome funcional posterior cuando exista

No es necesario exigir esta fusion desde el primer dia, pero si conviene reconocer que una segunda observacion barata y frecuente, como `HR_today`, puede mejorar la identificabilidad del estado latente de forma material.

En una primera iteracion, la secuencia mas defendible es:

- demostrar primero que la capa sombra supera a un baseline simple usando HRV principalmente
- solo despues evaluar si anadir observaciones extra reduce fragilidad y mejora valor incremental

La ablacion formal de senales puede reservarse para una fase posterior, cuando el modelo ya tenga suficiente complejidad como para que medir contribuciones marginales tenga sentido.

### 9.8 Criterio de paso de Fase 1 a Fase 2

La promocion a una Fase 2 mas compleja no deberia depender de que el modelo sea elegante, sino de que haya demostrado utilidad suficiente. La condicion minima recomendada es una combinacion de tres evidencias:

- mejora prospectiva consistente sobre el mejor baseline simple
- repeticion razonable de esa mejora en varios segmentos temporales
- senal suficientemente estable e interpretable como para justificar mayor complejidad

De forma mas concreta, antes de abrir la puerta a `Busso`, calibracion Bayesiana mas libre o fusion multimodal mas ambiciosa, deberia cumplirse algo parecido a esto:

- el modelo supera de forma repetible a `rolling HRV` y al menos a un baseline simple de carga
- la mejora aparece fuera de muestra, no solo in-sample
- el modelo aporta informacion util en casos discordantes, no solo cuando todas las senales apuntan ya en la misma direccion

Si esas condiciones no se cumplen, la conclusion correcta no es forzar mas complejidad, sino reconsiderar la definicion del estado latente, el outcome elegido o la necesidad misma de una capa sombra adicional.

### 9.9 Conclusion operativa

El Bloque 2 no obliga todavia a un modelo complejo, pero si fija con bastante claridad como debe validarse una Fase 1 seria. La secuencia metodologica mas defendible para `SSM-01` es:

- construir una capa sombra parsimoniosa
- validarla contra outcomes externos y temporales
- compararla contra baselines simples
- exigir mejora prospectiva repetible antes de escalar complejidad

Bajo esta lectura, la Fase 1 no debe entenderse como una demostracion de verdad fisiologica completa, sino como una prueba de utilidad incremental suficientemente robusta como para merecer una Fase 2.

---

## 10. Sintesis critica del Bloque 3

Esta sintesis cierra el Bloque 3 con un objetivo mas estrecho que en los bloques anteriores: no justificar la idea general del modelo, sino fijar la especificacion minima implementable de una Fase 1 en modo sombra, anclada al schema real del repositorio y compatible con la validacion definida en el Bloque 2.

El criterio rector es simple: en Fase 1 no interesa construir el modelo mas expresivo posible, sino el mas parsimonioso que aun permita poner a prueba una hipotesis util. Si la capa sombra no demuestra valor incremental con esta version minima, no hay justificacion para escalar a `Busso`, calibracion Bayesiana mas libre o multimodalidad mas ambiciosa.

### 10.1 Estado latente recomendado

La formulacion mas defendible para una primera implementacion es un unico estado latente de recuperacion autonómica, por ejemplo `autonomic_recovery` o `recovery_state`.

La eleccion de un solo estado responde a tres restricciones del caso:

- la observacion principal disponible en Fase 1 es HRV diaria
- la identificabilidad con una sola observacion es limitada
- el objetivo es evitar vender la señal como `fitness` mecanico o `fatigue` estructural

Por tanto, el estado latente no debe interpretarse como `fitness-fatigue` en sentido clasico. Debe interpretarse como una senal latente de recuperacion/autonomia observada de forma imperfecta por la HRV matinal y modulada por la carga reciente.

### 10.2 Observacion y entrada canonicas

La observacion canonica del modelo debe ser `lnRMSSD` desde `ENDURANCE_HRV_master_CORE.csv`.

Esta decision es importante por dos motivos:

- `lnRMSSD` es la columna real y canonica del `CORE`
- evita reutilizar campos ya procesados aguas abajo, como `lnRMSSD_used`, que pertenecen a otra capa del pipeline

De forma equivalente, la entrada de carga canonica para Fase 1 debe ser `load_day` desde `ENDURANCE_HRV_sessions_day.csv`, desplazada un dia:

- observacion en `t`: `lnRMSSD[t]`
- input exogeno: `u[t-1] = load_day[t-1]`

Esta alineacion temporal evita fuga fisiologica trivial. La HRV matinal del dia `t` no debe depender de una carga del mismo dia que todavia no ha ocurrido.

Aunque `trimp` exista a nivel de sesion, la variable diaria mas coherente con el contrato actual del repositorio es `load_day`. `trimp` puede conservarse como referencia o fallback tecnico en analisis posteriores, pero no como columna canonica de Fase 1.

### 10.3 Dinamica temporal minima

La dinamica candidata para esta primera iteracion es un modelo lineal univariado con persistencia y entrada exogena de carga previa:

```text
recovery_state[t] = phi * recovery_state[t-1] + beta * load_day[t-1] + eta_t
lnRMSSD[t] = recovery_state[t] + epsilon_t
```

con:

- `eta_t` como ruido de proceso
- `epsilon_t` como ruido de observacion
- `phi` en el rango `(0, 1)` para representar persistencia
- `beta < 0` si la carga deprime el estado de recuperacion

Esta formulacion mantiene el vinculo minimo entre entrenamiento y estado, sin exigir una semantica fisiologica demasiado fuerte. Al mismo tiempo, sigue siendo mas estable que un modelo de dos estados o una extension no lineal tipo `Busso`.

Sin embargo, esta no es la unica arquitectura defendible. El comparador estructural obligatorio para Fase 1 es un `Bayesian Local Level Model` sobre `lnRMSSD` sin entrada exogena directa, seguido de una regresion auxiliar de los residuos o innovaciones contra `load_day[t-1]`. Esta variante separa dos preguntas que el ARX-Kalman mezcla en una sola ecuacion:

- cual es el estado latente suavizado de la HRV, ignorando la carga
- si la carga previa explica de forma reproducible las innovaciones o residuos que el estado HRV-only no captura

Esta separacion es metodologicamente atractiva porque permite testear primero si `load_day` aporta senal antes de comprometerse con un modelo conjunto. Por tanto, el `local level + regresion de residuos` no debe tratarse como un mero control ornamental, sino como una prueba de admisibilidad de la carga. Si esta prueba no muestra contribucion clara de `load_day[t-1]`, el ARX-Kalman no deberia promocionarse como arquitectura principal por encima de un modelo HRV-only.

Ademas, antes de fijar el ARX-Kalman como candidato operativo, debe ejecutarse un pre-test OLS ligero de utilidad de carga:

```text
lnRMSSD[t] ~ lnRMSSD[t-1] + lnRMSSD[t-3] + lnRMSSD[t-7] + load_day[t-1]
```

Este test no se interpreta como prueba definitiva de causalidad ni como veto automatico basado solo en `p-value`. Su funcion es mas modesta: comprobar si `load_day[t-1]` aporta informacion incremental sobre `lnRMSSD[t]` despues de controlar persistencia reciente de la propia HRV. Si el coeficiente de `load_day[t-1]` es positivo, inestable o no mejora el ajuste fuera de muestra, la carga debe degradarse a senal exploratoria o baseline, y el candidato principal pasa a ser HRV-only (`local level`) hasta que exista evidencia externa mas fuerte. Un `p > 0.10` debe leerse como evidencia debil a favor de incluir carga, no como demostracion de ausencia de efecto.

Hay una limitacion matematica importante que debe quedar explicita. Con parametros congelados y ruido gaussiano, el filtro lineal tiende a operar con una ganancia de Kalman practicamente estable. En ese regimen, la estimacion filtrada puede expresarse como una combinacion lineal recursiva de `lnRMSSD` suavizado y `load_day` suavizado con memoria exponencial. Es decir: la Fase 1 no debe venderse como una inferencia fisiologica rica, sino como una capa lineal auditada que combina HRV, carga previa, incertidumbre y reglas de degradacion. Su valor incremental tendra que venir de esa trazabilidad, de la gestion de `missingness` y de la validacion externa, no de una expresividad matematica muy superior a un baseline lineal bien construido.

Esto implica una condicion de utilidad fuerte: con `lnRMSSD` como unica observacion, el estado latente solo merece sobrevivir si no se comporta como un simple smoother glorificado. Para comprobarlo, la validacion debe incluir una prueba de equivalencia frente a un baseline lineal que use los mismos ingredientes en forma transparente, por ejemplo una regresion OLS sobre:

```text
recovery_state[t] ~ EWMA(lnRMSSD)[t] + EWMA(load_day)[t-1]
```

Si ese baseline reproduce el estado filtrado con coeficientes y predicciones practicamente equivalentes, la capa SSM no debe promocionarse como nueva senal fisiologica. En ese caso, su unico posible valor residual seria operativo: tratamiento de incertidumbre, degradacion por calidad y manejo auditable de datos faltantes. Si tampoco aporta mejora en outcomes externos o dias discordantes, la Fase 1 debe considerarse fallida por redundancia.

Tambien existen alternativas mas expresivas o robustas que son tecnicamente razonables, pero no deberian entrar como implementacion principal de Fase 1:

- `beta_t` como coeficiente de carga variable con `random walk` lento: sigue siendo Kalman lineal con estado aumentado, pero introduce un segundo estado dificil de identificar con una sola observacion diaria
- AR(1) sobre residuos de `lnRMSSD` respecto a un baseline rolling: es muy auditable y puede usarse como baseline fuerte, aunque renuncia al marco probabilistico completo del SSM
- observacion con colas pesadas tipo Student-t: protege frente a dias extremos por enfermedad, alcohol, viaje o artefactos, pero exige filtrado aproximado o particulas y complica una Fase 1 que busca ser determinista y simple
- estado con tendencia explicita `[level, slow_trend]`: ayuda a separar deriva cronica de variacion aguda, pero agrega otro grado de libertad y debe esperar a que se caracterice primero la deriva real del historico

El veredicto de arquitectura queda asi: el ARX-Kalman univariado sigue siendo el candidato principal implementable, pero no debe justificarse solo por descarte de modelos mas complejos. Debe pasar desde el inicio la prueba `local level + regresion auxiliar de residuos sobre carga`. Si ambos enfoques son indistinguibles, o si la carga no explica residuos/innovaciones de forma reproducible, se debe preferir la alternativa mas auditable y estable antes de escalar complejidad.

### 10.4 Parametros y filosofia de calibracion

La Fase 1 debe operar con una filosofia de parametros fuertemente restringidos. La recomendacion mas prudente es:

- `phi` fijado inicialmente y sometido a analisis de sensibilidad posterior
- `beta` fijado o calibrado una sola vez sobre un tramo inicial de entrenamiento, nunca sobre toda la serie si luego se va a validar temporalmente
- `sigma_proc` y `sigma_obs_base` definidos como **desviaciones tipicas**, no varianzas, y congelados despues del `warm-up`

Valores iniciales de trabajo:

| Parametro | Valor inicial | Regla de Fase 1 |
|---|---:|---|
| `phi` | `0.92` | Fijo. Equivale a una semivida aproximada de 8.5 dias. Sensibilidad obligatoria en `0.85-0.97`. |
| `beta` | `-0.0010` | Efecto de carga diario sobre `lnRMSSD`. Una carga `load_day=100` desplaza el estado en `-0.10` log-unidades. Puede calibrarse una sola vez en los primeros 90 dias estables mediante OLS restringida, pero debe quedar `<= 0` y no reestimarse online. |
| `sigma_obs_base` | `0.12` | SD observacional base en escala `lnRMSSD`. Estimar en `warm-up` como `SD(lnRMSSD - rolling_7d(lnRMSSD))`; usar `0.12` como fallback si el tramo no es suficientemente estable. |
| `sigma_proc` | `0.04` | SD del ruido de proceso. Aproximadamente un tercio de `sigma_obs_base`; evita seguir ruido diario pero permite cambios reales. |

La implementacion debe convertir estas desviaciones tipicas a varianzas dentro del filtro:

```text
Q_base = sigma_proc^2
R_base = sigma_obs_base^2
```

La calibracion restringida de `beta`, si se activa, debe hacerse solo sobre el tramo inicial predefinido, preferentemente con una regresion simple de cambios o innovaciones de `lnRMSSD` frente a `load_day[t-1]`. Si el coeficiente estimado es positivo, inestable o indistinguible de cero, se mantiene el valor fijo `-0.0010` y se documenta que `beta` es asumido, no identificado.

Lo importante aqui no es encontrar la parametrizacion "optima", sino evitar que el modelo gane aparente inteligencia solo porque se le deja absorber demasiados grados de libertad.

En consecuencia:

- no conviene reestimar `phi` o `beta` on-line en Fase 1
- no conviene introducir todavia `EM`, `MCMC` ni priors complejos como parte central del primer despliegue sombra
- la unica cantidad que debe actualizarse recursivamente a diario es el propio estado latente

### 10.5 Calidad de observacion y datos faltantes

El modelo debe degradar de forma explicita cuando la calidad del dato baja o cuando faltan inputs. Aqui la regla no debe apoyarse en columnas inventadas, sino en las que el `CORE` ya expone canonicamente, por ejemplo:

- `Calidad`
- `Artifact_pct`
- `HRV_Stability`
- `Flags`

Mientras no exista una columna continua unica de calidad ya consolidada en el pipeline, la Fase 1 puede usar un `quality[t]` derivado mediante una regla reproducible y conservadora construida a partir de esas columnas. La idea no es "reprocesar" la HRV, sino distinguir entre:

- observacion normal
- observacion degradada
- observacion suprimida

La regla inicial recomendada no debe convertir toda la calidad en una escala discontinua `0.0/0.5/1.0`, porque eso introduce saltos bruscos en el ruido de observacion y puede mover artificialmente el `recovery_state`. Para Fase 1 se define mejor como un multiplicador continuo de la **varianza observacional**:

```text
R_t = sigma_obs_base^2 * obs_var_multiplier[t]
```

La observacion se suprime solo si no existe `lnRMSSD`, si `Calidad == INVALID` o si `Flags` contiene `LAT_NAN`. En los demas casos se usa la observacion, pero se infla `R_t` segun penalizaciones acumulativas:

```text
obs_var_multiplier[t] = 1.0 + penalty[t]

penalty[t] += 1.5   si Calidad == FLAG_mecánico
penalty[t] += 1.0   si HRV_Stability != OK
penalty[t] += 0.5   si Flags contiene BETA_FROZEN
penalty[t] += min(2.0, log1p((Artifact_pct - 5) / 5)) si Artifact_pct > 5
```

Si la implementacion trabaja internamente con desviacion tipica y no con varianza, debe usar:

```text
sigma_obs[t] = sigma_obs_base * sqrt(obs_var_multiplier[t])
```

Esta formulacion conserva informacion util en dias degradados, trata `Artifact_pct` como continuo y evita que un dia con 5.1% de artefactos se comporte igual que uno con artefactos extremos. `BETA_FROZEN` no invalida por si mismo la observacion: solo reduce su peso porque la medicion tiene menor independencia respecto al pipeline interno.

`BETA_FROZEN` merece tratamiento explicito porque no es un error de medicion clasico, sino una senal de dependencia metodologica. Si una proporcion alta de dias contiene este flag, el filtro no debe interpretar esas observaciones como mediciones i.i.d. plenamente independientes. En Fase 1 la mitigacion sera inflar `R_t` mediante `obs_var_multiplier`; no se suprime la observacion salvo que tambien exista una causa de supresion (`INVALID`, `LAT_NAN` o `lnRMSSD` ausente). La prevalencia de `BETA_FROZEN` debe reportarse en metadatos y en el informe de validacion, porque reduce el `N` efectivo informativo aunque el numero de filas sea alto.

Del mismo modo, hay que distinguir claramente entre:

- dia con sesion registrada en `sessions_day`: se usa `load_day`
- dia sin sesion registrada en el pipeline normal: se interpreta como no entrenamiento y se usa `load_day = 0`
- dato de carga ausente por fallo de integridad o sincronizacion conocido: se marca como `load_missing`

Para este proyecto, la regla operativa por defecto es que ausencia de sesion registrada equivale a descanso real. Solo debe marcarse `load_missing` cuando exista evidencia de que hubo entrenamiento no registrado o fallo de integridad del dato. En ese segundo caso, el modelo no deberia fingir descanso, sino degradar el paso de prediccion, por ejemplo aumentando la incertidumbre del proceso y marcando el dia como `ssm_load_missing`.

No obstante, una racha prolongada sin sesiones no debe interpretarse automaticamente como recuperacion fisiologica perfecta. Puede corresponder a descanso planificado, viaje, enfermedad, lesion o una fase contextual no observada. Por eso se define un modo de contexto de carga separado:

```text
load_context_mode = session_recorded   si la fecha existe en sessions_day
load_context_mode = no_session_short   si no hay sesion y el hueco alrededor es <= 3 dias
load_context_mode = no_session_medium  si no hay sesion y el hueco alrededor es 4-6 dias
load_context_mode = no_session_long    si no hay sesion y el hueco alrededor es >= 7 dias
load_context_mode = load_missing       solo si existe evidencia concreta de fallo de integridad
```

Regla inicial:

- `session_recorded`: usar `load_day` y varianza de proceso normal
- `no_session_short`: usar `load_day = 0` y varianza de proceso normal
- `no_session_medium`: usar `load_day = 0` e inflar levemente la varianza de proceso
- `no_session_long`: usar `load_day = 0`, pero inflar claramente la varianza de proceso y marcar baja confianza contextual
- `load_missing`: omitir el termino de carga e inflar la varianza de proceso como missing real

Asi se respeta la semantica operativa actual ("sin sesion registrada = no se entreno") sin permitir que el filtro convierta una semana sin carga en una subida monotona de recuperacion con confianza plena.

### 10.6 Warm-up e inicializacion

La Fase 1 necesita un periodo de arranque explicito. Una configuracion razonable es:

- `warm-up` de 30 observaciones utilizables de alta calidad, no 30 dias calendario
- una observacion cuenta para `warm-up` solo si `obs_suppressed = 0` y `obs_var_multiplier <= 1.25`
- la busqueda inicial se realiza dentro de los primeros 90 dias calendario con datos `CORE`; si no aparecen 30 observaciones utilizables, el `warm-up` se pospone y `ssm_warmup_complete = 0`
- inicializacion del estado con la media robusta o mediana de `lnRMSSD` en ese tramo utilizable
- inicializacion de la varianza del estado con varianza residual, no con la varianza cruda de `lnRMSSD`

Durante este periodo no deberia evaluarse el modelo ni promocionarse ninguna salida al sidecar como senal madura de decision. Conviene dejarlo visible en el output mediante una bandera explicita, por ejemplo `ssm_warmup_complete`.

Esta distincion es importante porque "hay input suficiente para correr el filtro" no equivale a "el estado ya es maduro y comparable con periodos posteriores".

En el arranque real del proyecto, este `warm-up` puede resolverse retrospectivamente con el historico ya disponible, pero solo si el historico contiene 30 observaciones de calidad suficiente. En la primera corrida completa, el modelo debe buscar esas 30 observaciones utilizables dentro del tramo candidato inicial; no debe asumir que los primeros 30 dias calendario bastan. En produccion diaria, el modelo no parte de cero salvo que se fuerce una reinicializacion.

Regla inicial de seleccion del `warm-up`: usar solo dias con observacion no suprimida y `obs_var_multiplier <= 1.25`. Esta regla sustituye el criterio laxo de "menor penalizacion disponible": si el tramo candidato no contiene 30 observaciones con ese nivel de calidad, no se fuerza la inicializacion con datos degradados. El sidecar puede escribirse igualmente, pero el estado queda marcado como no maduro hasta completar el `warm-up`.

La varianza inicial del estado (`P[0]`) debe estimarse sobre variacion corta, no sobre deriva cronica. La regla preferente es:

```text
P[0] = Var(lnRMSSD - rolling_median_30d(lnRMSSD))
```

calculada sobre observaciones utilizables del tramo inicial, con ventana causal cuando sea posible. Si no hay suficientes puntos para una mediana movil de 30 dias, se permite un fallback robusto:

```text
P[0] = (1.4826 * MAD(lnRMSSD - median_warmup))^2
```

El uso de fallback debe quedar documentado en metadatos. La varianza cruda de `lnRMSSD` solo se acepta como diagnostico, no como inicializacion normativa, porque mezcla ruido diario con deriva estacional o de bloque de entrenamiento.

### 10.7 Sidecar minimo recomendado

La primera entrega no debe tocar `FINAL.csv`. Debe escribir un sidecar propio, por ejemplo `ENDURANCE_HRV_ssm_shadow.csv`, con un schema pequeno pero suficiente para validacion, auditoria y comparacion contra baselines.

El conjunto minimo recomendado es:

- `Fecha`
- `ssm_input_ready`
- `ssm_warmup_complete`
- `ssm_recovery_state`
- `ssm_state_lo`
- `ssm_state_hi`
- `ssm_state_var` o `ssm_state_sd`
- `ssm_obs_missing`
- `ssm_load_missing`
- `ssm_load_context_mode`
- `ssm_proc_var_multiplier`
- `ssm_input_quality` o `ssm_quality_mode`
- `ssm_obs_var_multiplier`
- `control_rolling_hrv_7d`
- `control_load_7d`

Ademas, puede anadirse una columna opcional tipo `ssm_shadow_zscore` para facilitar comparaciones visuales y analiticas entre la capa latente y los controles simples.

La logica de este sidecar es doble:

- hacer el modelo auditable sin contaminar el pipeline canonico
- permitir comparacion directa entre el estado latente y controles transparentes

### 10.8 Controles de ingenieria y riesgo principal

El modelo principal debe convivir desde el primer dia con al menos dos controles simples:

- `rolling lnRMSSD` a 7 dias
- una EWMA de `load_day` con semivida corta

De forma opcional, puede anadirse un tercer control estructurado:

- `local level model` univariante con `lnRMSSD` como unica observacion

Este tercer control no sustituye a los baselines transparentes anteriores. Su funcion es mas especifica: comprobar si el modelo principal con carga exogena aporta algo mas que una inferencia latente suavizada de la propia HRV.

No se trata de comparadores ornamentales, sino del liston minimo de ingenieria. Si la capa sombra no supera a estos controles en la prediccion de outcomes independientes, entonces no se ha ganado el derecho a mayor complejidad.

El riesgo tecnico principal sigue siendo el mismo: que el estado latente se comporte, en la practica, como una version suavizada de la propia HRV, con escasa aportacion genuina de la carga. La correccion de alineacion temporal, el uso de `load_day[t-1]` y el tratamiento explicito de calidad reducen ese riesgo, pero no lo eliminan.

La incertidumbre del filtro tampoco debe tratarse como decoracion estadistica. Si `ssm_state_var`, `ssm_state_lo` o `ssm_state_hi` solo se reportan pero no gobiernan ninguna decision de supresion, degradacion o interpretacion, el valor incremental frente a un baseline rolling queda muy debilitado. La Fase 1 debe demostrar que la incertidumbre cambia el comportamiento del sistema sombra en dias de baja calidad, datos faltantes o senal ambigua.

Hay una segunda limitacion tecnica que debe quedar explicita: la identificabilidad practica de `phi` y `beta` es debil con una sola observacion diaria (`lnRMSSD`) y un historico N=1 de unos cientos de dias. Teoricamente, con variabilidad suficiente en `load_day`, el sistema marginalizado permite distinguir persistencia temporal (`phi`) y efecto exogeno de carga (`beta`). En la practica, el efecto esperado de una unidad de carga sobre `lnRMSSD` es pequeno frente al ruido intra-sujeto diario. Si `beta` se estimara libremente en Fase 1, lo esperable no seria una calibracion personal robusta, sino un intervalo de incertidumbre amplio que probablemente cruzaria cero.

Por tanto, congelar o restringir `phi` y `beta` no se justifica solo por "prudencia" metodologica abstracta. Se justifica porque el horizonte disponible todavia no sostiene una estimacion personal estable de esos parametros. La Fase 1 debe tratar `beta` como una hipotesis estructural de baja magnitud que se somete a sensibilidad y validacion externa, no como una medida individual ya aprendida del atleta.

Hay un tercer riesgo importante: el drift lento de `lnRMSSD`. En un seguimiento de 12 meses, la HRV puede moverse por estacionalidad, fase de entrenamiento, cambios cronicos de sueno, peso, hidratacion, enfermedad, temperatura o dispositivo. Si el modelo no separa esa deriva lenta, el `recovery_state` puede absorber tanto variacion corta de recuperacion como desplazamientos de baseline de semanas o meses. Eso contaminaría la interpretacion del estado y tambien la estimacion efectiva de persistencia (`phi`).

Para Fase 1 no se anade por defecto un segundo estado `level_trend`, porque eso cambia el modelo de una dimension a dos y reduce la parsimonia inicial. La mitigacion obligatoria es mas auditable:

- calcular una referencia lenta de `lnRMSSD`, por ejemplo mediana movil de 60-90 dias con ventana causal
- reportar una version centrada o residual `lnRMSSD_minus_slow_baseline` como diagnostico
- comparar el `recovery_state` contra ese baseline lento para estimar cuanta varianza del estado es deriva cronica
- marcar la validacion como contaminada por drift si el estado sigue mas al baseline lento que a las variaciones agudas o si la ventaja sobre baselines desaparece al usar la senal centrada

Solo si este diagnostico muestra que la deriva cronica domina y, al mismo tiempo, el modelo demuestra valor externo suficiente, tiene sentido abrir una extension con dos estados `[recovery_state, level_trend]`. En caso contrario, introducir `level_trend` en Fase 1 seria complejidad antes de evidencia.

Por eso, la salida correcta de una Fase 1 fallida no seria "hacer el modelo mas listo", sino aceptar una de estas conclusiones:

- la carga disponible no anade suficiente informacion sobre el outcome elegido
- la observacion HRV es demasiado ambigua para sostener un estado latente util en esta formulacion
- la senal esta dominada por deriva lenta de baseline y no por variaciones de recuperacion a escala de dias
- la capa sombra no mejora materialmente a los baselines simples

### 10.9 Conclusion operativa

El Bloque 3 no deberia cerrarse con una arquitectura ambiciosa, sino con una especificacion minima, coherente y trazable. Para este repositorio, esa especificacion minima queda resumida asi:

- estado unico de recuperacion autonómica
- observacion canonica `lnRMSSD` desde `CORE`
- entrada exogena `load_day[t-1]` desde `sessions_day`
- ARX-Kalman univariado como candidato principal, condicionado a prueba `local level + regresion de residuos`
- parametros fuertemente restringidos
- degradacion explicita por calidad y `missingness`
- sidecar sombra propio con incertidumbre, flags y controles simples

Bajo esta formulacion, la Fase 1 ya queda suficientemente cerrada como para pasar de la investigacion metodologica a una implementacion controlada. La condicion para abrir una Fase 2 no es que el modelo sea elegante, sino que esta version minima demuestre utilidad incremental real en validacion prospectiva.

---

## 11. Sintesis critica del Bloque 4

Esta sintesis cierra el Bloque 4 como protocolo de validacion prospectiva para la Fase 1 ya definida en los bloques anteriores. Si el Bloque 3 respondia a la pregunta "que modelo minimo merece ponerse a prueba", el Bloque 4 responde a la pregunta complementaria: "como demostrar si esa capa sombra aporta valor real usando outcomes externos y comparaciones honestas".

El objetivo no es convertir la validacion en un festival de metricas, sino fijar un marco suficiente para distinguir tres escenarios:

- el modelo aporta senal incremental real
- el modelo no mejora a referencias simples
- el modelo parece sofisticado, pero solo reordena la misma informacion que ya teniamos

### 11.1 Principio rector

La validacion debe seguir tres reglas basicas:

- el modelo no se evalua contra la propia HRV
- la evaluacion debe ser prospectiva y fuera de muestra
- el valor del modelo debe juzgarse frente a baselines simples, no solo por su ajuste interno

En la practica, esto significa que la capa sombra debe producir un estado diario que luego se contrasta contra outcomes funcionales o subjetivos posteriores, nunca contra una reinterpretacion de `lnRMSSD` del mismo dia.

### 11.2 Outcome principal: sesion comparable

El outcome principal mas defendible para una Fase 1 realista es la calidad funcional de la siguiente sesion comparable. La idea central no es exigir un test maximo semanal, sino extraer una medida repetible de tolerancia o eficiencia a partir de una familia de sesiones suficientemente parecidas a lo largo del tiempo.

En este repositorio la definicion no debe quedar como una idea generica, porque `ENDURANCE_HRV_sessions_day.csv` ya contiene columnas suficientes para etiquetar familias de sesion. Una sesion comparable deberia compartir, como minimo:

- tipo de estimulo: `has_aerobic`, `has_strength`, `has_mobility`
- banda de intensidad: `intensity_cat_day`
- duracion: `total_duration_min`
- carga interna: `load_day`
- contenido intenso: `z3_min_day`, `work_n_blocks_day`, `intensity_clustering_level`

La regla inicial de comparabilidad para dos dias de sesion `a` y `b` debe ser conservadora:

- mismo valor de `has_aerobic`
- mismo valor de `has_strength` cuando una de las dos sesiones sea de fuerza pura
- mismo `intensity_cat_day`
- ratio de `total_duration_min` entre `0.75` y `1.33`
- ratio de `load_day` entre `0.70` y `1.43`, salvo que `load_day` sea cero o falte
- diferencia de `z3_min_day` dentro de una tolerancia predefinida por familia

Las familias minimas a declarar en metadata son:

- `aerobic_long_z2`: `has_aerobic=1`, `intensity_cat_day=Z2`, `total_duration_min >= 75`
- `aerobic_short_z2`: `has_aerobic=1`, `intensity_cat_day=Z2`, `total_duration_min < 75`
- `aerobic_z3_tempo`: `has_aerobic=1`, `intensity_cat_day=Z3`, `total_duration_min` entre 30 y 60
- `aerobic_intervals`: `has_aerobic=1`, `intensity_clustering_level=high` o `work_n_blocks_day >= 3`
- `strength_only`: `has_strength=1`, `has_aerobic=0`

Estas familias son un punto de partida auditable, no una ontologia deportiva completa. Si una familia no acumula suficientes sesiones, se excluye de la validacion principal y se informa su cobertura.

Cuando sea posible, es preferible que esa sesion comparable sea relativamente controlada o submaxima, porque eso reduce ruido motivacional y hace mas interpretable el outcome. En ese contexto, la eficiencia a carga interna parecida o la respuesta funcional esperada de la sesion suelen ser mejores targets que el "rendimiento absoluto" sin contexto.

La formulacion metodologica correcta no es "el mejor dia del atleta", sino "como tolera hoy un estimulo parecido al que ya conocemos". Por eso, el outcome principal de arranque debe expresarse como una desviacion funcional robusta dentro de familia:

```text
metric_session[t] = metrica funcional elegida para la familia
FDS[t] = (metric_session[t] - mediana_rolling_8_familia) / MAD_rolling_8_familia
```

`FDS` significa `functional_deviation_score`. Debe orientarse para que valores mas altos indiquen mejor tolerancia funcional. Si se usa una metrica donde menor es mejor, como `cardiac_drift_worst` o `rpe_max_day`, el signo debe invertirse antes de calcular `FDS`.

Metricas candidatas por orden de preferencia, segun cobertura real:

- eficiencia de la sesion
- desviacion respecto al rango esperado de esa familia
- necesidad de modificar, recortar o degradar la sesion prevista
- pass/fail funcional definido antes de observar la HRV

Una metrica inicial implementable con columnas canonicas es `work_total_min_day / max(load_day, 1)`, pero solo debe usarse dentro de familias comparables y con las restricciones de duracion/carga anteriores. No debe interpretarse como eficiencia fisiologica universal: es un proxy pragmatico de trabajo observado por unidad de carga interna, util para validacion N=1 si y solo si no premia artificialmente sesiones largas muy suaves ni penaliza sesiones intensas planificadas. Cuando existan mejores senales de la sesion, pueden priorizarse `cardiac_drift_worst`, `effort_above_anchor_aerobic`, `effort_above_typical_aerobic`, `rpe_max_day` o un `pass/fail` funcional predefinido.

Conviene tratar estas variantes como expresiones de una misma idea, no como outcomes incompatibles entre si.

### 11.3 Outcome secundario y frecuencia minima

El outcome secundario recomendado sigue siendo `PRS`, `wellness` o una medida equivalente de recuperacion subjetiva en `D+1` o `D+2`, recogida antes de que el atleta vea la HRV o el resultado del modelo. Este tipo de outcome es menos fuerte que uno funcional, pero mucho mas frecuente y util para sostener una validacion diaria sin caer en circularidad trivial.

Respecto a la frecuencia del outcome principal, la lectura mas prudente es:

- idealmente, al menos dos observaciones funcionales por semana
- como minimo operativo, una observacion cada 7-10 dias
- si el outcome principal aparece menos de unas pocas decenas de veces por ano, la validacion funcional se vuelve fragil

Cuando el outcome funcional es demasiado raro, la respuesta correcta no es fingir densidad estadistica, sino:

- ampliar la ventana de evaluacion
- dar mas peso a los outcomes secundarios
- o replantear la definicion de sesion comparable

El mensaje metodologico de fondo es simple: un modelo diario puede entrenarse con serie diaria, pero no puede demostrar valor funcional robusto si casi nunca se observa el target funcional que pretende anticipar.

### 11.4 Diseno temporal recomendado

Para aproximadamente 12 meses de datos diarios, la estrategia mas defendible sigue siendo una validacion `walk-forward` o `rolling-origin` con ventana de entrenamiento expansiva. El modelo se ajusta con toda la historia disponible hasta un punto y se evalua en un bloque futuro, repitiendo el proceso varias veces.

No es necesario fijar un unico esquema rigido, pero si mantener estos principios:

- `warm-up` inicial suficiente para estabilizar estado y parametros
- bloques futuros claramente separados del tramo de entrenamiento
- multiples iteraciones fuera de muestra, no un unico corte afortunado
- alineacion temporal correcta entre estado estimado y outcome posterior

En una implementacion pragmatica, el bloque de test puede ser semanal, quincenal o mensual, segun la frecuencia real del outcome principal. Si el target funcional es escaso, los bloques deberian ser algo mas amplios para acumular suficientes observaciones evaluables.

Antes de interpretar el `walk-forward` como decisivo, hay que dimensionar el problema. Con unos 12 meses de datos diarios, un `warm-up` inicial y un outcome funcional observado solo en sesiones comparables, el numero efectivo de puntos por bloque puede ser bajo. Un bloque mensual contiene muchas observaciones de HRV, pero puede contener solo unas pocas observaciones funcionales si la sesion comparable aparece 1-2 veces por semana.

Por tanto, la validacion debe incluir un analisis ex-ante de potencia o `minimum detectable effect` (`MDE`) para el outcome principal elegido. Como minimo debe reportar:

- numero esperado de outcomes funcionales por bloque
- numero total esperado de outcomes fuera de muestra
- MDE expresado en desviaciones estandar del outcome
- diferencia minima de RMSE/MAE que el diseno podria detectar de forma razonable

Regla operativa inicial: si el MDE del outcome funcional principal supera aproximadamente `0.3 SD`, la validacion funcional debe declararse `no decisiva` para promocion por si sola. En ese escenario, el outcome funcional sigue siendo evidencia externa importante, pero la evaluacion debe apoyarse mas en outcomes secundarios densos, como wellness o recuperacion subjetiva, siempre manteniendo la separacion anti-circularidad.

### 11.5 Baselines oficiales

El modelo de Fase 1 no se justifica por tener estado oculto, sino por superar comparadores simples y razonables. El conjunto minimo de baselines para este bloque deberia incluir:

- un baseline de HRV suavizada, por ejemplo `rolling lnRMSSD` o una `EWMA`
- un baseline de carga reciente usando columnas canonicas ya existentes en `ENDURANCE_HRV_sessions_day.csv`, especialmente `load_3d`, `load_7d`, `load_14d` y `load_28d`
- un baseline intermedio que combine de forma lineal HRV y carga
- el `gate_final` actual de `ENDURANCE_HRV_master_FINAL.csv` como baseline informativo operativo
- un baseline operativo compuesto `gate_final + carga`, por ejemplo `gate_final` codificado de forma binaria u ordinal combinado con `load_7d` o `load_3d` mediante una regla lineal/logistica simple
- un baseline contextual de sueno desde `ENDURANCE_HRV_sleep.csv`, por ejemplo `polar_sleep_score` reciente o variables simples de duracion/eficiencia

Ese baseline intermedio es importante porque evita que la capa sombra gane solo frente a comparadores demasiado pobres. Una regresion lineal simple o un score aditivo HRV+carga es una comparacion mucho mas justa que oponer el modelo solo a una media movil.

La regla de repo es importante: no se debe construir una EWMA paralela de carga si el pipeline ya expone una metrica canonica equivalente. Para Fase 1, el comparador de carga principal debe ser `load_7d` y no una `EWMA(load_day)` ad hoc, salvo que el reporte indique explicitamente que se trata de un experimento auxiliar y no del baseline canonico.

Pero ese baseline intermedio no debe replicar el mismo kernel temporal implicito del filtro. Si se usa una combinacion lineal con las mismas EWMAs o con una constante temporal equivalente a la del SSM, la comparacion queda casi tautologica: el filtro y el baseline pueden empatar por construccion. Para que la validacion sea informativa, los baselines deben ser simples pero estructuralmente distinguibles, por ejemplo:

- media movil rectangular de `lnRMSSD`
- `load_3d` o `load_7d` como acumulados discretos
- regresion lineal con features simples como `lnRMSSD[t]`, `lnRMSSD_7d_mean`, `load_day[t-1]` o `load_3d`
- una EWMA con parametros predefinidos y distintos de los usados por el filtro

La pregunta correcta no es si el SSM bate a un clon algebraico de si mismo, sino si aporta algo frente a reglas lineales transparentes que no comparten exactamente su misma memoria temporal.

`acwr_simple_prev`, `monotony_7d_prev` y `strain_7d_prev` deben conservarse como comparadores secundarios porque ya forman parte de la capa de carga canonica del repositorio. Del mismo modo, `intensity_clustering_flag` e `intensity_blackhole_flag` no son baselines numericos principales, pero si deben usarse para estratificar o auditar fallos del modelo en contextos de carga cualitativamente distinta.

El `gate_final` no compite con la Fase 1 como mecanismo operativo, porque la capa SSM sigue en sombra y no debe tocar el gate. Pero si compite como referencia de valor: antes de abrir Fase 2 o visibilidad, hay que saber si la nueva senal aporta algo sobre lo que el sistema actual ya decide. Aun asi, el `gate_final` no es un baseline neutro ni independiente: ya contiene informacion derivada de `lnRMSSD` mediante `ROLL3`, `baseline_ln` y vetos agudos. Por eso debe reportarse como referencia operativa, pero no como unico liston de promocion. Si se evalua visibilidad o advisory, la comparacion justa es contra `gate_final + carga canonica`, no solo contra `gate-only`.

El baseline de sueno tambien debe ser contextual, no una nueva observacion del SSM en Fase 1. Si `polar_sleep_score` o variables simples de sueno explican mejor el outcome que el estado latente HRV+carga, la conclusion no es meter sueno inmediatamente en el filtro, sino reconocer que el liston real de utilidad es mas alto que `lnRMSSD` suavizado.

### 11.6 Dias discordantes

Uno de los puntos de mas valor del Bloque 4 es que explicita donde deberia demostrar utilidad adicional la capa sombra: en los dias donde las senales disponibles no cuentan la misma historia.

La definicion operativa mas defendible de dia discordante es aquella en que HRV, carga reciente y recuperacion subjetiva no apuntan en la misma direccion, siempre que el desacuerdo tenga magnitud suficiente y no sea solo ruido menor.

Por tanto, conviene definir:

- un baseline personal para HRV
- un baseline movil para carga reciente
- un baseline movil para la senal subjetiva
- y una zona neutra alrededor de la normalidad para no etiquetar como discordancia fluctuaciones pequenas

Pero este subgrupo tiene un riesgo metodologico claro: si se define la discordancia usando las mismas senales que luego entran en el SSM o en sus baselines principales, se puede dar ventaja por construccion a cualquier combinador lineal. En dias donde HRV y carga discrepan, una combinacion lineal puede parecer superior simplemente porque promedia senales opuestas, no porque haya inferido un estado fisiologico mas real.

Para evitar ese sesgo, el protocolo debe distinguir dos usos:

- **discordancia diagnostica**: describe dias donde HRV, carga y subjetivo no coinciden, util para auditoria cualitativa
- **discordancia de evaluacion**: subconjunto usado para medir valor incremental, definido preferentemente con al menos una senal externa al SSM, por ejemplo recuperacion subjetiva o wellness frente a HRV/carga

La regla recomendada es que la discordancia de evaluacion se pre-registre y use, siempre que haya datos, una senal que no entre en el modelo de Fase 1. Por ejemplo, discrepancia entre `wellness_subjective` y `lnRMSSD`, o entre recuperacion subjetiva y carga reciente. Si se usa una definicion basada solo en HRV+carga, el resultado debe marcarse como analisis exploratorio, no como evidencia fuerte de valor incremental.

Ademas, el rendimiento en dias discordantes debe compararse contra un combinador lineal OLS de los mismos baselines. Si el SSM solo iguala a ese combinador trivial en el subgrupo discordante, no demuestra senal latente nueva; demuestra que combinar senales discordantes mejora frente a mirarlas por separado.

Tambien hay que dimensionar el subgrupo. Si los dias discordantes representan 15-20% del historico, el N efectivo por bloque puede ser muy bajo. Por tanto, el reporte debe incluir numero total de dias discordantes evaluables, numero por bloque y una etiqueta de fiabilidad. Como regla inicial, menos de 30 dias discordantes evaluables deberia considerarse evidencia exploratoria, no decisiva.

La conclusion metodologica importante es que no basta con medir rendimiento global. Tambien hay que medir si el modelo conserva ventaja en el subgrupo de dias discordantes. Si solo mejora en el promedio total pero no en esos dias ambiguos, es posible que el modelo este aprendiendo sobre todo la tendencia media del sistema.

### 11.7 Que significa ganar de verdad

El exito del modelo no debe definirse como mejor ajuste retrospectivo ni como correlacion bonita con la HRV. Debe definirse como mejora prospectiva y repetible sobre baselines simples en outcomes externos.

Las formas mas utiles de evaluar esa mejora son:

- menor error fuera de muestra en el outcome principal
- mejor capacidad para acertar la direccion del cambio
- mejor lectura de dias discordantes
- estabilidad razonable al cambiar el esquema temporal de validacion

No deben tratarse como leyes universales, pero si deben quedar pre-registrados antes del primer ajuste del modelo para evitar sesgo de confirmacion posterior. La version 1 de `ENDURANCE_HRV_ssm_shadow_metadata.json` debe incluir un bloque `go_no_go_criteria` con esta estructura:

```yaml
go_no_go_criteria:
  required_all:
    rmse_outcome_principal_improvement_pct: ">= 8% vs best baseline"
    sign_accuracy_outcome_principal: ">= 0.55 absolute"
    replication_across_folds: ">= 3 of 5 walk-forward folds with positive direction"
  required_at_least_one:
    discordant_days_advantage:
      rmse_improvement_pct: ">= 12% on discordant subset"
    subjective_outcome_advantage:
      prs_mae_improvement_points: ">= 0.25"
  veto_conditions:
    outcome_viability_fail: "no existe outcome posterior externo con lag documentado y cobertura suficiente"
    degeneracy_test_fail: "OLS(EWMA_hrv, EWMA_load) reproduces Kalman state within tolerance"
    calibration_fail: "90% predictive lnRMSSD interval coverage outside [0.80, 0.95] or clearly non-uniform PIT in test folds"
    stability_fail: "phi sensitivity produces RMSE swings > 5% for phi in [0.88, 0.96]"
```

Estos numeros sustituyen cualquier lectura post-hoc de "mejora consistente". La reduccion de `RMSE` del 8% se usa como umbral go/no-go pragmatico porque el N efectivo puede ser limitado; el 10% queda como objetivo deseable, no como requisito absoluto. La mejora subjetiva baja de 0.30 a 0.25 puntos para que sea coherente con el caracter secundario y mas denso de ese outcome.

Si el MDE ex-ante del outcome principal es > 0.3 sd, estos umbrales se reportan como descriptivos, no como prueba decisiva de promocion. En ese caso, el documento de validacion debe etiquetar la evidencia funcional como `no_decisiva` y apoyar la decision en outcomes secundarios mas densos, sin sobreinterpretar el resultado.

Con esa cautela, si hubiera que elegir solo dos condiciones nucleares para justificar una Fase 2, serian estas:

- mejora prospectiva repetida sobre el mejor baseline simple o semiestructurado
- valor incremental claro en dias discordantes

La estabilidad del estado, la calibracion de incertidumbre y la robustez ante `missingness` no son simples criterios de apoyo: actuan como vetos. Si el estado es algebraicamente indistinguible de un baseline lineal equivalente, si los intervalos del 90% estan claramente mal calibrados, o si la sensibilidad a `phi` cambia materialmente el resultado, no se abre Fase 2 aunque alguna metrica puntual mejore.

### 11.8 Coste de error y uso futuro

El Bloque 4 tambien obliga a reconocer que la lectura de las metricas depende del uso operativo futuro. Un sistema orientado a prevenir dias realmente malos puede valorar mas la sensibilidad; un sistema orientado a no erosionar la confianza del usuario puede penalizar mas las falsas alarmas.

En esta fase, como el modelo sigue en `shadow mode`, la postura mas prudente es no fijar todavia una unica filosofia de umbral, sino reportar al menos:

- capacidad de detectar outcomes funcionalmente malos
- tasa de falsas alarmas frente a reglas simples
- comportamiento comparado en dias faciles y en dias discordantes

Eso permite que la decision de promocion a Fase 2 no dependa solo de una metrica aislada, sino del equilibrio real entre utilidad y coste operativo.

### 11.9 Conclusion operativa

El Bloque 4 queda suficientemente cerrado si se asume esta secuencia:

- definir un outcome principal basado en sesion comparable
- sostener la validacion diaria con outcomes secundarios no circulares
- usar validacion prospectiva por bloques con `walk-forward` o `rolling-origin`
- comparar contra HRV suavizada, carga reciente y una combinacion lineal simple de ambas
- medir rendimiento global y rendimiento en dias discordantes
- exigir mejora repetida antes de abrir la puerta a mas complejidad

Bajo esta lectura, la Fase 1 ya no es solo una idea metodologica, sino una hipotesis falsable: si la capa sombra no supera de forma creible a los baselines simples en este protocolo, no merece una Fase 2. Si en cambio aporta senal justo donde las reglas simples dejan mas ambiguedad, entonces la complejizacion posterior si queda justificada.

---

## 12. Sintesis critica del Bloque 5

Esta sintesis cierra el Bloque 5 como marco de integracion operativa y gobernanza para una senal de estado latente que ya ha demostrado valor incremental en modo sombra. El objetivo aqui ya no es justificar el modelo ni definir su validacion, sino responder a una pregunta mas pragmatica: como exponer una senal potencialmente util sin sobredimensionarla, sin contaminar la evaluacion futura y sin poner en riesgo el sistema decisor actual.

La idea central es que una senal latente validada no pasa directamente de "sidecar tecnico" a "decisor de carga". Entre ambos extremos hace falta una capa de gobernanza explicita: reglas de exposicion, interpretacion, degradacion, auditoria y rollback.

### 12.1 Principio rector

El modelo debe entenderse como un sistema de apoyo a la decision, no como un sustituto del juicio operativo existente. Su funcion inicial no es gobernar el `gate`, sino anadir contexto sobre autonomia y recuperacion cuando ese contexto ha demostrado utilidad frente a outcomes externos.

Por tanto, toda integracion prudente debe respetar tres reglas:

- la senal visible debe ser mas conservadora que la senal interna del modelo
- la incertidumbre debe gobernar la visibilidad, no solo la magnitud del estado
- cualquier promocion a uso visible o activo debe ser reversible

### 12.2 Que deberia mostrarse primero

La primera promocion no deberia consistir en mostrar el estado latente crudo ni en emitir recomendaciones directas de carga. La via mas prudente es una exposicion gradual.

El orden razonable de promocion es:

- primero, una visualizacion experimental de tendencia o contexto
- despues, una lectura textual breve y no vinculante
- solo mas tarde, si la utilidad sigue demostrada, una senal advisory o bandera suave
- nunca en Fase 1 una modificacion automatica del `gate` o de la prescripcion de carga

Esto implica que la salida visible debe ser una traduccion operativa del modelo, no el modelo mismo. El usuario o decisor no necesita ver `xi_t`, sino una lectura contextual prudente del tipo:

- tendencia favorable
- senal estable
- recuperacion parcialmente reducida
- datos insuficientes o confianza baja

### 12.3 Forma de presentacion recomendada

La salida mas defendible para una primera integracion visible es una combinacion pequena de elementos:

- una senal resumida o categoria interpretable
- una indicacion de tendencia reciente
- un indicador de confianza o calidad
- una explicacion breve de contexto

Conviene evitar dos extremos:

- un numero crudo sin interpretacion
- un semaforo demasiado prescriptivo que sugiera decisiones automaticas

La forma mas prudente no es "oraculo de readiness", sino "contexto adicional sobre recuperacion autonómica". En consecuencia, el lenguaje visible deberia ser descriptivo antes que imperativo.

### 12.4 Explicaciones minimas

Para que la senal sea interpretable sin vender causalidad falsa, toda salida visible deberia poder responder de forma sencilla a tres preguntas:

- que resume esta senal
- por que hoy se muestra asi
- que no significa

Una explicacion minima defendible deberia incluir:

- que la senal resume HRV diaria filtrada junto con el contexto de carga reciente
- que expresa autonomia o recuperacion, no fitness mecanico ni rendimiento garantizado
- que un valor bajo o una tendencia desfavorable no implican por si solos que deba cambiarse la sesion

No hace falta un marco formal de explicabilidad compleja para esta fase. Basta con una explicacion operativa sobria, consistente y alineada con los outcomes que el modelo ha demostrado anticipar.

### 12.5 Incertidumbre y reglas de supresion

La incertidumbre del modelo no debe quedar oculta. Debe traducirse a reglas practicas de uso, degradacion o supresion.

La logica general deberia ser esta:

- si la incertidumbre es baja, la senal puede mostrarse con normalidad
- si la incertidumbre es moderada, la senal puede mostrarse con advertencia
- si la incertidumbre es alta, la senal no deberia presentarse como interpretable ese dia

Esto equivale a reconocer que no todos los dias merecen una lectura diaria del modelo. Cuando la cobertura o la calidad de datos son pobres, la salida correcta no es inventar confianza, sino reducir visibilidad y apoyarse en referencias mas simples y auditables.

Estas reglas solo son defendibles si la incertidumbre esta empiricamente calibrada. El intervalo del estado latente no es observable de forma directa, por lo que la comprobacion minima debe hacerse sobre la prediccion de la observacion (`lnRMSSD`) y, si se generan intervalos para outcomes, tambien sobre esos outcomes. Antes de usar `ssm_state_var`, `ssm_state_lo` o `ssm_state_hi` para gobernar visibilidad, el reporte de validacion debe demostrar cobertura predictiva razonable y un diagnostico `PIT` aceptable. Si la cobertura del 90% queda fuera de `[0.80, 0.95]` o el `PIT` muestra sesgo claro, la incertidumbre puede reportarse como diagnostico tecnico, pero no debe usarse para activar reglas visibles de confianza/supresion.

### 12.6 Datos pobres, `missingness` y degradacion

La integracion operativa debe asumir de partida que habra dias sin HRV valida, dias con calidad dudosa y dias con carga incompleta. La respuesta correcta es una degradacion gradual, no una falsa continuidad.

Una politica prudente incluye:

- propagacion temporal del estado durante ausencias cortas
- aumento explicito de incertidumbre cuando faltan observaciones
- supresion o congelacion de la salida visible cuando la ausencia se prolonga
- fallback a baselines simples cuando la senal latente deja de ser fiable

El principio rector es simple: cuando el modelo pierde apoyo observacional, debe parecerse cada vez menos a un indicador "inteligente" y cada vez mas a una referencia conservadora o incluso a ausencia de senal.

### 12.7 Como evitar contaminar la validacion futura

Una vez que la senal gana visibilidad, aparece un problema nuevo: el usuario o el decisor pueden empezar a comportarse de forma distinta al verla, y entonces la validacion futura deja de medir solo el modelo y empieza a medir tambien el efecto de esa visibilidad.

Por eso, toda promocion visible deberia ir acompanada de salvaguardas como:

- etiquetar la senal como experimental o informativa en sus primeras fases
- separar visualmente esa capa de los indicadores consolidados
- registrar cuando una decision operativa ha estado influida por la senal
- analizar por separado los dias potencialmente contaminados

La gobernanza correcta no intenta negar esta contaminacion, sino hacerla visible y manejable.

### 12.8 Que componente merece promocion primero

Si el modelo demuestra valor suficiente, el primer componente que merece promocion no es una recomendacion de carga ni un alarmismo binario, sino una capa contextual de baja agresividad.

En la practica, lo primero que deberia promocionarse es:

- una visualizacion de tendencia de la recuperacion/autonomia
- un estado de confianza o fiabilidad
- y, opcionalmente, una nota contextual breve

Las alertas mas interpretativas o las banderas tipo "atencion" solo deberian entrar despues, y siempre como senal advisory, no como automatismo decisor.

### 12.9 Salvaguardas antes de influir en decisiones

El paso desde una senal visible a una senal con influencia sobre decisiones de carga exige un umbral de prudencia mucho mayor. Antes de llegar ahi, deberian cumplirse varias condiciones simultaneas:

- evidencia repetida de superioridad sobre baselines en validacion prospectiva
- estabilidad razonable de la senal a lo largo del tiempo
- reglas claras de supresion cuando la confianza cae
- posibilidad explicita de veto o ignorar la recomendacion
- comparacion continua con el sistema actual, sin sustitucion automatica

La idea clave es esta: una senal puede ser util mucho antes de ser apta para recomendar acciones. El hecho de que explique mejor la recuperacion no implica automaticamente que deba gobernar la carga.

### 12.10 Auditoria y rollback

Todo modelo visible debe ir acompanado de un mecanismo de auditoria periodica y de criterios explicitos de despromocion. No basta con definir cuando se promociona; tambien hay que definir cuando se retira o vuelve a sombra.

La auditoria periodica deberia revisar al menos:

- rendimiento reciente frente a baselines
- frecuencia de supresiones y degradaciones
- comportamiento en dias discordantes
- estabilidad de la distribucion del estado y de la cobertura de datos
- utilidad operativa percibida frente a ruido o confusion

El rollback deberia contemplar al menos dos niveles:

- vuelta a sombra invisible, si la senal pierde valor o genera confusion
- desconexion operativa, si hay deriva tecnica, cambio estructural no modelado o perdida fuerte de integridad de datos

Lo importante no es fijar hoy un umbral universal para cada uno de esos eventos, sino dejar claro que la promocion nunca es irreversible.

### 12.11 Conclusion operativa

El Bloque 5 queda suficientemente cerrado si se asume esta secuencia de gobernanza:

- primero, sidecar tecnico y validacion en sombra
- despues, visualizacion experimental y contextual
- luego, si sigue aportando valor, senal visible de baja agresividad
- mas tarde, y solo con salvaguardas fuertes, capacidad limitada de influir en decisiones
- siempre con auditoria periodica, degradacion conservadora y rollback posible

Bajo esta lectura, la pregunta ya no es si el modelo "puede" integrarse, sino bajo que condiciones merece hacerse visible sin crear una falsa sensacion de precision. La respuesta prudente es que la senal debe informar antes de sugerir, y sugerir antes de influir.

---

## 13. Plan de implementacion

Esta seccion traduce la posicion metodologica consolidada del documento a un plan de ejecucion concreto. El objetivo ya no es seguir ampliando el espacio teorico, sino definir la secuencia minima de trabajo para llevar la Fase 1 a codigo y validacion reproducible.

### 13.1 Alcance cerrado de Fase 1

La Fase 1 implementable queda cerrada con estas restricciones:

- no modifica `FINAL.csv`
- no modifica el `gate`
- no introduce `Busso`, `MCMC`, `HMM` ni multimodalidad fuerte
- no necesita dependencias nuevas fuera de `numpy` y `scipy`
- no expone una senal visible al usuario final

Su output es exclusivamente un sidecar tecnico en modo sombra, listo para auditoria y validacion.

### 13.2 Entregables tecnicos

Los entregables minimos recomendados son:

- `build_hrv_ssm.py`
- `ENDURANCE_HRV_ssm_shadow.csv`
- `ENDURANCE_HRV_ssm_shadow_metadata.json`
- un script o modulo de validacion prospectiva reproducible
- documentacion minima de contrato del sidecar y de su protocolo de evaluacion

La logica de esta lista es separar claramente:

- generacion del estado latente
- evaluacion del modelo
- gobernanza documental

### 13.3 Tareas concretas de codigo

#### Tarea 0 — Auditoria previa de outcomes

Antes de implementar el modelo de estado como componente evaluable, ejecutar una auditoria de outcomes sobre los datos reales disponibles.

Objetivo: confirmar que existe al menos un outcome posterior, externo y reproducible contra el que validar el sidecar sin circularidad ni ambiguedad temporal.

La auditoria debe revisar:

- `ENDURANCE_HRV_sessions_day.csv`:
  - que metricas candidatas como `cardiac_drift_worst`, `effort_above_anchor_aerobic`, `effort_above_typical_aerobic` y `rpe_max_day` se usen solo como resultado de una sesion posterior a la estimacion del estado
  - que exista una regla de "siguiente sesion comparable" y no una comparacion con la misma fecha sin justificar el lag
  - cobertura real por familia, por fold y por horizonte (`t+1...t+7`)
- `ENDURANCE_HRV_wellness_subjective.csv`:
  - columnas disponibles y porcentaje de dias con datos numericos reales
  - diferencia entre campos estructurados y comentarios libres
  - semantica temporal documentada: si el registro de `Fecha=t` describe estado de `t`, recuperacion de `t-1` o percepcion posterior
  - consistencia del lag elegido para `wellness_D+1` o `PRS_D+1`

La salida minima debe ser un bloque de metadata o reporte con:

- `primary_outcome_available`
- `secondary_outcome_available`
- `primary_outcome_name`
- `primary_outcome_lag_rule`
- `secondary_outcome_name`
- `secondary_outcome_lag_rule`
- `outcome_coverage_by_fold`
- `outcome_temporal_semantics_status`
- `outcome_audit_status`

Si `outcome_audit_status != pass`, no debe iniciarse la Tarea 3 como modelo validable. Se puede construir un prototipo tecnico del sidecar para inspeccion, pero la Fase 1 queda etiquetada como `no_validatable_current_data` hasta definir o recolectar un outcome viable.

#### Tarea 1 — Extraccion y alineacion de datos

Implementar la lectura y alineacion minima de:

- `ENDURANCE_HRV_master_CORE.csv`
- `ENDURANCE_HRV_sessions_day.csv`

con estas decisiones ya fijadas:

- observacion = `lnRMSSD`
- input exogeno = `load_day[t-1]`
- eje temporal diario por `Fecha`

Esta tarea debe resolver tambien:

- joins por fecha
- identificacion de `missingness`
- aplicacion de la regla operativa "sin sesion registrada = descanso real (`load_day = 0`)"
- distincion entre descanso real, racha prolongada sin sesiones y fallo puntual de integridad de carga
- generacion de `load_context_mode` y `proc_var_multiplier` para que los huecos largos sin sesiones no se interpreten como recuperacion con confianza plena

#### Tarea 2 — Mapeo de calidad y degradacion

Implementar una funcion reproducible que derive `quality[t]` desde columnas canonicas del `CORE`, usando al menos:

- `Calidad`
- `Artifact_pct`
- `HRV_Stability`
- `Flags`

La salida de esta capa debe permitir:

- observacion valida
- observacion degradada
- observacion suprimida

La regla inicial recomendada para esta fase debe devolver dos piezas separadas:

- `obs_suppressed`: verdadero solo si `lnRMSSD` falta, `Calidad == INVALID` o `Flags` contiene `LAT_NAN`
- `obs_var_multiplier`: multiplicador continuo de la varianza observacional, con base 1.0 y penalizaciones acumulativas por `FLAG_mecánico`, `HRV_Stability != OK`, `BETA_FROZEN` y exceso continuo de `Artifact_pct`

Regla de referencia:

```text
obs_suppressed = lnRMSSD falta OR Calidad == INVALID OR LAT_NAN en Flags

obs_var_multiplier = 1.0 + penalty
penalty += 1.5 si Calidad == FLAG_mecánico
penalty += 1.0 si HRV_Stability != OK
penalty += 0.5 si BETA_FROZEN en Flags
penalty += min(2.0, log1p((Artifact_pct - 5) / 5)) si Artifact_pct > 5
```

y gobernar:

- `ssm_obs_missing`
- `ssm_input_quality` o `ssm_quality_mode`
- inflado de ruido observacional

La implementacion debe dejar esta regla encapsulada y versionada para poder refinarla mas adelante sin ambiguedad historica.

#### Tarea 3 — Modelo de estado minimo

Implementar la arquitectura lineal minima y su comparador estructural obligatorio.

Arquitectura candidata: filtro ARX-Kalman univariado con carga exogena:

```text
recovery_state[t] = phi * recovery_state[t-1] + beta * load_day[t-1] + eta_t
lnRMSSD[t] = recovery_state[t] + epsilon_t
```

Comparador estructural obligatorio: `local level model` HRV-only mas regresion auxiliar de residuos:

```text
recovery_state[t] = recovery_state[t-1] + eta_t
lnRMSSD[t] = recovery_state[t] + epsilon_t
residual_or_innovation[t] ~ alpha + gamma * load_day[t-1]
```

Este comparador no debe degradarse a "control menor": es la prueba mas limpia de si la carga aporta senal incremental antes de integrarla dentro de la ecuacion de estado. Si iguala o supera al ARX-Kalman, el resultado no obliga a implementar dos modelos en produccion; obliga a detener la promocion del ARX como arquitectura preferente.

Pre-test diagnostico obligatorio de utilidad de carga:

```text
lnRMSSD[t] ~ lnRMSSD[t-1] + lnRMSSD[t-3] + lnRMSSD[t-7] + load_day[t-1]
```

Debe reportar coeficiente de `load_day[t-1]`, error estandar, `p-value`, cambio de `R^2` o error fuera de muestra frente al mismo modelo sin carga, y estabilidad del signo en folds temporales. Este pre-test no decide por si solo todo el modelo: un resultado no significativo puede deberse a baja potencia. Pero si `load_day[t-1]` no aporta mejora reproducible o el signo es contrario al supuesto fisiologico, la carga queda marcada como exploratoria y el modelo HRV-only pasa a ser la alternativa preferente para Fase 1.

con filosofia de parametros restringidos:

- `phi = 0.92` como default fijo, con sensibilidad obligatoria `0.85-0.97`
- `beta = -0.0010` como default fijo, o calibrado una sola vez en los primeros 90 dias estables mediante OLS restringida y no positiva
- `sigma_obs_base = 0.12` como fallback, estimado preferentemente como `SD(lnRMSSD - rolling_7d(lnRMSSD))` durante `warm-up`
- `sigma_proc = 0.04` como default inicial, aproximadamente un tercio de `sigma_obs_base`
- `Q_base = sigma_proc^2` y `R_base = sigma_obs_base^2`

La inicializacion debe respetar la regla de `warm-up` de la seccion 10.6:

- 30 observaciones no suprimidas con `obs_var_multiplier <= 1.25`
- busqueda inicial dentro de los primeros 90 dias calendario con datos `CORE`
- si no hay 30 observaciones utilizables en ese tramo, `ssm_warmup_complete = 0` y se pospone la emision de estado maduro
- `P[0]` estimado con varianza residual frente a `rolling_median_30d(lnRMSSD)`; fallback robusto con MAD documentado si la mediana movil no es viable

No debe haber reestimacion on-line libre de parametros en esta fase. La razon no es solo conservadurismo operativo: con una unica observacion diaria, `N` efectivo limitado, autocorrelacion de carga y ruido biologico relevante en `lnRMSSD`, la estimacion libre de `beta` probablemente tendria un intervalo de confianza demasiado amplio para interpretarse como sensibilidad individual fiable.

Ademas, la Fase 1 deberia incluir un analisis de sensibilidad ligero sobre `phi` y `beta`, para verificar si pequenos cambios en esos parametros alteran de forma desproporcionada el estado o la validacion. Ese analisis debe reportar `beta` como parametro asumido o restringido, no como parametro personalmente identificado salvo que una validacion posterior demuestre estabilidad fuera de muestra.

La implementacion tambien debe incluir un diagnostico de drift lento de baseline:

- calcular `lnRMSSD_slow_baseline` con mediana movil causal de 60-90 dias cuando haya cobertura suficiente
- calcular `lnRMSSD_detrended = lnRMSSD - lnRMSSD_slow_baseline` como senal diagnostica, no como reemplazo obligatorio de la observacion principal
- reportar correlacion y varianza explicada entre `ssm_recovery_state` y `lnRMSSD_slow_baseline`
- repetir de forma exploratoria la validacion con `lnRMSSD_detrended` o con baseline lento sustraido, sin convertir esa variante en el modelo oficial salvo decision posterior documentada

Quedan fuera de la implementacion principal de esta tarea, salvo backlog explicito:

- `beta_t` variable como segundo estado
- ruido observacional Student-t
- estado adicional de tendencia lenta (`level_trend`) como componente del Kalman principal
- filtro de particulas o aproximaciones no gaussianas

#### Tarea 4 — Sidecar sombra

Emitir un sidecar diario canonico con al menos:

- `Fecha`
- `ssm_input_ready`
- `ssm_warmup_complete`
- `ssm_recovery_state`
- `ssm_state_lo`
- `ssm_state_hi`
- `ssm_state_var` o `ssm_state_sd`
- `ssm_obs_missing`
- `ssm_load_missing`
- `ssm_load_context_mode`
- `ssm_proc_var_multiplier`
- `ssm_input_quality` o `ssm_quality_mode`
- `ssm_obs_var_multiplier`
- `control_rolling_hrv_7d`
- `control_load_7d`

Este fichero debe escribirse aunque existan dias con observacion ausente, de forma que el historial quede auditable.

El sidecar no debe considerarse reproducible si no se conoce exactamente contra que versiones de `CORE` y `sessions_day` fue generado. Como el filtro depende del historico completo, del `warm-up` y de parametros congelados tras la inicializacion, un cambio retrospectivo en `CORE` o en `sessions_day` invalida potencialmente toda la trayectoria posterior. Por tanto, una regeneracion incremental solo es segura si los hashes de los inputs historicos coinciden con los registrados en metadatos.

#### Tarea 5 — Metadatos y trazabilidad

Anadir un artefacto de metadatos con:

- parametros usados
- si cada parametro procede de default, `warm-up` o calibracion restringida
- rango temporal procesado
- ruta, tamano y hash `sha256` de `ENDURANCE_HRV_master_CORE.csv`
- ruta, tamano y hash `sha256` de `ENDURANCE_HRV_sessions_day.csv`
- dias validos
- dias suprimidos por calidad
- dias con carga ausente
- distribucion de `ssm_load_context_mode`
- multiplicadores de varianza de proceso usados por contexto de carga
- multiplicador medio de varianza observacional en `warm-up`
- recuento y porcentaje de observaciones con `BETA_FROZEN`
- recuento y porcentaje de observaciones con cada flag de calidad usado para inflar `R_t`
- ventana candidata de `warm-up` (`warmup_candidate_window_days`)
- umbral de calidad de `warm-up` (`warmup_obs_var_multiplier_threshold`)
- numero de observaciones utilizables de `warm-up`
- estado de `warmup_complete` y razon de posposicion si aplica
- metodo usado para `P[0]` (`rolling_median_30d_residual`, `MAD_fallback` u otro documentado)
- configuracion del diagnostico de drift lento (`slow_baseline_window_days`, metodo usado y cobertura)
- resultado del pre-test de utilidad de carga (`load_day[t-1]`): coeficiente, signo, `p-value`, mejora fuera de muestra y decision `load_signal_status`
- resultado de la auditoria previa de outcomes:
  - `outcome_audit_status`
  - `primary_outcome_available`
  - `secondary_outcome_available`
  - `primary_outcome_name`
  - `primary_outcome_lag_rule`
  - `secondary_outcome_name`
  - `secondary_outcome_lag_rule`
  - `outcome_temporal_semantics_status`
  - `outcome_coverage_by_fold`
- bloque `go_no_go_criteria` pre-registrado antes del primer ajuste:
  - criterios obligatorios (`required_all`)
  - criterios alternativos de valor adicional (`required_at_least_one`)
  - condiciones de veto (`veto_conditions`)
- fecha de generacion
- version del modelo o del script

Regla de invalidacion: antes de una ejecucion incremental, el script debe recalcular los hashes de `CORE` y `sessions_day`. Si cualquiera difiere del valor registrado, debe marcar `metadata_input_hash_mismatch = true` y regenerar el sidecar completo desde el inicio del rango procesado. No debe intentar parchear solo los dias nuevos, porque un cambio retrospectivo en el `warm-up`, en `sigma_obs_base`, en `P[0]`, en `beta` restringido o en la carga historica puede cambiar todos los estados posteriores.

Esto evita que el sidecar quede desacoplado de sus condiciones de generacion.

#### Tarea 6 — Controles de ingenieria

Implementar y guardar junto al sidecar los comparadores minimos:

- `rolling lnRMSSD 7d`
- `load_7d` canonico desde `ENDURANCE_HRV_sessions_day.csv`
- `load_3d`, `load_14d` y `load_28d` como comparadores de sensibilidad de carga
- `gate_final` actual desde `ENDURANCE_HRV_master_FINAL.csv` como baseline operativo informativo
- baseline compuesto `gate_final + load_7d` o `gate_final + load_3d`, implementado como regla lineal/logistica simple y reservado como comparador operativo de promocion
- `polar_sleep_score` reciente desde `ENDURANCE_HRV_sleep.csv` como baseline contextual secundario

Opcionalmente, se puede anadir un tercer control estructurado:

- `local level model` con `lnRMSSD` sola

Este control estructurado pasa a tener doble funcion: baseline de parsimonia y prueba de admisibilidad de la carga (`local level + regresion auxiliar de residuos sobre carga`). Si iguala o supera al ARX-Kalman, debe frenarse la promocion del ARX por falta de valor incremental claro.

### 13.4 Tareas concretas de validacion

#### Tarea 7 — Definicion reproducible del outcome

Convertir la definicion metodologica de `sesion comparable` en una especificacion reproducible de evaluacion. Para no bloquear la implementacion, la primera version debe fijar una definicion operativa inicial aunque pueda revisarse despues.

La propuesta inicial recomendada debe usar columnas reales de `ENDURANCE_HRV_sessions_day.csv`, no etiquetas externas aun no canonicas. La primera version debe generar, como minimo, estas familias:

- `aerobic_long_z2`: `has_aerobic=1`, `intensity_cat_day=Z2`, `total_duration_min >= 75`
- `aerobic_short_z2`: `has_aerobic=1`, `intensity_cat_day=Z2`, `total_duration_min < 75`
- `aerobic_z3_tempo`: `has_aerobic=1`, `intensity_cat_day=Z3`, `30 <= total_duration_min <= 60`
- `aerobic_intervals`: `has_aerobic=1` y (`intensity_clustering_level=high` o `work_n_blocks_day >= 3`)
- `strength_only`: `has_strength=1`, `has_aerobic=0`

La regla inicial de comparabilidad entre una sesion objetivo y sus referencias historicas dentro de la misma familia es:

- mismo `has_aerobic`
- mismo `intensity_cat_day`
- ratio de `total_duration_min` entre `0.75` y `1.33`
- ratio de `load_day` entre `0.70` y `1.43`, salvo carga cero o ausente
- diferencia de `z3_min_day` dentro de una tolerancia definida por familia
- en fuerza pura, exigir `has_strength=1` y `has_aerobic=0`

El outcome principal de arranque debe expresarse como calidad funcional de la siguiente sesion comparable, usando un `FDS` (`functional_deviation_score`) calculado dentro de familia:

```text
metric_session[t] = metrica funcional elegida para esa familia
FDS[t] = (metric_session[t] - mediana_rolling_8_familia) / MAD_rolling_8_familia
```

El signo debe orientarse para que `FDS` alto signifique mejor tolerancia funcional. La metrica inicial permitida es:

- `work_total_min_day / max(load_day, 1)` como proxy pragmatico de trabajo por carga interna, solo dentro de familia comparable

Condicion temporal no negociable: el `FDS` de una sesion fechada en `s` solo puede validar predicciones generadas antes de esa sesion, por ejemplo `ssm_recovery_state[t]` con `t < s` y horizonte predefinido. Las metricas de `sessions_day.csv` son mediciones de la propia sesion, no variables posteriores por si mismas. La independencia aparece solo al alinearlas como outcome de una estimacion previa.

Metricas alternativas o complementarias, si tienen cobertura suficiente:

- `cardiac_drift_worst` con signo invertido
- `effort_above_anchor_aerobic` con signo invertido
- `effort_above_typical_aerobic` con signo invertido
- `rpe_max_day` con signo invertido si representa esfuerzo excesivo no planificado
- `pass/fail` funcional predefinido antes de observar HRV o SSM

Esta tarea si exige fijar al menos:

- una familia de sesiones elegibles
- una regla de comparabilidad
- un outcome principal funcional
- un outcome secundario subjetivo no circular

El resultado debe ser un esquema de etiquetado que permita evaluar el modelo fuera de muestra y un bloque de metadata con:

- familias usadas
- numero de sesiones por familia
- tolerancias aplicadas
- metrica funcional elegida por familia
- cobertura del outcome principal por bloque de validacion

#### Tarea 8 — Harness de walk-forward

Implementar un script o modulo de validacion con:

- `warm-up` inicial
- ventana de entrenamiento expansiva
- bloques futuros de evaluacion
- comparacion contra baselines
- registro separado de rendimiento global y rendimiento en dias discordantes

El objetivo aqui no es solo medir error medio, sino dejar un proceso que pueda rerunearse sobre nuevo historico sin ambiguedad manual.

El harness debe incluir tambien un control minimo de cobertura. Como regla operativa inicial:

- si la cobertura de pares validos `lnRMSSD[t] + load_day[t-1]` cae por debajo de `70%` en una ventana movil de 30 dias, el modelo debe marcar esa ventana como degradada o de baja fiabilidad
- si la frecuencia del outcome principal cae por debajo de un minimo operativo sostenido, la validacion funcional debe ampliarse por bloques o apoyarse mas en el outcome secundario
- el reporte debe comparar explicitamente ARX-Kalman frente a `local level + regresion de residuos`; no basta con comparar el ARX contra rolling HRV y carga reciente
- antes de interpretar mejoras de RMSE/MAE, el harness debe calcular el `MDE` del outcome principal con el N efectivo observado
- la definicion de dias discordantes para evaluacion debe quedar pre-registrada y, si es posible, incluir una senal externa al SSM como wellness o recuperacion subjetiva
- el rendimiento en discordantes debe compararse contra un combinador lineal OLS de los mismos baselines

#### Tarea 9 — Baselines oficiales

La validacion debe comparar la capa sombra, como minimo, contra:

- HRV suavizada
- carga reciente canonica (`load_3d`, `load_7d`, `load_14d`, `load_28d`)
- un baseline lineal simple HRV + carga
- `gate_final` actual como baseline informativo
- `gate_final + carga` como baseline operativo compuesto para cualquier argumento de promocion visible/advisory
- sueno reciente como baseline contextual secundario

Los comparadores de carga deben usar las columnas canonicas de `sessions_day` antes de construir agregados nuevos. En particular, `load_7d` sustituye a cualquier `EWMA(load_day)` paralela como baseline principal de carga. `acwr_simple_prev`, `monotony_7d_prev`, `strain_7d_prev`, `intensity_clustering_flag` e `intensity_blackhole_flag` deben aparecer al menos en el reporte como comparadores secundarios o estratos de auditoria.

El `gate_final` no debe presentarse como baseline neutro. Es la decision operativa vigente y permite evaluar compatibilidad con el sistema actual, pero ya deriva de `lnRMSSD`. Por tanto, una mejora frente a `gate-only` no demuestra por si sola valor incremental. Para promocion, el comparador operativo minimo debe ser `gate_final + carga canonica`; si ese baseline compuesto iguala al SSM, no hay argumento suficiente para visibilidad advisory.

Estos baselines deben definirse de forma que no repliquen el kernel exponencial implicito del filtro. En particular, el baseline lineal HRV+carga debe usar features estructuralmente distinguibles del SSM, como ventanas rectangulares, acumulados discretos o predictores instantaneos/rezagados simples. Si se usa una EWMA, su parametro debe fijarse de forma externa y no ajustarse para coincidir con la memoria efectiva del filtro.

Ademas, debe existir una prueba inversa de equivalencia: ajustar un baseline OLS sobre `EWMA(lnRMSSD)` y `EWMA(load_day)` para comprobar hasta que punto replica el `ssm_recovery_state`. Si el baseline explica casi toda la variacion del estado y sus coeficientes son compatibles con los pesos implicitos del Kalman, el reporte debe marcar el SSM como redundante salvo que la validacion externa demuestre una ventaja clara.

Si el modelo no supera de forma razonable a este conjunto, la conclusion correcta es detener la promocion, no aumentar complejidad.

#### Tarea 10 — Reporte de validacion

Generar un artefacto reproducible de evaluacion que resuma:

- rendimiento global fuera de muestra
- rendimiento en dias discordantes
- frecuencia del outcome principal
- resultado de la auditoria previa de outcomes y decision `validacion_formal_permitida`
- confirmacion de que el outcome principal es posterior a la prediccion y no una metrica contemporanea usada con fuga temporal
- sensibilidad a dias con mala calidad o `missingness`
- comparacion contra baselines
- cumplimiento del bloque `go_no_go_criteria` pre-registrado: `required_all`, `required_at_least_one` y ausencia de `veto_conditions`

El reporte debe incluir tambien:

- cobertura de pares validos por ventana
- frecuencia observada del outcome principal
- `MDE` estimado para el outcome principal y etiqueta `decisivo/no decisivo`
- sensibilidad basica a cambios de `phi`
- sensibilidad basica a cambios de `beta`
- advertencia explicita si la contribucion estimada de carga es indistinguible de cero o no mejora a los baselines
- diagnostico de drift lento: relacion entre `ssm_recovery_state`, `lnRMSSD_slow_baseline` y `lnRMSSD_detrended`
- advertencia explicita si el estado parece absorber deriva cronica de baseline mas que variacion aguda de recuperacion
- decision documentada sobre que arquitectura queda como candidata preferente tras la comparacion inicial
- prueba de equivalencia entre `ssm_recovery_state` y baseline OLS `EWMA(lnRMSSD) + EWMA(load_day)`
- uso efectivo de la incertidumbre: numero de dias en que `ssm_state_var` o el intervalo modifican la interpretacion, suprimen salida o degradan confianza
- calibracion predictiva de la incertidumbre:
  - cobertura empirica del intervalo predictivo 90% para `lnRMSSD[t]`
  - `PIT = Phi((lnRMSSD[t] - y_pred[t]) / sigma_pred[t])` calculado fuera de muestra
  - histograma o resumen de uniformidad del `PIT`
  - sesgo medio y dispersion de residuos estandarizados
  - decision `uncertainty_calibration_status`
- comparacion contra `gate_final` actual como baseline informativo
- comparacion contra baseline compuesto `gate_final + carga canonica` como liston operativo de promocion
- comparacion contra `load_7d` canonico y resto de columnas de carga ya existentes
- comparacion contextual contra sueno reciente, sin usar sueno como input de Fase 1
- analisis estratificado por `intensity_clustering_flag` e `intensity_blackhole_flag` cuando haya cobertura suficiente
- definicion exacta de discordancia diagnostica y discordancia de evaluacion
- N total y por bloque de dias discordantes evaluables
- comparacion del SSM contra combinador OLS en dias discordantes
- etiqueta `exploratorio/no decisivo` si el subconjunto discordante es demasiado pequeno

No hace falta que este primer reporte sea un dashboard bonito. Basta con que sea estable, legible y auditable.

### 13.5 Tareas de integracion y gobernanza

#### Tarea 11 — Integracion no intrusiva

Mantener la Fase 1 completamente fuera del pipeline canonico:

- sin escritura en `FINAL.csv`
- sin cambios en `build_hrv_final_dashboard.py` que alteren el contrato
- sin consumo por parte del `gate`

La primera integracion real debe ser solo documental y analitica: sidecar y reporte.

#### Tarea 12 — Criterio de promocion a visibilidad

Definir explicitamente que una eventual promocion futura solo podra ocurrir si el reporte cumple el bloque `go_no_go_criteria` pre-registrado en `ENDURANCE_HRV_ssm_shadow_metadata.json` antes del primer ajuste:

- `required_all`:
  - `RMSE` del outcome principal >= 8% mejor que el mejor baseline disponible, incluyendo `gate_final + carga` si se evalua promocion visible/advisory
  - acierto direccional absoluto del outcome principal >= 0.55
  - direccion positiva en >= 3 de 5 folds walk-forward, o proporcion equivalente si el numero real de folds cambia
- `required_at_least_one`:
  - ventaja en dias discordantes con mejora de `RMSE` >= 12% en ese subconjunto
  - o ventaja en outcome subjetivo con mejora de `MAE` >= 0.25 puntos
- `veto_conditions`:
  - fallo de viabilidad de outcome: no existe outcome posterior, externo, con lag documentado y cobertura suficiente para una validacion formal
  - fallo de degeneracion: el baseline OLS `EWMA(lnRMSSD) + EWMA(load_day)` reproduce el estado Kalman dentro de la tolerancia definida
  - fallo de calibracion: cobertura del intervalo predictivo 90% de `lnRMSSD` fuera de `[0.80, 0.95]` en folds de test o `PIT` claramente no uniforme
  - fallo de estabilidad: sensibilidad a `phi` en `[0.88, 0.96]` produce cambios de `RMSE` > 5%

La politica de degradacion y supresion tambien debe estar probada, pero no sustituye estos criterios. Sirve para decidir si la senal puede mostrarse con seguridad; no demuestra valor predictivo.

Sin estas condiciones, no deberia abrirse la siguiente capa de integracion visible.

### 13.6 Criterios de aceptacion de la Fase 1

La Fase 1 puede considerarse completada cuando existan todos estos elementos:

- el script genera el sidecar sin tocar `FINAL.csv`
- el sidecar incluye estado, incertidumbre, flags y controles
- el sidecar registra hashes `sha256` de `CORE` y `sessions_day`, y se regenera completo si esos hashes cambian
- el modelo degrada correctamente ante calidad baja o datos ausentes
- existe una auditoria previa de outcomes con `outcome_audit_status = pass`, o la Fase 1 queda marcada explicitamente como `no_validatable_current_data`
- si `outcome_audit_status != pass`, el sidecar puede aceptarse solo como prototipo tecnico, no como validacion predictiva completada
- existe un harness de validacion `walk-forward`
- el harness valida la calibracion de incertidumbre con cobertura predictiva 90% y `PIT`
- la comparacion contra baselines es reproducible
- el documento deja clara la diferencia entre Fase 1 sombra y cualquier promocion futura

### 13.7 Siguiente decision tras la implementacion

Una vez completada la Fase 1, la siguiente decision ya no es tecnica sino de evidencia:

- si el modelo no supera a baselines simples, se cierra la via de complejizacion
- si el modelo aporta senal global y especialmente en dias discordantes, se justifica evaluar una Fase 2

La Fase 2 no deberia abrirse por elegancia del modelo, sino por rendimiento observado bajo este plan.
