# Catálogo de valores de clasificación — entrega BACK

**Aplicado por BACK en TEST y verificado en solo lectura el 17/09/2026.** Flyway registra `20260917160001__product_classification_value_catalog.sql` exitosamente. El catálogo contiene las siete opciones de Compra activas; las asignaciones a productos están vacías. Se verificaron FK compuesta, unicidad por tipo/código y controles de vigencia. No volver a ejecutar la migración. Evidencia: [captura posterior](../../documentacion/parametros_stock/clasificaciones_catalogo_aplicado_20260917.json).

El siguiente paso es preparar la sincronización de asignaciones desde T050. La migración no implementa el control de solapamientos ni la validación de valores activos en el servicio; esos aspectos no fueron verificados por esta lectura del catálogo.

## Cambios

- Conserva tipos y productos existentes.
- Borra las asignaciones de prueba de `inv_product_classification`, autorizadas por el usuario. Fuera de `connexa_platform_test` rechaza la operación si hay asignaciones. No usa CASCADE y se detiene si encuentra FKs entrantes o triggers de aplicación sobre las asignaciones.
- Crea `inv_product_classification_value` con código, descripción, tipo y actividad. Código único por tipo; UUID generado por PostgreSQL.
- Reemplaza el texto libre de la asignación por `classification_value_id`. Conserva `classification_type_id` y valida la coherencia mediante FK compuesta, evitando una migración innecesaria de las consultas que usan el tipo.
- Alta de asignaciones activa por defecto, inicio obligatorio con default CURRENT_DATE y fin exclusivo opcional. Permite historial; no impone UNIQUE(producto,tipo), que impediría conservarlo.
- Carga las siete opciones de DIARCO bajo `Clasificación Compra`. Conserva Clasificación Venta sin inventarle opciones. No asigna productos ni sincroniza T050.

La tabla de tipos conserva el campo `value` como nombre del criterio. La migración busca exactamente `Clasificación Compra`: comprobar ese nombre antes de aplicarla si BACK lo renombró. Las cinco asignaciones simuladas conocidas se eliminan; no se interpretan como datos reales ni se migran sus etiquetas.

## Ajustes de BACK

1. Mapear la nueva entidad y sustituir el texto libre en DTO/pantalla por selección de tipo y valor del catálogo. Rechazar nuevas asignaciones a valores inactivos. El catálogo permite texto en code para otros criterios, por ejemplo ABC=A/B/C.
2. Para Compra, mantener una sola asignación efectiva por producto. **El SQL valida referencias y fechas, pero no impide por sí solo intervalos superpuestos.** Implementar en el servicio la comprobación transaccional con serialización por producto, incluyendo todas las rutas de mantenimiento/sincronización. No asumir que el índice de consulta es una restricción temporal. Si el equipo necesita esa garantía también para escrituras SQL externas, acordar una migración adicional de cardinalidad por tipo/exclusión temporal; no imponer unicidad a todos los criterios sin definir si admiten multivalor.
3. Resolver la carga desde `[data-sync].[repl].[T050_ARTICULOS]`: C_ARTICULO → producto por ext_code; C_CLASIFICACION_COMPRA → código del catálogo de Compra. Reintentos idempotentes; otras clasificaciones no se modifican. Código 100 es explícito, no fallback para NULL/desconocidos.
4. Usar valid_from inclusivo y valid_to exclusivo. Los registros con fechas futuras o pasadas no se vuelven vigentes sólo por tener active=true. No activar datos simulados automáticamente: la tabla queda vacía después de migrar.

## Comprobación posterior (SELECT)

```sql
SELECT t.value AS type, v.code, v.description, v.active
FROM inventory.inv_product_classification_value v
JOIN inventory.inv_product_classification_type t ON t.id=v.classification_type_id
ORDER BY t.value, v.code;

SELECT count(*) FROM inventory.inv_product_classification;
```

Esperado: siete valores de Compra y cero asignaciones. La FK debe rechazar asignaciones a valores de otro tipo; el UNIQUE debe rechazar códigos duplicados dentro de un tipo. El mismo código puede existir en tipos distintos. No volver a ejecutar el SQL fuera de Flyway tras aplicarlo.

Validación local reproducible en `validate.mjs`, usando la dependencia PGlite ya instalada en el paquete de nivelación hermano. No depende de credenciales ni se conecta a TEST. No sustituye la validación Flyway/PostgreSQL 14 del pipeline de BACK.
