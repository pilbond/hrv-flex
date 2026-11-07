# IU-21 · Nightly Recharge en el contexto de recuperación

Propuesta de desarrollo del 6 de noviembre de 2026. Autor, Codex.

Tarea vinculada en `kanvas.json`, **IU-21**. Implementada el 6 de noviembre de 2026; revisión con cuatro hallazgos corregidos el mismo día (sección «Correcciones tras la revisión»). Pendiente de nueva revisión humana.

## Objetivo

Incorporar las valoraciones de recuperación nocturna de Polar AccessLink v4 a la persistencia de sueño y al contexto explicativo del brief diario. Hacer que la narrativa distinga duración e interrupciones, carga de sueño relativa al nivel habitual y carga autonómica nocturna.

## Caso que motiva el cambio

El brief diario del 2026-11-06 indicó discordancia entre recuperación nocturna y HRV matinal. El snapshot de producción recuperado desde Dropbox contiene `recovery_support_class=conflicted`, con `sleep_basic_ok` como código de discordancia.

- Duración de 449,5 minutos frente a P10 de 356,15 minutos.
- Siete interrupciones largas frente a P90 de 7,6.
- Sleep score de 68,6139, neutro para los umbrales absolutos actuales de 65 y 75.
- RMSSD nocturno de 32 ms, neutro para los umbrales absolutos actuales de 30 y 40 ms.
- RMSSD matinal de 26,46 ms, caída aproximada del 35 % frente a la base y veto agudo activo.

El usuario observó Nightly Recharge muy malo en Polar Flow, con valoración desfavorable de sueño y SNA. Esa valoración procede de su comunicación. Queda pendiente contrastarla con la respuesta original de su cuenta para esa fecha.

La regla actual convierte la ausencia de alertas de duración e interrupciones en apoyo favorable. Un rojo con apoyo y sin cautelas se etiqueta como discordante. Los percentiles de sueño se calculan sobre el histórico disponible, mientras Polar ofrece valoraciones relativas a su propia referencia personal.

## Disponibilidad y situación actual

La app ya consulta sueño y Nightly Recharge mediante `hrv_app/polar_gateway.py`. El adaptador `v4_nightly_to_internal` conserva RMSSD, RRI y respiración, pero omite las valoraciones y referencias personales de Polar.

| Dato documentado en v4 | Uso propuesto |
| --- | --- |
| `recoveryIndicator` | Valoración global de recuperación, escala 1–6 |
| `recoveryIndicatorSubLevel` | Detalle dentro de la categoría, opcional para trazabilidad |
| `ansStatus`, `ansRate` | Valor y clasificación del componente autonómico |
| `sleepScore.scoreRate` | Valoración de la puntuación de sueño frente al nivel habitual, escala 1–5 |
| `meanBaselineRmssd`, `sdBaselineRmssd` | Referencia personal del RMSSD nocturno |
| `meanBaselineRri`, `sdBaselineRri` | Referencia personal del intervalo entre latidos |
| `meanBaselineRespirationInterval`, `sdBaselineRespirationInterval` | Referencia personal del intervalo respiratorio |

Verificar las unidades y la correspondencia de códigos con etiquetas antes de implementar, especialmente `ansStatus` y `ansRate`, cuya descripción pública es limitada. Documentar qué campos son opcionales y cómo se representan ausencias.

La documentación incluye `hrvSamples` y `breathingRateSamples`. Su cobertura temporal real requiere inspección. La comparación entre inicio y final de la noche queda como posible ampliación posterior, condicionada a cobertura y calidad verificadas.

## Desarrollo previsto

