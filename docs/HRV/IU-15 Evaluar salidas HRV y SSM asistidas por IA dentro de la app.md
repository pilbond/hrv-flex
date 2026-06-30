# IU-15 Evaluar salidas HRV y SSM asistidas por IA dentro de la app

> Fecha: 2026-06-29
> Estado: analisis y diseno tecnico
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

Decision adicional tras la evaluacion experimental:

- `K2` pasa a ser el candidato de fase 1 para el brief diario;
- deja de tener sentido seguir comparando modelos antes del MVP;
- el siguiente paso correcto es integracion tecnica minima + revision semanal
  de salidas reales.

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

### 5.1 Principio

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

- `data/ENDURANCE_HRV_ai_daily_brief_latest.json`
- `data/ENDURANCE_HRV_ai_daily_brief_YYYY-MM-DD.json`

Propuesta fase 2:

- `data/ENDURANCE_HRV_ai_ssm_brief_latest.json`
- `data/ENDURANCE_HRV_ai_ssm_brief_YYYY-MM-DD.json`

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
- `HRV_AI_TEMPERATURE`
- `HRV_AI_TOP_P`
- `HRV_AI_THINKING`
- `HRV_AI_MAX_TOKENS`
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

Schema propuesto para fase 1.

Importante:

- este schema ya no usa nombres "limpios" o normalizados;
- refleja el payload real probado en la evaluacion experimental;
- si en el futuro se quiere exponer una API externa con nombres renombrados,
  eso debe documentarse como una traduccion explicita y no como el contrato
  interno de fase 1.

```json
{
  "meta": {
    "date": "YYYY-MM-DD",
    "generated_at": "ISO-8601",
    "week_start": "YYYY-MM-DD",
    "week_end": "YYYY-MM-DD",
    "source_lag_notes": ["texto"],
    "data_sources": ["data/ENDURANCE_HRV_master_FINAL.csv"]
  },
  "decision": {
    "gate_badge": "VERDE++",
    "gate_final": "VERDE",
    "Action": "INTENSIDAD_OK",
    "Action_detail": "EJECUTAR_PLAN",
    "quality_flag": false,
    "veto_agudo": false,
    "baseline60_degraded": false,
    "recovery_context_quality": "rich",
    "recovery_support_class": "supported",
    "recovery_discordance_flag": false
  },
  "reason_items": [
    {
      "type": "monotony",
      "layer": "inference",
      "source": "sessions_day",
      "message": "texto",
      "metric": "monotony_7d_prev",
      "value": 2.881,
      "threshold": 2.0
    }
  ],
  "reason_items_meta": {
    "contains_message_overlap": false,
    "overlap_groups": [],
    "renderable_metrics": [
      {
        "type": "monotony",
        "metric": "monotony_7d_prev",
        "value": 2.881,
        "threshold": 2.0,
        "severity": "high",
        "message": "texto"
      }
    ],
    "rendering_note": "If multiple reason_items express the same practical caution, mention it once.",
    "numeric_rendering_policy": "You may cite metric values and thresholds already present in reason_items_meta.renderable_metrics or reason_items. Do not compute derived statistics from morning_hrv, sleep_context, or recent_load_summary raw fields."
  },
  "morning_hrv": {
    "Calidad": "OK",
    "HRV_Stability": "OK",
    "Artifact_pct": 0.0,
    "Tiempo_Estabilizacion": 390.0,
    "HR_today": 49.38,
    "RMSSD_stable": 48.86,
    "lnRMSSD_today": 3.8889,
    "lnRMSSD_used": 3.9180,
    "HR_used": 47.58,
    "ln_base60": 3.8598,
    "HR_base60": 48.84,
    "d_ln": 0.0588,
    "d_HR": -1.2495,
    "residual_tag": "++",
    "tail_mismatch_pct": 0.91,
    "classification_authoritative": true,
    "classification": "green",
    "interpretation": "HRV matinal estable y compatible con gate favorable."
  },
  "sleep_context": {
    "polar_sleep_duration_min": 563.5,
    "polar_sleep_span_min": 607.0,
    "polar_deep_pct": 9.23,
    "polar_rem_pct": 24.58,
    "polar_efficiency_pct": 92.83,
    "polar_continuity": 2.8,
    "polar_continuity_index": 2.0,
    "polar_interruptions_long": 8.0,
    "polar_interruptions_total": 33.0,
    "polar_sleep_score": 72.47,
    "polar_night_rmssd": 58.0,
    "sleep_dur_p10": 358.75,
    "sleep_dur_p90": 519.0,
    "sleep_int_p90": 5.5,
    "classification_authoritative": true,
    "classification": "amber",
    "interpretation": "Sueno mas fragmentado de lo habitual, con cautela contextual.",
    "sleep_duration_anomaly": {
      "flag": false,
      "reasons": []
    }
  },
  "recent_load_summary": {
    "Fecha": "YYYY-MM-DD",
    "load_day": 16.0,
    "load_3d": 150.0,
    "load_7d": 362.0,
    "load_14d": 588.0,
    "acwr_simple_prev": 0.99,
    "acute_load_72h_rel": 2.871,
    "monotony_7d_prev": 2.666,
    "strain_7d_prev": 965.2,
    "intensity_clustering_flag": 0,
    "load_ctx_ready": true,
    "as_of_date": "YYYY-MM-DD"
  },
  "interpretation_contract": {
    "hard_rules": [
      "Do not contradict gate_badge, gate_final, Action, or Action_detail.",
      "Treat reason_items as the primary explanation layer for the day.",
      "If reason_items is empty, use decision and morning_hrv as primary context and set source_mode=reason_text_fallback.",
      "Treat classification and interpretation fields as authoritative; do not reclassify from raw numbers.",
      "If multiple reason_items overlap semantically, collapse them into one caution in the rendered text.",
      "You may cite metric values and thresholds already present in reason_items or reason_items_meta.renderable_metrics.",
      "Do not compute derived statistics from morning_hrv, sleep_context, or recent_load_summary raw fields.",
      "Do not diagnose illness, overtraining, or systemic fatigue."
    ]
  },
  "expected_output": {
    "language": "${HRV_AI_LANGUAGE:-es}",
    "format": "json",
    "max_words": 220
  }
}
```

