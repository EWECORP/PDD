\set ON_ERROR_STOP on

BEGIN;

DO $guard$
BEGIN
    IF current_database() <> 'diarco_data' THEN
        RAISE EXCEPTION
            'Migracion PDD backtest rolling: base incorrecta (%). Se esperaba diarco_data.',
            current_database();
    END IF;
END
$guard$;

DO $precondition$
BEGIN
    IF EXISTS (
        SELECT 1 FROM datamart.dm_pdd_pdvb_backtest_detail LIMIT 1
    ) THEN
        RAISE EXCEPTION
            'La tabla dm_pdd_pdvb_backtest_detail contiene datos del contrato anterior. Deben archivarse y validarse antes de aplicar v2.4.';
    END IF;
END
$precondition$;

ALTER TABLE datamart.dm_pdd_pdvb_backtest_detail
    ADD COLUMN forecast_calculation_run_uuid uuid,
    ADD COLUMN estimator_code varchar(40) NOT NULL DEFAULT 'PDVB_CANDIDATE',
    ADD COLUMN estimator_parameters jsonb NOT NULL DEFAULT '{}'::jsonb,
    ADD COLUMN fallback_level smallint NOT NULL DEFAULT 0,
    ADD COLUMN prediction_status varchar(20) NOT NULL DEFAULT 'OK';

ALTER TABLE datamart.dm_pdd_pdvb_backtest_detail
    ALTER COLUMN forecast_calculation_run_uuid SET NOT NULL,
    ALTER COLUMN predicted_pdvb DROP NOT NULL,
    ALTER COLUMN actual_basal_units DROP NOT NULL,
    ALTER COLUMN error_units DROP NOT NULL,
    ALTER COLUMN absolute_error_units DROP NOT NULL,
    ALTER COLUMN squared_error DROP NOT NULL,
    ALTER COLUMN estimator_code DROP DEFAULT,
    ALTER COLUMN prediction_status DROP DEFAULT;

ALTER TABLE datamart.dm_pdd_pdvb_backtest_detail
    DROP CONSTRAINT uq_dm_pdd_backtest_detail,
    DROP CONSTRAINT IF EXISTS dm_pdd_pdvb_backtest_detail_status_check,
    DROP CONSTRAINT IF EXISTS dm_pdd_pdvb_backtest_detail_predicted_pdvb_check,
    DROP CONSTRAINT IF EXISTS dm_pdd_pdvb_backtest_detail_actual_basal_units_check,
    DROP CONSTRAINT IF EXISTS dm_pdd_pdvb_backtest_detail_absolute_error_units_check,
    DROP CONSTRAINT IF EXISTS dm_pdd_pdvb_backtest_detail_squared_error_check;

ALTER TABLE datamart.dm_pdd_pdvb_backtest_detail
    ADD CONSTRAINT uq_dm_pdd_backtest_detail UNIQUE (
        evaluation_date, calculation_run_uuid, codigo_articulo, sucursal,
        forecast_origin_date, forecast_horizon_days, estimator_code
    ),
    ADD CONSTRAINT ck_dm_pdd_backtest_estimator CHECK (
        estimator_code IN (
            'PDVB_CANDIDATE', 'MEAN_28',
            'ALGO_01_GROWTH', 'ALGO_01_NORMALIZED'
        )
    ),
    ADD CONSTRAINT ck_dm_pdd_backtest_fallback CHECK (
        fallback_level BETWEEN 0 AND 9
    ),
    ADD CONSTRAINT ck_dm_pdd_backtest_prediction_status CHECK (
        prediction_status IN ('OK', 'WARN', 'BLOCKED', 'ZERO_VALID')
    ),
    ADD CONSTRAINT ck_dm_pdd_backtest_status CHECK (
        status IN ('VALID', 'EXCLUDED', 'BLOCKED')
    ),
    ADD CONSTRAINT ck_dm_pdd_backtest_prediction CHECK (
        (prediction_status = 'BLOCKED' AND predicted_pdvb IS NULL)
        OR (
            prediction_status <> 'BLOCKED'
            AND predicted_pdvb IS NOT NULL
            AND predicted_pdvb >= 0
        )
    ),
    ADD CONSTRAINT ck_dm_pdd_backtest_actual CHECK (
        actual_basal_units IS NULL OR actual_basal_units >= 0
    ),
    ADD CONSTRAINT ck_dm_pdd_backtest_errors CHECK (
        (
            status = 'VALID'
            AND eligible_actual
            AND predicted_pdvb IS NOT NULL
            AND actual_basal_units IS NOT NULL
            AND error_units IS NOT NULL
            AND absolute_error_units >= 0
            AND squared_error >= 0
        )
        OR (
            status <> 'VALID'
            AND error_units IS NULL
            AND absolute_error_units IS NULL
            AND squared_error IS NULL
        )
    );

CREATE INDEX ix_dm_pdd_backtest_run_estimator
    ON datamart.dm_pdd_pdvb_backtest_detail
    (calculation_run_uuid, estimator_code, status);

