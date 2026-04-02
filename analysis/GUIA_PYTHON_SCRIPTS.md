# Guia de scripts Python — modulo analysis

Este documento explica que hace cada `.py` del modulo `analysis/`, en que paso del flujo participa y como encajan entre si.

---

## 1) Mapa del flujo de analisis

El flujo completo para generar un report de sesion tiene dos pasos bien diferenciados:

```
Paso 1 — Preparar bundle
  sessions.csv + Polar API + Intervals API
      → .cache/session_bundles/[slug]/
          session.fit
          session_stream.csv
          session_rr.csv
          session_row.json
          bundle_manifest.json

Paso 2 — Analizar y generar report
  bundle_manifest.json
      → endurance_rr_session_v4.py   (subprocess)
          → summary.json, blocks.csv
      → session_cost_model.py        (importado por el anterior)
          → cardio_score, mecanico_score
      → session_payload.json         (payload conversacional)
      → reports/YYYY/MM/[slug]/
          technical_report.md
          analyst_prompt.md
          ai_handoff.md
          artifacts/
          debug/
```

El bundle en `.cache/` es temporal: se elimina automaticamente tras el analisis salvo `--keep-bundle`.

---

## 2) Script por script

---

### `analyze_session.py`

**Que hace:**
- CLI principal del modulo. Ejecuta el flujo completo en un solo comando: prepara el bundle y genera el report.
- Internamente llama a `prepare_bundle()` + `run_analysis()` de `session_analysis_pipeline.py`.
- Limpia el bundle de cache al terminar, salvo `--keep-bundle`.

**Cuando usarlo:**
- Caso habitual: cuando quieres generar el report de una sesion concreta (o la mas reciente) sin preocuparte por los pasos intermedios.

**Entradas:**
- `--session-id <id>` — ID de sesion desde `sessions.csv` (omitir = ultima sesion con fecha).
- `--sessions-csv` — ruta al CSV de sesiones (default: `data/ENDURANCE_HRV_sessions.csv`).
- `--reports-dir` — directorio de reports (default: `analysis/reports/`).
- `--keep-bundle` — no elimina los archivos crudos del bundle tras el analisis.
- `--keep-debug-artifacts` — conserva CSVs de depuracion (rr_beats, dfa_alpha1) en `debug/`.

**Salidas:**
- `reports/YYYY/MM/[slug]/` con el report completo.
- JSON en stdout con todas las rutas generadas.
- Bundle en cache eliminado por defecto.

**Ejemplo:**
```bash
# Ultima sesion (desde analysis/)
python analyze_session.py  -> python analysis/analyze_session.py --keep-bundle

# Sesion concreta
python analyze_session.py --session-id i133874358

# Conservar bundle y artifacts de debug
python analyze_session.py --session-id i133874358 --keep-bundle --keep-debug-artifacts
```

---

### `prepare_session_bundle.py`

**Que hace:**
- CLI para ejecutar solo el paso 1: descarga y prepara los archivos de una sesion en `.cache/session_bundles/[slug]/`.
- Descarga desde Intervals el FIT y el stream CSV (FC, velocidad, cadencia).
- Descarga desde Polar el CSV de RR para la sesion correspondiente.
- Genera `bundle_manifest.json` con todas las rutas y metadatos del bundle.

**Cuando usarlo:**
- Cuando quieres inspeccionar o validar los archivos de una sesion antes de analizarla.
- Cuando el analisis fallo y quieres reutilizar el bundle ya descargado con `run_session_analysis.py`.
- Debugging de la descarga o del matching Polar.

**Entradas:**
- `--session-id` — ID de sesion (omitir = ultima).
- `--sessions-csv` — CSV de sesiones.
- `--bundle-root` — directorio de cache (default: `analysis/.cache/session_bundles/`).

**Salidas:**
- `.cache/session_bundles/[slug]/bundle_manifest.json` y archivos de la sesion.
- JSON en stdout con el manifest completo.

**Ejemplo:**
```bash
python prepare_session_bundle.py --session-id i133874358
```

---

### `run_session_analysis.py`

**Que hace:**
- CLI para ejecutar solo el paso 2: toma un `bundle_manifest.json` ya preparado y genera el report completo.
- Util cuando el bundle existe en cache (ya descargado con `prepare_session_bundle.py` o con `--keep-bundle`).

**Cuando usarlo:**
- Reutilizar un bundle existente sin volver a descargar desde Polar/Intervals.
- Re-generar un report tras modificar logica de analisis, sin consumir API.

