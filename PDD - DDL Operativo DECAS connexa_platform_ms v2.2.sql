-- PDD / Posiciones, necesidades DECAS, backlog e integracion - v2.2 - 2026-08-05
-- Bases admitidas: connexa_platform_test (Test) / connexa_platform_ms (Produccion)
-- Esquema objetivo: stock_management
-- Requiere "PDD - DDL Operativo Core connexa_platform_ms v2.2.sql".
-- No crea reservas, asignaciones de stock, viajes, rutas ni planes de carga.
-- BORRADOR: ejecutar mediante Flyway/migracion aprobada y con ON_ERROR_STOP.

BEGIN;

DO $guard$
BEGIN
    IF current_database() NOT IN ('connexa_platform_test', 'connexa_platform_ms') THEN
        RAISE EXCEPTION
            'DDL PDD DECAS: base incorrecta (%). Se esperaba connexa_platform_test o connexa_platform_ms.',
            current_database();
    END IF;
END
$guard$;

CREATE TABLE stock_management.pdd_item_logistics_snapshot (
    item_logistics_snapshot_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    calculation_run_id bigint NOT NULL
        REFERENCES stock_management.pdd_calculation_run(calculation_run_id) ON DELETE RESTRICT,
    origin_cd integer NOT NULL,
    codigo_articulo integer NOT NULL,
    base_unit varchar(20) NOT NULL,
    units_per_package numeric(18,6) CHECK (units_per_package > 0),
    packages_per_pallet numeric(18,6) CHECK (packages_per_pallet > 0),
    unit_weight_kg numeric(18,6) CHECK (unit_weight_kg >= 0),
    unit_volume_m3 numeric(18,9) CHECK (unit_volume_m3 >= 0),
    source_snapshot_id bigint
        REFERENCES stock_management.pdd_source_snapshot(source_snapshot_id) ON DELETE RESTRICT,
    quality_status varchar(20) NOT NULL CHECK (
        quality_status IN ('COMPLETE', 'PARTIAL', 'MISSING', 'INVALID')
    ),
    source_as_of_ts timestamptz NOT NULL,
    input_checksum varchar(128) NOT NULL,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT uq_pdd_item_logistics_run UNIQUE (calculation_run_id, origin_cd, codigo_articulo),
    CONSTRAINT ck_pdd_item_logistics_origin CHECK (origin_cd = 41)
);

