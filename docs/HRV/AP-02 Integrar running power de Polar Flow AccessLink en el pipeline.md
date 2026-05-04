# AP-02 Integrar senal mecanica de deportes de pie desde Polar Flow AccessLink en el pipeline

## Objetivo
Validar y, si la cobertura y calidad lo permiten, incorporar una capa minima de senal mecanica para deportes de pie (`road_run`, `trail_run`, `hike`) procedente de Polar Flow/AccessLink al pipeline de sesiones, para enriquecer futuras metricas sin depender solo de proxies por frecuencia cardiaca, ritmo o estructura de bloques.

## Motivacion
En el ecosistema actual del repo:

- `build_sessions.py` solo consume streams de `heartrate,velocity_smooth`
- `sessions.csv` no persiste running power ni otras senales mecanicas equivalentes para deportes de pie
- tareas como `AP-01`, `DO-01` y futuras extensiones de `FP-01` en carrera se apoyan en proxies estructurales o de HR

Sin embargo:

- el Polar Vantage M3 si calcula running power en muneca;
- Polar Flow web muestra graficas y distribucion de potencia para sesiones de running;
- y la API oficial Polar AccessLink documenta muestras de potencia (`Power W`), lo que hace plausible recuperar ese dato de forma programatica.

Ademas, para deportes de pie puede haber otras senales utiles a investigar:

- potencia
- running power
- GAP
- velocidad por mitades
- cadencia por mitades

## Valor esperado
Incorporar una capa mecanica real para deportes de pie aportaria una base mucho mejor para interpretar sostenimiento de output y densidad de intensidad.

Permitiria:

- enriquecer `AP-01` con una v2 menos binaria en carrera
- mejorar la lectura por deporte de `DO-01`
- abrir la puerta a proxies de durability mas validos en running y trail
- reducir dependencia exclusiva de HR o de categorias estructurales

## Preguntas que esta tarea debe resolver

1. Que senales mecanicas de deportes de pie expone realmente AccessLink en tus sesiones reales?
2. Con que cobertura historica aparecen en `road_run`, `trail_run` y `hike`?
3. En que forma llega cada una:
   - stream por muestra
   - resumen por sesion
   - distribucion por zonas
4. Que calidad y consistencia tiene respecto a las sesiones del Vantage M3?
5. Que subset minimo de columnas merece la pena canonizar en `sessions.csv`?

## Enfoque recomendado

### Fase 1. Validacion tecnica
Comprobar sobre sesiones reales de deportes de pie si AccessLink devuelve senal mecanica utilizable.

Minimo a validar:

- presencia de potencia o running power
- presencia de GAP si existe
- disponibilidad de velocidad y cadencia con suficiente resolucion para partir por mitades
- cobertura por deporte
- estabilidad de nombres/campos
- coherencia temporal con la sesion

### Fase 2. Diseno de columnas canonicas
Si la validacion es positiva, anadir una capa minima en `sessions.csv`.

Columnas candidatas:

- `run_power_mean`
- `run_power_max`
- `run_power_p95`
- `run_power_available`
- `gap_mean`
- `gap_p95`
- `gap_available`
- `speed_first_half`
- `speed_second_half`
- `speed_first_hour`
- `speed_last_hour`
- `cadence_first_half`
- `cadence_second_half`
- opcionalmente `power_zone_times` o equivalente si la API lo permite

La v1 debe ser conservadora:

- mejor pocas columnas estables que una capa rica poco fiable;
- priorizar las que tengan mejor cobertura y mejor semantica para `road_run` y `trail_run`.

### Fase 3. Consumo futuro
No mezclar esta tarea con una metrica concreta de entrada.

Consumidores futuros probables:

- `AP-01` v2 para clustering de intensidad en run
- `DO-01` para distribucion observada con una capa mecanica adicional
- una futura extension de `FP-01` en carrera

## Decision metodologica
No cerrar aun ninguna metrica nueva sobre senal mecanica hasta validar antes:

- disponibilidad real
- cobertura historica
- consistencia por deporte

La prioridad de esta tarea es **ingestion y canonizacion del dato**, no redisenar de golpe las metricas que luego lo consumiran.

## Criterios de aceptacion propuestos

- queda verificado que senales mecanicas expone o no AccessLink para tus sesiones reales de deportes de pie
- se documenta la cobertura observada en `road_run`, `trail_run` y `hike`
- si la cobertura es suficiente, `sessions.csv` incorpora columnas canonicas minimas de senal mecanica
- la documentacion deja claro el origen del dato y sus limites
- no se rompe el pipeline actual si el dato no esta disponible en algunas sesiones

## Limites conocidos de la V1

- `speed_first_half`, `speed_second_half`, `cadence_first_half` y `cadence_second_half` se calculan hoy partiendo la serie en su mitad cronologica y filtrando despues las muestras no utiles dentro de cada mitad. Esto evita el sesgo de partir por conteo de muestras validas, pero sigue sin ser un corte exacto por tiempo absoluto si la senal tiene huecos largos o muestreo irregular.
- el fallback Polar via AccessLink no debe tratarse como backfill historico completo. La cobertura real depende de la ventana reciente que exponga `/v3/exercises` en la transaccion activa.
- por tanto, para historico antiguo la via preferente de mecanica sigue siendo `Intervals FIT`, y Polar queda como fallback reciente.

## Decision recomendada
Abrir esta tarea como capa habilitadora independiente.

No debe bloquear por si sola `AP-01`, pero tampoco conviene ignorarla si el dato existe y es recuperable, porque podria evitar rehacer despues varias metricas de carrera y de sostenimiento mecanico.
