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
  así que el corte v4 no cambia la fuente RR ni la construcción de `CORE`.
  Sí afecta a:
  - `ENDURANCE_HRV_sleep.csv`, que es un output canónico y puede modificar
    `FINAL`/`DASHBOARD` cuando estos se regeneran;
  - el enriquecimiento mecánico de deportes de pie en `sessions.csv` y sus
    agregados/contextos derivados.

Lo realmente nuevo que aporta F5 es una **frontera de dispatch para
sleep/nightly**, la selección correcta de autenticación e identidad en el
entrypoint y `sleep_store`, y el **corte de sesiones** dentro de
`PolarSessionClient`. Este último tiene dos dependencias reales: catálogo de
deporte y mapeo de samples mecánicos.

**Recomendación de alcance:** dividir F5 en dos sub-entregas independientes y
secuenciales:

- **F5.1 — Sleep/Nightly a v4** (firme, bajo riesgo, alto valor): cierra la
  continuidad OAuth real con refresh en producción.
- **F5.2 — Sesiones a v4** (acotada, detrás de su propio flag): solo se activa
  si el catálogo de deporte y los samples mecánicos validan. Puede diferirse sin
  bloquear F5.1, pero **bloquea F6**, porque no se puede retirar v3 mientras
  `PolarSessionClient` siga dependiendo de sus endpoints.

---

## 2. Qué pide exactamente la tarjeta AYO-21

> Gateway mínimo `hrv_app/polar_gateway.py` solo para sleep/nightly, dispatch por
> `POLAR_API_VERSION` y sin caché inicial. En v4, el entrypoint no exige
> token/registro v3 y `sleep_store` consulta aunque `x_user_id` sea `None`.
> F5.2 añade catálogo, samples mecánicos y backend por fecha dentro de
> `PolarSessionClient`, detrás de `POLAR_V4_SESSIONS`. Verificar semántica,
> esquemas y rollback por flags.

Cinco entregables: (1) gateway mínimo para sleep/nightly; (2) selección correcta
del flujo de autenticación e identidad v3/v4; (3) backend v4 por fecha para
`PolarSessionClient`, incluido catálogo deportivo; (4) corte escalonado por
flags; (5) verificación de esquemas, semántica y rollback documentado.

---

## 3. Superficie afectada (consumidores actuales de la frontera Polar)

| Consumidor | Llama hoy a | Para qué | Fuente de token hoy |
|---|---|---|---|
| `hrv_app/sleep_store.py::fetch_and_upsert_sleep` | `polar_client.fetch_polar_sleep`, `fetch_polar_nightly_recharge` (por fecha, con fallback al día anterior) | rellenar `ENDURANCE_HRV_sleep.csv` | token v3 que le pasa el orquestador |
| `polar_hrv_automation.py::main` | `polar_client.list_exercises` (**solo `--debug-sports`**), `register_user_if_needed` | diagnóstico de deportes / registro | `load_tokens()` v3, actualmente obligatorio incluso con `POLAR_API_VERSION=v4` |
| `build_sessions.py` → `hrv_app/polar_sessions.py::PolarSessionClient` | `list_exercises`, `get_exercise_with_samples`, `extract_mechanical_metrics` | enriquecer mecánica (potencia/cadencia/velocidad) de deportes de pie en `sessions_day` | carga su propio token v3 de `TOKEN_FILE` |

Notas que condicionan el diseño:

- `sleep_store` pide **por fecha** y con **fallback al día anterior**
  (`_polar_sleep_date_candidates`), y `_default_sleep_refresh_dates()` devuelve
  `[hoy, hoy-1]`. Puede haber fechas solapadas, pero el volumen normal es pequeño
  y no justifica por sí solo introducir estado adicional.
- v4 con `features` limita el rango a **1 día por petición** (confirmado en doc y
  captura F0). El `shadow` ya usa la forma validada `[día, día+1)` con features +
  `index_by_date().get(date)`. **El gateway debe reutilizar esa misma estrategia**
  (no inventar otra).
- En v4 el token NO es el token v3: viene del bundle v4 vía
  `polar_auth_v4.get_valid_access_token()`. Por eso la firma se mantiene
  (`fetch_polar_sleep(token, user_id, date)`) pero **en modo v4 el `token`
  recibido se ignora** y el gateway resuelve el suyo.

