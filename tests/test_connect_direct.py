from wssh.connect import _direct_ssh_base, probe_direct_ssh


def test_direct_ssh_base_includes_connect_timeout() -> None:
    cmd = _direct_ssh_base(22)
    assert "ConnectTimeout=15" in " ".join(cmd)


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
