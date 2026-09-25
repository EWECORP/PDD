from __future__ import annotations

from pathlib import Path

import yaml


def _load_prod_manifest() -> dict:
    root = Path(__file__).resolve().parents[1]
    return yaml.safe_load((root / "prefect.prod.yaml").read_text(encoding="utf-8"))


def test_prod_manifest_isolated_from_test_and_desa() -> None:
    config = _load_prod_manifest()
    assert config["work_pool"] == {
        "name": "diarco-pdd",
        "work_queue_name": "pdd",
        "job_variables": {},
    }

    deployments = config["deployments"]
    names = {item["name"] for item in deployments}
    assert names
    assert all("_PROD" in name for name in names)
    assert "PDD_OPERATIONAL_DAILY_MASTER" not in names

    for deployment in deployments:
        assert deployment["work_pool"]["name"] == "diarco-pdd"
        assert deployment["work_pool"]["work_queue_name"] == "pdd"
        assert "pdd-test-127" not in str(deployment)
        assert "pdd-desa" not in str(deployment)


def test_prod_schedules_are_delivered_inactive() -> None:
    deployments = _load_prod_manifest()["deployments"]
    scheduled = [item for item in deployments if item.get("schedules")]
    assert scheduled
    assert all(
        schedule["active"] is False
        for deployment in scheduled
        for schedule in deployment["schedules"]
    )


def test_prod_master_uses_runtime_registry_parameters() -> None:
    deployments = _load_prod_manifest()["deployments"]
    master = next(
        item
        for item in deployments
        if item["name"] == "PDD_OPERATIONAL_DAILY_MASTER_PROD"
    )
    assert master["parameters"] == {
        "created_by": "pdd.daily.orchestrator.prod",
        "force": False,
    }
