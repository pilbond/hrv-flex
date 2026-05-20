## Objetivo

Mejorar observabilidad y seguridad de errores sin convertir el sistema en una cascada de logs verbosos.

---

## Diagnostico

Hay dos problemas distintos que hoy se mezclan:

- `except/pass` o fallos tragados en diagnosticos
- errores OAuth o HTTP remotos que pueden acabar demasiado crudos en logs o HTML

Eso empeora tanto la trazabilidad como la higiene de seguridad.

---

## Alcance propuesto

- reemplazar silencios por errores resumidos y seguros
- clasificar mejor error esperado vs error inesperado
- evitar interpolar cuerpos remotos o mensajes no confiables en la respuesta web
- revisar mensajes de log para que tengan contexto suficiente

---

## Limites

- no introducir framework nuevo de logging
- no reescribir toda la app Flask
- no esconder errores reales detras de mensajes genericos inutiles

---

## Criterios de aceptacion

1. Los errores relevantes quedan visibles en logs con contexto suficiente.
2. No se exponen cuerpos remotos completos en HTML o mensajes inseguros.
3. La experiencia de debugging mejora frente al estado actual.
