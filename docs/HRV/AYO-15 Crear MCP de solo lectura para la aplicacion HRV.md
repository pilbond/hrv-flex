# AYO-15 Crear MCP de solo lectura para la aplicacion HRV

## Estado

Analisis y propuesta creados el 2026-06-12.

## Resumen ejecutivo

Crear un MCP propio para esta aplicacion aporta valor porque el proyecto ya no
es solo un descargador de Polar: contiene una capa de normalizacion,
trazabilidad, QA, contexto de carga y analisis que combina varias fuentes.

Un MCP de Polar expone datos del proveedor. Un MCP de esta aplicacion puede
exponer el producto propio:

- estado HRV diario;
- explicacion estructurada del gate;
- calidad y procedencia del dato;
- contexto de carga y recuperacion;
- sesiones normalizadas;
- contexto semanal;
- payloads tecnicos de `analysis/`;
- cobertura operativa y frescura de artefactos.

La recomendacion es construir una primera version local, `stdio`, de solo
lectura y basada exclusivamente en artefactos ya generados. No debe ejecutar
sincronizaciones, modificar outputs canonicos ni acceder a APIs externas.

## Problema que resuelve

Hoy un agente que quiera analizar el estado del atleta debe conocer:

- nombres y rutas de varios CSV y JSON;
- precedencia entre `CORE`, `FINAL`, `DASHBOARD`, sleep y sesiones;
- semantica de columnas;
- diferencia entre dato canonico y contexto local de `analysis/`;
- reglas de causalidad temporal;
- sidecars de calidad y manifests;
- que archivos no son fuente primaria;
- como degradar la respuesta cuando falta RR, sleep o streams.

La informacion existe, pero el consumidor debe reconstruir el contrato en cada
consulta. Eso aumenta:

- carga de contexto;
- lecturas innecesarias de ficheros completos;
- riesgo de usar columnas incorrectas;
- riesgo de mezclar futuro con pasado;
- riesgo de presentar proxies como mediciones;
- respuestas inconsistentes entre agentes;
- exposicion accidental de datos sensibles.

El MCP debe convertir ese conocimiento disperso en consultas tipadas,
acotadas, reproducibles y con procedencia.

## Por que MCP y no solo leer CSV

### Lectura directa de CSV

Es util para depuracion humana y procesamiento batch, pero obliga al agente a
descubrir esquemas, joins, fechas, nulls y jerarquia de fuentes. Tampoco limita
automaticamente el volumen devuelto.

### REST adicional en Flask

Una API REST seria adecuada para una UI o integracion tradicional. Sin
embargo, exige que cada cliente de IA conozca previamente endpoints y
contratos. Ampliar `/api/status` tampoco es apropiado: ese endpoint es
operativo y ya tiene una superficie sensible que debe reducirse, no crecer
hacia una API analitica general.

### MCP

MCP aporta:

- descubrimiento automatico de herramientas, recursos y esquemas;
- contratos de entrada y salida legibles por agentes;
- compatibilidad con distintos hosts MCP;
- separacion entre recursos de contexto y acciones;
- respuestas disenadas para contexto LLM;
- posibilidad de indicar herramientas de solo lectura;
- composicion futura con otros MCP sin acoplar el pipeline.

MCP no sustituye los contratos internos. Debe ser un adaptador sobre una capa
de consulta Python reutilizable.

## Donde aporta ventajas y por que

### 1. Estado diario

Herramienta propuesta:

```text
hrv_get_daily_status(date)
```

Ventaja:

- evita leer filas de varios CSV;
- devuelve una vista unica del estado;
- separa medicion, contexto, inferencia y accion;
- incluye calidad, frescura y fuentes.

Datos candidatos:

- gate y badge;
- HR, RMSSD, lnRMSSD y baseline;
- sleep previo;
- contexto de carga D-1;
- cautelas tipadas de `reason_items`;
- accion y `reason_text` como render secundario;
- manifest efectivo de la corrida.

Por que importa:

La pregunta mas frecuente no es "dame la fila de FINAL", sino "cual era el
estado del atleta en esta fecha y con que confianza". El MCP puede responder
eso sin obligar al agente a reinterpretar el gate.

### 2. Explicacion del gate

Herramienta propuesta:

```text
hrv_explain_gate(date)
```

Ventaja:

- usa `ENDURANCE_HRV_master_FINAL_reason_items.json` como fuente estructurada;
- evita depender solo de `reason_text`;
- distingue restriccion operativa, cautela, modificador de precision y
  contexto;
- expone valores y umbrales cuando existan.

Por que importa:

La explicabilidad es una parte propia del producto. Sin esta herramienta, cada
agente puede parafrasear de manera distinta o mezclar señales que el pipeline
mantiene separadas.

### 3. Analisis de sesiones

Herramientas propuestas:

```text
hrv_list_sessions(from, to, sport, intensity)
hrv_get_session_context(session_id)
hrv_compare_sessions(session_ids)
```

Ventaja:

- devuelve `session_payload.json` como fuente compacta principal;
- usa `summary.json` para soporte tecnico;
- incluye `training_audit`;
- expone terreno, durabilidad, eficiencia, contexto subjetivo y RR solo
  cuando son aplicables;
- oculta streams y RR crudos por defecto.

Por que importa:

`analysis/` ya ha hecho el trabajo costoso de integrar fuentes y gobernar
confianza. El MCP permite reutilizar ese producto sin volver a recorrer FIT,
CSV, sidecars y reports.

### 4. Contexto semanal

Herramientas propuestas:

```text
hrv_get_weekly_context(date)
hrv_get_training_distribution(from, to, sport)
```

Ventaja:

- combina `sessions_day`, distribucion semanal, weekly coach, FINAL,
  DASHBOARD y sleep;
- conserva causalidad temporal;
- expone calidad y limites de `training_audit`;
- evita que el agente agregue porcentajes de zona incorrectamente.

Por que importa:

El resumen semanal tiene reglas de ponderacion y confianza que no deben
reimplementarse en cada cliente.

### 5. Calidad, cobertura y trazabilidad

Herramientas propuestas:

```text
hrv_get_data_quality(date_or_range)
hrv_get_artifact_manifest(stage)
hrv_find_missing_rr(from, to)
hrv_get_data_inventory()
```

Ventaja:

- diferencia ausencia real, dato no aplicable y error;
- muestra cobertura de RR, sleep, sesiones y streams;
- usa manifests y hashes para identificar la corrida;
- permite saber si una conclusion es reproducible.

Por que importa:

Para este proyecto, una respuesta correcta incluye saber que datos faltan. Un
MCP que solo entregue metricas sin QA haria al agente mas convincente, pero no
mas fiable.

### 6. Diagnostico operativo

Herramienta propuesta:

```text
hrv_get_runtime_status()
```

Ventaja:

- ofrece una vista saneada de jobs, ultima actualizacion y artefactos;
- evita exponer rutas completas, secretos o diagnosticos de credenciales;
- permite al agente distinguir dato antiguo de fallo analitico.

Por que importa:

Una lectura deportiva puede ser incorrecta simplemente porque el sync no se
ha ejecutado. El estado operativo debe ser visible, pero separado de las
metricas.

### 7. Interoperabilidad entre agentes

Ventaja:

- Codex, ChatGPT, Claude u otros hosts pueden consumir el mismo contrato;
- se reduce la dependencia de prompts especificos por cliente;
- la semantica permanece en la aplicacion;
- las mejoras del pipeline quedan disponibles para todos los consumidores.

Por que importa:

El valor de la aplicacion no debe quedar ligado al agente que conozca mejor la
estructura del repositorio.

### 8. Privacidad por diseno

Ventaja:

- se puede devolver solo la ventana y campos necesarios;
- RR, streams, notas libres, GPS y rutas quedan ocultos por defecto;
- no es necesario conceder acceso general al filesystem;
- las herramientas pueden redactar identificadores y rutas.

Por que importa:

Un MCP especializado puede ser mas seguro que permitir a un agente leer todo
el workspace, siempre que mantenga una allowlist estricta de artefactos.

### 9. Composicion futura con Polar v4

Ventaja:

- el MCP de la app puede responder con datos canonicos locales;
- el MCP Polar puede aportar datos externos nuevos o bajo demanda;
- el agente puede comparar ambos sin convertir Polar MCP en dependencia del
  sync;
- la procedencia permite distinguir `polar_raw`, `app_canonical` y
  `analysis_local`.

Por que importa:

Evita confundir dos capas distintas:

