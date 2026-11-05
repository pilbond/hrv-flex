# HG-06: ¿Calculamos bien el RR desde el ECG?

Estado: análisis terminado, pendiente de revisión humana (nota de alcance actualizada 2026-10-21). Documento de trabajo derivado de [HG-06 Diagnóstico y referencia ECG](<HG-06 Diagnostico y referencia ECG.md>) y de su [revisión crítica](<HG-06 Revision critica Claude 2026-10-19.md>). **No modifica CORE, FINAL, DASHBOARD ni el convertidor**: el replay usa copias temporales fuera del repositorio; `research/experiments/hg06_replay/results/` conserva solo resultados acotados y huellas.

**Nota de alcance 2026-10-21:** `[180,360]` se conserva más abajo como referencia a una antigua variante exploratoria de HG-04. No es la ventana ahora recomendada ni validada; este replay tampoco elige la ventana futura.

Alcance: era ECG propia (`from_jsonl`). El histórico Polar queda excluido por ahora.

## La pregunta y sus dos mitades

«¿Estamos calculando bien los datos del ECG?» se descompone en:

1. **¿Es correcto cada RR que sale de `egc_to_rr.py`?** Requiere una referencia ECG pico a pico. Es la pregunta de fondo y la que HG-06 todavía no ha podido cerrar.
2. **Si hay errores, ¿cambian algo de lo que se usa?** (`Calidad`, RMSSD, baseline, gate). Se puede responder ya con un replay, sin necesidad de saber la identidad de cada pico.

La parte 1 de este documento responde a la 2; la parte 2 resume qué está ya respondido de la 1 y qué faltaría.

## Parte 1 — Replay de impacto

### Hecho previo verificado: el `offline` histórico es solo rango + delta-RR

`process_pair()` tiene `use_acc_gate=False` por defecto y `hrv_app` no pasa `--use-acc-gate`. Recalculando con la lógica de `rr_events()` (RR fuera de 300–2000 ms, o cambio >20% respecto al RR previo) sobre las duraciones archivadas de los 55 días: **0 discrepancias en 23.394 RR** (`scripts/flags_parity.py`, `results/flags_parity.json`). El ACC no intervino en ningún `offline` de estos días.

Consecuencia: la duda «¿delta-RR o ACC?» sobre por qué se descartan las parejas queda resuelta para este conjunto. Es delta-RR o rango, y por tanto es reproducible.

### Población

Los 55 días `from_jsonl` con al menos una pareja de la regla A fijada en `research/experiments/hg05/results/hg06_full_ecg_cases.csv` (301 parejas). RR originales extraídos de `data/rr_downloads` y verificados por SHA-256 contra esa tabla (`scripts/extract_rr.py`). El número depende de la regla A: otras variantes dan 244–371 parejas.

### Brazos

| Brazo | RR | `offline` | Representa |
|---|---|---|---|
| **C — control** | Originales | Originales | Debe reproducir exactamente CORE y FINAL vigentes. Si no, el replay se detiene. |
| **F1 — fusión en origen** | Cada pareja A sustituida por su suma | Recalculado para todo el día con la regla del convertidor | Lo que habría producido `egc_to_rr.py` sin el pico intermedio (escenario HG-08). |
| **F2 — fusión en capa lectora** | Cada pareja A sustituida por su suma | RR fusionado con `offline=0`; el resto conserva el archivado | Una fusión aplicada sobre el CSV ya existente (escenario HG-07). Los vecinos marcados por el pico partido siguen descartados. |
| **F1w / F2w** *(añadidos tras ver los primeros resultados)* | Igual que F1 / F2 | Igual que F1 / F2 | Misma fusión, pero con la latencia de estabilización (`Tiempo_Estabilizacion`) del control impuesta por fecha. Separa el efecto de la fusión del salto del detector de estabilización. Se ejecuta con una **copia** de `build_hrv_core.py` que difiere del original en 5 líneas (ver «Reproducción»). |

CORE se recalcula con el código actual (`build_hrv_core.py --data-dir <copia> --rr-dir <copia>`), sin pareado HG-03 ni ventana HG-04. FINAL se recalcula sobre **toda la serie**, porque un cambio en un día altera los baselines de los días siguientes aunque estos no tengan parejas.

Entorno: Python 3.10 / pandas 2.3.3 / numpy 2.2.6 (VM remota), distinto del de producción (3.13). El brazo C es la comprobación de que eso no altera los resultados.

### Regla de decisión (fijada antes de ejecutar, 2026-10-19)

Hay **impacto relevante** de la fusión si en el brazo F1 o F2, frente a C, se cumple al menos una:

1. En algún día con `Calidad` `OK` o `FLAG_mecánico` cambia `gate_final`.
2. En algún día `OK` o `FLAG_mecánico`, |Δ `lnRMSSD_used`| ≥ 0,25 · `SWC_ln` de ese día.
3. Algún día `INVALID` pasa a `OK` o `FLAG_mecánico`.

Si no se cumple ninguna, el error de la regla A **no cambia** lo que se usa hoy y la pregunta de fondo (parte 2) pasa a ser de exactitud, no de impacto. Si se cumple alguna, la adjudicación ECG se concentra en los días afectados.

### Resultados

#### 1. Control: reproducción exacta

El brazo C reproduce **CORE (502 × 18), FINAL (502 × 65) y DASHBOARD (502 × 9) sin ninguna diferencia** (numéricas con tolerancia relativa 1e-9, texto exacto). La diferencia de entorno (Python 3.10 frente a 3.13) no afecta. La copia con latencia forzada, aplicada al control (`Cw`), también reproduce CORE exactamente, lo que valida el parche.

#### 2. Regla de decisión: se cumple en los dos brazos

| Criterio | F1 (origen) | F2 (capa lectora) |
|---|---|---|
| 1. Cambia `gate_final` en día `OK`/`FLAG` | 06-15, 06-16, 06-17 (ÁMBAR→VERDE); 06-26 (ROJO→VERDE) | 06-26 (ROJO→VERDE); 07-14 (VERDE→ÁMBAR); 07-15 (ROJO→ÁMBAR); 09-06 (ÁMBAR→ROJO); 09-08 (ÁMBAR→VERDE) |
| 2. \|Δ `lnRMSSD_used`\| ≥ 0,25·SWC | 10 días (máx. 4,2 SWC el 04-20) | 5 días (máx. 2,8 SWC el 06-26) |
| 3. `INVALID` pasa a `OK`/`FLAG` | 03-30 (→FLAG, gate NO→ROJO); 04-19 (→OK, gate NO→VERDE) | 03-30 y 04-19 (→FLAG; gate NO→ROJO y NO→ÁMBAR) |

Según la regla fijada, **hay impacto relevante**. FINAL cambia en 60–65 filas, la mitad fuera de los 55 días del replay, por arrastre de baselines y roll3.

#### 3. Mecanismo: clasificación y valores cercanos al umbral

Con la ventana de estabilización fijada (F1w/F2w), el **RMSSD de cada día apenas cambia**:

| | F1 | F1w | F2 | F2w |
|---|---|---|---|---|
| \|ΔRMSSD\| mediana, 45 días `OK`/`FLAG` | 0,11% | 0,05% | 0,07% | 0,07% |
| \|ΔRMSSD\| máximo | 15,7% | **3,6%** | 67,3% | **2,1%** |

Los saltos grandes de F1/F2 los produce el detector de estabilización: `t_start_eff` pasa de 360 a 180 s (06-29, F1), de 210 a 45 s (06-15, F2), de 45 a 420 s (04-26, F2) o de 240 a 450 s (04-20, F1) con cambios mínimos en la serie. ~~Es una confirmación independiente de lo que documenta HG-04.~~ **Corrección (2026-10-20):** demuestra sensibilidad del detector actual a perturbaciones pequeñas; no prueba que la ventana fija [180, 360] propuesta en HG-04 sea la solución.

**Los cambios de gate son idénticos al fijar la latencia del control**, pero eso no elimina el efecto de pequeñas variaciones de RMSSD/lnRMSSD. ~~Por tanto no vienen del valor del RMSSD, sino de qué días cuentan como limpios.~~ **Corrección (2026-10-20):** el mecanismo es mixto. En 06-15/16/17 y 07-14/15 entran nuevos días `OK` en roll3 o baseline. En 06-26 la `Calidad` de los 60 días anteriores no cambia; diferencias de 0,001–0,02 en lnRMSSD de días ya `OK` mueven baseline y SWC. En 09-06/08 también influyen variaciones pequeñas de valor. FINAL solo usa `Calidad == OK` para roll3, baseline60 y SWC (`build_hrv_final_dashboard.py:972`); algunas fusiones reducen `Artifact_pct` hasta cruzar `ARTIFACT_OK_MAX = 15`:

| Día | Pares A | Amplitud <0,6 / >0,8 | F1w | F2w |
|---|---|---|---|---|
| 03-30 | 14 | 13 / 1 | `INVALID`→`FLAG` (25,9→16,6%) | `INVALID`→`FLAG` (25,9→19,0%) |
| 04-19 | 20 | 18 / 1 | `INVALID`→**`OK`** (26,0→12,7%) | `INVALID`→`FLAG` (26,0→16,8%) |
| 06-10 | 7 | 7 / 0 | `FLAG`→**`OK`** (18,2→14,8%) | sin cambio |
| 06-15 | 12 | 7 / 4 | `FLAG`→**`OK`** (20,0→13,9%) | sin cambio (**15,01%**, umbral 15,0) |
| 07-12 | 16 | 11 / 1 | sin cambio | `FLAG`→**`OK`** (17,6→9,3%) |

