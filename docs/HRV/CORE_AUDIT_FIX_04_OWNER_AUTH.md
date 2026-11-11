# Core Audit Fix 04 — Frontera de propietario OAuth y API

## Objetivo

Evitar que un tercero sustituya el bundle Polar del atleta o ejecute
operaciones sobre el único `DATA_DIR`, sin introducir infraestructura
multiusuario (login, cuentas, expiración de sesión). El proyecto es N=1
(ver `CLAUDE.md`): la frontera se refuerza sobre el mecanismo existente
`HRV_UI_KEY`, no se reemplaza por un sistema de sesiones de usuario.

## Estado actual (2026-07-16)

Ya implementado:

- `HRV_UI_KEY` protege todos los `/api/*` vía `@app.before_request`
  (`_require_ui_key`, `web_ui.py`). Si no está definida, comportamiento
  histórico sin auth.
- OAuth `state` anti-CSRF con `secrets.token_urlsafe(24)`, uso único y TTL
  (`_issue_oauth_state` / `_consume_oauth_state`, `web_ui.py`).
- Serialización de jobs: los POST operativos comparten estado y no corren
  en paralelo.

Debilidades que esta tarea corrige:

1. `_require_ui_key` acepta la clave por query string (`?key=`), además del
   header `X-HRV-KEY`. Una clave en la URL se filtra a logs de acceso,
   historial del navegador y cabecera `Referer`.
2. `static/ui.js` lee la clave desde `window.location.search` (`?key=`), lo
   que obliga a mantener el secreto en la URL de la UI.
3. El `state` OAuth no está ligado al navegador que inició `/auth`: es de un
   solo uso y con TTL, pero cualquier agente que obtenga un `state` válido
   puede completar el callback y persistir tokens.

## Alcance

Incluye:

- `_require_ui_key` en `web_ui.py` (transporte de la clave).
- Entrega de la clave a `static/ui.js` sin usar la URL.
- Vínculo del `state` OAuth (`/auth`, `/auth/callback`, `/oauth/callback`)
  a una cookie de sesión del navegador.

Explícitamente fuera de alcance (scope creep para N=1):

- Sistema de login / cuentas de usuario / expiración de sesión de propietario.
- Cualquier abstracción multiusuario o multi-tenant.
- Sustituir `HRV_UI_KEY` por otro mecanismo de secreto.

## Prioridad y ordenación

El valor de seguridad de esta tarea no es homogéneo. El único punto que
mueve la aguja de forma real es el **fail-closed de `HRV_UI_KEY` en
producción** (P0): sin él, si la clave no está definida, todos los `/api/*`
quedan abiertos en una URL pública de Railway. El resto (transporte de la
clave, vínculo `state`↔cookie) es endurecimiento / higiene (P1): defensa en
profundidad de severidad moderada-baja para un despliegue N=1.

CAF-04 queda por debajo de CAF-01/02/03 (integridad de datos históricos);
una pérdida de histórico es peor que un endurecimiento de transporte cuando
ya existe la barrera `HRV_UI_KEY`.

## Implementación esperada

### P0 — Fail-closed de `HRV_UI_KEY` en producción (alto valor, bajo esfuerzo)

1. **No operar sin clave en producción.** Si el despliegue es de producción
   (p. ej. `PUBLIC_URL` apunta a Railway) y `HRV_UI_KEY` no está definida, la
   app debe rechazar el arranque o, como mínimo, emitir un warning fuerte y
   bloqueante en el log. En local sin `PUBLIC_URL` se conserva el
   comportamiento histórico (sin auth) para no romper el flujo de desarrollo.

### P1 — Endurecimiento de transporte (higiene, diferible)

2. **Eliminar la clave de la query string.** `_require_ui_key` acepta la
   clave únicamente por el header `X-HRV-KEY`; deja de leer
   `request.args.get("key")`. Mantener `secrets.compare_digest`.
3. **Entregar la clave a la UI sin URL.** Cambiar `static/ui.js` para que no
   lea `?key=`. La clave se establece server-side en una cookie `HttpOnly`,
   `Secure`, `SameSite=Lax` (o se inyecta en el runtime config server-side),
   de modo que `apiFetch` siga enviando `X-HRV-KEY` sin exponer el secreto en
   la barra de direcciones.
4. **Ligar el `state` OAuth a la sesión del navegador.** Al emitir el `state`
   en `/auth`, asociarlo a un identificador guardado en cookie `HttpOnly`,
   `Secure`, `SameSite=Lax`. En el callback, además de consumir el `state`
   (uso único + TTL), verificar que coincide con la cookie del navegador que
   inició el flujo; si no coincide, no persistir tokens.
5. **Preservar invariantes existentes.** Mantener el control anti-replay
   (uso único + TTL) y la serialización de jobs. Sin secretos en URLs ni en
   logs.

## Aceptación

- **P0:** en un despliegue de producción (`PUBLIC_URL` de Railway) sin
  `HRV_UI_KEY`, la app rechaza el arranque o emite un warning bloqueante; en
  local sin `PUBLIC_URL` conserva el comportamiento histórico.
- `_require_ui_key` rechaza (401) toda petición `/api/*` con clave ausente,
  incorrecta o pasada por `?key=` cuando `HRV_UI_KEY` está definida; la acepta
  solo vía header `X-HRV-KEY`.
- `static/ui.js` no lee la clave desde la URL y las operaciones de la UI
  siguen autenticándose contra `/api/*`.
- Un callback OAuth con `state` válido pero sin la cookie de sesión que inició
  el flujo no persiste tokens.
- Ningún secreto (clave de UI, `state`) viaja en query string ni se registra
  en logs.
- Tests parametrizados que cubran `/api/sync`, `/api/sync-sessions`,
  `/api/restore-backup` y `/api/delete-latest-rr` para:
  clave ausente, clave incorrecta, clave por `?key=` (rechazada) y clave por
  header (aceptada); más el caso de callback OAuth sin cookie de sesión.
