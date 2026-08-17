from __future__ import annotations

import os
import re
from dataclasses import replace
from functools import lru_cache
from typing import Any, Callable
from uuid import UUID, uuid4

from fastapi import Depends, FastAPI, Header, Query, Request, Response
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import ValidationError
from sqlalchemy.exc import SQLAlchemyError

from .. import __version__
from ..config import OperationalSettings
from ..db import build_api_engine
from .cursor import CursorCodec, CursorPayload
from .errors import ApiError
from .models import (
    BacklogQuery,
    DirectedNeedCreate,
    DirectedNeedQuery,
    DirectedNeedReplace,
    Identity,
    StateAction,
)
from .repository import PddRepository
from .security import (
    ALL_ROLES,
    EDIT_ROLES,
    SUPERVISOR_ROLES,
    Authenticator,
    SecuritySettings,
    require_roles,
)


API_PREFIX = "/api/v1/pdd"
ETAG_PATTERN = re.compile(r'^W/"(?P<uuid>[0-9a-fA-F-]{36}):(?P<version>[1-9][0-9]*)"$')


def _csv(value: str | None, cast: Callable[[str], Any], field: str) -> tuple[Any, ...]:
    if value is None or not value.strip():
        return ()
    try:
        return tuple(cast(part.strip()) for part in value.split(",") if part.strip())
    except (TypeError, ValueError) as exc:
        raise ApiError(400, "INVALID_QUERY", f"{field} contiene un valor inválido") from exc


def _etag(entity_uuid: UUID | str, version: int) -> str:
    return f'W/"{entity_uuid}:{version}"'


def _expected_version(value: str, expected_uuid: UUID) -> int:
    match = ETAG_PATTERN.fullmatch(value)
    if match is None or UUID(match.group("uuid")) != expected_uuid:
        raise ApiError(400, "INVALID_QUERY", "If-Match no corresponde al recurso")
    return int(match.group("version"))


def _query_model(model: Any, values: dict[str, Any]) -> Any:
    try:
        return model.model_validate(values)
    except ValidationError as exc:
        field_errors = [
            {
                "field": ".".join(str(item) for item in issue["loc"]),
                "code": issue["type"],
                "message": issue["msg"],
            }
            for issue in exc.errors()
        ]
        raise ApiError(
            400,
            "INVALID_QUERY",
            "Los parámetros de consulta son inválidos",
            field_errors=field_errors,
        ) from exc


def _problem(request: Request, error: ApiError) -> JSONResponse:
    trace_id = getattr(request.state, "trace_id", str(uuid4()))
    correlation_id = getattr(request.state, "correlation_id", None)
    body = {
        "type": f"/problems/{error.code.lower().replace('_', '-')}",
        "title": error.title,
        "status": error.status_code,
        "code": error.code,
        "message": error.message,
        "traceId": trace_id,
        "correlationId": str(correlation_id) if correlation_id else None,
        "fieldErrors": error.field_errors,
    }
    return JSONResponse(
        status_code=error.status_code,
        content=jsonable_encoder(body),
        headers=error.headers,
    )


