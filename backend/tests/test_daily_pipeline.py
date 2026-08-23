from datetime import date, datetime, timezone
from inspect import getsource
from pathlib import Path
from uuid import UUID

import pytest
import yaml

from pdd_backend.jobs.daily_pipeline import (
    DailySourceState,
    REFRESH_OPEN_PO_SQL,
    pipeline_stage_revision,
    pipeline_stage_uuid,
    validate_published_pdvb_run,
    read_daily_source_state,
    refresh_open_purchase_orders,
    resolve_daily_pipeline_context,
)
from pdd_backend.flows.daily_pipeline import (
    pdd_operational_daily_flow,
    pdd_operational_publish_desa_flow,
)


SCOPE_UUID = UUID("f157e436-1094-431b-ae2a-8f477d780c3e")
MODEL_UUID = UUID("a0a35b25-628d-43f1-b651-82c97207fc60")
CONFIG_UUID = UUID("2f916828-c59d-4190-a795-29ac5cfc1a66")
PDVB_RUN_UUID = UUID("776354b5-b291-58ea-9579-0b86df61023b")
PUBLICATION_BATCH_UUID = UUID("8e07e28e-cf23-41e4-a4b6-c0a8a6b5e0b7")


def source_state(**overrides) -> DailySourceState:
    values = {
        "raw_sales_date": date(2026, 8, 15),
        "enriched_sales_date": date(2026, 8, 15),
        "stock_source_date": date(2026, 8, 15),
        "canonical_stock_date": date(2026, 8, 14),
        "scoped_sales_date": date(2026, 8, 14),
        "branch_stock_date": date(2026, 8, 16),
        "open_po_as_of_ts": datetime(2026, 8, 17, tzinfo=timezone.utc),
        "open_po_row_count": 100,
        "source_sync_run_uuid": "4ab919d4-2793-4101-90fe-5c5e60504a71",
        "source_sync_business_date": date(2026, 8, 16),
        "source_sync_status": "READY",
        "source_sync_refresh_mode": "FULL",
        "source_sync_finished_at": datetime(2026, 8, 16, 22, tzinfo=timezone.utc),
        "current_backlog_date": date(2026, 8, 14),
    }
    values.update(overrides)
    return DailySourceState(**values)


def test_daily_context_uses_day_after_common_close() -> None:
    context = resolve_daily_pipeline_context(
        source_state(),
        requested_business_date=None,
        today=date(2026, 8, 17),
    )
    assert context.status == "READY"
    assert context.business_date == date(2026, 8, 16)
    assert context.cutoff_date == date(2026, 8, 15)
    assert context.feature_start == date(2026, 8, 15)


def test_daily_context_catches_up_from_oldest_canonical_feature() -> None:
    context = resolve_daily_pipeline_context(
        source_state(
            canonical_stock_date=date(2026, 8, 10),
            scoped_sales_date=date(2026, 8, 12),
        ),
        requested_business_date=date(2026, 8, 16),
        today=date(2026, 8, 17),
    )
    assert context.feature_start == date(2026, 8, 11)


def test_daily_context_skips_already_published_date_unless_forced() -> None:
    state = source_state(current_backlog_date=date(2026, 8, 16))
    skipped = resolve_daily_pipeline_context(
        state,
        requested_business_date=None,
        today=date(2026, 8, 17),
    )
    forced = resolve_daily_pipeline_context(
        state,
        requested_business_date=None,
        today=date(2026, 8, 17),
        force=True,
    )
    assert skipped.status == "SKIPPED"
    assert skipped.reason == "NO_NEW_CLOSED_DATE"
    assert skipped.feature_start is None
    assert forced.status == "READY"


def test_daily_context_blocks_stale_or_uninitialized_inputs() -> None:
    with pytest.raises(RuntimeError, match="no alcanzan el corte"):
        resolve_daily_pipeline_context(
            source_state(enriched_sales_date=date(2026, 8, 14)),
            requested_business_date=date(2026, 8, 16),
            today=date(2026, 8, 17),
        )
    with pytest.raises(RuntimeError, match="INITIAL_BACKFILL_MANUAL"):
        resolve_daily_pipeline_context(
            source_state(scoped_sales_date=None),
            requested_business_date=date(2026, 8, 16),
            today=date(2026, 8, 17),
            force=True,
        )


