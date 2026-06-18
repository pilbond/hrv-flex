# CLAUDE.md - Polar HRV Automation (Railway) V4

Documento de apoyo operativo y arquitectura para Claude Code. **Autoridad operativa principal:** `AGENTS.md`

---

## Alcance & Precedencia

Este archivo es **subordinado a `AGENTS.md`** y solo concreta o replica:
- Estructura del proyecto y componentes
- Rutas canónicas de datos y outputs
- Runtime, variables de entorno, endpoints
- Seguridad y política de cambios

**Jerarquía documental del repositorio:**
1. `AGENTS.md` (operación global, runtime, endpoints, despliegue)
2. `docs/contracts/` (contratos HRV, esquemas, QA, gating)
3. `analysis/AGENTS.md` (reglas locales del módulo analítico)
4. `analysis/ENDURANCE_AGENT_DOMAIN.md` (rol, tono, baseline fisiológico)
5. `analysis/SESSION_ANALYSIS_METHOD.md` (método operativo del análisis)
6. `research/AGENTS.md` (enrutado de experimentos y auditorías no operativas)
7. Este `CLAUDE.md` (guía adaptada para Claude Code; no prevalece sobre los documentos anteriores)

---

## Objetivo del Proyecto

Sistema automatizado HRV para un **único atleta**:
- Autentica con **Polar AccessLink** vía OAuth2 Authorization Code
- Cubre nuevos RR matinales desde `ECG.jsonl + ACC.jsonl` en Dropbox, su única fuente (AYO-13-F4): si una fecha nueva no está en Dropbox, no entra al pipeline en ese ciclo; no hay fallback Polar para RR nuevos
- El histórico de `CORE` generado anteriormente con RR de Polar se conserva sin migración retroactiva
- Procesa RR con `build_hrv_core.py` → `CORE.csv` + `BETA_AUDIT.csv`
- Genera `FINAL.csv` y `DASHBOARD.csv` con `build_hrv_final_dashboard.py`
- Expone UI web Flask con endpoints de sincronización
- Sincroniza wellness a Intervals.icu (opcional)
- Se despliega en **Railway** con volumen persistente en `/data`

---

## Alcance Funcional

**Regla NO negociable:** Este es un proyecto **N=1** (uso personal de un único atleta).

- ❌ No es producto multiusuario
- ❌ No introducir abstracciones multi-athlete ni multi-tenant sin cambio de alcance explícito
- ❌ No soportar multi-cuenta ni selección de atleta sin autorización explícita
- ✅ Priorizar simplicidad operativa, trazabilidad, robustez

---

## Estructura del Repositorio

```
├── data/                              # Datos operativos
│   ├── rr_downloads/                 # RR crudos, reprocesables
│   ├── ENDURANCE_HRV_sleep.csv       # Sueño Polar (sin carga; carga en sessions_day.csv)
│   ├── ENDURANCE_HRV_master_CORE.csv
│   ├── ENDURANCE_HRV_master_FINAL.csv
│   ├── ENDURANCE_HRV_master_DASHBOARD.csv
│   ├── ENDURANCE_HRV_sessions.csv
│   ├── ENDURANCE_HRV_sessions_day.csv
│   ├── ENDURANCE_HRV_intensity_distribution_weekly.csv
│   ├── ENDURANCE_HRV_weekly_coach.json
│   ├── ENDURANCE_HRV_sessions_metadata.json
│   └── ENDURANCE_HRV_wellness_subjective.csv
├── scripts/                           # Scripts operativos locales
├── docs/
│   ├── contracts/                     # Norma HRV activa (esquemas, QA, gating)
│   └── legacy/                        # Documentación histórica (sensible)
├── hrv_app/                           # Paquete interno Python (ARQ-02)
│   ├── __init__.py
│   ├── config.py
│   ├── polar_utils.py
│   ├── oauth_utils.py
│   ├── pipeline_runner.py
│   ├── cli_reporting.py
│   ├── polar_sessions.py
│   ├── dropbox_rr.py
│   ├── intervals_sync.py
│   ├── sleep_store.py
│   ├── hrv_sync_flow.py
│   └── backup_dropbox.py
├── analysis/                          # Módulo analítico local
│   ├── AGENTS.md
│   ├── ENDURANCE_AGENT_DOMAIN.md
│   └── SESSION_ANALYSIS_METHOD.md
├── research/                          # Experimentos, auditorías e informes no operativos
│   ├── AGENTS.md
│   ├── README.md
│   ├── experiments/
│   ├── audits/
│   ├── reports/
│   └── archive/
├── web_ui.py                          # Flask + UI móvil
├── polar_hrv_automation.py            # Orquestador principal
├── build_hrv_core.py                   # RR → CORE + BETA_AUDIT
├── build_hrv_final_dashboard.py                # CORE + sleep → FINAL + DASHBOARD
├── build_sessions.py                  # Pipeline sesiones Intervals.icu
├── egc_to_rr.py                       # ECG.jsonl + ACC.jsonl → RR
├── Dockerfile                         # Python 3.11-slim
├── requirements_web.txt               # Deps web + pipeline (incluye scipy)
├── AGENTS.md                          # Documento padre
├── CLAUDE.md                          # Este archivo
└── .gitignore                         # (contiene .env, tokens, datos personales)
```

