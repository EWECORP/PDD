# Reunión técnica Valkimia — Relevamiento e interfaz Connexa

Versión: **1.0**  
Fecha: **2026-08-24**  
Interlocutor Valkimia: **Gustavo Palacios**  
Proyecto: **Planificación de la Distribución (PDD) — Connexa**

## 1. Correo de convocatoria

**Asunto:** Reunión técnica Connexa–Valkimia: datos logísticos e interfaz de planificación de despachos

Hola Gustavo,

Estamos avanzando con el módulo de Planificación de la Distribución en
Connexa. La solución permitirá seleccionar necesidades por
artículo/sucursal, formar y cubicar viajes y entregar a Valkimia únicamente
las líneas aprobadas para preparación y despacho.

Quisiera coordinar una reunión técnica con vos para trabajar sobre dos temas:

1. relevar qué información logística actualizada mantiene Valkimia —embalaje,
   peso, volumen, palletización, tipos de vehículo, stock operativo y datos de
   despacho— y cómo podríamos consultarla de forma controlada;
2. acordar una interfaz inicial mediante tablas en el entorno de Valkimia para
   que Connexa publique los viajes planificados y Valkimia informe aceptación,
   faltantes, preparación, despacho, guía y transporte utilizado.

La idea inicial es mantener identificadores únicos de Connexa en cada lote y
línea, asegurar idempotencia y separar las tablas que escribe Connexa de las
que escribe Valkimia. De esta forma podremos reintentar y conciliar sin
duplicar operaciones ni sobrescribir datos de otro sistema.

Si fuera posible, sería muy útil contar antes de la reunión con:

- motor y versión de base de datos utilizados por Valkimia;
- diagrama o diccionario de las tablas relevantes;
- catálogo de estados de preparación y despacho;
- ejemplo anonimizado de una orden preparada parcialmente y de un despacho;
- modelo actual de tipos de vehículo y capacidades;
- mecanismo disponible para detectar registros nuevos o modificados.

Adjunto una propuesta preliminar de interfaz para usarla como punto de partida;
no pretende condicionar el diseño interno de Valkimia.

Propongo una reunión de 75 minutos. Como resultado nos gustaría dejar acordado
el contrato de datos, las responsabilidades de escritura, los estados, la
estrategia de reintentos y un plan de prueba entre ambos equipos.

Muchas gracias.

Saludos,  
Eduardo Ettlin

## 2. Objetivos de la reunión

1. Identificar fuentes Valkimia más confiables o actuales que SGM.
2. Obtener claves, unidades, vigencias y timestamps de actualización.
3. Acordar la granularidad de publicación: viaje completo o una importación
   por parada/sucursal.
4. Acordar el contrato Connexa → Valkimia.
5. Acordar el contrato Valkimia → Connexa.
6. Definir idempotencia, estados, parciales, cancelaciones y correcciones.
7. Definir conectividad, seguridad, polling, retención y soporte.
8. Salir con responsables, entregables y fechas para una prueba DESA.

## 3. Agenda sugerida — 75 minutos

| Minutos | Tema |
| ---: | --- |
| 0–10 | Objetivo funcional y límites de responsabilidad |
| 10–25 | Modelo de datos y variables logísticas Valkimia |
| 25–40 | Publicación Connexa → Valkimia |
| 40–55 | Estados, cantidades y despacho Valkimia → Connexa |
| 55–65 | Seguridad, transacciones, polling y operación |
| 65–75 | Decisiones, responsables, muestras y plan de prueba |

## 4. Contexto que debemos explicar

- Connexa calcula el backlog DECAS y el planificador selecciona las líneas.
- Connexa forma viajes, paradas y cantidades y realiza cubicaje.
- Un viaje se publica solamente después de ser aprobado.
- Valkimia no recibe todo el backlog: recibe carga operativa concreta.
- Valkimia valida stock real, acepta o rechaza, prepara y despacha.
- El cumplimiento de la necesidad en Connexa se produce al despacho, no al
  importar ni al preparar.
- Una necesidad no atendida o rechazada vuelve a quedar disponible en Connexa.

## 5. Información del modelo Valkimia que debemos solicitar

### 5.1 Artículos y configuración logística

Por cada configuración artículo/proveedor/embalaje, si existe:

- código de artículo SGM y código interno Valkimia;
- GTIN/EAN de unidad y bulto;
- unidad base y unidad de preparación;
- factor unidades por bulto;
- bultos por capa y capas por pallet;
- unidades y bultos por pallet;
- peso neto y bruto de unidad/bulto;
- largo, ancho, alto y volumen de unidad/bulto;
- tipo y dimensiones del pallet;
- altura y peso bruto del pallet cargado;
- apilable, niveles de apilado, frágil y orientación;
- zona y rango de temperatura;
- mercancía peligrosa o restricciones de transporte;
- proveedor y configuración predeterminada;
- fuente del dato, calidad/verificación, vigencia desde/hasta;
- timestamp o versión de última modificación.

Preguntas imprescindibles:

1. ¿La configuración es única por artículo o cambia por proveedor?
2. ¿Peso y volumen son medidos, declarados por GS1/proveedor o calculados?
3. ¿Qué unidad utiliza físicamente cada columna?
4. ¿Los factores describen compra, almacenamiento o preparación?
5. ¿Se conserva historia o solamente el valor actual?
6. ¿Cómo se identifica la configuración vigente y predeterminada?

### 5.2 Stock y operación de depósito

- stock físico, reservado, comprometido, bloqueado y disponible;
- ubicación/sector y estado de inventario;
- stock usado por Valkimia para aceptar la preparación;
- tareas u olas de preparación;
- faltantes y códigos de motivo;
- sustituciones, anulaciones y correcciones;
- fecha/hora confiable del dato.

Debemos acordar la fórmula exacta de “stock disponible Valkimia”. No debe
inferirse a partir de nombres de columnas.

### 5.3 Vehículos y transporte

- código y descripción del tipo de vehículo;
- carga útil máxima: confirmar si es carga transportable o peso bruto total;
- volumen útil y unidad;
- posiciones de pallet y pallet equivalente;
- vehículos/patentes, acoplados y transportistas;
- conductor, ruta, paradas, guía/remito y viaje Valkimia;
- salida real, llegada estimada y entrega;
- vigencia y fecha de actualización de cada catálogo.

## 6. Contrato de publicación que debemos acordar

Identificadores que Valkimia debe conservar sin truncar:

| Campo | Origen | Uso |
| --- | --- | --- |
| `connexaExecutionId` | `pdd_valkimia_import_uuid` | Identidad del lote publicado |
| `connexaLineId` | `pdd_valkimia_import_line_uuid` | Identidad idempotente de la línea |
| `connexaTripId` | `dispatch_trip_uuid` | Viaje de Connexa |
| `connexaTripLineId` | `dispatch_trip_line_uuid` | Línea del viaje |
| `backlogLineUuid` | Backlog | Trazabilidad de la necesidad |

No se debe conciliar por artículo y sucursal solamente. Esos campos no
identifican un intento de preparación ni un despacho.

## 7. Recomendación de propiedad de tablas

No recomendamos que ambos sistemas actualicen la misma fila.

| Dirección | Tablas propuestas | Único escritor |
| --- | --- | --- |
| Connexa → Valkimia | `CNX_PDD_ENVIO`, `CNX_PDD_ENVIO_LINEA` | Connexa |
| Valkimia → Connexa | `CNX_PDD_EVENTO_ENVIO`, `CNX_PDD_EVENTO_LINEA` | Valkimia |
| Valkimia → Connexa | `CNX_PDD_DESPACHO`, `CNX_PDD_DESPACHO_LINEA` | Valkimia |

Ventajas:

- no hay actualizaciones cruzadas ni bloqueos ambiguos;
- Valkimia puede confirmar o rechazar técnicamente el lote completo;
- los eventos son append-only y no se pierden transiciones;
- un despacho puede contener varias líneas y una línea puede despacharse
  parcialmente en más de un despacho;
- los reintentos se deduplican por UUID;
- Connexa puede reconstruir y conciliar el estado completo.

El borrador físico se entrega en
`PDD - Propuesta Interfaz SQL Server Valkimia v1.0.sql`. Si Valkimia utiliza
otro motor se conserva el contrato lógico y se adapta el DDL.

## 8. Cantidades y estados

Recomendación: Valkimia informa cantidades **acumuladas por línea**:

```text
solicitada >= aceptada >= preparada >= despachada >= entregada
```

Además informa acumulados cancelados y rechazados. No se debe mezclar delta y
acumulado sin un indicador explícito.

Estados normalizados en Connexa:

```text
IMPORTED, ACCEPTED, PARTIAL, PREPARED, DISPATCHED,
DELIVERED, CANCELLED, REJECTED, FAILED, UNKNOWN
```

