
Añadir una trazabilidad mínima y atomica a las corridas canónicas del pipeline HRV.

Objetivo:
- registrar version de algoritmo, configuracion efectiva y timestamp de corrida;
- guardar esa trazabilidad como sidecars atomicos de `CORE` y de `FINAL/DASHBOARD`;
- evitar que dos corridas iguales se vean como equivalentes cuando no lo son.

Diagnostico:
sesiones y SSM ya tienen metadata, pero el procesado HRV principal seguia sin manifests equivalentes por etapa. Eso complicaba reproducir una decision pasada y auditar cambios de configuración.

Alcance minimo:
- escribir sidecars atomicos para la corrida de medicion (`CORE/BETA_AUDIT`) y para la corrida de decision (`FINAL/DASHBOARD`);
- incluir hash de parametros y version efectiva;
- dejar claro que esto no cambia el contenido del gate.

Nota operativa:
- el manifest de entrada de `CORE` hashea cada RR procesado; en el flujo normal con `--rr-file` el coste es bajo, pero una ejecucion masiva con `--rr-dir` sobre mucho historico puede añadir latencia.

No objetivo:
- no añadir una capa de gobernanza pesada;
- no crear un ledger prospectivo exhaustivo;
- no meter metadata nueva como columnas del CSV.

Criterios de aceptacion:
1. Cada corrida deja un manifest verificable por etapa.
2. El manifest permite distinguir corridas con configuraciones distintas.
3. La escritura es atomica y no rompe el flujo actual.

Nota de desarrollo: este documento es la fuente unica de la tarea.
