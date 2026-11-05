# HG-09: Política de Calidad HRV para la ventana 90–375 s

**Estado 2026-10-27:** cerrada (`green` en Kanvas). La decisión vigente está en §9: mantener la exclusión de `LAT_NAN` y de `STAB_LAST2_MISMATCH` en las referencias, con cautela de acción. La recomendación inicial de incluir solo `MISMATCH` (§7) queda como antecedente tras la evidencia insuficiente de §8. La entrega operativa se concreta en [HG-10](<HG-10 Corte historico y contrato de pares consecutivos.md>). Esta nota no modifica el pipeline ni el contrato vigente.

## 1. Pregunta que debe resolver

Si se calcula el CORE con pares originalmente consecutivos de HG-03, inicio fijo a 90 s y corte máximo del registro a 375 s (fin útil habitual cercano a 360 s), **¿qué incidencias deben cambiar `Calidad` y cuáles deben quedar solo como aviso?** Hay que medir también el efecto posterior sobre los días elegibles para roll-3, base de 60 días, SWC, semáforo y acción.

La pregunta principal es el tratamiento de `STAB_LAST2_MISMATCH`. `tail_mismatch_pct` compara el RMSSD de los últimos 120 s con el del tramo completo; una diferencia >15% marca `Unstable` y penaliza Calidad en la regla vigente. Esa discordancia **no es por sí sola un error RR ni una prueba de que exista o no una meseta fisiológica**.

La decisión secundaria es si `LAT_NAN` debe seguir penalizando automáticamente Calidad cuando la latencia ya no decide el comienzo de la ventana. Ambas decisiones deben evaluarse por separado antes de estudiar su combinación. El veto agudo y los umbrales del semáforo son problemas relacionados, pero no se rediseñan en esta tarea: se registran para no atribuirles a Calidad cambios que tienen otra causa.

## 2. Frontera con las demás tareas

- [HG-04](<HG-04 Ventana de calculo de RMSSD_stable y revision de estabilizacion.md>) estudia la geometría y deja **90 s + corte 375 s como candidato práctico**, sin demostrar superioridad fisiológica ni aprobar una migración. HG-09 toma esa geometría como escenario fijo para comparar políticas de Calidad.
- [HG-03](<RR_PARES_CONSECUTIVOS_TAREA.md>) preserva la adyacencia original de los pares RR. La comparación debe usar su semántica en todas las ramas.
- [HG-05](<HG-05 Auditoria de deteccion de latidos y calidad de senal en ventana.md>) separa artefactos globales y descartes dentro del tramo; está cerrada (`green`, 2026-10-27; véase §3). HG-06/07/08 investigan diagnóstico ECG, reconstrucción RR y detector en origen. Sus resultados pueden informar HG-09, pero no se presume que una fusión o corrección esté validada.
- **Frontera con [HG-10](<HG-10 Corte historico y contrato de pares consecutivos.md>) (consolidada 2026-10-27).** HG-09 entrega la decisión por flag, la política de referencias y acción, y los efectos medidos en copias aisladas. La implementación, los tests, `docs/contracts/`, el replay histórico y una eventual publicación controlada son de HG-10. El traspaso vigente está en §9; el de §7 es histórico.
- El tratamiento de incertidumbre del **veto agudo** y la elección entre ROJO y ÁMBAR requieren un criterio de decisión propio. HG-09 debe mostrar si un cambio de color nace en Calidad, el roll-3/base, el veto o los umbrales, sin mezclar las conclusiones.

## 3. Estado vigente y escenarios ya calculados

En producción rigen [el diccionario HRV](../contracts/ENDURANCE_HRV_Diccionario.md) y [la estructura canónica](../contracts/ENDURANCE_HRV_Estructura.md): `Calidad` puede ser `OK`, `FLAG_mecánico` o `INVALID`. Un `FLAG_mecánico` conserva un gate informativo, pero se excluye de las referencias limpias y activa cautela en la acción. `STAB_LAST2_MISMATCH` fuerza `HRV_Stability = Unstable`; `LAT_NAN` también penaliza según el contrato actual. `Artifact_pct` es global al registro: >15% impide `OK` y >20% fuerza `INVALID`. **Ningún replay de HG-04 ha cambiado esa norma.**

Los ensayos de HG-04 ya permiten evitar trabajo repetido:

| Comparación aislada | Resultado ya medido | Límite |
|---|---|---|
| Corte 375 s con QA vigente → mismo corte sin penalización automática de `LAT_NAN` (`H3S90T375NL`) | RMSSD y FC diarios idénticos en 506 fechas; 36 etiquetas de Calidad y 38 semáforos distintos. ~~En 22 días `LAT_NAN` era el único motivo de FLAG.~~ **[Corregido 2026-10-27]** Los 36 días que cambian tienen `LAT_NAN` como único motivo (estabilidad OK, artefactos ≤15%). La cifra de 22 de HG-04 §15 son los días que el corte a 375 s añade frente a `H3S90`. | Cambia la elegibilidad histórica y sus referencias, no el valor diario. No demuestra que los días recuperados sean fiables. |
| `H3S90T375NL` → misma copia quitando también la penalización de `STAB_LAST2_MISMATCH` | 29 días recuperados como `OK`; 30 semáforos distintos: 8 por Calidad del propio día y 22 por arrastre | Contar cambios no dice qué política acierta. El total de ROJO permanece en 123 en el ensayo documentado. |
| Señal y ECG originales de diez días marcados de era ECG | Entre 30 discrepancias revisadas no se halló error del conversor que explicase la discordancia. Diez días clase D, cero clase E; otros 19 de los 29 permanecen no determinables. El VPP observado es 0/10 (Wilson 95%: 0–27,8%). | Los 4.361 latidos concordantes no se revisaron uno a uno. La comparación no ve errores compartidos, desvíos <60 ms ni ectópicos. Cero de diez no estima sensibilidad ni especificidad del corte del 15%. |
| Treinta ventanas alternativas de 120 s por cada uno de esos diez días | Rango de medianas diarias de discordancia 9,12–16,74%; la cola cae en el decil superior en 7/10 | La muestra se escogió por la propia discordancia de la cola. La selección puede favorecer ese 7/10, pero no lo garantiza; falta contraste independiente. |

La cola tiene RMSSD menor que el tramo en 367/503 días (73%) y en 33/35 días con `tail_mismatch_pct ≥15%` (94,3%). Es un patrón descriptivo, no un criterio de calidad validado. La comparación antigua con diez controles `<8%` se retiró del argumento: no quedaron guardadas sus fechas ni la semilla concreta.

De los 30 cambios de semáforo al retirar `MISMATCH`, cuatro corresponden a días con ECG original auditado: **2026-03-31 y 2026-09-18** pasan de ÁMBAR a VERDE; **2026-05-18 y 2026-07-07**, de VERDE a ÁMBAR. En esos cuatro no se detectó un error del conversor de la clase visible para la auditoría. Esto no determina cuál color es mejor: sirve para revisar la consecuencia práctica de cada política.

**Fuentes de los resultados:** [nota HG-04](<HG-04 Ventana de calculo de RMSSD_stable y revision de estabilizacion.md>), [ensayo incremental de Calidad y semáforo](../../research/reports/hg04_calidad_semaforo_incremental_2026-10-23.md), [evidencia de `MISMATCH` y veto](../../research/reports/hg04_evidencia_mismatch_veto_2026-10-25.md), [auditoría RR ampliada](../../research/reports/hg04_errores_rr_ampliacion_10dias_2026-10-26.md), [resumen reproducible de las diez ventanas](../../research/experiments/hg04_replay/results/hg04_rr_ventanas_10dias_resumen_2026-10-26.csv) y [libro de 29 días](../../out/hg04_errores_rr_2026-10-26/ampliacion_10dias/errores_rr_29dias_actualizado.xlsx).

## 4. Opciones a contrastar

Comparar **las mismas fechas, RR, geometría, filtros, RMSSD y FC**. Variar solo la política indicada, con replay cronológico completo de FINAL:

1. **Referencia conservadora:** `LAT_NAN` y `STAB_LAST2_MISMATCH` mantienen su efecto vigente en Calidad.
2. **Sin penalización por latencia:** `LAT_NAN` queda visible como diagnóstico, como en `H3S90T375NL`; `STAB_LAST2_MISMATCH` conserva su efecto.
3. **Sin penalización automática por discordancia:** desde la opción 2, `STAB_LAST2_MISMATCH` queda visible, pero no excluye por sí solo un día de las referencias limpias. No elimina otros motivos de FLAG/INVALID.
4. **Sustituto multiventana, solo exploratorio:** resumir la discordancia de todas las ventanas de 120 s, con definición y umbral fijados *antes* de mirar las decisiones. No considerar la mediana superior por usar más ventanas; debe demostrar repetibilidad y utilidad.

