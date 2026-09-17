# Verificación posterior a los cambios de BACK — 17/09/2026

> **Revisión posterior del mismo día:** BACK ya creó `spl_forecast_planning_input` y se verificó la migración 03. El pendiente estructural de FORECAST descrito debajo está **cerrado**. Ver [estado actual y clasificaciones](11_estado_y_clasificaciones_TEST_20260917.md). Se conservan aquí las observaciones de la captura previa sobre fuentes/carga y consumidores.

**Dictamen: el modelo de inventory está listo para preparar la carga; todavía no está listo el circuito completo de cálculo/publicación.** Se comprobaron los cambios estructurales, pero falta poblar parámetros y selecciones, corregir lectores y completar la evidencia de FORECAST. Hay faltantes reales en los datos de origen que no deben convertirse silenciosamente en cero.

Se consultaron `connexa_platform_test` y las fuentes indicadas de `diarco_data` en transacciones READ ONLY / REPEATABLE READ. No se ejecutaron INSERT, UPDATE, DELETE, migraciones, reset ni pruebas de escritura con rollback. No se alteraron lectores Python. La revisión de triggers fue de catálogo/código; no certifica permisos ni funcionamiento del servicio Java/API.

## 1. Qué quedó aplicado correctamente

En el historial Flyway de inventory figuran exitosas:

- `20260914150001__normalize_product_site_replenishment`, aplicada el 17/09.
- `20260914150002__explicit_planning_logistics`, aplicada el 17/09.

| Componente | Comprobación real | Estado |
|---|---|---|
| `inv_product_site_replenishment` | 0 filas; ya no están `target_coverage_days` ni `safety_stock_days` | Correcto para iniciar carga nueva |
| Ambos días | `target_stock_days`, `overstock_days`: numeric(10,4), NOT NULL, finitos y no negativos | Correcto |
| Mínimo y preparación | `minimum_order_quantity` numeric(18,4) y `preparation_days` numeric(10,4), ambos NOT NULL | Correcto; deben venir completos de la carga |
| Múltiplo y plazos opcionales | Tipos numeric; múltiplo positivo si se informa, plazos no negativos/finítos | Correcto |
| Identidad | PK UUID, UNIQUE product_site_id y FK a producto/local | Correcto; una configuración por par |
| Revisión/actor | row_version, updated_at, updated_by y triggers stamp/audit habilitados | Correcto por inspección |
| `inv_planning_parameter_audit` | 0 filas; ID bigint identity; trigger contra UPDATE/DELETE/TRUNCATE | Correcto por inspección |
| `inv_product_planning_logistics` | 0 filas; PK producto y FK compuesta producto/variable | Correcto, falta selección/carga |
| `inv_planning_parameters_v` y `inv_planning_logistics_v` | Ambas existen; nombres y reglas esperadas | Correcto; devuelven 0 filas porque las tablas están vacías |

La FK de selección logística fue implementada con NO ACTION no diferible en lugar del RESTRICT propuesto; mantiene la protección frente a borrar una variable referenciada y no bloquea este avance. BACK también reforzó la validación del actor dentro de `inv_planning_audit_write`. No se exige que el SQL sea idéntico al borrador si preserva el contrato.

**No volver a ejecutar el reset ni las dos migraciones ya aplicadas.** Las 852 filas de prueba ya no están.

## 2. Pendiente estructural de FORECAST

No existe `supply_planning.spl_forecast_planning_input` en el catálogo relevado y no aparece la migración `20260914150003` en el historial Flyway de supply_planning. Tampoco se encontró una tabla de nombre equivalente `planning_input` en otro esquema.

Solicitar a BACK aplicar la [migración de snapshot FORECAST](../../entregables/backend_inventory_planning_20260914/migrations/supply_planning/V20260914150003__forecast_planning_input_snapshot.sql), o identificar y demostrar un mecanismo equivalente ya implementado. Es la evidencia por resultado que conserva los días, parámetro/revisión y logística usados.

**No impide preparar ni cargar inventory. Sí impide dar por terminado el contrato de publicación trazable de FORECAST.** No se reabre como requisito la propuesta anterior de políticas por grupo.

El historial de supply_planning sí tiene otras migraciones de políticas versionadas del 11/09. Esas entidades no sustituyen automáticamente el snapshot por resultado ni cambian la decisión confirmada de usar parámetros directos por artículo/local.

## 3. Fuentes y mapeo de carga

Los nombres físicos comprobados en la fuente central son **`diarco_data.src.base_productos_vigentes`** y **`diarco_data.src.base_stock_sucursal`**. Los nombres `src_base_*` se interpretaron como referencia a esas fuentes, no como tablas con ese nombre literal. En TEST también hay enlaces `diarco_prod_src_link`, pero este perfilado leyó directamente la fuente central; no se usaron sus tablas externas.

| Destino inventory | Fuente inicial identificada | Consideración |
|---|---|---|
| `product_site_id` | Productos: c_articulo + c_sucu_empr → inventory producto/local | Resolver códigos contra maestros TEST; no copiar UUID de otro esquema |
| `target_stock_days` | Stock: q_dias_stock | No usar dias_stock, que es otro atributo |
| `overstock_days` | Stock: q_dias_sobre_stock | No recuperar el eliminado safety_stock_days |
| `preparation_days` | Stock: dias_preparacion | Hay NULL en el origen; la tabla nueva exige valor |
| `minimum_order_quantity` | Productos: pedido_min | No confundir con stock_minimo ni con el mínimo de proveedor |
| `order_multiple` | Sin equivalencia confirmada en estas dos fuentes | Es opcional; no inferirlo de q_factor_compra ni q_unid_transferencia |
| `lead_time_days`, `transit_days` | Sin equivalencia confirmada en estas dos fuentes | Opcionales; no copiarlos desde preparación por conveniencia |
| `updated_by`, fechas, revisión | Trigger, con app.actor definido por el cargador | Contexto transaccional obligatorio |
| `active` | Regla explícita de carga/elegibilidad | La actividad del parámetro no sustituye habilitaciones de producto/local |

