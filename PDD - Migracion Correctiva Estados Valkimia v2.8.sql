-- PDD - Migracion Correctiva Estados Valkimia v2.8
-- Objetivo: alinear definitivamente catalogo, eventos y checks. No existe un
-- binario Java anterior que dependa de normalized_status.
--
-- Uso Flyway sugerido:
-- V<timestamp>__align_pdd_valkimia_status_contract.sql
--
-- Este archivo no contiene BEGIN/COMMIT ni comandos psql. Flyway debe
-- ejecutarlo transaccionalmente. No modificar migraciones ya aplicadas.

DO $preconditions$
BEGIN
    IF to_regclass('stock_management.pdd_valkimia_import_line_status') IS NULL THEN
        RAISE EXCEPTION
            'Falta stock_management.pdd_valkimia_import_line_status';
    END IF;

    IF to_regclass('stock_management.pdd_valkimia_import_line') IS NULL THEN
        RAISE EXCEPTION
            'Falta stock_management.pdd_valkimia_import_line';
    END IF;

    IF to_regclass('stock_management.pdd_valkimia_status_mapping') IS NULL THEN
        RAISE EXCEPTION
            'Falta stock_management.pdd_valkimia_status_mapping';
    END IF;

    IF to_regclass('stock_management.pdd_execution_event') IS NULL THEN
        RAISE EXCEPTION
            'Falta stock_management.pdd_execution_event';
    END IF;
END
$preconditions$;

-- La terminalidad pertenece al estado normalizado. is_active permite retirar
-- un codigo de seleccion futura sin borrar historia. display_order es solo UX.
ALTER TABLE stock_management.pdd_valkimia_import_line_status
    ADD COLUMN IF NOT EXISTS is_terminal boolean NOT NULL DEFAULT false,
    ADD COLUMN IF NOT EXISTS is_active boolean NOT NULL DEFAULT true,
    ADD COLUMN IF NOT EXISTS display_order smallint;

INSERT INTO stock_management.pdd_valkimia_import_line_status
    (name, description, is_terminal, is_active, display_order)
VALUES
    ('IMPORTED',
     'Linea recibida por el adaptador; todavia sin confirmacion de ejecucion.',
     false, true, 10),
    ('ACCEPTED',
     'Valkimia acepto la linea y se compromete a prepararla.',
     false, true, 20),
    ('PARTIAL',
     'Ejecucion parcial sobre una parte de la cantidad importada.',
     false, true, 30),
    ('PREPARED',
     'Mercaderia preparada en el CD y lista para despacho.',
     false, true, 40),
    ('DISPATCHED',
     'Mercaderia despachada desde el CD.',
     false, true, 50),
    ('DELIVERED',
     'Mercaderia entregada en la sucursal destino.',
     true, true, 60),
    ('CANCELLED',
     'Linea cancelada desde Connexa o desde Valkimia.',
     true, true, 70),
    ('REJECTED',
     'Valkimia rechazo la linea; no se va a ejecutar.',
     true, true, 80),
    ('FAILED',
     'La ejecucion fallo de forma no recuperable.',
     true, true, 90),
    ('UNKNOWN',
     'Estado externo sin mapeo conocido; requiere revision manual.',
     false, true, 100)
ON CONFLICT (name) DO UPDATE
SET description = EXCLUDED.description,
    is_terminal = EXCLUDED.is_terminal,
    is_active = EXCLUDED.is_active,
    display_order = EXCLUDED.display_order;

DO $validate_catalog$
DECLARE
    missing_codes text;
BEGIN
    SELECT string_agg(required.name, ', ' ORDER BY required.name)
    INTO missing_codes
    FROM (
        VALUES
            ('IMPORTED'), ('ACCEPTED'), ('PARTIAL'), ('PREPARED'),
            ('DISPATCHED'), ('DELIVERED'), ('CANCELLED'), ('REJECTED'),
            ('FAILED'), ('UNKNOWN')
    ) AS required(name)
    WHERE NOT EXISTS (
        SELECT 1
        FROM stock_management.pdd_valkimia_import_line_status AS actual
        WHERE actual.name = required.name
    );

    IF missing_codes IS NOT NULL THEN
        RAISE EXCEPTION 'Faltan estados Valkimia requeridos: %', missing_codes;
    END IF;

    IF EXISTS (
        SELECT 1
        FROM stock_management.pdd_valkimia_import_line_status
        WHERE display_order IS NULL OR display_order <= 0
    ) THEN
        RAISE EXCEPTION
            'Todos los estados Valkimia deben tener display_order positivo';
    END IF;
