# Core Audit Fix 02 — Estado real del pipeline

## Objetivo

Propagar el resultado de cada etapa del sync HRV hasta el entrypoint y la UI
para que un fallo de CORE, de integridad/escritura de sleep, FINAL/DASHBOARD,
Dropbox RR o auto-restore no termine como `exit 0` ni como una sincronización
correcta en `/api/status`.

El resultado debe distinguir tres situaciones:

- `ok`: la cadena canónica requerida terminó correctamente;
- `degraded`: la cadena canónica es válida, pero falló una etapa opcional;
- `failed`: falló una etapa requerida o no se pudo determinar de forma fiable
  el estado de una fuente obligatoria.

## Diagnóstico técnico del estado actual

### 1. El runner descarta la causa del fallo

`hrv_app/pipeline_runner.py` ejecuta los builders con `check=True`, pero
`_run_python_script()` convierte tanto un script ausente como cualquier
`CalledProcessError` en `None`. Los wrappers posteriores reducen de nuevo el
resultado a `bool` o `CompletedProcess | None`.

Consecuencias:

- se pierde la etapa, el `returncode` y una representación estructurada del
  error;
- CORE y FINAL no comparten un contrato de resultado;
- el orquestador solo puede decidir mediante `None` o `False`.

### 2. El flujo absorbe fallos canónicos

`hrv_app/hrv_sync_flow.py` devuelve `None` en todos los caminos. Si CORE falla,
el flujo muestra un aviso, actualiza sleep, intenta wellness y retorna sin
propagar el fallo. Si FINAL falla, el flujo continúa con SSM, wellness y el
resumen final. También hay caminos sin RR o sin fechas pendientes que terminan
sin indicar por qué no se procesó una medición.

Consecuencia: el caller no puede diferenciar éxito, degradación, ausencia
normal de RR o fallo canónico.

### 3. Dropbox mezcla ausencia de datos y error de fuente

`hrv_app/dropbox_rr.py::_run_dropbox_rr_import_for_dates()` devuelve únicamente
`(mapa_rr, cantidad_nueva)`. Configuración ausente, script ausente, timeout y
error del conversor terminan devolviendo el mismo tipo de resultado que una
ejecución correcta sin pares para las fechas solicitadas.

Consecuencia: un fallo de infraestructura se presenta como «no hay RR».

### 4. El entrypoint siempre respalda y devuelve éxito

Después de `sync_hrv_range()`, `polar_hrv_automation.py` ejecuta el backup y
devuelve `0`. Como el flujo no devuelve estado, el entrypoint no puede impedir
el backup de una generación canónica fallida ni producir un código no cero.

### 5. La UI solo conoce el código del proceso

`web_ui.py::_run_subprocess_job()` reduce el resultado del subprocess a
`returncode == 0`. El estado en memoria expone `success`, stdout y stderr, pero
no etapa, rango de fechas, estado de fuente ni degradaciones. `POST /api/sync`
es asíncrono: su `202` solo confirma que el job arrancó; el resultado terminal
se obtiene posteriormente mediante `/api/status`.

### 6. Cobertura de tests existente

Los tests actuales cubren ejecuciones correctas de los builders y varios
caminos del flujo, pero no verifican el contrato extremo a extremo. En
particular, el test de fallo de CORE valida actualmente el comportamiento que
esta tarea debe retirar: actualizar sleep y wellness y terminar sin error
propagado. Tampoco hay cobertura del resultado estructurado entre el proceso
CLI y el estado web.

## Alcance

- `hrv_app/pipeline_runner.py`: resultado estructurado de cada subprocess.
- `hrv_app/dropbox_rr.py`: estado explícito de la fuente Dropbox RR.
- `hrv_app/hrv_sync_flow.py`: agregación y propagación del resultado.
- `polar_hrv_automation.py`: código de salida, serialización y gate de backup.
- `web_ui.py`: consumo del resultado y exposición por `/api/status`.
- Tests unitarios, de contrato e integración del flujo anterior.

