from __future__ import annotations

import pytest

from pdd_backend import db
from pdd_backend import execution_limits
from pdd_backend.config import OperationalSettings, Settings
from tools.inspect_db_contention import classify_activity


def _settings() -> Settings:
    return Settings(
        pg_host="localhost", pg_port=5432, pg_database="diarco_data",
        pg_user="pdd", pg_password="secret", runtime_environment="PROD",
    )


def test_all_engine_connections_receive_server_side_limits(monkeypatch) -> None:
    calls = []

    def capture_engine(url, **kwargs):
        calls.append(kwargs)
        return kwargs

    monkeypatch.setattr(db, "create_engine", capture_engine)
    db.build_engine(_settings())
    db.build_operational_engine(
        OperationalSettings(
            pg_host="localhost", pg_port=5432,
            pg_database="connexa_platform_ms", pg_user="pdd",
            pg_password="secret", target_environment="PROD",
        )
    )

    assert [c["connect_args"]["application_name"] for c in calls] == [
        "pdd_prod_source", "pdd_prod_target",
    ]
    for call in calls:
        args = call["connect_args"]
        assert args["connect_timeout"] == 10
        assert "statement_timeout=1800000" in args["options"]
        assert "lock_timeout=30000" in args["options"]
        assert "idle_in_transaction_session_timeout=600000" in args["options"]


class _Connection:
    def __init__(self, *, acquired: bool):
        self.acquired = acquired
        self.calls = []
        self.invalidated = False

    def execution_options(self, **kwargs):
        assert kwargs == {"isolation_level": "AUTOCOMMIT"}
        return self

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def scalar(self, statement, params):
        self.calls.append((str(statement), params))
        if "pg_try_advisory_lock" in str(statement):
            return self.acquired
        return True

    def invalidate(self):
        self.invalidated = True


class _Engine:
    def __init__(self, connection):
        self.connection = connection
        self.disposed = False

    def connect(self):
        return self.connection

    def dispose(self):
        self.disposed = True


def test_daily_master_lock_releases_after_failure(monkeypatch) -> None:
    connection = _Connection(acquired=True)
    engine = _Engine(connection)
    monkeypatch.setattr(db, "build_engine", lambda _settings: engine)

    with pytest.raises(ValueError, match="stage failed"):
        with db.daily_master_execution_lock(_settings()):
            raise ValueError("stage failed")

    assert len(connection.calls) == 2
    assert "pg_try_advisory_lock" in connection.calls[0][0]
    assert "pg_advisory_unlock" in connection.calls[1][0]
    assert engine.disposed


def test_daily_master_lock_fails_after_bounded_wait(monkeypatch) -> None:
    connection = _Connection(acquired=False)
    engine = _Engine(connection)
    now = [0.0]
    monkeypatch.setattr(db, "build_engine", lambda _settings: engine)
    monkeypatch.setattr(db, "monotonic", lambda: now[0])
    monkeypatch.setattr(db, "sleep", lambda seconds: now.__setitem__(0, now[0] + seconds))

    with pytest.raises(RuntimeError, match="SOURCE_DAILY_MASTER_BUSY"):
        with db.daily_master_execution_lock(_settings(), wait_seconds=2, poll_seconds=1):
            pytest.fail("La corrida no debe iniciar")

    assert now[0] == 2
    assert len(connection.calls) == 3
    assert all("pg_try_advisory_lock" in query for query, _ in connection.calls)
    assert engine.disposed


def test_contention_diagnostic_flags_pdd_and_affected_peer() -> None:
    rows = [
        {
            "pid": 10, "application_name": "pdd_prod_source",
            "state": "active", "wait_event_type": None, "wait_event": None,
            "blocking_pids": [], "query_age_seconds": 1_300,
            "state_age_seconds": 1_300,
        },
        {
            "pid": 11, "application_name": "nightly_etl",
            "state": "active", "wait_event_type": "Lock", "wait_event": "relation",
            "blocking_pids": [10], "query_age_seconds": 40,
            "state_age_seconds": 40,
        },
    ]
    visible, anomalies = classify_activity(
        rows, active_seconds=1_200, lock_seconds=30,
        idle_transaction_seconds=120,
    )
    assert len(visible) == 2
    assert anomalies[0]["reasons"] == ["LONG_PDD_STATEMENT"]
    assert anomalies[1]["reasons"] == ["LOCK_WAIT", "OTHER_PROCESS_BLOCKED_BY_PDD"]


def test_hard_deadline_escalates_when_flow_does_not_exit(monkeypatch) -> None:
    timers = []
    signals = []

    class FakeTimer:
        def __init__(self, seconds, callback, args=()):
            self.seconds, self.callback, self.args = seconds, callback, args
            self.cancelled = False
            timers.append(self)

        def start(self):
            pass

        def cancel(self):
            self.cancelled = True

        def fire(self):
            self.callback(*self.args)

    monkeypatch.setattr(execution_limits, "POSIX_SIGNALS_AVAILABLE", True)
    monkeypatch.setattr(execution_limits, "Timer", FakeTimer)
    monkeypatch.setattr(execution_limits.signal, "SIGKILL", 9, raising=False)
    monkeypatch.setattr(execution_limits.os, "getpid", lambda: 12345)
    monkeypatch.setattr(execution_limits.os, "kill", lambda pid, sig: signals.append((pid, sig)))

    with execution_limits.hard_process_deadline(timeout_seconds=9_900):
        assert timers[0].seconds == 9_900
        timers[0].fire()

    assert timers[0].cancelled
    assert timers[1].seconds == 30
    assert not timers[1].cancelled
    timers[1].fire()
    assert signals == [
        (12345, execution_limits.signal.SIGTERM),
        (12345, execution_limits.signal.SIGKILL),
    ]
