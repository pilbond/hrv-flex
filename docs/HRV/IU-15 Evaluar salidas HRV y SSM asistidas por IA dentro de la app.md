# IU-15 Evaluar salidas HRV y SSM asistidas por IA dentro de la app

> Fecha: 2026-06-26
> Estado: propuesta
> Alcance: evaluacion funcional y tecnica. Sin analisis de coste.

## 1. Veredicto ejecutivo

La idea tiene valor, pero solo si se formula bien:

- la IA no debe sustituir el gate ni la logica canonica;
- la IA si puede mejorar la salida narrativa y la explicacion operativa;
- la integracion final debe vivir dentro de la app, no depender de copiar JSON
  manualmente en un chat externo;
- el camino correcto es construir primero una capa local de `handoff` y una
  llamada API opcional y auditable, antes de pensar en MCP o agentes mas
  complejos.

La recomendacion central es esta:

1. mantener `FINAL`, `reason_items` y el SSM como capas deterministas y
   reproducibles calculadas en Python;
2. usar IA para producir un `render` narrativo adicional, disciplinado por
   contrato, sobre esas salidas ya calculadas;
3. incorporar esa ejecucion como opcion de la app, con feature flag,
   sidecar propio y degradacion limpia si la API falla.

Recorte de alcance importante:

- fase 1: solo brief diario HRV;
- fase 2: SSM;
- fases posteriores: semanal, analysis y otras superficies.

## 2. Pregunta de producto que resuelve

Hoy el sistema ya calcula:

- estado HRV diario (`FINAL`, `DASHBOARD`);
- explicacion estructurada de cautelas (`FINAL_reason_items`);
- contexto de sueno y carga;
- lectura sombra del SSM con `daily_user_summary`;
- capa analitica local en `analysis/`.

Lo que falta no es mas dato, sino una mejor salida para consumo humano dentro
de la app:

- mas legible;
- mas razonada;
- mas consistente en tono;
- capaz de separar dato, inferencia, contexto y accion sin obligar al usuario
  a leer columnas o JSON.

## 3. Donde si aporta la IA

### 3.1 Render del `reason_text` diario

Es el mejor candidato.

Motivo:

- la logica base ya existe y es estable;
- `reason_items` ya separa tipo, fuente, valor y umbral;
- el problema pendiente es de redaccion y priorizacion narrativa, no de calculo.

Concluson:

- no conviene que la IA "decida" el `reason_text` desde datos crudos;
- si conviene que la IA genere una salida textual disciplinada a partir de:
  - `gate_badge`
  - `Action`
  - `Action_detail`
  - `reason_items`
  - subset curado de HRV, sueno y carga reciente.

### 3.2 Render explicativo del SSM

Tambien tiene valor, pero con una frontera muy clara.

Debe tratarse explicitamente como fase 2, no como parte del MVP.

Hoy `build_hrv_ssm.py` ya produce una interpretacion local reproducible en
`daily_user_summary.interpretive_text`.

La IA no deberia:

- recalcular el estado latente;
- reinterpretar el filtro de Kalman;
- ni convertir el SSM en una capa que mande sobre `FINAL`.

La IA si podria:

- traducir `daily_user_summary` a una salida mas clara y menos tecnica;
- integrarlo como contexto secundario del dia;
- explicitar mejor cuando el SSM refuerza, matiza o no aporta nada a la lectura
  HRV canonica.

Concluson:

- el SSM es buen candidato para una salida IA de tipo `comentario interpretativo`;
- no es buen candidato para que la IA "fabrique" la lectura primaria.

### 3.3 Otras superficies que pueden mejorar con IA

Hay al menos cuatro candidatas:

1. `brief diario de la app`
   Una tarjeta o bloque textual que resuma estado, tension y accion del dia.

2. `explicacion semanal`
   `ENDURANCE_HRV_weekly_coach.json` y el contexto de carga semanal pueden
   beneficiarse de una capa de sintesis mas humana.

3. `narrativa de analysis`
   El modulo `analysis/` ya usa handoffs y prompts; puede beneficiarse de una
   integracion mas directa con proveedores API en lugar de trabajo manual.

4. `mensajes de degradacion`
   Casos como falta de RR, sleep incompleto, carga no lista o SSM sin warmup
   pueden expresarse mejor con mensajes compactos y consistentes.

## 4. Donde no conviene meter IA

### 4.1 Gate y accion operativa

No debe delegarse a IA:

- `gate_final`
- `gate_badge`
- `Action`
- `Action_detail`
- overrides
- warnings
- veto agudo

Motivo:

- perderias reproducibilidad;
- subiria el riesgo de contradicciones;
- y obligarias a auditar texto libre donde hoy hay una decision normativa.

### 4.2 Generacion primaria de `reason_items`

Tampoco es buena idea en esta fase.

`reason_items` ya es una capa tipada, trazable y util para `analysis/`.
Cambiarla por un output IA libre degradaria el contrato.

Si la IA entra aqui, debe hacerlo como:

- render secundario de `reason_items`, o
- clasificador muy acotado y auditable en una fase experimental aparte.

### 4.3 Calculo SSM o estados fisiologicos

La IA no debe estimar:

