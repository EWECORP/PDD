from datetime import date

from pdd_backend import cli


def test_scope_snapshot_cli_passes_declared_arguments(monkeypatch, capsys) -> None:
    captured: dict = {}

    def fake_scope_snapshot_flow(*args):
        captured["args"] = args
        return {"status": "ok"}

    monkeypatch.setattr(cli, "pdd_scope_snapshot_flow", fake_scope_snapshot_flow)
    monkeypatch.setattr(
        "sys.argv",
        [
            "pdd-etl",
            "scope-snapshot",
            "--scope-version-uuid",
            "11111111-1111-1111-1111-111111111111",
            "--version-no",
            "6",
            "--business-date",
            "2026-09-23",
            "--captured-by",
            "test.user",
            "--supersedes-scope-version-uuid",
            "22222222-2222-2222-2222-222222222222",
        ],
    )

    cli.main()

    assert captured["args"] == (
        "11111111-1111-1111-1111-111111111111",
        6,
        date(2026, 9, 23),
        "test.user",
        "22222222-2222-2222-2222-222222222222",
    )
    assert '"status": "ok"' in capsys.readouterr().out
