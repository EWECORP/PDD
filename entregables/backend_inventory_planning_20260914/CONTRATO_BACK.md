# Contrato de mantenimiento y lectura

Versión lógica: **inventory-planning-v1**. Alcance confirmado: parámetros directos por artículo/local, compartidos por PDD y FORECAST. Las fechas de una corrida y su snapshot fijan qué se utilizó; no se agrega un servicio de publicación de reglas por grupo.

## 1. Reposición

Se conserva `inventory.inv_product_site_replenishment`, su PK UUID y UNIQUE `product_site_id`, con FK a `inv_product_site`. Sigue admitiendo una sola fila por par incluyendo inactivas.

| Campo | Tipo final | Obligatorio | Semántica |
|---|---|---|---|
| `target_stock_days` | numeric(10,4) | Sí | Días objetivo; cero explícito válido |
| `overstock_days` | numeric(10,4) | Sí | Días adicionales para necesidad opcional; cero explícito válido |
| `minimum_order_quantity` | numeric(18,4) | Sí | Mínimo por par en unidad base; cero = no impone mínimo |
| `preparation_days` | numeric(10,4) | Sí | Preparación; cero explícito válido |
| `order_multiple` | numeric(18,4) | No | Si se informa, positivo; NULL = no impone múltiplo por par |
| `lead_time_days`, `transit_days` | numeric(10,4) | No | Si se informan, no negativos; NULL = no configurado, no cero |
| `active` | boolean | Sí | Activación del parámetro; no habilita por sí sola la compra/transferencia del par |
| `row_version` | bigint | Sí | Revisión incrementada por trigger; el cliente no la elige |
| `created_at`, `updated_at` | timestamptz | Sí | Tiempos de creación/cambio administrados por trigger |
| `updated_by` | text | Sí | Actor del contexto transaccional autenticado |

Se eliminan los dos nombres antiguos; **no hay alias, compatibilidad ni copia de valores de seguridad**. Se conservan `replenishment_method` y `replenishment_frequency` por compatibilidad con BACK, pero el circuito PDD/FORECAST no los interpreta. La modalidad de abastecimiento sigue en `inv_product_site.supply_type` y el origen en `supplying_site_id`.

`expected_stock_days` se conserva físicamente para otros consumidores existentes. El editor y lectores nuevos sólo mantienen/consumen `target_stock_days`; no hay sincronización bidireccional ni fallback a `expected_stock_days`. Retirar el campo antiguo de todas las aplicaciones es otro cambio que requiere inventariar sus consumidores.