El auto-restore previo al sync sí entra en CAF-02 porque su fallo debe llegar al
exit code y a `/api/status`. El restore manual y la atomicidad de generaciones
pertenecen a CAF-03.

## Fuera de alcance

- hacer transaccional el conjunto completo de canónicos;
- versionar generaciones, hashes o manifests de backup;
- cambiar la lógica HRV, sus columnas, QA o gating;
- persistir historial de jobs tras reiniciar el proceso web;
- modificar el contrato de `sync-sessions`;
- resolver autenticación, autorización o exposición general de `/api/status`.

La publicación atómica por generación corresponde a CAF-03/CAF-06. CAF-02
solo garantiza que el resultado observado sea verdadero y se propague.

## Contrato de resultado

Debe existir un único tipo interno, por ejemplo `PipelineResult`, utilizado por
runner, flujo, entrypoint y adaptador web. Puede implementarse con dataclasses,
`TypedDict` o tipos equivalentes, pero su representación JSON debe conservar
como mínimo:

```json
{
  "status": "ok | degraded | failed",
  "success": true,
  "canonical_valid": true,
  "stage": "complete",
  "date_from": "2026-07-14",
  "date_to": "2026-07-15",
  "processed_dates": ["2026-07-15"],
  "uncovered_dates": ["2026-07-14"],
  "pending_sleep_dates": ["2026-07-14"],
  "source": {
    "name": "dropbox_rr",
    "status": "ok",
    "outcome": "data_found | no_data | not_requested | local_coverage"
  },
  "error": null,
  "degraded_stages": [],
  "stages": []
}
```

Reglas del contrato:

- `success` es un derivado: `true` para `ok` y `degraded`; `false` para
  `failed`.
- `canonical_valid` solo es `true` si todas las etapas canónicas requeridas en
  ese camino terminaron correctamente.
- `stage` identifica la última etapa ejecutada o la etapa que causó el fallo.
- `date_from` y `date_to` representan el rango solicitado; pueden ser `null` en
  modos sin rango.
- `processed_dates` contiene fechas realmente incorporadas o reprocesadas.
- `uncovered_dates` contiene fechas solicitadas para las que una consulta
  correcta no encontró RR; no representa errores de fuente.
- `pending_sleep_dates` contiene fechas de CORE que siguen sin sueño utilizable
  tras el intento del ciclo y que entrarán en la ventana de reintento.
- `error` es `null` salvo en `failed` y contiene `code`, `message` y, cuando
  proceda, `returncode`. No debe contener secretos ni volcar variables de
  entorno.
- `degraded_stages` enumera fallos opcionales mediante `stage`, `code` y
  `message` sanitizado.
- `stages` permite conservar la trazabilidad de las etapas ejecutadas sin
  obligar a inferirla desde stdout.

Los nombres exactos del tipo Python pueden variar, pero no la semántica ni los
campos mínimos del JSON.

## Catálogo de etapas

Valores previstos para `stage`:

- `preflight`;
- `auto_restore`;
- `dropbox_rr`;
- `core`;
- `sleep`;
- `final_dashboard`;
- `ssm_shadow`;
- `ai_daily`;
- `ai_ssm`;
- `intervals_wellness`;
- `backup`;
- `complete`.

No es necesario ejecutar todas las etapas en cada modo. Una etapa no requerida
debe constar como `not_requested` o no aparecer en `stages`; nunca debe
presentarse como correcta si no se ejecutó.

## Orden y activación de auto-restore

La comprobación de auto-restore forma parte de `preflight` y ocurre antes de
calcular fechas pendientes o consultar `dropbox_rr` en cada sync. No convierte
la restauración en una etapa habitual del pipeline:

1. `preflight` evalúa la condición existente de `auto_restore_if_empty()`.
2. Solo se intenta restaurar si `HRV_AUTO_RESTORE_ON_EMPTY_DATA=1` y CORE no
   tiene filas utilizables (ausente, vacío o ilegible según la implementación
   actual).
3. Si se intenta, `auto_restore` aparece en `stages`. Un resultado parcial o
   fallido es `failed` y aborta antes de Dropbox.
