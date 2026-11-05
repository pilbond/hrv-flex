# HG-10: corte histórico y contrato de pares RR consecutivos

**Actualización 2026-11-05:** generación HG-10 publicada en el `data/` local de `hrv-flex`, tras 758 pruebas y ensayo de recuperación. CORE/FINAL tienen 19/67 columnas; el sync normal acepta la geometría. Railway no se ha migrado en este corte. El informe y respaldo están en [validación y corte local](<HG-10 Validacion y corte local 2026-11-05.md>). Los estados «pendiente» que siguen documentan decisiones anteriores al corte.

**Artefactos del tramo HG-10 (candidata v2, 03/11/2026).** CORE y FINAL añaden `rejected_rr_pct_window` junto a `Artifact_pct`. El primero es el porcentaje de RR rechazados entre todos los RR cuyo instante final está entre 90 s y el final útil inclusive. Se aplican los descartes del filtro original antes de seleccionar el tramo. Sin RR en el tramo, el porcentaje queda vacío. Calidad y los flags de artefactos usan el porcentaje local: más de 15 % impide OK y más de 20 % implica INVALID. El global sigue describiendo el registro truncado y ponderando la varianza de SSM. FINAL identifica la métrica local en el motivo de calidad cuando recibe el nuevo esquema.

Regla adoptada en candidata. La ejecución aislada en out/hg10_verif_art_v2__zz2385i/ reproduce las decisiones del ensayo en 513 fechas y el SSM shadow completo (541 fechas de calendario). Pendiente preparar y ensayar publicación y recuperación. Los apartados previos a la adopción documentan el histórico de decisiones.

**HG-10 · Política B adoptada para la rama candidata (03/11/2026), pendiente de migración.** Esta decisión actualiza HG-09 §9 para la candidata. CORE conserva `LAT_NAN` como diagnóstico y concede `OK` si se cumplen todos los demás requisitos. FINAL aplica su elegibilidad y acción ordinarias. SSM admite la observación con `LAT_NAN` si la fila es `OK` y mantiene ausentes los casos combinados. El manifiesto CORE registra `QUALITY_POLICY_VERSION=hg10_latnan_aviso_art_window_v2`. El sync exige que la versión coincida. Las referencias anteriores al veto corresponden a la política previa.

Verificación sobre la cohorte congelada de 508 fechas: CORE y DASHBOARD reproducidos por valores; diferencias numéricas inferiores a 4 × 10⁻¹⁴ en derivados. El CORE operativo a 03/11 tiene 516 fechas. Las cifras 36/38/56 corresponden a la cohorte congelada. Las discusiones siguientes conservan el historial de la decisión.

**Corrección visible:** esta consolidación sustituye las conclusiones anteriores que
afirmaban que no había alternativa a LAT_NAN, que el reanclaje no podía ser un artefacto,
que el muestreo había agotado toda mejora y que el efecto era igual en ambas geometrías.
También retira la propuesta de enviar ese hallazgo a una tarea nueva y las recomendaciones
automáticas de bloquear o publicar. La versión anterior está preservada en
`out/hg10_correccion_2026-10-28/previo/`.

## Alcance y decisión vigente

HG-03 preparó la procedencia física de los RR; HG-04 propuso inicio fijo en 90 s, corte
máximo en 375 s y recorte final de 15 s. El final útil es el tiempo del último RR incluido
menos 15 s: aproximadamente 360 s, no necesariamente 360 s exactos.

HG-09 §9 decidió conservar la exclusión y cautela de LAT_NAN y STAB_LAST2_MISMATCH. Los
resultados contrafactuales de políticas alternativas no constituyen una autorización para
implantarlas. La fase añadida de HG-10 evalúa su adecuación, sin cambiar la política activa.

**Implementación real de HG-09 §9.** HG-09 no añadió un módulo de política:
conservó reglas preexistentes. `build_hrv_core.py` convierte `LAT_NAN` y
`STAB_LAST2_MISMATCH` en `FLAG_mecánico` (el segundo pasa por `Unstable`).
`build_hrv_final_dashboard.py` solo admite `Calidad == "OK"` para roll-3,
base60 y SWC; por ello excluye ambos flags sin reconocerlos por nombre.
`build_hrv_ssm.py` sí reconoce `LAT_NAN` por nombre y lo trata como
observación ausente. Un `MISMATCH` aislado entra en el SSM shadow con
varianza penalizada: +1,5 por `FLAG_mecánico` y +1,0 por estabilidad no `OK`.
Esta diferencia entre FINAL y SSM no contradice HG-09, pero «conservar la
política» implica mantener dos tratamientos operativos distintos.

