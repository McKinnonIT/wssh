from wssh.config import WsshConfig
from wssh.connect import (
    _bastion_ssh_cmd,
    _direct_ssh_base,
    probe_direct_ssh,
    run_ssh_capture,
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

    # The interactive path must stay interactive — password auth is still valid there.
    assert "BatchMode=yes" not in _bastion_ssh_cmd(config, "fms03", [])


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
