
Estado: **COMPLETADA** — 2026-06-18
Autor: análisis para Claude Code
Doc padre: `docs/HRV/AYO-13 Migrar Polar AccessLink de v3 a v4.md` (Fase 6)
Tarjeta Kanvas: `AYO-22` (cyan — pendiente revisión humana)

---

## 1. Resumen ejecutivo

AYO-22 es la **fase final** de la migración Polar v3 → v4: retirar el código,
las constantes y la configuración v3 una vez que v4 ya es el runtime normal.
No añade funcionalidad; **reduce superficie** y consolida v4 como único camino.

**Conclusión principal revisada (2026-06-17):**

- AYO-21 y AYO-23 ya dejaron v4 como runtime principal del producto.
- F6 ya no debe mezclar "hacer funcionar v4" con "borrar v3".
- Lo que sigue pendiente en F6 es la **retirada del doble stack**:
  OAuth/callback v3, `polar_oauth_local.py`, `polar_client.py`, ramas
  `shadow`, diagnósticos duales y backend v3 de sesiones.
- La paridad funcional de RR de sesiones en `analysis` ya quedó tratada fuera
  de F6 en `AYO-24`; F6 no debe reabrir esa discusión.

Este documento queda como plan de retirada final post-AYO-23.

---

## 2. Estado real de la migración (verificado en código, 2026-06-17)

| Fase                    | Tarea      | Estado          | Evidencia en repo                                                      |
| ----------------------- | ---------- | --------------- | ---------------------------------------------------------------------- |
| F0 Fixtures/paridad     | AYO-16     | ✅               | `scripts/capture_v4_fixtures.py`, captura real 2026-06-13 en la matriz |
| F1 Cliente v4 aislado   | AYO-17     | ✅               | `hrv_app/polar_client_v4.py`, `hrv_app/polar_adapters_v4.py`           |
| F2 OAuth v4 + refresh   | AYO-18     | ✅               | `hrv_app/polar_auth_v4.py`, flag `POLAR_API_VERSION`, callback dual    |
| F3 Lecturas shadow      | AYO-19     | ✅               | `hrv_app/polar_shadow.py`, sidecar `data/audit/polar_v4_shadow.jsonl`  |
| F4 Dropbox RR único     | AYO-20     | ✅ (orange)      | `hrv_sync_flow.sync_hrv_range` sin fallback Polar                      |
| **F5 Corte controlado** | **AYO-21** | ✅ | gateway y runtime v4 ya integrados |
| **F5.3 Consolidacion**  | **AYO-23** | ✅ | `POLAR_API_VERSION` default `v4`, `/auth` orientado a v4, legado v3 aislado |
| **F6 Retirada v3**      | **AYO-22** | **🟡 pendiente** | retirada final del doble stack y limpieza |

**Lo que aún corre en v3 (lo que F6 debe retirar):**

- `hrv_app/config.py` — constantes v3: `SCOPE`, `API_BASE`, `AUTH_URL`,
  `TOKEN_URL`; flag triple `POLAR_API_VERSION=v3|v4|shadow`.
- `hrv_app/polar_client.py` — cliente v3: `api_request`, `list_exercises`,
  `get_exercise_with_samples`, `fetch_sleep`/`fetch_nightly` (`/v3/...`),
  `register_user_if_needed`.
- `hrv_app/oauth_utils.py` — `register_polar_user` (POST XML `/v3/users`) y el
  `exchange_code_for_token` genérico v3.
- `hrv_app/polar_oauth_local.py` — helper OAuth local (abre navegador +
  `HTTPServer`) atado a `AUTH_URL`/`TOKEN_URL`/`SCOPE` v3.
- `web_ui.py` — mantiene flujo dual `?provider=v3|v4`, `_register_polar_user`,
  ramas `v3`/`shadow` en `_token_diagnostics`, callback dual y retry-aware por
  provider.
- `hrv_app/polar_shadow.py` + `scripts/shadow_report.py` — infraestructura de
  comparación v3↔v4 (deja de tener sentido cuando v4 es la única fuente).
- `hrv_app/polar_sessions.py` — sigue conservando backend v3 y deja el backend
  v4 de sesiones tras `POLAR_V4_SESSIONS`.
