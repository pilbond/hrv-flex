## Objetivo
Llevar la capa semanal de distribucion observada de DO-01 a una senal operativa diaria dentro de `sessions_day.csv`, sin tocar el gate HRV, para detectar semanas con reparto suboptimo de intensidad y hacer visible el "black hole" de Z2 en el flujo diario.

## Tesis central
La tarea DO-02 no consiste en rehacer DO-01 ni en duplicar el sidecar semanal dentro de `sessions_day.csv`.

La tarea consiste en derivar desde la capa canonica `sport x week` una senal diaria minima, estable y causal, calculada siempre sobre los `7 dias previos` (`D-7` a `D-1`), que pueda convivir con el resto del contexto de carga en `sessions_day.csv` y, potencialmente, alimentar `reason_text` como contexto futuro.

Dicho simple:

- DO-01 responde `como estuvo distribuida la intensidad por deporte en la semana`,
- DO-02 responderia `hoy arrastro una distribucion semanal sana, ambigua o sesgada hacia demasiado Z2`.

## Estado actual del repo
Hoy el repo ya tiene la v1 de distribucion observada:

- `sessions.csv` persiste `z1_total_min`, `z2_total_min`, `z3_total_min`,
- `build_sessions.py` genera `ENDURANCE_HRV_intensity_distribution_weekly.csv`,
- el sidecar semanal ya expone `distribution_pattern`, `distribution_confidence` y `distribution_notes`,
- `analysis/WEEKLY_ANALYSIS_METHOD.md` ya puede priorizar esa salida semanal como fuente canonica.

Lo que no existe todavia es:

- ningun `polarisation_index_prev_7d` en `sessions_day.csv`,
- ningun `intensity_blackhole_flag` diario,
- ninguna proyeccion shifted de la semana previa a la fila diaria,
- ningun consumo de esta capa en `build_hrv_final_dashboard.py`.

## Por que es relevante
La propuesta original de DO-01 apuntaba a algo mas que una tabla semanal bonita.

El problema operativo real no es solo detectar exceso de Z3. Para eso ya existe `z3_7d_sum`.

El problema que sigue sin cubrir es:

- semanas donde casi todo el volumen cae en Z2,
- sin mucha Z3,
- y sin una base suficientemente amplia de Z1.

Ese patron puede dejar:

- `load_3d` razonable,
- `ACWR` y `strain` sin saltos extremos,
- `z3_7d_sum` moderado,
- y aun asi una distribucion de intensidad suboptima.

Por eso DO-02 importa:

- introduce una lectura de calidad estructural de la semana,
- complementa la carga cuantitativa con distribucion cualitativa,
- y permite detectar un sesgo de entrenamiento que el gate HRV no ve.

## Diferencia con lo que ya existe
Hoy el repo ya tiene:

- `z3_7d_sum` para exposicion alta a intensidad,
- `work_7d_sum` para trabajo sostenido total,
- `ACWR/monotony/strain` para carga reciente,
- `intensity_clustering_flag` para concentracion corta de dias intensos.

DO-02 cubriria otra pregunta:

- no `cuanta carga hubo`,
- no `cuantos dias intensos se acumularon`,
- sino `como se repartio estructuralmente la intensidad de la semana previa`.

## Relacion con DO-01
DO-02 depende de DO-01.

Sin DO-01:

- no existe una base semanal canonica por deporte,
- no hay reglas estables de patron y confianza,
- y cualquier senal diaria seria una heuristica acoplada y dificil de justificar.

Con DO-01 ya implementado, DO-02 puede apoyarse en:

- `ENDURANCE_HRV_intensity_distribution_weekly.csv`,
- `distribution_pattern`,
- `distribution_confidence`,
- y, si se decide, un indice numerico adicional de polarizacion.

Importante para la implementacion:

- el sidecar de DO-01 sigue siendo canonico para lectura semanal y validacion metodologica,
- pero no debe reutilizarse como fuente directa del calculo diario si DO-02 quiere una ventana rolling real `D-7..D-1`.

## Riesgo metodologico principal
El mayor riesgo de DO-02 es semantico.

`sessions_day.csv` tiene granularidad diaria. DO-01 tiene granularidad `sport x week`.

Por tanto, DO-02 no debe:

- copiar filas semanales enteras dentro de cada dia,
- mezclar deportes sin una regla clara,
- ni fingir una precision diaria que el dato no tiene.

La capa diaria debe ser:

- minima,
- rolling sobre la ventana previa `D-7..D-1`,
- y explicitamente contextual.

## Pregunta de diseno clave
Que debe entrar en `sessions_day.csv`:

