# Solicitud al BACK Java — Catálogo de tipos de vehículo

Versión: **1.0**  
Fecha: **2026-08-24**  
Destino: `connexa-platform-stock-management` y
`connexa-platform-lib-model-stockmanagement`  
Base: `connexa_platform_diarco` en DESA; luego TEST y PROD  
Esquema: `stock_management`

## 1. Objetivo

Incorporar un catálogo canónico de tipos de vehículo para que el planificador
seleccione un tipo al crear o editar un viaje y Connexa pueda controlar el
cubicaje simultáneamente por:

- carga útil máxima en kilogramos;
- volumen útil máximo en metros cúbicos;
- posiciones equivalentes de pallet.

El catálogo pertenece a Stock Management. No debe almacenarse en
`diarco_data`, porque es una configuración operacional administrada por
Connexa y consumida durante la planificación.

## 2. Migración solicitada

Aplicar como una **nueva migración Flyway** el archivo:

`PDD - Migracion Catalogo Tipos Vehiculo v3.0.sql`

No modificar migraciones ya ejecutadas. La migración:

1. crea `stock_management.pdd_vehicle_type`;
2. agrega a `pdd_dispatch_trip` la FK nullable `vehicle_type_id`;
3. agrega snapshots de código y versión del catálogo;
4. conserva los campos existentes `vehicle_type`, `max_weight_kg`,
   `max_volume_m3` y `max_pallets` como snapshots del viaje;
5. no altera ni invalida viajes históricos.

La migración no debe sembrar los valores leídos de una captura de pantalla.
La carga inicial requiere un extracto autoritativo de Valkimia y confirmación
de unidades.

Si el microservicio accede mediante `connexa_pdd_api`, aplicar además
`PDD - Grants Catalogo Tipos Vehiculo v1.0.sql`. El rol recibe lectura, alta y
modificación, pero no borrado físico.

## 3. Modelo Java

En `connexa-platform-lib-model-stockmanagement` incorporar la entidad de
dominio y persistencia `PddVehicleType`, con estos conceptos:

| Campo | Semántica |
| --- | --- |
| `vehicleTypeUuid` | Identidad pública de API |
| `vehicleTypeCode` | Código canónico estable de Connexa |
| `description` | Descripción visible al planificador |
| `valkimiaTypeCode` | Código equivalente en Valkimia, si existe |
| `maxPayloadWeightKg` | Carga útil máxima en kg |
| `maxVolumeM3` | Volumen útil máximo en m³ |
| `maxPallets` | Posiciones equivalentes de pallet |
| `active` | Vigencia administrativa |
| `plannable` | Habilitación para seleccionar en viajes nuevos |
| `displayOrder` | Orden opcional en la UI |
| `rowVersion` | Control optimista de concurrencia |

Actualizar `PddDispatchTrip` con la relación nullable y los nuevos campos
snapshot. La relación no debe usar cascada de borrado.

## 4. Reglas obligatorias del servicio

### 4.1 Administración del catálogo

- No permitir borrado físico de tipos utilizados: desactivar con
  `is_active=false` e `is_plannable=false`.
- Un código canónico no cambia después de ser utilizado.
- `valkimia_type_code`, cuando se informa, debe ser único.
- Capacidad cero no significa desconocida: debe rechazarse. Un dato todavía no
  confirmado se persiste como `NULL`.
- Sólo puede marcarse `is_plannable=true` cuando el tipo está activo y las tres
  capacidades son positivas.
- Toda modificación incrementa `row_version`, `updated_at` y `updated_by`.

### 4.2 Creación o modificación de un viaje

El frontend envía `vehicleTypeUuid`; no envía capacidades autoritativas. El
BACK debe:

1. resolver el registro por UUID;
2. verificar `is_active=true` e `is_plannable=true`;
3. copiar dentro del viaje, en una misma transacción:
   - `vehicle_type_id`;
   - `vehicle_type_code`;
   - `vehicle_type` = descripción;
   - `vehicle_type_catalog_row_version`;
   - `max_weight_kg`;
   - `max_volume_m3`;
   - `max_pallets`;
4. recalcular los porcentajes/alertas de ocupación usando los snapshots.

Una edición posterior del catálogo no debe cambiar automáticamente los viajes
ya creados. Para adoptar la nueva capacidad, el usuario debe volver a aplicar
el tipo al viaje mediante una operación explícita y auditable.

