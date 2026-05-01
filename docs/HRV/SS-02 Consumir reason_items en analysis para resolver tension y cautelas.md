## Objetivo
Activar un consumidor real de `reason_items` dentro de `analysis/` para que la capa semantica introducida en `SS-01` deje de ser solo un detalle interno del builder y pase a gobernar de forma trazable la lectura de cautelas, tensiones y restricciones operativas en los informes.

La tarea no busca rehacer `analysis/`, ni duplicar `training_audit`, ni introducir un sistema semantico grande. Busca una integracion minima, util y testeable.

## Tesis central
Hoy `analysis/` ya consume:

- `sessions_day.csv` como contexto de carga,
- `ENDURANCE_HRV_sessions_metadata.json` como fuente estructurada de `training_audit`,
- `ENDURANCE_HRV_master_FINAL.csv` como contexto HRV diario.

Pero la parte semantica mas sensible de `FINAL` sigue entrando solo como texto libre:

- `gate_badge`,
- `Action`,
- `reason_text`.

Eso obliga a resolver tensiones practicas a partir de frases mezcladas, cuando `SS-01` ya separo internamente:

- dato medido,
- proxy,
- inferencia,
- accion.

La oportunidad real de `SS-02` es esta:

- mantener `training_audit` como autoridad de interpretabilidad de la capa de sesiones,
- y usar `reason_items` para la semantica fina del contexto HRV diario.

## Estado actual del repo
En [analysis/session_analysis_pipeline.py](/C:/Pilbond/polar-hrv-automation/analysis/session_analysis_pipeline.py:955) la fila de `FINAL` que viaja al payload solo incluye:

- `gate_badge`,
- `Action`,
- `baseline60_degraded`,
- `recovery_context_quality`,
- `recovery_support_class`,
- `recovery_discordance_flag`,
- `recovery_discordance_reason`,
- `reason_text`.

Las reglas del modulo analitico ya exigen resolver la tension entre badge favorable y cautela material:

- [analysis/AGENTS.md](/C:/Pilbond/polar-hrv-automation/analysis/AGENTS.md:225)
- [analysis/SESSION_ANALYSIS_METHOD.md](/C:/Pilbond/polar-hrv-automation/analysis/SESSION_ANALYSIS_METHOD.md:810)

Pero hoy esa resolucion depende de:

- texto libre en `reason_text`,
- semantica implicita,
- y criterio narrativo del analista.

`training_audit`, en cambio, ya tiene una capa estructurada compartida y reusable. `SS-02` debe seguir ese patron y no competir con el.

## Opciones utiles de consumo

### Opcion 1. Enriquecer el payload del informe diario
Anadir `final_reason_items` al payload construido por `analysis/session_analysis_pipeline.py`.

Uso esperado:

- distinguir que parte del contexto diario es `measured`, `proxy`, `inference` o `action`,
- evitar parsear `reason_text`,
- dar al analista IA una jerarquia semantica explicita.

Valor:

- alto
- coste bajo
- encaje directo con el informe diario

### Opcion 2. Derivar flags canonicas para tension y cautela
Construir una pequena capa rule-based a partir de `reason_items`, por ejemplo:

- `has_measured_quality_caution`
- `has_load_inference_caution`
- `has_action_constraint`
- `has_recovery_discordance`

Uso esperado:

- abrir o no el apartado `Tension explicita`,
- modular el tono operativo del informe,
- hacer visible cuando un verde es favorable pero condicionado.

Valor:

- alto
- coste medio
- mejor determinismo que el texto libre

### Opcion 3. Consumidor para el informe semanal
Usar `reason_items` para resumir:

- frecuencia de cautelas por calidad de dato,
- frecuencia de restricciones operativas,
- peso de carga, recuperacion o discordancia como origen de la cautela semanal.

Valor:

- medio
- coste medio
- util, pero no es el primer sitio donde mas duele la opacidad actual

### Opcion 4. Consumidor para QA y observabilidad
Usar `reason_items` para metricas internas:

- conteo por `type`,
- uso real de `layer`,
- consistencia entre `gate_badge`, `Action` y `action_constraint`,
- deteccion de emisores semanticos raros.

Valor:

- medio
- coste bajo
- retorno mas de mantenimiento que de informe

## Propuesta recomendada
La tarea `SS-02` deberia cubrir solo las dos primeras opciones:

1. consumidor real en `analysis/session_analysis_pipeline.py` para enriquecer el payload con `final_reason_items`;
2. derivacion de una capa minima de flags canonicas para resolver tension y cautelas de forma no ambigua.

No deberia incluir todavia:

- un redisenho completo del informe semanal,
- un motor semantico nuevo paralelo a `training_audit`,
- ni una explosion de reglas por `type`.

## Contrato minimo de consumo

### Entrada requerida
`analysis/` debe recibir una lista `final_reason_items` por fecha. La fuente puede ser:

- un sidecar estable,
- o una columna serializada en `FINAL`,

pero el contrato de `analysis/` no debe depender del mecanismo exacto de transporte.

Cada item consumible debe seguir este minimo:

```json
{
  "type": "data_quality",
  "layer": "measured",
  "source": "hrv_pipeline",
  "message": "Dato dudoso: limitar a Z1-Z2 max 90min"
}
```

Campos opcionales soportados:

- `variant`
- `severity`
- `metric`
- `value`
- `threshold`
- `gate_scope`
- `codes`
- `evidence`

`analysis/` debe ignorar con seguridad cualquier campo adicional no reconocido.

### Tipos y capas que el consumidor minimo debe entender
Sin imponer una tabla cerrada de todo el catalogo futuro, el consumidor inicial debe tratar de forma explicita al menos:

- `data_quality`
- `acwr`
- `monotony`
- `strain`
- `load_context`
- `clustering`
- `recovery_support`
- `recovery_discordance`
- `action_constraint`

Layers requeridos:

- `measured`
- `proxy`
- `inference`
- `action`

Si aparece un `layer` fuera de ese enum, el consumidor debe degradar de forma segura y marcar el payload como no conforme.

### Flags derivadas minimas
Desde `final_reason_items`, `analysis/` debe poder derivar al menos estas cuatro banderas:

- `has_measured_quality_caution`
  - `true` si existe algun item con `type = data_quality` y `layer = measured`
- `has_load_inference_caution`
  - `true` si existe algun item de `acwr`, `monotony`, `strain`, `load_context` o `clustering` con `layer = inference`
- `has_action_constraint`
  - `true` si existe algun item con `layer = action`
- `has_recovery_discordance`
  - `true` si existe algun item con `type = recovery_discordance`

El payload diario debe exponer estas flags ya calculadas, no obligar al prompt a reconstruirlas.

### Regla de convivencia con training_audit
`training_audit` y `reason_items` no compiten.

Regla:

- `training_audit` gobierna interpretabilidad y confianza de la capa de sesiones;
- `reason_items` gobierna la semantica explicita del contexto HRV diario.

Por tanto:

- `training_audit.signal_level.interpretability_limits` sigue siendo la fuente preferente de limitaciones globales de sesiones;
- `reason_items` no debe duplicar esas limitaciones salvo cuando una cautela del dia dependa directamente del pipeline HRV diario.

### Regla de uso en el informe
El informe diario debe seguir pudiendo renderizarse si `final_reason_items` no existe, usando `reason_text` como fallback.

Pero cuando `final_reason_items` exista:

- la apertura de `Tension explicita` debe basarse primero en las flags derivadas,
- el prompt debe preferir `final_reason_items` sobre inferencias libres desde `reason_text`,
- `reason_text` queda como render humano resumido, no como fuente primaria.

## Impacto tecnico esperado
Cambios minimos esperables:

- ampliar la carga de `FINAL` en [analysis/session_analysis_pipeline.py](/C:/Pilbond/polar-hrv-automation/analysis/session_analysis_pipeline.py:955) para leer `reason_items`;
- anadir normalizacion/parseo seguro del bloque;
- derivar flags canonicas antes de construir el payload conversacional;
- ajustar prompts o renderizadores para usar esa capa;
- tests de integracion que prueben que una restriccion operativa y una cautela medida ya no dependen de regex sobre `reason_text`.

## No objetivos
Esta tarea no debe:

- mover logica fisiologica fuera de `FINAL`,
- sustituir `training_audit`,
- rehacer `WEEKLY_ANALYSIS_METHOD.md` completo,
- ni exigir un catalogo documental cerrado de todos los `type` futuros.

## Criterios de aceptacion propuestos
1. `analysis/session_analysis_pipeline.py` puede cargar `final_reason_items` sin romper el flujo cuando no existan.
2. El payload diario expone `final_reason_items` y las flags derivadas minimas.
3. El informe diario puede abrir `Tension explicita` sin depender solo de `reason_text`.
4. `training_audit` sigue siendo la autoridad de interpretabilidad de la capa de sesiones y no se duplica en `reason_items`.
5. Existe al menos un test de integracion donde:
   - un item `data_quality` activa `has_measured_quality_caution`,
   - y un item `action_constraint` activa `has_action_constraint`.
6. Existe al menos un test de fallback donde `reason_items` no esta presente y el pipeline sigue funcionando con `reason_text`.

