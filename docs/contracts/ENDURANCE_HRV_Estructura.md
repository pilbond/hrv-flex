# ENDURANCE HRV — Estructura de Datos

**Revisión:** r2026-03-19 v3.3 (FINAL 58 cols + naming SLEEP + guía DASHBOARD corregida)  
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

### Alcance del contrato

Este contrato está definido para **uso personal de un solo atleta**.

- No modela multiusuario, multiatleta ni multi-tenant.
- La clave primaria `Fecha` se entiende dentro del histórico de ese único atleta.
- Cuando se describen percentiles o agregados "globales", significa "calculados sobre todo el histórico disponible del mismo atleta", no sobre varios usuarios.
- No se introducen campos para particionado por atleta, tenant, owner o cuenta salvo cambio de alcance explícito.

Si algún día se quisiera soportar varios atletas, este documento tendría que versionarse de nuevo porque cambiarían claves, persistencia, contratos de entrada/salida y supuestos de la UI.

---

## 1. Archivos del sistema

El sistema genera 7 archivos CSV + 1 JSON de trazabilidad. Cada uno tiene un rol distinto y se genera por un script específico:

| Archivo | Para qué sirve | Lo genera | Columnas |
|---------|---------------|-----------|----------|
| `ENDURANCE_HRV_master_CORE.csv` | La medición fisiológica del día: pulso, variabilidad, calidad de señal y trazabilidad mínima de estabilidad. Sin ninguna decisión de entrenamiento. | `endurance_hrv.py` | 18 |
| `ENDURANCE_HRV_master_FINAL.csv` | El gate de entrenamiento, las sombras, el residual, el veto agudo, el reason_text y la auditoría raw-vs-ref necesaria para entender qué hizo el sistema con los datos inestables. | `endurance_v4lite.py` | 58 |
| `ENDURANCE_HRV_master_DASHBOARD.csv` | Lo esencial para decidir en 10 segundos: semáforo, acción, warning, y reason_text contextual. Subconjunto de FINAL. | `endurance_v4lite.py` | 10 |
| `ENDURANCE_HRV_sleep.csv` | Sueño nocturno y señales de recuperación (Polar). Alimenta el reason_text pero NO afecta al gate. | `polar_hrv_automation.py` | 17 |
| `ENDURANCE_HRV_sessions.csv` | Detalle de cada sesión de entrenamiento: zonas, work blocks, drift, effort, clasificación. | `build_sessions.py` | 43 |
| `ENDURANCE_HRV_sessions_day.csv` | Agregados diarios de entrenamiento + rolling con cobertura (_nobs). Alimenta el reason_text para checks de carga. | `build_sessions.py` | 40 |
| `ENDURANCE_HRV_sessions_metadata.json` | Trazabilidad del pipeline de sesiones: versión, parámetros, hash, sampling rate, cobertura. | `build_sessions.py` | — |
| `ENDURANCE_HRV_master_BETA_AUDIT.csv` | Modelo alométrico beta/cRMSSD del sistema V3. Se conserva para comparación histórica; no afecta al gate V4-lite. | `endurance_hrv.py` | 13 |

---

## 2. Reglas generales

Estas reglas aplican a todos los archivos CSV del sistema:

- **Clave primaria:** `Fecha` (formato YYYY-MM-DD). Cada día solo puede tener una fila dentro del histórico del único atleta soportado por este proyecto.
- **Sin duplicados:** si se reprocesa un día, la nueva fila sustituye a la anterior (upsert por Fecha).
- **Orden:** ascendente por Fecha (el día más antiguo arriba, el más reciente abajo).
- **Codificación:** UTF-8
- **Separador:** coma (CSV estándar)

**Nota sobre sleep.csv:** Este archivo contiene solo datos de sueño/recuperación de Polar. Puede tener más filas que CORE/FINAL, porque registra noches aunque no haya habido medición HRV ese día. La carga de entrenamiento está en `sessions_day.csv` (generado por `build_sessions.py`). Su clave primaria sigue siendo Fecha (sin duplicados).

---

## 3. CORE (canónico) — columnas y orden exacto

CORE contiene la señal fisiológica pura del día: lo que el sensor midió y cómo de fiable es esa medición. No incluye ninguna decisión de entrenamiento.