---

## Outputs Canónicos

| Archivo | Columnas | Propósito |
|---------|----------|-----------|
| `ENDURANCE_HRV_master_CORE.csv` | 18 | RR procesado, métricas base |
| `ENDURANCE_HRV_master_BETA_AUDIT.csv` | 13 | Auditoría RR, diagnostics |
| `ENDURANCE_HRV_master_FINAL.csv` | 66 | CORE + gates + contexto + reason_text + recuperación multiseñal |
| `ENDURANCE_HRV_master_DASHBOARD.csv` | 10 | Resumen operativo para dashboard |
| `ENDURANCE_HRV_sleep.csv` | 17 | Sueño Polar (sidecar; carga en sessions_day.csv) |
| `ENDURANCE_HRV_sessions.csv` | - | Sesiones Intervals.icu (histórico) |
| `ENDURANCE_HRV_sessions_day.csv` | 61 | Carga por día + rolling con cobertura + clustering reciente de intensidad + distribución rolling + `elev_loss_7d_sum` |
| `ENDURANCE_HRV_sessions_metadata.json` | - | `training_audit` por capas (`dataset_level`, `signal_level`, `metric_level`) |
| `ENDURANCE_HRV_intensity_distribution_weekly.csv` | - | Distribución observada por `sport x week` con patrón y confianza |
| `ENDURANCE_HRV_weekly_coach.json` | - | Sidecar semanal con `planning_note`, cobertura y contexto retrospectivo `SYA-14` (`z3_budget_by_sport`, `z3_budget_summary`) visible en `/api/status` |
| `ENDURANCE_HRV_wellness_subjective.csv` | - | Sidecar local para bienestar subjetivo |
| `ENDURANCE_HRV_ssm_shadow.csv` | - | Shadow diario de SSM regenerado por `build_hrv_ssm.py` |

---

## Arquitectura Operativa

### `web_ui.py`
Flask + UI móvil.
Endpoints:
- `GET /` — inicio
- `GET /auth` — redirige a Polar OAuth
- `GET /auth/callback`, `/oauth/callback` — intercambio de code → tokens
- `POST /api/sync` — ejecuta `polar_hrv_automation.py --process` en thread
- `POST /api/sync-sessions` — ejecuta `build_sessions.py --update` en thread
- `POST /api/import-seed` — importa seed/artefactos auxiliares
- `POST /api/restore-backup` — restaura CSV canónicos desde el último backup en Dropbox
- `POST /api/delete-latest-rr` — elimina el ultimo RR ingerido
- `GET /api/status` — estado actual
- `GET /health` — health check

**Regla crítica:** `/api/sync`, `/api/sync-sessions`, `/api/import-seed`, `/api/restore-backup` y `/api/delete-latest-rr` **NO deben ejecutarse en paralelo**. El estado operativo es compartido; si uno está corriendo, el otro debe rechazarse.