1. Consultar de forma segura los payloads v4 de sueño y Nightly Recharge del 2026-11-06 y otras fechas contrastables. Registrar valores relevantes y procedencia, evitando credenciales. Si se necesita conservar una auditoría exploratoria, seguir `research/AGENTS.md` y su estructura.
2. Definir los campos adicionales de `ENDURANCE_HRV_sleep.csv`, sus tipos, unidades, valores permitidos y tratamiento de ausencias. Priorizar las tres valoraciones y las referencias personales necesarias para explicarlas. Preservar valores numéricos de origen para trazabilidad.
3. Extender adaptadores y `sleep_store` reutilizando el flujo de consulta y escritura atómica. Admitir CSV históricos de 17 columnas, añadiendo campos vacíos hasta que exista dato de Polar. Una respuesta parcial no debe borrar valores válidos ya persistidos. Mantener explícitos los resultados de consulta pendiente y error.
4. Revisar en `build_hrv_final_dashboard.py` la clasificación del contexto de recuperación. `sleep_basic_ok` debe expresar ausencia de alerta básica. Para declarar apoyo favorable o discordancia se necesitará evidencia positiva explícita. Definir una tabla de decisión para valoraciones favorables, desfavorables, mixtas y ausentes, con precedencia clara y sin contar varias veces componentes correlacionados del mismo índice.
5. Incorporar al payload y al snapshot del brief diario las valoraciones de Polar, su fecha y los motivos de la clasificación. Ajustar instrucciones y fallback determinista para nombrar la señal concreta. Evitar que una etiqueta general de recuperación oculte qué componente resulta favorable o desfavorable.
6. Revisar el consumo de sueño por el SSM y sus briefs para asegurar compatibilidad con el esquema ampliado. La adopción de nuevas observaciones o pesos en el modelo exige validación propia y una decisión de alcance explícita.
7. Actualizar `docs/contracts/` por los cambios de esquema y significado del contexto. Actualizar el recuento de columnas y la descripción operativa en `AGENTS.MD` cuando se implemente. Verificar backup, restore, manifiestos y lectores del CSV ampliado.
8. Preparar recuperación histórica por fechas y publicación de manera revisable, con copia previa y comprobación de resultados. Registrar el alcance real de la recuperación que permita Polar. Conservar los briefs originales como evidencia de lo que se publicó.

El alcance funcional propuesto es el contexto de recuperación y su explicación. Una modificación de los criterios que determinan el gate HRV requiere una decisión contractual específica.

## Criterios de aceptación

- Los campos recibidos de Polar llegan a la persistencia y al payload del brief con fecha, unidades y etiquetas verificadas.
- El caso del 6 de noviembre reproduce los valores observados en Flow cuando estén disponibles en la API. Si falta una valoración, la app expresa esa ausencia y conserva el resto de señales válidas.
- Un gate rojo acompañado de valoraciones nocturnas desfavorables produce una explicación coherente. La ausencia de alertas de duración e interrupciones por sí sola deja de generar una discordancia favorable.
- Una noche realmente favorable junto a HRV matinal desfavorable puede describirse como señal mixta, identificando el componente que la sustenta.
- Se prueban CSV históricos, campos opcionales, códigos desconocidos, respuestas parciales y reintentos de sincronización.
- Se verifican el fallback determinista y el contrato del brief IA, incluida su trazabilidad. Los números narrados deben proceder de campos o cálculos autorizados.
- Una comparación antes/después en un directorio aislado documenta el efecto sobre contexto, textos y esquemas, y verifica la estabilidad del gate bajo el alcance propuesto.
- Los contratos y la documentación operativa reflejan el resultado implementado.

## Resultados de la implementación (6 de noviembre de 2026)

Implementado por Claude Code. Gate, `Action`, `Action_detail` y columnas de FINAL y DASHBOARD sin cambios.

### Qué cambia

- **Persistencia.** `ENDURANCE_HRV_sleep.csv` pasa de 17 a 26 columnas. Las 9 nuevas van al final y guardan el valor de origen de Polar.

  | Columna | Origen v4 | Escala |
  | --- | --- | --- |
  | `polar_recharge_status` | `recoveryIndicator` | 1–6, de muy mala a muy buena |
  | `polar_recharge_sublevel` | `recoveryIndicatorSubLevel` | solo trazabilidad |
  | `polar_ans_charge` | `ansStatus` | continuo, aprox. −10 a +10 |
  | `polar_ans_charge_status` | `ansRate` | 1–5, frente al nivel habitual |
  | `polar_sleep_charge_status` | `sleepScore.scoreRate` | 1–5, frente al nivel habitual |
  | `polar_night_rmssd_baseline_mean` / `_sd` | `meanBaselineRmssd` / `sdBaselineRmssd` | ms, solo trazabilidad |
  | `polar_night_rri_baseline_mean` / `_sd` | `meanBaselineRri` / `sdBaselineRri` | ms, solo trazabilidad |

  En la API real, `meanBaselineRmssd` y `meanBaselineRri` llegan siempre a 0; se guardan tal cual y no se interpretan. La referencia respiratoria (`meanBaselineRespirationInterval`) y las series `hrvSamples` y `breathingRateSamples` quedan fuera.
