\set ON_ERROR_STOP on

BEGIN;

DO $guard$
BEGIN
    IF current_database() <> 'diarco_data' THEN
        RAISE EXCEPTION
            'Migracion registro runtime PDD: base incorrecta (%). Se esperaba diarco_data.',
            current_database();
    END IF;
END
$guard$;

CREATE SCHEMA IF NOT EXISTS audit;

CREATE TABLE audit.pdd_runtime_binding (
    runtime_binding_uuid uuid PRIMARY KEY,
    environment varchar(10) NOT NULL CHECK (
        environment IN ('TEST', 'DESA', 'PROD')
    ),
    process_code varchar(80) NOT NULL,
    revision_no integer NOT NULL CHECK (revision_no > 0),
    scope_version_uuid uuid NOT NULL
        REFERENCES datamart.dm_pdd_scope_version(scope_version_uuid)
        ON DELETE RESTRICT,
    model_version_uuid uuid NOT NULL,
    configuration_version_uuid uuid NOT NULL,
    pipeline_revision varchar(100) NOT NULL,
    effective_business_date date NOT NULL,
    status varchar(20) NOT NULL CHECK (
        status IN ('ACTIVE', 'SUPERSEDED')
    ),
    activated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    activated_by varchar(100) NOT NULL,
    reason text NOT NULL,
    supersedes_runtime_binding_uuid uuid
        REFERENCES audit.pdd_runtime_binding(runtime_binding_uuid)
        ON DELETE RESTRICT,
    superseded_at timestamptz,
    superseded_by varchar(100),
    detail jsonb NOT NULL DEFAULT '{}'::jsonb,
    UNIQUE (environment, process_code, revision_no),
    CHECK (btrim(process_code) <> ''),
    CHECK (btrim(pipeline_revision) <> ''),
    CHECK (btrim(activated_by) <> ''),
    CHECK (btrim(reason) <> ''),
    CHECK (
        (status = 'ACTIVE' AND superseded_at IS NULL AND superseded_by IS NULL)
        OR
        (status = 'SUPERSEDED' AND superseded_at IS NOT NULL
            AND superseded_by IS NOT NULL)
    )
);

CREATE UNIQUE INDEX uq_pdd_runtime_binding_active
    ON audit.pdd_runtime_binding (environment, process_code)
    WHERE status = 'ACTIVE';

CREATE INDEX ix_pdd_runtime_binding_history
    ON audit.pdd_runtime_binding
    (environment, process_code, revision_no DESC);

COMMENT ON TABLE audit.pdd_runtime_binding IS
'Seleccion versionada y auditada de scope, modelo, configuracion y pipeline que consume cada proceso PDD por ambiente.';

COMMIT;
