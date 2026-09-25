-- Controles del ultimo lote E/C/A simulado en DESA.
-- Ejecutar exclusivamente sobre connexa_platform_diarco.

-- 1. Cabeceras, lineas, estados y cantidades por tipo.
WITH latest_batch AS (
    SELECT notes::jsonb ->> 'batchCode' AS batch_code
    FROM stock_management.pdd_directed_need
    WHERE reason = 'SIMULATED_FRONTEND_TEST_DATA'
    ORDER BY created_at DESC
    LIMIT 1
)
SELECT
    b.batch_code,
    d.need_type,
    d.status,
    count(DISTINCT d.directed_need_id) AS cabeceras,
    count(*) AS lineas,
    count(*) FILTER (WHERE l.status = 'PARTIAL') AS parciales,
    sum(l.original_quantity) AS cantidad_original,
    sum(l.prepared_allocated_quantity) AS cantidad_preparada,
    sum(l.open_quantity) AS cantidad_abierta
FROM latest_batch b
JOIN stock_management.pdd_directed_need d
  ON d.notes::jsonb ->> 'batchCode' = b.batch_code
JOIN stock_management.pdd_directed_need_line l
  ON l.directed_need_id = d.directed_need_id
GROUP BY b.batch_code, d.need_type, d.status
ORDER BY d.need_type;

-- 2. Conciliacion de la foto vigente DECAS.
SELECT
    b.business_date,
    b.snapshot_version,
    count(*) AS lineas,
    sum(b.d_open_quantity) AS d,
    sum(b.e_open_quantity) AS e,
    sum(b.c_open_quantity) AS c,
    sum(b.a_open_quantity) AS a,
    sum(b.s_open_quantity) AS s,
    sum(b.mandatory_open_quantity) AS obligatorio,
    sum(b.optional_open_quantity) AS opcional,
    sum(b.total_open_quantity) AS total
FROM stock_management.pdd_current_backlog_line b
GROUP BY b.business_date, b.snapshot_version
ORDER BY b.business_date DESC, b.snapshot_version;

-- 3. Atribucion de las fuentes simuladas dentro del backlog vigente.
WITH latest_batch AS (
    SELECT notes::jsonb ->> 'batchCode' AS batch_code
    FROM stock_management.pdd_directed_need
    WHERE reason = 'SIMULATED_FRONTEND_TEST_DATA'
    ORDER BY created_at DESC
    LIMIT 1
), simulated_lines AS (
    SELECT l.directed_need_line_id, d.need_type
    FROM latest_batch b
    JOIN stock_management.pdd_directed_need d
      ON d.notes::jsonb ->> 'batchCode' = b.batch_code
    JOIN stock_management.pdd_directed_need_line l
      ON l.directed_need_id = d.directed_need_id
)
SELECT
    a.source_type,
    count(*) AS atribuciones,
    sum(a.contributed_quantity) AS cantidad_contribuida,
    sum(a.prepared_allocated_quantity) AS cantidad_preparada,
    sum(a.contributed_quantity - a.prepared_allocated_quantity)
        AS cantidad_abierta
FROM stock_management.pdd_backlog_source_allocation a
JOIN simulated_lines s
  ON s.directed_need_line_id = a.source_entity_id
 AND s.need_type = a.source_type
GROUP BY a.source_type
ORDER BY a.source_type;

-- 4. Cobertura de estimaciones logisticas para lineas con E/C/A.
SELECT
    count(*) AS lineas_eca,
    count(*) FILTER (WHERE estimated_packages IS NOT NULL) AS con_bultos,
    count(*) FILTER (WHERE estimated_pallets IS NOT NULL) AS con_pallets,
    count(*) FILTER (WHERE estimated_weight_kg IS NOT NULL) AS con_peso,
    count(*) FILTER (WHERE estimated_volume_m3 IS NOT NULL) AS con_volumen,
    count(*) FILTER (WHERE freshness_status = 'INCOMPLETE') AS incompletas
FROM stock_management.pdd_current_backlog_line
WHERE e_open_quantity > 0
   OR c_open_quantity > 0
   OR a_open_quantity > 0;

-- 5. Integridad final: debe devolver cero en las tres columnas.
SELECT
    count(*) FILTER (
        WHERE mandatory_open_quantity
              <> d_open_quantity + e_open_quantity + c_open_quantity
    ) AS obligatorio_inconsistente,
    count(*) FILTER (
        WHERE optional_open_quantity <> a_open_quantity + s_open_quantity
    ) AS opcional_inconsistente,
    count(*) FILTER (
        WHERE total_open_quantity
              <> mandatory_open_quantity + optional_open_quantity
    ) AS total_inconsistente
FROM stock_management.pdd_current_backlog_line;
