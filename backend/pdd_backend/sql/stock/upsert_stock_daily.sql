WITH cd_articles AS (
    SELECT DISTINCT bpv.c_articulo AS codigo_articulo
    FROM src.base_productos_vigentes AS bpv
    WHERE bpv.c_sucu_empr = :origin_cd
      AND bpv.active_for_purchase = 1
),
distribution_pairs AS (
    SELECT DISTINCT
        bpv.c_articulo AS codigo_articulo,
        bpv.c_sucu_empr AS sucursal
    FROM src.base_productos_vigentes AS bpv
    INNER JOIN cd_articles AS a
        ON a.codigo_articulo = bpv.c_articulo
    WHERE bpv.cod_cd = '41CD'
      AND bpv.abastecimiento = 0
      AND bpv.habilitado = 1
      AND bpv.active_for_sale = 1
      AND bpv.active_on_mix = 1
      AND bpv.c_sucu_empr <> :origin_cd
),
stock_scope AS (
    SELECT codigo_articulo, sucursal
    FROM distribution_pairs
    UNION
    SELECT codigo_articulo, :origin_cd AS sucursal
    FROM cd_articles
),
expanded AS (
    SELECT
        make_date(s.c_anio::integer, s.c_mes::integer, d.day_no) AS stock_date,
        s.c_articulo::integer AS codigo_articulo,
        s.c_sucu_empr::integer AS sucursal,
        d.qty::numeric(18,6) AS stock_quantity,
        s.c_anio::smallint AS source_year,
        s.c_mes::smallint AS source_month,
        d.day_no::smallint AS source_day,
        s.fecha_proceso AS source_processed_at,
        s.procesado_ok AS source_processed_ok,
        s.fuente_origen AS source_origin
    FROM src.t710_estadis_stock AS s
    INNER JOIN stock_scope AS sc
        ON sc.codigo_articulo = s.c_articulo
       AND sc.sucursal = s.c_sucu_empr
    CROSS JOIN LATERAL (VALUES
        (1,s.q_dia1),(2,s.q_dia2),(3,s.q_dia3),(4,s.q_dia4),(5,s.q_dia5),
        (6,s.q_dia6),(7,s.q_dia7),(8,s.q_dia8),(9,s.q_dia9),(10,s.q_dia10),
        (11,s.q_dia11),(12,s.q_dia12),(13,s.q_dia13),(14,s.q_dia14),(15,s.q_dia15),
        (16,s.q_dia16),(17,s.q_dia17),(18,s.q_dia18),(19,s.q_dia19),(20,s.q_dia20),
        (21,s.q_dia21),(22,s.q_dia22),(23,s.q_dia23),(24,s.q_dia24),(25,s.q_dia25),
        (26,s.q_dia26),(27,s.q_dia27),(28,s.q_dia28),(29,s.q_dia29),(30,s.q_dia30),
        (31,s.q_dia31)
    ) AS d(day_no, qty)
    WHERE make_date(s.c_anio::integer, s.c_mes::integer, 1)
              <= date_trunc('month', CAST(:end_date AS date))::date
      AND make_date(s.c_anio::integer, s.c_mes::integer, 1)
              >= date_trunc('month', CAST(:start_date AS date))::date
      AND d.day_no <= extract(
          day FROM (
              date_trunc('month', make_date(s.c_anio::integer, s.c_mes::integer, 1))
              + interval '1 month - 1 day'
          )
      )
),
closed_days AS (
    SELECT
        e.*,
        CASE
            WHEN e.source_processed_at IS NOT NULL THEN 'PROCESS_DATE_MINUS_1'
            ELSE 'EXPLICIT_CUTOFF'
        END::varchar(30) AS closed_day_rule
    FROM expanded AS e
    WHERE e.stock_date BETWEEN CAST(:start_date AS date) AND CAST(:end_date AS date)
      AND (
          e.source_processed_at IS NULL
          OR e.stock_date <= e.source_processed_at::date - 1
      )
),
prepared AS (
    SELECT
        c.*,
        CASE
            WHEN c.stock_quantity > 0 THEN 'POSITIVE'
            WHEN c.stock_quantity = 0 THEN 'ZERO'
            ELSE 'NEGATIVE'
        END::varchar(10) AS stock_sign_status,
        (c.stock_quantity > 0) AS is_serviceable_by_stock,
        encode(
            sha256(
                convert_to(
                    concat_ws('|',
                        c.stock_date::text,
                        c.codigo_articulo::text,
                        c.sucursal::text,
                        c.stock_quantity::text,
                        coalesce(c.source_processed_at::text, ''),
                        coalesce(c.source_processed_ok::text, ''),
                        coalesce(c.source_origin, '')
                    ),
                    'UTF8'
                )
            ),
            'hex'
        )::char(64) AS source_row_hash
    FROM closed_days AS c
)
INSERT INTO datamart.dm_pdd_stock_diario (
    stock_date,
    codigo_articulo,
    sucursal,
    stock_quantity,
    stock_sign_status,
    is_serviceable_by_stock,
    source_year,
    source_month,
    source_day,
    source_processed_at,
    source_processed_ok,
    source_origin,
    closed_day_rule,
    source_row_hash,
    normalized_at
)
SELECT
    stock_date,
    codigo_articulo,
    sucursal,
    stock_quantity,
    stock_sign_status,
    is_serviceable_by_stock,
    source_year,
    source_month,
    source_day,
    source_processed_at,
    source_processed_ok,
    source_origin,
    closed_day_rule,
    source_row_hash,
    clock_timestamp()
FROM prepared
ON CONFLICT (stock_date, codigo_articulo, sucursal) DO UPDATE
SET stock_quantity = EXCLUDED.stock_quantity,
    stock_sign_status = EXCLUDED.stock_sign_status,
    is_serviceable_by_stock = EXCLUDED.is_serviceable_by_stock,
    source_year = EXCLUDED.source_year,
    source_month = EXCLUDED.source_month,
    source_day = EXCLUDED.source_day,
    source_processed_at = EXCLUDED.source_processed_at,
    source_processed_ok = EXCLUDED.source_processed_ok,
    source_origin = EXCLUDED.source_origin,
    closed_day_rule = EXCLUDED.closed_day_rule,
    source_row_hash = EXCLUDED.source_row_hash,
    normalized_at = clock_timestamp()
WHERE dm_pdd_stock_diario.source_row_hash IS DISTINCT FROM EXCLUDED.source_row_hash;

