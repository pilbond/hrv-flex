<!-- rules_version: 2.1 -->
## Reglas generales
- separa claramente lo observado en los datos de lo inferido
- cuando una capa no sea interpretable, dilo de forma explicita
- prioriza el contenido de mayor senal sobre el relleno; no uses un tono generico ni de plantilla
- si hay tension entre `sessions` y `RR`, exponla y jerarquiza la confianza
- menciona la falta de `FIT/TCX` solo cuando una afirmacion concreta requiera esa granularidad adicional
- usa lenguaje modal cuando el dato no cierre la conclusion: `compatible con`, `sugiere`, `orienta`, `no confirma`
- no uses autoridad retorica o informes previos como sustituto de evidencia del caso
- trata `analysis_only_context.coach_metrics`, `composite_context.subjective_coherence`, `composite_context.thermal_context` y `composite_context.durability_context` como capas exploratorias de apoyo; no las eleves a contrato canonico ni las uses para contradecir `sessions.csv`, `training_audit` o la capa RR sin declarar la discrepancia de forma explicita

## Tono narrativo
- escribe como analista humano, no como plantilla automatica
- abre cada seccion interpretativa con una lectura breve antes de listar datos, cuando esa lectura aporte claridad
- usa los numeros como soporte de una idea analitica; evita acumular metricas sin explicar que cambian en la lectura
- conserva un tono didactico y directo: explica por que una senal importa, no solo que valor tiene
- evita repetir etiquetas tecnicas si ya quedaron justificadas por datos concretos
- mantiene la prudencia: usa `sugiere`, `compatible con`, `orienta` o `no confirma` cuando la evidencia no cierre una conclusion fuerte
- no suavices advertencias reales ni conviertas señales debiles en decisiones fuertes
- el informe debe poder leerse como una conversacion tecnica con el atleta: trazable, concreto y sin relleno motivacional

## Bloque coaching obligatorio
- despues de `Implicacion practica`, incluye un bloque de lectura coaching con estas secciones, salvo que no haya datos suficientes para sostenerlas:
- `Que Puede Aportar`: que adaptacion o valor especifico suma la sesion
- `Que Puede Restar`: que peaje o riesgo practico puede dejar
- `Balance Neto`: saldo final entre adaptacion y coste
- `Tipo de Fatiga`: fatiga dominante y, si aplica, segunda senal relevante
- `Que Senal Vigilar Ahora`: 1-3 senales concretas que cambiarian la lectura posterior
- `Que Ventana Abre o Cierra`: que tipo de trabajo queda mas o menos disponible despues
- `Que No Sobrerreleer`: interpretaciones tentadoras que los datos no sostienen
- `Que Haria Cambiar la Relectura`: condiciones observables que cambiarian la conclusion
- `Mejor Comparador del Bloque`: sesion o patron mas util para comparar, o declara que no hay comparador fuerte
- `Donde Estuvo el Error`: si no hubo error claro, dilo; no fuerces culpa retrospectiva
- `Que Construye vs Que Consume`: separa adaptacion buscada y coste consumido
- `Que Repetir / Que No Repetir`: una pauta accionable y una cautela concreta
- `Como Habria Encajado Mejor`: ajuste practico de diseno, timing o ejecucion si lo hay
- no conviertas este bloque en relleno motivacional; cada apartado debe derivar de datos o declarar su incertidumbre

## Reglas de fuentes y calidad
- en `Fuentes`, jerarquiza por funcion analitica (continuidad, FC temporal, contexto integrado, comparativa de bloque); usa tabla markdown con columnas `Rol analitico` y `Fuente` cuando haya 3 o mas fuentes
- trata `session_payload.json` como fuente humana principal y `summary.json` como fuente tecnica reproducible
- si `session_payload.json.final_reason_items_contract.fallback_to_reason_text = false` y la seccion `Tension explicita` usa cautelas HRV tipificadas, declara tambien la fuente estructurada de esa capa; cuando aplique, incluye `ENDURANCE_HRV_master_FINAL_reason_items.json` en `Fuentes`
- no cites `technical_report.md`, `report.md` ni informes previos como evidencia del caso
- si el bundle incluye `fit_path`, tratalo como fuente preferente para continuidad y granularidad temporal; `STREAM_CSV` complementa cuando aporte HR, velocidad o cadencia normalizadas
- si `hr_source = STREAM_CSV` sin FIT, la lectura global e intensidad siguen siendo validas; la ausencia de FIT solo limita trayectoria, splits o distribucion por segmentos
- en `Calidad del dato`, si `summary.json` incluye `duration_consistency`, registra el valor y la diferencia en minutos como trazabilidad
- si `stream_sampling.assumed_1hz = false`, indica que el stream no graba a ~1Hz (señal genuina, no artefacto de pausas); rebaja la confianza solo en conversiones exactas muestras->minutos; no invalida la clasificacion global

