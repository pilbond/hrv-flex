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
  - alertas de `zones_source_dist` si aportan contexto de calidad.

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

### 10.0 Definicion de RR valido
Un RR es valido si cumple simultaneamente:

- tiene formato `duration,offline`,
- contiene un volumen de filas coherente con la duracion de la sesion,
- no esta truncado ni vacio,
- tras la limpieza aplicada, el `% valido final` permite la interpretacion que se pretende hacer,
- la fuente preferente es `Polar H10`; si procede de OHR sin serie RR real, marcar `RR_NO_DISPONIBLE`.

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
**Modo A - beat windows** (modo preferente y actual de `endurance_rr_session_v4.py`)
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
- si se usa este modo, debe declararse como modo alternativo y no confundirse con la salida v4 por beats.

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

- si `stream_sampling.assumed_1hz = false`, rebajar confianza sobre lecturas que dependan de conversion `muestras -> minutos`,
- no usar como apoyo fuerte de interpretacion fina:
  - minutos exactos por zona,
  - `work blocks` derivados del stream,
  - rolling agregados que dependan de esas conversiones,
- explicitar la limitacion en la salida.

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

### Inputs minimos sugeridos
Cardiometabolico:

- tiempo `>=VT1`,
- tiempo `>=VT2`,
- `hr_p95` o equivalente,
- bloques sostenidos,
- `alpha1` solo si RR valido y lectura interpretable.

Mecanico:

- `D+`,
- `D-`,
- densidad vertical o pendiente,
- tiempo bajando o pendiente de cinta,
- nota de fatiga muscular local si existe.

### Salida recomendada
Se puede usar una sintesis local simple:

- `cardio_score: 0..3`
- `mecanico_score: 0..3`
- `coste_dominante`:
  - `cardiometabolico` si `cardio_score >= mecanico_score + 2`
  - `mecanico` si `mecanico_score >= cardio_score + 2`
  - `mixto` en el resto
  - `no_clasificable` si faltan inputs minimos

Definicion minima de escala:

- `0` = sin senal util o irrelevante
- `1` = senal presente pero baja
- `2` = senal clara y material
- `3` = senal dominante dentro de esa dimension

Regla:

- no asignar un score si no puedes justificarlo con al menos dos observaciones trazables al dato,
- si una dimension no tiene datos minimos, usar `no_clasificable` en vez de puntuarla de forma intuitiva.

### Regla interpretativa
La etiqueta final es una sintesis analitica local.
No debe presentarse como salida canonica ni como dato medido.

## 15. Estructura de salida obligatoria
### Orden por defecto
1. **Estructura global**
2. **Intensidad cardiovascular**
3. **Terreno / estructura de carga**
4. **Continuidad / fragmentacion**
5. **Splits o bloques**
6. **RR de sesion** solo si RR valido
7. **Diagnostico**
8. **Implicacion operativa**
9. **Confianza**
10. **Advertencias clave**

Regla:

- en sesiones simples, pueden omitirse secciones sin hallazgo material.

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
