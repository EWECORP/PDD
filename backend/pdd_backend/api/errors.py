from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class ApiError(Exception):
    status_code: int
    code: str
    message: str
    title: str = "Error PDD"
    field_errors: list[dict[str, str]] = field(default_factory=list)
    headers: dict[str, str] = field(default_factory=dict)

    def __str__(self) -> str:
        return self.message


def not_found(entity: str) -> ApiError:
    return ApiError(404, "RESOURCE_NOT_FOUND", f"No existe {entity}")


def version_conflict(expected: int, actual: int) -> ApiError:
    return ApiError(
        409,
        "VERSION_CONFLICT",
        f"La versión esperada es {expected}, pero la vigente es {actual}",
    )