def test_daily_context_requires_ready_audited_source_contract() -> None:
    with pytest.raises(RuntimeError, match="contrato auditado.*no esta READY"):
        resolve_daily_pipeline_context(
            source_state(source_sync_status="BLOCKED"),
            requested_business_date=date(2026, 8, 16),
            today=date(2026, 8, 17),
        )
    with pytest.raises(RuntimeError, match="contrato auditado.*no esta READY"):
        resolve_daily_pipeline_context(
            source_state(source_sync_business_date=date(2026, 8, 15)),
            requested_business_date=date(2026, 8, 16),
            today=date(2026, 8, 17),
        )


def test_daily_context_rejects_future_business_date() -> None:
    with pytest.raises(RuntimeError, match="es futura"):
        resolve_daily_pipeline_context(
            source_state(
                raw_sales_date=date(2026, 8, 17),
                enriched_sales_date=date(2026, 8, 17),
                stock_source_date=date(2026, 8, 17),
                branch_stock_date=date(2026, 8, 18),
            ),
            requested_business_date=None,
            today=date(2026, 8, 17),
        )


def test_stage_uuid_is_stable_and_revisioned() -> None:
    first = pipeline_stage_uuid(
        "PDVB",
        date(2026, 8, 16),
        SCOPE_UUID,
        MODEL_UUID,
        CONFIG_UUID,
        "DAILY_PIPELINE_V1",
    )
    repeated = pipeline_stage_uuid(
        "pdvb",
        date(2026, 8, 16),
        SCOPE_UUID,
        MODEL_UUID,
        CONFIG_UUID,
        "daily_pipeline_v1",
    )
    changed = pipeline_stage_uuid(
        "PDVB",
        date(2026, 8, 16),
        SCOPE_UUID,
        MODEL_UUID,
        CONFIG_UUID,
        "DAILY_PIPELINE_V2",
    )
    assert first == repeated
    assert first != changed


def test_operational_stage_revision_includes_effective_stock_date() -> None:
    stock_date = date(2026, 8, 18)
    assert pipeline_stage_revision(
        "PDVB", "DAILY_PIPELINE_V1", stock_date
    ) == "DAILY_PIPELINE_V1"
    assert pipeline_stage_revision(
        "ITEM_LOGISTICS", "DAILY_PIPELINE_V1", stock_date
    ) == "DAILY_PIPELINE_V1"
    assert pipeline_stage_revision(
        "DAILY_DECAS", "DAILY_PIPELINE_V1", stock_date
    ) == "DAILY_PIPELINE_V1:STOCK:2026-08-18"
    assert pipeline_stage_revision(
        "BACKLOG", "DAILY_PIPELINE_V1", stock_date
    ) == "DAILY_PIPELINE_V1:STOCK:2026-08-18"


def published_pdvb_row(**overrides) -> dict:
    values = {
        "calculation_run_uuid": PDVB_RUN_UUID,
        "business_date": date(2026, 8, 16),
        "model_version_uuid": MODEL_UUID,
        "scope_version_uuid": SCOPE_UUID,
        "origin_cd": 41,
        "row_count": 50711,
        "distinct_pair_count": 50711,
        "expected_pair_count": 50711,
        "published_row_count": 50711,
        "published_at_row_count": 50711,
        "publication_batch_count": 1,
        "publication_batch_uuid": PUBLICATION_BATCH_UUID,
        "published_at": datetime(2026, 8, 17, 21, 29, tzinfo=timezone.utc),
    }
    values.update(overrides)
    return values


def test_published_pdvb_barrier_accepts_only_complete_published_scope() -> None:
    result = validate_published_pdvb_run(published_pdvb_row(), PDVB_RUN_UUID)
    assert result.calculation_run_uuid == PDVB_RUN_UUID
    assert result.row_count == 50711
    assert result.publication_batch_uuid == PUBLICATION_BATCH_UUID


@pytest.mark.parametrize(
    ("row", "message"),
    [
        (None, "no esta disponible"),
        (published_pdvb_row(row_count=50710), "no cubre exactamente"),
        (published_pdvb_row(published_row_count=0), "no fue publicada completamente"),
        (published_pdvb_row(publication_batch_count=2), "no fue publicada completamente"),
    ],
)
def test_published_pdvb_barrier_rejects_invalid_inputs(row, message) -> None:
    with pytest.raises(RuntimeError, match=message):
        validate_published_pdvb_run(row, PDVB_RUN_UUID)


