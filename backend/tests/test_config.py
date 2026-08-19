from datetime import date
from decimal import Decimal
from uuid import UUID

import pytest

from pdd_backend.config import OperationalSettings, Settings
from pdd_backend.jobs.publisher import (
    estimate_checksum,
    resolve_publication_batch_uuid,
)
from pdd_backend.model_registry import load_model_version


MODEL_UUID = "a0a35b25-628d-43f1-b651-82c97207fc60"


def test_operational_safety_defaults() -> None:
    settings = Settings(
        pg_host="postgres",
        pg_port=5432,
        pg_database="diarco_data",
        pg_user="pdd",
        pg_password="secret",
    )
    assert settings.statement_timeout_ms == 1_800_000
    assert settings.keepalives_idle_seconds == 60
    assert settings.keepalives_interval_seconds == 30
    assert settings.keepalives_count == 5


def test_operational_target_defaults_to_test_only(monkeypatch) -> None:
    # Unit-test the class default without reloading the worker's TEST/DESA
    # dotenv file through PDD_ENV_PATH.
    monkeypatch.setattr("pdd_backend.config.load_environment", lambda: None)
    monkeypatch.setenv("PDD_OPERATIONAL_PG_HOST", "postgres")
    monkeypatch.setenv("PDD_OPERATIONAL_PG_DB", "connexa_platform_test")
    monkeypatch.setenv("PDD_OPERATIONAL_PG_USER", "pdd")
    monkeypatch.setenv("PDD_OPERATIONAL_PG_PASSWORD", "secret")
    monkeypatch.delenv("PDD_OPERATIONAL_TARGET_ENV", raising=False)
    monkeypatch.delenv("PDD_OPERATIONAL_ALLOW_PRODUCTION", raising=False)
    settings = OperationalSettings.from_env()
    assert settings.pg_database == "connexa_platform_test"
    assert settings.target_environment == "TEST"

    monkeypatch.setenv("PDD_OPERATIONAL_PG_DB", "connexa_platform_ms")
    with pytest.raises(RuntimeError, match="Destino operativo inconsistente"):
        OperationalSettings.from_env()


def test_operational_target_accepts_explicit_desa(monkeypatch) -> None:
    monkeypatch.setenv("PDD_OPERATIONAL_PG_HOST", "186.158.182.122")
    monkeypatch.setenv("PDD_OPERATIONAL_PG_DB", "connexa_platform_diarco")
    monkeypatch.setenv("PDD_OPERATIONAL_PG_USER", "connexa_platform_user")
    monkeypatch.setenv("PDD_OPERATIONAL_PG_PASSWORD", "secret")
    monkeypatch.setenv("PDD_OPERATIONAL_TARGET_ENV", "DESA")
    monkeypatch.delenv("PDD_OPERATIONAL_ALLOW_PRODUCTION", raising=False)

    settings = OperationalSettings.from_env()

    assert settings.target_environment == "DESA"
    assert settings.pg_database == "connexa_platform_diarco"


def test_operational_target_rejects_desa_with_production_database(monkeypatch) -> None:
    monkeypatch.setenv("PDD_OPERATIONAL_PG_HOST", "186.158.182.122")
    monkeypatch.setenv("PDD_OPERATIONAL_PG_DB", "connexa_platform_ms")
    monkeypatch.setenv("PDD_OPERATIONAL_PG_USER", "connexa_platform_user")
    monkeypatch.setenv("PDD_OPERATIONAL_PG_PASSWORD", "secret")
    monkeypatch.setenv("PDD_OPERATIONAL_TARGET_ENV", "DESA")

    with pytest.raises(RuntimeError, match="requiere PDD_OPERATIONAL_PG_DB"):
        OperationalSettings.from_env()


def test_operational_target_requires_explicit_production_opt_in(monkeypatch) -> None:
    monkeypatch.setenv("PDD_OPERATIONAL_PG_HOST", "postgres")
    monkeypatch.setenv("PDD_OPERATIONAL_PG_DB", "connexa_platform_ms")
    monkeypatch.setenv("PDD_OPERATIONAL_PG_USER", "pdd")
    monkeypatch.setenv("PDD_OPERATIONAL_PG_PASSWORD", "secret")
    monkeypatch.setenv("PDD_OPERATIONAL_TARGET_ENV", "PROD")
    monkeypatch.delenv("PDD_OPERATIONAL_ALLOW_PRODUCTION", raising=False)

    with pytest.raises(RuntimeError, match="Produccion requiere"):
        OperationalSettings.from_env()

    monkeypatch.setenv("PDD_OPERATIONAL_ALLOW_PRODUCTION", "true")
    settings = OperationalSettings.from_env()
    assert settings.target_environment == "PROD"


def test_model_registry_and_checksum_are_reproducible() -> None:
    manifest = load_model_version(UUID(MODEL_UUID))
    assert manifest.model_code == "PDVB_CD41"
    assert manifest.version_no == 3
    rows = [
        {
            "business_date": date(2026, 8, 12),
            "analytical_detail_id": 1,
            "model_version_uuid": UUID(MODEL_UUID),
            "scope_version_uuid": UUID("90dcd987-2ad6-4e4e-8d19-2ead45775d1f"),
            "origin_cd": 41,
            "codigo_articulo": 100,
            "sucursal": 1,
            "c_proveedor_primario": None,
            "method_code": "SKU_BRANCH_WEIGHTED",
            "fallback_level": 0,
            "status": "OK",
            "confidence_score": Decimal("95.00"),
            "pdvb_value": Decimal("2.500000"),
            "input_checksum": "abc",
        }
    ]
    assert estimate_checksum(rows) == estimate_checksum(rows)


def test_publication_batch_uuid_is_stable_and_reuses_source_lineage() -> None:
    calculation_run_uuid = UUID("34aa9ca9-8ab1-40ad-ab62-2ba1cd25ba77")
    existing_batch_uuid = UUID("42183719-db6f-4aaa-9750-bdfa97b3f2b4")

    generated = resolve_publication_batch_uuid(calculation_run_uuid, None)

    assert generated == resolve_publication_batch_uuid(calculation_run_uuid, None)
    assert (
        resolve_publication_batch_uuid(calculation_run_uuid, existing_batch_uuid)
        == existing_batch_uuid
    )
