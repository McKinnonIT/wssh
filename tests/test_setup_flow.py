import pytest

from wssh.config import WsshConfig
from wssh.setup_flow import normalize_email, prompt_manual_key_upload

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
