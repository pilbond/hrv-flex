# Plan AYO-14 — Evaluación de valor y abordaje MCP Polar v4

> **Tipo:** Plan + **decisión final** (no implementación).
> **Estado de la decisión:** **CERRADA — Opción D (no construir).** Ver §10 Conclusiones finales.
> **Fecha:** 2026-06-14.
> **Tarea:** `AYO-14 Evaluar e integrar MCP para Polar v4` (estado `purple` en Kanvas).
> **Depende de:** `AYO-13 Migrar Polar AccessLink de v3 a v4` (`orange`, con F4/F5/F6 aún pendientes).
> **Decisión de timing (confirmada):** AYO-14 **se ejecuta después** de cerrar la migración v4. Este documento es solo el plan.
> **Consumidor (confirmado 2026-06-14):** el **único consumidor de Polar v4 es la propia aplicación**. No hay agente/host externo que requiera acceso directo → **sella la Opción D** (ver §1 y §9.1).
> **Documento base:** [[docs/HRV/AYO-14 Evaluar e integrar MCP para Polar v4]] (análisis previo de opciones A/B/C).

---

## 1. Veredicto ejecutivo

**Recomendación: NO construir un MCP propio de Polar v4 ahora, y NO adoptar por defecto el candidato externo.**

AYO-14 aporta **valor marginal/bajo** al proyecto en su estado actual. El motivo es simple y verificable en el código:

- El pipeline **ya descarga y normaliza** los datos de Polar que importan (sueño, nightly recharge, RR/ejercicios, sesiones, PPI, tests).
- **Ya existe** un cliente Python v4 funcional (`hrv_app/polar_client_v4.py`) que habla con todos los endpoints v4 relevantes. No hace falta un segundo cliente, ni en Node ni propio.
- El verdadero valor para un agente está en consultar **el producto interpretado** (estado HRV, gate, calidad, contexto) — eso es **AYO-15**, no AYO-14.

Por tanto, la decisión documentada que cierra el criterio de aceptación #1 de AYO-14 ("importar, adaptar o construir") es:

> **Opción D — No construir. Dejar el acceso directo a Polar v4 como capacidad bajo demanda, resuelta con lo que ya existe (un CLI fino sobre `polar_client_v4.py`), y mantener el candidato externo solo como recurso aislado opcional si aparece una necesidad exploratoria real.**

Y la recomendación de prioridad de cartera:

> **Priorizar AYO-15 (MCP de la aplicación) por encima de AYO-14.** AYO-15 expone el valor diferencial del proyecto; AYO-14 expone datos del proveedor que el pipeline ya cubre.

Esto respeta la prioridad declarada: **simpleza, utilidad y buen funcionamiento por encima de sobreingeniería.**

---

## 2. Qué pide AYO-14 y en qué se diferencia de AYO-15

| | **AYO-14** | **AYO-15** |
|---|---|---|
| Expone | Datos **crudos del proveedor** (Polar API v4) | El **producto propio** ya calculado (estado, gate, calidad, contexto) |
| Fuente | Polar API v4 en vivo (vía cliente o MCP externo) | Artefactos locales ya generados (CSV/JSON/manifests) |
| Runtime candidato | Node.js (`polar-mcp-unofficial`) o propio | Python (`stdio`) |
| Credenciales | Requiere OAuth/token Polar | No requiere credenciales |
| Valor diferencial | Bajo (duplica lo que el pipeline ya captura) | Alto (semántica, QA y trazabilidad propias) |

Son **complementarios, no intercambiables**. La confusión habitual es tratarlos como lo mismo: AYO-14 = "acceso al proveedor"; AYO-15 = "estado normalizado e interpretado por la app".

```text
Polar MCP (AYO-14)   -> acceso al proveedor (datos crudos)
HRV App MCP (AYO-15) -> estado normalizado, auditado e interpretado por la app
```

---

