"""wssh CLI entry point."""

from __future__ import annotations

import sys
from pathlib import Path

import typer
from rich.console import Console
from rich.prompt import Confirm

from wssh import __version__
from wssh.auth import login_interactive, logout
from wssh.completion import bash_completion, command_tree, zsh_completion
from wssh.config import default_config_path, load_config
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
from wssh.targets import get_target_names, suggest_targets
from wssh.update import maybe_notify_update, report_update_status, run_update
from wssh.warpgate import WarpgateApiError, WarpgateClient

app = typer.Typer(
    name="wssh",
    help="SSH to Warpgate targets from your terminal",
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
_state_config_path: Path | None = None


def _parse_global_flags(argv: list[str]) -> list[str]:
    """Extract --config <path> from argv; return remaining args.

    Typer owns every other flag — this only exists because a bare target name
    (``wssh dns01``) is not a subcommand and never reaches Typer.
    """
    global _state_config_path
    rest: list[str] = []
    i = 0
    while i < len(argv):
        if argv[i] == "--config" and i + 1 < len(argv):
            _state_config_path = Path(argv[i + 1])
            i += 1
        else:
            rest.append(argv[i])
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
        dry_run=dry_run,
        manual_credentials=manual_credentials,
        skip_auth=skip_auth,
    )


@auth_app.command("login")
def auth_login(
    token: str | None = typer.Option(None, "--token", help="Paste an existing API token"),
    no_browser_cookies: bool = typer.Option(
        False,
        "--no-browser-cookies",
        help="Do not try to read session cookies from the browser",
    ),
) -> None:
    """Sign in via the Warpgate web UI and store an API token."""
    login_interactive(
        _config(),
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
        names = get_target_names(_config(), force_refresh=True)
    except WarpgateApiError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(1) from exc
    console.print(f"[green]Cached {len(names)} SSH target(s)[/green]")


@credentials_app.command("add-key")
def credentials_add_key(
    key_path: Path | None = typer.Option(None, "--key", help="Path to .pub file"),
    label: str | None = typer.Option(None, "--label"),
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
        setup_server_interactive(_config(), name, dry_run=dry_run)
    except WarpgateApiError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(1) from exc


@app.command("update")
def update_cmd(
    check: bool = typer.Option(
        False, "--check", help="Only report whether an update is available"
    ),
) -> None:
    """Update wssh to the latest version from GitHub."""
    raise typer.Exit(report_update_status() if check else run_update())


@app.command("version")
def version_cmd() -> None:
    """Show the installed wssh version."""
    typer.echo(__version__)


@app.command("config-path")
def config_path_cmd() -> None:
    """Print the path to the active config file."""
    typer.echo(str(_state_config_path or default_config_path()))


def _offer_setup(config, target: str, kind: str) -> bool:
    """maybe_offer_setup, skipped when stdin is not a tty — it asks Confirm questions,
    and a prompt written into a pipe just hangs on input nobody can supply."""
    return sys.stdin.isatty() and maybe_offer_setup(config, target, kind)


def _resolve_typo(target: str, known: list[str]) -> str | None:
    """Offer the closest known target for a name that is not one. None = no match taken."""
    matches = suggest_targets(target, known)
    if not matches:
        return None
    console.print(f"\n[yellow]No target [bold]{target}[/bold] in Warpgate.[/yellow]")
    if len(matches) > 1:
        console.print(f"  [dim]Close matches: {', '.join(matches)}[/dim]")
    if not sys.stdin.isatty():
        # Piped or scripted: suggest, never block on a prompt nobody can see.
        console.print(f"  [dim]Did you mean [bold]{matches[0]}[/bold]?[/dim]")
        return None
    if Confirm.ask(f"Did you mean [bold]{matches[0]}[/bold]?", default=True):
        return matches[0]
    return None


def connect(target: str, ssh_args: list[str]) -> int:
    """Connect via Warpgate; return ssh exit code."""
    config = _config()
    if not config.host or not config.user:
        console.print("[red]Not configured — run: wssh setup[/red]")
        return 1

    try:
        known = get_target_names(config, cache_only=False)
        if known and target not in known:
            suggested = _resolve_typo(target, known)
            if suggested:
                target = suggested
            elif explain_target_not_visible(config, target):
                if try_fix_target_role_access(config, target):
                    return run_ssh(config, target, ssh_args)
                return 1
            elif _offer_setup(config, target, "unknown_target"):
                return run_ssh(config, target, ssh_args)
    except WarpgateApiError as exc:
        # Not fatal — ssh below may still work. But swallowing it silently made a
        # dead token look like an unknown target: no suggestions, no visibility
        # check, and an offer to re-register a server that was registered all along.
        console.print(f"[yellow]Could not check targets: {exc}[/yellow]")
        if exc.status_code == 401:
            console.print("[dim]Your API token is not valid — run: wssh auth login[/dim]")

    code = run_ssh(config, target, ssh_args)
    if code == 0:
        return 0

    _, stdout, stderr = run_ssh_capture(config, target, ["true"])
    kind = classify_ssh_failure(f"{stderr}\n{stdout}")
    if _offer_setup(config, target, kind):
        return run_ssh(config, target, ssh_args)

    console.print(format_ssh_hint(stderr, target=target, stdout=stdout))
    return code


def _dispatch(argv: list[str]) -> None:
    if not argv:
        app()
        return
    if argv[0] in command_tree() or argv[0].startswith("-"):
        sys.argv = ["wssh", *argv]
        app()
        return
    target = argv[0]
    ssh_args = argv[1:]
    if ssh_args and ssh_args[0] == "--":
        ssh_args = ssh_args[1:]
    sys.exit(connect(target, ssh_args))


def main() -> None:
    argv = _parse_global_flags(sys.argv[1:])
    # After the command, not before: a notice printed ahead of an ssh session is
    # gone by the time the session ends. `update` is exempt — it reports its own
    # result, and this process still sees the pre-update commit.
    notify = argv[:1] != ["update"]
    try:
        _dispatch(argv)
    except typer.Exit as exc:
        sys.exit(exc.exit_code)
    finally:
        if notify:
            maybe_notify_update()


if __name__ == "__main__":
    main()
