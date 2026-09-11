"""Relevamiento de catálogo de PGP_TEST_DB; conexión exclusivamente de lectura."""
import json
from pathlib import Path
from datetime import datetime, timezone
import psycopg2
from psycopg2.extras import RealDictCursor
from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[2]
config = dotenv_values(ROOT / 'backend' / '.env')
queries = {
    'cluster_membership_quality': """select count(*) as rows,count(distinct site_id) as sites,
        count(*) filter(where supply_cluster_id is null) as without_cluster from supply_planning.spl_supply_site""",
    'conflicting_policy_keys': """select count(*) as keys_with_different_days from
        (select supply_cluster_id,category_id from supply_planning.spl_supply_cluster_category
        group by 1,2 having count(distinct (stock_days,stock_days_limit))>1) x""",
    'site_multiple_clusters': """select count(*) as sites_in_multiple_clusters from
        (select site_id from supply_planning.spl_supply_site group by 1 having count(distinct supply_cluster_id)>1) x""",
    'policy_counts': """select 'inventory.inv_product_site_replenishment' as object, count(*) as rows from inventory.inv_product_site_replenishment
        union all select 'inventory.inv_product_classification',count(*) from inventory.inv_product_classification
        union all select 'supply_planning.spl_supply_cluster',count(*) from supply_planning.spl_supply_cluster
        union all select 'supply_planning.spl_supply_cluster_category',count(*) from supply_planning.spl_supply_cluster_category
        union all select 'supply_planning.spl_supply_site',count(*) from supply_planning.spl_supply_site""",
    'policy_quality': """select count(*) as rows, min(stock_days) as min_days,max(stock_days) as max_days,
        min(stock_days_limit) as min_limit,max(stock_days_limit) as max_limit,
        count(*) filter(where stock_days_limit is null) as null_limits,
        count(*) filter(where stock_days<0 or stock_days_limit<0) as negative_values,
        count(*) filter(where stock_days_limit<stock_days) as limit_below_stock
        from supply_planning.spl_supply_cluster_category""",
    'policy_duplicates': """select count(*) as duplicated_keys from
        (select supply_cluster_id,category_id from supply_planning.spl_supply_cluster_category
        group by 1,2 having count(*)>1) x""",
    'classification_types': 'select value from inventory.inv_product_classification_type order by value',
    'foreign_tables': """select n.nspname as schema,c.relname as name,s.srvname as server
        from pg_foreign_table f join pg_class c on c.oid=f.ftrelid
        join pg_namespace n on n.oid=c.relnamespace join pg_foreign_server s on s.oid=f.ftserver
        order by 1,2""",
    'triggers': """select n.nspname as schema,c.relname as table_name,t.tgname as name,pg_get_triggerdef(t.oid) as definition
        from pg_trigger t join pg_class c on c.oid=t.tgrelid join pg_namespace n on n.oid=c.relnamespace
        where not t.tgisinternal and n.nspname not in ('pg_catalog','information_schema') order by 1,2,3""",
    'database': "select current_database() as database, current_setting('server_version') as version",
    'tables': """select n.nspname as schema, c.relname as name, c.relkind as kind,
        c.reltuples::bigint as estimated_rows, obj_description(c.oid) as comment
        from pg_class c join pg_namespace n on n.oid=c.relnamespace
        where n.nspname not in ('pg_catalog','information_schema')
        and n.nspname not like 'pg_toast%' and c.relkind in ('r','p','v','m','f') order by 1,2""",
    'columns': """select table_schema,table_name,column_name,ordinal_position,data_type,
        udt_name,is_nullable,column_default from information_schema.columns
        where table_schema not in ('pg_catalog','information_schema') order by 1,2,4""",
    'constraints': """select n.nspname as schema,c.relname as table_name, con.conname as name,
        con.contype as type,pg_get_constraintdef(con.oid) as definition
        from pg_constraint con join pg_class c on c.oid=con.conrelid
        join pg_namespace n on n.oid=c.relnamespace
        where n.nspname not in ('pg_catalog','information_schema') order by 1,2,3""",
    'indexes': "select schemaname,tablename,indexname,indexdef from pg_indexes where schemaname not in ('pg_catalog','information_schema') order by 1,2,3",
    'views': "select schemaname,viewname,definition from pg_views where schemaname not in ('pg_catalog','information_schema') order by 1,2",
}

def main():
    conn = psycopg2.connect(**{k:config['PGP_TEST_'+v] for k,v in
        [('host','HOST'),('port','PORT'),('dbname','DB'),('user','USER'),('password','PASSWORD')]},
        connect_timeout=15,options='-c default_transaction_read_only=on -c statement_timeout=60000')
    result = {'captured_at': datetime.now(timezone.utc).isoformat()}
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            for key, query in queries.items():
                cur.execute(query)
                result[key] = [dict(row) for row in cur.fetchall()]
        dest = Path(__file__).with_name('catalogo_pgp_test.json')
        dest.write_text(json.dumps(result, ensure_ascii=False, indent=2, default=str), encoding='utf-8')
        print(json.dumps({k:len(v) for k,v in result.items() if isinstance(v,list)}))
    finally:
        conn.rollback()
        conn.close()

if __name__ == '__main__':
    try:
        main()
    except psycopg2.Error as exc:
        message = str(exc)
        for suffix in ('PASSWORD', 'HOST', 'USER', 'DB'):
            value = config.get('PGP_TEST_' + suffix)
            if value:
                message = message.replace(value, '<' + suffix + '>')
        raise SystemExit(message)
