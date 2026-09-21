# Método de reposición desde abastecimiento

**Aplicado y verificado en TEST el 17/09/2026:** 1.001.400 filas actualizadas, cero métodos faltantes entre los pares mapeados y cero diferencias respecto del origen. La transacción quedó confirmada y la segunda ejecución de verificación encontró cero filas que requieran completar el método.

Origen: `diarco_data.src.base_productos_vigentes`. Destino: `connexa_platform_test.inventory.inv_product_site_replenishment.replenishment_method`. Cruce por artículo y sucursal; solo filas de reposición existentes.

La conversión guarda las descripciones solicitadas, sin espacios de relleno:

| Código | Descripción | Pares mapeados |
|---:|---|---:|
| 0 | Entrega desde CD | 385.983 |
| 1 | Entrega Desde el Proveedor | 383.759 |
| 2 | Cross Doking | 3.201 |
| 3 | Entrega desde QX | 228.457 |
| Total | | 1.001.400 |

La captura tiene 1.010.195 pares únicos, sin códigos NULL o desconocidos. Hay 8.795 pares sin fila de reposición en destino, conservados en `unmatched.csv`; este proceso no crea maestros ni parámetros faltantes. `c_proveedor_primario` queda en la captura para referencia, no se usa como clave.

Se actualiza exclusivamente `replenishment_method` cuando está NULL. Los triggers mantienen revisión, actor y auditoría. No se cambian días, cantidades, clasificaciones, selección logística ni `inv_product_site.supply_type`. Esta regla posterior sustituye la descripción histórica de `replenishment_method` como campo conservado solo por compatibilidad.

Estado de ejecución y evidencia:

- [Preview validado](../../data/cargas_inventory/20260917_metodo/preview.json).
- [Resultado de aplicación](../../data/cargas_inventory/20260917_metodo/result.json): revisar `status=COMMITTED`.
- [Verificación posterior](../../data/cargas_inventory/20260917_metodo/verification.json): revisar `status=VERIFIED` y `mismatches=0`.
- [Captura, hash y conversión](../../data/cargas_inventory/20260917_metodo/manifest.json).
- [Pares sin correspondencia](../../data/cargas_inventory/20260917_metodo/unmatched.csv).

Reproducción: [instrucciones del proceso de carga](../../cargas_inventory/README.md). El cargador es un paso complementario repetible y restringido a TEST. No sustituye por defecto valores no NULL que discrepen del origen; se detiene para revisión.
