# Nivelación inventory — PDD y FORECAST

> **Última verificación 17/09/2026:** BACK ya aplicó en TEST las tres migraciones, incluida `spl_forecast_planning_input`. Reposición y selección logística siguen vacías. No repetir el reset ni las migraciones. Ver [estado actual](../../documentacion/parametros_stock/11_estado_y_clasificaciones_TEST_20260917.md) y [calidad de las fuentes](../../documentacion/parametros_stock/10_verificacion_BACK_TEST_20260917.md). El texto siguiente registra el paquete original previo a su aplicación.

Entrega **14/09/2026**. **Paquete preparado, no aplicado en TEST.** Punto de partida: estructura actual aceptada por BACK; este paquete incorpora el nuevo alcance acordado con el usuario, sin exigir completar la propuesta anterior de políticas por grupo.

**Decisión confirmada:** `inventory.inv_product_site_replenishment` será la fuente única de parámetros directos por artículo/local para PDD y FORECAST. Se usarán **`target_stock_days` y `overstock_days`**. Se eliminan `target_coverage_days` y `safety_stock_days`; sus valores de prueba no se convierten ni se copian. Los 852 registros actuales pueden borrarse y regenerarse. Los valores nuevos deben provenir de una carga definida por negocio: no se suministra una carga ficticia ni se presupone sobrestock cero.

## Qué entregar a BACK

| Archivo | Cambio |
|---|---|
| `migrations/inventory/V20260914150001__normalize_product_site_replenishment.sql` | Dos días canónicos decimales obligatorios, mínimos/preparación explícitos, validaciones, revisión y auditoría de cambios |
| `migrations/inventory/V20260914150002__explicit_planning_logistics.sql` | Una selección logística por producto, FK al mismo producto, auditoría y vistas de lectura compartidas |
| `migrations/supply_planning/V20260914150003__forecast_planning_input_snapshot.sql` | Evidencia inmutable de parámetros y logística por resultado de FORECAST, sin alterar resultados históricos |
| `preparation/00_reset_test_replenishment.sql` | Borrado explícito de los datos de prueba, separado de Flyway y restringido a `connexa_platform_test` |
| `CONTRATO_BACK.md` | Campos, API/mantenimiento, carga, permisos y aceptación |
| `IMPACTO_PDD_FORECAST.md` | Matriz de consumidores, parche del piloto, adaptador PDD y tareas de integración |
| `application/FORECAST_CONNEXA.patch` | Parche preparado para el lector S20 local; no aplicado al repositorio |
| `verification/preflight.sql`, `postflight.sql` | Diagnósticos SELECT antes/después |

Se utilizan esquemas existentes. Las reglas DRAFT de `supply_planning.spl_stock_policy_*` permanecen como antecedente fuera del circuito nuevo; no se borran ni se publican. El paquete anterior `backend_stock_policy_flyway` **no es un prerrequisito** y no se debe ejecutar como parte de esta nivelación.

## Orden de implementación

1. BACK revisa contrato y aplica en su rama los cambios de entidades/DTO/DAO: nuevos nombres, BigDecimal, actor y control por `row_version`. Coordinar los lectores afectados: el S20 actual consulta `safety_stock_days` y fallará tras eliminarla si no se adapta.
2. Ejecutar `verification/preflight.sql` por SELECT y comparar con `verification/baseline_test.json`. Captura real: PostgreSQL 14.24, 852 filas, sin FKs entrantes ni triggers de aplicación en reposición. El catálogo cambia: si aparecen dependencias, revisarlas antes del reset.
3. Detener escrituras/cargas y consumidores del parámetro durante la nivelación. Ejecutar manualmente `preparation/00_reset_test_replenishment.sql` **sólo en TEST**. Borra exclusivamente esa tabla, sin TRUNCATE CASCADE ni regenerar datos. Para otros entornos con datos, preparar una migración de datos independiente; estos SQL rechazan una tabla no vacía.
4. Incorporar las migraciones 01 y 02 al historial Flyway de `inventory`; luego 03 al de `supply_planning`. Si BACK usa un historial único, conservar ese mismo orden. Los números de 14 dígitos son propuestos y posteriores al historial inventory capturado (`20260902121500`); comprobar también el historial del servicio correspondiente. Si hace falta renumerar, hacerlo **antes** de la primera aplicación. No ejecutar baseline/repair ni cambiar una migración aplicada.
5. Flyway debe ejecutarlas transaccionalmente en PostgreSQL, con `validate` y `migrate` del pipeline habitual. Los SQL no contienen BEGIN/COMMIT; sólo el reset manual administra su transacción. No incluir `preparation/`, `application/` ni `verification/` en `locations`.
6. Ejecutar `postflight.sql`. Tras migrar se esperan **cero parámetros y cero selecciones**; no representa cobertura operativa. Cargar por código de artículo/local, resolver UUID contra inventory y registrar actor. La plantilla CSV aporta encabezados, sin valores de negocio inventados.
7. Configurar la variable logística explícita por producto y validar datos. Aplicar los lectores y la persistencia de evidencia descritos en `IMPACTO_PDD_FORECAST.md`. Medir cobertura del scope completo; faltantes bloquean el nuevo cálculo/publicación.
8. Habilitar el circuito nuevo sólo tras las pruebas de aceptación. PDD conserva fórmulas DECAS y FORECAST sus algoritmos/segmentación. Flyway no actualiza Python, Java, pantallas, datos de carga ni jobs por sí mismo.

## Validación realizada y límites

Se ejecutaron **22 verificaciones SQL** en una base local [PGlite](https://pglite.dev/docs/about), que informa PostgreSQL 17.5. Usan un fixture sintético de las relaciones afectadas basado en TEST; no una copia de los datos de TEST. Se verificaron transacciones, reset fuera de TEST rechazado, tabla no vacía rechazada, constraints, decimales, auditoría, control optimista, selección logística y snapshots. Ver `verification/results.json` con los hashes de los SQL probados.

Se ejecutaron **4 pruebas de adaptadores**: rechazo de faltantes/duplicados, preservación de hechos, días decimales, trazabilidad y peso en kg. El parche de FORECAST pasó `git apply --check --ignore-space-change` sobre el árbol de trabajo revisado. Las copias en `application/forecast_preview/` facilitan la revisión; no son otra aplicación.

**No se ejecutaron Flyway CLI ni PostgreSQL 14 nativo ni servicios Java/API.** Las pruebas de concurrencia verifican revisión optimista, no carga de varias sesiones. El cierre con el pipeline PostgreSQL 14 de BACK sigue siendo necesario. La captura de TEST fue READ ONLY; no se ejecutó allí ni siquiera DDL transaccional con rollback.

Reproducción local de las pruebas, con Node/npm y Python con pandas/numpy:

```powershell
cd PDD/entregables/backend_inventory_planning_20260914/verification
npm ci --ignore-scripts --no-audit --no-fund
npm test
python test_adapters.py
```

`capture_baseline.py` requiere el checkout ETL y usa backend/.env sin exportar credenciales; BACK puede usar los SELECT de preflight sin Python. `build_forecast_patch.py` requiere el árbol actual de FORECAST_CONNEXA y rechaza cambios de contexto inesperados.

## Recuperación

Si falla una migración, su transacción se revierte; el reset manual previo ya confirmado permanece y deja la tabla vacía. Se conserva la posibilidad de regenerar los datos de prueba. No se entrega un rollback que vuelva a llamar seguridad al sobrestock. Después de aplicar y cargar, cualquier corrección debe ser una nueva migración hacia adelante. Conservar el paquete y sus hashes; no ejecutar las migraciones históricas de políticas por grupo como recuperación.
