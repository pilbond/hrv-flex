
## Objetivo
Incorporar `ACWR`, `monotony` y `strain` como capa canonica de contexto de carga para que el sistema pueda interpretar el estado HRV dentro del patron agudo-cronico y de la uniformidad de carga, sin convertir estas metricas en parte del gate.

### 1. ACWR (Acute:Chronic Workload Ratio) — Confianza: 92%

**Qué es:** Ratio ATL/CTL (carga aguda 7d / carga crónica 42d). Zona productiva 0.8–1.3, riesgo lesión >1.5.

**Por qué importa:** Tu sistema actual tiene `load_3d`, `load_7d`, `load_14d`, `load_28d` en sessions_day pero **NO calcula ACWR explícitamente**. El reason_text usa umbrales absolutos ("carga acumulada alta" si load_3d >250), pero estos umbrales fijos no se adaptan al nivel de fitness del atleta. Un CTL de 120 tolera load_3d de 300; un CTL de 50, no.

**Mejora concreta:** ACWR contextualiza la carga relativa al fitness actual. Permitiría que el reason_text diga "ACWR 1.4 — estás cargando más de lo que tu fitness crónico soporta" en vez de un umbral fijo que no distingue periodos de base vs. build.

### 2. Monotonía y Strain de Foster — Confianza: 88%

**Qué es:**

- Monotonía = Media(carga diaria 7d) / SD(carga diaria 7d). >2.0 = estrés repetitivo
- Strain = Σ(carga 7d) × Monotonía. >2200 = riesgo de sobreentrenamiento

**Por qué importa:** Tu sistema detecta _cuánta_ carga hay, pero no detecta la **variabilidad de esa carga**. Entrenar 5 días con la misma carga moderada es más peligroso inmunológicamente que 2 días duros + 3 suaves con la misma carga total. Foster demostró que monotonía alta + strain alto predice infección respiratoria y lesión en resistencia.

**Mejora concreta:** Añadir monotonía al reason_text detectaría semanas "peligrosamente iguales" que pasan desapercibidas con los rolling actuales. Un ÁMBAR con monotonía >1.8 debería sugerir variar estructura, no solo reducir volumen.

## Estado actual
El proyecto ya dispone de la materia prima necesaria:

- `build_sessions.py` genera `load_day`, `load_3d`, `load_7d`, `load_14d` y `load_28d` en `ENDURANCE_HRV_sessions_day.csv`.
- `build_hrv_final_dashboard.py` consume `sessions_day.csv` solo para avisos heuristicos en `reason_text`.
- La carga hoy no esta canonizada como una capa derivada estable, sino como checks sueltos:
  - `load_3d > 250`
  - `work_7d_sum > 200`
  - `z3_7d_sum > 60`
- El gate sigue dependiendo exclusivamente de HRV + pulso.

## Brecha detectada
Falta una capa de carga derivada y consistente que:

- tenga formula explicita,
- tenga semantica estable,
- se pueda documentar y auditar,
- y permita contextualizar mejor un `VERDE`, `AMBAR` o `ROJO`.

El proyecto de referencia `intervalsicugptcoach-public` si trata `ACWR`, `monotony` y `strain` como metricas derivadas explicitas, pero este repo todavia no.

## Que aporta cada metrica

### ACWR
`ACWR` (`Acute:Chronic Workload Ratio`) compara la carga reciente con la carga base reciente.

Aporta:

- deteccion de saltos agudos de carga,
- lectura de si la semana actual esta alineada con la tolerancia reciente,
- contexto para distinguir entre mantenimiento, progresion y descarga.

Uso interpretativo:

- `ACWR ~ 1.0` sugiere alineacion con la base,
- `ACWR alto` sugiere subida aguda,
- `ACWR bajo` sugiere descarga o infraexposicion.

### Monotony
`Monotony` mide cuan uniforme ha sido la carga diaria reciente.

Aporta:

- deteccion de semanas demasiado planas,
- contexto sobre falta de alternancia carga-descarga,
- explicacion de fatiga acumulada incluso cuando la carga total no es extrema.

