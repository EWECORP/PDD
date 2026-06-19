A continuación se entrega el **Paquete de Integración v1.0**: mapa de datos y dependencias para scoring, contratos/consultas requeridas a Valkimia, y el modelo de **ExternalExecution** para convivencia con SGM. Está armado para que pueda copiarse como bloque en Confluence y transformarse en tareas de desarrollo.

---

# Paquete de Integración v1.0 — Transferencias

## 1) Mapa de Datos y Dependencias para Score y Planificación

### 1.1 Datos mínimos por Need (SKU–Sucursal–CD–Bucket)

Para que el planificador funcione en modo completo (no degradado), Connexa necesita:

**A) Datos de demanda / urgencia**

- `manual_priority` (Connexa/SGM/manual)
    
- `sla_due_at` (si existe)
    
- `created_at` (aging)
    

**B) Datos tienda (contexto de quiebre y ventas)**

- `stock_store` (stock tienda actual)
    
- `stock_min_store` (mínimo o stock seguridad por tienda/SKU)
    
- `sales_rate_30d` (venta promedio diaria 30d)
    
- `promo_active` (promo vigente)
    

**C) Datos logísticos por SKU**

- `uom` (unidades / kg)
    
- `unit_transfer` (unidad mínima de transferencia)
    
- `case_pack` (si aplica)
    
- `family/category` (perecederos/secos/non-food)
    
- (futuro) `unit_volume`, `unit_weight`
    

**D) Datos CD (stock factible)**

- `stock_net_available` (SND) — Valkimia
    

---

### 1.2 Origen recomendado de cada dato (fuente “de verdad”)

|Dato|Fuente de verdad recomendada|Observación|
|---|---|---|
|stock_net_available (CD–SKU)|Valkimia|imprescindible|
|stock_store (Sucursal–SKU)|SGM / réplica a PG|si no está, score degrada|
|stock_min_store|Connexa/SGM (parametría surtido)|puede venir de maestro de mix|
|sales_rate_30d|Data mart (ventas)|cálculo diario o incremental|
|promo_active|SGM/Promo engine|boolean + vigencia|
|uom / vende por peso|Maestro de artículos|para unidades vs kg|
|unit_transfer / mínimos|Maestro de artículos/sucursal|clave para FAIR_SHARE|
|family/category|Maestro (clasificación)|define pesos y frecuencias|

---

### 1.3 Modo degradado (si faltan datos)

Para avanzar sin bloquear implementación:

- Si falta `stock_store` o `stock_min_store` ⇒ `break_risk = 0`
    
- Si falta `sales_rate_30d` ⇒ `sales_rate_norm = 0.5` o `0`
    
- Si falta `promo_active` ⇒ `promo_boost = 0`
    
- Score pasa a ser casi FIFO + prioridad manual, pero el sistema funciona.
    

---

## 2) Contratos/Consultas requeridas a Valkimia (mínimo viable)

Se definen 4 capacidades:

1. **Stock neto disponible (batch)**
    
2. **Listado de ejecuciones activas por SKU–Sucursal (anti-duplicación)**
    
3. **Publicación idempotente**
    
4. **Tracking de estado (polling o eventos)**
    

---

### 2.1 Interfaz V-01 — Stock Neto Disponible (batch)

**Objetivo:** planificar con factibilidad real.

**Request (conceptual):**

- `cd_id`
    
- `sku_ids[]`
    
- `as_of_ts` (opcional)
    

**Response por SKU:**

- `sku_id`
    
- `stock_net_available`
    
- `stock_physical` _(opcional, auditoría)_
    
- `stock_reserved_aco` _(opcional)_
    
- `stock_in_picking` _(opcional)_
    
- `calculated_at_ts`
    
- `stock_version`
    

**Regla:** `stock_net_available` nunca negativo. Si es negativo, se fuerza a 0 y se alerta (consistencia).

---

### 2.2 Interfaz V-02 — Ejecuciones activas por CD (para anti-duplicación)

**Objetivo:** detectar si ya existe una transferencia activa para evitar duplicar.

**Request:**

- `cd_id`
    
- `status_in[]` (opcional; por defecto estados activos)
    
- `since_ts` (opcional)
    

**Response (cabecera + líneas):**

- `valkimia_transfer_id`
    
- `cd_id`
    
- `sucursal_id`
    
- `status`
    
- `created_at_ts`
    
- `lines[]`: `sku_id`, `qty_requested`, `qty_prepared`, `qty_shipped`
    

**Uso:** Connexa construye un mapa rápido:  
`active_exec_map[(cd_id, sucursal_id, sku_id)] = valkimia_transfer_id`

---

### 2.3 Interfaz V-03 — Publicación idempotente

**Request:**

- `connexa_execution_id` (clave idempotente)
    
- `cd_id`, `sucursal_id`, `priority`, `created_at_ts`
    
- `lines[]`: `connexa_line_id`, `sku_id`, `qty_requested`, `uom`
    

**Response:**

