# ENDURANCE HRV — Estructura de Datos

**Revisión:** r2026-02-23 v3 (v4 enhancement)  
**Estado:** Producción

**Documentos relacionados:**
- `ENDURANCE_HRV_Spec_Tecnica.md` — Fórmulas, algoritmos y reglas de cálculo
- `ENDURANCE_HRV_Diccionario.md` — Qué significa cada columna y cómo usarla

---

## Alcance y jerarquía

Este documento es el **contrato de datos** del sistema ENDURANCE HRV: define qué archivos genera el sistema, qué columnas tiene cada uno, en qué orden, qué tipo de dato contienen, y si pueden ser nulos.

- **No redefine lógica de cálculo** — para fórmulas y umbrales, la autoridad es `Spec_Tecnica.md`
- **No explica cómo interpretar las salidas** — para eso, la autoridad es `Diccionario.md`
- Si hay conflicto entre documentos, prevalece: Spec_Tecnica > Estructura > Diccionario

---

## 1. Archivos del sistema

El sistema genera 5 archivos CSV. Cada uno tiene un rol distinto y se genera por un script específico:

| Archivo | Para qué sirve | Lo genera | Columnas |
|---------|---------------|-----------|----------|
| `ENDURANCE_HRV_master_CORE.csv` | La medición fisiológica del día: pulso, variabilidad, calidad de señal. Sin ninguna decisión de entrenamiento. | `endurance_hrv.py` | 12 |
| `ENDURANCE_HRV_master_FINAL.csv` | El gate de entrenamiento, las sombras, el residual, el veto agudo, el reason_text y toda la auditoría necesaria para entender por qué el sistema tomó esa decisión. | `endurance_v4lite.py` | 53 |
| `ENDURANCE_HRV_master_DASHBOARD.csv` | Lo esencial para decidir en 10 segundos: semáforo, acción, warning, y reason_text contextual. Subconjunto de FINAL. | `endurance_v4lite.py` | 10 |
| `ENDURANCE_HRV_context.csv` | Datos contextuales externos: sueño (Polar) y carga de entrenamiento (Intervals.icu). Alimenta el reason_text pero NO afecta al gate. | `polar_hrv_automation.py` | 34 |
| `ENDURANCE_HRV_master_BETA_AUDIT.csv` | Modelo alométrico beta/cRMSSD del sistema V3. Se conserva para comparación histórica; no afecta al gate V4-lite. | `endurance_hrv.py` | 13 |

---

## 2. Reglas generales

Estas reglas aplican a los 5 archivos por igual:

- **Clave primaria:** `Fecha` (formato YYYY-MM-DD). Cada día solo puede tener una fila.
- **Sin duplicados:** si se reprocesa un día, la nueva fila sustituye a la anterior (upsert por Fecha).
- **Orden:** ascendente por Fecha (el día más antiguo arriba, el más reciente abajo).
- **Codificación:** UTF-8
- **Separador:** coma (CSV estándar)

**Nota sobre context.csv:** Este archivo puede tener más filas que CORE/FINAL, porque registra noches y actividades aunque no haya habido medición HRV ese día. Su clave primaria sigue siendo Fecha (sin duplicados).

---

## 3. CORE (canónico) — columnas y orden exacto

CORE contiene la señal fisiológica pura del día: lo que el sensor midió y cómo de fiable es esa medición. No incluye ninguna decisión de entrenamiento.

**Cabecera exacta (copiar literal):**

```
Fecha,Calidad,HRV_Stability,Artifact_pct,Tiempo_Estabilizacion,HR_stable,RRbar_s,RMSSD_stable,RMSSD_stable_last2,lnRMSSD,Flags,Notes
```

