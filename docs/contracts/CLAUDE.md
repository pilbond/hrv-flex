# ENDURANCE HRV v4 — Tareas de Implementación

> Documento historico de implementacion (worklog).
> No es contrato operativo vigente.
> La referencia activa está en:
> - `ENDURANCE_HRV_Spec_Tecnica.md`
> - `ENDURANCE_HRV_Estructura.md`
> - `ENDURANCE_HRV_Diccionario.md`
> - `GUIA_PYTHON_SCRIPTS.md`
> - `PROCEDIMIENTO_RECOMENDADO.md`

**Para:** Claude Code (local, sobre repo `hrv-flex` branch `origin/v4`)  
**Contexto:** Sistema de monitoreo HRV en producción (Railway). Se implementan mejoras v4.  
**Estado:** Los masters históricos v4 ya están generados (274 días). Solo falta integrar la lógica en el pipeline diario.

---

## Qué ya está hecho (NO repetir)

Se han generado offline los siguientes archivos con datos históricos completos (2025-05-12 → 2026-02-23):

| Archivo | Filas × Cols | Qué contiene |
|---------|-------------|--------------|
| `ENDURANCE_HRV_master_FINAL_v4.csv` | 274 × 53 | FINAL completo + veto_agudo + reason_text |
| `ENDURANCE_HRV_master_DASHBOARD_v4.csv` | 274 × 10 | DASHBOARD + reason_text |
| `ENDURANCE_HRV_sleep.csv` | 288 × 34 | Sueño Polar (JSON) + carga Intervals (seed histórico, incluye noches sin medición HRV) |

Estos archivos son el **seed**. Deben copiarse al `HRV_DATA_DIR` como punto de partida. El pipeline diario los actualizará incrementalmente (context) o regenerará completos (FINAL/DASHBOARD).

Script de referencia con la lógica probada: `build_v4_historical.py`

---

## Estado actual del sistema

### Arquitectura
```
polar_hrv_automation.py  →  Descarga RR de Polar AccessLink (exercises)
                             Ejecuta endurance_hrv.py + endurance_v4lite.py
                             Push wellness a Intervals.icu

endurance_hrv.py         →  RR crudo → CORE.csv (12 cols) + BETA_AUDIT.csv (13 cols)
endurance_v4lite.py      →  CORE → FINAL.csv (49 cols) + DASHBOARD.csv (9 cols)
web_ui.py                →  Flask UI + endpoints /api/sync, /auth, etc.
```

### APIs configuradas (env vars existentes)
- **Polar AccessLink**: `POLAR_CLIENT_ID`, `POLAR_CLIENT_SECRET`, scope `accesslink.read_all`
  - Actualmente: solo `/v3/exercises` para RR
  - Disponible pero no usado: `/v3/users/{user-id}/sleep` y `/v3/users/{user-id}/nightly-recharge`
  - **VERIFICADO**: scope `accesslink.read_all` incluye sleep y nightly-recharge
- **Intervals.icu**: `INTERVALS_API_KEY`, `INTERVALS_ATHLETE_ID`
  - Actualmente: solo PUSH wellness. No hace GET de actividades.
  - Disponible: `GET /api/v1/athlete/{id}/activities` con misma auth

### Contratos de datos — SCHEMA BUMP
- CORE: 12 columnas → **no se toca**
- FINAL: 49 → **53 columnas** (+veto_agudo, ln_pre_veto, swc_ln_floor, reason_text)
- DASHBOARD: 9 → **10 columnas** (+reason_text)
- BETA_AUDIT: 13 → **no se toca**
- NUEVO: `ENDURANCE_HRV_sleep.csv` (34 columnas, archivo independiente)

---

## Flujo diario objetivo (tras implementación)

```
Cada mañana, al hacer sync:

1. polar_hrv_automation.py descarga RR de exercises      [YA EXISTE]
2. polar_hrv_automation.py descarga sleep del día          [NUEVO - Tarea 1.1]
3. polar_hrv_automation.py descarga nightly recharge       [NUEVO - Tarea 1.2]
4. polar_hrv_automation.py descarga actividades Intervals  [NUEVO - Tarea 1.3]
   (del día anterior; puede haber >1 sesión → sumar load total)
5. Append fila nueva a ENDURANCE_HRV_sleep.csv           [NUEVO - Tarea 1.4]
6. endurance_hrv.py procesa RR → actualiza CORE            [YA EXISTE]
7. endurance_v4lite.py lee CORE + sleep.csv →            [MODIFICADO - Tareas 2+3]
   regenera FINAL_v4 (53 cols) + DASHBOARD_v4 (10 cols) COMPLETOS
8. Push wellness a Intervals.icu                           [YA EXISTE]
```

