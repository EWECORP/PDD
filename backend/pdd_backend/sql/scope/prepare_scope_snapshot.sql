CREATE TEMP TABLE pdd_scope_excluded_categories ON COMMIT DROP AS
WITH configured AS (
    SELECT
        rule ->> 'rule_code' AS rule_code,
        (rule ->> 'c_rubro')::integer AS c_rubro,
        (rule ->> 'c_subrubro_1')::integer AS c_subrubro_1,
        rule ->> 'reason' AS reason
    FROM jsonb_array_elements(
        CAST(:exclusion_policy_json AS jsonb) -> 'rules'
    ) AS rules(rule)
)
SELECT
    configured.rule_code,
    configured.c_rubro,
    configured.c_subrubro_1,
    category.rubro_name,
    category.subrubro_1_name,
    configured.reason
FROM configured
LEFT JOIN LATERAL (
    SELECT
        upper(trim(source.n_rubro_normalizado)) AS rubro_name,
        upper(trim(source.n_subrubro_1_normalizado)) AS subrubro_1_name
    FROM src.m_1_categorias AS source
    WHERE trim(source.c_rubro::text)::integer = configured.c_rubro
      AND trim(source.c_subrubro_1::text)::integer = configured.c_subrubro_1
      AND source.n_rubro_normalizado IS NOT NULL
      AND source.n_subrubro_1_normalizado IS NOT NULL
    ORDER BY source.f_dato DESC NULLS LAST, source.f_proc DESC NULLS LAST
    LIMIT 1
) AS category ON true;

ALTER TABLE pdd_scope_excluded_categories
    ADD PRIMARY KEY (c_rubro, c_subrubro_1);

CREATE TEMP TABLE pdd_scope_source_excluded_branches ON COMMIT DROP AS
SELECT DISTINCT
    excluded.c_sucu_empr::integer AS destination_branch
FROM src.sucursales_excluidas AS excluded
WHERE excluded.c_sucu_empr IS NOT NULL;

ALTER TABLE pdd_scope_source_excluded_branches
    ADD PRIMARY KEY (destination_branch);

DO $validate_categories$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM pdd_scope_excluded_categories AS excluded
        WHERE excluded.rubro_name IS NULL
           OR excluded.subrubro_1_name IS NULL
    ) THEN
        RAISE EXCEPTION
            'La politica PDD contiene codigos inexistentes en src.m_1_categorias';
    END IF;
END
$validate_categories$;

CREATE TEMP TABLE pdd_scope_articles_snapshot ON COMMIT DROP AS
SELECT DISTINCT ON (bpv.c_articulo)
    bpv.c_articulo::integer AS codigo_articulo,
    bpv.c_proveedor_primario::integer AS c_proveedor_primario,
    (bpv.active_for_purchase = 1) AS cd_active_for_purchase,
    (bpv.habilitado = 1) AS cd_habilitado,
    (bpv.active_for_sale = 1) AS cd_active_for_sale,
    (bpv.active_on_mix = 1) AS cd_active_on_mix,
    bpv.fecha_extraccion AS source_extracted_at,
    encode(
        sha256(
            convert_to(
                concat_ws('|',
                    bpv.c_articulo::text,
                    coalesce(bpv.c_proveedor_primario::text, ''),
                    bpv.active_for_purchase::text,
                    coalesce(bpv.habilitado::text, ''),
                    coalesce(bpv.active_for_sale::text, ''),
                    coalesce(bpv.active_on_mix::text, '')
                ),
                'UTF8'
            )
        ),
        'hex'
    )::char(64) AS source_row_hash
FROM src.base_productos_vigentes AS bpv
WHERE bpv.c_sucu_empr = :origin_cd
  AND bpv.active_for_purchase = 1
  AND NOT EXISTS (
      SELECT 1
      FROM src.m_3_articulos AS art
      INNER JOIN pdd_scope_excluded_categories AS excluded
          ON excluded.c_rubro = art.c_rubro::integer
         AND excluded.c_subrubro_1 = art.c_subrubro_1::integer
      WHERE art.c_articulo::integer = bpv.c_articulo::integer
  )