```text
Polar MCP -> acceso al proveedor
HRV App MCP -> estado normalizado, auditado e interpretado por la app
```

## Modelo de respuesta recomendado

Las respuestas analiticas deben seguir una forma comun:

```json
{
  "schema_version": "1.0",
  "as_of": "2026-06-12",
  "status": "complete",
  "measured": {},
  "derived": {},
  "context": {},
  "quality": {
    "state": "high",
    "warnings": []
  },
  "sources": [],
  "provenance": {
    "generated_at": null,
    "artifact_hashes": {},
    "contract_versions": {}
  }
}
```

Reglas:

- `measured`: observaciones directas;
- `derived`: calculos deterministas;
- `context`: carga, sleep, sesion o semana;
- `quality`: cobertura, limitaciones y degradacion;
- `sources`: artefactos y capas usadas;
- `provenance`: manifests, hashes y versiones;
- `status`: `complete`, `partial`, `not_found`, `not_applicable` o `stale`.

No devolver `NaN`. Usar `null` y explicar su razon cuando sea relevante.

## Fuentes y precedencia

Orden recomendado:

1. contratos vigentes en `docs/contracts/`;
2. manifests de corrida;
3. sidecars JSON estructurados;
4. outputs canonicos CSV;
5. payloads reproducibles de `analysis/`;
6. informes narrativos solo como salida, no como fuente primaria.

Fuentes principales:

- `ENDURANCE_HRV_master_CORE.csv`;
- `ENDURANCE_HRV_master_BETA_AUDIT.csv`;
- `ENDURANCE_HRV_master_FINAL.csv`;
- `ENDURANCE_HRV_master_DASHBOARD.csv`;
- `ENDURANCE_HRV_master_FINAL_reason_items.json`;
- `ENDURANCE_HRV_sleep.csv`;
- `ENDURANCE_HRV_sessions.csv`;
- `ENDURANCE_HRV_sessions_day.csv`;
- `ENDURANCE_HRV_intensity_distribution_weekly.csv`;
- `ENDURANCE_HRV_weekly_coach.json`;
- `ENDURANCE_HRV_sessions_metadata.json`;
- manifests `CORE` y `FINAL`;
- `analysis/**/artifacts/session_payload.json`;
- `analysis/**/artifacts/summary.json`;
- `weekly_prep_manifest.json` cuando su contrato este estabilizado.

## Arquitectura propuesta

```text
Host MCP
   |
   v
servidor MCP local stdio
   |
   v
HRVQueryService
   |
   +-- ArtifactCatalog
   +-- DailyStatusReader
   +-- SessionContextReader
   +-- WeeklyContextReader
   +-- QualityAndProvenance
   |
   v
CSV / JSON / manifests / analysis artifacts
```

Modulos candidatos:

```text
hrv_app/query/
  artifact_catalog.py
  daily_status.py
  sessions.py
  weekly.py
  quality.py
  schemas.py

hrv_app/mcp/
  server.py
  tools.py
  resources.py
```

El servidor MCP no debe importar `web_ui.py`, builders ni entrypoints con
efectos laterales. La logica de consulta debe ser Python reutilizable desde
tests, CLI, Flask o MCP.

## Herramientas v1

Catalogo minimo:

```text
hrv_get_capabilities()
hrv_get_data_inventory()
hrv_get_daily_status(date)
hrv_explain_gate(date)
hrv_get_date_range(from, to, fields, limit)
hrv_list_sessions(from, to, sport, limit)
hrv_get_session_context(session_id)
hrv_get_weekly_context(date)
hrv_get_data_quality(from, to)
hrv_get_artifact_manifest(stage)
hrv_get_runtime_status()
```

Todas deben:

- validar fechas y limites;
- tener maximo de filas y bytes;
- ordenar resultados de forma determinista;
- informar truncamiento;
- incluir `as_of` y frescura;
- no devolver rutas absolutas;
- no devolver secretos;
- ser de solo lectura.

## Recursos MCP

Recursos de bajo volumen:

```text
hrv://capabilities
hrv://contracts/data-dictionary
hrv://contracts/source-precedence
hrv://artifacts/catalog
hrv://methods/session-analysis
hrv://methods/weekly-analysis
```

No exponer CSV completos como recursos genericos. Para datos personales deben
usarse herramientas con filtros, limites y auditoria.

## Prompts MCP