**Punto clave:** FINAL y DASHBOARD se regeneran completos cada vez (como ahora). El sleep.csv es incremental (append). Si el fetch de sleep o Intervals falla, el pipeline sigue — reason_text se genera con lo que haya disponible.

---

## BLOQUE 1: Fetch diario de contexto (polar_hrv_automation.py)

### Objetivo
Añadir funciones de fetch para sleep, nightly recharge y actividades. Cada mañana, tras descargar RR, hacer fetch y append a `sleep.csv`.

### Tarea 1.1: Fetch sleep de Polar AccessLink

**Endpoint:** `GET /v3/users/{user-id}/sleep/{date}` (non-transactional, no consume datos)  
**Auth:** Bearer token (ya disponible en TOKEN_FILE)  
**user_id:** Se guarda como `x_user_id` en el token response (`exchange_code_for_token()`, línea 558)

Campos a extraer:
```
date, sleep_start_time, sleep_end_time,
continuity (1.0-5.0), continuity_class (1-5),
light_sleep (ISO), deep_sleep (ISO), rem_sleep (ISO),
total_interruption_duration (ISO),
sleep_charge (1-5),
sleep_score (float)
```

**Implementación:**
```python
def fetch_polar_sleep(token: str, user_id: str, date_str: str) -> Optional[dict]:
    """Fetch sleep data for a date. Returns None if not available."""
    try:
        resp = api_request("GET", f"/users/{user_id}/sleep/{date_str}", token, timeout=30)
        return resp
    except Exception as e:
        print(f"⚠️ Sleep fetch failed for {date_str}: {e}")
        return None
```

Ubicación: `polar_hrv_automation.py`, junto a `list_exercises()` (línea 632).

**⚠️ Parsing crítico de interrupciones:** El `polar_interruptions_long` del sleep.csv es el **conteo** de interrupciones largas (mediana=4, P90=8), NO la duración total. En la respuesta de la API AccessLink, buscar el campo equivalente al `longCount` del export JSON de Polar Flow. Si la API solo devuelve `total_interruption_duration`, habrá que parsear el hipnograma para contar interrupciones. El valor del export JSON viene de `evaluation.interruptions.longCount`. Confundir conteo con duración produce un P90 inútil (~90min) en vez del operativo (~8 interrupciones).

### Tarea 1.2: Fetch nightly recharge de Polar AccessLink

**Endpoint:** `GET /v3/users/{user-id}/nightly-recharge/{date}`  
**Auth:** Mismo Bearer token

Campos:
```
heart_rate_avg (FC nocturna),
heart_rate_variability_avg (RMSSD nocturno = "nightly_rmssd"),
breathing_rate_avg,
nightly_recharge_status (POOR/COMPROMISED/OK/GOOD/VERY_GOOD),
ans_charge (-10 a +10)
```

**Implementación:** Análoga a sleep. Misma ubicación.

### Tarea 1.3: Fetch actividades de Intervals.icu

**Endpoint:** `GET /api/v1/athlete/{id}/activities?oldest={date}&newest={date}`  
**Auth:** Basic auth con API_KEY (reutilizar `_basic_auth_str("API_KEY", api_key)`, línea 407)

Campos por actividad:
```
type, icu_training_load (Load), icu_intensity,
moving_time (seg), icu_atl, icu_ctl, icu_tsb,
average_heartrate, max_heartrate, icu_rpe
```

**Importante:** Un día puede tener >1 actividad. Agregar:
- `intervals_load` = sum(icu_training_load) de todas las actividades del día
- `intervals_type_main` = type de la actividad con mayor load
- `intervals_duration_min` = sum(moving_time) / 60

**Implementación:**
```python
def fetch_intervals_activities(api_key: str, athlete_id: str, date_str: str) -> list:
    """Fetch activities for a date from Intervals.icu."""
    url = f"{INTERVALS_BASE_URL.rstrip('/')}/api/v1/athlete/{athlete_id}/activities"
    headers = {"Authorization": _basic_auth_str("API_KEY", api_key)}
    params = {"oldest": date_str, "newest": date_str}
    try:
        resp = requests.get(url, headers=headers, params=params, timeout=30)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        print(f"⚠️ Intervals fetch failed for {date_str}: {e}")
        return []
```

### Tarea 1.4: Append a sleep.csv

