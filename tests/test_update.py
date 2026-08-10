import sys

from wssh.update import DEFAULT_REPO, update_command


def test_prefers_pipx_when_available(monkeypatch) -> None:
    monkeypatch.delenv("WSSH_REPO", raising=False)
    monkeypatch.setattr("wssh.update.shutil.which", lambda _: "/usr/bin/pipx")
    assert update_command() == ["pipx", "install", "--force", f"git+{DEFAULT_REPO}"]


def test_the_repo_to_install_from_honours_the_env_override(monkeypatch) -> None:
    monkeypatch.setenv("WSSH_REPO", "https://github.com/you/wssh.git")
    monkeypatch.setattr("wssh.update.shutil.which", lambda _: "/usr/bin/pipx")
    assert update_command()[-1] == "git+https://github.com/you/wssh.git"


def test_falls_back_to_pip_in_this_interpreter(monkeypatch) -> None:
    monkeypatch.setattr("wssh.update.shutil.which", lambda _: None)
    cmd = update_command()
    assert cmd[:4] == [sys.executable, "-m", "pip", "install"]
    # Without this, pip sees the unchanged version and installs nothing.
    assert "--force-reinstall" in cmd
