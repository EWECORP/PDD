A continuación se entrega la **Especificación de Interfaces Valkimia v1.0** en formato **contract-first** (apto para OpenAPI luego). Se mantiene neutral respecto a si Valkimia expone REST, SOAP o SPs: el contrato define **payloads, reglas, idempotencia, errores, reintentos y límites**.

> Convención: todos los timestamps en ISO-8601, zona `America/Argentina/Buenos_Aires` o con offset.

---

# 0) Convenciones generales

## 0.1 Identificadores

- `connexa_execution_id`: UUID generado por Connexa (clave idempotente por cabecera).
    
- `connexa_line_id`: UUID por línea dentro del execution.
    
- `valkimia_transfer_id`: ID devuelto por Valkimia (string).
    
- `valkimia_line_id`: ID por línea devuelto por Valkimia (string).
    

## 0.2 Unidades de medida (UOM)

- `UNIT` (unidades)
    
- `KG` (kilos)
    
- (extensible) `L`, `M3`
    

Regla: `qty_requested` es decimal; se validará según `uom` y reglas de redondeo.

## 0.3 Estados estándar (normalizados)

Se define un set normalizado para que Connexa no dependa de nombres internos de Valkimia:

- `ACCEPTED`
    
- `REJECTED_STOCK`
    
- `REJECTED_RULE`
    
- `RESERVED_ACO`
    
- `PICKING`
    
- `PACKED` _(opcional)_
    
- `SHIPPED`
    
- `DELIVERED`
    
- `CANCELLED`
    
- `FAILED`
    

Valkimia puede tener estados propios, pero debe mapearlos a estos para integración.

---

# 1) Interface V-01 — Stock Neto Disponible (Batch)

## 1.1 Endpoint lógico

`POST /v1/stock/net-available`

## 1.2 Request

{  
  "request_id": "uuid-opcional",  
  "cd_id": 1,  
  "as_of_ts": "2026-03-02T10:30:00-03:00",  
  "sku_ids": [100200300, 100200301, 100200302],  
  "include_components": true  
}

### Reglas

- `sku_ids` batch máximo sugerido: 2.000 (parametrizable).
    
- Si `as_of_ts` es null → “ahora”.
    
- `include_components=false` habilita respuesta más liviana.
    

## 1.3 Response (200)

{  
  "cd_id": 1,  
  "calculated_at_ts": "2026-03-02T10:30:03-03:00",  
  "stock_version": "20260302T103003Z#CD1#seq889123",  
  "items": [  
    {  
      "sku_id": 100200300,  
      "stock_net_available": 120.0,  
      "uom": "UNIT",  
      "components": {  
        "stock_physical": 200.0,  
        "stock_reserved_aco": 50.0,  
        "stock_in_picking": 20.0,  
        "stock_committed_orders": 10.0,  
        "stock_blocked_quality": 0.0  
      }  
    },  
    {  
      "sku_id": 100200301,  
      "stock_net_available": 0.0,  
      "uom": "UNIT",  
      "components": {  
        "stock_physical": 12.0,  
        "stock_reserved_aco": 12.0,  
        "stock_in_picking": 0.0,  
        "stock_committed_orders": 0.0,  
        "stock_blocked_quality": 0.0  
      }  
    }  
  ],  
  "missing_skus": [100200302]  
}

### Reglas de negocio (obligatorias)

- `stock_net_available >= 0` siempre.
    
- Si un SKU no existe o no está en CD → debe informarse en `missing_skus`.
    
- Si `include_components=true`, la suma debe ser consistente:
    
    - `stock_net_available = max(stock_physical - reserved_aco - in_picking - committed - blocked, 0)`
        

## 1.4 Errores

- `400 INVALID_REQUEST` (cd_id faltante, sku_ids vacío)
    
- `413 PAYLOAD_TOO_LARGE` (batch excedido)
    
- `429 RATE_LIMIT` (demasiadas llamadas)
    
- `500 INTERNAL_ERROR`
    

---

# 2) Interface V-02 — Listado de Ejecuciones Activas (Anti-duplicación)

## 2.1 Endpoint lógico

`GET /v1/transfers/active?cd_id=1&since_ts=...`

## 2.2 Request (query params)

- `cd_id` (obligatorio)
    
- `since_ts` (opcional, default: last 48h)
    
