ENDURANCE HRV — Especificación técnica de implementación (algoritmo v3.x (Opción A))
Revisión del documento: r2025-12-25-UPDATE3 (25-dic-2025)

Changelog (resumen):
- r2025-12-25-UPDATE3: estandariza `Notes` como string determinista (clave=valor; `; `), añade claves mínimas para trazabilidad (sin añadir columnas nuevas).

Jerarquía (cuando haya discrepancias entre documentos):
1) Esta especificación técnica (implementación) manda sobre todo lo demás.
2) ENDURANCE_HRV_Estructura_Datos_Master define el contrato/orden de columnas, sin redefinir lógica.
3) ENDURANCE_HRV_Diccionario interpreta salidas; no introduce cálculos ni reglas nuevas.

Propósito:
Procesar RR matinales supinos (Polar H10) de forma determinista y robusta, produciendo 3 semáforos (gate + agudo + tendencia) y un desempate (Tiebreak) que se consulta solo si hay conflicto.

============================================================
0) ENTRADAS, SALIDAS, DEFINICIONES
============================================================

0.1 Entradas
- Ficheros RR en CSV (UTF-8, separador coma).
- Cabecera EXACTA: duration,offline
  - duration: intervalo RR en milisegundos (float)
  - offline: 0/1 (int), donde 1 = artefacto marcado por dispositivo
- Los ficheros se entregan normalmente en ZIP mensual con muchos *_RR.CSV.
- REQUISITO: el nombre del archivo contiene la fecha "YYYY-MM-DD".
  - Si además contiene hora "HH-MM-SS", se usa para resolver duplicados.

0.2 Definiciones clave
- "Eje temporal real": el tiempo se define por la suma acumulada de RR RAW, y NO se comprime al filtrar.
- "Día válido": `Calidad != INVALID` (incluye `OK` y `FLAG_mecánico`). `HRV_Stability` (OK/Unstable) NO excluye el día; solo informa fiabilidad mecánica.
- "Shift-1": ventanas históricas (14/30/90) se calculan con días anteriores; el día D no entra en su propia referencia.
- **Sufijo "_stable"**: indica que la métrica se calcula sobre el tramo estabilizado (tras descartar latencia inicial y recorte de cola final).
  
  Ejemplos: `HR_stable`, `RMSSD_stable`, `RMSSD_stable_last2`
  
  **Nota histórica:** Este sufijo reemplaza el anterior "_capas" usado en v2.x. En v3.x solo se usa "_stable".

0.3 Umbrales y constantes (v3)
- RR plausible (para RR_base): [300, 2000] ms
- Anti-cascada ΔRR: umbral 20% (ver sección 2.2)
- Ventanas latencia: 60 s, paso 30 s
- Umbral latencia: rel_change < 0.08
- Recorte de cola (tail-trim): 15 s (ver sección 3.1)
- Reglas estabilidad (cola): ventana final 120 s terminando en t_end_eff
- Requisito last2: n_pairs_last2 >= 60 (en la cola final)
- INVALID si:
  - Artifact_pct > 20%  O
  - HR_stable fuera de [30, 100] lpm

0.4 Salidas (archivos)
- El master incluye `Flags` (vocabulario cerrado) y `Notes` (texto libre) para trazabilidad y QA.
A) Maestro operativo (CSV): ENDURANCE_HRV_master_ALL.csv  (incluye Gate + 3 colores)
B) QA global (MD): ENDURANCE_HRV_QA_global_ALL_STD.md
C) Duplicados (CSV): Duplicados_resolucion_v3_<rango>.csv
D) QA β (MD): ENDURANCE_HRV_QA_beta_ALL_STD.md
E) (Opcional) Evaluación P1/P2 (CSV): ENDURANCE_HRV_eval_P1P2_ALL.csv

============================================================
1) PARSING DE FECHAS Y RESOLUCIÓN DE DUPLICADOS
============================================================

1.1 Parse de Fecha y hora desde filename
- Extraer Fecha (date) desde la primera ocurrencia YYYY-MM-DD.
- Extraer hora (time) si aparece HH-MM-SS en el nombre.
- Si no hay fecha → el archivo se ignora y se reporta en QA.

1.2 Duplicados por Fecha (determinista)
Si hay 2+ archivos con la misma Fecha, se elige UNO con este orden estricto:
  1) preferir no-INVALID
  2) preferir Calidad=OK sobre FLAG_mecánico
  3) preferir HRV_Stability=OK
  4) preferir Tiempo_Estabilizacion numérica en [60, 600]
  5) preferir mayor duración total (s) (t_end_raw último)
  6) preferir menor Artifact_pct
  7) si hay hora: preferir la hora más temprana; si no, orden alfabético

