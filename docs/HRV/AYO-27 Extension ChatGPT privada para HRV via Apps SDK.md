# AYO-27 — Extension ChatGPT privada para HRV via Apps SDK

## Decision propuesta

Extender la aplicacion HRV a ChatGPT mediante una app privada basada en MCP y
Apps SDK. El conector se desplegara como servicio HTTPS separado y de solo
lectura, consumiendo la capa de consulta tipada definida por `AYO-15`.

No se expondran CSV, rutas locales, tokens, RR crudos, GPS, streams completos
ni notas libres sin filtrar. Tampoco se habilitaran sincronizaciones,
restauraciones, borrados ni ninguna mutacion en la primera version.

## Objetivo

Permitir consultas en ChatGPT sobre los datos vivos y ya normalizados del
atleta, por ejemplo:

- «¿Que ha cambiado en mi recuperacion esta semana?»
- «¿Tiene sentido hacer intensidad manana?»
- «Compara el coste cardiovascular de mis dos ultimas sesiones de subida.»

Las respuestas deben basarse en artefactos canonicos y sidecars reproducibles,
no en interpretaciones libres de CSV ni en llamadas directas a Polar,
Dropbox o Intervals.

## Arquitectura

```text
ChatGPT
  |
  | OAuth 2.0 Authorization Code + PKCE (scope hrv:read)
  v
MCP HRV remoto (HTTPS, Railway)
  |
  v
HRVQueryService (AYO-15)
  |
  +-- outputs canonicos de data/
  +-- manifests y sidecars de trazabilidad
  +-- artefactos reproducibles de analysis/
```

El servidor MCP no debe reutilizar ni ampliar directamente los endpoints
operativos de Flask (`/api/sync`, `/api/status`, etc.). Compartira lectores y
esquemas con la app, pero tendra autenticacion, limites y superficie publica
propias.

## Autenticacion y privacidad

ChatGPT debe poder descubrir el recurso protegido y completar OAuth contra un
proveedor de identidad de la propia aplicacion. El flujo debe soportar:

- Authorization Code con PKCE `S256`;
- metadatos de recurso protegido en `/.well-known/oauth-protected-resource`;
- metadatos del authorization server;
- validacion de audiencia, expiracion y scope `hrv:read` en cada llamada;
- `resource` enlazado al token; y
- redirect URI de ChatGPT permitida explicitamente.

`HRV_UI_KEY` no sustituye OAuth: es una clave operativa de la UI y no ofrece
identidad, consentimiento, expiracion ni scopes adecuados para un conector.

Al ser una aplicacion N=1, la autorizacion debe quedar restringida a la cuenta
del atleta. No se introducira modelo multi-atleta ni se compartiran las
credenciales de proveedores con ChatGPT.

## Herramientas iniciales

Todas tendran `readOnlyHint: true`, limites de tamano, orden determinista,
`as_of`, frescura, calidad y procedencia:

```text
get_today_status()
get_hrv_trend(from, to)
get_training_load(from, to)
search_sessions(from, to, sport, limit)
get_session_context(session_id)
get_weekly_coach(date)
get_analysis_report(session_id)
```

Los resultados separaran `measured`, `derived`, `context`, `quality` y
`provenance`. Cuando falte evidencia, devolveran `partial`, `stale` o
`not_found`; nunca una conclusion inventada.

## Interfaz opcional

Apps SDK puede asociar una interfaz embebida a las herramientas: grafica de
HRV/sueno/carga, tabla de sesiones y resumen semanal. La interfaz es una fase
posterior: primero se valida el contrato MCP textual y sus respuestas
estructuradas.

## Fases

1. Completar `AYO-15`: `HRVQueryService`, contrato tipado y MCP local por
   `stdio` de solo lectura.
2. Implementar servidor MCP remoto HTTPS con las mismas herramientas y tests
   de paridad con la version local.
3. Implementar OAuth, metadata, validacion de tokens, rate limiting y
   auditoria sin datos sensibles.
4. Conectar y probar como app privada de ChatGPT.
5. Evaluar componente visual de Apps SDK solo si mejora consultas frecuentes.

## Criterios de aceptacion

1. El conector autentica mediante OAuth + PKCE y solo acepta `hrv:read`.
2. Cada herramienta es estrictamente de solo lectura.
3. No se filtran secretos, rutas absolutas, RR/GPS crudos, streams ni notas
   libres no saneadas.
4. El sync, la UI y el pipeline funcionan aunque el MCP este caido.
5. Las respuestas conservan contratos HRV, causalidad temporal, calidad y
   trazabilidad de `AYO-15`.
6. El conector queda disponible como app privada, sin publicacion ni soporte
   multiusuario implicitos.

## Referencias

- OpenAI Apps SDK: <https://developers.openai.com/apps-sdk>
- Construccion del servidor MCP: <https://developers.openai.com/apps-sdk/build/mcp-server>
- Autenticacion de Apps SDK: <https://developers.openai.com/apps-sdk/build/auth>
- Plan local previo: `docs/HRV/AYO-15 Crear MCP de solo lectura para la aplicacion HRV.md`