Tras obtener los datos de sleep + nightly + Intervals para el día, construir una fila y hacer append a `ENDURANCE_HRV_sleep.csv`.

**Schema del context (34 columnas, contrato fijo):**
```
Fecha,
polar_sleep_duration_min, polar_sleep_span_min,
polar_deep_pct, polar_rem_pct,
polar_efficiency_pct, polar_continuity, polar_continuity_index,
polar_interruptions_long, polar_interruptions_total, polar_sleep_score,
polar_night_rmssd, polar_night_rri, polar_night_resp,
intervals_load, intervals_load_max, intervals_intensity_max,
intervals_type_main, intervals_duration_min, intervals_n_acts,
intervals_avg_hr, intervals_max_hr,
intervals_atl, intervals_ctl, intervals_tsb,
intervals_rpe, intervals_resting_hr,
intervals_load_3d, intervals_load_yday,
sleep_dur_p10, sleep_dur_p90, sleep_int_p90,
load_3d_p90, load_3d_median
```

**Lógica de append:**
1. Leer sleep.csv existente (el seed tiene 288 filas históricas)
2. Si Fecha ya existe → update (upsert). Si no → append
3. Recalcular `intervals_load_3d` = sum(load de fecha-1, fecha-2, fecha-3) usando datos del context
4. Recalcular `intervals_load_yday` = load de fecha-1
5. Recalcular percentiles rolling con todos los datos disponibles:
   - `sleep_dur_p10`, `sleep_dur_p90` sobre todas las noches con duración
   - `sleep_int_p90` sobre todas las noches con interrupciones
   - `load_3d_p90`, `load_3d_median` sobre todos los días con load_3d > 0
6. Guardar sleep.csv

**Percentiles calibrados actuales (referencia):**
- Sueño duración P10: 362 min (6.0h)
- Interrupciones largas P90: 8
- Load 3d P90: 241

### Test de aceptación Bloque 1
```python
context = pd.read_csv("ENDURANCE_HRV_sleep.csv")
assert "Fecha" in context.columns
assert len(context) >= 288  # seed + nuevos
# Verificar que el día de hoy tiene datos (al menos parciales)
today = datetime.now().strftime('%Y-%m-%d')
assert today in context['Fecha'].values
```

---

## BLOQUE 2: Veto agudo + reason_text en el decisor (endurance_v4lite.py)

### Objetivo
Modificar `endurance_v4lite.py` para incluir veto agudo y reason_text. La lógica está probada y validada en `build_v4_historical.py`.

### Constantes a añadir (junto a Config, línea ~56)
```python
SWC_FLOOR = 0.04879   # ln(1.05), floor mínimo para SWC
VETO_MULT = 2.0       # veto si raw cae > 2×SWC bajo base60
```

### Arrays nuevos a inicializar (junto a residual_ln, línea ~307)
```python
veto_agudo = np.array([False]*len(df), dtype=bool)
ln_pre_veto = np.full(len(df), np.nan, dtype=float)
swc_ln_floor_arr = np.full(len(df), np.nan, dtype=float)
reason_parts: list[list[str]] = [[] for _ in range(len(df))]
```

### Inserción del veto agudo: DENTRO del loop principal

En el loop `for i in range(len(df)):` (línea 316), **después** de calcular base60 y SWC (línea ~341: `swc_ln60[i] = sw_ln`) y **antes** del gate 2D (línea ~350: `dln = float(ln_used[i] - b_ln)`):

```python
        # ===== VETO AGUDO (v4): bypass ROLL3 si caída aguda =====
        swc_v4 = max(sw_ln, SWC_FLOOR)
        swc_ln_floor_arr[i] = swc_v4

        if (is_clean[i] and np.isfinite(ln_today[i]) and np.isfinite(b_ln)
            and ln_today[i] < (b_ln - VETO_MULT * swc_v4)):
            veto_agudo[i] = True
            ln_pre_veto[i] = ln_used[i]   # guardar ROLL3 original
            ln_used[i] = ln_today[i]       # forzar dato crudo
            hr_used[i] = hr_today[i]       # forzar HR crudo también
            reason_parts[i].append(
                f"Caída aguda HRV: raw={ln_today[i]:.3f} vs base={b_ln:.3f} "
                f"(drop={ln_today[i]-b_ln:.3f}, umbral=-{VETO_MULT*swc_v4:.3f})"
            )

        # Gate 2D usa ln_used/hr_used (ya forzados si veto activo)
        dln = float(ln_used[i] - b_ln)
        ...
```