---

## 4. Diseño propuesto

Principio rector: **usar una frontera común solo donde las interfaces v3 y v4
son realmente equivalentes.** El gateway decide v3/v4 para sleep/nightly y
orquesta `V4Client` + adaptadores. Toda la normalización vive en
`polar_adapters_v4.py`; el gateway no la duplica.

Las sesiones no deben forzarse dentro de la firma global v3: v4 requiere rango
temporal cuando se solicitan `features`, mientras que `list_exercises(token)` no
recibe fecha. Esa diferencia pertenece a `PolarSessionClient`, que sí conoce la
fila y fecha que está enriqueciendo.

### 4.1 Funciones expuestas por el gateway

```text
fetch_polar_sleep(token, user_id, date_str)            -> Optional[dict]   # shape interno (v3)
fetch_polar_nightly_recharge(token, user_id, date_str) -> Optional[dict]
```

`sleep_store` solo cambia el import (`from .polar_client import ...` →
`from .polar_gateway import ...`). El shape de salida sigue siendo el interno
v3 que consumen `_extract_sleep_fields` y `_extract_nightly_fields`.

### 4.2 Dispatch por flag

```text
si config.POLAR_API_VERSION != "v4":   # "v3" y "shadow" operan en v3
    delega sleep/nightly 1:1 en polar_client
si == "v4":
    sleep/nightly -> ruta v4
```

`shadow` sigue siendo "v3 efectivo + lectura paralela v4 de auditoría": el
gateway lo trata como v3 (no cambia el comportamiento de F3).

`shadow` y `v4` son modos mutuamente excluyentes. Al activar
`POLAR_API_VERSION=v4`, no se ejecuta el hook shadow al final del sync: repetiría
las mismas lecturas v4, consumiría cuota y no aportaría valor diagnóstico después
de superar el gate. Para volver a comparar antes de un rollback se cambia
explícitamente a `POLAR_API_VERSION=shadow`.

### 4.3 Autenticación y token en v4

- En v4, el gateway obtiene el access token con
  `polar_auth_v4.get_valid_access_token(config.TOKEN_FILE_V4)` (refresh proactivo
  ya implementado en F2). El `token` que llega por firma se ignora.
- `polar_hrv_automation.py::main` debe seleccionar el flujo de credenciales
  antes de registrar usuario:
  - `v3` y `shadow`: mantienen `load_tokens()` y `register_user_if_needed()`;
  - `v4`: no requieren token ni registro v3 para ejecutar el sync. El cliente
    v4 resuelve el bundle mediante refresh cuando hace una lectura.
- `sleep_store.fetch_and_upsert_sleep()` no puede condicionar la lectura v4 a
  que exista `user_id`. En v3 mantiene el guard histórico; en v4 llama al
  gateway aunque `x_user_id` sea `None`, porque los endpoints v4 están asociados
  al bearer token.
- `--debug-sports` queda en la ruta v3 durante F5.1. Su migración se realiza en
  F5.2, cuando ya existe el backend de sesiones v4 y puede definirse una ventana
  diagnóstica explícita, por ejemplo los últimos 7 días.
- Degradación: si no hay token v4 utilizable (bundle ausente, scopes
  insuficientes, refresh fallido), el gateway devuelve `None`. `sleep_store` ya
  trata `None` como "no se escribe fila", por lo que la ausencia de sleep no
  rompe `--process`. El fallo debe quedar visible en logs sin secretos.

### 4.4 Consultas sleep/nightly

Implementación mínima:

- cada lookup v4 realiza una petición `[día, día+1)` con features, igual que el
  shadow, y selecciona la fecha mediante `index_by_date()`;
- no se introduce caché inicialmente: el sync normal consulta pocas fechas y la
  simplicidad pesa más que ahorrar alguna llamada duplicada;
- si la instrumentación demuestra duplicación relevante, se puede añadir
  memoización dentro de una instancia creada por job. No se permite un
  diccionario global persistente en el proceso Flask;
- no optimizar nightly sin `features`: la matriz vigente establece que
  `features` es obligatorio para obtener datos.

### 4.5 Sesiones v4 (F5.2, detrás de `POLAR_V4_SESSIONS`)

Es la parte con dependencias reales. Tres puntos:

1. **Catálogo de deporte (bloqueador nombrado en la matriz).** En v4 la sesión
   trae `sport.id` numérico, no el label. `extract_mechanical_metrics` y
   `match_polar_exercise` filtran por `detailed_sport_info` (`RUNNING`,
   `TRAIL_RUNNING`, `HIKING`…). Hay que cargar y **cachear** `/v4/sports/list`
   una vez y pasarlo como `sport_catalog` a `v4_session_to_internal()` (el
   adaptador ya acepta el parámetro). Sin catálogo, el filtro de deporte se
   degrada y cualquier sesión podría matchear.
   `V4Client` debe incorporar explícitamente `list_sports()` para
   `/v4/sports/list`; el catálogo se carga una vez por instancia de
   `PolarSessionClient`.

2. **Samples mecánicos.** El adaptador hoy mapea RR, sport, duración y start,
   pero **no** los samples mecánicos. La matriz confirma que viven en
   `exercises[].samples.samples[] = {type, intervalMillis, values}`. Hay que
   extender `v4_session_to_internal()` para emitir los `samples` v3 que consume
   `extract_mechanical_metrics` (sample-type `1`=velocidad, `2`=cadencia,
   `4`=potencia, con `data` como CSV). Es trabajo de adaptador, acotado y
   testeable con fixtures.

3. **No hay endpoint de detalle en v4.** `list_training_sessions(from,to,features)`
   ya devuelve todo, incluidos samples. Por tanto, `PolarSessionClient` debe
   exponer internamente una operación por fecha:
   - `list_exercises_for_date(date_str)` pide `[día, día+1)` con features,
     adapta las sesiones y las cachea en la instancia;
   - el detalle con samples se resuelve por id dentro de esa lista, sin segunda
     petición HTTP;
   - `enrich_row()` obtiene primero la fecha de la fila y consulta únicamente
     esa ventana.

`PolarSessionClient` se vuelve flag-aware: en v4, `available` se basa en la
existencia de un bundle v4 utilizable o refrescable, usa `V4Client` y mantiene
un cache por instancia/ejecución. No debe delegar las sesiones en el gateway de
sleep/nightly ni conservar `list_exercises(token)` como abstracción falsa.

---

## 5. Plan de ejecución por pasos

### Paso 0 — Preparación (sin código de producción)
- Refrescar la ventana `shadow` 7–14 días con datos reales y revisar
  `polar_v4_shadow.jsonl` contra el gate de la matriz (§7).
- Para sleep/nightly, ampliar o procesar el sidecar para calcular explícitamente
  cobertura, `Δrmssd` y `Δduración`; no asumir que el JSONL ya emite el gate
  agregado.
- Confirmar el shape de `/v4/sports/list` con una captura (bloqueador de F5.2).
- Añadir una comparación específica de sesiones v3/v4 que mida timestamp,
  duración y deporte. El shadow actual solo registra presencia, conteo y RR, por
  lo que no demuestra todavía el gate de matching.

### F5.1 — Sleep/Nightly a v4
1. Crear `hrv_app/polar_gateway.py` solo con sleep/nightly y dispatch por flag.
2. Reapuntar únicamente `sleep_store` al gateway.
3. Corregir `polar_hrv_automation.py` para que el modo v4 no cargue ni registre
   obligatoriamente credenciales v3.
4. Corregir el guard de `sleep_store`: en modo v4 debe consultar aunque
   `x_user_id` sea `None`.
5. Tests del gateway, entrypoint e identidad de sleep, incluida degradación a
   `None`.
6. Validación operativa: sync completo con `POLAR_API_VERSION=v4`, verificar que
   `ENDURANCE_HRV_sleep.csv` mantiene **17 columnas, orden y semántica**, y que
   `FINAL`/`DASHBOARD` se regeneran correctamente con los valores v4.

### F5.2 — Sesiones a v4 (opcional, detrás de `POLAR_V4_SESSIONS`)
1. Añadir `V4Client.list_sports()`, cargar `/v4/sports/list` una vez por
   instancia y pasar `sport_catalog` al adaptador.
2. Extender `v4_session_to_internal()` para emitir samples mecánicos v3.
3. Hacer `PolarSessionClient` flag-aware e implementar su backend v4 por fecha,
   con lookup por id dentro del cache de la instancia.
