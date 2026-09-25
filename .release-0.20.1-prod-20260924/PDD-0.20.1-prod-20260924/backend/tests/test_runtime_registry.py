from datetime import date, datetime, timezone
from inspect import getsource
from uuid import UUID

import pytest

from pdd_backend.runtime_registry import (
    RuntimeBinding,
    activate_runtime_binding,
    normalize_process_code,
    normalize_runtime_environment,
    resolve_runtime_selection,
)


SCOPE_UUID = UUID("c533e7e7-3363-4dc3-8127-24f48fe33522")
MODEL_UUID = UUID("a0a35b25-628d-43f1-b651-82c97207fc60")
CONFIG_UUID = UUID("2f916828-c59d-4190-a795-29ac5cfc1a66")


def binding() -> RuntimeBinding:
    return RuntimeBinding(
        runtime_binding_uuid=UUID("11111111-1111-1111-1111-111111111111"),
        environment="TEST",
        process_code="DAILY_MASTER",
        revision_no=2,
        scope_version_uuid=SCOPE_UUID,
        model_version_uuid=MODEL_UUID,
        configuration_version_uuid=CONFIG_UUID,
        pipeline_revision="DAILY_PIPELINE_V3",
        effective_business_date=date(2026, 9, 23),
        status="ACTIVE",
        activated_at=datetime(2026, 9, 23, 12, tzinfo=timezone.utc),
        activated_by="test.user",
        reason="test",
        supersedes_runtime_binding_uuid=None,
        detail={},
    )


def test_runtime_selector_uses_active_binding(monkeypatch) -> None:
    monkeypatch.setattr(
        "pdd_backend.runtime_registry.read_active_runtime_binding",
        lambda connection, environment, process_code: binding(),
    )

    selected = resolve_runtime_selection(object(), "test", "daily_master")

    assert selected.scope_version_uuid == SCOPE_UUID
    assert selected.model_version_uuid == MODEL_UUID
    assert selected.configuration_version_uuid == CONFIG_UUID
    assert selected.pipeline_revision == "DAILY_PIPELINE_V3"
    assert selected.source == "RUNTIME_BINDING"
    assert selected.revision_no == 2
    assert selected.effective_business_date == date(2026, 9, 23)
    assert selected.serializable()["effective_business_date"] == "2026-09-23"


def test_explicit_runtime_values_override_binding(monkeypatch) -> None:
    alternate = UUID("22222222-2222-2222-2222-222222222222")
    monkeypatch.setattr(
        "pdd_backend.runtime_registry.read_active_runtime_binding",
        lambda connection, environment, process_code: binding(),
    )

    selected = resolve_runtime_selection(
        object(),
        "TEST",
        "DAILY_MASTER",
        explicit_scope_uuid=alternate,
        explicit_pipeline_revision="daily_pipeline_v4",
    )

    assert selected.scope_version_uuid == alternate
    assert selected.model_version_uuid == MODEL_UUID
    assert selected.pipeline_revision == "DAILY_PIPELINE_V4"
    assert selected.source == "EXPLICIT_OVERRIDE"
    assert selected.effective_business_date is None


def test_runtime_selector_keeps_legacy_env_as_migration_fallback(monkeypatch) -> None:
    monkeypatch.setattr(
        "pdd_backend.runtime_registry.read_active_runtime_binding",
        lambda connection, environment, process_code: None,
    )

    selected = resolve_runtime_selection(
        object(),
        "TEST",
        "DAILY_MASTER",
        legacy_scope_uuid=SCOPE_UUID,
        legacy_model_uuid=MODEL_UUID,
        default_configuration_uuid=CONFIG_UUID,
        default_pipeline_revision="DAILY_PIPELINE_V3",
    )

    assert selected.source == "LEGACY_ENV"


def test_runtime_names_are_strictly_normalized() -> None:
    assert normalize_runtime_environment(" test ") == "TEST"
    assert normalize_process_code(" daily_master ") == "DAILY_MASTER"
    with pytest.raises(ValueError):
        normalize_runtime_environment("QA")
    with pytest.raises(ValueError):
        normalize_process_code("daily-master")


def test_activation_is_transactional_validated_and_audited() -> None:
    source = getsource(activate_runtime_binding)
    assert "_validate_runtime_candidate" in source
    assert "pg_advisory_xact_lock" in source
    assert "status='SUPERSEDED'" in source
    assert "INSERT INTO audit.pdd_runtime_binding" in source
    assert "activated_by" in source
    assert "reason" in source
