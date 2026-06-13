
## Estado

Propuesta de migracion tecnica creada el 2026-06-12.

Actualizacion 2026-06-12 — F0/F1/F2 implementadas (runtime sigue en v3):

- Confirmado por documentacion oficial: v4 usa la **misma app y credenciales**
  que v3 (registro en admin.polaraccesslink.com); solo cambian endpoints
  OAuth, scopes y refresh. `GET /training-sessions` documenta samples RR
  (`trainingsessionRRSample`); pendiente de confirmar con captura real.
- F0: `scripts/capture_v4_fixtures.py` (captura local con `--anonymize`),
  fixtures provisionales en `tests/fixtures/polar_v4/` y `polar_v3/`,
  matriz en `AYO-13-matriz-paridad-v3-v4.md` (estado PROVISIONAL hasta
  captura real).
- F1: `hrv_app/polar_client_v4.py` (V4Client aislado, retry unico tras 401,
  errores tipados sin tokens) y `hrv_app/polar_adapters_v4.py`
  (v4 → shape interno v3). Sin imports desde codigo productivo.
- F2: `hrv_app/polar_auth_v4.py` (exchange, refresh proactivo con lock y
  relectura de disco, rotacion atomica, `redact()`), flag
  `POLAR_API_VERSION=v3|v4|shadow` en `config.py`, bundle separado
  `.polar_tokens_v4.json` (`POLAR_TOKEN_PATH_V4`), `/auth?provider=v4`,
  state con version, callback dual y diagnostico `refreshable` en
  `/api/status`. Consolida IU-01 (state, ya existia) e IU-02 (refresh).
- Sin `POLAR_API_VERSION` el runtime es identico al actual (rollback
  implicito). Suite completa: 464 tests en verde.
- Subtareas Kanvas: AYO-16 (F0) a AYO-22 (F6).
- Pendiente F0 real: autorizar v4 y ejecutar la captura para cerrar la
  matriz (registro de usuario, x_user_id, samples mecanicos, BODY_AND_MIND).

## Objetivo

Migrar la integracion operativa de Polar AccessLink v3 a la Dynamic API v4
sin interrumpir el sync diario, sin cambiar los outputs canonicos y sin
convertir Polar en la fuente primaria de RR mientras no exista evidencia de
paridad frente a `ECG.jsonl + ACC.jsonl`.

La migracion debe mejorar:

- continuidad OAuth mediante refresh token;
- seguridad mediante scopes granulares;
- consultas por rango para sueno, Nightly Recharge y sesiones;
- acceso a PPI, tests y otras senales v4 para validacion o uso analitico;
- trazabilidad de version, scopes y origen de cada respuesta Polar.

## Situacion actual

El runtime usa:

- API base `https://www.polaraccesslink.com/v3`;
- autorizacion `https://flow.polar.com/oauth2/authorization`;
- token `https://polarremote.com/v2/oauth2/token`;
- scope unico `accesslink.read_all`;
- registro de usuario v3;
- `/exercises` y `/exercises/{id}?samples=true`;
- `/users/sleep/{date}`;
- `/users/nightly-recharge/{date}`;
- invalidacion local del access token cuando expira, sin refresh operativo.

Las areas principales afectadas son:

- `hrv_app/config.py`;
- `hrv_app/oauth_utils.py`;
- `hrv_app/polar_oauth_local.py`;
- `hrv_app/polar_client.py`;
- `hrv_app/polar_sessions.py`;
- `hrv_app/sleep_store.py`;
- `hrv_app/hrv_sync_flow.py`;
- `polar_hrv_automation.py`;
- `web_ui.py`;
- tests OAuth, UI, sync, sleep y sesiones.

El grafo del repositorio clasifica el radio de impacto como alto: la frontera
Polar participa en el flujo HRV, el enriquecimiento de sesiones, el sleep
store y la UI web. Por ello no se acepta un cambio directo de URLs.

## Diferencias v4 relevantes

### OAuth

La documentacion v4 define:

- autorizacion: `https://auth.polar.com/oauth/authorize`;
- token y refresh: `https://auth.polar.com/oauth/token`;
- access token con validez aproximada de 12 horas;
- refresh token obligatorio para continuidad;
- scopes granulares separados por dominio.

