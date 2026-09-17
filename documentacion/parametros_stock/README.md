# Parámetros de stock y maestros CONNEXA

**Clasificaciones, actualización posterior del 17/09:** aplicado y verificado el catálogo de valores por tipo, con las siete opciones de Compra activas y cero asignaciones a productos. Relaciones, unicidad y vigencias conforme al SQL entregado. Próximo paso: carga desde T050. Ver [paquete aplicado y estado](../../entregables/backend_classification_catalog_20260917/README.md).

**Última verificación del 17/09/2026:** las tres migraciones del paquete están aplicadas, incluido el snapshot FORECAST. Reposición y selección logística siguen vacías; faltan carga e integración de consumidores. Ver [estado actual y revisión de clasificaciones](11_estado_y_clasificaciones_TEST_20260917.md) y [diagnóstico de fuentes](10_verificacion_BACK_TEST_20260917.md). Los estados anteriores que siguen se conservan como antecedentes.

Actualización: **2026-09-14**. Estado: **TEST auditado en solo lectura; documentación actualizada; solicitudes a BACK preparadas, pendientes de envío**.

## Estado actual

BACK decidió reutilizar `inventory` para integrar los maestros sugeridos, sin crear `replenishment`. Se verificó en vivo `connexa_platform_test`: los maestros están integrados parcialmente; reposición tiene 852 filas. Las 605 reglas de políticas versionadas permanecen en `supply_planning`, en DRAFT. PDD todavía obtiene días objetivo y sobrestock desde `src.base_stock_sucursal`.

La ubicación en inventory es compatible con PDD, pero falta cerrar el contrato de ambos días, precedencia, políticas versionadas, logística y trazabilidad. Los conteos históricos de reposición vacía ya no describen el estado actual. No se modificó la base en la auditoría del 14/09.

## Documentación vigente

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