Atribución de cada cambio de gate:

| Día | Causa | Tipo |
|---|---|---|
| 06-15, 06-16, 06-17 (F1) | 06-10 y 06-15 pasan a `OK` y entran en roll3: `lnRMSSD_used` del 06-15 pasa de 3,645 a 3,805 | Clasificación |
| 07-14, 07-15 (F2) | 07-12 pasa a `OK` y entra en roll3 y baseline | Clasificación |
| 03-30, 04-19 (ambos) | Días sin decisión que pasan a tenerla | Recuperación |
| 06-26 (ambos) | Veto agudo al filo: margen −0,013 en C; el SWC del baseline pasa de 0,088 a ~0,099, el veto se desactiva y `lnRMSSD_used` vuelve a la media de 3 días | Umbral al filo |
| 09-06, 09-08 (F2) | `d_ln` a ±0,002 del umbral; un cambio mínimo de base60/SWC lo cruza | Umbral al filo |

#### 4. Lectura

- **Valor del RMSSD:** en los días utilizables, la regla A apenas cambia el RMSSD calculado (≤3,6% con la misma ventana; mediana ≈0,05%). Seguridad: 90%.
- **Clasificación:** la regla A cambia la `Calidad` de 3–4 de los 55 días; esto afecta algunos gates por arrastre y da decisión a 2 días antes `INVALID`. Otros gates cambian por variaciones de valor aun sin transición de `Calidad`. La atribución debe hacerse día a día.
- **Umbral al filo:** 06-26, 09-06 y 09-08 cambian por márgenes de 0,002–0,013 en ln. En este replay los mueven pequeñas variaciones de valor de días anteriores; el mecanismo concreto depende de las parejas fusionadas. Enlaza con el hallazgo de márgenes de decisión del estudio de 6 minutos.
- **Implementación:** F1 y F2 cambian conjuntos de días distintos (06-15: 13,9% frente a 15,01%). El resultado concreto depende de cómo se implemente la fusión, no solo de si se hace.
- **Supuesto:** todo esto asume que fusionar es correcto, es decir, que cada pareja A es un latido partido o una extrasístole interpolada. **No está validado.**

#### 5. Siguiente paso: regla de cierre en revisión (2026-10-20)

~~La morfología visual «no es QRS normal» en ≥90% de candidatas y «QRS normal» en ≥90% de controles aleatorios bastaría para justificar la fusión y cerrar HG-06.~~ **Corrección:** la muestra visual de 48 figuras tuvo controles débiles, pero no controles negativos independientes. Los RR muestran que 24/24 candidatas y 19/24 controles tenían ambos vecinos a ≤1,1 s; con una mediana alternativa de 20 vecinos, 21/24 candidatas y 17/24 controles tenían suma/mediana entre 0,9–1,1. La comparación visual 18/24 frente a 17/24 carecía de capacidad para medir si la regla A distinguía el patrón: ambos grupos compartían buena parte de esa geometría. La regla A parece seleccionar una parte de un conjunto mayor de picos débiles con geometría parecida, en consonancia con los 332 débiles no candidatos del censo. La revisión de 40 figuras tampoco fue ciega efectiva porque los intervalos visibles de los marcadores delataban el grupo. La forma visual por sí sola no establece que fusionar sea correcto.

La temporización de la regla A selecciona geometrías RR sospechosas, pero no valida la identidad del pico. La [prueba objetiva acotada](../../research/experiments/hg06_objective_ecg/README.md) comparó ECG sin filtrar en 24 parejas planificadas y 23 medibles. La amplitud cruda fue menor en candidatas en **18/23** (diferencia mediana −0,0504; p bilateral exacto 0,0106; p ajustado por tres medidas 0,0319). Es una señal exploratoria pequeña, sin conclusión según el criterio fijado de 22/24 y con controles que comparten geometría RR. La medida llamada inicialmente ruido se renombró actividad de ventanas adyacentes: puede incluir onda P o T. El resto de medidas tampoco alcanzó el criterio. Resultado **no concluyente para identidad y fusión**. HG-07 no se activa y el gate no cambia.

El pico débil no candidato del 2026-04-15, índice RR 88, cae dentro de la ventana RMSSD, pero sus dos intervalos laterales (1,115 y 1,161 s) son próximos a la mediana del día (~1,176 s) y no tienen la geometría de un intervalo partido. ~~Exige revisar el caso.~~ **Corrección:** no hay señal temporal de contaminación directa del RMSSD; la amplitud baja aislada no basta para clasificarlo como falso.

