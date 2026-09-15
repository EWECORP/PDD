"""Delivered adapter: overlay canonical days without changing facts or formulas.

The PDD service must call read_parameters_by_codes.sql once for its frozen scope,
then call this adapter before build_branch_position. This module does not connect
to a database and is not installed automatically by Flyway.
"""
from decimal import Decimal


def decimal_day(value):
    if value is None:
        raise ValueError('Missing canonical days')
    result = Decimal(str(value))
    if not result.is_finite() or result < 0:
        raise ValueError('Invalid canonical days')
    return result


def apply_parameters(stock_rows, parameter_rows):
    by_pair = {}
    for row in parameter_rows:
        key = (int(row['product_code']), int(row['site_code']))
        if key in by_pair:
            raise ValueError('Duplicate parameter pair')
        by_pair[key] = row
    result = []
    seen = set()
    for source in stock_rows:
        key = (int(source['codigo_articulo']), int(source['sucursal']))
        if key in seen:
            raise ValueError('Duplicate stock pair')
        seen.add(key)
        row = by_pair.get(key)
        if row is None or not row.get('replenishment_id') or not row.get('replenishment_row_version'):
            raise ValueError('Missing canonical parameter row')
        if row.get('product_site_active') is not True:
            raise ValueError('Inactive inventory product/site in PDD scope')
        target = decimal_day(row['target_stock_days'])
        overstock = decimal_day(row['overstock_days'])
        evidence = {
            'contract_version': 'inventory-planning-v1',
            'source_relation': 'inventory.inv_product_site_replenishment',
            'replenishment_id': str(row['replenishment_id']),
            'replenishment_row_version': int(row['replenishment_row_version']),
            'target_stock_days': str(target), 'overstock_days': str(overstock),
            'captured_at': str(row['captured_at']),
        }
        result.append({**source, 'q_dias_stock': target, 'q_dias_sobre_stock': overstock,
                       '_planning_input': evidence})
    if seen != set(by_pair):
        raise ValueError('Parameters outside frozen scope')
    return result
