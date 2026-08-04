"""Discover or generate SSH keys."""

from __future__ import annotations

import base64
import hashlib
import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class SshPublicKey:
    path: Path
    openssh_line: str


def normalize_openssh_public_key(openssh_line: str) -> str:
    """Return ``<algorithm> <base64>`` only, matching Warpgate's web UI and SSH auth.

    Warpgate compares client keys to stored credentials with exact string equality on
    ``{algorithm} {base64}`` (no comment). The profile UI strips comments before save;
    keys uploaded with a trailing comment never authenticate.
    """
    parts = openssh_line.strip().split()
    if len(parts) < 2:
        raise ValueError("invalid OpenSSH public key: expected '<type> <base64> [comment]'")
    return f"{parts[0]} {parts[1]}"


def public_key_stored_correctly(openssh_line: str) -> bool:
    """False when Warpgate would not match SSH auth (e.g. key still has a comment)."""
    try:
        return openssh_line.strip() == normalize_openssh_public_key(openssh_line)
    except ValueError:
        return False


def public_key_fingerprint(openssh_line: str) -> str:
    """SHA256 fingerprint from an OpenSSH public-key line (e.g. ``SHA256:AbCd...``).

    Same value as ``ssh-keygen -lf``: unpadded base64 of the SHA256 digest of the
    raw (base64-decoded) key blob.
    """
    blob = normalize_openssh_public_key(openssh_line).split()[1]
    digest = hashlib.sha256(base64.b64decode(blob)).digest()
    return "SHA256:" + base64.b64encode(digest).decode().rstrip("=")


def public_keys_match(line_a: str, line_b: str) -> bool:
    """True if two OpenSSH public-key lines are the same key (ignoring comment)."""
    try:
        return normalize_openssh_public_key(line_a) == normalize_openssh_public_key(line_b)
    except ValueError:
        return line_a.strip() == line_b.strip()


def private_key_path(public_key: SshPublicKey) -> Path | None:
    """Path to private key paired with a .pub file (e.g. id_rsa.pub -> id_rsa)."""
    candidate = public_key.path.with_suffix("")
    return candidate if candidate.is_file() else None


def find_public_key() -> SshPublicKey | None:
    candidates = [
        Path.home() / ".ssh" / "id_ed25519.pub",
        Path.home() / ".ssh" / "id_rsa.pub",
        Path.home() / ".ssh" / "id_ecdsa.pub",
    ]
    for path in candidates:
        if path.is_file():
            return SshPublicKey(path=path, openssh_line=path.read_text(encoding="utf-8").strip())
    return None


def generate_ed25519_key(comment: str, dry_run: bool = False) -> SshPublicKey | None:
    private = Path.home() / ".ssh" / "id_ed25519"
    public = private.with_suffix(".pub")
    if dry_run:
        return None
    private.parent.mkdir(mode=0o700, exist_ok=True)
    subprocess.run(
        ["ssh-keygen", "-t", "ed25519", "-f", str(private), "-C", comment],
        check=True,
    )
    return SshPublicKey(path=public, openssh_line=public.read_text(encoding="utf-8").strip())


_CLIPBOARD_COMMANDS = [
    ["pbcopy"],
    ["wl-copy"],
    ["xclip", "-selection", "clipboard"],
    ["xsel", "--clipboard", "--input"],
]

CLIPBOARD_TIMEOUT = 5


def copy_to_clipboard(text: str) -> bool:
    """Best-effort clipboard copy. Never blocks the caller.

    Output goes to /dev/null rather than pipes on purpose. Every X11/Wayland
    helper here forks a process that keeps running to own the selection, and
    that fork inherits our stdout/stderr. Captured, those pipes stay open for
    as long as the clipboard holds the value, so waiting for EOF never
    returns — ``wssh setup`` hung here on Linux while macOS's non-forking
    pbcopy was fine. The timeout covers a helper that does not fork at all.
    """
    for cmd in _CLIPBOARD_COMMANDS:
        try:
            subprocess.run(
                cmd,
                input=text.encode(),
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=CLIPBOARD_TIMEOUT,
            )
            return True
        except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
            continue
    return False
