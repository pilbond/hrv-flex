# Tarea: Baseline adaptativo de largo plazo

Estado: pendiente
Tipo de valor: valor de calibracion longitudinal y valor para la progresion semanal
Prioridad: alta

## Estado actual
Desde `2026-05-13`, `PCV-02` ya cerro la parte operativa principal de esta linea:

- `FINAL` expone `degraded_vs_best` y `degraded_vs_current_normal`
- `warning_mode=adaptive90` pasa a ser el default operativo
- `baseline60_degraded` queda como alias legacy
- contratos y tests ya reflejan esa nueva semantica

Por tanto, esta nota ya no compite con `HG-01`.
La relacion correcta hoy es:

- `PCV-02` = solucion canónica ya implantada para el warning largo plazo
- `HG-01` = hipotesis complementaria de metrica longitudinal adicional, solo si demuestra valor incremental frente a la lectura canónica actual

## Resumen
El problema original era que `baseline60_degraded` comparaba contra un `healthy_period` fijo y podia quedar cronificado cuando el atleta pasaba meses estable en un rango nuevo. Ese riesgo operativo ya quedo mitigado por `PCV-02`, pero sigue siendo relevante como contexto historico y de trazabilidad de la decision.

## Que falta exactamente
- mantener trazabilidad clara de que `PCV-02` absorbio esta necesidad operativa;
- vigilar si hace falta algun ajuste futuro de calibracion sobre `adaptive90`, sin reabrir la semantica base sin evidencia;
- conservar separacion entre gate diario y warning longitudinal;
- tratar `HG-01` solo como hipotesis complementaria y no como alternativa competidora mientras no haya evidencia nueva.

## Por que sigue teniendo valor
- deja trazable por que se cambio la semantica del warning largo plazo;
- ayuda a interpretar la convivencia entre `historical_best` y `current_normal`;
- evita reabrir en falso el mismo problema bajo nombres distintos.

## Archivos candidatos
- `build_hrv_final_dashboard.py`
- `docs/contracts/ENDURANCE_HRV_Spec_Tecnica.md`
- `docs/contracts/ENDURANCE_HRV_Diccionario.md`
- `docs/contracts/ENDURANCE_HRV_Estructura.md`

## Criterio de cierre
La linea queda cerrada cuando:

- la semantica implantada en `PCV-02` se considera estable;
- la documentacion deja claro que `HG-01` es solo una hipotesis complementaria y no una alternativa pendiente al warning canónico;
- no quedan ambiguedades operativas entre baseline adaptativo, warning dual y backlog longitudinal diferido.
