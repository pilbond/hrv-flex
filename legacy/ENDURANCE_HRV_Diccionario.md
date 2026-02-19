# Endurance HRV — Diccionario de columnas del master operativo (algoritmo v3.x · Opción A)

Revisión del documento: r2025-12-25-UPDATE3 (25-dic-2025)

Este documento explica, en lenguaje llano, **para qué sirve cada columna** del archivo maestro operativo `RR_master_OPERATIVO_v3_<rango>.csv`.

---

## **IMPORTANTE - Alcance del diccionario**

Este documento describe:
1. **Columnas del maestro operativo estándar** (las que aparecen en RR_master_OPERATIVO_v3_<rango>.csv)
2. **Columnas QA** (solo para reportes de auditoría, marcadas con 🔍)
3. **Columnas del dataset P1/P2 opcional** (marcadas con 📊)

Si una columna no está marcada, va en el maestro operativo.

Nota sobre informes QA (MD):
- Los informes `QA_global` y `QA_beta` son **reportes** (no datasets).
- Su estructura está **congelada por plantilla fija** para evitar deriva entre meses (ver especificación técnica).

---

## 0. Cómo leer el CSV la primera vez

Si abres el maestro por primera vez, sigue este orden:

### **Paso 1 (Gate - ¿es confiable?)**
1. Mira `Calidad` → Si es `INVALID`, ignora el resto (día perdido)
2. Mira `HRV_Stability` → Si es `Unstable`, toma con pinzas
3. Mira `Artifact_pct` → Si es >10%, puede haber ruido

### **Paso 2 (Decisión - ¿qué hago hoy?)**
4. Mira `Color_Agudo_Diario` → Tu semáforo principal
5. Mira `Color_Tendencia` → Tu contexto de fondo
6. **Solo si chocan**, mira `Color_Tiebreak`

### **Paso 3 (Auditoría - ¿por qué salió así?)**
7. Mira `HR_stable` vs tu normal → ¿Pulso alto/bajo hoy?
8. Mira `RMSSD_stable` vs percentiles P15/P30
9. Ignora el resto hasta que necesites depurar

### **Lo que NO debes hacer**
- ❌ Comparar RMSSD de un día con otro sin contexto
- ❌ Buscar "valores buenos/malos" universales
- ❌ Ignorar el Gate cuando el color te gusta

---

## 1. Valores típicos (solo orientación inicial)

**IMPORTANTE:** Estos valores son orientativos para la primera semana. Después de 30 días, tu sistema se calibra con TUS percentiles.

### Pulso supino matinal (HR_stable)
- Deportista resistencia bien entrenado: 40-55 lpm
- Deportista recreativo: 50-65 lpm
- Sedentario: 60-80 lpm
- **Alarma:** >80 lpm o <35 lpm → probablemente INVALID

### RMSSD supino matinal (RMSSD_stable)
- Muy entrenado: 60-100 ms
- Entrenado: 40-70 ms
- Recreativo: 25-50 ms
- **Lo importante NO es el número absoluto**, sino TU tendencia

### Artifact_pct
- Excelente: <5%
- Bueno: 5-10%
- Límite: 10-20% (FLAG_mecánico)
- Malo: >20% (INVALID)

### Tiempo_Estabilizacion
- **Qué es:** segundos necesarios para que la señal alcance un estado suficientemente estable (criterio de latencia del algoritmo).
- **Interpretación rápida (orientativa):**
  - Ideal: 60–120 s
  - Aceptable: 120–300 s
  - Sospechoso: >300 s (revisar respiración/movimiento/entorno)
  - Problema: >600 s (no puede ser `Calidad=OK`) 
  - **Latencia missing:** `NaN` significa que no se detectó estabilización con el criterio definido.
- **Regla operativa asociada:** si `Tiempo_Estabilizacion = NaN` → se fuerza `Calidad = FLAG_mecánico` y se añade `LAT_NAN` en `Flags`.

