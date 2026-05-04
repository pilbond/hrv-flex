## Objetivo
Reformular `FP-01` como una tarea de **validacion y acotacion** de un proxy mecanico de sostenimiento en sesiones largas.

La idea fisiologica sigue teniendo sentido: complementar `cardiac_drift_pct` con una lectura sobre si el output mecanico se sostiene bajo fatiga.

Lo que ya no tiene sentido es tratar `FP-01` como si la "Parte A" estuviera pendiente o como si ya existiera base suficiente para fijar un `Durability Index` operativo.

## Estado real del repo (2026-04-10)
### AP-02 ya cubrio la Parte A basica
`AP-02` ya anadio en `sessions.csv` la capa mecanica minima para deportes de pie:

- `speed_first_half`
- `speed_second_half`
- `cadence_first_half`
- `cadence_second_half`
- `run_power_*`
- `mechanics_source`

Referencias:

- `polar_sessions.py`
- `build_sessions.py`
- `docs/contracts/ENDURANCE_HRV_Sessions_Schema.md`

Por tanto, `FP-01` no debe seguir describiendo como pendiente la persistencia por mitades para `road_run`, `trail_run` y `hike`.

### Cobertura observada hoy
En `data/ENDURANCE_HRV_sessions.csv` a fecha `2026-04-10`:

- sesiones largas `>120 min`: `79`
- sesiones largas con alguna capa mecanica persistida: `19`
- esas `19` son solo de deportes de pie:
  - `trail_run`: `10`
  - `hike`: `7`
  - `road_run`: `2`
- `bike` largo con mecanica canonica en `sessions.csv`: `0`

Conclusion:

- la cobertura mecanica existe;
- pero sigue siendo estrecha;
- y no cubre el deporte dominante del historico largo (`bike`).

## Donde esta hoy el hueco real
El subconjunto teoricamente mas interesante para `FP-01` no es "todas las sesiones largas", sino las largas donde el drift cardiaco no parece alarmante.

En el dataset actual:

- sesiones largas `easy` o `work_steady` con `cardiac_drift_pct < 5`: `35`
- de esas, solo `10` tienen `speed_first_half/speed_second_half`
- de esas `10`, solo `1` es `road_run`

Ademas, en esa muestra mecanica de bajo drift:

- no hay ningun caso con ratio `<0.9`
- no hay ningun caso con ratio `<0.8`

Eso invalida usar hoy umbrales tipo `0.8` o `0.9` como si ya estuvieran soportados por backtesting local.

## Problemas metodologicos pendientes
### 1. La tarjeta solapa con AP-02
La persistencia por mitades ya esta hecha para deportes de pie.

Si `FP-01` sigue adelante, su alcance real solo puede ser uno de estos:

- anadir ventanas horarias (`speed_first_hour`, `speed_last_hour`) y su semantica explicita;
- o estudiar una extension especifica a `bike`.

### 2. Falta semantica temporal explicita
Hoy las mitades se calculan partiendo la serie por indice de muestra y filtrando despues.

Eso significa:

- no es una "primera hora" real;
- no decide entre `elapsed` y `moving`;
- y en sesiones con pausas puede cambiar mucho la interpretacion.

En `hike`, esto no es menor:

- sesiones largas de pie con `duration_min - moving_min >= 10`: `6`
- todas esas `6` son `hike`

Por tanto, antes de hablar de `first_hour/last_hour` hay que fijar una semantica:

- `elapsed`
- `moving`
- o ambas con `applicability/confidence`

### 3. No hay trimming de warmup/cooldown
El pipeline actual no recorta explicitamente warmup/cooldown para esta capa mecanica.

Riesgo:

- una sesion continua y bien sostenida puede parecer peor solo por estructura de entrada/salida;
- el sesgo afecta justo a la comparacion `first vs last`.

Si se trabaja esta tarea, hay que definir antes un recorte minimo:

- por tiempo fijo;
- por deteccion de tramo util;
- o por condiciones de intensidad/velocidad.

### 4. No se separa continuidad de estructura por bloques
La lectura de durabilidad mecanica solo tiene sentido razonable en sesiones relativamente continuas.

