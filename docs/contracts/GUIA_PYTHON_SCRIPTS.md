# Guia didactica de scripts Python

Este documento explica, en lenguaje simple, que hace cada `.py` del proyecto, en que flujo participa y como encaja la conversion `ECG.jsonl + ACC.jsonl -> RR`.

## 1) Mapa rapido del flujo principal

Flujo operativo normal (Railway o UI local):

1. `web_ui.py` levanta la web.
2. Al llamar `POST /api/sync`, la web ejecuta `python polar_hrv_automation.py --process`.
3. `polar_hrv_automation.py` valida entorno, tokens y argumentos, y delega el flujo operativo a `hrv_app.hrv_sync_flow`.
4. `hrv_app.hrv_sync_flow` calcula las fechas objetivo (desde `ultima_fecha_CORE + 1` hasta hoy) y usa `hrv_app.dropbox_rr` para intentar cubrirlas desde JSONL/ZIP con `egc_to_rr.py`. Si `CORE` esta vacio, primero intenta reconstruir desde RR ya presentes en `data/rr_downloads/`; solo si no hay RR locales cae al bootstrap corto desde Dropbox. Dropbox es la **unica** fuente de nuevos RR matinales (AYO-13-F4): si una fecha no esta en Dropbox, esa fecha no entra al pipeline en este ciclo (sin fallback Polar).
5. `hrv_app.sleep_store` actualiza `ENDURANCE_HRV_sleep.csv`, `hrv_app.intervals_sync` resuelve la parte de wellness/Intervals y `hrv_app.pipeline_runner` llama:
   - `build_hrv_core.py`
   - `build_hrv_final_dashboard.py`
   - cada builder deja además su sidecar de trazabilidad atómico (`ENDURANCE_HRV_master_CORE_manifest.json` y `ENDURANCE_HRV_master_FINAL_manifest.json`)

Importante:
- El comando principal no cambia: `python polar_hrv_automation.py --process`.
- `polar_hrv_automation.py` ya no concentra toda la logica operativa; hoy actua como entrypoint fino.
- `build_sessions.py` no se ejecuta automaticamente en ese flujo.
- `build_hrv_final_dashboard.py` usa `ENDURANCE_HRV_sessions_day.csv` solo si ya existe.
- Si `sessions_day.csv` y `sessions_metadata.json` estan al dia, `FINAL` puede incorporar contexto de carga canonico (`ACWR`, `monotony`, `strain`, clustering de intensidad) y capas de recuperacion multisenal sin tocar el gate.
- La capa de terreno no nace aqui: se genera despues dentro de `analysis/` al correr `analysis\\run_session_analysis.py` o `analysis\\analyze_session.py`.
- Esa capa sigue siendo local a `analysis/`: hoy puede exponer `terrain_fit_context` tambien en `bike`, y en sesiones `trail`/`road` puede mostrar `climb_power_mean` cuando la fuente FIT lo declara como potencia medida; `terrain_climbs.csv` sigue siendo el detalle reproducible por climb y no cambia ningun contrato canonico global.
- Esa misma capa local de `analysis/` ya puede enriquecer el bundle de sesion con `composite_context` (`subjective_coherence`, `thermal_context`, `durability_context`) sin tocar `sessions.csv`, `sessions_day.csv` ni otros contratos canonicos.
- `analysis/hrv_rebound_profile.py` genera una lectura retrospectiva de rebote HRV D+1/D+3 como sidecar local (`analysis/reports/hrv_rebound_profile/`); sirve para analisis semanal de absorcion, no para el gate diario.
- `analysis/` deja tambien `artifacts/report_sync_status.json` para explicitar si el `report.md` o `report.ia.md` humano esta alineado con `session_payload.json`, `summary.json` y `technical_report.md`. El prompt/handoff incluyen un `report_sync_token` que debe copiarse al inicio del informe narrativo final.
- En el semanal local, `analysis/analyze_weekly.py` reutiliza `weekly_prep_manifest.json`, genera `report.auto.md`, `report.ia.md`, `analyst_prompt.md`, `ai_handoff.md` y `artifacts/report_sync_status.json` bajo `analysis/reports/weekly/<week_start>_<week_end>/`. Esta capa sigue siendo local de `analysis/` y no modifica ningún contrato canónico del pipeline principal.
- Desde esta misma fase, `analysis/run_analysis()` genera `report.md` directamente como artefacto final gobernado por pipeline. Si encuentra un `report.md` legacy sin token, crea antes un backup `report.legacy.md` y luego toma posesion del informe principal.

## 2) Script por script

## `web_ui.py`
- Que hace:
  - Levanta Flask (UI + API).
  - Expone endpoints: `/`, `/auth`, `/auth/callback`, `/oauth/callback`, `/api/sync`, `/api/sync-sessions`, `/api/status`, `/api/import-seed`, `/api/restore-backup`, `/api/delete-latest-rr`, `/health`.
  - En `/api/sync` dispara `polar_hrv_automation.py --process`.
  - En `/api/sync-sessions` dispara `build_sessions.py --update`.
  - La UI prioriza los controles operativos, despues la tarjeta `Lectura HRV de hoy` (viewmodel `hrv_app.ui_view`, con indicadores de Calidad/Estabilidad, bloque Gate/Accion/Que paso/Que hacer, reason text y brief IA), y por ultimo `Detalle tecnico` / `raw output` (colapsado por defecto, con boton para expandir).
- Cuando usarlo:
  - Siempre que quieras usar OAuth web y lanzar sync desde navegador.
  - Es el entrypoint de Railway.
- Entradas:
  - Variables de entorno (`PORT`, `POLAR_CLIENT_ID`, `POLAR_CLIENT_SECRET`, `PUBLIC_URL`, etc.).
