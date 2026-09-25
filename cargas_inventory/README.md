# Carga inicial de inventory en TEST

## Proceso reutilizable por ambiente

`load_environment.py` reemplaza el uso operativo de `load_test.py` cuando el
destino se configura mediante `PDD_ENV_PATH`. Admite `TEST` y `PROD`, genera
una captura inmutable desde `diarco_data`, resuelve los UUID por códigos de
negocio dentro del destino y separa preview, aplicación y verificación.

Las altas de `inv_product_site_replenishment` siempre nacen activas. El estado
de la política de reposición es independiente de `inv_product_site.active` y
no debe copiarse desde él. El proceso preserva filas existentes y se detiene
si sus parámetros, clasificación o selección logística difieren de la captura.
No modifica silenciosamente datos ya administrados por Connexa.

La misma captura incorpora `replenishment_method` desde `abastecimiento` y el
`lead_time_days` de entrega desde CD usando proveedor general 0 por sucursal.
Cuando esa combinación no está informada, conserva la regla aprobada en TEST:
lead time cero. Los otros métodos mantienen lead time NULL. De esta manera la
carga inicial no necesita ejecutar luego los dos completadores históricos.

```bash
# Captura nueva desde SGM/diarco_data. La carpeta no debe existir.
python cargas_inventory/load_environment.py \
  --directory /ruta/captura-AAAAMMDD \
  --environment PROD \
  --extract \
  --confirm-production connexa_platform_ms

# Preview de PROD; no persiste datos.
python cargas_inventory/load_environment.py \
  --directory /ruta/captura-AAAAMMDD \
  --environment PROD \
  --confirm-production connexa_platform_ms

# Aplicación exacta del preview revisado.
python cargas_inventory/load_environment.py \
  --directory /ruta/captura-AAAAMMDD \
  --environment PROD \
  --apply \
  --confirm-production connexa_platform_ms \
  --preview-sha256 SHA256_INFORMADO_POR_EL_PREVIEW

# Verificación posterior, sólo lectura.
python cargas_inventory/load_environment.py \
  --directory /ruta/captura-AAAAMMDD \
  --environment PROD \
  --verify \
  --confirm-production connexa_platform_ms
```

Preview y verificación abren una transacción normal porque PostgreSQL no
permite crear/cargar tablas temporales en una transacción `READ ONLY`. En esos
modos el código no ejecuta DML sobre tablas persistentes y termina siempre con
`ROLLBACK`; las tablas de staging se declaran `ON COMMIT DROP`.

En PROD también se exige
`PDD_OPERATIONAL_ALLOW_PRODUCTION=true`, base exacta
`connexa_platform_ms` y coincidencia entre el ambiente solicitado y el
configurado. La aplicación usa una transacción, bloqueo asesor, locks de las
tres entidades y `app.actor` para conservar auditoría.

Mientras SGM continúe siendo fuente maestra, este proceso puede repetirse para
incorporar pares faltantes. Los cambios sobre filas ya existentes quedan
reportados como conflictos y requieren una promoción versionada específica;
el bootstrap no implementa sincronización destructiva ni sobrescrituras.
El factor SKU/proveedor se mantiene como proceso separado porque actualiza
relaciones maestras preexistentes y requiere su propia revisión de cambios.

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

`load_test.py` carga reposición, clasificación de compra y selección logística. En el checkout local lee las credenciales de `PDD/backend/.env`; esa ruta no se usa en el servidor desplegado, donde la configuración PDD está en `/etc/connexa/pdd-test.env`. No escribe secretos en los resultados y rechaza cualquier destino distinto de `connexa_platform_test`. Requiere Python, psycopg2 y python-dotenv.

La carga debe preservar de forma independiente los estados `product_site.active` y `replenishment.active`. No se debe desactivar una reposición válida por copiar el estado del producto-sucursal; esta condición forma parte del control previo a una nueva carga.

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
