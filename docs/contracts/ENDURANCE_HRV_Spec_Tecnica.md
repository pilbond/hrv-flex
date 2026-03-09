# ENDURANCE HRV — Especificación Técnica

**Revisión:** r2026-03-09 v4.2 (sleep sidecar + rutas data/ + reason_text dual source)  
**Estado:** Producción

---

## Jerarquía de documentos

1. `ENDURANCE_HRV_Spec_Tecnica.md` — **Este documento**: define las fórmulas, reglas y algoritmos de todo el sistema. Es la autoridad sobre "cómo se calcula".
2. `ENDURANCE_HRV_Estructura.md` — Define el contrato de datos: qué columnas tiene cada archivo, en qué orden, y qué tipo de dato. Es la autoridad sobre "qué forma tiene la salida".
3. `ENDURANCE_HRV_Diccionario.md` — Explica cómo interpretar cada columna y cómo usarlas en la práctica diaria. Es la autoridad sobre "qué significa y qué hago con ello".

---

# PARTE I: Procesamiento RR → CORE

**Objetivo de la Parte I:** tomar un fichero CSV crudo de intervalos RR (latido a latido) grabado con el sensor Polar H10, y producir una fila limpia con las métricas fisiológicas del día: pulso en reposo, variabilidad cardíaca, y un veredicto de calidad sobre la medición.

El procesamiento sigue un pipeline de 6 pasos: parseo → limpieza → detección de latencia → métricas del tramo estable → clasificación de calidad → modelo beta (legacy).

Origen: Secciones 0-5 de Spec v3.x (r2025-12-25-UPDATE3)

---

## 0. Entradas, salidas, definiciones

### 0.1 Entradas

- Ficheros RR en CSV (UTF-8, separador coma)
- Cabecera EXACTA: `duration,offline`
  - `duration`: intervalo RR en milisegundos (float) — el tiempo entre un latido y el siguiente
  - `offline`: 0/1 (int), donde 1 = artefacto marcado por el sensor Polar H10 (pérdida de contacto, interferencia)
- REQUISITO: el nombre del archivo debe contener la fecha `YYYY-MM-DD`
  - Si además contiene hora `HH-MM-SS`, se usa para resolver duplicados (cuando hay dos mediciones el mismo día)

### 0.2 Definiciones clave

| Término | Definición | Por qué importa |
|---------|------------|-----------------|
| Eje temporal real | El tiempo de cada latido se define por suma acumulada de RR RAW; cuando se filtran latidos, los restantes conservan su posición temporal original (NO se re-cumsum) | Si recomprimieras el eje, las ventanas temporales (latencia, cola) quedarían desplazadas y las métricas serían incorrectas |
| Día válido | `Calidad != INVALID` (incluye OK y FLAG_mecánico) | Los días FLAG_mecánico no son ideales pero tienen suficiente señal para no perderlos completamente |
| Shift-1 | Las ventanas históricas (baselines, ROLL3) se calculan con días **anteriores**; el día D nunca entra en su propia referencia | Evita contaminación circular: un día muy malo no puede bajar su propio baseline para parecer "menos malo" |
| Sufijo `_stable` | Métrica calculada sobre el tramo estabilizado (tras descartar la fase de ajuste inicial y la cola final) | La fase inicial es ruidosa (transición simpático→parasimpático al despertar); la cola puede tener artefactos de parada |

### 0.3 Constantes y umbrales

| Parámetro | Valor | Para qué se usa |
|-----------|-------|-----------------|
| RR plausible | [300, 2000] ms | Descartar intervalos fisiológicamente imposibles (300 ms ≈ 200 lpm, 2000 ms ≈ 30 lpm) |
| Anti-cascada ΔRR | 20% | Detectar saltos bruscos entre latidos consecutivos que indican artefacto (ectópicos, pérdida de contacto) |
| Ventana latencia | 60 s | Tamaño de la ventana deslizante para calcular RMSSD local y detectar cuándo se estabiliza la señal |
| Paso latencia | 30 s | Avance de la ventana (solapamiento 50%): compromiso entre resolución temporal y estabilidad del cálculo |
| Umbral latencia | 8% | Si dos ventanas consecutivas cambian menos de un 8%, se considera que la señal se ha estabilizado |
| Tail-trim | 15 s | Recortar los últimos 15 s de grabación, donde es habitual que haya artefacto por parar el sensor o moverse |
| Cola estabilidad | 120 s | Los últimos 120 s del tramo estable se usan para verificar que la señal no estaba cambiando al final |
| n_pairs mínimo cola | 60 | Mínimo de pares de latidos consecutivos en la cola para que el RMSSD de verificación sea fiable |
| INVALID si Artifact_pct | > 20% | Demasiado ruido: más de 1 de cada 5 latidos es artefacto → el dato no es confiable |
| INVALID si HR_stable | < 35 o > 100 lpm | Fuera de rango fisiológico para medición supina matinal → probable error de medición |

### 0.4 Salidas

| Archivo | Contenido |
|---------|-----------|
| `ENDURANCE_HRV_master_CORE.csv` | Medición canónica (12 cols): la señal fisiológica del día sin ninguna decisión |
| `ENDURANCE_HRV_master_BETA_AUDIT.csv` | Beta/cRMSSD legacy (13 cols): modelo alométrico del sistema V3, conservado para comparación |

---

## 1. Parsing de fechas y resolución de duplicados

**Objetivo:** identificar la fecha de cada fichero RR y, si hay varias mediciones el mismo día, elegir la mejor de forma determinista (siempre la misma decisión ante los mismos datos).

### 1.1 Parse de Fecha y hora

- Extraer Fecha (date) desde primera ocurrencia `YYYY-MM-DD` en el nombre del archivo
- Extraer hora (time) si aparece `HH-MM-SS` en el nombre
- Si no hay fecha → archivo se ignora y se reporta en QA

### 1.2 Duplicados por Fecha (determinista)

Si hay 2+ archivos con la misma Fecha, elegir UNO con este orden estricto de prioridad (el primer criterio que diferencia, gana):

1. Preferir no-INVALID sobre INVALID
2. Preferir `Calidad=OK` sobre `FLAG_mecánico`
3. Preferir `HRV_Stability=OK`
4. Preferir `Tiempo_Estabilizacion` numérica en [60, 600] (la estabilización se detectó y fue razonable)
5. Preferir mayor duración total (s) (más material para calcular)
6. Preferir menor `Artifact_pct` (menos ruido)
7. Si hay hora: preferir hora más temprana (la medición más cercana al despertar); si no, orden alfabético

---

## 2. Eje temporal y limpieza de RR

**Objetivo:** construir una serie temporal limpia de intervalos RR, eliminando artefactos en tres capas sucesivas: marcado por el sensor, fuera de rango fisiológico, y saltos bruscos. Es crítico que cada latido conserve su posición temporal original, incluso cuando se eliminan latidos intermedios.

