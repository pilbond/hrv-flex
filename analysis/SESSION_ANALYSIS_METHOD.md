<!-- contract_version: 1.3 -->
# SESSION_ANALYSIS_METHOD.md - Session analysis method

## 1. Alcance
Este documento define el metodo operativo reproducible para analizar sesiones del atleta del proyecto.

Aplica a:

- analisis de una sesion individual,
- comparacion entre objetivo y ejecucion,
- analisis de bloques dentro de una sesion,
- integracion de RR cuando exista RR valido.

No gobierna:

- tono y baseline del atleta, que viven en `ENDURANCE_AGENT_DOMAIN.md`,
- infraestructura, que vive en `../AGENTS.md`,
- logica HRV canonica del proyecto fuera del analisis de sesion.

## 2. Principios normativos
### MUST
- priorizar datos crudos medidos y trazables sobre inferencias,
- no bloquear el analisis por falta de una fuente si aun puede responderse con alcance reducido,
- omitir metricas no fiables en lugar de fabricarlas,
- declarar los parametros operativos usados cuando afecten al resultado.

### SHOULD
- producir artefactos reproducibles cuando se calculen metricas derivadas locales.

### MAY
- integrar contexto reciente de recuperacion y carga si existe y es fiable.

## 3. Jerarquia de evidencia
1. datos crudos medidos y trazables
2. outputs canonicos del pipeline
3. metricas derivadas reproducibles documentadas
4. inferencias analiticas
5. contexto verbal no verificado

Regla:

- una inferencia no debe contradecir un dato fiable sin explicitar el motivo.

## 4. Flujo obligatorio
1. validar disponibilidad y calidad del dato
2. identificar disciplina, tipo de sesion y complejidad analitica
3. reconstruir demanda externa
4. reconstruir respuesta interna
5. integrar RR/HRV si existe y es valido
6. integrar contexto de recuperacion y carga reciente cuando existan fuentes fiables
7. detectar coherencias o discrepancias
8. sintetizar conclusion e implicacion practica
9. declarar confianza y limitaciones

## 5. Validacion del dato
### MUST revisar
- timestamps consistentes,
- duracion plausible,
- consistencia entre elapsed y moving si ambos pueden derivarse,
- huecos grandes o series truncadas,
- consistencia entre distancia, ritmo o velocidad y altitud cuando aplique,
- FC disponible y razonable,
- RR disponible y con calidad suficiente si se pretende usar,
- ausencia de duplicados obvios,
- si existe `data/ENDURANCE_HRV_sessions_metadata.json` del pipeline de sesiones:
  - `stream_sampling.assumed_1hz`
  - alertas de `zones_source_dist` si aportan contexto de calidad,
- si existe `summary.json` del modulo local de analisis, revisar `duration_consistency`:
  - si `duration_consistency = OK`, registrar la diferencia en minutos como trazabilidad,
  - si `duration_consistency = WARN` o el campo indica inconsistencia, declararlo y priorizar la fuente mas fiable para anclar la duracion real.
- si existen `session_payload.json` y `summary.json` del slug, usarlos como capa compacta primaria antes de explorar otros artefactos del caso,
- tratar `technical_report.md`, `report.md`, prompts previos o handoffs solo como apoyo operacional, nunca como fuente primaria del analisis.

### MUST, si hay trail o carrera con serie suficiente
- revisar stop&go relevante,
- cuantificar pausas que puedan distorsionar ritmo o continuidad,
- decidir si la lectura debe apoyarse en elapsed, moving o ambos.

## 6. Clasificacion de la sesion
Clasificar operativamente:

- disciplina,
- estructura: continua, intervalos, tempo, larga, recuperacion, tecnica o mixta,
- objetivo probable solo si puede inferirse desde senales observables.

Si el objetivo no esta explicito, marcarlo como inferencia.

Si existe fila canonica en `sessions.csv`, usar para esa sesion como referencia primaria:

- `vt1_used`
- `vt2_used`
- `zones_source`

Si `zones_source = fallback`, declararlo y rebajar la fuerza de cualquier conclusion fina basada en zonas.
En este contexto, `fallback` significa que `sessions` uso umbrales genericos por deporte por falta de zonas configuradas en Intervals para esa disciplina.

### Complejidad analitica
- **Simple**: sesion continua, terreno llano o estable, sin RR, sin discrepancias obvias.
- **Media**: sesion con terreno moderado, o con RR disponible, o con alguna discrepancia menor.
- **Compleja**: trail con desnivel relevante, intervalos estructurados, RR con `DFA-alpha1`, discrepancias FC/RR, o comparacion objetivo/ejecucion.

