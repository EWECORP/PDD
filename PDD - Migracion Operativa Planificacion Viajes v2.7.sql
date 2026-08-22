\set ON_ERROR_STOP on

-- PDD / Planificacion de viajes Connexa y ejecucion Valkimia - v2.7
-- Fecha: 2026-08-21
-- Migracion aditiva. No elimina ni reescribe backlog o ejecuciones existentes.

BEGIN;

SET LOCAL lock_timeout = '10s';
SET LOCAL statement_timeout = '0';

DO $guard$
BEGIN
    IF current_database() NOT IN (
        'connexa_platform_test',
        'connexa_platform_diarco',
        'connexa_platform_ms'
    ) THEN
        RAISE EXCEPTION
            'Migracion PDD operativa v2.7: base incorrecta (%).', current_database();
    END IF;

    IF to_regnamespace('stock_management') IS NULL THEN
        RAISE EXCEPTION 'No existe el esquema stock_management';
    END IF;

    IF to_regclass('stock_management.pdd_current_backlog_line') IS NULL
       OR to_regclass('stock_management.pdd_valkimia_import') IS NULL
       OR to_regclass('stock_management.pdd_valkimia_import_line') IS NULL THEN
        RAISE EXCEPTION
            'Debe aplicar primero el contrato operativo PDD DECAS y la migracion de prefijo v2.6';
    END IF;
END
$guard$;

-- La foto de backlog conserva el saldo de necesidad. Estas columnas representan
-- compromisos operativos y no se suman a la demanda DECAS.
ALTER TABLE stock_management.pdd_current_backlog_line
    ADD COLUMN IF NOT EXISTS active_planned_quantity numeric(18,6)
        NOT NULL DEFAULT 0 CHECK (active_planned_quantity >= 0);

ALTER TABLE stock_management.pdd_current_backlog_line
    ADD COLUMN IF NOT EXISTS available_to_plan_quantity numeric(18,6)
        GENERATED ALWAYS AS (
            greatest(
                d_open_quantity + e_open_quantity + c_open_quantity
                + a_open_quantity + s_open_quantity
                - active_planned_quantity - active_imported_quantity,
                0::numeric
            )
        ) STORED;

COMMENT ON COLUMN stock_management.pdd_current_backlog_line.active_planned_quantity IS
'Cantidad reservada por planes Connexa aprobados y aun no publicada a Valkimia.';

COMMENT ON COLUMN stock_management.pdd_current_backlog_line.available_to_plan_quantity IS
'Saldo seleccionable: DECAS abierto menos planificado e importado activo; nunca negativo.';

CREATE TABLE IF NOT EXISTS stock_management.pdd_dispatch_plan (
    dispatch_plan_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    dispatch_plan_uuid uuid NOT NULL DEFAULT gen_random_uuid(),
    plan_code varchar(80) NOT NULL,
    business_date date NOT NULL,
    origin_cd integer NOT NULL,
    backlog_snapshot_version uuid NOT NULL,
    status varchar(30) NOT NULL CHECK (status IN (
        'DRAFT', 'VALIDATED', 'APPROVED', 'PARTIALLY_PUBLISHED', 'PUBLISHED',
        'IN_EXECUTION', 'COMPLETED', 'CANCELLED'
    )),
    notes text,
    planned_by varchar(100) NOT NULL,
    approved_by varchar(100),
    approved_at timestamptz,
    cancelled_by varchar(100),
    cancelled_at timestamptz,
    cancellation_reason text,
    row_version integer NOT NULL DEFAULT 1 CHECK (row_version > 0),
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT uq_pdd_dispatch_plan_uuid UNIQUE (dispatch_plan_uuid),
    CONSTRAINT uq_pdd_dispatch_plan_code UNIQUE (origin_cd, plan_code),
    CONSTRAINT ck_pdd_dispatch_plan_origin CHECK (origin_cd = 41),
    CONSTRAINT ck_pdd_dispatch_plan_approval CHECK (
        status NOT IN ('APPROVED', 'PARTIALLY_PUBLISHED', 'PUBLISHED',
                       'IN_EXECUTION', 'COMPLETED')
        OR (approved_by IS NOT NULL AND approved_at IS NOT NULL)
    ),
    CONSTRAINT ck_pdd_dispatch_plan_cancellation CHECK (
        status <> 'CANCELLED'
        OR (cancelled_by IS NOT NULL AND cancelled_at IS NOT NULL
            AND cancellation_reason IS NOT NULL)
    )
);

