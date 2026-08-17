# PDD - Fuente canónica de órdenes de compra pendientes v1.0

Fecha de decisión: 2026-08-17  
Fuente: `diarco_data.src.mv_base_oc_pendientes`  
Backend mínimo: `diarco-pdd-backend 0.12.0`

## Decisión

`src.mv_base_oc_pendientes` es la fuente canónica de las cantidades aún no
recibidas de órdenes de compra vigentes. El campo
`src.base_stock_sucursal.pedido_pendiente` deja de intervenir en los cálculos
PDD y se conserva únicamente como dato LEGACY de reconciliación.

Nunca deben sumarse ambas fuentes: hacerlo duplicaría mercadería entrante.

## Grano y consolidación

Aunque el destino funcional es artículo–sucursal, la vista entrega una fila
por orden–artículo–destino. La identidad documental se compone de
`u_prefijo_oc`, `u_sufijo_oc`, `c_articulo`, `c_sucu_destino` y proveedor.
Antes de calcular posiciones se aplica:

```sql
SELECT
    c_articulo::integer AS codigo_articulo,
    c_sucu_destino::integer AS destino,
    SUM(pendientes)::numeric AS pendiente
FROM src.mv_base_oc_pendientes
WHERE pendientes > 0
GROUP BY c_articulo, c_sucu_destino;
```

La condición `pendientes > 0` es deliberada. La definición actual de la vista
admite valores negativos cuando una línea fue sobrecumplida; esos valores no
son mercadería futura y no deben compensar OC positivas. Se cuentan como
anomalías en el diagnóstico y en el snapshot de fuente.

## Unidad de medida

No se vuelve a aplicar `q_factor_compra`. La vista ya calcula:

- artículos comunes: unidades solicitadas menos unidades cumplidas;
- venta por peso: peso solicitado menos peso cumplido.

Por lo tanto, `pendientes` ya es compatible con la unidad operativa de stock y
PDVB. `q_factor_compra`, `q_peso_unit_art` y `m_vende_por_peso` quedan como
atributos de auditoría de la transformación de origen.

## Aplicación por destino

| Destino de la OC | Campo operativo | Efecto |
|---|---|---|
| Sucursal incluida en el scope congelado | `pdd_branch_stock_position.direct_po_inbound` | Aumenta stock neto de sucursal y reduce D/S para evitar doble reposición desde CD |
| CD 41 | `pdd_cd_stock_position.open_po_on_time` | Aumenta disponibilidad proyectada del CD; no se asigna anticipadamente a una sucursal |
| Fuera del scope PDD CD41 | Ninguno | No participa en la corrida |

La vista no aporta fecha comprometida de entrega. Hasta contar con ese dato,
todas las OC positivas se clasifican provisionalmente como `open_po_on_time`,
`open_po_overdue` queda en cero y se conserva la alerta
`PO_DUE_CLASSIFICATION_PENDING`.

## Linaje y frescura

Cada corrida `DAILY_DECAS` crea un registro independiente en
`stock_management.pdd_source_snapshot`:

- `source_code`: `OPEN_PURCHASE_ORDERS`;
- `physical_relation`: `src.mv_base_oc_pendientes`;
- `as_of_ts`: máximo `fecha_extraccion` de la vista materializada;
- `row_count`: líneas positivas relevantes para el scope y el CD 41;
- `checksum`: SHA-256 de las cantidades consolidadas por artículo–destino;
- `detail`: cantidades, pares afectados y líneas negativas excluidas.

`direct_po_source_snapshot_id` y `po_source_snapshot_id` referencian este
snapshot. Stock físico y tránsito siguen referenciando
`BRANCH_AND_CD_STOCK` / `src.base_stock_sucursal`.

La corrida queda bloqueada si la vista está vacía o si `fecha_extraccion` es
anterior a la fecha operativa. Por ello el `REFRESH MATERIALIZED VIEW` debe
terminar antes de `PDD_DAILY_DECAS`.

## Perfil observado al 2026-08-17

Para el scope v5 `f157e436-1094-431b-ae2a-8f477d780c3e`:

- 3.927 líneas positivas relevantes;
- 1.058 pares artículo–sucursal con OC abierta;
- 1.333 artículos con OC destinada al CD 41;
- 8 líneas negativas excluidas;
- 7.126.154 unidades/peso positivos antes de la separación sucursal/CD;
- extracción: `2026-08-17 19:57:42.868024+00`.

Estos valores son un control de la primera integración, no umbrales fijos.

## Secuencia operativa

1. Actualizar las tablas LEGACY de OC.
2. Refrescar `src.mv_base_oc_pendientes`.
3. Actualizar stock y ventas.
4. Ejecutar `PDD_STOCK_READINESS_MANUAL`.
5. Continuar con `PDD_DAILY_DECAS_MANUAL` solamente si el diagnóstico devuelve
   `READY`.
6. Publicar el backlog DECAS.

## Controles posteriores a DAILY_DECAS

```sql
SELECT source_code, physical_relation, as_of_ts, row_count, status, detail
FROM stock_management.pdd_source_snapshot
WHERE calculation_run_id = (
    SELECT calculation_run_id
    FROM stock_management.pdd_calculation_run
    WHERE calculation_run_uuid = 'UUID_CORRIDA_DAILY_DECAS'
)
ORDER BY source_code;
```

```sql
SELECT
    COUNT(*) FILTER (WHERE direct_po_source_snapshot_id = stock_source_snapshot_id)
        AS linaje_oc_incorrecto,
    SUM(direct_po_inbound) AS oc_directas_sucursal
FROM stock_management.pdd_branch_stock_position
WHERE calculation_run_id = (
    SELECT calculation_run_id
    FROM stock_management.pdd_calculation_run
    WHERE calculation_run_uuid = 'UUID_CORRIDA_DAILY_DECAS'
);
```

El primer control debe devolver dos snapshots (`BRANCH_AND_CD_STOCK` y
`OPEN_PURCHASE_ORDERS`). El segundo debe devolver
`linaje_oc_incorrecto = 0`.

