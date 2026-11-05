# HG-04: Ventana fija de cálculo de RMSSD_stable y revisión de la estabilización

Estado (2026-10-27): investigación cerrada (`green` en Kanvas). Este documento conserva el razonamiento, las comparaciones y las propuestas históricas. El candidato práctico de inicio 90 s, corte máximo 375 s y recorte final 15 s se entrega a [HG-10](<HG-10 Corte historico y contrato de pares consecutivos.md>) para comparación y eventual activación; no cambia por sí mismo el cálculo, el contrato ni la QA vigente.

> **Lectura de las decisiones históricas.** Los apartados que seleccionan `H3S90T375NL`, proponen retirar la penalización `LAT_NAN` o reconsideran `MISMATCH` son escenarios de HG-04, anteriores a la decisión final de [HG-09 §9](<HG-09 Politica de Calidad HRV para ventana 90-375 s.md>). HG-10 conserva la exclusión y la cautela actuales para ambos motivos. El criterio de cierre operativo está en la nota de HG-10.

> **Cierre de investigación propuesto — 2026-10-27.** El alcance exploratorio de HG-04 puede
> pasar a revisión: el inicio 90 s y el corte máximo 375 s quedan como candidato práctico, no
> como ventana fisiológicamente superior demostrada. No se observó una meseta de RMSSD que
> justifique escoger una cola «más verdadera». La decisión de Calidad está en HG-09 y la
> activación, el contrato y el recálculo histórico en HG-10. Cerrar HG-04 en Kanvas no cambia
> CORE, FINAL ni el semáforo de producción.

> **Traspaso de Calidad — 2026-10-26.** La decisión sobre el efecto de `LAT_NAN` y
> `STAB_LAST2_MISMATCH` en `Calidad` sigue abierta y tiene ahora una tarea propia:
> [HG-09](<HG-09 Politica de Calidad HRV para ventana 90-375 s.md>). Los ensayos existentes son
> escenarios aislados, no una migración aprobada. La auditoría corregida de diez ECG no halló
> errores del conversor entre las discrepancias revisadas, pero no valida la limpieza de toda la
> señal ni demuestra utilidad de retirar `MISMATCH`. Las treinta ventanas alternativas por día
> muestran que la discordancia no se limita a la cola; que esta aparezca en el decil superior en
> 7/10 días **no está garantizado por la selección**, aunque esta pueda favorecerlo. Las cifras
> antiguas de diez controles `<8%` se retiraron porque no se conservaron sus fechas y semilla.
> Los apartados anteriores titulados «cierre de Calidad» quedan como historia del ensayo, no
> como cierre de la decisión normativa. Producción y `docs/contracts/` siguen sin cambios.

> **Rectificación bibliográfica y técnica — 2026-10-25.** Los dos informes incorporados hoy se han corregido tras revisar el paper original, los CORE y `egc_to_rr.py`. La concordancia H10–ECG publicada apoya el RR interno de la banda en adultos jóvenes y segmentos limpios, pero no valida toda nuestra era Polar ni nuestro conversor ECG. Este último **no interpola picos entre muestras**; su resolución numérica de salida no prueba precisión submuestra. El recuento de 1162 intervalos retirados corresponde a **489** días no `INVALID` de la copia truncada, no a 486. La clasificación de 29 presuntos latidos perdidos y la cuantización entre eras siguen sin verificación reproducible. Estar bajo 55 lpm no demuestra saturación parasimpática, y la correlación entre RR y lnRMSSD no prueba que FC sea prescindible en el gate. El protocolo publicado hace plausible un inicio de 90 s, sin validar el tramo propio ≈90–360 s. No cambian la candidatura de la ventana, la política de Calidad ni el semáforo de producción.

## Cierre de la selección de Calidad — 2026-10-23

**RECTIFICACIÓN posterior, 2026-10-23:** el título «cierre» fue excesivo: seleccionaba una copia existente sin probar la retirada de mismatch ni la alternativa de semáforo. Ya se han ejecutado solo esas pruebas pendientes sobre el CORE guardado, sin reprocesar RR. Véase [el informe incremental](../../research/reports/hg04_calidad_semaforo_incremental_2026-10-23.md). Quitar también mismatch recupera 29 días y cambia 30 gates (22 en fechas distintas de las recuperadas); el total de rojos sigue en 123. La alternativa ámbar, manteniendo Calidad NL, cambia 30 rojos a ámbar; la combinada cambia 61 gates frente a NL. Las métricas diarias permanecen idénticas. La recomendación de diseño revisada es desacoplar latencia y mismatch de elegibilidad técnica conservando sus avisos; el semáforo ámbar queda como alternativa experimental concreta, sin validación de superioridad. La decisión conservadora de abajo se conserva como antecedente y queda superada por esta comparación. Producción no modificada.

**Decisión de diseño:** para inicio fijo 90 s y corte máximo de grabación 375 s, seleccionar la política ya ensayada `H3S90T375NL`. Se elimina la exigencia de latencia finita/en rango para dar Calidad OK; `LAT_NAN` permanece informativo. Se conservan las demás reglas del ensayo, incluido `STAB_LAST2_MISMATCH`. Esta selección cierra la comparación de políticas de Calidad en esta fase; no ejecuta una migración de producción ni certifica validez fisiológica. Los párrafos anteriores en el tiempo que dejan pendiente elegir entre esas dos políticas quedan subordinados a esta decisión.

### Evidencia comprobada sin repetir los replays

Verificación de los CORE/FINAL existentes con `research/experiments/hg04_replay/scripts/verify_quality_closure.py`. Las copias contienen **506 fechas hasta 2026-10-22**, no la fila adicional 2026-10-23 incorporada después al Excel. No se reconstruyeron RR ni se regeneraron CORE/FINAL. Las diferencias porcentuales siguientes son relativas al RMSSD diario de referencia, no diferencias logarítmicas. Los umbrales 5/10/15% son descriptores, no márgenes clínicos ni criterios de aceptación.

| Comparación (corte menos referencia) | Cohorte | n | Media ΔRMSSD ms | Media ΔRMSSD % | Mediana abs(Δ%) | Días abs(Δ%) >10 | Rango Δ% | Media ΔFC lpm |
|---|---|---:|---:|---:|---:|---:|---|---:|
| Corte frente a C (Actual del replay) | OK en ambas | 393 | +0,7517 | +1,9387 | 2,524 | 27 | −10,695 a +25,259 | −0,3104 |
| Corte frente a H3S90 | OK en ambas | 395 | +0,4772 | +1,1270 | 1,451 | 0 | −6,258 a +8,211 | −0,2162 |
| Corte frente a C | No INVALID en ambas, valores presentes | 486 | +0,7693 | +2,2085 | 2,912 | 56 | −39,705 a +30,226 | −0,3245 |
| Corte frente a H3S90 | No INVALID en ambas, valores presentes | 486 | +0,5712 | +1,4230 | 1,593 | 6 | −9,140 a +13,200 | −0,2362 |

**Rectificación del chat:** sí existen diferencias grandes frente a C, no era necesario formularlo como posibilidad. Entre días OK comunes, 2026-09-14 pasa de 39,095 a 48,970 ms (+25,259%; FC 53,335 a 50,731), 2026-06-29 de 29,600 a 35,951 ms (+21,457%) y 2026-02-12 de 29,160 a 35,332 ms (+21,166%). La comparación C/corte mezcla HG-03, el inicio fijo y el corte; no atribuir esos extremos al corte solo. Frente a H3S90, el máximo porcentual en OK comunes es +8,211% el 2026-06-11 (37,543 a 40,626 ms). La similitud media no implica identidad diaria ni demuestra qué medición es más verdadera. La selección OK común condiciona la muestra; por eso se informa también no INVALID.

Entre corte y corte NL, **RMSSD y FC diarios coinciden en las 506 filas**. Se confirman los resultados ya disponibles: 36 días pasan de FLAG a OK y 38 semáforos cambian. NL conserva 454 OK, 35 FLAG y 17 INVALID, frente a 418/71/17 con la regla de latencia. No hay motivo para repetir ese ensayo.

### Política cerrada para esta fase

1. **Medición:** HG-03, inicio a 90 s, corte máximo 375 s y recorte de cola de 15 s. El tramo habitual es aproximadamente 90–360 s; los límites reales dependen de los latidos completos.
2. **Latencia:** se conserva el diagnóstico, pero no decide el inicio ni penaliza automáticamente Calidad. Su ausencia no prueba error técnico; tampoco se afirma que todos los días recuperados tengan la misma repetibilidad. El ruido mayor observado en los 22 nuevos LAT_NAN se conserva como limitación.
3. **INVALID:** conservar las reglas del replay (artefactos >20% o FC fuera de 35–100 lpm; FINAL excluye además datos numéricos ausentes/no finitos). Son límites heredados, no nuevos umbrales validados por HG-04.
4. **FLAG:** conservar artefactos >15%, cola insuficiente (<75 s o <60 pares), CV de RR en cola >0,20, RMSSD de cola ausente y discrepancia absoluta cola/tramo >15%. La prioridad INVALID prevalece. No llamar a todos estos motivos “fallos técnicos”: la discrepancia describe heterogeneidad temporal y se retiene como cautela de uso.
5. **STAB_LAST2_MISMATCH:** mantener su efecto actual en esta versión. Los 30 días afectados presentan pendientes más fuertes, pero eso no identifica la causa ni demuestra inutilidad del registro. Retirar esta segunda protección sería otra política, sin replay equivalente disponible; no se incluye en el cierre mínimo. Tampoco se cambia su 15% para reproducir tasas históricas.
6. **Registros cortos:** conservar el comportamiento ya medido (fin útil anterior si no alcanza 375 s y controles actuales de cola); informar la duración real en Notes. No afirmar cobertura fija de 270 s en todos los días ni inventar ahora un nuevo mínimo total. Esta política admite segmentos de distinta duración en esos casos y esa limitación debe acompañar su futura implantación.
7. **Uso posterior:** conservar en esta fase la selección de días OK para roll-3 y referencias y las reglas actuales del semáforo. No modificar simultáneamente veto, zonas de incertidumbre o criterio de rojo. El nombre legible de NL será “sin penalización por latencia”, nunca “sin Calidad”.

**Alcance del cierre:** queda elegida una política concreta, reproducida y revisable, no una QA puramente técnica ni una validación fisiológica definitiva. La implantación conjunta con HG-03, los contratos y la migración histórica son una fase operativa distinta. No hace falta repetir los ensayos de bloques ni el replay NL para decidir esta selección. Confianza técnica subjetiva: 95% en las cifras verificadas; 85% en la conveniencia de esta selección conservadora; sin probabilidad asignada a superioridad fisiológica.

**Avance 2026-10-23 — inicio 90 s y auditoría de estabilización.** Se mantiene el inicio fijo a 90 s como candidato de trabajo, sin incorporarlo aún al CORE operativo. El [ensayo reproducible de bloques completos de 60/90/120 s](../../research/reports/hg04_estabilizacion_ventanas_2026-10-23.md) muestra que la duración del bloque cambia mucho una hipotética clasificación de deriva: en los mismos 489 días y con un corte exploratorio del 15 %, 172 cambian de clasificación entre al menos dos longitudes. Entre 395 días OK comunes, 161 cruzan ese corte con bloques de 90 s. Los 22 nuevos `LAT_NAN` no tienen una diferencia entre extremos mayor que los OK comunes en la mediana de 90 s. Estos resultados descartan adoptar sin validación una regla automática basada solo en comparar dos bloques. La copia sin penalización `LAT_NAN` conserva el RMSSD de las 506 filas, pero cambia 36 calidades y 38 semáforos: tampoco se adopta aún. Quedan pendientes la repetibilidad independiente y una referencia adecuada de calidad de señal. El protocolo habitual es supino y se intenta respirar espontáneamente; no se medirá ni anotará a diario el tiempo de reposo previo, que no es factible obtener. Esa ausencia limita las explicaciones causales, pero no es una tarea de captura pendiente ni cambia el análisis de los RR disponibles.

**Concordancia del H10 (paper 2026).** [Análisis de Blalock, Riemann y Flatt](../../research/reports/hg04_paper_h10_validez_2026-10-25.md): el RR interno del H10 concuerda con ECG de laboratorio en adultos jóvenes y segmentos limpios (RMSSD: sesgo −0,1 ms, LoA −1,3 a 1,1 ms, MAPE 0,8%). Es apoyo externo a esa fuente de RR, no validación de nuestro detector sobre ECG ni de todo el histórico Polar. Su protocolo mide un minuto después de otro de estabilización: hace plausible 90 s, no valida nuestro tramo completo. Desplazaron ventanas de un minuto para hallar segmentos sin ectópicos y aplicaron detrending antes de las métricas temporales; no compararon métodos de edición ni calcularon nuestros `SD2`/`SI_baevsky`. En nuestra serie, 399/440 días `OK` están bajo 55 lpm, zona donde puede aparecer saturación, pero el umbral no la diagnostica y las medianas por sextiles no la descartan en días individuales. RR medio y lnRMSSD tienen R² = 0,752 entre días; la utilidad incremental de FC para el gate queda sin medir. La correlación casi nula con 30:15 es entre participantes, no evidencia de utilidad para una rutina diaria individual.

**Contraste externo 2026-10-25.** [Comparación con librerías y productos de HRV abiertos](../../research/reports/hg04_contraste_practica_externa_2026-10-25.md): ΔRR>20% coincide numéricamente con HRV4Training; sus porcentajes de datos utilizables y nuestro `Artifact_pct` **no tienen la misma definición**, de modo que 15%/20% no quedan validados por analogía. Las herramientas consultadas usan ventanas elegidas por protocolo o usuario, sin precedente localizado del detector propio; ello respalda explorar inicio fijo, no demuestra superioridad fisiológica. Dos proyectos abiertos usan siete días de media, lo que sugiere una sensibilidad separada del gate frente a sus tres lecturas `OK` y el veto, no un estándar que adoptar. El CORE truncado retira 1162 intervalos en 489 días no `INVALID` (677 `offline`, 460 ΔRR, 25 fuera de rango). Los 29 supuestos «perdidos» carecen de clasificación reproducible; la precisión temporal del conversor y la cuantización entre eras no se han resuelto.

**Días decisivos de Calidad y semáforo (2026-10-25).** [Informe](../../research/reports/hg04_dias_decisivos_calidad_semaforo_2026-10-25.md) y [tabla filtrable](../../out/hg04_dias_decisivos_2026-10-25/dias_decisivos.xlsx) sobre la base HG-03 + 90 s + corte 375 s, comparando NL, NL sin `MISMATCH`, NL con veto ámbar y la combinada, sin recalcular CORE. 82 días decisivos de 506 (29 cambian `Calidad`, 61 el semáforo). Quitar `MISMATCH` recupera 29 días a `OK` y **deja los ROJO en 123**: redistribuye sin aflojar, endureciendo 14 días frente a 16 que afloja. El veto ámbar es la política más acotada: 30 días, todos `ROJO→ÁMBAR`, con regla `EXP_VETO_AMBAR_SIN_ROJO_ROLL3` identificada y verificada en los 75 ROJO con veto sin excepciones. Atribución 2×2 de la combinada: de sus 61 cambios de color, 30 son por quitar `MISMATCH`, 30 por el veto ámbar y 1 por interacción (2025-12-18); otros 21 días cambian solo de `Calidad`. Los 34 `ROJO→ÁMBAR` son 30 del veto, 3 de `MISMATCH` y 1 de interacción, y los 5 días que pasan a ROJO al quitar `MISMATCH` siguen ROJO en la combinada. El 2026-04-17 se explica paso a paso; el 2026-06-27 no es decisivo entre estas cuatro políticas porque todas ya quitan la penalización `LAT_NAN`, pero sí lo era frente al corte con esa penalización (VERDE → ÁMBAR). No se adopta ninguna regla ni se interpreta menos ROJO como mejor.

**Evidencia sobre `MISMATCH` y veto ámbar (2026-10-25; precisión 2026-10-26).** [Protocolo previo](../../research/reports/hg04_protocolo_mismatch_veto_2026-10-25.md), [informe](../../research/reports/hg04_evidencia_mismatch_veto_2026-10-25.md) y [tabla auditable](../../out/hg04_evidencia_mismatch_veto_2026-10-25/evidencia_por_dia.xlsx). **`STAB_LAST2_MISMATCH`: candidato prometedor, no demostrado.** 28 de los 29 días recuperados no presentan defecto técnico **detectable por los seis criterios preregistrados** [95%]. El histograma de `tail_mismatch_pct` no muestra una discontinuidad visible junto al 15%, pero eso **no valida ni invalida** la utilidad del umbral. La métrica compara el RMSSD de la cola con el del tramo completo: es una **alerta de discordancia**, no una prueba formal de estacionariedad. Ni estos controles ni la correlación RMSSD-FC distinguen fisiología de artefacto residual; esta última se retiró como evidencia de calidad. Solo 2 de los 13 días que pasan a VERDE tienen bienestar declarado, por lo que U3 sigue abierta. **No basta para recomendar quitar `MISMATCH` de `Calidad`** [40%]; si se quitara, desaparecería esta alerta de discordancia cola-tramo y habría que decidir qué vigilancia conservar. **Veto ámbar: evidencia insuficiente** [95%]. La regla rebajaría 30 de 75 días ROJO con veto; 4 de esos 30 tuvieron veto en la medición anterior, así que no todos son episodios aislados. Los ocho indicadores independientes disponibles no muestran una diferencia concluyente entre los 30 rebajados y los 45 mantenidos (p 0,31–1,00; valores altos no prueban equivalencia). La carga de la víspera se corrigió donde antes se usaba la medición anterior; la interacción del 2025-12-18 depende de 0,19 lpm en el umbral de FC del trío. No se adopta ninguna regla ni se modifica producción.

