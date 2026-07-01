
## Contexto

Con IU-17 completado, la UI tiene una base estructural sana: viewmodel versionado (`hrv_app/ui_view.py`), fuente única de strings, tres rutas de render convergentes. El rediseño visual puede hacerse ahora sin riesgo de divergencia entre SSR y JS.

**Alcance acordado tras iteración de mockups (2026-06-30):** reescribir la card "Lectura HRV de hoy" para que el usuario vea de un vistazo la fiabilidad de la medición, la decisión del día y el contexto enriquecido, manteniendo la disposición de acciones actual.

**Política operativa:**
- Evitar sobre-ingeniería. Si una mejora requiere más de lo razonable para el valor que aporta, parar y preguntar.
- Antes y después de cada cambio, verificar que la UI no regresiona (tests de contrato + smoke visual).
- No cambios en pipeline, CSVs ni endpoints (solo se añade exposición de campos ya presentes en FINAL).

---

## Estado actual (snapshot post-IU-17)

### Stack
- Flask SSR (Jinja) + `ui.js` vanilla (IIFE, ~460 líneas) + `ui.css` (~470 líneas)
- Tres cards apiladas: `dashboard_actions.html`, `hrv_summary_card.html`, `technical_output_card.html`
- Viewmodel `view.hrv_today.*` y `view.system.*` disponibles en SSR y en `/api/status`
- Paleta definida con CSS custom properties (`--brand`, `--accent`, `--ok-bg`, etc.)

### Datos en FINAL no expuestos hoy en la UI

Existen en `ENDURANCE_HRV_master_FINAL.csv` pero no llegan a la UI:
- `Calidad` — fiabilidad de la toma (OK / WARN / INVALID)
- `HRV_Stability` — estabilidad de la señal
- `Action_detail` — acción derivada del gate (SUAVE_O_DESCANSO, INTENSIDAD_OK, ...)
- Texto "qué pasó" / "qué hacer" derivados de `gate_razon_base60` (hoy solo en CLI vía `hrv_app/cli_reporting.py`)

---

## Problemas detectados

### V1 — La decisión del día no es legible de un vistazo
El gate aparece como texto plano `"VERDE · BASE60_OK"` en una celda igual a las demás. La acción (`Action_detail`) no se muestra. El usuario tiene que leer y descodificar para saber qué hacer hoy.

### V2 — Jerarquía plana en el grid HRV
Los cuatro ítems del grid (`raw`, `used`, `base`, `gate`) tienen el mismo peso visual. El dato primario —RMSSD estable en `raw_text`— debería dominar; los derivados (`used`, `base`) son contexto secundario.

### V3 — No hay indicador visual de fiabilidad de la medición
`Calidad` y `HRV_Stability` no aparecen en la UI. El usuario no sabe si la toma de hoy es fiable salvo que mire el log técnico o el CSV.

### V4 — Datos disponibles pero invisibles
`Action_detail` y la traducción humana del código de razón del gate (mapping `2D_AMBOS` → "La señal suavizada bajó y la frecuencia cardiaca suavizada subió...") existen pero solo se ven en la CLI.

### V5 — Base60 oscurece su propio significado
El SWC se muestra junto a Base60 (`SWC_ln ±0.07`) cuando en realidad el SWC se materializa en el sufijo del gate (`VERDE++`, `ROJO---`). Base60 debería mostrarse como la referencia limpia que es, y el SWC ya viene incorporado en el badge del gate.

### V6 — Log técnico siempre visible y dominante
La sección `rawOutput` (min-height: 320px) ocupa un tercio de la pantalla en móvil aunque el usuario no la necesite tras un sync exitoso. No hay forma de colapsar o minimizar.

---

## Diseño cerrado

Mockup de referencia: ver iteraciones en hilo de conversación (v4 cierra el diseño).

### Layout de la card "Lectura HRV de hoy"

```
Lectura HRV de hoy (YYYY-MM-DD)
                                    Calidad OK · Estabilidad OK   ← tira discreta arriba-derecha

┌──────────────────────────────────────────────────────┐
│ RMSSD ESTABLE · HR · LNRMSSD BRUTO                   │  ← primario, full width
│ 45.2 ms · HR 58 · ln 3.812                           │
└──────────────────────────────────────────────────────┘

┌────────────────────┐  ┌────────────────────┐
│ LNRMSSD USADO      │  │ BASE60             │           ← secundarios
│ 44.0 ms · ln 3.78  │  │ 42.1 ms · ln 3.74  │
└────────────────────┘  └────────────────────┘

┌──────────────────────────────────────────────────────┐
│ 🚦 Gate     🔴 ROJO---                                │  ← decisión estructurada
│ 🧭 Acción   SUAVE_O_DESCANSO / DESCARGA               │
│ 🧾 Qué pasó La señal suavizada bajó y la FC subió... │
│ 🧾 Qué hacer Trata hoy como un día más delicado: ... │
└──────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────┐
│ REASON TEXT                                          │  ← contexto enriquecido
│ ROJO, pero el HRV de sueño salió alto (55ms): ...    │
└──────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────┐
│ BRIEF IA                                             │  ← narrativa IA
│ Día delicado pese al sueño favorable: ...            │
└──────────────────────────────────────────────────────┘
```