- estados latentes;
- bandas;
- calidad de observacion;
- innovacion;
- ni comparaciones rolling.

Eso debe seguir en Python.

## 5. Arquitectura recomendada dentro de la app

## 5.1 Principio

No empezar por MCP.

El primer paso correcto es una integracion interna en la app:

1. preparar un payload curado;
2. enviar ese payload a un proveedor LLM por API;
3. guardar la salida como sidecar o campo derivado;
4. mostrarla en UI sin alterar los outputs canonicos.

## 5.2 Capa propuesta

Para el MVP, la capa debe ser mas pequena de lo que parecia en la primera
redaccion.

Propuesta fase 1:

```text
hrv_app/ai/
  config.py
  daily_brief.py
```

Responsabilidades:

- `config.py`
  Variables de entorno y feature flags.

- `daily_brief.py`
  Construccion del payload diario, prompt, llamada API, validacion de salida y
  escritura atomica del sidecar.

Nota:

- `render_ssm.py`, `providers.py` e incluso una capa separada de `io.py` se
  anadiran solo si la fase 2 realmente ocurre;
- para un proyecto N=1, la abstraccion multi-provider no debe preceder a la
  primera integracion util.

## 5.3 Outputs recomendados

No tocar `FINAL.csv` de entrada.

Propuesta inicial fase 1:

- `data/ENDURANCE_HRV_ai_daily_brief.json`
- `data/ENDURANCE_HRV_ai_daily_brief.md`

Propuesta fase 2:

- `data/ENDURANCE_HRV_ai_ssm_brief.json`
- `data/ENDURANCE_HRV_ai_ssm_brief.md`

Opcionalmente, si luego se estabiliza:

- exponer el ultimo brief en `/api/status`;
- o en un endpoint nuevo, separado de los endpoints operativos mutantes.

## 5.4 Momento de ejecucion

Recomendacion:

- ejecutar despues de generar `FINAL` y, si existe, despues de regenerar SSM;
- nunca bloquear el sync principal si la IA falla;
- registrar estado `best effort`.

Orden sugerido del sync:

1. RR -> `CORE`
2. `CORE + sleep + sessions_day` -> `FINAL/DASHBOARD`
3. `SSM shadow`
4. `AI daily brief` opcional
5. `AI SSM brief` opcional solo en fase 2

## 5.5 Feature flags

Minimo:

- `HRV_AI_ENABLED=0/1`
- `HRV_AI_PROVIDER=<provider>`
- `HRV_AI_MODEL=<model>`
- `HRV_AI_API_KEY=<secret>`
- `HRV_AI_TIMEOUT_SEC`
- `HRV_AI_LANGUAGE=es`
- `HRV_AI_DAILY_ENABLED=0/1`
- `HRV_AI_SSM_ENABLED=0/1`

## 6. Contrato recomendado de payload

La IA debe recibir contexto curado, no CSV crudos.

### 6.1 Payload diario recomendado

Bloques:

- `meta`
- `decision`
- `reason_items`
- `morning_hrv`
- `sleep_context`
- `recent_load_summary`
- `interpretation_contract`
- `expected_output`

Schema propuesto para fase 1:

```json
{
  "meta": {
    "date": "YYYY-MM-DD",
    "source_lag_notes": ["training load context is available through D-1"]
  },
  "decision": {
    "gate_badge": "VERDE++",
    "gate_final": "VERDE",
    "action": "INTENSIDAD_OK",
    "action_detail": "EJECUTAR_PLAN",
    "quality_flag": false,
    "veto_agudo": false,
    "baseline60_degraded": false
  },
  "reason_items": [
    {
      "type": "sleep_fragmentation",
      "source": "sleep",
      "message": "texto",
      "metric": "polar_interruptions_long",
      "value": 8.0,
      "threshold": 6.0
    }
  ],
  "morning_hrv": {
    "quality": "OK",
    "stability": "OK",
    "classification": "green",
    "interpretation": "HRV matinal estable y compatible con gate favorable.",
    "artifact_pct": 0.0,
    "time_to_stabilization_sec": 390.0,
    "hr_today": 49.38,
    "rmssd_today": 48.86,
    "lnrmssd_today": 3.8889,
    "hr_baseline_60d": 48.84,
    "lnrmssd_baseline_60d": 3.8598,
    "d_ln": 0.0588,
    "d_hr": -1.2495,
    "residual_tag": "++"
  },
  "sleep_context": {
    "classification": "amber",
    "interpretation": "Sueno mas fragmentado de lo habitual, como cautela contextual.",
    "sleep_duration_min": 563.5,
    "sleep_efficiency_pct": 92.83,
    "sleep_score": 72.47,
    "interruptions_long": 8.0,
    "interruptions_total": 33.0,
    "continuity": 2.8,
    "continuity_index": 2.0,
    "historical_interruption_threshold_p90": 6.0
  },
  "recent_load_summary": {
    "as_of_date": "YYYY-MM-DD",
    "load_ctx_ready": true,
    "load_3d": 152.0,
    "load_7d": 337.0,
    "load_14d": 561.0,
    "acwr_simple_prev": 0.907,
    "acute_load_72h_rel": 2.864,
    "monotony_7d_prev": 2.881,
    "strain_7d_prev": 970.9,
    "intensity_clustering_flag": 0
  },
  "interpretation_contract": {
    "hard_rules": [
      "Do not contradict gate_badge, action, or action_detail.",
      "Treat reason_items as the primary explanation layer for the day.",
      "If reason_items is empty, use decision and morning_hrv as primary context and set source_mode=reason_text_fallback.",
      "Do not diagnose illness, overtraining, or systemic fatigue."
    ]
  },
  "expected_output": {
    "language": "${HRV_AI_LANGUAGE:-es}",
    "format": "json"
  }
}
```