## 3. Evaluación de valor: ¿aporta algo a este proyecto?

### 3.1 Lo que el pipeline + cliente v4 YA cubren (solapamiento)

Verificado en código (`hrv_app/polar_client_v4.py`, `polar_adapters_v4.py`, `sleep_store.py`, `hrv_sync_flow.py`):

| Dato Polar v4 | Endpoint v4 implementado | ¿Lo usa el pipeline hoy? |
|---|---|---|
| Sueño | `/sleeps` (`fetch_sleeps`) | Sí → `ENDURANCE_HRV_sleep.csv` |
| Nightly Recharge | `/nightly-recharge-results` (`fetch_nightly_recharges`) | Sí → sleep store |
| Ejercicios / RR | `list_exercises` + samples | Sí → CORE/FINAL |
| Sesiones de entrenamiento | `/training-sessions/list` (`list_training_sessions`) | Sí (vía Intervals + Polar Flow) |
| PPI samples | `/ppi-samples` (`fetch_ppi_samples`) | Parcial (disponible en cliente) |
| Tests | `/tests/list` (`fetch_tests`) | Disponible en cliente, uso limitado |

**Conclusión:** un MCP de Polar v4 no abre datos nuevos relevantes que el pipeline no pueda ya obtener con su propio cliente.

### 3.2 Dónde habría valor real (hueco)

AYO-14 solo aportaría valor neto si se cumple **alguna** de estas condiciones, hoy **no demostradas**:

1. Un agente necesita, de forma **recurrente**, datos Polar v4 que el pipeline **no persiste** (p. ej. temperatura de piel, *skin contact*, *continuous samples* de HR), y conviene exponerlos sin meterlos en el pipeline canónico.
2. Se necesita consultar Polar **en vivo**, más fresco que el último `sync`, en interacción ad-hoc.
3. Se quiere **comparar** la fuente cruda Polar frente al dato normalizado de la app para auditar la normalización.

Para un proyecto **N=1**, estos casos son **esporádicos**. Una capacidad permanente (MCP dedicado, runtime extra, segundo OAuth) es desproporcionada frente a su frecuencia de uso.

### 3.3 Costes que introduce AYO-14 (si se construye/adopta)

- Segundo runtime (Node) **o** segundo cliente Polar redundante con el Python ya existente.
- Segundo *token store* y segundo flujo OAuth (el callback del candidato externo está pensado para uso interactivo local, **no** para Railway).
- Riesgo *supply-chain*: el candidato es un paquete npm reciente, de baja adopción y mantenedor único.
- Superficie de mantenimiento y de seguridad adicional para un beneficio marginal.

**Balance:** coste estructural recurrente > valor esporádico. Salvo que emerja un consumidor claro, no compensa.

---

## 4. Opciones y trade-offs

Las tres opciones del documento base, más la opción mínima recomendada.

### Opción A — Importar el MCP externo sin cambios (`polar-mcp-unofficial`)
**Ventajas:** coste inicial casi nulo; cobertura v4 amplia; OAuth/privacidad/diagnóstico ya hechos; herramientas listas para agentes.
**Inconvenientes:** runtime Node junto a Python; segundo token store y cliente; modelos normalizados distintos a los del pipeline; dependencia de mantenimiento y *supply-chain* externa; callback no apto para Railway.
**Encaje:** aceptable **solo** como herramienta local aislada y bajo demanda; nunca en la imagen Railway ni reutilizado desde `/api/sync`.

### Opción B — Fork / adaptador fino del externo
**Ventajas:** conserva cobertura; permite recortar *scopes* y herramientas; alinea privacidad y nombres con el repo.
**Inconvenientes:** asumes el mantenimiento del fork y el seguimiento de *upstream*; sigue exigiendo Node 20.
**Encaje:** solo si A pasa el gate pero las diferencias semánticas son pequeñas y vale la pena corregirlas.

