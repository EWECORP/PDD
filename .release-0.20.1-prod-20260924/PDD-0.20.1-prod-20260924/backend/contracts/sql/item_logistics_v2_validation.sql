-- Validacion posterior de ITEM_LOGISTICS_V2.
-- Base objetivo: connexa_platform_test o connexa_platform_diarco.

WITH latest AS (
    SELECT calculation_run_id
    FROM stock_management.pdd_calculation_run
    WHERE run_type = 'DATA_PREP'
      AND formula_version = 'ITEM_LOGISTICS_V2'
      AND status = 'SUCCEEDED'
      AND is_current
    ORDER BY finished_at DESC NULLS LAST, calculation_run_id DESC
    LIMIT 1
)
SELECT
    r.calculation_run_uuid,
    r.business_date,
    r.formula_version,
    r.status,
    r.is_current,
    r.input_row_count,
    r.output_row_count,
    r.warning_count,
    r.error_count,
    r.input_checksum = r.output_checksum AS checksum_correcto,
    r.summary
FROM stock_management.pdd_calculation_run AS r
JOIN latest AS x USING (calculation_run_id);

WITH latest AS (
    SELECT calculation_run_id
    FROM stock_management.pdd_calculation_run
    WHERE run_type = 'DATA_PREP'
      AND formula_version = 'ITEM_LOGISTICS_V2'
      AND status = 'SUCCEEDED'
      AND is_current
    ORDER BY finished_at DESC NULLS LAST, calculation_run_id DESC
    LIMIT 1
)
SELECT
    s.source_code,
    s.source_database,
    s.physical_relation,
    s.as_of_ts,
    s.row_count,
    s.status,
    s.checksum,
    s.detail
FROM stock_management.pdd_source_snapshot AS s
JOIN latest AS x USING (calculation_run_id);

WITH latest AS (
    SELECT calculation_run_id
    FROM stock_management.pdd_calculation_run
    WHERE run_type = 'DATA_PREP'
      AND formula_version = 'ITEM_LOGISTICS_V2'
      AND status = 'SUCCEEDED'
      AND is_current
    ORDER BY finished_at DESC NULLS LAST, calculation_run_id DESC
    LIMIT 1
)
SELECT
    l.quality_status,
    l.packaging_quality_status,
    l.weight_quality_status,
    l.volume_quality_status,
    l.pallet_quality_status,
    count(*) AS articulos
FROM stock_management.pdd_item_logistics_snapshot AS l
JOIN latest AS x USING (calculation_run_id)
GROUP BY
    l.quality_status,
    l.packaging_quality_status,
    l.weight_quality_status,
    l.volume_quality_status,
    l.pallet_quality_status
ORDER BY articulos DESC;

WITH latest AS (
    SELECT calculation_run_id, scope_version_id, input_row_count
    FROM stock_management.pdd_calculation_run
    WHERE run_type = 'DATA_PREP'
      AND formula_version = 'ITEM_LOGISTICS_V2'
      AND status = 'SUCCEEDED'
      AND is_current
    ORDER BY finished_at DESC NULLS LAST, calculation_run_id DESC
    LIMIT 1
), coverage AS (
    SELECT
        x.input_row_count AS esperados,
        count(*) AS publicados,
        count(DISTINCT l.codigo_articulo) AS articulos,
        count(*) FILTER (WHERE a.codigo_articulo IS NULL) AS fuera_scope,
        count(*) FILTER (WHERE l.source_logistics_id IS NULL) AS sin_fuente
    FROM latest AS x
    JOIN stock_management.pdd_item_logistics_snapshot AS l
      USING (calculation_run_id)
    LEFT JOIN stock_management.pdd_distribution_scope_article AS a
      ON a.scope_version_id = x.scope_version_id
     AND a.codigo_articulo = l.codigo_articulo
    GROUP BY x.input_row_count
)
SELECT *, esperados = publicados AND publicados = articulos AS cobertura_correcta
FROM coverage;

WITH latest AS (
    SELECT calculation_run_id
    FROM stock_management.pdd_calculation_run
    WHERE run_type = 'DATA_PREP'
      AND formula_version = 'ITEM_LOGISTICS_V2'
      AND status = 'SUCCEEDED'
      AND is_current
    ORDER BY finished_at DESC NULLS LAST, calculation_run_id DESC
    LIMIT 1
)
SELECT
    count(*) FILTER (
        WHERE unit_weight_kg IS NOT NULL
          AND weight_quality_status = 'MISSING'
    ) AS peso_inconsistente,
    count(*) FILTER (
        WHERE unit_volume_m3 IS NOT NULL
          AND volume_quality_status = 'MISSING'
    ) AS volumen_inconsistente,
    count(*) FILTER (
        WHERE packages_per_pallet IS NOT NULL
          AND pallet_quality_status = 'MISSING'
    ) AS pallet_inconsistente,
    count(*) FILTER (
        WHERE quality_issue_codes IS NULL OR attributes IS NULL
    ) AS contrato_incompleto,
    count(*) FILTER (
        WHERE input_checksum IS NULL OR length(input_checksum) <> 64
    ) AS checksum_invalido,
    count(*) - count(DISTINCT codigo_articulo) AS duplicados
FROM stock_management.pdd_item_logistics_snapshot AS l
JOIN latest AS x USING (calculation_run_id);
