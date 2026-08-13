\set ON_ERROR_STOP on

BEGIN;

DO $guard$
BEGIN
    IF current_database() NOT IN ('connexa_platform_test', 'connexa_platform_ms') THEN
        RAISE EXCEPTION
            'Migracion PDD operativa v2.5: base incorrecta (%).', current_database();
    END IF;
END
$guard$;

ALTER TABLE stock_management.pdvb_backtest_metric
    ADD COLUMN evaluation_mode varchar(20) NOT NULL DEFAULT 'POINT_DAILY',
    DROP CONSTRAINT ck_pdvb_backtest_estimator,
    DROP CONSTRAINT uq_pdvb_backtest_metric;

ALTER TABLE stock_management.pdvb_backtest_metric
    ALTER COLUMN evaluation_mode DROP DEFAULT,
    ADD CONSTRAINT ck_pdvb_backtest_estimator CHECK (
        estimator_code IN (
            'PDVB_CANDIDATE', 'MEAN_28',
            'ALGO_01_GROWTH', 'ALGO_01_NORMALIZED',
            'OCCURRENCE_SIZE', 'CROSTON_SBA', 'HYBRID_EXPERIMENTAL'
        )
    ),
    ADD CONSTRAINT ck_pdvb_backtest_evaluation_mode CHECK (
        evaluation_mode IN ('POINT_DAILY', 'CUMULATIVE')
    ),
    ADD CONSTRAINT uq_pdvb_backtest_metric UNIQUE (
        calculation_run_id, evaluation_from, evaluation_to,
        forecast_horizon_days, evaluation_mode, estimator_code, sample_code,
        segment_type, segment_id, metric_code
    );

COMMENT ON COLUMN stock_management.pdvb_backtest_metric.evaluation_mode IS
'POINT_DAILY evalua el dia final; CUMULATIVE evalua la necesidad total del horizonte.';

COMMIT;
