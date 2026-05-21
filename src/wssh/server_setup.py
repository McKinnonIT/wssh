"""Bootstrap a server for Warpgate (authorized_keys + admin target registration)."""

from __future__ import annotations

import os
import platform
import re
import shlex
import shutil
import socket
import subprocess
import sys
from typing import Any, Callable

from rich.console import Console
from rich.prompt import Confirm, Prompt
from wssh.config import WsshConfig, save_config
from wssh.connect import (
    DIRECT_SSH_CONNECT_TIMEOUT,
    format_ssh_hint,
    probe_direct_ssh,
    run_direct_ssh,
    run_ssh,
    run_ssh_capture,
)
from wssh.constants import DEFAULT_TARGET_ROLE
from wssh.targets import refresh_targets
from wssh.warpgate import WarpgateApiError
from wssh.warpgate_admin import WarpgateAdminClient, ssh_target_summary

console = Console()


def default_server_host(name: str, server_domain: str) -> str:
    """Build default FQDN for a short target name (e.g. dns01 -> dns01.internal.example)."""
    if "." in name or not server_domain.strip():
        return name
    return f"{name}.{server_domain.strip()}"


def get_client_keys(config: WsshConfig, *, force_refresh: bool = False) -> list[str]:
    env_keys = os.environ.get("WSSH_WARPGATE_CLIENT_KEYS", "").strip()
    if env_keys and not force_refresh:
        return [k.strip() for k in env_keys.splitlines() if k.strip()]

    if config.warpgate_client_keys and not force_refresh:
        return list(config.warpgate_client_keys)

    with WarpgateAdminClient(config) as admin:
        keys = admin.get_ssh_client_keys()
    config.warpgate_client_keys = keys
    save_config(config)
    return keys


def _authorized_keys_shell_lines(keys: list[str]) -> list[str]:
    lines = [
        "set -e",
        "mkdir -p ~/.ssh && chmod 700 ~/.ssh",
        (
            'if [ -f ~/.ssh/authorized_keys ] && [ ! -w ~/.ssh/authorized_keys ]; then '
            'sudo chown "$(whoami):$(whoami)" ~/.ssh/authorized_keys; fi'
        ),
        "touch ~/.ssh/authorized_keys && chmod 600 ~/.ssh/authorized_keys",
    ]
    for line in keys:
        q = shlex.quote(line)
        lines.append(
            f"grep -qF {q} ~/.ssh/authorized_keys 2>/dev/null || echo {q} >> ~/.ssh/authorized_keys"
        )
    return lines


def _build_authorized_keys_remote_cmd(keys: list[str]) -> str:
    return " && ".join(_authorized_keys_shell_lines(keys))


def _target_slug(host: str, target_name: str | None) -> str:
    if target_name:
        return re.sub(r"[^\w.-]+", "-", target_name)
    return host.split(".")[0]


def _copy_lines_to_clipboard(lines: list[str]) -> bool:
    """Copy text to the system clipboard (macOS pbcopy, Linux xclip/wl-copy)."""
    payload = "\n".join(lines)
    if not payload:
        return False
    system = platform.system()
    if system == "Darwin" and shutil.which("pbcopy"):
        subprocess.run(["pbcopy"], input=payload, text=True, check=False)
        return True
    if system == "Linux":
        if shutil.which("wl-copy"):
            subprocess.run(["wl-copy"], input=payload, text=True, check=False)
            return True
        if shutil.which("xclip") and os.environ.get("DISPLAY"):
            subprocess.run(
                ["xclip", "-selection", "clipboard"],
                input=payload,
                text=True,
                check=False,
            )
            return True
    return False


def _print_copyable_key_line(key: str) -> None:
    """Print one SSH public key without Rich wrapping (must stay a single line)."""
    # Plain stdout avoids Rich's terminal width; user may still need to widen the window.
    sys.stdout.write(key + "\n")
    sys.stdout.flush()


def _print_manual_keys_instructions(
    ssh_user: str,
    keys: list[str],
    *,
    host: str,
    target_name: str | None,
) -> None:
    slug = _target_slug(host, target_name)
    console.print(
        f"\n[bold]Manual steps[/bold] (on the server as [bold]{ssh_user}[/bold]):\n"
    )
    console.print("  1. [dim]mkdir -p ~/.ssh && chmod 700 ~/.ssh[/dim]")
    console.print("  2. [dim]touch ~/.ssh/authorized_keys && chmod 600 ~/.ssh/authorized_keys[/dim]")
    console.print(
        f"  3. Add {len(keys)} Warpgate key(s) to [bold]~/.ssh/authorized_keys[/bold] "
        "(each key is exactly [bold]one line[/bold], no line breaks inside a key):\n"
    )

    if _copy_lines_to_clipboard(keys):
        console.print(
            f"     [green]Copied {len(keys)} key(s) to clipboard[/green] — "
            "paste into the file on the server (one key per line)\n"
        )
    else:
        console.print(
            "     [dim]Copy each line below in full (widen the terminal if it wraps):[/dim]\n"
        )
        for index, key in enumerate(keys, start=1):
            key_type = key.split()[0] if key.split() else "key"
            console.print(f"     [bold]Key {index}[/bold] ({key_type}):")
            _print_copyable_key_line(key)
            console.print("")

    console.print(f"  4. Run [bold]wssh setup-server {slug}[/bold] again\n")


