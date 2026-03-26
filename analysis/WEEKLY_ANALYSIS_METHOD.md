<!-- contract_version: 0.1-draft -->
# WEEKLY_ANALYSIS_METHOD.md - Weekly analysis method

## 1. Alcance
Este documento define el metodo operativo reproducible para el
informe semanal del atleta del proyecto.

Aplica a:

- analisis agregado de una semana de lunes a domingo,
- integracion de estructura, carga, recuperacion y tendencia HRV,
- orientacion operativa para la semana siguiente.

No aplica a:

- analisis de sesion individual, que vive en
  `SESSION_ANALYSIS_METHOD.md`,
- periodizacion formal de macrociclo o fase,
- modificacion de outputs canonicos del pipeline.

## 2. Precedencia
Manda:

- `../AGENTS.md` en infraestructura, runtime y reglas globales,
- `AGENTS.md` local en alcance del modulo y outputs reproducibles,
- `ENDURANCE_AGENT_DOMAIN.md` en tono, baseline y semantica de
  confianza,
- `SESSION_ANALYSIS_METHOD.md` en definiciones operativas ya
  existentes que este documento reutiliza,
- este documento en estructura, agregacion y reglas especificas del
  nivel semanal.

Regla:

- este documento extiende el metodo al nivel semanal,
- MUST NOT redefinir metricas canonicas ya existentes en
  `sessions.csv`, `sessions_day.csv`, `CORE`, `DASHBOARD` o `sleep`.

## 3. Principio central
El informe semanal responde preguntas que no deben resolverse en el
informe de sesion:

- que estructura tuvo realmente la semana,
- que carga util genero,
- si esa carga parece absorbida o no,
- que condiciona la decision de la semana siguiente.

MUST NOT:

- recapitular todas las sesiones una a una,
- actuar como revision de macrociclo,
- convertir una metrica auxiliar en la conclusion central.

Si menciona una sesion concreta, es como ejemplo de un patron
semanal, no como resumen secuencial.

## 4. Periodo y activacion
### Periodo
- semana calendario de lunes a domingo.

### Activacion
- el informe semanal se genera bajo demanda, cuando el usuario lanza
  el prompt.

### Contexto opcional del prompt
El usuario MAY anadir:

- eventos relevantes de la semana,
- molestias, enfermedad o viaje,
- observacion subjetiva no visible en los CSV.

## 5. Fuentes
### Primarias
- `data/ENDURANCE_HRV_sessions_day.csv`
- `data/ENDURANCE_HRV_sessions.csv`
- `data/ENDURANCE_HRV_master_FINAL.csv`
- `data/ENDURANCE_HRV_master_DASHBOARD.csv`
- `data/ENDURANCE_HRV_master_CORE.csv`
- `data/ENDURANCE_HRV_sleep.csv`

### Rol recomendado por fuente primaria
- `sessions_day.csv`: agregados diarios, rolling y estructura resumida
  de carga,
- `sessions.csv`: detalle por sesion, deporte y distribucion por zonas,
- `ENDURANCE_HRV_master_FINAL.csv`: auditoria fina del gate,
  residuales, warning y contexto avanzado cuando haga falta,
- `ENDURANCE_HRV_master_DASHBOARD.csv`: capa operativa resumida para
  `gate_badge`, `Action` y `reason_text`,
- `ENDURANCE_HRV_master_CORE.csv`: capa HRV matinal cruda y calidad de
  medicion,
- `ENDURANCE_HRV_sleep.csv`: sueno nocturno y recuperacion de Polar.

### Secundarias
- informes de sesion del periodo si existen y aportan un ejemplo
  concreto,
- contexto verbal del usuario.

### Regla de jerarquia
- las fuentes canonicas del pipeline mandan sobre los informes de
  sesion previos,
- un informe semanal MUST NOT depender de textos previos del analista
  como base primaria de evidencia.

## 6. Ventanas y cobertura
### Ventanas por defecto
- semana actual: lunes a domingo,
- comparacion corta de carga: 3 semanas previas,
- tendencia de recuperacion: 6-8 semanas si existen datos.

### Reglas de cobertura
- para lectura fina de HRV, usar preferentemente dias con
  `Calidad = OK`,
- si un rolling o una media tiene cobertura pobre, declararlo y
  rebajar confianza,
- `sessions_day.csv` no incluye dias sin entrenamiento; por tanto, la
  tabla semanal MUST construirse con un calendario de 7 dias y join
  de fuentes, no solo con `sessions_day`.