- Salidas:
  - Respuestas HTTP y logs.
  - `GET /api/status` devuelve estado actual del job, `job_type` y ultimo `output/error` relevante.
  - `GET /api/status` incluye tambien el resumen semanal de `ENDURANCE_HRV_weekly_coach.json` para que la UI pinte `planning_note`, `iso_week`, `window_end`, `data_quality` y `weekly_coach_z3_budget_summary` sin crear un endpoint nuevo.
  - `POST /api/sync` y `POST /api/sync-sessions` devuelven `202 Accepted` cuando el job queda corriendo en background; si terminan practicamente al instante, pueden devolver el resultado final en la propia respuesta.
  - No genera CSV por si solo; delega al pipeline.
- Automatico o manual:
  - Automatico en Railway (start command).
  - `POST /api/sync`, `POST /api/sync-sessions`, `POST /api/import-seed`, `POST /api/restore-backup` y `POST /api/delete-latest-rr` comparten estado y no deben ejecutarse en paralelo.
  - Si `HRV_UI_KEY` está definida, todos los `/api/*` exigen la clave vía header `X-HRV-KEY` o query `?key=`; sin definir, comportamiento histórico sin autenticación.

## `canvas-tool.py`
- Que hace:
  - Gestiona `Project.canvas` mediante comandos de lectura, propuesta, inicio, pausa, cierre y dependencias.
- Cuando usarlo:
  - Solo para el workflow Kanvas documentado en `AGENTS.MD`.
- Comando base:
  - `python canvas-tool.py Project.canvas <command>`
- Importante:
  - No editar `Project.canvas` manualmente.

## `polar_hrv_automation.py`
- Que hace:
  - Es el entrypoint CLI del flujo HRV.
  - Valida configuracion, tokens y argumentos.
  - Orquesta el registro Polar cuando hace falta y delega el trabajo operativo en modulos extraidos.
  - Mantiene el contrato CLI historico del repo sin reabrir el alcance funcional.
- Cuando usarlo:
  - Sync operativo principal (CLI o disparado desde web).
- Flags:
  - `--process`: flujo completo (cubrir fechas + CORE + FINAL + DASHBOARD + SSM).
  - `--auth`: forzar re-autenticacion Polar.
  - `--auto`: detectar automaticamente dias faltantes desde ultimo registro.
  - `--all`: reprocesa RR ya existentes en `rr_downloads/` sin descargar nada nuevo.
  - `--days N`: limita la ventana de fechas a los ultimos N dias.
  - `--ssm-audit`: ejecuta SSM shadow + validacion + outcome battery (no combina con `--process`).
  - `--debug-sports`: muestra deportes de sesiones Polar de los ultimos 7 dias (diagnostico).
  - `--verbose`: detalles de cada archivo procesado.
- Entradas:
  - Tokens, credenciales Polar, RR ya existentes, configuracion de `HRV_DATA_DIR`.
- Salidas:
  - RR descargados + actualizacion de sleep + (si `--process`) archivos CORE/BETA/FINAL/DASHBOARD.
- Automatico o manual:
  - Manual por CLI o automatico via `web_ui.py` en `/api/sync`.

## `hrv_app.hrv_sync_flow`
- Que hace:
  - Implementa el caso de uso principal del sync HRV.
  - Si `CORE` esta vacio, primero intenta reprocesar RR locales de `data/rr_downloads/`; si no existen, hace bootstrap corto desde Dropbox.
  - Resuelve rango de fechas y cubre `target_missing_dates` desde Dropbox (AYO-13-F4); si Dropbox no cubre una fecha nueva, esa fecha no entra al pipeline (sin fallback Polar).
  - Coordina escritura de RR, ejecucion de `build_hrv_core.py`, refresco de `sleep`, sync opcional con Intervals y reporting final.
- Cuando usarlo:
  - Indirectamente desde `polar_hrv_automation.py`.
  - Tambien como referencia cuando quieras entender el flujo operativo real sin leer el entrypoint.
- Entradas:
  - Argumentos CLI ya normalizados, cliente Polar, configuracion runtime y rutas base.
- Salidas:
  - Misma salida operativa del comando principal.
- Automatico o manual:
  - Automatico dentro del entrypoint.

## `hrv_app.config`
- Que hace:
  - Centraliza constantes operativas, rutas base, flags de runtime y mappings compartidos.
  - Evita que el entrypoint tenga estado global disperso.
- Cuando usarlo:
  - Siempre que un modulo operativo necesite paths, columnas canonicas o toggles runtime.

## `hrv_app.polar_utils`
- Que hace:
  - Reune parsers y helpers compartidos para variantes de campos Polar, duraciones, numericos, flags de entorno y extractos seguros de respuestas.
- Cuando usarlo:
  - Como soporte interno de clientes y UI; no es un entrypoint.

## `hrv_app.oauth_utils`
- Que hace:
  - Implementa el intercambio OAuth `code -> token`, registro de usuario y persistencia JSON atomica reutilizada por la UI web.
- Cuando usarlo:
  - Desde los flujos OAuth; no se ejecuta directamente.

## `hrv_app.polar_sessions`
- Que hace:
  - Resuelve matching de sesiones Intervals con ejercicios Polar y extrae la capa mecanica minima, incluyendo fallback FIT cuando aplica.
- Cuando usarlo:
  - Indirectamente desde `build_sessions.py` y el modulo `analysis/`; no es un entrypoint.

## `hrv_app.dropbox_rr`
- Que hace:
  - Escanea `RR.CSV` existentes por fecha.
  - Calcula fechas objetivo faltantes.
  - Lanza `egc_to_rr.py` para cubrir fechas desde Dropbox cuando esta habilitado.
  - Respeta `HRV_DROPBOX_RR_TIMEOUT_SEC` para evitar bloqueos indefinidos en el subprocess.
- Cuando usarlo:
  - Como capa operativa de cobertura RR principal.