**Entradas:**
- `--bundle-manifest <ruta>` — ruta al `bundle_manifest.json` (requerido).
- `--reports-dir` — directorio de reports (default: `analysis/reports/`).
- `--keep-debug-artifacts` — conserva artifacts de depuracion.

**Salidas:**
- `reports/YYYY/MM/[slug]/` con el report completo.
- JSON en stdout con todas las rutas generadas.

**Ejemplo:**
```bash
python run_session_analysis.py \
  --bundle-manifest .cache/session_bundles/2026-03-22_08-59_trail_run_i133874358/bundle_manifest.json
```

---

### `session_analysis_pipeline.py`

**Que hace:**
- Modulo central con toda la logica de preparacion y analisis. No se ejecuta directamente.
- Implementa las funciones que usan los tres CLIs anteriores:
  - `prepare_bundle()` — descarga FIT, stream CSV y RR; construye manifest.
  - `run_analysis()` — ejecuta `endurance_rr_session_v4.py` como subprocess; genera todos los artefactos del report.
  - `build_conversational_payload()` — ensambla el JSON compacto para el analista IA.
  - `build_analyst_prompt_markdown()` — genera `analyst_prompt.md` desde `analyst_prompt_rules.md` + rutas de sesion.
  - `build_ai_handoff_markdown()` — genera `ai_handoff.md` con instrucciones de uso para la IA.
  - `render_report_markdown()` — genera `technical_report.md` con metricas clave en markdown.
  - `cleanup_bundle()` — elimina el bundle de cache tras el analisis.

**Dependencias externas en runtime:**
- `build_sessions.py` (IntervalsClient para descargar FIT y stream).
- `polar_hrv_automation.py` (tokens Polar, descarga RR).
- `analyst_prompt_rules.md` (plantilla de reglas para el prompt generado).

**Cuando modificarlo:**
- Para cambiar la estructura del report o del payload.
- Para ajustar la logica de construccion del `analyst_prompt.md`.
- Para añadir nuevos campos al payload conversacional.

---

### `endurance_rr_session_v4.py`

**Que hace:**
- Analizador RR de sesion. Es el motor de calculo; se ejecuta como subprocess desde `session_analysis_pipeline.run_analysis()`.
- Limpieza de RR crudos (filtro out-of-range, delta-RR, artefactos locales).
- Calcula dos capas RR: `core` (limpieza estandar) y `strict` (para DFA).
- Metricas:
  - RMSSD por ventanas de 1 min y 5 min (P10, P50, P90, usabilidad por ventana).
  - DFA-alpha1 (mediana, IQR, pct_lt_075, gate de interpretabilidad).
  - HR@0.75 (umbral aerobico estimado por regresion FC-alpha1).
  - `duration_consistency` (coherencia entre RR crudo y referencia FIT/stream).
  - Bandas de RMSSD por minuto.
  - Zonas HR por alpha1.
- Llama a `session_cost_model.py` para incorporar `cardio_score` y `mecanico_score`.
- Genera (con prefijo `--out-prefix`):
  - `*_summary.json` — todas las metricas calculadas.
  - `*_blocks.csv` — bloques de trabajo detectados (opcional, si aplica).
  - `*_rr_beats.csv`, `*_dfa_alpha1.csv`, `*_rmssd_1min.csv`, `*_rmssd_5min.csv` — solo si `--keep-debug-artifacts`.

**Entradas CLI:**
- `--rr` — CSV de RR crudo (requerido).
- `--hr-stream-csv` — stream de FC desde Intervals.
- `--fit` — archivo FIT de la sesion (opcional, preferente si existe).
- `--sport` — familia de deporte (`trail`, `road`, `bike`, `hike`, `elliptical`, `swim`).
- `--sessions-csv` + `--session-id` — para incorporar el cost model.
- `--vt1`, `--vt2` — umbrales ventilatcrios (opcional; mejoran precision de zonas).
- `--out-prefix` — prefijo de ruta para los archivos de salida.

**Cuando modificarlo:**
- Para cambiar umbrales de limpieza RR o ventanas de calculo.
- Para anadir nuevas metricas al `summary.json`.
- Requiere actualizacion del contrato `ENDURANCE_HRV_Spec_Tecnica.md` si cambia el schema de salida.

---

### `session_cost_model.py`

**Que hace:**
- Calcula los scores de coste de sesion desde las columnas de `sessions.csv`.
- `cardio_score` (0-3): basado en tiempo en Z2/Z3, bloques de trabajo, HR P95 vs VT2.
- `mecanico_score` (0-3): basado en D+/h, D-/h, densidad de desnivel, locomotion blocks (trail/hike); o cadencia y bloques (bike, elliptical); o distancia y SWOLF (swim).
- Determina `coste_dominante` y `confidence` para cada dimension.
- Devuelve `cardio_evidence[]` y `mecanico_evidence[]` con los valores observacionales que sostienen cada score.
- Es importado por `endurance_rr_session_v4.py`; tambien se puede usar como CLI independiente.

