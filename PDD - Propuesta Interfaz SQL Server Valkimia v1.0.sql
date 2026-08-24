/*
===============================================================================
PDD - Propuesta de interfaz SQL Server Valkimia v1.0

ESTADO: BORRADOR PARA REUNIÓN TÉCNICA. NO EJECUTAR SIN APROBACIÓN DE VALKIMIA.

Suposición técnica: Microsoft SQL Server. DIARCO-VKMSQL (SGM Actual), tal vez sobre
la base actual que se llama VALKIMIA.

Propiedad:
- Connexa escribe solamente CNX_PDD_ENVIO y CNX_PDD_ENVIO_LINEA.
- Valkimia escribe solamente CNX_PDD_EVENTO_ENVIO, CNX_PDD_EVENTO_LINEA,
  CNX_PDD_DESPACHO y CNX_PDD_DESPACHO_LINEA.
- Ningún proceso debe borrar ni sobrescribir filas del otro sistema.
===============================================================================
*/

CREATE TABLE dbo.CNX_PDD_ENVIO (
    CONNEXA_EXECUTION_ID        uniqueidentifier NOT NULL,
    CONNEXA_TRIP_ID             uniqueidentifier NOT NULL,
    SCHEMA_VERSION              varchar(20) NOT NULL,
    ORIGIN_CD                   int NOT NULL,
    PLANNED_DEPARTURE_AT        datetimeoffset(3) NULL,
    ROUTE_CODE                  varchar(80) NULL,
    VEHICLE_TYPE_CODE           varchar(40) NULL,
    VEHICLE_REFERENCE           varchar(80) NULL,
    CARRIER_REFERENCE           varchar(100) NULL,
    STOP_COUNT                  int NOT NULL,
    LINE_COUNT                  int NOT NULL,
    PAYLOAD_HASH                char(64) NOT NULL,
    REQUESTED_AT                datetimeoffset(3) NOT NULL,
    REQUESTED_BY                varchar(100) NOT NULL,

    CONSTRAINT PK_CNX_PDD_ENVIO
        PRIMARY KEY (CONNEXA_EXECUTION_ID),
    CONSTRAINT CK_CNX_PDD_ENVIO_ORIGIN
        CHECK (ORIGIN_CD = 41),
    CONSTRAINT CK_CNX_PDD_ENVIO_COUNTS
        CHECK (STOP_COUNT > 0 AND LINE_COUNT > 0)
);
GO

CREATE UNIQUE INDEX UX_CNX_PDD_ENVIO_TRIP_HASH
    ON dbo.CNX_PDD_ENVIO (CONNEXA_TRIP_ID, PAYLOAD_HASH);
GO

