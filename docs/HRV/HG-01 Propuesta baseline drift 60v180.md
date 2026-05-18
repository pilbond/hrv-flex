

> Tarjeta Kanvas: `HG-01` - grupo `HRV Global`, estado `purple` (propuesta).
> Documento precedente: [SYA-10 Backlog diferido de senales retrospectivas y HRV longitudinal.md](SYA-10%20Backlog%20diferido%20de%20senales%20retrospectivas%20y%20HRV%20longitudinal.md)
> Documento relacionado: [Baseline adaptativo a largo plazo..md](Baseline%20adaptativo%20a%20largo%20plazo..md)

## Texto de la tarjeta

Objetivo: reformular y evaluar `baseline drift 60v180` como metrica HRV longitudinal de contexto separada de `PCV-02`, verificando si aporta senal independiente frente a `degraded_vs_best` y `degraded_vs_current_normal`, sin tocar gate, flags canonicos, `FINAL`, `DASHBOARD`, `sessions_day` ni `reason_text` por ahora.

Esta tarea no implementa cambios en `build_hrv_core.py`, `build_hrv_final_dashboard.py` ni en la semantica operativa del gate HRV.

---

## Analisis tecnico 2026-05-18

### Estado actual tras PCV-02

Desde `2026-05-13`, `PCV-02` ya resolvio el problema operativo central del baseline largo plazo:

- `FINAL` expone `degraded_vs_best` y `degraded_vs_current_normal`
- `warning_mode=adaptive90` pasa a ser el default operativo
- `baseline60_degraded` queda como alias legacy
- el warning largo sigue siendo informativo y no recolorea el gate

Por tanto, `HG-01` ya no debe plantearse como tarea candidata a modificar baseline, flags o gate. Su valor residual, si existe, es medir una deriva longitudinal adicional que complemente la lectura canónica ya implantada.

### Que pretende medir

`baseline drift 60v180` intenta capturar una deriva estructural entre:

- una referencia mas corta o mas reciente del atleta
- una referencia mas larga o historicamente alta

La intuicion es sencilla:

- si el atleta pasa mucho tiempo estable en un rango nuevo
- pero el sistema sigue comparando contra un periodo historico ideal ya lejano
- entonces `baseline60_degraded` puede quedarse activado durante meses sin representar bien el "normal actual"

No es una senal de coaching ni de sesion. En el estado actual del repo, tampoco es una pieza necesaria de la semantica central del motor HRV.

### Por que puede mantener tarjeta propia

Si se conserva, esta propuesta no encaja como ampliacion de `analysis/` por tres razones:

- pertenece a la capa HRV global longitudinal
- compara ventanas basales del atleta y no sesiones concretas
- puede afectar la interpretacion retrospectiva del estado basal aunque no cambie ninguna sesion

Por tanto, su destino natural sigue siendo una tarea HRV global separada, pero ya no como cambio urgente del warning canónico.

### Relacion con baseline adaptativo de largo plazo

Hoy existe ya la nota [Baseline adaptativo a largo plazo..md](Baseline%20adaptativo%20a%20largo%20plazo..md), que plantea el problema de fondo:

- el `healthy_period` historico puede quedar demasiado alto respecto al nuevo estado estable del atleta
- eso puede degradar durante meses una lectura que ya no refleja una anomalia aguda, sino un nuevo normal

Ese problema ya quedo absorbido operativamente por `PCV-02`.

`baseline drift 60v180` queda, como mucho, en la misma familia conceptual pero reformulado como comparacion cuantitativa entre ventanas.

La tarea debe decidir si:

- `baseline drift 60v180` no aporta nada nuevo y debe cerrarse como absorbida por `PCV-02`
- o si es una metrica separada que convive con la lectura canónica actual sin modificarla

### Preguntas que esta tarea debe resolver

1. Definicion operacional:
   que comparan exactamente `60` y `180`, con que estadistico y con que criterio de deriva
2. Impacto semantico:
   si la deriva queda solo como lectura contextual o si existe algun motivo fuerte para exponerla como metrica longitudinal aparte
3. Politica de adaptacion:
   si debe quedarse como ratio/indicador retrospectivo o si no merece entrar en outputs canonicos
4. Compatibilidad historica:
   como preservar trazabilidad sin borrar la referencia al "historical best"
5. Riesgo de regresion:
   como evitar duplicar semanticas ya cubiertas por `degraded_vs_current_normal`

### Criterios de aceptacion propuestos

1. Existe una definicion escrita y auditable de `baseline drift 60v180`.
2. Queda decidida su relacion con `PCV-02` y con la propuesta de baseline adaptativo a largo plazo.
3. Se documenta si esta idea:
   - se cierra como absorbida por `PCV-02`
   - o queda como lectura contextual separada
4. Existe criterio de reactivacion claro antes de cualquier implementacion.

### Condicion minima para pasar de `purple` a `red`

La tarjeta puede pasar a `red` solo si se cumplen a la vez estas condiciones:

1. existe una definicion operacional escrita de `baseline drift 60v180` con ventana, estadistico y umbral de deriva;
2. existe una decision documentada sobre si se cierra por absorcion en `PCV-02` o si queda como metrica contextual separada;
3. existe una decision documentada sobre su relacion con [Baseline adaptativo a largo plazo..md](Baseline%20adaptativo%20a%20largo%20plazo..md): absorcion, equivalencia o convivencia separada.

### Fuera de alcance

- colar la idea en `analysis_only_context` o `reason_text`
- introducir cambios directos en el pipeline HRV sin evidencia de valor incremental frente a `PCV-02`
- alterar contratos en `docs/contracts/` sin una definicion cerrada de impacto

### Conclusiones provisionales

Tras `PCV-02`, `HG-01` queda en `stand by`.

Si se retoma, debe hacerse como pregunta mas estrecha:

- aporta una metrica de deriva `60v180` informacion nueva no capturada por `degraded_vs_best` y `degraded_vs_current_normal`
- y puede demostrarse ese valor sin tocar gate ni warning canónico

Hasta demostrar ese valor incremental, la lectura prudente es backlog de investigacion/contexto, no cambio operativo.
