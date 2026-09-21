"""Verifica la carga confirmada contra sus archivos originales; solo lectura en TEST."""
import argparse
import csv
import json
from pathlib import Path
from load_test import connect, digest


def verify(folder):
    manifest=json.loads((folder/'manifest.json').read_text(encoding='utf-8'))
    for name,checksum in manifest['sha256'].items():
        assert digest(folder/(name+'.csv'))==checksum, 'Capture checksum mismatch'
    rules=json.loads((folder/'result.json').read_text(encoding='utf-8'))['rules']
    fill=rules['existing_stock_null_days']!='EXCLUDE'
    expected={}
    pending=set()
    with (folder/'replenishment.csv').open(encoding='utf-8',newline='') as f:
        for r in csv.DictReader(f):
            key=(r['product_code'],r['site_code'])
            missing=r['missing_stock']=='t'
            if not fill and not missing and (not r['target_stock_days'] or not r['overstock_days']):
                pending.add(key)
                continue
            from decimal import Decimal
            expected[key]=tuple(Decimal(v) for v in (
                '0' if missing else (r['target_stock_days'] or '7'),
                '0' if missing else (r['overstock_days'] or '0'),r['minimum_order_quantity'],r['preparation_days'] or '0'))
    with (folder/'classification.csv').open(encoding='utf-8',newline='') as f:
        classes={r['product_code']:r['classification_code'] for r in csv.DictReader(f)}
    result={'replenishment_checked':0,'parameter_mismatches':0,'pending_loaded':0,'classification_checked':0,'classification_mismatches':0}
    conn=connect('PGP_TEST_',True)
    try:
        with conn.cursor(name='verify_parameters') as cur:
            cur.itersize=10000
            cur.execute('''SELECT p.ext_code,s.code,r.target_stock_days,r.overstock_days,
                r.minimum_order_quantity,r.preparation_days,r.active,ps.active
                FROM inventory.inv_product_site_replenishment r
                JOIN inventory.inv_product_site ps ON ps.id=r.product_site_id
                JOIN inventory.inv_product p ON p.id=ps.product_id JOIN inventory.inv_site s ON s.id=ps.site_id''')
            for row in cur:
                key=tuple(row[:2]);result['replenishment_checked']+=1
                result['pending_loaded']+=key in pending
                result['parameter_mismatches']+=expected.get(key)!=tuple(row[2:6]) or row[6]!=row[7]
        type_id=json.loads((folder/'result.json').read_text(encoding='utf-8'))['purchase_classification_type']['id']
        with conn.cursor() as cur:
            cur.execute('''SELECT p.ext_code,v.code FROM inventory.inv_product_classification c
                JOIN inventory.inv_product p ON p.id=c.product_id
                JOIN inventory.inv_product_classification_value v ON v.id=c.classification_value_id
                WHERE c.classification_type_id=%s AND c.active''',(type_id,))
            for code,value in cur:
                result['classification_checked']+=1
                result['classification_mismatches']+=classes.get(code)!=value
            cur.execute('''SELECT count(*) FROM (SELECT product_id,classification_type_id
                FROM inventory.inv_product_classification WHERE active GROUP BY 1,2 HAVING count(*)>1) x''')
            result['duplicate_active_classifications']=cur.fetchone()[0]
            cur.execute('''SELECT count(*) FROM inventory.inv_product_planning_logistics l
                JOIN inventory.inv_logistic_variable v ON v.id=l.logistic_variable_id AND v.product_id=l.product_id
                WHERE NOT (v.active AND v.principal AND v.purchase_factor>0
                AND v.purchase_factor<'Infinity'::float8 AND v.uom_id IS NOT NULL AND btrim(v.uom_id)<>''
                AND (v.uom_id='unidad' OR (v.weight_in_gr>0 AND v.weight_in_gr<'Infinity'::float8))) IS TRUE''')
            result['invalid_logistics']=cur.fetchone()[0]
            for table in ('inv_product_site_replenishment','inv_product_classification','inv_product_planning_logistics','inv_planning_parameter_audit'):
                cur.execute('SELECT count(*) FROM inventory.'+table)
                result[table]=cur.fetchone()[0]
        counts=json.loads((folder/'result.json').read_text(encoding='utf-8'))['counts']
        result['passed']=(all(result[k]==0 for k in ('parameter_mismatches','pending_loaded','classification_mismatches','duplicate_active_classifications','invalid_logistics'))
            and result['replenishment_checked']==counts['replenishment_ready']
            and result['classification_checked']==counts['classification_ready']
            and result['inv_product_planning_logistics']==counts['logistic_unique_usable'])
        (folder/'verification.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
        print(json.dumps(result))
        assert result['passed'], 'Verification failed'
    finally:
        conn.rollback();conn.close()


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory',type=Path,required=True)
    verify(parser.parse_args().directory)