| # | Columna | Tipo | ¿Puede ser nulo? | Ejemplo | Qué es |
|---|---------|------|-------------------|---------|--------|
| 1 | Fecha | date | No | 2026-02-09 | Día de la medición matinal |
| 2 | Calidad | str | No | OK | Veredicto de usabilidad: OK / FLAG_mecánico / INVALID |
| 3 | HRV_Stability | str | No | OK | ¿El tramo final era estable? OK / Unstable |
| 4 | Artifact_pct | float | Sí | 3.45 | % de latidos descartados por artefactos |
| 5 | Tiempo_Estabilizacion | float | Sí | 90.0 | Segundos hasta que la señal se estabilizó. NaN si no se detectó. |
| 6 | HR_stable | float | Sí | 48.5 | Pulso medio en el tramo estable (lpm) |
| 7 | RRbar_s | float | Sí | 1.237 | Intervalo RR medio en el tramo estable (segundos) |
| 8 | RMSSD_stable | float | Sí | 52.3 | Variabilidad cardíaca del tramo completo (ms) |
| 9 | RMSSD_stable_last2 | float | Sí | 51.8 | Variabilidad de los últimos 120 s, para verificar estabilidad (ms) |
| 10 | lnRMSSD | float | Sí | 3.957 | Logaritmo natural de RMSSD_stable |
| 11 | Flags | str | Sí | LAT_NAN\|ART_GT10 | Incidencias detectadas, separadas por `\|` |
| 12 | Notes | str | Sí | src=...; dur_raw=... | Metadatos técnicos del procesamiento |

**Notas sobre formato:**
- `Flags`: vocabulario cerrado (ver Diccionario §7), valores separados por `|` (sin espacios)
- `Notes`: string determinista `clave=valor` separado por `; `, con claves mínimas: src + duraciones + conteos + desglose artefactos

---

## 4. FINAL (derivado) — columnas y orden exacto

FINAL es el archivo de auditoría completo: contiene la medición del día, el suavizado, los baselines, todos los gates, el veto agudo, el residual, la acción, la acumulación, los warnings y el reason_text contextual. Es el archivo donde puedes rastrear exactamente por qué el sistema tomó cada decisión.

**Cabecera exacta (copiar literal):**

```
Fecha,Calidad,HRV_Stability,Artifact_pct,Tiempo_Estabilizacion,HR_today,RMSSD_stable,lnRMSSD_today,lnRMSSD_used,HR_used,n_roll3,ln_base60,HR_base60,n_base60,SWC_ln,SWC_HR,d_ln,d_HR,gate_base60,gate_razon_base60,gate_shadow42,gate_razon_shadow42,n_base42,gate_shadow28,gate_razon_shadow28,n_base28,decision_mode,gate_final,gate_final_delta,decision_path,override_reason,residual_ln,residual_z,residual_tag,gate_badge,quality_flag,Color_operativo,Action,Action_detail,bad_streak,bad_7d,baseline60_degraded,healthy_rmssd,healthy_hr,healthy_period,flag_sistemico,flag_razon,warning_threshold,warning_mode,veto_agudo,ln_pre_veto,swc_ln_floor,reason_text
```

### Agrupación lógica

Las 53 columnas se organizan en 12 bloques lógicos. Cada bloque agrupa campos relacionados:

#### A) Identidad / medición base (8 cols)

Réplica de la medición de CORE. **Atención:** dos columnas tienen nombre distinto que en CORE (`HR_stable` → `HR_today`, `lnRMSSD` → `lnRMSSD_today`). Ver Diccionario §3 bloque A para detalle.

Columnas 1-8: `Fecha`, `Calidad`, `HRV_Stability`, `Artifact_pct`, `Tiempo_Estabilizacion`, `HR_today`, `RMSSD_stable`, `lnRMSSD_today`

#### B) Suavizado ROLL3 (3 cols)

Media móvil de los últimos 3 días clean. Es el valor suavizado que realmente se compara contra el baseline.

Columnas 9-11: `lnRMSSD_used`, `HR_used`, `n_roll3`

#### C) Baseline 60d + SWC (5 cols)

Tu "normal" reciente (mediana de 60 días) y el umbral de cambio mínimo significativo.

Columnas 12-16: `ln_base60`, `HR_base60`, `n_base60`, `SWC_ln`, `SWC_HR`

#### D) Deltas BASE60 (2 cols)

La distancia entre tu valor suavizado de hoy y tu baseline. Es lo que determina el color.

Columnas 17-18: `d_ln`, `d_HR`

