from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


LOADER_PATH = (
    Path(__file__).resolve().parents[2]
    / "cargas_inventory"
    / "load_environment.py"
)
SPEC = importlib.util.spec_from_file_location("pdd_inventory_loader", LOADER_PATH)
assert SPEC is not None and SPEC.loader is not None
loader = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(loader)


def test_prod_requires_allow_and_exact_confirmation() -> None:
    with pytest.raises(RuntimeError, match="ALLOW_PRODUCTION"):
        loader._production_guard(
            {"PDD_OPERATIONAL_TARGET_ENV": "PROD"},
            "PROD",
            "connexa_platform_ms",
        )
    with pytest.raises(RuntimeError, match="confirm-production"):
        loader._production_guard(
            {
                "PDD_OPERATIONAL_TARGET_ENV": "PROD",
                "PDD_OPERATIONAL_ALLOW_PRODUCTION": "true",
            },
            "PROD",
            None,
        )


def test_prod_accepts_explicit_guard() -> None:
    loader._production_guard(
        {
            "PDD_OPERATIONAL_TARGET_ENV": "PROD",
            "PDD_OPERATIONAL_ALLOW_PRODUCTION": "true",
        },
        "PROD",
        "connexa_platform_ms",
    )


def test_requested_environment_must_match_configuration() -> None:
    with pytest.raises(RuntimeError, match="Configured target environment"):
        loader._production_guard(
            {"PDD_OPERATIONAL_TARGET_ENV": "TEST"},
            "PROD",
            "connexa_platform_ms",
        )
