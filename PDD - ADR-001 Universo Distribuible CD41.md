# ADR-001 — Universo distribuible desde CD 41

Fecha: **2026-08-02**  
Estado: **Aprobado**  
Alcance: **PDD Fase 1 — cálculo automático D/S**

## Decisión

El universo artículo–sucursal elegible para calcular necesidades D y S desde el CD/local 41 se obtiene mediante la intersección de:

1. artículos habilitados para compra en el local 41;
2. artículos habilitados en cada sucursal destino;
3. ruta de abastecimiento desde `41CD`;
4. abastecimiento tipo `0`;
5. artículo activo para venta y dentro del mix.

La consulta normativa es:

```sql
WITH cd_articles AS (
    SELECT DISTINCT c_articulo
    FROM src.base_productos_vigentes
    WHERE c_sucu_empr = 41
      AND active_for_purchase = 1
)
SELECT
    41 AS origin_cd,
    p.c_sucu_empr AS destination_branch,
    p.c_articulo,
    p.c_proveedor_primario,
    p.cod_cd,
    p.abastecimiento
FROM src.base_productos_vigentes p
JOIN cd_articles a USING (c_articulo)
WHERE p.c_sucu_empr <> 41
  AND p.cod_cd = '41CD'
  AND p.abastecimiento = 0
  AND p.habilitado = 1
  AND p.active_for_sale = 1
  AND p.active_on_mix = 1;
```

## Evidencia de la fotografía actual

Al 2026-08-02 la consulta produjo:

- **59.512** pares artículo–sucursal;
- **2.237** artículos distintos efectivamente ruteados a sucursales;
- **49** sucursales destino.

El conjunto inicial de artículos comprables en el local 41 era de 2.915 en esa fotografía. La diferencia entre artículos comprables y artículos efectivamente ruteados es esperable.

Los conteos son controles de una fotografía, no parámetros. Cada corrida utiliza una `pdd_distribution_scope_version` con fecha, filtros, conteos y checksum.

## Consecuencias

- No se calcula D/S para productos entregados directamente por proveedor.
- El local 41 no se considera sucursal destino dentro del mismo scope.
- Un cambio de surtido o ruta crea una nueva versión; no modifica corridas anteriores.
- `pdd_pdvb_estimate`, `pdd_pdvb_current`, `pdd_branch_stock_position` y `pdd_need_snapshot` deben referenciar la versión de scope utilizada.
- Un par que no cumpla todas las condiciones no puede publicarse como necesidad automática desde CD 41.

## Controles

- cero duplicados por versión–sucursal–artículo;
- todos los pares referencian un artículo comprable de la misma versión;
- `origin_cd = 41`;
- `route_code = '41CD'`;
- `supply_mode = 0`;
- las tres banderas `habilitado`, `active_for_sale` y `active_on_mix` son verdaderas;
- variaciones anormales de artículos, pares o sucursales requieren aprobación antes de publicar.