### `polar_hrv_automation.py`
Orquestador del flujo principal.
- Cubre RR nuevos faltantes desde **Dropbox**, su única fuente (AYO-13-F4); si una fecha nueva no está en Dropbox, no entra al pipeline en este ciclo (sin fallback Polar)
- `--all` reprocesa solo RR ya presentes en disco, sin descargar nada nuevo
- Solo consulta ejercicios Polar (`/v3/exercises`) en modo diagnóstico `--debug-sports`
- Ejecuta `build_hrv_core.py` (RR → CORE)
- Ejecuta `build_hrv_final_dashboard.py` (CORE + sleep + sessions_day → FINAL + DASHBOARD)
- Ejecuta `build_hrv_ssm.py` cuando corresponde para regenerar `ENDURANCE_HRV_ssm_shadow.csv`
- `build_hrv_ssm_validation.py` y `build_hrv_ssm_outcome_battery.py` quedan como auditorias manuales bajo demanda
- Fetch sleep y nightly recharge de Polar; append/upsert a `ENDURANCE_HRV_sleep.csv`
- Push wellness a Intervals.icu (opcional, según config)

### `build_hrv_core.py`
Procesamiento de RR crudo.
`RR arrays` → `ENDURANCE_HRV_master_CORE.csv` + `ENDURANCE_HRV_master_BETA_AUDIT.csv`

**Nota:** NO modificar sin cambio de alcance explícito.

### `build_hrv_final_dashboard.py`
Decisor HRV con contexto.
Inputs: `CORE.csv` + `sleep.csv` + `sessions_day.csv` (ambos opcionales, solo para reason_text)
Outputs: `FINAL.csv` (66 cols) + `DASHBOARD.csv` (10 cols)
- `load_3d`, la capa canonica `ACWR/monotony/strain` y el clustering reciente de intensidad se consumen solo como contexto de `reason_text`
- `FINAL` integra la capa RE-01 sin tocar el gate HRV

### `build_sessions.py`
Pipeline de sesiones desde Intervals.icu.
Genera:
- `ENDURANCE_HRV_sessions.csv` (histórico de sesiones)
- `ENDURANCE_HRV_sessions_day.csv` (carga agregada por día + rolling + clustering)
- `ENDURANCE_HRV_intensity_distribution_weekly.csv` (distribución semanal por deporte)
- `ENDURANCE_HRV_weekly_coach.json` (resumen semanal estructurado para UI/coach)
- `ENDURANCE_HRV_sessions_metadata.json`
- `ENDURANCE_HRV_wellness_subjective.csv`

Canoniza la capa mecánica mínima para deportes de pie, el contexto de carga `ACWR/monotony/strain`, `training_audit`, la distribución observada semanal por deporte y el sidecar weekly coach.

Desde `SYA-14`, `ENDURANCE_HRV_weekly_coach.json` puede incluir:
- `z3_budget_by_sport`: lectura retrospectiva estructurada del percentil histórico de Z3 por deporte o familia
- `z3_budget_summary`: resumen corto para UI (`Contexto Z3 semanal`)

Regla de alcance:
- esta señal sigue siendo retrospectiva
- no modifica `sessions_day`, `FINAL`, `DASHBOARD` ni `reason_text`
- no introduce prescripción automática

Soporta: `--backfill`, `--daily`, `--update`, `--date`

### `egc_to_rr.py`
Convierte pares `ECG.jsonl + ACC.jsonl` (Dropbox) a RR compatibles.
Uso recomendado: local o Dropbox, **NO producción**.

---

## Runtime Defaults

Si no hay variables de entorno:

```
HRV_DATA_DIR = data
RR_DOWNLOAD_DIR = data/rr_downloads
POLAR_TOKEN_PATH = .polar_tokens.json
```

Datos operativos:
- **RR nuevos:** `data/rr_downloads/`
- **CSV maestros, sleep, sessions:** `data/`

---

## Variables de Entorno

### Requeridas para OAuth
- `POLAR_CLIENT_SECRET` — secret OAuth

### Una de estas (al menos)
- `POLAR_CLIENT_ID` o `POLAR_CLIENT_ID2` (precedencia: `POLAR_CLIENT_ID2` si ambas)

