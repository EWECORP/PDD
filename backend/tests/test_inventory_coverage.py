from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID
from unittest.mock import Mock

import pytest

from pdd_backend.jobs.daily_decas import (
    apply_inventory_parameters,
    select_publicable_estimates,
)
from pdd_backend.jobs.inventory_coverage import (
    InventoryGapPolicy,
    assess_inventory_coverage,
    inventory_issue,
)
from pdd_backend.jobs.daily_pipeline import pipeline_stage_revision


def _parameter(article: int, *, active: bool | None = True) -> dict:
    return {
        "codigo_articulo": str(article), "sucursal": "1",
        "inventory_product_id": UUID(int=1),
        "inventory_site_id": UUID(int=2),
        "inventory_product_site_id": UUID(int=3),
        "inventory_replenishment_id": UUID(int=4),
        "inventory_replenishment_active": active,
        "product_site_id": UUID(int=3) if active else None,
        "replenishment_id": UUID(int=4) if active else None,
        "replenishment_row_version": 1 if active else None,
        "target_stock_days": Decimal("7") if active else None,
        "overstock_days": Decimal("0") if active else None,
        "product_site_active": True,
        "active_for_purchase": True,
        "captured_at": datetime(2026, 10, 29, tzinfo=timezone.utc),
    }


def test_policy_enforces_both_authorized_limits(monkeypatch) -> None:
    policy = InventoryGapPolicy()
    assert policy.allowed(44_886) == 100
    assert policy.allowed(1_000) == 5
    monkeypatch.setenv("PDD_INVENTORY_MAX_EXCLUDED_PAIRS", "101")
    with pytest.raises(ValueError, match="no puede superar"):
        InventoryGapPolicy.from_env()
    monkeypatch.setenv("PDD_INVENTORY_MAX_EXCLUDED_PAIRS", "10")
    monkeypatch.setenv("PDD_INVENTORY_MAX_EXCLUDED_PERCENT", "0.6")
    with pytest.raises(ValueError, match="no puede superar"):
        InventoryGapPolicy.from_env()


def test_coverage_distinguishes_missing_and_inactive() -> None:
    missing = _parameter(101)
    missing["inventory_replenishment_id"] = None
    missing["product_site_id"] = None
    missing["replenishment_id"] = None
    inactive = _parameter(102, active=False)
    rows = [_parameter(100), missing, inactive]
    assert inventory_issue(missing) == "REPLENISHMENT_MISSING"
    assert inventory_issue(inactive) == "REPLENISHMENT_INACTIVE"
    report = assess_inventory_coverage(rows, InventoryGapPolicy(2, Decimal("100")))
    assert report["status"] == "WARNING_CONTINUE"
    assert report["reason_counts"] == {
        "REPLENISHMENT_INACTIVE": 1, "REPLENISHMENT_MISSING": 1,
    }
    assert assess_inventory_coverage(rows, InventoryGapPolicy())["status"] == "BLOCKED"


def test_daily_snapshot_records_excluded_pair_and_keeps_valid_policy() -> None:
    stock = [
        {"codigo_articulo": 100, "sucursal": 1},
        {"codigo_articulo": 101, "sucursal": 1},
    ]
    missing = _parameter(101)
    missing["inventory_replenishment_id"] = None
    missing["product_site_id"] = None
    missing["replenishment_id"] = None
    snapshot = apply_inventory_parameters(
        stock, [_parameter(100), missing], max_excluded_pairs=1,
    )
    assert snapshot.row_count == 1
    assert snapshot.excluded_pairs == (
        {"codigo_articulo": 101, "sucursal": 1,
         "reason": "REPLENISHMENT_MISSING"},
    )
    assert stock[0]["q_dias_stock"] == Decimal("7")
    assert "q_dias_stock" not in stock[1]
    with pytest.raises(RuntimeError, match="exceden el limite"):
        apply_inventory_parameters(stock, [_parameter(100), missing])


def test_excluded_inventory_pair_cannot_generate_automatic_need() -> None:
    estimates = [
        {"codigo_articulo": 100, "sucursal": 1, "status": "OK"},
        {"codigo_articulo": 101, "sucursal": 1, "status": "OK"},
        {"codigo_articulo": 102, "sucursal": 1, "status": "BLOCKED"},
    ]
    assert select_publicable_estimates(estimates, {(101, 1)}) == estimates[:1]


def test_inventory_revision_changes_when_policy_is_repaired() -> None:
    before = [_parameter(100), _parameter(101, active=False)]
    after = [_parameter(100), _parameter(101)]
    first = assess_inventory_coverage(before, InventoryGapPolicy())
    second = assess_inventory_coverage(after, InventoryGapPolicy())
    assert first["coverage_checksum"] != second["coverage_checksum"]
    first_revision = pipeline_stage_revision(
        "DAILY_DECAS", "DAILY_PIPELINE_V3", datetime(2026, 10, 29).date(),
        first["coverage_checksum"],
    )
    second_revision = pipeline_stage_revision(
        "DAILY_DECAS", "DAILY_PIPELINE_V3", datetime(2026, 10, 29).date(),
        second["coverage_checksum"],
    )
    assert first_revision != second_revision


def test_prefect_reporting_failure_keeps_full_gap_log(monkeypatch) -> None:
    from pdd_backend.flows import inventory_coverage as report_flow

    def fail(**_kwargs):
        raise RuntimeError("Prefect API unavailable")

    monkeypatch.setattr(report_flow, "emit_event", fail)
    monkeypatch.setattr(report_flow, "create_markdown_artifact", fail)
    logger = Mock()
    result = {
        "scope_version_uuid": "38af3a1d-4d9f-42a3-9ab1-b6ae224b3551",
        "scope_evaluated": "LIVE_CANDIDATE",
        "status": "BLOCKED",
        "scope_pairs": 2,
        "gap_count": 2,
        "allowed_gap_count": 0,
        "added_pairs": 1,
        "removed_pairs": 0,
        "active_directed_pairs": [],
        "reason_counts": {"REPLENISHMENT_MISSING": 2},
        "gaps": [
            {"codigo_articulo": 100, "sucursal": 1,
             "reason": "REPLENISHMENT_MISSING"},
            {"codigo_articulo": 101, "sucursal": 1,
             "reason": "REPLENISHMENT_MISSING"},
        ],
    }
    report_flow._publish_diagnostics(result, "TEST", logger)
    assert logger.warning.call_count == 4
    assert "100" in logger.warning.call_args_list[0].args[4]
    assert "101" in logger.warning.call_args_list[0].args[4]
