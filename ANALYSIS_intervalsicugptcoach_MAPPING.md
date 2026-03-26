# Análisis de Reutilización: intervalsicugptcoach-public → polar-hrv-automation_railway_v4

**Fecha**: 2026-03-25
**Scope**: Identificar componentes reutilizables del framework Intervals.icu Coach para mejorar polar-hrv-automation v4

---

## RESUMEN EJECUTIVO

**intervalsicugptcoach-public** es un **motor de auditoría determinista** con:
- 7 tiers de validación de datos (Tier-0 → Tier-3)
- 40+ métricas derivadas (ACWR, Strain, Monotony, Polarisation, Performance Intelligence)
- Framework de reporting estructurado (Unified Reporting Framework v5.1)
- Integración Intervals.icu + frameworks científicos (Seiler, Banister, Foster, San Millán, Skiba, Friel, Noakes, Mujika)
- Mapping de acciones coaching adaptativas basadas en reglas

**Intersección con polar-hrv-automation_railway_v4**:
- ✅ Normalización HRV vendor-agnostic
- ✅ Integración Intervals.icu (ya parcialmente implementada en `build_sessions.py`)
- ✅ Frameworks de reporting estructurado (complementa `FINAL.csv` + `DASHBOARD.csv`)
- ✅ Lógica de acciones coaching (complementa `reason_text` en veto HRV)
- ✅ Wellness coverage tracking (complementa sesiones + sleep)

---

## 1. COMPONENTES REUTILIZABLES POR PRIORIDAD

### PRIORIDAD ALTA ✅✅✅

#### 1.1 HRV Normalization (tier2_derived_metrics.py::normalise_hrv())
**Líneas**: 17–99
**Función**: Detecta device de HRV (Whoop, Oura, Apple, Fitbit, Polar, Garmin) y normaliza a escala RMSSD estándar

```python
def normalise_hrv(hrv_value: float, source: str = "unknown") -> float:
    """
    Normaliza HRV a estándar RMSSD (ms) independiente de vendor.

    Mapeos conocidos:
    - Whoop: recovery_score × 1.2
    - Oura: rmssd (ms, directo)
    - Apple: no expose directo; infer desde VO₂max
    - Fitbit: hrv_balance_score × 0.8
    - Polar: rmssd (ms, directo)
    - Garmin: lastNight5MinuteValues (promedio)
    """
```

**Fit para polar-hrv-automation**:
- Actualmente `build_hrv_final_dashboard.py` asume HRV es RMSSD directo
- Copiar/adaptar `normalise_hrv()` → permitir que Polar nativo + otros vendors se normalicen
- **Ubicación de inserción**: `build_hrv_core.py` o nuevo módulo `hrv_normalisation.py` en `analysis/`

**Línea de acción**:
```bash
1. Copiar tier2_derived_metrics.py::normalise_hrv() → analysis/hrv_normalisation.py
2. Adaptar para Polar ECG.jsonl + ACC.jsonl + raw streams
3. Integrar en build_hrv_core.py antes de procesamiento RR
4. Documental en docs/contracts/ENDURANCE_HRV_Diccionario.md
```

---

#### 1.2 Wellness Coverage Tracking (tier2_derived_metrics.py::compute_wellness_coverage())
**Líneas**: 150–200 (aprox.)
**Función**: Calcula % cobertura HRV, restHR, sleep, subjective por ventana temporal

```python
wellness_coverage = {
    "hrv_pct": 85,       # % días con HRV válido
    "resthr_pct": 70,
    "sleep_pct": 100,
    "subjective_pct": 45,
    "composite": 75,     # media ponderada
    "assessment": "Good",  # Good|Fair|Poor
}
```

**Fit para polar-hrv-automation**:
- `FINAL.csv` + `DASHBOARD.csv` incluyen campos: `RR_quality`, `sleep_available`, etc.
- Standardizar con `compute_wellness_coverage()` → auditar completeness de datos
- Útil para `reason_text` en veto HRV: "⚠️ HRV coverage 60%; recommend 7 more days before veto"

**Línea de acción**:
```bash
1. Copiar tier2_derived_metrics.py::compute_wellness_coverage() → analysis/
2. Adaptar para schema ENDURANCE_HRV_sleep.csv (17 cols) + sessions_day.csv
3. Agregar output a FINAL.csv como `wellness_coverage_pct`, `wellness_assessment`
4. Usar en veto_logic: si coverage <60%, flag como "pending_data"
```