`PORT` lo proporciona Railway en producción; en local es opcional y usa `8080` por defecto.

### Muy recomendadas
```
PUBLIC_URL=https://tu-app.up.railway.app
POLAR_TOKEN_PATH=/data/polar_tokens.json
HRV_DATA_DIR=/data
RR_DOWNLOAD_DIR=/data/rr_downloads
INTERVALS_API_KEY=<key>
INTERVALS_ATHLETE_ID=<id>
```

### Operativas
```
HRV_QUIET=1                          # logs mínimos
HRV_DISABLE_BACKUP=1                 # no respaldar CSVs
HRV_SYNC_TIMEOUT_SEC=300             # timeout sync
HRV_UI_KEY=<clave>                   # opcional: protege /api/* (header X-HRV-KEY o ?key=); sin definir = sin auth
HRV_STALE_MAX_DAYS=3                 # umbral de /health?strict=1 (503 si FINAL más viejo o ausente)
HRV_BACKUP_DROPBOX_ENABLED=1         # opcional: backup de ENDURANCE_HRV_* a Dropbox (carpeta plana, overwrite) tras sync exitoso
HRV_BACKUP_DROPBOX_PATH=/hrv_backups # carpeta del backup en Dropbox
```

### Especializadas
```
POLAR_USER_NAME=Polar_User
POLAR_TZ_OFFSET_MIN=0
INTERVALS_BASE_URL=https://intervals.icu
ATHLETE_WEIGHT_KG=68.0
SYSTEM_BIKE_WEIGHT_KG=80.0
HRV_WARNING_MODE=adaptive90          # adaptive90 | healthy85 | p20
HRV_HEALTHY_START=2025-07-01
HRV_HEALTHY_END=2025-09-30
HRV_SSM_REASON_TEXT_ENABLED=0        # experimental; mantener deshabilitado
```

### Dropbox RR
```
HRV_DROPBOX_RR_ENABLED=1
HRV_DROPBOX_RR_SCRIPT=egc_to_rr.py
HRV_DROPBOX_NO_AUX=1
HRV_DROPBOX_PAIR_LIMIT=<N>
HRV_DROPBOX_FOLDER_PATH=<path>
# Aliases legacy: DROPBOX_FOLDER_PATH, ECG_RR_DROPBOX_FOLDER
HRV_DROPBOX_RECURSIVE=1
DROPBOX_ACCESS_TOKEN=<token>
# O: DROPBOX_REFRESH_TOKEN + DROPBOX_APP_KEY + DROPBOX_APP_SECRET
```

---

## Persistencia & OAuth en Railway

### Principio NO negociable en producción
- Un único flujo OAuth web
- **Prohibido:** abrir navegador desde backend
- **Prohibido:** HTTPServer local para callback en producción

### Setup de volumen Railway
```
/data (montado en el contenedor)
├── polar_tokens.json      # tokens Polar (atómicos)
├── ENDURANCE_HRV_*.csv
└── rr_downloads/
```

### Flujo OAuth esperado
1. Usuario abre `GET /auth`
2. Backend redirige a Polar AccessLink
3. Polar redirige a `/auth/callback` o `/oauth/callback`
4. Backend intercambia `code` → tokens
5. Persist atómico en `POLAR_TOKEN_PATH`

**Reglas:**
- Escribir tokens **atomicamente**
- **NUNCA** exponer tokens por HTTP
- `x_user_id` se guarda en token response y se usa para sleep/nightly endpoints

---

## Endpoints & Jobs

### Contrato de endpoints
```
GET  /
GET  /auth
GET  /auth/callback
GET  /oauth/callback
POST /api/sync
POST /api/sync-sessions
GET  /api/status
POST /api/import-seed
POST /api/restore-backup
POST /api/delete-latest-rr
GET  /health
```

### Regla operativa de concurrencia
- Todos los endpoints POST operativos (`/api/sync`, `/api/sync-sessions`, `/api/import-seed`, `/api/restore-backup`, `/api/delete-latest-rr`) **comparten estado en memoria**
- **NO ejecutar en paralelo**
- Si uno está corriendo, rechazar el otro (409 Conflict o similar)
- La UI web debe evitar permitir botones simultáneos

