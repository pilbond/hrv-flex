# Plan AYO-13 — Migrar Polar AccessLink v3 → v4 (ejecución F0–F2)

## Contexto

La integración actual usa AccessLink v3 (`www.polaraccesslink.com/v3`, scope único `accesslink.read_all`, sin refresh token: cuando el access token expira se exige re-autorización manual). Polar publicó la Dynamic API v4 con OAuth en `auth.polar.com`, access token de ~12 h, **refresh token obligatorio**, scopes granulares y consultas por rango. La tarea AYO-13 (Kanvas, grupo Plataforma, estado purple) define una migración por dual stack + shadow + corte controlado, consolidando IU-01 (state OAuth, ya implementado) e IU-02 (refresh token).

Verificado en la doc oficial (https://www.polar.com/polar-api-v4/):
- **Misma app y mismas credenciales que v3** (registro en `admin.polaraccesslink.com`); solo cambian endpoints OAuth y scopes → no hacen falta `POLAR_V4_CLIENT_ID/SECRET` separados, se reutilizan `CLIENT_ID`/`CLIENT_SECRET`.
- Access token 12 h; refresh token para renovar sin re-auth.
- `GET /training-sessions` incluye samples RR (`trainingsessionRRSample`) → buen indicio para el fallback RR; F0 lo confirma empíricamente.
- No hay registro de usuario (POST /users) documentado en v4 → F0 lo confirma; el código queda preparado para ambas vías.

**Alcance aprobado por el usuario:** implementar **F0–F2** ahora (fixtures + cliente v4 aislado + OAuth v4 con refresh, todo bajo feature flag, runtime sigue en v3). F3–F6 quedan planificadas (dependen de autorización real y días de observación shadow). Además, **proponer subtareas en Kanvas** (purple) por fase.

**Principio rector:** el "modelo interno" es el shape v3 que ya consumen `sleep_store`, `hrv_sync_flow` y `polar_sessions`. Se usan **adaptadores ligeros v4→shape v3** (no refactor a dataclasses): los consumidores canónicos no cambian, cumpliendo "ningún consumidor depende de campos v4" con diff mínimo.

**No tocar:** `SLEEP_COLUMNS`/`upsert_sleep_row`, builders (`build_hrv_core.py`, `build_hrv_final_dashboard.py`, `build_sessions.py`), `dropbox_rr.py`, `intervals_sync.py`, CSVs canónicos, `polar_client.py` (cliente v3 puro hasta F6), tests v3 existentes (son el contrato de rollback). Sin commits/push salvo petición explícita del usuario.

---

## F0 — Contrato y fixtures

**Nuevo `scripts/capture_v4_fixtures.py`** (dev one-shot, no productivo):
- Flujo auth code local reutilizando el patrón de `hrv_app/polar_oauth_local.py` (HTTPServer:5050 + webbrowser) pero contra `https://auth.polar.com/oauth/authorize` y `.../oauth/token` con scopes `sleep:read nightly_recharge:read training_sessions:read ppi_data:read`.
- Descarga y vuelca respuestas crudas: sleeps por rango, nightly-recharge-results, training-sessions (list + detalle con samples), ppi-samples, token response (redactado).
- `--anonymize`: desplaza fechas, sustituye ids, elimina tokens → salida a `tests/fixtures/polar_v4/`.

**Fixtures v3 equivalentes** en `tests/fixtures/polar_v3/` (capturados del runtime actual o construidos desde los mocks inline de los tests existentes).

**Matriz de paridad** en `docs/HRV/AYO-13-matriz-paridad-v3-v4.md`: campos equivalentes/nuevos/ausentes/ambiguos por dominio (sleep, nightly, sessions, RR/PPI); confirmación empírica de: host base v4 exacto, ausencia de registro de usuario, presencia de `x_user_id` en token response, samples RR en training-sessions, visibilidad de micro-sesiones BODY_AND_MIND ≤10 min.

*Acción manual del usuario:* registrar `http://localhost:5050/oauth2/callback` como redirect URI extra en admin.polaraccesslink.com (si no está), ejecutar el script y autorizar. Si aún no puede, F1–F2 avanzan con fixtures provisionales construidos desde la spec pública y se marcan como `provisional` en la matriz.

## F1 — Cliente v4 aislado + adaptadores (sin imports desde código productivo)

**Nuevo `hrv_app/polar_client_v4.py`:**
- `API_BASE_V4` (confirmado en F0), `class PolarV4Error(RuntimeError)` con status y extracto de body **sin tokens**.
- `class V4Client`: `_request()` con Bearer, rate limit 0.4 s (mismo patrón que `PolarSessionClient`), timeout, y retry único tras 401 (delega refresh en `polar_auth_v4`, ver F2).
- Métodos: `fetch_sleeps(from, to)`, `fetch_nightly_recharges(from, to)`, `list_training_sessions(...)`, `get_training_session(id)` (con samples si F0 lo confirma), `fetch_ppi_samples(from, to)`.

**Nuevo `hrv_app/polar_adapters_v4.py`:**
- TypedDicts `InternalSleep` / `InternalNightly` / `InternalExercise` = subconjunto del shape v3 que los consumidores realmente leen (lista cerrada extraída de `sleep_store.py` y `polar_sessions.py`/`hrv_sync_flow.py` en F0).
- `v4_sleep_to_internal()`, `v4_nightly_to_internal()`, `v4_session_to_internal()`, `index_by_date()` (respuesta de rango v4 → lookup por fecha estilo v3). Mapeos según la matriz de paridad, no inventados.

**Tests:** `tests/test_polar_client_v4_contract.py` (URLs exactas, params from/to, error tipado sin token, retry 401 máx 1) y `tests/test_polar_adapters_v4.py` (fixture v4 → shape v3 campo a campo, fechas límite, ausencia → None).

## F2 — OAuth v4 + refresh bajo feature flag (consolida IU-01/IU-02)

**Nuevo `hrv_app/polar_auth_v4.py`:**
- `AUTH_URL_V4`, `TOKEN_URL_V4` (`https://auth.polar.com/oauth/{authorize,token}`).
- `build_auth_url_v4()`, `exchange_code_for_token_v4()`, `refresh_token_v4()` — reutilizan `build_basic_auth_header` y `save_json_atomic` de `hrv_app/oauth_utils.py` (sin modificarlos).
- Bundle v4 en **archivo separado** `polar_tokens_v4.json` (junto a `TOKEN_FILE`, mismo mecanismo de resolución de ruta de `config.py:137`): `{provider_version:"v4", access_token, refresh_token, expires_in, obtained_at, scopes, x_user_id}`. Rollback = flip de env var, el bundle v3 nunca se toca.
- `get_valid_access_token(path)`: refresh proactivo si quedan <120 s (con TTL 12 h y sync diario, el refresh es el camino caliente). `threading.Lock` de módulo + **relectura del bundle de disco tras adquirir el lock** (si otro hilo/proceso ya refrescó, se usa ese); escritura atómica conjunta de access+refresh. Sin file locks nuevos: la exclusividad mutua de jobs ya existente cubre el resto.
- Scopes guardados ≠ scopes configurados → bundle inválido → re-auth explícita (criterio del doc).
- `redact(bundle)` para diagnostics/logs: jamás expone access ni refresh token.

**`hrv_app/config.py`** (junto a L100-103, sin tocar constantes v3):
```python
POLAR_API_VERSION = (os.environ.get("POLAR_API_VERSION") or "v3").lower()  # v3|v4|shadow; inválido→v3
POLAR_V4_SCOPES = os.environ.get("POLAR_V4_SCOPES") or "sleep:read nightly_recharge:read training_sessions:read"
TOKEN_FILE_V4 = ...  # polar_tokens_v4.json, mismo resolver que TOKEN_FILE
```

**`web_ui.py`** (únicos puntos tocados en F2):
- `/auth` (L1330): si versión efectiva v4 **o** `?provider=v4` → `build_auth_url_v4` con `POLAR_V4_SCOPES`. El **state lleva la versión** (`_issue_oauth_state` guarda `version`, `_consume_oauth_state` la devuelve) → un solo callback, sin redirect URI nuevo.
- Callback (L1364): dispatch por versión del state → exchange v3 actual (intacto) o `exchange_code_for_token_v4` + bundle v4 atómico. Registro de usuario: `_register_for_version()` — v3 llama a `_register_polar_user` actual; v4 controlado por env flag `POLAR_V4_REQUIRES_REGISTRATION` (default False → `{"status":"not_required"}`), ~10 líneas de hook por si F0 demuestra lo contrario.
- `_token_diagnostics()` (L262): en modo v4 lee `TOKEN_FILE_V4` vía `redact()`; nuevo reason `"refreshable"` (expirado con refresh_token ≠ requiere re-auth).

**Tests F2:**
- `tests/test_polar_auth_v4.py`: exchange, refresh, rotación atómica, ventana de skew, scopes mismatch → re-auth, `redact()` sin refresh_token.
- `tests/test_polar_v4_refresh_retry.py`: 401 → refresh → retry, máx 1, relectura de disco.
- Ampliar `tests/test_web_ui_security.py`: state con versión, callback v4 persiste bundle, assert literal de que el JSON de `/api/status` no contiene `refresh_token`.
- Caso nuevo en `tests/test_web_ui_status.py`: reason `refreshable`.

*Acción manual del usuario tras F2:* nada obligatorio — con `POLAR_API_VERSION` sin definir, el runtime es idéntico a hoy. Opcional: autorizar v4 vía `/auth?provider=v4` para dejar el bundle v4 listo para shadow.

---

## F3–F6 (planificadas, NO en esta ejecución)

- **F3 shadow:** nuevo `hrv_app/polar_shadow.py` + hook al final de `--process` en `polar_hrv_automation.py`; sidecar `data/audit/polar_v4_shadow.jsonl` (volumen Railway) con presencia/diffs por fecha×dominio + latencia/refreshes; `scripts/shadow_report.py` de solo lectura. *(Revisión externa 2026-06-12)*: el sidecar debe incluir contadores explícitos por corrida — sesiones vistas, RR extraídos, sleeps/nightly adaptados, campos faltantes por dominio y mismatches por fecha — para que el informe de corte sea auditable sin releer el JSONL completo. Logs estructurados mínimos que distingan: fallo de auth, scopes insuficientes, refresh cedido por lock, respuesta Polar malformada, adapter mismatch. Shadow solo lee v4 y compara contra las observaciones v3 del sync (no re-consulta v3, no duplica escrituras). Requiere `POLAR_API_VERSION=shadow` en Railway y 7–14 días de observación.
- **F4 PPI:** script en `research/` comparando PPI v4 vs RR Dropbox vs type-11 v3; no toca `build_hrv_core.py`.
- **F5 corte:** nuevo `hrv_app/polar_gateway.py` (misma firma que `polar_client.py`, dispatch por flag, caché de rango para sleep/nightly) + reimports en `sleep_store.py` (L12), `hrv_sync_flow.py` (L47), `polar_hrv_automation.py`, `PolarSessionClient`. Corte escalonado: primero sleep/nightly (`POLAR_API_VERSION=v4`), después sesiones (`POLAR_V4_SESSIONS=1`). Riesgo conocido: `PolarSessionClient` carga su token por su cuenta y `load_tokens()` v3 corta si expirado — en v4 ambos deben resolver token vía gateway.
- **F6 retirada v3:** solo tras cerrar la matriz de paridad; actualizar `AGENTS.md`, `CLAUDE.md`, variables Railway, `analysis/session_analysis_pipeline.py` (importa `polar_client` directamente); rollback documentado un ciclo.

## Subtareas Kanvas

Con `python canvas-tool.py Project.canvas` proponer (purple) en grupo Plataforma, encadenadas con `add-dep` bajo AYO-13:
1. `AYO-13-F0` Capturar fixtures y matriz de paridad v3/v4
2. `AYO-13-F1` Cliente v4 aislado y adaptadores (dep: F0)
3. `AYO-13-F2` OAuth v4 y refresh bajo flag (dep: F1)
4. `AYO-13-F3` Lecturas shadow y sidecar de auditoría (dep: F2)
5. `AYO-13-F4` Dropbox como única fuente de nuevos RR matinales (dep: F3)
6. `AYO-13-F5` Corte controlado a v4 (dep: F3)
7. `AYO-13-F6` Retirada v3 y limpieza (dep: F4, F5)

(Los IDs reales los asigna canvas-tool; usar `propose-group` si está disponible y `start` sobre F0/F1/F2 al comenzar la implementación.)

## Verificación

1. `pytest` completo en verde — los tests v3 existentes (`test_polar_client_contract.py`, `test_polar_oauth_local_contract.py`, `test_sleep_store_contract.py`, `test_web_ui_security.py`, …) no se modifican y deben seguir pasando sin cambios (salvo los casos añadidos).
2. Tests nuevos F1/F2 en verde con fixtures.
3. Smoke local sin `POLAR_API_VERSION`: arrancar `web_ui.py`, comprobar que `/auth` sigue redirigiendo a `flow.polar.com` con scope `accesslink.read_all` y que `/api/status` es idéntico a hoy (rollback implícito verificado).
4. Smoke con `POLAR_API_VERSION=v4` (o `/auth?provider=v4`): `/auth` redirige a `auth.polar.com` con los scopes granulares y state; el callback con code simulado/real persiste `polar_tokens_v4.json` con chmod 600 y sin refresh_token en logs ni en `/api/status`.
5. Si hay credenciales/autorización real: ejecutar `scripts/capture_v4_fixtures.py`, verificar fixtures y completar la matriz de paridad (resuelve las incógnitas de samples RR y micro-sesiones BODY_AND_MIND).
6. Actualizar la nota `docs/HRV/AYO-13 Migrar Polar AccessLink de v3 a v4.md` (sección Estado) con lo confirmado de la doc oficial (misma app/credenciales que v3).