### Z-scores (z_HRV_28, z_HRVc_28) 📊
- Normal: entre -1.0 y +1.0
- Llamativo: -2.0 a -1.0 (ámbar en P2)
- Alarma: <-2.0 (rojo en P2)
- **Nota:** Estos se calculan contra TU historial, no son universales

---

## A) Identificación y trazabilidad

### `Fecha`
- **Qué es:** el día de la medición (YYYY-MM-DD).
- **Para qué sirve:** ordenar el histórico y calcular comparativas con días previos.
- **Cómo usarla:** es la clave principal (no debería haber duplicados).

### `Fuente`
- **Qué es:** referencia al archivo/origen de la medición (por ejemplo, el nombre del CSV original o el ZIP).
- **Para qué sirve:** auditoría y depuración si un día sale "raro".
- **Cómo usarla:** si hay dudas de calidad, lo primero es volver al archivo fuente.

*(Si tu export no incluye `Fuente`, es recomendable añadirla: ahorra horas de depuración.)*

---

### `Flags`
- **Qué es:** lista de etiquetas **generadas automáticamente** por el analizador para resumir incidencias mecánicas/QA del día.
- **Formato:** texto en una sola celda, con valores separados por `|` (sin espacios).  
  Ejemplo: `LAT_NAN|STAB_CV120_HIGH|ART_GT10`
- **Cómo usarlo:** si `Calidad=FLAG_mecánico` o `HRV_Stability=Unstable`, mira `Flags` para saber **por qué**.

**Vocabulario (cerrado) y significado:**
- `LAT_NAN`: no se detectó estabilización (Tiempo_Estabilizacion = NaN). **Regla:** fuerza `Calidad=FLAG_mecánico`.
- `ART_GT10`: `Artifact_pct > 10%` (no puede ser Calidad=OK).
- `ART_GT20`: `Artifact_pct > 20%` (Calidad=INVALID).
- `STAB_TAIL_SHORT`: cola efectiva insuficiente (duración < 75 s o pares RR insuficientes) → `HRV_Stability=Unstable`.
- `STAB_CV120_HIGH`: CV en los últimos 120 s > 0.20 → `HRV_Stability=Unstable`.
- `STAB_LAST2_NAN`: `RMSSD_stable_last2` = NaN → `HRV_Stability=Unstable`.
- `STAB_LAST2_MISMATCH`: discrepancia relativa >15% entre `RMSSD_stable_last2` y `RMSSD_stable` → `HRV_Stability=Unstable`.
- `BETA_CLIPPED`: `beta_mode="clipped"` (β estimada fuera de [0.1, 3.0] y recortada).
- `BETA_FROZEN`: `beta_mode="frozen"` (β congelada por inestabilidad del ajuste).
- `BETA_NONE`: `beta_mode="none"` (no hay corrección alométrica ese día).
- `QA_UNIT_WARN`: chequeos de unidades/coherencia fallan (p. ej., HR_stable no cuadra con RRbar_s).

### `Notes`
- **Qué es:** anotación **generada automáticamente** para añadir contexto operativo y trazabilidad sin crear columnas nuevas.
- **Importante:** aunque conceptualmente es “texto libre”, desde esta revisión se **estandariza** para que sea consistente y parsable.

**Formato estándar (determinista):**
- Una sola celda con pares `clave=valor` separados por `; ` (punto y coma + espacio).

**Claves mínimas (siempre presentes; si no aplican → `NA`):**
- `src`: nombre del fichero RR
- Duraciones (formato `M:SS` o `H:MM:SS`):
  - `dur_raw`: duración total RAW hasta el último RR
  - `dur_eff`: duración efectiva tras tail-trim de 15 s
  - `t_start_eff`: instante (desde inicio) a partir del cual se calculan métricas estables
  - `dur_tramo`: duración del tramo usado para métricas estables (`t_end_eff - t_start_eff`)
  - `dur_tail`: duración real de cola usada para estabilidad (máximo 120 s)
- Conteos: `n_total`, `n_base`, `n_clean`, `n_tramo`, `n_tail`
- Desglose de artefactos: `off` (offline=1), `oor` (fuera de rango), `dRR` (ΔRR>20%)
- `lat_mode`: `NUM` si hay estabilización detectada, `NAN` si no
- `stab`: copia de `HRV_Stability` (OK/Unstable)
- `note_free`: campo opcional (texto corto) si hay algo relevante que no encaja en flags/números

