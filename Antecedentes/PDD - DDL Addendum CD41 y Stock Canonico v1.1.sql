-- PDD / Addendum CD 41 y stock diario canónico - v1.1 - 2026-08-02
-- BORRADOR. Aplicar después de "PDD - DDL Demanda Basal PostgreSQL v1.0.sql".

BEGIN;

CREATE TABLE pdd.distribution_scope_version (
    scope_version_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    origin_cd integer NOT NULL,
    business_date date NOT NULL,
    status varchar(20) NOT NULL CHECK (status IN ('DRAFT', 'APPROVED', 'SUPERSEDED', 'REJECTED')),
    is_current boolean NOT NULL DEFAULT false,
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
    CONSTRAINT uq_distribution_scope_version UNIQUE (origin_cd, business_date, checksum),
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
    PRIMARY KEY (scope_version_id, codigo_articulo)
);

CREATE INDEX ix_distribution_scope_article_lookup
    ON pdd.distribution_scope_article (codigo_articulo, scope_version_id DESC);

CREATE TABLE pdd.distribution_scope_pair (
    scope_version_id bigint NOT NULL,
    origin_cd integer NOT NULL,
    destination_branch integer NOT NULL,
    codigo_articulo integer NOT NULL,
    c_proveedor_primario integer,
    route_code varchar(30),
    supply_mode integer,
    branch_habilitado boolean NOT NULL,
    branch_active_for_sale boolean NOT NULL,
    branch_active_on_mix boolean NOT NULL,
    source_row_hash char(64) NOT NULL,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    PRIMARY KEY (scope_version_id, destination_branch, codigo_articulo),
    FOREIGN KEY (scope_version_id, codigo_articulo)
        REFERENCES pdd.distribution_scope_article (scope_version_id, codigo_articulo)
        ON DELETE RESTRICT,
    CONSTRAINT ck_distribution_scope_distinct_branch CHECK (destination_branch <> origin_cd)
);

CREATE INDEX ix_distribution_scope_pair_operational
    ON pdd.distribution_scope_pair
    (scope_version_id, destination_branch, codigo_articulo, c_proveedor_primario);

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
    source_processed_at timestamp,
    source_processed_ok boolean,
    source_origin text,
    source_row_hash char(64) NOT NULL,
    normalized_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    PRIMARY KEY (stock_date, codigo_articulo, sucursal),
    CONSTRAINT ck_stock_daily_sign CHECK (
        (stock_quantity > 0 AND stock_sign_status = 'POSITIVE' AND is_serviceable_by_stock)
        OR (stock_quantity = 0 AND stock_sign_status = 'ZERO' AND NOT is_serviceable_by_stock)
        OR (stock_quantity < 0 AND stock_sign_status = 'NEGATIVE' AND NOT is_serviceable_by_stock)
    ),
    CONSTRAINT ck_stock_daily_source_date CHECK (
        extract(year FROM stock_date)::integer = source_year
        AND extract(month FROM stock_date)::integer = source_month
        AND extract(day FROM stock_date)::integer = source_day
    ),
    CONSTRAINT ck_stock_daily_closed CHECK (
        source_processed_at IS NULL OR stock_date <= source_processed_at::date - 1
    )
) PARTITION BY RANGE (stock_date);

-- Ejemplo:
-- CREATE TABLE datamart.dm_pdd_stock_diario_2026_08
-- PARTITION OF datamart.dm_pdd_stock_diario
-- FOR VALUES FROM ('2026-08-01') TO ('2026-09-01');

CREATE INDEX ix_dm_pdd_stock_pair_date
    ON datamart.dm_pdd_stock_diario (codigo_articulo, sucursal, stock_date DESC);
CREATE INDEX ix_dm_pdd_stock_serviceable
    ON datamart.dm_pdd_stock_diario (stock_date, codigo_articulo, sucursal)
    WHERE is_serviceable_by_stock;
CREATE INDEX ix_dm_pdd_stock_date_brin
    ON datamart.dm_pdd_stock_diario USING brin (stock_date);

ALTER TABLE pdd.calculation_run
    ADD COLUMN scope_version_id bigint
        REFERENCES pdd.distribution_scope_version(scope_version_id);

