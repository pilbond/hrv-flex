# ENDURANCE HRV - Propuestas vigentes

**Revision:** 2026-06-10

## 1. Proposito

Este documento sustituye a `ENDURANCE_HRV_Propuestas_v4.md`.

Su objetivo es mantener un backlog razonado de mejoras para la capa HRV
global, teniendo en cuenta el estado real del proyecto. No conserva
propuestas antiguas solo porque fueran razonables cuando se redactaron:
cada linea se evalua contra la implementacion actual, los contratos
vigentes y las tareas del Kanvas.

Este documento vive en `docs/contracts/` porque determina que mejoras
normativas u operativas del sistema HRV siguen teniendo sentido. Una
propuesta no modifica por si sola el contrato de columnas, el gate, QA ni
la semantica de una metrica. Cuando se adopte una mejora, deben actualizarse
los contratos especificos afectados.

## 2. Estado de partida

El proyecto ya ha incorporado una parte importante de las propuestas
historicas:

- Tier 2 en `CORE`: `SI_baevsky`, `SD1`, `SD2` y `SD1_SD2_ratio`.
- separacion entre `CORE`, `FINAL` y `DASHBOARD`, sin Tier 2 en la vista
  diaria;
- capa de accion integrada mediante `Action`, `Action_detail` y
  `reason_text`;
- veto agudo y suelo de SWC;
- deteccion informativa de saturacion parasimpatica;
- `quality_flag` con restriccion operativa de intensidad;
- contexto automatico de sueno Polar;
- contexto de carga mediante ventanas rolling, ACWR simple, monotonia,
  strain y clustering de intensidad;
- warnings de baseline duales y una capa SSM en sombra.

Por tanto, no debe intentarse implementar literalmente el antiguo plan v4.
Varias de sus soluciones han sido superadas por componentes actuales mas
ricos o mejor separados por capas.

## 3. Prioridad alta

### 3.1 Outcomes prospectivos y labels minimos

**Estado:** parcialmente propuesto en Kanvas mediante `IU-06 Captura
prospectiva minima de RPE sintomas y timestamp`.

**Decision:** valida, pero degradada de implementacion completa a piloto
prospectivo minimo.

Es el principal vacio del sistema. Sin outcomes y trazabilidad de la
adherencia no puede medirse si `gate_final` y `Action` protegen al atleta o
son demasiado conservadores.

Estos datos no son ground truth fisiologico. Son outcomes y proxies
subjetivos afectados por el tipo de sesion, el plan, la adherencia, el
entorno y otros confusores. Sirven para evaluar coherencia y detectar casos
discordantes, no para atribuir causalmente el resultado al gate.

La implementacion no debe copiar sin revision el esquema antiguo. Debe
aprovechar los datos ya disponibles en `sessions.csv`,
`sessions_day.csv` y `ENDURANCE_HRV_wellness_subjective.csv`, y limitar el
input manual a datos que no puedan inferirse de forma fiable.

El piloto debe empezar con el minimo compatible con `IU-06`:

- `Fecha`;
- timestamp de captura;
- RPE o resultado subjetivo post-sesion;
- sintomas;
- nota breve opcional.

`fill_before_viewing_gate`, `planned_session_risk_plan`, `followed_reco`,
`alcohol` y `trained_today` quedan condicionados a que el piloto demuestre
adherencia suficiente y una pregunta analitica que necesite cada campo.

Antes de implementarlo debe cerrarse la semantica temporal: que se rellena
antes de ver el gate y que se registra despues de la sesion.

### 3.2 Metricas de evaluacion del decisor

**Estado:** no implementadas y dependientes de labels.

**Decision:** validas como auditoria descriptiva, pero degradadas como
metricas de rendimiento del decisor.

Las metricas iniciales deben ser simples, auditables y mostrar siempre el
denominador:

- falsos verdes graves;
- falsos rojos repetidos;
- cobertura de labels;
- cobertura de plan previo;
- adherencia a la recomendacion;
- resultados separados entre plan previo y clasificacion retrospectiva.

No deben emitirse conclusiones firmes con muestras pequenas. Las metricas
de plan no deben reportarse como evaluacion valida mientras no alcancen un
minimo predefinido de casos evaluables.