### Reglas visuales

- **Calidad y Estabilidad:** tira de texto pequeño arriba-derecha de la card. Sin recuadros propios, sin íconos llamativos. Solo el valor (OK / WARN / INVALID) en color sutil. Su única función es señalar si la medición es fiable.
- **RMSSD estable (raw):** dato primario. Ocupa ancho completo, fuente grande (~21px, weight 500).
- **lnRMSSD usado y Base60:** dos columnas iguales debajo. Tamaño normal (~13px). Ambos muestran `ms · ln`. **Sin SWC.**
- **Bloque de decisión:** caja con 4 filas etiquetadas (`Gate`, `Acción`, `Qué pasó`, `Qué hacer`). El gate incluye el badge con su sufijo SWC (`++/+/−/−−−`) tal cual viene del pipeline.
- **Reason text:** caja con label "Reason text". Se mantiene como hoy (es el contexto enriquecido que integra sueño, recuperación, divergencia raw vs suavizado).
- **Brief IA:** caja con label "Brief IA". Se mantiene como hoy.
- **Sin semáforo de color**, sin color de borde de card según gate, sin gradientes según estado.

### Disposición de las cards (sin cambios)

- `dashboard_actions.html` arriba (sync HRV, sync sesiones).
- `hrv_summary_card.html` en medio (la card rediseñada).
- `technical_output_card.html` abajo (log técnico + Restore + Borrar último RR). **Los botones Restore y Borrar se quedan donde están actualmente.**

### Log técnico colapsable

- Por defecto colapsado cuando el último sync fue `success === true`.
- Botón toggle "Expandir / Contraer".
- Si hay error en el último sync, se muestra expandido.

---

## Cambios técnicos requeridos

### T1 — Módulo neutro para textos del gate (opción B)

Mover las funciones `_format_gate_reason()` y `_format_gate_next_step()` desde `hrv_app/cli_reporting.py` a un módulo nuevo `hrv_app/gate_text.py`:

- `format_gate_reason(razon_code, row)` → texto "Qué pasó"
- `format_gate_next_step(razon_code)` → texto "Qué hacer"

Promueve a API pública (sin guion bajo). `cli_reporting.py` las importa para no duplicar.

### T2 — Exponer nuevos campos en `/api/status`

En `_build_status_payload()` (`web_ui.py`), añadir desde `last_final_row`:

- `final_last_calidad` ← `Calidad`
- `final_last_hrv_stability` ← `HRV_Stability`
- `final_last_base60_ms` ← `exp(ln_base60)` ya en ms
- `final_last_gate_what_happened` ← `format_gate_reason(gate_razon_base60, row)`
- `final_last_gate_what_to_do` ← `format_gate_next_step(gate_razon_base60)`

`final_last_action_detail` ya existe (línea 952). No tocar `diagnostics` shape original.

### T3 — Extender `build_view()` en `hrv_app/ui_view.py`

Nueva sección dentro de `view.hrv_today`:

```python
"quality": "OK" | "WARN" | "INVALID" | None,
"stability": "OK" | ... | None,
"raw_text": "...",          # ya existe
"used_text": "44.0 ms · ln 3.78",   # cambiar formato a ms · ln (hoy: "ms · lnRMSSD usado X.XXX")
"base_text": "42.1 ms · ln 3.74",   # cambiar formato a ms · ln (hoy incluye SWC_ln)
"gate": {
    "badge": "ROJO---",     # incluye sufijo SWC tal cual viene del pipeline
    "action": "SUAVE_O_DESCANSO / DESCARGA",
    "what_happened": "...",
    "what_to_do": "...",
},
"reason_text": "...",       # ya existe
"ai_text": "...",           # ya existe
"fallback_text": "...",     # ya existe
```

Bumpear `VIEW_VERSION` a 2 (cambio retrocompatible con consumidores nuevos, pero el shape cambia).

### T4 — Reescribir el partial y el JS

- `templates/partials/hrv_summary_card.html`: nuevo layout siguiendo el mockup.
- `static/ui.js` `renderHrvSummaryPanel()`: leer los campos nuevos del viewmodel. Sigue sin construir strings.
- `static/ui.css`: estilos para tira calidad/estabilidad, bloque de decisión.