No se ha adoptado una modificación del detector ECG, de la fusión de RR de HG-07/08, de
los umbrales ni de la elegibilidad. La eventual propuesta deberá aportar evidencia y una
decisión explícita, además de implementación, pruebas y actualización contractual.

## Implementación y replay

- RMSSD de ventanas, tramo, cola y rescate, y SD1, usan pares físicamente consecutivos.
  Mínimos: 20 pares en ventanas, 60 en cola y 10 RR/9 pares para Poincaré. SD2 se conserva.
- Tramo desde 90 s; corte a 375 s antes del recorte final; límites inclusivos. Artifact_pct
  se calcula sobre el registro truncado, manteniendo los umbrales 15 %/20 %.
- REC_SHORT, WIN_NO_PAIRS y TIME_AXIS_UNRELIABLE impiden OK cuando no hay medición
  utilizable. No fuerzan INVALID por sí solos. El filtro delta-RR se conserva.
- Una cola con menos de 60 pares marca Unstable; su RMSSD numérico se conserva si hay
  al menos un par. La contradicción antigua con el contrato ya quedó corregida.
- GEOMETRY_VERSION viaja al manifiesto. Contratos distinguen candidato y desplegado.

[Replay](../../research/reports/hg10_replay_2026-10-27.md): 508 fechas con RR, frente a
511 filas de CORE. OK pasa de 442 a 422; cambian 78 gates y 103 acciones. Artifact_pct
cruza seis umbrales. Sesgo lnRMSSD −0,0056, límites de concordancia [−0,382; +0,371].
Son medidas de impacto, no de acierto. El control reproduce las columnas de cálculo;
las discrepancias ANS en dos fechas y BETA en seis son anteriores a HG-10.

La verificación del 27/10 registró reproducción de los cuatro brazos. La revisión del
28/10 comprobó 16/16 archivos contra sus manifiestos y ejecutó 97 pruebas de CORE,
FINAL, estado/orquestación, manifiestos y HG-10: todas pasan, en Python 3.13.3 local.
Esta última comprobación no se presenta como una nueva ejecución completa de los brazos.
El contraste con HG-04 coincide en RMSSD y Calidad sobre 503 fechas comunes.

## Qué sabemos sobre Calidad

La implementación aplica la política vigente. El requisito de latencia es
**binario** con esta duración: `max(lat, 60)` garantiza el límite inferior y
el detector no alcanza el superior de 600 s; el rango no excluye ninguna
latencia finita posible. La comprobación de `NaN` aparece tanto en flags como
en el predicado de `OK`.
LAT_NAN expresa que el detector no encontró su meseta; no es una medida directa de
calidad eléctrica ni una prueba de error de RMSSD.

Los 36 días LAT_NAN como único motivo de FLAG coinciden con HG-04. Los 22 nuevos de HG-04
y los 26 de HG-10 usan controles distintos; los 22 están contenidos en los 26. El efecto
era conocido, no un problema nuevo descubierto por el replay de HG-10.

Los escenarios A/B/C de [Calidad](../../research/reports/hg10_calidad_latnan_2026-10-27.md)
cuantifican las consecuencias de admitir esos días. No validan su exactitud. Las diferencias
de defectos técnicos tienen intervalos amplios que incluyen cero; no demuestran igualdad
ni ausencia de capacidad discriminativa. La decisión actual es conservadora y no está
validada como la mejor política.

