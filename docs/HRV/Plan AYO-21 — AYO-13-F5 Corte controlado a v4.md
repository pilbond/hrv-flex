# Plan AYO-21 — AYO-13-F5 Corte controlado a v4

Estado: **PROPUESTA** (2026-06-14). No implementa nada; describe el plan de
desarrollo. Prioridad declarada: **simpleza, utilidad y buen funcionamiento por
encima de cualquier sobreingeniería.**

Documento padre: `docs/HRV/AYO-13 Migrar Polar AccessLink de v3 a v4.md` (Fase 5).
Matriz de paridad y gate cuantitativo: `docs/HRV/AYO-13-matriz-paridad-v3-v4.md`.

---

## 1. Veredicto rápido

AYO-21 es **viable y de riesgo acotado**, porque casi todo el trabajo difícil ya
está hecho en F0–F4:

- el cliente v4 (`polar_client_v4.py`), el OAuth+refresh (`polar_auth_v4.py`) y
  los adaptadores v4→interno (`polar_adapters_v4.py`) ya existen, aislados y con
  tests;
- el flag `POLAR_API_VERSION=v3|v4|shadow` ya existe en `config.py` y el runtime
  sin flag es idéntico al actual (rollback implícito);
- el modo `shadow` (F3) ya ejecuta lecturas v4 en paralelo y deja auditoría en
  `data/audit/polar_v4_shadow.jsonl`: tenemos un **gate empírico antes de cortar**;
- F4 quitó a Polar del camino de los RR matinales (Dropbox es la única fuente),
  así que **el corte v4 NO toca el gate HRV ni el `CORE`**. Solo afecta a:
  - `sleep.csv` (sidecar de sueño/nightly), y
  - el enriquecimiento mecánico de deportes de pie en `sessions_day` (`build_sessions.py`).

Lo único realmente nuevo que aporta F5 es una **frontera de dispatch** (el
gateway) y el **corte de sesiones**, que sí tiene dos dependencias reales
(catálogo de deporte y mapeo de samples mecánicos).

**Recomendación de alcance:** dividir F5 en dos sub-entregas independientes y
secuenciales:

- **F5.1 — Sleep/Nightly a v4** (firme, bajo riesgo, alto valor): cierra la
  continuidad OAuth real con refresh en producción.
- **F5.2 — Sesiones a v4** (acotada, opcional, detrás de su propio flag): solo si
  el catálogo de deporte y los samples mecánicos validan; si no, se difiere sin
  bloquear F5.1 ni F6.

---

## 2. Qué pide exactamente la tarjeta AYO-21

> `hrv_app/polar_gateway.py` (misma firma que `polar_client`, dispatch por flag,
> cache de rango sleep/nightly) + reimports en `sleep_store`, `hrv_sync_flow`,
> `polar_hrv_automation` y `PolarSessionClient` (token via gateway en v4). Corte
> escalonado: `POLAR_API_VERSION=v4` para sleep/nightly primero, `POLAR_V4_SESSIONS=1`
> después. Verificar esquemas CSV intactos tras sync completo. Rollback = flip de
> env var.

Cinco entregables: (1) gateway con misma firma + dispatch + cache; (2) reimports
en los consumidores; (3) token v4 a través del gateway; (4) corte escalonado por
flags; (5) verificación de esquemas + rollback documentado.

---

## 3. Superficie afectada (consumidores actuales de la frontera Polar)

| Consumidor | Llama hoy a | Para qué | Fuente de token hoy |
|---|---|---|---|
| `hrv_app/sleep_store.py::fetch_and_upsert_sleep` | `polar_client.fetch_polar_sleep`, `fetch_polar_nightly_recharge` (por fecha, con fallback al día anterior) | rellenar `ENDURANCE_HRV_sleep.csv` | token v3 que le pasa el orquestador |
| `polar_hrv_automation.py::main` | `polar_client.list_exercises` (**solo `--debug-sports`**), `register_user_if_needed` | diagnóstico de deportes / registro | `load_tokens()` v3 |
| `build_sessions.py` → `hrv_app/polar_sessions.py::PolarSessionClient` | `list_exercises`, `get_exercise_with_samples`, `extract_mechanical_metrics` | enriquecer mecánica (potencia/cadencia/velocidad) de deportes de pie en `sessions_day` | carga su propio token v3 de `TOKEN_FILE` |

Notas que condicionan el diseño:

- `sleep_store` pide **por fecha** y con **fallback al día anterior**
  (`_polar_sleep_date_candidates`), y `_default_sleep_refresh_dates()` devuelve
  `[hoy, hoy-1]`. En una sync típica hay **fechas solapadas** (p.ej. `hoy-1`
  aparece como candidato de `hoy` y como fecha propia). Aquí es donde el "cache
  de rango" tiene valor real: evitar repetir la misma llamada v4.
- v4 con `features` limita el rango a **1 día por petición** (confirmado en doc y
  captura F0). El `shadow` ya usa la forma validada `[día, día+1)` con features +
  `index_by_date().get(date)`. **El gateway debe reutilizar esa misma estrategia**
  (no inventar otra).
- En v4 el token NO es el token v3: viene del bundle v4 vía
  `polar_auth_v4.get_valid_access_token()`. Por eso la firma se mantiene
  (`fetch_polar_sleep(token, user_id, date)`) pero **en modo v4 el `token`
  recibido se ignora** y el gateway resuelve el suyo.

---

## 4. Diseño propuesto del gateway (`hrv_app/polar_gateway.py`)

Principio rector: **una sola frontera de dispatch, misma firma que `polar_client`,
cero lógica nueva de negocio.** El gateway solo decide "v3 o v4" y, en v4,
orquesta `V4Client` + adaptadores + cache. Toda la normalización ya vive en
`polar_adapters_v4.py`; el gateway no la duplica.

### 4.1 Funciones expuestas (idénticas a `polar_client`)

```text
fetch_polar_sleep(token, user_id, date_str)            -> Optional[dict]   # shape interno (v3)
fetch_polar_nightly_recharge(token, user_id, date_str) -> Optional[dict]
list_exercises(token)                                  -> list[dict]
get_exercise_with_samples(token, exercise_id)          -> dict
```

Los consumidores **solo cambian el import** (`from .polar_client import ...` →
`from .polar_gateway import ...`). El shape de salida es siempre el interno v3
que ya consumen `_extract_sleep_fields`, `_extract_nightly_fields`,
`match_polar_exercise` y `extract_mechanical_metrics`.

### 4.2 Dispatch por flag

```text
si config.POLAR_API_VERSION != "v4":   # "v3" y "shadow" operan en v3
    delega 1:1 en polar_client.*
si == "v4":
    sleep/nightly -> ruta v4 (siempre que F5.1 esté activa)
    sesiones      -> ruta v4 solo si POLAR_V4_SESSIONS está activo; si no, v3
```

`shadow` sigue siendo "v3 efectivo + lectura paralela v4 de auditoría": el
gateway lo trata como v3 (no cambia el comportamiento de F3).

### 4.3 Token en v4

- En v4, el gateway obtiene el access token con
  `polar_auth_v4.get_valid_access_token(config.TOKEN_FILE_V4)` (refresh proactivo
  ya implementado en F2). El `token` que llega por firma se ignora.
- Degradación: si no hay token v4 utilizable (bundle ausente, scopes
  insuficientes, refresh fallido), el gateway devuelve `None`/`[]` **igual que v3
  cuando falta token**. `sleep_store` ya trata `None` como "no se escribe fila":
  no rompe la sync. Esto preserva el criterio "el shadow/cutover nunca tumba
  `--process`".

### 4.4 Cache de rango sleep/nightly

Implementación mínima y suficiente:

- memo por proceso `dict[(domain, date_str) -> Optional[dict interno]]`.
- En miss v4: una sola petición `[día, día+1)` con features (misma forma que el
  shadow), `index_by_date()`, se cachean **todas** las fechas devueltas, se
  devuelve la pedida.
- Efecto: las fechas solapadas (`hoy`, `hoy-1`, candidatos de fallback,
  `new_dates` del CORE) colapsan a **una llamada por fecha real**, no N.
- Sin TTL ni invalidación: el cache vive lo que dura el proceso de sync. Para un
  N=1 con sync diario es lo correcto; añadir expiración sería sobreingeniería.

> Decisión a confirmar en implementación (no asumir): si el item de nightly trae
> `meanNightlyRecoveryRmssd/Rri/RespirationInterval` **sin** `features`, se podría
> pedir el rango completo (hasta 28 días) en una sola llamada. La matriz tiene una
> nota ambigua. **Recomendación pragmática:** arrancar replicando la estrategia
> ya validada del shadow (1 día con features) y solo optimizar a rango amplio si
> una captura real confirma que los means están en la respuesta base. Simpleza
> primero.

### 4.5 Sesiones v4 (F5.2, detrás de `POLAR_V4_SESSIONS`)

