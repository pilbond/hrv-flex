# HG-07 / HG-08: reconstrucción RR en sombra y detector ECG en origen

> **Reorganización 2026-10-27.** Esta nota se llamaba «HG-05 Auditoría de detección de latidos y calidad de señal en ventana». Casi todo su contenido es alcance y evidencia de HG-06, HG-07 y HG-08, así que pasa a ser la nota de desarrollo de HG-07 y HG-08. Lo propio de HG-05 (descartes en ventana) se movió a la [nota de HG-05](<HG-05 Auditoria de deteccion de latidos y calidad de senal en ventana.md>) y la secuencia de §9 a [Secuencia de tareas HG](<HG Secuencia de tareas HRV.md>). Las líneas «Estado» y «Actualización de dependencia» que siguen describen la tarjeta HG-05 a 2026-10-21 y se conservan como antecedente.

Estado: tarea bloqueada por HG-04 en Kanvas (`gray`), revisada el 2026-10-21. Documento de alcance y hallazgos exploratorios; por sí mismo no cambia el pipeline, los canónicos ni la QA.

**Actualización de dependencia 2026-10-21:** HG-04 ya no prioriza adoptar inicios de 180/210 s ni la ventana `[180,360]`. Todas las apariciones de `[180,360]` más abajo describen el diseño o las comprobaciones históricas hechos con ese corte, **no la ventana futura aprobada**. La métrica `rejected_rr_pct_window` deberá definirse sobre la ventana que HG-04 valide finalmente. La auditoría exploratoria de calidad por tramos puede informar HG-04 antes de fijar esa ventana, sin cambiar todavía el contrato operativo.

Alcance: recuperar diagnóstico del convertidor, validar en sombra una posible reconstrucción de RR partidos y medir descartes dentro de la ventana fija de HG-04. La activación de una fusión en CORE y cualquier cambio de `Calidad` son decisiones posteriores, condicionadas a validación. HG-03 corrige el emparejamiento tras descartes y se coordina con la posible reconstrucción; HG-04 define la ventana necesaria para la métrica local.

Base empírica comunicada: revisión dirigida de 41 días con `Artifact_pct > 3%` (8 de origen Polar, 33 de origen `from_jsonl`) y clasificación **enteramente inferida de las duraciones RR**, no anotación de latidos sobre ECG. El reproceso de 497 grabaciones de HG-04 mide otros aspectos del pipeline; no valida la identidad de los picos de esta tarea. La muestra dirigida no estima la prevalencia de errores en todos los días.

**Corrección visible del 2026-10-19:** se recuperaron el [script reproductor](../../research/experiments/hg05_evidencia/pares_extra_2a1.py), la [tabla de 275 parejas](../../research/experiments/hg05_evidencia/pares_extra_2a1.csv), las [variantes de conteo](../../research/experiments/hg05_evidencia/variantes_conteo.csv) y copias del código original. El script reproduce 275 parejas y 550 intervalos RR implicados en los 33 días `from_jsonl`. La regla que generó esa cifra usa mediana móvil centrada de 21 RR, primer RR/mediana entre 0,42 y 0,62, suma/mediana entre 0,85 y 1,15 y emparejado codicioso sin solape; incluye `offline` en la mediana y no lo exige para seleccionar. La regla de partida de HG-07 (§4, antes «PR B») da **306** parejas sobre los mismos archivos, no 275. Mi conteo anterior de **330** usa otra mediana (vecinos válidos que excluyen el par) y permite solapes. Son tres recuentos de candidatos, no tres mediciones de picos ECG falsos.

Las nueve variantes documentadas producen **244–371** parejas. Este rango muestra sensibilidad a umbrales, mediana y solape; no es un intervalo de confianza ni una estimación de prevalencia. El dato 275 debe citarse siempre con su regla A y no como cantidad estable de latidos reparables.

Comprobación reproducible del 2026-10-18: solo hay ECG de 9 fechas únicas en `data/rr_downloads/`, contando ZIP y ficheros sueltos; **no** están localmente los de 2026-04-15 ni 2026-04-20. Ambos sí están en Dropbox, con ACC, dentro de ZIPs por fecha. Hay ZIP fechado para **216 de las 218 fechas `from_jsonl` de CORE**; faltan 2026-03-06 y 2026-03-07. Solo se comprobó el contenido de los dos ZIP principales. No hay sidecars locales `*_RR_events.csv`. Véase [auditoría de disponibilidad e inspección técnica](../../research/reports/hg05_scope_audit_2026-10-18.md).

---

## 1. Tres patrones distintos resumidos por una sola métrica

`Artifact_pct` agrega tres fenómenos sin relación entre sí. La auditoría los separa.

### 1.1 Candidatos a sobredetección de picos R en el pipeline propio