4. Si no se intenta porque el dataset es utilizable o la función está
   deshabilitada, `auto_restore` no aparece en `stages`; no se fabrica una
   etapa correcta que no se ejecutó.
5. Tras una restauración correcta se relee el estado de CORE y solo entonces
   se calcula el rango y se consulta Dropbox si aún procede.

CAF-02 no cambia la condición de IU-14 ni convierte un restore manual en
auto-restore. El endpoint `POST /api/restore-backup` continúa bajo CAF-03.

## Semántica y reintento de sleep

Sleep es contexto canónico, pero no participa en el gate ni en la acción HRV.
Por ello, la ausencia temporal de publicación en Polar no invalida CORE ni
impide generar FINAL/DASHBOARD. Debe distinguirse de un fallo que comprometa
el archivo canónico local.

Cada resultado de la etapa `sleep` debe exponer `status` y `outcome`:

| Situación | `sleep.status` | `sleep.outcome` | Resultado global |
|---|---|---|---|
| Se guardó al menos señal de sueño o nightly | `ok` | `data_found` | continúa |
| Polar respondió correctamente, pero no hay sleep ni nightly tras probar fecha exacta y día anterior | `pending` | `no_data_yet` | `degraded` |
| Consulta Polar con error de red, autenticación o API | `pending` | `request_error` | `degraded` |
| `sleep.csv` existente ilegible, esquema inválido o escritura atómica fallida | `failed` | `integrity_error` o `write_error` | `failed` |

El gateway debe dejar de reducir «sin dato» y «fallo de consulta» al mismo
`None`; la etapa necesita un resultado de fetch estructurado para clasificarlos.
La ausencia de Nightly Recharge por sí sola no deja el sleep pendiente si hay
una señal de sueño utilizable, porque Nightly es enriquecimiento opcional.

### Ventana de reintento

No se persiste una cola nueva ni se modifica el esquema de `sleep.csv`. En cada
sync se deriva `pending_sleep_dates` cruzando CORE con sleep y se reintentan
las fechas con CORE válido pero sin señal de sleep utilizable dentro de una
ventana móvil de **siete días naturales**, incluido hoy.

Los objetivos efectivos de sleep son la unión, sin duplicados, de:

1. fechas nuevas incorporadas a CORE en el ciclo;
2. la refrescada ordinaria de hoy y ayer;
3. fechas pendientes de la ventana de siete días.

Una fecha sale de `pending_sleep_dates` cuando se guarda una señal utilizable.
Una fecha más antigua que la ventana no se reintenta automáticamente: queda
ausente como contexto histórico y requiere una acción explícita de backfill si
se necesitara. Así se evita consultar a Polar todo el histórico en cada sync.

## Semántica de Dropbox RR

Para evitar que «sin datos» oculte un fallo, la fuente expone dos dimensiones:

- `source.status`: `not_requested`, `ok` o `failed`;
- `source.outcome`: `not_applicable`, `data_found`, `no_data`, `disabled`,
  `configuration_error`, `credentials_error`, `timeout`, `converter_error` o
  `unexpected_error`.

Reglas:

1. Una consulta que termina correctamente pero no encuentra pares para las
   fechas solicitadas produce `source.status=ok`, `outcome=no_data` y no falla
   el sync por sí sola.
2. Si solo cubre parte del rango tras una ejecución correcta, se procesan las
   fechas cubiertas y el resto se incluye en `uncovered_dates`.
3. Timeout, credenciales, configuración o conversor fallido producen
   `source.status=failed` y resultado global `failed` cuando Dropbox era
   necesario para resolver fechas nuevas.
4. Los archivos parciales generados por una ejecución que termina con timeout
   o error no se promocionan ni se procesan como si la fuente hubiese terminado
   correctamente.
5. En `--all`, Dropbox no se consulta y debe figurar como `not_requested`.
6. Si todas las fechas objetivo ya existen localmente o en CORE, Dropbox no es
   obligatorio para ese ciclo y no se fabrica un fallo de fuente. En ese caso
   la fuente queda como `source.status=not_requested` y
   `source.outcome=local_coverage`, para distinguir cobertura local de una
   consulta Dropbox que devolvió datos.

