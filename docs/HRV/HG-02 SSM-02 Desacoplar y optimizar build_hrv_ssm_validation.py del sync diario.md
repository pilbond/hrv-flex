> Tarjeta Kanvas: `HG-02` - grupo `HRV Global`, estado `cyan` (revisión pendiente).
> Documento de referencia: [ANALISIS_SSM_VALIDATION_RENDIMIENTO_2026-05-29.md](../../research/audits/system/2026-05-29/ANALISIS_SSM_VALIDATION_RENDIMIENTO_2026-05-29.md)

## Texto de la tarjeta

Desacoplar `build_hrv_ssm_validation.py` del sync diario y dejar su ejecución como auditoría manual bajo demanda.

La motivación es operativa: el reporte de validación y la batería exploratoria no alimentan la decisión diaria, pero sí consumen tiempo de pared que no merece pagarse en cada `POST /api/sync`.

## Criterio de cierre

1. `POST /api/sync` deja de ejecutar validación y batería SSM.
2. Existe un entrypoint manual explícito para la auditoría SSM.
3. El documento de rendimiento recoge la medición real posterior al cambio.
4. La tarjeta Kanvas apunta a este `.md` como localización canónica de la tarea.

## Nota operativa

La auditoría manual queda como:

```bash
python polar_hrv_automation.py --ssm-audit
```

La información detallada de rendimiento y la verificación posterior están en:

- [research/audits/system/2026-05-29/ANALISIS_SSM_VALIDATION_RENDIMIENTO_2026-05-29.md](../../research/audits/system/2026-05-29/ANALISIS_SSM_VALIDATION_RENDIMIENTO_2026-05-29.md)
- [docs/contracts/GUIA_PYTHON_SCRIPTS.md](../contracts/GUIA_PYTHON_SCRIPTS.md)
