# Lead time para Entrega desde CD — revisión del 17/09/2026

## Complemento tras actualización del origen

El usuario completó los plazos faltantes en T055. Se tomó una nueva captura y se confirmaron **67.105 actualizaciones adicionales** en TEST. Los **385.983 pares con Entrega desde CD** tienen ahora `lead_time_days` informado; no quedan pendientes de cobertura en ese universo. Los plazos existentes coincidían con la nueva fuente y se conservaron. Los otros métodos siguen sin cambios.

La fuente informa explícitamente plazo cero para **2.355 pares**, valor conservado sin reemplazarlo por otro plazo. Distribución total: 0 días: 2.355; 6: 146.566; 7: 23.608; 10: 8.751; 15: 110.869; 20: 74.208; 25: 19.626.

Evidencia: [resultado complementario](../../data/cargas_inventory/20260917_lead_time_cd0_complemento/result.json) y [verificación posterior](../../data/cargas_inventory/20260917_lead_time_cd0_complemento/verification.json). Los 67.105 pendientes mencionados en las secciones históricas siguientes quedan resueltos.

## Regla confirmada y ejecución posterior

**Estado final: aplicado y verificado en TEST.** COMMIT confirmado: 318.878 filas actualizadas. Verificación posterior: cero diferencias y cero filas adicionales por completar entre los pares con plazo disponible. Los 67.105 pares sin plazo continúan NULL. Los otros tres métodos de reposición conservan sus plazos NULL, sin actualizaciones.

El usuario confirmó que **proveedor 0 representa el plazo general desde CD por sucursal**. El proveedor primario del artículo no interviene. El cargador fue actualizado para usar `t055.c_proveedor=0` y la sucursal, manteniendo el filtro de destino `replenishment_method='Entrega desde CD'`.

La nueva captura resuelve 318.878 pares; 67.105 quedan sin plazo por falta de fila para su sucursal, sin convertirlos a cero. Evidencia de esta ejecución: [resultado](../../data/cargas_inventory/20260917_lead_time_cd0/result.json), [verificación](../../data/cargas_inventory/20260917_lead_time_cd0/verification.json) y [pendientes](../../data/cargas_inventory/20260917_lead_time_cd0/pending.csv). Los archivos de la primera captura se conservan como antecedente; el cargador rechaza capturas sin la nueva regla identificada en el manifest.

## Antecedente: cruce inicial por proveedor primario

Solicitud: completar `inventory.inv_product_site_replenishment.lead_time_days` desde `src.t055_lead_time_b2_sucursales.dias_entrega`, solamente para `replenishment_method = 'Entrega desde CD'`.

**Estado: preview realizado, sin actualización de TEST. Falta aclarar el significado del proveedor 0.**

La tabla de origen tiene 94 filas y todas usan `c_proveedor=0`; no hay duplicados proveedor/sucursal y los plazos informados son 6, 7, 10, 15, 20 y 25 días. El cruce literal con `src.base_productos_vigentes.c_proveedor_primario` y la sucursal no encuentra ninguna coincidencia. Los 385.983 pares de TEST con entrega desde CD siguen con lead time NULL.

Hipótesis pendiente de confirmación: si proveedor 0 es el plazo general desde CD, usarlo por sucursal cubriría **318.878** pares. Otros **67.105** pares pertenecen a sucursales sin fila de plazo, por lo que seguirían pendientes sin un valor inventado. No se aplicó esta hipótesis automáticamente.

Evidencia: [preview del cruce literal](../../data/cargas_inventory/20260917_lead_time/preview.json), [pares pendientes](../../data/cargas_inventory/20260917_lead_time/pending.csv), [cobertura hipotética por proveedor 0](../../data/cargas_inventory/20260917_lead_time/supplier_zero_hypothesis.json).

Se preparó [load_lead_time.py](../../cargas_inventory/load_lead_time.py) con captura, validación, aplicación transaccional y verificación. Implementa por ahora el cruce literal por proveedor primario y sucursal; debe ajustarse si se confirma otra regla. No modifica otros métodos ni asigna cero a plazos ausentes.