def test_open_po_refresh_is_serialized_and_non_concurrent() -> None:
    source = getsource(refresh_open_purchase_orders)
    assert REFRESH_OPEN_PO_SQL == (
        "REFRESH MATERIALIZED VIEW src.mv_base_oc_pendientes"
    )
    assert "pg_advisory_xact_lock" in source
    assert "CONCURRENTLY" not in source


def test_operational_master_consumes_audited_sources_without_refreshing_them() -> None:
    source = getsource(pdd_operational_daily_flow.fn)
    assert "refresh_open_purchase_orders_task" not in source
    assert "resolve_daily_context_task" in source


def test_source_state_is_scope_aware_for_features_and_backlog() -> None:
    source = getsource(read_daily_source_state)
    assert "dm_pdd_venta_diaria" in source
    assert "scope_version_uuid = CAST(:scope_uuid AS uuid)" in source
    assert "pdd_distribution_scope_version" in source
    assert "r.scope_id = '41:BACKLOG'" in source
    assert "audit.pdd_source_sync_run" in source
    assert "source_sync_status" in source


def test_master_deployment_has_daily_2030_argentina_schedule() -> None:
    root = Path(__file__).parents[1]
    config = yaml.safe_load((root / "prefect.yaml").read_text(encoding="utf-8"))
    deployment = next(
        item
        for item in config["deployments"]
        if item["name"] == "PDD_OPERATIONAL_DAILY_MASTER"
    )
    assert deployment["schedules"] == [
        {
            "cron": "30 20 * * *",
            "timezone": "America/Argentina/Buenos_Aires",
            "slug": "pdd-operational-daily-2030-art",
            "active": True,
        }
    ]
    assert deployment["parameters"]["force"] is False
    assert deployment["parameters"]["pipeline_revision"] == "DAILY_PIPELINE_V2"
    assert "business_date" not in deployment["parameters"]


def test_desa_master_deployment_is_isolated_and_manual() -> None:
    root = Path(__file__).parents[1]
    config = yaml.safe_load((root / "prefect.yaml").read_text(encoding="utf-8"))
    deployment = next(
        item
        for item in config["deployments"]
        if item["name"] == "PDD_OPERATIONAL_DAILY_MASTER_DESA"
    )
    assert "schedules" not in deployment
    assert deployment["parameters"]["force"] is False
    assert deployment["parameters"]["pipeline_revision"] == "DAILY_PIPELINE_V2"
    assert deployment["parameters"]["created_by"] == "pdd.daily.orchestrator.desa"
    assert deployment["work_pool"]["work_queue_name"] == "pdd-desa"


def test_desa_daily_publisher_is_isolated_scheduled_and_does_not_recalculate() -> None:
    source = getsource(pdd_operational_publish_desa_flow.fn)
    assert "pdd_features_flow" not in source
    assert "daily_pdvb_task" not in source
    assert "require_published_pdvb_task" in source
    assert "validate_desa_target_task" in source

    root = Path(__file__).parents[1]
    config = yaml.safe_load((root / "prefect.yaml").read_text(encoding="utf-8"))
    deployment = next(
        item
        for item in config["deployments"]
        if item["name"] == "PDD_OPERATIONAL_PUBLISH_DESA_DAILY"
    )
    assert deployment["schedules"] == [
        {
            "cron": "0 21 * * *",
            "timezone": "America/Argentina/Buenos_Aires",
            "slug": "pdd-operational-publish-desa-2100-art",
            "active": True,
        }
    ]
    assert deployment["parameters"]["force"] is False
    assert deployment["parameters"]["pipeline_revision"] == "DAILY_PIPELINE_V2"
    assert "business_date" not in deployment["parameters"]
    assert deployment["work_pool"]["work_queue_name"] == "pdd-desa"


def test_desa_item_logistics_deployment_is_manual_and_isolated() -> None:
    root = Path(__file__).parents[1]
    config = yaml.safe_load((root / "prefect.yaml").read_text(encoding="utf-8"))
    deployment = next(
        item
        for item in config["deployments"]
        if item["name"] == "PDD_PUBLISH_ITEM_LOGISTICS_DESA_MANUAL"
    )
    assert "schedules" not in deployment
    assert deployment["work_pool"]["work_queue_name"] == "pdd-desa"