4. Mantener el backend v3 actual sin modificar su semántica.
5. Migrar `--debug-sports` a sesiones v4 con una ventana diagnóstica explícita.
6. Validación: `build_sessions.py --update/--backfill` con `POLAR_V4_SESSIONS=1`,
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
- Al pasar a `v4`, el shadow queda desactivado automáticamente por la propia
  selección de modo. No se mantienen lecturas shadow paralelas en producción.
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

El shadow aporta la materia prima de sleep/nightly, pero el gate debe calcularse
y registrarse explícitamente. Para sesiones hace falta ampliar la comparación:
el shadow actual no valida timestamp, duración ni deporte.

---

## 8. Regression gate (tests)

Reaprovechar la suite v4 existente (`test_polar_client_v4_contract.py`,
`test_polar_adapters_v4.py`, `test_polar_auth_v4.py`, `test_polar_shadow_contract.py`,
`test_polar_v4_end_to_end.py`) y añadir, mínimos:

- **Gateway dispatch:** mismas entradas → v3 delega en `polar_client`; v4 usa
  `V4Client`+adaptador; `shadow` se comporta como v3.
- **Token v4 por gateway:** en v4 se usa el bundle v4 y se ignora el token v3 de
  firma; sin bundle utilizable → `None` sin romper el pipeline.
- **Entrypoint v4 independiente de v3:** `POLAR_API_VERSION=v4` puede ejecutar
  `--process` sin bundle v3 ni `register_user_if_needed`.
- **Identidad sleep v4:** con `x_user_id=None`, sleep/nightly siguen llamando al
  gateway en modo v4; en v3 se conserva el guard histórico.
- **Esquema intacto:** tras sync simulada en v4, `sleep.csv` mantiene
  `SLEEP_COLUMNS` (17) y, en F5.2, `sessions_day.csv` su esquema.
- **F5.2 adaptador mecánico:** fixture v4 con `exercises[].samples.samples[]` →
  `extract_mechanical_metrics` produce potencia/cadencia/velocidad equivalentes.
- **F5.2 catálogo:** `sport.id` → label v3 vía `sport_catalog`; sin catálogo, el
  filtro no matchea a ciegas.
- **F5.2 cliente de catálogo:** `V4Client.list_sports()` usa el endpoint correcto
  y el catálogo se carga una vez por instancia.
- **F5.2 rango:** cada `enrich_row()` consulta/cachea la fecha de su fila y no
  depende de una lista global sin rango.
- **Matriz de flags:** las 4 combinaciones de §6 arrancan y no rompen `--process`.

---

## 9. Ventajas

- **Reaprovecha casi todo:** cliente, OAuth/refresh, adaptadores y shadow ya
  existen y están testeados. F5 es sobre todo "cableado" + el corte de sesiones.
- **Fuente RR desacoplada:** por F4, el corte no cambia los RR de entrada ni la
  construcción de `CORE`. Sleep sigue siendo canónico y puede cambiar
  `FINAL`/`DASHBOARD`, por lo que debe validarse semánticamente.
- **Rollback trivial y verificable:** flip de env var, bundles separados, sin
  migración. Y un flag por dominio (sleep/nightly vs sesiones).
- **Decisión basada en evidencia:** el shadow mide el gate antes de cortar.
- **Continuidad OAuth real:** elimina el punto débil del token v3 (sin refresh
  operativo), que es el motivo de fondo de IU-02.
- **Cambio mínimo donde aplica:** `sleep_store` cambia de import;
  `PolarSessionClient` conserva su API pública (`enrich_row`) y encapsula la
  diferencia temporal v4 en su implementación.

## 10. Inconvenientes y riesgos (con mitigación)

