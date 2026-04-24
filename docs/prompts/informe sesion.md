Redacta un informe analitico en espanol, con tono prudente, natural y didactico. Debe sonar como un entrenador/analista humano explicando la sesion al atleta: claro, concreto y trazable, sin perder rigor ni inventar datos.

--------------

{{SESSION_SLUG}}: 2026-03-29_08-32_road_run_i135583336

Redacta el informe final rico de la sesion `{{SESSION_SLUG}}`.
Antes de responder, revisa y respeta los contratos del repo y del modulo `analysis` si aplica.

## Contratos que debes cargar y respetar
1. `analysis/AGENTS.md`
2. `analysis/ENDURANCE_AGENT_DOMAIN.md`
3. `analysis/SESSION_ANALYSIS_METHOD.md`

## Fuentes
- Usa `artifacts/session_payload.json` como fuente compacta principal.
- Usa `artifacts/summary.json` como apoyo tecnico y de QA.
- Usa `artifacts/report_sync_status.json` para comprobar si el `report.md` humano esta alineado con la regeneracion tecnica mas reciente.
- Abre `artifacts/blocks.csv` solo si hace falta granularidad adicional.
- Si existe `technical_report.md`, usalo como apoyo tecnico, pero no lo sobrescribas.
- El resultado final humano debe guardarse en `report.md`.
- Si `session_payload.json.narrative_targets.final_reason_rendered.enabled = true`, trata esa capa como la traduccion narrativa primaria de las cautelas HRV.

## Prioridades editoriales
- Quiero un informe didactico, valioso y prudente.
- Interpreta; no enumeres.
- Distingue intensidad de dosis: una sesion puede ser `bajo_estimulo` y aun asi aportar volumen relevante.
- Si `effort_vs_recent = above` o `effort_vs_anchor = above`, integralo en la lectura del coste total.
- Si una sensacion subjetiva encaja con el contexto reciente, expresalo como compatibilidad o hipotesis plausible, no como explicacion cerrada.
- Cuando un dato no este disponible, dilo; no lo rellenes con teoria.
- Si la capa RR fina es debil pero la clasificacion global es robusta, haz visible esa diferencia en la confianza.
- En sesiones de carrera, usa splits por km solo si ayudan a leer estructura, pacing o degradacion; si aportan valor, contextualizalos con desnivel y ambos gap cuando el dato lo permita.
- Si `final_reason_items_contract.fallback_to_reason_text = false`, no paraphrases `reason_text` como fuente primaria cuando ya hay items tipificados.
- No presentes `has_action_constraint = false` ni `baseline60_degraded = True` como bullets paralelos al mismo nivel que los `final_reason_items`.

## Objetivo
Explica:
- que estimulo fue realmente la sesion,
- donde estuvo la carga,
- si la ejecucion fue adecuada dado el contexto,
- que puede aportar,
- que puede restar,
- y que implicacion practica tiene para la siguiente decision.

## Estructura esperada
- Usa `report_sync_token` al principio del `report.md` como comentario HTML de sincronizacion.
- Mantiene `Conclusión` antes de `Advertencias`.
- `RR` debe incluir `HR@0.75` solo en la capa RR cuando exista.
- No dejes cabeceras vacias si una subseccion no tiene contenido.
- Si hay `speed_first_half` y `speed_second_half`, refleja la lectura de fade en la narrativa, no solo en tablas tecnicas.

## Salida
- Guarda el resultado final en:
  `analysis/reports/{{SESSION_PATH}}/report.md`
- Preserva `technical_report.md` como artefacto tecnico separado.
- Entrega como resultado final el contenido del informe y confirma la ruta de guardado.
