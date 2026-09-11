# Mantenimiento de políticas de stock — Especificación funcional v1.0

Fecha: 2026-09-11. Destinatarios: producto, frontend, backend y QA de CONNEXA.
Estado: especificación para implementación; pantallas y servicios todavía no implementados.
Base: `CONTRATO_ENTIDADES.md` y migraciones del paquete. Ante diferencias, esta especificación no modifica silenciosamente el DDL: las brechas identificadas al final requieren trabajo backend.

## 1. Objetivo y alcance

Permitir mantener días objetivo de stock y días adicionales de sobrestock por local o grupo, clasificación de compra y categoría opcional. El usuario debe poder explicar qué regla aplica a un artículo/local, preparar cambios en borrador y publicarlos con vigencia.

Ubicación sugerida en el menú: **Abastecimiento → Políticas de stock**. Título visible: **Políticas de stock**. No mostrar nombres de tablas, UUID, checksum ni errores SQL en formularios.

La primera entrega incluye versiones, edición de reglas, consulta de aplicación, validación y publicación. Incluye consulta de la importación inicial y del historial. No incluye edición de maestros de locales/categorías, creación de clasificaciones, importación libre de archivos, rediseño de zonas/formatos, ABC o rotación. Los grupos existentes sólo podrán utilizarse cuando el negocio valide su composición; hasta entonces permitir consultar y trabajar con reglas de local.

Publicar una política no significa que PDD la esté utilizando: el cálculo requiere una integración posterior. La UI debe presentar ambos estados por separado con información provista por backend.

## 2. Conceptos y reglas de negocio

| Concepto | Comportamiento |
|---|---|
| Versión | Conjunto completo de reglas. La nueva versión reemplaza el conjunto anterior, no hereda reglas ocultas. «Crear nueva versión» copia explícitamente las reglas elegidas como base. |
| Ámbito | Exactamente Local o Grupo de locales. No hay regla global sin ámbito. |
| Clasificación de compra | Obligatoria y única por regla; opciones desde catálogo. No existe «Todas» en esta entrega. |
| Categoría | Puede ser Todas las categorías, Familia o Rubro. |
| Días objetivo | Campo `target_stock_days`. |
| Días adicionales de sobrestock | Campo `overstock_days`; no equivale a stock de seguridad. |
| Precedencia | Local antes que Grupo; dentro del ámbito Rubro antes que Familia antes que Todas. |
| Ausencia de regla | Resultado «Sin cobertura»; no completar con cero ni tomar legado automáticamente. |

Una regla local general gana a una regla específica del grupo. Mostrar esta consecuencia en la explicación de aplicación. La clasificación debe coincidir siempre. Ambos días provienen de una única regla ganadora. `priority` no se muestra ni edita; permanece en 0.

Datos iniciales de TEST: 605 reglas para 55 locales, versión DRAFT. Se conservaron 22 filas excluidas de locales cerrados 83/84. Los conflictos de las reglas anteriores corresponden a datos dummy y no son incidencias que el operador deba resolver.

## 3. Permisos y estados

Permisos funcionales propuestos, a mapear al sistema de autorización existente:

| Permiso | Acciones |
|---|---|
| Consultar | Listar, ver reglas, consultar aplicación, validaciones e historial |
| Editar | Crear versión, crear/editar reglas y quitar reglas de borrador |
| Publicar | Validar y publicar borrador |

No exigir que editor y publicador sean personas distintas salvo política interna. Backend valida permisos en todas las operaciones y aplica el alcance empresa/local autorizado. Ocultar acciones no autorizadas; impedir acceso directo por URL/API.

| Estado persistido | Etiqueta | Edición |
|---|---|---|
| DRAFT | Borrador | Sí, con permiso |
| PUBLISHED | Publicada | Sólo lectura; botón «Crear nueva versión» |
| RETIRED | Retirada | Sólo lectura |

