# SYA-15 Continuidad aerobica Z1 alta

> Tarjeta Kanvas: `SYA-15` - grupo `Analysis / Coach`, estado actual `cyan` (pendiente de revision humana).
> Documento precedente: [SYA-10 Backlog diferido de senales retrospectivas y HRV longitudinal.md](SYA-10%20Backlog%20diferido%20de%20senales%20retrospectivas%20y%20HRV%20longitudinal.md)

## Texto original de la tarjeta

Objetivo: formalizar y evaluar la idea historicamente llamada `continuidad aerobica Z1 alta` como senal longitudinal `per-sport` no operativa, fijando su semantica, su destino natural y sus criterios de activacion.

Esta tarea no implementa aun la senal en `analysis_only_context`, `sessions_day`, `FINAL` ni `reason_text`.

## Estado real entregado 2026-05-18

El alcance ejecutado ya no coincide por completo con ese texto original.

Lo entregado en esta iteracion ha sido:

- definicion semantica reproducible de semanas `usable`, semanas `Z1-dominantes` y continuidad rolling `per-sport`
- implementacion local de `SYA-15` en `analysis/sya15_continuity.py`
- wrapper CLI en `scripts/analyze_sya15_continuity.py`
- sidecars locales reproducibles semanales en `analysis/reports/weekly/<week_start>_<week_end>/artifacts/`
- capa de preparacion semanal local con `analysis/run_weekly_analysis_prep.py`
- entrypoint semanal local con `analysis/analyze_weekly.py`
- integracion documental del flujo semanal local de `analysis`

Lo que sigue sin hacerse, y sigue explicitamente fuera del alcance canónico del sistema, es:

- incorporar `SYA-15` a `analysis_only_context`
- incorporarla a `sessions_day`
- incorporarla a `FINAL` o `DASHBOARD`
- usarla para recolorear gate, `reason_text` o logica HRV operativa global

Por tanto, la lectura correcta de esta tarjeta ya no es "solo semantica", sino:

- `SYA-15` queda definida e implementada como señal local reproducible del semanal de `analysis`
- no se promueve al pipeline HRV global ni a contratos canónicos

---

## Analisis tecnico 2026-05-15

### Conclusion ejecutiva

La tarea puede aportar valor, pero todavia no esta demostrado de forma fuerte que merezca vivir como senal formal separada y no como lectura derivada de `DO-01`.
Lo que si queda resuelto en este documento es la semantica minima y un primer chequeo historico reproducible.

Primera correccion semantica:

- `Z1 alta` no es un termino correcto para la definicion actual del proyecto
- el pipeline solo modela `Z1 = HR <= VT1` como una zona unica
- no existe hoy ninguna sub-zona interna de `Z1`
- por tanto, la lectura correcta no es "franja alta de Z1", sino continuidad de semanas `Z1-dominantes` o `sub-VT1`

Decision propuesta:

- mantenerla como senal longitudinal `per-sport` no operativa
- usar como unidad base el sidecar `ENDURANCE_HRV_intensity_distribution_weekly.csv`
- definir continuidad sobre ventana rolling `4w`, no sobre `7d` ni sobre una semana ISO aislada
- limitar la aplicabilidad inicial fuerte a `bike`
- dejar `trail_run` y `road_run` solo como candidatos exploratorios
- dejar `hike`, `swim`, `strength`, `mobility`, `elliptical` y `other` fuera de la primera version

### Que pretende medir

La senal, renombrada conceptualmente como `continuidad aerobica Z1-dominante` o `continuidad aerobica sub-VT1`, no intenta responder "cuanto Z1 hubo esta semana".
Intenta responder otra pregunta:

- si un deporte concreto viene acumulando semanas faciles de verdad
- si esa base aparece con continuidad de bloque y no como semanas sueltas
- si antes de subir carga en ese deporte existe una base reciente compatible con construccion aerobica

Escenario de uso canonico:

- antes de subir carga en `bike`, comprobar si en las `4` semanas previas ha existido continuidad suficiente de semanas con base Z1 dominante en esa misma modalidad
- en `trail_run` y `road_run`, esta misma lectura queda por ahora solo como exploratoria

### Relacion con SYA-08, DO-01 y DO-02

