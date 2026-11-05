# IU-20 — Trazabilidad prospectiva y evaluación a 14 días del brief IA

## Objetivo

Desplegar y evaluar la instrumentación de trazabilidad añadida al brief diario IA para poder distinguir entre:

- contexto de entrada ausente o desfasado,
- omisión o inferencia no respaldada del modelo,
- cambios en el payload, el prompt o la configuración de inferencia,
- y problemas previos en las señales deterministas.

La instrumentación no cambia el gate HRV, las señales fisiológicas ni el fallback determinista. Su finalidad es hacer auditable cada generación nueva.

## Estado al 2026-10-01

Ya está implementada la versión `2.0` del sidecar del brief diario en `hrv_app/ai/daily_brief.py`.

Cada nueva generación persiste:

- `sidecar_schema_version`,
- `input_snapshot`,
- `payload_hash`,
- `prompt_hash`,
- `inference_config` efectiva.

La configuración registrada refleja la petición realmente enviada al proveedor y excluye la clave API y las cabeceras de autorización. El `input_snapshot` es la representación exacta utilizada para calcular `payload_hash` y omite campos volátiles como `generated_at`.

También se han actualizado:

- los tests de contrato en `tests/test_ai_daily_brief_contract.py`,
- la documentación funcional de IU-15,
- y la auditoría `research/audits/system/2026-09-30/AUDITORIA_BRIEF_IA_2026-09-30.md`.

Verificación realizada antes del despliegue:

- tests específicos del brief IA: `14 passed`,
- suite relacionada de consumidores, almacenamiento y UI: `80 passed, 3 subtests passed`,
- suite completa: `729 passed, 2 skipped, 29 subtests passed`,
- compilación de `hrv_app/ai/daily_brief.py`: correcta.

## Alcance prospectivo

Los sidecars anteriores no se migran ni se reescriben. Un sidecar antiguo que conserva el mismo `payload_hash` puede seguir siendo reutilizado por la lógica de idempotencia. La versión `2.0` aparecerá a partir de la primera generación nueva o de un cambio del payload.

Por tanto, el periodo de observación empieza cuando se confirme en producción el primer sidecar válido con `sidecar_schema_version = "2.0"`, no en la fecha del commit.

## Despliegue

1. Subir al repositorio únicamente código, tests y documentación.
2. No versionar `data/`, sidecars generados, RR ni CSV personales.
3. Desplegar la revisión en Railway.
4. Ejecutar o esperar al siguiente sync diario.
5. Confirmar que el nuevo sidecar contiene los cinco campos de trazabilidad y no contiene secretos.
6. Registrar la fecha del primer sidecar v2 como inicio de observación.

## Ventana de evaluación

Evaluar después de 14 días naturales desde el primer sidecar v2, procurando disponer de al menos 10 briefs diarios v2 válidos. Si el despliegue y la primera generación se producen el 2026-10-01, la primera revisión corresponde al 2026-10-15.

Para cada fecha se recogerán, como mínimo:

| Campo | Finalidad |
|---|---|
| `date` | Identificar la observación |
| `status` y `source_mode` | Distinguir IA válida, fallback y error |
| número y tipos de `reason_items` | Saber qué evidencia determinista estaba disponible |
| fecha efectiva del contexto de carga | Detectar carga heredada o desfasada |
| `lag_days` de carga | Cuantificar el desfase temporal |
| `payload_hash` | Detectar cambios de entrada |
| `prompt_hash` | Detectar cambios del prompt |
| `inference_config` | Detectar cambios del modelo o muestreo |
| resultado de la validación | Separar fallo contractual de problema semántico |

## Preguntas de evaluación

1. ¿Los casos sin `reason_items` coinciden con ausencia real de señales deterministas?
2. ¿Aparece contexto de carga en la entrada IA cuando la fecha de carga está desfasada respecto al día del brief?
3. ¿El modelo formula relaciones causales que no están respaldadas por los `reason_items`?
4. ¿Cuántos briefs usan fallback y por qué motivo?
5. ¿Los cambios observados se explican por el payload, el prompt, la configuración o el propio modelo?
6. ¿La trazabilidad disponible permite reproducir y clasificar cada anomalía sin consultar datos ambiguos?

## Criterios de aceptación

- Existe al menos un sidecar v2 generado en producción.
- Ningún sidecar contiene credenciales, tokens o cabeceras de autorización.
- Se dispone de al menos 10 briefs v2 a lo largo de una ventana mínima de 14 días, o se documentan explícitamente los días ausentes.
- Cada incidencia se clasifica como entrada, desfase temporal, validación, inferencia del modelo o señal determinista.
- La evaluación termina con una decisión explícita sobre el siguiente cambio:
  - implementar ecos estructurados y mostrar la causa del gate (`S3 + S8`),
  - corregir primero la preparación del contexto,
  - o mantener el comportamiento actual si no aparece evidencia suficiente.

## Límites

Esta evaluación comprueba trazabilidad y coherencia interna; no demuestra verdad fisiológica ni causalidad clínica. Tampoco cubre todavía el brief SSM, cuya instrumentación debe evaluarse por separado si se decide extender el mismo esquema.