Es la parte con dependencias reales. Tres puntos:

1. **Catálogo de deporte (bloqueador nombrado en la matriz).** En v4 la sesión
   trae `sport.id` numérico, no el label. `extract_mechanical_metrics` y
   `match_polar_exercise` filtran por `detailed_sport_info` (`RUNNING`,
   `TRAIL_RUNNING`, `HIKING`…). Hay que cargar y **cachear** `/v4/sports/list`
   una vez y pasarlo como `sport_catalog` a `v4_session_to_internal()` (el
   adaptador ya acepta el parámetro). Sin catálogo, el filtro de deporte se
   degrada y cualquier sesión podría matchear.

2. **Samples mecánicos.** El adaptador hoy mapea RR, sport, duración y start,
   pero **no** los samples mecánicos. La matriz confirma que viven en
   `exercises[].samples.samples[] = {type, intervalMillis, values}`. Hay que
   extender `v4_session_to_internal()` para emitir los `samples` v3 que consume
   `extract_mechanical_metrics` (sample-type `1`=velocidad, `2`=cadencia,
   `4`=potencia, con `data` como CSV). Es trabajo de adaptador, acotado y
   testeable con fixtures.

3. **No hay endpoint de detalle en v4.** `list_training_sessions(from,to,features)`
   ya devuelve todo (incluidos samples) en una llamada. Por tanto, en v4:
   - `list_exercises(token)` → lista v4 de la ventana, adaptada a shape v3 con
     samples ya embebidos;
   - `get_exercise_with_samples(token, id)` → **lookup en cache**, sin segunda
     petición HTTP.
   - Como con features el rango es 1 día, el gateway debe **cachear por fecha**
     las sesiones (build_sessions itera muchos días → una llamada por fecha
     enriquecida, no por sesión).

`PolarSessionClient` se vuelve flag-aware: en v4, `available` se basa en el
bundle v4 y las llamadas `list_exercises`/`get_exercise_with_samples` delegan en
el gateway (el rate-limit ya lo hace `V4Client`).

---

## 5. Plan de ejecución por pasos

### Paso 0 — Preparación (sin código de producción)
- Refrescar la ventana `shadow` 7–14 días con datos reales y revisar
  `polar_v4_shadow.jsonl` contra el gate de la matriz (§8). Si sleep/nightly ya
  pasan en shadow, F5.1 es prácticamente confirmar lo observado.
- Confirmar el shape de `/v4/sports/list` con una captura (bloqueador de F5.2).

### F5.1 — Sleep/Nightly a v4
1. Crear `hrv_app/polar_gateway.py` con las 4 funciones, dispatch por flag, token
   v4 vía `get_valid_access_token`, y cache de rango para sleep/nightly. En esta
   sub-fase, `list_exercises`/`get_exercise_with_samples` delegan **siempre** en
   v3 (sesiones aún no se cortan).
2. Reapuntar imports: `sleep_store` → gateway. (Por consistencia,
   `polar_hrv_automation` y `PolarSessionClient` también importan del gateway,
   aunque su ruta siga siendo v3 hasta F5.2.)
3. Tests del gateway (§9), incluida la dedupe del cache y la degradación a `None`.
4. Validación operativa: sync completo con `POLAR_API_VERSION=v4`, verificar que
   `ENDURANCE_HRV_sleep.csv` mantiene **17 columnas, orden y semántica**, y que
   la cobertura/valores cumplen el gate frente a la ventana shadow previa.

### F5.2 — Sesiones a v4 (opcional, detrás de `POLAR_V4_SESSIONS`)
1. Cargar+cachear `/v4/sports/list` y pasar `sport_catalog` al adaptador.
2. Extender `v4_session_to_internal()` para emitir samples mecánicos v3.
3. Implementar la ruta v4 de `list_exercises`/`get_exercise_with_samples` en el
   gateway (lista por fecha con features + lookup en cache).
4. Hacer `PolarSessionClient` flag-aware.
5. Validación: `build_sessions.py --update/--backfill` con `POLAR_V4_SESSIONS=1`,
   verificar que `sessions_day.csv` mantiene esquema y que el match de sesiones
   cumple el gate (|Δstart|<20 min, mismo deporte mapeado).

### Paso final — Documentación y handoff a F6
- Actualizar `AGENTS.md`, `CLAUDE.md` y `docs/contracts/` **solo si** cambia
  semántica/esquema (no debería: el corte es de transporte).
