/*
===============================================================================
PDD - Propuesta de interfaz SQL Server Valkimia v1.1

ESTADO: BORRADOR PARA REUNION TECNICA.
NO EJECUTAR SIN APROBACION DE VALKIMIA, DBA E INFRAESTRUCTURA.

Motor supuesto: Microsoft SQL Server.
Servidor/base tentativos: DIARCO-VKMSQL / VALKIMIA.

Cambios principales respecto de v1.0:
- cursor monotónico CNX_ENVIO_SEQ para polling Connexa -> Valkimia;
- contrato explícito de REQUEST_PAYLOAD_HASH SHA-256;
- UUID de eventos y despachos provistos por Valkimia para reintentos estables;
- consistencia ejecución/línea mediante claves foráneas compuestas;
- una línea de viaje puede republicarse en una nueva ejecución corregida;
- CHANGE_VERSION rowversion en cabecera y detalle de despacho;
- nombres separados para hash de solicitud y hash de evento;
- polling por cursores durables y reconciliación periódica.

Propiedad:
- Connexa inserta solamente CNX_PDD_ENVIO y CNX_PDD_ENVIO_LINEA.
- Valkimia inserta CNX_PDD_EVENTO_ENVIO y CNX_PDD_EVENTO_LINEA.
- Valkimia inserta/actualiza CNX_PDD_DESPACHO y CNX_PDD_DESPACHO_LINEA.
- Ambos sistemas pueden leer todas las tablas de interfaz.
- Ningún proceso borra filas ni modifica filas propiedad del otro sistema.

Regla de publicación:
- Connexa inserta la cabecera y todas las líneas en UNA MISMA TRANSACCION.
- Valkimia procesa solamente datos confirmados por COMMIT.
- LINE_COUNT y STOP_COUNT se verifican al consumir el lote.

Este archivo crea objetos desde cero. No es una migración idempotente y no
incluye DROP, rollback, usuarios ni grants definitivos.
===============================================================================
*/

SET ANSI_NULLS ON;
SET QUOTED_IDENTIFIER ON;
SET XACT_ABORT ON;
GO

/*
-------------------------------------------------------------------------------
Contrato REQUEST_PAYLOAD_HASH: CNX-PDD-HASH-1
-------------------------------------------------------------------------------
Algoritmo:
    SHA-256 sobre los bytes UTF-8 de un documento JSON canónico, expresado como
    64 caracteres hexadecimales en minúsculas.

Campos de cabecera incluidos, en este orden:
    schemaVersion, connexaTripId, originCd, plannedDepartureAt, routeCode,
    vehicleTypeCode, vehicleReference, carrierReference, stopCount, lineCount.

Campos de cada línea incluidos, en este orden:
    connexaTripLineId, backlogLineUuid, lineSequence, stopSequence,
    codigoArticulo, sucursal, uom, requestedQuantity, estimatedPackages,
    estimatedPallets, estimatedWeightKg, estimatedVolumeM3.

Campos excluidos por ser técnicos, de auditoría o generados:
    CNX_ENVIO_SEQ, CONNEXA_EXECUTION_ID, CONNEXA_LINE_ID,
    REQUEST_PAYLOAD_HASH, REQUESTED_AT, REQUESTED_BY, CREATED_AT.

Canonicalización:
- propiedades en el orden anterior, sin espacios ni saltos de línea;
- líneas ordenadas por LINE_SEQUENCE y CONNEXA_TRIP_LINE_ID;
- UUID en minúsculas y con guiones;
- timestamps convertidos a UTC con milisegundos: yyyy-MM-ddTHH:mm:ss.fffZ;
- decimales como strings sin exponente: escala 6, volumen escala 9;
- null se incluye explícitamente; null, cadena vacía y cero son distintos;
- códigos normalizados antes de persistir y hashear;
- strings Unicode normalizados a NFC y serializados como UTF-8.

El hash se calcula sobre los mismos valores que se insertan. La base solamente
valida formato hexadecimal; Connexa calcula el hash y Valkimia lo recalcula.
-------------------------------------------------------------------------------
*/