def create_app(
    repository: PddRepository | Any | None = None,
    authenticator: Callable[..., Identity] | None = None,
    cursor_codec: CursorCodec | None = None,
) -> FastAPI:
    app = FastAPI(
        title="Connexa PDD API",
        version="1.0.0",
        docs_url=f"{API_PREFIX}/docs",
        openapi_url=f"{API_PREFIX}/runtime-openapi.json",
    )

    origins = [value.strip() for value in os.getenv("PDD_API_CORS_ORIGINS", "").split(",") if value.strip()]
    if origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=origins,
            allow_credentials=True,
            allow_methods=["GET", "POST", "PUT"],
            allow_headers=[
                "Authorization", "Content-Type", "If-Match", "Idempotency-Key",
                "X-Correlation-Id",
            ],
            expose_headers=["ETag", "Location", "X-Correlation-Id"],
        )

    repository_holder: list[Any] = [repository] if repository is not None else []
    authenticator_holder: list[Callable[..., Identity]] = [authenticator] if authenticator else []
    cursor_holder: list[CursorCodec] = [cursor_codec] if cursor_codec else []

    def get_repository() -> Any:
        if not repository_holder:
            settings = replace(
                OperationalSettings.from_env(),
                statement_timeout_ms=int(os.getenv("PDD_API_DB_STATEMENT_TIMEOUT_MS", "15000")),
                lock_timeout_ms=int(os.getenv("PDD_API_DB_LOCK_TIMEOUT_MS", "3000")),
            )
            repository_holder.append(PddRepository(build_api_engine(settings), settings))
        return repository_holder[0]

    def get_cursor_codec() -> CursorCodec:
        if not cursor_holder:
            secret = os.getenv("PDD_API_CURSOR_SECRET")
            if not secret:
                raise RuntimeError("Debe configurar PDD_API_CURSOR_SECRET")
            cursor_holder.append(CursorCodec(secret))
        return cursor_holder[0]

    def get_authenticator() -> Callable[..., Identity]:
        if not authenticator_holder:
            authenticator_holder.append(Authenticator(SecuritySettings.from_env()))
        return authenticator_holder[0]

    def startup_check() -> None:
        get_repository().ensure_contract()
        get_cursor_codec()
        get_authenticator()

    app.add_event_handler("startup", startup_check)

    def identity_dependency(
        authorization: str | None = Header(default=None, alias="Authorization"),
        user_id: str | None = Header(default=None, alias="X-Connexa-User"),
        roles: str | None = Header(default=None, alias="X-Connexa-Roles"),
        proxy_secret: str | None = Header(default=None, alias="X-PDD-Proxy-Secret"),
        test_user: str | None = Header(default=None, alias="X-PDD-Test-User"),
        test_roles: str | None = Header(default=None, alias="X-PDD-Test-Roles"),
    ) -> Identity:
        provider = get_authenticator()
        return provider(
            authorization=authorization,
            user_id=user_id,
            role_header=roles,
            supplied_secret=proxy_secret,
            test_user=test_user,
            test_roles=test_roles,
        )

    @app.middleware("http")
    async def correlation_middleware(request: Request, call_next: Callable[..., Any]) -> Response:
        supplied = request.headers.get("X-Correlation-Id")
        try:
            correlation_id = UUID(supplied) if supplied else uuid4()
        except ValueError:
            correlation_id = uuid4()
        request.state.correlation_id = correlation_id
        request.state.trace_id = str(uuid4())
        response = await call_next(request)
        response.headers["X-Correlation-Id"] = str(correlation_id)
        if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
            response.headers["Cache-Control"] = "no-store"
        return response

    @app.exception_handler(ApiError)
    async def api_error_handler(request: Request, error: ApiError) -> JSONResponse:
        return _problem(request, error)

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(request: Request, error: RequestValidationError) -> JSONResponse:
        field_errors = [
            {
                "field": ".".join(str(item) for item in issue["loc"] if item != "body"),
                "code": issue["type"],
                "message": issue["msg"],
            }
            for issue in error.errors()
        ]
        return _problem(
            request,
            ApiError(422, "VALIDATION_ERROR", "La solicitud contiene datos inválidos", field_errors=field_errors),
        )

    @app.exception_handler(SQLAlchemyError)
    async def database_error_handler(request: Request, error: SQLAlchemyError) -> JSONResponse:
        return _problem(request, ApiError(503, "DATA_UNAVAILABLE", "La base operativa no está disponible"))

    @app.get("/healthz", include_in_schema=False)
    def health(repository: Any = Depends(get_repository)) -> dict[str, str]:
        repository.ensure_contract()
        return {"status": "ok", "version": __version__}

    @app.get(f"{API_PREFIX}/status")
    def status(
        identity: Identity = Depends(identity_dependency),
        repository: Any = Depends(get_repository),
    ) -> dict[str, Any]:
        require_roles(identity, ALL_ROLES)
        snapshot = repository.current_snapshot()
        if snapshot is None:
            return {
                "status": "UNAVAILABLE",
                "environment": os.getenv("PDD_API_ENVIRONMENT", "UNKNOWN"),
                "apiVersion": "1.0.0",
                "currentSnapshot": None,
                "blockers": ["NO_CURRENT_SNAPSHOT"],
            }
        snapshot_body = {
            "snapshotVersion": snapshot["snapshot_version"],
            "businessDate": snapshot["business_date"],
            "calculationRunUuid": snapshot["calculation_run_uuid"],
            "publishedAt": snapshot["published_at"],
            "freshnessStatus": snapshot["freshness_status"],
        }
        degraded = snapshot["freshness_status"] != "CURRENT"
        return {
            "status": "DEGRADED" if degraded else "READY",
            "environment": os.getenv("PDD_API_ENVIRONMENT", "UNKNOWN"),
            "apiVersion": "1.0.0",
            "currentSnapshot": snapshot_body,
            "blockers": [f"SNAPSHOT_{snapshot['freshness_status']}"] if degraded else [],
        }

    @app.get(f"{API_PREFIX}/dashboard/summary")
    def dashboard(
        response: Response,
        identity: Identity = Depends(identity_dependency),
        repository: Any = Depends(get_repository),
    ) -> Any:
        require_roles(identity, ALL_ROLES)
        result = repository.dashboard()
        response.headers["ETag"] = f'W/"{result["snapshot"]["snapshotVersion"]}"'
        return result

    @app.get(f"{API_PREFIX}/backlog")
    def backlog(
        response: Response,
        page_size: int = Query(default=50, alias="pageSize", ge=1, le=200),
        page_cursor: str | None = Query(default=None, alias="pageCursor", max_length=1000),
        branch_id: str | None = Query(default=None, alias="branchId"),
        article_id: str | None = Query(default=None, alias="articleId"),
        supplier_id: str | None = Query(default=None, alias="supplierId"),
        need_type: str | None = Query(default=None, alias="needType"),
        mandatory: bool | None = Query(default=None),
        minimum_irq: float | None = Query(default=None, alias="minimumIrq", ge=0, le=100),
        target_date_to: str | None = Query(default=None, alias="targetDateTo"),
        freshness_status: str | None = Query(default=None, alias="freshnessStatus"),
        with_alerts: bool | None = Query(default=None, alias="withAlerts"),
        search: str | None = Query(default=None, min_length=2, max_length=100),
        sort: str = Query(default="priority_desc"),
        identity: Identity = Depends(identity_dependency),
        repository: Any = Depends(get_repository),
    ) -> Any:
        require_roles(identity, ALL_ROLES)
        query = _query_model(
            BacklogQuery,
            {
                "page_size": page_size, "page_cursor": page_cursor,
                "branch_ids": _csv(branch_id, int, "branchId"),
                "article_ids": _csv(article_id, int, "articleId"),
                "supplier_ids": _csv(supplier_id, int, "supplierId"),
                "need_types": _csv(need_type, str.upper, "needType"),
                "mandatory": mandatory, "minimum_irq": minimum_irq,
                "target_date_to": target_date_to,
                "freshness_statuses": _csv(freshness_status, str.upper, "freshnessStatus"),
                "with_alerts": with_alerts, "search": search, "sort": sort,
            }
        )
        codec = get_cursor_codec()
        decoded = codec.decode(page_cursor) if page_cursor else None
        result, next_values = repository.list_backlog(query, decoded)
        if next_values:
            snapshot = str(result["meta"]["snapshot"]["snapshotVersion"])
            result["meta"]["nextCursor"] = codec.encode(CursorPayload(snapshot, query.sort, next_values))
        response.headers["ETag"] = f'W/"{result["meta"]["snapshot"]["snapshotVersion"]}"'
        return result

    @app.get(f"{API_PREFIX}/backlog/{{backlogLineUuid}}")
    def backlog_detail(
        backlogLineUuid: UUID,
        response: Response,
        identity: Identity = Depends(identity_dependency),
        repository: Any = Depends(get_repository),
    ) -> Any:
        require_roles(identity, ALL_ROLES)
        result = repository.get_backlog(backlogLineUuid)
        response.headers["ETag"] = _etag(result["backlogLineUuid"], result["rowVersion"])
        return result

    @app.get(f"{API_PREFIX}/backlog/{{backlogLineUuid}}/explanation")
    def backlog_explanation(
        backlogLineUuid: UUID,
        identity: Identity = Depends(identity_dependency),
        repository: Any = Depends(get_repository),
    ) -> Any:
        require_roles(identity, ALL_ROLES)
        return repository.backlog_explanation(backlogLineUuid)

    @app.get(f"{API_PREFIX}/catalogs/filters")
    def catalogs(
        identity: Identity = Depends(identity_dependency),
        repository: Any = Depends(get_repository),
    ) -> Any:
        require_roles(identity, ALL_ROLES)
        return repository.filter_catalogs()

    @app.get(f"{API_PREFIX}/calculation-runs/{{calculationRunUuid}}")
    def calculation_run(
        calculationRunUuid: UUID,
        identity: Identity = Depends(identity_dependency),
        repository: Any = Depends(get_repository),
    ) -> Any:
        require_roles(identity, ALL_ROLES)
        return repository.calculation_run(calculationRunUuid)

    @app.get(f"{API_PREFIX}/directed-needs")
    def directed_list(
        page_size: int = Query(default=50, alias="pageSize", ge=1, le=200),
        page_cursor: str | None = Query(default=None, alias="pageCursor", max_length=1000),
        need_type: str | None = Query(default=None, alias="needType"),
        status_filter: str | None = Query(default=None, alias="status"),
        valid_on: str | None = Query(default=None, alias="validOn"),
        owner_user: str | None = Query(default=None, alias="ownerUser"),
        search: str | None = Query(default=None, min_length=2, max_length=120),
        identity: Identity = Depends(identity_dependency),
        repository: Any = Depends(get_repository),
    ) -> Any:
        require_roles(identity, ALL_ROLES)
        query = _query_model(
            DirectedNeedQuery,
            {
                "page_size": page_size, "page_cursor": page_cursor,
                "need_types": _csv(need_type, str.upper, "needType"),
                "statuses": _csv(status_filter, str.upper, "status"),
                "valid_on": valid_on, "owner_user": owner_user, "search": search,
            }
        )
        codec = get_cursor_codec()
        decoded = codec.decode(page_cursor) if page_cursor else None
        result, next_values = repository.list_directed(query, decoded)
        if next_values:
            result["nextCursor"] = codec.encode(CursorPayload("directed-needs", "updated_desc", next_values))
        return result

    @app.post(f"{API_PREFIX}/directed-needs", status_code=201)
    def directed_create(
        payload: DirectedNeedCreate,
        response: Response,
        idempotency_key: str = Header(alias="Idempotency-Key", min_length=8, max_length=160),
        identity: Identity = Depends(identity_dependency),
        repository: Any = Depends(get_repository),
        request: Request = None,
    ) -> Any:
        require_roles(identity, EDIT_ROLES)
        if payload.owner_user != identity.user_id and "PDD_SUPERVISOR" not in identity.roles:
            raise ApiError(422, "OWNER_MISMATCH", "ownerUser debe coincidir con la identidad autenticada")
        result, replay = repository.create_directed(
            payload, identity.user_id, idempotency_key, request.state.correlation_id
        )
        response.headers["ETag"] = _etag(result["directedNeedUuid"], result["versionNo"])
        response.headers["Location"] = f'{API_PREFIX}/directed-needs/{result["directedNeedUuid"]}'
        if replay:
            response.headers["Idempotent-Replay"] = "true"
        return result

    @app.get(f"{API_PREFIX}/directed-needs/{{directedNeedUuid}}")
    def directed_get(
        directedNeedUuid: UUID,
        response: Response,
        identity: Identity = Depends(identity_dependency),
        repository: Any = Depends(get_repository),
    ) -> Any:
        require_roles(identity, ALL_ROLES)
        result = repository.get_directed(directedNeedUuid)
        response.headers["ETag"] = _etag(result["directedNeedUuid"], result["versionNo"])
        return result

    @app.put(f"{API_PREFIX}/directed-needs/{{directedNeedUuid}}")
    def directed_replace(
        directedNeedUuid: UUID,
        payload: DirectedNeedReplace,
        response: Response,
        if_match: str = Header(alias="If-Match"),
        identity: Identity = Depends(identity_dependency),
        repository: Any = Depends(get_repository),
        request: Request = None,
    ) -> Any:
        require_roles(identity, EDIT_ROLES)
        current = repository.get_directed(directedNeedUuid)
        if "PDD_SUPERVISOR" not in identity.roles and current["ownerUser"] != identity.user_id:
            raise ApiError(403, "FORBIDDEN", "Un comprador solo modifica necesidades propias")
        if payload.owner_user != identity.user_id and "PDD_SUPERVISOR" not in identity.roles:
            raise ApiError(422, "OWNER_MISMATCH", "ownerUser debe coincidir con la identidad autenticada")
        result = repository.replace_directed(
            directedNeedUuid, _expected_version(if_match, directedNeedUuid),
            payload, identity.user_id, request.state.correlation_id,
        )
        response.headers["ETag"] = _etag(result["directedNeedUuid"], result["versionNo"])
        return result

    def transition(
        action: str,
        directed_need_uuid: UUID,
        payload: StateAction,
        if_match: str,
        identity: Identity,
        repository: Any,
        request: Request,
        response: Response,
    ) -> Any:
        require_roles(identity, SUPERVISOR_ROLES)
        result = repository.transition_directed(
            directed_need_uuid, _expected_version(if_match, directed_need_uuid), action,
            payload.reason, identity.user_id, request.state.correlation_id,
        )
        response.headers["ETag"] = _etag(result["directedNeedUuid"], result["versionNo"])
        return result

    @app.post(f"{API_PREFIX}/directed-needs/{{directedNeedUuid}}/activate")
    def directed_activate(
        directedNeedUuid: UUID, payload: StateAction, response: Response, request: Request,
        if_match: str = Header(alias="If-Match"),
        identity: Identity = Depends(identity_dependency), repository: Any = Depends(get_repository),
    ) -> Any:
        return transition("activate", directedNeedUuid, payload, if_match, identity, repository, request, response)

    @app.post(f"{API_PREFIX}/directed-needs/{{directedNeedUuid}}/cancel")
    def directed_cancel(
        directedNeedUuid: UUID, payload: StateAction, response: Response, request: Request,
        if_match: str = Header(alias="If-Match"),
        identity: Identity = Depends(identity_dependency), repository: Any = Depends(get_repository),
    ) -> Any:
        return transition("cancel", directedNeedUuid, payload, if_match, identity, repository, request, response)

    @app.post(f"{API_PREFIX}/directed-needs/{{directedNeedUuid}}/close")
    def directed_close(
        directedNeedUuid: UUID, payload: StateAction, response: Response, request: Request,
        if_match: str = Header(alias="If-Match"),
        identity: Identity = Depends(identity_dependency), repository: Any = Depends(get_repository),
    ) -> Any:
        return transition("close", directedNeedUuid, payload, if_match, identity, repository, request, response)

    @app.get(f"{API_PREFIX}/directed-needs/{{directedNeedUuid}}/versions")
    def directed_versions(
        directedNeedUuid: UUID,
        identity: Identity = Depends(identity_dependency),
        repository: Any = Depends(get_repository),
    ) -> Any:
        require_roles(identity, frozenset({"PDD_BUYER", "PDD_SUPERVISOR", "PDD_AUDITOR", "PDD_TECHNICAL"}))
        current = repository.get_directed(directedNeedUuid)
        elevated = {"PDD_SUPERVISOR", "PDD_AUDITOR", "PDD_TECHNICAL"}
        if "PDD_BUYER" in identity.roles and not identity.roles.intersection(elevated) and current["ownerUser"] != identity.user_id:
            raise ApiError(403, "FORBIDDEN", "Un comprador solo audita necesidades propias")
        return repository.directed_versions(directedNeedUuid)

    return app


app = create_app()
