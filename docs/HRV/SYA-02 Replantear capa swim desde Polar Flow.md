# SYA-02 Replantear capa swim desde Polar Flow + fallback FIT/TCX

## Texto consolidado de la tarea

> Replantear la capa swim para que `SYA-02` absorba el alcance semantico y tecnico que antes vivia en `TYM-02`.
>
> Objetivo: dejar de tratar la natacion como `bajo_estimulo` por ausencia estructural de senal mecanica, priorizando primero una fuente programatica Polar y usando FIT o TCX como fallback cuando esa capa no exista o no preserve suficiente detalle.
>
> Alcance inicial:
> - localizar la fuente primaria mas rica disponible para swim,
> - exponer `swim_context` reproducible en `analysis`,
> - unificar en una sola salida los datos de estilo, SWOLF, descansos, estructura de largos y degradacion tecnica,
> - dejar la integracion en `session_cost_model` fuera de esta iteracion.

## Objetivo operativo

Resolver el agujero estructural actual de swim:

- la FC de muneca bajo el agua es una senal debil,
- el parser actual no incorpora una capa tecnica/propulsiva propia de natacion,
- el pipeline acaba empujando demasiadas sesiones a `bajo_estimulo`,
- el metodo analitico ya espera estructura de series, SWOLF, brazadas y deterioro tecnico cuando existan.

Esta tarea sustituye a `TYM-02` como linea principal de trabajo. El contenido util de `TYM-02` se conserva aqui.

## Diagnostico actual

### Estado del codigo

- `analysis/session_cost_model.py` calcula hoy `swim_mechanical_score` con `work_total_min`, `work_longest_min` y `z3_pct`, con `confidence = "low"`.
- `analysis/session_analysis_pipeline.py` ya trata swim como deporte que deberia apoyarse en bloque, tecnica y sensacion, no en semantica terrestre.
- `analysis/SESSION_ANALYSIS_METHOD.md` ya define que en swim el `mecanico_score` significa coste propulsivo y tecnico, y que `SWOLF` solo vale como apoyo dentro de un contexto valido.
- `hrv_app/polar_client.py` solo expone AccessLink publico via `/exercises` y `/exercises/{id}?samples=true`; no existe hoy una API swim-rich integrada en el repo.

### Problema real

El problema no es "swim no tiene dato". El problema es de ingestión y jerarquia de fuentes:

1. Polar Flow parece mostrar una capa mas rica que la consumida hoy por el pipeline.
2. El FIT/TCX actual puede no preservar toda esa capa.
3. El analisis local necesita una salida unica y trazable, no dos diseños paralelos.

## Arbol de fuentes

### Fuente primaria preferente

Buscar primero una fuente programatica Polar que exponga, idealmente por largo o fase:

- estilo,
- descanso,
- distancia,
- duracion,
- FC,
- brazadas,
- frecuencia de brazada,
- SWOLF.

Fuentes candidatas a validar:

1. AccessLink `/exercises/{id}?samples=true`.
2. Endpoints de training data / exercise transactions si son accesibles con el flujo actual.
3. Export oficial FIT/TCX asociado a la sesion.

### Fallbacks

Si la capa Polar rica no existe o no es accesible:

1. fallback A: parser FIT de mensajes `length`, `lap` y `session`,
2. fallback B: reconstruccion desde TCX por trackpoints y mesetas de distancia, sin inferir estilo donde no haya dato directo.

Orden obligatorio:

`polar_flow_api` -> `fit_length_messages` -> `tcx_distance_plateaus` -> `none`

## Paso 0 obligatorio

Antes de cerrar diseño o implementación:

- hacer dump exploratorio de la sesion de referencia swim,
- inspeccionar respuesta cruda de Polar,
- inspeccionar FIT completo,
- inspeccionar TCX completo,
- verificar si hay `length`, `lap`, `stroke_type`, `length_type`, `pool_length`, pausas y/o muestras de brazada.

Sin ese paso, el diseño sigue apoyado en supuestos.

## Contrato semantico consolidado

### Objetivo de salida

`analysis` debe exponer un unico `swim_context` reproducible, aunque la fuente subyacente cambie.

Campos minimos:

```json
"swim_context": {
  "swim_source": "polar_flow_api",
  "pool_length_m": 25,
  "total_lengths": 48,
  "active_lengths": 44,
  "drill_lengths": 4,
  "rest_time_min": 8.3,
  "primary_stroke": "freestyle",
  "stroke_distribution": {
    "freestyle": { "lengths": 38, "pct": 79.2 },
    "breaststroke": { "lengths": 6, "pct": 12.5 },
    "drill": { "lengths": 4, "pct": 8.3 }
  },
  "swolf_by_stroke": {
    "freestyle": { "mean": 44.2, "min": 41.0, "max": 48.0, "cv_pct": 4.1 },
    "breaststroke": { "mean": 61.5, "min": 58.0, "max": 65.0, "cv_pct": 4.8 }
  },
  "dps_by_stroke": {
    "freestyle": 1.62,
    "breaststroke": 1.91
  },
  "stroke_rate_by_stroke": {
    "freestyle": 31.4,
    "breaststroke": 24.1
  },
  "swolf_degradation_pct": 6.5,
  "swolf_degradation_stroke": "freestyle",
  "hr_confidence": "low_wrist_in_water",
  "signals_available": {
    "pool_lengths": true,
    "stroke_type": true,
    "drill_detected": true,
    "rest_segments": true
  }
}
```