`SYA-08` no cerro esta pregunta.
Su cierre fue longitudinal, pero centrado en benchmarks repetibles, especializacion por deporte y lecturas tipo `route/climb/thermal`, no en continuidad de distribucion Z1 por bloque.

Por tanto:

- `DO-01` describe la distribucion observada de cada semana ISO por deporte
- `DO-02` describe una ventana causal corta `D-7..D-1` y detecta sesgo reciente hacia `Z2`
- `SYA-08` consolida lecturas longitudinales por deporte con foco en repeticion y especializacion
- `SYA-15` cubriria una pregunta distinta: continuidad reciente de bloque facil por deporte en horizonte `4w`

La hipotesis de valor incremental es esta:

- `DO-01` describe semanas sueltas por deporte
- `SYA-15` intentaria resumir continuidad de bloque `4w`

Pero esa diferencia sigue siendo, por ahora, una hipotesis razonable y no una demostracion cerrada de necesidad de producto.

### Nota terminologica

Mantengo el identificador historico `SYA-15` y el nombre de la tarjeta para no romper trazabilidad, pero dentro del analisis debe leerse asi:

- nombre heredado de tarjeta: `continuidad aerobica Z1 alta`
- nombre semantico correcto para la senal: `continuidad aerobica Z1-dominante`
- alternativa equivalente si se quiere enfatizar umbrales: `continuidad aerobica sub-VT1`

No se recomienda usar `Z1 alta` en nueva documentacion porque puede leerse de dos formas incorrectas:

- como si existiera una sub-zona alta dentro de `Z1`
- como si el proyecto siguiera la nomenclatura tipica de `5` zonas tipo Polar

### Definicion operacional propuesta

#### 1. Unidad base semanal

Usar una fila `sport x week` de `ENDURANCE_HRV_intensity_distribution_weekly.csv`.

Una semana `usable` para `SYA-15` debe cumplir:

- `distribution_confidence in {moderate, high}`
- `n_sessions_usable >= 2`
- `total_duration_min >= 90`

Esto reaprovecha exactamente las guardas reales de `DO-01` y evita crear una semantica paralela.

Limitacion conocida:

- este umbral minimo es igual para todos los deportes y todavia no esta calibrado de forma especifica para `bike`, `trail_run` y `road_run`
- en particular, puede ser demasiado permisivo para `bike`; por ahora se acepta como regla v1 solo para evaluar computabilidad minima

#### 2. Definicion de semana `Z1-dominante`

Definicion propuesta para una semana `Z1-dominante`:

- semana `usable`
- `z1_pct_weighted >= 75`
- `distribution_pattern in {pyramidal, polarized}`

Razon:

- `75%` separa base facil dominante de una semana solo "mas o menos comoda"
- exigir `pyramidal/polarized` evita aceptar semanas ambiguas o demasiado centradas en `Z2`
- no usa minutos absolutos como criterio principal porque eso confunde volumen con distribucion
- evita fingir una precision intra-Z1 que hoy el esquema no tiene

Dependencia canonica:

- `distribution_pattern` no se redefine en esta tarjeta
- `SYA-15` hereda la taxonomia canonica vigente de `DO-01`
- si `DO-01` cambia la lista o semantica de patrones, `SYA-15` debe revisarse antes de reutilizar esta condicion tal cual

Nota de QA:

- en el historico actual, toda semana `usable` con `z1_pct_weighted >= 75` ya cae tambien en `distribution_pattern in {pyramidal, polarized}`
- por tanto, la condicion compuesta no añade discriminacion observable hoy
- se puede mantener como guarda semantica explicita o simplificar en una revision futura a `z1_pct_weighted >= 75` sobre semanas `usable`

#### 3. Definicion de continuidad

Definicion propuesta sobre ventana rolling `4w`:

- continuidad positiva si en la semana actual de lectura mas las `3` semanas calendario inmediatamente anteriores hay al menos `3` semanas `Z1-dominantes`

Semantica:

- `3/4` evita que una unica semana muy facil pinte un bloque entero
- la ventana `4w` es lo bastante corta para ser util antes de subir carga y lo bastante larga para no solaparse con `DO-02`

Regla de borde obligatoria:

- si todavia no existen `4` semanas calendario desde el inicio del historico de ese deporte, la continuidad `4w` es `NA` y no debe evaluarse
- una semana sin fila para ese `sport` en `DO-01` cuenta como semana calendario no `Z1-dominante`
- una semana con fila pero no `usable` cuenta tambien como semana no `Z1-dominante`
- si la semana actual esta en curso en el momento de la lectura, se trata como semana no `Z1-dominante` hasta que este completa