CREATE INDEX IF NOT EXISTS ix_pdd_dispatch_plan_work
    ON stock_management.pdd_dispatch_plan
    (origin_cd, business_date DESC, status, updated_at DESC);

CREATE TABLE IF NOT EXISTS stock_management.pdd_dispatch_trip (
    dispatch_trip_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    dispatch_trip_uuid uuid NOT NULL DEFAULT gen_random_uuid(),
    dispatch_plan_id bigint NOT NULL
        REFERENCES stock_management.pdd_dispatch_plan(dispatch_plan_id) ON DELETE RESTRICT,
    trip_number integer NOT NULL CHECK (trip_number > 0),
    trip_code varchar(100) NOT NULL,
    status varchar(30) NOT NULL CHECK (status IN (
        'DRAFT', 'READY', 'APPROVED', 'PUBLISH_PENDING', 'PUBLISHED',
        'ACCEPTED', 'PARTIAL', 'PREPARING', 'PREPARED', 'DISPATCHED',
        'DELIVERED', 'CANCELLED', 'REJECTED', 'FAILED', 'UNKNOWN'
    )),
    planned_departure_at timestamptz,
    dispatch_window_start timestamptz,
    dispatch_window_end timestamptz,
    route_code varchar(80),
    vehicle_reference varchar(100),
    vehicle_type varchar(80),
    carrier_reference varchar(100),
    max_weight_kg numeric(18,6) CHECK (max_weight_kg > 0),
    max_volume_m3 numeric(18,9) CHECK (max_volume_m3 > 0),
    max_pallets numeric(18,6) CHECK (max_pallets > 0),
    planned_weight_kg numeric(18,6) NOT NULL DEFAULT 0 CHECK (planned_weight_kg >= 0),
    planned_volume_m3 numeric(18,9) NOT NULL DEFAULT 0 CHECK (planned_volume_m3 >= 0),
    planned_pallets numeric(18,6) NOT NULL DEFAULT 0 CHECK (planned_pallets >= 0),
    notes text,
    row_version integer NOT NULL DEFAULT 1 CHECK (row_version > 0),
    created_by varchar(100) NOT NULL,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT uq_pdd_dispatch_trip_uuid UNIQUE (dispatch_trip_uuid),
    CONSTRAINT uq_pdd_dispatch_trip_number UNIQUE (dispatch_plan_id, trip_number),
    CONSTRAINT uq_pdd_dispatch_trip_code UNIQUE (trip_code),
    CONSTRAINT ck_pdd_dispatch_trip_window CHECK (
        dispatch_window_end IS NULL OR dispatch_window_start IS NULL
        OR dispatch_window_end >= dispatch_window_start
    )
);

CREATE INDEX IF NOT EXISTS ix_pdd_dispatch_trip_work
    ON stock_management.pdd_dispatch_trip
    (status, planned_departure_at, dispatch_plan_id);

CREATE TABLE IF NOT EXISTS stock_management.pdd_dispatch_trip_stop (
    dispatch_trip_stop_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    dispatch_trip_stop_uuid uuid NOT NULL DEFAULT gen_random_uuid(),
    dispatch_trip_id bigint NOT NULL
        REFERENCES stock_management.pdd_dispatch_trip(dispatch_trip_id) ON DELETE RESTRICT,
    stop_sequence integer NOT NULL CHECK (stop_sequence > 0),
    sucursal integer NOT NULL,
    planned_arrival_at timestamptz,
    status varchar(20) NOT NULL DEFAULT 'PLANNED' CHECK (status IN (
        'PLANNED', 'IN_TRANSIT', 'ARRIVED', 'COMPLETED', 'CANCELLED'
    )),
    notes text,
    row_version integer NOT NULL DEFAULT 1 CHECK (row_version > 0),
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT uq_pdd_dispatch_trip_stop_uuid UNIQUE (dispatch_trip_stop_uuid),
    CONSTRAINT uq_pdd_dispatch_trip_stop_sequence UNIQUE (dispatch_trip_id, stop_sequence),
    CONSTRAINT uq_pdd_dispatch_trip_stop_branch UNIQUE (dispatch_trip_id, sucursal)
);

CREATE INDEX IF NOT EXISTS ix_pdd_dispatch_trip_stop_branch
    ON stock_management.pdd_dispatch_trip_stop (sucursal, status, planned_arrival_at);