**[SUPERADO EN PARTE el mismo día — ver párrafo siguiente: se recuperó el ECG de 10 de los 29 y dejaron de ser no determinables.]** **Errores RR residuales frente a discordancia cola-tramo (2026-10-26).** [Protocolo previo](../../research/reports/hg04_protocolo_errores_rr_2026-10-26.md) sellado antes de ejecutar ninguna detección, [informe](../../research/reports/hg04_errores_rr_vs_discordancia_2026-10-26.md) y [tabla auditable](../../out/hg04_errores_rr_2026-10-26/errores_rr_por_dia.xlsx). Pregunta: de los 29 días recuperados, cuántos contienen errores RR residuales y cuántos discordancia sin error detectable. Respuesta: **los 29 son clase `N`, no determinable, porque ninguno tiene ECG original**; el ECG local cubre 8 días distintos y la intersección es vacía. De los 29, **11 serían auditables si se recupera el ECG de Dropbox** y **18 de era Polar no lo serán nunca**, al haber generado la app el RR sin ECG que contrastar. En las 9 grabaciones ECG utilizables de 14, el conversor comete **0 errores de latido dentro del tramo** sobre 2.057 latidos emparejados (Wilson 95%: 0–1,86/1.000): los 6 errores verificados mediante revisión **ciega** (etiquetas A/B aleatorias, veredicto sellado antes de desenmascarar; 10 `EXTRA`, 3 `FALTA`, 0 ambiguos) caen **todos antes de los 90 s**, en el transitorio de arranque del amplificador, de modo que el inicio fijo a 90 s descarta por sí solo la zona donde el conversor falla [85%]. La corrección trazable no mueve `tail_mismatch_pct` en ninguna de las nueve (Δ = 0,00). La simulación de un único error insertado muestra que el indicador es **muy sensible y nada específico**: un solo latido omitido convierte un día limpio en marcado en el **99,5%** de las posiciones fuera de la cola [95%]. Dos días alcanzan 12–14% con el tramo verificado limpio [80%], y el 2026-07-10 varía **12 puntos** de indicador entre dos registros de la misma mañana con el RMSSD del día casi idéntico (46,35 frente a 46,02 ms) [60%], lo que abre una tercera lectura no considerada antes: parte de `tail_mismatch_pct` puede ser variabilidad del propio estimador, en cuyo caso no procedería ni quitar ni conservar la regla, sino sustituirla por un indicador con repetibilidad medida. **La decisión sobre `STAB_LAST2_MISMATCH` sigue abierta** [90%], lo que es coherente con conservarla en esta versión según la decisión de diseño de §Decisión y el punto 5 del cierre mínimo. **Ninguno de los 30 cambios de semáforo es reevaluable hoy**; con el ECG recuperado lo serían los 5 cuyo cambio nace de la `Calidad` propia de un día de era ECG. La geometría del análisis reproduce la copia `H3S90T375` en **503 de 503 días con diferencia máxima 0,000000**, tras corregir el filtro ΔRR con pares HG-03 y, sobre todo, conservar el eje de tiempos original al filtrar. El protocolo lleva una **corrección visible**: su «caso marcado» se eligió con valores del CORE de producción y, bajo la base declarada, no existe ningún día con ECG que lleve `STAB_LAST2_MISMATCH`, por lo que el corte del 15% no ha podido contrastarse contra errores verificados. El veto ámbar queda fuera de alcance hasta disponer de un criterio externo de utilidad.


**Ampliación tras recuperar el ECG de 10 días (2026-10-26, misma tarde).** [Protocolo](../../research/reports/hg04_protocolo_errores_rr_2026-10-26.md) con **enmienda §12** registrada antes de ejecutar nada sobre el material nuevo, [informe](../../research/reports/hg04_errores_rr_ampliacion_10dias_2026-10-26.md) y [tabla auditable](../../out/hg04_errores_rr_2026-10-26/ampliacion_10dias/errores_rr_29dias_actualizado.xlsx). Aparecieron en `data/rr_downloads/_source_jsonl_recovered/` las grabaciones originales de **10 de los 11 días de era ECG** entre los 29, todas a 130,1 Hz y de 501 a 545 s, cubriendo el tramo. Antes se revisaron sin resultado los 17 `.zip` mensuales (481 ficheros, todos CSV de RR) y las carpetas de paso, vacías. La clasificación pasa a **10 clase `D` (discordancia cola-tramo sin error de detección), 0 clase `E`, 19 clase `N`** (18 de era Polar, ahora limitación **definitiva** y no de búsqueda, más 2026-03-06 sin ECG). **no se halló ningún error del conversor entre las 30 discrepancias revisadas** [90%]; el denominador contrastado dentro del tramo es de **2.407 latidos** (Wilson 95%: hasta 1,593/1.000). Los 4.361 latidos concordantes **no se inspeccionaron uno a uno**, y ese límite acota solo la clase de error que el método ve —discrepancia entre dos detectores mayor de 60 ms—, no errores compartidos, desvíos de instante bajo 60 ms ni ectópicos; los 15 errores de la revisión **ciega** (13 `EXTRA`, 2 `FALTA`, 15 ambiguos; etiqueta A al conversor en 13 de 30 casos; veredicto sellado antes de desenmascarar) son **todos del detector independiente**, y los 2 únicos dentro del tramo son latidos que el conversor **sí** detectó y la referencia se saltó. Los 15 ambiguos son del 2026-03-31 y caen entre 0,02 y 7,59 s, fuera del tramo. La corrección trazable mueve `tail_mismatch_pct` **0,00 puntos en los diez**. El corte del 15% tiene por tanto **VPP de 0,0% para errores de detección** (0 de 10 días marcados con ECG; Wilson 95%: 0–27,8%): **no se observó ninguno** entre los días marcados auditables; no se concluye «poco específico», porque el intervalo admite hasta un 27,8%, y la respuesta de la fórmula a errores insertados en simulación es una propiedad algebraica del estimador, no una estimación de sensibilidad sobre mediciones reales. Dos controles nuevos reorientan la pregunta: la dirección es **sistemática** (la cola tiene menos RMSSD que el tramo en 73% de los 503 días, y en **94,3%** de los 35 marcados), y sobre todo **la discordancia no está en la cola**: en los días marcados **todas** las ventanas contiguas de 120 s discrepan del tramo entre **9 y 17%**, frente a **1,6 a 9,3%** en días control, [90%]. **Lo que ese control no puede decir** es si la cola es *además* especialmente discordante: los días se seleccionaron precisamente por la discordancia de esa cola, de modo que el 7 de 10 en el decil superior está garantizado por el diseño y no es evidencia en ninguna dirección. El rango «9 a 17%» es el de las **medianas por día**, no el de ventanas individuales (hay colas de 31,41%). Es decir, esos días tienen el RMSSD **inestable en todo el registro**, y `tail_mismatch_pct` es una estimación de un solo tiro de esa inestabilidad en una ventana arbitraria, lo que explica la mala repetibilidad ya observada. **Clase `D` no significa señal limpia**: esta auditoría no ve ectópicos —un solo ectópico eleva el RMSSD un 413% según Bourdillon— ni desvíos por debajo de 60 ms, y 3 de los 10 tienen `artefactos_pct` del orden o por encima del 0,9% en que Bourdillon observa, **en su cohorte y con su protocolo**, que el error de RMSSD excede una desviación típica poblacional, lo que los señala como los días que más atención merecen sin diagnosticar que su RMSSD sea incorrecto. Que el origen **no** sea el conversor **no asciende la hipótesis fisiológica** [40%]. **La decisión sobre `STAB_LAST2_MISMATCH` sigue abierta** [90%], pero por un motivo nuevo: ya no es que se ignore si marca errores —sabemos que no los marca— sino que mide algo real de forma pobre, lo que abre una tercera vía antes no planteada: **sustituirlo** por la mediana de la discordancia sobre todas las ventanas de 120 s, que usa todo el registro. No se recomienda ninguna opción sin criterio externo de utilidad. **4 de los 30 cambios de semáforo pasan a reevaluables** (2026-03-31 y 2026-09-18 ÁMBAR→VERDE; 2026-05-18 y 2026-07-07 VERDE→ÁMBAR): en los cuatro no se halló error de detección del conversor, lo que no prueba que el veto no corrija ningún error —quedan fuera los compartidos, los desvíos bajo 60 ms y los ectópicos— ni determina si el color resultante es el correcto. Los otros 26 no lo son (4 sin ECG, 22 por arrastre del trío o las referencias). El veto ámbar sigue fuera de alcance. No se modifica producción, contratos ni datos originales.
## Estado vigente tras revisión — 2026-10-21

> Revisión crítica posterior: [[HG-03 HG-04 Revision critica Claude 2026-10-21]] (errores en §13.5 y en «diferencias en ambos sentidos», §7 desfasado, propuesta de criterio de decisión).

**No hay una ventana aprobada. Los inicios de 180 y 210 s dejan de ser opciones prioritarias de adopción.** No existe evidencia bibliográfica directa que exija esperar tanto, y el análisis local tampoco ha demostrado que mejoren la validez o la utilidad longitudinal. Pueden conservarse únicamente como comparaciones de sensibilidad del replay para cuantificar qué cambia al recortar tarde; no compiten en igualdad de condiciones por la nueva regla. Tampoco quedan automáticamente aprobados 0, 60, 90 o 120 s: deben evaluarse con QC por ventana, cohortes comunes y un criterio longitudinal predefinido. Las prescripciones de §5, §8, §9 y §11 y las preferencias posteriores se conservan como historial de la investigación; quedan subordinadas a esta revisión y no constituyen instrucciones de implementación.

- El descenso observado de RMSSD dentro del registro no demuestra que el valor final sea más válido. La comparación con los últimos 120 s mide una diferencia temporal, no un sesgo frente a un patrón fisiológico validado. No se ha establecido su causa ni que un recorte elimine un transitorio.
- La regla de §14.7 selecciona 210 s bajo umbrales exploratorios y una referencia tardía elegida por el estudio. No valida ese inicio: cambia la muestra Polar y los intervalos no demuestran equivalencia dentro de ±0,03. Los porcentajes anteriores de confianza en una ventana concreta quedan retirados; eran juicios subjetivos, no probabilidades calibradas.
- El replay demuestra sensibilidad del gate a la definición de ventana, no mayor exactitud. Las diferencias de recuentos frente a C no son una descomposición causal (§14.2). La verificación posterior confirmó excepciones a la paridad completa con producción (§14.1).
- La variante E mantiene el detector y su uso en `Calidad`; solo deja de utilizar su latencia para escoger el inicio. Ya se compararon en sombra inicios 0/60/90/120 s solos y con HG-03 (§14.10). Falta definir y validar la regla de calidad que acompañaría a una nueva ventana.
- El 15% de `STAB_LAST2_MISMATCH` permanece vigente en producción. Una tasa parecida de flags no valida su sensibilidad en otra geometría, y ajustar el umbral para recuperar una tasa histórica tampoco la valida.

**Siguiente trabajo necesario:** las excepciones del control se aceptan solo para comparar brazos, no para publicar el histórico; usar el replay de inicios tempranos y registros cortos (§14.10) para definir una QA y una política de ventana insuficiente, y fijar un criterio longitudinal externo antes de proponer cambios contractuales. Para interpretar los resultados, se consideran condiciones habituales del protocolo la postura supina y el intento de respiración espontánea. El tiempo de reposo previo no se registra ni se imputará; se tratará como limitación al atribuir causas, no como requisito de captura. Sueño, carga o rendimiento aportarían validación contextual, no un patrón oro automático de HRV.

**Confianza en las correcciones metodológicas: 95%**, juicio técnico no calibrado. No se asigna una probabilidad de corrección fisiológica a 180/210 s con estos datos. La tarjeta HG-04 se ha actualizado mediante el CLI de Kanvas con este alcance; permanece en curso porque la validación y la implementación operativa siguen pendientes.

**Revisión bibliográfica 2026-10-21:** las respuestas de Consensus, Elicit, Perplexity y SciSpace se contrastaron con estudios originales en [la síntesis crítica de HG-04](../../research/reports/hg04/sintesis_critica_2026-10-21.md). Se confirma que el criterio tardío no es un patrón fisiológico independiente. Se corrige además la comparación de porcentajes de artefactos de §9.3: el 5% del estudio de Muñoz y `Artifact_pct` no miden lo mismo. Ninguna propuesta de los buscadores altera por sí sola la ventana o los umbrales de QA vigentes.

**Rectificación de prioridad 2026-10-21:** la formulación anterior «mantener 180 y 210 como candidatos» otorgaba un peso injustificado a esos recortes. Se mantienen solo como controles de sensibilidad; la hipótesis de adoptarlos requeriría evidencia local nueva, reproducible y definida con independencia de la concordancia con el final del registro.

**Alcance reflejado en la tarjeta HG-04:** investigar la definición de ventana de RMSSD_stable y su relación con estabilización y QA. Priorizar la evaluación de inicios 0/60/90/120 s en cohortes comunes y con QC por ventana, sin aprobar aún ninguno. Mantener 180/210 s solo como comparaciones secundarias de sensibilidad y sin suponer válida la referencia final. Resolver las excepciones de paridad del control, registros cortos y sensibilidad de STAB_LAST2_MISMATCH. El contexto conocido del protocolo es supino con respiración espontánea intentada; el reposo previo no se medirá por día y queda como limitación. Evaluar el diseño combinado con HG-03 y una regla de calidad explícita antes de actualizar contratos y recalcular el histórico. Correcciones de revisión realizadas en documento y scripts; implementación operativa pendiente. Nota: [[HG-04 Ventana de calculo de RMSSD_stable y revision de estabilizacion]].

Alcance: `RMSSD_stable`, `Tiempo_Estabilizacion`, `RMSSD_stable_last2` y el flag `STAB_LAST2_MISMATCH`. Es un cambio de **definición de ventana**, no una corrección de bug, y por tanto exige recálculo del histórico (ver sección 6). Relacionada con [[RR_PARES_CONSECUTIVOS_TAREA]] (HG-03): comparten el mismo recálculo y deben cortar juntas.

Base empírica: 497 grabaciones reprocesadas desde `data/rr_downloads` (454 de los zips `Franz_Dunn_*_RR.zip`, origen Polar; 43 CSV sueltos de origen `from_jsonl`), rango 2025-05-12 → 2026-10-17. Todas las cifras de este documento salen de ese reproceso contrafactual, no de los CSV operativos.

> **CORRECCIÓN 2026-10-20:** la etiqueta «zips = origen Polar» es falsa. Los zips de 2026-03 a 2026-09 contienen ficheros `*_from_jsonl_RR.CSV` (202 de 483 fechas comprimidas); los nombres de origen Polar son 281. Toda comparación por origen de este documento (en particular la tabla de §6) mezcla días ECG en el grupo «Polar» y se ha recalculado en §6 clasificando por nombre de fichero interno; la era ECG empieza el 2026-03-06. Las cifras que no separan por origen no se ven afectadas.

---

## 1. Problema

`RMSSD_stable` se calcula sobre el tramo que va desde `t_start_eff` hasta `t_end_eff` (`build_hrv_core.py:387,390,395`). `t_start_eff` lo decide un detector de latencia, y `t_end_eff` depende de la duración de la grabación. El resultado es que **la cantidad de latidos que entra en el cálculo varía enormemente entre días**, y con ella la precisión del valor.

Longitud del tramo estable medida sobre las 497 grabaciones:

| | segundos |
|---|---|
| mínimo | 65 |
| p5 | 122 |
| p25 | 257 |
| mediana | 332 |
| p75 | 416 |
| máximo | 531 |

Rango de **8,2×**. 55 días (11%) tienen un tramo menor de 180 s; 21 días lo tienen menor de 120 s.

La longitud puede afectar a la precisión del estimador. Aquí se midió la dispersión de `lnRMSSD` entre ventanas distintas **de la misma grabación**. Corrección 2026-10-21: la fisiología puede variar durante esa grabación; esta dispersión no aísla el ruido instrumental ni el error del estimador:

| Longitud de ventana | SD de lnRMSSD (mediana de 497 días) |
|---|---|
| 75 s | **0,114** |
| 120 s | **0,082** |
| 240 s | **0,039** |

Es decir: el ruido de medida de `lnRMSSD` varía por un factor ~3 entre días, y lo determina el detector de latencia, no el estado del atleta. El baseline (`base60_days = 60`, `adaptive_window_days = 90` en `build_hrv_final_dashboard.py:83,104`) y el gate tratan todos los días como igual de precisos.

Para calibrar la magnitud: el efecto de HG-03 sobre los días de origen ECG es de 0,041 como máximo en lnRMSSD. La heterogeneidad de ventana produce diferencias de 0,04 a 0,11 de forma rutinaria.

---

## 2. El detector de estabilización está mal construido

Cuatro defectos, los cuatro medidos.

### 2.1 Las ventanas se solapan al 50% y eso infla la estabilidad aparente

El detector usa ventanas de 60 s con paso de 30 s (`:348–359`): cada ventana comparte la mitad de sus latidos con la siguiente, así que la comparación está mecánicamente correlacionada.

| | Diferencia relativa mediana entre adyacentes | % de pares que pasan el filtro `<8%` |
|---|---|---|
| Ventanas solapadas (código actual) | 7,5% | **52%** |
| Ventanas contiguas sin solape | 12,0% | **35%** |

El solape hace el criterio ~1,5× más fácil de cumplir. Parte de lo que el detector mide es su propio solape.

### 2.2 El umbral del 8% está por debajo del ruido del estimador

La SD de `lnRMSSD` entre ventanas de 60 s de la misma medición es del orden de 0,11–0,16. El umbral `LAT_REL_EPS = 0.08` equivale a 0,077 en ln: el criterio exige que dos estimaciones consecutivas coincidan dentro de **menos de una desviación típica del propio ruido del estimador**. No es un test de estabilidad fisiológica; es esperar a que el ruido se alinee.

### 2.3 `rel(a, b) = |b − a| / a` es asimétrica

