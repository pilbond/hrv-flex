# HG-05: descartes RR dentro de la ventana de medición

**Estado 2026-10-27:** cerrada (`green` en Kanvas) tras revisión humana. *(Antes: terminada por el agente, pendiente de revisión, `cyan`.)* La medición descriptiva y sus traspasos están documentados; no se ha añadido una columna ni cambiado Calidad en producción.

> **Reorganización 2026-10-27.** El contenido anterior de esta nota (auditoría de 41 días, mecanismo de `detect_rpeaks()`, alcance de HG-06/HG-07/HG-08, casos de referencia y criterios comunes) se conserva íntegro en la [nota de HG-07/HG-08](<HG-07 HG-08 Reconstruccion RR y detector ECG en origen.md>). La secuencia de tareas está en [Secuencia de tareas HG](<HG Secuencia de tareas HRV.md>).

## 1. Qué quedaba de HG-05

Tras separar HG-06, HG-07 y HG-08, a HG-05 solo le quedaba una entrega: un porcentaje **descriptivo** de RR descartados dentro de la ventana de medición (`rejected_rr_pct_window`). La motivación era que, con el inicio adaptativo, la mitad de los descartes de los días auditados caía fuera del tramo medido y `Artifact_pct`, calculado sobre todo el registro, no describía la ventana (§1.2 de la nota de HG-07/HG-08).

## 2. Resultado de la comprobación (2026-10-27)

Medición post hoc, sin protocolo previo, sobre 507 fechas de CORE con la geometría candidata de HG-04 (inicio 90 s, registro cortado a 375 s). La réplica del filtro reproduce el `Artifact_pct` de CORE en las 507 fechas. Detalle, script y tablas: [informe](../../research/reports/hg05_ventana_vs_global_375_2026-10-27.md).

- El 36,5% de los descartes cae antes de 90 s; el 60,4% dentro de la ventana; el 3,2% en la cola recortada.
- En los 45 días con más del 3%, global y ventana ordenan los días casi igual (ρ de rangos 0,94).
- La elección global/ventana cambia la clasificación por umbral en **3 de 507 días**, todos de la era ECG (2026-03-30, 2026-04-20 y 2026-06-10). Ningún día supera un umbral en ventana sin superarlo en global.
- **El propio corte a 375 s** hace que seis días crucen un umbral del `Artifact_pct` global, al reducir el denominador. Tres pasan de `OK` a no `OK` (2026-03-21, 2026-04-15 y 2026-04-20) y tres pasan a `INVALID` (2026-06-10, 2026-06-15 y 2026-07-12). Ya figuraba en HG-04 §15.1.

## 3. Conclusión y traspasos

- **Medido:** con 90 s + 375 s, el hueco que motivó HG-05 casi desaparece por el cambio de geometría.
- **Inferencia (~75%):** la métrica en ventana tendría valor descriptivo y de auditoría, pero un efecto muy pequeño en decisiones. No justifica una tarea propia.
- **Traspaso a HG-10** ([nota vigente](<HG-10 Corte historico y contrato de pares consecutivos.md>)). Precisar `Artifact_pct` global del registro cortado a 375 s y contrastar los cruces de umbral medidos; mantener separado el porcentaje descriptivo de descartes en la ventana. Publicar este último solo si existe un consumidor concreto, con la definición auditable de §4. Cualquier cambio de umbrales requiere decisión propia.
- **Traspaso a HG-09** ([nota](<HG-09 Politica de Calidad HRV para ventana 90-375 s.md>)): el dato de los 3/507 días como contexto. La revisión de los umbrales del 15%/20% sigue condicionada a HG-07/HG-08.

## 4. Definición propuesta anteriormente (antecedente)

Texto movido sin cambios desde la nota anterior (§4, «HG-05 — descartes dentro de la ventana fija de HG-04»):

Tras fijar la ventana de HG-04, añadir una métrica **descriptiva** de descartes en ella. Definición propuesta: denominador = número de RR originales con tiempo final dentro de la **ventana adoptada** `[inicio, fin]`; numerador = número de esos RR originales excluidos por `offline`, rango o delta-RR según la precedencia vigente. Contar cada RR una sola vez. Publicar ambos recuentos y `rejected_rr_pct_window` para que se pueda auditar el porcentaje. Si hay duraciones inválidas que vuelvan incierto el eje temporal, devolver faltante y flag explícito. Documentar la convención exacta de los límites de ventana y probarla. El ejemplo anterior `[180,360]` no es una definición vigente.

`Artifact_pct` conserva su definición histórica global. Si HG-07 se activa, exponer de forma separada los candidatos reparados y, si aporta valor, un porcentaje posterior a la reparación; no sobreescribir silenciosamente el porcentaje global. `rejected_rr_pct_window` mide **descartes del algoritmo** en la ventana, no calidad eléctrica confirmada ni anomalías que el filtro dejó pasar.

La primera entrega de esta métrica **no altera `Calidad` ni el gate**. Antes de considerar sustituir los umbrales globales del 15%/20%, comparar sensibilidad, especificidad frente a ECG donde exista, reclasificación histórica, baselines y decisiones. Los siete ejemplos `OK` de ventana aparentemente limpia muestran utilidad descriptiva, pero ya eran `OK` y no justifican por sí solos un cambio de gate. Toda modificación de QA o esquema exige actualizar `docs/contracts/` antes de activarse.
