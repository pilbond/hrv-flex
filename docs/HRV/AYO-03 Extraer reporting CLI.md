## Objetivo

Separar la presentacion textual del flujo operativo para que el entrypoint deje de mezclar orquestacion con rendering CLI.

## Alcance

- mover `_print_header`, `_print_divider`, `_print_sync_completed`
- mover `_print_no_rr_files`, `_print_master_already_updated`
- mover `_get_color_emoji`, `_get_gate_emoji`, `_format_metric`
- mover `show_last_daily_summary`, `show_last_7_days_summary`, `show_latest_hrv_summaries`
- mover `COLOR_EMOJI` y `GATE_EMOJI`

## Criterios de aceptacion

1. `polar_hrv_automation.py` deja de contener funciones de rendering CLI.
2. `cli_reporting.py` no requiere credenciales Polar para importarse.
3. Los summaries siguen mostrando la misma informacion.

## Regression Gate

- `python -m py_compile` sobre `cli_reporting.py` y `polar_hrv_automation.py`
- smoke test de import de `cli_reporting.py`
- test minimo de `show_last_daily_summary` con CSV temporal
