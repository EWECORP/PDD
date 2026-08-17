"""Obtiene la fotografia reproducible de scope y hashes de implementacion."""

from __future__ import annotations

import hashlib
import argparse
import json
from pathlib import Path

from sqlalchemy import text

from pdd_backend.config import Settings
from pdd_backend.db import build_engine
from pdd_backend.scope_rules import (
    load_scope_exclusion_policy,
    scope_exclusion_policy_json,
)


SCOPE_SQL = """
WITH excluded_categories AS (
    SELECT
        (rule ->> 'c_rubro')::integer AS c_rubro,
        (rule ->> 'c_subrubro_1')::integer AS c_subrubro_1
    FROM jsonb_array_elements(
        CAST(:exclusion_policy_json AS jsonb) -> 'rules'
    ) AS rules(rule)
),
source_excluded_branches AS (
    SELECT DISTINCT c_sucu_empr::integer AS destination_branch
    FROM src.sucursales_excluidas
    WHERE c_sucu_empr IS NOT NULL
),
cd_articles AS (
    SELECT DISTINCT ON (c_articulo)
        bpv.c_articulo,
        bpv.c_proveedor_primario,
        bpv.active_for_purchase,
        bpv.habilitado,
        bpv.active_for_sale,
        bpv.active_on_mix,
        bpv.fecha_extraccion
    FROM src.base_productos_vigentes AS bpv
    WHERE bpv.c_sucu_empr = 41
      AND bpv.active_for_purchase = 1
      AND NOT EXISTS (
          SELECT 1
          FROM src.m_3_articulos AS art
          INNER JOIN excluded_categories AS excluded
              ON excluded.c_rubro = art.c_rubro::integer
             AND excluded.c_subrubro_1 = art.c_subrubro_1::integer
          WHERE art.c_articulo::integer = bpv.c_articulo::integer
      )
    ORDER BY bpv.c_articulo, bpv.fecha_extraccion DESC NULLS LAST
),
candidate_pairs AS (
    SELECT DISTINCT ON (b.c_sucu_empr, b.c_articulo)
        b.c_sucu_empr AS destination_branch,
        b.c_articulo AS codigo_articulo,
        coalesce(b.c_proveedor_primario, a.c_proveedor_primario)
            AS c_proveedor_primario,
        b.cod_cd,
        b.abastecimiento,
        b.habilitado,
        b.active_for_sale,
        b.active_on_mix,
        b.fecha_extraccion
    FROM src.base_productos_vigentes AS b
    INNER JOIN cd_articles AS a USING (c_articulo)
    WHERE b.cod_cd = '41CD'
      AND b.abastecimiento = 0
      AND b.habilitado = 1
      AND b.active_for_sale = 1
      AND b.active_on_mix = 1
      AND b.c_sucu_empr <> 41
    ORDER BY b.c_sucu_empr, b.c_articulo, b.fecha_extraccion DESC NULLS LAST
),
excluded_branches AS (
    SELECT DISTINCT candidate.destination_branch::integer AS destination_branch
    FROM candidate_pairs AS candidate
    INNER JOIN source_excluded_branches AS excluded
      ON excluded.destination_branch = candidate.destination_branch::integer
),
pairs AS (
    SELECT candidate.*
    FROM candidate_pairs AS candidate
    WHERE NOT EXISTS (
        SELECT 1
        FROM excluded_branches AS excluded
        WHERE excluded.destination_branch = candidate.destination_branch::integer
    )
),
article_manifest AS (
    SELECT
        count(*)::integer AS article_count,
        max(fecha_extraccion) AS source_as_of_ts,
        encode(
            sha256(
                convert_to(
                    string_agg(
                        concat_ws('|',
                            c_articulo::text,
                            coalesce(c_proveedor_primario::text, ''),
                            active_for_purchase::text,
                            coalesce(habilitado::text, ''),
                            coalesce(active_for_sale::text, ''),
                            coalesce(active_on_mix::text, '')
                        ),
                        E'\\n' ORDER BY c_articulo
                    ),
                    'UTF8'
                )
            ),
            'hex'
        ) AS article_checksum
    FROM cd_articles
),
pair_manifest AS (
    SELECT
        count(*)::integer AS pair_count,
        count(DISTINCT destination_branch)::integer AS destination_count,
        count(DISTINCT codigo_articulo)::integer AS routed_article_count,
        max(fecha_extraccion) AS source_as_of_ts,
        encode(
            sha256(
                convert_to(
                    string_agg(
                        concat_ws('|',
                            destination_branch::text,
                            codigo_articulo::text,
                            coalesce(c_proveedor_primario::text, ''),
                            cod_cd,
                            abastecimiento::text,
                            habilitado::text,
                            active_for_sale::text,
                            active_on_mix::text
                        ),
                        E'\\n' ORDER BY destination_branch, codigo_articulo
                    ),
                    'UTF8'
                )
            ),
            'hex'
        ) AS pair_checksum
    FROM pairs
),
branch_exclusion_manifest AS (
    SELECT
        count(*)::integer AS excluded_branch_count,
        (
            SELECT count(*)::integer
            FROM candidate_pairs AS candidate
            INNER JOIN excluded_branches AS excluded
              ON excluded.destination_branch = candidate.destination_branch::integer
        ) AS excluded_pair_count,
        coalesce(
            jsonb_agg(destination_branch ORDER BY destination_branch),
            '[]'::jsonb
        ) AS excluded_branches
    FROM excluded_branches
)
SELECT
    a.article_count,
    p.pair_count,
    p.destination_count,
    p.routed_article_count,
    greatest(a.source_as_of_ts, p.source_as_of_ts) AS source_as_of_ts,
    a.article_checksum,
    p.pair_checksum,
    b.excluded_branch_count,
    b.excluded_pair_count,
    b.excluded_branches,
    encode(
        sha256(
            convert_to(
                'articles:' || a.article_checksum || '|pairs:' || p.pair_checksum,
                'UTF8'
            )
        ),
        'hex'
    ) AS scope_checksum
FROM article_manifest AS a
CROSS JOIN pair_manifest AS p
CROSS JOIN branch_exclusion_manifest AS b
"""