- `valkimia_transfer_id`
    
- `accepted` (bool)
    
- `status`
    
- `lines[]`: `connexa_line_id`, `valkimia_line_id`, `status`, `reason_code`
    

**Regla:** si `connexa_execution_id` se repite, devuelve el mismo `valkimia_transfer_id`.

---

### 2.4 Interfaz V-04 — Tracking de estado

**Opción A (Polling):**

- `GET /transfers/{valkimia_transfer_id}`
    
- devuelve estado y cantidades por línea
    

**Opción B (Eventos):**

- Valkimia emite eventos `TransferStatusChanged` y `LineStatusChanged`
    
- Connexa deduplica por `event_id`
    

**Recomendación práctica de transición:** empezar con Polling (más simple), evolucionar a eventos cuando haya madurez.

---

## 3) Modelo “ExternalExecution” (convivencia con SGM)

Mientras exista SGM → Valkimia (aunque se quiera eliminar), Connexa debe poder:

- **ver** esas transferencias,
    
- **absorberlas** para tracking,
    
- **descontarlas** del backlog y no duplicar.
    

### 3.1 Entidad conceptual: ExternalExecution

**ExternalExecution**

- `external_execution_id` (UUID)
    
- `source_system` = `SGM` (u otros)
    
- `valkimia_transfer_id`
    
- `cd_id`
    
- `sucursal_id`
    
- `detected_at_ts`
    
- `status`
    
- `is_active` (bool)
    
- `linked_need_count`
    
- `notes`
    

**ExternalExecutionLine**

- `external_execution_line_id`
    
- `external_execution_id`
    
- `sku_id`
    
- `qty_requested`
    
- `qty_prepared`
    
- `qty_shipped`
    
- `qty_received` (si se conoce)
    
- `status`
    

### 3.2 Regla de absorción (linking) Need ↔ ExternalExecution

Cuando Connexa detecta una ejecución activa para (CD, Sucursal, SKU):

- Si existe Need matching (misma clave funcional/bucket cercano):
    
    - Linkear Need a ExternalExecutionLine
        
    - Marcar Need como `blocked_by_external_execution = true`
        
    - Ajustar `next_replan_at` (cooldown 2h)
        
    - Registrar evento: `ExternalExecutionDetected`
        

**¿Se descuenta backlog?** Dos opciones:

- **Opción conservadora (recomendada al principio):**
    
    - No descuenta backlog hasta ver despacho/entrega.
        
    - Solo bloquea publicación duplicada.
        
- **Opción agresiva:**
    
    - Descunta `qty_requested` como “committed externally”.
        
    - Requiere alta confianza en datos Valkimia.
        

---

## 4) Checklist técnico para implementar (mínimo viable)

### 4.1 Repositorio / Servicios

- Servicio/Job `planner_run_cd(cd_id)` (cron)
    
- Servicio `valkimia_adapter`:
    
    - get_stock_net_available
        
    - get_active_executions
        
    - publish_transfer
        
    - get_transfer_status
        

### 4.2 Persistencia (Connexa)

Tablas mínimas:

- `transfer_need`
    
- `transfer_plan`, `transfer_plan_line`
    
- `transfer_execution`, `transfer_execution_line`
    
- `external_execution`, `external_execution_line`
    
- `transfer_event_log`
    

### 4.3 Idempotencia y locking

- Unicidad Need: `(cd_id, sucursal_id, sku_id, bucket_date)`
    
- Unicidad PlanLine: `(plan_id, sucursal_id, sku_id)`
    
- Unicidad Execution: `connexa_execution_id` y `valkimia_transfer_id`
    
- `need_version` para optimistic lock (evitar carrera de replan)
    

---

## 5) KPIs de Integración (para validar en producción)

1. `publish_success_rate`
    
2. `reject_rate_stock`
    
3. `active_exec_dedup_hits` (cuántas veces se evitó duplicar)
    
4. `backlog_total` y `backlog_aging_p95`
    
5. `time_to_ship_p90`
    

---

# 6) Decisiones que conviene “cerrar” antes de codificar

1. ¿Bucket diario o intradía para perecederos?
    
2. ¿Se absorben ejecuciones externas (sí/no) y con qué modalidad (conservadora/agresiva)?
    
3. ¿Qué estados exactos de Valkimia existen y su mapping final?
    
4. ¿Polling o eventos en etapa 1? (recomendado: polling)
    
5. ¿Unidad mínima de transferencia por SKU (dónde vive la parametría)?
    

---

# 7) Próximo entregable inmediato (si siguen avanzando)

Para pasar de integración conceptual a implementación con baja fricción, el siguiente documento sería:

## “Especificación de Interfaces Valkimia v1.0”

- Payloads exactos (campos, tipos, obligatoriedad)
    
- Ejemplos de request/response
    
- Códigos de error y reintentos
    
- Timeouts, paginación, batch size
    

y en paralelo:

## “Diseño del tablero operativo v1.0”

- vistas, filtros, KPIs, drilldowns