Uso interpretativo:

- `monotony` baja o moderada sugiere variacion saludable,
- `monotony` alta sugiere patron repetitivo y mas costoso de sostener.

### Strain
`Strain` combina la cantidad semanal y la uniformidad.

Aporta:

- una lectura agregada del peso global de la semana,
- priorizacion de semanas realmente comprometidas,
- distincion entre "semana dura" y "semana dura y ademas mal distribuida".

Uso interpretativo:

- sube si aumenta la carga semanal,
- sube aun mas si esa carga esta muy repartida en patron uniforme.

## Base cientifica util
La base cientifica es suficiente para tratarlas como contexto de carga, pero no como regla fisiologica dura.

- `Monotony` y `strain` tienen una base clasica aplicada en monitorizacion de carga tipo Foster.
- `ACWR` tiene mucha literatura y utilidad descriptiva, pero mas controversia metodologica si se pretende usar como predictor causal de lesion.

Conclusion operativa:

- son validas como contexto interpretativo,
- no conviene convertirlas en semaforo automatico,
- encajan bien con la filosofia actual del repo: contexto sin tocar el gate HRV.

## Mejora medible esperada
Sobre los datos actuales del repo:

- cobertura contextual actual por coincidencia exacta de fecha HRV-sesion: `84.0%`,
- cobertura potencial si se reconstruye calendario derivado desde `sessions_day`: `98.7%`,
- mejora directa de cobertura contextual: `+14.7 puntos`.

Esto no demuestra por si solo una mejora clinica o decisional, pero si una mejora clara de trazabilidad y continuidad interpretativa.

## Riesgos y limites

- no confundir contexto de carga con causa del estado HRV,
- no usar `ACWR` como predictor fuerte de lesion,
- no heredar umbrales del proyecto base sin revisar escala local,
- no meter estas metricas dentro del gate salvo cambio de alcance explicito.

## Desarrollo propuesto

### 1. Canonizar formula
Definir explicitamente las tres metricas a partir de `load_day` y dias previos, pero manteniendo consistencia con la logica rolling simple que ya usa el repo.

Decision cerrada para v1:

- no usar EWMA en la primera implementacion;
- usar rolling simple, porque es mas transparente, mas auditable y coherente con `load_3d`, `load_7d`, `load_14d` y `load_28d`.

Propuesta v1:

- `acwr_simple_prev = (sum_7d_prev / 7) / (sum_28d_prev / 28)`
- `monotony_7d_prev = mean(load_day_prev_7d) / std(load_day_prev_7d)`
- `strain_7d_prev = sum_7d_prev * monotony_7d_prev`

Reglas:

- usar siempre `shift(1)`;
- no incluir la carga del mismo dia de la medicion HRV;
- calcular `monotony` y `strain` sobre calendario continuo;
- dias sin sesion cuentan como `0` de carga para estas dos metricas.

Guardas recomendadas:

- si `std == 0`, devolver `NaN` en `monotony`;
- si `nobs_7d < 3`, considerar `monotony` y `strain` no disponibles.

### 2. Persistir en sessions_day.csv
Extender `build_sessions.py` para anadir columnas canonicas a `ENDURANCE_HRV_sessions_day.csv`.

Propuesta minima:

- `acwr_simple_prev`
- `monotony_7d_prev`
- `strain_7d_prev`
- `load_ctx_ready`

Opcional:

- columnas de cobertura o `nobs` especificos para auditoria.

Definicion recomendada de disponibilidad:

- `load_ctx_ready = True` cuando `load_28d_nobs >= 14`

Esto evita vender contexto de carga como estable cuando el denominador cronico aun es demasiado corto.

### 3. Consumir en FINAL solo como contexto
Actualizar `build_hrv_final_dashboard.py` para:

- reconstruir un calendario diario a partir de `sessions_day.csv`,
- hacer `reindex` al rango continuo de fechas y `ffill(limit=7)` de `acwr_simple_prev`, `monotony_7d_prev`, `strain_7d_prev` y `load_ctx_ready`,
- alinear contexto de carga con cualquier fecha de HRV aunque no haya sesion ese dia,
- generar mensajes de `reason_text` mas semanticos.

