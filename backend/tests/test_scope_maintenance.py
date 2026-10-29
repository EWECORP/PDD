from __future__ import annotations

from types import SimpleNamespace

import pytest

from pdd_backend.jobs.scope_maintenance import (
    _guard_change,
    _pair_churn_percent,
    ensure_daily_scope,
)


def test_automatic_scope_rotation_accepts_small_exclusion_change(monkeypatch) -> None:
    monkeypatch.delenv("PDD_AUTO_SCOPE_MAX_AFFECTED_BRANCHES", raising=False)
    monkeypatch.delenv("PDD_AUTO_SCOPE_MAX_DELTA_PERCENT", raising=False)
    _guard_change(
        {"article_count": 2524, "pair_count": 46680},
        {"article_count": 2524, "pair_count": 46643},
        excluded_branches=2,
    )


def test_automatic_scope_rotation_stops_large_change(monkeypatch) -> None:
    monkeypatch.setenv("PDD_AUTO_SCOPE_MAX_DELTA_PERCENT", "2")
    with pytest.raises(RuntimeError, match="pair_count varia"):
        _guard_change(
            {"article_count": 2524, "pair_count": 46680},
            {"article_count": 2524, "pair_count": 45000},
            excluded_branches=2,
        )


def test_automatic_scope_rotation_stops_many_new_exclusions(monkeypatch) -> None:
    monkeypatch.setenv("PDD_AUTO_SCOPE_MAX_AFFECTED_BRANCHES", "1")
    with pytest.raises(RuntimeError, match="sucursales afectadas exceden"):
        _guard_change(
            {"article_count": 2524, "pair_count": 46680},
            {"article_count": 2524, "pair_count": 46643},
            excluded_branches=2,
        )


def test_automatic_scope_rotation_can_be_disabled_without_opening_database(monkeypatch) -> None:
    monkeypatch.setenv("PDD_AUTO_SCOPE_ENABLED", "false")
    result = ensure_daily_scope(SimpleNamespace(runtime_environment="PROD"), lambda *_: None)
    assert result == {"status": "SKIPPED", "reason": "AUTO_SCOPE_DISABLED"}


def test_pair_churn_detects_replacement_even_when_counts_match() -> None:
    assert _pair_churn_percent(1000, 1000, 10000) == 20