- Documentar el procedimiento de rollback y dejar AYO-22 (F6) como retirada de v3
  una vez consumida la ventana de transición.

---

## 6. Corte escalonado y rollback

Estados operativos (4 combinaciones, todas válidas y testeables):

| `POLAR_API_VERSION` | `POLAR_V4_SESSIONS` | Sleep/Nightly | Sesiones |
|---|---|---|---|
| v3 / ausente | — | v3 | v3 |
| shadow | — | v3 (+ auditoría v4) | v3 |
| v4 | ausente/0 | **v4** | v3 |
| v4 | 1 | **v4** | **v4** |

- **Rollback = flip de env var.** `POLAR_API_VERSION=v3` revierte todo al runtime
  actual sin migración de datos (bundles separados: `.polar_tokens.json` v3,
  `.polar_tokens_v4.json` v4). `POLAR_V4_SESSIONS=0` revierte solo sesiones.
- Orden recomendado en Railway: `shadow` (ya disponible) → validar gate → `v4`
  (sleep/nightly) → validar → `v4 + POLAR_V4_SESSIONS=1` → validar.
- Conservar v3 operativo y el rollback documentado **al menos un ciclo de
  despliegue** (requisito de F6).

---

## 7. Gate de validación (reutiliza shadow + criterios de la matriz)

Ya definido en la matriz (§"Criterios cuantitativos de corte"); el plan lo
adopta tal cual:

- **Sleep/Nightly:** cobertura v4 ≥ v3 en la ventana (7–14 días); |Δrmssd| ≤ 1 ms;
  |Δduración| ≤ 5 min/noche.
- **Sesiones:** 100% de las sesiones v3 matcheadas encuentran sesión v4 con
  |Δstart| < 20 min y mismo deporte mapeado, o discrepancia justificada.
- **Operativo:** 0 refresh no recuperados en la ventana; latencia v4 no degrada
  la sync.

Ventaja clave: **el shadow ya produce estos números antes de cortar**. F5.1 no es
un salto a ciegas; es confirmar lo que el sidecar ya está midiendo.

---

## 8. Regression gate (tests)

Reaprovechar la suite v4 existente (`test_polar_client_v4_contract.py`,
`test_polar_adapters_v4.py`, `test_polar_auth_v4.py`, `test_polar_shadow_contract.py`,
`test_polar_v4_end_to_end.py`) y añadir, mínimos:

- **Gateway dispatch:** mismas entradas → v3 delega en `polar_client`; v4 usa
  `V4Client`+adaptador; `shadow` se comporta como v3.
- **Cache de rango:** dos lookups solapados (`hoy`, `hoy-1`) producen **una sola**
  llamada HTTP por fecha real.
- **Token v4 por gateway:** en v4 se usa el bundle v4 y se ignora el token v3 de
  firma; sin bundle utilizable → `None`/`[]` sin excepción.
- **Esquema intacto:** tras sync simulada en v4, `sleep.csv` mantiene
  `SLEEP_COLUMNS` (17) y, en F5.2, `sessions_day.csv` su esquema.
- **F5.2 adaptador mecánico:** fixture v4 con `exercises[].samples.samples[]` →
  `extract_mechanical_metrics` produce potencia/cadencia/velocidad equivalentes.
- **F5.2 catálogo:** `sport.id` → label v3 vía `sport_catalog`; sin catálogo, el
  filtro no matchea a ciegas.
- **Matriz de flags:** las 4 combinaciones de §6 arrancan y no rompen `--process`.

---

## 9. Ventajas

- **Reaprovecha casi todo:** cliente, OAuth/refresh, adaptadores y shadow ya
  existen y están testeados. F5 es sobre todo "cableado" + el corte de sesiones.
- **Riesgo desacoplado del gate HRV:** por F4, el corte no toca `CORE`,
  `BETA_AUDIT`, `FINAL` ni `DASHBOARD`. El peor caso afecta a `sleep.csv` (sidecar)
  y a la mecánica de `sessions_day`, ambos degradables.
- **Rollback trivial y verificable:** flip de env var, bundles separados, sin
  migración. Y un flag por dominio (sleep/nightly vs sesiones).
- **Decisión basada en evidencia:** el shadow mide el gate antes de cortar.
- **Continuidad OAuth real:** elimina el punto débil del token v3 (sin refresh
  operativo), que es el motivo de fondo de IU-02.
- **Cambio mínimo en consumidores:** solo cambian imports; la firma se conserva.

## 10. Inconvenientes y riesgos (con mitigación)

