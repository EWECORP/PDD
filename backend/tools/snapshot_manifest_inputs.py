"""Obtiene la fotografia reproducible de scope y hashes de implementacion."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from sqlalchemy import text

from pdd_backend.config import Settings
from pdd_backend.db import build_engine


SCOPE_SQL = """
WITH cd_articles AS (
    SELECT DISTINCT ON (c_articulo)
        c_articulo,
        c_proveedor_primario,
        active_for_purchase,
        habilitado,
        active_for_sale,
        active_on_mix,
        fecha_extraccion
    FROM src.base_productos_vigentes
    WHERE c_sucu_empr = 41
      AND active_for_purchase = 1
    ORDER BY c_articulo, fecha_extraccion DESC NULLS LAST
),
pairs AS (
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
)
SELECT
    a.article_count,
    p.pair_count,
    p.destination_count,
    p.routed_article_count,
    greatest(a.source_as_of_ts, p.source_as_of_ts) AS source_as_of_ts,
    a.article_checksum,
    p.pair_checksum,
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
"""


IMPLEMENTATION_FILES = (
    "pdd_backend/jobs/stock_daily.py",
    "pdd_backend/jobs/sales_daily.py",
    "pdd_backend/jobs/pdvb.py",
    "pdd_backend/windows.py",
    "pdd_backend/sql/stock/upsert_stock_daily.sql",
    "pdd_backend/sql/sales/upsert_sales_daily.sql",
    "pdd_backend/sql/pdvb/insert_pdvb_detail.sql",
)


def file_hashes(root: Path) -> tuple[dict[str, str], str]:
    hashes: dict[str, str] = {}
    for relative_path in IMPLEMENTATION_FILES:
        payload = (root / relative_path).read_bytes()
        hashes[relative_path] = hashlib.sha256(payload).hexdigest()
    canonical = "\n".join(f"{name}:{hashes[name]}" for name in sorted(hashes))
    combined = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return hashes, combined


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    settings = Settings.from_env()
    engine = build_engine(settings)
    try:
        with engine.connect() as connection:
            scope = dict(connection.execute(text(SCOPE_SQL)).mappings().one())
    finally:
        engine.dispose()

    hashes, combined = file_hashes(root)
    result = {
        "scope": scope,
        "implementation": {
            "files": hashes,
            "combined_sha256": combined,
        },
    }
    print(json.dumps(result, default=str, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
