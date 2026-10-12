from __future__ import annotations

from prefect import flow

from pdd_backend.config import Settings
from pdd_backend.db import build_engine
from pdd_backend.jobs.backtest_retention import purge_backtest_detail


@flow(name="PDD - Depurar detalle de backtest", log_prints=True)
def pdd_backtest_retention_flow() -> dict:
    settings = Settings.from_env()
    engine = build_engine(settings)
    try:
        result = purge_backtest_detail(engine, settings)
    finally:
        engine.dispose()
    print(f"Detalle backtest depurado: {result}")
    return result
