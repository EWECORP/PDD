-- PDD / Capa analitica pesada - v2.2 - 2026-08-05
-- Base de datos objetivo: diarco_data
-- Esquema objetivo: datamart
--
-- Contiene solamente datos historicos voluminosos y reproducibles.
-- Los IDs UUID de corrida, modelo y scope son referencias logicas a
-- stock_management del ambiente Connexa de destino; PostgreSQL no permite FK entre bases de datos.
-- BORRADOR: ejecutar mediante una migracion aprobada y con ON_ERROR_STOP.

BEGIN;

DO $guard$
BEGIN
    IF current_database() <> 'diarco_data' THEN
        RAISE EXCEPTION
            'DDL PDD analitico: base incorrecta (%). Se esperaba diarco_data.',
            current_database();
    END IF;
END
$guard$;

CREATE SCHEMA IF NOT EXISTS datamart;

CREATE TABLE datamart.dm_pdd_stock_diario (
    stock_date date NOT NULL,
    codigo_articulo integer NOT NULL,
    sucursal integer NOT NULL,
    stock_quantity numeric(18,6) NOT NULL,
    stock_sign_status varchar(10) NOT NULL
        CHECK (stock_sign_status IN ('POSITIVE', 'ZERO', 'NEGATIVE')),
    is_serviceable_by_stock boolean NOT NULL,
    source_year smallint NOT NULL CHECK (source_year BETWEEN 2000 AND 2200),
    source_month smallint NOT NULL CHECK (source_month BETWEEN 1 AND 12),
    source_day smallint NOT NULL CHECK (source_day BETWEEN 1 AND 31),
    source_processed_at timestamp without time zone,
    source_processed_ok boolean,
    source_origin text,
    closed_day_rule varchar(30) NOT NULL CHECK (
        closed_day_rule IN ('PROCESS_DATE_MINUS_1', 'EXPLICIT_CUTOFF')
    ),
    source_row_hash char(64) NOT NULL,
    normalized_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    PRIMARY KEY (stock_date, codigo_articulo, sucursal),
    CONSTRAINT ck_dm_pdd_stock_sign CHECK (
        (stock_quantity > 0 AND stock_sign_status = 'POSITIVE' AND is_serviceable_by_stock)
        OR (stock_quantity = 0 AND stock_sign_status = 'ZERO' AND NOT is_serviceable_by_stock)
        OR (stock_quantity < 0 AND stock_sign_status = 'NEGATIVE' AND NOT is_serviceable_by_stock)
    ),
    CONSTRAINT ck_dm_pdd_stock_source_date CHECK (
        extract(year FROM stock_date)::integer = source_year
        AND extract(month FROM stock_date)::integer = source_month
        AND extract(day FROM stock_date)::integer = source_day
    )
) PARTITION BY RANGE (stock_date);

CREATE INDEX ix_dm_pdd_stock_pair_date
    ON datamart.dm_pdd_stock_diario
    (codigo_articulo, sucursal, stock_date DESC);

CREATE INDEX ix_dm_pdd_stock_serviceable
    ON datamart.dm_pdd_stock_diario
    (stock_date, codigo_articulo, sucursal)
    WHERE is_serviceable_by_stock;

CREATE INDEX ix_dm_pdd_stock_date_brin
    ON datamart.dm_pdd_stock_diario USING brin (stock_date);

CREATE TABLE datamart.dm_pdd_venta_diaria (
    sales_date date NOT NULL,
    codigo_articulo integer NOT NULL,
    sucursal integer NOT NULL,
    scope_version_uuid uuid NOT NULL,
    feature_run_uuid uuid NOT NULL,
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
    stock_quantity_snapshot numeric(18,6),
    stock_source_hash char(64),
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
    enriched_max_calculated_at timestamp without time zone,
    feature_calculated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    source_hash char(64) NOT NULL,
    PRIMARY KEY (sales_date, codigo_articulo, sucursal),
    CONSTRAINT ck_dm_pdd_daily_units_conservation CHECK (
        abs(greatest(observed_units, 0) - basal_units - promotional_units) <= 0.001
    ),
    CONSTRAINT ck_dm_pdd_daily_eligibility CHECK (
        NOT eligible_for_pdvb OR (
            assortment_active
            AND availability_status IN ('IN_STOCK', 'INFERRED_FROM_SALE')
        )
    ),
    CONSTRAINT ck_dm_pdd_daily_stock_lineage CHECK (
        (availability_status = 'UNKNOWN'
            AND stock_quantity_snapshot IS NULL
            AND stock_source_hash IS NULL)
        OR availability_status = 'INFERRED_FROM_SALE'
        OR stock_source_hash IS NOT NULL
    )
) PARTITION BY RANGE (sales_date);

