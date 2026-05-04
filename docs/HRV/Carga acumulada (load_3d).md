**Carga acumulada (load_3d > 200) es un predictor débil de ROJO**

El `load_3d` aparece frecuentemente en los `reason_text` pero los datos muestran muchos días VERDE con load_3d >200. Esto sugiere que el umbral de 200 es **demasiado bajo** para este atleta o que la carga por sí sola no es el factor determinante.

**Mejora:** Elevar el umbral de warning de `load_3d` a P75 del atleta (probablemente ~250-280) o hacerlo dinámico basado en el histórico.