Scopes iniciales propuestos para el runtime canonico:

- `sleep:read`;
- `nightly_recharge:read`;
- `training_sessions:read`;
- `ppi_data:read`, inicialmente solo en shadow;
- `tests:read`, solo si se adopta una salida analitica concreta.

No solicitar por defecto `profile:read`, `routes:read`, `calendar:read` u otros
scopes sin un consumidor y criterio de privacidad definidos.

### Datos

Endpoints v4 prioritarios:

- `GET /v4/data/sleeps?from=...&to=...`;
- `GET /v4/data/nightly-recharge-results?from=...&to=...`;
- `GET /v4/data/training-sessions/list`;
- `GET /v4/data/ppi-samples?from=...&to=...`;
- `GET /v4/data/tests/list?from=...&to=...`.

La respuesta v4 debe pasar por adaptadores internos. Ningun consumidor
canonico debe depender directamente de nombres de campos v4.

## Decisiones de arquitectura

1. Mantener una sola frontera Python para el pipeline.
2. Introducir v4 en paralelo y conservar v3 durante la validacion.
3. Usar feature flag con modos `v3`, `v4` y `shadow`.
4. Normalizar v3 y v4 a modelos internos equivalentes.
5. Mantener Dropbox como fuente RR primaria.
6. Tratar PPI v4 como fuente candidata hasta validar cobertura, semantica,
   errores estimados, movimiento, skin contact y compatibilidad temporal.
7. No introducir MCP dentro del camino critico de `/api/sync`.
8. No modificar `CORE`, `BETA_AUDIT`, `FINAL`, `DASHBOARD`, `sleep.csv` ni
   `sessions.csv` por el mero cambio de transporte.

Configuracion propuesta:

```text
POLAR_API_VERSION=v3|v4|shadow
POLAR_V4_SCOPES="sleep:read nightly_recharge:read training_sessions:read"
POLAR_TOKEN_PATH=/data/polar_tokens.json
```

El bundle persistido debe incluir version de proveedor, scopes concedidos,
`obtained_at`, expiracion y refresh token, sin exponerlos por logs o HTTP.

## Plan por fases

### Fase 0. Contrato y fixtures

- Capturar fixtures anonimizados v3 de ejercicios, samples, sueno y Nightly
  Recharge.
- Capturar fixtures v4 equivalentes tras una autorizacion de prueba.
- Definir modelos internos para sleep, nightly, training session y PPI.
- Documentar campos equivalentes, nuevos, ausentes y ambiguos.
- Confirmar en una prueba real si v4 elimina el registro de usuario v3 y
  documentar el nuevo ciclo de identidad.

Salida:

- matriz de paridad v3/v4;
- fixtures sin datos personales;
- criterios cuantitativos de corte.

### Fase 1. Cliente v4 aislado

- Crear un cliente v4 dentro de `hrv_app/`, separado de los adaptadores v3.
- Implementar timeout, errores tipados, rate limiting y reintentos acotados.
- Implementar consultas por rango.
- Añadir normalizadores v4 hacia los modelos internos.
- Evitar dependencias nuevas salvo que reduzcan claramente el riesgo.

La capa v4 no debe escribir CSV en esta fase.

### Fase 2. OAuth v4 y refresh

- Cambiar authorization y token endpoints bajo feature flag.
- Persistir y validar `state` en el flujo web.
- Implementar authorization code y refresh token.
- Rotar y guardar atomica y conjuntamente access y refresh token.
- Reintentar una sola vez tras `401` cuando el refresh sea viable.
- Requerir reautorizacion explicita si cambian los scopes.
- Mantener un unico flujo OAuth web en Railway.

Esta fase consolida el alcance de:

- `IU-01 Validar state OAuth y endurecer callbacks web`;
- `IU-02 Implementar refresh token Polar operativo`.

No conviene implementar `IU-02` de forma acoplada al endpoint v3 si su
resultado va a ser reemplazado inmediatamente por v4.

### Fase 3. Lecturas en shadow

- Ejecutar v3 como fuente efectiva y v4 como lectura paralela.
- Comparar cobertura diaria de sleep y Nightly Recharge.
- Comparar sesiones, timestamps, deporte, duracion y disponibilidad de
  samples mecanicos.
