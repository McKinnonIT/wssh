import pytest

from wssh.config import WsshConfig
from wssh.setup_flow import normalize_email, prompt_manual_key_upload, run_setup

EXAMPLE_DOMAIN = "example.com"


def test_normalize_appends_domain() -> None:
    assert normalize_email("alice", EXAMPLE_DOMAIN) == f"alice@{EXAMPLE_DOMAIN}"


def test_normalize_keeps_full_email() -> None:
    full = f"alice@{EXAMPLE_DOMAIN}"
    assert normalize_email(full, EXAMPLE_DOMAIN) == full


def test_normalize_without_domain() -> None:
    assert normalize_email("alice@corp.test", "") == "alice@corp.test"
    assert normalize_email("alice", "") == "alice"


def test_normalize_empty() -> None:
    assert normalize_email("  ", EXAMPLE_DOMAIN) == ""


@pytest.fixture
def manual_upload(monkeypatch):
    """prompt_manual_key_upload with the browser, clipboard, and prompt stubbed out."""
    printed: list[str] = []
    monkeypatch.setattr("wssh.setup_flow.webbrowser.open", lambda url: None)
    monkeypatch.setattr("wssh.setup_flow.Prompt.ask", lambda *a, **k: "")
    monkeypatch.setattr(
        "wssh.setup_flow.console.print", lambda msg="", **k: printed.append(str(msg))
    )
    return printed


def test_manual_key_upload_names_each_ui_step(manual_upload, monkeypatch) -> None:
    """Users read this and assume signing in registers the key — spell out the action."""
    monkeypatch.setattr("wssh.setup_flow.copy_to_clipboard", lambda text: True)
    prompt_manual_key_upload(WsshConfig(host="bastion.example.com"), "ssh-ed25519 AAAA sam@mac")
    blob = "\n".join(manual_upload)
    assert "separate step from signing in" in blob
    assert "Sign in if prompted" in blob
    assert "Add key" in blob
    assert "Public keys" in blob
    assert "clipboard" in blob
    assert "https://bastion.example.com/@warpgate/#/profile/credentials" in blob


def test_manual_key_upload_prints_key_unwrapped_and_uncommented(
    manual_upload, monkeypatch, capsys
) -> None:
    """A wrapped or commented key never authenticates once pasted into Warpgate."""
    monkeypatch.setattr("wssh.setup_flow.copy_to_clipboard", lambda text: False)
    long_key = "ssh-rsa " + "A" * 716
    prompt_manual_key_upload(WsshConfig(host="h"), f"{long_key} sam@mac")
    stdout = capsys.readouterr().out.splitlines()
    assert stdout == [long_key], "key must reach stdout as one unbroken, comment-free line"
    assert "Copy the key below in full" in "\n".join(manual_upload)


def test_setup_re_signs_in_when_a_stored_token_is_stale(monkeypatch, tmp_path) -> None:
    """A 401 is the reason people re-run setup; a stored-but-dead token must not skip it."""
    stored = WsshConfig(host="bastion.example.com", user="o@example.com", api_token="expired")
    logins: list[str] = []
    monkeypatch.setattr("wssh.setup_flow.load_config", lambda: stored)
    monkeypatch.setattr("wssh.setup_flow.save_config", lambda c, path=None: tmp_path / "c.yaml")
    monkeypatch.setattr("wssh.setup_flow.prompt_email", lambda c: c.user)
    monkeypatch.setattr("wssh.setup_flow.setup_ssh_key", lambda c, **k: None)
    monkeypatch.setattr("wssh.setup_flow.get_target_names", lambda c, **k: [])
    monkeypatch.setattr("wssh.setup_flow.detect_rc_file", lambda: tmp_path / "rc")
    monkeypatch.setattr("wssh.setup_flow.install_completion", lambda *a, **k: None)
    monkeypatch.setattr("wssh.setup_flow.console.print", lambda *a, **k: None)
    monkeypatch.setattr(
        "wssh.setup_flow.login_interactive", lambda c, **k: logins.append(c.api_token) or "new"
    )

    run_setup()

    assert logins == ["expired"], "login_interactive must run so it can verify the stored token"