#### E) Gate extendido (17 cols)

Todos los semáforos (BASE60 + sombras + decisión final + residual), con motivos y auditoría de override.

Columnas 19-35:
- BASE60: `gate_base60`, `gate_razon_base60`
- Sombra 42: `gate_shadow42`, `gate_razon_shadow42`, `n_base42`
- Sombra 28: `gate_shadow28`, `gate_razon_shadow28`, `n_base28`
- Decisión: `decision_mode`, `gate_final`, `gate_final_delta`, `decision_path`, `override_reason`
- Residual: `residual_ln`, `residual_z`, `residual_tag`, `gate_badge`

#### F) Calidad / color operativo (2 cols)

Flag de calidad dudosa y duplicado explícito del color final.

Columnas 36-37: `quality_flag`, `Color_operativo`

#### G) Acción (2 cols)

La instrucción de entrenamiento y su detalle (matizado por acumulación o quality_flag).

Columnas 38-39: `Action`, `Action_detail`

#### H) Acumulación (2 cols)

Racha y conteo de días malos. Cuando se acumulan, se activa DESCARGA.

Columnas 40-41: `bad_streak`, `bad_7d`

#### I) Warning baseline (4 cols)

Aviso a medio plazo si tu capacidad actual está por debajo de tu mejor momento.

Columnas 42-45: `baseline60_degraded`, `healthy_rmssd`, `healthy_hr`, `healthy_period`

#### J) Flags sistémicos (2 cols)

Reservado para información externa (sueño, enfermedad, viajes). Actualmente no se alimenta automáticamente.

Columnas 46-47: `flag_sistemico`, `flag_razon`

#### K) Parámetros warning (2 cols)

El umbral y el modo usados para calcular el warning de baseline degradado.

Columnas 48-49: `warning_threshold`, `warning_mode`

#### L) v4 Enhancement (4 cols)

Veto agudo (bypass de ROLL3 ante caídas bruscas) y texto explicativo contextual.

Columnas 50-53: `veto_agudo`, `ln_pre_veto`, `swc_ln_floor`, `reason_text`

| # | Columna | Tipo | ¿Puede ser nulo? | Ejemplo | Qué es |
|---|---------|------|-------------------|---------|--------|
| 50 | `veto_agudo` | bool | No | True | True si se detectó caída aguda de HRV que forzó bypass del suavizado ROLL3 |
| 51 | `ln_pre_veto` | float | Sí | 3.684 | Valor de lnRMSSD_used (ROLL3) antes de ser forzado a raw. NaN si no hubo veto |
| 52 | `swc_ln_floor` | float | Sí | 0.102 | SWC efectivo usado: max(SWC_ln, 0.04879). NaN si no se calculó base60 |
| 53 | `reason_text` | str | Sí | Caída aguda HRV \| Noche corta | Texto explicativo contextual. Vacío si no hay nada que reportar. Separador `\|` entre razones |

---

## 5. DASHBOARD (derivado) — columnas y orden exacto

DASHBOARD es un subconjunto de FINAL diseñado para consumo humano: lo que necesitas ver en 10 segundos para decidir qué hacer hoy. Sin auditoría, sin sombras individuales, sin residual detallado — solo lo esencial.

**Cabecera exacta (copiar literal):**

```
Fecha,Calidad,HR_today,RMSSD_stable,gate_badge,Action,gate_razon_base60,decision_path,baseline60_degraded,reason_text
```

| # | Columna | Tipo | Qué mirar |
|---|---------|------|-----------|
| 1 | Fecha | date | Día de la medición |
| 2 | Calidad | str | Primera parada: si es INVALID, ignora el resto |
| 3 | HR_today | float | Tu pulso matinal (para detectar anomalías de un vistazo) |
| 4 | RMSSD_stable | float | Tu variabilidad del día (referencia, no para comparar entre días) |
| 5 | gate_badge | str | **Tu semáforo** + matiz del residual (ej: VERDE+, ÁMBAR--, ROJO) |
| 6 | Action | str | **Qué hacer**: INTENSIDAD_OK / Z2_O_TEMPO_SUAVE / SUAVE_O_DESCANSO |
| 7 | gate_razon_base60 | str | Por qué salió ese color (2D_OK, 2D_LN, 2D_HR, 2D_AMBOS, etc.) |
| 8 | decision_path | str | Si hubo override por sombra. BASE60_ONLY = sin override |
| 9 | baseline60_degraded | bool | Warning a medio plazo (True si tu baseline está por debajo de tu referencia) |
| 10 | reason_text | str | Texto contextual: veto agudo, sueño malo, carga alta, divergencias. Vacío si no hay nada que reportar |

