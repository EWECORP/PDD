\set ON_ERROR_STOP on

BEGIN;

DO $guard$
BEGIN
    IF current_database() <> 'diarco_data' THEN
        RAISE EXCEPTION
            'Migracion PDD backtest v2.5: base incorrecta (%). Se esperaba diarco_data.',
            current_database();
    END IF;
END
$guard$;

ALTER TABLE datamart.dm_pdd_pdvb_backtest_detail
    ADD COLUMN evaluation_mode varchar(20) NOT NULL DEFAULT 'POINT_DAILY',
    ADD COLUMN evaluation_window_start date,
    ADD COLUMN actual_window_days integer,
    ADD COLUMN actual_eligible_days integer,
    ADD COLUMN actual_availability_coverage numeric(8,6),
    ADD COLUMN predicted_horizon_units numeric(18,6),
    ADD COLUMN demand_regime varchar(20),
    ADD COLUMN rubro integer,
    ADD COLUMN subrubro_1 integer;

-- Conserva y adapta las observaciones v2.4 sin recalcularlas.
UPDATE datamart.dm_pdd_pdvb_backtest_detail
SET evaluation_window_start = evaluation_date,
    actual_window_days = 1,
    actual_eligible_days = CASE WHEN eligible_actual THEN 1 ELSE 0 END,
    actual_availability_coverage = CASE WHEN eligible_actual THEN 1 ELSE 0 END,
    predicted_horizon_units = predicted_pdvb,
    demand_regime = 'UNCLASSIFIED'
WHERE evaluation_window_start IS NULL;

ALTER TABLE datamart.dm_pdd_pdvb_backtest_detail
    ALTER COLUMN evaluation_mode DROP DEFAULT,
    ALTER COLUMN evaluation_window_start SET NOT NULL,
    ALTER COLUMN actual_window_days SET NOT NULL,
    ALTER COLUMN actual_eligible_days SET NOT NULL,
    ALTER COLUMN actual_availability_coverage SET NOT NULL,
    ALTER COLUMN demand_regime SET NOT NULL,
    DROP CONSTRAINT uq_dm_pdd_backtest_detail,
    DROP CONSTRAINT ck_dm_pdd_backtest_estimator;

ALTER TABLE datamart.dm_pdd_pdvb_backtest_detail
    ADD CONSTRAINT uq_dm_pdd_backtest_detail UNIQUE (
        evaluation_date, calculation_run_uuid, codigo_articulo, sucursal,
        forecast_origin_date, forecast_horizon_days, evaluation_mode,
        estimator_code
    ),
    ADD CONSTRAINT ck_dm_pdd_backtest_estimator CHECK (
        estimator_code IN (
            'PDVB_CANDIDATE', 'MEAN_28',
            'ALGO_01_GROWTH', 'ALGO_01_NORMALIZED',
            'OCCURRENCE_SIZE', 'CROSTON_SBA', 'HYBRID_EXPERIMENTAL'
        )
    ),
    ADD CONSTRAINT ck_dm_pdd_backtest_evaluation_mode CHECK (
        evaluation_mode IN ('POINT_DAILY', 'CUMULATIVE')
    ),
    ADD CONSTRAINT ck_dm_pdd_backtest_evaluation_window CHECK (
        evaluation_window_start <= evaluation_date
        AND actual_window_days = evaluation_date - evaluation_window_start + 1
        AND actual_window_days > 0
        AND actual_eligible_days BETWEEN 0 AND actual_window_days
        AND actual_availability_coverage BETWEEN 0 AND 1
    ),
    ADD CONSTRAINT ck_dm_pdd_backtest_horizon_prediction CHECK (
        predicted_horizon_units IS NULL
        OR predicted_horizon_units >= 0
    ),
    ADD CONSTRAINT ck_dm_pdd_backtest_demand_regime CHECK (
        demand_regime IN (
            'NO_DEMAND', 'UNCLASSIFIED', 'SPARSE', 'SMOOTH',
            'ERRATIC', 'INTERMITTENT', 'LUMPY'
        )
    );

ALTER TABLE datamart.dm_pdd_pdvb_backtest_run
    ADD COLUMN evaluation_mode varchar(20) NOT NULL DEFAULT 'POINT_DAILY',
    ADD COLUMN actual_min_coverage numeric(8,6) NOT NULL DEFAULT 0.70,
    ADD CONSTRAINT ck_dm_pdd_backtest_run_mode CHECK (
        evaluation_mode IN ('POINT_DAILY', 'CUMULATIVE')
    ),
    ADD CONSTRAINT ck_dm_pdd_backtest_run_coverage CHECK (
        actual_min_coverage > 0 AND actual_min_coverage <= 1
    );

ALTER TABLE datamart.dm_pdd_pdvb_backtest_run
    ALTER COLUMN evaluation_mode DROP DEFAULT,
    ALTER COLUMN actual_min_coverage DROP DEFAULT;

ALTER TABLE datamart.dm_pdd_pdvb_backtest_metric
    ADD COLUMN evaluation_mode varchar(20) NOT NULL DEFAULT 'POINT_DAILY',
    ADD CONSTRAINT ck_dm_pdd_backtest_metric_mode CHECK (
        evaluation_mode IN ('POINT_DAILY', 'CUMULATIVE')
    ),
    ADD CONSTRAINT uq_dm_pdd_backtest_metric_v25 UNIQUE (
        calculation_run_uuid, evaluation_mode, estimator_code, sample_code,
        segment_type, segment_id, metric_code
    );

ALTER TABLE datamart.dm_pdd_pdvb_backtest_metric
    ALTER COLUMN evaluation_mode DROP DEFAULT;

CREATE INDEX ix_dm_pdd_backtest_regime_compare
    ON datamart.dm_pdd_pdvb_backtest_detail
    (calculation_run_uuid, evaluation_mode, demand_regime, estimator_code, status);

COMMENT ON COLUMN datamart.dm_pdd_pdvb_backtest_detail.evaluation_mode IS
'POINT_DAILY compara el dia origen+h; CUMULATIVE compara origen+1..origen+h.';

COMMENT ON COLUMN datamart.dm_pdd_pdvb_backtest_detail.predicted_horizon_units IS
'Pronostico total de la ventana evaluada. En modo acumulado es PDVB diario multiplicado por el horizonte.';

COMMENT ON COLUMN datamart.dm_pdd_pdvb_backtest_detail.actual_basal_units IS
'Demanda basal observada, escalada a la ventana completa cuando la cobertura servible alcanza el minimo de la corrida.';

COMMENT ON COLUMN datamart.dm_pdd_pdvb_backtest_detail.demand_regime IS
'Segmentacion experimental por ADI y CV2; los umbrales quedan registrados en parameters de la corrida.';

COMMIT;
