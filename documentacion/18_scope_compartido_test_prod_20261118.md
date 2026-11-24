# Reutilizacion de scopes entre TEST y PROD (backend 0.20.12)

El incidente de TEST del 18/11 se produjo porque PROD ya habia registrado el
checksum `7a07ce5af8c95fa9926cc7f4476917a868f5835655cf6f4d1e5ae192a6cd8d22`
en el scope `c53e8786-04a0-4bd9-833f-f8915375c181`. TEST buscaba un
descendiente de su propio scope anterior e intento insertar una copia.

La captura ahora calcula el checksum dentro de la misma transaccion. Si ya
existe una version con el mismo contenido, la reutiliza tras comprobar estado,
conteos, hashes de articulos y pares, y politicas de exclusion. Cada ambiente
conserva su propio binding runtime. Si las features del scope reutilizado no
alcanzan el corte requerido, se preparan antes de la aprobacion/activacion.
Una coincidencia de checksum con controles incompatibles sigue bloqueada.

## Prueba en TEST

Copiar `pdd-backend-0.20.12.zip` y `.zip.sha256` a `/tmp` de `diarco-test`.
Comprobar que no haya una corrida diaria en curso antes de promover:

```bash
cd /tmp
hostname -f
sha256sum -c pdd-backend-0.20.12.zip.sha256
unzip -p pdd-backend-0.20.12.zip tools/deploy_backend.sh > pdd-deploy-0.20.12.sh
test -s pdd-deploy-0.20.12.sh && bash -n pdd-deploy-0.20.12.sh
sudo bash /tmp/pdd-deploy-0.20.12.sh TEST 0.20.12 stage
sudo bash /tmp/pdd-deploy-0.20.12.sh TEST 0.20.12 promote
sudo bash /tmp/pdd-deploy-0.20.12.sh TEST 0.20.12 deploy
sudo bash /tmp/pdd-deploy-0.20.12.sh TEST 0.20.12 status
```

Despues del precheck READY, ejecutar `PDD_OPERATIONAL_DAILY_MASTER` una sola
vez y verificar el log `Mantenimiento de scope diario`, la corrida DAILY_DECAS
y la publicacion del backlog. El scope puede ser el mismo UUID que usa PROD;
el binding debe quedar en `environment='TEST'` y el destino operativo en
`connexa_platform_test`. No eliminar scopes previos.

PROD permanece en 0.20.10 durante esta prueba. Una vez que TEST termine y se
revisen sus resultados, el mismo paquete se puede desplegar en PROD cambiando
`TEST` por `PROD` en los comandos anteriores y ejecutandolos en `diarco-ms`.
