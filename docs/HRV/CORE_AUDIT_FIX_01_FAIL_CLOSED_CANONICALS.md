# Core Audit Fix 01 — Fail-closed de canónicos

## Objetivo

Evitar que un `CORE`, `BETA_AUDIT` o `ENDURANCE_HRV_sleep.csv` existente pero
ilegible, vacío o incompleto se trate como un archivo nuevo y se sobrescriba
con datos parciales.

## Alcance

- `build_hrv_core.py` (`get_or_create_df`).
- `hrv_app/sleep_store.py` (`upsert_sleep_row`).
- Preservación de bytes originales ante errores de lectura o escritura.

## Implementación esperada

1. Distinguir `archivo inexistente` de `archivo existente ilegible`.
2. Fallar antes de procesar o publicar cuando el canónico existente no se puede leer.
3. Usar `write_csv_atomic` para sleep.
4. Mantener backup/cuarentena explícita, sin presentarla como reparación automática.
5. Exigir el esquema completo vigente cuando el canónico ya existe.

## Política de compatibilidad

Para mantener la operativa N=1 sencilla, CAF-01 no introduce versiones de
esquema ni migradores automáticos:

- archivo ausente: se permite inicializarlo;
- archivo existente: debe ser legible, tener al menos una fila y coincidir con
  el esquema canónico exacto vigente, sin columnas ausentes ni adicionales;
- archivo de esquema antiguo o incompleto: se bloquea y requiere reparación o
  restauración manual.

Las cabeceras del dataset local y de los backups operativos disponibles se
comprobaron el 2026-07-14 y coinciden con los esquemas vigentes de 18 columnas
para CORE, 13 para BETA_AUDIT y 17 para sleep. Antes del despliegue debe
comprobarse también el volumen persistente de Railway.

## Aceptación

- Un CSV corrupto conserva exactamente sus bytes y produce código no cero.
- No se genera un manifest nuevo tras un fallo de lectura.
- `sleep.csv` nunca se escribe directamente sobre el canónico.
- Tests de integración para CORE, BETA y sleep.
- El contrato de datos documenta la lectura fail-closed y los esquemas completos.

## Riesgo residual

La recuperación seguirá requiriendo reparar o restaurar el archivo; el objetivo es impedir una pérdida silenciosa adicional. La compatibilidad de cualquier backup externo no inspeccionado, incluido el volumen activo de Railway, debe verificarse antes del despliegue.
