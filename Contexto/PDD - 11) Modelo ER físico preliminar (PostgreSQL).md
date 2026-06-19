A continuación se propone un **Modelo ER físico preliminar en PostgreSQL** para el nuevo esquema de transferencias, alineado con todo lo ya definido:

- **Need** como backlog consolidado
- **Plan** como corrida de planificación
- **Execution** como publicación/seguimiento hacia Valkimia
- **ExternalExecution** para convivencia transitoria con SGM
- **Event Log** para trazabilidad total
- **Tablas de configuración** para parametrizar reglas sin hardcodear

La propuesta está pensada para que pueda evolucionar luego a una implementación productiva sin tener que rehacer la base.

---

# 1. Criterios de diseño

## Objetivos del modelo

El modelo busca resolver cinco necesidades:

1. **No duplicar necesidades** por `CD + Sucursal + SKU + Bucket`
2. **Persistir backlog real**
3. **Separar claramente need / plan / execution**
4. **Permitir idempotencia e integración con Valkimia**
5. **Trazar absolutamente todos los cambios**

## Decisiones de diseño

Se propone:

- usar un esquema propio: `transfer`
- usar `uuid` como PK técnica
- usar `numeric(18,4)` para cantidades
- usar tablas de catálogo para estados si se desea máxima gobernanza, aunque para una primera versión también podrían usar `varchar + check`
- guardar snapshots de stock y score en las líneas de planificación
- registrar eventos en tabla append-only

Mi recomendación es comenzar con **catálogos simples + foreign keys**, porque les da gobernanza y evita textos inconsistentes.

---

# 2. Esquema lógico general

transfer.need  
    └── transfer.need_source  
    └── transfer.need_hold  
    └── transfer.need_event  
  
transfer.plan  
    └── transfer.plan_line  
  
transfer.execution  
    └── transfer.execution_line  
  
transfer.external_execution  
    └── transfer.external_execution_line  
    └── transfer.need_external_link  
  
transfer.event_log  
  
transfer.cfg_family_rule  
transfer.cfg_status_mapping

---

# 3. DDL propuesto — Esquema base

## 3.1 Crear esquema y extensiones

`CREATE SCHEMA IF NOT EXISTS transfer;`  
  
`CREATE EXTENSION IF NOT EXISTS pgcrypto;`  
`CREATE EXTENSION IF NOT EXISTS btree_gin;`

---

# 4. Catálogos de estados y tipos

Esto da consistencia y facilita BI, monitoreo y reglas.

## 4.1 Need status

`CREATE TABLE transfer.lk_need_status (`  
    `need_status_code varchar(40) PRIMARY KEY,`  
    `description      varchar(255) NOT NULL`  
`);`  
  
`INSERT INTO transfer.lk_need_status (need_status_code, description) VALUES`  
`('NEED_OPEN', 'Necesidad abierta'),`  
`('NEED_CONSOLIDATED', 'Necesidad consolidada'),`  
`('NEED_PARTIALLY_PLANNED', 'Necesidad parcialmente planificada'),`  
`('NEED_FULLY_PLANNED', 'Necesidad totalmente planificada'),`  
`('NEED_PARTIALLY_EXECUTING', 'Necesidad parcialmente en ejecucion'),`  
`('NEED_FULLY_EXECUTING', 'Necesidad totalmente en ejecucion'),`  
`('NEED_PARTIALLY_FULFILLED', 'Necesidad parcialmente cumplida'),`  
`('NEED_FULFILLED', 'Necesidad cumplida'),`  
`('NEED_CANCELLED', 'Necesidad cancelada'),`  
`('NEED_EXPIRED', 'Necesidad expirada');`

## 4.2 Plan line status

`CREATE TABLE transfer.lk_plan_line_status (`  
    `plan_line_status_code varchar(40) PRIMARY KEY,`  
    `description           varchar(255) NOT NULL`  
`);`  
  