**Ejemplo (humano):**
`src=Franz_Dunn_2025-12-24_07-27-45_RR.CSV; dur_raw=8:25; dur_eff=8:10; t_start_eff=1:00; dur_tramo=7:10; dur_tail=2:00; n_total=423; n_base=423; n_clean=422; n_tramo=...; n_tail=...; off=0; oor=0; dRR=1; lat_mode=NUM; stab=OK; note_free=NA`


---
## B) Gate - Fiabilidad (LEER PRIMERO)

### `Calidad`
- **Qué es:** veredicto operativo sobre si el día es utilizable:
  - `OK` = usable.
  - `FLAG_mecánico` = usable, pero con bandera amarilla (posible problema de medición).
  - `INVALID` = **no usable**.
- **Para qué sirve:** es el **filtro número 1** antes de mirar colores.
- **Cómo usarla:**
  - `INVALID` → **no decidir por HRV** (día "Indef").
  - `FLAG_mecánico` → evita decisiones agresivas basadas en HRV.
  - Si ves `LAT_NAN` en `Flags`, significa que no se detectó estabilización: es un aviso mecánico/QA (no se interpreta como fatiga por sí mismo).

### `HRV_Stability`
- **Qué es:** etiqueta simple de estabilidad del tramo final (por ejemplo: `OK` o `Unstable`).
- **Para qué sirve:** si sale `Unstable`, aunque el RMSSD sea alto/bajo, **no conviene justificar intensidad** con esa medición.
- **Cómo usarla:** es una señal de "prudencia": reduce confianza en los colores.

### `Artifact_pct`
- **Qué es:** porcentaje del registro descartado por **artefactos** (latidos mal detectados, offline=1, valores imposibles…).
- **Para qué sirve:** es uno de los **controles de calidad** más importantes.
- **Cómo interpretarlo (orientativo):**
  - <5% = excelente
  - 5-10% = bueno
  - 10-20% = límite (FLAG_mecánico)
  - >20% = malo (INVALID)

### `Tiempo_Estabilizacion`
- **Qué es:** cuántos segundos tarda la señal en "estabilizarse" desde que empiezas a medir.
- **Para qué sirve:** indica si hoy te costó más "entrar en reposo real" (o si el registro está contaminado por movimiento/respiración irregular).
- **Cómo interpretarlo:** valores muy altos o muy variables día a día suelen apuntar a problemas de protocolo o calidad.

---

## C) Los 3 colores (decisión diaria)

> Los colores solo tienen sentido si `Calidad` no es `INVALID`.

### `Color_Tendencia`
- **Qué es:** semáforo de "fondo" (último mes) calculado con percentiles (P15/P30) sobre `cRMSSD`.
- **Para qué sirve:** evitar meterte intensidad cuando vienes "tocando fondo" aunque hoy el agudo salga bien.
- **Cómo usarlo:** es tu freno de fondo (contexto).

### `Color_Agudo_Diario`
- **Qué es:** semáforo de "hoy" (agudo), basado en desviaciones respecto a tu normal (z-scores).
- **Para qué sirve:** es el **semáforo principal del día**.
- **Cómo usarlo:** guía la decisión de si hoy metes calidad o no (siempre respetando el gate).

### `Color_Tiebreak`
- **Qué es:** color de desempate basado en HRV corregida (z-score sobre `lncRMSSD`).
- **Para qué sirve:** solo se consulta si **Color_Agudo_Diario** y **Color_Tendencia** chocan. “el tiebreak detecta si el color agudo está distorsionado por un cambio anormal de HR/RR; puede bajar o subir alarma según el caso”.
- **Cómo usarlo:** rompe empates; no sustituye al agudo cuando todo está alineado.

### Valores posibles de color
- `Verde` / `Ámbar` / `Rojo`
- `Indef` = el sistema **no puede** dar un color fiable (por falta de histórico o por `INVALID`).

