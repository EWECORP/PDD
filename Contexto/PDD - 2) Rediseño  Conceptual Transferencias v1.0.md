**Rediseño Conceptual Formal** (versión 0.1) del esquema de Transferencias, con foco en: **fuente única de verdad, consolidación por SKU-sucursal, trazabilidad end-to-end, y eliminación del “borrado silencioso” en Valkimia**.

---

# Documento Conceptual — Rediseño de Transferencias (v0.1)

## 0. Propósito y Alcance

**Propósito.** Definir un modelo conceptual y operativo para gestionar transferencias CD→Sucursal con trazabilidad completa, evitando duplicidades y garantizando control del ciclo de vida aun cuando existan múltiples orígenes de necesidad (Connexa y SGM).

**Alcance.**

- Necesidades de transferencia (demanda interna).
    
- Planificación factible en función de stock neto disponible del CD.
    
- Publicación/ejecución logística en Valkimia.
    
- Seguimiento por línea, con estados auditables.
    
- Base para futura optimización logística (cubicaje, consolidación de viajes).
    

**Fuera de alcance (por ahora).**

- Reglas finas de asignación entre múltiples CDs.
    
- Reoptimización dinámica intradía.
    
- Costeo logístico y ruteo avanzado.
    

---

## 1. Situación Actual (AS-IS) y Dolencias

### 1.1 Flujo actual

- Connexa genera necesidades → DMZ → SGM → Valkimia (ejecución).
    
- SGM también genera transferencias directas hacia Valkimia.
    

### 1.2 Dolencias estructurales

1. **No existe una fuente única de planificación** (múltiples orígenes).
    
2. **Duplicación potencial**: 2+ solicitudes para mismo SKU+sucursal.
    
3. **Valkimia elimina solicitudes** si no puede preparar por falta de stock (sin backlog).
    
4. **Ausencia de estados confiables**: Connexa no sabe si la línea existe, fue borrada o se ejecutó.
    
5. **Imposibilidad de evolucionar** hacia cubicaje y optimización si no se controla el ciclo.
    

---

## 2. Principios del Rediseño (TO-BE)

### P1 — Fuente Única de Verdad (SSOT)

Connexa se define como el **orquestador único** del ciclo de vida de las transferencias.  
SGM puede originar necesidades, pero **no debe ser dueño del plan**.

### P2 — Consolidación determinística

Toda necesidad se consolida en Connexa con clave funcional:  
**(CD, Sucursal, SKU, ventana temporal / fecha objetivo)**

### P3 — Valkimia como ejecutor, no como reservorio decisor

Valkimia no puede “desaparecer” solicitudes: si no puede preparar, debe responder con rechazo/pendiente y Connexa debe conservar el registro.

### P4 — Idempotencia y trazabilidad

Toda publicación debe ser idempotente y toda línea debe tener:

- identificador interno Connexa
    
- identificador Valkimia (cuando exista)
    
- historial de estados y eventos
    

### P5 — Estado por línea (no solo por cabecera)

La unidad de control es la **línea SKU-sucursal**.

---

## 3. Modelo Conceptual Propuesto (Dominios y Entidades)

Se propone separar el dominio en 3 niveles:

## 3.1 Dominio A — Necesidad (Need)

Representa “lo que se requiere transferir” independientemente de si hay stock.

**Entidad:** `TransferNeed`

- Clave: `(cd_id, sucursal_id, sku_id, need_date_bucket)`
    
- Atributos:
    
    - `qty_need`
        
    - `origen_need` (CONNEXA / SGM / manual / otros)
        
    - `prioridad`
        
    - `motivo` (rotura, fill-rate, reposición, promo, etc.)
        
    - `timestamp_creación`, `timestamp_última_actualización`
        

**Regla principal:** si llega una segunda necesidad para el mismo bucket, **se acumula** (o se recalcula) en una misma necesidad consolidada.

---

## 3.2 Dominio B — Planificación (Plan)

