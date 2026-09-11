import json
from pathlib import Path
import psycopg2
from psycopg2.extras import RealDictCursor
from relevar_base import config

def main():
    conn=psycopg2.connect(**{k:config['PGP_TEST_'+v] for k,v in [('host','HOST'),('port','PORT'),('dbname','DB'),('user','USER'),('password','PASSWORD')]},connect_timeout=15,options='-c default_transaction_read_only=on -c statement_timeout=60000')
    result={}
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            for name,sql in {
                'sites':'select id,code,type from supply_planning.spl_site order by code',
                'categories':'select id,ext_code,name,parent_id,category_type_code from supply_planning.spl_category order by ext_code',
            }.items():
                cur.execute(sql); result[name]=[dict(r) for r in cur.fetchall()]
    finally: conn.rollback(); conn.close()
    Path(__file__).with_name('maestros_test.json').write_text(json.dumps(result,ensure_ascii=False,indent=2,default=str),encoding='utf-8')
    print(json.dumps({'sites':len(result['sites']),'categories':len(result['categories']),'candidate_categories':[r for r in result['categories'] if r['ext_code'] in ('2','7','8','10','2-2528')]},ensure_ascii=False,default=str))

if __name__=='__main__':
    try: main()
    except psycopg2.Error as exc:
        msg=str(exc)
        for suffix in ('PASSWORD','HOST','USER','DB'):
            if config.get('PGP_TEST_'+suffix): msg=msg.replace(config['PGP_TEST_'+suffix],'<'+suffix+'>')
        raise SystemExit(msg)
