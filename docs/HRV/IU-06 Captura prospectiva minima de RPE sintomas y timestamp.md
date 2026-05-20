## Objetivo

Abrir la via de validacion real del sistema con un conjunto minimo de etiquetas subjetivas y de contexto temporal.

---

## Diagnostico

El limite principal del bloque N=1 no es falta de correlaciones. Es falta de `ground truth`:

- no hay RPE diario consistente
- no hay registro sistematico de sintomas o enfermedad
- no siempre queda bien fijada la hora exacta de medicion

Sin eso, el sistema prueba coherencia interna, no capacidad predictiva real.

---

## Alcance propuesto

Captura minima, no maximalista:

- `RPE` diario de 0 a 10
- sintomas/illness flag simple
- timestamp exacto de la medicion HRV

Fase inicial:

- recoger y persistir
- exponer cobertura
- no meterlo aun en el gate

---

## Decisiones

- priorizar adherencia sobre riqueza de formulario
- evitar seis campos nuevos si tres bastan para arrancar validacion
- mantener esta capa como sidecar o capa separada hasta validar uso

---

## Criterios de aceptacion

1. Se puede recoger el trio minimo de forma reproducible.
2. La cobertura queda visible para analisis posterior.
3. La nueva capa no altera la logica diaria del gate en la primera fase.
