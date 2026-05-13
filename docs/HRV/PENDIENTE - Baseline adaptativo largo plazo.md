# Tarea: Baseline adaptativo de largo plazo

Estado: pendiente
Tipo de valor: valor de calibracion longitudinal y valor para la progresion semanal
Prioridad: alta

## Resumen
El warning `baseline60_degraded` sigue comparando contra un `healthy_period` fijo. Si el atleta pasa meses estable en un rango nuevo, la alerta puede quedar cronificada y perder utilidad.

## Que falta exactamente
- sustituir o complementar el `healthy_period` fijo por una referencia adaptativa;
- evaluar opciones como baseline rolling de 90 dias, reseteo condicionado o doble referencia (`historical_best` vs `current_normal`);
- mantener la separacion entre gate diario y warning longitudinal;
- actualizar contratos y diccionario para reflejar la nueva semantica.

## Por que sigue teniendo valor
- evita que el warning longitudinal se vuelva ruido permanente;
- mejora la utilidad coach de `baseline60_degraded` para semanas de progresion y descarga;
- hace que el sistema reconozca cambios reales de estado basal del atleta.

## Archivos candidatos
- `build_hrv_final_dashboard.py`
- `docs/contracts/ENDURANCE_HRV_Spec_Tecnica.md`
- `docs/contracts/ENDURANCE_HRV_Diccionario.md`
- `docs/contracts/ENDURANCE_HRV_Estructura.md`

## Criterio de cierre
El baseline largo plazo deja de depender exclusivamente de un tramo historico fijo y mantiene valor interpretativo cuando el atleta cambia de rango basal durante meses.
