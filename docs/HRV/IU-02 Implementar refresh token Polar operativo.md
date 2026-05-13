## Objetivo

Evitar que la expiracion del access token degrade el sistema cuando el refresh token ya podria resolverlo de forma transparente.

---

## Diagnostico

Hoy varias rutas internas tratan token expirado como token inutilizable:

- el flujo diario puede perder continuidad
- el enriquecimiento de sesiones puede quedarse sin Polar
- el sistema depende demasiado de reautenticacion manual

Esto genera fragilidad operativa innecesaria para un caso N=1 que deberia ser estable.

---

## Alcance propuesto

- anadir helper de refresh en la capa OAuth
- refrescar antes de declarar token invalido
- persistir el nuevo bundle de tokens de forma atomica
- reutilizar el mismo criterio desde `polar_oauth_local.py` y `polar_sessions.py`
- dejar trazabilidad clara de refresh correcto o refresh fallido

---

## Riesgos y limites

- no loguear payloads sensibles
- no mezclar refresh con rediseno completo del cliente Polar
- no tocar semantica HRV ni contratos de CSV

---

## Criterios de aceptacion

1. Si hay refresh token valido, la expiracion del access token no rompe el flujo.
2. El refresh actualiza persistencia de tokens de forma segura.
3. Los consumidores internos usan una ruta comun o equivalente coherente.
4. Los errores de refresh quedan observables sin exponer secretos.
