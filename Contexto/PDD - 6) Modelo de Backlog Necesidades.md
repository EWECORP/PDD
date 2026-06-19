A continuación se diseña el **Modelo de Backlog y Replanificación Automática** (formal, v1.0) para el nuevo esquema de transferencias, asegurando:

- que **nada se pierda** aunque Valkimia rechace o “no pueda”,
    
- que el sistema **se autorrecupere** ante faltantes de stock,
    
- que exista **priorización y fairness** entre sucursales,
    
- y que quede preparado para **cubicaje** en una etapa posterior.
    

---

# 1) Definición formal: qué es el Backlog

El **Backlog** es la suma de todas las necesidades (Need) que **no pudieron ser satisfechas** todavía, total o parcialmente.

Se define por línea (SKU–Sucursal–CD–Bucket):

backlog_qty = qty_need - qty_fulfilled

y puede estar compuesto por 3 “porciones”:

- **Pendiente por no planificar** (no hubo stock neto)
    
- **Pendiente por planificar parcialmente** (stock insuficiente)
    
- **Pendiente por ejecución fallida/rechazada** (Valkimia rechazó o no reservó)
    

---

# 2) Entidades y campos mínimos adicionales para backlog

Sobre lo ya definido, se agregan campos para controlar reintentos y prioridad.

## 2.1 TransferNeed (extensión)

Campos adicionales:

- `backlog_qty` _(derivado o materializado)_
    
- `last_planned_at`
    
- `last_published_at`
    
- `last_execution_status`
    
- `next_replan_at` (timestamp)
    
- `replan_attempts` (int)
    
- `max_replan_attempts` (int, default configurable)
    
- `priority_score` (num) — calculado
    
- `sla_due_at` (timestamp) — opcional
    
- `hold_reason` (nullable) — “congelada” por decisión operativa
    
- `need_version` (int) — para control de concurrencia (optimistic lock)
    

## 2.2 TransferPlanLine (extensión)

- `allocation_strategy` (enum: FIFO / PRIORITY / FAIR_SHARE / PROMO_BOOST)
    
- `stock_net_version` (string)
    
- `stock_net_snapshot_ts` (timestamp)
    

## 2.3 TransferExecutionLine (extensión)

- `reject_reason_code` (nullable)
    
- `reject_detail` (nullable)
    
- `last_event_id` (nullable)
    
- `retryable` (bool)
    

---

# 3) Estados formales de Backlog (vista de Need)

Se definen estados “operativos” del backlog (derivados del NeedStatus + Plan/Execution):

### BacklogState (derivado)

- `BL_OPEN` → existe backlog_qty > 0 y no está en hold
    
- `BL_WAITING_STOCK` → backlog_qty > 0 y último plan fue NO_STOCK
    
- `BL_WAITING_WINDOW` → no se replanifica antes de una fecha (next_replan_at futura)
    
- `BL_RETRYING` → está en ciclo de reintento
    
- `BL_HOLD` → congelada manualmente (hold_reason)
    
- `BL_CLOSED` → backlog_qty = 0 (Need fulfilled/cancelled)
    

Esto permite tableros y SLAs claros sin inventar nuevas tablas.

---

# 4) Motor de Replanificación — reglas y disparadores

## 4.1 Disparadores (Triggers) de replanificación

Se recomienda que la replanificación no sea “solo cron”, sino híbrida:

### Disparador A — Tiempo (cron)

- Cada X minutos/horas, por CD.
    
- Ej: cada 30 min para perecederos, cada 2h para secos.
    

### Disparador B — Evento de stock (preferible)

Cuando Valkimia informa:

- reposición de stock,
    
- liberación de ACO,
    
- ingreso de mercadería,  
    se dispara replanificación del subconjunto de SKUs afectados.
    

### Disparador C — Eventos de rechazo

Si una línea vuelve `EXEC_REJECTED_STOCK`, se agenda replanificación con “cooldown”.

---

## 4.2 Cooldown y backoff (evitar “thrashing”)

Para evitar que un SKU sin stock se intente publicar 200 veces:

**Regla de backoff exponencial:**

- intento 1 → replan en 30 min
    
- intento 2 → replan en 1 h
    
- intento 3 → replan en 2 h
    
- intento 4 → replan en 4 h
    
- tope → 24 h
    

Esto se implementa calculando `next_replan_at`.

---

# 5) Priorización formal (Priority Score)

El backlog debe ordenarse para asignar stock cuando aparece.

Se define un **Priority Score** calculado por Need:

Ejemplo conceptual:

priority_score =  
  w1 * prioridad_manual  
+ w2 * urgencia_sla  
+ w3 * venta_basal  
+ w4 * quiebre (stock tienda <= mínimo)  
+ w5 * promo_boost  
- w6 * penalidad_reintentos

### Componentes recomendados (prácticos)

1. **Prioridad manual** (0–100)
    
2. **SLA / due date** (más cerca = más score)
    
3. **Quiebre** (si tienda en riesgo)
    
4. **Promoción activa** (boost)
    
5. **Antigüedad del backlog** (FIFO parcial)
    
6. **Penalidad por reintentos** (para evitar loops)
    