---

## Seguridad

- ❌ No commitear `.env`, `.polar_tokens.json`, RR personales, CSV personales
- ❌ No loguear tokens, `client_secret`, API keys
- ✅ Rotar secretos si se exponen
- ✅ **NUNCA** exponer tokens ni artefactos sensibles por HTTP
- ⚠️ Tratar `research/archive/` como material histórico sensible

---

## Criterios de Aceptación

1. `/auth` devuelve 302 a Polar con `redirect_uri` correcto
2. `/auth/callback` guarda tokens en `POLAR_TOKEN_PATH` atomicamente
3. `POST /api/sync` genera o actualiza `CORE`, `BETA_AUDIT`, `sleep`, `FINAL`, `DASHBOARD`
4. Tras redeploy, `/api/sync` sigue funcionando (volumen persistente)
5. Logs útiles, sin secretos
6. RR se almacenan y leen desde `data/rr_downloads/`
7. Cobertura RR: **Dropbox es la única fuente de nuevos RR matinales** (AYO-13-F4); si una fecha nueva no está en Dropbox, no entra a `CORE` en ese ciclo (sin fallback Polar)
8. `POST /api/sync-sessions` ejecuta `build_sessions.py --update`
9. Los jobs mutables de la UI comparten estado y no se ejecutan simultáneamente
10. `POST /api/restore-backup` descarga el último backup de Dropbox a `DATA_DIR` con escritura atómica

---

## Comandos Operativos

### Windows local
```bash
scripts\run-web-ui.bat
scripts\run-hrv.bat
```

### Pipeline sesiones
```bash
python build_sessions.py --update
python build_sessions.py --backfill
python build_sessions.py --daily
python build_sessions.py --date 2026-03-19
```

### Conversión manual (Dropbox → RR)
```bash
python egc_to_rr.py --dropbox-folder /ruta/carpeta --dropbox-recursive --outdir data/rr_downloads
```

---

## Política de Cambios

- ✅ Cambios mínimos, bien acotados
- ✅ Compatibilidad Python 3.11
- ✅ Evitar nuevas dependencias salvo valor claro
- ✅ Preservar nombres, rutas, outputs operativos (salvo instrucción explícita)
- ✅ **NO reintroducir** rutas/outputs/flujos ya retirados sin cambio de alcance explícito

### Si un cambio afecta a:
- Lógica HRV
- Esquema de columnas
- Criterios QA
- Gating o semáforos
- Significado operativo de métricas

**→ Actualizar `docs/contracts/` también**

### Investigación y auditorías

- `analysis/` queda reservado al producto funcional de análisis de sesiones y semanas.
- Hipótesis, benchmarks, auditorías, revisiones por IA y experimentos no adoptados van en `research/`.
- Antes de crear contenido exploratorio, leer `research/AGENTS.md`.
- Guardar scripts en `research/**/scripts/` y outputs en `research/reports/` o en el subárbol del experimento.
- No escribir resultados junto al código ni importar `research/` desde la aplicación.

---

## Snapshot Actual (2026-06-12)

