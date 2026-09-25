from datetime import date
from decimal import Decimal
from pathlib import Path
from uuid import UUID

import pytest
import yaml

from pdd_backend.config import OperationalSettings
from pdd_backend.jobs.simulation import (
    _validate_environment,
    allocate_simulation_pairs,
    build_simulated_line_specs,
    normalize_batch_code,
    simulation_backlog_run_uuid,
)


def _candidates(count: int) -> list[dict]:
    return [
        {
            "sucursal": 1 + index % 3,
            "codigo_articulo": 10_000 + index,
            "c_proveedor_primario": 500 + index,
            "units_per_package": Decimal("6"),
            "packages_per_pallet": Decimal("20"),
            "unit_weight_kg": Decimal("1.5"),
            "unit_volume_m3": None,
        }
        for index in range(count)
    ]


def test_simulation_allocates_shared_and_exclusive_pairs() -> None:
    allocated = allocate_simulation_pairs(
        _candidates(14),
        lines_per_type=6,
        shared_pairs=2,
    )

    assert set(allocated) == {"E", "C", "A"}
    assert all(len(lines) == 6 for lines in allocated.values())
    shared = {
        (row["sucursal"], row["codigo_articulo"])
        for row in allocated["E"][:2]
    }
    assert shared == {
        (row["sucursal"], row["codigo_articulo"])
        for need_type in ("C", "A")
        for row in allocated[need_type][:2]
    }
    exclusive_sets = [
        {
            (row["sucursal"], row["codigo_articulo"])
            for row in allocated[need_type][2:]
        }
        for need_type in ("E", "C", "A")
    ]
    assert exclusive_sets[0].isdisjoint(exclusive_sets[1])
    assert exclusive_sets[0].isdisjoint(exclusive_sets[2])
    assert exclusive_sets[1].isdisjoint(exclusive_sets[2])


def test_simulated_lines_cover_open_and_partial_balances() -> None:
    allocated = allocate_simulation_pairs(
        _candidates(14),
        lines_per_type=6,
        shared_pairs=2,
    )
    lines = build_simulated_line_specs(allocated, date(2026, 8, 18))

    for need_type in ("E", "C", "A"):
        assert lines[need_type][0]["status"] == "PARTIAL"
        assert lines[need_type][1]["status"] == "OPEN"
        assert all(
            row["open_quantity"]
            == row["original_quantity"]
            - row["prepared_allocated_quantity"]
            - row["cancelled_quantity"]
            for row in lines[need_type]
        )


def test_simulation_identifier_is_normalized_and_idempotent() -> None:
    daily_uuid = UUID("15126e90-676d-513c-933a-078e32bb3d33")
    first = simulation_backlog_run_uuid(
        "DESA",
        "connexa_platform_diarco",
        daily_uuid,
        "frontend_01",
    )
    second = simulation_backlog_run_uuid(
        "DESA",
        "connexa_platform_diarco",
        daily_uuid,
        "FRONTEND_01",
    )

    assert normalize_batch_code(" frontend_01 ") == "FRONTEND_01"
    assert first == second
    with pytest.raises(ValueError, match="batch_code"):
        normalize_batch_code("lote con espacios")


def test_simulation_rejects_non_desa_targets() -> None:
    settings = OperationalSettings(
        pg_host="postgres",
        pg_port=5432,
        pg_database="connexa_platform_test",
        pg_user="pdd",
        pg_password="secret",
        target_environment="TEST",
    )
    with pytest.raises(RuntimeError, match="solo esta habilitada.*DESA"):
        _validate_environment(settings)


def test_simulation_deployment_is_manual_and_uses_desa_queue() -> None:
    root = Path(__file__).parents[1]
    config = yaml.safe_load((root / "prefect.yaml").read_text(encoding="utf-8"))
    deployment = next(
        item
        for item in config["deployments"]
        if item["name"] == "PDD_SIMULATE_ECA_DESA_MANUAL"
    )

    assert "schedules" not in deployment
    assert deployment["work_pool"]["work_queue_name"] == "pdd-desa"
    assert deployment["parameters"]["lines_per_type"] == 6
    assert deployment["parameters"]["shared_pairs"] == 2