**Decisión pendiente sobre `LAT_NAN`.** La alternativa conceptual más simple
es tratar `LAT_NAN` aislado como aviso y mantener la cautela cuando coincide
con otro defecto del tramo. No es un interruptor existente: si CORE cambia
`Calidad` a `OK`, FINAL lo incorpora automáticamente a referencias y cálculos,
pero SSM seguirá descartándolo por el flag nominal. La otra vía separa
elegibilidad y cautela con campos/reglas distintos, opción propuesta en HG-09
§7 y no adoptada en §9. Ambas vías requieren implementación, contratos,
pruebas y replay de CORE, FINAL y SSM. Si se decide antes del corte HG-10,
pueden integrarse en una sola migración; si se aplaza hasta después, habrá
un segundo recálculo histórico. Es una candidata de política, no una regla adoptada. Con
inicio fijo a 90 s, la ausencia de meseta no impide por sí misma medir el tramo.
La Calidad del tramo puede examinar pares físicamente consecutivos, descartes,
cobertura/huecos y estabilidad de sus partes y su cola. Ninguna comprobación
certifica cada pico ECG; los indicadores automáticos de señal ensayados tampoco
han demostrado ser un sustituto de `LAT_NAN`. No se exige certeza absoluta:
hay que estimar si los días con `LAT_NAN` aislado tienen más errores de RMSSD
relevantes que controles comparables. No detectar una diferencia no demostraría
equivalencia. **[Actualizado 2026-11-02]** El control barato de repetibilidad ya se ha
medido y la etiqueta falla como diagnóstico técnico estable: véase
«Robustez de `LAT_NAN`» más abajo. Los efectos por fecha en referencias, gates y
acciones de los brazos ya calculados están contrastados allí; el brazo que admite los 36
días cambia 38 gates. HG-09 §9 sigue vigente hasta una decisión.

## Robustez de `LAT_NAN` — 2026-11-02

[Informe](../../research/reports/hg10_latnan_robustez_2026-11-02.md),
[protocolo previo](../../research/reports/hg10_protocolo_latnan_robustez_2026-11-02.md)
y [enmienda descriptiva](../../research/reports/hg10_protocolo_latnan_robustez_enmienda1_2026-11-02.md).
Copias aisladas; no cambia `data/`, detector, umbrales ni HG-09 §9.

**Reproducibilidad.** La cadena ECG→RR→CORE es determinista: 230/230 grabaciones idénticas
en dos procesos; el RR operativo guardado coincide con el regenerado en 27/27 fechas.

**Robustez.** Nueve variantes preregistradas: fase de la rejilla de latencia (5, 10, 15, 20
y 25 s; solo procedimiento), descartar el primer o los dos primeros latidos, fiducial
refinado B y ECG truncado a 380 s. En las 50 grabaciones de referencia, **las 23 `LAT_NAN`
obtienen latencia finita con alguna variante** (17 solo con perturbaciones de entrada) y
6/27 latencias finitas pasan a `LAT_NAN`. Clase preregistrada: **no robusto, no frágil**.
Se replica en las 230 grabaciones ECG (P1 74 %, P2 30 %) y en la era sin ECG (15 de 16
días aislados). En total, **35 de los 36 días con `LAT_NAN` aislado del CORE candidato
pierden el flag** con alguna variante. Truncar el ECG fuera del registro no cambia ninguna
etiqueta (control negativo).

**Mecanismo.** Los días `LAT_NAN` tienen material completo (11–12 de 12 ventanas, artefactos
~0,6 %); su mejor terna falla el 8 % por una mediana de 1,8 puntos, cuando los días `OK`
quedan en ~4 %. Es un corte duro sobre un estadístico continuo. Ante las mismas
perturbaciones, `LAT_NAN` cambia 8–15 veces más que `STAB_LAST2_MISMATCH`. El RMSSD de esos
días no es más sensible que el de los `OK` (cociente 0,97; IC95 0,41–1,84). Todas las
discrepancias A/HRVanalysis/B de `LAT_NAN` se reproducen sin HRVanalysis.

**Lo que no dice.** Que el RMSSD de esos días sea exacto, ni que un margen amplio carezca de
información: las grabaciones con margen ≥15 % fueron las más estables (observación
posterior, sin umbral validado).

**Opciones** (escenarios ya calculados sobre 508 fechas):

| | Mantener | B: aviso | C: elegible con cautela |
|---|---|---|---|
| `OK` | 422 | 458 | 458 |
| Gates / acciones distintos frente a mantener | — | 38 / 56 | 38 / 27 |
| CORE | nada | quitar la condición de latencia finita | igual que B |
| FINAL | nada | nada | máscara de cautela nueva que lee `Flags` |
| SSM | nada | quitar `LAT_NAN` de `obs_missing` | igual que B |

B y C caben en la **misma migración** si se deciden antes de publicar; exigen versionar la
política de Calidad en el manifiesto y en la protección, que hoy solo verifica geometría.

**Lo que permiten los datos, según la regla preregistrada:** flexibilizar `LAT_NAN` aislado
a aviso (B). C es la alternativa conservadora. **No se ha adoptado**; requiere decisión
explícita del usuario, implementación, contratos, tests y replay combinado.
Las opciones de flexibilización, con su efecto y cambios de código, están en
[§8.1 del informe](../../research/reports/hg10_latnan_robustez_2026-11-02.md); el veto por
margen amplio y el consenso de fases quedan fuera por no estar evaluados.