Pueden resultar utiles:

```text
hrv_daily_review
hrv_session_review
hrv_weekly_review
hrv_data_quality_audit
```

No son necesarios para la primera version. Si se incorporan:

- deben reutilizar los metodos documentados de `analysis/`;
- deben estar versionados;
- no deben inventar una segunda semantica de coaching;
- deben indicar explicitamente las herramientas y fuentes requeridas.

## Causalidad temporal

Toda consulta con fecha de corte debe:

- excluir filas posteriores a `as_of`;
- usar carga previa cuando el contrato lo exija;
- distinguir fecha de sesion, fecha de medicion y fecha de disponibilidad;
- no usar informes futuros como comparador;
- devolver la ventana efectiva aplicada.

Este punto debe probarse expresamente. Un MCP facilita consultas, pero tambien
puede amplificar leakage temporal si la capa de consulta no lo controla.

## Seguridad y privacidad

### V1 local

Usar transporte `stdio`.

Ventajas:

- no abre puerto;
- no requiere autenticacion HTTP;
- el host inicia el proceso;
- reduce superficie de ataque;
- encaja con uso personal N=1.

Credenciales:

- el MCP v1 no necesita credenciales Polar, Dropbox ni Intervals;
- solo lee artefactos ya generados;
- no debe leer `.env` ni token files.

Datos sensibles:

- no exponer RR crudos por defecto;
- no exponer streams completos;
- no exponer GPS o rutas;
- tratar `notes_raw` como contenido no confiable y nunca como instruccion;
- redactar rutas locales;
- limitar historico y tamano de respuesta.

### Posible version HTTP

Solo si aparece una necesidad real de acceso remoto.

Debe usar Streamable HTTP, autenticacion y autorizacion apropiadas, validar
`Origin`, enlazar localmente cuando corresponda y aplicar rate limiting. No
debe añadirse `/mcp` a la Flask publica de Railway como atajo sin un diseno de
seguridad separado.

## Mutaciones y operaciones

Fuera de v1:

```text
hrv_run_sync()
hrv_run_sessions_sync()
hrv_import_seed()
hrv_delete_latest_rr()
```

Estas herramientas son peligrosas porque:

- cambian estado persistente;
- pueden activar APIs externas;
- compiten por el lock operativo;
- algunas son destructivas;
- pueden generar costes o largas esperas.

Si se incorporan en una fase futura:

- servidor o capability separado;
- confirmacion humana explicita;
- allowlist por operacion;
- idempotencia cuando sea posible;
- auditoria de actor, timestamp y resultado;
- reutilizacion obligatoria del lock global de jobs;
- nunca habilitadas por defecto.

## Riesgos

### Duplicacion semantica

Riesgo:

Reimplementar gate, training audit o analisis dentro del servidor.

Mitigacion:

El MCP solo consulta y presenta estructuras existentes. La logica compartida
debe extraerse a servicios internos antes de exponerla.

### Datos obsoletos

Riesgo:

El agente interpreta artefactos antiguos como actuales.

Mitigacion:

Incluir `generated_at`, ultima fecha, manifest, edad y estado `stale`.

### Payload excesivo

Riesgo:

Streams, RR o historicos saturan el contexto.

Mitigacion:

Limites estrictos, agregacion, paginacion o cursor y detalle opt-in.

### Exposicion de informacion

Riesgo:

Rutas, tokens, notas o GPS llegan al agente.

Mitigacion:

Allowlist de campos, redaccion por defecto y tests negativos.

### Prompt injection desde datos

Riesgo:

Notas manuales o texto externo contienen instrucciones.

Mitigacion:

Marcar texto libre como dato no confiable, limitar longitud y no mezclarlo con
descripciones de herramientas o prompts del servidor.

### Acoplamiento al layout

Riesgo:

Cambios de rutas rompen herramientas.

Mitigacion:

`ArtifactCatalog` central, variables de entorno existentes y manifests.

### Dependencia nueva

Riesgo:

El SDK MCP aumenta el runtime productivo.

Mitigacion:

Dependencias opcionales en un fichero separado y entrypoint local. No
instalarlo en Railway durante v1.

## Relacion con otras tareas

- `IU-13` mejora procedencia de CORE, FINAL y DASHBOARD y aumenta el valor del
  MCP, pero no es dependencia dura para iniciar el diseno.
