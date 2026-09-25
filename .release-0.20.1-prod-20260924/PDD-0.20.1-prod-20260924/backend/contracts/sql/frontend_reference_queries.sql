-- PDD Frontend API v1 - consultas de referencia para el backend de plataforma.
-- No ejecutar desde navegador. Todos los filtros deben parametrizarse.

-- 1. Snapshot vigente y corrida que lo publicó.
SELECT
    b.snapshot_version,
    min(b.business_date) AS business_date,
    r.calculation_run_uuid,
    r.formula_version,
    r.status,
    min(b.published_at) AS first_published_at,
    max(b.published_at) AS last_published_at,
    count(*) AS line_count
FROM stock_management.pdd_current_backlog_line b
JOIN stock_management.pdd_calculation_run r
  ON r.calculation_run_id = b.calculation_run_id
WHERE r.run_type = 'PUBLISH'
  AND r.scope_id = '41:BACKLOG'
  AND r.status = 'SUCCEEDED'
  AND r.is_current
GROUP BY b.snapshot_version, r.calculation_run_uuid, r.formula_version, r.status;

-- 2. Resumen. Los nombres se enriquecen fuera de estas tablas PDD.
SELECT
    count(*) AS line_count,
    count(DISTINCT b.codigo_articulo) AS article_count,
    count(DISTINCT b.sucursal) AS branch_count,
    count(DISTINCT b.c_proveedor_primario) AS supplier_count,
    sum(b.d_open_quantity) AS d,
    sum(b.e_open_quantity) AS e,
    sum(b.c_open_quantity) AS c,
    sum(b.a_open_quantity) AS a,
    sum(b.s_open_quantity) AS s,
    sum(b.mandatory_open_quantity) AS mandatory,
    sum(b.optional_open_quantity) AS optional,
    sum(b.total_open_quantity) AS total,
    count(*) FILTER (WHERE b.irq_score >= 90) AS critical_irq_line_count,
    count(*) FILTER (WHERE b.freshness_status = 'CURRENT') AS current_lines,
    count(*) FILTER (WHERE b.freshness_status = 'STALE') AS stale_lines,
    count(*) FILTER (WHERE b.freshness_status = 'INCOMPLETE') AS incomplete_lines
FROM stock_management.pdd_current_backlog_line b;

-- 3. Catálogo de alertas para el resumen.
SELECT alert_code, count(*) AS line_count
FROM stock_management.pdd_current_backlog_line b
CROSS JOIN LATERAL unnest(b.alert_codes) AS alert(alert_code)
GROUP BY alert_code
ORDER BY line_count DESC, alert_code;

-- 4. Base de consulta paginada. El cursor HTTP es opaco y debe codificar
-- snapshotVersion + sort + última tupla; no usar OFFSET para páginas profundas.
SELECT
    b.backlog_line_uuid,
    b.row_version,
    b.snapshot_version,
    b.business_date,
    b.origin_cd,
    b.sucursal,
    b.codigo_articulo,
    b.c_proveedor_primario,
    b.d_open_quantity,
    b.e_open_quantity,
    b.c_open_quantity,
    b.a_open_quantity,
    b.s_open_quantity,
    b.mandatory_open_quantity,
    b.optional_open_quantity,
    b.total_open_quantity,
    b.irq_score,
    b.priority_score,
    b.oldest_need_date,
    b.target_date,
    b.active_imported_quantity,
    b.prepared_quantity,
    b.in_transit_quantity,
    b.cd_reference_stock,
    b.estimated_packages,
    b.estimated_pallets,
    b.estimated_weight_kg,
    b.estimated_volume_m3,
    b.freshness_status,
    b.alert_codes,
    b.published_at
FROM stock_management.pdd_current_backlog_line b
WHERE b.snapshot_version = CAST(:snapshot_version AS uuid)
  AND (:branch_ids IS NULL OR b.sucursal = ANY(CAST(:branch_ids AS integer[])))
  AND (:article_ids IS NULL OR b.codigo_articulo = ANY(CAST(:article_ids AS integer[])))
  AND (:supplier_ids IS NULL OR b.c_proveedor_primario = ANY(CAST(:supplier_ids AS integer[])))
  AND (:minimum_irq IS NULL OR b.irq_score >= :minimum_irq)
  AND (:with_alerts IS NULL OR NOT :with_alerts OR cardinality(b.alert_codes) > 0)
ORDER BY
    b.priority_score DESC,
    b.irq_score DESC NULLS LAST,
    b.target_date NULLS LAST,
    b.oldest_need_date NULLS LAST,
    b.backlog_line_uuid
LIMIT :page_size_plus_one;

-- 5. Detalle por UUID público.
SELECT b.*, r.calculation_run_uuid, r.formula_version, r.summary
FROM stock_management.pdd_current_backlog_line b
JOIN stock_management.pdd_calculation_run r
  ON r.calculation_run_id = b.calculation_run_id