Divide por la ventana anterior (`:364–367`). Si el RMSSD sube, la base es la menor y la diferencia relativa sale mayor (más difícil pasar); si baja, al revés. El criterio detecta «estabilización» más fácilmente en descenso que en ascenso, y el perfil real desciende (sección 3), así que el sesgo opera en la dirección activa.

### 2.4 El fallback usa información del futuro y define el nivel estable de forma circular

El criterio secundario (`:374–386`) toma como `target` la mediana de las 4 últimas ventanas válidas y busca el primer momento que se le parece. Usa el final de la grabación para decidir el principio. Dispara en 7 de 497 días (1,4%) — poco, pero cuando dispara `Tiempo_Estabilizacion` significa algo distinto que en los otros 490 días, y nada en CORE registra cuál de los dos criterios decidió.

Reparto real: criterio primario 464/497, fallback 7/497, ninguno (lat = NaN → `t_start_eff = 45`) 26/497.

### 2.5 Inconsistencia menor

`t_start_eff = max(lat, 45)` (`:387`) pero la condición de `Calidad` usa `Lat_eff = max(lat, 60)` (`:439`). Dos suelos distintos para la misma magnitud.

---

## 3. La estabilización sí existe: el transitorio es real pero no hay nada que detectar

Perfil medio de las 497 grabaciones, alineado al inicio, con referencia en el nivel mediano de los minutos 4–7:

| Minuto | lnRMSSD vs referencia | IQR | Días por encima |
|---|---|---|---|
| 0–1 | **+0,213** (+24%) | +0,075 .. +0,335 | **412/488 (84%)** |
| 1–2 | +0,142 | +0,035 .. +0,253 | 399/488 (82%) |
| 2–3 | +0,065 | −0,031 .. +0,163 | 331/488 (68%) |
| 3–4 | +0,013 | −0,020 .. +0,092 | 281/490 (57%) |
| 4–5 | +0,000 | −0,049 .. +0,059 | 234/490 (48%) |
| 5–8 | −0,004 a −0,024 | — | ~40% |

Conclusión doble:

1. **Recortar el principio está justificado.** El primer minuto tiene un RMSSD ~24% más alto en el 84% de los días. Es un transitorio de asentamiento real, no ruido.
2. **Pero es la misma curva todos los días.** Decae de forma suave y monótona y está resuelto en el minuto 4 (al minuto 4–5 la proporción de días por encima es 48%, indistinguible del azar). No hay un evento específico de cada día que haya que localizar, y por tanto un detector adaptativo no tiene nada que aportar.

Comprobación directa de que no aporta: comparado con un recorte fijo, el detector da el mismo resultado en el día típico (mediana |Δ lnRMSSD| = 0,015 frente a recorte fijo de 60 s y frente a 120 s). Donde difiere, difiere en una cantidad del orden del ruido del estimador: no añade información, añade varianza.

Sesgo residual según el recorte fijo que se aplique (referencia: ventana desde 240 s):

| Recorte | Sesgo mediano | Dispersión entre días (SD) |
|---|---|---|
| 45 s (suelo actual) | +5,3% | 0,069 |
| 60 s | +4,5% | 0,066 |
| 90 s | +3,3% | 0,060 |
| **120 s** | **+2,4%** | **0,055** |
| 180 s | +0,9% | 0,041 |

---

## 4. `STAB_LAST2_MISMATCH`: el umbral es defendible, la base de comparación no

`HRV_Stability` se marca `Unstable` cuando `|RMSSD_last2 − RMSSD| / RMSSD > 0.15` (`:426`). Medido sobre las 497 grabaciones: dispararía en **37 días (7%)**, con mismatch mediano 4,9% y p90 13,9%.

La SD de `lnRMSSD` para una ventana de 120 s es 0,082 (≈8,5%), así que el umbral del 15% está en torno a 1,8 SD del ruido del estimador. **Es un umbral razonable** — una estimación preliminar sobre una muestra de 43 días sugería lo contrario (21% de disparos) y era un artefacto de muestra pequeña; queda descartada.

El defecto real es otro: `RMSSD_last2` (120 s fijos) se compara contra `RMSSD_stable`, cuya ventana varía entre 65 y 531 s. Dos cosas:

- La comparación mezcla un estimador de ruido 0,082 con otro cuyo ruido va de 0,039 a 0,12 según el día, así que el significado del 15% cambia de día en día.
- En los días de tramo corto, la cola de 120 s es una fracción grande del propio tramo (en 21 días el tramo es menor de 120 s, o sea que la cola **es** casi todo el tramo y el flag se compara consigo mismo).

Con una ventana de cálculo fija, la cola pasa a ser un subconjunto anidado y de proporción constante del tramo, y el 15% recupera un significado estable. **No hay que tocar el umbral; hay que homogeneizar la base.**

> **[Corregido 2026-10-20, revisión externa — §13]** Falso tal como está escrito. Con la cola anidada `[240, 360]` dentro de `[180, 360]`, ambas estimaciones comparten 2/3 de los datos y la tasa de disparo baja de ~7% a ~1,3% (§13.2). El 15% no conserva su comportamiento en la nueva geometría; su ajuste queda abierto.

---

## 5. Trabajo propuesto

Cambio mínimo, y resulta en **menos** código que ahora.

1. **Sustituir el detector de latencia por un recorte fijo de 180 s.** Eliminar el bucle de ventanas (`:348–359`), el criterio primario (`:368–372`) y el fallback (`:374–386`). `t_start_eff = 180.0`.

   Justificación: la caracterización n=1 (sección 10.1) sitúa el final del transitorio de este atleta entre 180 y 240 s, no entre 60 y 120. A 120 s solo el 44% de sus días están dentro de ±10% de su nivel estable, por debajo del suelo de ruido del estimador (~54%); a 180 s, el 51%. La literatura (sección 9) da 60 s para deportistas de resistencia jóvenes y 90 s para estudiantes [6], con ~2 min recomendados para población de más edad o menor actividad vagal: los 180 s quedan por encima de todos esos umbrales, y es su propio transitorio el que los exige.

2. **Calcular `RMSSD_stable` sobre una ventana fija anclada al inicio: `[180, 360]` s.** No «los últimos N s»: anclar al final hace que el recorte efectivo dependa de la duración del registro (141 s en 2025, 255 s en 2026) y reintroduce la heterogeneidad que esta tarea elimina. Con `[180, 360]` la geometría de medición es idéntica todos los días, sea el registro de 380 o de 540 s. Exige `t_end_eff ≥ 360`; si no, calcular con lo disponible y marcarlo (punto 4).

   Viabilidad medida de la combinación adoptada (recorte 180 s + ventana 180 s, es decir `t_end_eff ≥ 360`): **486/497 días (97,8%)**, de los cuales 212/222 en 2025 y 274/275 en 2026, y **85/86 del periodo `healthy`**. Los 11 no viables son grabaciones de menos de 375 s, concentradas en 2025-05 y 2025-06.

   Por qué 180 s de ventana y no 240 (detalle en sección 11):

   | Recorte | Ventana | Viabilidad total | 2025 | 2026 | Periodo `healthy` | SD de lnRMSSD |
   |---|---|---|---|---|---|---|
   | 180 s | 240 s | 335/497 | 61/222 | 274/275 | **3/86** | 0,039 |
   | **180 s** | **180 s** | **486/497** | **212/222** | **274/275** | **85/86** | **0,060** |
   | 120 s | 240 s | 486/497 | 212/222 | 274/275 | 85/86 | 0,039 |

   La ventana de 240 s exigiría recortar antes de los 180 s o renunciar a 2025, y **ninguna de las dos es aceptable** (sección 11): el recorte temprano deja transitorio residual, y 2025 contiene el ancla `healthy` del gate. Con recorte de 180 s, la ventana máxima compatible con todo el histórico es 180 s, y el coste en precisión es irrelevante: el ruido de ventana pasa de 0,039 a 0,060, que sobre una variabilidad día-a-día real de 0,207 supone una SD total de 0,2118 frente a 0,2068 — un 2,4% peor. El beneficio de esta tarea nunca fue llevar el ruido a su suelo, sino **homogeneizarlo**: que deje de variar entre 0,039 y 0,12 según el día.

3. **Conservar `Tiempo_Estabilizacion` como diagnóstico descriptivo, no como decisor.** Dos opciones, a decidir: (a) dejar de calcularlo y poner `NaN`, simplificando el contrato; (b) calcularlo con un estimador honesto (ventanas contiguas sin solape, umbral explícito en unidades de SD del estimador) y reportarlo sin que afecte al cálculo. La opción (b) tiene valor si se quiere seguir vigilando el transitorio; la (a) es más limpia. Si se elige (a), revisar la condición `60 <= Lat_eff <= 600` de `Calidad` (`:439`), que dejaría de tener entrada.

4. **Añadir una columna de precisión de la medición** a CORE: longitud efectiva de la ventana usada y un flag booleano de ventana insuficiente (`< 180 s`). Es información que hoy no existe en ninguna parte y es lo que permite al gate y al baseline distinguir un día medido con la ventana completa de uno medido con 90 s. ~~Aditiva, no rompe esquema.~~ **[Corregido 2026-10-20, revisión externa — §13]** Sí rompe esquema: el lector de CORE rechaza columnas no canónicas (`build_hrv_core.py:726–731`). Exige migración explícita y actualización de contrato y consumidores. Además, la longitud nominal no garantiza igual precisión: cuentan también los pares válidos y los huecos dentro de la ventana.

5. **Redefinir la cola como sub-ventana anidada: `[240, 360]` s** — los últimos 120 s de la ventana de medición, no los últimos 120 s del registro. Así la cola es siempre un subconjunto de proporción constante del tramo, con geometría idéntica cada día, y el umbral del 15% de `STAB_LAST2_MISMATCH` recupera un significado estable sin necesidad de cambiarlo. Todo el cálculo canónico queda contenido en `[180, 360]` s, que existe en 486/497 registros. ~~Verificar tras el cambio que la tasa de disparo se mantiene en el entorno del 7%.~~ **[Corregido 2026-10-20, revisión externa — §13]** Ya medido: no se mantiene (1,26% en días no `INVALID`, §13.2).

6. **Aplicar el mismo criterio en la ruta de rescate** `compute_day_from_rr_core_only()` (`:660,663,667,672–676`), que hoy fija `t_start_eff = 45.0`. Las dos rutas deben compartir la regla.

7. **Pruebas numéricas**: grabación de duración nominal (ventana exacta `[180, 360]`), grabación corta (flag de ventana insuficiente), grabación con `t_end_eff` justo en 360 s y justo por debajo, paridad de la ruta de rescate, y comprobación de que la cola `[240, 360]` queda contenida en la ventana de medición.

8. **Actualizar `docs/contracts/ENDURANCE_HRV_Spec_Tecnica.md`** (secciones 4.2, 4.3 y 4.4) antes de activar: nueva definición de ventana, recorte fijo, columna de precisión, y el estado de `Tiempo_Estabilizacion` según la opción elegida en el punto 3.

### Lo que no se toca

La fórmula de RMSSD (`:162–168`) es correcta: `sqrt(mean(Δ²))·1000`, sin `ddof`, conforme a Task Force 1996. `winsor` solo se aplica a la regresión beta (`:483–484`), no contamina RMSSD. El filtro de artefactos tampoco se toca: probar umbral 0,25 en vez de 0,20, o un filtro por mediana local de 5 en vez de latido previo, cambia el RMSSD en ratios de 0,9986 a 1,0000 — no hay retorno en rediseñarlo.

---

## 6. Recálculo del histórico

Este es un cambio de definición, no una corrección: si se aplica solo hacia delante, la serie mezcla dos definiciones con un escalón de nivel del 2–3% y el baseline compara el día de hoy contra una referencia construida con otra regla. **Hay que recalcular.**

Y se puede: `data/rr_downloads` contiene los RR del histórico completo, incluidos los de origen Polar, en los 16 zips `Franz_Dunn_*_RR.zip` (457 fechas, 2025-05-12 → 2026-08-31) más 43 CSV sueltos de 2026-09/10. *(Estado a 2026-10-20: 17 zips con 483 fechas hasta 2026-09-30 más 19 CSV sueltos de 2026-10; 502 fechas.)* Cobertura: **499 de las 502 filas de CORE (99,4%)**. Las tres sin RR son `2026-02-26`, `2026-02-27` y `2026-03-03`.

Esto invalida la lectura que `AGENTS.md:41` («el historico de CORE generado anteriormente con RR de Polar se conserva sin migracion retroactiva») podría sugerir como impedimento: la regla existe porque la **fuente** de RR cambió con AYO-13-F4 (Polar → ECG/ACC derivado de Dropbox), no porque el material sea irrecuperable. Para un cambio de definición de ventana, que se aplica igual a cualquier serie RR, el recálculo completo es posible y es lo correcto. **Ese punto de `AGENTS.md` debe revisarse o matizarse como parte de esta tarea**, distinguiendo «no re-derivar RR desde otra fuente» de «no recalcular métricas desde los RR archivados».

Interacción crítica con HG-03: el efecto del pareado incorrecto es mucho mayor en el histórico Polar que en los días recientes de origen ECG.

> **Tabla original errónea (2026-10-20):** el grupo «Polar (zip)» incluye 202 días de origen ECG. Recálculo debajo.

| Origen | n | Descartes/día (media) | Máx | % días que cambian | p95 \|Δ lnRMSSD\| | Máx |
|---|---|---|---|---|---|---|
| ECG/jsonl | 43 | 0,9 | 7 | 9% | 0,015 | 0,041 |
| Polar (zip) | 454 | 3,8 | **364** | 13% | 0,042 | **1,719** |

> **Recálculo 2026-10-20 con origen correcto** (`research/scripts/hg03_effect_by_true_origin.py`; origen por nombre de fichero interno; tramo del detector vigente; 502 fechas):
>
> | Origen | n | Descartes/día (media) | Máx | % días que cambian | p95 \|Δ lnRMSSD\| | Máx |
> |---|---|---|---|---|---|---|
> | ECG (2026-03-06 → 2026-10-20) | 221 | **16,4** | 341 | **20%** | 0,026 | **1,436** (2026-05-09) |
> | Polar (2025-05-12 → 2026-03-03) | 281 | 4,9 | 397 | 11% | 0,033 | 1,606 (2025-06-25) |
>
> **La conclusión anterior se invierte:** la era ECG tiene más descartes por día (28 días con >20 descartes frente a 5 en Polar) y más días afectados; los extremos son de magnitud similar en ambas eras. Todos los días con |Δ| > 0,2 son ya `INVALID`. Fuera de `INVALID`, el mayor efecto es 2025-09-11 (Polar, `FLAG_mecánico`, Δ = 0,483) y 2025-08-06 (0,158), ambos dentro del periodo `healthy`; en días `OK` el máximo es 0,080 (2025-09-03). **No verificado:** si los días `FLAG_mecánico` entran al cálculo de `healthy_rmssd`. ~~Discrepancia sin resolver: para 2026-01-12 este recálculo da 397 descartes y 330,5 → 90,7 ms, frente a 364 y 359,6 → 64,5 ms de la tabla original; la causa no está identificada.~~

> **Corrección 2026-10-21 (verificada con el RR de 2026-01-12):** las cuatro cifras se reproducen con dos decisiones independientes. Con inicio fijo a 360 s, RMSSD es 330,5 ms con pares contiguos entre RR retenidos y 90,7 ms con pares físicamente consecutivos; con inicio a 45 s, es 359,6 y 64,5 ms, respectivamente. Al aplicar HG-03 también al detector, este deja de hallar estabilización (`Tiempo_Estabilizacion: 360 → NaN`) y se aplica el inicio de respaldo de 45 s. Los 364 descartes de la tabla antigua son solo por dRR; 397 suma todos los motivos de descarte (`N_off + N_oor + N_drr`). Este día es `INVALID` en ambos replays.

Hay 11 días con más de 20 latidos descartados, todos de origen Polar. El extremo es `2026-01-12`: 364 de 607 latidos descartados, RMSSD 359,6 ms con el cálculo actual frente a 64,5 ms con pareado correcto. Esos días deberían estar clasificados `INVALID` por `artifact_pct > 20`, lo que hay que verificar explícitamente en el recálculo — si alguno entró como `OK` o `FLAG_mecánico` a un baseline, lo contaminó de forma grave.

Conclusión operativa: **HG-03 y HG-04 requieren exactamente el mismo recálculo y deben activarse en un único corte.** Por separado serían dos reprocesos, dos periodos de shadow y dos escalones de nivel en la serie.

### Procedimiento de recálculo

1. Copia aislada del dataset. `--all` reprocesa solo los RR ya presentes en disco (`AGENTS.md:123`) pero escribe sobre el CORE de producción: no ejecutarlo contra `data/` hasta haber validado.
2. Descomprimir los zips a un directorio de trabajo temporal (`add_ans_balance_to_core.py` ya importa `zipfile` y es referencia de cómo se leen).
3. Reproceso completo con pareado HG-03 + ventana HG-04. Comparar fila a fila contra el CORE actual: `RMSSD_stable`, `lnRMSSD`, `HR_stable`, `SD1/SD2`, `Tiempo_Estabilizacion`, `HRV_Stability`, `Calidad`, y los derivados en FINAL, DASHBOARD, baselines, gate y acción.

   **Método de comparación obligatorio**: no basta con «no hay diferencias significativas» ni con una correlación alta. Pecchia y Castaldo 2018 [4] revisaron 29 estudios de HRV ultra-corta y solo uno usaba un método válido; el resto concluía equivalencia a partir de correlaciones o de `p > 0,05`, que es inválido. La secuencia exigible es: (1) correlación, (2) **Bland–Altman** para detectar sesgo y límites de concordancia, y (3) **d de Cohen sobre los valores log-transformados**. Esto invalida explícitamente el razonamiento del paso 5 de la nota de HG-03 («la simulación aislada no cambió gate ni acción»): ausencia de cambio detectado no es equivalencia demostrada.
