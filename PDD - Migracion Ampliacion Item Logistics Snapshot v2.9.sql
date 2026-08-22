-- PDD - Migracion Ampliacion Item Logistics Snapshot v2.9
-- Fecha: 2026-08-21
-- Objetivo: ampliar el snapshot logistico operacional para peso, volumen,
-- palletizacion, manipulacion y calidad por eje.
--
-- Uso Flyway sugerido:
-- V<timestamp>__extend_pdd_item_logistics_snapshot.sql
--
-- Este archivo no contiene BEGIN/COMMIT ni comandos psql. Flyway debe
-- ejecutarlo transaccionalmente. No modificar una migracion ya aplicada.
-- Si excepcionalmente se ejecuta con psql:
-- psql --set ON_ERROR_STOP=1 --file <archivo.sql>

SET LOCAL lock_timeout = '15s';
SET LOCAL statement_timeout = '0';

DO $preconditions$
BEGIN
    IF current_database() NOT IN (
        'connexa_platform_test',
        'connexa_platform_diarco',
        'connexa_platform_ms'
    ) THEN
        RAISE EXCEPTION
            'Migracion PDD item logistics v2.9: base incorrecta (%).',
            current_database();
    END IF;

    IF to_regnamespace('stock_management') IS NULL THEN
        RAISE EXCEPTION 'No existe el esquema stock_management';
    END IF;

    IF to_regclass('stock_management.pdd_item_logistics_snapshot') IS NULL THEN
        RAISE EXCEPTION
            'Falta stock_management.pdd_item_logistics_snapshot';
    END IF;

    IF to_regclass('stock_management.pdd_calculation_run') IS NULL
       OR to_regclass('stock_management.pdd_source_snapshot') IS NULL THEN
        RAISE EXCEPTION
            'Faltan dependencias operativas de pdd_item_logistics_snapshot';
    END IF;
END
$preconditions$;

-- Identidad y procedencia. source_logistics_id es una referencia logica:
-- no corresponde una FK entre la base operacional y diarco_data.
ALTER TABLE stock_management.pdd_item_logistics_snapshot
    ADD COLUMN IF NOT EXISTS source_logistics_id bigint,
    ADD COLUMN IF NOT EXISTS supplier_code integer,
    ADD COLUMN IF NOT EXISTS logistics_configuration_code varchar(60),
    ADD COLUMN IF NOT EXISTS source_valid_from timestamptz,
    ADD COLUMN IF NOT EXISTS sells_by_weight boolean,
    ADD COLUMN IF NOT EXISTS package_uom varchar(30),
    ADD COLUMN IF NOT EXISTS unit_gtin varchar(14),
    ADD COLUMN IF NOT EXISTS package_gtin varchar(14),
    ADD COLUMN IF NOT EXISTS source_reference varchar(200);

-- Peso. unit_weight_kg sigue siendo el peso efectivo por unidad utilizado
-- por los calculos existentes.
ALTER TABLE stock_management.pdd_item_logistics_snapshot
    ADD COLUMN IF NOT EXISTS unit_net_weight_kg numeric(18,6),
    ADD COLUMN IF NOT EXISTS unit_gross_weight_kg numeric(18,6),
    ADD COLUMN IF NOT EXISTS package_gross_weight_kg numeric(18,6),
    ADD COLUMN IF NOT EXISTS weight_basis varchar(30);

-- Dimensiones exteriores del bulto y volumen.
-- unit_volume_m3 sigue siendo el volumen efectivo unitario.
ALTER TABLE stock_management.pdd_item_logistics_snapshot
    ADD COLUMN IF NOT EXISTS package_length_cm numeric(12,3),
    ADD COLUMN IF NOT EXISTS package_width_cm numeric(12,3),
    ADD COLUMN IF NOT EXISTS package_height_cm numeric(12,3),
    ADD COLUMN IF NOT EXISTS package_volume_m3 numeric(18,9),
    ADD COLUMN IF NOT EXISTS volume_method varchar(30);