- `analysis/session_analysis_pipeline.py` — ya no importa top-level el cliente
  v3, pero mantiene una rama legacy `v3` local para RR de sesiones.
- Tests v3: `test_polar_client_contract.py`, `test_polar_shadow_contract.py`,
  `test_polar_oauth_local_contract.py`, fixtures `tests/fixtures/polar_v3/`, y
  ramas v3/provider en `test_web_ui_security.py` y `test_polar_hrv_automation_cli.py`.

---

## 3. Precondiciones de arranque (gate de F6)

F6 **no se inicia** hasta que se cumpla TODO lo siguiente. Es una checklist de
entrada, no parte del trabajo de F6:

1. **AYO-23 cerrada funcionalmente**: `POLAR_API_VERSION=v4` es el default,
   `/auth` entra en v4 por defecto y el runtime ordinario ya no depende de v3.
2. **Ventana shadow superada** (criterios ya escritos en la matriz, sección
   "Criterios cuantitativos de corte (gate F5)"):
   - sleep/nightly: cobertura v4 ≥ v3, |Δrmssd| ≤ 1 ms, |Δduración| ≤ 5 min/noche;
   - sesiones: 100% match con |Δstart| < 20 min y mismo deporte, o discrepancia
     justificada;
   - operativo: 0 refresh no recuperados, latencia v4 no degrada el sync.
3. **Matriz de paridad CERRADA**: cambiar la cabecera de
   `AYO-13-matriz-paridad-v3-v4.md` de `PROVISIONAL` a `CERRADA`, con los
   resultados de la ventana shadow anexados. (El registro de usuario v4 ya está
   confirmado innecesario: matriz, incógnita #1 — `/v4/data/*` funciona sin
   `POST /users`.)
4. **AYO-24 cerrada**: la paridad funcional de RR de sesion en `analysis`
   ya esta resuelta y validada antes del corte final; F6 no la rediscute.
5. **Punto de rollback creado**: tag git del último build con v4 operativo y v3
   aún presente (ver §6).

Si cualquiera falla, F6 se queda en `purple`/bloqueada.

---

## 4. Objetivo y alcance de F6

**Objetivo:** que v4 sea el único transporte Polar del proyecto, sin flags de
versión, sin código muerto v3 y con documentación/operativa coherentes,
manteniendo intactos los outputs canónicos y un rollback real durante un ciclo
de despliegue.

**Dentro de alcance:**

- Retirar registro de usuario v3 y endpoints v3.
- Borrar `polar_oauth_local.py` y adaptar puntualmente los consumidores
  auxiliares que aún dependan de él.
- Retirar la rama legacy `v3` que todavía queda en
  `analysis/session_analysis_pipeline.py` una vez cumplido el gate de `AYO-24`.
- Colapsar el flag `POLAR_API_VERSION` y retirar también
  `POLAR_V4_SESSIONS` como resto transitorio de configuración.
- Retirar la infraestructura shadow (F3) del runtime.
- Limpiar tests v3 y fixtures `polar_v3/`.
- Actualizar `AGENTS.md`, `CLAUDE.md`, `docs/contracts/` y la doc operativa.
- Limpiar variables de entorno v3 en Railway.
- Dejar rollback documentado un ciclo de despliegue.

**Fuera de alcance:**

- Cambiar columnas o semántica de `CORE`/`FINAL`/`DASHBOARD`/`sleep`/`sessions`.
- Renombrar el bundle de tokens v4 al path canónico v3 (ver §5, decisión D2).
- Tocar el método analítico de `analysis/` más allá de la frontera Polar.
- Diseñar o implementar de cero el soporte de RR de sesiones de entrenamiento
  sobre v4.
- Introducir MCP en el camino de `/api/sync` (es AYO-14/AYO-15).
- Adoptar scopes/endpoints v4 nuevos sin consumidor.

---

## 5. Decisiones de diseño (con ventajas / inconvenientes)

### D1 — Rollback por redeploy, no por flag

En F5 el rollback es "flip de `POLAR_API_VERSION=v3`". En F6, al **borrar** el
código v3, ese flip deja de existir. El rollback de F6 pasa a ser **redeploy del
build anterior** (tag git previo a la retirada).

