import re
from pathlib import Path

from pdd_backend.operational_contract import OPERATIONAL_TABLES


ROOT = Path(__file__).resolve().parents[2]


def test_operational_tables_use_pdd_prefix() -> None:
    ddl_files = (
        ROOT / "PDD - DDL Operativo Core connexa_platform_ms v2.2.sql",
        ROOT / "PDD - DDL Operativo DECAS connexa_platform_ms v2.2.sql",
    )
    assert len(OPERATIONAL_TABLES) == 27
    assert len(OPERATIONAL_TABLES) == len(set(OPERATIONAL_TABLES))
    assert all(table.startswith("pdd_") for table in OPERATIONAL_TABLES)
    assert "pdd_item_logistics_snapshot" in OPERATIONAL_TABLES

    # Los DDL maestros viven un nivel sobre backend y no forman parte del
    # despliegue liviano de /srv/PDD/backend. Si están disponibles, también
    # verificamos que coincidan exactamente con el contrato canónico.
    if all(ddl_file.is_file() for ddl_file in ddl_files):
        created = []
        for ddl_file in ddl_files:
            created.extend(
                re.findall(
                    r"CREATE TABLE stock_management\.([a-z][a-z0-9_]*)",
                    ddl_file.read_text(encoding="utf-8"),
                )
            )
        assert set(created) == set(OPERATIONAL_TABLES)