«Programada», «Vigente» y «Finalizada» son etiquetas temporales derivadas de fechas, no nuevos estados persistidos. Fecha desde inclusiva y fecha hasta exclusiva. La UI utiliza «Vigente desde» y «Deja de aplicar el» con ayuda «Esta fecha ya no está incluida». Mostrar fechas en formato local; enviar ISO date. No ofrecer retirada manual en v1; su política operativa requiere definir continuidad de cobertura.

## 4. Pantalla A — Listado de versiones

Encabezado con título, botón «Crear versión» y aviso de integración, si corresponde: «Las políticas publicadas aún no se aplican al cálculo de reposición». Evitar afirmar que una versión está en uso sólo por estar publicada.

Filtros: estado, fecha de vigencia, autor y búsqueda por referencia de versión. Backend proporciona una referencia legible; no inventar un número secuencial persistido inexistente. Usar fecha de creación y un identificador corto como referencia visual, conservando UUID en navegación.

Grilla paginada del lado servidor, 25 filas por defecto:

| Columna | Contenido |
|---|---|
| Versión | Referencia y fecha de creación |
| Estado | Borrador/Publicada/Retirada y situación temporal |
| Vigencia | Desde / deja de aplicar el |
| Reglas | Total del conjunto |
| Motivo | Resumen del cambio |
| Creada por | Nombre visible del autor |
| Acciones | Abrir; crear nueva versión desde ésta |

Estado vacío: «Todavía no hay políticas de stock» y acción de creación si tiene permiso. Error de carga con reintento, conservando filtros. No presentar un error de red como lista vacía.

Crear versión abre diálogo: base (versión existente o vacía), motivo obligatorio, vigencia propuesta opcional mientras sea borrador. Una copia crea IDs nuevos para sus reglas y conserva relación de procedencia en auditoría; no copia ni reasigna las filas de importación histórica. Luego navega al detalle del nuevo borrador.

## 5. Pantalla B — Detalle de versión

Encabezado: referencia, estado, vigencia, motivo, autor, total de reglas. Acciones: «Guardar datos de versión», «Validar» y «Publicar», según permisos/estado. En publicada, sustituir edición por «Crear nueva versión».

Pestañas: **Reglas**, **Comprobar aplicación**, **Validación**, **Importación**, **Historial**. Pestaña Importación sólo cuando hay evidencia asociada; de lo contrario mensaje «Esta versión no tiene una importación asociada».

### Reglas

Filtros combinables: Local/Grupo, selector de ámbito, clasificación, nivel de categoría (Todas/Familia/Rubro), familia y rubro. Buscar ámbitos por código y nombre. Filtros no modifican la versión. Orden estable y paginación servidor; conservar filtros al volver del editor.

Columnas: ámbito, código/nombre del local o grupo, clasificación, familia, rubro, días objetivo, días adicionales de sobrestock y acciones. Representar general como «Todas las categorías»; familia sin rubro como «Todos los rubros». Nunca mostrar NULL o 0 como comodín de categoría.

Acciones en borrador: «Agregar regla», «Editar», «Duplicar», «Quitar de esta versión». Duplicar abre el editor sin guardar: debe cambiarse al menos una dimensión de la clave antes de confirmar. No ofrecer edición masiva ni selección para eliminación masiva en v1.

Quitar requiere confirmación contextual con ámbito y clasificación, indicando que no afecta versiones anteriores. Si la regla está referenciada por evidencia de importación, el backend debe rechazar la eliminación física y explicar «La regla tiene evidencia de importación. Cree una nueva versión para omitirla». El frontend no intenta borrar ni alterar la evidencia para sortear la FK. En una copia sin esa referencia puede omitirse conservando auditoría.

## 6. Pantalla C — Editor de regla

Panel lateral o página dedicada; mantener la misma organización en ambos casos. Orden de campos:

