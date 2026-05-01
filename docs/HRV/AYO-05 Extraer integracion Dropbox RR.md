## Objetivo

Aislar la estrategia Dropbox primero para cobertura RR, separando deteccion de fechas faltantes y wrapper de importacion del flujo principal.

## Alcance

- mover `_extract_date_from_rr_filename`
- mover `_scan_rr_files_by_date`
- mover `_iter_dates`
- mover `_compute_target_missing_dates`
- mover `_run_dropbox_rr_import_for_dates`

## Criterios de aceptacion

1. `main()` deja de mezclar cobertura Dropbox con descarga Polar.
2. La logica de cobertura por fecha queda trazable y reutilizable.
3. Se mantiene el comportamiento Dropbox primero con fallback Polar.

## Regression Gate

- `python -m py_compile` sobre `dropbox_rr.py` y `polar_hrv_automation.py`
- test de seleccion de RR por fecha
- test de fechas faltantes
- smoke test de importacion con subprocess mockeado