Obligatorio: registrar en Duplicados_resolucion:
- Fecha
- lista de candidatos
- métricas clave por candidato (INVALID/Calidad/Stab/Lat/duración/Artifact_pct)
- archivo elegido y criterio por el que ganó

============================================================
2) EJE TEMPORAL Y LIMPIEZA DE RR
============================================================

2.1 Eje temporal (CRÍTICO: no compresión)
Sea RR_raw_ms[i] el RR RAW del CSV.
Definir tiempo como fin de intervalo:
  t_end[i] = cumsum(RR_raw_ms)[i] / 1000   (segundos)

Cuando se excluyen RR, los RR restantes conservan su t_end original; no se re-cumsum.

2.2 Limpieza y artefactos (CRÍTICO)
2.2.1 RR_base
- Excluir RR con offline = 1
- Excluir RR fuera de [300, 2000] ms
RR_base = RR_raw que pasa ambas condiciones.

2.2.2 Filtro anti-cascada ΔRR>20% (OBLIGATORIO)
Se aplica SOBRE RR_base en su orden original (adyacentes).
Para i = 1..len(RR_base)-1:
  delta = abs(RR_base[i] - RR_base[i-1]) / RR_base[i-1]
  si delta > 0.20 → marcar RR_base[i] para exclusión por delta
IMPORTANTE:
- El comparador SIEMPRE es RR_base[i-1], aunque RR_base[i] sea marcado.
- PROHIBIDO comparar contra "último RR aceptado".

2.2.3 RR_clean
RR_clean = RR_base sin los marcados por delta.

2.2.4 Artifact_pct "real"
Sea N_total_raw = nº RR RAW del CSV.
Sea:
  N_offline = count(offline==1)
  N_out_of_range = count(offline==0 AND RR fuera de [300,2000])
  N_delta = nº RR marcados por delta dentro de RR_base
Entonces:
  Artifact_pct = 100 * (N_offline + N_out_of_range + N_delta) / N_total_raw

(Nota: las categorías offline y out_of_range son excluyentes por definición.)

============================================================
3) VENTANAS, LATENCIA Y TRAMO EFECTIVO (CON TAIL-TRIM)
============================================================

3.1 Tail-trim (recorte de cola) — cambio activo
Objetivo: eliminar artefacto típico de parada (movimiento/toque).

- Definir duración total RAW:
  t_end_raw_last = t_end[-1]
- Definir final efectivo:
  t_end_eff = t_end_raw_last - 15 s

Aplicación:
- Antes de calcular métricas del tramo y estabilidad, excluir de RR_clean todos los RR con:
  t_end > t_end_eff

IMPORTANTE:
- Artifact_pct NO cambia por tail-trim (se calcula en RAW).
- Tiempo_Estabilizacion se calcula sobre RR_clean sin tail-trim (no debe depender del final).

3.2 RMSSD por ventanas para latencia
Ventanas de 60 s con paso 30 s.
Para cada índice w:
- ventana w cubre: [30*w, 30*w + 60)
- asignación de RR_clean a ventanas por su t_end real:
  RR pertenece a ventana w si: 30*w <= t_end < 30*w+60

Cálculo RMSSD_w:
- Convertir RR a segundos: RR_s = RR_ms / 1000
- RMSSD = sqrt(mean(diff(RR_s)^2))
- Definir n_pairs = len(RR_s) - 1
- RMSSD_w solo si n_pairs >= 20; si no → RMSSD_w = NaN

Nota de unidades:
- Aunque RMSSD se calcula sobre RR_s, se reporta en ms (multiplicar por 1000) SOLO si se desea lectura humana.
- Para consistencia del histórico Endurance, almacenar RMSSD_stable y RMSSD_w en ms.
  (lnRMSSD usa RMSSD en ms.)

3.3 Latencia (Tiempo_Estabilizacion) — en segundos
Definir:
  rel_change(a→b) = abs(RMSSD_b - RMSSD_a) / RMSSD_a
  (solo si RMSSD_a y RMSSD_b existen y RMSSD_a > 0)

Criterio primario (umbral 8%):
Tiempo_Estabilizacion = 30*k donde k es el primer índice tal que:
  rel_change(k-1→k) < 0.08  Y  rel_change(k→k+1) < 0.08
(solo si esas RMSSD_w existen)

Fallback robusto (si no existe k):
- RMSSD_target = mediana de las últimas 4 ventanas válidas (RMSSD_w definido)
- Buscar el primer k con 3 ventanas válidas consecutivas (k,k+1,k+2) cumpliendo:
  abs(RMSSD_w - RMSSD_target)/RMSSD_target < 0.08