El objetivo de este schema no es ser bonito, sino ser ejecutable:

- usa solo campos ya existentes en `FINAL`, `sleep`, `sessions_day` y
  `reason_items`;
- limita el payload a unas 15-20 señales;
- separa claramente decision, causa primaria y contexto;
- anade clasificaciones simples calculadas en Python para evitar que el LLM
  interprete numeros crudos cuando el pipeline ya puede acotar la lectura.

### 6.2 Payload SSM recomendado

Bloques recomendados para SSM:

- `meta`
- `daily_user_summary`
- `relation_to_final`
- `interpretation_contract`
- `expected_output`

Recomendacion:

- en fase 2 el payload SSM debe apoyarse primero en
  `daily_user_summary.interpretive_text` y en los campos estructurados de
  `daily_user_summary`;
- no debe reinyectar todo `ssm_shadow.csv` en bruto.

Reglas duras del contrato:

- no contradecir `Action` ni `gate_badge`;
- tratar `reason_items` como fuente primaria cuando existan;
- tratar SSM como contexto secundario;
- no diagnosticar enfermedad, sobreentrenamiento ni fatiga sistemica;
- no inventar causalidad.

### 6.3 Contrato de salida recomendado

La salida del LLM no debe ser texto libre en fase 1.

Schema recomendado:

```json
{
  "payload_hash": "sha256-del-payload",
  "date": "YYYY-MM-DD",
  "summary": "string breve",
  "detail": "string algo mas explicativo",
  "tone": "green|amber|red",
  "source_mode": "reason_items|reason_text_fallback"
}
```

Reglas:

- `tone` debe ser compatible con `gate_final`;
- `source_mode` debe ser `reason_items` si existen `reason_items` no vacios;
- `source_mode` debe ser `reason_text_fallback` si `reason_items` esta vacio;
- `payload_hash` debe guardarse en el sidecar para idempotencia y auditoria;
- si el proveedor devuelve algo fuera de schema, la salida se descarta.

## 7. Encaje concreto de `reason_text`

Hay tres opciones de producto:

### Opcion A. Mantener `reason_text` canonico y anadir `ai_reason_text`

Es la recomendada.

Ventajas:

- no rompe contratos;
- no obliga a versionar docs/contracts de inmediato;
- mantiene el texto determinista como fallback;
- permite comparar output actual vs output IA.

### Opcion B. Reemplazar `reason_text` por IA en `FINAL`

No recomendada en primera fase.

Problemas:

- rompe reproducibilidad;
- exige reabrir el contrato de columnas y semantica;
- complica tests y auditoria.

### Opcion C. Mantener `reason_text` interno y mostrar solo el render IA en UI

Puede ser una buena fase 2.

Permite:

- conservar el canon tecnico;
- usar la IA solo como capa de presentacion.

Veredicto:

- fase inicial: A
- fase posterior posible: C

## 8. Encaje concreto del SSM

El mejor uso no es reemplazar `interpretive_text`, sino generar una salida
paralela mas usable para la app.

Propuesta:

- mantener `daily_user_summary.interpretive_text` como verdad reproducible;
- construir un `ai_ssm_brief` para UI;
- y, si ambos divergen materialmente, mostrar el determinista o marcar la
  respuesta IA como no publicable.

En otras palabras:

- el SSM no necesita un segundo cerebro;
- necesita un mejor traductor para la app.

## 9. Otras oportunidades reales

### 9.1 Weekly coach / planning note

Muy buen candidato.

Porque:

- ya hay estructura semanal;
- la necesidad es mas narrativa que matematica;
- y la salida humana se beneficia de priorizacion.

### 9.2 Analysis de sesion

Tambien buen candidato, pero ya existe trabajo local en `analysis/`.
La mejora aqui seria integrar proveedor y governance, no reinventar el modulo.

### 9.3 UI status / explicaciones de fallo

Candidato secundario pero util:

- mensajes de falta de auth;
- restore vacio;
- dataset stale;
- SSM no interpretable;
- falta de coverage.

## 9bis. Aprendizajes de intervalsicugptcoach-public

La revision externa de `intervalsicugptcoach-public` aporta tres patrones que
si merece la pena adoptar aqui, con una condicion: traducidos al contrato real
de este repo, no copiados literalmente.

### Lo que si conviene adoptar

#### 1. Payload autorizado, pequeno y explicito

La idea buena es construir un payload plano que explicite exactamente que
ve el LLM.

Aplicacion local:

- un unico payload diario curado;
- con bloques pequenos y fuente implicita estable;
- construido desde campos reales de `FINAL`, `sleep`, `sessions_day` y
  `reason_items`.

