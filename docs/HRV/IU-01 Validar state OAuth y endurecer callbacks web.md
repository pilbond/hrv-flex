## Objetivo

Cerrar los huecos reales del flujo OAuth web sin cambiar el alcance N=1 del proyecto ni rehacer la arquitectura completa del cliente Polar.

---

## Diagnostico

El riesgo no esta en usar OAuth web, sino en usarlo de forma incompleta:

- `/auth` genera `state` pero hoy la validacion posterior no esta cerrada.
- los callbacks mezclan logica de red, render HTML y manejo de errores.
- hay riesgo de interpolar errores remotos o parametros inseguros en respuestas HTML.

Esto no afecta a la logica HRV, pero si a la robustez de la frontera expuesta por `web_ui.py`.

---

## Alcance propuesto

- persistir `state` de forma minima y validar coincidencia en callback
- rechazar callbacks sin `state` valido
- sanear mensajes de error mostrados al usuario
- separar mejor error operativo, error remoto y respuesta HTML final
- revisar que el flujo oficial siga siendo web-only en produccion

---

## Decisiones y limites

- no introducir multiusuario
- no cambiar contratos HRV
- no abrir navegador desde backend
- no convertir esta tarea en un refactor general de `oauth_utils.py`

---

## Criterios de aceptacion

1. Un callback con `state` ausente o incorrecto se rechaza.
2. Los mensajes HTML no interpolan cuerpos remotos sin control.
3. El flujo productivo sigue siendo `GET /auth -> callback web -> persistencia`.
4. Los logs siguen siendo utiles sin exponer secretos.
