# Tarea: Coach semanal estructurado en producto

Estado: pendiente
Tipo de valor: decision semanal y productizacion minima del metodo coach
Prioridad: media-alta

## Redefinicion

Esta tarea NO debe intentar cerrar toda la capa coach semanal.
Su alcance correcto es mas estrecho:

- formalizar una salida estructurada semanal, determinista y reproducible;
- dejar fuera la narrativa LLM y la exposicion UI/API;
- servir de base para `PCV-05` y `PCV-06` sin solaparse con ellas.

## Problema real

El metodo semanal ya existe en `analysis/WEEKLY_ANALYSIS_METHOD.md` y el
repositorio ya puede producir informes semanales manuales, pero hoy no
existe un artefacto maquina estable que resuma la semana a nivel de
producto.

El gap no es de metodo analitico. El gap es de contrato y reutilizacion:

- no hay sidecar semanal canonico;
- `PCV-05` no tiene una base estructurada comun;
- `PCV-06` no tiene un recurso claro que exponer;
- el weekly sigue dependiendo de lectura manual o ejecucion ad hoc.

## Alcance valido de PCV-04

PCV-04 solo debe construir la capa estructurada determinista.

Output propuesto:

- `ENDURANCE_HRV_weekly_coach.json`

Responsabilidad de esta capa:

- resumir la semana ISO actual o la ultima semana calculable;
- consolidar senales semanales ya disponibles en el sistema;
- exponer un contrato compacto y estable para consumo posterior.

Esta tarea MUST NOT:

- generar `week_verdict` narrativo;
- generar `next_week_guidance` en texto;
- abrir endpoints nuevos;
- tocar `FINAL.csv`, `DASHBOARD.csv` o el gate diario;
- absorber el alcance propio de `PCV-05` o `PCV-06`.

## Campos minimos propuestos

- `iso_week`
- `window_start`
- `window_end`
- `week_is_partial`
- `week_type`
- `week_type_confidence`
- `week_load`
- `progression_risk`
- `hrv_trend`
- `data_quality`

## Semantica minima de campos

- `iso_week`: identificador `YYYY-Www`
- `window_start`, `window_end`: limites lunes-domingo
- `week_is_partial`: `true` si la semana no ha terminado al calcular
- `week_type`: patron observado semanal a partir de
  `ENDURANCE_HRV_intensity_distribution_weekly.csv`
- `week_type_confidence`: confianza de esa lectura semanal
- `week_load`: carga agregada semanal desde `sessions_day.csv`
- `progression_risk`: clasificacion simple desde carga reciente
  usando `ACWR/monotony/strain`
- `hrv_trend`: direccion resumida de la semana (`rising`, `stable`,
  `falling`, `insufficient_data`)
- `data_quality`: bandera compacta de interpretabilidad semanal

## Inputs canonicos

- `ENDURANCE_HRV_sessions_day.csv`
- `ENDURANCE_HRV_intensity_distribution_weekly.csv`
- `ENDURANCE_HRV_master_DASHBOARD.csv`
- `ENDURANCE_HRV_sessions_metadata.json` si hace falta rebajar confianza

## Lugar natural de implementacion

- `build_sessions.py`

Razon:

- ya produce sidecars semanales;
- ya concentra la capa de carga e intensidad;
- evita mezclar contrato semanal con el pipeline HRV diario.

## Relacion con otras tareas

- `PCV-05` debe consumir esta salida para producir una recomendacion
  corta reutilizable.
- `PCV-06` debe exponer esta salida o su derivado en UI/API.

Por tanto:

- `PCV-04` desbloquea;
- `PCV-05` traduce a accion;
- `PCV-06` expone en producto.

## Valor real

La tarea si tiene valor porque reduce una dependencia manual que hoy
limita la reutilizacion del weekly. Su valor no esta en crear mas
analisis, sino en fijar un contrato semanal compacto y reproducible.

El valor seria bajo si intentara incluir narrativa o UI dentro de la
misma tarjeta, porque eso la convertiria en una tarea paraguas
redundante.

## Riesgos y limites

- riesgo de inventar una semantica semanal demasiado ambiciosa antes de
  validar uso real;
- riesgo de duplicar señales ya presentes en sidecars existentes;
- riesgo de colar conclusiones narrativas en una capa que debe ser solo
  estructural.

Mitigacion:

- mantener pocos campos;
- preferir clasificaciones simples y auditables;
- dejar toda narrativa y entrega visual fuera de esta tarjeta.

## Criterio de cierre

1. `build_sessions.py` genera `ENDURANCE_HRV_weekly_coach.json`.
2. El JSON contiene solo campos deterministas y auditables.
3. El output queda documentado en `docs/contracts/`.
4. La tarea no introduce endpoint, UI ni texto narrativo.
