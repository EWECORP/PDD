# Impacto en PDD y FORECAST_CONNEXA

La decisión de parámetros directos reemplaza para este paquete el diseño previo por local/grupo. No se considera que BACK adeude la implementación del paquete de políticas del 11/09; éste es un cambio nuevo sobre TEST, confirmado con el usuario.

## Matriz de fuentes final

| Dato | Fuente nueva | Consumidores |
|---|---|---|
| Días objetivo | `inv_product_site_replenishment.target_stock_days` | PDD `q_dias_stock` / FORECAST `Q_DIAS_STOCK` mediante adaptador |
| Días adicionales | `inv_product_site_replenishment.overstock_days` | PDD `q_dias_sobre_stock` / FORECAST `Q_DIAS_SOBRE_STOCK` |
| Mínimo por par | `inv_product_site_replenishment.minimum_order_quantity` | FORECAST `PEDIDO_MIN`; independiente de mínimo proveedor |
| Preparación | `inv_product_site_replenishment.preparation_days` | FORECAST `DIAS_PREPARACION`; no sustituir por lead time automáticamente |
| Modalidad/origen | `inv_product_site.supply_type`, `supplying_site_id` | Conservar sucursal de necesidad, UUID/código de sitio abastecedor separados |
| Variable logística | Selección `inv_product_planning_logistics` → `inv_logistic_variable` | Nuevo S20 lee vista `inv_planning_logistics_v` |
| Proveedor elegible/condiciones | `inv_product_supplier` del proveedor de ejecución | Se mantiene lo confirmado; no filtrar proveedor primario |
| Stock, ventas y pendientes | Fuentes transaccionales actuales con corte explícito | Este paquete no crea hechos ni mueve diarco_data |

## FORECAST: parche preparado

`application/FORECAST_CONNEXA.patch` cambia el lector local `forecast_compare/extend.py` y el diagnóstico `field_status.py`. Las copias completas de revisión están en `application/forecast_preview/`.

- `Q_DIAS_STOCK` deja de venir de `expected_stock_days` y se lee del parámetro activo `target_stock_days`.
- `Q_DIAS_SOBRE_STOCK` deja de leer `safety_stock_days` y utiliza `overstock_days`.
- La consulta logística usa la selección explícita utilizable; falta de selección o atributos inválidos no se convierten a uno/cero.
- Se conservan IDs y revisiones de parámetro y selección.
- Se serializan Decimal como cadenas exactas en la evidencia JSON; esto evita el error de serialización que aparecería al cambiar float8 por numeric en psycopg2.
- Se conserva la demanda, la cardinalidad por artículo/local/proveedor, las constantes ya confirmadas, el peso en kg y el estado **LOCAL_S20_DRAFT / publication_ready=false**.

Aplicación posterior, con la DB ya migrada y el lector detenido hasta coordinar el cambio:

```powershell
git -C FORECAST_CONNEXA apply --check --ignore-space-change C:/PROYECTOS/ETL/PDD/entregables/backend_inventory_planning_20260914/application/FORECAST_CONNEXA.patch
git -C FORECAST_CONNEXA apply --ignore-space-change C:/PROYECTOS/ETL/PDD/entregables/backend_inventory_planning_20260914/application/FORECAST_CONNEXA.patch
```

El ajuste de whitespace permite revisar/aplicar contra el checkout CRLF. No se aplicó aquí porque TEST conserva aún las columnas antiguas. El parche parte de los cambios locales existentes del piloto; no sobrescribe una versión de producción ni sustituye archivos completos sin comprobar contexto.

## FORECAST: integración S10/S30/S40

El parche cubre S20 local. BACK/equipo FORECAST deben incorporar el contrato en el circuito completo antes de activarlo:

1. S10 toma y congela parámetros y selección una vez por ejecución; ventas/stock por los pares elegibles sin refiltrar proveedor legado. S20/S30 reutilizan esa evidencia. Repetir `--verify-master` en otra fecha no equivale a reproducción histórica.
2. S40 persiste `spl_forecast_planning_input` junto con cada resultado del circuito nuevo. El archivo `application/read_parameters_by_codes.sql` permite resolver IDs por código sin equiparar UUID de esquemas.
3. `purchase_unit` del resultado ya es float8: su truncamiento está en `safe_int` del publicador, no exige otra migración. Adaptar el nuevo publicador para preservar factor fraccionario y validar las cantidades efectivas.
4. `windows` sigue siendo integer en TEST. No truncar días canónicos: guardar los decimales exactos en el snapshot y adaptar el DTO/frontend nuevo a esos campos. El cálculo vigente de ventana publicado excluye sobrestock; mantener esa semántica. Si algún consumidor exige una ventana entera, documentar y probar el redondeo sólo de ese campo derivado; no redondear los días maestros ni escoger una regla implícita.
5. `last_purchase_quantity` sigue integer en TEST. No está resuelta una publicación fraccionaria de último ingreso por esta migración: si se utiliza un valor fraccionario, conservarlo en evidencia/DTO nuevo y no truncarlo al publicar. Evaluar su cambio de tipo con dependencias/consumidores como modificación posterior; no es necesario para renombrar los días ni para el S20 local.
6. `cod_cd` sigue varchar heredado. El snapshot separa UUID y código de suministro; el nuevo API debe exponerlos diferenciados. No introducir sitios 41CD/82CD ni consolidar compras en FORECAST: eso ocurre después de los ajustes del comprador.
7. El comprador requiere usuario de ejecución; los gráficos y detalle requieren los generadores existentes; tránsito/transferencias requieren lectores/fechas. No son tablas maestras faltantes que deban inventarse en Flyway. `PEDIDO_SGM` permanece retirado del contrato nuevo, sin borrar por este paquete `forcast`/`forecast` de resultados históricos.

No se incorporó configuración de algoritmos a reposición: modelo de forecasting y parámetros de compra son responsabilidades distintas. No se cambia el algoritmo del piloto ni se activa el publicador productivo con este paquete.

## PDD: adaptador y evidencia sin más DDL

`application/pdd_parameter_adapter.py` es un adaptador entregado, no instalado automáticamente. Recibe filas de `_read_source_stock` (`codigo_articulo`, `sucursal`) y el resultado de `read_parameters_by_codes.sql`, valida claves/cobertura y sustituye ambos días en una copia de las filas. No modifica existencias, OC, pendientes ni fórmulas.

Integración requerida en `pdd_backend/jobs/daily_decas.py`:

1. Después de leer `source_branches`, resolver parámetros contra el engine de **CONNEXA TEST**, no contra el engine de diarco_data. Usar los pares de la corrida y una transacción de lectura consistente.
2. Aplicar `apply_parameters(source_branches, parameter_rows)` antes de `build_branch_position`. El adaptador bloquea parámetros ausentes/duplicados e inventario inactivo; completar las habilitaciones de transferencia del scope según su contrato.
3. Copiar `source['_planning_input']` a `row['explanation']['planning_input']`. El campo JSON `pdd_branch_stock_position.explanation` ya existe. Incluir la identidad/revisión y valores en el checksum de entrada o en el checksum de la fuente canónica.
4. Registrar un `pdd_source_snapshot` adicional para la lectura de inventory, con fecha, relación, conteo y checksum. Conservar la fotografía/resumen para reanudación; no releer maestros actuales y afirmar que es la misma corrida.
5. Mantener en esta etapa la política actual de lead time y la logística snapshot PDD. El adaptador sólo cambia los dos días pedidos. Adoptar lead_time_days de inventory o sustituir unidades logísticas requiere comparar ese efecto separado; preparación y plazo de abastecimiento no se equiparan aquí.

Estas columnas JSON y snapshots existen en TEST: no hace falta agregar otra tabla operativa PDD para esta evidencia. La lógica de integración debe completarse al activar la fuente; entregar Flyway no cambia el lector actual.

## Qué ocurre con las doce solicitudes de la auditoría anterior

| Tema anterior | Tratamiento en este paquete |
|---|---|
| Maestro único y ambos días | Resuelto por decisión directa y migración 01 |
| Reglas generales, publicación de versiones, clasificación/perfiles | Fuera del alcance confirmado; las tablas DRAFT existentes quedan como antecedente |
| Concurrencia y auditoría | Revisión + triggers + contrato DAO; snapshots conservan parámetros efectivos |
| Selección logística ambigua | Selección explícita, sin deduplicar ni alterar principales existentes |
| Valores no válidos | Constraints para parámetros nuevos; cobertura/calidad logística debe validarse al cargar/consumir |
| Pares inactivos, mínimos y máximos legacy | No se corrige masivamente inventory; elegibilidad por consumidor y mínimo explícito nuevo |
| UUID entre esquemas | Resolver códigos e IDs del dominio correcto; conservar IDs separados en evidencia |
| Auditoría/outbox general de maestros, grupos/zonas, comercial, algoritmos | No se crean nuevas infraestructuras generales para este ajuste de parámetros |

Los informes 07–09 conservan el estado observado; este paquete define la solución acordada posterior. No deben interpretarse sus recomendaciones por grupo como dependencias obligatorias de la nueva nivelación.