CREATE TABLE dbo.CNX_PDD_ENVIO_LINEA (
    CONNEXA_LINE_ID             uniqueidentifier NOT NULL,
    CONNEXA_EXECUTION_ID        uniqueidentifier NOT NULL,
    CONNEXA_TRIP_LINE_ID        uniqueidentifier NOT NULL,
    BACKLOG_LINE_UUID           uniqueidentifier NOT NULL,
    LINE_SEQUENCE              int NOT NULL,
    STOP_SEQUENCE              int NOT NULL,
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
    CONSTRAINT UQ_CNX_PDD_ENVIO_LINEA_TRIP_LINE
        UNIQUE (CONNEXA_TRIP_LINE_ID),
    CONSTRAINT CK_CNX_PDD_ENVIO_LINEA_SEQUENCE
        CHECK (LINE_SEQUENCE > 0 AND STOP_SEQUENCE > 0),
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
       (CONNEXA_EXECUTION_ID, STOP_SEQUENCE, LINE_SEQUENCE);
GO

/*
Acuse técnico/funcional append-only del lote. Permite confirmar recepción o
rechazar cabecera/esquema antes de procesar líneas.
*/
CREATE TABLE dbo.CNX_PDD_EVENTO_ENVIO (
    VALKIMIA_EXECUTION_EVENT_ID bigint IDENTITY(1,1) NOT NULL,
    VALKIMIA_EVENT_UUID         uniqueidentifier NOT NULL
        CONSTRAINT DF_CNX_PDD_EXEC_EVENT_UUID DEFAULT NEWID(),
    CONNEXA_EXECUTION_ID        uniqueidentifier NOT NULL,
    EXTERNAL_REFERENCE          varchar(160) NULL,
    EXTERNAL_STATUS_CODE        varchar(100) NOT NULL,
    EXTERNAL_STATUS_DESCRIPTION varchar(200) NULL,
    REASON_CODE                 varchar(80) NULL,
    REASON_DETAIL               varchar(500) NULL,
    EXTERNAL_OCCURRED_AT        datetimeoffset(3) NOT NULL,
    RECORDED_AT                 datetimeoffset(3) NOT NULL
        CONSTRAINT DF_CNX_PDD_EXEC_EVENT_RECORDED DEFAULT SYSDATETIMEOFFSET(),
    PAYLOAD_HASH                char(64) NOT NULL,

    CONSTRAINT PK_CNX_PDD_EVENTO_ENVIO
        PRIMARY KEY (VALKIMIA_EXECUTION_EVENT_ID),
    CONSTRAINT UQ_CNX_PDD_EVENTO_ENVIO_UUID
        UNIQUE (VALKIMIA_EVENT_UUID),
    CONSTRAINT FK_CNX_PDD_EVENTO_ENVIO_ENVIO
        FOREIGN KEY (CONNEXA_EXECUTION_ID)
        REFERENCES dbo.CNX_PDD_ENVIO (CONNEXA_EXECUTION_ID)
);
GO

CREATE INDEX IX_CNX_PDD_EVENTO_ENVIO_POLL
    ON dbo.CNX_PDD_EVENTO_ENVIO (VALKIMIA_EXECUTION_EVENT_ID)
    INCLUDE (
        CONNEXA_EXECUTION_ID,
        EXTERNAL_STATUS_CODE,
        EXTERNAL_OCCURRED_AT
    );
GO

/*
Evento append-only escrito por Valkimia. EXTERNAL_STATUS_CODE conserva el
estado nativo; Connexa realiza el mapping. Las cantidades acumuladas permiten
polling repetido e idempotente.
*/
CREATE TABLE dbo.CNX_PDD_EVENTO_LINEA (
    VALKIMIA_EVENT_ID           bigint IDENTITY(1,1) NOT NULL,
    VALKIMIA_EVENT_UUID         uniqueidentifier NOT NULL
        CONSTRAINT DF_CNX_PDD_EVENT_UUID DEFAULT NEWID(),
    CONNEXA_EXECUTION_ID        uniqueidentifier NOT NULL,
    CONNEXA_LINE_ID             uniqueidentifier NOT NULL,
    EXTERNAL_REFERENCE          varchar(160) NULL,
    EXTERNAL_LINE_REFERENCE     varchar(160) NULL,
    EXTERNAL_STATUS_CODE        varchar(100) NOT NULL,
    EXTERNAL_STATUS_DESCRIPTION varchar(200) NULL,
    QUANTITY_SEMANTICS          varchar(15) NOT NULL,
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
        CONSTRAINT DF_CNX_PDD_EVENT_RECORDED DEFAULT SYSDATETIMEOFFSET(),
    PAYLOAD_HASH                char(64) NOT NULL,

    CONSTRAINT PK_CNX_PDD_EVENTO_LINEA
        PRIMARY KEY (VALKIMIA_EVENT_ID),
    CONSTRAINT UQ_CNX_PDD_EVENTO_LINEA_UUID
        UNIQUE (VALKIMIA_EVENT_UUID),
    CONSTRAINT FK_CNX_PDD_EVENTO_LINEA_ENVIO
        FOREIGN KEY (CONNEXA_EXECUTION_ID)
        REFERENCES dbo.CNX_PDD_ENVIO (CONNEXA_EXECUTION_ID),
    CONSTRAINT FK_CNX_PDD_EVENTO_LINEA_LINEA
        FOREIGN KEY (CONNEXA_LINE_ID)
        REFERENCES dbo.CNX_PDD_ENVIO_LINEA (CONNEXA_LINE_ID),
    CONSTRAINT CK_CNX_PDD_EVENTO_SEMANTICS
        CHECK (QUANTITY_SEMANTICS IN ('CUMULATIVE', 'DELTA')),
    CONSTRAINT CK_CNX_PDD_EVENTO_QUANTITIES
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
        )
);
GO

CREATE INDEX IX_CNX_PDD_EVENTO_LINEA_POLL
    ON dbo.CNX_PDD_EVENTO_LINEA (VALKIMIA_EVENT_ID)
    INCLUDE (
        CONNEXA_EXECUTION_ID,
        CONNEXA_LINE_ID,
        EXTERNAL_STATUS_CODE,
        EXTERNAL_OCCURRED_AT
    );
GO

CREATE INDEX IX_CNX_PDD_EVENTO_LINEA_CONNEXA
    ON dbo.CNX_PDD_EVENTO_LINEA
       (CONNEXA_EXECUTION_ID, CONNEXA_LINE_ID, VALKIMIA_EVENT_ID);
