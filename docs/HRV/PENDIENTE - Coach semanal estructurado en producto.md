# Tarea: Coach semanal estructurado en producto

Estado: pendiente
Tipo de valor: valor de decision semanal y valor de productizacion del metodo coach
Prioridad: media-alta

## Resumen
El metodo semanal existe y esta bastante trabajado, pero todavia no aparece como salida estructurada del producto ni en `FINAL/DASHBOARD` ni en la UI/API principal.

## Que falta exactamente
- convertir el metodo semanal en un output estable del sistema;
- definir un payload minimo como `week_verdict`, `week_type`, `progression_risk` y `next_week_guidance`;
- decidir si esa salida vive en JSON, endpoint especifico, bloque de UI o artefacto derivado;
- mantener separado el gate diario de la capa coach semanal.

## Por que sigue teniendo valor
- convierte conocimiento documental en decision reutilizable;
- reduce dependencia de lectura manual del metodo;
- permite usar la capa coach de forma consistente entre analisis, UI y automatismos futuros.

## Archivos candidatos
- `analysis/WEEKLY_ANALYSIS_METHOD.md`
- `web_ui.py`
- `build_hrv_final_dashboard.py`
- `docs/contracts/ENDURANCE_HRV_Spec_Tecnica.md`

## Criterio de cierre
La capa coach semanal se expone como salida estructurada del sistema y no solo como procedimiento documental o prompt.
