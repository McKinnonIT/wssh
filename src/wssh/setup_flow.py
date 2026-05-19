"""Interactive first-time setup."""

from __future__ import annotations

import os
import socket
import sys

from rich.console import Console
from rich.prompt import Confirm, Prompt

from wssh.auth import login_interactive
from wssh.config import WsshConfig, load_config, save_config
from wssh.constants import CREDENTIALS_URL
from wssh.email import git_default_email, is_org_email, normalize_email
from wssh.shell_rc import detect_rc_file, detect_shell_name, install_completion, remove_marked_blocks
from wssh.ssh_key import (
    copy_to_clipboard,
    find_public_key,
    generate_ed25519_key,
    normalize_openssh_public_key,
    public_key_stored_correctly,
)
from wssh.targets import refresh_targets
from wssh.warpgate import WarpgateApiError, WarpgateClient

console = Console()


def prompt_email(config: WsshConfig) -> str:
    console.print("\n[bold blue]Your Warpgate username[/bold blue]")
    default = git_default_email() or config.user
    if default and "@" not in default:
        default = normalize_email(default, config.domain)

    while True:
        hint = f" (e.g. firstname.lastname or full @{config.domain})"
        raw = Prompt.ask(
            "Google Workspace email" + (f" [{default}]" if default else hint),
            default=default or "",
            show_default=bool(default),
        ).strip()
        if not raw and default:
            raw = default
        email = normalize_email(raw, config.domain)
        if not email:
            console.print("[red]Email is required[/red]")
            continue
        if not is_org_email(email, config.domain):
            if not Confirm.ask(
                f"Expected @{config.domain} — continue with '{email}'?",
                default=False,
            ):
                continue
        console.print(f"[green]Using {email}[/green]")
        return email


def setup_ssh_key(
    config: WsshConfig,
    *,
    dry_run: bool = False,
    manual_credentials: bool = False,
) -> str | None:
    console.print("\n[bold blue]SSH key setup[/bold blue]")
    key = find_public_key()
    if key:
        console.print(f"[green]Found existing key: {key.path}[/green]")
    else:
        if not Confirm.ask("No SSH key found. Generate one now?", default=True):
            console.print("[yellow]Skipping SSH key — Google login required each time[/yellow]")
            return None
        if dry_run:
            console.print("[yellow]dry-run: would generate ~/.ssh/id_ed25519[/yellow]")
            return None
        key = generate_ed25519_key(config.user, dry_run=False)
        if key:
            console.print(f"[green]Generated {key.path}[/green]")

    if not key:
        return None

    if manual_credentials or not config.effective_api_token():
        openssh_line = normalize_openssh_public_key(key.openssh_line)
        if copy_to_clipboard(openssh_line):
            console.print("[green]Copied public key to clipboard[/green]")
        console.print(f"\n{openssh_line}\n")
        console.print("Paste into Warpgate credentials:")
        console.print(f"  {CREDENTIALS_URL}\n")
        if not dry_run:
            Prompt.ask("Press Enter when the key is saved", default="")
        return key.openssh_line

    if dry_run:
        console.print("[yellow]dry-run: would upload public key via API[/yellow]")
        return key.openssh_line

    try:
        with WarpgateClient(config) as client:
            existing = client.find_matching_public_key(key.openssh_line)
            if existing:
                stored = existing.get("openssh_public_key") or existing.get(
                    "opensshPublicKey"
                )
                existing_label = existing.get("label") or "existing key"
                if stored and not public_key_stored_correctly(stored):
                    console.print(
                        "[yellow]A matching key is registered but was saved in the wrong "
                        f"format ({existing_label}).[/yellow]\n"
                        "Delete it in Warpgate credentials, then run "
                        "[bold]wssh credentials add-key[/bold] again."
                    )
                else:
                    console.print(
                        "[green]Public key already registered in Warpgate[/green] "
                        f"[dim]({existing_label})[/dim]"
                    )
            else:
                label = f"wssh-setup ({socket.gethostname()})"
                client.add_public_key(label, key.openssh_line)
                console.print("[green]Uploaded public key to Warpgate[/green]")
    except WarpgateApiError as exc:
        console.print(f"[yellow]API upload failed: {exc}[/yellow]")
        console.print("Falling back to manual credentials flow…")
        return setup_ssh_key(config, dry_run=False, manual_credentials=True)

    return key.openssh_line


def run_setup(
    *,
    dry_run: bool = False,
    manual_credentials: bool = False,
    skip_auth: bool = False,
) -> None:
    if hasattr(os, "geteuid") and os.geteuid() == 0:
        console.print("[red]Do not run wssh setup as root.[/red]")
        sys.exit(1)

    console.print("\n[bold]McKinnon Warpgate SSH Setup[/bold]")
    if dry_run:
        console.print("[yellow]DRY RUN — no changes will be made[/yellow]")

    config = load_config()
    config.user = prompt_email(config)

    if not skip_auth and not dry_run and not manual_credentials:
        if not config.effective_api_token():
            console.print("\n[bold blue]Warpgate sign-in[/bold blue]")
            login_interactive(config)

    setup_ssh_key(config, dry_run=dry_run, manual_credentials=manual_credentials)

    if not dry_run:
        save_config(config)
        try:
            refresh_targets(config)
        except WarpgateApiError:
            pass

    rc_file = detect_rc_file()
    shell = detect_shell_name()
    console.print("\n[bold blue]Shell completion[/bold blue]")
    console.print(f"Installing completion in {rc_file}")
    if not dry_run:
        remove_marked_blocks(rc_file)
    install_completion(rc_file, shell, dry_run=dry_run)

    if dry_run:
        console.print("\n[yellow]Dry run complete — re-run without --dry-run to apply.[/yellow]\n")
        return

    save_config(config)
    console.print("\n[bold green]Setup complete[/bold green]")
    console.print(f"Reload your shell: [bold]source {rc_file}[/bold]")
    console.print("Example: [bold]wssh dns01[/bold]\n")