### 2.1 Eje temporal (CRÍTICO: no compresión)

Sea `RR_raw_ms[i]` el intervalo RR del CSV (en milisegundos).

```
t_end[i] = cumsum(RR_raw_ms)[i] / 1000   (segundos)
```

`t_end[i]` es el momento en que ocurrió el latido `i` desde el inicio de la grabación.

**IMPORTANTE:** Cuando se excluyen RR por artefacto, los RR restantes conservan su `t_end` original; NO se recalcula la suma acumulada. Esto garantiza que las ventanas temporales (latencia, cola, tail-trim) correspondan a momentos reales de la grabación.

### 2.2 Limpieza y artefactos

La limpieza se hace en 3 capas secuenciales. Cada capa opera sobre el resultado de la anterior.

#### Capa 1 — RR_base (marcado por sensor + rango fisiológico)

Excluir RR con:
- `offline = 1` (el sensor marcó pérdida de contacto)
- RR fuera de [300, 2000] ms (fisiológicamente imposible en reposo)

`RR_base` = todos los RR_raw que pasan ambas condiciones.

#### Capa 2 — Filtro anti-cascada ΔRR > 20% (OBLIGATORIO)

Detecta latidos donde el intervalo cambia bruscamente respecto al anterior — típico de ectópicos o micro-artefactos que pasaron la capa 1. Se aplica SOBRE `RR_base` en orden original (adyacentes).

```python
for i in range(1, len(RR_base)):
    delta = abs(RR_base[i] - RR_base[i-1]) / RR_base[i-1]
    if delta > 0.20:
        marcar RR_base[i] para exclusión
```

**IMPORTANTE — regla anti-cascada:**
- El comparador SIEMPRE es `RR_base[i-1]` (el latido anterior en la secuencia original), aunque `RR_base[i]` sea marcado para exclusión
- PROHIBIDO comparar contra "último RR aceptado" — eso propagaría el efecto de un artefacto a los latidos siguientes (cascada)

#### Capa 3 — RR_clean (resultado final)

`RR_clean` = `RR_base` sin los marcados por el filtro delta. Esta es la serie que se usará para todas las métricas.

#### Cálculo de Artifact_pct (sobre la serie RAW completa)

```
N_total_raw = nº RR RAW del CSV (todos)
N_offline   = count(offline == 1)                              (Capa 1)
N_oor       = count(offline == 0 AND RR fuera de [300, 2000])  (Capa 1)
N_delta     = nº RR marcados por delta dentro de RR_base       (Capa 2)

Artifact_pct = 100 × (N_offline + N_oor + N_delta) / N_total_raw
```

Artifact_pct refleja la proporción total de latidos descartados por cualquier causa.

---

## 3. Ventanas, latencia y tramo efectivo

**Objetivo:** de los ~6 minutos de grabación, determinar qué porción contiene señal estable y usable. Los primeros segundos suelen ser ruidosos (transición simpático→parasimpático al despertar, ajuste de la banda). Los últimos segundos pueden tener artefactos de parada. Hay que encontrar el punto de estabilización y definir el tramo útil.

### 3.1 Tail-trim (recorte de cola)

Se eliminan los últimos 15 segundos de la grabación para evitar artefactos típicos de parada (el usuario se mueve, toca el sensor, o anticipa el fin).

```
t_end_raw_last = t_end[-1]        (duración total de la grabación RAW)
t_end_eff = t_end_raw_last - 15   (nuevo final efectivo)
```

Antes de calcular métricas, se excluyen de `RR_clean` todos los RR con `t_end > t_end_eff`.

**NOTA:** `Artifact_pct` NO cambia por tail-trim — se calcula sobre la serie RAW completa, antes de recortar.

### 3.2 RMSSD por ventanas (para detectar estabilización)

Se calcula un RMSSD local en ventanas deslizantes para ver cómo evoluciona la variabilidad a lo largo de la grabación. Cuando la variabilidad deja de cambiar significativamente entre ventanas, se considera que la señal se ha estabilizado.

Ventanas de 60 s con paso de 30 s (solapamiento del 50%).

Para cada índice `w`:
- Ventana `w` cubre el intervalo temporal: `[30×w, 30×w + 60)` segundos
- Un RR pertenece a ventana `w` si: `30×w ≤ t_end < 30×w + 60`

Cálculo de RMSSD en cada ventana:
```python
RR_s = RR_ms / 1000                          # convertir a segundos
RMSSD = sqrt(mean(diff(RR_s)²)) × 1000       # resultado en ms
n_pairs = len(RR_s) - 1
# RMSSD_w solo se calcula si n_pairs >= 20; si no → NaN (ventana insuficiente)
```

### 3.3 Latencia (Tiempo_Estabilizacion)

La latencia es el tiempo que tarda la señal HRV en estabilizarse. Se detecta buscando el punto donde dos ventanas consecutivas dejan de cambiar significativamente.

```
rel_change(a→b) = abs(RMSSD_b - RMSSD_a) / RMSSD_a
```

**Criterio primario (umbral 8%):**

`Tiempo_Estabilizacion = 30×k` donde k es el primer índice tal que:
```
rel_change(k-1→k) < 0.08  AND  rel_change(k→k+1) < 0.08
```

Es decir: se necesitan **dos transiciones consecutivas** que cambien menos del 8%. Una sola ventana estable no basta — podría ser una pausa puntual en medio de una transición.

**Fallback robusto (si el criterio primario no encuentra estabilización):**

1. `RMSSD_target` = mediana de las últimas 4 ventanas válidas (la "meseta" final)
2. Buscar primer k con 3 ventanas consecutivas (k, k+1, k+2) cumpliendo:
   ```
   abs(RMSSD_w - RMSSD_target) / RMSSD_target < 0.08
   ```
3. Si tampoco se encuentra → `Tiempo_Estabilizacion = NaN` (la señal nunca se estabilizó)

### 3.4 Inicio efectivo de métricas

Una vez detectada (o no) la estabilización, se define dónde empieza el tramo útil:

```
t_start_eff = max(Tiempo_Estabilizacion, 45)
```

El mínimo de 45 s garantiza que siempre se descartan al menos los primeros 45 segundos, incluso si la estabilización se detectó antes (por seguridad ante falsas estabilizaciones tempranas).

Si `Tiempo_Estabilizacion = NaN` (no se detectó):
```
t_start_eff = 45
```

Se usa el mínimo por defecto. El "castigo" por no detectar estabilización se aplica vía `Calidad = FLAG_mecánico`, no vía un inicio más tardío.

---

## 4. Métricas del tramo estabilizado

**Objetivo:** calcular las métricas fisiológicas definitivas del día sobre el tramo limpio y estable: pulso medio, variabilidad cardíaca, y una verificación de que el tramo era realmente estable hasta el final.

### 4.1 Tramo operativo (tras tail-trim)