Firma dominante entre los intervalos anómalos seleccionados de la era `from_jsonl`: pares cortos cuya suma se acerca a la mediana local. **Es compatible** con un pico adicional, pero la suma por sí sola no confirma que un latido real se contara dos veces. Los 550 intervalos de la tabla forman 275 parejas candidatas bajo la regla A, no 550 latidos confirmados como partidos. Toda la clasificación de firmas de esta sección procede de RR, sin validación ECG.

Reparto por era, sobre latidos clasificados como anómalos:

| Firma | `from_jsonl` (33 días) | Polar (8 días) |
|---|---|---|
| **`extra(2→1)`** — candidato a latido partido | **27,5%** (550 intervalos) | 10,4% (96 intervalos) |
| `perdido(1→2)` — latido ausente | 13,0% (260) | **19,9%** (184) |
| `ectópico+pausa` | 6,3% (126) | 6,7% (62) |
| corto aislado / leve / muy corto | 44,9% (900) | 55,0% (509) |
| hueco grande | 8,3% (167) | 8,1% (75) |

La diferencia entre eras justifica una investigación estratificada por origen. Estos porcentajes están condicionados a días seleccionados por `Artifact_pct > 3%` y a una clasificación por RR; no prueban tasas de sobredetección o subdetección del detector, ni que la fisiología fuera igual entre eras. La similitud de la clase `ectópico+pausa` no constituye un control independiente.

Muestras crudas (`*` = marcado `offline`, `[]` = anómalo):

```
2026-04-15, mediana del día 1176 ms:
  1199  1069  1253  [669]* [515]* 1076* 1153        669 + 515 = 1184 ≈ 1176

2026-04-20, mediana del día 1268 ms:
  1076  1084  1115  [469]* [776]* 1207* 1230        469 + 776 = 1245 ≈ 1268
   966   974   948  [617]  [350]   997  1011        617 + 350 =  967
```

**Corrección visible (2026-10-18):** la pareja 617+350 ms atribuida al 20 de abril no aparece, con tolerancia ±2 ms, ni en su RR archivado ni al repetir el detector sobre el ECG del ZIP de Dropbox. Se conserva arriba como ejemplo de la nota original, **no** como fixture o evidencia validada hasta encontrar su procedencia. Las parejas 669+515 del 15 de abril y 469+776 del 20 sí aparecen en las series respectivas.

### 1.2 La métrica de descartes mezcla el arranque y la ventana medida

La mitad de los latidos anómalos caen **antes de `t_start_eff`**, es decir fuera de la ventana de medición: mediana 50,0% en la era `from_jsonl`, 60,7% en la era Polar. Y **15 de los 41 días auditados** tienen más del 70% de sus anomalías fuera de la ventana.

Días clasificados `OK` con `Artifact_pct` elevado y sin anomalías **según esta clasificación RR** dentro de la ventana usada:

| Fecha | `Artifact_pct` | `t_start_eff` | % anomalías FUERA de la ventana | Anomalías dentro |
|---|---|---|---|---|
| 2025-09-13 | 6,1% | 150 s | **100%** | 0 |
| 2025-08-28 | 3,6% | 180 s | **100%** | 0 |
| 2026-08-17 | 4,6% | 330 s | **100%** | 0 |
| 2026-06-29 | 3,1% | 360 s | **100%** | 0 |
| 2026-04-01 | 3,6% | 330 s | 92% | 1 |
| 2026-07-14 | 7,4% | 270 s | 90% | 2 |
| 2026-04-29 | 7,4% | 90 s | 75% | 5 |

Y el caso inverso: 2026-07-26 tiene solo 5,4% de artefactos pero el **89,5% dentro** de la ventana (17 latidos corruptos en la medición); 2026-04-15 tiene 31 dentro.

`Artifact_pct` se calcula sobre `N_total`, todo el registro (`build_hrv_core.py:305`), así que no distingue un arranque con descartes de una ventana con descartes. Los siete días citados **ya eran `OK`**; no demuestran una ganancia inmediata del gate. Tampoco son «falsos positivos» del `Artifact_pct` vigente, cuya definición contractual es precisamente global: muestran que ese porcentaje no debe interpretarse como porcentaje de descartes en la ventana. Además, una anomalía RR conservada por el filtro no aparecerá en ninguna métrica basada solo en descartes.

> **Actualización 2026-10-27:** las cifras de este apartado usan el inicio adaptativo vigente. Con la geometría candidata de HG-04 (inicio 90 s, corte 375 s), el 36,5% de los descartes de 507 días cae antes de 90 s, y elegir entre porcentaje global y de ventana cambia la clasificación por umbral (15%/20%) en 3 de 507 días. Véase el [informe del 2026-10-27](../../research/reports/hg05_ventana_vs_global_375_2026-10-27.md).

### 1.3 Grabaciones de HR y patrón RR atípicos

