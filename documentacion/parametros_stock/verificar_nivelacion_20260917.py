"""Verificación READ ONLY del cambio de BACK; no modifica datos ni estructuras."""
import json
from datetime import datetime, timezone
from pathlib import Path
import psycopg2
from psycopg2 import sql
from psycopg2.extras import RealDictCursor
from relevar_base import config, queries


def main():
    conn = psycopg2.connect(**{k:config['PGP_TEST_'+v] for k,v in
        [('host','HOST'),('port','PORT'),('dbname','DB'),('user','USER'),('password','PASSWORD')]},
        connect_timeout=15,options='-c default_transaction_read_only=on -c statement_timeout=45000')
    result={'captured_at':datetime.now(timezone.utc).isoformat()}
    try:
        conn.set_session(readonly=True,isolation_level='REPEATABLE READ')
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("select current_database() as database,current_setting('server_version') as version,current_setting('transaction_read_only') as read_only")
            result['database']=dict(cur.fetchone())
            if result['database']['database']!='connexa_platform_test':raise RuntimeError('Unexpected database')
            for key in ('tables','columns','constraints','indexes','triggers','views'):
                cur.execute(queries[key]); result[key]=[dict(r) for r in cur.fetchall()]
            result['checks']={}
            objects={(r['schema'],r['name']):r for r in result['tables']}
            targets=[('inventory',n) for n in ('inv_product_site_replenishment','inv_product_planning_logistics','inv_planning_parameter_audit','inv_planning_logistics_v','inv_planning_parameters_v')]+[('supply_planning','spl_forecast_planning_input')]
            for schema,name in targets:
                entry=objects.get((schema,name))
                if entry:
                    cur.execute(sql.SQL('select count(*) as rows from {}.{}').format(sql.Identifier(schema),sql.Identifier(name)))
                    result['checks'][schema+'.'+name]=dict(cur.fetchone())
                else:result['checks'][schema+'.'+name]={'missing':True}
            for schema in ('inventory','supply_planning'):
                if (schema,'flyway_schema_history') in objects:
                    cur.execute(sql.SQL('select version,description,script,installed_on,success from {}.flyway_schema_history order by installed_rank').format(sql.Identifier(schema)))
                    result['checks'][schema+'.flyway']=[dict(r) for r in cur.fetchall()]
            cur.execute('select count(*) as products from (select product_id from inventory.inv_logistic_variable where active and principal group by 1 having count(*)>1) x')
            result['checks']['logistics_multiple_principal']=dict(cur.fetchone())
            cur.execute("""select c.relname as table_name,a.attname as column_name,
                format_type(a.atttypid,a.atttypmod) as formatted_type,a.attidentity as identity
                from pg_attribute a join pg_class c on c.oid=a.attrelid
                join pg_namespace n on n.oid=c.relnamespace where n.nspname='inventory'
                and c.relname in ('inv_product_site_replenishment','inv_product_planning_logistics','inv_planning_parameter_audit')
                and a.attnum>0 and not a.attisdropped order by 1,a.attnum""")
            result['checks']['exact_types']=[dict(r) for r in cur.fetchall()]
            cur.execute("""select p.proname,p.prosrc from pg_proc p join pg_namespace n on n.oid=p.pronamespace
                where n.nspname='inventory' and p.proname in ('inv_planning_stamp','inv_planning_audit_write','inv_planning_audit_immutable')""")
            result['checks']['planning_functions']=[dict(r) for r in cur.fetchall()]
            cur.execute("""select c.relname,t.tgname,t.tgenabled from pg_trigger t
                join pg_class c on c.oid=t.tgrelid join pg_namespace n on n.oid=c.relnamespace
                where n.nspname='inventory' and not t.tgisinternal""")
            result['checks']['trigger_enabled']=[dict(r) for r in cur.fetchall()]
        dest=Path(__file__).with_name('verificacion_test_20260917.json')
        dest.write_text(json.dumps(result,ensure_ascii=False,indent=2,default=str),encoding='utf-8')
        print(json.dumps({'database':result['database'],'checks':{k:v for k,v in result['checks'].items() if isinstance(v,dict)}},ensure_ascii=False))
    finally:conn.rollback();conn.close()


if __name__=='__main__':
    try:main()
    except psycopg2.Error as exc:
        message=str(exc)
        for suffix in ('PASSWORD','HOST','USER','DB'):
            value=config.get('PGP_TEST_'+suffix)
            if value:message=message.replace(value,'<'+suffix+'>')
        raise SystemExit(message)