CREATE TABLE stock_management.pdd_branch_stock_position (
    business_date date NOT NULL,
    branch_stock_position_id bigint GENERATED ALWAYS AS IDENTITY,
    calculation_run_id bigint NOT NULL
        REFERENCES stock_management.pdd_calculation_run(calculation_run_id) ON DELETE RESTRICT,
    scope_version_id bigint NOT NULL
        REFERENCES stock_management.pdd_distribution_scope_version(scope_version_id) ON DELETE RESTRICT,
    origin_cd integer NOT NULL,
    sucursal integer NOT NULL,
    codigo_articulo integer NOT NULL,
    c_proveedor_primario integer,
    physical_stock numeric(18,6) NOT NULL,
    direct_po_inbound numeric(18,6) NOT NULL DEFAULT 0 CHECK (direct_po_inbound >= 0),
    cd_in_transit numeric(18,6) NOT NULL DEFAULT 0 CHECK (cd_in_transit >= 0),
    special_sale_committed numeric(18,6) NOT NULL DEFAULT 0
        CHECK (special_sale_committed >= 0),
    confirmed_transfer_pending numeric(18,6) NOT NULL DEFAULT 0
        CHECK (confirmed_transfer_pending >= 0),
    net_stock numeric(18,6) GENERATED ALWAYS AS (
        physical_stock + direct_po_inbound + cd_in_transit
        - special_sale_committed - confirmed_transfer_pending
    ) STORED,
    pdvb_business_date date NOT NULL,
    pdvb_estimate_id bigint NOT NULL,
    pdvb_value numeric(18,6) NOT NULL CHECK (pdvb_value >= 0),
    lead_time_days numeric(10,4) NOT NULL CHECK (lead_time_days > 0),
    target_stock_days numeric(10,4) NOT NULL CHECK (target_stock_days >= 0),
    overstock_days numeric(10,4) NOT NULL CHECK (overstock_days >= 0),
    critical_stock numeric(18,6) NOT NULL CHECK (critical_stock >= 0),
    minimum_stock numeric(18,6) NOT NULL CHECK (minimum_stock >= 0),
    maximum_stock numeric(18,6) NOT NULL CHECK (maximum_stock >= 0),
    overstock_quantity numeric(18,6) NOT NULL CHECK (overstock_quantity >= 0),
    coverage_days numeric(18,6),
    stock_source_snapshot_id bigint NOT NULL
        REFERENCES stock_management.pdd_source_snapshot(source_snapshot_id) ON DELETE RESTRICT,
    direct_po_source_snapshot_id bigint
        REFERENCES stock_management.pdd_source_snapshot(source_snapshot_id) ON DELETE RESTRICT,
    transit_source_snapshot_id bigint
        REFERENCES stock_management.pdd_source_snapshot(source_snapshot_id) ON DELETE RESTRICT,
    commitment_source_snapshot_id bigint
        REFERENCES stock_management.pdd_source_snapshot(source_snapshot_id) ON DELETE RESTRICT,
    configuration_version_id bigint NOT NULL
        REFERENCES stock_management.pdd_configuration_version(configuration_version_id) ON DELETE RESTRICT,
    calculation_status varchar(20) NOT NULL CHECK (
        calculation_status IN ('OK', 'WARN', 'BLOCKED', 'ZERO_PDVB')
    ),
    explanation jsonb NOT NULL DEFAULT '{}'::jsonb,
    alert_codes text[] NOT NULL DEFAULT ARRAY[]::text[],
    input_checksum varchar(128) NOT NULL,
    calculated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    PRIMARY KEY (business_date, branch_stock_position_id),
    CONSTRAINT uq_pdd_branch_stock_position_run UNIQUE (
        business_date, calculation_run_id, origin_cd, sucursal, codigo_articulo
    ),
    FOREIGN KEY (scope_version_id, sucursal, codigo_articulo)
        REFERENCES stock_management.pdd_distribution_scope_pair
            (scope_version_id, destination_branch, codigo_articulo)
        ON DELETE RESTRICT,
    FOREIGN KEY (pdvb_business_date, pdvb_estimate_id)
        REFERENCES stock_management.pdd_pdvb_estimate (business_date, pdvb_estimate_id)
        ON DELETE RESTRICT,
    CONSTRAINT ck_pdd_branch_stock_position_origin CHECK (origin_cd = 41),
    CONSTRAINT ck_pdd_branch_stock_position_pdvb_date CHECK (
        pdvb_business_date <= business_date
    ),
    CONSTRAINT ck_pdd_branch_stock_position_formulas CHECK (
        abs(critical_stock - (pdvb_value * lead_time_days)) <= 0.001
        AND abs(minimum_stock - (pdvb_value * 2 * lead_time_days)) <= 0.001
        AND abs(maximum_stock - (pdvb_value * target_stock_days)) <= 0.001
        AND abs(overstock_quantity - (pdvb_value * overstock_days)) <= 0.001
    )
) PARTITION BY RANGE (business_date);

CREATE INDEX ix_pdd_branch_stock_position_pair_date
    ON stock_management.pdd_branch_stock_position (codigo_articulo, sucursal, business_date DESC);

CREATE INDEX ix_pdd_branch_stock_position_run_status
    ON stock_management.pdd_branch_stock_position (calculation_run_id, calculation_status);

CREATE INDEX ix_pdd_branch_stock_position_date_brin
    ON stock_management.pdd_branch_stock_position USING brin (business_date);