Pero en las `19` sesiones largas con mecanica:

- `12` tienen al menos `1` bloque de trabajo
- `7` tienen `>=3` bloques

Eso obliga a introducir una puerta de aplicabilidad antes de usar el ratio como inferencia:

- exigir `easy` o `work_steady` muy continuo;
- o excluir sesiones con demasiados bloques;
- o bajar mucho la confianza cuando la estructura no sea continua.

### 5. Bike no esta resuelto
El historico largo esta dominado por `bike`, pero la capa AP-02 no canoniza mecanica para `bike`.

Sin potencia real:

- la velocidad es un proxy debil;
- la cadencia podria ayudar, pero no esta validada;
- y no conviene inventar un `Durability Index` universal.

## Re-escoping recomendado
### Parte A: ya completada
Marcar explicitamente como completado:

- persistencia por mitades para deportes de pie via `AP-02`

### Parte B: si merece hacerse ahora
Limitar `FP-01` a preparacion de dato y validacion metodologica:

1. definir si la ventana operativa sera por `moving` o por `elapsed`
2. anadir ventanas horarias reales:
   - `speed_first_hour`
   - `speed_last_hour`
   - opcionalmente `cadence_first_hour`
   - opcionalmente `cadence_last_hour`
3. definir trimming minimo de warmup/cooldown
4. definir `durability_applicable`, `durability_source` y `durability_confidence`
5. exigir backtesting local antes de fijar cualquier umbral

### Parte C: lo que no debe hacerse aun
No conviene cerrar todavia:

- un `mechanical_durability_proxy` universal por velocidad
- umbrales `0.8/0.9` como regla operativa
- integracion en `reason_text` o `FINAL`
- extension a `bike` sin estudio previo de potencia/cadencia

## Backtesting minimo exigible antes de cerrar FP-01
Antes de pasar de "tarea exploratoria" a "metrica operativa", hay que documentar al menos:

1. cuantas sesiones cumplen el filtro candidato exacto
2. cuantas de ellas tienen mecanica usable
3. distribucion real de ratios observados
4. cuantos casos con drift bajo muestran drop mecanico creible
5. en que deportes aparece senal interpretable
6. como cambia el resultado usando `elapsed` frente a `moving`

Sin esto, la tarea no deberia considerarse lista para definir thresholds.

## Decision practica
`FP-01` si tiene sentido, pero no como estaba redactada.

La version defendible hoy es esta:

- `AP-02` ya cubrio la base mecanica por mitades para deportes de pie
- `FP-01` debe pivotar a ventanas horarias reales, semantica temporal, filtros de aplicabilidad y backtesting
- si eso no se va a hacer ahora, es mejor congelar la tarea que introducir un ratio con semantica debil

## Siguiente paso recomendado
Si se quiere seguir con `FP-01`, el siguiente entregable correcto no es una metrica final, sino un mini-spike con:

1. definicion `moving` vs `elapsed`
2. propuesta de trimming
3. filtro de sesiones continuas
4. backtest sobre las sesiones largas candidatas

Solo despues de ese spike tendria sentido decidir si existe o no una v1 operativa de durability mecanica.

## Diseno acordado para seguir

### Objetivo practico

Usar `FP-01` en `analysis/` como una capa local de interpretacion de sesion, no como senal canonicamente cerrada del pipeline HRV.

La pregunta que debe responder no es "cual es el indice final de durabilidad", sino esta:

- hubo deriva cardiovascular sin caida clara de output
- hubo caida mecanica compatible con fatiga
- o la lectura es ambigua por terreno, pacing o estructura

### Regla de arquitectura

Separar dos capas:

1. `sessions.csv` conserva solo primitivas reutilizables, estables y bien definidas
2. `analysis/` construye el contexto interpretativo y el lenguaje fisiologico

Esto evita empujar una semantica aun abierta a `FINAL`, `reason_text` o al contrato HRV global.

## Scope definitivo de `sessions.csv`

### Debe persistir

- `decoupling` de Intervals tal como lo expone la fuente
- `run_power_first_half`
- `run_power_second_half`
- `speed_first_half`
- `speed_second_half`
- `cadence_first_half`
- `cadence_second_half`
- `durability_applicable`