### HRV global
- ✅ ARQ-02 (AYO-11): módulos internos reorganizados en `hrv_app/`; entrypoints de raíz (`web_ui.py`, `polar_hrv_automation.py`, `build_sessions.py`) intactos
- ✅ UI expone `/api/sync`, `/api/sync-sessions`, `/api/status`, `/api/import-seed`, `/api/restore-backup`, `/api/delete-latest-rr` y endpoints OAuth
- ✅ `build_sessions.py` genera `sessions`, `sessions_day`, `intensity_distribution_weekly`, `weekly_coach`, `sessions_metadata` y `wellness_subjective`
- ✅ AYO-13-F4 / AYO-20: Dropbox es la única fuente de nuevos RR matinales; sin fallback Polar para fechas nuevas (`--all` reprocesa solo RR locales; `list_exercises` queda detrás de `--debug-sports`)
- ✅ AYO-22 (AYO-13-F6): v3 completamente retirado; v4 es el único runtime Polar; `polar_client.py`, `polar_oauth_local.py` y `polar_shadow.py` eliminados; `POLAR_API_VERSION` y `POLAR_V4_SESSIONS` suprimidos; `analysis/session_analysis_pipeline.py` sin dependencias legacy v3
- ✅ `ENDURANCE_HRV_sleep.csv` es archivo canónico de sueño (17 cols; carga en sessions_day.csv)
- ✅ Los jobs HRV, sesiones, import seed, restore backup y borrado del último RR comparten estado y no se ejecutan simultáneamente
- ✅ `hrv_app/backup_dropbox.py`: backup opcional de `ENDURANCE_HRV_*` a carpeta plana en Dropbox (`HRV_BACKUP_DROPBOX_ENABLED`, overwrite tras cada sync); restauración vía `POST /api/restore-backup` con escritura atómica y backup previo en `data/backup/pre_restore/`
- ✅ `/health?strict=1` devuelve 503 si el FINAL falta o su última fecha supera `HRV_STALE_MAX_DAYS` (default 3); sin `strict` sigue siendo 200 (liveness)
- ✅ Si `HRV_UI_KEY` está definida, todos los `/api/*` exigen la clave vía header `X-HRV-KEY` o `?key=`; OAuth `state` validado con TTL y uso único
- ✅ `build_hrv_core.py`, `build_hrv_final_dashboard.py` y `build_sessions.py` usan `hrv_app.io_utils` para escrituras atómicas (eliminadas implementaciones locales duplicadas)
- ✅ CI en `.github/workflows/tests.yml`: pytest en push/PR, Python 3.11
- ✅ `sessions_day.csv` incluye carga canonica, clustering reciente de intensidad y señal `DO-02`
- ✅ `sessions_metadata.json` incluye `training_audit` por capas para gobernar confianza de coaching/carga
- ✅ `weekly_coach.json` expone tambien la capa `SYA-14` como contexto retrospectivo de Z3 por deporte sin tocar el gate
- ✅ `build_hrv_ssm.py` se ejecuta en el sync diario para regenerar `ENDURANCE_HRV_ssm_shadow.csv`; `build_hrv_ssm_validation.py` y `build_hrv_ssm_outcome_battery.py` quedan como auditorias manuales
- ✅ `build_hrv_final_dashboard.py` consume `load_3d`, `ACWR/monotony/strain` y clustering reciente de intensidad solo como contexto de `reason_text`
- ✅ Fetch sleep/nightly/intervals en `polar_hrv_automation.py` operativo
- ✅ Capa de recuperación multiseñal en FINAL (66 cols); `recovery_support_class`, `recovery_discordance_flag` y `recovery_discordance_reason` sin tocar el gate
- ✅ RE-02: sidecar `ENDURANCE_HRV_wellness_subjective.csv` (17 cols) para análisis retrospectivo; no alimenta `reason_text`
- ✅ DO-01: sidecar `ENDURANCE_HRV_intensity_distribution_weekly.csv` (21 cols); distribución observada por `sport × semana ISO` con patrón (`polarized`, `pyramidal`, `threshold`, `mixed`) y confianza explícita; no alimenta el gate

### Análisis de sesiones
- ✅ `analysis/analyze_session.py` tolera sesiones sin RR exportable
- ✅ RR es opcional: `prepare_bundle()` registra fallo sin crashear
- ✅ `run_analysis()` bifurca: con RR→análisis completo; sin RR→análisis degradado con cost model
- ✅ `render_report_markdown()` omite secciones RR cuando `rr_unavailable=true`
- ✅ Report parcial sin RR mantiene cardio/mecánico score + contexto intactos
- ✅ Documentación actualizada: `AGENTS.md`, `SESSION_ANALYSIS_METHOD.md`, `GUIA_PYTHON_SCRIPTS.md`

Si este snapshot queda desactualizado, actualizar o reducir.

---

## Referencias & Documentación