`INSERT INTO transfer.lk_plan_line_status VALUES`  
`('PLAN_ELIGIBLE', 'Elegible para planificar'),`  
`('PLAN_NOT_ELIGIBLE_RULE', 'No elegible por regla'),`  
`('PLAN_NOT_ELIGIBLE_STOCK', 'No elegible por stock'),`  
`('PLAN_PARTIAL_STOCK', 'Planificacion parcial por stock'),`  
`('PLAN_PLANNED', 'Planificada'),`  
`('PLAN_PUBLISHING', 'En publicacion'),`  
`('PLAN_PUBLISHED', 'Publicada'),`  
`('PLAN_PUBLISH_FAILED', 'Fallo la publicacion'),`  
`('PLAN_SUPERSEDED', 'Reemplazada por replanificacion'),`  
`('PLAN_CANCELLED', 'Cancelada');`

## 4.3 Execution status

`CREATE TABLE transfer.lk_execution_status (`  
    `execution_status_code varchar(40) PRIMARY KEY,`  
    `description           varchar(255) NOT NULL`  
`);`  
  
`INSERT INTO transfer.lk_execution_status VALUES`  
`('EXEC_DRAFT', 'Borrador'),`  
`('EXEC_PUBLISHED', 'Publicada a Valkimia'),`  
`('EXEC_ACCEPTED', 'Aceptada'),`  
`('EXEC_REJECTED_STOCK', 'Rechazada por stock'),`  
`('EXEC_REJECTED_RULE', 'Rechazada por regla'),`  
`('EXEC_RESERVED_ACO', 'Reservada en ACO'),`  
`('EXEC_PICKING', 'En picking'),`  
`('EXEC_PACKED', 'Empacada'),`  
`('EXEC_SHIPPED', 'Despachada'),`  
`('EXEC_DELIVERED', 'Entregada'),`  
`('EXEC_CANCELLED', 'Cancelada'),`  
`('EXEC_FAILED', 'Fallida');`

## 4.4 Origen de need

`CREATE TABLE transfer.lk_need_origin (`  
    `need_origin_code varchar(30) PRIMARY KEY,`  
    `description      varchar(255) NOT NULL`  
`);`  
  
`INSERT INTO transfer.lk_need_origin VALUES`  
`('CONNEXA', 'Generada por Connexa'),`  
`('SGM', 'Generada por SGM'),`  
`('MANUAL', 'Generada manualmente'),`  
`('ADJUSTMENT', 'Ajuste operativo');`

## 4.5 Estrategia de asignación

`CREATE TABLE transfer.lk_allocation_strategy (`  
    `allocation_strategy_code varchar(30) PRIMARY KEY,`  
    `description              varchar(255) NOT NULL`  
`);`  
  
`INSERT INTO transfer.lk_allocation_strategy VALUES`  
`('PRIORITY', 'Asignacion por prioridad'),`  
`('FIFO', 'Primero en entrar primero en salir'),`  
`('FAIR_SHARE', 'Reparto equitativo'),`  
`('PROMO_BOOST', 'Priorizacion por promocion');`

---

# 5. Tabla principal de Need

## 5.1 transfer.need