**Nota sobre lnRMSSD_today:** no se incluye en DASHBOARD (sigue estando en FINAL). Si se necesita, se puede derivar como `ln(RMSSD_stable)`.

---

## 6. CONTEXT (sidecar externo) — columnas y orden exacto

CONTEXT contiene datos de fuentes externas que el sistema HRV no mide directamente: sueño nocturno (Polar), carga de entrenamiento (Intervals.icu) y percentiles propios calibrados. Alimenta el `reason_text` en FINAL/DASHBOARD pero **NO afecta al cálculo del gate**. Si falta, el sistema funciona igualmente (solo pierde contexto textual).

**Cabecera exacta (copiar literal):**

```
Fecha,polar_sleep_duration_min,polar_sleep_span_min,polar_deep_pct,polar_rem_pct,polar_efficiency_pct,polar_continuity,polar_continuity_index,polar_interruptions_long,polar_interruptions_total,polar_sleep_score,polar_night_rmssd,polar_night_rri,polar_night_resp,intervals_load,intervals_load_max,intervals_intensity_max,intervals_type_main,intervals_duration_min,intervals_n_acts,intervals_avg_hr,intervals_max_hr,intervals_atl,intervals_ctl,intervals_tsb,intervals_rpe,intervals_resting_hr,intervals_load_3d,intervals_load_yday,sleep_dur_p10,sleep_dur_p90,sleep_int_p90,load_3d_p90,load_3d_median
```

### Agrupación lógica

Las 34 columnas se organizan en 4 bloques:

#### Polar Sleep (13 cols)

| Columna | Tipo | Qué es |
|---------|------|--------|
| `polar_sleep_duration_min` | float | Minutos de sueño real (asleep, sin interrupciones) |
| `polar_sleep_span_min` | float | Minutos totales en cama (incluye despertares) |
| `polar_deep_pct` | float | % de sueño profundo (N3) |
| `polar_rem_pct` | float | % de sueño REM |
| `polar_efficiency_pct` | float | Eficiencia: asleep / span × 100 |
| `polar_continuity` | int | Clase de continuidad (1-5, Polar) |
| `polar_continuity_index` | float | Índice de continuidad (Polar) |
| `polar_interruptions_long` | int | **Conteo** de interrupciones largas (≠ duración). P90 típico ≈ 8 |
| `polar_interruptions_total` | int | Conteo total de interrupciones (largas + cortas) |
| `polar_sleep_score` | float | Score de sueño Polar (0-100). Solo disponible con Nightly Recharge |
| `polar_night_rmssd` | float | RMSSD nocturno medio (ms). Solo con Nightly Recharge |
| `polar_night_rri` | float | RRI nocturno medio (ms). Solo con Nightly Recharge |
| `polar_night_resp` | float | Intervalo respiratorio nocturno (ms). Solo con Nightly Recharge |

#### Intervals.icu carga (13 cols)

| Columna | Tipo | Qué es |
|---------|------|--------|
| `intervals_load` | float | Carga total del día (sum de todas las actividades). 0 = día de descanso |
| `intervals_load_max` | float | Carga de la sesión más pesada del día |
| `intervals_intensity_max` | float | Intensidad máxima entre sesiones del día |
| `intervals_type_main` | str | Tipo de actividad de la sesión principal (la de mayor load) |
| `intervals_duration_min` | float | Duración total en minutos (sum de todas las actividades) |
| `intervals_n_acts` | int | Número de actividades registradas ese día |
| `intervals_avg_hr` | float | FC media ponderada de las sesiones |
| `intervals_max_hr` | float | FC máxima del día (max entre sesiones) |
| `intervals_atl` | float | Acute Training Load (fatiga reciente, Intervals.icu) |
| `intervals_ctl` | float | Chronic Training Load (fitness, Intervals.icu) |
| `intervals_tsb` | float | Training Stress Balance = CTL - ATL. Negativo = fatiga |
| `intervals_rpe` | float | RPE reportado (si existe) |
| `intervals_resting_hr` | float | FC reposo del día (de Intervals.icu, si existe) |

