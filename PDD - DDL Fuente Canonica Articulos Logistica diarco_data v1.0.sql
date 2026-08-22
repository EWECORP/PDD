-- PDD - DDL Fuente Canonica Articulos Logistica diarco_data v1.0
-- PostgreSQL 14+
-- Base objetivo: diarco_data
--
-- Ejecucion manual sugerida:
-- psql "$PDD_SOURCE_DATABASE_URL" -v ON_ERROR_STOP=1 \
--   -f "PDD - DDL Fuente Canonica Articulos Logistica diarco_data v1.0.sql"
--
-- No se realiza bootstrap desde src.base_productos_vigentes. Antes deben
-- validarse la semantica de q_peso_unit_art y la fuente de dimensiones.

BEGIN;

DO $preconditions$
BEGIN
    IF current_database() <> 'diarco_data' THEN
        RAISE EXCEPTION
            'Base incorrecta: se esperaba diarco_data y se recibio %',
            current_database();
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM pg_namespace
        WHERE nspname = 'src'
    ) THEN
        RAISE EXCEPTION 'No existe el esquema src';
    END IF;

    IF to_regclass('src.base_articulos_logistica') IS NOT NULL THEN
        RAISE EXCEPTION
            'src.base_articulos_logistica ya existe; aplicar una migracion incremental';
    END IF;
END
$preconditions$;