-- Palletizacion.
ALTER TABLE stock_management.pdd_item_logistics_snapshot
    ADD COLUMN IF NOT EXISTS packages_per_layer integer,
    ADD COLUMN IF NOT EXISTS layers_per_pallet integer,
    ADD COLUMN IF NOT EXISTS units_per_pallet numeric(18,6),
    ADD COLUMN IF NOT EXISTS pallet_type varchar(30),
    ADD COLUMN IF NOT EXISTS pallet_length_cm numeric(12,3),
    ADD COLUMN IF NOT EXISTS pallet_width_cm numeric(12,3),
    ADD COLUMN IF NOT EXISTS loaded_pallet_height_cm numeric(12,3),
    ADD COLUMN IF NOT EXISTS pallet_gross_weight_kg numeric(18,6);

-- Manipulacion. Son atributos opcionales hasta que DIARCO disponga de la
-- fuente correspondiente.
ALTER TABLE stock_management.pdd_item_logistics_snapshot
    ADD COLUMN IF NOT EXISTS stackable boolean,
    ADD COLUMN IF NOT EXISTS max_stack_levels smallint,
    ADD COLUMN IF NOT EXISTS fragile boolean,
    ADD COLUMN IF NOT EXISTS hazardous boolean,
    ADD COLUMN IF NOT EXISTS temperature_zone varchar(20),
    ADD COLUMN IF NOT EXISTS temperature_min_c numeric(6,2),
    ADD COLUMN IF NOT EXISTS temperature_max_c numeric(6,2),
    ADD COLUMN IF NOT EXISTS orientation_code varchar(20);

-- Los defaults conservadores mantienen compatible al publicador Python
-- anterior. El publicador V2 debe enviar explicitamente los cuatro estados y
-- quality_issue_codes; no debe depender de estos defaults.
ALTER TABLE stock_management.pdd_item_logistics_snapshot
    ADD COLUMN IF NOT EXISTS packaging_quality_status varchar(20)
        NOT NULL DEFAULT 'MISSING',
    ADD COLUMN IF NOT EXISTS weight_quality_status varchar(20)
        NOT NULL DEFAULT 'MISSING',
    ADD COLUMN IF NOT EXISTS volume_quality_status varchar(20)
        NOT NULL DEFAULT 'MISSING',
    ADD COLUMN IF NOT EXISTS pallet_quality_status varchar(20)
        NOT NULL DEFAULT 'MISSING',
    ADD COLUMN IF NOT EXISTS quality_issue_codes text[]
        NOT NULL DEFAULT ARRAY['LOGISTICS_CONTRACT_V2_NOT_POPULATED']::text[],
    ADD COLUMN IF NOT EXISTS verified_at timestamptz,
    ADD COLUMN IF NOT EXISTS verified_by varchar(120),
    ADD COLUMN IF NOT EXISTS attributes jsonb
        NOT NULL DEFAULT '{}'::jsonb;

-- Backfill objetivo de snapshots existentes. No inventa datos: solamente
-- clasifica lo que ya estaba persistido con el contrato V1.
UPDATE stock_management.pdd_item_logistics_snapshot AS snapshot
SET packaging_quality_status = CASE
        WHEN nullif(btrim(snapshot.base_unit), '') IS NOT NULL
             AND snapshot.units_per_package > 0
            THEN 'SOURCE'
        ELSE 'MISSING'
    END,
    weight_quality_status = CASE
        WHEN snapshot.unit_weight_kg > 0 THEN 'SOURCE'
        ELSE 'MISSING'
    END,
    volume_quality_status = CASE
        WHEN snapshot.unit_volume_m3 > 0 THEN 'SOURCE'
        ELSE 'MISSING'
    END,
    pallet_quality_status = CASE
        WHEN snapshot.packages_per_pallet > 0 THEN 'SOURCE'
        ELSE 'MISSING'
    END,
    quality_issue_codes = ARRAY(
        SELECT issue_code
        FROM unnest(ARRAY_REMOVE(ARRAY[
            CASE
                WHEN nullif(btrim(snapshot.base_unit), '') IS NULL
                     OR snapshot.units_per_package IS NULL
                    THEN 'PACKAGING_MISSING'
            END,
            CASE
                WHEN snapshot.unit_weight_kg IS NULL
                    THEN 'WEIGHT_MISSING'
            END,
            CASE
                WHEN snapshot.unit_volume_m3 IS NULL
                    THEN 'VOLUME_MISSING'
            END,
            CASE
                WHEN snapshot.packages_per_pallet IS NULL
                    THEN 'PALLET_CONFIGURATION_MISSING'
            END
        ]::text[], NULL)) AS issue_code
        ORDER BY issue_code
    );