| Fecha | HR mediana | % latidos anómalos | Calidad | Origen |
|---|---|---|---|---|
| 2026-01-12 | **82,9** | 54,2% | INVALID | Polar |
| 2025-06-20 | **70,0** | 40,1% | INVALID | Polar |
| 2025-06-25 | **68,9** | 51,5% | INVALID | Polar |
| 2026-05-09 | 57,0 | 61,8% | INVALID | jsonl |
| 2026-04-07 | 54,6 | 30,3% | INVALID | jsonl |

HR habitual de la serie: 48–52 lpm. La HR y la clasificación de intervalos de estos cinco días son atípicas, y los cinco ya quedaron `INVALID`. Sin ECG, ACC/protocolo verificado y contexto clínico no se puede atribuir su causa a movimiento ni afirmar que no fueran mediciones en reposo. El criterio de seguridad es que ninguna reconstrucción los convierta automáticamente en `OK`; cualquier cambio de QA se auditará por fecha.

---

## 2. Mecanismo técnico plausible de 1.1

`egc_to_rr.py:490–511`, en `detect_rpeaks()`:

```python
min_dist = int(round(0.35 * fs))                    # distancia mínima: 350 ms ABSOLUTOS
peaks, _ = find_peaks(mwi, height=thr, distance=min_dist)
...
# Merge peaks too close (<450ms), keep strongest.
while j + 1 < len(peaks) and (ts_s[peaks[j + 1]] - ts_s[peaks[j]]) < 0.45:
```

Ya existe una regla de fusión de picos, pero sus dos umbrales son **absolutos**: 350 ms de distancia mínima y 450 ms de ventana de fusión. La división de las 275 parejas RR candidatas se sitúa en una mediana de 0,521 del intervalo compuesto (p5 0,412; p95 0,604). Eso explica por qué un pico adicional, si lo hubiera, podría sobrevivir al detector cuando el RR habitual es largo; no confirma la identidad de ese pico.

A HR 50 (RR ≈ 1200 ms), el 52% son ~625 ms, **por encima de los 450 ms de la ventana de fusión**, así que el pico falso sobrevive. A HR 100 (RR ≈ 600 ms) serían ~312 ms y lo atraparía el `min_dist` de 350 ms.

La geometría hace plausible una sensibilidad especial a frecuencias cardiacas bajas, habituales en estas mediciones (48–52 lpm). «Solo se manifiesta» y «calibrado para población general» no quedan demostrados por estos datos; habría que medir la tasa de detección frente a ECG anotado a distintas frecuencias.

La auditoría **no podía determinar desde los RR** qué ocurrió en el ECG. La inspección técnica posterior de los dos ECG de Dropbox muestra varios picos intermedios con una onda amplia y mucho menos aguda que los complejos vecinos: la nitidez mediana del pico intermedio es 0,448/0,454 veces la de sus vecinos, frente a 0,997 en controles de RR normales de cada día. Esto **apoya** sobredetección en esos ejemplos, sin constituir anotación experta de todos los picos ni demostrar una causa única. El 20 de abril reproduce exactamente sus 431 RR archivados. El 15 de abril el detector actual produce 479 RR frente a 466 históricos, pero los 467 tiempos de pico archivados coinciden y la duración total es idéntica: hay **13 picos adicionales** bajo el entorno actual. Se necesita resolver versión de código/bibliotecas o parámetros antes de un backfill. Véase la investigación enlazada arriba.

### Diagnóstico que hoy no se publica con el RR canónico

`egc_to_rr.py:528,533,539` construyen una columna `reason` con los valores `OK`, `RR_OUT_OF_RANGE` y `DELTA_RR_GT_20P`, y `:611–612` añade una tercera fuente de `offline`: el gate de movimiento por ACC. Pero el CSV final solo escribe `duration,offline` (`:18`, `:759`): **la columna `reason` se calcula y se tira**.

Conservarla en un diagnóstico prospectivo permitiría separar `RR_OUT_OF_RANGE`, `DELTA_RR_GT_20P` y `ACC_HIGH_MOTION` del convertidor. El CSV canónico de RR tiene un esquema exacto de dos columnas (`egc_to_rr.py:759,819`); `*_RR_events.csv` ya ofrece `reason` cuando se habilitan auxiliares (`:835–838`), pero no hay sidecars locales en el inventario. El motivo original de un `offline` histórico no se recupera retroactivamente añadiendo la columna ahora, y la era Polar no comparte necesariamente estas categorías del convertidor.

---

## 3. Viabilidad de la corrección

La suma de los pares candidatos dividida por la mediana local es **1,023** de mediana (p5 0,930; p95 1,117; n = 275). Es una señal de plausibilidad, no una validación de que el intervalo compuesto sea el verdadero. Incluso si las 275 parejas heurísticas fueran correctas, la regla propuesta de ±10% excluiría al menos parte de la cola superior (p95 = 1,117), por lo que el efecto de la tabla siguiente no es una predicción verificada de esa implementación.

