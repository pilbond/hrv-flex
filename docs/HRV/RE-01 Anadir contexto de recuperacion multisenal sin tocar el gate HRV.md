# RE-01 Anadir contexto de recuperacion multisenal sin tocar el gate HRV

## Objetivo

Anadir una capa objetiva y transparente de contexto de recuperacion que combine la senal fisiologica ya existente con sueno Polar y carga reciente, sin sustituir al gate HRV como arbitro principal.

Esta tarea debe mantenerse separada de `RE-02`, que cubre wellness subjetivo de Intervals (`fatigue`, `stress`, `mood`, `motivation`, `soreness`, `injury`).

## Tesis principal

El proyecto actual ya tiene un gate diario conceptualmente fuerte basado en convergencia de `lnRMSSD + HR_stable`, por lo que `RE-01` no deberia introducir un nuevo arbitro paralelo ni un score que compita con el semaforo.

El valor real de `RE-01` es otro:

- detectar discordancias entre el gate y las senales objetivas de soporte;
- aumentar la resolucion interpretativa de `reason_text` o de `reason_items`;
- y contextualizar mejor algunos dias `VERDE`, `AMBAR` o `ROJO` sin tocar la decision principal.

La lectura correcta de esta tarea no es `crear un nuevo recovery index`, sino `cerrar el ciclo` cuando las otras capas ya existen:

- `CDC-01` aporta contexto de carga mejor formalizado;
- `AP-01` aporta clustering proactivo;
- `RE-02` aporta subjetivo;
- `SS-01` ordena la salida semantica.

En ese contexto, `RE-01` se convierte en una capa ligera de integracion y discordancia objetiva.

## Situacion actual del repo

Hoy el repo ya usa tres capas relevantes:

### 1. Gate HRV principal

En `build_hrv_final_dashboard.py`, la decision central se construye con:

- `lnRMSSD`
- `HR_stable`
- reglas de baseline y sombras

Ese gate ya cumple el papel de arbitro principal de readiness.

### 2. Sueno Polar como sidecar contextual

`ENDURANCE_HRV_sleep.csv` ya aporta:

- `polar_sleep_duration_min`
- `polar_interruptions_long`
- `polar_sleep_score`
- `polar_night_rmssd`
- `polar_night_rri`
- `polar_night_resp`
- percentiles derivados de duracion e interrupciones

Hoy esas senales entran solo en `reason_text` con reglas puntuales como:

- `Noche corta`
- `Noche fragmentada`
- `VERDE pero nightly_rmssd bajo`
- `ROJO con nightly_rmssd alto`

### 3. Carga reciente

`ENDURANCE_HRV_sessions_day.csv` ya aporta contexto de carga:

- `load_3d`
- `work_7d_sum`
- `z3_7d_sum`

## Que aporta el proyecto base

El proyecto de referencia usa una capa wellness/readiness mas explicita con metricas como:

- `RestingHR`
- `RestingHRDelta`
- `SleepQuality`
- `HRVBalance`
- `HRVDeviation`
- `AutonomicStatus`
- `load_recovery_state`

Y en su documentacion aparece la idea de un `Recovery Index` compuesto.

La parte trasladable aqui no es tanto el indice como tal, sino esta idea:

- fusionar varias senales objetivas de recuperacion en una lectura contextual coherente;
- sin quitarle el mando a la senal fisiologica principal.

## Hallazgos cuantitativos sobre el pipeline actual

Sobre los datos actuales:

- `FINAL`: 313 filas
- `CORE`: 313 filas
- `sleep.csv`: 323 filas

Cobertura sobre `FINAL`:

- `lnRMSSD + HR_stable`: 99.0%
- `HRV + HR + sleep_duration`: 94.2%
- `sleep_score` o `nightly_rmssd`: 26.2%

Distribucion actual del gate:

- `VERDE`: 151
- `ROJO`: 77
- `NO`: 45
- `AMBAR`: 40

Observaciones relevantes:

- el contexto basico de recuperacion ya tiene cobertura casi diaria;
- el contexto nocturno rico (`sleep_score`, `nightly_rmssd`) existe, pero no cubre toda la serie;
- por tanto, un score compuesto que dependa de senales ricas no seria estable como salida diaria universal.

## Donde esta el valor real de RE-01

El valor principal de `RE-01` no esta en inventar un nuevo numero 0-1 ni en crear otra clase del ANS, sino en detectar cuando el gate y las senales objetivas de soporte cuentan historias distintas.

Ejemplos de valor:

- `VERDE` con carga alta y noche peor de lo esperado
- `AMBAR` con recuperacion nocturna aceptable
- `ROJO` con sueno no malo y poca carga previa, que obliga a interpretar con cautela

Esto mejora la explicacion operacional aunque no cambie el color del dia.

