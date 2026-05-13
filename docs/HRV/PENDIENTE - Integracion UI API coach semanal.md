# Tarea: Integracion UI/API del coach semanal

Estado: pendiente
Tipo de valor: valor de acceso operativo y valor de visibilidad del sistema
Prioridad: media

## Resumen
La parte coach existe como metodo y prompt, pero no esta claramente expuesta en la UI ni en endpoints especificos para consulta semanal.

## Que falta exactamente
- decidir el punto de exposicion: endpoint, bloque de `/api/status`, nuevo recurso o bloque UI dedicado;
- mostrar el estado semanal sin mezclarlo con el gate diario;
- enlazar la salida semanal con sus fuentes (`FINAL`, `sessions_day`, `sleep`, informes semanales si aplica);
- documentar el contrato de consumo.

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
La UI o API expone una vista semanal coach clara, separada del gate diario y basada en contrato.
