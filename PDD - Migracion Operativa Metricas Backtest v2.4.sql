\set ON_ERROR_STOP on

BEGIN;

DO $guard$
BEGIN
    IF current_database() NOT IN ('connexa_platform_test', 'connexa_platform_ms') THEN
        RAISE EXCEPTION
            'Migracion PDD operativa: base incorrecta (%).', current_database();
    END IF;
END
$guard$;

ALTER TABLE stock_management.pdvb_backtest_metric
    ADD COLUMN estimator_code varchar(40) NOT NULL DEFAULT 'PDVB_CANDIDATE',
    ADD COLUMN sample_code varchar(20) NOT NULL DEFAULT 'OWN_VALID',
    ADD COLUMN expected_count bigint,
    ADD COLUMN prediction_count bigint,
    ADD COLUMN eligible_actual_count bigint;

UPDATE stock_management.pdvb_backtest_metric
SET expected_count = sample_size,
    prediction_count = sample_size,
    eligible_actual_count = sample_size
WHERE expected_count IS NULL
   OR prediction_count IS NULL
   OR eligible_actual_count IS NULL;

ALTER TABLE stock_management.pdvb_backtest_metric
    ALTER COLUMN estimator_code DROP DEFAULT,
    ALTER COLUMN sample_code DROP DEFAULT,
    ALTER COLUMN expected_count SET NOT NULL,
    ALTER COLUMN prediction_count SET NOT NULL,
    ALTER COLUMN eligible_actual_count SET NOT NULL,
    DROP CONSTRAINT uq_pdvb_backtest_metric;

ALTER TABLE stock_management.pdvb_backtest_metric
    ADD CONSTRAINT ck_pdvb_backtest_estimator CHECK (
        estimator_code IN (
            'PDVB_CANDIDATE', 'MEAN_28',
            'ALGO_01_GROWTH', 'ALGO_01_NORMALIZED'
        )
    ),
    ADD CONSTRAINT ck_pdvb_backtest_sample CHECK (
        sample_code IN ('OWN_VALID', 'COMMON_VALID')
    ),
    ADD CONSTRAINT ck_pdvb_backtest_coverage_counts CHECK (
        expected_count > 0
        AND prediction_count BETWEEN 0 AND expected_count
        AND eligible_actual_count BETWEEN 0 AND expected_count
        AND sample_size <= expected_count
    ),
    ADD CONSTRAINT uq_pdvb_backtest_metric UNIQUE (
        calculation_run_id, evaluation_from, evaluation_to,
        forecast_horizon_days, estimator_code, sample_code,
        segment_type, segment_id, metric_code
    );

COMMENT ON COLUMN stock_management.pdvb_backtest_metric.estimator_code IS
'Identifica el modelo candidato o benchmark evaluado sobre la misma corrida.';

COMMENT ON COLUMN stock_management.pdvb_backtest_metric.sample_code IS
'OWN_VALID usa la muestra valida del estimador; COMMON_VALID compara estimadores sobre exactamente las mismas observaciones.';

COMMIT;
