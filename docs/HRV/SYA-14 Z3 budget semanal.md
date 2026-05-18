# SYA-14 Z3 budget semanal

> Tarjeta Kanvas: `SYA-14` - grupo `Analysis / Coach`, estado `red` (lista para definicion acotada).
> Documento precedente: [SYA-10 Backlog diferido de senales retrospectivas y HRV longitudinal.md](SYA-10%20Backlog%20diferido%20de%20senales%20retrospectivas%20y%20HRV%20longitudinal.md)

## Texto de la tarjeta

Objetivo: redefinir `z3 budget semanal` como percentil historico de `Z3` por deporte, usando el sidecar `ENDURANCE_HRV_intensity_distribution_weekly.csv` para cuantificar si la semana actual esta baja, normal, alta o muy alta en `Z3` respecto al historico comparable del mismo deporte.

Esta tarea no implementa aun la senal en `analysis_only_context`, `sessions_day`, `FINAL` ni `reason_text`.

---

## Analisis tecnico 2026-05-18

### Que pretende medir

La formulacion valida de `SYA-14` ya no es "cuanto Z3 hubo", porque eso ya existe.

La pregunta correcta es:

- cuanto `Z3` lleva la semana actual respecto al historico del mismo deporte
- si esa semana cae en una zona baja, habitual, alta o excepcional para ese deporte
- si la capa semanal necesita una lectura de tolerancia historica y no solo una suma o porcentaje bruto

En esta redefinicion, `SYA-14` no es una recomendacion prospectiva.
Es una senal `weekly` retrospectiva y auditable.

### Definicion operacional propuesta

Senal candidata principal:

- `z3_pct_percentile_by_sport`

Definicion:

- tomar la fila semanal actual de `ENDURANCE_HRV_intensity_distribution_weekly.csv` para un `sport`
- leer su `z3_pct_weighted`
- comparar ese valor contra la distribucion historica de `z3_pct_weighted` de semanas del mismo `sport`
- convertir la posicion relativa en un percentil `0-100`

Formula conceptual:

```text
z3_pct_percentile_by_sport =
percentile_rank(
  z3_pct_weighted_semana_actual,
  {z3_pct_weighted de semanas historicas comparables del mismo sport}
)
```

Senales auxiliares opcionales, solo si luego hacen falta:

- `z3_total_min_percentile_by_sport`
- `z3_budget_band_by_sport` con bandas `low`, `normal`, `high`, `very_high`

La propuesta minima para `SYA-14` debe arrancar con una sola senal principal, no con un paquete grande.

### Inputs y unidad base

Fuente canonica:

- `ENDURANCE_HRV_intensity_distribution_weekly.csv`

Campos minimos necesarios:

- `sport`
- semana ISO o ancla semanal equivalente
- `z3_pct_weighted`
- `z3_total_min`
- `week_type_confidence` o cualquier campo de confianza semanal ya persistido

Unidad base recomendada:

- `z3_pct_weighted` como senal principal

Motivo:

- evita confundir semanas largas con semanas cortas
- es mas comparable entre semanas del mismo deporte
- ya existe en el sidecar semanal y no obliga a inventar agregados nuevos

`z3_total_min` puede quedar como comparador secundario, no como definicion primaria del "budget".

### Guardrails minimos

La senal solo debe calcularse si:

- hay muestra historica suficiente del mismo `sport`
- la semana actual no es `insufficient_data`
- la fila semanal actual tiene confianza al menos `moderate`
- las semanas historicas comparables tambien cumplen criterios minimos de confianza

Decisiones cerradas para v1:

- usar ventana historica rolling de `12 meses` hacia atras desde la semana de lectura
- exigir minimo `8` semanas comparables del mismo `sport`
- permitir fallback a `sport_family` solo si el `sport` no llega a `8` semanas pero la `sport_family` aporta al menos `12` semanas comparables
- si tampoco hay cobertura suficiente en `sport_family`, devolver `NaN` y no forzar lectura

Razon de estas decisiones:

- `12 meses` evita mezclar demasiado ruido remoto y conserva una estacion completa de entrenamiento
- `8` semanas por `sport` es un minimo pragmatico para que un percentil no sea casi binario
- el fallback a `sport_family` exige mas muestra que el calculo por `sport` porque la comparabilidad cae al mezclar modalidades
- devolver `NaN` es preferible a inventar un percentil con cobertura pobre

Definicion de "semana comparable" para el historico de referencia:

- misma unidad `sport` o `sport_family` segun aplique
- `week_type != insufficient_data`
- `week_type_confidence in {moderate, high}`
- `z3_pct_weighted` finito

