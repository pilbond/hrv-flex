# Notebook.md

**Revisión:** r2026-05-08 v0.2 (alineado con sistema vigente V4.10: capa RE-01, DO-01/02, clustering de intensidad, convergencia de carga)
**Sistema vigente con el que se sincroniza:** ENDURANCE HRV V4.10

Este notebook no sustituye al diccionario de columnas ni a la especificacion tecnica.
Su funcion es otra: explicar de forma didactica como piensa el sistema ENDURANCE HRV y por que toma las decisiones que toma.

Reglas editoriales:

- este documento describe comportamiento real del sistema actual
- cuando algo es solo informativo, se dice expresamente
- cuando algo no esta implementado, no se presenta como si ya existiera
- las preguntas son la unidad basica: cada encabezado responde una duda concreta

Convencion del trio documental:

- **Diccionario**: ¿que es esta columna y que hago con ella?
- **Notebook (este archivo)**: ¿por que el sistema piensa asi?
- **Spec_Tecnica**: ¿exactamente como lo calcula?

Si una pregunta empieza por `que` → Diccionario. Si empieza por `por que` → aqui. Si empieza por `como se calcula` → Spec_Tecnica.

---

## Indice

**Como funciona el sistema**
- ¿Que hace realmente este sistema cada manana?
- ¿Como decide el Gate 2D si puedo entrenar hoy?
- ¿Que intenta distinguir el gate entre fatiga real, ruido y variabilidad normal?

**Como construye su referencia**
- ¿Como se calcula mi "normal" de 60 dias?
- ¿Por que el sistema prefiere la mediana sobre el promedio?
- ¿Por que usa lnRMSSD como senal principal y no RMSSD bruto?
- ¿Como se calcula el SWC y por que es tan importante?
- ¿Como usa el SWC para cambiar el semaforo?
- ¿Que calcula swc_ln_floor y para que sirve?
- ¿Por que ventanas de 60, 42 y 28 dias?

**Mecanismos de proteccion**
- ¿Como funciona el mecanismo del veto agudo?
- ¿Cuando una medicion deja de ser fiable?
- ¿Cuando debo ignorar el verde y ser conservador de todas formas?

**Lectura del resultado**
- ¿Que significan los colores con + y -?
- ¿Que es el reason_text y como leerlo sin que me abrume?
- ¿Que es la capa RE-01 y para que sirve si no cambia el gate?
- ¿Que pasa cuando el gate sale verde pero el contexto dice otra cosa?

**Fisiologia y matiz**
- ¿Por que una HRV alta no siempre significa que estoy mejor recuperado?
- ¿Que diferencia hay entre HRV baja con pulso normal y HRV baja con pulso alto?
- ¿Que relacion fisiologica existe entre pulso y HRV, y por que el residual aporta contexto?
- ¿Por que el sistema da mas peso a la tendencia que al valor aislado de hoy?
- ¿Que significa que mi baseline se haya degradado aunque hoy el color no sea rojo?
- ¿Que tipo de fatiga detecta mejor la medicion matinal y cual se le escapa?

**Contexto que rodea el gate**
- ¿Como entran mis sesiones de entrenamiento en la decision del dia?
- ¿Como afecta exactamente el contenido de sessions al gate?
- ¿Como se manifiesta una acumulacion de carga?
- ¿Que aporta la distribucion de intensidad semanal?
- ¿Que papel juega el sueno como contexto?
- ¿Que info nocturna de Polar complementa la matinal?

**Auditoria y meta**
- ¿Que diferencia conceptual hay entre CORE, BETA_AUDIT, FINAL y DASHBOARD?
- ¿Que senales de FINAL deciden y cuales solo explican?
- ¿Por que el sistema separa decision operativa y metricas de auditoria?
- ¿Que papel tienen SI_baevsky y SD1/SD2 en el sistema actual?
- ¿Que factores explicativos entran en reason_text y cuales no?
- ¿Que cosas no deberia prometer este notebook como si ya existieran?
- ¿Para que sirve este notebook si ya existe el diccionario?

---

## ¿Que hace realmente este sistema cada manana?

Cada manana el sistema intenta responder a una pregunta muy simple: `¿tiene sentido meter intensidad hoy o conviene ser conservador?`

Para contestarla combina tres capas:

1. Tu medicion matinal con banda y RR, que es la senal principal.
2. Tu contexto nocturno Polar, que sirve para interpretar, no para mandar.
3. Tu carga reciente de entrenamiento, que añade contexto, no sustituye la fisiologia.

El resultado final es un semaforo operativo (`gate_badge`) y una recomendacion de accion diaria (`Action`, `Action_detail`).

→ Diccionario §0 ("Como leer el CSV operativo") describe la secuencia exacta de columnas que miras cada dia.

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

---

## ¿Como se calcula mi "normal" de 60 dias?

Tu `BASE60` es tu referencia fisiologica reciente.

No es una media de todo lo que haya ocurrido, sino una referencia robusta construida asi:

- mira los 60 dias anteriores al de hoy
- excluye el dia actual de su propia comparacion (regla `shift-1`)
- usa solo dias `clean` (Calidad OK, estabilidad OK, artefactos ≤10%, sin NaN)
- calcula la mediana de HRV y de pulso, no la media

Esto hace que tu baseline sea mas estable y menos sensible a dias raros, enfermedad puntual o mediciones malas.

El sistema exige ademas una base minima. Si no hay al menos 30 dias clean en esa ventana, no finge precision: devuelve `NO` con razon `BASE60_INSUF` y reconoce que no tiene base estadistica suficiente. Por eso, si llevas pocas semanas usando el sistema, es completamente normal ver `NO` durante el periodo de calibracion.

→ Diccionario §10 ("Glosario": BASE60, dia clean, shift-1).

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

El `SWC` (Smallest Worthwhile Change) es el umbral que separa ruido de cambio relevante.

El sistema no pregunta solo `¿hoy estoy peor que mi baseline?`, sino `¿estoy peor lo suficiente como para que merezca cambiar la decision?`

Para eso usa una dispersion robusta sobre tu ventana BASE60:

- calcula la MAD (Median Absolute Deviation)
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
- un suelo minimo equivalente a `ln(1.05)` (≈ 0.04879)

Eso impide que una variabilidad historicamente muy estable haga que el sistema reaccione de forma exagerada a microcambios sin importancia.

Su uso principal hoy es proteger la regla del veto agudo. No recolorea por si mismo el semaforo.

## ¿Por que el sistema usa ventanas de 60, 42 y 28 dias y que tipo de cambios detecta cada una?

Las tres ventanas existen porque no todas las alteraciones fisiologicas tienen la misma velocidad.

- `BASE60` capta tu normal mas estable y evita que unos pocos dias raros te redefinan.
- `BASE42` detecta cambios de regimen intermedios, mas rapido que BASE60 pero sin ser tan nervioso.
- `BASE28` es la sombra mas reactiva y se entera antes de que tu normal reciente esta cambiando.

En el modo normal del sistema (`O2_SHADOW`), BASE42 y BASE28 no mandan. Sirven para vigilar si tu fisiologia reciente ya va peor o mejor que lo que todavia refleja BASE60.

En un modo avanzado (`O3_OVERRIDE_PERSIST_2of3`), las sombras pueden ajustar el gate final un nivel si su discrepancia persiste 2 de los ultimos 3 dias. En produccion el modo por defecto es `O2`, asi que en la lectura habitual las sombras solo informan.

La idea no es multiplicar el ruido, sino mirar tu estado con tres velocidades distintas: una estable, una intermedia y una rapida.

→ Diccionario §3.E (gates extendidos) y §8 (decision_path).

---

## ¿Como funciona el mecanismo del veto agudo?

El veto agudo existe para resolver un problema real del suavizado: a veces el promedio de 3 dias puede esconder una caida brusca de hoy.

Por defecto, el sistema decide con una senal suavizada (`ROLL3`). Eso es bueno para no sobrerreaccionar al ruido. Pero tiene un coste: si hoy te hundes de golpe, dos dias buenos previos pueden maquillar la foto.

Para evitarlo, el sistema activa `veto_agudo` cuando:

- el dia de hoy es `clean`
- y el `lnRMSSD_today` cae por debajo de `ln_base60 - 2 * swc_ln_floor`

Cuando eso ocurre:

- deja de usar el promedio de 3 dias
- usa el dato crudo de hoy para HRV y pulso
- guarda el valor previo en `ln_pre_veto`, para que puedas auditar cuanto habria enmascarado el suavizado