### Reglas de salida segun complejidad
- si la complejidad es **simple**, comprimir la salida y omitir secciones sin hallazgo; la nota de calidad puede reducirse a `2-3` lineas,
- si la complejidad es **media**, incluir las secciones relevantes y omitir las que no aporten,
- si la complejidad es **compleja**, ejecutar el flujo completo y usar nota de calidad de `5-8` lineas.

## 7. Reconstruccion externa
### 7.1 Metricas obligatorias
#### Para trail, carrera y cinta cuando el dato lo permita
- `elapsed_time`
- `moving_time` si es interpretable
- `non_moving_time` si es interpretable
- `pause_count_ge_15s` si aporta valor
- `pause_time_ge_15s` si aporta valor
- `max_pause` si aporta valor
- distancia
- ritmo o velocidad
- `D+ / D-` estimado si existe altitud usable
- segmentacion por terreno o pendiente cuando tenga sentido
- splits por km o por bloques comparables

#### Para ciclismo cuando el dato lo permita
- `elapsed_time`
- `moving_time` si es interpretable
- `non_moving_time` si es interpretable
- `pause_count_ge_15s` si aporta valor
- `pause_time_ge_15s` si aporta valor
- `max_pause` si aporta valor
- distancia
- velocidad
- `D+ / D-` estimado si existe altitud usable
- segmentacion subida / bajada / rolling
- cadencia media pedaleando
- `coasting` si es interpretable
- splits utiles por 5 km o tramos equivalentes

### 7.2 Defaults recomendados con declaracion obligatoria
Estos parametros son **defaults recomendados**, no verdades universales.
Si se usan otros, deben declararse.

#### Moving / non-moving
- umbral recomendado: `0.5 m/s` si existe velocidad instantanea o derivada usable.

#### Pausas
- pausa relevante: tramo continuo de `>=15 s` sin desplazamiento efectivo por encima del umbral de moving.

#### Altitud y desnivel
- suavizado recomendado: mediana movil de `11 puntos` si la resolucion temporal es aproximadamente `1 Hz`,
- deadband recomendado para trail/carrera: `0.5 m`,
- si la altitud esta muy cuantizada, declarar que el `D+ / D-` es solo orden de magnitud.

#### Terreno / pendiente
- pendiente sobre altitud suavizada,
- ventana temporal recomendada: `10 s`,
- clasificacion recomendada:
  - `uphill` si grade `> +1%`
  - `downhill` si grade `< -1%`
  - `rolling` en el resto

### 7.3 Reglas de fuente
- en cinta, priorizar `FIT` sobre `TCX` para continuidad real si ambos discrepan,
- si el archivo indoor representa mal velocidad o distancia, reducir el peso interpretativo de `moving/pause` y priorizar bloques o protocolo declarado,
- no llamar continua a una sesion con stop&go apreciable sin explicitarlo.

### 7.4 Familias operativas
- `VirtualRun` / cinta: tratar como familia de carrera indoor; usar la parte cardiometabolica con normalidad, pero rebajar el peso de terreno, `moving/pause` y cualquier lectura espacial si el archivo cuantiza mal la velocidad o la distancia.
- `Hike`: tratar como familia de terreno con locomocion de marcha, no como carrera continua; mantener la lectura de desnivel y continuidad, pero rebajar la semantica de bloque corrible y tempo de carrera.
- `Elliptical`: tratar como cardio indoor de bajo impacto; no aplicar semantica de terreno, y usar `SWOLF` no aplica. Si faltan ritmo por bloques, cadence o serie interpretable, preferir `no_clasificable` en la dimension mecanica.

## 8. Reconstruccion interna
### MUST calcular
- FC media
- FC maxima
- P95 de FC
- tiempo en `Z1/Z2/Z3` segun disciplina
- bloques continuos de `Z2`:
  - tiempo total
  - numero de bloques
  - bloque maximo
  - mediana
- bloques `Z3` si aportan valor material

### Fuente primaria de zonas cuando exista `sessions.csv`
Anclar preferentemente la lectura de zonas y estructura a:

- `vt1_used`
- `vt2_used`
- `zones_source`
- `z1_pct / z2_pct / z3_pct`
- `work_n_blocks`
- `work_total_min`
- `work_longest_min`
- `work_avg_z3_pct`

### Metricas de continuidad
Para `Z2` y, si procede, `Z3`:

- `zone_block_count`
- `zone_longest_block`
- `zone_block_median`
- `zone_time_ge_1min`
- `zone_time_ge_2min`
- `zone_time_ge_5min`

