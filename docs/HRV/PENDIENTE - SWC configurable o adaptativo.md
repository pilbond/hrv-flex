# Tarea: SWC configurable o adaptativo

Estado: pendiente
Tipo de valor: valor de precision del gate y reduccion de falsos positivos
Prioridad: alta

## Resumen
El `swc_mult` sigue fijo en `0.5`. Para este atleta, el Kanvas ya identifico que esa sensibilidad puede generar alternancias VERDE-ROJO-VERDE demasiado nerviosas.

## Que falta exactamente
- permitir configurar `swc_mult` por entorno o por perfil de atleta;
- o calcularlo dinamicamente a partir de la variabilidad real del atleta;
- revisar el impacto en `gate_base60`, sombras y veto agudo;
- actualizar los contratos para que el comportamiento quede normado.

## Por que sigue teniendo valor
- reduce falsos `ROJO` y `AMBAR` cuando el sistema es demasiado reactivo;
- mejora la estabilidad del semaforo sin perder sensibilidad a caidas reales;
- ataca una limitacion del decisor, no solo del texto explicativo.

## Archivos candidatos
- `build_hrv_final_dashboard.py`
- `docs/contracts/ENDURANCE_HRV_Spec_Tecnica.md`
- `docs/contracts/ENDURANCE_HRV_Diccionario.md`

## Criterio de cierre
`swc_mult` deja de ser una constante fija ciega y pasa a estar parametrizado o adaptado, con contrato actualizado y comportamiento verificable.
