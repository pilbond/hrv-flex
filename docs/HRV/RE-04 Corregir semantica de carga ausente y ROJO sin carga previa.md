
Separar descanso real de ausencia de datos y evitar que el mismo dia de carga se use para explicar una decision matinal.

Objetivo:
- hacer que `load_day` ausente no se lea como cero sin contexto;
- revisar el mensaje "ROJO sin carga previa" para que use una señal realmente previa, no carga del mismo dia;
- exigir cobertura suficiente antes de emitir cautelas de carga.

Diagnostico:
el sistema ya detecta la ausencia de carga previa en el discurso, pero la semantica actual puede confundir `missing` con `0` y puede usar una carga del mismo dia para explicar una decision tomada antes.

Alcance minimo:
- gatear mensajes de carga con `load_*_nobs`;
- preferir `load_3d` o contexto estrictamente previo para los mensajes explicativos;
- degradar a "carga no disponible" cuando falte cobertura real.

No objetivo:
- no cambiar el gate HRV;
- no cambiar la definicion de `sessions_day.csv`;
- no mover toda la capa de carga fuera de `FINAL`.

Criterios de aceptacion:
1. Un dia sin sesiones no se interpreta como carga cero salvo que el contrato lo diga explícitamente.
2. El mensaje de ROJO usa una carga realmente previa y con cobertura valida.
3. Los mensajes de carga con `nobs` insuficiente no se emiten como hechos.

Nota de desarrollo: este documento es la fuente unica de la tarea.