CREATE TABLE dbo.CNX_PDD_ENVIO (
    CNX_ENVIO_SEQ              bigint IDENTITY(1,1) NOT NULL,
    CONNEXA_EXECUTION_ID       uniqueidentifier NOT NULL,
    CONNEXA_TRIP_ID            uniqueidentifier NOT NULL,
    SCHEMA_VERSION             varchar(20) NOT NULL,
    PAYLOAD_HASH_VERSION       varchar(30) NOT NULL
        CONSTRAINT DF_CNX_PDD_ENVIO_HASH_VERSION DEFAULT 'CNX-PDD-HASH-1',
    PAYLOAD_HASH_ALGORITHM     varchar(20) NOT NULL
        CONSTRAINT DF_CNX_PDD_ENVIO_HASH_ALGORITHM DEFAULT 'SHA-256',
    ORIGIN_CD                  int NOT NULL,
    PLANNED_DEPARTURE_AT       datetimeoffset(3) NULL,
    ROUTE_CODE                 varchar(80) NULL,
    VEHICLE_TYPE_CODE          varchar(40) NULL,
    VEHICLE_REFERENCE          varchar(80) NULL,
    CARRIER_REFERENCE          varchar(100) NULL,
    STOP_COUNT                 int NOT NULL,
    LINE_COUNT                 int NOT NULL,
    REQUEST_PAYLOAD_HASH       varchar(64) NOT NULL,
    REQUESTED_AT               datetimeoffset(3) NOT NULL,
    REQUESTED_BY               varchar(100) NOT NULL,

    CONSTRAINT PK_CNX_PDD_ENVIO
        PRIMARY KEY CLUSTERED (CNX_ENVIO_SEQ),
    CONSTRAINT UQ_CNX_PDD_ENVIO_EXECUTION
        UNIQUE (CONNEXA_EXECUTION_ID),
    CONSTRAINT UQ_CNX_PDD_ENVIO_EXECUTION_TRIP
        UNIQUE (CONNEXA_EXECUTION_ID, CONNEXA_TRIP_ID),
    CONSTRAINT CK_CNX_PDD_ENVIO_ORIGIN
        CHECK (ORIGIN_CD = 41),
    CONSTRAINT CK_CNX_PDD_ENVIO_COUNTS
        CHECK (STOP_COUNT > 0 AND LINE_COUNT > 0),
    CONSTRAINT CK_CNX_PDD_ENVIO_HASH_CONTRACT
        CHECK (
            PAYLOAD_HASH_VERSION = 'CNX-PDD-HASH-1'
            AND PAYLOAD_HASH_ALGORITHM = 'SHA-256'
            AND DATALENGTH(REQUEST_PAYLOAD_HASH) = 64
            AND REQUEST_PAYLOAD_HASH COLLATE Latin1_General_100_BIN2
                NOT LIKE '%[^0-9a-f]%'
        )
);
GO

/*
Impide publicar dos veces el mismo contenido lógico del mismo viaje aunque se
haya generado por error otro CONNEXA_EXECUTION_ID.
*/
CREATE UNIQUE INDEX UX_CNX_PDD_ENVIO_TRIP_HASH
    ON dbo.CNX_PDD_ENVIO (CONNEXA_TRIP_ID, REQUEST_PAYLOAD_HASH);
GO