### Puede persistir como derivada simple

- `power_ratio = run_power_second_half / run_power_first_half`
- `speed_ratio = speed_second_half / speed_first_half`

### No debe persistir aun como semantica cerrada

- `mechanical_fatigue_flag`
- `durability_score`
- `durability_pattern`
- thresholds operativos finales
- cualquier integracion en `FINAL` o `reason_text`

## Scope definitivo de `analysis`

### Regla de naming

`analysis/` ya tiene hoy un `composite_context.durability_context` exploratorio por tercios de `session_stream.csv`.

Ese bloque NO debe reinterpretarse silenciosamente como la salida de `FP-01`.

Para evitar colision semantica:

- el contexto actual por tercios debe seguir tratado como exploratorio local de streams
- la capa nueva de `FP-01` debe vivir como `analysis_only_context.durability_context`
- opcionalmente puede reflejarse en `session_payload.json` como alias plano `durability_context` para consumo del analista, pero sin sobrescribir el bloque exploratorio existente en `composite_context`

### Contrato propuesto de `analysis_only_context.durability_context`

Campos minimos:

- `version`: `fp01_v1`
- `source_scope`: `sessions_csv_primitives`
- `applicable`: `true/false`
- `applicability_reason`: lista corta o string con motivo principal si `false`
- `preferred_signal`: `power_ratio`, `speed_ratio` o `none`
- `decoupling_pct`
- `power_ratio`
- `speed_ratio`
- `mechanics_source`
- `run_power_available`
- `terrain_sensitivity`: `low`, `medium`, `high`
- `interpretation_confidence`: `low`, `medium`, `high`
- `durability_pattern`
- `method`
- `notes`

### Semantica de cada campo

- `applicable`: la sesion cumple el filtro minimo para leer sostenimiento mecanico
- `preferred_signal`: prioriza `power_ratio` cuando exista potencia util; si no, cae a `speed_ratio`
- `terrain_sensitivity`: cuanto puede contaminar el terreno la lectura del output observado
- `interpretation_confidence`: confianza agregada para la lectura narrativa, no validez fisiologica absoluta
- `durability_pattern`: clasificacion narrativa local del caso; no contrato canonico global

## Taxonomia inicial permitida en `analysis`

Valores iniciales de `durability_pattern`:

- `not_applicable`
- `cardiovascular_drift_only`
- `mechanical_drop_with_drift`
- `mechanical_drop_without_drift`
- `ambiguous_due_to_terrain`
- `ambiguous_due_to_structure`
- `stable_output`
- `mixed_signal`

Reglas:

- es una taxonomia local de `analysis/`
- puede evolucionar sin tocar el contrato HRV canonico
- no debe reciclarse como bandera operativa diaria en `FINAL`

## Reglas de interpretacion v1

### Prioridad de senales

1. si `run_power_available = 1`, la senal principal es `power_ratio`
2. si no hay potencia util, usar `speed_ratio` con mas cautela
3. `decoupling` nunca sustituye al ratio mecanico; se interpreta en paralelo

### Heuristicas narrativas iniciales

- `decoupling` alto + `power_ratio` estable -> `cardiovascular_drift_only`
- `decoupling` alto + `power_ratio` bajo -> `mechanical_drop_with_drift`
- `power_ratio` bajo + `decoupling` bajo o neutro -> `mechanical_drop_without_drift`
- `speed_ratio` bajo en `trail_run` o `hike` sin potencia -> priorizar `ambiguous_due_to_terrain` salvo contexto fuerte en contra
- sesion con muchos bloques o estructura muy fragmentada -> `ambiguous_due_to_structure`
- ratios estables y deriva contenida -> `stable_output`

### Restricciones explicitas

- no interpretar `speed_ratio > 1` como "mejora fisiologica" en `hike` sin contexto de elevacion
- no tratar `speed_ratio` como equivalente a `power_ratio`
- no tratar `decoupling` como prueba de fatiga periferica por si solo

## Regla de fuente para `analysis`

`FP-01` v1 debe construirse primero desde `sessions.csv` y sus primitivas ya canonizadas.