CREATE TABLE src.base_articulos_logistica (
    articulo_logistica_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    -- Identidad y configuracion. c_proveedor NULL significa configuracion
    -- general del articulo. Puede haber configuraciones especificas por
    -- proveedor siempre que una sola quede marcada como default actual.
    c_articulo integer NOT NULL CHECK (c_articulo > 0),
    c_proveedor integer CHECK (c_proveedor > 0),
    c_configuracion_logistica varchar(60) NOT NULL DEFAULT 'DEFAULT'
        CHECK (
            c_configuracion_logistica = upper(c_configuracion_logistica)
            AND c_configuracion_logistica ~ '^[A-Z][A-Z0-9_-]*$'
        ),
    m_configuracion_default boolean NOT NULL DEFAULT true,
    m_activo boolean NOT NULL DEFAULT true,

    -- Unidad base y venta variable.
    c_unidad_base varchar(20) NOT NULL CHECK (
        c_unidad_base IN ('UNIT', 'KG', 'LITER', 'METER', 'M2', 'M3', 'OTHER')
    ),
    m_vende_por_peso boolean NOT NULL,
    c_gtin_unidad varchar(14) CHECK (
        c_gtin_unidad ~ '^[0-9]{8,14}$'
    ),

    -- Bulto/caja utilizado para compra, picking y transferencia.
    c_tipo_bulto varchar(30) CHECK (
        c_tipo_bulto IN (
            'CASE', 'PACK', 'BAG', 'TRAY', 'BOTTLE', 'CAN',
            'DRUM', 'BALE', 'UNIT', 'OTHER'
        )
    ),
    c_gtin_bulto varchar(14) CHECK (
        c_gtin_bulto ~ '^[0-9]{8,14}$'
    ),
    q_unidades_por_bulto numeric(18,6) CHECK (q_unidades_por_bulto > 0),

    -- Peso. Para capacidad de transporte se utiliza peso bruto; el peso neto
    -- se conserva para reconciliar con el maestro comercial.
    q_peso_neto_unitario_kg numeric(18,6)
        CHECK (q_peso_neto_unitario_kg > 0),
    q_peso_bruto_unitario_kg numeric(18,6)
        CHECK (q_peso_bruto_unitario_kg > 0),
    q_peso_bruto_bulto_kg numeric(18,6)
        CHECK (q_peso_bruto_bulto_kg > 0),

    -- Dimensiones exteriores del bulto en centimetros y volumen canonico en
    -- metros cubicos. Las tres dimensiones se informan juntas o todas NULL.
    q_largo_bulto_cm numeric(12,3) CHECK (q_largo_bulto_cm > 0),
    q_ancho_bulto_cm numeric(12,3) CHECK (q_ancho_bulto_cm > 0),
    q_alto_bulto_cm numeric(12,3) CHECK (q_alto_bulto_cm > 0),
    q_volumen_bulto_m3 numeric(18,9) CHECK (q_volumen_bulto_m3 > 0),
    c_metodo_volumen varchar(30) CHECK (
        c_metodo_volumen IN (
            'MEASURED_DIMENSIONS',
            'SOURCE_DIMENSIONS',
            'SOURCE_REPORTED',
            'SUPPLIER_REPORTED',
            'ESTIMATED'
        )
    ),

    -- Palletizacion. Cuando se informan capas y bultos/capa, el total debe ser
    -- su producto. Se admite informar solamente q_bultos_por_pallet si la
    -- fuente todavia no dispone del detalle de capas.
    q_bultos_por_capa integer CHECK (q_bultos_por_capa > 0),
    q_capas_por_pallet integer CHECK (q_capas_por_pallet > 0),
    q_bultos_por_pallet integer CHECK (q_bultos_por_pallet > 0),
    c_tipo_pallet varchar(30),
    q_largo_pallet_cm numeric(12,3) CHECK (q_largo_pallet_cm > 0),
    q_ancho_pallet_cm numeric(12,3) CHECK (q_ancho_pallet_cm > 0),
    q_alto_pallet_cargado_cm numeric(12,3)
        CHECK (q_alto_pallet_cargado_cm > 0),
    q_peso_bruto_pallet_kg numeric(18,6)
        CHECK (q_peso_bruto_pallet_kg > 0),

    -- Restricciones de manipulacion.
    m_apilable boolean,
    q_max_niveles_apilado smallint CHECK (q_max_niveles_apilado > 0),
    -- NULL significa que la restriccion todavia no fue relevada. No se asume
    -- silenciosamente que un producto es seguro/no fragil.
    m_fragil boolean,
    m_peligroso boolean,
    c_zona_temperatura varchar(20) CHECK (
        c_zona_temperatura IN (
            'AMBIENT', 'CHILLED', 'FROZEN', 'CONTROLLED', 'UNKNOWN'
        )
    ),
    q_temperatura_min_c numeric(6,2),
    q_temperatura_max_c numeric(6,2),
    c_orientacion varchar(20) CHECK (
        c_orientacion IN ('ANY', 'UPRIGHT', 'THIS_SIDE_UP', 'OTHER')
    ),
    observaciones_manipulacion text,

    -- Calidad por eje. SOURCE significa informado por la fuente pero aun no
    -- verificado fisicamente; VERIFIED es la maxima calidad.
    c_calidad_embalaje varchar(15) NOT NULL DEFAULT 'MISSING' CHECK (
        c_calidad_embalaje IN (
            'VERIFIED', 'SOURCE', 'ESTIMATED', 'MISSING', 'INVALID'
        )
    ),
    c_calidad_peso varchar(15) NOT NULL DEFAULT 'MISSING' CHECK (
        c_calidad_peso IN (
            'VERIFIED', 'SOURCE', 'ESTIMATED', 'MISSING', 'INVALID'
        )
    ),
    c_calidad_volumen varchar(15) NOT NULL DEFAULT 'MISSING' CHECK (
        c_calidad_volumen IN (
            'VERIFIED', 'SOURCE', 'ESTIMATED', 'MISSING', 'INVALID'
        )
    ),
    c_calidad_pallet varchar(15) NOT NULL DEFAULT 'MISSING' CHECK (
        c_calidad_pallet IN (
            'VERIFIED', 'SOURCE', 'ESTIMATED', 'MISSING', 'INVALID'
        )
    ),
    observaciones_calidad text,
    verificado_en timestamptz,
    verificado_por varchar(100),

    -- Vigencia SCD2. Para cambiar una configuracion se cierra la fila vigente
    -- y se inserta otra; no se reescribe la historia utilizada por PDD.
    f_vigencia_desde timestamptz NOT NULL,
    f_vigencia_hasta timestamptz,

    -- Linaje y auditoria de ingesta.
    fuente_origen varchar(60) NOT NULL,
    referencia_origen varchar(160),
    fecha_extraccion timestamptz NOT NULL,
    fecha_proceso timestamptz NOT NULL DEFAULT clock_timestamp(),
    cdc_lsn bytea,
    estado_sincronizacion smallint NOT NULL DEFAULT 1,
    input_checksum varchar(64) NOT NULL CHECK (
        input_checksum ~ '^[0-9a-f]{64}$'
    ),
    atributos_adicionales jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (
        jsonb_typeof(atributos_adicionales) = 'object'
    ),
    creado_en timestamptz NOT NULL DEFAULT clock_timestamp(),
    actualizado_en timestamptz NOT NULL DEFAULT clock_timestamp(),

    CONSTRAINT ck_base_articulos_logistica_vigencia CHECK (
        f_vigencia_hasta IS NULL OR f_vigencia_hasta > f_vigencia_desde
    ),
    CONSTRAINT ck_base_articulos_logistica_dimensiones_bulto CHECK (
        (
            q_largo_bulto_cm IS NULL
            AND q_ancho_bulto_cm IS NULL
            AND q_alto_bulto_cm IS NULL
        )
        OR
        (
            q_largo_bulto_cm IS NOT NULL
            AND q_ancho_bulto_cm IS NOT NULL
            AND q_alto_bulto_cm IS NOT NULL
        )
    ),
    CONSTRAINT ck_base_articulos_logistica_volumen_metodo CHECK (
        (q_volumen_bulto_m3 IS NULL AND c_metodo_volumen IS NULL)
        OR
        (q_volumen_bulto_m3 IS NOT NULL AND c_metodo_volumen IS NOT NULL)
    ),
    CONSTRAINT ck_base_articulos_logistica_pallet_capas CHECK (
        q_bultos_por_capa IS NULL
        OR q_capas_por_pallet IS NULL
        OR q_bultos_por_pallet IS NULL
        OR q_bultos_por_pallet = q_bultos_por_capa * q_capas_por_pallet
    ),
    CONSTRAINT ck_base_articulos_logistica_temperatura CHECK (
        q_temperatura_min_c IS NULL
        OR q_temperatura_max_c IS NULL
        OR q_temperatura_min_c <= q_temperatura_max_c
    ),
    CONSTRAINT ck_base_articulos_logistica_apilado CHECK (
        q_max_niveles_apilado IS NULL OR m_apilable IS TRUE
    ),
    CONSTRAINT ck_base_articulos_logistica_peso_bruto CHECK (
        q_peso_neto_unitario_kg IS NULL
        OR q_peso_bruto_unitario_kg IS NULL
        OR q_peso_bruto_unitario_kg >= q_peso_neto_unitario_kg
    )
);