---

## D) Métricas base del día (la "fotografía" de hoy)

### `HR_stable`
- **Qué es:** frecuencia cardiaca media (latidos/min) en el tramo válido usado para calcular.
- **Para qué sirve:** contexto: si hoy estás con el pulso más alto de lo normal, suele ser señal de estrés/fatiga/recuperación incompleta.
- **Cómo interpretarlo:** compara con tu normal (histórico), no con un valor universal.

### `RRbar_s`
- **Qué es:** media del intervalo entre latidos (en segundos). Es otra forma de expresar el pulso.
- **Para qué sirve:** se usa para correcciones internas (hacer comparables días con pulso distinto).
- **Cómo interpretarlo:** más alto suele equivaler a pulso más bajo (y viceversa).

### `RMSSD_stable`
- **Qué es:** la variación "rápida" entre latidos (HRV) calculada con el método del sistema.
- **Para qué sirve:** es la **señal principal** de HRV "cruda" del día.
- **Cómo interpretarlo:** **no** lo interpretes por un número fijo; lo importante es tu tendencia y tu comparación contra tus propios percentiles.

### `RMSSD_stable_last2`
- **Qué es:** RMSSD calculado solo en la parte final del registro (últimos 120 segundos).
- **Para qué sirve:** verificar que la señal fue estable HASTA EL FINAL.

**Visualización:**
```
|-------- Medición completa (ej. 5 minutos) ---------|
[60s lat]  [tramo principal]  [últimos 120s]  [15s trim]
             ↑                      ↑              ↑
        RMSSD_stable           RMSSD_stable_last2  (descartado)
```

**Interpretación:**
- Si RMSSD_stable ≈ RMSSD_stable_last2 → señal estable (HRV_Stability = OK)
- Si difieren >15% → posible movimiento al final (HRV_Stability = Unstable)

**Ejemplo numérico:**
```
RMSSD_stable = 60 ms
RMSSD_stable_last2 = 63 ms
Diferencia: (63-60)/60 = 5% → OK ✅

RMSSD_stable = 60 ms
RMSSD_stable_last2 = 48 ms
Diferencia: (48-60)/60 = -20% → Unstable ⚠️
```

---

## E) HRV "corregida" y variables de control (comparabilidad entre días)

### `cRMSSD`
- **Qué es:** RMSSD ajustado para que días con pulso distinto sean más comparables.
- **Para qué sirve:** es la señal que alimenta el semáforo de **tendencia**.
- **Cómo interpretarlo:** igual que RMSSD: por histórico y percentiles propios.

**Nota nomenclatura:** "cRMSSD" = "corrected RMSSD" (corregido por cambios en HR/RR usando beta).

### `lnRMSSD`
- **Qué es:** RMSSD pasado a escala logarítmica (no cambia el orden "alto/bajo", solo lo hace más estable para estadística).
- **Para qué sirve:** cálculo de z-scores y control de "anomalías".
- **Cómo interpretarlo:** es más "técnico"; normalmente mirarás el color, no este número.

### `lncRMSSD` (NO se guarda, solo se calcula internamente)
- **Qué es:** logaritmo de `cRMSSD`.
- **Para qué sirve:** base del **desempate** (`Color_Tiebreak`) y de z-scores corregidos.

**¿Por qué existe lncRMSSD?**

Imagina dos escenarios donde tu HRV sale "baja":

**Escenario A (fatiga real):**
- Tu HR está normal (60 lpm)
- Tu RMSSD está bajo (30 ms)
- **Causa:** Estrés/fatiga real del sistema nervioso
- **Acción:** Descansar

**Escenario B ("rojo falso"):**
- Tu HR está anormalmente bajo hoy (45 lpm, por ej. sueño extra profundo)
- Tu RMSSD sale bajo (30 ms) porque hay una relación alométrica: a HR más bajo, RMSSD tiende a bajar
- **Causa:** Cambio en HR, no fatiga real
- **Acción:** Podrías entrenar normal