### T5 — Log técnico colapsable

- `templates/partials/technical_output_card.html`: añadir botón toggle.
- `static/ui.css`: clases `.collapsed` con `max-height: 0` transition.
- `static/ui.js`: toggle handler + colapsar por defecto si `lastSync.success === true`.

---

## Validación

### Antes de empezar
1. `pytest tests/test_ui_view.py tests/test_web_ui_status.py tests/test_cli_reporting_contract.py -v` → verde
2. Smoke visual de `/` con FINAL disponible.

### Tests nuevos
- `tests/test_gate_text.py` — contrato del mapping `gate_razon_base60` → ("qué pasó", "qué hacer") para los códigos canónicos (`2D_OK`, `2D_LN`, `2D_HR`, `2D_AMBOS`, `CAL/STAB/ART/NaN`, `*_INSUF`, ...).
- `tests/test_ui_view.py` — nuevos campos en `view.hrv_today`: `quality`, `stability`, `gate.badge`, `gate.action`, `gate.what_happened`, `gate.what_to_do`. Verificar `VIEW_VERSION == 2`.
- `tests/test_web_ui_status.py` — payload incluye los nuevos campos `final_last_*`.

### Después
- Smoke con un FINAL de cada estado (VERDE, AMBAR, ROJO) para verificar el render.
- Smoke del log colapsable en estado success y en estado error.

---

## Riesgos y límites de alcance

| Riesgo | Mitigación |
|---|---|
| Bump de `VIEW_VERSION` rompe consumidores | El único consumidor es la propia UI; tests cubren el shape nuevo. Documentar el cambio en el header del módulo. |
| `format_gate_reason` y `format_gate_next_step` dejan de ser privadas en `cli_reporting.py` | Promover a API pública en `gate_text.py`; `cli_reporting.py` las importa con el nombre nuevo. |
| Tiras Calidad/Estabilidad con valores no esperados (p. ej. `WARN`) | El mockup asume OK; cualquier valor distinto se muestra tal cual (sin color rojo agresivo, solo texto). |
| Eliminación de SWC en Base60 puede desorientar a quien lo usaba | El SWC sigue visible en el sufijo del gate (`ROJO---`), que es donde tiene sentido funcional. |

---

## Criterios de aceptación

1. Card HRV muestra Calidad y Estabilidad como tira discreta arriba.
2. Grid HRV: RMSSD primario a ancho completo; `lnRMSSD usado` y `Base60` como secundarios en formato `ms · ln`.
3. Sin SWC en Base60. El sufijo SWC (`++/+/−/−−−`) viaja con `gate_badge`.
4. Bloque de decisión con 4 filas: `Gate`, `Acción`, `Qué pasó`, `Qué hacer`.
5. Reason text y Brief IA mantenidos como cajas etiquetadas.
6. Restore y Borrar último RR siguen en `technical_output_card.html`.
7. Log técnico colapsable: colapsado por defecto si último sync OK.
8. `hrv_app/gate_text.py` existe; CLI lo consume; viewmodel lo consume.
9. `VIEW_VERSION == 2`; tests de scope UI en verde (incluye nuevos).
10. SSR y JS visualmente idénticos entre sí.

---

## Fuera de alcance (explícito)

- Cambios en pipeline, CSVs o endpoints.
- Coach semanal (`weekly_coach_*`) — descartado en iteración de mockups.
- Semáforo de color del gate (pill, borde de card según estado) — descartado.
- Sparklines, gráficos de tendencia, deltas vs baseline.
- Reorganización de cards (mover botones entre cards).
- PWA, notificaciones, modo oscuro, multi-idioma.
- Cambios en la paleta de colores base.

---

## Trazabilidad respecto a la propuesta original

| Propuesta original | Resolución |
|---|---|
| M1 — Pill de color para el gate | ❌ Descartado: no aporta sobre el badge textual con sufijo SWC |
| M2 — Jerarquía en grid HRV | ✅ Mantenido (RMSSD primario, derivados secundarios) |
| M3 — Color de card según gate | ❌ Descartado |
| S1 — Coach semanal en UI | ❌ Descartado: no aporta en este momento |
| S2 — Mover restore/borrar | ❌ Descartado: se quedan en `technical_output_card.html` |
| N1 — Log técnico colapsable | ✅ Mantenido |
| (nuevo) Calidad + Estabilidad | ✅ Añadido |
| (nuevo) Bloque Gate/Acción/Qué pasó/Qué hacer | ✅ Añadido |
| (nuevo) Base60 en ms; SWC fuera de Base60 | ✅ Añadido |
