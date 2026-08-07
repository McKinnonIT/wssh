"""SSH via Warpgate bastion."""

from __future__ import annotations

import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path
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
    cmd.extend(_identity_opts())
    return cmd


def _identity_opts() -> list[str]:
    """Pin ssh/scp to the key wssh uploaded to Warpgate."""
    pub = find_public_key()
    priv = private_key_path(pub) if pub else None
    return ["-i", str(priv), "-o", "IdentitiesOnly=yes"] if priv else []


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


# scp's own rule for telling a remote spec from a local path: a colon before any slash.
_SCP_REMOTE = re.compile(r"^([^/:]+):(.*)$")
# scp options that swallow the next argument, which is therefore not a path.
_SCP_VALUE_FLAGS = frozenset({"-c", "-F", "-i", "-J", "-l", "-o", "-P", "-S", "-X"})


def split_remote(arg: str) -> tuple[str, str] | None:
    """('dns01', '/etc/hosts') for a remote spec, None for a local path."""
    match = _SCP_REMOTE.match(arg)
    return (match.group(1), match.group(2)) if match else None


def _split_scp_args(args: list[str]) -> tuple[list[str], list[str]]:
    """Separate scp options from path operands."""
    flags: list[str] = []
    paths: list[str] = []
    want_value = False
    for arg in args:
        if want_value:
            flags.append(arg)
            want_value = False
        elif arg.startswith("-") and arg != "-":
            flags.append(arg)
            want_value = arg in _SCP_VALUE_FLAGS
        else:
            paths.append(arg)
    return flags, paths


def _scp_cmd(config: WsshConfig, target: str, args: list[str]) -> list[str]:
    """Warpgate selects the target from the SSH username, not the hostname.

    Passing it as ``-o User=`` rather than ``user:target@host:path`` keeps the colons
    out of scp's own host:path parsing, which would otherwise split in the wrong place.
    """
    return [
        "scp",
        "-P",
        str(config.port),
        "-o",
        f"User={config.user}:{target}",
        "-o",
        "PreferredAuthentications=publickey",
        *_identity_opts(),
        *args,
    ]


def _for_scp(config: WsshConfig, arg: str) -> str:
    """Rewrite ``target:path`` to the bastion's own ``host:path``."""
    spec = split_remote(arg)
    return f"{config.host}:{spec[1]}" if spec else arg


def _scp_between(
    config: WsshConfig,
    src_target: str,
    dest_target: str,
    flags: list[str],
    sources: list[str],
    dest: str,
) -> int:
    """Copy across two targets, staging on the local disk in between.

    One scp reaches exactly one target — the target lives in the SSH username — so
    there is no single command for this, with or without ``-3``. Staging a directory
    rather than named files lets ``-r`` and globs come out the far side intact.

    A failed leg is reported in wssh's own words. Two invisible copies with only
    scp's per-file complaints in between leave no way to tell how far it got.
    """
    # ponytail: stages through local disk; stream over ssh if the files stop fitting.
    print(f"{src_target} → (local) → {dest_target}", file=sys.stderr)
    with tempfile.TemporaryDirectory(prefix="wssh-scp-") as tmp:
        pull = [*flags, *(_for_scp(config, s) for s in sources), tmp]
        pull_code = subprocess.call(_scp_cmd(config, src_target, pull))
        staged = [str(p) for p in sorted(Path(tmp).iterdir())]

        if not staged:
            print(
                f"Nothing was pulled from {src_target} — {dest_target} was not touched.",
                file=sys.stderr,
            )
            return pull_code or 1
        if pull_code:
            # scp -r copies what it can and still exits non-zero, so one unreadable
            # file used to discard an otherwise complete tree. Push what arrived and
            # keep the failing exit code: same bargain scp makes on a single hop.
            print(
                f"Pull from {src_target} was incomplete — pushing what did copy, "
                f"so {dest_target} will be missing files.",
                file=sys.stderr,
            )

        push = [*flags, *staged, _for_scp(config, dest)]
        code = subprocess.call(_scp_cmd(config, dest_target, push)) or pull_code
        if code:
            print(f"{src_target} → {dest_target} did not complete cleanly.", file=sys.stderr)
        return code


def run_scp(config: WsshConfig, args: list[str]) -> int:
    """scp with ``target:path`` in place of ``host:path``."""
    if not config.host or not config.user:
        print("Warpgate not configured — run: wssh setup", file=sys.stderr)
        return 1
    flags, paths = _split_scp_args(args)
    if len(paths) < 2:
        print("usage: wssh scp [scp options] SOURCE... DEST", file=sys.stderr)
        return 1

    *sources, dest = paths
    src_targets = {spec[0] for spec in map(split_remote, sources) if spec}
    dest_spec = split_remote(dest)
    dest_target = dest_spec[0] if dest_spec else None
    targets = src_targets | ({dest_target} if dest_target else set())

    if not targets:
        print("Both paths are local — plain scp already does that", file=sys.stderr)
        return 1
    if len(targets) == 1:
        rewritten = [*flags, *(_for_scp(config, p) for p in paths)]
        return subprocess.call(_scp_cmd(config, targets.pop(), rewritten))
    if len(src_targets) == 1 and dest_target:
        return _scp_between(config, src_targets.pop(), dest_target, flags, sources, dest)
    print(
        f"One target per copy: {', '.join(sorted(targets))} is more than a source "
        "and a destination. Run it as separate commands.",
        file=sys.stderr,
    )
    return 1


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
