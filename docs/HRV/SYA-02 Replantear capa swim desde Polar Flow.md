# SYA-02 Capa swim desde Polar v4: largos validados, estilos, SWOLF y carga percibida

> Revisada el 2026-11-07 tras consultar Polar v4 para nueve sesiones reales.
> Corrige la reducción a «swim lite por vueltas de Intervals» del 2026-11-06:
> que un FIT regenerado no tenga mensajes `length` no implica que Polar carezca
> de información por largo. Sigue absorbiendo `TYM-02`.
> Estado: propuesta actualizada; auditoría ejecutada, integración pendiente.

## 1. Decisión y alcance

Construir un `swim_context` local de `analysis` con **Polar v4 como fuente
principal de natación**. Recuperar piscina, estilos, brazadas, SWOLF por estilo
y fases temporales; exponer largos cuando la coherencia de cada sesión
permita interpretar sus fases como largos.

Intervals aporta contexto canónico, RPE y respaldo descriptivo cuando Polar
no está disponible. El SWOLF de los FIT de Intervals auditados no sirve como
alternativa técnica: no supera la comprobación de semántica.

El objetivo es describir carga percibida, estructura de nado, exposición por
estilo y papel de la natación en la semana. Esta iteración no modifica
`session_cost_model.py`, `sessions.csv`, `sessions_day.csv`,
`ENDURANCE_HRV_weekly_coach.json`, `FINAL`, `DASHBOARD`, gate ni `reason_text`.
No incorpora nuevos flujos OAuth ni APIs v3.

## 2. Evidencia comprobada el 2026-11-07

### Consulta directa a Polar

Se utilizó `V4Client`, de `hrv_app/polar_client_v4.py`, con:

- `GET /v4/data/training-sessions/list`;
- intervalo diario `[día T00:00:00, día siguiente T00:00:00)`;
- `features=["samples", "laps", "statistics", "pause-times"]`.

La lista de features se envía mediante el cliente existente. El detalle viene
en `exercises[]`; no hace falta suponer un endpoint separado de detalle.

Muestra de conveniencia: ocho fechas con FIT swim cacheado y una sesión
reciente. No equivale a comprobar las 78 sesiones históricas.

| Fecha | Distancia Polar (m) | Piscina (m) | Fases / largos declarados | Vueltas Polar |
|---|---:|---:|---:|---:|
| 2026-01-27 | 1525 | 25 | 61 / 61 | 9 |
| 2026-02-05 | 1200 | 25 | 48 / 48 | 3 |
| 2026-02-09 | 925 | 25 | 37 / 37 | 0 |
| 2026-03-12 | 1725 | 25 | 69 / 69 | 5 |
| 2026-04-07 | 1200 | 25 | 48 / 48 | 5 |
| 2026-04-22 | 1100 | 25 | 44 / 44 | 0 |
| 2026-05-12 | 2025 | 25 | 81 / 81 | 6 |
| 2026-05-19 | 1850 | 25 | 74 / 74 | 5 |
| 2026-11-05 | 1875 | 25 | 75 / 75 | 14 |

Datos recuperados en las nueve sesiones:

- `exercises[].statistics.swimmingStatistics`: `poolLength`, `poolUnits`,
  `poolsSwum`, distancia, brazadas totales y `swimmingStyles[]`.
- Por estilo: distancia, `strokeCount`, `swimmingTimeTotalMillis`, FC y
  **`swolfAvg` de Polar**.
- `exercises[].samples.swimmingPhases.phases[]`: `startOffsetMillis`,
  `durationMillis`, `style` y `strokes`.
- Samples de velocidad, distancia, cadencia y FC; `pauseTimes`.
- Vueltas cuando existen, con distancia, duración y estadísticas swim.

Comprobaciones:

- **537 fases**; en 9/9 sesiones su número coincide con `poolsSwum`.
- En los **25 agregados por estilo**, `n_fases × poolLength` coincide con
  distancia y la suma de brazadas coincide con `strokeCount`.
- El SWOLF por estilo se reproduce con
  `(suma(durationMillis) / 1000 + suma(strokes)) / n_fases`.
  Error absoluto máximo frente a `swolfAvg`: **0,000064**, compatible con redondeo.
- No hay solapamientos de fases. Sí hay huecos temporales: no se ha demostrado
  que todo hueco sea descanso ni que coincida con una pausa de `pauseTimes`.
- Las dos sesiones sin vueltas Polar sí tienen fases y estadísticas por
  estilo. Las vueltas no pueden ser requisito de disponibilidad.