WHERE b.backlog_line_uuid = CAST(:backlog_line_uuid AS uuid);

-- 6. Fuentes atribuidas y saldo explicado.
SELECT
    a.source_type,
    a.source_entity_id,
    a.source_business_date,
    a.contributed_quantity,
    a.prepared_allocated_quantity,
    a.contributed_quantity - a.prepared_allocated_quantity AS open_quantity,
    a.attribution_order,
    a.attribution_rule_version
FROM stock_management.pdd_backlog_source_allocation a
JOIN stock_management.pdd_current_backlog_line b
  ON b.backlog_line_id = a.backlog_line_id
WHERE b.backlog_line_uuid = CAST(:backlog_line_uuid AS uuid)
ORDER BY a.attribution_order;

-- 7. Posición y fórmula D/S de la corrida fuente indicada por el publicador.
WITH selected AS (
    SELECT
        b.sucursal,
        b.codigo_articulo,
        (r.summary ->> 'source_daily_run_uuid')::uuid AS daily_run_uuid
    FROM stock_management.pdd_current_backlog_line b
    JOIN stock_management.pdd_calculation_run r
      ON r.calculation_run_id = b.calculation_run_id
    WHERE b.backlog_line_uuid = CAST(:backlog_line_uuid AS uuid)
),
daily_run AS (
    SELECT r.calculation_run_id, r.calculation_run_uuid,
           r.formula_version, r.configuration_version_id
    FROM stock_management.pdd_calculation_run r
    JOIN selected s ON s.daily_run_uuid = r.calculation_run_uuid
)
SELECT
    r.calculation_run_uuid,
    r.formula_version,
    p.physical_stock,
    p.direct_po_inbound,
    p.cd_in_transit,
    p.special_sale_committed,
    p.confirmed_transfer_pending,
    p.net_stock,
    p.pdvb_business_date,
    p.pdvb_value,
    p.lead_time_days,
    p.target_stock_days,
    p.overstock_days,
    p.critical_stock,
    p.minimum_stock,
    p.maximum_stock,
    p.overstock_quantity,
    p.coverage_days,
    p.calculation_status,
    p.explanation,
    p.alert_codes
FROM selected s
JOIN daily_run r ON true
JOIN stock_management.pdd_branch_stock_position p
  ON p.calculation_run_id = r.calculation_run_id
 AND p.sucursal = s.sucursal
 AND p.codigo_articulo = s.codigo_articulo;

-- 8. Necesidades dirigidas. La API debe evitar exponer directed_need_id bigint.
SELECT
    d.directed_need_uuid,
    d.origin_cd,
    d.need_type,
    d.business_reference,
    d.c_proveedor_primario,
    d.valid_from,
    d.valid_to,
    d.priority_score,
    d.owner_user,
    d.approver_user,
    d.status,
    d.version_no,
    d.reason,
    d.notes,
    d.created_at,
    d.created_by,
    d.updated_at,
    d.updated_by,
    d.approved_at,
    d.closed_at
FROM stock_management.pdd_directed_need d
WHERE (:need_types IS NULL OR d.need_type = ANY(CAST(:need_types AS text[])))
  AND (:statuses IS NULL OR d.status = ANY(CAST(:statuses AS text[])))
ORDER BY d.updated_at DESC, d.directed_need_uuid
LIMIT :page_size_plus_one;

-- 9. Líneas de una dirigida.
SELECT
    l.directed_need_line_id,
    l.sucursal,
    l.codigo_articulo,
    l.original_quantity,
    l.prepared_allocated_quantity,
    l.cancelled_quantity,
    l.open_quantity,
    l.target_date,
    l.sla_at,
    l.unit_code,
    l.units_per_package,
    l.packages_per_pallet,
    l.unit_weight_kg,
    l.unit_volume_m3,
    l.status,
    l.last_activity_at,
    l.row_version
FROM stock_management.pdd_directed_need_line l
JOIN stock_management.pdd_directed_need d
  ON d.directed_need_id = l.directed_need_id
WHERE d.directed_need_uuid = CAST(:directed_need_uuid AS uuid)
ORDER BY l.sucursal, l.codigo_articulo;

-- 10. Historial de versiones.
SELECT
    v.version_no,
    v.valid_from_ts,
    v.changed_by,
    v.change_reason,
    v.before_state,
    v.after_state,
    v.correlation_id
FROM stock_management.pdd_directed_need_version v
JOIN stock_management.pdd_directed_need d
  ON d.directed_need_id = v.directed_need_id
WHERE d.directed_need_uuid = CAST(:directed_need_uuid AS uuid)
ORDER BY v.version_no DESC;

-- Las mutaciones E/C/A no se implementan como SQL suelto: deben usar una
-- transacción del servicio, autenticación, Idempotency-Key, If-Match,
-- validaciones de scope y escritura append-only de pdd_directed_need_version.
