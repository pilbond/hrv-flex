# Objetivo

Reducir el ruido estructural de la carpeta raiz del repositorio separando:

- entrypoints operativos reales,
- modulos internos reutilizables,
- y scripts auxiliares o manuales.

La tarea no busca cambiar el comportamiento funcional del sistema HRV. Busca mejorar claridad estructural, trazabilidad y mantenibilidad sin romper:

- comandos CLI existentes,
- subprocess ya usados por `web_ui.py`,
- imports del modulo `analysis/`,
- contratos documentados en `AGENTS.MD` y `docs/contracts/`,
- ni el despliegue actual en Railway.

## Estado actual

La migracion de la opcion B ya se ejecuto en el repo actual:

- los modulos internos viven en `hrv_app/`;
- los entrypoints canonicos siguen en la raiz;
- los scripts auxiliares viven en `scripts/python/`;
- los contratos y guias activas deben citar `hrv_app.*` cuando hablen de implementacion interna;
- este documento conserva el contexto de diseno y la justificacion de la reorganizacion.

## Problema actual

Tras ejecutar `ARQ-01`, la raiz del repo sigue mezclando tres tipos de ficheros Python:

1. entrypoints operativos canonicos:
   - `web_ui.py`
   - `polar_hrv_automation.py`
   - `build_hrv_core.py`
   - `build_hrv_final_dashboard.py`
   - `build_sessions.py`
   - `egc_to_rr.py`

2. modulos internos de implementacion:
   - `config.py`
   - `hrv_sync_flow.py`
   - `dropbox_rr.py`
   - `sleep_store.py`
   - `intervals_sync.py`
   - `pipeline_runner.py`
   - `polar_client.py`
   - `polar_oauth_local.py`
   - `polar_sessions.py`
   - `polar_utils.py`
   - `oauth_utils.py`
   - `cli_reporting.py`

3. scripts auxiliares, de mantenimiento o de prueba manual:
   - `intervals_wellness_test.py`
   - `intervals_resting_hr_from_core.py`
   - `build_historical_hrv_compare.py`
   - `add_ans_balance_to_core.py`

4. ficheros no-HRV o de apoyo local que hoy tambien ensucian la raiz:
   - `canvas-tool.py` (copia local del tooling Kanvas, no parte del runtime HRV)

5. directorios de ruido o soporte local en raiz que merecen clasificacion explicita:
   - temporales de smoke/debug:
     - `tmp_hrv_core_smoke/`
     - `tmp_hrv_core_smoke2/`
     - `tmp_hrv_final_smoke/`
     - `tmp_hrv_final_smoke2/`
     - `.tmp_pip/`
   - historicos o manuales a revisar:
     - `backup/`
     - `research/archive/new/` (antes `new/`)
   - directorios con uso o referencias activas que no deben tratarse igual:
     - `seed_upload/` (directorio operativo real usado por `web_ui.py`)
     - `delete/` (referencia activa en `analysis/`, pero no directorio operativo del flujo HRV)

Eso vuelve poco legible la raiz y complica distinguir:

- que es API interna del sistema,
- que es un comando soportado,
- y que es una utilidad lateral.

## Tesis

No conviene crear una carpeta generica tipo `python/`.

La separacion correcta debe expresar fronteras reales:

- **raiz** para entrypoints y contratos de operacion,
- **paquete interno** para modulos reutilizables,
- **scripts/python/** para utilidades manuales o sidecars.

Pero esa reorganizacion tiene dos niveles posibles de alcance:

- **opcion minima**: limpiar la raiz moviendo solo scripts auxiliares;
- **opcion completa**: introducir paquete interno y actualizar imports reales del repo.

Antes de ejecutar la opcion completa hay que cerrar un inventario explicito de dependencias e imports.

## Opciones de alcance

### Opcion A — limpieza ligera de la raiz

Mover solo scripts auxiliares a `scripts/python/`:

- `intervals_wellness_test.py`
- `intervals_resting_hr_from_core.py`
- `build_historical_hrv_compare.py`
- `add_ans_balance_to_core.py`
- retirar `canvas-tool.py` de la raiz, al ser copia local del tooling Kanvas y no parte del runtime HRV
- clasificar directorios ruidosos de la raiz:
  - eliminar temporales de smoke/debug cuando no formen parte del trabajo activo
  - revisar `backup/` y `research/archive/new/` como material historico/manual a reubicar o dejar fuera de alcance
  - mantener `seed_upload/` fuera del alcance de limpieza visual al ser directorio operativo
  - tratar `delete/` como referencia activa de `analysis/`, pero no como directorio operativo del flujo HRV

Ventajas:

- coste bajo,
- riesgo muy bajo,
- mejora visual inmediata,
- no exige tocar imports de produccion.

Limite:

- no separa fisicamente los modulos internos ya extraidos en `ARQ-01`.

### Opcion B — paquete interno + limpieza estructural

Crear un paquete interno y mover ahi los modulos de implementacion.

Ventajas:

- la estructura del repo refleja por fin la separacion lograda en `ARQ-01`,
- se distinguen mejor entrypoints, API interna y scripts auxiliares,
- reduce ruido cognitivo en la raiz.

Coste:

- requiere inventario de imports,
- actualizacion de consumidores,
- regression gate mas estricto,
- y una politica clara de compatibilidad transitoria.

Decision recomendada:

- ejecutar primero una **fase 0** de auditoria,
- y solo despues decidir si `AYO-11` se queda en opcion A o avanza a opcion B.

## Propuesta estructural

Esta propuesta aplica solo si la Fase 0 concluye **opcion B**.

### 1. Mantener en raiz solo entrypoints operativos canonicos

Se quedarian en raiz:

- `web_ui.py`
- `polar_hrv_automation.py`
- `build_hrv_core.py`
- `build_hrv_final_dashboard.py`
- `build_sessions.py`
- `egc_to_rr.py`

Motivo:

- son comandos o entrypoints citados en `AGENTS.MD`,
- aparecen en docs operativas,
- y algunos ya son invocados por subprocess o por Railway.

### 2. Mover modulos internos a un paquete dedicado

Paquete propuesto: `hrv_app/`

Mover ahi:

- `config.py`
- `cli_reporting.py`
- `dropbox_rr.py`
- `hrv_sync_flow.py`
- `intervals_sync.py`
- `oauth_utils.py`
- `pipeline_runner.py`
- `polar_client.py`
- `polar_oauth_local.py`
- `polar_sessions.py`
- `polar_utils.py`
- `sleep_store.py`

Motivo:

- son piezas de implementacion interna,
- no deberian competir visualmente con entrypoints,
- y ya tienen cohesion suficiente para vivir como paquete.

Nota sobre `pipeline_runner.py`:

- aunque no tenga imports cruzados con otros modulos internos, su inclusion en `hrv_app/` se justifica por cohesion funcional;
- forma parte de la capa operativa interna que encapsula la ejecucion de builders y no del conjunto de entrypoints publicos del repo.

### 3. Mover scripts auxiliares a `scripts/python/`

Destino recomendado y fijado para esta tarea: `scripts/python/`

Candidatos:

- `intervals_wellness_test.py`
- `intervals_resting_hr_from_core.py`
- `build_historical_hrv_compare.py`
- `add_ans_balance_to_core.py`

Motivo:

- no forman parte del flujo canonico diario,
- tienen uso manual o puntual,
- y hoy ocupan espacio de decision en la raiz sin ser entrypoints principales.

## Estrategia recomendada

La migracion no debe hacerse como corte brusco.

### Fase 0 — inventario obligatorio de imports y consumidores

Antes de mover ningun modulo hay que mapear:

- entrypoints que importan modulos internos;
- modulo `analysis/` que importa simbolos desde raiz;
- tests que importan por nombre de modulo en raiz;
- imports cruzados entre los propios modulos candidatos al paquete interno;
- y cualquier subprocess, start command o doc que dependa de rutas actuales.

Consumidores ya identificados que deben entrar en ese inventario:

- `web_ui.py` arranca en Railway/Nixpacks con `python web_ui.py` y hoy importa `polar_utils` y `oauth_utils` por nombre de raiz;
- `polar_hrv_automation.py` hoy importa `config`, `polar_client`, `polar_oauth_local` y `hrv_sync_flow` por nombre de raiz;
- `build_sessions.py` importa `polar_sessions` directamente;
- `analysis/session_analysis_pipeline.py` importa `hrv_sync_flow`, `polar_client`, `polar_oauth_local`, `polar_sessions` y `polar_utils` desde raiz;
- `tests/test_config_contract.py` depende de `importlib.reload(config)`;
- varios modulos candidatos al paquete interno importan hoy `config` desde raiz;
- smoke tests y contratos que importan modulos por su nombre actual en raiz;
- varios tests de contrato importan directamente `cli_reporting`, `dropbox_rr`, `hrv_sync_flow`, `intervals_sync`, `pipeline_runner`, `polar_client`, `polar_oauth_local`, `polar_sessions` y `sleep_store` desde raiz.

Resultado obligatorio de la fase 0:

- lista cerrada de imports a actualizar,
- decision explicita sobre si se ejecuta opcion A o opcion B,
- y decision de compatibilidad para cada modulo movido.
- decision explicita sobre `config.py` si se evalua la opcion B.
- decision explicita sobre el estilo de imports intra-paquete si se ejecuta la opcion B.

Artefacto obligatorio de salida:

- una nota dedicada, propuesta como `docs/HRV/ARQ-02 Inventario de imports y consumidores.md`
- esa nota debe quedar enlazada desde la tarea Kanvas correspondiente si la fase 0 se ejecuta como trabajo real.

Formato minimo del inventario:

- tabla o listado estructurado por consumidor con:
  - `consumidor`
  - `tipo` (`entrypoint`, `analysis`, `test`, `script manual`, `doc/subprocess`)
  - `import actual`
  - `destino previsto`
  - `accion` (`migrar a hrv_app.*`, `mantener en raiz`, `wrapper temporal`, `fuera de alcance`)
  - `riesgo`
- y una seccion final con:
  - `decision recomendada: opcion A / opcion B`
  - `motivo`

Si se ejecuta la opcion B, el inventario debe incluir tambien:

- mapa de imports cruzados entre modulos candidatos al paquete;
- y una decision de estilo:
  - imports relativos dentro de `hrv_app/`, o
  - imports absolutos `hrv_app.*`.

Recomendacion por defecto para opcion B:

- usar imports relativos dentro del paquete (`from .config import ...`);
- reservar `hrv_app.*` para entrypoints, `analysis/` y tests.

Regla importante:

- si se ejecuta la opcion B, el trabajo principal no es "hacer que pytest vea `hrv_app/`";
- el directorio raiz del repo ya permite resolver `import hrv_app.*` sin necesidad de `pytest.ini`, `conftest.py` o `pip install -e .` en el escenario actual;
- el trabajo real es migrar consumidores que hoy importan por nombre de modulo en raiz;
- lo mismo aplica al despliegue: el problema no es `PYTHONPATH`, sino dejar entrypoints de produccion apuntando a nombres legacy en raiz despues del movimiento.

Criterio de decision entre opcion A y opcion B:

- elegir **opcion A** si el inventario concluye que el valor buscado es principalmente visual/organizativo y que mover modulos internos obliga a tocar demasiados consumidores sensibles para el beneficio esperado;
- elegir **opcion B** solo si el inventario deja una lista cerrada, acotada y ejecutable de consumidores a migrar, con tratamiento explicito para `config.py`, `analysis/`, entrypoints productivos y tests.

Decision obligatoria sobre `config.py` en opcion B:

- no basta con declararlo "excepcion documentada" sin mas;
- la fase 0 debe escoger explicitamente una de estas rutas:
  1. mover `config.py` a `hrv_app/` y adaptar el contrato de tests para recargar `hrv_app.config`;
  2. dejar `config.py` en raiz y aceptar de forma explicita que `hrv_app/` dependa de un modulo externo al paquete, tratandolo como deuda tecnica;
  3. refactorizar `config.py` para eliminar su necesidad de `reload()` antes del movimiento.

Recomendacion por defecto:

- si se ejecuta la opcion B, la salida preferida es mover `config.py` a `hrv_app/` y adaptar `tests/test_config_contract.py` para que el contrato de recarga apunte al modulo real.

### Fase 1 — ejecutar opcion A si se busca mejora visual de bajo riesgo

- crear `scripts/python/`
- mover ahi scripts manuales
- actualizar docs y comandos manuales

Esta fase puede cerrarse por si sola si el objetivo es solo limpiar la raiz sin tocar imports internos.

### Fase 2 — introducir paquete interno solo si la auditoria lo aprueba

- crear paquete interno propuesto: `hrv_app/`
- mover modulos internos al paquete
- actualizar imports reales en consumidores y tests
- actualizar tambien los imports cruzados entre los propios modulos del paquete
- preservar en raiz solo los contratos que de verdad sigan siendo externos

Regla:

- no se consideran "seguros" los entrypoints por el mero hecho de quedarse en raiz;
- hay que auditar igualmente sus imports internos.
- los tests que hoy hacen `import hrv_sync_flow`, `import sleep_store`, etc., deben migrar a `import hrv_app.hrv_sync_flow as hrv_sync_flow`, `import hrv_app.sleep_store as sleep_store` o equivalente;
- `analysis/session_analysis_pipeline.py` y entrypoints como `build_sessions.py` deben migrar tambien a `hrv_app.*` si la opcion B se ejecuta.
- `web_ui.py` y `polar_hrv_automation.py` deben tratarse como consumidores de produccion de primera clase, porque Railway/Nixpacks arrancan con `python web_ui.py` y el flujo principal sigue encadenando subprocess desde entrypoints en raiz.
- dentro de `hrv_app/`, definir y aplicar un unico estilo de import para evitar una migracion a medias.

### Fase 3 — compatibilidad transitoria controlada

Si se necesitan wrappers temporales, su uso queda restringido:

- no usar wrappers `from hrv_app.modulo import *` como solucion general;
- no usarlos para `config.py`, porque el contrato de `reload()` puede romperse;
- preferir actualizar imports reales en consumidores internos;
- dejar wrappers solo para contratos externos documentados o subprocess legacy que no se puedan mover en esa misma tarea.

Caso especial:

- `config.py` no debe moverse con shim ciego mientras exista un contrato de `importlib.reload(config)` en tests y runtime;
- si se quiere mover, antes hay que redefinir explicitamente ese contrato;
- si no se mueve, debe quedar documentado que `hrv_app/` no es autonomo todavia y que depende de `config.py` en raiz como deuda tecnica consciente.

Criterio de salida para wrappers:

- cada wrapper debe tener owner y motivo de existencia;
- debe existir una lista cerrada de wrappers permitidos;
- si un wrapper ya no cubre ningun contrato externo o doc vigente, debe eliminarse en la misma tarea o quedar asignado a una subtarea posterior explicita.

## Riesgos

### 1. Romper imports en `analysis/`

`analysis/session_analysis_pipeline.py` ya demostro que depende de simbolos del flujo HRV. Mover modulos sin actualizar imports o sin wrappers de compatibilidad puede romper la coleccion de tests o el runtime.

### 2. Romper subprocess y comandos documentados

`web_ui.py` sigue ejecutando entrypoints por subprocess. Cualquier cambio de ruta debe preservar esos comandos o dejar wrappers finos en raiz.

### 3. Romper el despliegue

Railway, scripts `.bat` o notas operativas pueden seguir asumiendo ficheros en raiz.

### 4. Romper contratos de import por `reload()` o por entrypoints con imports internos

`config.py` no se puede tratar como cualquier modulo si el contrato de tests depende de `importlib.reload()`. Del mismo modo, `build_sessions.py` y otros entrypoints pueden importar modulos internos aunque se queden en raiz.

### 5. Confundir un problema de migracion de imports con un problema de `sys.path`

Si `hrv_app/` vive dentro de la raiz del repo, el problema principal no es que pytest "no vea" el paquete. El riesgo real es dejar consumidores internos y tests apuntando a nombres de modulo en raiz despues del movimiento.

### 6. Romper el arranque de produccion

Dockerfile, Nixpacks y Railway arrancan hoy con `python web_ui.py`. Si `web_ui.py` o `polar_hrv_automation.py` siguen importando modulos internos por nombre de raiz despues del movimiento, el despliegue rompera aunque el paquete interno exista.

### 7. Dejar `config.py` como excepcion difusa y romper la cohesion del paquete

Si la opcion B mueve modulos internos a `hrv_app/` pero mantiene `config.py` en raiz sin decision explicita, el paquete queda acoplado hacia fuera y deja de ser realmente autocontenido. Esa excepcion solo es aceptable como deuda tecnica documentada.

### 8. Sobrerrefactorizar

La tarea no debe convertirse en reorganizacion cosmetica total del repo. Solo debe atacar la separacion entre:

- entrypoints,
- modulos internos,
- y scripts auxiliares.

## Criterios de aceptacion

### Criterios base

Aplican tanto a la opcion A como a la opcion B:

1. Los scripts auxiliares/manuales que entren en alcance salen de la raiz a una carpeta especifica.
2. `web_ui.py`, `polar_hrv_automation.py`, `build_sessions.py`, `build_hrv_core.py`, `build_hrv_final_dashboard.py` y `egc_to_rr.py` siguen invocables con el mismo contrato operativo.
3. `analysis/` sigue importando y funcionando sin depender de rutas rotas.
4. La documentacion operativa se actualiza si cambia algun path de script manual o modulo relevante.
5. La suite de smoke/import y contratos del bloque `AYO-10` sigue verde.

### Criterios adicionales si se ejecuta la opcion B

6. La raiz queda reservada a entrypoints operativos canonicos y ficheros de infraestructura.
7. Los modulos internos del flujo HRV viven en un paquete propio coherente.
8. Existe inventario cerrado de imports actualizados y lista explicita de wrappers temporales permitidos.
9. Tests, `analysis/` y entrypoints internos ya importan `hrv_app.*` o una excepcion documentada, en vez de depender de nombres legacy en raiz.
10. El arranque de produccion (`python web_ui.py`) sigue siendo valido sin depender de cambios en `PYTHONPATH`.
11. `config.py` queda resuelto explicitamente: o vive en `hrv_app/` con contrato de tests actualizado, o permanece en raiz como excepcion documentada y deuda tecnica consciente.

## Regression gate minimo

### Gate base

Aplicable por defecto a opcion A, y como base minima tambien a opcion B:

- `python -m py_compile` de entrypoints y modulos tocados
- smoke de import:
  - `polar_hrv_automation.py`
  - `web_ui.py`
  - `build_sessions.py`
- `pytest` al menos sobre:
  - `tests/test_polar_hrv_automation_import.py`
  - `tests/test_config_contract.py`

### Gate adicional si se ejecuta la opcion B

- smoke de import:
  - `analysis/session_analysis_pipeline.py`
- `pytest tests/` completo

Motivo:

- la opcion B afecta imports y consumidores en buena parte de la suite;
- por tanto no basta con un subset critico si se mueven modulos internos a `hrv_app/`.

## Recomendacion de implementacion

No ejecutar esta tarea como simple movimiento de archivos.

Ruta recomendada segun opcion elegida:

### Si la fase 0 concluye opcion A

1. ejecutar la fase 0 de inventario,
2. dejar cerrada la decision de quedarse en opcion A,
3. mover scripts auxiliares a `scripts/python/`,
4. actualizar documentacion y comandos manuales afectados,
5. pasar el gate base.

### Si la fase 0 concluye opcion B

1. ejecutar la fase 0 de inventario,
2. dejar cerrada la decision de avanzar a opcion B,
3. resolver explicitamente `config.py`,
4. mover modulos internos actualizando imports reales en entrypoints, `analysis/` y tests,
5. actualizar tambien imports intra-paquete con el estilo decidido en Fase 0,
6. aplicar compatibilidad transitoria solo cuando haga falta, segun Fase 3,
7. mover scripts auxiliares a `scripts/python/`,
8. actualizar documentacion,
9. pasar el gate base y el gate adicional de opcion B,
10. cerrar o eliminar wrappers transitorios con criterio explicito.

## Relacion con ARQ-01

Esta tarea es continuacion natural de `ARQ-01`.

`ARQ-01` separa responsabilidades dentro del flujo HRV.
`ARQ-02` ordena fisicamente esos modulos en el arbol del repo para que la estructura refleje esa separacion.
