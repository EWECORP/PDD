import json

from tools.run_frontend_mock import mock_response


def test_mock_serves_dashboard_and_backlog() -> None:
    status, headers, dashboard = mock_response(
        "GET", "/api/v1/pdd/dashboard/summary"
    )
    assert status == 200
    assert headers["ETag"]
    assert dashboard["lineCount"] == 15032

    status, _, backlog = mock_response("GET", "/api/v1/pdd/backlog?pageSize=50")
    assert status == 200
    assert backlog["meta"]["snapshot"]["snapshotVersion"] == (
        dashboard["snapshot"]["snapshotVersion"]
    )


def test_mock_mutations_cover_idempotency_and_version_conflict() -> None:
    status, _, problem = mock_response(
        "POST", "/api/v1/pdd/directed-needs", body=b"{}"
    )
    assert status == 400
    assert problem["code"] == "IDEMPOTENCY_KEY_REQUIRED"

    status, headers, directed = mock_response(
        "POST",
        "/api/v1/pdd/directed-needs",
        headers={"Idempotency-Key": "mock-key-001"},
        body=json.dumps({"needType": "E"}).encode(),
    )
    assert status == 201
    assert headers["Location"]
    assert directed["status"] == "DRAFT"

    status, _, problem = mock_response(
        "PUT",
        f"/api/v1/pdd/directed-needs/{directed['directedNeedUuid']}",
        headers={"If-Match": 'W/"stale"'},
        body=b"{}",
    )
    assert status == 409
    assert problem["code"] == "VERSION_CONFLICT"
