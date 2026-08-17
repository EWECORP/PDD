from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from uuid import UUID

from fastapi.testclient import TestClient

from pdd_backend.api.app import API_PREFIX, create_app
from pdd_backend.api.cursor import CursorCodec
from pdd_backend.api.models import Identity
from tools.validate_api import _contract_operations, _runtime_operations


ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = ROOT / "contracts" / "examples"


def _example(name: str) -> dict:
    return json.loads((EXAMPLES / name).read_text(encoding="utf-8"))


class FakeRepository:
    def __init__(self) -> None:
        self.dashboard_value = _example("dashboard-summary.json")
        self.backlog_page = _example("backlog-page.json")
        self.backlog_detail = _example("backlog-detail.json")
        self.directed = _example("directed-need.json")

    def ensure_contract(self) -> None:
        return None

    def current_snapshot(self) -> dict:
        snapshot = self.dashboard_value["snapshot"]
        return {
            "snapshot_version": UUID(snapshot["snapshotVersion"]),
            "business_date": snapshot["businessDate"],
            "calculation_run_uuid": UUID(snapshot["calculationRunUuid"]),
            "published_at": snapshot["publishedAt"],
            "freshness_status": snapshot["freshnessStatus"],
        }

    def dashboard(self) -> dict:
        return deepcopy(self.dashboard_value)

    def list_backlog(self, query, cursor):
        value = deepcopy(self.backlog_page)
        value["meta"]["nextCursor"] = None
        return value, ("100", "90", "2026-08-18", "2026-08-16", value["data"][-1]["backlogLineUuid"])

    def get_backlog(self, backlog_uuid):
        value = deepcopy(self.backlog_detail)
        value["backlogLineUuid"] = str(backlog_uuid)
        return value

    def backlog_explanation(self, backlog_uuid):
        return {
            "backlogLineUuid": str(backlog_uuid),
            "snapshotVersion": self.dashboard_value["snapshot"]["snapshotVersion"],
            "formulaVersion": "DAILY_DECAS_V1",
            "calculationRunUuid": self.dashboard_value["snapshot"]["calculationRunUuid"],
            "configurationVersionUuid": None,
            "stock": {},
            "formula": {},
            "sources": [],
            "alertCodes": [],
        }

    def filter_catalogs(self):
        row = self.backlog_page["data"][0]
        return {
            "snapshotVersion": self.dashboard_value["snapshot"]["snapshotVersion"],
            "branches": [row["branch"]],
            "articles": [row["article"]],
            "suppliers": [row["supplier"]],
        }

    def calculation_run(self, run_uuid):
        return {"calculationRunUuid": str(run_uuid)}

    def list_directed(self, query, cursor):
        return {
            "data": [deepcopy(self.directed)], "pageSize": query.page_size,
            "hasNextPage": False, "nextCursor": None, "totalItems": 1,
        }, None

    def get_directed(self, directed_uuid, *args, **kwargs):
        value = deepcopy(self.directed)
        value["directedNeedUuid"] = str(directed_uuid)
        return value

    def create_directed(self, payload, actor, idempotency_key, correlation_id):
        value = deepcopy(self.directed)
        value["ownerUser"] = actor
        return value, False

    def replace_directed(self, directed_uuid, expected_version, payload, actor, correlation_id):
        value = self.get_directed(directed_uuid)
        value["versionNo"] = expected_version + 1
        value["ownerUser"] = actor
        return value

    def transition_directed(self, directed_uuid, expected_version, action, reason, actor, correlation_id):
        value = self.get_directed(directed_uuid)
        value["versionNo"] = expected_version + 1
        value["status"] = {"activate": "ACTIVE", "cancel": "CANCELLED", "close": "CLOSED"}[action]
        return value

    def directed_versions(self, directed_uuid):
        return []


def _identity(roles: set[str]):
    def provider(**kwargs):
        return Identity(user_id="eduardo.ettlin", roles=frozenset(roles))
    return provider


def _client(roles: set[str] | None = None) -> TestClient:
    app = create_app(
        repository=FakeRepository(),
        authenticator=_identity(roles or {"PDD_SUPERVISOR"}),
        cursor_codec=CursorCodec("test-cursor-secret-123456789"),
    )
    return TestClient(app)


def _write_payload() -> dict:
    return {
        "needType": "E",
        "businessReference": "TEST-API-001",
        "supplierId": 100,
        "validFrom": "2026-08-18",
        "validTo": "2026-08-20",
        "priorityScore": 100,
        "ownerUser": "eduardo.ettlin",
        "reason": "Prueba de contrato",
        "notes": None,
        "lines": [
            {
                "branchId": 1,
                "articleId": 1000,
                "originalQuantity": 12,
                "targetDate": "2026-08-18",
                "slaAt": None,
                "unitCode": "UN",
            }
        ],
    }


def test_read_endpoints_and_signed_cursor() -> None:
    client = _client()
    status = client.get(f"{API_PREFIX}/status")
    assert status.status_code == 200
    assert status.json()["status"] == "DEGRADED"
    summary = client.get(f"{API_PREFIX}/dashboard/summary")
    assert summary.status_code == 200
    assert summary.json()["lineCount"] == 15032
    page = client.get(f"{API_PREFIX}/backlog?pageSize=2&needType=D,S")
    assert page.status_code == 200
    assert page.json()["meta"]["nextCursor"]
    assert page.headers["etag"].startswith('W/"')


def test_create_requires_edit_role_and_returns_concurrency_headers() -> None:
    viewer = _client({"PDD_VIEWER"})
    denied = viewer.post(
        f"{API_PREFIX}/directed-needs",
        headers={"Idempotency-Key": "frontend-test-001"},
        json=_write_payload(),
    )
    assert denied.status_code == 403
    assert denied.json()["code"] == "FORBIDDEN"

    supervisor = _client()
    created = supervisor.post(
        f"{API_PREFIX}/directed-needs",
        headers={"Idempotency-Key": "frontend-test-001"},
        json=_write_payload(),
    )
    assert created.status_code == 201
    assert created.headers["etag"]
    assert created.headers["location"].startswith(f"{API_PREFIX}/directed-needs/")
    assert created.headers["cache-control"] == "no-store"


def test_transition_rejects_etag_for_another_resource() -> None:
    client = _client()
    directed_uuid = UUID(_example("directed-need.json")["directedNeedUuid"])
    response = client.post(
        f"{API_PREFIX}/directed-needs/{directed_uuid}/activate",
        headers={"If-Match": 'W/"00000000-0000-0000-0000-000000000001:1"'},
        json={"reason": "Aprobación de prueba"},
    )
    assert response.status_code == 400
    assert response.json()["code"] == "INVALID_QUERY"


def test_validation_errors_follow_problem_details() -> None:
    response = _client().get(f"{API_PREFIX}/backlog?needType=X")
    assert response.status_code == 400
    body = response.json()
    assert body["code"] == "INVALID_QUERY"
    assert body["traceId"]
    assert body["fieldErrors"]


def test_runtime_routes_cover_the_versioned_contract() -> None:
    assert _runtime_operations() == _contract_operations()