CREATE TABLE stock_management.pdd_cd_stock_position (
    business_date date NOT NULL,
    cd_stock_position_id bigint GENERATED ALWAYS AS IDENTITY,
    calculation_run_id bigint NOT NULL
        REFERENCES stock_management.pdd_calculation_run(calculation_run_id) ON DELETE RESTRICT,
    origin_cd integer NOT NULL,
    codigo_articulo integer NOT NULL,
    c_proveedor_primario integer,
    physical_stock numeric(18,6) NOT NULL,
    open_po_on_time numeric(18,6) NOT NULL DEFAULT 0 CHECK (open_po_on_time >= 0),
    open_po_overdue numeric(18,6) NOT NULL DEFAULT 0 CHECK (open_po_overdue >= 0),
    mandatory_backlog numeric(18,6) NOT NULL DEFAULT 0 CHECK (mandatory_backlog >= 0),
    optional_backlog numeric(18,6) NOT NULL DEFAULT 0 CHECK (optional_backlog >= 0),
    coverage_index numeric(18,6),
    stock_source_snapshot_id bigint NOT NULL
        REFERENCES stock_management.pdd_source_snapshot(source_snapshot_id) ON DELETE RESTRICT,
    po_source_snapshot_id bigint
        REFERENCES stock_management.pdd_source_snapshot(source_snapshot_id) ON DELETE RESTRICT,
    status varchar(20) NOT NULL CHECK (status IN ('OK', 'WARN', 'BLOCKED')),
    alert_codes text[] NOT NULL DEFAULT ARRAY[]::text[],
    input_checksum varchar(128) NOT NULL,
    calculated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    PRIMARY KEY (business_date, cd_stock_position_id),
    CONSTRAINT uq_pdd_cd_stock_position_run UNIQUE (
        business_date, calculation_run_id, origin_cd, codigo_articulo
    ),
    CONSTRAINT ck_pdd_cd_stock_position_origin CHECK (origin_cd = 41)
) PARTITION BY RANGE (business_date);

CREATE INDEX ix_pdd_cd_stock_position_article_date
    ON stock_management.pdd_cd_stock_position (codigo_articulo, business_date DESC);

CREATE INDEX ix_pdd_cd_stock_position_run_status
    ON stock_management.pdd_cd_stock_position (calculation_run_id, status);

CREATE TABLE stock_management.pdd_need_snapshot (
    business_date date NOT NULL,
    need_snapshot_id bigint GENERATED ALWAYS AS IDENTITY,
    calculation_run_id bigint NOT NULL
        REFERENCES stock_management.pdd_calculation_run(calculation_run_id) ON DELETE RESTRICT,
    branch_stock_position_id bigint NOT NULL,
    scope_version_id bigint NOT NULL
        REFERENCES stock_management.pdd_distribution_scope_version(scope_version_id) ON DELETE RESTRICT,
    origin_cd integer NOT NULL,
    sucursal integer NOT NULL,
    codigo_articulo integer NOT NULL,
    c_proveedor_primario integer,
    need_type char(1) NOT NULL CHECK (need_type IN ('D', 'S')),
    is_mandatory boolean NOT NULL,
    calculated_quantity numeric(18,6),
    rounded_quantity numeric(18,6),
    rounding_unit numeric(18,6) CHECK (rounding_unit IS NULL OR rounding_unit > 0),
    open_quantity numeric(18,6),
    irq_score numeric(5,2) CHECK (irq_score BETWEEN 0 AND 100),
    priority_score numeric(12,6),
    target_date date,
    formula_code varchar(40) NOT NULL,
    formula_version varchar(40) NOT NULL,
    configuration_version_id bigint NOT NULL
        REFERENCES stock_management.pdd_configuration_version(configuration_version_id) ON DELETE RESTRICT,
    logistics_snapshot_id bigint
        REFERENCES stock_management.pdd_item_logistics_snapshot(item_logistics_snapshot_id) ON DELETE RESTRICT,
    estimated_packages numeric(18,6) CHECK (estimated_packages >= 0),
    estimated_pallets numeric(18,6) CHECK (estimated_pallets >= 0),
    estimated_weight_kg numeric(18,6) CHECK (estimated_weight_kg >= 0),
    estimated_volume_m3 numeric(18,9) CHECK (estimated_volume_m3 >= 0),
    calculation_status varchar(20) NOT NULL CHECK (
        calculation_status IN ('CALCULATED', 'ZERO', 'BLOCKED')
    ),
    explanation jsonb NOT NULL DEFAULT '{}'::jsonb,
    alert_codes text[] NOT NULL DEFAULT ARRAY[]::text[],
    input_checksum varchar(128) NOT NULL,
    calculated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    PRIMARY KEY (business_date, need_snapshot_id),
    CONSTRAINT uq_pdd_need_snapshot_run_pair_type UNIQUE (
        business_date, calculation_run_id, origin_cd, sucursal, codigo_articulo, need_type
    ),
    FOREIGN KEY (business_date, branch_stock_position_id)
        REFERENCES stock_management.pdd_branch_stock_position (business_date, branch_stock_position_id)
        ON DELETE RESTRICT,
    FOREIGN KEY (scope_version_id, sucursal, codigo_articulo)
        REFERENCES stock_management.pdd_distribution_scope_pair
            (scope_version_id, destination_branch, codigo_articulo)
        ON DELETE RESTRICT,
    CONSTRAINT ck_pdd_need_snapshot_origin CHECK (origin_cd = 41),
    CONSTRAINT ck_pdd_need_snapshot_mandatory CHECK (
        (need_type = 'D' AND is_mandatory)
        OR (need_type = 'S' AND NOT is_mandatory)
    ),
    CONSTRAINT ck_pdd_need_snapshot_quantities CHECK (
        (calculation_status = 'BLOCKED'
            AND calculated_quantity IS NULL
            AND rounded_quantity IS NULL
            AND open_quantity IS NULL)
        OR (calculation_status <> 'BLOCKED'
            AND calculated_quantity >= 0
            AND rounded_quantity >= 0
            AND open_quantity >= 0)
    ),
    CONSTRAINT ck_pdd_need_snapshot_zero CHECK (
        calculation_status <> 'ZERO'
        OR (calculated_quantity = 0 AND rounded_quantity = 0 AND open_quantity = 0)
    )
) PARTITION BY RANGE (business_date);