Punto importante: el veto no significa `ROJO automatico` por definicion. Significa `bypass del suavizado`. Luego el gate vuelve a evaluar la misma matriz 2D con ese dato crudo. Lo habitual es que el resultado sea AMBAR o ROJO, pero la matriz sigue siendo la misma.

Adicionalmente: el veto agudo cuenta como cualquier otro rojo a efectos de `bad_streak` y `bad_7d`. Si llevas dos rojos consecutivos (con o sin veto), `Action_detail` saltara a `DESCARGA`. Si llevas tres rojos en siete dias, igual. Eso significa que un veto aislado no te tira la semana, pero un veto sobre una semana ya tocada si.

## ¿Cuando una medicion deja de ser fiable y por que el sistema se vuelve conservador aunque el semaforo no sea rojo?

Una medicion deja de ser plenamente fiable cuando el sistema no la considera `clean`, aunque tampoco la descarte como invalida del todo.

En la practica, eso significa: `el sistema desconfia de la calidad de la senal aunque no tire toda la fila a la basura`.

Esa desconfianza puede venir de problemas previos de calidad, estabilidad o completitud ya arrastrados en la medicion procesada. Cuando ocurre, `quality_flag` pasa a `True`.

Su efecto operativo es conservador:

- aunque el gate no sea rojo
- la recomendacion se restringe
- la salida pasa a `SUAVE_O_DESCANSO`
- y `Action_detail` puede marcar `SUAVE_QUALITY`

Fisiologicamente tiene sentido: una buena decision con una mala medicion sigue siendo una mala decision.

Si quieres entender en un dia concreto cuanto se aleja el dato dudoso de la lectura conservadora, puedes mirar `gate_raw_today`, `gate_raw_reason` y `unstable_note` en FINAL: son una capa de auditoria contrafactual que te dice que color habria salido si te hubieras creido el dato bruto. **No cambian la accion**; solo te ayudan a calibrar cuanta cautela aplicar manualmente.

## ¿Cuando debo ignorar el verde y ser conservador de todas formas?

Hay tres senales del sistema que **no recolorean** el verde, pero que te deberian hacer no exprimirlo:

1. **`quality_flag = True`**. El dato de hoy es dudoso. Aunque pinte verde, `Action_detail` ya se ha forzado a `SUAVE_QUALITY`. Esto no es opcional: la regla operativa del sistema dice que no se confia en un dato dudoso para justificar intensidad.
2. **`recovery_discordance_flag = True`** con `recovery_support_class` en `fragile` o `conflicted`. El gate sale razonable pero el contexto multinocturno y de carga no lo apoya. Esta clase **no cambia la accion**, asi que la decision de moderar es tuya.
3. **`flag_sistemico` rellenado a mano**. Hoy no se alimenta automaticamente, pero si tu mismo has anotado algo (viaje, enfermedad incipiente, mala noche subjetiva), trata el verde como un verde con asterisco.

Tambien hay una situacion compuesta que merece mencion aparte: **VERDE con warning de baseline largo**. Desde `PCV-02`, la lectura canónica separa dos preguntas:

- `degraded_vs_best = True`: hoy puedes estar estable, pero sigues lejos de tu mejor forma histórica.
- `degraded_vs_current_normal = True`: hoy estás en caída activa respecto a tu normal reciente.

`baseline60_degraded` se mantiene como alias legacy para consumo rápido. En modo `adaptive90` (default), equivale a `degraded_vs_current_normal`. En modo `healthy85`, equivale a `degraded_vs_best`.

Si ves un VERDE con `degraded_vs_best = True` y `degraded_vs_current_normal = False`, la lectura correcta es: estás bien respecto a tu nivel reciente, pero no es momento de interpretar ese verde como permiso para progresar carga semanal agresivamente.

---

## ¿Que significan los colores con + y -?

El color del semaforo es uno (VERDE, AMBAR, ROJO, NO). Pero `gate_badge` le pega un sufijo que viene del residual:

