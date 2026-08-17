from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml

from pdd_backend.api.app import app
from pdd_backend.api.models import BacklogQuery, DirectedNeedQuery
from pdd_backend.api.repository import PddRepository
from pdd_backend.config import OperationalSettings
from pdd_backend.db import build_api_engine


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "contracts" / "pdd-frontend-openapi-v1.yaml"


def _runtime_operations() -> set[tuple[str, str]]:
    result: set[tuple[str, str]] = set()
    for route in app.routes:
        path = getattr(route, "path", "")
        if not path.startswith("/api/v1/pdd") or path.endswith(("/docs", "/runtime-openapi.json")):
            continue
        normalized = path.removeprefix("/api/v1/pdd") or "/"
        for method in getattr(route, "methods", set()):
            if method in {"GET", "POST", "PUT", "PATCH", "DELETE"}:
                result.add((method.lower(), normalized))
    return result


def _contract_operations() -> set[tuple[str, str]]:
    contract = yaml.safe_load(CONTRACT.read_text(encoding="utf-8"))
    return {
        (method, path)
        for path, item in contract["paths"].items()
        for method in item
        if method in {"get", "post", "put", "patch", "delete"}
    }


def main() -> None:
    expected = _contract_operations()
    actual = _runtime_operations()
    if expected != actual:
        raise RuntimeError(
            f"Rutas distintas al contrato; faltan={sorted(expected-actual)}, sobran={sorted(actual-expected)}"
        )

    settings = OperationalSettings.from_env()
    engine = build_api_engine(settings)
    repository = PddRepository(engine, settings)
    repository.ensure_contract()
    snapshot = repository.current_snapshot()
    if snapshot is None:
        raise RuntimeError("No existe snapshot vigente para validar la API")
    dashboard = repository.dashboard()
    page, _ = repository.list_backlog(BacklogQuery(page_size=2), None)
    if not page["data"]:
        raise RuntimeError("El backlog vigente no devolvio filas")
    backlog_uuid = page["data"][0]["backlogLineUuid"]
    detail = repository.get_backlog(backlog_uuid)
    explanation = repository.backlog_explanation(backlog_uuid)
    catalogs = repository.filter_catalogs()
    run = repository.calculation_run(snapshot["calculation_run_uuid"])
    directed, _ = repository.list_directed(DirectedNeedQuery(page_size=2), None)

    output: dict[str, Any] = {
        "status": "OK",
        "database": settings.pg_database,
        "runtime_operations": len(actual),
        "snapshot_version": str(snapshot["snapshot_version"]),
        "business_date": str(snapshot["business_date"]),
        "dashboard_lines": dashboard["lineCount"],
        "backlog_sample_rows": len(page["data"]),
        "backlog_detail_sources": len(detail["sources"]),
        "explanation_formula_version": explanation["formulaVersion"],
        "catalog_branches": len(catalogs["branches"]),
        "calculation_run_status": run["status"],
        "directed_need_rows": len(directed["data"]),
    }
    print(json.dumps(output, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