`CREATE TABLE transfer.need (`  
    `need_id                      uuid PRIMARY KEY DEFAULT gen_random_uuid(),`  
  
    `cd_id                        integer NOT NULL,`  
    `sucursal_id                  integer NOT NULL,`  
    `sku_id                       bigint  NOT NULL,`  
    `need_bucket_date             date    NOT NULL,`  
  
    `need_status_code             varchar(40) NOT NULL`  
        `REFERENCES transfer.lk_need_status(need_status_code),`  
  
    `need_origin_code             varchar(30) NOT NULL`  
        `REFERENCES transfer.lk_need_origin(need_origin_code),`  
  
    `family_code                  varchar(30) NULL,`  
    `uom_code                     varchar(10) NOT NULL DEFAULT 'UNIT',`  
  
    `qty_need                     numeric(18,4) NOT NULL CHECK (qty_need >= 0),`  
    `qty_planned                  numeric(18,4) NOT NULL DEFAULT 0 CHECK (qty_planned >= 0),`  
    `qty_published                numeric(18,4) NOT NULL DEFAULT 0 CHECK (qty_published >= 0),`  
    `qty_fulfilled                numeric(18,4) NOT NULL DEFAULT 0 CHECK (qty_fulfilled >= 0),`  
  
    `manual_priority              integer NOT NULL DEFAULT 50 CHECK (manual_priority BETWEEN 0 AND 100),`  
    `priority_score               numeric(18,6) NULL,`  
  
    `sla_due_at                   timestamp NULL,`  
    `hold_reason_code             varchar(50) NULL,`  
    `hold_reason_detail           text NULL,`  
  
    `blocked_by_external_execution boolean NOT NULL DEFAULT false,`  
  
    `last_planned_at              timestamp NULL,`  
    `last_published_at            timestamp NULL,`  
    `last_execution_status        varchar(40) NULL,`  
  
    `next_replan_at               timestamp NULL,`  
    `replan_attempts_total        integer NOT NULL DEFAULT 0,`  
    `current_retry_streak         integer NOT NULL DEFAULT 0,`  
  
    `need_version                 integer NOT NULL DEFAULT 1,`  
  
    `created_at                   timestamp NOT NULL DEFAULT now(),`  
    `updated_at                   timestamp NOT NULL DEFAULT now(),`  
    `cancelled_at                 timestamp NULL,`  
    `expired_at                   timestamp NULL,`  
  
    `CONSTRAINT uq_need_functional`  
        `UNIQUE (cd_id, sucursal_id, sku_id, need_bucket_date),`  
  
    `CONSTRAINT ck_need_qty_consistency`  
        `CHECK (`  
            `qty_need >= qty_fulfilled`  
            `AND qty_need >= qty_planned`  
            `AND qty_need >= qty_published`  
        `)`  
`);`

## 5.2 Índices recomendados para need

`CREATE INDEX idx_need_status`  
    `ON transfer.need (need_status_code);`  
  
`CREATE INDEX idx_need_replan`  
    `ON transfer.need (cd_id, next_replan_at)`  
    `WHERE qty_need > qty_fulfilled`  
      `AND hold_reason_code IS NULL;`  
  
`CREATE INDEX idx_need_backlog`  
    `ON transfer.need (cd_id, sku_id, sucursal_id, need_bucket_date)`  
    `WHERE qty_need > qty_fulfilled;`  
  
`CREATE INDEX idx_need_family`  
    `ON transfer.need (family_code, need_status_code);`  
  
`CREATE INDEX idx_need_external_block`  
    `ON transfer.need (blocked_by_external_execution)`  
    `WHERE blocked_by_external_execution = true;`

---

# 6. Origen detallado de Need

Permite que una need consolidada tenga múltiples fuentes.

## 6.1 transfer.need_source

`CREATE TABLE transfer.need_source (`  
    `need_source_id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),`  
    `need_id                      uuid NOT NULL REFERENCES transfer.need(need_id),`  
  
    `source_system                varchar(30) NOT NULL,`  
    `source_reference_id          varchar(100) NOT NULL,`  
    `source_line_reference_id     varchar(100) NULL,`  
  
    `source_event_type            varchar(50) NULL,`  
    `source_payload               jsonb NULL,`  
  
    `qty_contributed              numeric(18,4) NOT NULL CHECK (qty_contributed >= 0),`  
  
    `created_at                   timestamp NOT NULL DEFAULT now(),`  
  
    `CONSTRAINT uq_need_source_ref`  
        `UNIQUE (source_system, source_reference_id, COALESCE(source_line_reference_id, ''))`  
`);`

## Índices

`CREATE INDEX idx_need_source_need`  
    `ON transfer.need_source (need_id);`  
  
`CREATE INDEX idx_need_source_system_ref`  
    `ON transfer.need_source (source_system, source_reference_id);`

---

# 7. Planificación

## 7.1 transfer.plan

