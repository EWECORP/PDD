-- Soporte persistente para el servicio; ver DISENO_PUBLICACION.md.
-- No publica datos ni cambia el lector PDD.
CREATE TABLE supply_planning.spl_stock_policy_domain (
 code text PRIMARY KEY,
 description text NOT NULL
);
INSERT INTO supply_planning.spl_stock_policy_domain VALUES
 ('DEFAULT','Politica de la instalacion actual; no representa aislamiento multiempresa');

ALTER TABLE supply_planning.spl_stock_policy_version
 ADD COLUMN domain_code text NOT NULL DEFAULT 'DEFAULT'
   REFERENCES supply_planning.spl_stock_policy_domain(code),
 ADD COLUMN revision bigint NOT NULL DEFAULT 1 CHECK (revision > 0),
 ADD COLUMN base_version_id uuid REFERENCES supply_planning.spl_stock_policy_version(id),
 ADD COLUMN updated_at timestamptz NOT NULL DEFAULT now(),
 ADD COLUMN updated_by text,
 ADD COLUMN published_at timestamptz,
 ADD COLUMN published_by text,
 ADD CONSTRAINT uq_stock_policy_version_domain UNIQUE(domain_code,id);

CREATE INDEX spl_stock_policy_version_schedule_idx
 ON supply_planning.spl_stock_policy_version(domain_code,valid_from,valid_to)
 WHERE status='PUBLISHED';

CREATE TABLE supply_planning.spl_stock_policy_validation (
 id uuid PRIMARY KEY,
 policy_version_id uuid NOT NULL REFERENCES supply_planning.spl_stock_policy_version(id),
 revision bigint NOT NULL CHECK(revision > 0),
 scope_reference text NOT NULL,
 business_date date NOT NULL,
 input_fingerprint text NOT NULL,
 status text NOT NULL CHECK(status IN ('RUNNING','PASSED','FAILED','ERROR')),
 pair_count bigint CHECK(pair_count >= 0),
 covered_count bigint CHECK(covered_count >= 0),
 blocking_count bigint CHECK(blocking_count >= 0),
 created_at timestamptz NOT NULL DEFAULT now(),
 completed_at timestamptz,
 created_by text NOT NULL,
 error_code text,
 CHECK(status <> 'PASSED' OR
   (pair_count IS NOT NULL AND covered_count IS NOT NULL AND blocking_count IS NOT NULL
    AND covered_count=pair_count AND blocking_count=0 AND completed_at IS NOT NULL))
);
CREATE INDEX spl_stock_policy_validation_version_idx
 ON supply_planning.spl_stock_policy_validation(policy_version_id,created_at DESC);

CREATE TABLE supply_planning.spl_stock_policy_validation_issue (
 id uuid PRIMARY KEY,
 validation_id uuid NOT NULL REFERENCES supply_planning.spl_stock_policy_validation(id),
 severity text NOT NULL CHECK(severity IN ('ERROR','WARNING','INFO')),
 code text NOT NULL,
 message text NOT NULL,
 context jsonb NOT NULL DEFAULT '{}'::jsonb
);
CREATE INDEX spl_stock_policy_validation_issue_parent_idx
 ON supply_planning.spl_stock_policy_validation_issue(validation_id,severity,id);

CREATE TABLE supply_planning.spl_stock_policy_audit (
 id uuid PRIMARY KEY,
 policy_version_id uuid NOT NULL REFERENCES supply_planning.spl_stock_policy_version(id),
 rule_id uuid,
 action text NOT NULL,
 actor text NOT NULL,
 occurred_at timestamptz NOT NULL DEFAULT now(),
 request_id text NOT NULL,
 reason text NOT NULL,
 before_value jsonb,
 after_value jsonb
);
-- rule_id no lleva FK: el historial sobrevive a la eliminacion de una regla de borrador.
CREATE INDEX spl_stock_policy_audit_version_idx
 ON supply_planning.spl_stock_policy_audit(policy_version_id,occurred_at,id);

CREATE TABLE supply_planning.spl_stock_policy_request (
 domain_code text NOT NULL REFERENCES supply_planning.spl_stock_policy_domain(code),
 actor text NOT NULL,
 operation text NOT NULL,
 idempotency_key text NOT NULL,
 request_hash text NOT NULL,
 response_status integer NOT NULL CHECK(response_status BETWEEN 200 AND 299),
 response_body jsonb NOT NULL,
 response_etag text,
 created_at timestamptz NOT NULL DEFAULT now(),
 PRIMARY KEY(domain_code,actor,operation,idempotency_key)
);
COMMENT ON TABLE supply_planning.spl_stock_policy_domain IS
 'Fila de bloqueo de publicacion por dominio. Backend debe bloquearla FOR UPDATE antes de validar/transicionar vigencias.';
COMMENT ON TABLE supply_planning.spl_stock_policy_request IS
 'Respuestas exitosas guardadas en la misma transaccion del comando. No persistir credenciales. Reintento con mismo hash devuelve misma respuesta.';
