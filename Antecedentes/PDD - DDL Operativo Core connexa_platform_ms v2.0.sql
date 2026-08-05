-- PDD / Dominio operativo, gobierno y publicacion PDVB - v2.0 - 2026-08-03
-- Base de datos objetivo: connexa_platform_ms
-- Esquema objetivo: pdd
-- Aplicar antes de "PDD - DDL Operativo DECAS connexa_platform_ms v2.0.sql".
-- BORRADOR: ejecutar mediante Flyway/migracion aprobada y con ON_ERROR_STOP.

BEGIN;

DO $guard$
BEGIN
    IF current_database() <> 'connexa_platform_ms' THEN
        RAISE EXCEPTION
            'DDL PDD operativo: base incorrecta (%). Se esperaba connexa_platform_ms.',
            current_database();
    END IF;
END
$guard$;

CREATE SCHEMA IF NOT EXISTS pdd;

CREATE TABLE pdd.configuration_version (
    configuration_version_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    configuration_version_uuid uuid NOT NULL DEFAULT gen_random_uuid(),
    configuration_code varchar(60) NOT NULL,
    version_no integer NOT NULL CHECK (version_no > 0),
    status varchar(20) NOT NULL CHECK (status IN ('DRAFT', 'APPROVED', 'RETIRED')),
    valid_from date,
    valid_to date,
    parameters jsonb NOT NULL,
    checksum char(64) NOT NULL,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    created_by varchar(100) NOT NULL,
    approved_at timestamptz,
    approved_by varchar(100),
    CONSTRAINT uq_configuration_version_uuid UNIQUE (configuration_version_uuid),
    CONSTRAINT uq_configuration_version_code UNIQUE (configuration_code, version_no),
    CONSTRAINT ck_configuration_version_validity CHECK (
        valid_to IS NULL OR valid_from IS NULL OR valid_to >= valid_from
    ),
    CONSTRAINT ck_configuration_version_approval CHECK (
        status <> 'APPROVED' OR (approved_at IS NOT NULL AND approved_by IS NOT NULL)
    )
);

CREATE TABLE pdd.pdvb_model_version (
    model_version_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    model_version_uuid uuid NOT NULL DEFAULT gen_random_uuid(),
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
    CONSTRAINT uq_pdvb_model_version_uuid UNIQUE (model_version_uuid),
    CONSTRAINT uq_pdvb_model_version UNIQUE (model_code, version_no),
    CONSTRAINT ck_pdvb_model_validity CHECK (
        valid_to IS NULL OR valid_from IS NULL OR valid_to >= valid_from
    ),
    CONSTRAINT ck_pdvb_model_approval CHECK (
        status <> 'APPROVED' OR (approved_at IS NOT NULL AND approved_by IS NOT NULL)
    )
);

CREATE TABLE pdd.distribution_scope_version (
    scope_version_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    scope_version_uuid uuid NOT NULL DEFAULT gen_random_uuid(),
    origin_cd integer NOT NULL,
    business_date date NOT NULL,
    status varchar(20) NOT NULL CHECK (
        status IN ('DRAFT', 'APPROVED', 'SUPERSEDED', 'REJECTED')
    ),
    is_current boolean NOT NULL DEFAULT false,
    source_database varchar(80) NOT NULL DEFAULT 'diarco_data',
    source_relation varchar(200) NOT NULL DEFAULT 'src.base_productos_vigentes',
    source_as_of_ts timestamptz NOT NULL,
    article_filter jsonb NOT NULL,
    pair_filter jsonb NOT NULL,
    article_count integer NOT NULL CHECK (article_count >= 0),
    pair_count integer NOT NULL CHECK (pair_count >= 0),
    destination_count integer NOT NULL CHECK (destination_count >= 0),
    checksum char(64) NOT NULL,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    created_by varchar(100) NOT NULL,
    approved_at timestamptz,
    approved_by varchar(100),
    detail jsonb NOT NULL DEFAULT '{}'::jsonb,
    CONSTRAINT uq_distribution_scope_version_uuid UNIQUE (scope_version_uuid),
    CONSTRAINT uq_distribution_scope_version UNIQUE (origin_cd, business_date, checksum),
    CONSTRAINT ck_distribution_scope_phase1_origin CHECK (origin_cd = 41),
    CONSTRAINT ck_distribution_scope_current CHECK (NOT is_current OR status = 'APPROVED'),
    CONSTRAINT ck_distribution_scope_approval CHECK (
        status <> 'APPROVED' OR (approved_at IS NOT NULL AND approved_by IS NOT NULL)
    )
);

