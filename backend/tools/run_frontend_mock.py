from __future__ import annotations

import argparse
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import urlparse


ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = ROOT / "contracts" / "examples"
BASE = "/connexa/api/v1/pdd"


def _load(name: str) -> dict[str, Any]:
    return json.loads((EXAMPLES / name).read_text(encoding="utf-8"))


def _problem(status: int, code: str, message: str) -> dict[str, Any]:
    return {
        "type": f"/problems/{code.lower().replace('_', '-')}",
        "title": "Error mock PDD",
        "status": status,
        "code": code,
        "message": message,
        "traceId": "mock-trace-id",
        "correlationId": None,
        "fieldErrors": [],
    }


def mock_response(
    method: str,
    raw_path: str,
    headers: Mapping[str, str] | None = None,
    body: bytes | None = None,
) -> tuple[int, dict[str, str], dict[str, Any] | list[Any] | None]:
    headers = headers or {}
    parsed = urlparse(raw_path)
    path = parsed.path.rstrip("/") or "/"
    if not path.startswith(BASE):
        return 404, {}, _problem(404, "RESOURCE_NOT_FOUND", "Ruta mock inexistente")
    relative = path.removeprefix(BASE) or "/"
    dashboard = _load("dashboard-summary.json")
    backlog_page = _load("backlog-page.json")
    backlog_detail = _load("backlog-detail.json")
    directed = _load("directed-need.json")

    if method == "GET" and relative == "/status":
        return 200, {}, {
            "status": "DEGRADED",
            "environment": "FRONTEND_MOCK",
            "apiVersion": "1.1.0",
            "currentSnapshot": dashboard["snapshot"],
            "blockers": ["MOCK_DATA", "DIRECTED_NEEDS_NOT_PERSISTED"],
        }
    if method == "GET" and relative == "/dashboard/summary":
        return 200, {"ETag": 'W/"mock-dashboard:1"'}, dashboard
    if method == "GET" and relative == "/backlog":
        return 200, {
            "ETag": 'W/"mock-backlog:1"',
            "X-PDD-Mock-Filters": "ignored",
        }, backlog_page
    if method == "GET" and relative == "/catalogs/filters":
        rows = backlog_page["data"]
        return 200, {}, {
            "snapshotVersion": backlog_page["meta"]["snapshot"]["snapshotVersion"],
            "branches": list({row["branch"]["id"]: row["branch"] for row in rows}.values()),
            "articles": list({row["article"]["id"]: row["article"] for row in rows}.values()),
            "suppliers": list(
                {
                    row["supplier"]["id"]: row["supplier"]
                    for row in rows
                    if row.get("supplier") is not None
                }.values()
            ),
        }
    if method == "GET" and relative.startswith("/backlog/"):
        suffix = relative.removeprefix("/backlog/")
        line_uuid = suffix.removesuffix("/explanation")
        if line_uuid != backlog_detail["backlogLineUuid"]:
            return 404, {}, _problem(404, "RESOURCE_NOT_FOUND", "Línea mock inexistente")
        if suffix.endswith("/explanation"):
            return 200, {}, {
                "backlogLineUuid": line_uuid,
                "snapshotVersion": backlog_detail["snapshotVersion"],
                "formulaVersion": "BACKLOG_V1_TEST_PILOT",
                "calculationRunUuid": "f423e470-3b7d-44e0-970a-caaf401c9480",
                "configurationVersionUuid": "2f916828-c59d-4190-a795-29ac5cfc1a66",
                "stock": {
                    "physicalStock": 0,
                    "directPoInbound": 0,
                    "cdInTransit": 0,
                    "specialSaleCommitted": 0,
                    "confirmedTransferPending": 0,
                    "netStock": 0,
                    "coverageDays": 0,
                    "pdvbBusinessDate": "2026-08-16",
                    "pdvbValue": 12,
                    "leadTimeDays": 5,
                    "targetStockDays": 10,
                    "overstockDays": 2,
                    "criticalStock": 60,
                    "minimumStock": 120,
                    "maximumStock": 120,
                    "overstockQuantity": 24
                },
                "formula": {
                    "d": "max(maximumStock-netStock,0)",
                    "s": "max(maximumStock+overstock-max(netStock,0),0)-d",
                    "rounding": "CEIL_TO_PURCHASE_FACTOR"
                },
                "sources": backlog_detail["sources"],
                "alertCodes": backlog_detail["alertCodes"]
            }
        return 200, {"ETag": 'W/"e870017f:1"'}, backlog_detail

    directed_uuid = directed["directedNeedUuid"]
    if method == "GET" and relative == "/directed-needs":
        return 200, {}, {
            "data": [directed],
            "pageSize": 50,
            "hasNextPage": False,
            "nextCursor": None,
            "totalItems": 1,
        }
    if method == "POST" and relative == "/directed-needs":
        if not headers.get("Idempotency-Key"):
            return 400, {}, _problem(400, "IDEMPOTENCY_KEY_REQUIRED", "Falta Idempotency-Key")
        if body:
            json.loads(body.decode("utf-8"))
        created = {**directed, "status": "DRAFT", "versionNo": 1,
                   "approverUser": None, "approvedAt": None}
        return 201, {
            "Location": f"{BASE}/directed-needs/{directed_uuid}",
            "ETag": f'W/"{directed_uuid}:1"',
        }, created
    if relative.startswith(f"/directed-needs/{directed_uuid}"):
        if headers.get("If-Match") == 'W/"stale"':
            return 409, {}, _problem(409, "VERSION_CONFLICT", "Versión mock desactualizada")
        suffix = relative.removeprefix(f"/directed-needs/{directed_uuid}")
        if method == "GET" and suffix == "":
            return 200, {"ETag": f'W/"{directed_uuid}:2"'}, directed
        if method == "GET" and suffix == "/versions":
            return 200, {}, [
                {
                    "versionNo": 2,
                    "validFromTs": directed["updatedAt"],
                    "changedBy": directed["updatedBy"],
                    "changeReason": "Activación mock",
                    "beforeState": {"status": "DRAFT"},
                    "afterState": {"status": "ACTIVE"},
                    "correlationId": None,
                }
            ]
        if method == "PUT" and suffix == "":
            return 200, {"ETag": f'W/"{directed_uuid}:3"'}, {
                **directed, "versionNo": 3
            }
        if method == "POST" and suffix in {"/activate", "/cancel", "/close"}:
            status = {"/activate": "ACTIVE", "/cancel": "CANCELLED", "/close": "CLOSED"}[suffix]
            return 200, {"ETag": f'W/"{directed_uuid}:3"'}, {
                **directed, "status": status, "versionNo": 3
            }

    if method == "GET" and relative.startswith("/calculation-runs/"):
        run_uuid = relative.removeprefix("/calculation-runs/")
        return 200, {}, {
            "calculationRunUuid": run_uuid,
            "runType": "PUBLISH",
            "businessDate": "2026-08-16",
            "cutoffDate": "2026-08-15",
            "formulaVersion": "BACKLOG_V1_TEST_PILOT",
            "status": "SUCCEEDED",
            "current": True,
            "startedAt": "2026-08-17T16:45:41Z",
            "finishedAt": "2026-08-17T16:46:09Z",
            "createdBy": "eduardo.ettlin",
            "inputRowCount": 16699,
            "outputRowCount": 15032,
            "warningCount": 641,
            "errorCount": 0,
            "summary": {"mock": True},
            "sourceSnapshots": [],
        }
    return 404, {}, _problem(404, "RESOURCE_NOT_FOUND", "Recurso mock inexistente")


