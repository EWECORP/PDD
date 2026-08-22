# Solicitud al equipo BACK — Corrección del contrato de estados Valkimia

Versión: **1.0**  
Fecha: **2026-08-21**  
Clasificación del cambio: **Corrección de contrato y persistencia**  
Entorno relevado: **DESA — `connexa_platform_diarco`**  
Esquema: **`stock_management`**

## 1. Objetivo

Solicitar al equipo BACK la alineación completa del modelo de estados de la
integración Connexa–Valkimia. El catálogo incorporado por el equipo es una
mejora válida y debe conservarse, pero la implementación actual dejó contratos
inconsistentes entre la línea de importación, el mapping externo y el historial
de eventos.

La corrección debe realizarse antes de:

- habilitar el adaptador de escritura hacia Valkimia;
- cargar los mappings de estados externos;
- activar el polling de estados;
- promover la funcionalidad a TEST.

## 2. Evidencia verificada en DESA

La inspección de solo lectura del catálogo PostgreSQL confirmó las siguientes
migraciones Flyway aplicadas satisfactoriamente:

| Versión | Script |
| --- | --- |
| `20260820180000` | `V20260820180000__add_valkimia_import_line_status_table.sql` |
| `20260821085718` | `V20260821085718__drop_normalized_status_column.sql` |
| `20260821140000` | `V20260821140000__create_pdd_dispatch_planning_v27.sql` |

También se confirmó:

- `pdd_valkimia_import_line_status` existe y contiene 10 estados;
- `pdd_valkimia_import_line.status_id` es `NOT NULL` y FK al catálogo;
- `pdd_valkimia_status_mapping.status_id` es `NOT NULL` y FK al catálogo;
- `pdd_valkimia_import_line` ya no contiene `normalized_status`;
- las FK están validadas y utilizan `ON DELETE RESTRICT`;
- no existe un índice específico sobre `pdd_valkimia_import_line.status_id`;
- `pdd_execution_event` todavía conserva `normalized_status` textual;
- las tablas de importación, mapping y eventos todavía no contienen datos.

Estados cargados:

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

## 3. Defecto bloqueante

La restricción vigente de `pdd_execution_event.normalized_status` sólo admite:

```text
IMPORTED
PARTIAL
PREPARED
DISPATCHED
CANCELLED
DELIVERED
UNKNOWN
```

No admite:

```text
ACCEPTED
REJECTED
FAILED
```

Cuando el adaptador intente registrar un evento con cualquiera de esos tres
estados, PostgreSQL rechazará el `INSERT`. El defecto todavía no se manifestó
porque `pdd_execution_event` y `pdd_valkimia_status_mapping` están vacías.

## 4. Decisión de diseño solicitada

Se aprueba conservar el catálogo relacional. El modelo físico objetivo es:

```text
pdd_valkimia_import_line.status_id
  └─► pdd_valkimia_import_line_status.id

pdd_valkimia_status_mapping.status_id
  └─► pdd_valkimia_import_line_status.id

pdd_execution_event.status_id
  └─► pdd_valkimia_import_line_status.id
```

`last_external_status` continúa almacenando el código recibido de Valkimia. El
estado normalizado se obtiene desde el catálogo.

El API debe exponer el código simbólico —por ejemplo `PREPARED`— y no el ID
numérico interno.

## 5. Correcciones obligatorias

### 5.1 Nueva migración Flyway

No modificar ni renombrar ninguna migración ya aplicada. Debe crearse una nueva
migración, con versión posterior a `20260821140000`, por ejemplo:

```text
V<timestamp>__align_pdd_valkimia_status_contract.sql
```

La migración debe ser transaccional, repetible en una base equivalente y debe
fallar ante cualquier dato no convertible.

### 5.2 Alinear `pdd_execution_event`

Agregar `status_id` y relacionarlo con el catálogo. La migración debe soportar
datos preexistentes:

1. agregar `status_id` inicialmente nullable;
2. completarlo relacionando
   `pdd_execution_event.normalized_status = pdd_valkimia_import_line_status.name`;