## Ensayo histórico de la política B de `LAT_NAN` — 2026-11-03

[Informe](../../research/reports/hg10_latnan_politica_b_2026-11-03.md). Dos brazos en copia
aislada sobre las 508 fechas, con los mismos RR fijados por nombre y huella, la geometría
candidata, los pares consecutivos y el detector ECG actual. Única diferencia: la política
de `LAT_NAN` (un cambio de una línea en CORE y otro en SSM; FINAL sin tocar).

- **Control:** CORE idéntico bit a bit al replay PG; FINAL idéntico en decisión, referencias
  y acción (solo cambia `reason_text` del 2026-10-27, por `sessions_day` posterior). SSM
  determinista; sin referencia previa.
- **B frente a control:** 36 días `FLAG_mecánico` → `OK` y ninguna otra columna de CORE ni
  BETA_AUDIT; 38 semáforos (8 propio día, 30 arrastre), 56 acciones (29 / 27), 21 promovidos
  a `INTENSIDAD_OK`, ROJO 113 → 123, veto 77 → 88. Todas las cifras de control coinciden.
- **SSM:** entran exactamente las 36 observaciones promovidas y los 6 combinados siguen
  ausentes. Estado de recuperación: cambio mediano 0,028 ln en los días admitidos (máx.
  0,140, 2025-09-26) y 0,004 ln en los posteriores (máx. 0,088, 2025-09-21); se disipa en
  2–3 días. La incertidumbre baja siempre.

**Lectura:** el efecto medido es el previsto y está acotado. Que las acciones de B sean más
acertadas no se puede saber sin desenlace externo. Si se adopta, debe entrar en la misma
migración y con la política de Calidad versionada. **No adoptado**; HG-09 §9 sigue vigente.

## Fase ECG/RR: resultado corregido

[Informe actualizado](../../research/reports/hg10_calidad_ecg_confirmatorio_2026-10-28.md),
[revisión crítica](../../research/reports/hg10_revision_critica_2026-10-28.md),
[protocolo con enmienda](../../research/reports/hg10_protocolo_calidad_ecg_2026-10-27.md) y
[primer informe de la fase](../../research/reports/hg10_calidad_ecg_rr_2026-10-27.md),
conservado con su anotación de superado.

Se recuperaron 40 ECG, conservando las 20 parejas y los identificadores ciegos. Duraciones
RR y flags offline reproducen los archivos originales en 40/40. Esto prueba integridad,
no exactitud del detector. El desfase ECG→CORE es reconstruible.

El ensayo corregido usa el parser real, verifica el baseline y compara los mismos pares
físicos. El máximo desacuerdo por reanclaje sigue siendo **55,06 %**, mediana absoluta
**3,17 %**. En los 16 registros del agrupamiento exploratorio de desplazamiento alto,
la mediana con signo es +28,45 %. No prueba que el RMSSD publicado sea incorrecto ni
que el alternativo sea mejor. La referencia temporal sigue pendiente.

En C también hay sensibilidad (mediana absoluta 3,80 %, máximo 56,80 %), pero no idéntica
por fecha: la diferencia entre cambios relativos alcanza 23,47 pp. No se puede trasladar
una conclusión de exactitud o bloqueo únicamente desde estas cifras.

Los indicadores se calculan sobre el final útil real y se contrastan por parejas. El proxy
amplitud/variación tiene diferencia mediana pareada −3,185, IC95 [−9,578; +2,778], p
unilateral 0,134. No aporta base suficiente para adoptar una regla ni demuestra equivalencia.
La variación entre muestras no es SNR calibrada, los extremos observados no son saturación
ADC y la correlación de plantilla no es una referencia temporal.

**Conclusión:** no hay alternativa de Calidad validada. No se concluye que no exista
porque no separe LAT_NAN de OK. Se retiran las inferencias de independencia del ruido,
suelo irreducible del muestreo y causalidad basadas solo en correlaciones.

## Siguiente comprobación dentro de HG-10

Paquete local: `out/hg10_calidad_ecg_corregida_2026-10-28/revision_temporal/index.html`.
40 visores con muestras originales, zoom, final útil real, detector oculto inicialmente y
exportación de anotaciones por latido con tiempo e incertidumbre. Las láminas de 30 s
anteriores conservan utilidad general, pero no resuelven temporización de pocos ms.

