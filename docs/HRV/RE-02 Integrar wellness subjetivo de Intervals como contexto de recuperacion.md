

## Objetivo

Crear una tarea separada de `RE-01` para incorporar al sistema los campos subjetivos de wellness de Intervals que hoy aportan informacion nueva y no redundante respecto al pipeline HRV actual.

Campos objetivo:

- `fatigue`
- `stress`
- `mood`
- `motivation`
- `soreness`
- `injury`

La idea no es sustituir el gate HRV ni duplicar senales ya cubiertas por Polar o por `CORE`, sino anadir una capa subjetiva estructurada de contexto de recuperacion.

Tambien debe tenerse en cuenta que, ademas de los campos estructurados, existe un campo libre de comentarios en Intervals que puede aportar contexto cualitativo adicional.

## Por que esta tarea debe separarse de RE-01

`RE-01` estaba formulada como una capa multisenal amplia o incluso como un posible `Recovery Index` compuesto. Eso mezcla dos discusiones distintas:

1. integrar mejor sueno/HRV/carga en una lectura contextual;
2. anadir bienestar subjetivo del atleta.

El segundo bloque merece una tarea propia porque:

- usa una fuente distinta: wellness de Intervals;
- introduce senales nuevas, no solo recombinaciones de las ya existentes;
- tiene semantica distinta: percepcion subjetiva, no readiness fisiologico directo.

## Situacion actual del repo

Hoy el pipeline canonico usa sobre todo:

- `lnRMSSD` y `HR_stable` desde `CORE`
- sueno Polar desde `ENDURANCE_HRV_sleep.csv`
- carga reciente desde `ENDURANCE_HRV_sessions_day.csv`

No existe una capa canonica activa que consuma wellness subjetivo de Intervals en `FINAL`.

Sin embargo, hay evidencia clara de que esos datos si existen:

- la API de Intervals devuelve campos como `fatigue`, `stress`, `mood`, `motivation`, `soreness` e `injury`;
- el codigo actual empuja wellness a Intervals, pero no lo integra como input canonico del decisor.

Decision de fuente:

- no usar el CSV local historico de wellness como base de esta tarea;
- la fuente canonica de `RE-02` debe ser Intervals vivo, porque ahi es donde se rellena la parte subjetiva relevante.

## Datos observados en la API de Intervals

Analisis reciente sobre los ultimos 61 dias recuperados desde la API:

- `sleepQuality`: 98.4%
- `sleepScore`: 98.4%
- `sleepSecs`: 98.4%
- `restingHR`: 98.4%
- `readiness`: 93.4%
- `soreness`: 62.3%
- `fatigue`: 62.3%
- `stress`: 62.3%
- `mood`: 62.3%
- `motivation`: 62.3%
- `injury`: 62.3%

En las ultimas 3 semanas, los campos subjetivos de la captura muestran una cobertura mejor:

- `sleepQuality`: 100%
- `soreness`: 79.2%
- `fatigue`: 79.2%
- `stress`: 79.2%
- `mood`: 79.2%
- `motivation`: 79.2%
- `injury`: 79.2%

Eso ya es suficiente para considerarlos contexto util.

## Que aportan estos campos que hoy no tenemos

Estos campos anaden una capa que el HRV y el sueno objetivo no cubren bien:

- `fatigue`: cansancio percibido general
- `stress`: carga no entrenante y tension psicofisiologica
- `mood`: tono afectivo diario
- `motivation`: disposicion mental para entrenar
- `soreness`: carga periferica o dano muscular percibido
- `injury`: estado de lesion o molestia estructural

Esto puede explicar dias con:

- HRV razonable pero sensacion subjetiva mala
- gate verde con dolor o motivacion baja
- sueño correcto pero estres alto

Ademas, el campo libre de comentarios puede capturar matices que no caben bien en escalas cerradas:

- explicacion breve del estres o del dolor
- contexto laboral o vital
- nota sobre molestia concreta
- percepcion subjetiva que no encaja en un unico slider

## Mejora medible esperable

La mejora mas defendible no es cambiar el gate, sino aumentar el contexto interpretable:

- pasar de 0 campos subjetivos canonicos a 6 campos subjetivos utililes
- disponer de cobertura reciente cercana al 80% en las ultimas 3 semanas para esos 6 campos
- enriquecer `reason_text` y la lectura operativa en dias donde la fisiologia no cuenta toda la historia

Limitacion temporal importante:

- estos campos no deben tratarse como explicacion causal del gate HRV de esa misma manana;
- su funcion principal en v1 debe ser contextualizar el dia y la decision operativa, no reinterpretar retroactivamente la medicion fisiologica.

## Propuesta de implementacion

### 1. Ingesta canonica nueva

Crear un flujo de lectura de wellness desde Intervals y persistirlo como CSV canonico diario, por ejemplo:

- `ENDURANCE_HRV_wellness_subjective.csv`

