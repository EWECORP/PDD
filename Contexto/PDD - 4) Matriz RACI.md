Se desarrolla a continuación la **Matriz RACI formal** y el **Diccionario de Datos conceptual mínimo** para las entidades `TransferNeed`, `TransferPlan`, `TransferExecution`, con reglas de unicidad e índices recomendados.

Este documento puede considerarse **Versión 1.0 — Diseño Funcional-Conceptual** listo para pasar a especificación técnica.

---

# 1️⃣ MATRIZ RACI — Ciclo de Vida de Transferencias

### Roles considerados

- **Connexa (CNE)** → Orquestador funcional y técnico
    
- **SGM (SGM)** → Origen secundario de necesidad
    
- **Valkimia (VAL)** → Ejecutor logístico
    
- **Operación CD (OCD)** → Gestión física
    
- **Operación Sucursal (OSC)** → Recepción
    
- **IT Integraciones (ITI)** → Soporte técnico
    

---

## 1.1 Creación y Consolidación de Need

|Evento|CNE|SGM|VAL|OCD|OSC|ITI|
|---|---|---|---|---|---|---|
|Generar Need desde Forecast|R/A|I|I|I|I|C|
|Generar Need desde SGM|I|R/A|I|I|I|C|
|Consolidar Need|R/A|I|I|I|I|C|
|Cancelar Need|R/A|C|I|I|I|C|

---

## 1.2 Planificación

|Evento|CNE|SGM|VAL|OCD|OSC|ITI|
|---|---|---|---|---|---|---|
|Consultar Stock Neto|R|I|A|I|I|C|
|Calcular Plan|R/A|I|I|I|I|C|
|Replanificar|R/A|I|I|I|I|C|
|Bloquear por regla negocio|R/A|C|I|I|I|C|

---

## 1.3 Publicación

|Evento|CNE|SGM|VAL|OCD|OSC|ITI|
|---|---|---|---|---|---|---|
|Publicar Transferencia|R|I|A|I|I|C|
|Aceptar Transferencia|I|I|R/A|I|I|C|
|Rechazar por stock|I|I|R/A|I|I|C|
|Error integración|C|I|C|I|I|R/A|

---

## 1.4 Ejecución Logística

|Evento|CNE|SGM|VAL|OCD|OSC|ITI|
|---|---|---|---|---|---|---|
|Reserva ACO|I|I|R/A|C|I|C|
|Picking|I|I|R|A|I|C|
|Despacho|I|I|R|A|I|C|
|Recepción|I|I|I|C|R/A|C|
|Confirmación Entrega|R|I|A|I|C|C|

---

## 1.5 Reglas Clave Derivadas del RACI

1. Connexa es **Accountable** del ciclo completo.
    
2. Valkimia es **Accountable** de:
    
    - Stock Neto
        
    - Estados físicos
        
3. SGM no debe ser responsable de ejecución logística.
    
4. Operación CD es responsable del proceso físico, pero no del estado sistémico.
    

---

# 2️⃣ DICCIONARIO DE DATOS CONCEPTUAL

Se definen las entidades mínimas necesarias.

---

# 2.1 Entidad: TransferNeed

### Clave funcional única

(cd_id, sucursal_id, sku_id, need_bucket_date)

### Campos mínimos

|Campo|Tipo conceptual|Obligatorio|Descripción|
|---|---|---|---|
|need_id|UUID|✔|PK técnica|
|cd_id|int|✔|Centro distribución|
|sucursal_id|int|✔|Destino|
|sku_id|bigint|✔|Artículo|
|need_bucket_date|date|✔|Fecha objetivo|
|qty_need|numeric|✔|Cantidad total|
|qty_planned|numeric|✔|Default 0|
|qty_published|numeric|✔|Default 0|
|qty_fulfilled|numeric|✔|Default 0|
|need_status|enum|✔|Estado|
|origin_type|enum|✔|CONNEXA / SGM / MANUAL|
|priority|smallint|✔|Nivel prioridad|
|reason_code|varchar|✔|Motivo|
|created_at|timestamp|✔||
|updated_at|timestamp|✔||

### Índices recomendados

UNIQUE (cd_id, sucursal_id, sku_id, need_bucket_date)  
INDEX (need_status)  
INDEX (sku_id)  
INDEX (sucursal_id)

---

# 2.2 Entidad: TransferPlan

