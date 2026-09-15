# Auditoría de las entidades de inventory en TEST

Fecha: **2026-09-14**. Base comprobada: **connexa_platform_test**, PostgreSQL **14.24**.
Captura: **12:47:30 UTC / 09:47:30 Argentina**. Estado: **integración de maestros parcial; no habilitada como fuente PDD**.

## 1. Dictamen y alcance

La decisión comunicada por BACK de reutilizar `inventory` es compatible con PDD. No hace falta crear `replenishment`. Las entidades principales del DDL de maestros se reconocen en tablas `inventory.inv_*`, con reutilización de maestros y FKs. **No son una copia equivalente del DDL propuesto ni implementan todavía todo el contrato de políticas de stock de PDD.**

Se contrastaron dos entregas distintas:

1. El antecedente [DDL de maestros v1.0](../../../ETL_DIARCO/scripts/datamart/ddl_Connexa_Core_Master_Data.sql): producto, local, surtido, proveedores, logística, reposición, comercial, auditoría y outbox.
2. El [paquete de políticas versionadas del 11/09](../../entregables/backend_stock_policy_flyway/CONTRATO_ENTIDADES.md), incluidas migraciones 01–03 y diseño de publicación: reglas por local/grupo, familia/rubro opcionales, clasificación, días objetivo y sobrestock.

La primera familia está integrada parcialmente en `inventory`. La segunda **continúa como borrador en `supply_planning`**: no se encontraron sus equivalentes en `inventory`. Trasladar los maestros no demuestra que se hayan trasladado las reglas versionadas.

Se ejecutaron exclusivamente consultas SELECT a catálogo, agregados de calidad, claves de negocio para discrepancias e historial Flyway de inventory. La conexión exigió `transaction_read_only=on`, aislamiento `repeatable read`, validación del nombre de base y rollback al cerrar. No se ejecutaron migraciones, DDL, DML, validadores que escriben con rollback ni llamadas a rutinas. No se consultaron filas de tablas externas, Producción ni diarco_data. Sólo se modificó documentación y utilidades locales de relevamiento.

## 2. Dónde quedaron las entidades solicitadas

Los conteos son exactos a la captura. Las equivalencias funcionales parciales necesitan contrato del consumidor; no autorizan sustituir tablas en el código.

| Entidad propuesta | Ubicación comprobada | Filas | Evaluación |
|---|---|---:|---|
| `master_data.product` | `inventory.inv_product` | 18.272 | Maestro reutilizado; categoría y marca normalizadas mediante FK. `ext_code` es UNIQUE pero nullable; actualmente no faltan códigos. 1.696 productos sin categoría. |
| Categorías y marcas del producto | `inventory.inv_category`, `inv_brand`, `inv_manufacturer` | 2.689 categorías | Jerarquía por `parent_id`; la normalización es válida. Definir traducción a familia/rubro, sin asumir un nivel por nombre. |
| `master_data.product_barcode` | `inventory.inv_barcode` | 24.586 | FK a producto y catálogos de tipo/UOM, barcode único. Barcode admite NULL; cambió el contrato respecto del NOT NULL original. |
| `master_data.product_classification` | `inventory.inv_product_classification` + `inv_product_classification_type` | 0 + 0 | Buena separación del tipo; falta carga y garantía de una clasificación efectiva inequívoca. `active` default false, distinto del original. |
| `master_data.site` | `inventory.inv_site` | 188 | `code` obligatorio y único, `type` obligatorio. No están `region_code`, `region_name` ni `active` del original; zona/formato no son atributos explícitos aquí. |
| `master_data.product_site` | `inventory.inv_product_site` | 1.013.500 | UNIQUE producto/local y FKs correctas. Conserva flags, origen de suministro, capacidades y vigencias. `active_on_mix` se reconoce como candidato a `active_on_assortment`; confirmar semántica. |
| `master_data.site_cluster` | Sin equivalente exacto | — | Candidatos: `inventory.inv_set_of_site` (5 grupos), `inv_set_of_site_line` (171 miembros), o `supply_planning.spl_supply_cluster` (14). No declarar equivalencia automática. |
| `master_data.product_site_assortment` | `inventory.inv_product_site_assortment` | 0 | Tiene FK a producto/local, rol, obligatoriedad y fechas. Faltan `site_cluster_id` y `active`; no tiene unicidad ni CHECK de vigencia. |
| `supplier.supplier` | `inventory.inv_supplier` | 15.933 | Maestro existente con códigos/estado y tablas auxiliares normalizadas. |
| `supplier.supplier_product` | `inventory.inv_product_supplier` | 21.969 | UNIQUE producto/proveedor; incorpora lead time, mínimo, múltiplo y factor. `min_purchase_qty` se llama `minimum_purchase_quantity`. No se hallaron productos con varios proveedores primarios activos, pero no hay garantía estructural para impedirlo. |
| `logistics.product_logistics` | `inventory.inv_logistic_variable` | 26.209 | Integración parcial en una entidad con nivel y jerarquía propios. `box_units` → candidato `units_per_box`; `pallet_units` → `units_per_pallet`. Falta `transfer_factor` y vigencia. Requiere resolver grano y unidades. |
| `replenishment.product_site_replenishment` | `inventory.inv_product_site_replenishment` | 852 | FK correcta y UNIQUE producto/local. Configuración actual, sin versión, vigencia ni algoritmo/parámetros de forecast del antecedente. |
| `commercial.product_commercial_policy` | `inventory.inv_product_commercial_policy` | 0 | Política única por producto, sin vigencias ni actualización/actor; `promotional_enabled` default false frente a true del original. |
| `audit.product_master_audit_log` | Sin equivalente identificable en el catálogo relevado | — | La tabla de auditoría de precios de procurement y la de chat de nexa no prueban auditoría de estos maestros. Pedir evidencia del mecanismo de BACK. |
| `integration.product_master_outbox` | Sin equivalente identificable en el catálogo relevado | — | Pedir ubicación/contrato del mecanismo de eventos si BACK lo resuelve fuera de estas tablas. |

