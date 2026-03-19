# Notebook.md

Este notebook no sustituye al diccionario de columnas ni a la especificacion tecnica.
Su funcion es otra: explicar de forma didactica como piensa el sistema ENDURANCE HRV y por que toma las decisiones que toma.

Fecha de corte: 2026-03-13.

Regla editorial:

- este documento describe comportamiento real del sistema actual
- cuando algo es solo informativo, se dice expresamente
- cuando algo no esta implementado, no se presenta como si ya existiera

## ¿Que hace realmente este sistema cada manana?

Cada manana el sistema intenta responder a una pregunta muy simple: `¿tiene sentido meter intensidad hoy o conviene ser conservador?`

Para contestarla combina tres capas:

1. Tu medicion matinal con banda y RR, que es la senal principal.
2. Tu contexto nocturno Polar, que sirve para interpretar, no para mandar.
3. Tu carga reciente de entrenamiento, que añade contexto, no sustituye la fisiologia.

El resultado final es un semaforo operativo y una recomendacion de accion diaria.

## ¿Como decide el Gate 2D si puedo entrenar hoy?

El Gate 2D es el nucleo decisor del sistema. Cruza dos senales fisiologicas:

- tu variabilidad cardiaca en escala `lnRMSSD`
- tu pulso estable de reposo `HR_stable`

La logica es sencilla:

- si ambas senales estan dentro de tu rango normal, el dia es `VERDE`
- si solo cae la HRV, el dia pasa a `AMBAR` por `2D_LN`
- si solo sube el pulso, el dia pasa a `AMBAR` por `2D_HR`
- si se deterioran ambas a la vez, el dia pasa a `ROJO` por `2D_AMBOS`

La idea de fondo es importante: el sistema no quiere reaccionar a un numero aislado, sino a una convergencia de senales compatibles con fatiga, estres o mala tolerancia a la intensidad.

## ¿Que intenta distinguir el gate entre fatiga real, ruido de medicion y variabilidad normal?

Esa es probablemente la pregunta mas importante de todo el sistema.

El gate intenta separar tres cosas que a simple vista pueden parecer iguales:

- la variabilidad normal de un organismo vivo, que no deberia cambiar el entrenamiento
- el ruido de medicion, que puede mover el dato sin reflejar tu estado real
- la fatiga o el estres fisiologico que si deberian cambiar la decision del dia

Para hacerlo combina varias defensas:

- `BASE60`, para saber que es normal para ti
- `ROLL3`, para no sobrerreaccionar a un solo dato raro
- `SWC`, para exigir que el cambio sea biologicamente relevante
- `quality_flag`, para ponerse conservador si la senal no inspira confianza
- `veto_agudo`, para no dejar que el suavizado esconda una caida brusca real

En otras palabras: el gate no busca adivinarlo todo. Busca equivocarse menos cuando tiene que decidir si hoy compensa asumir riesgo o no.

## ¿Como se calcula mi "normal" de 60 dias?

Tu `BASE60` es tu referencia fisiologica reciente.

No es una media de todo lo que haya ocurrido, sino una referencia robusta construida asi:

- mira los 60 dias anteriores al de hoy
- excluye el dia actual de su propia comparacion
- usa solo dias `clean`
- calcula la mediana de HRV y de pulso, no la media

Esto hace que tu baseline sea mas estable y menos sensible a dias raros, enfermedad puntual o mediciones malas.

El sistema exige ademas una base minima. Si no hay suficientes dias clean en esa ventana, no finge precision: devuelve `NO` y reconoce que no tiene base estadistica suficiente.

## ¿Por que el sistema prefiere la mediana sobre el promedio?

Porque intenta proteger tu baseline del ruido y de los extremos.

Con un promedio, unos pocos dias muy malos o muy buenos desplazan la referencia con demasiada facilidad. Con la mediana, la referencia cambia mas despacio y refleja mejor tu estado habitual.