Pendiente: acordar criterio fiducial, precisión, margen relevante de RMSSD y adjudicación
antes de comparar etiquetas; anotar y registrar desacuerdos; evaluar diferencias continuas
y el efecto de incertidumbre. No se presupone una referencia perfecta ni se inventa un
umbral para recuperar días OK. La repetibilidad entre grabaciones sigue sin evaluarse.

## Protección y publicación

CORE exige generación coherente de CORE/BETA/manifiesto, huellas y marca de geometría por
fila. Las fechas 2026-02-26 y 2026-03-03 tienen un único RR cada una, y
2026-02-27 no tiene ninguno; ninguna permite calcular RMSSD. Figuran como
`FLAG_mecánico` y `NO` en el histórico. **Conflicto documental y decisión
abierta:** el replay y `PROCEDIMIENTO_RECOMENDADO.md` exigían conservarlas por
fusión; la revisión del 01/11 propuso omitirlas. La migración no puede tratar
ambas salidas como equivalentes: 508 y 511 filas producen canónicos distintos.
Se prefiere evaluar la omisión con copia de auditoría y replay de derivados,
pero no está aprobada ni ejecutada. Hasta resolverla, no publicar.
`--allow-hg10-migration` requiere un directorio explícito distinto del operativo; el sync
web no lo utiliza. La protección contra mezclar geometrías permanece activa.

La publicación exige un plan de migración que preserve todas las fechas con
medición utilizable, copia de recuperación, huellas y coherencia de la generación. Regenerar y
verificar FINAL, DASHBOARD y SSM shadow; revisar briefs IA fechados y latest derivados de
valores previos. No migrar retroactivamente fuentes Polar a Dropbox ni ejecutar --all
indiscriminadamente en producción.

**Bloqueos de reproducibilidad y operativa detectados el 01/11.** El candidato
en `build_hrv_core.py`, contratos y tests está en el árbol de trabajo de la
rama `desacople`, no en `HEAD`. Por tanto, «control C = HEAD» solo describe el
commit observado en el replay original; debe fijarse su SHA y las huellas de
entrada, no volver a interpretar `HEAD` en futuras corridas. La ruta operativa
`find_rr_files` ordenaba solo por fecha y dejaba sin resolver empates de
ficheros `(1)`; en 2025-10-07 y 2025-10-14 podía ganar un RR distinto entre
procesos. Ahora el desempate es estable y el modo migración rechaza fechas
duplicadas, pero esto no selecciona por sí solo la fuente correcta.
El replay fijó `src=` y no valida esa ruta. Antes de migrar, fijar un único
RR por fecha mediante inventario con nombre, procedencia y SHA-256; rechazar
empates no resueltos y demostrar paridad del CORE real con el replay.
La migración debe ser una operación coordinada con el despliegue: el guard
detiene el sync ante el manifiesto operativo sin `GEOMETRY_VERSION`. Falta
un runbook/script probado para esa transición, incluida recuperación.
El inventario de derivados debe incluir los artefactos persistidos de
`analysis/reports/` que contienen `lnRMSSD` o `RMSSD_stable`, además de SSM,
briefs y salidas canónicas; decidir cuáles se regeneran, versionan o marcan
como históricos antes del corte.

**Dos decisiones de semántica pendientes.** Mantener 15 %/20 % con el
denominador del registro truncado endurece la clasificación y crea tres
`INVALID` nuevos: aceptar ese efecto o revisar el contrato explícitamente.
Recuperar en el seguimiento el encargo `rejected_rr_pct_window` de HG-05 y
decidir si se implementa, se difiere o se descarta; no inferir que ya existe.

## Resolución temporal del RMSSD — corregida 2026-10-28

[Informe consolidado corregido](../../research/reports/hg10_resolucion_temporal_2026-10-28.md).
Esta sección sustituye explícitamente las conclusiones anteriores que trasladaban el error
sintético a los ECG reales y daban por resuelta la exactitud.

En 192 simulaciones, el error absoluto mediano baja de 1,61085 % a 0,07185 % con el
refinamiento parabólico del máximo positivo local. Es una mejora dentro del simulador;
28 corridas del detector actual subestiman, por lo que no «siempre infla».
En 50 ECG reales hay descenso en 47, mediana −1,59 %, extremos −13,03 % y +1,83 %,
con pares fijos y paridad basal 50/50. Es desacuerdo medido, no corrección demostrada.
No resuelve cuál anclaje real es más exacto ni sustituye LAT_NAN como criterio de Calidad.