`CREATE TABLE transfer.plan (`  
    `plan_id                      uuid PRIMARY KEY DEFAULT gen_random_uuid(),`  
  
    `cd_id                        integer NOT NULL,`  
    `plan_run_ts                  timestamp NOT NULL DEFAULT now(),`  
    `plan_status                  varchar(30) NOT NULL,`  
  
    `allocation_strategy_code     varchar(30) NOT NULL`  
        `REFERENCES transfer.lk_allocation_strategy(allocation_strategy_code),`  
  
    `stock_snapshot_ts            timestamp NULL,`  
    `stock_version                varchar(100) NULL,`  
  
    `planner_mode                 varchar(30) NOT NULL DEFAULT 'NORMAL',`  
    `created_by                   varchar(100) NOT NULL DEFAULT 'system',`  
  
    `total_lines                  integer NOT NULL DEFAULT 0,`  
    `total_skus                   integer NOT NULL DEFAULT 0,`  
    `total_qty_planned            numeric(18,4) NOT NULL DEFAULT 0,`  
  
    `created_at                   timestamp NOT NULL DEFAULT now(),`  
    `closed_at                    timestamp NULL`  
`);`

## Índices

`CREATE INDEX idx_plan_cd_run`  
    `ON transfer.plan (cd_id, plan_run_ts DESC);`

---

## 7.2 transfer.plan_line

`CREATE TABLE transfer.plan_line (`  
    `plan_line_id                 uuid PRIMARY KEY DEFAULT gen_random_uuid(),`  
    `plan_id                      uuid NOT NULL REFERENCES transfer.plan(plan_id),`  
    `need_id                      uuid NOT NULL REFERENCES transfer.need(need_id),`  
  
    `cd_id                        integer NOT NULL,`  
    `sucursal_id                  integer NOT NULL,`  
    `sku_id                       bigint  NOT NULL,`  
  
    `plan_line_status_code        varchar(40) NOT NULL`  
        `REFERENCES transfer.lk_plan_line_status(plan_line_status_code),`  
  
    `qty_backlog_at_plan          numeric(18,4) NOT NULL CHECK (qty_backlog_at_plan >= 0),`  
    `qty_planned                  numeric(18,4) NOT NULL CHECK (qty_planned >= 0),`  
  
    `stock_net_available_snapshot numeric(18,4) NULL,`  
    `stock_snapshot_ts            timestamp NULL,`  
    `stock_version                varchar(100) NULL,`  
  
    `allocation_strategy_code     varchar(30) NOT NULL`  
        `REFERENCES transfer.lk_allocation_strategy(allocation_strategy_code),`  
  
    `priority_score_snapshot      numeric(18,6) NULL,`  
    `manual_priority_snapshot     integer NULL,`  
    `reason_code                  varchar(50) NULL,`  
    `reason_detail                text NULL,`  
  
    `created_at                   timestamp NOT NULL DEFAULT now(),`  
    `published_at                 timestamp NULL,`  
    `superseded_at                timestamp NULL,`  
  
    `CONSTRAINT uq_plan_line_unique`  
        `UNIQUE (plan_id, sucursal_id, sku_id),`  
  
    `CONSTRAINT ck_plan_line_qty`  
        `CHECK (qty_planned <= qty_backlog_at_plan)`  
`);`

## Índices

`CREATE INDEX idx_plan_line_need`  
    `ON transfer.plan_line (need_id);`  
  
`CREATE INDEX idx_plan_line_status`  
    `ON transfer.plan_line (plan_line_status_code);`  
  
`CREATE INDEX idx_plan_line_sku_sucursal`  
    `ON transfer.plan_line (cd_id, sku_id, sucursal_id);`

---

# 8. Ejecución hacia Valkimia

## 8.1 transfer.execution

`CREATE TABLE transfer.execution (`  
    `execution_id                 uuid PRIMARY KEY DEFAULT gen_random_uuid(),`  
    `plan_id                      uuid NULL REFERENCES transfer.plan(plan_id),`  
  
    `connexa_execution_id         uuid NOT NULL UNIQUE,`  
  
    `cd_id                        integer NOT NULL,`  
    `sucursal_id                  integer NOT NULL,`  
  
    `execution_status_code        varchar(40) NOT NULL`  
        `REFERENCES transfer.lk_execution_status(execution_status_code),`  
  
    `valkimia_transfer_id         varchar(100) NULL UNIQUE,`  
    `source_system                varchar(30) NOT NULL DEFAULT 'CONNEXA',`  
  
    `priority                     integer NULL,`  
    `requested_ship_from_ts       timestamp NULL,`  
    `requested_ship_to_ts         timestamp NULL,`  
  
    `published_at                 timestamp NULL,`  
    `accepted_at                  timestamp NULL,`  
    `reserved_aco_at              timestamp NULL,`  
    `picking_started_at           timestamp NULL,`  
    `shipped_at                   timestamp NULL,`  
    `delivered_at                 timestamp NULL,`  
    `cancelled_at                 timestamp NULL,`  
    `failed_at                    timestamp NULL,`  
  
    `last_update_at               timestamp NOT NULL DEFAULT now(),`  
    `last_reason_code             varchar(50) NULL,`  
    `last_reason_detail           text NULL,`  
  
    `idempotency_hash             varchar(200) NULL,`  
  
    `created_at                   timestamp NOT NULL DEFAULT now()`  