**Flujo de transformaciones:**
```
RMSSD_stable (crudo del día, en ms)
    ↓
lnRMSSD = ln(RMSSD_stable)
    ↓ [se usa para Color_Agudo_Diario]
    ↓
cRMSSD = RMSSD_stable * (RRbar_s / RR_ref_90d)^(-beta_use_90d)
    ↓ [corrige por cambios de HR]
    ↓
lncRMSSD = ln(cRMSSD)
    ↓ [se usa para Color_Tiebreak]
```

**Ejemplo numérico:**

| Día | HR_stable | RMSSD_stable | lnRMSSD | cRMSSD | lncRMSSD | Color_Agudo | Color_Tiebreak |
|-----|-----------|--------------|---------|--------|----------|-------------|----------------|
| Normal | 55 lpm | 60 ms | 4.09 | 60 ms | 4.09 | Verde | Verde |
| Hoy | 48 lpm | 45 ms | 3.81 | 58 ms | 4.06 | **Rojo** | **Verde** |

**Interpretación:**
- `lnRMSSD` cayó mucho → Color_Agudo_Diario = Rojo
- **PERO** `lncRMSSD` casi no cambió → Color_Tiebreak = Verde
- **Conclusión:** El rojo es "falso"; el RMSSD bajo se explica por HR bajo (no por fatiga)

### `ln_corr`
- **Qué es:** cuánto "corrige" el sistema al pasar de RMSSD a cRMSSD.
- **Para qué sirve:** auditoría: si un día la corrección es extrema, conviene revisar contexto (pulso anómalo, medición rara).
- **Cómo interpretarlo:** no es "bueno/malo" por sí mismo; es una pista.

---

## F) "Dónde caes" respecto a tu normal (comparadores vs historial)

### Nota sobre "shift-1" (ventanas históricas)

Cuando el sistema calcula percentiles o z-scores para el día D, **NO incluye el día D** en la ventana de comparación.

**Ejemplo visual (ventana 30 días):**
```
Hoy es 20-dic-2025 (día D)

Ventana para calcular P15/P30:
[20-nov-2025 ... 19-dic-2025]  ← 30 días PREVIOS
         ↑                  ↑
       día D-30           día D-1

20-dic-2025 NO entra aquí
```

**¿Por qué?**
Para evitar "sesgo circular": si tu HRV hoy está anormalmente bajo, no queremos que eso "contamine" los percentiles contra los que te comparas.

### `Nprev30`
- **Qué es:** número de días válidos previos disponibles en la ventana de 30 días.
- **Definición de “día válido”:** `Calidad != INVALID` (incluye `OK` y `FLAG_mecánico`; `HRV_Stability=Unstable` no excluye el día).
- **Para qué sirve:** si hay pocos días válidos, el color de tendencia puede ser `Indef`.
- **Cómo interpretarlo:** cuanto más bajo, menos confiable es el semáforo de tendencia.

### `P15_cRMSSD_30d` y `P30_cRMSSD_30d`
- **Qué es:** dos "límites" calculados a partir de tu propio histórico reciente (30 días previos).
- **Para qué sirve:** separar "normal" de "bajo" con tu referencia personal (no con valores universales).
- **Cómo interpretarlo (idea simple):**
  - Por encima de P30 → suele ser "bien".
  - Entre P15 y P30 → "zona intermedia".
  - Por debajo de P15 → "bajo".

### `HR_z14`
- **Qué es:** indicador de cuánto se desvía tu pulso de hoy respecto a tu normal reciente (14 días previos).
- **Para qué sirve:** cuando el pulso está "demasiado alto", el sistema penaliza lecturas "demasiado optimistas".
- **Cómo interpretarlo:** cuanto más positivo, más "alto" está tu pulso vs tu normal.

### `z_HRV_28` 📊 (solo dataset P1/P2)
- **Qué es:** indicador de cuánto se desvía tu HRV (en escala log) respecto a tu normal reciente (28 días previos).
- **Para qué sirve:** base del semáforo **agudo**.
- **Cómo interpretarlo:** valores muy negativos suelen indicar HRV más baja de lo habitual.

