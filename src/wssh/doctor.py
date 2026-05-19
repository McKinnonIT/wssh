"""Diagnose common wssh installation problems."""

from __future__ import annotations

import shutil
import subprocess
import sys

from rich.console import Console

console = Console()


def _shell_wssh_type() -> str:
    try:
        result = subprocess.run(
            ["sh", "-c", "type wssh 2>&1 || true"],
            capture_output=True,
            text=True,
            check=False,
        )
        return (result.stdout + result.stderr).strip()
    except OSError:
        return ""


def run_doctor() -> int:
    issues = 0
    wssh_type = _shell_wssh_type()
    pipx_bin = shutil.which("wssh")

    console.print("\n[bold]wssh doctor[/bold]\n")

    if "function" in wssh_type or "is a shell function" in wssh_type:
        issues += 1
        console.print("[red]Problem:[/red] A legacy [bold]wssh()[/bold] shell function is active.")
        console.print("  Commands like [bold]wssh setup[/bold] SSH to a host named 'setup', not the CLI.\n")
        console.print("[green]Fix:[/green]")
        console.print("  1. Remove the block between these lines from ~/.zshrc (or ~/.bashrc):")
        console.print("     [dim]# >>> warpgate wssh wrapper >>>[/dim]")
        console.print("     [dim]# <<< warpgate wssh wrapper <<<[/dim]")
        console.print("  2. Reload: [bold]source ~/.zshrc[/bold]")
        console.print("  3. Run setup with: [bold]command wssh setup[/bold]")
        console.print("     or: [bold]~/.local/bin/wssh setup[/bold]\n")
    else:
        console.print("[green]OK[/green] No legacy shell function shadowing wssh.")

    if pipx_bin:
        console.print(f"[green]OK[/green] wssh binary: {pipx_bin}")
    else:
        issues += 1
        console.print("[red]Problem:[/red] wssh not found on PATH — run [bold]pipx install .[/bold]")

    if wssh_type and pipx_bin and "function" not in wssh_type:
        try:
            result = subprocess.run(
                [pipx_bin, "version"],
                capture_output=True,
                text=True,
                check=False,
                timeout=10,
            )
            if result.returncode == 0:
                console.print(f"[green]OK[/green] CLI version: {result.stdout.strip()}")
            else:
                issues += 1
                console.print("[red]Problem:[/red] wssh binary failed to run.")
        except subprocess.TimeoutExpired:
            issues += 1
            console.print("[red]Problem:[/red] wssh binary timed out.")

    console.print()
    return 1 if issues else 0


def main() -> None:
    sys.exit(run_doctor())
