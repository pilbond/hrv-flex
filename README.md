# Polar HRV Automation (Railway V4)

Automatiza el flujo diario de HRV de un unico atleta con Polar AccessLink, cobertura RR Dropbox -> Polar y pipeline ENDURANCE V4.

## Alcance

Este repositorio esta pensado para uso personal N=1.

- No es un producto multiusuario ni multiatleta.
- No introduce multi-cuenta, multi-tenant ni seleccion de atleta.
- Las decisiones de implementacion priorizan simplicidad operativa, trazabilidad y robustez.

## Precedencia documental

Este README es una guia de entrada. La documentacion operativa y normativa que manda de verdad es:

1. `AGENTS.MD` para estructura, runtime, rutas, endpoints, OAuth y despliegue.
2. `docs/contracts/` para logica HRV, columnas, QA, gating y semantica de metricas.
3. `analysis/AGENTS.md` y documentos locales de `analysis/` para el modulo analitico.

Si hay conflicto, manda `AGENTS.MD` y, para logica HRV, `docs/contracts/`.

## Que hace el sistema

El flujo principal:

1. Detecta fechas faltantes en `CORE`.
2. Intenta cubrir RR faltantes desde Dropbox a partir de `ECG.jsonl + ACC.jsonl`.
3. Si Dropbox no cubre esas fechas, usa Polar como fallback.
4. Actualiza `ENDURANCE_HRV_sleep.csv`.
5. Procesa RR con `build_hrv_core.py`.
6. Genera `FINAL` y `DASHBOARD` con `build_hrv_final_dashboard.py`.
7. Puede sincronizar wellness a Intervals.icu de forma opcional.

La prioridad canonica de cobertura RR es Dropbox primero y Polar como fallback.

## Arquitectura actual

### Componentes principales

- `web_ui.py`
  - UI Flask movil-first.
  - Expone `/`, `/auth`, `/auth/callback`, `/oauth/callback`, `/api/sync`, `/api/sync-sessions`, `/api/status` y `/health`.
  - Ejecuta `polar_hrv_automation.py --process` y `build_sessions.py --update` en background.
  - No permite correr `sync` HRV y `sync-sessions` a la vez.

- `polar_hrv_automation.py`
  - Orquestador principal del flujo HRV.
  - Delega la operativa real en `hrv_app.hrv_sync_flow`.

- `hrv_app/`
  - Paquete interno con la logica operativa.
  - Contiene flujo de sync, OAuth, clientes, reporting CLI, Dropbox RR, pipeline runner e integracion Intervals.

- `egc_to_rr.py`
  - Convierte pares `ECG.jsonl + ACC.jsonl` a RR CSV compatibles con el pipeline.

- `build_hrv_core.py`
  - RR -> `ENDURANCE_HRV_master_CORE.csv`
  - RR -> `ENDURANCE_HRV_master_BETA_AUDIT.csv`

- `build_hrv_final_dashboard.py`
  - `CORE + sleep + sessions_day` -> `ENDURANCE_HRV_master_FINAL.csv`
  - `CORE + sleep + sessions_day` -> `ENDURANCE_HRV_master_DASHBOARD.csv`
  - Usa contexto de carga y recuperacion como sidecar interpretativo en `reason_text`.

- `build_sessions.py`
  - Pipeline de sesiones desde Intervals.icu.
  - Genera sesiones, agregados diarios, distribucion semanal, weekly coach, metadata y wellness subjetivo.

- `analysis/`
  - Modulo local de analisis de sesiones.
  - Consume contexto reproducible del pipeline, pero no redefine la operativa global.

## Estructura del repositorio

- `data/`
  - Datos operativos y outputs locales por defecto.

- `data/rr_downloads/`
  - RR crudos, reprocesables.

- `docs/contracts/`
  - Contratos HRV activos.

- `docs/legacy/`
  - Documentacion historica. Tratar como material sensible.

- `scripts/`
  - Scripts operativos locales, especialmente para Windows.

- `analysis/`
  - Analisis de sesiones y artefactos locales del modulo.

## Outputs

### Canonicos

- `ENDURANCE_HRV_master_CORE.csv`
- `ENDURANCE_HRV_master_BETA_AUDIT.csv`
- `ENDURANCE_HRV_master_FINAL.csv`
- `ENDURANCE_HRV_master_DASHBOARD.csv`
- `ENDURANCE_HRV_sleep.csv`

### Complementarios

- `ENDURANCE_HRV_sessions.csv`
- `ENDURANCE_HRV_sessions_day.csv`
- `ENDURANCE_HRV_intensity_distribution_weekly.csv`
- `ENDURANCE_HRV_weekly_coach.json`
- `ENDURANCE_HRV_sessions_metadata.json`
- `ENDURANCE_HRV_wellness_subjective.csv`