- Importante:
  - Dropbox es la unica fuente de nuevos RR matinales (AYO-13-F4). Si una fecha nueva no esta cubierta en Dropbox, esa fecha no entra al pipeline en este ciclo; no hay fallback Polar para RR nuevos.
  - Correcciones de fechas ya existentes en CORE quedan fuera de alcance de F4 (requieren reprocesado manual del periodo, fuera de este flujo automatico).

## `hrv_app.polar_auth_v4`, `hrv_app.polar_client_v4`, `hrv_app.polar_adapters_v4`
- Que hacen:
  - `polar_auth_v4`: OAuth contra `auth.polar.com` con refresh token obligatorio, bundle separado (`polar_tokens_v4.json`) y rotacion atomica bajo lock.
  - `polar_client_v4`: cliente HTTP de la Dynamic API v4; lo consumen el gateway de sleep/nightly y `PolarSessionClient`.
  - `polar_adapters_v4`: convierte respuestas v4 al shape interno que consumen `sleep_store`, `hrv_sync_flow` y `polar_sessions`.
- Mascara `offline` en RR:
  - El adaptador añade `"offline": "0,1,0,..."` (mismo orden que `data`).
  - `hrv_app.hrv_sync_flow.extract_rr_ms` la consume: un RR en rango fisiologico pero marcado `offline=true` queda como artefacto.
  - No cambia el contrato del CSV RR ni los CSVs canonicos.
- Importante:
  - El catalogo de deportes usa `GET /v4/data/sports/list` y requiere el scope `sports:read`.
  - Los samples mecanicos en sesiones reales usan tipos string (`SPEED`, `CADENCE`, `POWER`/`LEFT_CRANK_CURRENT_POWER`).

## `hrv_app.sleep_store`
- Que hace:
  - Persiste y recalcula `ENDURANCE_HRV_sleep.csv`.
  - Normaliza campos de sleep y nightly recharge, hace upsert por fecha y recalcula derivados.
- Cuando usarlo:
  - Siempre que el flujo HRV necesite actualizar sueno/capas de recuperacion.

## `hrv_app.intervals_sync`
- Que hace:
  - Construye payloads wellness y resuelve el sync opcional con Intervals.icu.
  - Lee el ultimo master y agrega contexto de activities cuando hace falta.
- Cuando usarlo:
  - Solo como sidecar operativo del sync HRV.

## `hrv_app.cli_reporting`
- Que hace:
  - Genera el reporting textual del CLI y los resumenes diarios/7d.
  - Delega la traduccion humana de `gate_razon_base60` ("que paso"/"que hacer") a `hrv_app.gate_text`, manteniendo alias internos (`_format_gate_reason`, `_format_gate_next_step`) para no romper los call sites existentes.
- Cuando usarlo:
  - Cuando necesites presentation/output humano del flujo sin mezclarlo con la logica operativa.

## `hrv_app.gate_text`
- Que hace:
  - Traduce el codigo interno `gate_razon_base60` (ej. `2D_OK`, `2D_AMBOS`, `CAL/STAB/ART/NaN`, `BASE60_INSUF`) a dos textos independientes para el usuario: `format_gate_reason()` ("que paso") y `format_gate_next_step()` ("que hacer").
  - Para `CAL/STAB/ART/NaN`, si recibe la fila FINAL puede anexar pistas concretas (`Artifact_pct`, `HRV_Stability`, `Stability_Subtype`, `Tiempo_Estabilizacion`).
  - Es el modulo neutro compartido: antes esta logica vivia solo en `hrv_app.cli_reporting`; ahora tambien la consume `hrv_app.ui_view`/`web_ui.py` para que la web muestre el mismo texto que la CLI, sin duplicar el mapping.
- Cuando usarlo:
  - Siempre que necesites presentar `gate_razon_base60` en lenguaje humano (CLI o UI web). No cambia el gate ni su logica de decision, solo la traduccion textual.

## `hrv_app.ai` (`daily_brief`, `ssm_brief`)
- Que hace:
  - Rendering opcional de dos briefs mediante LLM, ambos con fallback determinista garantizado:
    - `daily_brief.run_ai_daily_brief_for_latest_date()`: reescribe la explicacion del gate HRV usando `reason_items` como capa primaria. Requiere `HRV_AI_ENABLED=1` y `HRV_AI_DAILY_ENABLED=1`. Persiste `ENDURANCE_HRV_ai_daily_brief_latest.json` en `DATA_DIR` y el historial fechado en `DATA_DIR/ai_briefs/daily/`.
    - `ssm_brief.run_ai_ssm_brief_for_latest_date()`: reescribe el brief SSM shadow desde el payload validado en `research/reports/iu16_ssm_brief_eval/prompt.md` (v4). Requiere `HRV_AI_ENABLED=1` y `HRV_AI_SSM_ENABLED=1`. Persiste `ENDURANCE_HRV_ai_ssm_brief_latest.json` en `DATA_DIR` y el historial fechado en `DATA_DIR/ai_briefs/ssm/`.
  - Ambos modulos construyen payloads pre-digeridos (sin campos crudos que el LLM pueda reinterpretar), llaman al modelo via OpenAI-compatible `chat/completions`, validan contrato de salida y persisten sidecars via `write_json_atomic`.
  - Idempotencia por `payload_hash` (SHA-256 del payload sin `generated_at`); si el hash coincide con el sidecar previo, no se vuelve a llamar al modelo.
  - Validacion `daily_brief`: `date`, `tone` alineado con `gate_final`, `source_mode` alineado con presencia de `reason_items`, `max_words` con margen 1.2x.
  - Validacion `ssm_brief`: `date`, `trigger_echo` y `relation_to_gate_echo` deben coincidir con el payload (canary de obediencia), `max_words` con margen 1.2x.
