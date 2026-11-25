# PDD — Evaluación del puente temporal CONNEXA → SGM → Valkimia

**Fecha:** 2026-11-24.  
**Estado:** factibilidad condicionada; análisis de código y contratos del repositorio, sin prueba contra las bases ni validación funcional de SGM/Valkimia.  
**Alcance:** viajes aprobados del CD 41, durante el retraso del desarrollo de Valkimia.

**Implementación solicitada:** la publicación se especifica como [API BACK en la DMZ](23_especificacion_funcional_api_puente_connexa_sgm_valkimia_20261124.md). El flujo Prefect citado abajo es únicamente evidencia del circuito anterior, no el runtime propuesto.

## Conclusión

**Sí se puede intentar reutilizar el mecanismo de alta de transferencias del circuito anterior como adaptador temporal**, siempre que SGM acepte procesar esas altas con la misma semántica que una transferencia propia y que el resultado pueda correlacionarse por línea con PDD. El flujo y los procedimientos disponibles ofrecen una ruta técnica plausible. **No se puede ejecutar el flujo viejo sin cambios con `pdd_valkimia_import_line`**: su origen, identidad, reglas de cantidad y retorno pertenecen a `supply_planning.spl_distribution_transfer`.

El puente debe conservar en CONNEXA el viaje, la necesidad, las reservas, los estados y la atribución de cantidades. SGM operaría la transferencia ya creada (stock, preparación, remito y funciones posteriores). El alta manual/automática de nuevas transferencias desde SGM se deshabilitaría para el mismo alcance al activar el puente; las transferencias SGM anteriores deben seguir su curso.

## Qué se puede reutilizar

| Pieza anterior | Uso transitorio posible | Cambio indispensable |
| --- | --- | --- |
| `publicar_transferencias_sgm.py` | Conexiones, consulta de stock/ACO y estructura de staging como referencia | Sustituir por lectura de importaciones y líneas PDD vinculadas a viajes aprobados. No ejecutar su selección `PRECARGA_CONNEXA`, su asignación FIFO de stock ni su actualización de cabeceras antiguas. |
| `[repl].[TRANSF_CONNEXA_IN]` | Cola técnica si su DDL, índices y permisos lo permiten | Registrar identidad PDD, revisión, hash y cantidad/unidad exactas por línea, con unicidad real. Evitar mezclar filas antiguas y PDD sin filtro de origen. |
| `repl.SP_PUBLICAR_TRANSF_CONNEXA_SGM` | Invocar `SD03_TRANSF_ALTA_DETALLE` y obtener `u_id_sincro` | Validar que el procedimiento remoto genera la misma transferencia operativa que SGM habría generado, conserva usuario/origen y permite identificar duplicados. |
| `repl.SP_PUBLICAR_TRANSF_CONNEXA_VK` | Invocar `SD03_TRANSF_ALTA_DETALLE_VK` usando el `u_id_sincro` de SGM | Validar tipos, factor, productos pesables, parciales y semántica de respuesta; verificar el efecto real en Valkimia. |
| `flujo_publicar_transferencias_sgm_vk.py` | Orden de etapas, lotes, límites de ejecución y `AUTOCOMMIT` para linked servers | Reemplazar prepublicación y retorno por línea PDD; no actualizar `spl_distribution_transfer.status_id` 80/10/85. |

El código de los SP muestra **dos altas sucesivas**, primero en `[DiarcoP]` y luego en `[VALKIMIA]`, con `u_id_sincro` como enlace. Eso demuestra el diseño del flujo, no su comportamiento actual desplegado. El script del SP de retorno por cabeceras se invoca desde Python, pero no aparece en los archivos de procedimientos revisados: hay que recuperar su definición instalada antes de evaluar su reutilización.

## Adaptación mínima desde PDD

1. Seleccionar únicamente `pdd_valkimia_import_line` de `pdd_valkimia_import` vinculadas a `pdd_dispatch_trip` aprobado y su `pdd_dispatch_trip_line`. Usar `valkimia_import_line_uuid` como identidad estable, `dispatch_trip_line_uuid` y `dispatch_trip_uuid` como trazabilidad. El `valkimia_import_line_id` es un `bigint` local, no el UUID de publicación.
2. Congelar el payload aprobado por línea y parada: CD 41, sucursal, artículo, cantidad, unidad, factor logístico, fecha y revisión. Confirmar mapeo de `imported_quantity`/`planned_quantity` a `q_bultos` y `q_factor` con ejemplos reales. No recalcular una cantidad distinta con el FIFO del script anterior: rompería la aprobación y las asignaciones DECAS. Si falta stock, registrar rechazo o bloqueo de la línea para resolución explícita.
3. Insertar en staging mediante operación idempotente y transaccional por `ambiente + valkimia_import_line_uuid + revisión`, con hash del payload. Guardar relación `línea PDD ↔ fila staging ↔ u_id_sincro SGM ↔ referencia VK`; exigir restricción única y consultar el resultado remoto antes de reintentar un timeout. El chequeo actual de UUID en staging no cubre una respuesta perdida tras crear la transferencia remota.
4. Ejecutar SGM y luego VK sobre **ese lote identificado**, con aislamiento por ambiente y origen. Los SP actuales reclaman cualquier fila pendiente/error de `TRANSF_CONNEXA_IN`; si la cola es compartida, se requiere filtro o cola separada y una decisión de operación para pendientes históricos. No arrancar el loop global sin ese aislamiento.
5. Registrar por línea los resultados SGM/VK en PDD y mantener `UNKNOWN` ante resultado ambiguo. Un `processed=0` o un `ERROR` de staging no demuestra que la alta remota no ocurrió. El retorno por cabeceras del modelo anterior sólo informa un agregado y escribe estados ajenos a PDD; hay que reemplazarlo por conciliación por línea y referencias externas. Después, sondear preparación, remitos y saldos conforme a [la especificación de integración](21_integracion_connexa_sgm_valkimia_intnecin_intsalout_20261119.md).