- ✅ Ventaja: simpleza máxima; no se conserva una rama de código v3 "por si
  acaso" que nunca se prueba y se pudre.
- ✅ Ventaja: el binario de rollback está realmente probado (es el build que
  estuvo en producción durante F5).
- ⚠️ Inconveniente: el rollback es de grano grueso (todo el deploy), no
  selectivo. Mitigación: ventana de un ciclo de despliegue con el tag a mano y
  procedimiento escrito en §6.

### D2 — Conservar el bundle de tokens v4 en su path actual

Mantener `.polar_tokens_v4.json` / `POLAR_TOKEN_PATH_V4`. **No** renombrarlo al
path v3 (`POLAR_TOKEN_PATH`) "para que quede limpio".

- ✅ Ventaja: no hay migración de estado en el volumen persistente de Railway;
  cero riesgo de perder la sesión OAuth tras el deploy.
- ✅ Ventaja: cambio reversible trivialmente.
- ⚠️ Inconveniente: queda una variable con sufijo `_V4` algo redundante cuando
  ya no hay v3. Es puramente cosmético; el coste de renombrar (reautorizar o
  copiar el archivo en el volumen) no compensa. Documentar el nombre y seguir.

### D3 — Colapsar el flag en una sola fase, no en dos

`POLAR_API_VERSION` desaparece. v4 es el comportamiento implícito (igual que hoy
v3 es el implícito sin flag). Se elimina la rama `shadow` y la validación del
flag.

- ✅ Ventaja: una sola lectura del código; sin estados intermedios confusos.
- ⚠️ Inconveniente: si v4 fallara en producción tras F6, no hay flip; aplica D1
  (redeploy). Aceptable porque F5 + ventana shadow ya validaron v4.
- Alternativa descartada (sobreingeniería): mantener un flag `v4|legacy` un
  release más. Añade ramas muertas y tests dobles sin valor real una vez que la
  ventana shadow pasó.

### D4 — `polar_oauth_local.py`: borrar, no migrar

Es un helper **solo local** (abre navegador + `HTTPServer`, prohibido en prod).
Tras AYO-23 ya quedó explícitamente como legado temporal. La decisión más simple
y coherente con el runtime final es **borrarlo**, no migrarlo.

- ✅ Ventaja: elimina un segundo camino OAuth local que ya no aporta valor al
  producto ni al despliegue.
- ✅ Ventaja: reduce imports legacy y evita mantener código de navegador local
  + `HTTPServer` para un caso marginal.
- ⚠️ Inconveniente: scripts auxiliares de captura o auditoría que aún lo usen
  deben adaptarse de forma puntual antes de borrarlo.

### D5 — Shadow (F3): retirar del runtime, conservar utilidad de auditoría

`polar_shadow.py` y la rama `shadow` de `/api/status` se eliminan del runtime.
El script de captura/comparación se mueve a `research/` si se quiere conservar
para auditorías puntuales; el JSONL histórico ya capturado se conserva.

- ✅ Ventaja: quita un camino de red v4 paralelo y código condicional de
  `/api/sync` y `/api/status`.
- ⚠️ Inconveniente: perder la comparación continua v3↔v4. Es esperado: tras el
  corte ya no hay v3 con qué comparar.

---

## 6. Procedimiento de rollback (a documentar y mantener un ciclo)

1. Antes de tocar nada: `git tag ayo22-pre-v3-removal` sobre el build v4 operativo.
2. Anotar en `AGENTS.md` el SHA/tag y el comando de redeploy de ese build.
3. Si tras desplegar F6 aparece un fallo Polar no recuperable:
   - redeploy del tag `ayo22-pre-v3-removal` (que aún tiene v3 + flag);
   - `POLAR_API_VERSION=v3` para volver al transporte v3 conocido.
4. Mantener tag + nota **un ciclo de despliegue** completo. Pasado ese ciclo sin
   incidencias, retirar la nota de rollback (no el tag).

---

## 7. Plan por pasos (orden seguro)

