INSERT INTO datamart.dm_pdd_scope_article (
    scope_version_uuid,
    codigo_articulo,
    c_proveedor_primario,
    cd_active_for_purchase,
    cd_habilitado,
    cd_active_for_sale,
    cd_active_on_mix,
    source_extracted_at,
    source_row_hash
)
SELECT
    CAST(:scope_version_uuid AS uuid),
    codigo_articulo,
    c_proveedor_primario,
    cd_active_for_purchase,
    cd_habilitado,
    cd_active_for_sale,
    cd_active_on_mix,
    source_extracted_at,
    source_row_hash
FROM pdd_scope_articles_snapshot;

