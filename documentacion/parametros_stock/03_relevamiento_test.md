# Relevamiento real de PGP_TEST_DB

> Documento histórico. Para el estado actual y la decisión de reutilizar `inventory`, consultar la [auditoría de TEST del 14/09/2026](07_auditoria_inventory_test_20260914.md). Los conteos y recomendaciones siguientes corresponden a su fecha original.

Fecha: 2026-09-11. Conexión exitosa a `connexa_platform_test`, PostgreSQL 14.24. Se utilizaron las credenciales actualizadas de `PDD/backend/.env`, con transacciones de solo lectura. No se modificaron datos ni estructuras. Este informe reemplaza las conclusiones provisionales sobre ubicación del documento 02.

## Conclusión

**Sí existen estructuras de parámetros en CONNEXA TEST. El candidato más directo es `supply_planning`, que ya implementa grupos de locales y días de stock por categoría.** No hace falta comenzar creando un dominio `replenishment`: ese esquema no aparece en el catálogo relevado. El antecedente del repositorio se encuentra desplegado con otros nombres en `inventory`.

`procurement` contiene organización de compradores, proveedores, categorías, locales y tareas; sus campos de días son límites por grupo de compradores. No se encontró allí una regla equivalente a local/perfil × familia/rubro × clasificación con ambos días. La interpretación funcional de esos límites requiere revisar el consumidor de la aplicación.

## Inventario por esquema

Los 1047 objetos incluyen tablas, particiones, vistas y tablas externas; no representan 1047 entidades independientes.

| Esquema | Objetos | Lectura del dominio a partir de sus objetos |
|---|---:|---|
| authentication | 17 | Autenticación |
| foundation | 34 | Datos compartidos y organización |
| inventory | 56 | Productos, locales, categorías y políticas por producto/local |
| procurement | 25 | Compradores, grupos, proveedores, categorías y tareas |
| procurement_and_sourcing | 101 | Compras y abastecimiento |
| supply_planning | 122 | Planificación de abastecimiento; grupos y reglas existentes |
| stock_management | 148 | Inventario operativo y PDD, incluidas particiones |
| commercial_agreements | 28 | Acuerdos comerciales |
| assortment | 2 | Surtido |
| comex | 22 | Comercio exterior |
| cad | 19 | Estructuras de diseño y espacio |
| mail_processor | 15 | Procesamiento de correo |
| nexa | 3 | Objetos auxiliares; responsabilidad funcional por confirmar |
| public | 218 | Modelo coexistente y objetos externos; no asumir que sea el maestro vigente |
| diarco_prod_connexa_public_link | 222 | Enlaces externos |
| diarco_prod_src_link | 15 | Enlaces a fuentes externas |

Se capturaron 11733 columnas, 3336 restricciones, 1535 índices, 23 vistas y 238 tablas externas. El diccionario incluye claves y relaciones. La extracción de triggers no internos devolvió uno, sobre recepciones de compras; esto no descarta auditoría implementada por aplicación.

## Estructuras reutilizables y datos comprobados

| Tabla | Modelo observado | Conteo exacto / hallazgo |
|---|---|---|
| `supply_planning.spl_supply_cluster` | PK UUID, nombre único | 14 grupos |
| `supply_planning.spl_supply_site` | Local `site_id` → `spl_site`; grupo `supply_cluster_id` → `spl_supply_cluster` | 100 filas, 100 locales distintos, ninguno sin grupo ni en varios grupos |
| `supply_planning.spl_supply_cluster_category` | Grupo + categoría → `spl_category`; `stock_days` obligatorio, `stock_days_limit` opcional | 141 filas; días entre 15 y 65; límite 0 en todas las filas |
| `inventory.inv_product_site_replenishment` | FK y UNIQUE por `product_site_id`; `target_coverage_days`, `safety_stock_days`, lead time, múltiplos | 0 filas |
| `inventory.inv_product_classification` | Producto + tipo UUID + valor, vigencias, activo | 0 filas; catálogo de tipos también vacío |
| `inventory.inv_product_site` | UNIQUE producto/local, `expected_stock_days`, capacidades, vigencias y surtido | Estructura disponible; no se perfiló su contenido |
| `stock_management.pdd_branch_stock_position` | Fotografía con `target_stock_days` y `overstock_days` | Existe en TEST con particiones; no se contó su contenido |
| `procurement.prc_buyer_group` | `stock_days_limit` y límite de compra | Límite de grupo de compradores; contenido no perfilado |
| `procurement.prc_buyer_group_relation` | `buyer_stock_days_limit` | No equivale por estructura a una política de reposición por artículo/local |

### Duplicados y semántica

Hay **23 claves grupo/categoría repetidas con pares de días diferentes**. No son solamente filas idénticas duplicadas. La tabla tiene PK `id` y FKs, pero no una restricción UNIQUE sobre grupo/categoría, ni vigencia, prioridad o clasificación que expliquen en su estructura esas diferencias. Debe verificarse la lógica del consumidor antes de decidir cómo consolidarlas.

