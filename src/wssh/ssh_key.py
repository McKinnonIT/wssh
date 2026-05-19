"""Discover or generate SSH keys."""

from __future__ import annotations

import os
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class SshPublicKey:
    path: Path
    openssh_line: str

    @property
    def fingerprint_suffix(self) -> str:
        parts = self.openssh_line.split()
        return parts[1][:16] if len(parts) > 1 else self.openssh_line[:16]


def public_key_blob(openssh_line: str) -> str | None:
    """Base64 key material from an OpenSSH public-key line (comment ignored)."""
    parts = openssh_line.strip().split()
    return parts[1] if len(parts) >= 2 else None


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
    """SHA256 fingerprint from an OpenSSH public-key line (e.g. ``SHA256:AbCd...``)."""
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".pub", delete=False, encoding="utf-8"
    ) as fh:
        fh.write(openssh_line.strip() + "\n")
        path = fh.name
    try:
        output = subprocess.check_output(
            ["ssh-keygen", "-lf", path],
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    finally:
        os.unlink(path)
    for token in output.split():
        if token.startswith("SHA256:"):
            return token
    raise ValueError(f"could not parse ssh-keygen fingerprint: {output!r}")


def public_keys_match(line_a: str, line_b: str) -> bool:
    """True if two OpenSSH public-key lines are the same key (ignoring comment)."""
    blob_a = public_key_blob(line_a)
    blob_b = public_key_blob(line_b)
    if blob_a and blob_b:
        return blob_a == blob_b
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


def copy_to_clipboard(text: str) -> bool:
    commands = [
        ["pbcopy"],
        ["wl-copy"],
        ["xclip", "-selection", "clipboard"],
        ["xsel", "--clipboard", "--input"],
    ]
    for cmd in commands:
        try:
            subprocess.run(cmd, input=text.encode(), check=True, capture_output=True)
            return True
        except (OSError, subprocess.CalledProcessError):
            continue
    return False
