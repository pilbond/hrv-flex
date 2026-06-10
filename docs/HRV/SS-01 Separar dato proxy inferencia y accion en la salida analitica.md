
## Objetivo
Separar explicitamente en la salida del sistema cuatro capas semanticas que hoy aparecen mezcladas en `FINAL` y `DASHBOARD`:

- dato medido
- proxy o derivado
- inferencia o clasificacion
- accion operativa

El objetivo no es cambiar el gate HRV, sino mejorar trazabilidad, auditabilidad y consumo coherente desde pipeline, UI y modulo `analysis/`.

## Diagnostico actual
La salida diaria actual de [build_hrv_final_dashboard.py](/C:/Pilbond/polar-hrv-automation/build_hrv_final_dashboard.py#L99) mezcla en una sola tabla:

- datos medidos como `HR_today`, `RMSSD_stable`, `lnRMSSD_today`
- proxies como `ln_base60`, `SWC_ln`, `d_ln`, `residual_z`
- inferencias como `gate_final`, `gate_badge`, `baseline60_degraded`
- acciones como `Action`, `Action_detail` y `reason_text`

Esto funciona operativamente, pero genera tres problemas:

1. dificulta saber que parte de una conclusion es medida y que parte es heuristica;
2. obliga a `analysis/` a reinterpretar salidas planas que ya vienen semantizadas de forma implícita;
3. hace crecer `reason_text` como contenedor mixto de evidencia, inferencia y recomendacion.

## Valor esperado
Implementar `SS-01` aportaria una mejora estructural clara:

- mayor trazabilidad del origen de cada recomendacion diaria;
- menor ambiguedad entre numero observado, proxy calculado y decision operativa;
- mejor consumo desde UI y `analysis/`;
- base semantica mas limpia para tareas como `CDC-01`, `DO-01`, `AP-01`, `RE-01/02`, `FP-01` y `ADC-01`.

La mejora principal no es fisiologica ni de precision del gate. Es una mejora de contrato y arquitectura de salida.

## Diferencia frente al proyecto original
El proyecto `intervalsicugptcoach-public` ya separa mejor el significado de cada metrica en [semantic_json_builder.py](/C:/Pilbond/Endurance%20External%20Projects/intervalsicugptcoach-public/semantic_json_builder.py#L190), donde cada bloque incluye:

- valor
- formula
- thresholds o criteria
- classification
- metric_confidence
- interpretation
- coaching_implication

No conviene copiar ese builder entero. Si conviene trasladar la idea de fondo: una salida que no entregue solo columnas, sino tambien rol semantico y confianza.

## Propuesta de implementacion

### Fase 1. Separacion semantica interna
Refactorizar [build_hrv_final_dashboard.py](/C:/Pilbond/polar-hrv-automation/build_hrv_final_dashboard.py) para construir bloques internos separados:

- `measured_block`
- `proxy_block`
- `inference_block`
- `action_block`
- `reason_items`

Aunque `FINAL` siga siendo CSV plano, la construccion dejaria de estar mezclada.

### Fase 2. Sidecar semantico compatible
Generar una salida adicional, por ejemplo:

- `ENDURANCE_HRV_master_SEMANTIC.jsonl`

Unidad recomendada: un objeto por fecha.

Estructura minima sugerida:

```json
{
  "Fecha": "2026-04-03",
  "measured": {
    "HR_today": 52,
    "RMSSD_stable": 41.2,
    "lnRMSSD_today": 3.72
  },
  "proxy": {
    "ln_base60": 3.81,
    "SWC_ln": 0.07,
    "load_3d": 268
  },
  "inference": {
    "gate_final": "AMBAR",
    "gate_reason": "2D_LN",
    "quality_flag": false,
    "confidence": "high"
  },
  "action": {
    "label": "Z2_O_TEMPO_SUAVE",
    "detail": "SIN_HIIT"
  },
  "reasons": [
    {
      "type": "load_context",
      "layer": "proxy",
      "source": "sessions_day",
      "message": "Carga acumulada alta"
    }
  ]
}
```

### Fase 3. Render controlado de `reason_text`
Hacer que `reason_text` sea un render corto derivado de `reason_items`, no el origen semantico principal.

Eso mantiene compatibilidad con:

- [ENDURANCE_HRV_master_FINAL.csv](/C:/Pilbond/polar-hrv-automation/data/ENDURANCE_HRV_master_FINAL.csv)
- [ENDURANCE_HRV_master_DASHBOARD.csv](/C:/Pilbond/polar-hrv-automation/data/ENDURANCE_HRV_master_DASHBOARD.csv)

sin perder estructura.

## Reglas recomendadas

### Dato medido
Solo deben entrar aqui valores observados o casi crudos:

- HR matinal
- RMSSD estable
- artefactos
- tiempo de estabilizacion
- sueno observado

### Proxy
Aqui viven calculos operativos:

- baselines
- SWC
- residuales
- rolling load
- ACWR, monotony o strain si se implementan
- NDLI proxy o durability proxy cuando existan

### Inferencia
Aqui viven clasificaciones o lectura semantica:

- gate final
- badge
- confidence
- warning classes
- estado de recuperacion o contexto de carga

### Accion
Aqui viven recomendaciones:

- `Action`
- `Action_detail`
- restricciones o sugerencias de sesion

## Integracion con analysis
`analysis/` ya exige separar dato, inferencia y certeza en [analysis/AGENTS.md](/C:/Pilbond/polar-hrv-automation/analysis/AGENTS.md#L229). Por tanto, la direccion correcta es:

1. el pipeline global produce una salida semantica mas limpia;
2. `analysis/` la consume y la amplifica;
3. no dejar que cada informe semanal o de sesion reconstruya esto ad hoc.

## Riesgos a evitar

- no romper `FINAL` ni `DASHBOARD` en v1;
- no copiar toda la complejidad del proyecto original;
- no confundir `proxy` con `medida`;
- no dejar `reason_text` como unico soporte de interpretacion.

## Recomendacion final
Implementar `SS-01` como una mejora incremental:

1. separar internamente capas semanticas en `build_hrv_final_dashboard.py`;
2. mantener los CSV actuales por compatibilidad;
3. anadir un sidecar semantico diario ligero;
4. usar esa capa para renderizar `reason_text` y facilitar el consumo desde `analysis/` y futuras mejoras.

## Version 2 - Enfoque reducido y realista

Nota:

- esta v2 se conserva como historial de iteracion;
- si hay conflicto entre v2 y v3, manda la v3;
- la sugerencia v2 de exponer `reason_items_json` en `FINAL` queda supersedida por la v3.

Tras revisar criticamente la propuesta original, la conclusion mas util es que `SS-01` no debe abordarse como una gran refactorizacion semantica de 3 fases. El problema existe, pero el consumidor real de un `SEMANTIC.jsonl` rico no existe hoy:

- la UI usa `DASHBOARD.csv`;
- `analysis/` ya sabe separar internamente dato, inferencia y certeza;
- el usuario no consume un sidecar JSON diario.

Por tanto, la parte con valor real y proporcionado es mucho mas pequena.

### Objetivo v2
Reducir `SS-01` a una mejora quirurgica:

- dejar de usar `reason_text` como origen semantico primario;
- tipar internamente los motivos como `reason_items`;
- seguir renderizando `reason_text` para compatibilidad.

### Alcance recomendado v2

1. Cambiar `reason_parts: list[str]` por `reason_items: list[dict]` en [build_hrv_final_dashboard.py](/C:/Pilbond/polar-hrv-automation/build_hrv_final_dashboard.py#L643).
2. Mantener `reason_text` como string pipe-separated derivado de esos items.
3. Historico: se considero anadir `reason_items_json` en `FINAL`, pero la v3 lo descarta para v1 si no existe consumidor real.
4. No crear en v1 un `SEMANTIC.jsonl` completo ni un sidecar semantico rico por fecha.
5. No introducir todavia un campo global `confidence` si no existe criterio explicito y estable para calcularlo.

### Estructura minima sugerida para cada item

```json
{
  "type": "load_context",
  "layer": "proxy",
  "source": "sessions_day",
  "message": "Carga acumulada alta (load_3d=268)"
}
```

Ejemplo de restriccion operativa:

```json
{
  "type": "action_constraint",
  "layer": "action",
  "source": "gate_final",
  "message": "SIN_HIIT"
}
```

### Valores cerrados de `layer`
Para evitar deriva semantica, `layer` debe limitarse en v1 a estos cuatro valores:

- `measured`
- `proxy`
- `inference`
- `action`

No usar en v1 variantes como `context`, `warning`, `status` o similares.

### Catalogo inicial recomendado de `type`
Conviene arrancar con un catalogo pequeno y explicito basado en los motivos que ya existen hoy en `build_hrv_final_dashboard.py`.

Tipos iniciales recomendados:

- `acute_drop`
- `parasympathetic_saturation`
- `data_quality`
- `sleep_duration`
- `sleep_fragmentation`
- `nightly_discordance`
- `load_accumulation`
- `volume_weekly`
- `z3_accumulation`
- `contradiction`
- `caution`

Mapa orientativo con motivos actuales:

| type | Ejemplo actual |
|---|---|
| `acute_drop` | `Caida aguda HRV: raw=... vs base=...` |
| `parasympathetic_saturation` | `HRV excesivamente alto: posible saturacion...` |
| `data_quality` | `Dato dudoso: limitar a Z1-Z2 max 90min` |
| `sleep_duration` | `Noche corta (XXmin < P10=YYmin)` |
| `sleep_fragmentation` | `Noche fragmentada (XX interr > P90=YY)` |
| `nightly_discordance` | `VERDE pero nightly_rmssd bajo (XXms)` |
| `load_accumulation` | `Carga acumulada alta (load_3d=XXX)` |
| `volume_weekly` | `Volumen semanal alto (work_7d=XXXmin)` |
| `z3_accumulation` | `Z3 acumulado alto (z3_7d=XXmin)` |
| `contradiction` | `ROJO sin carga previa ni sueno malo...` |
| `caution` | `VERDE con carga acumulada: precaucion...` |

Este catalogo no impide anadir tipos nuevos despues, pero obliga a que el crecimiento sea deliberado y no ad hoc.

### Valor real de la v2

- evita seguir anadiendo contexto nuevo como strings opacos;
- facilita que tareas como `CDC-01`, `AP-01`, `RE-01` o `RE-02` anadan motivos estructurados sin rehacer la arquitectura;
- conserva `DASHBOARD` tal como lo consume hoy el sistema; la extension publica de `FINAL` queda pospuesta en la v3 hasta que exista consumidor real;
- captura gran parte del valor semantico con una fraccion pequena del esfuerzo.

### Que se descarta en v2

- refactor amplio por bloques si no mejora outputs reales;
- sidecar `SEMANTIC.jsonl` rico por fecha;
- clon parcial del `semantic_json_builder.py` del proyecto original;
- venta de `SS-01` como prerequisito duro para el resto de tareas.

### Recomendacion final actualizada
La forma realista de implementar `SS-01` es tratarla como una tarea de semantizacion minima del contexto:

1. tipar `reason_items`;
2. seguir renderizando `reason_text`;
3. exponer estructura solo si aporta un consumidor concreto;
4. dejar una puerta abierta a una semantica mas rica mas adelante, si el sistema realmente la necesita.

## Version 3 - Contrato operativo recomendado

Esta version 3 sustituye a la v2 como recomendacion vigente para implementar `SS-01`.

Regla de precedencia dentro de este documento:

- si algun bloque anterior de v1/v2 contradice esta v3, prevalece la v3.

La conclusion se mantiene:

- `SS-01` si tiene sentido;
- no debe entrar aun como ampliacion publica de `FINAL` por defecto;
- su valor real hoy esta en estructurar internamente los emisores de `reason_text`.

La diferencia frente a v2 es que esta v3 cierra los puntos que quedaban ambiguos:

- frontera con `training_audit` / `interpretability_limits`,
- regla formal para asignar `layer`,
- estrategia para no mantener un catalogo obsoleto de `type`,
- consumidor y rollout,
- contrato minimo de testing.

### Decision de alcance

`SS-01` se divide en dos niveles:

#### Nivel A - obligatorio para considerar la tarea util

- reemplazar la construccion ad hoc de `reason_parts: list[str]` por emisores estructurados;
- mantener `reason_text` como render final para compatibilidad;
- no cambiar todavia el esquema publico de `FINAL` ni `DASHBOARD`.

#### Nivel B - opcional y solo si aparece consumidor real

- exponer `reason_items_json` en `FINAL`, o
- exponer un sidecar semantico adicional.

Regla:

- si `analysis/` y la UI no lo consumen, el Nivel B no se hace en v1 de `SS-01`.

### Regla de serializacion

En Nivel A:

- `reason_items` vive solo en memoria dentro de `build_hrv_final_dashboard.py`;
- `reason_text` se renderiza desde esa estructura en memoria;
- no se serializa a JSON ni se anade a `FINAL`.

En Nivel B:

- la serializacion publica solo se activa si ya existe consumidor real.

## Objetivo v3

Definir una unidad semantica minima y estable llamada `reason_item` para representar cada motivo que hoy termina renderizado dentro de `reason_text`.

`reason_item` no sustituye:

- las columnas canonicas de `FINAL`,
- `training_audit`,
- `gate_final`,
- `Action`.

`reason_item` solo sustituye el origen opaco de `reason_text`.

## No objetivos explicitos

Esta v3 no pretende:

- crear un segundo decisor paralelo al gate,
- introducir una capa global de `confidence` sin criterio estable,
- mover toda la semantica diaria a JSON externo,
- duplicar `training_audit`,
- convertir `reason_text` en un informe largo,
- romper el contrato de 66 columnas de `FINAL` sin consumidor real.

## Unidad semantica propuesta

### `reason_item`

Estructura minima recomendada:

```json
{
  "type": "acwr",
  "layer": "inference",
  "source": "sessions_day",
  "message": "ACWR muy alto: carga aguda muy por encima de la base cronica (1.69)"
}
```

Campos obligatorios:

- `type`
- `layer`
- `source`
- `message`

Campos opcionales recomendados:

- `variant`
- `severity`
- `metric`
- `value`
- `threshold`
- `gate_scope`
- `codes`
- `evidence`

Ejemplo con evidencia separada:

```json
{
  "type": "load_3d",
  "layer": "inference",
  "source": "sessions_day",
  "variant": "high",
  "metric": "load_3d",
  "value": 268,
  "threshold": 250,
  "message": "Carga acumulada alta (load_3d=268)"
}
```

## Regla formal para `layer`

El `layer` clasifica la afirmacion semantica del item, no el numero aislado que aparece en el mensaje.

Valores permitidos:

- `measured`
- `proxy`
- `inference`
- `action`

### Regla operativa por capa

#### `measured`

Solo para afirmaciones literalmente observadas, sin umbral ni lectura interpretativa.

Ejemplos validos:

- `Sueno observado 330 min`
- `nightly_rmssd observado 24 ms`

#### `proxy`

Para metricas derivadas o agregadas que siguen siendo calculo operativo, no lectura.

Ejemplos validos:

- `load_3d=268`
- `acwr_simple_prev=1.69`
- `strain_7d_prev=899`

#### `inference`

Para cualquier frase que ya hace una lectura, clasificacion o cruce de umbral.

Ejemplos:

- `Carga acumulada alta`
- `ACWR muy alto`
- `Monotonia elevada`
- `VERDE con recuperacion fragil`
- `ROJO con discordancia objetiva`

#### `action`

Para restricciones o sugerencias operativas.

Ejemplos:

- `contener la intensidad`
- `considera Z1 manana`
- `mejor sesgo conservador hoy`

### Regla critica para casos mixtos

Cuando una frase mezcle evidencia numerica y lectura:

- el `layer` se asigna por la lectura principal de la frase,
- la evidencia numerica va en `metric/value/threshold/evidence`,
- no se intenta clasificar la frase completa como `proxy` solo porque incluya un numero.

Por tanto:

- `Carga acumulada alta (load_3d=268)` -> `layer = inference`
- con `metric = load_3d`, `value = 268`, `threshold = 250`

Esta regla elimina la ambiguedad que dejaba la v2.

## Frontera con `training_audit`

La coexistencia con `interpretability_limits` debe quedar explicita.

### `training_audit` sigue siendo la autoridad para:

- calidad e interpretabilidad del dataset de sesiones,
- cobertura real de streams,
- uso de fallback,
- fiabilidad de carga, drift y zonas,
- degradacion de confianza del analisis de sesiones.

### `reason_items` solo cubre:

- explicacion contextual diaria del HRV,
- tensiones gate-contexto,
- motivos operativos que hoy se renderizan en `reason_text`.

### Regla de no duplicacion

`reason_items` no debe crear items tipo:

- `partial_aerobic_stream_coverage`
- `zones_fallback_present`
- `stream_sampling_not_1hz`
- `load_context_not_ready`

salvo que se quieran renderizar explicitamente como contexto diario del HRV, y aun asi deberian venir referenciados desde `training_audit`, no redefinidos.

Decision v3:

- `interpretability_limits` no se migra a `reason_items`;
- `reason_items` puede enlazar a esos limites via `codes` o `evidence`, pero no los reemplaza.

## Estrategia para `type`

La v2 fallaba por proponer un catalogo cerrado escrito a mano en el doc.

La v3 fija otra regla:

- el catalogo normativo de `type` no vive en este markdown;
- vive en los emisores reales del codigo;
- la documentacion solo puede incluir snapshots orientativos.

### Regla de implementacion

Cada motivo debe emitirse por una unica funcion helper, por ejemplo:

```python
emit_reason(
    items,
    type="acwr",
    layer="inference",
    source="sessions_day",
    variant="high",
    severity="high",
    metric="acwr_simple_prev",
    value=1.69,
    threshold=1.30,
    message="ACWR alto: carga aguda por encima de la base cronica (1.69)",
)
```

Prohibicion recomendada:

- no se permite `reason_parts[i].append(...)` directo fuera del helper.

### Enforcement minimo recomendado

La prohibicion anterior no debe quedar como norma blanda.

Debe existir al menos un test sentinel que falle si reaparece algun:

- `reason_parts[i].append(...)`, o
- equivalente directo fuera del helper oficial.

Regla:

- `emit_reason(...)` debe ser la unica puerta de entrada normal para crear motivos estructurados.

### Consecuencia

El catalogo actual de emisores puede regenerarse leyendo:

- las llamadas al helper, o
- una registry derivada de esas llamadas en el mismo modulo.

No se vuelve a mantener una lista "de memoria" en el documento.

## Estrategia para `type`, `variant` y `severity`

Para no hacer explosion de tipos:

- `type` describe la familia semantica estable,
- `variant` describe subtipo o direccion,
- `severity` describe intensidad cuando aplique.

### Regla de minimizacion

`severity` no forma parte del contrato minimo obligatorio de v1.

Si no aporta una distincion material, se omite.

Si se usa, debe cerrarse al enum:

- `low`
- `medium`
- `high`
- `very_high`

Ejemplos:

- `type = acwr`, `variant = high`, `severity = high`
- `type = acwr`, `variant = low`
- `type = strain`, `variant = high`, `severity = very_high`
- `type = intensity_clustering`, `variant = recent`, `severity = low|high`
- `type = recovery_support`, `variant = fragile|supported|conflicted`

Esto permite absorber:

- `recovery_discordance`,
- `acwr_high`,
- `monotony_high`,
- `strain_high`,
- `clustering_high`,
- futura senal de `intensity_distribution`

sin multiplicar `type` innecesariamente.

## Snapshot orientativo del catalogo actual

Este bloque no es normativo; solo refleja las familias semanticas que hoy se observan en `build_hrv_final_dashboard.py`.

Familias actuales que la v3 deberia cubrir:

- `acute_drop`
- `parasympathetic_saturation`
- `data_quality`
- `sleep_duration`
- `sleep_fragmentation`
- `nightly_rmssd_discordance`
- `load_3d`
- `work_7d`
- `z3_7d`
- `recent_load_absence`
- `acwr`
- `monotony`
- `strain`
- `intensity_clustering`
- `green_load_caution`
- `green_load_convergence`
- `recovery_support`

Posible familia futura ya prevista:

- `intensity_distribution`

Regla:

- el snapshot puede quedarse viejo;
- la implementacion y los tests deben leer el registro real de emisores, no este listado.

## Consumidor declarado

La v2 dejaba sin responder quien consumiria la estructura.

La v3 lo fija asi:

### Consumidor real hoy

- ninguno obligatorio fuera de `build_hrv_final_dashboard.py`

### Primer consumidor candidato

- `analysis/session_analysis_pipeline.py`

Uso previsto cuando se quiera:

- leer motivos estructurados en lugar de parsear solo `reason_text`,
- distinguir mejor evidencia, inferencia y accion al redactar informes,
- resolver tensiones gate-contexto con menos ambiguedad.

### Decision de rollout

Mientras `analysis/` no lea `reason_items`:

- no se expone `reason_items_json` en `FINAL`.
- la lista de dicts se construye en memoria pero **no se serializa a JSON** dentro del pipeline de escritura de `build_hrv_final_dashboard.py`. Serializar una columna que nadie lee añade coste en cada sync sin aporte.

Cuando `analysis/` lo consuma de verdad:

- entonces si tiene sentido abrir Nivel B y decidir si `reason_items_json` entra en `FINAL` o en un sidecar.
- solo entonces se activa la serialización en el pipeline.

### Criterio concreto para activar Nivel B

No basta con "podria servir" o con leer la estructura de forma experimental.

Nivel B solo debe activarse si se cumplen a la vez estas condiciones:

1. `analysis/session_analysis_pipeline.py` o un consumidor equivalente lee motivos estructurados desde un artefacto publico;
2. existe al menos un test de integracion que demuestre ese consumo;
3. ese consumidor usa la estructura para ramificar logica real de informe o interpretacion, no solo para loguearla.

## Contrato de testing

La v3 debe venir con contrato de tests explicito.

### Si `SS-01` se implementa solo como Nivel A

Deben anadirse tests para:

- asegurar que todos los motivos se emiten por helper estructurado,
- asegurar que existe un test sentinel contra `append` libre o equivalente,
- asegurar que el render final de `reason_text` no cambia en escenarios ya cubiertos,
- asegurar que cada item contiene al menos `type/layer/source/message`,
- asegurar que `layer` solo usa el enum permitido,
- poder listar el catalogo real de emisores desde codigo.

No deben cambiar:

- `COLS_FINAL`
- `COLS_DASHBOARD`
- contrato documental de 66 columnas en `FINAL`

### Si algun dia se activa Nivel B

Entonces el cambio ya no es interno y hay que actualizar al menos:

- `COLS_FINAL` en `build_hrv_final_dashboard.py`
- `docs/contracts/ENDURANCE_HRV_Diccionario.md`
- `docs/contracts/ENDURANCE_HRV_Spec_Tecnica.md`
- headers de `seed_upload`
- tests de contrato que validen el schema publico

Decision v3:

- ese cambio no forma parte del alcance minimo recomendado.

## Criterios de aceptacion v3

`SS-01` se considerara bien resuelto si:

1. `reason_text` sigue existiendo y mantiene compatibilidad funcional.
2. Todos los motivos se construyen desde emisores estructurados, no con `append` libre.
3. El `layer` deja de ser ambiguo para casos mixtos porque la evidencia numerica va separada.
4. La frontera con `training_audit` queda explicita y sin duplicacion.
5. El catalogo real de `type` puede regenerarse leyendo el codigo emisor actual.
6. No se rompe `FINAL` ni `DASHBOARD` sin consumidor real.

## Recomendacion final v3

La forma proporcionada de hacer `SS-01` es:

1. refactor interno de emisores de `reason_text`,
2. contrato minimo de `reason_item`,
3. catalogo derivado desde helper/registry del codigo,
4. frontera explicita con `training_audit`,
5. sin nueva columna publica en `FINAL` hasta que `analysis/` la use.

Con esta version, `SS-01` deja de ser una idea abstracta de "semantizar mejor" y pasa a ser una tarea concreta, implementable y defendible.