| Campo visible | Control | Obligación y dependencia | Payload |
|---|---|---|---|
| Aplicar a | Radio Local / Grupo de locales | Obligatorio | Determina cuál FK se envía |
| Local | Autocompletar código y nombre | Sólo con ámbito Local; seleccionable según maestro autorizado | `site_id` |
| Grupo de locales | Autocompletar y enlace «Ver locales» | Sólo con ámbito Grupo; composición validada previamente | `supply_cluster_id` |
| Clasificación de compra | Selector de catálogo | Obligatorio; sin opción Todas | `purchase_classification_code` |
| Alcance de categoría | Radio Todas las categorías / Familia / Rubro | Por defecto Todas al crear una regla manual | Deriva nulabilidad |
| Familia | Autocompletar | Obligatoria para Familia/Rubro | `family_category_id` |
| Rubro | Autocompletar filtrado por familia | Obligatorio sólo para Rubro | `category_id` |
| Días objetivo de stock | Entrada decimal | Obligatorio, sin valor predeterminado | `target_stock_days` |
| Días adicionales de sobrestock | Entrada decimal | Obligatorio, sin valor predeterminado; cero válido | `overstock_days` |

Permitir 0 a 999999,9999, hasta cuatro decimales, conforme a numeric(10,4). No redondear silenciosamente; rechazar exceso de precisión, negativos, infinito y NaN. Admitir coma decimal en UI y normalizar sin separadores de miles; acordar representación decimal del API para evitar pérdida de precisión. No exigir que sobrestock sea mayor/menor que stock objetivo.

Al cambiar Local por Grupo, limpiar la FK anterior; nunca enviar ambas. Al cambiar familia, limpiar rubro. Al elegir Todas, limpiar familia y rubro. Al elegir Familia, limpiar rubro. Advertir sólo si se perderá una selección ingresada, sin múltiples confirmaciones por campo.

Resumen previo a guardar: «Aplicará al local 25, productos SENSIBLES, todas las categorías: 18 días objetivo y 6 días adicionales de sobrestock». No mostrar UUID.

Ayuda de días: «El cálculo combina estos días con la demanda diaria y las existencias. Los días adicionales definen la necesidad opcional de sobrestock». No afirmar que S siempre equivale a PDVB × días adicionales.

Botones Guardar / Cancelar. Bloquear doble envío y mostrar progreso. Validación inline junto al campo y resumen navegable al primer error. Al cerrar con cambios no guardados, permitir seguir editando o descartarlos.

### Errores obligatorios

| Caso | Mensaje / acción |
|---|---|
| Clave repetida | «Ya existe una regla para este ámbito, clasificación y categoría»; enlace a regla existente |
| Rubro fuera de familia | «El rubro no pertenece a la familia seleccionada» |
| Falta de días | «Ingrese los días; puede indicar 0» |
| Versión dejó de ser borrador | «La versión fue publicada mientras estaba editando»; recargar en lectura |
| Edición concurrente | «Otra persona modificó esta versión. Actualice antes de guardar»; conservar entrada para comparación |
| Maestro eliminado/no disponible | «La selección ya no está disponible»; mantener visible la referencia anterior para diagnóstico |
| Sin permisos | Informar falta de autorización; no reintentar automáticamente |
| Error de red | Mantener formulario y permitir reintento sin duplicar regla |

## 7. Pantalla D — Comprobar aplicación

Formulario: versión actual (fija al entrar desde detalle), fecha de negocio, local y artículo. Selectores muestran códigos/descripciones. Botón «Consultar». Permitir consultar borradores indicando «Simulación de borrador».

Resultado exitoso:

- Artículo, local, clasificación y familia/rubro resueltos por backend para la consulta.
- Grupo efectivo, si lo hay, y fecha de los datos usados cuando esté disponible.
- Días objetivo y adicionales en dos valores destacados.
- Regla ganadora con enlace al editor/lectura y etiqueta Local/Grupo + Rubro/Familia/General.
- Lista opcional «Otras reglas coincidentes» con motivo de menor precedencia.

Resultados alternativos distintos: Sin cobertura; clasificación no disponible; asignación de grupo ambigua; versión fuera de vigencia; artículo/local no disponible; fallo de consulta. No usar «Sin cobertura» para errores técnicos. No calcular resolución en JavaScript ni consultar tablas externas desde el navegador.