- un indice numerico,
- un flag,
- una etiqueta de patron,
- o una combinacion minima de ellos.

Recomendacion:

- priorizar una senal numerica y un flag antes que una etiqueta categorica,
- dejar la etiqueta semanal completa en el sidecar `weekly`,
- y usar en `sessions_day.csv` solo lo necesario para consumo operativo.

## Desarrollo propuesto

### 1. Resolver dominancia por familia antes que por sport literal
La tarea no debe colapsar todos los deportes en una unica media semanal si eso destruye semantica, pero tampoco debe tratar como mezcla ambigua semanas que en realidad pertenecen a una misma familia deportiva.

Decision recomendada para v2:

- evaluar primero la dominancia por `familia deportiva`,
- usar el `sport` literal solo cuando no exista una familia clara o cuando la familia sea monodeporte.

Ejemplo operativo:

- `road_run + trail_run -> run_family`
- `bike -> bike_family`

Paso previo obligatorio:

- definir y codificar explicitamente el mapeo `sport -> sport_family` dentro del pipeline,
- no asumir que la familia existe ya en `build_sessions.py`.

Tabla v1 recomendada para los deportes que hoy entran en la capa de distribucion:

- `road_run -> run_family`
- `trail_run -> run_family`
- `bike -> bike_family`
- `elliptical -> elliptical_family`
- `hike -> hike_family`

Fuera de alcance v1 para esta capa:

- `swim` no entra todavia porque hoy no forma parte de `INTENSITY_DISTRIBUTION_SPORTS`
- `strength`, `mobility` y `other` quedan fuera de DO-02

Regla propuesta:

- exigir `dominant_family_share >= 0.60` para producir una senal fuerte,
- si la dominancia solo existe a nivel familia, permitir la senal diaria pero dejar claro que la lectura es estructural de familia, no comparacion fina entre modalidades,
- si no existe dominancia clara ni a nivel familia ni a nivel `sport`, no emitir senal operativa.

Decision cerrada de fallback:

- sin dominancia clara, `dominant_family_prev_7d` queda vacio,
- `dominant_family_share_prev_7d` queda en `NaN`,
- `z1_pct_weighted_prev_7d`, `z2_pct_weighted_prev_7d`, `z3_pct_weighted_prev_7d` y `polarisation_index_prev_7d` quedan en `NaN`,
- `distribution_signal_confidence_prev_7d` queda vacio,
- `intensity_blackhole_flag` queda en `False`.

## 2. Proyectar solo los 7 dias previos
La senal en `sessions_day.csv` debe ser causal y diaria.

Decision cerrada para v2:

- para el dia `D`, usar siempre una ventana rolling `D-7 .. D-1`,
- excluir de forma estricta el dia actual mediante `shift(1)`,
- no usar semana ISO cerrada como semantica principal.

Decision de fuente:

- DO-02 debe recalcular la ventana rolling directamente desde `ENDURANCE_HRV_sessions.csv`,
- no debe proyectar sin mas la fila `sport x week` del sidecar semanal,
- el sidecar de DO-01 queda como referencia semanal, no como motor del calculo diario.

Esto alinea DO-02 con la semantica de:

- `load_3d`,
- `ACWR`,
- `monotony`,
- `strain`,
- `intensity_clustering`.

Implicacion:

- la senal cambia cada dia,
- no da saltos artificiales cada lunes,
- y representa `lo que arrastro de estructura de intensidad en los 7 dias previos`.

Consecuencia tecnica:

- los `z1_pct_weighted_prev_7d`, `z2_pct_weighted_prev_7d` y `z3_pct_weighted_prev_7d` deben recalcularse desde sesiones individuales de la ventana,
- no deben heredarse del sidecar semanal porque ese sidecar tiene granularidad `sport x semana ISO`.

## 3. Introducir primero un indice numerico
La primera senal candidata deberia ser algo tipo:

- `polarisation_index_prev_7d`

La formula final si debe quedar cerrada en esta tarea. Candidatas plausibles:

### Candidata A: ratio Seiler simplificado

- `seiler_low_z3 = (z1 + z2) / total = 1 - z3`

Ventajas:

- muy simple,
- facil de explicar,
- robusta a ruido pequeno en Z1/Z2.

Limitacion clave:

- no detecta bien el problema central de DO-02, porque una semana muy de Z2 y una semana muy de Z1 pueden dar valores parecidos si ambas tienen poco Z3.

Conclusion:

- util como descriptor general de baja intensidad,
- insuficiente como indice principal de `black-hole`.

### Candidata B: ratio de balance contra Z2

- `balance_ratio_prev_7d = (z1_pct_weighted + z3_pct_weighted) / max(z2_pct_weighted, 1.0)`

