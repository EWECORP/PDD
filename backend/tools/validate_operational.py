from __future__ import annotations

import json

from sqlalchemy import text

from pdd_backend.config import OperationalSettings, Settings
from pdd_backend.db import build_engine, build_operational_engine


PUBLISHER_TABLES = (
    "pdd_pdvb_model_version",
    "pdd_distribution_scope_version",
    "pdd_distribution_scope_article",
    "pdd_distribution_scope_pair",
    "pdd_calculation_run",
    "pdd_pdvb_publication_batch",
    "pdd_pdvb_publication_stage",
    "pdd_pdvb_estimate",
    "pdd_pdvb_current",
    "pdd_pdvb_quality_issue",
)


def main() -> None:
    source_settings = Settings.from_env()
    target_settings = OperationalSettings.from_env()
    source_engine = build_engine(source_settings)
    target_engine = build_operational_engine(target_settings)
    try:
        with source_engine.connect() as source:
            source_database = source.execute(text("SELECT current_database()" )).scalar_one()
        with target_engine.connect() as target:
            target_database = target.execute(text("SELECT current_database()" )).scalar_one()
            existing = {
                row[0]
                for row in target.execute(
                    text(
                        """
                        SELECT table_name
                        FROM information_schema.tables
                        WHERE table_schema = 'stock_management'
                        """
                    )
                )
            }
        missing = sorted(set(PUBLISHER_TABLES) - existing)
        legacy = sorted(
            table for table in existing
            if table in {name.removeprefix("pdd_") for name in PUBLISHER_TABLES}
        )
        result = {
            "source_database": source_database,
            "target_database": target_database,
            "publisher_contract": "OK" if not missing else "INCOMPLETE",
            "missing_tables": missing,
            "legacy_unprefixed_tables": legacy,
        }
        print(json.dumps(result, indent=2, sort_keys=True))
        if missing:
            raise SystemExit(2)
    finally:
        target_engine.dispose()
        source_engine.dispose()


if __name__ == "__main__":
    main()
