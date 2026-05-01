## SYA-09 SYA-03F Fase 6 Alineacion del weekly report

Auditar impacto de SYA-04/05/06 sobre weekly report: revisar uso de nuevas columnas de sessions.csv, decidir exclusion o inclusion explicita de analysis_only_context/coaching sidecars en semanal, validar si trimp y nuevas senales cambian lectura semanal, y actualizar WEEKLY_ANALYSIS_METHOD/guia asociada sin mezclar contrato de sesion con contrato semanal.

Documento maestro: [[docs/HRV/SYA-03 Inventario y analisis ampliado de intervalsicugptcoach.md]]

## Análisis técnico 2026-04-23

### Estado actual del código
- `analysis/WEEKLY_ANALYSIS_METHOD.md` (contract_version 0.2-draft, 573 líneas) define fuentes, ventanas y estructura semanal pero **no menciona** `trimp`, `session_rpe`, `analysis_only_context`, `wellness_subjective` ni señales compuestas SYA-07 (verificado con grep: 0 matches).
- Fuentes primarias documentadas en `WEEKLY_ANALYSIS_METHOD.md:73-81`: incluyen `sessions_day.csv`, `sessions.csv`, `intensity_distribution_weekly.csv`, FINAL, DASHBOARD, CORE, sleep. No incluye `wellness_subjective.csv` ni artefactos de `analysis/reports/<slug>/artifacts/`.
- Columnas canonizadas Fase 1 (`trimp`, `decoupling`, `icu_weighted_avg_watts`, `icu_joules_above_ftp`, `icu_max_wbal_depletion`) ya en `sessions.csv` (`build_sessions.py:2142-2149`) pero el método semanal todavía apunta solo a `load_day`, `work_total_min_day`, `z3_min_day` (`:196-201`).
- `analysis/reports/weekly/` tiene solo 2 informes de ejemplo; el método está vivo pero la práctica aún es escasa.

### Valor actual
- Valor alto y **concreto**: hoy el weekly report ignora `trimp` y las primitivas validadas de SYA-05, lo que crea asimetría entre contrato de sesión (ya consolidado) y contrato semanal (congelado en v0.2).
- La decisión binaria clave es si `trimp` entra como segunda lectura de carga semanal junto a `load`, o si se descarta por correlación casi perfecta con `load` (`0.996` según SYA-05).

### Errores/riesgos
- Riesgo de mezclar contratos: colar `subjective_coherence` o `analysis_only_context` en weekly convertiría el sidecar analytical en señal operativa sin validación longitudinal, violando el marco SYA-03 8.1.
- Riesgo de duplicar señales: añadir `trimp_week` cuando `load_week` ya lo cubre (correlación 0.996) genera ruido contractual sin valor incremental.
- `wellness_subjective.csv` (RE-02) es sidecar retrospectivo sin decisión explícita sobre su rol semanal; puede tentar a usarse como insumo semanal antes de validar.

### Mejoras propuestas
1. Auditoría binaria de cada columna nueva de `sessions.csv` contra weekly: tabla {columna, decisión (incluir/excluir/referenciar), motivo}. Campos a auditar: `trimp`, `decoupling`, `icu_weighted_avg_watts`, `icu_joules_above_ftp`, `icu_max_wbal_depletion`.
2. Decidir explícitamente el estado de `analysis_only_context` y `wellness_subjective.csv` en el contrato semanal; recomendación: **excluir** ambos del contrato semanal canónico (permanecen como contexto opcional citable pero no fuente primaria).
3. Actualizar `WEEKLY_ANALYSIS_METHOD.md` sección 5 (Fuentes) y 8.2 (Carga) con el resultado de la auditoría; subir `contract_version` a `0.3`.
4. Redactar regla explícita de separación: "weekly report MUST NOT consumir `analysis_only_context` como insumo primario; solo puede citarlo como contexto de sesión ejemplar".
5. Valorar si `durability_day` o `subjective_coherence_day` (si llegan a canonizarse en SYA-08) entran al esqueleto semanal; hoy decir **no** hasta que SYA-08 cierre.

### Conclusión
Tarea con valor alto y ejecutable de inmediato: es principalmente un trabajo de contrato documental, no de código. El weekly report está desfasado respecto a SYA-04/05/06 y la asimetría empieza a notarse. Priorizar decisión sobre `trimp` (probablemente excluir por redundancia con `load`) y cerrar explícitamente que `analysis_only_context`/`wellness_subjective` quedan fuera del contrato semanal.
