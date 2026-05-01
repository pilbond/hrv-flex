
## Objetivo
Convertir la materia prima actual de sesiones en una capa estable de lectura por deporte que describa la distribucion observada de intensidad y permita clasificar patrones como polarizado, piramidal, threshold o mixto con base en la estructura real de las sesiones.

## Tesis central
La tarea DO-01 no consiste en anadir mas metrica de zonas a nivel sesion. Esa parte ya existe. La tarea consiste en canonizar una capa agregada y reutilizable por deporte para que la lectura de distribucion observada no dependa de una interpretacion manual en prompts o informes semanales.

## Estado actual del repo
Hoy el pipeline ya calcula bastante a nivel sesion:

- `z1_pct`, `z2_pct`, `z3_pct`
- `z2_total_min`, `z3_total_min`
- `work_n_blocks`, `work_total_min`, `work_longest_min`, `work_avg_z3_pct`
- `intensity_category`
- `session_group`

Esto vive en `build_sessions.py` y se guarda en `ENDURANCE_HRV_sessions.csv`.

Lo que no existe todavia es:

- una salida canonica por deporte,
- una ventana definida de observacion,
- una regla estable de clasificacion del patron observado,
- una capa de confianza para no sobreinterpretar semanas pobres.

## Relacion con analysis/
La tarea si tiene relacion directa con `analysis/`, especialmente con el analisis semanal.

`analysis/WEEKLY_ANALYSIS_METHOD.md` ya espera una seccion llamada `Distribucion observada por deporte` y permite describir la semana como `polarizado`, `piramidal`, `threshold` o `mixto`.

Por tanto:

- `analysis/` ya consume esta necesidad a nivel metodologico,
- pero todavia no existe una capa canonica del pipeline que la resuelva de forma estable.

La mejor lectura de DO-01 es:

- implementarla primero en el pipeline global,
- y despues hacer que `analysis/` la consuma.

## Relacion con Intervals.icu
Intervals ya muestra una clasificacion visual tipo `Polarizado`, `Piramidal`, `Umbral`, `HIIT`, `Base`, etc.

Pero DO-01 se diferencia en varias cosas:

- no depende de una UI externa,
- permite separar por deporte dentro de nuestro pipeline,
- permite fijar nuestras reglas de confianza,
- permite reutilizar la salida en `analysis/`, comparativas y auditoria,
- y evita depender del mapeo interno de zonas o de las limitaciones de configuracion de Intervals.

Dicho simple:

- Intervals da una clase visual,
- DO-01 pretende una salida canonica, documentada y reutilizable.

## Que existe ya y que falta

### Ya existe
- distribucion `Z1/Z2/Z3` por sesion,
- estructura de trabajo sostenido,
- clasificacion de sesion por estructura,
- separacion basica por deporte.

### Falta
- resumen agregado por deporte,
- clasificacion de patron observada sobre ventana,
- confianza de la lectura,
- documentacion contractual de esta capa.

## Aporte de la tarea
Didacticamente, esta tarea aporta una capa distinta a `intensity_category`.

- `intensity_category` responde: `que tipo de sesion fue esta?`
- `DO-01` responderia: `como se organizo realmente la intensidad de este deporte en la semana o ventana observada?`

Ejemplo:

- hoy el sistema puede decir que hubo `2 work_intense`, `1 easy` y `1 work_steady`,
- con DO-01 podria decir que en `bike` la distribucion observada fue `piramidal`, con predominio claro de Z1, Z2 relevante y Z3 baja pero presente.

## Mejora medible esperada
Sobre los datos actuales del repo:

- `ENDURANCE_HRV_sessions.csv` contiene `348` sesiones,
- en los deportes aeróbicos principales (`bike`, `road_run`, `trail_run`) hay `172` sesiones utiles,
- cobertura de `z1/z2/z3` completa en esos deportes: `100%`.

Esto implica que la materia prima ya esta disponible para construir la capa canonica.

A nivel de ventanas semanales por deporte:

- existen `109` ventanas `semana x deporte`,
- `44` (`40.4%`) ya tienen al menos `2` sesiones utiles,
- `16` (`14.7%`) ya tienen al menos `3` sesiones utiles.

Por tanto, una implementacion de DO-01 permitiria desde el dia uno:

- pasar de `0` resúmenes canónicos por deporte a `44` ventanas semanales utilizables con confianza minima,
- y tener `16` ventanas ya aptas para una lectura con confianza mas alta.

Esto no demuestra que la clasificacion final sea automaticamente perfecta, pero si demuestra que la capa no seria decorativa: produciria una salida inmediata y reutilizable.

## Lectura exploratoria del historico actual
Como exploracion preliminar sobre los datos actuales:

- `bike`: media aproximada `83.3 / 15.2 / 1.5` en `Z1/Z2/Z3`
- `road_run`: `76.4 / 19.0 / 4.7`
- `trail_run`: `73.6 / 23.1 / 3.3`

En agregado medio, los tres deportes principales se parecen mas a un patron `piramidal` que a uno `threshold` o `polarizado`.

Importante:

