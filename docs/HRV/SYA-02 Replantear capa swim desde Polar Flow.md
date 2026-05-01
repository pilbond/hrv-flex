# SYA-02 Replantear capa swim desde Polar Flow + fallback TCX

## Texto de la tarjeta (canvas)

> ## SYA-02 TYM-02 FP-04 Replantear capa swim desde Polar Flow + fallback TCX
> Sustituye el enfoque original centrado en length messages del FIT. Evidencia nueva: Polar Flow muestra fases de natacion con estilo, descanso, distancia, duracion, FC, brazadas, frecuencia de brazada y SWOLF; el FIT/TCX actual no preserva completa esa capa. Iteracion A: localizar fuente programatica primaria de Polar para swim phases y, si existe, exponer swim_context reproducible en analysis con pool_length_m=25, stroke_distribution, swolf_by_stroke, stroke_rate_by_stroke, rest_time_total y artifact swim_phases.csv. Iteracion B: si esa capa no es accesible, construir fallback desde TCX usando trackpoints y mesetas de distancia a multiplos de 25m para reconstruir largos, pausas en pared y degradacion basica, sin inferir estilo donde no haya dato directo. La integracion en cost model queda fuera de alcance inicial. Esta revision corrige que i138090502 no justifica open_water y que el problema real es de ingestión de la capa swim, no de inexistencia de dato en Polar.

Relación directa con: `docs/HRV/FP-04 SWOLF y parametros mecanicos de natacion.md` (diseño semántico heredado).

---

## Análisis técnico 2026-04-23

### Estado actual del código

- `analysis/session_cost_model.py:338-363` — `swim_mechanical_score` decide por `work_total_min`, `work_longest_min` y `z3_pct`; `confidence` fijo en `"low"`. Es la raíz de `bajo_estimulo` para cualquier natación.
- `analysis/session_analysis_pipeline.py:906, 1232-1240, 5682-5685` — el prompt analítico ya menciona SWOLF y brazada como "apoyo técnico/propulsivo", pero no hay datos que alimenten esas referencias.
- `analysis/fit_speed_utils.py`, `analysis/fit_terrain_utils.py` — parsers FIT existentes, orientados a run/bike. No existe `fit_swim_utils.py`.
- `hrv_app/polar_client.py:56-67` — AccessLink solo expone `/exercises`, `/exercises/{id}?samples=true`, `/users/sleep/{date}`, `/users/nightly-recharge/{date}`. **No hay endpoint público para phases de swim.**
- Sesión de referencia: `analysis/reports/2026/04/2026-04-07_15-16_swim_i138090502/artifacts/session.fit`.

### Fuentes Polar candidatas (iteración A)

1. **Polar AccessLink `/exercises/{id}?samples=true`** — ya usado; los samples vienen como arrays por tipo (HR, cadence, distance, speed). Habría que confirmar si existe un sample-type con `stroke_type`, `swolf` o `strokes` para swim. Posiblemente disponible `heart_rate`, `cadence` (stroke rate), `distance`; SWOLF y estilo no están documentados como sample-type estándar.
2. **Polar Flow (web)** — muestra las fases con todo el detalle, pero es UI, no API oficial. Scraping no recomendado (rompe al cambiar UI, ToS).
3. **Polar Flow export TCX / GPX / FIT** — export oficial descargable; candidato para fallback B.
4. **Training data de `exercise-transactions`** (AccessLink training data) — posible fuente de FIT/TCX/GPX crudos con el detalle que la UI muestra.

**Acción previa a diseño**: probar los cuatro endpoints de `exercise-transactions` (`/samples`, `/heart-rate-zones`, `/fit`, `/tcx`, `/gpx`) contra la sesión i138090502 y dump del FIT real (session + lap + length messages).

### Errores / riesgos del enfoque