Salida histórica del cálculo heurístico, **no** efecto medido de una fusión sobre CORE:

| Fecha | `Artifact_pct` de CORE | Proxy tras quitar etiquetas | Parejas candidatas A |
|---|---|---|---|
| 2026-04-27 | 14,7% | **3,2%** | 13 |
| 2026-07-12 | 17,6% | **4,2%** | 16 |
| 2026-04-19 | 26,0% | **7,7%** | 20 |
| 2026-06-15 | 20,0% | 9,0% | 12 |
| 2026-03-30 | 25,9% | 11,4% | 14 |
| 2026-06-10 | 18,2% | 8,5% | 7 |

Media contrafactual comunicada de los 33 días seleccionados: **24,6% → 12,5%**. Esta cifra procede de `originales/merge.py`: resta dos etiquetas `extra(2→1)` por pareja seleccionada de un recuento de etiquetas anómalas y conserva como denominador el número original de RR. **No recalcula `Artifact_pct` de CORE, RR fusionados, RMSSD, QA ni gate.** La reducción es parcialmente circular porque desaparecen del numerador las mismas etiquetas que la regla decide reclasificar. Tampoco corresponde a la regla B de ±10% de HG-07. Queda como ilustración histórica del cálculo original, no como predicción de mejora operativa; debe rehacerse en una copia aislada con una regla fijada antes de usarla para decidir.

La [comprobación del filtro inicial de CORE](../../research/experiments/hg05/scripts/reconcile_hg05_pair_survival.py), con huellas RR verificadas, encuentra **250/275 parejas con ambos RR rechazados**, **20 con uno aceptado** y **5 con ambos aceptados** por `offline`, rango y delta-RR, antes del recorte final y la selección de ventana. En la tabla RR original, 120 parejas tienen ambos `offline`, 143 solo uno y 12 ninguno. Esto apunta principalmente a una posible **recuperación de datos descartados**. Un RR aceptado en ese primer paso aún puede quedar fuera del tramo de RMSSD; el rastreo completo de HG-06 al final de este documento precisa ese riesgo directo. El estado de `offline` por sí solo no prueba que una fusión sea correcta.

Una fusión correcta podría recuperar RR útiles y cambiar RMSSD; una fusión incorrecta inventaría un intervalo y podría alterar la QA y el gate. Hay que medir ambas posibilidades antes del corte.

La suma y la posición de la división son dos filtros útiles para **generar candidatos conservadores**, pero su separación aparente de los casos clasificados como ectópicos procede de la misma heurística RR. No demuestra ausencia de falsas fusiones. La validación debe incluir contraejemplos con latidos prematuros, secuencias irregulares, movimiento y episodios donde el detector conserve RR anómalos.

---

## 4. Alcance de entrega revisado

### HG-06 — diagnóstico y referencia ECG, sin cambio canónico

1. Conservar prospectivamente el `reason` que `rr_events()` y `gate_rr_by_acc()` ya generan, preferiblemente mediante el sidecar `*_RR_events.csv` existente o un resumen pequeño con huella del RR y versión del convertidor. Mantener el RR canónico de dos columnas (`duration,offline`) y las 18 columnas de CORE. Los recuentos `off`, `oor` y `dRR` ya se escriben en `Notes` (`build_hrv_core.py:596–602`); añadir columnas a CORE solo si un consumidor concreto las necesita y tras actualizar contrato y migración.
2. Completar la anotación de los ECG/ACC de 2026-04-15 y 2026-04-20 y añadir casos positivos, negativos y ambiguos. El 20 de abril reproduce exactamente los RR archivados; resolver por qué el detector actual añade 13 picos el 15 de abril aunque todos los picos históricos y la duración total coincidan. Emparejar cada ECG con su RR mediante tiempos de pico, secuencia, marcas `offline`, huella y versión del entorno, no solo por fecha. Verificar contenido y correspondencia de los otros ZIP fechados antes de afirmar cobertura histórica completa.
3. Conservar una tabla de investigación por intervalo, con origen, fecha, índice original, tiempo, duraciones del par, mediana local, estado del filtro y anotación del ECG. El resultado de la inspección debe distinguir pico espurio, latido genuino, incierto y señal no interpretable; no imponer una categoría fisiológica desde RR solamente. Incluir contraejemplos con ectopia o ritmo irregular y días sin descartes. No publicar ECG ni RR personales completos.
4. Conservar la reproducción de los 275 pares de la regla A con su tabla, huellas y sensibilidad a variantes. Presentar aparte la regla B de HG-07 y la regla de muestreo ECG de HG-06; no mezclar sus recuentos. El `reason` nuevo no recupera las causas originales de los `offline` históricos ni crea categorías equivalentes para Polar.

**Cierre de HG-06:** cobertura y límites de ECG explícitos, tabla auditable de candidatos y contraejemplos, diagnóstico futuro disponible sin cambiar `Calidad`, baseline ni gate. Si no se obtiene una referencia útil, cerrar como diagnóstico y mantener HG-07 en sombra o sin activar.