El inventario de 506 fechas clasifica 276 cerca de 1 ms, 219 cerca de 7,686 ms y deja once
sin clasificar. Hay 230 de procedencia ECG; 219 no es el máximo de reprocesado.
Faltan frente a las 508 del replay 2025-10-07 y 2025-10-14, de origen Franz_Dunn;
el agregado informa cobertura y exclusiones del cargador. No son las tres fechas sin
RMSSD utilizable que aún figuran en el histórico operativo. Rejilla, procedencia y
exactitud son conceptos distintos.

Se retiran las atribuciones no verificadas al firmware Polar, la superioridad sobre RR nativo,
la estimación del error del anclaje anterior combinando varianzas sintéticas y reales, y la
identificación de latidos espurios a partir de razones RR sin referencia ECG.

Pendientes dentro de HG-10: referencia temporal independiente con incertidumbre explícita,
replay aislado de impacto y cobertura de ECG. El replay puede avanzar sin afirmar exactitud.
La validación de temporización sigue siendo distinta de detectar ectópicos o latidos omitidos.
HG-09 §9 permanece vigente; no se adopta el refinamiento y HG-10 sigue orange.

## Comparación con NeuroKit2 — conclusión consolidada

Se limita la relocalización a **45 grabaciones evaluables de 50**: cuatro se excluyen
por polaridad discordante y una por falta de pares comunes. En sus pares físicos comunes,
el desacuerdo mediano de RMSSD baja de +28,98 % a 0,00 % al aplicar la misma regla de
localización. No se extrapola a las exclusiones ni a los latidos no emparejados.
La coincidencia es esperable por construcción y no demuestra exactitud absoluta.
La proximidad entre B y L(A) muestra estabilidad entre dos reglas en esta muestra;
no demuestra independencia respecto a filtros, polaridad o elección del extremo.

**Ponderación corregida y reejecutada localmente:** un voto por latido original único
para coincidencia, desfase y dispersión; un voto por grabación en los resúmenes.
El RMSSD conserva sus pares físicos y sus cifras no cambian a la precisión guardada.
La SD mediana pasa de 3,7132 a **3,7177 ms** en A y de 14,3210 a **14,2684 ms** en C.
El porcentaje mínimo de coincidencia de muestra pasa de 98,696 % a **98,707 %**;
la mediana sigue en 100 %. Son medidas respecto a L(A), no error absoluto.
La traza instrumentada sigue coincidiendo con NeuroKit en 50/50 grabaciones y conserva
el hueco de 361,65 s entre aceptaciones directas del 31 de marzo.

Mantener el detector operativo es una decisión provisional por ausencia de defecto
concreto demostrado, no por superioridad. El refinamiento sigue siendo candidato.
La decisión sobre geometría y pares se separa de adoptar un nuevo fiducial.
No se exige una referencia temporal perfecta para decidir sobre aquella; nuevas capturas
o comparadores quedan como opciones justificables por discrepancias concretas.
HG-09 §9 permanece vigente; HG-10 sigue orange, sin publicación.

[Informe y antecedentes](../../research/reports/hg10_neurokit_2026-10-28.md).

## Comparación de una grabación con HRVanalysis 1.2 — 2026-10-29

La salida automática de HRVanalysis sobre el ECG del 2026-10-20 contiene 426 RR;
su rMSSD de pantalla de **33,1 ms** corresponde al registro completo (8:06), no
al tramo HG-10. Se han llevado sus tiempos de pico al eje original del ECG por
interpolación y se han aplicado las mismas reglas HG-10 que a nuestro RR.
El control propio reproduce el CORE candidato exactamente: **35,305 ms**;
HRVanalysis da **32,279 ms** (−8,57 %). Sus 427 picos se emparejan uno a uno
con los propios; solo faltan el primero y los dos últimos, en los extremos.

Sobre 233 ternas físicas idénticas dentro del tramo, A da **35,305 ms**, el
refinamiento B **32,249 ms** y HRVanalysis **32,251 ms**. En esos 427 latidos,
el desfase H−B tiene mediana −4,77 ms y dispersión de 0,40 ms: la variación
temporal entre latidos es casi la misma en esta grabación. La coincidencia con
un algoritmo externo aporta evidencia de reproducibilidad del *fiducial* B,
pero no establece cuál estima mejor el instante fisiológico ni extrapola a
otros días. Redondear H a la muestra más próxima habría inflado su RMSSD
HG-10 en 0,812 ms; ese método queda descartado para esta comparación.

