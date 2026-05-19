"""SSH via Warpgate bastion."""

from __future__ import annotations

import re
import subprocess
import sys
from typing import Any, Literal

from wssh.config import WsshConfig
from wssh.ssh_key import find_public_key, private_key_path

DirectSshProbe = Literal["ok", "timeout", "unreachable", "auth", "host_key"]

DIRECT_SSH_CONNECT_TIMEOUT = 15


class ConnectError(Exception):
    def __init__(self, message: str, *, kind: str = "unknown") -> None:
        super().__init__(message)
        self.kind = kind


_UNKNOWN_TARGET_PATTERNS = [
    re.compile(r"unknown target", re.I),
    re.compile(r"no such target", re.I),
    re.compile(r"target not found", re.I),
    re.compile(r"does not exist", re.I),
]

_AUTH_FAILURE_PATTERNS = [
    re.compile(r"permission denied", re.I),
    re.compile(r"publickey", re.I),
    re.compile(r"authentication failed", re.I),
]

# Warpgate-specific hints in SSH stderr
_WARPGATE_TARGET_AUTH_PATTERNS = [
    re.compile(r"warpgate.*target", re.I),
    re.compile(r"could not connect to target", re.I),
    re.compile(r"failed to authenticate.*target", re.I),
    re.compile(r"rejected Warpgate authentication", re.I),
]


def classify_ssh_failure(stderr: str) -> str:
    text = stderr or ""
    for pat in _UNKNOWN_TARGET_PATTERNS:
        if pat.search(text):
            return "unknown_target"
    for pat in _WARPGATE_TARGET_AUTH_PATTERNS:
        if pat.search(text):
            return "auth_failure"
    for pat in _AUTH_FAILURE_PATTERNS:
        if pat.search(text):
            return "auth_failure"
    if "connection refused" in text.lower():
        return "connection_refused"
    return "unknown"


def bastion_destination(config: WsshConfig, target: str) -> str:
    return f"{config.user}:{target}@{config.host}"


def _ssh_base_cmd(config: WsshConfig) -> list[str]:
    """Build ssh argv with identity file matching the key uploaded to Warpgate."""
    cmd = ["ssh", "-p", str(config.port)]
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
    result = subprocess.run(cmd, capture_output=True, text=True)
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


def run_ssh(config: WsshConfig, target: str, ssh_args: list[str]) -> int:
    if not config.user:
        print("Warpgate user not configured — run: wssh setup", file=sys.stderr)
        return 1
    cmd = [
        *_ssh_base_cmd(config),
        bastion_destination(config, target),
        *ssh_args,
    ]
    return subprocess.call(cmd)


def run_ssh_capture(config: WsshConfig, target: str, ssh_args: list[str]) -> tuple[int, str, str]:
    cmd = [
        *_ssh_base_cmd(config),
        bastion_destination(config, target),
        *ssh_args,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
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
    return subprocess.call(cmd, stdin=sys.stdin)


def run_direct_ssh_capture(
    user: str,
    host: str,
    port: int,
    remote_command: str,
) -> tuple[int, str, str]:
    cmd = [*_direct_ssh_base(port), f"{user}@{host}", remote_command]
    result = subprocess.run(cmd, capture_output=True, text=True)
    return result.returncode, result.stdout, result.stderr


def ssh_failure_output(stderr: str, stdout: str = "") -> str:
    """Combine SSH streams for error classification (OpenSSH may write to either)."""
    return f"{stderr}\n{stdout}".strip()


def format_ssh_hint(stderr: str, *, target: str | None = None, stdout: str = "") -> str:
    kind = classify_ssh_failure(ssh_failure_output(stderr, stdout))
    if kind == "auth_failure" and target:
        return (
            f"Authentication failed for [bold]{target}[/bold]. Common causes:\n"
            "  • Warpgate target points at the wrong host or SSH user (run [bold]wssh setup-server "
            f"{target}[/bold] to fix)\n"
            "  • Warpgate client keys are not in that user's [bold]authorized_keys[/bold]\n"
            "  • Your SSH key is not registered in Warpgate (run [bold]wssh credentials add-key[/bold])"
        )
    if kind == "unknown_target" and target:
        return f"Target [bold]{target}[/bold] is not registered in Warpgate."
    return stderr.strip() or "SSH connection failed"