Orden pensado para que en cada paso el árbol siga compilando y con tests verdes.
La regla es **retirar consumidores antes que productores**: primero se quita
quién importa v3, luego el v3 importado.

**Paso 0 — Gate y rollback.** Verificar §3, crear tag de rollback (§6).

**Paso 1 — Verificar el gate funcional ya cerrado en `AYO-24`.**

Antes de borrar la ultima rama legacy de `analysis`, comprobar que la validación
de `AYO-24` sigue vigente para el árbol exacto que se va a cortar. F6 no diseña
capacidad nueva ni reabre esa decisión.

**Paso 2 — Borrar `polar_oauth_local.py`.**
Adaptar antes los consumidores auxiliares que aún dependan de `load_tokens()`,
`do_oauth_flow()` o helpers de callback. No mantener un segundo flujo OAuth
local por inercia.
Consumidores no-runtime identificados al ejecutar este paso:
- `scripts/capture_v4_fixtures.py` — inlineó `_CallbackState` y `start_callback_server` directamente (D4: borrar, no migrar).
- `research/audits/intervals_vs_polar_stream/scripts/compare_session_streams.py` — import retirado; script marcado con NOTE de actualización pendiente a V4Client.
No se encontraron otros consumidores fuera de runtime ni de tests.

**Paso 3 — `web_ui.py` a v4 único.**
Eliminar `?provider=v3|v4` (queda v4 implícito), `_register_polar_user`, la rama
`shadow`/`v3` de `_token_diagnostics`, y simplificar el callback a v4. Mantener
validación de `state`, TTL y uso único (ya existentes).

**Paso 4 — Retirar registro de usuario y cliente v3.**
Quitar `register_polar_user` de `oauth_utils.py` y `register_user_if_needed` de
`polar_client.py`. Eliminar el módulo `polar_client.py` v3 si ya no lo importa
nadie (verificar con el grafo `query_graph pattern=callers_of`); si quedara algo
genérico reutilizable, conservar solo eso.

**Paso 5 — Limpiar `config.py`.**
Eliminar `SCOPE`, `API_BASE`, `AUTH_URL`, `TOKEN_URL` v3 y la maquinaria del flag
`POLAR_API_VERSION` (validación + modos), junto con `POLAR_V4_SESSIONS` como
flag transitorio ya obsoleto. Conservar `POLAR_V4_SCOPES`,
`TOKEN_FILE_V4`/`POLAR_TOKEN_PATH_V4`, `CLIENT_ID`/`CLIENT_SECRET` (compartidos),
`SPORTS_FILTER`, etc.

**Paso 6 — Retirar shadow del runtime.**
Eliminar `polar_shadow.py` del flujo `--process` y la rama `shadow` de
`/api/status`; mover `scripts/shadow_report.py` a `research/` si se conserva.

**Paso 7 — Tests.**
Borrar `test_polar_client_contract.py`, `test_polar_shadow_contract.py`,
`test_polar_oauth_local_contract.py` (D4 fija borrar, no migrar; no hay helper
que mantener), fixtures `tests/fixtures/polar_v3/`, y limpiar ramas v3/provider en
`test_web_ui_security.py` y `test_polar_hrv_automation_cli.py`. Confirmar que la
suite v4 (`test_polar_*_v4*.py`, `test_polar_auth_v4.py`) cubre lo retirado.

**Paso 8 — Documentación.**
Actualizar `AGENTS.md` (endpoints, variables, snapshot), `CLAUDE.md` (variables
de entorno, snapshot), `docs/contracts/GUIA_PYTHON_SCRIPTS.md`,
`docs/contracts/PROCEDIMIENTO_RECOMENDADO.md`, cerrar la matriz de paridad y
añadir el bloque de cierre F6 al doc padre AYO-13. Cualquier mención a v3 pasa a
histórico.

**Paso 9 — Verificación end-to-end.**
`pytest` completo verde; smoke de `/auth` → callback → `/api/status` → `/api/sync`
→ `/api/sync-sessions`; redeploy Railway con volumen y sync completo; grep de
ausencia de secretos en logs; confirmar esquemas CSV intactos (nº de columnas).