Esto encaja muy bien con la fase 1 de IU-15.

#### 2. Pre-clasificacion semantica en Python

El LLM no debe decidir si una senal es favorable o no a partir de numeros
crudos si el pipeline ya puede acotar esa lectura antes.

Aplicacion local:

- enviar `gate_final`, `gate_badge` y `Action` como verdad;
- y, cuando aporte valor, anadir campos resumidos del tipo
  `classification` o `interpretation` ya calculados en Python para las capas
  secundarias.

La idea no es que el LLM clasifique; la idea es que redacte bien una
clasificacion ya acotada.

#### 3. Prompt contractual de rendering

El prompt debe comportarse como contrato de render, no como instruccion vaga
de personalidad.

Aplicacion local:

- reglas duras;
- formato de salida JSON;
- prohibicion explicita de contradecir gate y accion;
- restriccion fuerte sobre diagnosticos e invencion causal.

### Lo que no conviene copiar

#### 1. La complejidad del builder semantico externo

Ese proyecto resuelve un problema mas amplio y heterogeneo. Aqui no hace falta
un grafo semantico de miles de lineas para el MVP.

Regla local:

- un payload diario de 15-20 campos es suficiente para fase 1.

#### 2. Nombres de campo o schema ajenos

No se deben importar ejemplos de payload con nombres como:

- `rmssd_ms`
- `rolling7_ln`
- `sleep_score_total`
- `session_acwr`

si esos no son los nombres canonicos ni los mejores representantes del
contrato actual de este repo.

Regla local:

- el payload debe mapearse solo desde columnas y sidecars reales del proyecto.

#### 3. Falta de validacion del output IA

La revision externa acierta al señalar que no basta con recibir texto del LLM.

Regla local:

- la salida debe validarse estructuralmente;
- y su `tone` debe comprobarse contra `gate_final`, no contra igualdad literal
  con `gate_badge`, porque `gate_badge` tiene variantes como `VERDE++`.

### Concluson operativa

El patron que si merece copiar de ese proyecto es este:

- payload curado y pequeno;
- prompt contractual;
- salida JSON validable;
- y LLM como renderer, no como motor de decision.

Lo que no debe heredarse es:

- complejidad innecesaria;
- schema ajeno;
- ni confianza excesiva en texto libre sin validacion.

## 10. Riesgos y mitigaciones

### Riesgo 1. Contradiccion con el gate

Mitigacion:

- contrato estricto;
- prompt disciplinado;
- validacion post-output;
- fallback al texto determinista.

Diseno minimo de validacion:

- si `gate_final=VERDE`, `tone` debe ser `green`;
- si `gate_final=AMBAR`, `tone` debe ser `amber`;
- si `gate_final=ROJO`, `tone` debe ser `red`;
- si falla el parseo, el schema o esta compatibilidad, la respuesta IA no se
  publica y se conserva el render determinista.

### Riesgo 2. Especulacion fisiologica

Mitigacion:

- payload acotado;
- instrucciones negativas claras;
- plantilla de salida breve;
- sin autonomia para decidir.

### Riesgo 3. Dependencia operativa de proveedor externo

Mitigacion:

- ejecucion opcional;
- no bloquear sync;
- sidecars separados;
- timeout corto.

Mitigacion adicional:

- si ya existe sidecar para la fecha actual y el hash del payload no ha
  cambiado, no repetir la llamada;
- registrar el hash usado en el sidecar para idempotencia y debugging.

### Riesgo 4. Mezclar canon y presentacion

Mitigacion:

- mantener outputs canonicos sin cambios en fase 1;
- exponer IA como capa adicional de presentacion.

## 11. Fases recomendadas

### Fase 1. Evaluacion integrada minima

- generar payload diario dentro de la app;
- llamar API LLM;
- validar schema y `tone`;
- guardar sidecar IA diario;
- no tocar `FINAL`;
- no tocar UI salvo una vista minima opcional;
- no incluir SSM.

### Fase 2. SSM brief

- payload SSM;
- render IA SSM;
- sidecar separado;
- UI opcional.

### Fase 3. Weekly / planning note

- usar `weekly_coach.json`;
- generar brief semanal;
- validar tono y utilidad.

### Fase 4. Consolidacion UI/API

- endpoint propio read-only para briefs IA;
- tarjeta UI;
- trazabilidad de freshness y fallback.

## 12. Cambios de repo que probablemente haran falta

- nueva carpeta `hrv_app/ai/`
- nuevos sidecars `ENDURANCE_HRV_ai_*`
- posible endpoint read-only nuevo
- tests de:
  - construccion de payload
  - fallback si falla API
  - validacion de contrato de salida
  - rechazo si `tone` contradice el gate
  - skip por idempotencia cuando el payload no cambia
  - no contradiccion con gate/action

Si se decide que algun campo canonico cambia de significado o se reemplaza por
texto IA dentro de `FINAL`, entonces habra que actualizar `docs/contracts/`.
Mientras la IA viva como capa adicional, no hace falta tocar el contrato
normativo.

## 13. Recomendacion final

La mejor jugada no es "que la IA haga el reason text", sino esta:

- que la app siga calculando el estado y las cautelas de forma determinista;
- que una capa IA interna genere una salida narrativa adicional y disciplinada;
- que esa salida se ejecute automaticamente dentro de la app;
- y que el sistema degrade con elegancia cuando la IA no este disponible.

Orden de valor esperado:

1. brief diario HRV desde `reason_items`
2. brief SSM como contexto secundario
3. brief semanal / planning note
4. mejoras de narrativa en `analysis/`

Lo que no recomiendo es delegar en IA:

- el gate;
- la accion;
- el calculo SSM;
- ni la generacion primaria de la capa estructurada `reason_items`.

## 14. Revision critica del documento

### 14.1 Sintesis de la tesis original

La tesis del documento es que la IA puede aportar valor como capa de
presentacion dentro de la app si se limita a renderizar salidas ya calculadas
por el pipeline. La decision, el gate, `Action`, `reason_items` y el SSM deben
seguir siendo deterministas; la fase 1 debe limitarse al brief diario HRV y
dejar el SSM para fase 2.

### 14.2 Contraargumentos mas fuertes

1. El documento asume que un brief IA aporta valor incremental frente a mejorar
   el `reason_text` determinista. Esa hipotesis es plausible, pero todavia no
   esta demostrada dentro de la app con una evaluacion comparativa estable.

2. El payload propuesto anade `classification` e `interpretation`, pero no
   define todavia las reglas exactas para calcularlas. Si esas etiquetas se
   implementan de forma laxa, se crea una segunda capa semantica paralela al
   gate que puede divergir del contrato HRV.

3. La validacion `tone` contra `gate_final` cubre el caso normal
   `VERDE/AMBAR/ROJO`, pero no explicita como tratar dias `NO`, `INVALID`,
   ausencia de `FINAL`, `quality_flag=True` o cualquier estado no publicable.

4. La integracion dentro del sync diario puede parecer barata, pero introduce
   una dependencia externa en un flujo operativo que hoy es reproducible sin
   red de IA. Aunque se marque `best effort`, hace falta definir bien logs,
   timeouts, sidecars y freshness para que no ensucie el diagnostico diario.

### 14.3 Confianza por afirmacion

- Afirmacion: la IA no debe sustituir el gate, `Action`, `reason_items` ni el
  calculo SSM.
  - Tipo: recomendacion
  - Confianza: 90/100
  - Estado: razonable

- Afirmacion: el brief diario HRV es el mejor candidato para fase 1.
  - Tipo: inferencial
  - Confianza: 80/100
  - Estado: razonable

- Afirmacion: el SSM debe quedar para fase 2 como comentario secundario.
  - Tipo: recomendacion
  - Confianza: 85/100
  - Estado: razonable

- Afirmacion: el schema `{summary, detail, tone, source_mode}` es suficiente
  para validar una salida IA diaria.
  - Tipo: inferencial
  - Confianza: 70/100
  - Estado: razonable, con borde bajo

- Afirmacion: `classification` e `interpretation` reduciran la especulacion del
  LLM.
  - Tipo: inferencial
  - Confianza: 65/100
  - Estado: especulativo hasta definir formulas y probar ejemplos reales

### 14.4 Fallos potenciales y verificacion

- Fallo: `classification` queda sin definicion normativa.
  - Plausibilidad: alta
  - Estado de comprobacion: confirmado
  - Justificacion: el documento propone el campo, pero no especifica aun reglas
    para derivarlo desde `gate_final`, `residual_tag`, `quality_flag`,
    `sleep_int_p90` u otros campos.

- Fallo: estados no publicables no estan cubiertos por el contrato de salida.
  - Plausibilidad: media
  - Estado de comprobacion: confirmado
  - Justificacion: la validacion actual solo contempla `VERDE`, `AMBAR` y
    `ROJO`; el sistema tambien maneja calidad, invalidacion y casos de ausencia
    de dato que pueden requerir `status=not_applicable` o fallback directo.

- Fallo: el sidecar IA podria quedar desfasado respecto a `FINAL` o
  `reason_items`.
  - Plausibilidad: media
  - Estado de comprobacion: parcialmente mitigado
  - Justificacion: el documento incorpora `payload_hash`, pero todavia no exige
    hash de fuentes, `as_of`, ni comparacion contra manifest o fecha ultima de
    `FINAL`.

- Fallo: el contrato de salida es demasiado pobre para UI futura.
  - Plausibilidad: media
  - Estado de comprobacion: indeterminado
  - Justificacion: `summary` y `detail` bastan para fase 1, pero una UI podria
    necesitar `sections`, `warnings`, `fallback_reason`, `published=false` o
    `validation_errors` sin reabrir el contrato.

### 14.5 Cambios y conclusiones

- Que se mantiene:
  La arquitectura general sigue siendo correcta: IA como renderer opcional,
  sidecars separados, no bloqueo del sync, y SSM diferido a fase 2.

- Que se debilita:
  La confianza en que el schema actual sea suficiente para produccion. Es buen
  MVP, pero necesita estados de publicacion, errores y casos no aplicables.

- Que se corrige:
  Antes de implementar, hay que definir reglas de `classification` y ampliar la
  validacion para estados no `VERDE/AMBAR/ROJO`.