-- Antes de endurecer los checks se informa expresamente cualquier valor V1
-- que utilizaba cero como sinonimo de desconocido.
DO $validate_legacy_values$
DECLARE
    invalid_count bigint;
BEGIN
    SELECT count(*)
    INTO invalid_count
    FROM stock_management.pdd_item_logistics_snapshot
    WHERE nullif(btrim(base_unit), '') IS NULL
       OR units_per_package <= 0
       OR packages_per_pallet <= 0
       OR unit_weight_kg <= 0
       OR unit_volume_m3 <= 0;

    IF invalid_count > 0 THEN
        RAISE EXCEPTION
            'Hay % snapshots V1 con texto vacio o valores logisticos <= 0. '
            'Corregirlos a NULL antes de aplicar v2.9.',
            invalid_count;
    END IF;
END
$validate_legacy_values$;

-- Se reemplazan solamente checks de las columnas cuyo dominio cambia. El
-- bloque admite que el nombre original haya sido generado por PostgreSQL.
DO $replace_checks$
DECLARE
    constraint_record record;
BEGIN
    FOR constraint_record IN
        SELECT conname
        FROM pg_constraint
        WHERE conrelid =
              'stock_management.pdd_item_logistics_snapshot'::regclass
          AND contype = 'c'
          AND pg_get_constraintdef(oid) ILIKE ANY (ARRAY[
              '%quality_status%',
              '%unit_weight_kg%',
              '%unit_volume_m3%',
              '%source_logistics_id%',
              '%supplier_code%',
              '%logistics_configuration_code%',
              '%source_valid_from%',
              '%package_uom%',
              '%unit_gtin%',
              '%package_gtin%',
              '%source_reference%',
              '%unit_net_weight_kg%',
              '%unit_gross_weight_kg%',
              '%package_gross_weight_kg%',
              '%weight_basis%',
              '%package_length_cm%',
              '%package_width_cm%',
              '%package_height_cm%',
              '%package_volume_m3%',
              '%volume_method%',
              '%packages_per_layer%',
              '%layers_per_pallet%',
              '%units_per_pallet%',
              '%pallet_type%',
              '%pallet_length_cm%',
              '%pallet_width_cm%',
              '%loaded_pallet_height_cm%',
              '%pallet_gross_weight_kg%',
              '%stackable%',
              '%max_stack_levels%',
              '%temperature_zone%',
              '%temperature_min_c%',
              '%temperature_max_c%',
              '%orientation_code%',
              '%quality_issue_codes%',
              '%verified_at%',
              '%verified_by%',
              '%attributes%'
          ])
    LOOP
        EXECUTE format(
            'ALTER TABLE stock_management.pdd_item_logistics_snapshot '
            'DROP CONSTRAINT %I',
            constraint_record.conname
        );
    END LOOP;
END
$replace_checks$;