#### Carga derivada (2 cols)

| Columna | Tipo | Qué es |
|---------|------|--------|
| `intervals_load_3d` | float | Sum de load de los 3 días anteriores (d-1 + d-2 + d-3). NO incluye hoy |
| `intervals_load_yday` | float | Load de ayer (d-1). Útil para detectar "ROJO sin carga previa" |

#### Percentiles propios (5 cols)

| Columna | Tipo | Qué es |
|---------|------|--------|
| `sleep_dur_p10` | float | Percentil 10 de duración de sueño (noches con dato). Debajo = noche corta |
| `sleep_dur_p90` | float | Percentil 90 de duración de sueño |
| `sleep_int_p90` | float | Percentil 90 de interrupciones largas. Encima = noche fragmentada |
| `load_3d_p90` | float | Percentil 90 de load_3d (excluyendo días de descanso) |
| `load_3d_median` | float | Mediana de load_3d |

**Notas:**
- Los percentiles se recalculan con **todo** el histórico disponible cada vez que se hace append. Son globales (mismo valor en todas las filas).
- Context puede tener más filas que FINAL: registra noches y actividades aunque no haya medición HRV.
- Si Polar Sleep API falla → campos `polar_*` quedan NaN. Si Intervals API falla → campos `intervals_*` quedan NaN. El pipeline no se aborta.

---

## 7. BETA_AUDIT (legacy) — columnas y orden exacto

BETA_AUDIT conserva el modelo alométrico beta/cRMSSD del sistema V3 para comparación histórica. **No afecta al gate V4-lite.** Las primeras 5 columnas replican datos de CORE con los mismos nombres.

**Cabecera exacta (copiar literal):**

```
Fecha,HR_stable,RRbar_s,RMSSD_stable,lnRMSSD,cRMSSD,beta_mode,beta_est_90d,beta_use_90d,R2_winsor_90d,Color_Agudo_Diario,Color_Tendencia,Color_Tiebreak
```

| # | Columna | Tipo | Qué es |
|---|---------|------|--------|
| 1 | Fecha | date | Día de la medición |
| 2 | HR_stable | float | Pulso (réplica de CORE) |
| 3 | RRbar_s | float | RR medio (réplica de CORE) |
| 4 | RMSSD_stable | float | Variabilidad (réplica de CORE) |
| 5 | lnRMSSD | float | ln de RMSSD (réplica de CORE) |
| 6 | cRMSSD | float | RMSSD corregido por beta (descuenta el efecto del pulso) |
| 7 | beta_mode | str | Estado del modelo: active / clipped / frozen / none |
| 8 | beta_est_90d | float | Beta estimado con los últimos 90 días |
| 9 | beta_use_90d | float | Beta realmente usado (puede diferir por clipping/freezing) |
| 10 | R2_winsor_90d | float | Calidad del ajuste (R² de la regresión winsorizada) |
| 11 | Color_Agudo_Diario | str | Color diario del sistema V3 (solo referencia) |
| 12 | Color_Tendencia | str | Color de tendencia del V3 (solo referencia) |
| 13 | Color_Tiebreak | str | Color de desempate del V3 (solo referencia) |

---

## 8. Diagrama de dependencias

Muestra qué entra y qué sale de cada script, y cómo se encadenan:

```
                    RR_*.csv
                    (intervalos latido-a-latido del sensor)
                       │
                       ▼
               ┌───────────────┐
               │ endurance_hrv │  Procesa RR crudo → métricas del día
               └───────────────┘
                   │       │
                   ▼       ▼
              CORE.csv   BETA_AUDIT.csv
              (medición)  (modelo beta V3)
                   │
                   ▼
           ┌──────────────────┐      CONTEXT.csv
           │ endurance_v4lite │ ◄─── (sueño + carga, solo para reason_text)
           └──────────────────┘
                   │
           ┌───────┴───────┐
           ▼               ▼
      FINAL.csv      DASHBOARD.csv
      (auditoría,     (operativo,
       53 cols)        10 cols)

  Polar Sleep API ──┐
  Polar Nightly  ───┤
                    ├──► CONTEXT.csv (34 cols)
  Intervals.icu ────┘    (sueño + carga + percentiles)
```

---

## 9. Validación de integridad

Tests que deben pasar después de cada procesamiento para garantizar que los archivos son correctos:

### CORE

```python
assert df["Fecha"].is_unique                                          # sin duplicados
assert df["Fecha"].notna().all()                                      # siempre hay fecha
assert df["Calidad"].isin(["OK", "FLAG_mecánico", "INVALID"]).all()   # vocabulario cerrado
assert df["HRV_Stability"].isin(["OK", "Unstable"]).all()             # vocabulario cerrado
```

### FINAL

```python
assert df["Fecha"].is_unique                                                           # sin duplicados
assert df.shape[1] == 53                                                               # schema v4
assert df["gate_final"].isin(["VERDE", "ÁMBAR", "ROJO", "NO"]).all()                 # vocabulario cerrado
assert df["Action"].isin(["INTENSIDAD_OK", "Z2_O_TEMPO_SUAVE", "SUAVE_O_DESCANSO"]).all()
assert df["warning_mode"].isin(["healthy85", "p20"]).all()
assert "veto_agudo" in df.columns                                                      # v4 columns present
assert "reason_text" in df.columns
assert df["reason_text"].dtype == object                                                # string type

# Consistencia veto: si veto activo, lnRMSSD_used == lnRMSSD_today
veto = df[df["veto_agudo"] == True]
for _, row in veto.iterrows():
    if pd.notna(row["lnRMSSD_today"]):
        assert abs(row["lnRMSSD_used"] - row["lnRMSSD_today"]) < 0.001
```

### DASHBOARD

```python
assert df.shape[1] == 10                                                               # schema v4
assert "reason_text" in df.columns
```

### CONTEXT

```python
assert ctx["Fecha"].is_unique                                                           # sin duplicados
assert ctx.shape[1] == 34                                                               # schema fijo
# Percentiles son globales (mismo valor en todas las filas)
assert ctx["sleep_dur_p10"].nunique() <= 1
assert ctx["load_3d_p90"].nunique() <= 1
# polar_interruptions_long es conteo (no duración), valores típicos 0-15
if ctx["polar_interruptions_long"].notna().any():
    assert ctx["polar_interruptions_long"].max() < 50  # sanity: no es duración en minutos
```

### Consistencia CORE ↔ FINAL

```python
# Mismas fechas en ambos archivos
assert set(core["Fecha"]) == set(final["Fecha"])

# RMSSD_stable coincide (es el mismo valor, copiado)
merged = core.merge(final, on="Fecha")
assert (merged["RMSSD_stable_x"] == merged["RMSSD_stable_y"]).all()
```

---

## 10. QA mínimo obligatorio (anti-bugs)

Verificaciones periódicas que complementan los tests automáticos de §8. Se ejecutan manualmente o en script de QA.

### QA unidades

Detecta errores de conversión o bugs silenciosos:
- `HR_stable ≈ 60 / RRbar_s` (error relativo ≤ 0.1%)
- `RRbar_s` típico 0.8–1.6 s; HR supina típica 45–60 lpm

### QA señal / mecánica

Monitoriza la calidad general de las mediciones:
- % de días INVALID, % FLAG_mecánico, % HRV_Stability=Unstable
- Top 20 días por Artifact_pct y por Tiempo_Estabilizacion (detectar sensor problemático o banda suelta)

### QA gate V4-lite

