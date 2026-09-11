"""Aplica únicamente la carga inicial DRAFT revisada a TEST, atómicamente."""
import json
from pathlib import Path
import psycopg2
from relevar_base import config

def main():
    if config['PGP_TEST_DB']!='connexa_platform_test': raise SystemExit('Solo TEST')
    conn=psycopg2.connect(**{k:config['PGP_TEST_'+v] for k,v in [('host','HOST'),('port','PORT'),('dbname','DB'),('user','USER'),('password','PASSWORD')]},connect_timeout=15)
    try:
        sql=Path(__file__).with_name('carga_inicial_test.sql').read_text(encoding='utf-8')
        # El COMMIT se realiza sólo después de verificar valores y conteos.
        sql=sql.removesuffix('COMMIT;\n')
        with conn.cursor() as cur:
            cur.execute(sql)
            cur.execute("select count(*) from supply_planning.spl_stock_policy_rule")
            assert cur.fetchone()[0]==605
            cur.execute("select count(*) from supply_planning.spl_stock_policy_import_row")
            assert cur.fetchone()[0]==627
            cur.execute('''select count(*) from supply_planning.spl_stock_policy_import_row i
              join supply_planning.spl_stock_policy_rule r on r.id=i.rule_id
              where (i.target_stock_days,i.overstock_days,i.site_code,i.family_code,i.category_code,i.purchase_classification_code)
              is distinct from (r.target_stock_days,r.overstock_days,r.legacy_site_code,r.legacy_family_code,r.legacy_category_code,r.purchase_classification_code)''')
            assert cur.fetchone()[0]==0
        conn.commit()
        result={'applied':True,'status':'DRAFT','rules':605,'import_rows':627,'value_mismatches':0}
        Path(__file__).with_name('resultado_carga_test.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
        print(json.dumps(result))
    finally: conn.rollback(); conn.close()

if __name__=='__main__':
    try: main()
    except psycopg2.Error as exc:
        msg=str(exc)
        for suffix in ('PASSWORD','HOST','USER','DB'):
            if config.get('PGP_TEST_'+suffix): msg=msg.replace(config['PGP_TEST_'+suffix],'<'+suffix+'>')
        raise SystemExit(msg)