## Matriz de criticidad

| Etapa o situación | Resultado global | Exit code | ¿Backup remoto? | Continuación permitida |
|---|---|---:|---|---|
| Auto-restore requerido falla o queda parcial | `failed` | distinto de 0 | no | no iniciar sync |
| Dropbox responde correctamente con RR | continúa | pendiente | pendiente | sí |
| Dropbox responde correctamente sin RR | `ok` si el resto requerido termina | 0 | sí, si se regeneró/validó la cadena canónica | sí |
| Dropbox timeout/credenciales/config/conversor | `failed` | distinto de 0 | no | no procesar parciales |
| CORE falla o no devuelve resultado válido | `failed` | distinto de 0 | no | no sleep, FINAL, SSM, wellness ni backup |
| Polar aún no publica sleep/nightly | `degraded` | 0 | sí | FINAL sin ese contexto; reintentar durante 7 días |
| Consulta Polar de sleep falla | `degraded` | 0 | sí | FINAL sin ese contexto; visible como error de fuente |
| `sleep.csv` ilegible o escritura atómica falla | `failed` | distinto de 0 | no | no FINAL, SSM, wellness ni backup |
| FINAL/DASHBOARD falla | `failed` | distinto de 0 | no | no SSM, briefs, wellness ni backup |
| SSM shadow falla | `degraded` | 0 | sí | sí |
| IA daily/SSM falla | `degraded` | 0 | sí | sí |
| Intervals wellness falla | `degraded` | 0 | sí | sí |
| Backup falla después de canónicos válidos | `degraded` | 0 | ya intentado | finalizar con aviso |
| `--process` no solicitado | `ok` si su trabajo solicitado termina | 0 | no | no exigir builders |

Una etapa opcional solo puede degradar un resultado cuyo
`canonical_valid=true`; nunca puede transformar un fallo canónico en éxito.

## Flujo de propagación esperado

1. `preflight` evalúa el auto-restore condicional antes de Dropbox. Si llega a
   intentarse y falla, devuelve `failed` sin iniciar el sync de RR.
2. El runner devuelve un resultado de etapa sin capturar el fallo como
   `None`. Conserva `returncode` y mensajes sanitizados.
3. Dropbox devuelve cobertura y estado de fuente en el mismo resultado.
4. Las fechas de sleep se forman uniendo fechas nuevas, refresco ordinario y
   pendientes de los últimos siete días. Una ausencia temporal o error remoto
   de sleep degrada, pero una falla de integridad/escritura aborta.
5. `sync_hrv_range()` devuelve siempre `PipelineResult`, incluidos los caminos
   «sin fechas pendientes», «sin RR» y `--all`.
6. El flujo se detiene en el primer fallo requerido. Las etapas opcionales
   posteriores no se ejecutan con canónicos stale.
7. `main()` ejecuta backup únicamente con `canonical_valid=true` y solo cuando
   el modo ejecutado autoriza backup.
8. El resultado del backup se incorpora al resultado global como `ok` o
   degradación opcional.
9. El entrypoint emite una representación JSON inequívoca para el proceso
   padre y devuelve código `0` para `ok/degraded` y no cero para `failed`.
10. La UI consume esa representación, la guarda en `execution_state` y la
   expone sin reconstruir la causa desde texto libre.

## Transporte CLI → UI

El canal de máquina queda fijado a stdout. Al terminar cualquier ejecución del
job HRV, el entrypoint emite exactamente una línea JSON compacta con este
prefijo literal:

```text
##HRV_RESULT##{"status":"ok",...}
```

La aplicación la emite con `flush=True` como su última línea controlada. No se
usa un archivo temporal: el resultado es pequeño, la UI ya captura stdout y un
archivo añadiría ciclo de vida, permisos, limpieza y una segunda superficie de
fallo sin aportar persistencia requerida por CAF-02.

Reglas:

- el JSON ocupa una única línea y cumple el contrato anterior;
- solo el job HRV exige este marcador; no se cambia implícitamente el job de
  sesiones;
- el parser de la UI recorre stdout desde el final y exige exactamente un
  marcador válido. No presupone que sea físicamente la última línea porque
  código externo podría escribir después;
- cero, más de uno o JSON inválido se consideran incumplimiento del contrato;
- código no cero sin marcador válido se representa como `failed` con
  `error.code=process_failed_without_result`;
- código cero sin marcador válido se representa como `failed` con
  `error.code=process_result_contract_invalid`;
- discrepancia entre código de salida y JSON se resuelve de forma fail-closed:
  prevalece `failed`;
- stdout/stderr continúan disponibles para diagnóstico técnico, pero el estado
  funcional no se deduce de ellos;
- un cierre anormal del intérprete que impida emitir el marcador seguirá siendo
  detectable por la ausencia del resultado y el código no cero.

## Contrato de `/api/sync` y `/api/status`

`POST /api/sync` mantiene su comportamiento asíncrono:

- `202` significa «job aceptado/iniciado», no «sync completado»;
- si el job termina dentro de la espera corta actual, puede devolver el estado
  terminal sin alterar su semántica;
- la verdad terminal vive en `/api/status`.

Cuando no hay job en curso, `/api/status` debe exponer, además de los campos de
compatibilidad existentes:

- `running`;
- `success`;
- `job_type`;
- `pipeline_status`;
- `pipeline_stage`;
- `pipeline_date_from` y `pipeline_date_to`;
- `processed_dates`, `uncovered_dates` y `pending_sleep_dates`;
- `source_status` y `source_outcome`;
- `pipeline_error` estructurado;
- `degraded_stages`;
- `last_run`.

`pipeline_result` conserva el payload terminal completo para diagnóstico; los
aliases planos anteriores son el contrato estable consumido por la UI.

El estado puede seguir siendo en memoria en CAF-02. Después de un reinicio no
se promete conservar el último job. Los mensajes expuestos por API deben estar
sanitizados; tokens, secretos, headers y credenciales nunca forman parte del
resultado estructurado.

## Estrategia de implementación

1. Introducir el tipo de resultado y helpers para `ok`, `degraded` y `failed`.
2. Migrar `pipeline_runner.py` sin cambiar todavía el orden del flujo.
3. Migrar Dropbox a resultado explícito y retirar la tupla ambigua.
4. Dar a la ingesta de sleep resultados estructurados, derivar pendientes y
   aplicar la ventana de reintento de siete días.
5. Hacer que `_process_rr_files()`, `_refresh_sleep_and_outputs()` y
   `sync_hrv_range()` devuelvan y combinen resultados.
6. Aplicar el fail-fast de etapas requeridas y el gate de wellness/backup.
7. Serializar el resultado en el entrypoint y mapearlo a exit code.
8. Parsearlo en `web_ui.py` y exponer los campos estables en `/api/status`.
9. Actualizar tests existentes y añadir la batería de integración.

## Plan de pruebas mínimo

### Runner

- script ausente conserva `stage` y error específico;
- `CalledProcessError` conserva `returncode` y no retorna `None`;
- éxito conserva stdout sin perder el estado estructurado;
- CORE y FINAL usan el mismo contrato.

### Dropbox

- ejecución correcta con datos;
- ejecución correcta sin datos;
- cobertura parcial correcta;
- integración deshabilitada cuando era necesaria;
- carpeta/script/configuración ausente;
- timeout;
- credenciales rechazadas;
- conversor con código no cero;
- ningún parcial se promociona tras timeout/error.

### Orquestador y entrypoint

- CORE fallido produce `failed`, no ejecuta etapas posteriores, no hace backup
  y devuelve código no cero;
- sleep aún no publicado produce `degraded`, genera FINAL y deja la fecha como
  pendiente;
- error remoto de sleep produce `degraded` y es distinguible de `no_data_yet`;
- `sleep.csv` ilegible o una escritura de sleep fallida produce fail-fast;
- una fecha pendiente recibe sleep tres días después y se completa en el sync
  posterior dentro de la ventana de siete días;