Verifica que la distribución de gates tiene sentido:
- Distribución de gate_final (VERDE/ÁMBAR/ROJO/NO) y gate_badge
- max(bad_streak), días con bad_7d ≥ 3 (detectar rachas inusualmente largas)
- % baseline60_degraded = True

### QA β (si usas BETA_AUDIT)

- Distribución de beta_mode (clip_rate = % capado) y distribución de `|ln_corr|`
- Top 10 días por `|ln_corr|` (detectar correcciones extremas)

### Plantilla fija de informes QA (obligatorio, anti-deriva)

Los informes QA deben seguir **siempre** esta estructura mínima. Si una sección no aplica, incluirla con "Sin incidencias / no aplica".

**QA_global (Markdown):**

| Sección | Contenido |
|---------|-----------|
| 0. Cobertura | Rango de fechas, número total de días |
| 1. Calidad | Tabla OK / FLAG_mecánico / INVALID con conteos y % |
| 2. INVALID | Lista de días INVALID con causa |
| 3. FLAG_mecánico | Lista de días FLAG con flags activados |
| 4. Sanity checks | HR, Artifact_pct, Latencia dentro de rangos |
| 5. Flags | Conteo de cada flag STAB_* y BETA_* |
| 6. Top outliers | Días con RMSSD, HR o artefactos extremos |
| 7. Distribución gate | VERDE/ÁMBAR/ROJO/NO con % |

**QA_beta (Markdown):**

| Sección | Contenido |
|---------|-----------|
| 0. Cobertura | Rango y completitud |
| 1. beta_mode | Distribución active/clipped/frozen/none |
| 2. Calidad 90d | Distribución de R² |
| 3. \|ln_corr\| | Distribución de la corrección aplicada |
| 4. Top 10 \|ln_corr\| | Días con corrección más grande |
| 5. Incidencias | Periodos con none/frozen |

---

## 11. Resultado práctico (cómo se usa cada día)

Secuencia de lectura rápida del DASHBOARD:

### Paso 1: Gate de fiabilidad

Mirar `Calidad`:
- **INVALID** → día perdido, no decidir por HRV
- **FLAG / Unstable** → prudencia. El gate se calcula pero la acción se fuerza a SUAVE

### Paso 2: Semáforo y acción

Mirar `gate_badge` y `Action`:
- **VERDE + INTENSIDAD_OK** → ejecutar plan previsto (intervalos, sesión dura, lo que toque)
- **ÁMBAR + Z2_O_TEMPO_SUAVE** → sin HIIT, pero Z1-Z2 permitido
- **ROJO/NO + SUAVE_O_DESCANSO** → mirar `Action_detail` para decidir si regenerativo o descarga total

### Paso 3: Contexto (v4)

Si `reason_text` no está vacío:
- Explica **por qué** el sistema tomó esa decisión y qué factores contextuales hay (sueño malo, carga acumulada, caída aguda de HRV, divergencias gate↔carga)
- No cambia el gate ni la acción, pero informa decisiones

### Paso 4: Warning (informativo)

Si `baseline60_degraded = True`:
- Tu capacidad actual está por debajo de tu mejor momento conocido
- No cambia el gate del día, pero considerar en decisiones semanales de progresión (no es momento de subir carga)

---

## 12. Migración desde V3

Si tienes el archivo monolítico del sistema anterior (`ENDURANCE_HRV_master_ALL.csv`):

```bash
# 1. Ejecutar migración (separa ALL en los 4 archivos nuevos)
python endurance_migrate.py --master-all ENDURANCE_HRV_master_ALL.csv

# 2. Verificar que DASHBOARD contiene los datos esperados
head -5 ENDURANCE_HRV_master_DASHBOARD.csv

# 3. Archivar el archivo monolítico (no borrar, por seguridad)
mkdir legacy
mv ENDURANCE_HRV_master_ALL.csv legacy/

# 4. Mover archivos intermedios con sufijos de fecha
mv *_20260209*.csv legacy/

# 5. A partir de aquí, usar los scripts nuevos para cada día
python endurance_hrv.py --rr-file rr_downloads/nuevo_RR.csv
python endurance_v4lite.py
```

---

Fin del documento.