En una herramienta de decision diaria eso importa mucho. Lo peligroso no es que la referencia tarde un poco mas en moverse; lo peligroso es que se mueva demasiado por culpa de eventos atipicos y empiece a justificar decisiones equivocadas.

## ¿Por que usa lnRMSSD como senal principal y no RMSSD bruto?

Porque el `RMSSD` bruto suele comportarse de forma mas asimetrica y menos estable para comparar cambios relativos.

Al pasar a `lnRMSSD`, el sistema trabaja con una escala mas adecuada para:

- comparar desviaciones respecto a tu baseline
- medir cambios de forma mas proporcional
- evitar que variaciones grandes en milisegundos deformen la lectura

Dicho de forma practica: el logaritmo hace que la senal sea mas util para decidir, no necesariamente mas intuitiva para leer a ojo.

## ¿Como se calcula el SWC y por que es tan importante?

El `SWC` es el umbral que separa ruido de cambio relevante.

El sistema no pregunta solo `¿hoy estoy peor que mi baseline?`, sino `¿estoy peor lo suficiente como para que merezca cambiar la decision?`

Para eso usa una dispersion robusta sobre tu ventana BASE60:

- calcula la MAD
- la convierte en una desviacion robusta
- aplica `SWC = 0.5 * robust_sd`

Se calcula por separado para:

- `SWC_ln`, que vigila la HRV
- `SWC_HR`, que vigila el pulso

La idea fisiologica es sencilla: un cuerpo vivo no es una maquina estatica. Si reaccionaras a cualquier oscilacion minima, el sistema seria histerico. El SWC evita eso.

## ¿Como usa el SWC para cambiar el semaforo?

Cada dia compara tu estado usado para decidir con tu baseline:

- `d_ln = lnRMSSD_used - ln_base60`
- `d_HR = HR_used - HR_base60`

Despues mira si esas diferencias superan sus umbrales:

- HRV baja si `d_ln < -SWC_ln`
- pulso alto si `d_HR > SWC_HR`

Y a partir de ahi aplica la matriz 2D:

- nada fuera de rango -> `VERDE`
- solo HRV baja -> `AMBAR`
- solo HR alta -> `AMBAR`
- ambas fuera de rango -> `ROJO`

Eso explica por que el sistema es mas exigente con los dias realmente malos: el rojo exige convergencia, no una simple molestia estadistica.

## ¿Que calcula swc_ln_floor y para que sirve?

`swc_ln_floor` es una proteccion contra la hipersensibilidad del sistema.

En la practica se define como el maximo entre:

- tu `SWC_ln` real
- un suelo minimo equivalente a `ln(1.05)`

Eso impide que una variabilidad historicamente muy estable haga que el sistema reaccione de forma exagerada a microcambios sin importancia.

Su uso principal hoy es proteger la regla del veto agudo. No recolorea por si mismo el semaforo.

## ¿Como funciona el mecanismo del veto agudo?

El veto agudo existe para resolver un problema real del suavizado: a veces el promedio de 3 dias puede esconder una caida brusca de hoy.

Por defecto, el sistema decide con una senal suavizada (`ROLL3`). Eso es bueno para no sobrerreaccionar al ruido. Pero tiene un coste: si hoy te hundes de golpe, dos dias buenos previos pueden maquillar la foto.

Para evitarlo, el sistema activa `veto_agudo` cuando:

- el dia de hoy es `clean`
- y el `lnRMSSD_today` cae por debajo de `ln_base60 - 2 * swc_ln_floor`

Cuando eso ocurre:

- deja de usar el promedio de 3 dias
- usa el dato crudo de hoy para HRV y pulso
- guarda el valor previo en `ln_pre_veto`

Punto importante: el veto no significa `ROJO automatico` por definicion. Significa `bypass del suavizado`. Luego el gate vuelve a evaluar la misma matriz 2D con ese dato crudo.

