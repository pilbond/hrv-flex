<!-- rules_version: 1.3 -->
## Reglas generales
- separa claramente lo observado en los datos de lo inferido
- cuando una capa no sea interpretable, dilo de forma explicita
- prioriza el contenido de mayor senal sobre el relleno; no uses un tono generico ni de plantilla
- si hay tension entre `sessions` y `RR`, exponla y jerarquiza la confianza
- menciona la falta de `FIT/TCX` solo cuando una afirmacion concreta requiera esa granularidad adicional
- usa lenguaje modal cuando el dato no cierre la conclusion: `compatible con`, `sugiere`, `orienta`, `no confirma`
- no uses autoridad retorica o informes previos como sustituto de evidencia del caso

## Reglas de fuentes y calidad
- en `Fuentes`, jerarquiza por funcion analitica (continuidad, FC temporal, contexto integrado, comparativa de bloque); usa tabla markdown con columnas `Rol analitico` y `Fuente` cuando haya 3 o mas fuentes
- trata `session_payload.json` como fuente humana principal y `summary.json` como fuente tecnica reproducible
- no cites `technical_report.md`, `report.md` ni informes previos como evidencia del caso
- si el bundle incluye `fit_path`, tratalo como fuente preferente para continuidad y granularidad temporal; `STREAM_CSV` complementa cuando aporte HR, velocidad o cadencia normalizadas
- si `hr_source = STREAM_CSV` sin FIT, la lectura global e intensidad siguen siendo validas; la ausencia de FIT solo limita trayectoria, splits o distribucion por segmentos
- en `Calidad del dato`, si `summary.json` incluye `duration_consistency`, registra el valor y la diferencia en minutos como trazabilidad
- si `stream_sampling.assumed_1hz = false`, indica que el stream no graba a ~1Hz (señal genuina, no artefacto de pausas); rebaja la confianza solo en conversiones exactas muestras->minutos; no invalida la clasificacion global

## Reglas por seccion
- `Datos`: estructura en apartados curados (`Perfil de sesion` 4-5 datos, `Intensidad` 3-4 bullets, `Estructura util` 2-4 bullets, `Contexto subjetivo` 1-2 bullets); no repitas cifras que luego se reinterpretan con mas valor en secciones posteriores
- `Respuesta interna`: cuando la ausencia de senal confirme un patron controlado, hazla visible (`late_intensity = 0`, `cardiac_drift_pct` bajo, sin acumulacion de Z3); la evidencia negativa sostiene la lectura tanto como la positiva
- `Capa RR`: presenta RMSSD y DFA-alpha1 en tablas markdown; incluye apartado `Sintesis de coste` con scores y sus anclajes observacionales (`cardio_evidence[]`, `mecanico_evidence[]` de `summary.json`); declara la `Limitacion clave` cuando exista; cierra con `Jerarquia de evidencia` numerada (que sostiene la lectura, que aporta RR, que no permite hacer)
- `HR @ alpha1=0.75`: si `hr_at_075_usable = false` pero `hr_at_075_crossing` tiene valor no nulo, incluye en `Capa RR` una linea de estimacion secundaria con este formato exacto: `HR estimada en α1=0.75: ~X lpm (mediana de N cruces HR-sorted, confianza: C)`; si `confidence = low` o `approximate` añade entre parentesis `solo orientativo`; nunca uses esta estimacion para validar umbrales o reclasificar zonas
- `Contexto de recuperacion y carga`: estructura en apartados (`Sueno previo`, `HRV matinal`, `Carga reciente`); si `gate_badge` es favorable pero `reason_text` introduce cautela (baseline60_degraded, saturacion parasimpatica), resuelve la tension en un apartado `Tension explicita` que diga que tipo de verde es y que permite o impide
- `Contexto de recuperacion y carga`: si `baseline60_degraded = True`, rebaja la fuerza del lenguaje; no conviertas HRV matinal + feel en diagnostico cerrado
- `Encaje en el bloque`: incluye tabla cuantificada con 3-4 sesiones relevantes (fecha, deporte, duracion, D+, work_total_min, load); prioriza sesiones comparables sobre recencia ciega; tras la tabla, lectura comparativa breve
- `Conclusion`: integra la sintesis de coste (cardio_score, mecanico_score, coste_dominante) con la clasificacion cualitativa; el lector debe poder verificar que la etiqueta esta sostenida por datos concretos
- `Interpretacion fisiologica`: ancla al menos una observacion a un valor numerico medido (RMSSD, alpha1); cuando la huella mecanica condicione mas la recuperacion que la fatiga central, dilo
- `Interpretacion fisiologica`: no conviertas Naismith, `pace equivalente`, drift, `residual_z`, `hr_at_075_crossing` o molestias subjetivas en la prueba principal de una conclusion fuerte
- `Implicacion practica`: incluye arbol de decision concreto para la sesion siguiente con 2-3 escenarios condicionales anclados a variables observadas; si la recomendacion sirve para cualquier sesion, no aporta valor
- `Implicacion practica`: no derives decisiones fuertes desde una unica heuristica debil o desde una molestia aislada
- `Confianza`: cuando las capas tengan calidad distinta, desglosa en tabla (Capa, Nivel, Limitacion); no uses etiqueta plana si la clasificacion global es robusta pero la lectura fina no lo es

## Seccion 0: Veredicto
- Sintesis en 2-3 frases: que fue la sesion, fue adecuada, que implica
- Incluye coste_dominante y clasificacion cualitativa
- El lector debe saber si preocuparse ANTES de leer el detalle

## Formato visual
- usa separadores `---` entre secciones principales
- usa negrita para apartados dentro de secciones
- prefiere tablas sobre listas de bullets cuando el contenido sea cuantitativo y comparable
