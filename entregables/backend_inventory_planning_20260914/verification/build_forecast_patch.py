"""Produce patch against current FORECAST_CONNEXA, without editing its code."""
import ast
import difflib
from pathlib import Path

PACKAGE = Path(__file__).resolve().parents[1]
ETL = PACKAGE.parents[2]
FORECAST = ETL / 'FORECAST_CONNEXA'


def replace_once(text, old, new):
    if text.count(old) != 1:
        raise RuntimeError('Source changed: expected exactly one occurrence: '+old[:80])
    return text.replace(old,new,1)


def build():
    patches=[]
    for relative in ('forecast_compare/extend.py','forecast_compare/field_status.py'):
        old=(FORECAST/relative).read_text(encoding='utf-8')
        new=old
        if relative.endswith('extend.py'):
            substitutions=[
                ('from datetime import datetime','from datetime import datetime\nfrom decimal import Decimal'),
                ('SELECT product_id::text, id::text, boxes_per_layer, pallet_layers,',
                 'SELECT product_id::text, logistic_variable_id::text, boxes_per_layer, pallet_layers,'),
                ('purchase_factor, weight_in_gr, uom_id\n                FROM inventory.inv_logistic_variable\n                WHERE active IS TRUE AND principal IS TRUE AND product_id=ANY(%s::uuid[])',
                 'purchase_factor, weight_in_gr, uom_id, selection_row_version\n                FROM inventory.inv_planning_logistics_v\n                WHERE usable_for_forecast IS TRUE AND product_id=ANY(%s::uuid[])'),
                ("'pallet_layers', 'purchase_factor', 'weight_in_gr', 'uom_id'], row)",
                 "'pallet_layers', 'purchase_factor', 'weight_in_gr', 'uom_id', 'selection_row_version'], row)"),
                ('ps.expected_stock_days,ps.supply_type,ps.supplying_site_id::text,',
                 'r.target_stock_days,ps.supply_type,ps.supplying_site_id::text,'),
                ('r.minimum_order_quantity,r.preparation_days,r.safety_stock_days',
                 'r.minimum_order_quantity,r.preparation_days,r.overstock_days,r.row_version'),
                ("'DIAS_PREPARACION','Q_DIAS_SOBRE_STOCK'], row)",
                 "'DIAS_PREPARACION','Q_DIAS_SOBRE_STOCK','replenishment_row_version'], row)"),
                ("'DIAS_PREPARACION','Q_DIAS_SOBRE_STOCK']:",
                 "'DIAS_PREPARACION','Q_DIAS_SOBRE_STOCK','replenishment_row_version']:"),
                ("out['logistic_variable_id'] = out.product_id.map(lambda key: unique.get(key, {}).get('logistic_variable_id'))",
                 "out['logistic_variable_id'] = out.product_id.map(lambda key: unique.get(key, {}).get('logistic_variable_id'))\n    out['logistics_selection_row_version'] = out.product_id.map(lambda key: unique.get(key, {}).get('selection_row_version'))"),
                ("source='CONNEXA_TEST_current_not_historical', supplier_id=supplier_id,",
                 "source='CONNEXA_TEST_current_not_historical', parameter_contract='inventory-planning-v1', supplier_id=supplier_id,"),
                ("def digest(path):", "def _json_decimal(value):\n    if isinstance(value, Decimal):\n        return str(value)  # Preserve exact master values in evidence JSON.\n    raise TypeError(type(value).__name__)\n\n\ndef digest(path):"),
                ("json.dumps(report, indent=2)","json.dumps(report, indent=2, default=_json_decimal)"),
            ]
            for a,b in substitutions:new=replace_once(new,a,b)
        else:
            new=replace_once(new,"('PEDIDO_MIN', 'DIAS_PREPARACION', 'Q_DIAS_SOBRE_STOCK')",
                             "('PEDIDO_MIN', 'DIAS_PREPARACION', 'Q_DIAS_STOCK', 'Q_DIAS_SOBRE_STOCK')")
            new=replace_once(new,"('Q_DIAS_STOCK', 'ABASTECIMIENTO', 'COD_CD')","('ABASTECIMIENTO', 'COD_CD')")
            new=replace_once(new,"return 'inventory.inv_logistic_variable',","return 'inventory.inv_planning_logistics_v',")
            new=replace_once(new,'Resolver ausencia, multiples activas/principales o atributos nulos; peso en kg',
                             'Configurar seleccion logistica explicita y atributos utilizables; peso en kg')
        ast.parse(new)
        patches.extend(difflib.unified_diff(old.splitlines(keepends=True),new.splitlines(keepends=True),
                       fromfile='a/'+relative,tofile='b/'+relative))
        dest=PACKAGE/'application'/'forecast_preview'/relative
        dest.parent.mkdir(parents=True,exist_ok=True)
        dest.write_text(new,encoding='utf-8')
    (PACKAGE/'application'/'FORECAST_CONNEXA.patch').write_text(''.join(patches),encoding='utf-8')
    print('Patch and review copies generated; FORECAST_CONNEXA source unchanged.')


if __name__=='__main__':build()