- `SYA-18` estabilizara el manifest semanal local; hasta entonces la
  herramienta semanal debe degradar con advertencia.
- `AYO-13` aporta Polar v4 al pipeline, pero el MCP de la app puede construirse
  con los artefactos actuales.
- `AYO-14` trata acceso MCP directo a Polar. Es complementario, no
  intercambiable con esta tarea.
- `IU-04` obliga a no reutilizar sin mas el payload completo de `/api/status`.

## Plan por fases

### Fase 0. Contrato

- fijar usuarios y consultas prioritarias;
- definir esquemas JSON de salida;
- clasificar campos sensibles;
- definir frescura, causalidad y limites;
- mapear herramientas a fuentes y contratos.

### Fase 1. Query service

- crear `ArtifactCatalog`;
- extraer lectores sin efectos laterales;
- reutilizar helpers de `reason_items` y `training_audit`;
- implementar modelos de respuesta;
- probar consultas sin MCP.

### Fase 2. MCP local read-only

- añadir SDK MCP oficial como dependencia opcional;
- implementar `stdio`;
- exponer herramientas v1;
- exponer recursos de contratos y capacidades;
- validar con MCP Inspector y al menos un host real.

### Fase 3. QA y seguridad

- tests de truncamiento y fechas;
- tests de secretos y rutas;
- tests de datos ausentes, parciales y stale;
- tests de causalidad temporal;
- tests de texto no confiable;
- benchmarks de latencia y memoria.

### Fase 4. Integracion con analysis

- consumir `session_payload.json` y `summary.json`;
- incorporar weekly manifest cuando este estable;
- evitar leer informes narrativos como evidencia;
- validar consistencia frente a los comandos locales actuales.

### Fase 5. Evaluacion de extensiones

- prompts versionados;
- transporte HTTP privado;
- composicion con MCP Polar;
- mutaciones en servidor separado;
- publicacion o instalacion como plugin, solo si aporta valor operativo.

## Criterios de aceptacion

1. El MCP funciona localmente por `stdio`.
2. Todas las herramientas v1 son de solo lectura.
3. No requiere credenciales de proveedores.
4. No importa entrypoints con efectos laterales.
5. Las respuestas usan esquemas versionados.
6. Cada respuesta declara fuentes, frescura y calidad.
7. Las consultas por fecha respetan causalidad temporal.
8. No devuelve tokens, rutas absolutas, GPS, RR o streams crudos por defecto.
9. La ausencia de un artefacto produce estado parcial, no una conclusion
   inventada.
10. Los payloads tienen limites y declaran truncamiento.
11. El MCP no modifica outputs canonicos ni contratos.
12. Su caida no afecta al sync, UI o Railway.
13. La suite incluye tests de privacidad y prompt injection desde texto libre.
14. Existe documentacion de instalacion, version y desactivacion.

## Indicadores de exito

- menos lecturas manuales de CSV para responder consultas habituales;
- reduccion del volumen medio enviado al agente;
- misma respuesta estructural entre distintos hosts;
- cero secretos o rutas sensibles en fixtures y respuestas;
- consultas diarias y de sesion reproducibles desde manifests;
- degradacion explicita cuando faltan datos;
- tiempo de respuesta local compatible con uso interactivo.

## Decision recomendada

Crear el MCP tiene valor alto si se mantiene como interfaz de consulta sobre
el producto ya calculado.

No tiene sentido si se limita a envolver archivos con herramientas
`read_file`, porque eso no aporta semantica ni seguridad. Tampoco debe
convertirse en una segunda implementacion del pipeline.

La primera entrega debe ser pequena:

- local;
- read-only;
- `stdio`;
- artefactos existentes;
- cinco a once herramientas de alto valor;
- respuestas compactas, tipadas y auditables.

## Referencias

- Arquitectura MCP:
  https://modelcontextprotocol.io/docs/learn/architecture
- Herramientas MCP:
  https://modelcontextprotocol.io/specification/2025-06-18/server/tools
- Recursos MCP:
  https://modelcontextprotocol.io/specification/2025-06-18/server/resources
- Transportes MCP:
  https://modelcontextprotocol.io/specification/2025-11-25/basic/transports
- Seguridad MCP:
  https://modelcontextprotocol.io/docs/tutorials/security/security_best_practices