- Si no se puede definir target o no hay 3 consecutivas → Tiempo_Estabilizacion = NaN

3.4 Separar "Latencia detectada" de "Inicio efectivo de métricas"
Guardar Tiempo_Estabilizacion tal cual se detecta, pero definir inicio operativo:
  t_start_eff = max(Tiempo_Estabilizacion, 45 s)
Si Tiempo_Estabilizacion = NaN:
  t_start_eff = 45 s
(Esto reduce sensibilidad a ruido del primer minuto.)

============================================================
4) MÉTRICAS DEL TRAMO ESTABILIZADO (sufijo "_stable") Y ESTABILIDAD
============================================================

**Nota:** El sufijo "_stable" indica que la métrica se calcula sobre el tramo estabilizado (tras descartar latencia inicial y recorte de cola), no sobre todo el archivo RAW.

4.1 Tramo operativo para métricas (tras tail-trim)
Definir tramo como RR_clean (ya tail-trim) con:
  t_end >= t_start_eff   y   t_end <= t_end_eff

4.2 Métricas del tramo estabilizado
Con RR_tramo_s = RR_tramo_ms/1000:

- RRbar_s = mean(RR_tramo_s)
- HR_stable = 60 / RRbar_s
- RMSSD_stable = RMSSD(RR_tramo_s)  [en ms para almacenar]
- lnRMSSD = ln(RMSSD_stable)        [RMSSD en ms]
- RMSSD_stable_last2:
  - Definir cola temporal de 120 s terminando en t_end_eff:
      tail = RR del tramo con t_end >= (t_end_eff - 120) y t_end <= t_end_eff
  - Requisito de suficiencia:
      n_pairs_tail = len(tail) - 1
      si n_pairs_tail < 60 → RMSSD_stable_last2 = NaN
      si n_pairs_tail >= 60 → RMSSD_stable_last2 = RMSSD(tail)

4.3 HRV_Stability (solo cola final; no depende de Lat=NaN)
Definir cola = tail (últimos 120 s terminando en t_end_eff).
Evaluar:

1) Si duración efectiva cola < 75 s o n_pairs_tail < 60 → Unstable
2) Si CV_120 = std(RR_tail_s)/mean(RR_tail_s) > 0.20 → Unstable
3) Si RMSSD_stable_last2 es NaN → Unstable
4) Si abs(RMSSD_stable_last2 - RMSSD_stable)/RMSSD_stable > 0.15 → Unstable
5) Si nada de lo anterior → OK

NOTA: Tiempo_Estabilizacion=NaN NO fuerza Unstable (esto fue un cambio deliberado para reducir falsos negativos).
El "castigo" por Lat missing se materializa vía Calidad (FLAG), no vía Stab.

REGLA (explícita): si `Tiempo_Estabilizacion = NaN` → forzar `Calidad = FLAG_mecánico` y añadir `LAT_NAN` en `Flags`. si la cola está bien.

============================================================
5) INVALID, CALIDAD, UNIDADES Y SANIDAD
============================================================

5.1 INVALID (exclusión dura de ventanas históricas)
INVALID si:
- Artifact_pct > 20%  O
- HR_stable < 35 lpm o HR_stable > 100 lpm

INVALID implica:
- no entra en ventanas 14/30/90
- Color = Indef
- Calidad = INVALID

5.2 Calidad (OK vs FLAG_mecánico)
Si NO INVALID:
- **Forzar FLAG por latencia missing:** si `Tiempo_Estabilizacion = NaN` → `Calidad = FLAG_mecánico` (aunque `HRV_Stability = OK`).
- Calidad = OK si:
  Artifact_pct <= 10%  AND
  60 <= Lat_eff <= 600  AND
  HRV_Stability = OK
Donde:
  Lat_eff = max(Tiempo_Estabilizacion, 60) si Tiempo_Estabilizacion numérica; si Tiempo_Estabilizacion=NaN → Lat_eff=60.
  **Importante:** aunque `Lat_eff=60`, si `Tiempo_Estabilizacion=NaN` la `Calidad` se fuerza a `FLAG_mecánico` (ver regla anterior).
  
**Nota:** Lat_eff es una variable interna de evaluación; NO se guarda en el maestro operativo. Solo se almacena Tiempo_Estabilizacion.

Si no cumple OK → Calidad = FLAG_mecánico

