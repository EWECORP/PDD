# PDD — Despliegue y prueba de la API backend

Versión: **1.0**  
Backend: **0.11.0**  
Ambiente inicial: **connexa_platform_test**  
Servicio: **`/api/v1/pdd`**

## 1. Resultado del desarrollo

La API implementa las 15 operaciones del contrato OpenAPI versionado:

- estado, resumen y catálogos;
- backlog con filtros, orden y cursor firmado;
- detalle, atribución y explicación reproducible;
- consulta de corridas y fuentes;
- alta, edición, activación, cancelación, cierre e historial E/C/A.

No expone PostgreSQL al navegador y no ejecuta cálculos analíticos. Consume la
foto ya publicada en `stock_management`.

## 2. Seguridad

El modo predeterminado es `proxy` y falla cerrado. El proxy corporativo debe:

1. validar el JWT del usuario;
2. eliminar cualquier `X-Connexa-User`, `X-Connexa-Roles` y
   `X-PDD-Proxy-Secret` recibido desde Internet;
3. inyectar esos tres headers con la identidad validada;
4. conservar `Authorization: Bearer ...`;
5. comunicarse con la API mediante una red confiable o localhost.

Roles aceptados:

- `PDD_VIEWER`;
- `PDD_BUYER`;
- `PDD_SUPERVISOR`;
- `PDD_AUDITOR`;
- `PDD_TECHNICAL`.

`PDD_BUYER` crea y modifica DRAFT propios. Solo `PDD_SUPERVISOR` activa,
cancela o cierra. La identidad persistida siempre surge de autenticación, no
del contenido enviado por el navegador.

## 3. Base de datos

Crear fuera del repositorio el rol LOGIN `connexa_pdd_api` y administrar su
contraseña con el mecanismo de secretos de Connexa. Luego ejecutar, con un
administrador y `ON_ERROR_STOP`, el script:

```text
PDD - Grants API PDD connexa_platform_test v1.0.sql
```

El rol puede leer la foto PDD y solo modificar las entidades E/C/A, su historial,
idempotencia y auditoría. No puede publicar PDVB, stock, D/S ni backlog.

## 4. Instalación en `/srv/PDD/backend`

```bash
cd /srv/PDD/backend
source /srv/FORECAST/venv/bin/activate
python -m pip install -e .
python -m pip show diarco-pdd-backend fastapi uvicorn
```

La versión esperada de `diarco-pdd-backend` es `0.11.0`.

Copiar `.env.api.example` a `.env.api`, completar las credenciales del rol API
y generar dos secretos diferentes de al menos 32 bytes:

```bash
openssl rand -hex 32
openssl rand -hex 32
```

Guardar uno en `PDD_API_PROXY_SECRET` y el otro en `PDD_API_CURSOR_SECRET`.
No imprimirlos en logs ni entregarlos al frontend.

Permisos recomendados:

```bash
chmod 600 /srv/PDD/backend/.env.api
```

## 5. Validación previa

```bash
cd /srv/PDD/backend
source /srv/FORECAST/venv/bin/activate
export PDD_ENV_PATH=/srv/PDD/backend/.env.api
python tools/validate_frontend_contract.py
python tools/validate_api.py
python tools/validate_api_write_rollback.py
python -m pytest -q
```

`validate_api.py` es de solo lectura. Comprueba las 15 rutas y consulta la foto
vigente, resumen, muestra de backlog, detalle, explicación, catálogos, corrida
y necesidades dirigidas.

`validate_api_write_rollback.py` recorre alta, replay idempotente, edición,
activación, cancelación, historial y auditoría en una transacción que siempre
finaliza con rollback; además comprueba que quedaron cero filas persistidas.

## 6. Servicio systemd

```bash
cp /srv/PDD/backend/pdd-api.service /etc/systemd/system/pdd-api.service
systemctl daemon-reload
systemctl enable --now pdd-api.service
systemctl status pdd-api.service --no-pager
journalctl -u pdd-api.service -n 100 --no-pager
```

El servicio escucha por defecto en `127.0.0.1:8088`. No se debe abrir ese
puerto directamente a Internet.

Control sin autenticación funcional:

```bash
curl --fail --silent http://127.0.0.1:8088/healthz
```

Respuesta esperada:

```json
{"status":"ok","version":"0.11.0"}
```

## 7. Prueba detrás del proxy

Una vez configurado el gateway:

```bash
curl --fail --silent \
  -H "Authorization: Bearer TOKEN_CORPORATIVO" \
  https://HOST_CONNEXA/api/v1/pdd/status
```

Luego comprobar:

```text
GET /api/v1/pdd/dashboard/summary
GET /api/v1/pdd/backlog?pageSize=10&needType=D,S
GET /api/v1/pdd/catalogs/filters
```

El proxy no debe aceptar que el cliente defina los headers internos de
identidad o el secreto compartido.

## 8. Prueba UAT E/C/A

1. Crear un DRAFT con `Idempotency-Key` único.
2. Repetir exactamente el POST y verificar que no se duplique.
3. Repetir la clave con otro payload y esperar 409 `IDEMPOTENCY_CONFLICT`.
4. Editar con el `ETag` recibido.
5. Editar con un `ETag` anterior y esperar 409 `VERSION_CONFLICT`.
6. Activar como supervisor.
7. Republicar backlog y comprobar la cantidad E/C/A.
8. Cancelar o cerrar y verificar el historial append-only.

La activación no dispara automáticamente el backlog: participa en la próxima
publicación controlada del proceso DECAS.

## 9. Observabilidad y límites

- `X-Correlation-Id` se acepta y devuelve en todas las respuestas;
- mutaciones usan `Cache-Control: no-store`;
- consultas tienen timeout de 15 segundos y locks de 3 segundos;
- cursores están firmados y detectan cambio de snapshot;
- el proceso utiliza `application_name=pdd_api`;
- `/healthz` verifica contrato físico, no credenciales de usuario;
- logs se consultan con `journalctl -u pdd-api.service`.

## 10. Pendientes de integración

- publicación de la ruta en el gateway Connexa;
- mapeo definitivo del JWT a los cinco roles PDD;
- catálogo corporativo de nombres de sucursal, artículo y proveedor;
- pruebas UAT con usuarios DIARCO;
- posterior interfaz y conciliación Valkimia.

No es necesario desplegar Prefect para la API. Prefect continúa generando y
publicando las entidades; `pdd-api.service` las consulta y administra E/C/A.