Ejemplo de explicación: «Se aplicó la regla general del local. Las reglas del local prevalecen sobre las de su grupo». Esta consulta de días no es todavía una simulación de cantidades D/S; no mostrar cantidades sin datos de PDVB/stock/logística y un servicio de simulación real.

## 8. Pantalla E — Validar y publicar

La validación se ejecuta en backend contra un scope explícito, fecha y revisión del borrador. Mostrar «Cobertura verificada para …», fecha de ejecución, cantidad de pares analizados, cubiertos, sin regla y ambiguos. Una medición de toda la tabla de stock no sustituye la validación del scope PDD.

Grilla de incidencias paginada: severidad, tipo, local/artículo o regla, descripción y acción. Enlace a edición cuando corresponda. Permitir filtros por severidad y tipo.

Bloquean publicación: claves inválidas/duplicadas, referencias incoherentes, días inválidos, vigencia inválida, versión superpuesta no resuelta, asignación ambigua, importaciones PENDING y pares del scope sin cobertura. EXCLUDED_CLOSED es informativo si los locales están fuera del scope; si el scope los incluye, debe corregirse el scope o su situación.

La publicación requiere validación exitosa sobre la revisión actual. Cualquier cambio posterior invalida el resultado. El backend revalida o verifica un token de revisión bajo bloqueo en la misma operación de publicación; botón habilitado en UI no reemplaza esa garantía.

Diálogo Publicar: referencia, vigencia, alcance validado, total de reglas y motivo; indicar «Después de publicar no se podrán editar las reglas de esta versión». Si ya hay versión vigente sin fin, el backend debe preparar una transición temporal sin solapamiento y presentar la fecha de cierre anterior. No ofrecer un flujo que sólo cambie status y deje dos versiones vigentes. La estrategia de transición/auditoría se implementará en el servicio.

Tras éxito: detalle sólo lectura y mensaje de publicación. Mostrar por separado «Aplicación en PDD: pendiente de integración / programada / en uso» únicamente según evidencia del backend; las últimas dos etiquetas requieren integración real. Si la petición termina en timeout, consultar estado antes de ofrecer repetir; publicación debe ser idempotente.

## 9. Importación e historial

Importación: tarjetas Total / Mapeadas / Pendientes / Excluidas; grilla con códigos de origen, clasificación, familia/rubro, ambos días, estado y motivo. El rubro 0 se puede mostrar como «Todos los rubros (origen: 0)». Es evidencia de sólo lectura. En TEST: 627/605/0/22; nunca hardcodear esos conteos.

Historial: fecha/hora, usuario, acción, campos antes/después y motivo. Debe distinguir creación manual, copia, edición de reglas, validación y publicación. El origen de importación no se reescribe al editar una regla. Si backend aún no tiene auditoría, marcar esta funcionalidad pendiente y no presentar `created_at` como historial completo.

## 10. Servicios requeridos: contrato funcional a formalizar

Operaciones sugeridas, no endpoints existentes ni OpenAPI definitivo:

| Operación | Entrada clave | Respuesta clave |
|---|---|---|
| Listar versiones | filtros/página/orden | items, total, permisos/acciones |
| Crear/copiar versión | base opcional, motivo, fechas | versión, revisión nueva |
| Modificar cabecera | ID, revisión esperada, motivo/fechas | revisión actualizada |
| Listar reglas | versión, filtros/página/orden | reglas con etiquetas maestras y total |
| Crear/editar/quitar regla | versión, revisión esperada, campos | resultado, revisión actualizada; conflicto de clave tipado |
| Consultar catálogos | búsqueda, familia para rubros, alcance autorizado | IDs, códigos, nombres, estado de disponibilidad |
| Consultar locales del grupo | grupo | composición y advertencias |
| Resolver aplicación | versión, fecha, local, artículo | días, regla ganadora, atributos usados, diagnóstico |
| Validar | versión/revisión, scope/fecha | ID de validación, estado, resumen, incidencias paginadas |
| Publicar | versión/revisión, validación, clave idempotencia | versión publicada o conflictos tipados |
| Consultar importación/historial | versión, filtros/página | evidencia paginada |