5.3 Chequeos de unidades (obligatorios en QA)
- duration debe ser ms (típicamente ~800–1400 ms en supino).
- RRbar_s típico ~0.8–1.6 s.
- Verificar coherencia exacta:
    HR_stable ≈ 60 / RRbar_s
  (error relativo <= 0.1%; si no, hay bug de unidades.)
- lnRMSSD: debe ser ln(RMSSD_en_ms). Valores típicos ~3.4–4.5 si RMSSD ~30–90 ms.

5.4 Flags y Notes (anotación/QA; no altera cálculos)
- `Flags`: lista separada por `|` con vocabulario cerrado (sin espacios). Se genera de forma determinista a partir de los campos calculados.
- `Notes`: string **determinista** en una sola celda, para trazabilidad/depuración sin introducir columnas nuevas.
  - **Formato:** pares `clave=valor` separados por `; ` (punto y coma + espacio).
  - **Claves mínimas (siempre presentes; pueden quedar vacías como `NA`):**
    - `src` (nombre del fichero RR)
    - Duraciones (formato `M:SS` o `H:MM:SS`): `dur_raw`, `dur_eff`, `t_start_eff`, `dur_tramo`, `dur_tail`
    - Conteos: `n_total`, `n_base`, `n_clean`, `n_tramo`, `n_tail`
    - Artefactos (desglose): `off`, `oor`, `dRR`
    - Latencia/estabilidad: `lat_mode` (NUM|NAN), `stab` (OK|Unstable)
    - Campo libre controlado: `note_free` (texto corto; opcional; vacío si no aplica)
  - **Obligatorio:** incluir siempre al menos `dur_raw`, `dur_eff`, `dur_tramo`, `dur_tail` (ver también Diccionario).

Vocabulario recomendado de `Flags` (mínimo):
- `LAT_NAN`: Tiempo_Estabilizacion = NaN (regla: fuerza Calidad=FLAG_mecánico)
- `ART_GT10`: Artifact_pct > 10%
- `ART_GT20`: Artifact_pct > 20% (INVALID)
- `STAB_TAIL_SHORT`: cola efectiva < 75 s o n_pairs_tail < 60
- `STAB_CV120_HIGH`: CV_120 > 0.20
- `STAB_LAST2_NAN`: RMSSD_stable_last2 = NaN
- `STAB_LAST2_MISMATCH`: discrepancia relativa last2 vs stable > 0.15
- `BETA_CLIPPED`: beta_mode = clipped
- `BETA_FROZEN`: beta_mode = frozen
- `BETA_NONE`: beta_mode = none
- `QA_UNIT_WARN`: chequeos de unidades fallan (ver 5.3)

============================================================
6) MODELO ALOMÉTRICO (β) + INSTRUMENTACIÓN (v3)
============================================================

Objetivo: corregir RMSSD por cambios de RR (HR) sin sobre-reaccionar.
Importante: el cálculo es determinista; el QA decide si hay que cambiar beta_cap (eso sería otra versión).

6.1 Ventana del modelo
Para el día D:
- Ventana: días [D-90, D-1] (shift-1)
- Usar solo días válidos (`Calidad != INVALID`). Permitir `FLAG_mecánico`. `HRV_Stability=Unstable` está permitido (no afecta a validez).

6.2 Requisitos mínimos para intentar estimar
- N90_valid >= 60
- IQR_RRbar_90d >= 0.03 s

6.3 Preparación de datos y winsorización (tipo 7)
Para cada día i en la ventana:
- x_i = ln(RRbar_s_i)
- y_i = ln(RMSSD_stable_i)   (RMSSD en ms)

Winsorizar por separado x e y al 10–90% usando cuantiles Hyndman & Fan tipo 7:
- Lx = Q7(x,0.10), Ux = Q7(x,0.90), x_w = clip(x, Lx, Ux)
- Ly = Q7(y,0.10), Uy = Q7(y,0.90), y_w = clip(y, Ly, Uy)

**Nota implementación:** Usar cuantiles tipo 7 (método lineal de Hyndman & Fan) para compatibilidad con implementaciones previas. Si usas numpy: `np.percentile` con configuración por defecto. Si usas pandas: `df.quantile()` con `interpolation='linear'`.

6.4 OLS (regresión lineal)
Ajustar:
  y_w = α + β_est * x_w + ε
Guardar:
- beta_est_90d = β_est (pre-clip)
- R2_winsor_90d = R² del ajuste en el dataset winsorizado

6.5 Reglas de estabilidad y elección de beta_use (beta_mode)
Definir beta_cap = 3.0 (v3).