class MockHandler(BaseHTTPRequestHandler):
    server_version = "PDDFrontendMock/1.0"

    def _handle(self) -> None:
        content_length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(content_length) if content_length else None
        try:
            status, extra_headers, payload = mock_response(
                self.command, self.path, self.headers, body
            )
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            status, extra_headers, payload = (
                400,
                {},
                _problem(400, "INVALID_JSON", str(exc)),
            )
        response = b"" if payload is None else json.dumps(
            payload, ensure_ascii=False, indent=2
        ).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(response)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization, Idempotency-Key, If-Match, X-Correlation-Id")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PUT, OPTIONS")
        self.send_header("X-PDD-Mock", "true")
        for name, value in extra_headers.items():
            self.send_header(name, value)
        self.end_headers()
        if response:
            self.wfile.write(response)

    def do_GET(self) -> None:  # noqa: N802
        self._handle()

    def do_POST(self) -> None:  # noqa: N802
        self._handle()

    def do_PUT(self) -> None:  # noqa: N802
        self._handle()

    def do_OPTIONS(self) -> None:  # noqa: N802
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization, Idempotency-Key, If-Match, X-Correlation-Id")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PUT, OPTIONS")
        self.end_headers()


def main() -> None:
    parser = argparse.ArgumentParser(description="Servidor mock local PDD para frontend")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=4010)
    args = parser.parse_args()
    server = ThreadingHTTPServer((args.host, args.port), MockHandler)
    print(f"PDD mock escuchando en http://{args.host}:{args.port}{BASE}")
    print("Solo para desarrollo local. Ctrl+C para detener.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
