# AYO-13 — Matriz de paridad Polar AccessLink v3 / Dynamic API v4

Estado: **CERRADA — 2026-06-18.** v3 retirado por completo en AYO-22 (F6). Este documento es referencia histórica de la migración.

## Actualización 2026-06-16 (validación operativa real de F5.2)

- **Catálogo de deportes validado en real**: el endpoint operativo es
  `GET /v4/data/sports/list`, no `/v4/sports/list`.
- **Scope requerido confirmado**: `sports:read` es obligatorio para ese
  endpoint. Con un bundle sin ese scope, la API responde
  `{"errorMessage":"Missing required scope: sports:read"}`.
- **Shape real del catálogo**: el identificador puede venir anidado como
  `identifier: {id: ...}` en vez de `id` escalar. El parser debe soportar
  ambas variantes.
- **Sesiones reales validadas con catálogo**: ids observados como `1`,
  `27`, `126` se resolvieron correctamente a `RUNNING`, `TRAIL_RUNNING` y
  `CORE`.
- **Samples mecánicos reales validados**: en sesiones reales de running y
  trail, `exercises[].samples.samples[].type` aparece como string
  (`SPEED`, `CADENCE`) y no solo como enum numérico `1/2/4`. El adaptador
  debe aceptar ambos shapes.
- **Resultado operativo**: con `POLAR_API_VERSION=v4` y
  `POLAR_V4_SESSIONS=1`, el matching por fecha/deporte funciona y la capa
  mecánica mínima canónica para deportes de pie queda alimentada en sesiones
  reales sin tocar outputs persistidos durante la validación.

## Actualización 2026-06-12 (segunda revisión externa): confirmado en doc oficial

- **`features` es obligatorio para obtener datos**: sin `features` las
  respuestas de sleeps/nightly/ppi solo contienen fechas. Con `features` el
  rango se limita a **1 día por petición**. La captura F0 hace dos pasadas:
  rango sin features (índice) + por-día con features (datos completos).
- **Nightly Recharge usa doble wrapper**:
  `{"nightlyRechargeResults": {"nightlyRechargeResults": [...]}}`; campos
  `sleepResultDate`, `meanNightlyRecoveryRmssd`, `meanNightlyRecoveryRri`,
  `meanNightlyRecoveryRespirationInterval` (intervalo, no frecuencia).
- **Sleep anida**: `sleepResult.hypnogram.sleepStart/sleepEnd`,
  `sleepScore` es objeto (`sleepScore.sleepScore`), `sleepEvaluation` con
  `analysis` (continuityIndex/continuityClass), `phaseDurations`
  (deep/rem/light) e `interruptions`.
- **Training sessions**: id en `identifier`, deporte como objeto `sport`,
  `startTime`/`stopTime`, `duration` en **milisegundos** y lista anidada
  `exercises[]` (donde viven los `rrSamples`). **No existe endpoint de
  detalle** `/training-sessions/{id}`: el enriquecimiento se pide con
  `features` sobre `/list`.
- **PPI**: wrapper `dailyPpiSamples[]` → `ppiSamplesPerDevice[]` →
  `ppiSamples[]` con `offsetMillis`, `ppInterval`, `errorEstimateMillis`,
  `skinContact`, `movement`, `offline`. Feature: `samples`.
- Los fixtures de `tests/fixtures/polar_v4/` siguen estos shapes oficiales,
  pero siguen siendo **sintéticos**: la captura real F0 los sustituye.
- Nombres exactos de `features` por endpoint: **confirmados en swagger**
  (ver actualización de la sexta revisión más abajo).

## Actualización 2026-06-12 (tercera revisión externa): swagger oficial

- **RR samples** viven en `exercises[].samples.rrSamples[]` con cada
  intervalo en `{durationMillis, offline}`. El adaptador lee este camino
  como ruta principal (los shapes planos quedan como fallback).