`);`

## Índices

`CREATE INDEX idx_execution_status`  
    `ON transfer.execution (execution_status_code);`  
  
`CREATE INDEX idx_execution_cd_sucursal`  
    `ON transfer.execution (cd_id, sucursal_id, created_at DESC);`  
  
`CREATE INDEX idx_execution_valkimia`  
    `ON transfer.execution (valkimia_transfer_id);`

---

## 8.2 transfer.execution_line

`CREATE TABLE transfer.execution_line (`  
    `execution_line_id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),`  
    `execution_id                 uuid NOT NULL REFERENCES transfer.execution(execution_id),`  
    `plan_line_id                 uuid NULL REFERENCES transfer.plan_line(plan_line_id),`  
    `need_id                      uuid NOT NULL REFERENCES transfer.need(need_id),`  
  
    `connexa_line_id              uuid NOT NULL UNIQUE,`  
    `valkimia_line_id             varchar(100) NULL UNIQUE,`  
  
    `sku_id                       bigint NOT NULL,`  
    `uom_code                     varchar(10) NOT NULL,`  
  
    `qty_requested                numeric(18,4) NOT NULL CHECK (qty_requested >= 0),`  
    `qty_accepted                 numeric(18,4) NOT NULL DEFAULT 0 CHECK (qty_accepted >= 0),`  
    `qty_prepared                 numeric(18,4) NOT NULL DEFAULT 0 CHECK (qty_prepared >= 0),`  
    `qty_shipped                  numeric(18,4) NOT NULL DEFAULT 0 CHECK (qty_shipped >= 0),`  
    `qty_delivered                numeric(18,4) NOT NULL DEFAULT 0 CHECK (qty_delivered >= 0),`  
  
    `execution_status_code        varchar(40) NOT NULL`  
        `REFERENCES transfer.lk_execution_status(execution_status_code),`  
  
    `reject_reason_code           varchar(50) NULL,`  
    `reject_reason_detail         text NULL,`  
  
    `retryable                    boolean NOT NULL DEFAULT true,`  
  
    `created_at                   timestamp NOT NULL DEFAULT now(),`  
    `last_event_ts                timestamp NULL,`  
    `updated_at                   timestamp NOT NULL DEFAULT now(),`  
  
    `CONSTRAINT uq_execution_line_business`  
        `UNIQUE (execution_id, sku_id)`  
`);`

## Índices

`CREATE INDEX idx_execution_line_need`  
    `ON transfer.execution_line (need_id);`  
  
`CREATE INDEX idx_execution_line_status`  
    `ON transfer.execution_line (execution_status_code);`  
  
`CREATE INDEX idx_execution_line_sku`  
    `ON transfer.execution_line (sku_id);`

---

# 9. Ejecuciones externas para convivencia con SGM

## 9.1 transfer.external_execution

`CREATE TABLE transfer.external_execution (`  
    `external_execution_id        uuid PRIMARY KEY DEFAULT gen_random_uuid(),`  
  
    `source_system                varchar(30) NOT NULL,`  
    `external_reference_id        varchar(100) NULL,`  
    `valkimia_transfer_id         varchar(100) NOT NULL UNIQUE,`  
  
    `cd_id                        integer NOT NULL,`  
    `sucursal_id                  integer NOT NULL,`  
  
    `execution_status_code        varchar(40) NOT NULL`  
        `REFERENCES transfer.lk_execution_status(execution_status_code),`  
  
    `detected_at_ts               timestamp NOT NULL DEFAULT now(),`  
    `created_at_ts                timestamp NULL,`  
    `last_update_ts               timestamp NULL,`  
  
    `is_active                    boolean NOT NULL DEFAULT true,`  
    `notes                        text NULL,`  
  
    `created_at                   timestamp NOT NULL DEFAULT now()`  