### Reglas semanticas heredadas de TYM-02

1. `SWOLF` solo es comparable dentro del mismo estilo.
2. No exponer `avg_swolf` global de sesion como metrica interpretable.
3. `primary_stroke` = estilo con mas largos activos no-drill.
4. `drill` se contabiliza, pero se excluye del calculo de eficiencia.
5. Si un estilo tiene muy pocos largos, marcar `too_few_lengths`.
6. `pool_length_m` se expone siempre; no normalizar automaticamente entre 25m y 50m.
7. La FC de muneca en agua se trata como contexto debil, no como ancla primaria.
8. Si no hay dato interpretable de tecnica o estructura, rebajar confianza de forma explicita.

### Error handling

- si no hay `pool_length_m` y no se puede reconstruir una sesion de piscina, usar `swim_context_error = "open_water_or_no_pool_structure"`,
- si solo existe FC y duracion, no inventar una lectura mecanica fuerte,
- si no hay fuente usable, devolver `swim_source = "none"` y continuar el pipeline sin crash.

## Artifact unico

`TYM-02` proponia `swim_lengths.csv` y `SYA-02` proponia `swim_phases.csv`. Queda unificado en un solo artifact swim con granularidad por largo.

Nombre recomendado:

- `artifacts/swim_lengths.csv`

Granularidad:

- una fila por largo si esa estructura existe,
- si la fuente primaria viene por fase, mantener una columna `phase_id` para agrupar,
- no crear dos artifacts paralelos para el mismo problema.

Columnas esperables:

```text
length_index,phase_id,length_type,stroke_type,elapsed_time_s,total_strokes,swolf,speed_mps,dps_m,stroke_rate_spm,source
```

## Decisiones de diseño

### Por que se integra TYM-02

`TYM-02` aportaba el contrato analitico correcto:

- SWOLF por estilo,
- distribucion de estilos,
- DPS,
- degradacion tecnica,
- exclusion de drill,
- `pool_length_m`,
- `primary_stroke`,
- semantica prudente de `SWOLF`.

`SYA-02` aporta el marco correcto de ingestión:

- primero encontrar la mejor fuente,
- no asumir que FIT basta,
- aceptar TCX solo como proxy degradado,
- imponer trazabilidad de origen.

Separarlas ya no aporta valor. Genera duplicidad.

### Campo obligatorio de trazabilidad

`swim_source` es obligatorio en el output:

- `polar_flow_api`
- `fit_length_messages`
- `tcx_distance_plateaus`
- `none`

Esto permite al consumidor saber si esta viendo dato directo o proxy.

## Riesgos principales

1. Que Polar no exponga programaticamente la capa swim rica fuera de su UI.
2. Que el FIT real no conserve `stroke_type` o `length_type` con la fidelidad asumida.
3. Que el TCX no permita reconstruir descansos o estilo con suficiente robustez.
4. Que se mezclen semanticas de dato directo y proxy sin marcar la fuente.

## Relacion con el cost model

La integracion en `analysis/session_cost_model.py` queda fuera de esta iteracion.

Primero hay que cerrar:

- la fuente,
- el parser,
- el contrato de `swim_context`,
- el artifact,
- la trazabilidad.

Solo despues tendria sentido revisar `mecanico_score` swim con la semantica ya definida en `analysis/SESSION_ANALYSIS_METHOD.md`.

## Criterios de aceptacion

1. Existe una unica tarea swim activa: `SYA-02`.
2. `SYA-02` incorpora el contrato semantico que antes describia `TYM-02`.
3. `analysis` puede exponer `swim_context` con `swim_source`.
4. El artifact swim queda unificado en un solo CSV reproducible.
5. `SWOLF` se trata por estilo y no como media global de sesion.
6. `drill` no contamina el calculo de eficiencia.
7. El fallback TCX no infiere estilo donde no haya dato directo.
8. La integracion en cost model no se mezcla con esta iteracion.

## Conclusión

`SYA-02` pasa a ser la tarea canonica de la capa swim. `TYM-02` deja de existir como linea paralela y sobrevive solo como contenido absorbido: su contrato semantico, sus restricciones y sus criterios de calidad quedan incorporados aqui.
