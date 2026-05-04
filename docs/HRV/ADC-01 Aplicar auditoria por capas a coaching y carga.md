
## Objetivo
Formalizar una capa minima de auditoria de entrenamiento que separe:
- dato disponible,
- dato interpretable,
- y dato accionable.

La tarea no busca rehacer el pipeline ni bloquear el sistema por detalles menores. Busca evitar conclusiones fisiologicas fuertes cuando la capa de sesiones no tenga la calidad suficiente para sostenerlas.

## Diagnostico actual
El repo ya tiene varias piezas tecnicas utiles en la capa de sesiones:
- `zones_source` por sesion
- `stream_dt_est` como canario de sampling
- `ENDURANCE_HRV_sessions_metadata.json` con `with_streams`, `stream_sampling` y `zones_source_dist`
- tests de contrato para `sessions.csv`, `sessions_day.csv` y metadata

Pero esas piezas aun no gobiernan la interpretacion. Hoy el sistema sabe cosas como:
- si hubo `fallback` de zonas
- si el sampling fue raro
- si una sesion no tiene drift

pero no convierte eso en una regla explicita del tipo:
- `high_confidence`
- `contextual`
- `informational`
- `not_applicable`

## Comparacion con el proyecto original
`intervalsicugptcoach-public` tiene una arquitectura mas madura en este punto:
- auditoria por tiers
- `data_quality_audit()` con coverage, state y trust_level
- reglas de `metric_confidence`
- resolucion de confianza antes del render

La leccion util no es copiar toda esa arquitectura. La leccion util es esta:
- primero validar si una capa es interpretable;
- despues calcular metricas;
- y solo entonces decidir si la lectura es accionable o solo contextual.

## Situacion real de tus datos actuales
La capa de sesiones esta hoy bastante limpia:
- `350` sesiones totales
- `zones_source = icu` en `350/350`
- `zones_source = fallback` en `0%`
- `229` sesiones con `stream_dt_est`
- `0` sesiones con sampling sospechoso
- `230` sesiones aerobicas
- `229/230` aerobicas con stream (`99.6%`)
- `204/230` aerobicas con `cardiac_drift_pct` (`88.7%`)
- `76/76` sesiones largas aerobicas con drift
- `bike/road_run/trail_run` con triplete `z1/z2/z3` en `100%`

Esto implica algo importante:
- `ADC-01` no es urgente porque hoy haya una gran corrupcion de datos;
- `ADC-01` es valiosa porque evita sobreinterpretaciones y protege frente a regresiones futuras o semanas de cobertura rara.

Lectura honesta del valor actual:

- con la calidad actual del repo, una auditoria formal diria `todo bien` en la gran mayoria de los casos;
- por tanto, el valor inmediato de `ADC-01` es bajo como mejora operativa diaria;
- su valor real hoy es de trazabilidad, hardening y preparacion para metricas nuevas o degradaciones futuras.

## Escenarios de activacion
La mejor forma de justificar `ADC-01` no es pensar en el historico actual, sino en los escenarios concretos donde una auditoria de confianza pasaria de casi trivial a realmente discriminante.

| Escenario | Que cambiaria | Efecto esperable en auditoria |
|---|---|---|
| Cambio de reloj o sensor | `zones_source` pasa a `fallback` o cambian las zonas disponibles | rebajar confianza de zonas y de metricas derivadas de intensidad |
| Fallo temporal de Intervals API | aparecen sesiones sin streams o con cobertura parcial | rebajar confianza de `cardiac_drift`, `work_*` y otras metricas dependientes de stream |
| Periodo de lesion o descanso largo | muy pocas sesiones en las ventanas recientes | `distribution_confidence = low`, `load_ctx_ready = False` o contexto cronico insuficiente |
| Nuevo deporte sin VT calibrado | se usa fallback generico de VT1/VT2 | marcar zonas e interpretacion por deporte como `contextual` |
| Degradacion del HR strap o de la captura | `stream_dt_est` anomalo, falta de stream o drift sistematicamente ausente donde deberia existir | activar alertas de calidad de señal y rebajar interpretabilidad cardiaca |

Estos escenarios son los que convierten `ADC-01` en una capa operativamente util. Mientras no aparezcan, su valor es sobre todo preventivo y de trazabilidad.

## Mejora medible esperable
La mejora principal no es “mas datos”, sino “mejor gobierno interpretativo”.

### 1. Cobertura formalizada de la capa aerobica
Convertir cobertura tecnica ya existente en reglas reutilizables:
- `99.6%` cobertura de streams aerobicos
- `88.7%` cobertura de drift aerobico
- `100%` de zonas completas en deportes principales

### 2. Proteccion sobre metricas nuevas
Permite modular de forma reproducible:
- `DO-01`: distribucion por deporte con confianza alta o contextual segun sesiones y zonas
- `FP-01`: durability como `not_applicable` o `low_confidence` cuando falte senal mecanica fiable
- `AP-01`: NDLI como `contextual` si la densidad de sesiones utiles no soporta una lectura fuerte