`);`

## 9.2 transfer.external_execution_line

`CREATE TABLE transfer.external_execution_line (`  
    `external_execution_line_id   uuid PRIMARY KEY DEFAULT gen_random_uuid(),`  
    `external_execution_id        uuid NOT NULL REFERENCES transfer.external_execution(external_execution_id),`  
  
    `sku_id                       bigint NOT NULL,`  
    `uom_code                     varchar(10) NOT NULL DEFAULT 'UNIT',`  
  
    `qty_requested                numeric(18,4) NOT NULL DEFAULT 0,`  
    `qty_prepared                 numeric(18,4) NOT NULL DEFAULT 0,`  
    `qty_shipped                  numeric(18,4) NOT NULL DEFAULT 0,`  
    `qty_delivered                numeric(18,4) NOT NULL DEFAULT 0,`  
  
    `execution_status_code        varchar(40) NOT NULL`  
        `REFERENCES transfer.lk_execution_status(execution_status_code),`  
  
    `created_at                   timestamp NOT NULL DEFAULT now(),`  
    `updated_at                   timestamp NOT NULL DEFAULT now(),`  
  
    `CONSTRAINT uq_external_exec_line`  
        `UNIQUE (external_execution_id, sku_id)`  
`);`

## 9.3 Vínculo Need ↔ ExternalExecution

`CREATE TABLE transfer.need_external_link (`  
    `need_external_link_id        uuid PRIMARY KEY DEFAULT gen_random_uuid(),`  
  
    `need_id                      uuid NOT NULL REFERENCES transfer.need(need_id),`  
    `external_execution_line_id   uuid NOT NULL REFERENCES transfer.external_execution_line(external_execution_line_id),`  
  
    `link_status                  varchar(30) NOT NULL DEFAULT 'LINKED',`  
    `qty_linked                   numeric(18,4) NULL,`  
  
    `created_at                   timestamp NOT NULL DEFAULT now(),`  
  
    `CONSTRAINT uq_need_external_link`  
        `UNIQUE (need_id, external_execution_line_id)`  
`);`

## Índices

`CREATE INDEX idx_external_execution_active`  
    `ON transfer.external_execution (cd_id, is_active, execution_status_code);`  
  
`CREATE INDEX idx_external_execution_line_sku`  
    `ON transfer.external_execution_line (sku_id);`  
  
`CREATE INDEX idx_need_external_link_need`  
    `ON transfer.need_external_link (need_id);`

---

# 10. Bitácora universal de eventos

Esta tabla es fundamental.  
Mi recomendación es que sea **append-only**.

## 10.1 transfer.event_log

`CREATE TABLE transfer.event_log (`  
    `event_id                     uuid PRIMARY KEY DEFAULT gen_random_uuid(),`  
  
    `entity_type                  varchar(30) NOT NULL,`  
    `entity_id                    uuid NOT NULL,`  
  
    `parent_entity_type           varchar(30) NULL,`  
    `parent_entity_id             uuid NULL,`  
  
    `event_type                   varchar(60) NOT NULL,`  
    `old_status_code              varchar(40) NULL,`  
    `new_status_code              varchar(40) NULL,`  
  
    `source_system                varchar(30) NOT NULL,`  
    `source_reference_id          varchar(100) NULL,`  
  
    `reason_code                  varchar(50) NULL,`  
    `reason_detail                text NULL,`  
  
    `event_payload                jsonb NULL,`  
  
    `event_ts                     timestamp NOT NULL DEFAULT now(),`  
    `created_by                   varchar(100) NOT NULL DEFAULT 'system'`  
`);`

## Índices

`CREATE INDEX idx_event_log_entity`  
    `ON transfer.event_log (entity_type, entity_id, event_ts DESC);`  
  
`CREATE INDEX idx_event_log_parent`  
    `ON transfer.event_log (parent_entity_type, parent_entity_id, event_ts DESC);`  
  