- Registrar diferencias en sidecar de auditoria, no en outputs canonicos.
- Medir errores, latencia, rate limits y refreshes.

No se deben duplicar escrituras ni ejecutar dos veces los builders.

### Fase 4. Validacion PPI

- Comparar PPI v4 con RR procedente de Dropbox y con sample type `11` v3 en
  fechas donde coincidan.
- Verificar unidades, orden, timestamp, huecos, `errorEstimateMillis`,
  movimiento, skin contact y marcadores offline.
- Evaluar si PPI sirve como:
  - fallback Polar del RR matinal;
  - contexto de recuperacion;
  - fuente solo analitica.
- No incorporarlo a `build_hrv_core.py` sin actualizar tests y, si cambia la
  semantica HRV, `docs/contracts/`.

### Fase 5. Corte controlado

- Activar v4 primero para sleep y Nightly Recharge.
- Activar despues training sessions y enriquecimiento mecanico.
- Mantener fallback v3 temporal por feature flag.
- Ejecutar el sync completo tras redeploy con volumen persistente.
- Verificar que no cambian esquemas ni orden de columnas.

### Fase 6. Retirada v3

- Retirar registro de usuario y endpoints v3 solo tras cerrar la matriz de
  paridad.
- Eliminar credenciales, flags y adaptadores v3 obsoletos.
- Actualizar `AGENTS.MD`, variables Railway y documentacion operativa.
- Conservar rollback documentado durante al menos un ciclo de despliegue.

## Criterios de aceptacion

1. `/auth` usa v4 y valida `state`.
2. `/auth/callback` persiste el bundle v4 de forma atomica.
3. Un token expirado se renueva sin intervencion manual.
4. Los refresh tokens nunca aparecen en logs, errores HTTP ni `/api/status`.
5. Sleep y Nightly Recharge mantienen la cobertura y semantica del CSV
   canonico para el periodo de validacion acordado.
6. Las sesiones comunes a v3 y v4 mantienen fecha, hora, deporte, duracion y
   disponibilidad mecanica, o sus discrepancias quedan justificadas.
7. `/api/sync` y `/api/sync-sessions` mantienen exclusividad mutua.
8. Dropbox sigue siendo la primera fuente para cubrir RR faltantes.
9. PPI no entra en el gate HRV sin validacion especifica.
10. El sistema sigue funcionando tras redeploy de Railway con volumen.
11. Existe rollback probado a v3 mientras dure la ventana de transicion.
12. Se actualizan contratos solo si cambia la semantica o esquema HRV.

## Regression gate

- tests unitarios de authorization code, `state`, refresh y rotacion;
- tests de persistencia atomica y permisos del token file;
- tests de `401 -> refresh -> retry` con limite de un reintento;
- fixtures de normalizacion v3/v4 para sleep, nightly y sesiones;
- tests de consultas por rango y fechas limite;
- tests de matching de sesiones y cambios de zona horaria;
- tests de PPI con errores, movimiento y skin contact;
- smoke test de `/auth`, callback, `/api/status` y `/api/sync`;
- smoke test Railway con volumen y redeploy;
- verificacion de ausencia de secretos en logs.

## Riesgos

- reautorizacion obligatoria al cambiar scopes;
- campos v4 no equivalentes a `exercise.samples`;
- menor cobertura PPI segun dispositivo o tipo de medicion;
- payloads grandes al solicitar demasiadas features de sesiones;
- doble consumo de cuota durante shadow;
- token bundle incompatible con el formato actual;
- cambios de timezone o identificadores que degraden el matching;
- retirada prematura de v3 sin rollback real.

## Fuera de alcance

- convertir el proyecto en multiusuario;
- sustituir Dropbox RR sin evidencia;
- cambiar columnas canonicas;
- introducir un servicio MCP en el sync productivo;
- adoptar todos los scopes o endpoints v4;
- redisenar el metodo analitico de `analysis/`.

## Referencias

- Polar AccessLink Dynamic API v4:
  https://www.polar.com/polar-api-v4/
- Polar AccessLink API v3:
  https://www.polar.com/accesslink-api/
- Tarea MCP asociada:
  `AYO-14 Evaluar e integrar MCP para Polar v4`.
