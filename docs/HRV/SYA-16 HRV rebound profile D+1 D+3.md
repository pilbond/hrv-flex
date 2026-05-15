

> Tarjeta Kanvas: `SYA-16` - grupo `Analysis / Coach`, estado `cyan` (terminada por el agente, pendiente de revision humana).
> Documento precedente: [SYA-10 Backlog diferido de senales retrospectivas y HRV longitudinal.md](SYA-10%20Backlog%20diferido%20de%20senales%20retrospectivas%20y%20HRV%20longitudinal.md)

## Texto de la tarjeta

Objetivo: formalizar y evaluar la idea de `HRV rebound profile D+1/D+3` como senal `weekly` retrospectiva, fijando su semantica, su ventana temporal, su relacion entre sesion origen y respuesta HRV posterior, y sus criterios de activacion.

Esta tarea no implementa aun la senal en `analysis_only_context`, `sessions_day`, `FINAL` ni `reason_text`.

---

## Analisis tecnico 2026-05-05

### Que pretende medir

`HRV rebound profile D+1/D+3` intenta capturar como responde el sistema en los dias posteriores a una sesion o bloque de carga:

- `D+1`: que ocurre al dia siguiente
- `D+3`: que ocurre tres dias despues

La idea no es medir el coste de la sesion en si, sino la velocidad y la calidad del rebote posterior:

- recuperacion rapida frente a lenta
- respuesta estable frente a rebote incompleto
- coste asumible frente a coste que sigue visible varios dias

### Por que merece tarjeta propia

La propuesta es valiosa, pero no encaja como senal de sesion por definicion:

- depende de informacion futura respecto a la sesion origen
- mezcla estimulo y respuesta posterior si se fuerza en un analisis inmediato
- necesita reglas claras para atribuir el rebote a una sesion concreta o a un bloque

Por tanto, su destino natural es una capa `weekly` retrospectiva o un enriquecimiento diferido, no una lectura local de `analysis/` sobre la sesion del dia.

### Hipotesis de trabajo

La hipotesis razonable hoy es esta:

- la senal debe vivir como lectura retrospectiva
- no debe presentarse como juicio causal fuerte sobre una unica sesion salvo contexto suficiente
- puede aportar valor para releer tolerancia de carga y calidad de absorcion del bloque

## Cierre operacional 2026-05-14

Esta actualizacion cierra las cuatro decisiones minimas que faltaban para sostener la tarea fuera de `purple`.

### 1. Variable HRV del rebote y referencia

La variable primaria del rebote sera `lnRMSSD_today`, no `lnRMSSD_used`.

Motivo:

- `lnRMSSD_today` representa la lectura matinal cruda del dia y evita contaminar el rebote con suavizados que usan dias vecinos
- `lnRMSSD_used` sirve para gating operativo diario, pero no es la mejor señal para leer cinetica post-carga porque mezcla parte del entorno temporal

La referencia primaria sera una baseline corta pre-evento:

- mediana de `lnRMSSD_today` en los ultimos `7` dias validos anteriores al evento origen
- solo dias con `Calidad == OK`
- minimo `5` dias validos para considerarla baseline corta usable

La escala de comparacion sera:

- `SWC_pre = 0.5 x robust_sd(lnRMSSD_today)` sobre esa misma ventana corta pre-evento
- si la ventana corta no alcanza cobertura suficiente, se permite fallback a `ln_base60` y `SWC_ln` ya existentes en el pipeline HRV

Regla explicita:

- la referencia principal NO sera `D-1` aislado, porque es demasiado ruidoso
- `D-1` puede usarse como contexto auxiliar, pero no como ancla unica de interpretacion

### 2. Regla de atribucion

La unidad primaria de atribucion NO sera la sesion individual sino el `session-day` origen.

Motivo:

- la HRV se observa a escala diaria matinal
- puede haber varias sesiones el mismo dia
- forzar atribucion a una sola sesion concreta produciria una precision falsa

Regla de atribucion:

1. por defecto, el origen es el `dia de carga` completo
2. si en ese dia hay varias sesiones, se interpreta como un unico evento de carga diario
3. si existen `2` o mas dias de carga relevantes en una ventana `D-1..D0`, la atribucion escala a `bloque corto` y deja de leerse como respuesta a una sesion unica

Para esta tarea, un `dia de carga relevante` sera un dia que cumpla al menos una de estas condiciones:

- `intense_day == true`
- `load_ctx_ready == true` y `load_day` claramente por encima de la carga habitual reciente
- existe evidencia analitica local de `key session` o `key block` en `analysis/`

Conclusión operacional:

- `SYA-16` medira absorcion de `eventos de carga diarios o microbloques`, no "el efecto exacto de una sesion concreta" salvo casos excepcionalmente limpios

### 3. Politica para dias contaminados

La politica sera conservadora y separara `hard invalidation` de `lectura con cautela`.

Invalidacion dura:

- `Calidad != OK` en la manana observada
- falta `lnRMSSD_today` valido en `D+1` o `D+3`
- aparece un nuevo `dia de carga relevante` antes del horizonte que se quiere leer

Regla temporal concreta:

- la lectura de `D+1` sigue siendo valida aunque el atleta entrene despues ese mismo dia, porque la HRV matinal precede a esa nueva sesion
- esa nueva sesion SI contamina la lectura de `D+2` y `D+3`
- por tanto, `D+3` solo se considera limpio si entre el evento origen y la manana de `D+3` no ha aparecido otro evento origen elegible

Lectura con cautela, no exclusion automatica:

- mal sueno subjetivo
- wellness deteriorado
- estres, viaje, calor u otro contexto externo documentado

Regla de interpretacion:

- estos factores no expulsan automaticamente el caso porque pueden formar parte real de la absorcion
- pero obligan a etiquetar la observacion como `contaminada_blando` o `contexto_adverso`, no como `rebote limpio`

### 4. Destino final fijado

El destino final queda fijado como `weekly retrospectivo`.

Reglas:

- no entra en `FINAL`
- no entra en `DASHBOARD`
- no entra en `sessions_day.csv`
- no entra en `reason_text`
- no entra en lectura inmediata de `analysis/` sobre la sesion del dia

Si se necesita una salida tecnica intermedia para QA o backtest, esa salida podra existir solo como `sidecar local` o artefacto reproducible, pero no cambia el destino funcional final.

## Lectura propuesta del perfil

Una vez fijada la semantica, la lectura base del rebote sera esta:

- `delta_D+1 = lnRMSSD_today[D+1] - baseline_pre`
- `delta_D+3 = lnRMSSD_today[D+3] - baseline_pre`
- `z_D+1 = delta_D+1 / SWC_pre`
- `z_D+3 = delta_D+3 / SWC_pre`

Clasificacion inicial auditable:

1. `rebote rapido`:
   - `z_D+1 >= -0.5`
   - `z_D+3 >= -0.5`
2. `rebote lento pero absorbido`:
   - `z_D+1 < -0.5`
   - `z_D+3 >= -0.5`
3. `rebote incompleto D+3`:
   - `z_D+3 < -0.5`
4. `sobrerrebote / posible saturacion`:
   - `z_D+3 > +1.0`
   - lectura exploratoria, no juicio de "mejor recuperacion" por defecto
5. `no interpretable`:
   - falta de datos o contaminacion dura

Esta taxonomia es deliberadamente prudente:

- no pretende inferir causalidad fuerte
- no convierte una respuesta autonómica aislada en verdict de calidad de sesion
- sirve para resumir velocidad de absorcion del evento de carga

## Artefacto tecnico v1

La implementacion tecnica de esta misma tarea vive como sidecar local en `analysis/`, no como output canonico global.

Script:

- `python analysis/hrv_rebound_profile.py`

Inputs:

- `data/ENDURANCE_HRV_master_FINAL.csv`
- `data/ENDURANCE_HRV_master_CORE.csv`
- `data/ENDURANCE_HRV_sessions_day.csv`
- `data/ENDURANCE_HRV_sessions.csv`
- `data/ENDURANCE_HRV_sleep.csv`