ALTER TABLE stock_management.pdd_item_logistics_snapshot
    ADD CONSTRAINT ck_pdd_item_logistics_overall_quality
        CHECK (quality_status IN (
            'COMPLETE', 'PARTIAL', 'ESTIMATED', 'MISSING', 'INVALID'
        )),
    ADD CONSTRAINT ck_pdd_item_logistics_effective_values
        CHECK (
            nullif(btrim(base_unit), '') IS NOT NULL
            AND (units_per_package IS NULL OR units_per_package > 0)
            AND (packages_per_pallet IS NULL OR packages_per_pallet > 0)
            AND (unit_weight_kg IS NULL OR unit_weight_kg > 0)
            AND (unit_volume_m3 IS NULL OR unit_volume_m3 > 0)
        ),
    ADD CONSTRAINT ck_pdd_item_logistics_source_identity
        CHECK (
            (source_logistics_id IS NULL OR source_logistics_id > 0)
            AND (supplier_code IS NULL OR supplier_code > 0)
            AND (
                logistics_configuration_code IS NULL
                OR nullif(btrim(logistics_configuration_code), '') IS NOT NULL
            )
            AND (
                source_reference IS NULL
                OR nullif(btrim(source_reference), '') IS NOT NULL
            )
            AND (
                source_valid_from IS NULL
                OR source_valid_from <= source_as_of_ts
            )
        ),
    ADD CONSTRAINT ck_pdd_item_logistics_package_uom
        CHECK (
            package_uom IS NULL
            OR nullif(btrim(package_uom), '') IS NOT NULL
        ),
    ADD CONSTRAINT ck_pdd_item_logistics_gtin
        CHECK (
            (
                unit_gtin IS NULL
                OR (
                    unit_gtin ~ '^[0-9]+$'
                    AND length(unit_gtin) IN (8, 12, 13, 14)
                )
            )
            AND (
                package_gtin IS NULL
                OR (
                    package_gtin ~ '^[0-9]+$'
                    AND length(package_gtin) IN (8, 12, 13, 14)
                )
            )
        ),
    ADD CONSTRAINT ck_pdd_item_logistics_weight_values
        CHECK (
            (unit_net_weight_kg IS NULL OR unit_net_weight_kg > 0)
            AND (unit_gross_weight_kg IS NULL OR unit_gross_weight_kg > 0)
            AND (package_gross_weight_kg IS NULL OR package_gross_weight_kg > 0)
        ),
    ADD CONSTRAINT ck_pdd_item_logistics_weight_relation
        CHECK (
            unit_net_weight_kg IS NULL
            OR unit_gross_weight_kg IS NULL
            OR unit_gross_weight_kg >= unit_net_weight_kg
        ),
    ADD CONSTRAINT ck_pdd_item_logistics_weight_basis
        CHECK (
            weight_basis IS NULL
            OR weight_basis IN (
                'GROSS_UNIT',
                'GROSS_PACKAGE_DERIVED',
                'NET_UNIT_FALLBACK',
                'ESTIMATED'
            )
        ),
    ADD CONSTRAINT ck_pdd_item_logistics_package_dimensions
        CHECK (
            (
                package_length_cm IS NULL
                AND package_width_cm IS NULL
                AND package_height_cm IS NULL
            )
            OR (
                package_length_cm > 0
                AND package_width_cm > 0
                AND package_height_cm > 0
            )
        ),
    ADD CONSTRAINT ck_pdd_item_logistics_volume_values
        CHECK (package_volume_m3 IS NULL OR package_volume_m3 > 0),
    ADD CONSTRAINT ck_pdd_item_logistics_volume_method
        CHECK (
            volume_method IS NULL
            OR volume_method IN (
                'MEASURED_DIMENSIONS',
                'SOURCE_DIMENSIONS',
                'SOURCE_REPORTED',
                'SUPPLIER_REPORTED',
                'ESTIMATED'
            )
        ),
    ADD CONSTRAINT ck_pdd_item_logistics_pallet_values
        CHECK (
            (packages_per_layer IS NULL OR packages_per_layer > 0)
            AND (layers_per_pallet IS NULL OR layers_per_pallet > 0)
            AND (units_per_pallet IS NULL OR units_per_pallet > 0)
            AND (pallet_length_cm IS NULL OR pallet_length_cm > 0)
            AND (pallet_width_cm IS NULL OR pallet_width_cm > 0)
            AND (
                loaded_pallet_height_cm IS NULL
                OR loaded_pallet_height_cm > 0
            )
            AND (
                pallet_gross_weight_kg IS NULL
                OR pallet_gross_weight_kg > 0
            )
            AND (
                pallet_type IS NULL
                OR pallet_type ~ '^[A-Z][A-Z0-9_]*$'
            )
        ),
    ADD CONSTRAINT ck_pdd_item_logistics_pallet_consistency
        CHECK (
            packages_per_layer IS NULL
            OR layers_per_pallet IS NULL
            OR packages_per_pallet IS NULL
            OR packages_per_pallet =
               packages_per_layer::numeric * layers_per_pallet::numeric
        ),
    ADD CONSTRAINT ck_pdd_item_logistics_units_pallet_consistency
        CHECK (
            units_per_package IS NULL
            OR packages_per_pallet IS NULL
            OR units_per_pallet IS NULL
            OR units_per_pallet = units_per_package * packages_per_pallet
        ),
    ADD CONSTRAINT ck_pdd_item_logistics_stack
        CHECK (
            (max_stack_levels IS NULL OR max_stack_levels > 0)
            AND (
                stackable IS DISTINCT FROM false
                OR max_stack_levels IS NULL
                OR max_stack_levels = 1
            )
        ),
    ADD CONSTRAINT ck_pdd_item_logistics_temperature
        CHECK (
            temperature_min_c IS NULL
            OR temperature_max_c IS NULL
            OR temperature_min_c <= temperature_max_c
        ),
    ADD CONSTRAINT ck_pdd_item_logistics_handling_codes
        CHECK (
            (
                temperature_zone IS NULL
                OR temperature_zone ~ '^[A-Z][A-Z0-9_]*$'
            )
            AND (
                orientation_code IS NULL
                OR orientation_code ~ '^[A-Z][A-Z0-9_]*$'
            )
        ),
    ADD CONSTRAINT ck_pdd_item_logistics_axis_quality
        CHECK (
            packaging_quality_status IN (
                'VERIFIED', 'SOURCE', 'ESTIMATED', 'MISSING', 'INVALID'
            )
            AND weight_quality_status IN (
                'VERIFIED', 'SOURCE', 'ESTIMATED', 'MISSING', 'INVALID'
            )
            AND volume_quality_status IN (
                'VERIFIED', 'SOURCE', 'ESTIMATED', 'MISSING', 'INVALID'
            )
            AND pallet_quality_status IN (
                'VERIFIED', 'SOURCE', 'ESTIMATED', 'MISSING', 'INVALID'
            )
        ),
    ADD CONSTRAINT ck_pdd_item_logistics_quality_issues
        CHECK (array_position(quality_issue_codes, NULL) IS NULL),
    ADD CONSTRAINT ck_pdd_item_logistics_verification
        CHECK (
            (verified_at IS NULL AND verified_by IS NULL)
            OR (
                verified_at IS NOT NULL
                AND nullif(btrim(verified_by), '') IS NOT NULL
            )
        ),
    ADD CONSTRAINT ck_pdd_item_logistics_attributes
        CHECK (jsonb_typeof(attributes) = 'object');