- **Compatibilidad.** Un CSV histórico de 17 columnas se acepta y se completa con las nuevas vacías. Cualquier otro esquema sigue fallando cerrado.
- **Respuestas parciales.** Si un reintento trae menos campos, los valores ya guardados para esa fecha se conservan. Los resultados de consulta pendiente y error no cambian.
- **Clasificación de recuperación en FINAL.**
  - `sleep_basic_ok` significa solo que no hay alerta de duración ni de interrupciones. Ya no cuenta como apoyo y nunca genera por sí solo `supported` ni `conflicted`.
  - Cada dominio aporta como mucho un código. En el dominio autonómico, `ansRate` 1–2 da cautela y 4–5 da apoyo; si existe, sustituye a los umbrales absolutos de RMSSD nocturno. En el dominio de sueño, `scoreRate` funciona igual y sustituye a los umbrales absolutos de sleep score. `recoveryIndicator` solo se usa si falta al menos un componente y los presentes son neutros, para no contar dos veces el mismo índice (ver segunda revisión).
  - Los códigos fuera de escala o no enteros se guardan, pero no se interpretan.
  - Los mensajes nombran el componente concreto. Ejemplos: «ROJO respaldado por estado del SNA nocturno de Polar por debajo de lo habitual y carga de sueño de Polar por debajo de lo habitual», o «ROJO, pero señal mixta: carga de sueño de Polar por encima de lo habitual».
- **Brief diario.** `sleep_context.polar_nightly_recharge` incluye `available`, `sleep_date`, cada valoración con valor, escala y etiqueta (`codigo_desconocido` si cae fuera de escala), `polar_ans_charge` y `polar_recharge_sublevel`. Las referencias personales no se exponen porque sus medias llegan a 0 en la API real (ver contraste). El prompt pide nombrar el componente y no inferir valoraciones cuando `available` es falso. Las valoraciones solo se publican si la fila de sueño es de la misma fecha que el FINAL. La carga de sueño sustituye al umbral absoluto del sleep score (1 → `red`, 2 → `amber`, 3–5 sin cautela por score). La versión de prompt sigue siendo `daily_brief_v1`; el cambio de texto queda registrado en `prompt_hash`.
- **SSM.** Lee sleep.csv por nombre de columna y no usa los campos nuevos. Con el CSV de 26 columnas, el shadow sale idéntico (diferencia máxima 3,6e−15).

### Comparación antes/después

Datos locales de `data/` copiados a un directorio aislado: 516 días, del 2025-05-12 al 2026-11-06. Se compararon el builder de FINAL del commit `781386a` y el actual. El sleep.csv local aún no tiene valoraciones Polar, así que la comparación mide solo el efecto de dejar de contar `sleep_basic_ok` como apoyo.

- **Sin cambios en el gate.** En FINAL solo cambian `recovery_support_class`, `recovery_discordance_flag`, `recovery_discordance_reason` y `reason_text`. En DASHBOARD solo cambia `reason_text`.

| Transición | Días | Efecto en `reason_text` |
| --- | --- | --- |
| VERDE `supported` → `neutral` | 75 | Ninguno, porque VERDE apoyado no tenía mensaje |
| ROJO `conflicted` → `neutral` | 19 | Desaparecen «ROJO, pero hay señales que no encajan del todo» y «Acción: revisar factores externos». En los 19 días la única razón era `sleep_basic_ok` |
| ÁMBAR `supported` → `neutral` | 12 | Desaparece «ÁMBAR con señales objetivas razonables». En 11 días también desaparece «Acción: Z2 controlado es razonable…» |
| ÁMBAR `neutral` → `fragile` | 18 | Aparecen «ÁMBAR con señales de recuperación flojas» y «Acción: mejor sesgo conservador hoy». La cautela ya existía y antes la anulaba `sleep_basic_ok`: carga reciente alta en 15 días, carga alta con intensidad concentrada en 2 y RMSSD nocturno bajo en 1 |

- **Discordancias.** Pasan de 77 a 76 días: 19 menos en ROJO y 18 más en ÁMBAR.
- **Caso del 2026-11-06** (ROJO, `DESCARGA`):
  - Antes: `conflicted`, discordancia `sleep_basic_ok` y «ROJO, pero hay señales que no encajan del todo… Acción: revisar factores externos; la acumulación de días rojos pide descarga».
  - Ahora: `neutral`, sin discordancia. El texto conserva la caída aguda de RMSSD (26 frente a 41 ms, −35 %), la causa del ROJO, la FC y la acumulación de días rojos.
  - Con las valoraciones reales de Polar, el día queda `supported` (ver la segunda comparación).