La Calidad cambia de `FLAG_mecánico` en A (`LAT_NAN`) a `OK` en H y B, con
artefactos 0 % y estabilidad de cola `OK` en A y H. Las latencias H/B son 300/90 s;
el primer latido H aparece 1,159 s después del primero A, de modo que sus
ventanas físicas no coinciden exactamente. Esto evidencia sensibilidad de la
etiqueta a la serie y a su origen temporal, sin validar la política. Se mantiene
la decisión provisional: no adoptar B por una sola grabación ni modificar HG-09
§9; la adopción de geometría y pares sigue separada de elegir el fiducial.

[Informe y cálculo reproducible](../../research/reports/hg10_hrvanalysis_2026-10-29.md).

**Lote HRVanalysis completo el 2026-10-29.** Las diez fechas preseleccionadas
entre las 50 grabaciones recuperadas se han procesado, además del piloto
2026-10-20: once ECG repartidos de marzo a octubre. Los once `.rr` y TXT
concuerdan y no registran correcciones. A reproduce 77 valores de control del
CORE candidato y B reproduce el benchmark anterior. En 2.465 ternas físicas
comunes, la diferencia absoluta H−B de RMSSD por fecha tiene mediana
**0,036 ms** y máximo **0,093 ms**; para la cadena HG-10 con pares propios, mediana
**0,105 ms** y máximo **0,564 ms** por diferencias en detección, filtros y
material. Esta reproducibilidad técnica en la muestra dirigida no establece
qué fiducial es fisiológicamente correcto. Calidad A/H difiere en dos fechas;
Calidad H/B, en una. La comparación no valida `LAT_NAN` ni justifica adoptar B
o modificar HG-09 §9. La geometría y los pares de HG-10 se deciden por
separado. [Protocolo](../../research/reports/hg10_hrvanalysis_ampliacion_protocolo_2026-10-29.md),
[informe parcial conservado](../../research/reports/hg10_hrvanalysis_ampliacion_2026-10-29.md)
y [lote completo](../../research/reports/hg10_hrvanalysis_lote_completo_2026-10-29.md).

**Cuatro fechas CORE recientes (26–29 de octubre), analizadas el 2026-10-29.**
Los EDF, `.rr` y TXT se verificaron sin correcciones registradas; «Invert QRS»
estuvo desmarcada. En las cuatro, H−B sobre ternas físicas comunes no supera
**0,196 ms**; en tres también es pequeño con la cadena HG-10 propia. El 29
es la excepción: H da **32,791 ms** frente a B **28,708 ms** con sus pares
propios, pero solo −0,121 ms sobre las 233 ternas comunes. H acepta siete
pares exclusivos frente a los comunes y presenta un `ΔRR` de −228,79 ms
en la región de 235–237 s del ECG, donde A tiene un pico sin pareja y
morfología atípica. H queda `FLAG_mecánico` por
`STAB_LAST2_MISMATCH`; A/B quedan `OK`. No se ha determinado qué detector
trata mejor ese evento. El CORE desplegado refleja otra configuración y, para
el 29, su manifiesto registra un RR de entrada con huella distinta del RR
local regenerado desde el ECG: no se atribuye la diferencia con esa fila a
la geometría. [Preparación y procedencia](../../research/reports/hg10_hrvanalysis_ultimas_preparacion_2026-10-29.md)
y [comparación de las cuatro fechas](../../research/reports/hg10_hrvanalysis_ultimas_2026-10-29.md).

## Criterio de cierre

Distinguir y documentar: (1) implementación y replay verificados, con control
fijado a commit e inventario RR; (2) evidencia y límites
de Calidad/temporización; (3) decisión explícita sobre geometría/pares y, por
separado, sobre cualquier flexibilización de `LAT_NAN`, con impacto explícito
en CORE, FINAL y SSM; (4) preparación y
verificación operativa de la publicación, incluida la decisión sobre las tres
filas sin RMSSD, el denominador de artefactos y los derivados persistidos.
La falta de referencia no
autoriza publicar automáticamente ni impone un bloqueo indefinido. HG-10 permanece
orange y no se declara cerrada con criterios de Calidad que no se han validado.