Un resultado malo tras un gate verde no demuestra por si solo un falso
verde: puede reflejar una sesion mal planteada, calor, enfermedad, terreno,
dolor o baja adherencia. Por ello, `FV_grave` y `FR_repetido` deben
presentarse como casos discordantes para revision, no como errores causales
confirmados del algoritmo.

### 3.3 Trazabilidad del pipeline HRV principal

**Estado:** parcial. Existen metadata para sesiones y SSM, pero no una
metadata equivalente para `CORE`, `FINAL` y `DASHBOARD`.

**Decision:** valida, pero degradada a manifest minimo.

Cada ejecucion deberia registrar como minimo:

- version del algoritmo;
- version de esquema;
- timestamp de ejecucion;
- hash de configuracion;
- parametros del decisor que puedan cambiar el resultado.

El commit Git y los hashes de inputs son opcionales. Un commit puede ser
engañoso con un worktree sucio y los hashes exhaustivos añaden coste y
churn sin mejorar necesariamente la operacion N=1.

No es necesario introducir todas estas propiedades como columnas de los
CSV. Un sidecar atomico del pipeline principal es suficiente, salvo que se
demuestre la necesidad de trazabilidad por fila.

### 3.4 Comparador canary de configuraciones

**Estado:** no implementado como herramienta del pipeline HRV.

**Decision:** valida de forma condicionada; no debe implementarse hasta que
exista un cambio concreto del decisor que comparar.

Antes de cambiar gate o `Action`, debe poder ejecutarse el mismo historico
con configuracion A y B y comparar:

- cambios de color;
- cambios de accion;
- falsos verdes y falsos rojos, cuando haya labels;
- dias discordantes;
- impacto por calidad de medicion y disponibilidad de contexto.

No hace falta infraestructura permanente ni despliegue paralelo. Para N=1
puede bastar ejecutar dos configuraciones en un directorio temporal y
generar una tabla de diferencias. Solo debe extraerse un script reusable si
esa comparacion se repite.

## 4. Prioridad media

### 4.1 Reporte periodico de evaluacion

**Estado:** no implementado.

**Decision:** degradada a reporte bajo demanda cuando exista muestra
suficiente.

Debe resumir cobertura, adherencia, falsos verdes, falsos rojos, calidad de
datos y cambios entre versiones. Construirlo antes de disponer de ground
truth solo produciria un informe descriptivo sin capacidad de evaluar el
decisor.

La periodicidad mensual es orientativa. Con pocos eventos evaluables puede
ser mas honesto emitirlo por volumen minimo de observaciones.

### 4.2 Reglas secuenciales

**Estado:** parcialmente cubiertas por `bad_streak`, `bad_7d` y
`Action_detail = DESCARGA`.

**Decision:** evaluar, no ampliar de inmediato.

Las reglas antiguas de rojos consecutivos, recuperacion tras varios dias
malos o combinaciones con sintomas pueden duplicar comportamiento actual.
Solo deben añadirse si un analisis con labels demuestra un fallo concreto.
Cada nueva regla debe evaluarse por separado mediante el comparador canary.

### 4.3 Nota de cambio decisorio

**Estado:** no existe como artefacto explicito para cada version relevante
del gate.

**Decision:** degradada; debe formar parte del artefacto canary o de la nota
de tarea, no crear una familia documental independiente.

Una nota por version decisoria debe documentar:

- objetivo del cambio;
- parametros modificados;
- datos usados para evaluarlo;
- metricas predefinidas;
- limitaciones;
- resultado del canary;
- decision de adoptar, mantener en sombra o descartar.

No se necesita una plataforma MLOps.

### 4.4 Confianza continua de la medicion

**Estado:** existe `quality_flag`, pero no un score continuo canonico.

**Decision:** degradada a descartada por defecto. Solo se reabre si aparece
un consumidor operativo y demuestra ventaja frente a `quality_flag`.

Un score puede aportar resolucion adicional, pero tambien crear otra
metrica sin accion asociada. Antes de implementarlo debe definirse que
decision cambia frente al booleano actual y comprobar que mejora la
clasificacion de calidad.

### 4.5 Drift longitudinal

