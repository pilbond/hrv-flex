
## Objetivo

Canonizar una senal proactiva de clustering reciente de intensidad para complementar el sistema actual, que hoy es principalmente reactivo al gate HRV diario.

La idea funcional de la tarea es buena: detectar acumulacion de sesiones intensas antes de que el ANS exprese fatiga clara en el HRV matinal. La formulacion literal de la tarjeta, sin embargo, no encaja con el historico actual y necesita recalibracion.

## Situacion actual en el repo

- `build_sessions.py` ya genera `intensity_category` por sesion con categorias como `work_intense`, `work_steady`, `work_moderate`, `finish_strong` y `easy`.
- `build_sessions.py` ya genera `ENDURANCE_HRV_sessions_day.csv`, que es el sitio natural para persistir una senal rolling diaria de clustering.
- `build_hrv_final_dashboard.py` ya consume `sessions_day.csv` para enriquecer `reason_text`, pero solo con checks reactivos de `load_3d`, `work_7d` y `z3_7d`.
- El sistema actual ya tiene `bad_streak`, pero esa senal es reactiva: describe dano expresado en el gate, no patron previo de apilamiento de intensidad.

## Que aporta el proyecto original

El proyecto base no trata NDLI como un simple conteo de sesiones duras. Lo integra en `performance_intelligence` y lo calcula con:

- `rolling_joules_above_ftp_7d`
- `high_intensity_days_7d`
- `mean_if_7d`
- mas senales auxiliares como eficiencia y variabilidad

Por tanto:

- la idea fisiologica si es trasladable;
- la formula original no se puede portar fielmente hoy porque este repo no tiene como capa canonica `FTP`, `IF` ni trabajo sobre umbral en potencia.

## Conclusiones del analisis

### 1. La tarea merece implementarse

Hay un hueco real entre:

- senales reactivas (`bad_streak`, `load_3d`, `z3_7d`)
- y una senal de patron corto de intensidad mal espaciada

Ese hueco es exactamente el que pretende cubrir `AP-01`.

### 2. La tarjeta, tal como esta escrita, no funciona sobre el historico actual

La regla propuesta en la tarjeta:

- `3` dias intensos en `3d`
- o `4` en `5d`

no genera ninguna alerta sobre el historico actual.

Resultado medido:

- `348` sesiones totales
- `29` sesiones `work_intense`
- `271` dias con sesiones
- `309` fechas de `FINAL` dentro del calendario util de sesiones
- flags con la regla literal de la tarjeta: `0`

Eso significa que implementarla literal aportaria mejora medible `0`.

### 3. Si se recalibra, si aparece valor real

La version minima con mejor encaje en el historico actual es:

```text
intense_day = 1 si existe alguna sesion con intensity_category == work_intense
intense_days_prev_5d = suma de intense_day en los 5 dias previos
ndli_proxy_flag = intense_days_prev_5d >= 2
```

Con ese umbral:

- `30` dias quedan marcados en `FINAL`
- `17` de ellos estan aun en `VERDE`
- `9` de esos `17` pasan a no-verde en las siguientes `48h`
- `15` de esos `17` no tenian ya un aviso equivalente de carga en `reason_text`

La mejora medible defendible es, por tanto:

- pasar de `0` avisos proactivos a `17` avisos utiles en dias todavia verdes
- con `9` de ellos anticipando deterioro del gate a corto plazo
- y `15` anadiendo informacion que hoy no aporta el texto actual

Contexto importante: tasa base de deterioro en 48h

- en dias `VERDE` con flag, la tasa de paso a no-verde en `48h` es `52.9%`
- en dias `VERDE` sin flag, la tasa base es `31.9%`
- el lift observado es de `+21.1` puntos

Esto no convierte la senal en predictor fuerte, pero si demuestra que aporta informacion anticipatoria por encima del baseline.

Lectura interpretativa:

- una tasa base de `31.9%` ya indica que casi `1` de cada `3` dias `VERDE` pasa a no-verde en `48h` por la variabilidad natural del sistema;
- con flag, esa probabilidad sube a `52.9%`, aproximadamente `1.66x` el baseline;
- por tanto, la senal no debe leerse como `si hay flag, caerás`, sino como `si hay flag, la probabilidad de deterioro cercano aumenta de forma apreciable`.

### 4. No conviene llamarlo NDLI canonico sin matiz

Lo correcto en este repo es documentarlo como:

- `intensity_clustering_flag`
- `intensity_clustering_level`
- o equivalente