- **`sport` es solo `{id: "22353647432"}`** (referencia numérica al
  catálogo `/v4/data/sports/list`). No hay `name` en la respuesta de sesiones.
  Sin catálogo, el adaptador devuelve el id crudo en `detailed-sport-info`;
  con `sport_catalog` opcional resuelve a label v3 (BODY_AND_MIND, TRAIL_RUNNING…).
  **Bloqueador F5:** cargar y cachear `/v4/data/sports/list` antes del corte para
  que el filtro de deportes del pipeline siga funcionando.
- **Features oficiales** (kebab-case): `/sleeps` admite `sleep-result`,
  `original-sleep-result`, `sleep-score`, `sleep-evaluation`;
  `/nightly-recharge-results` admite `samples`; `/tests/list` admite
  `samples`; `/training-sessions/list` enumera (confirmado en swagger):
  `samples`, `test-results`, `training-load-report`, `laps`, `hill-splits`,
  `routes`, `statistics`, `zones`, `pause-times`,
  `strength-training-results`, `comments`, `physical-info`.
- **TrainingSession** usa `durationMillis` a nivel superior (no `duration`);
  el adaptador lo prioriza y lo convierte a ISO 8601 para el shape v3.
- **Anonimizador**: ahora cubre `id`, sufijo `*Id` (sportId, exerciseId,
  routeId, favoriteId, organizationId, trainingTargetId, …), objetos
  anidados `sport.id`/`trainingTarget.id`/`favoriteTarget.id`, UUIDs en
  cualquier string, coordenadas (`latitude/longitude/route/location`) y
  texto libre (`name`, `note`, `description`, `comment`, `title`).
- **Refresh entre procesos**: además del `threading.Lock` intra-proceso,
  se usa un lockfile `O_CREAT|O_EXCL` con TTL de 60s para evitar que dos
  procesos quemen refresh tokens en paralelo.

## Actualización 2026-06-12 (cuarta revisión externa): adaptador sueño y /api/status v4

- **`phaseDurations.{deep,rem,light}` como objeto**: el esquema oficial puede
  devolver `{"durationMillis": N}` en lugar de un número plano. El adaptador
  (`v4_sleep_to_internal`) ahora extrae `durationMillis`/`seconds`/`minutes`/`value`
  del objeto antes de pasarlo a `sleep_store`, que solo sabe interpretar
  números o duraciones ISO. Cubierto por
  `test_phase_durations_as_objects_with_duration_millis`.
- **Bundle "refresh-only" en `/api/status`**: si el bundle v4 no tiene
  `access_token` pero sí `refresh_token`, `_token_diagnostics_v4()` ahora
  reporta `token_reason="refreshable"` (antes `"missing_access_token"`,
  contradiciendo que `get_valid_access_token()` lo renueva solo).
- **`token_expired` dentro del margen de refresco**: `bundle_needs_refresh()`
  se activa también ~120s antes de la expiración real (`REFRESH_SKEW_SEC`).
  `_token_diagnostics_v4()` ahora distingue "necesita refresh" de "expirado de
  verdad": `token_expired` solo es `True` si `obtained_at + expires_in <= now`
  (o no hay `expires_in`).
- **Modo shadow ciego al bundle v4**: `_token_diagnostics()` en modo
  `shadow` ahora añade `token_v4` con el diagnóstico completo del bundle v4
  (sin tokens), sin alterar el payload v3/default (`api_version` solo se
  añade fuera de `v3`, como antes).

## Actualización 2026-06-12 (quinta revisión externa): robustez de la captura F0 y cliente v4

- **Canónico vacío descartaba días con datos**: la selección de fixture
  canónico (`sleeps.json`, `training_sessions_list.json`, ...) ahora exige
  que el payload contenga al menos un item real (`_payload_has_items`,
  búsqueda recursiva de listas no vacías), no solo "sin error". Antes podía
  fijar `{"trainingSessions": []}` del día más reciente y descartar otro día
  de la ventana `--feature-days` que sí tenía sesiones con RR.
