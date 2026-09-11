# Publicación, concurrencia y auditoría — v1.0

Este diseño y `openapi-stock-policy.yaml` son contratos propuestos para implementación; no representan endpoints desplegados. La migración 03 agrega soporte persistente, no implementa por sí sola los controles del servicio. UUID de dominio/versiones y scope se resuelven dentro del ámbito autorizado por CONNEXA.

## Dominio y alcance

`DEFAULT` representa un único calendario de políticas para la instalación actual. No permite separar tenants. Antes de utilizar varias empresas con calendarios independientes, crear dominios autorizados y definir el mapeo de locales/grupos a dominio. El cliente no puede elegir un dominio para eludir autorización. Todas las versiones copiadas y referencias de publicación deben pertenecer al dominio de la URL.

Una versión es un conjunto completo. El scope es una referencia inmutable a los pares artículo/local cubiertos por el despliegue, no sólo los resultados de los filtros de pantalla. Sólo se publica con validación de ese scope. No se autoriza fallback al legado.

## Edición y ETag

El backend devuelve ETag fuerte `"<revision>"`. Todo cambio de cabecera/regla requiere If-Match. Bajo transacción: bloquear la fila de versión FOR UPDATE, verificar permiso, DRAFT y revisión; validar comando; aplicar; incrementar revision una sola vez; actualizar updated_at/by; insertar auditoría; confirmar. Las mutaciones de distintas reglas compiten por la misma revisión de versión intencionalmente. Lecturas de detalle/reglas devuelven la revisión del conjunto leído.

Falta If-Match → 428; revisión distinta → 412; publicada → 409. No actualizar silenciosamente. Una validación queda obsoleta cuando su revision deja de coincidir. Copiar versión genera nuevas IDs de reglas y base_version_id; source_checksum de una copia/manual se genera como identificador único del nuevo origen (por ejemplo `MANUAL:<uuid>`), no se reutiliza checksum de importación.

## Validación asíncrona

POST validations verifica revisión bajo bloqueo, crea RUNNING con scope, fecha y fingerprint de entradas; devuelve 202. Worker obtiene una fotografía consistente de reglas y de atributos de artículos/grupos/scope. Fingerprint identifica esas revisiones/snapshots, no sólo el texto de la consulta. Si cambia la versión durante el trabajo, marcar FAILED con STALE_VALIDATION. Incidencias se guardan y paginan.

PASSED exige todos los pares del scope cubiertos, cero errores bloqueantes, jerarquía válida, clasificación disponible, asignación no ambigua, días finitos, referencias autorizadas y ausencia de importaciones PENDING. Un scope vacío se rechaza por el servicio. EXCLUDED_CLOSED es informativo salvo que el scope incluya esos locales. Fallo de infraestructura → ERROR, nunca PASSED ni SIN_COBERTURA. La publicación comprueba vigencia del fingerprint contra las revisiones actuales; si no puede garantizar consistencia exige nueva validación.

## Publicación atómica

POST publish recibe validationId, expectedPreviousVersionId (UUID o null explícito), changeReason. If-Match e Idempotency-Key obligatorios. Las fechas se toman del borrador validado; modificarlas requiere editar y revalidar.

Orden de bloqueos para todos los publicadores: fila `spl_stock_policy_domain FOR UPDATE` → versiones afectadas ordenadas por UUID. El dominio debe existir; no bloquear una consulta vacía. Bajo el mismo bloqueo:

1. Comprobar identidad/permisos y buscar respuesta idempotente. Si existe y hash coincide, devolverla antes de evaluar el ETag actual; si hash difiere devolver 409 IDEMPOTENCY_CONFLICT.
2. Bloquear borrador; comprobar revisión, estado y dominio; no permitir publicación retroactiva (valid_from >= fecha de negocio actual de la instalación).
3. Comprobar validación PASSED de misma versión/revisión/scope y fingerprint vigente. Revalidar los invariantes que puedan cambiar concurrentemente o fijar snapshots para que la comprobación no sufra una carrera con cambios de maestros.
4. Determinar intervalo [valid_from,valid_to), fin NULL=infinito. Si hay una predecesora publicada que cruza el inicio, exigir expectedPreviousVersionId exacto. Si no hay, exigir null. Cerrar la predecesora en valid_from de la nueva; no cambiar sus reglas. Si comienza en la misma fecha, rechazar y resolver programación antes. Cualquier otra versión publicada que se superponga provoca 409 SCHEDULE_CONFLICT; no reprogramar múltiples versiones automáticamente.
5. Insertar evento SCHEDULE_CLOSED con fechas anteriores/nuevas para la predecesora, incrementar su revisión. La predecesora conserva PUBLISHED: su situación temporal se deriva de fechas; RETIRED no se usa en este flujo.
6. Publicar borrador, completar published_at/by, incrementar revisión, guardar auditoría PUBLISHED y respuesta idempotente en la misma transacción. Confirmar todo o nada.

