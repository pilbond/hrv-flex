
## Objetivo

Mejorar la claridad e informacion didactica del campo `reason_text` en `FINAL.csv` y `DASHBOARD.csv`.

El campo es correcto funcionalmente: nunca afecta al gate, acumula contexto operativo y se construye por capas. El problema es de legibilidad: algunos mensajes contienen notacion interna, jerga fisiologica o valores numericos sin escala que el atleta no puede interpretar directamente.

Esta tarea no toca logica HRV, no toca esquemas, no toca gates. Solo mejora los strings literales de los mensajes emitidos en `build_hrv_final_dashboard.py`.

**No objetivo explicito:** no introducir hipotesis fisiologicas, medicas o causales nuevas que el codigo actual no infiere. El texto puede ser mas claro, no mas explicativo en terminos de causa.

---

## Alcance funcional

Archivo afectado: `build_hrv_final_dashboard.py`

Funciones afectadas:
- `_emit_reason()` — el parametro `message=` de cada llamada
- `_recovery_summary_message()` — cadenas retornadas (linea ~492)
- `_recovery_action_message()` — cadenas retornadas (linea ~532)

Salida: campo `reason_text` en `ENDURANCE_HRV_master_FINAL.csv` y `ENDURANCE_HRV_master_DASHBOARD.csv`

Sin cambios estructurales en:
- logica de gating ni semaforos
- esquema de columnas de ningun CSV
- `reason_items` (claves, tipos y metadatos no cambian; solo cambia el valor textual de `message` en los items emitidos)
- separador `" | "` entre fragmentos de `reason_text`
- orden de emision de los fragmentos
- ningun otro modulo del pipeline

---

## Diagnostico

### Grupo 1 — Notacion estadistica opaca

**Mensajes afectados:**
- `Noche corta (360min < P10=450)`
- `Noche fragmentada (8 interr > P90=5)`

`P10` y `P90` son notacion interna de percentiles. Un atleta lee "P10=450" y no sabe que significa. Las variables `sleep_dur_p10` y `sleep_int_p90` ya estan disponibles en el punto de emision; el cambio es solo de formato.

**Propuesta:**
```
Noche corta (6h vs tu umbral habitual bajo de 7h30)
Sueno fragmentado (8 interrupciones; tu umbral habitual alto son 5)
```
Convertir minutos a horas y reemplazar `P10`/`P90` por una descripcion de percentil en lenguaje natural, sin presentarlo como "minimo/maximo" literal.

---

### Grupo 2 — Unidades y escala (pendiente de fase posterior)

**Mensajes afectados:**
- `Carga acumulada alta (load_3d=1250)`
- `Z3 acumulado alto (z3_7d=120min)`

`load_3d` aparece como numero sin escala de referencia. Mostrar el percentil historico (P75) requeriria computarlo y pasarlo al punto de emision — logica nueva. Se deja anotado para una subtarea posterior.

El cambio de etiqueta de `Z3` si se puede hacer en esta fase:
```
Tiempo en alta intensidad acumulado esta semana (120min en Z3)
```

---

### Grupo 3 — Ventana temporal de clustering opaca

**Mensaje afectado:**
- `VERDE pero con 2 dias intensos en los ultimos 3: prudencia con la intensidad (2/3d · 4/5d)`

El sufijo `(2/3d · 4/5d)` es notacion interna. El cuerpo del mensaje ya expresa la informacion. El sufijo añade ruido.

**Propuesta:**
```
VERDE pero con 2 dias intensos en los ultimos 3 (y 4 en los ultimos 5): prudencia con la intensidad
```
Cuando ambas ventanas tienen datos, integrarlas en el cuerpo. Cuando solo hay una, eliminar el sufijo.

---

### Grupo 4 — Mensajes no accionables

**Mensajes afectados:**
- `ROJO sin carga previa ni sueno malo: revisar otros factores`
- `ROJO sin carga previa reciente: revisar otros factores`

"Revisar otros factores" no orienta al atleta. Si el sistema ya descarto carga y sueno, debe orientar sin introducir causas especificas que el codigo no infiere.

**Propuesta:**
```
ROJO sin carga previa ni sueno malo: revisar factores externos al entrenamiento
ROJO sin carga previa reciente: revisar factores externos al entrenamiento
```

**Criterio aplicado:** el texto orienta al atleta hacia donde mirar, pero no afirma causas concretas (enfermedad, estres, artefacto). Esas hipotesis no son inferibles por el sistema a partir de los datos disponibles; incluirlas seria sesgar el diagnostico mas alla del alcance del modelo.

---

### Grupo 5 — Terminologia fisiologica sin contexto

**Mensajes afectados:**
- `HRV excesivamente alto: posible saturacion parasimpatica`
- `ROJO, pero RMSSD nocturno alto (48ms): la senal nocturna sale mejor de lo esperado`
- `VERDE, pero RMSSD nocturno bajo (22ms)`