```
Tramo = RR_clean con: t_end >= t_start_eff AND t_end <= t_end_eff
```

Es decir: los latidos limpios que caen entre el punto de estabilización y el final efectivo (sin los últimos 15 s).

### 4.2 Métricas principales

Con `RR_tramo_s = RR_tramo_ms / 1000`:

| Métrica | Cálculo | Qué representa |
|---------|---------|----------------|
| `RRbar_s` | mean(RR_tramo_s) | Intervalo medio entre latidos (inversa del pulso) |
| `HR_stable` | 60 / RRbar_s | Pulso medio en el tramo estable (lpm) |
| `RMSSD_stable` | RMSSD(RR_tramo_s) × 1000 [ms] | Variabilidad cardíaca principal (tono vagal) |
| `lnRMSSD` | ln(RMSSD_stable) | Logaritmo natural de RMSSD (simetriza la distribución para cálculos estadísticos) |

### 4.3 RMSSD_stable_last2 (verificación de cola)

Se calcula un RMSSD adicional solo sobre los últimos 120 s del tramo, para verificar que la señal era estable hasta el final (no estaba cambiando cuando paró la grabación).

```
tail = RR del tramo con: t_end >= (t_end_eff - 120) AND t_end <= t_end_eff
n_pairs_tail = len(tail) - 1

if n_pairs_tail < 60:
    RMSSD_stable_last2 = NaN    # insuficiente material en la cola
else:
    RMSSD_stable_last2 = RMSSD(tail) × 1000
```

### 4.4 HRV_Stability

Se evalúa si el tramo era realmente estable mirando la cola (últimos 120 s). Cualquiera de estas condiciones marca Unstable:

| Condición | Qué indica | Resultado |
|-----------|-----------|-----------|
| duración efectiva cola < 75 s | Muy poco material al final, no se puede verificar | Unstable |
| n_pairs_tail < 60 | Pocos latidos válidos en la cola | Unstable |
| CV_120 = std(RR_tail_s) / mean(RR_tail_s) > 0.20 | Los intervalos oscilaban demasiado al final | Unstable |
| RMSSD_stable_last2 = NaN | No se pudo calcular RMSSD de la cola | Unstable |
| abs(RMSSD_stable_last2 - RMSSD_stable) / RMSSD_stable > 0.15 | La variabilidad de la cola discrepa más de un 15% de la del tramo completo | Unstable |
| Ninguna de las anteriores | Todo coherente | OK |

**NOTA:** `Tiempo_Estabilizacion = NaN` NO fuerza Unstable. Son conceptos distintos: la latencia mide si la señal se estabilizó al principio; HRV_Stability mide si era estable al final. El "castigo" por latencia missing se materializa vía `Calidad` (FLAG_mecánico), no vía `HRV_Stability`.

---

## 5. INVALID, Calidad, unidades

**Objetivo:** clasificar la medición del día en tres niveles de usabilidad (INVALID / FLAG_mecánico / OK) según la severidad de los problemas detectados.

### 5.1 INVALID (exclusión dura)

La medición se descarta completamente si:
- `Artifact_pct > 20%` (demasiado ruidosa) **O**
- `HR_stable < 35 lpm` o `HR_stable > 100 lpm` (fuera de rango fisiológico para reposo supino)

INVALID implica:
- El día no entra en ninguna ventana histórica (ni ROLL3, ni baselines, ni residual)
- No se genera gate ni color
- `Calidad = INVALID`

### 5.2 Calidad (OK vs FLAG_mecánico)

Si el día NO es INVALID, se clasifica entre OK (fiable) y FLAG_mecánico (existe pero con dudas).

**Regla especial:** Si `Tiempo_Estabilizacion = NaN` (la señal nunca se estabilizó) → forzar `Calidad = FLAG_mecánico`, independientemente de todo lo demás.

De lo contrario, `Calidad = OK` si se cumplen **todas** estas condiciones:
```
Artifact_pct <= 10%  AND
60 <= Lat_eff <= 600  AND
HRV_Stability = OK
```

Donde `Lat_eff = max(Tiempo_Estabilizacion, 60)` es una variable interna (no se guarda en el CSV) que asegura que la latencia mínima considerada "razonable" es 60 s.

Si no cumple todas las condiciones → `Calidad = FLAG_mecánico`

### 5.3 Chequeos de unidades (obligatorios en QA)

Verificaciones de coherencia para detectar bugs o errores de conversión:

| Verificación | Valor esperado | Si falla |
|--------------|----------------|----------|
| `duration` en el CSV | ~800–1400 ms en supino | Posible error de unidades (¿se guardó en segundos?) |
| `RRbar_s` | ~0.8–1.6 s | Valores fuera de esto indican problema grave |
| `HR_stable ≈ 60 / RRbar_s` | Error relativo ≤ 0.1% | Si no se cumple, hay un bug en el cálculo |
| `lnRMSSD` | ~3.4–4.5 (si RMSSD ~30–90 ms) | Valores fuera sugieren error de unidades en RMSSD |

### 5.4 Flags (vocabulario cerrado)

Cada flag marca una incidencia específica detectada durante el procesamiento. Un día puede tener múltiples flags (separados por `|`).

| Flag | Cuándo se activa | Consecuencia |
|------|------------------|--------------|
| `LAT_NAN` | No se detectó punto de estabilización | Fuerza FLAG_mecánico |
| `ART_GT10` | Artifact_pct > 10% | Impide Calidad=OK |
| `ART_GT20` | Artifact_pct > 20% | Fuerza INVALID |
| `STAB_TAIL_SHORT` | Cola < 75 s o n_pairs_tail < 60 | Fuerza Unstable |
| `STAB_CV120_HIGH` | CV de cola > 0.20 | Fuerza Unstable |
| `STAB_LAST2_NAN` | RMSSD_stable_last2 = NaN | Fuerza Unstable |
| `STAB_LAST2_MISMATCH` | Discrepancia last2 vs stable > 15% | Fuerza Unstable |
| `BETA_CLIPPED` | beta_mode = clipped | Solo informativo (BETA_AUDIT) |
| `BETA_FROZEN` | beta_mode = frozen | Solo informativo (BETA_AUDIT) |
| `BETA_NONE` | beta_mode = none | Solo informativo (BETA_AUDIT) |
| `RESCUE_MODE` | CORE rescatado sin pipeline completo | Solo informativo |

### 5.5 Notes (trazabilidad)

Cada fila de CORE incluye un campo Notes con metadatos técnicos del procesamiento, en formato `clave=valor` separado por `; `.