Ejemplos:

- `ACWR alto: carga aguda por encima de la base cronica`
- `Monotony alta: patron de carga poco variable`
- `Strain alto: semana exigente y poco descargada`

Regla:

- no cambiar `gate_final`,
- no recolorear `Action`,
- solo enriquecer interpretacion.

Decision de implementacion:

- mantener `sessions_day.csv` como tabla de dias con sesion;
- resolver la propagacion del contexto en el consumidor, no en el productor.
- limitar la propagacion a un maximo de 7 dias sin nueva sesion; pasado ese limite, el contexto de carga debe aparecer como no disponible.

### 4. Calibrar umbrales localmente
No asumir que los umbrales del repo base valen tal cual.

Observacion del historico local:

- `ACWR` simple normalizado y `monotony` parecen compatibles con bandas heredadas como punto de partida,
- `strain` queda en escala mas baja, por lo que conviene calibracion local.

Estrategia sugerida:

- arrancar con umbrales heredados para `ACWR` simple normalizado,
- arrancar con umbrales heredados o cercanos para `monotony`,
- calibrar `strain` por percentiles del historico local.

Regla provisional para `strain`:

- `strain_high` si supera `P75` del historico local;
- `strain_extreme` si supera `P90`;
- si no hay al menos 8 semanas equivalentes de historico, tratar `strain` como contextual pero no umbralizar fuerte.

Limitacion conocida de `monotony`:

- al calcularse sobre calendario continuo con dias sin sesion = `0`, una semana con pocos entrenamientos puede producir `monotony` baja por alta variacion entre dias de carga y dias a cero;
- esto es coherente con la implementacion elegida, pero hace que la comparacion directa con referencias clasicas de Foster sea menos limpia en semanas de baja densidad de entrenamiento.

### 5. Documentar contrato
Actualizar:

- `docs/contracts/ENDURANCE_HRV_Sessions_Schema.md`
- `docs/contracts/ENDURANCE_HRV_Spec_Tecnica.md`

Debe quedar claro que:

- son metricas canonicas de contexto de carga,
- viven en `sessions_day.csv`,
- y no gobiernan el gate HRV.

## Orden de implementacion recomendado
1. Definir formulas y nombres canonicos de v1.
2. Implementar `acwr_simple_prev` en `build_sessions.py`.
3. Implementar `monotony_7d_prev` con guardas de `std` y `nobs`.
4. Integrar `ACWR` y `monotony` en `build_hrv_final_dashboard.py` con `reindex + ffill`.
5. Anadir `strain_7d_prev` como metrica secundaria.
6. Validar historico y rango de valores.
7. Actualizar contratos y QA.

## Criterios de aceptacion propuestos

- `sessions_day.csv` expone `ACWR`, `monotony` y `strain` con formula documentada.
- `ACWR` usa la version simple normalizada por ventana, no `load_7d / load_28d` a secas.
- `monotony` y `strain` se calculan sobre calendario continuo con dias sin sesion = `0`.
- `load_ctx_ready` queda definido explicitamente.
- Las metricas se pueden consumir tambien en dias HRV sin sesion ese mismo dia mediante propagacion limitada en `FINAL`.
- La propagacion del contexto en `FINAL` usa `ffill(limit=7)`; superado ese limite, el contexto aparece como no disponible.
- `FINAL` o `reason_text` puede mostrar el contexto de carga sin tocar `gate_final`.
- La documentacion contractual refleja nombres, formula y limites de uso.
- La implementacion mantiene la regla actual: contexto si, gate no.

## Decision recomendada
Implementar `CDC-01`, pero como canonizacion de contexto de carga y no como cambio del decisor HRV.

La mejor lectura de esta tarea es:

- formalizar,
- alinear,
- documentar,
- y hacer auditable la capa de carga.

No reescribir el gate.