- `VERDE+` o `VERDE++`: tu HRV de hoy es mejor de lo que cabria esperar dado tu pulso. Lectura: doble verde.
- `VERDE-` o `VERDE--`: tu HRV es razonable, pero algo peor de lo esperable para ese pulso. El verde es valido, pero menos enfatico.
- `AMBAR-`, `AMBAR--`, `AMBAR---`: ambar con residual cada vez peor. El sistema no escala a rojo, pero el residual te dice que la diferencia con tu normal es mas profunda de lo que el ambar sugiere.
- `ROJO`, `ROJO--`, `ROJO---`: rojo, posiblemente con residual muy negativo. El triple negativo es la senal mas fuerte que el sistema puede dar sin saltar a NO.

El residual no te puede salvar de un rojo ni puede agravar un verde a ambar: solo matiza. Pero esa matizacion vale, sobre todo cuando ves `VERDE-` despues de varios `VERDE+`: el color sigue siendo el mismo, pero algo se esta moviendo por debajo.

→ Diccionario §3.F (residual y badge).

## ¿Que es el reason_text y como leerlo sin que me abrume?

`reason_text` es el unico campo del DASHBOARD que esta escrito en lenguaje humano. Es el contexto del dia condensado en una o varias frases separadas por ` | `.

Tres reglas para leerlo sin agobiarte:

1. **No hay narrativa en orden**. Cada frase es una observacion independiente; no hay un argumento que las una. Si lees tres frases, son tres senales coexistiendo, no tres pasos de un razonamiento.
2. **No cambia el gate ni la accion**. Por mucho que el texto suene preocupante, si `Action = INTENSIDAD_OK` puedes entrenar; el texto te invita a ser inteligente, no te lo prohibe.
3. **No siempre dice algo**. Muchos dias buenos tienen `reason_text` vacio. Eso significa exactamente lo que parece: no hay nada que reportar.

Las familias mas comunes de mensajes son:

- caida aguda de HRV (cuando se activa el veto)
- noche corta o fragmentada vs tus propios percentiles personales
- carga reciente alta (`load_3d`, ACWR, monotonia, strain) — si convergen, el aviso es mas fuerte
- clustering de intensidad reciente (varios dias intensos en pocos dias)
- nightly RMSSD discordante con el gate matinal
- resumen `recovery_support_class` cuando hay tension entre gate y contexto

Cuando el dia es VERDE y `reason_text` se enciende con tres o cuatro avisos, no es que tengas que tirar el verde a la basura. Es que el verde llega con caveats. La diferencia entre exprimirlo o no exprimirlo la decides tu, leyendo el texto.

→ Diccionario §3.M (familias de mensajes con ejemplos exactos).

## ¿Que es la capa RE-01 y para que sirve si no cambia el gate?

La capa RE-01 es la lectura cruzada entre el gate matinal y el contexto multinocturno + carga. Vive en cuatro columnas:

- `recovery_context_quality`: te dice si hay contexto disponible (`none`, `basic`, `rich`).
- `recovery_support_class`: clasifica la coherencia (`supported`, `neutral`, `fragile`, `conflicted`).
- `recovery_discordance_flag`: marca explicita cuando hay tension.
- `recovery_discordance_reason`: codigos estructurados que dicen *que* discrepa (por ejemplo `sleep_basic_poor`, `nightly_rmssd_low`, `load_context_high`, `recent_load_low`).

¿Por que existe si no cambia el gate? Porque cambiar el gate por contexto introduciria justo el problema que el sistema lleva tiempo evitando: que una capa secundaria contamine el decisor primario. El sistema prefiere mantener el gate fisiologico limpio y poner la disonancia en una capa explicita que tu puedas leer.

En la practica: si nunca te pasas por aqui, sigues operando con gate + Action como siempre. Si quieres lectura mas afinada, `recovery_support_class` te dice de un vistazo si el verde de hoy es solido, fragil o francamente raro.

## ¿Que pasa cuando el gate sale verde pero el contexto de sueno y carga dice otra cosa?

Esta es una de las situaciones mas confusas de la lectura diaria, y por eso el sistema le ha dedicado una capa propia: `recovery_support_class`.

La idea de fondo es honesta: un verde matinal te dice que tu fisiologia matutina esta dentro de tu normal, pero no te dice que ese verde este `bien soportado` por la noche que tuviste y por la carga que llevas.

El sistema clasifica esa coherencia en cuatro categorias:

- `supported`: el gate y el contexto van a una. Verde con buena noche y carga razonable, o rojo con noche mala y carga alta.
- `neutral`: ni mucho apoyo ni mucha contradiccion. Es el caso mas comun.
- `fragile`: el gate sale razonable pero la noche fue mediocre o la carga viene exigente. El verde existe, pero el contexto te pide cautela.
- `conflicted`: el gate es razonable y el contexto dice claramente que no deberia. O al reves: gate malo sin nada en sueno ni carga que lo explique.

Cuando aparece `fragile` o `conflicted`, el sistema activa `recovery_discordance_flag = True` y deja en `recovery_discordance_reason` los motivos concretos.

Esta capa **no cambia el color del gate**. Lo que hace es ofrecerte un resumen rapido para que decidas si te crees el verde tal cual o si conviene quitarle ambicion. En la practica: con `fragile`, no exprimas la sesion intensa que tenias planeada; con `conflicted`, mira `reason_text` antes de decidir nada.

---

## ¿Por que una HRV alta no siempre significa que estoy mejor recuperado?

Porque una HRV alta puede significar cosas distintas segun el contexto.

A veces es una senal de buena recuperacion. Otras veces puede representar un predominio parasimpatico fuera de tu rango habitual o un estado raro respecto a tu patron habitual.

Por eso el sistema no premia automaticamente una HRV alta. La interpreta respecto a:

- tu baseline
- tu pulso
- la coherencia con el resto de senales

En el `reason_text`, una HRV muy por encima de lo normal puede aparecer como `posible saturacion parasimpatica relativa al rango local`.

## ¿Que diferencia fisiologica hay entre HRV baja con pulso normal y HRV baja con pulso alto?

No son cuadros equivalentes.

Cuando la HRV baja pero el pulso sigue normal, el sistema lo lee como una senal parcial. Puede haber fatiga, estres o mala tolerancia en desarrollo, pero todavia no hay una convergencia fuerte.

Cuando ademas el pulso sube, la interpretacion cambia. Ya no es solo una perdida de variabilidad: tambien hay activacion compatible con peor recuperacion o mayor estres sistemico. Por eso esa combinacion escala a rojo.

Dicho de otra manera: el pulso alto le da mas "credibilidad biologica" a una HRV baja.

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

---

## ¿Como entran mis sesiones de entrenamiento en la decision del dia?

Las sesiones no entran en el calculo del color. Pero entran en `reason_text` con tres metricas canonicas que conviene tener en la cabeza:

- **ACWR** (`acwr_simple_prev`): cuanto pesa tu carga reciente respecto a tu carga cronica de las ultimas semanas. Si esta alto, llevas demasiada carga reciente para tu base.
- **Monotonia** (`monotony_7d_prev`): cuanto se parecen entre si tus dias de la semana. Si la monotonia es alta, llevas siete dias muy parecidos sin descanso real.
- **Strain** (`strain_7d_prev`): producto de carga total semanal por monotonia. Una semana puede tener strain alto por ser dura, por ser monotona, o por ambas.

A esto se suman senales mas cortas: `load_3d` (carga aguda de tres dias), `intense_days_prev_5d` (cuantos dias intensos llevas en cinco), y la deteccion de `intensity_clustering` cuando esos dias intensos estan apilados.

Una observacion importante: estas metricas **solo se interpretan** si `load_ctx_ready = True`, es decir, si hay al menos 14 dias con datos de carga en los ultimos 28. Si vienes de un paron, las primeras dos semanas no te avisaran de carga aunque la haya.

Y el mensaje mas util que el sistema sabe construir aqui es la `convergencia de carga`: cuando `load_3d` y al menos una de ACWR/monotonia/strain coinciden en pintar exigencia. Si ves esa convergencia con un VERDE, conviene moderar la sesion intensa que tenias planeada.

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
- avisar cuando los dias intensos estan apilados (clustering de intensidad)

Dicho simple: `sessions_day` no manda sobre el semaforo, pero si cambia la forma en que deberias interpretar ese semaforo.

## ¿Como se manifiesta una acumulacion de carga en la combinacion HRV, pulso y contexto de entrenamiento?

Cuando la carga se acumula de forma mal absorbida, lo esperable es que el sistema empiece a ver una historia coherente entre varias piezas:

- la HRV deja de sostenerse o cae
- el pulso de reposo tiende a subir o a mantenerse demasiado alto para tu patron
- las sombras se vuelven mas reactivas antes que BASE60
- `reason_text` empieza a recoger carga reciente alta, ACWR elevado, monotonia o strain semanal
- el clustering detecta intensidad mal espaciada

No siempre aparecen todas a la vez ni con la misma fuerza. A veces la carga se manifiesta primero en el contexto de entrenamiento, luego en el pulso y despues en la HRV. Otras veces el primer signo claro es una caida de HRV tras varios dias densos.

Lo importante es que el sistema intenta leer esa acumulacion como un proceso, no como un numero aislado.

## ¿Que aporta la distribucion de intensidad semanal?

El sistema mantiene un sidecar (`ENDURANCE_HRV_intensity_distribution_weekly.csv`) que clasifica cada semana por deporte en cuatro patrones:

- `polarized`: Z1 alto, algo de Z3, Z2 minimo. La distribucion preferible para resistencia.
- `pyramidal`: Z1 > Z2 > Z3 con jerarquia clara. Tambien sostenible.
- `threshold`: Z2 domina. Es el "agujero negro" de intensidad: trabajas mucho sin generar adaptacion ni acumular fatiga aparente.
- `mixed`: sin patron claro.

Cada clasificacion viene con `distribution_confidence` (`high`, `moderate`, `low`). Si la confianza es baja, no la uses para conclusiones firmes — significa que la semana tenia pocas sesiones, poca duracion total, o zonas en fallback.

Esta capa **no afecta al gate ni a `reason_text`**. Es revision retrospectiva. Sirve para mirar tres semanas atras y notar, por ejemplo, que llevas un mes en `threshold` aunque tu HRV no haya saltado: el agujero negro es exactamente eso, sabotaje silencioso.

→ Diccionario §5quinquies (columnas detalladas de la distribucion semanal).

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

## ¿Que informacion nocturna de Polar complementa la medicion matinal y cual no debe tener peso decisor?

Hoy el sistema usa de forma efectiva para contexto y RE-01:

- `polar_sleep_duration_min`
- `polar_interruptions_long`
- `polar_night_rmssd`
- `polar_sleep_score` (cuando hay Nightly Recharge disponible)

Eso le permite construir mensajes como:

- noche corta vs tus percentiles personales
- noche fragmentada
- nightly RMSSD discordante con el gate matinal
- soporte nocturno aceptable cuando sleep_score acompana

En cambio, hoy no entran en la logica del gate ni en `reason_text` estas columnas, aunque se guarden:

- `polar_night_rri`
- `polar_night_resp`
- `polar_continuity`, `polar_continuity_index`
- `polar_efficiency_pct`

Y tambien es importante lo que no existe como columna operativa separada: hoy no hay un ANS Charge canonico que participe en la decision.

---

## ¿Que diferencia conceptual hay entre CORE, BETA_AUDIT, FINAL y DASHBOARD en la lectura de mi estado fisiologico?

Cada archivo cumple una funcion distinta en la lectura del sistema:

- `CORE`: es la capa fisiologica canonica. Guarda la medicion ya procesada y metricas como `lnRMSSD`, `SI_baevsky`, `SD1` y `SD2`.
- `BETA_AUDIT`: es una salida legacy de auditoria V3. Sirve para trazabilidad historica, no para decidir el gate actual.
- `FINAL`: es la capa de decision completa (62 columnas). Aqui viven baseline, SWC, deltas, veto, sombras, residual, gate final, accion, capa RE-01 y reason_text.
- `DASHBOARD`: es una vista resumida (10 columnas) para leer lo importante sin tragarte toda la auditoria.

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
- `decision_path`, `override_reason`
- `veto_agudo`, `ln_pre_veto`, `swc_ln_floor`
- `residual_ln`, `residual_z`, `residual_tag`

Y las columnas que ayudan sobre todo a interpretar el dia son:

- `gate_badge` (color + matiz del residual, lo que miras a diario)
- `reason_text`
- `recovery_support_class`, `recovery_discordance_flag`, `recovery_discordance_reason`
- `baseline60_degraded`
- `bad_streak`, `bad_7d`

En otras palabras: unas columnas deciden, otras explican y otras contextualizan.

