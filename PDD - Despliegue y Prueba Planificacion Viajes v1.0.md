# PDD — Despliegue y prueba de planificación de viajes

Versión: **1.0**  
Fecha: **2026-08-21**  
Estado: **Guía para adopción controlada DESA → TEST**

## 1. Alcance de este despliegue

La migración v2.7 crea el contrato persistente para que el equipo Java y
frontend desarrollen planes y viajes. No habilita todavía publicación real a
Valkimia ni modifica el orquestador Prefect.

No ejecutar en Producción hasta completar UAT, mapping legacy y conciliación.

## 2. Archivos

- `PDD - Migracion Operativa Planificacion Viajes v2.7.sql`;
- `PDD - Validacion Operativa Planificacion Viajes v2.7.sql`;
- `PDD - Grants API PDD stock_management v1.2.sql`;
- `backend/contracts/pdd-planning-openapi-v1.yaml`.

La migración se convertirá luego en una migración Flyway con número libre en
`connexa-platform-lib-model-stockmanagement`. Durante la adopción inicial puede
aplicarse manualmente de forma controlada.

## 3. Respaldo lógico de control

Antes de migrar registrar, al menos:

```sql
SELECT count(*) AS backlog_lines,
       sum(total_open_quantity) AS backlog_quantity
FROM stock_management.pdd_current_backlog_line;

SELECT count(*) AS imports,
       coalesce(sum(total_imported_quantity), 0) AS imported_quantity
FROM stock_management.pdd_valkimia_import;
```

La migración es aditiva, pero estos totales permiten demostrar que no alteró
los datos existentes.

## 4. Aplicación en DESA

Desde Linux, con credenciales suministradas por secreto/entorno:

```bash
psql "$PDD_TARGET_DATABASE_URL" \
  -v ON_ERROR_STOP=1 \
  -f "/srv/PDD/PDD - Migracion Operativa Planificacion Viajes v2.7.sql"
```

No colocar contraseña en la línea de comandos ni en este documento.

## 5. Smoke test

```bash
psql "$PDD_TARGET_DATABASE_URL" \
  -v ON_ERROR_STOP=1 \
  -f "/srv/PDD/PDD - Validacion Operativa Planificacion Viajes v2.7.sql"
```

El script inserta una cadena mínima dentro de una transacción y ejecuta
`ROLLBACK`. Debe mostrar cinco columnas `true` y un `NOTICE OK v2.7`.

## 6. Grants

Aplicar solamente si el ambiente utiliza el rol `connexa_pdd_api`:

```bash
psql "$PDD_TARGET_DATABASE_URL" \
  -v ON_ERROR_STOP=1 \
  -f "/srv/PDD/PDD - Grants API PDD stock_management v1.2.sql"
```

Si el microservicio usa `connexa_platform_user`, el DBA debe adaptar el rol y
ratificar mínimo privilegio; no reemplazar nombres a ciegas.

## 7. Controles posteriores

```sql
SELECT table_name
FROM information_schema.tables
WHERE table_schema = 'stock_management'
  AND table_name IN (
      'pdd_dispatch_plan',
      'pdd_dispatch_trip',
      'pdd_dispatch_trip_stop',
      'pdd_dispatch_trip_line',
      'pdd_dispatch_line_allocation',
      'pdd_valkimia_status_mapping',
      'pdd_integration_checkpoint'
  )
ORDER BY table_name;
```

Repetir los dos totales previos. Deben coincidir exactamente.

## 8. Prueba del contrato local

```bash
cd /srv/PDD/backend
source /srv/FORECAST/venv/bin/activate
PYTHONDONTWRITEBYTECODE=1 python -m pytest -q
```

La suite valida ambos OpenAPI, referencias internas, ejemplos JSON y nombres
`pdd_*` de la migración.

## 9. Orden de desarrollo Java

1. incorporar Flyway y entidades en
   `connexa-platform-lib-model-stockmanagement`;
2. implementar consulta planificable;
3. crear plan/viaje DRAFT;
4. implementar bloqueo, validación y aprobación;
5. implementar outbox/publicación sin conectar todavía Valkimia;
6. integrar frontend contra DESA;
7. obtener y certificar DDL legacy;
8. implementar adaptador/poller;
9. habilitar conciliación;
10. recién entonces retirar el guard de importaciones activas del publicador
    diario.

## 10. Gate para pasar a TEST

- migración y smoke test correctos en DESA;
- pruebas Java de concurrencia con dos planificadores;
- aprobación idempotente;
- totales plan/viaje/líneas conciliados;
- frontend no accede PostgreSQL;
- volumen nulo visible;
- publicación simulada no duplica outbox;
- cancelación libera reserva;
- mapping físico Valkimia aprobado o adaptador todavía deshabilitado por
  feature flag.
