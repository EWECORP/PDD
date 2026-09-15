"""Separate confirmed mappings from implementation and source-data work."""
import pandas as pd


def classify(field, master_checked):
    if field.startswith(('TRANSFER_PENDIENTE', 'TRANSITO_PENDIENTE')):
        source = ('src.base_transferencias_pendientes' if field.startswith('TRANSFER')
                  else 'src.base_productos_en_transito')
        return source, 'integration_pending', 'Implementar lectura y validar granularidad y fechas'
    if field == 'GRAFICO':
        return 'S30.insertar_graficos_forecast -> generar_grafico_json', 'generation_pending', 'Adaptar generador existente a snapshots, corte explicito y universo CONNEXA'
    if field == 'DETALLE_CALCULO_JSON':
        return 'funciones_forecast.agregar_detalle_calculo_forecast', 'generation_pending', 'Reutilizar generador existente y helpers con metricas y contexto del piloto'
    if field == 'C_COMPRADOR':
        return 'spl_buyer + spl_buyer_supplier', 'execution_context_pending', 'Integrar usuario de ejecucion y resolver comprador vigente'
    if field in ('PEDIDO_MIN', 'DIAS_PREPARACION', 'Q_DIAS_STOCK', 'Q_DIAS_SOBRE_STOCK'):
        return 'inventory.inv_product_site_replenishment', ('source_data_pending' if master_checked else 'source_not_checked'), 'Verificar fila activa y valores; no usar fallback legado'
    if field in ('ABASTECIMIENTO', 'COD_CD'):
        return 'inventory.inv_product_site', ('source_data_review' if master_checked else 'source_not_checked'), 'Revisar nulos segun modalidad; no consolidar ni exigir sitio abastecedor a toda entrega directa'
    if field in ('NUMBER_OF_BOXES_PER_LAYER', 'NUMBER_OF_LAYERS', 'Q_FACTOR_COMPRA',
                 'M_VENDE_POR_PESO', 'Q_PESO_UNIT_ART'):
        return 'inventory.inv_planning_logistics_v', ('source_data_pending' if master_checked else 'source_not_checked'), 'Configurar seleccion logistica explicita y atributos utilizables; peso en kg'
    if field in ('product_id', 'site_id', 'supplier_id'):
        return 'inventory', 'identity_review', 'Verificar UUID de origen y replica sin sustituir identidad'
    if field in ('STOCK', 'PEDIDO_PENDIENTE', 'PEDIDO_PENDIENTE_FECHA', 'ULTIMO_INGRESO',
                 'FECHA_ULTIMO_INGRESO', 'PRECIO_VENTA', 'PRECIO_COSTO', 'stock_reserva_observada',
                 'fecha_stock', 'fecha_extraccion', 'fuente_origen'):
        return 'src.base_stock_sucursal', 'source_data_review', 'Revisar nulos de la captura; no convertir automaticamente a cero'
    return '', 'definition_pending', 'Definir fuente y significado del campo'


def write_status_reports(output, missing, master_checked):
    """Missing counts are observations, not assertions that a definition is missing."""
    rows = []
    for item in missing:
        source, status, action = classify(item['field'], master_checked)
        rows.append(dict(**item, mapping_status='pending' if status == 'definition_pending' else 'confirmed', source=source,
                         work_status=status, next_action=action))
    columns = ['field', 'missing_rows', 'reason', 'mapping_status', 'source', 'work_status', 'next_action']
    table = pd.DataFrame(rows, columns=columns)
    table.to_csv(output/'field_status.csv', index=False)
    # No unresolved field source remains in the current list; keep a separate explicit report.
    table[table.mapping_status.ne('confirmed')].to_csv(output/'definitions_pending.csv', index=False)
    table[table.work_status.isin(['integration_pending', 'generation_pending', 'execution_context_pending'])].to_csv(
        output/'implementation_pending.csv', index=False)
    table[~table.work_status.isin(['integration_pending', 'generation_pending', 'execution_context_pending', 'definition_pending'])].to_csv(
        output/'data_review.csv', index=False)
    return dict(definitions_pending=int(table.mapping_status.eq('pending').sum()), fields_with_missing_values=len(rows),
                by_work_status=table.work_status.value_counts().to_dict(),
                note='Mapping confirmed does not mean data complete or publication ready')