---

#### 1.3 Energy System Progression (ESPE) Detection (tier3_espe.py)
**Líneas**: ~300 total
**Función**: Detecta fases de entreno (Base, Build, Peak, Taper, Recovery) basado en load trends + intensidad + subjective signals

```python
energy_system_progression = {
    "phase": "Base",  # Base|Build|Peak|Taper|Recovery
    "status": "Developing",
    "duration_days": 42,
    "next_phase_eta": "2026-04-15",
    "aerobic_dominance": 0.82,  # 0–1
    "intensity_bias": "Aerobic",  # Aerobic|Balanced|Anaerobic
    "adaptation_state": "Adaptive",  # Adaptive|Stable|Maladaptive
}
```

**Fit para polar-hrv-automation**:
- `FINAL.csv` incluye `rollback_cycles`, `training_phase` (puede complementarse)
- Mapear HRV-veto → fases ESPE:
  - Base: recuperación de veto → mantener Z2
  - Build: veto activo → reducir umbral ROLL3
  - Peak: veto muy estricto → priorizar reposo
  - Taper: veto débil → permitir sesiones breves

**Línea de acción**:
```bash
1. Copiar tier3_espe.py → analysis/energy_system_progression.py
2. Adaptar inputs: usar ENDURANCE_HRV_sessions_day.csv + sleep.csv
3. Agregar lógica: si fase == "Taper" Y HRV bajo → "recommend_maintain_taper"
4. Output: `training_phase`, `phase_eta`, `adaptation_state` → FINAL.csv
```

---

#### 1.4 Derived Metrics Core (tier2_derived_metrics.py)
**Métricas clave**: ACWR, Strain, Monotony, Polarisation, Recovery Index, Durability, FatOxIdx, Consistency

**Fit para polar-hrv-automation**:
- `CORE.csv` (18 cols) calcula RR-based metrics
- `FINAL.csv` (58 cols) complementa con contexto
- Podrías agregar 6–8 métricas derivadas de Intervals.icu (si sincronizadas sesiones):
  - ACWR (Acute/Chronic Work Ratio)
  - Strain (monotony × load)
  - Polarisation (% Z1-Z2 vs Z3-Z7)
  - Recovery Index
  - Durability Index (power consistency)

**Línea de acción**:
```bash
1. Copiar tier2_derived_metrics.py::derive_acwr(), derive_strain(), derive_polarisation()
2. Adaptar inputs: ENDURANCE_HRV_sessions_day.csv (TSS, intensity) en lugar de df_activities
3. Calcular en build_hrv_final_dashboard.py ANTES de veto logic
4. Uso: ACWR >1.3 → potenciar veto HRV; ACWR <0.8 → relajar veto
5. Output: agregar columnas a FINAL.csv
```

---

### PRIORIDAD MEDIA ✅✅

#### 2.1 Performance Intelligence Tier (tier3_performance_intelligence.py)
**Subfunción**: WDRM (W′ Repeatability), ISDM (Intensity-Specific Durability), NDLI (Neural Density Load Index)

```python
performance_intelligence = {
    "training_state": "Productive",  # Productive|HighStrain|Overreached
    "wdrm": {
        "value": 18.5,  # kJ depletion
        "pattern": "repeated",  # single|repeated|progressive|stochastic
        "engagement": "moderate",  # light|moderate|heavy
    },
    "isdm": {
        "value": 0.91,  # 0–1, durabilidad
        "trend": "improving",
    },
    "ndli": {
        "value": 0.82,  # clustering de high-intensity
        "saturation": "moderate",
    },
}
```

**Fit para polar-hrv-automation**:
- W′ (energía anaeróbica) está en `CORE.csv` si hay RR
- Podrías calcular WDRM + ISDM para sesiones sincronizadas desde Intervals.icu
- NDLI útil para detectar "high-intensity clustering fatigue" → complementar veto HRV

**Línea de acción**:
```bash
1. Si Intervals.icu sessions sincronizadas (build_sessions.py ya lo hace):
   - Copiar tier3_performance_intelligence.py::compute_wdrm(), compute_isdm(), compute_ndli()
   - Adaptar inputs: ENDURANCE_HRV_sessions.csv + power data
2. Output: agregar `training_state`, `wdrm_pattern` a FINAL.csv
3. Uso: training_state == "Overreached" → veto HRV muy estricto
```