def _print_keys_install_blocked(
    dest: str,
    ssh_user: str,
    host: str,
    keys: list[str],
    *,
    target_name: str | None = None,
    reason: str,
) -> None:
    """Explain why automatic key install failed; offer manual steps."""
    detail = {
        "timeout": f"{dest} — timed out from your network",
        "unreachable": f"{dest} — not reachable via direct SSH",
        "host_key": (
            f"{dest} — accept the host key locally first "
            f"([bold]ssh {dest}[/bold]), or use console access"
        ),
        "auth": (
            f"{dest} — server may not allow password login; "
            "use console or an existing key"
        ),
        "install_failed": dest,
    }.get(reason, dest)

    console.print("\n[bold red]✗ Could not install Warpgate keys from here[/bold red]")
    console.print(f"  [dim]{detail}[/dim]")
    console.print(
        "  [dim]Warpgate may still reach this host — you can register it anyway.[/dim]"
    )

    if Confirm.ask("Show manual install instructions?", default=False):
        _print_manual_keys_instructions(
            ssh_user, keys, host=host, target_name=target_name
        )
    else:
        console.print(
            "\n  [dim]Add keys on the server if needed, then continue Warpgate setup below.[/dim]\n"
        )


def install_authorized_keys(
    user: str,
    host: str,
    port: int,
    keys: list[str],
    *,
    dry_run: bool = False,
    target_name: str | None = None,
) -> bool:
    """Append Warpgate client keys in a single SSH session (one password prompt).

    Returns True if keys were installed (or nothing to install). False if install failed.
    """
    stripped_keys = [k.strip() for k in keys if k.strip()]
    if not stripped_keys:
        return True

    if dry_run:
        console.print(
            f"  [yellow]dry-run[/yellow] would install {len(stripped_keys)} key(s) on {user}@{host}"
        )
        return True

    dest = f"{user}@{host}"
    console.print(
        f"  [dim]Checking reachability ({DIRECT_SSH_CONNECT_TIMEOUT}s timeout)…[/dim]"
    )
    probe = probe_direct_ssh(user, host, port)
    if probe in ("timeout", "unreachable", "host_key"):
        _print_keys_install_blocked(
            dest,
            user,
            host,
            stripped_keys,
            target_name=target_name,
            reason=probe,
        )
        return False

    console.print(
        f"  [dim]One SSH login to {dest} "
        "(enter password once if prompted; sudo only if needed)[/dim]"
    )
    remote_cmd = _build_authorized_keys_remote_cmd(stripped_keys)
    code = run_direct_ssh(user, host, port, remote_cmd)
    if code != 0:
        console.print("  [dim]Retrying with sudo support…[/dim]")
        code = run_direct_ssh(user, host, port, remote_cmd, force_tty=True)

    if code != 0:
        _print_keys_install_blocked(
            dest,
            user,
            host,
            stripped_keys,
            target_name=target_name,
            reason="auth" if probe == "auth" else "install_failed",
        )
        return False
    console.print(f"  [green]authorized_keys updated ({len(stripped_keys)} Warpgate key(s))[/green]")
    return True


def _register_or_update_target(
    admin: WarpgateAdminClient,
    name: str,
    host: str,
    port: int,
    username: str,
) -> None:
    existing = admin.find_target_by_name(name)
    if existing:
        current = ssh_target_summary(existing)
        console.print(
            f"[yellow]Target '{name}' exists in Warpgate[/yellow] "
            f"(currently [bold]{current}[/bold])"
        )
        desired = f"{username}@{host}:{port}"
        if current.replace(" ", "") == desired.replace(" ", ""):
            console.print("[green]Warpgate target settings already match[/green]")
            _ensure_target_role_access(admin, existing, name)
            return
        if Confirm.ask(
            f"Update Warpgate to use [bold]{desired}[/bold]?",
            default=True,
        ):
            target_id = existing.get("id")
            if not target_id:
                console.print("[red]Could not read target id — update manually in Warpgate admin[/red]")
                return
            admin.update_ssh_target(
                target_id, name, host, port, username, existing=existing
            )
            console.print(f"[green]Updated Warpgate target '{name}' → {desired}[/green]")
            _ensure_target_role_access(admin, existing, name)
        else:
            console.print(
                "[yellow]Skipped target update — keys must be in "
                f"{current}'s authorized_keys, not necessarily {username}@{host}[/yellow]"
            )
            _ensure_target_role_access(admin, existing, name)
    else:
        created = admin.create_ssh_target(
            name=name,
            host=host,
            port=port,
            username=username,
            description=f"Added by wssh setup-server on {socket.gethostname()}",
        )
        console.print(f"[green]Registered Warpgate target '{name}'[/green]")
        _ensure_target_role_access(admin, created, name)


