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


def test_runtime_activation_cli_requires_audited_fields() -> None:
    parser = cli.build_parser()
    args = parser.parse_args(
        [
            "runtime-config",
            "activate",
            "--environment",
            "TEST",
            "--scope-version-uuid",
            "11111111-1111-1111-1111-111111111111",
            "--model-version-uuid",
            "22222222-2222-2222-2222-222222222222",
            "--configuration-version-uuid",
            "33333333-3333-3333-3333-333333333333",
            "--pipeline-revision",
            "DAILY_PIPELINE_V3",
            "--effective-business-date",
            "2026-09-23",
            "--activated-by",
            "test.user",
            "--reason",
            "validated",
        ]
    )

    assert args.runtime_command == "activate"
    assert args.effective_business_date == date(2026, 9, 23)
    assert args.activated_by == "test.user"