Outputs locales:

- `analysis/reports/hrv_rebound_profile/hrv_rebound_profile_events.csv`
- `analysis/reports/hrv_rebound_profile/hrv_rebound_profile_weekly.csv`
- `analysis/reports/hrv_rebound_profile/hrv_rebound_profile_summary.json`

Reglas de esta v1:

- evento origen elegible por `intense_day`
- tambien puede entrar por `acwr_simple_prev` alto, pero solo si:
  - `load_ctx_ready = true`
  - `load_day >= 60`
  - no es un dia exclusivamente de fuerza
- baseline primaria `pre7` sobre `lnRMSSD_today`; fallback a `ln_base60` y `SWC_ln`
- `D+1` usa lectura matinal del dia siguiente
- `D+3` se invalida si aparece un nuevo evento elegible en `D+1` o `D+2`
- sueno bajo o mal `sleep_score` quedan como cautela blanda, no como exclusion automatica

Limitacion declarada:

- esta v1 no consume aun evidencia de `key session` o `key block` desde sidecars de `analysis/`; la elegibilidad del evento se apoya solo en la capa canonica diaria de carga
- `high_relative_load` sigue siendo una heuristica de cribado, no una definicion fisiologica cerrada de "sesion clave"

## Revision manual de casos interpretables 2026-05-14

Tras implementar el sidecar y revisar los artefactos reales, la foto de esta v1 queda asi:

- `63` eventos origen detectados
- `20` casos interpretables
- `5` casos `clean`
- `15` casos con cautela blanda

Distribucion observada de los `20` casos interpretables:

- `rebote_rapido`: `4`
- `rebote_lento_absorbido`: `2`
- `rebote_incompleto_d3`: `8`
- `sobrerrebote`: `6`

### Casos interpretables observados

Casos `rebote_rapido`:

- `2025-07-20` `trail_run`, `load_day=115`, lectura compatible con absorcion razonablemente rapida, aunque con sueno corto en `D+1` y `D+3`
- `2025-08-23` `trail_run`, `load_day=79`, rebote rapido con `D+1` muy alto y `D+3` ya dentro de rango
- `2025-11-08` `road_run`, `load_day=41`, caso limpio y probablemente de los mas utiles de toda la muestra
- `2026-02-11` `bike|strength`, `load_day=85`, rapido pero con cautela blanda por sueno corto en `D+3`

Casos `rebote_lento_absorbido`:

- `2025-05-30` `bike`, `load_day=56`, `D+1` muy deprimido y `D+3` recuperado
- `2026-04-27` `road_run`, `load_day=66`, patron parecido pero menos extremo

Casos `rebote_incompleto_d3`:

- `2025-07-02` `trail_run`, `load_day=72`
- `2025-07-27` `bike`, `load_day=97`
- `2025-11-18` `road_run|strength`, `load_day=80`
- `2026-02-07` `trail_run`, `load_day=64`
- `2026-03-07` `trail_run`, `load_day=86`
- `2026-04-14` `mobility|trail_run`, `load_day=109`
- `2026-04-21` `strength|trail_run`, `load_day=75`
- `2026-05-05` `road_run`, `load_day=73`

Lectura comun:

- aqui la señal si parece capturar algo que el gate diario no resume por si solo: coste que todavia deja huella autonómica a `D+3`

Casos `sobrerrebote`:

- `2025-06-29` `bike`, `load_day=179`
- `2025-09-05` `bike`, `load_day=99`
- `2025-09-14` `trail_run`, `load_day=132`
- `2025-09-27` `road_run`, `load_day=60`
- `2026-03-15` `bike`, `load_day=63`
- `2026-04-11` `bike`, `load_day=157`

Lectura prudente:

- no deben leerse como "mejor recuperacion"
- en varios aparecen `D+1` o `D+3` con sueno corto
- por tanto, hoy funcionan mejor como clase separada de observacion rara que como outcome favorable

### Patrones que si parecen utiles