CREATE INDEX ix_dm_pdd_venta_pair_date
    ON datamart.dm_pdd_venta_diaria
    (codigo_articulo, sucursal, sales_date DESC);

CREATE INDEX ix_dm_pdd_venta_eligible_date
    ON datamart.dm_pdd_venta_diaria
    (sales_date, codigo_articulo, sucursal)
    WHERE eligible_for_pdvb;

CREATE INDEX ix_dm_pdd_venta_scope_date
    ON datamart.dm_pdd_venta_diaria
    (scope_version_uuid, sales_date, sucursal, codigo_articulo);

CREATE INDEX ix_dm_pdd_venta_date_brin
    ON datamart.dm_pdd_venta_diaria USING brin (sales_date);

CREATE TABLE datamart.dm_pdd_pdvb_estimate_detail (
    business_date date NOT NULL,
    pdvb_detail_id bigint GENERATED ALWAYS AS IDENTITY,
    calculation_run_uuid uuid NOT NULL,
    model_version_uuid uuid NOT NULL,
    scope_version_uuid uuid NOT NULL,
    origin_cd integer NOT NULL,
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
    publication_batch_uuid uuid,
    published_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    PRIMARY KEY (business_date, pdvb_detail_id),
    CONSTRAINT uq_dm_pdd_pdvb_detail_run_pair UNIQUE (
        business_date, calculation_run_uuid, codigo_articulo, sucursal
    ),
    CONSTRAINT ck_dm_pdd_pdvb_detail_dates CHECK (
        lookback_start <= lookback_end AND lookback_end < business_date
    ),
    CONSTRAINT ck_dm_pdd_pdvb_detail_days CHECK (
        eligible_days <= active_days AND nonzero_days <= eligible_days
    ),
    CONSTRAINT ck_dm_pdd_pdvb_detail_values CHECK (
        (status = 'BLOCKED' AND pdvb_value IS NULL)
        OR (status <> 'BLOCKED' AND pdvb_value IS NOT NULL AND pdvb_value >= 0)
    ),
    CONSTRAINT ck_dm_pdd_pdvb_detail_zero CHECK (
        status <> 'ZERO_VALID' OR pdvb_value = 0
    ),
    CONSTRAINT ck_dm_pdd_pdvb_detail_weights CHECK (
        status = 'BLOCKED'
        OR abs((recent_weight + previous_weight + seasonal_weight) - 1.0) <= 0.00001
    ),
    CONSTRAINT ck_dm_pdd_pdvb_detail_publication CHECK (
        (publication_batch_uuid IS NULL AND published_at IS NULL)
        OR (publication_batch_uuid IS NOT NULL AND published_at IS NOT NULL)
    )
) PARTITION BY RANGE (business_date);

CREATE INDEX ix_dm_pdd_pdvb_detail_pair_date
    ON datamart.dm_pdd_pdvb_estimate_detail
    (codigo_articulo, sucursal, business_date DESC);

CREATE INDEX ix_dm_pdd_pdvb_detail_run_status
    ON datamart.dm_pdd_pdvb_estimate_detail
    (calculation_run_uuid, status);

CREATE INDEX ix_dm_pdd_pdvb_detail_scope_date
    ON datamart.dm_pdd_pdvb_estimate_detail
    (scope_version_uuid, business_date DESC);

CREATE INDEX ix_dm_pdd_pdvb_detail_date_brin
    ON datamart.dm_pdd_pdvb_estimate_detail USING brin (business_date);