CREATE INDEX ix_pdd_need_snapshot_backlog
    ON stock_management.pdd_need_snapshot
    (business_date DESC, is_mandatory DESC, irq_score DESC, target_date)
    WHERE calculation_status = 'CALCULATED' AND open_quantity > 0;

CREATE INDEX ix_pdd_need_snapshot_pair_date
    ON stock_management.pdd_need_snapshot (codigo_articulo, sucursal, business_date DESC, need_type);

CREATE TABLE stock_management.pdd_directed_need (
    directed_need_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    directed_need_uuid uuid NOT NULL DEFAULT gen_random_uuid(),
    origin_cd integer NOT NULL,
    need_type char(1) NOT NULL CHECK (need_type IN ('E', 'C', 'A')),
    business_reference varchar(120) NOT NULL,
    c_proveedor_primario integer,
    valid_from date NOT NULL,
    valid_to date,
    priority_score numeric(12,6) NOT NULL DEFAULT 0,
    owner_user varchar(100) NOT NULL,
    approver_user varchar(100),
    status varchar(20) NOT NULL CHECK (
        status IN ('DRAFT', 'ACTIVE', 'CLOSED', 'CANCELLED', 'EXPIRED')
    ),
    version_no integer NOT NULL DEFAULT 1 CHECK (version_no > 0),
    reason text NOT NULL,
    notes text,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    created_by varchar(100) NOT NULL,
    updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    updated_by varchar(100) NOT NULL,
    approved_at timestamptz,
    closed_at timestamptz,
    CONSTRAINT uq_pdd_directed_need_uuid UNIQUE (directed_need_uuid),
    CONSTRAINT uq_pdd_directed_need_reference UNIQUE (origin_cd, need_type, business_reference),
    CONSTRAINT ck_pdd_directed_need_origin CHECK (origin_cd = 41),
    CONSTRAINT ck_pdd_directed_need_validity CHECK (valid_to IS NULL OR valid_to >= valid_from),
    CONSTRAINT ck_pdd_directed_need_approval CHECK (
        status <> 'ACTIVE' OR (approver_user IS NOT NULL AND approved_at IS NOT NULL)
    )
);

CREATE INDEX ix_pdd_directed_need_active
    ON stock_management.pdd_directed_need (need_type, valid_from, valid_to, priority_score DESC)
    WHERE status = 'ACTIVE';

