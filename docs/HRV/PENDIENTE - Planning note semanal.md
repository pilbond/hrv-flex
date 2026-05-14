# Tarea: Planning note semanal

Estado: implementada
Tipo de valor: valor accionable corto y valor de traduccion analisis -> plan
Prioridad: media-alta

## Resumen
La orientacion semanal ya se materializa como `planning_note` en `ENDURANCE_HRV_weekly_coach.json` y se expone en `/api/status` para consumo operativo.

## Que falta exactamente
- mantener sincronizado el texto con el metodo semanal y el prompt de informe cuando cambien las reglas;
- revisar si la UI debe mostrar `planning_note` de forma visible o solo via status.

## Por que sigue teniendo valor
- convierte analisis en una consigna util;
- mejora mucho la usabilidad del sistema para planificar microciclos;
- deja una traza corta de recomendacion sin necesidad de leer el informe completo.

## Archivos candidatos
- `analysis/WEEKLY_ANALYSIS_METHOD.md`
- `web_ui.py`
- `docs/prompts/informe semanal de entrenamiento.md`
- `docs/contracts/ENDURANCE_HRV_Diccionario.md`

## Criterio de cierre
El sistema genera una recomendacion semanal corta, trazable y reutilizable para la planificacion inmediata.