| Riesgo | Impacto | Mitigación |
|---|---|---|
| `/v4/sports/list`: shape no capturado todavía | Bloquea **F5.2** (no F5.1) | Captura previa en Paso 0; F5.2 es opcional y diferible |
| Samples mecánicos v4: mapeo nuevo en el adaptador | Mecánica de deportes de pie incorrecta si se mapea mal | Fixtures + test de equivalencia; flag separado permite no activarlo |
| Refresh v4 es el camino caliente (TTL ~12h) | Un refresh fallido = sin sleep/nightly ese día | Ya implementado y testeado en F2; degradación a `None` no rompe la sync; shadow lo ejercita |
| Ambigüedad nightly con/sin features | Llamadas de más o campos ausentes | Replicar estrategia validada del shadow; optimizar solo si captura lo confirma |
| Doble flag = 4 estados | Más superficie de prueba | Test explícito de la matriz de flags (§8) |
| Eficiencia: v4 sesiones es 1 llamada/día (features) | Más peticiones en `--backfill` largos | Cache por fecha en el gateway; rate-limit ya en `V4Client` |
| Micro-sesiones `BODY_AND_MIND` ≤10 min nunca capturadas en F0 | Bajo: por F4 los RR matinales vienen de Dropbox, no de Polar | No es bloqueante para F5; documentar y seguir |
| Doble consumo de cuota mientras conviven shadow/v3 | Cuota Polar | Cortar shadow al pasar a v4; ventana de transición acotada |

---

## 11. Fuera de alcance (de F5)

- Retirar endpoints/credenciales/registro v3 → es **F6 (AYO-22)**.
- Cambiar columnas canónicas o el método analítico.
- Meter PPI en el gate HRV o en `build_hrv_core.py`.
- Introducir MCP en el camino de `/api/sync` (eso es AYO-14/AYO-15).
- Convertir el proyecto en multiusuario.

---

## 12. Checklist de aceptación

1. Existe `hrv_app/polar_gateway.py` con la misma firma que `polar_client` y
   dispatch por `POLAR_API_VERSION` (+ `POLAR_V4_SESSIONS` para sesiones).
2. `sleep_store`, `hrv_sync_flow`, `polar_hrv_automation` y `PolarSessionClient`
   importan del gateway; ninguno importa `polar_client_v4`/adaptadores directamente.
3. Con `POLAR_API_VERSION=v4`, el token sale del bundle v4 (refresh transparente)
   y `sleep.csv` mantiene 17 columnas/orden/semántica tras sync completo.
4. El cache de rango colapsa fechas solapadas a una llamada por fecha real.
5. Con `POLAR_V4_SESSIONS=1`, `sessions_day.csv` mantiene esquema y el match de
   sesiones cumple el gate; sin el flag, las sesiones siguen en v3.
6. La degradación (sin token v4 / refresh fallido) no rompe `--process`.
7. Rollback probado: `POLAR_API_VERSION=v3` restaura el runtime actual.
8. Gate de la matriz (§7) cumplido y registrado a partir del shadow + sync v4.
9. Contratos (`docs/contracts/`) actualizados **solo si** cambia semántica/esquema.

---

## 13. Orden recomendado y esfuerzo aproximado

| Sub-fase | Contenido | Riesgo | Esfuerzo relativo |
|---|---|---|---|
| Paso 0 | Ventana shadow + captura `/v4/sports/list` | bajo | S |
| **F5.1** | Gateway + cache + reimports + sleep/nightly a v4 | bajo | M |
| **F5.2** | Catálogo deporte + samples mecánicos + sesiones a v4 | medio | M–L |
| Cierre | Validación de esquemas, docs, rollback documentado | bajo | S |

Recomendación: **entregar y estabilizar F5.1 antes de empezar F5.2.** F5.1 da el
valor principal (continuidad OAuth real) con riesgo mínimo; F5.2 puede diferirse
si el catálogo/mecánica resultan más caros de lo previsto, sin bloquear F6.

---

## 14. Decisiones abiertas a confirmar (no asumir)

1. ¿Nightly trae los means sin `features`? → define si el cache puede pedir rango
   amplio o se queda en 1 día/llamada. Default seguro: 1 día (como shadow).
2. Shape real de `/v4/sports/list` (bloqueador F5.2).
3. ¿Se activa F5.2 en este ciclo o se difiere? (afecta a la dependencia de AYO-22).
4. ¿Cortar `shadow` automáticamente al pasar a `v4`, o mantener ambos un tiempo
   asumiendo doble cuota?