### HG-07 — reconstrucción candidata en sombra; activación condicionada

1. Implementar una función pura que detecte **candidatos** entre dos RR contiguos en el archivo original. La suma dentro de ±10% de una mediana móvil local y la división entre 0,35 y 0,62 son parámetros de partida procedentes de la muestra exploratoria; fijarlos antes de la evaluación independiente y no ajustarlos sobre los casos de prueba. No fusionar a través de un RR ausente, inválido o de tiempo no fiable.
2. Calcular, sin publicar cambios canónicos, una serie candidata que conserve para cada intervalo el tramo de índices originales que representa. Una fusión de los RR originales `i` e `i+1` conserva el tiempo total y representa `[i,i+1]`; el emparejamiento de HG-03 solo podrá unir intervalos cuyos tramos originales sean contiguos. Registrar candidatos aceptados, rechazados e inciertos. Si la procedencia o el eje temporal no es fiable, no fusionar.
3. Validar con la referencia ECG de HG-06: precisión de la fusión, falsos positivos, candidatos perdidos y casos no adjudicables, separados por fuente. Buscar activamente falsas fusiones entre ectópicos, episodios irregulares, movimiento y los cinco días `INVALID` de la sección 1.3. La era Polar sin ECG no hereda por defecto la validación de `from_jsonl`.
4. Comparar en copia aislada la rama vigente, la candidata de fusión RR y la corrección en origen de HG-08, primero como efectos aislados y después con HG-03/HG-04: RR utilizables, RMSSD/lnRMSSD, Poincaré, `Calidad`, baseline, FINAL, gate y acción, incluyendo propagación cronológica. Conservar el `Artifact_pct` global calculado sobre los RR originales como referencia; publicar por separado cualquier porcentaje posterior a la reparación. La estimación 24,6% → 12,5% no es criterio de aceptación.
5. La fusión RR es una **alternativa** para fechas sin ECG verificable, no la solución universal por defecto. No extrapolar la validación de `from_jsonl` a Polar. Si algún origen supera los criterios de falsas fusiones y aporta valor adicional a HG-08, fijar antes del corte su QA y política histórica, actualizar `docs/contracts/`, probar ambas rutas de CORE y reconstruir en dataset aislado con backup, versión por fila y manifest. No ejecutar `--all` directamente sobre producción. Si no alcanza ese nivel, conservar solo el diagnóstico shadow.

**Cierre de HG-07:** decisión explícita de adoptar o no la fusión, con evidencia de falsos positivos y efecto histórico. Una suma cercana a la mediana no basta para declarar un pico R falso.

### HG-08 — validar una corrección del detector ECG en origen

El barrido de HG-06 enlazó por contenido el RR histórico con el ECG de 216/218 fechas `from_jsonl` de CORE; no se encontraron ZIP ECG fechados para el 6 y 7 de marzo de 2026. Se confirmó ECG y ACC dentro de los ZIP de los dos días principales, pero el ACC de la era completa no se auditó. Esta cobertura permite estudiar una posible corrección en origen de la era ECG; todavía no valida un detector alternativo ni autoriza rederivar RR.

1. Usar la referencia anotada de HG-06 para comparar `detect_rpeaks()` vigente con alternativas predefinidas. Evaluar picos espurios y perdidos, incluidos controles sin anomalías y señales de morfología ambigua. Una ventana de fusión relativa al RR es **hipótesis de implementación**, no umbral ya aprobado; comparar también evidencia de forma del ECG. Separar conjunto de diseño y evaluación.
2. Aprovechar el inventario ECG/RR por contenido de 216 fechas y comprobar el ACC antes de cualquier rederivación. El 15 de abril tiene 13 picos adicionales al reprocesar hoy el mismo eje temporal; registrar versiones de código y bibliotecas e investigar esa divergencia. Tratar 2026-03-06 y 2026-03-07 como fechas sin raw localizado.
3. Si una alternativa mejora la detección sin falsos cambios relevantes en controles, rederivar **solo desde el mismo ECG/ACC de origen** en una copia aislada, conservar el RR previo, registrar fuente/hash y versión, y comparar cronológicamente CORE, QA, baseline y gate. Documentar qué hacer con las dos fechas sin raw verificable, sin imputarlas ni cambiar su fuente. La era Polar permanece fuera de esta rederivación.

**Preferencia técnica condicional:** si el detector corregido se valida y la cobertura real lo permite, corregir la era ECG en origen antes que fusionar RR después. No se activa hasta disponer de referencia, replay, contrato y política histórica. HG-07 sigue siendo comparador y posible solución acotada donde haya evidencia propia.

### HG-05 — descartes dentro de la ventana fija de HG-04

