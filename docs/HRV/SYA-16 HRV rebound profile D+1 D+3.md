# SYA-16 HRV rebound profile D+1 D+3

> Tarjeta Kanvas: `SYA-16` - grupo `Analysis / Coach`, estado `purple` (propuesta).
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

### Preguntas que esta tarea debe resolver

1. Definicion operacional:
   que variable HRV se usa para medir rebote y contra que referencia se compara
2. Ventana temporal:
   por que `D+1` y `D+3`, y que ocurre si hay nuevas sesiones o ruido entre medias
3. Unidad de analisis:
   si el rebote se atribuye a una sesion concreta, a una sesion clave o a un bloque corto
4. Regla de lectura:
   como distinguir rebote limpio, rebote lento, rebote incompleto o lectura no interpretable
5. No sobreinterpretacion:
   como evitar inferencias causales excesivas cuando el HRV posterior esta contaminado por otras cargas, sueno o contexto externo

### Criterios de aceptacion propuestos

1. Existe una definicion escrita y auditable de `HRV rebound profile D+1/D+3`.
2. Queda decidido que su destino natural es:
   - weekly retrospectivo
   - enriquecimiento diferido local
   - descartado por baja interpretabilidad
3. Existe una regla explicita para casos con sesiones intermedias o contexto contaminado.
4. Existe criterio de reactivacion claro antes de cualquier implementacion.

### Condicion minima para pasar de `purple` a `red`

La tarjeta puede pasar a `red` solo si se cumplen a la vez estas condiciones:

1. existe una definicion operacional escrita del rebote HRV y de la referencia contra la que se compara;
2. existe una regla documentada de atribucion a sesion concreta, sesion clave o bloque corto;
3. existe una politica documentada para dias contaminados por nuevas sesiones, mal sueno o contexto externo;
4. queda fijado por escrito si el destino final es `weekly retrospectivo`, enriquecimiento diferido local o descarte.

### Fuera de alcance

- introducirlo como senal de sesion inmediata
- tocar `sessions.csv`, `sessions_day.csv`, `FINAL` o `DASHBOARD`
- usarlo para reinterpretar por la puerta de atras la semantica del gate HRV

### Conclusiones provisionales

`SYA-16` tiene sentido como tarea propia porque ordena una intuicion potente pero facil de malinterpretar:

- no que hizo la sesion
- sino como fue absorbida despues

Hasta cerrar bien esa semantica retrospectiva, la idea debe permanecer fuera de la capa operativa normal.