CREATE UNIQUE INDEX uq_distribution_scope_current
    ON pdd.distribution_scope_version (origin_cd)
    WHERE is_current;

CREATE TABLE pdd.distribution_scope_article (
    scope_version_id bigint NOT NULL
        REFERENCES pdd.distribution_scope_version(scope_version_id) ON DELETE RESTRICT,
    codigo_articulo integer NOT NULL,
    c_proveedor_primario integer,
    cd_active_for_purchase boolean NOT NULL,
    cd_habilitado boolean,
    cd_active_for_sale boolean,
    cd_active_on_mix boolean,
    source_row_hash char(64) NOT NULL,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    PRIMARY KEY (scope_version_id, codigo_articulo),
    CONSTRAINT ck_distribution_scope_article_purchase CHECK (cd_active_for_purchase)
);

CREATE INDEX ix_distribution_scope_article_lookup
    ON pdd.distribution_scope_article (codigo_articulo, scope_version_id DESC);

CREATE TABLE pdd.distribution_scope_pair (
    scope_version_id bigint NOT NULL,
    origin_cd integer NOT NULL,
    destination_branch integer NOT NULL,
    codigo_articulo integer NOT NULL,
    c_proveedor_primario integer,
    route_code varchar(30) NOT NULL,
    supply_mode integer NOT NULL,
    branch_habilitado boolean NOT NULL,
    branch_active_for_sale boolean NOT NULL,
    branch_active_on_mix boolean NOT NULL,
    source_row_hash char(64) NOT NULL,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    PRIMARY KEY (scope_version_id, destination_branch, codigo_articulo),
    FOREIGN KEY (scope_version_id, codigo_articulo)
        REFERENCES pdd.distribution_scope_article (scope_version_id, codigo_articulo)
        ON DELETE RESTRICT,
    CONSTRAINT ck_distribution_scope_distinct_branch CHECK (destination_branch <> origin_cd),
    CONSTRAINT ck_distribution_scope_pair_phase1_cd41 CHECK (
        origin_cd = 41
        AND route_code = '41CD'
        AND supply_mode = 0
        AND branch_habilitado
        AND branch_active_for_sale
        AND branch_active_on_mix
    )
);

CREATE INDEX ix_distribution_scope_pair_operational
    ON pdd.distribution_scope_pair
    (scope_version_id, destination_branch, codigo_articulo, c_proveedor_primario);

