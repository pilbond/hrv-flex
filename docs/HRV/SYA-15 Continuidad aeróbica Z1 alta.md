# SYA-15 Continuidad aerobica Z1 alta

> Tarjeta Kanvas: `SYA-15` - grupo `Contexto de carga`, estado `purple` (propuesta).
> Documento precedente: [SYA-10 Backlog diferido de senales retrospectivas y HRV longitudinal.md](SYA-10%20Backlog%20diferido%20de%20senales%20retrospectivas%20y%20HRV%20longitudinal.md)

## Texto de la tarjeta

Objetivo: formalizar y evaluar la idea de `continuidad aerobica Z1 alta` como senal longitudinal `per-sport` no operativa, fijando su semantica, su destino natural y sus criterios de activacion.

Esta tarea no implementa aun la senal en `analysis_only_context`, `sessions_day`, `FINAL` ni `reason_text`.

---

## Analisis tecnico 2026-05-05

### Que pretende medir

`continuidad aerobica Z1 alta` intenta capturar algo mas fino que "hacer mucho Z1":

- si existe una base aerobica suave pero sostenida
- si el trabajo facil aparece con continuidad real y no como minutos dispersos
- si la distribucion longitudinal por deporte mantiene un patron bajo coste compatible con construccion de fondo

La idea no apunta a una sesion aislada. Apunta a una tendencia longitudinal.

### Por que merece tarjeta propia

Hoy la idea es prometedora, pero todavia no esta semantizada con precision suficiente:

- `Z1 alta` puede significar tiempo absoluto, porcentaje de la semana o predominio relativo frente a Z2/Z3
- la continuidad puede medirse por frecuencia de sesiones, densidad de minutos o persistencia por bloques
- la interpretacion cambia mucho entre `bike`, `road_run`, `trail_run` o `hike`
- si no se define bien, puede acabar diciendo casi lo mismo que `dominant_family_prev_7d`, `z1/z2/z3_pct_weighted_prev_7d` o las salidas longitudinales de `SYA-08`

Por tanto, antes de implementarla hay que decidir exactamente que problema resuelve.

### Hipotesis de trabajo

La hipotesis razonable hoy es esta:

- no es una senal semanal operativa
- no es una senal de sesion
- su destino natural probable es una capa longitudinal `per-sport` no operativa o de investigacion local

### Preguntas que esta tarea debe resolver

1. Definicion operacional:
   que significa exactamente `Z1 alta` dentro del marco de 3 zonas del proyecto
2. Definicion de continuidad:
   si se mide por frecuencia de sesiones, minutos acumulados o estabilidad temporal
3. Especializacion por deporte:
   si la senal debe existir igual para todos los deportes o solo para algunos
4. Valor incremental:
   que aporta frente a `SYA-08`, `DO-01` y `DO-02`

### Criterios de aceptacion propuestos

1. Existe una definicion escrita y reproducible de `continuidad aerobica Z1 alta`.
2. Se fija si su destino natural es:
   - longitudinal per-sport no operativo
   - investigacion local
   - descartado por ambiguedad o redundancia
3. Se documenta que no debe confundirse con volumen facil bruto ni con distribucion semanal simple.
4. Existe criterio de reactivacion claro antes de cualquier implementacion.

### Condicion minima para pasar de `purple` a `red`

La tarjeta puede pasar a `red` solo si se cumplen a la vez estas condiciones:

1. existe una definicion operacional escrita de `Z1 alta` compatible con el marco de 3 zonas del proyecto;
2. existe una definicion escrita de "continuidad" que especifique si se mide por frecuencia, minutos o estabilidad temporal;
3. existe una decision documentada sobre si aplica a todos los deportes o solo a algunos;
4. existe una comparacion documentada contra `SYA-08`, `DO-01` y `DO-02` que muestre valor incremental no redundante.

### Fuera de alcance

- tocar `sessions.csv`, `sessions_day.csv`, `FINAL` o `DASHBOARD`
- introducir una nueva taxonomia de coaching sin backtest
- reabrir por esta via la capa canonica de distribucion semanal

### Conclusiones provisionales

`SYA-15` tiene sentido como tarea separada porque obliga a cerrar primero la pregunta semantica:

- no cuanto Z1 hay
- sino que significa continuidad aerobica util dentro del marco actual del proyecto

Hasta resolver eso, la idea debe permanecer como linea longitudinal diferida y no como feature pendiente de implementar.
