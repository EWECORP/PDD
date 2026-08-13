WITH ranked_estimates AS (
    SELECT
        e.*,
        row_number() OVER (
            PARTITION BY e.business_date, e.codigo_articulo, e.sucursal
            ORDER BY e.created_at DESC, e.calculation_run_uuid DESC
        ) AS recency_rank
    FROM datamart.dm_pdd_pdvb_estimate_detail AS e
    WHERE e.model_version_uuid = CAST(:model_version_uuid AS uuid)
      AND e.scope_version_uuid = CAST(:scope_version_uuid AS uuid)
      AND e.origin_cd = :origin_cd
      AND (
            CAST(:forecast_origin_date AS date) IS NULL
            OR e.business_date = CAST(:forecast_origin_date AS date)
      )
      AND e.business_date + :forecast_horizon_days
            BETWEEN CAST(:evaluation_from AS date) AND CAST(:evaluation_to AS date)
      AND (
            CAST(:forecast_calculation_run_uuid AS uuid) IS NULL
            OR e.calculation_run_uuid = CAST(:forecast_calculation_run_uuid AS uuid)
      )
),
estimates AS (
    SELECT *
    FROM ranked_estimates
    WHERE recency_rank = 1
),
article_categories AS (
    SELECT DISTINCT ON (a.c_articulo::integer)
        a.c_articulo::integer AS codigo_articulo,
        a.c_rubro::integer AS rubro,
        a.c_subrubro_1::integer AS subrubro_1
    FROM src.m_3_articulos AS a
    ORDER BY a.c_articulo::integer
),
eligible_history AS (
    SELECT
        e.business_date,
        e.codigo_articulo,
        e.sucursal,
        v.sales_date,
        v.basal_units,
        CASE
            WHEN v.sales_date BETWEEN e.recent_start AND e.recent_end THEN 'RECENT'
            WHEN v.sales_date BETWEEN e.previous_start AND e.previous_end THEN 'PREVIOUS'
            ELSE 'SEASONAL'
        END AS window_code
    FROM estimates AS e
    INNER JOIN datamart.dm_pdd_venta_diaria AS v
        ON v.codigo_articulo = e.codigo_articulo
       AND v.sucursal = e.sucursal
       AND v.scope_version_uuid = e.scope_version_uuid
       AND v.eligible_for_pdvb
       AND (
            v.sales_date BETWEEN e.recent_start AND e.recent_end
         OR v.sales_date BETWEEN e.previous_start AND e.previous_end
         OR v.sales_date BETWEEN e.seasonal_start AND e.seasonal_end
       )
),
history_stats AS (
    SELECT
        business_date,
        codigo_articulo,
        sucursal,
        count(*) FILTER (
            WHERE window_code = 'RECENT' AND basal_units > 0
        )::integer AS recent_positive_days,
        count(*) FILTER (
            WHERE window_code = 'PREVIOUS' AND basal_units > 0
        )::integer AS previous_positive_days,
        count(*) FILTER (
            WHERE window_code = 'SEASONAL' AND basal_units > 0
        )::integer AS seasonal_positive_days,
        avg(basal_units) FILTER (
            WHERE window_code = 'RECENT' AND basal_units > 0
        )::numeric(18,6) AS recent_positive_mean,
        avg(basal_units) FILTER (
            WHERE window_code = 'PREVIOUS' AND basal_units > 0
        )::numeric(18,6) AS previous_positive_mean,
        avg(basal_units) FILTER (
            WHERE window_code = 'SEASONAL' AND basal_units > 0
        )::numeric(18,6) AS seasonal_positive_mean
    FROM eligible_history
    GROUP BY business_date, codigo_articulo, sucursal
),
current_history AS (
    SELECT
        h.*,
        row_number() OVER (
            PARTITION BY h.business_date, h.codigo_articulo, h.sucursal
            ORDER BY h.sales_date
        )::integer AS eligible_sequence
    FROM eligible_history AS h
    WHERE h.window_code IN ('RECENT', 'PREVIOUS')
),
positive_events AS (
    SELECT
        business_date,
        codigo_articulo,
        sucursal,
        basal_units,
        row_number() OVER (
            PARTITION BY business_date, codigo_articulo, sucursal
            ORDER BY sales_date
        )::integer AS event_sequence,
        count(*) OVER (
            PARTITION BY business_date, codigo_articulo, sucursal
        )::integer AS event_count,
        (
            eligible_sequence
            - lag(eligible_sequence, 1, 0) OVER (
                PARTITION BY business_date, codigo_articulo, sucursal
                ORDER BY sales_date
            )
        )::numeric AS inter_demand_interval
    FROM current_history
    WHERE basal_units > 0
),
croston_stats AS (
    SELECT
        business_date,
        codigo_articulo,
        sucursal,
        max(event_count)::integer AS croston_event_count,
        (
            sum(
                CASE
                    WHEN event_sequence = 1 THEN
                        basal_units * power(
                            1 - CAST(:croston_alpha AS numeric),
                            event_count - 1
                        )
                    ELSE
                        CAST(:croston_alpha AS numeric) * basal_units * power(
                            1 - CAST(:croston_alpha AS numeric),
                            event_count - event_sequence
                        )
                END
            )
            /
            nullif(
                sum(
                    CASE
                        WHEN event_sequence = 1 THEN
                            inter_demand_interval * power(
                                1 - CAST(:croston_alpha AS numeric),
                                event_count - 1
                            )
                        ELSE
                            CAST(:croston_alpha AS numeric)
                            * inter_demand_interval * power(
                                1 - CAST(:croston_alpha AS numeric),
                                event_count - event_sequence
                            )
                    END
                ),
                0
            )
            * (1 - CAST(:croston_alpha AS numeric) / 2)
        )::numeric(18,6) AS croston_sba_value
    FROM positive_events
    GROUP BY business_date, codigo_articulo, sucursal
),
features AS (
    SELECT
        e.*,
        c.rubro,
        c.subrubro_1,
        coalesce(h.recent_positive_days, 0) AS recent_positive_days,
        coalesce(h.previous_positive_days, 0) AS previous_positive_days,
        coalesce(h.seasonal_positive_days, 0) AS seasonal_positive_days,
        h.recent_positive_mean,
        h.previous_positive_mean,
        h.seasonal_positive_mean,
        coalesce(cr.croston_event_count, 0) AS croston_event_count,
        cr.croston_sba_value,
        CASE
            WHEN e.nonzero_days = 0 THEN 'NO_DEMAND'
            WHEN e.adi IS NULL THEN 'UNCLASSIFIED'
            WHEN e.cv2 IS NULL THEN 'SPARSE'
            WHEN e.adi <= CAST(:adi_threshold AS numeric)
             AND e.cv2 <= CAST(:cv2_threshold AS numeric) THEN 'SMOOTH'
            WHEN e.adi <= CAST(:adi_threshold AS numeric)
             AND e.cv2 > CAST(:cv2_threshold AS numeric) THEN 'ERRATIC'
            WHEN e.adi > CAST(:adi_threshold AS numeric)
             AND e.cv2 <= CAST(:cv2_threshold AS numeric) THEN 'INTERMITTENT'
            ELSE 'LUMPY'
        END::varchar(20) AS demand_regime,
        (
            CAST(:algo01_recent_weight AS numeric) * coalesce(e.recent_mean, 0)
          + CAST(:algo01_previous_weight AS numeric) * coalesce(e.previous_mean, 0)
          + CAST(:algo01_seasonal_weight AS numeric) * coalesce(e.seasonal_mean, 0)
        )::numeric(18,6) AS algo01_growth_value,
        (
            (
                CAST(:algo01_recent_weight AS numeric) * coalesce(e.recent_mean, 0)
              + CAST(:algo01_previous_weight AS numeric) * coalesce(e.previous_mean, 0)
              + CAST(:algo01_seasonal_weight AS numeric) * coalesce(e.seasonal_mean, 0)
            )
            /
            nullif(
                CASE WHEN e.recent_eligible_days > 0
                    THEN CAST(:algo01_recent_weight AS numeric) ELSE 0 END
              + CASE WHEN e.previous_eligible_days > 0
                    THEN CAST(:algo01_previous_weight AS numeric) ELSE 0 END
              + CASE WHEN e.seasonal_eligible_days > 0
                    THEN CAST(:algo01_seasonal_weight AS numeric) ELSE 0 END,
                0
            )
        )::numeric(18,6) AS algo01_normalized_value,
        (
            (
                CAST(:occurrence_recent_weight AS numeric)
                    * coalesce(h.recent_positive_days, 0)
                    / nullif(e.recent_eligible_days, 0)
              + CAST(:occurrence_previous_weight AS numeric)
                    * coalesce(h.previous_positive_days, 0)
                    / nullif(e.previous_eligible_days, 0)
              + CAST(:occurrence_seasonal_weight AS numeric)
                    * coalesce(h.seasonal_positive_days, 0)
                    / nullif(e.seasonal_eligible_days, 0)
            )
            /
            nullif(
                CASE WHEN e.recent_eligible_days > 0
                    THEN CAST(:occurrence_recent_weight AS numeric) ELSE 0 END
              + CASE WHEN e.previous_eligible_days > 0
                    THEN CAST(:occurrence_previous_weight AS numeric) ELSE 0 END
              + CASE WHEN e.seasonal_eligible_days > 0
                    THEN CAST(:occurrence_seasonal_weight AS numeric) ELSE 0 END,
                0
            )
            *
            (
                CAST(:occurrence_recent_weight AS numeric)
                    * coalesce(h.recent_positive_mean, 0)
              + CAST(:occurrence_previous_weight AS numeric)
                    * coalesce(h.previous_positive_mean, 0)
              + CAST(:occurrence_seasonal_weight AS numeric)
                    * coalesce(h.seasonal_positive_mean, 0)
            )
            /
            nullif(
                CASE WHEN coalesce(h.recent_positive_days, 0) > 0
                    THEN CAST(:occurrence_recent_weight AS numeric) ELSE 0 END
              + CASE WHEN coalesce(h.previous_positive_days, 0) > 0
                    THEN CAST(:occurrence_previous_weight AS numeric) ELSE 0 END
              + CASE WHEN coalesce(h.seasonal_positive_days, 0) > 0
                    THEN CAST(:occurrence_seasonal_weight AS numeric) ELSE 0 END,
                0
            )
        )::numeric(18,6) AS occurrence_size_value
    FROM estimates AS e
    LEFT JOIN history_stats AS h
        USING (business_date, codigo_articulo, sucursal)
    LEFT JOIN croston_stats AS cr
        USING (business_date, codigo_articulo, sucursal)
    LEFT JOIN article_categories AS c USING (codigo_articulo)
),
hybrid AS (
    SELECT
        f.*,
        CASE
            WHEN f.demand_regime IN ('INTERMITTENT', 'LUMPY', 'SPARSE')
             AND f.croston_event_count >= 2
                THEN f.croston_sba_value
            WHEN f.status <> 'BLOCKED'
                THEN f.pdvb_value
            WHEN f.algo01_normalized_value IS NOT NULL
                THEN f.algo01_normalized_value
            ELSE NULL
        END::numeric(18,6) AS hybrid_value,
        CASE
            WHEN f.demand_regime IN ('INTERMITTENT', 'LUMPY', 'SPARSE')
             AND f.croston_event_count >= 2 THEN 'CROSTON_SBA'
            WHEN f.status <> 'BLOCKED' THEN 'PDVB_CANDIDATE'
            WHEN f.algo01_normalized_value IS NOT NULL THEN 'ALGO_01_NORMALIZED_FALLBACK'
            ELSE 'BLOCKED'
        END::varchar(40) AS hybrid_component
    FROM features AS f
),
predictions AS (
    SELECT
        h.business_date AS forecast_origin_date,
        h.calculation_run_uuid AS forecast_calculation_run_uuid,
        h.codigo_articulo,
        h.sucursal,
        h.rubro,
        h.subrubro_1,
        h.demand_regime,
        candidate.estimator_code,
        candidate.fallback_level,
        candidate.prediction_status,
        candidate.predicted_pdvb::numeric(18,6) AS predicted_pdvb,
        candidate.estimator_parameters,
        h.input_checksum AS estimate_checksum
    FROM hybrid AS h
    CROSS JOIN LATERAL (
        VALUES
            (
                'PDVB_CANDIDATE'::varchar(40),
                h.fallback_level,
                h.status::varchar(20),
                h.pdvb_value,
                jsonb_build_object('source', 'PDVB_V3')
            ),
            (
                'MEAN_28'::varchar(40),
                2::smallint,
                CASE
                    WHEN h.recent_eligible_days = 0 THEN 'BLOCKED'
                    WHEN h.recent_mean = 0 THEN 'ZERO_VALID'
                    ELSE 'OK'
                END::varchar(20),
                CASE WHEN h.recent_eligible_days > 0 THEN h.recent_mean END,
                jsonb_build_object('recent_days', 28)
            ),
            (
                'ALGO_01_GROWTH'::varchar(40),
                3::smallint,
                CASE
                    WHEN h.algo01_normalized_value IS NULL THEN 'BLOCKED'
                    WHEN h.algo01_growth_value = 0 THEN 'ZERO_VALID'
                    ELSE 'OK'
                END::varchar(20),
                CASE WHEN h.algo01_normalized_value IS NOT NULL
                    THEN h.algo01_growth_value END,
                jsonb_build_object(
                    'weights', jsonb_build_array(
                        CAST(:algo01_recent_weight AS numeric),
                        CAST(:algo01_previous_weight AS numeric),
                        CAST(:algo01_seasonal_weight AS numeric)
                    ),
                    'normalization', 'NONE',
                    'intent', 'GROWTH_UPLIFT'
                )
            ),
            (
                'ALGO_01_NORMALIZED'::varchar(40),
                3::smallint,
                CASE
                    WHEN h.algo01_normalized_value IS NULL THEN 'BLOCKED'
                    WHEN h.algo01_normalized_value = 0 THEN 'ZERO_VALID'
                    ELSE 'OK'
                END::varchar(20),
                h.algo01_normalized_value,
                jsonb_build_object(
                    'weights', jsonb_build_array(
                        CAST(:algo01_recent_weight AS numeric),
                        CAST(:algo01_previous_weight AS numeric),
                        CAST(:algo01_seasonal_weight AS numeric)
                    ),
                    'normalization', 'AVAILABLE_WINDOWS'
                )
            ),
            (
                'OCCURRENCE_SIZE'::varchar(40),
                5::smallint,
                CASE
                    WHEN h.eligible_days > 0 AND h.nonzero_days = 0
                        THEN 'ZERO_VALID'
                    WHEN h.occurrence_size_value IS NULL THEN 'BLOCKED'
                    WHEN h.occurrence_size_value = 0 THEN 'ZERO_VALID'
                    ELSE 'WARN'
                END::varchar(20),
                CASE
                    WHEN h.eligible_days > 0 AND h.nonzero_days = 0 THEN 0
                    ELSE h.occurrence_size_value
                END,
                jsonb_build_object(
                    'method', 'WEIGHTED_OCCURRENCE_X_POSITIVE_SIZE',
                    'weights', jsonb_build_array(
                        CAST(:occurrence_recent_weight AS numeric),
                        CAST(:occurrence_previous_weight AS numeric),
                        CAST(:occurrence_seasonal_weight AS numeric)
                    )
                )
            ),
            (
                'CROSTON_SBA'::varchar(40),
                6::smallint,
                CASE
                    WHEN h.eligible_days > 0 AND h.nonzero_days = 0
                        THEN 'ZERO_VALID'
                    WHEN h.croston_sba_value IS NULL THEN 'BLOCKED'
                    ELSE 'WARN'
                END::varchar(20),
                CASE
                    WHEN h.eligible_days > 0 AND h.nonzero_days = 0 THEN 0
                    ELSE h.croston_sba_value
                END,
                jsonb_build_object(
                    'alpha', CAST(:croston_alpha AS numeric),
                    'event_count', h.croston_event_count,
                    'history', 'RECENT_PLUS_PREVIOUS',
                    'bias_correction', 'SBA'
                )
            ),
            (
                'HYBRID_EXPERIMENTAL'::varchar(40),
                CASE
                    WHEN h.hybrid_component = 'PDVB_CANDIDATE' THEN h.fallback_level
                    WHEN h.hybrid_component = 'CROSTON_SBA' THEN 6
                    WHEN h.hybrid_component = 'ALGO_01_NORMALIZED_FALLBACK' THEN 4
                    ELSE 9
                END::smallint,
                CASE
                    WHEN h.hybrid_value IS NULL THEN 'BLOCKED'
                    WHEN h.hybrid_value = 0 THEN 'ZERO_VALID'
                    WHEN h.hybrid_component = 'PDVB_CANDIDATE' THEN h.status
                    ELSE 'WARN'
                END::varchar(20),
                h.hybrid_value,
                jsonb_build_object(
                    'component', h.hybrid_component,
                    'demand_regime', h.demand_regime,
                    'adi_threshold', CAST(:adi_threshold AS numeric),
                    'cv2_threshold', CAST(:cv2_threshold AS numeric)
                )
            )
    ) AS candidate(
        estimator_code,
        fallback_level,
        prediction_status,
        predicted_pdvb,
        estimator_parameters
    )
),
actual_windows AS (
    SELECT
        e.business_date AS forecast_origin_date,
        e.codigo_articulo,
        e.sucursal,
        CASE
            WHEN :evaluation_mode = 'POINT_DAILY'
                THEN e.business_date + :forecast_horizon_days
            ELSE e.business_date + 1
        END AS evaluation_window_start,
        e.business_date + :forecast_horizon_days AS evaluation_date,
        CASE
            WHEN :evaluation_mode = 'POINT_DAILY' THEN 1
            ELSE :forecast_horizon_days
        END::integer AS actual_window_days
    FROM estimates AS e
),
actuals AS (
    SELECT
        w.forecast_origin_date,
        w.codigo_articulo,
        w.sucursal,
        w.evaluation_window_start,
        w.evaluation_date,
        w.actual_window_days,
        count(v.*)::integer AS actual_rows,
        count(v.*) FILTER (WHERE v.eligible_for_pdvb)::integer AS actual_eligible_days,
        sum(v.basal_units) FILTER (
            WHERE v.eligible_for_pdvb
        )::numeric(24,6) AS observed_eligible_basal_units,
        string_agg(v.source_hash::text, '' ORDER BY v.sales_date) AS actual_hashes
    FROM actual_windows AS w
    LEFT JOIN datamart.dm_pdd_venta_diaria AS v
        ON v.codigo_articulo = w.codigo_articulo
       AND v.sucursal = w.sucursal
       AND v.scope_version_uuid = CAST(:scope_version_uuid AS uuid)
       AND v.sales_date BETWEEN w.evaluation_window_start AND w.evaluation_date
    GROUP BY
        w.forecast_origin_date,
        w.codigo_articulo,
        w.sucursal,
        w.evaluation_window_start,
        w.evaluation_date,
        w.actual_window_days
),
observations AS (
    SELECT
        p.*,
        a.evaluation_window_start,
        a.evaluation_date,
        a.actual_window_days,
        a.actual_rows,
        a.actual_eligible_days,
        CASE WHEN a.actual_window_days > 0
            THEN a.actual_eligible_days::numeric / a.actual_window_days
            ELSE 0
        END::numeric(8,6) AS actual_availability_coverage,
        CASE
            WHEN a.actual_eligible_days > 0 THEN
                a.observed_eligible_basal_units
                * a.actual_window_days / a.actual_eligible_days
        END::numeric(18,6) AS actual_basal_units,
        (
            a.actual_eligible_days::numeric / nullif(a.actual_window_days, 0)
            >= CAST(:actual_min_coverage AS numeric)
        ) AS eligible_actual,
        (
            p.predicted_pdvb * a.actual_window_days
        )::numeric(18,6) AS predicted_horizon_units,
        a.actual_hashes
    FROM predictions AS p
    INNER JOIN actuals AS a
        USING (forecast_origin_date, codigo_articulo, sucursal)
),
prepared AS (
    SELECT
        o.*,
        CASE
            WHEN o.prediction_status = 'BLOCKED' OR o.predicted_pdvb IS NULL
                THEN 'BLOCKED'
            WHEN NOT o.eligible_actual OR o.actual_basal_units IS NULL
                THEN 'EXCLUDED'
            ELSE 'VALID'
        END::varchar(20) AS status,
        CASE
            WHEN o.prediction_status <> 'BLOCKED'
             AND o.predicted_horizon_units IS NOT NULL
             AND o.eligible_actual
             AND o.actual_basal_units IS NOT NULL
            THEN (o.actual_basal_units - o.predicted_horizon_units)::numeric(18,6)
        END AS error_units,
        CASE
            WHEN o.prediction_status <> 'BLOCKED'
             AND o.predicted_horizon_units IS NOT NULL
             AND o.eligible_actual
             AND o.actual_basal_units IS NOT NULL
            THEN abs(o.actual_basal_units - o.predicted_horizon_units)::numeric(18,6)
        END AS absolute_error_units,
        CASE
            WHEN o.prediction_status <> 'BLOCKED'
             AND o.predicted_horizon_units IS NOT NULL
             AND o.eligible_actual
             AND o.actual_basal_units IS NOT NULL
            THEN power(o.actual_basal_units - o.predicted_horizon_units, 2)::numeric(24,8)
        END AS squared_error,
        array_remove(ARRAY[
            CASE WHEN o.prediction_status = 'BLOCKED' OR o.predicted_pdvb IS NULL
                THEN 'PREDICTION_BLOCKED' END,
            CASE WHEN o.actual_rows = 0 THEN 'ACTUAL_MISSING' END,
            CASE WHEN o.actual_rows > 0 AND NOT o.eligible_actual
                THEN 'ACTUAL_COVERAGE_LOW' END
        ]::text[], NULL) AS exclusion_codes,
        encode(
            sha256(
                convert_to(
                    concat_ws('|',
                        o.estimate_checksum,
                        coalesce(o.actual_hashes, ''),
                        o.estimator_code,
                        o.estimator_parameters::text,
                        :evaluation_mode,
                        o.evaluation_window_start::text,
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
    forecast_calculation_run_uuid,
    model_version_uuid,
    scope_version_uuid,
    origin_cd,
    codigo_articulo,
    sucursal,
    forecast_origin_date,
    forecast_horizon_days,
    evaluation_mode,
    evaluation_window_start,
    actual_window_days,
    actual_eligible_days,
    actual_availability_coverage,
    estimator_code,
    estimator_parameters,
    fallback_level,
    prediction_status,
    demand_regime,
    rubro,
    subrubro_1,
    predicted_pdvb,
    predicted_horizon_units,
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
    forecast_calculation_run_uuid,
    CAST(:model_version_uuid AS uuid),
    CAST(:scope_version_uuid AS uuid),
    :origin_cd,
    codigo_articulo,
    sucursal,
    forecast_origin_date,
    :forecast_horizon_days,
    :evaluation_mode,
    evaluation_window_start,
    actual_window_days,
    actual_eligible_days,
    actual_availability_coverage,
    estimator_code,
    estimator_parameters,
    fallback_level,
    prediction_status,
    demand_regime,
    rubro,
    subrubro_1,
    predicted_pdvb,
    predicted_horizon_units,
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
    forecast_horizon_days,
    evaluation_mode,
    estimator_code
) DO NOTHING;