### Verificación

- Suite `tests/`: 767 tests existentes en verde y 17 nuevos en `tests/test_polar_nightly_recharge_context.py`. Cubren el adaptador con fixtures v4, el CSV de 17 columnas, la respuesta parcial y reintento, los códigos desconocidos, un código por dominio, el ROJO con valoraciones desfavorables, la noche favorable como señal mixta, la estabilidad del gate y el payload del brief.
- Contratos actualizados: `ENDURANCE_HRV_Estructura.md`, `ENDURANCE_HRV_Diccionario.md`, `ENDURANCE_HRV_Spec_Tecnica.md` (v4.21) y `GUIA_PYTHON_SCRIPTS.md`. También el recuento de columnas en `AGENTS.MD` y `CLAUDE.md`.
- Backup y restore copian `ENDURANCE_HRV_*` como archivos completos, así que el esquema ampliado no les afecta.

### Contraste con la API real de Polar

Consulta local a Polar AccessLink v4 el 6 de noviembre de 2026, autorizada por el usuario, con refresh del token v4 local. Se registraron solo campos escalares, sin tokens ni identificadores.

**Caso del 2026-11-06.** Coincide con lo observado en Flow.

| Campo | Valor | Lectura |
| --- | --- | --- |
| `recoveryIndicator` | 1 (subnivel 38) | Nightly Recharge muy mala |
| `ansStatus` / `ansRate` | −8,56 / 1 | SNA muy por debajo de lo habitual |
| `sleepScore.sleepScore` / `scoreRate` | 68,61 / 1 | Carga de sueño muy por debajo de lo habitual |
| `meanNightlyRecoveryRmssd` | 32 ms | Igual que el `polar_night_rmssd` ya guardado |

**Escalas.** Se comprobaron en 13 noches, del 24 de octubre al 6 de noviembre.
- `ansRate` crece con `ansStatus`: −10 a −6,4 dan 1; −3,1 y −2,5 dan 2; 0,8 da 3; 4,1 a 4,6 dan 4. Es coherente con la escala 1–5 frente al nivel habitual.
- `scoreRate` crece con el sleep score, aunque no con umbrales fijos: 68,6 a 71,3 dan 1, 71 a 78 dan 2, 80,6 a 84,1 dan 3 y 87 da 4. Confirma que es relativo al nivel habitual. Por eso sustituye a los umbrales absolutos de 65 y 75.
- `recoveryIndicator` combina ambos. El 28 de octubre (SNA 1 y sueño 4) da 2, y el 3 de noviembre (SNA 2 y sueño 4) da 4. Usarlo solo como respaldo cuando faltan los componentes evita contar dos veces el mismo índice.

**Referencias personales.** `meanBaselineRmssd` y `meanBaselineRri` valen 0 en todas las noches; solo llegan informadas las desviaciones (`sdBaselineRmssd` ≈ 7–10 ms y `sdBaselineRri` ≈ 56–63 ms). `meanNightlyRecoveryRespirationInterval` también vale 0, mientras que `meanBaselineRespirationInterval` ronda 4.340 ms. Las referencias se guardan sin interpretar y no se exponen al brief.

**Otros datos.** `hrvSamples` trae 74–109 valores por noche, cada 5 minutos aproximadamente. La comparación entre inicio y final de la noche sería viable, pero queda fuera de este alcance.

**Retención.** Hay datos de abril, julio y septiembre de 2026, y ninguno en diciembre ni junio de 2025.

### Recuperación histórica local

- **Copia previa:** `data/backup/pre_nightly_ratings/ENDURANCE_HRV_sleep_20261106_214112.csv`.
- **Método.** Un script aparte consulta solo las 298 fechas de `data/ENDURANCE_HRV_sleep.csv` con Nightly Recharge o sleep score, todas de 2026 (del 2026-01-02 al 2026-11-06). Rellena únicamente las 9 columnas nuevas. No usa el flujo del sync porque ese flujo retira la fila si Polar confirma que no hay datos de la fecha.
- **Resultado:** 286 fechas con datos y ningún error. 282 tienen las tres valoraciones principales; 4 tienen solo una o dos, y en dos de ellas (2026-01-02 y 2026-01-04) los códigos son 0, fuera de escala. 12 fechas no traen valoraciones. Las 536 filas y las 17 columnas originales quedan idénticas a la copia.
- **No regenerado.** FINAL, DASHBOARD y los briefs de `data/` siguen como estaban; se regeneran en el próximo sync. Los briefs ya publicados se conservan como evidencia.