| Riesgo | Impacto | Mitigación |
|---|---|---|
| `/v4/sports/list`: shape no capturado todavía | Bloquea **F5.2** (no F5.1) | Captura previa en Paso 0; F5.2 es opcional y diferible |
| Samples mecánicos v4: mapeo nuevo en el adaptador | Mecánica de deportes de pie incorrecta si se mapea mal | Fixtures + test de equivalencia; flag separado permite no activarlo |
| Refresh v4 es el camino caliente (TTL ~12h) | Un refresh fallido = sin sleep/nightly ese día | Ya implementado y testeado en F2; degradación a `None` no rompe la sync; shadow lo ejercita |
| Doble flag = 4 estados | Más superficie de prueba | Test explícito de la matriz de flags (§8) |
| Eficiencia: v4 sesiones es 1 llamada/día (features) | Más peticiones en `--backfill` largos | Cache por fecha en `PolarSessionClient`; rate-limit ya en `V4Client` |
| Entry point exige token v3 en modo v4 | El corte no funciona sin credenciales legacy | Seleccionar autenticación antes de `load_tokens`/registro |
| `sleep_store` exige `user_id` | En v4 no se ejecutan lecturas aunque exista bundle | Guard dependiente de versión; v4 consulta por bearer token |
| Micro-sesiones `BODY_AND_MIND` ≤10 min nunca capturadas en F0 | Bajo: por F4 los RR matinales vienen de Dropbox, no de Polar | No es bloqueante para F5; documentar y seguir |
| Doble consumo de cuota durante la validación en `shadow` | Cuota Polar | Ventana previa acotada; al activar `v4`, shadow deja de ejecutarse |

---

## 11. Fuera de alcance (de F5)

- Retirar endpoints/credenciales/registro v3 → es **F6 (AYO-22)**.
- Cambiar columnas canónicas o el método analítico.
- Meter PPI en el gate HRV o en `build_hrv_core.py`.
- Introducir MCP en el camino de `/api/sync` (eso es AYO-14/AYO-15).
- Convertir el proyecto en multiusuario.

---

## 12. Checklist de aceptación

1. Existe `hrv_app/polar_gateway.py` con las funciones de sleep/nightly y
   dispatch por `POLAR_API_VERSION`.
2. `sleep_store` importa del gateway. `hrv_sync_flow` no se modifica salvo que
   aparezca una dependencia Polar real.
3. Con `POLAR_API_VERSION=v4`, el entrypoint no exige token ni registro v3; el
   token sale del bundle v4 mediante refresh transparente.
4. `sleep.csv` mantiene 17 columnas/orden/semántica y `FINAL`/`DASHBOARD` se
   regeneran correctamente tras sync completo.
5. En modo v4, sleep/nightly funcionan con `x_user_id=None`; en v3 se conserva
   el comportamiento histórico.
6. Con `POLAR_V4_SESSIONS=1`, `sessions_day.csv` mantiene esquema y el match de
   sesiones cumple el gate; sin el flag, las sesiones siguen en v3.
7. `PolarSessionClient` consulta v4 por fecha y resuelve samples por id desde su
   cache de instancia, sin simular `list_exercises(token)` global.
8. `V4Client.list_sports()` alimenta un catálogo cargado una vez por instancia.
9. La degradación (sin token v4 / refresh fallido) no rompe `--process`.
10. Rollback probado: `POLAR_API_VERSION=v3` restaura el runtime actual.
11. Con `POLAR_API_VERSION=v4` no se ejecutan lecturas shadow adicionales.
12. Gate de la matriz (§7) cumplido y registrado con comparación explícita.
13. Contratos (`docs/contracts/`) actualizados **solo si** cambia semántica/esquema.

---

## 13. Orden recomendado y esfuerzo aproximado

| Sub-fase | Contenido | Riesgo | Esfuerzo relativo |
|---|---|---|---|
| Paso 0 | Ventana shadow + captura `/v4/sports/list` | bajo | S |
| **F5.1** | Gateway sleep/nightly + auth/identidad del runtime | bajo-medio | M |
| **F5.2** | Catálogo + samples + backend por fecha en PolarSessionClient | medio | M–L |
| Cierre | Validación de esquemas, docs, rollback documentado | bajo | S |

Recomendación: **entregar y estabilizar F5.1 antes de empezar F5.2.** F5.1 da el
valor principal (continuidad OAuth real) con riesgo mínimo; F5.2 puede diferirse
si el catálogo/mecánica resultan más caros de lo previsto, pero F6 no puede
comenzar hasta que F5.2 esté implementada y validada.

---

## 14. Decisiones abiertas a confirmar (no asumir)

1. Shape real de `/v4/sports/list` (bloqueador F5.2).
2. ¿Se activa F5.2 en este ciclo o se difiere? Si se difiere, AYO-22 permanece
   bloqueada.