Ejemplo del 2026-05-19: 35 largos de braza, 875 m y SWOLF 57,7;
39 largos de espalda, 975 m y SWOLF 88,6872. Se pueden separar estilos
con datos directos, sin inferirlos desde notas ni desde la FC.

### Corrección explícita del inventario de Intervals

Los ocho FIT están regenerados por Intervals y no tienen mensajes `length`.
La inspección actual corrige estas afirmaciones del documento del 2026-11-06:

- **Sí contienen** `distance`, `speed` y `enhanced_speed` en los registros,
  además de FC, temperatura y timestamp. Esto no demuestra que sean medidas
  originales ni valida su uso como velocidad instantánea de nado.
- Solo **3/8 FIT** tienen SWOLF de vuelta. En sus **12 vueltas válidas**,
  coincide con `total_timer_time × 25 / total_distance`, con error inferior
  a 0,000002. Es tiempo por 25 m sin contribución identificable de brazadas:
  conservarlo como evidencia de auditoría, no como SWOLF interpretable.
- Cinco FIT terminan con una vuelta de 1 s sin distancia; cuatro sesiones
  tienen una sola vuelta con tiempo y distancia válidos.
- En los ocho FIT, la distancia de sesión coincide con Polar, pero la suma
  de sus vueltas válidas queda 25 m por debajo. Algunas vueltas difieren:
  el 19 de mayo la segunda tiene 525 m en FIT y 550 m en Polar. No emparejar
  vueltas por índice ni mezclar tiempo y distancia de fuentes distintas.

Por tanto, se retira el uso del SWOLF de Intervals como «provisional con
confianza baja». La consulta directa a Polar evita esa limitación en la muestra.

### Trazabilidad y límites

- Consulta: `research/audits/swim_sources/scripts/probe_polar_swim.py`.
- Validación offline: `research/audits/swim_sources/scripts/validate_probe.py`.
- Extractos seleccionados y huellas FIT:
  `research/audits/swim_sources/results/polar_swim_probe_2026-11-07.json`.
- Conciliación:
  `research/audits/swim_sources/results/polar_swim_validation_2026-11-07.json`.
