"""Diagnósticos SELECT; no extraen datos personales ni ejecutan rutinas."""

QUALITY_QUERIES = {
    "stock_bounds_distribution": """select min_stock_units,max_stock_units,count(*) as rows
      from inventory.inv_product_site group by 1,2 order by count(*) desc limit 10""",
    "logistics_by_level": """select v.logistic_variable_level_id,l.name as level_name,
      count(*) as rows,count(*) filter(where v.active and v.principal) as active_principal,
      count(*) filter(where v.units is not null and v.units>0) as positive_units,
      count(*) filter(where v.units_per_box is null) as missing_units_per_box,
      count(*) filter(where v.units_per_box=0) as zero_units_per_box
      from inventory.inv_logistic_variable v
      join inventory.inv_logistic_variable_level l on l.id=v.logistic_variable_level_id
      group by 1,2 order by 1""",
    "logistics_duplicate_level": """select count(*) as product_levels_with_multiple_active_principal
      from (select product_id,logistic_variable_level_id from inventory.inv_logistic_variable
      where active and principal group by 1,2 having count(*)>1) x""",
    "days_discrepancies": """select s.code as site_code,p.ext_code as product_code,
      ps.expected_stock_days,r.target_coverage_days,r.safety_stock_days
      from inventory.inv_product_site_replenishment r
      join inventory.inv_product_site ps on ps.id=r.product_site_id
      join inventory.inv_site s on s.id=ps.site_id join inventory.inv_product p on p.id=ps.product_id
      where r.target_coverage_days is distinct from ps.expected_stock_days order by 1,2""",
    "category_uuid_discrepancies": """select i.ext_code,i.id as inventory_id,s.id as supply_planning_id
      from inventory.inv_category i join supply_planning.spl_category s on s.ext_code=i.ext_code
      where i.id<>s.id order by i.ext_code""",
    "nonfinite_replenishment": """select count(*) as rows from inventory.inv_product_site_replenishment
      where exists(select 1 from unnest(array[target_coverage_days,safety_stock_days,
      minimum_order_quantity,order_multiple,lead_time_days,preparation_days,transit_days]) x
      where x::text in ('NaN','Infinity','-Infinity'))""",
    "column_details": """select n.nspname as schema,c.relname as table_name,a.attname as column_name,
      format_type(a.atttypid,a.atttypmod) as formatted_type,
      col_description(c.oid,a.attnum) as comment
      from pg_attribute a join pg_class c on c.oid=a.attrelid
      join pg_namespace n on n.oid=c.relnamespace
      where n.nspname in ('inventory','supply_planning','stock_management')
      and c.relkind in ('r','p') and a.attnum>0 and not a.attisdropped order by 1,2,a.attnum""",
    "replenishment_summary": """select count(*) as rows,
      count(*) filter(where active) as active,
      count(distinct product_site_id) as distinct_pairs,
      count(*) filter(where target_coverage_days is null) as missing_target,
      count(*) filter(where safety_stock_days is null) as missing_safety,
      count(*) filter(where lead_time_days is null) as missing_lead_time,
      count(*) filter(where order_multiple is null) as missing_multiple,
      count(*) filter(where target_coverage_days < 0 or safety_stock_days < 0
        or minimum_order_quantity < 0 or lead_time_days < 0
        or preparation_days < 0 or transit_days < 0) as negative_parameters,
      count(*) filter(where order_multiple <= 0) as nonpositive_multiple,
      min(target_coverage_days) as min_target, max(target_coverage_days) as max_target,
      min(safety_stock_days) as min_safety, max(safety_stock_days) as max_safety
      from inventory.inv_product_site_replenishment""",
    "replenishment_by_site": """select s.code as site_code,count(*) as rows,
      count(distinct ps.product_id) as products,
      count(*) filter(where r.target_coverage_days is distinct from ps.expected_stock_days) as differs_expected_days,
      count(*) filter(where not ps.active) as inactive_product_site
      from inventory.inv_product_site_replenishment r
      join inventory.inv_product_site ps on ps.id=r.product_site_id
      join inventory.inv_site s on s.id=ps.site_id group by s.code order by s.code""",
    "replenishment_methods": """select replenishment_method,replenishment_frequency,count(*) as rows
      from inventory.inv_product_site_replenishment group by 1,2 order by 1,2""",
    "product_site_quality": """select count(*) as rows,count(*) filter(where active) as active,
      count(*) filter(where expected_stock_days < 0 or min_stock_units < 0 or max_stock_units < 0) as negative_stock_parameters,
      count(*) filter(where max_stock_units < min_stock_units) as max_below_min,
      count(*) filter(where valid_to < valid_from) as inverted_validity,
      count(*) filter(where supplying_site_id=site_id) as self_supply,
      count(*) filter(where active_for_transfer and supplying_site_id is null) as transfer_without_supply_site,
      count(*) filter(where active_on_assortment) as on_assortment
      from inventory.inv_product_site""",
    "product_quality": """select count(*) as rows,
      count(*) filter(where ext_code is null or btrim(ext_code)='') as missing_external_code,
      count(*) filter(where category_id is null) as missing_category,
      count(*) filter(where valid_to < valid_from) as inverted_validity
      from inventory.inv_product""",
    "supplier_primary_quality": """select count(*) as products_with_multiple_active_primary
      from (select product_id from inventory.inv_product_supplier where active and primary_supplier
      group by product_id having count(*) > 1) x""",
    "logistics_quality": """select count(*) as rows,
      count(*) filter(where active and principal) as active_principal,
      count(*) filter(where active and principal and (purchase_factor is null or purchase_factor<=0)) as principal_invalid_purchase_factor,
      count(*) filter(where active and principal and (units_per_box is null or units_per_box<=0)) as principal_invalid_box_units,
      count(*) filter(where units_per_box<0 or units_per_pallet<0 or volume<0 or gross_weight<0) as negative_parameters
      from inventory.inv_logistic_variable""",
    "logistics_multiple_principal": """select count(*) as products_with_multiple_active_principal
      from (select product_id from inventory.inv_logistic_variable where active and principal
      group by product_id having count(*) > 1) x""",
    "assortment_quality": """select count(*) as rows,
      count(*) filter(where valid_to<valid_from) as inverted_validity,
      count(distinct product_site_id) as distinct_pairs from inventory.inv_product_site_assortment""",
    "site_mapping": """select count(*) as inventory_sites,
      count(*) filter(where s.id is not null) as matching_code,
      count(*) filter(where s.id=i.id) as same_uuid,
      count(*) filter(where s.id is not null and s.id<>i.id) as different_uuid
      from inventory.inv_site i left join supply_planning.spl_site s on s.code=i.code""",
    "category_mapping": """select count(*) as inventory_categories,
      count(*) filter(where s.id is not null) as matching_code,
      count(*) filter(where s.id=i.id) as same_uuid,
      count(*) filter(where s.id is not null and s.id<>i.id) as different_uuid
      from inventory.inv_category i left join supply_planning.spl_category s on s.ext_code=i.ext_code""",
    "stock_policy_versions": """select id,status,valid_from,valid_to,source_system from supply_planning.spl_stock_policy_version""",
    "stock_policy_integrity": """select count(*) as imports,
      count(*) filter(where i.mapping_status='MAPPED') as mapped,
      count(*) filter(where i.mapping_status='EXCLUDED_CLOSED') as excluded_closed,
      count(*) filter(where i.mapping_status='PENDING') as pending,
      count(*) filter(where i.policy_version_id<>r.policy_version_id) as cross_version,
      count(*) filter(where i.target_stock_days<>r.target_stock_days or i.overstock_days<>r.overstock_days) as different_days
      from supply_planning.spl_stock_policy_import_row i left join supply_planning.spl_stock_policy_rule r on r.id=i.rule_id""",
    "stock_policy_hierarchy": """select count(*) as rules,
      count(*) filter(where r.category_id is not null and c.parent_id is distinct from r.family_category_id) as wrong_parent
      from supply_planning.spl_stock_policy_rule r left join supply_planning.spl_category c on c.id=r.category_id""",
    "inventory_flyway": """select installed_rank,version,description,type,script,installed_on,success
      from inventory.flyway_schema_history order by installed_rank""",
    "constraint_validation": """select n.nspname as schema,c.relname as table_name,con.conname as name,con.convalidated as validated
      from pg_constraint con join pg_class c on c.oid=con.conrelid join pg_namespace n on n.oid=c.relnamespace
      where n.nspname in ('inventory','supply_planning') and not con.convalidated""",
}
