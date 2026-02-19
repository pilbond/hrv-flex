# Procedimiento Recomendado (V4)

## Uso diario (automático)
Ejecuta una sola vez al día:

python polar_hrv_automation.py --process

Esto hace:
- Descarga RR faltantes desde Polar.
- Genera ENDURANCE_HRV_master_CORE.csv y ENDURANCE_HRV_master_BETA_AUDIT.csv.
- Genera ENDURANCE_HRV_master_FINAL.csv y ENDURANCE_HRV_master_DASHBOARD.csv.

Si usas la Web UI, basta con presionar "Sincronizar".

## Uso manual (si necesitas rehacer)
1) Procesar RR a CORE/BETA_AUDIT:

python endurance_hrv.py --rr-dir rr_downloads

2) Generar gate V4-lite:

python endurance_v4lite.py

## Días sin sesión
Si no hay sesión en un día, el CSV simplemente no incluye esa fecha. Es normal.

## Migración desde V3 (si tienes master_ALL)
python __endurance_migrate.py --master-all ENDURANCE_HRV_master_ALL.csv

Luego valida ENDURANCE_HRV_master_DASHBOARD.csv.