## 7. Flujo obligatorio
1. construir el calendario semanal de 7 dias,
2. integrar sesiones, dashboard, core y sleep por fecha,
3. describir el perfil del microciclo sin interpretacion,
4. evaluar carga y estructura semanal,
5. evaluar recuperacion y absorcion,
6. revisar divergencias materiales con el sistema,
7. sintetizar y orientar la semana siguiente,
8. declarar confianza y limitaciones.

## 8. Estructura de salida

### Seccion 0 - Veredicto semanal
3-5 lineas que respondan:

- semana productiva, neutra o problematica,
- balance carga/recuperacion adecuado o no,
- principal alerta o ausencia de alerta.

Regla:

- el veredicto debe poder sostenerse con las secciones posteriores.

### Seccion 1 - Perfil del microciclo
Tabla de 7 dias con columnas minimas:

| Dia | Sueno | gate_badge | Action | Sesion(es) | load_day | work_total_min_day | z3_min_day |
|---|---|---|---|---|---|---|---|

Reglas:

- si no hubo sesion, el dia sigue apareciendo,
- si faltan datos de una capa, mostrarlo como ausente, no como cero,
- aqui no se interpreta; solo se presenta el esqueleto semanal.

### Seccion 2 - Carga y estructura
Debe responder:

- donde estuvieron los picos,
- donde los valles,
- si hubo alternancia carga/descarga,
- si hubo cierre con valle terminal o acumulacion final.

Metrica base prioritaria:

- `load_day`,
- `work_total_min_day`,
- `work_n_blocks_day`,
- `z3_min_day`,
- `elev_gain_day`,
- `elev_loss_day`,
- duracion total semanal.

Comparacion:

- contrastar con las 3 semanas previas,
- si la semana actual no es comparable por cobertura o contexto,
  decirlo explicitamente.

Interpretacion de la comparacion:

- si `load` semanal actual supera en `>30%` la media de las `3`
  semanas anteriores, senalarlo como pico de carga relativo,
- si es `<70%` de la media previa, interpretarlo como descarga,
  semana incompleta o reduccion material de carga,
- el rango `70-130%` describe mantenimiento o progresion moderada,
- estos umbrales son orientativos, no diagnosticos; la interpretacion
  debe considerar contexto, cobertura y motivo probable,
- si `load` no captura bien la huella real de la semana, cruzar la
  lectura con `work_total_min`, `z3_min` y carga mecanica acumulada.

SHOULD:

- cuando haya volumen material en trail, terreno con desnivel o
  sesion(es) con huella mecanica relevante, incluir `D+` y `D-`
  semanales como indicadores de carga mecanica acumulada,
- tratar `D-` semanal como senal especialmente relevante de estres
  excentrico acumulado cuando el contexto del deporte lo soporte,
- la carga mecanica semanal no equivale a sumar `mecanico_score`
  por sesion; describe acumulacion de terreno, impacto y estres
  musculoesqueletico que puede condicionar la recuperacion de forma
  parcialmente independiente del coste cardiometabolico,
- si aparece HRV deprimida, fatiga periferica o peor absorcion sin
  carga cardio proporcional, considerar la huella mecanica semanal
  como hipotesis explicativa y declararla como inferencia, no como
  hecho demostrado.

### Seccion 3 - Distribucion observada por deporte
Esta seccion describe la distribucion de intensidad realmente
observada, no la intencion del plan.

MUST:

- separar por deporte cuando haya multimodalidad material,
- usar tiempo en Z1/Z2/Z3 y `work_*` como contexto estructural,
- distinguir entre exposicion bruta por zonas y trabajo sostenido.

SHOULD:

- describir si el patron observado se parece mas a polarizado,
  piramidal, threshold o mixto, con lenguaje neutro y descriptivo.

Presentacion recomendada cuando haya multimodalidad material:

| Deporte | Tiempo aerobico total | Z1 % | Z2 % | Z3 % | work_total_min | work_n_blocks |
|---|---:|---:|---:|---:|---:|---:|

Reglas de presentacion:

- debajo de la tabla, incluir 2-4 lineas interpretativas que conecten
  los numeros con la lectura de distribucion observada,
- si un solo deporte domina claramente `>80%` del volumen aerobico
  semanal, se MAY comprimir la presentacion a una linea cuantificada
  sin tabla, siempre que no se pierda claridad,
- si la presentacion incluye deportes con zonas de confianza distinta
  (`trail/run`, `bike`, `swim`), incluir una nota breve indicando que
  los porcentajes de `Z1/Z2/Z3` describen la distribucion observada
  dentro de cada deporte, pero no son directamente comparables entre
  deportes con la misma finura fisiologica salvo que existan umbrales
  especificos y fiables para cada uno,