- esto es una exploracion util,
- no debe tratarse todavia como salida oficial del sistema,
- la regla de clasificacion definitiva debe fijarse en contrato.

## Riesgos y limites

- no asumir que cualquier columna de zonas implica comparabilidad fisiologica fina entre deportes,
- tratar la lectura principalmente como comparacion intra-deporte, no como comparacion fisiologica fuerte entre deportes,
- no tratar una semana con pocas sesiones como clasificacion fuerte,
- no mezclar deportes con semanticas distintas en una unica etiqueta global si la senal es ambigua,
- no copiar sin filtro el modelo `fused/combined` del proyecto base si aqui no hay la misma calidad de sensores o el mismo objetivo de producto.

Limitacion metodologica clave:

- las zonas HR no significan exactamente lo mismo en `bike`, `road_run` y `trail_run`;
- la componente mecanica, la estabilidad del esfuerzo y los propios umbrales VT1/VT2 hacen que un mismo patron fisiologico no se exprese igual en todos los deportes;
- por tanto, esta capa debe leerse sobre todo como `como fue mi bike esta semana respecto a otras semanas de bike`, no como `si mi bike fue mas polarizado que mi trail`.

## Que aporta el proyecto base
El proyecto `intervalsicugptcoach-public` aporta tres cosas utiles:

- semantica clara de patrones de distribucion,
- bandas de clasificacion (`threshold`, `pyramidal`, `polarised`),
- y reglas de confianza (`min_sessions`, `dominant_sport_required`, etc.).

La leccion importante no es portar todo su sistema de `power`, `fused` y `combined`, sino adoptar su disciplina de:

- formula explicita,
- interpretacion explicita,
- y confianza explicita.

## Desarrollo propuesto

### 1. Canonizar la logica antes que el archivo
La necesidad principal de DO-01 no es crear un CSV nuevo, sino fijar una unica logica reutilizable para agregar por deporte y ventana.

Decision recomendada para v1:

- implementar primero una funcion canonica reutilizable derivada de `sessions.csv`;
- persistir tambien un sidecar estable `ENDURANCE_HRV_intensity_distribution_weekly.csv` para evitar reconstruccion ad hoc en informes semanales.

Unidad canonica recomendada:

- `sport x window`

Ventana inicial recomendada:

- `7d` semanal

## 2. Basarla en sessions.csv, no en sessions_day.csv
La fuente correcta es `ENDURANCE_HRV_sessions.csv` porque:

- la tarea es por deporte,
- `sessions_day.csv` mezcla deportes dentro del mismo dia,
- y la lectura estructural fina ya esta calculada a nivel sesion.

## 3. Limitar la v1 a deportes aerobicos claros
Alcance inicial recomendado:

- `bike`
- `road_run`
- `trail_run`
- `elliptical`
- `hike`
- opcional mas adelante: `swim`

Excluir en v1:

- `strength`
- `mobility`
- `other`
-

No porque no tengan columnas, sino porque su comparabilidad fisiologica fina para esta capa es menor o mas ambigua.

## 4. Agregar por deporte y ventana
Campos propuestos:

- `window_start`
- `window_end`
- `sport`
- `n_sessions`
- `total_duration_min`
- `z1_pct_weighted`
- `z2_pct_weighted`
- `z3_pct_weighted`
- `z1_min`
- `z2_min`
- `z3_min`
- `work_total_min`
- `work_n_blocks`
- `work_longest_min`
- `intensity_category_mix`
- `distribution_pattern`
- `distribution_confidence`
- `distribution_notes`

Regla de ponderacion que debe quedar explicita:

- `z1_pct_weighted = sum(z1_total_min) / sum(z1_total_min + z2_total_min + z3_total_min) * 100`
- `z2_pct_weighted = sum(z2_total_min) / sum(z1_total_min + z2_total_min + z3_total_min) * 100`
- `z3_pct_weighted = sum(z3_total_min) / sum(z1_total_min + z2_total_min + z3_total_min) * 100`

No usar media aritmetica simple de porcentajes de sesion.

Decision practica para v1:

- anadir `z1_total_min` a `sessions.csv` para completar la capa que hoy ya expone `z2_total_min` y `z3_total_min`;
- evitar recalcular esta pieza de forma repetida en cada agregacion semanal;
- usar minutos por zona como base primaria de agregacion, no porcentajes sueltos.

Estado v1 implementado:

- `build_sessions.py` ya persiste `z1_total_min` en `sessions.csv`,
- `build_sessions.py` ya genera `ENDURANCE_HRV_intensity_distribution_weekly.csv`,
- la salida semanal queda definida por `sport x week` con `n_sessions_total`, `n_sessions_usable`, minutos ponderados por zona, `work_*`, `distribution_pattern`, `distribution_confidence` y `distribution_notes`.

El dato primario de esta capa debe ser:

- tiempo total por zona,
- porcentaje ponderado por tiempo,
- trabajo sostenido (`work_*`),
- y confianza.

La etiqueta de patron debe ser secundaria.

## 5. Clasificar el patron observado
La clasificacion categórica no debe ser la salida principal en v1.