CREATE TABLE IF NOT EXISTS stock_management.pdd_dispatch_trip_line (
    dispatch_trip_line_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    dispatch_trip_line_uuid uuid NOT NULL DEFAULT gen_random_uuid(),
    dispatch_trip_id bigint NOT NULL
        REFERENCES stock_management.pdd_dispatch_trip(dispatch_trip_id) ON DELETE RESTRICT,
    dispatch_trip_stop_id bigint NOT NULL
        REFERENCES stock_management.pdd_dispatch_trip_stop(dispatch_trip_stop_id) ON DELETE RESTRICT,
    backlog_line_uuid uuid NOT NULL,
    backlog_line_version integer NOT NULL CHECK (backlog_line_version > 0),
    backlog_snapshot_version uuid NOT NULL,
    codigo_articulo integer NOT NULL,
    sucursal integer NOT NULL,
    c_proveedor_primario integer,
    uom varchar(15) NOT NULL DEFAULT 'UNIT' CHECK (uom IN ('UNIT', 'KG')),
    planned_quantity numeric(18,6) NOT NULL CHECK (planned_quantity > 0),
    published_quantity numeric(18,6) NOT NULL DEFAULT 0 CHECK (published_quantity >= 0),
    accepted_quantity numeric(18,6) NOT NULL DEFAULT 0 CHECK (accepted_quantity >= 0),
    prepared_quantity numeric(18,6) NOT NULL DEFAULT 0 CHECK (prepared_quantity >= 0),
    dispatched_quantity numeric(18,6) NOT NULL DEFAULT 0 CHECK (dispatched_quantity >= 0),
    delivered_quantity numeric(18,6) NOT NULL DEFAULT 0 CHECK (delivered_quantity >= 0),
    cancelled_quantity numeric(18,6) NOT NULL DEFAULT 0 CHECK (cancelled_quantity >= 0),
    rejected_quantity numeric(18,6) NOT NULL DEFAULT 0 CHECK (rejected_quantity >= 0),
    estimated_packages numeric(18,6) CHECK (estimated_packages >= 0),
    estimated_pallets numeric(18,6) CHECK (estimated_pallets >= 0),
    estimated_weight_kg numeric(18,6) CHECK (estimated_weight_kg >= 0),
    estimated_volume_m3 numeric(18,9) CHECK (estimated_volume_m3 >= 0),
    irq_score numeric(5,2) CHECK (irq_score BETWEEN 0 AND 100),
    priority_score numeric(12,6) NOT NULL DEFAULT 0,
    status varchar(30) NOT NULL DEFAULT 'DRAFT' CHECK (status IN (
        'DRAFT', 'RESERVED', 'PUBLISH_PENDING', 'PUBLISHED', 'ACCEPTED',
        'PARTIAL', 'PREPARED', 'DISPATCHED', 'DELIVERED', 'CANCELLED',
        'REJECTED', 'FAILED', 'UNKNOWN'
    )),
    alert_codes text[] NOT NULL DEFAULT ARRAY[]::text[],
    input_checksum varchar(128) NOT NULL,
    row_version integer NOT NULL DEFAULT 1 CHECK (row_version > 0),
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT uq_pdd_dispatch_trip_line_uuid UNIQUE (dispatch_trip_line_uuid),
    CONSTRAINT uq_pdd_dispatch_trip_backlog_line UNIQUE (dispatch_trip_id, backlog_line_uuid),
    CONSTRAINT ck_pdd_dispatch_trip_line_progress CHECK (
        published_quantity <= planned_quantity
        AND accepted_quantity <= published_quantity
        AND prepared_quantity <= accepted_quantity
        AND dispatched_quantity <= prepared_quantity
        AND delivered_quantity <= dispatched_quantity
        AND cancelled_quantity + rejected_quantity <= planned_quantity
    )
);

-- No existe FK hacia pdd_current_backlog_line: esa tabla es una proyeccion
-- reemplazable. UUID, version y snapshot quedan congelados como referencia historica.
CREATE INDEX IF NOT EXISTS ix_pdd_dispatch_trip_line_backlog
    ON stock_management.pdd_dispatch_trip_line
    (backlog_line_uuid, backlog_line_version, status);