Los `id` de estos maestros son principalmente **UUID**, y varios no tienen default: debe proporcionarlos el backend/sincronizador. No aplicarles la regla de IDs bigint identity del diccionario de tablas operativas `pdd_*`.

## 3. Reposición por producto/local: bien definido y pendiente

### Garantías presentes

- PK UUID con `gen_random_uuid()`.
- `product_site_id NOT NULL`, FK a `inventory.inv_product_site(id)` y UNIQUE por ese campo.
- `inv_product_site` garantiza UNIQUE `(product_id,site_id)` y FKs a los maestros de inventory.
- `active NOT NULL DEFAULT true`, `created_at NOT NULL DEFAULT now()`.
- Índices por producto/local y activo. No hay restricciones NOT VALID en inventory/supply_planning.

Esto permite **como máximo una configuración por par**, contando también las inactivas. No permite un historial de configuraciones por par. La FK tiene `ON DELETE CASCADE`: borrar el par elimina su configuración. Es una decisión de ciclo de vida que BACK debe compatibilizar con la conservación histórica del cálculo.

### Diferencias funcionales

| Aspecto | Estado observado | Consecuencia |
|---|---|---|
| Días objetivo | `target_coverage_days double precision NULL` | No equivale aún a un contrato de parámetro obligatorio y exacto para PDD. |
| Seguridad | `safety_stock_days double precision NULL` | No significa sobrestock opcional. |
| Sobrestock PDD | No existe `overstock_days` ni equivalente explícito en esta tabla | No se pueden obtener ambos parámetros D/S solamente de ella. |
| Cantidades y plazos | Float8 nullable; `minimum_order_quantity`, `order_multiple`, lead/preparación/tránsito | Sin CHECK de no negativos, positivos o finitud. No rechaza por estructura valores inválidos. |
| Método/frecuencia | Varchar sin FK ni CHECK de catálogo | No se puede interpretar sus códigos sólo con el nombre. |
| Vigencia/versión | No hay `valid_from`, `valid_to`, versión ni regla de origen | `active` no permite reconstruir una política histórica. |
| Forecast | Sin `forecast_algorithm_code` ni `forecast_parameters` | Diferencia respecto del antecedente. Puede ser correcta si el modelo queda en `pdd_pdvb_model_version`; no exigir duplicación sin decisión funcional. |
| Auditoría | Sólo fecha de creación sin zona; sin actualización/actor | No demuestra quién cambió un parámetro ni sus valores anteriores. |

### Datos comprobados

