# Relevamiento de parámetros de reposición

## Resultado comprobado en código

`backend/pdd_backend/jobs/daily_decas.py`, función `_read_source_stock`, lee `src.base_stock_sucursal.q_dias_stock` y `q_dias_sobre_stock` para cada artículo/local. Filtra `fecha_stock` y selecciona la última `fecha_extraccion` por artículo/local. No consulta una política de CONNEXA para estos dos valores.

`build_branch_position` exige ambos parámetros no nulos y no negativos. Cero es válido. Guarda los valores como `target_stock_days` y `overstock_days`. El fallback de 15 días del manifiesto corresponde a lead time, no a estos parámetros.

`build_need_rows` calcula, antes del redondeo logístico:

```text
N = stock físico + OC pendientes directas + tránsito desde CD
M = PDVB × target_stock_days
O = PDVB × overstock_days
D = max(M − N, 0)
E = max(M + O − max(N, 0), 0)
S = max(E − D, 0)
```

D se publica como necesidad obligatoria y S como opcional. Estos días gobiernan los objetivos de reposición; no son por sí solos toda la estimación: intervienen también PDVB, existencias, pendientes y factores logísticos. PDVB se recibe como una estimación previamente calculada.

## Objetos encontrados en archivos

| Objeto | Evidencia | Interpretación y límite |
|---|---|---|
| `src.base_stock_sucursal` | `PDD/backend/pdd_backend/jobs/daily_decas.py` | Fuente efectiva de los días en el código actual. |
| Carga de stock | `ETL_DIARCO/scripts/push/obtener_base_stock.py` | Extrae mediante un procedimiento almacenado, marca origen `SP_BASE_STOCK_DMZ` y convierte ambos campos a enteros. No se comprobó en vivo el linaje interno del procedimiento. |
| `src.t055_articulos_param_stock` | `ETL_DIARCO/cdc/postgres/110_prepare_src_t055_articulos_param_stock.sql` | El script define unicidad por `c_sucu_empr, c_clasificacion_compra, c_familia, c_rubro`. Es un antecedente prácticamente idéntico a la clave propuesta por el usuario. Los scripts CDC no prueban que esté desplegada en TEST ni que sea la fuente interna del procedimiento de stock. |
| `stock_management.pdd_branch_stock_position` | `PDD/PDD - DDL Operativo DECAS connexa_platform_ms v2.2.sql` | Contiene `target_stock_days` y `overstock_days`, restricciones no negativas y verificaciones de fórmulas. Es una fotografía del cálculo, no un maestro de políticas editable. |
| `replenishment.product_site_replenishment` | `ETL_DIARCO/scripts/datamart/ddl_Connexa_Core_Master_Data.sql` | Antecedente de política por `product_site_id`, con `target_coverage_days`, `safety_stock_days`, lead time y vigencias. No tiene la estructura de reglas por familia/rubro/perfil. `safety_stock_days` no debe equipararse automáticamente a sobrestock opcional. |
| `master_data.site` | Mismo DDL de master data | Tiene `ext_code`, `site_type`, `region_code`, `region_name`. No prueba que zona comercial sea región ni aporta un atributo explícito de tamaño en esa definición. |
| `master_data.product` | Mismo DDL | Tiene categoría y subcategoría. Falta confirmar su correspondencia con `c_familia` y `c_rubro`. |
| `master_data.product_classification` | Mismo DDL | Modelo por tipo/valor y producto con vigencia. Es candidato para clasificaciones múltiples; requiere comprobar alcance por local y catálogos reales. |
| `procurement` | No se obtuvo catálogo de TEST | No es posible establecer qué políticas, maestros o relaciones contiene actualmente. |

Las consultas `ETL_DIARCO/IOSdb/flows/cadena/query.py` distinguen clasificación de compra 1=SENSIBLES, 2=RESTO TOP, 3=VARIEDAD EXTRA, 4=A REMOVER, 5=SIN VENTA, 6=SENSIBLES PM y 100=SIN CLASIFICAR. Son valores observados en código, no un catálogo validado en TEST. La clase ABC y la rotación no deben suponerse equivalentes a esos códigos.

## Relevamiento de TEST pendiente

1. Inventariar todos los esquemas y describir sus responsabilidades según tablas, comentarios y relaciones reales. Identificar migraciones y diferencias frente a los DDL locales.
2. Analizar `procurement`, `stock_management`, `replenishment` y los maestros realmente existentes. Buscar días de stock, cobertura, safety stock, sobrestock y políticas también en columnas JSON, vistas y funciones relevantes; el nombre de una columna no basta para descartar funcionalidad.
3. Identificar PK/FK de empresa o tenant, sucursal, artículo, familia, rubro y clasificación. Comprobar si un rubro es único globalmente o sólo dentro de familia.
4. Determinar dónde se mantienen zona, tipo y tamaño del local, su completitud y vigencia. Determinar si ABC/rotación son globales o por artículo/local y período.
5. Medir cantidades y calidad sin exportar datos personales: nulos, negativos, duplicados, reglas vigentes superpuestas, locales sin perfil, artículos sin clasificación y referencias huérfanas.
6. Verificar permisos de edición y auditoría existentes, integración con la aplicación CONNEXA y responsabilidades de los esquemas. Revisar triggers, funciones y procesos que modifican políticas.
7. Si se requiere reconciliar con SGM, relevar aparte el origen autorizado en `diarco_data`: distribución de valores por fecha y grupo, linaje de `SP_BASE_STOCK_DMZ` y divergencias respecto de T055. Esa base no se consultó en esta tarea.
8. Completar diccionario por tabla: función, claves, relaciones, campos, restricciones, índices, volumen aproximado, procedencia y consumidores. Sólo después cerrar el esquema físico y la migración.