### Segunda comparación: con las valoraciones reales

Mismo builder actual, aplicado a una copia aislada del sleep.csv recuperado y comparado con el FINAL del commit `781386a`. El gate, `Action` y `Action_detail` siguen idénticos.

| Transición | Días |
| --- | --- |
| VERDE `supported` → `neutral` | 93 |
| VERDE `supported` → `fragile` | 41 |
| ÁMBAR `neutral` → `fragile` | 27 |
| ROJO `conflicted` → `neutral` | 18 |
| ÁMBAR `supported` → `neutral` | 17 |
| ROJO `conflicted` → `supported` | 14 |
| ÁMBAR `supported` → `fragile` | 3 |

- **Discordancias.** Pasan de 77 a 116 días, y `reason_text` cambia en 192. El aumento viene sobre todo de VERDE frágil.
- **VERDE frágil (41 días, de febrero a octubre de 2026).** La regla ya existente marca un VERDE como frágil si hay cautelas en dos dominios de sueño, o en sueño y carga. Con Polar aparecen más cautelas de sueño: en 36 de esos días se suman a carga alta o intensidad concentrada; en los otros 5 coinciden dos dominios de sueño. El texto añade «VERDE, pero piden prudencia: …» y «Acción: contener la intensidad».
- **ROJO.** 14 días pasan de discordantes a respaldados por SNA o sueño desfavorables, entre ellos el 2026-11-06. En 2026 quedan 8 ROJO con señal mixta real (SNA o carga de sueño por encima de lo habitual).
- **Caso del 2026-11-06.** Queda «ROJO respaldado por estado del SNA nocturno de Polar por debajo de lo habitual y carga de sueño de Polar por debajo de lo habitual… Acción: descarga, solo suave o descanso», con `recovery_context_quality=rich`.
- **Corrección menor.** `recovery_discordance_reason` ya no incluye `sleep_basic_ok` en los ROJO con señal mixta.

### Decisión sobre VERDE frágil

El 6 de noviembre de 2026 el usuario decidió mantener la regla existente. Un VERDE queda frágil cuando hay cautelas en dos dominios de sueño, o en sueño y carga, también si la cautela de sueño procede de una valoración Polar. Solo afecta al contexto y a `reason_text`: el gate, `Action` y `Action_detail` no cambian.

### Correcciones tras la revisión

1. **El brief ya no atribuye al día valoraciones de otra noche (alta).** La lectura sigue tomando la última fila de sueño con fecha menor o igual a la del FINAL para el resto del contexto, pero `polar_nightly_recharge` solo publica valoraciones si esa fila es de la misma fecha. Si no lo es, sale `available=false` con `unavailable_reason="no_sleep_row_for_target_date"` y la `sleep_date` real. Una fila del día sin valoraciones da `unavailable_reason="no_polar_ratings"`. La clasificación del sueño tampoco usa la valoración de otra noche. El prompt pide no mencionar ni inferir valoraciones cuando `available` es falso.
2. **Precedencia del sueño en el brief, coherente con FINAL (media).** Con carga de sueño Polar válida, esa valoración sustituye al umbral absoluto `sleep_score < 65`: 1 → `red`, 2 → `amber`, 3–5 → sin cautela por score. Sin valoración, se mantiene el umbral de 65. Duración corta y fragmentación se evalúan siempre después. Casos fijados con tests: score 50 y valoración 1 → `red`; score 60 y valoración 4 → `green`; score 60 sin valoración → `red`; valoración 4 con sueño corto → `amber`.
3. **Procedimiento reproducible de recuperación histórica (media).** Nuevo `scripts/backfill_polar_nightly_ratings.py`, documentado en `GUIA_PYTHON_SCRIPTS.md`. Hace lo mismo que el script de la recuperación local, con copia previa, log, `--dry-run`, `--since` y ejecución idempotente. Un test cubre CSV legacy, relleno solo de valoraciones, fechas sin datos Polar y segunda pasada sin consultas.
4. **Ejemplo del contrato (baja).** La aserción de `ENDURANCE_HRV_Estructura.md` pasa a 26 columnas y comprueba las escalas de las valoraciones.

