WITH exclusion_policy AS (
    SELECT jsonb_build_object(
        'policy_code', CAST(:exclusion_policy_json AS jsonb) ->> 'policy_code',
        'version', (CAST(:exclusion_policy_json AS jsonb) ->> 'version')::integer,
        'rules', jsonb_agg(
            jsonb_build_object(
                'rule_code', rule_code,
                'c_rubro', c_rubro,
                'rubro_name', rubro_name,
                'c_subrubro_1', c_subrubro_1,
                'subrubro_1_name', subrubro_1_name,
                'reason', reason
            ) ORDER BY c_rubro, c_subrubro_1
        )
    ) AS policy_json
    FROM pdd_scope_excluded_categories
),
branch_exclusion_policy AS (
    SELECT jsonb_build_object(
        'policy_code', 'PDD_OPERATIONAL_BRANCH_EXCLUSIONS',
        'version', 1,
        'source_relation', 'src.sucursales_excluidas',
        'excluded_branch_count', count(*)::integer,
        'excluded_pair_count', (
            SELECT count(*)::integer
            FROM pdd_scope_excluded_branch_pairs
        ),
        'excluded_branches', coalesce(
            jsonb_agg(destination_branch ORDER BY destination_branch),
            '[]'::jsonb
        )
    ) AS policy_json
    FROM pdd_scope_excluded_branches
),
article_manifest AS (
    SELECT
        count(*)::integer AS article_count,
        max(source_extracted_at) AS source_as_of_ts,
        encode(
            sha256(
                convert_to(
                    string_agg(
                        concat_ws('|',
                            codigo_articulo::text,
                            coalesce(c_proveedor_primario::text, ''),
                            CASE WHEN cd_active_for_purchase THEN '1' ELSE '0' END,
                            CASE WHEN cd_habilitado IS NULL THEN ''
                                 WHEN cd_habilitado THEN '1' ELSE '0' END,
                            CASE WHEN cd_active_for_sale IS NULL THEN ''
                                 WHEN cd_active_for_sale THEN '1' ELSE '0' END,
                            CASE WHEN cd_active_on_mix IS NULL THEN ''
                                 WHEN cd_active_on_mix THEN '1' ELSE '0' END
                        ),
                        E'\n' ORDER BY codigo_articulo
                    ),
                    'UTF8'
                )
            ),
            'hex'
        ) AS article_checksum
    FROM pdd_scope_articles_snapshot
),
pair_manifest AS (
    SELECT
        count(*)::integer AS pair_count,
        count(DISTINCT destination_branch)::integer AS destination_count,
        count(DISTINCT codigo_articulo)::integer AS routed_article_count,
        max(source_extracted_at) AS source_as_of_ts,
        encode(
            sha256(
                convert_to(
                    string_agg(
                        concat_ws('|',
                            destination_branch::text,
                            codigo_articulo::text,
                            coalesce(c_proveedor_primario::text, ''),
                            route_code,
                            supply_mode::text,
                            CASE WHEN branch_habilitado THEN '1' ELSE '0' END,
                            CASE WHEN branch_active_for_sale THEN '1' ELSE '0' END,
                            CASE WHEN branch_active_on_mix THEN '1' ELSE '0' END
                        ),
                        E'\n' ORDER BY destination_branch, codigo_articulo
                    ),
                    'UTF8'
                )
            ),
            'hex'
        ) AS pair_checksum
    FROM pdd_scope_pairs_snapshot
),
manifest AS (
    SELECT
        a.article_count,
        p.routed_article_count,
        p.pair_count,
        p.destination_count,
        greatest(a.source_as_of_ts, p.source_as_of_ts) AS source_as_of_ts,
        a.article_checksum,
        p.pair_checksum,
        e.policy_json,
        b.policy_json AS branch_policy_json,
        encode(
            sha256(
                convert_to(
                    'articles:' || a.article_checksum || '|pairs:' || p.pair_checksum,
                    'UTF8'
                )
            ),
            'hex'
        ) AS scope_checksum
    FROM article_manifest AS a
    CROSS JOIN pair_manifest AS p
    CROSS JOIN exclusion_policy AS e
    CROSS JOIN branch_exclusion_policy AS b
)
INSERT INTO datamart.dm_pdd_scope_version (
    scope_version_uuid,
    scope_code,
    version_no,
    supersedes_scope_version_uuid,
    origin_cd,
    business_date,
    status,
    source_as_of_ts,
    article_filter,
    pair_filter,
    article_count,
    routed_article_count,
    pair_count,
    destination_count,
    article_checksum,
    pair_checksum,
    scope_checksum,
    captured_by,
    detail
)
SELECT
    CAST(:scope_version_uuid AS uuid),
    :scope_code,
    :version_no,
    CAST(:supersedes_scope_version_uuid AS uuid),
    :origin_cd,
    CAST(:business_date AS date),
    'DRAFT',
    source_as_of_ts,
    jsonb_build_object(
        'c_sucu_empr', :origin_cd,
        'active_for_purchase', 1,
        'category_exclusion_policy', policy_json
    ),
    jsonb_build_object(
        'cod_cd', '41CD',
        'abastecimiento', 0,
        'habilitado', 1,
        'active_for_sale', 1,
        'active_on_mix', 1,
        'excludes_origin', true,
        'routing_semantics', jsonb_build_object(
            'selection_level', 'ARTICLE_BRANCH',
            'branch_number_is_filter', false,
            'supply_modes', jsonb_build_object(
                '0', 'DELIVERY_FROM_CD',
                '1', 'DIRECT_FROM_SUPPLIER',
                '2', 'CROSS_DOCKING',
                '3', 'DELIVERY_FROM_QX_82'
            )
        ),
        'operational_branch_exclusion_policy', branch_policy_json
    ),
    article_count,
    routed_article_count,
    pair_count,
    destination_count,
    article_checksum,
    pair_checksum,
    scope_checksum,
    :captured_by,
    jsonb_build_object(
        'capture_isolation', 'REPEATABLE READ',
        'category_exclusion_policy', policy_json,
        'operational_branch_exclusion_policy', branch_policy_json
    )
FROM manifest
RETURNING
    scope_version_uuid,
    source_as_of_ts,
    article_count,
    routed_article_count,
    pair_count,
    destination_count,
    article_checksum,
    pair_checksum,
    scope_checksum;