Validar finitud y no negativos en DB/API. Usar BigDecimal y máximo cuatro decimales; **la API debe rechazar exceso de escala antes del INSERT**, porque PostgreSQL puede redondear al asignar a numeric(p,s). La base rechaza NaN/infinito mediante constraints además del rango del tipo. Referencia: [tipos numéricos de PostgreSQL 14](https://www.postgresql.org/docs/14/datatype-numeric.html).

## 2. API/DAO y auditoría

Reutilizar las rutas actuales de BACK; no se impone una API nueva. DTO de escritura: ID de par, ambos días, mínimo, preparación, campos opcionales y activo. En modificación exigir `expected_row_version` o ETag equivalente. No aceptar los nombres retirados como sinónimos de sobrestock.

En cada transacción de mantenimiento ejecutar `SELECT set_config('app.actor', :actor, true)` usando el usuario autenticado o un identificador de servicio de carga. Debe ser la **misma conexión/transacción** que escribe. El trigger rechaza la operación si falta actor, incrementa la revisión y registra antes/después en `inv_planning_parameter_audit`. La identidad del actor se valida en el servicio; un parámetro de sesión no autentica usuarios por sí mismo.

UPDATE/DELETE deben incluir ID + versión esperada y comprobar filas afectadas. Si no coincide, responder conflicto (por ejemplo 409); no sobrescribir con un reintento sin versión. La PK y el par no son editables; para otra identidad hay que crear otra configuración y conservar el historial.

Los triggers funcionan con los permisos del llamador: el rol de mantenimiento necesita INSERT/USAGE de la secuencia de auditoría además de sus permisos de tablas. BACK debe concederlos a **sus roles existentes**, no a PUBLIC. El rol lector sólo necesita SELECT. No habilitar TRUNCATE sobre tablas de configuración al rol de aplicación: el TRUNCATE evita triggers de fila. La auditoría bloquea UPDATE/DELETE/TRUNCATE, incluso sin filas; el rol de migraciones administra la estructura.

Un cambio de producto/local por sincronización puede disparar DELETE CASCADE sobre parámetros; también necesita contexto `app.actor`. Las instantáneas de resultados usan referencias lógicas sin FK a estos maestros para conservar evidencia aunque un maestro se retire.

## 3. Selección logística explícita

Entidad nueva: `inventory.inv_product_planning_logistics`.

- PK `product_id`: una selección por producto para este circuito.
- `logistic_variable_id`: FK compuesta con producto, impide elegir una variable de otro artículo.
- Revisión, actor y auditoría con el mismo contrato de reposición.
- Se preservan las 26.209 variables existentes. No se corrigen los 9.770 productos ambiguos poniendo todas menos una en false, ni se elige MIN(id) o la primera fila.
- El usuario de BACK elige la variable. Puede consultar `inv_planning_logistics_v`, que expone datos y `usable_for_forecast`; una selección inactiva, sin factor positivo finito o sin UOM utilizable no habilita el cálculo.

FORECAST conserva la semántica confirmada: factor desde `purchase_factor`, peso en kg = `weight_in_gr / 1000`, pesable según `uom_id != 'unidad'`; NULL nunca significa pesable automáticamente. Para pesables la vista exige peso positivo y finito. Capas y cajas permanecen como datos que deben validarse cuando se utilicen. La selección no inventa unidades por bulto, pallet ni volumen.

PDD conserva por ahora su `pdd_item_logistics_snapshot` y la fuente logística acordada para él; antes de adoptar la misma selección para redondeo/palletizado debe mapear expresamente units_per_package y validar unidades. El nuevo campo resuelve la elección de variable de FORECAST, no certifica equivalencia de toda logística PDD.

## 4. Lectura y carga inicial

`inv_planning_parameters_v` devuelve como máximo una configuración activa por par. **No es un filtro completo de elegibilidad.** Cada consumidor aplica sus flags, scope y proveedor de ejecución. Leer por LEFT JOIN desde el scope, registrar y rechazar faltantes. Cero sólo es válido si fue configurado explícitamente.

La carga recibe códigos de producto/local y ambos días del negocio, los resuelve en `inventory.inv_product.ext_code` e `inv_site.code`, busca `inv_product_site` y rechaza códigos ausentes, duplicados o pares no válidos. Mantener la revisión y actor. No convertir las 605 reglas DRAFT de T055 automáticamente ni usar su cobertura parcial como carga completa. La plantilla CSV está vacía porque no se acordaron los valores a regenerar.

Fuente congelada por corrida: UUID de parámetro, revisión, ambos días, fecha de lectura y todos los valores efectivamente utilizados. Cambiar un maestro no cambia resultados ya calculados. El servicio debe leer una única fotografía coherente, reutilizarla entre etapas y generar nueva corrida para entradas distintas.

## 5. Snapshot FORECAST

`supply_planning.spl_forecast_planning_input` contiene una fila por resultado del publicador nuevo. FK a la PK del resultado; los UUID de maestros inventory son referencias históricas, deliberadamente sin FK. No se cargan filas retrospectivas con el estado actual de los maestros.

`input_snapshot` debe contener al menos: `contract_version`, códigos/UUID de producto y local, proveedor de ejecución y relación proveedor/producto, mínimo, preparación, lead/transit si se usan, factor de compra y unidad/peso realmente utilizados, UUID/revisión de selección, filtros y fecha/corte de las entradas o referencia a manifiesto inmutable con checksum. Decimales exactos como números manejados por Decimal/BigDecimal o cadenas decimales documentadas, no conversiones a int. La DB verifica objeto JSON; el servicio valida este contenido.

Insertar resultado + snapshot + estado final de ejecución en la misma transacción/publicación controlada. Cada resultado del modo nuevo debe tener snapshot; la adición de una tabla no impide que el publicador viejo siga omitiéndolo. Reintentos con el mismo result_id verifican igualdad de contenido; no usar DO NOTHING para ocultar entradas diferentes. La tabla rechaza UPDATE/DELETE/TRUNCATE y restringe borrar su resultado padre.

## 6. Aceptación mínima de BACK

1. Migraciones en PostgreSQL 14/Flyway y entidades compiladas con los nombres/tipos nuevos.
2. Alta con 15,25 días objetivo, 2,5 días adicionales y 1,25 preparación; lectura sin truncar. Nulos obligatorios, negativos, NaN/infinito y múltiplo cero rechazados.
3. Ediciones concurrentes: la revisión desactualizada no pisa la vigente; actor y antes/después auditados. Cambios de selección también auditados.
4. Elegir una variable entre varias principales sin tocar las otras; variable de otro producto rechazada; elección inutilizable bloquea el consumidor.
5. Carga y lectura del scope completo sin faltantes silenciosos. No activar por tener simplemente cero errores SQL después de una migración vacía.
6. S20 y PDD consumen los mismos días del par. FORECAST conserva proveedor de ejecución y condiciones de esa relación, sin filtrar primary_supplier ni consolidar OC.
7. Reproducción de resultado usando su snapshot aunque se cambien/eliminen parámetros actuales. Nuevo S40 no publica como completa una corrida sin evidencia por línea.
