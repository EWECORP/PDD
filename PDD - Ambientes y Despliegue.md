# Ambientes y despliegue PDD

Versión: **1.0**  
Fecha: **2026-08-05**  
Estado: **Vigente**

## Ubicación por ambiente

| Ambiente | Host | Puerto | Base | Esquema operativo |
| --- | --- | ---: | --- | --- |
| Test | `186.158.182.223` | 5432 | `connexa_platform_test` | `stock_management` |
| Producción | Configuración segura `PGP_*` | 5432 | `connexa_platform_ms` | `stock_management` |
| Analítico | Configuración segura `PG_*` | 5432 | `diarco_data` | `datamart` |

Las credenciales no forman parte de este documento ni del repositorio. Deben
inyectarse mediante variables de entorno o el mecanismo de secretos del worker.

## Estado verificado de Test

Validación de solo lectura realizada el 2026-08-05:

- PostgreSQL `14.23`;
- conexión a `connexa_platform_test` exitosa;
- esquema `stock_management` existente;
- 48 tablas existentes;
- esquema `pdd` inexistente;
- historial Flyway disponible en
  `stock_management.flyway_schema_history`;
- última migración observada:
  `20260506000000 - add stock count status table`, exitosa;
- zona horaria del servidor PostgreSQL: `Etc/UTC`.

La fecha de negocio del PDD continúa interpretándose en
`America/Argentina/Buenos_Aires`; no debe derivarse implícitamente de la zona
UTC del servidor.

## Promoción de cambios

Secuencia prevista:

1. convertir los DDL aprobados en migraciones Flyway del esquema
   `stock_management`;
2. ejecutar `validate` en Test;
3. aplicar primero Core y luego DECAS en `connexa_platform_test`;
4. ejecutar smoke tests y reconciliaciones;
5. completar UAT;
6. promover exactamente los mismos artefactos a `connexa_platform_ms`;
7. no editar una migración ya aplicada; cualquier corrección se publica como
   una migración nueva.

## Guard de seguridad

Los DDL operativos vigentes admiten únicamente:

```text
connexa_platform_test
connexa_platform_ms
```

Una ejecución contra otra base termina con error antes de crear objetos.

## Configuración

Para herramientas que necesiten acceder a Test se reserva el prefijo:

```text
PGP_TEST_HOST
PGP_TEST_PORT
PGP_TEST_DB
PGP_TEST_USER
PGP_TEST_PASSWORD
```

El backend analítico actual continúa usando `PG_*` contra `diarco_data`. Las
variables `PGP_TEST_*` serán utilizadas al implementar la publicación hacia
Connexa y las pruebas de integración.