### Opción C — MCP propio en Python sobre `polar_client_v4.py`
**Ventajas:** una sola normalización y política de errores/fechas/privacidad; reutiliza el cliente v4 que **ya existe**; mejor alineación con `analysis/` y el caso N=1; sin runtime Node.
**Inconvenientes:** hay que implementar y mantener protocolo MCP, OAuth local interactivo, manejo de tokens y límites; duplica capacidades que el pipeline ya tiene si no hay un consumidor claro.
**Encaje:** preferible a A/B **si** se decide tener MCP de Polar propio, porque parte del cliente ya está. Pero solo se justifica con un caso de uso recurrente probado.

### Opción D — No construir; capacidad bajo demanda (RECOMENDADA)
**Qué es:** no se crea ningún MCP de Polar. Para la necesidad exploratoria puntual se usa **lo que ya existe**:
- un **CLI fino** (read-only) sobre `polar_client_v4.py` para volcar un rango/feature concreto cuando haga falta (coste muy bajo, reutiliza el cliente y la auth ya implementados), y/o
- el **candidato externo en local aislado** si en algún momento se quiere una superficie MCP rápida sin escribir código.

**Ventajas:** cero coste estructural; cero nueva dependencia productiva; cero segundo OAuth permanente; máxima simpleza; reutiliza lo existente; reversible y sin riesgo para Railway.
**Inconvenientes:** no ofrece descubrimiento automático de herramientas MCP (no necesario en N=1 mientras no haya consumidor recurrente).
**Encaje:** es la opción coherente con "simpleza > sobreingeniería" dado que el caso de uso aún no está claro.

### Tabla resumen

| Opción | Coste inicial | Coste recurrente | Riesgo | Reutiliza lo nuestro | Recomendada |
|---|---|---|---|---|---|
| A Importar externo | Muy bajo | Medio (Node, supply-chain) | Medio | No | Solo aislado/bajo demanda |
| B Fork | Medio | Alto (mantener fork) | Medio | Parcial | No (salvo diferencias pequeñas) |
| C MCP propio Python | Alto | Medio | Bajo | Sí | Solo si hay consumidor recurrente |
| **D No construir** | **Mínimo** | **Mínimo** | **Bajo** | **Sí** | **Sí** |

---

## 5. Plan de abordaje (cuando se ejecute, tras cerrar v4)

Plan en fases cortas, **condicionado** a que `AYO-13` haya cerrado F5 (corte a v4) y F6 (retirada v3). Cada fase tiene una salida que permite **parar sin deuda**.

