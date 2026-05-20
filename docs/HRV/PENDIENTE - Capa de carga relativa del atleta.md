# Tarea: Capa de carga relativa del atleta

Estado: parcialmente implementado
Tipo de valor: valor explicativo, valor predictivo temprano y valor de personalizacion
Prioridad: alta

## Resumen
La capa de carga relativa ya existe en el repositorio y esta documentada en contratos. La base canonica relevante en `sessions_day` es:

- `acwr_simple_prev`
- `monotony_7d_prev`
- `strain_7d_prev`
- `load_ctx_ready`
- `intense_days_prev_3d`
- `intense_days_prev_5d`
- `intensity_clustering_flag`
- `intensity_clustering_level`

El problema abierto de PCV-03 ya no es "crear contexto de carga desde cero". Lo que queda es terminar de retirar o simplificar avisos residuales apoyados en umbrales absolutos dentro de `reason_text`, especialmente donde sigan apareciendo lecturas tipo `load_3d`, `work_7d_sum` y `z3_7d_sum` sin la lectura relativa correspondiente.

Hoy siguen existiendo mensajes del tipo:

- `Carga acumulada reciente alta (load_3d=...)`
- `VERDE con carga acumulada (load_3d=...): precaucion con la intensidad`

Eso limita la interpretacion porque el sistema mezcla senales ya personalizadas del atleta con reglas absolutas heredadas.

## Estado real del repositorio
Lo que ya existe y debe considerarse cubierto:

- `acute_chronic_ratio_7_28` ya esta cubierto de forma operativa por `acwr_simple_prev`.
- `monotony_7d` ya esta cubierto de forma operativa por `monotony_7d_prev`.
- el apilado reciente de dias duros ya esta cubierto en parte por `intense_days_prev_3d` y `intense_days_prev_5d`.
- `strain_7d_prev` ya aporta una lectura relativa adicional del contexto de carga.

Lo que sigue faltando o puede refinarsse:

- una limpieza final de los textos que todavia mencionan `load_3d` como si fuera la unica señal de carga;
- una forma mas clara de expresar si la carga reciente es alta para este atleta y este bloque, no solo alta en terminos brutos;
- una narrativa de `reason_text` que explique mejor verdes fragiles y rojos con contexto de carga realmente personalizado.

## Valores relativos y calculo
Los valores relativos que ya forman parte de la capa canonica de carga son:

- `acwr_simple_prev`
- `monotony_7d_prev`
- `strain_7d_prev`
- `intense_days_prev_3d`
- `intense_days_prev_5d`
- `intensity_clustering_flag`
- `intensity_clustering_level`

Las guardas de contexto son:

- `load_ctx_ready`
- `load_28d_nobs`

Definicion operativa de cada uno:

- `acwr_simple_prev = media de `load_7d` previa por dia / media de `load_28d` previa por dia`; en el pipeline actual se implementa como `load_7d / 7` dividido por `load_28d / 28`.
- `monotony_7d_prev = media de `load_day` de los 7 dias previos / desviacion estandar de esos 7 dias previos`.
- `strain_7d_prev = suma de `load_day` de los 7 dias previos * monotony_7d_prev`.
- `intense_days_prev_3d` y `intense_days_prev_5d` cuentan dias intensos previos en ventanas de 3 y 5 dias.
- `intensity_clustering_flag` y `intensity_clustering_level` se derivan de esos conteos.
- `load_ctx_ready = True` cuando `load_28d_nobs >= 14`.

La senal relativa que PCV-03 introdujo es:

- `acute_load_72h_rel = load_3d / (load_28d / 28)` cuando exista contexto suficiente.

Como se actualizan con el tiempo:

- `build_sessions.py` los recalcula en cada ejecucion de `--update`, `--daily` o `--backfill`;
- las ventanas son causales y moviles, asi que cada dia nuevo desplaza las ventanas un paso hacia delante;
- el pipeline usa `shift(1)` o equivalentes para excluir el dia actual del contexto que alimenta la lectura relativa;
- si no hay historial suficiente, los campos quedan en `NaN` hasta que `load_ctx_ready` pase a `True`.

## Que falta exactamente
- sustituir o complementar reglas absolutas por metricas relativas del atleta alli donde todavia domine `load_3d`;
- revisar si hace falta una segunda senal de "calidad/densidad" reciente, pero sin duplicar mecanicamente lo que ya cubren `z3_7d_sum`, `intensity_clustering_*` o `DO-02`;
- rehacer los avisos de `reason_text` para que expliquen mejor verdes fragiles y rojos sin causa aparente;
- decidir si `load_3d` debe quedarse como dato bruto de apoyo o reducirse aun mas en favor de la lectura relativa.

## Alcance recomendado
Alcance minimo util:

- depurar los textos restantes que aun describen `load_3d` como warning principal sin contexto relativo;
- ajustar el copy de `reason_text` para que exprese el exceso relativo frente al baseline cronico del propio atleta.

Alcance diferido o condicional:

- `quality_stress_72h`, solo si demuestra valor incremental claro frente a `z3_7d_sum`, clustering reciente y la capa de polarizacion semanal;
- nuevas senales adicionales de apilado de dias duros, solo si no solapan con `intense_days_prev_3d` y `intense_days_prev_5d`.

## Normalizacion de `acute_load_72h_rel`
La normalizacion debe ser consistente con la capa canonica existente de carga:

- si `load_ctx_ready` es `False`, emitir `NaN`;
- si `load_28d_nobs < 14`, emitir `NaN` de forma equivalente, porque la base cronica todavia no es interpretable;
- si `chronic_mean_28d <= 0`, emitir `NaN`;
- solo calcular el ratio cuando exista contexto suficiente y el denominador sea valido.

Esto evita alarmas espurias en bloques de descarga o historiales cortos sin introducir un cap artificial que deforme la senal.

La calibracion operativa de los umbrales no es causal: cuando hay suficiente historial listo, `acute_load_72h_rel` se interpreta con percentiles locales (`P75/P90`) calculados sobre todo el historico disponible del atleta en `base_df`, igual que la capa de `strain`. Si aun no hay suficiente soporte, el dashboard cae en umbrales bootstrap provisionales (`3.9/4.5`).

## Por que sigue teniendo valor
- mejora mucho la interpretacion de carga sin tocar el gate base;
- reduce avisos muertos o poco informativos apoyados en thresholds universales;
- mejora la explicabilidad de `reason_text` al decir si la carga es alta para este atleta, no solo si supera un numero fijo;
- permite personalizar mejor la lectura de verdes fragiles y rojos con contexto de carga reciente.

## Archivos candidatos
- `build_sessions.py`
- `build_hrv_final_dashboard.py`
- `docs/contracts/ENDURANCE_HRV_Sessions_Schema.md`
- `docs/contracts/ENDURANCE_HRV_Spec_Tecnica.md`
- `tests/test_build_sessions_contract.py`
- `tests/test_cli_reporting_contract.py`

## Criterio de cierre
La capa relativa de carga reciente queda documentada en contratos y guias, y los textos de uso dejan de presentar `load_3d` como unica lectura de carga.

Condiciones concretas:

- `sessions_day` expone al menos una senal relativa nueva para carga aguda reciente;
- `reason_text` usa esa senal con mensajes mas especificos que los umbrales absolutos actuales;
- los umbrales operativos de `acute_load_72h_rel` se leen preferentemente de `P75/P90` locales sobre el historico listo del atleta, con fallback bootstrap mientras falta soporte;
- los contratos reflejan el nuevo campo y su semantica;
- los tests cubren el comportamiento minimo esperado.
