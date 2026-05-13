## Objetivo

Mantener `GET /api/status` como diagnostico util sin convertirlo en inventario interno del entorno.

---

## Diagnostico

El endpoint hoy mezcla dos cosas:

- estado operativo que si aporta valor
- detalles internos que no aportan al usuario final y si amplian superficie de exposicion

En una app personal esto no es una catastrofe, pero sigue siendo deuda operativa real.

---

## Alcance propuesto

- conservar estado de jobs, salud basica y banderas utiles
- reducir paths absolutos, detalles internos y presencia de secretos inferibles
- separar mejor diagnostico para UI de diagnostico para debugging local

---

## Decisiones

- no eliminar el endpoint si la UI lo necesita
- no introducir autenticacion compleja salvo necesidad clara
- priorizar minimizacion de datos antes que mas funcionalidad

---

## Criterios de aceptacion

1. La UI sigue pudiendo representar estado de jobs y salud basica.
2. El endpoint deja de exponer detalles internos innecesarios.
3. El troubleshooting razonable sigue siendo posible.