### Regla interpretativa critica
- no presentar tiempo acumulado en `Z2` como `AeT util` si la continuidad es insuficiente,
- si la mayor parte del `Z2` proviene de bloques cortos, expresarlo explicitamente como discrepancia entre `tiempo en zona` y `continuidad del estimulo`.
- no convertir una heuristica externa o un proxy de terreno en intensidad fisiologica exacta si el dato medido no alcanza para sostenerlo.

### Evidencia negativa
Cuando la ausencia de senal sea relevante para la lectura, hacerla explicitamente visible:
- ausencia de cierre descontrolado (`late_intensity`)
- ausencia de deriva cardiovascular llamativa (`cardiac_drift_pct` bajo o moderado)
- ausencia de acumulacion significativa de tiempo en `Z3`

Regla: no omitir la evidencia negativa relevante simplemente porque no haya hallazgo; su ausencia confirma un patron de sesion controlada y debe decirse.

### Continuidad fisiologica util
Para continuidad `>=VT1`, reutilizar por defecto la definicion canonica de `work blocks` del proyecto en `ENDURANCE_HRV_Sessions_Schema.md`.

Regla operativa:

- dos tramos adyacentes `HR >= VT1` pueden fusionarse como un unico bloque solo si:
  - el gap entre ellos es `<= 60 s`,
  - la caida de FC durante el gap es `<= 10 lpm`.

Interpretacion:

- esta continuidad fusionada describe mejor el estimulo util real que el simple cruce estricto de umbral,
- no equivale a pureza estricta de `Z2`,
- no debe ocultar la diferencia entre exposicion bruta por zona y continuidad fisiologica.

### MUST reportar si la diferencia es material
Si la continuidad estricta por zonas y la continuidad fisiologica por `work blocks` cambian de forma material la lectura de la sesion, MUST hacer visibles ambas.

Ejemplos de cambio material:

- el numero de bloques cambia la etiqueta interpretativa,
- `time in zone` sugiere mucha fragmentacion pero `work blocks` sugiere pocos tramos sostenidos,
- la lectura de `AeT util` depende de usar una u otra definicion.

## 9. Durabilidad / desacople
### MAY calcularse como bandera
- `speed/HR`
- `Pa:Hr`
- metricas equivalentes

### MUST NOT
- usarlo como conclusion principal en terreno variable o sin potencia,
- tratarlo como diagnostico fuerte si stop&go, perfil o superficie contaminan la comparacion.

## 10. Capa RR
La capa RR solo se ejecuta si RR es valido.

Si no hay RR disponible:
- el analisis continua sin error; se genera `summary.json` parcial con `rr_unavailable: true`,
- el `technical_report.md` omite automaticamente secciones RR,
- se preservan: coste (cardio/mecanico), contexto (sesiones_day, sleep, final),
- se pierden: RMSSD, DFA-alpha1, HR@0.75, gating RR-dependiente.

Esto es un **analisis degradado pero operativo**.

### 10.0 Definicion de RR valido
Un RR es valido si cumple simultaneamente:

- tiene formato `duration,offline`,
- contiene un volumen de filas coherente con la duracion de la sesion,
- no esta truncado ni vacio,
- tras la limpieza aplicada, el `% valido final` permite la interpretacion que se pretende hacer,
- la fuente preferente es `Polar H10`; si procede de OHR sin serie RR real, marcar `RR_NO_DISPONIBLE`.

Si no hay RR en absoluto (fallo de grabacion, dispositivo sin sensor, Polar sin export):
- registrar motivo en `manifest["rr_error"]`,
- continuar analisis con cost model intacto,
- marcar payload con `rr_unavailable: true`.

### 10.1 Limpieza
#### Minimo obligatorio
1. excluir `offline=true`
2. excluir RR fuera de `300-2000 ms`

#### Limpieza estricta recomendada
3. excluir latidos con `dRR > 20%` respecto al previo valido

Reglas:

- la modalidad de limpieza usada debe declararse siempre,
- si se usa una utilidad local con otra estrategia reproducible, debe explicitarse y no compararse a ciegas con salidas generadas bajo otro esquema.

### 10.2 QA obligatoria
Reportar siempre:

- filas totales
- offline
- fuera de rango
- eliminados por filtro adicional si existe
- validos finales
- `% valido final`

### 10.3 RMSSD en ejercicio
Configuracion recomendada:

- ventanas no solapadas de `1 min`
- ventanas no solapadas de `5 min`

Reportar:

- `P10 / P50 / P90`
- tiempo por bandas en ventanas de `1 min` si aporta valor:
  - `<=7 ms`
  - `8-11 ms`
  - `>=12 ms`

### 10.4 DFA-alpha1
Solo usar configuraciones reproducibles y declaradas.

Utilidad local preferente del modulo:

- `analysis/endurance_rr_session_v4.py`

#### Modos aceptados del modulo
**Modo A - beat windows** (modo preferente y actual de la utilidad local por latidos)
- ventana: `300 latidos`
- paso: `60 latidos`
- `rr_layer_used = strict`
- requiere QA separada de capa core y strict
- puede emitir `dfa_gate`

**Modo B - time windows**
- ventana: `120 s` (ajustable via `--window-sec`)
- paso: `5 s` (ajustable via `--step-sec`)
- minimo de latidos por ventana: `200` (`--min-beats`)
- fraccion minima de latidos validos: `0.95` (`--min-valid-frac`)
- escalas por defecto: `4-16` (`--scale-min`, `--scale-max`)
- si se usa este modo, debe declararse como modo alternativo y no confundirse con la salida principal por latidos.

#### MUST reportar
- modo usado
- numero de ventanas validas
- mediana
- `Q25 / Q75` o `IQR`
- `% < 0.75`
- `dfa_gate` si la utilidad lo soporta
- si hay `time_axis_trust != OK`, limitar la lectura temporal y declararlo

Reglas:

- no comparar directamente el numero de ventanas entre modos distintos como si midieran lo mismo,
- si se usa `HR@0.75`, declarar tambien si el cruce es robusto o debil.
- si `hr_at_075.usable = false`, MUST NOT usar el cruce secundario para recalibrar umbrales, reclasificar zonas o `validar` VT1/VT2.

### 10.5 HR@alpha1~0.75
Estimar solo si el cruce es interpretable.

`HR@0.75` es usable solo si se cumplen simultaneamente:

- `dfa_gate = DFA_OK`,
- existe mapeo HR-alpha1 suficiente,
- `alpha1` disminuye con la FC de forma coherente,
- hay tiempo suficiente alrededor del cruce,
- la sesion no es claramente no estacionaria para ese uso.

Si no se cumple, escribir:

- `HR@0.75 no estimable con fiabilidad`
- y el motivo concreto.

## 11. Coherencias y discrepancias
Buscar y expresar en terminos cuantificados:

- demanda alta con respuesta interna contenida,
- demanda moderada con respuesta interna desproporcionada,
- estabilidad inicial y degradacion final,
- discrepancia entre objetivo esperado y ejecucion real,
- si FC y RR cuentan historias distintas.

Regla:

- una discrepancia entre capas no autoriza por si sola una conclusion fuerte; primero debe declararse que capa manda y por que.

## 12. Contexto de recuperacion y carga reciente
### SHOULD integrar cuando existan fuentes fiables
- `data/ENDURANCE_HRV_sleep.csv`
- `data/ENDURANCE_HRV_sessions_day.csv`
- `data/ENDURANCE_HRV_sessions_metadata.json` del pipeline de sesiones
- outputs `FINAL` y `DASHBOARD`
- proximidad de sesiones exigentes previas
- acumulacion de carga reciente

Buscar:

- fatiga residual plausible
- desacople entre exigencia de la sesion y estado previo
- continuidad o ruptura respecto al patron reciente

### Regla de confianza por metadata
Si existe `data/ENDURANCE_HRV_sessions_metadata.json` del pipeline de sesiones:

- si `stream_sampling.assumed_1hz = false`, es señal de que el stream no graba a ~1Hz (dispositivo no estándar o exportación en frecuencia distinta); rebajar confianza sobre lecturas que dependan de conversion `muestras -> minutos`,
- no usar como apoyo fuerte de interpretacion fina:
  - minutos exactos por zona,
  - `work blocks` derivados del stream,
  - rolling agregados que dependan de esas conversiones,
- explicitar la limitacion en la salida.
- nota: pausas o tiempo detenido durante la sesion NO causan este flag (el calculo usa elapsed_time, no moving_time).

### Regla critica HRV / recuperacion
- `gate_badge`, `residual_z`, `RMSSD_stable`, `sleep`, `feel` y `reason_text` son contexto potente, pero no equivalen a diagnostico por si solos,
- si `baseline60_degraded = True`, rebajar automaticamente la fuerza de cualquier conclusion fina sobre recuperacion, saturacion vagal o readiness,
- en ese caso, el lenguaje permitido debe ser prudente: `compatible con`, `sugiere`, `no confirma`,
- MUST NOT presentar `saturacion parasimpatica`, `supercompensacion` o estados equivalentes como hechos cerrados si solo se apoyan en HRV matinal y percepcion subjetiva.

