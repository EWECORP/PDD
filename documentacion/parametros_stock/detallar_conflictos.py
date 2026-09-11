"""Consulta exclusivamente de lectura de reglas conflictivas en TEST."""
import json
from datetime import datetime, timezone
from pathlib import Path
import psycopg2
from psycopg2.extras import RealDictCursor
from relevar_base import config

SQL = """
WITH conflicts AS (
 SELECT supply_cluster_id, category_id
 FROM supply_planning.spl_supply_cluster_category
 GROUP BY 1,2
 HAVING count(DISTINCT (stock_days,stock_days_limit)) > 1
)
SELECT g.id AS cluster_id, g.name AS cluster_name,
 c.id AS category_id,c.ext_code AS category_code,c.name AS category_name,
 r.id AS rule_id,r.stock_days,r.stock_days_limit,r.timestamp
FROM conflicts x
JOIN supply_planning.spl_supply_cluster_category r
 USING(supply_cluster_id,category_id)
JOIN supply_planning.spl_supply_cluster g ON g.id=r.supply_cluster_id
JOIN supply_planning.spl_category c ON c.id=r.category_id
ORDER BY g.name,c.ext_code,c.name,r.stock_days,r.id
"""

def main():
    conn = psycopg2.connect(**{k:config['PGP_TEST_'+v] for k,v in
        [('host','HOST'),('port','PORT'),('dbname','DB'),('user','USER'),('password','PASSWORD')]},
        connect_timeout=15,options='-c default_transaction_read_only=on -c statement_timeout=60000')
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(SQL)
            rows=[dict(row) for row in cur.fetchall()]
    finally:
        conn.rollback()
        conn.close()
    root=Path(__file__).parent
    captured=datetime.now(timezone.utc).isoformat()
    (root/'conflictos_test.json').write_text(json.dumps({'captured_at':captured,'rows':rows},ensure_ascii=False,indent=2,default=str),encoding='utf-8')
    groups={}
    for row in rows:
        groups.setdefault((row['cluster_id'],row['category_id']),[]).append(row)
    lines=['# Combinaciones conflictivas de stock en TEST','',f'Captura UTC: {captured}. Consulta de solo lectura en `connexa_platform_test`.','',
           'Conflicto: una misma clave grupo/categoría tiene más de un par distinto `(stock_days, stock_days_limit)`. No se modificó ninguna regla.','',
           '| Grupo | Código categoría | Categoría | Días de stock distintos | Límites distintos | Filas |','|---|---|---|---|---|---:|']
    for items in groups.values():
        r=items[0]
        cells=[r['cluster_name'],r['category_code'],r['category_name'],', '.join(map(str,sorted(set(x['stock_days'] for x in items)))),', '.join(sorted(set(str(x['stock_days_limit']) for x in items))),len(items)]
        lines.append('| '+' | '.join(str(x).replace('|','\\|') for x in cells)+' |')
    lines+=['',f'Total: {len(groups)} combinaciones, {len(rows)} filas.','',
            'El límite no se interpreta como sobrestock: su semántica está pendiente de confirmar. Los IDs y timestamps de todas las filas se conservan en [conflictos_test.json](conflictos_test.json).','',
            'La consulta reproducible se encuentra en [detallar_conflictos.py](detallar_conflictos.py). No se infiere una regla ganadora a partir del timestamp.']
    report='\n'.join(lines)+'\n'
    (root/'05_combinaciones_conflictivas.md').write_text(report,encoding='utf-8')
    print(report)

if __name__=='__main__':
    try:
        main()
    except psycopg2.Error as exc:
        message=str(exc)
        for suffix in ('PASSWORD','HOST','USER','DB'):
            value=config.get('PGP_TEST_'+suffix)
            if value:
                message=message.replace(value,'<'+suffix+'>')
        raise SystemExit(message)
