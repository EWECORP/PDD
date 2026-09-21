"""Carga inicial reproducible: origen READ ONLY, destino exclusivamente TEST.

Sin --apply solo prepara archivos y consulta destino usando staging TEMP.
--apply reutiliza la captura y agrega filas faltantes, sin pisar ediciones.
"""
import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
import sys

import psycopg2
from psycopg2.extras import RealDictCursor

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'documentacion/parametros_stock'))
from relevar_base import config


def connect(prefix,readonly):
    conn=psycopg2.connect(**{k:config[prefix+v] for k,v in
        [('host','HOST'),('port','PORT'),('dbname','DB'),('user','USER'),('password','PASSWORD')]},
        connect_timeout=15,options='-c statement_timeout=300000 -c lock_timeout=10000')
    conn.set_session(readonly=readonly,isolation_level='REPEATABLE READ')
    with conn.cursor() as cur:
        cur.execute('select current_database()')
        expected='diarco_data' if prefix=='PG_' else 'connexa_platform_test'
        if cur.fetchone()[0]!=expected:
            conn.close();raise RuntimeError('Unexpected database; loading production is disabled')
    return conn


def digest(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda:f.read(1024*1024),b''):h.update(chunk)
    return h.hexdigest()


def extract(folder):
    if folder.exists():raise RuntimeError('Capture directory must be new')
    folder.mkdir(parents=True)
    conn=connect('PG_',True)
    try:
        with conn.cursor() as cur:
            cur.execute('select max(fecha_stock) from src.base_stock_sucursal')
            closing=cur.fetchone()[0]
            if closing is None:raise RuntimeError('No closing stock')
            cur.execute('select count(*)-count(distinct(c_articulo,c_sucu_empr)) from src.base_productos_vigentes')
            if cur.fetchone()[0]:raise RuntimeError('Duplicate product/site in source')
            cur.execute('select count(*)-count(distinct(codigo_articulo,codigo_sucursal)) from src.base_stock_sucursal where fecha_stock=%s',(closing,))
            if cur.fetchone()[0]:raise RuntimeError('Duplicate product/site at closing')
            cur.execute("""select count(*) from src.t050_articulos where c_articulo is null
                or c_articulo::text in ('NaN','Infinity','-Infinity') or c_articulo<>trunc(c_articulo)
                or c_clasificacion_compra is null or c_clasificacion_compra::text in ('NaN','Infinity','-Infinity')
                or c_clasificacion_compra<>trunc(c_clasificacion_compra)""")
            if cur.fetchone()[0]:raise RuntimeError('Invalid article/classification codes in T050')
            queries={
                'replenishment':cur.mogrify("""SELECT p.c_articulo::text product_code,p.c_sucu_empr::text site_code,
                    p.pedido_min::numeric minimum_order_quantity,s.q_dias_stock target_stock_days,
                    s.q_dias_sobre_stock overstock_days,s.dias_preparacion preparation_days,
                    (s.codigo_articulo IS NULL) missing_stock,
                    (s.dias_preparacion IS NULL) missing_preparation
                    FROM src.base_productos_vigentes p LEFT JOIN src.base_stock_sucursal s
                      ON s.codigo_articulo=p.c_articulo AND s.codigo_sucursal=p.c_sucu_empr AND s.fecha_stock=%s
                    ORDER BY p.c_articulo,p.c_sucu_empr""",(closing,)).decode(),
                'classification':"""SELECT DISTINCT c_articulo::bigint::text product_code,
                    c_clasificacion_compra::bigint::text classification_code
                    FROM src.t050_articulos ORDER BY 1,2""",
            }
            for name,query in queries.items():
                print('EXTRACT '+name,flush=True)
                with (folder/(name+'.csv')).open('w',encoding='utf-8',newline='') as out:
                    cur.copy_expert('COPY ('+query+') TO STDOUT WITH (FORMAT CSV, HEADER TRUE)',out)
            manifest={'captured_at':datetime.now(timezone.utc).isoformat(),'source_database':'diarco_data',
                      'source_read_only':True,'stock_closing':str(closing),
                      'sources':['src.base_productos_vigentes','src.base_stock_sucursal','src.t050_articulos'],
                      'sha256':{n:digest(folder/(n+'.csv')) for n in queries}}
            (folder/'manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    finally:conn.rollback();conn.close()


def load(folder,apply):
    manifest=json.loads((folder/'manifest.json').read_text(encoding='utf-8'))
    for name,checksum in manifest['sha256'].items():
        if digest(folder/(name+'.csv'))!=checksum:raise RuntimeError('Capture checksum mismatch')
    report={'started_at':datetime.now(timezone.utc).isoformat(),'target_database':'connexa_platform_test',
            'source_manifest':manifest,'mode':'APPLY' if apply else 'PREVIEW','status':'RUNNING',
            'rules':{'missing_stock_days':0,'null_preparation':0,'existing_stock_null_days':{'target_stock_days':7,'overstock_days':0},
                     'existing_target_rows':'preserve','logistics':'only unique active/principal usable variable'},
            'counts':{}}
    dest=folder/('result.json' if apply else 'preview.json')
    conn=connect('PGP_TEST_',False)
    committed=False
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            if apply:
                cur.execute("SELECT pg_advisory_xact_lock(hashtext('inventory_initial_load_v1'))")
                cur.execute('LOCK TABLE inventory.inv_product_site_replenishment,inventory.inv_product_classification,inventory.inv_product_planning_logistics IN SHARE ROW EXCLUSIVE MODE')
                cur.execute("SELECT set_config('app.actor',%s,true)",('ETL:inventory_initial_load:'+folder.name,))
            cur.execute('''CREATE TEMP TABLE load_replenishment(product_code text,site_code text,minimum_order_quantity numeric,
                target_stock_days numeric,overstock_days numeric,preparation_days numeric,missing_stock boolean,missing_preparation boolean) ON COMMIT DROP;
                CREATE TEMP TABLE load_classification(product_code text,classification_code text) ON COMMIT DROP;''')
            for name in ('replenishment','classification'):
                with (folder/(name+'.csv')).open(encoding='utf-8',newline='') as f:
                    cur.copy_expert('COPY load_'+name+' FROM STDIN WITH (FORMAT CSV, HEADER TRUE)',f)
            cur.execute('ANALYZE load_replenishment; ANALYZE load_classification;')
            cur.execute('SELECT product_code FROM load_classification GROUP BY 1 HAVING count(*)>1 LIMIT 1')
            if cur.fetchone():raise RuntimeError('Multiple purchase classes per product in T050')
            cur.execute("""SELECT t.id,t.value FROM inventory.inv_product_classification_type t
                JOIN inventory.inv_product_classification_value v ON v.classification_type_id=t.id
                GROUP BY t.id,t.value HAVING count(*)=7 AND count(*) FILTER(WHERE v.active AND v.code IN ('1','2','3','4','5','6','100'))=7""")
            candidates=cur.fetchall()
            if len(candidates)!=1:raise RuntimeError('Cannot uniquely resolve purchase classification catalog')
            type_id=str(candidates[0]['id']);report['purchase_classification_type']=dict(candidates[0]);report['purchase_classification_type']['id']=type_id
            cur.execute('''CREATE TEMP TABLE load_resolved ON COMMIT DROP AS SELECT x.*,ps.id AS product_site_id,
                p.id AS product_id,ps.active AS pair_active,
                CASE WHEN x.missing_stock THEN 0 ELSE coalesce(x.target_stock_days,7) END AS resolved_target,
                CASE WHEN x.missing_stock THEN 0 ELSE coalesce(x.overstock_days,0) END AS resolved_overstock,
                coalesce(x.preparation_days,0) AS resolved_preparation
                FROM load_replenishment x LEFT JOIN inventory.inv_product p ON p.ext_code=x.product_code
                LEFT JOIN inventory.inv_site s ON s.code=x.site_code
                LEFT JOIN inventory.inv_product_site ps ON ps.product_id=p.id AND ps.site_id=s.id''')
            cur.execute('''CREATE TEMP TABLE load_ready ON COMMIT DROP AS SELECT * FROM load_resolved
                WHERE product_site_id IS NOT NULL AND resolved_target IS NOT NULL AND resolved_overstock IS NOT NULL''')
            cur.execute("""SELECT count(*) n FROM load_ready WHERE
                NOT (minimum_order_quantity>=0 AND minimum_order_quantity<'Infinity'::numeric)
                OR minimum_order_quantity IS NULL OR minimum_order_quantity<>round(minimum_order_quantity,4)
                OR minimum_order_quantity>=100000000000000
                OR NOT (resolved_target>=0 AND resolved_target<1000000)
                OR NOT (resolved_overstock>=0 AND resolved_overstock<1000000)
                OR NOT (resolved_preparation>=0 AND resolved_preparation<1000000)""")
            if cur.fetchone()['n']:raise RuntimeError('Invalid numeric values or precision in candidate parameters')
            cur.execute('''CREATE TEMP TABLE load_classes ON COMMIT DROP AS SELECT x.*,p.id AS product_id,v.id AS value_id
                FROM load_classification x LEFT JOIN inventory.inv_product p ON p.ext_code=x.product_code
                LEFT JOIN inventory.inv_product_classification_value v ON v.classification_type_id=%s::uuid AND v.code=x.classification_code AND v.active''',(type_id,))
            cur.execute('SELECT count(*) n FROM load_classes WHERE value_id IS NULL')
            if cur.fetchone()['n']:raise RuntimeError('T050 contains codes outside purchase catalog')
            cur.execute('''CREATE TEMP TABLE load_logistics ON COMMIT DROP AS
                SELECT v.product_id,min(v.id::text)::uuid AS logistic_variable_id FROM inventory.inv_logistic_variable v
                WHERE v.active AND v.principal AND v.product_id IN (SELECT product_id FROM load_ready UNION SELECT product_id FROM load_classes WHERE product_id IS NOT NULL)
                GROUP BY v.product_id HAVING count(*)=1
                AND bool_and((v.purchase_factor>0 AND v.purchase_factor<'Infinity'::float8
                  AND v.uom_id IS NOT NULL AND btrim(v.uom_id)<>''
                  AND (v.uom_id='unidad' OR (v.weight_in_gr>0 AND v.weight_in_gr<'Infinity'::float8))) IS TRUE)''')
            cur.execute('''CREATE TEMP TABLE load_logistics_pending ON COMMIT DROP AS
                SELECT p.id product_id,p.ext_code product_code,count(v.id) active_principal_candidates
                FROM inventory.inv_product p LEFT JOIN inventory.inv_logistic_variable v
                  ON v.product_id=p.id AND v.active AND v.principal
                WHERE p.id IN (SELECT product_id FROM load_ready UNION SELECT product_id FROM load_classes WHERE product_id IS NOT NULL)
                  AND NOT EXISTS (SELECT 1 FROM load_logistics l WHERE l.product_id=p.id)
                GROUP BY p.id,p.ext_code''')
            metrics={
                'replenishment_source':'SELECT count(*) n FROM load_resolved',
                'unmapped_pairs':'SELECT count(*) n FROM load_resolved WHERE product_site_id IS NULL',
                'existing_stock_null_days_excluded':'SELECT count(*) n FROM load_resolved WHERE product_site_id IS NOT NULL AND (resolved_target IS NULL OR resolved_overstock IS NULL)',
                'replenishment_ready':'SELECT count(*) n FROM load_ready',
                'target_null_default_7':'SELECT count(*) n FROM load_ready WHERE NOT missing_stock AND target_stock_days IS NULL',
                'overstock_null_default_0':'SELECT count(*) n FROM load_ready WHERE NOT missing_stock AND overstock_days IS NULL',
                'missing_stock_zero':'SELECT count(*) n FROM load_ready WHERE missing_stock',
                'null_preparation_zero':'SELECT count(*) n FROM load_ready WHERE missing_preparation',
                'inactive_inventory_pairs':'SELECT count(*) n FROM load_ready WHERE NOT pair_active',
                'classification_source':'SELECT count(*) n FROM load_classes',
                'classification_missing_product':'SELECT count(*) n FROM load_classes WHERE product_id IS NULL',
                'classification_ready':'SELECT count(*) n FROM load_classes WHERE product_id IS NOT NULL',
                'logistic_unique_usable':'SELECT count(*) n FROM load_logistics',
                'logistic_pending':'SELECT count(*) n FROM load_logistics_pending',
            }
            for key,q in metrics.items():cur.execute(q);report['counts'][key]=cur.fetchone()['n']
            print(json.dumps(report['counts']),flush=True)
            for name,q in {
                'unmapped_pairs':'SELECT product_code,site_code FROM load_resolved WHERE product_site_id IS NULL',
                'missing_days':'SELECT product_code,site_code,target_stock_days,overstock_days FROM load_resolved WHERE product_site_id IS NOT NULL AND (resolved_target IS NULL OR resolved_overstock IS NULL)',
                'unmapped_classification_products':'SELECT product_code,classification_code FROM load_classes WHERE product_id IS NULL',
                'pending_logistics':'SELECT * FROM load_logistics_pending',
            }.items():
                with (folder/(name+'.csv')).open('w',encoding='utf-8',newline='') as out:cur.copy_expert('COPY ('+q+') TO STDOUT WITH (FORMAT CSV, HEADER TRUE)',out)
            if apply:
                statements={
                    'replenishment_inserted':'''INSERT INTO inventory.inv_product_site_replenishment(product_site_id,target_stock_days,overstock_days,minimum_order_quantity,preparation_days,active)
                        SELECT product_site_id,resolved_target,resolved_overstock,minimum_order_quantity,resolved_preparation,pair_active
                        FROM load_ready x WHERE NOT EXISTS (SELECT 1 FROM inventory.inv_product_site_replenishment r WHERE r.product_site_id=x.product_site_id) ON CONFLICT(product_site_id) DO NOTHING''',
                    'classification_inserted':cur.mogrify('''INSERT INTO inventory.inv_product_classification(product_id,classification_type_id,classification_value_id,valid_from,active)
                        SELECT x.product_id,%s::uuid,x.value_id,CURRENT_DATE,true FROM load_classes x WHERE x.product_id IS NOT NULL
                        AND NOT EXISTS (SELECT 1 FROM inventory.inv_product_classification c WHERE c.product_id=x.product_id AND c.classification_type_id=%s::uuid AND c.active)''',(type_id,type_id)).decode(),
                    'logistics_inserted':'''INSERT INTO inventory.inv_product_planning_logistics(product_id,logistic_variable_id)
                        SELECT product_id,logistic_variable_id FROM load_logistics ON CONFLICT(product_id) DO NOTHING''',
                }
                for name,q in statements.items():
                    print('INSERT '+name,flush=True);cur.execute(q);report['counts'][name]=cur.rowcount
                cur.execute('''SELECT count(*) n FROM load_ready x LEFT JOIN inventory.inv_product_site_replenishment r ON r.product_site_id=x.product_site_id WHERE r.id IS NULL''')
                if cur.fetchone()['n']:raise RuntimeError('Missing target rows before commit')
                for table in ('inv_product_site_replenishment','inv_product_classification','inv_product_planning_logistics','inv_planning_parameter_audit'):
                    cur.execute('SELECT count(*) n FROM inventory.'+table);report['counts']['final_'+table]=cur.fetchone()['n']
            report['status']='VALIDATED_PENDING_COMMIT' if apply else 'PREVIEW_OK'
            dest.write_text(json.dumps(report,indent=2,default=str),encoding='utf-8')
        if apply:conn.commit();committed=True;report['status']='COMMITTED'
        else:conn.rollback()
        report['finished_at']=datetime.now(timezone.utc).isoformat()
        dest.write_text(json.dumps(report,indent=2,default=str),encoding='utf-8')
        print(json.dumps({'status':report['status'],'counts':report['counts']}),flush=True)
    except Exception:
        if not committed:conn.rollback()
        report['status']='ERROR_AFTER_COMMIT' if committed else 'FAILED_OR_COMMIT_UNCERTAIN'
        dest.write_text(json.dumps(report,indent=2,default=str),encoding='utf-8')
        raise
    finally:conn.close()


if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--directory',type=Path,required=True)
    ap.add_argument('--extract',action='store_true')
    ap.add_argument('--apply',action='store_true')
    args=ap.parse_args()
    try:
        if args.extract:extract(args.directory)
        load(args.directory,args.apply)
    except psycopg2.Error as exc:
        msg=str(exc)
        for prefix in ('PG_','PGP_TEST_'):
            for suffix in ('PASSWORD','HOST','USER','DB'):
                if config.get(prefix+suffix):msg=msg.replace(config[prefix+suffix],'<'+suffix+'>')
        raise SystemExit(msg)
