-- PDD / Demanda Basal (PDVB) - DDL propuesto v1.0 - 2026-08-02
-- BORRADOR: no ejecutar en producción sin migración aprobada.

BEGIN;

CREATE SCHEMA IF NOT EXISTS pdd;
CREATE SCHEMA IF NOT EXISTS datamart;

CREATE TABLE pdd.pdvb_model_version (
    model_version_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    model_code varchar(50) NOT NULL,
    version_no integer NOT NULL CHECK (version_no > 0),
    status varchar(20) NOT NULL CHECK (status IN ('DRAFT', 'APPROVED', 'RETIRED')),
    valid_from date,
    valid_to date,
    parameters jsonb NOT NULL,
    implementation_sha256 char(64) NOT NULL,
    code_commit_sha varchar(64),
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    created_by varchar(100) NOT NULL,
    approved_at timestamptz,
    approved_by varchar(100),
    CONSTRAINT uq_pdvb_model_version UNIQUE (model_code, version_no),
    CONSTRAINT ck_pdvb_model_validity CHECK (valid_to IS NULL OR valid_to >= valid_from),
    CONSTRAINT ck_pdvb_model_approval CHECK (
        status <> 'APPROVED' OR (approved_at IS NOT NULL AND approved_by IS NOT NULL)
    )
);

CREATE TABLE pdd.calculation_run (
    calculation_run_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    run_type varchar(30) NOT NULL CHECK (run_type IN ('PDVB', 'DAILY_DECAS', 'BACKTEST')),
    business_date date NOT NULL,
    cutoff_date date NOT NULL,
    scope_type varchar(30) NOT NULL DEFAULT 'ALL',
    scope_id varchar(100) NOT NULL DEFAULT 'ALL',
    attempt_no integer NOT NULL DEFAULT 1 CHECK (attempt_no > 0),
    model_version_id bigint REFERENCES pdd.pdvb_model_version(model_version_id),
    status varchar(20) NOT NULL
        CHECK (status IN ('PENDING', 'RUNNING', 'SUCCEEDED', 'FAILED', 'BLOCKED', 'SUPERSEDED')),
    is_current boolean NOT NULL DEFAULT false,
    started_at timestamptz,
    finished_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    created_by varchar(100) NOT NULL,
    input_row_count bigint,
    output_row_count bigint,
    warning_count bigint NOT NULL DEFAULT 0 CHECK (warning_count >= 0),
    error_count bigint NOT NULL DEFAULT 0 CHECK (error_count >= 0),
    summary jsonb NOT NULL DEFAULT '{}'::jsonb,
    error_detail text,
    CONSTRAINT uq_calculation_run_attempt
        UNIQUE (run_type, business_date, scope_type, scope_id, attempt_no),
    CONSTRAINT ck_calculation_cutoff CHECK (cutoff_date < business_date),
    CONSTRAINT ck_calculation_times CHECK (
        finished_at IS NULL OR started_at IS NULL OR finished_at >= started_at
    ),
    CONSTRAINT ck_calculation_current_success CHECK (NOT is_current OR status = 'SUCCEEDED')
);

CREATE UNIQUE INDEX uq_calculation_run_current
    ON pdd.calculation_run (run_type, business_date, scope_type, scope_id)
    WHERE is_current;
CREATE INDEX ix_calculation_run_status_date
    ON pdd.calculation_run (status, business_date DESC);

CREATE TABLE pdd.source_snapshot (
    source_snapshot_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    calculation_run_id bigint NOT NULL REFERENCES pdd.calculation_run(calculation_run_id),
    source_code varchar(60) NOT NULL,
    physical_relation varchar(200) NOT NULL,
    source_batch_id varchar(200),
    is_required boolean NOT NULL DEFAULT true,
    min_business_date date,
    max_business_date date,
    as_of_ts timestamptz NOT NULL,
    expected_as_of_ts timestamptz,
    row_count bigint CHECK (row_count IS NULL OR row_count >= 0),
    checksum varchar(128),
    freshness_seconds bigint CHECK (freshness_seconds IS NULL OR freshness_seconds >= 0),
    status varchar(20) NOT NULL CHECK (status IN ('VALID', 'STALE', 'MISSING', 'INVALID')),
    captured_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    detail jsonb NOT NULL DEFAULT '{}'::jsonb,
    error_detail text,
    CONSTRAINT uq_source_snapshot_run UNIQUE (calculation_run_id, source_code),
    CONSTRAINT ck_source_snapshot_range CHECK (
        max_business_date IS NULL OR min_business_date IS NULL OR max_business_date >= min_business_date
    )
);

