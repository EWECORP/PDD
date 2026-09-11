"""Compara cobertura y días de T055 contra última fecha de stock, sólo lectura."""
import json
from pathlib import Path
import psycopg2
from psycopg2.extras import RealDictCursor
from relevar_t055 import cfg

SQL="""
WITH last_date AS (SELECT max(fecha_stock::date) d FROM src.base_stock_sucursal),
stock AS (
 SELECT DISTINCT ON (codigo_sucursal,codigo_articulo)
 codigo_sucursal,codigo_articulo,q_dias_stock,q_dias_sobre_stock
 FROM src.base_stock_sucursal,last_date WHERE fecha_stock::date=d
 ORDER BY codigo_sucursal,codigo_articulo,fecha_extraccion DESC NULLS LAST
), articles AS (
 SELECT c_articulo,min(c_familia) family,min(c_rubro) category,min(c_clasificacion_compra) classification,
 count(DISTINCT (c_familia,c_rubro,c_clasificacion_compra)) variants
 FROM src.t050_articulos GROUP BY c_articulo
), compared AS (
 SELECT s.*, a.variants, p.q_dias_stock target_days,p.q_dias_sobre_stock overstock_days,
 p.c_sucu_empr matched_site
 FROM stock s LEFT JOIN articles a ON a.c_articulo=s.codigo_articulo
 LEFT JOIN LATERAL (
 SELECT p.* FROM src.t055_articulos_param_stock p
 WHERE p.c_sucu_empr=s.codigo_sucursal AND p.c_familia=a.family
 AND p.c_claisificacion_compra=a.classification AND (p.c_rubro=0 OR p.c_rubro=a.category)
 ORDER BY (p.c_rubro<>0) DESC LIMIT 1
 ) p ON a.variants=1
)
SELECT (SELECT d FROM last_date) stock_date,count(*) total_pairs,
 count(*) FILTER(WHERE variants IS NULL) missing_article,
 count(*) FILTER(WHERE variants>1) ambiguous_article,
 count(*) FILTER(WHERE matched_site IS NOT NULL) covered_pairs,
 count(*) FILTER(WHERE matched_site IS NULL) uncovered_pairs,
 count(*) FILTER(WHERE matched_site IS NOT NULL AND
 (q_dias_stock,q_dias_sobre_stock) IS DISTINCT FROM (target_days,overstock_days)) different_pairs,
 count(*) FILTER(WHERE matched_site IS NOT NULL AND
 (q_dias_stock,q_dias_sobre_stock) IS NOT DISTINCT FROM (target_days,overstock_days)) equal_pairs
FROM compared
"""
def main():
    if cfg['PG_DB']!='diarco_data':raise SystemExit('Solo diarco_data')
    conn=psycopg2.connect(**{k:cfg['PG_'+v] for k,v in [('host','HOST'),('port','PORT'),('dbname','DB'),('user','USER'),('password','PASSWORD')]},connect_timeout=15,options='-c default_transaction_read_only=on -c statement_timeout=60000')
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(SQL); result=dict(cur.fetchone())
    finally:conn.rollback();conn.close()
    Path(__file__).with_name('comparacion_t055_stock.json').write_text(json.dumps(result,indent=2,default=str),encoding='utf-8')
    print(json.dumps(result,default=str))
if __name__=='__main__':
    try: main()
    except psycopg2.Error as exc:
        msg=str(exc)
        for suffix in ('PASSWORD','HOST','USER','DB'):
            if cfg.get('PG_'+suffix):msg=msg.replace(cfg['PG_'+suffix],'<'+suffix+'>')
        raise SystemExit(msg)