- Incertidumbres abiertas:
  Falta probar si el brief IA mejora de forma consistente el `reason_text`
  determinista en una muestra de dias reales con `reason_items` vacios,
  multiples cautelas, `quality_flag=True`, `ROJO`, y carga desfasada.

### 14.6 Respuesta revisada

IU-15 sigue siendo una propuesta valida, pero no deberia pasar directamente a
implementacion sin cerrar tres detalles: reglas exactas para
`classification`, estados de salida para dias no publicables, y contrato de
sidecar con `payload_hash`, fecha, estado de publicacion y errores de
validacion. Con esos ajustes, la fase 1 puede implementarse como un MVP
acotado y reversible: brief diario HRV generado por API, guardado como sidecar,
validado contra `gate_final`, y descartado automaticamente cuando no cumpla el
contrato. El SSM debe permanecer fuera de fase 1.

## 15. Conclusiones

### 15.1 Estado del documento

El documento ha pasado por tres iteraciones: propuesta inicial, incorporacion
de aprendizajes externos, y revision critica. El resultado es un diseño de
producto coherente con la arquitectura del repo, acotado al alcance N=1, y con
una fase 1 ejecutable.

### 15.2 Lo que esta resuelto

1. **Frontera determinista/IA.** La decision mas importante del documento esta
   bien fundamentada y verificada contra el codigo: `gate_final`, `Action`,
   `reason_items` y el calculo SSM no se delegan a IA. La IA entra como
   renderer de salidas ya calculadas. Esta frontera no debe renegociarse en
   fase 1.

2. **Payload concreto.** El schema de la seccion 6.1 usa campos reales del
   pipeline (`gate_badge`, `gate_final`, `Action`, `Action_detail`,
   `residual_tag`, `d_ln`, `d_hr`, `lnrmssd_today`, `sleep_score`,
   `interruptions_long`, `load_3d`, `acwr_simple_prev`, etc.). Los nombres
   son canonicos del repo. El payload es pequeno (~20 campos), plano, y
   construible desde `FINAL`, `sleep` y `sessions_day` sin transformaciones
   costosas.

3. **Contrato de salida.** El schema `{payload_hash, date, summary, detail,
   tone, source_mode}` es minimo pero suficiente para fase 1. La validacion
   `tone ↔ gate_final` tiene reglas explicitas.

4. **Degradacion.** La IA no bloquea el sync. El sidecar es opcional. El
   fallback es el `reason_text` determinista existente. Idempotencia por
   `payload_hash`.

5. **Fases incrementales.** Brief diario → SSM → semanal → UI. Cada fase es
   independiente y reversible.

### 15.3 Lo que queda abierto antes de implementar

1. **`gate_final = "NO"`.** La revision critica senala correctamente que la
   validacion tone/gate solo contempla `VERDE`, `AMBAR` y `ROJO`. Pero el
   pipeline real tiene un cuarto valor: `NO`, que se asigna a dias con
   `Calidad=INVALID`, roll3 insuficiente, baseline60 insuficiente, o SWC
   degenerado (lineas 968, 1042, 1049, 1069, 1074 de
   `build_hrv_final_dashboard.py`). Para estos dias, el brief IA no tiene
   sentido — la decision correcta es no generar brief y registrar
   `status=not_applicable` en el sidecar.

   Regla propuesta:
   - si `gate_final = "NO"`, no llamar al LLM;
   - escribir sidecar con `{"status": "not_applicable", "reason": "gate_NO",
     "date": "...", "payload_hash": "..."}`;
   - la UI muestra el fallback determinista o nada.

2. **`quality_flag = True`.** Los dias con calidad degradada (`Calidad != OK`
   pero no `INVALID`) reciben un gate valido (`VERDE`, `AMBAR` o `ROJO`)
   pero con `quality_flag=True`. El payload ya incluye este campo. La
   pregunta es si el brief IA debe mencionarlo o simplemente ignorarlo.

   Recomendacion: incluirlo como hard rule en el prompt —
   `If quality_flag is true, mention that the HRV reading has reduced
   confidence today` — pero no impedir la generacion del brief.

3. **Reglas de `classification` para `morning_hrv` y `sleep_context`.** El
   documento propone estos campos pero no define las reglas. Para fase 1,
   la derivacion mas simple y coherente es:
   - `morning_hrv.classification`: derivar de `residual_tag` → `++/+++` es
     `green`, `""` o `+` es `green`, `-` es `amber`, `--/---` es `red`;
   - `sleep_context.classification`: derivar de si `interruptions_long >
     historical_interruption_threshold_p90` → `amber`, else `green`; o de
     `sleep_score < 65` → `red`.
   Esto es derivable sin logica nueva — son campos que ya existen.

4. **Contrato de sidecar ampliado.** Para cubrir los casos anteriores, el
   sidecar deberia admitir al menos:

   ```json
   {
     "status": "ok|not_applicable|error|validation_failed",
     "date": "YYYY-MM-DD",
     "payload_hash": "sha256",
     "tone": "green|amber|red",
     "summary": "...",
     "detail": "...",
     "source_mode": "reason_items|reason_text_fallback",
     "validation_errors": [],
     "reason": "gate_NO|api_timeout|tone_mismatch|..."
   }
   ```

   `status=ok` es el caso feliz. Los demas permiten diagnostico sin romper
   el schema.