CREATE INDEX IF NOT EXISTS ix_pdd_dispatch_trip_line_branch_article
    ON stock_management.pdd_dispatch_trip_line
    (sucursal, codigo_articulo, status);

CREATE TABLE IF NOT EXISTS stock_management.pdd_dispatch_line_allocation (
    dispatch_line_allocation_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    dispatch_trip_line_id bigint NOT NULL
        REFERENCES stock_management.pdd_dispatch_trip_line(dispatch_trip_line_id) ON DELETE RESTRICT,
    source_type char(1) NOT NULL CHECK (source_type IN ('D', 'E', 'C', 'A', 'S')),
    source_entity_id bigint NOT NULL,
    source_business_date date,
    planned_allocated_quantity numeric(18,6) NOT NULL
        CHECK (planned_allocated_quantity > 0),
    prepared_allocated_quantity numeric(18,6) NOT NULL DEFAULT 0
        CHECK (prepared_allocated_quantity >= 0),
    dispatched_allocated_quantity numeric(18,6) NOT NULL DEFAULT 0
        CHECK (dispatched_allocated_quantity >= 0),
    cancelled_allocated_quantity numeric(18,6) NOT NULL DEFAULT 0
        CHECK (cancelled_allocated_quantity >= 0),
    attribution_order integer NOT NULL CHECK (attribution_order > 0),
    attribution_rule_version varchar(40) NOT NULL,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT uq_pdd_dispatch_line_allocation UNIQUE (
        dispatch_trip_line_id, source_type, source_entity_id, source_business_date
    ),
    CONSTRAINT ck_pdd_dispatch_line_allocation_progress CHECK (
        prepared_allocated_quantity <= planned_allocated_quantity
        AND dispatched_allocated_quantity <= prepared_allocated_quantity
        AND cancelled_allocated_quantity <= planned_allocated_quantity
    )
);

CREATE INDEX IF NOT EXISTS ix_pdd_dispatch_line_allocation_source
    ON stock_management.pdd_dispatch_line_allocation
    (source_type, source_entity_id, dispatch_trip_line_id);

-- Enlace de la publicacion Valkimia con el viaje aprobado.
ALTER TABLE stock_management.pdd_valkimia_import
    ADD COLUMN IF NOT EXISTS dispatch_trip_id bigint,
    ADD COLUMN IF NOT EXISTS dispatch_trip_stop_id bigint;

DO $import_trip_fk$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'fk_pdd_valkimia_import_dispatch_trip'
          AND conrelid = 'stock_management.pdd_valkimia_import'::regclass
    ) THEN
        ALTER TABLE stock_management.pdd_valkimia_import
            ADD CONSTRAINT fk_pdd_valkimia_import_dispatch_trip
            FOREIGN KEY (dispatch_trip_id)
            REFERENCES stock_management.pdd_dispatch_trip(dispatch_trip_id)
            ON DELETE RESTRICT;
    END IF;
END
$import_trip_fk$;

DO $import_stop_fk$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'fk_pdd_valkimia_import_dispatch_trip_stop'
          AND conrelid = 'stock_management.pdd_valkimia_import'::regclass
    ) THEN
        ALTER TABLE stock_management.pdd_valkimia_import
            ADD CONSTRAINT fk_pdd_valkimia_import_dispatch_trip_stop
            FOREIGN KEY (dispatch_trip_stop_id)
            REFERENCES stock_management.pdd_dispatch_trip_stop(dispatch_trip_stop_id)
            ON DELETE RESTRICT;
    END IF;
END
$import_stop_fk$;

DROP INDEX IF EXISTS stock_management.uq_pdd_valkimia_import_dispatch_trip;

CREATE UNIQUE INDEX IF NOT EXISTS uq_pdd_valkimia_import_trip_stop
    ON stock_management.pdd_valkimia_import
    (dispatch_trip_id, coalesce(dispatch_trip_stop_id, -1::bigint))
    WHERE dispatch_trip_id IS NOT NULL;

ALTER TABLE stock_management.pdd_valkimia_import
    ADD COLUMN IF NOT EXISTS last_external_updated_at timestamptz,
    ADD COLUMN IF NOT EXISTS last_polled_at timestamptz;

DO $replace_import_status_check$
DECLARE
    constraint_name text;
