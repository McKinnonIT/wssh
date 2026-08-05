"""SSH via Warpgate bastion."""

from __future__ import annotations

import os
import re
import subprocess
import sys
from typing import Literal

from wssh.config import WsshConfig
from wssh.ssh_key import find_public_key, private_key_path

DirectSshProbe = Literal["ok", "timeout", "unreachable", "auth", "host_key"]

DIRECT_SSH_CONNECT_TIMEOUT = 15

_UNKNOWN_TARGET = ("unknown target", "no such target", "target not found", "does not exist")
_AUTH_FAILURE = (
    "permission denied",
    "publickey",
    "authentication failed",
    "could not connect to target",  # Warpgate-specific hints below
    "rejected warpgate authentication",
)
# The only two that need more than a substring: "<word> ... target" ordering.
_AUTH_FAILURE_RE = re.compile(r"warpgate.*target|failed to authenticate.*target", re.I)


# Terminals whose terminfo entry almost no remote host has, so the session dies on
# "'xterm-ghostty': unknown terminal type". Ghostty's own fix (shell-integration-features
# = ssh-terminfo) is a shell function wrapping ssh, so it never sees the ssh we spawn.
# https://ghostty.org/docs/help/terminfo
_UNKNOWN_REMOTE_TERMS = ("xterm-ghostty", "xterm-kitty")


def ssh_env() -> dict[str, str] | None:
    """Environment for ssh, with TERM downgraded when the remote won't know it.

    ssh takes TERM for its pty request straight from its own environment, which works
    on every OpenSSH version (``-o SetEnv=TERM`` needs 8.7+). Set ``WSSH_TERM`` to pick
    a different value, or to empty to keep your real TERM — do that once you've copied
    the entry over with ``infocmp -x $TERM | ssh host -- tic -x -``.

    Returns None to inherit the environment unchanged.
    """
    fallback = os.environ.get("WSSH_TERM", "xterm-256color").strip()
    if not fallback or not os.environ.get("TERM", "").startswith(_UNKNOWN_REMOTE_TERMS):
        return None
    return {**os.environ, "TERM": fallback}


def classify_ssh_failure(stderr: str) -> str:
    text = (stderr or "").lower()
    if any(s in text for s in _UNKNOWN_TARGET):
        return "unknown_target"
    if any(s in text for s in _AUTH_FAILURE) or _AUTH_FAILURE_RE.search(text):
        return "auth_failure"
    if "connection refused" in text:
        return "connection_refused"
    return "unknown"


def bastion_destination(config: WsshConfig, target: str) -> str:
    return f"{config.user}:{target}@{config.host}"


def _ssh_base_cmd(config: WsshConfig, *, batch_mode: bool = False) -> list[str]:
    """Build ssh argv with identity file matching the key uploaded to Warpgate.

    Public key only. wssh registers your key with Warpgate, so a password prompt
    here is never the way in — Warpgate offers keyboard-interactive and ssh would
    otherwise stop and ask for a password no one can supply. Failing straight to
    ``Permission denied (publickey)`` is both faster and diagnosable.

    ``batch_mode`` additionally forbids every interactive prompt. Required
    whenever output is captured: a prompt written to a pipe is invisible, so the
    terminal just hangs on input the user cannot see.
    """
    cmd = ["ssh", "-p", str(config.port), "-o", "PreferredAuthentications=publickey"]
    if batch_mode:
        cmd.extend(["-o", "BatchMode=yes"])
    pub = find_public_key()
    if pub:
        priv = private_key_path(pub)
        if priv:
            cmd.extend(["-i", str(priv), "-o", "IdentitiesOnly=yes"])
    return cmd


def _prepare_stdio_for_ssh() -> None:
    """Restore terminal after Rich prompts so ssh can prompt for a password."""
    if not sys.stdin.isatty():
        return
    try:
        subprocess.run(
            ["stty", "sane"],
            stdin=sys.stdin,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
    except OSError:
        pass


def _direct_ssh_base(port: int, *, batch_mode: bool = False) -> list[str]:
    opts = [
        "ssh",
        "-p",
        str(port),
        "-o",
        "StrictHostKeyChecking=accept-new",
        "-o",
        f"ConnectTimeout={DIRECT_SSH_CONNECT_TIMEOUT}",
    ]
    opts.extend(["-o", "BatchMode=yes" if batch_mode else "BatchMode=no"])
    return opts


def probe_direct_ssh(user: str, host: str, port: int) -> DirectSshProbe:
    """Reachability check without prompting for a password."""
    cmd = [*_direct_ssh_base(port, batch_mode=True), f"{user}@{host}", "true"]
    result = subprocess.run(cmd, capture_output=True, text=True, stdin=subprocess.DEVNULL)
    text = f"{result.stderr}\n{result.stdout}".lower()
    if "timed out" in text or "timeout" in text:
        return "timeout"
    if "connection refused" in text:
        return "unreachable"
    if "host key verification failed" in text:
        return "host_key"
    if result.returncode == 0:
        return "ok"
    if "permission denied" in text:
        return "auth"
    return "unreachable"


def _bastion_ssh_cmd(
    config: WsshConfig, target: str, ssh_args: list[str], *, batch_mode: bool = False
) -> list[str]:
    return [
        *_ssh_base_cmd(config, batch_mode=batch_mode),
        bastion_destination(config, target),
        *ssh_args,
    ]


def run_ssh(config: WsshConfig, target: str, ssh_args: list[str]) -> int:
    if not config.host:
        print("Warpgate host not configured — run: wssh setup", file=sys.stderr)
        return 1
    if not config.user:
        print("Warpgate user not configured — run: wssh setup", file=sys.stderr)
        return 1
    return subprocess.call(_bastion_ssh_cmd(config, target, ssh_args), env=ssh_env())


def run_ssh_capture(config: WsshConfig, target: str, ssh_args: list[str]) -> tuple[int, str, str]:
    """Run ssh and capture its output. Never prompts — see _ssh_base_cmd."""
    result = subprocess.run(
        _bastion_ssh_cmd(config, target, ssh_args, batch_mode=True),
        capture_output=True,
        text=True,
        stdin=subprocess.DEVNULL,
        env=ssh_env(),
    )
    return result.returncode, result.stdout, result.stderr


def run_direct_ssh(
    user: str,
    host: str,
    port: int,
    remote_command: str,
    *,
    force_tty: bool = False,
    dry_run: bool = False,
) -> int:
    _prepare_stdio_for_ssh()
    cmd = [*_direct_ssh_base(port), f"{user}@{host}"]
    if force_tty:
        cmd.insert(-1, "-t")
    cmd.append(remote_command)
    if dry_run:
        print("Would run:", " ".join(cmd))
        return 0
    return subprocess.call(cmd, stdin=sys.stdin, env=ssh_env())


def format_ssh_hint(stderr: str, *, target: str | None = None, stdout: str = "") -> str:
    # OpenSSH may write the useful part to either stream.
    kind = classify_ssh_failure(f"{stderr}\n{stdout}")
    if kind == "auth_failure" and target:
        return (
            f"Authentication failed for [bold]{target}[/bold]. Common causes:\n"
            "  • Warpgate target points at the wrong host or SSH user (run [bold]wssh setup-server "
            f"{target}[/bold] to fix)\n"
            "  • Warpgate client keys are not in that user's [bold]authorized_keys[/bold]\n"
            "  • Your SSH key is not registered in Warpgate "
            "(run [bold]wssh credentials add-key[/bold])"
        )
    if kind == "unknown_target" and target:
        return f"Target [bold]{target}[/bold] is not registered in Warpgate."
    return stderr.strip() or "SSH connection failed"
