import importlib.util
import json
from decimal import Decimal
from pathlib import Path
import sys
import unittest

PACKAGE=Path(__file__).resolve().parents[1]
ETL=PACKAGE.parents[2]
sys.path.insert(0,str(ETL/'FORECAST_CONNEXA'))


def module(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    result=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


pdd=module('planning_adapter',PACKAGE/'application/pdd_parameter_adapter.py')
forecast=module('forecast_compare.planning_preview',PACKAGE/'application/forecast_preview/forecast_compare/extend.py')


class Adapters(unittest.TestCase):
    def params(self):
        return dict(product_code='1',site_code='11',replenishment_id='r1',replenishment_row_version=3,
                    product_site_active=True,target_stock_days=Decimal('15.2500'),overstock_days=Decimal('2.5000'),captured_at='2026-09-14T12:00:00Z')

    def test_pdd_canonical_overrides_legacy_without_changing_facts(self):
        stock=dict(codigo_articulo=1,sucursal=11,q_dias_stock=99,q_dias_sobre_stock=88,stock=42,dias_preparacion=3)
        result=pdd.apply_parameters([stock],[self.params()])[0]
        self.assertEqual(result['q_dias_stock'],Decimal('15.25'))
        self.assertEqual(result['q_dias_sobre_stock'],Decimal('2.5'))
        self.assertEqual(result['stock'],42)
        self.assertEqual(result['dias_preparacion'],3)
        self.assertEqual(result['_planning_input']['replenishment_row_version'],3)
        self.assertEqual(stock['q_dias_stock'],99)

    def test_pdd_missing_duplicate_inactive_and_nonfinite_rejected(self):
        stock=[dict(codigo_articulo=1,sucursal=11,q_dias_stock=99)]
        for rows in [[],[self.params(),self.params()],[dict(self.params(),product_site_active=False)],
                     [dict(self.params(),target_stock_days=None)],[dict(self.params(),overstock_days='NaN')]]:
            with self.assertRaises(ValueError):pdd.apply_parameters(stock,rows)

    def test_forecast_decimal_json_keeps_precision(self):
        encoded=json.dumps({'days':Decimal('15.2500')},default=forecast._json_decimal)
        self.assertEqual(json.loads(encoded)['days'],'15.2500')
        with self.assertRaises(TypeError):forecast._json_decimal(object())

    def test_forecast_scope_revision_and_kg(self):
        import pandas as pd
        frame=pd.DataFrame({'product_id':['p1'],'site_id':['s1']})
        forecast.apply_site_parameters(frame,[dict(product_id='p1',site_id='s1',Q_DIAS_STOCK=Decimal('15.25'),Q_DIAS_SOBRE_STOCK=Decimal('2.5'),replenishment_row_version=3)])
        self.assertEqual(frame.loc[0,'Q_DIAS_STOCK'],Decimal('15.25'))
        self.assertEqual(frame.loc[0,'replenishment_row_version'],3)
        forecast.apply_logistics(frame,[dict(product_id='p1',logistic_variable_id='l1',selection_row_version=2,
                    weight_in_gr=2500,purchase_factor=1.5,uom_id='kg')])
        self.assertEqual(frame.loc[0,'Q_PESO_UNIT_ART'],2.5)
        self.assertEqual(frame.loc[0,'Q_FACTOR_COMPRA'],1.5)
        self.assertEqual(frame.loc[0,'logistics_selection_row_version'],2)


if __name__=='__main__':unittest.main()
