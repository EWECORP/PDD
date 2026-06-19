**Plan de Migración Controlado** desde el esquema actual hacia el modelo objetivo, con enfoque en **continuidad operativa, reducción de riesgo y reversibilidad**.

Este documento puede considerarse:

> **Plan de Transición — Transferencias Connexa 1.0**

---

# 1️⃣ Objetivo del Plan de Migración

Migrar desde el esquema actual:

Connexa → DMZ → SGM → Valkimia  
SGM → Valkimia

Hacia el esquema objetivo:

Connexa (Need + Plan + Execution)  
      ↓  
   Valkimia

Sin:

- Interrumpir operación
    
- Generar duplicados
    
- Perder trazabilidad
    
- Alterar físicamente el circuito del CD en etapas iniciales
    

---

# 2️⃣ Principios de Migración

### P1 — No Big Bang

Se implementa en fases paralelas.

### P2 — Observabilidad primero

Primero se mide y reconcilia antes de bloquear.

### P3 — Reversibilidad

Cada etapa debe poder revertirse sin pérdida de datos.

### P4 — SGM sigue operando hasta etapa 3

No se corta publicación SGM hasta tener estabilidad.

---

# 3️⃣ Fases de Migración

---

# 🔷 FASE 0 — Diagnóstico y Línea Base (2–4 semanas)

## Objetivo

Entender volumen real, duplicaciones y estados inconsistentes.

### Acciones

1. Construir monitor:
    
    - Transferencias activas en Valkimia
        
    - Transferencias generadas por Connexa
        
    - Transferencias generadas por SGM
        
    - Duplicaciones SKU–Sucursal
        
2. Métricas base:
    
    - % duplicaciones
        
    - % eliminadas por Valkimia
        
    - Tiempo medio hasta despacho
        
    - Fill rate CD→Sucursal
        
3. No se cambia nada operativo.
    

### Entregable

Informe de situación real.

---

# 🔷 FASE 1 — Shadow Mode (Connexa como Observador)

## Objetivo

Crear el nuevo modelo sin afectar publicación actual.

### Qué se implementa

- Crear tablas:
    
    - TransferNeed
        
    - TransferPlan
        
    - TransferExecution
        
- Consumir:
    
    - Transferencias activas Valkimia
        
    - Transferencias generadas por Connexa y SGM
        
- Generar Needs “sombra”
    

### Qué NO se hace

- No se publica nada desde el nuevo modelo.
    
- No se bloquea SGM.
    

### Resultado

Connexa ya tiene:

- Backlog consolidado
    
- Estado real de ejecuciones
    
- Capacidad de simular planificación
    

---

# 🔷 FASE 2 — Planificación Controlada (Sin cortar SGM)

## Objetivo

Activar planificación basada en stock neto, pero manteniendo convivencia.

### Cambios

1. Connexa calcula Plan real.
    
2. Antes de publicar:
    
    - Consulta Valkimia para detectar ejecuciones activas.
        
    - Evita duplicar si ya existe una transferencia activa.
        
3. Publica solo:
    
    - SKU–Sucursal sin ejecución activa.
        

### Resultado

- Se reduce duplicación.
    
- Se evita publicar sobre líneas ya en proceso.
    
- SGM aún puede publicar, pero Connexa no pisa.
    

---

# 🔷 FASE 3 — Publicador Único (Corte Controlado)

## Objetivo

Connexa se convierte en único publicador.

### Acciones

1. Bloquear en SGM:
    
    - Publicación directa a Valkimia.
        
    - Reemplazar por envío de Need hacia Connexa.
        
2. Mantener reconciliación automática:
    
    - Si SGM todavía generara alguna, Connexa la absorbe.
        
3. Activar:
    
    - Replanificación automática de rechazadas.
        

### Resultado

- Se elimina origen dual.
    
- Se estabiliza arquitectura.
    

---

# 🔷 FASE 4 — Optimización y Cubicaje

Solo cuando:

- 100% publicación centralizada.
    
- Estados consistentes.
    
- Backlog limpio.
    

Se activa:

- Consolidación por viaje.
    
- Simulación capacidad camión.
    
- Agrupación inteligente.
    

---

# 4️⃣ Gestión de Riesgos

## Riesgo 1 — Duplicaciones durante transición

Mitigación:

- Chequeo obligatorio antes de publicar:
    
    Existe ejecución activa SKU–Sucursal?
    
- Si sí → no publicar.
    

---

## Riesgo 2 — Stock inconsistente

Mitigación:

- Usar stock neto con timestamp y versión.
    
- No usar stock bruto.
    

---

## Riesgo 3 — Rechazos masivos por stock

Mitigación:

- Activar modo “PlanPartialOnly”
    
- Publicar solo si SND > 0.
    

---

## Riesgo 4 — Falta de confianza de operación

Mitigación:

- Panel de control visible:
    
    - Backlog
        
    - Publicadas
        
    - Rechazadas
        
    - En picking
        
    - Despachadas
        

---

# 5️⃣ Plan Técnico de Implementación

## Sprint 1

- Crear esquema nuevo en PostgreSQL.
    
- Construir job de ingesta desde Valkimia.
    
- Crear tabla de reconciliación.
    

## Sprint 2

- Implementar consolidación Need.
    
- Implementar simulador de Plan.
    
- Validar contra datos históricos.
    

## Sprint 3

- Implementar publicación idempotente.
    
- Activar Shadow Publish Mode.
    

## Sprint 4

- Activar modo “Connexa Publicador Primario”.
    
- Deshabilitar publicación directa SGM.
    

---

# 6️⃣ Métricas de Éxito por Fase

|Fase|Métrica|
|---|---|
|0|% duplicación identificado|
|1|100% trazabilidad en Connexa|
|2|Reducción >70% duplicaciones|
|3|0 publicaciones directas SGM|
|4|+X% mejora ocupación camión|

---

# 7️⃣ Plan de Rollback

En cada fase:

- Publicación Connexa puede desactivarse.
    
- SGM puede reactivarse como publicador.
    
- Las tablas nuevas no afectan sistema actual.
    

---

# 8️⃣ Duración Estimada Realista

|Fase|Duración|
|---|---|
|0|3 semanas|
|1|4 semanas|
|2|4 semanas|
|3|3 semanas|
|4|posterior|

Total: ~3 a 4 meses controlados.

---

# 9️⃣ Evaluación Estratégica

### Versión Neutral

Este plan reduce riesgo operativo y permite migración progresiva sin interrumpir CD.

### Opinión Técnica

Si intentan saltar directamente a “Connexa único publicador” sin Shadow Mode, el riesgo operativo es alto.

El valor real está en:

> Medir primero → Controlar después → Optimizar al final.

---

# 1️⃣0️⃣ Próximo Paso Recomendado

Ahora hay dos caminos posibles:

1. Diseñar el **Modelo de Backlog y Replanificación Automática**
    
2. Diseñar el **Tablero Ejecutivo de Control de Transferencias** para Dirección
    

Desde mi punto de vista, el siguiente paso lógico es:

👉 Diseñar el modelo de backlog y replanificación automática, porque es el corazón operativo del nuevo esquema.