## Reglas por seccion
- `Datos`: estructura en apartados curados (`Perfil de sesion` 4-5 datos, `Intensidad` 3-4 bullets, `Estructura util` 2-4 bullets, `Contexto subjetivo` 1-2 bullets); no repitas cifras que luego se reinterpretan con mas valor en secciones posteriores
- `Datos`: si existe `analysis_only_context.coach_metrics`, usar `session_rpe`, `feel` e `icu_intensity` solo como capa subjetiva/coach local; no presentarlos como contrato canonico ni como equivalentes directos de `load` o `trimp`
- `Datos`: si existe `session_payload.json.subjective_context.notes_raw`, usarla como nota manual del atleta en `Contexto subjetivo`; no mezclarla con `session_rpe`, `feel` ni con `load`/`trimp`
- `Datos`: cuando `session_rpe` aparezca en narrativa, descomponer al menos la primera mencion como carga tipo Foster (`session_rpe ~= icu_rpe x moving_time_min`) para que la escala sea legible
- `Datos`: si existe `session_payload.json.composite_context.subjective_coherence`, usarla solo como capa exploratoria de coherencia de carga; `session_rpe_load_equiv` y `trimp_load_equiv` son comparaciones lineales normalizadas para el atleta, no conversiones fisiologicas exactas
- `Datos`: si `subjective_coherence_state` sale claramente `coherent` o `mismatched`, conviene mencionarlo una vez cuando ayude a contextualizar la sesion; evita repetirlo si no cambia la lectura
- `Datos`: si existe `session_payload.json.composite_context.thermal_context`, usarla como costo termico simple basado en `average_weather_temp`; no presentarla como WBGT ni como diagnostico de calor cerrado
- `Datos`: si `thermal_band` es `low` o `marginal`, usarla sobre todo para descartar que el calor explique la deriva; no merece protagonismo propio
- `Datos`: si existe `session_payload.json.composite_context.durability_context`, usarla como lectura exploratoria por tercios sobre `session_stream.csv`; no convertirla en taxonomia fuerte por deporte ni confundirla con la capa FP-01
- `Datos`: si existe `session_payload.json.composite_context.durability_context.rolling_only_context`, usarla como variante de control para trail/hike; excluye climbs y suele ser mas interpretable que los tercios brutos
- `Datos`: si existe `session_payload.json.durability_context`, priorizarla como lectura local FP-01 desde primitivas de `sessions.csv` (`decoupling`, `power_ratio`, `speed_ratio`, `durability_applicable`); usar `durability_pattern`, `preferred_signal` e `interpretation_confidence` como apoyo narrativo, no como contrato HRV canonico
- `Datos`: si `durability_hint` sale `terrain_confounded` o `steady_easy`, es preferible traducir esa lectura al texto en lugar de omitirla por parecer "solo exploratory"
- `Datos`: en `trail`, si `power_ratio` aparece sin un perfil de terreno por mitades, tratarlo como señal ambigua porque puede reflejar solo una subida concentrada en la primera mitad y no una degradacion fisiologica cerrada
- `Datos`: en la capa run-aware de `trail`, si `terrain_climb_hr_mean` supera `VT1` o `VT2`, incluirlo en la base del candidato y de la severidad; no dejarlo solo como contexto
- `Datos`: `runaware_context.climb_hr_mean` es alias directo de `terrain_climb_hr_mean`; úsalo cuando necesites acceder programaticamente a la señal sin parsear strings
- `Datos`: si existe `strength_grade`, úsalo para distinguir `terrain_sparse`, `terrain_moderate` y `terrain_robust` cuando la capa sea solo de terreno; `strength = exploratory` no significa que la evidencia sea igual de débil en todos los casos
- `Datos`: si existe `durability_hint_detail`, traduce el subtipo de `terrain_confounded` en lenguaje llano; no colapses `terrain_confounded_hr_peak`, `terrain_confounded_speed_drop` y `terrain_confounded_mixed` en una sola frase vaga
- `Datos`: si `zones_source = fallback`, no subas el peso interpretativo del bonus tecnico trail; la fiabilidad de `work_avg_z3_pct` puede ser insuficiente para justificar ese extra
- `Datos`: si existen `v1_snapshot` y `runaware_context`, explicitar que `v1_snapshot` es la decision minima de AP-01 v1 para ese dia y `runaware_context` es la candidata en sombra; compararlos sin presentarlos como capas equivalentes
- `Datos`: si `runaware_context.terrain_climb_hr_mean` existe, usarlo para contextualizar el peaje cardiovascular de subida y, cuando sea pertinente, compararlo con VT1/VT2 sin convertirlo en contrato canonico nuevo
- `Datos`: si `runaware_context.terrain_climb_vam_mean` existe, usarlo como ritmo vertical medio del tramo dominante y combinarlo con `terrain_climb_hr_mean` para leer el coste de subida sin convertirlo en contrato canonico nuevo
- `Datos`: si `runaware_context.terrain_climb_power_mean` existe, usarlo como potencia media en subida y leerlo junto a `terrain_climb_hr_mean` y `terrain_climb_vam_mean` para cerrar el coste del tramo dominante sin elevarlo a contrato canonico nuevo
- `Datos`: si existe `session_payload.json.narrative_targets.coach_report_examples.datos`, puede reutilizarse como ejemplo de formulacion, pero adaptando el texto al caso y sin copiarlo literalmente
- `Estructura externa`: si existe `analysis_only_context.structured_workout`, usar `coach_intervals.csv` o `coach_groups.csv` solo cuando ayuden a describir bloques o repeticiones con valor tactico; no asumir que toda presencia de `icu_intervals` implica una sesion de intervalos formal
- `Estructura externa`: si existe `session_payload.json.narrative_targets.coach_report_examples.estructura_externa`, usarlo como patron de traduccion tactica por deporte
- `Estructura externa`: si `session_payload.json.terrain_climbs` tiene 2 o mas subidas y el deporte es `bike`, incluye la tabla de subidas del payload tal cual (columnas `#`, `Km`, `D+`, `Tiempo`, `Pend.`, `FC media`, `VAM`; mas `Z1/Z2/Z3` si hay datos de zona; mas `Potencia` si esta disponible); la tabla precede a la lectura narrativa de las subidas, no la sustituye
- `Estructura externa`: si `terrain_climbs` tiene 2 o mas subidas en `trail` o `road`, incluye tabla de subidas con columnas `#`, `Km`, `D+`, `Tiempo`, `Pend.`, `FC media`, `VAM`, `Ritmo (min/km)` (en lugar de potencia); mas `Z1/Z2/Z3` si hay datos de zona; la tabla precede a la lectura narrativa de las subidas, no la sustituye
- `Estructura externa`: si `terrain_climbs` incluye columnas `Z1`, `Z2`, `Z3`, leer la distribucion por subida y destacar cuales concentran tiempo en Z3; si la FC global clasifica la sesion como Z1/Z2 pero alguna subida supera el 30% en Z3, senalarlo explicitamente como exposicion cardiovascular no visible en el agregado
- `Estructura externa`: si la potencia de subida aparece marcada como `*(est.)*` en bike, presentarla con cautela de estimacion: menciona que proviene de un modelo fisico (gravedad + rodadura + aerodinamica), no de potenciometro; no la uses para comparar con FTP ni para validar umbrales de potencia
- `Estructura externa`: si potencia medida aparece en `trail` o `road` (Polar Vantage M3 u otro power meter de running), presentarla sin etiqueta `*(est.)*`; es medicion directa, no estimacion; usa `W/kg atleta` como ratio primario (denominador: masa corporal, convencion sector igual que bike)
- `Estructura externa`: cuando aparezca `W/kg atleta` en potencia estimada (bike), tener en cuenta que los vatios se calcularon para el sistema completo (atleta + bici + equipamiento, ~80 kg por defecto) pero el denominador del ratio es solo la masa corporal del atleta (~68 kg); esto es convencion estandar del sector (igual que Strava o TrainingPeaks) y no un error; no inferir que el atleta produce esos vatios independientemente del peso del equipo
- `Respuesta interna`: cuando la ausencia de senal confirme un patron controlado, hazla visible (`late_intensity = 0`, `cardiac_drift_pct` bajo, sin acumulacion de Z3); la evidencia negativa sostiene la lectura tanto como la positiva
- `Respuesta interna`: si coexisten `cardiac_drift_pct` y `analysis_only_context.coach_metrics.decoupling_pct`, leerlos como señales relacionadas pero no equivalentes; si divergen, declararlo como discrepancia de capa y no fuerces una fusion
- `Respuesta interna`: en `road` o `trail` con terreno ondulado/quebrado, contextualiza el drift; un `cardiac_drift_pct` moderado no significa automaticamente lo mismo que en una sesion llana y estable
- `Respuesta interna`: si `terrain_fit_context.climb_z3_pct_mean` esta disponible, usarlo para cuantificar la exposicion cardiovascular media en subidas; si diverge del perfil global (p. ej. sesion clasifica Z1-2 globalmente pero `climb_z3_pct_mean > 25%`), nombrar esa tension como dilusion de intensidad y no como contradiccion de datos
- `Respuesta interna`: en trail o ultrafondo, un `climb_z3_pct_mean > 25%` con perfil global Z1-Z2 es patron esperado: las subidas son esfuerzo puntual intenso intercalados en continuidad facil; esto NO es anomalia, es caracteristica del deporte; menciona como "dilusion de intensidad en climbs" para contextualizar, no como falla de control
- `Capa RR`: presenta RMSSD y DFA-alpha1 en tablas markdown; incluye apartado `Sintesis de coste` con scores y sus anclajes observacionales (`cardio_evidence[]`, `mecanico_evidence[]` de `summary.json`) y explicita la `Base mecánica` cuando `mecanico_score >= 2`; declara la `Limitacion clave` cuando exista; cierra con `Jerarquia de evidencia` numerada (que sostiene la lectura, que aporta RR, que no permite hacer)
- `Capa RR`: en `bike` o esfuerzos muy faciles, si aparece `DFA` muy alto junto a `RMSSD` de ejercicio bajo, explica que ambas escalas no son directamente equivalentes; prioriza `DFA-alpha1` para clasificar el dominio de esfuerzo y usa RMSSD como apoyo contextual
- `HR @ alpha1=0.75`: si `hr_at_075_usable = false` pero `hr_at_075_crossing` tiene valor no nulo, incluye en `Capa RR` una linea de estimacion secundaria con este formato exacto: `HR estimada en α1=0.75: ~X lpm (mediana de N cruces HR-sorted, confianza: C)`; si `confidence = low` o `approximate` añade entre parentesis `solo orientativo`; nunca uses esta estimacion para validar umbrales o reclasificar zonas
- `Contexto de recuperacion y carga`: estructura en apartados (`Sueno previo`, `HRV matinal`, `Carga reciente`); si existe `session_payload.json.final_reason_flags.has_explicit_tension = true`, abre `Tension explicita` usando primero `final_reason_items`; solo si no existen, recurre a `reason_text` como fallback
- `Contexto de recuperacion y carga`: cuando `session_payload.json.final_reason_items_contract.fallback_to_reason_text = false`, `Tension explicita` MUST describir los items estructurados por `type` y, cuando existan, `value` y `threshold`; no debe parafrasear `reason_text` como fuente primaria
- `Contexto de recuperacion y carga`: cuando haya mas de un item en `final_reason_items`, distingue su papel fisiologico u operativo; no colapses `intensity_clustering` y `green_load_caution` en una sola prudencia generica si el payload los separa
- `AP-03 / concordancia historica`: si el payload incluye `v1_snapshot`, `v1_shadow_comparison` o `v1_shadow_history`, explica en lenguaje llano que la concordancia mide alineacion de criterio entre AP-01 v1 y la sombra; deja claro que `aligned` es coincidencia, `divergent` es discrepancia de decision y que esto no mide por si mismo cuan dura fue la sesion
- `AP-03 / concordancia historica`: deja claro que `intensity_clustering_flag` de v1 cuenta dias intensos de cualquier deporte, mientras que la sombra rolling compara solo sesiones trail con `shadow_session_candidate=1`; una divergencia puede reflejar diferencia de alcance y no solo error de criterio
- `AP-03 / concordancia historica`: si el payload expone `v1_scope`, `shadow_scope` o `scope_note`, utiliza esa nota para explicar el alcance diferencial antes de comentar alineacion o divergencia
- `AP-03 / concordancia historica`: si existen `strength_grade_summaries`, comentalos como corte adicional para evitar mezclar `terrain_sparse` con `terrain_robust`; no sustituyen el agregado global, pero ayudan a interpretar donde se concentra la divergencia
- `AP-03 / concordancia historica`: si aparece `shadow_positive_rate`, aclara que es tasa de activacion de la sombra, no precision ni valor predictivo; un valor alto puede reflejar sobre-señalizacion, umbral mas sensible o mejor cobertura
- `AP-03 / concordancia historica`: si aparecen `next_day_gate`, `next_day_residual_z`, `next_day_action` o `next_day_hrv_delta`, explicita que son outcomes del dia siguiente usados para aproximar valor predictivo; si faltan, no los inventes
- `AP-03 / concordancia historica`: si aparece `shadow_source`, explicita si la fila es `terrain_only`, `power_only` o `combined`; no mezcles variantes distintas bajo la misma conclusion
- `AP-03 / concordancia historica`: si aparecen `shadow_session_candidate` y `shadow_candidate`, aclara que el primero es la activacion cruda por sesion y el segundo la version rolling comparable con AP-01 v1
- `AP-03 / concordancia historica`: si `v1_shadow_history.row_count < 10`, añade una advertencia de muestra pequena y evita redactar la tasa como si fuera decisoria
- `AP-03 / concordancia historica`: si faltan `next_day_*` en una fila reciente, dilo como advertencia de lift parcial; la ausencia de outcome del dia siguiente significa que esa sesion aun no ha pasado por el pipeline HRV posterior
- `Contexto de recuperacion y carga`: si `final_reason_flags.has_action_constraint = false`, dilo explicitamente cuando cierre la tension; permiso con margen reducido no equivale a restriccion operativa
- `Contexto de recuperacion y carga`: si `baseline60_degraded = True`, rebaja la fuerza del lenguaje; no conviertas HRV matinal + feel en diagnostico cerrado
- `Contexto de recuperacion y carga`: si `gate_badge` ya es `ÁMBAR...` o `ROJO...`, abre `Tension explicita` desde el color/accion (`gate_badge`, `Action`) y usa los items para explicar por que el gate ya cambió; no lo redactes como un verde con cautelas
- `Contexto de recuperacion y carga`: si `gate_badge` sigue en `VERDE...`, puedes abrir desde el permiso condicionado y despues explicar las cautelas tipificadas
- `Contexto de recuperacion y carga`: no presentes `has_action_constraint = false` ni `baseline60_degraded = True` como bullets paralelos al mismo nivel que los `final_reason_items`; el primero es una lectura operativa derivada y el segundo un modificador de precision
- `Contexto de recuperacion y carga`: si `n_sessions dia > 1` y puedes identificar otras sesiones del mismo dia desde `sessions.csv`, menciona cuales fueron y si ocurrieron antes o despues; no dejes la doble sesion como numero sin contexto
- `Encaje en el bloque`: incluye tabla cuantificada con 3-4 sesiones relevantes (fecha, deporte, duracion, D+, work_total_min, load); prioriza sesiones comparables por etapa de bloque, proximidad temporal, intensidad y tipo de estimulo sobre recencia ciega; el mismo deporte ayuda, pero no es un filtro duro; tras la tabla, lectura comparativa breve
- `Encaje en el bloque`: si existe `analysis_only_context.coach_metrics.hr_load` o `session_rpe`, pueden usarse como señales paralelas de carga local, pero presentalas siempre junto a `load`/`trimp` y sin asumir equivalencia de escala
- `Encaje en el bloque`: si existe `session_payload.json.narrative_targets.coach_report_examples.encaje_bloque`, puede usarse como ejemplo de redaccion comparativa prudente
- `Conclusion`: integra la sintesis de coste (cardio_score, mecanico_score, coste_dominante) con la clasificacion cualitativa; cuando `mecanico_score >= 2`, resume en una frase la base mecánica concreta (por ejemplo, `D+/h`, bloque corrible, climbs o VAM) para que el lector vea por que no queda en `1`; el lector debe poder verificar que la etiqueta esta sostenida por datos concretos
- `Conclusion`: si `mecanico_score >= 3` en trail, explicita que el peaje mecánico ya compite con el cardiometabolico y puede empujar la lectura a `mixto`; no lo presentes como simple nota secundaria
- `Interpretacion fisiologica`: ancla al menos una observacion a un valor numerico medido (RMSSD, alpha1); cuando la huella mecanica condicione mas la recuperacion que la fatiga central, dilo
- `Interpretacion fisiologica`: no conviertas Naismith, `pace equivalente`, drift, `residual_z`, `hr_at_075_crossing` o molestias subjetivas en la prueba principal de una conclusion fuerte
- `Advertencias`: si aparece `polarization_index` en `analysis_only_context`, recordar que su formula ICU es opaca; no usarlo como prueba fuerte aislada
- `Advertencias`: si existe `session_payload.json.narrative_targets.coach_report_examples.advertencias`, usarlo como ejemplo de cautela semantica por deporte
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