CREATE INDEX IF NOT EXISTS ix_pdd_item_logistics_quality
    ON stock_management.pdd_item_logistics_snapshot (
        calculation_run_id,
        packaging_quality_status,
        weight_quality_status,
        volume_quality_status,
        pallet_quality_status
    );

CREATE INDEX IF NOT EXISTS ix_pdd_item_logistics_source
    ON stock_management.pdd_item_logistics_snapshot (source_logistics_id)
    WHERE source_logistics_id IS NOT NULL;

COMMENT ON TABLE stock_management.pdd_item_logistics_snapshot IS
'Snapshot inmutable de la configuracion logistica utilizada por una corrida PDD.';

COMMENT ON COLUMN stock_management.pdd_item_logistics_snapshot.source_logistics_id IS
'Referencia logica a diarco_data.src.base_articulos_logistica.articulo_logistica_id; no es FK entre bases.';
COMMENT ON COLUMN stock_management.pdd_item_logistics_snapshot.supplier_code IS
'Proveedor de la configuracion logistica; NULL para configuracion general.';
COMMENT ON COLUMN stock_management.pdd_item_logistics_snapshot.logistics_configuration_code IS
'Codigo funcional de la presentacion o configuracion logistica.';
COMMENT ON COLUMN stock_management.pdd_item_logistics_snapshot.source_valid_from IS
'Inicio de vigencia en la fuente canonica.';
COMMENT ON COLUMN stock_management.pdd_item_logistics_snapshot.sells_by_weight IS
'Indica administracion o venta por peso.';
COMMENT ON COLUMN stock_management.pdd_item_logistics_snapshot.package_uom IS
'Unidad logistica del bulto: BOX, PACK, BAG, DISPLAY u otra.';
COMMENT ON COLUMN stock_management.pdd_item_logistics_snapshot.unit_gtin IS
'GTIN/EAN de la unidad base.';
COMMENT ON COLUMN stock_management.pdd_item_logistics_snapshot.package_gtin IS
'GTIN/DUN del bulto.';
COMMENT ON COLUMN stock_management.pdd_item_logistics_snapshot.source_reference IS
'Referencia de la medicion, archivo o sistema que origino la configuracion.';