### 15.4 Riesgos residuales

- **Valor incremental no demostrado.** El documento asume que un brief IA
  mejora la experiencia frente al `reason_text` determinista. Esto es
  plausible pero no esta probado. La fase 1 deberia incluir una comparacion
  informal: para 5-10 dias reales con distintos gates y reason_items, generar
  el brief IA y comparar con el `reason_text` actual. Si no mejora, no hay
  justificacion para el coste operativo.

- **Drift semantico.** Si `classification` e `interpretation` se calculan con
  reglas distintas al gate, se crea una segunda capa semantica que puede
  divergir. Mitigacion: derivar `classification` solo de campos que ya
  participan en el gate (`residual_tag`, `d_ln`, `d_hr`, `quality_flag`), no
  inventar logica nueva.

- **Coste.** El documento excluye analisis de coste por diseno. Para fase 1
  con un LLM tipo Haiku/Sonnet, ~1K tokens input + ~300 output, el coste es
  <$0.01/dia. No es un blocker, pero deberia documentarse como baseline.

### 15.5 Veredicto final

IU-15 es implementable como MVP si se cierran los cuatro puntos de la seccion
15.3. La arquitectura es conservadora en el buen sentido: no toca outputs
canonicos, degrada limpiamente, y el alcance de fase 1 es pequeno.

La pregunta real no es si se puede construir (se puede, en 1-2 sesiones), sino
si el brief IA aporta valor perceptible frente al `reason_text` determinista.
La recomendacion es construir fase 1 como experimento acotado y validar con
dias reales antes de comprometerse con fases posteriores.

Orden de trabajo sugerido:

1. Definir reglas de `classification` (seccion 15.3.3)
2. Implementar `hrv_app/ai/config.py` + `daily_brief.py`
3. Hook en `hrv_sync_flow.py` despues del SSM
4. Generar briefs para 5-10 dias reales y comparar con `reason_text`
5. Decidir si se expone en UI o se descarta

## 16. Evaluacion del paquete de evaluacion experimental

### 16.1 Que se ha generado

Se ha montado un paquete de evaluacion reproducible en
`research/iu15_ai_brief_eval/` con:

- script generador (`research/scripts/generate_iu15_ai_brief_eval.py`);
- 5 payloads (2026-06-22 a 2026-06-26), uno por dia;
- prompt para el modelo (`prompt.md`);
- rubrica de puntuacion manual (`rubric.md`);
- baseline separada (`baseline_reason_texts.json`);
- manifiesto con hashes por payload (`manifest.json`).

El proposito es evaluar si la salida de un LLM, alimentada con el payload
curado, mejora el `reason_text` determinista actual. El `reason_text` no se
muestra al modelo — la comparacion queda para la evaluacion humana.

### 16.2 Lo que esta bien hecho

**1. Script reproducible y bien estructurado.** `generate_iu15_ai_brief_eval.py`
lee directamente de `FINAL`, `sleep`, `sessions_day` y `reason_items.json`.
Selecciona automaticamente la semana ISO mas reciente. Genera payload, hash,
baseline y manifiesto en una sola ejecucion. Los helpers `_to_py`, `_row_dict`
y `_hash_json` son correctos y cubren los edge cases de numpy/pandas.

**2. Campos canonicos verificados.** Los payloads usan nombres reales del
contrato HRV de este repo: `gate_badge`, `gate_final`, `Action`,
`Action_detail`, `quality_flag`, `veto_agudo`, `baseline60_degraded`,
`Calidad`, `HRV_Stability`, `Artifact_pct`, `lnRMSSD_today`, `d_ln`, `d_HR`,
`residual_tag`, `polar_sleep_duration_min`, `polar_interruptions_long`,
`sleep_int_p90`, `monotony_7d_prev`, `strain_7d_prev`, `acwr_simple_prev`,
`load_ctx_ready`. No hay nombres importados de otro proyecto.

**3. Pre-clasificacion implementada.** `_classify_morning()` y
`_classify_sleep()` derivan `classification` e `interpretation` directamente
desde `gate_final`, `quality_flag`, `residual_tag`, `sleep_score`,
`interruptions_long` y `reason_items`. Esto cierra el punto 15.3.3 de la
revision critica: las reglas de clasificacion ya tienen una implementacion
concreta y verificable.

**4. Cobertura de variabilidad real.** Los 5 dias cubren:
- 4x VERDE (con variantes `VERDE+`, `VERDE---`, `VERDE++`) y 1x ROJO;
- reason_items desde 2 hasta 7 items por dia;
- cautelas de carga (monotonia, strain), sueno (fragmentacion, duracion),
  recuperacion (discordance, fragile, conflicted) y veto agudo;
- el dia ROJO tiene `veto_agudo=true` y `recovery_discordance_flag=true`,
  que es un caso complejo y exigente para el LLM.

**5. Separacion limpia baseline/prompt.** El `reason_text` no esta en el
payload ni en el prompt. Esto permite una evaluacion ciega.