Claves mínimas (siempre presentes):
- `src` — nombre del fichero RR de origen
- `dur_raw`, `dur_eff` — duración total de la grabación y duración efectiva (tras tail-trim) en segundos
- `t_start_eff`, `dur_tramo`, `dur_tail` — inicio del tramo, duración del tramo, duración de la cola
- `n_total`, `n_base`, `n_clean`, `n_tramo`, `n_tail` — conteo de latidos en cada etapa del pipeline
- `off`, `oor`, `dRR` — desglose de artefactos: offline, fuera de rango, y filtro delta
- `lat_mode` — NUM (se detectó estabilización) o NAN (no se detectó)
- `stab` — OK o Unstable

---

## 6. Beta / cRMSSD (legacy, para BETA_AUDIT)

**Objetivo:** calcular un modelo alométrico que captura la relación natural entre pulso y variabilidad cardíaca, y usarlo para "corregir" el RMSSD descontando el efecto del pulso. Este modelo era el corazón del sistema V3 pero en V4-lite ya no se usa para el gate — se conserva solo para comparación histórica.

**IMPORTANTE:** Beta/cRMSSD se calcula como best-effort. Si falla por cualquier motivo, CORE se escribe igualmente (las columnas de BETA_AUDIT quedan con NaN).

### 6.1 Ventana del modelo

Para día D:
- Ventana: días [D-90, D-1] (shift-1, 90 días previos)
- Usar solo días con `Calidad != INVALID`

### 6.2 Requisitos mínimos

Para que el modelo sea estimable:
- `N90_valid >= 60` (al menos 60 días válidos en la ventana de 90)
- `IQR(RRbar_s) >= 0.03` (variación suficiente en el pulso para estimar la pendiente)

### 6.3 Estimación

Se ajusta una regresión lineal en espacio logarítmico (relación alométrica):

```python
x = ln(RRbar_s)        # winsorizado P10-P90 (recortando extremos)
y = ln(RMSSD_stable)    # winsorizado P10-P90
beta_est, R² = OLS(x, y)
```

`beta_est` es la pendiente: cuánto cambia ln(RMSSD) por cada unidad de cambio en ln(RR). Típicamente entre 0.5 y 2.0.

### 6.4 Modos de beta

| Modo | Cuándo se aplica | Qué pasa |
|------|------------------|----------|
| `active` | beta_est válido, estable, dentro de rango | Se usa directamente |
| `clipped` | beta_est fuera de [0.1, 3.0] | Se recorta al límite más cercano |
| `frozen` | beta_est inestable (R² < 0.10 o salto > 0.15 respecto al día anterior) | Se reutiliza el beta del día anterior |
| `none` | No hay suficiente historial para estimar | No se calcula corrección |

### 6.5 Corrección

```
cRMSSD = RMSSD × (RRbar_s / RR_ref)^(-beta_use)
```

Donde `RR_ref = mediana(RRbar_s)` en la ventana de 90 días. La idea: si tu RR de hoy es más bajo que tu mediana (pulso más alto), el factor de corrección compensa al alza el RMSSD.

---

# PARTE II: Decisor CORE → FINAL/DASHBOARD (V4-lite)

**Revisión de módulo:** V4-lite r2026-02-12  
**Objetivo:** a partir de las métricas fisiológicas del día (CORE), decidir si puedes meter intensidad, si debes moderar, o si toca descansar. El decisor es robusto y **no depende operativamente del modelo beta/cRMSSD** (que queda relegado a BETA_AUDIT).

El decisor funciona en 7 pasos: clasificación de calidad → suavizado → baselines → gate 2D → override por sombras → residual → acción.

---

## 7. Alcance del decisor

Este decisor toma CORE (ya procesado) y genera:

1) **Gate diario de intensidad** — VERDE/ÁMBAR/ROJO/NO: ¿puedes entrenar fuerte hoy?
2) **Sombras de baseline** (BASE42 y BASE28): ¿tu "normal" está cambiando antes de que lo vea el baseline principal?
3) **Residual** (desacople HRV↔RR): para tu pulso de hoy, ¿tu HRV es mejor o peor de lo esperable?
4) **Acumulación** (rachas de ROJO/NO) y warning de baseline degradado

**NO** proporciona:
- Procesamiento de RR crudo (ver Parte I)
- Decisión semanal de progresión (requiere integrar carga + rendimiento)
- Diagnóstico médico

---

## 8. Flujo de datos

```
ENDURANCE_HRV_master_CORE.csv (entrada)
ENDURANCE_HRV_sleep.csv (entrada opcional, para reason_text)
                    │
                    ▼
┌─────────────────────────────────────────┐
│  endurance_v4lite.py                    │
│  1. Clasificar calidad (clean/flag)     │
│  2. Suavizado ROLL3 (solo clean)        │
│  3. Baselines BASE60 + SWC             │
│  3b. Veto agudo (bypass ROLL3 si caída) │
│  4. Gate 2D BASE60                      │
│  5. Sombras BASE42/BASE28              │
│  6. Override opcional (modo O3)         │
│  7. Residual (BASE60) + sufijo          │
│  8. Acción + acumulación + warning      │
│  9. Reason_text (sleep.csv si existe) │
└─────────────────────────────────────────┘
     │
     ├──► ENDURANCE_HRV_master_FINAL.csv (auditable, 53 cols)
     │
     └──► ENDURANCE_HRV_master_DASHBOARD.csv (operativo, 10 cols)
```

---

## 9. Calidad y quality_flag (Opción B)

**Objetivo:** decidir cómo tratar cada día según la fiabilidad de su medición. La idea clave es que un dato dudoso no se descarta completamente (como haría INVALID), sino que se conserva para ver la tendencia pero no se permite tomar decisiones de intensidad sobre él.

### 9.1 Clasificación de días

| Categoría | Condición | Qué pasa con el día |
|-----------|-----------|---------------------|
| INVALID | `Calidad == INVALID` | Se ignora completamente: no entra en ROLL3, ni en baselines, ni en residual. Gate = NO. |
| quality_flag | `Calidad=FLAG_mecánico` OR `HRV_Stability=Unstable` OR `Artifact_pct>10%` | Se calcula el gate 2D (para no perder la señal de tendencia), pero la acción se fuerza a SUAVE — no se puede justificar intensidad con un dato dudoso. |
| clean | `Calidad=OK` AND `HRV_Stability=OK` AND `Artifact_pct<=10%` | Opera normalmente. Es el único tipo de día que entra en ROLL3 y baselines. |

### 9.2 Reglas clave

- **ROLL3 y baselines** se calculan **solo con días clean** — así la referencia contra la que se compara siempre es "limpia".
- Con `quality_flag=True`, el día se conserva (no se borra) y se calcula gate, pero **Action_detail = SUAVE_QUALITY**.
- `INVALID` no entra en ningún cálculo (ni ROLL3, ni baselines, ni residual).

---

## 10. Suavizado (ROLL3)

**Objetivo:** en vez de comparar el dato crudo de hoy contra el baseline (lo que sería muy ruidoso, porque la HRV varía bastante día a día), se suaviza tomando la media de los 3 últimos días fiables. Esto filtra fluctuaciones puntuales sin perder sensibilidad ante cambios sostenidos.