END
$validate_catalog$;

ALTER TABLE stock_management.pdd_valkimia_import_line_status
    ALTER COLUMN display_order SET NOT NULL;

DO $replace_catalog_checks$
DECLARE
    constraint_record record;
BEGIN
    FOR constraint_record IN
        SELECT conname
        FROM pg_constraint
        WHERE conrelid =
              'stock_management.pdd_valkimia_import_line_status'::regclass
          AND contype = 'c'
          AND (
              pg_get_constraintdef(oid) ILIKE '%name%upper%'
              OR pg_get_constraintdef(oid) ILIKE '%display_order%'
          )
    LOOP
        EXECUTE format(
            'ALTER TABLE stock_management.pdd_valkimia_import_line_status '
            'DROP CONSTRAINT %I',
            constraint_record.conname
        );
    END LOOP;
END
$replace_catalog_checks$;

ALTER TABLE stock_management.pdd_valkimia_import_line_status
    ADD CONSTRAINT ck_pdd_valkimia_import_line_status_name
        CHECK (
            name = upper(name)
            AND name ~ '^[A-Z][A-Z0-9_]*$'
        ),
    ADD CONSTRAINT ck_pdd_valkimia_import_line_status_display_order
        CHECK (display_order > 0);

-- Alineacion del historial: status_id pasa a ser la referencia canonica.
ALTER TABLE stock_management.pdd_execution_event
    ADD COLUMN IF NOT EXISTS status_id bigint;

DO $backfill_execution_event_status$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = 'stock_management'
          AND table_name = 'pdd_execution_event'
          AND column_name = 'normalized_status'
    ) THEN
        UPDATE stock_management.pdd_execution_event AS event
        SET status_id = status.id
        FROM stock_management.pdd_valkimia_import_line_status AS status
        WHERE event.status_id IS NULL
          AND status.name = event.normalized_status;
    END IF;

    IF EXISTS (
        SELECT 1
        FROM stock_management.pdd_execution_event
        WHERE status_id IS NULL
    ) THEN
        RAISE EXCEPTION
            'Hay eventos con estado no convertible al catalogo Valkimia';
    END IF;
END
$backfill_execution_event_status$;

DO $execution_event_status_fk$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conrelid = 'stock_management.pdd_execution_event'::regclass
          AND conname = 'fk_pdd_execution_event_status'
    ) THEN
        ALTER TABLE stock_management.pdd_execution_event
            ADD CONSTRAINT fk_pdd_execution_event_status
            FOREIGN KEY (status_id)
            REFERENCES stock_management.pdd_valkimia_import_line_status(id)
            ON DELETE RESTRICT;
    END IF;
END
$execution_event_status_fk$;

ALTER TABLE stock_management.pdd_execution_event
    ALTER COLUMN status_id SET NOT NULL;

-- event_type representa el hecho recibido, no el estado agregado PARTIAL.
DO $replace_event_type_checks$
DECLARE
    constraint_record record;
BEGIN
    FOR constraint_record IN
        SELECT conname
        FROM pg_constraint
        WHERE conrelid = 'stock_management.pdd_execution_event'::regclass
          AND contype = 'c'
          AND pg_get_constraintdef(oid) ILIKE '%event_type%'
    LOOP
        EXECUTE format(
            'ALTER TABLE stock_management.pdd_execution_event '
            'DROP CONSTRAINT %I',
            constraint_record.conname
        );
    END LOOP;

    ALTER TABLE stock_management.pdd_execution_event
        ADD CONSTRAINT ck_pdd_execution_event_event_type
        CHECK (
            event_type IN (
                'IMPORTED', 'ACCEPTED', 'PREPARED', 'DISPATCHED',
                'DELIVERED', 'CANCELLED', 'REJECTED', 'FAILED',
                'CORRECTED', 'UNKNOWN'
            )
        );

    FOR constraint_record IN
        SELECT conname
        FROM pg_constraint
        WHERE conrelid =
              'stock_management.pdd_valkimia_status_mapping'::regclass
          AND contype = 'c'
          AND pg_get_constraintdef(oid) ILIKE '%event_type%'
    LOOP
        EXECUTE format(
            'ALTER TABLE stock_management.pdd_valkimia_status_mapping '
            'DROP CONSTRAINT %I',
            constraint_record.conname
        );
    END LOOP;

    ALTER TABLE stock_management.pdd_valkimia_status_mapping
        ADD CONSTRAINT ck_pdd_valkimia_status_mapping_event_type
        CHECK (
            event_type IN (
                'IMPORTED', 'ACCEPTED', 'PREPARED', 'DISPATCHED',
                'DELIVERED', 'CANCELLED', 'REJECTED', 'FAILED',
                'CORRECTED', 'UNKNOWN'
            )
        );