### Inserción de reason_text: DESPUÉS del gate final

Después del bloque de Action (línea ~565), añadir generación de reason_text.
Necesita leer `ENDURANCE_HRV_sleep.csv` si existe:

```python
    # ===== REASON_TEXT (contextual) =====
    ctx_path = DATA_DIR / "ENDURANCE_HRV_sleep.csv"
    ctx_lookup = {}
    if ctx_path.exists():
        ctx_df = pd.read_csv(ctx_path)
        ctx_df['Fecha'] = ctx_df['Fecha'].astype(str)
        ctx_lookup = ctx_df.set_index('Fecha')

    for i in range(len(df)):
        fecha = str(df.iloc[i]["Fecha"])

        # Saturación parasimpática
        if np.isfinite(d_ln[i]) and np.isfinite(swc_ln_floor_arr[i]):
            if d_ln[i] > 2 * swc_ln_floor_arr[i]:
                reason_parts[i].append("HRV excesivamente alto: posible saturación parasimpática")

        # Quality override
        if quality_flag[i] and gate_final[i] in (VERDE, AMBAR):
            reason_parts[i].append("Dato dudoso: limitar a Z1-Z2 máx 90min")

        # Contexto desde sleep.csv
        if fecha in ctx_lookup.index:
            ctx_row = ctx_lookup.loc[fecha]

            # Sueño (percentiles propios, NO umbrales fijos)
            sleep_dur = _safe_float(ctx_row, 'polar_sleep_duration_min')
            sleep_int = _safe_float(ctx_row, 'polar_interruptions_long')
            sleep_dur_p10 = _safe_float(ctx_row, 'sleep_dur_p10')
            sleep_int_p90 = _safe_float(ctx_row, 'sleep_int_p90')

            if sleep_dur is not None and sleep_dur_p10 is not None and sleep_dur < sleep_dur_p10:
                reason_parts[i].append(f"Noche corta ({sleep_dur:.0f}min < P10={sleep_dur_p10:.0f})")
            if sleep_int is not None and sleep_int_p90 is not None and sleep_int > sleep_int_p90:
                reason_parts[i].append(f"Noche fragmentada ({sleep_int:.0f} interr > P90={sleep_int_p90:.0f})")

            # Nightly RMSSD discordancia
            night_rmssd = _safe_float(ctx_row, 'polar_night_rmssd')
            if night_rmssd is not None:
                if gate_final[i] == VERDE and night_rmssd < 25:
                    reason_parts[i].append(f"VERDE pero nightly_rmssd bajo ({night_rmssd:.0f}ms)")
                elif gate_final[i] == ROJO and night_rmssd > 45:
                    reason_parts[i].append(f"ROJO con nightly_rmssd alto ({night_rmssd:.0f}ms): posible confusor")

            # Carga
            load_3d = _safe_float(ctx_row, 'intervals_load_3d')
            load_3d_p90 = _safe_float(ctx_row, 'load_3d_p90')
            tsb = _safe_float(ctx_row, 'intervals_tsb')
            load_yday = _safe_float(ctx_row, 'intervals_load_yday')

            if load_3d is not None and load_3d_p90 is not None and load_3d > load_3d_p90:
                reason_parts[i].append(f"Carga acumulada alta (3d={load_3d:.0f} > P90={load_3d_p90:.0f})")
            if tsb is not None and tsb < -25:
                reason_parts[i].append(f"Fatiga profunda (TSB={tsb:.0f})")
            if gate_final[i] == ROJO and load_yday is not None and load_yday < 30:
                if sleep_dur is None or (sleep_dur_p10 is not None and sleep_dur >= sleep_dur_p10):
                    reason_parts[i].append("ROJO sin carga previa ni sueño malo: revisar otros factores")
            if gate_final[i] == VERDE and tsb is not None and tsb < -20:
                reason_parts[i].append(f"VERDE con fatiga acumulada (TSB={tsb:.0f}): precaución intensidad")

    reason_text = np.array([" | ".join(p) if p else "" for p in reason_parts], dtype=object)
```

Helper necesario:
```python
def _safe_float(row, col):
    """Extract float from context row, return None if missing."""
    try:
        v = row[col]
        if pd.isna(v):
            return None
        return float(v)
    except (KeyError, TypeError, ValueError):
        return None
```

