
A continuación se entrega la **Máquina de Estados formal (state machine)** y el **Contrato de Integración mínimo** entre Connexa–SGM–Valkimia, en un nivel conceptual-operativo lo bastante preciso como para convertirse luego en especificación técnica.

---

# 1) Máquina de Estados Formal

Se modelan **tres entidades** con estados explícitos:

- **Need**: necesidad consolidada (backlog “verdadero”).
    
- **PlanLine**: decisión de planificación por línea (SKU–Sucursal).
    
- **ExecutionLine**: ejecución logística (lo que Valkimia acepta y procesa).
    

La regla central es:

> Need nunca “desaparece”; se reduce por planificaciones/ejecuciones, pero conserva historial.

---

## 1.1 State Machine — TransferNeed

### Estados (NeedStatus)

1. `NEED_OPEN`
    
2. `NEED_CONSOLIDATED`
    
3. `NEED_PARTIALLY_PLANNED`
    
4. `NEED_FULLY_PLANNED`
    
5. `NEED_PARTIALLY_EXECUTING`
    
6. `NEED_FULLY_EXECUTING`
    
7. `NEED_PARTIALLY_FULFILLED`
    
8. `NEED_FULFILLED`
    
9. `NEED_CANCELLED`
    
10. `NEED_EXPIRED` (opcional si usan ventana temporal)
    

### Eventos y transiciones

|Evento|Desde|Hacia|Regla|
|---|---|---|---|
|`NeedCreated`|—|`NEED_OPEN`|Se crea la necesidad|
|`NeedMerged`|`NEED_OPEN`/`NEED_CONSOLIDATED`|`NEED_CONSOLIDATED`|Se acumulan necesidades del mismo bucket|
|`PlanAllocated(qty)`|`NEED_CONSOLIDATED`/`NEED_OPEN`|`NEED_PARTIALLY_PLANNED` o `NEED_FULLY_PLANNED`|según qty_plan vs qty_need|
|`ExecutionPublished(qty)`|`NEED_*PLANNED`|`NEED_PARTIALLY_EXECUTING` o `NEED_FULLY_EXECUTING`|según qty publicada|
|`ExecutionProgressed(qty_fulfilled)`|`NEED_*EXECUTING`|`NEED_PARTIALLY_FULFILLED` o `NEED_FULFILLED`|según qty recibida|
|`NeedCancelled`|cualquier estado no final|`NEED_CANCELLED`|cancelación manual/negocio|
|`NeedExpired`|`NEED_OPEN`/`NEED_CONSOLIDATED`|`NEED_EXPIRED`|caducidad por fecha objetivo|

### Invariantes (Need)

- `qty_need >= qty_planned_total >= qty_published_total >= qty_fulfilled_total`
    
- Nunca se elimina el registro: solo cambia estado / cantidades.
    

---

## 1.2 State Machine — TransferPlanLine

La PlanLine representa lo que Connexa decide “intentar ejecutar” en una corrida.

### Estados (PlanLineStatus)

1. `PLAN_ELIGIBLE` (candidata por reglas)
    
2. `PLAN_NOT_ELIGIBLE_RULE` (bloqueada por reglas: mix, proveedor, etc.)
    
3. `PLAN_NOT_ELIGIBLE_STOCK` (no hay stock neto)
    
4. `PLAN_PARTIAL_STOCK` (hay stock, pero no alcanza)
    
5. `PLAN_PLANNED` (qty definida)
    
6. `PLAN_PUBLISHING` (en proceso de publicar)
    
7. `PLAN_PUBLISHED` (publicada; ya existe ExecutionLine)
    
8. `PLAN_PUBLISH_FAILED` (falló publicación)
    
9. `PLAN_SUPERSEDED` (reemplazada por replanificación)
    
10. `PLAN_CANCELLED`
    

### Eventos y transiciones