Gustavo debe entregar el catálogo nativo y ejemplos para mapear cada código.
Connexa conserva el código nativo y realiza la normalización; Valkimia no tiene
que adoptar nuestros nombres.

Para el lote completo se necesita, como mínimo, distinguir recepción,
aceptación y rechazo técnico. Un error de esquema o de cabecera debe poder
informarse aun cuando Valkimia no haya creado eventos de línea.

## 8.1 Forma recomendada de exponer datos logísticos

Solicitar vistas de contrato de sólo lectura —por ejemplo,
`VW_CNX_ARTICULO_LOGISTICA`, `VW_CNX_TIPO_VEHICULO` y
`VW_CNX_STOCK_OPERATIVO`— en lugar de acceso directo a tablas internas. Las
vistas deben tener claves estables, unidades explícitas y un campo de versión o
última modificación. De ese modo Valkimia puede evolucionar su modelo interno
sin romper la ingesta de Connexa.

## 9. Preguntas que deben responderse

### Publicación

1. ¿Valkimia admite un viaje con múltiples sucursales/paradas?
2. ¿Necesita una cabecera por viaje o una por sucursal?
3. ¿Qué campos son obligatorios para crear una tarea de preparación?
4. ¿Puede utilizar UUID de 36 caracteres como clave idempotente?
5. ¿Cómo confirma que leyó y aceptó el lote?
6. ¿Puede aceptar parcialmente una importación?
7. ¿Qué sucede ante una línea sin stock?

### Retorno

1. ¿Qué estados nativos existen y cuáles son terminales?
2. ¿Las cantidades disponibles son acumuladas o del último evento?
3. ¿Puede disminuir una cantidad previamente informada por corrección?
4. ¿Una línea puede prepararse o despacharse en varias entregas?
5. ¿Cuándo se asignan guía, vehículo, transportista y conductor?
6. ¿Cómo relacionar cada despacho con las líneas y cantidades efectivas?
7. ¿Existe un ID de evento o `rowversion` monotónico confiable?

### Técnica y operación

1. Motor, versión, codificación y zona horaria de la base.
2. Servidor y base por DESA/TEST/PROD.
3. Cuenta técnica, permisos mínimos y cifrado de conexión.
4. Transacciones e índices admitidos en tablas de interfaz.
5. Frecuencia máxima de lectura/escritura y ventana de mantenimiento.
6. Retención y archivado.
7. SLA, monitoreo y contactos ante incidentes.
8. Procedimiento de reenvío y reconciliación completa.

## 10. Acuerdos que deben quedar escritos

Completar durante la reunión:

| Decisión | Acuerdo | Responsable | Fecha |
| --- | --- | --- | --- |
| Motor y versión |  | Gustavo |  |
| Granularidad viaje/parada |  | Ambos |  |
| Tablas y propietario de escritura |  | Ambos |  |
| Identificadores y longitudes |  | Gustavo |  |
| Cantidades acumuladas/delta |  | Gustavo |  |
| Catálogo de estados |  | Gustavo |  |
| Campo monotónico para polling |  | Gustavo |  |
| Guía y transporte |  | Gustavo |  |
| Unidades logísticas |  | Gustavo |  |
| Reintentos e idempotencia |  | Ambos |  |
| Seguridad y conectividad |  | Infraestructura |  |
| Retención y reconciliación |  | Ambos |  |
| Datos y fecha de prueba DESA |  | Ambos |  |

## 11. Evidencia solicitada después de la reunión

1. DDL real de las tablas fuente logísticas.
2. Diccionario con unidad y semántica por campo.
3. Catálogo de tipos de vehículo.
4. Catálogo de estados Valkimia.
5. Muestras anonimizadas: aceptada, parcial, sin stock, preparada, despachada,
   cancelada, corregida y entregada.
6. DDL ajustado de las tablas de interfaz.
7. Plan de conectividad y credenciales técnicas por ambiente.
8. Caso de prueba completo con dos sucursales y un despacho parcial.

## 12. Criterios de aceptación de la prueba conjunta

- publicar dos veces el mismo lote no duplica líneas;
- una línea sin stock se rechaza con motivo explícito;
- una preparación parcial libera el remanente acordado;
- un despacho parcial informa guía y cantidad efectiva;
- un segundo despacho de la misma línea se concilia correctamente;
- Connexa no pierde eventos aunque repita el polling;
- un estado desconocido queda aislado, no altera cantidades y genera alerta;
- una corrección no elimina historia;
- la reconciliación completa reproduce el mismo estado final.