**Cabecera exacta (copiar literal):**

```
Fecha,Calidad,HRV_Stability,Stability_Subtype,Artifact_pct,Tiempo_Estabilizacion,HR_stable,RRbar_s,RMSSD_stable,RMSSD_stable_last2,tail_mismatch_pct,lnRMSSD,Flags,SI_baevsky,SD1,SD2,SD1_SD2_ratio,Notes
```

| # | Columna | Tipo | ¿Puede ser nulo? | Ejemplo | Qué es |
|---|---------|------|-------------------|---------|--------|
| 1 | Fecha | date | No | 2026-02-09 | Día de la medición matinal |
| 2 | Calidad | str | No | OK | Veredicto de usabilidad: OK / FLAG_mecánico / INVALID |
| 3 | HRV_Stability | str | No | OK | ¿El tramo final era estable? OK / Unstable |
| 4 | Stability_Subtype | str | No | STAB_LAST2_MISMATCH | Subtipo explícito del chequeo de estabilidad. `OK` si no hubo incidencia |
| 5 | Artifact_pct | float | Sí | 3.45 | % de latidos descartados por artefactos |
| 6 | Tiempo_Estabilizacion | float | Sí | 90.0 | Segundos hasta que la señal se estabilizó. NaN si no se detectó. |
| 7 | HR_stable | float | Sí | 48.5 | Pulso medio en el tramo estable (lpm) |
| 8 | RRbar_s | float | Sí | 1.237 | Intervalo RR medio en el tramo estable (segundos) |
| 9 | RMSSD_stable | float | Sí | 52.3 | Variabilidad cardiaca del tramo estable completo (ms) |
| 10 | RMSSD_stable_last2 | float | Sí | 51.8 | Variabilidad de los últimos 120 s, para verificar estabilidad (ms) |
| 11 | tail_mismatch_pct | float | Sí | 20.48 | Diferencia relativa entre `RMSSD_stable` y `RMSSD_stable_last2` en porcentaje |
| 12 | lnRMSSD | float | Sí | 3.957 | Logaritmo natural de RMSSD_stable |
| 13 | Flags | str | Sí | STAB_LAST2_MISMATCH\|BETA_FROZEN | Incidencias detectadas, separadas por `\|` |
| 14 | SI_baevsky | float | Sí | 63.2 | Índice de estrés de Baevsky (informativo, no entra en el gate) |
| 15 | SD1 | float | Sí | 25.95 | SD1 del diagrama de Poincare (informativo) |
| 16 | SD2 | float | Sí | 74.21 | SD2 del diagrama de Poincare (informativo) |
| 17 | SD1_SD2_ratio | float | Sí | 0.35 | Ratio SD1/SD2 (informativo) |
| 18 | Notes | str | Sí | src=...; dur_raw=... | Metadatos técnicos del procesamiento |

**Notas sobre formato:**
- `Stability_Subtype` hace explícito el subtipo de estabilidad sin obligar a parsear `Flags`
- `tail_mismatch_pct` es diagnóstico: no decide el color por sí mismo, pero explica los `Unstable` por discrepancia de cola
- `Flags`: vocabulario cerrado (ver Diccionario §7), valores separados por `|` (sin espacios)
- `Notes`: string determinista `clave=valor` separado por `; `, con claves mínimas: src + duraciones + conteos + desglose artefactos

---

## 4. FINAL (derivado) — columnas y orden exacto

FINAL es el archivo de auditoría completo: contiene la medición del día, el suavizado, los baselines, todos los gates, el veto agudo, el residual, la acción, la acumulación, los warnings y el `reason_text` contextual. Además, desde r2026-03-12 expone una capa mínima de auditoría `raw vs ref` para entender mejor los días `Unstable` sin cambiar el `gate_final`.

**Cabecera exacta (copiar literal):**

