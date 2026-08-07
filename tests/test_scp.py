from pathlib import Path

from wssh.config import WsshConfig
from wssh.connect import _split_scp_args, run_scp, split_remote

CONFIG = WsshConfig(user="sam@mckinnonsc.vic.edu.au", host="ssh.mckinnon.tech", port=2222)


def _record(monkeypatch) -> list[list[str]]:
    """Capture scp argv instead of running it; stage a file so leg two proceeds."""
    calls: list[list[str]] = []

    def fake_call(cmd, **kwargs):
        calls.append(cmd)
        dest = Path(cmd[-1])
        # Only ever write inside the staging directory — "." is a real destination here.
        if dest.name.startswith("wssh-scp-") and dest.is_dir():
            (dest / "file.txt").write_text("staged")
        return 0

    monkeypatch.setattr("wssh.connect.subprocess.call", fake_call)
    return calls


def test_split_remote() -> None:
    assert split_remote("docker04:~/file.txt") == ("docker04", "~/file.txt")
    assert split_remote("./local:name") is None  # slash first — a local path
    assert split_remote("/tmp/x") is None


def test_options_taking_a_value_are_not_paths() -> None:
    assert _split_scp_args(["-r", "-l", "100", "a", "b"]) == (["-r", "-l", "100"], ["a", "b"])


def test_target_becomes_the_ssh_user_not_the_host(monkeypatch) -> None:
    """Warpgate picks the target from the username; the host is always the bastion."""
    calls = _record(monkeypatch)
    assert run_scp(CONFIG, ["-r", "dns01:/etc/hosts", "."]) == 0
    (cmd,) = calls
    assert "User=sam@mckinnonsc.vic.edu.au:dns01" in cmd
    assert cmd[cmd.index("-P") + 1] == "2222"
    assert "ssh.mckinnon.tech:/etc/hosts" in cmd, "target: is rewritten to the bastion host:"
    assert cmd[-2:] == ["ssh.mckinnon.tech:/etc/hosts", "."]
    assert "-r" in cmd


def test_cross_target_copy_stages_locally(monkeypatch) -> None:
    """One scp reaches one target, so target-to-target is two copies via local disk."""
    calls = _record(monkeypatch)
    assert run_scp(CONFIG, ["docker04:~/file.txt", "docker02:~/"]) == 0
    pull, push = calls
    assert "User=sam@mckinnonsc.vic.edu.au:docker04" in pull
    assert "User=sam@mckinnonsc.vic.edu.au:docker02" in push
    assert pull[-2] == "ssh.mckinnon.tech:~/file.txt"
    assert Path(pull[-1]).name.startswith("wssh-scp-"), "pulled into a staging directory"
    assert Path(push[-2]).name == "file.txt", "staged file is pushed on by name"
    assert push[-1] == "ssh.mckinnon.tech:~/"


def test_partial_pull_still_pushes_what_copied(monkeypatch, capsys) -> None:
    """scp -r exits non-zero on one unreadable file — that must not discard the rest."""
    calls: list[list[str]] = []

    def fake_call(cmd, **kwargs):
        calls.append(cmd)
        dest = Path(cmd[-1])
        if dest.name.startswith("wssh-scp-"):
            (dest / "guacamole-ap").mkdir()
            return 1  # some files were unreadable
        return 0

    monkeypatch.setattr("wssh.connect.subprocess.call", fake_call)
    code = run_scp(CONFIG, ["-r", "docker02:/apps/guacamole-ap", "docker04:/apps/"])
    assert len(calls) == 2, "the push must still run"
    assert code == 1, "an incomplete copy must not report success"
    err = capsys.readouterr().err
    assert "was incomplete" in err and "missing files" in err


def test_pull_that_copied_nothing_does_not_touch_the_destination(monkeypatch, capsys) -> None:
    calls: list[list[str]] = []
    monkeypatch.setattr(
        "wssh.connect.subprocess.call", lambda cmd, **k: calls.append(cmd) or 1
    )
    assert run_scp(CONFIG, ["-r", "docker02:/apps/x", "docker04:/apps/"]) == 1
    assert len(calls) == 1, "nothing staged — the destination must be left alone"
    assert "was not touched" in capsys.readouterr().err


def test_three_targets_is_refused(monkeypatch) -> None:
    calls = _record(monkeypatch)
    assert run_scp(CONFIG, ["a01:/f", "b01:/f", "c01:/tmp/"]) == 1
    assert not calls, "no half-done copy when the request cannot be honoured"


def test_two_local_paths_is_refused(monkeypatch) -> None:
    calls = _record(monkeypatch)
    assert run_scp(CONFIG, ["/tmp/a", "/tmp/b"]) == 1
    assert not calls
