## Objetivo

Mantener `HR@0.75` como descriptor util cuando realmente ayuda, pero sin convertirlo en ancla narrativa excesiva.

---

## Diagnostico

Hoy su presencia en tablas y narrativa es mayor que su fiabilidad practica en muchas sesiones:

- no siempre es usable
- depende de calidad DFA/modelo
- puede arrastrar una precision aparente mayor de la real

La mejora no es borrar la metrica, sino recolocarla.

---

## Alcance propuesto

- reducir prominencia en report y warnings
- usarla como apoyo secundario cuando la confianza sea suficiente
- evitar frases que sugieran umbral fino si la calidad no lo sostiene

---

## Limites

- no retirar el calculo si sigue aportando en algunos casos
- no mezclar esta tarea con una revision completa de DFA

---

## Criterios de aceptacion

1. `HR@0.75` sigue disponible cuando es usable.
2. Su peso narrativo baja en sesiones donde la confianza no acompana.
3. El informe deja de sobrerrepresentar una senal irregular.