- Referencia: [Polar Dynamic API v4](https://www.polar.com/polar-api-v4/).

Los resultados conservan campos seleccionados y agregados, no respuestas
completas, rutas, tokens ni identificadores personales de Polar. La muestra
cubre piscina de 25 m con braza, espalda y crol. No valida 50 m, yardas,
aguas abiertas, mariposa, drill ni fases desconocidas. La consistencia interna
no demuestra exactitud frente a un conteo manual.

## 3. Jerarquía de fuentes y reglas

| Información | Fuente principal | Degradación permitida |
|---|---|---|
| Piscina, estilos, brazadas | Polar estadísticas y fases | Ausencia explícita, sin inferir |
| SWOLF por estilo | Polar `swimmingStyles[].swolfAvg` | `null`; sin fallback al SWOLF FIT auditado |
| Largo individual | Fase Polar validada como largo | Conservar fase sin distancia ficticia |
| Vueltas | Polar `laps` | FIT Intervals descriptivo, con controles |
| RPE y contexto de carga | `sessions.csv` y contexto coach existente | Ausencia explícita |
| Contexto semanal | Agregado local desde `sessions.csv` | Sidecar local con cobertura |

1. Distinguir `phase`, `length` y `lap`. Validar piscina/unidades, tipos,
   tiempos, conteos y conciliación de distancia/brazadas antes de asignar
   una longitud de piscina a cada fase. `TURN`, `OTHER`, `OTHER_SWIMMING`
   y `DRILL` no heredan automáticamente la regla observada en crol/braza/espalda.
2. El estilo es clasificación reportada por Polar, no observación humana
   infalible. Lo declarado por el atleta se conserva aparte como contexto
   subjetivo; no inferir estilo por ritmo, FC o SWOLF.
3. `swolfAvg` es dato reportado. `duration_s + strokes` por largo validado
   es una derivación local; registrar su procedencia y conciliación con
   Polar. No etiquetarla como valor directamente recibido.
4. No presentar SWOLF global mezclando estilos. Comparar mismo estilo,
   piscina conocida y contexto de serie/ritmo comparable. No normalizar
   25 m a 50 m ni comparar cuando falta piscina.
5. SWOLF alto no equivale a mayor coste ni SWOLF menor demuestra por sí solo
   mejora técnica. `breaststroke_pct` describe exposición, no riesgo de lesión.
6. FC como contexto con procedencia/calidad. Usar `low_wrist_in_water` si
   se identifica origen de muñeca; de otro modo, `sensor_unknown`.
7. Sin Polar o sin correspondencia inequívoca, continuar con contexto parcial,
   sin ampliar la búsqueda a toda la cuenta ni introducir otro OAuth.

## 4. Desarrollo propuesto

### A — Auditoría de fuentes: base ejecutada

La consulta y conciliación anteriores sustituyen al spike pendiente. Hay
evidencia suficiente para priorizar Polar. El archivo original de Intervals
y TCX quedan como investigación opcional, no como dependencia.

Convertir las observaciones en fixtures mínimas sin datos personales y
comprobar casos ausentes de la muestra. El resultado 9/9 no garantiza
cobertura universal.

### B — Adquisición y normalización local

- Reutilizar `V4Client` y su autenticación, con consulta diaria acotada y caché
  del bundle de `analysis`; no añadir llamadas al sync HRV diario.
- Solicitar las cuatro features. El consumo actual de sesiones en
  `hrv_app/polar_sessions.py` solicita solo `samples`: no basta para esta capa.
- Extraer swim del payload v4 **antes** de `v4_session_to_internal`:
  `hrv_app/polar_adapters_v4.py` conserva campos generales y samples, pero
  no transporta estilos, fases ni estadísticas swim. Crear un extractor
  local en `analysis/`, sin ampliar el adaptador compartido salvo necesidad.
- Emparejar por deporte, hora y duración; normalizar `startTime` usando
  `timezoneOffsetMinutes`, incluido horario de verano. Guardar discrepancias
  de distancia como QA. Correspondencia ambigua -> `ambiguous_match`.
- Separar adquisición y función pura de transformación: recálculo desde
  caché sin red. Errores de Polar no inutilizan el informe.
- Generar `swim_phases.csv` y `swim_laps.csv` dentro de
  `analysis/reports/<slug>/artifacts/`. Una fase incluye `length_validated`
  y distancia derivada cuando proceda; no duplicarla en `swim_lengths.csv`.
- Manifiesto con versión del extractor, fecha de consulta, features y huellas
  de inputs/sidecars. La caché personal permanece fuera de Git.

### C — Métricas e integración en el informe

- Piscina, largos validados, distancia, duración de nado por estilo, brazadas
  y SWOLF por estilo. Distribución por **distancia conocida**, con cobertura
  y distancia sin estilo clasificable.
- Ritmo: `100 × duration_s / distance_m`. Agregados mediante
  `100 × suma_tiempos / suma_distancias`, no media simple de ritmos.
  Separar `swim_time`, `lap_timer_time` y duración total de sesión.
- Huecos entre fases como dato descriptivo. No llamarlos automáticamente
  descanso ni sumarlos a `pauseTimes` suponiendo que son disjuntos.
- `srpe_load = sessions.rpe × sessions.duration_min`, unidad `AU`, usando
  minutos totales según contrato actual, RPE válido 1-10 y duración positiva.
  No equivale a `load` ni a `trimp`.
- Mantener aparte `coach_metrics.session_rpe`, ya existente y potencialmente
  calculado sobre otra duración. Mostrar bases y discrepancias, sin
  sobrescritura ni elección silenciosa. RPE ausente -> `null`; no usar el
  cero del proveedor como RPE válido.
- `rpe_vs_cardio_discordance`: heurística descriptiva RPE >= 4 y
  `cardio_score == 0`; si falta un dato, `null`, no `false`.
  No reclasifica coste ni demuestra fallo de FC.
- Mismo `swim_context` en `summary.json`, `session_payload.json`,
  informe y handoff, también cuando no hay RR.
- Al implementar, actualizar `analysis/ANALYSIS_DICTIONARY.md` y
  `analysis/SESSION_ANALYSIS_METHOD.md`. Son métricas locales, no contratos
  HRV globales.

### D — Contexto semanal y comparaciones

- Sidecar semanal local descubierto por `weekly_prep_manifest.json`;
  no escribir `ENDURANCE_HRV_weekly_coach.json`.
- Minutos de natación y carrera/trail, y
  `swim_share_of_swim_run = swim_min / (swim_min + run_trail_min)`, usando
  `duration_min` en ambos términos. Denominador cero -> `null`. Declarar
  categorías y fechas; otros deportes no entran en ese cociente. No implica
  equivalencia de carga ni demuestra sustitución de impacto sin contexto.
- Historia de mismo estilo/piscina/fuente/base temporal: valores y cobertura
  de las últimas 5 sesiones anteriores elegibles. Con menos de 3, marcar
  `too_few_sessions` y evitar resumen de tendencia. Son mínimos operativos
  de presentación, no umbrales fisiológicos validados.
- **Diferir la deriva automática** `pace_drift_pct` / `swolf_drift_pct`.
  Primera y última vuelta pueden representar trabajos distintos. Adoptarla
  exige validar bloques homogéneos, pausas, estilos y distancias; disponer
  de dos valores no justifica interpretarlos como deterioro.

## 5. Contrato local propuesto

Conservar `null` y motivos estructurados en contextos parciales. Separar
disponibilidad de interpretabilidad y registrar fuente/estado por métrica.

```json
{
  "swim_context": {
    "schema_version": "swim_context_v1",
    "status": "partial",
    "swim_source": "polar_v4",
    "granularity": "length",
    "length_validation_status": "passed",
    "pool_length_m": 25.0,
    "n_phases": 74,
    "n_lengths_validated": 74,
    "n_laps": 5,
    "swolf_source": "polar",
    "swolf_validation_status": "validated_against_phases",
    "swolf_by_stroke": {
      "BREASTSTROKE": 57.7,
      "BACKSTROKE": 88.6872
    },
    "stroke_distribution_basis": "distance_m",
    "srpe_load": null,
    "srpe_duration_basis": "sessions.duration_min",
    "rpe_vs_cardio_discordance": null,
    "quality_reasons": ["rpe_missing"],
    "artifacts": {
      "phases": "swim_phases.csv",
      "laps": "swim_laps.csv"
    }
  }
}
```

Ejemplo basado en los campos swim del 2026-05-19; no es un artefacto ya
implementado. La ausencia de RPE ilustra degradación parcial.

- `status`: `available`, `partial`, `unavailable`.
- `swim_source`: `polar_v4`, `intervals_fit_laps`, `none`; la fuente del
  RPE se registra aparte aunque no haya fuente de estructura swim.
- `granularity`: `length`, `phase`, `lap`, `session`, `none`.
- Motivos: `polar_unavailable`, `ambiguous_match`, `pool_unknown`,
  `unsupported_phase_type`, `phase_validation_failed`, `stroke_unknown`,
  `too_few_lengths`, `rpe_missing`, `duration_missing`, `source_mismatch`.
- Menos de 3 largos por estilo: conservar agregado oficial y tamaño de
  muestra, marcar `too_few_lengths` y excluir de tendencias.
- `swim_phases.csv`: ID, offsets, duración, estilo, brazadas, validación como
  largo, distancia/ritmo/SWOLF derivados y motivos de exclusión.
  `swim_laps.csv`: límites y magnitudes de una sola fuente por fila.

## 6. Criterios de aceptación

1. Polar v4 con cuatro features y correspondencia de sesión trazable.
2. Los casos auditados reproducen piscina, distancia, estilos y brazadas.
   SWOLF reconstruido por estilo dentro de 0,001 del reportado; una diferencia
   mayor genera QA y bloquea la validación de la derivación.
3. Solo hay largos tras validar coherencia. Sin vueltas siguen disponibles
   fases/estadísticas; tipos no soportados no generan metros inventados.
4. Cada métrica tiene valor/base/fuente o `null` con motivo. El SWOLF FIT
   sospechoso no llega al informe como métrica técnica.
5. Comparaciones por estilo/piscina/base temporal/tamaño de muestra.
   Sin SWOLF global mezclado ni deriva automática primera/última.
6. Resumen, payload e informe coherentes, también sin RR o sin Polar.
   sRPE explica sus diferencias respecto a cargas ya existentes.
7. Semanal mediante sidecar/manifiesto local. Comprobar que outputs
   operativos globales y cost model permanecen intactos.
8. Pruebas offline con fixtures mínimas: Polar completo, sin vueltas,
   sin RPE, sin Polar/FIT, matching ambiguo, cambio horario, piscina/unidad
   desconocida, `TURN`/`DRILL`, fases inconsistentes, vuelta FIT terminal
   vacía, SWOLF sospechoso, contexto parcial y sesión no swim. Sin credenciales
   ni API real en las pruebas.

## 7. Pendientes separados

- Corregida la nota de `durability_context.confidence = high` «sin velocidad»:
  los ocho summaries actuales sí incluyen velocidad por tercio. Una auditoría
  debe investigar su procedencia, cobertura y calidad, no asumir ausencia.
- Diferidos: deriva por bloques validada, DPS/frecuencia de brazada como
  métricas interpretativas, fuentes originales adicionales y uso de swim
  en el modelo de coste mecánico.
- Captura prospectiva de RPE: se confirmó presencia en 19/78 sesiones hasta
  el 2026-11-05. Los datos técnicos de Polar no sustituyen la percepción.