|Evento|Desde|Hacia|Regla|
|---|---|---|---|
|`PlanRunStarted`|—|`PLAN_ELIGIBLE`|Se evalúa la línea|
|`RuleBlocked`|`PLAN_ELIGIBLE`|`PLAN_NOT_ELIGIBLE_RULE`|negocio|
|`StockUnavailable`|`PLAN_ELIGIBLE`|`PLAN_NOT_ELIGIBLE_STOCK`|SND = 0|
|`StockPartial`|`PLAN_ELIGIBLE`|`PLAN_PARTIAL_STOCK`|0 < SND < need|
|`QtyPlanned`|`PLAN_ELIGIBLE`/`PLAN_PARTIAL_STOCK`|`PLAN_PLANNED`|qty definida|
|`PublishRequested`|`PLAN_PLANNED`|`PLAN_PUBLISHING`||
|`PublishAck`|`PLAN_PUBLISHING`|`PLAN_PUBLISHED`|Valkimia devuelve IDs|
|`PublishError`|`PLAN_PUBLISHING`|`PLAN_PUBLISH_FAILED`|error técnico|
|`Replanned`|`PLAN_*`|`PLAN_SUPERSEDED`|nueva corrida reemplaza|
|`PlanCancelled`|`PLAN_*`|`PLAN_CANCELLED`||

### Invariantes (PlanLine)

- `qty_planned <= StockNetoDisponible` (en la corrida)
    
- La transición a `PLAN_PUBLISHED` implica que **existe** ExecutionLine vinculada.
    

---

## 1.3 State Machine — TransferExecutionLine

La ExecutionLine representa el estado real de la logística (Valkimia).

### Estados (ExecutionLineStatus)

1. `EXEC_DRAFT` (creada internamente, aún no aceptada)
    
2. `EXEC_PUBLISHED` (request enviada)
    
3. `EXEC_ACCEPTED` (Valkimia aceptó)
    
4. `EXEC_REJECTED_STOCK` (Valkimia rechaza por stock)
    
5. `EXEC_RESERVED_ACO` (reserva/ACOPIO confirmada)
    
6. `EXEC_PICKING` (en preparación)
    
7. `EXEC_PACKED` (opcional)
    
8. `EXEC_SHIPPED` (despachada)
    
9. `EXEC_DELIVERED` (entregada/recibida)
    
10. `EXEC_CANCELLED`
    
11. `EXEC_FAILED` (error integraciones)
    

### Eventos y transiciones

|Evento|Desde|Hacia|Regla|
|---|---|---|---|
|`PublishSent`|`EXEC_DRAFT`|`EXEC_PUBLISHED`||
|`ValkimiaAccepted`|`EXEC_PUBLISHED`|`EXEC_ACCEPTED`||
|`ValkimiaRejectedStock`|`EXEC_PUBLISHED`|`EXEC_REJECTED_STOCK`|NO borrar; devolver motivo|
|`ACOConfirmed`|`EXEC_ACCEPTED`|`EXEC_RESERVED_ACO`|si aplica|
|`PickingStarted`|`EXEC_ACCEPTED`/`EXEC_RESERVED_ACO`|`EXEC_PICKING`||
|`Shipped`|`EXEC_PICKING`|`EXEC_SHIPPED`||
|`Delivered`|`EXEC_SHIPPED`|`EXEC_DELIVERED`||
|`Cancelled`|`EXEC_*`|`EXEC_CANCELLED`||
|`IntegrationError`|cualquier|`EXEC_FAILED`||

### Invariantes (ExecutionLine)

- Si Valkimia “no puede”, el estado correcto es `EXEC_REJECTED_STOCK`, no eliminación.
    
- `EXEC_DELIVERED` es final exitoso.
    

---

# 2) Contrato de Integración Mínimo

El contrato mínimo tiene tres APIs (o interfaces) lógicas:

1. **Stock Neto Disponible** (Valkimia → Connexa)
    
2. **Publicación de Transferencias** (Connexa → Valkimia)
    
3. **Tracking / Eventos de Estado** (Valkimia → Connexa o Connexa consulta)
    

Se especifica en formato conceptual (luego se pasa a OpenAPI / contratos técnicos).

---

## 2.1 API 1 — Stock Neto Disponible (Valkimia → Connexa)

### Objetivo

Connexa necesita el stock “utilizable” para planificar sin generar basura.

### Request (conceptual)