Puede enriquecerse despues con:

- `terrain_context`
- `terrain_fit_context`
- `structured_workout`
- `route_context`

Pero la lectura base no debe depender de recalculos ad hoc sobre `session_stream.csv` si la primitiva ya existe en `sessions.csv`.

## Criterio de aceptacion revisado

La tarea puede darse por bien encaminada si:

1. `sessions.csv` conserva solo primitivas y derivadas simples
2. `analysis/` expone un `durability_context` local, trazable y separado del exploratorio por tercios
3. la documentacion deja claro que esta capa no afecta a `FINAL`, `DASHBOARD` ni `reason_text`
4. existe taxonomia minima local para el analista
5. existen tests de contrato en `analysis` para casos representativos de:
   - drift sin caida mecanica
   - caida mecanica con drift
   - caida de velocidad ambigua por terreno
   - no aplicable por estructura o duracion

## Estado actual de la tarea

### Cerrado

Pertenece ya a `FP-01` y puede considerarse resuelto o suficientemente encaminado:

1. persistencia de primitivas y derivadas simples en `sessions.csv`
   - `run_power_first_half`
   - `run_power_second_half`
   - `speed_first_half`
   - `speed_second_half`
   - `cadence_first_half`
   - `cadence_second_half`
   - `durability_applicable`
   - `speed_ratio`
   - `power_ratio`

2. capa local de `analysis` separada del exploratorio por tercios
   - `analysis_only_context.durability_context`
   - alias plano `session_payload.json.durability_context`
   - sin reusar silenciosamente `composite_context.durability_context`

3. taxonomia local minima de `durability_pattern`
   - `not_applicable`
   - `cardiovascular_drift_only`
   - `mechanical_drop_with_drift`
   - `mechanical_drop_without_drift`
   - `ambiguous_due_to_terrain`
   - `ambiguous_due_to_structure`
   - `stable_output`
   - `mixed_signal`

4. integracion narrativa en el informe final de `analysis`
   - la capa local ya se usa para modular el lenguaje del informe
   - la capa exploratoria por tercios ya queda rebajada a contraste cuando la lectura FP-01 aplica

5. tests de contrato del modulo de `analysis`
   - payload
   - prompt
   - narrativa
   - casos representativos de aplicable / no aplicable / ambiguo

6. mejora local de lectura estructural que evita sobreinterpretar `work_n_blocks`
   - `analysis_only_context.work_block_context`
   - alias plano `session_payload.json.work_block_context`
   - esta capa no cambia el contrato de `sessions.csv`, pero corrige errores de lectura narrativa del tipo "5 bloques duros" cuando en realidad hubo un bloque duro dominante

7. puerta clasica `run-aware` ya implementada y cubierta por contrato
   - `road_run >= 60 min` con potencia util o `>= 75 min` sin ella
   - `trail_run >= 75 min` con potencia util o `>= 90 min` sin ella
   - `hike >= 90 min`
   - sigue exigiendo `work_n_blocks <= 2` y mitades de velocidad disponibles
   - la misma semantica ya vive en `build_sessions.py`, en el fallback de `analysis/` y en `docs/contracts/ENDURANCE_HRV_Sessions_Schema.md`

8. narrativa simple de `trail_run` y contrato final alineados
   - en trail, la lectura simple prioriza `power_ratio` cuando existe potencia util
   - `speed_ratio` queda como apoyo, no como arbitro principal, salvo que la sesion carezca de potencia
   - los tests de contrato ya fijan el caso simple, el caso ambiguo por terreno y el caso no aplicable por estructura o duracion

### Pendiente dentro de `FP-01`

No quedan pendientes funcionales dentro de `FP-01`.

Lo que sigue abierto pertenece a `FP-05` o a futuras ampliaciones contextuales, no a la `durability` clasica.

## Validacion reciente del gate clasico (2026-04-23)

Validacion manual sobre `data/ENDURANCE_HRV_sessions.csv`, recalculando `durability_applicable` con la logica actual de `build_sessions.py`.

Casos reales abiertos correctamente por la puerta nueva:

1. `road_run` `i135583336` (`70.5 min`, potencia util, `work_n_blocks=1`)
   - `durability_applicable=1`
   - `speed_ratio=1.047`
   - `power_ratio=1.044`
   - lectura coherente: el gate nuevo abre un caso estable que antes quedaba innecesariamente fuera por el umbral unico de `90 min`

2. `road_run` `i121195861` (`76.0 min`, sin potencia, `work_n_blocks=0`)
   - `durability_applicable=1`
   - `speed_ratio=0.890`
   - `cardiac_drift_pct=14.1`
   - lectura coherente: la regla anterior de `>= 90 min` dejaba fuera una senal clasica util

3. `trail_run` `i117906255` (`78.4 min`, potencia util, `work_n_blocks=0`)
   - `durability_applicable=1`
   - `speed_ratio=1.320`
   - `power_ratio=0.779`
   - `decoupling=21.04`
   - lectura: el gate clasico puede abrirlo, pero la interpretacion sigue siendo ambigua por terreno; esto no invalida `FP-01`, sino que marca el punto donde empieza `FP-05`

Casos que siguen quedando fuera con razon:

- `road_run` entre `60-75 min` sin potencia util
- `road_run` o `trail_run` con `work_n_blocks > 2`
- `trail_run` entre `75-90 min` sin potencia util

Conclusion operativa:

- el umbral unico de `>= 90 min` si estaba dejando fuera senal clasica valida en `road_run`
- en `trail_run`, la duracion no era el unico problema; la estructura y la sensibilidad al terreno siguen mandando
- la puerta nueva corrige mejor la entrada a `FP-01` sin convertirlo en una capa contextual

### Persistencia verificada tras `python build_sessions.py --update`

Se comparo el `data/ENDURANCE_HRV_sessions.csv` actual contra un recalculo con la logica vigente de `build_sessions.py`.

Resultado:

- no hubo filas con delta entre el valor persistido y el valor recalculado de `durability_applicable`
- por tanto, la puerta clasica `run-aware` ya esta persistida correctamente en el CSV canonico local

Casos concretos que quedan abiertos como se esperaba:

1. `road_run` `i135583336`
   - `duration_min = 70.5`
   - `work_n_blocks = 1`
   - `run_power_available = 1`
   - `durability_applicable = 1`
   - caso representativo de `road_run 60-75 min` abierto por potencia util

2. `trail_run` `i117906255`
   - `duration_min = 78.4`
   - `work_n_blocks = 0`
   - `run_power_available = 1`
   - `durability_applicable = 1`
   - caso representativo de `trail_run 75-90 min` abierto por potencia util y estructura suficientemente continua

Casos que siguen fuera y confirman que la puerta no se relajo de mas:

- `road_run 60-75 min` sin potencia util -> siguen en `0`
- `trail_run 75-90 min` sin potencia util -> siguen en `0`
- `road_run` o `trail_run` con `work_n_blocks > 2` -> siguen en `0`

### Fuera de alcance de `FP-01`

Esto ya no debe seguir tratandose dentro de `FP-01` y debe desviarse a `FP-05`:

1. eficiencia contextual basada en:
   - `power + GAP + pendiente + FC`
   - y, cuando exista, `cadencia`

2. comparacion entre climbs comparables

3. comparacion por bins de pendiente

4. comparacion de repeatability en sesiones estructuradas o por repeticiones

5. el modelo de tres estados para `trail_run`
   - `classic_applicable`
   - `contextual_only`
   - `not_applicable`

6. cualquier capa nueva tipo:
   - `efficiency_context`
   - `matched_climbs`
   - `matched_segments`
   - `repeatability_loss_in_climbs`

7. cualquier intento de convertir la lectura contextual en:
   - contrato canonico de `sessions.csv`
   - `FINAL`
   - `DASHBOARD`
   - `reason_text`

## Regla de frontera con `FP-05`

`FP-01` debe quedarse como:

- capa de `durability clasica de sesion`
- basada en primitivas simples de `sessions.csv`
- con una lectura prudente y trazable en `analysis`

`FP-05` debe absorber:

- la `durability contextual`
- la eficiencia contextual
- y los casos donde `trail_run` no puede leerse bien con una comparacion global por mitades
