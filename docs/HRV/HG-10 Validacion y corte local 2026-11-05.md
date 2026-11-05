# HG-10: validación y corte local (2026-11-05)

Estado: generación HG-10 publicada en `data/` local el 2026-11-05; Railway no migrado en este corte.

## Alcance adoptado en el código

HG-03 (pares RR físicamente consecutivos), HG-04 (inicio fijo 90 s, corte 375 s y recorte 15 s), HG-05 (descartes del tramo) y la política de Calidad B integrada en HG-10. HG-07/08 permanecen exploratorias: no se adopta fusión de RR ni otro detector ECG. HG-01 es contexto en sombra; HG-02 separa la auditoría SSM manual del sync diario.

## Evidencia de la candidata

- Fuente RR: 513 archivos distintos en `out/hg10_513_gva0ajt_/rr/`; las 513 huellas del manifiesto coinciden.
- Generación recalculada: `out/hg_release_validation_20261105_fresh/`. CORE tiene 513 fechas únicas y 19 columnas; FINAL tiene 513 fechas y 67 columnas; SSM tiene 541 días de calendario.
- CORE coincide byte a byte con la candidata anterior (`sha256 35b0f40502821113e296d69c8c3c7bdc92f5191c6626753530463ba16f72945b`). BETA_AUDIT difiere solo en redondeos numéricos, máximo absoluto `6.7e-15`.
- CORE/BETA, FINAL/DASHBOARD/sidecar y la procedencia CORE→FINAL y CORE/sesiones/sueño→SSM verifican por SHA-256. El `sessions_day` de la candidata actual coincide con el operativo (`sha256 e99b8cffdd7aef8cd65fad0f863cf27e16f2910fd11c3a5009cf24daec070fea`).
- Un segundo procesamiento normal de CORE sobre la candidata conservó exactamente la huella de CORE.
- La suite completa: 758 pruebas pasadas, con 4 pruebas que requieren crear carpetas temporales bajo `tests/` ejecutadas por separado. Se corrigieron dos tests obsoletos: ruta fija del otro checkout y un doble de archivo temporal incompleto.
- Frente a `data/` operativo: 81 cambios de `gate_final` y 98 de `Action`. Las fechas 2026-02-26, 2026-02-27 y 2026-03-03 faltan tanto en el CORE operativo como en la candidata; ninguna fecha operativa se pierde.

## Ensayo de publicación y recuperación

En `out/hg10_rehearsal_20261105/` se copiaron los 19 ficheros `ENDURANCE_HRV_*` de la raíz de `data/` a `active/` y `rollback/`. Sobre `active/` se instalaron los nueve artefactos candidatos, se retiraron de esa copia los dos briefs IA `*_latest.json` antiguos y se regeneraron CORE, FINAL y SSM. La cadena de manifiestos y todas las huellas de salida coincidieron. Se restauraron los 19 ficheros desde `rollback/`: cero discrepancias de huella.

## Procedimiento de corte operativo y recuperación

1. Confirmar que no hay sync HRV ni sync de sesiones en marcha y que las entradas `sleep`, `sessions_day` y `wellness_subjective` siguen coincidiendo con la copia validada. Si cambian, repetir los derivados en copia aislada.
2. Crear un respaldo fechado de los 19 `ENDURANCE_HRV_*` de la raíz de `data/`, con SHA-256 por fichero. Conservar también los briefs IA `*_latest.json`; el historial `data/ai_briefs/` permanece histórico.
3. Instalar en `data/` los nueve artefactos CORE, BETA, FINAL, DASHBOARD, SSM, sidecar y manifiestos; apartar los dos briefs `*_latest.json` anteriores en el respaldo para que la UI use su texto determinista hasta el próximo brief válido.
4. Regenerar CORE usando solo los 513 RR fijados por huella, luego FINAL y SSM, para que los manifiestos referencien `data/`. Verificar esquema, fechas, huellas y cadena de manifiestos; comprobar `/api/status`, `/health` y un sync posterior con RR nuevo.
5. Si cualquier verificación falla, restaurar los 19 archivos del respaldo y comprobar todas las huellas originales antes de reactivar el sync. Conservar el informe del ensayo y el respaldo para auditoría.

El corte afecta solo a este checkout local. El despliegue Railway y su volumen requieren su propio corte coordinado y respaldo del volumen; no están cubiertos por esta validación.

## Resultado del corte local

Con autorización explícita se respaldaron y verificaron por SHA-256 los 19 archivos `ENDURANCE_HRV_*` en `data/backup/hg10_pre_cutover_20261105_approval/`. Los dos briefs IA `*_latest.json` anteriores se apartaron en `stale_latest/` dentro de ese respaldo; el historial fechado no se modificó. Se instalaron los nueve artefactos HG-10 y se regeneraron CORE, FINAL/DASHBOARD y SSM en `data/` para fijar rutas y huellas de la generación local.

Resultado: CORE 513 filas / 19 columnas, FINAL 513 filas / 67 columnas, SSM 542 días de calendario. Todas las huellas de salida coinciden con los manifiestos y FINAL enlaza el manifiesto CORE actual. `canonical_geometry_issue()` devuelve `None`; `/health` y `/health?strict=1` devuelven 200. La suite posterior al corte pasó: 754 pruebas en el entorno aislado y cuatro pruebas adicionales que crean carpetas en `tests/`, total 758.

El respaldo se conserva para recuperación. Las acciones y gates modificados respecto al histórico anterior son los 98 y 81 ya auditados. Los briefs IA `latest` se regenerarán en una ejecución autorizada del flujo de IA; mientras tanto la UI utilizará el texto determinista. El volumen Railway no fue modificado.