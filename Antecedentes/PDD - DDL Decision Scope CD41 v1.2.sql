-- PDD - Ratificación del scope CD41 - v1.2 - 2026-08-02
-- Aplicar después del DDL v1.0 y del addendum v1.1.

BEGIN;

ALTER TABLE pdd.distribution_scope_version
    ADD CONSTRAINT ck_distribution_scope_phase1_origin
    CHECK (origin_cd = 41);

ALTER TABLE pdd.distribution_scope_article
    ADD CONSTRAINT ck_distribution_scope_article_purchase
    CHECK (cd_active_for_purchase);

ALTER TABLE pdd.distribution_scope_pair
    ADD CONSTRAINT ck_distribution_scope_pair_phase1_cd41
    CHECK (
        origin_cd = 41
        AND route_code = '41CD'
        AND supply_mode = 0
        AND branch_habilitado
        AND branch_active_for_sale
        AND branch_active_on_mix
    );

COMMENT ON CONSTRAINT ck_distribution_scope_pair_phase1_cd41
    ON pdd.distribution_scope_pair IS
'Regla aprobada ADR-001: sólo pares abastecidos desde 41CD, modo 0 y plenamente habilitados.';

COMMIT;
