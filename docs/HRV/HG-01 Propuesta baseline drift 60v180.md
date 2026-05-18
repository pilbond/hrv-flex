

> Tarjeta Kanvas: `HG-01` - grupo `HRV Global`, estado `purple` (propuesta).
> Documento precedente: [SYA-10 Backlog diferido de senales retrospectivas y HRV longitudinal.md](SYA-10%20Backlog%20diferido%20de%20senales%20retrospectivas%20y%20HRV%20longitudinal.md)
> Documento relacionado: [Baseline adaptativo a largo plazo..md](Baseline%20adaptativo%20a%20largo%20plazo..md)

## Texto de la tarjeta

Objetivo: formalizar y evaluar la propuesta de `baseline drift 60v180` como tarea HRV global separada, fijando su relacion con el baseline adaptativo de largo plazo, su impacto potencial sobre baseline, flags y gate, y sus criterios de activacion.

Esta tarea no implementa aun cambios en `build_hrv_core.py`, `build_hrv_final_dashboard.py`, `FINAL`, `DASHBOARD` ni en la semantica operativa del gate HRV.

---

## Analisis tecnico 2026-05-05

### Que pretende medir

`baseline drift 60v180` intenta capturar una deriva estructural entre:

- una referencia mas corta o mas reciente del atleta
- una referencia mas larga o historicamente alta

La intuicion es sencilla:

- si el atleta pasa mucho tiempo estable en un rango nuevo
- pero el sistema sigue comparando contra un periodo historico ideal ya lejano
- entonces `baseline60_degraded` puede quedarse activado durante meses sin representar bien el "normal actual"

No es una senal de coaching ni de sesion. Es una cuestion de semantica central del motor HRV.

### Por que merece tarjeta propia

Esta propuesta no encaja como ampliacion de `analysis/` por tres razones:

- toca el baseline fisiologico de referencia
- puede cambiar la interpretacion de `degraded`, `green`, `amber` o `red`
- puede afectar la lectura longitudinal del atleta incluso sin cambiar ninguna sesion

Por tanto, su destino natural es una tarea HRV global separada.

### Relacion con baseline adaptativo de largo plazo

Hoy existe ya la nota [Baseline adaptativo a largo plazo..md](Baseline%20adaptativo%20a%20largo%20plazo..md), que plantea el problema de fondo:

- el `healthy_period` historico puede quedar demasiado alto respecto al nuevo estado estable del atleta
- eso puede degradar durante meses una lectura que ya no refleja una anomalia aguda, sino un nuevo normal

`baseline drift 60v180` parece la misma familia de problema, pero formulada como comparacion entre ventanas.

La tarea debe decidir si:

- `baseline drift 60v180` es solo una forma concreta de operacionalizar el baseline adaptativo
- o si es una senal separada que convive con otra logica de recalibracion

### Preguntas que esta tarea debe resolver

1. Definicion operacional:
   que comparan exactamente `60` y `180`, con que estadistico y con que criterio de deriva
2. Impacto semantico:
   si la deriva cambia solo una lectura contextual o si modifica baseline, flags y gate
3. Politica de adaptacion:
   si el sistema debe recalibrar automaticamente, sugerir recalibracion o mantener doble escala
4. Compatibilidad historica:
   como preservar trazabilidad sin borrar la referencia al "historical best"
5. Riesgo de regresion:
   como evitar que un baseline dinamico normalice un deterioro real del atleta

### Criterios de aceptacion propuestos

1. Existe una definicion escrita y auditable de `baseline drift 60v180`.
2. Queda decidida su relacion con la propuesta de baseline adaptativo a largo plazo.
3. Se documenta si esta idea:
   - modifica baseline HRV
   - modifica flags o gate
   - o queda solo como lectura contextual separada
4. Existe criterio de reactivacion claro antes de cualquier implementacion.

### Condicion minima para pasar de `purple` a `red`

La tarjeta puede pasar a `red` solo si se cumplen a la vez estas condiciones:

1. existe una definicion operacional escrita de `baseline drift 60v180` con ventana, estadistico y umbral de deriva;
2. existe una decision documentada sobre si modifica `baseline`, `flags`, `gate` o si queda solo como lectura contextual;
3. existe una decision documentada sobre su relacion con [Baseline adaptativo a largo plazo..md](Baseline%20adaptativo%20a%20largo%20plazo..md): absorcion, equivalencia o convivencia separada.

### Fuera de alcance

- colar la idea en `analysis_only_context` o `reason_text`
- introducir cambios directos en el pipeline HRV sin decision semantica previa
- alterar contratos en `docs/contracts/` sin una definicion cerrada de impacto

### Conclusiones provisionales

`HG-01` tiene sentido como tarea propia porque fuerza a tratar el problema donde realmente vive:

- no en la narrativa analitica
- no en una capa weekly
- sino en la semantica del baseline HRV del sistema

Hasta resolver esa semantica, cualquier intento de hacerlo "dinamico" seria prematuro.