- una fecha pendiente fuera de la ventana no provoca consultas históricas
  ilimitadas;
- FINAL fallido produce el mismo fail-fast;
- SSM, IA, Intervals o backup fallidos producen `degraded` y código cero;
- Dropbox sin datos produce `ok` si las demás etapas requeridas terminan;
- error de Dropbox requerido produce código no cero;
- `--all` no exige Dropbox;
- ejecución sin `--process` no exige CORE/FINAL ni dispara backup;
- auto-restore fallido llega al resultado terminal;
- auto-restore correcto se completa antes de calcular el rango o consultar
  Dropbox;
- dataset utilizable o auto-restore deshabilitado no añade una etapa
  `auto_restore` ficticia;
- el JSON terminal y el exit code nunca se contradicen.

### API

- `POST /api/sync` sigue devolviendo `202` mientras el job corre;
- un CORE/FINAL/Dropbox fallido termina con `success=false` en
  `/api/status`;
- `/api/status` identifica etapa, rango y error estructurado;
- una degradación opcional conserva `success=true` y
  `pipeline_status=degraded`;
- un marcador `##HRV_RESULT##` válido se consume aunque una librería haya
  escrito texto después;
- cero, varios o un marcador JSON inválido se tratan como fallo de contrato;
- el payload no contiene secretos;
- los campos previos necesarios para la UI siguen disponibles.

Los tests de integración deben partir al menos una vez de `POST /api/sync`,
esperar o ejecutar el worker controladamente y verificar el estado terminal de
`/api/status`; no basta con probar funciones aisladas.

## Criterios de aceptación

1. Un fallo de CORE, de integridad/escritura de sleep o de FINAL/DASHBOARD produce `success=false`,
   `pipeline_status=failed` y código no cero.
2. Timeout, credenciales, configuración o conversor Dropbox fallido quedan
   visibles como fallo de fuente, nunca como «sin RR».
3. Una consulta Dropbox correcta sin RR queda visible como
   `source_status=ok`, `source_outcome=no_data` y no falla por sí sola.
4. `/api/status` identifica etapa, rango de fechas, error y degradaciones.
5. Ningún backup remoto se ejecuta después de un resultado canónico fallido.
6. SSM, IA, Intervals y backup conservan semántica best effort y degradan sin
   invalidar canónicos válidos.
7. Los parciales de Dropbox no se procesan después de timeout o error.
8. El restore manual parcial no se declara resuelto por CAF-02; queda cubierto
   explícitamente por CAF-03.
9. El resultado terminal CLI usa exactamente un marcador
   `##HRV_RESULT##` JSON válido; su ausencia, duplicidad o contradicción con el
   exit code falla de forma cerrada.
10. Auto-restore se intenta solo desde preflight cuando aplica y antes de
    Dropbox; no aparece como etapa cuando no se ejecuta.
11. Sleep no publicado todavía o con error remoto queda como degradación
    visible, no bloquea FINAL, y se reintenta durante siete días; un fallo de
    integridad o escritura de `sleep.csv` sí bloquea el pipeline.
12. Existen tests de integración desde `POST /api/sync` hasta
   `/api/status` para éxito, degradación y fallo.
13. Toda la suite sigue siendo compatible con Python 3.11.

## Riesgos y decisiones pendientes

- La atomicidad entre CORE, sleep y FINAL no queda resuelta hasta CAF-03/CAF-06;
  CAF-02 evita anunciar o respaldar como válida una ejecución fallida.
- Los logs humanos pueden seguir siendo extensos. El resultado API debe usar
  mensajes sanitizados y acotados, dejando el detalle técnico fuera del
  contrato funcional.
- `success=true` para `degraded` preserva la idea de que los canónicos son
  utilizables. Los consumidores que necesiten distinguirlo deben consultar
  `pipeline_status`.
- Si durante la implementación aparece una etapa canónica adicional, debe
  clasificarse explícitamente en la matriz antes de incorporarla; no se asume
  `best effort` por defecto.
