"""Completa lead_time_days en TEST para Entrega desde CD, proveedor 0 por sucursal."""
import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from load_test import connect, digest


def extract(folder):
    folder.mkdir(parents=True, exist_ok=False)
    conn=connect('PG_',True)
    try:
        with conn.cursor() as cur:
            cur.execute('SELECT count(*)-count(distinct(c_articulo,c_sucu_empr)) FROM src.base_productos_vigentes')
            if cur.fetchone()[0]:raise RuntimeError('Duplicate product/site source')
            cur.execute('''SELECT count(*) FROM src.t055_lead_time_b2_sucursales WHERE
                c_proveedor IS NULL OR c_sucursal IS NULL OR
                NOT (c_proveedor>=0 AND c_proveedor<1e15 AND c_proveedor=trunc(c_proveedor)) OR
                NOT (c_sucursal>=0 AND c_sucursal<1e15 AND c_sucursal=trunc(c_sucursal))''')
            if cur.fetchone()[0]:raise RuntimeError('Invalid supplier/site codes')
            cur.execute('SELECT count(*)-count(distinct(c_proveedor,c_sucursal)) FROM src.t055_lead_time_b2_sucursales')
            if cur.fetchone()[0]:raise RuntimeError('Duplicate supplier/site lead time')
            with (folder/'source.csv').open('w',encoding='utf-8',newline='') as f:
                cur.copy_expert('''COPY (SELECT p.c_articulo::text product_code,p.c_sucu_empr::text site_code,
                    '0'::text supplier_code,t.dias_entrega::numeric days,
                    CASE WHEN t.c_proveedor IS NULL THEN 'MISSING_LEAD_TIME'
                         WHEN t.dias_entrega IS NULL THEN 'NULL_DAYS'
                         WHEN NOT (t.dias_entrega>=0 AND t.dias_entrega<1000000)
                           OR t.dias_entrega::numeric<>round(t.dias_entrega::numeric,4) THEN 'INVALID_DAYS'
                         ELSE 'READY' END reason
                    FROM src.base_productos_vigentes p LEFT JOIN src.t055_lead_time_b2_sucursales t
                      ON t.c_proveedor=0 AND t.c_sucursal::bigint=p.c_sucu_empr
                    ORDER BY p.c_articulo,p.c_sucu_empr) TO STDOUT WITH (FORMAT CSV, HEADER TRUE)''',f)
        (folder/'manifest.json').write_text(json.dumps({'captured_at':datetime.now(timezone.utc).isoformat(),
            'source':'diarco_data: src.base_productos_vigentes + src.t055_lead_time_b2_sucursales',
            'sha256':digest(folder/'source.csv'),'method':'Entrega desde CD',
            'supplier_rule':'GENERAL_CD_SUPPLIER_0_BY_SITE'},indent=2),encoding='utf-8')
    finally:conn.rollback();conn.close()