**Checklist operativa de despliegue — Railway / entorno.**
Quitar `POLAR_API_VERSION` y `POLAR_V4_SESSIONS` del entorno de Railway.
**No tocar** `POLAR_CLIENT_ID(2)` ni `POLAR_CLIENT_SECRET` (son la **misma
app/credenciales** que v4 — ver matriz, "misma app y credenciales"; borrarlas
rompería v4). Mantener `POLAR_V4_SCOPES` y `POLAR_TOKEN_PATH_V4`.

---

## 8. Criterios de aceptación

1. No queda referencia operativa a `polaraccesslink.com/v3`, `flow.polar.com`,
   `polarremote.com`, `accesslink.read_all` ni `POST /users` fuera de `docs`
   históricas.
2. `POLAR_API_VERSION` y `POLAR_V4_SESSIONS` no existen en código ni en
   variables de Railway.
3. `/auth`, callback y `/api/status` operan solo en v4; `state` validado.
4. La retirada de la rama legacy de RR de sesion en `analysis` se apoya en el
   gate funcional ya resuelto en `AYO-24`; F6 no introduce regresión ahí.
5. Sync completo (sleep, nightly, sesiones) verde tras redeploy con volumen;
   esquemas y nº de columnas de CSV canónicos sin cambios.
6. `/api/sync` y `/api/sync-sessions` mantienen exclusividad mutua.
7. Suite de tests verde sin los contratos v3; cobertura v4 equivalente.
8. Matriz de paridad marcada CERRADA con resultados de la ventana shadow.
9. Rollback documentado y vigente un ciclo de despliegue (tag + procedimiento).
10. Sin secretos (tokens, client_secret, refresh) en logs, errores HTTP ni
    `/api/status`.

---

## 9. Preguntas abiertas para el usuario (antes de ejecutar)

1. **`scripts/shadow_report.py` y captura v4**: ¿conservar en `research/` para
   auditorías puntuales o eliminar del repo? (D5).
2. **Momento**: ¿quieres que F6 se prepare ahora como PR "listo para mergear tras
   cerrar la ventana shadow", o se mantiene en backlog hasta ejecutar ese corte?

---

## 10. Ventajas e inconvenientes globales de la tarea

**Ventajas de hacer F6 (cuando proceda):**

- Una sola frontera Polar (v4) → menos código, menos ramas condicionales, menos
  tests dobles, menos superficie de fallo.
- Elimina el registro de usuario XML v3 y el flag triple, simplificando OAuth y
  `/api/status`.
- Continuidad real vía refresh token v4 sin el camino v3 latente.
- Documentación y operativa coherentes con el runtime real.

**Inconvenientes / costes:**

- Pérdida del rollback por flag: pasa a redeploy de build anterior (D1). Coste
  bajo si se mantiene el tag.
- Es trabajo de **borrado** con poco valor visible para el usuario final; su
  beneficio es mantenibilidad, no función nueva.
- Riesgo si se ejecuta antes de tiempo: retirar v3 sin que v4 esté validado en
  producción dejaría al sistema sin red de seguridad (riesgo explícito en el
  doc padre: "retirada prematura de v3 sin rollback real").

**Recomendación:** mantener AYO-22 acotada a retirada de legado hasta cerrar la
ventana shadow. Cuando eso ocurra, ejecutar F6 como un PR único, secuencial y
acotado (§7), priorizando el orden seguro, la retirada explícita de
`POLAR_V4_SESSIONS` y el rollback por tag. Evitar sobreingeniería: nada de
flags de compatibilidad nuevos, nada de reabrir `AYO-24` y nada de renombrar
estado persistido por cosmética.

---

## 11. Regression gate (mínimo)

- `pytest` completo verde sin los módulos/contratos v3.
- Tests de OAuth v4: authorization code, `state`, refresh, rotación atómica,
  `401 → refresh → retry` (un reintento).
- Smoke `/auth` → callback → `/api/status` → `/api/sync` → `/api/sync-sessions`.
- Sync completo Railway con volumen y redeploy; columnas CSV invariantes.
- Verificación de ausencia de secretos en logs.
- Análisis de sesión con RR vía v4 produce el mismo reporte que con v3 para una
  sesión de referencia.