- Parámetros:
    
    - `cd_id`
        
    - `sku_ids[]` (batch)
        
    - `as_of_ts` (opcional; por defecto “ahora”)
        
    - `include_components` (opcional para auditoría)
        

### Response

Por cada SKU:

- `cd_id`
    
- `sku_id`
    
- `stock_physical`
    
- `stock_reserved_aco`
    
- `stock_in_picking`
    
- `stock_committed_orders` (si corresponde)
    
- `stock_blocked_quality` (si existe)
    
- `stock_net_available` ✅ (campo obligatorio)
    
- `calculated_at_ts`
    
- `stock_version` (hash o secuencia para idempotencia / reconciliación)
    

**Regla contractual:** `stock_net_available` debe ser consistente con los componentes informados.

---

## 2.2 API 2 — Publicación de Transferencia (Connexa → Valkimia)

### Objetivo

Enviar solo lo planificable, de forma idempotente, y recibir IDs Valkimia para tracking.

### Request — Cabecera

- `connexa_execution_id` (UUID o correlativo)
    
- `plan_id`
    
- `cd_id`
    
- `sucursal_id`
    
- `requested_ship_window` (opcional)
    
- `priority`
    
- `created_at_ts`
    

### Request — Líneas

- `connexa_line_id`
    
- `sku_id`
    
- `qty_requested`
    
- `uom` (unidad; kg/unidades)
    
- `constraints` (opcional; frágil, temperatura, etc.)
    

### Idempotencia

- Valkimia debe tratar `(connexa_execution_id)` como clave idempotente.
    
- Si llega repetido:
    
    - devolver el mismo `valkimia_transfer_id` y estado actual.
        

### Response

- `valkimia_transfer_id` ✅
    
- `accepted` (bool)
    
- `status` (ej: ACCEPTED / REJECTED_STOCK)
    
- `lines[]` con:
    
    - `connexa_line_id`
        
    - `valkimia_line_id`
        
    - `status`
        
    - `reason_code` (si rechaza)
        
- `received_at_ts`
    

**Regla contractual:** si no puede por stock, responde `REJECTED_STOCK` (no borra).

---

## 2.3 API 3 — Tracking de Estado (Valkimia ↔ Connexa)

Hay dos patrones posibles: **Polling** o **Eventos**. Conceptualmente se definen ambos; se puede implementar primero Polling.

### Opción A — Polling (Connexa consulta)

**Request:**

- `valkimia_transfer_id` o `since_ts`
    

**Response:**

- cabecera con estado actual y timestamps
    
- líneas con estado y cantidades:
    
    - `qty_prepared`
        
    - `qty_shipped`
        
    - `qty_delivered`
        

### Opción B — Eventos (Valkimia publica eventos)

**Evento:**

- `event_id`
    
- `valkimia_transfer_id`
    
- `connexa_execution_id` (si lo guardan)
    
- `event_type` (ACOConfirmed, PickingStarted, Shipped, Delivered, RejectedStock)
    
- `event_ts`
    
- `payload` (cantidades, motivo)
    

**Regla contractual:** los eventos deben ser:

- **ordenables por `event_ts`**
    
- **deduplicables por `event_id`**
    

---

# 3) Contrato adicional mínimo con SGM (durante transición)

Si SGM va a seguir generando “algo”, el contrato recomendado es:

## SGM → Connexa: “Need SGM”

- `origen = SGM`
    
- `sku_id`
    
- `sucursal_id`
    
- `qty_need`
    
- `need_date_bucket`
    
- `reason_code`
    
- `sgm_reference_id` (para auditoría)
    

**Regla:** SGM no publica a Valkimia; solo informa necesidades.

---

# 4) Reglas de Reconciliación (para evitar duplicados durante transición)

Mientras exista dualidad, Connexa debe detectar “ejecuciones externas” en Valkimia:

### Mecanismo

- Valkimia expone listados activos por `(cd_id, sucursal_id, sku_id)` con estados no finales.
    
- Connexa lo interpreta como `ExternalExecution` y:
    
    - descuenta del backlog Need
        
    - evita publicar duplicado
        
    - o “absorbe” la ejecución para tracking (modo reconciliación)
        

Esto permite migrar sin cortar operación.


---
