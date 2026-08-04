import json
import subprocess
import sys

import pytest

from wssh import update

LOCAL = "2db85ba8e248a9246bc5c50ad8240aa438524b2f"
REMOTE = "5c019d543904adcc6be00a42f2c35bd72bc89826"

# Bound before the autouse fixture stubs it out, so the tests that exercise
# ls-remote itself can still reach the real implementation.
real_remote_commit = update.remote_commit

VCS_RECORD = json.dumps(
    {
        "url": "https://github.com/McKinnonIT/wssh.git",
        "vcs_info": {"commit_id": LOCAL, "vcs": "git"},
    }
)
DIR_RECORD = json.dumps({"url": "file:///home/sam/wssh", "dir_info": {}})


@pytest.fixture(autouse=True)
def isolate(monkeypatch, tmp_path):
    """Never touch the real cache, the network, or the user's environment."""
    monkeypatch.setattr(update, "cache_path", lambda: tmp_path / "update.json")
    monkeypatch.delenv("WSSH_NO_UPDATE_CHECK", raising=False)
    monkeypatch.delenv("WSSH_REPO", raising=False)
    monkeypatch.setattr(
        update, "remote_commit", lambda *a: pytest.fail("unexpected network call")
    )


def set_record(monkeypatch, raw: str | None) -> None:
    monkeypatch.setattr(update, "_direct_url", lambda: json.loads(raw) if raw else {})


# --- where this copy came from --------------------------------------------- #


def test_installed_commit_read_from_pip_record(monkeypatch) -> None:
    set_record(monkeypatch, VCS_RECORD)
    assert update.installed_commit() == LOCAL


def test_no_commit_for_a_non_git_install(monkeypatch) -> None:
    set_record(monkeypatch, DIR_RECORD)
    assert update.installed_commit() is None


def test_malformed_record_is_not_fatal(monkeypatch) -> None:
    monkeypatch.setattr(update, "distribution", lambda name: _FakeDist("{not json"))
    assert update.installed_commit() is None


class _FakeDist:
    def __init__(self, raw): self._raw = raw          # noqa: E704
    def read_text(self, name): return self._raw       # noqa: E704


def test_repo_url_precedence(monkeypatch) -> None:
    set_record(monkeypatch, VCS_RECORD)
    assert update.repo_url() == "https://github.com/McKinnonIT/wssh.git"
    monkeypatch.setenv("WSSH_REPO", "https://github.com/you/wssh.git")
    assert update.repo_url() == "https://github.com/you/wssh.git"


def test_local_dir_install_does_not_become_the_update_url(monkeypatch) -> None:
    """A file:// path is not necessarily a git repo — fall back to the default."""
    set_record(monkeypatch, DIR_RECORD)
    assert update.repo_url() == update.DEFAULT_REPO


# --- reading the remote ---------------------------------------------------- #


def test_remote_commit_parses_ls_remote(monkeypatch) -> None:
    calls = {}

    def fake_run(cmd, **kwargs):
        calls.update(cmd=cmd, env=kwargs["env"], timeout=kwargs["timeout"])
        return subprocess.CompletedProcess(cmd, 0, f"{REMOTE}\tHEAD\n", "")

    monkeypatch.setattr(update.subprocess, "run", fake_run)
    assert real_remote_commit("https://example.test/r.git") == REMOTE
    assert calls["cmd"] == ["git", "ls-remote", "https://example.test/r.git", "HEAD"]
    # A private repo or passphrased key must fail, not sit waiting for input.
    assert calls["env"]["GIT_TERMINAL_PROMPT"] == "0"
    assert "BatchMode=yes" in calls["env"]["GIT_SSH_COMMAND"]
    assert calls["timeout"] == update.LS_REMOTE_TIMEOUT


@pytest.mark.parametrize(
    "outcome",
    [
        subprocess.TimeoutExpired(cmd="git", timeout=5),
        OSError("git not installed"),
        subprocess.CompletedProcess("git", 128, "", "repository not found"),
    ],
)
def test_remote_commit_returns_none_when_it_cannot_read(monkeypatch, outcome) -> None:
    def fake_run(cmd, **kwargs):
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome

    monkeypatch.setattr(update.subprocess, "run", fake_run)
    assert real_remote_commit("https://example.test/r.git") is None


# --- the cached comparison ------------------------------------------------- #


def test_reports_a_differing_remote_commit(monkeypatch) -> None:
    set_record(monkeypatch, VCS_RECORD)
    monkeypatch.setattr(update, "remote_commit", lambda *a: REMOTE)
    assert update.check_for_update() == REMOTE


