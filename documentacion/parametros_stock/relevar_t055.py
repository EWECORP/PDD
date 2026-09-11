"""Relevamiento de la fuente canónica legacy; sólo lectura."""
import json
from pathlib import Path
from datetime import datetime, timezone
import psycopg2
from psycopg2.extras import RealDictCursor
from dotenv import dotenv_values

ROOT=Path(__file__).resolve().parents[2]
cfg=dotenv_values(ROOT/'backend/.env')

def main():
    if cfg['PG_DB'] != 'diarco_data':
        raise SystemExit('Se requiere PG_DB=diarco_data')
    conn=psycopg2.connect(**{k:cfg['PG_'+v] for k,v in [('host','HOST'),('port','PORT'),('dbname','DB'),('user','USER'),('password','PASSWORD')]},connect_timeout=15,options='-c default_transaction_read_only=on -c statement_timeout=60000')
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("select column_name,data_type from information_schema.columns where table_schema='src' and table_name in ('t055_articulos_param_stock') order by ordinal_position")
            columns=[dict(r) for r in cur.fetchall()]
            cur.execute('select * from src.t055_articulos_param_stock')
            rows=[dict(r) for r in cur.fetchall()]
            cur.execute("select table_name,column_name from information_schema.columns where table_schema='src' and table_name in ('t050_articulos','base_stock_sucursal') and (column_name like '%clas%' or column_name like '%famil%' or column_name like '%rubro%' or column_name like '%articulo%')")
            mapping_columns=[dict(r) for r in cur.fetchall()]
    finally:
        conn.rollback(); conn.close()
    result={'captured_at':datetime.now(timezone.utc).isoformat(),'columns':columns,'rows':rows}
    Path(__file__).with_name('t055_snapshot.json').write_text(json.dumps(result,ensure_ascii=False,indent=2,default=str),encoding='utf-8')
    print(json.dumps({'columns':columns,'rows':len(rows),'mapping_columns':mapping_columns},default=str,ensure_ascii=False))

if __name__=='__main__':
    try: main()
    except psycopg2.Error as exc:
        message=str(exc)
        for suffix in ('PASSWORD','HOST','USER','DB'):
            if cfg.get('PG_'+suffix): message=message.replace(cfg['PG_'+suffix],'<'+suffix+'>')
        raise SystemExit(message)