- 852 filas activas, 852 pares, distribuidos en 100 locales; esto **no certifica cobertura del scope CD41**. El total de pares inventory es 1.013.500 y no equivale al universo PDD.
- Días objetivo entre 0 y 90; seguridad entre 0 y 3.
- Ningún NULL en objetivo, seguridad, lead time o múltiplo; ningún negativo en los parámetros verificados, ningún múltiplo no positivo, ningún NaN o infinito. Es calidad de esta muestra, no una garantía para futuras escrituras.
- 241 configuraciones activas corresponden a pares `inv_product_site.active=false`. Definir la elegibilidad conjunta.
- Método/frecuencia observados: `0/25` (125 filas), `1/25` (454), `3/25` (271), `./.` (2). No inferir que 25 significa días ni que `.` sea un valor válido.
- Hay tres discrepancias con el otro campo de cobertura:

| Local | Artículo | `expected_stock_days` | `target_coverage_days` | `safety_stock_days` |
|---|---|---:|---:|---:|
| 11 | 10166 | 70 | 71 | 0 |
| 23 | 1 | 25 | 1 | 1 |
| 33 | 1 | 18 | 4 | 3 |

BACK debe definir el maestro y la precedencia. No corregir por promedio, fecha o copia automática.

## 4. Políticas por local/grupo: no trasladadas a inventory

Permanecen en `supply_planning`:

| Tabla | Filas | Estado |
|---|---:|---|
| `spl_stock_policy_version` | 1 | DRAFT, versión `46271d2f-0d1e-4bcc-ae68-6c6f964cb447`, sin fechas de publicación |
| `spl_stock_purchase_classification` | 4 | Catálogo de compra de la carga T055 |
| `spl_stock_policy_rule` | 605 | Ambos días no negativos, local XOR grupo, familia obligatoria |
| `spl_stock_policy_import_row` | 627 | 605 MAPPED y 22 EXCLUDED_CLOSED; 0 PENDING |

No hay diferencias de días entre importación y regla, cruces de versión efectivos ni rubros con padre incorrecto en las 605 reglas. **Sin embargo, sigue faltando la FK compuesta que impediría futuros cruces de versión.**

No está reflejada la migración 02 entregada: familia sigue NOT NULL, no están los CHECK de categorías opcionales ni la FK compuesta importación/regla. No está reflejada la migración 03: no hay `domain`, `validation`, `validation_issue`, `audit`, `request`, ni revisión y campos de publicación de versión. Las entidades de soporte tampoco aparecen bajo nombres `inv_stock_policy_*`.

Estas diferencias se verifican por estructura, no ejecutando Flyway. El historial `inventory.flyway_schema_history` tiene 23 entradas, todas exitosas, última versión `20260902121500`; registra creación/refactor de maestros el 31/08. No se inspeccionó el repositorio Java ni se ejecutó `flyway validate`; no se certifican checksums de los archivos de BACK ni su implementación de servicios.

Si la decisión de inventory incluye también las políticas por grupo, BACK debe adaptar y migrar el contrato completo allí. Si sólo incluye los maestros, debe confirmar explícitamente la permanencia de las políticas en supply_planning y su integración. **No ejecutar directamente los SQL antiguos como si ya representaran la decisión actual.**

## 5. Otras brechas relevantes para la integración

### Logística

Las 26.209 variables están en nivel `1 / Unit`; 26.208 son activas y principales. Hay **9.770 combinaciones producto/nivel con más de una variable principal activa**. Esto no determina por sí solo que los registros sean erróneos: demuestra que `product_id + nivel + principal` no selecciona una única entrada para PDD. BACK debe definir si intervienen barcode, UOM u otra dimensión.

Las 26.208 principales activas carecen de `units_per_box` positivo; 2.388 no tienen `purchase_factor` positivo. Todas las variables tienen `units>0`, pero **no se certificó que `units` sea unidades por bulto**. No sustituir campos por intuición. El lector PDD usa `pdd_item_logistics_snapshot.units_per_package`, no directamente esta tabla.

### Mínimos, máximos y vigencias

Los 1.013.500 pares tienen `min_stock_units=1` y `max_stock_units=0`. Si máximo cero significa «sin límite», debe documentarse esa convención; un CHECK genérico `max>=min` rechazaría toda la carga. No tratarlo como un millón de errores sin esa definición. Hay 89.231 pares con local abastecedor igual al local; validar por tipo de suministro, sin declarar inválido todo autoabastecimiento.

