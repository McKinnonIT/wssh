import pytest

from wssh.connect import classify_ssh_failure


def test_unknown_target() -> None:
    assert classify_ssh_failure("Warpgate: unknown target dns01") == "unknown_target"


def test_auth_failure() -> None:
    assert classify_ssh_failure("Permission denied (publickey)") == "auth_failure"


def test_warpgate_rejected_authentication() -> None:
    assert (
        classify_ssh_failure("SSH target rejected Warpgate authentication request")
        == "auth_failure"
    )


def test_remote_command_exit_code_is_not_diagnosed(monkeypatch, capsys) -> None:
    """A command that exits non-zero has connected fine — no probe, no hint."""
    from wssh import cli
    from wssh.config import WsshConfig

    monkeypatch.setattr(cli, "_config", lambda: WsshConfig(user="u@x", host="h"))
    monkeypatch.setattr(cli, "get_target_names", lambda config, **k: ["dns01"])
    monkeypatch.setattr(cli, "run_ssh", lambda config, target, args: 7)
    monkeypatch.setattr(
        cli, "run_ssh_capture", lambda *a, **k: pytest.fail("probed a working connection")
    )

    assert cli.connect("dns01", ["false"]) == 7
    assert capsys.readouterr().out == ""


def test_connection_failure_is_diagnosed_on_stderr(monkeypatch, capsys) -> None:
    from wssh import cli
    from wssh.config import WsshConfig

    monkeypatch.setattr(cli, "_config", lambda: WsshConfig(user="u@x", host="h"))
    monkeypatch.setattr(cli, "get_target_names", lambda config, **k: ["dns01"])
    monkeypatch.setattr(cli, "run_ssh", lambda config, target, args: 255)
    monkeypatch.setattr(
        cli, "run_ssh_capture", lambda *a, **k: (255, "", "Permission denied (publickey)")
    )
    monkeypatch.setattr(cli, "_offer_setup", lambda *a: False)

    assert cli.connect("dns01", ["true"]) == 255
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "Authentication failed" in captured.err