CREATE TABLE dbo.CNX_PDD_ENVIO_LINEA (
    CONNEXA_LINE_ID             uniqueidentifier NOT NULL,
    CONNEXA_EXECUTION_ID        uniqueidentifier NOT NULL,
    CONNEXA_TRIP_LINE_ID        uniqueidentifier NOT NULL,
    BACKLOG_LINE_UUID           uniqueidentifier NOT NULL,
    LINE_SEQUENCE               int NOT NULL,
    STOP_SEQUENCE               int NOT NULL,
    CODIGO_ARTICULO             int NOT NULL,
    SUCURSAL                    int NOT NULL,
    UOM                         varchar(20) NOT NULL,
    REQUESTED_QUANTITY          decimal(18,6) NOT NULL,
    ESTIMATED_PACKAGES          decimal(18,6) NULL,
    ESTIMATED_PALLETS           decimal(18,6) NULL,
    ESTIMATED_WEIGHT_KG         decimal(18,6) NULL,
    ESTIMATED_VOLUME_M3         decimal(18,9) NULL,
    CREATED_AT                  datetimeoffset(3) NOT NULL,

    CONSTRAINT PK_CNX_PDD_ENVIO_LINEA
        PRIMARY KEY (CONNEXA_LINE_ID),
    CONSTRAINT FK_CNX_PDD_ENVIO_LINEA_ENVIO
        FOREIGN KEY (CONNEXA_EXECUTION_ID)
        REFERENCES dbo.CNX_PDD_ENVIO (CONNEXA_EXECUTION_ID),
    CONSTRAINT UQ_CNX_PDD_ENVIO_LINEA_EXEC_LINE
        UNIQUE (CONNEXA_EXECUTION_ID, CONNEXA_LINE_ID),
    CONSTRAINT UQ_CNX_PDD_ENVIO_LINEA_EXEC_TRIP_LINE
        UNIQUE (CONNEXA_EXECUTION_ID, CONNEXA_TRIP_LINE_ID),
    CONSTRAINT CK_CNX_PDD_ENVIO_LINEA_SEQUENCE
        CHECK (LINE_SEQUENCE > 0 AND STOP_SEQUENCE > 0),
    CONSTRAINT CK_CNX_PDD_ENVIO_LINEA_CODES
        CHECK (
            CODIGO_ARTICULO > 0
            AND SUCURSAL > 0
            AND LEN(LTRIM(RTRIM(UOM))) > 0
        ),
    CONSTRAINT CK_CNX_PDD_ENVIO_LINEA_QUANTITY
        CHECK (REQUESTED_QUANTITY > 0),
    CONSTRAINT CK_CNX_PDD_ENVIO_LINEA_ESTIMATES
        CHECK (
            (ESTIMATED_PACKAGES IS NULL OR ESTIMATED_PACKAGES >= 0)
            AND (ESTIMATED_PALLETS IS NULL OR ESTIMATED_PALLETS >= 0)
            AND (ESTIMATED_WEIGHT_KG IS NULL OR ESTIMATED_WEIGHT_KG >= 0)
            AND (ESTIMATED_VOLUME_M3 IS NULL OR ESTIMATED_VOLUME_M3 >= 0)
        )
);
GO

CREATE INDEX IX_CNX_PDD_ENVIO_LINEA_EXECUTION
    ON dbo.CNX_PDD_ENVIO_LINEA
       (CONNEXA_EXECUTION_ID, STOP_SEQUENCE, LINE_SEQUENCE)
    INCLUDE (
        CONNEXA_LINE_ID,
        CONNEXA_TRIP_LINE_ID,
        CODIGO_ARTICULO,
        SUCURSAL,
        REQUESTED_QUANTITY
    );
GO

