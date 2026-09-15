"""S20 local: enrich frozen pilot inputs without publishing or changing states."""
import argparse
import hashlib
import json
from datetime import datetime
from decimal import Decimal
from pathlib import Path

import numpy as np
import pandas as pd

from .config import PilotConfig
from .field_status import write_status_reports
from .pilot import KEY, normalize, excluded_codes

# Supplier-dependent prices and policy days are deliberately not taken from stock.
CLOSING_FIELDS = {
    'stock': 'STOCK', 'pedido_pendiente': 'PEDIDO_PENDIENTE',
    'transfer_pendiente': 'TRANSFER_PENDIENTE', 'transito_pendiente': 'TRANSITO_PENDIENTE',
    'pedido_pendiente_fecha': 'PEDIDO_PENDIENTE_FECHA',
    'transfer_pendiente_fecha': 'TRANSFER_PENDIENTE_FECHA',
    'transito_pendiente_fecha': 'TRANSITO_PENDIENTE_FECHA',
    'ultimo_ingreso': 'ULTIMO_INGRESO', 'fecha_ultimo_ingreso': 'FECHA_ULTIMO_INGRESO',
    'precio_venta': 'PRECIO_VENTA', 'precio_costo': 'PRECIO_COSTO',
    'stock_reserva': 'stock_reserva_observada',
    'fecha_stock': 'fecha_stock', 'fecha_extraccion': 'fecha_extraccion',
    'fuente_origen': 'fuente_origen',
}
PENDING = ['NUMBER_OF_BOXES_PER_LAYER',
           'NUMBER_OF_LAYERS', 'Q_FACTOR_COMPRA', 'PEDIDO_MIN', 'C_COMPRADOR',
           'ABASTECIMIENTO', 'COD_CD', 'M_VENDE_POR_PESO', 'Q_PESO_UNIT_ART',
           'Q_DIAS_STOCK', 'Q_DIAS_SOBRE_STOCK', 'DIAS_PREPARACION',
           'GRAFICO', 'DETALLE_CALCULO_JSON']


def missing_reason(field):
    if field in ('GRAFICO', 'DETALLE_CALCULO_JSON'):
        return 'generation_pending'
    if field in ('Q_DIAS_STOCK', 'Q_DIAS_SOBRE_STOCK', 'DIAS_PREPARACION',
                 'PEDIDO_MIN', 'ABASTECIMIENTO', 'COD_CD'):
        return 'connexa_product_site_source_null_or_unavailable'
    if field in ('NUMBER_OF_BOXES_PER_LAYER', 'NUMBER_OF_LAYERS', 'Q_FACTOR_COMPRA',
                 'Q_PESO_UNIT_ART', 'M_VENDE_POR_PESO'):
        return 'logistic_selection_and_units_pending'
    if field == 'C_COMPRADOR':
        return 'execution_user_buyer_resolution_pending'
    if field.startswith(('TRANSITO_PENDIENTE', 'TRANSFER_PENDIENTE')):
        return 'dedicated_pending_source_integration_pending'
    return 'unresolved_mapping_or_policy' if field in PENDING else 'source_null_or_absent'