---

#### 2.2 Semantic JSON Builder (semantic_json_builder.py)
**Función**: Construir JSON semántico compatible con Unified Reporting Framework v5.1

```python
def build_semantic_json(
    df_activities, df_wellness, athlete_profile,
    metrics, window_start, window_end
) -> dict:
    """Retorna dict con estructura URF v5.1"""
    return {
        "meta": {...},
        "training_volume": {...},
        "metrics": {...},
        "daily_load": [...],
        "events": [...],
        "wellness": {...},
        "performance_intelligence": {...},
        "energy_system_progression": {...},
        "actions": [...],
        "future_forecast": {...},
    }
```

**Fit para polar-hrv-automation**:
- Actual: outputs son CSV tabular + Markdown ad-hoc
- Potencial: generar JSON estructurado → dashboards, APIs, downstream systems
- Reutilizable para "HRV Weekly Report JSON" → compatible con web_ui.py

**Línea de acción**:
```bash
1. Crear `analysis/hrv_semantic_json_builder.py` basado en semantic_json_builder.py
2. Schema HRV especifico (reducido vs URF completo):
   {
     "meta": {...},
     "hrv_metrics": {
       "mean": ...,
       "trend": ...,
       "coverage": ...,
       "veto_flags": [...]
     },
     "sleep_summary": {...},
     "rr_quality": {...},
     "actions": ["increase_recovery", ...],
     "dashboard_summary": {...}
   }
3. Integrar en web_ui.py: GET /api/status → JSON semántico + CSV exports
```

---

#### 2.3 Report Schema Guard (report_schema_guard.py)
**Función**: Validar JSON output contra schema URF v5.1; QA determinista

```python
def validate_report_schema(report_json: dict) -> dict:
    """Retorna {"valid": True/False, "errors": [...], "warnings": [...]}"""
```

**Fit para polar-hrv-automation**:
- Actual: QA es ad-hoc (gating rules en veto_logic)
- Potencial: validar FINAL.csv/DASHBOARD.csv contra schema
- Útil para CI/CD en Railway

**Línea de acción**:
```bash
1. Crear `analysis/hrv_schema_guard.py` con schema ENDURANCE_HRV_master_FINAL.csv
2. Validar:
   - All required columns present
   - Data types correctos (float, int, datetime)
   - Ranges: ROLL3 in [0–1], veto_flag in [0–1], reason_text length <256
3. Usar en build_hrv_final_dashboard.py post-execution:
   if not validate_schema(df_final):
       raise SchemaValidationError("FINAL.csv schema violation")
```

---

### PRIORIDAD BAJA ✅

#### 3.1 Coaching Actions (tier2_actions.py + tier3_adaptive_decision_engine.py)
**Función**: Generar recomendaciones coaching basadas en métricas + frameworks

```python
actions = [
    {
        "type": "load_management",
        "priority": "high",
        "recommendation": "Reduce TSS by 15% next week",
        "rationale": "ACWR 1.45 exceeds 1.3 threshold; Strain 3800 >3500",
    },
    {
        "type": "recovery",
        "priority": "medium",
        "recommendation": "Add 1 rest day or 2 easy spins",
        "rationale": "HRV ↓ 18%; Sleep avg 6.2h (<7h target)",
    },
]
```

**Fit para polar-hrv-automation**:
- Actual: `reason_text` en FINAL.csv es descriptivo (ej. "HRV low, sleep <6.5h")
- Potencial: formalizar acciones → JSON estructurado
- Usar frameworks (Seiler, Banister, etc.) para justificar

**Línea de acción**:
```bash
1. Adaptar tier2_actions.py heuristics → HRV veto domain:
   if hrv_low AND load_high AND sleep_low:
       actions.append({
           "type": "recovery",
           "priority": "high",
           "recommendation": "Reduce next session to Z2 (60 min max)",
           "rationale": "HRV ↓ 22% from baseline; ATL rising; sleep 6h",
       })
2. Salida: actions → FINAL.csv::reason_text (formalizado)
3. Web UI: GET /api/actions → JSON actions array
```

---

#### 3.2 Future Forecast (tier3_future_forecast.py)
**Función**: Proyectar CTL, ATL, TSB para 7/14/28 días