## Orden de trabajo entre tareas HG (2026-10-19)

No vinculante para el contenido de este documento, pero queda registrado por el contexto que da:

1. **HG-01, HG-02** — sin relación con el cálculo del RR; en cualquier momento.
2. **HG-06** — prueba objetiva acotada terminada; registrar el límite de evidencia. No activar HG-07 con estas parejas sin validar.
3. **HG-03 + HG-04** — estudiar su implementación y validación propias antes del recálculo del histórico. El replay no valida la ventana fija de HG-04. HG-07 comparte con HG-03 la necesidad de leer los RR conservando el índice original de cada latido.
4. **Revisión de la métrica de calidad** (artefactos dentro de la ventana, umbral `ARTIFACT_OK_MAX`): después del recálculo de HG-04, porque calibrarla antes sería hacerlo sobre una definición de ventana que va a cambiar.
5. **HG-08** al final: corregir el detector en origen. Solo afecta a grabaciones nuevas o rederivadas y necesita una validación más amplia que estos 5 días.

Pendiente, sin tarea propia: los gates de 06-26, 09-06 y 09-08 cambiaron en el replay por pequeñas diferencias de valor de días anteriores y márgenes estrechos de decisión. Conviene estudiar esa fragilidad por separado.

### Reproducción

Scripts en `research/experiments/hg06_replay/scripts/` y resultados acotados en `research/experiments/hg06_replay/results/` (fuera de Git). Los RR y las tablas completas de cada brazo viven solo en `$HOME/hg06_replay_work/`:

```
python extract_rr.py                         # RR originales de los 55 días, verificados por SHA-256
python flags_parity.py                       # offline = rango + delta-RR (0 discrepancias)
python run_arm.py <C|F1|F2|Cw|F1w|F2w> prepare|core|final|collect  # collect solo guarda SHA-256
python analyze.py                            # impact_summary.json, impact_days_*.csv, impact_series_*.csv
python compare_tables.py <a.csv> <b.csv>     # comparación por Fecha
```

`run_arm.py` trabaja en `$HOME/hg06_replay_work/<brazo>` (configurable con `HG06_REPLAY_WORK`), fija `HRV_DATA_DIR` a la copia y no escribe en `data/`. `extract_rr.py` y `flags_parity.py` leen los RR de ese mismo directorio. `collect` solo guarda hashes de salida; `analyze.py` publica únicamente las filas de FINAL que cambian y escribe `impact_summary.json` como UTF-8 para conservar tildes. Se verificó por hash que CORE, FINAL, BETA_AUDIT, DASHBOARD y `build_hrv_core.py` reales no cambiaron. Para F1w/F2w/Cw genera una copia `build_hrv_core_hg06_fixedlat.py` que añade `import json` y cuatro líneas antes de `t_start_eff = …` para imponer `lat` por fecha.

### Límites

- Regla A fija; otras variantes darían otros días.
- Solo era `from_jsonl`; Polar excluido.
- Código CORE actual: sin pareado HG-03 ni ventana fija HG-04.
- El replay mide consecuencias suponiendo que la fusión es correcta; no valida picos.

## Parte 2 — Qué está respondido de la pregunta de fondo

| Pregunta | Estado | Evidencia |
|---|---|---|
| ¿El convertidor reproduce su propio histórico? | **Sí** | 216/216 días, picos a ≤5 ms (HG-06) |
| ¿La captura pierde muestras? | **No, en los 55 días auditados** | PolarRecorder 2.0.6, sin huecos (HG-06) |
| ¿Por qué se descarta un RR? | **Resuelto en los 55 días**: rango o delta-RR; ACC no interviene | `flags_parity.json`, 0/23.394 discrepancias |
| ¿Hay un patrón repetido de RR anómalos? | **Sí** | 301 parejas en 55 días, mayoría de amplitud baja (HG-06) |
| ¿Altera el valor del RMSSD de los días que se usan? | **Poco** (≤3,6% con la misma ventana) | Este replay, F1w/F2w |
| ¿Altera la clasificación y el gate? | **Sí, en pocos días**, por cambios de `Calidad` y de valores cercanos al umbral | Este replay |
| ¿Es cada pico de una pareja A un latido o no? | **No respondido** | Prueba objetiva acotada no concluyente; no hay referencia de verdad |

Respuesta provisional a «¿calculamos bien el RR desde el ECG?»: donde se calcula el RMSSD, el resultado cambia poco con la regla A al mantener la latencia del control. La fusión hipotética afecta a la clasificación de algunos días y también a valores previos que mueven gates cercanos al umbral. El replay muestra inestabilidad del detector de estabilización actual, pero no valida el cambio propuesto en HG-04 ni demuestra que los picos intermedios sean falsos.