CREATE TABLE pdd.calculation_run (
    calculation_run_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    calculation_run_uuid uuid NOT NULL DEFAULT gen_random_uuid(),
    run_type varchar(30) NOT NULL CHECK (run_type IN (
        'SCOPE_REFRESH', 'DATA_PREP', 'PDVB', 'DAILY_DECAS', 'BACKTEST', 'PUBLISH'
    )),
    business_date date NOT NULL,
    cutoff_date date NOT NULL,
    scope_type varchar(30) NOT NULL DEFAULT 'CD',
    scope_id varchar(100) NOT NULL,
    attempt_no integer NOT NULL DEFAULT 1 CHECK (attempt_no > 0),
    scope_version_id bigint REFERENCES pdd.distribution_scope_version(scope_version_id),
    model_version_id bigint REFERENCES pdd.pdvb_model_version(model_version_id),
    configuration_version_id bigint
        REFERENCES pdd.configuration_version(configuration_version_id),
    formula_version varchar(40),
    status varchar(20) NOT NULL CHECK (status IN (
        'PENDING', 'RUNNING', 'SUCCEEDED', 'FAILED', 'BLOCKED', 'SUPERSEDED'
    )),
    is_current boolean NOT NULL DEFAULT false,
    started_at timestamptz,
    finished_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    created_by varchar(100) NOT NULL,
    input_row_count bigint CHECK (input_row_count IS NULL OR input_row_count >= 0),
    output_row_count bigint CHECK (output_row_count IS NULL OR output_row_count >= 0),
    warning_count bigint NOT NULL DEFAULT 0 CHECK (warning_count >= 0),
    error_count bigint NOT NULL DEFAULT 0 CHECK (error_count >= 0),
    input_checksum varchar(128),
    output_checksum varchar(128),
    summary jsonb NOT NULL DEFAULT '{}'::jsonb,
    error_detail text,
    CONSTRAINT uq_calculation_run_uuid UNIQUE (calculation_run_uuid),
    CONSTRAINT uq_calculation_run_attempt UNIQUE (
        run_type, business_date, scope_type, scope_id, attempt_no
    ),
    CONSTRAINT ck_calculation_cutoff CHECK (cutoff_date < business_date),
    CONSTRAINT ck_calculation_times CHECK (
        finished_at IS NULL OR started_at IS NULL OR finished_at >= started_at
    ),
    CONSTRAINT ck_calculation_current_success CHECK (
        NOT is_current OR status = 'SUCCEEDED'
    ),
    CONSTRAINT ck_calculation_scope_required CHECK (
        run_type NOT IN ('PDVB', 'DAILY_DECAS') OR scope_version_id IS NOT NULL
    ),
    CONSTRAINT ck_calculation_model_required CHECK (
        run_type NOT IN ('PDVB', 'BACKTEST') OR model_version_id IS NOT NULL
    ),
    CONSTRAINT ck_calculation_config_required CHECK (
        run_type <> 'DAILY_DECAS' OR configuration_version_id IS NOT NULL
    )
);

CREATE UNIQUE INDEX uq_calculation_run_current
    ON pdd.calculation_run (run_type, business_date, scope_type, scope_id)
    WHERE is_current;

CREATE INDEX ix_calculation_run_status_date
    ON pdd.calculation_run (status, business_date DESC);

CREATE TABLE pdd.source_snapshot (
    source_snapshot_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    calculation_run_id bigint NOT NULL
        REFERENCES pdd.calculation_run(calculation_run_id) ON DELETE RESTRICT,
    source_code varchar(60) NOT NULL,
    source_database varchar(80) NOT NULL,
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
        max_business_date IS NULL
        OR min_business_date IS NULL
        OR max_business_date >= min_business_date
    )
);

CREATE INDEX ix_source_snapshot_status
    ON pdd.source_snapshot (calculation_run_id, status)
    WHERE status <> 'VALID';

CREATE TABLE pdd.pdvb_publication_batch (
    publication_batch_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    publication_batch_uuid uuid NOT NULL DEFAULT gen_random_uuid(),
    calculation_run_id bigint NOT NULL
        REFERENCES pdd.calculation_run(calculation_run_id) ON DELETE RESTRICT,
    source_database varchar(80) NOT NULL DEFAULT 'diarco_data',
    source_relation varchar(200) NOT NULL
        DEFAULT 'datamart.dm_pdd_pdvb_estimate_detail',
    expected_row_count bigint NOT NULL CHECK (expected_row_count >= 0),
    staged_row_count bigint CHECK (staged_row_count IS NULL OR staged_row_count >= 0),
    published_row_count bigint CHECK (published_row_count IS NULL OR published_row_count >= 0),
    source_checksum varchar(128) NOT NULL,
    staged_checksum varchar(128),
    status varchar(20) NOT NULL CHECK (
        status IN ('PENDING', 'STAGING', 'VALIDATED', 'PUBLISHED', 'FAILED', 'SUPERSEDED')
    ),
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    validated_at timestamptz,
    published_at timestamptz,
    created_by varchar(100) NOT NULL,
    error_detail text,
    detail jsonb NOT NULL DEFAULT '{}'::jsonb,
    CONSTRAINT uq_pdvb_publication_batch_uuid UNIQUE (publication_batch_uuid),
    CONSTRAINT uq_pdvb_publication_run UNIQUE (calculation_run_id),
    CONSTRAINT ck_pdvb_publication_validation CHECK (
        status NOT IN ('VALIDATED', 'PUBLISHED')
        OR (
            validated_at IS NOT NULL
            AND staged_row_count = expected_row_count
            AND staged_checksum = source_checksum
        )
    ),
    CONSTRAINT ck_pdvb_publication_published CHECK (
        status <> 'PUBLISHED'
        OR (published_at IS NOT NULL AND published_row_count = expected_row_count)
    )
);