4. Registrar fechas y magnitudes que cambian, con atención a los días que cambian de `Calidad` (entran o salen de la elegibilidad de baseline).
5. Marca de versión de cálculo por fila, obligatoria: es lo que distingue el bloque recalculado y permite auditar la transición.
6. Solo entonces aplicar sobre producción, con backup previo.

### Riesgo a vigilar

`scripts/python/add_ans_balance_to_core.py` reescribe `CORE.csv` (`:411`) con lógica duplicada de pipeline (su propio `poincare_sd` en `:77–86`, su propio filtro delta-RR en `:141`, su propio `np.diff` en `:169`). Si se ejecuta después del cambio, reintroduce el cálculo antiguo sobre el CORE recalculado. **Neutralizarlo (marcar deprecated o alinearlo) antes de cualquier otra cosa.**

---

## 7. Criterio de cierre

> **[Superado 2026-10-21 — ver [[HG-03 HG-04 Revision critica Claude 2026-10-21]] §5]** La lista siguiente se escribió para la ventana `[180,360]` con cola anidada, que el «Estado vigente» ya no aprueba, y no figuraba entre las secciones declaradas históricas. Se conserva como historial. Criterio de cierre vigente, neutro respecto a la geometría:
>
> 1. Regla de inicio y fin de `RMSSD_stable` elegida con un criterio de decisión explícito y documentado antes de aplicarlo.
> 2. Ningún camino en que el detector de latencia determine qué latidos entran en una métrica canónica.
> 3. Política explícita para ventanas insuficientes (registros cortos), sin degradación silenciosa.
> 4. QA coherente con la geometría elegida, incluida la sensibilidad de `STAB_LAST2_MISMATCH`; el 15% no se ajusta para reproducir una tasa histórica.
> 5. Las dos rutas de CORE (completa y rescate) comparten la misma regla.
> 6. Contrato actualizado y, si se añaden columnas, migración explícita del esquema (`build_hrv_core.py:726–731`).
> 7. Histórico recalculado desde los RR archivados en copia aislada, con versión, Bland–Altman y d de Cohen sobre logs, y efectos en QA, baselines, gate y acción documentados; corte conjunto con HG-03.
> 8. `add_ans_balance_to_core.py` no puede reintroducir el cálculo antiguo (hecho) y `AGENTS.md:41` matizado.
> 9. Coordinación con HG-05/HG-06/HG-07 según HG-05 §9 *(movida el 2026-10-27 a [Secuencia de tareas HG](<HG Secuencia de tareas HRV.md>))*.

- `RMSSD_stable` se calcula sobre una ventana de longitud fija en todos los días en que hay material; los días que no lo permiten están marcados explícitamente, no silenciosamente degradados.
- No queda ningún camino en que el detector de latencia determine qué latidos entran en una métrica canónica.
- Las dos rutas de CORE (completa y rescate) comparten la misma regla de ventana.
- `RMSSD_stable_last2` es un subconjunto anidado del tramo y su umbral del 15% se compara contra una base homogénea.
- CORE expone la longitud de ventana efectiva y el flag de ventana insuficiente.
- El histórico está recalculado desde los RR archivados, con marca de versión, y las diferencias y sus efectos en QA, baseline y gate están documentados.
- El contrato refleja la implementación antes de activarla en el flujo diario.
- `add_ans_balance_to_core.py` no puede reintroducir el cálculo antiguo.
- `AGENTS.md:41` matizado para distinguir re-derivación de fuente de recálculo de métricas.
- La equivalencia o diferencia respecto al cálculo anterior se ha demostrado con Bland–Altman y d de Cohen sobre valores log-transformados, no con ausencia de significación.
- La métrica descriptiva de descartes **dentro** de la ventana queda para HG-05, después de fijar la ventana aquí; no es criterio de cierre de HG-04.
- La revisión de `ARTIFACT_OK_MAX` queda aplazada hasta disponer de la validación de HG-07 y de la métrica en ventana de HG-05. Ninguna de ellas mide por sí sola calidad eléctrica confirmada. No cambiar el umbral en este corte.
- La coordinación con HG-03 y las tareas HG-05/HG-06/HG-07 sigue la secuencia revisada de HG-05 §9 *(movida el 2026-10-27 a [Secuencia de tareas HG](<HG Secuencia de tareas HRV.md>))*; HG-04 no espera una fusión aún no validada.
- *Actualización 2026-10-27:* HG-05 se propone para cierre; la métrica en ventana pasa a HG-10 como campo opcional y la definición de `Artifact_pct` con corte a 375 s a HG-10. Véase la [nota de HG-05](<HG-05 Auditoria de deteccion de latidos y calidad de senal en ventana.md>).

---

## 11. Por qué no se excluye 2025 y por qué la ventana es de 180 s

Dos correcciones a versiones anteriores de este documento, ambas con medición.

### 11.1 El ancla `healthy` del gate está en 2025

`build_hrv_final_dashboard.py:107–109`:

```
healthy_start = os.environ.get("HRV_HEALTHY_START", "2025-07-01")
healthy_end   = os.environ.get("HRV_HEALTHY_END",   "2025-09-30")
healthy_factor = 0.85
```

**86 días de CORE** en ese periodo definen `healthy_rmssd`, del que sale `threshold_best = 0.85 × healthy_rmssd` (`:301`) y con él `degraded_vs_best` y `warning_threshold_best`, que entran al gate. 2025 no participa en el baseline: lo **ancla**.

> **[Corregido 2026-10-20, revisión externa — §13]** Error factual: esas señales **no entran al gate**. Son el aviso informativo `baseline60_degraded` (contrato §16: «no cambia el gate del día»), calculado después de `gate_final` (`build_hrv_final_dashboard.py:2136–2155`), y con el modo por defecto `adaptive90` el aviso legacy usa la referencia reciente, no `healthy`. Su único consumidor fuera del dashboard es `analysis/session_analysis_pipeline.py`, como modificador de precisión del contexto. Conservar 2025 sigue teniendo valor (referencia histórica comparable y aviso informativo), pero no es necesario para preservar el semáforo. Esto debilita el argumento contra ventanas más largas; la decisión 180/180 queda como candidata, no como única opción viable.

Una versión anterior de este documento afirmaba que el gate nunca alcanza 2025 porque la ventana más larga es de 90 días (`adaptive_window_days`). Era falso. Además existen umbrales de carga con `expanding(min_periods=8)` (`:512`), es decir histórico completo, aunque esos derivan de sesiones y no los afecta HG-04.

Consecuencia directa: con recorte de 180 s y ventana de 240 s, solo **3 de los 86 días** del periodo healthy son viables (duración mediana en ese periodo: 395 s). Esa combinación no tiene un coste aceptable, **destruye el ancla**. Queda descartada. *(Ver corrección anterior: el ancla es informativa; el descarte debe reevaluarse con ese coste real.)*

### 11.2 La precisión extra de una ventana de 240 s es inmaterial

SD de lnRMSSD día a día, calculada desde diferencias de días consecutivos (n = 450 pares): **0,207**.

| Ventana | Ruido de ventana | % de la varianza día-a-día | SD total esperada |
|---|---|---|---|
| 120 s | 0,082 | 16% | — |
| **180 s** | **0,060** | **8%** | 0,2118 |
| 240 s | 0,039 | 4% | 0,2068 |

Pasar de 180 a 240 s mejora la SD total un 2,4%. El valor de la tarea está en eliminar la **heterogeneidad** (hoy el ruido varía entre 0,039 y 0,12 según el día), no en alcanzar el suelo de ruido.

### 11.3 Viabilidad de la combinación adoptada

| Recorte | Ventana | Total | 2025 | 2026 | Periodo healthy |
|---|---|---|---|---|---|
| 180 s | 240 s | 335/497 | 61/222 | 274/275 | **3/86** |
| **180 s** | **180 s** | **486/497** | **212/222** | **274/275** | **85/86** |
| 120 s | 240 s | 486/497 | 212/222 | 274/275 | 85/86 |

**Decisión: recorte fijo de 180 s, ventana `[180, 360]` s, cola `[240, 360]` s, recálculo completo de las 499 filas recalculables, sin bloque legacy.** El ancla `healthy` se recalcula con la misma definición que la serie viva, que es precisamente el objetivo. Los 11 días no viables (registros < 375 s) reciben el flag de ventana insuficiente.

Esto **anula** la decisión de la sección 10.4 («serie viva desde 2026-01, 2025 como legacy»), que se apoyaba en dos premisas erróneas: que el gate no alcanza 2025 (11.1) y que la ventana de 240 s valía su coste (11.2).

---

## 10. Caracterización n=1 del transitorio: la medición que decide

La sección 3 y la 9 comparan contra medias poblacionales. Lo que determina la regla correcta es cómo se estabiliza **este** atleta, no el deportista medio de un estudio. Recaracterización sobre 484 registros de duración ≥375 s, usando como referencia de cada día **su propio nivel estable** (RMSSD de los últimos 180 s de ese registro), que es más limpio que la referencia de minutos 4–7 usada en la sección 3.

### 10.1 Su transitorio es más largo y mucho más variable que el de la literatura

| Minuto | Mediana | p25 | p75 | % días > +10% | SD entre días |
|---|---|---|---|---|---|
| 0–1 | **+0,227** | +0,083 | +0,356 | **74%** | 0,213 |
| 1–2 | **+0,150** | +0,039 | +0,269 | **64%** | 0,173 |
| 2–3 | +0,072 | −0,021 | +0,176 | 45% | 0,177 |
| 3–4 | +0,047 | −0,038 | +0,123 | 34% | 0,149 |
| 4–5 | +0,025 | −0,070 | +0,099 | 26% | 0,136 |

Los 60 s de Krejčí [6] dejarían en su caso un sesgo mediano de **+15%** en el minuto siguiente. La estabilización de 60–90 s validada en deportistas jóvenes es insuficiente para este atleta.

Corrección respecto a la sección 3: allí se concluyó que el transitorio estaba resuelto en el minuto 4. Era en parte un artefacto de usar los minutos 4–7 como referencia. Con referencia independiente, el transitorio se extiende más.

> **CORRECCIÓN 2026-10-20 (ver sección 12):** la tabla siguiente está inflada por solape entre bloque y referencia a partir del corte de 180 s. Sin solape, 120 s y 180 s dan el mismo 44%. La conclusión «se completa entre 180 y 240 s» no se sostiene.

**Dónde termina de verdad:** proporción de días en que el bloque de 60 s que empieza en cada corte cae dentro de ±10% de su nivel estable:

| Corte | % días dentro de ±10% |
|---|---|
| 0 s | 19% |
| 60 s | 28% |
| 120 s | **44%** |
| 180 s | 51% |
| 240 s | **54%** |

El suelo de ruido es el dato clave: un bloque de 60 s tiene SD de lnRMSSD de 0,11–0,15, así que ±10% equivale a ±0,7–0,9 SD y bajo ruido puro cabría esperar ~50–55% de días dentro de la banda. A 240 s se alcanza ese 54%: el transitorio ha desaparecido y lo que queda es ruido. A 120 s solo 44%, por debajo del suelo: **queda transitorio residual**. Su estabilización se completa entre 180 y 240 s, no entre 60 y 120.

### 10.2 Dependencia del estado: HIPÓTESIS NO CONFIRMADA

Se exploró si el transitorio es mayor en los días de HRV baja, lo que haría que un recorte insuficiente inflara precisamente los días malos y sesgara hacia falso VERDE. **La hipótesis no resiste el control metodológico y queda descartada como argumento.** Se documenta aquí para que no se vuelva a derivar.

La estimación inicial daba rho = −0,272 (Spearman, minuto 0–1 vs RMSSD estable del día, n = 484), con gradiente aparente por terciles (+0,306 en el tercil bajo frente a +0,175 en el alto). **Esa estimación estaba viciada**: los días se ordenaron por el mismo denominador por el que se dividía el transitorio (`ref`), lo que genera regresión a la media mecánica — los días cuyo `ref` resultó bajo por ruido muestran un cociente inflado sin que exista ningún mecanismo fisiológico. Es exactamente el tipo de error que advierte Pecchia y Castaldo 2018 [4].

Controles aplicados (n = 449 registros con ventana tardía partible):

| Método | Minuto 0–1 | Minuto 1–2 |
|---|---|---|
| Naive (mismo `ref` para cociente y orden) | rho = −0,272 | −0,156 |
| Split-half (cociente vs `ref_B`, orden por `ref_A`) | rho = −0,201 | −0,095 |
| **Día anterior (orden totalmente independiente)** | **rho = −0,108** | **+0,001** |

Y los terciles ordenados por el RMSSD del día anterior (n = 412 días consecutivos) no muestran gradiente monótono:

| Tercil (día anterior) | Transitorio min 0–1 | min 1–2 | min 2–3 | n |
|---|---|---|---|---|
| Bajo (30,6 ms) | +0,265 | +0,175 | +0,080 | 138 |
| Medio (40,6 ms) | +0,218 | +0,130 | +0,063 | 136 |
| Alto (52,3 ms) | +0,224 | +0,159 | +0,084 | 138 |

Interpretación: con un ordenador independiente queda un residuo débil en el primer minuto (rho = −0,108) y **nada** en el segundo, sin dosis-respuesta. El split-half tampoco es concluyente porque `ref_A` y `ref_B` provienen del mismo registro: cualquier factor que degrade ese día entero (contacto de electrodos, más artefactos) eleva el transitorio y baja `ref` a la vez, produciendo correlación sin mecanismo de estado.

**Consecuencia para la tarea:** el argumento de «sesgo dependiente del estado hacia falso VERDE» **no debe usarse** para justificar el recorte. La justificación del recorte tardío se apoya únicamente en la magnitud y duración del transitorio (sección 10.1), que es una comparación intra-día pareada y no está afectada por este sesgo. Eso basta: el recorte sigue estando justificado, pero por una razón menos y mejor acotada.

### 10.3 Sin evidencia de deriva en 17 meses

Mediana del transitorio por semestre: 2025-S1 +0,108 / 2025-S2 +0,250 / 2026-S1 +0,234 / 2026-S2 +0,193 (minuto 0–1). El valor bajo de 2025-S1 está confundido por la duración: con grabaciones de ~380 s la referencia de los últimos 180 s cae mucho antes en el registro y comprime el transitorio aparente. Entre los periodos de duración comparable (2025-S2 a 2026-S2) no hay deriva clara. **No hay que recalibrar el recorte periódicamente** [confianza 80%].

### 10.4 Consecuencia: la regla cambia — SUPERSEDIDA POR LA SECCIÓN 11

> Las cifras de esta sección (cortes efectivos por duración, viabilidad de pares) siguen siendo válidas. **La decisión que concluye no lo es**: se apoyaba en que el gate no alcanza 2025, lo cual es falso (sección 11.1). Se conserva por trazabilidad del razonamiento.

La regla «últimos 240 s» ya implica un corte efectivo muy distinto según la duración del registro:

| Año | Duración mediana | Corte efectivo implícito |
|---|---|---|
| 2025 | 396 s | **~141 s** |
| 2026 | 510 s | **~255 s** |

Es decir: para los registros actuales el diseño propuesto ya cumple lo que exige su transitorio (~255 s), y hablar de «recorte de 120 s» era engañoso: los 120 s eran solo la puerta de viabilidad, no el inicio de la medición. Pero en los registros de 2025 la misma regla deja el corte en 141 s, donde su propio transitorio sigue activo y es dependiente del estado.

Viabilidad de pares (recorte fijo, ventana fija):

| Recorte | Ventana | Total | 2025 | 2026 |
|---|---|---|---|---|
| 120 s | 240 s | 486/497 | 212/222 | 274/275 |
| **180 s** | **240 s** | 335/497 | 61/222 | **274/275** |
| 240 s | 240 s | 284/497 | 21/222 | 263/275 |

Las grabaciones de 2025 **no pueden** satisfacer a la vez un recorte ≥180 s y una ventana de 240 s: es una imposibilidad física, no una elección de diseño.

**Decisión revisada:**

- **Serie viva (desde 2026-01): recorte fijo de 180 s + ventana fija de 240 s.** Viable en 274/275 registros. Respaldado por la magnitud de su propio transitorio (sección 10.1), con ruido residual de 0,039.
- **2025: bloque legacy.** Recalcularlo con recorte de 120 s produciría valores comparables entre sí pero no con la serie viva, y medidos con un recorte que en este atleta deja transitorio residual (mediana +0,07 en el minuto 2–3). Es más honesto marcarlo con su propia definición y excluirlo de los baselines de gate.
- **El coste de excluir 2025 es nulo en la práctica**: el baseline operativo más largo es de 90 días (`adaptive_window_days`) y desde 2026-01 hay 275 registros con duración homogénea de ~500 s. El gate nunca alcanza 2025.

Esto **sustituye** la conclusión de la sección 9.2 («una sola regla para todo el histórico pesa más»). Esa conclusión priorizaba la homogeneidad formal de la serie; la caracterización n=1 muestra que aplicar una regla única obligaría a medir toda la serie con un recorte que en este atleta deja transitorio residual. Prevalece medir bien la serie que alimenta el gate.

Efecto práctico: el recálculo pasa de 499 filas a **275** (2026 completo), y la frontera de definición se sitúa en 2026-01-01, que además coincide con el cambio de duración de protocolo. Sigue siendo necesario el recálculo, pero es más barato y más defendible.

---

## 9. Contraste con la literatura

Revisión bibliográfica externa consultada (informe Sci-Bot, 19 referencias, 2026-10-18) sobre duración mínima, estabilización, postura y dispositivos en HRV matinal. Resultado global: **converge con esta tarea en los tres puntos centrales y añade dos elementos nuevos.**

### 9.1 Converge

