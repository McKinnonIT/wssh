from pathlib import Path

import pytest

from wssh.config import WsshConfig
from wssh.connect import _split_scp_args, run_scp, split_remote
from wssh.warpgate import WarpgateApiError

CONFIG = WsshConfig(user="sam@mckinnonsc.vic.edu.au", host="ssh.mckinnon.tech", port=2222)
KNOWN = ["a01", "b01", "c01", "dns01", "docker02", "docker04", "fms03"]


@pytest.fixture(autouse=True)
def known_targets(monkeypatch):
    """Never read the developer's own target cache to decide what a test target is."""
    monkeypatch.setattr("wssh.connect.get_target_names", lambda config, **k: list(KNOWN))


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


def test_user_at_target_is_named_as_the_mistake(monkeypatch, capsys) -> None:
    """Warpgate reads the username as the target, so user@target used to come back
    as a bare 'Permission denied' naming neither problem."""
    calls = _record(monkeypatch)
    assert run_scp(CONFIG, ["-r", "sysadmin@fms03:/opt/db/", "."]) == 1
    assert not calls, "no point connecting — Warpgate cannot honour a user in the spec"
    err = capsys.readouterr().err
    assert "sysadmin@fms03" in err and "use 'fms03:'" in err


def test_user_at_unknown_host_still_explains_the_rule(monkeypatch, capsys) -> None:
    _record(monkeypatch)
    assert run_scp(CONFIG, ["root@nowhere:/etc/hosts", "."]) == 1
    err = capsys.readouterr().err
    assert "target name on its own" in err


def test_typo_in_a_target_is_suggested(monkeypatch, capsys) -> None:
    calls = _record(monkeypatch)
    assert run_scp(CONFIG, ["dns0:/etc/hosts", "."]) == 1
    assert not calls
    assert "Did you mean dns01?" in capsys.readouterr().err


def test_unreadable_target_list_never_blocks_a_copy(monkeypatch) -> None:
    """A cold cache and an unreachable API must not be why a copy refuses to run."""
    calls = _record(monkeypatch)

    def unreachable(config, **kwargs):
        raise WarpgateApiError("connection refused")

    monkeypatch.setattr("wssh.connect.get_target_names", unreachable)
    assert run_scp(CONFIG, ["-r", "whatever:/etc/hosts", "."]) == 0
    assert len(calls) == 1