-- Una configuracion proveedor/embalaje puede tener una sola fila abierta.
CREATE UNIQUE INDEX uq_base_articulos_logistica_config_actual
    ON src.base_articulos_logistica (
        c_articulo,
        coalesce(c_proveedor, -1),
        c_configuracion_logistica
    )
    WHERE f_vigencia_hasta IS NULL;

-- PDD debe encontrar una sola configuracion default actual por articulo.
CREATE UNIQUE INDEX uq_base_articulos_logistica_default_actual
    ON src.base_articulos_logistica (c_articulo)
    WHERE f_vigencia_hasta IS NULL
      AND m_activo
      AND m_configuracion_default;

CREATE INDEX ix_base_articulos_logistica_articulo_vigencia
    ON src.base_articulos_logistica
       (c_articulo, f_vigencia_desde DESC, f_vigencia_hasta);

CREATE INDEX ix_base_articulos_logistica_proveedor_actual
    ON src.base_articulos_logistica
       (c_proveedor, c_articulo)
    WHERE f_vigencia_hasta IS NULL AND m_activo;

CREATE INDEX ix_base_articulos_logistica_calidad_actual
    ON src.base_articulos_logistica (
        c_calidad_embalaje,
        c_calidad_peso,
        c_calidad_volumen,
        c_calidad_pallet
    )
    WHERE f_vigencia_hasta IS NULL AND m_activo;

CREATE INDEX ix_base_articulos_logistica_fecha_extraccion
    ON src.base_articulos_logistica (fecha_extraccion DESC);