Definición para el día *t*:

```python
lnRMSSD_used(t) = mean(lnRMSSD_today) en los últimos 3 días clean ≤ t
HR_used(t)      = mean(HR_today)      en los últimos 3 días clean ≤ t
n_roll3         = nº días usados (debe ser 3)
```

Si `n_roll3 < 3` (no hay suficientes días clean recientes) → `gate_base60 = NO`, `gate_razon_base60 = ROLL3_INSUF`. Esto ocurre al inicio del histórico o tras rachas de días INVALID/FLAG.

---

## 11. Baselines (shift-1)

**Objetivo:** establecer tu "normal" — el nivel de HRV y pulso que sirve como referencia para decidir si hoy estás mejor, igual o peor de lo habitual. Se usan tres ventanas de diferente longitud para capturar tanto la tendencia estable (60 días) como cambios recientes (42 y 28 días).

### 11.1 BASE60 (principal)

Ventana: `[t-60d, t)` — los 60 días previos a hoy, **solo días clean**, excluyendo hoy (shift-1).

```python
ln_base60 = median(lnRMSSD_today) en ventana
HR_base60 = median(HR_today)      en ventana
n_base60  = nº días clean en ventana
```

Se usa **mediana** (no media) porque es robusta a outliers: un par de días extremos no desplazan tu referencia.

Requisito: `n_base60 >= 30` (al menos la mitad de los 60 días deben ser clean). Si no se cumple: `gate_base60 = NO`, `gate_razon_base60 = BASE60_INSUF`.

### 11.2 SWC robusto (BASE60)

El SWC (Smallest Worthwhile Change) define cuánto tiene que moverse tu dato respecto al baseline para que se considere una señal real (no ruido). Se calcula por variable dentro de la ventana BASE60:

```python
robust_sd = MAD × 1.4826      # SD robusta: equivalente a SD pero usando MAD
SWC = 0.5 × robust_sd         # el cambio mínimo significativo es medio SD
```

- `SWC_ln` se calcula sobre `lnRMSSD_today` en la ventana
- `SWC_HR` se calcula sobre `HR_today` en la ventana

Si `SWC` resulta NaN o 0 (dispersión nula, datos insuficientes) → `gate_base60 = NO`, `gate_razon_base60 = SWC_NAN/0`.

### 11.3 Sombras BASE42 y BASE28 (informativas)

Se calculan igual que BASE60 (medianas + SWC), pero con ventanas más cortas: `[t-42d, t)` y `[t-28d, t)`.

**¿Para qué?** BASE60 es intencionadamente lenta — tarda en reflejar cambios de régimen. Si tu HRV lleva 3 semanas bajando, BASE60 todavía "recuerda" los buenos días de hace 2 meses. Las sombras, con ventanas más cortas, detectan esa tendencia antes.

**Requisito mínimo (sombras):**
- Regla general: `min_clean_shadow(W) = max(ceil(0.5×W), 10)` días clean en `[t-W, t)` (shift-1).
- Para `W=42`: `n_base42 >= 21`.
- Para `W=28`: `n_base28 >= 14`.

Si `n_baseXX` no alcanza su mínimo, entonces `gate_shadowXX = NO` y `gate_razon_shadowXX = BASEXX_INSUF`.

> Las sombras **no gobiernan** por defecto (modo O2); sirven para alertar de transiciones. En modo O3 pueden ajustar el gate final.

---

## 11bis. Veto agudo (bypass de ROLL3)

**Objetivo:** detectar caídas bruscas de HRV que el suavizado ROLL3 enmascara. ROLL3 promedia los últimos 3 días clean, lo que amortigua cambios puntuales — esto es deseable para filtrar ruido, pero peligroso cuando hay una caída aguda real: si ayer y anteayer estaban bien y hoy tu HRV se desploma, ROLL3 aún muestra un valor cercano al normal, ocultando la señal de alarma.

### 11bis.1 Constantes

| Parámetro | Valor | Por qué |
|-----------|-------|---------|
| `SWC_FLOOR` | 0.04879 (= ln(1.05)) | Floor mínimo para SWC. Evita que SWC sea trivialmente pequeño en periodos de variabilidad muy baja, lo que causaría falsos positivos constantes |
| `VETO_MULT` | 2.0 | Multiplicador del umbral. Veto se activa si la caída supera 2 × SWC (un cambio que duplica el "mínimo significativo") |

### 11bis.2 Lógica (dentro del loop principal, tras BASE60+SWC)

Se ejecuta solo para días con `is_clean=True` y con `BASE60` válido (n_base60 ≥ 30):

```python
# SWC efectivo con floor
swc_v4 = max(SWC_ln, SWC_FLOOR)

# ¿El dato RAW de hoy cae bruscamente respecto al baseline?
if lnRMSSD_today < (ln_base60 - VETO_MULT × swc_v4):
    veto_agudo = True
    ln_pre_veto = lnRMSSD_used    # guardar valor ROLL3 original
    lnRMSSD_used = lnRMSSD_today  # forzar dato crudo
    HR_used = HR_today             # forzar HR crudo también
```

Después del veto, el Gate 2D (§12) se calcula con el dato **crudo** en vez del suavizado. Esto significa que la caída se refleja inmediatamente en el gate, sin esperar a que ROLL3 la absorba.

### 11bis.3 Por qué se fuerza también HR_used

Forzar `HR_used = HR_today` mantiene coherencia temporal: si la HRV bajó bruscamente hoy, el HR que la acompaña es el de hoy, no un promedio de los últimos 3 días. Esto permite que el Gate 2D evalúe la convergencia real del día (ambas señales del mismo momento).

### 11bis.4 Columnas generadas

| Columna | Tipo | Qué contiene |
|---------|------|--------------|
| `veto_agudo` | bool | True si se activó el bypass |
| `ln_pre_veto` | float | Valor de lnRMSSD_used (ROLL3) antes del override. NaN si no hubo veto |
| `swc_ln_floor` | float | SWC efectivo usado (con floor aplicado) |

### 11bis.5 Efecto validado (datos históricos)

En 274 días de datos reales, el veto se activa en 54 días (20%) y cambia el gate en 19: 7 VERDE→ROJO, 11 ÁMBAR→ROJO, 1 ROJO→ÁMBAR (este último porque el ROLL3 inflaba artificialmente el HR por días previos malos, y el dato crudo mostraba HR normal).

---

## 12. Gate 2D por baseline

**Objetivo:** comparar tu estado suavizado de hoy (ROLL3) contra tu baseline y decidir un color. La regla es bidimensional ("2D") porque mira **dos señales simultáneamente**: HRV y pulso. La convergencia de ambas da mucha más confianza que una sola.

### 12.1 Gate BASE60 (base)