CREATE TABLE pdd.pdvb_publication_stage (
    publication_batch_id bigint NOT NULL
        REFERENCES pdd.pdvb_publication_batch(publication_batch_id) ON DELETE CASCADE,
    business_date date NOT NULL,
    analytical_detail_id bigint NOT NULL,
    model_version_id bigint NOT NULL
        REFERENCES pdd.pdvb_model_version(model_version_id) ON DELETE RESTRICT,
    scope_version_id bigint NOT NULL
        REFERENCES pdd.distribution_scope_version(scope_version_id) ON DELETE RESTRICT,
    origin_cd integer NOT NULL,
    codigo_articulo integer NOT NULL,
    sucursal integer NOT NULL,
    c_proveedor_primario integer,
    method_code varchar(40) NOT NULL CHECK (method_code IN (
        'SKU_BRANCH_WEIGHTED', 'SKU_BRANCH_RECENT',
        'SKU_NETWORK_SHRINKAGE', 'INSUFFICIENT_DATA'
    )),
    fallback_level smallint NOT NULL CHECK (fallback_level BETWEEN 0 AND 9),
    status varchar(20) NOT NULL CHECK (status IN ('OK', 'WARN', 'BLOCKED', 'ZERO_VALID')),
    confidence_score numeric(5,2) NOT NULL CHECK (confidence_score BETWEEN 0 AND 100),
    pdvb_value numeric(18,6),
    input_checksum varchar(128) NOT NULL,
    explanation_summary jsonb NOT NULL DEFAULT '{}'::jsonb,
    staged_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    PRIMARY KEY (publication_batch_id, sucursal, codigo_articulo),
    FOREIGN KEY (scope_version_id, sucursal, codigo_articulo)
        REFERENCES pdd.distribution_scope_pair
            (scope_version_id, destination_branch, codigo_articulo)
        ON DELETE RESTRICT,
    CONSTRAINT ck_pdvb_stage_origin CHECK (origin_cd = 41),
    CONSTRAINT ck_pdvb_stage_value CHECK (
        (status = 'BLOCKED' AND pdvb_value IS NULL)
        OR (status <> 'BLOCKED' AND pdvb_value IS NOT NULL AND pdvb_value >= 0)
    ),
    CONSTRAINT ck_pdvb_stage_zero CHECK (status <> 'ZERO_VALID' OR pdvb_value = 0)
);

CREATE INDEX ix_pdvb_stage_scope
    ON pdd.pdvb_publication_stage
    (publication_batch_id, scope_version_id, sucursal, codigo_articulo);

