# PDD — Integración Valkimia por adaptadores

Versión: **2.2**  
Fecha: **2026-08-21**  
Estado: **Contrato lógico aprobado; mapping físico legacy pendiente**

## 1. Decisión

Connexa selecciona backlog, forma/cubica viajes y publica solamente viajes
aprobados. Valkimia valida stock operativo, prepara y despacha. El dominio no
depende del transporte: el primer adaptador usa tabla legacy y una versión
futura podrá usar APIs.

```text
Connexa Plan/Viaje
   -> ValkimiaExecutionPort
      -> LegacyTableAdapter (inicial)
      -> ValkimiaApiAdapter  (futuro)
```

## 2. Puerto de publicación

```text
publishApprovedTrip(valkimiaImportUuid)
```

Precondiciones:

- viaje `APPROVED`;
- líneas y atribuciones congeladas;
- cantidades reservadas;
- importación e import lines persistidas;
- mensaje outbox `OUTBOUND` pendiente;
- idempotency key y checksum disponibles.

El adaptador escribe únicamente el payload persistido. No vuelve a consultar
el backlog para reconstruirlo.

## 3. Identificadores obligatorios

| Campo lógico | Uso |
| --- | --- |
| `connexaExecutionId` | UUID de `pdd_valkimia_import` |
| `connexaLineId` | UUID de `pdd_valkimia_import_line` |
| `connexaTripId` | UUID de viaje |
| `connexaTripLineId` | UUID de línea de viaje |
| `backlogLineUuid` | Trazabilidad de necesidad |

El match nunca se hace sólo por artículo/sucursal. Valkimia devuelve sus IDs
en `externalReference` y `externalLineReference`.

## 4. Outbound legacy

El adaptador debe:

1. tomar mensajes `PENDING/RETRY` de `pdd_integration_message`;
2. bloquear el mensaje durante el intento;
3. insertar/upsert idempotentemente mediante `connexaLineId`;
4. guardar referencia de payload y hash;
5. marcar `PROCESSED` o programar `RETRY` con backoff;
6. enviar a dead-letter después del máximo configurable.

Un timeout ambiguo obliga a consultar la tabla por ID antes de reinsertar.

## 5. Inbound polling

```text
pollActiveExecutions(checkpoint)
```

Frecuencia recomendada: cada 2–5 minutos durante el horario operativo y una
reconciliación completa diaria.

Algoritmo:

1. obtener importaciones activas;
2. leer la tabla legacy por `connexaExecutionId/connexaLineId`;
3. aplicar cursor con solapamiento temporal;
4. conservar código y timestamp externos;
5. mapear mediante `pdd_valkimia_status_mapping`;
6. crear `pdd_execution_event` deduplicado;
7. actualizar proyección de línea/importación/viaje;
8. liberar rechazado/cancelado o imputar despachado;
9. avanzar `pdd_integration_checkpoint` sólo después del commit.

## 6. Cantidades

Se prefieren acumulativas:

```text
requested >= accepted >= prepared >= dispatched >= delivered
```

La tabla externa debe declarar si informa delta o acumulado. No se infiere. Una
disminución acumulativa genera `CORRECTED`, alerta y auditoría.

## 7. Estados

El mapping físico se cargará después de relevar la tabla. Estados normalizados:

```text
IMPORTED
ACCEPTED
PARTIAL
PREPARED
DISPATCHED
DELIVERED
CANCELLED
REJECTED
FAILED
UNKNOWN
```

Un código no mapeado queda `UNKNOWN`; no libera ni cumple cantidades.

## 8. Conciliación funcional

| Observación Valkimia | Acción Connexa |
| --- | --- |
| Aceptación | conserva reserva |
| Aceptación parcial | libera rechazado |
| Preparación | actualiza avance |
| Despacho | imputa DECAS y crea tránsito |
| Cancelación | libera no despachado |
| Entrega | cierra tránsito |
| Falla técnica | reintenta sin duplicar |
| Estado desconocido | aísla y alerta |

La necesidad permanece visible hasta despacho. Valkimia nunca elimina backlog
Connexa.

## 9. Observabilidad

- mensajes pendientes/retry/dead-letter;
- antigüedad del checkpoint;
- importaciones sin ACK;
- estados desconocidos;
- referencias huérfanas;
- cantidades inconsistentes;
- latencia publicación–aceptación–preparación–despacho;
- reconciliación completa y diferencias.

## 10. Datos pendientes para el adaptador físico

Antes de codificar SQL contra Valkimia se requiere:

1. DDL de tabla de interfaz de entrada y estado;
2. PK y restricciones únicas;
3. ejemplos de aceptación, parcial, preparado, despacho, cancelación y error;
4. catálogo de códigos;
5. semántica de cantidades;
6. timestamp/version de modificación confiable;
7. mecanismo de confirmación de lectura;
8. transacciones y aislamiento disponibles;
9. límites, SLA y retención;
10. estrategia para registros históricos existentes.

## 11. Pruebas de contrato

- publicación total y parcial;
- reintento antes/después de persistir;
- idempotencia por línea;
- polling repetido;
- evento duplicado;
- estado desconocido;
- cantidad acumulada decreciente;
- preparado mayor que aceptado;
- despacho parcial y cancelación de remanente;
- checkpoint sin pérdida ante rollback;
- reconciliación completa;
- sustitución del adaptador legacy por uno API sin cambiar el dominio.
