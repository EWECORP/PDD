# Integración Valkimia por Adaptadores — Fase 1

Versión: **2.1**
Fecha: **2026-07-28**
Estado: **Contrato lógico; validar contra ambiente**

---

## 1. Objetivo

Permitir que Valkimia consulte e importe oportunísticamente backlog Connexa y devuelva ejecución por línea, sin acoplar el dominio a la versión instalada o WEB.

## 2. Dirección funcional

```text
Valkimia -> consulta backlog priorizado en Connexa
Valkimia -> confirma las líneas/cantidades importadas
Valkimia -> informa preparación y estados
Connexa  -> registra, imputa y conserva remanente
```

La Fase 1 no requiere que Connexa empuje una orden de distribución. Si la tecnología instalada obliga a un intercambio inverso, el adaptador debe preservar esta semántica: la selección pertenece al operador/Valkimia y no a un optimizador Connexa.

## 3. Puerto de consulta

```text
searchOpenDistributionNeeds(filter, page, snapshotVersion)
```

Filtros:

- CD, sucursal, proveedor y artículo;
- D/E/C/A/S;
- obligatorio/opcional;
- prioridad e IRQ;
- fecha/SLA;
- peso, volumen, bultos y pallets;
- solo datos logísticos completos, opcional.

Respuesta lógica:

```json
{
  "snapshotVersion": "2026-07-28/CD01/07",
  "asOf": "2026-07-28T06:10:00-03:00",
  "page": 1,
  "totalLines": 1,
  "totals": {"units": 100, "kg": 250, "m3": 1.8, "pallets": 2.4},
  "lines": [{
    "needLineId": "uuid",
    "lineVersion": 4,
    "branchId": "041",
    "itemId": "1234",
    "supplierId": "P01",
    "decas": {"D": 60, "E": 20, "C": 0, "A": 0, "S": 20},
    "mandatoryQuantity": 80,
    "optionalQuantity": 20,
    "openQuantity": 100,
    "irq": 90,
    "priority": 1,
    "targetDate": "2026-07-29",
    "logistics": {"kg": 250, "m3": 1.8, "pallets": 2.4}
  }]
}
```

Los totales son estimaciones; no validan capacidad ni forman una carga.

## 4. Puerto de confirmación de importación

```text
confirmNeedImport(request)
```

```json
{
  "idempotencyKey": "VKM-20260728-000123",
  "snapshotVersion": "2026-07-28/CD01/07",
  "operatorId": "vkm-user",
  "lines": [{
    "needLineId": "uuid",
    "lineVersion": 4,
    "quantity": 80
  }]
}
```

Resultados por línea:

- `ACCEPTED`;
- `ALREADY_ACCEPTED`;
- `STALE_VERSION`;
- `QUANTITY_EXCEEDS_OPEN`;
- `NOT_FOUND`;
- `INVALID`.

Una confirmación aceptada registra intención/importación; no reduce backlog.

## 5. Puerto de ejecución

```text
recordDistributionExecution(event)
```

```json
{
  "eventId": "VKM-EVT-7788",
  "externalDocumentId": "55431",
  "externalLineId": "10",
  "needLineId": "uuid",
  "eventType": "PREPARED",
  "quantityMode": "CUMULATIVE",
  "quantity": 50,
  "externalStatus": "TER",
  "occurredAt": "2026-07-28T15:30:00-03:00",
  "dispatchNote": null,
  "estimatedDeliveryAt": null
}
```

El contrato debe fijar si la cantidad es delta o acumulada. Nunca se infiere.

## 6. Idempotencia y concurrencia

- consulta ligada a `snapshotVersion`;
- cada línea tiene `lineVersion`;
- importación usa `idempotencyKey`;
- ejecución usa `eventId` o clave compuesta estable;
- una versión obsoleta no se acepta silenciosamente;
- locks por clave evitan doble efecto;
- reintentos devuelven el resultado previo;
- los payloads se persisten mediante inbox/outbox.