CREATE INDEX ix_source_snapshot_status
    ON pdd.source_snapshot (calculation_run_id, status) WHERE status <> 'VALID';

CREATE TABLE datamart.dm_pdd_venta_diaria (
    sales_date date NOT NULL,
    codigo_articulo integer NOT NULL,
    sucursal integer NOT NULL,
    c_proveedor_primario integer,
    familia integer,
    rubro integer,
    subrubro integer,
    source_row_count integer NOT NULL CHECK (source_row_count >= 0),
    observed_units numeric(18,6) NOT NULL DEFAULT 0,
    return_units numeric(18,6) NOT NULL DEFAULT 0 CHECK (return_units >= 0),
    basal_units numeric(18,6) NOT NULL DEFAULT 0 CHECK (basal_units >= 0),
    promotional_units numeric(18,6) NOT NULL DEFAULT 0 CHECK (promotional_units >= 0),
    sold_amount numeric(20,4),
    effective_unit_price numeric(18,6),
    min_price numeric(18,6),
    max_price numeric(18,6),
    assortment_active boolean NOT NULL,
    availability_status varchar(30) NOT NULL CHECK (availability_status IN (
        'IN_STOCK', 'OUT_OF_STOCK', 'INFERRED_FROM_SALE', 'NOT_ASSORTED', 'UNKNOWN'
    )),
    special_sale_flag boolean NOT NULL DEFAULT false,
    normal_promo_flag boolean NOT NULL DEFAULT false,
    strong_promo_flag boolean NOT NULL DEFAULT false,
    promo_score_max numeric(8,4),
    promo_adjustment_method varchar(30) NOT NULL CHECK (promo_adjustment_method IN (
        'ENRICHED', 'RAW_FLAGS', 'NO_ADJUSTMENT', 'NOT_APPLICABLE'
    )),
    eligible_for_pdvb boolean NOT NULL,
    exclusion_codes text[] NOT NULL DEFAULT ARRAY[]::text[],
    source_max_processed_at timestamptz,
    enriched_max_calculated_at timestamp,
    feature_calculated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    source_hash char(64) NOT NULL,
    PRIMARY KEY (sales_date, codigo_articulo, sucursal),
    CONSTRAINT ck_daily_units_conservation CHECK (
        abs(greatest(observed_units, 0) - basal_units - promotional_units) <= 0.001
    ),
    CONSTRAINT ck_daily_eligibility CHECK (
        NOT eligible_for_pdvb OR (
            assortment_active AND availability_status IN ('IN_STOCK', 'INFERRED_FROM_SALE')
        )
    )
) PARTITION BY RANGE (sales_date);

-- Ejemplo de partición gestionada por migración/job:
-- CREATE TABLE datamart.dm_pdd_venta_diaria_2026_08
-- PARTITION OF datamart.dm_pdd_venta_diaria
-- FOR VALUES FROM ('2026-08-01') TO ('2026-09-01');

CREATE INDEX ix_dm_pdd_venta_pair_date
    ON datamart.dm_pdd_venta_diaria (codigo_articulo, sucursal, sales_date DESC);
CREATE INDEX ix_dm_pdd_venta_eligible_date
    ON datamart.dm_pdd_venta_diaria (sales_date, codigo_articulo, sucursal)
    WHERE eligible_for_pdvb;
CREATE INDEX ix_dm_pdd_venta_date_brin
    ON datamart.dm_pdd_venta_diaria USING brin (sales_date);

