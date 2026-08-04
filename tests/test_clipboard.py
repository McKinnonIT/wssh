import time

from wssh.ssh_key import copy_to_clipboard

# A helper that forks a process which keeps running and inherits our stdout —
# exactly what xclip and wl-copy do to own the selection after they exit.
FORKING_HELPER = [["sh", "-c", "cat >/dev/null; sleep 30 & exit 0"]]


def test_forking_helper_does_not_block(monkeypatch) -> None:
    """Capturing stdout waited for the forked clipboard owner to exit. It never does."""
    monkeypatch.setattr("wssh.ssh_key._CLIPBOARD_COMMANDS", FORKING_HELPER)
    start = time.monotonic()
    assert copy_to_clipboard("ssh-ed25519 AAAA test") is True
    assert time.monotonic() - start < 5, "returned only after the forked child died"


def test_helper_that_never_exits_times_out(monkeypatch) -> None:
    monkeypatch.setattr("wssh.ssh_key._CLIPBOARD_COMMANDS", [["sleep", "30"]])
    monkeypatch.setattr("wssh.ssh_key.CLIPBOARD_TIMEOUT", 1)
    assert copy_to_clipboard("ssh-ed25519 AAAA test") is False


def test_all_helpers_missing_returns_false(monkeypatch) -> None:
    monkeypatch.setattr("wssh.ssh_key._CLIPBOARD_COMMANDS", [["wssh-no-such-clipboard-tool"]])
    assert copy_to_clipboard("x") is False