def _json_decimal(value):
    if isinstance(value, Decimal):
        return str(value)  # Preserve exact master values in evidence JSON.
    raise TypeError(type(value).__name__)


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def verify_master(universe, supplier):
    """Read current TEST replicas; never replace inventory IDs with replica IDs."""
    checks = []
    with PilotConfig.load().read_connection('MASTER') as conn:
        with conn.cursor() as cur:
            specs = [
                ('product', 'inv_product', 'spl_product', 'ext_code', 'inventory_product_id', 'Codigo_Articulo'),
                ('site', 'inv_site', 'spl_site', 'code', 'inventory_site_id', 'Sucursal'),
            ]
            for entity, inv, spl, code, id_col, key in specs:
                scope = universe[[key, id_col]].drop_duplicates()
                cur.execute(f'''SELECT i.{code}, i.id::text, s.id::text
                    FROM inventory.{inv} i LEFT JOIN supply_planning.{spl} s
                    ON s.id=i.id AND s.{code}=i.{code} WHERE i.{code}=ANY(%s)''',
                    ([str(x) for x in scope[key]],))
                rows = {r[0]: r[1:] for r in cur.fetchall()}
                for value, frozen in scope.itertuples(index=False, name=None):
                    current, replica = rows.get(str(value), (None, None))
                    checks.append(dict(entity=entity, code=str(value), inventory_id=str(frozen),
                                       current_inventory_id=current, replica_id=replica,
                                       valid=str(frozen) == current == replica))
            cur.execute('''SELECT i.id::text, s.id::text FROM inventory.inv_supplier i
                LEFT JOIN supply_planning.spl_supplier s ON s.id=i.id AND s.ext_code=i.ext_code
                WHERE i.ext_code=%s''', (str(supplier),))
            rows = cur.fetchall()
            supplier_id, replica = rows[0] if len(rows) == 1 else (None, None)
            frozen_ids = (universe.inventory_supplier_id.dropna().astype(str).unique().tolist()
                          if 'inventory_supplier_id' in universe else [])
            valid = supplier_id is not None and supplier_id == replica and (
                not frozen_ids or frozen_ids == [supplier_id])
            checks.append(dict(entity='supplier', code=str(supplier), inventory_id=supplier_id,
                               current_inventory_id=supplier_id, replica_id=replica, valid=valid))
            cur.execute('''SELECT product_id::text, logistic_variable_id::text, boxes_per_layer, pallet_layers,
                purchase_factor, weight_in_gr, uom_id, selection_row_version
                FROM inventory.inv_planning_logistics_v
                WHERE usable_for_forecast IS TRUE AND product_id=ANY(%s::uuid[])''',
                (universe.inventory_product_id.astype(str).unique().tolist(),))
            logistics = [dict(zip(['product_id', 'logistic_variable_id', 'boxes_per_layer',
                         'pallet_layers', 'purchase_factor', 'weight_in_gr', 'uom_id', 'selection_row_version'], row))
                         for row in cur.fetchall()]
            scope = universe[['inventory_product_id', 'inventory_site_id']].to_dict('records')
            cur.execute('''WITH scope AS (
                SELECT * FROM jsonb_to_recordset(%s::jsonb)
                AS x(inventory_product_id uuid, inventory_site_id uuid))
                SELECT ps.product_id::text,ps.site_id::text,ps.id::text,
                    r.target_stock_days,ps.supply_type,ps.supplying_site_id::text,
                    supply.code,r.id::text,r.minimum_order_quantity,r.preparation_days,r.overstock_days,r.row_version
                FROM scope x JOIN inventory.inv_product_site ps
                  ON ps.product_id=x.inventory_product_id AND ps.site_id=x.inventory_site_id
                LEFT JOIN inventory.inv_site supply ON supply.id=ps.supplying_site_id
                LEFT JOIN inventory.inv_product_site_replenishment r
                  ON r.product_site_id=ps.id AND r.active IS TRUE''', (json.dumps(scope),))
            site_parameters = [dict(zip(['product_id','site_id','product_site_id','Q_DIAS_STOCK',
                'ABASTECIMIENTO','COD_CD','supplying_site_code','replenishment_id','PEDIDO_MIN',
                'DIAS_PREPARACION','Q_DIAS_SOBRE_STOCK','replenishment_row_version'], row)) for row in cur.fetchall()]
    return dict(checked_at=datetime.now().astimezone().isoformat(),
                source='CONNEXA_TEST_current_not_historical', parameter_contract='inventory-planning-v1', supplier_id=supplier_id,
                checks=checks, logistics=logistics, site_parameters=site_parameters)


