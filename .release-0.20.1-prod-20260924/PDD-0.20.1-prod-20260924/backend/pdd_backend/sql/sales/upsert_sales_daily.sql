WITH cd_articles AS (
    SELECT
        a.codigo_articulo,
        a.c_proveedor_primario
    FROM datamart.dm_pdd_scope_article AS a
    WHERE a.scope_version_uuid = CAST(:scope_version_uuid AS uuid)
),
scope_pairs AS (
    SELECT
        p.codigo_articulo,
        p.destination_branch AS sucursal,
        coalesce(p.c_proveedor_primario, a.c_proveedor_primario)
            AS c_proveedor_primario
    FROM datamart.dm_pdd_scope_pair AS p
    INNER JOIN cd_articles AS a USING (codigo_articulo)
    WHERE p.scope_version_uuid = CAST(:scope_version_uuid AS uuid)
      AND p.origin_cd = :origin_cd
),
calendar AS (
    SELECT generate_series(
        CAST(:start_date AS date),
        CAST(:end_date AS date),
        interval '1 day'
    )::date AS sales_date
),
raw_daily AS (
    SELECT
        b.fecha::date AS sales_date,
        b.codigo_articulo,
        b.sucursal,
        count(*)::integer AS source_row_count,
        sum(greatest(b.unidades, 0))::numeric(18,6) AS observed_units,
        sum(abs(least(b.unidades, 0)))::numeric(18,6) AS return_units,
        sum(b.importe_vendido::numeric)::numeric(20,4) AS sold_amount,
        (
            sum(CASE WHEN b.unidades > 0 THEN b.precio * b.unidades ELSE 0 END)
            / nullif(sum(greatest(b.unidades, 0)), 0)
        )::numeric(18,6) AS effective_unit_price,
        min(b.precio)::numeric(18,6) AS min_price,
        max(b.precio)::numeric(18,6) AS max_price,
        bool_or(coalesce(b.venta_especial, false)) AS special_sale_flag,
        bool_or(coalesce(b.promo_normal, false)) AS normal_promo_flag,
        bool_or(coalesce(b.promo_fuerte, false)) AS strong_promo_flag,
        max(b.familia) AS familia,
        max(b.rubro) AS rubro,
        max(b.subrubro) AS subrubro,
        max(b.c_proveedor_primario) AS c_proveedor_primario,
        max(b.fecha_procesado) AS source_max_processed_at
    FROM src.base_ventas_extendida AS b
    INNER JOIN scope_pairs AS sp
        ON sp.codigo_articulo = b.codigo_articulo
       AND sp.sucursal = b.sucursal
    WHERE b.fecha >= CAST(:start_date AS date)
      AND b.fecha < CAST(:end_date AS date) + interval '1 day'
    GROUP BY b.fecha::date, b.codigo_articulo, b.sucursal
),
enriched_daily AS (
    SELECT
        e.fecha::date AS sales_date,
        e.codigo_articulo,
        e.sucursal,
        count(*)::integer AS enriched_row_count,
        sum(greatest(e.venta_basal, 0))::numeric(18,6) AS basal_units,
        sum(greatest(e.venta_promocional, 0))::numeric(18,6) AS promotional_units,
        max(e.score_promo)::numeric(8,4) AS promo_score_max,
        bool_or(coalesce(e.promo_fuerte_detectada, false)) AS strong_promo_detected,
        max(e.fecha_calculo) AS enriched_max_calculated_at
    FROM datamart.dm_bve_ventas_enriquecidas AS e
    INNER JOIN scope_pairs AS sp
        ON sp.codigo_articulo = e.codigo_articulo
       AND sp.sucursal = e.sucursal
    WHERE e.fecha >= CAST(:start_date AS date)
      AND e.fecha < CAST(:end_date AS date) + interval '1 day'
    GROUP BY e.fecha::date, e.codigo_articulo, e.sucursal
),
panel AS (
    SELECT
        c.sales_date,
        sp.codigo_articulo,
        sp.sucursal,
        coalesce(r.c_proveedor_primario, sp.c_proveedor_primario) AS c_proveedor_primario,
        r.familia,
        r.rubro,
        r.subrubro,
        coalesce(r.source_row_count, 0) AS source_row_count,
        coalesce(r.observed_units, 0)::numeric(18,6) AS observed_units,
        coalesce(r.return_units, 0)::numeric(18,6) AS return_units,
        r.sold_amount,
        r.effective_unit_price,
        r.min_price,
        r.max_price,
        coalesce(r.special_sale_flag, false) AS special_sale_flag,
        coalesce(r.normal_promo_flag, false) AS normal_promo_flag,
        coalesce(r.strong_promo_flag, false) AS strong_promo_flag,
        e.enriched_row_count,
        e.basal_units AS enriched_basal_units,
        e.promotional_units AS enriched_promotional_units,
        e.promo_score_max,
        coalesce(e.strong_promo_detected, false) AS strong_promo_detected,
        r.source_max_processed_at,
        e.enriched_max_calculated_at,
        s.stock_quantity,
        s.is_serviceable_by_stock,
        s.source_row_hash AS stock_source_hash
    FROM calendar AS c
    CROSS JOIN scope_pairs AS sp
    LEFT JOIN raw_daily AS r
        ON r.sales_date = c.sales_date
       AND r.codigo_articulo = sp.codigo_articulo
       AND r.sucursal = sp.sucursal
    LEFT JOIN enriched_daily AS e
        ON e.sales_date = c.sales_date
       AND e.codigo_articulo = sp.codigo_articulo
       AND e.sucursal = sp.sucursal
    LEFT JOIN datamart.dm_pdd_stock_diario AS s
        ON s.stock_date = c.sales_date
       AND s.codigo_articulo = sp.codigo_articulo
       AND s.sucursal = sp.sucursal
),
validated_panel AS (
    SELECT
        p.*,
        (
            p.enriched_row_count > 0
            AND abs(
                p.observed_units
                - coalesce(p.enriched_basal_units, 0)
                - coalesce(p.enriched_promotional_units, 0)
            ) <= 0.001
        ) AS enriched_units_conserved
    FROM panel AS p
),
classified AS (
    SELECT
        p.*,
        CASE
            WHEN p.observed_units > 0 THEN 'INFERRED_FROM_SALE'
            WHEN p.stock_source_hash IS NULL THEN 'UNKNOWN'
            WHEN p.is_serviceable_by_stock THEN 'IN_STOCK'
            ELSE 'OUT_OF_STOCK'
        END::varchar(30) AS availability_status,
        CASE
            WHEN p.enriched_units_conserved THEN p.enriched_basal_units
            WHEN p.enriched_row_count > 0 THEN 0
            WHEN p.source_row_count > 0
             AND (p.special_sale_flag OR p.normal_promo_flag OR p.strong_promo_flag)
                THEN 0
            ELSE p.observed_units
        END::numeric(18,6) AS basal_units,
        CASE
            WHEN p.enriched_units_conserved THEN p.enriched_promotional_units
            WHEN p.enriched_row_count > 0 THEN p.observed_units
            WHEN p.source_row_count > 0
             AND (p.special_sale_flag OR p.normal_promo_flag OR p.strong_promo_flag)
                THEN p.observed_units
            ELSE 0
        END::numeric(18,6) AS promotional_units,
        CASE
            WHEN p.enriched_units_conserved THEN 'ENRICHED'
            WHEN p.enriched_row_count > 0 THEN 'ENRICHED_INVALID'
            WHEN p.source_row_count > 0
             AND (p.special_sale_flag OR p.normal_promo_flag OR p.strong_promo_flag)
                THEN 'RAW_FLAGS'
            WHEN p.source_row_count > 0 THEN 'NO_ADJUSTMENT'
            ELSE 'NOT_APPLICABLE'
        END::varchar(30) AS promo_adjustment_method
    FROM validated_panel AS p
),
prepared AS (
    SELECT
        c.*,
        (
            c.availability_status IN ('IN_STOCK', 'INFERRED_FROM_SALE')
            AND NOT (
                (
                    c.promo_adjustment_method = 'RAW_FLAGS'
                    AND c.observed_units > 0
                )
                OR c.promo_adjustment_method = 'ENRICHED_INVALID'
            )
        ) AS eligible_for_pdvb,
        array_remove(ARRAY[
            CASE WHEN c.availability_status = 'UNKNOWN' THEN 'STOCK_UNKNOWN' END,
            CASE WHEN c.availability_status = 'OUT_OF_STOCK' THEN 'OUT_OF_STOCK' END,
            CASE
                WHEN c.promo_adjustment_method = 'RAW_FLAGS' AND c.observed_units > 0
                THEN 'PROMO_WITHOUT_ENRICHMENT'
            END,
            CASE
                WHEN c.promo_adjustment_method = 'ENRICHED_INVALID'
                THEN 'ENRICHED_UNITS_MISMATCH'
            END
        ], NULL)::text[] AS exclusion_codes,
        encode(
            sha256(
                convert_to(
                    concat_ws('|',
                        c.sales_date::text,
                        c.codigo_articulo::text,
                        c.sucursal::text,
                        c.observed_units::text,
                        c.return_units::text,
                        c.basal_units::text,
                        c.promotional_units::text,
                        c.availability_status,
                        c.promo_adjustment_method,
                        coalesce(c.stock_source_hash::text, '')
                    ),
                    'UTF8'
                )
            ),
            'hex'
        )::char(64) AS source_hash
    FROM classified AS c
)
INSERT INTO datamart.dm_pdd_venta_diaria (
    sales_date,
    codigo_articulo,
    sucursal,
    scope_version_uuid,
    feature_run_uuid,
    c_proveedor_primario,
    familia,
    rubro,
    subrubro,
    source_row_count,
    observed_units,
    return_units,
    basal_units,
    promotional_units,
    sold_amount,
    effective_unit_price,
    min_price,
    max_price,
    assortment_active,
    availability_status,
    stock_quantity_snapshot,
    stock_source_hash,
    special_sale_flag,
    normal_promo_flag,
    strong_promo_flag,
    promo_score_max,
    promo_adjustment_method,
    eligible_for_pdvb,
    exclusion_codes,
    source_max_processed_at,
    enriched_max_calculated_at,
    feature_calculated_at,
    source_hash
)
SELECT
    sales_date,
    codigo_articulo,
    sucursal,
    CAST(:scope_version_uuid AS uuid),
    CAST(:feature_run_uuid AS uuid),
    c_proveedor_primario,
    familia,
    rubro,
    subrubro,
    source_row_count,
    observed_units,
    return_units,
    basal_units,
    promotional_units,
    sold_amount,
    effective_unit_price,
    min_price,
    max_price,
    true,
    availability_status,
    stock_quantity,
    stock_source_hash,
    special_sale_flag,
    normal_promo_flag,
    (strong_promo_flag OR strong_promo_detected),
    promo_score_max,
    promo_adjustment_method,
    eligible_for_pdvb,
    exclusion_codes,
    source_max_processed_at,
    enriched_max_calculated_at,
    clock_timestamp(),
    source_hash