/*
Acuse técnico/funcional append-only del lote. VALKIMIA_EVENT_UUID no posee
DEFAULT: Valkimia debe generar uno estable y reutilizarlo en cada reintento.

VALIDATED_REQUEST_PAYLOAD_HASH es el hash recalculado por Valkimia. Connexa lo
compara con CNX_PDD_ENVIO.REQUEST_PAYLOAD_HASH. Ante diferencia, Valkimia
registra un rechazo de lote y no procesa líneas.

EVENT_PAYLOAD_HASH es el SHA-256 canónico del contenido del propio evento; no
es el hash de la solicitud Connexa.
*/
CREATE TABLE dbo.CNX_PDD_EVENTO_ENVIO (
    VALKIMIA_EXECUTION_EVENT_ID bigint IDENTITY(1,1) NOT NULL,
    VALKIMIA_EVENT_UUID         uniqueidentifier NOT NULL,
    CONNEXA_EXECUTION_ID        uniqueidentifier NOT NULL,
    EXTERNAL_REFERENCE          varchar(160) NULL,
    EXTERNAL_STATUS_CODE        varchar(100) NOT NULL,
    EXTERNAL_STATUS_DESCRIPTION varchar(200) NULL,
    REASON_CODE                 varchar(80) NULL,
    REASON_DETAIL               varchar(500) NULL,
    EXTERNAL_OCCURRED_AT        datetimeoffset(3) NOT NULL,
    RECORDED_AT                 datetimeoffset(3) NOT NULL
        CONSTRAINT DF_CNX_PDD_EXEC_EVENT_RECORDED DEFAULT SYSDATETIMEOFFSET(),
    VALIDATED_REQUEST_PAYLOAD_HASH varchar(64) NULL,
    EVENT_PAYLOAD_HASH          varchar(64) NOT NULL,

    CONSTRAINT PK_CNX_PDD_EVENTO_ENVIO
        PRIMARY KEY CLUSTERED (VALKIMIA_EXECUTION_EVENT_ID),
    CONSTRAINT UQ_CNX_PDD_EVENTO_ENVIO_UUID
        UNIQUE (VALKIMIA_EVENT_UUID),
    CONSTRAINT FK_CNX_PDD_EVENTO_ENVIO_ENVIO
        FOREIGN KEY (CONNEXA_EXECUTION_ID)
        REFERENCES dbo.CNX_PDD_ENVIO (CONNEXA_EXECUTION_ID),
    CONSTRAINT CK_CNX_PDD_EVENTO_ENVIO_HASHES
        CHECK (
            (
                VALIDATED_REQUEST_PAYLOAD_HASH IS NULL
                OR (
                    DATALENGTH(VALIDATED_REQUEST_PAYLOAD_HASH) = 64
                    AND VALIDATED_REQUEST_PAYLOAD_HASH
                        COLLATE Latin1_General_100_BIN2
                        NOT LIKE '%[^0-9a-f]%'
                )
            )
            AND DATALENGTH(EVENT_PAYLOAD_HASH) = 64
            AND EVENT_PAYLOAD_HASH COLLATE Latin1_General_100_BIN2
                NOT LIKE '%[^0-9a-f]%'
        )
);
GO

CREATE INDEX IX_CNX_PDD_EVENTO_ENVIO_EXECUTION
    ON dbo.CNX_PDD_EVENTO_ENVIO
       (CONNEXA_EXECUTION_ID, VALKIMIA_EXECUTION_EVENT_ID)
    INCLUDE (
        EXTERNAL_STATUS_CODE,
        EXTERNAL_OCCURRED_AT,
        VALIDATED_REQUEST_PAYLOAD_HASH
    );
GO