**Cuando usarlo como CLI:**
- Para verificar los scores de una sesion concreta sin lanzar el analisis completo.

**Entradas CLI:**
- `--sessions-csv` — CSV de sesiones.
- `--session-id` — ID de sesion (requerido en modo CLI).

**Ejemplo:**
```bash
python session_cost_model.py --session-id i133874358
```

---

## 3) Archivos de configuracion del modulo

| Archivo | Rol |
|---|---|
| `analyst_prompt_rules.md` | Plantilla de reglas para el `analyst_prompt.md` generado. Version controlada con `rules_version`. Unica fuente de verdad para las reglas del analista IA. |
| `SESSION_ANALYSIS_METHOD.md` | Metodo operativo del analisis de sesion. Se embebe en el payload y se pasa a la IA como contexto de metodo. |
| `ENDURANCE_AGENT_DOMAIN.md` | Rol, tono y baseline fisiologico del analista. Se embebe en el payload. |
| `AGENTS.md` | Reglas locales del modulo (precedencia, alcance, restricciones). |

---

## 4) Outputs del report por sesion

Cada report se genera en `reports/YYYY/MM/[slug]/`:

| Archivo | Quien lo genera | Para que |
|---|---|---|
| `technical_report.md` | `render_report_markdown()` | Resumen tecnico de metricas clave en markdown. Lectura rapida sin IA. |
| `analyst_prompt.md` | `build_analyst_prompt_markdown()` | Prompt listo para pegar en Claude/GPT. Incluye rutas de sesion, sport family, reglas y seccion de output. |
| `ai_handoff.md` | `build_ai_handoff_markdown()` | Instrucciones de uso para la IA: que archivos pasar y en que orden. |
| `artifacts/session_payload.json` | `build_conversational_payload()` | JSON compacto con todo el contexto de la sesion para el analista IA. Fuente principal del informe. |
| `artifacts/summary.json` | `endurance_rr_session_v4.py` | Todas las metricas calculadas en detalle. Apoyo tecnico al payload. |
| `artifacts/session.fit` | `run_analysis()` (copia) | FIT de la sesion copiado desde el bundle para que el report sea autocontenido. |
| `artifacts/manifest.json` | `run_analysis()` | Manifest del bundle: rutas de origen, info de descarga, errores. |
| `artifacts/blocks.csv` | `endurance_rr_session_v4.py` | Bloques de trabajo detectados (existe solo si la sesion tiene bloques). |
| `debug/analysis_stderr.txt` | `run_analysis()` | Stderr del analizador. Solo se conserva si contiene contenido. |

---

## 5) Casos especiales

### Sesión sin RR exportable

Si Polar no devuelve RR para una sesión (fallo de grabación, dispositivo sin sensor, export no disponible), `analyze_session.py` **no crashea**:

```
RuntimeError: el ejercicio Polar no contiene RR exportable
↓
prepare_bundle() registra en manifest["rr_error"]
↓
run_analysis() genera summary.json parcial con rr_unavailable=true
↓
technical_report.md omite secciones RR automáticamente
↓
session_payload.json incluye indicador rr_unavailable para el analista IA
```

**Salida:** Report válido con cost model (cardio/mecánico) + contexto, sin métricas RR.

**No es un error operativo**, es una degradación esperada. Útil para análisis de carga/coste aunque sin RMSSD/DFA/HR@0.75.

---

## 6) Resumen practico

**Flujo habitual (un comando):**
```bash
cd analysis/
python analyze_session.py --session-id i133874358
```

**Si quieres inspeccionar el bundle antes de analizar:**
```bash
python prepare_session_bundle.py --session-id i133874358
# revisa .cache/session_bundles/[slug]/
python run_session_analysis.py --bundle-manifest .cache/session_bundles/[slug]/bundle_manifest.json
```

**Si solo quieres verificar los scores de coste:**
```bash
python session_cost_model.py --session-id i133874358
```

**Que scripts importan para operar:**
1. `analyze_session.py` — unico punto de entrada para uso normal.
2. `endurance_rr_session_v4.py` — motor de calculo (no se llama directamente).
3. `session_cost_model.py` — scores de coste (no se llama directamente en el flujo normal).

Los CLIs `prepare_session_bundle.py` y `run_session_analysis.py` son para flujos partidos (debug, reintentos, reutilizacion de bundle).
