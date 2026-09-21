"""Completa replenishment_method en TEST desde una captura verificable de abastecimiento."""
import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from load_test import connect, digest

METHODS = {0: 'Entrega desde CD', 1: 'Entrega Desde el Proveedor',
           2: 'Cross Doking', 3: 'Entrega desde QX'}


def extract(folder):
    folder.mkdir(parents=True, exist_ok=False)
    conn = connect('PG_', True)
    try:
        with conn.cursor() as cur:
            cur.execute('SELECT count(*)-count(distinct(c_articulo,c_sucu_empr)) FROM src.base_productos_vigentes')
            if cur.fetchone()[0]:
                raise RuntimeError('Duplicate source pairs')
            cur.execute('SELECT count(*) FROM src.base_productos_vigentes WHERE abastecimiento IS NULL OR abastecimiento NOT IN (0,1,2,3) OR c_articulo IS NULL OR c_sucu_empr IS NULL')
            if cur.fetchone()[0]:
                raise RuntimeError('Invalid source codes')
            with (folder/'source.csv').open('w', encoding='utf-8', newline='') as f:
                cur.copy_expert('''COPY (SELECT c_sucu_empr::text site_code,c_articulo::text product_code,
                    c_proveedor_primario::text primary_supplier_code,abastecimiento
                    FROM src.base_productos_vigentes ORDER BY c_sucu_empr,c_articulo)
                    TO STDOUT WITH (FORMAT CSV, HEADER TRUE)''', f)
        manifest={'captured_at':datetime.now(timezone.utc).isoformat(),
                  'source':'diarco_data.src.base_productos_vigentes',
                  'sha256':digest(folder/'source.csv'),'mapping':METHODS}
        (folder/'manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    finally:
        conn.rollback();conn.close()


def run(folder, apply=False, verify=False):
    manifest=json.loads((folder/'manifest.json').read_text(encoding='utf-8'))
    if digest(folder/'source.csv')!=manifest['sha256']:
        raise RuntimeError('Source checksum mismatch')
    conn=connect('PGP_TEST_',False)
    report={'started_at':datetime.now(timezone.utc).isoformat(),'database':'connexa_platform_test',
            'manifest':manifest,'status':'RUNNING'}
    output=folder/('verification.json' if verify else 'result.json' if apply else 'preview.json')
    committed=False
    try:
        with conn.cursor() as cur:
            if apply:
                cur.execute("SELECT pg_advisory_xact_lock(hashtext('inventory_initial_load_v1'))")
                cur.execute('LOCK TABLE inventory.inv_product_site_replenishment IN SHARE ROW EXCLUSIVE MODE')
                cur.execute("SELECT set_config('app.actor',%s,true)",('ETL:replenishment_method:'+folder.name,))
            cur.execute('CREATE TEMP TABLE method_source(site_code text,product_code text,primary_supplier_code text,code integer) ON COMMIT DROP')
            with (folder/'source.csv').open(encoding='utf-8',newline='') as f:
                cur.copy_expert('COPY method_source FROM STDIN WITH (FORMAT CSV, HEADER TRUE)',f)
            cur.execute('CREATE TEMP TABLE method_map(code integer PRIMARY KEY,method text NOT NULL) ON COMMIT DROP')
            cur.executemany('INSERT INTO method_map VALUES (%s,%s)',list(METHODS.items()))
            cur.execute('SELECT count(*) FROM method_source WHERE code IS NULL OR code NOT IN (0,1,2,3)')
            if cur.fetchone()[0]:raise RuntimeError('Unknown supply code')
            cur.execute('ANALYZE method_source')
            cur.execute('''CREATE TEMP TABLE method_resolved ON COMMIT DROP AS
                SELECT x.*,m.method,r.id target_id,r.replenishment_method previous_method
                FROM method_source x JOIN method_map m ON m.code=x.code
                LEFT JOIN inventory.inv_product p ON p.ext_code=x.product_code
                LEFT JOIN inventory.inv_site s ON s.code=x.site_code
                LEFT JOIN inventory.inv_product_site ps ON ps.product_id=p.id AND ps.site_id=s.id
                LEFT JOIN inventory.inv_product_site_replenishment r ON r.product_site_id=ps.id''')
            cur.execute('SELECT count(*) FROM method_resolved WHERE target_id IS NOT NULL AND previous_method IS NOT NULL AND previous_method<>method')
            if cur.fetchone()[0]:raise RuntimeError('Existing methods conflict with source; no overwrite performed')
            cur.execute('SELECT count(*),count(target_id),count(*) FILTER(WHERE target_id IS NOT NULL AND previous_method IS NULL) FROM method_resolved')
            report['source_rows'],report['matched'],report['missing_methods']=cur.fetchone()
            cur.execute('SELECT code,method,count(*) FROM method_resolved WHERE target_id IS NOT NULL GROUP BY 1,2 ORDER BY 1')
            report['distribution']=cur.fetchall()
            with (folder/'unmatched.csv').open('w',encoding='utf-8',newline='') as f:
                cur.copy_expert('COPY (SELECT site_code,product_code,code FROM method_resolved WHERE target_id IS NULL) TO STDOUT WITH (FORMAT CSV, HEADER TRUE)',f)
            print(json.dumps(report),flush=True)
            if apply:
                cur.execute('''UPDATE inventory.inv_product_site_replenishment r SET replenishment_method=x.method
                    FROM method_resolved x WHERE r.id=x.target_id AND r.replenishment_method IS NULL''')
                report['updated']=cur.rowcount
            cur.execute('''SELECT count(*) FROM method_resolved x JOIN inventory.inv_product_site_replenishment r
                ON r.id=x.target_id WHERE r.replenishment_method IS DISTINCT FROM x.method''')
            report['mismatches']=cur.fetchone()[0]
            if (apply or verify) and report['mismatches']:raise RuntimeError('Verification mismatch')
            report['status']='VALIDATED_PENDING_COMMIT' if apply else 'VERIFIED' if verify else 'PREVIEW_OK'
            output.write_text(json.dumps(report,indent=2),encoding='utf-8')
        if apply:
            conn.commit();committed=True;report['status']='COMMITTED'
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
