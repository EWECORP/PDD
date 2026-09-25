# Ambientes y despliegue PDD

Versión: **2.0**

Fecha: **2026-09-24**

Estado: **Vigente**

## Arquitectura por ambiente

| Función | Host / servicio | Base o ruta | Esquemas / proceso |
| --- | --- | --- | --- |
| Fuentes, cálculo analítico y runtime | `186.158.182.54:5432` | `diarco_data` | `src`, `datamart`, `audit` |
| Aplicación PDD TEST | `186.158.182.127` | `/srv/PDD` | `prefect-worker-pdd-test.service` |
| Destino operativo TEST | `186.158.182.223:5432` | `connexa_platform_test` | `stock_management`, `inventory` |
| Destino operativo DESA | Configuración segura | `connexa_platform_diarco` | `stock_management`, `inventory` |
| Destino operativo PROD | Configuración segura | `connexa_platform_ms` | `stock_management`, `inventory` |
| Orquestación | `https://orquestador.connexa-cloud.com/api` | Prefect Server | pool `diarco-pdd` |

La aplicación no reside en el servidor de datos. El worker de TEST corre en
`186.158.182.127` y se conecta por separado a `diarco_data` y al destino
operativo. Las tablas propias de PDD en `stock_management` usan el prefijo
`pdd_`; `pdd` es un dominio funcional, no un esquema independiente.

## Estado validado de TEST

Validación funcional y técnica completada el **2026-09-24**:

- backend `diarco-pdd-backend 0.20.0` instalado en `/srv/PDD/backend`;
- virtualenv propio `/srv/PDD/.venv`;
- usuario y grupo de servicio `pdd:pdd`;
- configuración fuera del código en `/etc/connexa/pdd-test.env`;
- worker `pdd-test-127` activo en la cola homónima, pool `diarco-pdd`;
- schedule único `pdd-operational-daily-2115-art`, 21:15 ART;
- migraciones operativas aplicadas hasta v3.0;
- registro `audit.pdd_runtime_binding` v3.1 disponible en `diarco_data`;
- validaciones SQL, operativas y suite de pruebas completas;
- pipeline diario completado para fecha de negocio `2026-09-23`, usando stock
  al cierre de `2026-09-22`, con 13.773 líneas de backlog publicadas.

El scope validado en esa prueba fue
`c533e7e7-3363-4dc3-8127-24f48fe33522`. Los UUID funcionales no deben copiarse
a una imagen ni fijarse nuevamente en este documento: la selección vigente se
consulta en el registro runtime.

Con esa evidencia no quedó una modificación estructural pendiente en TEST para
la versión 0.20.0. Los pendientes enumerados al final son de automatización,
carga o integración; un cambio futuro de tablas deberá ingresar como una nueva
migración y actualizar este manifiesto.

## Promoción inicial a PROD 0.20.1

La versión 0.20.1 separa la configuración productiva del piloto TEST y corrige
la materialización inicial de modelo, configuración y scope aprobados. La
promoción autorizada el 2026-09-24 por `eduardo.ettlin` usa fecha efectiva
2026-09-23 y los siguientes identificadores:

| Entidad | UUID / revisión |
| --- | --- |
| Scope v6 | `c533e7e7-3363-4dc3-8127-24f48fe33522` |
| Modelo PDVB v3 | `a0a35b25-628d-43f1-b651-82c97207fc60` |
| Configuración DECAS PROD v1 | `3e5bd515-8642-4eb7-8058-844c67beb408` |
| Pipeline | `DAILY_PIPELINE_V3` |

El scope se aprueba en `diarco_data` ejecutando una sola vez
`PDD - Promocion Scope PROD 20260924.sql`. El script verifica UUID, versión,
CD, fecha, conteos, checksums, membresía y features hasta D-1 antes de cambiar
el estado y deja la aprobación en `detail.approval`.

La publicación operativa copia `approved_at` y `approved_by` a
`connexa_platform_ms`. El primer binding `PROD/DAILY_MASTER` se activa sólo
después de instalar el mismo artefacto validado, con los workers aún detenidos.
Los deployments productivos se crean exclusivamente con `prefect.prod.yaml`;
no se reutilizan ni sobrescriben los deployments de TEST.

## Contrato de fechas

PDD calcula siempre con datos cerrados. Para una fecha de negocio `D`, el
stock y las restantes posiciones operativas corresponden al cierre de `D-1`.
El proceso diario resuelve el último cierre común disponible y no debe derivar
la fecha desde el reloj UTC del servidor.

La zona funcional y de schedules es
`America/Argentina/Buenos_Aires`. Si no hay un nuevo cierre común, la corrida
normal termina idempotentemente como `SKIPPED/NO_NEW_CLOSED_DATE`.

## Configuración y secretos

En TEST, systemd define como mínimo:

```text
User=pdd
Group=pdd
WorkingDirectory=/srv/PDD/backend
Environment="HOME=/var/lib/pdd"
Environment="PYTHONPATH=/srv/PDD/backend"
Environment="PREFECT_API_URL=https://orquestador.connexa-cloud.com/api"
Environment="PDD_ENV_PATH=/etc/connexa/pdd-test.env"
Environment="PDD_OPERATIONAL_TARGET_ENV=TEST"
```

