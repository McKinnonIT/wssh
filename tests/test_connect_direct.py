from wssh.config import WsshConfig
from wssh.connect import (
    _bastion_ssh_cmd,
    _direct_ssh_base,
    probe_direct_ssh,
    run_ssh_capture,
    ssh_env,
)


def test_direct_ssh_base_includes_connect_timeout() -> None:
    cmd = _direct_ssh_base(22)
    assert "ConnectTimeout=15" in " ".join(cmd)


def test_captured_ssh_never_prompts(monkeypatch) -> None:
    """A prompt written to a captured pipe is invisible and hangs the terminal."""
    config = WsshConfig(user="a@x.com", host="bastion", port=2222)
    seen: dict = {}

    class Result:
        returncode, stdout, stderr = 255, "", "denied"

    def fake_run(cmd, **kwargs):
        seen["cmd"], seen["kwargs"] = cmd, kwargs
        return Result()

    monkeypatch.setattr("wssh.connect.subprocess.run", fake_run)
    run_ssh_capture(config, "fms03", ["true"])
    assert "BatchMode=yes" in seen["cmd"]
    assert seen["kwargs"].get("stdin") is not None, "captured ssh must not inherit stdin"

    # The interactive path stays interactive, but still cannot reach a password prompt.
    assert "BatchMode=yes" not in _bastion_ssh_cmd(config, "fms03", [])


def test_bastion_never_offers_password_auth() -> None:
    """wssh registers your key with Warpgate; a password prompt is never the way in."""
    cmd = _bastion_ssh_cmd(WsshConfig(user="a@x.com", host="bastion", port=2222), "fms03", [])
    assert "PreferredAuthentications=publickey" in cmd


def test_setup_server_bootstrap_still_allows_a_password() -> None:
    """Installing Warpgate's keys on a fresh host is exactly when a password is needed."""
    cmd = " ".join(_direct_ssh_base(22))
    assert "PreferredAuthentications" not in cmd
    assert "BatchMode=no" in cmd


def test_probe_direct_ssh_timeout(monkeypatch) -> None:
    class Result:
        returncode = 255
        stdout = ""
        stderr = "ssh: connect to host x port 22: Operation timed out"

    monkeypatch.setattr(
        "wssh.connect.subprocess.run",
        lambda *args, **kwargs: Result(),
    )
    assert probe_direct_ssh("u", "h", 22) == "timeout"


def test_ghostty_term_is_downgraded_for_the_remote(monkeypatch) -> None:
    """Remote hosts have no xterm-ghostty terminfo, and ghostty's own fix is a shell function."""
    monkeypatch.setenv("TERM", "xterm-ghostty")
    monkeypatch.delenv("WSSH_TERM", raising=False)
    assert (ssh_env() or {})["TERM"] == "xterm-256color"

    monkeypatch.setenv("WSSH_TERM", "screen-256color")
    assert (ssh_env() or {})["TERM"] == "screen-256color"

    # Opt out once the terminfo entry is installed on the far side.
    monkeypatch.setenv("WSSH_TERM", "")
    assert ssh_env() is None

    # A TERM every host already knows is left alone — None means "inherit unchanged".
    monkeypatch.delenv("WSSH_TERM", raising=False)
    monkeypatch.setenv("TERM", "xterm-256color")
    assert ssh_env() is None