**El detector adaptativo es el instrumento equivocado.** Krejčí 2018 [6] observa que la FC se estabiliza antes que el RMSSD (30 s frente a 60 s en deportistas) y concluye literalmente que *iniciar el registro mediante un algoritmo de «FC estable» puede ser inadecuado*. ~~Es la misma conclusión que la sección 2 de este documento, obtenida por otra vía.~~ **[Corregido 2026-10-20, revisión externa — §13]** Krejčí critica detectar la estabilidad por **FC**; el detector local usa **RMSSD**. Es un argumento convergente, no una refutación directa del algoritmo local.

**El transitorio existe y hay que recortarlo.** Forner-Llacer 2020 [7], con 718 mediciones en futbolistas profesionales, encuentra que la ventana sin estabilización (0 + 1 min) sobreestima el RMSSD (mediana 95,1 vs 87,7 ms, ≈ +8,5%). El perfil medido en la sección 3 (+24% en el primer minuto) es del mismo signo y mayor magnitud, coherente con que aquí el primer minuto se compara contra el nivel estable del propio registro.

**El recorte queda por encima del mínimo bibliográfico.** Los valores publicados van de 60 s en deportistas jóvenes [6] a ~2 min para población general o de menor actividad vagal; el recorte adoptado (180 s, sección 11) supera ambos. *(Corregido 2026-10-20: antes decía «120 s de recorte está bien situado», decisión ya superada.)*

**Promediar varios días.** Uhlig 2020 [11] encuentra ICC de solo 0,49–0,64 en supino a lo largo de 11 meses y recomienda promedios multi-día por la alta variabilidad intraindividual. El pipeline ya lo hace (`RMSSD_med7`, `build_hrv_final_dashboard.py:272`): queda corroborado, no hay que cambiarlo.

**Postura y dispositivo.** Supino es la referencia y la postura más fiable [9][10][11]; la banda de pecho ECG es válida frente a ECG/Holter, con sesgos de 0,6% en SDNN y 1,6% en RMSSD en supino [12][13]. El protocolo actual es correcto en ambos aspectos. Nota lateral: la literatura señala que en deportistas con muy alta actividad vagal el LnRMSSD pierde sensibilidad con FC muy baja («saturación parasimpática»), caso en el que medir sentado puede ser preferible [3]; es la justificación de un protocolo sentado como el de `data/SeatRR`, fuera del alcance de esta tarea.

### 9.2 Tensión aparente que no lo es: ¿120 s bastan para el RMSSD?

Munoz 2015 [1] (n = 3.387) obtiene r = 0,986 para RMSSD con 120 s frente al patrón de 240–300 s y concluye que *no es necesario superar 120 s* para los índices temporales. Holmes 2020 [3] no encuentra diferencias entre 1 + 1 min y 5 + 5 min, con ICC de 0,88–0,92 para RMSSD. Leído superficialmente, eso haría innecesaria cualquier ventana por encima de 120 s.

No es una contradicción: **miden criterios distintos.**

- `r` e ICC son medidas de concordancia **entre sujetos**: su valor está dominado por la varianza interindividual. En una muestra de 3.387 adultos con rangos de RMSSD muy amplios, un ICC alto convive con un error intraindividual apreciable.
- Lo que decide el gate de ENDURANCE HRV es la utilidad **intraindividual**: detectar cambios relevantes de un único atleta contra su propio baseline. La dispersión de ventanas de la sección 1 (SD de lnRMSSD de 0,082 con ventana de 120 s frente a 0,039 con 240 s) mezcla variación fisiológica dentro del registro y error de medición. **No mide por sí sola la precisión entre días ni se puede comparar directamente con un cambio de ~0,05 en lnRMSSD.**

La propia revisión aporta el argumento: Uhlig 2020 [11] documenta que la variabilidad intraindividual es tan alta que la fiabilidad de una medición aislada es limitada. Una duración «validada» para distinguir grupos no está validada para seguir a un individuo día a día.

Conclusión histórica de esta sección: la literatura valida 120 s para uso transversal, lo que no basta para seguimiento individual. La decisión final (recorte 180 s, ventana 180 s, sección 11) queda por encima de ese mínimo bibliográfico y por debajo del patrón de referencia de 240–300 s [1], que es inalcanzable en este histórico sin recortar demasiado pronto o sacrificar el periodo `healthy`.

> **RECTIFICACIÓN 2026-10-21:** «valida 120 s» era demasiado general. Muñoz et al. compararon subventanas de 120 s con una época posterior de 240–300 s que las contenía, en adultos de población general y con intervalos derivados de presión arterial digital. Los propios autores advierten que el solapamiento infla la concordancia. Esto no valida la repetibilidad diaria ni una duración mínima para el gate de este atleta. La decisión de 180 s de §11 ya estaba retirada en el estado vigente de este documento.

### 9.3 Elemento nuevo 1: comparación de métricas de artefactos (rectificada)

> **RECTIFICACIÓN 2026-10-21:** era erróneo llamar al 5% de [1] «el estándar» y afirmar que el umbral local es «3–4× más laxo». En Muñoz et al., el >5% era un criterio de exclusión **de ese estudio** sobre intervalos NN interpolados tras inspección visual de señales de presión arterial digital. Nuestro `Artifact_pct` es `(N_off + N_oor + N_drr) / N_total` sobre el registro RR completo, sin medir la fracción NN interpolada ni su concentración en la ventana usada para RMSSD (`build_hrv_core.py:284–305`). Los porcentajes no son directamente comparables. La recomendación de excluir un segmento por más de un artefacto aparece en la discusión de Muñoz para segmentos muy cortos y no debe trasladarse sin validación a registros de varios minutos.

El código vigente admite `Calidad = OK` hasta `ARTIFACT_OK_MAX = 15.0` y solo marca `INVALID` por encima del 20% (`build_hrv_core.py:84,431–432`). Son umbrales operativos propios; esta comparación bibliográfica no demuestra que sean apropiados o inapropiados.

Medido sobre CORE (n = 501):

| `Artifact_pct` | Días | % |
|---|---|---|
| > 5% | 33 | 6,6% |
| > 10% | 22 | 4,4% |
| > 15% | 17 | 3,4% |
| > 20% | 14 | 2,8% |

En la extracción histórica, **14 días clasificados `OK` superan el 5% de descartes sobre el registro completo** (5 de ellos superan el 10%). Este recuento describe la métrica local; el 5% no es aquí un umbral de rechazo derivado de Muñoz. Esos días entran al baseline y al gate como `OK`. El porcentaje no determina cuántos descartes hubo en la ventana medida ni la calidad eléctrica real del ECG; por ello no permite concluir que los 14 días sean inaceptables.

Esto interacciona directamente con HG-03: los días de mayor número de descartes son justamente aquellos en que el pareado incorrecto hace más daño (sección 6).

**Queda fuera del alcance de HG-04** — es un cambio de umbral de QA, no de ventana de cálculo. HG-05 medirá por separado los descartes dentro de la ventana fija y HG-07 evaluará en sombra una posible reparación de RR. Solo después de comparar esas métricas con ECG verificable, QA histórica, baselines y decisiones podrá reconsiderarse el 15%/20%. La propuesta de bajar a 5% sobre el porcentaje global no se adopta con la evidencia actual.

### 9.4 Elemento nuevo 2: precedente exacto de protocolo

Uhlig 2020 [11] usa registros de 8 minutos y analiza **los minutos 2 a 7**: recorte de 120 s y ventana de 300 s. Es, literalmente, el diseño que propone esta tarea, con 60 s más de ventana. Las grabaciones de 2026 (duración mediana 510 s) lo admitirían en 274/275 casos; las de 2025 (mediana 396 s) no. Si en algún momento se decidiera dejar de recalcular el tramo 2025 y tratarlo como bloque legacy cerrado, **300 s sería la elección preferible para la serie viva**, con respaldo bibliográfico directo. Mientras el objetivo sea una sola definición para las 499 filas, la ventana es de 180 s (sección 11.3).

### 9.5 Lo que la literatura no cubre

El informe señala que faltan estudios que validen el registro matinal con banda de pecho en contexto domiciliario, y que la mayoría de validaciones ultra-cortas se hicieron en adultos jóvenes o deportistas, con poca evidencia en mayores [4][6][3]. Tampoco hay consenso formal sobre el tiempo de estabilización: los valores publicados oscilan entre 0 y 10 min según población y métrica. Es decir: la decisión de recorte y ventana (180 s / 180 s, sección 11) no puede apoyarse solo en bibliografía, y las mediciones internas de este documento siguen siendo la evidencia principal para este atleta concreto.

Referencias citadas con la numeración del informe Sci-Bot: [1] Munoz 2015 PLOS ONE (10.1371/journal.pone.0138921); [3] Holmes 2020 (10.1016/j.hitech.2020.100375); [4] Pecchia & Castaldo 2018 (10.1049/htl.2017.0090); [6] Krejčí 2018 PLOS ONE (10.1371/journal.pone.0205115); [7] Forner-Llacer 2020 (10.1055/a-1186-1316); [9] Acharya 2005 (10.1016/j.jbmt.2004.04.001); [10] Kumar 2020 (10.1016/j.procs.2020.03.435); [11] Uhlig 2020 (10.1016/j.biopsycho.2020.107905); [12] Porto & Junqueira 2008 (10.1111/j.1540-8159.2009.02175.x); [13] Loimaala 1999 (10.1046/j.1365-2281.1999.00152.x).

---

## 8. Confianza de cada conclusión (histórica; porcentajes retirados)

> **Estado 2026-10-21:** esta tabla registra juicios anteriores para preservar la trazabilidad. Sus porcentajes no están calibrados y **ninguno constituye una conclusión o recomendación vigente**; aplican las correcciones iniciales y la síntesis crítica enlazada arriba.

| Conclusión | Certeza |
|---|---|
| La fórmula de RMSSD es correcta y no requiere cambio | 99% |
| El transitorio de estabilización es real y justifica recortar el principio | 97% |
| El histórico es recalculable (499/502 filas) | 98% |
| El solape del 50% infla la estabilidad aparente del detector | 96% |
| El umbral del 8% está por debajo del ruido del estimador | 95% |
| El filtro delta-RR no merece rediseño | 96% |
| `rel()` es asimétrica y favorece el descenso | 93% |
| El detector no aporta frente a un recorte fijo | 94% |
| La heterogeneidad de ventana (8,2×) es la mayor fuente de varianza evitable | 92% |
| El umbral del 15% es razonable en la geometría **vigente**; ~~el defecto está en la base de comparación~~ — en la geometría nueva no conserva su comportamiento (§13.2) | 88% → **40%** para la nueva geometría |
| Conviene unificar HG-03 y HG-04 en un solo corte | 88% |
| Que su transitorio sea más largo que el de la literatura (60–90 s insuficientes para él) | 95% |
| Que el transitorio **no** dependa de forma establecida del estado del día (hipótesis descartada) | 82% |
| ~~Que su estabilización se complete entre 180 y 240 s~~ — **retirada 2026-10-20** (sección 12): el decaimiento sigue hasta ~270–300 s | — |
| Que el transitorio decaiga de forma continua hasta ~270–300 s (sección 12) | 80% |
| Que el recorte adecuado sea 180 s — **rejustificado** (sección 12): es el inicio más tardío compatible con ventana de 180 s en ~todo el histórico | 80% |
| Que la ventana deba ser de 180 s y no 240 s (precisión inmaterial frente a varianza real) | 91% |
| ~~Que 2025 **no** deba excluirse, por contener el ancla `healthy`~~ — el ancla es informativa, no del gate (§13.1); conservar 2025 sigue siendo preferible por comparabilidad | 97% → **70%** |
| Que la ventana deba anclarse al inicio y no al final del registro | 93% |

| Que no haya deriva del transitorio en 17 meses | 80% |

| ~~El umbral de artefactos vigente (OK hasta 15%) es más laxo que el estándar (5%)~~ — **retirada 2026-10-21**: métricas no comparables (§9.3) | — |

Todas las mediciones provienen de las 497 grabaciones tumbadas de `data/rr_downloads`. **No cubren las grabaciones sentadas de `data/SeatRR`**, que habría que verificar por separado si en algún momento entran al pipeline: su duración y su perfil de transitorio pueden ser distintos y el recorte de 180 s no está validado para ellas.

---

## 12. Corrección 2026-10-20: la tabla de §10.1 estaba inflada por solape

Scripts: `research/scripts/hg04_transient_overlap_check.py` y `research/scripts/hg04_transient_bias_disjoint.py` (lectura en memoria de `data/rr_downloads`, 17 zips + CSV `from_jsonl`, 502 fechas; filtros vigentes de `_parse_and_filter_rr`; RMSSD con pares originalmente consecutivos).

**El defecto.** En §10.1 la referencia de cada día son los últimos 180 s del registro. En registros cortos (2025, ~381 s efectivos) esa referencia empieza en ~200 s, así que los bloques que empiezan en 180 y 240 s comparten latidos con ella. Es el mismo error que §2.1 reprocha al detector. Salida cruda:

| Corte | §10.1 (con solape) | Sin solape (n) | Submuestra común sin solape (n=276) |
|---|---|---|---|
| 0 s | 18,6% | 18,6% (479) | 21,0% |
| 60 s | 28,1% | 28,1% (480) | 25,4% |
| 120 s | 44,1% | 44,1% (481) | 43,8% |
| 180 s | **51,2%** | **45,3%** (333) | **43,8%** |
| 240 s | **54,2%** | **48,4%** (281) | **48,6%** |

Las cifras de §10.1 se reproducen; la mejora 120 → 180 s es artefacto del solape.

**Sesgo con referencia disjunta** (referencia = últimos 120 s; bloques de 60 s que terminan antes), submuestra común n=276, mediana Δ lnRMSSD [IC95 bootstrap]:

| Bloque | Mediana | IC95 | % días > 0 |
|---|---|---|---|
| 120–180 s | +0,090 | +0,073 .. +0,116 | 75% |
| 180–240 s | +0,060 | +0,048 .. +0,084 | 67% |
| 240–300 s | +0,031 | +0,013 .. +0,046 | 59% |
| 270–330 s | +0,029 | −0,006 .. +0,042 | 55% |
| 300–360 s | +0,013 | −0,016 .. +0,041 | 53% |

**Qué cambia:**

1. El transitorio no «termina entre 180 y 240 s»: decae de forma continua y su sesgo deja de ser distinguible de 0 hacia 270–300 s. A 180 s queda ~+6%.
2. No se puede separar, con registros de ≤9 min, un transitorio de asentamiento de una deriva lenta durante toda la grabación. **No verificado.**
3. Para seguimiento longitudinal no hace falta sesgo cero: con geometría fija el sesgo residual es un desplazamiento común a todos los días. Lo que importa es que sea constante entre días; eso **no está medido todavía** para `[180, 360]` y es una comprobación pendiente antes de implementar.
4. La elección de 180 s se mantiene, pero con otra justificación: es el inicio más tardío compatible con una ventana de 180 s en 486/497 registros (`t_end_eff ≥ 360`). Cualquier inicio más tardío reduce sesgo y pierde 2025/`healthy`. No es «el punto donde termina el transitorio».

### 12.1 Estabilidad entre días del sesgo de `[180, 360]` (medido 2026-10-20)

Script: `research/scripts/hg04_window_bias_stability.py`. Δ = lnRMSSD`[s, s+180]` − lnRMSSD de los últimos 120 s (disjunta). Solo registros con `t_end_eff ≥ 480` s: **n = 287** (209 ECG, 78 Polar; 2025-07-08 → 2026-10-15). Nulo empírico: dos ventanas tardías de 120 s, `[te−240, te−120]` vs `[te−120, te]`: SD robusta 0,129, de la que se deriva una SD esperada solo por ruido de **0,117** para la comparación 180 vs 120 (supuesto: varianza ∝ 1/longitud).

| Ventana | Mediana Δ | SD robusta | Exceso sobre ruido |
|---|---|---|---|
| `[0, 180]` | +0,170 | 0,154 | 0,100 |
| `[60, 240]` | +0,116 | 0,143 | 0,083 |
| `[120, 300]` | +0,062 | 0,118 | 0,011 |
| **`[180, 360]`** | **+0,042** | **0,107** | **0,000** |

Dependencia de estado con ordenador independiente (lnRMSSD`[180,360]` del día anterior, n = 266 pares consecutivos): `[180,360]` rho = −0,035, terciles +0,044 / +0,029 / +0,047, sin gradiente. Por origen: mediana +0,036 (ECG) frente a +0,049 (Polar); diferencia no contrastada.

**Lectura:** en `[180, 360]` queda un desplazamiento medio de ~+4% y su dispersión entre días no se distingue del ruido del estimador: el sesgo es una constante común, no una fuente de varianza por día, que es lo que necesita el seguimiento longitudinal. **Validado para registros ≥ 480 s** [confianza 80%].

> **[Corregido 2026-10-20, revisión externa — §13]** Sobreinterpretación. El «exceso 0,000» es un exceso negativo recortado a cero; el nulo usa ventanas tardías que también contienen variación fisiológica y supone varianza ∝ 1/longitud; no se fijó margen de equivalencia ni cota de incertidumbre. Lo medido es: **no se detecta** variación del sesgo por encima del ruido estimado. La constancia del sesgo queda **indeterminada** [confianza en constancia: 40%]. **No verificado** para los registros cortos de 2025 (mayoría del periodo `healthy`, mediana 395 s), donde no cabe una referencia disjunta tras los 360 s. Nota: el ruido de una ventana de 120 s que implica este nulo (~0,091) es mayor que el 0,082 de §1; no se ha resuelto la diferencia de método.

### 12.2 ¿Tiene `Tiempo_Estabilizacion` valor como control de calidad? (punto 3 de §5)

Medido 2026-10-20 para decidir entre las opciones (a) y (b) del punto 3 de §5.

**Lectura del código.** En `Calidad` (`build_hrv_core.py:439–440`) la condición `60 <= Lat_eff <= 600` es inoperante: `Lat_eff = max(lat, 60)` es siempre ≥ 60 y en CORE no hay ningún `lat > 600` (máximo físico: la duración del registro). El único efecto real de la latencia sobre `Calidad` es `lat = NaN` → `FLAG_mecánico`.