## Flujo operativo principal

Comando recomendado:

```bash
python polar_hrv_automation.py --process
```

Este comando:

1. Calcula fechas faltantes en `CORE`.
2. Intenta importar RR desde Dropbox si el flujo esta habilitado.
3. Descarga de Polar solo lo que Dropbox no cubre.
4. Actualiza `sleep`.
5. Regenera `CORE`, `BETA_AUDIT`, `FINAL` y `DASHBOARD`.

Para recalcular historico de `FINAL` y `DASHBOARD` sin rehacer descargas ni `CORE`:

```bash
python build_hrv_final_dashboard.py
```

## Pipeline de sesiones

Comando recomendado:

```bash
python build_sessions.py --update
```

Outputs principales de sesiones:

- `ENDURANCE_HRV_sessions.csv`
  - Sesiones individuales enriquecidas.

- `ENDURANCE_HRV_sessions_day.csv`
  - Agregados diarios y contexto reproducible de carga.
  - Incluye `load_3d`, `acwr_simple_prev`, `monotony_7d_prev`, `strain_7d_prev`.
  - Incluye clustering reciente de intensidad con `intense_days_prev_3d`, `intense_days_prev_5d`, `intensity_clustering_flag`, `intensity_clustering_level`.
  - Incluye senal rolling de polarizacion por familia.

- `ENDURANCE_HRV_intensity_distribution_weekly.csv`
  - Distribucion observada semanal por deporte.

- `ENDURANCE_HRV_weekly_coach.json`
  - Resumen semanal estructurado con marcas de corte, cobertura y contexto retrospectivo visible en UI.
  - Desde `SYA-14`, puede incluir `z3_budget_by_sport` y `z3_budget_summary` como lectura de percentil historico de Z3 por deporte.

- `ENDURANCE_HRV_sessions_metadata.json`
  - Metadata del pipeline y `training_audit`.

- `ENDURANCE_HRV_wellness_subjective.csv`
  - Capa subjetiva de wellness.

## Web UI

Ejecucion local:

```bash
python web_ui.py
```

Endpoints principales:

- `GET /`
- `GET /auth`
- `GET /auth/callback`
- `GET /oauth/callback`
- `POST /api/sync`
- `POST /api/sync-sessions`
- `GET /api/status`
- `GET /health`

Reglas operativas:

- `/api/sync` y `/api/sync-sessions` comparten estado en memoria.
- No deben ejecutarse en paralelo.
- Si un job esta corriendo, el otro debe rechazarse.

Notas de UI:

- El bloque `Detalle tecnico` muestra el output operativo del ultimo job.
- `GET /api/status` expone estado del job, diagnosticos de runtime y el resumen ya procesado del weekly coach.
- Si esta habilitado por entorno, la UI puede exponer import de CSV seed.
- La UI permite borrar el ultimo RR moviendolo a backup, no borrandolo de forma destructiva.
- Cuando existe `ENDURANCE_HRV_weekly_coach.json`, la UI puede mostrar `planning_note` y `Contexto Z3 semanal` sin introducir reglas nuevas de decision.

## Significado del bloque tecnico

El resumen mostrado al final del sync y en la UI es una vista corta del ultimo registro de `FINAL`.

Ejemplo:

```text
[OK] Archivos actualizados hasta 2026-04-14
📅 Fecha:                   2026-04-14
💓 HR hoy:                  49.2 bpm
📊 RMSSD:                   47.3 ms
🚦 Gate:                    VERDE++
🧭 Acción:                  INTENSIDAD_OK / EJECUTAR_PLAN
🧾 Razón gate:              2D_OK
🧠 Reason text:             VERDE pero con 2 días intensos en los últimos 5: prudencia con la intensidad (1/3d · 2/5d) | VERDE con carga aguda 72h (acute_load_72h_rel=4.20x; load_3d=221): precaución intensidad
🧩 Decision path:           BASE60_ONLY
🧪 Contexto recuperación:  contexto completo / señales alineadas
📐 Base 60d:                44.1 ms (n=41)
📏 Healthy RMSSD:           50.2 ms
⚠️  Umbral warn.:           42.6 ms
```

Lectura rapida del ejemplo:

- El gate del dia es verde, pero el `reason_text` introduce prudencia por intensidad reciente agrupada y por carga acumulada corta.
- `Base 60d` es la referencia reciente usada por el sistema; `Umbral warn.` es solo la linea informativa contra la que se compara esa base.
- `Contexto recuperación` indica que habia suficiente informacion y que esa informacion apuntaba en la misma direccion que la lectura principal.

Campos importantes:

- `Razon gate`
  - Motivo base del gate principal.

- `Reason text`
  - Explicacion contextual legible del dia.
  - Puede incluir carga reciente, clustering de intensidad, sueno o senales de recuperacion.

- `Decision path`
  - Camino de decision usado por el builder para llegar al gate final.
  - Sigue siendo un campo tecnico, no una recomendacion de entrenamiento.

- `Contexto recuperacion`
  - Resume cuanta informacion habia y si las senales estaban alineadas o mezcladas.
  - Ejemplo: `contexto completo / senales alineadas`.

- `Base 60d`
  - Baseline60 equivalente en RMSSD ms usado como referencia reciente.

- `Healthy RMSSD`
  - Ancla sana usada para comparar degradacion de baseline60.

- `Umbral warn.`
  - Umbral informativo de degradacion de baseline60.
  - No es la baseline60; es la linea de comparacion.

- `Warning base`
  - Se activa cuando `baseline60_degraded=True`.
  - Es una advertencia contextual; no recolorea por si sola el gate.

## Variables de entorno

### Requeridas

- `POLAR_CLIENT_SECRET`
- `PORT`
- una de:
  - `POLAR_CLIENT_ID`
  - `POLAR_CLIENT_ID2`

Nota:

- Si existen ambas, el codigo da precedencia a `POLAR_CLIENT_ID2`.

### Muy recomendadas

- `PUBLIC_URL`
- `POLAR_TOKEN_PATH`
- `HRV_DATA_DIR`
- `RR_DOWNLOAD_DIR`
- `INTERVALS_API_KEY`
- `INTERVALS_ATHLETE_ID`

### Operativas

- `HRV_QUIET=1`
- `HRV_DISABLE_BACKUP=1`
- `HRV_SYNC_TIMEOUT_SEC`

### Dropbox RR

- `HRV_DROPBOX_RR_ENABLED=1`
- `HRV_DROPBOX_RR_SCRIPT=egc_to_rr.py`
- `HRV_DROPBOX_NO_AUX=1`
- `HRV_DROPBOX_PAIR_LIMIT=<N>`
- `HRV_DROPBOX_FOLDER_PATH=<dropbox_path>`
- `HRV_DROPBOX_RECURSIVE=1`
- `DROPBOX_ACCESS_TOKEN`
- o `DROPBOX_REFRESH_TOKEN + DROPBOX_APP_KEY + DROPBOX_APP_SECRET`

## Defaults locales

Si no se sobreescriben por entorno:

- `HRV_DATA_DIR=data`
- `RR_DOWNLOAD_DIR=data/rr_downloads`
- `POLAR_TOKEN_PATH=.polar_tokens.json`

Por tanto, en local:

- RR nuevos y reprocesables van a `data/rr_downloads/`
- CSV maestros, `sleep` y `sessions` viven en `data/`

## Railway y OAuth

Principios de produccion:

- En Railway debe existir un unico flujo OAuth web.
- No se debe abrir navegador desde backend.
- No se debe usar callback local tipo `HTTPServer` en produccion.

Configuracion recomendada con Volume en `/data`:

- `POLAR_TOKEN_PATH=/data/polar_tokens.json`
- `HRV_DATA_DIR=/data`
- `RR_DOWNLOAD_DIR=/data/rr_downloads`

Flujo esperado:

1. Abrir `GET /auth`
2. Redireccion a Polar
3. Callback en `/auth/callback` o `/oauth/callback`
4. Intercambio de `code` por tokens
5. Persistencia atomica en `POLAR_TOKEN_PATH`

## Ejecucion local

Windows:

```bash
scripts\run-python.bat
scripts\run-web-ui.bat
python build_sessions.py --update
```

Conversion manual Dropbox -> RR:

```bash
python egc_to_rr.py --dropbox-folder /ruta/carpeta --dropbox-recursive --outdir data/rr_downloads
```

## Seguridad

No commitear:

- `.env`
- `.polar_tokens.json`
- RR personales
- CSV personales
- contenidos de `data/`

Reglas:

- No loguear tokens ni `client_secret`.
- Rotar secretos si se exponen.
- No exponer tokens ni artefactos sensibles por HTTP.
- Tratar `docs/legacy/` como material historico sensible.

## Modulo analysis

`analysis/` es un modulo local separado para analisis de sesiones.

- Consume contexto del pipeline, incluyendo `training_audit`, carga reciente y capa mecanica minima.
- Puede generar artefactos locales como `terrain_intervals.csv` o `terrain_climbs.csv`.
- No debe reinterpretar ni sustituir la documentacion operativa global.

Para tareas dentro de `analysis/`, manda `analysis/AGENTS.md` despues de `AGENTS.MD`.
