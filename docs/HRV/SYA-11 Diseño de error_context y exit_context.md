
**Versión:** 0.1 | **Estado:** en_discusión | **Última actualización:** 2026-04-20

Documento de trabajo para la evolución de las secciones de juicio en `build_final_report_markdown()`.
No es un contrato definitivo; registra el análisis activo para no perder hilo entre sesiones.

**Archivo:** `docs/HRV/SYA-11 Diseño de error_context y exit_context.md`  
**Tarea Kanvas:** SYA-11  
**Depende de:** [SYA-01 SS-02](SS-02%20Consumir%20reason_items%20en%20analysis%20para%20resolver%20tension%20y%20cautelas.md)

---

## Tabla de contenidos

1. [Contexto del problema](#contexto-del-problema)
2. [Arquitectura: Modelo 3](#arquitectura-modelo-3)
3. [Distinción fundamental](#distinción-fundamental-determinístico-vs-síntesis)
4. [error_context](#estructura-propuesta-error_context)
   - [Campos y cálculo](#campos-y-quién-los-calcula)
   - [Síntesis del analista](#qué-el-analista-sintetiza-con-esto)
5. [exit_context](#estructura-propuesta-exit_context)
   - [Campos y cálculo](#campos-y-quién-los-calcula-1)
   - [Síntesis del analista](#qué-el-analista-sintetiza-con-esto-1)
6. [block_role y adaptation_likely](#pregunta-de-diseño-abierta-block_role-y-adaptation_likely)
7. [Ejemplos esperados](#ejemplo-de-salida-modelo-3-esperada)
8. [Estado y próximos pasos](#estado-actual-y-próximos-pasos)
9. [Referencias](#referencias-y-documentos-relacionados)

---

## Quick reference

| Elemento | Ubicación | Responsable | Estado |
|---|---|---|---|
| Funciones actuales (genéricas) | [session_analysis_pipeline.py](/C:/Pilbond/polar-hrv-automation/analysis/session_analysis_pipeline.py) líneas 2910, 2828, 2933 | código | ❌ no diferenciado |
| `_build_error_context()` | [session_analysis_pipeline.py](/C:/Pilbond/polar-hrv-automation/analysis/session_analysis_pipeline.py) | **a implementar** | ⬜ |
| `_build_exit_context()` | [session_analysis_pipeline.py](/C:/Pilbond/polar-hrv-automation/analysis/session_analysis_pipeline.py) | **a implementar** | ⬜ |
| `build_final_reason_rendered()` | [session_analysis_pipeline.py:1900](/C:/Pilbond/polar-hrv-automation/analysis/session_analysis_pipeline.py:1900) | código ✅ | patrón a extender |
| `narrative_targets` en payload | [build_conversational_payload()](/C:/Pilbond/polar-hrv-automation/analysis/session_analysis_pipeline.py) | **a actualizar** | ⬜ |
| `analyst_prompt_rules.md` | [analyst_prompt_rules.md](/C:/Pilbond/polar-hrv-automation/analysis/analyst_prompt_rules.md) | **a actualizar** | ⬜ |

---

## Contexto del problema

Las secciones de juicio del informe programático —especialmente **§Dónde Estuvo el Error** y **§Cómo Habría Encajado Mejor**— tienen valor conceptual real pero implementación genérica:

```python
def _build_error_location(reporting_mode, positive_adaptations, negative_costs) -> str:
    if reporting_mode == "gate_first":
        return "Si hubo un error, estuvo más en la dosificación o en la agresividad..."
    if negative_costs and len(negative_costs) > len(positive_adaptations):
        return "Si hubo un error, estuvo más en el ajuste de la sesión al contexto..."
    return "No aparece un error claro de elección..."
```

El problema no es el concepto sino los **parámetros**: la función recibe muy poca información para distinguir casos y produce texto demasiado genérico.

---

## Arquitectura: Modelo 3

El patrón probado es `build_final_reason_rendered()`: el código computa **anclas estructuradas** y el analista (AI) genera la narrativa sobre esas anclas.

```
código   → anchor dict (error_context / exit_context)
analista → narrativa a partir de esas anclas
```

Esto extiende el mismo patrón que ya funciona para `§Tensión explícita` a las secciones de juicio.

Referencia: Ver [SS-02: Consumir reason_items en analysis](/C:/Pilbond/polar-hrv-automation/docs/HRV/SS-02%20Consumir%20reason_items%20en%20analysis%20para%20resolver%20tension%20y%20cautelas.md) para el patrón original en SYA-01.

---

## Distinción fundamental: determinístico vs síntesis

| Campo | Quién lo calcula | Criterio | Ejemplo |
|---|---|---|---|
| Comparaciones con umbral fijo | **Código** | `work_total >= 10`, `drift >= 10`, `gate_badge in ÁMBAR/ROJO` | `target_hit = work_total_min >= 10` |
| Conteo de señales | **Código** | `len(negative_costs)`, `climb_count`, `load_rank` | `negative_cost_count = 3` |
| Datos derivados no triviales | **Código** | Requieren data access o comparación con histórico | `load_rank_in_sport_7d`, `sessions_since_last_quality`, `gate_vs_execution_delta` |
| **Etiqueta de síntesis** | **Analista (IA)** | Jerarquizar signals en tensión; nombrar el concepto | nombre del locus del error, rol del bloque, probabilidad de adaptación |

El analista aporta lo que el código no puede hacer bien: **jerarquizar signals que apuntan en direcciones opuestas** y **nombrar la tensión** entre ellos.

**Principio clave:** El código debe proporcionar **"datos interesantes más allá del dato crudo"** (comparaciones, ranks, counts derivados). El analista sintetiza esos datos en narrativa significativa.

---

## Estructura propuesta: `error_context`

Ancla para **§Dónde Estuvo el Error**.

```json
{
  "error_context": {
    "gate_mode": "gate_first",
    "gate_vs_execution_delta": "exceeded",
    "execution_coherence": "high",
    "negative_cost_count": 3,
    "positive_count": 2,
    "thermal_penalty": "high",
    "durability_hint": "fade_like",
    "cost_vs_gate_mismatch": true
  }
}
```

### Campos y quién los calcula

| Campo | Código | Descripción |
|---|---|---|
| `gate_mode` | ✅ | `"gate_first"` (ÁMBAR/ROJO) o `"caution_first"` (VERDE) |
| `gate_vs_execution_delta` | ✅ | `"exceeded"` si `work_avg_z3_pct > 50` y gate era `Z2_O_TEMPO_SUAVE`; `"aligned"` si no |
| `execution_coherence` | ✅ | `"high"` si `subjective_coherence_score >= 85` |
| `negative_cost_count` | ✅ | `len(negative_costs)` del caller |
| `positive_count` | ✅ | `len(positive_adaptations)` del caller |
| `thermal_penalty` | ✅ | `thermal_band` de `composite_context` |
| `durability_hint` | ✅ | de `composite_context.durability_context` |
| `cost_vs_gate_mismatch` | ✅ | `gate_mode == "gate_first" and gate_vs_execution_delta == "exceeded"` |

### Qué el analista sintetiza con esto

Con `error_context`, el analista puede nombrar el **locus del error**:
- `gate_mode = gate_first` + `gate_vs_execution_delta = exceeded` → error de calibración/dosificación
- `gate_mode = caution_first` + `negative_cost_count > positive_count` → error de encaje en el bloque
- `execution_coherence = high` + `cost_vs_gate_mismatch = true` → el error fue de decisión, no de ejecución

Esta distinción (tipo vs dosis vs timing) no la puede hacer ninguna otra sección.

---

## Estructura propuesta: `exit_context`

Ancla para **§Cómo Habría Encajado Mejor**, **§Qué Construye vs Qué Consume** y, en parte, **§Qué Repetir / Qué No Repetir**.

```json
{
  "exit_context": {
    "execution_quality": {
      "target_hit": true,
      "work_total_min": 36.8,
      "cost_within_expected": false
    },
    "block_role_signals": {
      "load_rank_in_sport_7d": 1,
      "is_peak_load_in_block": true,
      "sessions_since_last_quality": 5,
      "effort_vs_recent": "above",
      "effort_vs_anchor": "above"
    },
    "adaptation_signals": {
      "sport_family": "bike",
      "climb_count": 2,
      "work_avg_z3_pct": 80,
      "long_duration": true,
      "thermal_load": "high",
      "gate_vs_execution_delta": "exceeded",
      "execution_coherence": "high"
    }
  }
}
```

### Campos y quién los calcula

#### `execution_quality`

| Campo | Código | Descripción |
|---|---|---|
| `target_hit` | ✅ | `work_total_min >= 10` (umbral de sesión con trabajo útil) |
| `work_total_min` | ✅ | dato directo de `session_row` |
| `cost_within_expected` | ✅ | `False` si `drift >= 10` o `durability_hint == "fade_like"` con gate VERDE |

#### `block_role_signals`

| Campo | Código | Descripción |
|---|---|---|
| `load_rank_in_sport_7d` | ✅ | rank de esta sesión entre las del mismo deporte en 7d (1 = más costosa) |
| `is_peak_load_in_block` | ✅ | `load > max(load de recent_rows)` |
| `sessions_since_last_quality` | ✅ | n sesiones desde la última con `work_total_min >= 10` en el mismo deporte |
| `effort_vs_recent` | ✅ | columna ya disponible en `sessions.csv` |
| `effort_vs_anchor` | ✅ | columna ya disponible en `sessions.csv` |

#### `adaptation_signals`

| Campo | Código | Descripción |
|---|---|---|
| `sport_family` | ✅ | dato directo |
| `climb_count` | ✅ | de `terrain_fit_context` o `_report_bike_climb_count()` |
| `work_avg_z3_pct` | ✅ | dato directo |
| `long_duration` | ✅ | `moving_min >= 180` (bike) o `moving_min >= 90` (trail) |
| `thermal_load` | ✅ | `thermal_band` de `composite_context` |
| `gate_vs_execution_delta` | ✅ | compartido con `error_context` |
| `execution_coherence` | ✅ | compartido con `error_context` |

### Qué el analista sintetiza con esto

Con `exit_context`, el analista puede:
- Nombrar el **rol del bloque**: `block_role_signals.is_peak_load_in_block = true` + `sessions_since_last_quality = 5` → "pico de carga del bloque después de 5 sesiones sin trabajo útil en bici"
- Evaluar si la **adaptación es probable**: `execution_coherence = high` + `cost_within_expected = false` + `thermal_load = high` → "adaptación posible pero con margen reducido por el peaje térmico y la ejecución por encima del gate"
- Especificar **qué habría encajado mejor**: con `climb_count`, `long_duration`, `gate_mode` y `cost_within_expected` puede formular: "mantener el tipo de salida pero con una subida menos o desplazarlo a un día sin clustering de intensidad"

---

## Pregunta de diseño abierta: `block_role` y `adaptation_likely`

### El instinto del usuario

> "El analista puede aportar algún dato interesante más allá del dato crudo."

Esto señala que los campos de síntesis NO deben ser etiquetas pre-computadas (`"peak_quality_stimulus"`, `true`). El analista necesita **recibir las señales no triviales que el código computa** (comparaciones, ranks, counts) y **nombrar la síntesis él mismo**.

### Propuesta: `block_role_signals` en lugar de `block_role`

En lugar de:
```json
"block_role": "peak_quality_stimulus"  // pre-computado → pobre diferenciación
```

Proponer:
```json
"block_role_signals": {
  "load_rank_in_sport_7d": 1,            // código computa: no trivial sin data access
  "is_peak_load_in_block": true,          // código computa: comparación directa
  "sessions_since_last_quality": 5       // código computa: count no trivial
}
```

El analista lee esos tres valores y escribe: *"pico de carga del bloque, primera sesión de calidad en ciclismo desde hace 5 sesiones"*. Eso es el "dato interesante" que el analista añade sobre los datos crudos.

### Propuesta: `adaptation_signals` en lugar de `adaptation_likely`

En lugar de:
```json
"adaptation_likely": true  // pre-computado → no captura tensión entre señales
```

Proponer:
```json
"adaptation_signals": {
  "gate_vs_execution_delta": "exceeded",  // gate dijo Z2, ejecutó Z3 — código computa
  "execution_coherence": "high",          // coherencia subjetiva ≥ 85 — código computa
  "recovery_margin_at_gate": "reduced",   // gate ÁMBAR → margen reducido — código computa
  "thermal_penalty": "high"               // thermal_band — código computa
}
```

El analista sintetiza: *"la adaptación es posible pero el exceso de ejecución sobre el gate y el peaje térmico reducen la probabilidad de absorción limpia"*. La tensión entre `execution_coherence = high` (lo hizo bien) y `gate_vs_execution_delta = exceeded` + `thermal_penalty = high` (pero a un coste real) es exactamente lo que el analista nombra y el código no puede.

---

## Ejemplo de salida Modelo 3 esperada

### §Dónde Estuvo el Error (bike, i138879060, ÁMBAR+++)

Con `error_context`:
```json
{
  "gate_mode": "gate_first",
  "gate_vs_execution_delta": "exceeded",
  "execution_coherence": "high",
  "thermal_penalty": "high",
  "cost_vs_gate_mismatch": true
}
```

Narrativa esperada del analista:
> Si hubo un error, estuvo en la **decisión**, no en la ejecución. El atleta ejecutó bien lo que se propuso (`execution_coherence = high`), pero lo que se propuso excedió claramente lo que el contexto matinal autorizaba. No fue una sesión mal ejecutada: fue una sesión bien ejecutada en el momento equivocado del bloque.

Esto es lo que la implementación actual no puede generar: la distinción entre "error de ejecución" vs "error de decisión".

### §Cómo Habría Encajado Mejor (bike, i138879060)

Con `exit_context`:
```json
{
  "block_role_signals": { "is_peak_load_in_block": true, "load_rank_in_sport_7d": 1 },
  "adaptation_signals": { "climb_count": 2, "gate_vs_execution_delta": "exceeded", "thermal_penalty": "high" }
}
```

Narrativa esperada del analista:
> Habría encajado mejor si la misma salida se hubiera desplazado a un día con gate verde o, si el contexto matinal ÁMBAR era ya fijo, manteniendo la salida larga pero haciendo solo una subida a tope en lugar de dos. El peaje de la segunda subida, sumado al calor, es lo que convirtió una sesión costosa en una sesión que recortó el margen del bloque siguiente.

---

## Estado actual y próximos pasos

### Pendiente de resolver

- [ ] Implementar `_build_error_context()` en `analysis/session_analysis_pipeline.py`
- [ ] Implementar `_build_exit_context()` en `analysis/session_analysis_pipeline.py`
- [ ] Añadir `error_context` y `exit_context` a `narrative_targets` en `build_conversational_payload()`
- [ ] Actualizar `analyst_prompt_rules.md` con reglas de uso de estos nuevos anchors
- [ ] Conectar ambos contexts a `_build_error_location()` y `_build_better_fit_readout()` para mejorar la versión programática

### Dependencias

- `composite_context` — ya implementado en SYA-07 ✅
- `terrain_fit_context` con `climb_count` — ya disponible ✅
- `effort_vs_recent`, `effort_vs_anchor` — ya en `sessions.csv` ✅
- `sessions_since_last_quality` — nuevo cálculo, requiere recorrer `recent_rows` ⬜

### Relación con SYA-01

El trabajo de `error_context` y `exit_context` es una extensión de [SYA-01 SS-02](/C:/Pilbond/polar-hrv-automation/docs/HRV/SS-02%20Consumir%20reason_items%20en%20analysis%20para%20resolver%20tension%20y%20cautelas.md) (consumir `reason_items` en analysis). El patrón es el mismo: anclas estructuradas que el analista usa para generar narrativa. La diferencia es que aquí las anclas no vienen de un contrato externo (FINAL.csv) sino de cómputos locales del pipeline de análisis.

Hoy SYA-01 está en Review. Una vez complete, SYA-11 se desbloqueará para implementación, reusando el patrón ya validado.

---

## Referencias y documentos relacionados

### Documentación existente

- [analysis/SESSION_ANALYSIS_METHOD.md](/C:/Pilbond/polar-hrv-automation/analysis/SESSION_ANALYSIS_METHOD.md) — Método operativo del análisis (v1.6+)
- [analysis/ENDURANCE_AGENT_DOMAIN.md](/C:/Pilbond/polar-hrv-automation/analysis/ENDURANCE_AGENT_DOMAIN.md) — Rol y tono del agente analítico
- [analysis/analyst_prompt_rules.md](/C:/Pilbond/polar-hrv-automation/analysis/analyst_prompt_rules.md) — Reglas para el analista (v1.8+)
- [analysis/AGENTS.md](/C:/Pilbond/polar-hrv-automation/analysis/AGENTS.md) — Autoridad operativa global del análisis
- [SS-01: Separar dato, proxy, inferencia y acción](SS-01%20Separar%20dato%20proxy%20inferencia%20y%20accion%20en%20la%20salida%20analitica.md) — Arquitectura base
- [SS-02: Consumir reason_items en analysis](SS-02%20Consumir%20reason_items%20en%20analysis%20para%20resolver%20tension%20y%20cautelas.md) — Patrón original (SYA-01)

### Código relacionado

- [analysis/session_analysis_pipeline.py](/C:/Pilbond/polar-hrv-automation/analysis/session_analysis_pipeline.py:2909) — Pipeline de análisis
  - `build_final_reason_rendered()` en [línea ~1900](/C:/Pilbond/polar-hrv-automation/analysis/session_analysis_pipeline.py:1900) — Patrón a extender
  - `_build_error_location()` en [línea ~2909](/C:/Pilbond/polar-hrv-automation/analysis/session_analysis_pipeline.py:2909) — Función a mejorar
  - `_build_better_fit_readout()` en [línea ~3070](/C:/Pilbond/polar-hrv-automation/analysis/session_analysis_pipeline.py:3070) — Función a mejorar
  - `build_conversational_payload()` — Payload del analista
- [analysis/endurance_rr_session_v4.py](/C:/Pilbond/polar-hrv-automation/analysis/endurance_rr_session_v4.py) — Análisis RR

### Tareas Kanvas relacionadas

- **SYA-01** — Consumir `reason_items` en analysis (en Review)
- **SYA-11** — error_context y exit_context (esta tarea, Proposed)
- **SYA-08** — Consolidación longitudinal y especialización por deporte (in progress)

---

## Historial de cambios

| Versión | Fecha | Cambio |
|---|---|---|
| 0.1 | 2026-04-20 | Documento inicial; diseño completo de error_context y exit_context; propuesta de block_role_signals y adaptation_signals |
| 0.2 | 2026-04-23 | Añadido análisis técnico de estado de implementación |

---

## Análisis técnico 2026-04-23

### Estado de implementación actual

- `_build_error_context()` y `_build_exit_context()` **no existen** en `analysis/session_analysis_pipeline.py`. Grep sobre `error_context|exit_context` en `analysis/` devuelve cero matches.
- Las funciones genéricas siguen tal cual se describen en el MD:
  - `_build_error_location()` en `analysis/session_analysis_pipeline.py:3703` (3 ramas estáticas por `reporting_mode`/counts).
  - `_build_better_fit_readout()` en `analysis/session_analysis_pipeline.py:3757` (ramas por `reporting_mode` + `sport_family` + `climb_phrase`).
- `build_final_reason_rendered()` en `analysis/session_analysis_pipeline.py:541` ya existe como patrón de referencia (SYA-01). Se inyecta en `narrative_targets` en `analysis/session_analysis_pipeline.py:5326`.
- `build_conversational_payload()` en `analysis/session_analysis_pipeline.py:5091`: bloque `narrative_targets` (líneas 5301-5330) incluye `final_reason_rendered`, `composite_context`, `durability_context`, `work_block_context` pero **no** `error_context` ni `exit_context`.
- `analysis/analyst_prompt_rules.md`: sin reglas para `error_context`/`exit_context`; solo regula `final_reason_items` y `final_reason_rendered` (líneas 14, 50-57).
- Dependencia SYA-01 (SS-02): referenciada en el MD como "en Review"; su patrón ya está consolidado en código, por lo que SYA-11 está técnicamente **desbloqueada**.

### Valor

- Sigue aportando valor. Las secciones §Dónde Estuvo el Error y §Cómo Habría Encajado Mejor son hoy texto canned con variabilidad casi nula (ver `_build_error_location:3703-3712`). Exponer señales derivadas (`load_rank_in_sport_7d`, `sessions_since_last_quality`, `cost_vs_gate_mismatch`) permite al analista distinguir "error de decisión" vs "error de ejecución", que ninguna otra sección cubre.
- El patrón Modelo 3 (código computa anclas, analista narra) ya está validado por SYA-01 → riesgo de diseño bajo.

### Errores / riesgos

- `sessions_since_last_quality` es cálculo nuevo: requiere recorrer `recent_rows` y definir umbral de "quality" (¿`work_total_min >= 10`?, ¿`is_quality_session`?). Sin consenso, cada implementación divergirá.
- `load_rank_in_sport_7d`: depende de qué columna de "load" se use (`load`, `load_cost`, `training_load`). Ambigüedad pendiente en el MD.
- Riesgo de duplicación con `composite_context` y `work_block_context` ya inyectados: varios campos propuestos (`thermal_penalty`, `durability_hint`, `effort_vs_recent`, `effort_vs_anchor`) ya viajan en esos objetos. Puede haber redundancia → o bien el analista consume de dos sitios la misma señal, o bien `error_context`/`exit_context` deberían ser **vistas proyectadas** (referencias/keys) más que copias.
- El MD no fija formato de ausencia: qué emite cada campo cuando falta dato (`None`, string vacío, omitir). Sin contrato, el analista tendrá que inferirlo.
- Nada previsto sobre cómo se degrada cuando `rr_unavailable=true` (análisis parcial).

### Mejoras propuestas

1. Antes de implementar, decidir **política de solapamiento** con `composite_context`/`work_block_context`: ¿`error_context` copia, referencia o proyecta subset? Documentar en el MD.
2. Definir en el MD la **convención de nulos** (`null` vs campo omitido) y cómo el analista debe reaccionar (¿silenciar ancla?, ¿fallback a texto genérico?).
3. Fijar la definición operativa de "quality session" para `sessions_since_last_quality` (propuesta: `work_total_min >= 10` y `sport_family` coincide).
4. Añadir una sección de **contrato de versión** (`error_context_version`, `exit_context_version`) como hace `final_reason_items_contract`, para permitir evolución sin romper analyst.
5. Incluir un caso de test de regresión con una sesión VERDE + bajo coste (donde hoy `_build_error_location` devuelve "No aparece un error claro") para asegurar que las anclas también generan narrativa coherente en ausencia de conflicto.
6. Conectar las nuevas anclas a las funciones programáticas (`_build_error_location`, `_build_better_fit_readout`) como upgrade silencioso: así la versión sin-IA también mejora.

### Conclusión

El diseño sigue vigente, bien alineado con el patrón SYA-01 y técnicamente desbloqueado. No hay implementación ninguna: falta todo el bloque de código (`_build_error_context`, `_build_exit_context`, inyección en `narrative_targets`, reglas en `analyst_prompt_rules.md`). Antes de pasar a `orange` conviene cerrar tres decisiones abiertas: (i) solapamiento con `composite_context`/`work_block_context`, (ii) política de nulos, (iii) definición de "quality session" para el rank. Con esas tres decisiones y el patrón de SYA-01 como plantilla, la implementación es mecánica y de riesgo bajo.

## Valor final de SYA-11

SYA-11 aporta valor real porque convierte dos secciones narrativas antes estáticas en anclas estructuradas reutilizables:

- `error_context` permite distinguir con más precisión si el problema fue de decisión, dosificación o encaje en el bloque.
- `exit_context` permite releer el rol real de la sesión dentro de la semana y evitar conclusiones basadas en un recorte corto de sesiones recientes.
- `narrative_targets` transporta esas anclas al payload de `analysis/` sin elevarlas a contrato canónico global.
- La ventana `load_rank_in_sport_7d` ya no depende de un recorte visual de 4 filas, sino de una ventana temporal real de 7 días por deporte.

En términos prácticos, la mejora no añade solo más texto:

- reduce falsos positivos narrativos sobre “primera sesión de calidad” o “bloque limpio”;
- mejora la coherencia entre `session_payload.json`, `report.auto.md` y el prompt del analista;
- deja una base estable para que futuras sesiones comparen el encaje en el bloque con una semántica reproducible.

El resultado final es útil porque hace más fiable la lectura de contexto sin tocar los contratos HRV globales ni inflar el informe con texto decorativo.
