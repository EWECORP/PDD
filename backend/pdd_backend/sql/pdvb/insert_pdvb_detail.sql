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
stats AS (
    SELECT
        sp.codigo_articulo,
        sp.sucursal,
        sp.c_proveedor_primario,
        count(v.*) FILTER (
            WHERE v.sales_date BETWEEN CAST(:recent_start AS date) AND CAST(:recent_end AS date)
        )::integer AS recent_active_days,
        count(v.*) FILTER (
            WHERE v.sales_date BETWEEN CAST(:previous_start AS date) AND CAST(:previous_end AS date)
        )::integer AS previous_active_days,
        count(v.*) FILTER (
            WHERE v.sales_date BETWEEN CAST(:seasonal_start AS date) AND CAST(:seasonal_end AS date)
        )::integer AS seasonal_active_days,
        count(v.*) FILTER (
            WHERE v.eligible_for_pdvb
              AND v.sales_date BETWEEN CAST(:recent_start AS date) AND CAST(:recent_end AS date)
        )::integer AS recent_eligible_days,
        count(v.*) FILTER (
            WHERE v.eligible_for_pdvb
              AND v.sales_date BETWEEN CAST(:previous_start AS date) AND CAST(:previous_end AS date)
        )::integer AS previous_eligible_days,
        count(v.*) FILTER (
            WHERE v.eligible_for_pdvb
              AND v.sales_date BETWEEN CAST(:seasonal_start AS date) AND CAST(:seasonal_end AS date)
        )::integer AS seasonal_eligible_days,
        coalesce(sum(v.basal_units) FILTER (
            WHERE v.eligible_for_pdvb
              AND v.sales_date BETWEEN CAST(:recent_start AS date) AND CAST(:recent_end AS date)
        ), 0)::numeric(20,6) AS recent_basal_units,
        coalesce(sum(v.basal_units) FILTER (
            WHERE v.eligible_for_pdvb
              AND v.sales_date BETWEEN CAST(:previous_start AS date) AND CAST(:previous_end AS date)
        ), 0)::numeric(20,6) AS previous_basal_units,
        coalesce(sum(v.basal_units) FILTER (
            WHERE v.eligible_for_pdvb
              AND v.sales_date BETWEEN CAST(:seasonal_start AS date) AND CAST(:seasonal_end AS date)
        ), 0)::numeric(20,6) AS seasonal_basal_units,
        avg(v.basal_units) FILTER (
            WHERE v.eligible_for_pdvb
              AND v.sales_date BETWEEN CAST(:recent_start AS date) AND CAST(:recent_end AS date)
        )::numeric(18,6) AS recent_mean,
        avg(v.basal_units) FILTER (
            WHERE v.eligible_for_pdvb
              AND v.sales_date BETWEEN CAST(:previous_start AS date) AND CAST(:previous_end AS date)
        )::numeric(18,6) AS previous_mean,
        avg(v.basal_units) FILTER (
            WHERE v.eligible_for_pdvb
              AND v.sales_date BETWEEN CAST(:seasonal_start AS date) AND CAST(:seasonal_end AS date)
        )::numeric(18,6) AS seasonal_mean,
        count(v.*)::integer AS active_days,
        count(v.*) FILTER (WHERE v.eligible_for_pdvb)::integer AS eligible_days,
        count(v.*) FILTER (
            WHERE v.eligible_for_pdvb AND v.basal_units > 0
        )::integer AS nonzero_days,
        count(v.*) FILTER (
            WHERE v.eligible_for_pdvb
              AND (v.source_row_count = 0 OR v.promo_adjustment_method = 'ENRICHED')
        )::integer AS promo_reliable_days,
        avg(v.basal_units) FILTER (
            WHERE v.eligible_for_pdvb AND v.basal_units > 0
        ) AS nonzero_mean,
        stddev_samp(v.basal_units) FILTER (
            WHERE v.eligible_for_pdvb AND v.basal_units > 0
        ) AS nonzero_stddev,
        string_agg(v.source_hash::text, '' ORDER BY v.sales_date) AS feature_hashes
    FROM scope_pairs AS sp
    LEFT JOIN datamart.dm_pdd_venta_diaria AS v
        ON v.codigo_articulo = sp.codigo_articulo
       AND v.sucursal = sp.sucursal
       AND (
            v.sales_date BETWEEN CAST(:recent_start AS date) AND CAST(:recent_end AS date)
         OR v.sales_date BETWEEN CAST(:previous_start AS date) AND CAST(:previous_end AS date)
         OR v.sales_date BETWEEN CAST(:seasonal_start AS date) AND CAST(:seasonal_end AS date)
       )
    GROUP BY sp.codigo_articulo, sp.sucursal, sp.c_proveedor_primario
),
weighted AS (
    SELECT
        s.*,
        (
            CASE WHEN s.recent_eligible_days > 0 THEN CAST(:recent_base_weight AS numeric) ELSE 0 END
          + CASE WHEN s.previous_eligible_days > 0 THEN CAST(:previous_base_weight AS numeric) ELSE 0 END
          + CASE WHEN s.seasonal_eligible_days > 0 THEN CAST(:seasonal_base_weight AS numeric) ELSE 0 END
        ) AS available_weight,
        (s.recent_eligible_days + s.previous_eligible_days + s.seasonal_eligible_days)
            AS total_window_eligible_days
    FROM stats AS s
),
scored AS (
    SELECT
        w.*,
        CASE
            WHEN w.recent_eligible_days < :minimum_recent_eligible_days
              OR w.total_window_eligible_days < :minimum_total_eligible_days
              OR w.available_weight = 0
                THEN 0
            ELSE CASE WHEN w.recent_eligible_days > 0
                THEN CAST(:recent_base_weight AS numeric) / w.available_weight ELSE 0 END
        END::numeric(8,6) AS recent_weight,
        CASE
            WHEN w.recent_eligible_days < :minimum_recent_eligible_days
              OR w.total_window_eligible_days < :minimum_total_eligible_days
              OR w.available_weight = 0
                THEN 0
            ELSE CASE WHEN w.previous_eligible_days > 0
                THEN CAST(:previous_base_weight AS numeric) / w.available_weight ELSE 0 END
        END::numeric(8,6) AS previous_weight,
        CASE
            WHEN w.recent_eligible_days < :minimum_recent_eligible_days
              OR w.total_window_eligible_days < :minimum_total_eligible_days
              OR w.available_weight = 0
                THEN 0
            ELSE CASE WHEN w.seasonal_eligible_days > 0
                THEN CAST(:seasonal_base_weight AS numeric) / w.available_weight ELSE 0 END
        END::numeric(8,6) AS seasonal_weight,
        (
            w.recent_eligible_days < :minimum_recent_eligible_days
            OR w.total_window_eligible_days < :minimum_total_eligible_days
            OR w.available_weight = 0
        ) AS is_blocked,
        CASE WHEN w.active_days > 0
            THEN w.eligible_days::numeric / w.active_days ELSE 0 END AS availability_coverage,
        CASE WHEN w.eligible_days > 0
            THEN w.promo_reliable_days::numeric / w.eligible_days ELSE 0 END AS promo_coverage
    FROM weighted AS w
),
estimated AS (
    SELECT
        s.*,
        CASE WHEN s.is_blocked THEN NULL ELSE (
            coalesce(s.recent_mean, 0) * s.recent_weight
          + coalesce(s.previous_mean, 0) * s.previous_weight
          + coalesce(s.seasonal_mean, 0) * s.seasonal_weight
        ) END::numeric(18,6) AS pdvb_raw,
        CASE WHEN s.nonzero_days > 0
            THEN s.eligible_days::numeric / s.nonzero_days ELSE NULL END::numeric(18,6) AS adi,
        CASE
            WHEN s.nonzero_mean > 0 AND s.nonzero_stddev IS NOT NULL
            THEN power(s.nonzero_stddev / s.nonzero_mean, 2)
            ELSE NULL
        END::numeric(18,6) AS cv2
    FROM scored AS s
),
final AS (
    SELECT
        e.*,
        CASE
            WHEN e.is_blocked THEN 'BLOCKED'
            WHEN e.pdvb_raw = 0 THEN 'ZERO_VALID'
            WHEN e.availability_coverage < CAST(:warning_coverage AS numeric)
              OR e.previous_eligible_days = 0
              OR e.seasonal_eligible_days = 0 THEN 'WARN'
            ELSE 'OK'
        END::varchar(20) AS status,
        CASE
            WHEN e.is_blocked THEN 'INSUFFICIENT_DATA'
            WHEN e.previous_eligible_days = 0 AND e.seasonal_eligible_days = 0
                THEN 'SKU_BRANCH_RECENT'
            ELSE 'SKU_BRANCH_WEIGHTED'
        END::varchar(40) AS method_code,
        CASE
            WHEN e.is_blocked THEN 9
            WHEN e.previous_eligible_days = 0 AND e.seasonal_eligible_days = 0 THEN 2
            WHEN e.seasonal_eligible_days = 0 THEN 1
            ELSE 0
        END::smallint AS fallback_level,
        least(
            100,
            greatest(0, 100 * e.availability_coverage)
        )::numeric(5,2) AS confidence_score,
        encode(
            sha256(
                convert_to(
                    concat_ws('|',
                        CAST(:scope_version_uuid AS uuid)::text,
                        e.codigo_articulo::text,
                        e.sucursal::text,
                        CAST(:business_date AS date)::text,
                        coalesce(e.feature_hashes, '')
                    ),
                    'UTF8'
                )
            ),
            'hex'
        ) AS input_checksum
    FROM estimated AS e
)
INSERT INTO datamart.dm_pdd_pdvb_estimate_detail (
    business_date,
    calculation_run_uuid,
    model_version_uuid,
    scope_version_uuid,
    origin_cd,
    codigo_articulo,
    sucursal,
    c_proveedor_primario,
    method_code,
    fallback_level,
    status,
    confidence_score,
    lookback_start,
    lookback_end,
    recent_start,
    recent_end,
    recent_basal_units,
    recent_eligible_days,
    recent_mean,
    recent_weight,
    previous_start,
    previous_end,
    previous_basal_units,
    previous_eligible_days,
    previous_mean,
    previous_weight,
    seasonal_start,
    seasonal_end,
    seasonal_basal_units,
    seasonal_eligible_days,
    seasonal_mean,
    seasonal_weight,
    active_days,
    eligible_days,
    nonzero_days,
    availability_coverage,
    promo_coverage,
    adi,
    cv2,
    pdvb_raw,
    pdvb_value,
    explanation,
    input_checksum
)
SELECT
    CAST(:business_date AS date),
    CAST(:calculation_run_uuid AS uuid),
    CAST(:model_version_uuid AS uuid),
    CAST(:scope_version_uuid AS uuid),
    :origin_cd,
    codigo_articulo,
    sucursal,
    c_proveedor_primario,
    method_code,
    fallback_level,
    status,
    confidence_score,
    CAST(:seasonal_start AS date),
    CAST(:cutoff_date AS date),
    CAST(:recent_start AS date),
    CAST(:recent_end AS date),
    recent_basal_units,
    recent_eligible_days,
    recent_mean,
    recent_weight,
    CAST(:previous_start AS date),
    CAST(:previous_end AS date),
    previous_basal_units,
    previous_eligible_days,
    previous_mean,
    previous_weight,
    CAST(:seasonal_start AS date),
    CAST(:seasonal_end AS date),
    seasonal_basal_units,
    seasonal_eligible_days,
    seasonal_mean,
    seasonal_weight,
    active_days,
    eligible_days,
    nonzero_days,
    availability_coverage,
    promo_coverage,
    adi,
    cv2,
    pdvb_raw,
    pdvb_raw,
    jsonb_build_object(
        'cutoff_date', CAST(:cutoff_date AS date),
        'available_weight', available_weight,
        'minimum_recent_eligible_days', :minimum_recent_eligible_days,
        'minimum_total_eligible_days', :minimum_total_eligible_days
    ),
    input_checksum
FROM final
ON CONFLICT (business_date, calculation_run_uuid, codigo_articulo, sucursal)
DO NOTHING;
