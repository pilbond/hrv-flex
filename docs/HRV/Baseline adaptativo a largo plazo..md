
El `healthy_period` está fijado en `2025-07-01..2025-09-30`. Los RMSSD de ese periodo (~50-55) son los más altos del dataset. Ahora que el atleta se ha estabilizado en feb-mar 2026 con RMSSD ~30-35, el sistema sigue comparando contra ese periodo ideal. Resultado: el atleta lleva **meses en baseline60_degraded=True** y muchos VERDE aparecen como "VERDE---" porque su nivel actual es significativamente más bajo que su mejor momento.

**Mejora propuesta:** Implementar un **baseline adaptativo a largo plazo**. Si el atleta lleva >60 días estable en un nuevo rango (feb-mar: RMSSD 30-40 consistentemente), el baseline debería recalibrarse. Opciones:

- Resetear `healthy_period` automáticamente cuando hay 60+ días OK consecutivos con CV <15%
- Usar un baseline running de 90 días en vez del periodo fijo
- Escala dual: mantener el "historical best" como referencia pero usar el "current normal" para el gate diario
  
> Nota histórica: esta nota describe el problema antes de `PCV-02`. Desde `2026-05-13`, la solución canónica ya separa `degraded_vs_best` y `degraded_vs_current_normal`, manteniendo `baseline60_degraded` como alias legacy.