FROM prepared
ON CONFLICT (sales_date, codigo_articulo, sucursal) DO UPDATE
SET scope_version_uuid = EXCLUDED.scope_version_uuid,
    feature_run_uuid = EXCLUDED.feature_run_uuid,
    c_proveedor_primario = EXCLUDED.c_proveedor_primario,
    familia = EXCLUDED.familia,
    rubro = EXCLUDED.rubro,
    subrubro = EXCLUDED.subrubro,
    source_row_count = EXCLUDED.source_row_count,
    observed_units = EXCLUDED.observed_units,
    return_units = EXCLUDED.return_units,
    basal_units = EXCLUDED.basal_units,
    promotional_units = EXCLUDED.promotional_units,
    sold_amount = EXCLUDED.sold_amount,
    effective_unit_price = EXCLUDED.effective_unit_price,
    min_price = EXCLUDED.min_price,
    max_price = EXCLUDED.max_price,
    assortment_active = EXCLUDED.assortment_active,
    availability_status = EXCLUDED.availability_status,
    stock_quantity_snapshot = EXCLUDED.stock_quantity_snapshot,
    stock_source_hash = EXCLUDED.stock_source_hash,
    special_sale_flag = EXCLUDED.special_sale_flag,
    normal_promo_flag = EXCLUDED.normal_promo_flag,
    strong_promo_flag = EXCLUDED.strong_promo_flag,
    promo_score_max = EXCLUDED.promo_score_max,
    promo_adjustment_method = EXCLUDED.promo_adjustment_method,
    eligible_for_pdvb = EXCLUDED.eligible_for_pdvb,
    exclusion_codes = EXCLUDED.exclusion_codes,
    source_max_processed_at = EXCLUDED.source_max_processed_at,
    enriched_max_calculated_at = EXCLUDED.enriched_max_calculated_at,
    feature_calculated_at = clock_timestamp(),
    source_hash = EXCLUDED.source_hash
WHERE dm_pdd_venta_diaria.source_hash IS DISTINCT FROM EXCLUDED.source_hash
   OR dm_pdd_venta_diaria.scope_version_uuid IS DISTINCT FROM EXCLUDED.scope_version_uuid;
