"""Read-only capture; never runs migrations. Credentials stay in backend/.env."""
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import psycopg2
from psycopg2.extras import RealDictCursor

PACKAGE = Path(__file__).resolve().parents[1]
PDD = PACKAGE.parents[1]
sys.path.insert(0, str(PDD / 'documentacion' / 'parametros_stock'))
from relevar_base import config, queries


def main():
    conn = psycopg2.connect(**{k: config['PGP_TEST_' + v] for k, v in
        [('host','HOST'),('port','PORT'),('dbname','DB'),('user','USER'),('password','PASSWORD')]},
        connect_timeout=15, options='-c default_transaction_read_only=on -c statement_timeout=45000')
    result = {'captured_at': datetime.now(timezone.utc).isoformat()}
    try:
        conn.set_session(readonly=True, isolation_level='REPEATABLE READ')
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("select current_database() as database,current_setting('server_version') as version,current_setting('transaction_read_only') as read_only")
            result['database'] = dict(cur.fetchone())
            if result['database']['database'] != 'connexa_platform_test':
                raise RuntimeError('Unexpected database')
            for key in ('columns', 'constraints', 'indexes'):
                cur.execute(queries[key])
                result[key] = [dict(r) for r in cur.fetchall() if
                    (r.get('table_schema',r.get('schema',r.get('schemaname'))) == 'inventory'
                     or 'forecast_execution_execute' in r.get('table_name',r.get('tablename','')))]
            for key, query in {
                'replenishment_count': 'select count(*) as rows from inventory.inv_product_site_replenishment',
                'incoming_fk': "select conrelid::regclass::text as source,pg_get_constraintdef(oid) as definition from pg_constraint where contype='f' and confrelid='inventory.inv_product_site_replenishment'::regclass",
                'triggers': "select tgname,pg_get_triggerdef(oid) as definition from pg_trigger where tgrelid='inventory.inv_product_site_replenishment'::regclass and not tgisinternal",
                'flyway': 'select version,description,script,success from inventory.flyway_schema_history order by installed_rank',
                'principal_duplicates': 'select count(*) as products from (select product_id from inventory.inv_logistic_variable where active and principal group by 1 having count(*)>1) x',
                'forecast_integer_column_dependents': """select a.attname as column_name,
                    pg_describe_object(d.classid,d.objid,d.objsubid) as dependent
                    from pg_depend d join pg_attribute a on a.attrelid=d.refobjid and a.attnum=d.refobjsubid
                    where d.refobjid='supply_planning.spl_supply_forecast_execution_execute_result'::regclass
                    and a.attname in ('windows','last_purchase_quantity') order by 1,2""",
            }.items():
                cur.execute(query)
                result[key] = [dict(r) for r in cur.fetchall()]
        (PACKAGE/'verification'/'baseline_test.json').write_text(json.dumps(result,ensure_ascii=False,indent=2,default=str),encoding='utf-8')
        print(json.dumps({k:result[k] for k in ('database','replenishment_count','incoming_fk','triggers','principal_duplicates')}))
    finally:
        conn.rollback()
        conn.close()


if __name__ == '__main__':
    try:
        main()
    except psycopg2.Error as exc:
        message = str(exc)
        for suffix in ('PASSWORD','HOST','USER','DB'):
            value = config.get('PGP_TEST_'+suffix)
            if value:
                message = message.replace(value,'<'+suffix+'>')
        raise SystemExit(message)