### `z_HRVc_28` 📊 (solo dataset P1/P2)
- **Qué es:** lo mismo que `z_HRV_28` pero usando HRV **corregida** (`lncRMSSD`).
- **Para qué sirve:** base del **desempate**.

---

## G) Columnas de auditoría β (opcionales, pero recomendables)

Estas columnas existen para entender **por qué** `cRMSSD` cambia respecto a `RMSSD_stable`.

### `beta_est_90d`
- **Qué es:** estimación del efecto del pulso sobre tu HRV (basada en ~90 días).
- **Para qué sirve:** corregir el hecho de que tu HRV natural varía con tu pulso.

**Ejemplo didáctico:**
Si tu pulso baja 10 lpm (por ejemplo, dormiste 9h en vez de 7h), tu RMSSD puede bajar ~15% aunque NO estés fatigado. El sistema detecta esto y "corrige" el RMSSD para que sea comparable con días de pulso normal.

**Analogía:** Es como ajustar la temperatura ambiente cuando mides la fiebre. Si tu termómetro marca 36.8°C pero la habitación está a 30°C, no significa que tengas hipotermia.

**Valores típicos:** beta entre 0.5 y 2.0 es normal. Valores fuera de [0.1, 3.0] se recortan automáticamente.

### `beta_use_90d`
- **Qué es:** el valor realmente usado por el sistema (puede ser recortado o congelado).
- **Para qué sirve:** saber qué corrección se aplicó de verdad.

### `beta_mode`
- **Qué es:** estado del sistema de corrección (`active`, `clipped`, `frozen`, `none`).
- **Para qué sirve:** indica si la corrección está funcionando normal o en modo "seguridad".

### `RR_ref_90d`
- **Qué es:** referencia de RR medio (de tu histórico) usada como "ancla".
- **Para qué sirve:** estabiliza la corrección.

### `N90_valid`
- **Qué es:** cuántos días válidos hay en el bloque de 90 días.
- **Para qué sirve:** medir si la corrección se apoya en suficiente histórico.

### `IQR_RRbar_90d`
- **Qué es:** medida simple de dispersión de RR medio en 90 días.
- **Para qué sirve:** si es extremo, la corrección puede ser menos fiable.

### `R2_winsor_90d`
- **Qué es:** indicador de "calidad del ajuste" interno (muy técnico).
- **Para qué sirve:** auditoría; si cae mucho de forma persistente, revisar la corrección.

---

## H) Resumen del "material" disponible (columnas QA)

### `total_dur_s` 🔍 (solo QA)
- **Qué es:** duración total registrada (en segundos).
- **Para qué sirve:** detectar mediciones demasiado cortas o cortadas.
- **Cómo usarla:** si es anormalmente baja para tu protocolo, sospecha de calidad.

### `t_end_eff` 🔍 (solo QA)
- **Qué es:** "final efectivo" del registro tras recortes internos (por ejemplo, recorte de cola).
- **Para qué sirve:** saber hasta dónde llega el tramo realmente usado para calcular.
- **Cómo usarla:** si difiere mucho de `total_dur_s`, hubo mucho recorte por artefactos o por reglas del sistema.

---

## 9. Ejemplos de lectura (3 casos típicos)

### Caso 1: Día perfecto
```csv
Fecha,Calidad,HRV_Stability,Artifact_pct,HR_stable,RMSSD_stable,Color_Agudo_Diario,Color_Tendencia,Color_Tiebreak
2025-12-15,OK,OK,3.2,52,68,Verde,Verde,Verde
```
**Interpretación:**
- Gate perfecto (Calidad=OK, Stab=OK, Artifact bajo)
- Pulso normal para ti (52 lpm)
- HRV alta (68 ms)
- Los 3 colores verdes → Entrena normal

---

### Caso 2: Rojo real (fatiga)
```csv
Fecha,Calidad,HRV_Stability,Artifact_pct,HR_stable,RMSSD_stable,Color_Agudo_Diario,Color_Tendencia,Color_Tiebreak
2025-12-16,OK,OK,5.8,61,38,Rojo,Rojo,Rojo
```
**Interpretación:**
- Gate OK (dato confiable)
- Pulso alto (+9 lpm vs día anterior)
- HRV baja (38 ms, -44% vs día anterior)
- Los 3 colores rojos → Fatiga real, descanso