## ¿Que relacion fisiologica existe entre pulso en reposo y HRV, y por que el residual anade contexto util?

Pulso en reposo y HRV suelen moverse de forma relacionada, aunque no identica.

En general:

- cuando el pulso sube, la HRV tiende a bajar
- cuando el pulso baja, la HRV tiende a mejorar

Pero esa relacion nunca es perfecta. Y ahi entra el residual.

El residual responde a una pregunta fina: `dado el pulso que tienes hoy, ¿tu HRV esta mejor o peor de lo esperable?`

Si el residual es:

- positivo, tu HRV esta mejor de lo esperado para ese pulso
- negativo, tu HRV esta peor de lo esperado para ese pulso

Eso se traduce en un sufijo del badge: `+`, `++`, `+++`, `-`, `--`, `---`.

Lo esencial es esto: el residual da matiz, no da orden. Anade contexto al color, pero no cambia el color.

## ¿Por que una HRV alta no siempre significa que estoy mejor recuperado?

Porque una HRV alta puede significar cosas distintas segun el contexto.

A veces es una senal de buena recuperacion. Otras veces puede representar una respuesta desproporcionada, una saturacion parasimpatica o un estado raro respecto a tu patron habitual.

Por eso el sistema no premia automaticamente una HRV alta. La interpreta respecto a:

- tu baseline
- tu pulso
- la coherencia con el resto de senales

En el `reason_text`, una HRV muy por encima de lo normal puede aparecer como `posible saturacion parasimpatica`.

## ¿Que diferencia fisiologica hay entre HRV baja con pulso normal y HRV baja con pulso alto?

No son cuadros equivalentes.

Cuando la HRV baja pero el pulso sigue normal, el sistema lo lee como una senal parcial. Puede haber fatiga, estres o mala tolerancia en desarrollo, pero todavia no hay una convergencia fuerte.

Cuando ademas el pulso sube, la interpretacion cambia. Ya no es solo una perdida de variabilidad: tambien hay activacion compatible con peor recuperacion o mayor estres sistemico. Por eso esa combinacion escala a rojo.

Dicho de otra manera: el pulso alto le da mas "credibilidad biologica" a una HRV baja.

## ¿Por que el sistema da mas peso a la tendencia que al valor aislado de hoy?

Porque el HRV diario es intrinsecamente ruidoso.

Hay demasiadas cosas que pueden mover una medicion puntual:

- tension al despertar
- postura
- respiracion
- pequenas diferencias de rutina
- ruido de senal

Si decidieras solo con el numero de hoy, tendrias muchas falsas alarmas. Por eso el sistema usa:

- un baseline largo para saber que es normal para ti
- un suavizado corto para no sobrerreaccionar
- un veto agudo para no dormirse ante una caida real

Es una forma de equilibrar sensibilidad y estabilidad.

## ¿Por que el sistema usa ventanas de 60, 42 y 28 dias y que tipo de cambios detecta cada una?

Las tres ventanas existen porque no todas las alteraciones fisiologicas tienen la misma velocidad.

- `BASE60` capta tu normal mas estable y evita que unos pocos dias raros te redefinan.
- `BASE42` detecta cambios de regimen intermedios, mas rapido que BASE60 pero sin ser tan nervioso.
- `BASE28` es la sombra mas reactiva y se entera antes de que tu normal reciente esta cambiando.

En el modo normal del sistema (`O2_SHADOW`), BASE42 y BASE28 no mandan. Sirven para vigilar si tu fisiologia reciente ya va peor o mejor que lo que todavia refleja BASE60.

En un modo avanzado (`O3_OVERRIDE_PERSIST_2of3`), las sombras pueden ajustar el gate final un nivel si su discrepancia persiste 2 de los ultimos 3 dias.

La idea no es multiplicar el ruido, sino mirar tu estado con tres velocidades distintas: una estable, una intermedia y una rapida.

## ¿Que significa que mi baseline se haya degradado aunque hoy el color no sea rojo?