3. abortar si queda algún evento sin correspondencia;
4. crear la FK con `ON DELETE RESTRICT`;
5. declarar `status_id NOT NULL`;
6. adaptar el código Java para escribir y leer la relación;
7. retirar `normalized_status` en la misma migración, después del backfill y la
   validación. Se confirmó que todavía no existe ningún Java que lo utilice.

### 5.3 Alinear los tipos de evento

Los checks de `event_type` de estas dos tablas deben usar el mismo catálogo
funcional:

- `pdd_execution_event`;
- `pdd_valkimia_status_mapping`.

Valores requeridos:

```text
IMPORTED
ACCEPTED
PREPARED
DISPATCHED
DELIVERED
CANCELLED
REJECTED
FAILED
CORRECTED
UNKNOWN
```

`PARTIAL` es un estado de la línea; la parcialidad también debe quedar expresada
por las cantidades acumuladas. Si el equipo decide utilizar además un evento
`PARTIAL`, debe incorporarlo de forma consistente en ambas tablas y documentar
su semántica.

### 5.4 Índice operativo

Agregar como mínimo:

```sql
CREATE INDEX ix_pdd_valkimia_import_line_status_updated
    ON stock_management.pdd_valkimia_import_line
       (status_id, last_updated_at);
```

La FK no crea automáticamente un índice sobre la columna referenciante. Este
acceso será utilizado por seguimiento, conciliación y monitoreo.

### 5.5 Integridad del catálogo

Conservar `UNIQUE(name)` y agregar una validación equivalente a:

```sql
CHECK (
    name = upper(name)
    AND name ~ '^[A-Z][A-Z0-9_]*$'
)
```

Los diez códigos son parte del contrato y no deben renombrarse ni eliminarse.
`ON DELETE RESTRICT` debe mantenerse.

### 5.6 Terminalidad

`is_terminal` es propiedad del estado normalizado y no del código externo. Debe
incorporarse en `pdd_valkimia_import_line_status`.

| Estado | `is_terminal` |
| --- | ---: |
| `IMPORTED` | false |
| `ACCEPTED` | false |
| `PARTIAL` | false |
| `PREPARED` | false |
| `DISPATCHED` | false |
| `DELIVERED` | true |
| `CANCELLED` | true |
| `REJECTED` | true |
| `FAILED` | true |
| `UNKNOWN` | false |

`pdd_valkimia_status_mapping.is_terminal` debe eliminarse después de adaptar el
código, o al menos dejar de ser la fuente de verdad. No deben existir dos
mappings hacia el mismo estado normalizado con distinta terminalidad.

`quantity_semantics` e `is_active` sí pertenecen al mapping externo y deben
permanecer allí.

## 6. Cambios requeridos en Java

El módulo Java Stock Management debe incorporar:

1. entidad/repositorio de `pdd_valkimia_import_line_status`;
2. relación obligatoria desde la línea de importación;
3. relación obligatoria desde el mapping;
4. relación obligatoria desde el evento de ejecución;
5. búsqueda del estado por `name`, sin IDs numéricos hardcodeados;
6. proyección del `name` como `status`/`normalizedStatus` en el API;
7. control optimista mediante `row_version` al actualizar una línea;
8. validación de progresión de estados y cantidades;
9. fallback explícito a `UNKNOWN` cuando no exista mapping;
10. alerta para todo código externo no mapeado.

El ID del catálogo es una identidad física. No forma parte del contrato público
ni debe aparecer en payloads de frontend o Valkimia.

## 7. Reglas mínimas de transición

La FK valida pertenencia al catálogo, pero no valida transiciones. El servicio
debe impedir regresiones silenciosas y modificaciones de estados terminales.

Reglas mínimas:

- un estado terminal no puede volver a uno operativo;
- `DELIVERED` no puede disminuir cantidades despachadas o entregadas;
- `CANCELLED` y `REJECTED` liberan únicamente el saldo no despachado;
- `FAILED` requiere detalle técnico y no debe marcar cumplimiento;
- `UNKNOWN` no libera, no despacha y no cumple cantidades;
- una observación más antigua no puede reemplazar una más reciente;
- una corrección debe generar un evento `CORRECTED`, no sobrescribir historia;
- el procesamiento repetido del mismo evento debe ser idempotente.

La progresión cuantitativa debe conservar:

```text
imported_quantity
  >= accepted_quantity
    >= prepared_quantity
      >= dispatched_quantity
        >= delivered_quantity
```

Además:

```text
cancelled_quantity + rejected_quantity <= imported_quantity
```

## 8. Mapping externo

`pdd_valkimia_status_mapping` está vacío en DESA. No deben inventarse códigos de
Valkimia para completar la tabla.

La carga se realizará cuando se obtenga:

- DDL de la tabla legacy;
- catálogo real de estados;
- ejemplos de cada transición;
- semántica de cantidades delta o acumuladas;
- timestamp o versión confiable para polling;
- mecanismo de ACK o confirmación.

Hasta entonces, un código sin mapping debe producir `UNKNOWN`, evento auditable
y alerta operativa.

## 9. Permisos

La migración debe revisar los roles efectivos del ambiente. Como mínimo:

- el usuario de la aplicación Java necesita `SELECT` sobre el catálogo;
- el proceso de conciliación necesita `SELECT/INSERT/UPDATE` sobre mapping,
  importaciones, líneas, eventos y checkpoints según su responsabilidad;
- el frontend no debe modificar el catálogo directamente;
- no se deben conceder permisos generales sobre todas las tablas del esquema.

## 10. Pruebas obligatorias

### 10.1 Persistencia

- insertar una línea con cada uno de los diez estados;
- comprobar rechazo de un `status_id` inexistente;
- comprobar rechazo al borrar un estado referenciado;
- comprobar unicidad de `name`;
- comprobar rechazo de códigos en minúsculas;
- registrar eventos `ACCEPTED`, `REJECTED` y `FAILED` sin error;
- comprobar que el mapping retorna el estado normalizado esperado.

### 10.2 Transiciones

- flujo completo `IMPORTED → ACCEPTED → PREPARED → DISPATCHED → DELIVERED`;
- aceptación y preparación parciales;
- rechazo total y parcial;
- cancelación antes y después de preparación;
- código externo desconocido;
- evento repetido;
- evento atrasado;
- intento de regresión desde un estado terminal;
- conflicto de `row_version`.

### 10.3 Regresión

- `pdd_valkimia_import` continúa usando su estado agregado propio;
- la API sigue devolviendo códigos textuales;
- la publicación de un viaje mantiene idempotencia;
- el backlog conserva las reservas activas;
- rechazo/cancelación libera sólo el saldo correspondiente;
- despacho imputa DECAS y genera tránsito;
- entrega cierra el tránsito.

## 11. Criterios de aceptación

La corrección se considera terminada cuando:

1. Flyway valida sin modificar checksums históricos;
2. las tres FK al catálogo existen y están validadas;
3. ningún evento conserva un estado fuera del catálogo;
4. `ACCEPTED`, `REJECTED` y `FAILED` pueden registrarse;
5. existe índice sobre `pdd_valkimia_import_line.status_id`;
6. terminalidad tiene una única fuente de verdad;
7. las pruebas Java unitarias e integración pasan;
8. el OpenAPI no expone IDs internos de estados;
9. el smoke test SQL se ejecuta con rollback y pasa;
10. el resultado se valida primero en DESA y luego en TEST.

## 12. Entregables solicitados

El equipo BACK debe entregar:

- nueva migración Flyway correctiva;
- scripts Flyway anteriores publicados en el repositorio canónico;
- entidades, repositorios y servicios Java actualizados;
- pruebas unitarias e integración;
- evidencia de `flyway validate` y `flyway migrate` en DESA;
- resultado del smoke test;
- actualización del contrato OpenAPI si cambia algún payload;
- nota breve de compatibilidad para la promoción a TEST.

No debe promoverse el adaptador Valkimia mientras el defecto de
`pdd_execution_event` permanezca abierto.

## 13. SQL de referencia entregado

Se adjuntan dos archivos para que el equipo BACK los revise, asigne nombres
Flyway definitivos e incorpore al repositorio canónico:

1. `PDD - Migracion Correctiva Estados Valkimia v2.8.sql`;
2. `PDD - Validacion Correctiva Estados Valkimia v2.8.sql`.

La migración deja directamente el modelo físico final porque se confirmó que
todavía no existe ningún binario Java que dependa de `normalized_status`.
