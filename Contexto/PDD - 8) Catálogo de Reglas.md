A continuación se entrega el **Catálogo de Reglas (Matriz)** listo para documentar en Confluence como anexo normativo del rediseño. Está pensado para **no dejar lugar a interpretaciones** durante implementación.

---

# Catálogo de Reglas — Transferencias (v1.0)

## 0) Convenciones y definiciones

### 0.1 Clave funcional de Need

Una necesidad consolidada se identifica por:

**(cd_id, sucursal_id, sku_id, need_bucket_date)**

### 0.2 Definición de “ejecución activa” (para anti-duplicación)

Una ejecución en Valkimia se considera **activa** si su estado ∈:

- `ACEPTADA`
    
- `RESERVADA_ACO`
    
- `EN_PREPARACION / PICKING`
    
- `DESPACHADA` _(hasta confirmar recepción si aplica)_
    
- `EN_TRANSITO` _(si existe)_
    

No activa si:

- `ENTREGADA/RECIBIDA`
    
- `CANCELADA`
    
- `RECHAZADA_POR_STOCK`
    
- `FALLIDA`
    

---

# 1) Reglas de Bucket (need_bucket_date)

## R-BKT-01 — Bucket diario (default)

- `need_bucket_date = fecha local (America/Argentina/Buenos_Aires)` truncada a día.
    

**Aplicación recomendada:** Secos y Non-Food.

## R-BKT-02 — Bucket intradía (opcional)

- Permite 2 buckets: AM/PM o ventanas (ej. 08:00–14:00 / 14:00–20:00)
    

**Aplicación recomendada:** Perecederos y urgencias operativas.

## R-BKT-03 — Reglas de merge

Si llega una Need con la misma clave funcional:

- Se ejecuta **MERGE**:
    
    - `qty_need = qty_need + qty_incoming` _(modo incremental)_  
        **o**
        
    - `qty_need = max(qty_need, qty_incoming)` _(modo recalculado)_
        

**Regla de decisión:**

- Si el origen es Forecast (recalcula) → usar `max/reemplazo`
    
- Si el origen es “event-driven” (ajustes, quiebres) → usar `suma`
    

---

# 2) Reglas de Cálculo de Componentes de Priority Score

Se define un score total:

`priority_score = Σ(componentes ponderados)`

Los componentes se normalizan a [0..1] salvo `manual_priority` (0..100).

---

## R-PRS-01 — manual_priority

- Input: entero 0..100.
    
- Default:
    
    - Connexa forecast → 50
        
    - SGM need → 60 (por urgencia operativa)
        
    - Manual → valor ingresado
        

Normalización (si se requiere):

- `manual_priority_norm = manual_priority / 100.0`
    

---

## R-PRS-02 — sla_urgency (0..1)

Si `sla_due_at` es null → `sla_urgency = 0`

Caso contrario:

- `hours_left = (sla_due_at - now)` en horas
    
- `sla_urgency = clamp( 1 - (hours_left / SLA_WINDOW_HOURS), 0, 1 )`
    

**Parámetros por familia (SLA_WINDOW_HOURS):**

- Perecederos: 12
    
- Secos: 72
    
- Non-Food: 168
    

Interpretación: si falta poco para el vencimiento, urgencia crece.

---

## R-PRS-03 — break_risk (0..1)

Se define con stock tienda y mínimo.

- Si no hay stock tienda: `break_risk = 0` (modo degradado)
    
- Caso contrario:
    
    - `break_risk = 1` si `stock_store <= stock_min_store`
        
    - `break_risk = 0` si `stock_store > stock_min_store`
        

**Extensión opcional (gradual):**

- `break_risk = clamp((stock_min_store - stock_store)/stock_min_store, 0, 1)`
    

---

## R-PRS-04 — sales_rate_norm (0..1)

`sales_rate` sugerida: venta promedio diaria 30d.

Normalización **por familia y CD**:

- Calcular `p95_sales_rate` por familia/CD en ventana 30d
    
- `sales_rate_norm = clamp(sales_rate / p95_sales_rate, 0, 1)`
    

Si no hay p95:

- fallback: min-max global de familia
    
- o `sales_rate_norm = 0.5` (degradado)
    

---

## R-PRS-05 — promo_boost (0 o 1)

- `promo_boost = 1` si `promo_active = true`
    
- caso contrario 0
    

**Opcional:** intensidad 0..1 si existe `promo_factor`.

---

## R-PRS-06 — backlog_age_norm (0..1)

`age_hours = now - created_at`

Normalización por familia:

- Perecederos: `AGE_MAX = 12h`
    
- Secos: `AGE_MAX = 96h`
    
- Non-Food: `AGE_MAX = 168h`
    

`backlog_age_norm = clamp(age_hours / AGE_MAX, 0, 1)`

---

## R-PRS-07 — retry_penalty

- `retry_penalty = replan_attempts` (lineal)
    
- o `retry_penalty = log(1 + replan_attempts)` (suavizado)
    

Recomendación: **log** para no castigar de más.

---

# 3) Pesos del score (por familia)

(Se usan los definidos previamente; aquí se “sellan” formalmente)

### Perecederos

- manual 0.25
    
- sla 0.20
    
- quiebre 0.25
    
- ventas 0.15
    
- promo 0.10
    
- age 0.10
    
- penalty 0.05
    

### Secos

- manual 0.25
    
- sla 0.10
    
- quiebre 0.20
    
- ventas 0.20
    
- promo 0.10
    
- age 0.15
    
- penalty 0.05
    

### Non-Food

- manual 0.25
    
- sla 0.05
    
