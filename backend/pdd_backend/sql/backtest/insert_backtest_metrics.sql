WITH detail AS (
    SELECT *
    FROM datamart.dm_pdd_pdvb_backtest_detail
    WHERE calculation_run_uuid = CAST(:calculation_run_uuid AS uuid)
      AND evaluation_mode = :evaluation_mode
),
common_keys AS (
    SELECT
        evaluation_date,
        codigo_articulo,
        sucursal,
        forecast_origin_date
    FROM detail
    GROUP BY evaluation_date, codigo_articulo, sucursal, forecast_origin_date
    HAVING count(DISTINCT estimator_code) = :estimator_count
       AND bool_and(status = 'VALID')
),
sampled AS (
    SELECT 'OWN_VALID'::varchar(20) AS sample_code, d.*
    FROM detail AS d
    WHERE d.status = 'VALID'

    UNION ALL

    SELECT 'COMMON_VALID'::varchar(20) AS sample_code, d.*
    FROM detail AS d
    INNER JOIN common_keys AS k
        USING (evaluation_date, codigo_articulo, sucursal, forecast_origin_date)
),
segmented_samples AS (
    SELECT
        s.sample_code,
        s.estimator_code,
        segment.segment_type,
        segment.segment_id,
        s.actual_basal_units,
        s.predicted_horizon_units,
        s.error_units,
        s.absolute_error_units,
        s.squared_error
    FROM sampled AS s
    CROSS JOIN LATERAL (
        VALUES
            ('ALL'::varchar(40), 'ALL'::varchar(100)),
            ('BRANCH'::varchar(40), s.sucursal::varchar(100)),
            (
                'DEMAND_REGIME'::varchar(40),
                coalesce(s.demand_regime, 'UNCLASSIFIED')::varchar(100)
            ),
            (
                'RUBRO'::varchar(40),
                coalesce(s.rubro::text, 'UNCLASSIFIED')::varchar(100)
            ),
            (
                'SUBRUBRO_1'::varchar(40),
                concat_ws('/',
                    coalesce(s.rubro::text, 'UNCLASSIFIED'),
                    coalesce(s.subrubro_1::text, 'UNCLASSIFIED')
                )::varchar(100)
            ),
            ('FALLBACK_LEVEL'::varchar(40), s.fallback_level::varchar(100)),
            (
                'PREDICTION_STATUS'::varchar(40),
                s.prediction_status::varchar(100)
            )
    ) AS segment(segment_type, segment_id)
),
aggregated AS (
    SELECT
        sample_code,
        estimator_code,
        segment_type,
        segment_id,
        count(*)::bigint AS sample_size,
        count(*) FILTER (WHERE actual_basal_units = 0)::bigint AS zero_actual_count,
        sum(actual_basal_units)::numeric(24,6) AS actual_units_sum,
        sum(predicted_horizon_units)::numeric(24,6) AS predicted_units_sum,
        avg(absolute_error_units)::numeric(20,8) AS mae,
        CASE WHEN sum(actual_basal_units) > 0
            THEN (100 * sum(absolute_error_units) / sum(actual_basal_units))::numeric(20,8)
        END AS wape,
        CASE WHEN sum(actual_basal_units) > 0
            THEN (100 * sum(error_units) / sum(actual_basal_units))::numeric(20,8)
        END AS bias,
        sqrt(avg(squared_error))::numeric(20,8) AS rmse
    FROM segmented_samples
    GROUP BY sample_code, estimator_code, segment_type, segment_id
),
segmented_coverage AS (
    SELECT
        d.estimator_code,
        segment.segment_type,
        segment.segment_id,
        count(*)::bigint AS expected_count,
        count(*) FILTER (WHERE d.predicted_pdvb IS NOT NULL)::bigint AS prediction_count,
        count(*) FILTER (WHERE d.eligible_actual)::bigint AS eligible_actual_count
    FROM detail AS d
    CROSS JOIN LATERAL (
        VALUES
            ('ALL'::varchar(40), 'ALL'::varchar(100)),
            ('BRANCH'::varchar(40), d.sucursal::varchar(100)),
            (
                'DEMAND_REGIME'::varchar(40),
                coalesce(d.demand_regime, 'UNCLASSIFIED')::varchar(100)
            ),
            (
                'RUBRO'::varchar(40),
                coalesce(d.rubro::text, 'UNCLASSIFIED')::varchar(100)
            ),
            (
                'SUBRUBRO_1'::varchar(40),
                concat_ws('/',
                    coalesce(d.rubro::text, 'UNCLASSIFIED'),
                    coalesce(d.subrubro_1::text, 'UNCLASSIFIED')
                )::varchar(100)
            ),
            ('FALLBACK_LEVEL'::varchar(40), d.fallback_level::varchar(100)),
            (
                'PREDICTION_STATUS'::varchar(40),
                d.prediction_status::varchar(100)
            )
    ) AS segment(segment_type, segment_id)
    GROUP BY d.estimator_code, segment.segment_type, segment.segment_id
),
metric_rows AS (
    SELECT
        a.*,
        c.expected_count,
        c.prediction_count,
        c.eligible_actual_count,
        metric.metric_code,
        metric.metric_value
    FROM aggregated AS a
    INNER JOIN segmented_coverage AS c
        USING (estimator_code, segment_type, segment_id)
    CROSS JOIN LATERAL (
        VALUES
            ('MAE'::varchar(20), a.mae),
            ('WAPE'::varchar(20), a.wape),
            ('BIAS'::varchar(20), a.bias),
            ('RMSE'::varchar(20), a.rmse)
    ) AS metric(metric_code, metric_value)
    WHERE metric.metric_value IS NOT NULL
)
INSERT INTO datamart.dm_pdd_pdvb_backtest_metric (
    calculation_run_uuid,
    model_version_uuid,
    scope_version_uuid,
    evaluation_from,
    evaluation_to,
    forecast_horizon_days,
    evaluation_mode,
    estimator_code,
    sample_code,
    segment_type,
    segment_id,
    metric_code,
    metric_value,
    sample_size,
    expected_count,
    prediction_count,
    eligible_actual_count,
    zero_actual_count,
    actual_units_sum,
    predicted_units_sum
)
SELECT
    CAST(:calculation_run_uuid AS uuid),
    CAST(:model_version_uuid AS uuid),
    CAST(:scope_version_uuid AS uuid),
    CAST(:evaluation_from AS date),
    CAST(:evaluation_to AS date),
    :forecast_horizon_days,
    :evaluation_mode,
    estimator_code,
    sample_code,
    segment_type,
    segment_id,
    metric_code,
    metric_value,
    sample_size,
    expected_count,
    prediction_count,
    eligible_actual_count,
    zero_actual_count,
    actual_units_sum,
    predicted_units_sum
FROM metric_rows
ON CONFLICT (
    calculation_run_uuid,
    evaluation_mode,
    estimator_code,
    sample_code,
    segment_type,
    segment_id,
    metric_code
) DO NOTHING;