Representa “lo que se decide ejecutar” en función de stock neto y reglas.

**Entidad:** `TransferPlan`

- Cabecera: agrupa por CD y “corrida de planificación”
    
- Atributos:
    
    - `plan_id`
        
    - `cd_id`
        
    - `plan_run_ts`
        
    - `estado_plan` (abierto, enviado, cerrado, reintento, etc.)
        

**Entidad:** `TransferPlanLine`

- Clave: `(plan_id, sucursal_id, sku_id)`
    
- Atributos:
    
    - `qty_planned`
        
    - `qty_reserved_expected` (si aplica)
        
    - `plan_status_line`:
        
        - `PLANIFICABLE`
            
        - `PARCIAL`
            
        - `NO_PLANIFICABLE_STOCK`
            
        - `BLOQUEADA_REGLA`
            
    - `reason_code` (sin stock, bloqueado, restricción, etc.)
        
    - `need_refs` (referencia(s) a necesidades consolidadas)
        

**Regla principal:** el plan puede generar líneas parciales; lo no planificable permanece como backlog en Need.

---

## 3.3 Dominio C — Ejecución (Execution)

Representa “lo que Valkimia aceptó y está ejecutando”.

**Entidad:** `TransferExecution`

- Cabecera: corresponde a una solicitud/logística en Valkimia
    
- Atributos:
    
    - `execution_id` (Connexa)
        
    - `valkimia_transfer_id` (externo)
        
    - `cd_id`
        
    - `sucursal_id`
        
    - `estado_ejecución` (ver sección Estados)
        
    - `timestamps` relevantes
        

**Entidad:** `TransferExecutionLine`

- Clave: `(execution_id, sku_id)`
    
- Atributos:
    
    - `qty_sent`
        
    - `qty_prepared`
        
    - `qty_shipped`
        
    - `qty_received`
        
    - `execution_line_status`
        
    - `valkimia_line_id` (si existe)
        
    - `incidencias` (faltante, sustitución, etc.)
        

---

## 4. Stock Neto Valkimia (Concepto)

Se define un concepto formal:

**Stock Neto Disponible (SND)** por SKU en CD:

	SND = Stock físico  
	− reservas/compromisos (incluye ACO)  
	− en preparación  
	− pedidos pendientes (si compiten por el mismo stock)  
	− bloqueos de calidad / cuarentena

**Salida requerida de Valkimia → Connexa:** una vista/endpoint “Stock Neto Disponible por SKU-CD”, con timestamp y criterios.

---

## 5. Estados Formales del Ciclo de Vida

### 5.1 Estados de Need

- `NEED_ABIERTA`
    
- `NEED_CONSOLIDADA`
    
- `NEED_PARCIALMENTE_PLANIFICADA`
    
- `NEED_PLANIFICADA_TOTAL`
    
- `NEED_CANCELADA`
    

### 5.2 Estados de Plan (por línea)

- `PLANIFICABLE`
    
- `PARCIAL`
    
- `NO_PLANIFICABLE_STOCK`
    
- `NO_PLANIFICABLE_REGLA`
    
- `ENVIADA_A_EJECUCION`
    
- `ERROR_PUBLICACION`
    
- `REINTENTO_PENDIENTE`
    

### 5.3 Estados de Execution (Valkimia / Connexa)

- `PUBLICADA`
    
- `ACEPTADA`
    
- `RESERVADA_ACO` (si aplica)
    
- `EN_PREPARACION`
    
- `DESPACHADA`
    
- `ENTREGADA/RECIBIDA`
    
- `RECHAZADA_POR_STOCK`
    
- `CANCELADA`
    
- `ERROR_INTEGRACION`
    

**Regla clave:** Valkimia puede “rechazar”, pero Connexa nunca elimina.  
Connexa conserva el historial y permite replanificar.

---

## 6. Flujo TO-BE (Conceptual)

### Fase 1 — Ingesta de Necesidades

1. Connexa genera necesidades.
    