ORDER BY bpv.c_articulo, bpv.fecha_extraccion DESC NULLS LAST;

ALTER TABLE pdd_scope_articles_snapshot
    ADD PRIMARY KEY (codigo_articulo);

CREATE TEMP TABLE pdd_scope_excluded_branch_pairs ON COMMIT DROP AS
SELECT DISTINCT ON (bpv.c_sucu_empr, bpv.c_articulo)
    bpv.c_sucu_empr::integer AS destination_branch,
    bpv.c_articulo::integer AS codigo_articulo
FROM src.base_productos_vigentes AS bpv
INNER JOIN pdd_scope_articles_snapshot AS article
    ON article.codigo_articulo = bpv.c_articulo::integer
INNER JOIN pdd_scope_source_excluded_branches AS excluded
    ON excluded.destination_branch = bpv.c_sucu_empr::integer
WHERE bpv.cod_cd = '41CD'
  AND bpv.abastecimiento = 0
  AND bpv.habilitado = 1
  AND bpv.active_for_sale = 1
  AND bpv.active_on_mix = 1
  AND bpv.c_sucu_empr <> :origin_cd
ORDER BY bpv.c_sucu_empr, bpv.c_articulo, bpv.fecha_extraccion DESC NULLS LAST;

ALTER TABLE pdd_scope_excluded_branch_pairs
    ADD PRIMARY KEY (destination_branch, codigo_articulo);

CREATE TEMP TABLE pdd_scope_excluded_branches ON COMMIT DROP AS
SELECT DISTINCT destination_branch
FROM pdd_scope_excluded_branch_pairs;

ALTER TABLE pdd_scope_excluded_branches
    ADD PRIMARY KEY (destination_branch);

CREATE TEMP TABLE pdd_scope_pairs_snapshot ON COMMIT DROP AS
SELECT DISTINCT ON (bpv.c_sucu_empr, bpv.c_articulo)
    CAST(:origin_cd AS integer) AS origin_cd,
    bpv.c_sucu_empr::integer AS destination_branch,
    bpv.c_articulo::integer AS codigo_articulo,
    coalesce(bpv.c_proveedor_primario, a.c_proveedor_primario)::integer
        AS c_proveedor_primario,
    bpv.cod_cd::varchar(30) AS route_code,
    bpv.abastecimiento::integer AS supply_mode,
    (bpv.habilitado = 1) AS branch_habilitado,
    (bpv.active_for_sale = 1) AS branch_active_for_sale,
    (bpv.active_on_mix = 1) AS branch_active_on_mix,
    bpv.fecha_extraccion AS source_extracted_at,
    encode(
        sha256(
            convert_to(
                concat_ws('|',
                    bpv.c_sucu_empr::text,
                    bpv.c_articulo::text,
                    coalesce(bpv.c_proveedor_primario::text, a.c_proveedor_primario::text, ''),
                    bpv.cod_cd,
                    bpv.abastecimiento::text,
                    bpv.habilitado::text,
                    bpv.active_for_sale::text,
                    bpv.active_on_mix::text
                ),
                'UTF8'
            )
        ),
        'hex'
    )::char(64) AS source_row_hash
FROM src.base_productos_vigentes AS bpv
INNER JOIN pdd_scope_articles_snapshot AS a
    ON a.codigo_articulo = bpv.c_articulo
WHERE bpv.cod_cd = '41CD'
  AND bpv.abastecimiento = 0
  AND bpv.habilitado = 1
  AND bpv.active_for_sale = 1
  AND bpv.active_on_mix = 1
  AND bpv.c_sucu_empr <> :origin_cd
  AND NOT EXISTS (
      SELECT 1
      FROM pdd_scope_excluded_branches AS excluded
      WHERE excluded.destination_branch = bpv.c_sucu_empr::integer
  )
ORDER BY bpv.c_sucu_empr, bpv.c_articulo, bpv.fecha_extraccion DESC NULLS LAST;

ALTER TABLE pdd_scope_pairs_snapshot
    ADD PRIMARY KEY (destination_branch, codigo_articulo);
