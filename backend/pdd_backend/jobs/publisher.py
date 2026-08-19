from __future__ import annotations

import hashlib
import json
from collections import Counter
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from typing import Any, Iterable, Mapping, Sequence
from uuid import NAMESPACE_URL, UUID, uuid5

from sqlalchemy import Engine, text
from sqlalchemy.engine import Connection

from ..config import OperationalSettings, Settings
from ..db import transactional_connection
from ..model_registry import ModelVersionManifest, load_model_version


@dataclass(frozen=True)
class PublicationResult:
    calculation_run_uuid: UUID
    publication_batch_uuid: UUID
    business_date: date
    source_rows: int
    published_rows: int
    current_rows: int
    blocked_rows: int
    source_checksum: str
    target_database: str
    reused_publication: bool = False

    def serializable(self) -> dict[str, Any]:
        return {
            **self.__dict__,
            "calculation_run_uuid": str(self.calculation_run_uuid),
            "publication_batch_uuid": str(self.publication_batch_uuid),
            "business_date": self.business_date.isoformat(),
        }


ESTIMATE_COLUMNS = (
    "business_date",
    "analytical_detail_id",
    "model_version_uuid",
    "scope_version_uuid",
    "origin_cd",
    "codigo_articulo",
    "sucursal",
    "c_proveedor_primario",
    "method_code",
    "fallback_level",
    "status",
    "confidence_score",
    "pdvb_value",
    "input_checksum",
)


def _json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def _canonical_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Decimal):
        return format(value, "f")
    return str(value)


def estimate_checksum(rows: Iterable[Mapping[str, Any]]) -> str:
    digest = hashlib.sha256()
    for row in rows:
        line = "|".join(_canonical_value(row[column]) for column in ESTIMATE_COLUMNS)
        digest.update(line.encode("utf-8"))
        digest.update(b"\n")
    return digest.hexdigest()


def _chunks(rows: Sequence[Mapping[str, Any]], size: int = 2_000):
    for start in range(0, len(rows), size):
        yield rows[start : start + size]


def _read_source_scope(connection: Connection, scope_version_uuid: UUID) -> dict[str, Any]:
    scope = connection.execute(
        text(
            """
            SELECT *
            FROM datamart.dm_pdd_scope_version
            WHERE scope_version_uuid = :scope_version_uuid
            """
        ),
        {"scope_version_uuid": scope_version_uuid},
    ).mappings().one_or_none()
    if scope is None:
        raise RuntimeError(f"Scope analitico inexistente: {scope_version_uuid}")
    return dict(scope)