CREATE TABLE stock_management.pdd_directed_need_line (
    directed_need_line_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    directed_need_id bigint NOT NULL
        REFERENCES stock_management.pdd_directed_need(directed_need_id) ON DELETE RESTRICT,
    sucursal integer NOT NULL,
    codigo_articulo integer NOT NULL,
    original_quantity numeric(18,6) NOT NULL CHECK (original_quantity > 0),
    prepared_allocated_quantity numeric(18,6) NOT NULL DEFAULT 0
        CHECK (prepared_allocated_quantity >= 0),
    cancelled_quantity numeric(18,6) NOT NULL DEFAULT 0 CHECK (cancelled_quantity >= 0),
    open_quantity numeric(18,6) GENERATED ALWAYS AS (
        greatest(original_quantity - prepared_allocated_quantity - cancelled_quantity, 0)
    ) STORED,
    target_date date,
    sla_at timestamptz,
    unit_code varchar(20) NOT NULL DEFAULT 'UN',
    units_per_package numeric(18,6) CHECK (units_per_package > 0),
    packages_per_pallet numeric(18,6) CHECK (packages_per_pallet > 0),
    unit_weight_kg numeric(18,6) CHECK (unit_weight_kg >= 0),
    unit_volume_m3 numeric(18,9) CHECK (unit_volume_m3 >= 0),
    status varchar(20) NOT NULL CHECK (
        status IN ('OPEN', 'PARTIAL', 'FULFILLED', 'CANCELLED')
    ),
    last_activity_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    row_version integer NOT NULL DEFAULT 1 CHECK (row_version > 0),
    CONSTRAINT uq_pdd_directed_need_line UNIQUE (directed_need_id, sucursal, codigo_articulo),
    CONSTRAINT ck_pdd_directed_need_line_balance CHECK (
        prepared_allocated_quantity + cancelled_quantity <= original_quantity
    ),
    CONSTRAINT ck_pdd_directed_need_line_status CHECK (
        (status = 'OPEN' AND open_quantity = original_quantity)
        OR (status = 'PARTIAL' AND open_quantity > 0 AND open_quantity < original_quantity)
        OR (status IN ('FULFILLED', 'CANCELLED') AND open_quantity = 0)
    )
);

CREATE INDEX ix_pdd_directed_need_line_open
    ON stock_management.pdd_directed_need_line (sucursal, codigo_articulo, target_date)
    WHERE open_quantity > 0;

CREATE TABLE stock_management.pdd_directed_need_version (
    directed_need_version_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    directed_need_id bigint NOT NULL
        REFERENCES stock_management.pdd_directed_need(directed_need_id) ON DELETE RESTRICT,
    version_no integer NOT NULL CHECK (version_no > 0),
    valid_from_ts timestamptz NOT NULL DEFAULT clock_timestamp(),
    changed_by varchar(100) NOT NULL,
    change_reason text NOT NULL,
    before_state jsonb,
    after_state jsonb NOT NULL,
    correlation_id uuid,
    CONSTRAINT uq_pdd_directed_need_version UNIQUE (directed_need_id, version_no)
);