**Estado:** existen warnings duales, baseline adaptativo y diagnosticos SSM;
la evaluación del drift longitudinal sigue pendiente.

**Decision:** degradada a evaluacion en sombra mediante `HG-01`. Debe
cerrarse o absorberse si no demuestra valor incremental.

El trabajo debe demostrar valor incremental frente a
`degraded_vs_best`, `degraded_vs_current_normal` y los diagnosticos
longitudinales existentes. No debe entrar directamente en `FINAL`,
`DASHBOARD` o `reason_text`.

## 5. Prioridad baja

### 5.1 Hora de despertar

Polar proporciona `sleep_end_time`, pero el archivo canonico de sueno no la
persiste.

**Decision:** degradada a descartada en el alcance actual. Solo tiene sentido si se abre un estudio de
latencia de medicion o variacion circadiana. No debe afectar al gate sin
evidencia propia.

### 5.2 Score continuo 2D y severidad ambar

**Decision:** degradada a descartada.

El sistema ya dispone de `gate_badge`, residual, `reason_items`, calidad y
contexto de recuperacion. Una nueva escala `AMBAR_LEVE/AMBAR_FUERTE`
probablemente duplicaria semantica y aumentaria la carga cognitiva.

### 5.3 SWC asimetrico

**Decision:** degradada a standby; no implementar sin evidencia de fallo
sistematico del SWC actual.

Es un cambio del decisor y requiere labels, preregistro y canary.

### 5.4 Baseline ponderado por calidad

**Decision:** degradada a descartada.

Incluir mediciones dudosas con peso parcial puede contaminar el baseline.
El filtrado actual es mas defendible mientras no exista evidencia de que
descarta demasiada señal valida.

### 5.5 Features adicionales de tendencia

Incluye pendientes cortas, `recovery_debt` y flechas de tendencia.

**Decision:** absorbidas por analysis, semanal o UI; dejan de ser propuesta
del pipeline HRV global.

Ya existen warnings, acumulacion de gates y tendencias semanales. No se
justifican nuevas columnas operativas salvo que resuelvan una pregunta no
cubierta.

### 5.6 Playbook fisiologico

**Decision:** trasladada conceptualmente a documentacion analitica; deja de
ser propuesta operativa del pipeline HRV global.

Los patrones fisiologicos son utiles para orientar una interpretacion,
pero HRV, pulso y sueno no identifican por si solos una causa clinica.

## 6. Propuestas que no deben recibir inversion ahora

### 6.1 DFA-alpha1 como guardarrail del gate matutino

DFA-alpha1 ya tiene un uso especifico en `analysis/` para sesiones. Llevarlo
al decisor matutino exige protocolo propio, repetibilidad demostrada y
valor incremental frente al gate actual.

### 6.2 SampEn

Su complejidad y sensibilidad metodologica no estan justificadas sin
ground truth que muestre falsos verdes no cubiertos por las señales
actuales.

### 6.3 Indices PNS/SNS personalizados

Derivan de metricas existentes y pueden aumentar el ruido cognitivo. No
deben incorporarse al dashboard diario.

### 6.4 Clasificacion simplificada de riesgo real

El pipeline actual de sesiones modela intensidad, carga, zonas y contexto
con mas detalle que la antigua clasificacion basada solo en
`icu_intensity` y `sub_type`. Reintroducirla literalmente seria una
regresion.

### 6.5 Reproducir literalmente el contexto antiguo

No debe reconstruirse el antiguo bloque basado en `sleep_bad_auto`,
ATL/CTL/TSB y umbrales fijos de ANS charge. El proyecto ha evolucionado
hacia:

- umbrales personales de sueno;
- carga rolling;
- ACWR simple;
- monotonia y strain;
- clustering de intensidad;
- contexto de recuperacion multiseñal;
- señales estructuradas en `reason_items`.

Estas capas actuales son el punto de partida.

## 7. Secuencia recomendada

1. Ejecutar `IU-06` como piloto minimo de captura prospectiva.
2. Medir adherencia, cobertura y utilidad antes de ampliar campos.
3. Añadir un manifest minimo del pipeline HRV cuando se toque de nuevo el
   versionado o el decisor.
4. Revisar casos discordantes con denominadores explicitos, sin atribucion
   causal automatica.
