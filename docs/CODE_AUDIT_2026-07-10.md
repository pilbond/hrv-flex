# Auditoría técnica de `polar-hrv-automation` — 2026-07-10

## Alcance y método

Auditoría orientada a un despliegue Railway N=1 que debe operar durante años sin supervisión. Se revisó el árbol existente en esta sesión, primero con `code-review-graph` y después leyendo los archivos concretos de los flujos críticos. El árbol estaba modificado antes de la auditoría; por tanto, este informe describe el working tree observado el 2026-07-10, no necesariamente `HEAD`.

Flujos trazados de extremo a extremo:

- `POST /api/sync` → thread → `polar_hrv_automation.py --process` → Dropbox RR → CORE/BETA → sleep → FINAL/DASHBOARD/SSM → disco.
- `GET /auth` → Polar OAuth → `/auth/callback` → intercambio de `code` → bundle v4 atómico.
- Fechas faltantes → `egc_to_rr.py` en staging → selección por fecha → procesamiento → promoción a `rr_downloads/`.

Inventario real relevante: nueve entrypoints/scripts operativos Python en raíz (`build_hrv_core.py`, `build_hrv_final_dashboard.py`, `build_hrv_ssm.py`, sus dos auditorías, `build_sessions.py`, `egc_to_rr.py`, `polar_hrv_automation.py`, `web_ui.py`), además de `canvas-tool.py`; 23 módulos Python directamente bajo `hrv_app/`, el subpaquete `hrv_app/ai/` y 43 ficheros de tests Python. Los tres módulos v3 que la documentación declara retirados (`polar_client.py`, `polar_oauth_local.py`, `polar_shadow.py`) no existen. Sí son operativamente relevantes, aunque el resumen arquitectónico apenas los desarrolla, `railway.json`, `Procfile`, `templates/`, `static/` y `hrv_app/ai/`.

Validación ejecutada:

- Suite focalizada de seguridad/sync/Dropbox/sleep/CORE/runner: **64 passed**.
- Suite completa: **685 passed, 2 skipped, 26 subtests passed**.

Pasar la suite no invalida los hallazgos: varios comportamientos de degradación están implementados —y alguno probado— como éxito o continuación deliberada.

## Resumen ejecutivo

Top 5 por riesgo real:

1. **Pérdida del histórico CORE/BETA al encontrar un CSV existente ilegible.** `get_or_create_df` transforma cualquier error de lectura en un dataframe vacío y el mismo proceso lo sobrescribe después. Ocurre ante CSV truncado, corrupción, error transitorio de lectura o esquema que haga fallar `read_csv`; el siguiente RR deja solo las filas reprocesadas. Véase [H-01](#h-01--un-core-o-beta-ilegible-se-convierte-en-un-dataset-nuevo-y-se-sobrescribe).
2. **Sustitución remota de la cuenta Polar N=1.** `/auth` y sus callbacks no están cubiertos por `HRV_UI_KEY`; cualquier visitante que complete OAuth con su propia cuenta hace que el servidor persista ese grant sobre el bundle único. Ocurre si la URL pública es accesible sin una capa externa de autenticación. Véase [H-02](#h-02--oauth-permite-sustituir-el-bundle-del-atleta-sin-autenticar-al-propietario).
3. **La web anuncia éxito aunque falle CORE o una etapa canónica posterior.** Los fallos internos se convierten en `return`, `main()` devuelve `0` y la web define éxito únicamente por el return code. Ocurre, por ejemplo, si `build_hrv_core.py` termina no-cero. Véase [H-03](#h-03--los-fallos-del-pipeline-se-convierten-en-exit-0-y-éxito-web).
4. **Un `sleep.csv` ilegible pierde todo su histórico y además se escribe sin atomicidad.** El reader sustituye el archivo existente por un dataframe vacío y `to_csv` escribe directamente sobre el canónico. Ocurre ante corrupción o fallo de escritura durante el upsert. Véase [H-04](#h-04--sleepcsv-falla-abierto-hacia-vacío-y-su-writer-no-es-atómico).
5. **Los endpoints operativos son anónimos si falta `HRV_UI_KEY`.** La condición está codificada como opt-out; con la variable ausente, cualquiera que alcance Railway puede lanzar sync/import/restore o borrar el último RR. Véase [H-05](#h-05--los-api-operativos-quedan-anónimos-cuando-hrv_ui_key-no-está-definida).

Conclusión: la base es razonablemente modular y la mayoría de escrituras individuales importantes son atómicas, pero hoy no cumple el criterio “años sin supervisión”. Los bloqueantes son pequeños y concretos: fallar cerrado ante canónicos ilegibles, propagar el estado real de las etapas y autenticar también OAuth y los endpoints operativos en producción.

## Hallazgos

### H-01 — Un CORE o BETA ilegible se convierte en un dataset nuevo y se sobrescribe

**Prioridad:** Crítico  
**Confianza:** Alta  
**Estado:** OBSERVADO

`build_hrv_core.py:728-732`:

```python
            df = df[[c for c in columns if c in df.columns] + [c for c in df.columns if c not in columns]]
            return df
        except Exception as e:
            print(f"Advertencia: No se pudo leer {path} ({e}). Creando nuevo.")
            return pd.DataFrame(columns=columns)
```

`build_hrv_core.py:810-823` confirma que ambos históricos usan esa función:

```python
core_df = get_or_create_df(OUT_CORE, COLS_CORE)
beta_df = get_or_create_df(OUT_BETA_AUDIT, COLS_BETA_AUDIT)

if not core_df.empty and not beta_df.empty:
    history_df = core_df.merge(
```

`build_hrv_core.py:903-906` muestra que se copia el fichero previo:

```python
if OUT_CORE.exists():
    shutil.copy2(OUT_CORE, backup_dir / f"CORE_backup_{ts}.csv")
if OUT_BETA_AUDIT.exists():
    shutil.copy2(OUT_BETA_AUDIT, backup_dir / f"BETA_AUDIT_backup_{ts}.csv")
```

`build_hrv_core.py:909-911` muestra la sobrescritura posterior:

```python
# Guardar
write_csv_atomic(core_df, OUT_CORE)
write_csv_atomic(beta_df, OUT_BETA_AUDIT)
```

**Qué ocurre exactamente:** si uno de los CSV existe pero `pd.read_csv` lanza, se trata como dataset nuevo. El bucle incorpora los RR de esta ejecución y el writer atómico reemplaza el canónico anterior. El backup preserva una copia, pero preserva precisamente el archivo ilegible y la operación se presenta como una reconstrucción normal. Si solo uno de CORE/BETA falla, además se rompe la alineación histórica entre ambos.

**Propuesta concreta:** diferenciar estrictamente “no existe” de “existe pero no se puede leer”. En el segundo caso, lanzar una excepción tipada antes de procesar o escribir. Opcionalmente mover/copiar el archivo ilegible a cuarentena y exigir restore/reparación explícita; nunca inicializar vacío automáticamente. Añadir un test de integración que escriba un CORE truncado, ejecute `main()` y compruebe return code no-cero y bytes originales intactos.

### H-02 — OAuth permite sustituir el bundle del atleta sin autenticar al propietario

**Prioridad:** Crítico  
**Confianza:** Alta  
**Estado:** OBSERVADO

`web_ui.py:330-332` declara una clave opcional:

```python
# Clave compartida opcional para proteger /api/*. Si HRV_UI_KEY no está
# definida, el comportamiento es el histórico (sin autenticación).
UI_KEY = (os.environ.get("HRV_UI_KEY") or "").strip()
```

`web_ui.py:363-366` limita esa clave exclusivamente a `/api/*`:

```python
@app.before_request
def _require_ui_key():
    if not UI_KEY or not request.path.startswith("/api/"):
        return None
```

`web_ui.py:1419-1424` expone el inicio OAuth fuera de ese prefijo:

```python
if not client_id or not client_secret:
    return _api_error(MSG["auth_missing_credentials"], 500)

redirect_uri = _redirect_uri()
state = _issue_oauth_state()
return redirect(build_auth_url_v4(client_id, redirect_uri, POLAR_V4_SCOPES, state))
```

`web_ui.py:1464-1468` carga las credenciales del servicio:

```python
try:
    client_id = (os.environ.get("POLAR_CLIENT_ID2") or os.environ.get("POLAR_CLIENT_ID") or "").strip()
    client_secret = (os.environ.get("POLAR_CLIENT_SECRET") or "").strip()
    if not client_id or not client_secret:
        raise RuntimeError("Credenciales POLAR_CLIENT_ID / POLAR_CLIENT_SECRET no configuradas")
```

`web_ui.py:1470-1473` persiste el grant que complete el visitante:

```python
redirect_uri = _redirect_uri()

token_json = exchange_code_for_token_v4(code, client_id, client_secret, redirect_uri)
persist_authorized_bundle(TOKEN_PATH_V4, token_json, scopes=POLAR_V4_SCOPES)
```

**Qué ocurre exactamente:** el `state` evita callback forjado/replay, pero no demuestra que quien inició `/auth` sea el propietario del despliegue. Un tercero puede abrir `/auth`, autorizar su propia cuenta Polar y completar el callback válido; el bundle único de `/data` se reemplaza con ese grant. A partir de ahí las lecturas sleep/nightly v4 se consultan con la cuenta sustituta.

**Propuesta concreta:** en producción, exigir la misma clave de propietario para `/auth` y ligar el callback a una cookie de sesión `HttpOnly`, `Secure`, `SameSite=Lax` que contenga/verifique el nonce. Como mínimo, proteger `/auth` con `HRV_UI_KEY` y hacer obligatoria esa variable cuando `IS_PRODUCTION`; no poner la clave en query string para OAuth. Test de integración: con clave configurada, `/auth` sin header/cookie debe devolver 401 y no emitir state.

### H-03 — Los fallos del pipeline se convierten en exit 0 y éxito web

**Prioridad:** Alto  
**Confianza:** Alta  
**Estado:** OBSERVADO

`hrv_app/pipeline_runner.py:43-48` convierte un builder no-cero en `None`:

```python
print(f"⚠️  Error ejecutando {script_name} (código {exc.returncode})")
if exc.stdout:
    print(exc.stdout)
if exc.stderr:
    print(exc.stderr)
return None
```

`hrv_app/hrv_sync_flow.py:242-247` registra el fallo de CORE y retorna normalmente:

```python
if result is None:
    _render_report(build_message_report("⚠️  build_hrv_core.py falló; se actualiza sleep.csv, pero no se regenera FINAL/DASHBOARD."))
    _refresh_sleep_and_outputs(access_token, x_user_id, run_final_dashboard=False)
    _send_intervals_wellness_from_master(INTERVALS_SOURCE_PATH)
    show_latest_hrv_summaries()
    return
```

`polar_hrv_automation.py:140-144` no recibe resultado y devuelve cero:

```python
sync_hrv_range(args, None, None, [])

# Backup opcional del histórico fuera del volumen (opt-in, nunca rompe el sync)
run_dropbox_backup()
return 0
```

`web_ui.py:523-527` define éxito solo por ese código:

```python
)

success = (result.returncode == 0)
message = success_message if success else f'Error en {_job_label(job_type)}'
_set_execution_result(job_type, success, result.stdout or '', result.stderr or '', message)
```

**Qué ocurre exactamente:** si CORE falla, `sync_hrv_range` termina normalmente, se intenta incluso el backup y el proceso padre devuelve `0`; `/api/status` queda con `success=true`. FINAL también se trata como booleano local y no cambia el resultado global. Esto oculta el fallo precisamente al mecanismo que la UI y un operador usarían para detectar la mañana fallida.

**Propuesta concreta:** devolver un resultado estructurado (`ok`, `degraded`, `failed`, etapas y fechas) desde `sync_hrv_range`; `main()` debe devolver no-cero si falla CORE, FINAL o cualquier output obligatorio del modo `--process`. La web ya sabe interpretar return codes, por lo que no necesita una arquitectura nueva. Mantener AI, SSM experimental, Intervals y backup como best-effort explícitos. Test de integración: mock de `run_build_hrv_core -> None`, ejecutar el entrypoint vía `_run_subprocess_job` y afirmar `success=false`.

### H-04 — `sleep.csv` falla abierto hacia vacío y su writer no es atómico

**Prioridad:** Alto  
**Confianza:** Alta  
**Estado:** OBSERVADO

`hrv_app/sleep_store.py:360-365` transforma un canónico ilegible en vacío:

```python
        try:
            sleep_df = pd.read_csv(SLEEP_PATH)
        except (FileNotFoundError, pd.errors.EmptyDataError, OSError, ValueError):
            sleep_df = pd.DataFrame(columns=SLEEP_COLUMNS)
    else:
        sleep_df = pd.DataFrame(columns=SLEEP_COLUMNS)
```

`hrv_app/sleep_store.py:373-378` reemplaza después el archivo directamente:

```python
sleep_df = pd.concat([sleep_df, pd.DataFrame([row])], ignore_index=True)
sleep_df = _recalculate_sleep_derived(sleep_df)
sleep_df = sleep_df[SLEEP_COLUMNS]

SLEEP_PATH.parent.mkdir(parents=True, exist_ok=True)
sleep_df.to_csv(SLEEP_PATH, index=False)
```

**Qué ocurre exactamente:** si el CSV histórico está vacío, truncado o temporalmente ilegible, el siguiente upsert crea un dataframe con una sola fila y sobrescribe el histórico. Además, un corte de proceso, disco lleno o error de I/O durante `to_csv(SLEEP_PATH)` puede dejar el canónico parcial porque no usa `write_csv_atomic`.

**Propuesta concreta:** importar y usar `write_csv_atomic`; si el archivo existe y no se puede leer, lanzar y conservarlo intacto. Solo crear un dataframe vacío cuando `not SLEEP_PATH.exists()`. Añadir tests de read-failure fail-closed y de llamada al helper atómico.

### H-05 — Los API operativos quedan anónimos cuando `HRV_UI_KEY` no está definida

**Prioridad:** Alto  
**Confianza:** Alta  
**Estado:** OBSERVADO

`web_ui.py:364-369` desactiva toda autenticación cuando la variable está vacía:

```python
def _require_ui_key():
    if not UI_KEY or not request.path.startswith("/api/"):
        return None
    provided = (request.headers.get("X-HRV-KEY") or request.args.get("key") or "").strip()
    if provided and secrets.compare_digest(provided, UI_KEY):
        return None
```

`web_ui.py:1391-1395` muestra que el borrado operativo es uno de esos endpoints:

```python
@app.route('/api/delete-latest-rr', methods=['POST'])
def delete_latest_rr():
    """Mover a backup el último RR CSV del directorio operativo."""
    if not _try_begin_execution('delete_rr'):
        return _api_error(_in_progress_error(_execution_snapshot().get('job_type'), MSG['delete_in_progress_suffix']), 409)
```

`web_ui.py:1397-1402` confirma la mutación y el resultado exitoso:

```python
try:
    result = _delete_latest_rr()
    _set_execution_result(
        'delete_rr',
        True,
        json.dumps(result, ensure_ascii=False, indent=2),
```

**Qué ocurre exactamente:** con `HRV_UI_KEY` ausente o vacía, cualquier cliente que alcance el servicio puede invocar los cinco POST operativos. El impacto no es solo consumo de CPU: puede mover el RR más reciente, importar seeds disponibles o restaurar un backup sobre `/data`. La serialización evita dos jobs simultáneos, no un caller no autorizado.

**Propuesta concreta:** hacer obligatoria una clave no vacía en producción y abortar el arranque si falta. Mantener el modo sin clave únicamente para loopback/local mediante una condición explícita. Aceptar la clave solo en header; `?key=` termina en historiales, proxies y logs. Añadir una prueba parametrizada sobre todos los `/api/*`, no solo restore.

### H-06 — Un error de Dropbox se degrada a “sin RR” y el ciclo termina con éxito

**Prioridad:** Medio  
**Confianza:** Alta  
**Estado:** OBSERVADO

`hrv_app/dropbox_rr.py:194-199` captura el timeout sin devolver estado de error:

```python
except subprocess.TimeoutExpired as exc:
    print(f"⚠️  Timeout ejecutando importación Dropbox RR (>{DROPBOX_RR_TIMEOUT_SEC}s)")
    if exc.stdout:
        print(exc.stdout)
    if exc.stderr:
        print(exc.stderr)
```

`hrv_app/dropbox_rr.py:200-205` hace lo mismo con un proceso no-cero:

```python
except subprocess.CalledProcessError as exc:
    print(f"⚠️  Error ejecutando importación Dropbox RR (código {exc.returncode})")
    if exc.stdout:
        print(exc.stdout)
    if exc.stderr:
        print(exc.stderr)
```

`hrv_app/dropbox_rr.py:208-213` devuelve solamente los ficheros que hayan quedado disponibles:

```python
merged_map: Dict[date, Path] = dict(pre_map)
merged_map.update(post_map)

result = {d: merged_map[d] for d in target_set if d in merged_map}
new_count = sum(1 for d in result if d not in pre_map and d in post_map)
return result, new_count
```

`tests/test_dropbox_rr_contract.py:118-123` codifica esa supervivencia como contrato:

```python
def test_run_dropbox_rr_import_for_dates_passes_timeout_and_survives_timeout(self):
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        preexisting = root / "existing_2026-03-01_from_jsonl_RR.CSV"
        preexisting.write_text("duration,offline\n90,0\n", encoding="utf-8")
```

`tests/test_dropbox_rr_contract.py:124-127` provoca el timeout:

```python
buffer = io.StringIO()

def fake_run(cmd, **kwargs):
    raise subprocess.TimeoutExpired(cmd=cmd, timeout=kwargs.get("timeout"))
```

**Qué ocurre exactamente:** no se distingue “Dropbox respondió correctamente pero no contiene esa fecha” —caso de dominio válido— de “la única fuente falló por timeout, credenciales, converter o red”. Ambos terminan como mapa parcial/vacío; el flujo superior refresca lo que pueda y, por H-03, la web marca éxito.

**Propuesta concreta:** devolver `{files, missing_dates, source_status, error}`. `missing_dates` con `source_status=ok` puede ser éxito sin datos; timeout/no-cero debe producir `degraded` o fallo del job y quedar visible en `/api/status`. Conservar outputs parciales válidos, pero no borrar el error.

### H-07 — Los backups locales de CORE/BETA crecen sin política de retención

**Prioridad:** Medio  
**Confianza:** Alta  
**Estado:** OBSERVADO

`build_hrv_core.py:899-904` crea nombres nuevos por timestamp en cada ejecución con backups habilitados:

```python
if not disable_backup:
    backup_dir = DATA_DIR / "backup"
    backup_dir.mkdir(exist_ok=True)

    if OUT_CORE.exists():
        shutil.copy2(OUT_CORE, backup_dir / f"CORE_backup_{ts}.csv")
```

La búsqueda de todas las referencias a `CORE_backup_` y `BETA_AUDIT_backup_` en el código operativo solo encontró estas escrituras; no se observó pruning o retención.

**Qué ocurre exactamente:** con el default de backups activo, cada mañana conserva nuevas copias completas de CORE y BETA. El crecimiento es monótono; sumado a un RR por día y sidecars históricos, termina consumiendo el volumen finito. Cuando el volumen se llena, los writers fallan; H-03 puede convertir parte de esos fallos en un sync aparente exitoso.

**Propuesta concreta:** retención simple N=1, por ejemplo 14 diarios + 12 mensuales, ejecutada solo después de completar y verificar la nueva generación. Añadir `free_bytes` y tamaño de `data/backup` a `/api/status`/`health?strict=1`, sin exponer rutas completas.

### H-08 — La atomicidad es por fichero, no por generación canónica

**Prioridad:** Medio  
**Confianza:** Alta  
**Estado:** OBSERVADO

`build_hrv_final_dashboard.py:2286-2290` reemplaza tres artefactos secuencialmente:

```python
final, dashboard = build_final_and_dashboard(core, cfg)
DATA_DIR.mkdir(parents=True, exist_ok=True)
write_csv_atomic(final, OUT_FINAL)
write_csv_atomic(dashboard, OUT_DASHBOARD)
write_json_atomic(final.attrs.get("reason_items_sidecar", {}), OUT_FINAL_REASON_ITEMS)
```

`build_hrv_core.py:909-913` hace lo mismo con CORE y BETA antes de construir el manifest:

```python
# Guardar
write_csv_atomic(core_df, OUT_CORE)
write_csv_atomic(beta_df, OUT_BETA_AUDIT)

manifest = build_run_manifest(
```

`web_ui.py:995-1000` consume FINAL directamente, sin comprobar el manifest:

```python
last_final_row = {}
if final_path.exists():
    try:
        with final_path.open("r", encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
```

**Qué ocurre exactamente:** si el segundo o tercer replace falla, los artefactos anteriores ya son de la generación nueva y los posteriores permanecen viejos; el manifest nuevo no llega a escribirse. La UI consume los CSV directamente y no valida el manifest de corrida, por lo que puede presentar una combinación de generaciones.

**Propuesta concreta:** mantener la atomicidad individual, pero envolver cada grupo con un pequeño protocolo de generación: crear todos los temporales, validarlos, conservar snapshots previos y efectuar los replaces; si uno falla, restaurar el grupo anterior y devolver no-cero. Como defensa adicional, los consumidores deben rechazar una generación cuyo manifest falte o cuyos hashes no coincidan.

## Cobertura de tests: huecos de mayor valor

El grafo encontró cobertura directa para refresh/persistencia OAuth y para el importador Dropbox, pero no relacionó tests con `get_or_create_df`, `sync_hrv_range`, `oauth_callback` ni `_run_subprocess_job`. La lectura manual muestra abundantes tests del flujo, aunque centrados en happy paths/degradación actual. Por ejemplo, `tests/test_build_hrv_core_contract.py:67-72` solo verifica la creación exitosa:

```python
exit_code = core_builder.main()

self.assertEqual(exit_code, 0)
self.assertTrue((data_dir / "ENDURANCE_HRV_master_CORE.csv").exists())
self.assertTrue((data_dir / "ENDURANCE_HRV_master_BETA_AUDIT.csv").exists())
```

Los tres tests de integración con mejor retorno serían:

1. **Fail-closed de históricos:** CORE/BETA y sleep preexistentes pero corruptos; el proceso debe fallar, conservar bytes y no publicar manifest nuevo.
2. **Propagación web real:** simular fallo de CORE y de FINAL desde `POST /api/sync`; el estado final debe ser `success=false`, con etapa y fecha fallidas.
3. **Frontera de propietario:** en configuración de producción, todos los `/api/*` y `/auth` deben rechazar ausencia/clave incorrecta; un callback sin sesión propietaria ligada al state no debe persistir nada.

No hace falta testear cada función privada ni introducir fixtures complejas: estos tres atraviesan las fronteras donde hoy se pierde la semántica.

## No verificado

Estos puntos no cuentan como hallazgos ni entran en el top de riesgos:

- **Valor real de `HRV_UI_KEY` en Railway.** El repositorio solo define el comportamiento condicional. Hace falta inspeccionar las variables del servicio para saber si H-05 está actualmente expuesto.
- **Protección externa de `/auth`.** No se verificó si Railway, un proxy, VPN o firewall autentica la URL antes de Flask. Hace falta configuración de infraestructura o una prueba desde Internet.
- **Número de réplicas/instancias.** El repo arranca un único proceso Flask por contenedor (`python web_ui.py`), pero no se verificó el escalado real de Railway. Más de una réplica rompería la exclusión basada únicamente en memoria.
- **Estado e integridad actual de `/data`.** No se inspeccionó el volumen de producción; no se afirma que haya CSV corruptos, generaciones mixtas o poco espacio, solo cómo responde el código si ocurre.
- **Capacidad y crecimiento real del volumen.** Hace falta tamaño asignado, uso actual y tasa de crecimiento para estimar fecha de agotamiento.
- **Monitor de `health?strict=1`.** El endpoint existe, pero no se verificó que un servicio externo lo consulte ni alerte.
- **Calidad del backup Dropbox actual.** No se inspeccionaron credenciales, contenido remoto ni consistencia de la última copia.
- **Descendientes tras timeout web.** El runner web aplica timeout al proceso padre, mientras los builders son subprocess internos sin timeout. No se probó en el runtime Railway si un builder descendiente queda vivo tras matar al padre.

## Doc drift

### D-01 — La guía afirma que el entrypoint valida tokens; el entrypoint no lo hace

`docs/contracts/GUIA_PYTHON_SCRIPTS.md:9-12`:

```text
1. `web_ui.py` levanta la web.
2. Al llamar `POST /api/sync`, la web ejecuta `python polar_hrv_automation.py --process`.
3. `polar_hrv_automation.py` valida entorno, tokens y argumentos, y delega el flujo operativo a `hrv_app.hrv_sync_flow`.
```

`polar_hrv_automation.py:137-142`:

```python
        print(f"❌ Auto-restore falló: {exc}", file=sys.stderr)
        return 1

    sync_hrv_range(args, None, None, [])

    # Backup opcional del histórico fuera del volumen (opt-in, nunca rompe el sync)
```

**Contradicción:** el entrypoint parsea argumentos y ejecuta auto-restore, pero no valida token ni credenciales antes de delegar; incluso pasa `None, None`. La web solo comprueba que el path del bundle exista, no que sea JSON válido ni refrescable. Actualizar la guía o implementar una validación explícita que falle limpio cuando las etapas obligatorias necesiten Polar.

### D-02 — “Backup tras sync exitoso” no coincide con la semántica real de éxito

`AGENTS.MD:125-127`:

```text
Actualiza `ENDURANCE_HRV_sleep.csv`.
Ejecuta `build_hrv_core.py`, `build_hrv_final_dashboard.py` y `build_hrv_ssm.py` cuando corresponde.
Al final del sync exitoso, ejecuta `hrv_app.backup_dropbox.run_backup()` (opt-in via `HRV_BACKUP_DROPBOX_ENABLED`; nunca rompe el sync).
```

`polar_hrv_automation.py:140-144`:

```python
sync_hrv_range(args, None, None, [])

# Backup opcional del histórico fuera del volumen (opt-in, nunca rompe el sync)
run_dropbox_backup()
return 0
```

**Contradicción:** por H-03, un fallo de CORE retorna normalmente desde `sync_hrv_range`; el entrypoint lo considera final normal, ejecuta backup y devuelve cero. La documentación usa “exitoso” en el sentido esperado, mientras el código usa “no lanzó excepción”. Corregir primero la semántica del código y conservar el texto documental.

### D-03 — El criterio de aceptación promete actualizar todos los canónicos, pero la API puede devolver éxito sin hacerlo

`AGENTS.MD:321-325`:

```text
## 14. Criterios de aceptacion
1. `/auth` devuelve 302 a Polar con `redirect_uri` correcto.
2. `/auth/callback` guarda tokens en `POLAR_TOKEN_PATH`.
3. `POST /api/sync` genera o actualiza `CORE`, `BETA_AUDIT`, `sleep`, `FINAL` y `DASHBOARD`.
4. Tras redeploy, `/api/sync` sigue funcionando si hay Volume.
```

`hrv_app/hrv_sync_flow.py:269-275`:

```python
_render_report(build_pipeline_stage_report("Ejecutando build_hrv_final_dashboard.py..."))
final_ok = run_build_hrv_final_dashboard_only()

_render_report(build_pipeline_stage_report("Ejecutando build_hrv_ssm.py..."))
ssm_ok = run_build_hrv_ssm_shadow_only()
if not ssm_ok:
```

**Contradicción:** `final_ok=False` no se propaga ni impide el cierre exitoso. El criterio de aceptación describe el resultado contractual, pero el código no lo garantiza ni lo refleja en el return code.

## Lo que está bien y no conviene desmontar

### Tokens v4: persistencia atómica, permisos y refresh serializado

`hrv_app/oauth_utils.py:44-49`:

```python
def save_json_atomic(path: Path, payload: dict[str, Any], chmod_mode: int = 0o600) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + f".{os.getpid()}.{uuid4().hex[:8]}.tmp")
    tmp_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    tmp_path.replace(path)
```

`hrv_app/oauth_utils.py:50-54` aplica permisos restrictivos:

```python
if chmod_mode is None:
    return
try:
    os.chmod(path, chmod_mode)
except OSError:
    pass
```

`hrv_app/polar_auth_v4.py:362-367` relee el bundle bajo locks para evitar quemar un refresh rotatorio:

```python
seen_obtained_at = bundle.get("obtained_at")
with _REFRESH_LOCK, _file_lock(bundle_path) as got_file_lock:
    current = load_bundle_v4(bundle_path) or bundle
    if current.get("obtained_at") != seen_obtained_at and not bundle_needs_refresh(current):
        return current.get("access_token")
```

No se observaron tokens en `/api/status`: `redact()` solo expone presencia/metadata. Esta base debe conservarse.

### Serialización de los cinco POST en el proceso actual

`web_ui.py:468-473` hace check-and-set bajo el mismo lock:

```python
def _try_begin_execution(job_type: str) -> bool:
    with execution_state_lock:
        if execution_state['running']:
            return False
        execution_state['running'] = True
        execution_state['success'] = None
```

`web_ui.py:474-478` completa la transición bajo el mismo lock:

```python
execution_state['last_output'] = ''
execution_state['last_error'] = ''
execution_state['job_type'] = job_type
execution_state['message'] = None
return True
```

Los cinco handlers llaman a `_try_begin_execution` antes de mutar datos. Con el arranque observado de un solo proceso por contenedor, esto resuelve correctamente la concurrencia intra-proceso sin introducir colas ni workers.

### Dropbox es la única fuente de RR nuevos y usa staging

`hrv_app/hrv_sync_flow.py:368-373` solo obtiene los nuevos RR desde el importador Dropbox:

```python
dropbox_rr_map, dropbox_rr_new = _run_dropbox_rr_import_for_dates(
    target_missing_dates,
    OUTDIR,
    verbose=args.verbose,
)
if dropbox_rr_map:
```

`hrv_app/hrv_sync_flow.py:374-377` deriva de ese mapa la única lista de RR nuevos:

```python
reused = max(len(dropbox_rr_map) - dropbox_rr_new, 0)
_render_report(build_message_report(f"☁️  Dropbox RR: {len(dropbox_rr_map)} fecha(s) cubierta(s) ({dropbox_rr_new} nuevas, {reused} ya existentes)"))

rr_files = [path for _, path in sorted(dropbox_rr_map.items())]
```

`hrv_app/dropbox_rr.py:152-157` separa preexistentes y staging:

```python
outdir = Path(rr_dir)
pre_map = _scan_rr_files_by_date(outdir, source_tag="from_jsonl")
stage_dir = _dropbox_stage_dir(outdir)

if not DROPBOX_RR_ENABLED:
    result = {d: pre_map[d] for d in target_set if d in pre_map}
```

`hrv_app/dropbox_rr.py:170-175` limpia solamente ese staging antes de importar:

```python
if not script_path.exists():
    _qprint(f"⚠️  No existe el script Dropbox RR: {script_path}")
    result = {d: pre_map[d] for d in target_set if d in pre_map}
    return result, 0

_clear_dropbox_stage_dir(stage_dir)
```

No se observó fallback Polar para RR nuevos. La promoción a nombre canónico ocurre después de CORE exitoso, lo que reduce la posibilidad de tratar un RR no procesado como operativo.

### Writers atómicos individuales y health estricto

`hrv_app/io_utils.py:44-49` crea el temporal en el mismo directorio:

```python
def write_csv_atomic(df: pd.DataFrame, path: Path, **to_csv_kwargs) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f"{path.name}.", suffix=".tmp")
    os.close(fd)
    tmp_path = Path(tmp)
    try:
```

`hrv_app/io_utils.py:50-52` escribe y reemplaza al final:

```python
    df.to_csv(tmp_path, index=False, **to_csv_kwargs)
    _replace_atomic(tmp_path, path)
finally:
```

CORE, BETA, FINAL, DASHBOARD, sessions, SSM y manifests usan estos helpers. La excepción operativa relevante es `sleep.csv` (H-04).

`web_ui.py:1537-1543` implementa correctamente un readiness opt-in separado del liveness:

```python
strict = (request.args.get('strict') or '').strip().lower() in {'1', 'true', 'yes'}
if strict:
    days = staleness.get('days_stale')
    if days is None or days > stale_max:
        payload['status'] = 'stale'
        return jsonify(payload), 503
```

Conviene mantener `/health` como liveness 200 y usar `?strict=1` para alertas; lo pendiente es verificar que exista un monitor externo.

## Orden de remediación recomendado

1. **P0, una sesión:** H-01 + H-04. Fail-closed para canónicos existentes ilegibles y `write_csv_atomic` en sleep.
2. **P0, una sesión:** H-03 + H-06. Resultado estructurado por etapas y return code no-cero para outputs obligatorios/errores de la única fuente.
3. **P0, una sesión:** H-02 + H-05. Frontera única de propietario, obligatoria en producción, cubriendo `/auth` y `/api/*`.
4. **P1:** H-08. Validación/rollback de generaciones y consumo del manifest.
5. **P1:** H-07. Retención local y métrica de espacio libre.

No se recomienda multiusuario, DI, repositorios, microservicios, queues ni workers. Las correcciones caben en los módulos actuales y reducen complejidad operativa.

## Revisión crítica complementaria — 2026-07-13

### 1. Síntesis de la tesis original

La auditoría identifica correctamente que los flujos HRV sync, OAuth v4 y RR Dropbox no son todavía suficientemente resistentes para operar durante años sin supervisión. Los riesgos más sólidos son la reinicialización de históricos ilegibles, la pérdida de errores del pipeline y la falta de una frontera de propietario para OAuth y los endpoints operativos.

La conclusión es válida para los flujos cubiertos por AYO-26, pero resulta demasiado amplia si se interpreta como una auditoría exhaustiva de todo el runtime.

### 2. Contraargumentos más fuertes

1. Las prioridades `Crítico/Alto/Medio` no tienen una matriz explícita de impacto, probabilidad y exposición. H-01 y H-02 son graves, pero su criticidad efectiva depende de la posibilidad de recuperación y de la configuración real de Railway.
2. El informe no es completamente reproducible: no fija commit, diff del working tree, versión de Python, dependencias, variables de entorno ni los comandos exactos usados para obtener los 64 tests focalizados.
3. Algunas remediaciones necesitan precisión adicional. Proteger `/auth` mediante un header no es suficiente para una navegación OAuth normal; además, `static/ui.js` lee actualmente la clave desde la URL. El rollback mediante varios `replace` tampoco constituye atomicidad real de generación.
4. El alcance declarado cubre sync, OAuth y Dropbox RR, no restauración, despliegue WSGI ni todo `sync-sessions`. La conclusión global debe reflejar ese límite.

### 3. Confianza por afirmación

- CORE/BETA y `sleep.csv` pueden perder histórico ante errores de lectura: factual, 99/100, razonable.
- Un fallo de CORE o FINAL puede terminar en `exit 0` y `success=true`: factual, 99/100, razonable.
- OAuth y los APIs no tienen una frontera suficiente de propietario: factual, 96/100, razonable; la exposición efectiva de producción no está verificada.
- Dropbox, restore y publicaciones multiarchivo pueden dejar estados parciales sin visibilidad adecuada: inferencial, 94/100, razonable.
- El sistema completo no puede operar durante años sin supervisión: inferencial, 88/100, razonable para los flujos auditados; no demostrado para todo el repositorio.

### 4. Fallos potenciales y verificación

- **Restore parcial presentado como éxito.** Plausibilidad alta; estado confirmado. `hrv_app.backup_dropbox.restore_backup()` descarga y reemplaza archivos uno a uno, puede devolver `status="partial"`, y `/api/restore-backup` marca incondicionalmente el job como exitoso. El auto-restore puede dejar CORE restaurado y otros archivos ausentes; un arranque posterior puede saltarse la restauración al detectar CORE utilizable.
- **Servidor de desarrollo Flask en Railway.** Plausibilidad alta; estado confirmado por `web_ui.py`, `Procfile` y `railway.json`, que arrancan `python web_ui.py` y `app.run()`. La documentación oficial de Flask desaconseja `run()` en producción por razones de estabilidad, seguridad y rendimiento.
- **La clave UI puede filtrarse por URL.** Plausibilidad alta; estado confirmado. `static/ui.js` obtiene `key` de `window.location.search`; eliminar la aceptación de query string en backend no resuelve por sí solo la exposición.
- **H-07 está sobredimensionado.** Plausibilidad media; estado parcialmente confirmado. La ausencia de retención existe, pero sin capacidad ni tasa de crecimiento de Railway no se puede justificar todavía como prioridad superior a restore, autenticación o propagación de errores.

### 5. Cambios y conclusiones

- **Qué se mantiene:** H-01, H-03, H-04 y H-06 están bien demostrados; H-05 es una vulnerabilidad real si falta `HRV_UI_KEY`; H-08 identifica correctamente la inconsistencia potencial entre artefactos.
- **Qué se debilita:** H-02 debe clasificarse como alto y elevarse a crítico solo tras confirmar exposición pública sin autenticación externa. H-07 debería quedar como P2 hasta medir el volumen.
- **Qué se corrige:** H-01 afecta con seguridad al archivo ilegible, no necesariamente a CORE y BETA simultáneamente. H-08 necesita generaciones versionadas y un único puntero/manifest validado, no solo rollback secuencial.
- **Incertidumbres abiertas:** configuración real de Railway, autenticación externa, número de réplicas, capacidad del volumen, monitorización de `/health?strict=1`, integridad remota de Dropbox y comportamiento de procesos descendientes tras timeout.

La suite actual ejecutada el 2026-07-13 produjo `687 passed, 2 skipped, 26 subtests passed`; la diferencia frente a los `685 passed` del auditado original es compatible con cambios posteriores y no invalida aquella medición histórica.

### 6. Respuesta revisada

La auditoría confirma fallos operativos importantes en los flujos HRV sync, OAuth v4 y RR Dropbox. El problema central es la pérdida de semántica ante errores: históricos ilegibles se reinicializan, etapas obligatorias pueden fallar con `exit 0`, restauraciones parciales pueden anunciar éxito y la frontera de propietario no cubre OAuth de forma suficiente. La arquitectura modular permite corregirlo sin introducir multiusuario, colas ni microservicios.

Orden de remediación revisado:

1. Fail-closed de CORE/BETA/sleep y escritura atómica de sleep.
2. Resultado estructurado del pipeline; CORE, FINAL, Dropbox y restore parcial deben producir estado no exitoso.
3. Restauración por generación completa, validada antes de publicar y con rollback/reintento seguro.
4. Sesión de propietario para `/auth`, callback ligado a sesión y autenticación de todos los `/api/*`; retirar claves de URLs.
5. Sustituir `app.run()` por un servidor WSGI de producción compatible con Railway.
6. Generaciones canónicas versionadas y consumo validado mediante manifest.
7. Retención de backups y métricas de espacio después de medir capacidad y crecimiento.