- **Fixture obsoleto sin aviso**: si ningún día de la ventana produce items
  para un dominio, el script ya NO sobreescribe ni borra el `<nombre>.json`
  existente; imprime un aviso y escribe `<nombre>.CAPTURE_STALE.txt` para que
  sea imposible pasar por alto que el fixture quedó desactualizado.
- **`_range_params()` ahora hace cumplir "features ⇒ rango ≤ 1 día"**: si
  `features` viene con un rango `from`/`to` de más de un día, `V4Client`
  lanza `PolarV4Error` antes de la petición HTTP (falla por contrato, no con
  un 400 de red). Rango de 1 día o fechas no-ISO (p.ej. tests con `"a"`/`"b"`)
  no se validan y siguen funcionando igual que antes.

## Actualización 2026-06-12 (auto-revisión): semántica de scopes y robustez

- **`make_bundle()` distingue exchange de refresh** (RFC 6749): si la
  respuesta de token omite `scope`, en un **refresh** se conservan los
  scopes ya persistidos (el grant no cambió), pero en un **exchange**
  (authorization_code) la omisión significa "idéntico a lo solicitado".
  Antes, re-autorizar con scopes ampliados podía heredar los scopes viejos
  del bundle previo y dejar la app en bucle de re-auth.
- **`fetch_ppi_samples()` devuelve day-objects sin aplanar**: el shape
  oficial es `dailyPpiSamples[]` → `ppiSamplesPerDevice[]` → `ppiSamples[]`.
  El consumidor de F4 debe aplanar dos niveles; el cliente F1 es solo
  transporte y no lo hace.
- Captura F0: el marcador `CAPTURE_STALE.txt` se limpia al regenerar el
  canónico; el anonimizador elimina también coordenadas con prefijo
  (`startLatitude`, `endLongitude`, `maxAltitude`); throttle aplicado
  también en respuestas de error.
- Adaptador de sesiones: el fallback de RR por exercise solo se usa si la
  ruta oficial (`samples.rrSamples`) no dio valores (evita duplicados).

## Actualización 2026-06-12 (sexta revisión externa): duraciones protobuf y features confirmadas

- **Duraciones de sueño como string protobuf**: el swagger declara
  `phaseDurations.{deep,rem,light}` como `int64` (ms), pero los **ejemplos
  oficiales** de `/sleeps` devuelven strings estilo protobuf-Duration
  (`"90s"`, `"5460s"`, `"28800s"` en sleepGoal, `"220s"` en interruptions).
  El adaptador normaliza `"Ns"` → ISO `PT{N}S` (un número plano se leería
  como minutos por la heurística de `sleep_store`). Hasta la captura real,
  asumir que el runtime devuelve el formato de los ejemplos.
- **Bundle corrupto no tumba el diagnóstico**: `obtained_at`/`expires_in`
  no numéricos se tratan como 0 (`_safe_float`) → el bundle se clasifica
  como refrescable/expirado en vez de lanzar `ValueError` hacia el refresh
  o `/api/status` (500).
- **`/tests/list` admite `features=samples`** (swagger): la captura F0 ahora
  lo pide; sin él no se capturan los samples de tests pese a `tests:read`.
- **Features de `/training-sessions/list` confirmadas** (ya no provisional):
  `samples`, `test-results`, `training-load-report`, `laps`, `hill-splits`,
  `routes`, `statistics`, `zones`, `pause-times`,
  `strength-training-results`, `comments`, `physical-info`. Nota F5: hay
  `statistics`/`zones`/`laps` — candidatos para los samples mecánicos
  (speed/cadence/power) que el corte de sesiones necesita evaluar.

## Actualización 2026-06-12 (séptima revisión externa): offline RR, sport snake, lock de exchange