Significa que tu problema puede no ser solo `como estas hoy`, sino `desde donde estas operando ultimamente`.

Un rojo habla de una alerta aguda del dia. Un baseline degradado habla de una bajada mas lenta de tu capacidad normal reciente respecto a una referencia mas sana o mas favorable.

Eso puede ocurrir, por ejemplo, cuando:

- sigues funcionando sin un colapso agudo
- pero tu normal reciente ya es peor que hace semanas o meses
- y el sistema detecta que te has acostumbrado a rendir desde un escalon inferior

Por eso un dia puede no ser rojo y, aun asi, dejar la sensacion de que algo de fondo va peor. El color responde al estado de hoy. El baseline degradado habla del terreno sobre el que llevas tiempo moviendote.

## ¿Que tipo de fatiga detecta mejor la medicion matinal y que tipo de fatiga puede escaparse?

La medicion matinal detecta mejor la fatiga que deja huella en el estado autonomico de reposo.

Suele captar razonablemente bien:

- recuperacion insuficiente
- carga acumulada que ya ha afectado a tu sistema autonomico
- estres sistemico
- enfermedad incipiente o malestar global cuando ya alteran HRV y pulso

Puede escaparse o verse peor en:

- fatiga muy local muscular o biomecanica
- dolor periferico sin gran impacto autonomico
- deterioro tecnico o neuromuscular sin huella clara en reposo
- problemas de nutricion, calor o hidratacion que aun no hayan cambiado tu medicion matinal
- dias en que la fatiga existe, pero la senal matinal sale sorprendentemente neutra

Por eso el sistema ayuda mucho, pero no sustituye el juicio del atleta ni la lectura del entrenamiento real.

## ¿Que diferencia conceptual hay entre CORE, BETA_AUDIT, FINAL y DASHBOARD en la lectura de mi estado fisiologico?

Cada archivo cumple una funcion distinta en la lectura del sistema:

- `CORE`: es la capa fisiologica canonica. Guarda la medicion ya procesada y metricas como `lnRMSSD`, `SI_baevsky`, `SD1` y `SD2`.
- `BETA_AUDIT`: es una salida legacy de auditoria V3. Sirve para trazabilidad historica, no para decidir el gate actual.
- `FINAL`: es la capa de decision completa. Aqui viven baseline, SWC, deltas, veto, sombras, residual, gate final y accion.
- `DASHBOARD`: es una vista resumida para leer lo importante sin tragarte toda la auditoria.

Si quieres entender `que paso`, lees `FINAL`. Si quieres leer `que hago hoy`, miras `DASHBOARD`.

## ¿Que senales de FINAL son las que realmente deciden si hoy tolero intensidad y cuales solo ayudan a interpretar el contexto?

Las que mandan de verdad son pocas.

Las columnas practicamente decisoras son:

- `gate_final`
- `Action`
- `Action_detail`
- `quality_flag`

Las columnas que construyen la decision y te dejan auditarla son:

- `ln_base60`, `HR_base60`
- `SWC_ln`, `SWC_HR`
- `d_ln`, `d_HR`
- `gate_base60`
- `gate_shadow42`, `gate_shadow28`
- `decision_path`
- `override_reason`
- `veto_agudo`
- `ln_pre_veto`
- `residual_ln`, `residual_z`, `residual_tag`

Y las columnas que ayudan sobre todo a interpretar el dia son:

- `reason_text`
- `baseline60_degraded`
- `bad_streak`
- `bad_7d`

En otras palabras: unas columnas deciden, otras explican y otras contextualizan.

## ¿Por que el sistema separa decision operativa y metricas de auditoria?

Porque decidir y entender no son exactamente la misma tarea.

Si metieras todas las metricas disponibles en la decision diaria, el sistema seria mas fragil, mas opaco y probablemente mas nervioso. Al separar capas, el sistema logra dos cosas:

- mantener una decision diaria relativamente sobria y estable
- conservar suficiente auditoria para revisar despues por que salio ese color

Esa separacion es sana. Permite que el semaforo no dependa de veinte senales a la vez, pero evita tambien la caja negra total.

## ¿Cuando una medicion deja de ser fiable y por que el sistema se vuelve conservador aunque el semaforo no sea rojo?

Una medicion deja de ser plenamente fiable cuando el sistema no la considera `clean`, aunque tampoco la descarte como invalida del todo.

En la practica, eso significa: `el sistema desconfia de la calidad de la senal aunque no tire toda la fila a la basura`.

Esa desconfianza puede venir de problemas previos de calidad, estabilidad o completitud ya arrastrados en la medicion procesada.

Su efecto operativo es conservador:

- aunque el gate no sea rojo
- la recomendacion se restringe
- la salida pasa a `SUAVE_O_DESCANSO`
- y `Action_detail` puede marcar `SUAVE_QUALITY`

Fisiologicamente tiene sentido: una buena decision con una mala medicion sigue siendo una mala decision.

## ¿Que factores explicativos entran en reason_text y por que algunos datos disponibles no se usan para decidir?

`reason_text` no es un espejo de todos los datos disponibles. Es un texto corto con solo algunos factores contextuales que hoy el sistema considera utiles para interpretar el dia.

Puede incluir:

- mensaje de veto agudo
- aviso de calidad dudosa
- noche corta
- noche fragmentada
- discordancia de `polar_night_rmssd`
- carga acumulada alta
- volumen semanal alto
- Z3 acumulado alto
- rojo sin carga previa ni sueno malo
- verde con carga acumulada alta

Y se quedan fuera, aunque existan en CSV, cosas como:

- `SI_baevsky`
- `SD1`, `SD2`, `SD1_SD2_ratio`
- `polar_night_rri`
- `polar_night_resp`
- `polar_continuity`, `polar_efficiency_pct`, `polar_sleep_score`
- residual y sombras como explicacion textual automatica
- cualquier ANS Charge diferenciado

¿Por que se quedan fuera? Porque el sistema intenta que `reason_text` sea explicativo sin convertirse en un informe infinito ni en un segundo decisor paralelo.

## ¿Que informacion nocturna de Polar complementa la medicion matinal y cual no debe tener peso decisor?

Hoy el sistema usa de forma efectiva para contexto:

- `polar_sleep_duration_min`
- `polar_interruptions_long`
- `polar_night_rmssd`

Eso le permite construir mensajes como:

- noche corta
- noche fragmentada
- rojo con nightly RMSSD alto como posible confusor

En cambio, hoy no entran en la logica del gate ni en `reason_text` estas columnas, aunque se guarden:

- `polar_night_rri`
- `polar_night_resp`
- `polar_continuity`
- `polar_continuity_index`
- `polar_efficiency_pct`
- `polar_sleep_score`

Y tambien es importante lo que no existe como columna operativa separada: hoy no hay un ANS Charge canonico que participe en la decision.

## ¿Que papel juega el sueno como contexto y por que no debe anular por si solo la medicion matinal?

Porque el sueno contextualiza, pero la medicion matinal sigue siendo la prueba principal del dia.

El sueno te ayuda a responder preguntas como:

- `¿venia ya tocado de la noche?`
- `¿hay una explicacion razonable para esta mala senal?`
- `¿hay discordancia entre noche y manana?`

Pero no debe anular por si solo la medicion matinal por dos motivos:

- la medicion matinal esta hecha bajo un protocolo mas directo y comparable dia a dia
- el dato nocturno puede ser util como contexto y, aun asi, no reflejar exactamente tu tolerancia al esfuerzo de esta manana

Por eso el sistema permite que un nightly bueno matice un rojo, pero no le da permiso para borrar el gate.

## ¿Como ayuda la carga de entrenamiento reciente a interpretar una caida de HRV sin sustituir la senal fisiologica principal?