## Que no conviene hacer

- no sustituir el gate HRV por un `Recovery Index`;
- no recalcular otra clase autonómica paralela al gate;
- no duplicar `HRV` o `restingHR` con fuentes menos canonicamente controladas;
- no depender de `sleep_score` como senal diaria obligatoria;
- no mezclar en esta tarea los subjetivos de wellness, que ahora viven en `RE-02`.

## Propuesta de implementacion

### Fase 1. No crear un CSV nuevo
Toda la logica puede vivir dentro de `build_hrv_final_dashboard.py`, que ya junta:

- `CORE`
- `sleep.csv`
- `sessions_day.csv`

Si hace falta trazabilidad, es preferible anadir unas pocas columnas a `FINAL` antes que crear un `ENDURANCE_HRV_recovery_context.csv` nuevo.

Columnas minimas razonables:

- `recovery_support_class`
- `recovery_discordance_flag`
- `recovery_discordance_reason`

Importante:

- estos nombres deben entenderse de momento como candidatos semanticos, no como contrato cerrado;
- los nombres exactos de columna para `FINAL` deben confirmarse despues del analisis cuantitativo de la Fase 5;
- ese analisis puede mostrar, por ejemplo, que `recovery_discordance_flag` basta y que `recovery_support_class` es redundante o poco discriminativa.

### Fase 2. Separar soporte basico y soporte rico

#### Contexto basico

Usar siempre que haya datos:

- `lnRMSSD` relativo a baseline
- `HR_stable` relativo a baseline
- `polar_sleep_duration_min`
- `polar_interruptions_long`
- `load_3d` o carga reciente

#### Contexto rico

Usar solo cuando exista:

- `polar_sleep_score`
- `polar_night_rmssd`

Esto permite una degradacion limpia por cobertura.

### Fase 3. Reglas transparentes de discordancia, no score opaco

Ejemplos de clases:

- `supported`
- `neutral`
- `fragile`
- `conflicted`

Ejemplos de reglas:

- `VERDE + carga alta + sueno flojo -> fragile`
- `VERDE + clustering reciente + mala noche -> fragile`
- `AMBAR + soporte bueno -> neutral o supported`
- `ROJO + nightly alto + poca carga previa -> conflicted`

El foco debe estar en:

- cuando las capas objetivas ya apoyan al gate;
- y, sobre todo, cuando cuentan una historia distinta.

### Fase 4. Integracion en FINAL

En `build_hrv_final_dashboard.py`, anadir mensajes en `reason_text` o `reason_items` tipo:

- `Recuperacion nocturna peor de lo esperado pese a gate verde`
- `AMBAR con sueno correcto: limitar intensidad pero posible Z2 controlado`
- `ROJO con discordancia nocturna: interpretar con cautela`

Sin tocar:

- `gate_final`
- `Action`
- `Action_detail`

al menos en v1.

Si `SS-01` esta disponible, estos mensajes deberian salir como items tipados de capa `inference`, no solo como texto libre.

### Fase 5. Analisis cuantitativo previo
Antes de cerrar reglas, conviene medir sobre el historico:

- cuantos dias caerian en `fragile`
- cuantos en `conflicted`
- y cuantos casos no estan ya cubiertos por el `reason_text` actual

Sin ese analisis, las reglas quedan demasiado conceptuales.

### Fase 6. Auditoria de cobertura

Anadir indicadores tipo:

- `recovery_context_coverage`
- `recovery_context_quality`

para no vender precision falsa en dias sin senales ricas.

## Mejora medible esperable

La mejora defendible es:

- formalizar una lectura de discordancia objetiva con cobertura basica alta (`94.2%` con HRV+HR+sleep basico);
- enriquecer la interpretacion en dias donde ya hay senales, pero aun no se verbalizan como historia cruzada;
- aumentar la consistencia entre `CORE`, `sleep.csv`, `sessions_day.csv` y `reason_text`.

No conviene venderla como una revolucion del gate, sino como una mejora de interpretabilidad, trazabilidad y coherencia contextual.

## Recomendacion final

Implementar `RE-01` como capa ligera de discordancia objetiva y mantener `RE-02` para wellness subjetivo.

La frontera correcta queda asi:

- `RE-01`: coherencia o discordancia entre gate y soporte objetivo (HRV, sueno Polar, carga reciente)
- `RE-02`: recuperacion subjetiva, basada en wellness de Intervals

Timing recomendado:

- `RE-01` aporta su maximo valor despues de `CDC-01`, `AP-01`, `SS-01` y preferiblemente `RE-02`;
- antes de esas tareas, tiende a reconstruir de forma parcial cosas que otras capas ya resolveran mejor.

Esa separacion es mas limpia, mas auditable y mas compatible con la arquitectura actual del repo.
