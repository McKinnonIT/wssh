from wssh.config import WsshConfig
from wssh.server_setup import (
    _authorized_keys_remote_cmd,
    _print_keys_install_blocked,
    default_server_host,
    install_authorized_keys,
    prompt_server_connection,
)


def test_build_authorized_keys_remote_cmd() -> None:
    cmd = _authorized_keys_remote_cmd(["ssh-ed25519 AAA test"])
    assert "sudo chown" in cmd
    assert "mkdir -p ~/.ssh" in cmd
    assert "ssh-ed25519 AAA test" in cmd


SERVER_DOMAIN = "internal.example.com"


def test_default_server_host_short_name() -> None:
    assert default_server_host("dns01", SERVER_DOMAIN) == f"dns01.{SERVER_DOMAIN}"


def test_default_server_host_fqdn_unchanged() -> None:
    fqdn = "dns01.example.com"
    assert default_server_host(fqdn, SERVER_DOMAIN) == fqdn


def test_default_server_host_without_suffix() -> None:
    assert default_server_host("dns01", "") == "dns01"


def test_prompt_server_connection_accepts_defaults(monkeypatch) -> None:
    config = WsshConfig(
        server_domain=SERVER_DOMAIN,
        default_ssh_user="deploy",
        default_ssh_port=22,
    )
    monkeypatch.setattr("wssh.server_setup.Confirm.ask", lambda *a, **k: True)
    prompted: list[str] = []
    monkeypatch.setattr(
        "wssh.server_setup.Prompt.ask",
        lambda msg, **k: prompted.append(msg) or "",
    )
    host, user, port = prompt_server_connection(config, "dns02")
    assert host == f"dns02.{SERVER_DOMAIN}"
    assert user == "deploy"
    assert port == 22
    assert prompted == []


def test_prompt_server_connection_custom_values(monkeypatch) -> None:
    config = WsshConfig(default_ssh_user="deploy", default_ssh_port=22)
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
    monkeypatch.setattr("wssh.server_setup.copy_to_clipboard", lambda text: True)
    assert (
        install_authorized_keys(
            "deploy", "pangolin.internal.example.com", 22, ["ssh-ed25519 AAA test"]
        )
        is False
    )


def test_install_authorized_keys_failure_returns_false(monkeypatch) -> None:
    monkeypatch.setattr("wssh.server_setup.probe_direct_ssh", lambda *args: "auth")
    monkeypatch.setattr("wssh.server_setup.run_direct_ssh", lambda *a, **k: 1)
    monkeypatch.setattr("wssh.server_setup.copy_to_clipboard", lambda text: True)
    assert (
        install_authorized_keys(
            "deploy", "zabbix02.internal.example.com", 22, ["ssh-ed25519 AAA test"]
        )
        is False
    )


def test_unreachable_host_names_the_network_as_the_cause(monkeypatch) -> None:
    """No credential fixes an unreachable host — don't let the user hunt for one."""
    monkeypatch.setattr("wssh.server_setup.probe_direct_ssh", lambda *a: "timeout")
    monkeypatch.setattr("wssh.server_setup.copy_to_clipboard", lambda text: True)
    printed: list[str] = []
    monkeypatch.setattr(
        "wssh.server_setup.console.print", lambda msg="", **k: printed.append(str(msg))
    )
    assert (
        install_authorized_keys(
            "sysadmin", "fms03.internal", 22, ["ssh-ed25519 AAA x"], target_name="fms03"
        )
        is False
    )
    blob = "\n".join(printed)
    assert "network or VPN" in blob
    assert "port 22 never answered" in blob
    assert "wssh setup-server fms03" in blob


def test_reachable_host_still_attempts_a_password_login(monkeypatch) -> None:
    """Installing keys on a host that lacks them is exactly when a password is needed."""
    monkeypatch.setattr("wssh.server_setup.probe_direct_ssh", lambda *a: "auth")
    monkeypatch.setattr("wssh.server_setup.copy_to_clipboard", lambda text: True)
    monkeypatch.setattr("wssh.server_setup.console.print", lambda *a, **k: None)
    attempts: list[tuple] = []
    monkeypatch.setattr(
        "wssh.server_setup.run_direct_ssh",
        lambda user, host, port, cmd, **k: attempts.append((user, host)) or 1,
    )
    install_authorized_keys("sysadmin", "fms03.internal", 22, ["ssh-ed25519 AAA x"])
    assert attempts, "a reachable host must still get an interactive login attempt"
    assert attempts[0] == ("sysadmin", "fms03.internal")


def test_blocked_keys_use_clipboard_when_available(monkeypatch, capsys) -> None:
    copied: list[str] = []
    monkeypatch.setattr(
        "wssh.server_setup.copy_to_clipboard",
        lambda text: copied.append(text) or True,
    )
    monkeypatch.setattr("wssh.server_setup.console.print", lambda *a, **k: None)
    _print_keys_install_blocked(
        "deploy@pangolin.internal.example.com",
        "deploy",
        ["ssh-ed25519 AAA warpgate", "ssh-rsa BBB warpgate"],
        reason="timeout",
    )
    assert copied == ["ssh-ed25519 AAA warpgate\nssh-rsa BBB warpgate"]
    assert capsys.readouterr().out == ""


def test_blocked_keys_printed_when_clipboard_unavailable(monkeypatch, capsys) -> None:
    monkeypatch.setattr("wssh.server_setup.probe_direct_ssh", lambda *args: "ok")
    monkeypatch.setattr("wssh.server_setup.run_direct_ssh", lambda *a, **k: 1)
    monkeypatch.setattr("wssh.server_setup.copy_to_clipboard", lambda text: False)
    printed: list[str] = []
    monkeypatch.setattr(
        "wssh.server_setup.console.print",
        lambda msg="", **k: printed.append(str(msg)),
    )
    assert (
        install_authorized_keys(
            "deploy", "zabbix02.internal.example.com", 22, ["ssh-ed25519 AAA test"]
        )
        is False
    )
    assert "To install by hand" in "\n".join(printed)
    # The key itself goes to plain stdout so Rich cannot wrap it mid-line.
    assert capsys.readouterr().out.splitlines() == ["ssh-ed25519 AAA test"]


def test_install_authorized_keys_runs_remote_cmd(monkeypatch) -> None:
    monkeypatch.setattr("wssh.server_setup.probe_direct_ssh", lambda *args: "ok")
    calls: list[tuple] = []

    def fake_run_direct_ssh(user, host, port, remote_command, **kwargs):
        calls.append((user, host, port, remote_command, kwargs))
        return 0

    monkeypatch.setattr("wssh.server_setup.run_direct_ssh", fake_run_direct_ssh)
    assert install_authorized_keys("deploy", "dns02.example.com", 22, ["ssh-ed25519 AAA test"])
    assert len(calls) == 1
    assert calls[0][0] == "deploy"
    assert "ssh-ed25519 AAA test" in calls[0][3]