```python
future_forecast = {
    "7d": {
        "ctl_projected": 145,
        "atl_projected": 92,
        "tsb_projected": 53,
        "forecast_confidence": 0.82,
    },
    "14d": {...},
    "28d": {...},
}
```

**Fit**: Complementar `forecast_reason`, predicciones de veto HRV futuro

**Línea de acción**: Baja prioridad; implementar post-v1

---

## 2. PATRONES ARQUITECTÓNICOS REUTILIZABLES

### 2.1 Tier Architecture Pattern
**intervalsicugptcoach**: Tier-0 (fetch) → Tier-1 (validate) → Tier-2 (compute) → Tier-3 (intelligence)

**Mapeo a polar-hrv-automation**:
```
build_hrv_core.py                    ≈ Tier-0 (fetch RR) + Tier-1 (validate)
build_hrv_final_dashboard.py         ≈ Tier-2 (compute metrics + veto) + Tier-3 (actions)
```

**Mejora**: Formalizar tiers como módulos independientes:
```python
# analysis/tier0_rr_fetch.py
def fetch_and_normalise_rr(date_range):
    """Fetch RR desde Dropbox/Polar; normaliza a arrays"""

# analysis/tier1_rr_validate.py
def validate_rr_integrity(df_rr, df_ecg, df_acc):
    """Audita RR: duplicados, outliers, cobertura"""

# analysis/tier2_hrv_compute.py
def compute_hrv_metrics(df_rr):
    """Calcula CORE.csv: RMSSD, SDNN, LF/HF, veto flags"""

# analysis/tier3_hrv_intelligence.py
def compute_hrv_intelligence(df_core, df_wellness, df_sessions):
    """Calcula FINAL.csv: reason_text, actions, energy_phase"""
```

---

### 2.2 Heuristics-Based Decision Engine
**intervalsicugptcoach**: coaching_heuristics.py + coaching_cheat_sheet.py define thresholds

**Mapeo a polar-hrv-automation**:
Formalizar veto_logic como heuristics:
```python
# analysis/hrv_heuristics.py
HEURISTICS = {
    "rr_coverage_min": 0.6,     # %
    "rr_quality_threshold": 0.8,
    "sleep_target_hours": 7,
    "sleep_deficit_alert": 6.5,
    "hrv_baseline_window": 14,  # días
    "hrv_drop_threshold": 0.2,  # 20% below baseline
    "roll3_floor_swc": 2.0,     # SWC multiplier
    "acwr_safe_range": (0.8, 1.3),
    "strain_alert": 3500,
    "monotony_alert": 2.5,
}

def evaluate_veto(hrv_latest, baseline, load, sleep, rr_coverage):
    """Retorna (veto_flag, confidence, reason)"""
    if rr_coverage < HEURISTICS["rr_coverage_min"]:
        return (None, 0.3, "Insufficient RR data")
    if hrv_latest < baseline * (1 - HEURISTICS["hrv_drop_threshold"]):
        return (True, 0.9, f"HRV drop {hrv_latest/baseline:.0%}")
    ...
```

---

### 2.3 Framework Mapping
**intervalsicugptcoach**: docs/coach_framework-map.md mapea frameworks (Seiler, Banister, Foster, etc.)

**Mapeo a polar-hrv-automation**:
Crear `docs/contracts/FRAMEWORKS_HRV.md`:
```markdown
# Frameworks Aplicables a HRV Veto

## Seiler 80/20 Polarisation
- Aplicable: distribuir sesiones Z1–Z2 vs Z3+
- HRV integration: si HRV bajo + Monotony >2.5 → aumentar % Z2

## Banister Fitness-Fatigue Model
- Aplicable: CTL/ATL balance
- HRV integration: si TSB >+60 (muy fresco) Y HRV alto → permitir sesión high-intensity
- HRV integration: si TSB <-40 (muy fatigado) Y HRV bajo → veto estricto

## Foster Monotony Model
- Aplicable: variación de intensidad diaria
- HRV integration: Monotony >2.5 + HRV bajo → força alternancia Z1/Z3

## Noakes Central Governor
- Aplicable: HRV como proxy de CNS fatiga
- HRV integration: HRV ↓ 25% + RPE ↑ 20% → veto CNS-driven
```

---

## 3. PLAN DE INTEGRACIÓN RECOMENDADO

