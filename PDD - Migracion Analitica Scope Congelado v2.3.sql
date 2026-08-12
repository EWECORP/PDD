\set ON_ERROR_STOP on

BEGIN;

DO $guard$
BEGIN
    IF current_database() <> 'diarco_data' THEN
        RAISE EXCEPTION
            'Migracion PDD scope congelado: base incorrecta (%). Se esperaba diarco_data.',
            current_database();
    END IF;
END
$guard$;

CREATE TABLE datamart.dm_pdd_scope_version (
    scope_version_uuid uuid PRIMARY KEY,
    scope_code varchar(80) NOT NULL,
    version_no integer NOT NULL CHECK (version_no > 0),
    supersedes_scope_version_uuid uuid
        REFERENCES datamart.dm_pdd_scope_version(scope_version_uuid) ON DELETE RESTRICT,
    origin_cd integer NOT NULL CHECK (origin_cd = 41),
    business_date date NOT NULL,
    status varchar(20) NOT NULL CHECK (
        status IN ('DRAFT', 'APPROVED', 'SUPERSEDED', 'REJECTED')
    ),
    source_database varchar(80) NOT NULL DEFAULT 'diarco_data',
    source_relation varchar(200) NOT NULL DEFAULT 'src.base_productos_vigentes',
    source_as_of_ts timestamp without time zone NOT NULL,
    article_filter jsonb NOT NULL,
    pair_filter jsonb NOT NULL,
    article_count integer NOT NULL CHECK (article_count >= 0),
    routed_article_count integer NOT NULL CHECK (routed_article_count >= 0),
    pair_count integer NOT NULL CHECK (pair_count >= 0),
    destination_count integer NOT NULL CHECK (destination_count >= 0),
    article_checksum char(64) NOT NULL,
    pair_checksum char(64) NOT NULL,
    scope_checksum char(64) NOT NULL,
    captured_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    captured_by varchar(100) NOT NULL,
    detail jsonb NOT NULL DEFAULT '{}'::jsonb,
    UNIQUE (scope_code, version_no),
    UNIQUE (origin_cd, scope_checksum),
    CHECK (supersedes_scope_version_uuid IS NULL
        OR supersedes_scope_version_uuid <> scope_version_uuid)
);

CREATE TABLE datamart.dm_pdd_scope_article (
    scope_version_uuid uuid NOT NULL
        REFERENCES datamart.dm_pdd_scope_version(scope_version_uuid) ON DELETE RESTRICT,
    codigo_articulo integer NOT NULL,
    c_proveedor_primario integer,
    cd_active_for_purchase boolean NOT NULL,
    cd_habilitado boolean,
    cd_active_for_sale boolean,
    cd_active_on_mix boolean,
    source_extracted_at timestamp without time zone,
    source_row_hash char(64) NOT NULL,
    captured_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    PRIMARY KEY (scope_version_uuid, codigo_articulo),
    CHECK (cd_active_for_purchase)
);

CREATE INDEX ix_dm_pdd_scope_article_lookup
    ON datamart.dm_pdd_scope_article (codigo_articulo, scope_version_uuid);

CREATE TABLE datamart.dm_pdd_scope_pair (
    scope_version_uuid uuid NOT NULL,
    origin_cd integer NOT NULL,
    destination_branch integer NOT NULL,
    codigo_articulo integer NOT NULL,
    c_proveedor_primario integer,
    route_code varchar(30) NOT NULL,
    supply_mode integer NOT NULL,
    branch_habilitado boolean NOT NULL,
    branch_active_for_sale boolean NOT NULL,
    branch_active_on_mix boolean NOT NULL,
    source_extracted_at timestamp without time zone,
    source_row_hash char(64) NOT NULL,
    captured_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    PRIMARY KEY (scope_version_uuid, destination_branch, codigo_articulo),
    FOREIGN KEY (scope_version_uuid, codigo_articulo)
        REFERENCES datamart.dm_pdd_scope_article
            (scope_version_uuid, codigo_articulo) ON DELETE RESTRICT,
    CHECK (destination_branch <> origin_cd),
    CHECK (
        origin_cd = 41
        AND route_code = '41CD'
        AND supply_mode = 0
        AND branch_habilitado
        AND branch_active_for_sale
        AND branch_active_on_mix
    )
);

CREATE INDEX ix_dm_pdd_scope_pair_lookup
    ON datamart.dm_pdd_scope_pair
    (scope_version_uuid, destination_branch, codigo_articulo);

COMMENT ON TABLE datamart.dm_pdd_scope_version IS
'Cabecera sellada de un universo PDD reproducible capturado en diarco_data.';

COMMENT ON TABLE datamart.dm_pdd_scope_article IS
'Membresia inmutable de articulos habilitados para compra en el CD de una version de scope.';

COMMENT ON TABLE datamart.dm_pdd_scope_pair IS
'Membresia inmutable articulo-sucursal distribuida desde el CD para una version de scope.';

COMMIT;