BEGIN
    SELECT c.conname INTO constraint_name
    FROM pg_constraint c
    WHERE c.conrelid = 'stock_management.pdd_valkimia_import'::regclass
      AND c.contype = 'c'
      AND pg_get_constraintdef(c.oid) LIKE '%status%'
    ORDER BY c.oid
    LIMIT 1;

    IF constraint_name IS NOT NULL THEN
        EXECUTE format(
            'ALTER TABLE stock_management.pdd_valkimia_import DROP CONSTRAINT %I',
            constraint_name
        );
    END IF;

    ALTER TABLE stock_management.pdd_valkimia_import
        ADD CONSTRAINT ck_pdd_valkimia_import_status CHECK (
            status IN (
                'PENDING', 'ACCEPTED', 'PARTIAL', 'COMPLETED', 'CANCELLED',
                'REJECTED', 'FAILED', 'UNKNOWN'
            )
        );
END
$replace_import_status_check$;

-- Identidad publica por linea y proyeccion acumulativa de la ejecucion.
ALTER TABLE stock_management.pdd_valkimia_import_line
    ADD COLUMN IF NOT EXISTS valkimia_import_line_uuid uuid;

UPDATE stock_management.pdd_valkimia_import_line
SET valkimia_import_line_uuid = gen_random_uuid()
WHERE valkimia_import_line_uuid IS NULL;

ALTER TABLE stock_management.pdd_valkimia_import_line
    ALTER COLUMN valkimia_import_line_uuid SET DEFAULT gen_random_uuid(),
    ALTER COLUMN valkimia_import_line_uuid SET NOT NULL,
    ADD COLUMN IF NOT EXISTS dispatch_trip_line_id bigint,
    ADD COLUMN IF NOT EXISTS accepted_quantity numeric(18,6) NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS dispatched_quantity numeric(18,6) NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS delivered_quantity numeric(18,6) NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS cancelled_quantity numeric(18,6) NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS rejected_quantity numeric(18,6) NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS last_external_updated_at timestamptz,
    ADD COLUMN IF NOT EXISTS last_polled_at timestamptz;

UPDATE stock_management.pdd_valkimia_import_line
SET accepted_quantity = prepared_quantity
WHERE accepted_quantity = 0
  AND prepared_quantity > 0;

CREATE UNIQUE INDEX IF NOT EXISTS uq_pdd_valkimia_import_line_uuid
    ON stock_management.pdd_valkimia_import_line (valkimia_import_line_uuid);

CREATE UNIQUE INDEX IF NOT EXISTS uq_pdd_valkimia_import_trip_line
    ON stock_management.pdd_valkimia_import_line (dispatch_trip_line_id)
    WHERE dispatch_trip_line_id IS NOT NULL;

DO $import_line_trip_fk$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'fk_pdd_valkimia_import_line_dispatch_trip_line'
          AND conrelid = 'stock_management.pdd_valkimia_import_line'::regclass
    ) THEN
        ALTER TABLE stock_management.pdd_valkimia_import_line
            ADD CONSTRAINT fk_pdd_valkimia_import_line_dispatch_trip_line
            FOREIGN KEY (dispatch_trip_line_id)
            REFERENCES stock_management.pdd_dispatch_trip_line(dispatch_trip_line_id)
            ON DELETE RESTRICT;
    END IF;
END
$import_line_trip_fk$;

DO $replace_import_line_status_check$
DECLARE
    constraint_name text;
BEGIN
    SELECT c.conname INTO constraint_name
    FROM pg_constraint c
    WHERE c.conrelid = 'stock_management.pdd_valkimia_import_line'::regclass
      AND c.contype = 'c'
      AND pg_get_constraintdef(c.oid) LIKE '%normalized_status%'
    ORDER BY c.oid
    LIMIT 1;

    IF constraint_name IS NOT NULL THEN
        EXECUTE format(
            'ALTER TABLE stock_management.pdd_valkimia_import_line DROP CONSTRAINT %I',
            constraint_name
        );
    END IF;

    ALTER TABLE stock_management.pdd_valkimia_import_line
        ADD CONSTRAINT ck_pdd_valkimia_import_line_status CHECK (
            normalized_status IN (
                'IMPORTED', 'ACCEPTED', 'PARTIAL', 'PREPARED', 'DISPATCHED',
                'DELIVERED', 'CANCELLED', 'REJECTED', 'FAILED', 'UNKNOWN'
            )
        );
END
$replace_import_line_status_check$;