- `status_in` (opcional; default: estados activos)
    
- `include_lines` (default: true)
    

## 2.3 Response (200)

{  
  "cd_id": 1,  
  "generated_at_ts": "2026-03-02T10:35:10-03:00",  
  "active_statuses": ["ACCEPTED","RESERVED_ACO","PICKING","SHIPPED"],  
  "items": [  
    {  
      "valkimia_transfer_id": "TRF-894455",  
      "cd_id": 1,  
      "sucursal_id": 41,  
      "status": "RESERVED_ACO",  
      "created_at_ts": "2026-03-02T09:10:00-03:00",  
      "last_update_ts": "2026-03-02T09:12:00-03:00",  
      "lines": [  
        {  
          "valkimia_line_id": "TRF-894455-001",  
          "sku_id": 100200300,  
          "uom": "UNIT",  
          "qty_requested": 10,  
          "qty_prepared": 0,  
          "qty_shipped": 0,  
          "line_status": "RESERVED_ACO"  
        }  
      ]  
    }  
  ]  
}

### Reglas

- Si `include_lines=false`, se omite `lines` y el payload se reduce.
    
- Debe ser paginable si el volumen es alto:
    
    - `page_token` / `next_page_token` (opcional).
        

## 2.4 Errores

- `400 INVALID_REQUEST` (cd_id faltante)
    
- `429 RATE_LIMIT`
    
- `500 INTERNAL_ERROR`
    

---

# 3) Interface V-03 — Publicación de Transferencia (Idempotente)

## 3.1 Endpoint lógico

`POST /v1/transfers`

## 3.2 Request (cabecera + líneas)

{  
  "connexa_execution_id": "8bff7c5d-ff55-4d5b-a26c-6f7fd30fd9aa",  
  "plan_id": "53ab0f20-9c52-47b3-aad7-6054b8ff1c2d",  
  "cd_id": 1,  
  "sucursal_id": 41,  
  "priority": 60,  
  "created_at_ts": "2026-03-02T10:40:00-03:00",  
  "requested_ship_window": {  
    "from_ts": "2026-03-02T12:00:00-03:00",  
    "to_ts": "2026-03-03T18:00:00-03:00"  
  },  
  "lines": [  
    {  
      "connexa_line_id": "1efb2e62-7d3a-4fd6-87a8-5134d746c2b8",  
      "sku_id": 100200300,  
      "uom": "UNIT",  
      "qty_requested": 12.0  
    },  
    {  
      "connexa_line_id": "b3b3ef2b-9d50-4c7e-9a88-5d1c48f9cfe3",  
      "sku_id": 100200301,  
      "uom": "UNIT",  
      "qty_requested": 6.0  
    }  
  ]  
}

### Validaciones obligatorias

- `connexa_execution_id` debe ser **único** por ejecución.
    
- `lines` no vacío; máximo sugerido por request: 2.000 líneas (parametrizable).
    
- No se permiten líneas duplicadas por `sku_id` dentro de la misma ejecución (si llegan, Valkimia debe consolidarlas o rechazar con error claro).
    
- `qty_requested > 0`.
    
- Coherencia de UOM (si SKU es pesable y viene en UNIT → error de validación o conversión declarada).
    

## 3.3 Respuesta idempotente — éxito total (200)

{  
  "connexa_execution_id": "8bff7c5d-ff55-4d5b-a26c-6f7fd30fd9aa",  
  "valkimia_transfer_id": "TRF-894470",  
  "accepted": true,  
  "status": "ACCEPTED",  
  "received_at_ts": "2026-03-02T10:40:02-03:00",  
  "lines": [  
    {  
      "connexa_line_id": "1efb2e62-7d3a-4fd6-87a8-5134d746c2b8",  
      "valkimia_line_id": "TRF-894470-001",  
      "sku_id": 100200300,  
      "status": "ACCEPTED",  
      "reason_code": null  
    },  
    {  
      "connexa_line_id": "b3b3ef2b-9d50-4c7e-9a88-5d1c48f9cfe3",  
      "valkimia_line_id": "TRF-894470-002",  
      "sku_id": 100200301,  
      "status": "ACCEPTED",  
      "reason_code": null  
    }  
  ]  
}

## 3.4 Respuesta — aceptación parcial (200)

