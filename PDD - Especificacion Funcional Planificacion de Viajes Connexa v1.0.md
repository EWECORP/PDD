# PDD — Especificación funcional de planificación y cubicaje de viajes en Connexa

Versión: **1.0**  
Fecha: **2026-08-21**  
Estado: **Aprobada para diseño frontend y backend Java**  
Decisión rectora: `PDD - ADR-003 Planificacion de Viajes en Connexa.md`

## 1. Objetivo

Entregar al planificador del CD 41 una pantalla Connexa para seleccionar saldo
DECAS, formar viajes, controlar capacidad y publicar a Valkimia solamente las
líneas aprobadas para preparación y despacho.

```text
Backlog vigente -> Plan borrador -> Viajes -> Validación -> Aprobación
       -> Publicación legacy/API -> Preparación Valkimia -> Despacho -> Conciliación
```

La pantalla no modifica el cálculo PDVB ni las fórmulas DECAS. Opera sobre la
foto vigente publicada por PDD.

## 2. Usuarios y permisos

| Rol | Capacidad |
| --- | --- |
| `PDD_VIEWER` | Consultar backlog, planes y viajes |
| `PDD_PLANNER` | Crear y editar borradores, líneas, paradas y capacidad |
| `PDD_SUPERVISOR` | Validar, aprobar, cancelar y publicar |
| `PDD_AUDITOR` | Consultar versiones, eventos y payloads |
| `PDD_TECHNICAL` | Reintentar mensajes, ejecutar polling y resolver `UNKNOWN` |

El actor siempre surge del JWT. No se acepta un usuario funcional enviado por
el navegador.

## 3. Pantalla principal

### 3.1 Cabecera

Mostrar siempre:

- fecha de negocio;
- `snapshotVersion` del backlog;
- fecha/hora de publicación;
- fecha del stock CD utilizado;
- estado de frescura;
- plan abierto, planificador y versión;
- indicador de actualización más reciente disponible.

Si cambia el snapshot, la UI informa el cambio y recarga. No mezcla líneas de
dos snapshots.

### 3.2 Panel izquierdo: backlog seleccionable

Filtros:

- sucursal, zona y ruta;
- artículo, descripción, familia, rubro y proveedor;
- D/E/C/A/S, obligatorio u opcional;
- IRQ, prioridad y fecha objetivo;
- con/sin stock CD suficiente;
- datos logísticos completos/incompletos;
- bulto o pallet completo;
- texto libre.

Columnas mínimas:

- sucursal, artículo, descripción y proveedor;
- D/E/C/A/S;
- obligatorio, opcional y total abierto;
- planificado e importado activo;
- disponible para planificar;
- stock CD de referencia;
- IRQ, prioridad, antigüedad y fecha objetivo;
- bultos, pallets, kg, m3;
- alertas, `rowVersion` y acción de detalle.

Orden inicial:

```text
obligatorio primero,
priorityScore DESC,
irqScore DESC,
targetDate NULLS LAST,
oldestNeedDate,
sucursal,
codigoArticulo
```

### 3.3 Panel central: selección

Funciones:

- agregar una o varias líneas;
- editar cantidad parcial;
- completar a bulto o pallet con confirmación;
- excluir cantidades opcionales;
- dividir una necesidad entre viajes;
- mover líneas entre viajes;
- quitar líneas de un borrador;
- consultar explicación y atribución DECAS;
- mostrar rechazos de validación sin perder el resto del trabajo.

El borrador no consume saldo firme. La aprobación vuelve a validar y reserva.

### 3.4 Panel derecho: viajes y cubicaje

Cada viaje permite informar:

- código y número;
- fecha/ventana de salida;
- vehículo, tipo y transportista de referencia;
- capacidad máxima de kg, pallets y m3;
- ruta;
- sucursales/paradas y secuencia;
- observaciones.

Indicadores:

```text
Peso     = sum(estimatedWeightKg) / maxWeightKg
Pallets  = sum(estimatedPallets)  / maxPallets
Volumen  = sum(estimatedVolumeM3) / maxVolumeM3
```

Un indicador se muestra como `SIN DATOS` si alguna línea carece del factor
necesario. El volumen no bloquea la primera entrega mientras la fuente canónica
no exista; peso y pallets sí deben quedar visibles.

La v1 permite múltiples paradas, pero una línea pertenece a una sola parada.
Si la interfaz Valkimia exige una transferencia por sucursal, la publicación
divide el viaje conservando `dispatchTripUuid` como correlación común.

## 4. Estados

### 4.1 Plan

```text
DRAFT -> VALIDATED -> APPROVED -> PARTIALLY_PUBLISHED -> PUBLISHED
                                                \-> IN_EXECUTION -> COMPLETED
DRAFT/VALIDATED/APPROVED -------------------------------> CANCELLED
```

### 4.2 Viaje

```text
DRAFT -> READY -> APPROVED -> PUBLISH_PENDING -> PUBLISHED
       -> ACCEPTED/PARTIAL -> PREPARING -> PREPARED -> DISPATCHED -> DELIVERED
```

Salidas excepcionales: `REJECTED`, `FAILED`, `UNKNOWN`, `CANCELLED`.

### 4.3 Línea

