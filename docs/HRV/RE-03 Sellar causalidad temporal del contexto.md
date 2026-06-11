
Corregir la capa de contexto para que ninguna explicación histórica cambie al añadir datos futuros.

Objetivo:
- convertir los percentiles de contexto de `reason_text` a ventanas trailing/expanding;
- impedir que reprocesar el histórico reescriba mensajes pasados;
- dejar un contrato verificable con tests de invariancia temporal.

Diagnostico:
el gate ya es causalmente limpio, pero la narrativa y parte del contexto de carga siguen pudiendo contaminarse con el futuro al recalcularse sobre todo el histórico disponible en cada corrida.

Alcance minimo:
- acotar los cuantiles de contexto a datos previos al dia evaluado;
- revisar cualquier fallback que dependa de la serie completa;
- añadir tests que comparen un run truncado contra el run completo en fechas anteriores al corte.

No objetivo:
- no tocar el gate HRV;
- no rehacer la capa de analisis;
- no convertir esta tarea en una revision general de todo `reason_text`.

Criterios de aceptacion:
1. Un run truncado no cambia el contexto histórico ya emitido.
2. Los cuantiles de contexto quedan documentados como trailing o expanding.
3. Existe al menos un test de invariancia temporal para la salida diaria.

Nota de desarrollo: este documento es la fuente unica de la tarea.