Verificación: 24 tests en `tests/test_polar_nightly_recharge_context.py`; suite completa con 791 tests en verde, sin cambios en los `ENDURANCE_HRV_*` de `data/` durante la ejecución.

**Incidencia en los datos locales.** El 6 de noviembre a las 21:55 se ejecutó una restauración desde el backup de Dropbox. Todos los `ENDURANCE_HRV_*` de `data/` se reescribieron, y `sleep.csv` volvió a la versión de 17 columnas sin valoraciones (idéntica a la copia `pre_nightly_ratings`). La versión con las 284 fechas valoradas está en `data/backup/pre_restore/ENDURANCE_HRV_sleep.csv`. El 7 de noviembre, con el visto bueno del usuario, se devolvió esa copia a `data/` (mismas 536 filas y 17 columnas originales idénticas; respaldo del estado anterior en `data/backup/pre_ratings_recovery/`) y se regeneraron FINAL y DASHBOARD solo con el builder, sin sync. Gate, `Action` y `Action_detail` idénticos; `reason_text` cambia en 257 días; el 2026-11-06 queda «ROJO respaldado por…» con contexto `rich`.

### Segunda revisión

1. **El brief no presenta como actual el sueño de otra fecha.** Si la última fila de sueño no es de la noche del FINAL, `sleep_context` solo publica `sleep_for_target_date=false`, la `sleep_date` real y `classification="not_available"`. Ya no publica sleep score, duración, fases ni anomalía de esa otra noche. El prompt pide no describir el sueño en ese caso. Con la noche del día, el contexto es el de siempre más `sleep_for_target_date=true` y `sleep_date`.
2. **Valoraciones parciales en el backfill.** El script reintenta por defecto las fechas con datos Polar a las que les falta alguna de las tres valoraciones principales, no solo las que no tienen ninguna. Hoy son 16 fechas: las 12 sin valoraciones y las 4 parciales. Los valores guardados no se pierden si el reintento trae menos.
3. **Códigos fuera de escala, igual en FINAL y en el brief.** El brief marca `available=false` (`unavailable_reason="only_unknown_codes"`) si ningún código es válido. Los conserva con `codigo_desconocido` para trazabilidad, y la clasificación del sueño cae al umbral de score.
4. **Nightly Recharge ante respuestas parciales.** Se usa si falta al menos un componente y los presentes son neutros. Así, SNA neutro, carga de sueño ausente y Nightly Recharge muy mala da `polar_recharge_poor`, en lugar de quedar `neutral`. Si un componente ya da código, Nightly Recharge no se suma. Con dos componentes neutros tampoco se usa. En el histórico local ningún día cambia con esta regla.

### Pendiente

1. **Despliegue en Railway.** El primer sync con el código nuevo amplía sleep.csv en el volumen sin migración manual. Después, ejecutar en el contenedor `python scripts/backfill_polar_nightly_ratings.py --dry-run` y luego sin `--dry-run`, fuera de cualquier job de la UI, y lanzar un sync para regenerar FINAL, DASHBOARD y el brief. El backup a Dropbox del sync siguiente ya llevará las 26 columnas; restaurar uno anterior devuelve un sleep.csv sin valoraciones.
2. **Commit.** Ningún cambio está commiteado.

## Fuentes y archivos de referencia

- [Documentación oficial de Polar AccessLink v4](https://www.polar.com/polar-api-v4/).
- [Documento técnico de Nightly Recharge](https://www.polar.com/img/static/whitepapers/pdf/polar-nightly-recharge-white-paper.pdf). El componente SNA utiliza cuatro horas desde 30 minutos después del inicio del sueño. La carga de sueño considera el resultado de sueño de la noche.
- `hrv_app/polar_adapters_v4.py`, `hrv_app/polar_gateway.py`, `hrv_app/sleep_store.py`.
- `build_hrv_final_dashboard.py`, `hrv_app/ai/daily_brief.py`, `build_hrv_ssm.py`.
- Evidencia local privada del incidente en `data/ai_briefs/daily/ENDURANCE_HRV_ai_daily_brief_2026-11-06.json`. Mantener los archivos personales fuera de Git.