Criterios para "inestable" (se congela si hay beta previo usable):
- No cumple requisitos (N90_valid < 60 o IQR < 0.03)
- R2_winsor_90d < 0.10
- salto excesivo: |beta_est_t - beta_use_{t-1}| > 0.15 (si beta_use_{t-1} existe)
- (Opcional si se calcula SE) CI ancho: 2*1.96*SE(beta) > 0.30

Reglas:
1) Si NO se puede estimar o el ajuste es inestable:
   - Si existe beta_use_{t-1} → beta_use_90d = beta_use_{t-1}, beta_mode="frozen"
   - Si no existe → beta_use_90d = NaN, beta_mode="none" y NO se corrige

2) Si se puede estimar y es estable:
   - beta_use_90d = clip(beta_est_90d, 0.1, 3.0)
   - beta_mode="clipped" si beta_est fuera de [0.1,3.0], si no "active"

6.6 RR_ref y cálculo de cRMSSD
**Nota nomenclatura:** "cRMSSD" = "corrected RMSSD" (corregido por cambios en HR/RR usando beta).

- RR_ref_90d = mediana(RRbar_s) en la ventana 90d (los días válidos usados)
Si beta_mode in {"active","clipped","frozen"}:
  cRMSSD = RMSSD_stable * (RRbar_s / RR_ref_90d)^(-beta_use_90d)
  ln_corr = ln(cRMSSD / RMSSD_stable)
Si beta_mode="none":
  cRMSSD = RMSSD_stable
  ln_corr = 0

6.7 Columnas β que se almacenan (auditoría)
- beta_est_90d
- beta_use_90d
- beta_mode ∈ {active, clipped, frozen, none}
- RR_ref_90d
- N90_valid
- IQR_RRbar_90d
- R2_winsor_90d
- ln_corr

============================================================
7) HR_z14, P15/P30 Y COLOR "PRINCIPAL" (Color_Tendencia)
============================================================

7.1 HR_z14 (robusto)
Ventana: últimos 14 días previos válidos (shift-1), mínimo 7.

Donde HR_stable_prev = [HR_stable del día D-1, D-2, ..., D-14] (solo días válidos: `Calidad != INVALID`; Unstable permitido)

Cálculo robusto:
- med = mediana(HR_stable_prev)
- MAD = mediana(|HR_prev - med|)
- σ_rob = 1.4826 * MAD
- HR_z14 = (HR_hoy - med) / σ_rob
- clamp HR_z14 a [-5, +5] y redondear a 2 decimales
Si σ_rob=0 o no hay suficientes días → HR_z14 = NaN

7.2 Percentiles P15/P30 sobre cRMSSD
Ventana: últimos 30 días previos válidos (shift-1), Nprev30 >= 15.
- P15 = Q7(cRMSSD_prev, 0.15)
- P30 = Q7(cRMSSD_prev, 0.30)

7.3 Color_Tendencia (percentiles)
Si INVALID o Nprev30 < 15 → Color = Indef
Si no:
- Verde si cRMSSD >= P30
- Ámbar si P15 <= cRMSSD < P30
- Rojo si cRMSSD < P15

Modulación mínima (anti "verde falso"):
- "Verde muy justo" si (cRMSSD - P30) < 0.10*(P30 - P15)
- Si Verde muy justo y HR_z14 >= +3 → degradar a Ámbar

============================================================
8) SEMÁFOROS P1/P2 (Z-SCORES) + VERSIONES CON lncRMSSD
============================================================

**Nota sobre nomenclatura:**
En este sistema se calculan dos políticas de umbral sobre z-scores:
- **P1 (Policy 1)**: estricta → `Color_P1` (solo evaluación técnica)
- **P2 (Policy 2)**: permisiva → `Color_Agudo_Diario` (decisión diaria)

P2 es el que aparece en el CSV maestro y se usa cada mañana.
P1 existe solo para comparación/evaluación técnica en datasets opcionales.

**Nota sobre almacenamiento:**
Los z-scores (z_HRV_28, HR_z14, z_HRVc_28) se calculan siempre, pero:
- En el **maestro operativo** (sección 10) solo se guardan los **colores resultantes**: Color_Agudo_Diario, Color_Tiebreak
- Los z-scores intermedios NO se guardan en el maestro operativo
- Opcionalmente, se puede generar un **dataset P1/P2** (archivo separado) que incluya todos los z-scores para evaluación técnica

Estos semáforos NO sustituyen al Color_Tendencia; se usan en Opción A (decisión final).

8.1 Z-score robusto HRV (lnRMSSD) — z_HRV_28
- Señal: lnRMSSD (del tramo estabilizado)
- Ventana: últimos 28 días previos válidos (shift-1), mínimo 10
- Mediana + MAD:
  z_HRV_28 = (lnRMSSD_hoy - med_prev) / (1.4826*MAD_prev)