/*
Evento append-only por línea. EXTERNAL_STATUS_CODE conserva el estado nativo;
Connexa realiza el mapping. CUMULATIVE es la semántica recomendada. DELTA queda
disponible solamente si ambos equipos lo acuerdan expresamente.

Fuente de verdad propuesta: CNX_PDD_DESPACHO_LINEA determina el cumplimiento
físico. DISPATCHED_QUANTITY de este evento es una proyección operativa y debe
reconciliar con la suma de detalles de despachos válidos según el mapping.
*/
CREATE TABLE dbo.CNX_PDD_EVENTO_LINEA (
    VALKIMIA_EVENT_ID           bigint IDENTITY(1,1) NOT NULL,
    VALKIMIA_EVENT_UUID         uniqueidentifier NOT NULL,
    CONNEXA_EXECUTION_ID        uniqueidentifier NOT NULL,
    CONNEXA_LINE_ID             uniqueidentifier NOT NULL,
    EXTERNAL_REFERENCE          varchar(160) NULL,
    EXTERNAL_LINE_REFERENCE     varchar(160) NULL,
    EXTERNAL_STATUS_CODE        varchar(100) NOT NULL,
    EXTERNAL_STATUS_DESCRIPTION varchar(200) NULL,
    QUANTITY_SEMANTICS          varchar(15) NOT NULL
        CONSTRAINT DF_CNX_PDD_LINE_EVENT_SEMANTICS DEFAULT 'CUMULATIVE',
    ACCEPTED_QUANTITY           decimal(18,6) NOT NULL,
    PREPARED_QUANTITY           decimal(18,6) NOT NULL,
    DISPATCHED_QUANTITY         decimal(18,6) NOT NULL,
    DELIVERED_QUANTITY          decimal(18,6) NOT NULL,
    CANCELLED_QUANTITY          decimal(18,6) NOT NULL,
    REJECTED_QUANTITY           decimal(18,6) NOT NULL,
    REASON_CODE                 varchar(80) NULL,
    REASON_DETAIL               varchar(500) NULL,
    EXTERNAL_OCCURRED_AT        datetimeoffset(3) NOT NULL,
    RECORDED_AT                 datetimeoffset(3) NOT NULL
        CONSTRAINT DF_CNX_PDD_LINE_EVENT_RECORDED DEFAULT SYSDATETIMEOFFSET(),
    EVENT_PAYLOAD_HASH          varchar(64) NOT NULL,

    CONSTRAINT PK_CNX_PDD_EVENTO_LINEA
        PRIMARY KEY CLUSTERED (VALKIMIA_EVENT_ID),
    CONSTRAINT UQ_CNX_PDD_EVENTO_LINEA_UUID
        UNIQUE (VALKIMIA_EVENT_UUID),
    CONSTRAINT FK_CNX_PDD_EVENTO_LINEA_EXEC_LINE
        FOREIGN KEY (CONNEXA_EXECUTION_ID, CONNEXA_LINE_ID)
        REFERENCES dbo.CNX_PDD_ENVIO_LINEA
            (CONNEXA_EXECUTION_ID, CONNEXA_LINE_ID),
    CONSTRAINT CK_CNX_PDD_EVENTO_LINEA_SEMANTICS
        CHECK (QUANTITY_SEMANTICS IN ('CUMULATIVE', 'DELTA')),
    CONSTRAINT CK_CNX_PDD_EVENTO_LINEA_QUANTITIES
        CHECK (
            ACCEPTED_QUANTITY >= 0
            AND PREPARED_QUANTITY >= 0
            AND DISPATCHED_QUANTITY >= 0
            AND DELIVERED_QUANTITY >= 0
            AND CANCELLED_QUANTITY >= 0
            AND REJECTED_QUANTITY >= 0
            AND (
                QUANTITY_SEMANTICS <> 'CUMULATIVE'
                OR (
                    ACCEPTED_QUANTITY >= PREPARED_QUANTITY
                    AND PREPARED_QUANTITY >= DISPATCHED_QUANTITY
                    AND DISPATCHED_QUANTITY >= DELIVERED_QUANTITY
                )
            )
        ),
    CONSTRAINT CK_CNX_PDD_EVENTO_LINEA_HASH
        CHECK (
            DATALENGTH(EVENT_PAYLOAD_HASH) = 64
            AND EVENT_PAYLOAD_HASH COLLATE Latin1_General_100_BIN2
                NOT LIKE '%[^0-9a-f]%'
        )
);
GO

CREATE INDEX IX_CNX_PDD_EVENTO_LINEA_CONNEXA
    ON dbo.CNX_PDD_EVENTO_LINEA
       (CONNEXA_EXECUTION_ID, CONNEXA_LINE_ID, VALKIMIA_EVENT_ID)
    INCLUDE (
        EXTERNAL_STATUS_CODE,
        QUANTITY_SEMANTICS,
        EXTERNAL_OCCURRED_AT
    );
GO

