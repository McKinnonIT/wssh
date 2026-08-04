import sys

from wssh.update import DEFAULT_REPO, repo_spec, update_command


def test_repo_spec_defaults_to_mckinnonit(monkeypatch) -> None:
    monkeypatch.delenv("WSSH_REPO", raising=False)
    assert repo_spec() == f"git+{DEFAULT_REPO}"


def test_repo_spec_honours_env_override(monkeypatch) -> None:
    monkeypatch.setenv("WSSH_REPO", "https://github.com/you/wssh.git")
    assert repo_spec() == "git+https://github.com/you/wssh.git"


def test_prefers_pipx_when_available(monkeypatch) -> None:
    monkeypatch.setattr("wssh.update.shutil.which", lambda _: "/usr/bin/pipx")
    assert update_command()[:3] == ["pipx", "install", "--force"]


def test_falls_back_to_pip_in_this_interpreter(monkeypatch) -> None:
    monkeypatch.setattr("wssh.update.shutil.which", lambda _: None)
    cmd = update_command()
    assert cmd[:4] == [sys.executable, "-m", "pip", "install"]
    # Without this, pip sees the unchanged version and installs nothing.
    assert "--force-reinstall" in cmd