La inmutabilidad aplica al contenido de reglas publicado. La única modificación de cabecera publicada permitida es el cierre controlado de vigencia por el servicio de transición, auditado. No ofrecer PATCH genérico sobre publicadas. No existe endpoint de retiro en v1.

Este algoritmo serializa publicaciones incluso para intervalos sin predecesora. No hay constraint de exclusión temporal en la migración: el contrato exige que sólo el servicio autorizado escriba estados/fechas; acceso SQL manual puede violar esa garantía. El equipo debe restringir credenciales, probar dos publicadores concurrentes e integrar el bloqueo con sus repositorios transaccionales. No se promete inmutabilidad mediante triggers inexistentes.

## Idempotencia

Todos los POST de creación/validación/publicación requieren clave UUID generada por el cliente; PUT/DELETE también usan clave para recuperar respuesta tras timeout. Hash canónico incluye método, ruta, body y revisión solicitada. Clave se identifica por dominio, actor autenticado y operación (método+ruta canónica).

Adquirir bloqueo transaccional por clave (o usar el bloqueo de versión/dominio, cuando cubra todos los participantes) antes de buscar/ejecutar. Para creación de versión, usar bloqueo de dominio. No usar «consultar si existe y después insertar» sin exclusión mutua. Guardar sólo respuestas exitosas junto a la mutación; el rollback deja la clave disponible. Validación asíncrona guarda su respuesta 202 y ID de trabajo; el worker no vuelve a crear el trabajo. No purgar claves hasta acordar retención y política de reintentos.

## Auditoría y seguridad

Mapeo de permisos: Consultar para GET y resolve; Editar para crear/copiar versión y modificar cabecera/reglas; Publicar para iniciar validación y publicar. El publicador tiene además permiso de consulta. El autor de un borrador no obtiene publicación implícita. Adaptar bearerAuth al middleware existente; la API no introduce login nuevo. El servicio verifica que ruleId/validationId pertenezcan a versionId y que éste pertenezca al dominio autorizado, devolviendo 404 para referencias fuera de ese alcance.

Registrar CREATED, COPIED, HEADER_UPDATED, RULE_CREATED, RULE_UPDATED, RULE_DELETED, VALIDATION_STARTED/COMPLETED, SCHEDULE_CLOSED, PUBLISHED. Actor sale de sesión, no del payload; request_id se propaga. JSON antes/después contiene sólo datos funcionales, nunca tokens. Auditoría es append-only por servicio y permisos; la migración no instala triggers de captura ni grants porque el rol runtime aún debe definirse por el equipo.

Las reglas referenciadas por importación no se eliminan; devolver 409 IMPORT_EVIDENCE_REFERENCE. La auditoría de otras reglas eliminadas conserva rule_id sin FK. Las clasificaciones/locales/categorías son sólo lectura en esta API; validar pertenencia al dominio antes de guardar.

## Resolución

Seleccionar versión o borrador explícito, fecha, artículo/local. Resolver clasificación y familia/rubro desde el adaptador de maestros; no aceptar esos atributos del navegador como fuente de verdad. Local > grupo; dentro del ámbito rubro > familia > general. Clasificación obligatoria. Devolver ambos días, regla y explicación; ninguna coincidencia → outcome NO_COVERAGE (200), error técnico → 503. Grupo ambiguo → outcome AMBIGUOUS. Una versión explícita fuera de vigencia devuelve OUTSIDE_VALIDITY, salvo modo draftPreview para borradores. priority permanece 0.

## Pruebas que debe ejecutar el backend

- Dos editores con mismo ETag: sólo uno confirma; otro 412.
- Dos publicaciones en un dominio: se serializan y la segunda detecta predecesora/revisión desactualizada; nunca intervalos superpuestos.
- Timeout tras COMMIT y reintento: misma respuesta/ETag, sin nueva auditoría ni versión.
- Clave reutilizada con otro payload: 409; fallo antes de COMMIT: sin resultado parcial.
- Worker con revisión/maestros cambiados: validación no publicable.
- Cierre de predecesora y publicación fallida: rollback de ambas.
- Edición de publicada y eliminación de evidencia: rechazadas.
- Copia conserva el origen auditable sin modificar importación histórica.

Los SQL se validan por separado; estas pruebas de servicio requieren implementación backend y no se declaran ejecutadas en este paquete.
