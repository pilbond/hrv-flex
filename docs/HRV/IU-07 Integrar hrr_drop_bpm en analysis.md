## Objetivo

Aprovechar mejor una senal ya disponible antes de seguir creando metricas nuevas.

---

## Diagnostico

`hrr_drop_bpm` ya existe en la capa canonica de sesiones, pero su explotacion analitica sigue siendo secundaria.

Eso sugiere una oportunidad clara:

- bajo coste de integracion
- senal fisiologicamente interpretable
- posible valor para leer recuperacion post-esfuerzo o coste residual

---

## Alcance propuesto

- asegurar presencia clara en `summary` y `session_payload` cuando aplique
- definir si entra en tablas, narrativa o ambos
- evitar sobrerreaccionar si la cobertura es irregular por deporte o dispositivo

---

## Limites

- no convertirlo aun en decisor canonico
- no inventar umbrales fuertes sin backtest
- no desplazar a metricas mas robustas si no aporta realmente

---

## Criterios de aceptacion

1. La senal queda visible y trazable en `analysis`.
2. Existe una regla minima de uso narrativo coherente.
3. Se puede evaluar su utilidad sin tocar contratos globales.