- quiebre 0.10
    
- ventas 0.20
    
- promo 0.20
    
- age 0.20
    
- penalty 0.05
    

---

# 4) Reglas de Planificación y Asignación

## R-PLN-01 — Elegibilidad

Una Need es elegible si:

- backlog_qty > 0
    
- no está en hold
    
- next_replan_at <= now
    
- no está cancelada/expirada
    

## R-PLN-02 — Stock neto

Una PlanLine se crea solo si:

- `stock_net_available > 0`
    
- `qty_planned = min(backlog_qty, stock_net_available_remaining)`
    

## R-PLN-03 — Estrategia de asignación

Default por familia:

- Perecederos: PRIORITY
    
- Secos: PRIORITY
    
- Non-Food: PRIORITY
    

Activar FAIR_SHARE cuando:

- `stock_net_available < threshold_low_stock`  
    y hay más de `N` sucursales demandando el SKU
    

Parámetros sugeridos:

- `threshold_low_stock = 10 unidades` (ajustable por UOM)
    
- `N = 5`
    

## R-PLN-04 — FAIR_SHARE (formal)

Si se activa:

1. Asignar `min_unit` a cada sucursal en orden por prioridad hasta agotar stock.
    
2. Con remanente, completar por prioridad.
    

`min_unit`:

- si UOM = cajas → 1 caja
    
- si UOM = kg → 1 * unidad transferencia (q_unid_transferencia)
    

---

# 5) Reglas Anti-duplicación (durante transición)

## R-DEDUP-01 — Check pre-publicación obligatorio

Antes de publicar una PlanLine:

- Consultar si existe ejecución activa (Valkimia) para (CD, Sucursal, SKU)
    

Si existe:

- NO publicar nueva
    
- Marcar Need con:
    
    - `blocked_by_external_execution = true`
        
    - `next_replan_at = now + cooldown_external` (ej. 2h)
        
    - `reason_code = EXTERNAL_EXECUTION_ACTIVE`
        

## R-DEDUP-02 — Absorción (opcional)

Si se decide absorber:

- Crear `TransferExecution` con flag `external_origin=true`
    
- Linkear la Need para trazabilidad
    
- No duplicar publicación
    

---

# 6) Reglas de Publicación e Idempotencia

## R-PUB-01 — Clave idempotente

`connexa_execution_id` es clave idempotente.

Si Valkimia recibe el mismo `connexa_execution_id`:

- debe devolver el mismo `valkimia_transfer_id` y estado actual.
    

## R-PUB-02 — Parcialidad

Si Valkimia:

- acepta cabecera
    
- rechaza algunas líneas
    

Connexa debe:

- crear Execution igual
    
- para líneas rechazadas:
    
    - revertir a backlog
        
    - registrar reject_reason_code
        

---

# 7) Reglas de Replanificación (cooldown + backoff)

## R-RPL-01 — Backoff exponencial

`next_replan_at = now + min(base * 2^(attempts-1), max)`

Parámetros por familia:

- Perecederos: base 15m, max 4h
    
- Secos: base 30m, max 12h
    
- Non-Food: base 60m, max 24h
    

## R-RPL-02 — Reset de attempts

Si una Need logra ser publicada y aceptada:

- `replan_attempts` puede mantenerse (histórico)
    
- o resetear a 0 (operativo)
    

Recomendación:

- mantener histórico y resetear en un campo separado:
    
    - `current_retry_streak` (reset)
        
    - `replan_attempts_total` (acumula)
        

---

# 8) Reglas de mapeo de estados Valkimia → Connexa

## R-MAP-01 — Mapping cabecera

- Valkimia `ACEPTADA` → `EXEC_ACCEPTED`
    
- `ACO` → `EXEC_RESERVED_ACO`
    
- `PREPARACION` → `EXEC_PICKING`
    
- `DESPACHADA` → `EXEC_SHIPPED`
    
- `ENTREGADA/RECIBIDA` → `EXEC_DELIVERED`
    
- `SIN_STOCK/RECHAZO` → `EXEC_REJECTED_STOCK`
    
- `CANCELADA` → `EXEC_CANCELLED`
    
- `ERROR` → `EXEC_FAILED`
    

## R-MAP-02 — Estados “activos”

Los estados activos para anti-duplicación se derivan de los estados Valkimia “no finales” definidos en 0.2.

---

# 9) Reglas de Alertas y Umbrales

## R-ALT-01 — Aging crítico p95

- Perecederos: p95 > 6h
    
- Secos: p95 > 48h
    
- Non-Food: p95 > 96h
    

## R-ALT-02 — Rechazo por stock anómalo

- reject_rate_stock > 20% en ventana 2h
    

## R-ALT-03 — Ejecución colgada

- `EXEC_ACCEPTED` sin `PICKING` en:
    
    - Perecederos: 2h
        
    - Secos: 6h
        
    - Non-Food: 12h
        

## R-ALT-04 — Duplicación detectada

- 2 ejecuciones activas mismo (CD, Sucursal, SKU) → alerta alta
    

---

# 10) Tabla final — Parámetros “sellados” (para config)

Esta tabla debe vivir en una tabla de parámetros o archivo de config.

- bucket_mode: DAILY / INTRADAY
    
- allocation_strategy: PRIORITY / FAIR_SHARE / FIFO
    
- sla_window_hours: por familia
    
- age_max_hours: por familia
    
- backoff_base_minutes: por familia
    
- backoff_max_minutes: por familia
    
- low_stock_threshold: por familia/UOM
    
- min_unit_transfer: por SKU (o por familia)
    
- active_statuses_valkimia: lista