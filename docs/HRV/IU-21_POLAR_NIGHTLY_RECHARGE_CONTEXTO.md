# IU-21 · Nightly Recharge en el contexto de recuperación

Propuesta de desarrollo del 6 de noviembre de 2026. Autor, Codex.

Tarea vinculada en `kanvas.json`, **IU-21**. Estado inicial `proposed`, pendiente de aprobación humana.

## Objetivo

Incorporar las valoraciones de recuperación nocturna de Polar AccessLink v4 a la persistencia de sueño y al contexto explicativo del brief diario. Hacer que la narrativa distinga duración e interrupciones, carga de sueño relativa al nivel habitual y carga autonómica nocturna.

## Caso que motiva el cambio

El brief diario del 2026-11-06 indicó discordancia entre recuperación nocturna y HRV matinal. El snapshot de producción recuperado desde Dropbox contiene `recovery_support_class=conflicted`, con `sleep_basic_ok` como código de discordancia.

- Duración de 449,5 minutos frente a P10 de 356,15 minutos.
- Siete interrupciones largas frente a P90 de 7,6.
- Sleep score de 68,6139, neutro para los umbrales absolutos actuales de 65 y 75.
- RMSSD nocturno de 32 ms, neutro para los umbrales absolutos actuales de 30 y 40 ms.
- RMSSD matinal de 26,46 ms, caída aproximada del 35 % frente a la base y veto agudo activo.

El usuario observó Nightly Recharge muy malo en Polar Flow, con valoración desfavorable de sueño y SNA. Esa valoración procede de su comunicación. Queda pendiente contrastarla con la respuesta original de su cuenta para esa fecha.

La regla actual convierte la ausencia de alertas de duración e interrupciones en apoyo favorable. Un rojo con apoyo y sin cautelas se etiqueta como discordante. Los percentiles de sueño se calculan sobre el histórico disponible, mientras Polar ofrece valoraciones relativas a su propia referencia personal.

## Disponibilidad y situación actual

La app ya consulta sueño y Nightly Recharge mediante `hrv_app/polar_gateway.py`. El adaptador `v4_nightly_to_internal` conserva RMSSD, RRI y respiración, pero omite las valoraciones y referencias personales de Polar.

| Dato documentado en v4 | Uso propuesto |
| --- | --- |
| `recoveryIndicator` | Valoración global de recuperación, escala 1–6 |
| `recoveryIndicatorSubLevel` | Detalle dentro de la categoría, opcional para trazabilidad |
| `ansStatus`, `ansRate` | Valor y clasificación del componente autonómico |
| `sleepScore.scoreRate` | Valoración de la puntuación de sueño frente al nivel habitual, escala 1–5 |
| `meanBaselineRmssd`, `sdBaselineRmssd` | Referencia personal del RMSSD nocturno |
| `meanBaselineRri`, `sdBaselineRri` | Referencia personal del intervalo entre latidos |
| `meanBaselineRespirationInterval`, `sdBaselineRespirationInterval` | Referencia personal del intervalo respiratorio |

Verificar las unidades y la correspondencia de códigos con etiquetas antes de implementar, especialmente `ansStatus` y `ansRate`, cuya descripción pública es limitada. Documentar qué campos son opcionales y cómo se representan ausencias.

La documentación incluye `hrvSamples` y `breathingRateSamples`. Su cobertura temporal real requiere inspección. La comparación entre inicio y final de la noche queda como posible ampliación posterior, condicionada a cobertura y calidad verificadas.

## Desarrollo previsto