`CREATE INDEX idx_event_log_type_ts`  
    `ON transfer.event_log (event_type, event_ts DESC);`  
  
`CREATE INDEX idx_event_log_payload_gin`  
    `ON transfer.event_log`  
    `USING gin (event_payload);`

---

# 11. Configuración y parametría

## 11.1 Reglas por familia

`CREATE TABLE transfer.cfg_family_rule (`  
    `family_code                  varchar(30) PRIMARY KEY,`  
  
    `bucket_mode                  varchar(20) NOT NULL,`  
    `allocation_strategy_code     varchar(30) NOT NULL`  
        `REFERENCES transfer.lk_allocation_strategy(allocation_strategy_code),`  
  
    `sla_window_hours             integer NOT NULL,`  
    `age_max_hours                integer NOT NULL,`  
  
    `backoff_base_minutes         integer NOT NULL,`  
    `backoff_max_minutes          integer NOT NULL,`  
  
    `threshold_low_stock          numeric(18,4) NOT NULL,`  
    `max_replan_attempts          integer NOT NULL DEFAULT 999,`  
  
    `weight_manual_priority       numeric(8,4) NOT NULL,`  
    `weight_sla_urgency           numeric(8,4) NOT NULL,`  
    `weight_break_risk            numeric(8,4) NOT NULL,`  
    `weight_sales_rate            numeric(8,4) NOT NULL,`  
    `weight_promo_boost           numeric(8,4) NOT NULL,`  
    `weight_backlog_age           numeric(8,4) NOT NULL,`  
    `weight_retry_penalty         numeric(8,4) NOT NULL,`  
  
    `created_at                   timestamp NOT NULL DEFAULT now(),`  
    `updated_at                   timestamp NOT NULL DEFAULT now()`  
`);`

## 11.2 Mapeo de estados Valkimia → internos

`CREATE TABLE transfer.cfg_status_mapping (`  
    `status_mapping_id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),`  
  
    `source_system                varchar(30) NOT NULL,`  
    `source_status_code           varchar(50) NOT NULL,`  
    `internal_status_code         varchar(40) NOT NULL,`  
  
    `entity_type                  varchar(30) NOT NULL,`  
    `is_active                    boolean NOT NULL DEFAULT true,`  
  
    `created_at                   timestamp NOT NULL DEFAULT now(),`  
  
    `CONSTRAINT uq_status_mapping`  
        `UNIQUE (source_system, source_status_code, entity_type)`  
`);`

---

# 12. Vistas útiles para operación

## 12.1 Backlog vivo

`CREATE OR REPLACE VIEW transfer.v_backlog_open AS`  
`SELECT`  
    `n.need_id,`  
    `n.cd_id,`  
    `n.sucursal_id,`  
    `n.sku_id,`  
    `n.need_bucket_date,`  
    `n.family_code,`  
    `n.need_status_code,`  
    `n.qty_need,`  
    `n.qty_fulfilled,`  
    `(n.qty_need - n.qty_fulfilled) AS backlog_qty,`  
    `n.priority_score,`  
    `n.manual_priority,`  
    `n.next_replan_at,`  
    `n.blocked_by_external_execution,`  
    `n.created_at,`  
    `n.updated_at`  
`FROM transfer.need n`  
`WHERE n.qty_need > n.qty_fulfilled`  
  `AND n.need_status_code NOT IN ('NEED_CANCELLED', 'NEED_EXPIRED', 'NEED_FULFILLED');`

## 12.2 Ejecuciones activas

`CREATE OR REPLACE VIEW transfer.v_execution_active AS`  
`SELECT`  
    `e.execution_id,`  
    `e.connexa_execution_id,`  
    `e.valkimia_transfer_id,`  
    `e.cd_id,`  
    `e.sucursal_id,`  
    `e.execution_status_code,`  
    `e.created_at,`  
    `e.last_update_at`  
`FROM transfer.execution e`  
`WHERE e.execution_status_code IN (`  
    `'EXEC_ACCEPTED',`  
    `'EXEC_RESERVED_ACO',`  
    `'EXEC_PICKING',`  
    `'EXEC_PACKED',`  
    `'EXEC_SHIPPED'`  