def _read_source_membership(
    connection: Connection,
    scope_version_uuid: UUID,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    articles = [
        dict(row)
        for row in connection.execute(
            text(
                """
                SELECT codigo_articulo, c_proveedor_primario,
                       cd_active_for_purchase, cd_habilitado,
                       cd_active_for_sale, cd_active_on_mix, source_row_hash
                FROM datamart.dm_pdd_scope_article
                WHERE scope_version_uuid = :scope_version_uuid
                ORDER BY codigo_articulo
                """
            ),
            {"scope_version_uuid": scope_version_uuid},
        ).mappings()
    ]
    pairs = [
        dict(row)
        for row in connection.execute(
            text(
                """
                SELECT origin_cd, destination_branch, codigo_articulo,
                       c_proveedor_primario, route_code, supply_mode,
                       branch_habilitado, branch_active_for_sale,
                       branch_active_on_mix, source_row_hash
                FROM datamart.dm_pdd_scope_pair
                WHERE scope_version_uuid = :scope_version_uuid
                ORDER BY destination_branch, codigo_articulo
                """
            ),
            {"scope_version_uuid": scope_version_uuid},
        ).mappings()
    ]
    return articles, pairs


def _read_source_estimates(
    connection: Connection,
    calculation_run_uuid: UUID,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    header = connection.execute(
        text(
            """
            SELECT business_date, model_version_uuid, scope_version_uuid, origin_cd,
                   count(*)::bigint AS row_count,
                   min(created_at) AS started_at,
                   max(created_at) AS finished_at,
                   count(DISTINCT publication_batch_uuid)::integer
                       AS publication_batch_count,
                   min(publication_batch_uuid::text)::uuid
                       AS publication_batch_uuid,
                   count(*) FILTER (
                       WHERE publication_batch_uuid IS NOT NULL
                   )::bigint AS published_row_count,
                   count(*) FILTER (
                       WHERE published_at IS NOT NULL
                   )::bigint AS published_at_row_count
            FROM datamart.dm_pdd_pdvb_estimate_detail
            WHERE calculation_run_uuid = :calculation_run_uuid
            GROUP BY business_date, model_version_uuid, scope_version_uuid, origin_cd
            """
        ),
        {"calculation_run_uuid": calculation_run_uuid},
    ).mappings().all()
    if len(header) != 1:
        raise RuntimeError(
            f"La corrida {calculation_run_uuid} debe identificar un unico snapshot; "
            f"grupos encontrados={len(header)}"
        )
    source_header = dict(header[0])
    published_rows = source_header["published_row_count"]
    published_at_rows = source_header["published_at_row_count"]
    if source_header["publication_batch_count"] > 1 or published_rows not in (
        0,
        source_header["row_count"],
    ):
        raise RuntimeError("El linaje de publicacion de la corrida esta fragmentado")
    if published_rows != published_at_rows:
        raise RuntimeError("El linaje de publicacion de la corrida esta incompleto")
    rows = [
        dict(row)
        for row in connection.execute(
            text(
                """
                SELECT business_date,
                       pdvb_detail_id AS analytical_detail_id,
                       model_version_uuid, scope_version_uuid, origin_cd,
                       codigo_articulo, sucursal, c_proveedor_primario,
                       method_code, fallback_level, status, confidence_score,
                       pdvb_value, input_checksum,
                       explanation AS explanation_summary
                FROM datamart.dm_pdd_pdvb_estimate_detail
                WHERE calculation_run_uuid = :calculation_run_uuid
                ORDER BY sucursal, codigo_articulo
                """
            ),
            {"calculation_run_uuid": calculation_run_uuid},
        ).mappings()
    ]
    return source_header, rows


def resolve_publication_batch_uuid(
    calculation_run_uuid: UUID,
    source_publication_batch_uuid: UUID | None,
) -> UUID:
    """Devuelve un identificador estable y compartible entre ambientes destino."""
    if source_publication_batch_uuid is not None:
        return UUID(str(source_publication_batch_uuid))
    return uuid5(NAMESPACE_URL, f"connexa:pdd:pdvb:{calculation_run_uuid}")


def _ensure_target_contract(connection: Connection) -> None:
    missing = connection.execute(
        text(
            """
            SELECT array_remove(ARRAY[
                CASE WHEN to_regclass('stock_management.pdd_pdvb_model_version') IS NULL
                     THEN 'pdvb_model_version' END,
                CASE WHEN to_regclass('stock_management.pdd_distribution_scope_version') IS NULL
                     THEN 'distribution_scope_version' END,
                CASE WHEN to_regclass('stock_management.pdd_distribution_scope_article') IS NULL
                     THEN 'distribution_scope_article' END,
                CASE WHEN to_regclass('stock_management.pdd_distribution_scope_pair') IS NULL
                     THEN 'distribution_scope_pair' END,
                CASE WHEN to_regclass('stock_management.pdd_calculation_run') IS NULL
                     THEN 'calculation_run' END,
                CASE WHEN to_regclass('stock_management.pdd_pdvb_publication_batch') IS NULL
                     THEN 'pdvb_publication_batch' END,
                CASE WHEN to_regclass('stock_management.pdd_pdvb_publication_stage') IS NULL
                     THEN 'pdvb_publication_stage' END,
                CASE WHEN to_regclass('stock_management.pdd_pdvb_estimate') IS NULL
                     THEN 'pdvb_estimate' END,
                CASE WHEN to_regclass('stock_management.pdd_pdvb_current') IS NULL
                     THEN 'pdvb_current' END,
                CASE WHEN to_regclass('stock_management.pdd_pdvb_quality_issue') IS NULL
                     THEN 'pdvb_quality_issue' END
            ], NULL) AS missing
            """
        )
    ).scalar_one()
    if missing:
        raise RuntimeError(
            "Contrato stock_management incompleto; faltan: " + ", ".join(missing)
        )


def _ensure_model(
    connection: Connection,
    manifest: ModelVersionManifest,
    created_by: str,
) -> int:
    connection.execute(
        text(
            """
            INSERT INTO stock_management.pdd_pdvb_model_version (
                model_version_uuid, model_code, version_no, status,
                parameters, implementation_sha256, code_commit_sha, created_by
            ) VALUES (
                :model_version_uuid, :model_code, :version_no, :status,
                CAST(:parameters AS jsonb), :implementation_sha256,
                :code_commit_sha, :created_by
            )
            ON CONFLICT (model_version_uuid) DO NOTHING
            """
        ),
        {
            **manifest.__dict__,
            "parameters": _json(manifest.parameters),
            "created_by": created_by,
        },
    )
    stored = connection.execute(
        text(
            """
            SELECT model_version_id, model_code, version_no,
                   implementation_sha256
            FROM stock_management.pdd_pdvb_model_version
            WHERE model_version_uuid = :model_version_uuid
            """
        ),
        {"model_version_uuid": manifest.model_version_uuid},
    ).mappings().one()
    expected = (
        manifest.model_code,
        manifest.version_no,
        manifest.implementation_sha256,
    )
    actual = (
        stored["model_code"],
        stored["version_no"],
        stored["implementation_sha256"].strip(),
    )
    if actual != expected:
        raise RuntimeError("El modelo operativo existente no coincide con el manifiesto")
    return stored["model_version_id"]


def _ensure_scope(
    connection: Connection,
    scope: Mapping[str, Any],
    articles: Sequence[Mapping[str, Any]],
    pairs: Sequence[Mapping[str, Any]],
    created_by: str,
) -> int:
    if len(articles) != scope["article_count"] or len(pairs) != scope["pair_count"]:
        raise RuntimeError("La membresia analitica no coincide con la cabecera del scope")
    detail = dict(scope.get("detail") or {})
    detail.update(
        {
            "scope_code": scope["scope_code"],
            "version_no": scope["version_no"],
            "routed_article_count": scope["routed_article_count"],
            "article_checksum": scope["article_checksum"].strip(),
            "pair_checksum": scope["pair_checksum"].strip(),
        }
    )
    connection.execute(
        text(
            """
            INSERT INTO stock_management.pdd_distribution_scope_version (
                scope_version_uuid, origin_cd, business_date, status, is_current,
                source_database, source_relation, source_as_of_ts,
                article_filter, pair_filter, article_count, pair_count,
                destination_count, checksum, created_at, created_by, detail
            ) VALUES (
                :scope_version_uuid, :origin_cd, :business_date, :status, false,
                :source_database, :source_relation, :source_as_of_ts,
                CAST(:article_filter AS jsonb), CAST(:pair_filter AS jsonb),
                :article_count, :pair_count, :destination_count, :checksum,
                :created_at, :created_by, CAST(:detail AS jsonb)
            )
            ON CONFLICT (scope_version_uuid) DO NOTHING
            """
        ),
        {
            **dict(scope),
            "article_filter": _json(scope["article_filter"]),
            "pair_filter": _json(scope["pair_filter"]),
            "checksum": scope["scope_checksum"].strip(),
            "created_at": scope["captured_at"],
            "created_by": created_by,
            "detail": _json(detail),
        },
    )
    stored = connection.execute(
        text(
            """
            SELECT scope_version_id, article_count, pair_count, checksum
            FROM stock_management.pdd_distribution_scope_version
            WHERE scope_version_uuid = :scope_version_uuid
            """
        ),
        {"scope_version_uuid": scope["scope_version_uuid"]},
    ).mappings().one()
    if (
        stored["article_count"] != scope["article_count"]
        or stored["pair_count"] != scope["pair_count"]
        or stored["checksum"].strip() != scope["scope_checksum"].strip()
    ):
        raise RuntimeError("El scope operativo existente no coincide con diarco_data")
    scope_version_id = stored["scope_version_id"]

    article_sql = text(
        """
        INSERT INTO stock_management.pdd_distribution_scope_article (
            scope_version_id, codigo_articulo, c_proveedor_primario,
            cd_active_for_purchase, cd_habilitado, cd_active_for_sale,
            cd_active_on_mix, source_row_hash
        ) VALUES (
            :scope_version_id, :codigo_articulo, :c_proveedor_primario,
            :cd_active_for_purchase, :cd_habilitado, :cd_active_for_sale,
            :cd_active_on_mix, :source_row_hash
        ) ON CONFLICT (scope_version_id, codigo_articulo) DO NOTHING
        """
    )
    for chunk in _chunks(articles):
        connection.execute(
            article_sql,
            [{**row, "scope_version_id": scope_version_id} for row in chunk],
        )

    pair_sql = text(
        """
        INSERT INTO stock_management.pdd_distribution_scope_pair (
            scope_version_id, origin_cd, destination_branch, codigo_articulo,
            c_proveedor_primario, route_code, supply_mode, branch_habilitado,
            branch_active_for_sale, branch_active_on_mix, source_row_hash
        ) VALUES (
            :scope_version_id, :origin_cd, :destination_branch, :codigo_articulo,
            :c_proveedor_primario, :route_code, :supply_mode, :branch_habilitado,
            :branch_active_for_sale, :branch_active_on_mix, :source_row_hash
        ) ON CONFLICT (scope_version_id, destination_branch, codigo_articulo)
          DO NOTHING
        """
    )
    for chunk in _chunks(pairs):
        connection.execute(
            pair_sql,
            [{**row, "scope_version_id": scope_version_id} for row in chunk],
        )

    counts = connection.execute(
        text(
            """
            SELECT
                (SELECT count(*) FROM stock_management.pdd_distribution_scope_article
                  WHERE scope_version_id = :scope_version_id) AS articles,
                (SELECT count(*) FROM stock_management.pdd_distribution_scope_pair
                  WHERE scope_version_id = :scope_version_id) AS pairs
            """
        ),
        {"scope_version_id": scope_version_id},
    ).mappings().one()
    if counts["articles"] != len(articles) or counts["pairs"] != len(pairs):
        raise RuntimeError("El scope operativo quedo incompleto")
    return scope_version_id


def _ensure_estimate_partition(connection: Connection, business_date: date) -> None:
    month_start = business_date.replace(day=1)
    if month_start.month == 12:
        next_month = date(month_start.year + 1, 1, 1)
    else:
        next_month = date(month_start.year, month_start.month + 1, 1)
    partition = f"pdd_pdvb_estimate_y{month_start.year:04d}m{month_start.month:02d}"
    connection.execute(
        text(
            f"""
            CREATE TABLE IF NOT EXISTS stock_management.{partition}
            PARTITION OF stock_management.pdd_pdvb_estimate
            FOR VALUES FROM ('{month_start.isoformat()}') TO ('{next_month.isoformat()}')
            """
        )
    )


def _read_staged_for_checksum(
    connection: Connection,
    publication_batch_id: int,
) -> list[Mapping[str, Any]]:
    return connection.execute(
        text(
            """
            SELECT s.business_date, s.analytical_detail_id,
                   m.model_version_uuid, v.scope_version_uuid,
                   s.origin_cd, s.codigo_articulo, s.sucursal,
                   s.c_proveedor_primario, s.method_code, s.fallback_level,
                   s.status, s.confidence_score, s.pdvb_value, s.input_checksum
            FROM stock_management.pdd_pdvb_publication_stage AS s
            JOIN stock_management.pdd_pdvb_model_version AS m
              ON m.model_version_id = s.model_version_id
            JOIN stock_management.pdd_distribution_scope_version AS v
              ON v.scope_version_id = s.scope_version_id
            WHERE s.publication_batch_id = :publication_batch_id
            ORDER BY s.sucursal, s.codigo_articulo
            """
        ),
        {"publication_batch_id": publication_batch_id},
    ).mappings().all()


def _mark_source_published(
    source_engine: Engine,
    source_settings: Settings,
    calculation_run_uuid: UUID,
    publication_batch_uuid: UUID,
    expected_rows: int,
) -> None:
    with transactional_connection(source_engine, source_settings) as connection:
        lineage = connection.execute(
            text(
                """
                SELECT count(*)::bigint AS total_rows,
                       count(*) FILTER (
                           WHERE publication_batch_uuid IS NOT NULL
                       )::bigint AS marked_rows,
                       count(DISTINCT publication_batch_uuid)::integer
                           AS marked_batches,
                       count(*) FILTER (
                           WHERE publication_batch_uuid IS NOT NULL
                             AND published_at IS NULL
                       )::bigint AS missing_published_at
                FROM datamart.dm_pdd_pdvb_estimate_detail
                WHERE calculation_run_uuid = :calculation_run_uuid
                """
            ),
            {"calculation_run_uuid": calculation_run_uuid},
        ).mappings().one()
        if lineage["total_rows"] != expected_rows:
            raise RuntimeError(
                "Cantidad analitica inesperada al marcar publicacion: "
                f"{lineage['total_rows']}/{expected_rows}"
            )
        if lineage["marked_batches"] > 1 or lineage["marked_rows"] not in (
            0,
            expected_rows,
        ):
            raise RuntimeError("El linaje analitico esta fragmentado")
        if lineage["missing_published_at"]:
            raise RuntimeError("El linaje analitico publicado no tiene fecha completa")
        # La fuente conserva el primer lote que publico la corrida. Las siguientes
        # publicaciones (por ejemplo TEST y DESA) tienen su lote autoritativo en
        # cada base operativa y no deben sobrescribir ese primer marcador.
        if lineage["marked_rows"] == expected_rows:
            return
        connection.execute(
            text(
                """
                UPDATE datamart.dm_pdd_pdvb_estimate_detail
                SET publication_batch_uuid = :publication_batch_uuid,
                    published_at = COALESCE(published_at, clock_timestamp())
                WHERE calculation_run_uuid = :calculation_run_uuid
                  AND publication_batch_uuid IS NULL
                """
            ),
            {
                "calculation_run_uuid": calculation_run_uuid,
                "publication_batch_uuid": publication_batch_uuid,
            },
        )
        marked = connection.execute(
            text(
                """
                SELECT count(*)
                FROM datamart.dm_pdd_pdvb_estimate_detail
                WHERE calculation_run_uuid = :calculation_run_uuid
                  AND publication_batch_uuid = :publication_batch_uuid
                  AND published_at IS NOT NULL
                """
            ),
            {
                "calculation_run_uuid": calculation_run_uuid,
                "publication_batch_uuid": publication_batch_uuid,
            },
        ).scalar_one()
        if marked != expected_rows:
            raise RuntimeError(f"Linaje analitico incompleto: {marked}/{expected_rows}")


def publish_pdvb(
    source_engine: Engine,
    source_settings: Settings,
    target_engine: Engine,
    target_settings: OperationalSettings,
    calculation_run_uuid: UUID,
    created_by: str,
) -> PublicationResult:
    if not created_by.strip():
        raise ValueError("created_by es obligatorio")

    with source_engine.connect() as source:
        header, rows = _read_source_estimates(source, calculation_run_uuid)
        scope = _read_source_scope(source, header["scope_version_uuid"])
        articles, pairs = _read_source_membership(
            source, header["scope_version_uuid"]
        )
    if len(rows) != header["row_count"] or len(rows) != scope["pair_count"]:
        raise RuntimeError(
            "La corrida PDVB no cubre exactamente el scope congelado: "
            f"estimaciones={len(rows)}, scope={scope['pair_count']}"
        )
    manifest = load_model_version(header["model_version_uuid"])
    source_checksum = estimate_checksum(rows)
    status_counts = Counter(row["status"] for row in rows)

    with transactional_connection(target_engine, target_settings) as target:
        target.execute(
            text("SELECT pg_advisory_xact_lock(hashtext('pdd.publish.pdvb'))")
        )
        _ensure_target_contract(target)
        existing = target.execute(
            text(
                """
                SELECT r.calculation_run_id, b.publication_batch_uuid,
                       b.published_row_count, b.source_checksum, b.status
                FROM stock_management.pdd_calculation_run AS r
                JOIN stock_management.pdd_pdvb_publication_batch AS b
                  ON b.calculation_run_id = r.calculation_run_id
                WHERE r.calculation_run_uuid = :calculation_run_uuid
                """
            ),
            {"calculation_run_uuid": calculation_run_uuid},
        ).mappings().one_or_none()
        if existing is not None:
            if (
                existing["status"] != "PUBLISHED"
                or existing["published_row_count"] != len(rows)
                or existing["source_checksum"] != source_checksum
            ):
                raise RuntimeError("Existe una publicacion incompatible para la corrida")
            publication_batch_uuid = existing["publication_batch_uuid"]
            target.execute(
                text(
                    """
                    UPDATE stock_management.pdd_calculation_run
                    SET summary = jsonb_set(
                        COALESCE(summary, '{}'::jsonb),
                        '{environment}',
                        to_jsonb(CAST(:target_environment AS text)),
                        true
                    )
                    WHERE calculation_run_id = :calculation_run_id
                    """
                ),
                {
                    "target_environment": target_settings.target_environment,
                    "calculation_run_id": existing["calculation_run_id"],
                },
            )
            reused = True
        else:
            reused = False
            model_version_id = _ensure_model(target, manifest, created_by)
            scope_version_id = _ensure_scope(
                target, scope, articles, pairs, created_by
            )
            attempt_no = target.execute(
                text(
                    """
                    SELECT COALESCE(max(attempt_no), 0) + 1
                    FROM stock_management.pdd_calculation_run
                    WHERE run_type = 'PDVB'
                      AND business_date = :business_date
                      AND scope_type = 'CD' AND scope_id = :scope_id
                    """
                ),
                {
                    "business_date": header["business_date"],
                    "scope_id": str(header["origin_cd"]),
                },
            ).scalar_one()
            calculation_run_id = target.execute(
                text(
                    """
                    INSERT INTO stock_management.pdd_calculation_run (
                        calculation_run_uuid, run_type, business_date, cutoff_date,
                        scope_type, scope_id, attempt_no, scope_version_id,
                        model_version_id, formula_version, status, started_at,
                        created_by, input_row_count, output_row_count,
                        warning_count, error_count, input_checksum, summary
                    ) VALUES (
                        :calculation_run_uuid, 'PDVB', :business_date, :cutoff_date,
                        'CD', :scope_id, :attempt_no, :scope_version_id,
                        :model_version_id, :formula_version, 'RUNNING', :started_at,
                        :created_by, :input_row_count, :output_row_count,
                        :warning_count, 0, :input_checksum, CAST(:summary AS jsonb)
                    ) RETURNING calculation_run_id
                    """
                ),
                {
                    "calculation_run_uuid": calculation_run_uuid,
                    "business_date": header["business_date"],
                    "cutoff_date": header["business_date"] - timedelta(days=1),
                    "scope_id": str(header["origin_cd"]),
                    "attempt_no": attempt_no,
                    "scope_version_id": scope_version_id,
                    "model_version_id": model_version_id,
                    "formula_version": f"{manifest.model_code}_v{manifest.version_no}",
                    "started_at": header["started_at"],
                    "created_by": created_by,
                    "input_row_count": len(rows),
                    "output_row_count": len(rows),
                    "warning_count": status_counts["WARN"] + status_counts["BLOCKED"],
                    "input_checksum": source_checksum,
                    "summary": _json(
                        {
                            "environment": target_settings.target_environment,
                            "source_calculation_run_uuid": str(calculation_run_uuid),
                            "status_counts": status_counts,
                        }
                    ),
                },
            ).scalar_one()
            publication_batch_uuid = resolve_publication_batch_uuid(
                calculation_run_uuid,
                header["publication_batch_uuid"],
            )
            publication_batch_id = target.execute(
                text(
                    """
                    INSERT INTO stock_management.pdd_pdvb_publication_batch (
                        publication_batch_uuid, calculation_run_id,
                        expected_row_count, source_checksum, status, created_by,
                        detail
                    ) VALUES (
                        :publication_batch_uuid, :calculation_run_id,
                        :expected_row_count, :source_checksum, 'STAGING', :created_by,
                        CAST(:detail AS jsonb)
                    ) RETURNING publication_batch_id
                    """
                ),
                {
                    "publication_batch_uuid": publication_batch_uuid,
                    "calculation_run_id": calculation_run_id,
                    "expected_row_count": len(rows),
                    "source_checksum": source_checksum,
                    "created_by": created_by,
                    "detail": _json(
                        {
                            "canonical_columns": ESTIMATE_COLUMNS,
                            "canonical_order": ["sucursal", "codigo_articulo"],
                            "checksum_algorithm": "SHA-256",
                        }
                    ),
                },
            ).scalar_one()

            stage_sql = text(
                """
                INSERT INTO stock_management.pdd_pdvb_publication_stage (
                    publication_batch_id, business_date, analytical_detail_id,
                    model_version_id, scope_version_id, origin_cd,
                    codigo_articulo, sucursal, c_proveedor_primario,
                    method_code, fallback_level, status, confidence_score,
                    pdvb_value, input_checksum, explanation_summary
                ) VALUES (
                    :publication_batch_id, :business_date, :analytical_detail_id,
                    :model_version_id, :scope_version_id, :origin_cd,
                    :codigo_articulo, :sucursal, :c_proveedor_primario,
                    :method_code, :fallback_level, :status, :confidence_score,
                    :pdvb_value, :input_checksum, CAST(:explanation_summary AS jsonb)
                )
                """
            )
            for chunk in _chunks(rows):
                target.execute(
                    stage_sql,
                    [
                        {
                            **row,
                            "publication_batch_id": publication_batch_id,
                            "model_version_id": model_version_id,
                            "scope_version_id": scope_version_id,
                            "explanation_summary": _json(row["explanation_summary"]),
                        }
                        for row in chunk
                    ],
                )
            staged = _read_staged_for_checksum(target, publication_batch_id)
            staged_checksum = estimate_checksum(staged)
            if len(staged) != len(rows) or staged_checksum != source_checksum:
                raise RuntimeError("El staging operativo no coincide con la fuente")
            target.execute(
                text(
                    """
                    UPDATE stock_management.pdd_pdvb_publication_batch
                    SET staged_row_count = :row_count,
                        staged_checksum = :checksum,
                        status = 'VALIDATED', validated_at = clock_timestamp()
                    WHERE publication_batch_id = :publication_batch_id
                    """
                ),
                {
                    "row_count": len(rows),
                    "checksum": staged_checksum,
                    "publication_batch_id": publication_batch_id,
                },
            )
            _ensure_estimate_partition(target, header["business_date"])
            target.execute(
                text(
                    """
                    INSERT INTO stock_management.pdd_pdvb_estimate (
                        business_date, calculation_run_id, publication_batch_id,
                        analytical_detail_id, model_version_id, scope_version_id,
                        origin_cd, codigo_articulo, sucursal, c_proveedor_primario,
                        method_code, fallback_level, status, confidence_score,
                        pdvb_value, input_checksum, explanation_summary, published_at
                    )
                    SELECT business_date, :calculation_run_id, publication_batch_id,
                           analytical_detail_id, model_version_id, scope_version_id,
                           origin_cd, codigo_articulo, sucursal, c_proveedor_primario,
                           method_code, fallback_level, status, confidence_score,
                           pdvb_value, input_checksum, explanation_summary,
                           clock_timestamp()
                    FROM stock_management.pdd_pdvb_publication_stage
                    WHERE publication_batch_id = :publication_batch_id
                    """
                ),
                {
                    "calculation_run_id": calculation_run_id,
                    "publication_batch_id": publication_batch_id,
                },
            )
            target.execute(
                text(
                    """
                    INSERT INTO stock_management.pdd_pdvb_quality_issue (
                        calculation_run_id, business_date, codigo_articulo,
                        sucursal, severity, issue_code, entity_type,
                        entity_key, detail, evidence
                    )
                    SELECT :calculation_run_id, business_date, codigo_articulo,
                           sucursal, 'WARN', 'PDVB_INSUFFICIENT_DATA',
                           'ARTICLE_BRANCH',
                           jsonb_build_object('codigo_articulo', codigo_articulo,
                                              'sucursal', sucursal),
                           'PDVB bloqueado por evidencia basal insuficiente',
                           explanation_summary
                    FROM stock_management.pdd_pdvb_publication_stage
                    WHERE publication_batch_id = :publication_batch_id
                      AND status = 'BLOCKED'
                    """
                ),
                {
                    "calculation_run_id": calculation_run_id,
                    "publication_batch_id": publication_batch_id,
                },
            )
            target.execute(
                text(
                    """
                    INSERT INTO stock_management.pdd_pdvb_current (
                        origin_cd, codigo_articulo, sucursal, business_date,
                        pdvb_estimate_id, calculation_run_id, model_version_id,
                        scope_version_id, pdvb_value, status, confidence_score,
                        published_at
                    )
                    SELECT e.origin_cd, e.codigo_articulo, e.sucursal,
                           e.business_date, e.pdvb_estimate_id,
                           e.calculation_run_id, e.model_version_id,
                           e.scope_version_id, e.pdvb_value, e.status,
                           e.confidence_score, e.published_at
                    FROM stock_management.pdd_pdvb_estimate AS e
                    WHERE e.calculation_run_id = :calculation_run_id
                      AND e.status <> 'BLOCKED'
                    ON CONFLICT (origin_cd, codigo_articulo, sucursal) DO UPDATE
                    SET business_date = EXCLUDED.business_date,
                        pdvb_estimate_id = EXCLUDED.pdvb_estimate_id,
                        calculation_run_id = EXCLUDED.calculation_run_id,
                        model_version_id = EXCLUDED.model_version_id,
                        scope_version_id = EXCLUDED.scope_version_id,
                        pdvb_value = EXCLUDED.pdvb_value,
                        status = EXCLUDED.status,
                        confidence_score = EXCLUDED.confidence_score,
                        published_at = EXCLUDED.published_at
                    WHERE EXCLUDED.business_date >= stock_management.pdd_pdvb_current.business_date
                    """
                ),
                {"calculation_run_id": calculation_run_id},
            )
            target.execute(
                text(
                    """
                    DELETE FROM stock_management.pdd_pdvb_current AS c
                    WHERE c.origin_cd = :origin_cd
                      AND c.business_date <= :business_date
                      AND NOT EXISTS (
                          SELECT 1
                          FROM stock_management.pdd_pdvb_publication_stage AS s
                          WHERE s.publication_batch_id = :publication_batch_id
                            AND s.status <> 'BLOCKED'
                            AND s.origin_cd = c.origin_cd
                            AND s.codigo_articulo = c.codigo_articulo
                            AND s.sucursal = c.sucursal
                      )
                    """
                ),
                {
                    "origin_cd": header["origin_cd"],
                    "business_date": header["business_date"],
                    "publication_batch_id": publication_batch_id,
                },
            )
            target.execute(
                text(
                    """
                    UPDATE stock_management.pdd_calculation_run
                    SET is_current = false
                    WHERE run_type = 'PDVB' AND business_date = :business_date
                      AND scope_type = 'CD' AND scope_id = :scope_id
                      AND calculation_run_id <> :calculation_run_id
                    """
                ),
                {
                    "business_date": header["business_date"],
                    "scope_id": str(header["origin_cd"]),
                    "calculation_run_id": calculation_run_id,
                },
            )
            target.execute(
                text(
                    """
                    UPDATE stock_management.pdd_pdvb_publication_batch
                    SET published_row_count = :row_count, status = 'PUBLISHED',
                        published_at = clock_timestamp()
                    WHERE publication_batch_id = :publication_batch_id
                    """
                ),
                {
                    "row_count": len(rows),
                    "publication_batch_id": publication_batch_id,
                },
            )
            target.execute(
                text(
                    """
                    UPDATE stock_management.pdd_calculation_run
                    SET status = 'SUCCEEDED', is_current = true,
                        finished_at = clock_timestamp(),
                        output_checksum = :output_checksum
                    WHERE calculation_run_id = :calculation_run_id
                    """
                ),
                {
                    "output_checksum": source_checksum,
                    "calculation_run_id": calculation_run_id,
                },
            )

        published_rows = len(rows)
        current_rows = len(rows) - status_counts["BLOCKED"]

    _mark_source_published(
        source_engine,
        source_settings,
        calculation_run_uuid,
        publication_batch_uuid,
        len(rows),
    )
    return PublicationResult(
        calculation_run_uuid=calculation_run_uuid,
        publication_batch_uuid=publication_batch_uuid,
        business_date=header["business_date"],
        source_rows=len(rows),
        published_rows=published_rows,
        current_rows=current_rows,
        blocked_rows=status_counts["BLOCKED"],
        source_checksum=source_checksum,
        target_database=target_settings.pg_database,
        reused_publication=reused,
    )
