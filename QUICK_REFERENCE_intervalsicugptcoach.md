# Quick Reference: intervalsicugptcoach Components

**Cheat sheet** para reutilización rápida de componentes clave

---

## 🎯 Top 5 Prioridades

| # | Componente | Fuente | Ubicación | Esfuerzo | Valor |
|:--|:--|:--|:--|:--|:--|
| 1️⃣ | **HRV Normalization** | `tier2_derived_metrics.py` | líneas 17–99 | 2h | ALTO |
| 2️⃣ | **Wellness Coverage Audit** | `tier2_derived_metrics.py` | líneas 150–200 | 1h | ALTO |
| 3️⃣ | **ACWR/Strain Metrics** | `tier2_derived_metrics.py` | líneas 300–450 | 4h | ALTO |
| 4️⃣ | **Energy System Phases** | `tier3_espe.py` | whole file | 6h | MEDIO |
| 5️⃣ | **JSON Semantic Builder** | `semantic_json_builder.py` | whole file | 3h | MEDIO |

---

## 📦 Copy-Paste Ready Functions

### normalise_hrv()
```python
# Source: C:\Pilbond\Endurance External Projects\intervalsicugptcoach-public\
#         tier2_derived_metrics.py::normalise_hrv() (lines 17–99)
#
# Usage:
from analysis.hrv_normalisation import normalise_hrv
hrv_normalized = normalise_hrv(hrv_value=45.2, source="Polar")
#
# Supports: Whoop, Oura, Apple, Fitbit, Polar, Garmin
# Output: standardized RMSSD (ms)
```

### compute_wellness_coverage()
```python
# Source: tier2_derived_metrics.py::compute_wellness_coverage()
#
# Usage:
coverage = compute_wellness_coverage(df_wellness, window_days=7)
#
# Returns: {
#   "hrv_pct": 85,
#   "resthr_pct": 70,
#   "sleep_pct": 100,
#   "subjective_pct": 45,
#   "composite": 75,
#   "assessment": "Good"  # Good|Fair|Poor
# }
```

### derive_acwr()
```python
# Source: tier2_derived_metrics.py::derive_acwr()
#
# Usage:
acwr = derive_acwr(df_activities, window_acute=7, window_chronic=28)
#
# Returns: float in [0.6, 2.0]
# Safe range: 0.8–1.3
# Overtraining: >1.5
```

### detect_training_phase()
```python
# Source: tier3_espe.py::detect_training_phase()
#
# Usage:
phase = detect_training_phase(df_activities, df_wellness)
#
# Returns: {
#   "phase": "Base|Build|Peak|Taper|Recovery",
#   "duration_days": 42,
#   "next_phase_eta": "2026-04-15",
#   "adaptation_state": "Adaptive|Stable|Maladaptive"
# }
```

### build_semantic_json()
```python
# Source: semantic_json_builder.py::build_semantic_json()
#
# Usage:
report_json = build_semantic_json(
    df_activities=df_sessions,
    df_wellness=df_sleep,
    athlete_profile=athlete,
    metrics=computed_metrics,
    window_start="2026-03-17",
    window_end="2026-03-23"
)
#
# Returns: URF v5.1 compliant dict with 10 sections
```

---

## 🔗 Architecture Map

```
┌─ normalise_hrv() + compute_wellness_coverage()
│  (Validate inputs)
│
├─ derive_acwr(), derive_strain(), derive_polarisation()
│  (Compute Tier-2 metrics)
│
├─ detect_training_phase()
│  (Detect ESPE phase)
│
├─ compute_wdrm(), compute_isdm(), compute_ndli()
│  (Compute Tier-3 Performance Intelligence)
│
├─ generate_actions()
│  (Coaching actions from heuristics)
│
└─ build_semantic_json()
   (Structure output as JSON URF v5.1)
```

---

## 📋 Files to Copy (minimal)

```bash
# MUST HAVE
tier2_derived_metrics.py              # extract: normalise_hrv,
                                      # compute_wellness_coverage,
                                      # derive_acwr/strain/polarisation

# SHOULD HAVE
tier3_espe.py                         # detect_training_phase, adapt_phase
coaching_heuristics.py                # HEURISTICS dict
coaching_cheat_sheet.py               # classification thresholds
semantic_json_builder.py              # build_semantic_json

# NICE TO HAVE
tier3_performance_intelligence.py     # compute_wdrm, compute_isdm, compute_ndli
tier2_actions.py                      # generate_actions
report_schema_guard.py                # validate_schema
```

---

## 🧬 Integration Points

### 1. HRV Normalization (Tier-0/1)
```python
# In: build_hrv_core.py
# Before RR processing
from analysis.hrv_normalisation import normalise_hrv
df_wellness['hrv_normalized'] = df_wellness['hrv'].apply(
    lambda x: normalise_hrv(x, source='Polar')
)
```

### 2. Wellness Coverage (Tier-2)
```python
# In: build_hrv_final_dashboard.py
# Pre-veto check
coverage = compute_wellness_coverage(df_wellness, window_days=14)
if coverage['composite'] < 0.6:
    logger.warning(f"Low wellness coverage: {coverage['composite']:.0%}")
    veto_confidence *= coverage['composite']  # reduce confidence
```

### 3. Derived Metrics (Tier-2)
```python
# In: build_hrv_final_dashboard.py
# Pre-veto computation
acwr = derive_acwr(df_sessions_day, window_acute=7, window_chronic=28)
strain = derive_strain(df_sessions_day)
polarisation = derive_polarisation(df_sessions_day)

# Use in veto logic
if acwr > 1.3 and hrv_low:
    veto = True  # overtraining signal confirmed
    reason += f"; ACWR {acwr:.2f} >1.3 signals overtraining"
```