`);`

---

# 13. Trigger recomendado para updated_at

## 13.1 Función

`CREATE OR REPLACE FUNCTION transfer.fn_set_updated_at()`  
`RETURNS trigger`  
`LANGUAGE plpgsql`  
`AS $$`  
`BEGIN`  
    `NEW.updated_at := now();`  
    `RETURN NEW;`  
`END;`  
`$$;`

## 13.2 Triggers

`CREATE TRIGGER trg_need_updated_at`  
`BEFORE UPDATE ON transfer.need`  
`FOR EACH ROW`  
`EXECUTE FUNCTION transfer.fn_set_updated_at();`  
  
`CREATE TRIGGER trg_execution_line_updated_at`  
`BEFORE UPDATE ON transfer.execution_line`  
`FOR EACH ROW`  
`EXECUTE FUNCTION transfer.fn_set_updated_at();`  
  
`CREATE TRIGGER trg_external_execution_line_updated_at`  
`BEFORE UPDATE ON transfer.external_execution_line`  
`FOR EACH ROW`  
`EXECUTE FUNCTION transfer.fn_set_updated_at();`

---

# 14. Relaciones principales del ER

## Relación de negocio

### Núcleo

- `need` 1 — N `need_source`
- `plan` 1 — N `plan_line`
- `need` 1 — N `plan_line`
- `execution` 1 — N `execution_line`
- `plan_line` 1 — 0..1 `execution_line`
- `need` 1 — N `execution_line`

### Convivencia

- `external_execution` 1 — N `external_execution_line`
- `need` N — N `external_execution_line` vía `need_external_link`

### Auditoría

- cualquier entidad → N `event_log`

---

# 15. Recomendaciones de implementación

## Versión mínima viable

Si quisieran empezar más liviano, podrían crear primero:

- `transfer.need`
- `transfer.plan`
- `transfer.plan_line`
- `transfer.execution`
- `transfer.execution_line`
- `transfer.event_log`

y dejar para fase 2:

- `external_execution`
- `need_source`
- `cfg_status_mapping`
- `cfg_family_rule`

## Mi opinión técnica

Yo no dejaría afuera desde el inicio:

- `event_log`
- `need_source`
- `external_execution`

Porque justamente el problema actual está en la **multiplicidad de orígenes** y en la **falta de trazabilidad**.  
Si eso no queda modelado desde el principio, luego reaparece el mismo desorden.

---
### SCRIPT DE GENERACIÓN

![[Crear_Entidades.sql]]

### Observaciones importantes

1. El script está preparado para ejecutarse varias veces en forma razonablemente segura:
    - usa `IF NOT EXISTS`
    - usa `ON CONFLICT DO NOTHING`
    - recrea triggers con `DROP TRIGGER IF EXISTS`
2. Hay dos campos de “fecha de modificación” con distinta lógica:
    - `updated_at`
    - `last_update_at` en `transfer.execution`
3. No incluí `FK` a tablas maestras de artículos, sucursales o CDs porque eso depende de cómo tengan hoy modelado `src.m_3_articulos`, `src.m_91_sucursales`, depósitos/CDs, etc.  
    Mi recomendación es dejar esas claves desacopladas en esta primera versión, y agregar las validaciones por proceso de negocio o en una segunda etapa.
4. `plan_status`, `link_status`, `entity_type`, `event_type` quedaron como `varchar` libre.  
    Esto es deliberado: da más flexibilidad en una primera implementación. Si lo prefieren totalmente gobernado, se puede ampliar con catálogos adicionales.
5. El índice de `need_source` con `COALESCE(...)` está creado como índice único, no como constraint, porque PostgreSQL no permite directamente esa expresión dentro de un `UNIQUE CONSTRAINT` estándar.

Si desean, el siguiente paso más útil sería entregarles el **script de procedimientos base en PL/pgSQL**, por ejemplo:

- `sp_merge_need`
- `sp_create_plan_for_cd`
- `sp_register_execution_response`
- `sp_requeue_rejected_lines`

Eso ya dejaría la capa de negocio bastante encaminada.