### Campos

|Campo|Tipo|Obligatorio|
|---|---|---|
|plan_id|UUID|✔|
|cd_id|int|✔|
|plan_run_ts|timestamp|✔|
|plan_status|enum|✔|
|created_by|varchar|✔|
|created_at|timestamp|✔|

### Índices

INDEX (cd_id, plan_run_ts)

---

# 2.3 Entidad: TransferPlanLine

|Campo|Tipo|Obligatorio|
|---|---|---|
|plan_line_id|UUID|✔|
|plan_id|UUID|✔|
|need_id|UUID|✔|
|sku_id|bigint|✔|
|sucursal_id|int|✔|
|qty_planned|numeric|✔|
|stock_snapshot|numeric|✔|
|plan_line_status|enum|✔|
|reason_code|varchar|✖|
|created_at|timestamp|✔|

### Restricciones

UNIQUE (plan_id, sku_id, sucursal_id)  
FOREIGN KEY (need_id)

---

# 2.4 Entidad: TransferExecution

|Campo|Tipo|Obligatorio|
|---|---|---|
|execution_id|UUID|✔|
|plan_id|UUID|✔|
|cd_id|int|✔|
|sucursal_id|int|✔|
|valkimia_transfer_id|varchar|✔|
|execution_status|enum|✔|
|published_at|timestamp|✔|
|last_update_at|timestamp|✔|

### Índices

UNIQUE (valkimia_transfer_id)  
INDEX (execution_status)

---

# 2.5 Entidad: TransferExecutionLine

|Campo|Tipo|Obligatorio|
|---|---|---|
|execution_line_id|UUID|✔|
|execution_id|UUID|✔|
|sku_id|bigint|✔|
|qty_requested|numeric|✔|
|qty_prepared|numeric|✔|
|qty_shipped|numeric|✔|
|qty_received|numeric|✔|
|execution_line_status|enum|✔|
|valkimia_line_id|varchar|✔|
|last_event_ts|timestamp|✔|

### Restricciones

UNIQUE (execution_id, sku_id)  
FOREIGN KEY (execution_id)

---

# 3️⃣ Reglas de Integridad Transversal

### R1 — Nunca eliminar

TransferNeed, Plan o Execution no se borran.  
Solo cambian estado.

### R2 — Idempotencia

Publicación debe ser única por `execution_id`.

### R3 — Trazabilidad total

Toda transición genera registro en tabla:

transfer_event_log

Con:

- entity_type
    
- entity_id
    
- old_status
    
- new_status
    
- event_type
    
- event_ts
    
- source_system
    

---

# 4️⃣ Reglas de Negocio Críticas

1. Una Need no puede pasar a FULFILLED si `qty_fulfilled < qty_need`.
    
2. Una PlanLine no puede publicarse si `qty_planned > stock_net_available_snapshot`.
    
3. Una ExecutionLine rechazada por stock debe:
    
    - restar qty_published
        
    - devolver qty al backlog Need.
        

---

# 5️⃣ Preparación para Fase 2 (Cubicaje)

Para soportarlo, debe agregarse:

En `TransferPlanLine`:

- `unit_volume`
    
- `unit_weight`
    
- `total_volume`
    
- `total_weight`
    

En `TransferExecution`:

- `truck_capacity_volume`
    
- `truck_capacity_weight`
    
- `capacity_utilization_pct`
    

---

# 6️⃣ Evaluación Arquitectónica Final

### Versión Neutral

El modelo ya:

- Elimina duplicación
    
- Impide borrado silencioso
    
- Permite replanificación
    
- Asegura trazabilidad
    

### Opinión Técnica

Este modelo transforma Connexa en un verdadero **OMS interno de transferencias**.  
Con esta base, pueden:

- Medir fill rate real CD→Sucursal
    
- Simular impacto financiero de faltantes
    
- Optimizar consolidación de viajes
    
- Integrar forecasting + logística en un único motor
    

---

Si desean avanzar al siguiente nivel, el paso lógico es:

1. Diseñar el **Modelo ER físico preliminar (PostgreSQL)**
    
2. Definir el **Plan de Migración desde el esquema actual**
    
3. Diseñar el **Modelo de Backlog y Replanificación automática**
    

¿Avanzamos hacia el modelo físico preliminar o prefieren primero diseñar el plan de migración controlado desde el esquema actual?

---
