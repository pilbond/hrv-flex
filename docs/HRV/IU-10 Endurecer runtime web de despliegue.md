## Objetivo

Reducir fragilidad operativa del arranque web y limpiar desajustes menores de runtime/documentacion.

---

## Diagnostico

La app ya mejoro en varios puntos de despliegue, pero queda deuda pequena y real:

- arranque todavia muy basico
- ausencia de `.dockerignore`
- incoherencias documentales de timeout/runtime

No es el primer problema del sistema, pero si una mejora razonable de higiene operativa.

---

## Alcance propuesto

- revisar estrategia de arranque web si hay alternativa simple y robusta
- anadir `.dockerignore` minimo
- alinear timeout documentado con timeout real
- mantener compatibilidad con Railway y Python 3.11

---

## Limites

- no convertir esto en una migracion de plataforma
- no introducir dependencias nuevas sin valor claro
- no tocar logica HRV

---

## Criterios de aceptacion

1. El runtime queda algo mas robusto sin complejidad innecesaria.
2. La documentacion operativa deja de contradecir al codigo en puntos basicos.
3. El despliegue actual sigue funcionando en Railway.