/*
Cabecera real del despacho/embarque generado por Valkimia. Toda modificación
de la cabecera genera automáticamente un nuevo CHANGE_VERSION.

UPDATED_AT no se actualiza mediante DEFAULT durante un UPDATE: Valkimia debe
asignar SYSDATETIMEOFFSET() explícitamente cuando modifique la cabecera.

VALKIMIA_DISPATCH_UUID no posee DEFAULT: debe ser estable entre reintentos.
La FK compuesta impide asociar el despacho a un viaje diferente del que
corresponde a CONNEXA_EXECUTION_ID.
*/
CREATE TABLE dbo.CNX_PDD_DESPACHO (
    VALKIMIA_DISPATCH_ID        bigint IDENTITY(1,1) NOT NULL,
    VALKIMIA_DISPATCH_UUID      uniqueidentifier NOT NULL,
    CONNEXA_EXECUTION_ID        uniqueidentifier NOT NULL,
    CONNEXA_TRIP_ID             uniqueidentifier NOT NULL,
    EXTERNAL_DOCUMENT           varchar(160) NULL,
    GUIDE_NUMBER                varchar(100) NULL,
    SHIPMENT_REFERENCE          varchar(160) NULL,
    EXTERNAL_STATUS_CODE        varchar(100) NOT NULL,
    CARRIER_CODE                varchar(80) NULL,
    CARRIER_NAME                varchar(160) NULL,
    VEHICLE_TYPE_CODE           varchar(40) NULL,
    VEHICLE_TYPE_DESCRIPTION    varchar(160) NULL,
    TRACTOR_PLATE               varchar(20) NULL,
    TRAILER_PLATE               varchar(20) NULL,
    DRIVER_REFERENCE            varchar(80) NULL,
    DRIVER_NAME                 varchar(160) NULL,
    ACTUAL_DEPARTURE_AT         datetimeoffset(3) NULL,
    ESTIMATED_ARRIVAL_AT        datetimeoffset(3) NULL,
    ACTUAL_WEIGHT_KG            decimal(18,6) NULL,
    ACTUAL_VOLUME_M3            decimal(18,9) NULL,
    ACTUAL_PALLETS              decimal(18,6) NULL,
    CREATED_AT                  datetimeoffset(3) NOT NULL
        CONSTRAINT DF_CNX_PDD_DISPATCH_CREATED DEFAULT SYSDATETIMEOFFSET(),
    UPDATED_AT                  datetimeoffset(3) NOT NULL
        CONSTRAINT DF_CNX_PDD_DISPATCH_UPDATED DEFAULT SYSDATETIMEOFFSET(),
    CHANGE_VERSION              rowversion NOT NULL,

    CONSTRAINT PK_CNX_PDD_DESPACHO
        PRIMARY KEY (VALKIMIA_DISPATCH_ID),
    CONSTRAINT UQ_CNX_PDD_DESPACHO_UUID
        UNIQUE (VALKIMIA_DISPATCH_UUID),
    CONSTRAINT UQ_CNX_PDD_DESPACHO_ID_EXEC
        UNIQUE (VALKIMIA_DISPATCH_ID, CONNEXA_EXECUTION_ID),
    CONSTRAINT FK_CNX_PDD_DESPACHO_EXEC_TRIP
        FOREIGN KEY (CONNEXA_EXECUTION_ID, CONNEXA_TRIP_ID)
        REFERENCES dbo.CNX_PDD_ENVIO
            (CONNEXA_EXECUTION_ID, CONNEXA_TRIP_ID),
    CONSTRAINT CK_CNX_PDD_DESPACHO_TOTALS
        CHECK (
            (ACTUAL_WEIGHT_KG IS NULL OR ACTUAL_WEIGHT_KG >= 0)
            AND (ACTUAL_VOLUME_M3 IS NULL OR ACTUAL_VOLUME_M3 >= 0)
            AND (ACTUAL_PALLETS IS NULL OR ACTUAL_PALLETS >= 0)
        ),
    CONSTRAINT CK_CNX_PDD_DESPACHO_UPDATED
        CHECK (UPDATED_AT >= CREATED_AT)
);
GO

CREATE INDEX IX_CNX_PDD_DESPACHO_CHANGE_VERSION
    ON dbo.CNX_PDD_DESPACHO (CHANGE_VERSION)
    INCLUDE (
        VALKIMIA_DISPATCH_ID,
        VALKIMIA_DISPATCH_UUID,
        CONNEXA_EXECUTION_ID,
        EXTERNAL_STATUS_CODE,
        UPDATED_AT
    );
GO

CREATE INDEX IX_CNX_PDD_DESPACHO_EXECUTION
    ON dbo.CNX_PDD_DESPACHO
       (CONNEXA_EXECUTION_ID, VALKIMIA_DISPATCH_ID);
GO

