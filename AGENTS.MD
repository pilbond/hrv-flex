# AGENTS.md — Polar HRV Automation (Railway)

## Objetivo del proyecto
Sistema automatizado de monitoreo HRV que:
- Autentica con Polar AccessLink (OAuth2 Authorization Code).
- Descarga datos (p.ej. sesiones Body&Mind/HRV) vía API.
- Procesa HRV con algoritmos propios (`endurance_hrv.py`).
- Expone UI web móvil (Flask) y endpoints de sincronización.
- Despliegue en Railway para acceso remoto.

## Arquitectura (actual)
- `web_ui.py`: Servidor Flask + UI móvil + endpoints `/auth`, `/auth/callback`, `/api/sync`, `/api/status`.
- `polar_hrv_automation.py`: Lógica de descarga/sync contra Polar API usando tokens ya obtenidos.
- `endurance_hrv.py`: Procesamiento HRV.
- `Dockerfile`: Python 3.11-slim.
- `requirements_web.txt`: dependencias.
- Railway: servicio web en puerto `PORT` (8080).

## Principio clave (para evitar fallos recurrentes)
Debe existir **un único flujo OAuth “web”** en producción (Railway).  
Está prohibido en producción:
- abrir navegador desde backend (`webbrowser.open`)
- levantar un “callback server local” con `HTTPServer().bind()` para capturar el `code`

En Railway el callback debe entrar por el **Flask app**.

## Variables de entorno (Railway / local)
Requeridas:
- `POLAR_CLIENT_ID`
- `POLAR_CLIENT_SECRET`
- `PUBLIC_URL` (ej. `https://web-production-xxxx.up.railway.app`)
- `PORT` (Railway lo define; local usar 8080 o el que corresponda)

Recomendadas:
- `POLAR_TOKEN_PATH` (para persistencia de tokens; en Railway con Volume: `/data/polar_tokens.json`)
- `POLAR_USER_NAME` (opcional; no debe ser requisito funcional)

## Persistencia: Railway Volume
En Railway, el filesystem del contenedor puede ser efímero. Para no perder autorización:
- Crear y montar Volume en `/data`
- Configurar `POLAR_TOKEN_PATH=/data/polar_tokens.json`

Requisitos de implementación:
- El backend debe:
  - crear el directorio padre (`mkdir -p`) antes de escribir
  - guardar tokens con escritura atómica (tmp + replace)
  - aplicar permisos restrictivos si aplica (chmod 600)
- Nunca servir `polar_tokens.json` por HTTP ni imprimirlo en logs.

## OAuth (flujo esperado)
Canon:
1) Usuario abre `GET /auth`
2) Backend redirige a `https://flow.polar.com/oauth2/authorization` con:
   - `response_type=code`
   - `client_id=...`
   - `redirect_uri=${PUBLIC_URL}/auth/callback`
   - `scope=accesslink.read_all` (si aplica; no omitir)
   - `state=<random>` (recomendado)
3) Polar redirige a:
   - `${PUBLIC_URL}/auth/callback?code=XXXXX&state=...`
4) Backend en `/auth/callback`:
   - valida `code` (y `state` si se usa)
   - intercambia `code` por tokens:
     - `POST https://polarremote.com/v2/oauth2/token`
   - guarda tokens en `POLAR_TOKEN_PATH`
   - registra usuario en Polar AccessLink:
     - `POST https://www.polaraccesslink.com/v3/users` con `Authorization: Bearer <access_token>`
     - tratar 409 (already registered) como éxito
5) Usuario vuelve a `/` y puede ejecutar sync

Compatibilidad:
- Se puede mantener `/oauth/callback` como alias a `/auth/callback` si existía legado, pero el canon debe ser `/auth/callback`.

## Endpoints (contrato)
- `GET /` → UI
- `GET /auth` → inicia OAuth (302)
- `GET /auth/callback` → completa OAuth (200 o error explícito)
- `POST /api/sync` → ejecuta sync; si no hay token → 400 con mensaje “Falta autorización. Abre /auth…”
- `GET /api/status` → estado (incluye si hay tokens y última sync)
- `GET /health` → healthcheck simple (200)

## Seguridad (no negociable)
- No commitear: `.env`, `.polar_tokens.json`, `polar_tokens.json`, `.oauth_code.txt`, CSV/HRV personales.
- No loguear tokens, ni `client_secret`, ni respuestas completas del token endpoint.
- No exponer endpoints de “descarga de tokens”.
- Si un secreto se filtra, rotarlo en Polar y actualizar Railway.

## Criterios de aceptación (tests de “done”)
1) En Railway:
   - `GET /auth` devuelve 302 a Polar con `scope` y `redirect_uri` correctos.
2) Tras autorizar en Polar:
   - `GET /auth/callback` devuelve 200 y guarda tokens en `POLAR_TOKEN_PATH`.
3) Sin reautorizar:
   - `POST /api/sync` devuelve 200 (o respuesta de éxito) y usa tokens existentes.
4) Persistencia:
   - tras redeploy/restart en Railway, `POST /api/sync` sigue funcionando (si Volume montado).
5) Observabilidad:
   - logs muestran errores útiles (status_code, endpoint) sin filtrar secretos.

## Diagnóstico rápido (si algo falla)
- Si `/auth/callback` da 400:
  - inspeccionar querystring: ¿viene `error=...` en lugar de `code`?
  - revisar exactitud de `redirect_uri` (https, dominio, path)
  - confirmar `scope` requerido y presente
- Si hay 401 en AccessLink API:
  - confirmar que el token exchange funcionó y se está leyendo el token correcto desde `POLAR_TOKEN_PATH`
  - confirmar que la app en Polar AccessLink está “Active” y callbacks coinciden al 100%

## Estilo de cambios (para agentes)
- Cambios mínimos, sin reestructurar el repo salvo necesidad.
- Mantener compatibilidad Python 3.11.
- Evitar dependencias nuevas si no aportan valor claro.
- No introducir nuevas columnas/formatos en outputs personales sin justificación.