Las tablas de producto, producto/local, clasificación, surtido y producto/proveedor tienen fechas pero carecen de los CHECK de orden de vigencia del antecedente. No se detectaron fechas invertidas en los agregados ejecutados sobre producto, producto/local y surtido; no se auditó toda regla temporal de negocio. Clasificación carece además de garantía de valor efectivo único por producto/tipo.

### Identidades entre esquemas

De 188 locales inventory, 187 coinciden por código con supply_planning y tienen el mismo UUID. De 2.689 categorías, 2.688 coinciden por código; **cuatro tienen UUID distintos**. Sus códigos son:

- `10-2700-5327-5353-5428`
- `2-5130-5403-5427`
- `3-2054-2139-2226-5429`
- `4-3548-3556-5426`

Los UUID concretos están en la evidencia JSON. Esto impide asumir identidad universal entre maestros. No se comprobó impacto de esas cuatro categorías dentro del scope CD41 ni se propone igualar UUID existentes.

## 6. Estado de PDD y documentación operativa

`daily_decas.py::_read_source_stock` continúa leyendo `src.base_stock_sucursal.q_dias_stock` y `q_dias_sobre_stock`. Guarda los valores en `stock_management.pdd_branch_stock_position`. No consulta `inventory.inv_product_site_replenishment` ni `spl_stock_policy_rule` para resolver esos días. La logística del cálculo se lee desde `stock_management.pdd_item_logistics_snapshot`.

El catálogo conserva las entidades operativas `stock_management.pdd_*`, incluidas planificación/viajes. Integrar maestros en inventory **no traslada DECAS, backlog, corridas o viajes fuera de stock_management**, ni cambia la capa analítica en diarco_data. Esta auditoría verifica su ubicación y el consumidor relevante; no vuelve a certificar todas las columnas y reglas del contrato operativo v2.7.

Respecto de la captura del 11/09, las columnas, restricciones e índices de inventory son iguales. El cambio comprobado en reposición es de **contenido: 0 → 852 filas**. Los cuatro objetos nuevos del catálogo general son las tablas del borrador supply_planning ya documentadas en el informe 06. No atribuir a una migración reciente de BACK cambios que la comparación no muestra.

## 7. Condiciones de aceptación y solicitudes

Ver [08_solicitudes_BACK_inventory_test.md](08_solicitudes_BACK_inventory_test.md), con evidencia, prioridad y criterios verificables. Estado: **pedido preparado para revisión/envío; no enviado por herramientas ni aplicado**.

Antes de activar inventory como fuente PDD se necesita: contrato de días objetivo/sobrestock y precedencia; ubicación definitiva de políticas versionadas; clasificación y cobertura del scope; resolver de logística inequívoco; trazabilidad de versión/regla y garantía de publicación. La ausencia de servicios en este repositorio no prueba que BACK no los tenga: corresponde solicitar contrato, código o pruebas de aceptación.

## 8. Evidencia y reproducción

- [catalogo_test_inventory_20260914.json](catalogo_test_inventory_20260914.json): 1.051 objetos, 11.767 columnas, 3.359 restricciones y 1.542 índices; incluye particiones y tablas externas, no son 1.051 entidades independientes.
- [09_diccionario_inventory_test_20260914.md](09_diccionario_inventory_test_20260914.md): diccionario focalizado de maestros y políticas, tipos exactos, nulabilidad, defaults, FKs e índices.
- [auditar_test_inventory.py](auditar_test_inventory.py) y [consultas_auditoria_inventory.py](consultas_auditoria_inventory.py): extractor y SELECT de diagnóstico.

```powershell
python PDD/documentacion/parametros_stock/auditar_test_inventory.py
```

Usa las variables PGP_TEST_* existentes en backend/.env, sin imprimir credenciales. El nombre de archivo corresponde a esta auditoría: una reproducción reemplaza esa evidencia local; para otra fecha conservar una nueva captura fechada. No se almacenan cuerpos de rutinas, datos de contactos ni filas de tablas externas. El catálogo refleja la visibilidad del usuario de conexión. No se verificaron APIs, pantallas, permisos de aplicación ni servicios externos de auditoría/publicación.