CREATE TABLE pdd.pdvb_estimate (
    business_date date NOT NULL,
    pdvb_estimate_id bigint GENERATED ALWAYS AS IDENTITY,
    calculation_run_id bigint NOT NULL REFERENCES pdd.calculation_run(calculation_run_id),
    model_version_id bigint NOT NULL REFERENCES pdd.pdvb_model_version(model_version_id),
    codigo_articulo integer NOT NULL,
    sucursal integer NOT NULL,
    c_proveedor_primario integer,
    method_code varchar(40) NOT NULL CHECK (method_code IN (
        'SKU_BRANCH_WEIGHTED', 'SKU_BRANCH_RECENT',
        'SKU_NETWORK_SHRINKAGE', 'INSUFFICIENT_DATA'
    )),
    fallback_level smallint NOT NULL DEFAULT 0 CHECK (fallback_level BETWEEN 0 AND 9),
    status varchar(20) NOT NULL CHECK (status IN ('OK', 'WARN', 'BLOCKED', 'ZERO_VALID')),
    confidence_score numeric(5,2) NOT NULL CHECK (confidence_score BETWEEN 0 AND 100),
    lookback_start date NOT NULL,
    lookback_end date NOT NULL,
    recent_start date,
    recent_end date,
    recent_basal_units numeric(20,6) NOT NULL DEFAULT 0 CHECK (recent_basal_units >= 0),
    recent_eligible_days integer NOT NULL DEFAULT 0 CHECK (recent_eligible_days >= 0),
    recent_mean numeric(18,6),
    recent_weight numeric(8,6) NOT NULL DEFAULT 0 CHECK (recent_weight BETWEEN 0 AND 1),
    previous_start date,
    previous_end date,
    previous_basal_units numeric(20,6) NOT NULL DEFAULT 0 CHECK (previous_basal_units >= 0),
    previous_eligible_days integer NOT NULL DEFAULT 0 CHECK (previous_eligible_days >= 0),
    previous_mean numeric(18,6),
    previous_weight numeric(8,6) NOT NULL DEFAULT 0 CHECK (previous_weight BETWEEN 0 AND 1),
    seasonal_start date,
    seasonal_end date,
    seasonal_basal_units numeric(20,6) NOT NULL DEFAULT 0 CHECK (seasonal_basal_units >= 0),
    seasonal_eligible_days integer NOT NULL DEFAULT 0 CHECK (seasonal_eligible_days >= 0),
    seasonal_mean numeric(18,6),
    seasonal_weight numeric(8,6) NOT NULL DEFAULT 0 CHECK (seasonal_weight BETWEEN 0 AND 1),
    active_days integer NOT NULL DEFAULT 0 CHECK (active_days >= 0),
    eligible_days integer NOT NULL DEFAULT 0 CHECK (eligible_days >= 0),
    nonzero_days integer NOT NULL DEFAULT 0 CHECK (nonzero_days >= 0),
    availability_coverage numeric(8,6) CHECK (availability_coverage BETWEEN 0 AND 1),
    promo_coverage numeric(8,6) CHECK (promo_coverage BETWEEN 0 AND 1),
    adi numeric(18,6),
    cv2 numeric(18,6),
    pdvb_raw numeric(18,6),
    pdvb_value numeric(18,6),
    explanation jsonb NOT NULL DEFAULT '{}'::jsonb,
    input_checksum varchar(128) NOT NULL,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    PRIMARY KEY (business_date, pdvb_estimate_id),
    CONSTRAINT uq_pdvb_estimate_run_pair
        UNIQUE (business_date, calculation_run_id, codigo_articulo, sucursal),
    CONSTRAINT ck_pdvb_estimate_dates CHECK (
        lookback_start <= lookback_end AND lookback_end < business_date
    ),
    CONSTRAINT ck_pdvb_estimate_days CHECK (
        eligible_days <= active_days AND nonzero_days <= eligible_days
    ),
    CONSTRAINT ck_pdvb_estimate_values CHECK (
        (status = 'BLOCKED' AND pdvb_value IS NULL) OR
        (status <> 'BLOCKED' AND pdvb_value IS NOT NULL AND pdvb_value >= 0)
    ),
    CONSTRAINT ck_pdvb_estimate_zero CHECK (status <> 'ZERO_VALID' OR pdvb_value = 0),
    CONSTRAINT ck_pdvb_estimate_weights CHECK (
        status = 'BLOCKED' OR
        abs((recent_weight + previous_weight + seasonal_weight) - 1.0) <= 0.00001
    )
) PARTITION BY RANGE (business_date);

-- Ejemplo de partición gestionada por migración/job:
-- CREATE TABLE pdd.pdvb_estimate_2026_08
-- PARTITION OF pdd.pdvb_estimate
-- FOR VALUES FROM ('2026-08-01') TO ('2026-09-01');

CREATE INDEX ix_pdvb_estimate_pair_date
    ON pdd.pdvb_estimate (codigo_articulo, sucursal, business_date DESC);
CREATE INDEX ix_pdvb_estimate_run_status
    ON pdd.pdvb_estimate (calculation_run_id, status);