/*
Cantidad efectiva de una línea en un despacho. CONNEXA_EXECUTION_ID permite
validar que tanto el despacho como la línea pertenecen a la misma ejecución.

CHANGE_VERSION propio evita perder una modificación del detalle aunque la
cabecera del despacho no sea actualizada. Connexa mantiene un checkpoint
separado para esta tabla.

UPDATED_AT debe ser asignado explícitamente por Valkimia en cada UPDATE.
*/
CREATE TABLE dbo.CNX_PDD_DESPACHO_LINEA (
    VALKIMIA_DISPATCH_ID        bigint NOT NULL,
    CONNEXA_EXECUTION_ID        uniqueidentifier NOT NULL,
    CONNEXA_LINE_ID             uniqueidentifier NOT NULL,
    DISPATCHED_QUANTITY         decimal(18,6) NOT NULL,
    EXTERNAL_LINE_REFERENCE     varchar(160) NULL,
    CREATED_AT                  datetimeoffset(3) NOT NULL
        CONSTRAINT DF_CNX_PDD_DISPATCH_LINE_CREATED DEFAULT SYSDATETIMEOFFSET(),
    UPDATED_AT                  datetimeoffset(3) NOT NULL
        CONSTRAINT DF_CNX_PDD_DISPATCH_LINE_UPDATED DEFAULT SYSDATETIMEOFFSET(),
    CHANGE_VERSION              rowversion NOT NULL,

    CONSTRAINT PK_CNX_PDD_DESPACHO_LINEA
        PRIMARY KEY (VALKIMIA_DISPATCH_ID, CONNEXA_LINE_ID),
    CONSTRAINT FK_CNX_PDD_DESPACHO_LINEA_DISPATCH_EXEC
        FOREIGN KEY (VALKIMIA_DISPATCH_ID, CONNEXA_EXECUTION_ID)
        REFERENCES dbo.CNX_PDD_DESPACHO
            (VALKIMIA_DISPATCH_ID, CONNEXA_EXECUTION_ID),
    CONSTRAINT FK_CNX_PDD_DESPACHO_LINEA_EXEC_LINE
        FOREIGN KEY (CONNEXA_EXECUTION_ID, CONNEXA_LINE_ID)
        REFERENCES dbo.CNX_PDD_ENVIO_LINEA
            (CONNEXA_EXECUTION_ID, CONNEXA_LINE_ID),
    CONSTRAINT CK_CNX_PDD_DESPACHO_LINEA_QUANTITY
        CHECK (DISPATCHED_QUANTITY > 0),
    CONSTRAINT CK_CNX_PDD_DESPACHO_LINEA_UPDATED
        CHECK (UPDATED_AT >= CREATED_AT)
);
GO

CREATE INDEX IX_CNX_PDD_DESPACHO_LINEA_CHANGE_VERSION
    ON dbo.CNX_PDD_DESPACHO_LINEA (CHANGE_VERSION)
    INCLUDE (
        VALKIMIA_DISPATCH_ID,
        CONNEXA_EXECUTION_ID,
        CONNEXA_LINE_ID,
        DISPATCHED_QUANTITY,
        UPDATED_AT
    );
GO

CREATE INDEX IX_CNX_PDD_DESPACHO_LINEA_EXECUTION
    ON dbo.CNX_PDD_DESPACHO_LINEA
       (CONNEXA_EXECUTION_ID, CONNEXA_LINE_ID, VALKIMIA_DISPATCH_ID);
GO

/*
===============================================================================
POLLING PROPUESTO
===============================================================================

Regla común:
1. leer un lote ordenado;
2. procesarlo idempotentemente;
3. guardar el checkpoint junto con los cambios locales en una transacción;
4. avanzar al máximo cursor confirmado, nunca al máximo solamente leído;
5. ejecutar reconciliación completa periódica de ejecuciones activas.

Los cursores pueden presentar saltos por rollback. Un salto no significa que
falte un registro. IDENTITY y rowversion tampoco son fechas de negocio.
*/