- clamp a [-5,+5]

8.2 Z-score robusto HR (HR_stable) — HR_z14
- Señal: HR_stable
- Ventana: últimos 14 días previos válidos (shift-1), mínimo 7
- Mediana + MAD, clamp [-5,+5]

8.3 Z-score robusto HRV corregida (lncRMSSD) — z_HRVc_28
- Definir lncRMSSD = ln(cRMSSD)

**Nota:** lncRMSSD se calcula internamente pero NO se guarda en el maestro operativo. Solo se almacenan lnRMSSD y cRMSSD.

- Ventana y cálculo igual que 8.1, sustituyendo lnRMSSD por lncRMSSD
- clamp [-5,+5]

8.4 Colores P1 (más estricto)
Base por HRV:
- Verde si z_HRV_28 >= -0.8
- Ámbar si -1.6 <= z_HRV_28 < -0.8
- Rojo si z_HRV_28 < -1.6
Override por HR:
- Si HR_z14 >= +3.0 → Rojo
Indef si falta ventana o INVALID.

P1_lncRMSSD: igual, pero usando z_HRVc_28 en lugar de z_HRV_28.

8.5 Color_Agudo_Diario (P2, permisivo)
Base por HRV:
- Verde si z_HRV_28 >= -1.0
- Ámbar si -2.0 <= z_HRV_28 < -1.0
- Rojo si z_HRV_28 < -2.0
Override por HR (dos niveles):
- Si HR_z14 >= +3.8 → Rojo
- Si HR_z14 >= +3.0 y el color base era Verde → degradar a Ámbar
Indef si falta ventana o INVALID.

Color_Tiebreak: igual, pero usando z_HRVc_28.

============================================================
9) DECISIÓN DIARIA — OPCIÓN A (NO UN SOLO SEMÁFORO)
============================================================

La decisión usa 3 capas + desempate:
1) Gate técnico (Calidad/Stab/INVALID)
2) Estado agudo (Color_Agudo_Diario / P2)
3) Contexto/tendencia (Color_Tendencia por percentiles)
4) Desempate (Color_Tiebreak) solo si hay conflicto

9.1 Gate (obligatorio)
- Si Calidad=INVALID → día NO confiable:
  - No tomar decisiones de calidad basadas en HRV.
  - Recomendación: entrenamiento conservador (Z1/Z2 suave) guiado por sensaciones, sueño y carga previa.
- Si Calidad=FLAG_mecánico o HRV_Stability=Unstable → día "usable con pinzas":
  - Prohibido usarlo para justificar intensidad.
  - Puede usarse para confirmar prudencia.

9.2 Decisión base con dos señales (Color_Agudo_Diario + Color_Tendencia)
(Asumiendo que NO es INVALID; si es FLAG/Unstable, la recomendación ya se limita)

- Color_Agudo_Diario Verde + Color_Tendencia Verde:
  → plan normal (resistencia/base o calidad si estaba programada)
- Color_Agudo_Diario Verde + Color_Tendencia Ámbar/Rojo:
  → permisivo pero prudente: volumen Z1/Z2 OK; evitar calidad fuerte
- Color_Agudo_Diario Ámbar (cualquier Color_Tendencia):
  → base/recuperación; nada de calidad
- Color_Agudo_Diario Rojo + Color_Tendencia Verde:
  → perturbación aguda: 24 h conservador (Z1). Si se repite 2 días, descargar.
- Color_Agudo_Diario Rojo + Color_Tendencia Rojo:
  → señal fuerte: descanso o Z1 muy suave

9.3 Desempate (Color_Tiebreak) — se consulta solo cuando hay conflicto (se calcula y almacena siempre)
- Si Color_Agudo_Diario = Rojo pero Color_Tiebreak = Verde/Ámbar:
  → bajar alarma a Ámbar (probable efecto HR/RR arrastrando RMSSD)
- Si Color_Agudo_Diario = Verde pero Color_Tiebreak = Rojo:
  → bajar a Ámbar (posible "verde falso" por HR baja)

============================================================
10) QUÉ SE ALMACENA (MAESTRO OPERATIVO + β AUDIT)
============================================================

El maestro final (orden sugerido; columnas mínimas + β audit):

Fecha,
Calidad,
HRV_Stability,
Artifact_pct,
Tiempo_Estabilizacion,

HR_stable,
RRbar_s,
RMSSD_stable,
RMSSD_stable_last2,
lnRMSSD,
cRMSSD,