Columnas iniciales:

- `Fecha`
- `well_fatigue_raw`
- `well_stress_raw`
- `well_mood_raw`
- `well_motivation_raw`
- `well_soreness_raw`
- `well_injury_raw`
- `well_comment_raw`

Columnas derivadas recomendadas:

- `well_fatigue_label`
- `well_stress_label`
- `well_mood_label`
- `well_motivation_label`
- `well_soreness_label`
- `well_injury_label`

No incluir en la capa canonica principal `sleepScore`, `sleepQuality` o `readiness` de Intervals salvo para auditoria, porque se solapan con fuentes objetivas ya presentes en el repo.

### 2. Normalizacion semantica

Mapear escalas de Intervals a etiquetas transparentes:

- `fatigue`: bajo / medio / alto / extremo
- `stress`: bajo / medio / alto / extremo
- `mood`: genial / bueno / aceptar / grunon
- `motivation`: extremo / alto / promedio / bajo
- `soreness`: bajo / promedio / alto / extremo
- `injury`: ninguna / niggle / pobre / lesionado

Mantener tambien el valor numerico bruto.

Debe fijarse por contrato el mapping numerico exacto una vez validado contra la API viva.

Regla de activacion:

- las reglas operativas de `RE-02` no deben activarse hasta que el mapping numerico -> etiqueta quede fijado en contrato;
- evitar implementar umbrales flotantes o dependientes de interpretacion ad hoc antes de congelar esa correspondencia.

### 3. Cobertura y fiabilidad

Anadir columnas de auditoria:

- `wellness_subjective_available`
- `wellness_subjective_n_fields`
- `wellness_subjective_coverage_7d`

Esto evita sobrerrepresentar dias con datos parciales.

Uso recomendado de `wellness_subjective_coverage_7d`:

- si `wellness_subjective_coverage_7d < 50%`, degradar la confianza de la capa a `informational`;
- en ese caso, evitar mensajes contextuales fuertes salvo que exista `injury` o una senal especialmente relevante y persistente.

Regla de fuente:

- la fiabilidad de esta capa depende de que el atleta rellene Intervals con disciplina razonable;
- esto debe quedar explicitado como parte del contrato de entrada.

### 4. Consumo en FINAL

En `build_hrv_final_dashboard.py`, leer esta nueva capa y anadir mensajes contextuales tipo:

- `VERDE con fatigue alto: vigilar carga subjetiva`
- `VERDE con stress alto: precaucion con intensidad`
- `ÁMBAR con motivacion baja y soreness alto: mejor Z1 o descarga`
- `Lesion/molestia reportada: evitar sobreinterpretar readiness fisiologico`

Sin tocar el gate en v1.

Regla temporal de alineacion:

- reindexar a calendario continuo;
- usar `ffill(limit=1)` o `limit=2` para `fatigue`, `stress`, `mood`, `motivation` y `soreness`;
- usar una persistencia mas larga para `injury`, por ejemplo `ffill(limit=3)` o `limit=5`;
- leer esta capa en paralelo al HRV, como contexto operativo del dia, no como causa del gate.

### 5. Reglas prudentes

No usar un score unico al inicio. Mejor reglas transparentes:

- `stress >= alto`
- `fatigue >= alto`
- `soreness >= alto`
- `injury != ninguna`
- combinaciones tipo `fatigue alto + motivacion baja`

Peso operativo recomendado:

- `injury`
- `soreness`
- `fatigue`
- `stress`
- `motivation`
- `mood`

`mood` y `motivation` aportan mejor en combinacion que como señal principal aislada.

Significado de `peso operativo`:

- determina tanto la prioridad del mensaje en `reason_text` como su capacidad para disparar reglas por si solo;
- los campos de mayor peso (`injury`, `soreness`, `fatigue`) pueden justificar mensaje contextual sin apoyo adicional;
- los campos de menor peso (`motivation`, `mood`) deberian entrar sobre todo en combinacion con otras senales.

### 6. Fase posterior

Si funciona bien, se podria crear una clase derivada tipo:

- `subjective_recovery_context = supportive / neutral / fragile / compromised`

pero solo despues de medir cobertura real y estabilidad temporal.

## Recomendacion final

Crear esta tarea por separado de `RE-01` es correcto.

`RE-02` deberia centrarse en integrar wellness subjetivo de Intervals como contexto estructurado, no como arbitro del sistema. El mayor valor nuevo esta en `fatigue`, `stress`, `mood`, `motivation`, `soreness` e `injury`, porque esos campos si cubren una dimension que hoy el pipeline no modela.

Si `SS-01` esta disponible, esta capa deberia integrarse ademas via `reason_items` tipados, por ejemplo:

- `wellness_fatigue_high`
- `wellness_stress_high`
- `wellness_soreness_high`
- `wellness_injury_reported`

con `injury` tratado como estado especialmente persistente y operativo.