### Fase 0 — Decisión y gate (sin código)
- Confirmar el caso de uso real (ver §7, decisiones abiertas). Si sigue sin haber consumidor recurrente → **cerrar AYO-14 con Opción D** y mover esfuerzo a AYO-15. Fin.
- Registrar la decisión documentada (cumple criterio de aceptación #1).
- **Entregable:** decisión + esta evaluación actualizada.

### Fase 1 — Capacidad mínima bajo demanda (Opción D)
*Solo si hace falta acceso a Polar v4 fuera del pipeline.*
- Definir 1–2 consultas concretas necesarias (p. ej. "volcar `tests` o `ppi-samples` de un rango").
- Especificar un CLI read-only fino sobre `polar_client_v4.py` con: validación de fechas, límites de filas/bytes, salida determinista, sin rutas absolutas ni secretos, y redacción de campos sensibles (GPS/RR crudos ocultos por defecto).
- **Entregable:** CLI puntual reutilizable; sin protocolo MCP, sin runtime nuevo.

### Fase 2 — Evaluación del candidato externo (solo si se quiere superficie MCP)
- Fijar versión exacta del paquete (`polar-mcp-unofficial`, p. ej. `0.3.5`) y auditar dependencias.
- Instalar **en local aislado**, con credenciales y *token store* separados; **nunca** en Railway.
- Comparar sus respuestas contra los modelos internos v4 (`polar_adapters_v4.py`) sobre fixtures.
- Pasar el **gate de adopción** (§6). Si pasa → Opción A (uso aislado). Si las diferencias son pequeñas y molestan → considerar Opción B.
- **Entregable:** informe de auditoría + decisión de adopción/descarte.

### Fase 3 — (Condicional) MCP propio Python
*Solo si Fase 0 demuestra un consumidor recurrente y el externo no satisface seguridad/semántica.*
- Envolver `polar_client_v4.py` con un servidor MCP `stdio` read-only y las herramientas mínimas del documento base (`polar_connection_status`, `polar_get_sleep`, `polar_get_nightly_recharge`, `polar_get_training_sessions`, `polar_get_ppi_samples`, `polar_get_tests`, y opcionalmente `polar_build_*_context`).
- Reutilizar OAuth/refresh v4 ya existentes (`polar_auth_v4.py`); SDK MCP como dependencia **opcional**, fuera de la imagen Railway.
- **Entregable:** MCP local aislado con tests de privacidad, límites y causalidad.

> **Nota de secuencia:** Fases 2 y 3 son **excluyentes** en la práctica (o adoptas externo, o construyes propio). No se hacen ambas.

---

## 6. Gate de adopción (para Opción A/B)

Reutiliza el gate del documento base. Un candidato externo no se adopta salvo que cumpla **todo**:

1. Licencia compatible (MIT) y **versión fijada**.
2. Auditoría de dependencias sin vulnerabilidades críticas conocidas.
3. OAuth v4 y *refresh* correctos.
4. Tokens **no** visibles para el agente ni en logs.
5. Herramientas estrictamente read-only.
6. GPS redactado por defecto.
7. Respuestas con límites de fecha, filas y bytes.
8. Timeouts, *rate limiting* y reintentos acotados.
9. Sin acceso a CSV personales salvo herramienta explícitamente aprobada.
10. **Sin dependencia desde el pipeline productivo.**
11. Tests reproducibles con fixtures.
12. Procedimiento claro de actualización, *rollback* y revocación.

---

## 7. Riesgos y mitigaciones

| Riesgo | Mitigación |
|---|---|
| Construir algo sin consumidor (sobreingeniería) | Fase 0 obligatoria: sin caso de uso recurrente → Opción D y stop. |
| *Supply-chain* del candidato externo | Versión fijada + auditoría + uso local aislado; nunca en Railway. |
| Segundo OAuth / token store divergente | Preferir reutilizar `polar_auth_v4.py`; el externo solo aislado y temporal. |
| Acoplar MCP al `sync` o a Railway | Prohibido `/api/sync -> MCP -> Polar`; MCP siempre fuera del camino crítico. |
| Duplicar normalización | Si se construye propio, reutilizar `polar_adapters_v4.py`, no reimplementar. |
| Exposición de datos sensibles (RR/GPS/tokens) | Allowlist de campos, redacción por defecto, tests negativos. |
| Confundir AYO-14 con AYO-15 | Mantener separación: proveedor vs producto (ver §2). |

---

## 8. Definición de "hecho" para AYO-14

AYO-14 se puede cerrar cuando exista una **decisión documentada y auditada**, aunque el resultado sea "no construir":

1. Decisión registrada: importar / adaptar / construir / **no construir** (criterio #1).
2. Si se adopta el externo: supera el gate de seguridad y privacidad (§6).
3. Si se construye/usa CLI: read-only, sin credenciales expuestas, payloads acotados, fuera del camino crítico de Railway.
4. Una caída de cualquier pieza MCP/CLI **no** afecta al `sync`, la UI ni Railway.
5. Documentado: versión fijada, instalación, actualización y revocación.

Con la recomendación de este plan (Opción D), 1, 3, 4 y 5 se satisfacen sin escribir un MCP.

---

## 9. Decisiones abiertas

1. ~~**Caso de uso recurrente:** ¿existe ya un agente/host que necesite Polar v4 crudo de forma habitual?~~ **RESUELTA (2026-06-14):** no. El único consumidor de Polar v4 es la propia aplicación → **Opción D confirmada**.
2. **Prioridad frente a AYO-15:** ¿se acepta posponer/cerrar AYO-14 y dedicar el esfuerzo MCP a AYO-15 (mayor valor)? — *Pendiente, pero la recomendación es sí.*
3. **Datos fuera del pipeline:** ¿hay interés real en temperatura de piel / *skin contact* / *continuous samples* que hoy no se persisten? — *Pendiente; si surge, se cubre con un CLI fino sobre `polar_client_v4.py` (Fase 1), no con un MCP.*

---

## 10. Conclusiones finales

**Decisión: CERRADA — Opción D (no construir MCP de Polar v4).**

Fundamento, ya verificado y confirmado:

1. **No hay consumidor que lo justifique.** Confirmado el 2026-06-14: el **único consumidor de Polar v4 es la propia aplicación**. Ningún agente/host externo necesita acceso directo al proveedor.
2. **El acceso ya está resuelto internamente.** La app habla con Polar v4 mediante `hrv_app/polar_client_v4.py` (`/sleeps`, `/nightly-recharge-results`, `/training-sessions/list`, `/ppi-samples`, `/tests/list`) y normaliza con `polar_adapters_v4.py`. Un MCP de Polar duplicaría capacidades existentes.
3. **El valor MCP del proyecto está en el producto, no en el proveedor.** Exponer estado HRV interpretado, gate, calidad y contexto corresponde a **AYO-15**, que sí tiene consumidor potencial (cualquier agente que consulte el estado del atleta).
4. **Coste > beneficio.** Construir/adoptar AYO-14 ahora añadiría runtime/cliente redundante, segundo OAuth y *token store*, y riesgo *supply-chain*, a cambio de un beneficio inexistente hoy. Contradice "simpleza, utilidad y buen funcionamiento por encima de sobreingeniería".

**Qué NO se hace:**

- No se construye MCP propio de Polar (Opción C).
- No se adopta ni forkea el candidato externo `polar-mcp-unofficial` (Opciones A/B).
- No se añade nada al camino crítico de Railway ni al `sync`.

**Qué queda en reserva (sin trabajo ahora):**

- Si algún día aparece un consumidor externo recurrente, o interés en datos Polar que el pipeline no persiste (temperatura de piel, *skin contact*, *continuous samples*), la primera respuesta es un **CLI fino read-only sobre `polar_client_v4.py`** (Fase 1). Solo si eso no basta se reevalúa el candidato externo (Fase 2) o un MCP propio (Fase 3), pasando el gate de §6.

**Próximos pasos recomendados:**

1. Marcar **AYO-14 como resuelta por decisión** (no requiere desarrollo). Cumple su criterio de aceptación #1 ("existe una decisión documentada").
2. **Redirigir el esfuerzo MCP a AYO-15**, donde está el valor real.
3. Mantener este documento como registro de la decisión; revisar solo si cambia la premisa del consumidor único.

---

## 11. Referencias

- Documento base de opciones: [[docs/HRV/AYO-14 Evaluar e integrar MCP para Polar v4]]
- Tarea complementaria: [[docs/HRV/AYO-15 Crear MCP de solo lectura para la aplicacion HRV]]
- Cliente v4 ya implementado: `hrv_app/polar_client_v4.py`, `hrv_app/polar_adapters_v4.py`, `hrv_app/polar_auth_v4.py`
- Candidato externo: https://github.com/davidmosiah/polar-mcp · https://www.npmjs.com/package/polar-mcp-unofficial
- Polar AccessLink Dynamic API v4: https://www.polar.com/polar-api-v4/
- Arquitectura/seguridad MCP: https://modelcontextprotocol.io/docs/learn/architecture