El archivo `/etc/connexa/pdd-test.env` pertenece a `root:pdd`, modo `0640`, y
contiene conexiones y secretos. No se copia dentro de `/srv/PDD/backend`, no
se incluye en el ZIP y no se versiona.

El archivo identifica el ambiente y proceso estable:

```text
PDD_RUNTIME_ENVIRONMENT=TEST
PDD_RUNTIME_PROCESS_CODE=DAILY_MASTER
```

Scope, modelo, configuración y revisión de pipeline se resuelven desde la fila
`ACTIVE` de `diarco_data.audit.pdd_runtime_binding`. Las variables
`PDD_SCOPE_VERSION_UUID` y `PDD_MODEL_VERSION_UUID` son solamente fallback
transitorio durante la adopción del registro.

## Esquema y migraciones

La secuencia canónica está en `PDD - 00 Manifiesto DDL v3.1.sql`.

- `diarco_data` recibe el DDL analítico, sus migraciones y el registro runtime;
- cada base Connexa recibe Core/DECAS y las migraciones operativas hasta v3.0;
- los DDL v2.2 representan el punto de partida, no la fotografía final;
- v2.8 reemplaza `normalized_status` por el catálogo/FK de estados vigente;
- nunca se modifica una migración que ya fue aplicada.

Antes de aplicar una migración se consulta el historial Flyway y la estructura
existente. Después se ejecuta el validador específico de esa versión y
`backend/tools/validate_operational.py`. La promoción a PROD usa exactamente
los mismos artefactos aprobados en TEST.

## Despliegue normal de una versión

1. Desarrollo genera un ZIP versionado, sin `.env`, junto con SHA-256 y notas
   de versión.
2. Infra o el mecanismo de despliegue copia el artefacto al servidor TEST y lo
   expande en un directorio `backend.next-<revision>`.
3. Se aplican las migraciones pendientes en orden y con `ON_ERROR_STOP`.
4. Sin detener el worker se ejecutan pytest, `validate_sql.py`,
   `validate_operational.py` y los smoke tests sobre el directorio nuevo.
5. Se detiene el worker, se conserva el backend anterior como
   `backend.prev-<version>-<fecha>`, se hace el intercambio de directorios y se
   instala el paquete editable en `/srv/PDD/.venv`.
6. Se inicia el worker y se verifican systemd, logs, work pool, queue,
   deployment y schedule.
7. Se ejecuta una corrida controlada. La promoción se acepta sólo con estado
   `Completed` y reconciliaciones de datos correctas.
8. El rollback restaura el backend anterior, reinstala esa versión y reinicia
   el worker. Las migraciones de datos no se revierten destruyendo estructura;
   requieren una migración compensatoria aprobada.

Los scripts de despliegue delegados (`deploy-pdd-test`, `rollback-pdd-test`,
`status-pdd-test`, `logs-pdd-test`) deben ser provistos y administrados por
Infra antes de retirar el sudo amplio. Los grupos sudo existentes por sí solos
no crean esos comandos.

## Operación normal

Comandos de comprobación en TEST:

```bash
sudo systemctl status prefect-worker-pdd-test.service --no-pager -l
sudo journalctl -u prefect-worker-pdd-test.service --since "30 minutes ago" --no-pager

cd /srv/PDD/backend
sudo -u pdd env \
  HOME=/var/lib/pdd \
  PDD_ENV_PATH=/etc/connexa/pdd-test.env \
  PREFECT_API_URL=https://orquestador.connexa-cloud.com/api \
  /srv/PDD/.venv/bin/prefect work-pool inspect diarco-pdd

sudo -u pdd env \
  HOME=/var/lib/pdd \
  PDD_ENV_PATH=/etc/connexa/pdd-test.env \
  PREFECT_API_URL=https://orquestador.connexa-cloud.com/api \
  /srv/PDD/.venv/bin/prefect work-queue inspect pdd-test-127 --pool diarco-pdd

sudo -u pdd env \
  HOME=/var/lib/pdd \
  PDD_ENV_PATH=/etc/connexa/pdd-test.env \
  /srv/PDD/.venv/bin/pdd-etl runtime-config show --environment TEST
```

No se debe ejecutar `source /etc/connexa/pdd-test.env`: el archivo es leído por
la aplicación y puede tener formato no compatible con el shell. Tampoco se
deben copiar el prompt, enlaces Markdown ni el texto de salida como si fueran
comandos.

## Pendientes conocidos

- automatizar los scripts restringidos de despliegue y rollback con Infra;
- promover a DESA/PROD sólo después de UAT y de contar con los mismos grants y
  migraciones;
- corregir el cargador de Inventory para no desactivar reposiciones válidas al
  copiar el estado de `product_site`;
- implementar la reconciliación real de importaciones Valkimia activas. Hasta
  entonces el backlog se bloquea deliberadamente ante importaciones
  `PENDING`, `ACCEPTED` o `PARTIAL`;
- activar el monitoreo/backtesting semanal sólo después de medir su costo en
  TEST. El monitoreo propone evidencia; nunca cambia automáticamente el modelo
  activo.