-- Vista canonica que consumira el ETL. Mantiene nombres explicitos y calcula
-- factores derivados sin persistir resultados redundantes en la fuente.
CREATE VIEW src.v_base_articulos_logistica_actual AS
SELECT
    l.articulo_logistica_id,
    l.c_articulo,
    l.c_proveedor,
    l.c_configuracion_logistica,
    l.c_unidad_base,
    l.m_vende_por_peso,
    l.c_gtin_unidad,
    l.c_tipo_bulto,
    l.c_gtin_bulto,
    l.q_unidades_por_bulto,
    l.q_peso_neto_unitario_kg,
    l.q_peso_bruto_unitario_kg,
    l.q_peso_bruto_bulto_kg,
    l.q_largo_bulto_cm,
    l.q_ancho_bulto_cm,
    l.q_alto_bulto_cm,
    l.q_volumen_bulto_m3,
    CASE
        WHEN l.q_volumen_bulto_m3 IS NOT NULL
         AND l.q_unidades_por_bulto > 0
        THEN l.q_volumen_bulto_m3 / l.q_unidades_por_bulto
        ELSE NULL
    END::numeric(18,9) AS q_volumen_unitario_m3,
    l.c_metodo_volumen,
    l.q_bultos_por_capa,
    l.q_capas_por_pallet,
    l.q_bultos_por_pallet,
    CASE
        WHEN l.q_unidades_por_bulto IS NOT NULL
         AND l.q_bultos_por_pallet IS NOT NULL
        THEN l.q_unidades_por_bulto * l.q_bultos_por_pallet
        ELSE NULL
    END::numeric(18,6) AS q_unidades_por_pallet,
    l.c_tipo_pallet,
    l.q_largo_pallet_cm,
    l.q_ancho_pallet_cm,
    l.q_alto_pallet_cargado_cm,
    l.q_peso_bruto_pallet_kg,
    l.m_apilable,
    l.q_max_niveles_apilado,
    l.m_fragil,
    l.m_peligroso,
    l.c_zona_temperatura,
    l.q_temperatura_min_c,
    l.q_temperatura_max_c,
    l.c_orientacion,
    l.c_calidad_embalaje,
    l.c_calidad_peso,
    l.c_calidad_volumen,
    l.c_calidad_pallet,
    l.f_vigencia_desde,
    l.fuente_origen,
    l.referencia_origen,
    l.fecha_extraccion,
    l.fecha_proceso,
    l.input_checksum,
    l.atributos_adicionales,
    l.actualizado_en
FROM src.base_articulos_logistica AS l
WHERE l.f_vigencia_hasta IS NULL
  AND l.m_activo
  AND l.m_configuracion_default;

COMMENT ON TABLE src.base_articulos_logistica IS
    'Fuente canonica versionada de embalaje, peso, volumen, palletizacion y manipulacion por articulo.';

COMMENT ON COLUMN src.base_articulos_logistica.c_proveedor IS
    'Proveedor de la configuracion; NULL representa una configuracion general del articulo.';

COMMENT ON COLUMN src.base_articulos_logistica.q_unidades_por_bulto IS
    'Unidades base contenidas en el bulto logistico de compra/picking/transferencia.';

COMMENT ON COLUMN src.base_articulos_logistica.q_peso_bruto_bulto_kg IS
    'Peso del bulto incluyendo producto, envase y embalaje; preferido para capacidad de transporte.';

COMMENT ON COLUMN src.base_articulos_logistica.q_volumen_bulto_m3 IS
    'Volumen canonico exterior del bulto en metros cubicos; nunca completar faltantes con cero.';

COMMENT ON COLUMN src.base_articulos_logistica.q_bultos_por_pallet IS
    'Capacidad de pallet completo expresada en bultos logisticos.';

COMMENT ON COLUMN src.base_articulos_logistica.input_checksum IS
    'SHA-256 hexadecimal de los atributos canonicos para detectar cambios e idempotencia.';

COMMENT ON VIEW src.v_base_articulos_logistica_actual IS
    'Una configuracion logistica default, activa y vigente por articulo para consumo ETL PDD.';

COMMIT;