- **Flag `offline` por RR preservado**: el swagger marca `offline: boolean`
  como required en cada `trainingsessionRRSample`. El shape v3
  (`{"sample-type":"11","data":"rr1,rr2"}`) no tiene canal para él, así que
  el adaptador añade una máscara paralela `"offline": "0,1,0,..."` (misma
  longitud que `data`). **Contrato F5:** el gateway debe fusionarla (OR) con
  el chequeo fisiológico de rango de `extract_rr_ms` — offline=1 de Polar es
  la primera capa de descarte de artefactos aunque el RR caiga en 300–2000ms.
- **`transitionRrSamples` incluidos**: en sesiones multideporte los RR de
  transición (mismo schema) se anexan tras los RR de cada exercise.
- **Sport en kebab y snake**: `polar_sessions.match_polar_exercise` y
  `polar_sport_raw` leen `detailed_sport_info` (snake) directamente; el
  adaptador emite ambas variantes para que el filtro de deportes no se
  salte en silencio (sport vacío ⇒ cualquier sesión matchea).
- **Exchange bajo lock**: `persist_authorized_bundle()` guarda el bundle del
  callback OAuth bajo el mismo `_REFRESH_LOCK` + lockfile que el refresh;
  una rotación en vuelo ya no puede sobrescribir el grant recién autorizado.
  Si el lock no se libera en el timeout, el exchange persiste igualmente
  (es el dato más autoritativo).
- **Sueño autoritativo**: el adaptador mapea `sleepEvaluation.asleepDuration`
  → `asleep_duration`, `sleepSpan` → `sleep_span` y
  `analysis.efficiencyPercent` → `efficiency` (todos confirmados en
  swagger; las duraciones llegan como strings protobuf `"25200s"` y se
  normalizan a ISO). `sleep_store` los usa en vez de recalcular desde fases.
- **Errores de red tipados**: `V4Client._do_get` envuelve
  `requests.RequestException` en `PolarV4Error` (Timeout/ConnectionError ya
  no se propagan crudos).
- **XSS en página de error del callback**: `str(e)` ahora se escapa antes de
  insertarse en HTML (un `error_description` del token endpoint podía
  contener markup).
- **Captura local con `state`**: `capture_v4_fixtures.py` genera state
  anti-CSRF, lo valida contra el callback y aborta si no coincide.

## Actualización 2026-06-12 (octava revisión externa): cierre del circuito offline y OAuth

- **`extract_rr_ms` consume la máscara `offline`**: el flag de Polar ya no
  se pierde en el consumidor — se fusiona (OR) con el chequeo fisiológico
  de rango. Un RR 300–2000ms marcado offline=true queda como artefacto.
  Cambio retrocompatible: los samples v3 no traen la máscara y mantienen el
  comportamiento histórico. (Esto adelanta a F1/F2 el contrato que estaba
  anotado para el gateway F5.)
- **El exchange ya no escribe sin lock**: `persist_authorized_bundle()` usa
  timeout > TTL de lock huérfano (la adquisición está garantizada: un
  refresh vivo libera en segundos, uno muerto se rompe a los 60s); si aun
  así no se obtiene, lanza `PolarAuthV4Error` en vez de arriesgar que un
  refresh en vuelo restaure credenciales antiguas.
- **`save_json_atomic` con tmp único**: el nombre temporal incluye
  pid+uuid; dos escritores concurrentes ya no colisionan sobre el mismo
  `.tmp` (el `replace` final sigue siendo atómico).
- **Un 2xx sin `access_token` es error**: `_token_request` valida que la
  respuesta del token endpoint contenga `access_token`; antes un 200 vacío
  se persistía como bundle sin credenciales y el callback reportaba éxito.

## Actualización 2026-06-12 (novena revisión externa): sin bundles híbridos