{  
  "connexa_execution_id": "8bff7c5d-ff55-4d5b-a26c-6f7fd30fd9aa",  
  "valkimia_transfer_id": "TRF-894471",  
  "accepted": true,  
  "status": "ACCEPTED",  
  "received_at_ts": "2026-03-02T10:40:02-03:00",  
  "lines": [  
    {  
      "connexa_line_id": "1efb2e62-7d3a-4fd6-87a8-5134d746c2b8",  
      "valkimia_line_id": "TRF-894471-001",  
      "sku_id": 100200300,  
      "status": "ACCEPTED",  
      "reason_code": null  
    },  
    {  
      "connexa_line_id": "b3b3ef2b-9d50-4c7e-9a88-5d1c48f9cfe3",  
      "valkimia_line_id": null,  
      "sku_id": 100200301,  
      "status": "REJECTED_STOCK",  
      "reason_code": "NO_NET_STOCK"  
    }  
  ]  
}

### Regla crítica (obligatoria)

**Valkimia NO debe eliminar la solicitud.**  
Si no puede, responde `REJECTED_STOCK` por línea y conserva el evento (auditable).

## 3.5 Respuesta — rechazo total por stock (200 o 409)

Opción recomendada: **200 con `accepted=false`** (más simple para Connexa).

{  
  "connexa_execution_id": "8bff7c5d-ff55-4d5b-a26c-6f7fd30fd9aa",  
  "valkimia_transfer_id": "TRF-894472",  
  "accepted": false,  
  "status": "REJECTED_STOCK",  
  "received_at_ts": "2026-03-02T10:40:02-03:00",  
  "reason_code": "NO_NET_STOCK_HEADER",  
  "lines": [  
    {  
      "connexa_line_id": "1efb2e62-7d3a-4fd6-87a8-5134d746c2b8",  
      "valkimia_line_id": null,  
      "sku_id": 100200300,  
      "status": "REJECTED_STOCK",  
      "reason_code": "NO_NET_STOCK"  
    }  
  ]  
}

## 3.6 Idempotencia (reintento)

Si Connexa reenvía el mismo `connexa_execution_id`, Valkimia devuelve **idéntico**:

- `valkimia_transfer_id`
    
- `status`
    
- `lines[*].valkimia_line_id/status`
    

## 3.7 Errores (cuando el request es inválido)

- `400 INVALID_REQUEST`
    
    - qty <= 0
        
    - UOM incompatible
        
    - lines vacío
        
- `409 DUPLICATE_REQUEST`
    
    - si Valkimia no implementa idempotencia y detecta duplicado (no recomendado)
        
- `422 UNPROCESSABLE_RULE`
    
    - reglas de negocio (ej. sucursal bloqueada)
        
- `429 RATE_LIMIT`
    
- `500 INTERNAL_ERROR`
    
- `503 DEPENDENCY_UNAVAILABLE` (si Valkimia no puede calcular stock o acceder a su WMS interno)
    

---

# 4) Interface V-04 — Consulta de Transferencia por ID (Tracking)

## 4.1 Endpoint lógico

`GET /v1/transfers/{valkimia_transfer_id}`

## 4.2 Response (200)

{  
  "valkimia_transfer_id": "TRF-894470",  
  "cd_id": 1,  
  "sucursal_id": 41,  
  "status": "PICKING",  
  "created_at_ts": "2026-03-02T10:40:02-03:00",  
  "last_update_ts": "2026-03-02T11:15:00-03:00",  
  "lines": [  
    {  
      "valkimia_line_id": "TRF-894470-001",  
      "sku_id": 100200300,  
      "uom": "UNIT",  
      "qty_requested": 12,  
      "qty_prepared": 12,  
      "qty_shipped": 0,  
      "qty_delivered": 0,  
      "line_status": "PICKING"  
    }  
  ],  
  "events": [  
    {  
      "event_id": "EVT-001",  
      "event_type": "PICKING_STARTED",  
      "event_ts": "2026-03-02T11:10:00-03:00"  
    }  
  ]  
}

### Reglas

- `events` opcional (si existe, facilita reconciliación).
    
- Si no hay `events`, Connexa usa `status/last_update_ts`.
    

## 4.3 Errores

- `404 NOT_FOUND` (id inexistente)
    
- `429 RATE_LIMIT`
    
- `500 INTERNAL_ERROR`
    

---

