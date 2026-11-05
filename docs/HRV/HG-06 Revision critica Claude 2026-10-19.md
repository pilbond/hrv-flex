# Revisión crítica de HG-06 (HG-05A): diagnóstico y referencia ECG

Fecha: 2026-10-19. Autor: Claude, a petición de Francisco, revisando [el documento principal de HG-06](<HG-06 Diagnostico y referencia ECG.md>), la tarjeta HG-06 de `Project.canvas`, el [informe técnico](../../research/reports/hg06_reference_2026-10-18.md), varios scripts de `research/experiments/hg05/scripts/` y las tablas de `research/experiments/hg05/results/`. Incluye cruces recalculados contra CORE y FINAL.

## Veredicto

La parte computacional es sólida: hay trazabilidad, se verifican las huellas y los límites están declarados con honestidad. Pero hay **un error factual que se repite**, **una revisión "ciega" que en realidad no lo es**, y un problema de fondo: **la tarea no tiene criterio de cierre y persigue una pregunta que la decisión siguiente (HG-07) no necesita responder del todo**.

## Lo que está bien

| Afirmación | Seguridad |
|---|---|
| Los picos archivados se reproducen a ≤5 ms en 216/216 días (solo el 15 de abril tiene picos extra). Es el hallazgo más útil: el detector es determinista y rederivar en HG-08 es viable. | 90% (no recalculado desde el raw) |
| Las cifras de supervivencia y de puentes del documento coinciden con los JSON y CSV de resultados (291/7/3, 66 diferencias, 1,37 ms / 2,56%). | 95% |
| El sidecar `_rr_diagnostics/*_RR_reasons.csv` no lo recogen los lectores RR. CORE usa un `glob("*_RR.csv")` no recursivo y `scan_rr_files_by_date` filtra por `endswith("_RR.CSV")`. | 90% |
| La crítica a Sci-Bot es correcta: el H10 graba a 130 Hz, no a 1000, y con los RR1 de 453–1352 ms la regla de latencia T no puede cumplirse. | 90% |
| La auditoría de captura (PolarRecorder 2.0.6, sin huecos en 3,69 M muestras) descarta pérdida visible de muestras en esos 55 días. | 80% |

## Errores

### 1. Se da por hecho que `Artifact_pct >10%` equivale a `INVALID`. Es falso.

En `build_hrv_core.py:84` el umbral es `ARTIFACT_OK_MAX = 15.0`. De los 18 días con más del 10%:

| Calidad | Días |
|---|---|
| `INVALID` | 10 |
| `FLAG_mecánico` | 3 (06-10, 06-15, 07-12) |
| `OK` | 5 (03-21, 04-15, 04-20, 04-27, 05-19) |

~~Además, los días `FLAG_mecánico` sí entran en el baseline: solo se excluye `INVALID` (`build_hrv_core.py:457,510`).~~ **Corrección (2026-10-19, replay HG-06):** esa afirmación era errónea para el gate. En FINAL, baseline60, roll3 y SWC usan solo `Calidad == OK` (`build_hrv_final_dashboard.py:972`); las líneas citadas de CORE son su historia interna, no el baseline del gate. Un día `FLAG_mecánico` recibe gate pero no alimenta baselines.

**Consecuencia concreta.** El documento principal y el informe técnico (l. 336) dicen que de los 35 picos débiles con ambos RR limpios, "34 están en días >10% ya `INVALID`". Uno de ellos está en **2026-04-15, que es `OK`**: índice 88, razón de amplitud 0,542, `offline` 0/0. Con `t_start_eff = 60 s` y RR de unos 1,17 s, ese pico cae hacia los ~100 s, **dentro del tramo de RMSSD**.

- Seguridad en el error de redacción: 95%.
- Seguridad en que ese pico está dentro del tramo: 85% (estimado por índice, no por el tiempo exacto).
- Que el impacto sea pequeño es probable (70%): si ambos RR pasaron el filtro delta del 20%, el pico está a distancia normal y seguramente es un latido real de baja amplitud. Pero hay que comprobarlo, no darlo por cubierto.

La conclusión de supervivencia de las parejas A sí se sostiene: los 5 días donde aportan RR son `INVALID` de verdad. Solo es errónea la equivalencia escrita entre paréntesis.

### 2. La revisión ciega de 40 extractos no era ciega

En `hg06_blind_ecg_sample.py:78-79` se dibujan los marcadores de los picos anterior, central y posterior en una ventana de ±1,1 s:

- En las candidatas, los dos vecinos caen a ~0,45–0,75 s. Se ha comprobado que en 19 de 20 ambos marcadores quedan dentro de la ventana.
- En los controles, los vecinos están a ~1 RR mediano (~1,1–1,3 s), es decir, fuera o al borde.

**La figura revela el grupo**, así que la separación 16/20 frente a 17/20 está inflada. Seguridad: 90%.

En la revisión de 48 parejas débiles pasa lo mismo: el docstring dice "no RR pattern shown", pero los marcadores muestran el espaciado. Ahí el resultado fue negativo y la fuga no lo infla. Seguridad en que también hay fuga: 60%.

**Mejora:** un único marcador central, ventana fija de ±0,4 s y sin marcadores vecinos. También conviene recordar que el revisor es el mismo que formuló la hipótesis.