`ENDURANCE_HRV_sessions_day.csv` no decide el color del dia. Su papel es mas sutil: ayuda a interpretar si una senal fisiologica encaja con la carga reciente.

Por ejemplo, puede anadir avisos si detecta:

- `load_3d` alto
- `work_7d_sum` alto
- `z3_7d_sum` alto
- un dia rojo sin carga previa clara
- un dia verde con carga acumulada que aconseja prudencia

Eso enriquece la lectura del dia, pero no sustituye la senal principal del gate.

La filosofia es correcta: la carga te dice `de donde podria venir` el estado de hoy, pero no debe imponerse sobre la medicion matinal.

## ¿Como afecta exactamente el contenido de sessions al gate?

A dia de hoy, `sessions_day` no recolorea el gate ni cambia por si mismo un `VERDE`, `AMBAR` o `ROJO`.

El color del gate sigue saliendo de la fisiologia matinal:

- `lnRMSSD`
- `HR_stable`
- baseline
- SWC
- veto agudo
- sombras

Lo que hace `sessions_day` es anadir contexto sobre la carga reciente para que la lectura del dia sea mas inteligente.

En la practica puede:

- explicar mejor una caida de HRV si vienes de varios dias densos
- volver mas prudente la lectura de un `VERDE` con mucha carga acumulada
- sugerir que un `ROJO` no encaja del todo con la carga previa y obliga a mirar otros factores

Dicho simple: `sessions_day` no manda sobre el semaforo, pero si cambia la forma en que deberias interpretar ese semaforo.

## ¿Como se manifiesta una acumulacion de carga en la combinacion HRV, pulso y contexto de entrenamiento?

Cuando la carga se acumula de forma mal absorbida, lo esperable es que el sistema empiece a ver una historia coherente entre varias piezas:

- la HRV deja de sostenerse o cae
- el pulso de reposo tiende a subir o a mantenerse demasiado alto para tu patron
- las sombras se vuelven mas reactivas antes que BASE60
- `reason_text` empieza a recoger carga reciente alta, volumen elevado o Z3 acumulado

No siempre aparecen todas a la vez ni con la misma fuerza. A veces la carga se manifiesta primero en el contexto de entrenamiento, luego en el pulso y despues en la HRV. Otras veces el primer signo claro es una caida de HRV tras varios dias densos.

Lo importante es que el sistema intenta leer esa acumulacion como un proceso, no como un numero aislado.

## ¿Que papel tienen SI_baevsky y SD1/SD2 en el sistema actual?

Hoy su papel es informativo.

Se calculan y se guardan porque aportan lectura fisiologica adicional:

- `SI_baevsky` puede sugerir activacion simpatica
- `SD1/SD2` ayuda a leer la geometria de la variabilidad

Pero actualmente:

- no recolorean el gate
- no activan veto
- no cambian `Action`

Su valor hoy es de auditoria e interpretacion experta, no de mando operativo.

## ¿Que cosas no deberia prometer este notebook como si ya existieran?

No deberia presentar como vigentes, salvo que el codigo cambie de verdad:

- Studio o pestanas nuevas de analitica
- reportes mensuales generados por la app
- KPI automaticos de falsos verdes
- ANS Charge operativo como entrada del gate
- metricas Tier 3 accionables como DFA-a1 o SampEn
- protocolos ICC integrados en el flujo productivo

Si alguna de esas ideas se quiere conservar, mejor ponerla como `futuro` o `experimental`, no como comportamiento actual.

## ¿Para que sirve entonces este notebook si ya existe un diccionario?

El diccionario te dice `que significa una columna`.

Este notebook debe decirte algo distinto: `como razona el sistema`, `por que separa unas senales de otras`, `que manda de verdad`, `que solo contextualiza` y `que errores de interpretacion conviene evitar`.

Ese es su valor. No repetir la tabla de columnas, sino traducir la logica del sistema a preguntas humanas bien respondidas.
