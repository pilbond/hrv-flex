# AGENTS.md - Endurance Analysis Module

## 1. Alcance
Este modulo cubre:

- analisis de sesiones individuales y comparativas,
- interpretacion integrada de `TCX`, `FIT` y `RR.CSV`,
- produccion de informes reproducibles,
- notas de calidad y artefactos derivados locales del modulo de analisis.

No cubre:

- runtime, OAuth, despliegue, endpoints,
- logica HRV global fuera del analisis de sesiones,
- modificacion de outputs canonicos globales salvo instruccion explicita.

## 2. Carga obligatoria del modulo
Para cualquier tarea analitica del modulo, cargar y respetar este orden:

1. `../AGENTS.md`
2. `AGENTS.md`
3. `ENDURANCE_AGENT_DOMAIN.md`
4. `SESSION_ANALYSIS_METHOD.md`
5. documentos HRV canonicos en `../docs/contracts/` solo cuando aplique integracion HRV normativa:
   - `ENDURANCE_HRV_Spec_Tecnica.md`
   - `ENDURANCE_HRV_Estructura.md`
   - `ENDURANCE_HRV_Diccionario.md`
   - `ENDURANCE_HRV_Sessions_Schema.md`

Reglas:

- si falta `ENDURANCE_AGENT_DOMAIN.md`, el analisis queda sin baseline interpretativo,
- si falta `SESSION_ANALYSIS_METHOD.md`, el analisis pierde su procedimiento operativo,
- si alguno falta, debe declararse la limitacion.

## 3. Precedencia en caso de conflicto
Manda:

- infraestructura y operacion global -> `../AGENTS.md`
- dominio, tono, baseline y semantica de confianza -> `ENDURANCE_AGENT_DOMAIN.md`
- metodo operativo y definiciones del analisis -> `SESSION_ANALYSIS_METHOD.md`
- HRV normativa del proyecto -> documentos canonicos `ENDURANCE_HRV_*` en `../docs/contracts/`, con precedencia:
  1. `ENDURANCE_HRV_Spec_Tecnica.md`
  2. `ENDURANCE_HRV_Estructura.md`
  3. `ENDURANCE_HRV_Diccionario.md`
  4. `ENDURANCE_HRV_Sessions_Schema.md`
  5. QA STD canonicos si procede

Este archivo manda solo sobre:

- alcance del modulo,
- orden de carga,
- reglas de adopcion y outputs reproducibles del modulo.

Reglas criticas:

- los outputs canonicos del proyecto pueden informar contexto, pero no sustituyen a la documentacion normativa,
- ningun CSV de estado u output derivado debe entrar en la jerarquia de precedencia documental.

## 4. Objetivo del modulo
Todo analisis debe responder, de forma trazable al dato, a estas seis preguntas:

1. que estimulo fue realmente
2. donde estuvo la carga
3. si la continuidad del estimulo fue util o fragmentada
4. si la capa RR confirma o matiza la FC
5. si procede, cual fue el balance cardiometabolico vs mecanico
6. como debe releerse la sesion mas adelante

## 5. Inputs validos
### MUST aceptar
- `TCX`
- `FIT`
- `RR.CSV` con cabecera `duration,offline`
- contexto explicito del usuario

### MAY aceptar
- outputs operativos del proyecto,
- tablas derivadas reproducibles del modulo,
- outputs HRV canonicos del proyecto cuando aporten contexto adicional,
- `sessions.csv`, `sessions_day.csv` y `ENDURANCE_HRV_sessions_metadata.json` del pipeline de sesiones cuando existan.

### MUST NOT
- tratar contexto verbal como sustituto de un dato medido, salvo para describir carga externa indoor cuando el archivo no la represente bien.

## 6. Reglas de fuente
### MUST
- en exterior, `TCX` y `FIT` pueden complementarse; usar la fuente mas fiel para cada campo,
- en cinta, si el archivo indoor representa mal velocidad, distancia o pendiente, usar el protocolo declarado por el usuario como fuente de verdad de la carga externa,
- si dos fuentes discrepan de forma material, explicitar cual se prioriza y por que.

### SHOULD
- priorizar `FIT` frente a `TCX` para eventos, resumen o continuidad cuando el `FIT` sea mas rico,
- priorizar `TCX` si es la unica fuente con serie temporal usable,
- reducir el peso interpretativo de `moving/pause` cuando la fuente indoor cuantice mal la velocidad,
- si existe fila canonica en `sessions.csv`, priorizar para esa sesion:
  - `vt1_used`
  - `vt2_used`
  - `zones_source`
  - `moving_min`
  - `work_*`

## 7. Reglas de validez RR
La definicion operativa de RR valido y los parametros de limpieza viven en `SESSION_ANALYSIS_METHOD.md`.

### Sesiones sin RR exportable
Desde v4 (2026-03-23): si Polar no exporta RR para una sesión (fallo de grabación, dispositivo sin sensor, etc.):
- `prepare_bundle()` registra el error en `manifest["rr_error"]` sin crashear,
- `run_analysis()` genera un `summary.json` parcial con `rr_unavailable: true`,
- el report incluye `session_cost_model` (cardio/mecánico desde `sessions.csv`) y contexto,
- omite automáticamente secciones RR del `technical_report.md`,
- el analista IA recibe un `payload` con indicador `rr_unavailable` y ajusta el análisis.

