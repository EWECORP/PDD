from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[1]
OPENAPI = ROOT / "contracts" / "pdd-frontend-openapi-v1.yaml"
EXAMPLES = ROOT / "contracts" / "examples"


def walk(value: Any):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from walk(child)


def main() -> None:
    contract = yaml.safe_load(OPENAPI.read_text(encoding="utf-8"))
    if contract.get("openapi") != "3.1.0":
        raise RuntimeError("Se esperaba OpenAPI 3.1.0")
    operations = [
        operation["operationId"]
        for path in contract["paths"].values()
        for method, operation in path.items()
        if method in {"get", "post", "put", "patch", "delete"}
    ]
    if len(operations) != len(set(operations)):
        raise RuntimeError("Hay operationId duplicados")
    references = 0
    for node in walk(contract):
        reference = node.get("$ref")
        if not reference or not reference.startswith("#/components/"):
            continue
        references += 1
        current: Any = contract
        for part in reference.removeprefix("#/").split("/"):
            if part not in current:
                raise RuntimeError(f"Referencia OpenAPI inexistente: {reference}")
            current = current[part]
    examples = sorted(EXAMPLES.glob("*.json"))
    for example in examples:
        json.loads(example.read_text(encoding="utf-8"))
    print(
        json.dumps(
            {
                "status": "OK",
                "openapi": contract["openapi"],
                "api_version": contract["info"]["version"],
                "paths": len(contract["paths"]),
                "operations": len(operations),
                "schemas": len(contract["components"]["schemas"]),
                "internal_references": references,
                "example_files": len(examples),
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