def _ensure_target_role_access(
    admin: WarpgateAdminClient,
    target: dict[str, Any],
    name: str,
) -> None:
    target_id = target.get("id")
    if not target_id:
        refetched = admin.find_target_by_name(name)
        target_id = refetched.get("id") if refetched else None
    if not target_id:
        console.print(
            f"[yellow]Could not resolve target id for '{name}' — enable "
            f"[bold]Allow access for roles → {DEFAULT_TARGET_ROLE}[/bold] in Warpgate admin.[/yellow]"
        )
        return
    try:
        if admin.ensure_target_role(target_id):
            console.print(
                f"[green]Granted [bold]{DEFAULT_TARGET_ROLE}[/bold] role access on '{name}'[/green]"
            )
        else:
            console.print(
                f"[dim]{DEFAULT_TARGET_ROLE} role access already enabled on '{name}'[/dim]"
            )
    except WarpgateApiError as exc:
        console.print(
            f"[yellow]Could not assign {DEFAULT_TARGET_ROLE} role: {exc}[/yellow]\n"
            f"Enable [bold]Allow access for roles → {DEFAULT_TARGET_ROLE}[/bold] "
            "manually in Warpgate admin."
        )


def try_fix_target_role_access(config: WsshConfig, target: str) -> bool:
    """If the target exists in Warpgate but the user cannot see it, grant role access.

    Returns True when the target should be retried (role was fixed or user should reconnect).
    """
    if not config.effective_admin_token():
        return False
    try:
        with WarpgateAdminClient(config) as admin:
            if not admin.find_target_by_name(target):
                return False
            if not admin.ensure_target_access(target):
                console.print(
                    f"[dim]{DEFAULT_TARGET_ROLE} role access already enabled on '{target}'[/dim]"
                )
                return True
            console.print(
                f"[green]Granted [bold]{DEFAULT_TARGET_ROLE}[/bold] role access on '{target}'[/green]"
            )
            refresh_targets(config)
            return True
    except WarpgateApiError as exc:
        console.print(f"[yellow]Could not update role access: {exc}[/yellow]")
        return False


def explain_target_not_visible(config: WsshConfig, target: str) -> bool:
    """Print a helpful message when a target exists in admin but not in the user's list."""
    if not config.effective_admin_token():
        return False
    try:
        with WarpgateAdminClient(config) as admin:
            if not admin.find_target_by_name(target):
                return False
    except WarpgateApiError:
        return False

    console.print(
        f"\n[yellow]Target '{target}' exists in Warpgate but your account cannot access it yet.[/yellow]\n"
        f"Enable [bold]Allow access for roles → {DEFAULT_TARGET_ROLE}[/bold] in the Warpgate admin UI, "
        f"or run [bold]wssh setup-server {target}[/bold] to fix it automatically."
    )
    return True


def prompt_server_connection(config: WsshConfig, name: str) -> tuple[str, str, int]:
    """Ask once to accept defaults, or prompt for host, user, and port individually."""
    default_host = default_server_host(name, config.server_domain)
    default_user = config.default_ssh_user
    default_port = config.default_ssh_port

    console.print("Planned connection:")
    console.print(f"  Host: [cyan]{default_host}[/cyan]")
    console.print(f"  SSH user: [cyan]{default_user}[/cyan]")
    console.print(f"  Port: [cyan]{default_port}[/cyan]\n")

    if Confirm.ask("Continue with these settings?", default=True):
        return default_host, default_user, default_port

    console.print()
    host = Prompt.ask("Server hostname or IP", default=default_host)
    ssh_user = Prompt.ask("SSH user for direct access", default=default_user)
    ssh_port = int(Prompt.ask("SSH port", default=str(default_port)))
    return host, ssh_user, ssh_port


