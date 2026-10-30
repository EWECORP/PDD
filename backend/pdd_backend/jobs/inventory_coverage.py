"""Read-only Inventory coverage check for a frozen PDD scope."""

from __future__ import annotations

import os
import hashlib
import json
from collections import Counter
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any, Mapping, Sequence
from uuid import UUID

from sqlalchemy import Connection, Engine, text

from ..config import Settings
from ..db import load_sql
from ..scope_rules import scope_exclusion_policy_json
from .daily_decas import _read_inventory_parameters


@dataclass(frozen=True)
class InventoryGapPolicy:
    max_pairs: int = 100
    max_percent: Decimal = Decimal("0.5")

    @classmethod
    def from_env(cls) -> "InventoryGapPolicy":
        try:
            max_pairs = int(os.getenv("PDD_INVENTORY_MAX_EXCLUDED_PAIRS", "100"))
            max_percent = Decimal(
                os.getenv("PDD_INVENTORY_MAX_EXCLUDED_PERCENT", "0.5")
            )
        except (ValueError, InvalidOperation) as exc:
            raise ValueError("Limite de exclusiones Inventory invalido") from exc
        if (
            not max_percent.is_finite()
            or not 0 <= max_pairs <= 100
            or not 0 <= max_percent <= Decimal("0.5")
        ):
            raise ValueError(
                "El limite Inventory no puede superar 100 pares ni 0.5 por ciento"
            )
        return cls(max_pairs, max_percent)

    def allowed(self, scope_pairs: int) -> int:
        return min(self.max_pairs, int(scope_pairs * self.max_percent / 100))


def inventory_issue(row: Mapping[str, Any]) -> str | None:
    for field, reason in (
        ("inventory_product_id", "PRODUCT_MISSING"),
        ("inventory_site_id", "SITE_MISSING"),
        ("inventory_product_site_id", "PRODUCT_SITE_MISSING"),
        ("inventory_replenishment_id", "REPLENISHMENT_MISSING"),
    ):
        if field in row and row[field] is None:
            return reason
    if row.get("inventory_replenishment_active") is False:
        return "REPLENISHMENT_INACTIVE"
    for field in (
        "inventory_product_id", "inventory_site_id", "product_site_id",
        "replenishment_id", "replenishment_row_version", "captured_at",
    ):
        if row.get(field) is None:
            return "ACTIVE_PARAMETER_MISSING"
    for field in ("target_stock_days", "overstock_days"):
        try:
            number = Decimal(str(row[field]))
        except (KeyError, InvalidOperation, TypeError, ValueError):
            return "INVALID_" + field.upper()
        if not number.is_finite() or number < 0:
            return "INVALID_" + field.upper()
    return None


def assess_inventory_coverage(
    rows: Sequence[Mapping[str, Any]], policy: InventoryGapPolicy
) -> dict[str, Any]:
    if not rows:
        raise RuntimeError("El scope no contiene pares para verificar Inventory")
    gaps = [
        {
            "codigo_articulo": int(row["codigo_articulo"]),
            "sucursal": int(row["sucursal"]),
            "reason": reason,
        }
        for row in rows
        if (reason := inventory_issue(row)) is not None
    ]
    gaps.sort(key=lambda row: (row["sucursal"], row["codigo_articulo"]))
    digest = hashlib.sha256()
    for row in sorted(
        rows, key=lambda item: (int(item["sucursal"]), int(item["codigo_articulo"]))
    ):
        values = (
            row["codigo_articulo"], row["sucursal"],
            row.get("product_site_id"), row.get("replenishment_id"),
            row.get("inventory_replenishment_active"),
            row.get("inventory_replenishment_row_version"),
            row.get("target_stock_days"), row.get("overstock_days"),
            row.get("product_site_active"), row.get("active_for_purchase"),
            inventory_issue(row),
        )
        digest.update("|".join(str(value) for value in values).encode("utf-8"))
        digest.update(b"\n")
    allowed = policy.allowed(len(rows))
    return {
        "status": (
            "READY" if not gaps else
            "WARNING_CONTINUE" if len(gaps) <= allowed else "BLOCKED"
        ),
        "scope_pairs": len(rows),
        "covered_pairs": len(rows) - len(gaps),
        "gap_count": len(gaps),
        "allowed_gap_count": allowed,
        "max_excluded_pairs": policy.max_pairs,
        "max_excluded_percent": str(policy.max_percent),
        "reason_counts": dict(sorted(Counter(g["reason"] for g in gaps).items())),
        "coverage_checksum": digest.hexdigest(),
        "gaps": gaps,
    }