> **Movido 2026-10-27** a la [nota de HG-05](<HG-05 Auditoria de deteccion de latidos y calidad de senal en ventana.md>), junto con la medición que propone cerrarla y el traspaso de lo pendiente a HG-09 y HG-10.

### Umbrales posteriores

La revisión de `ARTIFACT_OK_MAX` queda aplazada hasta decidir entre la corrección en origen de HG-08, la posible fusión acotada de HG-07 y la métrica descriptiva de HG-05. No se presupone bajar el umbral al 5% ni reemplazar un porcentaje global por uno de ventana sin simular sus efectos en QA, baseline y gate.

---

## 5. Casos de referencia para la validación

| Fecha | Papel | Comprobación |
|---|---|---|
| 2026-04-15 y 2026-04-20 | Candidatos principales `from_jsonl` | ECG y ACC hallados en ZIPs de Dropbox; 20 de abril emparejado exactamente, 15 de abril con los mismos 467 tiempos de pico históricos y 13 picos adicionales hoy |
| 2026-04-27 | Cambio estimado grande | Medir el resultado de la regla exacta, no usar 14,7% → 3,2% como resultado ya validado |
| 2026-07-26 | Anomalías RR concentradas en ventana según la revisión | Comprobar cuántas fueron realmente descartadas; la nueva métrica no detecta anomalías aceptadas |
| 2025-09-13 | Origen Polar, `off=0` | Contrastar el porcentaje global y el de ventana sin atribuir causa desde RR |
| 2025-06-20 y 2026-01-12 | Casos `INVALID` de origen Polar | Confirmar que una posible fusión no los rehabilita por error |
| Días sin descartes y casos ECG ambiguos | Controles y contraejemplos | Paridad de métricas y recuento de falsas fusiones |

Los cinco días de §1.3 se revisarán por separado en el replay, sin asumir que su HR elevada prueba movimiento o que su `INVALID` sea inmutable por definición.

---

## 6. Criterios de aceptación comunes

- La referencia y el código de auditoría permiten distinguir observación RR, anotación ECG, inferencia y decisión.
- HG-06 anota todos los candidatos del 15 y 20 de abril que pueda emparejar con la serie archivada, más controles y casos ambiguos; un conjunto adicional no utilizado para escoger parámetros sirve para evaluar HG-07/HG-08. Se publican cobertura de anotación, falsos positivos/negativos y sus intervalos de incertidumbre por origen. Si el conjunto no permite acotar falsas correcciones, ninguna rama se activa automáticamente.
- Ningún intervalo fusionado entra en CORE sin validación suficiente, recuento explícito, procedencia original, versión de cálculo, comparación histórica y contrato actualizado.
- Ningún RR se rederiva desde ECG/ACC sin demostrar correspondencia con el RR histórico, medir cambios frente a la referencia anotada y resolver explícitamente las fechas sin raw verificable; no se sustituye la fuente Polar.
- El RR de entrada conserva compatibilidad con `duration,offline`. El diagnóstico adicional no reinterpreta retrospectivamente los `offline` de Polar ni del convertidor previo.
- Los recuentos globales originales y los de ventana tienen denominadores, exclusiones y límites temporales explícitos; el porcentaje en ventana no se presenta como calidad eléctrica verificada.
- Las pruebas cubren pares contiguos, huecos, secuencias de tres intervalos cortos, duraciones inválidas, bordes de ventana, rescate CORE, días limpios y los `INVALID` de referencia.
- La métrica de ventana es descriptiva al publicarse. Una revisión de los umbrales de QA y gate constituye una decisión posterior con simulación histórica y actualización contractual.

---

## 7. Estado de las conclusiones

| Afirmación | Estado tras revisión |
|---|---|
| `detect_rpeaks()` usa límites fijos de 350/450 ms | Verificado en código |
| `Artifact_pct` usa el registro completo | Verificado en código y contrato |
| Existen 275 parejas RR bajo la regla A original | Reproducido con script, tabla de índices y huellas; sigue siendo clasificación RR sin adjudicación ECG |
| Las 275 parejas son picos falsos fusionables con seguridad | No demostrado |
| La regla B de HG-07 produce las 275 parejas publicadas | No: produce 306 con mediana móvil y emparejado sin solape sobre los mismos RR |
| La regla exacta reducirá la media 24,6% → 12,5% | No demostrado; el cálculo original resta sus propias etiquetas anómalas sin volver a ejecutar CORE |
| Los cinco días de HR atípica se debieron a movimiento/no reposo | Causa no adjudicada; la QA vigente es `INVALID` |
| El porcentaje de descartes en ventana mejorará las decisiones del gate | Hipótesis pendiente de comparación; los siete ejemplos citados ya eran `OK` |
| Hay ECG de los días de referencia 2026-04-15/20 | No local; sí en sendos ZIPs de Dropbox, comprobados en lectura |
| Los ejemplos ECG revisados contienen picos intermedios de forma distinta de los vecinos | Apoyado por figuras y nitidez relativa en los dos días; inspección técnica, no anotación exhaustiva ni especificidad estimada |
| El detector actual reproduce el RR archivado del 20 de abril | Sí: 431 RR, diferencia máxima 0,0 ms |
| El detector actual reproduce el RR archivado del 15 de abril | No: 479 frente a 466 RR; sí reproduce los 467 tiempos de pico históricos y añade 13; resolver la divergencia del entorno antes de rederivar |
| El ejemplo 617+350 ms pertenece al RR archivado del 20 de abril | No se reprodujo dentro de ±2 ms; retirar como fixture hasta localizar su fuente |
| Hay raw ECG/ACC verificable para toda la era `from_jsonl` | RR histórico y contenido ECG enlazados en 216/218 fechas; faltan ZIP ECG fechados del 6 y 7 de marzo de 2026. El ACC no se auditó en el barrido general |