def setup_server_interactive(
    config: WsshConfig,
    name: str,
    *,
    dry_run: bool = False,
    on_complete: Callable[[], None] | None = None,
) -> None:
    console.print(f"\n[bold]Set up Warpgate for [cyan]{name}[/cyan][/bold]\n")

    host, ssh_user, ssh_port = prompt_server_connection(config, name)

    console.print(
        "\n[dim]Warpgate will SSH to the server as this user — "
        "client keys must be in their ~/.ssh/authorized_keys[/dim]\n"
    )

    try:
        keys = get_client_keys(config)
    except WarpgateApiError as exc:
        console.print(f"[red]{exc}[/red]")
        console.print(
            "Set [bold]WSSH_WARPGATE_CLIENT_KEYS[/bold] or ask your administrator for Warpgate client keys."
        )
        raise SystemExit(1) from exc

    console.print(f"Installing {len(keys)} Warpgate client key(s) on {ssh_user}@{host}…")
    keys_installed = install_authorized_keys(
        ssh_user, host, ssh_port, keys, dry_run=dry_run, target_name=name
    )
    if not keys_installed:
        if not Confirm.ask(
            "Continue Warpgate setup anyway? "
            "(Warpgate may reach this host; keys may already be installed)",
            default=True,
        ):
            raise SystemExit(1)
        console.print(
            "[dim]Continuing — registering target in Warpgate.[/dim]\n"
        )

    if dry_run:
        console.print("[yellow]dry-run[/yellow] skipping Warpgate target registration")
        return

    try:
        with WarpgateAdminClient(config) as admin:
            _register_or_update_target(admin, name, host, ssh_port, ssh_user)
    except WarpgateApiError as exc:
        if exc.status_code == 403:
            console.print(
                "[red]Cannot register/update target — admin permission required.[/red]\n"
                "Ask your administrator to set Warpgate target "
                f"[bold]{name}[/bold] → {ssh_user}@{host}:{ssh_port}"
            )
            raise SystemExit(1) from exc
        raise

    config.default_ssh_user = ssh_user
    save_config(config)

    try:
        refresh_targets(config)
    except WarpgateApiError:
        pass

    console.print("\nVerifying connection via Warpgate…")
    code = run_ssh(config, name, ["echo", "wssh-setup-ok"])
    if code == 0:
        console.print("[green]Connection successful[/green]")
    else:
        _, stdout, stderr = run_ssh_capture(config, name, ["true"])
        console.print("[yellow]Could not verify via Warpgate yet[/yellow]")
        console.print(format_ssh_hint(stderr, target=name, stdout=stdout))
        console.print(
            f"If keys are on the server, try: [bold]wssh {name}[/bold]"
        )

    if on_complete:
        on_complete()


def _target_registered_in_warpgate(config: WsshConfig, name: str) -> bool:
    """True when the target exists in Warpgate admin (may still need role access)."""
    if not config.effective_admin_token():
        return False
    try:
        with WarpgateAdminClient(config) as admin:
            return admin.find_target_by_name(name) is not None
    except WarpgateApiError:
        return False


def _offer_retry_or_setup(
    config: WsshConfig,
    target: str,
    *,
    message: str,
) -> bool:
    """Target exists in Warpgate but SSH failed — retry or optional full setup."""
    console.print(f"\n[yellow]{message}[/yellow]")
    if try_fix_target_role_access(config, target):
        return True
    if Confirm.ask("Retry connection?", default=True):
        return True
    if Confirm.ask(
        f"Run [bold]wssh setup-server {target}[/bold] to fix keys and target settings?",
        default=False,
    ):
        setup_server_interactive(config, target)
        return True
    return False


def maybe_offer_setup(
    config: WsshConfig,
    target: str,
    error_kind: str,
) -> bool:
    if error_kind not in ("unknown_target", "auth_failure"):
        return False

    if error_kind == "unknown_target" and explain_target_not_visible(config, target):
        if try_fix_target_role_access(config, target):
            return True
        if Confirm.ask("Retry connection?", default=True):
            return True
        if Confirm.ask(
            f"Run [bold]wssh setup-server {target}[/bold] to fix keys and target settings?",
            default=False,
        ):
            setup_server_interactive(config, target)
            return True
        return False

    if _target_registered_in_warpgate(config, target):
        return _offer_retry_or_setup(
            config,
            target,
            message=(
                f"Target '{target}' is registered in Warpgate but the connection failed. "
                "Warpgate client keys may be missing on the server, or host/user may be wrong."
            ),
        )

    if error_kind == "unknown_target":
        msg = f"Target '{target}' is not registered in Warpgate."
    else:
        msg = (
            f"Warpgate could not authenticate to '{target}'. "
            "The target may use the wrong SSH user/host, or client keys may be missing."
        )
    console.print(f"\n[yellow]{msg}[/yellow]")
    if not Confirm.ask("Run setup-server for this host now?", default=True):
        return False
    setup_server_interactive(config, target)
    return True