IMPLEMENTATION_FILES = (
    "pyproject.toml",
    "pdd_backend/__init__.py",
    "pdd_backend/cli.py",
    "pdd_backend/config.py",
    "pdd_backend/db.py",
    "pdd_backend/model_registry.py",
    "pdd_backend/operational_registry.py",
    "pdd_backend/operational_contract.py",
    "pdd_backend/manifests/model_versions.json",
    "pdd_backend/manifests/operational_configurations.json",
    "pdd_backend/flows/analytical.py",
    "pdd_backend/flows/backtest.py",
    "pdd_backend/flows/publisher.py",
    "pdd_backend/flows/operational_inputs.py",
    "pdd_backend/backtest_metrics.py",
    "pdd_backend/jobs/common.py",
    "pdd_backend/jobs/stock_daily.py",
    "pdd_backend/jobs/sales_daily.py",
    "pdd_backend/jobs/scope_snapshot.py",
    "pdd_backend/scope_rules.py",
    "pdd_backend/rules/scope_exclusions.json",
    "pdd_backend/jobs/pdvb.py",
    "pdd_backend/jobs/backtest.py",
    "pdd_backend/jobs/publisher.py",
    "pdd_backend/jobs/operational_inputs.py",
    "pdd_backend/jobs/daily_decas.py",
    "pdd_backend/jobs/backlog.py",
    "pdd_backend/api/__init__.py",
    "pdd_backend/api/app.py",
    "pdd_backend/api/cursor.py",
    "pdd_backend/api/errors.py",
    "pdd_backend/api/main.py",
    "pdd_backend/api/models.py",
    "pdd_backend/api/repository.py",
    "pdd_backend/api/security.py",
    "contracts/pdd-frontend-openapi-v1.yaml",
    "pdd_backend/windows.py",
    "pdd_backend/sql/scope/prepare_scope_snapshot.sql",
    "pdd_backend/sql/scope/insert_scope_version.sql",
    "pdd_backend/sql/scope/insert_scope_articles.sql",
    "pdd_backend/sql/scope/insert_scope_pairs.sql",
    "pdd_backend/sql/stock/upsert_stock_daily.sql",
    "pdd_backend/sql/sales/upsert_sales_daily.sql",
    "pdd_backend/sql/pdvb/insert_pdvb_detail.sql",
    "pdd_backend/sql/backtest/insert_backtest_detail.sql",
    "pdd_backend/sql/backtest/insert_backtest_metrics.sql",
)