"Saturacion parasimpatica" es jerga que solo entiende alguien con formacion especifica. "RMSSD nocturno" tampoco es intuitivo sin contexto.

**Propuesta:**
```
HRV inusualmente alto: posible predominio parasimpatico fuera de tu rango habitual
ROJO, pero el HRV de sueno salio alto (48ms): la recuperacion nocturna fue mejor de lo esperado
VERDE, pero el HRV nocturno fue bajo (22ms): la recuperacion durante el sueno no acompana
```

**Criterio aplicado:** la hipotesis de "saturacion parasimpatica" se parafrasea en lenguaje mas claro pero sin sustituirla por hipotesis nuevas (artefacto, enfermedad, etc.). Los otros dos mensajes son de `_recovery_summary_message()` y usan RMSSD nocturno — se traduce al equivalente en lenguaje natural sin cambiar la inferencia.

---

### Grupo 6 — Caida aguda con valores internos en crudo

**Mensaje afectado:**
- `Caida aguda HRV: raw=2.980 vs base=3.451 (drop=-0.471, umbral=-0.387)`

`raw=2.980` son valores de `ln(rMSSD)` — unidades internas sin significado directo para el atleta. Lo que importa es cuanto cayo en relacion al margen habitual de variacion.

**Propuesta:**
```
Caida brusca de HRV: supero el umbral de caida aguda respecto a tu variacion habitual
```

**Criterio aplicado:** no mostrar `raw`, `base`, `drop` ni el umbral numerico cuando esos valores siguen estando en escala `lnRMSSD`. Si se quiere mantener detalle numerico, esa mejora tendria que expresarse en unidades mas interpretables o salir de esta tarea.

---

### Grupo 7 — Inconsistencia en mensajes de convergencia de carga

**Mensajes afectados:**
- `VERDE con convergencia de carga (load_3d + ACWR): precaucion intensidad reforzada` — sin valores
- `VERDE con carga acumulada (load_3d=1180): precaucion intensidad` — con valor
- `VERDE con contexto de carga exigente (ACWR): precaucion intensidad` — solo nombre, sin valor

Tres mensajes del mismo bloque con distinto nivel de detalle numerico.

**Propuesta:** uniformizar el nivel de detalle, pero sin forzar valores que hoy no estan disponibles en el mensaje agregado de convergencia.

Regla propuesta:
- si el mensaje cita un unico indicador y su valor ya esta disponible en scope, mostrarlo
- si el mensaje agrega varios indicadores (`load_3d` + `ACWR`/`monotonia`/`strain`), mantener un resumen tipado y no mezclar valores parciales que dejen el mensaje desequilibrado

Ejemplos validos:
```
VERDE con carga acumulada (load_3d=1250): precaucion con la intensidad
VERDE con contexto de carga exigente (ACWR): precaucion con la intensidad
VERDE con convergencia de carga (load_3d + ACWR): precaucion con la intensidad reforzada
```

**Motivo:** en el codigo actual el bloque de convergencia agrega nombres de fuentes desde `load_ctx_caution_sources`, no una estructura homogénea de pares `indicador=valor` en el punto de renderizado final. Forzar valores en ese mensaje ya roza cambio de logica/presentacion compuesta.

---

### Grupo 8 — Action message indistinguible del diagnostico

**Mensajes afectados:**
- `contener la intensidad`
- `Z2 controlado es razonable si sensaciones normales`
- `mejor sesgo conservador hoy`
- `revisar factores externos`
- `suave o descanso`

Aparecen como un fragmento mas del pipe, al mismo nivel visual que los diagnosticos. Un lector que lee:
```
Noche corta (6h) | Carga alta | VERDE, pero... | contener la intensidad
```
puede no distinguir que el ultimo item es una recomendacion y no un diagnostico.

**Propuesta:** prefijo fijo en el action message usando ASCII para maxima compatibilidad con CSV y consolas:
```
Accion: contener la intensidad
Accion: Z2 controlado es razonable si sensaciones normales
Accion: suave o descanso
```

**Impacto downstream observado:** `analysis/session_analysis_pipeline.py` lee `reason_text` pero no lo parsea; solo lo reexpone en el payload diario. El cambio de prefijo es, por tanto, de bajo riesgo en `analysis`. Aun asi, si aparece algun consumidor adicional que haga parsing textual, debe actualizarse en el mismo commit.

---

## Ejecucion

### Precondicion

Identificar en `tests/test_build_hrv_final_dashboard_contract.py` todos los `assertIn` sobre strings literales de `reason_text`. Los que se han identificado:

| linea | string literal afectado |
|---|---|
| 260 | `"ROJO sin carga previa reciente: revisar otros factores"` |
| 292 | `"ROJO sin carga previa ni sueno malo: revisar otros factores"` |
| 318 | `"VERDE con carga acumulada (load_3d=210): precaucion intensidad"` |
| 361 | `"VERDE pero con 2 dias intensos en los ultimos 3: prudencia con la intensidad (2/3d · 3/5d)"` |
| 409 | `"AMBAR con senales nocturnas favorables"` |
| 456 | `"ROJO, pero RMSSD nocturno alto (50ms): la senal nocturna sale mejor de lo esperado"` |
| 459 | `"ROJO, pero sueno y carga reciente no encajan con un rojo claro"` |

Ademas, hay al menos un fixture literal afectado en `tests/test_cli_reporting_contract.py`:

| linea | string literal afectado |
|---|---|
| 34 | `"VERDE con carga acumulada (load_3d=210): precaucion intensidad"` |

**Estos asserts y fixtures se actualizan en el mismo commit** que los strings de produccion. No es una precondicion a resolver antes; es trabajo incluido en cada fase.

**Nota de lectura:** la tabla resume strings en formato normalizado para documentacion (sin depender de tildes o escapes tipograficos). El string exacto a actualizar en cada caso es siempre el del propio test o fixture fuente.

Verificar tambien si algun documento de `docs/contracts/` cita ejemplos literales de `reason_text` y actualizarlos si los hay.

### Fase 1 — Cambios de texto puro

Grupos 3, 4, 5, 6 y parte de 7. Todos son cambios de string literal donde las variables necesarias ya estan disponibles en el punto de emision.

Un unico commit. Solo `build_hrv_final_dashboard.py`:
- parametro `message=` en llamadas a `_emit_reason()`
- cadenas retornadas por `_recovery_summary_message()` y `_recovery_action_message()`
- asserts literales afectados en `tests/test_build_hrv_final_dashboard_contract.py`
- fixture literal afectado en `tests/test_cli_reporting_contract.py`

Sin tocar logica, sin tocar esquemas, sin tocar separador `|` ni orden de emision.

### Fase 2 — Formato con datos ya disponibles en scope

Grupos 1 y la parte de 2 que no requiere logica nueva (etiqueta de Z3).
Las variables `sleep_dur_p10` y `sleep_int_p90` ya existen cuando se emite el mensaje.
Puede ir en el mismo commit que la Fase 1 o en uno separado si se prefiere revision independiente.

### Fase 3 — Cambio estructural del action message

Grupo 8. El analisis de impacto downstream ya esta resuelto (ver Grupo 8 en Diagnostico):
`analysis/session_analysis_pipeline.py` solo reexpone `reason_text`, no lo parsea.

El commit puede ejecutarse limpiamente sobre `build_hrv_final_dashboard.py`, en la funcion `_recovery_action_message()`, sin actualizar consumidores adicionales.

Si antes de ejecutar aparece cualquier otro consumidor que haga parsing textual de `reason_text`, debe actualizarse en el mismo commit.

### Fuera de alcance de esta tarea

- Grupo 2 completo (escala de `load_3d` con percentil historico): requiere computar P75 en runtime y pasarlo al punto de emision. Se deja anotado para una subtarea posterior.
- Cualquier cambio estructural en `reason_items` (claves, tipos o metadatos emitidos por `_emit_reason()`).
- Cualquier cambio en la logica de gating.
- Cualquier cambio en el separador `" | "` o en el orden de emision de fragmentos.

---

## Gate de regresion

- `py_compile` sobre `build_hrv_final_dashboard.py`
- `pytest tests/test_build_hrv_final_dashboard_contract.py` — debe pasar con los asserts actualizados
- `pytest tests/test_cli_reporting_contract.py` — debe pasar con el fixture actualizado
- `pytest tests/` completo
- smoke manual: ejecutar el pipeline sobre datos reales y leer `reason_text` en el CSV de salida

---

## Criterios de aceptacion

1. Ningun mensaje del `reason_text` contiene notacion estadistica cruda (`P10`, `P90`) sin traduccion a lenguaje natural.
2. Los valores internos en escala `ln(rMSSD)` no aparecen en crudo en el mensaje de caida aguda.
3. El sufijo de ventana de clustering es legible o esta integrado en el cuerpo del mensaje.
4. Los mensajes de ROJO sin contexto orientan al atleta hacia donde mirar sin afirmar causas concretas que el sistema no infiere.
5. Los mensajes de convergencia de carga son consistentes en cuanto al nivel de detalle y no fuerzan valores parciales que hoy no estan disponibles en el renderizado agregado.
6. La suite completa de tests sigue verde.
7. El campo `reason_text` sigue siendo solo contexto: no afecta al gate ni al semaforo.
8. El separador `" | "` entre fragmentos de `reason_text` no cambia.
9. El orden de emision de los fragmentos no cambia.
10. Ningun mensaje nuevo contiene hipotesis fisiologicas, medicas o causales que el codigo actual no infiere.