### Fase 1: Setup Modular (1–2 semanas)
```bash
# Crear estructura tier-based
mkdir -p analysis/tier0_tier1_tier2_tier3/
touch analysis/tier0_rr_fetch.py
touch analysis/tier1_rr_validate.py
touch analysis/tier2_hrv_compute.py
touch analysis/tier3_hrv_intelligence.py
touch analysis/hrv_heuristics.py
touch analysis/hrv_normalisation.py
touch analysis/hrv_semantic_json_builder.py
touch analysis/hrv_schema_guard.py
touch docs/contracts/FRAMEWORKS_HRV.md

# Refactorizar build_hrv_core.py → tier0 + tier1 + tier2
# Refactorizar build_hrv_final_dashboard.py → tier2 + tier3
```

### Fase 2: HRV Normalisation (1 semana)
```bash
1. Copiar normalise_hrv() → analysis/hrv_normalisation.py
2. Adaptar para Polar ECG.jsonl + ACC.jsonl + streams
3. Integrar en build_hrv_core.py pre-processing
4. Test: múltiples fuentes Polar, validar rango de salida
5. Documentar en ENDURANCE_HRV_Diccionario.md
```

### Fase 3: Metrics Derivadas (2 semanas)
```bash
1. Copiar ACWR/Strain/Polarisation logic → tier2_hrv_compute.py
2. Adaptar inputs: ENDURANCE_HRV_sessions_day.csv (si Intervals.icu sincronizado)
3. Calcular en build_hrv_final_dashboard.py pre-veto
4. Usar en veto_logic: ACWR >1.3 → potenciar veto
5. Output: agregar 6 columnas a FINAL.csv
6. Test: validar contra Intervals.icu reports (cross-check)
```

### Fase 4: JSON Semántico (2 semanas)
```bash
1. Crear hrv_semantic_json_builder.py (schema reducido vs URF)
2. Integrar en build_hrv_final_dashboard.py post-execution
3. Servir en web_ui.py GET /api/status → JSON + CSV
4. Dashboard web: consumir JSON semántico
5. Test: validar schema contra guard rules
```

### Fase 5: Acciones & Heuristics (2 semanas)
```bash
1. Formalizar veto_logic → hrv_heuristics.py
2. Copiar tier2_actions.py → hrv_actions.py
3. Generar acciones coaching basadas en métricas + frameworks
4. Output: actions array → reason_text + JSON
5. Web UI: GET /api/actions → acciones estructuradas
```

### Fase 6: Frameworks Documentados (1 semana)
```bash
1. Documentar FRAMEWORKS_HRV.md con mappings Seiler/Banister/Foster
2. Justificar cada heuristic con referencias científicas
3. Agregar a AGENTS.md como guía operativa
```

---

## 4. FICHEROS ESPECÍFICOS A COPIAR/ADAPTAR

| Origen | Destino | Función | Esfuerzo |
|:--|:--|:--|:--|
| `tier2_derived_metrics.py::normalise_hrv()` | `analysis/hrv_normalisation.py` | HRV vendor-agnostic | 2h |
| `tier2_derived_metrics.py::compute_wellness_coverage()` | `analysis/hrv_coverage.py` | Auditoría completeness | 1h |
| `tier2_derived_metrics.py::derive_acwr/strain/polarisation()` | `analysis/tier2_hrv_compute.py` | Métricas derivadas | 4h |
| `tier3_espe.py` | `analysis/tier3_energy_system.py` | Detección de fases | 6h |
| `tier3_performance_intelligence.py::compute_wdrm/isdm/ndli()` | `analysis/tier3_hrv_intelligence.py` | PI metrics | 4h |
| `semantic_json_builder.py` | `analysis/hrv_semantic_json_builder.py` | JSON URF-like | 3h |
| `report_schema_guard.py` | `analysis/hrv_schema_guard.py` | Validación QA | 2h |
| `tier2_actions.py` | `analysis/hrv_actions.py` | Acciones coaching | 3h |
| `coaching_heuristics.py` | `analysis/hrv_heuristics.py` | Thresholds HRV | 2h |
| `docs/coach_framework-map.md` | `docs/contracts/FRAMEWORKS_HRV.md` | Documentación frameworks | 3h |

**Esfuerzo total estimado**: 30 horas (4–5 semanas a part-time)

---

## 5. CASOS DE USO CONCRETOS