El objetivo de este schema no es ser bonito, sino ser ejecutable:

- usa solo campos ya existentes en `FINAL`, `sleep`, `sessions_day` y
  `reason_items`;
- limita el payload a un conjunto curado y acotado de senales relevantes, sin
  reenviar tablas completas ni CSV crudos;
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
  "date": "YYYY-MM-DD",
  "summary": "string breve",
  "detail": "string algo mas explicativo",
  "tone": "green|amber|red|not_applicable",
  "source_mode": "reason_items|reason_text_fallback"
}
```

Reglas:

- `tone` debe ser compatible con `gate_final`;
- `source_mode` debe ser `reason_items` si existen `reason_items` no vacios;
- `source_mode` debe ser `reason_text_fallback` si `reason_items` esta vacio;
- `tone=not_applicable` solo aplica a casos no publicables;
- si el proveedor devuelve algo fuera de schema, la salida se descarta.

Nota:

- este es el contrato minimo de salida del LLM, no el schema completo del
  sidecar;
- `payload_hash`, `status`, `provider`, `model`, `published` y
  `validation_errors` pertenecen al sidecar operativo que envuelve esta
  respuesta para idempotencia, trazabilidad y control de publicacion.

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
- si `gate_final=NO`, el brief no se publica y el caso se trata como
  `not_applicable`;
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
- refinar la tarjeta `Lectura HRV de hoy` si hiciera falta;
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
   el `reason_text` determinista. Esa hipotesis es plausible, pero necesita
   validacion continua con uso real dentro de la app; no basta con una
   comparacion puntual o una impresion aislada.

2. Historicamente, el payload propuesto anadia `classification` e
   `interpretation` antes de tener reglas exactas para calcularlas. Ese riesgo
   ya no esta abierto: las reglas quedaron alineadas con
   `_classify_morning()` y `_classify_sleep()` y el problema pasa a ser de
   mantener esa coherencia, no de definirla desde cero.

3. Historicamente, la validacion `tone` contra `gate_final` cubria solo el
   caso normal `VERDE/AMBAR/ROJO`. Ese hueco ya quedo cubierto con
   `not_applicable`, reglas de no publicacion y sidecar ampliado para dias
   `NO` u otros estados no publicables.

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
  - Confianza: 80/100
  - Estado: razonable; formulas implementadas y probadas en la muestra

### 14.4 Fallos potenciales y verificacion

- Fallo: `classification` queda sin definicion normativa.
  - Plausibilidad: alta
  - Estado de comprobacion: resuelto
  - Justificacion: la definicion operativa ya quedo aterrizada en
    `_classify_morning()` y `_classify_sleep()`, y el documento actualizado
    remite explicitamente a esa logica.

- Fallo: estados no publicables no estan cubiertos por el contrato de salida.
  - Plausibilidad: media
  - Estado de comprobacion: mitigado
  - Justificacion: el documento ya cubre `gate_final=NO`,
    `status=not_applicable`, `published=false` y el tratamiento de casos no
    publicables tanto en riesgos como en sidecars y reglas de ejecucion.

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
  La necesidad original de definir `classification` y cubrir estados no
  `VERDE/AMBAR/ROJO` ya quedo absorbida por las secciones 15 a 17. El foco
  pasa de "cerrar huecos de diseno" a "mantener coherencia entre documento,
  payload y codigo".

- Incertidumbres abiertas:
  Falta probar si el brief IA mejora de forma consistente el `reason_text`
  determinista en una muestra de dias reales con `reason_items` vacios,
  multiples cautelas, `quality_flag=True`, `ROJO`, y carga desfasada.

### 14.6 Respuesta revisada

IU-15 sigue siendo una propuesta valida y los bloqueos principales detectados
en esta revision critica ya quedaron cerrados en las secciones 15 a 17:

- reglas de `classification` alineadas con el script real;
- estados no publicables cubiertos;
- contrato de sidecar ya ampliado.

Por tanto, el documento ya no esta en fase de "no implementar todavia", sino
en fase de MVP tecnico pequeno, reversible y auditable para el brief diario
HRV. El SSM debe seguir fuera de fase 1.

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
   `recovery_support_class`, `reason_items_meta`, `Calidad`,
   `HRV_Stability`, `lnRMSSD_today`, `polar_sleep_score`,
   `polar_interruptions_long`, `load_3d`, `acwr_simple_prev`,
   `expected_output.max_words`, etc.). Los nombres son canonicos del repo.
   El payload es pequeno, ejecutable y construible desde `FINAL`, `sleep`,
   `sessions_day` y `reason_items` sin transformaciones costosas.

3. **Contrato de salida.** El JSON minimo del LLM
   `{date, summary, detail, tone, source_mode}` y el sidecar operativo que lo
   envuelve (`payload_hash`, `status`, `provider`, `published`, etc.) son
   suficientes para fase 1. La validacion `tone ↔ gate_final` tiene reglas
   explicitas.

4. **Degradacion.** La IA no bloquea el sync. El sidecar es opcional. El
   fallback es el `reason_text` determinista existente. Idempotencia por
   `payload_hash`.

5. **Fases incrementales.** Brief diario → SSM → semanal → UI. Cada fase es
   independiente y reversible.

### 15.3 Decisiones operativas ya cerradas para el MVP

1. **`gate_final = "NO"`.** La revision critica detecto correctamente que
   hacia falta cubrir este caso. El pipeline real tiene un cuarto valor: `NO`,
   que se asigna a dias con
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
   decision de MVP es que el brief IA debe mencionarlo como reduccion de
   confianza, no usarlo como veto.

   Recomendacion: incluirlo como hard rule en el prompt —
   `If quality_flag is true, mention that the HRV reading has reduced
   confidence today` — pero no impedir la generacion del brief.

3. **Reglas de `classification` para `morning_hrv` y `sleep_context`.** Este
   punto ya quedo resuelto para fase 1. La derivacion correcta debe quedar
   alineada con la implementacion real del
   paquete de evaluacion:
   - `morning_hrv.classification`: anclada en `gate_final`, con `quality_flag`
     como matiz de confianza, para no crear una segunda capa semantica que
     diverja del gate;
   - `sleep_context.classification`: derivada de `sleep_score`,
     `interruptions_long` y `reason_items`, como capa secundaria de contexto.
   La regla importante no es inventar una taxonomia nueva, sino reutilizar la
   misma logica Python ya probada en `_classify_morning()` y
   `_classify_sleep()`.

4. **Contrato de sidecar ampliado.** Para cubrir los casos anteriores, el
   sidecar minimo quedo superado por el schema mas completo de la seccion 17.6,
   pero este bloque conserva el nucleo funcional que debe mantenerse al menos:

   ```json
   {
     "status": "ok|not_applicable|error|validation_failed",
     "date": "YYYY-MM-DD",
     "payload_hash": "sha256",
     "tone": "green|amber|red|not_applicable",
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
  reglas distintas a las ya probadas en Python, se crea una segunda capa
  semantica que puede divergir del gate o del contexto real. Mitigacion:
  reutilizar la misma logica implementada en `_classify_morning()` y
  `_classify_sleep()`, no inventar una clasificacion paralela en el documento
  o en el prompt.

### 15.5 Veredicto final

IU-15 es implementable como MVP. La arquitectura es conservadora en el buen
sentido: no toca outputs canonicos, degrada limpiamente, y el alcance de fase
1 es pequeno.

La pregunta real no es si se puede construir (se puede, en 1-2 sesiones), sino
si el brief IA aporta valor perceptible frente al `reason_text` determinista.
La recomendacion es construir fase 1 como experimento acotado y validar con
dias reales antes de comprometerse con fases posteriores.

Orden de trabajo sugerido:

1. Implementar `hrv_app/ai/config.py` + `daily_brief.py`
2. Hook en `hrv_sync_flow.py` despues del SSM
3. Generar briefs para 5-10 dias reales y comparar con `reason_text`
4. Si supera esa revision, mantenerlo en la UI minima ya definida; si no,
   dejarlo como sidecar interno y seguir con fallback determinista

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
`_classify_sleep()` derivan `classification` e `interpretation` con reglas ya
implementadas y verificables:

- `_classify_morning()` se ancla en `gate_final` y `quality_flag`;
- `_classify_sleep()` usa `sleep_score`, `interruptions_long` y `reason_items`
  como contexto secundario.

Esto cierra el punto 15.3.3 de la revision critica.

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

### 16.3 Lo que se mejoro y lo que sigue abierto

**1. Redundancia en `reason_items`: sigue siendo un riesgo real, pero ya esta
mitigado en el contrato.**

La redundancia del pipeline sigue existiendo en dias con
`recovery_support`/`recovery_discordance` o con `green_load_caution` mas
metricas base. Eso no se elimino del payload, pero ya se mitigo con:

- `reason_items_meta.contains_message_overlap`
- `reason_items_meta.overlap_groups`
- regla explicita de colapsar cautelas solapadas en el prompt y en
  `interpretation_contract.hard_rules`

Este punto sigue siendo valido como foco de observacion semanal, no como hueco
del diseno.

**2. Los datos anomicos del 26-jun ya no describen el estado actual.**

Las observaciones historicas sobre:

- `polar_interruptions_total = 38`
- `polar_sleep_duration_min = 883.5`

correspondian a una version anterior del CSV y de los payloads. Tras la
regeneracion:

- `polar_interruptions_total` del 26-jun es 34;
- `polar_sleep_duration_min` del 26-jun es 474.5;
- `sleep_duration_anomaly` ya existe en el payload como flag explicito.

Por tanto, esas lineas deben leerse como hallazgos historicos ya cerrados, no
como problemas vigentes del paquete.

**3. `max_words`, autoridad de `classification` y regla eliminatoria ya fueron
resueltos.**

Estado actual del paquete:

- `expected_output.max_words` ya existe y esta fijado en 220;
- el prompt ya trata `classification` e `interpretation` como autoritativos;
- la rubrica ya hace `gate fidelity` eliminatoria.

Estos puntos ya no son trabajo pendiente.

**4. Sigue faltando cobertura real de `gate_final = NO`.**

La limitacion que si sigue abierta es que la semana evaluada no contiene ningun
dia `NO`. El script y el contrato ya contemplan `not_applicable`, pero no hay
ejemplo real dentro del paquete de 5 dias. Esto no invalida la evaluacion, pero
si deja una esquina sin probar con datos de la muestra actual.

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

El paquete esta bien construido y es coherente con la propuesta. La mayoria de
las mejoras detectadas durante la revision ya quedaron incorporadas en payload,
prompt y rubrica; la unica limitacion real que sigue abierta en la muestra es
la falta de un caso `gate_final = NO`.

La evaluacion ya ha cumplido su funcion: cerrar el payload, el prompt y el
criterio de aceptacion lo suficiente como para pasar a un MVP tecnico con
`K2`, fallback determinista y revision semanal de salidas reales.

## 17. Diseno tecnico minimo aprobado para fase 1

### 17.1 Decision de producto

Tras la evaluacion manual de la semana 2026-06-22 a 2026-06-26, la decision
operativa propuesta es:

- pasar a implementacion tecnica del brief diario HRV dentro de la app;
- fijar `K2` como renderer inicial de fase 1;
- mantener `reason_text` determinista como fallback y referencia;
- dejar el SSM fuera del MVP y tratarlo explicitamente como fase 2.

La politica de calidad pasa a ser esta:

- integrar primero;
- revisar semanalmente las salidas reales;
- ajustar prompt o payload solo si aparece un patron repetido de fallo.

### 17.2 Objetivo exacto del MVP

Generar automaticamente, dentro del sync diario, un `ai_daily_brief`
adicional a partir de:

- `ENDURANCE_HRV_master_FINAL.csv`
- `ENDURANCE_HRV_sleep.csv`
- `ENDURANCE_HRV_sessions_day.csv`
- `ENDURANCE_HRV_master_FINAL_reason_items.json`

El brief IA no cambia ningun output canonico. Solo crea una capa de
presentacion adicional, publicable si valida y descartable si falla.

### 17.3 Cambios minimos de codigo

Estructura propuesta:

```text
hrv_app/ai/
  __init__.py
  config.py
  daily_brief.py
```

Responsabilidades:

- `config.py`
  Lee feature flags, proveedor, modelo, timeout, idioma y version de prompt.

- `daily_brief.py`
  Construye payload, calcula `payload_hash`, decide skip/not_applicable,
  llama al proveedor, valida la salida y escribe sidecars.

No hace falta en fase 1:

- capa compleja multi-provider;
- endpoint nuevo dedicado;
- cambiar `FINAL.csv`;
- generar brief SSM;
- persistir `.md` adicional para UI.

### 17.4 Punto de enganche real en el flujo

El hook natural esta en `hrv_app/hrv_sync_flow.py`, dentro de
`_process_rr_files()`, despues de:

1. `run_build_hrv_final_dashboard_only()`
2. `run_build_hrv_ssm_shadow_only()`

Orden recomendado del final del sync:

1. RR -> `CORE`
2. sleep -> `ENDURANCE_HRV_sleep.csv`
3. `FINAL/DASHBOARD`
4. `SSM shadow`
5. `AI daily brief` (`best effort`)
6. backup / reporting ya existentes

Razon:

- el payload necesita `FINAL` y `reason_items` ya cerrados;
- el sync principal ya ha producido todo lo importante antes de llamar a IA;
- un fallo IA no contamina los outputs operativos ni el diagnostico del dia.

### 17.5 Sidecars propuestos

#### Latest para UI

`data/ENDURANCE_HRV_ai_daily_brief_latest.json`

Uso:

- lectura rapida por la UI del dia vigente;
- depuracion simple;
- no requiere buscar por fecha.

#### Historico para revision semanal

`data/ENDURANCE_HRV_ai_daily_brief_YYYY-MM-DD.json`

Uso:

- revisar ultimos 7 dias;
- comparar versiones de prompt;
- detectar drift o casos peores que `reason_text`;
- no hace falta mostrar este historico en la UI del MVP.

No hace falta `.md` en fase 1. La UI puede renderizar `summary` y `detail`
directamente desde JSON.

### 17.6 Contrato operativo del sidecar

Schema minimo recomendado:

```json
{
  "status": "ok|not_applicable|error|validation_failed|skipped_unchanged",
  "date": "YYYY-MM-DD",
  "payload_hash": "sha256",
  "provider": "string",
  "model": "string",
  "prompt_version": "daily_brief_v1",
  "published": true,
  "summary": "texto",
  "detail": "texto",
  "tone": "green|amber|red|not_applicable",
  "source_mode": "reason_items|reason_text_fallback",
  "reason": null,
  "validation_errors": [],
  "model_output_preview": "",
  "created_at": "ISO-8601"
}
```

Reglas:

- `status=ok` es el unico caso publicable;
- `published=false` en cualquier error, validacion fallida o `gate_NO`;
- `status=skipped_unchanged` evita llamadas repetidas si el hash no cambia;
- `tone=not_applicable` solo para casos no publicables;
- `validation_errors` debe registrar el motivo exacto del rechazo;
- `model_output_preview` guarda una muestra acotada de la salida textual del
  modelo cuando falla el parseo o la llamada, para depurar respuestas vacias,
  prosa no JSON o modos de razonamiento que no publican en `message.content`.

### 17.7 Reglas de ejecucion

Reglas duras del MVP:

- si `HRV_AI_ENABLED=0`, no hacer nada;
- si `HRV_AI_DAILY_ENABLED=0`, no hacer nada;
- si `gate_final=NO`, no llamar al LLM y escribir `not_applicable`;
- si existe sidecar historico del dia con igual `payload_hash` y `status=ok`,
  devolver `skipped_unchanged`;
- si existe sidecar historico con el mismo `payload_hash` pero `status=error`
  o `validation_failed`, el MVP reintenta en el siguiente sync; esto es
  deliberado para no congelar un fallo transitorio del proveedor o del prompt.
  No hay backoff en fase 1;
- timeout corto;
- cualquier excepcion termina en sidecar + log, nunca en fallo del sync.

### 17.8 Validaciones minimas antes de publicar

Validaciones requeridas:

1. parseo JSON correcto;
2. presencia de `date`, `summary`, `detail`, `tone`, `source_mode`;
3. `date` igual a la del payload;
4. `tone` compatible con `gate_final`;
5. `source_mode` coherente con si hay o no `reason_items`;
6. `summary` y `detail` no vacios;
7. total de palabras de `summary + detail` no superior a
   `expected_output.max_words * 1.2`.

Si alguna falla:

- escribir sidecar `validation_failed`;
- registrar `validation_errors`;
- no publicar el brief IA;
- mantener visible el `reason_text` determinista.

### 17.9 Variables de entorno minimas

```text
HRV_AI_ENABLED=0
HRV_AI_DAILY_ENABLED=0
HRV_AI_PROVIDER=<provider>
HRV_AI_MODEL=<provider_model_id>
HRV_AI_API_KEY=<secret>
HRV_AI_BASE_URL=<openai_compatible_base_url>
HRV_AI_TIMEOUT_SEC=12
HRV_AI_TEMPERATURE=0.2
HRV_AI_TOP_P=
HRV_AI_THINKING=
HRV_AI_MAX_TOKENS=400
HRV_AI_LANGUAGE=es
HRV_AI_PROMPT_VERSION=daily_brief_v1
```

Nota:

- `HRV_AI_MODEL` queda configurable aunque el candidato inicial sea la familia
  `K2`; el valor exacto debe ser el identificador real exigido por el
  proveedor activo;
- `HRV_AI_BASE_URL` permite apuntar a un endpoint compatible con
  `chat/completions` sin hardcodear proveedor en la app;
- `HRV_AI_TEMPERATURE`, `HRV_AI_TOP_P`, `HRV_AI_THINKING` y
  `HRV_AI_MAX_TOKENS` gobiernan la generacion del proveedor activo; para
  Kimi `k2.6` via Moonshot se ha validado `HRV_AI_THINKING=disabled`,
  `HRV_AI_TEMPERATURE=0.6`, `HRV_AI_TOP_P=0.95` y
  `HRV_AI_MAX_TOKENS=400`;
- no hace falta ningun flag SSM en fase 1.

### 17.10 Comportamiento de UI

MVP recomendado:

- la UI sigue calculando y mostrando las metricas HRV actuales;
- si existe `ENDURANCE_HRV_ai_daily_brief_latest.json` con `status=ok` y fecha
  igual al ultimo dia de `FINAL`, la UI muestra un bloque sobrio `Brief IA`
  dentro de `Lectura HRV de hoy`;
- la UI muestra `reason_text` en un bloque separado dentro de esa misma tarjeta;
- no se anade una tarjeta aparte de historico, comparativa ni lista de briefs
  recientes en fase 1;
- si el brief IA no existe, falla o no publica, simplemente no se muestra el
  bloque `Brief IA`; `reason_text` sigue visible como fallback determinista.

Esto mantiene:

- compatibilidad total con el flujo actual;
- fallback inmediato;
- riesgo de regresion muy bajo.

### 17.11 Revision semanal como parte del diseno

La revision semanal deja de ser opcional y pasa a formar parte del proceso:

- conservar historico por fecha;
- revisar una vez por semana los briefs de los ultimos 7 dias;
- marcar manualmente:
  - mejores que `reason_text`
  - equivalentes
  - peores
  - patrones de fallo repetidos

Solo si aparece un patron repetido se ajusta:

- prompt;
- payload;
- validaciones.

Esto es preferible a seguir afinando en abstracto antes de ver uso real.

### 17.12 Orden de implementacion

1. Crear `hrv_app/ai/config.py`
2. Crear `hrv_app/ai/daily_brief.py`
3. Hook en `hrv_app/hrv_sync_flow.py`
4. Escribir `latest` + historico
5. Tests minimos de payload, `gate_NO`, skip por hash, timeout y
   validacion tone/gate
6. Mostrar `Brief IA` y `reason_text` dentro de `Lectura HRV de hoy`,
   sin tarjeta independiente de historico, y solo publicar `Brief IA`
   si `status=ok`

Veredicto:

- la propuesta ya no necesita mas investigacion previa para arrancar;
- necesita una implementacion pequena, reversible y auditable.