- si `work_longest_min` cambia materialmente la lectura estructural,
  SHOULD anadirse en la interpretacion o como columna extra.

MUST NOT:

- imponer una etiqueta unica global si los deportes tienen semanticas
  distintas o la senal es ambigua,
- tratar la etiqueta como juicio de calidad por si misma,
- redefinir continuidad semanal con umbrales nuevos cuando ya existe
  `work blocks` como semantica operativa.

### Seccion 4 - Recuperacion y absorcion
Debe integrar:

- duracion y consistencia de sueno,
- tendencia HRV de corto y medio plazo,
- HR en reposo si aporta senal,
- relacion entre carga reciente y estado de recuperacion.

Reglas:

- `sleep` y HRV matinal son capas distintas; no presentarlas como si
  fueran la misma medicion,
- si hay dias `FLAG_mecanico`, `Unstable` o con calidad degradada,
  hacer visible el impacto en confianza,
- no sobreinterpretar una oscilacion pequena aislada.

Presentacion recomendada para HRV cuando la ventana cubra `4+`
semanas:

| Semana | RMSSD media (OK) | n dias OK | HR reposo media |
|---|---:|---:|---:|

Reglas HRV:

- usar preferentemente dias con `Calidad = OK`,
- interpretar la direccion tras la tabla: progresa, oscila,
  regresa o estancada,
- si `n dias OK` es bajo o irregular, rebajar confianza de la lectura.

A nivel semanal, distinguir dos lecturas de HRV:

- recuperacion intra-semana:
  evaluar si, tras el principal o los principales picos de carga de la
  semana, la HRV vuelve al rango observado antes de esos picos o deja
  una senal clara de recuperacion funcional antes del cierre semanal,
- tendencia inter-semana:
  la comparacion de medias semanales en ventana de `6-8` semanas
  informa si hay adaptacion acumulada, oscilacion, estancamiento o
  regresion.

Reglas adicionales HRV:

- la lectura intra-semana se ancla a la estructura real del
  microciclo, no a dias fijos del calendario,
- si el pico principal cae al final de la semana y no hay tiempo
  suficiente para observar recuperacion, declararlo como limitacion,
- si el inicio de la semana ya llega degradado por carga previa,
  reducir la fuerza de la comparacion intra-semana.

Presentacion recomendada para sueno:

- comparar el agregado semanal con `2-3` semanas anteriores,
- incluir media de duracion y rango,
- incluir `%` de noches `< 7h`,
- incluir media de sueno profundo cuando exista cobertura suficiente.

Reglas de sueno:

- si la cobertura de sueno profundo es baja o muy incompleta,
  declararlo y no tratar la media como senal fuerte.

### Seccion 5 - Monotony y strain
Estas metricas son auxiliares y no desplazan la lectura principal.

Definicion operativa recomendada:

- `monotony = media(load_day semana) / desviacion_estandar(load_day semana)`
- `strain = load_semanal_total * monotony`

Semantica:

- `monotony` describe cuan uniforme o repetitiva fue la carga diaria,
- `strain` describe carga semanal ponderada por esa uniformidad.

Reglas:

- el calculo MUST incluir los 7 dias del calendario; dias sin sesion
  computan como `load_day = 0`,
- si un dia tiene solo fuerza o movilidad con `load < 10`, usar el
  valor real, no cero,
- presentar como indicador de contexto, no como diagnostico autonomo
  de sobrecarga,
- si la semana tiene cobertura rara, distribucion atipica de fuerza,
  o `load_day` poco interpretable, declararlo y rebajar peso
  interpretativo.

### Seccion 6 - Divergencias relevantes con el sistema
Solo incluir si hubo divergencias materiales.

Comparar:

- decision real del entrenamiento,
- `Action`,
- `reason_text`,
- calidad del dato del dia cuando cambie la lectura.

Reglas:

- no comparar solo contra `gate_badge`,
- MUST NOT moralizar; es calibracion, no juicio,
- si no hubo divergencias relevantes, decirlo en una linea o omitir la
  seccion.

SHOULD:

- para cada divergencia material, evaluar brevemente si los datos de
  los `2-3` dias siguientes confirmaron o desmintieron la
  recomendacion del sistema,
- priorizar como evidencia posterior:
  - evolucion de HRV,
  - `Action` y `reason_text` de los dias siguientes,
  - calidad de recuperacion y sueno,
  - estructura y respuesta de la siguiente sesion solo si aporta una
    senal clara y trazable,