2. SGM (si continúa existiendo como origen) envía “necesidades SGM” a Connexa (no a Valkimia).
    
3. Connexa consolida por clave funcional.
    

### Fase 2 — Evaluación de Factibilidad (Stock Neto)

4. Connexa consulta Stock Neto Valkimia por CD-SKU.
    
5. Connexa calcula asignación y genera `TransferPlan` + líneas.
    

### Fase 3 — Publicación controlada

6. Solo líneas `PLANIFICABLE/PARCIAL` se publican a Valkimia.
    
7. Valkimia responde con `valkimia_transfer_id` y estado inicial.
    
8. Connexa persiste el vínculo (clave externa) y deja trazabilidad por línea.
    

### Fase 4 — Seguimiento y Auditoría

9. Connexa consulta o recibe eventos de Valkimia (polling o eventos).
    
10. Connexa actualiza `Execution` y retroalimenta `Need` (saldos pendientes).
    

---

## 7. Reglas de Convivencia con SGM (Transición)

Dado que hoy SGM genera transferencias directas, se proponen 2 estrategias (una neutral y una preferida):

### Estrategia Neutral (compatible, gradual)

- SGM sigue generando algunas transferencias, pero:
    
    - Connexa implementa un **mecanismo de reconciliación**: si detecta transferencias activas en Valkimia para SKU+sucursal, las descuenta del plan y/o las “absorbe” como ejecución externa.
        
- Riesgo: seguirá habiendo dualidad, pero controlada.
    

### Estrategia Recomendada (objetivo)

- SGM deja de publicar transferencias a Valkimia.
    
- SGM produce solo “Need SGM” hacia Connexa.
    
- Connexa es el único publicador a Valkimia.
    
- Resultado: se elimina la duplicación de raíz.
    

---

## 8. Requerimientos Funcionales (nivel conceptual)

1. Consolidación de necesidades por SKU-sucursal-bucket.
    
2. Cálculo de stock neto disponible desde Valkimia.
    
3. Planificación por corrida (plan_run) y por línea.
    
4. Publicación idempotente con tracking de IDs Valkimia.
    
5. Estados por línea + auditoría.
    
6. Replanificación automática de pendientes.
    
7. Reconciliación con transferencias “externas” durante transición (si existen).
    

---

## 9. Requerimientos No Funcionales

- **Trazabilidad**: todo cambio debe generar evento.
    
- **Idempotencia**: reintentos no duplican.
    
- **Observabilidad**: KPIs de:
    
    - líneas rechazadas por stock
        
    - backlog pendiente
        
    - tiempo medio hasta despacho
        
    - fill rate de transferencias
        
- **Performance**: stock neto por SKU-CD debe ser consultable masivamente.
    
- **Seguridad**: control de permisos por roles (compras / logística / IT).
    

---

## 10. Roadmap de Implementación Conceptual (en etapas)

### Etapa 1 — Control y trazabilidad sin cambiar Valkimia

- Crear `Need/Plan/Execution` en Connexa.
    
- Persistir IDs Valkimia.
    
- No perder historial.
    

### Etapa 2 — Stock neto y “publicar solo lo factible”

- Integrar consulta SND.
    
- Publicación filtrada por factibilidad.
    
- Backlog real.
    

### Etapa 3 — Desacoplar SGM como publicador

- Convertir SGM en “origen de need”.
    
- Eliminar (o bloquear) publicación directa SGM→Valkimia.
    

### Etapa 4 — Cubicaje y optimización logística

- Consolidación por viaje.
    
- Restricciones de volumen/peso/capacidad.
    
- Simulación y optimización.
    

---

# Cierre (lo que opino)

**Neutralmente:** el rediseño propuesto corrige los tres agujeros estructurales: duplicación, borrado silencioso, y falta de trazabilidad.

**Mi opinión:** el mayor beneficio se logra cuando se logra el principio de “Connexa único publicador a Valkimia”. Si eso queda a medias, igual se mejora, pero se conserva un riesgo residual de inconsistencias.