- `AGENTS.md` — Detalle arquitectónico y operativo
- `docs/contracts/ENDURANCE_HRV_Spec_Tecnica.md` — Especificación técnica HRV
- `docs/contracts/ENDURANCE_HRV_Estructura.md` — Esquema de CSVs
- `docs/contracts/ENDURANCE_HRV_Diccionario.md` — Diccionario de columnas
- `docs/contracts/PROCEDIMIENTO_RECOMENDADO.md` — Flujo operativo diario
- `docs/contracts/GUIA_PYTHON_SCRIPTS.md` — Guía de scripts


## Archivos canónicos

Siempre leer desde:
- `C:\Pilbond\polar-hrv-automation\`

NO desde:
- `C:\Users\francisco.delgadosi\OneDrive - Plexus Tech\Documentos\RR\polar-hrv-automation_railway_v4\` (copia OneDrive desactualizada)
- `.claude/worktrees/*`

## Workflow Kanvas

Si existe `Project.canvas` en la raiz del proyecto, usar Kanvas como tablero visual de tareas.

Reglas:
- Nunca editar `Project.canvas` directamente.
- Todas las modificaciones del canvas deben hacerse con el CLI de Kanvas.
- CLI canonico desde la raiz del repositorio:
  `python canvas-tool.py Project.canvas <command>`
- Al inicio de cada sesion:
  `python canvas-tool.py Project.canvas status`
- Si hay inconsistencias visuales o tareas sin ID:
  `python canvas-tool.py Project.canvas normalize`

Politica de estados:
- `purple`: propuesta del agente
- `red`: tarea aprobada y lista
- `orange`: en curso
- `cyan`: terminada por el agente, pendiente de revision humana
- `green`: solo el humano puede marcarla como completada
- `gray`: bloqueada por dependencias

Permisos del agente:
- Puede leer el tablero con `status`, `show`, `list`, `ready`, `blocked`, `blocking`, `dump`
- Puede proponer tareas con `propose`, `batch`, `propose-group`
- Puede empezar y cerrar trabajo con `start`, `finish`, `pause`
- Puede editar solo tareas en `orange` con `edit`
- Puede anadir dependencias con `add-dep`
- No puede marcar tareas en `green`
- No puede borrar tarjetas ni editar el JSON del canvas a mano

Integracion con este repositorio:
- Las reglas operativas de `polar-hrv-automation` siguen teniendo prioridad
- Kanvas solo organiza planificacion, dependencias y estado del trabajo
- Si hay conflicto entre Kanvas y las reglas del dominio HRV, manda `AGENTS.MD` del proyecto y la documentacion de `docs/contracts/`

<!-- code-review-graph MCP tools -->
## MCP Tools: code-review-graph

**IMPORTANT: This project has a knowledge graph. ALWAYS use the
code-review-graph MCP tools BEFORE using Grep/Glob/Read to explore
the codebase.** The graph is faster, cheaper (fewer tokens), and gives
you structural context (callers, dependents, test coverage) that file
scanning cannot.

### When to use graph tools FIRST

- **Exploring code**: `semantic_search_nodes` or `query_graph` instead of Grep
- **Understanding impact**: `get_impact_radius` instead of manually tracing imports
- **Code review**: `detect_changes` + `get_review_context` instead of reading entire files
- **Finding relationships**: `query_graph` with callers_of/callees_of/imports_of/tests_for
- **Architecture questions**: `get_architecture_overview` + `list_communities`

Fall back to Grep/Glob/Read **only** when the graph doesn't cover what you need.

### Key Tools

| Tool | Use when |
|------|----------|
| `detect_changes` | Reviewing code changes — gives risk-scored analysis |
| `get_review_context` | Need source snippets for review — token-efficient |
| `get_impact_radius` | Understanding blast radius of a change |
| `get_affected_flows` | Finding which execution paths are impacted |
| `query_graph` | Tracing callers, callees, imports, tests, dependencies |
| `semantic_search_nodes` | Finding functions/classes by name or keyword |
| `get_architecture_overview` | Understanding high-level codebase structure |
| `refactor_tool` | Planning renames, finding dead code |

### Workflow

1. The graph auto-updates on file changes (via hooks).
2. Use `detect_changes` for code review.
3. Use `get_affected_flows` to understand impact.
4. Use `query_graph` pattern="tests_for" to check coverage.
