from __future__ import annotations

import hmac
import os
from dataclasses import dataclass

from fastapi import Header

from .errors import ApiError
from .models import Identity


ALL_ROLES = frozenset(
    {"PDD_VIEWER", "PDD_BUYER", "PDD_SUPERVISOR", "PDD_AUDITOR", "PDD_TECHNICAL"}
)
EDIT_ROLES = frozenset({"PDD_BUYER", "PDD_SUPERVISOR"})
SUPERVISOR_ROLES = frozenset({"PDD_SUPERVISOR"})


@dataclass(frozen=True, slots=True)
class SecuritySettings:
    mode: str
    proxy_secret: str | None

    @classmethod
    def from_env(cls) -> "SecuritySettings":
        mode = os.getenv("PDD_API_AUTH_MODE", "proxy").strip().lower()
        if mode not in {"proxy", "test"}:
            raise RuntimeError("PDD_API_AUTH_MODE debe ser proxy o test")
        secret = os.getenv("PDD_API_PROXY_SECRET")
        if mode == "proxy" and (secret is None or len(secret) < 16):
            raise RuntimeError(
                "PDD_API_PROXY_SECRET debe tener al menos 16 caracteres en modo proxy"
            )
        if mode == "test" and os.getenv("PDD_API_ALLOW_TEST_AUTH", "false").lower() != "true":
            raise RuntimeError(
                "El modo test requiere PDD_API_ALLOW_TEST_AUTH=true de forma explícita"
            )
        return cls(mode=mode, proxy_secret=secret)


class Authenticator:
    def __init__(self, settings: SecuritySettings) -> None:
        self._settings = settings

    def __call__(
        self,
        authorization: str | None = Header(default=None, alias="Authorization"),
        user_id: str | None = Header(default=None, alias="X-Connexa-User"),
        role_header: str | None = Header(default=None, alias="X-Connexa-Roles"),
        supplied_secret: str | None = Header(default=None, alias="X-PDD-Proxy-Secret"),
        test_user: str | None = Header(default=None, alias="X-PDD-Test-User"),
        test_roles: str | None = Header(default=None, alias="X-PDD-Test-Roles"),
    ) -> Identity:
        if self._settings.mode == "test":
            user_id = test_user or "frontend.test"
            role_header = test_roles or "PDD_SUPERVISOR"
        else:
            if authorization is None or not authorization.startswith("Bearer "):
                raise ApiError(401, "UNAUTHENTICATED", "Falta el token Bearer")
            if supplied_secret is None or not hmac.compare_digest(
                supplied_secret, self._settings.proxy_secret or ""
            ):
                raise ApiError(401, "UNAUTHENTICATED", "Solicitud fuera del proxy confiable")
        if not user_id:
            raise ApiError(401, "UNAUTHENTICATED", "No se recibió la identidad corporativa")
        roles = frozenset(
            role.strip().upper() for role in (role_header or "").split(",") if role.strip()
        )
        if not roles.intersection(ALL_ROLES):
            raise ApiError(403, "FORBIDDEN", "La identidad no posee un rol PDD")
        return Identity(user_id=user_id, roles=roles)


def require_roles(identity: Identity, allowed: frozenset[str]) -> None:
    if not identity.roles.intersection(allowed):
        raise ApiError(403, "FORBIDDEN", "La operación no está permitida para el rol actual")
