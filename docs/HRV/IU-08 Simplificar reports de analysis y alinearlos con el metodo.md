## Objetivo

Reducir expansion narrativa y devolver el informe de sesiones a una estructura mas disciplinada y util.

---

## Diagnostico

El problema principal no es falta de datos. Es exceso de capas discursivas:

- demasiadas secciones accesorias
- mezcla de metodo, coaching y ornamentacion
- coste de lectura alto para ganancia desigual

Eso erosiona la consistencia del modulo `analysis`.

---

## Alcance propuesto

- revisar secciones obligatorias del prompt
- eliminar o degradar bloques con baja utilidad repetida
- alinear estructura final con `SESSION_ANALYSIS_METHOD.md`
- dejar mas clara la separacion entre dato, interpretacion y recomendacion

---

## Decisiones

- preservar hallazgos fuertes ya incorporados
- no tirar por la borda la capa `analysis_only_context` si aporta
- priorizar legibilidad y disciplina frente a exhaustividad ornamental

---

## Criterios de aceptacion

1. El report final es mas corto o mas enfocado sin perder senales fuertes.
2. La estructura queda mas alineada con el metodo local.
3. Disminuyen las secciones que repiten o adornan sin cambiar decision.
