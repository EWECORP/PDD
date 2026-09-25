\set ON_ERROR_STOP on

BEGIN;

DO $guard$
DECLARE
    v_scope record;
    v_articles bigint;
    v_pairs bigint;
    v_feature_through date;
BEGIN
    IF current_database() <> 'diarco_data' THEN
        RAISE EXCEPTION
            'Promocion scope PDD PROD: base incorrecta (%). Se esperaba diarco_data.',
            current_database();
    END IF;

    PERFORM pg_advisory_xact_lock(hashtext('PDD_SCOPE_PROD_PROMOTION'));

    SELECT *
      INTO v_scope
      FROM datamart.dm_pdd_scope_version
     WHERE scope_version_uuid = 'c533e7e7-3363-4dc3-8127-24f48fe33522'::uuid
     FOR UPDATE;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'No existe el scope PDD v6 esperado';
    END IF;

    IF v_scope.version_no <> 6
       OR v_scope.origin_cd <> 41
       OR v_scope.business_date <> DATE '2026-09-23'
       OR v_scope.article_count <> 2524
       OR v_scope.pair_count <> 46680
       OR btrim(v_scope.article_checksum) <>
          '2d03c32e69dc59a65e9bcf1e5ef3381eedcbfca29d21f72bad9340ca212bb50d'
       OR btrim(v_scope.pair_checksum) <>
          'e41d20c1cacd8802c263abb0be9c6fd1b4e7afddb7827237fcf58696238502e4'
       OR btrim(v_scope.scope_checksum) <>
          '47b2079ab205d1b689d00cfb12566321bbd474991193720e63c74a52bce5d1dc'
    THEN
        RAISE EXCEPTION 'La identidad o los conteos del scope v6 no coinciden';
    END IF;

    IF v_scope.status NOT IN ('DRAFT', 'APPROVED') THEN
        RAISE EXCEPTION 'Estado no promovible para scope v6: %', v_scope.status;
    END IF;

    SELECT count(*) INTO v_articles
      FROM datamart.dm_pdd_scope_article
     WHERE scope_version_uuid = v_scope.scope_version_uuid;

    SELECT count(*) INTO v_pairs
      FROM datamart.dm_pdd_scope_pair
     WHERE scope_version_uuid = v_scope.scope_version_uuid;

    SELECT max(sales_date) INTO v_feature_through
      FROM datamart.dm_pdd_venta_diaria
     WHERE scope_version_uuid = v_scope.scope_version_uuid;

    IF v_articles <> v_scope.article_count
       OR v_pairs <> v_scope.pair_count
       OR v_feature_through < DATE '2026-09-22'
    THEN
        RAISE EXCEPTION
            'Scope v6 incompleto: articulos=%/%, pares=%/%, features=%',
            v_articles, v_scope.article_count,
            v_pairs, v_scope.pair_count,
            v_feature_through;
    END IF;

    IF v_scope.status = 'APPROVED'
       AND NOT (
           coalesce(v_scope.detail, '{}'::jsonb) #>> '{approval,approved_by}'
           = 'eduardo.ettlin'
           AND coalesce(v_scope.detail, '{}'::jsonb) #>> '{approval,environment}'
           = 'PROD'
       )
    THEN
        RAISE EXCEPTION
            'El scope v6 ya figura APPROVED pero no posee la aprobación PROD esperada';
    END IF;

    IF v_scope.status = 'DRAFT' THEN
        UPDATE datamart.dm_pdd_scope_version
           SET status = 'APPROVED',
               detail = coalesce(detail, '{}'::jsonb) || jsonb_build_object(
                   'approval', jsonb_build_object(
                       'environment', 'PROD',
                       'approved_at', clock_timestamp(),
                       'approved_by', 'eduardo.ettlin',
                       'reason', 'Promocion inicial PDD 0.20.1 validada en TEST'
                   )
               )
         WHERE scope_version_uuid = v_scope.scope_version_uuid;
    END IF;
END
$guard$;

SELECT scope_version_uuid, version_no, status, business_date,
       article_count, pair_count, detail -> 'approval' AS approval
  FROM datamart.dm_pdd_scope_version
 WHERE scope_version_uuid = 'c533e7e7-3363-4dc3-8127-24f48fe33522'::uuid;

COMMIT;
