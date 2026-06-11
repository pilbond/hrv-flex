
Añadir una trazabilidad mínima y atomica a las salidas canonicas del pipeline HRV.

Objetivo:
- registrar version de algoritmo, configuracion efectiva y timestamp de corrida;
- guardar esa trazabilidad junto a `CORE`, `FINAL` y `DASHBOARD`;
- evitar que dos corridas iguales se vean como equivalentes cuando no lo son.

Diagnostico:
sesiones y SSM ya tienen metadata, pero el decisor HRV principal sigue sin un manifest equivalente. Eso complica reproducir una decision pasada y auditar cambios de configuración.

Alcance minimo:
- escribir un sidecar atomico para la corrida principal;
- incluir hash de parametros y version efectiva;
- dejar claro que esto no cambia el contenido del gate.

No objetivo:
- no añadir una capa de gobernanza pesada;
- no crear un ledger prospectivo exhaustivo;
- no meter metadata nueva como columnas del CSV.

Criterios de aceptacion:
1. Cada corrida principal deja un manifest verificable.
2. El manifest permite distinguir corridas con configuraciones distintas.
3. La escritura es atomica y no rompe el flujo actual.

Nota de desarrollo: este documento es la fuente unica de la tarea.