beta_est_90d,
beta_use_90d,
beta_mode,
RR_ref_90d,
N90_valid,
IQR_RRbar_90d,
R2_winsor_90d,
ln_corr,

Nprev30,
P15_cRMSSD_30d,
P30_cRMSSD_30d,
HR_z14,

Color_Tendencia,
Color_Agudo_Diario,
Color_Tiebreak

Notas:
- No almacenar pNN50 ni métricas no usadas.
- Internamente usar float64 sin redondeos intermedios; solo:
  - HR_z14 clamp ±5 y redondeo 2 decimales (si se desea)
  - El resto puede almacenarse con precisión razonable (p.ej., 6 decimales en betas).

- Los tres semáforos (`Color_Tendencia`, `Color_Agudo_Diario`, `Color_Tiebreak`) se calculan y **se almacenan siempre** en el maestro operativo.
  - `Color_Tiebreak` se **consulta** solo cuando hay conflicto entre agudo y tendencia; no se deja en blanco.
- Regla operativa: si `Calidad` = INVALID → el día se trata como **Indef** (no decidir por HRV). Si `Calidad` = FLAG_mecánico o `HRV_Stability` ≠ OK → prudencia; el Gate manda sobre los colores.

El dataset de evaluación P1/P2 (opcional) añade:
- z_HRV_28, HR_z14, z_HRVc_28
- Nprev28_lnRMSSD, Nprev14_HR, Nprev28_lncRMSSD
- Color_P1                      # (estricto, solo para evaluación técnica)
- Color_P1_lncRMSSD            # (estricto, versión corregida por HR)
- Color_Agudo_Diario           # (P2, usado en decisión diaria)
- Color_Tiebreak               # (P2 corregido, solo para desempate)
- Color_Tendencia              # (copiado del maestro)

============================================================
11) QA OBLIGATORIO (anti-bugs, anti-sobreingeniería)
============================================================

11.1 QA "canario" (unit test por archivo concreto)
Si el usuario aporta un RR específico "canario" (ej. 2025-07-13):
Reportar:
- N_total_raw, N_offline, N_out_of_range, N_delta, Artifact_pct
- total_dur_s, t_end_eff (tras tail-trim)
- Tiempo_Estabilizacion (primario o fallback; explicar por qué)
- HR_stable, RRbar_s
- RMSSD_stable, RMSSD_stable_last2
- HRV_Stability, Calidad, INVALID?
Además: tabla de ventanas de latencia (60s, step 30s):
  w, [t0,t1), n_RR, n_pairs, RMSSD_w, rel_change_prev
y candidatos k (primario/fallback).

11.2 Sanity checks globales (cada mes y acumulado)
- % días HR_stable fuera [35,100] (debería ser 0 excepto INVALID)
- Distribución Artifact_pct (outliers >50% rarísimos; listar top 20)
- % Tiempo_Estabilizacion=NaN (si sube >15–20% sostenido: revisar reglas/protocolo)
- Distribución de `dur_tramo = t_end_eff - t_start_eff` (P10/P50/P90) y % de días con `dur_tramo < 120 s` y `< 180 s`.
  - Si estos porcentajes suben de forma sostenida: revisar protocolo (duración total, movimiento) y reglas de latencia.
- % Calidad: OK / FLAG / INVALID
- Listar 20 días con Lat más alta y 20 con Artifact_pct más alto
- Verificación unidades:
  - RRbar_s típico 0.8–1.6
  - HR_stable ≈ 60/RRbar_s (error relativo <=0.1%)

Plantilla fija de salida — QA_global (MD)
- Nombre: `ENDURANCE_HRV_QA_global_ALL_STD.md` (o equivalente; el contenido debe seguir esta plantilla).
- Debe incluir SIEMPRE estas secciones (aunque estén vacías):
  0) Cobertura
     - Rango (min→max), n de días presentes y n esperado dentro del rango, días ausentes (si aplica).
  1) Calidad (tabla): OK / FLAG_mecánico / INVALID
  2) INVALID (tabla detalle o 'Sin días INVALID')
     - Columnas mínimas: Fecha, Artifact_pct, HRV_Stability, Tiempo_Estabilizacion, Flags, Notes
  3) FLAG_mecánico (tabla detalle o 'Sin días FLAG_mecánico')
     - Columnas mínimas: Fecha, Artifact_pct, HRV_Stability, Tiempo_Estabilizacion, Flags, Notes
  4) Sanity checks (bloque de métricas resumidas)
     - HR fuera de rango (excl. INVALID), Artifact_pct (mediana/P90/max), Latencia (NaN/mediana/P90/max), dur_tramo (P10/P50/P90 y %<120/%<180 si disponible), coherencia HR vs RR (P95/max).
  5) Flags de estabilidad (conteos): LAT_NAN, STAB_LAST2_MISMATCH, STAB_TAIL_SHORT
  6) Top outliers (tablas): Top 20 Artifact_pct y Top 20 Tiempo_Estabilizacion
  7) Resumen β/cRMSSD (operativo): tabla de conteos beta_mode + clip_rate + |ln_corr| (mediana/P90)