**Dato de HG-05 (2026-10-27).** Con 90 s + 375 s, el porcentaje de descartes en ventana y el `Artifact_pct` global del registro cortado solo difieren en un umbral del 15%/20% en 3 de 507 días. El corte a 375 s, por sí solo, hace cruzar un umbral a seis días de la era ECG. La definición de `Artifact_pct` con registro cortado se decide en HG-10. Véase el [informe](../../research/reports/hg05_ventana_vs_global_375_2026-10-27.md).

Conservar como controles de seguridad los motivos graves ya contratados (`INVALID`, datos no finitos, artefactos elevados, FC fuera de rango, cola insuficiente u otros defectos independientes). No ajustar el 15% para igualar la tasa histórica de flags ni bajar los umbrales globales de `Artifact_pct` sin la validación por origen y por ventana de HG-05/07/08.

## 5. Plan de evaluación sin repetir lo ya calculado

### 5.1 Protocolo previo y datos

1. Inventariar y verificar huellas de los CORE/FINAL y scripts de los ensayos ya realizados. Reutilizar los resultados para las opciones 1–3 cuando su paridad esté demostrada; recalcular solo una comparación o campo que falte. Fijar fechas, exclusiones y denominadores antes de analizar resultados.
2. Definir **un criterio externo de utilidad** antes de elegir regla. Como mínimo, evaluar si una etiqueta de Calidad nueva identifica días poco repetibles o con señal ECG problemática sin excluir días repetibles y utilizables. Si se usa fatiga, rendimiento o carga posterior, fijar desenlace, horizonte temporal, cobertura y dirección esperada previamente; evitar convertir cambios de semáforo en una etiqueta de verdad.
3. Estimar la **repetibilidad** con pares de grabaciones comparables de la misma mañana, si existen. El par del 2026-07-10 (RMSSD 46,35/46,02 ms; `tail_mismatch` 12,19/0,20%) es una alerta, no una estimación de repetibilidad poblacional. Si no hay pares suficientes, declarar esa pregunta no resuelta.
4. Para la opción multiventana, guardar script, fechas y resultados por día y por ventana. Seleccionar los días para comprobar si la cola destaca mediante un criterio independiente de ella o usar un contraste que modele explícitamente la selección. Separar variación esperable por muestreo de 120 s, deriva temporal y artefactos; no llamar «inestabilidad fisiológica» a toda discrepancia.

### 5.2 Comparación de decisiones

Para cada opción informar, con ejemplos a favor y en contra:

- transición diaria `OK`/`FLAG_mecánico`/`INVALID`, motivo exacto y casos con varios motivos;
- días que entran o salen del roll-3 y de la base 60, antigüedad y número de observaciones limpias;
- cambio del valor usado por el gate, SWC, semáforo y acción; separar **efecto del propio día**, **arrastre por composición de referencias**, **veto agudo** y **cruce de umbrales**;
- cobertura por era Polar/ECG, registros cortos y días `LAT_NAN`, `MISMATCH` o con artefactos;
- discrepancias cercanas a umbrales y decisiones con incertidumbre; las 30 recoloraciones existentes son casos a revisar, **no** métrica de éxito.

El conjunto ECG de diez días solo permite auditar la clase de error detectable por comparación de detectores. Mantener como no determinables los 18 días de era Polar y el 2026-03-06 sin ECG; no trasladarles automáticamente el veredicto de los diez.

## 6. Regla de decisión y entregables

**Antes de ver el resultado final**, fijar márgenes prácticos para repetibilidad, cobertura y utilidad externa, junto con los costes aceptables de excluir una medición buena o admitir una defectuosa. Si ningún escenario supera a la referencia con evidencia suficiente, conservar la regla vigente y documentar la incertidumbre; no elegir por el número de VERDES o por proximidad al sistema actual.

La tarea termina cuando existan:

1. protocolo fechado en `research/reports/` con muestra, desenlaces, márgenes y reglas de comparación previos;
2. tabla por día filtrable y agregados reproducibles, con huellas, denominadores, control de paridad de métricas diarias y atribución de los efectos cronológicos;
3. evaluación explícita de casos favorables, adversos y no determinables, incluida la repetibilidad o su falta de datos;
4. recomendación **adoptar / mantener / evidencia insuficiente** para cada uno de `LAT_NAN` y `STAB_LAST2_MISMATCH`, más el destino de la alternativa multiventana;
5. ~~si se adopta un cambio operativo: implementación y pruebas en ambas rutas de CORE, replay histórico aislado, actualización de `docs/contracts/` y plan de recálculo/despliegue con trazabilidad.~~ **[Corregido 2026-10-27]** Ese trabajo pertenece a HG-10. HG-09 entrega la lista concreta de lo que HG-10 recibe (§7). Hasta entonces, producción y el contrato siguen como están.