def test_silent_when_already_at_the_remote_commit(monkeypatch) -> None:
    set_record(monkeypatch, VCS_RECORD)
    monkeypatch.setattr(update, "remote_commit", lambda *a: LOCAL)
    assert update.check_for_update() is None


def test_second_call_uses_the_cache(monkeypatch) -> None:
    set_record(monkeypatch, VCS_RECORD)
    calls = []
    monkeypatch.setattr(update, "remote_commit", lambda *a: calls.append(1) or REMOTE)
    assert update.check_for_update() == REMOTE
    assert update.check_for_update() == REMOTE
    assert len(calls) == 1, "the network must be touched once per interval, not per run"


def test_force_bypasses_the_cache(monkeypatch) -> None:
    set_record(monkeypatch, VCS_RECORD)
    calls = []
    monkeypatch.setattr(update, "remote_commit", lambda *a: calls.append(1) or REMOTE)
    update.check_for_update()
    update.check_for_update(force=True)
    assert len(calls) == 2


def test_offline_check_is_not_retried_every_run(monkeypatch) -> None:
    set_record(monkeypatch, VCS_RECORD)
    calls = []
    monkeypatch.setattr(update, "remote_commit", lambda *a: calls.append(1) or None)
    assert update.check_for_update() is None
    assert update.check_for_update() is None
    assert len(calls) == 1, "a failed check must still be recorded"


def test_non_git_install_never_checks(monkeypatch) -> None:
    set_record(monkeypatch, DIR_RECORD)
    assert update.check_for_update() is None  # remote_commit would fail the test


def test_env_var_opts_out(monkeypatch) -> None:
    set_record(monkeypatch, VCS_RECORD)
    monkeypatch.setenv("WSSH_NO_UPDATE_CHECK", "1")
    assert update.check_for_update() is None  # remote_commit would fail the test


def test_clear_cache_forces_a_recheck(monkeypatch) -> None:
    set_record(monkeypatch, VCS_RECORD)
    calls = []
    monkeypatch.setattr(update, "remote_commit", lambda *a: calls.append(1) or REMOTE)
    update.check_for_update()
    update.clear_cache()
    update.check_for_update()
    assert len(calls) == 2


# --- the notice ------------------------------------------------------------ #


def test_notice_names_both_commits_and_the_command(monkeypatch, capsys) -> None:
    set_record(monkeypatch, VCS_RECORD)
    monkeypatch.setattr(update, "remote_commit", lambda *a: REMOTE)
    monkeypatch.setattr(sys.stderr, "isatty", lambda: True, raising=False)
    update.maybe_notify_update()
    printed = capsys.readouterr()
    assert printed.out == "", "the notice must not pollute stdout"
    assert "Update available" in printed.err
    assert LOCAL[:7] in printed.err and REMOTE[:7] in printed.err
    assert "wssh update" in printed.err


def test_notice_silent_when_stderr_is_not_a_tty(monkeypatch, capsys) -> None:
    set_record(monkeypatch, VCS_RECORD)
    monkeypatch.setattr(update, "remote_commit", lambda *a: REMOTE)
    monkeypatch.setattr(sys.stderr, "isatty", lambda: False, raising=False)
    update.maybe_notify_update()
    assert capsys.readouterr().err == ""


def test_notice_never_raises(monkeypatch) -> None:
    """A cosmetic check must not be the reason a connection fails."""
    monkeypatch.setattr(sys.stderr, "isatty", lambda: True, raising=False)
    monkeypatch.setattr(update, "check_for_update", lambda **k: 1 / 0)
    update.maybe_notify_update()


# --- version line ---------------------------------------------------------- #


def test_version_line_is_the_commit_alone(monkeypatch) -> None:
    """0.1.0 never moves, so printing it would only invite misplaced trust."""
    set_record(monkeypatch, VCS_RECORD)
    assert update.version_line() == LOCAL[:7]


def test_version_line_says_unknown_without_a_commit(monkeypatch) -> None:
    """A dir or PyPI-style install has no commit to name."""
    set_record(monkeypatch, DIR_RECORD)
    assert update.version_line() == "unknown"


def test_opt_out_also_covers_the_version_command(monkeypatch) -> None:
    """`wssh version` must not stall on the network for an air-gapped machine."""
    monkeypatch.delenv("WSSH_NO_UPDATE_CHECK", raising=False)
    assert update.check_disabled() is False
    monkeypatch.setenv("WSSH_NO_UPDATE_CHECK", "1")
    assert update.check_disabled() is True