Con esto la continuidad se evalua sobre calendario real, no sobre "ultimas cuatro filas disponibles".

Opcional para una v2 exploratoria:

- descriptor `8w` solo como capa secundaria, nunca como requisito inicial

### Aplicabilidad por deporte

Decision propuesta:

- aplicar en primera clase a `bike`
- dejar `trail_run` como candidato exploratorio de segunda prioridad
- dejar `road_run` como candidato exploratorio de segunda prioridad
- no aplicar por ahora a `hike`
- no aplicar a deportes cuya semantica de zonas o continuidad aerobica sea demasiado pobre en el historico actual

Motivo:

- `bike` tiene densidad y frecuencia de activacion suficientes para justificar exploracion real
- `trail_run` tiene cobertura de semanas usables, pero con la definicion actual la continuidad `4w` casi no activa
- `road_run` tiene poca muestra usable y una sola activacion `4w` bajo regla calendario
- `hike` tiene muy poca historia y una semantica distinta entre salida suave, terreno y excursion larga
- `swim`, `strength`, `mobility` y `elliptical` no deben mezclarse con esta lectura

### Cobertura real del historico actual

Chequeo reproducible ejecutado con ancla `2026-05-15` sobre `data/ENDURANCE_HRV_intensity_distribution_weekly.csv`.

Comando de referencia:

- `python scripts/analyze_sya15_continuity.py --today 2026-05-15`

Opcionalmente, el mismo comando puede emitir un reporte local reproducible con `--report-md` y/o `--report-json` hacia `analysis/ia_analisis_reviews/` u otra ruta local de trabajo.

Nota:

- `--today` fija una fecha de anclaje para reproducir exactamente este chequeo historico
- si se omite, el script usa la fecha actual y sirve para reevaluar el estado vivo de la senal
- `--window-size` debe ser `>= 2`; `1w` ya no se acepta porque no representa continuidad sino estado semanal puntual
- `--focus-sport` fija el deporte del reporte local; si se omite, el reporte usa el primer deporte del resumen disponible
- `--sports` solo afecta al detalle tabular en stdout; no redefine el foco del reporte local
- el payload `--report-json` se serializa ya como JSON estricto: huecos de calendario salen como `null`, no como `NaN`

Metodologia minima usada en este chequeo:

1. ordenar por `sport` y `window_start`
2. marcar semana `usable` si `distribution_confidence in {moderate, high}`, `n_sessions_usable >= 2` y `total_duration_min >= 90`
3. marcar semana `Z1-dominante` si la semana es `usable`, `z1_pct_weighted >= 75` y `distribution_pattern in {pyramidal, polarized}`
4. validar que cada `window_start` este alineado con lunes ISO; si no lo esta, abortar el chequeo
5. reconstruir calendario semanal continuo por deporte en saltos de `7` dias desde el primer `window_start` hasta la semana actual anclada
6. evaluar continuidad `4w` solo cuando ya existen `4` semanas calendario; semanas ausentes o no `usable` cuentan como no `Z1-dominantes`
7. si la semana actual esta en curso, se mantiene en calendario como semana no `Z1-dominante` hasta completarse, aunque `DO-01` ya tenga una fila para esa semana

Nota de implementacion actual:

- la version local del script permite variar `--window-size`, pero mantiene la misma semantica: continuidad rolling por deporte con ventana minima `2w`
- la sensibilidad de ventana que emite el reporte local excluye `1w` a proposito, porque `1w` no es una señal de continuidad interpretable

Cobertura observada:

- `bike`: `53` semanas calendario, `45` filas observadas, `28` semanas `usable`, `23` semanas `Z1-dominantes`
- `trail_run`: `53` semanas calendario, `42` filas observadas, `19` semanas `usable`, `11` semanas `Z1-dominantes`
- `road_run`: `52` semanas calendario, `35` filas observadas, `6` semanas `usable`, `3` semanas `Z1-dominantes`
- `hike`: `47` semanas calendario, `4` filas observadas, `3` semanas `usable`, `3` semanas `Z1-dominantes`

Nota de lectura para `hike`:

- la gran diferencia entre semanas calendario y filas observadas no se interpreta aqui como bug
- refleja simplemente que `hike` tiene densidad historica demasiado baja para esta senal y por eso queda fuera de primera version

Frecuencia de activacion observada con la definicion propuesta:

- semanas `Z1-dominantes` en `bike`: `23/28` semanas `usable`
- semanas `Z1-dominantes` en `trail_run`: `11/19` semanas `usable`
- semanas `Z1-dominantes` en `road_run`: `3/6` semanas `usable`
- continuidad `4w` positiva en `bike`: `12/50` ventanas evaluables (`24%`)
- continuidad `4w` positiva en `trail_run`: `1/50` ventanas evaluables (`2%`)
- continuidad `4w` positiva en `road_run`: `1/49` ventanas evaluables (`2%`)
- continuidad `4w` positiva en `hike`: `0/44` ventanas evaluables (`0%`)

Sensibilidad de umbral en `bike`, reproducible con el mismo script variando solo `--min-positive`:

- `python scripts/analyze_sya15_continuity.py --today 2026-05-15 --min-positive 2`
- `python scripts/analyze_sya15_continuity.py --today 2026-05-15 --min-positive 3`
- `python scripts/analyze_sya15_continuity.py --today 2026-05-15 --min-positive 4`

- `2/4`: `29/50` ventanas evaluables (`58%`)
- `3/4`: `12/50` ventanas evaluables (`24%`)
- `4/4`: `2/50` ventanas evaluables (`4%`)

Lectura de estos resultados:

- en `bike`, aunque `23/28` semanas `usable` son `Z1-dominantes`, la continuidad `4w` no queda permanentemente encendida: activa en `24%` de las ventanas evaluables
- eso no demuestra aun que discrimine bien, pero si evita la conclusion fuerte de que este "siempre en positivo"
- en `bike`, las `12` ventanas positivas no aparecen como un unico bloque aislado; se agrupan en `4` episodios de calendario con longitudes `3 + 3 + 2 + 4` semanas
- detalle de episodios `bike`: `2025-07-07 a 2025-07-21`, `2025-08-25 a 2025-09-08`, `2025-10-13 a 2025-10-20` y `2026-04-20 a 2026-05-11`
- esas fechas son fechas de evaluacion de ventana `4w`, no fechas directas de entrenamiento; cada marca resume la semana de lectura mas las `3` semanas inmediatamente anteriores
- tambien importa el silencio entre episodios: entre `2025-10-20` y `2026-04-20` hay un gap de `26` semanas sin continuidad `4w` positiva, asi que la senal no debe leerse como patron cronico permanente de `bike`
- en el historico total de `bike`, esas `12` semanas positivas cubren aproximadamente `12/53` del calendario, es decir, cerca del `23%` del tiempo total observado; el patron que emerge es episodico, no basal
- sensibilidad de umbral en `bike`: `2/4` activa `29/50` ventanas evaluables (`58%`) y `4/4` solo `2/50` (`4%`); por eso `3/4` sigue siendo por ahora el mejor balance entre tasa de activacion y ruido
- esa distribucion temporal no prueba valor prospectivo, pero si sugiere que la senal no describe solo una anomalia puntual del historico
- en `trail_run` la continuidad `4w` con esta configuracion activa muy poco
- en `road_run` la muestra util sigue siendo fragil y la continuidad apenas aparece una vez
- la formulacion actual parece mas prometedora para `bike` que para el resto

Importante:

- estos resultados sostienen computabilidad minima
- no demuestran por si solos valor incremental suficiente frente a una consulta manual sobre `DO-01`
- este chequeo debe revisarse si cambia de forma material el historico disponible, si se acumulan nuevas semanas en `trail_run` o `road_run`, o si se recalibran los umbrales fisiologicos usados para zonificar

### Destino natural

Decision arquitectonica actual:

- `SYA-15` queda ubicada en la capa local del semanal de `analysis`
- se ejecuta mediante `run_weekly_analysis_prep.py` y puede ser consumida por `analyze_weekly.py`
- genera sidecars locales reproducibles `sya15_continuity_<sport>_<min>of<window>w.(md|json)`
- no forma parte del pipeline HRV global ni del contrato canónico de sidecars operativos

Justificacion:

- el valor incremental frente a una lectura manual de `DO-01` sigue siendo hipotesis
- solo `bike` sostiene hoy una frecuencia de activacion con interes real
- `trail_run` y `road_run` siguen demasiado debiles para justificar un contrato global nuevo
- los umbrales y la semantica todavia pueden moverse tras una revision cualitativa de episodios reales

Condicion de promocion futura a sidecar canónico o señal global:

- documentar una revision cualitativa minima sobre `bike` con al menos `3` ventanas positivas y `3` negativas donde el autor del analisis semanal pueda justificar con evidencia de bloque que las positivas corresponden a base sostenida y las negativas a ausencia de esa base
- mantener la misma definicion operativa durante al menos una revision historica posterior del chequeo, sin necesidad de cambiar umbrales ni la regla `4w`; por tanto, esta condicion solo puede evaluarse en una iteracion posterior y no en la primera tarjeta de implementacion
- nombrar un consumidor concreto fuera de la narrativa libre del informe semanal, por ejemplo un campo estructurado de `analysis` o una salida semanal reutilizable con contrato explicito

Implicacion para esta entrega:

- la semantica ya no es el unico resultado de la tarea
- la implementacion ya existe, pero confinada al semanal local de `analysis`
- una promocion posterior a sidecar canónico o señal global requeriria una decision nueva y explicitamente documentada

No debe entrar todavia en:

- `analysis_only_context`
- `sessions_day`
- `FINAL`
- `reason_text`

hasta que exista una validacion minima de frecuencia, interpretabilidad y utilidad real.

### Criterios de aceptacion revisados

1. Existe una definicion escrita y reproducible de semana `Z1-dominante` basada en `distribution_confidence`, `n_sessions_usable`, `z1_pct_weighted` y `distribution_pattern`.
2. Existe una definicion escrita y reproducible de continuidad sobre ventana rolling `4w`.
3. Existe una decision documentada de aplicabilidad por deporte.
4. Existe comparacion escrita con `SYA-08`, `DO-01` y `DO-02` y queda explicitado si el valor incremental sigue siendo hipotesis o ya esta demostrado.
5. Existe verificacion minima de cobertura historica por deporte.
6. Existe escenario de uso claro y no decorativo.
7. Existe chequeo historico minimo de frecuencia de activacion para evitar una senal trivialmente constante o casi muda.
8. Existe implementacion local reproducible en `analysis/` sin tocar el pipeline HRV global.
9. Existe integracion del semanal local suficiente para generar sidecars, prep semanal e informe semanal local reproducible.

### Estado tras este analisis

La tarea ya no esta bloqueada por ambiguedad terminologica.
Tampoco esta vacia desde el punto de vista operacional: ya existe definicion, validacion historica minima e implementacion local reproducible.

Siguen quedando dos reservas antes de defender una promocion de alcance fuera de `analysis`:

- el valor incremental frente a una lectura manual de `DO-01` sigue siendo una hipotesis razonable, no una necesidad demostrada
- la configuracion actual parece util sobre todo en `bike`; en `trail_run` y `road_run` sigue siendo demasiado debil para tratarlos como primera clase

Riesgo adicional que queda explicitamente fuera de resolucion en esta entrega:

- si `vt1_used` o `vt2_used` cambian de forma retroactiva en el pipeline de sesiones, semanas historicas ya clasificadas como `Z1-dominantes` pueden reclasificarse sin que cambie el entrenamiento real
- por tanto, cualquier lectura longitudinal de `SYA-15` depende tambien de la estabilidad de los umbrales fisiologicos usados por el pipeline

Lo que quedaria para una futura tarjeta ya no es implementar `SYA-15` en `analysis`, sino decidir si merece promoción de alcance:

- decidir si merece existir como señal formal separada fuera del semanal local o basta con una lectura/manual query sobre `DO-01`
- decidir si la formulacion debe limitarse persistentemente a `bike`
- decidir si alguna parte debe promoverse a sidecar canónico, contexto estructurado o narrativa operacional reutilizable

### Fuera de alcance

- tocar `sessions.csv`, `sessions_day.csv`, `FINAL` o `DASHBOARD` para incorporar `SYA-15`
- introducir una nueva taxonomia de coaching sin backtest
- reabrir por esta via la capa canonica de distribucion semanal
- recolorear el gate o modificar `reason_text` con `SYA-15`
