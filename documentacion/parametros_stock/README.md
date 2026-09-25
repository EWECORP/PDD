# Parámetros de stock y maestros CONNEXA

**Lead time desde CD:** regla confirmada: proveedor 0 por sucursal. Ver [estado y evidencia](14_lead_time_TEST_20260917.md).

**Método de reposición:** proceso para completar `replenishment_method` desde `abastecimiento` incorporado a la carga. Ver [conversión y evidencia de ejecución](13_metodo_reposicion_TEST_20260917.md).

**Actualización de la carga:** completados los 5.922 pares antes excluidos por días NULL: objetivo 7 y sobrestock 0. Total TEST: **1.001.400** reposiciones. Ver [estado actualizado](12_carga_inicial_TEST_20260917.md).

**Carga inicial confirmada el 17/09/2026:** 995.478 reposiciones, 18.386 clasificaciones y 2.766 selecciones log?sticas. Los pares con fila de stock y d?as NULL quedaron excluidos. Ver [estado de carga, evidencia y pendientes](12_carga_inicial_TEST_20260917.md). Las capturas siguientes describen estados anteriores a esta carga.

**Clasificaciones, actualización posterior del 17/09:** aplicado y verificado el catálogo de valores por tipo, con las siete opciones de Compra activas y cero asignaciones a productos. Relaciones, unicidad y vigencias conforme al SQL entregado. Próximo paso: carga desde T050. Ver [paquete aplicado y estado](../../entregables/backend_classification_catalog_20260917/README.md).

**Estado integrado al 24/09/2026:** las tres migraciones del paquete están aplicadas, se cargaron los parámetros de Inventory y PDD 0.20.0 consume `inventory.inv_planning_parameters_v`. La corrida diaria integral de TEST completó con cobertura del scope y 13.773 líneas de backlog. Durante la prueba se corrigieron 275 reposiciones válidas que habían quedado inactivas por copiar indebidamente el estado de `product_site`; el cargador debe preservar ambos estados por separado. Ver [estado y clasificaciones al 17/09](11_estado_y_clasificaciones_TEST_20260917.md) como evidencia previa a la integración. Los estados fechados que siguen son antecedentes, no la fotografía actual.

Actualización: **2026-09-24**. Estado: **Inventory integrado con PDD en TEST; carga y corrida diaria validadas**.

## Estado actual

BACK decidió reutilizar `inventory` para integrar los maestros sugeridos, sin crear `replenishment`. Las 605 reglas de políticas versionadas permanecen en `supply_planning`, en DRAFT y fuera del circuito activo. Desde PDD 0.19.0, PDD obtiene `target_stock_days` y `overstock_days` exclusivamente desde `inventory.inv_planning_parameters_v`; ya no usa esos días de `src.base_stock_sucursal`.

La ubicación en `inventory` y el contrato de ambos días quedaron integrados
para PDD. Las políticas versionadas DRAFT continúan fuera del circuito y la
logística conserva su gobierno separado. Los conteos históricos de reposición
vacía ya no describen el estado actual. La auditoría del 14/09 fue de sólo
lectura; las cargas y correcciones posteriores tienen su evidencia fechada.

## Evidencia y antecedentes

- [07_auditoria_inventory_test_20260914.md](07_auditoria_inventory_test_20260914.md): mapa de entidades solicitadas a tablas reales, calidad, diferencias y dictamen.
- [08_solicitudes_BACK_inventory_test.md](08_solicitudes_BACK_inventory_test.md): doce solicitudes con prioridad, evidencia y criterio de aceptación; preparadas, no enviadas ni aplicadas.
- [09_diccionario_inventory_test_20260914.md](09_diccionario_inventory_test_20260914.md): columnas, tipos exactos, defaults, nulabilidad, restricciones e índices de 28 tablas de maestros y políticas.
- [catalogo_test_inventory_20260914.json](catalogo_test_inventory_20260914.json): evidencia del catálogo, conteos, diagnósticos e historial Flyway de inventory.
- [auditar_test_inventory.py](auditar_test_inventory.py) y [consultas_auditoria_inventory.py](consultas_auditoria_inventory.py): consultas reproducibles de solo lectura.

## Antecedentes conservados

- [06_implementacion_borrador_test.md](06_implementacion_borrador_test.md): creación/carga del borrador del 11/09; 605 reglas y 627 filas de evidencia.
- [05_combinaciones_conflictivas.md](05_combinaciones_conflictivas.md): conflictos de grupos de prueba, posteriormente confirmados como dummy.
- [03_relevamiento_test.md](03_relevamiento_test.md), [04_diccionario_catalogo.md](04_diccionario_catalogo.md) y [catalogo_pgp_test.json](catalogo_pgp_test.json): fotografía histórica anterior a la carga del borrador.
- [02_propuesta_politicas_stock.md](02_propuesta_politicas_stock.md) y [01_relevamiento_repositorio.md](01_relevamiento_repositorio.md): propuesta inicial y análisis del lector PDD.
- [Paquete BACK del 11/09](../../entregables/backend_stock_policy_flyway/README.md): contrato original y migraciones en supply_planning; requieren reconciliación con la decisión final de BACK. Esta auditoría no los ejecutó ni modificó.

## Reproducción

Desde la raíz ETL, con Python, psycopg2 y python-dotenv:

```powershell
python PDD/documentacion/parametros_stock/auditar_test_inventory.py
```

Lee PGP_TEST_* de backend/.env, verifica la base y exige transacción READ ONLY / REPEATABLE READ. Sólo consulta catálogo y datos seleccionados de TEST; no lee filas de tablas externas ni ejecuta validadores de migraciones. Una reproducción sobrescribe el JSON de esta auditoría: para una nueva fecha conservar una captura separada. El diccionario Markdown representa la captura fechada, no se regenera automáticamente al ejecutar el extractor.
