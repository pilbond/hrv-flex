# AYO-14 Evaluar e integrar MCP para Polar v4

## Estado

Propuesta dependiente de `AYO-13 Migrar Polar AccessLink de v3 a v4`.

## Objetivo

Evaluar si conviene importar, adaptar o construir un servidor MCP de solo
lectura para que agentes puedan consultar datos Polar v4 sin convertir MCP en
dependencia del pipeline canonico.

El MCP debe servir a consultas interactivas y a `analysis/`, no ejecutar ni
modificar:

- `CORE`;
- `BETA_AUDIT`;
- `FINAL`;
- `DASHBOARD`;
- `sleep.csv`;
- `sessions.csv`;
- jobs operativos de la UI.

## Candidato externo localizado

A fecha 2026-06-12 existe:

- repositorio: `davidmosiah/polar-mcp`;
- paquete npm: `polar-mcp-unofficial`;
- licencia: MIT;
- API declarada: Polar AccessLink Dynamic API v4;
- runtime: Node.js 20 o superior;
- enfoque: local-first y read-only;
- tokens en `~/.polar-mcp/tokens.json` con permisos `0600`;
- modos de privacidad y redaccion GPS;
- herramientas para sleep, Nightly Recharge, training sessions, PPI,
  continuous samples, tests, temperatura y skin contact;
- cache SQLite opcional;
- version npm observada: `0.3.5`.

La adopcion no debe ser automatica. Es un proyecto reciente y con adopcion
publica todavia baja. Requiere auditoria de codigo, dependencias, OAuth,
refresh, limites de payload y politica de actualizaciones.

## Opciones

### Opcion A. Importar el MCP sin cambios

Ventajas:

- menor coste inicial;
- cobertura v4 amplia;
- OAuth, diagnostico y privacidad ya implementados;
- herramientas y resumenes preparados para agentes.

Limites:

- segundo runtime Node junto al proyecto Python;
- segundo token store y potencialmente segundo cliente Polar;
- modelos normalizados distintos a los del pipeline;
- dependencia de mantenimiento y supply chain externa;
- callback local pensado para uso interactivo, no para Railway.

Uso aceptable:

- MCP local aislado para Codex u otros clientes;
- no instalarlo en la imagen Railway;
- no reutilizarlo desde `/api/sync`.

### Opcion B. Fork o adaptador fino

Ventajas:

- conserva gran parte de la cobertura existente;
- permite limitar scopes y herramientas;
- puede alinear privacidad, payloads y nombres con este repositorio.

Costes:

- responsabilidad de mantener el fork;
- seguimiento de upstream;
- sigue requiriendo Node 20 si se conserva la implementacion.

### Opcion C. MCP propio sobre el cliente Python v4

Ventajas:

- una sola normalizacion;
- una politica comun de errores, fechas y privacidad;
- mejor alineacion con `analysis/` y el caso N=1.

Costes:

- mayor trabajo inicial;
- hay que implementar y mantener protocolo MCP, OAuth local y herramientas;
- riesgo de duplicar capacidades ya disponibles.

## Recomendacion inicial

No construir desde cero como primera opcion.

Orden recomendado:

1. Completar el cliente y los modelos internos v4 de `AYO-13`.
2. Auditar `polar-mcp-unofficial` en una version fijada.
3. Probarlo localmente con credenciales y token store separados.
4. Comparar sus respuestas con los modelos internos v4.
5. Adoptarlo sin cambios si supera los gates.
6. Crear un adaptador o fork solo si las diferencias son pequenas.
7. Construir MCP propio solo si compartir modelos Python resulta decisivo o
   el candidato externo falla seguridad, mantenimiento o semantica.

## Herramientas minimas esperadas

- `polar_connection_status`;
- `polar_get_sleep(from, to)`;
- `polar_get_nightly_recharge(from, to)`;
- `polar_get_training_sessions(from, to, features)`;
- `polar_get_ppi_samples(from, to)`;
- `polar_get_tests(from, to)`;
- `polar_build_recovery_context(date)`;
- `polar_build_session_context(session_id)`.

Las dos herramientas de contexto deben devolver payloads acotados,
reproducibles y con:

- fuente;
- endpoint;
- fecha de consulta;
- ventana temporal;
- scopes usados;
- campos ausentes;
- avisos de calidad;
- version del normalizador.

## Gate de adopcion

1. Licencia compatible y version fijada.
2. Auditoria de dependencias sin vulnerabilidades criticas conocidas.
3. OAuth v4 y refresh correctos.
4. Tokens no visibles para el agente ni en logs.
5. Herramientas read-only.
6. GPS redactado por defecto.
7. Respuestas con limites de fecha, filas y bytes.
8. Timeouts, rate limiting y reintentos acotados.
9. Sin acceso a CSV personales salvo herramienta explicitamente aprobada.
10. Sin dependencia desde el pipeline productivo.
11. Tests reproducibles con fixtures.
12. Procedimiento claro de actualizacion, rollback y revocacion.

## Arquitectura objetivo

```text
Railway / sync canonico
        |
        v
cliente Python Polar v4 -> normalizadores -> pipeline y CSV

agente local
        |
        v
MCP Polar v4 -> Polar API o adaptador de solo lectura
```

No se acepta:

```text
/api/sync -> MCP -> Polar
```

## Criterios de aceptacion

1. Existe una decision documentada: importar, adaptar o construir.
2. El candidato elegido supera el gate de seguridad y privacidad.
3. El MCP funciona localmente con scopes minimos.
4. Ningun token aparece en respuestas MCP.
5. Las respuestas estan acotadas y no saturan el contexto del agente.
6. El MCP no escribe outputs canonicos.
7. Una caida del MCP no afecta a Railway ni al sync diario.
8. Se documenta instalacion, version fijada, actualizacion y revocacion.

## Referencias

- Polar AccessLink Dynamic API v4:
  https://www.polar.com/polar-api-v4/
- Candidato MCP:
  https://github.com/davidmosiah/polar-mcp
- Paquete npm:
  https://www.npmjs.com/package/polar-mcp-unofficial