MODEL_IMPLEMENTATION_FILES = (
    "pdd_backend/flows/analytical.py",
    "pdd_backend/jobs/common.py",
    "pdd_backend/jobs/stock_daily.py",
    "pdd_backend/jobs/sales_daily.py",
    "pdd_backend/jobs/pdvb.py",
    "pdd_backend/windows.py",
    "pdd_backend/sql/stock/upsert_stock_daily.sql",
    "pdd_backend/sql/sales/upsert_sales_daily.sql",
    "pdd_backend/sql/pdvb/insert_pdvb_detail.sql",
)

SCOPE_IMPLEMENTATION_FILES = (
    "pdd_backend/jobs/scope_snapshot.py",
    "pdd_backend/scope_rules.py",
    "pdd_backend/rules/scope_exclusions.json",
    "pdd_backend/sql/scope/prepare_scope_snapshot.sql",
    "pdd_backend/sql/scope/insert_scope_version.sql",
    "pdd_backend/sql/scope/insert_scope_articles.sql",
    "pdd_backend/sql/scope/insert_scope_pairs.sql",
)


FROZEN_SCOPE_SQL = """
SELECT
    scope_version_uuid,
    scope_code,
    version_no,
    status,
    business_date,
    source_as_of_ts,
    article_count,
    routed_article_count,
    pair_count,
    destination_count,
    article_checksum,
    pair_checksum,
    scope_checksum,
    pair_filter -> 'operational_branch_exclusion_policy'
        AS operational_branch_exclusion_policy
FROM datamart.dm_pdd_scope_version
WHERE scope_version_uuid = CAST(:scope_version_uuid AS uuid)
"""


def file_hashes_for(
    root: Path,
    relative_paths: tuple[str, ...],
) -> tuple[dict[str, str], str]:
    hashes: dict[str, str] = {}
    for relative_path in relative_paths:
        payload = (root / relative_path).read_bytes()
        hashes[relative_path] = hashlib.sha256(payload).hexdigest()
    canonical = "\n".join(f"{name}:{hashes[name]}" for name in sorted(hashes))
    combined = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return hashes, combined


def file_hashes(root: Path) -> tuple[dict[str, str], str]:
    return file_hashes_for(root, IMPLEMENTATION_FILES)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scope-version-uuid")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    settings = Settings.from_env()
    engine = build_engine(settings)
    try:
        with engine.connect() as connection:
            if args.scope_version_uuid:
                row = connection.execute(
                    text(FROZEN_SCOPE_SQL),
                    {"scope_version_uuid": args.scope_version_uuid},
                ).mappings().one_or_none()
                if row is None:
                    raise RuntimeError(
                        f"Scope congelado inexistente: {args.scope_version_uuid}"
                    )
                scope = dict(row)
            else:
                scope = dict(
                    connection.execute(
                        text(SCOPE_SQL),
                        {"exclusion_policy_json": scope_exclusion_policy_json()},
                    ).mappings().one()
                )
    finally:
        engine.dispose()

    hashes, combined = file_hashes(root)
    model_hashes, model_combined = file_hashes_for(
        root, MODEL_IMPLEMENTATION_FILES
    )
    scope_hashes, scope_combined = file_hashes_for(
        root, SCOPE_IMPLEMENTATION_FILES
    )
    result = {
        "scope": scope,
        "scope_exclusion_policy": load_scope_exclusion_policy(),
        "implementation": {
            "files": hashes,
            "combined_sha256": combined,
        },
        "model_implementation": {
            "files": model_hashes,
            "combined_sha256": model_combined,
        },
        "scope_implementation": {
            "files": scope_hashes,
            "combined_sha256": scope_combined,
        },
    }
    print(json.dumps(result, default=str, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
