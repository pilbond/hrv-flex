# 🎯 Procedimiento Recomendado y Días Sin Sesión

## ✅ Mejor Procedimiento: Modo Automático

### Comando Diario Recomendado
```bash
python polar_hrv_final.py --process
```

### ¿Por qué este es el mejor?

1. **Inteligente:** Lee última fecha del master CSV
2. **Eficiente:** Solo descarga días faltantes
3. **Automático:** Detecta y procesa todo solo
4. **Seguro:** Limita a 30 días para evitar descargas masivas
5. **Sin duplicados:** No re-descarga lo que ya tienes

### Flujo Automático

```
┌─────────────────────────────────────────────────────┐
│ python polar_hrv_final.py --process                 │
└─────────────────────────────────────────────────────┘
              │
              ▼
     ┌────────────────────┐
     │ Leer Master CSV    │
     │ Última fecha: 16   │
     └────────────────────┘
              │
              ▼
     ┌────────────────────┐
     │ Calcular faltantes │
     │ Hoy: 19            │
     │ Faltan: 3 días     │
     └────────────────────┘
              │
              ▼
     ┌────────────────────┐
     │ Descargar 17,18,19 │
     └────────────────────┘
              │
              ▼
     ┌────────────────────┐
     │ Procesar con       │
     │ endurance_hrv.py   │
     └────────────────────┘
              │
              ▼
     ┌────────────────────┐
     │ Master actualizado │
     │ hasta 19           │
     └────────────────────┘
```

## 📅 Días Sin Sesión: Completamente Normal

### ¿Qué pasa si falté un día?

**Ejemplo:**
- 15 ene: ✅ Sesión grabada
- 16 ene: ❌ No hice sesión (descansé)
- 17 ene: ✅ Sesión grabada
- 18 ene: ✅ Sesión grabada

**Resultado:**
```bash
python polar_hrv_final.py --process

📅 Última medición: 2026-01-15
   Faltan 3 días hasta hoy

🔍 Obteniendo ejercicios...
✅ 2 sesiones tras filtros

📥 Descargando datos RR...
  [0] ✅ Franz_Dunn_2026-01-17_09-23-30_RR.CSV
  [1] ✅ Franz_Dunn_2026-01-18_08-58-55_RR.CSV

📊 2 archivos CSV descargados
```

**¿Qué pasó con el día 16?**
- ✅ El script lo buscó en Polar
- ✅ No encontró sesión Body&Mind ese día
- ✅ Siguió con los demás días
- ✅ Todo normal, no es un error

### Master CSV con días faltantes

Tu master quedará así:

```csv
Fecha,RMSSD,...
2026-01-15,45.3,...
2026-01-17,43.1,...
2026-01-18,44.7,...
```

**Nota:** El día 16 simplemente NO está. Esto es correcto y esperado.

### ¿Cuándo SÍ es un problema?

❌ **Problema real:** Sesión grabada pero no aparece
- Causa: No sincronizó con Polar Flow
- Solución: Abre app Polar, fuerza sincronización, reintenta

❌ **Problema real:** Master no se actualiza
- Causa: Error en endurance_hrv.py
- Solución: Revisa errores en output

✅ **NO es problema:** Días sin sesión por:
- Descanso programado
- Olvido de grabar
- Viaje / enfermedad
- Cualquier razón personal

## 🔄 Workflow Diario Ideal

### Setup Inicial (Una vez)
```bash
# 1. Primera autenticación
python polar_hrv_final.py --auth

# 2. Primera descarga (últimos 30 días)
python polar_hrv_final.py --days 30 --process
```

### Uso Diario (Cada mañana)
```bash
# Simplemente esto
python polar_hrv_final.py --process
```

**Qué hace:**
1. Lee última fecha del master
2. Descarga solo días nuevos
3. Procesa automáticamente
4. Master actualizado
5. App Vue muestra nuevos datos

### Si te atrasaste varios días
```bash
# Sin problemas, el modo auto se encarga
python polar_hrv_final.py --process

# Output:
📅 Última medición: 2026-01-10
   Faltan 9 días hasta hoy
   Descargando 9 días faltantes
```

### Si te atrasaste más de 30 días
```bash
# El script te avisará
📅 Última medición: 2025-12-01
   Faltan 49 días (>30)
   Limitando a últimos 30 días
   Usa --all para descargar todo

# Para descargar todo:
python polar_hrv_final.py --all --process
```

## 🎯 Casos de Uso

### Caso 1: Uso diario normal
```bash
# Cada mañana después de tu sesión HRV
python polar_hrv_final.py --process
```

### Caso 2: Olvidé sincronizar 3 días
```bash
# Mismo comando, detecta automáticamente
python polar_hrv_final.py --process
```

### Caso 3: Estuve de viaje 2 semanas
```bash
# Mismo comando, descarga todo lo faltante
python polar_hrv_final.py --process
```

### Caso 4: Setup inicial / rehacer todo
```bash
# Descargar todas las sesiones históricas
python polar_hrv_final.py --all --process
```

### Caso 5: Solo quiero ver qué hay sin procesar
```bash
# Solo descarga, no procesa
python polar_hrv_final.py --auto
```

### Caso 6: Master está actualizado
```bash
python polar_hrv_final.py --process

# Output:
✅ Master actualizado hasta hoy (2026-01-19)
   No hay nada que descargar
```

## 📊 Visualización en App Vue

La app Vue **no necesita días consecutivos**. Funciona perfectamente con:

```
Master CSV:
2026-01-15 ✓
2026-01-16 -  (sin sesión)
2026-01-17 ✓
2026-01-18 ✓
2026-01-19 -  (sin sesión)
2026-01-20 ✓

Gráfico:
        •
    •       •
•               •

        (gaps son normales)
```

## ✨ Resumen

### ✅ Hacer
- Ejecutar `python polar_hrv_final.py --process` cada día
- Dejar que el modo auto maneje las fechas
- Ignorar días sin sesión (es normal)

### ❌ No hacer
- Preocuparse por días sin sesión
- Calcular manualmente qué días descargar
- Re-descargar todo cada vez
- Usar `--days` manualmente a menos que sea necesario

### 🎯 Comando único para todo
```bash
python polar_hrv_final.py --process
```

Eso es todo. El script se encarga del resto. 🚀
