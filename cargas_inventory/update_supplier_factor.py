"""Sincroniza factor oficial SKU/proveedor desde diarco_data a TEST; captura y auditoria local."""
import argparse,json
from pathlib import Path
from datetime import datetime,timezone
from load_test import connect,digest

def run(folder,apply=False):
    if not folder.exists():
        folder.mkdir(parents=True)
        source=connect('PG_',True)
        try:
            with source.cursor() as q:
                q.execute("""SELECT count(*) FROM (SELECT c_articulo,c_proveedor_primario
                    FROM src.base_productos_vigentes GROUP BY 1,2 HAVING c_articulo IS NULL
                    OR c_proveedor_primario IS NULL OR count(distinct q_factor_compra)<>1
                    OR count(*)<>count(q_factor_compra) OR min(q_factor_compra)<=0) x""")
                if q.fetchone()[0]:raise RuntimeError('Invalid or conflicting source factors')
                with (folder/'source.csv').open('w',encoding='utf-8',newline='') as f:
                    q.copy_expert("""COPY (SELECT c_articulo::text product_code,c_proveedor_primario::text supplier_code,
                        min(q_factor_compra) factor FROM src.base_productos_vigentes GROUP BY 1,2)
                        TO STDOUT WITH (FORMAT CSV,HEADER TRUE)""",f)
            (folder/'manifest.json').write_text(json.dumps({'captured_at':datetime.now(timezone.utc).isoformat(),
                'source':'diarco_data.src.base_productos_vigentes','sha256':digest(folder/'source.csv')},indent=2))
        finally:source.rollback();source.close()
    manifest=json.loads((folder/'manifest.json').read_text())
    if digest(folder/'source.csv')!=manifest['sha256']:raise RuntimeError('Checksum mismatch')
    report={'manifest':manifest,'target':'connexa_platform_test','apply':apply}
    c=connect('PGP_TEST_',False)
    try:
        with c.cursor() as q:
            if apply:q.execute('LOCK TABLE inventory.inv_product_supplier IN SHARE ROW EXCLUSIVE MODE')
            q.execute('CREATE TEMP TABLE factors(product_code text,supplier_code text,factor double precision,PRIMARY KEY(product_code,supplier_code)) ON COMMIT DROP')
            with (folder/'source.csv').open(encoding='utf-8',newline='') as f:q.copy_expert('COPY factors FROM STDIN WITH (FORMAT CSV,HEADER TRUE)',f)
            q.execute("""CREATE TEMP TABLE resolved ON COMMIT DROP AS SELECT x.*,ps.id,ps.purchase_factor old_factor
                FROM factors x LEFT JOIN inventory.inv_product p ON p.ext_code=x.product_code
                LEFT JOIN inventory.inv_supplier s ON s.ext_code=x.supplier_code
                LEFT JOIN inventory.inv_product_supplier ps ON ps.product_id=p.id AND ps.supplier_id=s.id""")
            q.execute('SELECT count(*) FROM (SELECT product_code,supplier_code FROM resolved GROUP BY 1,2 HAVING count(*)>1) x')
            if q.fetchone()[0]:raise RuntimeError('Ambiguous target SKU/supplier')
            q.execute('SELECT count(*),count(id),count(*) FILTER(WHERE id IS NOT NULL AND old_factor IS DISTINCT FROM factor) FROM resolved')
            report['source_pairs'],report['matched'],report['to_update']=q.fetchone()
            for name,sql in [('changes','SELECT * FROM resolved WHERE id IS NOT NULL AND old_factor IS DISTINCT FROM factor'),('unmatched','SELECT * FROM resolved WHERE id IS NULL')]:
                with (folder/(name+('.applied' if apply else '.preview')+'.csv')).open('w',encoding='utf-8',newline='') as f:q.copy_expert('COPY ('+sql+') TO STDOUT WITH (FORMAT CSV,HEADER TRUE)',f)
            if apply:
                q.execute('UPDATE inventory.inv_product_supplier ps SET purchase_factor=r.factor FROM resolved r WHERE ps.id=r.id AND ps.purchase_factor IS DISTINCT FROM r.factor')
                report['updated']=q.rowcount
            q.execute('SELECT count(*) FROM resolved r JOIN inventory.inv_product_supplier ps ON ps.id=r.id WHERE ps.purchase_factor IS DISTINCT FROM r.factor')
            report['mismatches']=q.fetchone()[0]
            if apply and report['mismatches']:raise RuntimeError('Verification failed')
        if apply:c.commit()
        else:c.rollback()
        report['status']='COMMITTED' if apply else 'PREVIEW'
        (folder/('result.json' if apply else 'preview.json')).write_text(json.dumps(report,indent=2))
        print(json.dumps(report))
    finally:c.rollback();c.close()

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--directory',type=Path,required=True);p.add_argument('--apply',action='store_true')
    a=p.parse_args();run(a.directory,a.apply)
