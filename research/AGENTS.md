# AGENTS.md - Research

## Alcance

Esta carpeta contiene trabajo exploratorio no operativo:

- experimentos,
- auditorias,
- analisis estadisticos puntuales,
- informes historicos generados por IA.

No contiene codigo requerido por la aplicacion ni por el modulo funcional
`analysis/`.

## Reglas

- No escribir outputs junto a los scripts.
- Guardar codigo reproducible en `scripts/`.
- Guardar resultados generados en `results/` o `research/reports/`.
- Usar `research/.scratch/` para pruebas descartables.
- No presentar resultados exploratorios como contratos canonicos.
- No importar codigo de `research/` desde el pipeline operativo.
- No guardar secretos, tokens ni copias completas de datos personales.
- Documentar muestra, fecha, supuestos y limitaciones antes de conservar un
  experimento.

## Protocolo anti-especulación (usar al pedir analisis)

Antes de concluir nada, seguir este protocolo:

1. Si vas a afirmar algo sobre el codigo, cita archivo:linea. Si vas a afirmar
   algo sobre los datos, ejecutalo y enseña la salida cruda primero.
2. Pasos pequeños: una pregunta, una medicion, una conclusion. No generar
   informes largos hasta que cada numero este verificado.
3. Para cada hallazgo, buscar activamente el caso que lo contradiga (¿hay
   algun dia/fila donde esto no se cumpla?).
4. Si no hay forma de comprobar algo (no existe el dato, no se puede
   ejecutar), decirlo explicitamente — no rellenar con una explicacion
   plausible.
5. Si hay un error, corregirlo de forma visible en el propio documento, no
   reescribirlo en silencio.

## Precedencia

`research/` no entra en la jerarquia normativa. En caso de conflicto mandan:

1. `../AGENTS.MD`
2. `../docs/contracts/`
3. `../analysis/AGENTS.md` para el modulo funcional de analisis