**Días afectados.** En CORE (504 filas) hay 32 días con `lat = NaN`; **15** son `FLAG_mecánico` solo por ese motivo (`Artifact_pct` 0–2,6%, `HRV_Stability = OK`, HR 47–60): 11 de la era Polar y 4 de la era ECG.

**¿Indica la latencia mediciones peores?** Script `research/scripts/hg04_latency_as_quality.py` (argumento opcional `Polar`/`ECG`). Dos medidas de calidad por día, sobre los 490 días no `INVALID`: incoherencia interna `|lnRMSSD[180,270] − lnRMSSD[270,360]|` (independiente del nivel fisiológico) y desviación `|lnRMSSD_stable − mediana de los 14 días OK previos|`. Spearman con p por permutación (sin scipy en el entorno).

| Era | Latencia vs incoherencia interna | Latencia vs desviación (tramo CORE) | Días NaN: incoherencia vs resto |
|---|---|---|---|
| Polar (n ≈ 255) | rho +0,037, p = 0,55 | **rho +0,143, p ≈ 0,02** | +0,038, p = 0,16 (n = 13) |
| ECG (n = 206) | rho +0,005, p = 0,94 | rho −0,061, p = 0,40 | +0,103, p = 0,075 (n = 4) |

**La asociación de la era Polar es mecánica.** Script `research/scripts/hg04_latency_dev_fixed_window.py`: repitiendo la desviación con lnRMSSD de ventana fija `[180, 360]`, que la latencia no toca, cae a rho = +0,066 (p = 0,30, n = 248). Interpretación: en los registros cortos de 2025 una latencia tardía acorta el tramo y lo hace más ruidoso; la latencia no detecta mediciones malas, las produce. Es la heterogeneidad que elimina esta tarea [confianza 75%].

> **[Corregido 2026-10-20, revisión externa — §13]** No demostrado. Entre ambas pruebas cambian la métrica y la muestra (257 → 248), y comparar un resultado significativo con otro no significativo no prueba causalidad. La explicación mecánica es **plausible, no establecida** [50%].

**Conclusión.** El detector vigente no aporta como control de calidad [confianza 80%]. **[Corregido 2026-10-20, revisión externa — §13]** Rebajada: lo medido es que **no se detecta** valor como control de calidad con estas pruebas [confianza 55–60%]; no que carezca de él. Queda sin probar si un estimador bien construido (opción b) aportaría; ningún dato actual sugiere una señal que recuperar. Los 4 días NaN de la era ECG (incoherencia +0,10) son demasiado pocos para concluir en ningún sentido.

### 12.3 Efecto de la opción (a) sobre el ancla `healthy`

`compute_healthy_anchors()` (`build_hrv_final_dashboard.py:260–284`) usa solo días `Calidad == OK`, mediana móvil de 7 días. Promoviendo a `OK` los 15 días del punto anterior, sin ningún otro cambio: días `OK` del periodo 76 → 80; `healthy_rmssd` 50,07 → **50,07 ms** (Δ 0,00%); `healthy_hr` 49,21 → 49,26; umbral `0,85 ×` sin cambio (42,56 ms). La opción (a) por sí sola no mueve el ancla [confianza 95%]. El efecto del recálculo completo HG-03 + HG-04 sobre el ancla queda por medir en el procedimiento de §6.

---

## 13. Revisión externa 2026-10-20

Se verificó cada punto contra código y datos antes de aceptarlo. Los cuatro se confirman.

### 13.1 El ancla `healthy` no interviene en el gate — confirmado

Contrato `ENDURANCE_HRV_Spec_Tecnica.md` §16 (`baseline60_degraded`: «no cambia el gate del día»); cálculo tras `gate_final` en `build_hrv_final_dashboard.py:2136–2155`, bajo el comentario «Warning baseline60_degraded (informativo)». Correcciones aplicadas en §11.1 y en la tabla de §8.

### 13.2 La tasa de `STAB_LAST2_MISMATCH` cae con la geometría nueva — confirmado

Script `research/scripts/hg04_mismatch_rate_new_geometry.py` (pares originalmente consecutivos; 485 fechas evaluables con CORE y `t_end_eff ≥ 360`; comparación disjunta evaluable en 484):

| Cálculo | >15% (todas) | >15% (no `INVALID`, n = 476) |
|---|---|---|
| CORE vigente | 35 (7,22%; n=485) | 31 (6,51%) |
| Geometría vigente, pares consecutivos | 32 (6,60%; n=485) | 30 (6,30%) |
| **`[180,360]` vs cola anidada `[240,360]`** | **7 (1,44%; n=485)** | **6 (1,26%)** |
| Mitades disjuntas `[180,270]` vs `[270,360]` (referencia descriptiva) | 148 (30,58%; n=484) | 144 (30,25%) |

**Corrección reproducida 2026-10-21:** el `dropna()` global excluía un registro `INVALID` por no poder calcular la comparación disjunta, aunque sí era evaluable en las tres métricas principales. Se usan ahora cohortes explícitas. En los 484 días comunes con la comparación disjunta, los tres primeros recuentos son 34, 31 y 6, respectivamente; los no `INVALID` no cambian. Cuantiles del mismatch nuevo p50/p90/p95/p99 sobre 485 días: 0,035 / 0,095 / 0,120 / 0,154 (vigente con pares consecutivos: 0,047 / 0,134 / 0,167 / 0,241). El p93 es 0,106, pero **reproducir la tasa no es un criterio de validación**: falta evaluar qué inestabilidades detecta cada geometría y cuáles deja pasar. Son disparos de la condición, no cambios del semáforo.

### 13.3 Sesgo constante y latencia — sobreinterpretación aceptada

Ver correcciones en §12.1 y §12.2. Lo que se mantiene: el sesgo mediano de `[180,360]` es ~+4,3% (reproducido por el revisor) y no se detecta dependencia del estado del día con ordenador independiente. Lo que se retira: «constante», «validado» y «la latencia produce mediciones malas». Para afirmar constancia haría falta un margen de equivalencia predefinido y una cota superior de la variación del sesgo.

### 13.4 Las columnas nuevas rompen esquema — confirmado

`build_hrv_core.py:726–731` rechaza columnas no canónicas. Corrección en §5 punto 4.

### 13.5 Estado revisado de la decisión

**`[180, 360]` con cola `[240, 360]` se mantiene como candidata principal, no como diseño validado** [80% en su razonabilidad]. Antes de adoptarla:

1. Recálculo conjunto en copia aislada (HG-03 sola, HG-04 sola, ambas) y comparación de QA, baselines y gate con Bland–Altman y d de Cohen (§6).
2. Evaluación de sensibilidad de `STAB_LAST2_MISMATCH` en la nueva geometría: qué días dejan de dispararse y si eran inestables por otros criterios.
3. Política explícita para ventanas incompletas. **Corregido 2026-10-21:** no son 11, son **44** registros con `t_end_eff < 375 s`, todos de la era Polar. ~~36 entre 2025-05-12 y 2025-07-23 (la mayoría, 37, entre 355 y 375 s)… Ninguno cae en el periodo `healthy` (jul–sep 2025).~~ **[Corregido 2026-10-21 tarde]:** 35 hasta 2025-07-23; 40 entre 355 y 375 s; **11 sí están en el periodo `healthy`** (2025-07-01, 07-06, 07-18, 07-23, 08-12, 08-29, 08-30, 09-02, 09-12, 09-18, 09-24); el resto, 2025-11-01 y 2026-03-05. El «11» original y el de §14.10 cuentan otra cosa (`t_end_eff < 360`, sin 180 s tras el inicio); ambas cifras son válidas para preguntas distintas. Con inicio en 210 s dejan un tramo de 75–165 s. Las 3 fechas sin RR (2026-02-26/27 y 2026-03-03) no son un problema de ventana: no hay archivo, la captura del dispositivo falló (0–1 latido registrado) y ya están `FLAG_mecánico`/excluidas del gate; no requieren política nueva.
4. Diseño de la migración de esquema de CORE.
5. Reevaluar ventanas más largas (p. ej. 240 s) ahora que 2025 no es necesario para el gate.

### 13.6 Reevaluación de ventanas más largas (punto 5 de §13.5)

Script `research/scripts/hg04_window_candidates.py` (502 fechas: 281 Polar, 221 ECG; 86 en periodo `healthy`). Pares originalmente consecutivos. Ruido del estimador = SD robusta de (lnRMSSD mitad 1 − mitad 2)/2 dentro de la ventana; incluye la variación fisiológica intraventana, que también afecta a la medición. SD día a día = SD robusta de diferencias entre días consecutivos /√2, en la submuestra común a las cuatro primeras candidatas (n = 311 pares).

| Ventana | Viables (Polar / ECG / `healthy`) | Ruido del estimador | Sesgo mediano vs ref. disjunta (n) | SD día a día |
|---|---|---|---|---|
| **`[180, 360]`** | 485 (269 / 216 / 85) | 0,065 | +0,042 (282) | 0,229 |
| `[180, 420]` | 335 (119 / 216 / **3**) | 0,061 | — | 0,221 |
| `[120, 360]` | 486 (270 / 216 / 85) | 0,062 | +0,050 (282) | 0,221 |
| `[150, 360]` | 485 (269 / 216 / 85) | 0,064 | +0,041 (282) | 0,230 |
| `[180, 480]` | 282 (78 / 204 / 2) | 0,055 | — | 0,232* |
| `[240, 480]` | 282 (78 / 204 / 2) | 0,060 | — | 0,222* |

\* Submuestra distinta (solo registros ≥ 480 s, n = 253 pares): no comparable directamente con las filas anteriores.

Lectura:

1. **La dispersión calculada con mitades es ~6% menor (0,065 → 0,061)** para la ventana de 240 s. No demuestra una reducción equivalente del error del estimador: las cohortes difieren y la estadística incluye cambios fisiológicos intrarregistro. La SD día a día es 0,229 frente a 0,221, sin intervalo de confianza. `[180, 420]` pierde 150 de los 269 días Polar viables y deja el periodo `healthy` en 3/86. No basta para elegir una ventana.
2. `[120, 360]` obtiene la misma precisión que `[180, 420]` conservando 2025, a costa de empezar dentro del transitorio (sesgo +0,050 frente a +0,042). Como la estabilidad entre días del sesgo no está establecida (§13.3), empezar antes es un riesgo no cuantificado. No se recomienda sobre `[180, 360]`, pero queda como alternativa razonable [confianza 60%].
3. **Discrepancia sin resolver:** §1 atribuía a la ventana de 240 s un ruido de 0,039 frente a 0,060 para 180 s (−35%). Con el método de mitades la mejora es ~6%. Los métodos difieren (§1: dispersión entre ventanas en distintas posiciones del mismo registro, que incluye transitorio y deriva; aquí: mitades contiguas de una misma ventana). Hasta resolverlo, la cifra de §1 no debe usarse para justificar ninguna elección.
4. Ninguna diferencia de esta tabla tiene intervalo de confianza; son diferencias pequeñas y deben leerse como orden de magnitud.

**Resultado:** `[180, 360]` sigue siendo la candidata principal; la reevaluación no encuentra una ventana claramente mejor.

---

## 14. Replay conjunto HG-03 / HG-04 (2026-10-20)

Experimento: `research/experiments/hg04_replay/` (scripts `extract_rr.py`, `run_arm.py`, `analyze.py`, `arm_h4v.py`, `rojo_exit_segments.py`; resumen agregado en `results/summary.json` y días con cambio de gate en `results/gate_changes_<brazo>.csv`). Copia aislada fuera del repo (`$HOME/hg04_replay_work` en la VM); `data/` no se modifica. Se ejecutan los scripts reales `build_hrv_core.py` (copia parcheada con anclas de texto únicas) y `build_hrv_final_dashboard.py`.

### 14.1 Brazos

| Brazo | Cambio |
|---|---|
| C | Sin cambios (control) |
| H3 | Candidato HG-03: separador NaN entre latidos conservados no consecutivos en origen; afecta a RMSSD, Poincaré, cola, `n_pairs_tail` y ventanas del detector; ambas rutas |
| H4 | Candidato HG-04: recorte 180 s, ventana `[180,360]`, cola `[240,360]`, `Calidad` sin condición de latencia (opción a); ambas rutas |
| H34 | H3 + H4 |
| H4w | Solo ventana HG-04, `Calidad` con la regla de latencia vigente |
| H4v | Valores de H4w con `Calidad` y `HRV_Stability` del control (aísla el efecto de los valores del de la composición de días clean) |

**Corrección de paridad (2026-10-21):** el análisis original solo contrastaba `RMSSD_stable`, `HR_stable`, `SD1` y `Calidad` de CORE; no demostró igualdad completa de los cuatro CSV. La nueva reconstrucción aislada C compara fecha y columna con producción: mismo esquema y fechas; DASHBOARD coincide; CORE difiere en seis fechas (`Flags` en las seis y métricas auxiliares en 2025-10-07/14), BETA_AUDIT en esas dos fechas y FINAL solo en `Stability_Subtype` y `tail_mismatch_pct` de esas dos. Hay, por tanto, **paridad parcial, no completa**. El detalle reproducible y las causas no demostradas están en [el informe de control](../../research/reports/hg03_hg04_control_replay_2026-10-21.md). Las comparaciones de brazos siguen siendo contra C, no contra producción.

### 14.2 Resultados (vs C; 504 filas, 501 reprocesadas)

| | H3 | H4 | H34 | H4w | H4v |
|---|---|---|---|---|---|
| lnRMSSD, días OK en ambos: r | 0,999 | 0,977 | 0,977 | 0,977 | 0,974 |
| Bland–Altman sesgo | +0,000 | −0,003 | −0,004 | −0,003 | −0,001 |
| Límites de concordancia | ±0,028 | −0,132..+0,127 | −0,133..+0,125 | −0,132..+0,127 | −0,139..+0,137 |
| d de Cohen (log) / d_z | 0,001 / 0,017 | −0,008 / −0,039 | −0,014 / −0,064 | −0,008 / −0,039 | −0,004 / −0,019 |
| `STAB_LAST2_MISMATCH` (C = 33) | 31 | 9 | 7 | 9 | 9 |
| Calidad `FLAG` → `OK` / `OK` → `FLAG` | 4 / 2 | 43 / 6 | 43 / 5 | 27 / 6 | 0 / 0 |
| **Días con cambio de `gate_final`** | **18** | **89** | **88** | **80** | **73** |
| … de ellos en 2026 / últimos 90 registros | 3 / 2 | 51 / 21 | 49 / 21 | 49 / 20 | 45 / 19 |
| Cambios de `Action` | 19 | 107 | 103 | 91 | 66 |
| ROJO total (C = 124) | 123 | 97 | 96 | 97 | 99 |

Lectura:

1. **HG-03 es de bajo impacto en días válidos** (sesgo nulo, LoA ±0,03, 18 cambios de gate). Su efecto se concentra en pocos días con muchos descartes.
2. **HG-04 no es equivalente al cálculo vigente.** Sesgo medio nulo, pero los límites de concordancia (±0,13) superan el SWC típico (~0,11): un mismo día puede cambiar de lado del umbral. Cambia el gate en ~18% de los días y en 21 de los últimos 90.
3. **Corrección de atribución (2026-10-21):** 89, 80 y 73 cuentan diferencias de cada brazo frente a C y no pueden restarse para atribuir efectos. La comparación directa encuentra **26 días distintos entre H4 y H4w**, y **36 entre H4w y H4v**. Son contrastes condicionados a cada configuración, con posibles interacciones. H4v cambia 73 días frente a C manteniendo `Calidad` y `HRV_Stability` de C; esto no convierte esos 73 en una parte aditiva de los 89. Los CSV guardados permiten reconstruir estas comparaciones; fuera de la unión de sus fechas cambiadas ambos brazos coinciden con C.
4. **El desplazamiento es asimétrico: menos ROJO** (124 → ~97). En los 39 días que salen de ROJO (H4w), `d_ln` pasa de −0,243 a −0,086; el cambio viene sobre todo de `lnRMSSD_used` (media de 3 días clean; +0,106 mediano), no de `ln_base60` (−0,018).

### 14.3 Hallazgo principal: HG-04 acorta el tramo a la mitad en la serie actual

| Brazo | Tramo mediano Polar / ECG | SD día a día Polar / ECG | `SWC_ln` mediano Polar / ECG |
|---|---|---|---|
| C | 314 s / 364 s | 0,194 / 0,218 | 0,122 / 0,110 |
| H3 | 315 s / 387 s | 0,196 / 0,211 | 0,118 / 0,109 |
| H4w | **179 s / 179 s** | 0,204 / 0,217 | 0,116 / **0,121** |
| H34 | 179 s / 179 s | 0,203 / 0,217 | 0,119 / 0,119 |

El documento planteó HG-04 como reducción de ruido por homogeneización. **En el histórico real, la ventana `[180,360]` mide la mitad de latidos que el tramo vigente**, tanto en la era Polar como en la ECG. No mejora la SD día a día (Polar empeora ligeramente) y en la era ECG ensancha el SWC un ~10% (0,110 → 0,121), lo que por sí solo reduce los ROJO. El supuesto de §1 («el ruido varía entre 0,039 y 0,12 según el día») describe la heterogeneidad, pero no tiene en cuenta que la mayoría de días hoy se miden con un tramo **más largo** que el propuesto.

Consecuencia: la reducción de ROJO no puede atribuirse a mejor medición. No hay forma, con estos datos, de saber si los ROJO que desaparecen eran falsos o verdaderos.

### 14.4 Implicaciones para el diseño [especulativo hasta medir]