```
Fecha,Calidad,HRV_Stability,Artifact_pct,Tiempo_Estabilizacion,Stability_Subtype,tail_mismatch_pct,HR_today,RMSSD_stable,lnRMSSD_today,lnRMSSD_used,HR_used,n_roll3,gate_raw_today,gate_raw_reason,unstable_note,ln_base60,HR_base60,n_base60,SWC_ln,SWC_HR,d_ln,d_HR,gate_base60,gate_razon_base60,gate_shadow42,gate_razon_shadow42,n_base42,gate_shadow28,gate_razon_shadow28,n_base28,decision_mode,gate_final,gate_final_delta,decision_path,override_reason,residual_ln,residual_z,residual_tag,gate_badge,quality_flag,Color_operativo,Action,Action_detail,bad_streak,bad_7d,baseline60_degraded,healthy_rmssd,healthy_hr,healthy_period,flag_sistemico,flag_razon,warning_threshold,warning_mode,veto_agudo,ln_pre_veto,swc_ln_floor,reason_text
```

### Agrupación lógica

Las 58 columnas se organizan en 13 bloques lógicos. Cada bloque agrupa campos relacionados:

#### A) Identidad / medición base (10 cols)

Réplica de la medición de CORE, incluyendo ahora el subtipo explícito de estabilidad y el porcentaje de mismatch de cola.

Columnas 1-10: `Fecha`, `Calidad`, `HRV_Stability`, `Artifact_pct`, `Tiempo_Estabilizacion`, `Stability_Subtype`, `tail_mismatch_pct`, `HR_today`, `RMSSD_stable`, `lnRMSSD_today`

#### B) Suavizado ROLL3 (3 cols)

Media móvil de los últimos 3 días clean. Es el valor suavizado que realmente se compara contra el baseline.

Columnas 11-13: `lnRMSSD_used`, `HR_used`, `n_roll3`

#### C) Auditoría raw del día (3 cols)

Capa informativa para días dudosos. No recolorea el semáforo oficial.

Columnas 14-16: `gate_raw_today`, `gate_raw_reason`, `unstable_note`

#### D) Baseline 60d + SWC (5 cols)

Tu "normal" reciente (mediana de 60 días) y el umbral de cambio mínimo significativo.

Columnas 17-21: `ln_base60`, `HR_base60`, `n_base60`, `SWC_ln`, `SWC_HR`

#### E) Deltas BASE60 (2 cols)

La distancia entre tu valor suavizado de hoy y tu baseline. Es lo que determina el color oficial.

Columnas 22-23: `d_ln`, `d_HR`

#### F) Gate extendido (17 cols)

Todos los semáforos (BASE60 + sombras + decisión final + residual), con motivos y auditoría de override.

Columnas 24-40:
- BASE60: `gate_base60`, `gate_razon_base60`
- Sombra 42: `gate_shadow42`, `gate_razon_shadow42`, `n_base42`
- Sombra 28: `gate_shadow28`, `gate_razon_shadow28`, `n_base28`
- Decisión: `decision_mode`, `gate_final`, `gate_final_delta`, `decision_path`, `override_reason`
- Residual: `residual_ln`, `residual_z`, `residual_tag`, `gate_badge`

#### G) Calidad / color operativo (2 cols)

Flag de calidad dudosa y duplicado explícito del color final.

Columnas 41-42: `quality_flag`, `Color_operativo`

#### H) Acción (2 cols)

La instrucción de entrenamiento y su detalle (matizado por acumulación o `quality_flag`).

Columnas 43-44: `Action`, `Action_detail`

#### I) Acumulación (2 cols)

Racha y conteo de días ROJO. Cuando se acumulan, se activa DESCARGA. Los días `NO` por falta de datos no inflan estos contadores.

Columnas 45-46: `bad_streak`, `bad_7d`

#### J) Warning baseline (4 cols)

Aviso a medio plazo si tu capacidad actual está por debajo de tu mejor momento.

Columnas 47-50: `baseline60_degraded`, `healthy_rmssd`, `healthy_hr`, `healthy_period`

#### K) Flags sistémicos (2 cols)

Reservado para información externa (sueño, enfermedad, viajes). Actualmente no se alimenta automáticamente.

Columnas 51-52: `flag_sistemico`, `flag_razon`

#### L) Parámetros warning (2 cols)

El umbral y el modo usados para calcular el warning de baseline degradado.

Columnas 53-54: `warning_threshold`, `warning_mode`

#### M) v4 Enhancement (4 cols)