5. Crear una comparacion canary solo ante un cambio concreto del decisor.
6. Generar un reporte bajo demanda cuando haya muestra suficiente.
7. Revisar reglas secuenciales o nuevos scores solo si los datos muestran
   un fallo concreto.

## 8. Regla de adopcion

Una propuesta solo pasa a implementacion operativa cuando:

1. resuelve un problema observado y no solo una posibilidad teorica;
2. no duplica una señal o artefacto existente;
3. tiene consumidor y consecuencia definidos;
4. puede evaluarse con datos disponibles;
5. respeta la separacion entre gate, accion, contexto y analysis;
6. incluye tests y actualizacion de contratos cuando afecta logica HRV,
   columnas, QA, gating o significado de metricas;
7. se incorpora a Kanvas antes de iniciar una implementacion sustancial.

## 9. Revision critica libre

Esta seccion revisa adversarialmente las recomendaciones anteriores. En
caso de conflicto, esta revision y los estados de la seccion 10 prevalecen
sobre la prioridad nominal de las secciones 3 a 6.

### 9.1 Sintesis de la tesis original

La tesis original sostenia que el siguiente salto de calidad debia venir de
labels prospectivos, metricas de error, trazabilidad y comparaciones canary,
mientras que nuevas metricas fisiologicas debian aplazarse. La direccion
general era prudente, pero sobrevaloraba la capacidad de los labels para
actuar como ground truth y adelantaba infraestructura antes de demostrar
que tendria uso recurrente.

### 9.2 Contraargumentos mas fuertes

1. Los outcomes manuales no identifican causalmente aciertos o fallos del
   gate. El resultado de una sesion depende del estimulo elegido, terreno,
   temperatura, dolor, motivacion, nutricion y adherencia, entre otros
   factores.
2. El coste principal de los labels no es tecnico, sino conductual. Un
   esquema amplio puede fracasar por baja adherencia y generar una base
   sesgada hacia dias llamativos.
3. Metadata exhaustiva, model cards y un framework canary pueden convertirse
   en mantenimiento sin consumidor. Para N=1 deben aparecer al ritmo de
   cambios reales del decisor.
4. El proyecto tiene tareas operativas y de seguridad abiertas. Mejorar
   OAuth, refresh tokens, errores y escritura atomica puede aportar mas
   fiabilidad inmediata que construir una capa formal de evaluacion HRV.

### 9.3 Confianza por afirmacion

- Afirmacion: falta una captura prospectiva util.
  - Tipo: factual e inferencial.
  - Confianza: 85/100.
  - Estado: razonable.
- Afirmacion: los labels permitiran medir si el gate protege al atleta.
  - Tipo: inferencial.
  - Confianza: 55/100.
  - Estado: especulativo; permiten auditar asociacion y discordancia, no
    demostrar proteccion causal.
- Afirmacion: el pipeline HRV necesita metadata propia.
  - Tipo: recomendacion.
  - Confianza: 72/100 para un manifest minimo; 40/100 para hashes y
    trazabilidad exhaustiva.
  - Estado: razonable solo en alcance minimo.
- Afirmacion: se necesita un comparador canary reusable.
  - Tipo: recomendacion.
  - Confianza: 60/100.
  - Estado: especulativo hasta que exista un cambio decisorio concreto.
- Afirmacion: nuevas metricas como SampEn, PNS/SNS o un score 2D no son
  prioritarias.
  - Tipo: recomendacion.
  - Confianza: 90/100.
  - Estado: razonable.

### 9.4 Fallos potenciales y verificacion

- Fallo: confundir outcome subjetivo con ground truth.
  - Plausibilidad: alta.
  - Estado de comprobacion: confirmado conceptualmente.
  - Justificacion: el outcome no controla el estimulo ni los confusores y
    no permite atribucion causal directa al gate.
- Fallo: baja adherencia al esquema de labels.
  - Plausibilidad: alta.
  - Estado de comprobacion: no confirmado.
  - Justificacion: todavia no existe el piloto; `IU-06` debe medirlo antes
    de ampliar el esquema.