### MAY omitir si
- no existen fuentes de recuperacion
- la sesion es de complejidad simple y no hay senales de fatiga

## 13. Sintesis practica
La sintesis final debe responder:

- que ocurrio realmente
- que significa fisiologicamente
- que implicacion tiene para la siguiente decision

## 14. Balance cardiometabolico vs mecanico
### Regla general
Antes de usar una etiqueta final, describir por separado:

- carga cardiometabolica,
- carga mecanica.

### Marco operativo
Este framework es una sintesis analitica local.

Reglas:

- no presentarlo como salida canonica ni como dato medido,
- primero registrar observaciones trazables al dato y despues derivar el score,
- no asignar un score si no puedes justificarlo con al menos dos observaciones trazables al dato,
- si una dimension no tiene base minima suficiente, usar `no_clasificable`,
- si ambas dimensiones son bajas, usar `bajo_estimulo`.

### Semantica comun
Campos recomendados:

- `cardio_score: 0..3`
- `mecanico_score: 0..3`
- `coste_dominante`
- `confidence_cardio`
- `confidence_mecanico`
- `cardio_evidence[]`
- `mecanico_evidence[]`

Semantica:

- `cardio_score` = carga interna
- `mecanico_score` = coste musculoesqueletico, locomotor, periferico o propulsivo segun el deporte

Escala base comun:

- `0` = sin senal util o irrelevante
- `1` = senal presente pero baja
- `2` = senal clara y material
- `3` = senal dominante dentro de esa dimension

### Inputs minimos sugeridos
Cardiometabolico:

- tiempo `>=VT1`,
- tiempo `>=VT2`,
- `hr_p95` o equivalente,
- bloques sostenidos,
- `alpha1` solo si RR valido y lectura interpretable.

Mecanico:

- metricas especificas del deporte,
- estructura del terreno o del bloque,
- continuidad del estimulo,
- un proxy razonable de exigencia periferica o propulsiva,
- nota de fatiga muscular local si existe.

### Cardio score 0..3
Usar al menos dos anclajes observables.

- `0`: `<10%` del tiempo `>=VT1`, `<2%` `>=VT2` y sin bloque `>=VT1` de `8 min`
- `1`: `10-24%` `>=VT1` o `2-4%` `>=VT2` o bloque `>=VT1` de `8-19 min`
- `2`: `>=25%` `>=VT1` o `>=5%` `>=VT2` o bloque `>=VT1` de `20-34 min` o bloque `>=VT2` de `6-11 min`
- `3`: `>=40%` `>=VT1` o `>=12%` `>=VT2` o bloque `>=VT1` `>=35 min` o bloque `>=VT2` `>=12 min`

Reglas:

- `hr_p95` puede reforzar el score cardiometabolico,
- `alpha1` solo puede reforzarlo si RR es interpretable,
- no usar `alpha1` para sustituir tiempo en zonas y continuidad.

### Trail
Semantica mecanica:

- `mecanico_terreno_score` = coste por subida, bajada, pendiente y excenrico
- `mecanico_locomocion_score` = coste por correr rapido en terreno corrible aunque el desnivel sea bajo

Inputs utiles:

- `D+`,
- `D-`,
- `D+/h`,
- `D-/h`,
- tiempo en subida,
- tiempo en bajada,
- pendiente,
- bloques corribles sostenidos,
- velocidad o ritmo en llano o rolling,
- cadencia si aporta contexto.

Anclajes iniciales para `mecanico_terreno_score`:

- `0`: `D+/h < 150` y `D-/h < 150`
- `1`: `150-399` m/h de `D+` o `D-`
- `2`: `400-799` m/h de `D+` o `D-`
- `3`: `>=800` m/h de `D+` o `D-`

`mecanico_locomocion_score`:

- `0`: llano o rolling facil, sin bloque corrible exigente
- `1`: llano o rolling corrido con intencion, pero sin bloque sostenido material
- `2`: bloque material en terreno corrible a ritmo vivo o de carrera
- `3`: gran volumen o bloque muy exigente en terreno corrible

Calculo recomendado:

- `mecanico_score = max(mecanico_terreno_score, mecanico_locomocion_score)`
- subir `+1` si ambos son `>= 2`
- cap en `3`

### Bike
Semantica mecanica:

- `mecanico_terreno_bike_score` = demanda periferica ligada al relieve
- `mecanico_pedaleo_bike_score` = demanda periferica inferida por pedaleo y contexto

Inputs utiles:

- pendiente o perfil inferido desde `FIT` o `TCX`,
- tiempo subiendo,
- continuidad de las subidas,
- velocidad,
- cadencia,
- duracion de bloques exigentes.

Reglas:

- no hablar de `torque` como si estuviera medido si no hay potencia,
- con `cadencia + velocidad + pendiente` se puede inferir demanda periferica razonable,
- `cadencia` baja aislada no basta para clasificar demanda mecanica alta.

`mecanico_terreno_bike_score`:

- `0`: sin subidas sostenidas ni relieve relevante
- `1`: subida presente pero modesta
- `2`: subida material por duracion o acumulacion
- `3`: subida claramente dominante o repetida durante gran parte de la sesion

`mecanico_pedaleo_bike_score`:

- `0`: sin patron de pedaleo exigente
- `1`: cadencia relativamente baja o bloque exigente corto
- `2`: cadencia baja en subida o bloque sostenido con velocidad y terreno coherentes
- `3`: larga duracion o repeticion de bloques de pedaleo exigente en subida o terreno resistente

Calculo recomendado:

- `mecanico_score = max(mecanico_terreno_bike_score, mecanico_pedaleo_bike_score)`
- subir `+1` si ambos son `>= 2`
- cap en `3`

### Swim
Semantica mecanica:

- en natacion, `mecanico_score` significa coste propulsivo y tecnico

Subcomponentes recomendados:

- `propulsivo_score` = coste por bloques exigentes, densidad y continuidad del trabajo util
- `tecnico_score` = coste por deterioro de eficiencia o deriva tecnica cuando el dato lo soporte

Inputs utiles:

- ritmo,
- estructura de la serie,
- densidad del trabajo,
- descansos,
- `SWOLF`,
- brazadas o frecuencia de brazada si existen.
- numero de repeticiones exigentes,
- bloque mas largo de trabajo continuo,
- consistencia o deriva entre largos.

Reglas:

- `SWOLF` sirve como apoyo de economia o deriva tecnica, no como criterio unico,
- no tratar `SWOLF` alto por si solo como mas coste mecanico; puede reflejar peor ritmo, tecnica o contexto de serie,
- si solo hay FC y duracion, muchas sesiones deben quedar `no_clasificable` en esta dimension,
- si no hay estructura de serie, ritmo por bloques o metrica tecnica interpretable, rebajar confianza de forma explicita.

`propulsivo_score`:

- `0`: tecnica, drills o nado suave, sin bloque exigente ni densidad material
- `1`: trabajo propulsivo ligero o moderado, con series presentes pero sin bloque material
- `2`: bloques exigentes claros o densidad de trabajo propulsivo material
- `3`: sesion claramente dominada por bloques exigentes, alta densidad o volumen propulsivo sostenido

Anclajes observables utiles para `propulsivo_score`:

- presencia de series exigentes repetidas,
- bloque continuo de ritmo sostenido,
- recuperaciones cortas para el nivel de exigencia,
- parte material de la sesion dedicada a trabajo util y no solo a tecnica.

`tecnico_score`:

- `0`: tecnica estable, sin deriva interpretable
- `1`: pequenas variaciones tecnicas o eficiencia discretamente peor al final
- `2`: deriva tecnica material entre bloques o dentro de una serie
- `3`: sesion claramente condicionada por deterioro tecnico o coste tecnico-propulsivo alto

Anclajes observables utiles para `tecnico_score`:

- empeoramiento de `SWOLF` a ritmo comparable,
- aumento de brazadas por largo a mismo ritmo,
- caida de ritmo con coste similar,
- variabilidad anomala entre repeticiones comparables.

Calculo recomendado:

- `mecanico_score = max(propulsivo_score, tecnico_score)`
- subir `+1` si ambos son `>= 2`
- cap en `3`

Reglas de clasificacion en swim:

- si solo hay FC y duracion, preferir `no_clasificable` antes que inventar un `mecanico_score`,
- si hay ritmo de serie pero no metrica tecnica, se puede clasificar `propulsivo_score` con confianza limitada,
- si hay `SWOLF` o brazada sin contexto de ritmo o serie, usarlo solo como nota de apoyo, no como base del score.

### Confianza
Usar:

- `alta` si la dimension usa metricas directas y coherentes
- `media` si usa proxies razonables
- `baja` si depende de pocos proxies o el dato es incompleto

Reglas:

- en `bike`, sin potencia la confianza mecanica rara vez pasa de `media`
- en `swim`, sin datos de serie o tecnica la confianza mecanica suele ser `baja` o `no_clasificable`

### Etiqueta final
Calculo recomendado:

- `cardiometabolico` si `cardio_score >= 2` y `cardio_score > mecanico_score`
- `mecanico` si `mecanico_score >= 2` y `mecanico_score > cardio_score`
- `mixto` si ambos son `>= 2` y empatan
- `bajo_estimulo` si ambos son `<= 1`
- `no_clasificable` si falta base minima en una dimension

### Regla de salida
Si se usa este framework, MUST exponer la base observacional del score.

Ejemplo:

- `cardio_score = 2` por `31% >=VT1` y bloque `>=VT1` de `24 min`
- `mecanico_score = 3` por `D+ = 980 m`, `D- = 1040 m` y `41 min` en subida o bajada
- `coste_dominante = mecanico`

### Exposicion de evidencia raw al presentar scores
Al presentar `cardio_score` y `mecanico_score` en el informe, MUST incluir los valores observacionales que los justifican:
- no presentar solo la etiqueta numerica; anadir al menos los 2-3 anclajes observables que la generaron,
- si el `summary.json` incluye `cardio_evidence[]` y `mecanico_evidence[]`, reutilizarlos directamente,
- esto conecta el score abstracto al dato trazable y permite al lector verificar la clasificacion.

## 15. Estructura de salida obligatoria
### Orden por defecto
1. **Fuentes**
2. **Calidad del dato**
3. **Datos**
4. **Estructura externa**
5. **Respuesta interna**
6. **Capa RR** solo si RR valido
7. **Contexto de recuperacion y carga**
8. **Encaje en el bloque**
9. **Conclusion**
10. **Interpretacion fisiologica**
11. **Implicacion practica**
12. **Confianza**
13. **Advertencias**

Regla:

- en sesiones simples, pueden omitirse secciones sin hallazgo material.

### Reglas de seccion Fuentes
La seccion Fuentes no es un inventario de archivos; es la declaracion de que dato manda para cada aspecto del analisis.
- jerarquizar por funcion analitica: continuidad temporal, FC, contexto integrado, comparativa de bloque,
- cuando la sesion usa 3 o mas fuentes, presentarlas en tabla con columnas `Rol analitico` y `Fuente`; la tabla permite ver de un vistazo que archivo sostiene cada lectura.
- `session_payload.json` y `summary.json` deben figurar como capa principal cuando existan,
- `technical_report.md`, `report.md` o informes previos no deben citarse como evidencia del caso.

### Reglas de seccion Datos
Los datos de la sesion deben facilitar la lectura posterior, no competir con ella.
- estructurar en apartados curados:
  - **Perfil de sesion**: 4-5 datos clave (disciplina, duracion, distancia, desnivel si aplica, FC media/max),
  - **Intensidad**: 3-4 bullets (distribucion por zonas, tiempo util, P95),
  - **Estructura util**: 2-4 bullets (work blocks, bloque maximo, Z3 dentro de bloque),
  - **Contexto subjetivo**: 1-2 bullets (RPE, feel, nota del atleta si existe),
- las cifras que luego se reinterpretan con mas valor en Estructura externa, Respuesta interna o Capa RR no deben repetirse aqui; basta con presentarlas una vez donde aporten mas senal.

### Reglas de seccion Capa RR
La Capa RR tiene varias metricas cuantitativas que se leen mejor en tabla que en prosa.
- presentar RMSSD de ejercicio en tabla: Ventana, P10, P50, P90, Ventanas usables,
- presentar DFA-alpha1 en tabla: Mediana, IQR, % < 0.75,
- tras las metricas, incluir un apartado **Sintesis de coste** que conecte `cardio_score`, `mecanico_score` y `coste_dominante` con los anclajes observacionales que los justifican,
- si existe una limitacion que recorte la lectura fina (HR@0.75 no usable, gradiente alpha1 incoherente, etc.), declararla en un apartado **Limitacion clave** antes de cerrar,
- cerrar la seccion con una **Jerarquia de evidencia** numerada en 3 niveles: que sostiene la lectura estructural principal, que aporta la capa RR, y que no permite hacer.
- si `hr_at_075.usable = false`, cualquier `crossing` de baja confianza debe presentarse solo como orientacion secundaria; nunca como base de validacion de umbral.