- **El exchange ya no hereda `refresh_token` previo**: en `make_bundle()` la
  herencia de refresh_token queda limitada a rotaciones (`refresh=True`).
  Un authorization_code crea un grant nuevo; heredar el refresh del grant
  anterior (posiblemente revocado) producía un bundle híbrido
  access-nuevo/refresh-viejo. `x_user_id` sí se sigue preservando en ambos
  casos.

## Confirmado por documentación oficial

| Aspecto | v3 | v4 | Estado |
|---|---|---|---|
| Registro de app | admin.polaraccesslink.com | **misma app y credenciales** | confirmado (doc) |
| Authorization | flow.polar.com/oauth2/authorization | auth.polar.com/oauth/authorize | confirmado (doc) |
| Token | polarremote.com/v2/oauth2/token | auth.polar.com/oauth/token (también refresh) | confirmado (doc) |
| Scope | `accesslink.read_all` | granulares (`sleep:read`, `nightly_recharge:read`, `training_sessions:read`, `ppi_data:read`, …) | confirmado (doc) |
| Access token TTL | larga (años) | ~12 h (`expires_in: 43199`) | confirmado (doc) |
| Refresh token | no existe | obligatorio (`grant_type=refresh_token`, Basic auth) | confirmado (doc) |
| Base de datos API | www.polaraccesslink.com/v3 | www.polaraccesslink.com/v4/data | confirmado (doc) |
| Registro usuario (POST /users) | obligatorio (XML) | no documentado | **confirmar con prueba real** |
| `x_user_id` en token response | sí | no aparece (`jti` en su lugar) | **confirmar con prueba real** |
| Rango sleeps | n/a (por fecha) | `?from&to`, máx 30 días | confirmado (doc) |
| Rango nightly | n/a (por fecha) | `?from&to`, máx 28 días sin features | confirmado (doc) |
| Rango PPI | n/a | `?from&to`, máx 90 días sin features | confirmado (doc) |
| RR en sesiones | `/exercises/{id}?samples=true`, sample-type 11 | `trainingsessionRRSample` en training-sessions | **confirmar shape con captura** |

## Endpoints

| Dominio | v3 | v4 |
|---|---|---|
| Sesiones (lista) | `GET /v3/exercises` | `GET /v4/data/training-sessions/list` |
| Sesión + samples | `GET /v3/exercises/{id}?samples=true` | `GET /v4/data/training-sessions/list?features=...` (no hay endpoint de detalle) |
| Sueño | `GET /v3/users/sleep/{date}` | `GET /v4/data/sleeps?from&to` |
| Nightly Recharge | `GET /v3/users/nightly-recharge/{date}` | `GET /v4/data/nightly-recharge-results?from&to` |
| PPI | (sample type 11 dentro de exercises) | `GET /v4/data/ppi-samples?from&to` |
| Tests | n/a | `GET /v4/data/tests/list?from&to` |

## Sleep — campo a campo

Modelo interno = claves v3 snake_case que consume `sleep_store._extract_sleep_fields`.

| Interno (v3) | v4 real (ruta) | Estado |
|---|---|---|
| `date` | `sleepDate` | ✅ confirmado |
| `sleep_start_time` | `sleepResult.hypnogram.sleepStart` (ISO con offset) | ✅ confirmado |
| `sleep_end_time` | `sleepResult.hypnogram.sleepEnd` | ✅ confirmado |
| `deep_sleep` | `sleepEvaluation.phaseDurations.deep` (string protobuf `"5070s"`) | ✅ confirmado |
| `rem_sleep` | `sleepEvaluation.phaseDurations.rem` | ✅ confirmado |
| `light_sleep` | `sleepEvaluation.phaseDurations.light` | ✅ confirmado |
| `asleep_duration` / `sleep_span` | `sleepEvaluation.asleepDuration` / `sleepSpan` (protobuf `"Ns"`) | ✅ confirmado (autoritativos: ganan sobre recalc de fases) |
| `efficiency` | `sleepEvaluation.analysis.efficiencyPercent` | ✅ confirmado |
| `continuity` | `sleepEvaluation.analysis.continuityIndex` | ✅ confirmado |
| `continuity_class` | `sleepEvaluation.analysis.continuityClass` | ✅ confirmado |
| `sleep_score` | `sleepScore.sleepScore` (objeto anidado) | ✅ confirmado |
| `evaluation.interruptions` | `sleepEvaluation.interruptions.{longCount,totalCount}` | ✅ confirmado |