## 7. Estados

Connexa conserva código original y normaliza:

| Externo candidato | Normalizado inicial |
| --- | --- |
| `GEN` | `IMPORTED` |
| `ACO`, `CUR`, `PRG` | `IN_PROCESS` |
| `REV` | `IN_PROCESS` o alerta, validar |
| `TER` | `PREPARED`, validar |
| `EXP` | `DISPATCHED`, validar |
| `CAR` | `IN_PROCESS`, validar |
| `ANU` | `CANCELLED`, validar efecto |
| `AGR` | `GROUPED`, vincular documento |

Un valor no mapeado se registra como `UNKNOWN_EXTERNAL_STATUS` y no cierra saldo.

## 8. Capacidades observadas

El PDF `Reuniones/Documentacion servicios WMS-VKM_v2.pdf` documenta operaciones candidatas sobre documentos de salida:

```text
getById, getId, listNewDeliveryFinished, inUse,
add, addList, setProcessed, cancel
```

También presenta cantidades requeridas/confirmadas y estados. Esto no confirma:

- disponibilidad en DIARCO;
- autenticación y métodos;
- campo apto para ID Connexa;
- idempotencia;
- semántica de “confirmada”;
- filtros pull desde Connexa;
- límites;
- despacho o recepción.

El adaptador podrá traducir el contrato lógico a REST, base de datos, archivo controlado o mecanismo híbrido, sujeto a certificación.

## 9. Reconciliación

Proceso:

1. leer eventos/documentos cambiados;
2. persistir inbox;
3. deduplicar;
4. validar cantidades;
5. vincular por ID Connexa;
6. registrar evento;
7. imputar preparado;
8. actualizar proyección;
9. confirmar procesamiento externo, si aplica.

Una cantidad acumulada que disminuye genera corrección auditada y alerta; no se sobrescribe.

## 10. Errores y reintentos

| Tipo | Tratamiento |
| --- | --- |
| Dato inválido | rechazar línea, sin reintento automático |
| Versión vencida | refrescar foto y seleccionar nuevamente |
| Timeout de importación | consultar por clave antes de reenviar |
| Evento duplicado | responder éxito previo |
| Referencia desconocida | aislar y alertar |
| Estado desconocido | conservar y alertar |
| Preparado mayor al importado | aislar hasta reconciliar |
| Error transitorio | backoff y límite de intentos |

## 11. Seguridad y observabilidad

- TLS y autenticación acordada;
- secretos en gestor corporativo;
- mínimo privilegio;
- payloads sensibles protegidos;
- correlación punta a punta;
- métricas de consultas, importaciones, eventos, latencia, errores y duplicados;
- alarmas por cola, frescura, referencias huérfanas y estados desconocidos.

## 12. Pruebas de contrato D1–D5

1. conectividad y autenticación;
2. consulta paginada y filtros;
3. totales y datos logísticos ausentes;
4. confirmación parcial;
5. repetición idempotente;
6. versión vencida;
7. preparación parcial;
8. evento duplicado;
9. delta versus acumulado;
10. timeout antes/después de persistir;
11. estados reales;
12. documento agrupado/anulado;
13. límites y rendimiento;
14. caracteres, fechas, decimales y unidades;
15. contingencia por archivo, si fuera necesaria.

La evidencia de estas pruebas cierra el contrato físico.

## 13. Migración WEB futura

Se implementa el mismo puerto estable, se ejecutan las pruebas de contrato y se cambia el adaptador por fecha controlada. La migración no modifica DECAS, backlog, IDs ni reglas funcionales.

## 14. Exclusiones de integración

El adaptador no:

- reserva o asigna stock;
- selecciona automáticamente líneas;
- agrupa por camión;
- crea viajes/rutas;
- calcula capacidad o cubicaje;
- optimiza cargas.

