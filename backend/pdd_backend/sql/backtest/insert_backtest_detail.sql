WITH estimates AS (
    SELECT
        e.business_date AS forecast_origin_date,
        e.codigo_articulo,
        e.sucursal,
        e.pdvb_value AS predicted_pdvb,
        e.input_checksum AS estimate_checksum
    FROM datamart.dm_pdd_pdvb_estimate_detail AS e
    WHERE e.model_version_uuid = CAST(:model_version_uuid AS uuid)
      AND e.scope_version_uuid = CAST(:scope_version_uuid AS uuid)
      AND e.origin_cd = :origin_cd
      AND e.status <> 'BLOCKED'
      AND e.business_date + :forecast_horizon_days
            BETWEEN CAST(:evaluation_from AS date) AND CAST(:evaluation_to AS date)
),
observations AS (
    SELECT
        e.*,
        e.forecast_origin_date + :forecast_horizon_days AS evaluation_date,
        coalesce(v.basal_units, 0)::numeric(18,6) AS actual_basal_units,
        coalesce(v.eligible_for_pdvb, false) AS eligible_actual,
        v.source_hash AS actual_checksum
    FROM estimates AS e
    LEFT JOIN datamart.dm_pdd_venta_diaria AS v
        ON v.sales_date = e.forecast_origin_date + :forecast_horizon_days
       AND v.codigo_articulo = e.codigo_articulo
       AND v.sucursal = e.sucursal
),
prepared AS (
    SELECT
        o.*,
        (o.actual_basal_units - o.predicted_pdvb)::numeric(18,6) AS error_units,
        abs(o.actual_basal_units - o.predicted_pdvb)::numeric(18,6)
            AS absolute_error_units,
        power(o.actual_basal_units - o.predicted_pdvb, 2)::numeric(24,8)
            AS squared_error,
        CASE WHEN o.eligible_actual THEN 'VALID' ELSE 'EXCLUDED' END::varchar(20)
            AS status,
        CASE WHEN o.eligible_actual THEN ARRAY[]::text[]
             ELSE ARRAY['ACTUAL_NOT_SERVICEABLE']::text[] END AS exclusion_codes,
        encode(
            sha256(
                convert_to(
                    concat_ws('|',
                        o.estimate_checksum,
                        coalesce(o.actual_checksum::text, ''),
                        o.evaluation_date::text,
                        CAST(:forecast_horizon_days AS text)
                    ),
                    'UTF8'
                )
            ),
            'hex'
        ) AS input_checksum
    FROM observations AS o
)
INSERT INTO datamart.dm_pdd_pdvb_backtest_detail (
    evaluation_date,
    calculation_run_uuid,
    model_version_uuid,
    scope_version_uuid,
    origin_cd,
    codigo_articulo,
    sucursal,
    forecast_origin_date,
    forecast_horizon_days,
    predicted_pdvb,
    actual_basal_units,
    eligible_actual,
    error_units,
    absolute_error_units,
    squared_error,
    status,
    exclusion_codes,
    input_checksum
)
SELECT
    evaluation_date,
    CAST(:calculation_run_uuid AS uuid),
    CAST(:model_version_uuid AS uuid),
    CAST(:scope_version_uuid AS uuid),
    :origin_cd,
    codigo_articulo,
    sucursal,
    forecast_origin_date,
    :forecast_horizon_days,
    predicted_pdvb,
    actual_basal_units,
    eligible_actual,
    error_units,
    absolute_error_units,
    squared_error,
    status,
    exclusion_codes,
    input_checksum
FROM prepared
ON CONFLICT (
    evaluation_date,
    calculation_run_uuid,
    codigo_articulo,
    sucursal,
    forecast_origin_date,
    forecast_horizon_days
) DO NOTHING;