def apply_site_parameters(out, rows):
    groups = {}
    for row in rows:
        groups.setdefault((row['product_id'], row['site_id']), []).append(row)
    if any(len(values) != 1 for values in groups.values()):
        raise ValueError('Ambiguous product/site or active replenishment parameters')
    for field in ['product_site_id','Q_DIAS_STOCK','ABASTECIMIENTO','COD_CD',
                  'supplying_site_code','replenishment_id','PEDIDO_MIN',
                  'DIAS_PREPARACION','Q_DIAS_SOBRE_STOCK','replenishment_row_version']:
        out[field] = [groups.get((p, s), [{}])[0].get(field)
                      for p, s in zip(out.product_id, out.site_id)]


def apply_logistics(out, rows):
    """Only a unique active/principal row is usable; weight contract is kilograms."""
    groups = {}
    for row in rows:
        groups.setdefault(row['product_id'], []).append(row)
    ambiguous = sorted(key for key, vals in groups.items() if len(vals) > 1)
    unique = {key: vals[0] for key, vals in groups.items() if len(vals) == 1}
    for dest, src in [('NUMBER_OF_BOXES_PER_LAYER', 'boxes_per_layer'),
                      ('NUMBER_OF_LAYERS', 'pallet_layers'), ('Q_FACTOR_COMPRA', 'purchase_factor'),
                      ('Q_PESO_UNIT_ART', 'weight_in_gr')]:
        out[dest] = out.product_id.map(lambda key: unique.get(key, {}).get(src))
        if dest == 'Q_PESO_UNIT_ART':
            out[dest] = pd.to_numeric(out[dest], errors='raise') / 1000.0
    out['logistic_variable_id'] = out.product_id.map(lambda key: unique.get(key, {}).get('logistic_variable_id'))
    out['logistics_selection_row_version'] = out.product_id.map(lambda key: unique.get(key, {}).get('selection_row_version'))
    def weight_flag(key):
        uom = unique.get(key, {}).get('uom_id')
        return pd.NA if uom is None else int(uom != 'unidad')
    out['M_VENDE_POR_PESO'] = out.product_id.map(weight_flag)
    return ambiguous


