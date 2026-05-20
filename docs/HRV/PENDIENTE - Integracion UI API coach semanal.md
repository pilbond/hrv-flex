# Tarea: Integracion UI/API del coach semanal

Estado: implementada
Tipo de valor: valor de acceso operativo y valor de visibilidad del sistema
Prioridad: media

## Resumen
La parte coach existe como metodo y prompt, y ahora se expone en una tarjeta dedicada de la UI a partir de `/api/status`, sin crear un endpoint nuevo.

## Que falta exactamente
- mantener sincronizado el texto con el metodo semanal y el prompt de informe cuando cambien las reglas;
- revisar si conviene ampliar la tarjeta con mas contexto semanal cuando el contrato de `ENDURANCE_HRV_weekly_coach.json` crezca.

## Por que sigue teniendo valor
- hace util la capa coach sin depender de ejecuciones manuales externas;
- mejora la trazabilidad entre dato, interpretacion y accion;
- prepara la arquitectura para automatismos futuros sin tocar el decisor HRV.

## Archivos candidatos
- `web_ui.py`
- `docs/contracts/ENDURANCE_HRV_Spec_Tecnica.md`
- `docs/contracts/ENDURANCE_HRV_Estructura.md`
- `analysis/WEEKLY_ANALYSIS_METHOD.md`

## Criterio de cierre
La UI expone una vista semanal coach clara, separada del gate diario y basada en contrato.