def run(folder,apply=False,verify=False):
    manifest=json.loads((folder/'manifest.json').read_text(encoding='utf-8'))
    if manifest.get('supplier_rule')!='GENERAL_CD_SUPPLIER_0_BY_SITE':
        raise RuntimeError('Capture does not implement the confirmed supplier 0 rule; extract a new capture')
    if digest(folder/'source.csv')!=manifest['sha256']:raise RuntimeError('Source checksum mismatch')
    conn=connect('PGP_TEST_',False)
    report={'started_at':datetime.now(timezone.utc).isoformat(),'manifest':manifest,'database':'connexa_platform_test'}
    output=folder/('result.json' if apply else 'verification.json' if verify else 'preview.json')
    committed=False
    try:
        with conn.cursor() as cur:
            if apply:
                cur.execute("SELECT pg_advisory_xact_lock(hashtext('inventory_initial_load_v1'))")
                cur.execute('LOCK TABLE inventory.inv_product_site_replenishment IN SHARE ROW EXCLUSIVE MODE')
                cur.execute("SELECT set_config('app.actor',%s,true)",('ETL:lead_time:'+folder.name,))
            cur.execute('CREATE TEMP TABLE lead_source(product_code text,site_code text,supplier_code text,days numeric,reason text,PRIMARY KEY(product_code,site_code)) ON COMMIT DROP')
            with (folder/'source.csv').open(encoding='utf-8',newline='') as f:
                cur.copy_expert('COPY lead_source FROM STDIN WITH (FORMAT CSV, HEADER TRUE)',f)
            cur.execute('ANALYZE lead_source')
            cur.execute('''CREATE TEMP TABLE lead_resolved ON COMMIT DROP AS
                SELECT r.id,r.lead_time_days previous_days,p.ext_code product_code,s.code site_code,
                    x.supplier_code,x.days,coalesce(x.reason,'MISSING_PRODUCT_SITE_SOURCE') reason
                FROM inventory.inv_product_site_replenishment r
                JOIN inventory.inv_product_site ps ON ps.id=r.product_site_id
                JOIN inventory.inv_product p ON p.id=ps.product_id JOIN inventory.inv_site s ON s.id=ps.site_id
                LEFT JOIN lead_source x ON x.product_code=p.ext_code AND x.site_code=s.code
                WHERE r.replenishment_method='Entrega desde CD' ''')
            cur.execute("SELECT reason,count(*) FROM lead_resolved GROUP BY 1 ORDER BY 1")
            report['by_reason']=dict(cur.fetchall())
            cur.execute("SELECT days,count(*) FROM lead_resolved WHERE reason='READY' GROUP BY 1 ORDER BY 1")
            report['distribution']=[(str(d),n) for d,n in cur.fetchall()]
            cur.execute("SELECT count(*) FROM lead_resolved WHERE reason='READY' AND previous_days IS NOT NULL AND previous_days<>days")
            if cur.fetchone()[0]:raise RuntimeError('Existing lead times conflict; no overwrite performed')
            with (folder/'pending.csv').open('w',encoding='utf-8',newline='') as f:
                cur.copy_expert("COPY (SELECT product_code,site_code,supplier_code,days,reason FROM lead_resolved WHERE reason<>'READY') TO STDOUT WITH (FORMAT CSV, HEADER TRUE)",f)
            cur.execute("SELECT count(*) FROM lead_resolved WHERE reason='READY' AND previous_days IS NULL")
            report['to_complete']=cur.fetchone()[0]
            print(json.dumps(report),flush=True)
            if apply:
                cur.execute("""UPDATE inventory.inv_product_site_replenishment r SET lead_time_days=x.days
                    FROM lead_resolved x WHERE r.id=x.id AND x.reason='READY' AND r.lead_time_days IS NULL
                    AND r.replenishment_method='Entrega desde CD'""")
                report['updated']=cur.rowcount
            cur.execute("""SELECT count(*) FROM lead_resolved x JOIN inventory.inv_product_site_replenishment r ON r.id=x.id
                WHERE x.reason='READY' AND r.lead_time_days IS DISTINCT FROM x.days""")
            report['mismatches']=cur.fetchone()[0]
            if (apply or verify) and report['mismatches']:raise RuntimeError('Lead time verification mismatch')
            cur.execute("SELECT replenishment_method,count(*),count(lead_time_days) FROM inventory.inv_product_site_replenishment GROUP BY 1 ORDER BY 1")
            report['target_counts']=cur.fetchall()
            report['status']='VALIDATED_PENDING_COMMIT' if apply else 'VERIFIED' if verify else 'PREVIEW_OK'
            output.write_text(json.dumps(report,indent=2),encoding='utf-8')
        if apply:conn.commit();committed=True;report['status']='COMMITTED'
        else:conn.rollback()
        report['finished_at']=datetime.now(timezone.utc).isoformat()
        output.write_text(json.dumps(report,indent=2),encoding='utf-8')
        print(json.dumps(report),flush=True)
    except Exception:
        if not committed:conn.rollback()
        report['status']='ERROR_AFTER_COMMIT' if committed else 'FAILED_OR_COMMIT_UNCERTAIN'
        output.write_text(json.dumps(report,indent=2),encoding='utf-8')
        raise
    finally:conn.close()


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory',type=Path,required=True)
    parser.add_argument('--extract',action='store_true')
    mode=parser.add_mutually_exclusive_group()
    mode.add_argument('--apply',action='store_true')
    mode.add_argument('--verify',action='store_true')
    args=parser.parse_args()
    if args.extract:extract(args.directory)
    run(args.directory,args.apply,args.verify)
