# Carga inicial de inventory — TEST — 17/09/2026

## Actualización: completar días NULL

Por nueva instrucción del usuario, los pares con fila de stock se completan por campo: objetivo NULL → **7**; sobrestock NULL → **0**. Los valores informados se conservan. Se insertaron **5.922** pares adicionales, todos con ambos días originalmente NULL, y el total de reposición quedó en **1.001.400**. No se insertaron nuevas clasificaciones ni selecciones logísticas. Auditoría acumulada: **1.004.166** registros.

Esta regla reemplaza la exclusión inicial descrita más abajo. La ausencia de toda la fila de stock sigue resolviéndose con ambos días en cero; preparación NULL sigue en cero. Los 8.795 pares sin correspondencia en maestros y los pendientes logísticos continúan pendientes.

Evidencia separada para conservar la primera ejecución: [resultado complementario](../../data/cargas_inventory/20260917_completar_dias/result.json) y [verificación complementaria](../../data/cargas_inventory/20260917_completar_dias/verification.json).

## Antecedente: primera carga

**Estado: COMMIT confirmado y verificación independiente aprobada.** Se insertaron las 995.478 reposiciones, 18.386 clasificaciones y 2.766 selecciones previstas. La comparación completa contra la captura obtuvo cero diferencias de parámetros y clasificación, cero pares pendientes cargados, cero clasificaciones activas duplicadas y cero selecciones logísticas inválidas. Auditoría: 998.244 filas, correspondientes a reposición y logística.

Destino: `connexa_platform_test`. Fuente: captura consistente de `diarco_data`, cierre de stock 16/09/2026. Ejecución autorizada por el usuario; sin DDL ni cambios de producción. El resultado de la transacción y la verificación se encuentran en [result.json](../../data/cargas_inventory/20260917_inicial/result.json) y [verification.json](../../data/cargas_inventory/20260917_inicial/verification.json).

## Universo validado

| Concepto | Filas |
|---|---:|
| Pares de productos vigentes en origen | 1.010.195 |
| Pares sin correspondencia en maestros TEST | 8.795 |
| Pares mapeados con fila de stock y días NULL, excluidos | 5.922 |
| Pares de reposición válidos | 995.478 |
| De ellos, sin fila de stock: días en cero | 34.154 |
| De ellos, preparación NULL convertida a cero | 510.524 |
| De ellos, pares inactivos conservados como inactivos | 636.561 |
| Clasificaciones de origen | 60.881 |
| Artículos de origen sin maestro producto TEST | 42.495 |
| Clasificaciones para productos existentes | 18.386 |
| Selecciones logísticas únicas utilizables | 2.766 |
| Productos pendientes de selección logística | 15.620 |

Los conteos de ceros se superponen: los pares sin fila de stock están incluidos en preparación NULL. La carga conserva el estado del par en inventory y no lo reactiva ni lo filtra por habilitación legacy. No se cargan cantidades físicas de stock.

La clasificación usa el tipo **Clasificación Compra** (`8fe2ed35-bbe5-4cd5-b886-4d378df7e77f`), que contiene las siete opciones. Existe además un tipo **Compra** sin catálogo; se conserva sin modificar. El cargador resuelve el tipo por su catálogo en cada destino y no fija este UUID en el código.

## Pendientes concretos

- [missing_days.csv](../../data/cargas_inventory/20260917_inicial/missing_days.csv): pares excluidos por objetivo/sobrestock NULL; decisión explícita del usuario.
- [unmapped_pairs.csv](../../data/cargas_inventory/20260917_inicial/unmapped_pairs.csv): reconciliar contra maestros antes de ampliar la carga.
- [unmapped_classification_products.csv](../../data/cargas_inventory/20260917_inicial/unmapped_classification_products.csv): artículos T050 que no existen en inventory; no se crearon productos automáticamente.
- [pending_logistics.csv](../../data/cargas_inventory/20260917_inicial/pending_logistics.csv): productos sin una variable principal activa única y utilizable. Incluye número de candidatas; requiere selección o corrección de maestros.
- Integrar consumidores PDD y FORECAST_CONNEXA con los campos canónicos y la selección logística explícita. La carga no activa el parche de aplicación preparado anteriormente.
- `supply_planning.spl_forecast_planning_input` se poblará con resultados reales del proceso de previsión; no corresponde generar snapshots ficticios en esta carga de maestros.

## Reproducción

Ver [cargador y reglas](../../cargas_inventory/README.md). Fuente inmutable con hashes; UUID resueltos por códigos; inserts sin sobrescribir filas existentes; una transacción y triggers de auditoría habilitados. Preparación para producción reutilizable, con habilitación de destino y validación nueva pendientes antes de cualquier ejecución allí.
