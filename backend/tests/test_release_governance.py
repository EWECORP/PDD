from inspect import getsource
from uuid import UUID

from pdd_backend.jobs.daily_decas import _ensure_configuration
from pdd_backend.jobs.publisher import _ensure_model, _ensure_scope
from pdd_backend.model_registry import load_model_version
from pdd_backend.operational_registry import load_operational_configuration


MODEL_UUID = UUID("a0a35b25-628d-43f1-b651-82c97207fc60")
PROD_CONFIGURATION_UUID = UUID("3e5bd515-8642-4eb7-8058-844c67beb408")


def test_prod_model_is_approved_and_audited() -> None:
    model = load_model_version(MODEL_UUID)

    assert model.status == "APPROVED"
    assert model.valid_from.isoformat() == "2026-09-23"
    assert model.approved_by == "eduardo.ettlin"


def test_prod_configuration_is_distinct_approved_and_uses_inventory() -> None:
    configuration = load_operational_configuration(PROD_CONFIGURATION_UUID)

    assert configuration.configuration_code == "PDD_DAILY_DECAS_PROD"
    assert configuration.status == "APPROVED"
    assert configuration.approved_by == "eduardo.ettlin"
    assert configuration.parameters["environment"] == "PROD"
    assert configuration.parameters["target_stock_days"]["source"].startswith(
        "inventory."
    )


def test_approved_operational_records_include_approval_metadata() -> None:
    model_source = getsource(_ensure_model)
    configuration_source = getsource(_ensure_configuration)
    scope_source = getsource(_ensure_scope)

    assert "approved_at, approved_by" in model_source
    assert "clock_timestamp()" in model_source
    assert "stored_model.status = 'DRAFT'" in model_source
    assert "stored_model.parameters = EXCLUDED.parameters" in model_source
    assert "approved_at, approved_by" in configuration_source
    assert "clock_timestamp()" in configuration_source
    assert "approval.approved_at/approved_by" in scope_source