No se asignan porcentajes subjetivos de confianza a estas afirmaciones. Los resultados de la revisión de 41 días no cubren `data/SeatRR` ni autorizan extender una regla a ese protocolo.

---

## 8. Relación con HG-03, HG-04 y HG-08

HG-03 preserva la adyacencia de los intervalos originales tras descartar. Si HG-07 valida una fusión, su representación por tramo de índices debe integrarse con esa regla antes de cualquier corte canónico. HG-04 debe **definir y validar** la ventana antes de canonizar la métrica de HG-05; ya no se presupone `[180,360]`.

La fusión sigue siendo incierta; **HG-04 no queda bloqueada por HG-07 ni HG-08**. HG-08 compara una corrección del detector en origen para la era ECG con la reconstrucción RR de HG-07. Si alguna rama alcanza validación antes del corte histórico de HG-03/HG-04, puede prepararse un replay conjunto. Si no, HG-03/HG-04 deben poder avanzar y la rama validada requerirá después su propia comparación y, solo si se adopta, otro recálculo controlado. Evitar un segundo recálculo no justifica retrasar indefinidamente una corrección mejor fundamentada.

---

## 9. Avances de HG-06 relevantes para HG-07 y HG-08

> **Movido 2026-10-27.** La secuencia de tareas que ocupaba esta sección (orden de 2026-10-27 y secuencia histórica de 2026-10-21) está ahora en [Secuencia de tareas HG](<HG Secuencia de tareas HRV.md>). Aquí se conservan los avances de HG-06.

### Avance de HG-06 (2026-10-18)

Se ha implementado diagnóstico prospectivo por RR sin alterar el CSV canónico ni CORE, y se ha generado una primera referencia ECG/ACC reproducible de cinco fechas con tabla acotada de candidatos y controles. La selección de 41 días se reproduce (33 `from_jsonl`, 8 Polar). **Actualización 2026-10-19:** el código y la tabla originales aparecieron y reproducen 275 con la regla A; la regla B del documento da 306, y la regla de muestreo ECG usada en HG-06 da 330 por otra mediana y solape. El 15 de abril mantiene 13 picos adicionales al reprocesar; no se conoce aún su causa. La inspección ECG es técnica, no experta ni exhaustiva, por lo que no habilita todavía HG-07/HG-08. Estado y pendientes: [HG-06](HG-06%20Diagnostico%20y%20referencia%20ECG.md).

La primera comparación automática en sombra de HG-06 usó un detector de amplitud filtrada y 100 controles aleatorios. Ese detector produjo 538 picos exclusivos en cinco fechas y coincidió con 49/50 casos que la revisión técnica había considerado compatibles con sobredetección. Su acuerdo con el convertidor **no** valida la identidad de esos picos; la pantalla de forma ECG sigue siendo exploratoria y presenta al menos un control aleatorio de baja amplitud sin adjudicar. Los datos canónicos permanecen intactos.

**Reencuadre de muestra del 2026-10-19:** el 15 de abril es un caso particular de divergencia al reprocesar, no el centro de la pregunta general. HG-06 añadió 20 fechas nuevas, elegidas de forma reproducible entre cuatro niveles de `Artifact_pct` y varios meses, excluyendo las cinco fechas piloto. En las 20, el detector actual reproduce todos los tiempos de pico del RR archivado a ≤5 ms; esto muestra estabilidad de reproducción en esa muestra, no exactitud fisiológica. Hay 84 parejas RR candidatas bajo la regla A, pero su pantalla morfológica no es uniforme: 43/67 casos muestreados tienen razón de amplitud <0,6 y 18/67 >0,8. Dos días de `Artifact_pct` muy alto tienen candidatos con amplitud similar a controles. Por tanto, aún no se sostiene una explicación única de todos los descartes ni una tasa general de picos falsos. Véase [HG-06](HG-06%20Diagnostico%20y%20referencia%20ECG.md).