END
$replace_event_type_checks$;

-- Antes de retirar la duplicacion se valida/sincroniza la terminalidad.
DO $sync_mapping_terminality$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = 'stock_management'
          AND table_name = 'pdd_valkimia_status_mapping'
          AND column_name = 'is_terminal'
    ) THEN
        UPDATE stock_management.pdd_valkimia_status_mapping AS mapping
        SET is_terminal = status.is_terminal
        FROM stock_management.pdd_valkimia_import_line_status AS status
        WHERE status.id = mapping.status_id
          AND mapping.is_terminal IS DISTINCT FROM status.is_terminal;
    END IF;
END
$sync_mapping_terminality$;

CREATE INDEX IF NOT EXISTS ix_pdd_valkimia_import_line_status_updated
    ON stock_management.pdd_valkimia_import_line
       (status_id, last_updated_at);

COMMENT ON TABLE stock_management.pdd_valkimia_import_line_status IS
    'Catalogo canonico de estados normalizados de una linea enviada a Valkimia.';

COMMENT ON COLUMN stock_management.pdd_valkimia_import_line_status.name IS
    'Codigo estable expuesto por API; no utilizar el ID fisico fuera de persistencia.';

COMMENT ON COLUMN stock_management.pdd_valkimia_import_line_status.is_terminal IS
    'Indica que la linea no admite nuevas transiciones operativas ordinarias.';

COMMENT ON COLUMN stock_management.pdd_execution_event.status_id IS
    'Estado normalizado canonico asociado al evento de ejecucion.';

-- Permiso de lectura para el rol de API cuando exista. No se otorgan permisos
-- amplios sobre el resto del esquema.
DO $optional_api_grant$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'connexa_pdd_api') THEN
        GRANT SELECT
            ON stock_management.pdd_valkimia_import_line_status
            TO connexa_pdd_api;
    END IF;
END
$optional_api_grant$;

-- No existe un binario Java previo que dependa de estas columnas. Se valida la
-- equivalencia antes de retirar las dos fuentes de verdad duplicadas.
DO $final_contract_validation$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = 'stock_management'
          AND table_name = 'pdd_execution_event'
          AND column_name = 'normalized_status'
    ) AND EXISTS (
        SELECT 1
        FROM stock_management.pdd_execution_event AS event
        JOIN stock_management.pdd_valkimia_import_line_status AS status
          ON status.id = event.status_id
        WHERE event.normalized_status IS DISTINCT FROM status.name
    ) THEN
        RAISE EXCEPTION
            'normalized_status y status_id no coinciden';
    END IF;

    IF EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = 'stock_management'
          AND table_name = 'pdd_valkimia_status_mapping'
          AND column_name = 'is_terminal'
    ) AND EXISTS (
        SELECT 1
        FROM stock_management.pdd_valkimia_status_mapping AS mapping
        JOIN stock_management.pdd_valkimia_import_line_status AS status
          ON status.id = mapping.status_id
        WHERE mapping.is_terminal IS DISTINCT FROM status.is_terminal
    ) THEN
        RAISE EXCEPTION
            'La terminalidad del mapping no coincide con el catalogo';
    END IF;
END
$final_contract_validation$;

ALTER TABLE stock_management.pdd_execution_event
    DROP COLUMN IF EXISTS normalized_status;

ALTER TABLE stock_management.pdd_valkimia_status_mapping
    DROP COLUMN IF EXISTS is_terminal;

COMMENT ON COLUMN stock_management.pdd_execution_event.status_id IS
    'FK al estado normalizado; reemplaza el antiguo normalized_status textual.';

COMMENT ON COLUMN stock_management.pdd_valkimia_status_mapping.status_id IS
    'Estado normalizado de destino. La terminalidad se obtiene del catalogo.';