def extend(source, output, check_master=False):
    source, output = Path(source), Path(output)
    if output.exists():
        raise ValueError('Output directory must be new')
    manifest = json.loads((source/'manifest.json').read_text(encoding='utf-8'))
    frames = {}
    for name in ('universe', 'sales', 'closing', 'results'):
        path = source/f'{name}.csv'
        if digest(path) != manifest['input_hashes'][name]:
            raise ValueError(f'Input hash mismatch: {name}')
        frames[name] = pd.read_csv(path)
    u = normalize(frames['universe'], KEY+['supplier_code', 'inventory_product_id', 'inventory_site_id'], KEY)
    r = normalize(frames['results'], KEY+['supplier_code', 'Forecast'], KEY)
    c = normalize(frames['closing'], KEY+['fecha_stock'], KEY)
    s = normalize(frames['sales'], KEY+['Fecha', 'Unidades'], None)
    pairs = set(map(tuple, u[KEY].values))
    for f in (r, c):
        if set(map(tuple, f[KEY].values)) != pairs:
            raise ValueError('Universe, results and closing must cover identical pairs')
    if not set(map(tuple, s[KEY].values)).issubset(pairs):
        raise ValueError('Sales outside universe')
    for f in (u, r):
        if not pd.to_numeric(f.supplier_code).eq(int(manifest['supplier_code'])).all():
            raise ValueError('Supplier mismatch')
    if not np.isfinite(pd.to_numeric(r.Forecast)).all():
        raise ValueError('Invalid forecast')
    temporal = manifest['temporal_context']
    cutoff = pd.Timestamp(temporal['data_cutoff_date'])
    if not pd.Timestamp(temporal['stock_closing_date']) <= cutoff < pd.Timestamp(temporal['execution_date']):
        raise ValueError('Invalid temporal context')
    if s.Fecha.gt(cutoff).any() or not pd.to_datetime(c.fecha_stock).dt.normalize().eq(
            pd.Timestamp(temporal['stock_closing_date'])).all():
        raise ValueError('Source dates do not match manifest')
    policy = manifest.get('purchase_exclusions')
    if policy is None:
        raise ValueError('Purchase exclusion snapshot required for S20')
    if u.Sucursal.isin(excluded_codes(policy['sites'])).any():
        raise ValueError('Excluded sites in input')
    # Keep only attributes with explicit provenance; never override the execution supplier.
    out = r.merge(u.drop(columns='supplier_code'), on=KEY, validate='one_to_one')
    out = out.merge(c[KEY+[x for x in CLOSING_FIELDS if x in c]].rename(columns=CLOSING_FIELDS),
                    on=KEY, validate='one_to_one')
    out['product_id'] = out.inventory_product_id
    out['site_id'] = out.inventory_site_id
    for name, start, end in [('Ventas_rango_1', 14, 0), ('Ventas_rango_2', 29, 15)]:
        sales = s[s.Fecha.between(cutoff-pd.Timedelta(days=start), cutoff-pd.Timedelta(days=end))]
        agg = sales.groupby(KEY).Unidades.sum().rename(name).reset_index()
        out = out.merge(agg, on=KEY, how='left', validate='one_to_one')
        out[name] = out[name].fillna(0)  # No matching sales means zero, including fractional units.
    audit = verify_master(u, manifest['supplier_code']) if check_master else None
    out['supplier_id'] = out.get('inventory_supplier_id', pd.Series(pd.NA, index=out.index))
    if audit and out.supplier_id.isna().all():
        out['supplier_id'] = audit['supplier_id']
    out['HABILITADO'] = 1  # Frozen eligible universe with purchase exclusions applied.
    for col in PENDING:
        out[col] = pd.NA
    # Business constants for forecast; purchase pricing happens later at OC valuation.
    out['FACTOR_VENTA'] = 1
    out['I_LISTA_CALCULADO'] = 0
    ambiguous_logistics = apply_logistics(out, audit['logistics']) if audit else []
    if audit:
        apply_site_parameters(out, audit['site_parameters'])
    missing = []
    for col in list(CLOSING_FIELDS.values())+PENDING+['product_id', 'site_id', 'supplier_id']:
        count = int(out[col].isna().sum()) if col in out else len(out)
        if count:
            missing.append(dict(field=col, missing_rows=count,
                                reason=missing_reason(col)))
    report = dict(status='LOCAL_S20_DRAFT', publication_ready=False, database_writes=0,
                  rows=len(out), cutoff=str(cutoff.date()),
                  source_manifest_sha256=digest(source/'manifest.json'), source_directory=str(source),
                  temporal_context=temporal, purchase_exclusions=policy,
                  policies_resolved=False, replica_check=audit,
                  retired_fields={'PEDIDO_SGM': 'Legacy estimate no longer required by business'},
                  ambiguous_logistic_product_ids=ambiguous_logistics,
                  logistic_weight_unit='kg',
                  blockers=['S40 field integration and source-data checks incomplete',
                            'S40 calculation detail and graphics not generated'] + (
                      ['Replica validation not performed'] if audit is None else
                      ['Replica identity inconsistencies'] if any(not x['valid'] for x in audit['checks']) else []))
    output.mkdir(parents=True, exist_ok=False)
    out.to_csv(output/'extended_draft.csv', index=False)
    pd.DataFrame(missing, columns=['field', 'missing_rows', 'reason']).to_csv(output/'missing_fields.csv', index=False)
    report['field_status_summary'] = write_status_reports(output, missing, audit is not None)
    report['output_sha256'] = digest(output/'extended_draft.csv')
    (output/'report.json').write_text(json.dumps(report, indent=2, default=_json_decimal), encoding='utf-8')
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--verify-master', action='store_true', help='Read current TEST UUID replicas')
    args = parser.parse_args()
    try:
        report = extend(args.input, args.output, args.verify_master)
    except Exception as exc:
        parser.exit(2, f'S20 failed ({type(exc).__name__}); no database writes.\n')
    print(json.dumps({k: report[k] for k in ('status', 'rows', 'publication_ready', 'database_writes')}))


if __name__ == '__main__':
    main()