### COLS_FINAL actualizado (49 → 53)
```python
COLS_FINAL = [
    "Fecha","Calidad","HRV_Stability","Artifact_pct","Tiempo_Estabilizacion",
    "HR_today","RMSSD_stable","lnRMSSD_today",
    "lnRMSSD_used","HR_used","n_roll3",
    "ln_base60","HR_base60","n_base60","SWC_ln","SWC_HR","d_ln","d_HR",
    "gate_base60","gate_razon_base60",
    "gate_shadow42","gate_razon_shadow42","n_base42",
    "gate_shadow28","gate_razon_shadow28","n_base28",
    "decision_mode","gate_final","gate_final_delta","decision_path","override_reason",
    "residual_ln","residual_z","residual_tag","gate_badge",
    "quality_flag","Color_operativo",
    "Action","Action_detail","bad_streak","bad_7d",
    "baseline60_degraded","healthy_rmssd","healthy_hr","healthy_period",
    "flag_sistemico","flag_razon",
    "warning_threshold","warning_mode",
    # v4 nuevas
    "veto_agudo","ln_pre_veto","swc_ln_floor","reason_text",
]
```

### COLS_DASHBOARD actualizado (9 → 10)
```python
COLS_DASHBOARD = [
    "Fecha","Calidad","HR_today","RMSSD_stable","gate_badge","Action",
    "gate_razon_base60","decision_path","baseline60_degraded",
    "reason_text",
]
```

### Resultados esperados (validados con datos históricos)
- Veto agudo: 54 días activado, 19 cambios de gate (7 VERDE→ROJO, 11 ÁMBAR→ROJO, 1 ROJO→ÁMBAR)
- Gate redistribución: VERDE 132→125, ÁMBAR 43→33, ROJO 61→78, NO 38→38
- Reason_text: 125 de 274 días con contexto

### Test de aceptación Bloque 2
```python
final = pd.read_csv("ENDURANCE_HRV_master_FINAL.csv")
assert len(final.columns) == 53
assert "veto_agudo" in final.columns
assert "reason_text" in final.columns
assert final["veto_agudo"].sum() >= 50  # ~54 en datos actuales

# Verificar consistencia veto
veto = final[final["veto_agudo"] == True]
for _, row in veto.iterrows():
    assert abs(row["lnRMSSD_used"] - row["lnRMSSD_today"]) < 0.001, \
        f"Veto day {row['Fecha']} should use raw lnRMSSD"

# Regresión: comparar con seed
seed = pd.read_csv("ENDURANCE_HRV_master_FINAL_v4.csv")  # el seed histórico
merged = seed.merge(final, on="Fecha", suffixes=("_seed", "_new"))
diffs = merged[merged["gate_final_seed"] != merged["gate_final_new"]]
assert len(diffs) == 0, f"Regression: {len(diffs)} days differ from seed"
```

---

## BLOQUE 3: Actualizar documentos normativos

### Archivos a actualizar
1. **`ENDURANCE_HRV_Estructura.md`**
   - FINAL: 49 → 53 columnas (añadir bloque L: v4 con veto_agudo, ln_pre_veto, swc_ln_floor, reason_text)
   - DASHBOARD: 9 → 10 columnas (añadir reason_text)
   - Nuevo archivo: documentar ENDURANCE_HRV_sleep.csv (34 cols)
   - Actualizar cabeceras exactas (copiar literal)
   - Añadir tests de integridad para nuevas columnas

2. **`ENDURANCE_HRV_Diccionario.md`**
   - Documentar veto_agudo, ln_pre_veto, swc_ln_floor, reason_text
   - Documentar sleep.csv y sus columnas

3. **`ENDURANCE_HRV_Spec_Tecnica.md`**
   - Nueva sección §10bis: Veto agudo (entre §10 ROLL3 y §12 Gate 2D)
   - Documentar: SWC_FLOOR = ln(1.05), VETO_MULT = 2.0, lógica de bypass
   - Nueva sección §15bis: Reason_text (después de §15 Acción)
   - Actualizar §17: 53 cols FINAL, 10 cols DASHBOARD, nuevo sleep.csv
   - Actualizar §19 Limitaciones: añadir que context depende de APIs externas

4. **`AGENTS.MD`**
   - Actualizar arquitectura con sleep.csv
   - Añadir fetch de sleep/nightly/intervals al flujo
   - Documentar nuevas funciones en polar_hrv_automation.py

---

## BLOQUE 4: Integración en polar_hrv_automation.py

### Objetivo
Conectar los fetches del Bloque 1 con el pipeline existente. Esto va en `polar_hrv_automation.py`.

