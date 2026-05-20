## Objetivo

Hacer que `ENDURANCE_HRV_sleep.csv` tenga la misma garantia minima de persistencia que ya existe en otras partes del sistema.

---

## Diagnostico

La escritura directa del archivo de sueno deja una ventana de riesgo:

- truncado si el proceso cae en mitad del write
- corrupcion visible si hay timeout o cierre abrupto
- incoherencia con el patron atomico ya usado para tokens y para salidas de sesiones

No es una mejora teorica. Es una mejora de integridad de datos con coste bajo.

---

## Alcance propuesto

- escribir a temporal en el mismo directorio
- `flush/fsync` si aplica
- reemplazo atomico del archivo final
- conservar esquema, orden y semantica actual del CSV

---

## Limites

- no rehacer `sleep_store`
- no cambiar columnas ni merge incremental
- no tocar logica de fetch de Polar

---

## Criterios de aceptacion

1. El archivo final nunca queda medio escrito por una interrupcion normal del proceso.
2. El comportamiento funcional del pipeline no cambia.
3. El patron queda alineado con utilidades atomicas ya presentes en el repo.