Ventajas:

- interpretable: compara `facil + duro` frente a `medio`,
- monotona respecto al sesgo hacia Z2,
- separa mejor semanas piramidales sanas de semanas demasiado centradas en trabajo medio.

Limitacion:

- puede crecer mucho cuando Z2 es casi cero.

Mitigacion:

- usarlo sobre semanas con confianza suficiente,
- y dejar que el flag operativo gobierne la interpretacion fuerte.

### Candidata C: ratio producto tipo polarizacion fuerte

- `product_ratio_prev_7d = (z1_pct_weighted * z3_pct_weighted) / max(z2_pct_weighted ** 2, 1.0)`

Ventajas:

- penaliza de forma fuerte semanas sin extremos claros,
- premia la coexistencia de base amplia y algo de intensidad real.

Limitaciones:

- demasiado sensible a `z3` casi nulo,
- menos interpretable para uso diario,
- mas facil de volver inestable con pocas sesiones.

Decision cerrada para v1:

- usar `polarisation_index_prev_7d` con la formula de la candidata B,
- mantener la candidata C solo como referencia metodologica si mas adelante se quiere una v2 mas exigente.

Definicion v1:

- `polarisation_index_prev_7d = (z1_pct_weighted_prev_7d + z3_pct_weighted_prev_7d) / max(z2_pct_weighted_prev_7d, 1.0)`

Semantica:

- indice alto = semana bien apoyada en Z1 y/o con algo de Z3 respecto a Z2,
- indice bajo = semana sesgada hacia trabajo medio,
- el indice no sustituye a `distribution_pattern`; solo resume riesgo estructural diario.

Justificacion empirica del umbral v1:

- sobre el subconjunto historico local con `dominant_family_share >= 0.60`, los percentiles del indice quedan aproximadamente en:
- `P10 = 2.151`
- `P25 = 3.360`
- `P50 = 6.246`
- `P75 = 15.003`
- fijar el corte en `2.2` situa el flag cerca del extremo bajo de la distribucion observada,
- eso evita elegir un valor arbitrario y mantiene una frecuencia de activacion baja pero no decorativa.

Importante: la señal se emite a nivel diario, pero la frecuencia operativa relevante se mide en episodios consecutivos (`runs`) de `True`, no en días sueltos. Un episodio puede cubrir varios días porque la ventana rolling se solapa, así que el porcentaje diario sobrestima la percepción de “cuántas veces pasa” si no se colapsan los días adyacentes.

Recomendacion v2:

- mantener `distribution_pattern` en el sidecar semanal,
- y usar en `sessions_day.csv` un indice numerico + un flag.

## 4. Anadir un flag operativo explicito
La capa diaria puede incluir:

- `intensity_blackhole_flag`
- `intensity_blackhole_episode_id`
- `intensity_blackhole_episode_len`
- opcionalmente `intensity_distribution_flag`

Semantica recomendada:

- activar solo cuando la confianza semanal sea suficiente,
- la familia dominante o el deporte dominante esten claros,
- y el reparto Z2 sea materialmente dominante sobre una base insuficiente de Z1.

Decision cerrada para v1:

- `intensity_blackhole_flag = True` solo si:
- `distribution_confidence in {moderate, high}`
- `n_sessions_usable >= 2`
- `dominant_family_duration_min >= 90`
- `dominant_family_share >= 0.60`
- `polarisation_index_prev_7d < 2.2`
- `z2_pct_weighted_prev_7d >= 30`
- `z3_pct_weighted_prev_7d <= 10`

Justificacion:

- `dominant_family_share >= 0.60` deja una cobertura util sin volver la senal demasiado permisiva,
- `polarisation_index_prev_7d < 2.2` captura semanas donde Z2 pesa demasiado frente a `Z1 + Z3`,
- `z2 >= 30` evita marcar semanas mayormente Z1 con algo de variacion,
- `z3 <= 10` evita confundir una semana con intensidad real moderada con un `black-hole` puro.

## 5. Mantener la confianza como primer ciudadano
Igual que en DO-01, esta tarea no debe sobreinterpretar semanas pobres.

La senal diaria no deberia activarse si:

- la semana previa tiene baja confianza,
- no hay suficiente volumen aerobico,
- hay demasiada mezcla de deportes o familias sin dominancia clara,
- o la semana solo tiene una sesion.

Recomendacion:

- incluir `distribution_signal_confidence_prev_7d`,
- recalcular esa confianza sobre la misma ventana rolling `D-7..D-1`,
- y no alimentar `reason_text` cuando esa confianza no sea suficiente.

Decision cerrada:

- DO-02 no debe heredar `distribution_confidence` desde el sidecar semanal,
- debe recalcular su propia confianza rolling con la misma filosofia de DO-01:
- `low` si `<2` sesiones utiles,
- `moderate` con `2` sesiones utiles o con volumen escaso,
- `high` cuando hay `>=3` sesiones utiles y volumen suficiente,
- degradar si hay cobertura parcial de zonas o presencia de `fallback`.

Que significa exactamente `confianza semanal sea suficiente`:

- no significa `certeza fisiologica alta`,
- significa `calidad minima suficiente para usar la señal como contexto operativo sin venderla como verdad fuerte`.

Lectura practica por niveles:

- `low`: la ventana existe pero es demasiado pobre o ambigua; puede guardarse el dato bruto, pero no debe activar `intensity_blackhole_flag` ni alimentar `reason_text`
- `moderate`: ya hay soporte minimo para interpretar la estructura de intensidad; el indice puede mostrarse y el flag puede activarse si ademas se cumplen dominancia y umbrales
- `high`: la ventana tiene soporte suficiente para una lectura estructural bastante estable; el indice y el flag son utilizables como contexto diario con menos reservas

Dicho de forma simple:

- `low` = `veo algo, pero no me fio lo bastante como para avisar`
- `moderate` = `ya hay base para avisar, aunque con cautela`
- `high` = `la senal ya es bastante creible como contexto operativo`

Regla operativa recomendada:

- para `polarisation_index_prev_7d`, permitir persistencia cuando la confianza sea `moderate` o `high`
- para `intensity_blackhole_flag`, exigir tambien `moderate` o `high`
- para `reason_text`, reservar consumo futuro preferentemente a `high` o a `moderate` con dominancia muy clara

## 5.1 Columnas nuevas en sessions_day.csv
Lista cerrada de columnas v1:

- `dominant_family_prev_7d` (`string`, vacio si no hay dominancia clara)
- `dominant_family_share_prev_7d` (`float`, `NaN` si no aplica)
- `n_sessions_usable_prev_7d` (`int`, `0` si no hay señal suficiente)
- `z1_pct_weighted_prev_7d` (`float`, `NaN` si no hay señal)
- `z2_pct_weighted_prev_7d` (`float`, `NaN` si no hay señal)
- `z3_pct_weighted_prev_7d` (`float`, `NaN` si no hay señal)
- `distribution_signal_confidence_prev_7d` (`string`: `low|moderate|high`, vacio si no aplica)
- `polarisation_index_prev_7d` (`float`, `NaN` si no hay señal)
- `intensity_blackhole_flag` (`bool`, `False` por defecto)

Regla de defaults:

- cuando no haya señal suficiente, las columnas numericas quedan en `NaN`,
- las categoricas quedan vacias,
- `n_sessions_usable_prev_7d` queda en `0`,
- el flag queda en `False`.

## 6. Validacion historica local
La tarea no debe quedar cerrada solo por criterio conceptual; necesita una comprobacion minima sobre el historico existente.

Resultado exploratorio sobre el historico local actual:

- filas `sport x week` con señal util y fila dominante por familia: `37`
- de esas, sobreviven `20` (`54.1%`) al exigir `dominant_family_share >= 0.60`
- con `0.70` solo sobrevivirian `10` (`27.0%`), demasiado restrictivo para este caso de uso
- con `0.55` sobrevivirian `27` (`73.0%`), pero sube mas el riesgo de mezcla semantica

Comparativa de candidatas sobre ese subconjunto `share >= 0.60`:

- `distribution_pattern == threshold`: `0/20` semanas; demasiado raro para servir como base operativa
- ratio de balance con regla mas estricta (`z2 >= 35`, `z1 <= 60`): `1/20` (`5%`); probablemente demasiado conservador
- ratio de balance v1 (`polarisation_index_prev_7d < 2.2`, `z2 >= 30`, `z3 <= 10`): `3/20` (`15%`); frecuencia razonable para una alerta contextual

Nota de lectura: esos `3/20` windows del sidecar son una validacion sobre ventanas semanales, pero la proyeccion diaria produce episodios de duracion variable. En el historico local la salida diaria suma `22` dias con flag `True`, que se agrupan en `13` episodios independientes. La magnitud operativa a seguir para esta senal es, por tanto, `episodios/run`, no `dias activos`.

Lectura:

- la señal v1 no queda muda,
- tampoco activa una fraccion absurda del historico,
- y detecta semanas que todavia aparecen como `pyramidal` en la etiqueta categórica de DO-01 pero ya muestran sesgo operativo hacia Z2.