def _directed_gaps(
    target: Connection, gaps: Sequence[Mapping[str, Any]], business_date: date
) -> list[dict[str, int]]:
    if not gaps:
        return []
    return [
        dict(row)
        for row in target.execute(
            text(
                """WITH gaps AS (
                       SELECT * FROM jsonb_to_recordset(CAST(:gaps AS jsonb))
                         AS x(codigo_articulo bigint,sucursal integer)
                   )
                   SELECT DISTINCT g.codigo_articulo,g.sucursal
                   FROM gaps g
                   JOIN stock_management.pdd_directed_need_line l
                     ON l.codigo_articulo=g.codigo_articulo
                    AND l.sucursal=g.sucursal
                   JOIN stock_management.pdd_directed_need d
                     ON d.directed_need_id=l.directed_need_id
                   WHERE d.status='ACTIVE' AND d.valid_from<=:business_date
                     AND (d.valid_to IS NULL OR d.valid_to>=:business_date)
                     AND l.open_quantity>0
                   ORDER BY g.sucursal,g.codigo_articulo"""
            ),
            {"gaps": json.dumps(gaps), "business_date": business_date},
        ).mappings()
    ]


def inspect_inventory_coverage(
    source_engine: Engine,
    target_engine: Engine,
    scope_version_uuid: UUID,
    policy: InventoryGapPolicy,
    business_date: date | None = None,
) -> dict[str, Any]:
    with source_engine.connect() as source:
        scope_rows = [
            dict(row)
            for row in source.execute(
                text(
                    """SELECT codigo_articulo, destination_branch AS sucursal
                       FROM datamart.dm_pdd_scope_pair
                       WHERE scope_version_uuid=CAST(:scope AS uuid)
                       ORDER BY destination_branch,codigo_articulo"""
                ),
                {"scope": scope_version_uuid},
            ).mappings()
        ]
    with target_engine.connect() as target:
        rows = _read_inventory_parameters(target, scope_rows)
        result = assess_inventory_coverage(rows, policy)
        directed: list[dict[str, int]] = (
            _directed_gaps(target, result["gaps"], business_date)
            if business_date is not None else []
        )
        result["active_directed_pairs"] = directed
        if directed:
            result["status"] = "BLOCKED"
    return {"scope_version_uuid": str(scope_version_uuid), **result}


def preview_scope_membership(
    source_engine: Engine,
    source_settings: Settings,
    active_scope_uuid: UUID,
 ) -> tuple[list[dict[str, Any]], int, int]:
    """Build live pair membership using the same SQL as snapshot capture.

    Temporary tables are discarded with an explicit rollback; no scope version
    or operational row is written.
    """
    with source_engine.connect().execution_options(
        isolation_level="REPEATABLE READ"
    ) as source:
        transaction = source.begin()
        try:
            source.execute(
                text(load_sql("scope/prepare_scope_snapshot.sql")),
                {
                    "origin_cd": source_settings.origin_cd,
                    "exclusion_policy_json": scope_exclusion_policy_json(),
                },
            )
            candidate_pairs = [
                dict(row)
                for row in source.execute(
                    text(
                        """SELECT codigo_articulo, destination_branch AS sucursal
                           FROM pdd_scope_pairs_snapshot
                           ORDER BY destination_branch,codigo_articulo"""
                    )
                ).mappings()
            ]
            active_pairs = {
                (int(row[0]), int(row[1]))
                for row in source.execute(
                    text(
                        """SELECT codigo_articulo,destination_branch
                           FROM datamart.dm_pdd_scope_pair
                           WHERE scope_version_uuid=CAST(:scope AS uuid)"""
                    ),
                    {"scope": active_scope_uuid},
                )
            }
        finally:
            transaction.rollback()
    candidate_keys = {
        (int(row["codigo_articulo"]), int(row["sucursal"]))
        for row in candidate_pairs
    }
    return (
        candidate_pairs,
        len(candidate_keys - active_pairs),
        len(active_pairs - candidate_keys),
    )


def inspect_candidate_inventory_coverage(
    source_engine: Engine,
    target_engine: Engine,
    source_settings: Settings,
    active_scope_uuid: UUID,
    policy: InventoryGapPolicy,
    business_date: date,
) -> dict[str, Any]:
    candidate_pairs, added_pairs, removed_pairs = preview_scope_membership(
        source_engine, source_settings, active_scope_uuid
    )
    with target_engine.connect() as target:
        result = assess_inventory_coverage(
            _read_inventory_parameters(target, candidate_pairs), policy
        )
        directed = _directed_gaps(target, result["gaps"], business_date)
        result["active_directed_pairs"] = directed
        if directed:
            result["status"] = "BLOCKED"
    return {
        **result,
        "added_pairs": added_pairs,
        "removed_pairs": removed_pairs,
        "business_date": business_date.isoformat(),
    }