ALTER TABLE pdd.calculation_run
    ADD CONSTRAINT ck_calculation_scope_required CHECK (
        run_type NOT IN ('PDVB', 'DAILY_DECAS') OR scope_version_id IS NOT NULL
    );

ALTER TABLE datamart.dm_pdd_venta_diaria
    ADD COLUMN stock_quantity_snapshot numeric(18,6),
    ADD COLUMN stock_source_hash char(64);

ALTER TABLE datamart.dm_pdd_venta_diaria
    ADD CONSTRAINT ck_daily_stock_lineage CHECK (
        (availability_status = 'UNKNOWN' AND stock_source_hash IS NULL)
        OR availability_status = 'INFERRED_FROM_SALE'
        OR stock_source_hash IS NOT NULL
    );

ALTER TABLE pdd.pdvb_estimate
    ADD COLUMN origin_cd integer NOT NULL DEFAULT 41,
    ADD COLUMN scope_version_id bigint
        REFERENCES pdd.distribution_scope_version(scope_version_id);

ALTER TABLE pdd.pdvb_estimate
    ADD CONSTRAINT ck_pdvb_scope_required CHECK (scope_version_id IS NOT NULL);

CREATE INDEX ix_pdvb_estimate_scope
    ON pdd.pdvb_estimate (scope_version_id, origin_cd, business_date DESC);

ALTER TABLE pdd.pdvb_current
    ADD COLUMN origin_cd integer NOT NULL DEFAULT 41,
    ADD COLUMN scope_version_id bigint
        REFERENCES pdd.distribution_scope_version(scope_version_id);

ALTER TABLE pdd.pdvb_current
    ADD CONSTRAINT ck_pdvb_current_scope_required CHECK (scope_version_id IS NOT NULL);

CREATE INDEX ix_pdvb_current_scope
    ON pdd.pdvb_current (scope_version_id, origin_cd, sucursal, codigo_articulo);

COMMENT ON TABLE pdd.distribution_scope_version IS
'Versión inmutable del universo distribuible desde un CD; los conteos nunca se hardcodean.';
COMMENT ON TABLE pdd.distribution_scope_pair IS
'Pares sucursal-articulo habilitados para recibir distribución desde el CD de la versión.';
COMMENT ON TABLE datamart.dm_pdd_stock_diario IS
'Stock LEGACY t710 normalizado a fecha-articulo-sucursal; ausencia de fila significa desconocido, no cero.';

-- Patrón de normalización (adaptar a scope/rango y ejecutar como upsert):
-- SELECT
--   make_date(s.c_anio::int, s.c_mes::int, d.day_no) AS stock_date,
--   s.c_articulo::int,
--   s.c_sucu_empr::int,
--   d.qty AS stock_quantity
-- FROM src.t710_estadis_stock s
-- CROSS JOIN LATERAL (VALUES
--   (1,s.q_dia1),(2,s.q_dia2),(3,s.q_dia3),(4,s.q_dia4),(5,s.q_dia5),
--   (6,s.q_dia6),(7,s.q_dia7),(8,s.q_dia8),(9,s.q_dia9),(10,s.q_dia10),
--   (11,s.q_dia11),(12,s.q_dia12),(13,s.q_dia13),(14,s.q_dia14),(15,s.q_dia15),
--   (16,s.q_dia16),(17,s.q_dia17),(18,s.q_dia18),(19,s.q_dia19),(20,s.q_dia20),
--   (21,s.q_dia21),(22,s.q_dia22),(23,s.q_dia23),(24,s.q_dia24),(25,s.q_dia25),
--   (26,s.q_dia26),(27,s.q_dia27),(28,s.q_dia28),(29,s.q_dia29),(30,s.q_dia30),
--   (31,s.q_dia31)
-- ) AS d(day_no, qty)
-- WHERE d.day_no <= extract(day FROM (
--     date_trunc('month', make_date(s.c_anio::int,s.c_mes::int,1))
--     + interval '1 month - 1 day'))
--   AND make_date(s.c_anio::int,s.c_mes::int,d.day_no) <= :cutoff_date
--   AND (s.fecha_proceso IS NULL OR
--        make_date(s.c_anio::int,s.c_mes::int,d.day_no) <= s.fecha_proceso::date - 1);

COMMIT;