1. **Supuesto a validar**: que Polar expone los phases programáticamente. Si solo están en la UI web de Flow, el proyecto colapsa a la iteración B (TCX/FIT parser) — que ya es el alcance original de TYM-02.
2. **Reconstrucción desde TCX por mesetas de distancia a múltiplos de 25m** es frágil: el GPS en piscina cubierta suele estar apagado; la distancia en TCX puede venir del acelerómetro post-procesado, no granular por largo. Hay que verificar con un TCX real antes de comprometerse.
3. **Inferencia de estilo sin dato directo** — la tarjeta lo prohíbe explícitamente, lo cual es correcto. El fallback TCX puede reconstruir largos y descansos, pero no `stroke_type` salvo que el TCX lo preserve como `TPX` extension.
4. **`rest_time_total` desde TCX**: solo recuperable si el trackpoint timeline tiene huecos temporales o flags de pausa; no siempre es el caso con auto-pausa deshabilitada.
5. Duplicidad con TYM-02: ambas tarjetas proponen artifact de swim + context. Riesgo de diseños paralelos si no se marca subsumción explícita.

### Mejoras propuestas

1. **Paso 0 exploratorio (pre-diseño)**: script one-shot que dump-ea el FIT de i138090502 (todos los `length`, `lap`, `session` messages; todos los campos) + el TCX equivalente + respuesta cruda de AccessLink samples. Sin ese dump, cualquier diseño posterior se apoya en supuestos.
2. **Unificar semántica con FP-04**: reutilizar íntegro el contrato `swim_context` del MD de TYM-02 (pool_length_m, primary_stroke, swolf_by_stroke con `too_few_lengths`, exclusión de drill, `hr_confidence = low_wrist_in_water`). Añadir `stroke_rate_by_stroke` y `rest_time_total` que SYA-02 introduce como nuevos.
3. **Artifact renombrado**: la tarjeta propone `swim_phases.csv`; FP-04 propone `swim_lengths.csv`. Conciliar en un único artifact con granularidad por largo y, si hay fases de Polar Flow accesibles, columna `phase_id` para agrupar.
4. **Campo `swim_source` obligatorio** en el output (`polar_flow_api` | `fit_length_messages` | `tcx_distance_plateaus` | `none`) — crítico para trazabilidad y para que el analista IA sepa el nivel de confianza.
5. **Corrección del malentendido i138090502**: la tarjeta aclara que no era open_water. Esto invalida la rama `open_water_no_pool_length` como explicación del fallo actual — el `pool_length_m` está ahí, lo que faltó fue el parser. Registrar este hallazgo en el análisis retrospectivo.
6. **Sin integración en cost model** en esta tarjeta — bien. Evita el `confidence_mecanico = medium` prematuro. Es consistente con la separación en iteración B de FP-04.

### Relación con otras tareas

- **TYM-02 / FP-04** queda **subsumida** por SYA-02. El diseño semántico de FP-04 se mantiene; SYA-02 lo extiende con la búsqueda de fuente Polar Flow como iteración A preferente y el fallback TCX como iteración B complementaria al parser FIT ya contemplado.
- No bloquea a tareas cardio/terrain; es independiente del flujo trail/road/bike.
- Mantiene el principio SS-01 (dato vs proxy vs inferencia): SWOLF/brazada de Polar = dato directo; reconstrucción TCX por mesetas = proxy; cualquier estilo no declarado = no inferir.

### Conclusión

La tarjeta corrige el diagnóstico (problema de ingestión, no ausencia de dato en Polar) y reordena bien el árbol de decisión: primero buscar fuente programática Polar Flow, luego caer a FIT `length`, luego a TCX. El alcance de FP-04/TYM-02 no se pierde — se reubica como rama de fallback. Recomendable **ejecutar primero el paso 0 exploratorio** (dump de i138090502 desde las cuatro fuentes) antes de comprometer el diseño detallado, para evitar reescribir contrato si Polar AccessLink sí expone sample-types swim o si el TCX no da la granularidad asumida.
