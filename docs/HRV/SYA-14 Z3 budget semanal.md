# SYA-14 Z3 budget semanal

> Tarjeta Kanvas: `SYA-14` - grupo `Analysis / Coach`, estado `purple` (propuesta).
> Documento precedente: [SYA-10 Backlog diferido de senales retrospectivas y HRV longitudinal.md](SYA-10%20Backlog%20diferido%20de%20senales%20retrospectivas%20y%20HRV%20longitudinal.md)

## Texto de la tarjeta

Objetivo: formalizar y evaluar la idea de `z3 budget semanal` como senal `weekly` retrospectiva, fijando su semantica, su diferencia respecto a la capa actual de carga/intensidad y sus criterios de activacion.

Esta tarea no implementa aun la senal en `analysis_only_context`, `sessions_day`, `FINAL` ni `reason_text`.

---

## Analisis tecnico 2026-05-05

### Que pretende medir

`z3 budget semanal` intenta responder a una pregunta concreta:

- cuanto tramo de intensidad media-alta se ha "gastado" en la semana
- si la semana ya acumula suficiente densidad de trabajo en `Z3`
- si existe margen razonable para meter mas calidad o si el bloque ya va cargado

No es una lectura de una sesion aislada. Es una lectura agregada y retrospectiva.

### Por que merece tarjeta propia

La idea es util, pero hoy sigue siendo ambigua en cuatro puntos clave:

- que se entiende exactamente por `Z3` dentro del marco de 3 zonas del proyecto
- si el "budget" se expresa como minutos absolutos, porcentaje semanal o tolerancia historica
- como se diferencia de `load`, `strain`, `monotony`, clustering de intensidad y distribucion semanal ya existentes
- cual seria su destino natural exacto: weekly operativo, weekly retrospectivo o sidecar local

Sin cerrar esas preguntas, la senal corre riesgo de duplicar contexto ya disponible con otro nombre.

### Hipotesis de trabajo

La hipotesis razonable hoy es esta:

- la senal deberia vivir como capa `weekly` retrospectiva
- no debe describir una sesion concreta
- solo tiene sentido si aporta una lectura distinta de la carga acumulada y de la distribucion de intensidad ya observada

### Preguntas que esta tarea debe resolver

1. Definicion operacional:
   cuanto cuenta como `Z3` y en que unidad se mide el "budget"
2. Horizonte temporal:
   si la ventana correcta es semanal fija, rolling 7d o alguna variante por deporte
3. No redundancia:
   que informacion anade frente a `load_3d`, `ACWR/monotony/strain`, `intensity_clustering_*` y `DO-02`
4. Reglas de lectura:
   como distinguir "budget consumido", "budget alto pero tolerable" y "sobrecarga de Z3"

### Criterios de aceptacion propuestos

1. Existe una definicion escrita y auditable de `z3 budget semanal`.
2. Existe una comparacion explicita contra las capas actuales de carga e intensidad para justificar que no es redundante.
3. Queda decidido su destino natural:
   - weekly retrospectivo
   - weekly operativo
   - descartado por redundancia
4. Existe criterio de reactivacion claro antes de cualquier implementacion.

### Condicion minima para pasar de `purple` a `red`

La tarjeta puede pasar a `red` solo si se cumplen a la vez estas condiciones:

1. existe una definicion operacional escrita de `Z3` y del tipo de `budget` que se quiere medir;
2. existe una comparacion documentada contra `load_3d`, `ACWR/monotony/strain`, `intensity_clustering_*` y `DO-02`;
3. esa comparacion concluye de forma explicita que la senal aporta valor incremental no redundante;
4. queda fijado por escrito si su destino final es `weekly retrospectivo`, `weekly operativo` o descarte.

### Fuera de alcance

- tocar `sessions.csv`, `sessions_day.csv`, `FINAL` o `DASHBOARD`
- promover la idea directamente a `analysis/`
- reabrir por esta via la semantica HRV global

### Conclusiones provisionales

`SYA-14` tiene sentido como tarea separada porque transforma una intuicion valida en una decision tecnicamente defendible.

Hasta que no exista una definicion no redundante, debe tratarse como backlog estructurado y no como implementacion pendiente.