### Reglas de seccion Contexto de recuperacion y carga
El contexto previo condiciona la lectura de la sesion. Para que sea rapido de consultar:
- estructurar en apartados con negrita: **Sueno previo**, **HRV matinal**, **Carga reciente**,
- si hay tension entre un `gate_badge` favorable y un `reason_text` con cautela, no dejarla como nota al margen; resolverla en un apartado **Tension explicita** que diga que tipo de verde es y que permite o impide operativamente.

### Reglas de seccion Encaje en el bloque
La comparacion con sesiones recientes aporta contexto que el analisis aislado no tiene.
- incluir una tabla cuantificada con 3-4 sesiones relevantes del bloque o periodo reciente,
- columnas minimas: fecha, deporte, duracion, D+ si aplica, `work_total_min`, `load`,
- priorizar sesiones comparables (mismo deporte, bloque activo) sobre recencia ciega,
- usar `sessions.csv` como fuente primaria,
- tras la tabla, una lectura comparativa breve que situe la sesion actual dentro de la secuencia.

### Reglas de seccion Conclusion
La conclusion debe integrar la lectura cualitativa con sus anclajes numericos.
- incluir la sintesis de coste (`cardio_score`, `mecanico_score`, `coste_dominante`) junto a la clasificacion cualitativa,
- no dejar la conclusion solo como texto narrativo; el lector debe poder verificar que la etiqueta esta sostenida por datos concretos.

### Reglas de seccion Interpretacion fisiologica
La interpretacion fisiologica no es una repeticion de la conclusion; es la lectura de que ocurrio a nivel de sistemas.
- anclar al menos una observacion a un valor numerico medido (RMSSD, alpha1 o equivalente) para que la lectura no quede desconectada del dato,
- cuando la huella mecanica condicione mas la recuperacion que la fatiga central, decirlo; en trail esto es frecuente y cambia la decision siguiente.
- distinguir explicitamente cuando se usa un valor medido frente a una aproximacion, heuristica o proxy.
- MUST NOT convertir Naismith, `pace equivalente`, drift, `residual_z`, `hr_at_075_crossing` o molestias subjetivas en prueba central de una conclusion fuerte sin respaldo adicional.

### Reglas de seccion Implicacion practica
La implicacion practica solo es util si es concreta y condicional.
- incluir un arbol de decision para la sesion siguiente con 2-3 escenarios,
- anclar cada escenario a una variable observable (estado musculoesqueletico, carga reciente, gate_badge),
- evitar recomendaciones genericas; si la recomendacion sirve para cualquier sesion, no aporta valor.
- MUST NOT basar una decision importante en una unica heuristica debil o en una unica molestia subjetiva aislada.

### Reglas de seccion Confianza
La confianza global puede ocultar que las capas tienen calidades muy distintas.
- cuando las capas difieran, desglosarar en tabla con columnas: Capa, Nivel, Limitacion; esto hace visible que la clasificacion global puede ser robusta aunque la lectura fina no lo sea,
- la semantica completa de confianza por capas esta definida en `ENDURANCE_AGENT_DOMAIN.md` seccion 10.

### Formato visual
El formato no es decorativo; estructura la lectura.
- usar separadores `---` entre secciones principales para marcar transiciones,
- usar negrita para apartados dentro de secciones,
- preferir tablas sobre listas de bullets cuando el contenido sea cuantitativo y comparable (RMSSD, DFA, sesiones del bloque, confianza por capas).

### Regla explicita sobre proxies
- Naismith, `pace equivalente`, drift, `residual_z`, `hr_at_075_crossing` y molestias subjetivas son proxies o apoyos contextuales,
- pueden reencuadrar la lectura, pero MUST NOT convertirse en la prueba central de una conclusion fuerte sin respaldo adicional.

## 16. Nota resumen de calidad
Tras el analisis completo:

- en sesiones simples, usar nota de `2-3` lineas,
- en sesiones medias o complejas, usar nota de `5-8` lineas.

Estructura recomendada:

- etiqueta fisiologica
- hallazgo clave
- balance cardiometabolico vs mecanico si aporta valor
- RR/alpha1 interpretabilidad
- comparabilidad
- lectura correcta

## 17. Casos donde no concluir fuerte
Reducir confianza y recortar alcance cuando:

- falta la mayor parte del dato clave,
- la sesion esta truncada o corrupta,
- el RR es invalido y el analisis depende de RR,
- hay conflicto grave entre fuentes sin resolver,
- el contexto invalida la inferencia principal.

## 18. Regla final
Este documento define el metodo.
La interpretacion final, el tono y la semantica de confianza vienen de `ENDURANCE_AGENT_DOMAIN.md`.