**6. Rubrica operativa.** 5 criterios, 0-2 cada uno, total 0-10. Los
criterios estan bien calibrados: gate fidelity, uso de reason_items,
no especulacion, utilidad practica, brevedad. La regla de decision
(8-10 = mejor, 6-7 = mixto, 0-5 = no mejor) es clara.

### 16.3 Lo que puede mejorarse

**1. Redundancia en reason_items de los payloads.**

Varios dias incluyen items que son variantes del mismo mensaje:
- `recovery_support` y `recovery_discordance` emiten frases casi identicas
  (`"VERDE, pero sueño y carga reciente piden prudencia"`);
- `green_load_caution` resume lo que `monotony` + `strain` ya dicen.

Esto no es un error del script — es lo que produce el pipeline real. Pero
el LLM podria interpretar la redundancia como multiples cautelas distintas y
amplificar el tono. Seria util que el prompt incluyera una regla como:
`"Some reason_items are redundant by design (e.g. recovery_support and
recovery_discordance may repeat the same message). Treat them as one caution,
not multiple."`.

**2. El payload del dia ROJO (26-jun) tiene `sleep_context.classification = green`
a pesar de `polar_interruptions_total = 38`.**

`_classify_sleep()` solo mira `interruptions_long` vs `sleep_int_p90`, y
38 interrupciones totales con 3 largas no lo dispara. Esto es tecnicament
correcto por las reglas actuales, pero un LLM que lea
`polar_interruptions_total: 38` podria percibir una incoherencia con
`classification: green`. Opciones:
- documentar en el prompt que `classification` es autoritativa y que el LLM
  no debe re-clasificar por su cuenta;
- o ampliar `_classify_sleep()` para considerar `interruptions_total` en
  un threshold alto (p.ej. > 30).

**3. El payload del 26-jun tiene `polar_sleep_duration_min = 883.5`
(14.7 horas).**

Esto parece un valor anomalo o un fin de semana con siesta incluida en el
span. Si es un valor real (la medicion de Polar a veces captura siestas),
no es un error del script, pero el LLM podria interpretarlo como dato
sospechoso. Podria anadirse un flag `sleep_duration_anomaly` cuando la
duracion exceda un umbral razonable (p.ej. > 12h).

**4. Falta una regla en el prompt sobre `max_words`.**

El payload incluye `expected_output.max_words: 170`, pero el prompt no
menciona explicitamente un limite de longitud. Conviene anadir una linea:
`"Keep the total output under 170 words."`.

**5. El prompt no dice que `classification` e `interpretation` son
autoritativos.**

El LLM recibe los numeros crudos de HRV y sueno ademas de la
clasificacion. Si no sabe que la clasificacion prevalece, podria reclasificar
por su cuenta mirando los numeros. Sugerencia: anadir al prompt:
`"The classification and interpretation fields in morning_hrv and
sleep_context are pre-computed and authoritative. Do not override them."`.

**6. No hay caso `gate_final = NO` en los 5 dias.**

Los 5 payloads tienen gates validos (VERDE o ROJO). El script maneja `NO`
correctamente en `_classify_morning()` (devuelve `not_applicable`), pero no
hay ejemplo de ese caso en la evaluacion. Esto limita la cobertura pero no
es un defecto del script — depende de los datos reales de la semana.

**7. La rubrica no pondera los criterios.**

Los 5 criterios valen 0-2 cada uno con peso igual. Pero `gate fidelity`
deberia ser mas critico que `brevity`. Un brief que contradice el gate es
inservible aunque sea breve y bien escrito. Sugerencia: hacer que `gate
fidelity` sea eliminatorio — si es 0, la puntuacion total es 0
independientemente de los demas criterios.

### 16.4 Coherencia con IU-15

El paquete de evaluacion implementa fielmente lo que IU-15 propone:

- payload curado, pequeno, con campos canonicos;
- clasificacion pre-calculada en Python;
- prompt contractual con hard rules;
- salida JSON tipada;
- baseline separada para comparacion ciega;
- trazabilidad por hash.

Los puntos abiertos de la seccion 15.3 de IU-15 quedan asi:

| Punto | Estado |
|---|---|
| 15.3.1 `gate_final = NO` | Cubierto en `_classify_morning()`, sin ejemplo en la semana |
| 15.3.2 `quality_flag = True` | Cubierto en `_classify_morning()` y en el prompt, sin ejemplo en la semana |
| 15.3.3 Reglas de `classification` | Implementadas en `_classify_morning()` y `_classify_sleep()` |
| 15.3.4 Contrato de sidecar ampliado | No aplica al paquete de evaluacion (es para la app) |

### 16.5 Veredicto del paquete

El paquete esta bien construido y es coherente con la propuesta. Puede usarse
directamente para la evaluacion manual. Las mejoras sugeridas (prompt mas
explicito sobre redundancia, `max_words` y autoridad de `classification`)
son afinaciones menores que mejorarian la calidad de los resultados sin
cambiar la estructura.

El paso siguiente es ejecutar la evaluacion: pegar cada payload con el prompt
en el modelo elegido, recoger las 5 salidas, y puntuar con la rubrica
comparando contra el baseline. Si la media esta en 8-10, la fase 1 tiene
justificacion empirica para avanzar.