1. La señal aporta una unidad de lectura que no existe hoy en el pipeline canonico:
   no mide el coste de la sesion, sino si ese coste sigue visible o no varios dias despues.
2. `rebote_incompleto_d3` parece la clase mas prometedora:
   es la que mejor encaja con la intuicion practica de "carga absorbida vs no absorbida".
3. `rebote_lento_absorbido` tambien tiene valor:
   distingue casos en los que `D+1` sale castigado pero `D+3` ya ha normalizado.
4. `rebote_rapido` existe de verdad en la muestra:
   no es una clase vacia ni puramente teorica.

### Fragilidades observadas

1. La mayor limitacion real sigue siendo la interpretabilidad:
   `63` eventos producen `20` casos interpretables.
2. La contaminacion por nuevos eventos mata muchos casos:
   esto no es un bug; es parte de la realidad de semanas con carga encadenada.
3. `sobrerrebote` es semanticamente ambiguo:
   hoy debe mantenerse como etiqueta exploratoria, no como lectura de recuperacion positiva.
4. `high_relative_load` sigue siendo util pero secundaria frente a `intense_day`:
   tras endurecer el filtro a `load_day >= 60` y excluir fuerza pura, deja de meter mucho ruido obvio, pero aun no tiene la solidez semantica de `intense_day`.

### Ajuste tecnico cerrado en esta tarea

El filtro `high_relative_load` se ha endurecido respecto al primer borrador:

- antes bastaba `acwr_simple_prev >= 1.25` con `load_ctx_ready`
- ahora ademas exige `load_day >= 60`
- y excluye dias exclusivamente de fuerza

Impacto observado:

- eventos totales: `90 -> 63`
- casos interpretables: `13 -> 20`
- casos `clean`: `3 -> 5`

Este ajuste mejora disciplina sin perder casos utiles.

## Conclusiones finales

`SYA-16` SI aporta valor real, pero de forma acotada y retrospectiva.

Conclusion operativa:

1. la tarea queda bien definida y tecnicamente instrumentada como sidecar local;
2. la clase con mas valor potencial es `rebote_incompleto_d3`;
3. `rebote_lento_absorbido` aporta una segunda lectura util;
4. `sobrerrebote` queda como clase exploratoria y no debe promoverse sin mas;
5. la señal no esta lista para entrar en outputs canonicos ni narrativa diaria;
6. si se usa, debe vivir como capa `weekly retrospectiva` o como artefacto de backtest local.

Decision de cierre de esta tarea:

- `SYA-16` queda cerrada como:
  - semantica definida
  - sidecar tecnico reproducible implementado
  - evidencia preliminar documentada de utilidad parcial
- NO queda aprobada para entrar en `FINAL`, `DASHBOARD`, `sessions_day`, `reason_text` ni `analysis_only_context` semanal como fuente primaria
- SI queda aprobada como linea de investigacion local suficientemente seria para futuras lecturas `weekly` retrospectivas

## Propuesta de render en informe semanal

Si esta señal se usa en un informe `weekly`, debe aparecer como subcapa dentro de `Recuperacion y absorcion`, no como bloque principal del microciclo.

Ubicacion recomendada:

- `Seccion 4 - Recuperacion y absorcion`

Tabla recomendada cuando haya `1+` casos interpretables en la semana:

| Evento origen | Tipo | load_day | D+1 | D+3 | Clase | Confianza | Nota |
|---|---:|---:|---:|---:|---|---|---|
| `2026-04-21` | `trail_run` | `75` | `-0.79 SWC` | `-1.99 SWC` | `rebote_incompleto_d3` | media | sueno bajo en `D+3` |
| `2026-04-27` | `road_run` | `66` | `-1.15 SWC` | `-0.12 SWC` | `rebote_lento_absorbido` | alta | sin contaminacion dura |

Reglas de la tabla:

- `Evento origen`: fecha del `session-day` o `bloque corto`
- `Tipo`: deporte o combinacion corta de deportes
- `D+1` y `D+3`: usar `z_D+1` y `z_D+3` en unidades de `SWC_pre`
- `Clase`: una de las taxonomias cerradas en esta tarea
- `Confianza`: derivada de `clean` vs `soft_caution`; no debe fingir precision superior
- `Nota`: una sola cautela material, no un comentario largo