CREATE TABLE stock_management.pdd_current_backlog_line (
    backlog_line_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    backlog_line_uuid uuid NOT NULL DEFAULT gen_random_uuid(),
    snapshot_version uuid NOT NULL,
    business_date date NOT NULL,
    calculation_run_id bigint NOT NULL
        REFERENCES stock_management.pdd_calculation_run(calculation_run_id) ON DELETE RESTRICT,
    origin_cd integer NOT NULL,
    sucursal integer NOT NULL,
    codigo_articulo integer NOT NULL,
    c_proveedor_primario integer,
    d_open_quantity numeric(18,6) NOT NULL DEFAULT 0 CHECK (d_open_quantity >= 0),
    e_open_quantity numeric(18,6) NOT NULL DEFAULT 0 CHECK (e_open_quantity >= 0),
    c_open_quantity numeric(18,6) NOT NULL DEFAULT 0 CHECK (c_open_quantity >= 0),
    a_open_quantity numeric(18,6) NOT NULL DEFAULT 0 CHECK (a_open_quantity >= 0),
    s_open_quantity numeric(18,6) NOT NULL DEFAULT 0 CHECK (s_open_quantity >= 0),
    mandatory_open_quantity numeric(18,6) GENERATED ALWAYS AS (
        d_open_quantity + e_open_quantity + c_open_quantity
    ) STORED,
    optional_open_quantity numeric(18,6) GENERATED ALWAYS AS (
        a_open_quantity + s_open_quantity
    ) STORED,
    total_open_quantity numeric(18,6) GENERATED ALWAYS AS (
        d_open_quantity + e_open_quantity + c_open_quantity
        + a_open_quantity + s_open_quantity
    ) STORED,
    irq_score numeric(5,2) CHECK (irq_score BETWEEN 0 AND 100),
    priority_score numeric(12,6) NOT NULL DEFAULT 0,
    oldest_need_date date,
    target_date date,
    active_imported_quantity numeric(18,6) NOT NULL DEFAULT 0
        CHECK (active_imported_quantity >= 0),
    prepared_quantity numeric(18,6) NOT NULL DEFAULT 0 CHECK (prepared_quantity >= 0),
    in_transit_quantity numeric(18,6) NOT NULL DEFAULT 0 CHECK (in_transit_quantity >= 0),
    cd_reference_stock numeric(18,6),
    estimated_packages numeric(18,6) CHECK (estimated_packages >= 0),
    estimated_pallets numeric(18,6) CHECK (estimated_pallets >= 0),
    estimated_weight_kg numeric(18,6) CHECK (estimated_weight_kg >= 0),
    estimated_volume_m3 numeric(18,9) CHECK (estimated_volume_m3 >= 0),
    freshness_status varchar(20) NOT NULL CHECK (
        freshness_status IN ('CURRENT', 'STALE', 'INCOMPLETE')
    ),
    alert_codes text[] NOT NULL DEFAULT ARRAY[]::text[],
    row_version integer NOT NULL DEFAULT 1 CHECK (row_version > 0),
    input_checksum varchar(128) NOT NULL,
    published_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT uq_pdd_current_backlog_uuid UNIQUE (backlog_line_uuid),
    CONSTRAINT ck_pdd_current_backlog_origin CHECK (origin_cd = 41),
    CONSTRAINT ck_pdd_current_backlog_nonempty CHECK (total_open_quantity > 0)
);

CREATE UNIQUE INDEX uq_pdd_current_backlog_grain
    ON stock_management.pdd_current_backlog_line
    (origin_cd, sucursal, codigo_articulo, coalesce(c_proveedor_primario, -1));

CREATE INDEX ix_pdd_current_backlog_priority
    ON stock_management.pdd_current_backlog_line
    (freshness_status, priority_score DESC, irq_score DESC, target_date, oldest_need_date);

CREATE INDEX ix_pdd_current_backlog_supplier
    ON stock_management.pdd_current_backlog_line
    (c_proveedor_primario, sucursal, codigo_articulo);

CREATE TABLE stock_management.pdd_backlog_source_allocation (
    backlog_source_allocation_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    backlog_line_id bigint NOT NULL
        REFERENCES stock_management.pdd_current_backlog_line(backlog_line_id) ON DELETE CASCADE,
    source_type char(1) NOT NULL CHECK (source_type IN ('D', 'E', 'C', 'A', 'S')),
    source_entity_id bigint NOT NULL,
    source_business_date date,
    contributed_quantity numeric(18,6) NOT NULL CHECK (contributed_quantity > 0),
    prepared_allocated_quantity numeric(18,6) NOT NULL DEFAULT 0
        CHECK (prepared_allocated_quantity >= 0),
    attribution_order integer NOT NULL CHECK (attribution_order > 0),
    attribution_rule_version varchar(40) NOT NULL,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT uq_pdd_backlog_source_allocation UNIQUE (
        backlog_line_id, source_type, source_entity_id, source_business_date
    ),
    CONSTRAINT ck_pdd_backlog_source_prepared CHECK (
        prepared_allocated_quantity <= contributed_quantity
    )
);

COMMENT ON TABLE stock_management.pdd_backlog_source_allocation IS
'Atribucion contable del saldo y del cumplimiento a su fuente DECAS; no asigna ni reserva stock.';