COMMENT ON COLUMN stock_management.pdd_item_logistics_snapshot.unit_weight_kg IS
'Peso efectivo por unidad base utilizado por los calculos PDD.';
COMMENT ON COLUMN stock_management.pdd_item_logistics_snapshot.unit_net_weight_kg IS
'Peso neto de una unidad base, en kilogramos.';
COMMENT ON COLUMN stock_management.pdd_item_logistics_snapshot.unit_gross_weight_kg IS
'Peso bruto de una unidad base, en kilogramos.';
COMMENT ON COLUMN stock_management.pdd_item_logistics_snapshot.package_gross_weight_kg IS
'Peso bruto del bulto completo, en kilogramos.';
COMMENT ON COLUMN stock_management.pdd_item_logistics_snapshot.weight_basis IS
'Regla de seleccion del peso efectivo unitario.';

COMMENT ON COLUMN stock_management.pdd_item_logistics_snapshot.package_length_cm IS
'Largo exterior del bulto, en centimetros.';
COMMENT ON COLUMN stock_management.pdd_item_logistics_snapshot.package_width_cm IS
'Ancho exterior del bulto, en centimetros.';
COMMENT ON COLUMN stock_management.pdd_item_logistics_snapshot.package_height_cm IS
'Alto exterior del bulto, en centimetros.';
COMMENT ON COLUMN stock_management.pdd_item_logistics_snapshot.package_volume_m3 IS
'Volumen exterior del bulto, en metros cubicos.';
COMMENT ON COLUMN stock_management.pdd_item_logistics_snapshot.unit_volume_m3 IS
'Volumen efectivo por unidad base utilizado por los calculos PDD.';
COMMENT ON COLUMN stock_management.pdd_item_logistics_snapshot.volume_method IS
'Procedencia o metodo utilizado para obtener el volumen.';

COMMENT ON COLUMN stock_management.pdd_item_logistics_snapshot.packages_per_layer IS
'Cantidad de bultos por camada del pallet.';
COMMENT ON COLUMN stock_management.pdd_item_logistics_snapshot.layers_per_pallet IS
'Cantidad de camadas del pallet completo.';
COMMENT ON COLUMN stock_management.pdd_item_logistics_snapshot.units_per_pallet IS
'Cantidad de unidades base por pallet completo.';
COMMENT ON COLUMN stock_management.pdd_item_logistics_snapshot.pallet_type IS
'Tipo normalizado de pallet.';
COMMENT ON COLUMN stock_management.pdd_item_logistics_snapshot.pallet_length_cm IS
'Largo del pallet, en centimetros.';
COMMENT ON COLUMN stock_management.pdd_item_logistics_snapshot.pallet_width_cm IS
'Ancho del pallet, en centimetros.';
COMMENT ON COLUMN stock_management.pdd_item_logistics_snapshot.loaded_pallet_height_cm IS
'Altura total del pallet cargado, en centimetros.';
COMMENT ON COLUMN stock_management.pdd_item_logistics_snapshot.pallet_gross_weight_kg IS
'Peso bruto del pallet completo, en kilogramos.';

COMMENT ON COLUMN stock_management.pdd_item_logistics_snapshot.stackable IS
'Indica si el bulto admite apilamiento.';
COMMENT ON COLUMN stock_management.pdd_item_logistics_snapshot.max_stack_levels IS
'Maximo de niveles de apilamiento permitidos.';
COMMENT ON COLUMN stock_management.pdd_item_logistics_snapshot.fragile IS
'Indica manipulacion como mercaderia fragil.';
COMMENT ON COLUMN stock_management.pdd_item_logistics_snapshot.hazardous IS
'Indica mercaderia peligrosa o regulada.';
COMMENT ON COLUMN stock_management.pdd_item_logistics_snapshot.temperature_zone IS
'Zona termica normalizada.';
COMMENT ON COLUMN stock_management.pdd_item_logistics_snapshot.temperature_min_c IS
'Temperatura minima permitida, en grados Celsius.';
COMMENT ON COLUMN stock_management.pdd_item_logistics_snapshot.temperature_max_c IS
'Temperatura maxima permitida, en grados Celsius.';
COMMENT ON COLUMN stock_management.pdd_item_logistics_snapshot.orientation_code IS
'Restriccion normalizada de orientacion del bulto.';