---

### Caso 3: "Rojo falso" (desempate actúa)
```csv
Fecha,Calidad,HRV_Stability,Artifact_pct,HR_stable,RMSSD_stable,Color_Agudo_Diario,Color_Tendencia,Color_Tiebreak
2025-12-17,OK,OK,6.1,45,42,Rojo,Verde,Verde
```
**Interpretación:**
- Gate OK
- Pulso muy bajo (45 lpm, -7 lpm vs día anterior)
- HRV bajó (42 ms) pero es esperable con HR tan bajo
- Color_Agudo_Diario = Rojo (HRV crudo bajo)
- Color_Tiebreak = Verde (HRV corregido normal)
- **Decisión:** Bajar alarma a Ámbar (sección 9.3 de Spec). Probablemente no es fatiga, solo efecto de haber dormido extra bien.

---

## 10. Diagrama de flujo (cómo se decide cada mañana)

```
┌─────────────────────────────────────────┐
│  Abres el CSV del día                   │
└─────────────────┬───────────────────────┘
                  │
                  ▼
       ┌──────────────────────┐
       │ ¿Calidad = INVALID?  │
       └──────────┬───────────┘
                  │
         ┌────────┴────────┐
         │ SÍ              │ NO
         ▼                 ▼
    ┌─────────┐      ┌──────────────────────┐
    │ No usar │      │ ¿Calidad = FLAG       │
    │ HRV hoy │      │  o Stab = Unstable?   │
    └─────────┘      └──────────┬───────────┘
                                │
                       ┌────────┴────────┐
                       │ SÍ              │ NO
                       ▼                 ▼
                  ┌─────────┐      ┌──────────────┐
                  │ Solo    │      │ Gate OK →    │
                  │ prudencia│      │ Ver colores  │
                  └─────────┘      └──────┬───────┘
                                          │
                                          ▼
                              ┌───────────────────────┐
                              │ Color_Agudo_Diario    │
                              │ + Color_Tendencia     │
                              └───────────┬───────────┘
                                          │
                              ┌───────────┴───────────┐
                              │ ¿Ambos alineados?     │
                              └───────────┬───────────┘
                                          │
                                 ┌────────┴────────┐
                                 │ SÍ              │ NO
                                 ▼                 ▼
                          ┌──────────┐      ┌────────────────┐
                          │ Decisión │      │ Consultar      │
                          │ directa  │      │ Color_Tiebreak │
                          └──────────┘      └────────────────┘
```

---

## 11. Glosario de términos técnicos

### MAD (Median Absolute Deviation)
Medida de dispersión robusta (menos sensible a outliers que la desviación estándar). Se usa para calcular z-scores más estables.

### Percentil tipo 7 (Hyndman & Fan)
Método específico de calcular percentiles. Es el que usa numpy por defecto.  
**Para implementadores:** `np.percentile` o `df.quantile(interpolation='linear')`

### Shift-1 (ventanas históricas)
El día de hoy NO entra en su propia ventana de comparación. Siempre se usan días PREVIOS.

### Día válido (para ventanas)
Un día se considera **válido** si `Calidad != INVALID`. Esto **incluye** días con `Calidad=FLAG_mecánico`.
`HRV_Stability=Unstable` **no excluye** el día de las ventanas históricas; solo indica menor fiabilidad mecánica.

### Winsorización
Recortar valores extremos al 10% y 90% para evitar que outliers distorsionen regresiones.

### Z-score robusto
Medida de "cuántas desviaciones" estás de tu normal, calculada con mediana+MAD en vez de media+SD (más resistente a días raros).

### Beta (modelo alométrico)
Coeficiente que captura cómo tu HRV cambia naturalmente con cambios en tu pulso. Típicamente entre 0.5 y 2.0.