- si los datos posteriores no son interpretables o la cobertura es
  insuficiente, decirlo explicitamente.

### Seccion 7 - Orientacion para la siguiente semana
Debe ser breve, concreta y condicional.

MUST:

- priorizar condiciones y restricciones,
- anclar cada orientacion a una variable observable,
- ser especifica al estado actual de la semana.

SHOULD:

- incluir una condicion de entrada para el primer pico de carga de la
  semana siguiente, anclada a la primera variable operativa que estara
  disponible al inicio del microciclo,
- priorizar como variables de entrada:
  - HRV matinal,
  - `Action` y `reason_text` del primer dia,
  - calidad de sueno de la noche previa cuando aporte senal,
- la condicion de entrada no prescribe una sesion concreta; define si
  se puede arrancar con carga o si conviene extender la recuperacion
  `24-48h`.

MUST NOT:

- prescribir sesiones exactas como si existiera un plan formal,
- dar consejos genericos que servirian para cualquier semana.

### Seccion 8 - Confianza y limitaciones
Debe declarar:

- cobertura real de datos,
- calidad de HRV y sueno,
- ausencias o incoherencias relevantes,
- que parte de la conclusion es robusta y cual es tentativa.

## 9. Regla de compresion
Si la semana es simple y sin hallazgos materiales, el informe se
puede comprimir a:

- veredicto semanal,
- tabla del microciclo,
- orientacion breve,
- limitaciones esenciales.

Regla:

- la compresion no depende solo de que "todo este verde",
- si `reason_text`, calidad del dato o estructura semanal introducen
  cautelas materiales, no comprimir en exceso.

Regla especifica para semanas de descarga:

- si la semana muestra un patron claro de descarga
  (`load` semanal `<60%` de la media de las `3` semanas previas) y no
  hay una causa externa dominante que lo explique, la lectura MUST
  priorizar evidencia de recuperacion y supercompensacion por encima
  del analisis de carga bruta,
- en una descarga, la baja carga no es ausencia de hallazgo; es el
  hallazgo principal que debe evaluarse,
- en ese caso, priorizar:
  - tendencia HRV intra-semana,
  - tendencia HRV inter-semana cuando aporte contexto,
  - calidad y consistencia del sueno,
  - senales de mejor absorcion o persistencia de fatiga,
- una semana de descarga MUST NOT comprimirse solo por parecer
  "tranquila"; primero debe evaluarse si la descarga esta cumpliendo
  su funcion fisiologica.

Criterios orientativos de compresion:

- semana sin cautelas materiales en `Action` o `reason_text`,
- carga semanal en rango comparable a las `3` semanas previas,
- sueno suficiente y sin senales claras de degradacion,
- sin divergencias materiales con el sistema,
- sin senal clara de regresion en HRV.

Reglas de decision:

- si se cumplen todos, SHOULD comprimirse,
- si hay una cautela material unica, evaluar si basta con desplegar
  solo la seccion afectada,
- si hay multiples cautelas o una senal fuerte de regresion, SHOULD
  usarse informe completo,
- la compresion se decide por materialidad, no por simple conteo de
  checks.

## 10. Reglas generales
### MUST
- separar dato de inferencia,
- usar lenguaje tecnico y neutro,
- cuantificar siempre que sea posible,
- reutilizar la semantica canonica ya existente del proyecto,
- tratar `work_*` como la capa principal de continuidad util cuando
  aporte mas senal que la simple exposicion por zonas.

### SHOULD
- preferir tablas cuando el contenido sea comparable,
- usar ejemplos de sesion solo cuando iluminen un patron semanal,
- describir por deporte si ello evita una lectura agregada enganosa.

### MUST NOT
- inventar una periodizacion que no existe en los datos,
- usar una sola etiqueta semanal si el patron es mixto o ambiguo,
- convertir monotony/strain en arbitro central del informe,
- presentar una inferencia longitudinal como hecho fuerte si la
  cobertura no la sostiene.

## 11. Exclusion explicita de esta v1
Esta version corta no obliga a incluir como secciones fijas:

- revision formal del macrociclo,
- memoria editorial respecto al informe semanal anterior,
- scoring numerico de adherencia,
- prescripcion de sesiones concretas.

## 12. Regla final
El metodo de sesion vive en `SESSION_ANALYSIS_METHOD.md`.
El tono, baseline y confianza viven en `ENDURANCE_AGENT_DOMAIN.md`.
Este documento extiende ese marco al nivel semanal sin reemplazarlo.
