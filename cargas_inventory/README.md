# Carga inicial de inventory en TEST

## Completar modalidad de reposición

Después de cargar los pares, ejecutar `load_replenishment_method.py`. Completa `inventory.inv_product_site_replenishment.replenishment_method` desde `src.base_productos_vigentes.abastecimiento`, cruzando `c_articulo` y `c_sucu_empr` con los códigos de producto y sucursal. `c_proveedor_primario` se conserva en la captura como referencia, pero no forma parte de la clave ni se modifica en TEST.

| abastecimiento | replenishment_method |
|---:|---|
| 0 | Entrega desde CD |
| 1 | Entrega Desde el Proveedor |
| 2 | Cross Docking |
| 3 | Entrega desde QX |

```powershell
python PDD/cargas_inventory/load_replenishment_method.py --directory PDD/data/cargas_inventory/NUEVA_CAPTURA_METODO --extract
python PDD/cargas_inventory/load_replenishment_method.py --directory PDD/data/cargas_inventory/NUEVA_CAPTURA_METODO --apply
python PDD/cargas_inventory/load_replenishment_method.py --directory PDD/data/cargas_inventory/NUEVA_CAPTURA_METODO --verify
```

Este paso es parte de la carga completa, también para preparar la futura adaptación a producción. Solo admite TEST actualmente. Rechaza códigos desconocidos/NULL y pares duplicados en origen; completa métodos NULL, conserva valores coincidentes y se detiene ante valores existentes distintos. Es repetible y deja captura con hash, pendientes y resultado. La verificación usa tablas temporales y revierte la transacción: no modifica tablas persistentes. Las actualizaciones aplicadas mantienen triggers, auditoría y revisión de fila habilitados; no cambian días ni `inv_product_site.supply_type`.

## Carga de parámetros y clasificaciones

### Plazo de entrega para abastecimiento desde CD

Después del paso de métodos, `load_lead_time.py` completa `lead_time_days` únicamente donde `replenishment_method = 'Entrega desde CD'`. Obtiene el proveedor primario del par artículo/sucursal en `src.base_productos_vigentes` y cruza `c_proveedor_primario = t055.c_proveedor`, `c_sucu_empr = t055.c_sucursal`. El valor es `src.t055_lead_time_b2_sucursales.dias_entrega`, en días, sin sumarlo a preparación ni tránsito.

```powershell
python PDD/cargas_inventory/load_lead_time.py --directory PDD/data/cargas_inventory/NUEVA_CAPTURA_LEAD_TIME --extract
python PDD/cargas_inventory/load_lead_time.py --directory PDD/data/cargas_inventory/NUEVA_CAPTURA_LEAD_TIME --apply
python PDD/cargas_inventory/load_lead_time.py --directory PDD/data/cargas_inventory/NUEVA_CAPTURA_LEAD_TIME --verify
```

Proveedor/sucursal sin coincidencia, días NULL o inválidos quedan en `pending.csv`, sin asignar un plazo por defecto. Cero informado explícitamente es válido. Se rechazan claves de proveedor/sucursal duplicadas o inválidas. Se completan solo plazos NULL; los valores existentes diferentes detienen la ejecución para revisión. Conserva captura, hash, auditoría y verificación; restringido a TEST. No modifica otros métodos de reposición.

`load_test.py` carga reposición, clasificación de compra y selección logística. Lee las credenciales de `PDD/backend/.env`, no las escribe en los resultados y rechaza cualquier destino distinto de `connexa_platform_test`. Requiere Python, psycopg2 y python-dotenv.

Desde `C:\PROYECTOS\ETL`:

```powershell
# Captura nueva y validación sin cambios persistentes en TEST
python PDD/cargas_inventory/load_test.py --directory PDD/data/cargas_inventory/NUEVA_CAPTURA --extract
# Aplicación de la misma captura validada
python PDD/cargas_inventory/load_test.py --directory PDD/data/cargas_inventory/NUEVA_CAPTURA --apply
# Verificación independiente posterior, solo lectura
python PDD/cargas_inventory/verify_test.py --directory PDD/data/cargas_inventory/NUEVA_CAPTURA
```

La carpeta de extracción debe ser nueva. La aplicación verifica los SHA256 de la captura y resuelve los UUID por códigos de negocio en el destino. Se ejecuta en una transacción con bloqueo de las tres tablas durante la carga, sin deshabilitar auditoría. Los inserts preservan filas existentes; no sincronizan cambios posteriores de la fuente. Una repetición no agrega pares o selecciones existentes ni una segunda clasificación activa del mismo tipo. Antes de repetir después de un error de conexión, comprobar el estado real de TEST: un resultado local incompleto no demuestra rollback.

## Reglas autorizadas

- Universo: pares de `src.base_productos_vigentes` que existen en los maestros de inventory; se conserva `inv_product_site.active`, sin filtrar por habilitación legacy.
- Stock: último cierre de `src.base_stock_sucursal`. `q_dias_stock` → `target_stock_days`; `q_dias_sobre_stock` → `overstock_days`; `pedido_min` → `minimum_order_quantity`.
- Si falta toda la fila de stock: ambos días y preparación en cero. Esto no carga cantidades físicas de stock.
- Si existe fila de stock pero falta alguno de los dos días: el par queda pendiente, sin insertar. **No usar `--zero-existing-null-days`**, opción que altera esta regla.
- Preparación NULL: cero. Mínimo obligatorio válido; múltiplos y otros plazos no se inventan.
- Clasificación: `src.t050_articulos`, réplica de T050_ARTICULOS. Se resuelve el catálogo con las siete opciones activas 1,2,3,4,5,6,100. Código 100 es explícito, no un reemplazo de NULL. Una clase activa por producto y tipo, vigente desde la fecha de carga.
- Logística: solo productos con exactamente una variable activa y principal, con factor y unidad/peso utilizables. Los demás quedan pendientes.
- No se generan snapshots de previsiones: `spl_forecast_planning_input` requiere resultados reales del proceso FORECAST.

## Evidencia y producción

Cada carpeta contiene captura CSV, manifest con cierre y hashes, preview/result JSON, verificación y CSV de pendientes. La verificación independiente está orientada a la carga inicial: exige coincidencia completa con esa captura y no pretende validar posteriores ediciones legítimas.

Para producción se reutilizan consultas, reglas y resolución por códigos; habrá que habilitar expresamente otro destino, hacer una captura nueva, validar los maestros y revisar filas existentes y pendientes antes de ejecutar. Este script no permite cargar producción. La integración de los lectores PDD y FORECAST_CONNEXA se realiza aparte de esta carga.

La ejecuci?n complementaria usa `PDD/data/cargas_inventory/20260917_completar_dias`, copia de los CSV y manifest originales, para conservar la evidencia hist?rica de la primera carga. El cargador agrega solo filas faltantes.