### cRMSSD ("c" = corrected)
RMSSD ajustado por cambios de pulso usando el modelo beta. Permite comparar días con diferentes HR de base.

### lncRMSSD
Logaritmo de cRMSSD. Se usa para calcular Color_Tiebreak y detectar si un color "raro" se debe a fatiga real o a cambios de HR.

---

## Sugerencia de orden de columnas (lectura humana)

1. Identificación: `Fecha`, `Fuente`
2. Gate (PRIMERO): `Calidad`, `HRV_Stability`, `Artifact_pct`, `Tiempo_Estabilizacion`, `Flags`, `Notes`
3. Decisión: `Color_Agudo_Diario`, `Color_Tendencia`, `Color_Tiebreak`
4. Métricas base: `HR_stable`, `RRbar_s`, `RMSSD_stable`, `RMSSD_stable_last2`
5. Señales comparación: `cRMSSD`, `lnRMSSD`, `HR_z14`, `Nprev30`, `P15_cRMSSD_30d`, `P30_cRMSSD_30d`
6. Auditoría β: `beta_*`, `RR_ref_90d`, `N90_valid`, `IQR_RRbar_90d`, `R2_winsor_90d`, `ln_corr`


## Otros 

Problemas latencia alta

A) Causas mecánicas (las más frecuentes)

Te mueves, ajustas postura, tensas piernas/abdomen, tragas, toses.
La banda pierde contacto o hay micro-artefactos no marcados como offline.
Estás frío, incómodo, o con respiración irregular por postura.
Estas causas generan “ruido” que se parece a fisiología, pero no lo es.

B) Causas fisiológicas reales

Activación simpática al despertar (estrés, dolor, anticipación).
Respiración muy variable (suspiros, cambios de ritmo, apnea breve).
Microdespertares o sueño fragmentado: entras al registro aún “activado”.
Recuperación mala/estado inflamatorio: el control autonómico está inestable.
Aquí la latencia está diciendo algo real: “hoy tu sistema no está en un estado estacionario”.
Por qué es “malo” y baja la confiabilidad
Porque RMSSD no es un número fijo, es una estimación. Para que sea comparable día a día, necesitas medirlo en condiciones similares y en un estado relativamente estable.
Cuando la latencia es alta, pasan dos problemas:
Estás midiendo una transición, no un estado
El inicio de la mañana suele ser un periodo de ajuste (respiración, tono vagal, CO₂, alerta).
Si el tramo estable llega tarde, el RMSSD del día depende mucho de “en qué minuto” decides medir.
Te queda poco “material estable”
Si estabilizas tarde, el tramo útil se acorta.
Con 60–90 s estables, el RMSSD es mucho más sensible al azar (y a 2–3 respiraciones raras) que con 3–5 min.
Resultado: el número puede cambiar bastante sin que tu fisiología “global” haya cambiado tanto.
Cómo interpretarlo correctamente

Latencia alta no significa automáticamente “fatiga”. Significa: “este día, la medición tiene menos calidad o tu sistema está menos estacionario”.

En tu esquema, eso justifica FLAG_mecánico porque el dato:

puede ser real (inestabilidad autonómica),

o puede ser medición peor,
y no hay forma fiable de separarlo solo con RR.

Qué hacer cuando la latencia sale alta (procedimiento)

Mira si también sube Artifact_pct o aparece STAB_LAST2_MISMATCH / TAIL_SHORT.
Si sí: más probable que sea mecánico.

Repite la medición 10–15 min después (si puedes), mismo protocolo.

Si mejora claramente: era transición/mecánico.

Si sigue igual: probablemente es fisiológico (estrés/sueño/enfermedad).

No tomes decisiones de carga basadas solo en ese RMSSD.
Usa el gate: si está flaggeado, el color (si lo hay) se interpreta “con pinzas”.

Métrica simple para ti (sin estadística)

Si la estabilización tarda mucho y el tramo estable final es corto, la medición es menos fiable.

Si la estabilización tarda mucho pero luego tienes un tramo largo y limpio (varios minutos), es menos problemático: te costó “entrar”, pero la estimación final puede ser válida.

Fin del documento.
