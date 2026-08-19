import json
from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "contracts" / "pdd-frontend-openapi-v1.yaml"
EXAMPLES = ROOT / "contracts" / "examples"


def _walk(value: Any):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk(child)


def test_openapi_contract_is_parseable_and_has_unique_operations() -> None:
    contract = yaml.safe_load(CONTRACT.read_text(encoding="utf-8"))
    assert contract["openapi"] == "3.1.0"
    assert contract["info"]["version"] == "1.1.0"
    assert contract["servers"][0]["url"] == "/connexa/api/v1/pdd"
    assert contract["x-connexa-implementation"]["runtime"] == "Java 21"
    assert contract["x-connexa-implementation"]["pythonRuntimeRole"] == (
        "analytical-etl-only"
    )

    operations = [
        operation["operationId"]
        for path in contract["paths"].values()
        for method, operation in path.items()
        if method in {"get", "post", "put", "patch", "delete"}
    ]
    assert operations
    assert len(operations) == len(set(operations))


def test_all_internal_component_references_exist() -> None:
    contract = yaml.safe_load(CONTRACT.read_text(encoding="utf-8"))
    for node in _walk(contract):
        reference = node.get("$ref")
        if not reference or not reference.startswith("#/components/"):
            continue
        current: Any = contract
        for part in reference.removeprefix("#/").split("/"):
            assert part in current, f"Referencia inexistente: {reference}"
            current = current[part]


def test_mock_examples_are_valid_json_and_snapshot_consistent() -> None:
    examples = {
        path.stem: json.loads(path.read_text(encoding="utf-8"))
        for path in EXAMPLES.glob("*.json")
    }
    assert set(examples) == {
        "backlog-detail",
        "backlog-page",
        "dashboard-summary",
        "directed-need",
        "problem-details",
    }
    dashboard = examples["dashboard-summary"]
    backlog = examples["backlog-page"]
    snapshot = dashboard["snapshot"]["snapshotVersion"]
    assert backlog["meta"]["snapshot"]["snapshotVersion"] == snapshot
    assert all(row["snapshotVersion"] == snapshot for row in backlog["data"])

    totals = dashboard["quantities"]
    assert totals["mandatory"] == totals["d"] + totals["e"] + totals["c"]
    assert totals["optional"] == totals["a"] + totals["s"]
    assert totals["total"] == totals["mandatory"] + totals["optional"]
    assert sum(dashboard["freshnessCounts"].values()) == dashboard["lineCount"]


def test_directed_need_mock_covers_active_partial_special_need() -> None:
    directed = json.loads(
        (EXAMPLES / "directed-need.json").read_text(encoding="utf-8")
    )
    assert directed["needType"] in {"E", "C", "A"}
    assert directed["status"] == "ACTIVE"
    assert directed["approverUser"]
    line = directed["lines"][0]
    assert line["status"] == "PARTIAL"
    assert line["openQuantity"] == (
        line["originalQuantity"]
        - line["preparedAllocatedQuantity"]
        - line["cancelledQuantity"]
    )