El código exploratorio va en `research/**/scripts/`, sus salidas en `research/**/results/` o `research/reports/`; no se importa desde la aplicación. No guardar copias completas de RR personales en el informe ni alterar `data/` durante la evaluación.

## 7. Resultado inicial (2026-10-27, anterior a la revisión de §9)

Protocolo previo: [`hg09_protocolo_2026-10-27.md`](../../research/reports/hg09_protocolo_2026-10-27.md). Informe: [`hg09_politica_calidad_2026-10-27.md`](../../research/reports/hg09_politica_calidad_2026-10-27.md). Script y agregados: `research/experiments/hg09/`. Cohorte A: 506 fechas (2025-05-12 → 2026-10-22), con la geometría fija HG-03 + 90 s + 375 s.

**Comportamiento de FINAL comprobado.** `Action` depende solo de `quality_flag`, es decir, de `Calidad == OK` (`build_hrv_final_dashboard.py:971-973`, `:1279-1290`). Promover un día a `OK` libera su acción aunque siga `Unstable`. Por eso se evaluaron por separado la elegibilidad para referencias y la cautela de acción (brazos «c»).

| Flag | Diagnóstico | Referencias (roll-3, base60, SWC) | Acción del propio día |
|---|---|---|---|
| `LAT_NAN` (36 días como único motivo) | visible | **MANTENER** la exclusión: 32/36 sin defecto técnico (<90%) y 2 días defectuosos cambian su propio semáforo. Resultado frágil: defectos en el borde de los umbrales y tasa post hoc similar en días OK de la era ECG | **MANTENER** la cautela |
| `STAB_LAST2_MISMATCH` (23 días como único motivo) | visible | **ADOPTAR**: 23/23 sin defecto, sin sostén defectuoso, influencia acotada. El artefacto residual sigue sin medirse; se acepta bajo el supuesto de coste del protocolo | **EVIDENCIA INSUFICIENTE** para liberarla: se conserva la cautela |
| Ambos (6 días) | visible | excluido | cautela |

**Efecto de la política propuesta frente a la regla vigente** (misma geometría):

- semáforo: 31 cambios, 4 del propio día y 27 por arrastre (17 solo por base60/SWC);
- acción: 22 cambios, todos por arrastre (8 más permisivos y 14 más restrictivos);
- Action_detail: 23 cambios;
- veto: de 77 a 85 días.

Liberar además la acción añadiría 17 cambios del propio día, 14 a `INTENSIDAD_OK`. Entre ellos está 2026-05-18, con fatiga y dolor altos declarados.

**Incierto o no resoluble con los datos actuales:**

- **Repetibilidad.** Solo hay 4 pares secuenciales. Haría falta ≥20 mañanas con dos grabaciones casi consecutivas procesadas con la geometría candidata.
- **Utilidad externa.** El bienestar subjetivo sigue cubriendo unos 132 días. Haría falta un desenlace prospectivo preregistrado.
- **Alternativa multiventana.** No se ha desarrollado: no hay una pregunta concreta que cambie la decisión.

**Traspaso inicialmente propuesto a HG-10 (sustituido por §9):**

1. Representación de la separación elegibilidad/cautela y actualización de `docs/contracts/`, incluidos `reason_text`/`reason_items`.
2. Implementación en CORE y FINAL con tests: solo `MISMATCH` elegible con cautela; `LAT_NAN` y la combinación excluidos; un día elegible puede activar el veto.
3. Presentación de un gate de color con acción en cautela.
4. Replay histórico aislado de la cohorte completa con estos agregados como control.
5. Lo ya recibido de HG-05: `Artifact_pct` con el registro cortado y los recuentos en ventana.

**Corrección de una hipótesis previa:** durante el inventario se anticipó (~60%) que `LAT_NAN` sería elegible para las referencias. El resultado preregistrado no lo apoya.

## 8. Evidencia nueva sobre `MISMATCH` (2026-10-27, tarde)

Pregunta: ¿excluir los días cuyo único motivo es `STAB_LAST2_MISMATCH` reduce errores de medición o de repetibilidad frente a admitirlos en las referencias?