Veto agudo (bypass de ROLL3 ante caídas bruscas) y texto explicativo contextual.

Columnas 55-58: `veto_agudo`, `ln_pre_veto`, `swc_ln_floor`, `reason_text`

**Nuevas columnas de auditoría mínima:**
- `Stability_Subtype`: subtipo explícito de estabilidad (`OK`, `STAB_LAST2_MISMATCH`, `STAB_TAIL_SHORT`, etc.)
- `tail_mismatch_pct`: % de discrepancia entre `RMSSD_stable` y `RMSSD_stable_last2`
- `gate_raw_today`: semáforo 2D contrafactual usando el raw del día (`lnRMSSD_today`, `HR_today`) frente a la misma baseline
- `gate_raw_reason`: razón de ese gate raw (`2D_OK`, `2D_LN`, `2D_HR`, `2D_AMBOS`)
- `unstable_note`: resumen corto `raw vs ref` cuando `quality_flag=True`

**Importante:** `gate_raw_today`, `gate_raw_reason` y `unstable_note` son solo auditoría. No cambian `gate_final`.

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

## 6. SLEEP (sidecar externo) — columnas y orden exacto

`ENDURANCE_HRV_sleep.csv` contiene datos de sueño y recuperación nocturna de Polar. Alimenta el `reason_text` en FINAL/DASHBOARD pero **NO afecta al cálculo del gate**. Si falta, el sistema funciona igualmente (solo pierde contexto de sueño en reason_text).

**La carga de entrenamiento ya NO está en sleep.csv** — está en `sessions_day.csv` (generado por `build_sessions.py`), que tiene datos más ricos: work blocks, zonas con moving mask, rolling con cobertura real (_nobs).

**Cabecera exacta (copiar literal):**

```
Fecha,polar_sleep_duration_min,polar_sleep_span_min,polar_deep_pct,polar_rem_pct,polar_efficiency_pct,polar_continuity,polar_continuity_index,polar_interruptions_long,polar_interruptions_total,polar_sleep_score,polar_night_rmssd,polar_night_rri,polar_night_resp,sleep_dur_p10,sleep_dur_p90,sleep_int_p90
```

### Agrupación lógica

Las 17 columnas se organizan en 3 bloques:

#### Polar Sleep (10 cols)

| Columna | Tipo | Qué es |
|---------|------|--------|
| `polar_sleep_duration_min` | float | Minutos de sueño real (asleep, sin interrupciones) |
| `polar_sleep_span_min` | float | Minutos totales en cama (incluye despertares) |
| `polar_deep_pct` | float | % de sueño profundo (N3). Solo con Sleep Plus Stages (cobertura ~18%) |
| `polar_rem_pct` | float | % de sueño REM. Solo con Sleep Plus Stages (cobertura ~18%) |
| `polar_efficiency_pct` | float | Eficiencia: asleep / span × 100 |
| `polar_continuity` | int | Clase de continuidad (1-5, Polar) |
| `polar_continuity_index` | float | Índice de continuidad (Polar) |
| `polar_interruptions_long` | int | **Conteo** de interrupciones largas (≠ duración). P90 típico ≈ 8 |
| `polar_interruptions_total` | int | Conteo total de interrupciones (largas + cortas) |
| `polar_sleep_score` | float | Score de sueño Polar (0-100). Solo con Nightly Recharge (cobertura ~18%) |

#### Polar Nightly Recharge (3 cols)

| Columna | Tipo | Qué es |
|---------|------|--------|
| `polar_night_rmssd` | float | RMSSD nocturno medio (ms). Solo con Nightly Recharge |
| `polar_night_rri` | float | RRI nocturno medio (ms). Solo con Nightly Recharge |
| `polar_night_resp` | float | Intervalo respiratorio nocturno (ms). Solo con Nightly Recharge |

#### Percentiles propios (3 cols)

| Columna | Tipo | Qué es |
|---------|------|--------|
| `sleep_dur_p10` | float | Percentil 10 de duración de sueño. Debajo = noche corta |
| `sleep_dur_p90` | float | Percentil 90 de duración de sueño |
| `sleep_int_p90` | float | Percentil 90 de interrupciones largas. Encima = noche fragmentada |

