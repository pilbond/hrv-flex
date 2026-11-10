# AYO-27 — Extension ChatGPT privada para HRV via Apps SDK

## Estado

Propuesta **aparcada**. Revisada el 2026-11-09 contra el estado actual del
repositorio. No se retira, pero no debe aprobarse hasta que se cumplan las
condiciones de activación.

## Decisión propuesta

Extender la aplicación HRV a ChatGPT mediante una app privada basada en MCP y
Apps SDK: un servidor MCP remoto, HTTPS y de solo lectura, que reutiliza la
capa de consulta y el contrato de respuesta del MCP local
([[AYO-15 Crear MCP de solo lectura para la aplicacion HRV]]).

Uso N=1: una sola cuenta autorizada, la del atleta. Sin sync, restore,
borrados ni ninguna mutación.

## Condiciones de activación

Aprobar la tarea solo cuando se cumplan todas:

1. El MCP local está implementado y se ha usado de forma real durante varias
   semanas, con un contrato de respuesta estable.
2. Existe una necesidad concreta de consultar el estado HRV fuera del entorno
   local (por ejemplo, desde el móvil en ChatGPT) que no cubren la UI web ni el
   brief diario.
3. La frontera de propietario OAuth y API de la app Flask está resuelta y
   `/api/status` ya no expone diagnóstico interno innecesario.
4. Se acepta explícitamente enviar datos de salud del atleta a un tercero
   (OpenAI) como cambio de alcance del proyecto.

## Qué datos puede servir

En Railway solo existe el volumen `/data` con los outputs del pipeline. Los
informes de `analysis/` se generan en local, no se sincronizan a `/data` ni
entran en el backup de Dropbox, y `.dockerignore` excluye
`analysis/reports/` de la imagen. Por tanto, el servidor remoto **solo** puede
responder con:

- `ENDURANCE_HRV_master_FINAL.csv`, `..._DASHBOARD.csv`,
  `..._FINAL_reason_items.json` y manifests;
- `ENDURANCE_HRV_sleep.csv`;
- `ENDURANCE_HRV_sessions_day.csv` y `ENDURANCE_HRV_sessions.csv`;
- `ENDURANCE_HRV_weekly_coach.json` e
  `ENDURANCE_HRV_intensity_distribution_weekly.csv`.

Quedan fuera los análisis de sesión (`session_payload.json`, `summary.json`,
reports). Incorporarlos exigiría un flujo nuevo que suba artefactos de
`analysis/` a `/data`, con redacción de rutas; sería una tarea aparte.

## Arquitectura

```text
ChatGPT
  |
  | OAuth 2.1 Authorization Code + PKCE (scope hrv:read)
  v
MCP HRV remoto (HTTPS, Railway, servicio o proceso separado de la UI Flask)
  |
  v
hrv_app/query/  (misma capa que el MCP local)
  |
  v
/data  (outputs canónicos y manifests; solo lectura)
```

- No reutiliza ni amplía los endpoints operativos de Flask (`/api/sync`,
  `/api/status`, etc.).
- Comparte lectores y sobre de respuesta con el MCP local; tests de paridad
  entre ambos.
- Su caída no afecta al sync, la UI ni el pipeline.

## Autenticación

- Authorization Code con PKCE `S256` y servidor de autorización propio o
  delegado, restringido a la cuenta del atleta.
- Metadatos de recurso protegido y de servidor de autorización según lo que
  exija Apps SDK en el momento de implementar (verificar la documentación
  vigente; los requisitos de autenticación de conectores han cambiado con el
  tiempo).
- Validación de audiencia, expiración y scope `hrv:read` en cada llamada.
- Redirect URI de ChatGPT permitida explícitamente.
- `HRV_UI_KEY` no sustituye OAuth: no ofrece identidad, consentimiento,
  expiración ni scopes.
- Rate limiting y auditoría de llamadas sin datos sensibles en logs.

## Herramientas iniciales

Todas con `readOnlyHint: true`, límites de tamaño, orden determinista, `as_of`,
frescura, calidad y procedencia:

```text
get_today_status()              # equivale a hrv_get_daily_status(última fecha)
get_hrv_trend(from, to)         # sobre hrv_get_date_range
get_data_quality(from, to)      # sobre hrv_get_data_quality
get_training_load(from, to)     # sessions_day, solo columnas allowlisted
get_weekly_coach(date)          # weekly_coach.json; requiere contrato semanal estable
```

Fuera de la primera versión: búsqueda y contexto de sesiones, informes de
análisis y cualquier herramienta que devuelva texto libre (`notes_raw`).

## Interfaz opcional

Apps SDK permite una interfaz embebida (gráfica de HRV, sueño y carga). Solo se
evalúa después de validar el contrato textual y si mejora consultas
frecuentes.

## Fases

1. Comprobar las condiciones de activación.
2. Servidor MCP remoto HTTPS con las herramientas iniciales y tests de paridad
   con el MCP local.
3. OAuth, metadatos, validación de tokens, rate limiting y auditoría.
4. Conexión y prueba como app privada de ChatGPT.
5. Evaluar interfaz visual.

## Relación con otras tareas

- **AYO-15** (propuesta): dependencia dura; aporta capa de consulta y contrato.
- **CAF-04** (propuesta): frontera de propietario OAuth y API; debe cerrarse
  antes de abrir otra superficie autenticada en Railway.
- **IU-04** (propuesta): reducción de `/api/status`; mismo criterio de
  superficie mínima.
- **SYA-18** (propuesta): condiciona `get_weekly_coach` si se apoya en el
  manifest semanal.

## Criterios de aceptación

1. El conector autentica mediante OAuth + PKCE y solo acepta `hrv:read` de la
   cuenta del atleta.
2. Cada herramienta es estrictamente de solo lectura.
3. Solo sirve datos presentes en `/data`; no expone CSV completos, secretos,
   rutas, RR, GPS, streams ni texto libre.
4. El sync, la UI y el pipeline funcionan aunque el MCP remoto esté caído.
5. Las respuestas son idénticas en contrato a las del MCP local para la misma
   fecha y artefactos.
6. El conector queda como app privada, sin publicación ni soporte multiusuario.

## Referencias

- OpenAI Apps SDK: <https://developers.openai.com/apps-sdk>
- Construcción del servidor MCP: <https://developers.openai.com/apps-sdk/build/mcp-server>
- Autenticación de Apps SDK: <https://developers.openai.com/apps-sdk/build/auth>