- Cuando usarlo:
  - `_run_ai_daily_brief_best_effort()` se llama en `hrv_app.hrv_sync_flow` tras `run_build_hrv_final_dashboard_only()`; `_run_ai_ssm_brief_best_effort()` tras `run_build_hrv_ssm_shadow_only()`. Fallo del LLM nunca aborta el sync.
  - La UI (`hrv_app.ui_view.build_view()`) prefiere el texto IA solo si el sidecar publica un texto validado; para el SSM exige ademas que `relation_to_gate` coincida con el calculado independientemente por Python. Cualquier divergencia cae al texto determinista.
- Entradas:
  - `daily_brief`: `ENDURANCE_HRV_master_FINAL.csv`, `ENDURANCE_HRV_sleep.csv`, `ENDURANCE_HRV_sessions_day.csv` (opcional), `ENDURANCE_HRV_master_FINAL_reason_items.json`.
  - `ssm_brief`: `ENDURANCE_HRV_ssm_shadow.csv`, `ENDURANCE_HRV_master_FINAL.csv`.
  - Variables `HRV_AI_*` (provider, model, base_url, api_key, temperature, top_p, max_tokens, thinking, timeout, language) definidas en `env.example`.
- Salidas:
  - Sidecars JSON con campos `status` (`ok`/`skipped_unchanged`/`not_applicable`/`validation_failed`/`error`/`disabled`/`missing_*`), `payload_hash`, `provider`, `model`, `prompt_version`, `published`, `summary`, `detail`, textos especificos por brief (`tone`/`source_mode` en daily; `relation_to_gate`/`trigger` en SSM), `validation_errors`, `model_output_preview`.

## `hrv_app.ui_view`
- Que hace:
  - Capa de presentacion (viewmodel) de la UI web. Centraliza el formato de strings y la composicion del arbol que consumen tanto las plantillas Jinja (SSR) como `static/ui.js` (rehidratacion via `/api/status`).
  - `compose_hrv_summary()` mantiene las claves historicas `hrv_summary_*` para no romper consumidores existentes.
  - `build_view()` produce el viewmodel versionado (`VIEW_VERSION`, hoy `3`) con `hrv_today` (incluye `quality`, `stability`, `raw_text`, `used_text`, `base_text`, el bloque `gate` con `badge`/`action`/`what_happened`/`what_to_do`, y `ssm_text`/`ssm_relation_to_gate`/`ssm_source_mode` que exponen el brief SSM shadow con trazabilidad de si viene del renderer IA o del fallback determinista) y `system` (estado de autorizacion y ultimo RR).
  - `base_text` usa `final_last_base60_ms` (precalculado por `web_ui.py`) si esta presente; si no, recalcula desde `ln_base60`.
- Cuando usarlo:
  - Es la unica fuente de verdad de textos/estructura para la tarjeta `Lectura HRV de hoy`; ni la plantilla Jinja ni `ui.js` deben conocer nombres crudos del pipeline (`gate_razon_base60`, `ln_base60`, etc.), solo el arbol que expone este modulo.

## `hrv_app.pipeline_runner`
- Que hace:
  - Encapsula el lanzamiento de los scripts de pipeline como subprocesos: `build_hrv_core.py`, `build_hrv_final_dashboard.py`, `build_hrv_ssm.py`, `build_hrv_ssm_validation.py` y `build_hrv_ssm_outcome_battery.py`.
  - Centraliza el entorno de subprocess (UTF-8), la construccion de comandos y el manejo de errores.
  - Expone funciones `run_build_hrv_*_only()` que devuelven bool segun exito.
- Cuando usarlo:
  - Siempre que el flujo principal necesite ejecutar builders sin mantener ese detalle en el entrypoint.

## `hrv_app.io_utils`
- Que hace:
  - Proporciona `write_csv_atomic`, `write_json_atomic`, `write_text_atomic` y `json_safe` compartidos por todos los módulos que escriben artefactos canónicos.
  - Todas las escrituras usan `tempfile + os.replace` con retry ante `PermissionError`.
- Cuando usarlo:
  - Lo importan `build_hrv_core.py`, `build_hrv_final_dashboard.py`, `build_sessions.py`, `build_hrv_ssm.py` y `hrv_app/backup_dropbox.py`. No se llama directamente desde el flujo operativo.

## `hrv_app.backup_dropbox`
- Que hace:
  - Backup opcional de los `ENDURANCE_HRV_*.csv/.json` de la raiz de `DATA_DIR` y del historial IA en `DATA_DIR/ai_briefs/**/ENDURANCE_HRV_*.json` a Dropbox tras un sync exitoso.
  - Sube los artefactos a `HRV_BACKUP_DROPBOX_PATH`, preservando la ruta relativa de `ai_briefs/` y sobrescribiendo cada archivo (Dropbox conserva versiones anteriores por su cuenta).
  - Restaura archivos desde Dropbox a `DATA_DIR` con escritura atómica, recreando subcarpetas como `ai_briefs/`, y backup previo de los archivos existentes en `data/backup/pre_restore/`.
  - Puede hacer auto-restore opt-in cuando `DATA_DIR` arranca vacío o con `CORE` ilegible, si `HRV_AUTO_RESTORE_ON_EMPTY_DATA=1`.
  - Reutiliza las credenciales Dropbox ya configuradas para la ingesta RR.
- Cuando usarlo:
  - El backup se ejecuta automáticamente al final de cada sync si `HRV_BACKUP_DROPBOX_ENABLED=1`.
  - La restauración se invoca desde `POST /api/restore-backup` en la UI web.
  - El auto-restore bloquea el sync si no deja un `CORE` usable tras la restauración.
  - NUNCA lanza excepciones en el backup (el sync continua); la restauración sí lanza si falta credencial, no hay archivos en `/hrv_backups/` o el restore no deja un `CORE` usable.
