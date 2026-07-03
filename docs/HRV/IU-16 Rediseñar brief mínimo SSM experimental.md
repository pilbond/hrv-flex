
> Fecha: 2026-06-29
> Estado: propuesta
> Dependencia Kanvas: `IU-15`
> Objetivo: definir un brief SSM mínimo, usable y validable sin promocionar el
> mensaje SSM actual como salida estable.

## 1. Contexto

La revisión externa del SSM dejó una conclusión útil y una conclusión débil:

- útil: el mensaje SSM actual tiene problemas reales de jerarquía, duplicación
  y semántica inflada;
- débil: no hay evidencia suficiente para reactivar el SSM completo como texto
  diario principal.

Desde entonces cambió una pieza relevante: el sueño ya entra en el SSM tras la
actualización de `ENDURANCE_HRV_sleep.csv`, por lo que la crítica de "texto
muerto permanente de sueño" ya no aplica igual al estado actual del pipeline.

Eso no cambia la decisión de producto:

- el SSM sigue siendo mejor candidato a capa `shadow` o mensaje de excepción;
- no a narrativa diaria larga y primaria;
- y la validación pendiente sigue siendo prospectiva: utilidad real para la
  decisión, no solo plausibilidad técnica.

## 2. Decisión de trabajo

El siguiente paso no es reactivar el texto actual del SSM ni seguir ampliando
la discusión teórica.

El siguiente paso correcto es:

1. mantener `HRV_SSM_REASON_TEXT_ENABLED=0` por defecto;
2. definir una versión mínima experimental del brief SSM;
3. usarla solo como salida controlada para evaluación;
4. decidir con registro prospectivo si aporta algo por encima del gate.

## 3. Qué debe resolver el brief mínimo

El brief mínimo no intenta explicar todo el SSM. Solo debe responder una
pregunta:

> "¿Hay hoy alguna señal adicional del SSM que merezca matizar la lectura del
> gate?"

Si la respuesta es no, no debe emitirse nada.

Si la respuesta es sí, el brief debe:

- ser corto;
- no duplicar sueño ni confianza;
- no abrir con `zona alto/medio/bajo`;
- no presentar una causalidad fuerte no validada;
- y dejar claro que es un matiz experimental, no una capa de decisión.

## 4. Reglas del brief mínimo

### 4.1 Cuándo emitirlo

Emitirlo solo cuando al menos una de estas condiciones se cumpla:

- `|ssm_innovation| >= 0.12`
- el sueño nocturno aporte una señal clara (`sleep_input_quality != suppressed`
  y `|sleep_innovation| >= 0.12`)
- exista una matización relevante entre observación matinal, estado SSM y gate
  que merezca prudencia adicional

Si no se cumple ninguna, la salida correcta es silencio.

### 4.2 Qué no debe decir

- no abrir con la zona del histórico SSM;
- no duplicar la confianza en dos frases;
- no duplicar el sueño en dos frases;
- no usar "fatiga reciente te descuenta X%" como idea principal;
- no contradecir `gate_final`, `gate_badge`, `Action` ni `Action_detail`;
- no hablar como si gobernara la decisión del día.

### 4.3 Estructura

Máximo 3 frases:

1. observación principal del SSM;
2. matiz de sueño o de discrepancia;
3. caveat operativo.

## 5. Evaluación del cambio respecto al mensaje actual

### 5.1 Lo que mejora

- reduce longitud y densidad;
- elimina duplicaciones de confianza y sueño;
- evita abrir con una etiqueta de zona poco útil;
- centra el valor del SSM en la discrepancia o la cautela adicional;
- lo convierte en comentario secundario compatible con el gate.

### 5.2 Lo que no resuelve aún

- no demuestra por sí mismo utilidad operativa;
- no resuelve la validación prospectiva pendiente;
- no zanja si la innovación aporta valor estable o solo ocasional;
- no convierte el SSM en capa primaria de decisión.

## 6. Plantillas mínimas

Las plantillas de abajo están diseñadas como mensajes experimentales de UI o
brief local, no como contrato canónico del pipeline.

### 6.1 Día normal

Usar cuando el SSM no detecta desviación relevante y el sueño no añade señal
clara.

```text
El SSM ve hoy una lectura alineada con lo esperable para tu línea reciente.
No añade una cautela relevante por encima del gate de hoy.
SSM shadow: matiz experimental, no señal principal.
```

### 6.2 Día con prudencia

Usar cuando la observación matinal o el sueño añaden cautela, pero sin una
anomalía fuerte.

```text
El SSM sitúa tu estado hoy en torno a tu rango reciente, pero la lectura de la
mañana quedó algo por debajo de lo esperable.
El sueño nocturno también añade prudencia, así que conviene leer el día con más
calma que la que sugeriría una señal aislada.
SSM shadow: matiz experimental; acompaña al gate, no lo sustituye.
```

### 6.3 Día con anomalía clara

Usar cuando hay sorpresa relevante o una discrepancia suficientemente marcada
como para justificar comentario específico.

```text
El SSM detecta hoy una desviación clara entre lo observado y lo que esperaba
para tu estado reciente.
La lectura conviene tratarla como una anomalía puntual que merece contexto
adicional antes de asumir que marca una tendencia nueva.
SSM shadow: lectura experimental; úsala solo como matiz del gate.
```

## 7. Recomendación de implementación

La primera iteración no debería tocar el modelo ni el contrato del SSM.

Debe limitarse a:

- construir un renderer alternativo breve;
- activarlo solo bajo flag o en entorno de prueba;
- revisar manualmente varios días reales;
- y usar el registro prospectivo ya preparado para decidir si se queda o se
  descarta.

### 7.1 Opción A implementada: renderer determinista mínimo

La primera entrega adoptada es la opción A:

- `hrv_app/ssm_brief.py` construye un brief SSM determinista y pequeño;
- no llama a IA;
- no escribe en `FINAL`, `DASHBOARD` ni contratos canónicos;
- decide `ok`, `silent`, `not_applicable` o `missing` desde campos ya
  calculados del sidecar SSM;
- publica texto solo si hay señal material por `ssm_innovation`,
  `sleep_innovation` usable o discrepancia suficiente frente al rolling;
- expone la salida en `/api/status` y en `view.hrv_today.ssm_text`;
- la UI lo muestra dentro de la tarjeta HRV actual como bloque `SSM shadow`.

La salida visible sigue siendo una capa secundaria. El texto debe conservar
siempre esta jerarquía:

1. el gate y la acción operativa mandan;
2. `reason_items` explican la decisión principal;
3. el SSM solo añade un matiz experimental si hay señal material;
4. si no hay señal material, el estado correcto es `silent`.

Esta implementación no cubre todavía la opción B. La IA queda reservada como
rewriter opcional sobre este brief determinista, no como generador primario.

## 8. Criterio de salida

La tarea IU-16 queda bien resuelta si produce:

1. una versión mínima del brief SSM claramente distinta del mensaje actual;
2. reglas explícitas de cuándo emitirla y cuándo callar;
3. una prueba corta sobre días reales;
4. y una decisión posterior basada en el registro prospectivo de 14 días.

Sin esa validación, la salida debe seguir en modo experimental.
