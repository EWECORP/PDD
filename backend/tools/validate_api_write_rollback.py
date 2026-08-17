from __future__ import annotations

import json
from contextlib import contextmanager
from datetime import date, timedelta
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import text

import pdd_backend.api.repository as repository_module
from pdd_backend.api.models import DirectedNeedCreate, DirectedNeedReplace
from pdd_backend.api.repository import PddRepository
from pdd_backend.config import OperationalSettings
from pdd_backend.db import build_api_engine


def main() -> None:
    settings = OperationalSettings.from_env()
    engine = build_api_engine(settings)
    repository = PddRepository(engine, settings)
    token = uuid4().hex
    reference = f"API-ROLLBACK-{token[:20]}"
    close_reference = f"API-CLOSE-{token[:23]}"
    actor = "pdd.api.rollback"
    correlation = uuid4()

    with engine.connect() as connection:
        transaction = connection.begin()

        @contextmanager
        def shared_connection(*args, **kwargs):
            yield connection

        original_context = repository_module.transactional_connection
        repository_module.transactional_connection = shared_connection
        try:
            pair = connection.execute(
                text(
                    """
                    SELECT p.destination_branch,p.codigo_articulo
                    FROM stock_management.pdd_calculation_run r
                    JOIN stock_management.pdd_distribution_scope_pair p
                      ON p.scope_version_id=r.scope_version_id
                    WHERE r.run_type='PUBLISH' AND r.scope_id='41:BACKLOG'
                      AND r.status='SUCCEEDED' AND r.is_current
                    ORDER BY p.destination_branch,p.codigo_articulo LIMIT 1
                    """
                )
            ).mappings().one()
            today = date.today()
            create = DirectedNeedCreate.model_validate(
                {
                    "needType": "E",
                    "businessReference": reference,
                    "validFrom": today.isoformat(),
                    "validTo": (today + timedelta(days=7)).isoformat(),
                    "priorityScore": "100",
                    "ownerUser": actor,
                    "reason": "Validacion transaccional con rollback",
                    "lines": [
                        {
                            "branchId": pair["destination_branch"],
                            "articleId": pair["codigo_articulo"],
                            "originalQuantity": "12",
                            "unitCode": "UN",
                        }
                    ],
                }
            )
            created, replay = repository.create_directed(
                create, actor, f"rollback-{token}", correlation
            )
            if replay or created["status"] != "DRAFT" or created["versionNo"] != 1:
                raise RuntimeError("Alta DRAFT inesperada")
            replayed, replay = repository.create_directed(
                create, actor, f"rollback-{token}", correlation
            )
            if not replay or replayed["directedNeedUuid"] != created["directedNeedUuid"]:
                raise RuntimeError("Replay idempotente inesperado")

            replace = DirectedNeedReplace.model_validate(
                {
                    **create.model_dump(by_alias=True, mode="json"),
                    "priorityScore": "110",
                    "changeReason": "Ajuste durante validacion rollback",
                }
            )
            directed_uuid = created["directedNeedUuid"]
            edited = repository.replace_directed(
                directed_uuid, 1, replace, actor, uuid4()
            )
            active = repository.transition_directed(
                directed_uuid, 2, "activate", "Aprobacion rollback", actor, uuid4()
            )
            cancelled = repository.transition_directed(
                directed_uuid, 3, "cancel", "Cancelacion rollback", actor, uuid4()
            )
            versions = repository.directed_versions(directed_uuid)
            event_count = connection.execute(
                text(
                    """
                    SELECT count(*) FROM stock_management.pdd_business_event_log
                    WHERE entity_type='DIRECTED_NEED' AND entity_id=:entity
                    """
                ),
                {"entity": str(directed_uuid)},
            ).scalar_one()
            if (
                edited["versionNo"] != 2
                or active["status"] != "ACTIVE"
                or cancelled["status"] != "CANCELLED"
                or len(versions) != 4
                or event_count != 4
                or cancelled["lines"][0]["openQuantity"] != Decimal("0")
            ):
                raise RuntimeError("Ciclo E/C/A inconsistente")

            close_create = DirectedNeedCreate.model_validate(
                {
                    **create.model_dump(by_alias=True, mode="json"),
                    "businessReference": close_reference,
                    "needType": "C",
                }
            )
            close_draft, _ = repository.create_directed(
                close_create, actor, f"rollback-close-{token}", uuid4()
            )
            close_uuid = close_draft["directedNeedUuid"]
            repository.transition_directed(
                close_uuid, 1, "activate", "Aprobacion cierre rollback", actor, uuid4()
            )
            closed = repository.transition_directed(
                close_uuid, 2, "close", "Cierre autorizado rollback", actor, uuid4()
            )
            close_versions = repository.directed_versions(close_uuid)
            if (
                closed["status"] != "CLOSED"
                or closed["versionNo"] != 3
                or closed["lines"][0]["openQuantity"] != Decimal("0")
                or len(close_versions) != 3
            ):
                raise RuntimeError("Cierre dirigido inconsistente")
            output = {
                "status": "OK_ROLLBACK",
                "reference": reference,
                "created_version": created["versionNo"],
                "edited_version": edited["versionNo"],
                "active_version": active["versionNo"],
                "cancelled_version": cancelled["versionNo"],
                "history_rows": len(versions),
                "business_events": event_count,
                "idempotent_replay": replay,
                "closed_version": closed["versionNo"],
                "close_history_rows": len(close_versions),
            }
        finally:
            repository_module.transactional_connection = original_context
            transaction.rollback()

    with engine.connect() as verification:
        persisted = verification.execute(
            text(
                """
                SELECT count(*) FROM stock_management.pdd_directed_need
                WHERE business_reference=ANY(CAST(:references AS text[]))
                """
            ),
            {"references": [reference, close_reference]},
        ).scalar_one()
    if persisted:
        raise RuntimeError("La prueba rollback dejo datos persistidos")
    output["persisted_rows"] = persisted
    print(json.dumps(output, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
