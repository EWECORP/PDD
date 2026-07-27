# Modelo de Datos Conceptual — Necesidades de Distribución

Versión: **2.0**
Fecha: **2026-07-24**
Estado: **Base conceptual; modelo físico pendiente de decisiones de arquitectura**

---

## 1. Objetivo

Definir el modelo que soporta la Fase 1 sin heredar estructuras de convivencia con SGM ni anticipar entidades propias de optimización logística.

El modelo debe representar:

- fotos diarias de cálculo;
- necesidad regular vigente;
- excepciones persistentes;
- consolidado ofrecido a Valkimia;
- cantidades y estados informados;
- pipeline y backlog;
- transferencias intersucursal;
- auditoría e integración.

---

## 2. Decisiones de diseño

1. **Histórico y vigente separados.** Las corridas son inmutables; una proyección/vista identifica la foto vigente.
2. **Necesidad y oferta separadas.** Una necesidad puede alimentar varias ofertas y una oferta puede consolidar varias fuentes.
3. **Excepciones con identidad.** No se recrean cada día.
4. **Tracking por línea.** Las cantidades se registran por artículo.
5. **Estado externo conservado.** Se almacena el valor Valkimia y su normalización.
6. **Sin convivencia.** No existen `external_execution` ni entidades de absorción SGM.
7. **Carga inicial explícita.** Los pendientes del corte se identifican con lote de migración.
8. **Intersucursal separada.** No se modela como oferta del CD.
9. **Eventos append-only.** Ningún cambio sensible queda sin auditoría.
10. **Adaptadores desacoplados.** El dominio no almacena estructuras específicas de una API salvo en mensajes técnicos.

---

## 3. Mapa de entidades

```text
CalculationRun
  ├── CalculationSourceSnapshot
  └── RegularNeedSnapshot ─────────────┐
                                      │
ExceptionNeed ── ExceptionNeedLine ────┼── NeedSourceAllocation
                                      │          │
                                      v          v
                              DistributionOffer ── DistributionOfferLine
                                                        │
                                                        v
                                              OfferExternalReference
                                                        │
                                                        v
                                                OfferStatusEvent

BranchTransferRequest ── BranchTransferLine ── BranchTransferEvent

Todas las entidades ──> BusinessEventLog
Integraciones ────────> IntegrationMessage
Configuración ────────> ConfigurationVersion
Carga inicial ────────> MigrationBatch
```

---

## 4. Cálculo diario

### 4.1 `calculation_run`

| Campo | Descripción |
| --- | --- |
| `calculation_run_id` | UUID |
| `business_date` | Fecha operativa |
| `scope_type`, `scope_id` | Universo calculado |
| `formula_version` | Versión de regla |
| `status` | `STARTED`, `VALIDATING`, `CALCULATING`, `COMPLETED`, `FAILED`, `SUPERSEDED` |
| `is_current` | Indicador de versión vigente del ámbito |
| `started_at`, `finished_at` | Timestamps |
| `created_by` | Proceso/usuario |
| `summary` | Conteos y totales controlados |

Restricción: solo una corrida `is_current=true` por `business_date + scope`.

### 4.2 `calculation_source_snapshot`

Registra:

- fuente;
- lote;
- `as_of_ts`;
- obligatorio/opcional;
- estado de calidad;
- cantidad de registros;
- checksum o control;
- mensaje de degradación.

### 4.3 `regular_need_snapshot`

Grano:

```text
calculation_run + CD + sucursal + artículo
```

Campos:

- demanda/horizonte;
- stock sucursal;
- inbound válido;
- compromisos;
- stock proyectado;
- stock objetivo;
- necesidad bruta;
- pipeline descontado;
- necesidad abierta;
- stock CD de referencia;
- cantidad ofertable;
- múltiplo;
- alertas;
- explicación serializada/versionada.

Esta tabla es histórica. No se actualiza cuando llega un estado Valkimia.

### 4.4 `current_distribution_need`

Puede implementarse como vista o proyección materializada.

Combina:

- último `regular_need_snapshot`;
- excepciones activas;
- ofertas activas;
- cantidades preparadas;
- intersucursales activas;
- backlog y alertas.

Es la fuente principal del panel, no un segundo registro maestro.

---

## 5. Excepciones

### 5.1 `exception_need`

Cabecera común:

- `exception_need_id`;
- tipo: `SPECIAL_SALE`, `COMMERCIAL_AGREEMENT`, `STOCKPILE`;
- referencia;
- proveedor opcional;
- inicio/fin;
- SLA;
- prioridad;
- política `ADDITIVE`, `MINIMUM_GUARANTEE`, `REPLACE`;
- estado;
- creador/aprobador;
- timestamps;
- motivo/observación.

### 5.2 `exception_need_line`

Grano:

```text
exception_need + sucursal + artículo
```

Cantidades:

- requerida;
- imputada como preparada;
- recibida, si aplica;
- cancelada;
- backlog.

Debe soportar materialización masiva de un acuerdo, manteniendo la referencia común.

### 5.3 `exception_need_version`

Recomendado para cambios sensibles:

- versión;
- valores;
- vigencia;
- usuario;
- motivo;
- aprobación.

---

## 6. Oferta y ejecución Valkimia

### 6.1 `distribution_offer`

Cabecera de lote:

- `distribution_offer_id`;
- referencia externa estable;
- fecha operativa;
- CD;
- adaptador;
- estado técnico/funcional;
- creación/publicación;
- correlación;
- cantidad de líneas y total;
- usuario/proceso.

### 6.2 `distribution_offer_line`

Grano:

```text
oferta + sucursal + artículo + unidad
```

Campos:

- `offer_line_id`;
- fecha objetivo;
- prioridad informativa;
- cantidad ofrecida;
- cantidad confirmada/preparada acumulada;
- cantidad despachada/recibida cuando exista;
- estado normalizado;
- última actualización;
- error/motivo.

### 6.3 `need_source_allocation`

Explica qué fuentes forman una línea:

| Campo | Uso |
| --- | --- |
| `offer_line_id` | Línea consolidada |
| `source_type` | `REGULAR_SNAPSHOT` o `EXCEPTION_LINE` |
| `source_id` | Entidad de origen |
| `qty_contributed` | Cantidad aportada |
| `qty_prepared_allocated` | Preparado imputado |
| `allocation_order` | Orden determinístico |
| `rule_version` | Regla aplicada |

No representa asignación de SND entre sucursales. Solo descompone e imputa el resultado de una línea ya preparada.

### 6.4 `offer_external_reference`

Campos:

- oferta/línea;
- sistema/version/adaptador;
- documento externo;
- línea externa;
- tipo/operación;
- referencia enviada;
- fecha de vínculo;
- estado de validación.

Unicidades:

- sistema + documento externo;
- adaptador + referencia enviada.

### 6.5 `offer_status_event`

Evento inmutable:

- documento/línea;
- estado externo;
- estado normalizado;
- cantidades;
- fecha del evento externo;
- fecha de recepción;
- payload/referencia técnica;
- versión de mapping.

El estado actual se deriva del último evento válido, no reemplaza la historia.

---

## 7. Transferencia intersucursal

### 7.1 `branch_transfer_request`

Cabecera:

- ID;
- referencia;
- sucursal origen/destino;
- fecha requerida;
- motivo;
- prioridad;
- estado;
- solicitante/aprobador;
- responsable logístico;
- timestamps.

### 7.2 `branch_transfer_line`

- artículo;
- cantidad solicitada;
- aprobada;
- preparada;
- despachada;
- recibida;
- cancelada;
- stock origen al solicitar/aprobar;
- stock protegido;
- alertas.

### 7.3 `branch_transfer_event`

Timeline de aprobación y ejecución. Puede resolverse con `business_event_log` si se garantiza el detalle.

---

## 8. Datos transversales

### 8.1 `business_event_log`

- `event_id`;
- entidad/tipo/ID;
- evento;
- estado anterior/nuevo;
- actor/sistema;
- fecha;
- correlación;
- motivo;
- payload funcional.

Append-only a nivel funcional.

### 8.2 `integration_message`

- mensaje/correlación;
- adaptador/operación;
- dirección;
- referencia funcional;
- intento;
- request/response protegidos;
- estado HTTP/técnico;
- inicio/fin;
- próximo reintento;
- clasificación del error.

### 8.3 `configuration_version`

Versiona:

- fórmula;
- políticas de excepción;
- mappings;
- polling;
- alertas;
- imputación;
- múltiplos;
- calendario;
- permisos funcionales.

### 8.4 `migration_batch`

- lote;
- fecha de corte;
- origen;
- conteos/totales;
- estado;
- aprobación;
- reporte de conciliación.

Los registros migrados guardan `migration_batch_id`. El origen histórico SGM no habilita nuevas cargas.

---

## 9. Saldos y fórmulas

### Necesidad regular abierta

```text
regular_open_qty =
  max(gross_regular_need - valid_inbound_pipeline, 0)
```

El pipeline incluido debe identificarse para no descontarlo dos veces.

### Backlog de excepción

```text
exception_backlog_qty =
  max(requested_qty - prepared_or_fulfilled_allocated - cancelled_qty, 0)
```

### Saldo de oferta

```text
offer_open_qty =
  max(offered_qty - prepared_qty - cancelled_or_rejected_qty, 0)
```

Estos saldos tienen propósitos diferentes y no deben sumarse sin conocer sus vínculos.

---

## 10. Índices y controles recomendados

Índices:

- necesidades por comprador/proveedor/sucursal/artículo;
- corrida por fecha/ámbito/vigente;
- excepción por tipo/estado/vigencia/SLA;
- oferta por referencia/estado/fecha;
- documento externo;
- eventos por entidad/fecha;
- intersucursal por origen/destino/estado/SLA;
- mensajes por correlación/estado/reintento.

Controles:

- cantidades no negativas;
- confirmada no superior a ofrecida sin evento de corrección;
- una referencia externa funcional;
- no crear oferta con mapping maestro inválido;
- no aceptar fuente SGM posterior al corte;
- no aprobar intersucursal origen=destino;
- no modificar snapshots históricos;
- no borrar eventos.

---

## 11. Privacidad, retención y seguridad

- Payloads técnicos deben enmascarar credenciales y datos sensibles.
- Auditoría y mensajes tendrán políticas de retención distintas.
- Los permisos de datos deberán respetar ámbito de comprador/proveedor cuando aplique.
- Las correcciones se registran como nuevos eventos, no sobrescritura silenciosa.
- La carga inicial y cambios de parámetros requieren controles reforzados.

---

## 12. Evolución a Fase 2

El modelo podrá extenderse con:

- `net_stock_snapshot`;
- `allocation_run`;
- `allocation_line`;
- `reservation`;
- `load_plan`;
- `trip`;
- `vehicle_capacity`;
- `route`;
- `optimization_scenario`.

Estas entidades no deben implementarse anticipadamente dentro de Need u Offer. La separación evita que la Fase 1 quede acoplada al futuro algoritmo.

---

## 13. Pendientes para modelo físico

- motor de base de datos y esquema;
- volumen/retención;
- particionado de snapshots y eventos;
- estrategia de vista vigente;
- transacciones de publicación;
- outbox/inbox;
- locking de referencia;
- granularidad exacta de unidad de medida;
- fuente de recepciones;
- catálogo de estados validado;
- requisitos corporativos de seguridad.

