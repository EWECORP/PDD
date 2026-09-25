from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml


BACKEND_ROOT = Path(__file__).resolve().parents[1]
CONTRACT = BACKEND_ROOT / "contracts" / "pdd-planning-openapi-v1.yaml"
MIGRATION = BACKEND_ROOT / "contracts" / "sql" / "planning_migration_v2_7.sql"


def _walk(node: Any):
    if isinstance(node, dict):
        yield node
        for value in node.values():
            yield from _walk(value)
    elif isinstance(node, list):
        for value in node:
            yield from _walk(value)


def test_planning_openapi_is_parseable_and_java_owned() -> None:
    contract = yaml.safe_load(CONTRACT.read_text(encoding="utf-8"))

    assert contract["openapi"] == "3.1.0"
    assert contract["info"]["version"] == "1.0.0"
    assert contract["servers"][0]["url"] == "/connexa/api/v1/pdd"
    assert contract["x-connexa-implementation"]["runtime"] == "Java 21"
    assert contract["x-connexa-implementation"]["pythonRuntimeRole"] == (
        "analytical-etl-only"
    )

    operation_ids = [
        operation["operationId"]
        for path in contract["paths"].values()
        for method, operation in path.items()
        if method.lower() in {"get", "post", "put", "patch", "delete"}
    ]
    assert len(operation_ids) == len(set(operation_ids))
    assert {
        "listPlanningBacklog",
        "createDispatchPlan",
        "approveDispatchPlan",
        "publishDispatchTrip",
        "pollValkimiaImport",
    }.issubset(operation_ids)


def test_planning_openapi_references_resolve_locally() -> None:
    contract = yaml.safe_load(CONTRACT.read_text(encoding="utf-8"))

    for node in _walk(contract):
        reference = node.get("$ref")
        if not reference:
            continue
        assert reference.startswith("#/"), reference
        current: Any = contract
        for token in reference[2:].split("/"):
            current = current[token.replace("~1", "/").replace("~0", "~")]


def test_planning_migration_uses_prefixed_operational_tables() -> None:
    sql = MIGRATION.read_text(encoding="utf-8")
    created = re.findall(
        r"CREATE TABLE IF NOT EXISTS stock_management\.([a-z][a-z0-9_]*)",
        sql,
    )

    assert set(created) == {
        "pdd_dispatch_plan",
        "pdd_dispatch_trip",
        "pdd_dispatch_trip_stop",
        "pdd_dispatch_trip_line",
        "pdd_dispatch_line_allocation",
        "pdd_valkimia_status_mapping",
        "pdd_integration_checkpoint",
    }
    assert all(name.startswith("pdd_") for name in created)
    assert "\\set ON_ERROR_STOP on" in sql
    assert "connexa_platform_diarco" in sql


def test_planning_contract_preserves_end_to_end_public_ids() -> None:
    contract = yaml.safe_load(CONTRACT.read_text(encoding="utf-8"))
    schemas = contract["components"]["schemas"]

    assert "dispatchTripLineUuid" in schemas["DispatchTripLine"]["properties"]
    assert "valkimiaImportLineUuid" in schemas["ValkimiaImportLine"]["properties"]
    assert "backlogLineUuid" in schemas["ValkimiaImportLine"]["properties"]