```text
DRAFT -> RESERVED -> PUBLISH_PENDING -> PUBLISHED -> ACCEPTED
       -> PARTIAL/PREPARED -> DISPATCHED -> DELIVERED
```

Salidas excepcionales: `REJECTED`, `FAILED`, `UNKNOWN`, `CANCELLED`.

## 5. Reglas de selección y reserva

1. La referencia es `backlogLineUuid + backlogLineVersion + snapshotVersion`.
2. La cantidad debe ser mayor que cero y no superar
   `availableToPlanQuantity`.
3. `INCOMPLETE` es seleccionable solamente con advertencia y permiso de
   supervisor; las alertas no se ocultan.
4. Al aprobar se bloquean las filas de backlog involucradas, se vuelve a
   calcular disponibilidad y se persiste todo en una transacción.
5. Una versión vencida devuelve 409 `VERSION_CONFLICT` por línea.
6. Las líneas válidas pueden aprobarse aunque otras fallen, únicamente si el
   usuario confirma una aprobación parcial.
7. En `APPROVED`, la selección queda firme y ya no puede entrar en otro plan.
8. Publicar mueve la reserva de `activePlannedQuantity` a
   `activeImportedQuantity`; no suma ambos estados.
9. La atribución queda congelada en orden: E vencida, E, C, D, A, S.
10. D/E/C son obligatorias; A/S son opcionales y pueden recortarse primero.

## 6. Validaciones al aprobar

- plan y viaje en estado permitido;
- snapshot y versiones vigentes;
- artículo–sucursal dentro del scope;
- sucursal no excluida;
- cantidades y UOM válidas;
- una parada compatible con la sucursal de cada línea;
- no exceder saldo planificable;
- no exceder stock neto Connexa de referencia sin autorización explícita;
- capacidad informada y alertas de sobrecarga;
- bultos/pallets coherentes;
- no duplicar la misma línea en un viaje;
- checksum de entrada reproducible.

Valkimia realiza la validación final de stock operativo. Un rechazo nunca
elimina la necesidad.

## 7. Publicación

Solamente un viaje aprobado puede publicar. En la misma transacción Connexa:

1. genera `pdd_valkimia_import`;
2. genera una línea por `pdd_dispatch_trip_line`;
3. calcula `payload_checksum`;
4. crea un mensaje `OUTBOUND` en `pdd_integration_message`;
5. registra evento de negocio y correlación.

El adaptador escribe luego la interfaz legacy. Un reintento con la misma
idempotency key devuelve la misma importación y no duplica registros.

## 8. Conciliación Valkimia

El adaptador consulta los estados externos y crea eventos deduplicados.
Cantidades recomendadas: acumulativas por línea.

| Evento | Efecto Connexa |
| --- | --- |
| Aceptada | conserva reserva |
| Rechazada | libera cantidad rechazada |
| Preparada | informa avance; todavía no cumple |
| Despachada | imputa cumplimiento DECAS y pasa a tránsito |
| Cancelada | libera saldo no despachado |
| Entregada | cierra tránsito y ejecución |
| Desconocida | pone en cuarentena, no modifica cantidades |

El estado no puede retroceder salvo `CORRECTED` auditado.

## 9. Concurrencia

- GET de agregados devuelve `ETag`;
- mutaciones requieren `If-Match`;
- `rowVersion` aumenta en cada modificación;
- aprobación y publicación requieren `Idempotency-Key`;
- la UI conserva cambios locales ante conflicto y muestra las líneas afectadas;
- dos planificadores nunca pueden reservar la misma cantidad firme.

## 10. Pantallas complementarias

### Monitor de publicaciones Valkimia

- plan/viaje/importación;
- estado de outbox;
- referencia externa;
- solicitado, aceptado, preparado, despachado y entregado;
- última consulta y última modificación externa;
- errores y reintentos.

### Detalle del viaje

- cabecera, paradas y capacidad;
- líneas y atribuciones DECAS;
- vínculo al backlog original;
- importaciones generadas;
- timeline de eventos;
- payload enviado y estado externo.

## 11. Métricas iniciales

- backlog disponible vs reservado;
- ocupación por peso, pallets y volumen;
- porcentaje obligatorio/opcional por viaje;
- aceptación Valkimia;
- fill rate preparado y despachado;
- rechazo por falta de stock;
- tiempo aprobación–publicación–preparación–despacho;
- selecciones liberadas o canceladas;
- mensajes en retry/dead-letter;
- estados externos desconocidos.

## 12. Criterios de aceptación

1. Dos sesiones no pueden aprobar la misma cantidad.
2. Un snapshot cambiado no se confirma silenciosamente.
3. Todo viaje aprobado conserva sus líneas y atribuciones históricas.
4. Reintentar publicación no duplica la interfaz.
5. Un rechazo parcial libera únicamente el remanente rechazado.
6. Preparar no descuenta el backlog; despachar sí.
7. Una cancelación nunca reduce cantidad ya despachada.
8. Los totales del viaje concilian con sus líneas.
9. Los totales de importación concilian con viaje e interfaz.
10. Todo cambio tiene actor, correlation ID, timestamp y evento.
11. La pantalla funciona con aproximadamente 15.000 líneas usando paginación
    y filtros en servidor.
12. Valkimia recibe exclusivamente viajes aprobados, nunca el backlog completo.