CREATE TABLE stock_management.pdd_valkimia_import (
    valkimia_import_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    valkimia_import_uuid uuid NOT NULL DEFAULT gen_random_uuid(),
    idempotency_key varchar(160) NOT NULL,
    adapter_code varchar(60) NOT NULL,
    origin_cd integer NOT NULL,
    backlog_snapshot_version uuid NOT NULL,
    external_reference varchar(160),
    status varchar(30) NOT NULL CHECK (status IN (
        'PENDING', 'ACCEPTED', 'PARTIAL', 'COMPLETED', 'CANCELLED', 'FAILED', 'UNKNOWN'
    )),
    requested_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    imported_at timestamptz,
    requested_by varchar(100) NOT NULL,
    line_count integer NOT NULL CHECK (line_count >= 0),
    total_imported_quantity numeric(20,6) NOT NULL DEFAULT 0
        CHECK (total_imported_quantity >= 0),
    total_prepared_quantity numeric(20,6) NOT NULL DEFAULT 0
        CHECK (total_prepared_quantity >= 0),
    payload_checksum varchar(128) NOT NULL,
    detail jsonb NOT NULL DEFAULT '{}'::jsonb,
    CONSTRAINT uq_pdd_valkimia_import_uuid UNIQUE (valkimia_import_uuid),
    CONSTRAINT uq_pdd_valkimia_import_idempotency UNIQUE (adapter_code, idempotency_key),
    CONSTRAINT ck_pdd_valkimia_import_origin CHECK (origin_cd = 41),
    CONSTRAINT ck_pdd_valkimia_import_totals CHECK (
        total_prepared_quantity <= total_imported_quantity
    )
);

CREATE INDEX ix_pdd_valkimia_import_status_date
    ON stock_management.pdd_valkimia_import (status, requested_at DESC);

CREATE TABLE stock_management.pdd_valkimia_import_line (
    valkimia_import_line_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    valkimia_import_id bigint NOT NULL
        REFERENCES stock_management.pdd_valkimia_import(valkimia_import_id) ON DELETE RESTRICT,
    backlog_line_uuid uuid NOT NULL,
    backlog_line_version integer NOT NULL CHECK (backlog_line_version > 0),
    codigo_articulo integer NOT NULL,
    sucursal integer NOT NULL,
    imported_quantity numeric(18,6) NOT NULL CHECK (imported_quantity > 0),
    prepared_quantity numeric(18,6) NOT NULL DEFAULT 0 CHECK (prepared_quantity >= 0),
    normalized_status varchar(30) NOT NULL CHECK (normalized_status IN (
        'IMPORTED', 'PARTIAL', 'PREPARED', 'DISPATCHED', 'CANCELLED', 'FAILED', 'UNKNOWN'
    )),
    external_reference varchar(160),
    external_line_reference varchar(160),
    last_external_status varchar(100),
    last_updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    row_version integer NOT NULL DEFAULT 1 CHECK (row_version > 0),
    CONSTRAINT uq_pdd_valkimia_import_line UNIQUE (valkimia_import_id, backlog_line_uuid),
    CONSTRAINT ck_pdd_valkimia_import_line_prepared CHECK (
        prepared_quantity <= imported_quantity
    )
);

CREATE INDEX ix_pdd_valkimia_import_line_external
    ON stock_management.pdd_valkimia_import_line (external_reference, external_line_reference);

CREATE TABLE stock_management.pdd_execution_event (
    execution_event_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    deduplication_key varchar(200) NOT NULL,
    valkimia_import_id bigint NOT NULL
        REFERENCES stock_management.pdd_valkimia_import(valkimia_import_id) ON DELETE RESTRICT,
    valkimia_import_line_id bigint NOT NULL
        REFERENCES stock_management.pdd_valkimia_import_line(valkimia_import_line_id) ON DELETE RESTRICT,
    event_type varchar(30) NOT NULL CHECK (event_type IN (
        'IMPORTED', 'PREPARED', 'DISPATCHED', 'CANCELLED', 'CORRECTED', 'DELIVERED', 'UNKNOWN'
    )),
    external_status varchar(100),
    normalized_status varchar(30) NOT NULL CHECK (normalized_status IN (
        'IMPORTED', 'PARTIAL', 'PREPARED', 'DISPATCHED', 'CANCELLED', 'DELIVERED', 'UNKNOWN'
    )),
    quantity_semantics varchar(15) NOT NULL CHECK (
        quantity_semantics IN ('DELTA', 'CUMULATIVE')
    ),
    event_quantity numeric(18,6) NOT NULL CHECK (event_quantity >= 0),
    external_document varchar(160),
    external_line_reference varchar(160),
    shipment_reference varchar(160),
    estimated_arrival_at timestamptz,
    external_occurred_at timestamptz NOT NULL,
    received_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    mapping_version varchar(40) NOT NULL,
    payload_reference varchar(300),
    payload_hash varchar(128) NOT NULL,
    processing_status varchar(20) NOT NULL CHECK (
        processing_status IN ('RECEIVED', 'APPLIED', 'IGNORED', 'FAILED')
    ),
    error_detail text,
    CONSTRAINT uq_pdd_execution_event_dedup UNIQUE (deduplication_key)
);

