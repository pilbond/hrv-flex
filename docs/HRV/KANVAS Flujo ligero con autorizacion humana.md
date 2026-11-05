# Kanvas: flujo ligero con autorización humana

## Decisión

Kanvas se mantiene como tablero visual de propuestas, trabajo autorizado y
validación humana. No es una fuente normativa del dominio HRV: `AGENTS.md` y
`docs/contracts/` conservan esa prioridad.

El control humano es intencional y no debe eliminarse. En particular, el
agente no puede iniciar cambios en código, datos, configuración, documentación
operativa o despliegue por el mero hecho de que exista una propuesta.

## Flujo de estados

| Color | Estado | Responsable principal | Significado |
| --- | --- | --- | --- |
| Purple | Propuesta | Agente o humano | Idea por evaluar. No autoriza ejecución. |
| Orange | En curso | Humano al iniciar; agente durante el trabajo | Tarea expresamente autorizada para ejecución. Solo una persona puede mover una tarjeta de `purple` a `orange`. |
| Blue | Entregada para revisión | Agente | Trabajo terminado con evidencia de verificación; pendiente de validación humana. |
| Green | Cerrada | Humano | Trabajo aceptado y cerrado. Solo una persona puede marcar este estado. |
| Gray | Bloqueada | Agente o humano | No puede progresar; debe indicar la dependencia o decisión que falta. |

Se elimina el estado `red`: la autorización queda representada por el paso
directo y explícito de `purple` a `orange` realizado por una persona.

```text
purple (propuesta)
  └─ humano autoriza e inicia ──> orange (en curso)
                                    └─ agente entrega ──> blue (revisión humana)
                                                                  └─ humano valida ──> green (cerrada)
```

Una tarea puede pasar a `gray` desde cualquier estado no cerrado cuando exista
un bloqueo real. Al resolverse, la persona decide si vuelve a `purple` o a
`orange`.

## Reglas de autorización

1. El agente puede leer, diagnosticar y proponer trabajo desde `purple`.
2. El agente solo puede ejecutar cambios en una tarjeta que ya esté en
   `orange`.
3. La acción humana de mover `purple` a `orange` es la autorización explícita
   para ejecutar el alcance escrito en la tarjeta.
4. El agente termina el trabajo en `blue`; no lo considera aceptado ni cerrado.
5. Solo la persona revisora puede convertir `blue` en `green`, devolverla a
   `orange` con una observación concreta, o marcarla `gray` si aparece un
   bloqueo.

## Simplificación de las tarjetas

Cada tarjeta debe contener solo lo necesario para gobernar el trabajo:

- resultado esperado;
- criterio de aceptación verificable;
- dependencia o bloqueo, si existe.

El detalle técnico debe permanecer donde aporta más valor: cambios versionados,
pruebas, documentación contractual y resultados de análisis. Kanvas no debe
duplicar esa documentación.

Los cambios pequeños, reversibles y del mismo ámbito pueden agruparse en una
tarjeta de mantenimiento. Las iniciativas con impacto en lógica HRV, columnas,
QA, gating o semáforos deben seguir además la política de actualización de
`docs/contracts/` establecida en `AGENTS.md`.

## Problemas que esta variante mitiga

- Elimina la ambigüedad entre tarea aprobada, terminada y cerrada.
- Hace visible y auditable el permiso previo a cualquier ejecución del agente.
- Reduce el coste administrativo al suprimir un estado que no añade una
  decisión distinta.
- Evita que `blue` se interprete como cierre definitivo: la revisión humana es
  un paso obligatorio y explícito.
- Reduce el ruido del tablero al reservarlo para intención, autorización,
  estado y bloqueo; no para documentación duplicada.

## Límite operativo

El tablero puede reflejar el estado del trabajo, pero no sustituye la revisión
del diff, las pruebas ni los contratos del repositorio. Una tarjeta en `green`
expresa aceptación humana; la seguridad y corrección técnica siguen requiriendo
la evidencia correspondiente en el repositorio.
