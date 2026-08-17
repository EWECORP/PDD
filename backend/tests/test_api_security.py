from __future__ import annotations

import pytest

from pdd_backend.api.cursor import CursorCodec, CursorPayload
from pdd_backend.api.errors import ApiError
from pdd_backend.api.security import Authenticator, SecuritySettings


def test_cursor_is_signed_and_detects_tampering() -> None:
    codec = CursorCodec("cursor-secret-with-more-than-sixteen")
    payload = CursorPayload("snapshot", "priority_desc", ("100", "abc"))
    token = codec.encode(payload)
    assert codec.decode(token) == payload
    replacement = "A" if token[-1] != "A" else "B"
    with pytest.raises(ApiError, match="pageCursor"):
        codec.decode(token[:-1] + replacement)


def test_proxy_authentication_is_fail_closed() -> None:
    authenticator = Authenticator(
        SecuritySettings(mode="proxy", proxy_secret="proxy-secret-123456789")
    )
    with pytest.raises(ApiError) as missing:
        authenticator(
            authorization=None,
            user_id=None,
            role_header=None,
            supplied_secret=None,
            test_user=None,
            test_roles=None,
        )
    assert missing.value.status_code == 401

    identity = authenticator(
        authorization="Bearer opaque-jwt",
        user_id="eduardo.ettlin",
        role_header="PDD_VIEWER,PDD_BUYER",
        supplied_secret="proxy-secret-123456789",
        test_user=None,
        test_roles=None,
    )
    assert identity.user_id == "eduardo.ettlin"
    assert "PDD_BUYER" in identity.roles


def test_test_auth_requires_explicit_enable(monkeypatch) -> None:
    monkeypatch.setenv("PDD_API_AUTH_MODE", "test")
    monkeypatch.delenv("PDD_API_ALLOW_TEST_AUTH", raising=False)
    with pytest.raises(RuntimeError, match="ALLOW_TEST_AUTH"):
        SecuritySettings.from_env()