GO

/* Cabecera real del despacho/embarque generado por Valkimia. */
CREATE TABLE dbo.CNX_PDD_DESPACHO (
    VALKIMIA_DISPATCH_ID        bigint IDENTITY(1,1) NOT NULL,
    VALKIMIA_DISPATCH_UUID      uniqueidentifier NOT NULL
        CONSTRAINT DF_CNX_PDD_DISPATCH_UUID DEFAULT NEWID(),
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
    UPDATED_AT                  datetimeoffset(3) NOT NULL,
    CHANGE_VERSION              rowversion NOT NULL,

    CONSTRAINT PK_CNX_PDD_DESPACHO
        PRIMARY KEY (VALKIMIA_DISPATCH_ID),
    CONSTRAINT UQ_CNX_PDD_DESPACHO_UUID
        UNIQUE (VALKIMIA_DISPATCH_UUID),
    CONSTRAINT FK_CNX_PDD_DESPACHO_ENVIO
        FOREIGN KEY (CONNEXA_EXECUTION_ID)
        REFERENCES dbo.CNX_PDD_ENVIO (CONNEXA_EXECUTION_ID),
    CONSTRAINT CK_CNX_PDD_DESPACHO_TOTALS
        CHECK (
            (ACTUAL_WEIGHT_KG IS NULL OR ACTUAL_WEIGHT_KG >= 0)
            AND (ACTUAL_VOLUME_M3 IS NULL OR ACTUAL_VOLUME_M3 >= 0)
            AND (ACTUAL_PALLETS IS NULL OR ACTUAL_PALLETS >= 0)
        )
);
GO

CREATE INDEX IX_CNX_PDD_DESPACHO_POLL
    ON dbo.CNX_PDD_DESPACHO (UPDATED_AT, VALKIMIA_DISPATCH_ID);
GO

/*
Cantidad efectiva de cada línea en cada despacho. La PK compuesta permite que
una línea sea despachada parcialmente en más de un documento.
*/
CREATE TABLE dbo.CNX_PDD_DESPACHO_LINEA (
    VALKIMIA_DISPATCH_ID        bigint NOT NULL,
    CONNEXA_LINE_ID             uniqueidentifier NOT NULL,
    DISPATCHED_QUANTITY         decimal(18,6) NOT NULL,
    EXTERNAL_LINE_REFERENCE     varchar(160) NULL,
    CREATED_AT                  datetimeoffset(3) NOT NULL
        CONSTRAINT DF_CNX_PDD_DISPATCH_LINE_CREATED DEFAULT SYSDATETIMEOFFSET(),

    CONSTRAINT PK_CNX_PDD_DESPACHO_LINEA
        PRIMARY KEY (VALKIMIA_DISPATCH_ID, CONNEXA_LINE_ID),
    CONSTRAINT FK_CNX_PDD_DESPACHO_LINEA_DISPATCH
        FOREIGN KEY (VALKIMIA_DISPATCH_ID)
        REFERENCES dbo.CNX_PDD_DESPACHO (VALKIMIA_DISPATCH_ID),
    CONSTRAINT FK_CNX_PDD_DESPACHO_LINEA_LINEA
        FOREIGN KEY (CONNEXA_LINE_ID)
        REFERENCES dbo.CNX_PDD_ENVIO_LINEA (CONNEXA_LINE_ID),
    CONSTRAINT CK_CNX_PDD_DESPACHO_LINEA_QUANTITY
        CHECK (DISPATCHED_QUANTITY > 0)
);
GO

/*
Consultas de polling propuestas:

-- Eventos posteriores al checkpoint durable de Connexa.
SELECT *
FROM dbo.CNX_PDD_EVENTO_LINEA
WHERE VALKIMIA_EVENT_ID > @LAST_EVENT_ID
ORDER BY VALKIMIA_EVENT_ID;

-- Acuses de lote posteriores a su propio checkpoint.
SELECT *
FROM dbo.CNX_PDD_EVENTO_ENVIO
WHERE VALKIMIA_EXECUTION_EVENT_ID > @LAST_EXECUTION_EVENT_ID
ORDER BY VALKIMIA_EXECUTION_EVENT_ID;

-- Despachos modificados, con solapamiento temporal.
SELECT *
FROM dbo.CNX_PDD_DESPACHO
WHERE UPDATED_AT >= @UPDATED_FROM
ORDER BY UPDATED_AT, VALKIMIA_DISPATCH_ID;
*/
