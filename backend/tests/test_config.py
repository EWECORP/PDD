from datetime import date
from decimal import Decimal
from uuid import UUID

import pytest

from pdd_backend.config import OperationalSettings, Settings
from pdd_backend.jobs.publisher import estimate_checksum
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
    monkeypatch.setenv("PDD_OPERATIONAL_PG_HOST", "postgres")
    monkeypatch.setenv("PDD_OPERATIONAL_PG_DB", "connexa_platform_test")
    monkeypatch.setenv("PDD_OPERATIONAL_PG_USER", "pdd")
    monkeypatch.setenv("PDD_OPERATIONAL_PG_PASSWORD", "secret")
    monkeypatch.delenv("PDD_OPERATIONAL_ALLOW_PRODUCTION", raising=False)
    settings = OperationalSettings.from_env()
    assert settings.pg_database == "connexa_platform_test"

    monkeypatch.setenv("PDD_OPERATIONAL_PG_DB", "connexa_platform_ms")
    with pytest.raises(RuntimeError, match="solo admite connexa_platform_test"):
        OperationalSettings.from_env()


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
