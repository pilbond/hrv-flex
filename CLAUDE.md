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
6. Este `CLAUDE.md` (guía adaptada para Claude Code; no prevalece sobre los documentos anteriores)

---

## Objetivo del Proyecto

Sistema automatizado HRV para un **único atleta**:
- Autentica con **Polar AccessLink** vía OAuth2 Authorization Code
- Intenta cubrir RR faltantes desde `ECG.jsonl + ACC.jsonl` en Dropbox primero
- Usa Polar como fallback cuando Dropbox no está disponible o falta cobertura
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
│   └── ENDURANCE_HRV_sessions_day.csv
├── scripts/                           # Scripts operativos locales
├── docs/
│   ├── contracts/                     # Norma HRV activa (esquemas, QA, gating)
│   └── legacy/                        # Documentación histórica (sensible)
├── analysis/                          # Módulo analítico local
│   ├── AGENTS.md
│   ├── ENDURANCE_AGENT_DOMAIN.md
│   └── SESSION_ANALYSIS_METHOD.md
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
| `ENDURANCE_HRV_master_FINAL.csv` | 58 | CORE + gates + contexto + reason_text |
| `ENDURANCE_HRV_master_DASHBOARD.csv` | 10 | Resumen operativo para dashboard |
| `ENDURANCE_HRV_sleep.csv` | 17 | Sueño Polar (sidecar; carga en sessions_day.csv) |
| `ENDURANCE_HRV_sessions.csv` | - | Sesiones Intervals.icu (histórico) |
| `ENDURANCE_HRV_sessions_day.csv` | - | Carga por día (usado por v4lite) |

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
- `GET /api/status` — estado actual
- `GET /health` — health check

**Regla crítica:** `/api/sync` y `/api/sync-sessions` **NO deben ejecutarse en paralelo**. El estado operativo es compartido; si uno está corriendo, el otro debe rechazarse.

### `polar_hrv_automation.py`
Orquestador del flujo principal.
- Descarga RR desde Polar AccessLink (`/v3/exercises`)
- Intenta cubrir RR faltantes desde **Dropbox primero**
- Fallback a Polar si Dropbox no cubre las fechas necesarias
- Ejecuta `build_hrv_core.py` (RR → CORE)
- Ejecuta `build_hrv_final_dashboard.py` (CORE + sleep + sessions_day → FINAL + DASHBOARD)
- Fetch sleep y nightly recharge de Polar; append/upsert a `ENDURANCE_HRV_sleep.csv`
- Push wellness a Intervals.icu (opcional, según config)

### `build_hrv_core.py`
Procesamiento de RR crudo.
`RR arrays` → `ENDURANCE_HRV_master_CORE.csv` + `ENDURANCE_HRV_master_BETA_AUDIT.csv`

**Nota:** NO modificar sin cambio de alcance explícito.

### `build_hrv_final_dashboard.py`
Decisor HRV con contexto.
Inputs: `CORE.csv` + `sleep.csv` + `sessions_day.csv` (ambos opcionales, solo para reason_text)
Outputs: `FINAL.csv` (58 cols) + `DASHBOARD.csv` (10 cols)
- Veto agudo: bypass ROLL3 si caída > 2×SWC bajo baseline
- Reason_text: contexto operativo (sueño, carga, nightly RMSSD discordancia)
- ln_pre_veto, swc_ln_floor: trazabilidad del veto

### `build_sessions.py`
Pipeline de sesiones desde Intervals.icu.
Genera:
- `ENDURANCE_HRV_sessions.csv` (histórico de sesiones)
- `ENDURANCE_HRV_sessions_day.csv` (carga agregada por día)
- `ENDURANCE_HRV_sessions_metadata.json`

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

### Requeridas
- `POLAR_CLIENT_SECRET` — secret OAuth
- `PORT` — puerto Flask

### Una de estas (al menos)
- `POLAR_CLIENT_ID` o `POLAR_CLIENT_ID2` (precedencia: `POLAR_CLIENT_ID2` si ambas)

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
```

### Dropbox RR
```
HRV_DROPBOX_RR_ENABLED=1
HRV_DROPBOX_RR_SCRIPT=egc_to_rr.py
HRV_DROPBOX_NO_AUX=1
HRV_DROPBOX_PAIR_LIMIT=<N>
HRV_DROPBOX_FOLDER_PATH=<path>
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
GET  /health
```

### Regla operativa de concurrencia
- `/api/sync` (HRV) y `/api/sync-sessions` (sesiones) **comparten estado en memoria**
- **NO ejecutar en paralelo**
- Si uno está corriendo, rechazar el otro (409 Conflict o similar)
- La UI web debe evitar permitir botones simultáneos

---

## Seguridad

- ❌ No commitear `.env`, `.polar_tokens.json`, RR personales, CSV personales
- ❌ No loguear tokens, `client_secret`, API keys
- ✅ Rotar secretos si se exponen
- ✅ **NUNCA** exponer tokens ni artefactos sensibles por HTTP
- ⚠️ Tratar `docs/legacy/` como material histórico sensible

---

## Criterios de Aceptación

1. `/auth` devuelve 302 a Polar con `redirect_uri` correcto
2. `/auth/callback` guarda tokens en `POLAR_TOKEN_PATH` atomicamente
3. `POST /api/sync` genera o actualiza `CORE`, `BETA_AUDIT`, `sleep`, `FINAL`, `DASHBOARD`
4. Tras redeploy, `/api/sync` sigue funcionando (volumen persistente)
5. Logs útiles, sin secretos
6. RR se almacenan y leen desde `data/rr_downloads/`
7. Cobertura RR: **Dropbox primero**, fallback Polar si faltan fechas
8. `POST /api/sync-sessions` ejecuta `build_sessions.py --update`
9. UI web no permite ejecutar `/api/sync` y `/api/sync-sessions` simultáneamente

---

## Comandos Operativos

### Windows local
```bash
scripts\run-web-ui.bat
scripts\run-python.bat
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

---

## Snapshot Actual (2026-03-23)

### HRV global
- ✅ UI expone `/api/sync`, `/api/sync-sessions`, `/api/status`, endpoints OAuth
- ✅ `build_sessions.py` genera sesiones + metadata
- ✅ Flujo recomendado: Dropbox primero, Polar fallback
- ✅ `ENDURANCE_HRV_sleep.csv` es archivo canónico de sueño (17 cols; carga en sessions_day.csv)
- ✅ UI no permite ejecutar sync HRV y sync-sessions simultáneamente
- ✅ UI prioriza bloque técnico visible
- ✅ Veto agudo + reason_text en v4lite operativo
- ✅ Fetch sleep/nightly/intervals en polar_hrv_automation.py operativo

### Análisis de sesiones (v4 nuevo)
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
- `C:\Users\francisco.delgadosi\OneDrive - Plexus Tech\Documentos\RR\polar-hrv-automation_railway_v4\`

NO desde worktrees como:
- `.claude/worktrees/*`

