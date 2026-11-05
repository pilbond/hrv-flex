# Research

Zona de investigacion no operativa del repositorio.

`research/` contiene experimentos, auditorias y resultados que ayudan a evaluar
hipotesis o decisiones, pero no forman parte de la aplicacion, del pipeline
canonico ni del modulo funcional `analysis/`.

## Estructura

- `experiments/`: scripts para probar hipotesis concretas.
- `audits/`: revisiones reproducibles del sistema, modelos o documentacion.
- `reports/`: informes generados e historicos de analisis exploratorio.
- `.scratch/`: trabajo temporal descartable.

Cada experimento o auditoria debe mantener separados:

- `scripts/`: codigo reproducible que puede versionarse.
- `results/`: outputs generados, normalmente ignorados por Git.
- `README.md`: objetivo, muestra, metodo, limitaciones y estado de adopcion.

## Regla de adopcion

Un resultado de `research/` no modifica por si solo contratos, gates, columnas
ni comportamiento operativo. Para adoptarlo hay que implementar el cambio en
la capa correspondiente, anadir tests y actualizar `docs/contracts/` cuando
afecte a logica HRV normativa.