### UC1: Veto HRV mejorado con ACWR
```python
# Antes
if hrv < baseline * 0.8:
    veto = True

# Después (con ACWR from intervalsicugptcoach)
acwr = compute_acwr(sessions_7d, sessions_28d)
if hrv < baseline * 0.8:
    if acwr > 1.3:  # overtraining signal
        veto = True
    elif acwr < 0.8:  # undertraining signal
        veto = False  # permit session for stimulation
    else:
        veto = True_conservative  # veto débil
```

### UC2: reason_text contextualizado con frameworks
```python
# Antes
reason_text = "HRV low (42ms), sleep 6h"

# Después (con frameworks + heuristics)
reason_text = """
HRV ↓ 18% from baseline (42 vs 51ms).
Sleep deficit 1h (6h vs 7h target).
Strain 3200 approaching alert (3500).
→ Banister ATL high; recommend Z2-only tomorrow, 60min max.
→ Monitor monotony (currently 2.3); add variety next week.
Confidence: 87% (coverage 14/15 days).
"""
```

### UC3: Dashboard con JSON semántico
```json
{
  "meta": {
    "window": "2026-03-17 to 2026-03-23",
    "athlete": "Francisco",
    "confidence": 0.87
  },
  "hrv_metrics": {
    "mean": 46,
    "baseline": 51,
    "trend": -9.8,  # %
    "coverage": 14/15,
    "source": "Polar"
  },
  "sleep_summary": {
    "mean_hours": 6.8,
    "target_hours": 7,
    "deficit_total": 1.4
  },
  "veto_flags": [
    {
      "date": "2026-03-23",
      "veto": true,
      "confidence": 0.92,
      "primary_signal": "HRV_low",
      "secondary_signals": ["sleep_deficit", "strain_high"],
      "reason": "..."
    }
  ],
  "actions": [
    {
      "type": "recovery",
      "priority": "high",
      "recommendation": "Z2-only, 60min max, next 2 days",
      "framework": "Banister_fitness_fatigue",
      "rationale": "..."
    }
  ]
}
```

---

## 6. RIESGOS & MITIGACIÓN

| Riesgo | Impacto | Mitigación |
|:--|:--|:--|
| Incompatibilidad schema Intervals.icu | Alto | Usar adapter pattern; mantener compat backwards |
| Complejidad aumentada (Tier-3 intensive) | Medio | Implementar fase a fase; prioritizar Tier-0/Tier-1/Tier-2 |
| Performance (múltiples tiers × múltiples métricas) | Medio | Cachear outputs intermedios; lazy-evaluate Tier-3 |
| Breaking changes en build_hrv_*.py | Alto | Branch separada (v4.1); test exhaustivo antes merge |
| Documentación desactualizada | Bajo | Mantener CLAUDE.md, AGENTS.md, contracts/ al día |

---

## 7. RESUMEN & SIGUIENTES PASOS

**intervalsicugptcoach-public** ofrece una **arquitectura probada y modular** para:
1. ✅ Normalizar HRV (vendor-agnostic)
2. ✅ Calcular métricas derivadas (ACWR, Strain, Polarisation)
3. ✅ Detectar fases entreno (ESPE)
4. ✅ Performance Intelligence (WDRM, ISDM, NDLI)
5. ✅ Generar acciones coaching basadas en reglas + frameworks científicos
6. ✅ Reportar JSON semántico + Markdown

**Recomendación**:
- **Corto plazo (v4.1)**: Integrar HRV normalization + Wellness Coverage (2 semanas)
- **Mediano plazo (v4.2)**: Agregar métricas derivadas + JSON builder (4 semanas)
- **Largo plazo (v4.3+)**: Performance Intelligence + Adaptive Actions (6+ semanas)

**Punto de partida**:
1. Leer `intervalsicugptcoach/AGENTS.md` + `README.md`
2. Estudiar `tier2_derived_metrics.py` (core logic)
3. Crear rama `feature/intervalsicugptcoach-integration`
4. Implementar Fase 1 (Setup Modular) + Fase 2 (HRV Normalisation)
5. PR pequeño, merge, iterate

---

**Documento preparado por**: Claude Code Agent
**Alcance**: Mapping reutilización intervalsicugptcoach → polar-hrv-automation_railway_v4
**Validez**: Vigente hasta cambios mayores en intervalsicugptcoach repo (próxima revisión: 2026-06-25)
