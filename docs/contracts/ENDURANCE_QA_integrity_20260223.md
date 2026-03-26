# ENDURANCE HRV — QA de integridad (post-implementación)
Fecha generación: 2026-02-23

## Resumen
- Rango HRV (CORE/FINAL/DASH/BETA): 2025-05-12 → 2026-02-23  (N=274)
- CONTEXT: N=288 (incluye 14 fechas sin medición HRV)

## Calidad de señal (CORE)
- Calidad: {'OK': 244, 'FLAG_mecánico': 26, 'INVALID': 4}
- HRV_Stability: {'OK': 244, 'Unstable': 30}

## Salida operativa (FINAL)
- gate_final: {'VERDE': 125, 'ROJO': 78, 'NO': 38, 'ÁMBAR': 33}
- Action: {'SUAVE_O_DESCANSO': 133, 'INTENSIDAD_OK': 112, 'Z2_O_TEMPO_SUAVE': 29}
- Action_detail: {'EJECUTAR_PLAN': 112, 'DESCARGA': 93, 'SIN_HIIT': 29, 'SUAVE_QUALITY': 22, 'SUAVE': 18}
- quality_flag=True: 26 días
- veto_agudo=True: 54 días
- Top gate_razon_base60: {'2D_OK': 125, '2D_AMBOS': 78, 'BASE60_INSUF': 31, '2D_HR': 18, '2D_LN': 15, 'CAL/STAB/ART/NaN': 4, 'ROLL3_INSUF': 3}

## Contexto (CONTEXT)
- Cobertura sueño (polar_sleep_duration_min no-NaN): 95.8%
- Cobertura nightly RMSSD (polar_night_rmssd no-NaN): 17.7%
- Cobertura Intervals (intervals_load no-NaN): 83.0%

## Warning baseline60_degraded (señal de largo plazo)
- warning_mode: {'healthy85': 274}
- warning_threshold (ms): 43.03600047584024
- Últimos 60 días: baseline60_degraded=True en 57/58 (98.3%)
- Mediana exp(ln_base60) últimos 60 días ≈ 32.2 ms (vs threshold 43.0 ms)

## Invariantes (reglas que deben cumplirse)
- OK · veto: lnRMSSD_used==lnRMSSD_today
- OK · veto: HR_used==HR_today
- OK · quality_flag + (VERDE|ÁMBAR) => Action_detail=SUAVE_QUALITY
- OK · INVALID => gate_final=NO
- OK · INVALID => Action=SUAVE_O_DESCANSO
- OK · DASHBOARD es subset exacto de FINAL (10 cols)

## Observaciones
- El contrato de columnas y orden está respetado en los 5 CSV (Estructura v2026-02-23).
- La alineación CORE↔FINAL↔DASHBOARD es perfecta por Fecha (sin desajustes).
- Si el warning baseline60_degraded se mantiene casi siempre activo, puede perder valor operacional; esto no rompe nada (no recolorea), pero conviene decidir si se quiere mantener como warning permanente o recalibrar el periodo healthy/mode.