CREATE TABLE datamart.dm_pdd_pdvb_backtest_detail (
    evaluation_date date NOT NULL,
    backtest_detail_id bigint GENERATED ALWAYS AS IDENTITY,
    calculation_run_uuid uuid NOT NULL,
    model_version_uuid uuid NOT NULL,
    scope_version_uuid uuid NOT NULL,
    origin_cd integer NOT NULL,
    codigo_articulo integer NOT NULL,
    sucursal integer NOT NULL,
    forecast_origin_date date NOT NULL,
    forecast_horizon_days integer NOT NULL CHECK (forecast_horizon_days > 0),
    predicted_pdvb numeric(18,6) NOT NULL CHECK (predicted_pdvb >= 0),
    actual_basal_units numeric(18,6) NOT NULL CHECK (actual_basal_units >= 0),
    eligible_actual boolean NOT NULL,
    error_units numeric(18,6) NOT NULL,
    absolute_error_units numeric(18,6) NOT NULL CHECK (absolute_error_units >= 0),
    squared_error numeric(24,8) NOT NULL CHECK (squared_error >= 0),
    status varchar(20) NOT NULL CHECK (status IN ('VALID', 'EXCLUDED', 'WARN')),
    exclusion_codes text[] NOT NULL DEFAULT ARRAY[]::text[],
    input_checksum varchar(128) NOT NULL,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    PRIMARY KEY (evaluation_date, backtest_detail_id),
    CONSTRAINT uq_dm_pdd_backtest_detail UNIQUE (
        evaluation_date, calculation_run_uuid, codigo_articulo, sucursal,
        forecast_origin_date, forecast_horizon_days
    ),
    CONSTRAINT ck_dm_pdd_backtest_dates CHECK (
        forecast_origin_date < evaluation_date
        AND evaluation_date - forecast_origin_date = forecast_horizon_days
    )
) PARTITION BY RANGE (evaluation_date);

CREATE INDEX ix_dm_pdd_backtest_model_period
    ON datamart.dm_pdd_pdvb_backtest_detail
    (model_version_uuid, evaluation_date DESC);

CREATE INDEX ix_dm_pdd_backtest_pair_period
    ON datamart.dm_pdd_pdvb_backtest_detail
    (codigo_articulo, sucursal, evaluation_date DESC);

CREATE INDEX ix_dm_pdd_backtest_date_brin
    ON datamart.dm_pdd_pdvb_backtest_detail USING brin (evaluation_date);

COMMENT ON TABLE datamart.dm_pdd_stock_diario IS
'Stock LEGACY t710 normalizado a fecha-articulo-sucursal. La ausencia de fila significa desconocido, nunca stock cero.';

COMMENT ON COLUMN datamart.dm_pdd_stock_diario.source_processed_ok IS
'Se conserva por linaje; no actua como filtro hasta documentar su semantica en el sistema LEGACY.';

COMMENT ON TABLE datamart.dm_pdd_venta_diaria IS
'Feature canonico a grano fecha-articulo-sucursal. Incluye dias sin venta cuando el scope y el stock permiten clasificarlos.';

COMMENT ON TABLE datamart.dm_pdd_pdvb_estimate_detail IS
'Detalle historico, explicable e inmutable de PDVB. Se publica un subconjunto compacto en stock_management del ambiente Connexa de destino.';

COMMENT ON COLUMN datamart.dm_pdd_pdvb_estimate_detail.calculation_run_uuid IS
'Referencia logica, sin FK cross-database, a stock_management del ambiente Connexa de destino.calculation_run.calculation_run_uuid.';

COMMENT ON TABLE datamart.dm_pdd_pdvb_backtest_detail IS
'Observaciones detalladas de rolling-origin backtest; las metricas agregadas se conservan en stock_management del ambiente Connexa de destino.';

-- Las particiones mensuales deben ser creadas por migracion/job antes de cargar.
-- Ejemplo:
-- CREATE TABLE datamart.dm_pdd_stock_diario_2026_08
-- PARTITION OF datamart.dm_pdd_stock_diario
-- FOR VALUES FROM ('2026-08-01') TO ('2026-09-01');
--
-- Repetir el patron para dm_pdd_venta_diaria,
-- dm_pdd_pdvb_estimate_detail y dm_pdd_pdvb_backtest_detail.

COMMIT;