- Entradas:
  - Variables de entorno Dropbox (`DROPBOX_ACCESS_TOKEN` o refresh trio), `HRV_BACKUP_DROPBOX_PATH`, `HRV_AUTO_RESTORE_ON_EMPTY_DATA`.
- Salidas:
  - Archivos subidos/descargados a/desde Dropbox, dict de resultado con status.

## `hrv_app.polar_gateway`
- Que hace:
  - Gateway de sleep/nightly Polar usando v4 como unico transporte (AYO-22).
  - Coordina `polar_auth_v4`, `polar_client_v4` y `polar_adapters_v4` para obtener datos de sueno y nightly recharge.
- Cuando usarlo:
  - Lo importa `hrv_app.sleep_store`; no es un entrypoint.

## `hrv_app.run_manifest`
- Que hace:
  - Genera sidecars atomicos de trazabilidad (`*_manifest.json`) con hashes de inputs/outputs, configuracion efectiva y timestamp.
  - Proporciona `build_run_manifest()`, `artifact_signature()`, `file_digest()`, `stable_digest()`, `write_run_manifest_atomic()` y `utc_now_iso()`.
- Cuando usarlo:
  - Lo importan `build_hrv_core.py` y `build_hrv_final_dashboard.py` para dejar manifests atomicos tras cada corrida.

## `hrv_app.eval_utils`
- Que hace:
  - Proporciona `ols_predict`, `evaluate_predictor` y `bootstrap_delta_mae` compartidos por los modulos SSM.
  - `evaluate_predictor` calcula Spearman, holdout MAE/RMSE (80/20 OLS) y walk-forward MAE.
  - `bootstrap_delta_mae` da CI90 sobre la diferencia de MAE entre dos predictores (1000 iteraciones).
- Cuando usarlo:
  - Lo importa `build_hrv_ssm_outcome_battery.py`. No se llama directamente desde el flujo operativo.

## `egc_to_rr.py`
- Que hace:
  - Busca pares `ECG.jsonl` + `ACC.jsonl` en carpeta local o Dropbox.
  - Convierte cada par a un RR compatible con la app.
  - Guarda RR con nomenclatura tipo `ENDURANCE_YYYY-MM-DD_from_jsonl_RR.CSV`.
  - Puede guardar ficheros auxiliares en subcarpeta (por defecto `_aux_jsonl`).
- Cuando usarlo:
  - Manualmente para validar conversiones.
  - Automaticamente cuando lo invoca `polar_hrv_automation.py` para cubrir fechas faltantes.
- Entradas:
  - Local: `--input-dir` o `--ecg` + `--acc`.
  - Dropbox: `--dropbox-folder` + credenciales Dropbox.
  - Credenciales Dropbox segun fuente configurada.
- Salidas:
  - RR en `data/rr_downloads`.
  - Opcional: artefactos de apoyo en `_aux_jsonl`.
- Automatico o manual:
  - Ambos.

## `build_hrv_core.py`
- Que hace:
  - Procesa RR crudos.
  - Calcula metrica HRV estable por dia.
  - Genera:
    - `ENDURANCE_HRV_master_CORE.csv`
    - `ENDURANCE_HRV_master_BETA_AUDIT.csv`
- Cuando usarlo:
  - Siempre que quieras transformar RR en dataset CORE/AUDIT.
- Entradas:
  - RR (`--rr-file` o `--rr-dir`, normalmente `data/rr_downloads`).
- Salidas:
- CORE y BETA_AUDIT.
  - `ENDURANCE_HRV_master_CORE_manifest.json` como sidecar atómico de trazabilidad de la corrida.
- Automatico o manual:
  - Automatico dentro de `polar_hrv_automation.py --process`.
  - Tambien se puede correr manual.

## `build_hrv_final_dashboard.py`
- Que hace:
  - Lee CORE + sleep.
- Aplica la logica del decisor FINAL/DASHBOARD (decision operativa diaria).
  - Enriquce `reason_text` con contexto de sueno y carga.
  - Construye internamente `reason_items` estructurados y despues renderiza `reason_text` desde esa capa.
  - Publica ademas `ENDURANCE_HRV_master_FINAL_reason_items.json` como sidecar estable para consumo de `analysis/`.
  - Valida semanticamente cada motivo con enums cerrados de `layer` (`measured/proxy/inference/action`) y `severity` (`low/medium/high/very_high`).
  - Consume la capa de contexto canonico de carga desde `ENDURANCE_HRV_sessions_day.csv`:
    - `acwr_simple_prev`
    - `monotony_7d_prev`
    - `strain_7d_prev`
    - `load_ctx_ready`
  - Consume la capa de clustering reciente de intensidad:
    - `intense_day`
    - `intense_days_prev_3d`
    - `intense_days_prev_5d`
    - `intensity_clustering_flag`
    - `intensity_clustering_level`
  - Construye la capa de contexto de recuperacion multisenal sin tocar el gate:
    - `recovery_context_quality`
    - `recovery_support_class`
    - `recovery_discordance_flag`
    - `recovery_discordance_reason`
  - Si existe `ENDURANCE_HRV_sessions_day.csv`, usa sus campos de carga.
  - Genera:
    - `ENDURANCE_HRV_master_FINAL.csv` (66 columnas)
    - `ENDURANCE_HRV_master_DASHBOARD.csv`
- Cuando usarlo:
  - Siempre que quieras pasar de CORE a salida operativa FINAL/DASHBOARD.
- Entradas:
  - `ENDURANCE_HRV_master_CORE.csv`
- `ENDURANCE_HRV_sleep.csv`
  - Opcional: `ENDURANCE_HRV_sessions_day.csv`
