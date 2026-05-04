# SYA-13 Diccionario local de analysis

> Tarjeta Kanvas: `SYA-13` — grupo `Semantica y analysis`, estado `purple` (propuesta).

## Texto de la tarjeta

Objetivo: crear un diccionario local de `analysis` que centralice el significado de artefactos, contextos JSON, taxonomias y labels exploratorios que hoy viven repartidos entre codigo, prompts, metodos y notas FP.

El objetivo no es ampliar el diccionario canonico HRV de `docs/contracts/`, sino separar con claridad semantica global y semantica local de `analysis`.

---

## Analisis tecnico 2026-04-28

### Motivo de apertura

`analysis` ya tiene vocabulario propio suficiente como para justificar un diccionario local:

- `analysis_only_context`
- `runaware_context`
- `durability_context`
- `terrain_context`
- `terrain_fit_context`
- `efficiency_context`
- `matched_climbs.csv`
- labels como `stable_contextual_efficiency`, `mixed_signal`, `mechanical_efficiency_drop`

Hoy ese significado esta repartido entre:

- `analysis/SESSION_ANALYSIS_METHOD.md`
- `analysis/AGENTS.md`
- `analysis/analyst_prompt_rules.md`
- notas `docs/HRV/FP-xx`
- y el propio codigo

Eso tiene tres problemas:

1. cuesta saber cual es la fuente primaria de definiciones
2. las notas de tarea acaban mezclando decision historica con semantica estable
3. revisiones y handoffs pueden confundir una capa local exploratoria con un contrato canonico

### Alcance propuesto

Crear un documento local, por ejemplo:

- `analysis/ANALYSIS_DICTIONARY.md`

Con secciones como minimo para:

- artefactos locales
- contextos JSON locales
- labels de clasificacion
- niveles de confianza
- senales exploratorias
- notas de "no canonico / no exportar"

### Formato recomendado por entrada

Cada entrada deberia incluir:

- nombre
- donde aparece
- que significa
- cuando aplica
- que no significa
- si es contrato canonico o solo local de `analysis`

### Ejemplos de entradas prioritarias

- `analysis_only_context`
- `runaware_context`
- `durability_context`
- `terrain_context`
- `terrain_fit_context`
- `efficiency_context`
- `matched_climbs.csv`
- `stable_contextual_efficiency`
- `cardiovascular_efficiency_drop`
- `mechanical_efficiency_drop`
- `repeatability_loss_in_climbs`
- `mixed_signal`

### Criterios de aceptacion propuestos

1. Existe un diccionario local de `analysis` en una ruta estable.
2. El documento distingue de forma explicita entre semantica canonica y semantica local.
3. Las definiciones estables de contextos y labels ya no dependen de leer notas `FP-xx`.
4. `SESSION_ANALYSIS_METHOD.md`, `AGENTS.md` o `analyst_prompt_rules.md` pueden enlazarlo como fuente semantica primaria cuando corresponda.

### Fuera de alcance

- mover esta semantica al diccionario canonico HRV
- promover senales exploratorias a contrato global
- recalibrar thresholds o redisenar taxonomias

### Conclusion

La tarea tiene sentido porque la capa `analysis` ya no es un conjunto pequeno de reglas sueltas: acumula objetos, artefactos y labels propios. Sin un diccionario local, la semantica estable queda dispersa y las notas de tarea se convierten en pseudo-contratos accidentales.
