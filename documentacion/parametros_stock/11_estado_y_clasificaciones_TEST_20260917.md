# Estado actualizado y revisión de clasificaciones — 17/09/2026

> **Actualización posterior:** BACK aplicó `20260917160001`. Ya existe `inv_product_classification_value`, con siete valores de Compra activos. La asignación usa `classification_value_id` y FK compuesta para validar su tipo; el texto libre fue retirado. Hay cero asignaciones y active ahora tiene default true. Por tanto, la propuesta de tercera tabla y las cinco filas simuladas descritas debajo son antecedentes, no el estado actual. Ver [evidencia posterior](clasificaciones_catalogo_aplicado_20260917.json) y [contrato aplicado](../../entregables/backend_classification_catalog_20260917/README.md). Falta cargar las asignaciones reales desde T050; no se ejecutó ninguna carga en esta verificación.

## Estado de la nivelación

**Cerrado el pendiente estructural identificado en el informe 10:** existe `supply_planning.spl_forecast_planning_input`, con cero filas, y Flyway registra `20260914150003__forecast_planning_input_snapshot` aplicada exitosamente el 17/09.

Se verificaron columnas, nulabilidad, PK por result_id, FK al resultado FORECAST con ON DELETE RESTRICT, CHECK de revisiones positivas, días no negativos/finitos y snapshot JSON objeto. El trigger contra UPDATE/DELETE/TRUNCATE está habilitado y su función rechaza esas operaciones. Los IDs de maestros inventory no tienen FK, conforme al contrato de conservar referencias históricas. La inspección fue de solo lectura; no se probaron escrituras ni servicios de aplicación.

Las tres migraciones del paquete están registradas en sus respectivos historiales. No se encontró otro faltante estructural del paquete revisado. **Esto no significa que el circuito ya esté listo para publicar**:

- Reposición y selección logística siguen con cero filas; deben cargarse.
- Persisten las tareas de integración de lectores y escritura de snapshots del informe 10. No se modificó código de aplicación en esta revisión.
- Las incidencias de fuentes del informe 10 siguen como evidencia de esa captura; no se volvió a perfilar diarco_data en esta revisión.

## Lógica original de las clasificaciones

El DDL original de maestros proponía una asignación por producto con `classification_type` y `classification_value` como textos. BACK normalizó el **tipo** en una entidad separada:

| Entidad | Qué representa | Ejemplo |
|---|---|---|
| `inv_product_classification_type` | Dimensión o criterio con el que se clasifica | Clasificación Compra, Clasificación Venta, ABC |
| `inv_product_classification` | Asignación de un valor a un producto bajo ese criterio, con actividad y vigencia | Artículo 10775 → Clasificación Compra → 1-Sensibles |

Relaciones actuales:

```text
inv_product                  1 ─── N inv_product_classification
inv_product_classification_type 1 ─── N inv_product_classification
```

`classification_type_id` referencia el tipo. `classification_value` es el valor concreto y actualmente es texto libre. El nombre `value` en la tabla de tipos puede confundir: allí contiene el nombre del criterio, no una de sus alternativas.

Un mismo producto puede tener, por ejemplo, una clasificación de compra y otra de venta, en filas separadas. El modelo no tiene site_id: la clasificación es **global por producto**, no distinta por sucursal. Tampoco está separada por proveedor.

## Qué se simuló y qué está bien

Hay dos tipos: **Clasificación Compra** y **Clasificación Venta**. Se encontraron cinco asignaciones, a cinco productos, todas bajo el tipo Compra:

| Artículo | Valor asignado | Activo |
|---|---|---|
| 10775 | 1-Sensibles | false |
| 10778 | 5-Sin Venta | false |
| 10780 | 2-Resto Top | false |
| 10781 | 6-Sensibles PM | false |
| 10784 | 3-Variedad Extra | false |

Las cinco tienen valid_from=2026-01-01 y valid_to=2030-12-31. No se detectaron valores vacíos, fechas invertidas ni varias asignaciones activas por producto/tipo en esta muestra. Clasificación Venta aún no tiene asignaciones.

**La simulación es coherente con el diseño actual**: los tipos son dimensiones y las filas de producto son asignaciones. No es posible certificar que cada artículo deba tener esa clase comercial sin una fuente de negocio; se verificó coherencia estructural, no corrección de la clasificación elegida.

El detalle que impide que sean utilizadas como vigentes por un consumidor que filtra actividad es que **todas están inactivas**. El default de la tabla es `active=false`: omitirlo al insertar produce justamente ese estado. Las fechas por sí solas no activan las filas. No se cambió su actividad en esta revisión.

## ¿Conviene otra relación?

No hace falta invertir ni eliminar la relación actual. Es válida si se desea un sistema flexible de etiquetas libres. Sin embargo, para clasificaciones de compra con alternativas controladas, **conviene completar el modelo con un catálogo de valores**:

```text
Tipo Compra
  ├─ código 1 / Sensibles
  ├─ código 2 / Resto Top
  ├─ código 3 / Variedad Extra
  └─ ...

Producto 10775 → valor de catálogo código 1, perteneciente al tipo Compra
```

Propuesta, no aplicada: una entidad como `inv_product_classification_value` con UUID, tipo, código estable, descripción y actividad; UNIQUE(tipo,código). La asignación al producto referenciaría ese valor. El tipo se deriva del valor; si se conserva también en la asignación, una FK compuesta debe impedir que ambos tipos difieran.

Esto mantiene las dos responsabilidades actuales y agrega una tercera: **tipo → alternativas permitidas → asignación al producto**. Separar código `1` y descripción `Sensibles` evita depender del formato `1-Sensibles` o de cambios de texto para integrar otros sistemas. No se propone crear un tipo distinto para cada alternativa.

En el modelo actual, la base acepta cualquier texto no nulo: errores tipográficos, distintas etiquetas para el mismo código o valores ajenos al tipo. La FK sólo valida que el tipo exista, no que `classification_value` pertenezca a su catálogo. El control podría existir en BACK, pero no se verificó su API/UI.

Antes de usar clasificaciones como filtro operativo, conviene acordar además:

1. Si cada tipo permite un único valor vigente por producto o varios. Para Compra, si se espera uno, impedir asignaciones temporalmente superpuestas; un simple UNIQUE(producto,tipo) eliminaría la posibilidad de guardar historia.
2. La semántica exacta de vigencia y sus controles: hoy no hay CHECK de fechas ni garantía de no solapamiento.
3. Cómo se activa una asignación y qué hace el consumidor cuando falta. No confundir ausencia con una clase comercial como “Sin Venta”.
4. La relación con códigos del origen y catálogos existentes. No asumir que Compra, Venta y ABC son equivalentes ni reutilizar UUID/códigos entre dominios sin contrato.

Estos ajustes son una recomendación adicional de calidad del modelo, **no un prerrequisito de la carga de días por artículo/local** ya acordada. El circuito directo de reposición no depende de resolver reglas por clasificación/grupo.

## Evidencia

- [verificacion_clasificaciones_20260917.json](verificacion_clasificaciones_20260917.json): nueva captura TEST, catálogo, historial y datos de la simulación.
- [verificar_clasificaciones_20260917.py](verificar_clasificaciones_20260917.py): extractor READ ONLY, conserva las capturas anteriores.
- [Informe previo](10_verificacion_BACK_TEST_20260917.md): carga, fuentes y consumidores; su pendiente estructural de snapshot queda cerrado por esta revisión.

No se modificó ningún registro ni estructura de TEST. No se activaron clasificaciones, no se crearon catálogos y no se ejecutó nuevamente ninguna migración.