## Problemas metodológicos

### 3. No hay criterio de cierre (85%)

El título promete una "referencia ECG" que no se ha construido. A cambio hay unas 20 auditorías con proxies, y cada una termina en "no prueba". Los cuatro pendientes son abiertos ("ampliar", "investigar discrepancias"), así que la tarea no puede cerrarse así.

**Propuesta:** fijar ahora un conjunto de adjudicación cerrado, por ejemplo 100 candidatas y 100 controles estratificados con el formato ciego corregido. Definir de antemano la regla de decisión, por ejemplo: si la proporción `no_qrs` tiene un IC95 inferior a X%, HG-07 avanza.

### 4. La pregunta "¿pico verdadero o falso?" no es la que necesita HG-07 (75%)

Hay un diagnóstico diferencial que el documento no menciona: la **extrasístole ventricular interpolada**. Es típica de frecuencias bajas como las tuyas y encaja con lo observado:

- La suma de la pareja es ≈1 RR sinusal; la mediana 1,023 incluso es compatible con la ligera prolongación por conducción oculta.
- Un QRS ancho tiene poca energía en 8–30 Hz, lo que daría una razón de amplitud baja.
- Saldría etiquetado "sin deflexión estrecha".

Esto es especulación fisiológica: no hay evidencia de que ocurra en estos registros. Pero importa por una razón: **en los dos casos, artefacto o interpolada, la acción correcta para el NN es la misma, sumar la pareja**. Por tanto, la adjudicación pico a pico solo es necesaria para HG-08 (corregir en origen y, si interesa, contar ectopia), no para decidir HG-07.

Además, el agnosticismo es excesivo. Coinciden varias pruebas independientes:

- suma ≈ mediana, sin pausa compensatoria;
- posición mesodiastólica;
- amplitud 0,15–0,57 frente a ~1 en los QRS vecinos;
- concentración en días degradados;
- captura íntegra (sin huecos de muestreo).

Un PAC real tendría un QRS normal (razón ~1). La mayoría de las candidatas débiles probablemente no son latidos sinusales (85%). Lo que sigue abierto es si son ruido o ectopia.

### 5. Falta traducir el efecto a la escala de decisión (90%)

1,37 ms equivale a Δln ≈ −0,026, que son **~27% del `SWC_ln`** (0,096) del 2026-09-11. Ese día `d_ln = +0,105` (VERDE+++) y `lnRMSSD_used` diluye el efecto, así que es improbable que cambie el gate (80%). Pero en días cerca del umbral, un 27% del SWC sí puede cambiarlo.

Hay además un contrafactual barato que no se ha calculado: **sustituir cada pareja A por su suma y recalcular con adyacencia correcta (HG-03)**. Omitir los puentes, como se hace ahora, no equivale a corregirlos. Este replay, hecho en los 55 días y midiendo la distancia a umbral, responde directamente cuánto vale HG-07.

### 6. Esfuerzo con poco rendimiento

- **Muestra de 20 fechas:** quedó superada por el barrido completo de 216 días. Habría que marcarla como etapa intermedia (70%).
- **XQRS:** se ejecutó a 130 Hz sin remuestrear, aunque está pensado para ~250–360 Hz. Que encuentre un solo pico en 4 días apunta más a configuración que a la señal (60%). Si se mantiene, conviene remuestrear y comprobar la polaridad; si no, retirarlo como comparador.

### 7. Forma del documento (95% en los hechos, el resto es opinión)

Faltan el título H1 y la respuesta a la pregunta principal al inicio. Ocupa 30 KB y funciona como cuaderno de laboratorio. Debería abrir con algo así:

> "Sí hay un patrón repetido: 301 parejas en 55 días, el 75% de amplitud <0,6, concentrado en días degradados. El impacto directo en días `OK` está acotado (≤2,6%, ~0,27 SWC en el peor caso). El valor principal es recuperar datos en días `INVALID`/`FLAG`."

## Cambios mínimos propuestos, por orden

1. Corregir la equivalencia ">10% = `INVALID`" en el documento principal (líneas de supervivencia y del censo) y en el informe técnico (l. 212 y 336). Verificar el pico de índice 88 del 2026-04-15 contra el tramo estabilizado.
2. Marcar la revisión ciega de 40 extractos como **no ciega** y no usarla como evidencia de separación.
3. Añadir el H1, un resumen con la respuesta y el criterio de cierre.
4. Hacer el replay por suma en los 55 días, con el delta en `lnRMSSD_used` frente a `SWC_ln` y los cambios de gate. Con esto se decide HG-07.
5. Añadir la interpolada como diferencial, sin afirmarla.

## Lo que no se ha verificado en esta revisión

- No se ha recalculado nada desde el ECG/RR raw, solo la coherencia entre documento, tablas y CORE.
- No se han ejecutado los 13 tests de contrato: el entorno remoto no tiene `pytest` instalado.
- Del informe técnico de 401 líneas solo se han leído las secciones relevantes, no entero.

Antes de dar el veredicto se ha comprobado si alguna conclusión dependía del error de `INVALID`: la de supervivencia de las parejas A no depende; la del censo de picos débiles sí.