Wrapper real: `{"nightSleeps": [ ... ]}`. Las duraciones llegan como **string
protobuf `"Ns"`** (`"5070s"`), no como ms ni ISO; el adaptador las normaliza a
`PT...S`. El shape es **profundamente anidado** (hypnogram / sleepScore /
sleepEvaluation), no plano: el adaptador ya lo cubre vía rutas con punto.

## Nightly Recharge — campo a campo

| Interno (v3) | v4 real (ruta) | Estado |
|---|---|---|
| `date` | `sleepResultDate` | ✅ confirmado |
| `heart_rate_variability_avg` | `meanNightlyRecoveryRmssd` | ✅ confirmado |
| `nightly_rri` | `meanNightlyRecoveryRri` (directo, no derivado de HR) | ✅ confirmado |
| `breathing_rate_avg` | `meanNightlyRecoveryRespirationInterval` (intervalo→brpm; `0` en la captura ⇒ sin valor) | ✅ confirmado |
| — | `ansStatus`, `recoveryIndicator`, `hrvSamples[]`, `breathingRateSamples[]` | nuevos en v4, sin consumidor |

Wrapper real: **simple** `{"nightlyRechargeResults": [ ... ]}` (no doble
wrapper). No hay `heartRateAvg` en el item; el RRI medio viene directo en
`meanNightlyRecoveryRri`. El cliente tolera ambos wrappers vía `_extract_items`.

## Training sessions — campo a campo

Modelo interno = claves kebab-case v3 que consumen `match_polar_exercise` y
`extract_mechanical_metrics`.

| Interno (v3) | v4 real (ruta) | Estado |
|---|---|---|
| `id` | `identifier` (string en la captura anonimizada; `sport.id` es dict anidado) | ✅ confirmado |
| `start-time` | `startTime` (ISO, p.ej. `2025-06-12T11:37:28`) | ✅ confirmado |
| `detailed-sport-info` | `sport.id` (dict `{"id": ...}`, requiere catálogo de deporte) | ✅ confirmado |
| `duration` (ISO8601) | `durationMillis` (ms → el adaptador genera `PT...`) | ✅ confirmado |
| capa mecánica (speed/cadence/power) | `exercises[].samples.samples[]` = `{type, intervalMillis, values}` | ✅ confirmado (v4 SÍ expone samples mecánicos; desbloquea `POLAR_V4_SESSIONS`) |
| `samples` type 11 (RR) | `exercises[].samples.rrSamples[]` = `{durationMillis}` | ✅ confirmado |

Wrapper real: `{"trainingSessions": [ ... ]}`. La sesión trae métricas de
cabecera (`distanceMeters`, `calories`, `hrAvg/hrMax`, `ascentMeters/descentMeters`
en el exercise, `runningIndex`, `recoveryTimeMillis`, `timezoneOffsetMinutes`).

⚠️ **`rrSamples` NO trae el flag `offline`** en la captura real (solo
`durationMillis`). El adaptador lo defaultea a `0` y el chequeo fisiológico de
rango de `extract_rr_ms` sigue marcando artefactos. Validación empírica F0
(2026-06-12, sesión real de 1h15): 10 794 RR extraídos, 125 marcados como
artefacto por rango. La máscara `offline` del adaptador queda como extensión
forward-compatible (PPI sí trae el flag, ver abajo).

