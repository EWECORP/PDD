"""Inspección de metadatos de las fuentes indicadas, sin cargar reposición."""
import json
from pathlib import Path
from datetime import datetime, timezone
import psycopg2
from psycopg2.extras import RealDictCursor
from relevar_base import config

def main():
    conn=psycopg2.connect(**{k:config['PG_'+v] for k,v in
        [('host','HOST'),('port','PORT'),('dbname','DB'),('user','USER'),('password','PASSWORD')]},
        connect_timeout=15,options='-c default_transaction_read_only=on -c statement_timeout=45000')
    result={'captured_at':datetime.now(timezone.utc).isoformat()}
    try:
        conn.set_session(readonly=True,isolation_level='REPEATABLE READ')
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("select current_database() as database,current_setting('transaction_read_only') as read_only")
            result['database']=dict(cur.fetchone())
            if result['database']['database']!='diarco_data':raise RuntimeError('Unexpected source database')
            cur.execute("""select table_schema,table_name,column_name,data_type from information_schema.columns
                where table_name in ('base_productos_vigentes','base_stock_sucursal','src_base_productos_vigentes','src_base_stock_sucursal')
                order by table_schema,table_name,ordinal_position""")
            result['columns']=[dict(r) for r in cur.fetchall()]
            result['quality']={}
            for name,query in {
                'products': """select count(*) as rows,count(distinct(c_articulo,c_sucu_empr)) as pairs,
                    min(fecha_extraccion) as min_extraction,max(fecha_extraccion) as max_extraction,
                    count(*) filter(where pedido_min is null) as null_minimum,
                    count(*) filter(where pedido_min<0 or pedido_min::text in ('NaN','Infinity','-Infinity')) as invalid_minimum
                    from src.base_productos_vigentes""",
                'stock_latest': """select max(fecha_stock) as latest_stock from src.base_stock_sucursal""",
                'stock_latest_quality': """with latest as (select max(fecha_stock) as dt from src.base_stock_sucursal)
                    select count(*) as rows,count(distinct(codigo_articulo,codigo_sucursal)) as pairs,
                    count(*) filter(where q_dias_stock is null or q_dias_sobre_stock is null or dias_preparacion is null) as missing_required_days,
                    count(*) filter(where q_dias_stock<0 or q_dias_sobre_stock<0 or dias_preparacion<0) as negative_days,
                    min(fecha_extraccion) as min_extraction,max(fecha_extraccion) as max_extraction
                    from src.base_stock_sucursal s join latest l on s.fecha_stock=l.dt""",
                'source_join': """with latest as (select max(fecha_stock) as dt from src.base_stock_sucursal),
                    p as (select c_articulo,c_sucu_empr,count(*) as variants from src.base_productos_vigentes group by 1,2),
                    s as (select codigo_articulo,codigo_sucursal,count(*) as variants from src.base_stock_sucursal
                        where fecha_stock=(select dt from latest) group by 1,2)
                    select count(*) as product_pairs,
                        count(*) filter(where s.codigo_articulo is null) as pairs_without_latest_stock,
                        count(*) filter(where p.variants>1) as duplicated_product_pairs,
                        count(*) filter(where s.variants>1) as duplicated_latest_stock_pairs
                    from p left join s on s.codigo_articulo=p.c_articulo and s.codigo_sucursal=p.c_sucu_empr""",
                'matched_required_fields': """with latest as (select max(fecha_stock) as dt from src.base_stock_sucursal)
                    select (p.habilitado=1 and p.active_for_purchase=1) is true as legacy_purchase_enabled,
                        count(*) as product_pairs,
                        count(*) filter(where s.codigo_articulo is null) as without_stock,
                        count(*) filter(where s.codigo_articulo is not null and s.q_dias_stock is null) as null_target,
                        count(*) filter(where s.codigo_articulo is not null and s.q_dias_sobre_stock is null) as null_overstock,
                        count(*) filter(where s.codigo_articulo is not null and s.dias_preparacion is null) as null_preparation,
                        count(*) filter(where s.q_dias_stock is not null and s.q_dias_sobre_stock is not null and s.dias_preparacion is not null) as complete_parameters
                    from src.base_productos_vigentes p left join src.base_stock_sucursal s
                      on s.codigo_articulo=p.c_articulo and s.codigo_sucursal=p.c_sucu_empr and s.fecha_stock=(select dt from latest)
                    group by 1 order by 1""",
            }.items():
                cur.execute(query);result['quality'][name]=[dict(r) for r in cur.fetchall()]
        Path(__file__).with_name('fuentes_reposicion_20260917.json').write_text(json.dumps(result,ensure_ascii=False,indent=2,default=str),encoding='utf-8')
        print(json.dumps({'database':result['database'],'quality':result['quality']},ensure_ascii=False,default=str))
    finally:conn.rollback();conn.close()

if __name__=='__main__':
    try:main()
    except psycopg2.Error as exc:
        message=str(exc)
        for suffix in ('PASSWORD','HOST','USER','DB'):
            value=config.get('PG_'+suffix)
            if value:message=message.replace(value,'<'+suffix+'>')
        raise SystemExit(message)