Antecedentes: [HG-03](RR_PARES_CONSECUTIVOS_TAREA.md),
[HG-04](<HG-04 Ventana de calculo de RMSSD_stable y revision de estabilizacion.md>),
[HG-05](<HG-05 Auditoria de deteccion de latidos y calidad de senal en ventana.md>),
[HG-06](<HG-06 Diagnostico y referencia ECG.md>),
[HG-07 / HG-08](<HG-07 HG-08 Reconstruccion RR y detector ECG en origen.md>),
[HG-09](<HG-09 Politica de Calidad HRV para ventana 90-375 s.md>).

## Inventario ampliado y ensayo hasta el 03/11/2026

516 fechas operativas, 513 entradas RR fijadas en la copia y tres filas previas sin RMSSD utilizable. Las 508 huellas originales coinciden con el inventario congelado. Las cinco incorporaciones son 28 y 29/10 y 01, 02 y 03/11. CORE, FINAL/DASHBOARD y SSM se ejecutaron en la copia. [Inventario de la ejecución](../../out/hg10_513_gva0ajt_/inventario.json). El inventario conserva las huellas de los archivos locales sin transformar. Para el 03/11 sustituir CRLF por LF reproduce exactamente los 3731 bytes y la huella del manifiesto operativo; el mismo control para el 29/10 produce los 3750 bytes y la huella registrada en la preparación anterior. Esto resuelve la salvedad de procedencia de ese día. Las cifras 36/38/56 siguen correspondiendo al contraste de políticas sobre 508 fechas.

## Decisión ejecutada · 03/11/2026
Retiradas por decisión del usuario las filas sin RMSSD del 26/02, 27/02 y 03/03 de los cuatro maestros locales. Quedan 513 fechas hasta el 03/11. Se conservaron los bytes de las filas restantes, se registró la operación en los manifiestos y se guardó la generación previa en data/backup/hg10_retirada_1m_yvayh/. Esta operación local resuelve la decisión sobre las tres filas. Los ensayos previos conservan sus cohortes originales.

## Descartes dentro del tramo útil · 513 fechas hasta 03/11/2026

Se reprodujo el porcentaje global del CORE candidato en 513/513 fechas con los RR del inventario. Sobre los RR cuyo instante final está entre 90 s y el último RR incluido menos 15 s, las bandas de 15/20 % coinciden con el global truncado en 510/513. Las tres excepciones son 30/03 (24,07 % global, 19,91 % local), 20/04 (15,74 %, 12,90 %) y 10/06 (23,89 %, 10,14 %). De los tres nuevos INVALID por el corte, junio 15 y julio 12 siguen por encima del 20 % dentro del tramo. El 10/06 hubo 53 descartes antes del segundo 90 y 22 de 217 en el tramo. Es una comparación descriptiva de denominadores; cambiar la regla de Calidad requeriría evaluar sus derivados y decidir la adopción. Se recomienda conservar los umbrales numéricos y registrar la métrica local para auditoría. [Cálculo reproducible](../../research/experiments/hg10/scripts/hg10_descartes_513.py) y [resultados por fecha](../../research/experiments/hg10/results/hg10_descartes_513.csv).

## Ensayo en copia del criterio de artefactos en el tramo · 03/11/2026

Control y variante sobre los mismos 513 RR, política B de latencia y umbrales estrictos >15 % y >20 %. Solo la variante usa el porcentaje del tramo en la Calidad y los flags ART. Artifact_pct sigue siendo global en ambas, incluido su uso en la varianza del SSM. El RMSSD diario coincide en todas las filas. Calidad cambia el 30/03 (INVALID a FLAG), el 20/04 (FLAG a OK) y el 10/06 (INVALID a OK). FINAL cambia cuatro gates: 30/03 NO a ÁMBAR, 20/04 ÁMBAR a VERDE, 18/05 VERDE a ÁMBAR y 10/06 NO a VERDE. Dos acciones pasan de SUAVE_O_DESCANSO a INTENSIDAD_OK (20/04 y 10/06). El veto agudo se activa además el 13/06. SSM admite una observación adicional (10/06); cambio absoluto mediano del estado de recuperación cero y máximo 0,02732 lnRMSSD (20/04). Es un ensayo de impacto, pendiente de decisión. Para adoptar, exponer el porcentaje local que explica Calidad, distinguirlo del global en los motivos del FINAL y versionar la regla. [Reproducción](../../research/experiments/hg10/scripts/hg10_ensayo_artefactos_513.py).