## ¿Por que el sistema separa decision operativa y metricas de auditoria?

Porque decidir y entender no son exactamente la misma tarea.

Si metieras todas las metricas disponibles en la decision diaria, el sistema seria mas fragil, mas opaco y probablemente mas nervioso. Al separar capas, el sistema logra dos cosas:

- mantener una decision diaria relativamente sobria y estable
- conservar suficiente auditoria para revisar despues por que salio ese color

Esa separacion es sana. Permite que el semaforo no dependa de veinte senales a la vez, pero evita tambien la caja negra total.

## ¿Que papel tienen SI_baevsky y SD1/SD2 en el sistema actual?

Hoy su papel es informativo.

Se calculan y se guardan en CORE porque aportan lectura fisiologica adicional:

- `SI_baevsky` puede sugerir activacion simpatica
- `SD1/SD2` ayuda a leer la geometria de la variabilidad

Pero actualmente:

- no recolorean el gate
- no activan veto
- no cambian `Action`
- **no se replican en FINAL ni DASHBOARD** — si los necesitas, debes leerlos directamente desde CORE

Su valor hoy es de auditoria e interpretacion experta, no de mando operativo.

## ¿Que factores explicativos entran en reason_text y por que algunos datos disponibles no se usan para decidir?

`reason_text` no es un espejo de todos los datos disponibles. Es un texto corto con factores contextuales que el sistema considera utiles para interpretar el dia.

Las familias actualmente activas son:

- caida aguda de HRV (cuando se activa el veto agudo)
- HRV inusualmente alta respecto al rango local
- noche corta o noche larga atipica vs tus propios percentiles
- noche fragmentada vs tu propio P90
- carga aguda alta (`load_3d`)
- carga canonica alta (ACWR, monotonia o strain)
- convergencia de carga (cuando `load_3d` coincide con al menos una canonica)
- clustering de intensidad reciente (`intense_days_prev_3d/5d`)
- nightly RMSSD discordante con el gate matinal
- resumen `recovery_support_class` (verde fragil, ambar con apoyo, rojo discordante…)

Y se quedan fuera, aunque existan en CSV:

- `SI_baevsky`, `SD1`, `SD2`, `SD1_SD2_ratio`
- `polar_night_rri`, `polar_night_resp`
- `polar_continuity`, `polar_efficiency_pct`
- el wellness subjetivo (`fatigue`, `stress`, `mood`, `motivation`, `soreness`, `injury`) — vive en su propio sidecar, reservado para analisis retrospectivo
- residual y sombras como explicacion textual automatica
- cualquier ANS Charge diferenciado (no existe operativamente)

¿Por que se quedan fuera? Porque `reason_text` busca ser explicativo sin convertirse en informe infinito ni en segundo decisor paralelo.

## ¿Que cosas no deberia prometer este notebook como si ya existieran?

No deberia presentar como vigentes, salvo que el codigo cambie de verdad:

- Studio o pestanas nuevas de analitica
- reportes mensuales generados por la app
- KPI automaticos de falsos verdes
- ANS Charge operativo como entrada del gate
- metricas Tier 3 accionables como SampEn (DFA-α1 existe en analysis local de sesion, pero **no** en el decisor diario)
- protocolos ICC integrados en el flujo productivo
- coach semanal estructurado en producto (sigue en `PENDIENTE`)
- baseline adaptativo a largo plazo (sigue en `PENDIENTE`)
- capa de carga relativa del atleta (sigue en `PENDIENTE`)
- SWC configurable o adaptativo (sigue en `PENDIENTE`)
- planning note semanal automatica (sigue en `PENDIENTE`)
- integracion UI/API del coach semanal (sigue en `PENDIENTE`)

Si alguna de esas ideas se quiere conservar, mejor ponerla como `futuro` o `experimental`, no como comportamiento actual.

## ¿Para que sirve entonces este notebook si ya existe un diccionario?

El diccionario te dice `que significa una columna`.

Este notebook debe decirte algo distinto: `como razona el sistema`, `por que separa unas senales de otras`, `que manda de verdad`, `que solo contextualiza` y `que errores de interpretacion conviene evitar`.

Ese es su valor. No repetir la tabla de columnas, sino traducir la logica del sistema a preguntas humanas bien respondidas.

---

Fin del documento.
