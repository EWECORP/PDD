from __future__ import annotations

import argparse
from datetime import date

from .flows.analytical import (
    pdd_backtest_flow,
    pdd_daily_flow,
    pdd_features_flow,
    pdd_initial_backfill_flow,
    pdvb_task,
)


def parse_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("La fecha debe usar formato YYYY-MM-DD") from exc


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="pdd-etl")
    subparsers = parser.add_subparsers(dest="command", required=True)

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
    return parser


def main() -> None:
    args = build_parser().parse_args()
    if args.command == "features":
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


if __name__ == "__main__":
    main()