DO $import_line_progress_checks$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'ck_pdd_valkimia_import_line_execution_progress'
          AND conrelid = 'stock_management.pdd_valkimia_import_line'::regclass
    ) THEN
        ALTER TABLE stock_management.pdd_valkimia_import_line
            ADD CONSTRAINT ck_pdd_valkimia_import_line_execution_progress CHECK (
                accepted_quantity BETWEEN 0 AND imported_quantity
                AND prepared_quantity <= accepted_quantity
                AND dispatched_quantity >= 0
                AND dispatched_quantity <= prepared_quantity
                AND delivered_quantity >= 0
                AND delivered_quantity <= dispatched_quantity
                AND cancelled_quantity >= 0
                AND rejected_quantity >= 0
                AND cancelled_quantity + rejected_quantity <= imported_quantity
            );
    END IF;
END
$import_line_progress_checks$;

CREATE TABLE IF NOT EXISTS stock_management.pdd_valkimia_status_mapping (
    valkimia_status_mapping_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    adapter_code varchar(60) NOT NULL,
    external_status varchar(100) NOT NULL,
    mapping_version varchar(40) NOT NULL,
    normalized_status varchar(30) NOT NULL CHECK (normalized_status IN (
        'IMPORTED', 'ACCEPTED', 'PARTIAL', 'PREPARED', 'DISPATCHED',
        'DELIVERED', 'CANCELLED', 'REJECTED', 'FAILED', 'UNKNOWN'
    )),
    event_type varchar(30) NOT NULL CHECK (event_type IN (
        'IMPORTED', 'PREPARED', 'DISPATCHED', 'CANCELLED',
        'CORRECTED', 'DELIVERED', 'UNKNOWN'
    )),
    quantity_semantics varchar(15) NOT NULL DEFAULT 'CUMULATIVE' CHECK (
        quantity_semantics IN ('DELTA', 'CUMULATIVE')
    ),
    is_terminal boolean NOT NULL DEFAULT false,
    is_active boolean NOT NULL DEFAULT true,
    description text,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    created_by varchar(100) NOT NULL,
    CONSTRAINT uq_pdd_valkimia_status_mapping UNIQUE (
        adapter_code, external_status, mapping_version
    )
);

CREATE INDEX IF NOT EXISTS ix_pdd_valkimia_status_mapping_active
    ON stock_management.pdd_valkimia_status_mapping
    (adapter_code, mapping_version, external_status)
    WHERE is_active;

CREATE TABLE IF NOT EXISTS stock_management.pdd_integration_checkpoint (
    integration_checkpoint_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    interface_code varchar(60) NOT NULL,
    direction varchar(10) NOT NULL CHECK (direction IN ('INBOUND', 'OUTBOUND')),
    scope_key varchar(120) NOT NULL,
    cursor_value varchar(300),
    last_success_at timestamptz,
    last_full_reconciliation_at timestamptz,
    status varchar(20) NOT NULL DEFAULT 'READY' CHECK (
        status IN ('READY', 'RUNNING', 'DEGRADED', 'FAILED')
    ),
    detail jsonb NOT NULL DEFAULT '{}'::jsonb,
    row_version integer NOT NULL DEFAULT 1 CHECK (row_version > 0),
    updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT uq_pdd_integration_checkpoint UNIQUE (
        interface_code, direction, scope_key
    )
);

COMMENT ON TABLE stock_management.pdd_dispatch_plan IS
'Plan Connexa que congela una seleccion del backlog antes de crear viajes y publicar a Valkimia.';

COMMENT ON TABLE stock_management.pdd_dispatch_trip IS
'Viaje o carga planificada y cubicada por Connexa; Valkimia solamente la ejecuta.';

COMMENT ON TABLE stock_management.pdd_dispatch_trip_line IS
'Cantidad de una linea de backlog reservada para un viaje. Conserva UUID, version y snapshot leidos.';

COMMENT ON TABLE stock_management.pdd_dispatch_line_allocation IS
'Imputacion congelada de una linea de viaje a sus fuentes DECAS en orden E vencida, E, C, D, A, S.';

COMMENT ON TABLE stock_management.pdd_valkimia_import IS
'Publicacion de un viaje aprobado hacia el adaptador Valkimia; no es un borrador ni un plan editable.';

COMMENT ON TABLE stock_management.pdd_integration_checkpoint IS
'Cursor y estado durable del polling o escritura de una interfaz legacy.';

COMMIT;