- Fallo: sobreingenieria de gobernanza.
  - Plausibilidad: media.
  - Estado de comprobacion: indeterminado.
  - Justificacion: metadata y canary aportan trazabilidad, pero no hay una
    cadencia demostrada de cambios del decisor que justifique un framework.
- Fallo: distraer trabajo de robustez operativa.
  - Plausibilidad: media-alta.
  - Estado de comprobacion: confirmado como coste de oportunidad.
  - Justificacion: Kanvas mantiene abiertas tareas de OAuth, refresh,
    errores, runtime web y escritura atomica.

### 9.5 Cambios y conclusiones

- Se mantiene: capturar datos prospectivos minimos y evitar nuevas metricas
  fisiologicas sin evidencia.
- Se debilita: tratar `FV_grave` y `FR_repetido` como medidas directas de
  calidad del algoritmo.
- Se corrige: `IU-06` ya cubre el punto de entrada natural para el piloto;
  no debe abrirse una iniciativa paralela de labels.
- Se degrada: metadata exhaustiva, model cards separadas, reporte mensual
  fijo y framework canary reusable.
- Queda incierto: si la adherencia y densidad de outcomes alcanzaran para
  evaluar cambios del decisor con utilidad practica.

### 9.6 Respuesta revisada

El trabajo con mayor valor no es implantar todo el sistema de gobernanza
propuesto, sino ejecutar un piloto pequeno mediante `IU-06`. Si ese piloto
consigue cobertura estable y produce casos comparables, se añaden metricas
descriptivas y un manifest minimo. Canary y documentacion de version se
crean cuando exista un cambio real de gate o `Action`, no antes.

Las propuestas de nuevas metricas o scores quedan descartadas, absorbidas
por capas existentes o en standby. La prioridad global del repositorio debe
seguir favoreciendo robustez operativa y seguridad sobre nueva
infraestructura analitica.

## 10. Estado final de validez

| Propuesta | Estado revisado | Condicion o destino |
|---|---|---|
| Captura prospectiva minima | **VALIDA** | Ejecutar mediante `IU-06` como piloto reducido |
| Esquema amplio de labels | **DEGRADADA** | Ampliar solo si el piloto demuestra adherencia y necesidad |
| `FV_grave` / `FR_repetido` | **DEGRADADAS** | Casos discordantes descriptivos, no errores causales |
| Manifest HRV minimo | **VALIDA CONDICIONADA** | Añadir al tocar versionado o decisor |
| Metadata e input hashes exhaustivos | **DEGRADADA** | Solo si aparece una auditoria que los necesite |
| Comparador canary | **VALIDA CONDICIONADA** | Crear ante un cambio concreto de gate o `Action` |
| Reporte periodico | **DEGRADADA** | Bajo demanda y con muestra suficiente |
| Reglas secuenciales nuevas | **DEGRADADAS** | Evaluar solo ante fallos observados |
| Model card independiente | **DEGRADADA** | Integrar en tarea o resultado canary |
| Score continuo de confianza | **DESCARTADA POR DEFECTO** | Reabrir solo con consumidor y ventaja demostrada |
| Drift longitudinal | **DEGRADADA A SHADOW** | Resolver mediante `HG-01`; absorber o cerrar sin valor incremental |
| Hora de despertar | **DESCARTADA** | Reabrir solo para estudio circadiano |
| Score 2D / severidad ambar | **DESCARTADA** | Duplica señales existentes |
| SWC asimetrico | **STANDBY** | Requiere evidencia, labels y canary |
| Baseline ponderado por calidad | **DESCARTADA** | Riesgo de contaminar baseline |
| Tendencias y `recovery_debt` | **ABSORBIDAS** | Analysis, semanal o UI |
| Playbook fisiologico | **TRASLADADA** | Documentacion analitica, no decisor |
| DFA-alpha1 matutino | **DESCARTADA AHORA** | Sin protocolo ni evidencia incremental |
| SampEn | **DESCARTADA** | Complejidad sin problema demostrado |
| PNS/SNS personalizado | **DESCARTADA** | Redundancia y carga cognitiva |
| Riesgo real simplificado | **SUPERADA** | Sustituida por el pipeline de sesiones |
| Contexto antiguo ATL/CTL/TSB/ANS | **SUPERADA** | Sustituido por contexto actual personalizado |
