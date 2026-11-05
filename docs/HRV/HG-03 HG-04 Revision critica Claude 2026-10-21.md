# Revisión crítica HG-03 / HG-04 — Claude, 2026-10-21

Alcance: estado de [[HG-04 Ventana de calculo de RMSSD_stable y revision de estabilizacion]] y [[RR_PARES_CONSECUTIVOS_TAREA]] (HG-03) a 2026-10-21 17:00, incluido el trabajo de otras sesiones (cabecera «Estado vigente», §14.9–14.10, informes `research/reports/hg03_hg04_control_replay_2026-10-21.md` y `hg04_early_windows_*`, cambios en `build_hrv_core.py` y tests). Cada afirmación se verificó contra código, datos o resultados guardados salvo que se indique. Los porcentajes son juicio técnico no calibrado.

## Resumen

El trabajo es en general sólido y la corrección metodológica de la cabecera de HG-04 es mayoritariamente acertada. Hay **tres errores factuales** (uno mío), **un riesgo de código latente**, **documentación desactualizada en HG-03** y **un riesgo de diseño**: sin un criterio de decisión concreto, HG-04 puede quedar bloqueada indefinidamente.

## 1. Lo que está bien

| Afirmación | Certeza | Evidencia |
|---|---|---|
| La procedencia por índice original (`original_idx_eff`) es más correcta que el criterio por tiempos que usé en el replay del 2026-10-20 | 95% | `build_hrv_core.py:297–349`: el índice se captura antes de quitar duraciones inválidas; el criterio por tiempos no detecta el hueco de una fila `NaN` porque el `cumsum` ya la excluyó |
| `rr_pair_diffs()` es correcto en el caso documentado | 98% | Ejecutado: `[1000,1020,1030,1060]` con índices `[0,1,3,4]` → `[20, 30]` |
| Retirar 180/210 s como «candidatos» y las confianzas asociadas es correcto | 85% | La regla de §14.7 se apoyaba en una referencia tardía no validada y en una submuestra Polar distinta |
| «El replay mide sensibilidad del gate, no exactitud» | 95% | Sin patrón externo no hay forma de saber qué gate acierta |
| Tests de HG-03 añadidos (`tests/test_hg03_rr_pair_provenance.py`, `tests/test_hg03_session_rr_pairs.py`) | — | **No verificados**: la VM no tiene `pytest` ni red para instalarlo |

## 2. Errores factuales

### 2.1 Mío — registros cortos (§13.5 punto 3 de HG-04)

Escribí el 2026-10-21 que «ninguno cae en el periodo `healthy`». **Falso** [99%]: de los 44 registros con `t_end_eff < 375 s`, **11 están en jul–sep 2025** (07-01, 07-06, 07-18, 07-23, 08-12, 08-29, 08-30, 09-02, 09-12, 09-18, 09-24). También eran erróneos los recuentos parciales: son 35 (no 36) hasta 2025-07-23 y 40 (no 37) entre 355 y 375 s. Además, mi «corrección» de 11 → 44 mezcló definiciones: el «11» original y el de §14.10 se refieren a registros sin 180 s disponibles tras el inicio (`t_end_eff < 360`), y el 44 a `t_end_eff < 375`. Ambas cifras son válidas para preguntas distintas.

**Solución:** corregido de forma visible en §13.5 de HG-04.

### 2.2 «Las diferencias frente a C van en ambos sentidos» (cabecera y §14.10)

Impreciso para los inicios más tempranos [95%]. De `results/early_window_2026-10-21.json`, cohorte común n = 303:

| Inicio | Sesgo lnRMSSD | Días más altos / más bajos que C |
|---|---|---|
| 0 s | +0,048 | **258 / 45** |
| 60 s | +0,013 | 166 / 91 |
| 90 s | +0,003 | 123 / 143 |
| 120 s | −0,004 | 109 / 150 |
| 180 s | −0,013 | 101 / 181 |

Es un gradiente monótono: cuanto antes empieza el tramo, más alto el RMSSD, coherente con el descenso intrarregistro de §12. Que ese descenso no demuestre cuál valor es «más válido» es cierto; que no exista dirección sistemática no lo es. Dato útil que no está destacado: **el inicio de 90 s reproduce casi exactamente el nivel actual** (sesgo +0,003, balanceado).

**Solución:** sustituir «van en ambos sentidos» por «son sistemáticas y monótonas con el inicio; su validez relativa no está establecida».

### 2.3 HG-03: discrepancia de 2026-01-12 marcada «sin resolver» — ya tiene explicación

[95%] Verificado en el replay: con pares originales, el detector deja de encontrar estabilización ese día (`Tiempo_Estabilizacion` 360 s → `NaN`), así que el tramo pasa a empezar en 45 s en lugar de 360 s. Mi recálculo del 2026-10-20 aplicaba la corrección de pares **con la latencia vigente**; el original y el replay H3 la aplican **también al detector**. Las dos cifras (90,7 y 64,5 ms) son correctas para definiciones distintas; el día es `INVALID` en ambas.

**Solución:** anotarlo en HG-03 en lugar de «causa no identificada».

## 3. Riesgo de código latente

[90%] `_parse_and_filter_rr()` calcula `time_axis_reliable` pero **ningún consumidor lo usa**:

