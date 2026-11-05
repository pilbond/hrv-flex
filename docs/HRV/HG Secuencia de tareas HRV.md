# Secuencia de tareas HG (HRV)

Estado comprobado el 2026-11-01 con `python canvas-tool.py Project.canvas status` y `show`. `Project.canvas` gobierna el estado de las tarjetas; esta nota resume dependencias y alcance técnico. No autoriza por sí misma un corte canónico.

| Tarjeta | Kanvas | Entrega y relación con HG-10 |
|---|---|---|
| HG-03 y HG-04 | `green` | Procedencia de RR y helper de pares preparados; geometría 90 s + corte máximo 375 s investigada como candidato. Ningún CSV canónico migrado. |
| HG-05 y HG-06 | `green` | Descartes en ventana y referencia ECG documentados. HG-05 entrega la definición de `Artifact_pct` con registro cortado y recuentos descriptivos opcionales. |
| HG-09 | `green` | Decisión final: conservar la exclusión de `LAT_NAN` y `STAB_LAST2_MISMATCH` de referencias, y la cautela de acción. La evaluación prospectiva de `MISMATCH` permanece abierta sin bloquear HG-10. |
| HG-10 | `orange` | Dependencias HG-03 y HG-09 satisfechas. Candidato implementado y replay en copias; ningún corte canónico publicado. Pendientes decisión sobre geometría/pares, decisión separada sobre `LAT_NAN` y migración verificada. Véase la [nota de HG-10](<HG-10 Corte historico y contrato de pares consecutivos.md>). |
| HG-07 y HG-08 | `purple` | Reconstrucción RR en sombra y detector ECG en origen. Son evaluaciones independientes y no bloquean la decisión sobre geometría/pares de HG-10. |

La secuencia de trabajo de HG-10 es: fijar definiciones y casos insuficientes; implementar y probar en ambas rutas de CORE; ejecutar replay histórico en copia aislada; revisar efectos en derivados y contratos; preparar una publicación controlada y recuperable. La geometría candidata usa inicio a 90 s, corte de registro a 375 s y recorte final de 15 s, de modo que el tramo útil habitual termina cerca de 360 s. La regla de Calidad de HG-09 se conserva.

Los ensayos y las decisiones rectificadas permanecen en las notas de [HG-03](<RR_PARES_CONSECUTIVOS_TAREA.md>), [HG-04](<HG-04 Ventana de calculo de RMSSD_stable y revision de estabilizacion.md>), [HG-05](<HG-05 Auditoria de deteccion de latidos y calidad de senal en ventana.md>) y [HG-09](<HG-09 Politica de Calidad HRV para ventana 90-375 s.md>). Las tablas antiguas de colores y orden se retiraron de esta nota para que no compitan con Kanvas.