CREATE INDEX ix_pdd_execution_event_line_date
    ON stock_management.pdd_execution_event (valkimia_import_line_id, external_occurred_at);

CREATE INDEX ix_pdd_execution_event_document
    ON stock_management.pdd_execution_event (external_document, external_line_reference);

CREATE TABLE stock_management.pdd_integration_message (
    integration_message_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    correlation_id uuid NOT NULL,
    idempotency_key varchar(200) NOT NULL,
    interface_code varchar(60) NOT NULL,
    direction varchar(10) NOT NULL CHECK (direction IN ('INBOUND', 'OUTBOUND')),
    message_type varchar(80) NOT NULL,
    status varchar(20) NOT NULL CHECK (
        status IN ('PENDING', 'PROCESSING', 'PROCESSED', 'RETRY', 'FAILED', 'DEAD_LETTER')
    ),
    payload_reference varchar(300) NOT NULL,
    payload_hash varchar(128) NOT NULL,
    attempt_count integer NOT NULL DEFAULT 0 CHECK (attempt_count >= 0),
    next_attempt_at timestamptz,
    received_at timestamptz,
    processed_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    error_detail text,
    CONSTRAINT uq_pdd_integration_message_idempotency UNIQUE (
        interface_code, direction, idempotency_key
    )
);

CREATE INDEX ix_pdd_integration_message_work
    ON stock_management.pdd_integration_message (status, next_attempt_at, created_at)
    WHERE status IN ('PENDING', 'RETRY');

CREATE INDEX ix_pdd_integration_message_correlation
    ON stock_management.pdd_integration_message (correlation_id, created_at);

CREATE TABLE stock_management.pdd_business_event_log (
    business_event_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    entity_type varchar(60) NOT NULL,
    entity_id varchar(120) NOT NULL,
    event_type varchar(80) NOT NULL,
    actor_type varchar(20) NOT NULL CHECK (actor_type IN ('USER', 'SYSTEM', 'INTEGRATION')),
    actor_id varchar(100) NOT NULL,
    occurred_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    correlation_id uuid,
    reason text,
    before_state jsonb,
    after_state jsonb,
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX ix_pdd_business_event_entity_date
    ON stock_management.pdd_business_event_log (entity_type, entity_id, occurred_at DESC);

CREATE INDEX ix_pdd_business_event_correlation
    ON stock_management.pdd_business_event_log (correlation_id, occurred_at)
    WHERE correlation_id IS NOT NULL;

COMMENT ON TABLE stock_management.pdd_branch_stock_position IS
'Foto inmutable del stock neto explicable por corrida, CD, sucursal y articulo.';

COMMENT ON COLUMN stock_management.pdd_branch_stock_position.net_stock IS
'Stock fisico + OC directa + transito CD - venta especial comprometida - transferencia confirmada pendiente.';

COMMENT ON TABLE stock_management.pdd_need_snapshot IS
'Foto inmutable de necesidades automaticas D/S. Las nuevas corridas reemplazan la foto vigente, no acumulan D/S.';

COMMENT ON TABLE stock_management.pdd_directed_need IS
'Cabecera persistente de necesidades dirigidas E/C/A; no se recrea en cada corrida.';

COMMENT ON TABLE stock_management.pdd_current_backlog_line IS
'Proyeccion reconstruible del saldo DECAS vigente. No es una orden, reserva ni asignacion de stock.';

COMMENT ON COLUMN stock_management.pdd_current_backlog_line.active_imported_quantity IS
'Cantidad del mismo backlog presente en importaciones activas; no se suma a la demanda.';

COMMENT ON TABLE stock_management.pdd_execution_event IS
'Evento externo append-only y deduplicado; importar por si solo no reduce el saldo.';

-- Las particiones mensuales de branch_stock_position, cd_stock_position y
-- need_snapshot deben crearse por migracion/job antes de cada carga.

COMMIT;
