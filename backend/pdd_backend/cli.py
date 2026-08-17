from __future__ import annotations

import argparse
import json
from datetime import date
from decimal import Decimal, InvalidOperation

from .flows.analytical import (
    pdd_backtest_flow,
    pdd_daily_flow,
    pdd_features_flow,
    pdd_initial_backfill_flow,
    pdd_scope_snapshot_flow,
    pdvb_task,
)
from .flows.backtest import pdd_rolling_backtest_flow
from .flows.operational_inputs import (
    pdd_daily_decas_flow,
    pdd_publish_backlog_flow,
    pdd_publish_item_logistics_flow,
    pdd_stock_readiness_flow,
)
from .flows.publisher import pdd_publish_pdvb_flow


def parse_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("La fecha debe usar formato YYYY-MM-DD") from exc


def parse_decimal(value: str) -> Decimal:
    try:
        return Decimal(value)
    except InvalidOperation as exc:
        raise argparse.ArgumentTypeError("El valor debe ser numerico") from exc


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="pdd-etl")
    subparsers = parser.add_subparsers(dest="command", required=True)

    scope = subparsers.add_parser(
        "scope-snapshot",
        help="Congela la membresia de una nueva version de scope",
    )
    scope.add_argument("--scope-version-uuid", required=True)
    scope.add_argument("--version-no", required=True, type=int)
    scope.add_argument("--business-date", required=True, type=parse_date)
    scope.add_argument("--captured-by", required=True)
    scope.add_argument("--supersedes-scope-version-uuid")

    features = subparsers.add_parser("features", help="Carga stock y venta diaria")
    features.add_argument("--start", required=True, type=parse_date)
    features.add_argument("--end", required=True, type=parse_date)
    features.add_argument("--scope-version-uuid")

    backfill = subparsers.add_parser("initial-backfill", help="Carga ventanas y calcula PDVB")
    backfill.add_argument("--business-date", type=parse_date)
    backfill.add_argument("--scope-version-uuid")
    backfill.add_argument("--model-version-uuid")

    daily = subparsers.add_parser("daily", help="Ejecuta el proceso diario")
    daily.add_argument("--business-date", type=parse_date)
    daily.add_argument("--scope-version-uuid")
    daily.add_argument("--model-version-uuid")

    pdvb = subparsers.add_parser("pdvb", help="Calcula PDVB sobre features existentes")
    pdvb.add_argument("--business-date", required=True, type=parse_date)
    pdvb.add_argument("--scope-version-uuid")
    pdvb.add_argument("--model-version-uuid")

    backtest = subparsers.add_parser("backtest", help="Genera observaciones de backtest")
    backtest.add_argument("--from", dest="evaluation_from", required=True, type=parse_date)
    backtest.add_argument("--to", dest="evaluation_to", required=True, type=parse_date)
    backtest.add_argument("--horizon", type=int, default=1)
    backtest.add_argument("--scope-version-uuid")
    backtest.add_argument("--model-version-uuid")

    rolling = subparsers.add_parser(
        "rolling-backtest",
        help="Genera origenes historicos, benchmarks y metricas",
    )
    rolling.add_argument("--origin-from", required=True, type=parse_date)
    rolling.add_argument("--origin-to", required=True, type=parse_date)
    rolling.add_argument("--horizon", type=int, default=1)
    rolling.add_argument("--max-origins", type=int, default=120)
    rolling.add_argument(
        "--mode",
        choices=("POINT_DAILY", "CUMULATIVE"),
        default="POINT_DAILY",
        help="Evalua el dia final o la demanda acumulada desde origen+1",
    )
    rolling.add_argument(
        "--actual-min-coverage",
        type=parse_decimal,
        default=Decimal("0.70"),
    )
    rolling.add_argument(
        "--croston-alpha",
        type=parse_decimal,
        default=Decimal("0.10"),
    )
    rolling.add_argument(
        "--adi-threshold",
        type=parse_decimal,
        default=Decimal("1.32"),
    )
    rolling.add_argument(
        "--cv2-threshold",
        type=parse_decimal,
        default=Decimal("0.49"),
    )
    rolling.add_argument(
        "--sample-percent",
        type=parse_decimal,
        default=Decimal("100"),
        help="Muestra deterministica de articulos en (0,100]",
    )
    rolling.add_argument("--scope-version-uuid")
    rolling.add_argument("--model-version-uuid")

    publish = subparsers.add_parser(
        "publish-pdvb",
        help="Publica una corrida PDVB en stock_management.pdd_*",
    )
    publish.add_argument("--calculation-run-uuid", required=True)
    publish.add_argument("--created-by", required=True)

    logistics = subparsers.add_parser(
        "publish-item-logistics",
        help="Publica datos logisticos del scope en stock_management.pdd_*",
    )
    logistics.add_argument("--business-date", required=True, type=parse_date)
    logistics.add_argument("--created-by", required=True)
    logistics.add_argument("--scope-version-uuid")
    logistics.add_argument("--calculation-run-uuid")

    readiness = subparsers.add_parser(
        "stock-readiness",
        help="Valida fecha, cobertura y calidad de src.base_stock_sucursal",
    )
    readiness.add_argument("--expected-through", required=True, type=parse_date)
    readiness.add_argument("--scope-version-uuid")

    decas = subparsers.add_parser(
        "daily-decas",
        help="Construye posiciones de stock y necesidades automaticas D/S",
    )
    decas.add_argument("--business-date", required=True, type=parse_date)
    decas.add_argument("--pdvb-calculation-run-uuid", required=True)
    decas.add_argument("--logistics-calculation-run-uuid", required=True)
    decas.add_argument("--configuration-version-uuid", required=True)
    decas.add_argument("--created-by", required=True)
    decas.add_argument("--scope-version-uuid")
    decas.add_argument("--calculation-run-uuid")

    backlog = subparsers.add_parser(
        "publish-backlog",
        help="Consolida D/E/C/A/S y publica el backlog operativo vigente",
    )
    backlog.add_argument("--daily-calculation-run-uuid", required=True)
    backlog.add_argument("--created-by", required=True)
    backlog.add_argument("--calculation-run-uuid")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    if args.command == "scope-snapshot":
        result = pdd_scope_snapshot_flow(
            args.scope_version_uuid,
            args.version_no,
            args.business_date,
            args.captured_by,
            args.supersedes_scope_version_uuid,
        )
        print(json.dumps(result, default=str, indent=2, sort_keys=True))
    elif args.command == "features":
        pdd_features_flow(args.start, args.end, args.scope_version_uuid)
    elif args.command == "initial-backfill":
        pdd_initial_backfill_flow(
            args.business_date,
            args.scope_version_uuid,
            args.model_version_uuid,
        )
    elif args.command == "daily":
        pdd_daily_flow(
            args.business_date,
            args.scope_version_uuid,
            args.model_version_uuid,
        )
    elif args.command == "pdvb":
        pdvb_task.fn(
            args.business_date,
            args.scope_version_uuid,
            args.model_version_uuid,
        )
    elif args.command == "backtest":
        pdd_backtest_flow(
            args.evaluation_from,
            args.evaluation_to,
            args.scope_version_uuid,
            args.model_version_uuid,
            args.horizon,
        )
    elif args.command == "rolling-backtest":
        pdd_rolling_backtest_flow(
            args.origin_from,
            args.origin_to,
            args.scope_version_uuid,
            args.model_version_uuid,
            args.horizon,
            args.max_origins,
            args.mode,
            args.actual_min_coverage,
            args.croston_alpha,
            args.adi_threshold,
            args.cv2_threshold,
            args.sample_percent,
        )
    elif args.command == "publish-pdvb":
        result = pdd_publish_pdvb_flow(
            args.calculation_run_uuid,
            args.created_by,
        )
        print(json.dumps(result, default=str, indent=2, sort_keys=True))
    elif args.command == "publish-item-logistics":
        result = pdd_publish_item_logistics_flow(
            args.business_date,
            args.created_by,
            args.scope_version_uuid,
            args.calculation_run_uuid,
        )
        print(json.dumps(result, default=str, indent=2, sort_keys=True))
    elif args.command == "stock-readiness":
        result = pdd_stock_readiness_flow(
            args.expected_through,
            args.scope_version_uuid,
        )
        print(json.dumps(result, default=str, indent=2, sort_keys=True))
    elif args.command == "daily-decas":
        result = pdd_daily_decas_flow(
            args.business_date,
            args.pdvb_calculation_run_uuid,
            args.logistics_calculation_run_uuid,
            args.configuration_version_uuid,
            args.created_by,
            args.scope_version_uuid,
            args.calculation_run_uuid,
        )
        print(json.dumps(result, default=str, indent=2, sort_keys=True))
    elif args.command == "publish-backlog":
        result = pdd_publish_backlog_flow(
            args.daily_calculation_run_uuid,
            args.created_by,
            args.calculation_run_uuid,
        )
        print(json.dumps(result, default=str, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