- Salidas:
  - FINAL y DASHBOARD.
  - `ENDURANCE_HRV_master_FINAL_manifest.json` como sidecar atómico de trazabilidad de la corrida.
  - `reason_items` sigue sin exponerse como columna en `FINAL` ni en `DASHBOARD`, pero ahora tambien se serializa en `ENDURANCE_HRV_master_FINAL_reason_items.json`.
  - `FINAL` mantiene `gate_final`, `Action` y `Action_detail` como arbitros operativos.
  - La recuperación multiseñal solo aporta soporte o discordancia objetiva via columnas y `reason_text`.
  - El contexto de carga y el clustering solo aportan contexto en `reason_text`; no recolorean el gate.
  - El manifest de `FINAL/DASHBOARD` enlaza al manifest de `CORE` por ruta, hash de archivo y hash efectivo de configuración cuando está disponible.
  - `analysis/` puede tratar el sidecar como fuente estructurada primaria cuando `fallback_to_reason_text = false`, pero eso no cambia el contrato público de los CSV.
- Automatico o manual:
  - Automatico dentro de `polar_hrv_automation.py --process`.
  - Tambien se puede correr manual.

## `build_sessions.py`
- Que hace:
  - Extrae sesiones de entrenamiento desde Intervals API.
  - Construye:
    - `ENDURANCE_HRV_sessions.csv` (detalle por sesion)
    - `ENDURANCE_HRV_sessions_day.csv` (agregado diario + rolling)
    - `ENDURANCE_HRV_intensity_distribution_weekly.csv` (resumen semanal por deporte del patron de distribucion observada)
    - `ENDURANCE_HRV_weekly_coach.json` (resumen semanal estructurado con marcas de corte, cobertura y contexto retrospectivo de Z3)
    - `ENDURANCE_HRV_sessions_metadata.json`
    - `ENDURANCE_HRV_wellness_subjective.csv` (wellness subjetivo diario desde Intervals, si hay cobertura)
  - Canoniza la capa de señal mecanica minima en `sessions.csv` para deportes de pie:
    - `mechanics_source`
    - `run_power_*`
    - `speed_first_half`, `speed_second_half`
    - `cadence_first_half`, `cadence_second_half`
  - Canoniza la extracción mínima de coach metrics en `sessions.csv`:
    - `calories`
    - `average_cadence`
    - `average_weather_temp`
    - `hrr_drop_bpm`
    - `trimp`
    - y, si `device_watts=true`, `icu_weighted_avg_watts`, `icu_joules_above_ftp`, `icu_max_wbal_depletion`, `decoupling`
  - Canoniza la capa de contexto de carga en `sessions_day.csv`:
    - `acwr_simple_prev`
    - `monotony_7d_prev`
    - `strain_7d_prev`
    - `load_ctx_ready`
  - Canoniza la capa de clustering proactivo en `sessions_day.csv`:
    - `intense_day`
    - `intense_days_prev_3d`
    - `intense_days_prev_5d`
    - `intensity_clustering_flag`
    - `intensity_clustering_level`
  - Embebe la auditoria ligera por capas en `ENDURANCE_HRV_sessions_metadata.json`:
    - `training_audit.dataset_level`
    - `training_audit.signal_level`
    - `training_audit.metric_level`
  - No genera la capa local de terreno de `analysis`:
    - no persiste `terrain_context`
    - no persiste `terrain_fit_context`
    - no escribe `terrain_intervals.csv` ni `terrain_climbs.csv`
- Cuando usarlo:
  - Cuando quieras actualizar la capa de carga de entrenamiento.
  - Recomendado en cron separado (diario/backfill), no dentro del sync Polar.
- Entradas:
  - `INTERVALS_API_KEY`, `INTERVALS_ATHLETE_ID` y parametros (`--daily`, `--backfill`, `--update`, `--date`, `--oldest`, `--no-streams`, `--no-notes`).
- Modos utiles:
  - `--backfill`: historico completo desde `--oldest`.
  - `--daily`: ultimas 48h.
  - `--update`: desde el ultimo dia con datos hasta hoy, releyendo tambien ese ultimo dia.
  - `--date YYYY-MM-DD`: un dia concreto.
  - `--no-streams`: omite descarga y procesado de streams cuando quieres una corrida mas ligera.
  - `--no-notes`: omite notas/wellness textual cuando quieres minimizar dependencias de contenido libre.
  - `--output <dir>`: directorio de salida alternativo (por defecto usa `HRV_DATA_DIR`).
- Salidas:
  - CSVs de sesiones, distribucion semanal, wellness subjetivo y metadata.
  - `sessions.csv` pasa a ser la fuente canonica de detalle por sesion, incluidos coste, zonas, drift, mecanica minima y la extracción mínima cerrada de coach metrics por sesión.
  - `sessions_day.csv` pasa a ser la fuente canonica de rolling de carga y clustering para `reason_text`.
  - `intensity_distribution_weekly.csv` pasa a ser la salida canonica de distribucion observada por `sport x week`.
  - `ENDURANCE_HRV_weekly_coach.json` pasa a ser el sidecar canonico de resumen semanal estructurado para consumo posterior.
  - Ese sidecar puede incluir:
    - `z3_budget_by_sport` como lectura retrospectiva estructurada de percentil historico de Z3 por deporte o familia
    - `z3_budget_summary` como resumen corto visible en UI (`Contexto Z3 semanal`), deliberadamente asimetrico y solo surfaceado para bandas `high/very_high`
  - Esta capa sigue siendo retrospectiva y no introduce prescripcion automatica ni modifica `sessions_day`, `FINAL`, `DASHBOARD` o `reason_text`.
- Si `HRV_AUTO_RESTORE_ON_EMPTY_DATA=1`, el CLI intenta restaurar el directorio de salida antes de procesar cuando detecta un `CORE` vacío, ilegible o ausente.
  - `sessions_metadata.json` pasa a ser la fuente canonica de `training_audit` para rebajar confianza de coaching/carga sin bloquear pipeline.
