# Endurance HRV — Columnas de semáforo (Opción A) y orden recomendado del master

Algoritmo: v3.x (Opción A)
Revisión del documento: r2025-12-21-UPDATE2 (21-dic-2025)

Alcance y jerarquía:
- Este documento define **contrato de datos** (columnas, orden y significado operativo de cada campo).
- No redefine lógica de cálculo: para fórmulas/umbrales manda `ENDURANCE_HRV_Spec_Tecnica_Implementacion`.
- Para interpretación de las salidas (sin alterar cálculos) manda `ENDURANCE_HRV_Diccionario`.

---

## 1) Opción A (acordada): 3 señales + desempate (se consulta solo si hay conflicto; se almacena siempre)

En Opción A no se pretende tener 5 columnas de color compitiendo, sino:

1) **Gate de fiabilidad técnica** (no es "color", pero manda):
   - `Calidad` (OK / FLAG_mecánico / INVALID)
   - `HRV_Stability` (OK / Unstable)
   - Definición de “día válido” para ventanas (14/30/90): `Calidad != INVALID` (incluye `FLAG_mecánico`; `HRV_Stability=Unstable` permitido).

2) **Estado agudo (hoy)**:
   - **Color_Agudo_Diario** (z-scores robustos) → decide "hoy puedo o no puedo"
   - Terminología: es el **semáforo principal del día** (operativo).

3) **Contexto/tendencia (último mes)**:
   - **Color_Tendencia** (percentiles P15/P30 sobre cRMSSD) → freno de fondo
   - Terminología: es el **semáforo de fondo**; puede frenar aunque el agudo esté verde.

4) **Desempate**:
   - **Color_Tiebreak** se calcula y se guarda siempre; se consulta solo para resolver conflicto entre (2) y (3), o para "rojo agudo" que parece arrastrado por HR.

---

## 2) Columnas de color que SÍ se guardan (solo 3)

Para cumplir "solo 3 columnas de colores", guardar únicamente:

1) **Color_Tendencia**  
   - Semáforo de fondo por percentiles (P15/P30) de **cRMSSD** y modulación por `HR_z14`.

2) **Color_Agudo_Diario**  
   - Semáforo agudo por z-score robusto (28d) de **lnRMSSD** + freno por `HR_z14`.

3) **Color_Tiebreak**  
   - Versión de Color_Agudo_Diario usando **ln(cRMSSD)** en lugar de **lnRMSSD**.
   - Sirve para detectar si un rojo/verde es real o artefacto de cambios en HR.
   - **Uso**: desempate (se consulta solo si hay conflicto). Se calcula y se guarda siempre.

> **Nota técnica sobre P1/P2:**  
> El sistema calcula dos políticas de umbral (P1 estricta, P2 permisiva).  
> Solo P2 se usa en decisión diaria y se guarda en el master con nombres amigables:
> - P2 → `Color_Agudo_Diario`
> - P2 corregido → `Color_Tiebreak`
> 
> P1 (estricto) solo se calcula en datasets de evaluación opcionales.
> Más detalles en la Especificación Técnica, sección 8.

> Nota adicional: P1 y P1_lncRMSSD **no se guardan** en el master, salvo que quieras un archivo "FULL-EVAL" aparte.

---

## 3) ¿Qué pasa con el Gate? (Calidad/HRV_Stability)

**No es un color**, pero es el filtro que evita autoengaño:
- Si `Calidad=INVALID` → no usar HRV para decidir (día Indef).
- Si `Calidad=FLAG_mecánico` o `HRV_Stability=Unstable` → dato usable con prudencia; evitar intensidad.

Esto debe estar visible al inicio del master, aunque no sea "columna de color".

---

## 4) Orden recomendado del master (para lectura fácil)

Sin quitar columnas, pero agrupando.  
Las columnas de **color van juntas al final**, como pediste.

### A) Identidad / trazabilidad
1. `Fecha`
2. *(opcional)* `Fuente` / `Archivo` (si lo mantienes)

### B) Gate (leer primero)
3. `Calidad`
4. `HRV_Stability`
5. `Artifact_pct`
6. `Tiempo_Estabilizacion`

### C) Núcleo fisiológico
7. `HR_stable`
8. `RRbar_s`
9. `RMSSD_stable`
10. `RMSSD_stable_last2`
11. `lnRMSSD`
12. `cRMSSD`

### D) Auditoría β (explica cRMSSD)
13. `beta_est_90d`
14. `beta_use_90d`
15. `beta_mode`
16. `RR_ref_90d`
17. `N90_valid`
18. `IQR_RRbar_90d`
19. `R2_winsor_90d`
20. `ln_corr`

### E) Ventana/umbrales del semáforo principal
21. `Nprev30`
22. `P15_cRMSSD_30d`
23. `P30_cRMSSD_30d`
24. `HR_z14`

### F) Semáforos (solo 3 columnas, juntas al final)
25. `Color_Tendencia`
26. `Color_Agudo_Diario`
27. `Color_Tiebreak`

### G) Anotaciones (recomendado)
28. `Flags`
29. `Notes`

**Notas sobre formato (para evitar deriva):**
- `Flags`: vocabulario cerrado, valores separados por `|` (sin espacios).
- `Notes`: string determinista `clave=valor` separado por `; `, con claves mínimas (src + duraciones + conteos + desglose artefactos). Ver detalle en `ENDURANCE_HRV_Spec_Tecnica_Implementacion` y `ENDURANCE_HRV_Diccionario`.

---

## 5) QA mínimo que debe acompañar cada recalculado (resumen)

### QA unidades (anti-bugs)
- Comprobar: `HR_stable ≈ 60 / RRbar_s` (error relativo <= 0.1%).
- RRbar_s típico 0.8–1.6 s; HR supina típica 45–60 lpm.

### QA señal / mecánica
- % `INVALID`, % `FLAG_mecánico`, % `HRV_Stability=Unstable`
- Top 20 `Artifact_pct` y top 20 `Tiempo_Estabilizacion`

### QA β (si usas cRMSSD)
- clip_rate (β capado arriba) y distribución de `|ln_corr|`
- corr( ln(cRMSSD), ln(RRbar_s) ) en 60–90d cerca de 0
- Top 10 días por `|ln_corr|`

### Plantilla fija de informes QA (obligatorio, anti-deriva)
- QA_global (MD) debe seguir SIEMPRE esta estructura:
  0) Cobertura · 1) Calidad · 2) INVALID · 3) FLAG_mecánico · 4) Sanity checks · 5) Flags (conteos) · 6) Top outliers · 7) Resumen β
- QA_beta (MD) debe seguir SIEMPRE esta estructura:
  0) Cobertura · 1) beta_mode · 2) Calidad 90d · 3) |ln_corr| · 4) Top 10 |ln_corr| · 5) Incidencias none/frozen
- Si una sección no aplica en un rango → incluirla igualmente con el texto “Sin incidencias / no aplica”.
---

## 6) Resultado práctico (cómo se usa cada día — Opción A)

1) Mirar `Calidad/HRV_Stability` (y, si procede, `Flags/Notes` para el motivo):
   - INVALID → no decidir por HRV (día Indef).
   - FLAG/Unstable → prudencia; no justificar intensidad.

2) Mirar **Color_Agudo_Diario** (agudo) y **Color_Tendencia** (tendencia):
   - Si van alineados → decisión fácil.
   - Si chocan → usar **Color_Tiebreak** como desempate.

Fin del documento.