- El intercambio real es **homogeneidad frente a precisión**, no homogeneidad con precisión gratis. §11 y §13.6 lo infravaloraron porque comparaban ventanas fijas entre sí, no contra el tramo vigente.
- Alternativas a evaluar: inicio fijo con fin al final del registro (`[s, t_end_eff]`; longitud heterogénea, conserva más latidos que una ventana fija corta); o ventana fija más larga solo donde existe (p. ej. `[180,480]` en la era ECG), aceptando dos definiciones. Ninguna garantiza haber eliminado un transitorio fisiológico.
- La decisión no puede tomarse solo con concordancia: haría falta un criterio externo (sesiones, carga, sueño) para saber qué versión del gate acierta más.

### 14.5 Defecto operativo encontrado

`find_rr_files()` (`build_hrv_core.py:804–810`) busca `*_RR.csv|*_RR.CSV|*_rr.csv`. Dos ficheros del zip de 2025-10 se llaman `…_RR (1).CSV` y, si se extraen con ese nombre, quedan fuera del reproceso. En el replay se renombraron en la copia de trabajo. **Corrección 2026-10-21:** coinciden RMSSD, HR y Calidad, pero no todos los valores: el reproceso obtiene `Stability_Subtype`, `tail_mismatch_pct`, `SI_baevsky`, `SD1`, `SD2` y `SD1_SD2_ratio` donde el CORE guardado tenía vacíos. Por ejemplo, `SD1` pasa de vacío a 40,77 y 41,59 respectivamente. No procede declarar ausencia de error ni paridad completa. La extracción del replay debe normalizar los nombres en la copia y conservar el origen y la huella, sin alterar los RR originales.

### 14.6 Variante E: inicio fijo a 180 s, fin al final del registro

Brazo `H4e` de `run_arm.py`: solo cambia `t_start_eff = 180.0` en ambas rutas; tramo `[180, t_end_eff]`; cola (últimos 120 s del registro) y `Calidad` vigentes. Comparable con H4w (ventana `[180,360]`, `Calidad` vigente).

| Brazo | Tramo mediano (p5) Polar | Tramo mediano (p5) ECG | SD día a día Polar / ECG | `SWC_ln` Polar / ECG |
|---|---|---|---|---|
| C | 314 s (107) | 364 s (123) | 0,194 / 0,218 | 0,122 / 0,110 |
| H4w `[180,360]` | 179 s (179) | 179 s (179) | 0,204 / 0,217 | 0,116 / 0,121 |
| **H4e `[180, fin]`** | **203 s (179)** | **315 s (299)** | **0,191 / 0,217** | 0,116 / 0,114 |

| vs C | H4w | **H4e** |
|---|---|---|
| lnRMSSD OK en ambos: sesgo | −0,003 | −0,009 |
| Límites de concordancia | −0,132..+0,127 | **−0,095..+0,078** |
| d de Cohen / d_z | −0,008 / −0,039 | −0,029 / −0,200 |
| `STAB_LAST2_MISMATCH` (C = 33) | 9 | 28 |
| Calidad `FLAG`→`OK` / `OK`→`FLAG` | 27 / 6 | 14 / 10 |
| Días con cambio de `gate_final` (2026 / últimos 90 registros) | 80 (49 / 20) | **59 (33 / 16)** |
| ROJO total (C = 124) | 97 | 107 |

Lectura:

1. **Dentro de la era ECG, la variante E ya es casi homogénea**: tramo de 299–315 s (p5–mediana), porque las grabaciones tienen duración estable. La heterogeneidad que queda está **entre eras** (≈203 s frente a ≈315 s), no día a día dentro de la serie que hoy alimenta el gate [confianza 85%].
2. Usa más latidos que `[180,360]` y no empeora la SD día a día; en la era Polar es la mejor de las tres (0,191).
3. Produce 28 flags `STAB_LAST2_MISMATCH` frente a 33. La proximidad de tasas no demuestra que detecte los mismos problemas ni valida el umbral del 15% para la nueva geometría; falta revisar discordancias y sensibilidad. No se propone recalibrarlo solo para igualar tasas.
4. Cambia el gate en 59 días, menos que H4w (80). Sigue habiendo menos ROJO (124 → 107) y un sesgo sistemático pequeño (−0,009; d_z −0,20), coherente con excluir el transitorio inicial: el nivel de lnRMSSD baja algo y el baseline lo acompaña.
5. Lo que no resuelve: la diferencia de longitud entre eras y los registros cortos de 2025 (p5 de 179 s, igual que H4w). Tampoco hay criterio externo para saber qué versión del gate acierta más.

**Valoración corregida:** E conserva más latidos y muestra mayor concordancia con C que `[180,360]` en este replay. No elimina el detector: este sigue ejecutándose y condicionando `Calidad`. Tampoco demuestra eliminar un transitorio ni mejorar la precisión fisiológica. E queda como candidata exploratoria; este brazo no incluye HG-03 y no valida el diseño combinado final.

### 14.7 Elección del inicio en la variante E — regla preregistrada (2026-10-21, escrita antes de ver resultados)

Ninguna justificación previa de los 180 s es válida para la variante E (§10.1 retirada por solape; §12 punto 4 solo aplicaba a la ventana `[180,360]`). Se barre el inicio `s ∈ {60, 90, 120, 150, 180, 210, 240, 270, 300}` s con tramo `[s, t_end_eff]`.

Métricas por `s` (pares originalmente consecutivos; filtros vigentes):

- **Sesgo residual**: lnRMSSD`[s, t_end_eff − 120]` − lnRMSSD`[t_end_eff − 120, t_end_eff]` (disjuntos), en registros con al menos 60 s en el primer segmento. Mediana con IC95 bootstrap.
- **Dispersión entre días del sesgo**: SD robusta del sesgo residual, comparada con un nulo tardío `[t_end_eff − 240, t_end_eff − 120]` vs `[t_end_eff − 120, t_end_eff]` en los mismos registros, con IC95 bootstrap de la diferencia.
- **Ruido interno del tramo**: SD robusta de (mitad 1 − mitad 2)/2.
- **Cobertura**: tramo ≥ 120 s, por era.

**Regla de decisión:** el **menor** `s` que cumpla a la vez:

1. |mediana del sesgo residual| ≤ 0,03 (≈3%), **en ambas eras por separado**;
2. el límite superior del IC95 de [SD del sesgo − SD del nulo] ≤ 0,03;
3. en la era Polar, tramo ≥ 120 s en ≥ 95% de los días.

Si ningún `s` cumple los tres, se informa y no se elige. Los umbrales (0,03 y 120 s / 95%) son una propuesta operativa, no un valor fisiológico validado. Después, los dos o tres `s` mejor situados se pasan por el replay completo para medir el impacto sobre el gate (sin que ese impacto entre en la regla).

### 14.8 Resultado del barrido (2026-10-21)

Script `research/scripts/hg04_start_sweep.py`. Salida (sesgo residual = lnRMSSD`[s, t_end_eff−120]` − lnRMSSD`[t_end_eff−120, t_end_eff]`):

| s | Era | Sesgo mediano [IC95] | SD sesgo − SD nulo [IC95] | Ruido interno | Tramo ≥ 120 s | n |
|---|---|---|---|---|---|---|
| 150 | Polar | +0,049 [+0,039, +0,070] | −0,020 [−0,033, −0,004] | 0,054 | 100% | 278 |
| 150 | ECG | +0,041 [+0,025, +0,057] | −0,006 [−0,032, +0,020] | 0,054 | 100% | 216 |
| 180 | Polar | +0,041 [+0,026, +0,056] | −0,009 [−0,031, +0,003] | 0,058 | 99,3% | 269 |
| 180 | ECG | +0,036 [+0,013, +0,053] | −0,013 [−0,038, +0,012] | 0,056 | 100% | 216 |
| **210** | Polar | **+0,024** [−0,002, +0,060] | −0,011 [−0,040, +0,018] | 0,059 | 99,3% | **123** |
| **210** | ECG | **+0,024** [+0,012, +0,040] | −0,018 [−0,039, +0,007] | 0,052 | 100% | 216 |
| 240 | Polar | +0,008 [−0,015, +0,044] | −0,001 [−0,022, +0,023] | 0,071 | 96,1% | 119 |
| 240 | ECG | +0,012 [−0,001, +0,038] | −0,000 [−0,020, +0,016] | 0,057 | 100% | 216 |
| 270 | Polar | +0,002 | — | 0,072 | **43,8%** | 117 |

(60, 90 y 120 s: sesgo +0,048 a +0,079, no cumplen el criterio 1; 300 s: no cumple 2 ni 3.)

**Resultado de la regla preregistrada: s = 210 s** (210 y 240 cumplen los tres criterios; se elige el menor).

Debilidades de este resultado, identificadas después de verlo:

1. **Muestra Polar sesgada a partir de 210 s.** El primer segmento `[s, t_end_eff−120]` debe medir ≥ 60 s; en los registros cortos de 2025 (`t_end_eff` ≈ 381 s) eso deja de cumplirse a 210 s y n cae de 269 a 123. El criterio 1 de la era Polar se evalúa a 210 s solo en registros largos, **no en los cortos que dominan el periodo `healthy`**. No verificado que el sesgo de los registros cortos sea similar.
2. **El criterio 2 discrimina poco entre los candidatos principales**, pero no se cumple en todos los `s`: falla a 300 s. Sigue afectado por las limitaciones del nulo señaladas en §13.3.
3. **La era ECG cumple el criterio 1 por la estimación puntual (+0,024), no por el intervalo** (IC95 hasta +0,040). La regla se escribió sobre la mediana, y se aplica tal cual.
4. 180 s falla el criterio 1 por poco (+0,041 / +0,036 frente a 0,03).

Replay completo (vs C; `Calidad` vigente; cola de los últimos 120 s):

| | H4e (180) | **H4e210** | H4e240 |
|---|---|---|---|
| Tramo mediano (p5) Polar / ECG | 203 (179) / 315 (299) | 173 (149) / 285 (269) | 143 (119) / 255 (239) |
| SD día a día Polar / ECG | 0,191 / 0,217 | 0,196 / **0,212** | 0,217 / 0,216 |
| `SWC_ln` Polar / ECG | 0,116 / 0,114 | 0,121 / 0,115 | 0,126 / 0,114 |
| Sesgo / LoA (OK en ambos) | −0,009 / −0,095..+0,078 | −0,014 / −0,107..+0,078 | −0,019 / −0,118..+0,079 |
| `STAB_LAST2_MISMATCH` (C = 33) | 28 | 26 | 17 |
| Días con cambio de gate (2026 / últimos 90 registros) | 59 (33 / 16) | **51 (27 / 15)** | 60 (30 / 14) |
| ROJO (C = 124) | 107 | **117** | 114 |

Lectura: 210 s es el que menos altera el gate y el que menos reduce los ROJO; la SD día a día es prácticamente igual a la de 180 s. 240 s empeora la era Polar (tramo 143 s, SD 0,217) y altera el flag de estabilidad.

**Valoración corregida:** la regla exploratoria elige 210 s, pero no demuestra que sea fisiológicamente mejor que 180 s ni que deba descartarse un inicio anterior. El argumento Polar descansa en una submuestra distinta y la referencia tardía no está validada. Aunque los recuentos frente a C sean 59, 51 y 60, hay **34 días con gates distintos entre E180 y E210**, y otros **34 entre E210 y E240**. No es correcto describir la diferencia como pequeña en todas las métricas. Se retiran las confianzas anteriores de 55–60% y 80% sobre el inicio adecuado.

### 14.9 Alcance de las correcciones y reproducción (2026-10-21)

`python research/experiments/hg04_replay/scripts/analyze.py --saved-only` reconstruye los contrastes directos a partir de los CSV de cambios, comprueba fechas únicas, gates completos y consistencia del control, y guarda `results/review_audit.json`. No reconstruye métricas continuas ni certifica paridad de los outputs ausentes. El modo completo requiere el directorio de trabajo del replay y compara todas las columnas de los cuatro outputs contra producción. Los resultados históricos de `summary.json` no se sustituyen al ejecutar el modo de auditoría guardada.

Verificación de la corrección documental original: auditoría guardada ejecutada (26/36/34/34 cambios directos), script de mismatch ejecutado (485 registros principales y 484 en cohorte disjunta) y cinco tests de regresión superados. La extracción normaliza automáticamente sufijos `_RR (n).CSV` en la copia de trabajo, preserva origen/huella y rechaza colisiones de contenido. **Actualización 2026-10-21:** se reconstruyeron C y H3 en una nueva copia aislada y se comprobaron los cuatro CSV completos; C tiene las excepciones descritas en §14.1. Este nuevo H3 usa índices originales y mínimos de pares, mientras que los recuentos históricos de §14.2 proceden del brazo anterior basado en tiempos: que ambos den 18 cambios de gate no demuestra identidad de todos los valores. El nuevo replay H3 queda detallado en [el informe de control](../../research/reports/hg03_hg04_control_replay_2026-10-21.md).

Los recuentos originalmente llamados «últimos 90 días» se calcularon sobre los **últimos 90 registros**; así deben leerse las tablas históricas. El analizador distingue ahora ambos conceptos. La dispersión de mitades y la SD entre días son estadísticas descriptivas que incluyen variación fisiológica; no estiman por sí solas el error de medición. En §14.7–14.8, «sesgo residual» significa diferencia del segmento anterior a la cola respecto de la cola, **no** sesgo de toda la ventana E respecto de una verdad conocida. Registrar una regla antes de un barrido local no equivale a una validación prospectiva independiente.

---

## 15. Copias paralelas del histórico: HG-03, HG-03 + 90 s, HG-03 + 120 s (2026-10-22)

Informe detallado de las seis copias (qué es cada una, cómo se construyó, verificaciones y análisis): [Copias demostrativas del CORE 2026-10-22](../../research/reports/hg04_copias_demo_core_2026-10-22.md).

Petición del usuario: CORE paralelos con inicio fijo para evaluar día a día. Se incluye HG-03 en las copias con inicio fijo porque cualquier versión final la llevará; una copia «solo HG-03» permite separar los dos efectos.

**Método.** Scripts `research/experiments/hg04_replay/scripts/run_parallel.py` (copias) y `compare_parallel.py` (comparación). Copia aislada en la VM; `data/` no se modifica. HG-03 usa la implementación ya presente en `build_hrv_core.py` (`rr_pair_diffs` + `original_idx_eff`) en tramo, Poincaré, cola, `n_pairs_tail` y ventanas del detector, en ambas rutas. Inicio fijo: `t_start_eff = 90/120` en ambas rutas, tramo `[s, t_end_eff]`; la cola (últimos 120 s), el detector (solo informativo) y la regla de `Calidad` quedan como hoy. CORE con 506 filas, 503 con RR.

**Salidas.** Copias completas y tabla día a día en `out/hg04_copias_paralelas_2026-10-22/` (ignorado por git; fuera de `research/` porque `research/AGENTS.md` prohíbe copias completas de datos personales). Agregados en `results/parallel_2026-10-22_summary.json`.

**Verificaciones.**
- Control: reproduce producción en RMSSD, `Calidad`, semáforo y acción en los 506 días. Diferencias solo en 2025-10-07 y 2025-10-14 (SD1, SI, `tail_mismatch_pct`, `Flags`), cuyas filas de producción vienen de una versión antigua del código porque `find_rr_files()` no reconoce `… (1).CSV` (§14.5); en la copia de trabajo se renombran.
- HG-03 por índice original reproduce los valores del replay por tiempos del 2026-10-20 (2026-01-12: 64,5 ms; 2025-09-11: 52,2 ms).
- RMSSD de 10 días (8 al azar + 2026-01-12 y 2025-06-25) recalculado de forma independiente desde los RR para 90 y 120 s: diferencia máxima 7·10⁻¹⁵ ms.

**Resultados (vs control; Bland–Altman de lnRMSSD en días `OK` en ambos):**

| | HG-03 | HG-03 + 90 s | HG-03 + 120 s |
|---|---|---|---|
| Sesgo / LoA (total) | +0,000 / ±0,029 | +0,008 / −0,066..+0,082 | +0,001 / −0,075..+0,076 |
| Sesgo / d_z Polar | −0,000 / −0,03 | +0,005 / 0,14 | −0,002 / −0,07 |
| Sesgo / d_z ECG | +0,001 / 0,08 | **+0,013 / 0,30** | +0,005 / 0,11 |
| Cambios de semáforo (últimos 90 días) | 18 (2) | 55 (13) | 48 (9) |
| Cambios de `Calidad` | 6 | 21 | 20 |
| ROJO (control 124) | 123 | 128 | 128 |
| `STAB_LAST2_MISMATCH` (control 33) | 31 | 36 | 29 |
| `Unstable` (control 46) | 44 | 49 | 42 |

| Copia | Tramo mediano (p5) Polar | Tramo mediano (p5) ECG | SD día a día Polar / ECG | `SWC_ln` Polar / ECG |
|---|---|---|---|---|
| Control | 314 s (107) | 364 s (124) | 0,194 / 0,218 | 0,122 / 0,109 |
| HG-03 | 315 s (118) | 387 s (126) | 0,196 / 0,211 | 0,118 / 0,109 |
| HG-03 + 90 s | 293 s (**269**) | 404 s (**389**) | 0,189 / 0,208 | 0,114 / 0,113 |
| HG-03 + 120 s | 263 s (**239**) | 374 s (**359**) | 0,191 / 0,210 | 0,113 / 0,110 |

**Descomposición de HG-03** (inicio elegido por el detector igual o distinto que en el control): mismo inicio, 454 días, 46 con algún cambio, mediana |Δln| 0, p95 0,014, 14 cambios de semáforo; inicio distinto, 52 días, mediana |Δln| 0,023, p95 0,228, 4 cambios de semáforo. Los cambios grandes en ambos grupos (máximo ≈1,6) son días `INVALID`.

**Lectura** [confianza entre corchetes]:

1. HG-03 sola apenas cambia los días válidos (LoA ±0,03) [90%].
2. El inicio fijo elimina los tramos muy cortos: hoy el 5% de los días se mide con ≤107–124 s porque el detector arranca tarde; con 90/120 s el p5 sube a 239–389 s. Es la mejora de homogeneidad que se buscaba, sin perder latidos en la mediana [85%].
3. La SD día a día baja ligeramente con ambos inicios (Polar 0,194 → 0,189/0,191; ECG 0,218 → 0,208/0,210). Diferencias pequeñas y sin intervalo de confianza: coherentes con menos ruido, no demostradas [55%].
4. A diferencia de `[180,360]` (§14.2), los ROJO no bajan: 124 → 128 en ambos. El cambio de geometría no desplaza la decisión en una dirección [80%].
5. 120 s reproduce mejor el nivel del histórico que 90 s en la era ECG (sesgo +0,005 frente a +0,013). La cifra de §2.2 de la revisión crítica (90 s, sesgo +0,003) era sin HG-03 y en otra cohorte; no es contradictoria pero no aplica tal cual [75%].
6. Ninguna de estas cifras dice qué versión acierta más fisiológicamente (§13.5, criterio externo pendiente).

### 15.1 Copia adicional: HG-03 + 90 s con grabación cortada a 375 s (2026-10-22)

**Motivo.** Evaluar acortar las grabaciones futuras a 375 s. Copia `H3S90T375` en `run_parallel.py`: igual que `H3S90`, más un truncado en `_parse_and_filter_rr` justo después de quitar los `NaN` y antes de calcular `dur_raw`. Se conservan los latidos cuyo tiempo acumulado (incluidos los `offline`) es ≤375 s. Así `dur_raw` ≤375 s, `t_end_eff` ≤360 s, el tramo es `[90, 360]` (≈270 s) y la cola es `[240, 360]`. El `Artifact_pct` se calcula sobre el registro truncado, como pasaría con una grabación real de 375 s. Los registros de ≤375 s no cambian: 11 de 503, todos de la era Polar.

**Alcance del corte.** La duración bruta mediana es 398 s en Polar y 511 s en ECG. El corte apenas toca Polar y elimina ≈136 s por registro en ECG.

**Verificaciones.** `dur_raw` máximo en la copia: 375,0 s. 490 de 506 días difieren de `H3S90`; los 16 restantes son los registros cortos y las fechas sin RR. Se recalcularon a mano 10 días `OK` aleatorios (semilla 375) desde los RR: diferencia máxima de 0 en RMSSD y en FC.

**Resultados** (Bland–Altman solo con días `OK` en ambas copias):

| Comparación | Era | n | Sesgo lnRMSSD | LoA | d_z | Sesgo FC (lpm) | Cambios semáforo | Cambios Calidad | ROJO ref → copia |
|---|---|---:|---:|---|---:|---:|---:|---:|---|
| corte 375 vs Actual | Polar | 228 | +0,013 | −0,070..+0,096 | 0,30 | −0,21 | 35 | 31 | 73 → 77 |
| | ECG | 165 | +0,025 | −0,081..+0,132 | 0,47 | −0,45 | 41 | 43 | 51 → 36 |
| | total | 393 | +0,018 | −0,076..+0,112 | 0,38 | −0,31 | 76 (últimos 90: 23) | 74 | 124 → 113 |
| corte 375 vs HG-03 + 90 s (efecto del corte solo) | Polar | 231 | +0,008 | −0,032..+0,047 | 0,38 | −0,14 | 21 | 24 | 79 → 77 |
| | ECG | 164 | +0,016 | −0,040..+0,071 | 0,55 | −0,32 | 38 | 41 | 49 → 36 |
| | total | 395 | +0,011 | −0,037..+0,059 | 0,45 | −0,22 | 59 (últimos 90: 18) | 65 | 128 → 113 |

| Copia | Tramo mediano Polar / ECG (p5) | SD día a día Polar / ECG | SWC_ln mediano Polar / ECG | SWC_HR mediano Polar / ECG |
|---|---|---|---|---|
| Actual | 314 (107) / 364 (124) s | 0,194 / 0,218 | 0,122 / 0,109 | 1,37 / 1,28 |
| HG-03 + 90 s | 293 (269) / 404 (389) s | 0,189 / 0,208 | 0,114 / 0,113 | 1,43 / 1,19 |
| HG-03 + 90 s corte 375 | 269 (268) / 269 (268) s | 0,193 / 0,199 | 0,116 / 0,115 | 1,43 / 1,30 |

**Calidad.** Frente a Actual: 46 días pasan de OK a FLAG, 25 de FLAG a OK y 3 de FLAG a INVALID. Los 3 nuevos INVALID (2026-06-10, 2026-06-15 y 2026-07-12) se deben a `ART_GT20`: los artefactos del registro pesan más sobre un total menor. Frente a `H3S90`, los flags nuevos en los días que pasan de OK a FLAG son `LAT_NAN` (22), `STAB_LAST2_MISMATCH` (15) y `ART_GT15` (3). `LAT_NAN` sube de 30 a 55 días (ECG: 8 → 29). **[Corregido 2026-10-22]** No es por falta de ventanas (los 22 días afectados conservan 12): el mejor trío consecutivo queda al 10,1% de mediana frente al umbral del 8%, y en el registro completo el detector solo lo encontraba en la parte final (mediana 360 s) que el corte elimina (§15.1.1 y §6.2 del informe de copias). La regla de `Calidad` (`build_hrv_core.py:470-475`) exige `lat` finita para dar OK, aunque con inicio fijo el detector ya no decide el tramo. **Este aumento de FLAG es un efecto de la regla de QA, no de la medición.**

**Mecanismo de los cambios de semáforo** (clasificación en este orden: Calidad del día; aparición o desaparición del veto agudo; cambio de `gate_razon_base60`). Frente a `H3S90`: 35 por cruce del umbral 2D, 19 por Calidad del día y 5 por veto agudo. Frente a Actual: 39, 26 y 11 respectivamente.

**Lectura** [confianza entre corchetes]:

1. Con el corte, todos los registros miden el mismo tramo (≈269 s) en ambas eras: desaparece la diferencia de geometría Polar/ECG (293 frente a 404 s con 90 s sin corte) [95%].
2. Cortar sube de forma sistemática el nivel de lnRMSSD y baja la FC, sobre todo en ECG: +0,016 ln y −0,32 lpm frente a 90 s sin corte. El sesgo es positivo en todos los meses. Por tanto, el tramo eliminado (≈360–500 s) tiene de media un RMSSD algo menor y una FC algo mayor que `[90, 360]`. La causa no está identificada. La postura habitual es supina; no se considera un cambio postural como explicación disponible para estas comparaciones. La respiración se intenta mantener libre, pero no se mide; tampoco se conoce de forma factible el tiempo de reposo previo. Estas limitaciones impiden atribuir el cambio a una causa concreta. Es especulativo [hecho 90%; causa sin evaluar].
3. Frente a Actual, en ECG el desplazamiento es ≈23% de un SWC_ln (+0,025 frente a 0,109) y ≈35% de un SWC_HR (−0,45 frente a 1,28 lpm). Si se acortaran las grabaciones sin recalcular el histórico, durante los 60 días de base el sistema compararía días cortos con una base de días largos. El sesgo empujaría hacia semáforos más favorables. **Recomendación:** si se adopta, recalcular el histórico truncado a 375 s (esta copia lo simula) para que la base sea coherente desde el primer día [80%].
4. La bajada de ROJO en ECG (51 → 36; frente a `H3S90`, 49 → 36, sobre todo en mayo–octubre: 41 → 32) no es una mejora demostrada. Coincide con más días FLAG (que salen del roll-3 y de la base) y con un nivel más alto. No se ha separado qué parte corresponde a cada causa [60% de que sea mayoritariamente artefacto de QA y nivel].
5. La SD día a día en ECG baja (0,208 → 0,199) pese a usar ≈135 s menos de señal. Es compatible con que el final del registro añada variabilidad propia; no está demostrado y no hay intervalo de confianza [50%].
6. **Requisito si se adopta 375 s con inicio fijo:** revisar la regla `LAT_NAN → FLAG`. Con la regla actual, acortar el registro degrada la Calidad en ≈25 días por un detector que ya no decide el tramo [85%].
7. Como en §15, nada de esto dice qué versión acierta fisiológicamente.

#### 15.1.1 Medición del peso de la regla `LAT_NAN → FLAG` (2026-10-22)

Para separar el efecto de la QA del efecto de la medición se añadió la copia `H3S90T375NL`: idéntica a `H3S90T375` quitando solo las dos líneas que fuerzan `FLAG_mecánico` cuando `lat` es `NaN` (`build_hrv_core.py:470-475`); `LAT_NAN` sigue emitiéndose como flag informativo. **Control de paridad:** `RMSSD_stable` idéntico en los 506 días, como corresponde a un cambio que solo afecta a `Calidad`.

| Copia | Días OK | ROJO total | ROJO Polar | ROJO ECG | VERDE |
|---|---:|---:|---:|---:|---:|
| Actual | 439 | 124 | 73 | 51 | 257 |
| HG-03 + 90 s | 434 | 128 | 79 | 49 | 256 |
| HG-03 + 90 s corte 375 | 418 | 113 | 77 | **36** | 265 |
| HG-03 + 90 s corte 375 sin la regla | **454** | 123 | 81 | **42** | 256 |

En `H3S90T375` el detector falla en 55 días (30 en `H3S90`; en ECG 29 frente a 8) y en 45 de ellos eso baja la Calidad; en 22 es el único motivo (estabilidad `OK`, `Artifact_pct` ≤15). **[Corregido 2026-10-22]** La explicación anterior —«falla porque con 375 s hay menos ventanas de 60 s donde encajar y el *fallback* calcula su mediana con menos ventanas»— es falsa: los 22 días conservan 12 ventanas, 11–12 válidas, y el *fallback* podía ejecutarse. Reconstruido el detector sobre los RR truncados, el mejor trío consecutivo queda al 10,1% de mediana frente al umbral del 8% (`build_hrv_core.py:378-415`): **el criterio es más estrecho que la variabilidad natural del RMSSD entre ventanas de 60 s**. Sobre el registro completo, esos 22 días sí encuentran latencia (mediana 360 s; 21 de 22 por encima de 300 s; 9 más allá de 360 s), es decir, su único trío que cumple el 8% está en la parte final que el corte elimina. Detalle, datos a favor y en contra de tocar la regla, y la prueba pendiente que lo resolvería: §6.2 y §6.3 del [informe de copias](../../research/reports/hg04_copias_demo_core_2026-10-22.md).

Lecturas [confianza entre corchetes]:

1. **La caída de ROJO en ECG era en parte artefacto de la QA.** De los 13 ROJO que desaparecen (49 → 36 frente a `H3S90`), ≈6 vuelven al quitar la regla (42). Esto precisa la lectura 4 de §15.1, que atribuía la caída «mayoritariamente» a la QA y al nivel con un 60%: aproximadamente la mitad es regla de QA y la otra mitad desplazamiento de nivel [80%].
2. **Quitar la regla no estabiliza el semáforo:** los cambios frente a `H3S90` pasan de 59 a 58, pero 38 días difieren entre `H3S90T375` y `H3S90T375NL`. Cambia *qué* días se mueven, no cuántos. El argumento para quitarla es de coherencia (no penalizar la Calidad por algo que ya no entra en el cálculo), no de estabilidad [90%].
3. Sin la regla quedan 35 días `FLAG`: 30 por `STAB_LAST2_MISMATCH`, 3 por `ART_GT15` y 3 por `STAB_TAIL_SHORT`. Son los motivos que la regla pretendía cubrir [95%].
4. No se propone tocar esta regla por separado, ni eliminarla sin sustituto: forma parte de la misma decisión que la ventana, pendiente de criterio externo (§13.5). Lo establecido es que **con el código vigente, acortar a 375 s degrada la Calidad de ≈22 días por un motivo que con inicio fijo ya no afecta al cálculo** [85%]. Que esos 22 días sean efectivamente datos buenos es menos seguro: `LAT_NAN` correlaciona con registros menos estacionarios en el control (`tail_mismatch` >15% en el 18% de esos días frente al 6%; `Unstable` 32% frente a 6%), aunque a esos ya los marca `STAB_LAST2_MISMATCH` por su cuenta [65%, §6.3 del informe].

Un día `FLAG_mecánico` sí recibe semáforo (en `H3S90T375`: 37 VERDE, 14 ÁMBAR, 11 ROJO, 9 NO), pero queda fuera de `is_clean` (`build_hrv_final_dashboard.py:972`) y por tanto fuera del roll-3, de la base de 60 días y del SWC: marcar un día altera la referencia de los ~60 días siguientes.

**Salida actualizada el 2026-10-23:** en la hoja `90s vs corte 375s` del Excel se añadieron cálculos a las 506 filas diarias. El bloque Z:CC (56 columnas) compara 90 s con el corte a 375 s. El bloque CD:DS (42 columnas) incorpora `H3S90T375NL`, sin la penalización `LAT_NAN → FLAG`, junto al corte con QA vigente. Muestra Calidad, Flags, semáforo, acción, RMSSD/FC diario y de gate, fechas del roll-3, vetos, medias descriptivas de 30/60 días, Base60 operativa, `d_ln`/`d_HR` y tamaños de muestra. Las columnas «común» comparan solo fechas que tienen Calidad OK en ambos brazos de esa comparación, para separar el cambio de valor del cambio en selección por Calidad. Las medias descriptivas son aritméticas sobre los días limpios previos; no sustituyen la mediana que usa la base operativa.

En las 506 fechas, `H3S90T375NL` conserva el RMSSD y la FC diarios del corte; cambia solo la política de Calidad y sus efectos posteriores. Frente al corte con QA vigente, cambian 36 etiquetas de Calidad y 38 semáforos. `LAT_NAN` queda como flag informativo. Esta variante sigue siendo una comparación exploratoria, no un cambio aprobado.

El 2026-08-31 ilustra esa diferencia: entre 90 s y el corte, el RMSSD diario redondeado es 37,5 ms en ambas versiones y la FC difiere 0,2 lpm, pero la señal móvil del gate es 40,84 frente a 46,27 ms. Sus tres fechas limpias no coinciden. En las medias propias de cada versión, el RMSSD cambia +0,77% a 30 días y −0,32% a 60 días; sobre las mismas fechas OK en ambas, cambia +2,74% y +1,91%. En este caso, la composición del grupo cambia la lectura de la media. Es un ejemplo puntual, no un patrón general ni una prueba de cuál ventana es más válida. La descripción del Excel incluye los cálculos nuevos y conserva los cambios agregados ya auditados: 59 semáforos y 65 calidades entre 90 s y el corte.

Limpieza aplicada el 2026-10-20: §9.1, §9.5 y el párrafo final alineados con la decisión 180/180; referencias de línea actualizadas; inventario de `data/rr_downloads` actualizado en §6; clasificación por origen marcada como errónea (inicio del documento y §6), pendiente de recálculo.

### 14.10 Replay de inicios tempranos con HG-03 (2026-10-21)

Se ejecutaron en copia aislada los inicios fijos 0/60/90/120 s con final `t_end_eff`, cola y regla actual de `Calidad`, solos (`E*`) y con pares originales (`H3E*`). El [protocolo previo](../../research/reports/hg04_early_windows_protocol_2026-10-21.md), el [informe técnico](../../research/reports/hg04_early_windows_replay_2026-10-21.md) y [los agregados reproducibles](../../research/experiments/hg04_replay/results/early_window_2026-10-21.json) separan resultados de interpretación. Hay 501 RR y una cohorte común de 303 días `OK` con lnRMSSD finito en C y los ocho brazos tempranos; las tres fechas sin RR no cuentan como cambios.

| Inicio | Gates distintos de C sin/con HG-03 | Flags `STAB_LAST2_MISMATCH` sin/con HG-03 | Mediana de ventana disponible |
|---|---:|---:|---:|
| 0 s | 158 / 99 | 173 / 105 | 485 s |
| 60 s | 73 / 65 | 69 / 53 | 425 s |
| 90 s | 62 / 55 | 45 / 36 | 395 s |
| 120 s | 53 / 48 | 36 / 29 | 365 s |

El control C tiene 33 flags mismatch. En E0, 131 días pasan de `OK` a `FLAG_mecánico`, todos por ese flag; al conservar la calidad del control, E0 aún cambia 75 gates (en vez de 158). Por tanto, el cálculo y la QA contribuyen e interactúan cronológicamente; los recuentos no se pueden restar para atribuir causas. El inicio 0 no queda refutado fisiológicamente por una regla de mismatch concebida para otra geometría. **Corrección interpretativa 2026-10-21:** en los 303 días comunes, empezar antes eleva sistemáticamente el *nivel agregado* de lnRMSSD: el sesgo frente a C progresa de `+0,048` (E0) a `+0,013` (E60), `+0,003` (E90) y `−0,004` (E120). E0 es mayor que C en 258 días y menor en 45; reducirlo a «diferencias en ambos sentidos» ocultaba el patrón. E90 casi reproduce el nivel medio actual (43,58 frente a 43,48 ms de RMSSD aritmético), pero no es equivalente por día ni en el gate (62 diferencias); la correlación alta tampoco lo demuestra. Los límites Bland–Altman para E0/E60/E90/E120 son `−0,052..+0,149`, `−0,053..+0,080`, `−0,058..+0,064` y `−0,066..+0,058`, respectivamente. Este gradiente no identifica por sí mismo el inicio fisiológicamente más válido.

La sensibilidad posterior 180 → final cambia 59 gates sin HG-03 y 61 con él; `[180,360]` con la calidad vigente cambia 80 en ambos casos. Ambas geometrías dejan menos de 180 s disponibles en 11 días, y `[180,360]` mantiene siete de esos días como `OK`: necesita una salida explícita para ventana insuficiente. Cuatro días con menos de 20 pares válidos bajo todos los inicios tempranos ya eran `INVALID` en C. Este resultado no aprueba 90, 120 ni 180 s por cercanía al gate anterior. **La decisión sobre ventana y QA sigue abierta** hasta disponer de un criterio externo predefinido y de una política para registros cortos; el 15% vigente no se ajusta para reproducir su tasa histórica.