- Automatico o manual:
  - Manual (no lo llama el flujo principal por defecto).

## `intervals_wellness_test.py`
- Que hace:
  - Script de prueba para hacer `PUT` de un campo wellness en Intervals.
  - Sirve para validar auth/payload/campo custom.
- Cuando usarlo:
  - Diagnostico tecnico puntual.
- Entradas:
  - API key, athlete id, fecha, field, value.
- Salidas:
  - Respuesta HTTP en consola.
- Automatico o manual:
  - Manual, no operativo.
- Ruta actual:
  - `scripts/python/intervals_wellness_test.py`

## `intervals_resting_hr_from_core.py`
- Que hace:
  - Lee `HR_stable` desde CORE y lo sube a wellness (`restingHR`) en Intervals.
  - Permite enviar un dia, rango, o todo el CSV.
- Cuando usarlo:
  - Backfill/correccion manual de `restingHR` en Intervals.
- Entradas:
  - `ENDURANCE_HRV_master_CORE.csv` + credenciales Intervals.
- Salidas:
  - Requests PUT a Intervals (sin generar CSV nuevo).
- Automatico o manual:
  - Manual, no parte del pipeline principal.
- Ruta actual:
  - `scripts/python/intervals_resting_hr_from_core.py`

## `add_ans_balance_to_core.py`
- Que hace:
  - Reprocesa RR y calcula metricas ANS:
    - `SI_baevsky`
    - `SD1`
    - `SD2`
    - `SD1_SD2_ratio`
  - Hace merge por `Fecha` dentro de `ENDURANCE_HRV_master_CORE.csv`.
- Cuando usarlo:
  - Analisis adicional o enriquecimiento de CORE.
- Entradas:
  - RR en `data/rr_downloads` (o `--rr-dir`) + CORE.
- Salidas:
  - CORE actualizado con columnas ANS.
- Automatico o manual:
  - Manual, fuera del flujo principal.
- Ruta actual:
  - `scripts/python/add_ans_balance_to_core.py`

## `build_historical_hrv_compare.py`
- Que hace:
  - Script historico/one-off para reconstruir contexto y comparar salidas sobre datasets antiguos.
  - Puede generar salidas temporales de comparativa con sufijos legacy, fuera del contrato canonico actual.
- Cuando usarlo:
  - Analisis historico, validaciones, comparativas de version.
- Entradas:
  - Fuentes historicas con rutas hardcodeadas (no pensado para Railway runtime actual).
- Salidas:
  - CSVs historicos de comparativa, no canónicos.
- Automatico o manual:
  - Manual, fuera del flujo operativo.
- Ruta actual:
  - `scripts/python/build_historical_hrv_compare.py`

## `build_hrv_ssm.py`
- Que hace:
  - Genera la capa sombra SSM de Fase 1: Banister de dos estados (lento/rapido) con observacion HRV matinal y observacion nocturna de sueno opcional como segunda fuente.
  - Escribe `ENDURANCE_HRV_ssm_shadow.csv` (30 cols) y `ENDURANCE_HRV_ssm_shadow_metadata.json`.
  - Expone `preprocess_base()` para precomputar la parte invariante (obs_quality, load_context, sleep_context) y `run_ssm_from_base()` para ejecutar solo el Kalman sobre un base ya procesado — util para validacion con multiples configuraciones sin recalcular lo costoso.
  - No modifica `FINAL.csv`, no toca el gate y no se expone en la UI operativa.
- Cuando usarlo:
  - Automaticamente tras `build_hrv_final_dashboard.py` en cada sync via `hrv_app.hrv_sync_flow`.
  - Manualmente: `python build_hrv_ssm.py [--data-dir <dir>]`.
  - Su parser es minimo: solo reconoce `--data-dir`; no ofrece `--help` y los argumentos desconocidos se ignoran.
- Entradas:
  - `ENDURANCE_HRV_master_CORE.csv`, `ENDURANCE_HRV_sessions_day.csv`, `ENDURANCE_HRV_sleep.csv` (opcional).
- Salidas:
  - `ENDURANCE_HRV_ssm_shadow.csv`, `ENDURANCE_HRV_ssm_shadow_metadata.json`.
- Automatico o manual:
  - Automatico en cada sync HRV. Manual disponible.

## `build_hrv_ssm_validation.py`
- Que hace:
  - Genera el reporte reproducible de validacion Fase 1 del modelo SSM: elige el outcome principal (FDS sobre `cardiac_drift_worst` normalizado por deporte), construye pares temporales, evalua SSM vs rolling vs load vs EWMA con walk-forward, bootstrap CI, estratificacion por deporte, comparador estructural (beta=0 vs ARX) y comparador de sueno.
  - Escribe `research/reports/ssm_validation/ENDURANCE_HRV_ssm_validation_report.json` y `.md`.
  - El resultado no forma parte del contrato estatico: debe leerse de `phase1_conclusion`, `go_no_go` y `primary_strict_by_sport` en el JSON regenerado.
  - No modifica el gate.
- Cuando usarlo:
  - Manualmente: `python build_hrv_ssm_validation.py [--data-dir <dir>] [--output-dir <dir>]`.
  - Por defecto escribe en `research/reports/ssm_validation/`; `--output-dir` permite aislar los resultados de una ejecución.
  - Bajo demanda cuando se quiera reevaluar si el SSM aporta valor; no forma parte del sync HRV diario.
  - O de forma agrupada via `python polar_hrv_automation.py --ssm-audit`, que primero regenera `ssm_shadow`.
- Entradas:
  - `ENDURANCE_HRV_ssm_shadow.csv`, `ENDURANCE_HRV_ssm_shadow_metadata.json`, `ENDURANCE_HRV_master_CORE.csv`, `ENDURANCE_HRV_sessions_day.csv`, `ENDURANCE_HRV_sessions.csv`, `ENDURANCE_HRV_sleep.csv`, `ENDURANCE_HRV_master_FINAL.csv`.
