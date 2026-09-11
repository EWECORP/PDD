"""Validacion SQL sobre TEST, siempre ROLLBACK; no ejecuta el motor Flyway."""
import json
import sys
from pathlib import Path
from uuid import uuid4
import psycopg2

PACKAGE=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(PACKAGE.parents[1]/'documentacion/parametros_stock'))
from relevar_base import config

def check(cur, schema):
    version,site,family,classification=uuid4(),uuid4(),uuid4(),987654321
    cur.execute(f'SELECT id FROM {schema}.spl_site LIMIT 1')
    row=cur.fetchone()
    if row: site=row[0]
    else: cur.execute(f'INSERT INTO {schema}.spl_site(id) VALUES (%s)',(str(site),))
    cur.execute(f'INSERT INTO {schema}.spl_stock_purchase_classification VALUES (%s,%s)',(classification,'TEST'))
    cur.execute(f'''INSERT INTO {schema}.spl_stock_policy_version
      (id,source_system,source_checksum,created_by,change_reason) VALUES (%s,'TEST',%s,'test','rollback')''',(str(version),str(uuid4())))
    insert=f'''INSERT INTO {schema}.spl_stock_policy_rule
      (id,policy_version_id,site_id,purchase_classification_code,target_stock_days,overstock_days)
      VALUES (%s,%s,%s,%s,15,3)'''
    cur.execute(insert,(str(uuid4()),str(version),str(site),classification))
    cur.execute('SAVEPOINT duplicate_check')
    try:
        cur.execute(insert,(str(uuid4()),str(version),str(site),classification))
    except psycopg2.errors.UniqueViolation:
        cur.execute('ROLLBACK TO SAVEPOINT duplicate_check')
    else: raise AssertionError('Se acepto una regla general duplicada')
    cur.execute(f"SELECT is_nullable FROM information_schema.columns WHERE table_schema=%s AND table_name='spl_stock_policy_rule' AND column_name='family_category_id'",(schema,))
    assert cur.fetchone()[0]=='YES'

def main():
    assert config['PGP_TEST_DB']=='connexa_platform_test'
    conn=psycopg2.connect(**{k:config['PGP_TEST_'+v] for k,v in [('host','HOST'),('port','PORT'),('dbname','DB'),('user','USER'),('password','PASSWORD')]},connect_timeout=15)
    scripts=[p.read_text(encoding='utf-8') for p in sorted((PACKAGE/'migrations').glob('V*.sql'))]
    results=[]
    try:
        for fresh in (True,False):
            try:
                with conn.cursor() as cur:
                    cur.execute("SET LOCAL lock_timeout='5s'; SET LOCAL statement_timeout='30s'")
                    schema='stock_policy_validation_'+uuid4().hex[:12] if fresh else 'supply_planning'
                    if fresh:
                        cur.execute(f'CREATE SCHEMA {schema}')
                        for table in ('spl_site','spl_supply_cluster','spl_category'):
                            cur.execute(f'CREATE TABLE {schema}.{table}(id uuid PRIMARY KEY)')
                    else:
                        cur.execute('SELECT count(*) FROM supply_planning.spl_stock_policy_rule')
                        before=cur.fetchone()[0]
                    for script in scripts:
                        cur.execute(script.replace('supply_planning.',schema+'.'))
                    if not fresh:
                        cur.execute('SELECT count(*) FROM supply_planning.spl_stock_policy_rule')
                        assert cur.fetchone()[0]==before
                    check(cur,schema)
                    results.append({'path':'fresh' if fresh else 'existing_test','passed':True,'rollback':True})
            finally: conn.rollback()
    finally: conn.close()
    (PACKAGE/'verification/results.json').write_text(json.dumps(results,indent=2),encoding='utf-8')
    print(json.dumps(results))

if __name__=='__main__':
    try: main()
    except psycopg2.Error as exc:
        msg=str(exc)
        for suffix in ('PASSWORD','HOST','USER','DB'):
            if config.get('PGP_TEST_'+suffix): msg=msg.replace(config['PGP_TEST_'+suffix],'<'+suffix+'>')
        raise SystemExit(msg)
