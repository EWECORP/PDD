"""Genera SQL transaccional de borrador desde snapshots revisados, sin conectarse."""
import hashlib
import json
from pathlib import Path
from uuid import uuid4
from collections import defaultdict
from decimal import Decimal

ROOT=Path(__file__).parent
def literal(value):
    if value is None: return 'NULL'
    return "'"+str(value).replace("'","''")+"'"

def main():
    snapshot=(ROOT/'t055_snapshot.json').read_bytes()
    rows=json.loads(snapshot)['rows']
    masters=json.loads((ROOT/'maestros_test.json').read_text(encoding='utf-8'))
    sites=defaultdict(list)
    for s in masters['sites']:
        try: sites[int(s['code'])].append(s['id'])
        except (ValueError,TypeError): pass
    cats={r['ext_code']:r for r in masters['categories']}
    version=str(uuid4())
    sql=['BEGIN;',"DO $$ BEGIN IF current_database() <> 'connexa_platform_test' THEN RAISE EXCEPTION 'Solo TEST'; END IF; END $$;", "SET LOCAL lock_timeout='5s';", "SET LOCAL statement_timeout='60s';"]
    sql.append((ROOT.parents[1]/'backend/contracts/sql/stock_policy_v1.sql').read_text(encoding='utf-8'))
    sql.append('INSERT INTO supply_planning.spl_stock_policy_version(id,source_system,source_checksum,created_by,change_reason) VALUES ('+','.join(map(literal,[version,'diarco_data.src.t055_articulos_param_stock',hashlib.sha256(snapshot).hexdigest(),'codex','Carga inicial autorizada; locales 83 y 84 cerrados; rubro 0 toda la familia']))+');')
    for code,name in [(1,'SENSIBLES'),(2,'RESTO TOP'),(3,'VARIEDAD EXTRA'),(6,'SENSIBLES PM')]:
        sql.append(f'INSERT INTO supply_planning.spl_stock_purchase_classification(code,name) VALUES ({code},{literal(name)});')
    seen=set(); mapped=excluded=0
    for r in rows:
        values=[r[k] for k in ['c_sucu_empr','c_familia','c_rubro','c_claisificacion_compra']]
        if any(v is None or not Decimal(str(v)).is_finite() or int(v)!=v for v in values): raise ValueError('Clave no entera')
        site,family,category,classification=map(int,values)
        key=(site,family,category,classification)
        if key in seen: raise ValueError('Clave repetida')
        seen.add(key)
        days=[Decimal(str(r[k])) for k in ['q_dias_stock','q_dias_sobre_stock']]
        if any(not d.is_finite() or d<0 for d in days): raise ValueError('Dias invalidos')
        rule=None
        if site in (83,84):
            status='EXCLUDED_CLOSED'; reason='Local cerrado confirmado por usuario'; excluded+=1
        else:
            if len(sites[site])!=1: raise ValueError(f'Local sin mapeo unico: {site}')
            f=cats[str(family)]; c=cats[f'{family}-{category}'] if category else None
            if c and c['parent_id']!=f['id']: raise ValueError('Jerarquia incompatible')
            rule=str(uuid4()); status='MAPPED'; reason=None; mapped+=1
            fields=[rule,version,sites[site][0],f['id'],c['id'] if c else None,classification,*days,site,family,category]
            sql.append('INSERT INTO supply_planning.spl_stock_policy_rule(id,policy_version_id,site_id,family_category_id,category_id,purchase_classification_code,target_stock_days,overstock_days,legacy_site_code,legacy_family_code,legacy_category_code) VALUES ('+','.join(map(literal,fields))+');')
        fields=[version,site,family,category,classification,*days,rule,status,reason]
        sql.append('INSERT INTO supply_planning.spl_stock_policy_import_row VALUES ('+','.join(map(literal,fields))+');')
    sql+=['COMMIT;']
    (ROOT/'carga_inicial_test.sql').write_text('\n'.join(sql)+'\n',encoding='utf-8')
    report={'version_id':version,'source_rows':len(rows),'mapped_rules':mapped,'excluded_closed':excluded,'status':'DRAFT','source_checksum':hashlib.sha256(snapshot).hexdigest()}
    (ROOT/'carga_inicial_resumen.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report))

if __name__=='__main__': main()