### Punto de inserción
En la función principal de sync, **después** de descargar y procesar RR (lo que termina ejecutando `endurance_hrv.py` + `endurance_v4lite.py`), y **antes** del push a Intervals wellness:

1. Obtener `user_id` del token guardado en TOKEN_FILE
2. Determinar fecha del día procesado
3. Llamar `fetch_polar_sleep(token, user_id, fecha)`
4. Llamar `fetch_polar_nightly_recharge(token, user_id, fecha)`
5. Llamar `fetch_intervals_activities(api_key, athlete_id, fecha_ayer)` 
   - **Ojo:** las actividades de "ayer" son las relevantes para el HRV de "hoy"
   - Puede haber 0, 1, o N actividades → agregar sumando load
6. Construir fila de context y append/upsert a `ENDURANCE_HRV_sleep.csv`
7. Recalcular percentiles rolling
8. **Volver a ejecutar `endurance_v4lite.py`** para que use el context actualizado
   - O alternativamente: ejecutar v4lite una sola vez DESPUÉS del append a context

### Flujo revisado del sync
```python
# Actual (simplificado):
# 1. download_rr()
# 2. run endurance_hrv.py → CORE
# 3. run endurance_v4lite.py → FINAL + DASHBOARD
# 4. push wellness to Intervals

# Nuevo:
# 1. download_rr()
# 2. run endurance_hrv.py → CORE
# 3. fetch_and_append_context(token, fecha)  ← NUEVO
# 4. run endurance_v4lite.py → FINAL_v4 + DASHBOARD_v4 (lee sleep.csv)
# 5. push wellness to Intervals
```

---

## Variables de entorno

| Variable | Ya existe | Necesaria para |
|----------|-----------|----------------|
| `POLAR_CLIENT_ID` | ✅ | Auth Polar |
| `POLAR_CLIENT_SECRET` | ✅ | Auth Polar |
| `INTERVALS_API_KEY` | ✅ | Fetch actividades + push wellness |
| `INTERVALS_ATHLETE_ID` | ✅ | Fetch actividades + push wellness |
| `POLAR_USER_ID` | ✅ (en tokens JSON como `x_user_id`) | Sleep/nightly endpoints |

No se necesitan variables nuevas.

---

## Orden de ejecución

```
1. Copiar seed files al HRV_DATA_DIR:
   - ENDURANCE_HRV_sleep.csv (seed histórico, 288 filas)
   - Renombrar FINAL_v4 → FINAL, DASHBOARD_v4 → DASHBOARD (cuando estés listo)

2. BLOQUE 2: Modificar endurance_v4lite.py (veto agudo + reason_text)
   → commit + test de regresión contra seed
   → El test de regresión debe dar 0 diffs si el sleep.csv es el mismo

3. BLOQUE 1: Implementar fetch en polar_hrv_automation.py
   → commit + deploy + verificar que llegan datos de sleep/intervals

4. BLOQUE 4: Integrar fetches en el flujo de sync
   → commit + deploy + verificar flujo completo end-to-end

5. BLOQUE 3: Actualizar docs
   → commit
```

**Nota sobre el orden:** El BLOQUE 2 (decisor) va antes del BLOQUE 1 (fetch) porque el decisor funciona sin sleep.csv — simplemente no genera reason_text contextual. Así puedes validar el veto agudo en aislamiento antes de conectar las APIs.

Si BLOQUE 1 falla (API no responde), el pipeline sigue funcionando: el veto agudo opera solo con datos HRV y el reason_text se genera parcial (sin sueño/carga). El sleep.csv simplemente tendrá NaN para ese día.

---

## Notas para Claude Code

- Repo: `hrv-flex` branch `origin/v4`
- Archivo principal a modificar: `endurance_v4lite.py` (712 líneas, función `build_final_and_dashboard()`)
- Archivo secundario: `polar_hrv_automation.py` (1474 líneas, funciones de fetch + flujo sync)
- **NO tocar** `endurance_hrv.py` (procesamiento RR, Parte I)
- La lógica exacta de veto agudo y reason_text está probada en `build_v4_historical.py` — portarla, no reinventarla
- El seed `ENDURANCE_HRV_sleep.csv` tiene 288 filas y 34 columnas — respetar ese schema exacto
- Mantener compatibilidad Python 3.11
- Tests: ejecutar `python endurance_v4lite.py` y verificar FINAL (53 cols) + DASHBOARD (10 cols)
- Test de regresión: el FINAL generado debe coincidir con `ENDURANCE_HRV_master_FINAL_v4.csv` (seed)

