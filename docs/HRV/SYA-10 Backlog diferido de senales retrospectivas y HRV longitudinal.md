## SYA-10 SYA-03G Backlog diferido de senales retrospectivas y HRV longitudinal

Agrupar propuestas valiosas que han quedado fuera del alcance inmediato de SYA-07/08/09: HRV rebound profile D+1/D+3 como lectura retrospectiva, baseline drift 60v180 o baseline adaptativo de largo plazo, continuidad aeróbica Z1 alta si se redefine bien en el marco de 3 zonas, y otras ideas que no encajan hoy ni como senal compuesta de sesion ni como weekly operativo. Esta subtarea SI puede: clasificar, reformular y decidir destino natural (weekly, HRV global, investigacion local) de cada idea diferida. Esta subtarea NO puede: colar estas ideas en analysis_only_context, sessions_day, FINAL o reason_text sin validacion y sin actualizar antes el marco maestro en SYA-03. Cierre obligatorio: dejar backlog diferido limpio y trazable en SYA-03 con criterio de reactivacion.

Documento maestro: [[docs/HRV/SYA-03 Inventario y analisis ampliado de intervalsicugptcoach.md]]

## Análisis técnico 2026-04-23

### Estado actual del código
- Ninguna de las señales del backlog está implementada. Grep sobre el repo: `HRV_rebound`, `baseline_drift`, `z3_budget`, `60v180` solo aparecen en `Project.canvas` y en el MD maestro SYA-03. Cero ocurrencias en código Python.
- Existe ya tarea relacionada: `docs/HRV/Baseline adaptativo a largo plazo.md` (tarjeta separada) — posible colisión/alineación con "baseline drift 60v180".
- Existe tarjeta relacionada `docs/HRV/El umbral SWC puede ser demasiado estrecho.md` que toca la misma capa HRV global.
- SYA-03 8.1 (`:1086-1090`) ya marcó explícitamente: HRV rebound profile → weekly/retrospectivo; baseline drift 60v180 → HRV global separada; z3 budget → weekly.

### Valor actual
- Valor como **backlog disciplinado**: evita que ideas prometedoras se cuelen camufladas en `analysis_only_context` o `reason_text` sin validación.
- Valor bajo como implementación inmediata; valor alto como gobernanza y trazabilidad para no perder ideas pero tampoco ejecutarlas precipitadamente.
- El trabajo real de cada ítem del backlog probablemente vive en tarjetas separadas futuras (una por señal), no en ésta.

### Errores/riesgos
- Riesgo de convertir esta tarjeta en un saco sin criterio de reactivación claro: sin condiciones binarias para sacar una idea del backlog, queda varada.
- Colisión con `Baseline adaptativo a largo plazo.md`: hay que decidir si "baseline drift 60v180" es la misma tarjeta o diferente.
- Riesgo de ampliar alcance: añadir aquí cualquier idea nueva que aparezca en revisiones externas convierte la tarjeta en ruido.

### Mejoras propuestas
1. Estructurar el backlog en tabla con columnas: `idea | capa destino natural (weekly/HRV global/analysis local) | dependencia | criterio de reactivación | tarjeta destino propuesta`.
2. Ítems iniciales a clasificar:
   - **HRV rebound profile D+1/D+3** → capa weekly o sidecar retrospectivo; criterio reactivación: cuando SYA-09 cierre y haya sitio natural en weekly.
   - **baseline drift 60v180** → HRV global; verificar colisión con `Baseline adaptativo a largo plazo.md` y consolidar.
   - **continuidad aeróbica Z1 alta** → sidecar weekly per-sport; criterio: cuando SYA-08 consolide distribución longitudinal por deporte.
   - **z3 budget semanal** → weekly operativo; criterio: tras cierre SYA-09.
   - **TSB/form score clásico** → descartar explícitamente (SYA-03 `:1092-1093` ya lo marcó como redundante).
3. Regla explícita: al cerrar cualquier ítem como tarjeta nueva, eliminar fila del backlog y dejar link cruzado.
4. Actualizar SYA-03 bloque "Plantilla obligatoria de trazabilidad" (`:1147`) con referencia al backlog diferido y su política de reactivación.

### Conclusión
Tarea útil como gobernanza, ejecutable de inmediato y de bajo esfuerzo (es documental). El valor no está en implementar sino en **no olvidar** ideas sin dejarlas colarse prematuramente. Recomendación: ejecutarla justo después de cerrar SYA-08 y SYA-09, porque varios ítems del backlog tendrán entonces destino natural más claro. Verificar colisión con `Baseline adaptativo a largo plazo.md` antes de escribir la tabla final.