# 5) Interface V-05 — Consulta incremental de eventos (opcional pero muy útil)

Si Valkimia puede exponerlo, reduce polling.

## 5.1 Endpoint lógico

`GET /v1/transfers/events?cd_id=1&since_ts=...`

## 5.2 Response

{  
  "cd_id": 1,  
  "since_ts": "2026-03-02T00:00:00-03:00",  
  "generated_at_ts": "2026-03-02T11:30:00-03:00",  
  "items": [  
    {  
      "event_id": "EVT-10001",  
      "valkimia_transfer_id": "TRF-894470",  
      "valkimia_line_id": "TRF-894470-001",  
      "event_type": "SHIPPED",  
      "event_ts": "2026-03-02T11:20:00-03:00",  
      "payload": {  
        "qty_shipped": 12  
      }  
    }  
  ],  
  "next_since_ts": "2026-03-02T11:20:00-03:00"  
}

### Regla

- `event_id` debe permitir deduplicación.
    
- `next_since_ts` permite paginar/continuar.
    

---

# 6) Códigos de razón (Reason Codes) — estándar

## 6.1 Rechazos por stock

- `NO_NET_STOCK` (sin stock neto)
    
- `RESERVED_BY_ACO` (comprometido por ACO)
    
- `IN_PICKING` (comprometido por picking)
    
- `BLOCKED_QUALITY` (bloqueado)
    

## 6.2 Reglas de negocio

- `BRANCH_BLOCKED`
    
- `SKU_BLOCKED`
    
- `UOM_MISMATCH`
    
- `MIN_TRANSFER_NOT_MET`
    
- `WINDOW_INVALID`
    

## 6.3 Errores técnicos

- `DEPENDENCY_TIMEOUT`
    
- `INTERNAL_EXCEPTION`
    

---

# 7) Políticas de reintento, timeouts y límites

## 7.1 Timeouts sugeridos

- V-01 Stock neto (batch): 10–20s (depende batch)
    
- V-03 Publish: 10s
    
- V-04 Get transfer: 5s
    

## 7.2 Retries (Connexa)

- Reintentar **solo** ante:
    
    - `503 DEPENDENCY_UNAVAILABLE`
        
    - `429 RATE_LIMIT` (con backoff)
        
    - `500` (máx 2 reintentos)
        
- No reintentar ante:
    
    - `400/422` (deben corregirse)
        
    - `REJECTED_STOCK` (esto es negocio, vuelve al backlog)
        

## 7.3 Rate limits sugeridos

- Stock neto: 60 req/min por CD
    
- Active transfers: 30 req/min por CD
    
- Publish: 30 req/min por CD (depende operación)
    

## 7.4 Batch size

- Stock neto: 2.000 SKU por request
    
- Publish lines: 2.000 líneas por ejecución (ideal < 500 por performance)
    

---

# 8) Reglas de consistencia y auditoría (obligatorias)

1. Valkimia debe **persistir** la recepción de `connexa_execution_id` para idempotencia.
    
2. Valkimia debe permitir tracking por `valkimia_transfer_id` aun si la ejecución falla.
    
3. Rechazo por stock **no elimina** la transferencia: queda en estado `REJECTED_STOCK` con evento auditable.
    
4. Connexa registra todo en `transfer_event_log`.
    

---

# 9) Casos de prueba mínimos (UAT) para validar integración

1. Stock neto devuelve 0 y publish responde `REJECTED_STOCK`.
    
2. Publish aceptado, luego pasa a `RESERVED_ACO`, `PICKING`, `SHIPPED`, `DELIVERED`.
    
3. Publish parcial: 1 línea aceptada, 1 rechazada.
    
4. Idempotencia: reenviar mismo `connexa_execution_id` devuelve mismo `valkimia_transfer_id`.
    
5. Anti-duplicación: `active` muestra transferencia existente y Connexa bloquea nueva publicación.
    

---

## Próximo paso recomendado

Con esta especificación, el siguiente artefacto es un **Test Plan de Integración** (matriz de escenarios + datos de prueba + criterios de aceptación), y/o el **diseño del adaptador Valkimia** (interfaces internas + mapeos + retry policies).

Si avanzan, puedo entregar el **Test Plan de Integración v1.0** listo para QA y operación (incluyendo escenarios de convivencia con SGM y casos de rollback).