- Protocolo previo: [`hg09b_protocolo_evidencia_mismatch_2026-10-27.md`](../../research/reports/hg09b_protocolo_evidencia_mismatch_2026-10-27.md).
- Informe: [`hg09b_evidencia_mismatch_2026-10-27.md`](../../research/reports/hg09b_evidencia_mismatch_2026-10-27.md).
- Scripts y agregados: `research/experiments/hg09b/`.

**Resultado: EVIDENCIA INSUFICIENTE** en las dos preguntas.

- **Error de medición** (solo era ECG):
  - 7 casos `MISMATCH` frente a 21 controles OK próximos en fecha;
  - revisión ciega con ECG de 288 casos: discrepancias, 248 concordantes y 19 intervalos aceptados sospechosos;
  - errores confirmados del conversor en 1 caso y 2 controles, todos ya parcialmente neutralizados por `offline`;
  - tras corregirlos, ningún día cambia lnRMSSD ≥0,057 (máximo 0,021) ni cambia de flag;
  - 0/7 frente a 0/21 días con error relevante; IC95% de la diferencia −0,15 a 0,35, más ancho que el margen de 15 puntos.
- **Repetibilidad:** 13 pares de grabaciones repetidas, ninguno con `MISMATCH`. `tail_mismatch_pct` varía una mediana de 6,9 puntos dentro de la misma mañana.
- **Era Polar:** sin ECG; imposible de contrastar.

**Efecto sobre la decisión del §7:** no la confirma ni la refuta. La elegibilidad de `MISMATCH` para referencias seguía apoyándose en el supuesto de coste. **Se conserva la cautela de acción.** La decisión operativa posterior está en §9.

**Pendiente** (criterio y plan en el informe §8):
- repetir la misma evaluación al alcanzar ≥22 casos `MISMATCH` informativos de la era ECG;
- recogida de pares repetidos tras un día `MISMATCH`: **no factible con el runtime actual**. El sync no calcula la geometría candidata ni expone su subtipo; antes se necesitaría un cálculo *shadow* de solo lectura sobre el RR recién grabado y comprobar que entrega el resultado a tiempo. Es una comprobación posterior documentada en el informe HG-09b §8.

## 9. Decisión revisada para el traspaso (2026-10-27)

**Mantener la regla de Calidad vigente para ambos flags al aplicar la geometría candidata.** Un día cuyo único motivo es `STAB_LAST2_MISMATCH` sigue excluido de roll-3, base60 y SWC, y su acción mantiene la cautela. `LAT_NAN` solo y la combinación de ambos también siguen excluidos y con cautela. El diagnóstico permanece visible. Esta decisión conserva el comportamiento actual de Calidad; no adopta la separación de elegibilidad y acción propuesta en §7.

**Motivo del cambio respecto a §7.** El brazo A2c cuantificó el efecto histórico de incluir los 23 días `MISMATCH`, pero no demostró que sus referencias fueran más fiables ni más útiles. La auditoría HG-09b halló 0/7 días ECG `MISMATCH` con error relevante frente a 0/21 controles; el límite superior del IC95% de la diferencia es 0,35, superior al margen previo de 0,15. Los otros 15 días `MISMATCH` de era Polar no tienen ECG de contraste y no existe ningún par repetido con el flag. El supuesto de coste que permitió recomendar A2c no basta ahora para autorizar un cambio de referencias y decisiones. La evidencia tampoco demuestra que la exclusión actual sea mejor.

Los **31 cambios de semáforo y 22 de acción** de A2c siguen siendo resultados contrafactuales válidos para aquella cohorte y geometría; **no son cambios que HG-10 deba implantar**. La pregunta sobre `MISMATCH` queda abierta para una evaluación prospectiva separada, con los criterios de HG-09b §8. No bloquea el trabajo de geometría de HG-10.

**Traspaso vigente a [HG-10](<HG-10 Corte historico y contrato de pares consecutivos.md>):** activar y contratar la ventana y los pares de HG-03/HG-04, resolver ventanas insuficientes y `Artifact_pct` del registro cortado según HG-05, y hacer replay histórico aislado de CORE, BETA_AUDIT, FINAL, DASHBOARD, referencias, gate y acción antes de cualquier migración. Conservar la exclusión de `LAT_NAN` y `MISMATCH` en los tests y en `docs/contracts/`. No añadir campos de elegibilidad/cautela ni la presentación especial de un día `MISMATCH` elegible salvo una decisión posterior respaldada por evidencia. La tarjeta HG-10 de Kanvas sigue en `purple`; su texto se ajustará mediante el CLI cuando pase a un estado editable.