### 4. Training Phase Detection (Tier-3)
```python
# In: build_hrv_final_dashboard.py
# Post-veto, pre-actions
phase = detect_training_phase(df_sessions_day, df_wellness)
if phase['phase'] == 'Taper':
    veto = veto and 0.5  # relax veto during taper
```

### 5. JSON Output (Render)
```python
# In: build_hrv_final_dashboard.py or new endpoint
report_json = build_semantic_json(
    df_activities=df_sessions_day,
    df_wellness=df_wellness,
    athlete_profile={'name': 'Athlete', 'ftp': 285, ...},
    metrics={'acwr': 1.12, 'strain': 2850, ...},
    window_start=date_start,
    window_end=date_end
)

# Output in web_ui.py
@app.get('/api/report')
def get_report():
    return report_json  # JSON client-friendly
```

---

## 🧮 Metric Thresholds (from coaching_cheat_sheet.py)

```python
# ACWR (Acute:Chronic Work Ratio)
ACWR_SAFE_MIN = 0.8
ACWR_SAFE_MAX = 1.3
ACWR_CAUTION = 1.5
# Action: if >1.3 and hrv_low → veto

# STRAIN (Foster)
STRAIN_ALERT = 3500
# Action: if >3500 for 3+ days → recommend ease

# MONOTONY (Foster)
MONOTONY_ALERT = 2.5
# Action: if >2.5 → add intensity variation

# POLARISATION (Seiler 80/20)
POLARISATION_TARGET = 0.8  # 80% Z1-Z2
POLARISATION_ACCEPTABLE_MIN = 0.7
POLARISATION_ACCEPTABLE_MAX = 0.9
# Action: if <0.7 → too much Z3; increase Z1-Z2

# HRV RECOVERY INDEX
RECOVERY_INDEX_OPTIMAL = 0.8
RECOVERY_INDEX_FATIGUED = 0.6
# Action: if <0.6 and veto_pending → confirm veto

# WELLNESS COVERAGE
COVERAGE_MINIMUM = 0.6  # 60%
COVERAGE_GOOD = 0.9    # 90%
# Action: if <0.6 → reduce veto confidence
```

---

## 📚 Documentation to Read

1. **intervalsicugptcoach/README.md** — Visión general (10 min)
2. **intervalsicugptcoach/docs/Unified Reporting Framework.md** — Especificación URF v5.1 (20 min)
3. **intervalsicugptcoach/docs/coach_framework-map.md** — Frameworks (Seiler, Banister, Foster) (20 min)
4. **intervalsicugptcoach/all-modules.md** — Load order + dependencies (10 min)
5. **intervalsicugptcoach/ANALYSIS_intervalsicugptcoach_MAPPING.md** — This repo's integration guide (30 min)

---

## ⚡ Quick Start (1 hour)

```bash
# 1. Create branch
git checkout -b feature/intervalsicugptcoach-integration

# 2. Create module skeleton
mkdir -p analysis/hrv_extended
touch analysis/hrv_extended/__init__.py
touch analysis/hrv_extended/normalisation.py
touch analysis/hrv_extended/metrics.py
touch analysis/hrv_extended/heuristics.py

# 3. Copy normalise_hrv()
# From: C:\Pilbond\Endurance External Projects\intervalsicugptcoach-public\
#       tier2_derived_metrics.py (lines 17–99)
# To:   analysis/hrv_extended/normalisation.py

# 4. Test import
python -c "from analysis.hrv_extended.normalisation import normalise_hrv; print('✅ OK')"

# 5. Integrate in build_hrv_core.py
# Add: from analysis.hrv_extended.normalisation import normalise_hrv
# Use: df_wellness['hrv_norm'] = df_wellness['hrv'].apply(normalise_hrv)

# 6. Test pipeline
python build_hrv_core.py

# 7. Commit & PR
git add analysis/hrv_extended/
git commit -m "feat: add vendor-agnostic HRV normalization from intervalsicugptcoach"
git push origin feature/intervalsicugptcoach-integration
```

---

## 🔍 Key Files Location (intervalsicugptcoach-public)

```
C:\Pilbond\Endurance External Projects\intervalsicugptcoach-public\
├── tier2_derived_metrics.py          ← COPY normalise_hrv, compute_wellness_coverage, derive_*
├── tier3_espe.py                     ← COPY detect_training_phase
├── tier3_performance_intelligence.py ← COPY compute_wdrm, isdm, ndli
├── semantic_json_builder.py          ← COPY build_semantic_json
├── coaching_heuristics.py            ← REFERENCE thresholds
├── coaching_cheat_sheet.py           ← REFERENCE classifications
├── report_schema_guard.py            ← COPY validate_schema
├── tier2_actions.py                  ← REFERENCE action patterns
└── docs/
    ├── Unified Reporting Framework.md    ← READ schema
    └── coach_framework-map.md            ← READ frameworks
```

---

## 🎓 Expected Outcomes

After integrating:

✅ HRV normalization vendor-agnostic (Whoop, Oura, Polar, etc.)
✅ Wellness coverage audit (% HRV/sleep/mood completeness)
✅ Derived metrics (ACWR, Strain, Polarisation) in FINAL.csv
✅ Training phase detection (Base/Build/Peak/Taper/Recovery)
✅ JSON semantic output for dashboards + downstream systems
✅ Structured coaching actions with framework justification
✅ Improved veto confidence scoring

---

**Last updated**: 2026-03-25
**Next review**: When intervalsicugptcoach-public changes significantly