El ID y revisión son campos técnicos de transporte, no del formulario. Acordar token de concurrencia con backend; no usar checksum del lote como revisión de edición. Si la validación es larga, devolver un identificador de trabajo y consultar progreso, sin mantener la pantalla bloqueada. Errores deben tener código estable, mensaje funcional y campos afectados; no mostrar mensajes SQL.

## 11. Criterios de aceptación QA

| ID | Escenario | Resultado esperado |
|---|---|---|
| UI-01 | Alta local + clasificación + Todas | Persiste ambas categorías NULL y ambos días |
| UI-02 | Familia seleccionada sin rubro | Aplica a todos sus rubros |
| UI-03 | Cambiar familia tras elegir rubro | Rubro anterior se limpia y se exige una nueva selección |
| UI-04 | Cambiar Local a Grupo | Sólo la FK del grupo llega a API |
| UI-05 | Días 0 / negativos / 5 decimales | 0 aceptado; los otros rechazados sin redondeo |
| UI-06 | Duplicar regla general sin cambiar clave | Error de duplicado y enlace a existente |
| UI-07 | Local general y grupo por rubro coinciden | Gana local general con explicación |
| UI-08 | Tres niveles coinciden dentro del local | Gana rubro; al quitarlo gana familia; después general |
| UI-09 | No coincide clasificación | No aplica la regla; no existe fallback oculto |
| UI-10 | Usuario sólo consulta | No puede editar/publicar ni por URL/API |
| UI-11 | Publicación o edición concurrente | Conflicto visible; no se sobreescriben cambios |
| UI-12 | Editar después de validar | Validación anterior deja de habilitar publicación |
| UI-13 | Publicar dos veces por timeout | Una publicación, resultado recuperable por idempotencia |
| UI-14 | Versión publicada | Sólo lectura; nueva versión copia sin modificar historia |
| UI-15 | Evidencia de locales 83/84 | Excluida por cierre; no se convierte en regla activa |
| UI-16 | Regla referenciada por importación | Quitar informa restricción; no elimina evidencia |
| UI-17 | Fecha igual al fin de vigencia | La versión no se considera vigente |
| UI-18 | Cobertura faltante o grupo ambiguo | Publicación bloqueada, incidencias navegables |
| UI-19 | Red falla al guardar | Se conserva entrada y reintento no duplica |
| UI-20 | Publicación con PDD aún sin integrar | UI no afirma que el cálculo ya la utiliza |

Accesibilidad: controles etiquetados, navegación con teclado, foco al abrir/cerrar panel, errores anunciados, estados identificados con texto además de color. Mostrar loading, vacío y error como estados diferentes. En grillas extensas mantener paginación servidor y búsqueda; no descargar todo el catálogo para un selector.

## 12. Dependencias y brechas frente al paquete Flyway

Antes de habilitar edición general debe aplicarse la segunda migración: familia NULL y unicidad correspondiente. Las entidades actuales no aportan por sí solas auditoría completa, revisión optimista, referencia a versión base, autor/fecha de publicación, validaciones persistidas ni trabajo asíncrono. El equipo debe implementarlos con mecanismos existentes de CONNEXA o agregar migraciones; no asumir columnas que no existen.

También requieren implementación: permisos con alcance, selección de versión vigente y transición sin solapamiento, bloqueo de reglas publicadas, jerarquía categoría, resolución artículo/local, composición validada de grupos y lectura de estado de integración PDD.

Secuencia recomendada de construcción: migraciones y catálogos → listado/detalle/editor de borradores → resolver aplicación y validar cobertura → auditoría/concurrencia/publicación → integración PDD. Si se entrega por etapas, la publicación permanece deshabilitada hasta que sus garantías backend estén completas; no reemplazarla con un cambio manual de estado.