**Fixture**: `training_sessions_list.json` se mantiene como fixture controlado
(2 deportes para tests de mapeo) — ya **confirmado estructuralmente** idéntico
al real. La captura real (2.6 MB, 1 sesión, `sport.id` anonimizado a `ANON_ID`)
no se versiona: es inservible para mapeo de deporte y demasiado grande.

## PPI samples — campo a campo

Wrapper real: `{"dailyPpiSamples": [{date, modified, ppiSamplesPerDevice: [{recordingDevice, ppiSamples: [...]}]}]}`.

| Campo PPI | Tipo | Nota |
|---|---|---|
| `offsetMillis` | int | offset desde inicio del registro diario |
| `ppInterval` | int (ms) | intervalo pulso-a-pulso (lo lee el adaptador vía `ppInterval`/`ppi`) |
| `errorEstimateMillis` | int | estimación de error del intervalo |
| `skinContact` | bool | contacto con piel |
| `movement` | bool | movimiento detectado |
| `offline` | bool | **PPI SÍ trae el flag offline** (a diferencia de rrSamples de training-sessions) |

## Incógnitas que cierra la captura real (F0)

1. ✅ `/v4/data/*` funciona sin registro de usuario; el token response trae `x_user_id` (scopes concedidos incluyen los cinco solicitados).
2. ✅ Wrappers reales: `nightSleeps` (lista), `nightlyRechargeResults` (lista, wrapper **simple**), `dailyPpiSamples`. `trainingSessions` pendiente de re-captura.
3. ✅ Duraciones de sueño: **string protobuf `"Ns"`** (segundos), no ms ni ISO. El adaptador normaliza a `PT...S`.
4. ⏳ Micro-sesiones `BODY_AND_MIND` ≤10 min: la ventana capturada (2026-06-11..13) no incluyó ninguna; no contradice su existencia. Pendiente de una captura con una micro-sesión real.
   - Igual aclaración para `tests_list`: el `.CAPTURE_STALE.txt` indica que la ventana no incluyó ninguna prueba (fitness/ortostática), **no** un fallo del capturador. El endpoint responde 200; simplemente no había items.
5. ✅ Samples mecánicos: v4 SÍ los expone en `exercises[].samples.samples[]` (`{type, intervalMillis, values}`). Desbloquea `POLAR_V4_SESSIONS`.
6. ✅ Semántica PPI: `ppInterval`+`errorEstimateMillis`+`skinContact`+`movement`+`offline` por muestra, agrupadas por día y por dispositivo. PPI **sí** trae `offline` (training-sessions rrSamples no).

## Bug de contrato confirmado en F0 (2026-06-13): datetime en training-sessions

`/v4/data/training-sessions/list` rechaza `from`/`to` en formato fecha pura
(`YYYY-MM-DD`) con 400 `"Value for key 'from' could not be parsed as
datetime"`, mientras que `/sleeps`, `/nightly-recharge-results`,
`/ppi-samples` y `/tests/list` sí aceptan fecha pura. Solución aplicada:
promover el rango a `YYYY-MM-DDT00:00:00` solo para ese endpoint, tanto en el
script de captura (`_range_params_for`) como en el cliente productivo
(`V4Client._as_datetime_bound`). Tests de regresión en
`test_polar_client_v4_contract.py` (`test_training_sessions_promotes_date_to_datetime`,
`test_other_endpoints_keep_date_only`).

## Criterios cuantitativos de corte (gate F5)

- Sleep/nightly: cobertura v4 ≥ cobertura v3 en la ventana shadow (7–14 días); |Δrmssd| ≤ 1 ms; |Δduración| ≤ 5 min por noche.
- Sesiones: 100% de las sesiones v3 matcheadas encuentran sesión v4 con |Δstart| < 20 min y mismo deporte mapeado, o discrepancia justificada.
- Operativo: 0 errores de refresh no recuperados durante la ventana; latencia v4 no degrada el sync.
