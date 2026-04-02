Genera el informe semanal de entrenamiento del atleta en formato Markdown y guárdalo en disco.

{{WEEK_START}} = 2026-03-23
{{WEEK_END}} = 2026-03-29
{{PHASE}} = sin plan formal
{{BLOCK_CONTEXT}} = bloque de base aerobica
{{EVENTS}} = nada relevante

## 1. Periodo
Analiza la semana completa de `{{WEEK_START}}` a `{{WEEK_END}}` inclusive (`lunes a domingo`).

## 2. Contexto declarado
- Fase: {{PHASE}}
- Lectura actual: {{BLOCK_CONTEXT}}
- Eventos relevantes: {{EVENTS}}
- Restriccion: no asumir intencion de periodizacion que no este explicitamente declarada

## 3. Contratos que debes cargar y respetar
Carga y aplica, por este orden:

1. `\AGENTS.md`
2. `\analysis\AGENTS.md`
3. `\analysis\ENDURANCE_AGENT_DOMAIN.md`
4. `\analysis\WEEKLY_ANALYSIS_METHOD.md`
5. Usa `\analysis\SESSION_ANALYSIS_METHOD.md` solo como referencia de definiciones operativas ya canonicas que el metodo semanal reutiliza.

## 4. Fuentes primarias obligatorias
Usa como base primaria de evidencia:

- `\data\ENDURANCE_HRV_sessions_day.csv`
- `\data\ENDURANCE_HRV_sessions.csv`
- `\data\ENDURANCE_HRV_master_FINAL.csv`
- `\data\ENDURANCE_HRV_master_DASHBOARD.csv`
- `\data\ENDURANCE_HRV_master_CORE.csv`
- `\data\ENDURANCE_HRV_sleep.csv`

## 5. Fuentes secundarias
- Puedes usar informes de sesion de esa misma semana solo si sirven como ejemplo concreto de un patron semanal.
- No uses informes previos como fuente primaria de evidencia.
- Si citas una sesion concreta, que sea para ilustrar un patron semanal, no para recapitular la semana.

## 6. Reglas operativas de construccion
- Construye un calendario explicito de 7 dias con join por fecha entre las fuentes.
- Los dias sin sesion deben aparecer igualmente en la tabla semanal.
- Para `monotony` y `strain`, usa los 7 dias del calendario; los dias sin sesion computan como `load_day = 0`.
- Si un dia tiene solo fuerza o movilidad con `load < 10`, usa el valor real, no cero.
- Para lecturas finas de HRV, prioriza dias con `Calidad = OK`.
- Si la cobertura es pobre, irregular o degradada, declaralo y rebaja la confianza.
- No leas `gate_badge` aislado de `Action` y `reason_text`.
- No inventes causalidad si los datos no la sostienen.
- Separa siempre dato observado, inferencia y conclusion practica.

## 7. Preguntas que el informe debe responder
1. Que estructura tuvo realmente la semana.
2. Que carga util genero.
3. Que carga mecanica acumulada dejo, especialmente si hubo trail o desnivel relevante.
4. Si esa carga parece absorbida o no.
5. Si la semana funciono como mantenimiento, pico relativo, descarga o progresion moderada respecto al patron reciente.
6. Que divergencias relevantes hubo entre lo hecho y lo recomendado por el sistema.
7. Que condiciona el arranque de la semana siguiente.

## 8. Reglas analiticas especificas
- En `Carga y estructura`, interpreta la comparacion con las 3 semanas previas:
  - `>130%` de la media previa = pico relativo de carga
  - `70-130%` = mantenimiento o progresion moderada
  - `<70%` = descarga, semana incompleta o reduccion material
- Estos umbrales son orientativos; interpreta con contexto.
- Si `load` no captura bien la huella real de la semana, cruza la lectura con `work_total_min`, `z3_min`, `D+` y `D-`.
- Si hubo volumen material en trail o desnivel relevante, incluye `D+` y `D-` semanales como indicadores de carga mecanica acumulada.
- Trata `D-` semanal como señal especialmente relevante de estres excentrico cuando el contexto lo soporte.
- Si aparece peor absorcion o HRV deprimida sin carga cardio proporcional, considera la huella mecanica como hipotesis explicativa y declarala como inferencia, no como hecho.

## 9. Reglas para la distribucion de intensidad
- Presenta la distribucion observada por deporte.
- Si hay multimodalidad material, usa esta tabla:

| Deporte | Tiempo aerobico total | Z1 % | Z2 % | Z3 % | work_total_min | work_n_blocks |
|---|---:|---:|---:|---:|---:|---:|

- Debajo de la tabla, añade 2-4 lineas interpretativas.
- Si un solo deporte domina claramente `>80%` del volumen aerobico semanal, puedes comprimir esta parte a una linea cuantificada sin tabla.
- Si `work_longest_min` cambia materialmente la lectura estructural, incluyelo en la interpretacion o como columna extra.
- Si la tabla mezcla `trail/run`, `bike` y `swim`, añade una nota breve indicando que los porcentajes de zonas describen la distribucion observada dentro de cada deporte, pero no son directamente comparables con la misma finura fisiologica entre deportes salvo que existan umbrales especificos y fiables.
- Si el patron observado se parece mas a `polarizado`, `piramidal`, `threshold` o `mixto`, puedes decirlo con lenguaje neutro y descriptivo.
- No impongas una sola etiqueta global si la semana es multimodal o la señal es ambigua.

## 10. Reglas para recuperacion y absorcion
- Presenta tendencia HRV en tabla si la ventana cubre `4+` semanas:

| Semana | RMSSD media (OK) | n dias OK | HR reposo media |
|---|---:|---:|---:|

- Interpreta despues la direccion: progresa, oscila, regresa o estancada.
- Si `n dias OK` es bajo o irregular, rebaja la confianza.
- Para sueño, compara el agregado semanal con `2-3` semanas anteriores e incluye:
  - media de duracion y rango
  - `%` de noches `< 7h`
  - media de sueño profundo cuando la cobertura lo permita
- Si la cobertura de sueño profundo es baja, dilo y no lo trates como señal fuerte.
- Distingue `recuperacion intra-semana` de `tendencia inter-semana`.
- Si el pico principal cae al final de la semana y no hay tiempo suficiente para observar recuperacion, declaralo como limitacion.
- Si el inicio de la semana ya llega degradado por carga previa, reduce la fuerza de la comparacion intra-semana.

## 11. Reglas para divergencias con el sistema
- Incluye esta seccion solo si hubo divergencias materiales.
- Compara decision real vs `Action` y `reason_text`, no solo contra `gate_badge`.
- Para cada divergencia material, evalua si los `2-3` dias siguientes confirmaron o desmintieron la recomendacion del sistema.
- Prioriza como evidencia posterior:
  - evolucion de HRV
  - `Action` y `reason_text` de los dias siguientes
  - sueño y recuperacion
  - la siguiente sesion solo si aporta una señal clara y trazable
- Si la evidencia posterior no es interpretable, dilo explicitamente.
- No moralices; esto es calibracion del sistema, no juicio.

## 12. Regla especial para semanas de descarga
Si la semana muestra un patron claro de descarga (`load` semanal `<60%` de la media de las 3 semanas previas) y no hay causa externa dominante:
- no la trates como “semana simple”
- prioriza evidencia de recuperacion y supercompensacion por encima del analisis de carga bruta
- evalua especialmente:
  - tendencia HRV intra-semana
  - tendencia HRV inter-semana cuando aporte contexto
  - calidad y consistencia del sueño
  - señales de mejor absorcion o persistencia de fatiga

## 13. Regla de compresion
Aplica la compresion de `§9` de `WEEKLY_ANALYSIS_METHOD.md` solo si realmente se cumple el criterio de materialidad.

## 14. Estructura obligatoria del informe
0. Veredicto semanal
1. Perfil del microciclo
2. Carga y estructura
3. Distribucion observada por deporte
4. Recuperacion y absorcion
5. Monotony y strain
6. Divergencias relevantes con el sistema
7. Orientacion para la siguiente semana
8. Confianza y limitaciones

## 15. Reglas de redaccion
- El veredicto va primero.
- El detalle va despues.
- No recapitules las sesiones una por una.
- Se didactico, pero manteniendo tono tecnico, neutral y trazable al dato.
- Separa claramente lo observado de lo inferido.
- Si una conclusion es tentativa, dilo.
- Si algo no puede sostenerse con los datos, no lo fuerces.

## 16. Regla de salida

Guarda ahi el informe final en:

`\analysis\reports\weekly\{{WEEK_START}}_{{WEEK_END}}_report.md`

Entrega como resultado final el contenido del informe y confirma la ruta de guardado.
