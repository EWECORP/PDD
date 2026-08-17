from __future__ import annotations

import base64
import hashlib
import hmac
import json
from dataclasses import dataclass
from typing import Any

from .errors import ApiError


@dataclass(frozen=True, slots=True)
class CursorPayload:
    snapshot: str
    sort: str
    values: tuple[Any, ...]


class CursorCodec:
    def __init__(self, secret: str) -> None:
        if len(secret) < 16:
            raise RuntimeError("PDD_API_CURSOR_SECRET debe tener al menos 16 caracteres")
        self._secret = secret.encode("utf-8")

    def encode(self, payload: CursorPayload) -> str:
        raw = json.dumps(
            {"snapshot": payload.snapshot, "sort": payload.sort, "values": payload.values},
            separators=(",", ":"),
            ensure_ascii=True,
        ).encode("utf-8")
        signature = hmac.new(self._secret, raw, hashlib.sha256).digest()
        return base64.urlsafe_b64encode(raw + signature).decode("ascii").rstrip("=")

    def decode(self, token: str) -> CursorPayload:
        try:
            padded = token + "=" * (-len(token) % 4)
            signed = base64.urlsafe_b64decode(padded.encode("ascii"))
            raw, supplied = signed[:-32], signed[-32:]
            expected = hmac.new(self._secret, raw, hashlib.sha256).digest()
            if not hmac.compare_digest(supplied, expected):
                raise ValueError("firma")
            value = json.loads(raw.decode("utf-8"))
            return CursorPayload(
                snapshot=str(value["snapshot"]),
                sort=str(value["sort"]),
                values=tuple(value["values"]),
            )
        except (ValueError, KeyError, TypeError, UnicodeError, json.JSONDecodeError) as exc:
            raise ApiError(400, "INVALID_QUERY", "pageCursor es inválido") from exc