/* Valkimia: publicaciones Connexa posteriores a su checkpoint durable. */
DECLARE @LAST_CNX_ENVIO_SEQ bigint = 0;
DECLARE @BATCH_SIZE int = 500;
DECLARE @CONNEXA_EXECUTION_ID uniqueidentifier = NULL;
DECLARE @LAST_LINE_EVENT_ID bigint = 0;
DECLARE @LAST_EXECUTION_EVENT_ID bigint = 0;
DECLARE @LAST_DISPATCH_VERSION binary(8) = 0x0000000000000000;
DECLARE @LAST_DISPATCH_LINE_VERSION binary(8) = 0x0000000000000000;

SELECT TOP (@BATCH_SIZE) e.*
FROM dbo.CNX_PDD_ENVIO e
WHERE e.CNX_ENVIO_SEQ > @LAST_CNX_ENVIO_SEQ
ORDER BY e.CNX_ENVIO_SEQ;

/* Leer las líneas de cada ejecución seleccionada. */
SELECT l.*
FROM dbo.CNX_PDD_ENVIO_LINEA l
WHERE l.CONNEXA_EXECUTION_ID = @CONNEXA_EXECUTION_ID
ORDER BY l.STOP_SEQUENCE, l.LINE_SEQUENCE, l.CONNEXA_LINE_ID;

/* Connexa: eventos de línea posteriores a su checkpoint. */
SELECT TOP (@BATCH_SIZE) ev.*
FROM dbo.CNX_PDD_EVENTO_LINEA ev
WHERE ev.VALKIMIA_EVENT_ID > @LAST_LINE_EVENT_ID
ORDER BY ev.VALKIMIA_EVENT_ID;

/* Connexa: eventos de lote posteriores a su checkpoint independiente. */
SELECT TOP (@BATCH_SIZE) ev.*
FROM dbo.CNX_PDD_EVENTO_ENVIO ev
WHERE ev.VALKIMIA_EXECUTION_EVENT_ID > @LAST_EXECUTION_EVENT_ID
ORDER BY ev.VALKIMIA_EXECUTION_EVENT_ID;

/* Connexa: cabeceras de despacho nuevas o modificadas. */
SELECT TOP (@BATCH_SIZE) d.*
FROM dbo.CNX_PDD_DESPACHO d
WHERE d.CHANGE_VERSION > @LAST_DISPATCH_VERSION
ORDER BY d.CHANGE_VERSION;

/* Connexa: detalles de despacho nuevos o modificados. */
SELECT TOP (@BATCH_SIZE) dl.*
FROM dbo.CNX_PDD_DESPACHO_LINEA dl
WHERE dl.CHANGE_VERSION > @LAST_DISPATCH_LINE_VERSION
ORDER BY dl.CHANGE_VERSION;

/*
Los parámetros @CONNEXA_EXECUTION_ID, @LAST_LINE_EVENT_ID,
@LAST_EXECUTION_EVENT_ID, @LAST_DISPATCH_VERSION y
@LAST_DISPATCH_LINE_VERSION son provistos por los consumidores. No son
variables globales de SQL Server.

Suposición operativa para no saltar transacciones concurrentes:
- un único publicador lógico por dirección, o escritura serializada;
- transacciones breves;
- lectura sin READPAST;
- polling con solapamiento/reprocesamiento idempotente;
- reconciliación completa diaria.
===============================================================================
*/

/*
===============================================================================
PERMISOS MINIMOS A MATERIALIZAR CON ROLES/USUARIOS DEFINITIVOS
===============================================================================
Connexa:
- SELECT en las seis tablas;
- INSERT en CNX_PDD_ENVIO y CNX_PDD_ENVIO_LINEA;
- sin UPDATE ni DELETE sobre tablas Valkimia.

Valkimia:
- SELECT en las seis tablas;
- INSERT en CNX_PDD_EVENTO_ENVIO y CNX_PDD_EVENTO_LINEA;
- INSERT y UPDATE en CNX_PDD_DESPACHO y CNX_PDD_DESPACHO_LINEA;
- sin UPDATE ni DELETE sobre tablas Connexa;
- sin DELETE en ninguna tabla de interfaz.
===============================================================================
*/