CREATE TABLE datamart.dm_pdd_pdvb_backtest_run (
    calculation_run_uuid uuid PRIMARY KEY,
    model_version_uuid uuid NOT NULL,
    scope_version_uuid uuid NOT NULL,
    origin_cd integer NOT NULL CHECK (origin_cd = 41),
    origin_from date NOT NULL,
    origin_to date NOT NULL,
    evaluation_from date NOT NULL,
    evaluation_to date NOT NULL,
    forecast_horizon_days integer NOT NULL CHECK (forecast_horizon_days > 0),
    origin_count integer NOT NULL CHECK (origin_count > 0),
    completed_origin_count integer NOT NULL DEFAULT 0 CHECK (completed_origin_count >= 0),
    estimator_codes varchar(40)[] NOT NULL,
    parameters jsonb NOT NULL,
    status varchar(20) NOT NULL CHECK (status IN ('RUNNING', 'COMPLETED', 'FAILED')),
    estimate_row_count bigint NOT NULL DEFAULT 0 CHECK (estimate_row_count >= 0),
    detail_row_count bigint NOT NULL DEFAULT 0 CHECK (detail_row_count >= 0),
    metric_row_count bigint NOT NULL DEFAULT 0 CHECK (metric_row_count >= 0),
    error_message text,
    started_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    completed_at timestamptz,
    CHECK (origin_to >= origin_from),
    CHECK (evaluation_to >= evaluation_from),
    CHECK (evaluation_from - origin_from = forecast_horizon_days),
    CHECK (evaluation_to - origin_to = forecast_horizon_days),
    CHECK (completed_origin_count <= origin_count),
    CHECK (
        (status = 'RUNNING' AND completed_at IS NULL)
        OR (status IN ('COMPLETED', 'FAILED') AND completed_at IS NOT NULL)
    )
);

CREATE INDEX ix_dm_pdd_backtest_run_model_period
    ON datamart.dm_pdd_pdvb_backtest_run
    (model_version_uuid, scope_version_uuid, evaluation_to DESC);

CREATE TABLE datamart.dm_pdd_pdvb_backtest_metric (
    backtest_metric_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    calculation_run_uuid uuid NOT NULL
        REFERENCES datamart.dm_pdd_pdvb_backtest_run(calculation_run_uuid)
        ON DELETE RESTRICT,
    model_version_uuid uuid NOT NULL,
    scope_version_uuid uuid NOT NULL,
    evaluation_from date NOT NULL,
    evaluation_to date NOT NULL,
    forecast_horizon_days integer NOT NULL CHECK (forecast_horizon_days > 0),
    estimator_code varchar(40) NOT NULL,
    sample_code varchar(20) NOT NULL CHECK (
        sample_code IN ('OWN_VALID', 'COMMON_VALID')
    ),
    segment_type varchar(40) NOT NULL,
    segment_id varchar(100) NOT NULL,
    metric_code varchar(20) NOT NULL CHECK (
        metric_code IN ('MAE', 'WAPE', 'BIAS', 'RMSE')
    ),
    metric_value numeric(20,8) NOT NULL,
    sample_size bigint NOT NULL CHECK (sample_size > 0),
    expected_count bigint NOT NULL CHECK (expected_count > 0),
    prediction_count bigint NOT NULL CHECK (prediction_count >= 0),
    eligible_actual_count bigint NOT NULL CHECK (eligible_actual_count >= 0),
    zero_actual_count bigint NOT NULL CHECK (zero_actual_count >= 0),
    actual_units_sum numeric(24,6) NOT NULL CHECK (actual_units_sum >= 0),
    predicted_units_sum numeric(24,6) NOT NULL CHECK (predicted_units_sum >= 0),
    calculated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    UNIQUE (
        calculation_run_uuid, estimator_code, sample_code,
        segment_type, segment_id, metric_code
    ),
    CHECK (evaluation_to >= evaluation_from),
    CHECK (prediction_count <= expected_count),
    CHECK (eligible_actual_count <= expected_count),
    CHECK (sample_size <= expected_count)
);

CREATE INDEX ix_dm_pdd_backtest_metric_compare
    ON datamart.dm_pdd_pdvb_backtest_metric
    (calculation_run_uuid, sample_code, segment_type, metric_code, metric_value);

COMMENT ON COLUMN datamart.dm_pdd_pdvb_backtest_detail.estimator_code IS
'PDVB_CANDIDATE es el modelo versionado; ALGO_01_GROWTH conserva 0.8+0.1+0.2 sin normalizar; ALGO_01_NORMALIZED aisla el efecto del uplift.';

COMMENT ON COLUMN datamart.dm_pdd_pdvb_backtest_metric.metric_value IS
'BIAS usa actual-pronostico: positivo indica subpronostico y negativo sobrepronostico. WAPE y BIAS se expresan en porcentaje.';

COMMIT;