- Salidas:
  - `research/reports/ssm_validation/ENDURANCE_HRV_ssm_validation_report.json`, `research/reports/ssm_validation/ENDURANCE_HRV_ssm_validation_report.md`.
- Automatico o manual:
  - Manual bajo demanda.

## `build_hrv_ssm_outcome_battery.py`
- Que hace:
  - Prueba el predictor SSM contra outcomes alternativos a `cardiac_drift_worst`: `lnRMSSD_t+1` y `well_fatigue_raw_t+1`.
  - Incluye comparadores SSM, rolling HRV 7d, AR(1), EWMA grid y bootstrap CI.
  - Los hallazgos dependen del dataset: deben leerse en `outcomes` y `battery_conclusion` del JSON regenerado, no copiarse como una propiedad permanente del script.
  - No modifica el gate.
- Cuando usarlo:
  - Manualmente: `python build_hrv_ssm_outcome_battery.py [--data-dir <dir>] [--output-dir <dir>]`.
  - Por defecto escribe en `research/reports/ssm_validation/`; `--output-dir` permite aislar los resultados de una ejecución.
  - Bajo demanda, normalmente despues de lanzar la validacion SSM manual.
  - O de forma agrupada via `python polar_hrv_automation.py --ssm-audit`.
- Entradas:
  - `ENDURANCE_HRV_master_CORE.csv`, `ENDURANCE_HRV_ssm_shadow.csv`, `ENDURANCE_HRV_wellness_subjective.csv`.
- Salidas:
  - `research/reports/ssm_validation/ENDURANCE_HRV_ssm_outcome_battery.json`, `research/reports/ssm_validation/ENDURANCE_HRV_ssm_outcome_battery.md`.
- Automatico o manual:
  - Manual bajo demanda.

## 3) Resumen practico

Si tu pregunta es "que scripts importan para operar dia a dia":

1. `web_ui.py` (servidor web)
2. `polar_hrv_automation.py` (sync y orquestacion)
3. `egc_to_rr.py` (Dropbox/local JSONL -> RR, cuando faltan fechas o para validacion manual)
4. `build_hrv_core.py` (RR -> CORE/BETA)
5. `build_hrv_final_dashboard.py` (CORE -> FINAL/DASHBOARD + contexto de recuperación multiseñal)

Y aparte, opcionales recomendados:

1. `build_sessions.py` para mantener al dia `sessions.csv`, `sessions_day.csv`, `ENDURANCE_HRV_weekly_coach.json`, `sessions_metadata.json` y `wellness_subjective.csv`, y asi habilitar el clustering, la señal mecánica mínima, el contexto de carga, la auditoría por capas, el wellness subjetivo y el resumen semanal.
2. `build_hrv_ssm.py` se ejecuta automaticamente tras cada sync HRV para regenerar `ENDURANCE_HRV_ssm_shadow.csv`. `build_hrv_ssm_validation.py` y `build_hrv_ssm_outcome_battery.py` quedan como herramientas manuales bajo demanda: son sombra pura, no tocan `FINAL`, no recoloran el gate y sirven para reevaluar si el SSM aporta valor. El veredicto vigente debe leerse de los JSON regenerados, porque cambia con el dataset.
   - Entry point recomendado: `python polar_hrv_automation.py --ssm-audit`
3. `analysis\\analyze_session.py` o `analysis\\run_session_analysis.py` cuando quieras explotar la capa analitica local sin tocar contratos canonicos:
   - terreno (`GAP`, `VAM`, potencia por split y climbs FIT`; en `bike`, la capa FIT puede anadir potencia estimada local por subida)
   - `composite_context` (`subjective_coherence`, `thermal_context`, `durability_context`)
   - `narrative_targets` (`error_context`, `exit_context`, `final_reason_rendered`); `exit_context.block_role_signals.load_rank_in_sport_7d` usa una ventana real de 7 dias por deporte, no un recorte visual de sesiones recientes
   - para sesiones `trail_run`: capa shadow (`runaware_context`, `v1_shadow_history`) — validacion paralela del clustering v1 con senal de terreno y potencia de carrera; shadow-only, no modifica ningun contrato canonico
4. `analysis\\hrv_rebound_profile.py` cuando quieras revisar la absorcion HRV de forma retrospectiva por semana o por bloque, sin mezclar esa lectura con el gate diario ni con `sessions_day`.

## 4) Modulos de soporte en `analysis/` (no documentados como entrypoints)

Los siguientes scripts son modulos internos de la capa analitica local. No son entrypoints independientes; los consumen `analyze_session.py`, `run_session_analysis.py` y `analyze_weekly.py`:

- `session_analysis_pipeline.py` — Pipeline central: contiene `run_analysis()` y `prepare_bundle()`
- `session_cost_model.py` — Scoring cardio/mecanico por sesion
- `fit_speed_utils.py` — Calculo de metricas de velocidad desde FIT
- `fit_terrain_utils.py` — Analisis de terreno desde FIT (GAP, VAM, climbs)
- `training_audit_utils.py` — Utilidades de auditoria de calidad de entrenamiento
- `prepare_session_bundle.py` — Empaquetado de datos de sesion para analisis
- `run_session_analysis_batch.py` — Variante batch de `run_session_analysis.py`
- `run_weekly_analysis_prep.py` — Etapa de preparacion para analisis semanal
- `build_weekly_analysis_sidecars.py` — Generacion de sidecars semanales
- `efficiency_context_audit.py` — Auditoria de contexto de eficiencia
- `patch_speed_metrics.py` — Correccion/parche de metricas de velocidad
- `sya15_continuity.py` — Analisis de continuidad deportiva (SYA-15)
- `endurance_rr_session_v4.py` — Analisis RR de sesion con QA y gates DFA