CREATE TABLE pdd.pdvb_estimate (
    business_date date NOT NULL,
    pdvb_estimate_id bigint GENERATED ALWAYS AS IDENTITY,
    calculation_run_id bigint NOT NULL
        REFERENCES pdd.calculation_run(calculation_run_id) ON DELETE RESTRICT,
    publication_batch_id bigint NOT NULL
        REFERENCES pdd.pdvb_publication_batch(publication_batch_id) ON DELETE RESTRICT,
    analytical_detail_id bigint NOT NULL,
    model_version_id bigint NOT NULL
        REFERENCES pdd.pdvb_model_version(model_version_id) ON DELETE RESTRICT,
    scope_version_id bigint NOT NULL
        REFERENCES pdd.distribution_scope_version(scope_version_id) ON DELETE RESTRICT,
    origin_cd integer NOT NULL,
    codigo_articulo integer NOT NULL,
    sucursal integer NOT NULL,
    c_proveedor_primario integer,
    method_code varchar(40) NOT NULL CHECK (method_code IN (
        'SKU_BRANCH_WEIGHTED', 'SKU_BRANCH_RECENT',
        'SKU_NETWORK_SHRINKAGE', 'INSUFFICIENT_DATA'
    )),
    fallback_level smallint NOT NULL CHECK (fallback_level BETWEEN 0 AND 9),
    status varchar(20) NOT NULL CHECK (status IN ('OK', 'WARN', 'BLOCKED', 'ZERO_VALID')),
    confidence_score numeric(5,2) NOT NULL CHECK (confidence_score BETWEEN 0 AND 100),
    pdvb_value numeric(18,6),
    input_checksum varchar(128) NOT NULL,
    explanation_summary jsonb NOT NULL DEFAULT '{}'::jsonb,
    published_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    PRIMARY KEY (business_date, pdvb_estimate_id),
    CONSTRAINT uq_pdvb_estimate_run_pair UNIQUE (
        business_date, calculation_run_id, codigo_articulo, sucursal
    ),
    FOREIGN KEY (scope_version_id, sucursal, codigo_articulo)
        REFERENCES pdd.distribution_scope_pair
            (scope_version_id, destination_branch, codigo_articulo)
        ON DELETE RESTRICT,
    CONSTRAINT ck_pdvb_estimate_origin CHECK (origin_cd = 41),
    CONSTRAINT ck_pdvb_estimate_values CHECK (
        (status = 'BLOCKED' AND pdvb_value IS NULL)
        OR (status <> 'BLOCKED' AND pdvb_value IS NOT NULL AND pdvb_value >= 0)
    ),
    CONSTRAINT ck_pdvb_estimate_zero CHECK (status <> 'ZERO_VALID' OR pdvb_value = 0)
) PARTITION BY RANGE (business_date);

CREATE INDEX ix_pdvb_estimate_pair_date
    ON pdd.pdvb_estimate (codigo_articulo, sucursal, business_date DESC);

CREATE INDEX ix_pdvb_estimate_run_status
    ON pdd.pdvb_estimate (calculation_run_id, status);

CREATE INDEX ix_pdvb_estimate_scope
    ON pdd.pdvb_estimate (scope_version_id, origin_cd, business_date DESC);

CREATE TABLE pdd.pdvb_current (
    origin_cd integer NOT NULL,
    codigo_articulo integer NOT NULL,
    sucursal integer NOT NULL,
    business_date date NOT NULL,
    pdvb_estimate_id bigint NOT NULL,
    calculation_run_id bigint NOT NULL
        REFERENCES pdd.calculation_run(calculation_run_id) ON DELETE RESTRICT,
    model_version_id bigint NOT NULL
        REFERENCES pdd.pdvb_model_version(model_version_id) ON DELETE RESTRICT,
    scope_version_id bigint NOT NULL
        REFERENCES pdd.distribution_scope_version(scope_version_id) ON DELETE RESTRICT,
    pdvb_value numeric(18,6) NOT NULL CHECK (pdvb_value >= 0),
    status varchar(20) NOT NULL CHECK (status IN ('OK', 'WARN', 'ZERO_VALID')),
    confidence_score numeric(5,2) NOT NULL CHECK (confidence_score BETWEEN 0 AND 100),
    published_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    PRIMARY KEY (origin_cd, codigo_articulo, sucursal),
    FOREIGN KEY (business_date, pdvb_estimate_id)
        REFERENCES pdd.pdvb_estimate (business_date, pdvb_estimate_id)
        ON DELETE RESTRICT,
    FOREIGN KEY (scope_version_id, sucursal, codigo_articulo)
        REFERENCES pdd.distribution_scope_pair
            (scope_version_id, destination_branch, codigo_articulo)
        ON DELETE RESTRICT,
    CONSTRAINT ck_pdvb_current_origin CHECK (origin_cd = 41)
);