**Resultado:** cuando hay stock, se asigna “primero” a lo más crítico.

---

# 6) Estrategias de asignación (Allocation Strategies)

Connexa debe soportar estrategias por familia o por CD:

### Estrategia 1 — PRIORITY (recomendada)

Asigna stock según `priority_score`.

### Estrategia 2 — FAIR_SHARE

Si hay poco stock y muchas sucursales:

- repartir proporcional (ej. mínimo 1 caja por tienda)
    
- luego completar por prioridad.
    

### Estrategia 3 — FIFO

Útil como fallback simple, pero suele ser injusta operativamente.

### Estrategia 4 — PROMO_BOOST

Prioriza sucursales con promoción activa.

**Recomendación:** PRIORITY + FAIR_SHARE como segundo paso.

---

# 7) Algoritmo formal de Planificación con backlog

## Entrada

- Backlog (Need) filtrado por:
    
    - `backlog_qty > 0`
        
    - `now >= next_replan_at`
        
    - `hold_reason is null`
        
- Stock neto Valkimia por SKU (SND)
    

## Salida

- TransferPlan (corrida)
    
- TransferPlanLines (qty_planned por SKU–Sucursal)
    

## Procedimiento (determinístico)

1. Agrupar backlog por SKU.
    
2. Para cada SKU, obtener `snd`.
    
3. Ordenar las Needs del SKU por `priority_score DESC`, luego antigüedad.
    
4. Asignar:
    
    - si snd = 0 → todas pasan a `BL_WAITING_STOCK`
        
    - si 0 < snd < total_backlog → asignación parcial
        
    - si snd ≥ total_backlog → asignación total
        
5. Generar PlanLines solo para qty_planned > 0.
    
6. Marcar Needs:
    
    - `qty_planned += qty_planned`
        
    - actualizar `last_planned_at`
        
    - set `next_replan_at` (si quedó backlog remanente)
        

---

# 8) Ciclo de vida ante rechazos Valkimia

### Caso: Valkimia rechaza por stock

Cuando ExecutionLine pasa a `EXEC_REJECTED_STOCK`:

Acción automática en Connexa:

1. Restar el “publicado” que no prosperó:
    
    - `qty_published -= qty_rejected`
        
2. Revertir al backlog:
    
    - `backlog_qty` vuelve a aumentar (o, si se deriva, queda implícito)
        
3. Incrementar:
    
    - `replan_attempts += 1`
        
4. Calcular:
    
    - `next_replan_at = now + backoff(replan_attempts)`
        
5. Estado backlog:
    
    - `BL_WAITING_STOCK`
        

**Regla:** nunca se pierde. Nunca se elimina.

---

# 9) Controles anti-duplicación (clave en transición)

Antes de publicar cualquier PlanLine:

**Check obligatorio:**

- ¿Existe ejecución activa en Valkimia para (CD, Sucursal, SKU) en estado no final?
    

Si sí:

- No publicar nueva
    
- O “absorber” la existente como ExternalExecution (modo transición)
    

Esto garantiza no duplicar aunque existan remanentes por SGM.

---

# 10) Tablero operativo de backlog (mínimo viable)

Se sugiere un tablero con:

### KPIs

- Backlog total unidades / kilos
    
- Backlog por CD
    
- Backlog por sucursal (Top 20)
    
- Backlog “en riesgo SLA”
    
- Rechazos por stock (últimas 24/72h)
    
- Tiempo medio en backlog (aging)
    

### Vistas

- Por SKU: “colas” de sucursales esperando
    
- Por sucursal: faltantes acumulados
    
- Por estado: waiting_stock / hold / retrying
    

Esto es lo que crea confianza operativa.

---

# 11) Parámetros configurables (para no hardcodear)

- `replan_frequency_minutes` por CD / familia
    
- `max_replan_attempts`
    
- `backoff_base_minutes`, `backoff_max_minutes`
    
- pesos de `priority_score` (w1..w6)
    
- estrategia por CD/familia: PRIORITY / FAIR_SHARE
    
- bucket de Need (diario / intradía / semanal)
    

---

# 12) Opinión final (y recomendación)

### Neutral

El modelo de backlog + replanificación propuesto:

- evita pérdidas por rechazo,
    
- crea un ciclo de vida controlado,
    
- habilita medición y mejora continua.
    

### Mi opinión técnica

El “salto” más importante no es publicar solo lo factible, sino **crear backlog real con estados auditables**.  
Eso transforma el proceso de “intentos sueltos” a un flujo industrializable.

---

# 13) Próximo entregable sugerido

Para cerrar la fase de diseño y pasar a implementación, el siguiente documento clave es:

1. **Especificación de reglas de cálculo del Priority Score** (con pesos iniciales por categoría)
    
2. **Pseudocódigo implementable** del planificador (para que desarrollo lo construya tal cual)
    
3. **Modelo de monitoreo y alertas** (qué se alerta y cuándo)
    

Si avanzan, en el próximo mensaje entrego el **pseudocódigo implementable** + una propuesta de **pesos iniciales** para `priority_score` por rubro/familia (perecederos vs secos vs non-food).