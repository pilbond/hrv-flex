# HG-08 · Resultado del análisis del detector ECG

10 de noviembre de 2026

La recomendación es conservar el detector vigente. RPNet recuperó complejos
omitidos en grabaciones difíciles, pero también introdujo detecciones
adicionales. La mejora neta fue de una discrepancia al excluir las dos fechas
del diseño inicial.

## Comparación inicial

Se puntuaron 360 complejos en 36 extractos de 12 grabaciones del mismo atleta.
Hamilton evitó la única detección adicional del control. Kalidas–Tamil evitó
esa misma detección y añadió una detección y una omisión en otra grabación.
El refinamiento temporal conservó las detecciones y su exactitud quedó
inconcluyente. RPNet emparejó los 360 complejos, evitó la detección adicional
del control e introdujo dos nuevas.

## Ampliación a grabaciones difíciles

Se seleccionó un extracto de 12 segundos en cada una de 20 fechas con más del
10 % de RR descartados en la ventana de medida. En cada fecha se eligió el tramo
con mayor concentración de marcas de descarte del detector vigente. Una sola
lectura visual del ECG, previa a la comparación, dejó ocho extractos completos
y partes de otros como dudosos. Quedaron 96 complejos puntuables.

| Detector | Complejos emparejados | Detecciones adicionales | Omisiones |
|---|---:|---:|---:|
| Vigente | 91 | 19 | 5 |
| RPNet | 96 | 19 | 0 |

RPNet recuperó cinco complejos en cuatro fechas. Evitó 14 detecciones
adicionales del detector vigente e introdujo otras 14. Las discrepancias
bajaron de 24 a 19 en la muestra completa y de 20 a 19 al excluir las dos
fechas de diseño. El criterio para avanzar exigía cero discrepancias nuevas.

[Informe técnico, selección por fecha y comandos de reproducción](../../research/reports/hg08_detector_2026-11-10.md)