Debajo de la tabla, la lectura debe ir en `2-4` lineas. Ejemplo:

- Esta semana hubo `2` eventos interpretables de rebote HRV.
- Uno dejo `rebote_incompleto_d3`, compatible con coste autonomico todavia visible tres dias despues.
- El otro mostro `rebote_lento_absorbido`: caida clara en `D+1`, pero recuperacion practica en `D+3`.
- La absorcion semanal fue heterogenea; no parece una semana de asimilacion limpia y uniforme.

Regla de uso editorial:

- si hay `0` casos interpretables, omitir el bloque o resumirlo en una linea
- si hay `1-2` casos interpretables, usar tabla corta + lectura sintetica
- si hay varios casos y patron claro, permitir que esta capa apoye la conclusion de absorcion semanal

Regla de jerarquia:

- esta capa NO sustituye:
  - `sleep`
  - HRV semanal agregada
  - `load_day`
  - `monotony/strain`
  - divergencias con el sistema
- esta capa SI puede aportar una pregunta distinta:
  - si los picos de carga de la semana dejaron o no una huella autonómica persistente

Lo que NO debe hacer en weekly:

- no actuar como semaforo semanal
- no juzgar una sesion como buena o mala
- no reinterpretar por si sola la semana completa
- no entrar como fuente primaria si la muestra interpretables es minima o blanda

### Preguntas que esta tarea debe resolver

1. Definicion operacional:
   cerrada con `lnRMSSD_today` frente a baseline corta pre-evento y fallback `BASE60`
2. Ventana temporal:
   cerrada en `D+1` y `D+3` como hitos minimos de absorcion rapida vs persistencia de coste
3. Unidad de analisis:
   cerrada en `session-day` o `bloque corto`, no en sesion individual por defecto
4. Regla de lectura:
   cerrada con taxonomia `rebote rapido / lento / incompleto / sobrerrebote / no interpretable`
5. No sobreinterpretacion:
   cerrada con politica de contaminacion dura vs blanda y destino exclusivo `weekly retrospectivo`

### Criterios de aceptacion propuestos

1. Existe una definicion escrita y auditable de `HRV rebound profile D+1/D+3`.
2. Queda decidido que su destino natural es `weekly retrospectivo`.
3. Existe una regla explicita para casos con sesiones intermedias o contexto contaminado.
4. Existe criterio de implementacion prudente sin invadir capa operativa diaria.

### Condiciones ya resueltas para salir de `purple`

Esta actualizacion deja resueltas las cuatro condiciones que `SYA-03` exigia para que la idea dejara de ser solo propuesta:

1. existe una definicion operacional escrita del rebote HRV y de la referencia contra la que se compara;
2. existe una regla documentada de atribucion a `session-day` o `bloque corto`;
3. existe una politica documentada para dias contaminados por nuevas sesiones, mal sueno o contexto externo;
4. queda fijado por escrito que el destino final es `weekly retrospectivo`.

Consecuencia operativa:

- `SYA-16` ya no deberia volver a `purple`
- el estado coherente es `orange` mientras se decide si se implementa un sidecar tecnico o si se cierra la tarea solo como definicion semantica

### Fuera de alcance

- introducirlo como senal de sesion inmediata
- tocar `sessions.csv`, `sessions_day.csv`, `FINAL` o `DASHBOARD`
- usarlo para reinterpretar por la puerta de atras la semantica del gate HRV

### Cierre de la tarea

`SYA-16` tiene sentido como tarea propia porque ordena una intuicion potente pero facil de malinterpretar:

- no que hizo la sesion
- sino como fue absorbida despues

Esa semantica ya queda cerrada en esta misma tarea, junto con un sidecar tecnico reproducible y una primera revision manual de casos reales.

La idea debe permanecer fuera de la capa operativa normal hasta que exista una decision explicita posterior de promocion.