Prioridad recomendada:

1. porcentajes ponderados `Z1/Z2/Z3`
2. `work_total_min` y `work_n_blocks`
3. confianza
4. `distribution_pattern` como resumen opcional

Version minima para v1 si se mantiene etiqueta:

- `threshold`: `Z2 >= Z1` y `Z2 > Z3`
- `pyramidal`: `Z1 > Z2 > Z3` y `Z1 - Z2 >= 10`
- `polarized`: `Z1 >= 70` y `Z3 >= Z2`
- `mixed`: patron ambiguo o multimodal

Estas reglas deben tratarse como resumen descriptivo, no como verdad fisiologica fuerte.

El margen `Z1 - Z2 >= 10` evita que distribuciones casi-threshold como `45/40/15` queden clasificadas automaticamente como piramidales claras.

Version mas ambiciosa y mas cercana al repo base:

- derivar un indice explicito estilo Seiler o Treff sobre el colapso a 3 zonas,
- y mapear bandas de clasificacion sobre ese indice.

Recomendacion:

- empezar por la salida numerica y descriptiva,
- dejar la variante tipo Seiler/Treff como v2 o como columna adicional.

## 6. Anadir reglas de confianza
Inspiracion del proyecto base:

- `low` si `<2` sesiones utiles,
- `moderate` con `2` sesiones,
- `high` con `>=3` o `>=4` sesiones,
- rebajar confianza si `zones_source` es pobre o si la mezcla de deportes hace la lectura ambigua.

Esto es clave para no sobreinterpretar ventanas debiles.

Regla base recomendada en v1:

- `low` si `<2` sesiones utiles;
- `moderate` si `2` sesiones utiles;
- `moderate` si `>=3` sesiones pero `total_duration_min < 90`;
- `high` si `>=3` sesiones y `total_duration_min >= 90`.

Esto evita tratar igual tres sesiones muy cortas que tres sesiones con volumen semanal representativo.

`intensity_category_mix` debe definirse explicitamente si se mantiene.

Recomendacion v1:

- que represente una distribucion resumida de categorias, por ejemplo:
  - `easy=2;work_steady=1;work_intense=1`

No usarlo como etiqueta dominante unica si se quiere preservar riqueza descriptiva.

## 7. Integrar con analysis/
Una vez exista la logica canonica:

- `analysis/WEEKLY_ANALYSIS_METHOD.md` podra consumirla directamente,
- la seccion `Distribucion observada por deporte` dejara de depender de reconstruccion manual,
- y el analista podra centrarse en la interpretacion, no en rehacer el calculo.

Decision importante:

- DO-01 no depende tecnicamente de CDC-01;
- ambas tareas pueden implementarse en paralelo;
- CDC-01 aporta mas valor al flujo diario, mientras que DO-01 aporta mas al analisis semanal y a la lectura estructural por deporte.

## 8. Actualizar contrato
Documentos a actualizar:

- `docs/contracts/ENDURANCE_HRV_Sessions_Schema.md`
- `docs/contracts/ENDURANCE_HRV_Spec_Tecnica.md`
- si aplica, referencias metodologicas en `analysis/WEEKLY_ANALYSIS_METHOD.md`

Debe quedar claro:

- que la capa es descriptiva,
- que esta orientada a lectura por deporte,
- que tiene reglas de confianza,
- y que no sustituye el gate HRV.

## Orden de implementacion recomendado
1. Definir ventana, deportes validos y campos canonicos.
2. Crear funcion canonica derivada desde `sessions.csv`.
3. Fijar ponderacion por tiempo y reglas de confianza.
4. Validar historico y cobertura por deporte.
5. Anadir `distribution_pattern` solo como resumen opcional.
6. Actualizar contratos.
7. Integrar el consumo en `analysis/`.

Si mas adelante aparece un consumidor claro fuera de `analysis/`, entonces valorar persistir un CSV derivado.

## Criterios de aceptacion propuestos

- existe una logica canonica por deporte y ventana reutilizable desde el pipeline o `analysis/`,
- la salida resume `Z1/Z2/Z3` y `work_*` de forma estable,
- la ponderacion por zonas esta definida por tiempo total, no por media simple de sesiones,
- la clasificacion del patron observado, si existe, es secundaria y esta documentada,
- cada fila incluye nivel de confianza,
- la documentacion explicita que la lectura es principalmente intra-deporte,
- `analysis/` puede consumir esta capa sin reconstruirla manualmente,
- la implementacion no afecta al gate HRV ni a `FINAL/DASHBOARD` salvo contexto futuro explicito.

## Decision recomendada
Implementar DO-01 si se quiere que la lectura por deporte deje de vivir solo en prompts o en interpretacion manual.

La mejor version de la tarea en este repo no es copiar tal cual la clasificacion de Intervals ni todo el stack del proyecto base, sino:

- formalizar una salida por deporte,
- con semantica simple,
- reglas de confianza,
- y uso directo por `analysis/`.

Importe, al finalizar el trabajo dejas todos los md relacionados actualizados.
