INSERT INTO datamart.dm_pdd_scope_pair (
    scope_version_uuid,
    origin_cd,
    destination_branch,
    codigo_articulo,
    c_proveedor_primario,
    route_code,
    supply_mode,
    branch_habilitado,
    branch_active_for_sale,
    branch_active_on_mix,
    source_extracted_at,
    source_row_hash
)
SELECT
    CAST(:scope_version_uuid AS uuid),
    origin_cd,
    destination_branch,
    codigo_articulo,
    c_proveedor_primario,
    route_code,
    supply_mode,
    branch_habilitado,
    branch_active_for_sale,
    branch_active_on_mix,
    source_extracted_at,
    source_row_hash
FROM pdd_scope_pairs_snapshot;