porque no es el mismo NDLI del proyecto base, que depende de potencia y trabajo sobre FTP.
Sobre esto discutir si la tarea de añadir potencia y gap en las sesiones de run modifica en parte esta apreciacion

Decision de nomenclatura:

- evitar `ndli_proxy` como nombre principal de campo, porque comunica poco y sigue siendo abstracto;
- dejar `NDLI` solo como referencia conceptual en la documentacion.

## Que aporta esta senal frente a lo que ya existe

- `load_3d` dice: has cargado bastante.
- `z3_7d` dice: has acumulado intensidad.
- `ndli_proxy` diria: la intensidad reciente esta mal espaciada.

Ese matiz es importante, porque dos semanas con la misma carga total pueden tener perfiles de recuperacion muy distintos si una de ellas apila demasiada intensidad en pocos dias.

## Esquema de implementacion recomendado

### Fase 1. Canonizar la senal diaria

Ampliar `build_sessions.py` para que `ENDURANCE_HRV_sessions_day.csv` incluya:

- `intense_day`
- `intense_days_prev_3d`
- `intense_days_prev_5d`
- `intensity_clustering_flag`
- `intensity_clustering_level`

Siempre con ventanas de dias previos, excluyendo el propio dia.

Definicion operativa de v1:

```text
intense_day = 1 si existe alguna sesion con intensity_category == work_intense
intense_days_prev_3d = suma de intense_day en los 3 dias previos
intense_days_prev_5d = suma de intense_day en los 5 dias previos
intensity_clustering_flag = intense_days_prev_5d >= 2
```

Limitacion conocida de v1:

- `intense_day` es binario y no distingue grado de dureza dentro de `work_intense`;
- esta simplificacion es aceptable en v1, pero debe documentarse como aproximacion pragmatica.

### Fase 2. Integrarla en FINAL como contexto

En `build_hrv_final_dashboard.py`, al leer `sessions_day.csv`, anadir mensajes tipo:

- `VERDE pero clustering reciente de intensidad: considera Z1 manana`
- `Clustering alto de intensidad reciente: vigilar recuperacion`

No tocar el gate en v1. Debe ser contexto, no decisor.

Propagacion recomendada en `FINAL`:

- hacer `reindex` al calendario continuo;
- aplicar `ffill(limit=2)` a `intensity_clustering_flag` y `intensity_clustering_level`;
- pasado ese limite, la senal debe aparecer como no disponible.

Esto mantiene coherencia con el caracter de ventana corta de la metrica y evita arrastrar un clustering viejo demasiados dias.

### Fase 3. Anadir severidad

Propuesta:

- `low`: `>=2` dias `work_intense` en `5d`
- `high`: `>=2` dias `work_intense` en `3d` o `>=3` en `5d`

Esto separa bien la alerta suave de la alerta de apilamiento claro.

Precedencia explicita:

```text
if intense_days_prev_3d >= 2 or intense_days_prev_5d >= 3:
    intensity_clustering_level = "high"
elif intense_days_prev_5d >= 2:
    intensity_clustering_level = "low"
else:
    intensity_clustering_level = None
```

### Fase 4. Documentar contrato

Actualizar `docs/contracts/` para dejar claro:

- que es una senal contextual
- que inputs usa
- que ventana usa
- y que no equivale al NDLI power-based del proyecto base

## Extension futura razonable

Si se decide enriquecer la metrica por deporte:

- `road_run`: combinar `intensity_category` con running power del reloj
- `trail_run`: combinar `intensity_category`, running power y/o GAP
- `bike`: seguir con proxy estructural salvo que exista potenciómetro externo

Eso permitiria una v2 mejor que el simple conteo binario de `work_intense`.

Nota importante:

- en deportes tipo `run` existe la oportunidad de enriquecer la senal con running power del Polar Vantage M3;
- antes de cerrar la implementacion definitiva, conviene verificar si Intervals expone ese dato con cobertura y estabilidad suficientes en el historico;
- si existe y es usable, la mejor decision puede ser preparar una v1 simple y dejar abierta una v2 `run-aware`, evitando rehacer la tarea a ciegas.

## Recomendacion final

Implementar `AP-01`, pero no como copia del NDLI original ni con el umbral literal de la tarjeta.

La version correcta para el estado actual del repo es:

- proxy local
- calibrado con el historico real
- persistido en `sessions_day.csv`
- consumido por `FINAL` solo como aviso contextual
- y documentado explicitamente como senal de clustering de intensidad

Nombre recomendado de la capa:

- `intensity_clustering_flag`
- `intensity_clustering_level`

`NDLI` debe quedar solo como referencia conceptual, no como nombre principal de columna.