```python
d_ln_60 = lnRMSSD_used - ln_base60     # delta de HRV (negativo = peor)
d_HR_60 = HR_used      - HR_base60     # delta de pulso (positivo = peor)

ln_bajo = d_ln_60 < -SWC_ln     # ¿HRV significativamente por debajo de tu normal?
hr_alto = d_HR_60 >  SWC_HR     # ¿Pulso significativamente por encima de tu normal?
```

| Condición | gate_base60 | gate_razon_base60 | Interpretación |
|-----------|-------------|-------------------|----------------|
| Ambos fuera | ROJO | 2D_AMBOS | Convergencia de señales: alta confianza de fatiga/estrés |
| Solo ln_bajo | ÁMBAR | 2D_LN | HRV baja pero pulso normal: señal parcial, prudencia |
| Solo hr_alto | ÁMBAR | 2D_HR | Pulso alto pero HRV normal: posible sueño malo, estrés puntual |
| Ninguno | VERDE | 2D_OK | Ambas señales dentro de tu rango normal |

### 12.2 Gate sombras (BASE42 / BASE28)

Misma regla 2D aplicada con `baseXX` y `SWC_XX` de cada sombra. Resultado:

- `gate_shadow42`, `gate_razon_shadow42`, `n_base42`
- `gate_shadow28`, `gate_razon_shadow28`, `n_base28`

---

## 13. Modo de decisión (O2 vs O3)

**Objetivo:** definir quién tiene la última palabra — solo BASE60, o BASE60 con posible ajuste por las sombras.

### 13.1 Modos disponibles

- **O2_SHADOW (default):** `gate_final = gate_base60`. Las sombras se reportan pero no influyen en la decisión. Es el modo más conservador.
- **O3_OVERRIDE_PERSIST_2of3 (opcional):** permite que las sombras ajusten el gate final ±1 nivel si discrepan de forma persistente (al menos 2 de los últimos 3 días).

El modo activo se expone como `decision_mode`.

### 13.2 Cómo se informa en O2_SHADOW

Se reportan todos los gates (base + sombras), pero la decisión es directa:

- `gate_final = gate_base60`
- `decision_path = BASE60_ONLY`
- `override_reason = ""` (vacío)

### 13.3 Override opcional (O3_OVERRIDE_PERSIST_2of3)

**Idea:** BASE60 sigue siendo el ancla, pero si una sombra insiste durante varios días en que el gate debería ser diferente, se ajusta. Esto permite reaccionar a cambios de régimen sin abandonar la estabilidad de BASE60.

**Definiciones:**

Orden de severidad: `VERDE < ÁMBAR < ROJO` (NO no participa en el override).

`shadow_pick(t)` — qué sombra se consulta:
  - Si `gate_shadow28` es VERDE/ÁMBAR/ROJO → usar sombra 28 (la más reactiva)
  - Si no está disponible, pero `gate_shadow42` es VERDE/ÁMBAR/ROJO → usar sombra 42
  - Si ninguna está disponible → no hay override posible

**Persistencia (regla 2 de 3):**
- Sea `S = {t-2, t-1, t}` (los últimos 3 días, incluyendo hoy).
- `persist_down` si en ≥2 de esos 3 días: la sombra dice un gate **peor** que BASE60.
- `persist_up` si en ≥2 de esos 3 días: la sombra dice un gate **mejor** que BASE60.

**Aplicación:**
- Si `persist_down` → `gate_final = downgrade(gate_base60, 1)` (ej: VERDE → ÁMBAR)
- Si `persist_up` → `gate_final = upgrade(gate_base60, 1)` (ej: ÁMBAR → VERDE)
- Si ambos a la vez (raro) → no override, prevalece BASE60

**Auditoría (siempre trazable):**
- `gate_final_delta` en {-1, 0, +1}
- `decision_path`: `BASE60_ONLY` / `OVERRIDE_DOWN_28_2of3` / `OVERRIDE_UP_28_2of3` / `OVERRIDE_DOWN_42_2of3` / `OVERRIDE_UP_42_2of3`
- `override_reason`: texto corto (ej. `shadow28 peor 2/3`)

---

## 14. Residual (desacople HRV↔RR) y sufijos

**Objetivo:** añadir un matiz al gate. El gate 2D compara tu estado contra tu baseline, pero no distingue si tu HRV está baja porque tu pulso subió (relación natural) o porque algo más está pasando. El residual separa ambos efectos: modela la relación normal HRV↔pulso con tus últimos 60 días, y mide cuánto se desvía tu día de esa relación.

### 14.1 Definición

Modelo (BASE60, shift-1, solo clean):

- Variables:
  - `x = ln(RRbar_s)` del día (RR medio en segundos, en escala logarítmica)
  - `y = lnRMSSD_today` del día

Ajuste lineal (OLS) en ventana `[t-60d, t)` (el modelo se entrena sin el día que se evalúa):

```python
y = a + b·x
```

Residual del día *t*:

```python
residual_ln = y_t - (a + b·x_t)
```

- `residual_ln > 0` → tu HRV es **más alta** de lo que predice tu pulso (buena señal parasimpática)
- `residual_ln < 0` → tu HRV es **más baja** de lo esperable dado tu pulso (posible fatiga/estrés no explicada por el pulso)

### 14.2 Normalización (residual_z)

Para interpretar la magnitud del residual, se normaliza con una escala robusta calculada sobre los residuales de entrenamiento (los 60 días de la ventana):

```python
robust_sd_res = MAD(residuals) × 1.4826
SWC_res = 0.5 × robust_sd_res
residual_z = residual_ln / SWC_res
```

Si `SWC_res` resulta NaN o 0 → `residual_z = NaN` y `residual_tag = ""`.

### 14.3 Tag (sufijo)

Sufijo simétrico basado en `residual_z`:

- `+` si `residual_z ≥ +0.5`, `++` si `≥ +1.0`, `+++` si `≥ +2.0`
- `-` si `residual_z ≤ -0.5`, `--` si `≤ -1.0`, `---` si `≤ -2.0`

`residual_tag` es **informativo** y **no recolorea** el gate. Es un matiz para interpretar, no para decidir.

### 14.4 Badge operativo

El badge combina el gate final con el sufijo del residual:

- `gate_badge = gate_final + residual_tag`
- Ejemplos: `VERDE+` (todo bien, HRV mejor de lo esperable), `ÁMBAR--` (prudencia, y además HRV peor de lo que predice el pulso), `ROJO` (sin sufijo, residual dentro de rango normal)

---

## 15. Acción operativa

**Objetivo:** traducir el gate y la calidad en una instrucción concreta de entrenamiento, y detectar acumulación de días malos que justifique una descarga.

### 15.1 Mapping básico