Si en el futuro la cobertura real muestra que `12 meses` recorta demasiado deportes de baja frecuencia, la primera palanca a revisar debe ser el fallback a `sport_family`, no relajar a ciegas el minimo de confianza.

### Lectura operativa propuesta

Interpretacion orientativa:

- percentil `< 40`: semana baja en `Z3` para ese deporte
- percentil `40-75`: rango habitual
- percentil `75-90`: semana alta
- percentil `> 90`: semana muy alta o excepcional

Esta lectura sigue siendo retrospectiva.
No responde por si sola "haz otra sesion de calidad" ni "no la hagas".
Solo deja una medida de tolerancia historica observada.

Decision explicita de presentacion v1:

- la salida estructurada conserva las cuatro bandas `low`, `normal`, `high`, `very_high`
- el resumen textual visible solo habla para bandas `high` y `very_high`
- bandas `low` y `normal` quedan silenciosas en UI por ahora para evitar inflar la capa semanal con mensajes de baja prioridad

Esta asimetria es deliberada y no debe confundirse con ausencia de dato:

- la semantica completa vive en `z3_budget_by_sport`
- el texto visible es una seleccion conservadora de eventos altos
- si mas adelante se quiere surfacing explicito de margen amplio o semana inusualmente baja en `Z3`, debe abrirse como ajuste de producto/UI, no como bug del calculo base

### No redundancia frente a lo existente

La diferencia con las capas ya activas es explicita:

- `z3_total_min` y `z3_pct_weighted_prev_7d` responden "cuanto Z3 hubo"
- `week_type` responde "que patron de distribucion tuvo la semana"
- `intensity_clustering_*` responde "si la intensidad se agrupó"
- `ACWR/monotony/strain` responden "que carga relativa se acumuló"

`SYA-14` en esta forma responde otra pregunta:

- donde cae esta semana de `Z3` dentro de tu propia distribucion historica por deporte

Eso si es valor incremental.

### Preguntas que esta tarea debe resolver

1. Definicion operacional:
   si la senal principal final sera `z3_pct_percentile_by_sport` o una variante equivalente con otro naming
2. Horizonte historico:
   queda fijado en rolling `12 meses` para v1
3. Cobertura:
   quedan fijadas `8` semanas minimas por `sport`
4. Fallback:
   cae a `sport_family` solo si hay al menos `12` semanas comparables; si no, queda en `NaN`
5. Destino natural:
   si debe vivir en weekly coach, sidecar semanal ampliado o capa local de `analysis`

### Criterios de aceptacion propuestos

1. Existe una definicion escrita y auditable de `z3 budget semanal`.
2. La definicion deja cerrado que la semantica es percentil historico de `Z3` por deporte, no recomendacion prospectiva ni suma bruta.
3. Existe comparacion explicita contra `z3_total_min`, `z3_pct_weighted_prev_7d`, `week_type`, `intensity_clustering_*` y `ACWR/monotony/strain`.
4. Queda fijado su destino natural como capa `weekly` retrospectiva o sidecar local, sin tocar `sessions_day`, `FINAL` ni `reason_text`.

### Condicion minima para implementar

La tarea puede implementarse solo si se cumplen a la vez estas condiciones:

1. existe naming final y formula cerrada del percentil por deporte;
2. existen reglas escritas de cobertura minima, horizonte historico y fallback;
3. queda decidido si se usa `z3_pct_weighted`, `z3_total_min` o ambas, con una sola primaria;
4. queda fijado por escrito que la salida es retrospectiva y no una recomendacion de coaching por si misma.

### Fuera de alcance

- tocar `sessions.csv`, `sessions_day.csv`, `FINAL` o `DASHBOARD`
- convertir la senal en permiso/prohibicion automatica para meter mas calidad
- reabrir por esta via la semantica HRV global

### Conclusiones provisionales

`SYA-14` solo tiene valor si deja de significar "mas Z3 esta semana" y pasa a significar:

- percentil historico de `Z3` por deporte
- lectura retrospectiva de tolerancia observada
- capa semanal separada de la carga y de la distribucion ya existentes

Con esa redefinicion, la tarea deja de ser ambigua y pasa a ser una implementacion acotada y defendible.

### Decision v1 recomendada

Para dejar la tarea lista para implementacion, la decision recomendada es:

- senal primaria: `z3_pct_percentile_by_sport`
- historico de referencia: rolling `12 meses`
- muestra minima por `sport`: `8` semanas comparables
- fallback: `sport_family` solo con `12` o mas semanas comparables
- sin cobertura suficiente: `NaN`
- destino natural inicial: sidecar semanal ampliado o weekly coach, no `sessions_day` ni `FINAL`