**Punto de unidades:** el script anterior redondea `units_per_package` a entero y usa `qty_requested` como bultos; el SP VK convierte `q_factor` a `DECIMAL(3,0)` y fija `M_VENDE_POR_PESO='N'`. PDD admite `UNIT` y `KG` con seis decimales. El puente debe bloquear artículos pesables o factores/fracciones no representables hasta que SGM valide un mapeo y un procedimiento aptos. No truncar ni redondear silenciosamente.

## Corte del alta en SGM sin perder sus demás funciones

El corte debe aplicarse a **todos los puntos que crean transferencias nuevas en SGM para CD 41 y el alcance migrado** (pantallas, APIs, jobs, importaciones y usuarios), manteniendo consultas, edición permitida, preparación, remitos, seguimiento, correcciones y procesamiento de transferencias ya abiertas. Hay que inventariar esos puntos y validar los permisos efectivos. El usuario técnico CONNEXA debe conservar una vía explícita y auditable para `SD03_TRANSF_ALTA_DETALLE` y `SD03_TRANSF_ALTA_DETALLE_VK`; un bloqueo global del procedimiento impediría el puente.

Definir un instante de corte y conciliar los pendientes SGM/CONNEXA antes de habilitar el primer lote. Impedir doble alta para el mismo artículo/sucursal/necesidad por canales distintos, con identidad verificable y revisión operativa de transferencias anteriores. El interruptor de reversa pausa **nuevas publicaciones PDD** y deja activos sondeo, remitos y resolución de lo ya publicado. Reabrir altas SGM requiere conciliar primero el saldo y las transferencias abiertas; no se eliminan filas externas para retroceder.

## Condiciones para un piloto en TEST

- Confirmar con SGM el DDL y la versión **desplegada** de staging y SP, permisos, efectos de `SD03_TRANSF_ALTA_DETALLE`, vínculo de `u_id_sincro`, criterio de duplicado y todas las vías de alta SGM que se deshabilitarán. Confirmar si la alta VK por ese SP sustituye efectivamente los cambios pendientes de Valkimia.
- Probar una línea y dos líneas del mismo viaje, dos viajes al mismo artículo/sucursal, reintento tras timeout en cada SP, una caída entre SGM y VK, factor fuera de rango, pesable, stock insuficiente, preparación parcial y remito múltiple. Verificar que cada línea tenga una sola alta remota y que SGM conserve las funciones posteriores.
- Verificar la correlación de salida/remito a la línea PDD. `IntSalOUT` no expone `INIId` según la planilla revisada; sin vínculo oficial `INIId ↔ ISOId`/remito o token preservado, no se puede acreditar despacho ni liberar saldo automáticamente.
- Resolver el bloqueo actual del cálculo diario: `backend/pdd_backend/jobs/backlog.py` detiene la publicación si hay importaciones `PENDING`, `ACCEPTED` o `PARTIAL`. El piloto puede mantener esa protección y operar con intervención controlada, pero no escalar el puente como operación diaria normal hasta implementar reservas y conciliación por línea.

**Decisión de avance:** construir un adaptador PDD para el mecanismo legacy y probarlo en TEST es razonable. La activación productiva queda condicionada a las comprobaciones anteriores y a una prueba integral de SGM → VK → remito → conciliación PDD. Este documento no constata que las versiones desplegadas de los SP coincidan con los archivos del repositorio.

## Evidencia de repositorio

- `../../ETL_DIARCO/scripts/pull/flujo_publicar_transferencias_sgm_vk.py`: etapas, SP y retorno antiguo.
- `../../ETL_DIARCO/scripts/pull/publicar_transferencias_sgm.py`: lectura `PRECARGA_CONNEXA`, stock/FIFO, staging y actualización de cabeceras.
- `../../ETL_DIARCO/scripts/pull/SQL_Stored_Procedures/SP_PUBLICAR_TRANSF_CONNEXA_SGM.sql` y `SP_PUBLICAR_TRANSF_CONNEXA_VK.sql`: altas remotas, selección de pendientes y estados de staging.
- `../backend/contracts/sql/planning_migration_v2_7.sql` y `../PDD - Migracion Correctiva Estados Valkimia v2.8.sql`: identidades, vínculos y cantidades PDD.
- `../backend/pdd_backend/jobs/backlog.py`: guard de importaciones activas.