CREATE TABLE pdd.pdvb_current (
    codigo_articulo integer NOT NULL,
    sucursal integer NOT NULL,
    business_date date NOT NULL,
    pdvb_estimate_id bigint NOT NULL,
    calculation_run_id bigint NOT NULL REFERENCES pdd.calculation_run(calculation_run_id),
    model_version_id bigint NOT NULL REFERENCES pdd.pdvb_model_version(model_version_id),
    pdvb_value numeric(18,6) NOT NULL CHECK (pdvb_value >= 0),
    status varchar(20) NOT NULL CHECK (status IN ('OK', 'WARN', 'ZERO_VALID')),
    confidence_score numeric(5,2) NOT NULL CHECK (confidence_score BETWEEN 0 AND 100),
    published_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    PRIMARY KEY (codigo_articulo, sucursal),
    FOREIGN KEY (business_date, pdvb_estimate_id)
        REFERENCES pdd.pdvb_estimate (business_date, pdvb_estimate_id)
);

CREATE INDEX ix_pdvb_current_date_status ON pdd.pdvb_current (business_date, status);

CREATE TABLE pdd.pdvb_quality_issue (
    quality_issue_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    calculation_run_id bigint NOT NULL REFERENCES pdd.calculation_run(calculation_run_id),
    business_date date NOT NULL,
    codigo_articulo integer,
    sucursal integer,
    severity varchar(10) NOT NULL CHECK (severity IN ('INFO', 'WARN', 'ERROR', 'BLOCKER')),
    issue_code varchar(60) NOT NULL,
    entity_type varchar(40) NOT NULL,
    entity_key jsonb NOT NULL DEFAULT '{}'::jsonb,
    detail text NOT NULL,
    evidence jsonb NOT NULL DEFAULT '{}'::jsonb,
    detected_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    resolved_at timestamptz,
    resolved_by varchar(100),
    resolution_detail text,
    CONSTRAINT ck_pdvb_issue_resolution CHECK (resolved_at IS NULL OR resolved_by IS NOT NULL)
);

CREATE INDEX ix_pdvb_quality_open
    ON pdd.pdvb_quality_issue (severity, business_date DESC, issue_code)
    WHERE resolved_at IS NULL;
CREATE INDEX ix_pdvb_quality_pair
    ON pdd.pdvb_quality_issue (codigo_articulo, sucursal, business_date DESC)
    WHERE codigo_articulo IS NOT NULL AND sucursal IS NOT NULL;

CREATE TABLE pdd.pdvb_backtest_metric (
    backtest_metric_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    calculation_run_id bigint REFERENCES pdd.calculation_run(calculation_run_id),
    model_version_id bigint NOT NULL REFERENCES pdd.pdvb_model_version(model_version_id),
    evaluation_from date NOT NULL,
    evaluation_to date NOT NULL,
    forecast_horizon_days integer NOT NULL CHECK (forecast_horizon_days > 0),
    segment_type varchar(40) NOT NULL,
    segment_id varchar(100) NOT NULL,
    metric_code varchar(20) NOT NULL CHECK (metric_code IN ('MAE', 'WAPE', 'BIAS', 'RMSE')),
    metric_value numeric(20,8) NOT NULL,
    sample_size bigint NOT NULL CHECK (sample_size > 0),
    zero_actual_count bigint NOT NULL DEFAULT 0 CHECK (zero_actual_count >= 0),
    calculated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    detail jsonb NOT NULL DEFAULT '{}'::jsonb,
    CONSTRAINT uq_pdvb_backtest_metric UNIQUE (
        model_version_id, evaluation_from, evaluation_to, forecast_horizon_days,
        segment_type, segment_id, metric_code
    ),
    CONSTRAINT ck_pdvb_backtest_dates CHECK (evaluation_to >= evaluation_from)
);

CREATE INDEX ix_pdvb_backtest_model_period
    ON pdd.pdvb_backtest_metric (model_version_id, evaluation_to DESC);

COMMENT ON TABLE datamart.dm_pdd_venta_diaria IS
'Venta diaria preparada a grano fecha-articulo-sucursal; no es el PDVB final.';
COMMENT ON TABLE pdd.pdvb_estimate IS
'Estimación PDVB inmutable con componentes suficientes para explicar la fórmula.';
COMMENT ON TABLE pdd.pdvb_current IS
'Proyección vigente por articulo-sucursal; sólo se publica desde una corrida exitosa.';

-- Publicación transaccional desde aplicación:
-- 1. validar corrida SUCCEEDED y conteos;
-- 2. upsert pdvb_current desde estimaciones no bloqueadas;
-- 3. retirar pares fuera de surtido mediante regla explícita;
-- 4. marcar calculation_run.is_current;
-- 5. commit único.

COMMIT;