COMMENT ON COLUMN stock_management.pdd_item_logistics_snapshot.packaging_quality_status IS
'Calidad del factor de compra y la presentacion.';
COMMENT ON COLUMN stock_management.pdd_item_logistics_snapshot.weight_quality_status IS
'Calidad de los datos de peso.';
COMMENT ON COLUMN stock_management.pdd_item_logistics_snapshot.volume_quality_status IS
'Calidad de dimensiones y volumen.';
COMMENT ON COLUMN stock_management.pdd_item_logistics_snapshot.pallet_quality_status IS
'Calidad de la configuracion de pallet.';
COMMENT ON COLUMN stock_management.pdd_item_logistics_snapshot.quality_issue_codes IS
'Codigos estables de incidencias logisticas detectadas.';
COMMENT ON COLUMN stock_management.pdd_item_logistics_snapshot.verified_at IS
'Fecha de la ultima verificacion humana o certificada.';
COMMENT ON COLUMN stock_management.pdd_item_logistics_snapshot.verified_by IS
'Usuario, proveedor o proceso que verifico la configuracion.';
COMMENT ON COLUMN stock_management.pdd_item_logistics_snapshot.attributes IS
'Extension controlada para atributos no incorporados aun al contrato estructurado.';

-- Control final de la propia migracion.
DO $postconditions$
DECLARE
    missing_columns text;
BEGIN
    SELECT string_agg(required.column_name, ', ' ORDER BY required.column_name)
    INTO missing_columns
    FROM (
        VALUES
            ('source_logistics_id'),
            ('supplier_code'),
            ('logistics_configuration_code'),
            ('source_valid_from'),
            ('sells_by_weight'),
            ('package_uom'),
            ('unit_gtin'),
            ('package_gtin'),
            ('source_reference'),
            ('unit_net_weight_kg'),
            ('unit_gross_weight_kg'),
            ('package_gross_weight_kg'),
            ('weight_basis'),
            ('package_length_cm'),
            ('package_width_cm'),
            ('package_height_cm'),
            ('package_volume_m3'),
            ('volume_method'),
            ('packages_per_layer'),
            ('layers_per_pallet'),
            ('units_per_pallet'),
            ('pallet_type'),
            ('pallet_length_cm'),
            ('pallet_width_cm'),
            ('loaded_pallet_height_cm'),
            ('pallet_gross_weight_kg'),
            ('stackable'),
            ('max_stack_levels'),
            ('fragile'),
            ('hazardous'),
            ('temperature_zone'),
            ('temperature_min_c'),
            ('temperature_max_c'),
            ('orientation_code'),
            ('packaging_quality_status'),
            ('weight_quality_status'),
            ('volume_quality_status'),
            ('pallet_quality_status'),
            ('quality_issue_codes'),
            ('verified_at'),
            ('verified_by'),
            ('attributes')
    ) AS required(column_name)
    WHERE NOT EXISTS (
        SELECT 1
        FROM information_schema.columns AS actual
        WHERE actual.table_schema = 'stock_management'
          AND actual.table_name = 'pdd_item_logistics_snapshot'
          AND actual.column_name = required.column_name
    );

    IF missing_columns IS NOT NULL THEN
        RAISE EXCEPTION
            'Faltan columnas de item logistics v2.9: %', missing_columns;
    END IF;

    IF EXISTS (
        SELECT 1
        FROM stock_management.pdd_item_logistics_snapshot
        WHERE packaging_quality_status IS NULL
           OR weight_quality_status IS NULL
           OR volume_quality_status IS NULL
           OR pallet_quality_status IS NULL
           OR quality_issue_codes IS NULL
           OR attributes IS NULL
    ) THEN
        RAISE EXCEPTION
            'La ampliacion dejo campos de calidad obligatorios en NULL';
    END IF;
END
$postconditions$;