| gate_final | quality_flag | Action | En la práctica |
|-----------|--------------|--------|----------------|
| VERDE | False | INTENSIDAD_OK | Puedes ejecutar intervalos, sesiones duras, lo planificado |
| VERDE | True | SUAVE_O_DESCANSO | El gate es bueno pero el dato no es fiable → no arriesgar |
| ÁMBAR | False | Z2_O_TEMPO_SUAVE | Sin HIIT, pero puedes hacer volumen aeróbico (Z1-Z2) |
| ÁMBAR | True | SUAVE_O_DESCANSO | Dato dudoso + señal parcial → conservador |
| ROJO | * | SUAVE_O_DESCANSO | Señal clara de fatiga/estrés → regenerativo o descanso |
| NO | * | SUAVE_O_DESCANSO | Sin datos suficientes para decidir → no arriesgar |

### 15.2 Action_detail (acumulación)

La acumulación detecta si los días malos se están amontonando:

```python
bad_streak = racha consecutiva de (ROJO o NO) hasta hoy
bad_7d = nº de (ROJO o NO) en los últimos 7 días
```

| Condición | Action_detail | Significado |
|-----------|---------------|-------------|
| gate_final=VERDE y no quality_flag | EJECUTAR_PLAN | Todo limpio, adelante con lo planificado |
| gate_final=ÁMBAR y no quality_flag | SIN_HIIT | Quita intervalos, mantén volumen |
| quality_flag=True | SUAVE_QUALITY | Dato dudoso, no justifica intensidad |
| bad_streak ≥ 2 OR bad_7d ≥ 3 | DESCARGA | Acumulación de señales negativas → reducir carga semanal |
| Otros ROJO/NO | SUAVE | Mal día puntual, regenerativo |

### 15.3 Reason_text (contexto explicativo)

**Objetivo:** generar un texto que explique *por qué* el sistema tomó esa decisión, combinando información del gate con datos contextuales de sueño y carga. Es informativo — **no recolorea** ni modifica el gate ni la acción.

**Fuentes:** combina datos del pipeline HRV (veto agudo, saturación, quality) con:
- `ENDURANCE_HRV_sleep.csv` — sueño Polar (noche corta, fragmentada, nightly_rmssd)
- `ENDURANCE_HRV_sessions_day.csv` — carga de entrenamiento (load_3d, work_7d, z3_7d)

**Generación:** Se evalúan las siguientes condiciones en orden. Las que se cumplen se concatenan con separador ` | `:

| Prioridad | Condición | Fuente | Texto generado |
|-----------|-----------|--------|----------------|
| 1 | `veto_agudo == True` | HRV pipeline | `Caída aguda HRV: raw=X vs base=Y (drop=Z, umbral=-W)` |
| 2 | `d_ln > 2 × swc_v4` | HRV pipeline | `HRV excesivamente alto: posible saturación parasimpática` |
| 3 | `quality_flag == True` y gate VERDE/ÁMBAR | HRV pipeline | `Dato dudoso: limitar a Z1-Z2 máx 90min` |
| 4 | `polar_sleep_duration_min < sleep_dur_p10` | sleep.csv | `Noche corta (Xmin < P10=Y)` |
| 5 | `polar_interruptions_long > sleep_int_p90` | sleep.csv | `Noche fragmentada (X interr > P90=Y)` |
| 6 | VERDE + `polar_night_rmssd < 25` | sleep.csv | `VERDE pero nightly_rmssd bajo: vigilar` |
| 7 | ROJO + `polar_night_rmssd > 45` | sleep.csv | `ROJO con nightly_rmssd alto: posible confusor` |
| 8 | `load_3d > 250` (con `load_3d_nobs >= 2`) | sessions_day.csv | `Carga acumulada alta (load_3d=X)` |
| 9 | `work_7d_sum > 200` | sessions_day.csv | `Volumen semanal alto (work_7d=Xmin)` |
| 10 | `z3_7d_sum > 60` | sessions_day.csv | `Z3 acumulado alto (z3_7d=Xmin)` |
| 11 | ROJO + `load_day < 30` + sueño OK | sessions_day.csv | `ROJO sin carga previa ni sueño malo: revisar otros factores` |
| 12 | VERDE + `load_3d > 200` | sessions_day.csv | `VERDE con carga acumulada: precaución intensidad` |

**Umbrales de sueño:** Basados en percentiles propios (P10, P90), NO en valores fijos. Se recalculan con todo el histórico disponible. Esto adapta los avisos a TU patrón de sueño.

**Umbrales de carga:** Valores absolutos. El check de load_3d solo se ejecuta si `load_3d_nobs >= 2` (cobertura real de la métrica, no "días con sesiones").

**Si sleep.csv no existe:** Solo se generan las condiciones 1-3 (basadas en datos HRV) + 8-12 (si sessions_day.csv existe). Si tampoco existe sessions_day.csv, solo condiciones 1-3.

---

## 16. Warning baseline60_degraded

**Objetivo:** avisar cuando tu capacidad actual (baseline de los últimos 60 días) está significativamente por debajo de tu mejor momento conocido. Es un indicador a medio plazo — no cambia el gate del día, pero sugiere que las decisiones de progresión semanal deberían ser conservadoras.

**Dos modos disponibles:**

### 16.1 Modo healthy85 (default)

Compara tu baseline actual contra un periodo de referencia donde estabas bien entrenado y sano:

```python
healthy_rmssd = mediana(exp(lnRMSSD)) en periodo sano (ej: jul-sep 2025)
healthy_hr    = mediana(HR_stable) en periodo sano
threshold = 0.85 × healthy_rmssd
degraded = exp(ln_base60) < threshold
```

Si tu RMSSD mediano actual está por debajo del 85% de tu mejor momento → warning.

### 16.2 Modo p20

Usa el percentil 20 de tu histórico completo como umbral (no necesita periodo de referencia definido manualmente):

```python
threshold = P20(exp(ln_base60) histórico)
degraded = exp(ln_base60) < threshold
```

Si tu baseline actual está por debajo del P20 de todos tus baselines históricos → warning.

**IMPORTANTE:** El warning es **informativo**, NO recolorea el gate. No distingue entre baseline bajo por enfermedad, por temporada de descanso, o por adaptación a volumen alto sostenido (donde es esperable).

---

## 17. Archivos de salida (V4 r2026-03-01)

| Archivo | Para qué | Columnas |
|---------|----------|----------|
| `ENDURANCE_HRV_master_CORE.csv` | La medición fisiológica del día, sin decisiones | 12 |
| `ENDURANCE_HRV_master_FINAL.csv` | Gate, veto agudo, sombras, residual, reason_text y auditoría completa | 53 |
| `ENDURANCE_HRV_master_DASHBOARD.csv` | Lo esencial para decidir en 10 segundos + reason_text | 10 |
| `ENDURANCE_HRV_sleep.csv` | Sueño nocturno y recuperación (Polar) | 17 |
| `ENDURANCE_HRV_sessions.csv` | Detalle de cada sesión de entrenamiento | 42 |
| `ENDURANCE_HRV_sessions_day.csv` | Agregados diarios + rolling con cobertura (_nobs) | 31 |
| `metadata.json` | Trazabilidad pipeline sesiones (versión, params, sampling rate) | — |
| `ENDURANCE_HRV_master_BETA_AUDIT.csv` | Modelo beta del V3, para comparación histórica | 13 |