## 7. Solapamiento con CDC-01
DO-02 no debe duplicar sin mas lo que ya expresan `ACWR`, `monotony` o `strain`.

Chequeo exploratorio sobre las `3` ventanas que activan `intensity_blackhole_flag` en la configuracion v1:

- `2/3` no coincidieron con `monotony` alta en la semana siguiente,
- `2/3` no coincidieron con `ACWR` alto en la semana siguiente,
- el grupo marcado por DO-02 presento medias de `monotony` y `ACWR` mas bajas que el resto del subconjunto analizado.

Interpretacion:

- DO-02 no parece redundante con CDC-01,
- su mejor lectura es complementaria: `no vas especialmente cargado, pero la semana se esta repartiendo demasiado en Z2`.

## 8. Mantenerlo fuera del gate
DO-02 no debe:

- recolorear `gate_badge`,
- alterar `Action`,
- ni modificar `FINAL/DASHBOARD` salvo como contexto futuro de `reason_text`.

Si se integra en `build_hrv_final_dashboard.py`, debe seguir el mismo principio que:

- `load_3d`,
- `ACWR`,
- `monotony`,
- `strain`,
- `intensity_clustering`.

Es decir:

- contexto operativo,
- nunca decision automatica.

## 9. Relevancia operativa esperada
Si se implementa bien, DO-02 aportaria una alerta que hoy no existe:

- no solo `vas cargado`,
- sino `vas cargando mal repartido`.

Eso puede ser especialmente util en semanas donde:

- el HRV sigue verde,
- no hay Z3 excesiva,
- pero la distribucion cae en demasiado trabajo medio.

## 10. Riesgos y limites

- no tratar una senal combinada como lectura fisiologica fuerte si mezcla deportes muy distintos,
- no construir una heuristica tan sensible que marque media base aeróbica como black-hole por error,
- no duplicar en `sessions_day.csv` toda la complejidad del sidecar semanal,
- no meter la etiqueta categorica en `reason_text` si no hay confianza suficiente.

## Orden de implementacion recomendado
0. Definir y codificar el mapeo `sport -> sport_family`.
1. Fijar la semantica causal de la ventana previa y la fuente rolling desde `sessions.csv`.
2. Decidir la regla de dominancia por familia y la caida a `sport` literal.
3. Recalcular zonas ponderadas y confianza sobre la ventana `D-7..D-1`.
4. Implementar `polarisation_index_prev_7d` con la formula v1 cerrada.
5. Implementar `intensity_blackhole_flag` con las guardas cerradas.
6. Integrar las columnas nuevas en `sessions_day.csv`.
7. Documentar contrato y limites.
8. Evaluar si merece entrar en `reason_text`.

## Criterios de aceptacion propuestos

- existe al menos una senal diaria derivada de la distribucion semanal previa,
- la senal usa siempre una ventana rolling de `7 dias previos` y excluye el dia actual,
- la implementacion recalcula la ventana rolling desde `sessions.csv` y no reutiliza directamente el sidecar semanal,
- la activacion no mezcla deportes sin regla explicita y permite dominancia por familia deportiva cuando eso refleje mejor la semantica real,
- el mapeo `sport -> sport_family` queda codificado de forma explicita,
- `sessions_day.csv` expone una lista cerrada de columnas nuevas con defaults documentados,
- `polarisation_index_prev_7d` tiene formula explicita y documentada,
- `intensity_blackhole_flag` tiene guardas explicitas de confianza, volumen y dominancia,
- la frecuencia de activacion se interpreta como episodios consecutivos de `True` y no como dias sueltos,
- el resumen de episodio evita contar a mano dias consecutivos en `sessions_day.csv`,
- `dominant_family_share >= 0.60` queda fijado como umbral v1,
- el corte `polarisation_index_prev_7d < 2.2` queda respaldado por percentiles del historico local,
- la validacion historica muestra una frecuencia de activacion util y no decorativa,
- la confianza rolling gobierna la emision del flag o del indice y no se hereda ciegamente del sidecar semanal,
- la capa sigue siendo contextual y no toca el gate HRV,
- `sessions_day.csv` puede expresar el riesgo de semana Z2-dominada,
- la documentacion deja claro que DO-02 es v2 de integracion operativa de DO-01.

## Decision recomendada
Implementar DO-02 si se quiere que la distribucion observada deje de ser solo una capa de analisis semanal y pase a formar parte del contexto diario del sistema.

La mejor version de esta tarea no es meter toda la tabla semanal dentro de `sessions_day.csv`, sino:

- proyectar una senal minima,
- causal,
- con confianza explicita,
- y util para detectar el black-hole de intensidad sin tocar el gate.


