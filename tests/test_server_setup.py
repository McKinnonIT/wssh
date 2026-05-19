from wssh.config import WsshConfig
from wssh.constants import SERVER_DOMAIN
from wssh.server_setup import (
    _build_authorized_keys_remote_cmd,
    _print_manual_keys_instructions,
    default_server_host,
    install_authorized_keys,
    prompt_server_connection,
)


def test_build_authorized_keys_remote_cmd() -> None:
    cmd = _build_authorized_keys_remote_cmd(["ssh-ed25519 AAA test"])
    assert "sudo chown" in cmd
    assert "mkdir -p ~/.ssh" in cmd
    assert "ssh-ed25519 AAA test" in cmd


def test_default_server_host_short_name() -> None:
    assert default_server_host("dns01", SERVER_DOMAIN) == f"dns01.{SERVER_DOMAIN}"


def test_default_server_host_fqdn_unchanged() -> None:
    fqdn = "dns01.example.com"
    assert default_server_host(fqdn, SERVER_DOMAIN) == fqdn


def test_prompt_server_connection_accepts_defaults(monkeypatch) -> None:
    config = WsshConfig(default_ssh_user="sysadmin", default_ssh_port=22)
    monkeypatch.setattr("wssh.server_setup.Confirm.ask", lambda *a, **k: True)
    prompted: list[str] = []
    monkeypatch.setattr(
        "wssh.server_setup.Prompt.ask",
        lambda msg, **k: prompted.append(msg) or "",
    )
    host, user, port = prompt_server_connection(config, "dns02")
    assert host == f"dns02.{SERVER_DOMAIN}"
    assert user == "sysadmin"
    assert port == 22
    assert prompted == []


def test_prompt_server_connection_custom_values(monkeypatch) -> None:
    config = WsshConfig(default_ssh_user="sysadmin", default_ssh_port=22)
    monkeypatch.setattr("wssh.server_setup.Confirm.ask", lambda *a, **k: False)
    answers = iter(["custom.host", "root", "2222"])
    monkeypatch.setattr(
        "wssh.server_setup.Prompt.ask",
        lambda msg, **k: next(answers),
    )
    host, user, port = prompt_server_connection(config, "dns02")
    assert host == "custom.host"
    assert user == "root"
    assert port == 2222


def test_install_authorized_keys_timeout_returns_false(monkeypatch) -> None:
    monkeypatch.setattr("wssh.server_setup.probe_direct_ssh", lambda *args: "timeout")
    monkeypatch.setattr("wssh.server_setup.Confirm.ask", lambda *a, **k: False)
    assert (
        install_authorized_keys(
            "sysadmin",
            "pangolin.noddy.example.com",
            22,
            ["ssh-ed25519 AAA test"],
            target_name="pangolin",
        )
        is False
    )


def test_install_authorized_keys_failure_returns_false(monkeypatch) -> None:
    monkeypatch.setattr("wssh.server_setup.probe_direct_ssh", lambda *args: "auth")
    monkeypatch.setattr("wssh.server_setup.run_direct_ssh", lambda *a, **k: 1)
    monkeypatch.setattr("wssh.server_setup.Confirm.ask", lambda *a, **k: False)
    assert (
        install_authorized_keys(
            "sysadmin",
            "zabbix02.noddy.example.com",
            22,
            ["ssh-ed25519 AAA test"],
            target_name="zabbix02",
        )
        is False
    )


def test_manual_keys_instructions_use_clipboard_when_available(monkeypatch) -> None:
    copied: list[list[str]] = []
    printed: list[str] = []
    monkeypatch.setattr(
        "wssh.server_setup._copy_lines_to_clipboard",
        lambda lines: copied.append(lines) or True,
    )
    monkeypatch.setattr(
        "wssh.server_setup._print_copyable_key_line",
        lambda key: printed.append(key),
    )
    monkeypatch.setattr(
        "wssh.server_setup.console.print",
        lambda msg, **k: None,
    )
    _print_manual_keys_instructions(
        "sysadmin",
        ["ssh-ed25519 AAA warpgate", "ssh-rsa BBB warpgate"],
        host="pangolin.noddy.example.com",
        target_name="pangolin",
    )
    assert copied == [["ssh-ed25519 AAA warpgate", "ssh-rsa BBB warpgate"]]
    assert printed == []


def test_install_authorized_keys_failure_shows_instructions_when_asked(monkeypatch) -> None:
    monkeypatch.setattr("wssh.server_setup.probe_direct_ssh", lambda *args: "ok")
    monkeypatch.setattr("wssh.server_setup.run_direct_ssh", lambda *a, **k: 1)
    monkeypatch.setattr("wssh.server_setup.Confirm.ask", lambda *a, **k: True)
    monkeypatch.setattr("wssh.server_setup._copy_lines_to_clipboard", lambda lines: False)
    stdout_keys: list[str] = []
    monkeypatch.setattr(
        "wssh.server_setup._print_copyable_key_line",
        lambda key: stdout_keys.append(key),
    )
    printed: list[str] = []
    monkeypatch.setattr(
        "wssh.server_setup.console.print",
        lambda msg, **k: printed.append(str(msg)),
    )
    assert (
        install_authorized_keys(
            "sysadmin",
            "zabbix02.noddy.example.com",
            22,
            ["ssh-ed25519 AAA test"],
            target_name="zabbix02",
        )
        is False
    )
    blob = "\n".join(printed)
    assert "Manual steps" in blob
    assert stdout_keys == ["ssh-ed25519 AAA test"]


def test_install_authorized_keys_runs_remote_cmd(monkeypatch) -> None:
    monkeypatch.setattr("wssh.server_setup.probe_direct_ssh", lambda *args: "ok")
    calls: list[tuple] = []

    def fake_run_direct_ssh(user, host, port, remote_command, **kwargs):
        calls.append((user, host, port, remote_command, kwargs))
        return 0

    monkeypatch.setattr("wssh.server_setup.run_direct_ssh", fake_run_direct_ssh)
    assert install_authorized_keys(
        "sysadmin",
        "dns02.example.com",
        22,
        ["ssh-ed25519 AAA test"],
    )
    assert len(calls) == 1
    assert calls[0][0] == "sysadmin"
    assert "ssh-ed25519 AAA test" in calls[0][3]