- Una duración `NaN` en el CSV: la fila se descarta, el eje temporal se comprime en silencio y el día puede salir `Calidad = OK` (verificado con un RR sintético: `OK`, RMSSD 38,6, sin flag).
- Una duración `inf`: `compute_day_from_rr()` **lanza `OverflowError`** (verificado). En el sync diario eso aborta el procesado de ese día.

Ningún RR histórico contiene `NaN` ni `inf` (comprobado en los 501 archivos), así que hoy no hay daño; es un riesgo para datos futuros, sobre todo del convertidor ECG. HG-03 punto 1 ya pide «definir una salida segura»; el riesgo es dar el punto por cubierto porque el flag existe.

**Solución:** en el PR que conecte HG-03 al cálculo canónico, (a) tratar `inf` igual que `NaN` en `valid_mask`; (b) si `time_axis_reliable` es falso, forzar como mínimo `FLAG_mecánico` con un flag explícito (p. ej. `TIME_AXIS_GAP`) y no calcular latencia ni cola; (c) dos tests: duración `NaN` → no `OK`; duración `inf` → no excepción.

## 4. Documentación desactualizada en HG-03

[95%] Siguen sin marcar cifras del inventario antiguo con origen mal clasificado:

- Punto 5: «499 de las 502 filas», «16 zips», «43 CSV sueltos de 2026-09/10». Actual: **504 filas de CORE, 501 con RR**, 17 zips con 483 fechas hasta 2026-09-30 y 19 CSV sueltos de octubre.
- «El recuento real de pares no cruza el umbral de 60 en ningún día de los 497 (mínimo 90)» y «`Tiempo_Estabilizacion` cambia en 4 de 43 días recientes»: salen de la muestra antigua (los «43 días recientes» eran la clasificación errónea). Hay que repetirlos sobre los 501 o marcarlos como superados.

**Solución:** marcar ambos bloques como superados y remitir al informe de control del 2026-10-21.

**Verificación y aplicación (2026-10-21 17:30):** inventario confirmado (504 filas, 501 con RR, 17 zips con 483 fechas hasta 2026-09-30, 19 CSV de octubre). La afirmación de pares era peor de lo indicado arriba: sobre los 501 RR hay **10 días con menos de 60 pares reales en la cola (mínimo 0)**, todos `INVALID`; sin `INVALID` el mínimo es 81, no 90. `Tiempo_Estabilizacion` cambia en 52/504 días (34/220 en la era ECG; 3 de los últimos 43). Las tres correcciones y la explicación de 2026-01-12 están aplicadas en HG-03, y §7 de HG-04 está marcado como superado con un criterio de cierre neutro.

## 5. HG-04 §7 «Criterio de cierre» contradice el estado vigente

[95%] Aún exige ventana de longitud fija, cola anidada con el 15%, columna de longitud y flag de ventana insuficiente: todo eso corresponde a `[180,360]`, que la cabecera ya no aprueba. Quien cierre la tarea mirando §7 trabajaría contra la cabecera.

**Solución:** marcar §7 como histórico y reescribir el cierre en términos neutros respecto a la geometría: (1) regla de inicio y fin elegida con el criterio de §6 de esta revisión; (2) política explícita de ventana insuficiente; (3) QA coherente con la geometría (incluido `STAB_LAST2_MISMATCH`); (4) ambas rutas con la misma regla; (5) contrato y migración; (6) recálculo con trazabilidad.

## 6. Riesgo de diseño: el criterio externo no está definido y puede bloquear la tarea

[80%] La cabecera condiciona cualquier decisión a «un criterio longitudinal externo predefinido», pero no lo define. Con los datos actuales (registros de 6–9 min, sin réplica el mismo día) no puede resolverse dónde acaba el transitorio ni qué inicio es «más válido»: es un límite del diseño de medición, no del análisis. Sin una propuesta concreta, la tarea puede quedar abierta indefinidamente mientras el detector defectuoso sigue en producción.

**Soluciones, por orden de valor:**

1. **Mini-estudio prospectivo (el más informativo).** Durante 10–14 mañanas, grabar 10–12 min tumbado en lugar de 6–9. Permite: ver directamente dónde se aplana el descenso en cada día, medir si su magnitud varía entre días y comparar cada inicio contra una referencia **disjunta y tardía** dentro del mismo registro. Coste: unos minutos diarios. Requiere que el usuario lo acepte; el pipeline actual procesa registros más largos sin cambios.
2. **Criterio externo con datos ya disponibles.** Usando `ENDURANCE_HRV_sessions_day.csv`: predefinir los días tras carga alta y comparar, por inicio candidato, el tamaño del efecto de la caída de lnRMSSD frente a días tras descanso (d con IC95). Una definición que discrimine mejor la carga es más útil para el gate. Limitación: la carga no es un patrón oro (lo dice la propia cabecera); úsese como criterio de utilidad, no de validez.
3. **Criterio de mínimo cambio** si no se quiere esperar: elegir el inicio fijo que reproduce el nivel actual (≈90 s; sesgo +0,003 en la cohorte común) para eliminar el detector y su aleatoriedad sin desplazar el nivel del histórico. No resuelve qué es fisiológicamente correcto, pero arregla el defecto demostrado (detector aleatorio) con el menor impacto. Es un paso intermedio defendible, no una conclusión.

## 7. Lo que queda abierto, sin cambios

- HG-03 PR B/C dependen de la geometría de HG-04.
- `STAB_LAST2_MISMATCH` en cualquier geometría nueva.
- DFA-α1 con huecos (HG-03 punto 10).
