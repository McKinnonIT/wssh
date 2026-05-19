"""wssh CLI entry point."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console

from wssh import __version__
from wssh.auth import login_interactive, logout
from wssh.completion import bash_completion, zsh_completion
from wssh.config import default_config_path, load_config, save_config
from wssh.connect import classify_ssh_failure, format_ssh_hint, run_ssh, run_ssh_capture
from wssh.server_setup import (
    explain_target_not_visible,
    maybe_offer_setup,
    setup_server_interactive,
    try_fix_target_role_access,
)
from wssh.setup_flow import run_setup
from wssh.ssh_key import (
    find_public_key,
    public_key_fingerprint,
    public_key_stored_correctly,
)
from wssh.targets import get_target_names, refresh_targets
from wssh.warpgate import WarpgateApiError, WarpgateClient

COMMANDS = frozenset({
    "setup",
    "auth",
    "targets",
    "credentials",
    "completion",
    "setup-server",
    "version",
    "config-path",
    "doctor",
})

app = typer.Typer(
    name="wssh",
    help="McKinnon Warpgate SSH client",
    no_args_is_help=True,
    add_completion=False,
)
auth_app = typer.Typer(help="Authentication")
targets_app = typer.Typer(help="Warpgate targets")
credentials_app = typer.Typer(help="Credential management")
app.add_typer(auth_app, name="auth")
app.add_typer(targets_app, name="targets")
app.add_typer(credentials_app, name="credentials")

console = Console()
_state_config_path: Optional[Path] = None
_state_dry_run: bool = False


def _parse_global_flags(argv: list[str]) -> list[str]:
    """Extract --config / --dry-run from argv; return remaining args."""
    global _state_config_path, _state_dry_run
    rest: list[str] = []
    i = 0
    while i < len(argv):
        arg = argv[i]
        if arg in ("--dry-run", "-n"):
            _state_dry_run = True
        elif arg in ("--verbose", "-v"):
            pass
        elif arg == "--config" and i + 1 < len(argv):
            _state_config_path = Path(argv[i + 1])
            i += 1
        else:
            rest.append(arg)
        i += 1
    return rest


def _config():
    return load_config(_state_config_path)


@app.callback(invoke_without_command=True)
def main_callback(ctx: typer.Context) -> None:
    if ctx.invoked_subcommand is None:
        console.print(ctx.get_help())


@app.command("setup")
def setup_cmd(
    dry_run: bool = typer.Option(False, "--dry-run", "-n"),
    manual_credentials: bool = typer.Option(
        False,
        "--manual-credentials",
        help="Paste SSH key in Warpgate UI instead of API upload",
    ),
    skip_auth: bool = typer.Option(False, "--skip-auth"),
) -> None:
    """First-time setup: email, SSH key, auth, shell completion."""
    run_setup(
        dry_run=dry_run or _state_dry_run,
        manual_credentials=manual_credentials,
        skip_auth=skip_auth,
    )


@auth_app.command("login")
def auth_login(
    token: Optional[str] = typer.Option(None, "--token", help="Paste an existing API token"),
    provider: str = typer.Option("google", "--provider"),
    no_browser_cookies: bool = typer.Option(
        False,
        "--no-browser-cookies",
        help="Do not try to read session cookies from the browser",
    ),
) -> None:
    """Sign in via Google SSO and store an API token."""
    login_interactive(
        _config(),
        provider=provider,
        token=token,
        use_browser_cookies=not no_browser_cookies,
    )


@auth_app.command("logout")
def auth_logout() -> None:
    """Remove the stored API token."""
    logout(_config())


@targets_app.command("list")
def targets_list(
    cache_only: bool = typer.Option(
        False, "--cache-only", help="Use cache only (for completion hooks)"
    ),
    force: bool = typer.Option(False, "--force", "-f", help="Refresh from API"),
) -> None:
    """List SSH targets you can access."""
    try:
        names = get_target_names(
            _config(), force_refresh=force, cache_only=cache_only
        )
    except WarpgateApiError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(1) from exc
    for name in names:
        typer.echo(name)


@targets_app.command("refresh")
def targets_refresh_cmd() -> None:
    """Refresh the local targets cache."""
    try:
        names = refresh_targets(_config())
    except WarpgateApiError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(1) from exc
    console.print(f"[green]Cached {len(names)} SSH target(s)[/green]")


@credentials_app.command("add-key")
def credentials_add_key(
    key_path: Optional[Path] = typer.Option(None, "--key", help="Path to .pub file"),
    label: Optional[str] = typer.Option(None, "--label"),
) -> None:
    """Upload your SSH public key to Warpgate."""
    config = _config()
    if not config.effective_api_token():
        console.print("[red]No API token — run: wssh auth login[/red]")
        raise typer.Exit(1)
    if key_path:
        line = key_path.read_text(encoding="utf-8").strip()
    else:
        found = find_public_key()
        if not found:
            console.print("[red]No SSH public key found[/red]")
            raise typer.Exit(1)
        line = found.openssh_line
    import socket

    key_label = label or f"wssh ({socket.gethostname()})"
    with WarpgateClient(config) as client:
        existing = client.find_matching_public_key(line)
        if existing:
            stored = existing.get("openssh_public_key") or existing.get("opensshPublicKey")
            if stored and not public_key_stored_correctly(stored):
                existing_label = existing.get("label") or "existing key"
                console.print(
                    "[yellow]A matching key is registered but was saved in the wrong "
                    f"format ({existing_label}).[/yellow]\n"
                    "Delete it in Warpgate credentials, then run this command again."
                )
                raise typer.Exit(1)
            fp = public_key_fingerprint(line)
            existing_label = existing.get("label") or "existing key"
            console.print(
                f"[green]Public key already registered[/green] "
                f"([dim]{fp} — {existing_label}[/dim])"
            )
            return
        client.add_public_key(key_label, line)
    console.print("[green]Public key added[/green]")


@app.command("completion")
def completion_cmd(shell: str = typer.Argument(..., help="bash or zsh")) -> None:
    """Print shell completion script (eval from your rc file)."""
    if shell == "bash":
        typer.echo(bash_completion())
    elif shell == "zsh":
        typer.echo(zsh_completion())
    else:
        console.print(f"[red]Unknown shell: {shell}[/red]")
        raise typer.Exit(1)


@app.command("setup-server")
def setup_server_cmd(
    name: str = typer.Argument(..., help="Warpgate target name (e.g. dns01)"),
    dry_run: bool = typer.Option(False, "--dry-run", "-n"),
) -> None:
    """Install Warpgate keys on a server and register it in Warpgate."""
    try:
        setup_server_interactive(_config(), name, dry_run=dry_run or _state_dry_run)
    except WarpgateApiError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(1) from exc


@app.command("version")
def version_cmd() -> None:
    typer.echo(__version__)


@app.command("config-path")
def config_path_cmd() -> None:
    typer.echo(str(_state_config_path or default_config_path()))


@app.command("doctor")
def doctor_cmd() -> None:
    """Check for install issues (e.g. old shell function shadowing wssh)."""
    from wssh.doctor import run_doctor

    raise typer.Exit(run_doctor())


def connect(target: str, ssh_args: list[str]) -> int:
    """Connect via Warpgate; return ssh exit code."""
    config = _config()
    if not config.user:
        console.print("[red]Not configured — run: wssh setup[/red]")
        return 1

    try:
        known = get_target_names(config, cache_only=False)
        if known and target not in known:
            if explain_target_not_visible(config, target):
                if try_fix_target_role_access(config, target):
                    return run_ssh(config, target, ssh_args)
                return 1
            if maybe_offer_setup(config, target, "unknown_target"):
                return run_ssh(config, target, ssh_args)
    except WarpgateApiError:
        pass

    code = run_ssh(config, target, ssh_args)
    if code == 0:
        return 0

    _, _, stderr = run_ssh_capture(config, target, ["true"])
    kind = classify_ssh_failure(stderr)
    if maybe_offer_setup(config, target, kind):
        return run_ssh(config, target, ssh_args)

    console.print(format_ssh_hint(stderr, target=target))
    return code


def main() -> None:
    argv = _parse_global_flags(sys.argv[1:])
    try:
        if not argv:
            app()
            return
        if argv[0] in COMMANDS or argv[0].startswith("-"):
            sys.argv = ["wssh", *argv]
            app()
            return
        target = argv[0]
        ssh_args = argv[1:]
        if ssh_args and ssh_args[0] == "--":
            ssh_args = ssh_args[1:]
        sys.exit(connect(target, ssh_args))
    except typer.Exit as exc:
        sys.exit(exc.exit_code)


if __name__ == "__main__":
    main()