**Barrido completo del 2026-10-19:** se vinculó el RR histórico con el ECG de 216 de los 218 días `from_jsonl` de CORE; faltan ZIP fechados del 6 y 7 de marzo. En 93.038 RR archivados, la regla A encuentra 301 parejas candidatas en 55 días. Las 275 parejas originales de los 33 días con `Artifact_pct > 3%` coinciden exactamente por fecha, índice y SHA-256 de RR; hay 26 candidatas adicionales en días ≤3%. La medida exploratoria de amplitud ECG es baja (<0,6 frente a picos vecinos) en 226/301 candidatas, pero 53/301 tienen amplitud alta (>0,8) y 18/2160 controles aleatorios no candidatos también tienen amplitud baja. Solo el 15 de abril produce 13 picos adicionales con el convertidor actual; los picos archivados de los 216 días se reproducen dentro de 5 ms. **Conclusión limitada:** hay un patrón RR recurrente y una señal morfológica que merece revisión; todavía no existe un recuento validado de picos falsos, una explicación única de `Artifact_pct` ni base para corregir automáticamente el RR. Detalle y reproducción: [HG-06](HG-06%20Diagnostico%20y%20referencia%20ECG.md).

**Prueba de contraejemplos del 2026-10-19:** HG-06 generó 71 extractos ECG acotados en 19 fechas, seleccionados para poner a prueba tanto las candidatas de amplitud alta como los controles no candidatos de amplitud baja. La inspección técnica no experta encontró candidatas de amplitud alta con deflexión central estrecha y otras con oscilación amplia o deriva; la amplitud aislada no adjudica identidad. Los 18 controles bajos quedaron fuera de la regla A por sus puertas RR, aunque algunos muestran una deflexión central muy pequeña. Cuatro no tenían marcas `offline` en el par; dos pares pasan íntegros el filtro inicial de CORE, pero sus tiempos finales de 428–514 s quedan fuera de la **antigua propuesta** `[180,360]` de HG-04. Esa ubicación no permite deducir su relevancia bajo la ventana que se adopte en el futuro. No se ha demostrado un cambio de RMSSD ni del gate. El patrón general no se puede resumir como «275 falsos» ni como «solo el 15 de abril». Véase el [diagnóstico HG-06](HG-06%20Diagnostico%20y%20referencia%20ECG.md).

El ACC emparejado de esas 19 fechas estaba disponible. La pantalla de movimiento del convertidor marcó 5/17 candidatas de amplitud alta y 3/16 candidatas débiles con cobertura, pero **0/18 controles débiles**. Una extensión a los **55 días con candidatas A** encontró ACC legible en todos: movimiento alto en **38/300 candidatas con cobertura** frente a **20/550 controles aleatorios no candidatos** del mismo conjunto de días. En los días con `Artifact_pct >10%`, 191/208 candidatas con cobertura no tienen esa marca. El flag ACC no valida el pico ECG ni reconstruye los motivos históricos de `offline`; el movimiento detectado por esta pantalla explica solo parte del patrón.

**Revisión visual parcialmente ciega y destino en CORE (2026-10-19):** HG-06 seleccionó sin mirar amplitud ECG 20 candidatas y 20 controles del mismo día, cinco días por banda de artefacto; se ocultaron fecha, RR, grupo y ACC antes de anotar la forma. La revisión técnica marcó 16/20 candidatas sin deflexión estrecha central clara (4 inciertas) y 17/20 controles con deflexión estrecha (3 inciertos). Por azar, 19/20 candidatas de esta muestra tenían amplitud baja, así que no se extrapola a las 301, y el revisor no es clínico ni independiente. El rastreo de **las 301 candidatas** por el filtro real de CORE halló que **291** no aportan ninguno de sus RR al tramo vigente de RMSSD; solo 10 aportan uno o ambos, repartidos en cinco días ya `INVALID`. Entre las 226 candidatas de amplitud baja, 225 no aportan RR. Esta evidencia acota la hipótesis de corrupción directa de las métricas vigentes por **esta regla A**; su posible interés principal sigue siendo recuperar datos descartados. No mide cuánto cambiarían RMSSD, `Calidad` o gate tras una reparación ni excluye otros errores de detección. Detalle, scripts y límites: [HG-06](HG-06%20Diagnostico%20y%20referencia%20ECG.md).

**Matiz de cálculo:** aunque una candidata no aporte RR directamente, CORE puede calcular una diferencia de RMSSD entre dos RR conservados separados por intervalos descartados. En los 41 días `OK` con alguna candidata A, **66 de 10.814 diferencias** cruzan al menos un RR descartado de esas parejas, repartidas en 20 días; el mayor peso por día es **5,3% de la suma de diferencias al cuadrado**. El hueco puede incluir otros descartes, y ese porcentaje no es el cambio de RMSSD que produciría reparar un pico. Se detalla en [HG-06](HG-06%20Diagnostico%20y%20referencia%20ECG.md) y se coordina con HG-03.