Nota:
- La plantilla fija es un contrato anti-deriva: no añadir ni quitar secciones; si se añade contenido nuevo, solo dentro de las secciones existentes.

11.3 QA específico de β (mensual y rolling 30d)
1) clip_rate = % días con beta_mode=clipped
   warning si >80% durante >=45 días rolling
2) Corrección aplicada:
   |ln_corr| = |ln(cRMSSD/RMSSD_stable)|
   warning si P90(|ln_corr|) > 0.25 o si >30% de días tienen |ln_corr| > 0.20
3) Dependencia residual con RR:
   corr = corr( ln(cRMSSD), ln(RRbar_s) ) en 60–90d
   objetivo ≈ 0; warning si |corr| > 0.15 (especialmente si corr < -0.15)
4) Top 10 días por |ln_corr| con:
   Fecha, RRbar_s, RMSSD_stable, cRMSSD, beta_use_90d, beta_mode, R2_winsor_90d

Plantilla fija de salida — QA_beta (MD)
- Nombre: `ENDURANCE_HRV_QA_beta_ALL_STD.md` (o equivalente; el contenido debe seguir esta plantilla).
- Debe incluir SIEMPRE estas secciones (aunque estén vacías):
  0) Cobertura (rango, n)
  1) Resumen beta_mode (tabla de conteos + clip_rate)
  2) Calidad del ajuste 90d (resumen de N90_valid, IQR_RRbar_90d, R2_winsor_90d: min/P10/P50/P90)
  3) Corrección aplicada (|ln_corr|: mediana/P90/max)
  4) Top 10 días por |ln_corr| (tabla)
     - Columnas mínimas: Fecha, RRbar_s, RMSSD_stable, cRMSSD, beta_use_90d, beta_mode, R2_winsor_90d, ln_corr
  5) Incidencias (tabla para beta_mode=none/frozen o 'Sin incidencias')
     - Columnas mínimas: Fecha, beta_mode, beta_est_90d, beta_use_90d, N90_valid, IQR_RRbar_90d, R2_winsor_90d, Flags, Notes

Nota:
- QA_beta se publica mensual y también en versión acumulada (ALL) para detectar deriva.
11.4 Regla de cambio de versión (única palanca; evitar iterar sin fin)
Mientras solo haya warnings → NO cambiar el modelo.
Solo si durante >=45 días rolling se cumplen simultáneamente:
- clip_rate > 80%  AND
- P90(|ln_corr|) > 0.25
Entonces activar v3.3f:
- beta_cap pasa de 3.0 → 2.5
- Recalcular histórico y re-evaluar QA 2 meses completos

============================================================
12) CONDICIÓN DE PARADA (diagnóstico antes de seguir)
============================================================

Si se detecta algo fisiológicamente imposible o típico de bug:
- HR supina >100 lpm o RRbar_s <0.5 s en "supino"
- Artifact_pct ~99% en un fichero aparentemente normal
- HR_stable no cuadra con RRbar_s (unidades mal)
Entonces:
- PARAR procesamiento masivo
- Reportar diagnóstico (archivo afectado, conteos, ejemplos de RR, unidades)
- No recalcular histórico hasta corregir

============================================================
INSTRUCCIONES PARA EL CHAT NUEVO (qué debe hacer el asistente)
============================================================

1) Leer ZIP(s) RR, parsear fecha/hora del nombre.
2) Procesar cada fichero según secciones 2–5 (incluye tail-trim 15s).
3) Resolver duplicados por fecha según sección 1.2 y registrar.
4) Construir maestro operativo + β audit según secciones 6–7.
5) (Opcional recomendado) Construir dataset P1/P2 según sección 8.
6) Ejecutar QA (canario si se aporta + global + β QA) según sección 11.
7) Reportar resultados: maestro, QA y duplicados.
8) Para uso diario: aplicar Opción A (sección 9) y devolver:
   Gate (Calidad/Stab), Color_Agudo_Diario, Color_Tendencia, desempate Color_Tiebreak si conflicto, y recomendación de acción.

FIN ESPECIFICACIÓN