Unión de origen: `c_articulo = codigo_articulo` y `c_sucu_empr = codigo_sucursal`. Fijar un cierre común. No filtrar las observaciones por proveedor primario al construir el parámetro compartido.

### Calidad de las fuentes comprobada

Último cierre de stock: **2026-09-16**; extracción de ambas fuentes: **17/09/2026 por la mañana**, según los timestamps sin zona almacenados en origen.

- Productos vigentes: **1.010.195 filas y pares únicos**. Pedido mínimo: ningún NULL, negativo, NaN o infinito en el control realizado.
- Stock del último cierre: **1.284.942 filas y pares únicos**. No se detectaron días negativos; **637.876 filas** tienen al menos uno de los tres días requeridos ausente.
- De los pares de productos vigentes, **34.380** no tienen stock del último cierre. No se detectaron duplicados por par en ninguna de las dos entradas de esta unión.

Desglose sobre productos vigentes:

| Indicador | habilitado=1 y active_for_purchase=1 | Resto |
|---|---:|---:|
| Pares | 358.116 | 652.079 |
| Sin stock del cierre | 11.271 | 23.109 |
| Con stock, objetivo NULL | 0 | 5.922 |
| Con stock, sobrestock NULL | 0 | 5.922 |
| Con stock, preparación NULL | **151.358** | 333.139 |
| Con los tres días informados | **195.487** | 295.831 |

Este corte de habilitación legacy es un diagnóstico, **no el scope definitivo de PDD ni la elegibilidad de FORECAST**, que se resuelven desde CONNEXA. Los 195.487 pares completos son candidatos de origen, no filas ya aprobadas para cargar: falta verificar correspondencia completa con `inv_product_site`, exclusiones y precisión de cantidades.

La preparación faltante necesita una regla de negocio o una fuente alternativa confirmada. Mantenerla como incidencia hasta resolverla. No llenar 0, no reutilizar automáticamente el fallback de lead time de PDD y no elegir para cada par una fecha de stock distinta sin una política explícita.

## 4. Logística y consumidores

- `inv_product_planning_logistics` está vacía. Existen **9.705 productos con varias variables activas/principales**; el nuevo modelo permite seleccionar una, pero la migración no la elige. No cargar la primera fila ni deduplicar arbitrariamente.
- El lector local `FORECAST_CONNEXA/forecast_compare/extend.py` todavía usa `ps.expected_stock_days` y `r.safety_stock_days`. El camino `--verify-master` es incompatible con la estructura nueva: la última columna ya no existe. El [parche entregado](../../entregables/backend_inventory_planning_20260914/application/FORECAST_CONNEXA.patch) pasa `git apply --check --ignore-space-change` contra el árbol revisado, pero **no se aplicó en esta verificación**.
- Ese parche cambia ambos días, lee la selección logística y maneja Decimal en la evidencia JSON. Debe coordinarse antes de la siguiente prueba S20 contra TEST.
- PDD `daily_decas.py` sigue leyendo q_dias_stock/q_dias_sobre_stock de la fotografía legacy. No está todavía integrado al nuevo maestro: cargar inventory no modifica automáticamente sus resultados. El adaptador entregado requiere integración y conservación de evidencia en explanation/source_snapshot.
- No se ejecutaron S10/S20/S40 ni se verificó qué revisión de Java/Python está desplegada. Las observaciones de consumidores corresponden al código del workspace.

## 5. Qué necesitamos para avanzar

**Podemos avanzar ya:** diseñar la carga con los cuatro campos identificados, generar una previsualización por scope y cruzar códigos contra UUID TEST. No falta otro cambio estructural de reposición para eso.

**Antes de cargar el alcance completo:** resolver preparación faltante y pares sin stock del cierre, definir exclusiones/alcance, validar mapeo producto/local y precisión; cargar con actor y sin inventar valores.

**Antes de ejecutar/publicar el circuito nuevo:** poblar selección logística, adaptar los lectores, registrar snapshots PDD y completar con BACK la migración 03 de FORECAST o su equivalente. Validar cobertura con el scope real, no con conteos globales.

No se deben reenviar las doce solicitudes históricas como si todas siguieran pendientes. Para BACK, el pendiente estructural concreto observado es el snapshot FORECAST; carga/calidad de origen e integración de lectores son tareas distintas.

## Evidencia reproducible

- [verificacion_test_20260917.json](verificacion_test_20260917.json): catálogo, tipos exactos, FKs, triggers/funciones relevantes, vistas, conteos e historial Flyway.
- [fuentes_reposicion_20260917.json](fuentes_reposicion_20260917.json): columnas y agregados de ambas fuentes.
- [verificar_nivelacion_20260917.py](verificar_nivelacion_20260917.py) y [verificar_fuentes_reposicion_20260917.py](verificar_fuentes_reposicion_20260917.py): extractores READ ONLY. Conservan los relevamientos anteriores en sus archivos originales.