1. Consultar de forma segura los payloads v4 de sueño y Nightly Recharge del 2026-11-06 y otras fechas contrastables. Registrar valores relevantes y procedencia, evitando credenciales. Si se necesita conservar una auditoría exploratoria, seguir `research/AGENTS.md` y su estructura.
2. Definir los campos adicionales de `ENDURANCE_HRV_sleep.csv`, sus tipos, unidades, valores permitidos y tratamiento de ausencias. Priorizar las tres valoraciones y las referencias personales necesarias para explicarlas. Preservar valores numéricos de origen para trazabilidad.
3. Extender adaptadores y `sleep_store` reutilizando el flujo de consulta y escritura atómica. Admitir CSV históricos de 17 columnas, añadiendo campos vacíos hasta que exista dato de Polar. Una respuesta parcial no debe borrar valores válidos ya persistidos. Mantener explícitos los resultados de consulta pendiente y error.
4. Revisar en `build_hrv_final_dashboard.py` la clasificación del contexto de recuperación. `sleep_basic_ok` debe expresar ausencia de alerta básica. Para declarar apoyo favorable o discordancia se necesitará evidencia positiva explícita. Definir una tabla de decisión para valoraciones favorables, desfavorables, mixtas y ausentes, con precedencia clara y sin contar varias veces componentes correlacionados del mismo índice.
5. Incorporar al payload y al snapshot del brief diario las valoraciones de Polar, su fecha y los motivos de la clasificación. Ajustar instrucciones y fallback determinista para nombrar la señal concreta. Evitar que una etiqueta general de recuperación oculte qué componente resulta favorable o desfavorable.
6. Revisar el consumo de sueño por el SSM y sus briefs para asegurar compatibilidad con el esquema ampliado. La adopción de nuevas observaciones o pesos en el modelo exige validación propia y una decisión de alcance explícita.
7. Actualizar `docs/contracts/` por los cambios de esquema y significado del contexto. Actualizar el recuento de columnas y la descripción operativa en `AGENTS.MD` cuando se implemente. Verificar backup, restore, manifiestos y lectores del CSV ampliado.
8. Preparar recuperación histórica por fechas y publicación de manera revisable, con copia previa y comprobación de resultados. Registrar el alcance real de la recuperación que permita Polar. Conservar los briefs originales como evidencia de lo que se publicó.

El alcance funcional propuesto es el contexto de recuperación y su explicación. Una modificación de los criterios que determinan el gate HRV requiere una decisión contractual específica.

## Criterios de aceptación

- Los campos recibidos de Polar llegan a la persistencia y al payload del brief con fecha, unidades y etiquetas verificadas.
- El caso del 6 de noviembre reproduce los valores observados en Flow cuando estén disponibles en la API. Si falta una valoración, la app expresa esa ausencia y conserva el resto de señales válidas.
- Un gate rojo acompañado de valoraciones nocturnas desfavorables produce una explicación coherente. La ausencia de alertas de duración e interrupciones por sí sola deja de generar una discordancia favorable.
- Una noche realmente favorable junto a HRV matinal desfavorable puede describirse como señal mixta, identificando el componente que la sustenta.
- Se prueban CSV históricos, campos opcionales, códigos desconocidos, respuestas parciales y reintentos de sincronización.
- Se verifican el fallback determinista y el contrato del brief IA, incluida su trazabilidad. Los números narrados deben proceder de campos o cálculos autorizados.
- Una comparación antes/después en un directorio aislado documenta el efecto sobre contexto, textos y esquemas, y verifica la estabilidad del gate bajo el alcance propuesto.
- Los contratos y la documentación operativa reflejan el resultado implementado.

## Fuentes y archivos de referencia

- [Documentación oficial de Polar AccessLink v4](https://www.polar.com/polar-api-v4/).
- [Documento técnico de Nightly Recharge](https://www.polar.com/img/static/whitepapers/pdf/polar-nightly-recharge-white-paper.pdf). El componente SNA utiliza cuatro horas desde 30 minutos después del inicio del sueño. La carga de sueño considera el resultado de sueño de la noche.
- `hrv_app/polar_adapters_v4.py`, `hrv_app/polar_gateway.py`, `hrv_app/sleep_store.py`.
- `build_hrv_final_dashboard.py`, `hrv_app/ai/daily_brief.py`, `build_hrv_ssm.py`.
- Evidencia local privada del incidente en `data/ai_briefs/daily/ENDURANCE_HRV_ai_daily_brief_2026-11-06.json`. Mantener los archivos personales fuera de Git.
