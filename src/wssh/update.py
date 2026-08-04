"""Reinstall wssh from GitHub (``wssh update``)."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys

from rich.console import Console

DEFAULT_REPO = "https://github.com/McKinnonIT/wssh.git"

console = Console()


def repo_spec() -> str:
    """pip requirement for the wssh repo. WSSH_REPO overrides it, as install.sh allows."""
    return f"git+{os.environ.get('WSSH_REPO', '').strip() or DEFAULT_REPO}"


def update_command() -> list[str]:
    """pipx when it is on PATH (how install.sh installs), else pip into this interpreter.

    ``--force`` / ``--force-reinstall`` are not optional: the version in
    pyproject rarely changes between commits, so pip would otherwise decide the
    requirement is already satisfied and install nothing.
    """
    spec = repo_spec()
    if shutil.which("pipx"):
        return ["pipx", "install", "--force", spec]
    return [sys.executable, "-m", "pip", "install", "--force-reinstall", spec]


def run_update() -> int:
    cmd = update_command()
    console.print(f"[dim]$ {' '.join(cmd)}[/dim]")
    code = subprocess.call(cmd)
    if code != 0:
        console.print("[red]Update failed[/red]")
        return code
    console.print("[green]wssh updated[/green] [dim]— open a new shell to reload completion[/dim]")
    return 0
