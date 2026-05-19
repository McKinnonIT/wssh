"""Bootstrap a server for Warpgate (authorized_keys + admin target registration)."""

from __future__ import annotations

import os
import shlex
import socket
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
    """Build default FQDN for a short target name (e.g. dns01 -> dns01.noddy....)."""
    if "." in name:
        return name
    return f"{name}.{server_domain}"


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


def _build_authorized_keys_remote_cmd(keys: list[str]) -> str:
    parts = [
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
        parts.append(
            f"grep -qF {q} ~/.ssh/authorized_keys 2>/dev/null || echo {q} >> ~/.ssh/authorized_keys"
        )
    return " && ".join(parts)


def install_authorized_keys(
    user: str,
    host: str,
    port: int,
    keys: list[str],
    *,
    dry_run: bool = False,
) -> None:
    """Append Warpgate client keys in a single SSH session (one password prompt)."""
    stripped_keys = [k.strip() for k in keys if k.strip()]
    if not stripped_keys:
        return

    if dry_run:
        console.print(
            f"  [yellow]dry-run[/yellow] would install {len(stripped_keys)} key(s) on {user}@{host}"
        )
        return

    dest = f"{user}@{host}"
    console.print(
        f"  [dim]Checking reachability ({DIRECT_SSH_CONNECT_TIMEOUT}s timeout)…[/dim]"
    )
    probe = probe_direct_ssh(user, host, port)
    if probe == "timeout":
        console.print(
            f"[red]Cannot reach {dest} — connection timed out.[/red]\n"
            "Check VPN/network, or verify the hostname resolves and SSH is up."
        )
        raise SystemExit(1)
    if probe in ("unreachable", "host_key"):
        console.print(
            f"[red]Cannot reach {dest} via SSH.[/red]\n"
            "Verify the host is online and you can connect with: "
            f"[bold]ssh {dest}[/bold]"
        )
        raise SystemExit(1)

    console.print(
        f"  [dim]One SSH login to {dest} "
        "(enter password once if prompted; sudo only if needed)[/dim]"
    )
    code = run_direct_ssh(user, host, port, remote_cmd)
    if code != 0:
        console.print("  [dim]Retrying with sudo support…[/dim]")
        code = run_direct_ssh(user, host, port, remote_cmd, force_tty=True)

    if code != 0:
        console.print(f"[red]Failed to update authorized_keys on {dest}[/red]")
        console.print(
            "\nEnsure you can SSH directly (password or key). "
            "If [bold]authorized_keys[/bold] is root-owned, fix on the server then retry:\n"
            f"  [bold]sudo chown {user}:{user} ~/.ssh/authorized_keys[/bold]\n"
            f"  [bold]chmod 600 ~/.ssh/authorized_keys[/bold]"
        )
        raise SystemExit(1)
    console.print(f"  [green]authorized_keys updated ({len(stripped_keys)} Warpgate key(s))[/green]")


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


def setup_server_interactive(
    config: WsshConfig,
    name: str,
    *,
    dry_run: bool = False,
    on_complete: Callable[[], None] | None = None,
) -> None:
    console.print(f"\n[bold]Set up Warpgate for [cyan]{name}[/cyan][/bold]\n")

    default_host = default_server_host(name, config.server_domain)
    host = Prompt.ask("Server hostname or IP", default=default_host)
    ssh_user = Prompt.ask("SSH user for direct access", default=config.default_ssh_user)
    ssh_port = int(Prompt.ask("SSH port", default=str(config.default_ssh_port)))

    console.print(
        "\n[dim]Warpgate will SSH to the server as this user — "
        "client keys must be in their ~/.ssh/authorized_keys[/dim]\n"
    )

    try:
        keys = get_client_keys(config)
    except WarpgateApiError as exc:
        console.print(f"[red]{exc}[/red]")
        console.print(
            "Set [bold]WSSH_WARPGATE_CLIENT_KEYS[/bold] or ask IT for Warpgate client keys."
        )
        raise SystemExit(1) from exc

    console.print(f"Installing {len(keys)} Warpgate client key(s) on {ssh_user}@{host}…")
    install_authorized_keys(ssh_user, host, ssh_port, keys, dry_run=dry_run)

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
                "Ask IT to set Warpgate target "
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
        _, _, stderr = run_ssh_capture(config, name, ["true"])
        console.print("[yellow]Connection test failed[/yellow]")
        console.print(format_ssh_hint(stderr, target=name))

    if on_complete:
        on_complete()


def maybe_offer_setup(
    config: WsshConfig,
    target: str,
    error_kind: str,
) -> bool:
    if error_kind not in ("unknown_target", "auth_failure"):
        return False
    if error_kind == "unknown_target":
        if explain_target_not_visible(config, target):
            if try_fix_target_role_access(config, target):
                return True
            if Confirm.ask(
                f"Run setup-server for '{target}' anyway?",
                default=False,
            ):
                setup_server_interactive(config, target)
                return True
            return False
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