CREATE INDEX ix_pdvb_current_date_status
    ON pdd.pdvb_current (business_date, status);

CREATE INDEX ix_pdvb_current_scope
    ON pdd.pdvb_current (scope_version_id, origin_cd, sucursal, codigo_articulo);

CREATE TABLE pdd.pdvb_quality_issue (
    quality_issue_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    calculation_run_id bigint NOT NULL
        REFERENCES pdd.calculation_run(calculation_run_id) ON DELETE RESTRICT,
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
    calculation_run_id bigint NOT NULL
        REFERENCES pdd.calculation_run(calculation_run_id) ON DELETE RESTRICT,
    model_version_id bigint NOT NULL
        REFERENCES pdd.pdvb_model_version(model_version_id) ON DELETE RESTRICT,
    scope_version_id bigint NOT NULL
        REFERENCES pdd.distribution_scope_version(scope_version_id) ON DELETE RESTRICT,
    evaluation_from date NOT NULL,
    evaluation_to date NOT NULL,
    forecast_horizon_days integer NOT NULL CHECK (forecast_horizon_days > 0),
    segment_type varchar(40) NOT NULL,
    segment_id varchar(100) NOT NULL,
    metric_code varchar(20) NOT NULL CHECK (
        metric_code IN ('MAE', 'WAPE', 'BIAS', 'RMSE')
    ),
    metric_value numeric(20,8) NOT NULL,
    sample_size bigint NOT NULL CHECK (sample_size > 0),
    zero_actual_count bigint NOT NULL DEFAULT 0 CHECK (zero_actual_count >= 0),
    calculated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    detail jsonb NOT NULL DEFAULT '{}'::jsonb,
    CONSTRAINT uq_pdvb_backtest_metric UNIQUE (
        calculation_run_id, evaluation_from, evaluation_to, forecast_horizon_days,
        segment_type, segment_id, metric_code
    ),
    CONSTRAINT ck_pdvb_backtest_dates CHECK (evaluation_to >= evaluation_from)
);

CREATE INDEX ix_pdvb_backtest_model_period
    ON pdd.pdvb_backtest_metric (model_version_id, evaluation_to DESC);

COMMENT ON TABLE pdd.distribution_scope_version IS
'Version inmutable del universo distribuible desde CD 41; los conteos se calculan y nunca se hardcodean.';

COMMENT ON CONSTRAINT ck_distribution_scope_pair_phase1_cd41
    ON pdd.distribution_scope_pair IS
'Regla ADR-001: cod_cd=41CD, abastecimiento=0, habilitado=1, active_for_sale=1 y active_on_mix=1.';

COMMENT ON TABLE pdd.pdvb_publication_stage IS
'Staging transaccional para publicar el subconjunto PDVB desde diarco_data sin consultar tablas pesadas por FDW.';

COMMENT ON TABLE pdd.pdvb_estimate IS
'Historia operativa compacta de PDVB; el detalle completo permanece en diarco_data.datamart.dm_pdd_pdvb_estimate_detail.';

COMMENT ON COLUMN pdd.pdvb_estimate.analytical_detail_id IS
'Referencia logica sin FK cross-database al detalle analitico de diarco_data.';

COMMENT ON TABLE pdd.pdvb_current IS
'Proyeccion vigente por CD-articulo-sucursal. Solo admite estimaciones no bloqueadas.';

-- Publicacion esperada, dentro de una unica transaccion de aplicacion:
-- 1. crear pdvb_publication_batch en PENDING/STAGING;
-- 2. bulk load del scope de la corrida en pdvb_publication_stage;
-- 3. verificar conteo, checksum, modelo, scope y ausencia de duplicados;
-- 4. marcar VALIDATED;
-- 5. insertar pdvb_estimate y hacer upsert de pdvb_current solo para no bloqueados;
-- 6. retirar explicitamente de pdvb_current los pares que salieron del scope;
-- 7. marcar batch PUBLISHED y corrida SUCCEEDED/is_current; commit.

COMMIT;