`stock_days_limit=0` en las 141 filas no demuestra que el sobrestock sea cero. Puede representar un valor especial, un límite no configurado o una convención de aplicación. **No se debe mapear a `q_dias_sobre_stock` sin confirmar su semántica.** Lo mismo aplica a `safety_stock_days`, porque stock de seguridad y sobrestock opcional son conceptos diferentes.

Las asignaciones local/grupo hoy no están duplicadas, pero sólo tienen PK por UUID y FKs: falta una garantía de unicidad por local si se decide mantener un único perfil efectivo.

## Categorías, locales y clasificaciones

`supply_planning.spl_category` tiene `ext_code` único, relación jerárquica `parent_id`, `category_type_code` y `category_type_id`. Esto permite representar niveles, pero todavía hay que comprobar con un mapeo de datos qué nivel corresponde a familia y rubro del legado. No unir categorías por nombre.

`supply_planning.spl_site` incluye código único, empresa y tipo. No tiene campos explícitos de zona o tamaño. Los grupos existentes pueden servir de perfiles, pero el catálogo no demuestra que sus nombres y membresías representen una combinación de zona/tamaño. Se debe definir esa correspondencia con el negocio.

`inventory` tiene sus propios maestros de producto, categoría y local. Las FKs de `supply_planning` apuntan a sus propios maestros. No se debe asumir igualdad de UUID entre esquemas; validar correspondencias por código y establecer el contrato de sincronización.

No hay clasificación cargada en las tablas de `inventory` relevadas. Antes de condicionar por compra, ABC o rotación, definir el origen de cada dimensión, su alcance global o por local y su vigencia. No asumir que «A» equivale a «sensible».

## Tablas externas y coexistencia

`public.t_cluster_param_stock` **es una tabla externa**, con `cluster_log, c_familia, c_rubro, q_dias_stock, q_dias_sobre_stock`. Su estructura es especialmente relevante como antecedente, pero no constituye un maestro local de TEST. No se consultaron sus filas ni se escribieron datos a través de enlaces.

Existen también `public.spl_supply_cluster_category` y objetos homónimos en esquemas de enlace. El catálogo por sí solo no establece cuál consume hoy cada pantalla. Antes de migrar, localizar las consultas de la aplicación y la sincronización entre modelos. Crear o editar una tabla local no garantiza que CONNEXA o PDD la utilicen.

## Recomendación revisada

1. Usar `supply_planning` como dominio candidato y reutilizar `spl_supply_cluster`, `spl_supply_site`, `spl_site` y `spl_category`, previa validación de su uso por la aplicación.
2. Incorporar una política versionada que contenga explícitamente **días objetivo y días de sobrestock**. Extender la tabla actual sólo si se valida compatibilidad con sus consumidores; en caso contrario crear tablas de reglas/versiones dentro del mismo dominio y un adaptador para consumidores existentes.
3. Resolver las 23 combinaciones conflictivas con una previsualización y decisión funcional; no eliminar filas ni elegir el último timestamp automáticamente.
4. Aplicar el diseño del documento 02: ámbito local/perfil/global, clasificación, vigencia, prioridad explícita, auditoría y resolución única. Los clusters proporcionan la base del perfil, no toda la política.
5. Mantener la política por producto/local de `inventory` como capacidad a evaluar para excepciones o resultados resueltos, evitando dos maestros editables para el mismo parámetro. Hoy está vacía.
6. Cambiar el lector de PDD para consumir los parámetros efectivos de CONNEXA; conservar los valores y la regla/version en cada corrida. Hasta modificar `daily_decas.py`, PDD continúa leyendo los días de `src.base_stock_sucursal`.

PostgreSQL es versión 14: no diseñar la unicidad de filtros NULL usando `UNIQUE NULLS NOT DISTINCT` de versiones posteriores. Definir índices por ámbito y normalización de filtros, o una representación sin ambigüedad; la publicación debe validar además solapamientos funcionales y temporales.

## Límites y siguientes verificaciones de implementación

El relevamiento incluyó catálogo general y consultas agregadas específicas; no auditó todas las filas de negocio, permisos de UI, rutinas almacenadas, JSON de configuración ni código externo de CONNEXA. No se certifica ausencia absoluta de otra lógica de políticas fuera de las estructuras analizadas.

Antes de implementar: confirmar semántica de `stock_days_limit`, consumidor de las tablas de `public` frente a `supply_planning`, mapeo familia/rubro, origen de clasificación y perfil zona/tamaño. Estas decisiones no impidieron completar el relevamiento solicitado, pero sí condicionan una migración correcta. No se ejecutó DDL ni se alteró el cálculo actual.