**Notas:**
- Los percentiles se recalculan con **todo** el histórico disponible cada vez que se hace upsert. Son globales (mismo valor en todas las filas).
- `ENDURANCE_HRV_sleep.csv` puede tener más filas que FINAL: registra noches aunque no haya medición HRV.
- Si Polar Sleep API falla → campos `polar_*` quedan NaN. El pipeline no se aborta.

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
           ┌──────────────────┐      ENDURANCE_HRV_sleep.csv   SESSIONS_DAY.csv
           │ endurance_v4lite │ ◄─── (sueño Polar,     ◄── (carga, work blocks,
           └──────────────────┘       solo reason_text)     solo reason_text)
                   │
           ┌───────┴───────┐
           ▼               ▼
      FINAL.csv      DASHBOARD.csv
      (auditoría,     (operativo,
       58 cols)        10 cols)

  Polar Sleep API ──┐
  Polar Nightly  ───┤
                    ├──► ENDURANCE_HRV_sleep.csv (17 cols)
                    │    (sueño + recuperación)
                    │
  Intervals.icu ────┤
                    ├──► build_sessions.py ──► SESSIONS.csv (43 cols)
                    │                     ├──► SESSIONS_DAY.csv (40 cols)
                    │                     └──► ENDURANCE_HRV_sessions_metadata.json
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
assert df.shape[1] == 58                                                               # schema v4 actual
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

### SLEEP

```python
assert sleep["Fecha"].is_unique                                                         # sin duplicados
assert sleep.shape[1] == 17                                                             # schema actual (solo Polar sleep)
# Percentiles son globales (mismo valor en todas las filas)
assert sleep["sleep_dur_p10"].nunique() <= 1
# polar_interruptions_long es conteo (no duración), valores típicos 0-15
if sleep["polar_interruptions_long"].notna().any():
    assert sleep["polar_interruptions_long"].max() < 50  # sanity: no es duración en minutos
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
- **FLAG_mecánico** → prudencia. El gate se calcula, pero la acción se limita por calidad

Mirar `HRV_Stability`:
- **Unstable** no aparece en DASHBOARD
- Si necesitas revisar estabilidad, mirar CORE o FINAL

### Paso 2: Semáforo y acción

Mirar `gate_badge` y `Action`:
- **VERDE + INTENSIDAD_OK** → ejecutar plan previsto (intervalos, sesión dura, lo que toque)
- **ÁMBAR + Z2_O_TEMPO_SUAVE** → sin HIIT, pero Z1-Z2 permitido
- **ROJO/NO + SUAVE_O_DESCANSO** → tratar como día de descarga o descanso; si hace falta matiz fino, mirar FINAL

### Paso 3: Contexto (v4)

Si `reason_text` no está vacío:
- Explica **por qué** el sistema tomó esa decisión y qué factores contextuales hay (sueño malo, carga acumulada, caída aguda de HRV, divergencias gate↔carga)
- No cambia el gate ni la acción, pero informa decisiones

### Paso 4: Warning (informativo)

Si `baseline60_degraded = True`:
- Tu capacidad actual está por debajo de tu mejor momento conocido
- No cambia el gate del día, pero considerar en decisiones semanales de progresión (no es momento de subir carga)

---

## 12. Migración desde V3 (histórico)

Si tienes el archivo monolítico del sistema anterior (`ENDURANCE_HRV_master_ALL.csv`):

```bash
# 1. Ejecutar migración con script legacy (si lo tienes en otro repo)
python endurance_migrate.py --master-all ENDURANCE_HRV_master_ALL.csv

# 2. Verificar que DASHBOARD contiene los datos esperados
head -5 data/ENDURANCE_HRV_master_DASHBOARD.csv

# 3. Archivar el archivo monolítico (no borrar, por seguridad)
mkdir -p docs/legacy
mv ENDURANCE_HRV_master_ALL.csv docs/legacy/

# 4. Mover archivos intermedios con sufijos de fecha
mv *_20260209*.csv docs/legacy/

# 5. A partir de aquí, usar los scripts nuevos para cada día
python endurance_hrv.py --rr-file data/rr_downloads/nuevo_RR.csv --data-dir data
python endurance_v4lite.py --data-dir data
```

---

Fin del documento.

