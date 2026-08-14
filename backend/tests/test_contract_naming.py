import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_operational_tables_use_pdd_prefix() -> None:
    ddl_files = (
        ROOT / "PDD - DDL Operativo Core connexa_platform_ms v2.2.sql",
        ROOT / "PDD - DDL Operativo DECAS connexa_platform_ms v2.2.sql",
    )
    created = []
    for ddl_file in ddl_files:
        created.extend(
            re.findall(
                r"CREATE TABLE stock_management\.([a-z][a-z0-9_]*)",
                ddl_file.read_text(encoding="utf-8"),
            )
        )
    assert len(created) == 27
    assert all(table.startswith("pdd_") for table in created)
    assert "pdd_item_logistics_snapshot" in created