### 3. Reduccion de sobreinterpretacion
Hoy ya hay casos que deberian degradar lectura:
- `26` sesiones aerobicas sin drift
- `1` sesion aerobica sin stream y sin zonas derivadas
- sesiones de fuerza, mobility u `other` con semantica fisiologica mas debil

`ADC-01` evitaria tratar esas situaciones como si todas las metricas fueran equivalentes.

### 4. Trazabilidad para analysis y futuras capas
Pasarias de:
- “la metrica existe”

a:
- “la metrica existe con esta confianza, por estas razones, y con estas limitaciones”

## Propuesta de implementacion
## Fase 1 - contrato documentado por metrica
Primero documentar las reglas de confianza y aplicabilidad en `docs/contracts/`, sin crear todavia un motor central grande.

Objetivo:

- dejar claro que condiciones hacen que una metrica sea `high`, `contextual`, `informational` o `not_applicable`;
- permitir que cada tarea (`DO-01`, `AP-01`, `FP-01`, etc.) aplique esas reglas localmente de forma consistente.

Decision metodologica:

- en v1, priorizar contrato y reglas explicitas;
- no crear todavia `training_confidence.py` salvo que aparezca duplicacion real entre consumidores.

## Fase 2 - metadata enriquecida
Ampliar `ENDURANCE_HRV_sessions_metadata.json` con un bloque ligero de calidad y aplicabilidad global.

Ejemplo de contenido esperable:

- `%` de sesiones aerobicas con stream
- `%` de sesiones aerobicas con drift disponible
- `%` de `zones_source = fallback`
- `sampling_ok`
- resumen de deportes o contextos con interpretabilidad limitada

No hace falta un artefacto nuevo si la metadata existente puede absorberlo.

## Fase 3 - niveles de auditoria
Separar conceptualmente tres niveles:

### dataset_level
- sesiones totales
- dias
- rango temporal
- duplicados si aplica

### signal_level
- `%` con streams
- `%` con drift
- `%` con zonas
- `%` fallback
- sampling OK / no OK

### metric_level
- `polarisation_confidence`
- `ndli_confidence`
- `durability_confidence`
- `load_context_confidence`

## Fase 4 - reglas simples y explicitas
Ejemplos razonables para este repo:

### Polarisation / distribucion por deporte
- `high` si `>=3` sesiones utiles y triplete `z1/z2/z3` completo
- `contextual` si `2`
- `informational` si `<2`

### Durability
- `high` solo si hay stream valido y deporte interpretable
- `low` o `not_applicable` si no hay senal mecanica suficiente

### NDLI
- `contextual` por defecto
- `high` si hay al menos `2` sesiones `work_intense` utiles en la ventana

### Cardiac drift
- `high` si hay duracion minima y stream valido
- `not_applicable` en fuerza, mobility u `other`

Estas reglas no tienen por que vivir aun en un modulo central. Pueden aplicarse localmente por cada metrica, siempre que sigan el contrato documentado.

## Fase 5 - integracion de consumo
### Pipeline global
No hace falta un output complejo en v1.

Basta con una de estas dos opciones:
- guardar un `ENDURANCE_HRV_training_audit.json` ligero
- o, preferiblemente en v1, ampliar `ENDURANCE_HRV_sessions_metadata.json` con un bloque `signal_quality` y otro opcional de `metric_applicability`

### analysis/
`analysis` deberia consumir esta capa para:
- rebajar confianza automaticamente
- declarar limitaciones de forma reproducible
- evitar reconstruir la auditoria a mano en cada informe

## Fase 6 - reason_text solo si aparece necesidad real
Con la calidad actual del repo, esta fase no debe ser parte del alcance base.

Solo despues de estabilizar la auditoria y si aparecen casos reales que lo justifiquen:
- `lectura de carga: confianza moderada por cobertura parcial`
- `durability no interpretable esta semana`
- `distribucion por deporte contextual, no accionable`

Esto no debe tocar el gate HRV.

## Recomendacion final
La version correcta de `ADC-01` no es copiar el sistema de auditoria completo del proyecto original.

La version correcta es:
- una capa minima y compartida de confianza/aplicabilidad,
- basada en señales que ya existen,
- usada por `analysis` y por las nuevas metricas de carga/coaching,
- y lo bastante simple para no sobredisenar el repo.

No debe abordarse en v1 como:

- un gran modulo central nuevo,
- una capa textual nueva en `reason_text`,
- ni un prerequisito duro para implementar primero `CDC-01`, `AP-01` o `DO-01`.

Timing recomendado:

- implementar antes las metricas que realmente necesitan reglas locales de confianza (`CDC-01`, `AP-01`, `DO-01`);
- usar `ADC-01` despues como tarea de consolidacion para formalizar y unificar esas reglas cuando ya exista una masa critica de consumidores.

## Decision practica
Si se implementa ahora, el orden razonable es:
1. definir reglas minimas de confianza por metrica;
2. exponerlas en metadata enriquecida;
3. hacer que `analysis` y futuras metricas las consuman localmente;
4. solo si aparece duplicacion real, extraer helper o modulo compartido;
5. solo luego decidir si compensa un artefacto de auditoria mas rico.
