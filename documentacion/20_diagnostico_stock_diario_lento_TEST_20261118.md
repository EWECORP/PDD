# Diagnostico de DAILY_DECAS lento en TEST (18/11/2026)

La corrida Prefect `tricky-flounder` (`a2906bdc-a719-4301-8a3c-b06d726188b0`)
activo el scope `25349db5-f7bb-4008-8b85-429304a12b09`, verifico 40.374
pares Inventory y termino PDVB. Desde las 10:32 ART permanece en la tarea
`PDD - Construir posiciones y necesidades D y S`.

En `diarco_data`, PostgreSQL mantenia activa una consulta sobre
`src.base_stock_sucursal` durante casi tres horas, sin espera por bloqueo.
El plan estimaba **1** par para el scope nuevo, que realmente tiene **40.374**,
y elegia un `Nested Loop` con ordenacion/ventana sobre la tabla de stock.
La consulta antigua ordenaba el stock de toda la fecha antes de cruzarlo con
los pares del scope. La tabla tiene alrededor de 1,3 millones de filas y 631 MB.

En 0.20.13 la lectura de sucursales y CD busca para cada par/articulo la
ultima extraccion mediante el indice `(codigo_sucursal,codigo_articulo)` y
`LEFT JOIN LATERAL ... LIMIT 1`. Mantiene la fecha efectiva de stock y el
criterio de extraccion mas reciente. La lectura real de TEST devolvio
40.374 pares y 2.122 articulos CD en **0,67 segundos** sin escribir datos.

## Recuperacion en TEST

La corrida actual sigue usando el codigo y el plan antiguos; desplegar una
version nueva no cambia la consulta que ya esta ejecutandose. Cancelar esa
corrida desde Prefect y esperar a que su proceso y consulta SQL terminen antes
de promover el backend. Las publicaciones previas siguen vigentes; la
renovacion del scope y el PDVB ya completados se pueden reutilizar si el
pipeline confirma sus checksums.

Copiar `pdd-backend-0.20.13.zip` y su `.sha256` a `/tmp` de `diarco-test`:

```bash
cd /tmp
sha256sum -c pdd-backend-0.20.13.zip.sha256
unzip -p pdd-backend-0.20.13.zip tools/deploy_backend.sh > pdd-deploy-0.20.13.sh
test -s pdd-deploy-0.20.13.sh && bash -n pdd-deploy-0.20.13.sh
sudo bash /tmp/pdd-deploy-0.20.13.sh TEST 0.20.13 stage
sudo bash /tmp/pdd-deploy-0.20.13.sh TEST 0.20.13 promote
sudo bash /tmp/pdd-deploy-0.20.13.sh TEST 0.20.13 deploy
sudo bash /tmp/pdd-deploy-0.20.13.sh TEST 0.20.13 status
```

Volver a ejecutar `PDD_OPERATIONAL_DAILY_MASTER` una vez y verificar
DAILY_DECAS, backlog y el estado final. Esperar esta validacion antes de
promover PROD. El ZIP 0.20.13 tambien conserva los horarios efectivos de
Prefect (PROD 21:00, TEST 22:15) para que `deploy` no los revierta.