Esto es una **degradación del análisis, no un error operativo**. La sesión genera report útil para coste/carga pero sin las métricas de variabilidad.

### Reglas de modulo

- si no hay RR valido o el archivo no cumple los criterios operativos, marcar en payload `rr_unavailable: true`,
- motivos tipicos: no hay RR, archivo roto, muy pocas filas, sesion solo OHR sin serie RR usable.

### MUST NOT
- calcular `DFA-alpha1` sin RR valido,
- calcular `RMSSD` en ejercicio sin RR valido,
- inferir `HR@0.75` con base debil,
- presentar una utilidad local como si fuera el pipeline canonico del proyecto,
- crashear si falta RR; en cambio, generar report degradado con cost model intacto.

## 8. Outputs obligatorios del modulo
### MUST generar, cuando proceda
- informe de sesion reproducible en Markdown,
- nota resumen de calidad,
- artefactos derivados reproducibles si se han calculado metricas locales.

Nombres recomendados:

- `session_report_YYYY-MM-DD_HH-mm-ss.md`
- `derived_metrics_*_windows.csv`
- `derived_metrics_*_blocks.csv`
- `derived_metrics_*_summary.json`

Reglas:

- no modificar outputs canonicos globales salvo instruccion explicita,
- no tratar artefactos locales como outputs canonicos,
- si se crea una metrica derivada nueva, documentarla antes de reutilizarla.

## 8.1 Regla de informe conversacional
Cuando exista una carpeta de sesion en `analysis/reports/<slug>/`, la orden corta:

- `Redacta el informe final rico de la sesión <slug>`

debe interpretarse con este contrato por defecto, sin que el usuario tenga que repetir rutas:

### MUST - fuentes y artefactos
- usar `analysis/reports/<slug>/artifacts/session_payload.json` como fuente compacta principal,
- usar `analysis/reports/<slug>/artifacts/summary.json` como apoyo tecnico,
- abrir `analysis/reports/<slug>/artifacts/blocks.csv` solo si hace falta granularidad adicional,
- cargar y respetar `ENDURANCE_AGENT_DOMAIN.md` y `SESSION_ANALYSIS_METHOD.md`,
- usar `analysis/delete/session_report_*.md` como referencia de densidad y estructura cuando existan,
- guardar el resultado final en `analysis/reports/<slug>/report.md`,
- preservar `analysis/reports/<slug>/technical_report.md` como artefacto tecnico separado.

### MUST - estructura del informe
- seguir el orden de secciones definido en `SESSION_ANALYSIS_METHOD.md` seccion 15,
- en **Fuentes**, jerarquizar por funcion analitica (no como inventario de archivos),
- en **Datos**, estructurar en sub-bloques: Perfil de sesion, Intensidad, Estructura util, Contexto subjetivo,
- en **Respuesta interna**, hacer explicita la evidencia negativa relevante cuando confirme un patron controlado,
- en **Capa RR**, al presentar `cardio_score` y `mecanico_score`, incluir los anclajes observacionales que los generan,
- en **Encaje en el bloque**, incluir mini-tabla cuantificada con 3-4 sesiones relevantes,
- en **Confianza**, desglosa por capas si tienen calidad distinta (Clasificacion global / Capa RR fina / Resultado neto),
- si existe tension entre `gate_badge` favorable y `reason_text` con cautela material, resolverla de forma explicita en el cuerpo del informe.

### SHOULD
- priorizar el payload sobre la exploracion manual de CSV completos,
- evitar repetir al usuario que adjunte archivos si la carpeta de sesion ya existe,
- tratar `report.md` como producto final humano y `technical_report.md` como soporte tecnico,
- usar el FIT cuando este disponible como fuente preferente de continuidad y FC temporal; declararlo en Calidad del dato,
- si `duration_consistency` esta disponible en `summary.json`, incluirla como dato de trazabilidad en Calidad del dato.

### MUST NOT
- sobrescribir `technical_report.md` con el informe rico,
- usar `report.md` para un resumen tecnico corto,
- exigir al usuario un prompt largo cuando el `slug` de sesion ya identifica el caso,
- usar etiqueta plana de confianza si las capas tienen calidad claramente diferente.

## 9. Comparacion con informes externos
Si el usuario aporta un informe externo:

### MUST
- comparar punto por punto,
- separar coincidencias, valor anadido del adjunto y donde este analisis es mas prudente o mas util,
- identificar el principal riesgo de malinterpretacion futura.

### MUST NOT
- convertir pequenas diferencias marginales en la discusion central.

## 10. Regla de trabajo
### MUST
- distinguir dato medido de inferencia,
- no presentar estimaciones como medidas,
- cuantificar siempre que sea posible,
- explicitar limitaciones del dato,
- separar calidad del dato y conclusion,
- no inventar causalidad,
- preferir artefactos reproducibles frente a analisis opacos.

## 11. Regla final
El metodo concreto de analisis lo define `SESSION_ANALYSIS_METHOD.md`.
El tono, baseline, confianza e interpretacion los define `ENDURANCE_AGENT_DOMAIN.md`.
Este archivo no debe duplicar su contenido salvo para fijar alcance, precedencia y outputs del modulo.
