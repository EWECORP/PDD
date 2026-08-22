# PDD — Contrato API de planificación Connexa y ejecución Valkimia

Versión: **1.0**  
Fecha: **2026-08-21**  
Estado: **Contract-first para backend Java**  
OpenAPI: `backend/contracts/pdd-planning-openapi-v1.yaml`

## 1. Propiedad

- El frontend Connexa consume el microservicio Java
  `connexa-platform-stock-management`.
- Persistencia, repositorios y migraciones pertenecen a
  `connexa-platform-lib-model-stockmanagement`.
- Python/Prefect no expone estas operaciones y no atiende comandos
  interactivos.
- El adaptador Valkimia puede comenzar como polling legacy y cambiar luego a
  API sin modificar el dominio de planes y viajes.

Base pública:

```text
/connexa/api/v1/pdd
```

## 2. Identidades

| Identidad | Alcance |
| --- | --- |
| `snapshotVersion` | Foto de backlog consultada |
| `backlogLineUuid` | Grano estable artículo–sucursal–proveedor |
| `dispatchPlanUuid` | Plan creado por Connexa |
| `dispatchTripUuid` | Viaje o carga |
| `dispatchTripLineUuid` | Selección exacta dentro del viaje |
| `valkimiaImportUuid` | Publicación idempotente del viaje |
| `valkimiaImportLineUuid` | Línea exacta publicada |
| `externalReference` | Identificador de cabecera Valkimia |
| `externalLineReference` | Identificador de línea Valkimia |

Los bigint son internos y no forman parte del contrato HTTP ni de la interfaz
legacy.

## 3. Operaciones frontend

| Método | Ruta | operationId | Rol |
| --- | --- | --- | --- |
| GET | `/planning/backlog` | `listPlanningBacklog` | `PDD_VIEWER` |
| GET | `/dispatch-plans` | `listDispatchPlans` | `PDD_VIEWER` |
| POST | `/dispatch-plans` | `createDispatchPlan` | `PDD_PLANNER` |
| GET | `/dispatch-plans/{planUuid}` | `getDispatchPlan` | `PDD_VIEWER` |
| PUT | `/dispatch-plans/{planUuid}` | `replaceDispatchPlan` | `PDD_PLANNER` |
| POST | `/dispatch-plans/{planUuid}/trips` | `createDispatchTrip` | `PDD_PLANNER` |
| PUT | `/dispatch-trips/{tripUuid}` | `replaceDispatchTrip` | `PDD_PLANNER` |
| POST | `/dispatch-trips/{tripUuid}/lines` | `addDispatchTripLines` | `PDD_PLANNER` |
| PUT | `/dispatch-trips/{tripUuid}/lines/{lineUuid}` | `replaceDispatchTripLine` | `PDD_PLANNER` |
| DELETE | `/dispatch-trips/{tripUuid}/lines/{lineUuid}` | `removeDispatchTripLine` | `PDD_PLANNER` |
| POST | `/dispatch-plans/{planUuid}/validate` | `validateDispatchPlan` | `PDD_PLANNER` |
| POST | `/dispatch-plans/{planUuid}/approve` | `approveDispatchPlan` | `PDD_SUPERVISOR` |
| POST | `/dispatch-plans/{planUuid}/cancel` | `cancelDispatchPlan` | `PDD_SUPERVISOR` |
| POST | `/dispatch-trips/{tripUuid}/publish` | `publishDispatchTrip` | `PDD_SUPERVISOR` |
| GET | `/valkimia-imports` | `listValkimiaImports` | `PDD_VIEWER` |
| GET | `/valkimia-imports/{importUuid}` | `getValkimiaImport` | `PDD_VIEWER` |
| POST | `/valkimia-imports/{importUuid}/poll` | `pollValkimiaImport` | `PDD_TECHNICAL` |

## 4. Cabeceras transversales

- `Authorization: Bearer ...`;
- `X-Correlation-Id` opcional y devuelto;
- `Idempotency-Key` obligatorio en crear, aprobar y publicar;
- `If-Match` obligatorio en PUT, DELETE y comandos de estado;
- respuestas de detalle incluyen `ETag`;
- errores usan `application/problem+json`.

## 5. Lectura planificable

`GET /planning/backlog` extiende la proyección de backlog con:

```json
{
  "snapshotVersion": "uuid",
  "items": [
    {
      "backlogLineUuid": "uuid",
      "rowVersion": 7,
      "codigoArticulo": 62047,
      "sucursal": 12,
      "totalOpenQuantity": 100,
      "activePlannedQuantity": 20,
      "activeImportedQuantity": 10,
      "availableToPlanQuantity": 70,
      "estimatedPallets": 1.4,
      "estimatedWeightKg": 420
    }
  ],
  "nextCursor": null
}
```

El cursor contiene snapshot y filtros normalizados. Si cambia la foto, la API
responde 409 `SNAPSHOT_CHANGED`.

## 6. Aprobación

La aprobación recibe las versiones leídas y permite indicar si se acepta un
resultado parcial:

```json
{
  "allowPartialApproval": false,
  "reason": "Plan operativo turno tarde"
}
```

La transacción bloquea y revalida todas las líneas. Posibles errores por línea:

- `BACKLOG_LINE_NOT_FOUND`;
- `SNAPSHOT_CHANGED`;
- `VERSION_CONFLICT`;
- `INSUFFICIENT_AVAILABLE_QUANTITY`;
- `OUT_OF_SCOPE`;
- `LOGISTICS_INCOMPLETE`;
- `CAPACITY_EXCEEDED`;
- `INVALID_STOP`.

## 7. Publicación

`POST /dispatch-trips/{tripUuid}/publish`:

1. verifica viaje `APPROVED`;
2. crea/reutiliza `valkimiaImportUuid`;
3. crea las líneas públicas de importación;
4. genera outbox `OUTBOUND`;
5. devuelve 202 mientras el adaptador procesa.

La publicación produce una importación por viaje cuando la interfaz admite
múltiples destinos, o una por parada/sucursal cuando Valkimia exige una
transferencia por destino. En ambos casos se conserva el mismo
`dispatchTripUuid` y cada línea se publica una sola vez.

La misma idempotency key y mismo hash devuelve la misma publicación. La misma
clave con otro contenido devuelve 409 `IDEMPOTENCY_CONFLICT`.

## 8. Payload lógico hacia Valkimia

El medio inicial es tabla legacy, pero el contenido canónico es:

```json
{
  "connexaExecutionId": "valkimia-import-uuid",
  "connexaTripId": "dispatch-trip-uuid",
  "originCd": 41,
  "plannedDepartureAt": "2026-08-22T08:00:00-03:00",
  "lines": [
    {
      "connexaLineId": "valkimia-import-line-uuid",
      "connexaTripLineId": "dispatch-trip-line-uuid",
      "backlogLineUuid": "backlog-line-uuid",
      "codigoArticulo": 62047,
      "sucursal": 12,
      "uom": "UNIT",
      "requestedQuantity": 48
    }
  ]
}
```

La tabla física puede usar otros nombres, pero debe transportar sin truncar al
menos `connexaExecutionId` y `connexaLineId`.

## 9. Lectura legacy y normalización

Mientras no exista callback/API, un worker consulta la interfaz por nuestros
IDs. Requisitos del adaptador:

- polling cada 2–5 minutos en horario operativo;
- checkpoint durable;
- solapamiento temporal para evitar pérdidas;
- reconciliación completa diaria de importaciones activas;
- catálogo versionado `pdd_valkimia_status_mapping`;
- cantidades acumulativas preferidas;
- evento deduplicado por ID externo o hash estable;
- `UNKNOWN` ante estado no mapeado;
- no aplicar regresiones silenciosas de estado.

Payload canónico leído:

```json
{
  "connexaExecutionId": "uuid",
  "connexaLineId": "uuid",
  "externalReference": "TRF-894470",
  "externalLineReference": "TRF-894470-001",
  "externalStatus": "PREPARADO",
  "acceptedQuantity": 48,
  "preparedQuantity": 36,
  "dispatchedQuantity": 0,
  "deliveredQuantity": 0,
  "externalUpdatedAt": "2026-08-22T10:15:00-03:00"
}
```

## 10. Conciliación

Las proyecciones se actualizan desde eventos, no desde el frontend:

```text
requested >= accepted >= prepared >= dispatched >= delivered
```

Rechazado y cancelado liberan saldo no despachado. Despachado imputa
cumplimiento en `pdd_dispatch_line_allocation` siguiendo la atribución
congelada. Entregado cierra el tránsito.

La reconstrucción diaria del backlog debe preservar compromisos activos. El
guard temporal que impide publicar con importaciones activas debe retirarse
solamente al habilitar esta conciliación.

## 11. Errores adicionales

| HTTP | Código | Uso |
| ---: | --- | --- |
| 409 | `SNAPSHOT_CHANGED` | Foto distinta |
| 409 | `VERSION_CONFLICT` | Agregado modificado |
| 409 | `QUANTITY_ALREADY_RESERVED` | Reserva concurrente |
| 409 | `IDEMPOTENCY_CONFLICT` | Clave reutilizada con otro payload |
| 422 | `INVALID_STATE_TRANSITION` | Acción no permitida |
| 422 | `CAPACITY_EXCEEDED` | Viaje excedido |
| 422 | `LOGISTICS_INCOMPLETE` | Faltan factores obligatorios |
| 422 | `INSUFFICIENT_AVAILABLE_QUANTITY` | Saldo planificable insuficiente |
| 502 | `VALKIMIA_ADAPTER_ERROR` | Interfaz externa inválida |
| 503 | `VALKIMIA_UNAVAILABLE` | Interfaz no disponible |

## 12. Implementación Java

En `connexa-platform-lib-model-stockmanagement`:

- entidades y repositorios `pdd_dispatch_*`;
- proyección de backlog planificable;
- repositorios de reserva, importación, outbox y eventos;
- migración Flyway basada en la v2.7;
- tests PostgreSQL de bloqueo y concurrencia.

En `connexa-platform-stock-management`:

- controllers `PddDispatchPlanController`, `PddDispatchTripController` y
  `PddValkimiaImportController`;
- casos de uso y servicios transaccionales;
- autorización, ETag, idempotencia y problem details;
- adaptador legacy detrás de un puerto `ValkimiaExecutionPort`;
- scheduler/poller independiente del request HTTP;
- métricas, auditoría y reintentos.

El detalle físico de la interfaz queda pendiente del DDL y muestras reales de
la tabla Valkimia. No debe codificarse SQL contra esa tabla antes de ratificar
nombres, claves, estados y semántica de cantidades.