El contrato exacto (columnas, orden, tipos) de CORE/FINAL/DASHBOARD/SLEEP está en `ENDURANCE_HRV_Estructura.md`.
El contrato de sessions/sessions_day/metadata está en `ENDURANCE_HRV_Sessions_Schema_v3.1.md`.

---

## 18. Uso diario

```bash
# 1. Flujo operativo recomendado (descarga/actualiza + procesa)
python polar_hrv_automation.py --process

# 2. Reproceso manual (si necesitas depurar por pasos)
python endurance_hrv.py --rr-file data/rr_downloads/Franz_YYYY-MM-DD_RR.csv --data-dir data
python endurance_v4lite.py --data-dir data

# 3. Ver resultado del día
tail -1 data/ENDURANCE_HRV_master_DASHBOARD.csv
```

---

## 19. Limitaciones conocidas

1. **ROLL3 requiere 3 días clean previos** — Los primeros días del histórico o tras rachas de INVALID/FLAG serán NO (sin gate)
2. **BASE60 requiere 30 días clean en 60 días** — Se necesitan ~60 días calendario mínimo para que el sistema empiece a operar
3. **SWC puede ser muy estrecho** si tu variabilidad histórica es baja — esto hace que el gate sea muy sensible a cambios pequeños, aumentando los falsos ámbar/rojo
4. **Sombras BASE28/42 pueden ser más sensibles al ruido** por tener ventanas más cortas — por eso no mandan por defecto (modo O2)
5. **El residual es un overlay estadístico** — útil para matizar, pero no es un "diagnóstico". Un residual negativo persistente merece atención, pero un pico puntual puede ser ruido
6. **El warning no distingue causa** — un baseline bajo puede ser enfermedad, temporada de descanso, o adaptación a volumen alto sostenido. Requiere interpretación humana
7. **No hay integración de carga externa en el gate** — El gate solo ve HRV y pulso, no TSS/TRIMP ni horas de sueño. El `reason_text` aporta contexto de sueño (via `ENDURANCE_HRV_sleep.csv`) y carga (via `ENDURANCE_HRV_sessions_day.csv`), pero es informativo — no modifica el gate. La decisión final siempre requiere interpretación humana
8. **`ENDURANCE_HRV_sleep.csv` y `sessions_day.csv` dependen de APIs externas** — Si Polar AccessLink no responde, los campos de sueño quedan NaN. Si Intervals.icu no responde, `sessions_day.csv` no se genera. El gate y la acción no se ven afectados
9. **Veto agudo puede ser conservador** — Al forzar el dato crudo, un día puntualmente malo (ej: medición defectuosa que pasó quality checks) puede producir un ROJO innecesario. El SWC_FLOOR de 0.04879 limita falsos positivos pero no los elimina
10. **Percentiles de sueño se estabilizan tras ~30 noches** — Durante las primeras semanas, los P10/P90 pueden ser inestables y generar avisos inapropiados

---

## 20. QA obligatorio

**Objetivo:** verificar periódicamente que el sistema está funcionando correctamente, que los datos tienen sentido, y que no hay bugs ni derivas silenciosas.

### 20.1 Plantilla QA global

Archivo: `ENDURANCE_HRV_QA_global_ALL_STD.md`

Secciones obligatorias (si una no aplica, incluirla con "Sin incidencias"):
1. **Cobertura** — rango de fechas, número total de días
2. **Calidad** — tabla de distribución OK / FLAG_mecánico / INVALID
3. **Detalle INVALID** — qué días y por qué causa
4. **Detalle FLAG_mecánico** — qué días y qué flags activaron
5. **Sanity checks** — HR, Artifact_pct, Latencia dentro de rangos esperados
6. **Flags de estabilidad** — conteos de cada flag STAB_*
7. **Top outliers** — días con valores extremos de RMSSD, HR, artefactos
8. **Distribución gate_final** — proporción de VERDE/ÁMBAR/ROJO/NO (y gate_badge)
9. **% quality_flag=True** — proporción de días con dato dudoso

### 20.2 Plantilla QA beta

Archivo: `ENDURANCE_HRV_QA_beta_ALL_STD.md`

Secciones obligatorias:
1. **Cobertura** — rango y completitud
2. **Resumen beta_mode** — distribución de active/clipped/frozen/none
3. **Calidad del ajuste 90d** — distribución de R²
4. **Corrección aplicada** — distribución de |ln_corr|
5. **Top 10 días por |ln_corr|** — días donde la corrección fue más grande
6. **Incidencias** — periodos con none/frozen

---

## Histórico de cambios

| Fecha | Cambio |
|-------|--------|
| 2026-03-01 v4.1 | sleep.csv simplificado: 34→17 cols (solo Polar sleep/nightly, sin Intervals) |
| 2026-03-01 v4.1 | reason_text dual source: sueño de sleep.csv, carga de sessions_day.csv |
| 2026-03-01 v4.1 | Nuevos archivos sessions.csv (42 cols), sessions_day.csv (31 cols), metadata.json |
| 2026-03-01 v4.1 | reason_text: TSB/load_3d_p90 reemplazados por load_3d+nobs, work_7d, z3_7d (umbrales absolutos) |
| 2026-02-23 v4 | Añadido veto agudo (§11bis): bypass ROLL3 en caídas agudas, con SWC_FLOOR y VETO_MULT |
| 2026-02-23 v4 | Añadido reason_text (§15.3): texto explicativo contextual con sueño, carga y coherencia gate↔contexto |
| 2026-02-23 v4 | Nuevo archivo sleep.csv (§17): sidecar de sueño Polar |
| 2026-02-23 v4 | FINAL bumped 49→53 cols, DASHBOARD 9→10 cols |
| 2026-02-12 v3 | Redactado didáctico: intros explicativas en cada sección, "por qué" antes de "cómo" |
| 2026-02-12 v2 | Reintegradas fórmulas warning §16, sección QA §20, limitaciones §19 completas |
| 2026-02-12 | Añadido residual (BASE60) + sufijos + gate_badge |
| 2026-02-12 | Añadidas sombras BASE42/BASE28 y modo de decisión (O2/O3) |
| 2026-02-12 | Añadidos campos de auditoría: decision_path, override_reason, gate_final_delta |
| 2026-02-09 | Unificación Spec_RR + Spec_Gate en documento único |
| 2026-02-09 | Opción B: quality_flag permite calcular gate pero fuerza SUAVE |
| 2026-02-09 | Beta/cRMSSD como best-effort (no bloquea CORE) |

---

Fin del documento.