### 4.3 Errores esperados

| Caso | HTTP | Código funcional sugerido |
| --- | ---: | --- |
| UUID inexistente | 404 | `VEHICLE_TYPE_NOT_FOUND` |
| Tipo inactivo o no planificable | 422 | `VEHICLE_TYPE_NOT_PLANNABLE` |
| Capacidades incompletas | 422 | `VEHICLE_TYPE_CAPACITY_INCOMPLETE` |
| Código duplicado | 409 | `VEHICLE_TYPE_CODE_ALREADY_EXISTS` |
| Versión concurrente obsoleta | 409 | `VEHICLE_TYPE_VERSION_CONFLICT` |

## 5. API a incorporar

Mantener el prefijo y convenciones de la API de Stock Management.

### Consulta para planificación

La base vigente del contrato es `/connexa/api/v1/pdd`. Agregar sobre ella:

`GET /vehicle-types?active=true&plannable=true`

Respuesta mínima por elemento:

```json
{
  "vehicleTypeUuid": "uuid",
  "vehicleTypeCode": "SEMI_24P",
  "description": "SEMI 24 P",
  "valkimiaTypeCode": "101",
  "maxPayloadWeightKg": 24000,
  "maxVolumeM3": 87,
  "maxPallets": 21,
  "active": true,
  "plannable": true,
  "rowVersion": 1
}
```

### Administración

- `POST /vehicle-types`
- `PUT /vehicle-types/{vehicleTypeUuid}`
- `POST /vehicle-types/{vehicleTypeUuid}/deactivate`
- `POST /vehicle-types/{vehicleTypeUuid}/activate`

Los planificadores requieren lectura. Alta, modificación y cambio de vigencia
deben quedar restringidos a supervisores/administradores y registrar un evento
de negocio PDD.

Actualizar `backend/contracts/pdd-planning-openapi-v1.yaml`: el request de
alta/edición de viaje debe incorporar `vehicleTypeUuid`. `vehicleType` puede
permanecer en la respuesta como descripción congelada. El BACK debe ignorar o
rechazar capacidades recibidas desde el navegador para evitar que el cliente
altere límites operativos.

## 6. Carga inicial

Antes de cargar datos, obtener desde Valkimia:

- código y descripción;
- carga útil y unidad de medida;
- volumen útil y unidad de medida;
- capacidad de pallets y definición del pallet equivalente;
- vigencia actual;
- tipos no configurables por sí solos, como tractor o chasis;
- fecha de extracción y responsable de validación.

Los valores cero del legado deben transformarse en `NULL` y el tipo debe quedar
`is_plannable=false` hasta ser confirmado. No utilizar la imagen de referencia
como fuente maestra.

Para permitir el desarrollo anticipado en DESA se entrega por separado
`PDD - Seed DESA Tipos Vehiculo Simulados v1.0.sql`. Sus filas están marcadas
con `attributes.data_status=SIMULATED_DESA`, son idempotentes y el script
rechaza su ejecución fuera de `connexa_platform_diarco`. Deben reemplazarse o
regularizarse cuando exista el extracto autoritativo.

## 7. Compatibilidad y transición

- Los viajes históricos con `vehicle_type_id IS NULL` continúan siendo
  consultables.
- Desde la habilitación funcional, el servicio Java debe exigir
  `vehicleTypeUuid` para viajes nuevos.
- Después de revisar y, si corresponde, mapear viajes abiertos, podrá
  planificarse una migración posterior que haga obligatoria la FK. No hacerlo
  en v3.0.
- `ON DELETE RESTRICT` impide eliminar un catálogo referenciado.

## 8. Aceptación

Se considera terminado cuando:

1. la migración v3.0 se aplica con Flyway sin alterar checksums históricos;
2. se aplican los grants del catálogo al rol de API;
3. el SQL `PDD - Validacion Catalogo Tipos Vehiculo v3.0.sql` no detecta
   inconsistencias;
4. el frontend lista únicamente tipos activos y planificables;
5. crear/editar un viaje copia las capacidades en el snapshot;
6. cambiar el catálogo no modifica viajes existentes;
7. desactivar un tipo impide nuevas selecciones sin romper consultas
   históricas;
8. existen pruebas Java de concurrencia, duplicados, capacidades incompletas,
   snapshot y desactivación.
